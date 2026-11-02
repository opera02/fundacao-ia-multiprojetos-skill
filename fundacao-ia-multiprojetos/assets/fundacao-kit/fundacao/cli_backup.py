"""Comandos de backup, com identidade e conexão fornecidas pela entrada principal.

1.7.10 (desenho 1.7.10, §5.8 e §7.1; MELHORIAS-1.7.10, §0 itens 14 e 15):
- `backup criar` trava a manutenção (state/manutencao.json) do início ao fim, também na falha, depois de autorizar;
  devolve um resumo (a lista de arquivos só com --detalhar; ela está sempre no manifest.json da cópia) e grava
  registry/ultima-copia.json.
- `backup verificar` com sucesso, âncora conferida e fundação viva anota a verificação em registry/ultima-copia.json.
- `backup situacao` (administração ou auditoria) diz a idade da última cópia, pelo registro e pelo livro de cópias, e,
  passados 7 dias, avisa (W_COPIA_ANTIGA) com o comando pronto da próxima cópia.
- O que sobrar de uma pasta de preparo sai no stderr como W_SOBRA_DO_PREPARO, com a contagem e o caminho.
- Revisão de segurança da 1.7.10 (KIT-F7): `backup restaurar` passa a raiz da fundação viva — no desastre, sem ela, a
  --raiz com cara de fundação (fundacao/ ou projects/; correções da revisão 2) —, e a restauração recusa destino dentro
  dela; a próxima cópia não sugere de novo uma pasta dentro da raiz (o `backup criar` a recusaria).
O parser do comando fica aqui (`registrar_parser`), com as opções de sempre, a ação `situacao` e --detalhar: a entrada
principal o registra com `cmd_backup`, no lugar do bloco próprio.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .core import backup, limpeza, livro_assinado, manutencao, preparo, regras_da_copia
from .core.auth import Policy, principal_from_env
from .core.ancora_copia import _fundacao_viva, dentro_da_copia
from .core.comando_titular import _aspas_bash, _aspas_powershell
from .core.contracts import FundacaoError, ValidationError

ACOES = ("criar", "verificar", "restaurar", "situacao")


def registrar_parser(sub):
    """O subcomando `backup` inteiro: as opções de sempre, a ação `situacao` e --detalhar (1.7.10)."""
    s = sub.add_parser("backup")
    s.add_argument("acao", choices=list(ACOES))
    s.add_argument("--destino", type=Path)
    s.add_argument("--origem", type=Path)
    s.add_argument("--rotulo", default="manual")
    s.add_argument("--retiradas", type=Path, help="registro protegido de retiradas (obrigatório para liberar)")
    s.add_argument("--aceitar-registro-nao-comprovado", action="store_true",
                   help="decisão do administrador, depois de conferir o registro à mão: aceita registro sem "
                        "identidade comprovada (cópia de kit anterior ou registro recriado); fica na trilha")
    s.add_argument("--sha256-manifesto", help="âncora da cópia: o sha256_manifesto devolvido pelo `backup criar`, "
                                              "guardado fora da cópia (verificar e restaurar)")
    s.add_argument("--aceitar-copia-sem-ancora", metavar="MOTIVO",
                   help="decisão do administrador, depois de conferir de onde veio a cópia: restaura cópia sem "
                        "âncora externa, com o motivo; fica na resposta e na trilha")
    s.add_argument("--exigir-livro-assinado", action="store_true",
                   help="só aceita âncora do livro com assinatura válida do titular")
    s.add_argument("--detalhar", action="store_true",
                   help="criar: devolve também a lista de arquivos e o relatório do .git (por padrão, só o resumo)")
    return s


def executar(args, conectar):
    if args.acao in ("criar", "situacao"):
        if args.acao == "criar" and not args.destino:
            raise FundacaoError("informe --destino (pasta nova ou vazia para a cópia)")
        con = conectar(args.raiz)
        try:
            me, policy = principal_from_env(con), Policy(con)
            if args.acao == "criar":
                policy.require(me, "admin", "foundation")
            elif not any(policy.allowed(me.principal_id, a, "foundation") for a in ("admin", "audit")):
                policy.require(me, "audit", "foundation")  # registra a negativa e recusa
        finally:
            con.close()
        return _criar(args) if args.acao == "criar" else _situacao(args)
    if not args.origem:
        raise FundacaoError("informe --origem (pasta da cópia)")
    if getattr(args, "exigir_livro_assinado", False):
        # Com raiz viva, a ACL atual deve negar antes de ler manifesto ou livro.
        # Sem raiz viva, a assinatura ainda vem antes de confiar na ACL da cópia.
        # autorizar() reconfere a autorização depois da prova, inclusive revogações.
        _fundacao_viva(args.raiz, args.origem)
    livro = (args.raiz / "state" / backup.LIVRO_COPIAS if args.acao == "verificar"
             else args.retiradas.parent / backup.LIVRO_COPIAS if args.retiradas else None)
    if getattr(args, "exigir_livro_assinado", False):
        if livro is None or backup.dentro_da_copia(livro, args.origem):
            raise ValidationError("livro assinado deve ficar fora da cópia")
        sha = livro_assinado.ancora_do_livro(livro, preparo.ler(args.origem / "manifest.json"))
        if args.sha256_manifesto and args.sha256_manifesto != sha:
            raise ValidationError("hash informado diverge da assinatura do livro")
        args.sha256_manifesto = sha  # prova criptográfica verificada, não o hash de uma entrada sem assinatura
    # A cópia privada do banco, quando a autorização vem da cópia, também é contada ao sair (1.7.10).
    autorizacao = _avisando_sobra(backup.autorizar, args.raiz, args.origem, sha256_manifesto=args.sha256_manifesto,
                                  livro=livro)
    if args.acao == "verificar":
        resultado = {**backup.verify_backup(args.origem, sha256_manifesto=args.sha256_manifesto, livro=livro),
                     "autorizacao": autorizacao}
        _anotar_verificacao(args, resultado, autorizacao)
        return resultado
    if not args.destino:
        raise FundacaoError("informe --destino (pasta nova)")
    raiz = autorizacao.get("raiz")  # KIT-F7: a viva; no desastre (banco perdido), a --raiz com cara de fundação
    if autorizacao.get("politica") != "fundação viva" and not (raiz and regras_da_copia.cara_de_fundacao(raiz)):
        raiz = None  # revisão 2: antes, com o registro num cofre, a restauração dentro da raiz era liberada
    resultado = _avisando_sobra(backup.restore, args.origem, args.destino, args.retiradas,
                                executado_por=autorizacao["identidade"],
                                aceitar_registro_nao_comprovado=args.aceitar_registro_nao_comprovado,
                                sha256_manifesto=args.sha256_manifesto, livro=livro,
                                aceitar_copia_sem_ancora=args.aceitar_copia_sem_ancora,
                                raiz_da_fundacao=Path(raiz) if raiz else None)
    resultado["autorizacao"] = autorizacao
    if resultado.get("released") and resultado.get("aviso_ancora"):
        codigo = "W_ANCORA_DO_LIVRO" if resultado["ancora"]["situacao"] == "conferida" else "W_COPIA_SEM_ANCORA"
        sys.stderr.write(json.dumps({"aviso": {"code": codigo, "message": resultado["aviso_ancora"]}},
                                    ensure_ascii=False) + "\n")
    return resultado


def _avisar_sobra(sobra) -> None:
    """W_SOBRA_DO_PREPARO no stderr quando a limpeza de um preparo não foi completa (contagem e caminho)."""
    if not isinstance(sobra, dict) or sobra.get("limpa", True):
        return
    contagem = {k: sobra.get(k) for k in ("pasta", "arquivos", "pastas", "ligacoes", "bytes")}
    sys.stderr.write(json.dumps({"aviso": {"code": "W_SOBRA_DO_PREPARO", "message": limpeza.AVISO_SOBRA, **contagem,
                                           "erros": (sobra.get("erros") or [])[:3]}}, ensure_ascii=False) + "\n")


def _avisando_sobra(funcao, *args, **kwargs):
    """Chama `funcao` e avisa a sobra do preparo, também quando ela falha (a sobra vai junto do erro)."""
    try:
        resultado = funcao(*args, **kwargs)
    except BaseException as exc:
        _avisar_sobra(getattr(exc, "sobra_do_preparo", None) or (getattr(exc, "details", None) or {}).get(
            "sobra_do_preparo"))
        raise
    _avisar_sobra(resultado.get("sobra_do_preparo"))
    return resultado


def _criar(args) -> dict:
    destino = Path(os.path.abspath(args.destino))
    with manutencao.travada(args.raiz, f"backup criar ({args.rotulo})") as trava:
        res = _avisando_sobra(backup.create_backup, args.raiz, destino, args.rotulo)
        avisos = list(res.get("avisos") or [])
        try:  # o registro que o aviso de início de sessão lê (sem abrir state/)
            manutencao.registrar_copia(args.raiz, rotulo=res.get("label"), criada_em=res["created_at"],
                                       destino=str(destino.resolve()))
        except (OSError, FundacaoError) as exc:
            avisos.append(f"o registro da última cópia (registry/ultima-copia.json) não foi gravado "
                          f"({type(exc).__name__}): a cópia vale; `backup situacao` usa o livro de cópias")
    if trava is None:  # já havia uma trava (não desta operação): o backup correu sem trocá-la (#3)
        atual = manutencao.ler(args.raiz) or {}
        avisos.append(f"já havia uma trava de manutenção (motivo: {atual.get('motivo')}, pid: {atual.get('pid')}, "
                      f"host: {atual.get('host')}, desde: {atual.get('desde')}): não foi trocada nem removida; se a "
                      "operação dela já terminou, apague state/manutencao.json depois de conferir")
    if trava and trava.get("nao_removida"):
        avisos.append("a trava de manutenção (state/manutencao.json) não saiu (" + trava["nao_removida"] + "): "
                      "as sessões do Ubuntu não abrem enquanto ela existir; apague-a depois de conferir")
    if getattr(args, "detalhar", False):
        return {**res, "avisos": avisos}
    files, git = res.get("files") or [], res.get("git") or {}
    return {"rotulo": res.get("label"), "created_at": res.get("created_at"), "arquivos": len(files),
            "bytes": sum(f.get("size", 0) for f in files), "db": res.get("db"), "retiradas": res.get("retiradas"),
            "sha256_manifesto": res.get("sha256_manifesto"), "guarde_a_ancora": res.get("guarde_a_ancora"),
            "avisos": avisos, "ligacoes_nao_seguidas": res.get("ligacoes_nao_seguidas", []),
            "git_levados": len(git.get("levados", [])), "segredos_incluidos": res.get("segredos_incluidos", 0),
            "detalhes": "a lista de arquivos e o relatório do .git ficam no manifest.json da cópia (ou use --detalhar)"}


def _anotar_verificacao(args, resultado: dict, autorizacao: dict) -> None:
    """Cópia conferida (arquivos, banco e âncora) na fundação viva: a verificação vai para o registro da última
    cópia (registry/ultima-copia.json)."""
    copia = resultado.get("copia") or {}
    if not (resultado.get("ok") and resultado["ancora"].get("situacao") == "conferida"
            and autorizacao.get("politica") == "fundação viva" and copia.get("criada_em")):
        return
    try:
        resultado["registro_da_copia"] = manutencao.registrar_verificacao(
            args.raiz, rotulo=copia.get("rotulo"), criada_em=copia["criada_em"],
            destino=str(Path(os.path.abspath(args.origem)).resolve()))
    except (OSError, FundacaoError) as exc:
        resultado["registro_da_copia"] = (f"não gravado ({type(exc).__name__}): a verificação vale; o registro da "
                                          "última cópia ficou como estava")


def _situacao(args) -> dict:
    res = manutencao.situacao(args.raiz)
    res["proxima_copia"] = proxima_copia(args.raiz, (res.get("ultima_copia") or {}).get("destino"))
    if not res["em_dia"]:
        sys.stderr.write(json.dumps({"aviso": {"code": "W_COPIA_ANTIGA", "message": res["aviso"]}},
                                    ensure_ascii=False) + "\n")
    if res.get("aviso_trava"):
        sys.stderr.write(json.dumps({"aviso": {"code": "W_TRAVA_DE_MANUTENCAO", "message": res["aviso_trava"]}},
                                    ensure_ascii=False) + "\n")
    return res


def proxima_copia(raiz: Path, anterior: str | None, agora: datetime | None = None) -> dict:
    """Comandos prontos da próxima cópia (rótulo semanal-AAAA-Sss, na pasta da última cópia) e da verificação, no
    shell desta máquina: PowerShell no Windows; bash no Linux e no WSL."""
    ano, semana, _ = (agora or datetime.now(timezone.utc)).isocalendar()
    rotulo = base = f"semanal-{ano}-S{semana:02d}"
    # O destino anterior vem do livro ou do registro (gravados por quem grava state/ e registry/): com quebra de linha
    # ou nulo, ele quebraria o comando — vale como se não houvesse; dentro da raiz também (KIT-F7: o `criar` recusa).
    valido = (isinstance(anterior, str) and anterior and not any(c in anterior for c in "\r\n\0")
              and not dentro_da_copia(Path(anterior).parent, raiz))
    pasta = Path(anterior).parent if valido else None
    for n in range(2, 10):  # rótulo já usado nesta semana: o seguinte
        if pasta is None or not os.path.lexists(pasta / rotulo):
            break
        rotulo = f"{base}-{n}"
    destino = str(pasta / rotulo) if pasta else f"<pasta das cópias, de preferência em outro disco>/{rotulo}"
    aspas, python = (_aspas_powershell, "python") if os.name == "nt" else (_aspas_bash, "python3")
    cli = f"{python} -m fundacao --raiz {aspas(str(raiz))} backup"
    return {"rotulo": rotulo, "destino": destino,
            "criar": f"{cli} criar --destino {aspas(destino)} --rotulo {rotulo}",
            "verificar": f"{cli} verificar --origem {aspas(destino)}",
            "antes": ("rode na pasta da fundação, com as sessões dos projetos fechadas (a cópia trava a manutenção "
                      "enquanto roda)" + ("" if pasta else "; troque a pasta das cópias no destino"))}
