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
Não segue ligação (link simbólico ou junção): ela vai para `ligacoes_nao_seguidas`, e o que há do outro lado não é
lido nem inventariado. Tetos aplicados durante a varredura: 100 mil itens, 32 níveis, 5 MB por arquivo e 100 MB no
total; o que ficou de fora vai para `nao_lidos` (auditoria Codex Security da 1.7.6, #7). Arquivo com vínculo físico
(hard link, mais de um nome) também vai para `nao_lidos`, sem leitura: o outro nome pode estar fora da raiz (revisão
de segurança da 1.7.7, R177-VAL-02).
Nome de skill fora do padrão do preparo do host (1.7.10; MELHORIAS-1.7.10, seção 1, item 8: 21 nomes com espaço no
APP Saúde e o modelo `{setup-skill-name}` no Site e no Togare, recusados pelo preparo): o nome é conferido com a mesma
regra do `assets/host/preparo_host.py` (`NOME_DE_SKILL`, repetida aqui e conferida igual por teste) e, fora dela, vai
para `nomes_fora_do_padrao` (nome, pasta e motivo: tamanho, espaço, chave, acento ou outro caractere) e a pasta da
skill para `neutralizar` (a negação pelo nome não a cobre; o `importar.py` neutraliza `.claude/skills` na cópia).
O `name` só é lido na forma simples do frontmatter: '---' no byte 0, o '---' de fecho dentro do começo lido, uma linha
`name:` com o valor simples ou entre aspas sem escape e, no topo, só chaves simples. Fora dela o nome é incerto (um
leitor de YAML pode dar outro: chave entre aspas, BOM, mapa em linha, nome depois do começo lido, comentário, bloco ou
marca na linha do nome) e vai para `nomes_fora_do_padrao`, com a pasta em `neutralizar`; o SKILL.md não lido também.
O nome da pasta, quando válido, entra sempre nas negações sugeridas, além do nome lido: o host usa o da pasta quando o
frontmatter não tem nome ou não se lê, e negar um nome que não existe não custa nada (revisão de segurança da 1.7.10,
FLUXB-F3, revisão 2).
Os nomes (instruções, `.claude` e as pastas dela, `SKILL.md`, `.mcp.json` e `.codex`) são comparados pela regra única,
`regras_de_segredo.normalizar` (NFKC e sem caixa), como no `importar.neutralizavel`: o NTFS e o DrvFs abrem
`.CLAUDE/skills/x/SKILL.md`, `Claude.md` e `.MCP.json` pelo nome em minúsculas, e o host os carregaria. Cada `.claude`
do caminho conta, da mais interna para fora: a skill numa `.claude` aninhada noutra entra na lista (revisão de
segurança da 1.7.10, FLUXB-F3).
As pastas puladas (`.git`, `node_modules`, `.venv` e `venv`) são comparadas pelo nome EXATO, porque o pulo erra para o
lado de olhar mais: `Venv`, `ⅴenv`, `ｎｏｄｅ_ｍｏｄｕｌｅｓ` e `.GIT` são percorridas como qualquer pasta. Dentro de uma `.claude`
ou de uma `.codex` nada é pulado: `.claude/skills/venv/SKILL.md` é o lugar canônico de uma skill. Cada pasta pulada vai
para `nao_lidos`: o inventário fica parcial e diz qual pasta ficou de fora. Só a `.git` da raiz de um clone que o
chamador acabou de fazer (o `git_projeto.py montar`, com `listar(..., git_da_raiz_confiavel=True)`) é pulada sem
registro; a da origem do B1, a da pasta do projeto e as aninhadas podem trazer CLAUDE.md e `.claude/skills` (FLUXB-F3,
revisão 2). O `__pycache__` deixou de ser pulado: é pequeno, e pulá-lo deixaria uma lacuna em todo projeto Python
(FLUXB-F3, revisão 1 da correção).
Agentes (`.claude/agents/*.md`, 1.7.11): o mesmo vale para o `name` do frontmatter e para o nome do arquivo (sem o
`.md`), que o host usa como tipo do subagente; as negações sugeridas (`sugestoes.negar_agentes`, para o
`preparo_host.py ... --negar-agente`) trazem os dois; nome fora do padrão ou incerto vai para `agentes_fora_do_padrao`
e o ARQUIVO para `neutralizar`.
Código 0 quando leu tudo e todos os nomes cabem no padrão; 1 quando o inventário ficou parcial (ligação não seguida,
teto, arquivo ou pasta não lida ou pulada — o resultado diz o quê) ou há nome fora do padrão ou incerto (para o B1
registrar a lacuna); 2 se a pasta não existe.
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
import unicodedata
from pathlib import Path

AQUI = Path(__file__).resolve().parent


def _carregar(nome: str):
    """Um script ao lado deste, pelo caminho (sem mexer no `sys.path`: vale também com `python3 -I`)."""
    spec = importlib.util.spec_from_file_location(f"_instrucoes_{nome}", AQUI / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


REGRAS = _carregar("regras_de_segredo")  # a comparação de nomes da regra única (FLUXB-F3)

# A regra do preparo do host para o nome na negação `Skill(<nome>)` (assets/host/preparo_host.py, NOME_DE_SKILL),
# repetida aqui (este script não importa o preparo) e conferida igual por teste. A conferência usa `fullmatch`: o `$`
# do `match` aceitaria uma quebra de linha no fim do nome.
NOME_DE_SKILL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
INSTRUCOES = {"CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", "AGENTS.override.md"}
# A lista na forma da regra única: é assim que os nomes do disco são comparados (FLUXB-F3).
INSTRUCOES_SEM_CAIXA = frozenset(REGRAS.normalizar(n) for n in INSTRUCOES)
# Pastas puladas, pelo nome exato e fora de `.claude` e `.codex`; as que não são a `.git` vão para `nao_lidos`
# (FLUXB-F3, revisão 1: a forma sem caixa pulava `Venv` e `ｎｏｄｅ_ｍｏｄｕｌｅｓ` calada, e o nome exato já pulava
# `.claude/skills/venv`).
IGNORAR = {".git", "node_modules", ".venv", "venv"}
EXTENSOES_DE_HOST = frozenset({".claude", ".codex"})  # dentro delas, nada é pulado
TIPOS_NA_CLAUDE = ("agents", "commands", "rules")  # pastas da .claude que dão o tipo do item
EXCLUSAO_DE_DADOS = "**/projects/*/data/**"
TETO_ITENS = 100_000          # entradas examinadas (arquivos e pastas)
TETO_PROFUNDIDADE = 32        # níveis de pasta abaixo da raiz
TETO_ARQUIVO = 5_000_000      # bytes lidos de um arquivo (hash em blocos)
TETO_TOTAL = 100_000_000      # bytes lidos no total
INICIO = 65_536               # começo do SKILL.md onde se procura o `name` do frontmatter
BLOCO = 1 << 20
# A forma simples do frontmatter, a única em que o `name` lido linha a linha é o que um leitor de YAML daria (revisão
# de segurança da 1.7.10, FLUXB-F3, revisão 2). A linha do nome: o valor entre aspas, sem escape, ou simples, sem
# indicador do YAML no começo (aspas, marca, âncora, apelido, bloco, mapa ou lista em linha, diretiva) e sem comentário.
LINHA_DO_NOME = re.compile(r"name:[ \t]+(\"[^\"\\]*\"|'[^']*'|[^\s#'\"!&*>|{}\[\],%@`][^#]*?)[ \t]*")
# As outras linhas do topo: chave simples, que todo leitor de YAML lê igual (a chave entre aspas, com âncora ou marca,
# a explícita '?', a de mescla '<<' e o mapa em linha ficam de fora).
CHAVE_SIMPLES = re.compile(r"([A-Za-z0-9_][A-Za-z0-9_.-]*)[ \t]*:(?:[ \t].*)?")
# Caracteres que os leitores tratam de jeitos diferentes: controle, quebra de linha que não é '\n' (o '\r' solto, NEL
# e os separadores Unicode), o BOM e o caractere de troca da decodificação (UTF-8 inválido).
FORA_DA_FORMA = re.compile(r"[\x00-\x08\x0b-\x1f\x7f\x85\u2028\u2029\ufeff\ufffd]")
NOME_INCERTO = "frontmatter fora da forma simples"
NOME_NAO_LIDO = "SKILL.md não lido"
# Windows: etiqueta de ponto de nova análise "substituta de nome" (bit 29) — junção, link simbólico e afins.
SUBSTITUTA_DE_NOME = 0x20000000


class Trocado(OSError):
    """O arquivo aberto não é o examinado: virou ligação, deixou de ser comum ou resolve fora da raiz."""


class VinculoFisico(OSError):
    """Arquivo com mais de um nome (hard link): o conteúdo pode ser o de um arquivo de fora da raiz (R177-VAL-02)."""


def e_ligacao(st: os.stat_result) -> bool:
    """Link simbólico ou junção (e afins do Windows), pelo lstat — sem seguir a ligação."""
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & SUBSTITUTA_DE_NOME)


def sob_extensao_de_host(partes: tuple) -> bool:
    """O item fica dentro de uma `.claude` ou de uma `.codex` (comparadas pela regra única)? Ali nada é pulado nem
    podado: `.claude/skills/venv/SKILL.md` é o lugar canônico de uma skill (revisão de segurança da 1.7.10,
    FLUXB-F3)."""
    return any(REGRAS.normalizar(p) in EXTENSOES_DE_HOST for p in partes[:-1])


def percorrer(raiz: Path, situacao: dict, git_da_raiz_confiavel: bool = False):
    """Arquivos comuns sob a raiz, em ordem de caminho, sem atravessar ligação (a ligação vai para a situação e não é
    lida). Os tetos de itens e de profundidade valem DURANTE a varredura, não depois de ordenar. A pasta pulada (nome
    exato, fora de `.claude` e `.codex`) vai para `nao_lidos` (FLUXB-F3, revisão 1); só a `.git` da raiz, quando o
    chamador garante que é a do clone que ele acabou de fazer, fica sem registro (revisão 2)."""
    vistos = 0

    def listar(pasta: Path, partes: tuple) -> list:
        nonlocal vistos
        entradas = []
        try:
            with os.scandir(pasta) as it:
                for e in it:
                    vistos += 1
                    if vistos > TETO_ITENS:
                        situacao["limites"].add("itens")
                        situacao["nao_lidos"].append({"caminho": "/".join(partes) or ".",
                                                      "motivo": f"teto de {TETO_ITENS} itens: a varredura parou aqui"})
                        break
                    entradas.append(e)
        except OSError as exc:
            situacao["nao_lidos"].append({"caminho": "/".join(partes) or ".",
                                          "motivo": f"pasta ilegível: {type(exc).__name__}"})
        return [(partes + (e.name,), e) for e in sorted(entradas, key=lambda e: e.name, reverse=True)]

    pilha = listar(raiz, ())
    while pilha:
        partes, e = pilha.pop()
        try:
            st = e.stat(follow_symlinks=False)
        except OSError:
            continue
        if e_ligacao(st):
            situacao["ligacoes"].append("/".join(partes))
        elif stat.S_ISDIR(st.st_mode):
            if e.name in IGNORAR and not sob_extensao_de_host(partes):  # nome exato: o pulo erra para olhar mais
                if not (git_da_raiz_confiavel and partes == (".git",)):  # FLUXB-F3, revisão 2
                    situacao["nao_lidos"].append({"caminho": "/".join(partes),
                                                  "motivo": f"pasta pulada ({e.name}): não inventariada (instruções e "
                                                            "skills de dentro dela não foram conferidas)"})
                continue
            if "itens" in situacao["limites"]:
                continue
            if len(partes) > TETO_PROFUNDIDADE:
                situacao["limites"].add("profundidade")
                situacao["nao_lidos"].append({"caminho": "/".join(partes),
                                              "motivo": f"teto de {TETO_PROFUNDIDADE} níveis: pasta não aberta"})
                continue
            pilha += listar(Path(e.path), partes)
        elif stat.S_ISREG(st.st_mode):
            yield Path(e.path), partes


def ler(p: Path, raiz_real: Path, teto: int) -> tuple[str | None, bytes, int]:
    """SHA-256 em blocos (None se o arquivo passar do teto), o começo do conteúdo e os bytes lidos. Abre sem seguir
    ligação na folha (POSIX) e sem esperar em FIFO; confere, depois de abrir, que é o arquivo do lstat e que ele
    resolve dentro da raiz. Arquivo com vínculo físico (mais de um nome, no lstat ou no fstat) não é lido."""
    st = os.lstat(p)
    if e_ligacao(st) or not stat.S_ISREG(st.st_mode):
        raise Trocado(f"não é arquivo comum: {p.name}")
    if st.st_nlink > 1:
        raise VinculoFisico(f"vínculo físico: {p.name}")
    fd = os.open(p, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0))
    h, inicio, lidos = hashlib.sha256(), b"", 0
    try:
        aberto = os.fstat(fd)
        if aberto.st_nlink > 1:
            raise VinculoFisico(f"vínculo físico: {p.name}")
        if (not stat.S_ISREG(aberto.st_mode) or (aberto.st_dev, aberto.st_ino) != (st.st_dev, st.st_ino)
                or not Path(os.path.realpath(p)).is_relative_to(raiz_real)):
            raise Trocado(f"mudou entre o exame e a leitura: {p.name}")
        while bloco := os.read(fd, min(BLOCO, teto + 1 - lidos)):
            lidos += len(bloco)
            if lidos > teto:
                return None, inicio, teto
            h.update(bloco)
            inicio += bloco[:max(0, INICIO - len(inicio))]
    finally:
        os.close(fd)
    return h.hexdigest(), inicio, lidos


