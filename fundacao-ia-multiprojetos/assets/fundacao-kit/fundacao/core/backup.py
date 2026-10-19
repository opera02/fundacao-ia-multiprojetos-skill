"""Estado de referência, backup e restauração (livro A05, A18, A35; 3.0 R13).

- Banco: cópia consistente pela API de backup do SQLite (nunca copiar o arquivo
  em uso sem o -wal) + PRAGMA integrity_check + comparação lógica. A cópia sai do modo
  WAL (abrir para conferir não cria `-wal`/`-shm`) e o manifesto guarda o SHA-256 do
  arquivo do banco e o resumo lógico; a verificação confere os dois.
- Arquivos: manifesto com hash e tamanho; credenciais nunca entram.
- Restauração sempre em destino separado; antes de liberar o uso, reaplicar o que o
  registro protegido guarda depois do snapshot: retiradas (senão a fonte ou a memória
  retirada "ressuscita") e revogações de acesso (senão quem perdeu o acesso o recupera).
- O registro protegido (`state/retiradas.jsonl`) tem identidade própria, criada pelo `init`
  e anotada no manifesto: a restauração recusa registro de outra fundação ou recriado.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from pathlib import Path

from .canon import canonical_json, sha256_file, sha256_text
from .contracts import ValidationError
from .db import connect, transaction, uri_somente_leitura, utcnow
from .ids import new_id

EXCLUDE_PARTS = {"__pycache__", ".venv", "node_modules", ".git"}
EXCLUDE_NAMES = {".env", "state.sqlite", "state.sqlite-wal", "state.sqlite-shm"}
FILE_DIRS = ("fundacao", "registry", "templates", "projects")
REGISTRO = "registro"  # tipo da linha de identidade do registro protegido
SCHEMA_REGISTRO = "fundacao.retiradas/1"
MARCA_NAO_LIBERADA = "restauracao-nao-liberada.json"
# Campos exigidos por tipo de linha (sem `entity_type` = fonte, formato gravado pela 1.1.0).
_CAMPOS = {
    "source": ("entity_id", "decided_by", "decided_at"),
    "memory": ("entity_id", "decided_by", "decided_at"),
    "acl_revoke": ("entity_id", "principal", "resource", "action", "decided_by", "decided_at"),
    "component_disable": ("entity_id", "component_id", "decided_by", "decided_at"),
}
# Arquivos que o sistema operacional cria sozinho numa pasta (Explorer em pasta de rede, Finder):
# não contam como "extras" na verificação e não são restaurados.
METADADOS_DO_SO = ("Thumbs.db", "ehthumbs.db", "desktop.ini", ".DS_Store")
# O que a restauração NÃO reaplica (vai na resposta, para conferência da administração).
NAO_REAPLICADO = [
    "concessões de acesso posteriores à cópia (reconceder é decisão da administração)",
    "habilitação de componente posterior à cópia (o componente volta desligado)",
    "alterações em arquivos posteriores à cópia, como registry/route_policy.json: confira à mão",
]


def _files(root: Path):
    for top in FILE_DIRS:
        base = root / top
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and not (set(path.relative_to(root).parts) & EXCLUDE_PARTS) \
                    and path.name not in EXCLUDE_NAMES and not path.name.endswith(".pyc"):
                yield path


def logical_summary(db_path: Path, *, copia: bool = False) -> dict:
    """Resumo lógico lido em modo somente leitura (não grava nada no banco conferido). `copia=True`
    (cópia de backup): leitura imutável, só do arquivo do banco, sem criar `-wal`/`-shm`."""
    con = sqlite3.connect(uri_somente_leitura(db_path, imutavel=copia), uri=True)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            " AND name NOT LIKE 'fts_%' ORDER BY name")]
        counts = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        user_version = con.execute("PRAGMA user_version").fetchone()[0]
    finally:
        con.close()
    return {"tables": counts, "integrity_check": integrity, "user_version": user_version}


# ------------------------------------------------------------------ registro protegido
def _ilegivel(linha: int, motivo: str) -> ValidationError:
    return ValidationError("registro de retiradas ilegível", linha=linha, motivo=motivo)


def _ler_texto(log_path: Path) -> str | None:
    path = Path(log_path)
    if not path.exists():
        return None
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise _ilegivel(0, "não é texto UTF-8") from None


def _ler_registro(log_path: Path, *, estrito: bool = False) -> tuple[str | None, list[tuple[str, dict]]]:
    """Lê e valida o registro inteiro antes de qualquer uso. Devolve a identidade e as linhas de
    retirada/revogação (texto e objeto), sem a linha de identidade. Tipo de linha desconhecido
    (gravado por um kit mais novo) só é recusado com `estrito=True` — a restauração, que precisa
    reaplicar tudo; contar linhas (backup) e preencher retiradas (init) o aceitam."""
    texto = _ler_texto(log_path)
    if texto is None:
        return None, []
    return _analisar_registro(texto, estrito=estrito)


def _analisar_registro(texto: str, *, estrito: bool = False) -> tuple[str | None, list[tuple[str, dict]]]:
    log_id, linhas = None, []
    for n, line in enumerate(texto.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            raise _ilegivel(n, "JSON inválido") from None
        if not isinstance(rec, dict):
            raise _ilegivel(n, "linha não é objeto")
        tipo = rec.get("entity_type", "source")
        if tipo == REGISTRO:
            if log_id is not None or not isinstance(rec.get("log_id"), str) or not rec["log_id"]:
                raise _ilegivel(n, "identidade repetida ou vazia")
            log_id = rec["log_id"]
            continue
        campos = _CAMPOS.get(tipo)
        if campos is None:
            if estrito or not isinstance(tipo, str) or not isinstance(rec.get("entity_id"), str):
                raise _ilegivel(n, "tipo de linha desconhecido (registro de kit mais novo? atualize o kit)")
            linhas.append((line, rec))
            continue
        if any(not isinstance(rec.get(c), str) or not rec[c] for c in campos):
            raise _ilegivel(n, "campo obrigatório ausente")
        if tipo in ("source", "memory") and not isinstance(rec.get("reason"), str):
            raise _ilegivel(n, "motivo ausente")
        if tipo == "source" and not re.fullmatch(r".+@\d+", rec["entity_id"]):
            raise _ilegivel(n, "fonte sem versão (esperado id@versão)")
        afetadas = rec.get("affected", [])
        if tipo == "memory" and not (isinstance(afetadas, list) and all(isinstance(a, str) for a in afetadas)):
            raise _ilegivel(n, "derivados da memória em formato inválido")
        linhas.append((line, rec))
    return log_id, linhas


def default_tombstone_log(con: sqlite3.Connection) -> Path | None:
    """Registro protegido padrão: `<raiz>/state/retiradas.jsonl`, ao lado do banco."""
    for row in con.execute("PRAGMA database_list"):
        if row[1] == "main" and row[2]:
            return Path(row[2]).parent / "retiradas.jsonl"
    return None


def ensure_tombstone_log(log_path: Path) -> str:
    """Garante o registro protegido com identidade própria (o `init` chama). Registro de kit
    anterior, sem identidade, recebe-a numa linha nova ao final: nada é reescrito."""
    path = Path(log_path)
    log_id, _ = _ler_registro(path)
    if log_id:
        return log_id
    log_id = new_id("reg")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(canonical_json({"entity_type": REGISTRO, "log_id": log_id, "criado_em": utcnow(),
                                 "schema_version": SCHEMA_REGISTRO}) + "\n")
    return log_id


def tombstone_state(log_path: Path) -> dict:
    """Identidade, quantidade de linhas de retirada/revogação e hash da última (cobertura)."""
    log_id, linhas = _ler_registro(log_path)
    return {"log_id": log_id, "linhas": len(linhas),
            "ultima_sha256": sha256_text(linhas[-1][0]) if linhas else None}


def read_tombstone_log(log_path: Path) -> list[dict]:
    return [rec for _, rec in _ler_registro(log_path)[1]]


def append_tombstone_log(log_path: Path, record: dict) -> None:
    """Registro protegido, mantido FORA do backup, para reaplicação. Registro novo nasce com identidade.
    A linha só conta como gravada depois de `fsync` (durabilidade conferida antes de marcar a outbox)."""
    log_path = Path(log_path)
    if not log_path.exists() or log_path.stat().st_size == 0:
        ensure_tombstone_log(log_path)
    with log_path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(canonical_json(record) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


# ------------------------------------------------------------------ outbox do registro protegido
def enqueue_protected(con: sqlite3.Connection, record: dict) -> str:
    """Grava a intenção de exportar `record` ao registro protegido NA MESMA transação da decisão
    (revogação, retirada, desativação): se o append falhar ou o processo cair depois do commit, a
    intenção continua no banco e é exportada depois (auditoria F11). Chame dentro da transação."""
    outbox_id = new_id("obx")
    con.execute("INSERT INTO protected_outbox (outbox_id, record_json, created_at) VALUES (?,?,?)",
                (outbox_id, canonical_json({**record, "outbox_id": outbox_id}), utcnow()))
    return outbox_id


def outbox_pending(con: sqlite3.Connection) -> int:
    return con.execute("SELECT COUNT(*) FROM protected_outbox WHERE exported_at IS NULL").fetchone()[0]


def flush_outbox(con: sqlite3.Connection, log_path: Path | None = None) -> dict:
    """Exporta, em ordem, as intenções pendentes para o registro protegido. Idempotente: a linha que
    já está no registro (queda depois do append, antes da marca) não é gravada de novo. Levanta o
    erro de gravação; o que não foi gravado continua pendente para a próxima tentativa — que
    acontece em toda nova decisão protegida, no `init`, no backup e ao abrir a fundação pela CLI."""
    pendentes = con.execute("SELECT outbox_id, record_json FROM protected_outbox WHERE exported_at IS NULL"
                            " ORDER BY rowid").fetchall()
    if not pendentes:
        return {"exportadas": 0, "pendentes": 0}
    log = Path(log_path) if log_path else default_tombstone_log(con)
    if log is None:
        return {"exportadas": 0, "pendentes": len(pendentes)}
    ja_gravadas = {rec.get("outbox_id") for _, rec in _ler_registro(log)[1]}
    exportadas = 0
    for outbox_id, record_json in pendentes:
        if outbox_id not in ja_gravadas:
            append_tombstone_log(log, json.loads(record_json))
        with transaction(con):
            con.execute("UPDATE protected_outbox SET exported_at = ? WHERE outbox_id = ? AND exported_at IS NULL",
                        (utcnow(), outbox_id))
        exportadas += 1
    return {"exportadas": exportadas, "pendentes": 0}


def backfill_tombstone_log(con: sqlite3.Connection, log_path: Path) -> list[str]:
    """Acrescenta ao registro as retiradas que estão no banco e faltam nele (ex.: memórias retiradas
    com kit anterior à 1.2.0). Só entidades-raiz (versões de fonte e memórias): trechos e caches
    derivados são refeitos pela limpeza na reaplicação. Também recompõe, pela trilha de eventos,
    revogações de acesso e desativações de componente que um kit anterior à 1.4.0 confirmou no
    banco e não chegou a gravar no registro (falha ou queda depois do commit; auditoria F11)."""
    from .memory import withdrawal_closure  # import tardio evita ciclo
    novas = _recompor_pela_trilha(con, log_path)
    _, linhas = _ler_registro(log_path)
    conhecidas: set[str] = set()
    for _, rec in linhas:
        conhecidas.add(rec["entity_id"])
        conhecidas.update(rec.get("affected") or [])
    for row in con.execute("SELECT entity_id, project_id, decided_by, reason, decided_at FROM tombstone"
                           " ORDER BY decided_at, entity_id").fetchall():
        ent = row[0]
        if ent in conhecidas:
            continue
        if con.execute("SELECT 1 FROM memory_item WHERE memory_id = ?", (ent,)).fetchone():
            # Mesma resolução da retirada: inclui derivados registrados por `id@revisão` (F07).
            rec = {"entity_type": "memory", "entity_id": ent, "affected": withdrawal_closure(con, ent)}
        else:
            sid, _, ver = ent.rpartition("@")
            if not (sid and ver.isdigit() and con.execute(
                    "SELECT 1 FROM source_version WHERE source_id = ? AND version = ?", (sid, int(ver))).fetchone()):
                continue  # derivado (trecho, cache): refeito pela limpeza da fonte
            rec = {"entity_type": "source", "entity_id": ent}
        rec.update(project_id=row[1], decided_by=row[2] or "desconhecido", reason=row[3] or "",
                   decided_at=row[4] or utcnow(), origem="preenchido-pelo-init")
        append_tombstone_log(log_path, rec)
        conhecidas.update([ent, *rec.get("affected", [])])
        novas.append(ent)
    return novas


def _recompor_pela_trilha(con: sqlite3.Connection, log_path: Path) -> list[str]:
    """Revogação/desativação cuja decisão mais recente na trilha é posterior à última linha do
    registro para o mesmo alvo — e que continua valendo agora — volta ao registro. Errar aqui só
    acrescenta linha para um estado que já é o atual (o lado seguro: menos acesso)."""
    _, linhas = _ler_registro(log_path)
    ultima_linha: dict[str, str] = {}
    for _, rec in linhas:
        ultima_linha[rec["entity_id"]] = max(ultima_linha.get(rec["entity_id"], ""), rec.get("decided_at", ""))
    novas = []
    revogacoes: dict[tuple, tuple] = {}
    for ts, subject, payload in con.execute("SELECT ts, subject, payload_json FROM event WHERE kind = 'acl_revoke'"
                                            " ORDER BY seq"):
        p = json.loads(payload)
        if all(isinstance(p.get(k), str) for k in ("from", "resource", "action")):
            revogacoes[(p["from"], p["resource"], p["action"])] = (ts, subject)
    for (quem, recurso, acao), (ts, admin) in revogacoes.items():
        ent = f"acl:{quem}:{acao}:{recurso}"
        if ultima_linha.get(ent, "") >= ts:
            continue  # o registro já tem esta revogação (ou uma posterior)
        if con.execute("SELECT 1 FROM acl WHERE subject = ? AND resource = ? AND action = ?",
                       (quem, recurso, acao)).fetchone():
            continue  # concedida de novo depois: não há o que recompor
        append_tombstone_log(log_path, {"entity_type": "acl_revoke", "entity_id": ent, "principal": quem,
                                        "resource": recurso, "action": acao, "decided_by": admin or "desconhecido",
                                        "decided_at": ts, "origem": "recomposto-da-trilha"})
        novas.append(ent)
    raiz = Path(log_path).resolve().parent.parent
    desativacoes: dict[str, tuple] = {}
    for ts, subject, payload in con.execute("SELECT ts, subject, payload_json FROM event WHERE kind = 'component_disabled'"
                                            " ORDER BY seq"):
        cid = json.loads(payload).get("component_id")
        if isinstance(cid, str) and cid:
            desativacoes[cid] = (ts, subject)
    for cid, (ts, admin) in desativacoes.items():
        ent = f"componente:{cid}"
        arq = raiz / "registry" / "components" / f"{cid}.json"
        if ultima_linha.get(ent, "") >= ts or not arq.is_file():
            continue
        try:
            if json.loads(arq.read_text(encoding="utf-8")).get("enabled") is not False:
                continue  # habilitado de novo depois: não há o que recompor
        except (OSError, json.JSONDecodeError):
            continue
        append_tombstone_log(log_path, {"entity_type": "component_disable", "entity_id": ent, "component_id": cid,
                                        "decided_by": admin or "desconhecido", "decided_at": ts,
                                        "origem": "recomposto-da-trilha"})
        novas.append(ent)
    return novas


def _cobre(linhas: list[tuple[str, dict]], conhecido: dict) -> bool:
    """O registro informado precisa conter as linhas conhecidas quando a cópia foi feita."""
    n = int(conhecido.get("linhas") or 0)
    if not n:
        return True
    return len(linhas) >= n and sha256_text(linhas[n - 1][0]) == conhecido.get("ultima_sha256")


# ------------------------------------------------------------------ backup
def create_backup(root: Path, dest: Path, label: str) -> dict:
    root, dest = Path(root), Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError("destino de backup não vazio: não substitua uma referência anterior")
    src_db = root / "state" / "state.sqlite"
    if src_db.exists():
        # Decisão protegida que ainda não chegou ao registro (falha ou queda depois do commit) é
        # exportada antes; se não der, não há cópia: ela nasceria com lacuna (auditoria F11).
        con = connect(src_db)
        try:
            try:
                flush_outbox(con, root / "state" / "retiradas.jsonl")
            except (OSError, ValidationError) as exc:
                raise ValidationError("registro protegido com decisões pendentes de gravação: corrija o acesso ao "
                                      "registro (state/retiradas.jsonl) e repita; nenhuma cópia foi feita",
                                      erro=type(exc).__name__) from exc
        finally:
            con.close()
    # O registro protegido precisa existir, legível e com identidade, ANTES da cópia: é ele que a
    # restauração confere. Fundação de kit anterior: rode `init` (cria a identidade e preenche).
    retiradas = tombstone_state(root / "state" / "retiradas.jsonl")
    if not retiradas["log_id"]:
        raise ValidationError("registro de retiradas ausente ou sem identidade nesta raiz: rode `init` antes do backup")
    dest.mkdir(parents=True, exist_ok=True)
    files = []
    if src_db.exists():
        (dest / "state").mkdir()
        src = sqlite3.connect(str(src_db))
        dst = sqlite3.connect(str(dest / "state" / "state.sqlite"))
        try:
            src.backup(dst)  # cópia consistente mesmo com o banco em uso
            dst.execute("PRAGMA journal_mode = DELETE")  # cópia fora do WAL: conferir não cria -wal/-shm
        finally:
            dst.close()
            src.close()
    for path in _files(root):
        rel = path.relative_to(root)
        target = dest / "files" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        files.append({"path": rel.as_posix(), "size": path.stat().st_size, "sha256": sha256_file(path)})
    manifest = {
        "schema_version": "fundacao.backup/1",
        "label": label,
        "created_at": utcnow(),
        "db": logical_summary(dest / "state" / "state.sqlite", copia=True) if src_db.exists() else None,
        "db_sha256": sha256_file(dest / "state" / "state.sqlite") if src_db.exists() else None,
        "files": files,
        # Identidade do registro e linhas conhecidas no momento da cópia: na restauração, o registro
        # informado precisa ter a mesma identidade e alcançar pelo menos este ponto.
        "retiradas": retiradas,
        "excluded": sorted(EXCLUDE_NAMES | EXCLUDE_PARTS),
        "credentials": "não incluídas; restabelecer pelo mecanismo próprio de cada provedor",
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _ler_manifesto(backup_dir: Path) -> dict:
    """Manifesto com a estrutura esperada; senão, erro do contrato (não traceback)."""
    m = json.loads((Path(backup_dir) / "manifest.json").read_text(encoding="utf-8"))
    ok = (isinstance(m, dict) and isinstance(m.get("files"), list)
          and all(isinstance(f, dict) and isinstance(f.get("path"), str) and isinstance(f.get("sha256"), str)
                  for f in m["files"])
          and isinstance(m.get("db"), (dict, type(None))) and isinstance(m.get("retiradas"), (dict, type(None))))
    if not ok:
        raise ValidationError("manifesto da cópia com estrutura inválida: não é uma cópia desta fundação")
    return m


def verify_backup(backup_dir: Path) -> dict:
    """Confere a cópia contra o manifesto: hash de cada arquivo; no banco, o SHA-256 do arquivo
    (cópias da 1.3.1 em diante), a integridade e o resumo lógico (contagem por tabela e
    `user_version`). Banco trocado, tabela esvaziada ou banco ausente = não confere.
    Limite: manifesto e banco ficam na mesma pasta; quem puder reescrever os dois forja a cópia
    (proteja as cópias: 3-2-1-1-0, com uma imutável)."""
    backup_dir = Path(backup_dir)
    manifest = _ler_manifesto(backup_dir)
    changed, missing = [], []
    for f in manifest["files"]:
        path = backup_dir / "files" / f["path"]
        if not path.exists():
            missing.append(f["path"])
        elif sha256_file(path) != f["sha256"]:
            changed.append(f["path"])
    # Arquivo na cópia que o manifesto não lista também não confere: seria restaurado (até código
    # em fundacao/) sem que ninguém o tivesse copiado.
    base = backup_dir / "files"
    listados = {f["path"] for f in manifest["files"]}
    soltos = sorted(rel for rel in (p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file())
                    if rel not in listados) if base.is_dir() else []
    do_so = [rel for rel in soltos if rel.rsplit("/", 1)[-1] in METADADOS_DO_SO]
    extras = [rel for rel in soltos if rel not in do_so]
    db = backup_dir / "state" / "state.sqlite"
    esperado = manifest.get("db")
    db_check, db_problemas = None, []
    if db.exists():
        if manifest.get("db_sha256") and sha256_file(db) != manifest["db_sha256"]:
            db_problemas.append("hash do banco diferente do manifesto")
        db_check = logical_summary(db, copia=True)
        if db_check["integrity_check"] != "ok":
            db_problemas.append("integrity_check falhou")
        if esperado:
            tabelas = esperado.get("tables") or {}
            diferentes = sorted(t for t in set(tabelas) | set(db_check["tables"])
                                if tabelas.get(t) != db_check["tables"].get(t))
            if diferentes:
                db_problemas.append("contagens diferentes do manifesto: " + ", ".join(diferentes))
            if db_check["user_version"] != esperado.get("user_version"):
                db_problemas.append("user_version diferente do manifesto")
    elif esperado:
        db_problemas.append("banco ausente na cópia")
    resultado = {"ok": not changed and not missing and not extras and not db_problemas,
                 "changed": changed, "missing": missing, "extras": extras, "db": db_check,
                 "db_problemas": db_problemas}
    if do_so:
        resultado["ignorados_do_so"] = do_so  # metadados do sistema: nem conferidos nem restaurados
    if db.exists() and not manifest.get("db_sha256"):
        resultado["aviso"] = ("cópia anterior à 1.3.1: o banco é conferido só por integridade e contagens "
                              "(o manifesto não tem db_sha256); uma troca com as mesmas contagens passaria — "
                              "faça um backup novo")
    return resultado


# ------------------------------------------------------------------ restauração
def restore(backup_dir: Path, target_root: Path, tombstone_log: Path | None, *,
            aceitar_registro_nao_comprovado: bool = False, executado_por: str = "restauracao") -> dict:
    """Restaura em destino NOVO, reaplica o que o registro guarda e só então libera.

    Não libera (released=false), e não copia nada, quando: a cópia não confere; o registro não foi
    informado, não existe, é ilegível, tem identidade diferente da anotada na cópia (outra fundação
    ou registro recriado) ou não alcança as linhas conhecidas no momento da cópia. Cópia sem
    identidade anotada (kit anterior à 1.3.0) e sem retiradas só libera com aceitação explícita,
    que fica na resposta e na trilha. Reaplica por tipo: fonte (`id@versão`, com limpeza dos
    derivados), memória (com os derivados registrados) e revogação de acesso (só as posteriores
    à cópia). Cada reaplicação vira evento na trilha restaurada. Até liberar, o destino carrega
    `state/restauracao-nao-liberada.json`, e a CLI recusa usar essa raiz.

    Ponto de corte coerente (auditoria F12): o registro é relido depois da reaplicação e, se
    cresceu (escritores ativos na origem), as linhas novas também são reaplicadas, até ficar
    estável; registro reescrito (não só acrescido) ou que não para de mudar impede a liberação. O
    registro do destino recebe exatamente o conteúdo reaplicado — nunca uma cópia posterior do
    arquivo vivo —, então banco e registro do destino refletem o mesmo corte (`corte_do_registro`
    na resposta). Decisões protegidas confirmadas no banco copiado e ainda não exportadas (outbox)
    entram no registro do destino antes de liberar."""
    backup_dir, target_root = Path(backup_dir), Path(target_root)
    if target_root.exists() and any(target_root.iterdir()):
        raise FileExistsError("restaure em diretório novo ou vazio; nunca sobre a origem")
    check = verify_backup(backup_dir)

    def nao_liberar(reason: str, **extra) -> dict:
        return {"released": False, "reason": reason, "check": check, **extra}

    if not check["ok"]:
        return nao_liberar("backup íntegro? não")
    if tombstone_log is None:
        return nao_liberar("registro de retiradas indisponível: não liberar")
    if not Path(tombstone_log).is_file():
        return nao_liberar("registro de retiradas inexistente no caminho informado: não liberar")
    manifest = _ler_manifesto(backup_dir)
    try:
        texto = _ler_texto(Path(tombstone_log)) or ""  # conteúdo capturado UMA vez: é o corte inicial
        log_id, linhas = _analisar_registro(texto, estrito=True)  # validado antes de copiar
    except ValidationError as exc:
        return nao_liberar(f"registro de retiradas ilegível (linha {exc.details.get('linha')}: "
                           f"{exc.details.get('motivo')}): não liberar")
    conhecido = manifest.get("retiradas") or {}
    ressalva = None
    if conhecido.get("log_id"):
        if log_id != conhecido["log_id"]:
            if not aceitar_registro_nao_comprovado:
                return nao_liberar("registro de retiradas com identidade diferente da anotada na cópia "
                                   "(outra fundação ou registro recriado): não liberar")
            ressalva = "identidade do registro diferente da anotada na cópia; aceito por decisão explícita"
    elif not conhecido.get("linhas"):
        if not aceitar_registro_nao_comprovado:
            return nao_liberar("cópia sem identidade do registro e sem retiradas para conferir (kit anterior à "
                               "1.3.0): nada prova que este registro é desta fundação; confira-o e use a "
                               "aceitação explícita")
        ressalva = "cópia sem identidade do registro; registro aceito por decisão explícita"
    if not _cobre(linhas, conhecido):
        return nao_liberar("registro de retiradas não alcança as retiradas da cópia "
                           "(outro registro ou registro truncado): não liberar")
    posicao = int(conhecido.get("linhas") or 0)  # linhas já refletidas no banco copiado

    shutil.copytree(backup_dir / "files", target_root, dirs_exist_ok=True,  # destino novo ou vazio
                    ignore=shutil.ignore_patterns(*METADADOS_DO_SO))
    (target_root / "state").mkdir(parents=True, exist_ok=True)
    marca = target_root / "state" / MARCA_NAO_LIBERADA
    marca.write_text(json.dumps({"copia": manifest.get("label"), "inicio": utcnow(),
                                 "situacao": "restauração em andamento ou não liberada: não use esta raiz"},
                                ensure_ascii=False), encoding="utf-8")
    shutil.copy2(backup_dir / "state" / "state.sqlite", target_root / "state" / "state.sqlite")
    con = connect(target_root / "state" / "state.sqlite")
    reapplied: list[str] = []
    destino_log = target_root / "state" / "retiradas.jsonl"
    mesmo_registro = Path(tombstone_log).resolve() == destino_log.resolve()
    try:
        from . import events, revisions  # import tardio evita ciclo
        from .auth import Principal, resource_project, scope_of
        from .knowledge import KnowledgeService
        system = Principal(executado_por, "processo-de-restauracao")

        def evento(rec: dict, tipo: str) -> None:
            events.emit(con, "restore_reapplied", project_id=rec.get("project_id"), subject=system.principal_id,
                        payload={"tipo": tipo, "entidade": rec["entity_id"], "decidido_por": rec["decided_by"],
                                 "decidido_em": rec["decided_at"], "copia": manifest.get("label")})

        def reaplicar(idx: int, rec: dict) -> None:
            tipo = rec.get("entity_type", "source")
            entity = rec["entity_id"]
            if tipo == "acl_revoke":
                if idx < posicao:
                    return  # anterior à cópia: já refletida no banco copiado
                with transaction(con):
                    apagadas = con.execute("DELETE FROM acl WHERE subject = ? AND resource = ? AND action = ?",
                                           (rec["principal"], rec["resource"], rec["action"])).rowcount
                    if apagadas:
                        revisions.bump(con, scope_of(rec["resource"]), "policy_rev")
                        evento(rec, tipo)
                if apagadas:
                    reapplied.append(entity)
                return
            if tipo == "component_disable":
                if idx < posicao:
                    return  # anterior à cópia: o arquivo copiado já está desligado
                comp = target_root / "registry" / "components" / f"{rec['component_id']}.json"
                if comp.is_file():
                    entrada = json.loads(comp.read_text(encoding="utf-8"))
                    if entrada.get("enabled"):
                        entrada["enabled"] = False
                        tmp = comp.with_suffix(".tmp")
                        tmp.write_text(json.dumps(entrada, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                        tmp.replace(comp)
                        evento(rec, tipo)
                        reapplied.append(entity)
                return
            if tipo == "memory":
                ids = [entity] + [a for a in rec.get("affected", []) if a != entity]
                novos = [i for i in ids if not con.execute(
                    "SELECT 1 FROM tombstone WHERE entity_id = ?", (i,)).fetchone()]
                if not novos:
                    return
                with transaction(con):
                    for i in novos:
                        con.execute("INSERT INTO tombstone VALUES (?,?,?,?,?,?)",
                                    (i, rec.get("project_id"), rec["decided_by"], rec["reason"], rec["decided_at"],
                                     "done"))
                        con.execute("UPDATE memory_item SET status = 'withdrawn' WHERE memory_id = ?", (i,))
                    evento(rec, tipo)
                reapplied.append(entity)
                return
            if con.execute("SELECT 1 FROM tombstone WHERE entity_id = ?", (entity,)).fetchone():
                return
            source_id, version = entity.rsplit("@", 1)
            with transaction(con):
                con.execute(
                    "INSERT INTO tombstone VALUES (?,?,?,?,?,?)",
                    (entity, rec.get("project_id"), rec["decided_by"], rec["reason"], rec["decided_at"], "pending"),
                )
                con.execute(
                    "UPDATE source_version SET status = 'withdrawn', is_current = 0 WHERE source_id = ? AND version = ?",
                    (source_id, int(version)),
                )
                if rec.get("project_id"):
                    revisions.bump(con, resource_project(rec["project_id"]), "corpus_rev")
                evento(rec, tipo)
            KnowledgeService(target_root, con, system).cleanup(entity)
            reapplied.append(entity)

        for idx, (_, rec) in enumerate(linhas):
            reaplicar(idx, rec)
        # Escritores ativos na origem: o que entrou no registro durante a restauração também entra.
        for _rodada in range(5):
            if mesmo_registro:
                break
            atual = _ler_texto(Path(tombstone_log)) or ""
            if atual == texto:
                break
            if not atual.startswith(texto):
                return nao_liberar("registro de retiradas reescrito durante a restauração (não só acrescido): "
                                   "não liberar; confira o registro e restaure de novo", reapplied=reapplied)
            try:
                _, todas = _analisar_registro(atual, estrito=True)
            except ValidationError as exc:
                return nao_liberar(f"registro de retiradas ilegível depois da cópia (linha {exc.details.get('linha')}):"
                                   " não liberar", reapplied=reapplied)
            for idx in range(len(linhas), len(todas)):
                reaplicar(idx, todas[idx][1])
            texto, linhas = atual, todas
        else:
            return nao_liberar("registro de retiradas continua mudando durante a restauração: pare os escritores "
                               "da origem e restaure de novo", reapplied=reapplied)
        if not mesmo_registro:
            # O destino segue com o registro NO MESMO CORTE do banco: o conteúdo reaplicado, não o arquivo vivo.
            destino_log.write_bytes(texto.encode("utf-8"))
        try:
            pendentes = flush_outbox(con, destino_log)  # decisões do banco copiado ainda não exportadas
        except (OSError, ValidationError) as exc:
            return nao_liberar(f"decisões da cópia não puderam ir ao registro do destino ({type(exc).__name__}): "
                               "não liberar", reapplied=reapplied)
        corte = {"linhas": len(linhas), "ultima_sha256": sha256_text(linhas[-1][0]) if linhas else None}
        events.emit(con, "restore_completed", subject=system.principal_id,
                    payload={"copia": manifest.get("label"), "registro": log_id, "reaplicadas": len(reapplied),
                             "corte_do_registro": corte, "outbox_da_copia": pendentes["exportadas"],
                             **({"ressalva": ressalva} if ressalva else {})})
        summary = logical_summary(target_root / "state" / "state.sqlite")
    finally:
        con.close()
    released = summary["integrity_check"] == "ok"
    if released:
        marca.unlink()
    result = {"released": released, "reapplied": reapplied, "registro": log_id, "nao_reaplicado": NAO_REAPLICADO,
              "corte_do_registro": corte, "db": summary, "check": check}
    if ressalva:
        result["ressalva"] = ressalva
    if check.get("aviso"):
        result["aviso_copia"] = check["aviso"]
    from .. import KIT_VERSION  # import tardio: versão do kit que está restaurando
    kit_copia = _versao_do_kit(target_root)
    if kit_copia and kit_copia != KIT_VERSION:
        # A raiz restaurada roda o kit que veio na cópia; o registro protegido pode ter tipos mais novos.
        result["kit_da_copia"] = kit_copia
        result["acao_necessaria"] = (f"a raiz restaurada traz o kit {kit_copia} da cópia (este é o {KIT_VERSION}); "
                                     "antes de usá-la, atualize o kit nela (instalar_kit.py --destino <destino> "
                                     "--atualizar) e rode `python -m fundacao init`")
    alvo = str(target_root.resolve())
    if alvo.startswith("\\\\?\\UNC\\") or (alvo.startswith("\\\\") and not alvo.startswith("\\\\?\\")):
        result["aviso_destino"] = ("destino em pasta de rede: serve para conferir; para usar a fundação, restaure em "
                                   "disco local (o SQLite em WAL não deve operar num compartilhamento de rede)")
    return result


def _versao_do_kit(raiz: Path) -> str | None:
    init = Path(raiz) / "fundacao" / "__init__.py"
    if not init.is_file():
        return None
    m = re.search(r'KIT_VERSION\s*=\s*"([^"]+)"', init.read_text(encoding="utf-8"))
    return m.group(1) if m else None
