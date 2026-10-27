"""Leitura autorizada de fontes e verificação de citações sem recuperar texto antes da permissão."""
from . import events
from .auth import resource_case, resource_project
from .contracts import NotFound


def fonte_autorizada(con, policy, principal, source_id, version):
    """Confere metadados e permissão antes de recuperar a linha com texto preparado.

    A consulta final exige o mesmo projeto/caso observado: uma mudança de escopo
    entre as consultas não entrega conteúdo sob uma autorização do escopo anterior.
    Isso não constitui uma transação universal entre leitores e revogações concorrentes.
    """
    meta = con.execute(
        "SELECT project_id, case_id FROM source_version WHERE source_id = ? AND version = ?",
        (source_id, version),
    ).fetchone()
    if meta is None:
        raise NotFound("fonte não encontrada")
    project_id, case_id = meta["project_id"], meta["case_id"]
    resource = resource_case(project_id, case_id) if case_id else resource_project(project_id)
    if not policy.allowed(principal.principal_id, "read", resource):
        events.emit(con, "access_denied", subject=principal.principal_id,
                    payload={"action": "read", "resource": resource, "source": principal.source})
        raise NotFound("fonte não encontrada")
    row = con.execute(
        "SELECT * FROM source_version WHERE source_id = ? AND version = ?"
        " AND project_id = ? AND case_id IS ?", (source_id, version, project_id, case_id),
    ).fetchone()
    if row is None:
        raise NotFound("fonte não encontrada")
    return row


def verificar_citacao(con, policy, principal, source, chunk_id):
    """Confere vínculo, autorização e vigência antes de buscar o corpo do trecho."""
    row = con.execute(
        "SELECT c.source_id, c.version, c.resource, c.page FROM chunk c"
        " JOIN source_version s ON s.source_id = c.source_id AND s.version = c.version"
        " WHERE c.chunk_id = ? AND c.project_id = s.project_id"
        " AND c.resource = CASE WHEN s.case_id IS NULL OR s.case_id = '' THEN 'project:' || s.project_id"
        " ELSE 'case:' || s.project_id || ':' || s.case_id END", (chunk_id,),
    ).fetchone()
    if row is not None and not policy.allowed(principal.principal_id, "read", row["resource"]):
        events.emit(con, "access_denied", subject=principal.principal_id,
                    payload={"action": "read", "resource": row["resource"], "source": principal.source})
        row = None  # trecho alheio responde igual a inexistente
    if row is None:
        return {"chunk_id": chunk_id, "valid": False, "reason": "trecho inexistente ou sem acesso"}
    src = source(row["source_id"], row["version"])
    if src["status"] != "approved" or not src["is_current"]:
        return {"chunk_id": chunk_id, "valid": False, "reason": f"fonte {src['status']}"}
    if not src["approved_hash"] or src["prepared_hash"] != src["approved_hash"]:
        return {"chunk_id": chunk_id, "valid": False, "reason": "aprovação de outro texto preparado"}
    if con.execute("SELECT 1 FROM tombstone WHERE entity_id IN (?, ?)",
                   (chunk_id, f"{row['source_id']}@{row['version']}")).fetchone():
        return {"chunk_id": chunk_id, "valid": False, "reason": "retirada"}
    body = con.execute(
        "SELECT body FROM chunk WHERE chunk_id = ? AND source_id = ? AND version = ? AND resource = ?",
        (chunk_id, row["source_id"], row["version"], row["resource"]),
    ).fetchone()
    if body is None:
        return {"chunk_id": chunk_id, "valid": False, "reason": "trecho inexistente ou sem acesso"}
    return {"chunk_id": chunk_id, "valid": True,
            "citation": f"{row['source_id']}@{row['version']}, p. {row['page']}", "body": body["body"]}