def nome_da_skill(inicio: bytes, pasta: str) -> str | None:
    """O `name` do frontmatter do SKILL.md (`inicio`: os primeiros INICIO bytes), lido só na forma simples; sem
    frontmatter, o nome da pasta, que é o que o host usa. None quando o nome é incerto: o frontmatter começa depois do
    byte 0 (BOM ou espaço), não fecha dentro do começo lido, tem caractere que os leitores tratam diferente, chave fora
    da forma simples no topo (entre aspas, '?', '<<', mapa em linha, recuada), `name` repetido ou continuado na linha
    seguinte, ou a linha do nome fora da forma simples (comentário, bloco, marca, âncora ou escape) — nesses casos um
    leitor de YAML pode dar outro nome (revisão de segurança da 1.7.10, FLUXB-F3, revisão 2)."""
    texto = inicio.decode("utf-8", errors="replace")
    if not texto.lstrip("\ufeff \t\r\n").startswith("---"):
        return pasta
    linhas = [linha.removesuffix("\r") for linha in texto.split("\n")]
    fecho = next((i for i, linha in enumerate(linhas[1:], 1) if linha.startswith(("---", "..."))), None)
    if (linhas[0] != "---" or fecho is None or linhas[fecho] != "---"
            or (fecho == len(linhas) - 1 and len(inicio) >= INICIO)):  # o fecho pode ter sido cortado no teto
        return None
    nomes, anterior = [], None
    for linha in linhas[1:fecho]:
        if FORA_DA_FORMA.search(linha):
            return None
        if not linha.strip() or linha.startswith("#"):
            continue
        if linha[0] in " \t-":  # dentro do valor da chave anterior (recuada ou item de lista)
            if anterior in (None, "name"):  # o topo recuado, ou a continuação do nome
                return None
            continue
        achado = LINHA_DO_NOME.fullmatch(linha)
        chave = None if achado else CHAVE_SIMPLES.fullmatch(linha)
        if achado:
            nomes.append(achado.group(1))
        elif chave is None or chave.group(1) == "name":
            return None
        anterior = "name" if achado else chave.group(1)
    if len(nomes) > 1:
        return None
    if not nomes:
        return pasta
    return nomes[0][1:-1] if nomes[0][0] in "\"'" else nomes[0]


