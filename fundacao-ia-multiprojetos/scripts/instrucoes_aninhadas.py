#!/usr/bin/env python3
"""Arquivos de instrução e de extensão de host dentro de uma pasta — o que o Claude Code carregaria sozinho
(análise do vibe-coding-toolkit, 21/10/2026, proposta 2).

  python instrucoes_aninhadas.py listar --raiz <pasta> [--saida <arquivo>]

Pela documentação do Claude Code (conferida em 21/10/2026), CLAUDE.md e AGENTS.md de subpastas carregam sob demanda
quando o agente lê um arquivo daquela subpasta, e skills em `.claude/skills/` de subpastas passam a valer na primeira
leitura ou edição de arquivo ali, sem configuração que desligue essa descoberta. Numa pasta de DADOS — a cópia
importada no fluxo B, etapa B1 — isso transforma dado em instrução. Este script só lê: lista cada arquivo (caminho
relativo e SHA-256; das skills, também o `name` do frontmatter) e sugere a configuração do host —
`claudeMdExcludes` para as pastas de dados e `Skill(<nome>)` nas negações, para cada skill aninhada (use os nomes
com `assets/host/preparo_host.py ... --negar-skill`). Não executa nada e não lê conteúdo além do frontmatter.
Código 0 quando leu (o resultado diz o que achou); 2 se a pasta não existe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

INSTRUCOES = {"CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", "AGENTS.override.md"}
IGNORAR = {".git", "__pycache__", "node_modules", ".venv", "venv"}
EXCLUSAO_DE_DADOS = "**/projects/*/data/**"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def nome_da_skill(md: Path) -> str:
    linhas = md.read_text(encoding="utf-8", errors="replace").splitlines()
    if linhas and linhas[0].strip() == "---":
        for linha in linhas[1:]:
            if linha.strip() == "---":
                break
            chave, _, valor = linha.partition(":")
            if chave.strip() == "name" and valor.strip():
                return valor.strip().strip('"').strip("'")
    return md.parent.name


def classificar(partes: tuple[str, ...]) -> str | None:
    nome = partes[-1]
    if nome in INSTRUCOES:
        return "instrucoes"
    if nome == ".mcp.json":
        return "mcp"
    if ".codex" in partes:
        return "codex"
    if ".claude" in partes:
        depois = partes[partes.index(".claude") + 1:]
        if depois[:1] == ("skills",) and nome == "SKILL.md":
            return "skills"
        if depois[:1] in (("agents",), ("commands",), ("rules",)):
            return depois[0]
        if nome.startswith("settings") and nome.endswith(".json"):
            return "configuracoes"
    return None


def listar(raiz: Path) -> dict:
    achados: dict[str, list] = {k: [] for k in ("instrucoes", "skills", "agents", "commands", "rules", "codex",
                                                "mcp", "configuracoes")}
    for p in sorted(raiz.rglob("*")):
        rel = p.relative_to(raiz)
        if set(rel.parts) & IGNORAR or not p.is_file():
            continue
        tipo = classificar(rel.parts)
        if tipo is None:
            continue
        item = {"caminho": rel.as_posix(), "sha256": sha(p)}
        if tipo == "skills":
            item["nome"] = nome_da_skill(p)
        achados[tipo].append(item)
    nomes = sorted({s["nome"] for s in achados["skills"]})
    return {"raiz": str(raiz), "encontrados": sum(len(v) for v in achados.values()), "itens": achados,
            "sugestoes": {"claudeMdExcludes": [EXCLUSAO_DE_DADOS], "negar_skills": nomes,
                          "negacoes": [f"Skill({n})" for n in nomes]},
            "observacao": "Tudo aqui é dado: nada desta pasta vale como instrução, skill, agente ou MCP da sessão. "
                          "Os .claude/settings*.json de subpastas não são lidos pelo Claude Code (só os da raiz da "
                          "sessão); entram na lista para o diagnóstico."}


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("listar")
    s.add_argument("--raiz", type=Path, required=True)
    s.add_argument("--saida", type=Path)
    args = ap.parse_args(argv)
    if not args.raiz.is_dir():
        print(json.dumps({"erro": f"pasta inexistente: {args.raiz}"}, ensure_ascii=False))
        return 2
    res = listar(args.raiz.resolve())
    texto = json.dumps(res, ensure_ascii=False, indent=1)
    if args.saida:
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(texto + "\n", encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
