"""Comandos de lições; a CLI principal fornece conexão e identidade do lançador."""

from __future__ import annotations

from .core import events, licoes
from .core.contracts import ValidationError
from .core.memory import MemoryService


def registrar_parser(subparsers):
    memoria = subparsers.add_parser("memoria", help="memória persistente do projeto")
    grupos = memoria.add_subparsers(dest="memoria_grupo", required=True)
    licao = grupos.add_parser("licao", help="lições com gatilho, evidência e confiança")
    acoes = licao.add_subparsers(dest="memoria_acao", required=True)
    for acao in ("propor", "revisar"):
        parser = acoes.add_parser(acao)
        if acao == "propor":
            parser.add_argument("--projeto", required=True)
            parser.add_argument("--op-id", required=True)
            parser.add_argument("--origem", choices=("humano", "ia", "documento"), default="ia")
            parser.add_argument("--vigente-desde")
        else:
            parser.add_argument("--memoria", required=True)
            parser.add_argument("--revisao", required=True, type=int)
            parser.add_argument("--motivo", required=True)
            parser.add_argument("--mudanca", choices=("correcao", "mudanca_decisao"), default="correcao")
        for campo in ("gatilho", "licao", "evidencia"):
            parser.add_argument("--" + campo, required=True)
        parser.add_argument("--confianca", choices=sorted(licoes.CONFIANCAS), required=True)
    consultar = acoes.add_parser("consultar")
    consultar.add_argument("--projeto", required=True)
    consultar.add_argument("--gatilho", required=True)
    for acao in ("pendente", "aprovar", "historico", "retirar"):
        parser = acoes.add_parser(acao)
        parser.add_argument("--memoria", required=True)
        if acao == "aprovar":
            parser.add_argument("--hash", required=True)
        if acao == "retirar":
            parser.add_argument("--motivo", required=True)
    return memoria


def executar(args, con, principal, tombstone_log=None):
    servico = MemoryService(con, principal, tombstone_log)
    acao = args.memoria_acao
    if acao == "consultar":
        return servico.query_licoes(project_id=args.projeto, gatilho=args.gatilho)
    if acao in {"propor", "revisar"}:
        body = licoes.serializar(gatilho=args.gatilho, licao=args.licao, evidencia=args.evidencia,
                                 confianca=args.confianca)
        if acao == "propor":
            mid = servico.propose(op_id=args.op_id, scope="project", project_id=args.projeto,
                                 kind="licao", origin=args.origem, body=body, source_ref=args.evidencia,
                                 effective_from=args.vigente_desde)
            return {"memory_id": mid}
    # As ações pelo ID usam os mesmos controles de autorização e aprovação da
    # memória; nunca aceitam identidade ou aprovação dentro do corpo da lição.
    row = con.execute("SELECT scope,project_id,case_id,kind FROM memory_item WHERE memory_id=?",
                      (args.memoria,)).fetchone()
    if row is None:
        raise ValidationError("lição não encontrada")
    recurso = servico._resource(row["scope"], row["project_id"], row["case_id"])
    if not servico.policy.allowed(principal.principal_id, "read", recurso):
        # O ID alheio nao confirma existencia nem revela projeto/tipo ao chamador.
        # A negativa fica apenas na trilha interna, como em MemoryService.pending_hash.
        events.emit(con, "access_denied", subject=principal.principal_id,
                    payload={"action": "read", "resource": recurso, "source": principal.source})
        raise ValidationError("lição não encontrada")
    if row["kind"] != "licao":
        raise ValidationError("memória informada não é uma lição")
    if acao == "revisar":
        return {"revision": servico.revise(args.memoria, expected_revision=args.revisao, body=body,
                                          source_ref=args.evidencia, reason=args.motivo, change_kind=args.mudanca)}
    if acao == "pendente":
        revisao, digest = servico.pending_hash(args.memoria)
        return {"revision": revisao, "hash": digest}
    if acao == "aprovar":
        return {"revision": servico.approve(args.memoria, args.hash)}
    if acao == "historico":
        return servico.history(args.memoria)
    if acao == "retirar":
        return {"affected": servico.withdraw(args.memoria, args.motivo)}
    raise ValidationError("ação de lição inválida")
