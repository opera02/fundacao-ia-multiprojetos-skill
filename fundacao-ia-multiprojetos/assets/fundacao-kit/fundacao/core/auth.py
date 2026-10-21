"""Identidade e autorização aplicadas fora do modelo.

Regras (livro A03, A07, A13; OWASP): negar por padrão, conferir a cada pedido,
obter a identidade do contexto confiável (lançador/sessão), nunca de um campo
escrito pelo modelo. `project_id` é destino, não credencial.

Recursos: 'foundation' | 'common' | 'project:<id>' | 'case:<id>:<case>'.
Ações: admin, read, write, approve, curate, audit, use.

Limitação honesta: num computador de usuário único, o agente executor roda com
as mesmas permissões do sistema operacional que o usuário. Este módulo testa a
LÓGICA da política e protege todos os caminhos que passam pelo serviço; o
isolamento real exige também contas/permissões do SO, sandbox e bloqueios
preventivos (permissions.deny, hooks PreToolUse).
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass

from . import events, revisions
from .contracts import AccessDenied, ValidationError
from .db import transaction, utcnow
from .paths import validate_id

ENV_PRINCIPAL = "FUNDACAO_PRINCIPAL"
ACTIONS = {"admin", "read", "write", "approve", "curate", "audit", "use"}


@dataclass(frozen=True)
class Principal:
    principal_id: str
    source: str  # 'lancador-env' (real) | 'teste-simulado' (lógica da política)


def principal_from_env(con: sqlite3.Connection) -> Principal:
    value = os.environ.get(ENV_PRINCIPAL, "").strip()
    if not value:
        raise AccessDenied(f"identidade ausente: o lançador deve definir {ENV_PRINCIPAL}")
    if con.execute("SELECT 1 FROM principal WHERE principal_id = ?", (value,)).fetchone() is None:
        raise AccessDenied("identidade não registrada")
    return Principal(value, "lancador-env")


def resource_project(project_id: str) -> str:
    return f"project:{validate_id(project_id, 'project_id')}"


def resource_case(project_id: str, case_id: str) -> str:
    return f"case:{validate_id(project_id, 'project_id')}:{validate_id(case_id, 'case_id')}"


def scope_of(resource: str) -> str:
    """Escopo de revisão de um recurso (projeto do caso, ou o próprio recurso)."""
    if resource.startswith("case:"):
        return "project:" + resource.split(":")[1]
    return resource


class Policy:
    def __init__(self, con: sqlite3.Connection):
        self.con = con

    def _grant_exists(self, subject: str, resource: str, action: str) -> bool:
        return (
            self.con.execute(
                "SELECT 1 FROM acl WHERE subject = ? AND resource = ? AND action = ?",
                (subject, resource, action),
            ).fetchone()
            is not None
        )

    def allowed(self, subject: str, action: str, resource: str) -> bool:
        if action not in ACTIONS:
            return False
        if resource.startswith("case:"):
            # Caso exige concessão própria E acesso ao projeto (defesa em profundidade).
            project = "project:" + resource.split(":")[1]
            return self._grant_exists(subject, resource, action) and self._grant_exists(
                subject, project, "read"
            )
        return self._grant_exists(subject, resource, action)

    def require(self, principal: Principal, action: str, resource: str) -> None:
        """Nega e registra o evento. Chame ANTES de abrir a transação de escrita,
        para que o registro da negativa não seja desfeito junto com ela."""
        if not self.allowed(principal.principal_id, action, resource):
            events.emit(
                self.con,
                "access_denied",
                subject=principal.principal_id,
                payload={"action": action, "resource": resource, "source": principal.source},
            )
            raise AccessDenied("acesso negado", action=action, resource=resource)

    def recheck(self, principal: Principal, action: str, resource: str) -> None:
        """Reconfirmação dentro da transação (sem evento), contra corridas."""
        if not self.allowed(principal.principal_id, action, resource):
            raise AccessDenied("acesso negado", action=action, resource=resource)

    # --- administração -------------------------------------------------
    def register_principal(self, admin: Principal | None, principal_id: str, display: str = "") -> None:
        validate_id(principal_id, "principal_id")
        has_admin = self.con.execute(
            "SELECT 1 FROM acl WHERE resource = 'foundation' AND action = 'admin'"
        ).fetchone()
        if has_admin:
            if admin is None:
                raise AccessDenied("registro de identidade exige administrador")
            self.require(admin, "admin", "foundation")
        with transaction(self.con):
            if has_admin:
                self.recheck(admin, "admin", "foundation")
            self.con.execute(
                "INSERT INTO principal (principal_id, display_name, created_at) VALUES (?,?,?)"
                " ON CONFLICT(principal_id) DO NOTHING",
                (principal_id, display, utcnow()),
            )

    def bootstrap_admin(self, principal_id: str) -> Principal:
        """Cria o primeiro administrador. Só funciona enquanto não houver nenhum."""
        with transaction(self.con):
            if self.con.execute(
                "SELECT 1 FROM acl WHERE resource = 'foundation' AND action = 'admin'"
            ).fetchone():
                raise AccessDenied("já existe administrador; use uma identidade autorizada")
            self.register_principal(None, principal_id, "administrador inicial")
            self.con.execute(
                "INSERT INTO acl VALUES (?,?,?,?,?)",
                (principal_id, "foundation", "admin", "bootstrap", utcnow()),
            )
            events.emit(self.con, "admin_bootstrap", subject=principal_id)
        return Principal(principal_id, "lancador-env")

    def grant(self, admin: Principal, subject: str, resource: str, action: str) -> None:
        if action not in ACTIONS:
            raise ValidationError("ação desconhecida", action=action)
        self.require(admin, "admin", "foundation")
        with transaction(self.con):
            self.recheck(admin, "admin", "foundation")
            if self.con.execute(
                "SELECT 1 FROM principal WHERE principal_id = ?", (subject,)
            ).fetchone() is None:
                raise ValidationError("identidade não registrada", subject=subject)
            self.con.execute(
                "INSERT INTO acl VALUES (?,?,?,?,?) ON CONFLICT DO NOTHING",
                (subject, resource, action, admin.principal_id, utcnow()),
            )
            events.emit(
                self.con, "acl_grant", subject=admin.principal_id,
                payload={"to": subject, "resource": resource, "action": action},
            )

    def revoke(self, admin: Principal, subject: str, resource: str, action: str) -> None:
        self.require(admin, "admin", "foundation")
        from .backup import enqueue_protected, flush_outbox  # import tardio evita ciclo
        with transaction(self.con):
            self.recheck(admin, "admin", "foundation")
            apagadas = self.con.execute(
                "DELETE FROM acl WHERE subject = ? AND resource = ? AND action = ?",
                (subject, resource, action),
            ).rowcount
            # Caso conta no projeto; o comum entra no contexto de todo projeto, então revogar ali também
            # invalida os caches de cada projeto, não só os do comum (auditoria #21).
            revisions.incrementar_alcance(self.con, resource, "policy_rev")
            events.emit(
                self.con, "acl_revoke", subject=admin.principal_id,
                payload={"from": subject, "resource": resource, "action": action},
            )
            if apagadas:
                # A revogação vai para o registro protegido (fora do backup): restaurar uma cópia anterior
                # a reaplica antes de liberar; senão, quem perdeu o acesso o recuperaria. A intenção é
                # gravada NA MESMA transação da exclusão (outbox): falha no append ou queda depois do
                # commit não deixam a revogação fora do registro (auditoria F11).
                enqueue_protected(self.con, {
                    "entity_type": "acl_revoke", "entity_id": f"acl:{subject}:{action}:{resource}",
                    "principal": subject, "resource": resource, "action": action,
                    "decided_by": admin.principal_id, "decided_at": utcnow()})
        # Exporta esta e qualquer pendência anterior: repetir a revogação também reconcilia.
        flush_outbox(self.con)
