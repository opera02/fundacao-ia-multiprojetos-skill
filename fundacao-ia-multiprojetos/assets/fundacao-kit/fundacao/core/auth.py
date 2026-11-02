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

Trava de projeto e identidade `sessao-<p>` (1.7.10; contratos do lote 2, §4; crítica do desenho, "sessao-<p> sem
admin"): com FUNDACAO_PROJETO_TRAVADO=<p> — o kit rodado pelo porteiro da sessão do projeto no Ubuntu —, a política
tem um teto que nenhuma linha de ACL derruba: só `project:<p>` (e os casos dele), sem admin, audit, approve nem
curate, sem `foundation` e, do comum, só a leitura. A identidade `sessao-<p>` recebe exatamente read, write e use em
`project:<p>`, DERIVADAS da trava (sem linha de ACL no banco e sem mudar o esquema: user_version continua 5); sem a
trava, ou com a trava de outro projeto, tudo lhe é negado, mesmo com linha de ACL. O assinante das decisões vem da
configuração do porteiro (FUNDACAO_ASSINANTE: o titular; emenda E1), nunca da identidade da sessão. Honestidade (§0 dos
contratos): com a raiz em /mnt/e, onde o sandbox não confinou os comandos nas sondas de 31/10/2026, a trava é camada
lógica — quem roda o kit fora do porteiro escolhe as variáveis — até o canário passar no ambiente real.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path, PurePath

from . import events, revisions
from .contracts import AccessDenied, ValidationError
from .db import transaction, utcnow
from .paths import contained, exact_child, validate_id

ENV_PRINCIPAL = "FUNDACAO_PRINCIPAL"
ENV_TRAVA = "FUNDACAO_PROJETO_TRAVADO"
ENV_RAIZ = "FUNDACAO_RAIZ"
ENV_ASSINANTE = "FUNDACAO_ASSINANTE"  # posto pelo porteiro, de porteiro.json (o titular que assina: emenda E1)
ACTIONS = {"admin", "read", "write", "approve", "curate", "audit", "use"}
PREFIXO_SESSAO = "sessao-"
ACOES_DA_SESSAO = frozenset({"read", "write", "use"})
FORA_DA_TRAVA = frozenset({"admin", "audit", "approve", "curate"})
# O que a sessão do projeto pede ao kit pelo porteiro (o mesmo mapa de assets/host/wsl/porteiro.py; há teste): comando
# e ações permitidas (None: sem ação). Nunca init, projeto, acl, componente, backup, copia-assinatura, rota nem banco;
# na 1.7.10, nem `eventos` nem `memoria licao historico` (emenda E2 dos contratos: leitura que pode mostrar o que não é
# do projeto; voltam na 1.7.11 só com leitura restrita ao projeto).
COMANDOS_DA_TRAVA = {"status": None, "tarefa": {"criar", "ver", "concluir"},
                     "decisao": {"preparar", "verificar", "registrar", "comando", "conferir-ancora"},
                     "abertura": {"preparar", "verificar", "vigente"}, "conhecimento": {"listar", "buscar"},
                     "memoria": {"propor", "consultar", "pendente"}}


def trava() -> tuple[bool, str | None]:
    """(ligada, projeto) da trava de projeto. Ligada com valor fora da forma de identificador: (True, None), e tudo
    é negado — a trava nunca se desliga por um valor errado."""
    valor = os.environ.get(ENV_TRAVA, "")
    if not valor:
        return False, None
    try:
        return True, validate_id(valor, "projeto travado")
    except ValidationError:
        return True, None


def projeto_travado() -> str | None:
    """O projeto da trava válida (o `status` o mostra para o aperto de mão do porteiro), ou None."""
    return trava()[1]


def sessao_de(projeto: str) -> str:
    return PREFIXO_SESSAO + projeto


def dentro_da_trava(projeto: str | None, action: str, resource: str) -> bool:
    """Teto da trava, para qualquer identidade: só o projeto travado e os casos dele, sem administração, auditoria,
    aprovação nem curadoria; do comum, só a leitura."""
    if projeto is None or action in FORA_DA_TRAVA:
        return False
    if resource == "common":
        return action == "read"
    return resource == f"project:{projeto}" or resource.startswith(f"case:{projeto}:")


@dataclass(frozen=True)
class Principal:
    principal_id: str
    # 'lancador-env' (real) | 'teste-simulado' (lógica da política) | 'trava-de-projeto' (sessao-<p>, 1.7.10) |
    # 'assinante-da-configuracao' (o titular que assina a decisão preparada pela sessão travada)
    source: str


def principal_from_env(con: sqlite3.Connection) -> Principal:
    value = os.environ.get(ENV_PRINCIPAL, "").strip()
    if not value:
        raise AccessDenied(f"identidade ausente: o lançador deve definir {ENV_PRINCIPAL}")
    if value.startswith(PREFIXO_SESSAO):
        # Identidade de sessão: vale só com a trava do próprio projeto, sem linha no banco (as concessões vêm da trava).
        ligada, projeto = trava()
        if not (ligada and projeto is not None and value == sessao_de(projeto)):
            raise AccessDenied(f"identidade de sessão sem a trava do seu projeto ({ENV_TRAVA}): tudo negado")
        return Principal(value, "trava-de-projeto")
    if con.execute("SELECT 1 FROM principal WHERE principal_id = ?", (value,)).fetchone() is None:
        raise AccessDenied("identidade não registrada")
    return Principal(value, "lancador-env")


def assinante_da_decisao(con: sqlite3.Connection, principal: Principal) -> Principal:
    """Quem assina a decisão preparada pela sessão travada: o titular da configuração do porteiro
    (FUNDACAO_ASSINANTE), registrado na fundação. A preparação passa a ser autorizada para ele, dentro do teto da
    trava (escrita só em `project:<p>`, pelas concessões dele no banco). Fora da sessão travada, ou sem a configuração,
    é a própria identidade (o preparo avisa quando ela não está na âncora). Limite: `decisoes.preparar_decisao` usa a
    mesma identidade para autorizar, assinar e registrar o evento `decisao_preparada`, que fica com o titular."""
    ligada, projeto = trava()
    nome = os.environ.get(ENV_ASSINANTE, "").strip()
    if not (ligada and projeto is not None and principal.principal_id == sessao_de(projeto) and nome):
        return principal
    if nome.startswith(PREFIXO_SESSAO) or con.execute(
            "SELECT 1 FROM principal WHERE principal_id = ?", (nome,)).fetchone() is None:
        raise AccessDenied("o assinante da configuração do porteiro (FUNDACAO_ASSINANTE) não é uma identidade "
                           "registrada da fundação: refaça o preparo do projeto")
    return Principal(nome, "assinante-da-configuracao")


def raiz_da_execucao(args) -> Path:
    """A raiz em que o comando roda. Sem a trava: a pedida em --raiz (padrão: a pasta atual), resolvida, como antes.
    Com a trava (o kit rodado pelo porteiro), recusa — AccessDenied ou PathEscape, pelo contrato da CLI — o que a
    sessão não pode pedir: outra raiz que não a do lançador (FUNDACAO_RAIZ), comando ou ação fora de
    COMANDOS_DA_TRAVA, qualquer --ancora (vale só a âncora padrão desta máquina) e caminho de argumento fora de
    projects/<p>/ (relativo vale a partir da pasta atual, como no resto da CLI)."""
    raiz = Path(args.raiz).resolve()
    ligada, projeto = trava()
    if not ligada:
        return raiz
    if projeto is None:
        raise AccessDenied(f"trava de projeto inválida ({ENV_TRAVA}): tudo negado")
    do_lancador = os.environ.get(ENV_RAIZ, "").strip()
    if not do_lancador or raiz != Path(do_lancador).resolve():
        raise AccessDenied(f"no modo travado vale só a raiz do lançador ({ENV_RAIZ}): --raiz diferente recusada")
    comando = getattr(args, "comando", None)
    acao = getattr(args, "memoria_acao" if comando == "memoria" else "acao", None)
    acoes = COMANDOS_DA_TRAVA.get(comando, set())
    if comando not in COMANDOS_DA_TRAVA or (acoes is not None and acao not in acoes) or (
            comando == "memoria" and getattr(args, "memoria_grupo", None) != "licao"):
        raise AccessDenied("comando fora do que a sessão do projeto pede no modo travado", comando=comando, acao=acao)
    if getattr(args, "ancora", None) is not None:
        raise AccessDenied("--ancora recusada no modo travado: vale só a âncora padrão desta máquina")
    pasta = exact_child(raiz / "projects", projeto)
    for nome, valor in sorted(vars(args).items()):
        if nome != "raiz" and isinstance(valor, PurePath):
            contained(pasta, valor if Path(valor).is_absolute() else Path.cwd() / valor, within=pasta)
    return raiz


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
        ligada, projeto = trava()
        if ligada:
            if not dentro_da_trava(projeto, action, resource):  # teto: nenhuma linha de ACL o derruba
                return False
            if subject == sessao_de(projeto):  # concessões derivadas da trava, sem linha de ACL
                return resource == f"project:{projeto}" and action in ACOES_DA_SESSAO
        if str(subject).startswith(PREFIXO_SESSAO):  # sessão fora da sua trava: tudo negado, mesmo com linha de ACL
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
        """Cria o primeiro administrador. Só funciona enquanto não houver nenhum, e nunca no modo travado."""
        if trava()[0]:
            raise AccessDenied("modo travado (sessão de projeto): sem administração")
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
