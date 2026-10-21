"""CLI da fundação: `python -m fundacao <comando>`.

A identidade vem do lançador (variável FUNDACAO_PRINCIPAL), nunca de um
argumento que o modelo possa escrever. Saída em JSON; erros em stderr com
código 2, sem conteúdo protegido. Restauração não liberada ou cópia que não confere: código 3.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path

from . import KIT_VERSION, TEMPLATE_VERSION
from .core import backup, components, events, memory, projects, routing
from .core.auth import Policy, principal_from_env
from .core.contracts import AccessDenied, FundacaoError
from .core.db import connect, uri_somente_leitura
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
    ok, bad = events.verify_chain(con)
    autorizados = [p["project_id"] for p in projects.list_projects(con, me)]
    marcas = ",".join("?" * len(autorizados))
    tarefas = ({r[0]: r[1] for r in con.execute(
        f"SELECT state, COUNT(*) FROM task WHERE project_id IN ({marcas}) GROUP BY state", autorizados)}
        if autorizados else {})
    return {
        "identidade": me.principal_id,
        "projetos_autorizados": autorizados,
        "componentes": _componentes_visiveis(args.raiz, con, me, autorizados),
        "tarefas_por_estado": tarefas,  # só dos projetos que a identidade pode ler
        "eventos_cadeia_integra": ok, "primeiro_evento_quebrado": bad,
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
    _exigir_opcoes(args, "objetivo" if args.acao == "criar" else "id")
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
    if args.acao == "verificar":
        ok, bad = events.verify_chain(con)
        return {"cadeia_integra": ok, "primeiro_evento_quebrado": bad}
    # Exportar copia metadados de todos os projetos: só auditoria ou administração da fundação.
    _exigir(con, me, ("audit", "foundation"), ("admin", "foundation"))
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


def _autorizar_pela_copia(origem: Path) -> str:
    """Restaurar e verificar são autorizados contra o banco DA CÓPIA, aberto somente leitura:
    funciona com o banco de origem corrompido ou perdido e não cria nem migra nada na origem.
    A negativa aqui não vai para a trilha (a cópia é somente leitura; a origem pode estar danificada)."""
    db = Path(origem) / "state" / "state.sqlite"
    if not db.is_file():
        raise FundacaoError("cópia sem banco de estado: não é possível autorizar a operação")
    con = sqlite3.connect(uri_somente_leitura(db, imutavel=True), uri=True)  # '#', '%', espaços, rede; sem -wal/-shm
    try:
        me = principal_from_env(con)
        if not Policy(con).allowed(me.principal_id, "admin", "foundation"):
            raise AccessDenied("restauração e verificação exigem administração da fundação (conferida na cópia)",
                               action="admin", resource="foundation")
    finally:
        con.close()
    return me.principal_id


def cmd_backup(args) -> dict:
    # Backup copia todos os projetos e o estado: só a administração da fundação.
    if args.acao == "criar":
        if not args.destino:
            raise FundacaoError("informe --destino (pasta nova ou vazia para a cópia)")
        if not (args.raiz / "state" / "state.sqlite").is_file():
            raise FundacaoError("fundação sem banco de estado nesta raiz: nada a copiar")
        con = _con(args.raiz)
        me = principal_from_env(con)
        _exigir(con, me, ("admin", "foundation"))
        con.close()
        return backup.create_backup(args.raiz, args.destino, args.rotulo)
    if not args.origem:
        raise FundacaoError("informe --origem (pasta da cópia)")
    quem = _autorizar_pela_copia(args.origem)
    if args.acao == "verificar":
        # Âncora (#8): a informada ou a do livro de cópias desta raiz.
        return backup.verify_backup(args.origem, sha256_manifesto=args.sha256_manifesto,
                                    livro=args.raiz / "state" / backup.LIVRO_COPIAS)
    if not args.destino:
        raise FundacaoError("informe --destino (pasta nova)")
    resultado = backup.restore(args.origem, args.destino, args.retiradas, executado_por=quem,
                               aceitar_registro_nao_comprovado=args.aceitar_registro_nao_comprovado,
                               sha256_manifesto=args.sha256_manifesto,
                               aceitar_copia_sem_ancora=args.aceitar_copia_sem_ancora)
    if resultado.get("released") and resultado.get("aviso_ancora"):
        sys.stderr.write(json.dumps({"aviso": {"code": "W_COPIA_SEM_ANCORA", "message": resultado["aviso_ancora"]}},
                                    ensure_ascii=False) + "\n")
    return resultado


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fundacao", description="Fundação de IA Multiprojetos (kit de referência)")
    p.add_argument("--raiz", type=Path, default=Path.cwd(), help="raiz autorizada da fundação")
    sub = p.add_subparsers(dest="comando", required=True)
    s = sub.add_parser("init"); s.add_argument("--admin"); s.set_defaults(func=cmd_init)
    s = sub.add_parser("status"); s.set_defaults(func=cmd_status)
    s = sub.add_parser("projeto"); s.add_argument("acao", choices=["criar", "listar", "drift"])
    s.add_argument("--id"); s.add_argument("--nome"); s.add_argument("--finalidade"); s.add_argument("--componentes")
    s.set_defaults(func=cmd_projeto)
    s = sub.add_parser("tarefa"); s.add_argument("acao", choices=["criar", "ver"])
    s.add_argument("--projeto", required=True); s.add_argument("--objetivo"); s.add_argument("--chave")
    s.add_argument("--id"); s.set_defaults(func=cmd_tarefa)
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
    s.add_argument("--aceitar-copia-sem-ancora", action="store_true",
                   help="decisão do administrador, depois de conferir de onde veio a cópia: restaura cópia sem "
                        "âncora que não consta no livro de cópias ou cujo código difere do kit; fica na trilha")
    s.set_defaults(func=cmd_backup)
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
        # Restauração não liberada (ex.: sem registro de retiradas) e cópia que não confere não são sucesso.
        falhou = isinstance(resultado, dict) and (
            resultado.get("released") is False or (args.comando == "backup" and resultado.get("ok") is False))
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
