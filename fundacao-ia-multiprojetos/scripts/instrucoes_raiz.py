#!/usr/bin/env python3
"""Instruções automáticas na raiz da fundação: AGENTS.md gerado e CLAUDE.md que o importa (análise do
vibe-coding-toolkit, 21/10/2026, proposta 1).

  gerar    --raiz <raiz> [--simular] [--adotar]
  conferir --raiz <raiz>                                 problema -> código 1

Sem esses arquivos, as regras de sessão só entram no contexto se a skill for acionada. O Claude Code carrega o
CLAUDE.md da pasta da sessão e das pastas acima (e `@AGENTS.md` dentro dele nunca duplica); o Codex lê AGENTS.md da
raiz do Git até a pasta atual (documentação conferida em 21/10/2026). O AGENTS.md é um RESUMO GERADO pela skill
(`assets/templates/AGENTS-RAIZ.md`; memórias nativas recebem só resumos gerados, capacidade 04): só o trecho
entre os marcadores da fundação é regenerado; o que estiver fora dele (o trecho do titular) é preservado.
AGENTS.md escrito à mão (sem os marcadores) não é sobrescrito: conflito, código 3, salvo `--adotar`, que o
guarda inteiro no trecho do titular.
CLAUDE.md ausente vira `@AGENTS.md`; existente ganha a linha `@AGENTS.md` no começo, se faltar, e mantém o resto.
Gravação sem seguir ligação nem vínculo físico (revisão de segurança da 1.7.7, R177-ATU-03): temporário de nome
imprevisível, criado com exclusividade e posto no lugar com `os.replace` (antes, `.AGENTS.md.tmp` tinha nome previsível
e um vínculo físico ali levava o texto gerado a um arquivo de fora); AGENTS.md ou CLAUDE.md que é ligação ou pasta
recusa, código 1, sem ler nem gravar nada.
Os arquivos orientam; os limites continuam nos hooks e nas permissões. As chamadas aos provedores rodam numa pasta
temporária vazia (adapters/cli.py) e não carregam estes arquivos.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:  # carregado por caminho (testes): o módulo vizinho também tem de ser achado
    sys.path.append(str(AQUI))
import gravacao_segura as gravacao  # noqa: E402  (sem seguir ligação nem vínculo físico; R177-ATU-03)

SKILL = Path(__file__).resolve().parents[1]
MODELO = SKILL / "assets" / "templates" / "AGENTS-RAIZ.md"
INICIO = "<!-- fundacao: início do trecho gerado pela skill; regenere com scripts/instrucoes_raiz.py gerar -->"
FIM = "<!-- fundacao: fim do trecho gerado -->"
TITULAR_INICIO = "<!-- titular: início — regras suas; a skill preserva este trecho -->"
TITULAR_FIM = "<!-- titular: fim -->"
IMPORTA = "@AGENTS.md"
LIMITE_DE_LINHAS = 200  # recomendação do Claude Code por arquivo de instruções


class Conflito(Exception):
    pass


class Recusa(Exception):
    """AGENTS.md ou CLAUDE.md da raiz é ligação ou pasta: nada é lido nem gravado por ele (R177-ATU-03)."""


def versao_da_skill() -> str:
    m = re.search(r'^\s*version:\s*"?([^"\s]+)"?\s*$', (SKILL / "SKILL.md").read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else "desconhecida"


def trecho_gerado(raiz: Path) -> str:
    texto = MODELO.read_text(encoding="utf-8")
    valores = {"RAIZ": str(raiz), "VERSAO": versao_da_skill()}  # sem nomes de projetos: também podem ser dado
    for chave, valor in valores.items():
        texto = texto.replace("{{" + chave + "}}", valor)
    return INICIO + "\n" + texto.rstrip("\n") + "\n" + FIM + "\n"


def agents_md(raiz: Path, atual: str | None, adotar: bool = False) -> str:
    """Só o trecho entre os marcadores da fundação muda; tudo o que está fora dele fica como estava."""
    gerado = trecho_gerado(raiz)
    if atual is None:
        return gerado + "\n" + TITULAR_INICIO + "\n" + TITULAR_FIM + "\n"
    if INICIO in atual and FIM in atual:
        antes, resto = atual.split(INICIO, 1)
        return antes + gerado.rstrip("\n") + resto.split(FIM, 1)[1]
    if not adotar:
        raise Conflito("AGENTS.md escrito à mão (sem os marcadores da skill): nada foi alterado. Revise e repita "
                       "com --adotar, que o guarda inteiro no trecho do titular")
    return gerado + "\n" + TITULAR_INICIO + "\n" + atual.strip("\n") + "\n" + TITULAR_FIM + "\n"


def claude_md(atual: str | None) -> str:
    if atual is None:
        return IMPORTA + "\n"
    if any(linha.strip() == IMPORTA for linha in atual.splitlines()):
        return atual
    return IMPORTA + "\n\n" + atual


def ler(p: Path) -> str | None:
    try:
        gravacao.conferir_destino(p)
    except gravacao.GravacaoRecusada:
        raise Recusa(p.name + " na raiz é ligação (link simbólico ou junção) ou pasta: nada foi lido nem alterado; "
                     "troque-o por um arquivo comum e repita") from None
    return p.read_text(encoding="utf-8") if p.is_file() else None


def gravar(p: Path, texto: str) -> None:
    gravacao.publicar(p, texto.encode("utf-8"))  # temporário imprevisível e exclusivo, depois os.replace


def gerar(raiz: Path, simular: bool = False, adotar: bool = False) -> dict:
    a_arq, c_arq = raiz / "AGENTS.md", raiz / "CLAUDE.md"
    a_atual, c_atual = ler(a_arq), ler(c_arq)
    a_novo, c_novo = agents_md(raiz, a_atual, adotar), claude_md(c_atual)
    res = {"raiz": str(raiz), "simulacao": simular}
    for nome, arq, atual, novo in (("agents", a_arq, a_atual, a_novo), ("claude", c_arq, c_atual, c_novo)):
        acao = "igual" if atual == novo else ("criar" if atual is None else "atualizar")
        if acao != "igual" and not simular:
            gravar(arq, novo)
        res[nome] = {"arquivo": str(arq), "acao": acao, "sha256": hashlib.sha256(novo.encode("utf-8")).hexdigest()}
    res["linhas_agents"] = len(a_novo.splitlines())
    return res


def conferir(raiz: Path) -> dict:
    problemas = []
    try:
        a_atual, c_atual = ler(raiz / "AGENTS.md"), ler(raiz / "CLAUDE.md")
    except Recusa as exc:
        return {"raiz": str(raiz), "ok": False, "problemas": [str(exc)]}
    if a_atual is None:
        problemas.append("AGENTS.md ausente na raiz")
    elif INICIO not in a_atual or FIM not in a_atual:
        problemas.append("AGENTS.md sem os marcadores da skill (escrito à mão)")
    elif a_atual.split(INICIO, 1)[1].split(FIM, 1)[0] != trecho_gerado(raiz).split(INICIO, 1)[1].split(FIM, 1)[0]:
        problemas.append("trecho gerado do AGENTS.md diferente do modelo atual (editado à mão ou skill nova)")
    elif len(a_atual.splitlines()) > LIMITE_DE_LINHAS:
        problemas.append(f"AGENTS.md com mais de {LIMITE_DE_LINHAS} linhas")
    if c_atual is None or not any(l.strip() == IMPORTA for l in c_atual.splitlines()):
        problemas.append("CLAUDE.md ausente ou sem a linha @AGENTS.md")
    return {"raiz": str(raiz), "ok": not problemas, "problemas": problemas}


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gerar")
    g.add_argument("--raiz", type=Path, required=True)
    g.add_argument("--simular", action="store_true", help="só mostra o que faria")
    g.add_argument("--adotar", action="store_true", help="guarda um AGENTS.md escrito à mão no trecho do titular")
    c = sub.add_parser("conferir")
    c.add_argument("--raiz", type=Path, required=True)
    args = ap.parse_args(argv)
    raiz = args.raiz.resolve()
    if args.cmd == "conferir":
        res = conferir(raiz)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0 if res["ok"] else 1
    try:
        res = gerar(raiz, args.simular, args.adotar)
    except Conflito as exc:
        print(json.dumps({"ok": False, "conflito": str(exc)}, ensure_ascii=False))
        return 3
    except (Recusa, gravacao.GravacaoRecusada) as exc:  # ligação no destino, ou que apareceu durante a gravação
        print(json.dumps({"ok": False, "erro": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, **res}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
