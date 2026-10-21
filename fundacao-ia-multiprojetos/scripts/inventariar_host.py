#!/usr/bin/env python3
"""Inventário do ecossistema do host: o que o Claude Code e o Codex carregam neste perfil (análise do
vibe-coding-toolkit, 21/10/2026, proposta 15; requisito R54).

  gravar    --saida <arquivo> [--perfil <pasta do usuário>] [--raiz <fundação>] [--substituir]
  verificar --inventario <arquivo> [--perfil ...] [--raiz ...]      diferenças -> código 1

Só lê, sem rede e sem executar nada. Skills: onde estão, se são ligação (e para onde), o `name` e a versão do
frontmatter, o SHA-256 do conteúdo e a primeira linha da licença; o mesmo `name` em pastas reais diferentes sai
em `duplicatas`. Plugins: id, versão e escopo; catálogos: a origem declarada. Hooks: evento, matcher,
executável e o SHA-256 dos scripts citados. Servidores MCP (Claude e Codex): só nome, tipo, executável (sem
caminho nem argumentos, mesmo num `command` em texto único) ou host da URL — NUNCA `env`, `headers`, argumentos ou dados da conta; .credentials.json
e auth.json não são abertos. Licença é fato observado, não parecer jurídico.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

RESTRICOES = ("all rights reserved", "additional restrictions")
SCRIPTS_DE_HOOK = (".py", ".ps1", ".sh", ".mjs", ".js", ".cmd", ".bat")
BARRA_INVERTIDA = chr(92)


def sha_arquivo(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sha_pasta(pasta: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(pasta.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
            h.update(p.relative_to(pasta).as_posix().encode("utf-8") + b"\0" + sha_arquivo(p).encode("ascii") + b"\n")
    return h.hexdigest()


def ligacao(p: Path) -> bool:
    """Link simbólico ou junção (sem segui-lo)."""
    try:
        st = os.lstat(p)
    except OSError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & 0x20000000)


def ler_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# Primeiro elemento de um `command` em texto único: entre aspas; caminho do Windows com espaços até o executável;
# ou a primeira palavra. O resto são argumentos, que podem trazer token (revisão de segurança da 1.7.0, VCT170-03).
PRIMEIRO_ELEMENTO = re.compile(r'\s*(?:"([^"]+)"|' + "'([^']+)'" + r'|([A-Za-z]:[\\/].*?\.(?:exe|cmd|bat|com))(?=\s|$)|(\S+))',
                               re.I)


def nome_do_executavel(comando: str) -> str | None:
    """Só o nome do executável, sem caminho nem argumentos."""
    m = PRIMEIRO_ELEMENTO.match(comando or "")
    primeiro = next((g for g in m.groups() if g), "") if m else ""
    return Path(primeiro.replace(BARRA_INVERTIDA, "/")).name or None


def frontmatter(texto: str) -> dict:
    linhas = texto.splitlines()
    if not linhas or linhas[0].strip() != "---":
        return {}
    campos = {}
    for linha in linhas[1:]:
        if linha.strip() == "---":
            break
        chave, _, valor = linha.strip().partition(":")
        if chave in ("name", "version") and valor.strip() and chave not in campos:
            campos[chave] = valor.strip().strip('"').strip("'")
    return campos


def licenca(pasta: Path) -> tuple[str | None, bool]:
    for nome in ("LICENSE.txt", "LICENSE", "LICENSE.md"):
        p = pasta / nome
        if p.is_file():
            texto = p.read_text(encoding="utf-8", errors="replace")
            primeira = next((l.strip() for l in texto.splitlines() if l.strip()), "")
            return primeira[:120], any(r in texto[:4000].lower() for r in RESTRICOES)
    return None, False


def skills(perfil: Path, raiz: Path | None) -> list[dict]:
    locais = [("perfil", perfil, ".claude/skills"), ("perfil", perfil, ".agents/skills"),
              ("perfil", perfil, ".codex/skills")] + ([("raiz", raiz, ".claude/skills")] if raiz else [])
    out = []
    for origem, base, rel in locais:
        pasta = base / rel
        if not pasta.is_dir():
            continue
        for item in sorted(pasta.iterdir()):
            if not (item / "SKILL.md").is_file():
                continue
            fm = frontmatter((item / "SKILL.md").read_text(encoding="utf-8", errors="replace"))
            primeira, restritiva = licenca(item)
            eh_ligacao = ligacao(item)
            out.append({"local": f"{origem}:{rel}/{item.name}", "nome": fm.get("name") or item.name,
                        "versao": fm.get("version"), "ligacao": eh_ligacao,
                        "alvo": str(item.resolve()) if eh_ligacao else None, "_real": str(item.resolve()),
                        "sha256": sha_pasta(item), "licenca": primeira, "licenca_restritiva_declarada": restritiva})
    return out


def duplicatas(lista: list[dict]) -> list[dict]:
    """Mesmo `name` em pastas reais diferentes (a ligação para a mesma pasta não conta)."""
    por_nome: dict[str, dict[str, str]] = {}
    for s in lista:
        por_nome.setdefault(s["nome"], {}).setdefault(os.path.normcase(s["_real"]), s["local"])
    return [{"nome": n, "locais": sorted(reais.values())} for n, reais in sorted(por_nome.items()) if len(reais) > 1]


def plugins(perfil: Path) -> list[dict]:
    dados = ler_json(perfil / ".claude" / "plugins" / "installed_plugins.json") or {}
    out = []
    for pid, instalacoes in sorted((dados.get("plugins") or {}).items()):
        for inst in instalacoes if isinstance(instalacoes, list) else []:
            if isinstance(inst, dict):
                out.append({"id": pid, "versao": inst.get("version"), "escopo": inst.get("scope"),
                            "com_projeto": bool(inst.get("projectPath"))})  # o caminho pode trazer nome de cliente
    return out


def catalogos(perfil: Path) -> list[dict]:
    dados = ler_json(perfil / ".claude" / "plugins" / "known_marketplaces.json") or {}
    out = []
    for nome, cfg in sorted(dados.items()):
        fonte = cfg.get("source") if isinstance(cfg, dict) else None
        fonte = fonte if isinstance(fonte, dict) else {}
        out.append({"nome": nome, "tipo": fonte.get("source"), "repo": fonte.get("repo"),
                    "host": urlsplit(str(fonte["url"])).hostname if fonte.get("url") else None})
    return out


def _mcp(cliente: str, nome: str, cfg: dict, onde: str) -> dict:
    item = {"cliente": cliente, "nome": nome, "onde": onde,
            "tipo": cfg.get("type") or ("http" if cfg.get("url") else "stdio")}
    if cfg.get("command"):
        item["executavel"] = nome_do_executavel(str(cfg["command"]))
    if cfg.get("url"):
        item["host"] = urlsplit(str(cfg["url"])).hostname
    return item


def mcp(perfil: Path, raiz: Path | None) -> list[dict]:
    out = []
    claude = ler_json(perfil / ".claude.json") or {}
    for nome, cfg in sorted((claude.get("mcpServers") or {}).items()):
        if isinstance(cfg, dict):
            out.append(_mcp("claude", nome, cfg, "usuario"))
    if raiz:
        alvo = os.path.normcase(str(raiz.resolve()))
        for caminho, proj in (claude.get("projects") or {}).items():
            if isinstance(proj, dict) and os.path.normcase(str(Path(caminho).resolve())) == alvo:
                for nome, cfg in sorted((proj.get("mcpServers") or {}).items()):
                    if isinstance(cfg, dict):
                        out.append(_mcp("claude", nome, cfg, "projeto"))
        for nome, cfg in sorted(((ler_json(raiz / ".mcp.json") or {}).get("mcpServers") or {}).items()):
            if isinstance(cfg, dict):
                out.append(_mcp("claude", nome, cfg, ".mcp.json"))
    toml = perfil / ".codex" / "config.toml"
    if toml.is_file():
        try:
            dados = tomllib.loads(toml.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            dados = {}
        for nome, cfg in sorted((dados.get("mcp_servers") or {}).items()):
            if isinstance(cfg, dict):
                out.append(_mcp("codex", nome, cfg, "config.toml"))
    return out


def hooks(perfil: Path, raiz: Path | None) -> list[dict]:
    arquivos = [("perfil", perfil, perfil / ".claude" / "settings.json")]
    if raiz:
        arquivos += [("raiz", raiz, raiz / ".claude" / n) for n in ("settings.json", "settings.local.json",
                                                                     "settings.wsl.json")]
    out = []
    for origem, base, arq in arquivos:
        for evento, grupos in sorted(((ler_json(arq) or {}).get("hooks") or {}).items()):
            for grupo in grupos if isinstance(grupos, list) else []:
                for h in (grupo.get("hooks") or []) if isinstance(grupo, dict) else []:
                    if not isinstance(h, dict):
                        continue
                    comando = str(h.get("command") or "")
                    partes = [comando, *map(str, h.get("args") or [])] if h.get("args") else comando.split()
                    scripts = []
                    for parte in partes:
                        p = Path(parte.strip('"').replace(BARRA_INVERTIDA, "/"))
                        p = p if p.is_absolute() else base / p
                        if p.suffix.lower() in SCRIPTS_DE_HOOK and p.is_file():
                            scripts.append({"caminho": str(p), "sha256": sha_arquivo(p)})
                    out.append({"origem": f"{origem}:{arq.name}", "evento": evento, "matcher": grupo.get("matcher"),
                                "executavel": nome_do_executavel(partes[0]) if partes else None, "scripts": scripts})
    return out


def inventario(perfil: Path, raiz: Path | None) -> dict:
    lista = skills(perfil, raiz)
    inv = {"schema_version": "fundacao.inventario-host/1",
           "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "perfil": str(perfil), "raiz": str(raiz) if raiz else None,
           "skills": lista, "duplicatas": duplicatas(lista), "plugins": plugins(perfil),
           "catalogos": catalogos(perfil), "mcp": mcp(perfil, raiz), "hooks": hooks(perfil, raiz),
           "observacao": "Licença é fato observado (primeira linha do arquivo), não parecer jurídico."}
    for s in inv["skills"]:
        s.pop("_real", None)
    return inv


def chaves(inv: dict) -> dict:
    return {"skills": {s["local"]: s for s in inv["skills"]},
            "plugins": {f"{p['id']}|{p.get('escopo')}|{p.get('com_projeto')}": p for p in inv["plugins"]},
            "catalogos": {c["nome"]: c for c in inv["catalogos"]},
            "mcp": {f"{m['cliente']}|{m['onde']}|{m['nome']}": m for m in inv["mcp"]},
            "hooks": {f"{h['origem']}|{h['evento']}|{h['matcher']}|{i}": h for i, h in enumerate(inv["hooks"])}}


def diferencas(antes: dict, agora: dict) -> dict:
    a, b = chaves(antes), chaves(agora)
    return {cat: {"adicionados": sorted(set(b[cat]) - set(a[cat])), "removidos": sorted(set(a[cat]) - set(b[cat])),
                  "alterados": sorted(k for k in set(a[cat]) & set(b[cat]) if a[cat][k] != b[cat][k])}
            for cat in a}


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gravar")
    g.add_argument("--saida", type=Path, required=True)
    g.add_argument("--substituir", action="store_true", help="regrava um inventário existente")
    v = sub.add_parser("verificar")
    v.add_argument("--inventario", type=Path, required=True)
    for p in (g, v):
        p.add_argument("--perfil", type=Path, default=None, help="pasta do usuário (padrão: a deste usuário)")
        p.add_argument("--raiz", type=Path, default=None, help="raiz da fundação (hooks, skills e MCP do projeto)")
    args = ap.parse_args(argv)
    if args.cmd == "gravar":
        if args.saida.exists() and not args.substituir:
            print(json.dumps({"ok": False, "erro": f"{args.saida} já existe; use --substituir para regravar"},
                             ensure_ascii=False))
            return 1
        perfil = (args.perfil or Path.home()).resolve()
        inv = inventario(perfil, args.raiz.resolve() if args.raiz else None)
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(json.dumps(inv, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "inventario": str(args.saida), "skills": len(inv["skills"]),
                          "duplicatas": inv["duplicatas"], "plugins": len(inv["plugins"]), "mcp": len(inv["mcp"]),
                          "hooks": len(inv["hooks"]), "licencas_restritivas_declaradas": sorted(
                              s["local"] for s in inv["skills"] if s["licenca_restritiva_declarada"])},
                         ensure_ascii=False, indent=1))
        return 0
    antes = ler_json(args.inventario)
    if not isinstance(antes, dict):
        print(json.dumps({"ok": False, "erro": "inventário ausente ou ilegível"}, ensure_ascii=False))
        return 1
    perfil = (args.perfil or Path(antes.get("perfil") or Path.home())).resolve()
    raiz = args.raiz or (Path(antes["raiz"]) if antes.get("raiz") else None)
    dif = diferencas(antes, inventario(perfil, raiz.resolve() if raiz else None))
    mudou = any(lista for cat in dif.values() for lista in cat.values())
    print(json.dumps({"ok": not mudou, "diferencas": dif}, ensure_ascii=False, indent=1))
    return 1 if mudou else 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
