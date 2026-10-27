#!/usr/bin/env python3
"""Inventário do ecossistema do host: o que o Claude Code e o Codex carregam neste perfil (análise do
vibe-coding-toolkit, 21/10/2026, proposta 15; requisito R54).

  gravar    --saida <arquivo> [--perfil <pasta do usuário>] [--raiz <fundação>] [--substituir]
  verificar --inventario <arquivo> [--perfil ...] [--raiz ...]      diferenças -> código 1

Só lê, sem rede e sem executar nada do que inventaria (a expressão de um matcher é avaliada num subprocesso Python
isolado, com tempo limite: `alertas_hooks.py`). Skills: onde estão, se são ligação (e para onde), o `name` e a versão do
frontmatter, o SHA-256 do conteúdo e a primeira linha da licença; o mesmo `name` em pastas reais diferentes sai
em `duplicatas`. Plugins: id, versão e escopo; catálogos: a origem declarada. Hooks: evento, matcher,
executável e o SHA-256 dos scripts citados. Servidores MCP (Claude e Codex): só nome, tipo, executável (sem
caminho nem argumentos, mesmo num `command` em texto único) ou host da URL — NUNCA `env`, `headers`, argumentos ou dados da conta; .credentials.json
e auth.json não são abertos. O executável é só um nome (letras, dígitos, `_`, `.`, `+`, `-`): o que não tem essa forma,
como `$env:NOME='valor';`, sai nulo (revisão de segurança da 1.7.7, R177-VAL-05). Licença é fato observado, não parecer
jurídico.
Esquema 2 (análise do everything-claude-code, 21/10/2026, proposta 1): os plugins também por dentro — hooks, MCP e
skills de cada plugin instalado ou sincronizado, lidos só dentro de `~/.claude/plugins/` (`inventario_plugins.py`) —
e os alertas de matcher e de evento de todos os hooks (`alertas_hooks.py`). O `verificar` acusa hook acrescentado.
O matcher é avaliado e comparado inteiro e cru; dos hooks de plugin o inventário guarda a cópia de exibição (até 200
caracteres, com caractere de controle e surrogate trocados por espaço) e o SHA-256 do inteiro cru (revisão de segurança
da 1.7.7, R177-VAL-03; o cru, na segunda passada, R177B-A-01).
JSON do perfil e da raiz, o TOML do Codex e o próprio inventário relido pelo `verificar` passam pela leitura de
`inventario_plugins.decodificar`: mais de 100 níveis de lista e objeto, ou o aninhamento que estoura o limite de
recursão, valem como o arquivo ilegível — antes, o `RecursionError` (e o valor de 1500 níveis no `json.dumps` com
recuo) fazia o `gravar` e o `verificar` saírem com 1, sem saída (revisão de segurança da 1.7.7, terceira passada,
R177C-B-02). A forma também é conferida, com as `FORMAS` do `inventario_plugins.py` (um lugar só): lista no topo,
`"hooks": [..]`, `"mcpServers": [..]`, o `args` de um hook como número ou o `mcp_servers` do Codex como texto
derrubavam o `gravar` e o `verificar` (AttributeError, TypeError); agora o arquivo do perfil ou da raiz que foge da
forma, ilegível ou aninhado demais vai para `arquivos_nao_lidos`, com a origem e o motivo, e o `verificar` acusa
quando isso muda; o inventário relido de forma inesperada sai com 1 e o motivo (terceira passada, R177C-B-02, tipo
inesperado). Só a parte fora da forma fica de fora (`inventario_plugins.podar`), o resto é lido, e o registro de "não
lido" guarda o SHA-256 do arquivo, que entra na chave do `verificar`: descartar o arquivo inteiro e comparar só a
origem e o motivo deixava passar um hook com `curl`, um servidor MCP novo ou o matcher trocado para `.*` no mesmo
arquivo (quarta passada, R177D-3).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
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
ESQUEMA, ESQUEMA_1 = "fundacao.inventario-host/2", "fundacao.inventario-host/1"
CAMPOS_NOVOS = ("tipo", "matcher_tipo")  # registrados nos hooks a partir do esquema 2


def _vizinho(nome: str):
    """Módulo da mesma pasta, carregado pelo caminho e não pelo `sys.path` (vale também com `python -P` ou `-I`)."""
    spec = importlib.util.spec_from_file_location(nome, Path(__file__).resolve().with_name(nome + ".py"))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


PLUGINS, ALERTAS = _vizinho("inventario_plugins"), _vizinho("alertas_hooks")


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


def ler_json(p: Path, forma=None, origem: str | None = None, nao_lidos: list | None = None, carregar=json.loads,
             formato: str = "JSON"):
    """JSON (ou TOML, com `carregar`) do perfil, da raiz ou do inventário — só as partes na `forma` —, ou None. Ausente
    dá None sem anotação; ilegível, aninhado demais (o `RecursionError` derrubava o inventário: R177C-B-02) ou com parte
    fora da `forma` (R177C-B-02, tipo inesperado) é anotado em `nao_lidos`, quando dada, com a origem, o motivo e o
    SHA-256 do arquivo, que o `verificar` compara (quarta passada, R177D-3)."""
    sha = None
    try:
        bruto = p.read_bytes()
    except (FileNotFoundError, NotADirectoryError):
        return None
    except (OSError, ValueError):
        motivo = f"{formato} ilegível"
    else:
        sha = hashlib.sha256(bruto).hexdigest()
        try:
            dados = PLUGINS.decodificar(bruto.decode("utf-8"), carregar)
        except PLUGINS.AninhadoDemais:
            motivo = f"{formato} aninhado demais"
        except ValueError:
            motivo = f"{formato} ilegível"
        else:
            podado, erros = PLUGINS.podar(dados, forma)
            if not erros:
                return dados
            motivo = PLUGINS.motivo_da_forma(formato, podado, erros)
            dados = None if podado is PLUGINS.REMOVIDO else podado  # só a parte fora da forma fica de fora (R177D-3)
            if nao_lidos is not None:
                nao_lidos.append({"origem": origem, "motivo": motivo, "sha256": sha})
            return dados
    if nao_lidos is not None:
        nao_lidos.append({"origem": origem, "motivo": motivo, **({"sha256": sha} if sha else {})})
    return None


def host_da_url(url) -> str | None:
    """Só o host da URL; a malformada (colchete aberto, caractere que a normalização recusa) dá None em vez de
    derrubar o inventário com `ValueError` (revisão de segurança da 1.7.7, R177-VAL-04)."""
    try:
        return urlsplit(str(url)).hostname
    except ValueError:
        return None


# Primeiro elemento de um `command` em texto único: entre aspas; caminho do Windows com espaços até o executável;
# ou a primeira palavra. O resto são argumentos, que podem trazer token (revisão de segurança da 1.7.0, VCT170-03).
PRIMEIRO_ELEMENTO = re.compile(r'\s*(?:"([^"]+)"|' + "'([^']+)'" + r'|([A-Za-z]:[\\/].*?\.(?:exe|cmd|bat|com))(?=\s|$)|(\S+))',
                               re.I)
# `VAR=valor` antes do executável (forma de shell) também pode trazer token (everything-claude-code, proposta 1).
ATRIBUICOES = re.compile(r"""\A\s*(?:[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|'[^']*'|\S*)(?:\s+|$))+""")
# O que sobra só vale se for nome de executável: a atribuição do PowerShell (`$env:NOME='valor';`), um `&` ou uma
# opção com `=` viram nulo, não texto do comando (revisão de segurança da 1.7.7, R177-VAL-05).
NOME_DE_EXECUTAVEL = re.compile(r"[\w.+-]+")


def nome_do_executavel(comando: str) -> str | None:
    """Só o nome do executável, sem caminho, argumentos nem `VAR=valor` antes dele; fora desse formato, None."""
    m = PRIMEIRO_ELEMENTO.match(ATRIBUICOES.sub("", comando or "", count=1))
    primeiro = next((g for g in m.groups() if g), "") if m else ""
    nome = Path(primeiro.replace(BARRA_INVERTIDA, "/")).name
    return nome if NOME_DE_EXECUTAVEL.fullmatch(nome) else None


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
    # Fora da forma, o leitor dos plugins anota o arquivo em `plugins_nao_lidos`; aqui ele só não entra (R177C-B-02).
    dados = ler_json(perfil / ".claude" / "plugins" / "installed_plugins.json",
                     PLUGINS.FORMAS["installed_plugins.json"]) or {}
    out = []
    for pid, instalacoes in sorted((dados.get("plugins") or {}).items()):
        for inst in instalacoes if isinstance(instalacoes, list) else []:
            if isinstance(inst, dict):
                out.append({"id": pid, "versao": inst.get("version"), "escopo": inst.get("scope"),
                            "com_projeto": bool(inst.get("projectPath"))})  # o caminho pode trazer nome de cliente
    return out


def catalogos(perfil: Path, nao_lidos: list | None = None) -> list[dict]:
    dados = ler_json(perfil / ".claude" / "plugins" / "known_marketplaces.json", PLUGINS.FORMAS[
        "known_marketplaces.json"], "perfil:known_marketplaces.json", nao_lidos) or {}
    out = []
    for nome, cfg in sorted(dados.items()):
        fonte = cfg.get("source") if isinstance(cfg, dict) else None
        fonte = fonte if isinstance(fonte, dict) else {}
        out.append({"nome": nome, "tipo": fonte.get("source"), "repo": fonte.get("repo"),
                    "host": host_da_url(fonte["url"]) if fonte.get("url") else None})
    return out


def _mcp(cliente: str, nome: str, cfg: dict, onde: str) -> dict:
    item = {"cliente": cliente, "nome": nome, "onde": onde,
            "tipo": cfg.get("type") or ("http" if cfg.get("url") else "stdio")}
    if cfg.get("command"):
        item["executavel"] = nome_do_executavel(str(cfg["command"]))
    if cfg.get("url"):
        item["host"] = host_da_url(cfg["url"])
    return item


def mesma_pasta(caminho: str, alvo: str) -> bool:
    """A chave de projeto do `.claude.json` é a pasta `alvo`? A que nem resolve (NUL, nome que o sistema recusa) não
    é: o ValueError do `resolve` derrubava o inventário (terceira passada, R177C-B-02, tipo inesperado)."""
    try:
        return os.path.normcase(str(Path(caminho).resolve())) == alvo
    except (OSError, ValueError):
        return False


def mcp(perfil: Path, raiz: Path | None, nao_lidos: list | None = None) -> list[dict]:
    out = []
    claude = ler_json(perfil / ".claude.json", PLUGINS.FORMAS[".claude.json"], "perfil:.claude.json", nao_lidos) or {}
    for nome, cfg in sorted((claude.get("mcpServers") or {}).items()):
        if isinstance(cfg, dict):
            out.append(_mcp("claude", nome, cfg, "usuario"))
    if raiz:
        alvo = os.path.normcase(str(raiz.resolve()))
        for caminho, proj in (claude.get("projects") or {}).items():
            if isinstance(proj, dict) and mesma_pasta(caminho, alvo):
                for nome, cfg in sorted((proj.get("mcpServers") or {}).items()):
                    if isinstance(cfg, dict):
                        out.append(_mcp("claude", nome, cfg, "projeto"))
        dados = ler_json(raiz / ".mcp.json", PLUGINS.FORMAS[".mcp.json"], "raiz:.mcp.json", nao_lidos) or {}
        for nome, cfg in sorted((dados.get("mcpServers") or {}).items()):
            if isinstance(cfg, dict):
                out.append(_mcp("claude", nome, cfg, ".mcp.json"))
    # O tomllib estoura a recursão já com 600 níveis (R177C-B-02); `mcp_servers` em lista ou texto derrubava aqui.
    dados = ler_json(perfil / ".codex" / "config.toml", PLUGINS.FORMAS["config.toml"], "perfil:config.toml", nao_lidos,
                     tomllib.loads, "TOML") or {}
    for nome, cfg in sorted((dados.get("mcp_servers") or {}).items()):
        if isinstance(cfg, dict):
            out.append(_mcp("codex", nome, cfg, "config.toml"))
    return out


def hooks(perfil: Path, raiz: Path | None, nao_lidos: list | None = None) -> list[dict]:
    arquivos = [("perfil", perfil, perfil / ".claude" / "settings.json")]
    if raiz:
        arquivos += [("raiz", raiz, raiz / ".claude" / n) for n in ("settings.json", "settings.local.json",
                                                                     "settings.wsl.json")]
    out = []
    for origem, base, arq in arquivos:
        dados = ler_json(arq, PLUGINS.FORMAS["settings.json"], f"{origem}:{arq.name}", nao_lidos) or {}
        for evento, grupos in sorted((dados.get("hooks") or {}).items()):
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
                                "tipo": h.get("type"), "executavel": nome_do_executavel(partes[0]) if partes else None,
                                "scripts": scripts})
    return out