def motivo_do_nome(nome: str) -> str | None:
    """None quando o nome cabe na regra do preparo do host; senão os motivos, nesta ordem: tamanho, espaço, chave,
    acento (letra fora do ASCII) e outro caractere."""
    if NOME_DE_SKILL.fullmatch(nome):
        return None

    def acento(c: str) -> bool:
        return ord(c) > 127 and unicodedata.category(c)[0] in "LM"

    def permitido(c: str) -> bool:
        return c.isascii() and (c.isalnum() or c in "._:-")

    motivos = []
    if not nome or len(nome) > 128:
        motivos.append("tamanho")
    if any(c.isspace() for c in nome):
        motivos.append("espaço")
    if any(c in "{}" for c in nome):
        motivos.append("chave")
    if any(acento(c) for c in nome):
        motivos.append("acento")
    outros = [c for c in nome if not (c.isspace() or c in "{}" or acento(c) or permitido(c))]
    if outros or (nome and permitido(nome[0]) and not nome[0].isalnum()):  # '.', '_', ':' ou '-' no começo
        motivos.append("outro caractere")
    return ", ".join(motivos) if motivos else "outro caractere"


def nomes_para_o_host(skills: list) -> tuple[list[str], list[dict], list[str]]:
    """Os nomes que o preparo do host aceita negar, os fora do padrão (com a pasta e o motivo) e as pastas a
    neutralizar na cópia. O nome da pasta, quando válido, entra sempre nas negações, além do nome lido: o host usa o da
    pasta quando o frontmatter não tem nome ou não se lê (revisão de segurança da 1.7.10, FLUXB-F3, revisão 2). O nome
    incerto (None, com o motivo em `nome_incerto`) vai para os fora do padrão, com a pasta a neutralizar."""
    validos, fora, neutralizar = set(), [], set()
    for s in skills:
        pasta = s["caminho"].rpartition("/")[0] or "."
        nome_da_pasta = pasta.rpartition("/")[2]
        pasta_valida = pasta != "." and motivo_do_nome(nome_da_pasta) is None
        if pasta_valida:
            validos.add(nome_da_pasta)
        nome = s.get("nome")
        motivo = f"nome incerto: {s.get('nome_incerto') or NOME_INCERTO}" if nome is None else motivo_do_nome(nome)
        if motivo is None:
            validos.add(nome)
            continue
        item = {"nome": nome, "pasta": pasta, "motivo": motivo}
        if pasta_valida:
            item["negar_pela_pasta"] = nome_da_pasta
        fora.append(item)
        neutralizar.add(pasta)
    return sorted(validos), sorted(fora, key=lambda i: (i["pasta"], i["nome"] or "")), sorted(neutralizar)


