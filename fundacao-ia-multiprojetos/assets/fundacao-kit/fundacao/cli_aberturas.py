"""Ficha de aberturas na CLI: `python -m fundacao abertura preparar|verificar|vigente` (1.7.10; contratos do lote 2,
§5). O `__main__` registra este módulo no laço das extensões (`registrar_parser` e `executar`, como cli_memoria).

- `preparar --projeto P --rascunho ARQ`: o rascunho (JSON dentro da pasta do projeto, lido sem seguir ligação) vira a
  ficha `projects/<p>/outputs/aberturas/ficha-v<N>.json`: a versão é a seguinte à maior já vista (rascunhos, caixa de
  entrada e, no Linux, área do titular), o `manifesto_sha256` vazio de um plugin é calculado no disco, os tetos fixos
  (core/aberturas_regras.py) e o disco dos plugins (core/aberturas_plugins.py) são conferidos, e a ficha vai na forma
  canônica, como arquivo novo. Devolve o que ela abre, em português simples, e a forma fixa do comando da ferramenta
  do titular, na cópia protegida (nunca um comando montado com valores do rascunho), com onde rodá-la sem o perfil
  de um shell (core/aberturas_comando.py). Exige escrita no projeto.
- `verificar --projeto P [--versao N]`: confere a ficha preparada (a maior, sem `--versao`) e diz se a caixa de entrada
  já tem essa versão assinada. Exige leitura no projeto. Ficha adulterada depois do preparo: `valida` falso, nunca um
  erro fora do formato.
- `vigente --projeto P [--area A] [--json]`: `core/aberturas.vigente`, sem banco e sem identidade: a ação troca o
  `func` do laço das extensões (que abriria o banco) pelo dela. Sem `--area`: no Linux, a área do titular de dono
  root; no Windows, a caixa de entrada, rotulada "caixa-de-entrada (não instalada)". A saída é sempre JSON (`--json`
  só a confirma).
O disco é o de core/aberturas_disco.py: no POSIX, o rascunho é lido e a ficha criada pela pasta aberta, sem seguir
ligação (trocar `outputs/` por um link no meio não desvia nada); no Windows, pelo caminho conferido parte a parte.
Com o kit travado no projeto do lançador (FUNDACAO_PROJETO_TRAVADO, contratos §4), as três ações recusam outro
projeto, e `vigente` recusa `--area` e raiz diferente da do lançador: a trava só restringe, nunca amplia.
"""

from __future__ import annotations

import hashlib
import os
from datetime import date
from pathlib import Path

from .core import aberturas, events
from .core.aberturas_disco import LeituraRecusada, Pasta
from .core.aberturas_plugins import conferir_plugin
from .core.aberturas_regras import SCHEMA, TETO_FICHA, canonico, carregar, descrever, mostrar, validar
from .core.contracts import AccessDenied, NotFound, PathEscape, ValidationError
from .core.projects import project_root

ENV_TRAVA = "FUNDACAO_PROJETO_TRAVADO"
ENV_RAIZ = "FUNDACAO_RAIZ"


def registrar_parser(subparsers):
    p = subparsers.add_parser("abertura", allow_abbrev=False,
                              help="ficha de aberturas do projeto (fechada por padrão; só a assinatura do titular abre)")
    acoes = p.add_subparsers(dest="acao", required=True)  # dest 'acao' como os demais comandos (pedido do PORTEIRO)
    a = acoes.add_parser("preparar", allow_abbrev=False, help="valida, numera e grava a ficha a partir do rascunho")
    a.add_argument("--projeto", required=True)
    a.add_argument("--rascunho", required=True, type=Path,
                   help="JSON do rascunho dentro da pasta do projeto (relativo a ela, ou absoluto)")
    a = acoes.add_parser("verificar", allow_abbrev=False, help="confere a ficha preparada e a assinatura dela")
    a.add_argument("--projeto", required=True)
    a.add_argument("--versao", type=int, help="padrão: a maior versão preparada")
    a = acoes.add_parser("vigente", allow_abbrev=False, help="a ficha em vigor, sem banco e sem identidade")
    a.add_argument("--projeto", required=True)
    a.add_argument("--area", type=Path, default=None, help="pasta das fichas assinadas (padrão resolvido no executor: "
                                                           "a do titular no Linux; a caixa de entrada da raiz no Windows)")
    a.add_argument("--json", action="store_true", help="saída em JSON (é sempre)")
    a.set_defaults(func=cmd_vigente)  # vence o `func` que o laço das extensões põe no `abertura`: não abre o banco
    return p


