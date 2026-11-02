#!/usr/bin/env python3
"""Plugin candidato de um projeto: montar, conferir e preparar a revisão (1.7.10; DESENHO-1.7.10 §8.2; contratos do
lote 2, §0, §3, §5 `plugins[]`, §6 e §8; pacote PLUGINS). Sem ele, as skills, os agentes e os comandos de cada projeto
não chegam à ficha de aberturas.

  python plugin_candidato.py montar   --raiz R --projeto P --nome N --origem <pasta em projects/P> [--descricao T]
  python plugin_candidato.py conferir --pasta <candidato> [--projeto P]
  python plugin_candidato.py revisar  --pasta <candidato> [--saida <arquivo .md em projects/P/outputs/>]

Honestidade (contratos, §0): nada daqui abre coisa alguma. O candidato só vale depois que o titular o revisa, o lista
na ficha de aberturas (`plugins[] {nome, origem, manifesto_sha256}`) e a assina pela ferramenta fixa dele, e depois do
canário no ambiente real; até lá nenhuma sessão o carrega. As recusas daqui são do código (lista positiva e cópia que
não segue ligação), não barreira do sistema: no Ubuntu com a raiz em /mnt/e, o sandbox não confinou os comandos nas
sondas de 31/10/2026. Quem instala é o preparo do titular, fora da sessão, conferindo de novo pelo manifesto.

Manifesto: `manifesto(pasta) -> (dict, sha256)` com `{"schema_version": "fundacao.plugin_candidato/1", "nome": <nome
da pasta>, "arquivos": [{"caminho", "bytes", "sha256"}]}` — todo arquivo comum da árvore, caminho relativo com '/', na
ordem do código Unicode. O sha256 é a receita única do kit (emenda E3 dos contratos; integração, item I4):
`aberturas_plugins.sha256_do_manifesto(arquivos)` do kit desta skill (assets/fundacao-kit, carregado pelo caminho), o
SHA-256 do JSON compacto da lista `arquivos` (sem `schema_version` nem `nome`): o mesmo valor do `abertura preparar`,
da ferramenta do titular e do preparo do host, e o `plugins[].manifesto_sha256` da ficha. O nome do plugin fica preso
pelo `plugin.json`, que entra no hash (o `name` dele tem de ser o da pasta e o da ficha). Cada arquivo é lido pelo
caminho conferido (`copia_segura.abrir_comum`, por `_ler`: sem seguir ligação, um nome só), uma vez: os mesmos bytes
vão para o hash e para a conferência do conteúdo; ligação, junção, vínculo físico, dispositivo, FIFO, nome que não é
UTF-8, nome forte e pasta de segredo da regra única (recusados sem ler o arquivo), o caminho
`projects/<p>/plugins-candidatos/<nome>` que passa por ligação, o bit de execução fora do Windows (salvo numa montagem
9p ou drvfs sem a opção metadata; emenda E9), o conteúdo de executável (`#!`, ELF ou MZ no começo), em todo sistema, e
os tetos (`TETO`, conferidos também nos bytes lidos) recusam (`CandidatoRecusado`). O manifesto não julga o resto do
conteúdo: isso é do `conferir`.

Forma aceita (lista positiva, como a crítica do desenho pediu: o que não está nela recusa), nunca mais frouxa que a
regra do kit (emenda E4; integração, item I12: um candidato conforme aqui e recusado no `abertura preparar` enganaria
a sessão):
- `.claude-plugin/plugin.json` (só ele ali): `name` igual à pasta, `description` e, opcionais, `version` e `author`
  {name, email, url}. Hooks, MCP, LSP, monitores, mods e caminhos próprios de componente rodam fora do sandbox ou
  apontam para fora da forma: 1.7.11 (na raiz, `hooks/`, `bin/`, `monitors/`, `scripts/`, `.mcp.json`, `.lsp.json`,
  `settings*.json`, scripts e binários recusam com a mesma marca);
- `skills/<x>/SKILL.md` com arquivos de apoio em subpastas; `agents/*.md` (com name e description); `commands/*.md`;
  na raiz, só a licença: LICENSE, LICENSE.md ou LICENSE.txt (`LICENCAS`, dentro do `NA_RAIZ_DO_PLUGIN` do kit;
  NOTICE e COPYING, não: o texto deles vai junto no LICENSE);
- tipos: só Markdown (.md) em skills/, agents/ e commands/, como no kit; fora do Windows, nenhum arquivo com bit de
  execução (o kit o recusa), salvo numa montagem 9p ou drvfs sem a opção metadata (o DrvFs do WSL, /mnt/<letra>), onde
  todo arquivo aparece 0777 e o bit não prova nada (`_sem_prova_do_bit`, pela regra do kit; emenda E9); e, em todo
  sistema, nenhum arquivo que comece como executável (`#!`, ELF ou MZ): o kit só o confere no DrvFs sem metadata, e o
  instalador do host no Ubuntu, que lê a raiz em /mnt/<letra>, o recusaria (revisão da integração, rodada 2: a sessão do
  Windows dava conforme a um candidato que o host não instala; a sessão pode ser mais estrita, emenda E4). Texto em
  UTF-8, sem caractere de controle, sem CR sozinho nem separador de linha do Unicode (o YAML do Claude Code os lê como
  quebra de linha e veria chaves de cabeçalho que esta conferência não vê; LF e CRLF valem), sem controle de direção
  nem os caracteres de etiqueta do Unicode (escondem texto do titular); no Markdown, o U+FEFF (BOM) só no começo, onde
  é tirado antes do cabeçalho, como o Claude Code faz (fora do começo, recusa: emenda E8). Script, binário, pacote e
  todo outro tipo: recusados (1.7.11);
- nomes: nada oculto salvo `.claude-plugin` (sem `.claude/`, `.mcp.json`...), sem pasta `hooks/`, `bin/`,
  `node_modules/`, sem configuração (`settings*.json`, `hooks.json`, `plugin.json` fora do lugar, `package.json`...),
  sem arquivo de instrução (CLAUDE.md, AGENTS.md), sem nome forte nem pasta de segredo da regra única (fortes +
  pastas, `regras_de_segredo.py`: recusados sem ler, nem para o hash; os fracos só ficam marcados na revisão), sem o
  que o Windows recusa (controle, tab e quebra de linha inclusive), sem caractere da área privada do Unicode (o DrvFs
  o troca por um daqueles entre o Windows e o Ubuntu: reconferência da integração, rodada 2) e sem dois nomes que só
  diferem pela caixa ou pela forma Unicode. Nome do plugin: o `NOME_PLUGIN` da ficha (`aberturas_regras` do kit:
  minúsculas, números e hífen, até 64), que o `abertura preparar` exige; das skills e dos comandos: o `NOME_DE_SKILL`
  do preparo do host, sem ':' e sem '.' no fim; o nome do plugin com '--' (fora do kebab-case) ou que cite claude,
  anthropic ou cc-plugin sai com aviso (o validador do Claude Code avisa ou recusa: `KEBAB`, `MARCAS_DA_ANTHROPIC`);
- cabeçalho YAML de `SKILL.md`, `agents/*.md` e `commands/*.md`, lido de forma conservadora (`cabecalho`): só
  `chave: valor` no primeiro nível, com as chaves da lista de cada tipo (`CHAVES_DE_SKILL`, `CHAVES_DE_COMANDO`,
  `CHAVES_DE_AGENTE`, dentro das do kit), aberto e fechado só por '---' (no fim, no máximo espaço ou tab: E4);
  `hooks`, `mcpServers` e `permissionMode` recusam. `allowed-tools` (que vale mesmo sem confiança da pasta) só com a
  lista positiva (`FERRAMENTAS_DO_CABECALHO`): Bash, PowerShell, Monitor, WebFetch, WebSearch e MCP recusam — a
  ferramenta só abre pela ficha —, o que não está na lista também, o valor fora do formato simples (curinga fora de
  parênteses, escape, âncora, bloco) e o especificador entre parênteses com caminho para fora (também com '$' em
  qualquer ponto, que o Claude Code troca pelo argumento ou pela variável);
- execução de shell embutida (`!` seguido de crase, ou cerca de crases ou tils seguida de `!`, em qualquer ponto da
  linha: o Claude Code 2.1.302 roda o bloco ```! sem âncora de começo de linha), que roda ao invocar: recusada em
  todo .md; e, em `SKILL.md` e `commands/*.md`, referência de arquivo com '@' para fora (absoluto, '~', '..', letra
  de unidade, `file:`, '$' em qualquer ponto: o Claude Code 2.1.302 troca os argumentos e as variáveis antes de colher
  as menções; reconferência da integração, rodada 2), colhida como o Claude Code 2.1.302 a colhe: a forma entre aspas
  duplas (`@"..."`, a menção com espaço no caminho, que cruza quebra de linha) e, à parte, cada trecho sem espaço que
  começa com '@' (também dentro de um trecho entre aspas, que antes a escondia: revisão da integração, rodada 2). As
  regras de allowed-tools e da menção são as do kit (`MARKDOWN`, core/aberturas_markdown.py), que o caminho confiável
  também aplica (integração, item I16). Limite: o argumento preenchido na invocação ($ARGUMENTS) pode trazer uma
  menção inteira, que nenhuma regra sobre o arquivo vê; ali vale a negação de leitura do perfil do projeto.
Tetos (`TETO`): os do kit (`aberturas_plugins.TETO_PLUGIN`: 500 arquivos, 1 MiB por arquivo, 16 MiB no total, 12
níveis de pasta), mais 10.000 arquivos e pastas na varredura e o plugin.json até 64 KiB.
Por último, o `conferir`, o `revisar` e a conferência final do `montar` passam o candidato no disco pelo validador do
kit (`aberturas_plugins.conferir_pasta_do_plugin`, `_regra_do_kit`): o que ele recusa recusa aqui (integração, item
I17: o resto da leitura do cabeçalho, como hooks ou mcpServers citados num valor ou numa chave recuada, etiqueta,
âncora, alias, barra invertida, item '-' na coluna 0 e o cabeçalho de um Markdown de apoio), e o manifesto que ele
calcula tem de ser o daqui.

montar: copia de `--origem` (dentro de `projects/P`, sem ligação no caminho; em data/, com aviso) para
`projects/P/plugins-candidatos/P-N/`, que não pode existir. A origem é uma skill avulsa (tem SKILL.md: vira
`skills/<pasta>/`) ou uma árvore com `skills/`, `agents/` e `commands/` (uma `.claude/` ou um plugin), de cuja raiz
vem só a licença (`LICENCAS`): o resto fica listado em `nao_copiados`, com aviso para hooks, MCP, configuração e
para NOTICE, COPYING e afins. Confere tudo antes de gravar; copia por `copia_segura.copiar_conferindo(...,
sha256_esperado=<o lido na conferência>, dentro_de=<origem>)` para uma pasta temporária, grava o `plugin.json` (name
P-N e description), confere o resultado (também pela regra do kit) e só então renomeia. Recusa = nada no destino.
Caminho relativo: da pasta atual. Na sessão de um projeto (FUNDACAO_PROJECT, FUNDACAO_RAIZ), outro projeto ou outra
raiz recusam: o script não troca de projeto (a variável só restringe, nunca amplia).
conferir: a forma, as regras e os tetos; imprime o manifesto e o `manifesto_sha256` (só quando conforme), os
componentes com o jeito novo de chamar (`/P-N:<skill>`) e cada motivo. Na sessão de um projeto, `conferir` e
`revisar` só leem pasta cujo caminho real (ligação resolvida) fica em `<FUNDACAO_RAIZ>/projects/<p>` (sem
FUNDACAO_RAIZ, num caminho real com `projects/<p>`): outro projeto, o data/ dele e outra raiz recusam, também fora de
plugins-candidatos/ (isolamento lógico, contratos §0).
revisar: o esqueleto da revisão do titular (instruções, scripts, rede, segredos): arquivos, domínios e ferramentas
citados, trechos que parecem mandar ignorar regras ou ler fora do projeto, marcados sem julgar; todo texto vindo do
candidato vai entre crases (ali o Markdown não interpreta HTML, comentário nem link: nada esconde parte da revisão).
Só lê o candidato; com `--saida`, grava só esse arquivo (novo, em `projects/P/outputs/`, sem nome oculto como
`.claude/` ou `.porteiro/`, sem arquivo de instrução como CLAUDE.md ou AGENTS.md, sem seguir ligação); sem, imprime o
Markdown.
Saída JSON. Códigos: 0 feito ou conforme; 2 recusado (com cada motivo) ou uso incorreto.
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
from datetime import datetime, timezone
from fnmatch import fnmatchcase
from pathlib import Path
from urllib.parse import urlsplit

AQUI = Path(__file__).resolve().parent
ESQUEMA = "fundacao.plugin_candidato/1"
CANDIDATOS = "plugins-candidatos"
PREFIXO_TEMP = ".montando-"
VARIAVEL_PROJETO, VARIAVEL_RAIZ = "FUNDACAO_" + "PROJECT", "FUNDACAO_" + "RAIZ"
# A regra do preparo do host para o nome em `Skill(<nome>)` (assets/host/preparo_host.py, NOME_DE_SKILL), repetida
# aqui (este script não importa o preparo) e conferida igual por teste.
NOME_DE_SKILL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
ID_PROJETO = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")  # o identificador do kit (fundacao/core/paths.py)
# O validador de plugin do Claude Code 2.1.302 aceita nome fora deste padrão, mas avisa (a sincronização com o
# Claude.ai exige kebab-case), e recusa ou avisa o nome de terceiro que passa por um da Anthropic (começar com
# claude-, anthropic-, anthropics- ou cc-plugin-, ser claude, claude-code ou claude-mods, pôr official ao lado de claude
# ou anthropic; citar claude ou anthropic só avisa). Aqui, os dois são aviso: o canário confere a carga.
KEBAB = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MARCAS_DA_ANTHROPIC = ("claude", "anthropic", "cc-plugin")
LIMITE_DE_MOTIVOS = 200
# Na raiz do candidato, só a licença, e só os nomes que o kit aceita lá (aberturas_plugins.NA_RAIZ_DO_PLUGIN, emenda
# E4; integração, item I12: NOTICE e COPYING passavam aqui e caíam no `abertura preparar`). O README e o CHANGELOG, que
# o kit também aceita, ficam de fora (mais estrito, como antes).
LICENCAS = frozenset({"license", "license.md", "license.txt"})
# Os outros nomes de licença e de aviso (NOTICE, COPYING, LICENCE, LICENSE-MIT...): não vêm da origem, com aviso.
OUTRA_LICENCA = re.compile(r"(?i)(?:licen[cs]e|notice|copying)(?:[-_][a-z0-9]+)*(?:\.(?:md|txt))?")
COMPONENTES = ("skills", "agents", "commands")
PASTAS_QUE_EXECUTAM = frozenset({"hooks", "bin", "mods", "monitors", "lsp", "node_modules", "__pycache__", "venv"})
CONFIGURACOES = ("settings*.json", "*.mcp.json", "mcp.json", "hooks.json", "*.lsp.json", "lsp.json", "plugin.json",
                 "marketplace.json", "package.json", "package-lock.json")
INSTRUCOES = frozenset({"claude.md", "claude.local.md", "agents.md", "agents.override.md"})
EXECUTAVEIS = frozenset(".py .pyc .pyw .sh .bash .zsh .fish .ps1 .psm1 .bat .cmd .js .mjs .cjs .ts .mts .cts .tsx .jsx "
                        ".exe .dll .so .dylib .bin .jar .class .rb .pl .php .lua .wasm .vbs .wsf .msi .com .scr .node "
                        ".mcpb .dxt .appimage .deb .rpm .zip .tar .gz .tgz .7z".split())  # contém as do kit (item I12)
RESERVADOS = frozenset({"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                        *(f"lpt{i}" for i in range(1, 10))})
# O que a raiz de uma origem leva e não vem para o candidato, com aviso (o que dependia disso pode não funcionar); na
# raiz do candidato, o mesmo recusa com a marca da 1.7.11 (contratos §5; pacote PLUGINS, item 3).
QUE_EXECUTAM_NA_ORIGEM = frozenset({"hooks", "hooks.json", ".mcp.json", "mcp.json", "settings.json", "bin", "mods",
                                    "settings.local.json", ".claude-plugin", ".lsp.json", "monitors", "scripts"})
QUE_EXECUTA = "hooks, MCP, LSP, monitores, configuração e executáveis do plugin: 1.7.11"
CHAVES_DO_PLUGIN = ("name", "version", "description", "author")
CHAVES_DO_AUTOR = ("name", "email", "url")
# Cabeçalho: só chaves que descrevem ou restringem (nenhuma roda código, abre servidor ou concede permissão), e só as
# que o kit também aceita para o tipo (aberturas_plugins.CHAVES_DO_FRONTMATTER; emenda E4, integração, item I12):
# saíram `version`, `context` e `agent` das skills, `name`, `paths` e essas dos comandos e `skills` dos agentes, que o
# kit recusa. `arguments` e `disallowed-tools`, que o kit aceita, continuam fora (mais estrito).
CHAVES_DE_SKILL = frozenset({"name", "description", "license", "compatibility", "metadata", "allowed-tools",
                             "argument-hint", "disable-model-invocation", "user-invocable", "model", "effort", "paths",
                             "when_to_use"})
CHAVES_DE_COMANDO = CHAVES_DE_SKILL - {"name", "paths"}
CHAVES_DE_AGENTE = frozenset({"name", "description", "tools", "disallowedTools", "model", "color", "effort",
                              "maxTurns"})
CHAVES_QUE_ABREM = {"hooks": "hooks (rodam fora do sandbox): 1.7.11",
                    "mcpServers": "servidores MCP (rodam fora do sandbox): 1.7.11",
                    "permissionMode": "permissionMode (muda as permissões da sessão)"}
# allowed-tools (FERRAMENTAS_DO_CABECALHO, SO_PELA_FICHA) e a menção '@' (REFERENCIA): as regras do kit,
# core/aberturas_markdown.py, carregadas abaixo (integração, item I16: as mesmas no caminho confiável).
# O Claude Code 2.1.302 roda `/```!\s*\n?([\s\S]*?)\n?```/g` (sem âncora de começo de linha) e
# `/(?<=^|\s)!`([^`]+)`/gm` ao invocar: aqui, qualquer `!` seguido de crase e qualquer cerca (crases ou tils) seguida
# de `!`, em qualquer ponto (mais casos, nunca menos). A cerca só começa onde a sequência começa (o lookbehind): sem
# ele, cada posição de uma linha longa de crases varreria o resto dela (tempo quadrático num arquivo de 1 MiB).
SHELL_EMBUTIDO = re.compile(r"!`|(?<!`)`{3,}[ \t]*!|(?<!~)~{3,}[ \t]*!")
CONTROLE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069\U000e0000-\U000e007f]")
# CR sozinho e os separadores de linha do Unicode: o YAML 1.2 lê o CR sozinho como quebra de linha (e o 1.1, também
# U+2028 e U+2029), e o Claude Code passa o bloco cru ao `Bun.YAML.parse`; uma chave depois deles ficaria escondida
# de um leitor que só quebra no LF. O NEL (U+0085) já é controle.
QUEBRA_ESCONDIDA = re.compile(r"\r(?!\n)|[\u2028\u2029]")
LINHAS = re.compile(r"\r\n|[\r\n\x85\u2028\u2029]")  # o cabeçalho quebra em toda quebra que algum YAML aceite
INVISIVEIS = re.compile("[\u00ad\u200b-\u200f\u2060-\u2064\ufeff]")
# A chave colada no ':' (`name : x` recusa, como no kit: _CHAVE_DE_PRIMEIRO_NIVEL; integração, item I12).
CHAVE = re.compile(r"([A-Za-z][A-Za-z0-9_-]*):(?:[ \t](.*))?")
OPACO = re.compile(r"[A-Za-z0-9+/=_-]{32,}")  # possível valor de segredo: mascarado nos trechos da revisão
# O valor depois de senha, password, token, api_key ou secret seguidos de ':' ou '=' (até 30 caracteres entre eles):
# mascarado mesmo curto (reconferência do pacote PLUGINS: "a senha do banco: <valor>" saía inteiro no REVISAO.md).
VALOR_DE_SEGREDO = re.compile(r"(?i)(\b(?:senha|password|passwd|token|api[_-]?key|secret)\b[^:=\n]{0,30}?[:=]\s*)"
                              r"(\S+)")
URL = re.compile(r"(?i)\b(?:https?|wss?|ftp)://[^\s<>\"'`)\]}|]+")
DOMINIO = re.compile(r"(?i)\bdomain:([a-z0-9*][a-z0-9.*-]*\.[a-z]{2,})")
WWW = re.compile(r"(?i)(?<![\w.@/-])www\.[a-z0-9-]+(?:\.[a-z0-9-]+)+")
CITADAS = re.compile(r"\b(?:Bash|PowerShell|WebFetch|WebSearch|Monitor|BashOutput|KillShell|NotebookEdit|TodoWrite|"
                     r"ExitPlanMode|SlashCommand)\b|\b(?:Read|Write|Edit|MultiEdit|Glob|Grep|Skill|Task|Agent)(?=\()"
                     r"|\bmcp__[A-Za-z0-9_-]+(?:__[A-Za-z0-9_*-]+)?")
# Marcas da revisão (padrões de texto, sem julgamento): a revisão é do titular (DESENHO §8.2: instruções, scripts,
# rede e segredos).
PADROES = (
    ("instrucao", re.compile(r"(?i)\b(?:ignore|disregard|forget|override|bypass|circumvent)\b[^\n]{0,60}?\b(?:"
                             r"instructions?|rules?|guidelines?|polic(?:y|ies)|restrictions?|guardrails?|safety|"
                             r"permissions?|system prompt|previous|prior)\b")),
    ("instrucao", re.compile(r"(?i)\b(?:ignor[ae]\w*|desconsider\w*|esque[cç]\w*|contorn\w*|burl\w*|dribl\w*|"
                             r"sobrescrev\w*|desativ\w*|deslig\w*)\b[^\n]{0,60}?\b(?:instru[cç]\w*|regras?|"
                             r"orienta[cç]\w*|pol[ií]tic\w*|restri[cç]\w*|limites?|seguran[cç]a|hooks?|sandbox|"
                             r"permiss\w*|anteriores)\b")),
    ("instrucao", re.compile(r"(?i)\b(?:sem|without)\s+(?:pedir|perguntar|confirmar|avisar|asking|confirmation|"
                             r"permission|telling)\b|dangerously|bypasspermissions|skip-permissions|--no-verify|"
                             r"allowunsandboxed|disablesandbox|--yolo")),
    ("instrucao", re.compile(r"(?i)\b(?:n[aã]o|never|don'?t|do not)\s+(?:conte|diga|mencione|informe|avise|revele|"
                             r"mostre|tell|mention|inform|reveal|show)\b[^\n]{0,40}?\b(?:usu[aá]rio|titular|user|"
                             r"human|humano)s?\b")),
    ("fora", re.compile(r"(?i)(?<![\w.])(?:/mnt/[a-z](?!\w)|/home/|/root\b|/etc/|/var/|/run/|/tmp/|/usr/|/opt/)|~/|"
                        r"\$home\b|%userprofile%|%appdata%|%localappdata%|\\\\wsl|(?<![a-z])[a-z]:[\\/]")),
    ("fora", re.compile(r"\.\.[\\/]|(?i:\bprojects[\\/][a-z0-9-]+|\bstate[\\/]|state\.sqlite|\.claude[\\/]|"
                        r"\.porteiro|\.fundacao\b)")),
    ("comando", re.compile(r"(?i)(?<![\w-])(?:curl|wget|npm|npx|pnpm|yarn|pip3?|pipx|uvx|python3?|bash|sudo|chmod|"
                           r"ssh|scp|rsync|docker|kubectl|powershell|pwsh|iwr|iex|invoke-webrequest|"
                           r"invoke-expression|git\s+(?:push|clone|fetch|pull|remote)|rm\s+-rf)(?![\w-])")),
    ("segredo", re.compile(r"(?i)\.ssh\b|\bid_(?:rsa|ed25519|ecdsa|dsa)\b|(?<![\w.])\.env\b|\.git-credentials|"
                           r"\.aws[\\/]|\.netrc|\.npmrc|\.pypirc|\bcredentials\b|\.kube[\\/]|kubeconfig|"
                           r"\bapi[_-]?key\b|\bsenha\b|\bpassword\b|\btoken\b")),
)
LIMITE_DE_MARCAS = 100


def _carregar(nome: str):
    """Um script ao lado deste, pelo caminho (sem mexer no `sys.path`)."""
    spec = importlib.util.spec_from_file_location(f"_plugin_candidato_{nome}", AQUI / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _carregar_do_kit(modulo: str):
    """Um módulo do kit desta skill (assets/fundacao-kit/fundacao), pelo caminho, num pacote de nome próprio: sem mexer
    no `sys.path` nem no `fundacao` de quem importa este script (emendas E3 e E4: a receita do manifesto e a regra do
    plugin são as do kit; integração, itens I4 e I12)."""
    pacote, base = "_plugin_candidato_kit", AQUI.parent / "assets" / "fundacao-kit" / "fundacao"
    carregado = sys.modules.get(pacote)
    if carregado is None:
        spec = importlib.util.spec_from_file_location(pacote, base / "__init__.py",
                                                      submodule_search_locations=[str(base)])
        carregado = importlib.util.module_from_spec(spec)
        sys.modules[pacote] = carregado
        try:
            spec.loader.exec_module(carregado)
        except BaseException:
            del sys.modules[pacote]
            raise
    elif list(carregado.__path__) != [str(base)]:
        raise ImportError(f"{pacote}: já carregado de outra cópia do kit ({list(carregado.__path__)})")
    return importlib.import_module(f"{pacote}.{modulo}")


COPIA = _carregar("copia_segura")        # leitura e cópia sem seguir ligação nem vínculo físico (contratos, §8)
REGRAS = _carregar("regras_de_segredo")  # a regra única: fortes + pastas recusam (contratos, §3)
GRAVACAO = _carregar("gravacao_segura")  # pasta e arquivo novos sem seguir ligação (revisar --saida)
KIT = _carregar_do_kit("core.aberturas_plugins")  # a receita do manifesto e a regra do plugin (emendas E3 e E4)
FICHA = _carregar_do_kit("core.aberturas_regras")  # o nome de plugin que a ficha aceita (NOME_PLUGIN)
# allowed-tools e menção '@' (integração, item I16): a regra do kit, que o caminho confiável também confere. Lista
# positiva do cabeçalho: só o que lê, grava no projeto ou delega; Bash, PowerShell, Monitor, WebFetch, WebSearch e MCP
# (SO_PELA_FICHA) só abrem pela ficha; a menção como o Claude Code 2.1.302 a colhe (as duas varreduras dele, à parte:
# a forma entre aspas, cruzando quebra de linha, e cada trecho sem espaço que começa com '@'), mais a REFERENCIA.
MARKDOWN = _carregar_do_kit("core.aberturas_markdown")
FERRAMENTAS_DO_CABECALHO, SO_PELA_FICHA = MARKDOWN.FERRAMENTAS_DO_CABECALHO, MARKDOWN.SO_PELA_FICHA
REFERENCIA = MARKDOWN.REFERENCIA
# O conteúdo de executável, em todo sistema (emenda E9; revisão da integração, rodada 2): o bit de execução só vale
# fora de uma montagem 9p ou drvfs sem a opção metadata, e o conteúdo, que o kit confere lá, a sessão confere sempre.
PELO_CONTEUDO = ("executável pelo conteúdo (#!, ELF ou MZ no começo): o kit o recusa no DrvFs sem a opção metadata "
                 "(/mnt/<letra> no WSL, onde o bit de execução não prova nada), e o instalador do host lê a raiz por "
                 "lá; esta conferência o recusa em todo sistema: 1.7.11")
# Tetos: os do kit (aberturas_plugins.TETO_PLUGIN; emenda E4, integração, item I12: antes 8 MiB por arquivo e 64 MiB
# no total, e sem teto de arquivos), mais os daqui, mais estritos (a varredura e o plugin.json).
TETO = {"entradas": 10000, "arquivos": KIT.TETO_PLUGIN["arquivos"], "arquivo": KIT.TETO_PLUGIN["bytes_arquivo"],
        "total": KIT.TETO_PLUGIN["bytes"], "profundidade": KIT.TETO_PLUGIN["niveis"], "plugin.json": 64 << 10}


class CandidatoRecusado(ValueError):
    """Recusado, com cada motivo em `motivos`: nada foi gravado no destino."""

    def __init__(self, motivos):
        self.motivos = [motivos] if isinstance(motivos, str) else list(motivos)
        resto = len(self.motivos) - 3
        super().__init__("; ".join(self.motivos[:3]) + (f" (e mais {resto})" if resto > 0 else ""))


# --- nomes e manifesto -----------------------------------------------------------------------------------------------
def _exibir(texto) -> str:
    """Texto do candidato para mostrar: sem controle nem surrogate solto (a saída em UTF-8 não quebra)."""
    return CONTROLE.sub(" ", str(texto).encode("utf-8", "replace").decode("utf-8"))


def nome_valido(nome) -> bool:
    """Nome do plugin, de uma skill ou de um comando: o `NOME_DE_SKILL` do preparo do host, sem ':' (separa o plugin
    da skill em `/<plugin>:<skill>`, e o Windows não o aceita em nome de pasta) e sem '.' no fim (o Windows o tira)."""
    return isinstance(nome, str) and bool(NOME_DE_SKILL.fullmatch(nome)) and ":" not in nome and not nome.endswith(".")


def nome_de_plugin_valido(nome) -> bool:
    """Nome do plugin: o de `nome_valido` e o `NOME_PLUGIN` da ficha de aberturas (aberturas_regras do kit: minúsculas,
    números e hífen, até 64), que o `abertura preparar` exige em `plugins[].nome` (emenda E4; integração, item I12:
    `demo-Kit_v2` passava aqui, com aviso, e caía na ficha)."""
    return nome_valido(nome) and bool(FICHA.NOME_PLUGIN.fullmatch(nome))


def _manifesto(nome: str, lista: list) -> dict:
    """O manifesto mostrado: `schema_version` e `nome` em volta da lista `arquivos` ({caminho, bytes, sha256}, em ordem
    de caminho), a única parte que entra no `manifesto_sha256` (aberturas_plugins.sha256_do_manifesto; emenda E3)."""
    return {"schema_version": ESQUEMA, "nome": nome, "arquivos": sorted(lista, key=lambda a: a["caminho"])}


def _exigir_pasta(pasta: Path) -> None:
    """A pasta do candidato existe, é pasta e não é ligação; no lugar padrão (`projects/<p>/plugins-candidatos/
    <nome>`), nenhum componente desde `projects/` é ligação (contratos §5: origem "sem ligação"; uma
    plugins-candidatos/ trocada por junção não muda o candidato em silêncio)."""
    try:
        st = os.lstat(pasta)
    except OSError as exc:
        raise CandidatoRecusado(f"{pasta}: não existe ({exc.strerror or exc})") from None
    if COPIA.e_ligacao(st) or not stat.S_ISDIR(st.st_mode):
        raise CandidatoRecusado(f"{pasta}: é ligação (link simbólico ou junção) ou não é pasta")
    if _projeto_do_caminho(pasta) is not None and GRAVACAO.com_ligacao(pasta.parents[3], "/".join(pasta.parts[-4:])):
        raise CandidatoRecusado(f"{pasta}: o caminho desde projects/ passa por ligação (link simbólico ou junção)")


def _varrer(base: Path, prefixo: str = "", conta: dict | None = None, *,
            bit_de_execucao: bool = False) -> tuple[list, list, list]:
    """(arquivos [(rel, caminho)], pastas [rel], motivos) da árvore de `base`, sem seguir ligação; `rel` com '/' e o
    `prefixo` na frente (as coordenadas do candidato). Para ao passar dos tetos (`conta` soma entre chamadas). Com
    `bit_de_execucao` (o candidato no disco fora de uma montagem 9p ou drvfs sem metadata, onde o bit não prova nada:
    `_sem_prova_do_bit`, emenda E9; a origem do `montar` não, que a cópia sai 0o444), fora do Windows o arquivo com bit
    de execução recusa, como no kit (aberturas_plugins: "executável ou script no plugin: só na 1.7.11"; integração,
    item I12), num motivo só com os primeiros nomes. O conteúdo de executável é do `_avaliar` e do `manifesto`."""
    conta = {"entradas": 0, "total": 0} if conta is None else conta
    arquivos, pastas, motivos, pilha, com_bit = [], [], [], [(base, prefixo)], []
    while pilha:
        atual, rel_atual = pilha.pop()
        try:
            with os.scandir(atual) as it:
                nomes = sorted(e.name for e in it)
        except OSError as exc:
            motivos.append(f"{rel_atual or '.'}: não deu para listar ({exc.strerror or exc})")
            continue
        for nome in nomes:
            rel = f"{rel_atual}/{nome}" if rel_atual else nome
            conta["entradas"] += 1
            if conta["entradas"] > TETO["entradas"]:
                motivos.append(f"passa do teto de {TETO['entradas']} arquivos e pastas")
                pilha.clear()
                break
            if any(0xD800 <= ord(c) <= 0xDFFF for c in nome):
                motivos.append(f"{_exibir(rel)}: nome que não é UTF-8")
                continue
            caminho, exibido = atual / nome, _exibir(rel)
            try:
                st = os.lstat(caminho)
            except OSError as exc:
                motivos.append(f"{exibido}: não deu para examinar ({exc.strerror or exc})")
                continue
            if COPIA.e_ligacao(st):
                motivos.append(f"{exibido}: ligação (link simbólico ou junção): nunca seguida")
            elif stat.S_ISDIR(st.st_mode):
                if rel.count("/") >= TETO["profundidade"]:
                    motivos.append(f"{exibido}: passa do teto de {TETO['profundidade']} níveis de pasta")
                else:
                    pastas.append(rel)
                    pilha.append((caminho, rel))
            elif not stat.S_ISREG(st.st_mode):
                motivos.append(f"{exibido}: não é arquivo comum nem pasta (dispositivo, FIFO ou socket)")
            elif st.st_nlink != 1:
                motivos.append(f"{exibido}: vínculo físico (mais de um nome): o conteúdo pode ser de um arquivo de "
                               "fora")
            elif st.st_size > TETO["arquivo"]:
                motivos.append(f"{exibido}: passa do teto de {TETO['arquivo']} bytes por arquivo")
            else:
                conta["total"] += st.st_size
                if conta["total"] > TETO["total"]:
                    motivos.append(f"passa do teto de {TETO['total']} bytes no total")
                    pilha.clear()
                    break
                if bit_de_execucao and os.name != "nt" and st.st_mode & 0o111:
                    com_bit.append(exibido)
                arquivos.append((rel, caminho))
    if com_bit:
        exemplos = ", ".join(com_bit[:3]) + (f" e mais {len(com_bit) - 3}" if len(com_bit) > 3 else "")
        motivos.append(f"{exemplos}: bit de execução (fora do Windows, o kit recusa arquivo executável no plugin: "
                       "1.7.11; no DrvFs sem a opção metadata, como /mnt/<letra> no WSL, o bit não prova nada e vale o "
                       "conteúdo)")
    return arquivos, pastas, motivos


def _sem_prova_do_bit(pasta: Path) -> bool:
    """Emenda E9: True numa montagem 9p ou drvfs sem a opção metadata (o DrvFs do WSL, /mnt/<letra>, onde todo arquivo
    aparece 0777): lá o bit de execução não prova nada. A regra é a do kit (aberturas_plugins.bit_de_execucao_vale, que
    lê o /proc/mounts sem executar programa); no ext4, o bit vale; no Windows, não há bit. O conteúdo (`#!`, ELF ou MZ
    no começo) esta ferramenta confere em todo sistema (PELO_CONTEUDO)."""
    return os.name != "nt" and not KIT.bit_de_execucao_vale(pasta)


def _teto_de_arquivos(quantos: int) -> list:
    """O teto de arquivos do kit (TETO_PLUGIN; integração, item I12), conferido antes de ler qualquer um."""
    return [f"passa do teto de {TETO['arquivos']} arquivos do plugin (o do kit)"] if quantos > TETO["arquivos"] else []


def manifesto(pasta) -> tuple[dict, str]:
    """(manifesto, sha256) do candidato, pelo contrato do docstring do módulo. Recusa: `CandidatoRecusado`."""
    pasta = Path(os.path.abspath(pasta))
    _exigir_pasta(pasta)
    arquivos, _pastas, motivos = _varrer(pasta, bit_de_execucao=not _sem_prova_do_bit(pasta))  # emenda E9
    motivos += _teto_de_arquivos(len(arquivos))
    # Regra única (contratos §3): nome forte e pasta de segredo nunca são lidos, nem para o hash.
    motivos += [f"{_exibir(rel)}: {REGRAS.motivo(classe)} (o manifesto não o lê)" for rel, _ in arquivos
                if (classe := REGRAS.classificar(rel)) in ("forte", "pasta-de-segredo")]
    if motivos:
        raise CandidatoRecusado(motivos)
    lista, total, executaveis = [], 0, []
    for rel, caminho in arquivos:
        try:  # lido uma vez: os mesmos bytes no hash e na conferência do conteúdo, em todo sistema (PELO_CONTEUDO)
            conteudo = _ler(caminho, pasta)
        except (OSError, CandidatoRecusado) as exc:  # CopiaRecusada (ligação, vínculo físico, troca), teto ou leitura
            raise CandidatoRecusado(f"{_exibir(rel)}: {exc}") from None
        lido = {"bytes": len(conteudo), "sha256": hashlib.sha256(conteudo).hexdigest()}
        if KIT.executavel_pelo_conteudo(conteudo):
            executaveis.append(f"{_exibir(rel)}: {PELO_CONTEUDO}")
        total += lido["bytes"]
        if lido["bytes"] > TETO["arquivo"] or total > TETO["total"]:  # cresceu depois do exame
            raise CandidatoRecusado(f"{_exibir(rel)}: os bytes lidos passam do teto ({TETO['arquivo']} por arquivo, "
                                    f"{TETO['total']} no total)")
        lista.append({"caminho": rel, "bytes": lido["bytes"], "sha256": lido["sha256"]})
    if executaveis:
        raise CandidatoRecusado(executaveis)
    dados = _manifesto(pasta.name, lista)
    return dados, KIT.sha256_do_manifesto(dados["arquivos"])  # a receita única do kit (emenda E3; item I4)


def _ler(caminho: Path, dentro_de: Path) -> bytes:
    """Os bytes do arquivo, lidos uma vez pelo caminho conferido da cópia: os mesmos que são conferidos e, no
    `montar`, exigidos de novo (SHA-256) na cópia."""
    fd = COPIA.abrir_comum(caminho, dentro_de)
    try:
        partes, n = [], 0
        while bloco := os.read(fd, COPIA.BLOCO):
            n += len(bloco)
            if n > TETO["arquivo"]:
                raise CandidatoRecusado(f"passa do teto de {TETO['arquivo']} bytes por arquivo")
            partes.append(bloco)
    finally:
        os.close(fd)
    return b"".join(partes)


# --- forma e nomes ---------------------------------------------------------------------------------------------------
def _executa_na_raiz(nome: str, e_pasta: bool) -> bool:
    """Na raiz do candidato, o que o Claude Code leria como hook, MCP, LSP, monitor, configuração ou executável do
    plugin (`hooks/`, `.mcp.json`, `settings.json`, `bin/`, `.lsp.json`, `monitors/`, `scripts/`, script, binário)."""
    dobrado = nome.casefold()
    if dobrado == ".claude-plugin":
        return False
    if e_pasta:
        return dobrado in QUE_EXECUTAM_NA_ORIGEM or dobrado.split(".", 1)[0] in PASTAS_QUE_EXECUTAM
    return (dobrado in QUE_EXECUTAM_NA_ORIGEM or any(fnmatchcase(dobrado, g) for g in CONFIGURACOES)
            or os.path.splitext(dobrado)[1] in EXECUTAVEIS)


def _motivo_da_forma(partes: list, e_pasta: bool) -> str | None:
    """None se a entrada cabe na forma do plugin (lista positiva); senão o motivo."""
    topo, nome, n = partes[0], partes[-1], len(partes)
    if n == 1:
        if e_pasta:
            if topo in (".claude-plugin", *COMPONENTES):
                return None
            return (f"pasta fora da forma do plugin ({QUE_EXECUTA})" if _executa_na_raiz(nome, True) else
                    "pasta fora da forma do plugin (só .claude-plugin/, skills/, agents/ e commands/)")
        if nome.casefold() in LICENCAS:
            return None
        return (f"arquivo fora da forma do plugin na raiz ({QUE_EXECUTA})" if _executa_na_raiz(nome, False) else
                "arquivo fora da forma do plugin na raiz (lá, só a licença: LICENSE, LICENSE.md ou LICENSE.txt, como "
                "no kit; NOTICE e COPYING vão junto no texto do LICENSE)")
    if topo == ".claude-plugin":
        return None if (n == 2 and not e_pasta and nome == "plugin.json") else \
            "em .claude-plugin/ só o plugin.json (marketplace e outros não entram)"
    if topo == "skills":
        if n == 2:
            if not e_pasta:
                return "arquivo solto em skills/ (cada skill é uma pasta com SKILL.md)"
            return None if nome_valido(nome) else "nome de skill fora do padrão do preparo do host"
        return "SKILL.md aninhado (só skills/<x>/SKILL.md)" if (n > 3 and nome.casefold() == "skill.md") else None
    if topo in ("agents", "commands"):
        if e_pasta:
            return f"subpasta em {topo}/ (só {topo}/*.md)"
        if not nome.endswith(".md"):
            return f"em {topo}/ só arquivos .md"
        if topo == "commands" and not nome_valido(nome[:-3]):
            return "nome de comando fora do padrão do preparo do host"
        return None
    return "fora da forma do plugin"


def _motivo_do_nome(rel: str, e_pasta: bool) -> str | None:
    """Regras do último nome de `rel`: portabilidade, oculto, segredo, instrução, configuração e executável (o tipo é
    de `_motivo_do_tipo`)."""
    nome = rel.rsplit("/", 1)[-1]
    base = nome.split(".", 1)[0].casefold()
    # Controle (tab e quebra de linha inclusive: o NTFS não os aceita), formatação invisível, surrogate solto e os
    # separadores de linha e de parágrafo do Unicode.
    if (CONTROLE.search(nome) or INVISIVEIS.search(nome) or any(c in '<>:"\\|?*' for c in nome)
            or any(unicodedata.category(c) in ("Cc", "Cf", "Cs", "Zl", "Zp") for c in nome)
            or nome.endswith((" ", ".")) or base in RESERVADOS or len(nome.encode("utf-8", "surrogatepass")) > 255):
        return ('nome que não funciona igual no Windows e no Ubuntu (controle, < > : " \\ | ? *, espaço ou ponto no '
                'fim, nome reservado)')
    # A área privada do Unicode (reconferência da integração, rodada 2; sondado no DrvFs em 01/11/2026): o DrvFs
    # (/mnt/<letra> no WSL) mostra no Ubuntu o U+F001 a U+F01F, U+F022, U+F02A, U+F03A, U+F03C, U+F03E, U+F03F, U+F05C e
    # U+F07C de um nome do Windows como controle e " * : < > ? \ |: a sessão e o kit do Windows aceitavam um candidato
    # que o kit do Ubuntu recusava ou lia com outro manifesto. Como no kit (aberturas_plugins._nome_que_muda), toda ela.
    if any(unicodedata.category(c) == "Co" for c in nome):
        return ('nome que não funciona igual no Windows e no Ubuntu (área privada do Unicode: o DrvFs, /mnt/<letra> no '
                'WSL, a troca por controle ou < > : " \\ | ? *, e o arquivo teria outro nome e outro manifesto)')
    if nome.startswith(".") and rel != ".claude-plugin":
        return "nome oculto (.claude/, .mcp.json, .git/ e afins não entram)"
    classe = REGRAS.classificar(rel)
    if classe in ("forte", "pasta-de-segredo"):
        return REGRAS.motivo(classe) + " (regra única: fortes e pastas não entram)"
    if e_pasta:
        return None if base not in PASTAS_QUE_EXECUTAM else \
            f"pasta {nome}/ (hooks, executáveis e pacotes de código: 1.7.11)"
    dobrado = nome.casefold()
    if dobrado in INSTRUCOES:
        return "arquivo de instrução (CLAUDE.md, AGENTS.md): carregaria como instrução da sessão"
    if rel != ".claude-plugin/plugin.json" and any(fnmatchcase(dobrado, g) for g in CONFIGURACOES):
        return "configuração do Claude Code ou de pacote de código (hooks, MCP, settings): 1.7.11"
    if os.path.splitext(dobrado)[1] in EXECUTAVEIS:
        return "script, binário ou pacote (executa ou esconde o conteúdo): 1.7.11"
    return None


def _motivo_do_tipo(rel: str) -> str | None:
    """O tipo de um arquivo pela regra do kit (aberturas_plugins: "só Markdown em skills/, agents/ e commands/";
    emenda E4, integração, item I12): fora o plugin.json e a licença da raiz (`LICENCAS`), só .md. Antes valiam aqui
    .txt, .json, .yaml, .yml, .csv e imagens, que o kit recusa: o candidato conforme caía no `abertura preparar`."""
    if rel == ".claude-plugin/plugin.json" or ("/" not in rel and rel.casefold() in LICENCAS):
        return None
    if os.path.splitext(rel.rsplit("/", 1)[-1].casefold())[1] == ".md":
        return None
    return "tipo de arquivo fora da lista (em skills/, agents/ e commands/ só Markdown .md, a regra do kit na 1.7.10)"


def _colisoes(rels) -> list:
    vistos, motivos = {}, []
    for rel in sorted(rels):
        chave = REGRAS.normalizar(rel)
        if chave in vistos and vistos[chave] != rel:
            motivos.append(f"{_exibir(rel)}: só difere de {_exibir(vistos[chave])} pela caixa ou pela forma Unicode")
        vistos.setdefault(chave, rel)
    return motivos


# --- cabeçalho e conteúdo --------------------------------------------------------------------------------------------
def cabecalho(texto: str) -> tuple[dict | None, list]:
    """O cabeçalho YAML do começo do Markdown, lido de forma conservadora: ({chave: valor bruto}, motivos), ou
    (None, []) sem cabeçalho. Vale só `chave: valor` no primeiro nível, com continuação recuada ou item '-', e
    comentário; o resto (chave entre aspas ou com ponto, '?', '<<', mapa no topo, abertura ou fecho fora da forma,
    '...') é motivo: o que este leitor não entende não pode esconder uma chave do leitor do Claude Code. As linhas
    quebram em toda quebra que algum YAML aceita (LF, CRLF, CR sozinho, NEL, U+2028 e U+2029: `LINHAS`), para uma
    chave depois de um CR sozinho não passar por parte do valor da anterior. Abre e fecha só numa linha '---' com, no
    fim, no máximo espaço ou tab (emenda E4, como o kit: um '---' seguido de NBSP não fecha aqui nem lá)."""
    linhas = LINHAS.split(texto.lstrip("\ufeff"))
    inicio = next((i for i, linha in enumerate(linhas) if linha.strip()), None)
    if inicio is None:
        return None, []
    primeira = linhas[inicio].rstrip("\r")
    if primeira.startswith("+++"):
        return {}, ["cabeçalho TOML (+++) não é aceito"]
    if not primeira.startswith("---"):
        return None, []
    motivos = [] if primeira.rstrip(" \t") == "---" else ["abertura do cabeçalho fora da forma ---"]
    # As linhas de cada chave vão numa lista e só se juntam no fim: somar texto a texto custava tempo quadrático num
    # cabeçalho de milhões de linhas. Com motivos demais, a leitura para (o arquivo já está recusado).
    chaves, atual = {}, None
    for linha in linhas[inicio + 1:]:
        linha = linha.rstrip("\r")
        if linha.rstrip(" \t") == "---":
            return {k: "\n".join(v) for k, v in chaves.items()}, motivos
        if len(motivos) >= LIMITE_DE_MOTIVOS:
            motivos.append("motivos demais no cabeçalho: a leitura parou aqui")
            break
        if linha.startswith(("---", "...")):
            motivos.append(f"linha {_exibir(linha[:20])!r} dentro do cabeçalho")
            atual = None
        elif linha[:1] in (" ", "\t", "-"):
            if atual is None:
                motivos.append("linha recuada fora de uma chave no cabeçalho")
            else:
                chaves[atual].append(linha)
        elif linha.startswith("#") or not linha.strip():
            continue
        elif not (m := CHAVE.fullmatch(linha)):
            motivos.append(f"linha do cabeçalho fora da forma 'chave: valor': {_exibir(linha[:60])!r}")
            atual = None
        elif m.group(1) in chaves:
            motivos.append(f"chave repetida no cabeçalho: {m.group(1)}")
            atual = None
        else:
            chaves[m.group(1)] = [m.group(2) or ""]
            atual = m.group(1)
    else:
        motivos.append("cabeçalho sem a linha --- de fecho")
    return {k: "\n".join(v) for k, v in chaves.items()}, motivos


# As funções de allowed-tools e da menção '@' são as do kit (integração, item I16): uma regra só, aqui e no caminho
# confiável. ferramentas_do_valor: os nomes do valor (sem o que vem entre parênteses), ou None fora do formato simples;
# _de_fora: o alvo aponta para fora do plugin; _referencias_de_fora: os alvos de fora das menções do texto.
ferramentas_do_valor = MARKDOWN.ferramentas_do_valor
_de_fora, _referencias_de_fora = MARKDOWN.de_fora, MARKDOWN.referencias_de_fora


def _escalar(valor: str | None) -> str | None:
    """O valor simples de uma linha, sem aspas; None se ausente, em várias linhas, com escape ou com indicador de
    YAML (âncora, apelido, etiqueta, bloco, mapa, lista ou comentário)."""
    if valor is None or "\n" in valor:
        return None
    v = valor.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return None if "\\" in v[1:-1] or v[0] in v[1:-1] else v[1:-1]
    return None if (v[:1] in "&*!|>{[%@`'\"" or " #" in v) else v


def _resumo(valor: str | None, limite: int = 300) -> str:
    if not valor:
        return ""
    partes = [p.strip() for p in valor.split("\n")]
    texto = " ".join(p for p in partes if p and p not in ("|", ">", "|-", ">-", "|+", ">+"))
    if len(texto) >= 2 and texto[0] == texto[-1] and texto[0] in "'\"":
        texto = texto[1:-1]
    texto = _exibir(texto)
    return texto[:limite] + ("…" if len(texto) > limite else "")


def _tipo(partes: list) -> str | None:
    if len(partes) == 3 and partes[0] == "skills" and partes[2] == "SKILL.md":
        return "skill"
    if len(partes) == 2 and partes[0] in ("agents", "commands") and partes[1].endswith(".md"):
        return "agente" if partes[0] == "agents" else "comando"
    return None


def _conferir_componente(rel: str, tipo: str, texto: str, plugin: str) -> tuple[list, dict]:
    chaves, achados = cabecalho(texto)
    motivos = [f"{rel}: {m}" for m in achados]
    chaves = chaves or {}
    permitidas = {"skill": CHAVES_DE_SKILL, "comando": CHAVES_DE_COMANDO, "agente": CHAVES_DE_AGENTE}[tipo]
    for chave in chaves:
        if chave in CHAVES_QUE_ABREM:
            motivos.append(f"{rel}: o cabeçalho declara {CHAVES_QUE_ABREM[chave]}")
        elif chave not in permitidas:
            motivos.append(f"{rel}: chave {chave} fora da lista do cabeçalho de {tipo} (pode mudar o que o Claude "
                           "Code faz)")
    ferramentas = None if tipo == "agente" else []
    if tipo != "agente" and "allowed-tools" in chaves:
        # A regra do kit (aberturas_markdown.problemas_do_allowed_tools; item I16): fora do formato simples, o que só
        # abre pela ficha, o que está fora da lista positiva e o especificador com caminho para fora (Read(//**),
        # Edit(~/.bashrc): pré-aprovaria leitura ou escrita fora do projeto sem perguntar).
        ferramentas = ferramentas_do_valor(chaves["allowed-tools"]) or []
        motivos += [f"{rel}: {_exibir(m)}" for m in MARKDOWN.problemas_do_allowed_tools(chaves["allowed-tools"])]
    elif tipo == "agente" and "tools" in chaves:  # restringe (não concede): mostrado ao titular, não recusado
        ferramentas = ferramentas_do_valor(chaves["tools"])
        ferramentas = [_resumo(chaves["tools"], 80)] if ferramentas is None else ferramentas
    proprio = rel.split("/")[1] if tipo == "skill" else rel.split("/")[1][:-3]
    nome = _escalar(chaves.get("name"))
    if "name" in chaves and not nome_valido(nome):
        motivos.append(f"{rel}: name do cabeçalho fora do padrão do preparo do host (uma linha, sem ':' nem '.' no "
                       "fim)")
    if tipo == "agente" and (not nome or not chaves.get("description", "").strip()):
        motivos.append(f"{rel}: agente sem name ou description no cabeçalho (o Claude Code não o carrega)")
    if tipo != "agente":
        if fora := _referencias_de_fora(texto):
            motivos.append(f"{rel}: referência de arquivo com @ para fora do plugin ({_exibir(', '.join(fora[:3]))}): "
                           "o Claude Code a lê ao invocar")
    chamado = nome if (tipo != "comando" and nome_valido(nome)) else proprio
    return motivos, {"tipo": tipo, "nome": chamado, "arquivo": rel,
                     "invocacao": f"{plugin}:{chamado}" if tipo == "agente" else f"/{plugin}:{chamado}",
                     "descricao": _resumo(chaves.get("description")), "ferramentas": ferramentas,
                     "cabecalho": _resumo(chaves.get("tools" if tipo == "agente" else "allowed-tools"), 200),
                     "modelo": _escalar(chaves.get("model"))}


def _conferir_plugin_json(rel: str, dados: bytes, nome: str) -> list:
    if len(dados) > TETO["plugin.json"]:
        return [f"{rel}: passa de {TETO['plugin.json']} bytes"]

    def sem_repeticao(pares):
        if len({k for k, _ in pares}) != len(pares):
            raise ValueError("chave repetida")
        return dict(pares)

    try:
        obj = json.loads(dados.decode("utf-8"), object_pairs_hook=sem_repeticao)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        return [f"{rel}: JSON ilegível ou com chave repetida ({_exibir(exc)[:80]})"]
    if not isinstance(obj, dict):
        return [f"{rel}: não é um objeto JSON"]
    motivos = [f"{rel}: chave {_exibir(k)!r} fora da lista (só name, version, description e author; hooks, MCP, LSP, "
               "monitores e caminhos próprios de componente: 1.7.11)" for k in obj if k not in CHAVES_DO_PLUGIN]
    if obj.get("name") != nome:
        motivos.append(f"{rel}: name tem de ser {nome} (o nome da pasta do candidato)")
    texto = obj.get("description")
    if not isinstance(texto, str) or not texto.strip() or len(texto) > 1024 or CONTROLE.search(texto):
        motivos.append(f"{rel}: description tem de ser um texto de 1 a 1024 caracteres, sem controle")
    versao = obj.get("version", "0")
    if not isinstance(versao, str) or not 0 < len(versao) <= 64 or CONTROLE.search(versao):
        motivos.append(f"{rel}: version tem de ser um texto curto")
    autor = obj.get("author", {})
    if not isinstance(autor, dict) or any(k not in CHAVES_DO_AUTOR or not isinstance(v, str) for k, v in autor.items()):
        motivos.append(f"{rel}: author tem de ser um objeto só com name, email e url em texto")
    return motivos


def _conferir_arquivo(rel: str, dados: bytes, plugin: str) -> tuple[list, dict | None, str | None]:
    """(motivos, componente, texto) do conteúdo de um arquivo cujo nome já passou pelas regras: o plugin.json, a
    licença da raiz e o Markdown (o resto o tipo recusa antes, como no kit: integração, item I12)."""
    if rel == ".claude-plugin/plugin.json":
        return _conferir_plugin_json(rel, dados, plugin), None, None
    ext = os.path.splitext(rel.rsplit("/", 1)[-1].casefold())[1]
    try:
        texto = dados.decode("utf-8").removeprefix("\ufeff")
    except UnicodeDecodeError:
        return [f"{rel}: não é texto UTF-8"], None, None
    if controle := CONTROLE.search(texto):
        return [f"{rel}: caractere de controle U+{ord(controle.group()):04X} (pode esconder texto do titular)"], None, \
            texto
    if quebra := QUEBRA_ESCONDIDA.search(texto):
        return [f"{rel}: CR sozinho ou separador de linha do Unicode (U+{ord(quebra.group()):04X}): o YAML do Claude "
                "Code veria linhas que esta conferência não vê (use LF ou CRLF)"], None, texto
    if ext == ".md" and MARKDOWN.BOM in texto:  # emenda E8: o BOM só é tirado no começo, como no kit
        return [f"{rel}: U+FEFF (BOM) fora do começo do Markdown: caractere invisível que esconde texto do titular (só "
                "no começo ele é tirado, como o Claude Code faz ao ler o cabeçalho)"], None, texto
    motivos, componente = [], None
    if ext == ".md":
        if SHELL_EMBUTIDO.search(texto):
            motivos.append(f"{rel}: execução de shell embutida (! seguido de crase, ou cerca de crases ou tils seguida "
                           "de !, em qualquer ponto da linha): roda ao invocar")
        if tipo := _tipo(rel.split("/")):
            achados, componente = _conferir_componente(rel, tipo, texto, plugin)
            motivos += achados
    return motivos, componente, texto


# --- conferência -----------------------------------------------------------------------------------------------------
def _avaliar(nome: str, projeto: str | None, arquivos: list, pastas: list, achados: list, base: Path,
             gerados: dict | None = None) -> tuple[dict, dict, list]:
    """Forma, nomes, conteúdo e manifesto de um candidato — no disco ou, no `montar`, ainda na origem: (resultado,
    textos, arquivos lidos). `arquivos` [(rel, caminho)] é lido dentro de `base`; `gerados` {rel: bytes}. O arquivo
    lido que começa com `#!`, ELF ou MZ recusa em todo sistema (PELO_CONTEUDO; antes, só numa montagem sem metadata)."""
    gerados = gerados or {}
    motivos = list(achados)
    if not nome_valido(nome):
        motivos.append(f"{_exibir(nome)}: nome do plugin fora do padrão do preparo do host (sem ':' nem '.' no fim)")
    elif not nome_de_plugin_valido(nome):
        motivos.append(f"{_exibir(nome)}: nome do plugin fora da regra da ficha de aberturas (minúsculas, números e "
                       "hífen, até 64: aberturas_regras.NOME_PLUGIN do kit): o abertura preparar o recusaria")
    if projeto is not None and not (ID_PROJETO.fullmatch(projeto) and nome.startswith(projeto + "-")
                                    and len(nome) > len(projeto) + 1):
        motivos.append(f"{_exibir(nome)}: o nome tem de ser <projeto>-<nome> do projeto {_exibir(projeto)}")
    recusadas: list = []

    def sob_recusada(rel: str) -> bool:
        return any(rel.startswith(r + "/") for r in recusadas)

    for rel in sorted(pastas):
        if not sob_recusada(rel) and (motivo := _motivo_da_forma(rel.split("/"), True) or _motivo_do_nome(rel, True)):
            motivos.append(f"{_exibir(rel)}/: {motivo}")
            recusadas.append(rel)
    entradas = sorted([*arquivos, *((rel, None) for rel in gerados)], key=lambda e: e[0])
    motivos += _teto_de_arquivos(len(entradas))  # o plugin.json gerado pelo `montar` também conta, como no kit
    aceitos = []
    for rel, caminho in entradas:
        if sob_recusada(rel):
            continue
        motivo = _motivo_da_forma(rel.split("/"), False) or _motivo_do_nome(rel, False) or _motivo_do_tipo(rel)
        if motivo:
            motivos.append(f"{_exibir(rel)}: {motivo}")
        aceitos.append((rel, caminho, motivo is None))
    rels = {rel for rel, _ in entradas}
    motivos += _colisoes([*pastas, *rels])
    if ".claude-plugin/plugin.json" not in rels:
        motivos.append(".claude-plugin/plugin.json: falta")
    motivos += [f"{_exibir(rel)}/: skill sem SKILL.md" for rel in sorted(pastas) if rel.count("/") == 1
                and rel.startswith("skills/") and rel not in recusadas and f"{rel}/SKILL.md" not in rels]
    if not any(rel.split("/")[0] in COMPONENTES for rel in rels):
        motivos.append("o candidato não tem skill, agente nem comando")
    lista, textos, componentes, lidos = [], {}, [], 0
    for rel, caminho, nome_certo in aceitos:
        if REGRAS.classificar(rel) in ("forte", "pasta-de-segredo"):
            continue  # regra única (contratos §3): nunca lido, nem para o hash, que a revisão mostraria
        try:
            dados = gerados[rel] if caminho is None else _ler(caminho, base)
        except (OSError, CandidatoRecusado) as exc:  # CopiaRecusada é um OSError
            motivos.append(f"{_exibir(rel)}: {exc}")
            continue
        lidos += len(dados)
        if lidos > TETO["total"]:  # o exame somou o tamanho visto; aqui, os bytes lidos (o arquivo pode ter crescido)
            motivos.append(f"passa do teto de {TETO['total']} bytes no total (bytes lidos)")
            break
        lista.append({"caminho": rel, "bytes": len(dados), "sha256": hashlib.sha256(dados).hexdigest()})
        if caminho is not None and KIT.executavel_pelo_conteudo(dados):  # em todo sistema (revisão, rodada 2)
            motivos.append(f"{_exibir(rel)}: {PELO_CONTEUDO}")
            continue
        if nome_certo:
            achados_do_arquivo, componente, texto = _conferir_arquivo(rel, dados, nome)
            motivos += achados_do_arquivo
            if texto is not None:
                textos[rel] = texto
            if componente:
                componentes.append(componente)
    avisos = [f"{c['arquivo']}: sem tools no cabeçalho, o agente herda todas as ferramentas da sessão"
              for c in componentes if c["tipo"] == "agente" and c["ferramentas"] is None]
    avisos += [f"{c['arquivo']}: o name {c['nome']} difere da pasta; confira como o Claude Code a chama"
               for c in componentes if c["tipo"] == "skill" and c["nome"] != c["arquivo"].split("/")[1]]
    if nome_de_plugin_valido(nome) and not KEBAB.fullmatch(nome):  # o que passa na ficha e ainda avisa: o '--'
        avisos.append(f"{_exibir(nome)}: o nome do plugin não é kebab-case (minúsculas, números e hífen, sem '--'): o "
                      "validador do Claude Code 2.1.302 o aceita, mas avisa (a sincronização com o Claude.ai exige "
                      "kebab-case)")
    if nome_valido(nome) and any(marca in nome.casefold() for marca in MARCAS_DA_ANTHROPIC):
        avisos.append(f"{_exibir(nome)}: o nome cita claude, anthropic ou cc-plugin: o Claude Code 2.1.302 recusa ou "
                      "avisa nome de terceiro que passa por um da Anthropic (prefira outro --nome; o canário confere)")
    conforme, dados = not motivos, _manifesto(nome, lista)
    if len(motivos) > LIMITE_DE_MOTIVOS:
        motivos = [*motivos[:LIMITE_DE_MOTIVOS], f"(e mais {len(motivos) - LIMITE_DE_MOTIVOS} motivos)"]
    sha = KIT.sha256_do_manifesto(dados["arquivos"]) if conforme else None  # a receita única (emenda E3; item I4)
    res = {"schema_version": ESQUEMA, "nome": nome, "pasta": str(base), "conforme": conforme, "motivos": motivos,
           "manifesto": dados if conforme else None, "manifesto_sha256": sha, "arquivos": len(lista),
           "bytes": sum(a["bytes"] for a in lista), "componentes": componentes, "avisos": avisos}
    return res, textos, dados["arquivos"]


def _do_kit(erro: dict) -> str:
    """Um erro do validador do kit como motivo daqui (`<caminho>: <motivo>`), com a marca de onde veio."""
    campo, motivo = str(erro.get("campo", "")), str(erro.get("motivo", ""))
    rel = campo.partition(": ")[2] if campo.startswith("plugin ") else campo
    return f"{_exibir(rel or campo)}: {_exibir(motivo)} (regra do kit, aberturas_plugins.conferir_pasta_do_plugin)"


def _regra_do_kit(pasta: Path, nome: str, res: dict) -> None:
    """A última conferência do candidato no disco: o validador do kit (aberturas_plugins.conferir_pasta_do_plugin),
    que é a regra do `abertura preparar`, da ferramenta do titular e do preparo do host (emenda E4: esta ferramenta da
    sessão pode ser mais estrita, nunca mais frouxa; integração, item I12). Só depois que as regras daqui aceitaram
    (nada de nome forte chega a ser lido): erro do kit recusa, e o manifesto que ele calcula, lendo os bytes de novo,
    tem de ser o daqui (um arquivo trocado no intervalo recusa)."""
    if not res["conforme"]:
        return
    kit = KIT.conferir_pasta_do_plugin(pasta, nome)
    motivos = [_do_kit(e) for e in kit["erros"]]
    if not motivos and kit["manifesto_sha256"] != res["manifesto_sha256"]:
        motivos.append("o candidato mudou durante a conferência (o manifesto calculado pelo kit difere do daqui): "
                       "confira de novo")
    if motivos:
        if len(motivos) > LIMITE_DE_MOTIVOS:
            motivos = [*motivos[:LIMITE_DE_MOTIVOS], f"(e mais {len(motivos) - LIMITE_DE_MOTIVOS} motivos)"]
        res.update(conforme=False, motivos=motivos, manifesto=None, manifesto_sha256=None)


def _examinar(pasta: Path, nome: str, projeto: str | None) -> tuple[dict, dict, list]:
    """O candidato no disco: as regras daqui (o bit de execução, salvo numa montagem 9p ou drvfs sem metadata, emenda
    E9; o conteúdo de executável, em todo sistema) e, por último, a regra do kit."""
    _exigir_pasta(pasta)
    arquivos, pastas, achados = _varrer(pasta, bit_de_execucao=not _sem_prova_do_bit(pasta))
    res, textos, lista = _avaliar(nome, projeto, arquivos, pastas, achados, pasta)
    _regra_do_kit(pasta, nome, res)
    return res, textos, lista


def _projeto_do_caminho(pasta: Path) -> str | None:
    """O <p> de um candidato em `<raiz>/projects/<p>/plugins-candidatos/<nome>`; None em outro lugar (como a cópia
    que o preparo do titular instala)."""
    mae = pasta.parent
    if mae.name.casefold() == CANDIDATOS and mae.parent.parent.name.casefold() == "projects":
        return mae.parent.name
    return None


def _sessao(projeto: str | None, raiz: Path | None = None) -> None:
    """Na sessão de um projeto, outro projeto ou outra raiz recusam (isolamento lógico: a variável só restringe)."""
    da_sessao, raiz_da_sessao = os.environ.get(VARIAVEL_PROJETO), os.environ.get(VARIAVEL_RAIZ)
    if da_sessao and projeto and projeto != da_sessao:
        raise CandidatoRecusado(f"o projeto da sessão é {da_sessao}: o script não lê nem grava o candidato de "
                                f"{projeto}")
    if raiz is not None and raiz_da_sessao and (os.path.normcase(os.path.abspath(raiz))
                                                != os.path.normcase(os.path.abspath(raiz_da_sessao))):
        raise CandidatoRecusado(f"a raiz da sessão é {raiz_da_sessao}: --raiz não troca de raiz")


def _dentro_da_sessao(pasta) -> None:
    """Na sessão de um projeto (FUNDACAO_PROJECT), só pasta cujo caminho real (ligação resolvida) fica em
    `<FUNDACAO_RAIZ>/projects/<p>` — sem FUNDACAO_RAIZ, num caminho real com os componentes `projects/<p>` —, também
    fora de plugins-candidatos/: outro projeto, o data/ dele e outra raiz recusam antes de qualquer leitura (revisão do
    pacote PLUGINS; isolamento lógico, contratos §0: a variável só restringe, nunca amplia). Identificador inválido na
    variável: recusa tudo. Fora de uma sessão, nada muda (o preparo do titular lê de onde precisar).
    Reconferência do pacote: com a raiz, `projects/<p>` trocado por junção recusa (o realpath a seguiria até o outro
    projeto); sem ela, todo componente `projects` do caminho real tem de vir seguido de `<p>` (um `projects/demo`
    dentro de `projects/outro` não basta; recusa a mais se a própria raiz ficar abaixo de uma pasta `projects`)."""
    da_sessao = os.environ.get(VARIAVEL_PROJETO)
    if not da_sessao:
        return
    real = Path(os.path.normcase(os.path.realpath(pasta)))
    raiz = os.environ.get(VARIAVEL_RAIZ)
    if not ID_PROJETO.fullmatch(da_sessao):
        dentro = False
    elif raiz:
        raiz_real = os.path.realpath(raiz)
        dentro = (not GRAVACAO.com_ligacao(raiz_real, f"projects/{da_sessao}")
                  and real.is_relative_to(os.path.normcase(os.path.join(raiz_real, "projects", da_sessao))))
    else:
        partes = real.parts
        indices = [i for i in range(len(partes) - 1) if partes[i] == "projects"]
        dentro = bool(indices) and all(partes[i + 1] == da_sessao for i in indices)
    if not dentro:
        raise CandidatoRecusado(f"o projeto da sessão é {_exibir(da_sessao)}: o script só lê pasta de projects/"
                                f"{_exibir(da_sessao)} (o caminho real de {_exibir(pasta)} fica fora)")


def conferir(pasta, projeto: str | None = None) -> dict:
    """A conferência inteira do candidato (forma, regras, tetos, manifesto e componentes); não grava nada. O projeto
    vem de `projeto` ou do caminho (`projects/<p>/plugins-candidatos/`) e prende o nome a `<p>-<nome>`."""
    pasta = Path(os.path.abspath(pasta))
    _dentro_da_sessao(pasta)
    do_caminho = _projeto_do_caminho(pasta)
    if projeto and do_caminho and projeto != do_caminho:
        raise CandidatoRecusado(f"o candidato fica em projects/{do_caminho}, não em projects/{projeto}")
    _sessao(projeto or do_caminho)
    return _examinar(pasta, pasta.name, projeto or do_caminho)[0]


# --- montar ----------------------------------------------------------------------------------------------------------
def _planejar(origem: Path) -> tuple[list, list, list, list]:
    """(arquivos [(rel no candidato, caminho na origem)], pastas do candidato, não copiados da raiz da origem,
    motivos): a skill avulsa (a origem tem SKILL.md) vira `skills/<pasta>/`; da árvore vêm `skills/`, `agents/`,
    `commands/` e a licença da raiz."""
    conta = {"entradas": 0, "total": 0}
    if os.path.lexists(origem / "SKILL.md"):
        prefixo = f"skills/{origem.name}"
        arquivos, pastas, motivos = _varrer(origem, prefixo, conta)
        return arquivos, ["skills", prefixo, *pastas], [], motivos
    arquivos, pastas, nao_copiados, motivos = [], [], [], []
    try:
        with os.scandir(origem) as it:
            nomes = sorted(e.name for e in it)
    except OSError as exc:
        return [], [], [], [f"--origem: não deu para listar ({exc.strerror or exc})"]
    for nome in nomes:
        caminho = origem / nome
        try:
            st = os.lstat(caminho)
        except OSError as exc:
            motivos.append(f"{_exibir(nome)}: não deu para examinar ({exc.strerror or exc})")
            continue
        ligacao, pasta = COPIA.e_ligacao(st), stat.S_ISDIR(st.st_mode)
        if (nome in COMPONENTES or nome.casefold() in LICENCAS) and ligacao:
            motivos.append(f"{_exibir(nome)}: ligação (link simbólico ou junção): nunca seguida")
        elif nome in COMPONENTES and pasta:
            achados = _varrer(caminho, nome, conta)
            arquivos += achados[0]
            pastas += [nome, *achados[1]]
            motivos += achados[2]
        elif nome.casefold() in LICENCAS and stat.S_ISREG(st.st_mode):
            arquivos.append((nome, caminho))
        else:
            nao_copiados.append(_exibir(nome) + ("/" if pasta and not ligacao else ""))
    return arquivos, pastas, nao_copiados, motivos


def _apagar_sem_seguir(caminho: Path) -> None:
    """Apaga a pasta temporária do `montar` sem descer por ligação (o `shutil.rmtree` do Windows pode descer por
    junção): a ligação sai pelo próprio nome, nunca pelo alvo. O que não sair fica (é temporário do projeto)."""
    try:
        st = os.lstat(caminho)
    except OSError:
        return
    if stat.S_ISDIR(st.st_mode) and not COPIA.e_ligacao(st):
        try:
            with os.scandir(caminho) as it:
                nomes = [e.name for e in it]
        except OSError:
            nomes = []
        for nome in nomes:
            _apagar_sem_seguir(caminho / nome)
    try:
        (os.rmdir if stat.S_ISDIR(st.st_mode) else os.unlink)(caminho)
    except OSError:
        pass


def montar(raiz, projeto: str, nome: str, origem, descricao: str | None = None) -> dict:
    """Monta `projects/<projeto>/plugins-candidatos/<projeto>-<nome>/` a partir de `origem` (ver o módulo)."""
    raiz = Path(os.path.abspath(raiz))
    _sessao(projeto, raiz)
    if not isinstance(projeto, str) or not ID_PROJETO.fullmatch(projeto):
        raise CandidatoRecusado(f"projeto {projeto!r}: identificador inválido (o do kit: minúsculas, números e hífen)")
    plugin = f"{projeto}-{nome}"
    if not nome_valido(nome) or not nome_de_plugin_valido(plugin):
        raise CandidatoRecusado(f"nome {nome!r}: fora da regra da ficha de aberturas para o plugin {projeto}-<nome> "
                                "(minúsculas, números e hífen, até 64 com o projeto; aberturas_regras.NOME_PLUGIN do "
                                "kit, que o abertura preparar exige) e do padrão do preparo do host")
    if descricao is not None and (not descricao.strip() or len(descricao) > 1024 or CONTROLE.search(descricao)):
        raise CandidatoRecusado("--descricao: de 1 a 1024 caracteres, sem caractere de controle")
    pasta_p = raiz / "projects" / projeto
    if GRAVACAO.com_ligacao(raiz, f"projects/{projeto}") or not pasta_p.is_dir():
        raise CandidatoRecusado(f"{pasta_p}: o projeto não existe ou é ligação")
    origem = Path(os.path.abspath(origem))
    if not origem.is_relative_to(pasta_p) or origem == pasta_p:
        raise CandidatoRecusado(f"--origem {origem}: fica fora de {pasta_p} (só uma pasta dentro do projeto)")
    rel_origem = origem.relative_to(pasta_p).as_posix()
    if GRAVACAO.com_ligacao(pasta_p, rel_origem):
        raise CandidatoRecusado(f"--origem {origem}: passa por ligação (link simbólico ou junção)")
    if not origem.is_dir() or not Path(os.path.realpath(origem)).is_relative_to(os.path.realpath(pasta_p)):
        raise CandidatoRecusado(f"--origem {origem}: não é uma pasta do projeto")
    _dentro_da_sessao(origem)
    destino = pasta_p / CANDIDATOS / plugin
    if destino.is_relative_to(origem):
        raise CandidatoRecusado(f"--origem {origem}: contém o destino {destino}")
    if GRAVACAO.com_ligacao(pasta_p, f"{CANDIDATOS}/{plugin}"):
        raise CandidatoRecusado(f"{destino}: o caminho passa por ligação (link simbólico ou junção)")
    if os.path.lexists(destino):
        raise CandidatoRecusado(f"{destino}: já existe (apague o candidato antigo, que é do projeto, ou use outro "
                                "--nome)")
    arquivos, pastas, nao_copiados, achados = _planejar(origem)
    texto = descricao or (f"Skills, agentes e comandos do projeto {projeto} (candidato: vale só com a ficha de "
                          "aberturas assinada pelo titular)")
    gerado = (json.dumps({"name": plugin, "description": texto}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    previa, _textos, _lista = _avaliar(plugin, projeto, arquivos, [".claude-plugin", *pastas], achados, origem,
                                       {".claude-plugin/plugin.json": gerado})
    if not previa["conforme"]:
        raise CandidatoRecusado(previa["motivos"])
    esperado = {a["caminho"]: a["sha256"] for a in previa["manifesto"]["arquivos"]}
    try:
        temp = GRAVACAO.pasta_sem_ligacao(pasta_p, CANDIDATOS) / f"{PREFIXO_TEMP}{os.urandom(6).hex()}"
        temp.mkdir()
    except OSError as exc:
        raise CandidatoRecusado(f"{pasta_p / CANDIDATOS}: não deu para criar a pasta da montagem ({exc})") from None
    try:
        for rel, caminho in arquivos:
            (temp / rel).parent.mkdir(parents=True, exist_ok=True)
            COPIA.copiar_conferindo(caminho, temp / rel, sha256_esperado=esperado[rel], dentro_de=origem)
        (temp / ".claude-plugin").mkdir()
        GRAVACAO.criar(temp / ".claude-plugin" / "plugin.json", gerado)
        if os.name != "nt":
            os.chmod(temp / ".claude-plugin" / "plugin.json", 0o444)
        res = _examinar(temp, plugin, projeto)[0]
        if not res["conforme"]:  # na cópia valem também o bit de execução e a regra do kit (integração, item I12)
            raise CandidatoRecusado(["a conferência do candidato montado recusou (nada ficou no destino)",
                                     *res["motivos"]])
        if res["manifesto_sha256"] != previa["manifesto_sha256"]:
            raise CandidatoRecusado("a cópia não confere com a origem conferida")
        if os.path.lexists(destino):
            raise CandidatoRecusado(f"{destino}: apareceu durante a montagem")
        os.rename(temp, destino)
    except OSError as exc:
        _apagar_sem_seguir(temp)
        raise CandidatoRecusado(f"a montagem falhou e nada ficou no destino ({exc})") from None
    except BaseException:
        _apagar_sem_seguir(temp)
        raise
    avisos = []
    if fora := [n for n in nao_copiados if n.rstrip("/").casefold() in QUE_EXECUTAM_NA_ORIGEM]:
        avisos.append(f"não vêm da origem: {', '.join(fora)} — hooks, MCP, configuração e executáveis ficam para a "
                      "1.7.11 (o que dependia deles pode não funcionar no candidato)")
    if licencas := [n for n in nao_copiados if not n.endswith("/") and OUTRA_LICENCA.fullmatch(n)]:
        avisos.append(f"não vêm da origem: {', '.join(licencas)} — na raiz do candidato, só LICENSE, LICENSE.md ou "
                      "LICENSE.txt (a regra do kit); se a licença pede que o aviso viaje com a cópia, junte o texto ao "
                      "LICENSE na cópia de trabalho da origem e monte de novo")
    if rel_origem.split("/")[0].casefold() == "data":
        avisos.append("a origem fica em data/ (dado): vira instrução só depois da revisão do titular, da ficha "
                      "assinada e do canário")
    script, sha = Path(__file__).resolve(), res["manifesto_sha256"]
    python = "python" if os.name == "nt" else "python3"
    revisao = pasta_p / "outputs" / "plugins" / nome / "REVISAO.md"
    return {"schema_version": ESQUEMA, "feito": "montar", "candidato": str(destino), "nome": plugin,
            "origem": rel_origem, "arquivos": res["arquivos"], "bytes": res["bytes"], "manifesto_sha256": sha,
            "componentes": res["componentes"], "nao_copiados": nao_copiados, "avisos": avisos + res["avisos"],
            "ficha": {"nome": plugin, "origem": f"{CANDIDATOS}/{plugin}", "manifesto_sha256": sha},
            "proximos_passos": [f'{python} "{script}" conferir --pasta "{destino}"',
                                f'{python} "{script}" revisar --pasta "{destino}" --saida "{revisao}"',
                                "o titular revisa o REVISAO.md; se aceitar, a ficha de aberturas lista a entrada de "
                                "'ficha' e ele a assina pela ferramenta fixa dele; o preparo dele instala o plugin "
                                "só depois do canário"]}


# --- revisar ---------------------------------------------------------------------------------------------------------
def _md(texto) -> str:
    """Texto do candidato para dentro de um trecho de código (crases) do Markdown: sem crase, barra vertical nem quebra
    de linha, que fechariam o trecho ou a célula da tabela."""
    texto = _exibir(texto).replace("|", "¦").replace("`", "'")
    return re.sub(r"[\r\n\t\N{LINE SEPARATOR}\N{PARAGRAPH SEPARATOR}]", " ", texto)


def _codigo(texto) -> str:
    """Texto do candidato sempre entre crases: ali o Markdown não interpreta HTML, comentário, link nem ênfase, e nada
    do candidato esconde ou disfarça parte da revisão (revisão do pacote PLUGINS). Vazio vira '—'."""
    texto = _md(texto).strip()
    return f"`{texto}`" if texto else "—"


def _trecho(linha: str) -> str:
    texto = OPACO.sub("«…»", _md(INVISIVEIS.sub("", linha)).strip())
    texto = VALOR_DE_SEGREDO.sub(lambda m: m.group(1) + "«…»", texto)
    return texto[:160] + ("…" if len(texto) > 160 else "")


def _hosts(linha: str):
    for m in URL.finditer(linha):
        try:
            host = urlsplit(m.group(0)).hostname
        except ValueError:
            host = None
        if host:
            yield host.rstrip(".")
    yield from (m.group(1).casefold() for m in DOMINIO.finditer(linha))
    yield from (m.group(0).casefold() for m in WWW.finditer(linha))


def _marcas(textos: dict) -> tuple[dict, dict, dict, dict]:
    """Trechos por categoria [(rel, linha, trecho)], domínios {host: [vezes, lugar]}, ferramentas {nome: [vezes,
    arquivos]} e caracteres invisíveis {rel: quantos}: só padrões de texto, sem julgar."""
    trechos, dominios, ferramentas, invisiveis = {c: [] for c, _ in PADROES}, {}, {}, {}
    for rel, texto in sorted(textos.items()):
        for n, linha in enumerate(texto.split("\n"), 1):
            for categoria in {c for c, rx in PADROES if rx.search(linha)}:
                trechos[categoria].append((rel, n, _trecho(linha)))
            for host in _hosts(linha):
                dominios.setdefault(host, [0, f"{rel}:{n}"])[0] += 1
            for m in CITADAS.finditer(linha):
                ferramentas.setdefault(m.group(0), [0, set()])[0] += 1
                ferramentas[m.group(0)][1].add(rel)
        if quantos := len(INVISIVEIS.findall(texto)):
            invisiveis[rel] = quantos
    return trechos, dominios, ferramentas, invisiveis


def _lista_de_trechos(itens: list, vazio: str) -> list:
    if not itens:
        return [f"- {vazio}"]
    linhas = [f"- `{_md(rel)}:{n}` — `{trecho}`" for rel, n, trecho in itens[:LIMITE_DE_MARCAS]]
    return linhas + ([f"- (e mais {len(itens) - LIMITE_DE_MARCAS})"] if len(itens) > LIMITE_DE_MARCAS else [])


def revisar(pasta) -> tuple[str, dict]:
    """(Markdown do esqueleto da revisão, resultado da conferência) do candidato; só lê."""
    pasta = Path(os.path.abspath(pasta))
    _dentro_da_sessao(pasta)
    projeto = _projeto_do_caminho(pasta)
    _sessao(projeto)
    res, textos, lista = _examinar(pasta, pasta.name, projeto)
    trechos, dominios, ferramentas, invisiveis = _marcas(textos)
    nome, sha = _md(res["nome"]), res["manifesto_sha256"]
    exibida = f"projects/{projeto}/{CANDIDATOS}/{res['nome']}" if projeto else res["pasta"]  # sem o caminho da máquina
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    m = [f"# Revisão do plugin candidato `{nome}`", "",
         f"> Esqueleto gerado por `scripts/plugin_candidato.py revisar` em {agora}. Só leitura do candidato: nada foi "
         "executado nem baixado. Os trechos marcados vêm de padrões de texto, sem julgamento: a revisão é do titular.",
         "> O candidato só vale depois que o titular o lista na ficha de aberturas e a assina pela ferramenta fixa "
         "dele, e depois do canário no ambiente real (contratos do lote 2 da 1.7.10, §0 e §5). Até lá nenhuma sessão "
         "o carrega.", "", "## Identificação", f"- Pasta: `{_md(exibida)}`",
         "- Conferência: " + ("conforme" if res["conforme"] else "**RECUSADO** (motivos abaixo: corrija na origem e "
                                                                  "monte de novo)"),
         f"- Arquivos: {res['arquivos']} ({res['bytes']} bytes)",
         f"- `manifesto_sha256`: `{sha}`" if sha else "- `manifesto_sha256`: só quando conforme"]
    if res["motivos"]:
        m += ["", "### Motivos da recusa", *(f"- {_codigo(x)}" for x in res["motivos"])]
    if res["avisos"]:
        m += ["", "### Avisos", *(f"- {_codigo(x)}" for x in res["avisos"])]
    m += ["", "## Componentes e o jeito novo de chamar", "",
          "| Tipo | Nome | Como chamar | Ferramentas do cabeçalho | Modelo | Descrição |", "|---|---|---|---|---|---|"]
    for c in res["componentes"]:  # o valor cru do cabeçalho: o titular vê também o que vem entre parênteses
        ferr = "(todas as da sessão)" if c["ferramentas"] is None else _codigo(c["cabecalho"])
        m.append(f"| {c['tipo']} | {_codigo(c['nome'])} | {_codigo(c['invocacao'])} | {ferr} | "
                 f"{_codigo(c['modelo'] or '')} | {_codigo(c['descricao'])} |")
    m += ["", "## 1. Instruções", "",
          "### Trechos que parecem mandar ignorar regras, contornar permissões ou esconder algo do titular",
          *_lista_de_trechos(trechos["instrucao"], "nenhum trecho marcado"), "",
          "### Trechos que citam leitura fora do projeto (caminho absoluto, `..`, outro projeto, `state/`, `.claude/`)",
          *_lista_de_trechos(trechos["fora"], "nenhum trecho marcado")]
    if invisiveis:
        m += ["", "### Caracteres invisíveis (podem esconder texto)",
              *(f"- `{_md(rel)}`: {q}" for rel, q in sorted(invisiveis.items()))]
    m += ["", "## 2. Scripts e comandos", "",
          "O plugin não leva script nem executável (a conferência recusa). Comandos citados no texto, que uma skill "
          "pode pedir para rodar:", *_lista_de_trechos(trechos["comando"], "nenhum comando citado"), "",
          "## 3. Rede", "",
          "O plugin não abre rede: um domínio só vale se o titular o puser na ficha (`rede.dominios` e, para o "
          "WebFetch, `webfetch.dominios`).", ""]
    m += (["| Domínio | Vezes | Primeiro lugar |", "|---|---|---|",
           *(f"| {_codigo(h)} | {v} | {_codigo(lugar)} |" for h, (v, lugar) in sorted(dominios.items()))]
          if dominios else ["- nenhum domínio citado"])
    fracos = [a["caminho"] for a in lista if REGRAS.classificar(a["caminho"]) == "fraco"]
    m += ["", "## 4. Segredos", "",
          "- Nomes que a regra única marca como fracos (ficam no plugin; confira o conteúdo): "
          + (", ".join(f"`{_md(r)}`" for r in fracos) if fracos else "nenhum"),
          "- Trechos que citam caminho ou palavra de segredo (só o trecho; valores longos mascarados):",
          *_lista_de_trechos(trechos["segredo"], "nenhum trecho marcado"), "", "## 5. Ferramentas citadas no texto", ""]
    m += (["| Ferramenta | Vezes | Arquivos |", "|---|---|---|",  # o nome vem de `CITADAS`: letras, números, _ * -
           *(f"| {_codigo(f)} | {v} | {_codigo(', '.join(sorted(arqs))[:300])} |"
             for f, (v, arqs) in sorted(ferramentas.items()))] if ferramentas else ["- nenhuma citada"])
    m += ["", "## 6. Arquivos", "", "| Caminho | Bytes | SHA-256 (começo) |", "|---|---|---|",
          *(f"| `{_md(a['caminho'])}` | {a['bytes']} | `{a['sha256'][:16]}` |" for a in lista), "",
          "## Decisão do titular (preencher à mão)", "",
          "- [ ] Li as instruções de cada skill, agente e comando (componentes e seção 1).",
          "- [ ] Os trechos marcados foram explicados ou não são problema.",
          "- [ ] Os domínios de que o plugin precisa, se houver, vão para a ficha (rede.dominios, webfetch.dominios).",
          "- [ ] Aceito listar na ficha de aberturas: `" + _md(json.dumps(
              {"nome": res["nome"], "origem": f"{CANDIDATOS}/{res['nome']}", "manifesto_sha256": sha},
              ensure_ascii=False)) + "`" if sha else "- [ ] (o candidato está recusado: nada a listar na ficha)",
          "", "Observações do titular:", ""]
    return "\n".join(m) + "\n", res


def destino_da_revisao(pasta, saida) -> Path:
    """O arquivo de `--saida`, conferido antes de gravar: dentro do projeto do candidato (que tem de estar em
    `projects/<p>/plugins-candidatos/`), em outputs/ (a folha prevê `outputs/plugins/<N>/REVISAO.md`), .md, sem nome
    oculto (`.claude/`, `.porteiro/`), sem nome curto do Windows (`CLAUDE~1`), sem arquivo de instrução (CLAUDE.md,
    AGENTS.md: a revisão traz trechos do candidato e viraria instrução da sessão) e sem ligação no caminho."""
    pasta = Path(os.path.abspath(pasta))
    _dentro_da_sessao(pasta)
    if _projeto_do_caminho(pasta) is None:
        raise CandidatoRecusado("--saida só para candidato em projects/<p>/plugins-candidatos/ (sem --saida, o "
                                "Markdown sai na tela)")
    projeto_dir = pasta.parent.parent
    alvo = Path(os.path.abspath(saida))
    if not alvo.is_relative_to(projeto_dir) or alvo == projeto_dir:
        raise CandidatoRecusado(f"--saida {alvo}: fica fora do projeto {projeto_dir}")
    partes = alvo.relative_to(projeto_dir).parts
    if partes[0].casefold() in ("data", CANDIDATOS):
        raise CandidatoRecusado(f"--saida {alvo}: não em data/ (dado) nem em {CANDIDATOS}/ (o candidato só é lido)")
    if partes[0].casefold() != "outputs":
        raise CandidatoRecusado(f"--saida {alvo}: só em outputs/ do projeto (ex.: outputs/plugins/<nome>/REVISAO.md)")
    if any(":" in parte or CONTROLE.search(parte) or INVISIVEIS.search(parte) for parte in partes):
        # no NTFS, `x:y.md` grava num fluxo de `x`
        raise CandidatoRecusado(f"--saida {_exibir(alvo)}: nome com ':', caractere de controle ou invisível")
    if any(parte.startswith(".") or re.search(r"~\d", parte) for parte in partes):
        raise CandidatoRecusado(f"--saida {alvo}: nome oculto (.claude/, .porteiro/) ou curto do Windows no caminho: "
                                "a revisão não vai para configuração nem para a fila do porteiro")
    if not alvo.name.casefold().endswith(".md"):
        raise CandidatoRecusado(f"--saida {alvo}: a revisão é um arquivo .md")
    if alvo.name.casefold() in INSTRUCOES:
        raise CandidatoRecusado(f"--saida {alvo}: arquivo de instrução (CLAUDE.md, AGENTS.md): a revisão traz trechos "
                                "do candidato e carregaria como instrução da sessão")
    if GRAVACAO.com_ligacao(projeto_dir, "/".join(partes)):
        raise CandidatoRecusado(f"--saida {alvo}: passa por ligação (link simbólico ou junção)")
    return alvo


def gravar_revisao(pasta, saida, texto: str) -> Path:
    """Grava a revisão num arquivo novo (`destino_da_revisao`), sem seguir ligação; o que já existe não é trocado."""
    alvo = destino_da_revisao(pasta, saida)
    projeto_dir = Path(os.path.abspath(pasta)).parent.parent
    partes = alvo.relative_to(projeto_dir).parts
    try:
        if len(partes) > 1:
            GRAVACAO.pasta_sem_ligacao(projeto_dir, "/".join(partes[:-1]))
        GRAVACAO.criar(alvo, texto.encode("utf-8"))
    except FileExistsError:
        raise CandidatoRecusado(f"--saida {alvo}: já existe (a revisão do titular não é trocada; use outro nome)") \
            from None
    except OSError as exc:
        raise CandidatoRecusado(f"--saida {alvo}: não gravado ({exc})") from None
    return alvo


def main(argv: list | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="plugin_candidato.py", allow_abbrev=False,
                                 description="Plugin candidato de um projeto: montar, conferir e revisar.")
    sub = ap.add_subparsers(dest="acao", required=True)
    m = sub.add_parser("montar", allow_abbrev=False, help="monta projects/P/plugins-candidatos/P-N/")
    for opcao in ("--raiz", "--projeto", "--nome", "--origem"):
        m.add_argument(opcao, required=True)
    m.add_argument("--descricao")
    c = sub.add_parser("conferir", allow_abbrev=False, help="confere o candidato e mostra o manifesto")
    c.add_argument("--pasta", required=True)
    c.add_argument("--projeto")
    r = sub.add_parser("revisar", allow_abbrev=False, help="esqueleto da revisão do titular")
    r.add_argument("--pasta", required=True)
    r.add_argument("--saida")
    args = ap.parse_args(argv)
    try:
        if args.acao == "montar":
            res = montar(args.raiz, args.projeto, args.nome, args.origem, args.descricao)
            print(json.dumps(res, ensure_ascii=False, indent=1))
            return 0
        if args.acao == "conferir":
            res = conferir(args.pasta, args.projeto)
            print(json.dumps(res, ensure_ascii=False, indent=1))
            return 0 if res["conforme"] else 2
        if args.saida:
            destino_da_revisao(args.pasta, args.saida)  # recusa antes de ler o candidato
        texto, res = revisar(args.pasta)
        if not args.saida:
            sys.stdout.write(texto)
            return 0
        alvo = gravar_revisao(args.pasta, args.saida, texto)
        print(json.dumps({"schema_version": ESQUEMA, "feito": "revisar", "revisao": str(alvo), "nome": res["nome"],
                          "conforme": res["conforme"], "manifesto_sha256": res["manifesto_sha256"]},
                         ensure_ascii=False, indent=1))
        return 0
    except CandidatoRecusado as exc:
        print(json.dumps({"erro": "recusado", "motivos": exc.motivos}, ensure_ascii=False, indent=1))
        return 2
    except OSError as exc:  # falha de disco fora das conferências: nada foi gravado no destino
        print(json.dumps({"erro": "recusado", "motivos": [_exibir(exc)]}, ensure_ascii=False, indent=1))
        return 2


if __name__ == "__main__":
    sys.exit(main())
