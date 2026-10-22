"""Estado operacional em SQLite: conexão configurada, transações e migrações.

Decisões (livro A06/A09/A14 e proposta 3.0): foreign_keys ligado em cada
conexão, busy_timeout limitado, transações curtas com BEGIN IMMEDIATE e
migrações numeradas por `PRAGMA user_version`. Nunca abra o mesmo banco
simultaneamente pelo Windows e pelo WSL (/mnt/c).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

def _adicionar_colunas(con: sqlite3.Connection, tabela: str, colunas: dict[str, str]) -> None:
    """ALTER TABLE ADD COLUMN só para as colunas que faltam (o SQLite não tem IF NOT EXISTS)."""
    existentes = {r[1] for r in con.execute(f"PRAGMA table_info({tabela})")}
    for nome, tipo in colunas.items():
        if nome not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}")


MIGRATIONS: list = [
    # 1 — esquema inicial
    """
    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE principal (
      principal_id TEXT PRIMARY KEY, display_name TEXT, created_at TEXT NOT NULL);
    CREATE TABLE acl (
      subject TEXT NOT NULL, resource TEXT NOT NULL, action TEXT NOT NULL,
      granted_by TEXT NOT NULL, granted_at TEXT NOT NULL,
      PRIMARY KEY (subject, resource, action));
    CREATE TABLE project (
      project_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, purpose TEXT NOT NULL,
      template_version TEXT NOT NULL, schema_version TEXT NOT NULL,
      status TEXT NOT NULL CHECK (status IN ('creating','active','archived')),
      created_by TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE revision_counter (
      scope TEXT PRIMARY KEY, policy_rev INTEGER NOT NULL DEFAULT 1,
      corpus_rev INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE task (
      task_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES project(project_id),
      objective TEXT NOT NULL, state TEXT NOT NULL, idempotency_key TEXT UNIQUE,
      schema_version TEXT NOT NULL, created_by TEXT NOT NULL,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE run (
      run_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES task(task_id),
      project_id TEXT NOT NULL REFERENCES project(project_id),
      flow_id TEXT NOT NULL, flow_version TEXT NOT NULL, flow_json TEXT NOT NULL,
      state TEXT NOT NULL, budget_json TEXT NOT NULL, calls_used INTEGER NOT NULL DEFAULT 0,
      created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      UNIQUE (task_id, flow_id, flow_version));
    CREATE TABLE step (
      run_id TEXT NOT NULL REFERENCES run(run_id), step_id TEXT NOT NULL,
      state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
      executions INTEGER NOT NULL DEFAULT 0, input_hash TEXT, output_ref TEXT,
      output_hash TEXT, error TEXT, lease_until REAL, decision_json TEXT,
      updated_at TEXT NOT NULL, PRIMARY KEY (run_id, step_id));
    CREATE TABLE dispatch (
      dispatch_id INTEGER PRIMARY KEY AUTOINCREMENT, component_id TEXT NOT NULL,
      component_version TEXT, project_id TEXT, subject TEXT, outcome TEXT NOT NULL,
      ts TEXT NOT NULL);
    CREATE TABLE event (
      seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
      ts TEXT NOT NULL, schema_version TEXT NOT NULL, kind TEXT NOT NULL,
      project_id TEXT, subject TEXT, run_id TEXT, task_id TEXT,
      payload_json TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL,
      exported INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE op_key (
      op_id TEXT PRIMARY KEY, kind TEXT NOT NULL, result_ref TEXT NOT NULL,
      created_at TEXT NOT NULL);
    CREATE TABLE memory_item (
      memory_id TEXT PRIMARY KEY,
      scope TEXT NOT NULL CHECK (scope IN ('common','project','case')),
      project_id TEXT REFERENCES project(project_id), case_id TEXT,
      kind TEXT NOT NULL CHECK (kind IN ('fato','hipotese','decisao','preferencia','procedimento')),
      origin TEXT NOT NULL CHECK (origin IN ('humano','ia','documento')),
      status TEXT NOT NULL CHECK (status IN ('proposed','approved','rejected','withdrawn')),
      revision INTEGER NOT NULL CHECK (revision > 0), body TEXT NOT NULL,
      body_hash TEXT NOT NULL, source_ref TEXT NOT NULL, author_subject TEXT NOT NULL,
      approved_by TEXT, approved_hash TEXT, effective_from TEXT, recorded_at TEXT NOT NULL);
    CREATE TABLE memory_revision (
      memory_id TEXT NOT NULL REFERENCES memory_item(memory_id), revision INTEGER NOT NULL,
      body TEXT NOT NULL, body_hash TEXT NOT NULL, source_ref TEXT NOT NULL,
      reason TEXT NOT NULL,
      change_kind TEXT NOT NULL CHECK (change_kind IN ('criacao','correcao','mudanca_decisao')),
      editor_subject TEXT NOT NULL, recorded_at TEXT NOT NULL,
      state TEXT NOT NULL CHECK (state IN ('proposed','approved','rejected','superseded')),
      approved_by TEXT, approved_at TEXT,
      PRIMARY KEY (memory_id, revision));
    CREATE TABLE promotion (
      promotion_id TEXT PRIMARY KEY,
      source_memory_id TEXT NOT NULL REFERENCES memory_item(memory_id),
      candidate_body TEXT NOT NULL, candidate_hash TEXT NOT NULL, justification TEXT NOT NULL,
      requested_by TEXT NOT NULL, requested_at TEXT NOT NULL,
      decision TEXT NOT NULL CHECK (decision IN ('pending','approved','rejected')),
      decided_by TEXT, decided_at TEXT, published_memory_id TEXT);
    CREATE TABLE source_version (
      source_id TEXT NOT NULL, version INTEGER NOT NULL,
      project_id TEXT NOT NULL REFERENCES project(project_id), case_id TEXT,
      rel_path TEXT NOT NULL, original_hash TEXT NOT NULL, prepared_hash TEXT,
      prepared_json TEXT,
      status TEXT NOT NULL CHECK (status IN ('pending','approved','rejected','withdrawn','superseded')),
      is_current INTEGER NOT NULL DEFAULT 0, rubric_json TEXT, purpose TEXT,
      prepared_by TEXT, approved_by TEXT, approved_hash TEXT, review_due TEXT,
      registered_by TEXT NOT NULL, registered_at TEXT NOT NULL,
      PRIMARY KEY (source_id, version));
    CREATE TABLE chunk (
      chunk_rowid INTEGER PRIMARY KEY AUTOINCREMENT, chunk_id TEXT NOT NULL UNIQUE,
      source_id TEXT NOT NULL, version INTEGER NOT NULL, project_id TEXT NOT NULL,
      resource TEXT NOT NULL, page INTEGER NOT NULL, ordinal INTEGER NOT NULL,
      body TEXT NOT NULL, body_hash TEXT NOT NULL, recipe TEXT NOT NULL,
      FOREIGN KEY (source_id, version) REFERENCES source_version(source_id, version));
    CREATE TABLE dependency (
      parent_id TEXT NOT NULL, child_id TEXT NOT NULL,
      relation TEXT NOT NULL DEFAULT 'wasDerivedFrom', PRIMARY KEY (parent_id, child_id));
    CREATE TABLE tombstone (
      entity_id TEXT PRIMARY KEY, project_id TEXT, decided_by TEXT NOT NULL,
      reason TEXT NOT NULL, decided_at TEXT NOT NULL,
      cleanup_state TEXT NOT NULL CHECK (cleanup_state IN ('pending','done')));
    CREATE TABLE cache_entry (
      cache_key TEXT PRIMARY KEY, kind TEXT NOT NULL, project_id TEXT NOT NULL,
      subject TEXT NOT NULL, policy_rev INTEGER NOT NULL, corpus_rev INTEGER NOT NULL,
      value_json TEXT NOT NULL, sources_json TEXT NOT NULL, created_at TEXT NOT NULL,
      expires_at REAL);
    """,
    # 2 — chaves de idempotência e de operação passam a valer por projeto/escopo (sem colisão global)
    """
    UPDATE task SET idempotency_key = project_id || '::' || idempotency_key
      WHERE idempotency_key IS NOT NULL AND instr(idempotency_key, '::') = 0;
    UPDATE op_key SET op_id = (
        SELECT CASE m.scope WHEN 'common' THEN 'common'
                            WHEN 'case' THEN 'case:' || m.project_id || ':' || m.case_id
                            ELSE 'project:' || m.project_id END
        FROM memory_item m WHERE m.memory_id = op_key.result_ref) || '::' || op_id
      WHERE kind = 'memory.propose' AND instr(op_id, '::') = 0
        AND EXISTS (SELECT 1 FROM memory_item m WHERE m.memory_id = op_key.result_ref)
    """,
    # 3 — candidato à base comum vinculado à revisão e ao hash da origem (auditoria F06)
    lambda con: _adicionar_colunas(con, "promotion", {"source_revision": "INTEGER", "source_hash": "TEXT"}),
    # 4 — outbox do registro protegido (F11) e reservas de capacidade por rota (F10)
    """
    CREATE TABLE IF NOT EXISTS protected_outbox (
      outbox_id TEXT PRIMARY KEY, record_json TEXT NOT NULL, created_at TEXT NOT NULL,
      exported_at TEXT);
    CREATE TABLE IF NOT EXISTS route_reservation (
      reservation_id TEXT PRIMARY KEY, route TEXT NOT NULL, project_id TEXT, subject TEXT,
      state TEXT NOT NULL CHECK (state IN ('reserved','finalized','released')),
      created_at TEXT NOT NULL, finalized_at TEXT, attempt_event_id TEXT)
    """,
]


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def uri_somente_leitura(caminho: Path, *, imutavel: bool = False) -> str:
    """URI `file:` somente leitura para o SQLite. `as_uri()` codifica `#`, `%` e espaços (sem isso,
    `#` vira fragmento e o SQLite abriria outro arquivo). Caminho de rede (UNC) ou com o prefixo de
    caminho longo do Windows sai de `as_uri()` com autoridade (`file://servidor/...`), que o SQLite
    recusa; com `file:////` a autoridade fica vazia e o caminho é aceito (conferido em 18/10/2026
    com `localhost/C$` e com o prefixo de caminho longo). `imutavel=True` (só para cópias de
    backup, que não mudam): o SQLite lê só o arquivo do banco — o mesmo que a restauração copia —
    e não cria `-wal`/`-shm`, nem em cópia antiga em WAL."""
    uri = Path(caminho).resolve().as_uri()
    if not uri.startswith("file:///"):
        uri = "file:////" + uri[len("file://"):]
    return uri + ("?mode=ro&immutable=1" if imutavel else "?mode=ro")


def connect(path: Path, *, wal: bool = True) -> sqlite3.Connection:
    """Abre o banco com as PRAGMAs da fundação e aplica migrações pendentes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: etapas paralelas do coordenador debitam orçamento sob trava;
    # nenhuma outra operação compartilha a conexão entre threads.
    con = sqlite3.connect(str(path), isolation_level=None, timeout=5.0, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 5000")
    if wal:
        con.execute("PRAGMA journal_mode = WAL")
    if con.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise RuntimeError("foreign_keys não pôde ser habilitado nesta conexão")
    migrate(con)
    return con


def conectar_somente_leitura(path: Path) -> sqlite3.Connection:
    """Conexão só de leitura ao banco de uma raiz (não migra nem cria arquivo), com linhas por nome."""
    con = sqlite3.connect(uri_somente_leitura(Path(path)), uri=True, timeout=5.0)
    con.row_factory = sqlite3.Row
    return con


def conectar_copia(path: Path) -> sqlite3.Connection:
    """Conexão só de leitura ao banco de uma CÓPIA, que não muda (imutável: lê só o arquivo do banco, sem criar
    `-wal`/`-shm`), com linhas por nome. Abra só o arquivo já conferido pelo hash do manifesto ancorado."""
    con = sqlite3.connect(uri_somente_leitura(Path(path), imutavel=True), uri=True)
    con.row_factory = sqlite3.Row
    return con


def migrate(con: sqlite3.Connection) -> int:
    current = con.execute("PRAGMA user_version").fetchone()[0]
    for number, script in enumerate(MIGRATIONS, start=1):
        if number <= current:
            continue
        con.execute("BEGIN IMMEDIATE")
        try:
            if callable(script):  # migração em Python (ex.: idempotente por inspeção do esquema)
                script(con)
            else:
                for statement in [s.strip() for s in script.split(";") if s.strip()]:
                    con.execute(statement)
            con.execute(f"PRAGMA user_version = {number}")
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return con.execute("PRAGMA user_version").fetchone()[0]


@contextmanager
def transaction(con: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Transação de escrita curta. Se já houver uma aberta, participa dela."""
    if con.in_transaction:
        yield con
        return
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
    except BaseException:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")