def _conferir_trava(args) -> None:
    travado = os.environ.get(ENV_TRAVA, "").strip()
    if not travado:
        return
    if args.projeto != travado:
        raise AccessDenied("kit travado no projeto do lançador: outro projeto é recusado", projeto=args.projeto)
    if getattr(args, "area", None) is not None:
        raise AccessDenied("kit travado: a ficha em vigor só da área padrão (sem --area)")
    raiz = os.environ.get(ENV_RAIZ, "").strip()
    if raiz and Path(raiz).resolve() != Path(args.raiz).resolve():
        raise AccessDenied("kit travado: raiz diferente da do lançador")


def cmd_vigente(args) -> dict:
    """`abertura vigente`: a ficha em vigor, sem banco e sem identidade."""
    _conferir_trava(args)
    area, rotulo = aberturas.area_padrao(args.raiz, args.projeto) if args.area is None else (args.area, None)
    resultado = aberturas.vigente(args.raiz, args.projeto, area)
    if rotulo:
        resultado["area"] = rotulo
    return resultado


def executar(args, con=None, principal=None, tombstone_log=None):
    if args.acao == "vigente":
        return cmd_vigente(args)
    _conferir_trava(args)
    if con is None or principal is None:
        raise ValidationError("preparar e verificar exigem o banco e a identidade do lançador")
    if args.acao == "preparar":
        return preparar(args.raiz, con, principal, args.projeto, args.rascunho)
    if args.acao == "verificar":
        return verificar(args.raiz, con, principal, args.projeto, args.versao)
    raise ValidationError("ação de abertura desconhecida")


def _no_projeto(pasta: Path, caminho: Path) -> tuple[str, ...]:
    """As partes do rascunho abaixo da pasta do projeto (relativo a ela, ou absoluto dentro dela)."""
    alvo = Path(os.path.abspath(caminho if Path(caminho).is_absolute() else pasta / caminho))
    try:
        partes = alvo.relative_to(pasta).parts
    except ValueError:
        partes = ()
    if not partes:
        raise PathEscape("o rascunho precisa ser um arquivo dentro da pasta do projeto", rascunho=str(caminho))
    return partes


def _ler_rascunho(pasta: Path, rascunho) -> bytes:
    partes = _no_projeto(pasta, Path(rascunho))
    try:
        with Pasta(pasta, partes[:-1]) as aberta:
            bruto = aberta.ler(partes[-1], TETO_FICHA)
    except LeituraRecusada as exc:
        raise PathEscape(f"rascunho recusado ({exc})", rascunho=str(rascunho)) from None
    if bruto is None:
        raise NotFound("rascunho inexistente na pasta do projeto", rascunho=str(rascunho))
    return bruto


def _plugins(ficha: dict) -> list[dict]:
    lista = ficha.get("plugins") if isinstance(ficha, dict) else None
    return [p for p in lista if isinstance(p, dict)] if isinstance(lista, list) else []


def _erros_dos_plugins(pasta: Path, ficha: dict) -> list[dict]:
    return [e for item in _plugins(ficha) for e in conferir_plugin(pasta, item)["erros"]]