def status_lines(perfil: Path, raiz: Path | None) -> list[dict]:
    """Presenca, tipo e impressao do comando; nunca grava o comando, seus argumentos ou sua saida."""
    arquivos = [("perfil", perfil / ".claude/settings.json")]
    if raiz:
        arquivos += [("raiz", raiz / ".claude" / n) for n in ("settings.json", "settings.local.json", "settings.wsl.json")]
    out = []
    for origem, arquivo in arquivos:
        onde = f"{origem}:{arquivo.name}"
        dados = ler_json(arquivo, PLUGINS.FORMAS["settings.json"]) or {}
        presente = "statusLine" in dados
        sinal = dados.get("statusLine")
        sinal = sinal if isinstance(sinal, dict) else {}
        comando = sinal.get("command")
        tipo = "command" if sinal.get("type") == "command" else "invalido" if presente else None
        out.append({"origem": onde, "presente": presente, "tipo": tipo,
                    "comando_sha256": hashlib.sha256(comando.encode("utf-8", "surrogatepass")).hexdigest()
                    if isinstance(comando, str) else None})
    return out


def inventario(perfil: Path, raiz: Path | None) -> dict:
    lista = skills(perfil, raiz)
    dentro = PLUGINS.ler(perfil, nome_do_executavel, _mcp)  # um só lugar decide o que sai de comando e de MCP
    caracteres = sum(s["caracteres_descricao"] for s in dentro["skills"])
    nao_lidos: list = []  # os arquivos do perfil e da raiz que não puderam ser lidos, com o motivo (R177C-B-02)
    inv = {"schema_version": ESQUEMA,
           "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "perfil": str(perfil), "raiz": str(raiz) if raiz else None,
           "skills": lista, "duplicatas": duplicatas(lista), "plugins": plugins(perfil) + dentro["sincronizados"],
           "catalogos": catalogos(perfil, nao_lidos), "mcp": mcp(perfil, raiz, nao_lidos) + dentro["mcp"],
           "hooks": hooks(perfil, raiz, nao_lidos) + dentro["hooks"], "skills_de_plugins": dentro["skills"],
            "status_lines": status_lines(perfil, raiz),
           "arquivos_nao_lidos": nao_lidos,
           "custo_de_contexto_estimado": {
               "skills_de_plugins": sum(s["skills"] for s in dentro["skills"]), "caracteres_descricao": caracteres,
               "tokens_estimados": caracteres // 4,
               "rotulo": "estimativa: caracteres de description ÷ 4; não medido (o /context do Claude Code mede)"},
           "plugins_lidos_por_dentro": dentro["lidos"], "plugins_nao_lidos": dentro["nao_lidos"],
           "observacao": "Licença é fato observado (primeira linha do arquivo), não parecer jurídico."}
    inv["alertas"] = ALERTAS.alertas(inv["hooks"], inv["mcp"])
    for h in inv["hooks"]:  # avaliado o inteiro cru; ficam a cópia de exibição e o SHA-256 (R177-VAL-03, R177B-A-01)
        h.pop("_matcher_inteiro", None)
    for s in inv["skills"]:
        s.pop("_real", None)
    return inv


