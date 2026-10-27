#!/usr/bin/env python3
"""Confere se os arquivos citados nos Markdown de uma skill/fundação existem.

Verifica: links Markdown relativos `[texto](caminho)`; caminhos em código ou em texto
corrido começando por `references/`, `scripts/`, `assets/` ou `evals/`; e caminhos
relativos em código (`../fluxo-c-operar.md`, `capacidades/04-memoria.md`).
`<skill>/...` (pasta desta skill) é conferido em qualquer lugar, também dentro de comandos, e só
a partir da raiz da skill. Todo caminho é conferido com a grafia exata (maiúsculas e minúsculas).
Convenção da skill: arquivo da própria skill é sempre citado com caminho; nome solto
(`RETOMADA.md`, `relato.md`) designa artefato da fundação do usuário e não é exigido
aqui. Caminhos são resolvidos a partir do arquivo que cita, da raiz e de `references/`.
No pacote instalável (sem `evals/`), citações a `evals/...` são listadas à parte
("fora_do_pacote_instalavel"), não como ausência.
Comandos citados (`python <skill>/scripts/X.py ...`, `python -m fundacao ...`) são conferidos contra o
argparse do script, lido pela árvore sintática sem executar nada: subcomando, ação e opção inexistentes ou
abreviadas saem em "comandos_com_problema" (proposta 8 da análise do vibe-coding-toolkit, 21/10/2026).

Uso: python verificar_referencias.py [--raiz DIR]   (ausências -> código 1)
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shlex
import sys
from pathlib import Path

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
CODE = re.compile(r"`([^`\s]+)`")
# Sem a crase no lookbehind: os trechos de código SEM espaço já saíram do texto (CODE.sub), e os
# que sobram (comandos com espaços) podem começar direto no caminho, como `scripts/x.py criar`.
PLAIN_PATH = re.compile(r"(?<![\w/.-])((?:references|scripts|assets|evals)/[A-Za-z0-9_./\-]*[A-Za-z0-9_\-])")
PREFIXED = re.compile(r"^(?:\.\./)*(?:references|scripts|assets|evals|capacidades|livro)/[A-Za-z0-9_./\-]+$")
RELATIVE = re.compile(r"^(?:\.\./)+[A-Za-z0-9_./\-]+\.(?:md|py|json|csv)$")
IGNORE_PREFIX = ("http://", "https://", "mailto:", "#")
# `<skill>/…` aponta para esta skill: conferido qualquer que seja a primeira pasta (um erro em
# `script/` no lugar de `scripts/` também precisa aparecer).
SKILL_REF = re.compile(r"<skill>/([A-Za-z0-9_./\-]*[A-Za-z0-9_\-])")


def candidates(root: Path, md: Path, target: str) -> list[tuple[Path, str]]:
    return [(md.parent, target), (root, target), (root / "references", target)]


def existe_exato(base: Path, rel: str) -> bool:
    """O caminho existe com a grafia exata de cada parte. No Windows e no macOS o sistema de
    arquivos não distingue maiúsculas, mas o pacote pode ir para um que distingue (Linux)."""
    atual = base
    for parte in (p for p in rel.split("/") if p and p != "."):
        if parte == "..":
            atual = atual.parent
            continue
        try:
            if parte not in os.listdir(atual):
                return False
        except OSError:
            return False
        atual = atual / parte
    return atual.exists()


# --- Comandos citados conferidos contra o argparse (análise do vibe-coding-toolkit, 21/10/2026, proposta 8) ---
# 10 das 66 intervenções do titular na implantação vieram de instruções que não rodavam como escritas. Cada
# `python <skill>/scripts/X.py ...` e `python -m fundacao ...` citado é conferido contra o argparse do script,
# lido pela árvore sintática (nada é executado): subcomando, ação (choices) e opção precisam existir, com o nome
# inteiro. Parser montado de forma dinâmica (nome em variável) não é conferido e sai em `scripts_nao_conferidos`.
COMANDO = re.compile(r"\bpython3?(?:\s+-[A-Za-z]+)*\s+(?:(?:<skill>/)?scripts/(?P<script>[A-Za-z0-9_]+\.py)"
                     r"|-m\s+fundacao)(?=[\s`]|$)(?P<resto>[^`\n]*)")
SEM_VALOR = {"store_true", "store_false", "count", "help", "version", "store_const", "append_const"}
CLI_DO_KIT = Path("assets") / "fundacao-kit" / "fundacao" / "__main__.py"


class Parser:
    def __init__(self) -> None:
        self.opcoes: dict[str, bool] = {"-h": False, "--help": False}  # opção -> recebe valor?
        self.posicionais: list[list[str] | None] = []                   # choices de cada posicional
        self.subcomandos: dict[str, "Parser"] = {}
        self.tem_subcomandos = False
        self.dinamico = False


def _texto(no) -> str | None:
    return no.value if isinstance(no, ast.Constant) and isinstance(no.value, str) else None


def _textos(no) -> list[str] | None:
    if isinstance(no, (ast.List, ast.Tuple)):
        valores = [_texto(e) for e in no.elts]
        return valores if all(v is not None for v in valores) else None
    return None


def _kw(chamada: ast.Call, nome: str):
    return next((k.value for k in chamada.keywords if k.arg == nome), None)


def _argumento(parser: Parser, chamada: ast.Call) -> None:
    nomes = [_texto(a) for a in chamada.args]
    if not nomes or None in nomes:
        parser.dinamico = True
        return
    acao = _texto(_kw(chamada, "action"))
    nargs = _kw(chamada, "nargs")
    recebe = acao not in SEM_VALOR and not (isinstance(nargs, ast.Constant) and nargs.value == 0)
    if nomes[0].startswith("-"):
        parser.opcoes.update(dict.fromkeys(nomes, recebe))
    else:
        choices = _kw(chamada, "choices")
        parser.posicionais.append(_textos(choices) if choices is not None else None)


def estrutura_argparse(caminho: Path) -> Parser | None:
    """O parser principal do script (o primeiro ArgumentParser atribuído a uma variável), ou None."""
    try:
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return None
    auxiliares: dict[str, list[tuple[int, ast.Call]]] = {}  # def f(p): p.add_argument(...)
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef):
            params = [a.arg for a in no.args.args]
            chamadas = [(params.index(n.func.value.id), n) for n in ast.walk(no)
                        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                        and n.func.attr == "add_argument" and isinstance(n.func.value, ast.Name)
                        and n.func.value.id in params]
            if chamadas:
                auxiliares[no.name] = chamadas
    principais: list[Parser] = []

    def chamada(no, env):
        if not isinstance(no, ast.Call):
            return env.get(no.id) if isinstance(no, ast.Name) else None
        f = no.func
        if (isinstance(f, ast.Attribute) and f.attr == "ArgumentParser") or \
                (isinstance(f, ast.Name) and f.id == "ArgumentParser"):
            return Parser()
        if isinstance(f, ast.Name) and f.id in auxiliares:
            for indice, interna in auxiliares[f.id]:
                alvo = chamada(no.args[indice], env) if indice < len(no.args) else None
                if isinstance(alvo, Parser):
                    _argumento(alvo, interna)
            return None
        if not isinstance(f, ast.Attribute):
            return None
        alvo = chamada(f.value, env)
        if isinstance(alvo, Parser):
            if f.attr == "add_subparsers":
                alvo.tem_subcomandos = True
                return ("subcomandos", alvo)
            if f.attr in ("add_argument_group", "add_mutually_exclusive_group"):
                return alvo
            if f.attr == "add_argument":
                _argumento(alvo, no)
        elif isinstance(alvo, tuple) and f.attr == "add_parser":
            nome, filho = (_texto(no.args[0]) if no.args else None), Parser()
            if nome is None:
                alvo[1].dinamico = True
            else:
                for n in [nome, *(_textos(_kw(no, "aliases")) or [])]:
                    alvo[1].subcomandos[n] = filho
            return filho
        return None

    def visitar(corpo, env):
        for st in corpo:
            if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
                valor = chamada(st.value, env)
                env[st.targets[0].id] = valor
                if isinstance(valor, Parser) and not principais and isinstance(st.value, ast.Call) \
                        and getattr(st.value.func, "attr", getattr(st.value.func, "id", "")) == "ArgumentParser":
                    principais.append(valor)
            elif isinstance(st, ast.Expr):
                chamada(st.value, env)
            elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visitar(st.body, {})
            else:
                for campo in ("body", "orelse", "finalbody"):
                    visitar(getattr(st, campo, []) or [], env)
                for tratador in getattr(st, "handlers", []) or []:
                    visitar(tratador.body, env)

    visitar(arvore.body, {})
    if not principais:
        return None
    raiz = principais[0]
    # Extensões da CLI do kit: `for m in (cli_a, cli_b): m.registrar_parser(sub)` acrescenta subcomandos que a
    # leitura acima não acompanha. Lê o `registrar_parser` só dos módulos desse laço (1.7.9, R179-37).
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.For) and isinstance(no.iter, (ast.Tuple, ast.List)) and raiz.tem_subcomandos
                and any(isinstance(n, ast.Attribute) and n.attr == "registrar_parser" for n in ast.walk(no))):
            continue
        for elemento in no.iter.elts:
            try:
                modulo = ast.parse((caminho.parent / (elemento.id + ".py")).read_text(encoding="utf-8"))
            except (AttributeError, OSError, SyntaxError, ValueError):
                raiz.dinamico = True  # extensão que não dá para ler: o subcomando dela não é conferido
                continue
            for funcao in modulo.body:
                if isinstance(funcao, ast.FunctionDef) and funcao.name == "registrar_parser" and funcao.args.args:
                    visitar(funcao.body, {funcao.args.args[0].arg: ("subcomandos", raiz)})
    return raiz


def _fichas(resto: str) -> list[str]:
    for corte in (" #", "&&", ";"):
        resto = resto.split(corte, 1)[0]
    try:
        fichas = shlex.split(resto, posix=True)
    except ValueError:
        fichas = resto.split()
    return [f.strip("[]()") for f in fichas if f.strip("[]()") not in ("", "\\")]


def _valor(ficha: str) -> bool:
    return any(c in ficha for c in "<>{}*") or "..." in ficha or "…" in ficha


def conferir_comando(parser: Parser, fichas: list[str]) -> list[tuple[str, str]]:
    """Problemas de um comando citado: (ficha, problema). Opção global vale só antes do subcomando."""
    problemas, atual, posicao, alternativa, pular = [], parser, 0, False, False
    for ficha in fichas:
        if pular:
            pular = False
            continue
        if ficha == "--":
            break
        if ficha == "|":
            alternativa = True
            continue
        if ficha.startswith("--") and len(ficha) > 2:
            for opcao in ficha.split("|"):
                nome = opcao.split("=", 1)[0].rstrip(".,:")
                if atual.dinamico or nome in atual.opcoes:
                    pular = atual.opcoes.get(nome, False) and "=" not in opcao and "|" not in ficha
                    continue
                candidatas = [o for o in atual.opcoes if o.startswith(nome)]
                problemas.append((nome, f"opção abreviada (use {candidatas[0]})" if len(candidatas) == 1
                                  else "opção inexistente"))
            continue
        if ficha.startswith("-") or _valor(ficha) or atual.dinamico:
            continue
        nomes = ficha.split("|")
        if atual.tem_subcomandos and posicao == 0 and not atual.posicionais:
            problemas += [(n, "subcomando inexistente") for n in nomes if n not in atual.subcomandos]
            validos = [n for n in nomes if n in atual.subcomandos]
            if not validos:
                break  # subcomando desconhecido: o resto do comando não é conferível
            atual, posicao, alternativa = atual.subcomandos[validos[0]], 0, False
            continue
        indice = posicao - 1 if alternativa and posicao else posicao
        if indice < len(atual.posicionais) and atual.posicionais[indice]:
            problemas += [(n, "ação inexistente") for n in nomes if n not in atual.posicionais[indice]]
        if not alternativa:
            posicao += 1
        alternativa = False
    return problemas


def conferir_comandos(root: Path) -> dict:
    estruturas: dict[str, Parser | None] = {}
    conferidos, com_problema, nao_conferidos = 0, [], set()
    for md in sorted(root.rglob("*.md")):
        rel_md = md.relative_to(root)
        if rel_md.parts[0] in ("evals", "__pycache__"):
            continue
        for m in COMANDO.finditer(md.read_text(encoding="utf-8")):
            chave = m.group("script") or "-m fundacao"
            if chave not in estruturas:
                alvo = root / "scripts" / chave if m.group("script") else root / CLI_DO_KIT
                estruturas[chave] = estrutura_argparse(alvo) if alvo.is_file() else None
            parser = estruturas[chave]
            if parser is None:
                nao_conferidos.add(chave)
                continue
            conferidos += 1
            for ficha, problema in conferir_comando(parser, _fichas(m.group("resto"))):
                com_problema.append({"arquivo": rel_md.as_posix(), "comando": m.group(0).strip()[:160],
                                     "opcao": ficha, "problema": problema})
    return {"comandos_conferidos": conferidos, "comandos_com_problema": com_problema,
            "scripts_nao_conferidos": sorted(nao_conferidos)}


def check(root: Path) -> dict:
    missing, checked, outside = [], 0, []
    has_evals = (root / "evals").is_dir()
    for md in sorted(root.rglob("*.md")):
        rel_md = md.relative_to(root)
        if any(part in ("evals", "__pycache__") for part in rel_md.parts[:1]):
            continue
        # `<skill>/` = pasta desta skill: some antes da busca, para que `<skill>/scripts/x.py` seja
        # conferido em qualquer lugar — trecho de código, comando com espaços ou bloco de código.
        original = md.read_text(encoding="utf-8")
        text = original.replace("<skill>/", "")
        da_skill = {m.group(1) for m in SKILL_REF.finditer(original)}  # resolvidos só pela raiz
        targets = sorted(da_skill)
        targets += [m.group(1) for m in LINK.finditer(text)]
        for m in CODE.finditer(text):
            t = m.group(1).rstrip(".,;:)")
            if PREFIXED.match(t) or RELATIVE.match(t):
                targets.append(t)
        targets += [m.group(1).rstrip(".") for m in PLAIN_PATH.finditer(CODE.sub(" ", text))]
        seen = set()
        for target in targets:
            if target in seen:
                continue
            seen.add(target)
            if target.startswith(IGNORE_PREFIX) or any(ch in target for ch in "<{*") or "..." in target:
                continue
            clean = target.split("#", 1)[0]
            if not clean:
                continue
            if clean.startswith("evals/") and not has_evals:
                # Pacote instalável (.skill) não leva evals/: a citação vale para o pacote completo.
                outside.append({"arquivo": rel_md.as_posix(), "referencia": target})
                continue
            checked += 1
            onde = [(root, clean)] if target in da_skill else candidates(root, md, clean)
            if not any(existe_exato(base, rel) for base, rel in onde):
                missing.append({"arquivo": rel_md.as_posix(), "referencia": target})
    comandos = conferir_comandos(root)
    return {"ok": not missing and not comandos["comandos_com_problema"], "referencias_conferidas": checked,
            "ausentes": missing, "fora_do_pacote_instalavel": outside, **comandos}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args()
    result = check(args.raiz.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