def nomes_de_agentes(agentes: list) -> tuple[list[str], list[dict], list[str]]:
    """Como `nomes_para_o_host`, para os agentes (`.claude/agents/<x>.md`): os nomes que o preparo aceita negar (o
    `name` do frontmatter e o nome do arquivo, sem o `.md`, cada um quando válido), os fora do padrão ou incertos (com o
    arquivo e o motivo) e os ARQUIVOS a neutralizar na cópia. Arquivo que não termina em `.md` não é agente do host."""
    validos, fora, neutralizar = set(), [], set()
    for a in agentes:
        if "nome" not in a:
            continue
        arquivo = a["caminho"]
        do_arquivo = arquivo.rpartition("/")[2][:-len(".md")]
        arquivo_valido = motivo_do_nome(do_arquivo) is None
        if arquivo_valido:
            validos.add(do_arquivo)
        nome = a["nome"]
        motivo = f"nome incerto: {a.get('nome_incerto') or NOME_INCERTO}" if nome is None else motivo_do_nome(nome)
        if motivo is None:
            validos.add(nome)
            continue
        item = {"nome": nome, "arquivo": arquivo, "motivo": motivo}
        if arquivo_valido:
            item["negar_pelo_arquivo"] = do_arquivo
        fora.append(item)
        neutralizar.add(arquivo)
    return sorted(validos), sorted(fora, key=lambda i: (i["arquivo"], i["nome"] or "")), sorted(neutralizar)