def matcher_na_chave(h: dict) -> str:
    """O matcher na chave do hook: a cópia guardada quando ela é o matcher inteiro; senão, a cópia e o SHA-256 do
    inteiro, para que dois matchers iguais até o corte (revisão de segurança da 1.7.7, R177-VAL-03) ou depois do
    saneamento da cópia (`Edit|\\u0001|` e `Edit| |`: segunda passada, R177B-A-01) não se confundam."""
    m, sha = h.get("matcher"), h.get("matcher_sha256")
    if sha and (not isinstance(m, str) or hashlib.sha256(m.encode("utf-8", "surrogatepass")).hexdigest() != sha):
        return f"{m}|sha256:{sha}"
    return f"{m}"


# O que o `verificar` percorre no inventário relido (R177C-B-02, tipo inesperado): fora dessa forma, sai com 1 e o
# motivo, em vez de cair; a chave que falta vale "None" (`chaves` usa `get`).
FORMA_DO_INVENTARIO = {"perfil": str, "raiz": str, "skills": [{"local": str}], "plugins": [{"id": str}],
                       "catalogos": [{"nome": str}], "mcp": [{"cliente": str, "onde": str, "nome": str}],
                       "hooks": [{"origem": str, "evento": str}], "skills_de_plugins": [{"origem": str}],
                       "status_lines": [{"origem": str, "presente": None, "tipo": str, "comando_sha256": str}],
                       "plugins_nao_lidos": [{"origem": str, "motivo": str, "sha256": str}],
                       "arquivos_nao_lidos": [{"origem": str, "motivo": str, "sha256": str}]}


