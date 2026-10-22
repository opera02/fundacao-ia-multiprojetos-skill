"""Contratos comuns: erros, estados e versões de formato.

`schema_version` identifica a estrutura de um registro; `version` identifica o
componente. As duas coisas evoluem separadamente (livro, A06).
"""

from __future__ import annotations

from typing import Any

# Versões de formato dos registros próprios da fundação (contratos didáticos).
SCHEMAS = {
    "project": "fundacao.project/1",
    "task": "fundacao.task/1",
    "component": "fundacao.component/1",
    "event": "fundacao.event/1",
    "memory": "fundacao.memory/1",
    "evidence": "fundacao.evidence/1",
    "usage": "fundacao.usage/1",
    "provider_result": "fundacao.provider_result/1",
}

# Estados honestos de requisito (Apêndice B). Não existe "concluído com ressalvas".
REQUIREMENT_STATES = (
    "em_desenvolvimento",
    "implementado_ativo",
    "implementado_inativo",
    "bloqueado",
)

# Níveis de evidência (A01): qualificam conclusões, não o fornecedor.
EVIDENCE_LEVELS = ("documentado", "codigo_presente", "executado", "validado")

# Estados de etapa/tarefa (A09, A31).
STEP_STATES = ("pending", "running", "waiting_human", "succeeded", "failed", "cancelled")

ALLOWED_STEP_TRANSITIONS = {
    "pending": {"running", "cancelled"},
    "running": {"succeeded", "failed", "waiting_human", "cancelled", "pending"},
    "waiting_human": {"pending", "succeeded", "cancelled"},
    "failed": {"pending", "cancelled"},
    "succeeded": {"pending"},  # somente por invalidação de entrada alterada
    "cancelled": set(),
}


class FundacaoError(Exception):
    """Erro base. A mensagem nunca deve conter conteúdo protegido."""

    code = "E_FUNDACAO"

    def __init__(self, message: str, **details: Any):
        super().__init__(message)
        self.details = details

    def as_dict(self) -> dict:
        return {"error": {"code": self.code, "message": str(self), **self.details}}


class AccessDenied(FundacaoError):
    code = "E_ACCESS_DENIED"


class ValidationError(FundacaoError):
    code = "E_VALIDATION"


class PathEscape(FundacaoError):
    code = "E_PATH_ESCAPE"


class AlreadyExists(FundacaoError):
    code = "E_EXISTS"


class NotFound(FundacaoError):
    code = "E_NOT_FOUND"


class ComponentDisabled(FundacaoError):
    code = "E_COMPONENT_DISABLED"


class DependencyUnavailable(FundacaoError):
    code = "E_DEPENDENCY_UNAVAILABLE"


class RevisionConflict(FundacaoError):
    code = "E_REVISION_CONFLICT"


class BudgetExhausted(FundacaoError):
    code = "E_BUDGET_EXHAUSTED"


class InvalidTransition(FundacaoError):
    code = "E_INVALID_TRANSITION"


class StaleArtifact(FundacaoError):
    code = "E_STALE"


class LimiteExcedido(FundacaoError):
    """Pedido, saída de processo ou arquivo acima do teto (auditoria Codex Security da 1.7.6, #9)."""

    code = "E_LIMITE_EXCEDIDO"


def check_transition(current: str, new: str) -> None:
    if new not in ALLOWED_STEP_TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"transição proibida: {current} -> {new}", current=current, new=new)


def require_fields(record: dict, fields: tuple[str, ...], where: str) -> None:
    missing = [f for f in fields if record.get(f) in (None, "")]
    if missing:
        raise ValidationError(f"{where}: campos obrigatórios ausentes: {', '.join(missing)}", missing=missing)
