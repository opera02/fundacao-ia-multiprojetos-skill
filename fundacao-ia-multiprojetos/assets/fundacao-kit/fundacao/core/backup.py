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
- Ligação (link simbólico ou junção) não é seguida: nem na cópia, nem na verificação (#24).
- Âncora externa (#8) e quem verifica ou restaura (auditoria Codex Security da 1.7.6, #2): ancora_copia.py. Sem
  âncora, a restauração só libera por decisão explícita, com motivo — o código igual ao do kit não a dispensa.
- Preparo privado (auditoria da 1.7.6, #12): preparo.py. Backup e restauração copiam presos ao objeto listado; a
  restauração monta a raiz numa pasta de preparo ao lado do destino e só a promove depois de conferi-la de novo.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import stat
from pathlib import Path

from . import preparo, publicacao
from .ancora_copia import (  # noqa: F401 — âncora, manifesto e autorização (1.7.7), reexportados
    AVISO_SEM_ANCORA, FONTE_LIVRO, GUARDE_A_ANCORA, LIVRO_COPIAS, MARCA_NAO_LIBERADA, anotar_ancora, autorizar,
    aviso_da_ancora, conferir_ancora, dentro_da_copia, ler_manifesto, motivo_sem_ancora)
from .canon import canonical_json, sha256_file, sha256_text
from .contracts import FundacaoError, ValidationError
from .db import connect, transaction, uri_somente_leitura, utcnow
from .ids import new_id
from .registro_protegido import (  # noqa: F401 — leitura do registro protegido (1.7.4)
    REGISTRO, _analisar_registro, _id_de_componente_valido, _ilegivel, _ler_registro, _ler_texto)

EXCLUDE_PARTS = {"__pycache__", ".venv", "node_modules", ".git"}
EXCLUDE_NAMES = {".env", "state.sqlite", "state.sqlite-wal", "state.sqlite-shm"}
FILE_DIRS = ("fundacao", "registry", "templates", "projects", "AGENTS.md", "CLAUDE.md")  # + instruções da raiz
# Registros da fundação fora do kit: entram na cópia por padrão, para o backup não precisar de um
# "complemento" (auditoria da implantação real de 2026-10-19/20: dez complementos num só dia). A raiz troca a
# lista em registry/backup_policy.json ({"incluir": [...]}); `state/` (banco e registros) tem tratamento próprio.
REGISTROS_PADRAO = ("docs", "evidence", "ferramentas", "tests", "RETOMADA.md")
POLITICA_BACKUP = "backup_policy.json"
SCHEMA_REGISTRO = "fundacao.retiradas/1"
# Arquivos que o sistema operacional cria sozinho numa pasta (Explorer em pasta de rede, Finder):
# não contam como "extras" na verificação e não são restaurados.
METADADOS_DO_SO = ("Thumbs.db", "ehthumbs.db", "desktop.ini", ".DS_Store")
# O que a restauração NÃO reaplica (vai na resposta, para conferência da administração).
NAO_REAPLICADO = [
    "concessões de acesso posteriores à cópia (reconceder é decisão da administração)",
    "habilitação de componente posterior à cópia (o componente volta desligado)",
    "alterações em arquivos posteriores à cópia, como registry/route_policy.json: confira à mão",
]


def registros_incluidos(root: Path) -> list[str]:
    """Caminhos da raiz, além do kit e do banco, que entram na cópia: a lista `incluir` de
    registry/backup_policy.json ou REGISTROS_PADRAO. Caminho vazio, absoluto, com `..`, em `state/` ou `.git`
    recusa o backup antes de copiar (ValidationError)."""
    arq = Path(root) / "registry" / POLITICA_BACKUP
    if not arq.is_file():
        return list(REGISTROS_PADRAO)
    try:
        incluir = json.loads(arq.read_text(encoding="utf-8")).get("incluir")
    except (OSError, ValueError, AttributeError) as exc:
        raise ValidationError(f"política de backup ilegível (registry/{POLITICA_BACKUP})",
                              erro=type(exc).__name__) from exc
    if not isinstance(incluir, list) or not all(isinstance(x, str) and x.strip() for x in incluir):
        raise ValidationError(f"política de backup inválida: `incluir` precisa ser lista de caminhos relativos "
                              f"(registry/{POLITICA_BACKUP})")
    for rel in incluir:
        p = Path(rel)
        if p.is_absolute() or p.drive or p.root or ".." in p.parts or p.parts[0] in ("state", ".git"):
            raise ValidationError("política de backup inválida: só caminhos relativos dentro da raiz, fora de "
                                  f"state/ e .git (registry/{POLITICA_BACKUP})", caminho=rel)
    return incluir


def _files(root: Path, ligacoes: list[str] | None = None, extras: tuple[str, ...] | list[str] = ()):
    """Arquivos que entram na cópia, com o `lstat` da listagem (a identidade que a cópia confere, #12): os do kit
    (FILE_DIRS) e os registros da fundação (`extras`, pastas ou arquivos). Ligação (pasta ou arquivo) não é seguida
    (#24): fica fora, anotada em `ligacoes`."""
    ligacoes = [] if ligacoes is None else ligacoes
    vistos: set[Path] = set()
    for top in (*FILE_DIRS, *extras):
        base = Path(root) / top
        try:
            st = os.lstat(base)
        except OSError:
            continue
        if preparo.e_ligacao(base):
            ligacoes.append(Path(top).as_posix())
            continue
        itens = preparo.percorrer(base, EXCLUDE_PARTS) if stat.S_ISDIR(st.st_mode) else [(base, False, st)]
        for path, ligacao, st in itens:
            if not _copiavel(path.name) or path in vistos:
                continue
            vistos.add(path)
            if ligacao:
                ligacoes.append(path.relative_to(root).as_posix())
            elif stat.S_ISREG(st.st_mode):
                yield path, st


def _copiavel(nome: str) -> bool:
    return nome not in EXCLUDE_NAMES | EXCLUDE_PARTS and not nome.endswith(".pyc")


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
def default_tombstone_log(con: sqlite3.Connection) -> Path | None:
    """Registro protegido padrão: `<raiz>/state/retiradas.jsonl`, ao lado do banco."""
    for row in con.execute("PRAGMA database_list"):
        if row[1] == "main" and row[2]:
            return Path(row[2]).parent / "retiradas.jsonl"
    return None


def ensure_tombstone_log(log_path: Path) -> str:
    """Garante o registro protegido com identidade própria (o `init` chama). Registro de kit
    anterior, sem identidade, recebe-a numa linha nova ao final: nada é reescrito. As linhas vão por
    `publicacao.anexar`: ligação ou vínculo físico no lugar do registro recusa sem gravar (R177-KIT-04)."""
    path = Path(log_path)
    log_id, _ = _ler_registro(path)
    if log_id:
        return log_id
    log_id = new_id("reg")
    path.parent.mkdir(parents=True, exist_ok=True)
    publicacao.anexar(path, (canonical_json({"entity_type": REGISTRO, "log_id": log_id, "criado_em": utcnow(),
                                             "schema_version": SCHEMA_REGISTRO}) + "\n").encode("utf-8"))
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
    publicacao.anexar(log_path, (canonical_json(record) + "\n").encode("utf-8"))  # com fsync; sem seguir ligação


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
        if isinstance(cid, str) and _id_de_componente_valido(cid):
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
    root, dest = Path(os.path.abspath(root)), Path(os.path.abspath(dest))
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError("destino de backup não vazio: não substitua uma referência anterior")
    ligada = preparo.ligacao_no_caminho(dest) or preparo.ligacao_no_caminho(root / "state" / "state.sqlite")
    if ligada:  # #12: a cópia iria para outro lugar, ou o estado viria de outro lugar
        raise ValidationError("o caminho da raiz ou do destino da cópia passa por ligação (link simbólico ou junção): "
                              "informe o caminho real", caminho=ligada)
    extras = registros_incluidos(root)
    destino_real = dest.resolve()
    for top in (*FILE_DIRS, *extras):  # cópia dentro do que ela copia se copiaria a si mesma
        alvo = (root / top).resolve()
        if destino_real == alvo or destino_real.is_relative_to(alvo):
            raise ValidationError("o destino da cópia fica dentro de uma pasta que ela copia: use um destino fora "
                                  "dela (de preferência em outro disco)", pasta=Path(top).as_posix())
    src_db = root / "state" / "state.sqlite"
    if src_db.exists():
        # Decisão protegida que ainda não chegou ao registro (falha ou queda depois do commit) é
        # exportada antes; se não der, não há cópia: ela nasceria com lacuna (auditoria F11).
        con = connect(src_db)
        try:
            try:
                flush_outbox(con, root / "state" / "retiradas.jsonl")
            except (OSError, FundacaoError) as exc:  # inclui registro que é ligação ou vínculo físico (R177-KIT-04)
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
    # #12: a cópia é montada numa pasta de preparo exclusiva ao lado do destino e promovida inteira (renomeação
    # atômica): nada é gravado no destino nem através de ligação nele, e cópia pela metade não aparece.
    pasta = preparo.criar_preparo(dest)
    try:
        manifest = _montar_copia(root, pasta, label, extras, retiradas)
        # Âncora (#8): o hash do manifesto, que confere cada arquivo e o banco, sai da pasta da cópia.
        ancora = sha256_file(pasta / "manifest.json")
        substituido = preparo.promover(pasta, dest)  # destino vazio criado antes: trocado (R177-KIT-05)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    resultado = {**manifest, "sha256_manifesto": ancora, "guarde_a_ancora": GUARDE_A_ANCORA}
    avisos = [preparo.AVISO_DESTINO_EXISTENTE] if substituido else []
    if manifest.get("ligacoes_nao_seguidas"):
        avisos.append("ligações (link simbólico ou junção) não foram seguidas e o que elas apontam NÃO está na "
                      "cópia: veja ligacoes_nao_seguidas")
    try:
        anotar_ancora(root / "state" / LIVRO_COPIAS, {"rotulo": label, "criado_em": manifest["created_at"],
                                                      "destino": str(dest.resolve()), "sha256_manifesto": ancora})
    except (OSError, FundacaoError) as exc:  # livro que é ligação ou vínculo físico: recusado sem gravar (R177-KIT-04)
        avisos.append(f"a âncora não foi anotada no livro de cópias ({type(exc).__name__}: {exc}): guarde o "
                      "sha256_manifesto; a restauração vai pedi-lo")
    if avisos:
        resultado["aviso"] = "; ".join(avisos)
    return resultado


def _montar_copia(root: Path, pasta: Path, label: str, extras: list[str], retiradas: dict) -> dict:
    """Banco, arquivos e manifest.json da cópia, gravados na pasta de preparo (#12); devolve o manifesto."""
    src_db = root / "state" / "state.sqlite"
    files = []
    if src_db.exists():
        (pasta / "state").mkdir()
        src = sqlite3.connect(str(src_db))
        dst = sqlite3.connect(str(pasta / "state" / "state.sqlite"))
        try:
            src.backup(dst)  # cópia consistente mesmo com o banco em uso
            dst.execute("PRAGMA journal_mode = DELETE")  # cópia fora do WAL: conferir não cria -wal/-shm
        finally:
            dst.close()
            src.close()
    ligacoes: list[str] = []
    criadas = {pasta}
    for path, st in _files(root, ligacoes, extras):
        rel = path.relative_to(root)
        target = pasta / "files" / rel
        preparo.criar_pasta(target.parent, criadas)
        try:  # presa ao objeto listado: trocado por ligação depois da listagem, fica fora como ligação (#12)
            sha, tamanho = preparo.copiar(path, target, st)
        except ValidationError:
            ligacoes.append(rel.as_posix())
            continue
        # Tamanho e hash do que foi COPIADO: a origem não é lida de novo depois da cópia.
        files.append({"path": rel.as_posix(), "size": tamanho, "sha256": sha})
    manifest = {
        "schema_version": "fundacao.backup/1",
        "label": label,
        "created_at": utcnow(),
        "db": logical_summary(pasta / "state" / "state.sqlite", copia=True) if src_db.exists() else None,
        "db_sha256": sha256_file(pasta / "state" / "state.sqlite") if src_db.exists() else None,
        "files": files,
        # Identidade do registro e linhas conhecidas no momento da cópia: na restauração, o registro
        # informado precisa ter a mesma identidade e alcançar pelo menos este ponto.
        "retiradas": retiradas,
        "excluded": sorted(EXCLUDE_NAMES | EXCLUDE_PARTS),
        "credentials": "não incluídas; restabelecer pelo mecanismo próprio de cada provedor",
        "registros_incluidos": extras,
    }
    if ligacoes:
        manifest["ligacoes_nao_seguidas"] = sorted(ligacoes)
    (pasta / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def verify_backup(backup_dir: Path, *, sha256_manifesto: str | None = None, livro: Path | None = None) -> dict:
    """Confere a cópia contra o manifesto: hash de cada arquivo; no banco, o SHA-256 do arquivo
    (cópias da 1.3.1 em diante), a integridade e o resumo lógico (contagem por tabela e
    `user_version`). Banco trocado, tabela esvaziada ou banco ausente = não confere; ligação dentro
    da cópia também (#24), e nada é lido através dela: `files/` é listada antes, sem seguir ligação, e só o arquivo
    comum listado tem o hash calculado, preso ao objeto da listagem (R177-KIT-03). O manifesto fica na mesma pasta:
    quem reescreve os dois forja a cópia — por isso ele é conferido contra a âncora guardada fora dela (#8):
    `sha256_manifesto` informado (divergente = não confere) ou o livro de cópias, fora da cópia (R177-KIT-01); sem
    âncora ou com a do livro, a resposta avisa (`aviso_ancora`). O
    manifesto é lido uma vez (a âncora confere os bytes que valem) e caminho dele que sairia de `files/` é
    estrutura inválida (#12). A restauração verifica a cópia já trazida para o preparo, não no lugar."""
    backup_dir = Path(backup_dir)
    bruto = preparo.ler(backup_dir / "manifest.json")
    manifest = ler_manifesto(bruto)
    ancora = conferir_ancora(bruto, sha256_manifesto, livro, backup_dir)
    base, comuns, ligacoes = backup_dir / "files", {}, []  # comuns: caminho relativo -> (caminho, lstat da listagem)
    if preparo.e_ligacao(base):
        ligacoes.append(".")  # a própria pasta files/
    elif base.is_dir():
        for p, ligacao, st in preparo.percorrer(base):
            rel = p.relative_to(base).as_posix()
            if ligacao:  # a cópia nunca tem ligação: restaurá-la copiaria o que está do outro lado
                ligacoes.append(rel)
            elif stat.S_ISREG(st.st_mode):
                comuns[rel] = (p, st)
    missing = [f["path"] for f in manifest["files"] if f["path"] not in comuns]  # ausente, ligação ou pasta
    changed = [f["path"] for f in manifest["files"]
               if f["path"] in comuns and preparo.resumo(*comuns[f["path"]]) != f["sha256"]]
    # Arquivo na cópia que o manifesto não lista também não confere: seria restaurado (até código
    # em fundacao/) sem que ninguém o tivesse copiado.
    listados = {f["path"] for f in manifest["files"]}
    soltos = sorted(rel for rel in comuns if rel not in listados)
    do_so = [rel for rel in soltos if rel.rsplit("/", 1)[-1] in METADADOS_DO_SO]
    extras = [rel for rel in soltos if rel not in do_so]
    db = backup_dir / "state" / "state.sqlite"
    esperado = manifest.get("db")
    db_check, db_problemas = None, []
    if preparo.e_ligacao(db.parent) or preparo.e_ligacao(db):
        db_problemas.append("o banco da cópia passa por ligação (link simbólico ou junção)")
    elif db.exists():
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
    resultado = {"ok": (not changed and not missing and not extras and not db_problemas and not ligacoes
                        and ancora["situacao"] != "divergente"),
                 "changed": changed, "missing": missing, "extras": extras, "db": db_check,
                 "db_problemas": db_problemas, "ancora": ancora}
    if ligacoes:
        resultado["ligacoes"] = sorted(ligacoes)
    resultado.update(aviso_da_ancora(ancora))
    if do_so:
        resultado["ignorados_do_so"] = do_so  # metadados do sistema: nem conferidos nem restaurados
    if db.exists() and not manifest.get("db_sha256"):
        resultado["aviso"] = ("cópia anterior à 1.3.1: o banco é conferido só por integridade e contagens "
                              "(o manifesto não tem db_sha256); uma troca com as mesmas contagens passaria — "
                              "faça um backup novo")
    return resultado


# ------------------------------------------------------------------ restauração
def restore(backup_dir: Path, target_root: Path, tombstone_log: Path | None, *,
            aceitar_registro_nao_comprovado: bool = False, executado_por: str = "restauracao",
            sha256_manifesto: str | None = None, aceitar_copia_sem_ancora: str | None = None,
            livro: Path | None = None) -> dict:
    """Restaura em destino NOVO, reaplica o que o registro guarda e só então libera.

    Não libera (released=false), e não copia nada para o destino, quando: o caminho da cópia ou do destino
    passa por ligação; a cópia não confere; o registro não foi informado, não existe, é ilegível, tem
    identidade diferente da anotada na cópia (outra fundação ou registro recriado) ou não alcança as linhas
    conhecidas no momento da cópia. Cópia sem identidade anotada (kit anterior à 1.3.0) e sem retiradas só
    libera com aceitação explícita, que fica na resposta e na trilha. Reaplica por tipo: fonte (`id@versão`,
    com limpeza dos derivados), memória (com os derivados registrados), revogação de acesso e desativação de
    componente (só as posteriores à cópia). Cada reaplicação vira evento na trilha restaurada.

    Ponto de corte coerente (auditoria F12): o registro é relido depois da reaplicação e, se
    cresceu (escritores ativos na origem), as linhas novas também são reaplicadas, até ficar
    estável; registro reescrito (não só acrescido) ou que não para de mudar impede a liberação. O
    registro do destino recebe exatamente o conteúdo reaplicado — nunca uma cópia posterior do
    arquivo vivo —, então banco e registro do destino refletem o mesmo corte (`corte_do_registro`
    na resposta). Decisões protegidas confirmadas no banco copiado e ainda não exportadas (outbox)
    entram no registro do destino antes de liberar.

    Âncora externa (#8; auditoria Codex Security da 1.7.6, #2): o manifest.json é lido uma vez e conferido contra
    `sha256_manifesto` (informado) ou contra o livro de cópias ao lado do registro (`livro`; padrão: `copias.jsonl`
    na pasta do registro). Âncora divergente não libera. Sem âncora, não libera — nem com o código igual ao do kit
    — salvo `aceitar_copia_sem_ancora` com o motivo, decisão que fica na resposta e na trilha (`ressalva_ancora`).
    Registro ou livro dentro da própria cópia não valem, e a âncora vinda do livro sai com `aviso_ancora` (R177-KIT-01).

    Preparo privado (auditoria da 1.7.6, #12): a cópia vem para uma pasta de preparo criada ao lado do destino, com
    exclusividade, cada arquivo lido sem seguir ligação e conferido como o objeto listado; a verificação, o banco e
    a reaplicação usam só o preparo, que carrega `state/restauracao-nao-liberada.json` até o fim. Logo antes da
    promoção — renomeação atômica para o destino, que nunca grava através de ligação —, a raiz preparada é
    conferida de novo. O destino só recebe a raiz liberada; o preparo não liberado é apagado. Destino vazio criado
    antes é trocado pela raiz preparada, sem as permissões próprias dele: `aviso_permissoes` (R177-KIT-05)."""
    backup_dir, target_root = Path(os.path.abspath(backup_dir)), Path(os.path.abspath(target_root))
    if target_root.exists() and any(target_root.iterdir()):
        raise FileExistsError("restaure em diretório novo ou vazio; nunca sobre a origem")
    if livro is None and tombstone_log is not None:
        livro = Path(tombstone_log).parent / LIVRO_COPIAS
    check: dict = {}

    def nao_liberar(reason: str, **extra) -> dict:
        return {"released": False, "reason": reason, "check": check, **extra}

    ligada = preparo.ligacao_no_caminho(backup_dir) or preparo.ligacao_no_caminho(target_root)
    if ligada:  # #12: a leitura ou a escrita iria para outro lugar
        return nao_liberar(f"o caminho da cópia ou do destino passa por ligação (link simbólico ou junção) em {ligada}:"
                           " informe o caminho real; não liberar")
    bruto = preparo.ler(backup_dir / "manifest.json")  # lido UMA vez: a âncora e o que vale são estes bytes
    manifest = ler_manifesto(bruto)
    ancora = check["ancora"] = conferir_ancora(bruto, sha256_manifesto, livro, backup_dir)
    if ancora.get("livro_recusado"):
        livro = None  # dentro da própria cópia: não confere nada nem vai para a raiz restaurada (R177-KIT-01)
    if ancora["situacao"] == "divergente":
        return nao_liberar("o manifesto da cópia não confere com o sha256_manifesto informado: não é a cópia que "
                           "foi guardada, ou ela foi alterada; não liberar")
    if tombstone_log is None:
        return nao_liberar("registro de retiradas indisponível: não liberar")
    if dentro_da_copia(tombstone_log, backup_dir):  # a cópia não comprova a si mesma (R177-KIT-01)
        return nao_liberar(f"o registro de retiradas informado ({tombstone_log}) fica dentro da própria cópia: não "
                           "vale; informe o registro protegido da fundação, guardado fora da cópia; não liberar")
    if not Path(tombstone_log).is_file():
        return nao_liberar("registro de retiradas inexistente no caminho informado: não liberar")
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
    ressalva_ancora = None
    if ancora["situacao"] != "conferida":
        motivos = [motivo_sem_ancora(ancora)]
        codigo_diferente = _codigo_diferente_do_kit(manifest)
        if codigo_diferente:
            motivos.append("o código da cópia (fundacao/), que a raiz restaurada vai executar, difere do kit que "
                           "está restaurando")
        motivo = aceitar_copia_sem_ancora.strip() if isinstance(aceitar_copia_sem_ancora, str) else ""
        if not motivo:  # #2: sem âncora, só a decisão explícita e motivada; o código igual ao do kit não a dispensa
            return nao_liberar("cópia sem âncora externa: " + " e ".join(motivos) + ". Informe --sha256-manifesto "
                               "com o código devolvido pelo `backup criar`; sem ele, confira de onde veio a cópia e "
                               "use --aceitar-copia-sem-ancora \"<motivo>\" (a decisão fica na trilha); não liberar",
                               codigo_diferente=codigo_diferente)
        ressalva_ancora = f"cópia sem âncora externa ({'; '.join(motivos)}); aceita por decisão explícita: {motivo}"
    fim = {"ancora": ancora["situacao"], **({"ressalva": ressalva} if ressalva else {}),
           **({"ressalva_ancora": ressalva_ancora} if ressalva_ancora else {})}
    pasta = preparo.criar_preparo(target_root)
    try:
        try:  # a cópia inteira vem para o preparo, presa ao objeto listado: depois disso, nada é lido da origem
            achados = preparo.trazer_copia(backup_dir, pasta / "copia", pular=METADADOS_DO_SO)
        except ValidationError as exc:
            return nao_liberar(f"a cópia mudou durante a leitura ({exc}): não liberar; restaure de novo")
        check = verify_backup(pasta / "copia", sha256_manifesto=sha256_manifesto, livro=livro)
        if achados["ligacoes"]:
            check["ok"], check["ligacoes"] = False, sorted({*check.get("ligacoes", []), *achados["ligacoes"]})
        if achados["pulados"]:
            check["ignorados_do_so"] = achados["pulados"]  # metadados do sistema: nem conferidos nem restaurados
        if check["ancora"]["sha256_manifesto"] != ancora["sha256_manifesto"]:
            return nao_liberar("o manifesto da cópia mudou durante a restauração: não liberar; restaure de novo")
        check["ancora"] = ancora  # os mesmos bytes: vale a conferência da leitura inicial (com o motivo, se houver)
        if not check["ok"]:
            return nao_liberar("backup íntegro? não")
        raiz = pasta / "raiz"
        os.rename(pasta / "copia" / "files", raiz)
        os.mkdir(raiz / "state")
        os.rename(pasta / "copia" / "state" / "state.sqlite", raiz / "state" / "state.sqlite")
        (raiz / "state" / MARCA_NAO_LIBERADA).write_text(json.dumps(
            {"copia": manifest.get("label"), "inicio": utcnow(),
             "situacao": "restauração em andamento ou não liberada: não use esta raiz"}, ensure_ascii=False),
            encoding="utf-8")
        feito = _reaplicar(raiz, manifest, Path(tombstone_log), texto, linhas, log_id,
                           int(conhecido.get("linhas") or 0), executado_por, livro, fim)
        if "recusa" in feito:
            return nao_liberar(feito["recusa"], reapplied=feito["reapplied"])
        if feito["summary"]["integrity_check"] != "ok":
            return nao_liberar("o banco restaurado não passou na conferência de integridade: não liberar",
                               reapplied=feito["reapplied"], db=feito["summary"])
        esperado = {**{f["path"]: None if f["path"] in feito["alterados"] else f["sha256"] for f in manifest["files"]},
                    **{f"state/{nome}": sha for nome, sha in feito["estado"].items()}}
        try:  # imediatamente antes da promoção: a raiz preparada é a que foi conferida e reaplicada (#12)
            divergentes = preparo.reconferir(raiz, esperado)
        except ValidationError as exc:
            divergentes = [str(exc)]
        if divergentes:
            return nao_liberar("a raiz preparada mudou antes da promoção (" + ", ".join(divergentes[:5]) + "): não "
                               "liberar; restaure de novo", reapplied=feito["reapplied"])
        try:
            substituido = preparo.promover(raiz, target_root)
        except (OSError, ValidationError) as exc:
            return nao_liberar(f"o destino mudou durante a restauração ({exc}): não liberar",
                               reapplied=feito["reapplied"])
        (target_root / "state" / MARCA_NAO_LIBERADA).unlink()  # liberada: o destino é a raiz conferida
    finally:
        shutil.rmtree(pasta, ignore_errors=True)  # o que sobrou do preparo; raiz não liberada não fica
    result = {"released": True, "reapplied": feito["reapplied"], "registro": log_id,
              "nao_reaplicado": NAO_REAPLICADO, "corte_do_registro": feito["corte"], "db": feito["summary"],
              "ancora": ancora, "check": check, **aviso_da_ancora(ancora),
              **({"aviso_permissoes": preparo.AVISO_DESTINO_EXISTENTE} if substituido else {})}  # R177-KIT-05
    if ressalva:
        result["ressalva"] = ressalva
    if ressalva_ancora:
        result["ressalva_ancora"] = ressalva_ancora
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


def _reaplicar(raiz: Path, manifest: dict, tombstone_log: Path, texto: str, linhas: list, log_id: str | None,
               posicao: int, executado_por: str, livro: Path | None, fim: dict) -> dict:
    """Reaplica o registro protegido na raiz PREPARADA (#12: nada fora do preparo) e fecha a restauração com o evento
    `restore_completed` (`fim`: âncora e ressalvas). `posicao`: linhas já refletidas no banco copiado. Recusa no
    meio: {"recusa", "reapplied"}; senão, o que foi reaplicado, o corte, o resumo do banco, os arquivos reescritos e
    o SHA-256 de cada arquivo de `state/` (conferidos de novo antes da promoção)."""
    con = connect(raiz / "state" / "state.sqlite")
    reapplied: list[str] = []
    alterados: set[str] = set()  # reescritos pela reaplicação: fora da conferência pelo manifesto
    destino_log = raiz / "state" / "retiradas.jsonl"
    try:
        from . import events, revisions  # import tardio evita ciclo
        from .auth import Principal, resource_project
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
                        # O mesmo alcance do serviço: revogar no comum muda o comum e todos os projetos (#21).
                        revisions.incrementar_alcance(con, rec["resource"], "policy_rev")
                        evento(rec, tipo)
                if apagadas:
                    reapplied.append(entity)
                return
            if tipo == "component_disable":
                if idx < posicao:
                    return  # anterior à cópia: o arquivo copiado já está desligado
                from .components import entry_path  # contido em registry/components/ (avaliação E11, F-03)
                comp = entry_path(raiz, rec["component_id"])
                if comp.is_file():
                    entrada = json.loads(comp.read_text(encoding="utf-8"))
                    if entrada.get("enabled"):
                        entrada["enabled"] = False
                        tmp = comp.with_suffix(".tmp")
                        tmp.write_text(json.dumps(entrada, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                        tmp.replace(comp)
                        alterados.add(f"registry/components/{rec['component_id']}.json")
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
                # Retirada do comum (sem projeto) muda o corpus do comum e de todos os projetos (#21, #23).
                revisions.incrementar_alcance(
                    con, resource_project(rec["project_id"]) if rec.get("project_id") else "common", "corpus_rev")
                evento(rec, tipo)
            KnowledgeService(raiz, con, system).cleanup(entity)
            reapplied.append(entity)

        for idx, (_, rec) in enumerate(linhas):
            reaplicar(idx, rec)
        # Escritores ativos na origem: o que entrou no registro durante a restauração também entra.
        for _rodada in range(5):
            atual = _ler_texto(Path(tombstone_log)) or ""
            if atual == texto:
                break
            if not atual.startswith(texto):
                return {"recusa": "registro de retiradas reescrito durante a restauração (não só acrescido): não "
                                  "liberar; confira o registro e restaure de novo", "reapplied": reapplied}
            try:
                _, todas = _analisar_registro(atual, estrito=True)
            except ValidationError as exc:
                return {"recusa": f"registro de retiradas ilegível depois da cópia (linha {exc.details.get('linha')}):"
                                  " não liberar", "reapplied": reapplied}
            for idx in range(len(linhas), len(todas)):
                reaplicar(idx, todas[idx][1])
            texto, linhas = atual, todas
        else:
            return {"recusa": "registro de retiradas continua mudando durante a restauração: pare os escritores da "
                              "origem e restaure de novo", "reapplied": reapplied}
        # O destino segue com o registro NO MESMO CORTE do banco: o conteúdo reaplicado, não o arquivo vivo.
        destino_log.write_bytes(texto.encode("utf-8"))
        if livro is not None and Path(livro).is_file():
            shutil.copy2(livro, raiz / "state" / LIVRO_COPIAS)  # a raiz restaurada conhece as âncoras
        try:
            pendentes = flush_outbox(con, destino_log)  # decisões do banco copiado ainda não exportadas
        except (OSError, ValidationError) as exc:
            return {"recusa": f"decisões da cópia não puderam ir ao registro do destino ({type(exc).__name__}): "
                              "não liberar", "reapplied": reapplied}
        corte = {"linhas": len(linhas), "ultima_sha256": sha256_text(linhas[-1][0]) if linhas else None}
        events.emit(con, "restore_completed", subject=system.principal_id,
                    payload={"copia": manifest.get("label"), "registro": log_id, "reaplicadas": len(reapplied),
                             "corte_do_registro": corte, "outbox_da_copia": pendentes["exportadas"], **fim})
        summary = logical_summary(raiz / "state" / "state.sqlite")
    finally:
        con.close()
    return {"reapplied": reapplied, "alterados": alterados, "corte": corte, "summary": summary,
            "estado": {p.name: sha256_file(p) for p in (raiz / "state").iterdir()}}


def _codigo_diferente_do_kit(manifest: dict) -> list[str]:
    """Arquivos de `fundacao/` em que a cópia difere do kit que está restaurando (#8). A raiz restaurada
    executa o código da cópia; sem âncora, nada prova que ele é o código que foi copiado (e nem o código
    igual dispensa a decisão explícita: a cópia pode ter banco e permissões forjados — #2)."""
    kit = Path(__file__).resolve().parents[1]
    proprio = {f"fundacao/{p.relative_to(kit).as_posix()}": sha256_file(p)
               for p, ligacao, st in preparo.percorrer(kit, EXCLUDE_PARTS)
               if not ligacao and stat.S_ISREG(st.st_mode) and _copiavel(p.name)}
    da_copia = {f["path"]: f["sha256"] for f in manifest["files"] if f["path"].startswith("fundacao/")}
    return sorted(p for p in proprio.keys() | da_copia.keys() if proprio.get(p) != da_copia.get(p))


def _versao_do_kit(raiz: Path) -> str | None:
    init = Path(raiz) / "fundacao" / "__init__.py"
    if not init.is_file():
        return None
    m = re.search(r'KIT_VERSION\s*=\s*"([^"]+)"', init.read_text(encoding="utf-8"))
    return m.group(1) if m else None