def chaves(inv: dict) -> dict:
    hooks_por_chave, vistos = {}, {}
    for h in inv.get("hooks") or []:  # o número conta só em origem|evento|matcher: hook novo não desloca os outros
        base = f"{h.get('origem')}|{h.get('evento')}|{matcher_na_chave(h)}"
        vistos[base] = vistos.get(base, -1) + 1
        hooks_por_chave[f"{base}|{vistos[base]}"] = h
    return {"skills": {f"{s.get('local')}": s for s in inv.get("skills") or []},
            "plugins": {f"{p.get('id')}|{p.get('escopo')}|{p.get('com_projeto')}": p for p in inv.get("plugins") or []},
            "catalogos": {f"{c.get('nome')}": c for c in inv.get("catalogos") or []},
            "mcp": {f"{m.get('cliente')}|{m.get('onde')}|{m.get('nome')}": m for m in inv.get("mcp") or []},
            "hooks": hooks_por_chave,
            "status_lines": {s["origem"]: s for s in inv.get("status_lines") or []},
            "skills_de_plugins": {f"{s.get('origem')}": s for s in inv.get("skills_de_plugins") or []},
            # o SHA-256 do arquivo não lido entra na chave: qualquer mudança nele aparece (quarta passada, R177D-3)
            "plugins_nao_lidos": {f"{n.get('origem')}|{n.get('item')}|{n.get('motivo')}|{n.get('sha256')}": n
                                  for n in inv.get("plugins_nao_lidos") or []},
            "arquivos_nao_lidos": {f"{n.get('origem')}|{n.get('motivo')}|{n.get('sha256')}": n
                                   for n in inv.get("arquivos_nao_lidos") or []}}