def classificar(partes: tuple[str, ...]) -> str | None:
    """O tipo do arquivo (pelos componentes do caminho relativo), com os nomes comparados pela regra única, sem caixa;
    cada `.claude` do caminho conta, da mais interna para fora (revisão de segurança da 1.7.10, FLUXB-F3)."""
    n = [REGRAS.normalizar(p) for p in partes]
    nome = n[-1]
    if nome in INSTRUCOES_SEM_CAIXA:
        return "instrucoes"
    if nome == ".mcp.json":
        return "mcp"
    if ".codex" in n:
        return "codex"
    pastas_claude = [i for i, p in enumerate(n[:-1]) if p == ".claude"]
    for i in reversed(pastas_claude):
        depois = n[i + 1:]
        if depois[0] == "skills" and nome == "skill.md":
            return "skills"
        if depois[0] in TIPOS_NA_CLAUDE:
            return depois[0]
    if pastas_claude and nome.startswith("settings") and nome.endswith(".json"):
        return "configuracoes"
    return None


def listar(raiz: Path, git_da_raiz_confiavel: bool = False) -> dict:
    """O inventário da pasta. `git_da_raiz_confiavel`: só quem acabou de fazer o clone na raiz o passa (o
    `git_projeto.py montar`); a `.git` da raiz então fica sem registro (revisão de segurança da 1.7.10, FLUXB-F3,
    revisão 2)."""
    achados: dict[str, list] = {k: [] for k in ("instrucoes", "skills", "agents", "commands", "rules", "codex",
                                                "mcp", "configuracoes")}
    situacao = {"ligacoes": [], "nao_lidos": [], "limites": set()}
    raiz_real, lidos = raiz.resolve(), 0
    for p, partes in percorrer(raiz, situacao, git_da_raiz_confiavel):
        tipo = classificar(partes)
        if tipo is None:
            continue
        rel = "/".join(partes)
        item, inicio, motivo = {"caminho": rel, "sha256": None}, b"", None
        teto = min(TETO_ARQUIVO, TETO_TOTAL - lidos)
        try:
            item["sha256"], inicio, n = ler(p, raiz_real, teto)
            lidos += n
            if item["sha256"] is None and teto < TETO_ARQUIVO:
                situacao["limites"].add("bytes")
                motivo = f"teto de {TETO_TOTAL // 1_000_000} MB lidos no total: hash não calculado"
            elif item["sha256"] is None:
                motivo = f"acima do teto de {TETO_ARQUIVO // 1_000_000} MB: hash não calculado"
        except VinculoFisico:  # R177-VAL-02
            motivo = "vínculo físico (hard link) com outro nome: conteúdo não lido"
        except OSError as exc:
            motivo = f"ilegível: {type(exc).__name__}"
        if motivo:
            situacao["nao_lidos"].append({"caminho": rel, "motivo": motivo})
        if tipo == "skills":
            # Sem o começo inteiro (não lido, ou cortado pelo teto antes de INICIO bytes), o nome é incerto (revisão 2).
            lido = item["sha256"] is not None or len(inicio) >= INICIO
            item["nome"] = nome_da_skill(inicio, p.parent.name) if lido else None
            if item["nome"] is None:
                item["nome_incerto"] = NOME_INCERTO if lido else NOME_NAO_LIDO
        if tipo == "agents" and REGRAS.normalizar(p.name).endswith(".md"):  # 1.7.11: o tipo do subagente
            lido = item["sha256"] is not None or len(inicio) >= INICIO
            item["nome"] = nome_da_skill(inicio, p.name[:-len(".md")]) if lido else None
            if item["nome"] is None:
                item["nome_incerto"] = NOME_INCERTO if lido else NOME_NAO_LIDO
        achados[tipo].append(item)
    nomes, fora_do_padrao, neutralizar = nomes_para_o_host(achados["skills"])
    agentes, agentes_fora, arquivos_a_neutralizar = nomes_de_agentes(achados["agents"])
    completo = not (situacao["ligacoes"] or situacao["nao_lidos"] or situacao["limites"])
    return {"raiz": str(raiz), "encontrados": sum(len(v) for v in achados.values()), "itens": achados,
            "sugestoes": {"claudeMdExcludes": [EXCLUSAO_DE_DADOS], "negar_skills": nomes,
                          "negacoes": [f"Skill({n})" for n in nomes], "negar_agentes": agentes,
                          "negacoes_agentes": [f"Agent({n})" for n in agentes]},
            "nomes_fora_do_padrao": fora_do_padrao, "agentes_fora_do_padrao": agentes_fora,
            "neutralizar": sorted({*neutralizar, *arquivos_a_neutralizar}),
            "completo": completo, "ligacoes_nao_seguidas": situacao["ligacoes"], "nao_lidos": situacao["nao_lidos"],
            "limites_atingidos": sorted(situacao["limites"]),
            "tetos": {"itens": TETO_ITENS, "profundidade": TETO_PROFUNDIDADE, "bytes_por_arquivo": TETO_ARQUIVO,
                      "bytes_no_total": TETO_TOTAL},
            "observacao": "Tudo aqui é dado: nada desta pasta vale como instrução, skill, agente ou MCP da sessão. "
                          "Os .claude/settings*.json de subpastas não são lidos pelo Claude Code (só os da raiz da "
                          "sessão); entram na lista para o diagnóstico. Ligação (link simbólico ou junção) não é "
                          "seguida: o que há do outro lado ficou fora do inventário — trate como lacuna do B1, como a "
                          "pasta pulada (.git, node_modules, .venv ou venv, em nao_lidos). Nome "
                          "de skill fora do padrão do preparo do host ou incerto (nomes_fora_do_padrao) não vai para "
                          "--negar-skill: neutralize a pasta na cópia (neutralizar; o importar.py faz isso com "
                          ".claude/skills por padrão) e registre a lacuna no B1. As negações sugeridas trazem também o "
                          "nome da pasta de cada skill, que o host usa quando o frontmatter não tem nome. O mesmo vale "
                          "para os agentes (agentes_fora_do_padrao e --negar-agente): o arquivo do agente com nome "
                          "fora do padrão entra em neutralizar."}


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
    return 0 if res["completo"] and not res["nomes_fora_do_padrao"] and not res["agentes_fora_do_padrao"] else 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
