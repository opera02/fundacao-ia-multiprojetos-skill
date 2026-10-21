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
- Âncora externa (#8): o manifesto fica na pasta da cópia, e quem pode reescrevê-la recalcula
  tudo. O `backup criar` devolve o SHA-256 do manifest.json e o anota no livro de cópias
  (`state/copias.jsonl`, ao lado do registro protegido e fora da cópia); a restauração confere
  a cópia por ele. Sem âncora, cópia que não consta no livro ou cujo código difere do kit que
  restaura só libera por decisão explícita; sem livro e com o mesmo código, libera com aviso.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import stat
from pathlib import Path

from .canon import canonical_json, sha256_file, sha256_text
from .contracts import ValidationError
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
MARCA_NAO_LIBERADA = "restauracao-nao-liberada.json"
LIVRO_COPIAS = "copias.jsonl"  # âncoras das cópias (sha256 do manifest.json), ao lado do registro protegido
# Windows: etiqueta de ponto de nova análise "substituta de nome" (bit 29) — junção, link simbólico e
# afins, que redirecionam para outro caminho; arquivo de nuvem (OneDrive) e deduplicação não a têm.
_SUBSTITUTA_DE_NOME = 0x20000000
GUARDE_A_ANCORA = ("guarde o sha256_manifesto FORA da pasta da cópia (anotação, gerenciador de senhas, outro disco); "
                   "ele também foi anotado em state/copias.jsonl — guarde esse livro junto do registro protegido "
                   "(state/retiradas.jsonl). A restauração confere a cópia por ele.")
AVISO_SEM_ANCORA = ("ATENÇÃO: nada fora da pasta da cópia confirma que ela é a que foi guardada; quem pode escrever "
                    "nessa pasta pode trocar arquivos, banco e permissões e recalcular o manifesto. Confira com o "
                    "sha256_manifesto devolvido pelo `backup criar` (--sha256-manifesto) ou com o livro de cópias "
                    "(state/copias.jsonl) ao lado do registro protegido.")
# Arquivos que o sistema operacional cria sozinho numa pasta (Explorer em pasta de rede, Finder):
# não contam como "extras" na verificação e não são restaurados.
METADADOS_DO_SO = ("Thumbs.db", "ehthumbs.db", "desktop.ini", ".DS_Store")
# O que a restauração NÃO reaplica (vai na resposta, para conferência da administração).
NAO_REAPLICADO = [
    "concessões de acesso posteriores à cópia (reconceder é decisão da administração)",
    "habilitação de componente posterior à cópia (o componente volta desligado)",
    "alterações em arquivos posteriores à cópia, como registry/route_policy.json: confira à mão",
]


def _e_ligacao(path: Path) -> bool:
    """Link simbólico ou junção (e afins do Windows), conferido sem seguir a ligação."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & _SUBSTITUTA_DE_NOME)


def _percorrer(base: Path, ignorar: set[str]) -> list[tuple[Path, bool]]:
    """Caminhos sob `base`, ordenados, sem atravessar ligação: a ligação vem marcada (True) e o que
    há do outro lado não é listado nem lido. `os.walk` sozinho entraria na junção do Windows."""
    itens = []
    for pasta, subpastas, nomes in os.walk(base):
        atual = Path(pasta)
        for nome in sorted(subpastas):
            if nome in ignorar or _e_ligacao(atual / nome):
                subpastas.remove(nome)
                if nome not in ignorar:
                    itens.append((atual / nome, True))
        itens.extend((atual / nome, _e_ligacao(atual / nome)) for nome in nomes)
    return sorted(itens)


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
    """Arquivos que entram na cópia: os do kit (FILE_DIRS) e os registros da fundação (`extras`, pastas ou
    arquivos). Ligação (pasta ou arquivo) não é seguida (#24): fica fora, anotada em `ligacoes`; arquivo cujo
    caminho resolvido sai da raiz (troca no meio), também."""
    ligacoes = [] if ligacoes is None else ligacoes
    raiz = Path(root).resolve()
    vistos: set[Path] = set()
    for top in (*FILE_DIRS, *extras):
        base = Path(root) / top
        if _e_ligacao(base):
            ligacoes.append(Path(top).as_posix())
            continue
        if base.is_file():
            itens = [(base, False)] if _copiavel(base.name) else []
        elif base.is_dir():
            itens = _percorrer(base, EXCLUDE_PARTS)
        else:
            continue
        for path, ligacao in itens:
            if not _copiavel(path.name) or path in vistos:
                continue
            vistos.add(path)
            if ligacao or (path.is_file() and not path.resolve().is_relative_to(raiz)):
                ligacoes.append(path.relative_to(root).as_posix())
            elif path.is_file():
                yield path


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
    root, dest = Path(root), Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError("destino de backup não vazio: não substitua uma referência anterior")
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
    ligacoes: list[str] = []
    for path in _files(root, ligacoes, extras):
        rel = path.relative_to(root)
        target = dest / "files" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        # Tamanho e hash do que foi COPIADO: a origem não é lida de novo depois da cópia.
        files.append({"path": rel.as_posix(), "size": target.stat().st_size, "sha256": sha256_file(target)})
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
        "registros_incluidos": extras,
    }
    if ligacoes:
        manifest["ligacoes_nao_seguidas"] = sorted(ligacoes)
    (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    # Âncora (#8): o hash do manifesto, que confere cada arquivo e o banco, sai da pasta da cópia.
    ancora = sha256_file(dest / "manifest.json")
    resultado = {**manifest, "sha256_manifesto": ancora, "guarde_a_ancora": GUARDE_A_ANCORA}
    avisos = []
    if ligacoes:
        avisos.append("ligações (link simbólico ou junção) não foram seguidas e o que elas apontam NÃO está na "
                      "cópia: veja ligacoes_nao_seguidas")
    try:
        _anotar_ancora(root / "state" / LIVRO_COPIAS, {"rotulo": label, "criado_em": manifest["created_at"],
                                                       "destino": str(dest.resolve()), "sha256_manifesto": ancora})
    except OSError as exc:
        avisos.append(f"a âncora não foi anotada no livro de cópias ({type(exc).__name__}): guarde o "
                      "sha256_manifesto; a restauração vai pedi-lo")
    if avisos:
        resultado["aviso"] = "; ".join(avisos)
    return resultado


def _anotar_ancora(livro: Path, registro: dict) -> None:
    livro.parent.mkdir(parents=True, exist_ok=True)
    with livro.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(canonical_json(registro) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _ancoras_do_livro(livro: Path) -> set[str]:
    """Âncoras anotadas no livro de cópias; linha ilegível não confere nada (só deixa de achar)."""
    try:
        linhas = livro.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return set()
    ancoras = set()
    for linha in linhas:
        try:
            rec = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and isinstance(rec.get("sha256_manifesto"), str):
            ancoras.add(rec["sha256_manifesto"])
    return ancoras


def conferir_ancora(backup_dir: Path, sha256_manifesto: str | None = None, livro: Path | None = None) -> dict:
    """Confere o manifest.json da cópia contra a âncora guardada FORA dela (#8): a informada pelo
    operador ou a anotada no livro de cópias. `situacao`: conferida, divergente (a informada não
    bate) ou ausente (com `livro_sem_esta_copia` quando o livro existe e não a tem)."""
    atual = sha256_file(Path(backup_dir) / "manifest.json")
    if sha256_manifesto:
        situacao = "conferida" if sha256_manifesto.strip().lower() == atual else "divergente"
        return {"situacao": situacao, "fonte": "sha256 informado", "sha256_manifesto": atual}
    if livro is not None and Path(livro).is_file():
        if atual in _ancoras_do_livro(Path(livro)):
            return {"situacao": "conferida", "fonte": str(livro), "sha256_manifesto": atual}
        return {"situacao": "ausente", "fonte": None, "livro_sem_esta_copia": str(livro), "sha256_manifesto": atual}
    return {"situacao": "ausente", "fonte": None, "sha256_manifesto": atual}


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


def verify_backup(backup_dir: Path, *, sha256_manifesto: str | None = None, livro: Path | None = None) -> dict:
    """Confere a cópia contra o manifesto: hash de cada arquivo; no banco, o SHA-256 do arquivo
    (cópias da 1.3.1 em diante), a integridade e o resumo lógico (contagem por tabela e
    `user_version`). Banco trocado, tabela esvaziada ou banco ausente = não confere; ligação dentro
    da cópia também (#24). O manifesto fica na mesma pasta: quem reescreve os dois forja a cópia — por
    isso o manifesto é conferido contra a âncora guardada fora dela (#8): `sha256_manifesto` informado
    (divergente = não confere) ou o livro de cópias; sem âncora, a resposta avisa (`aviso_ancora`)."""
    backup_dir = Path(backup_dir)
    manifest = _ler_manifesto(backup_dir)
    ancora = conferir_ancora(backup_dir, sha256_manifesto, livro)
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
    soltos, ligacoes = [], []
    if base.is_dir():
        for p, ligacao in _percorrer(base, set()):
            rel = p.relative_to(base).as_posix()
            if ligacao:  # a cópia nunca tem ligação: restaurá-la copiaria o que está do outro lado
                ligacoes.append(rel)
            elif p.is_file() and rel not in listados:
                soltos.append(rel)
    soltos.sort()
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
    resultado = {"ok": (not changed and not missing and not extras and not db_problemas and not ligacoes
                        and ancora["situacao"] != "divergente"),
                 "changed": changed, "missing": missing, "extras": extras, "db": db_check,
                 "db_problemas": db_problemas, "ancora": ancora}
    if ligacoes:
        resultado["ligacoes"] = sorted(ligacoes)
    if ancora["situacao"] == "ausente":
        resultado["aviso_ancora"] = AVISO_SEM_ANCORA
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
            sha256_manifesto: str | None = None, aceitar_copia_sem_ancora: bool = False,
            livro: Path | None = None) -> dict:
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
    entram no registro do destino antes de liberar.

    Âncora externa (#8): o manifest.json é conferido contra `sha256_manifesto` (informado) ou contra o
    livro de cópias ao lado do registro (`livro`; padrão: `copias.jsonl` na pasta do registro).
    Âncora divergente não libera. Sem âncora, não libera — salvo `aceitar_copia_sem_ancora`, que fica
    na resposta e na trilha — quando o livro existe e não tem esta cópia ou quando o código da cópia
    (`fundacao/`, que a raiz restaurada vai executar) difere do kit que restaura; sem livro e com o
    mesmo código, libera com `aviso_ancora`."""
    backup_dir, target_root = Path(backup_dir), Path(target_root)
    if target_root.exists() and any(target_root.iterdir()):
        raise FileExistsError("restaure em diretório novo ou vazio; nunca sobre a origem")
    if livro is None and tombstone_log is not None:
        livro = Path(tombstone_log).parent / LIVRO_COPIAS
    check = verify_backup(backup_dir, sha256_manifesto=sha256_manifesto, livro=livro)

    def nao_liberar(reason: str, **extra) -> dict:
        return {"released": False, "reason": reason, "check": check, **extra}

    if check["ancora"]["situacao"] == "divergente":
        return nao_liberar("o manifesto da cópia não confere com o sha256_manifesto informado: não é a cópia que "
                           "foi guardada, ou ela foi alterada; não liberar")
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
    ressalva_ancora = None
    if check["ancora"]["situacao"] != "conferida":
        motivos = []
        if check["ancora"].get("livro_sem_esta_copia"):
            motivos.append(f"ela não consta no livro de cópias ao lado do registro ({LIVRO_COPIAS})")
        codigo_diferente = _codigo_diferente_do_kit(manifest)
        if codigo_diferente:
            motivos.append("o código da cópia (fundacao/), que a raiz restaurada vai executar, difere do kit que "
                           "está restaurando")
        if motivos and not aceitar_copia_sem_ancora:
            return nao_liberar("cópia sem âncora externa: " + " e ".join(motivos) + ". Informe --sha256-manifesto "
                               "com o código devolvido pelo `backup criar`; sem ele, confira de onde veio a cópia e "
                               "use --aceitar-copia-sem-ancora (a decisão fica na trilha); não liberar",
                               codigo_diferente=codigo_diferente)
        if motivos:
            ressalva_ancora = "cópia sem âncora externa (" + "; ".join(motivos) + "); aceita por decisão explícita"
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
                comp = entry_path(target_root, rec["component_id"])
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
                # Retirada do comum (sem projeto) muda o corpus do comum e de todos os projetos (#21, #23).
                revisions.incrementar_alcance(
                    con, resource_project(rec["project_id"]) if rec.get("project_id") else "common", "corpus_rev")
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
        if livro is not None and Path(livro).is_file() and not (target_root / "state" / LIVRO_COPIAS).exists():
            shutil.copy2(livro, target_root / "state" / LIVRO_COPIAS)  # a raiz restaurada conhece as âncoras
        try:
            pendentes = flush_outbox(con, destino_log)  # decisões do banco copiado ainda não exportadas
        except (OSError, ValidationError) as exc:
            return nao_liberar(f"decisões da cópia não puderam ir ao registro do destino ({type(exc).__name__}): "
                               "não liberar", reapplied=reapplied)
        corte = {"linhas": len(linhas), "ultima_sha256": sha256_text(linhas[-1][0]) if linhas else None}
        events.emit(con, "restore_completed", subject=system.principal_id,
                    payload={"copia": manifest.get("label"), "registro": log_id, "reaplicadas": len(reapplied),
                             "corte_do_registro": corte, "outbox_da_copia": pendentes["exportadas"],
                             "ancora": check["ancora"]["situacao"],
                             **({"ressalva": ressalva} if ressalva else {}),
                             **({"ressalva_ancora": ressalva_ancora} if ressalva_ancora else {})})
        summary = logical_summary(target_root / "state" / "state.sqlite")
    finally:
        con.close()
    released = summary["integrity_check"] == "ok"
    if released:
        marca.unlink()
    result = {"released": released, "reapplied": reapplied, "registro": log_id, "nao_reaplicado": NAO_REAPLICADO,
              "corte_do_registro": corte, "db": summary, "ancora": check["ancora"], "check": check}
    if ressalva:
        result["ressalva"] = ressalva
    if check["ancora"]["situacao"] != "conferida":
        result["aviso_ancora"] = AVISO_SEM_ANCORA
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


def _codigo_diferente_do_kit(manifest: dict) -> list[str]:
    """Arquivos de `fundacao/` em que a cópia difere do kit que está restaurando (#8). A raiz restaurada
    executa o código da cópia; sem âncora, nada prova que ele é o código que foi copiado."""
    kit = Path(__file__).resolve().parents[1]
    proprio = {f"fundacao/{p.relative_to(kit).as_posix()}": sha256_file(p)
               for p, ligacao in _percorrer(kit, EXCLUDE_PARTS)
               if not ligacao and p.is_file() and _copiavel(p.name)}
    da_copia = {f["path"]: f["sha256"] for f in manifest["files"] if f["path"].startswith("fundacao/")}
    return sorted(p for p in proprio.keys() | da_copia.keys() if proprio.get(p) != da_copia.get(p))


def _versao_do_kit(raiz: Path) -> str | None:
    init = Path(raiz) / "fundacao" / "__init__.py"
    if not init.is_file():
        return None
    m = re.search(r'KIT_VERSION\s*=\s*"([^"]+)"', init.read_text(encoding="utf-8"))
    return m.group(1) if m else None
