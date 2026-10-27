"""CLI da fundação: `python -m fundacao <comando>`.

A identidade vem do lançador (variável FUNDACAO_PRINCIPAL), nunca de um
argumento que o modelo possa escrever. Saída em JSON; erros em stderr com
código 2, sem conteúdo protegido. Restauração não liberada, cópia que não confere, decisão que não
confere, âncora desprotegida e tarefa não concluída: código 3.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path

from . import KIT_VERSION, TEMPLATE_VERSION
from .core import backup, components, decisoes, events, memory, projects, routing
from .core.auth import Policy, principal_from_env
from .core.contracts import FundacaoError
from .core.db import connect
from .core.tasks import Coordinator


def _out(data) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n")


def _exigir_opcoes(args, *opcoes: str) -> None:
    """Opções obrigatórias da ação. Faltando, o erro sai pelo contrato da CLI (JSON no stderr, código 2),
    não como traceback (auditoria final da 1.4.2, AF-01)."""
    faltam = [o for o in opcoes if getattr(args, o.replace("-", "_"), None) in (None, "")]
    if faltam:
        raise FundacaoError("informe " + " e ".join(f"--{o}" for o in faltam), faltam=[f"--{o}" for o in faltam])


def _con(root: Path, criar: bool = False):
    """Só o `init` cria o banco. Os demais comandos recusam raiz sem estado — senão um `status`
    numa fundação com banco perdido criaria um banco vazio no lugar (e mascararia a perda)."""
    db = root / "state" / "state.sqlite"
    if (root / "state" / backup.MARCA_NAO_LIBERADA).exists():
        raise FundacaoError("raiz de restauração não liberada (state/restauracao-nao-liberada.json): "
                            "não use; refaça a restauração numa pasta nova (fluxo C9)")
    if not criar and not db.is_file():
        raise FundacaoError("fundação sem banco de estado nesta raiz; para recuperar, restaure uma cópia (fluxo C9)")
    con = connect(db)
    if not criar:
        # Reinício também reconcilia: decisão protegida confirmada no banco e ainda fora do registro
        # (falha ou queda depois do commit) vai agora. Sem conseguir, avisa e segue (auditoria F11).
        try:
            backup.flush_outbox(con, root / "state" / "retiradas.jsonl")
        except (OSError, FundacaoError) as exc:
            sys.stderr.write(json.dumps({"aviso": {
                "code": "W_REGISTRO_PROTEGIDO_PENDENTE", "pendentes": backup.outbox_pending(con),
                "message": "decisões protegidas ainda não gravadas em state/retiradas.jsonl; corrija o acesso ao "
                           "registro e rode `init` (backup e restauração recusam enquanto houver pendência)",
                "tipo": type(exc).__name__}}, ensure_ascii=False) + "\n")
    return con


def cmd_init(args) -> dict:
    root = args.raiz
    for sub in ("registry/components", "templates/project", "projects", "state", "evidence"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    con = _con(root, criar=True)
    policy = Policy(con)
    has_admin = con.execute("SELECT 1 FROM acl WHERE resource='foundation' AND action='admin'").fetchone()
    created_admin = None
    if not has_admin:
        if not args.admin:
            raise FundacaoError("primeira inicialização exige --admin <identidade do titular>")
        policy.bootstrap_admin(args.admin)
        created_admin = args.admin
    # Registro protegido de retiradas e revogações, com identidade própria desde o início (a
    # restauração confere a identidade anotada na cópia). Numa fundação existente — por exemplo,
    # depois de atualizar o kit —, cria a identidade se faltar e preenche as retiradas que estão
    # no banco e faltam no registro. Idempotente.
    log = root / "state" / "retiradas.jsonl"
    log_id = backup.ensure_tombstone_log(log)
    # Decisões protegidas confirmadas no banco e ainda fora do registro (falha ou queda depois do
    # commit) vão agora; sem conseguir, o `init` falha (auditoria F11).
    exportadas = backup.flush_outbox(con, log)["exportadas"]
    # Memórias já retiradas por kit anterior: derivados registrados por revisão também saem de uso (F07).
    reparos = memory.repair_withdrawn_derivations(con)  # cada reparo entra na outbox, na mesma transação
    backup.flush_outbox(con, log)
    preenchidas = backup.backfill_tombstone_log(con, log)
    extra = {}
    if exportadas > 0:
        extra["pendencias_exportadas"] = exportadas
    if reparos:
        extra["derivados_reparados"] = [{"memory_id": r["memory_id"], "novos": r["novos"]} for r in reparos]
    return {"raiz": str(root), "kit_version": KIT_VERSION, "template_version": TEMPLATE_VERSION,
            "admin_criado": created_admin, "user_version": con.execute("PRAGMA user_version").fetchone()[0],
            "registro_retiradas": {"identidade": log_id, "preenchidas": preenchidas, **extra}}


def _componentes_visiveis(root: Path, con, me, autorizados: list[str]) -> list[dict]:
    """Administração vê todos; as demais identidades veem só componentes dos próprios
    projetos, com a lista de projetos recortada (não revela nomes de outros projetos)."""
    todos = components.discover(root)
    if Policy(con).allowed(me.principal_id, "admin", "foundation"):
        return todos
    visiveis = []
    for comp in todos:
        meus = [p for p in comp.get("allowed_projects", []) if p in autorizados]
        if meus:
            visiveis.append({**comp, "allowed_projects": meus})
    return visiveis


def cmd_status(args) -> dict:
    con = _con(args.raiz)
    me = principal_from_env(con)
    diagnostico_global = any(Policy(con).allowed(me.principal_id, a, "foundation") for a in ("audit", "admin"))
    ok, bad = events.verify_chain(con) if diagnostico_global else (None, None)
    autorizados = [p["project_id"] for p in projects.list_projects(con, me)]
    marcas = ",".join("?" * len(autorizados))
    tarefas = ({r[0]: r[1] for r in con.execute(
        f"SELECT state, COUNT(*) FROM task WHERE project_id IN ({marcas}) GROUP BY state", autorizados)}
        if autorizados else {})
    return {"identidade": me.principal_id, "projetos_autorizados": autorizados,
        "componentes": _componentes_visiveis(args.raiz, con, me, autorizados),
        "tarefas_por_estado": tarefas,  # só dos projetos que a identidade pode ler
        "eventos_cadeia_integra": ok, "primeiro_evento_quebrado": bad,
        "eventos_diagnostico_global": "medido" if diagnostico_global else "nao_medido_sem_permissao",
    }


def cmd_projeto(args) -> dict:
    con = _con(args.raiz)
    me = principal_from_env(con)
    if args.acao == "criar":
        _exigir_opcoes(args, "id", "nome", "finalidade")
        comps = [c for c in (args.componentes or "").split(",") if c]
        return projects.create_project(args.raiz, con, me, args.id, args.nome, args.finalidade, comps)
    if args.acao == "listar":
        return {"projetos": projects.list_projects(con, me)}
    if args.acao == "drift":
        _exigir_opcoes(args, "id")
        projects.project_root(args.raiz, con, me, args.id)
        return projects.template_drift(args.raiz, args.id)
    raise FundacaoError("ação desconhecida")


def cmd_tarefa(args) -> dict:
    con = _con(args.raiz)
    me = principal_from_env(con)
    if args.acao == "concluir":
        # Só o aceite válido sobre a entrega exata, registrado e mais recente da tarefa (decisoes.concluir_tarefa).
        _exigir_opcoes(args, "decisao")
        return decisoes.concluir_tarefa(args.raiz, con, me, args.decisao, ancora=decisoes.resolver_ancora(args.ancora),
                                        politica=decisoes.carregar_politica(args.raiz), projeto=args.projeto)
    _exigir_opcoes(args, "projeto", "objetivo" if args.acao == "criar" else "id")
    coord = Coordinator(args.raiz, con, me, args.projeto)
    if args.acao == "criar":
        return {"task_id": coord.create_task(args.objetivo, args.chave)}
    if args.acao == "ver":
        return coord.get_task(args.id)
    raise FundacaoError("ação desconhecida")


def cmd_componente(args) -> dict:
    con = _con(args.raiz)
    me = principal_from_env(con)  # listar também exige identidade
    if args.acao == "listar":
        autorizados = [p["project_id"] for p in projects.list_projects(con, me)]
        return {"componentes": _componentes_visiveis(args.raiz, con, me, autorizados)}
    _exigir_opcoes(args, "id")
    resultado = components.set_enabled(args.raiz, con, me, args.id, args.acao == "habilitar")
    for aviso in resultado.get("avisos", []):
        # Também no stderr, para quem lê só o terminal (N1: skill de host continua no disco).
        sys.stderr.write(f"AVISO {aviso['codigo']}: {aviso['mensagem']} Pasta: {aviso['pasta']}\n")
    return resultado


def cmd_acl(args) -> dict:
    con = _con(args.raiz)
    me = principal_from_env(con)
    policy = Policy(con)
    if args.acao == "registrar":
        policy.register_principal(me, args.principal)
    elif args.acao == "conceder":
        _exigir_opcoes(args, "recurso", "acao-permitida")
        policy.grant(me, args.principal, args.recurso, args.acao_permitida)
    elif args.acao == "revogar":
        _exigir_opcoes(args, "recurso", "acao-permitida")
        policy.revoke(me, args.principal, args.recurso, args.acao_permitida)
    return {"ok": True}


def _exigir(con, me, *permissoes: tuple[str, str]) -> None:
    """Exige ao menos uma das permissões (ação, recurso); a negativa fica registrada."""
    policy = Policy(con)
    if not any(policy.allowed(me.principal_id, acao, recurso) for acao, recurso in permissoes):
        policy.require(me, *permissoes[0])


def cmd_eventos(args) -> dict:
    con = _con(args.raiz)
    me = principal_from_env(con)
    # Verificar e exportar leem metadados globais: autorize antes de qualquer leitura.
    _exigir(con, me, ("audit", "foundation"), ("admin", "foundation"))
    if args.acao == "verificar":
        ok, bad = events.verify_chain(con)
        return {"cadeia_integra": ok, "primeiro_evento_quebrado": bad}
    if not args.destino:
        raise FundacaoError("informe --destino")
    return {"exportados": events.export_jsonl(con, args.destino)}


def cmd_rota(args) -> dict:
    """Gasto de uma rota (auditoria ou administração) e reconciliação de custo (administração)."""
    con = _con(args.raiz)
    me = principal_from_env(con)
    if args.acao == "gasto":
        _exigir(con, me, ("audit", "foundation"), ("admin", "foundation"))
        return routing.spending_report(con, args.rota)
    if not (args.tentativa and args.custo_usd is not None and args.fonte):
        raise FundacaoError("informe --tentativa, --custo-usd e --fonte")
    return routing.reconcile_cost(con, me, args.rota, args.tentativa, args.custo_usd, args.fonte)


def cmd_backup(args) -> dict:
    from .cli_backup import executar
    return executar(args, _con)


def cmd_extensao(args):
    con = _con(args.raiz)
    try:
        return args.executor(args, con, principal_from_env(con), args.raiz / "state" / "retiradas.jsonl")
    finally:
        con.close()


def cmd_decisao(args) -> dict:
    """Decisões do titular sobre entregas, assinadas com chave fora do alcance do executor e conferidas contra a
    âncora (references/seguranca-isolamento.md §2). A âncora padrão desta máquina, se existir, é a única que vale."""
    if args.acao == "conferir-ancora":
        return decisoes.conferir_ancora(decisoes.resolver_ancora(args.ancora) or Path(decisoes.ANCORAS_PADRAO[0]))
    con = _con(args.raiz)
    me = principal_from_env(con)
    politica = decisoes.carregar_politica(args.raiz)
    ancora = decisoes.resolver_ancora(args.ancora)
    if args.acao == "preparar":
        _exigir_opcoes(args, "projeto", "tarefa", "entrega", "tipo", "motivo")
        r = decisoes.preparar_decisao(args.raiz, con, me, projeto=args.projeto, tarefa=args.tarefa,
                                      entrega=args.entrega, tipo=args.tipo, motivo=args.motivo,
                                      decisao_id=args.decisao_id, ancora=ancora, politica=politica, shell=args.shell)
        return {**r, "politica": decisoes.resumo_politica(politica)}
    _exigir_opcoes(args, "arquivo")
    projeto, arquivo = decisoes.pasta_da_decisao(args.raiz, args.arquivo)
    pasta = projects.project_root(args.raiz, con, me, projeto, action="write" if args.acao == "registrar" else "read")
    if args.acao == "comando":
        assinante = decisoes.ler_decisao(arquivo).get("assinante", me.principal_id)
        return {"decisao": str(arquivo), "para_o_titular": decisoes.comando_para_o_titular(
            arquivo, assinante=assinante, ancora=ancora or decisoes.ANCORAS_PADRAO[0], shell=args.shell)}
    r = decisoes.verificar_decisao(arquivo, pasta, ancora, politica)
    r["politica"] = decisoes.resumo_politica(politica)
    if args.acao == "registrar":
        r.update(decisoes.registrar_decisao(con, me, pasta, r) if r["valida"] else {"registro": "não registrada"})
    return r


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fundacao", description="Fundação de IA Multiprojetos (kit de referência)")
    p.add_argument("--raiz", type=Path, default=Path.cwd(), help="raiz autorizada da fundação")
    sub = p.add_subparsers(dest="comando", required=True)
    s = sub.add_parser("init"); s.add_argument("--admin"); s.set_defaults(func=cmd_init)
    s = sub.add_parser("status"); s.set_defaults(func=cmd_status)
    s = sub.add_parser("projeto"); s.add_argument("acao", choices=["criar", "listar", "drift"])
    s.add_argument("--id"); s.add_argument("--nome"); s.add_argument("--finalidade"); s.add_argument("--componentes")
    s.set_defaults(func=cmd_projeto)
    s = sub.add_parser("tarefa"); s.add_argument("acao", choices=["criar", "ver", "concluir"])
    s.add_argument("--projeto"); s.add_argument("--objetivo"); s.add_argument("--chave"); s.add_argument("--id")
    s.add_argument("--decisao", type=Path, help="concluir: o aceite em projects/<projeto>/decisoes/")
    s.add_argument("--ancora", type=Path, help="concluir: allowed_signers (com a âncora padrão presente, só ela vale)")
    s.set_defaults(func=cmd_tarefa)
    s = sub.add_parser("componente"); s.add_argument("acao", choices=["listar", "habilitar", "desabilitar"])
    s.add_argument("--id"); s.set_defaults(func=cmd_componente)
    s = sub.add_parser("acl"); s.add_argument("acao", choices=["registrar", "conceder", "revogar"])
    s.add_argument("--principal", required=True); s.add_argument("--recurso"); s.add_argument("--acao-permitida")
    s.set_defaults(func=cmd_acl)
    s = sub.add_parser("eventos"); s.add_argument("acao", choices=["verificar", "exportar"])
    s.add_argument("--destino", type=Path); s.set_defaults(func=cmd_eventos)
    s = sub.add_parser("rota"); s.add_argument("acao", choices=["gasto", "custo"])
    s.add_argument("--rota", required=True); s.add_argument("--tentativa", help="event_id da tentativa")
    s.add_argument("--custo-usd", help="custo conferido, em dólares (decimal)")
    s.add_argument("--fonte", help="onde o custo foi conferido (painel, fatura)")
    s.set_defaults(func=cmd_rota)
    s = sub.add_parser("backup"); s.add_argument("acao", choices=["criar", "verificar", "restaurar"])
    s.add_argument("--destino", type=Path); s.add_argument("--origem", type=Path); s.add_argument("--rotulo", default="manual")
    s.add_argument("--retiradas", type=Path, help="registro protegido de retiradas (obrigatório para liberar)")
    s.add_argument("--aceitar-registro-nao-comprovado", action="store_true",
                   help="decisão do administrador, depois de conferir o registro à mão: aceita registro sem "
                        "identidade comprovada (cópia de kit anterior ou registro recriado); fica na trilha")
    s.add_argument("--sha256-manifesto", help="âncora da cópia: o sha256_manifesto devolvido pelo `backup criar`, "
                                              "guardado fora da cópia (verificar e restaurar)")
    s.add_argument("--aceitar-copia-sem-ancora", metavar="MOTIVO",
                   help="decisão do administrador, depois de conferir de onde veio a cópia: restaura cópia sem "
                        "âncora externa, com o motivo; fica na resposta e na trilha")
    s.set_defaults(func=cmd_backup)
    s.add_argument("--exigir-livro-assinado", action="store_true", help="só aceita âncora do livro com assinatura válida do titular")
    from . import cli_conhecimento, cli_copias, cli_memoria
    for modulo in (cli_memoria, cli_copias, cli_conhecimento):
        modulo.registrar_parser(sub).set_defaults(func=cmd_extensao, executor=modulo.executar)
    s = sub.add_parser("decisao", help="decisões do titular sobre entregas (assinatura ssh-keygen -Y)")
    s.add_argument("acao", choices=["preparar", "verificar", "registrar", "conferir-ancora", "comando"])
    s.add_argument("--projeto"); s.add_argument("--tarefa"); s.add_argument("--tipo", choices=list(decisoes.TIPOS))
    s.add_argument("--entrega", help="caminho da entrega a partir da pasta do projeto, dentro de outputs/")
    s.add_argument("--motivo", help="as palavras do titular"); s.add_argument("--decisao-id")
    s.add_argument("--arquivo", type=Path, help="decisão em projects/<projeto>/decisoes/")
    s.add_argument("--ancora", type=Path, help="allowed_signers (com a âncora padrão presente, só ela vale)")
    s.add_argument("--shell", choices=list(decisoes.SHELLS),
                   help="shell do comando do titular (padrão: PowerShell no Windows e no WSL; bash no Linux)")
    s.set_defaults(func=cmd_decisao)
    return p


def main(argv: list[str] | None = None) -> int:
    # Windows: o console/pipe pode usar página de código legada; a saída é sempre UTF-8.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    args.raiz = args.raiz.resolve()
    try:
        resultado = args.func(args)
        _out(resultado)
        # Restauração não liberada (ex.: sem registro de retiradas), cópia que não confere, decisão que não confere,
        # âncora desprotegida e tarefa não concluída não são sucesso.
        falhou = isinstance(resultado, dict) and (
            resultado.get("released") is False or (args.comando == "backup" and resultado.get("ok") is False)
            or (args.comando == "decisao" and False in (resultado.get("valida"), resultado.get("protegida")))
            or (args.comando == "tarefa" and resultado.get("concluida") is False))
        return 3 if falhou else 0
    except FundacaoError as exc:
        sys.stderr.write(json.dumps(exc.as_dict(), ensure_ascii=False, default=str) + "\n")
        return 2
    except (OSError, sqlite3.DatabaseError, json.JSONDecodeError) as exc:
        # Erros de arquivo e de banco também seguem o contrato: JSON em stderr e código 2.
        codigo = "E_BANCO" if isinstance(exc, sqlite3.DatabaseError) else "E_ARQUIVO"
        sys.stderr.write(json.dumps({"error": {"code": codigo, "message": str(exc),
                                               "tipo": type(exc).__name__}}, ensure_ascii=False) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
