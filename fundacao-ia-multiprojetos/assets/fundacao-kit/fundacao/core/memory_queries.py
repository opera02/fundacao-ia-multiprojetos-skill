"""Leitura de memória e lições; autorização antes de entregar qualquer conteúdo."""

from __future__ import annotations

from . import licoes
from .auth import resource_project
from .db import transaction, utcnow


def consultar(servico, *, project_id=None, case_id=None, include_common=True, text=None) -> list[dict]:
    """Somente revisões vigentes aprovadas que a identidade pode ler."""
    out = []
    for row in servico.con.execute(
        "SELECT * FROM memory_item WHERE status = 'approved' ORDER BY recorded_at"
    ).fetchall():
        if row["scope"] == "common":
            if not include_common:
                continue
        elif row["project_id"] != project_id:
            continue
        if row["scope"] == "case" and row["case_id"] != case_id:
            continue
        resource = servico._resource(row["scope"], row["project_id"], row["case_id"])
        if not servico.policy.allowed(servico.principal.principal_id, "read", resource):
            continue  # filtrado antes de qualquer entrega
        if servico.con.execute("SELECT 1 FROM tombstone WHERE entity_id = ?", (row["memory_id"],)).fetchone():
            continue
        if not licoes.vigente(row):
            continue
        if text and text.lower() not in row["body"].lower():
            continue
        out.append({
            "memory_id": row["memory_id"], "revision": row["revision"], "scope": row["scope"],
            "kind": row["kind"], "origin": row["origin"], "body": row["body"],
            "source_ref": row["source_ref"], "approved_by": row["approved_by"],
        })
    return out


def consultar_licoes(servico, *, project_id: str, gatilho: str) -> list[dict]:
    """FTS5 literal no gatilho, com ACL antes de ler índice ou conteúdo.

    Só a revisão aprovada vigente volta. O resultado é hipótese a reconferir
    na tarefa, nunca aprovação de proposta pendente.
    """
    resource = resource_project(project_id)
    servico.policy.require(servico.principal, "read", resource)
    expressao = licoes.expressao_fts(gatilho)
    if expressao is None:
        return []
    agora, out = licoes.instante(utcnow()), []
    # A reconferência e a leitura observam a mesma ACL nesta transação curta.
    with transaction(servico.con):
        servico.policy.recheck(servico.principal, "read", resource)
        rows = servico.con.execute(
            "SELECT m.*, r.state AS revision_state FROM lesson_trigger f"
            " JOIN memory_item m ON m.memory_id=f.memory_id AND m.revision=f.revision"
            " JOIN memory_revision r ON r.memory_id=m.memory_id AND r.revision=m.revision"
            " WHERE lesson_trigger MATCH ? AND f.project_id=? AND m.project_id=?"
            " AND m.scope='project' AND m.case_id IS NULL AND m.kind='licao'"
            " AND m.status='approved' AND r.state='approved' AND m.approved_hash=m.body_hash"
            " AND r.body_hash=m.body_hash AND r.body=m.body"
            " AND NOT EXISTS (SELECT 1 FROM tombstone t WHERE t.entity_id=m.memory_id"
            " OR t.entity_id=m.memory_id || '@' || m.revision)"
            " ORDER BY m.recorded_at,m.memory_id", (expressao, project_id, project_id)).fetchall()
        for row in rows:
            if not licoes.vigente(row, agora):
                continue
            dados = licoes.validar(row["body"], row["source_ref"])
            out.append({"memory_id": row["memory_id"], "revision": row["revision"],
                        "scope": row["scope"], "project_id": project_id, "kind": "licao",
                        "origin": row["origin"], "source_ref": row["source_ref"],
                        "approved_by": row["approved_by"], **dados})
    return out