def preparar(raiz, con, principal, projeto: str, rascunho) -> dict:
    pasta = project_root(raiz, con, principal, projeto, action="write")
    bruto = _ler_rascunho(pasta, rascunho)
    try:
        dados = carregar(bruto)
    except ValueError as exc:
        raise ValidationError(f"rascunho ilegível: {exc}") from None
    if not isinstance(dados, dict):
        raise ValidationError("o rascunho precisa ser um objeto JSON com os campos da ficha")
    if dados.get("schema_version", SCHEMA) != SCHEMA:
        raise ValidationError(f"rascunho de outro esquema: use {SCHEMA}")
    if dados.get("project_id", projeto) != projeto:
        raise ValidationError("rascunho de outro projeto: nada foi gravado", projeto=projeto)
    versao = aberturas.proxima_versao(raiz, projeto, pasta)
    ficha = {**dados, "schema_version": SCHEMA, "project_id": projeto, "versao": versao}
    ficha.setdefault("ficha_id", f"aberturas-{projeto}")
    for item in _plugins(ficha):  # manifesto vazio: calculado agora, no disco (a ferramenta do titular confere de novo)
        if item.get("manifesto_sha256") in (None, ""):
            item["manifesto_sha256"] = conferir_plugin(pasta, {**item, "manifesto_sha256": ""})["manifesto_sha256"] or ""
    problemas = validar(ficha, projeto=projeto, hoje=date.today())
    erros = problemas["erros"] + _erros_dos_plugins(pasta, ficha)
    if erros:
        raise ValidationError("rascunho recusado pelos tetos da ficha de aberturas: nada foi gravado", erros=erros[:50],
                              avisos=problemas["avisos"][:50])
    conteudo = canonico(ficha)
    with Pasta(pasta, aberturas.RASCUNHOS, criar=True) as destino:
        destino.criar_novo(aberturas.nome_da_ficha(versao), conteudo)
    sha = hashlib.sha256(conteudo).hexdigest()
    events.emit(con, "abertura_preparada", project_id=projeto, subject=principal.principal_id,
                payload={"versao": versao, "sha256_ficha": sha})
    out = {"projeto": projeto, "versao": versao, "ficha_id": ficha["ficha_id"],
           "arquivo": str(pasta.joinpath(*aberturas.RASCUNHOS, aberturas.nome_da_ficha(versao))), "sha256": sha,
           "aberturas": descrever(ficha), "avisos": problemas["avisos"],
           "para_o_titular": aberturas.comando_do_titular(raiz, projeto, versao),
           "proximo_passo": "o titular roda, FORA do Claude, a forma fixa de para_o_titular como diz o onde_rodar dela "
                            "(a caixa Executar, Win+R, onde houver: um terminal novo também carrega o perfil, $PROFILE "
                            "ou ~/.bashrc, que a sessão pode ter gravado): a ferramenta mostra o que a ficha abre, pede "
                            "o nome do projeto e assina; no Ubuntu, o preparo do projeto (sudo) instala a ficha "
                            "assinada na área do titular",
           "importante": aberturas.HONESTIDADE}
    if "versao" in dados and dados["versao"] != versao:
        out["versao_do_rascunho_trocada"] = {"no_rascunho": mostrar(dados["versao"]), "gravada": versao}
    return out


def verificar(raiz, con, principal, projeto: str, versao: int | None) -> dict:
    pasta = project_root(raiz, con, principal, projeto, action="read")
    try:
        with Pasta(pasta, aberturas.RASCUNHOS) as rascunhos:
            presentes = aberturas.versoes(rascunhos.nomes())
            versao = max(presentes) if versao is None and presentes else versao
            bruto = rascunhos.ler(presentes[versao], TETO_FICHA) if versao in presentes else None
    except LeituraRecusada as exc:
        raise PathEscape(f"ficha preparada recusada ({exc})", versao=versao) from None
    if bruto is None:
        raise NotFound("ficha preparada inexistente em outputs/aberturas/", versao=versao)
    out = {"projeto": projeto, "versao": versao, "arquivo": str(pasta.joinpath(*aberturas.RASCUNHOS, presentes[versao])),
           "sha256": hashlib.sha256(bruto).hexdigest(), "importante": aberturas.HONESTIDADE}
    try:
        ficha = carregar(bruto)
    except ValueError as exc:
        return {**out, "valida": False, "erros": [{"campo": "ficha", "motivo": f"ilegível: {exc}"}], "avisos": []}
    problemas = validar(ficha, projeto=projeto, hoje=date.today())
    erros = problemas["erros"] + _erros_dos_plugins(pasta, ficha)
    if isinstance(ficha, dict) and ficha.get("versao") != versao:
        erros.append({"campo": "versao", "motivo": "a versão escrita na ficha difere da do nome do arquivo"})
    assinavel = None if erros else hashlib.sha256(canonico(ficha)).hexdigest()
    assinada = aberturas.conferir_versao(aberturas.caixa_de_entrada(raiz, projeto), versao, projeto)
    return {**out, "valida": not erros, "erros": erros[:50], "avisos": problemas["avisos"][:50],
            "forma_canonica": assinavel == out["sha256"], "aberturas": descrever(ficha),
            "assinatura": {"na_caixa_de_entrada": assinada["sha256"] is not None, "valida": assinada["valida"],
                           "igual_a_esta": assinavel is not None and assinada["sha256"] == assinavel,
                           "motivo": assinada["motivo_invalida"]}}
