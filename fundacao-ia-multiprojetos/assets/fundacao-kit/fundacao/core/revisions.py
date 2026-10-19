"""Revisões de política e de corpus por escopo.

Revogar uma permissão incrementa `policy_rev`; aprovar, atualizar ou retirar
uma fonte incrementa `corpus_rev`. Caches que guardam essas revisões na chave
deixam de valer imediatamente (invalidação ampla e explicável, livro A20).
"""

from __future__ import annotations

import sqlite3

from .db import transaction


def get(con: sqlite3.Connection, scope: str) -> tuple[int, int]:
    row = con.execute(
        "SELECT policy_rev, corpus_rev FROM revision_counter WHERE scope = ?", (scope,)
    ).fetchone()
    if row is None:
        return 1, 1
    return row["policy_rev"], row["corpus_rev"]


def bump(con: sqlite3.Connection, scope: str, field: str) -> int:
    if field not in ("policy_rev", "corpus_rev"):
        raise ValueError("campo de revisão inválido")
    with transaction(con):
        con.execute(
            "INSERT INTO revision_counter (scope) VALUES (?) ON CONFLICT(scope) DO NOTHING",
            (scope,),
        )
        con.execute(f"UPDATE revision_counter SET {field} = {field} + 1 WHERE scope = ?", (scope,))
        return con.execute(
            f"SELECT {field} FROM revision_counter WHERE scope = ?", (scope,)
        ).fetchone()[0]