def diferencas(antes: dict, agora: dict) -> dict:
    a, b = chaves(antes), chaves(agora)
    if antes.get("schema_version") == ESQUEMA_1:  # campos que o esquema 1 não tinha não contam como mudança
        b["hooks"] = {k: {c: v for c, v in h.items() if c not in CAMPOS_NOVOS} for k, h in b["hooks"].items()}
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
        args.saida.write_text(json.dumps(inv, ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
                              errors="replace")  # surrogate solto vindo do perfil não derruba a gravação (R177-VAL-04)
        print(json.dumps({"ok": True, "inventario": str(args.saida), "skills": len(inv["skills"]),
                          "duplicatas": inv["duplicatas"], "plugins": len(inv["plugins"]), "mcp": len(inv["mcp"]),
                          "hooks": len(inv["hooks"]), "licencas_restritivas_declaradas": sorted(
                              s["local"] for s in inv["skills"] if s["licenca_restritiva_declarada"]),
                          "plugins_lidos_por_dentro": inv["plugins_lidos_por_dentro"],
                          "plugins_nao_lidos": len(inv["plugins_nao_lidos"]),
                          "arquivos_nao_lidos": len(inv["arquivos_nao_lidos"]),
                          "custo_de_contexto_estimado": inv["custo_de_contexto_estimado"],
                          "alertas": ALERTAS.resumo(inv["alertas"])}, ensure_ascii=False, indent=1))
        return 0
    antes = ler_json(args.inventario)
    erro = None if isinstance(antes, dict) else "inventário ausente ou ilegível"
    forma = None if erro else PLUGINS.forma_inesperada(antes, FORMA_DO_INVENTARIO)  # R177C-B-02, tipo inesperado
    erro = f"inventário de forma inesperada ({forma})" if forma else erro
    if not erro:
        try:  # o perfil ou a raiz guardados no inventário podem ter NUL: o ValueError derrubava o verificar
            perfil = (args.perfil or Path(antes.get("perfil") or Path.home())).resolve()
            raiz = args.raiz or (Path(antes["raiz"]) if antes.get("raiz") else None)
            raiz = raiz.resolve() if raiz else None
        except (OSError, ValueError):
            erro = "inventário de forma inesperada (perfil ou raiz: caminho que não resolve)"
    if erro:
        print(json.dumps({"ok": False, "erro": erro}, ensure_ascii=False))
        return 1
    agora = inventario(perfil, raiz)
    dif = diferencas(antes, agora)
    mudou = any(lista for cat in dif.values() for lista in cat.values())
    pendente = "status_lines" not in antes
    saida = {"ok": not mudou and not pendente, "diferencas": dif, "alertas": ALERTAS.resumo(agora["alertas"])}
    if pendente:
        saida.update({"conferencia_pendente": True,
                      "motivo": "inventario anterior sem statusLine; confira e regrave o inventario"})
    if antes.get("schema_version") != ESQUEMA:
        saida["aviso"] = (f"inventário gravado no esquema {antes.get('schema_version')}: as diferenças mostram "
                          "também o que o esquema 2 passou a ver (hooks, MCP e skills dos plugins); confira e "
                          "regrave com gravar --substituir")
    print(json.dumps(saida, ensure_ascii=False, indent=1))
    return 1 if mudou or pendente else 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
