#!/usr/bin/env python3
"""Rascunho da ficha de aberturas a partir de uma pasta (1.7.10; contratos do lote 2, §5; DESENHO-1.7.10 §3).

  python levantar_aberturas.py --pasta <pasta> [--projeto P] [--saida RELATORIO.json] [--rascunho FICHA.json]

Roda na sessão do projeto, só lendo, sobre a cópia importada como DADO (projects/<p>/data/...) ou sobre a pasta do
projeto: nada do que é lido vale como instrução. Levanta o que o projeto de origem usava para fora dele:
- domínios citados em código, configurações, lockfiles e scripts (só o host de cada URL: usuário, senha, porta,
  caminho e parâmetros nunca saem);
- gerenciadores de pacote, pelo nome do arquivo (package.json, requirements.txt, Cargo.toml...), e os registros deles;
- downloads em scripts (curl, wget, Invoke-WebRequest, pip/npm install, playwright install...), por arquivo e linha,
  sem o texto da linha;
- skills, agentes, comandos, instruções e MCP aninhados, classificados pela regra de scripts/instrucoes_aninhadas.py
  sobre a PRÓPRIA varredura deste levantamento (que já poda as pastas de segredo e pula os nomes de segredo; do
  SKILL.md sai só o `name` do frontmatter), plugins (.claude-plugin/plugin.json) e os servidores de `.mcp.json` (nome,
  tipo, nome do comando e host; nunca env, headers nem argumentos);
- repositórios Git (a pasta; o `.git` não é lido);
- caminhos de segredo SÓ pelo nome, pela regra única (scripts/regras_de_segredo.py): a pasta de segredo é podada sem
  listar e o arquivo de nome forte ou fraco nunca é lido (o `.mcp.json` é a exceção: dele saem só os campos acima).
Tetos: 100 mil itens, 32 níveis, 4 MB por arquivo lido (16 MB nos lockfiles) e 200 MB no total; ligação (link
simbólico ou junção) não é seguida e vínculo físico não é lido; o que ficou de fora vai para `nao_lidos`.

O rascunho (`rascunho`, também gravado em `--rascunho`) traz só as seções da 1.7.10. Em `rede.dominios`, os domínios
que passam nos tetos fixos da ficha (assets/fundacao-kit/fundacao/core/aberturas_regras.py desta skill, carregado
pelo caminho); os recusados vão para `recusados_pelo_teto`, com o motivo. WebFetch e WebSearch ficam fechados (são
decisão do titular); `WebFetch(domain:...)` achado em configuração vai para `candidatos_webfetch`. Plugin só entra no
rascunho quando está em `plugins-candidatos/<nome>/` da pasta levantada (a do projeto), com `manifesto_sha256`
vazio: o `abertura preparar` o calcula. O que é da 1.7.11 (MCP, Git, segredos, navegador, outras LLMs) vai para
`para_1_7_11`, fora da ficha. `motivo` e `consequencias` ficam vazios: a sessão os preenche com as palavras do
titular antes de `python -m fundacao abertura preparar --projeto P --rascunho <arquivo>`.

Honestidade (contratos do lote 2, §0): o rascunho não abre nada. Só a ficha assinada pela ferramenta fixa do titular
vale, e só depois do canário no ambiente real.

Código 0: tudo lido; 1: levantamento parcial (ligação, teto ou arquivo não lido: o relatório diz o quê); 2: uso
incorreto.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import stat
import sys
import unicodedata
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ESQUEMA = "fundacao.levantamento_aberturas/1"


def _carregar(nome: str, caminho: Path):
    """Um módulo pelo caminho, sem mexer no `sys.path` (como o manifesto.py e o importar.py)."""
    spec = importlib.util.spec_from_file_location(nome, caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


REGRAS = _carregar("_levantar_regras_de_segredo", AQUI / "regras_de_segredo.py")
ANINHADAS = _carregar("_levantar_instrucoes_aninhadas", AQUI / "instrucoes_aninhadas.py")
GRAVACAO = _carregar("_levantar_gravacao_segura", AQUI / "gravacao_segura.py")
FICHA = _carregar("_levantar_aberturas_regras",
                  AQUI.parent / "assets" / "fundacao-kit" / "fundacao" / "core" / "aberturas_regras.py")

TETO_ITENS, TETO_NIVEIS, TETO_LISTA = 100_000, 32, 500
TETO_ARQUIVO, TETO_LOCKFILE, TETO_TOTAL = 4 << 20, 16 << 20, 200 << 20
PODADAS = frozenset({"__pycache__", "node_modules", ".venv", "venv", ".mypy_cache", ".pytest_cache", ".tox", ".cache"})
EXTENSOES = frozenset(".py .js .mjs .cjs .ts .tsx .jsx .sh .bash .zsh .ps1 .psm1 .bat .cmd .rb .go .rs .java .kt .php "
                      ".cs .json .jsonc .toml .yaml .yml .ini .cfg .conf .xml .gradle .properties .lock .mk .tf .hcl"
                      .split())
NOMES = frozenset({"makefile", "dockerfile", "justfile", "procfile", "gemfile", "pipfile"})
PIP, NPM = ("pypi.org", "files.pythonhosted.org"), ("registry.npmjs.org",)
GERENCIADORES = {
    "package.json": ("npm", NPM), "package-lock.json": ("npm", NPM), "npm-shrinkwrap.json": ("npm", NPM),
    "yarn.lock": ("yarn", ("registry.yarnpkg.com",) + NPM), "pnpm-lock.yaml": ("pnpm", NPM),
    "pyproject.toml": ("pip", PIP), "setup.py": ("pip", PIP), "setup.cfg": ("pip", PIP), "pipfile": ("pip", PIP),
    "pipfile.lock": ("pip", PIP), "poetry.lock": ("pip", PIP), "uv.lock": ("pip", PIP),
    "cargo.toml": ("cargo", ("crates.io", "static.crates.io", "index.crates.io")), "cargo.lock": ("cargo", ()),
    "go.mod": ("go", ("proxy.golang.org", "sum.golang.org")), "go.sum": ("go", ()),
    "gemfile": ("gem", ("rubygems.org",)), "gemfile.lock": ("gem", ()),
    "composer.json": ("composer", ("repo.packagist.org",)), "composer.lock": ("composer", ()),
    "pom.xml": ("maven", ("repo.maven.apache.org",)), "build.gradle": ("gradle", ("repo.maven.apache.org",)),
    "build.gradle.kts": ("gradle", ("repo.maven.apache.org",)), "deno.json": ("deno", ("deno.land", "jsr.io")),
}
OUTRAS_LLM = ("openai.com", "anthropic.com", "generativelanguage.googleapis.com", "aiplatform.googleapis.com",
              "mistral.ai", "cohere.ai", "cohere.com", "groq.com", "openrouter.ai", "deepseek.com", "together.xyz",
              "perplexity.ai", "x.ai")
IDENTIFICADORES = frozenset({"www.w3.org", "w3.org", "json-schema.org", "schemas.microsoft.com", "schema.org",
                             "schemas.openxmlformats.org", "purl.org", "xmlns.com", "ns.adobe.com", "www.apache.org",
                             "apache.org", "opensource.org", "creativecommons.org", "spdx.org", "www.gnu.org",
                             "gnu.org", "semver.org", "keepachangelog.com"})
URL = re.compile(r"(?i)\b(?:https?|wss?|ftp)://([^\s/'\"<>`\\?#)\]}]+)")
WEBFETCH = re.compile(r"WebFetch\(domain:([^)\s\"']+)\)")
DOWNLOAD = re.compile(r"(?i)\b(curl|wget|invoke-webrequest|iwr|start-bitstransfer|pip3? install|npm (?:install|i) -g|"
                      r"npx|pnpm dlx|go install|cargo install|playwright install|apt(?:-get)? install|brew install)\b")
NAVEGADOR = re.compile(r"(?i)\b(playwright|puppeteer|selenium|webdriver)\b")
SUBSTITUTA_DE_NOME = 0x20000000  # Windows: junção, link simbólico e afins (bit 29 da etiqueta de reparse)
_LEITURA = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
HONESTIDADE = ("O rascunho não abre nada: só a ficha assinada pela ferramenta fixa do titular vale, e só depois do "
               "canário no ambiente real (com a raiz em /mnt/e, o isolamento entre projetos é lógico até lá).")


def e_ligacao(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & SUBSTITUTA_DE_NOME)


def limpo(texto, teto: int = 80) -> str:
    """Texto vindo da pasta levantada, para o relatório: sem caractere de controle nem invisível, e curto."""
    return "".join(c for c in str(texto) if unicodedata.category(c)[0] != "C")[:teto]


def host(bruto: str) -> str:
    """O host de um `esquema://usuario:senha@host:porta`: sem usuário, senha nem porta, em minúsculas."""
    resto = bruto.rsplit("@", 1)[-1]
    if resto.startswith("["):
        return resto[:resto.find("]") + 1].lower()
    return resto.split(":", 1)[0].rstrip(".").lower()


def gerenciador(nome: str) -> tuple[str, tuple] | None:
    baixo = nome.casefold()
    if baixo.startswith("requirements") and baixo.endswith(".txt"):
        return "pip", PIP
    return GERENCIADORES.get(baixo)


class Levantamento:
    """O que a varredura acha. Cada lista tem teto (TETO_LISTA); a contagem total fica em `contagens`."""

    def __init__(self, pasta: Path):
        self.pasta, self.lidos, self.contagens, self.limites, self.dominios = pasta, 0, {}, set(), {}
        self.listas = {k: [] for k in ("ligacoes_nao_seguidas", "nao_lidos", "pastas_podadas", "segredos_pelo_nome",
                                       "repositorios_git", "gerenciadores", "downloads", "para_1_7_11",
                                       "candidatos_webfetch", "plugins_encontrados")}
        self.aninhadas = {k: [] for k in ("instrucoes", "skills", "agents", "commands", "rules", "codex", "mcp",
                                          "configuracoes")}

    def anotar(self, lista: str, item) -> None:
        self.contagens[lista] = self.contagens.get(lista, 0) + 1
        if len(self.listas[lista]) < TETO_LISTA:
            self.listas[lista].append(item)

    def nao_lido(self, rel: str, motivo: str) -> None:
        if "teto" in motivo:
            self.limites.add("bytes")
        self.anotar("nao_lidos", {"caminho": rel, "motivo": motivo})

    def dominio(self, nome: str, origem: str) -> None:
        origens = self.dominios.setdefault(nome, [])
        if origem not in origens:
            origens.append(origem)

    def percorrer(self):
        """(caminho, partes, so_aninhadas) dos arquivos comuns, sem atravessar ligação; poda o `.git`, as pastas de
        segredo e as reconstruíveis (node_modules, .venv...), estas nunca dentro de `.claude` ou `.codex`:
        `.claude/skills/venv/` é o lugar canônico de uma skill (revisão de segurança da 1.7.10, FLUXB-F3, revisão 1).
        Ali a reconstruível é percorrida só para as aninhadas (`so_aninhadas`): as dependências de um hook não viram
        domínio nem gerenciador do rascunho (revisão 2)."""
        pilha, vistos = [(self.pasta, (), False)], 0
        while pilha:
            pasta, partes, so_aninhadas = pilha.pop()
            try:
                with os.scandir(pasta) as it:
                    entradas = sorted(it, key=lambda e: e.name, reverse=True)
            except OSError as exc:
                self.nao_lido("/".join(partes) or ".", f"pasta ilegível ({exc.__class__.__name__})")
                continue
            for e in entradas:
                vistos += 1
                if vistos > TETO_ITENS:
                    self.limites.add("itens")
                    return
                rel_partes = partes + (e.name,)
                rel = "/".join(rel_partes)
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    self.nao_lido(rel, "ilegível")
                    continue
                if e_ligacao(st):
                    self.anotar("ligacoes_nao_seguidas", rel)
                elif e.name == ".git":
                    self.anotar("repositorios_git", "/".join(partes) or ".")
                    self.anotar("para_1_7_11", {"secao": "git", "item": "/".join(partes) or ".", "origem": rel})
                elif stat.S_ISDIR(st.st_mode):
                    if REGRAS.e_pasta_de_segredo(e.name):
                        self.anotar("segredos_pelo_nome", {"caminho": rel + "/", "classe": "pasta-de-segredo"})
                    elif e.name in PODADAS and not ANINHADAS.sob_extensao_de_host(rel_partes):
                        self.anotar("pastas_podadas", rel)
                    elif len(rel_partes) > TETO_NIVEIS:
                        self.limites.add("profundidade")
                        self.nao_lido(rel, f"limite de {TETO_NIVEIS} níveis")
                    else:
                        pilha.append((Path(e.path), rel_partes, so_aninhadas or e.name in PODADAS))
                elif stat.S_ISREG(st.st_mode):
                    yield Path(e.path), rel_partes, so_aninhadas

    def ler(self, caminho: Path, rel: str, teto: int) -> bytes | None:
        """O arquivo comum, sem seguir ligação nem vínculo físico, dentro do teto (senão, `nao_lidos` e None). O lstat
        é do caminho (no Windows, o do `scandir` não traz inode nem vínculos)."""
        try:
            st = os.lstat(caminho)
            fd = None if (e_ligacao(st) or not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > teto
                          or self.lidos + st.st_size > TETO_TOTAL) else os.open(caminho, _LEITURA)
        except OSError as exc:
            return self.nao_lido(rel, f"ilegível ({exc.__class__.__name__})")
        if fd is None:
            return self.nao_lido(rel, "vínculo físico (hard link) ou trocado: não lido" if st.st_nlink != 1
                                 or not stat.S_ISREG(st.st_mode) else f"acima do teto de {teto} bytes ou do total")
        try:
            aberto = os.fstat(fd)
            if (aberto.st_dev, aberto.st_ino) != (st.st_dev, st.st_ino) or aberto.st_nlink != 1:
                return self.nao_lido(rel, "trocado entre o exame e a leitura")
            partes, total = [], 0
            while bloco := os.read(fd, min(1 << 20, teto + 1 - total)):
                partes.append(bloco)
                total += len(bloco)
                if total > teto:
                    return self.nao_lido(rel, f"acima do teto de {teto} bytes")
        finally:
            os.close(fd)
        self.lidos += total
        return b"".join(partes)

    def mcp(self, dados: bytes, rel: str) -> None:
        """Servidores de um `.mcp.json`: nome, tipo, nome do comando e host. Nunca env, headers nem argumentos."""
        try:
            doc = json.loads(dados.decode("utf-8"))
        except (ValueError, RecursionError):
            return self.nao_lido(rel, ".mcp.json ilegível")
        servidores = doc.get("mcpServers") if isinstance(doc, dict) else None
        for nome, cfg in (list(servidores.items())[:200] if isinstance(servidores, dict) else []):
            item = {"secao": "mcp", "item": limpo(nome), "origem": rel}
            if isinstance(cfg, dict):
                item["tipo"] = limpo(cfg.get("type") or ("http" if "url" in cfg else "stdio"), 20)
                if isinstance(cfg.get("command"), str):
                    item["comando"] = limpo(cfg["command"].replace("\\", "/").rsplit("/", 1)[-1], 60)
                achado = URL.search(cfg["url"]) if isinstance(cfg.get("url"), str) else None
                if achado:
                    item["dominios"] = [limpo(host(achado.group(1)), 253)]
            self.anotar("para_1_7_11", item)
        return None

    def plugin(self, dados: bytes, pasta_rel: str) -> None:
        try:
            doc = json.loads(dados.decode("utf-8"))
        except (ValueError, RecursionError):
            doc = None
        nome = doc.get("name") if isinstance(doc, dict) else None
        self.anotar("plugins_encontrados", {"pasta": pasta_rel, "nome": limpo(nome, 64) if isinstance(nome, str) else None,
                                            "declara_hooks_ou_mcp": isinstance(doc, dict) and any(
                                                c in doc for c in ("hooks", "mcpServers", "lspServers"))})

    def texto(self, dados: bytes, rel: str) -> None:
        if b"\0" in dados[:8192]:
            return
        for numero, linha in enumerate(dados.decode("utf-8", "replace").splitlines(), 1):
            hosts = [host(m.group(1)) for m in URL.finditer(linha)]
            for h in hosts:
                self.dominio(h, rel)
            for m in WEBFETCH.finditer(linha):
                self.anotar("candidatos_webfetch", {"dominio": limpo(m.group(1).lower(), 253), "origem": rel})
            baixa = DOWNLOAD.search(linha)
            if baixa:
                self.anotar("downloads", {"arquivo": rel, "linha": numero, "ferramenta": baixa.group(1).lower(),
                                          "dominios": sorted({limpo(h, 253) for h in hosts})})
            navegador = NAVEGADOR.search(linha)
            if navegador:
                self.anotar("para_1_7_11", {"secao": "navegador", "item": navegador.group(1).lower(),
                                            "origem": f"{rel}:{numero}"})

    def aninhada(self, caminho: Path, partes: tuple, rel: str) -> None:
        """Instrução, skill, agente, comando, regra, Codex, MCP ou configuração aninhada (a regra de
        instrucoes_aninhadas.classificar), achada por esta varredura: o arquivo de nome de segredo nem chega aqui. Da
        skill, lê só o começo, para o `name` do frontmatter."""
        tipo = ANINHADAS.classificar(partes)
        if tipo is None:
            return
        item = {"caminho": rel}
        if tipo == "skills":
            dados = self.ler(caminho, rel, TETO_ARQUIVO)
            # SKILL.md não lido: o nome é incerto, e a pasta vai para a negação (FLUXB-F3, revisão 2).
            item["nome"] = None if dados is None else ANINHADAS.nome_da_skill(
                dados[:ANINHADAS.INICIO], partes[-2] if len(partes) > 1 else ".")
            if item["nome"] is None:
                item["nome_incerto"] = ANINHADAS.NOME_NAO_LIDO if dados is None else ANINHADAS.NOME_INCERTO
        if len(self.aninhadas[tipo]) < TETO_LISTA:
            self.aninhadas[tipo].append(item)

    def varrer(self) -> None:
        for caminho, partes, so_aninhadas in self.percorrer():
            rel, nome = "/".join(partes), partes[-1]
            baixo = nome.casefold()
            if so_aninhadas:  # reconstruível dentro de .claude/.codex: só as aninhadas, nunca segredo (revisão 2)
                if baixo == ".mcp.json" or not REGRAS.classificar(rel):
                    self.aninhada(caminho, partes, rel)
                continue
            if baixo == ".mcp.json":
                self.aninhada(caminho, partes, rel)
                dados = self.ler(caminho, rel, TETO_ARQUIVO)
                if dados is not None:
                    self.mcp(dados, rel)
                continue
            classe = REGRAS.classificar(rel)
            if classe:
                self.anotar("segredos_pelo_nome", {"caminho": rel, "classe": classe})
                continue
            self.aninhada(caminho, partes, rel)
            achado = gerenciador(nome)
            if achado:
                self.anotar("gerenciadores", {"gerenciador": achado[0], "arquivo": rel, "dominios": list(achado[1])})
                for d in achado[1]:
                    self.dominio(d, f"gerenciador {achado[0]} ({rel})")
            plugin = partes[-2:] == (".claude-plugin", "plugin.json")
            if achado or plugin or os.path.splitext(baixo)[1] in EXTENSOES or baixo in NOMES:
                dados = self.ler(caminho, rel, TETO_LOCKFILE if achado else TETO_ARQUIVO)
                if dados is not None and plugin:
                    self.plugin(dados, "/".join(partes[:-2]) or ".")
                if dados is not None:
                    self.texto(dados, rel)


def _proposto(item: dict) -> dict | None:
    """Plugin em `plugins-candidatos/<nome>/` da pasta levantada vira item do rascunho, com o manifesto vazio."""
    partes = item["pasta"].split("/")
    nome = item["nome"] if item["nome"] is not None else partes[-1]
    if len(partes) != 2 or partes[0] != "plugins-candidatos" or not FICHA.NOME_PLUGIN.fullmatch(nome):
        return None
    return {"nome": nome, "origem": item["pasta"], "manifesto_sha256": ""}


def levantar(pasta: Path, projeto: str | None = None) -> dict:
    lev = Levantamento(pasta)
    lev.varrer()
    candidatos, recusados, ignorados, avisos = {}, [], [], []
    for nome, origens in sorted(lev.dominios.items()):
        resumo = {"arquivos": origens[:5], "total": len(origens)}
        motivo = FICHA.problema_do_dominio(nome)
        if any(c in nome for c in "${}%<>"):
            ignorados.append({"dominio": limpo(nome, 253), "motivo": "modelo ou variável, não um domínio"})
        elif nome in IDENTIFICADORES or nome.endswith((".example", ".invalid", ".test")) or nome.startswith("example."):
            ignorados.append({"dominio": nome, "motivo": "endereço que costuma ser só identificador ou exemplo"})
        elif any(nome == d or nome.endswith("." + d) for d in OUTRAS_LLM):
            lev.anotar("para_1_7_11", {"secao": "outras_llm", "item": nome, "origem": origens[0]})
        elif motivo:
            recusados.append({"dominio": limpo(nome, 253), "motivo": motivo, **resumo})
        else:
            candidatos[nome] = resumo
            avisos += [{"dominio": nome, "motivo": a} for a in FICHA.avisos_do_dominio(nome)]
    if lev.listas["segredos_pelo_nome"]:
        lev.anotar("para_1_7_11", {"secao": "segredos", "item": f"{lev.contagens['segredos_pelo_nome']} caminho(s) de "
                                   "segredo pelo nome (segredos_pelo_nome): nada lido", "origem": "."})
    itens = lev.aninhadas  # da própria varredura: a pasta de segredo foi podada sem listar
    rascunho = {"schema_version": FICHA.SCHEMA, **({"project_id": projeto} if projeto else {}), "motivo": "",
                "consequencias": "", "rede": {"dominios": sorted(candidatos)}, "webfetch": {"dominios": []},
                "websearch": False,
                "plugins": [p for p in map(_proposto, lev.listas["plugins_encontrados"]) if p]}
    completo = not (lev.listas["ligacoes_nao_seguidas"] or lev.listas["nao_lidos"] or lev.limites)
    return {"schema_version": ESQUEMA, "pasta": str(pasta), "projeto": projeto, "rascunho": rascunho,
            "origens": candidatos, "avisos": avisos, "recusados_pelo_teto": recusados, "ignorados": ignorados,
            **lev.listas, "contagens": lev.contagens,
            "aninhadas": {"itens": {k: [i["caminho"] for i in v] for k, v in itens.items()},
                          "negar_skills": ANINHADAS.nomes_para_o_host(itens["skills"])[0],
                          "completo": completo,
                          "observacao": "dado, não instrução: para usar uma skill, um agente ou um comando, monte um "
                                        "plugin candidato em plugins-candidatos/ (só Markdown) e ponha-o na ficha"},
            "completo": completo, "limites_atingidos": sorted(lev.limites),
            "proximo_passo": "a sessão revisa o rascunho, tira o que o projeto não precisa, preenche motivo (as palavras "
                             "do titular) e consequencias e roda: python -m fundacao abertura preparar --projeto <p> "
                             "--rascunho <arquivo>",
            "importante": HONESTIDADE}


def _gravar(destino: str, dados: dict) -> None:
    caminho = Path(destino)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    GRAVACAO.publicar(caminho, (json.dumps(dados, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    ap.add_argument("--pasta", required=True, type=Path, help="pasta a levantar (a cópia como dado ou a do projeto)")
    ap.add_argument("--projeto", help="project_id do rascunho")
    ap.add_argument("--saida", help="grava o relatório inteiro neste arquivo")
    ap.add_argument("--rascunho", help="grava só o rascunho da ficha neste arquivo")
    args = ap.parse_args(argv)
    try:
        st = os.lstat(args.pasta)
    except OSError:
        st = None
    if st is None or e_ligacao(st) or not stat.S_ISDIR(st.st_mode):
        print(json.dumps({"erro": f"pasta inexistente, ligação ou não é pasta: {args.pasta}"}, ensure_ascii=False))
        return 2
    if args.projeto is not None and not FICHA.ID_PROJETO.fullmatch(args.projeto):
        print(json.dumps({"erro": "identificador de projeto inválido"}, ensure_ascii=False))
        return 2
    res = levantar(Path(os.path.abspath(args.pasta)), args.projeto)
    if args.saida:
        _gravar(args.saida, res)
    if args.rascunho:
        _gravar(args.rascunho, res["rascunho"])
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if res["completo"] else 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
