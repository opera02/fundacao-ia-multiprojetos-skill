"""Eventos auditáveis com cadeia de hashes (outbox na mesma transação).

O SQLite é a fonte da verdade; cada evento é gravado na mesma transação da
mudança de estado e encadeado por `prev_hash`. A exportação JSONL é derivada.
Os eventos guardam identificadores e resultados, nunca conteúdo protegido.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .canon import canonical_json, sha256_json
from .contracts import SCHEMAS
from .db import transaction, utcnow
from .ids import new_id
from .publicacao import anexar

GENESIS = "0" * 64


def emit(
    con: sqlite3.Connection,
    kind: str,
    *,
    project_id: str | None = None,
    subject: str | None = None,
    run_id: str | None = None,
    task_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    payload = payload or {}
    with transaction(con):
        row = con.execute("SELECT hash FROM event ORDER BY seq DESC LIMIT 1").fetchone()
        prev_hash = row["hash"] if row else GENESIS
        event = {
            "event_id": new_id("evt"),
            "ts": utcnow(),
            "schema_version": SCHEMAS["event"],
            "kind": kind,
            "project_id": project_id,
            "subject": subject,
            "run_id": run_id,
            "task_id": task_id,
            "payload": payload,
            "prev_hash": prev_hash,
        }
        digest = sha256_json(event)
        con.execute(
            "INSERT INTO event (event_id, ts, schema_version, kind, project_id, subject, run_id,"
            " task_id, payload_json, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                event["event_id"], event["ts"], event["schema_version"], kind, project_id,
                subject, run_id, task_id, canonical_json(payload), prev_hash, digest,
            ),
        )
    return event["event_id"]


def verify_chain(con: sqlite3.Connection) -> tuple[bool, int | None]:
    """Recalcula a cadeia. Retorna (íntegra, seq do primeiro evento quebrado)."""
    prev = GENESIS
    for row in con.execute("SELECT * FROM event ORDER BY seq"):
        event = {
            "event_id": row["event_id"],
            "ts": row["ts"],
            "schema_version": row["schema_version"],
            "kind": row["kind"],
            "project_id": row["project_id"],
            "subject": row["subject"],
            "run_id": row["run_id"],
            "task_id": row["task_id"],
            "payload": json.loads(row["payload_json"]),
            "prev_hash": row["prev_hash"],
        }
        if row["prev_hash"] != prev or sha256_json(event) != row["hash"]:
            return False, row["seq"]
        prev = row["hash"]
    return True, None


def export_jsonl(con: sqlite3.Connection, path: Path) -> int:
    """Exporta eventos ainda não exportados (idempotente). As linhas vão juntas por `publicacao.anexar`: destino que
    é ligação ou vínculo físico recusa sem gravar e sem marcar nada como exportado (revisão de segurança da 1.7.7,
    R177-KIT-04: com `open("a")`, os eventos iam para o arquivo de fora)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = con.execute("SELECT * FROM event WHERE exported = 0 ORDER BY seq").fetchall()
    if not rows:
        return 0
    linhas = []
    for row in rows:
        record = {k: row[k] for k in row.keys() if k not in ("payload_json", "exported")}
        record["payload"] = json.loads(row["payload_json"])
        linhas.append(canonical_json(record) + "\n")
    anexar(path, "".join(linhas).encode("utf-8"))
    with transaction(con):
        con.execute("UPDATE event SET exported = 1 WHERE seq <= ?", (rows[-1]["seq"],))
    return len(rows)


_FILTERABLE = {"project_id", "subject", "run_id", "task_id"}


def count(con: sqlite3.Connection, kind: str, **filters: Any) -> int:
    sql = "SELECT COUNT(*) FROM event WHERE kind = ?"
    params: list[Any] = [kind]
    for key, value in filters.items():
        if key not in _FILTERABLE:
            raise ValueError(f"filtro não permitido: {key}")
        sql += f" AND {key} = ?"
        params.append(value)
    return con.execute(sql, params).fetchone()[0]
