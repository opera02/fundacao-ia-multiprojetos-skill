"""Revisões de política e de corpus por escopo.

Revogar uma permissão incrementa `policy_rev`; aprovar, atualizar ou retirar
uma fonte — ou uma memória: aprovar, corrigir, publicar ou retirar — incrementa
`corpus_rev`. Caches que guardam essas revisões na chave deixam de valer
imediatamente (invalidação ampla e explicável, livro A20). O alcance segue o
contexto: o caso conta no projeto dele, e o comum, que entra no contexto de todo
projeto, vale para ele e para cada projeto (auditorias A09, #21 e #23).
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


def escopos_alcancados(con: sqlite3.Connection, recurso: str) -> list[str]:
    """Escopos de revisão que uma mudança em `recurso` alcança: o próprio escopo; o do projeto, para
    um caso; o comum e todos os projetos, para o comum."""
    if recurso == "common":
        projetos = con.execute("SELECT project_id FROM project ORDER BY project_id").fetchall()
        return ["common"] + ["project:" + r[0] for r in projetos]
    if recurso.startswith("case:"):
        return ["project:" + recurso.split(":")[1]]
    return [recurso]


def incrementar_alcance(con: sqlite3.Connection, recurso: str, field: str) -> None:
    """`bump` em cada escopo de `escopos_alcancados(recurso)`, numa só transação (ou na que estiver aberta)."""
    with transaction(con):
        for escopo in escopos_alcancados(con, recurso):
            bump(con, escopo, field)
