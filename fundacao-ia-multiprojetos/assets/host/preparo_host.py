#!/usr/bin/env python3
r"""Preparo do host da fundação: perfis do Claude Code gerados pelos modelos da skill, o `/etc/wsl.conf` com um só
bloco [interop] desligado e, no Ubuntu (WSL2), a área do titular de dono root com o perfil, o porteiro e o lançador de
CADA projeto (1.7.10; contratos do lote 2, §6 e §7; DESENHO-1.7.10 §1 e §4).

Honestidade (contratos do lote 2, §0): nas sondas de 31/10/2026, com a raiz em /mnt/e (DrvFs), o sandbox do Claude
Code 2.1.302 NÃO confinou os comandos (a ferramenta Read foi barrada); em ext4 confinou. Até o canário passar no
ambiente real, ou a fundação ir para o ext4 do WSL, o isolamento entre projetos no Ubuntu é LÓGICO: as regras que a IA
segue, a trava de projeto do kit, o porteiro fora do sandbox e os hooks (guarda-corpos). O que protege mesmo sem
confinamento: os arquivos de dono root (a área `/etc/fundacao-ia` e o lançador), a âncora do Windows e as assinaturas.

Perfil do projeto no Ubuntu (`perfil_wsl`): plano A (`permissions.blockReadsOutsideWorkingDirectories` e
`sandbox.network.strictAllowlist`) MAIS as negações nominais do plano B (state/, cada outro projeto e o
`.claude/projetos/<outro>` da raiz, /mnt/d, a pasta do Windows do titular, as transcrições e o histórico do Claude
Code, ~/.codex, ~/.fundacao e as configurações por projeto); segredos pela regra única (fortes + pastas, nunca os
fracos: `scripts/regras_de_segredo.py`, importado pelo caminho); escrita só no projeto, com `denyWrite` e Edit negado
em `projects/<p>/.porteiro/respostas` (nunca na pasta-mãe `.porteiro/`), `projects/<p>/.claude`, o `.claude` da raiz,
`registry/` e a âncora; `state/` fora do sandbox (negado e sem allowRead nem allowWrite: a armadilha do tmpfs da v1);
sockets de /tmp, /run, /var/run, /mnt/wsl e /mnt/wslg negados (salvo o temp do projeto); a ficha de aberturas assinada
(`aberturas.vigente` do kit, recebida por injeção) é a única fonte da rede, do WebFetch, do WebSearch e dos plugins;
sem ficha válida, tudo fechado. Portão do canário (contratos, §0; SONDAS de 31/10/2026: "até a prova passar, todas as
aberturas ficam fechadas"): a ficha só é aplicada com o relatório `fundacao.ensaio_isolamento/1` do ensaio real
instalado pelo titular (`instalar-canario`), do mesmo Claude Code fixado (versão e SHA-256) e da mesma forma de caminho
da raiz (ext4 ou drvfs:/mnt/<x>, medida no /proc/mounts); sem ele, tudo fechado e o relatório do preparo diz por quê.
O porteiro.json.kit_sha256 e a árvore "kit" usam a conta do próprio porteiro (`sha256_do_kit` de
assets/host/wsl/porteiro.py, pacote PORTEIRO): uma conta só. Os domínios e os plugins da ficha passam pelo validador
do kit desta cópia da skill (aberturas_regras.problema_do_dominio, aberturas_plugins.conferir_plugin e a receita
única do manifesto, sha256_do_manifesto: emendas E3 e E4; folha da integração, I5), sem réplica aqui. O preparo do
Ubuntu também instala a cópia protegida da ferramenta do titular em /usr/local/lib/fundacao-ia/<KIT_VERSION>/ (I11),
de onde a forma do Ubuntu do comando do kit a roda. Em PreToolUse, `guarda_ferramentas.py` fica com o matcher
`*` (a forma documentada de "todas"; `.*` é expressão e o alertas_hooks a acusa como "casa tudo"; o §7 dos contratos diz
`.*`: pendência registrada para o coordenador) e nega o que estiver fora de FUNDACAO_FERRAMENTAS.

Comandos (código 0 ok · 1 conferência com problemas, conflito ou recusa · 2 uso incorreto ou entrada inválida; fora
do 0, nada é gravado):
  perfil-windows --raiz R --python PY [--projeto P] [--negar-skill N]... [--somente-leitura D]... [--backups D]...
                 [--saida F]
  gerar-perfil-projeto --raiz R --projeto P --perfil-windows W [--area-raiz A] [--temp-base T] [--saida F]
                 (o antigo `perfil-wsl` é o mesmo comando)
  conferir-perfil-wsl --perfil F --raiz R --projeto P [--perfil-windows W] [--area-raiz A] [--lancador L]
  instalar-projeto --raiz R --projeto P --titular T --claude BIN --claude-versao V --claude-sha256 H
                 --origem-hash TEXTO --perfil-windows W --casa C --usuario U [--simular] [--area-raiz A --bin B
                 [--ferramenta-base F]]
                 (o titular roda com sudo; sem root, só com --area-raiz e --bin explícitos, para ensaio; a cópia
                 protegida da ferramenta do titular vai para /usr/local/lib/fundacao-ia ou, no ensaio, para F)
  plano-ferramenta [--python PY]    (o preparar-maquina.ps1: a cópia protegida do Windows, com o Python fixado)
  instalar-canario --relatorio R [--area-raiz A] [--simular]   (titular, sudo: o relatório do ensaio real do canário)
  conferir-abertura --raiz R --projeto P --area A [--limpar] [--texto]     (o lançador chama, como o usuário)
  limpar-marcadores --raiz R --projeto P --area A
  limpar-porteiro --raiz R --projeto P --casa C [--texto]   (o lançador: pastas de trabalho de porteiro morto)
  registrar-projeto --raiz R --projeto P --origem D [--origem D]... [--somente-leitura D]... [--negar-skill N]...
  ler-projetos-host --raiz R [--projeto P]
  fora-do-registro --raiz R [--somente-leitura D]... [--negar-skill N]...   (o preparar-maquina.ps1: o que o
                 registry/projetos-host.json não tem e o próximo preparar-projeto.ps1 tiraria do perfil)
  ultima-copia --raiz R     (os dois scripts do Windows: o destino de registry/ultima-copia.json, para o portão das cópias)
  identidade --titular T [--projeto P] [--atual F] [--estrito] [--sem-projeto] [--saida F]
  conferir-identidade --arquivo F --titular T --projeto P
  wsl-conf --arquivo F [--saida F]                                          (JSON com "mudou" e "texto")
Pastas de dados não viram instrução (análise do vibe-coding-toolkit, 21/10/2026): os perfis trazem `claudeMdExcludes`
para `**/projects/*/data/**`, e skill aninhada sai em `permissions.deny` como `Skill(<nome>)` (negação cumulativa:
`registry/projetos-host.json`, que só o titular grava, soma os nomes de todos os projetos). O perfil do Windows nega a
leitura de cada outro projeto e de `projects/*/data/**`, nega WebFetch e WebSearch e registra os hooks com `-I -B`;
lá não há sandbox, e os hooks são guarda-corpos rotulados.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import importlib
import importlib.util
import json
import ntpath
import os
import posixpath
import re
import secrets
import shlex
import shutil
import stat
import sys
import types
import unicodedata
from datetime import date, datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SKILL = AQUI.parent.parent
SCRIPTS = SKILL / "scripts"
MODELO_WINDOWS = AQUI / "windows" / "settings.json"
MODELO_WSL = AQUI / "wsl" / "settings.wsl.json"
MODELO_LANCADOR = AQUI / "wsl" / "abrir-sessao.sh"
MODELO_HOOKS = AQUI.parent / "hooks"  # os hooks da skill, que o preparo do Windows copia para <raiz>/.claude/hooks
# Os hooks de cada perfil (contratos do lote 2, §7) e o marcador de cada um nos modelos.
MARCADOR_DO_HOOK = {"sinais_sessao.py": "HOOK_SINAIS", "guarda_ferramentas.py": "HOOK_FERRAMENTAS",
                    "guarda_caminho.py": "HOOK_CAMINHO", "guarda_identidade.py": "HOOK_IDENTIDADE",
                    "guarda_rede.py": "HOOK_REDE", "guarda_leitura.py": "HOOK_LEITURA", "aviso_copia.py": "HOOK_AVISO"}
HOOKS_WSL = ("sinais_sessao.py", "guarda_ferramentas.py", "guarda_caminho.py", "guarda_identidade.py",
             "guarda_rede.py", "guarda_leitura.py")
HOOKS_WINDOWS = ("sinais_sessao.py", "aviso_copia.py", "guarda_caminho.py", "guarda_identidade.py",
                 "guarda_rede.py", "guarda_leitura.py")
HOOKS = ("guarda_caminho.py", "guarda_identidade.py", "sinais_sessao.py", "guarda_ferramentas.py", "guarda_rede.py",
         "guarda_leitura.py", "aviso_copia.py")  # os que o preparar-maquina.ps1 copia para <raiz>/.claude/hooks
GANCHOS_WSL = (("SessionStart", "compact", "sinais_sessao.py"), ("PreToolUse", "*", "guarda_ferramentas.py"),
               ("PreToolUse", "Edit|Write|MultiEdit|NotebookEdit|mcp__.*", "guarda_caminho.py"),
               ("PreToolUse", "Bash|PowerShell", "guarda_identidade.py"),
               ("PreToolUse", "WebFetch|WebSearch", "guarda_rede.py"),
               ("PreToolUse", "Read|Grep|Glob", "guarda_leitura.py"))
ANCORA_BASE_WSL = "/mnt/c/ProgramData/FundacaoIA"  # a pasta da âncora do Windows (allowed_signers), vista do WSL
MONTAGEM = "/mnt/"  # [automount] root padrão do WSL
AREA_RAIZ = "/etc/fundacao-ia"  # área do titular, dono root (contratos do lote 2, §6)
BIN_DIR = "/usr/local/bin"
TEMP_BASE = "/tmp"
SONDA_INTEROP_CMD = "/mnt/c/Windows/System32/cmd.exe"
SONDA_INTEROP_BINFMT = "/proc/sys/fs/binfmt_misc"
# Managed settings ficam acima do --settings (e, sem eles, um mod aprova o que um deny recusa); "on WSL,
# /etc/claude-code is user-writable as well" (documentação de managed settings, conferida em 31/10/2026; DESENHO §9).
GERENCIADAS = "/etc/claude-code"
PYTHON_LINUX = "/usr/bin/python3"
IDENTIFICADOR = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?$")  # titular e plugins
# Projeto: a forma do kit (fundacao/core/paths.validate_id) e a do porteiro (PROJETO_RE): [a-z0-9-], 1 a 40, sem '-'
# nas pontas, sem "--" e sem nome reservado do Windows. Um projeto que o kit e o porteiro recusam não ganha perfil, área
# nem lançador (revisão do lote 2: o preparo aceitava '.', '_' e 64 caracteres, e o porteiro fechava sem explicar).
PROJETO_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
RESERVADOS_WINDOWS = frozenset({"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                                *(f"lpt{i}" for i in range(1, 10))})
USUARIO_LINUX = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MARCADOR = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
BARRA_INVERTIDA = chr(92)
CHAVE_IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"  # a variável da identidade (montada: um hook barra o nome com '=')
CHAVE_PROJETO = "FUNDACAO_PROJECT"  # projeto autenticado das sessões (guarda_caminho: escrita só nele)
NOME_DE_SKILL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
EXCLUSAO_DE_DADOS = "**/projects/*/data/**"
# Lista fechada do --tools e de FUNDACAO_FERRAMENTAS (crítica do desenho: "Bash, Read, Edit, Write, Glob, Grep, Skill,
# Task, TodoWrite e as do projeto"); WebFetch e WebSearch só com a ficha. O canário lista as da versão fixada.
FERRAMENTAS_BASE = ("Bash", "Read", "Edit", "Write", "Glob", "Grep", "Skill", "Task", "TodoWrite")
UNIDADES_NEGADAS = ("d",)  # /mnt/d (cópias e origens do titular): negada, salvo se a raiz ficar nela
# Na casa do usuário (contratos do lote 2, §6; DESENHO §1.3): transcrições, histórico e saídas do Claude Code, o login
# do Codex, chaves e espelhos do porteiro e as configurações e travas por projeto.
CASA_NEGADA = (".claude/projects/**", ".claude/history.jsonl", ".claude/file-history/**", ".claude/paste-cache/**",
               ".claude/session-env/**", ".claude/sessions/**", ".claude/shell-snapshots/**", ".claude/todos/**",
               ".claude/plans/**", ".claude/backups/**", ".codex/**", ".fundacao/**", ".local/share/fundacao-ia/**")
SOQUETES_NEGADOS = ("/tmp", "/run", "/var/run", "/mnt/wsl", "/mnt/wslg")  # sem o filtro seccomp, "sockets livres"
MARCADORES_OBRIGATORIOS = (".bashrc", ".bash_profile", ".zshrc", ".zprofile", ".profile", ".gitconfig",
                           ".gitmodules", ".ripgreprc")  # lista obrigatória do bwrap (sandbox-runtime, 31/10/2026)
MARCADORES_PASTA = (".vscode", ".idea")
MARCADORES_RECUSADOS = (".mcp.json", "CLAUDE.local.md")  # com conteúdo, o lançador não abre
# Só limpeza: o sandbox 2.1.302 deixou estes de 0 byte na pasta de trabalho nas sondas de 31/10/2026, fora da lista
# obrigatória. Arquivo comum de 0 byte, sem ligação: apagado; com conteúdo, é do projeto e fica (sem recusar). O canário
# confirma a lista na versão fixada.
MARCADORES_LIMPEZA = (".npmrc", ".yarnrc", ".yarnrc.yml")
ESQUEMA_PROJETOS_HOST = "fundacao.projetos_host/1"
ESQUEMA_PORTEIRO = "fundacao.porteiro/1"
ESQUEMA_HASHES = "fundacao.hashes_projeto/1"
ESQUEMA_ABERTURAS = "fundacao.aberturas_instaladas/1"
ESQUEMA_FICHA = "fundacao.ficha_aberturas/1"
ESQUEMA_CANARIO = "fundacao.ensaio_isolamento/1"  # relatório do canário (pacote CANARIO; contratos, §0 e §9)
FS_DRVFS = ("9p", "drvfs", "v9fs")  # o /mnt/<x> do WSL2 no /proc/mounts (a mesma lista que o canário mede)
VERSAO_CLAUDE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
REGISTRO_HOST = "registry/projetos-host.json"
TETO_REGISTRO, TETO_HASHES, TETO_JSON, TETO_ARVORE = 256 * 1024, 4 * 1024 * 1024, 2 * 1024 * 1024, 5000
# O registro da última cópia de segurança (kit, core/manutencao.py: gravado pelo `backup criar`), com o teto e o limite
# do destino do hook aviso_copia.py, que o lê do mesmo jeito.
ULTIMA_COPIA, ESQUEMA_ULTIMA_COPIA = "registry/ultima-copia.json", "fundacao.ultima_copia/1"
TETO_ULTIMA_COPIA, LIMITE_DESTINO = 64 * 1024, 400
PASTAS_IGNORADAS = ("__pycache__", ".pytest_cache", ".git")  # só na cópia da skill (o que fica de fora não é copiado)
SUFIXOS_IGNORADOS = (".pyc", ".sqlite")
# Onde o `sudo npm install -g` põe o sandbox-runtime (Node do Ubuntu e do instalador oficial): caminhos fixos, sem
# perguntar ao npm (a configuração dele, herdada do titular, decidiria o caminho; revisão do lote 2).
SECCOMP_BASES = ("/usr/local/lib/node_modules", "/usr/lib/node_modules")
RESERVADAS_1711 = ("mcp", "navegador", "git", "segredos", "outras_llm", "execucao", "leitura_liberada",
                   "perfil_navegador_copiado")
CAMPOS_DA_FICHA = {"schema_version", "ficha_id", "project_id", "versao", "motivo", "consequencias", "vigencia_ate",
                   "rede", "webfetch", "websearch", "plugins", *RESERVADAS_1711}
# Domínios e plugins da ficha: a regra é a do validador do kit desta cópia da skill (aberturas_regras e
# aberturas_plugins, carregados por modulos_do_kit), não uma réplica (emendas E3 e E4 dos contratos; folha da
# integração, I5: a réplica do HOST era menos estrita que o kit nos domínios e no frontmatter).
FICHA_NOME = re.compile(r"^ficha-v([1-9][0-9]{0,5})\.json$")
# A cópia protegida da ferramenta do titular no Ubuntu (folha da integração, I11; core/aberturas_comando do kit:
# FERRAMENTA_POSIX, REL_FERRAMENTA e ESQUEMA_HASHES; assets/host/fundacao_titular.py, conferir_copia): a mesma árvore da
# skill, só a ferramenta e o pacote do kit, com o hashes.json ao lado, de dono root.
FERRAMENTA_BASE = "/usr/local/lib/fundacao-ia"
ESQUEMA_FERRAMENTA = "fundacao.ferramenta_titular/1"
REL_FERRAMENTA = "assets/host/fundacao_titular.py"
REL_KIT_DA_FERRAMENTA = "assets/fundacao-kit/fundacao"
VERSAO_DO_KIT = re.compile(r'^KIT_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"\s*$', re.M)
CHAVES_DO_LANCADOR = ("RAIZ", "PROJETO", "USUARIO", "AREA", "SKILL", "CLAUDE_BIN", "CLAUDE_VERSAO", "CLAUDE_SHA256",
                      "CLAUDE_ORIGEM_HASH", "FERRAMENTAS", "PLUGINS", "PREPARO_SHA256", "PORTEIRO_SHA256",
                      "TEMP_PROJETO", "SONDA_INTEROP_CMD", "SONDA_INTEROP_BINFMT")
_SCRIPTS: dict = {}
_PORTEIROS: dict = {}
_KITS: dict = {}


class EntradaInvalida(ValueError):
    pass


class Conflito(EntradaInvalida):
    """Arquivo do titular com valor diferente do pedido: não é sobrescrito."""


# ------------------------------------------------------------------ peças comuns
def identificador(valor: str, rotulo: str) -> str:
    if not isinstance(valor, str) or not IDENTIFICADOR.match(valor) or ".." in valor:
        raise EntradaInvalida(f"{rotulo} inválido: {valor!r} (use letras minúsculas, dígitos, '.', '_' ou '-')")
    return valor


def e_projeto(valor) -> bool:
    return (isinstance(valor, str) and bool(PROJETO_ID.match(valor)) and "--" not in valor
            and valor not in RESERVADOS_WINDOWS)


def projeto_valido(valor: str, rotulo: str = "projeto") -> str:
    """O projeto na forma do kit e do porteiro (PROJETO_ID); fora dela, EntradaInvalida com a regra."""
    if not e_projeto(valor):
        raise EntradaInvalida(f"{rotulo} inválido: {valor!r} (a forma do kit: 1 a 40 letras minúsculas, dígitos ou "
                              "'-', sem '-' nas pontas, sem '--' e sem nome reservado do Windows)")
    return valor


def caminho_wsl(caminho: str, montagem: str = MONTAGEM) -> str:
    """Unidade do Windows (`E:` e o resto, com qualquer barra) vira `/mnt/e/...`; caminho absoluto do Linux fica
    igual, sem a barra final. Relativo e caminho de rede são recusados."""
    texto = str(caminho).strip()
    m = re.match(r"^([A-Za-z]):([/\x5c].*)?$", texto)
    if m:
        resto = re.sub(r"[/\x5c]+", "/", m.group(2) or "").strip("/")
        return montagem.rstrip("/") + "/" + m.group(1).lower() + ("/" + resto if resto else "")
    if texto.startswith("/") and not texto.startswith("//"):
        return texto.rstrip("/") or "/"
    raise EntradaInvalida(f"caminho absoluto esperado (unidade do Windows ou caminho do Linux): {caminho!r}")


def regra_windows(caminho: str) -> str:
    """Pasta do Windows (`D:\\Origem`) na forma das regras do Claude Code no Windows (`//d/Origem`): os caminhos das
    regras viram POSIX (C:\\ vira /c/) e `//` marca o absoluto (documentação de permissões, conferida em 31/10/2026)."""
    m = re.match(r"^([A-Za-z]):[/\x5c](.*)$", str(caminho).strip())
    if not m:
        raise EntradaInvalida(f"pasta do Windows com unidade esperada: {caminho!r}")
    resto = re.sub(r"[/\x5c]+", "/", m.group(2)).strip("/")
    return "//" + m.group(1).lower() + ("/" + resto if resto else "")


def pasta_do_windows(caminho: str) -> str | None:
    """Caminho do registro na forma do Windows: `/mnt/<x>/...` vira `X:\\...`, e a unidade fica como está; o que fica só
    no Ubuntu (fora de /mnt/<x>, sem unidade) devolve None: o perfil do Windows não o alcança."""
    m = re.match(r"^" + re.escape(MONTAGEM.rstrip("/")) + r"/([a-z])(?:/(.*))?$", caminho)
    if m:
        caminho = m.group(1).upper() + ":" + BARRA_INVERTIDA + (m.group(2) or "").replace("/", BARRA_INVERTIDA)
    return caminho if re.match(r"^[A-Za-z]:[/\x5c]", caminho) else None


def texto_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def renderizar(modelo, valores: dict, listas: dict | None = None):
    """Troca `{{NOME}}` pelos valores. Item de lista com um marcador de `listas` vira um item por valor (nenhum, se
    a lista estiver vazia). Sobrou marcador = erro: o perfil nunca sai pela metade."""
    listas = listas or {}

    def texto(s: str) -> str:
        def troca(m):
            if m.group(1) not in valores:
                raise EntradaInvalida(f"marcador sem valor no modelo: {m.group(0)}")
            return str(valores[m.group(1)])
        return MARCADOR.sub(troca, s)

    def passo(no):
        if isinstance(no, dict):
            return {k: passo(v) for k, v in no.items()}
        if isinstance(no, list):
            saida = []
            for item in no:
                nomes = MARCADOR.findall(item) if isinstance(item, str) else []
                de_lista = [n for n in nomes if n in listas]
                if len(de_lista) > 1:
                    raise EntradaInvalida(f"item com dois marcadores de lista: {item}")
                if de_lista:
                    marca = "{{" + de_lista[0] + "}}"
                    saida.extend(texto(item.replace(marca, valor)) for valor in listas[de_lista[0]])
                else:
                    saida.append(passo(item))
            return saida
        return texto(no) if isinstance(no, str) else no

    saida = passo(copy.deepcopy(modelo))
    sobras = [s for s in _textos(saida) if "{{" in s or "}}" in s]
    if sobras:
        raise EntradaInvalida(f"marcador não substituído no modelo: {sobras[0][:120]}")
    return saida


def _textos(no):
    if isinstance(no, dict):
        for v in no.values():
            yield from _textos(v)
    elif isinstance(no, list):
        for v in no:
            yield from _textos(v)
    elif isinstance(no, str):
        yield no


def ler_modelo(caminho: Path) -> dict:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def negar_skills(perfil: dict, nomes=()) -> dict:
    """Acrescenta `Skill(<nome>)` às negações (skill aninhada em pasta de dados: nenhuma configuração a exclui)."""
    negacoes = perfil.setdefault("permissions", {}).setdefault("deny", [])
    for nome in nomes:
        if not NOME_DE_SKILL.match(str(nome)):
            raise EntradaInvalida(f"nome de skill inválido: {nome!r}")
        if f"Skill({nome})" not in negacoes:
            negacoes.append(f"Skill({nome})")
    return perfil


def _sem_repetir(itens) -> list:
    return list(dict.fromkeys(itens))


def _objeto(valor) -> dict:
    return valor if isinstance(valor, dict) else {}


def _lista(valor) -> list:
    return valor if isinstance(valor, list) else []


def _canonico(valor) -> str:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _carregar_script(nome: str):
    """Módulo de `scripts/` da skill, pelo caminho (a regra única de segredo, a cópia conferida e a gravação sem
    ligação: um lugar só para cada coisa; o preparo não depende do sys.path)."""
    if nome not in _SCRIPTS:
        caminho = SCRIPTS / f"{nome}.py"
        if not caminho.is_file():
            raise EntradaInvalida(f"script da skill ausente: {caminho}")
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location(f"_preparo_host_{nome}", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        _SCRIPTS[nome] = modulo
    return _SCRIPTS[nome]


def modulos_do_kit(skill=SKILL) -> types.SimpleNamespace:
    """O validador do kit DESTA cópia da skill (`assets/fundacao-kit/fundacao/core/aberturas_regras.py` e
    `aberturas_plugins.py`): a regra única da ficha e dos plugins no caminho confiável (emendas E3 e E4 dos contratos;
    folha da integração, I5). Como a ferramenta do titular (fundacao_titular.kit), só o kit ao lado desta cópia,
    conferido pelo arquivo de cada módulo, nunca o da raiz da fundação (gravável pelas sessões). O pacote é carregado
    pelo caminho, sob um nome próprio: não depende do sys.path nem colide com outro `fundacao` já carregado no processo
    (o aberturas.vigente de carregar_vigente, ou o kit de outra cópia de ensaio). Sem o validador: EntradaInvalida."""
    pasta = Path(os.path.realpath(Path(skill) / "assets" / "fundacao-kit" / "fundacao"))
    chave = str(pasta)
    if chave not in _KITS:
        nome = "_preparo_host_kit_" + hashlib.sha256(chave.encode("utf-8")).hexdigest()[:12]
        sys.dont_write_bytecode = True  # sem __pycache__ no kit da skill (o CEN-11 acusa)
        try:
            spec = importlib.util.spec_from_file_location(nome, pasta / "__init__.py",
                                                          submodule_search_locations=[chave])
            if spec is None or spec.loader is None:
                raise ImportError("fundacao/__init__.py ausente")
            pacote = importlib.util.module_from_spec(spec)
            sys.modules[nome] = pacote
            spec.loader.exec_module(pacote)
            regras = importlib.import_module(nome + ".core.aberturas_regras")
            plugins = importlib.import_module(nome + ".core.aberturas_plugins")
        except Exception as exc:  # noqa: BLE001 - kit que não carrega: recusa com o motivo, sem traceback
            for carregado in [m for m in sys.modules if m == nome or m.startswith(nome + ".")]:
                del sys.modules[carregado]
            raise EntradaInvalida(f"o validador do kit da skill ({pasta}) não carregou ({type(exc).__name__}: "
                                  f"{exc})") from None
        for modulo in (regras, plugins):
            if Path(os.path.realpath(str(getattr(modulo, "__file__", "")))).parent != pasta / "core":
                raise EntradaInvalida(f"o validador carregado ({getattr(modulo, '__file__', None)}) não é o do kit "
                                      f"desta skill ({pasta})")
        _KITS[chave] = types.SimpleNamespace(pasta=pasta, regras=regras, plugins=plugins)
    return _KITS[chave]


def _e_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def _dentro(caminho: str, pasta: str) -> bool:
    """`caminho` (POSIX, normalizado) é `pasta` ou fica dentro dela."""
    caminho, pasta = caminho.rstrip("/") or "/", pasta.rstrip("/") or "/"
    return caminho == pasta or caminho.startswith(pasta + "/")


# ------------------------------------------------------------------ regra única de segredo nos perfis
def negacoes_de_segredo(regras=None) -> list[str]:
    """`Read(...)` da regra única (contratos do lote 2, §3): os nomes FORTES e as PASTAS de segredo, relativos à pasta
    de trabalho; nunca os fracos (senão `tokenizer.py`, `test_segredos.py` e o código da própria skill ficariam
    negados)."""
    listas = (regras or _carregar_script("regras_de_segredo")).listas()
    return ([f"Read(./**/{n})" for n in listas["nomes_fortes"]]
            + [f"Read(./**/{p}/**)" for p in listas["pastas_de_segredo"]])


def complemento_de_segredos(modelo: dict, regras=None) -> list[str]:
    """As negações da regra única que o modelo ainda não traz literalmente (o modelo guarda as da 1.7.9)."""
    presentes = {r for r in _lista(_objeto(_objeto(modelo).get("permissions")).get("deny")) if isinstance(r, str)}
    return [r for r in negacoes_de_segredo(regras) if r not in presentes]


def segredos_do_perfil(perfil) -> dict:
    """Os nomes e as pastas de segredo que as regras `Read(./...)` do perfil negam (para conferir com a regra única).
    O `Read(./state/**)` do perfil do Windows (a pasta do banco, na raiz) não é nome de segredo e fica de fora."""
    fortes, pastas = set(), set()
    for regra in _lista(_objeto(_objeto(perfil).get("permissions")).get("deny")):
        if not (isinstance(regra, str) and regra.startswith("Read(./") and regra.endswith(")")):
            continue
        corpo = regra[len("Read(./"):-1]
        if corpo == "state/**":
            continue
        corpo = corpo[3:] if corpo.startswith("**/") else corpo
        if corpo.endswith("/**") and "/" not in corpo[:-3]:
            pastas.add(corpo[:-3])
        elif "/" not in corpo:
            fortes.add(corpo)
    return {"fortes": fortes, "pastas": pastas}


def _confere_regra_unica(perfil, regras=None) -> list[str]:
    try:
        listas = (regras or _carregar_script("regras_de_segredo")).listas()
    except EntradaInvalida as exc:
        return [str(exc)]
    achados = segredos_do_perfil(perfil)
    problemas = []
    for nome, esperado in (("fortes", set(listas["nomes_fortes"])), ("pastas", set(listas["pastas_de_segredo"]))):
        if achados[nome] != esperado:
            faltam, sobram = sorted(esperado - achados[nome]), sorted(achados[nome] - esperado)
            problemas.append(f"negações de segredo ({nome}) diferentes da regra única (scripts/regras_de_segredo.py): "
                             f"faltam {faltam[:6]}, a mais {sobram[:6]}")
    return problemas


# ------------------------------------------------------------------ perfil do Windows
def perfil_windows(*, raiz: str, python: str, projeto: str | None = None, outros_projetos=(), somente_leitura=(),
                   backups=(), modelo: dict | None = None, negar=(), regras=None, registro: dict | None = None) -> dict:
    """`.claude/settings.json` da raiz (sessões do Windows; sem sandbox, os hooks são guarda-corpos rotulados): o
    projeto das sessões no `env` (`-Projeto`, 1.7.10: sai do settings.local.json), Read negado de cada outro projeto,
    de `projects/*/data/**` e das cópias de segurança, WebFetch e WebSearch negados, Edit negado nas pastas só de
    leitura e nas cópias e os hooks com `-I -B`. A geração prepara o perfil; só o preparo do titular o ativa.
    Com `registro` (registry/projetos-host.json, do ler_projetos_host), o Edit negado soma também as origens e as pastas
    só de leitura de TODOS os projetos registrados (folha da integração, I21: o perfil do Windows é um só e é refeito
    inteiro a cada preparo; o preparar-maquina.ps1 rodado sozinho, sem -SomenteLeitura, deixava a origem gravável).
    `/mnt/<x>/...` vira `X:\\...`; caminho só do Ubuntu (fora de /mnt/<x>, sem unidade) não cabe no perfil do Windows
    e fica de fora, como no preparar-projeto.ps1."""
    if not ntpath.isabs(str(raiz)) or not ntpath.isabs(str(python)):
        raise EntradaInvalida("raiz e python precisam ser caminhos absolutos do Windows")
    raiz, python = ntpath.normpath(str(raiz)), ntpath.normpath(str(python))  # barras do Windows nos caminhos
    if projeto is not None:
        projeto_valido(projeto)
    outros = sorted({identificador(p, "projeto") for p in outros_projetos} - {projeto})
    pasta = ntpath.join(raiz, ".claude", "hooks")
    valores = {"PYTHON": python, "RAIZ": raiz,
               **{MARCADOR_DO_HOOK[n]: ntpath.join(pasta, n) for n in HOOKS_WINDOWS},
               "STATUS_SINAIS": comando_status_windows(python, ntpath.join(pasta, "sinais_sessao.py"))}
    modelo = modelo or ler_modelo(MODELO_WINDOWS)
    registradas = []  # as pastas do registro, na forma do Windows, na ordem dos projetos e de cada lista (I21)
    for nome in sorted(_objeto(_objeto(registro).get("projetos"))):
        item = registro["projetos"][nome]
        registradas += [p for p in map(pasta_do_windows, [*item["origens"], *item["somente_leitura"]]) if p]
    # A pasta que é a raiz ou a contém (um registro antigo ou feito à mão; o registrar-projeto e os scripts do Windows
    # já a recusam: revisão seguinte da terceira rodada da integração, defeito 1) negaria às sessões a própria fundação.
    chave_raiz = _chave_de_pasta(raiz)
    for pasta_negada in [*somente_leitura, *registradas, *backups]:
        chave = _chave_de_pasta(pasta_negada)
        if chave_raiz == chave or chave_raiz.startswith(chave + BARRA_INVERTIDA):
            raise EntradaInvalida(f"a pasta {pasta_negada} contém a raiz da fundação: o perfil negaria às sessões a "
                                  f"própria fundação (use uma subpasta que não a contenha; se veio de {REGISTRO_HOST}, "
                                  "tire-a de lá)")
    leitura = [f"Read(./projects/{o}/**)" for o in outros] + [f"Read({regra_windows(b)}/**)" for b in backups]
    edicao = [f"Edit({regra_windows(p)}/**)" for p in [*somente_leitura, *registradas, *backups]]
    listas = {"SEGREDOS_DA_REGRA_UNICA": complemento_de_segredos(modelo, regras), "LEITURA_NEGADA": _sem_repetir(leitura),
              "EDICAO_NEGADA": _sem_repetir(edicao)}
    perfil = renderizar(modelo, valores, listas)
    if projeto:
        perfil.setdefault("env", {})[CHAVE_PROJETO] = projeto
    return negar_skills(perfil, negar)


def comando_status_windows(python: str, hook: str) -> str:
    """StatusLine usa shell (não args). EncodedCommand evita que os dois shells possíveis no Windows (Git Bash
    e PowerShell) interpretem espaços, dólar, crase ou aspas dos caminhos. O comando codificado é só um argv fixo
    para o interpretador conferido; não contém entrada JSON, dado de projeto ou segredo. Fonte: /docs/en/statusline.
    PowerShell encaminha stdin ao processo nativo; o hook conserva seu prazo interno de leitura."""
    def literal(caminho):
        if any(c in caminho for c in ("\n", "\r", "\0")):
            raise EntradaInvalida("caminho da linha de status com quebra de linha")
        return "'" + caminho.replace("\\", "/").replace("'", "''") + "'"
    texto = f"& {literal(python)} -I -B {literal(hook)} --status-line; exit $LASTEXITCODE"
    codificado = base64.b64encode(texto.encode("utf-16le")).decode("ascii")
    return "powershell.exe -NoProfile -NonInteractive -EncodedCommand " + codificado


# ------------------------------------------------------------------ ficha de aberturas -> perfil (contratos, §6)
def aberturas_fechadas(motivo: str = "sem ficha de aberturas válida: tudo fechado") -> dict:
    return {"valida": False, "motivo": motivo, "versao": None, "ficha_id": None, "arquivo": None, "sha256": None,
            "sig_sha256": None, "vigencia_ate": None, "rede": [], "webfetch": [], "websearch": False, "plugins": []}


def problema_do_dominio(dominio, skill=SKILL) -> str | None:
    """Motivo da recusa de um domínio da ficha (ou do perfil), ou None: o `aberturas_regras.problema_do_dominio` do kit
    desta cópia da skill, a mesma regra do `abertura preparar`, do `vigente` e da ferramenta do titular (folha da
    integração, I5), no lugar da réplica do HOST (que deixava passar PROVEDORES_COMPARTILHADOS, DNS_PARA_QUALQUER_IP, o
    IP escrito no nome e uma quebra de linha no fim). O domínio vai na mensagem, escapado. Sem o validador:
    EntradaInvalida."""
    regras = modulos_do_kit(skill).regras
    motivo = regras.problema_do_dominio(dominio)
    return f"{motivo}: {regras.mostrar(dominio)}" if motivo else None


def aberturas_da_ficha(resultado, projeto: str, hoje: date | None = None, skill=SKILL) -> dict:
    """Do resultado de `aberturas.vigente` (kit) ao que o perfil usa: rede, WebFetch, WebSearch e plugins. Qualquer
    coisa fora da forma, vencida, reservada para a 1.7.11 ou de outro projeto fecha tudo (o motivo vai ao relatório).
    Os domínios passam pelo validador do kit da `skill` (problema_do_dominio); sem ele, tudo fechado."""
    if not isinstance(resultado, dict) or resultado.get("valida") is not True:
        motivo = resultado.get("motivo_invalida") if isinstance(resultado, dict) else None
        return aberturas_fechadas(f"sem ficha de aberturas válida ({motivo or 'nenhuma'}): tudo fechado")
    ficha = resultado.get("ficha")
    if not isinstance(ficha, dict):
        return aberturas_fechadas("a ficha vigente veio sem conteúdo: tudo fechado")
    erros = []
    extras = sorted(set(ficha) - CAMPOS_DA_FICHA)
    if extras:
        erros.append(f"campos desconhecidos na ficha: {', '.join(map(str, extras))}")
    if ficha.get("schema_version") != ESQUEMA_FICHA or ficha.get("project_id") != projeto:
        erros.append("ficha de outro esquema ou de outro projeto")
    versao = ficha.get("versao")
    if not isinstance(versao, int) or isinstance(versao, bool) or versao < 1 or resultado.get("versao") != versao:
        erros.append("versão da ficha inválida")
    for secao in RESERVADAS_1711:
        if ficha.get(secao):
            erros.append(f"seção {secao} reservada para a 1.7.11")
    vigencia = ficha.get("vigencia_ate")
    if vigencia is not None:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(vigencia)) or date.fromisoformat(vigencia) < (hoje or date.today()):
                erros.append(f"ficha vencida ou com vigência inválida ({vigencia})")
        except ValueError:
            erros.append(f"vigência inválida ({vigencia})")

    def dominios(secao) -> list:
        bruto = ficha.get(secao)
        if bruto is None:
            return []
        if not isinstance(bruto, dict) or set(bruto) - {"dominios"}:
            erros.append(f"{secao} fora da forma (só a lista dominios)")
            return []
        valor = bruto.get("dominios", [])
        if not isinstance(valor, list):
            erros.append(f"{secao}.dominios não é lista")
            return []
        for d in valor:
            motivo = problema_do_dominio(d, skill)
            if motivo:
                erros.append(motivo)
        return _sem_repetir(d for d in valor if isinstance(d, str))

    try:
        rede, webfetch = dominios("rede"), dominios("webfetch")
    except EntradaInvalida as exc:  # sem o validador do kit, nenhum domínio é aceito
        return aberturas_fechadas(f"domínios da ficha não conferidos ({exc}): tudo fechado")
    if not set(webfetch) <= set(rede):
        erros.append("webfetch.dominios fora de rede.dominios (o WebFetch libera o domínio também para o shell)")
    websearch = ficha.get("websearch", False)
    if not isinstance(websearch, bool):
        erros.append("websearch não é booleano")
    plugins = []
    for p in _lista(ficha.get("plugins")) if isinstance(ficha.get("plugins", []), list) else [None]:
        p = _objeto(p)
        nome, origem, sha = p.get("nome"), p.get("origem"), p.get("manifesto_sha256")
        if (set(p) != {"nome", "origem", "manifesto_sha256"} or not isinstance(nome, str) or not IDENTIFICADOR.match(nome)
                or not isinstance(sha, str) or not SHA256.match(sha) or not _relativo_simples(origem)):
            erros.append(f"plugin fora da forma: {str(nome)[:60]!r}")
            continue
        plugins.append({"nome": nome, "origem": origem, "manifesto_sha256": sha})
    if len({p["nome"] for p in plugins}) != len(plugins):
        erros.append("plugin repetido na ficha")
    if erros:
        return aberturas_fechadas("ficha recusada pelo preparo (" + "; ".join(erros[:4]) + "): tudo fechado")
    return {"valida": True, "motivo": "ficha de aberturas assinada e vigente", "versao": versao,
            "ficha_id": ficha.get("ficha_id"), "arquivo": Path(str(resultado.get("arquivo") or "")).name or None,
            "sha256": resultado.get("sha256"), "sig_sha256": resultado.get("sig_sha256"), "vigencia_ate": vigencia,
            "rede": rede, "webfetch": webfetch, "websearch": websearch, "plugins": plugins}


def _relativo_simples(rel) -> bool:
    """Caminho relativo POSIX, sem '..', ':', barra invertida, curinga ou controle (origem de plugin no projeto)."""
    if not isinstance(rel, str) or not rel.strip() or rel.startswith("/") or BARRA_INVERTIDA in rel or ":" in rel:
        return False
    partes = rel.split("/")
    return all(p not in ("", ".", "..") and not any(c in p for c in "*?[]\n\r\0") for p in partes)


def ferramentas_do_projeto(aberturas: dict | None) -> list[str]:
    ab = aberturas or aberturas_fechadas()
    return [*FERRAMENTAS_BASE, *(["WebFetch"] if ab["webfetch"] else []), *(["WebSearch"] if ab["websearch"] else [])]


def _ferramentas_tem_web(perfil) -> tuple[bool, bool]:
    lista = str(_objeto(_objeto(perfil).get("env")).get("FUNDACAO_FERRAMENTAS", "")).split(",")
    return "WebFetch" in lista, "WebSearch" in lista


# ------------------------------------------------------------------ portão do canário (contratos, §0)
def tipo_de_fs(caminho) -> str:
    """Tipo do sistema de arquivos de `caminho` pelo /proc/mounts (o ponto de montagem mais longo que o contém), como o
    canário mede (pacote CANARIO); fora do Linux ou ilegível, 'nao_medido'."""
    if not sys.platform.startswith("linux"):
        return "nao_medido"
    try:
        real, melhor, tipo = os.path.realpath(str(caminho)), "", "nao_medido"
        with open("/proc/mounts", encoding="utf-8", errors="replace") as f:
            for linha in f:
                partes = linha.split()
                if len(partes) < 3:
                    continue
                ponto = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), partes[1])  # \040 é o espaço
                if (real == ponto or real.startswith(ponto.rstrip("/") + "/")) and len(ponto) >= len(melhor):
                    melhor, tipo = ponto, partes[2]
        return tipo
    except OSError:
        return "nao_medido"


def forma_do_caminho(caminho: str, fs: str) -> str | None:
    """A forma de caminho que o canário prova: 'ext4' (fora do /mnt) ou 'drvfs:/mnt/<x>' (o disco do Windows pelo 9p
    do WSL2). Outra combinação: None (o canário não a prova; tudo fica fechado)."""
    caminho = posixpath.normpath(str(caminho))
    if fs in FS_DRVFS:
        m = re.match(r"^/mnt/([a-z])(?:/|$)", caminho)
        return f"drvfs:/mnt/{m.group(1)}" if m else None
    return "ext4" if fs == "ext4" and not _dentro(caminho, "/mnt") else None


def _forma_do_relatorio(relatorio: dict) -> str | None:
    forma, fs = relatorio.get("forma"), relatorio.get("sistema_de_arquivos")
    if not isinstance(forma, str) or not isinstance(fs, str):
        return None
    if forma == "ext4":
        return "ext4" if fs == "ext4" else None
    m = re.match(r"^drvfs:(/mnt/[a-z]/[^\n\r\0]*)$", forma)
    return forma_do_caminho(m.group(1), fs) if m else None


def conferir_relatorio_do_canario(relatorio, *, claude_versao: str | None = None, claude_sha256: str | None = None,
                                  forma: str | None = None) -> str | None:
    """Motivo da recusa do relatório `fundacao.ensaio_isolamento/1`, ou None. Vale só o ensaio real (não simulado) com
    `conclusao.confina_comandos: true` — o canário só conclui isso com todos os itens de comando aprovados, o perfil
    gerado pelo preparo, o sandbox ligado e a forma medida igual à declarada —, do Claude Code fixado (versão e SHA-256,
    quando dados) e da forma de caminho da raiz (quando dada)."""
    if not isinstance(relatorio, dict) or relatorio.get("schema_version") != ESQUEMA_CANARIO:
        return f"o arquivo não é um relatório do canário ({ESQUEMA_CANARIO})"
    if relatorio.get("simulado") is not False:
        return "relatório de simulação: só o ensaio real conta"
    conclusao = _objeto(relatorio.get("conclusao"))
    if conclusao.get("confina_comandos") is not True:
        return ("o canário não provou que o sandbox confina os comandos ("
                + str(conclusao.get("motivo") or "sem conclusão")[:160] + ")")
    claude = _objeto(relatorio.get("claude"))
    versao, sha = claude.get("versao"), claude.get("sha256")
    if not (isinstance(versao, str) and VERSAO_CLAUDE.match(versao) and isinstance(sha, str) and SHA256.match(sha)):
        return "relatório sem a versão e o SHA-256 do Claude Code que o canário rodou"
    if claude_versao is not None and (versao != claude_versao or sha != claude_sha256):
        return (f"o canário rodou o Claude Code {versao} ({sha[:12]}...), não o fixado {claude_versao} "
                f"({str(claude_sha256)[:12]}...): rode o ensaio com o binário fixado")
    medida = _forma_do_relatorio(relatorio)
    if medida is None or conclusao.get("forma", relatorio.get("forma")) != relatorio.get("forma"):
        return "relatório com uma forma de caminho que o canário não prova (só ext4 e drvfs:/mnt/<x>)"
    if forma is not None and medida != forma:
        return f"o canário provou a forma {medida}, não a da raiz ({forma}): rode o ensaio na forma de caminho da raiz"
    return None


def portao_do_canario(area_raiz, *, claude_versao, claude_sha256, raiz_wsl: str, fs_raiz: str | None = None) -> dict:
    """Contratos, §0: nenhuma abertura vale sem o canário aprovado no ambiente real. Vale o relatório que o titular
    instalou (`instalar-canario`) em `<área>/canario/<versão>.json`, conferido contra o Claude Code fixado e a forma de
    caminho da raiz (medida no /proc/mounts). Sem ele, `aprovado` False e o motivo (tudo fechado)."""
    base = {"aprovado": False, "arquivo": None, "sha256": None, "forma": None}
    if not (isinstance(claude_versao, str) and VERSAO_CLAUDE.match(claude_versao)):
        return {**base, "motivo": "sem a versão do Claude Code fixado na área (rode o preparo do Ubuntu)"}
    arquivo = Path(area_raiz) / "canario" / f"{claude_versao}.json"
    forma = forma_do_caminho(raiz_wsl, fs_raiz or tipo_de_fs(raiz_wsl))
    if forma is None:
        return {**base, "motivo": f"a raiz ({raiz_wsl}) fica num sistema de arquivos que o canário não prova (só ext4 e "
                                  "drvfs:/mnt/<x>)"}
    if not os.path.lexists(arquivo):
        return {**base, "forma": forma, "motivo": (
            f"sem canário aprovado para o Claude Code {claude_versao} na forma {forma}: o titular roda o ensaio "
            "(scripts/ensaio_isolamento_wsl.py) no Ubuntu e instala o relatório com preparo_host.py instalar-canario")}
    try:
        dados = _ler_bytes_seguro(arquivo, TETO_JSON)
        relatorio = json.loads(dados.decode("utf-8"))
    except (OSError, ValueError) as exc:
        return {**base, "forma": forma, "arquivo": arquivo.as_posix(), "motivo": f"relatório do canário ilegível ({exc})"}
    motivo = conferir_relatorio_do_canario(relatorio, claude_versao=claude_versao, claude_sha256=claude_sha256,
                                           forma=forma)
    if motivo:
        return {**base, "forma": forma, "arquivo": arquivo.as_posix(), "motivo": motivo}
    return {"aprovado": True, "arquivo": arquivo.as_posix(), "sha256": hashlib.sha256(dados).hexdigest(),
            "forma": forma, "motivo": f"canário aprovado para o Claude Code {claude_versao} na forma {forma} "
                                      f"({str(relatorio.get('data') or 'sem data')[:32]})"}


def com_canario(aberturas: dict, canario: dict) -> dict:
    """A ficha só vale com o canário aprovado (contratos, §0): sem ele, tudo fechado, com o motivo."""
    if not aberturas["valida"] or canario.get("aprovado") is True:
        return aberturas
    return aberturas_fechadas(f"a ficha v{aberturas['versao']} não vale sem o canário aprovado no ambiente real "
                              f"(contratos, §0): tudo fechado ({canario.get('motivo')})")


# ------------------------------------------------------------------ perfil do projeto no Ubuntu
def temp_do_projeto(temp_base: str, projeto: str) -> str:
    return temp_base.rstrip("/") + "/fundacao-ia-" + projeto


def leitura_negada_wsl(raiz_wsl: str, outros, perfil_windows: str, montagem: str = MONTAGEM) -> list[str]:
    """As negações nominais do plano B (DESENHO §1.3, "defesa em profundidade"): cada outro projeto e o
    `.claude/projetos/<outro>` da raiz, as unidades do titular (salvo a da raiz), a pasta do Windows dele (salvo se a
    raiz ficar nela) e, na casa, transcrições, histórico, login do Codex, porteiro e configurações por projeto. Uma
    regra Read em deny vira denyRead do sandbox: cobre a ferramenta e o shell (documentação, 31/10/2026)."""
    regras = []
    for o in outros:
        regras += [f"Read(/{raiz_wsl}/projects/{o}/**)", f"Read(/{raiz_wsl}/.claude/projetos/{o}/**)"]
    for unidade in UNIDADES_NEGADAS:
        alvo = montagem.rstrip("/") + "/" + unidade
        if not _dentro(raiz_wsl, alvo):
            regras.append(f"Read(/{alvo}/**)")
    if perfil_windows and not _dentro(raiz_wsl, perfil_windows):
        regras.append(f"Read(/{perfil_windows}/**)")
    return regras + [f"Read(~/{rel})" for rel in CASA_NEGADA]


def _montar_perfil_wsl(raiz_wsl: str, projeto: str, outros, perfil_windows: str, ancora_base: str, somente_leitura,
                       negar, aberturas: dict, temp_base: str = TEMP_BASE, montagem: str = MONTAGEM,
                       modelo: dict | None = None, regras=None) -> dict:
    """O modelo do WSL preenchido com caminhos já no formato do WSL (para gerar e para conferir)."""
    modelo = modelo or ler_modelo(MODELO_WSL)
    proj = f"{raiz_wsl}/projects/{projeto}"
    ab = aberturas
    pasta = raiz_wsl + "/.claude/hooks/"
    valores = {"RAIZ": raiz_wsl, "PROJETO": projeto, "PROJETO_DIR": proj, "PERFIL_WINDOWS": perfil_windows,
               "ANCORA_BASE": ancora_base, "TEMP_PROJETO": temp_do_projeto(temp_base, projeto),
               "FERRAMENTAS": ",".join(ferramentas_do_projeto(ab)), "DOMINIOS_WEB": ",".join(ab["webfetch"]),
               **{MARCADOR_DO_HOOK[n]: pasta + n for n in HOOKS_WSL},
               "STATUS_SINAIS": PYTHON_LINUX + " -I -B " + shlex.quote(pasta + "sinais_sessao.py") + " --status-line"}
    web = [*([] if ab["webfetch"] else ["WebFetch"]), *([] if ab["websearch"] else ["WebSearch"])]
    listas = {"OUTROS_PROJETOS": list(outros), "SOMENTE_LEITURA": list(somente_leitura),
              "SEGREDOS_DA_REGRA_UNICA": complemento_de_segredos(modelo, regras),
              "LEITURA_NEGADA": leitura_negada_wsl(raiz_wsl, outros, perfil_windows, montagem), "WEB_NEGADA": web,
              "WEBFETCH_PERMITIDO": [f"WebFetch(domain:{d})" for d in ab["webfetch"]],
              "REDE_PERMITIDA": list(ab["rede"])}
    perfil = renderizar(modelo, valores, listas)
    perfil.setdefault("sandbox", {}).setdefault("filesystem", {}).setdefault("denyRead", []).extend(SOQUETES_NEGADOS)
    env = perfil.setdefault("env", {})
    if ab["websearch"]:
        env["FUNDACAO_WEBSEARCH"] = "1"
    if not ab["webfetch"]:
        env["CLAUDE_CODE_DISABLE_WEB_FETCH"] = "1"
    return negar_skills(perfil, negar)


def perfil_wsl(*, raiz: str, projeto: str, perfil_windows: str, outros_projetos, somente_leitura=(),
               ancora_base: str = ANCORA_BASE_WSL, montagem: str = MONTAGEM, modelo: dict | None = None, negar=(),
               aberturas: dict | None = None, temp_base: str = TEMP_BASE, regras=None, backups=()) -> dict:
    """Perfil da sessão do PROJETO no Ubuntu (`/etc/fundacao-ia/projetos/<p>/settings.wsl.json`; 1.7.10). Sem a ficha,
    tudo fechado. `backups` saiu na 1.7.10 (as cópias de segurança não ficam graváveis por sessão nenhuma)."""
    if backups:
        raise EntradaInvalida("1.7.10: a sessão do projeto não grava cópias de segurança (-Backups saiu do perfil do "
                              "Ubuntu); a cópia é do kit, fora das sessões")
    projeto_valido(projeto)
    outros = sorted({identificador(p, "projeto") for p in outros_projetos})  # negados: a forma mais larga basta
    if projeto in outros:
        raise EntradaInvalida(f"o projeto da sessão ({projeto}) não pode estar entre os projetos negados")
    raiz_wsl = caminho_wsl(raiz, montagem)
    leitura = _sem_repetir(caminho_wsl(s, montagem) for s in somente_leitura)
    for pasta in leitura:
        if _dentro(pasta, raiz_wsl):
            raise EntradaInvalida(f"pasta só de leitura dentro da raiz: {pasta}")
    ab = aberturas or aberturas_fechadas()
    perfil = _montar_perfil_wsl(raiz_wsl, projeto, outros, caminho_wsl(perfil_windows, montagem),
                                caminho_wsl(ancora_base, montagem), leitura, negar, ab, temp_base, montagem, modelo,
                                regras)
    problemas = invariantes_perfil_wsl(perfil, raiz_wsl, projeto, ab, regras=regras)
    if problemas:
        raise EntradaInvalida("o modelo do perfil do WSL não garante: " + "; ".join(problemas))
    return perfil


def invariantes_perfil_wsl(perfil, raiz_wsl: str, projeto: str | None = None, aberturas: dict | None = None,
                           regras=None) -> list[str]:
    """O que o perfil do projeto tem de garantir (DESENHO §1.4 e a folha do HOST), ao gerar e ao conferir."""
    problemas = []
    perfil = _objeto(perfil)
    sandbox = _objeto(perfil.get("sandbox"))
    fs = _objeto(sandbox.get("filesystem"))
    rede = _objeto(sandbox.get("network"))
    perm = _objeto(perfil.get("permissions"))
    env = _objeto(perfil.get("env"))
    raiz = raiz_wsl.rstrip("/")
    projeto = projeto or env.get(CHAVE_PROJETO)
    if not e_projeto(projeto):
        return ["perfil sem o projeto da sessão (FUNDACAO_PROJECT) na forma do kit"]
    proj = f"{raiz}/projects/{projeto}"
    if sandbox.get("enabled") is not True or sandbox.get("failIfUnavailable") is not True:
        problemas.append("sandbox desligado ou sem falha obrigatória (failIfUnavailable)")
    if sandbox.get("allowUnsandboxedCommands") is not False:
        problemas.append("comandos fora do sandbox permitidos (allowUnsandboxedCommands)")
    if "excludedCommands" in sandbox:
        problemas.append("excludedCommands roda fora do sandbox ('not a security boundary'): não pode haver")
    if perm.get("blockReadsOutsideWorkingDirectories") is not True:
        problemas.append("leitura fora das pastas de trabalho liberada (blockReadsOutsideWorkingDirectories)")
    if rede.get("strictAllowlist") is not True:
        problemas.append("rede sem strictAllowlist: host fora da lista vira pergunta, não recusa")
    dominios = _lista(rede.get("allowedDomains"))
    if aberturas is not None and dominios != list(aberturas["rede"]):
        problemas.append("rede do sandbox diferente da ficha: sandbox.network.allowedDomains tem de ser a lista exata "
                         "de rede.dominios da ficha vigente (sem ficha, vazia)")
    negados = [c for c in _lista(fs.get("denyWrite")) if isinstance(c, str)]
    for alvo, rotulo in ((raiz + "/.claude", ".claude da raiz"), (proj + "/.claude", ".claude do projeto"),
                         (proj + "/.porteiro/respostas", "respostas do porteiro"), (raiz + "/registry", "registry/")):
        if alvo not in negados:
            problemas.append(f"{rotulo} gravável pelo sandbox (falta em denyWrite)")
    for alvo in (proj, proj + "/.porteiro", proj + "/.porteiro/pedidos"):
        if alvo in negados:
            problemas.append(f"denyWrite em {alvo[len(raiz) + 1:]}: a fila do porteiro deixaria de funcionar (só "
                             "respostas/ é negada)")
    estado = raiz + "/state"
    negacoes = [n for n in _lista(perm.get("deny")) if isinstance(n, str)]
    if f"Read(/{estado}/**)" not in negacoes:
        problemas.append("ferramenta Read e shell com acesso a state/ (falta Read(//<raiz>/state/**))")
    for chave in ("allowRead", "allowWrite"):
        for c in _lista(fs.get(chave)):
            if isinstance(c, str) and (_dentro(c, estado) or _dentro(estado, c)):
                problemas.append(f"state/ em {chave}: o banco fica fora do sandbox (só o porteiro o abre)")
    for c in _lista(fs.get("allowWrite")):
        if not (isinstance(c, str) and _dentro(c, proj)):
            problemas.append(f"allowWrite fora do projeto: {str(c)[:80]}")
    ab_web = (bool(aberturas["webfetch"]), bool(aberturas["websearch"])) if aberturas else _ferramentas_tem_web(perfil)
    if ab_web[0] == ("WebFetch" in negacoes) or ab_web[1] == ("WebSearch" in negacoes):
        problemas.append("WebFetch e WebSearch: só sem negação quando a ficha os abre (sem ficha, negados: saída de "
                         "dados que o sandbox de rede não cobre)")
    if EXCLUSAO_DE_DADOS not in _lista(perfil.get("claudeMdExcludes")):
        problemas.append("instruções de pastas de dados (CLAUDE.md, AGENTS.md) carregáveis: falta claudeMdExcludes")
    for chave, esperado in (("syncClaudeAiSkills", False), ("syncClaudeAiPlugins", False),
                            ("disableClaudeAiConnectors", True)):
        if perfil.get(chave) is not esperado:
            problemas.append(f"{chave} tem de ser {str(esperado).lower()}")
    esperado_env = {CHAVE_IDENTIDADE: f"sessao-{projeto}", CHAVE_PROJETO: projeto, "FUNDACAO_RAIZ": raiz,
                    "FUNDACAO_PORTEIRO": proj + "/.porteiro", "FUNDACAO_MCP_PERMITIDAS": ""}
    if aberturas is not None:
        esperado_env["FUNDACAO_FERRAMENTAS"] = ",".join(ferramentas_do_projeto(aberturas))
        esperado_env["FUNDACAO_DOMINIOS_WEB"] = ",".join(aberturas["webfetch"])
    for chave, valor in esperado_env.items():
        if env.get(chave) != valor:
            problemas.append(f"env.{chave} diferente do esperado para o projeto {projeto}")
    lista = str(env.get("FUNDACAO_FERRAMENTAS", "")).split(",")
    if not set(FERRAMENTAS_BASE) <= set(lista) or not set(lista) <= set(FERRAMENTAS_BASE) | {"WebFetch", "WebSearch"}:
        problemas.append("FUNDACAO_FERRAMENTAS fora da lista fechada do projeto")
    for chave in ("FUNDACAO_PERMITIR_TROCA_IDENTIDADE", "FUNDACAO_PORTEIRO_SERVIDOR", "FUNDACAO_PROJETO_TRAVADO"):
        if chave in env:
            problemas.append(f"env.{chave} não pode estar no perfil da sessão")
    grupos = _objeto(perfil.get("hooks"))
    for evento, matcher, nome in GANCHOS_WSL:
        alvo = f"{raiz}/.claude/hooks/{nome}"
        ok = any(_objeto(g).get("matcher") == matcher and any(
            _objeto(h).get("command") == PYTHON_LINUX and _objeto(h).get("args") == ["-I", "-B", alvo]
            and _objeto(h).get("onFailure") == "block" for h in _lista(_objeto(g).get("hooks")))
            for g in _lista(grupos.get(evento)))
        if not ok:
            problemas.append(f"hook {nome} da raiz ausente ou fora da forma ({evento} {matcher}, python3 -I -B)")
    return problemas + _confere_regra_unica(perfil, regras)


def _caminho_de_vaga(caminho) -> bool:
    """Caminho absoluto do Linux, normalizado, sem curinga nem quebra de linha (como o gerador o escreve)."""
    return (isinstance(caminho, str) and caminho.startswith("/") and not caminho.startswith("//")
            and posixpath.normpath(caminho) == caminho and not any(c in caminho for c in "*?\n\r\0"))


def parametros_do_perfil_wsl(perfil, raiz_wsl: str, projeto: str | None = None) -> dict:
    """As vagas do modelo como estão no perfil (projeto, pasta do Windows, âncora, temp, pastas só de leitura, outros
    projetos, skills negadas e o que a ficha abriu), para gerar de novo e comparar. Fora da forma: EntradaInvalida.
    O preparo e o lançador comparam com vagas confiáveis (registro, hashes.json e a ficha); estas servem à conferência
    da estrutura quando só o perfil está à mão."""
    raiz = raiz_wsl.rstrip("/")
    perfil = _objeto(perfil)
    fs = _objeto(_objeto(perfil.get("sandbox")).get("filesystem"))
    env = _objeto(perfil.get("env"))
    projeto = projeto or env.get(CHAVE_PROJETO)
    if not e_projeto(projeto):
        raise EntradaInvalida("perfil fora do formato do modelo (sem o projeto da sessão)")
    proj = f"{raiz}/projects/{projeto}"
    janelas = [c for c in _lista(fs.get("denyRead")) if isinstance(c, str) and c.startswith("/") and c.endswith("/.ssh")]
    lidas = [c for c in _lista(fs.get("allowRead"))]
    if len(janelas) != 1 or len(lidas) < 3 or lidas[0] != raiz + "/fundacao":
        raise EntradaInvalida("perfil fora do formato do modelo (pasta do Windows, kit ou âncora)")
    temp = lidas[-1]
    if not (isinstance(temp, str) and posixpath.basename(temp) == "fundacao-ia-" + projeto):
        raise EntradaInvalida("perfil fora do formato do modelo (temp do projeto)")
    vagas = {"projeto": projeto, "perfil_windows": janelas[0][:-len("/.ssh")], "ancora_base": lidas[1],
             "temp_base": posixpath.dirname(temp), "somente_leitura": lidas[2:-1],
             "outros_projetos": [c[len(raiz) + len("/projects/"):] for c in _lista(fs.get("denyWrite"))
                                 if isinstance(c, str) and c.startswith(raiz + "/projects/") and not _dentro(c, proj)],
             "negar": [r[len("Skill("):-1] for r in _lista(_objeto(perfil.get("permissions")).get("deny"))
                       if isinstance(r, str) and r.startswith("Skill(") and r.endswith(")")]}
    for caminho in [vagas["perfil_windows"], vagas["ancora_base"], vagas["temp_base"], *vagas["somente_leitura"]]:
        if not _caminho_de_vaga(caminho):
            raise EntradaInvalida(f"caminho fora do formato do modelo no perfil: {str(caminho)[:80]!r}")
    for nome in vagas["outros_projetos"]:
        identificador(nome, "projeto negado no perfil")
    rede = [d for d in _lista(_objeto(_objeto(perfil.get("sandbox")).get("network")).get("allowedDomains"))]
    webfetch = [r[len("WebFetch(domain:"):-1] for r in _lista(_objeto(perfil.get("permissions")).get("allow"))
                if isinstance(r, str) and r.startswith("WebFetch(domain:") and r.endswith(")")]
    for d in [*rede, *webfetch]:
        motivo = problema_do_dominio(d)  # o validador do kit (I5); sem ele, EntradaInvalida: a conferência recusa
        if motivo:
            raise EntradaInvalida("perfil fora do formato do modelo (" + motivo + ")")
    vagas["aberturas"] = {**aberturas_fechadas("lido do próprio perfil"), "rede": rede, "webfetch": webfetch,
                          "websearch": env.get("FUNDACAO_WEBSEARCH") == "1"}
    return vagas


def _primeira_diferenca(atual, esperado, caminho: str = "") -> str:
    """Onde o perfil difere do esperado (só o caminho das chaves, sem valores)."""
    if isinstance(atual, dict) and isinstance(esperado, dict):
        for k in sorted(set(atual) | set(esperado), key=str):
            if k not in esperado:
                return f"{caminho}{k} (a mais)"
            if k not in atual:
                return f"{caminho}{k} (falta)"
            if _canonico(atual[k]) != _canonico(esperado[k]):
                return _primeira_diferenca(atual[k], esperado[k], f"{caminho}{k}.")
    elif isinstance(atual, list) and isinstance(esperado, list) and len(atual) == len(esperado):
        for i, (x, y) in enumerate(zip(atual, esperado)):
            if _canonico(x) != _canonico(y):
                return _primeira_diferenca(x, y, f"{caminho.rstrip('.')}[{i}].")
    return caminho.rstrip(".") or "(perfil inteiro)"


def conferir_perfil_wsl(perfil, raiz_wsl: str, projeto: str | None = None, outros_projetos=None, *,
                        parametros: dict | None = None, aberturas: dict | None = None, somente_leitura=None,
                        negar=None, ferramentas_lancador: str | None = None, regras=None) -> list[str]:
    """O perfil do projeto que o preparo fixa: os invariantes e, inteiro, igual ao que o modelo gera [Decisão; auditoria
    Codex Security da 1.7.6, #5]. Com `outros_projetos` (os da raiz), cada um tem de estar negado; com `parametros`,
    `aberturas`, `somente_leitura` e `negar` (do hashes.json, da ficha vigente e do registro), a comparação usa esses
    valores confiáveis em vez das vagas lidas do perfil; com `ferramentas_lancador`, FUNDACAO_FERRAMENTAS tem de ser a
    lista do --tools do lançador. Sem `aberturas` (a ficha vigente), vale "sem ficha válida, tudo fechado": a rede, o
    WebFetch e o WebSearch que o próprio perfil declara não contam."""
    raiz = raiz_wsl.rstrip("/")
    ab = aberturas if aberturas is not None else aberturas_fechadas()
    problemas = invariantes_perfil_wsl(perfil, raiz, projeto, ab, regras=regras)
    da_sessao = projeto or _objeto(_objeto(perfil).get("env")).get(CHAVE_PROJETO)
    prefixo, negados = f"Read(/{raiz}/projects/", set()
    for regra in _lista(_objeto(_objeto(perfil).get("permissions")).get("deny")):
        if isinstance(regra, str) and regra.startswith(prefixo) and regra.endswith("/**)"):
            negados.add(regra[len(prefixo):-len("/**)")])
    if outros_projetos is not None:
        faltam = sorted(set(outros_projetos) - negados - {da_sessao})
        if faltam:
            problemas.append("projetos da raiz sem leitura e escrita negadas no perfil (criados depois do preparo?): "
                             + ", ".join(faltam))
    if da_sessao in negados:
        problemas.append(f"o projeto da sessão ({da_sessao}) está entre os projetos negados")
    try:
        vagas = parametros_do_perfil_wsl(perfil, raiz, projeto)
    except EntradaInvalida as exc:
        return problemas + [str(exc)]
    p = {**vagas, **{k: v for k, v in (parametros or {}).items() if v is not None}}
    try:
        esperado = _montar_perfil_wsl(raiz, vagas["projeto"], vagas["outros_projetos"], p["perfil_windows"],
                                      p["ancora_base"],
                                      vagas["somente_leitura"] if somente_leitura is None else list(somente_leitura),
                                      vagas["negar"] if negar is None else list(negar), ab, p["temp_base"],
                                      regras=regras)
    except EntradaInvalida as exc:
        return problemas + [str(exc)]
    if _canonico(perfil) != _canonico(esperado):
        problemas.append("perfil diferente do que o modelo da skill gera para esta raiz e esta ficha (primeira "
                         f"diferença: {_primeira_diferenca(perfil, esperado)})")
    if ferramentas_lancador is not None and ferramentas_lancador != _objeto(_objeto(perfil).get("env")).get(
            "FUNDACAO_FERRAMENTAS"):
        problemas.append("FUNDACAO_FERRAMENTAS diferente da lista do --tools do lançador")
    return problemas


def projetos_da_raiz(raiz) -> list[str]:
    """Nomes das pastas no primeiro nível de `projects/` (sem entrar nelas e sem pastas ocultas)."""
    pasta = Path(raiz) / "projects"
    if not pasta.is_dir():
        return []
    return sorted(p.name for p in pasta.iterdir() if p.is_dir() and not p.name.startswith("."))


# ------------------------------------------------------------------ registry/projetos-host.json (só o titular grava)
def _absoluto_registrado(caminho) -> str:
    """Caminho absoluto como fica no registro: unidade do Windows (`D:\\...`, barras do Windows) ou POSIX normalizado.
    Curinga, controle, caminho de rede e relativo: EntradaInvalida."""
    texto = str(caminho).strip()
    if not texto or any(c in texto for c in "*?[]\n\r\0"):
        raise EntradaInvalida(f"caminho inválido para o registro: {str(caminho)[:80]!r}")
    if re.match(r"^[A-Za-z]:[/\x5c]", texto):
        normal = ntpath.normpath(texto)
        return normal[0].upper() + normal[1:]
    if texto.startswith("/") and not texto.startswith("//"):
        return posixpath.normpath(texto)
    raise EntradaInvalida(f"caminho absoluto esperado (unidade do Windows ou caminho do Linux): {str(caminho)[:80]!r}")


def _visao_local(caminho: str) -> Path:
    """O caminho do registro visto deste sistema (no Linux, `D:\\x` vira /mnt/d/x; no Windows, /mnt/d/x vira D:\\x)."""
    if os.name == "nt":
        m = re.match(r"^/mnt/([a-z])(?:/(.*))?$", caminho)
        return Path(f"{m.group(1).upper()}:\\" + (m.group(2) or "").replace("/", "\\")) if m else Path(caminho)
    return Path(caminho_wsl(caminho)) if re.match(r"^[A-Za-z]:", caminho) else Path(caminho)


def _validar_registro(dados) -> dict:
    if not isinstance(dados, dict) or dados.get("schema_version") != ESQUEMA_PROJETOS_HOST:
        raise EntradaInvalida(f"{REGISTRO_HOST} fora do esquema {ESQUEMA_PROJETOS_HOST}")
    if set(dados) - {"schema_version", "projetos"} or not isinstance(dados.get("projetos"), dict):
        raise EntradaInvalida(f"{REGISTRO_HOST} com chaves a mais ou sem 'projetos'")
    for nome, item in dados["projetos"].items():
        projeto_valido(nome, f"projeto em {REGISTRO_HOST}")
        if not isinstance(item, dict) or set(item) != {"origens", "somente_leitura", "aninhadas_negadas"}:
            raise EntradaInvalida(f"{REGISTRO_HOST}: projeto {nome} fora da forma")
        for chave in ("origens", "somente_leitura"):
            if not isinstance(item[chave], list) or any(_absoluto_registrado(c) != c for c in item[chave]):
                raise EntradaInvalida(f"{REGISTRO_HOST}: {nome}.{chave} fora da forma")
        if not isinstance(item["aninhadas_negadas"], list) or not all(
                isinstance(n, str) and NOME_DE_SKILL.match(n) for n in item["aninhadas_negadas"]):
            raise EntradaInvalida(f"{REGISTRO_HOST}: {nome}.aninhadas_negadas fora da forma")
    return dados


def ler_projetos_host(raiz) -> dict:
    """`registry/projetos-host.json` (contratos do lote 2, §6): lido sem seguir ligação, até 256 KiB, no esquema
    `fundacao.projetos_host/1`. Ausente: o registro vazio."""
    raiz = Path(raiz)
    vazio = {"schema_version": ESQUEMA_PROJETOS_HOST, "projetos": {}}
    gravacao = _carregar_script("gravacao_segura")
    if gravacao.com_ligacao(raiz, REGISTRO_HOST):
        raise EntradaInvalida(f"{REGISTRO_HOST} passa por ligação (link simbólico ou junção): não lido")
    arquivo = raiz / REGISTRO_HOST
    if not os.path.lexists(arquivo):
        return vazio
    return _validar_registro(_ler_json_seguro(arquivo, TETO_REGISTRO))


def registrar_projeto(raiz, projeto: str, origens, somente_leitura=(), negar=()) -> dict:
    """Soma ao registro (só cresce) as origens, as pastas só de leitura e as skills aninhadas negadas do projeto; cada
    pasta tem de existir e ficar fora da raiz. Grava inteiro ou nada (temporário e troca), em LF, sem seguir ligação."""
    raiz = Path(raiz)
    projeto_valido(projeto)
    if not (raiz / "projects" / projeto).is_dir():
        raise EntradaInvalida(f"o projeto {projeto} não existe em {raiz / 'projects'}")
    if not origens:
        raise EntradaInvalida("informe ao menos uma --origem (pasta de onde o projeto veio, fluxo B)")
    dados = ler_projetos_host(raiz)
    item = dados["projetos"].setdefault(projeto, {"origens": [], "somente_leitura": [], "aninhadas_negadas": []})
    raiz_real = os.path.normcase(os.path.realpath(raiz))
    for chave, valores in (("origens", origens), ("somente_leitura", somente_leitura)):
        for valor in valores:
            normal = _absoluto_registrado(valor)
            local = _visao_local(normal)
            if not local.is_dir():
                raise EntradaInvalida(f"pasta inexistente (ou não montada) para o registro: {normal}")
            real = os.path.normcase(os.path.realpath(local))
            if real == raiz_real or real.startswith(raiz_real.rstrip(os.sep) + os.sep):
                raise EntradaInvalida(f"pasta dentro da raiz da fundação não vai ao registro: {normal}")
            # Nem a que contém a raiz (a mesma regra do Get-PastasConferidas dos scripts do Windows; revisão da terceira
            # rodada da integração, defeito 1): o Edit negado dela negaria às sessões a escrita na própria fundação.
            if raiz_real.startswith(real.rstrip(os.sep) + os.sep):
                raise EntradaInvalida(f"pasta que contém a raiz da fundação não vai ao registro (use uma subpasta que "
                                      f"não a contenha): {normal}")
            if normal not in item[chave]:
                item[chave].append(normal)
    for nome in negar:
        if not NOME_DE_SKILL.match(str(nome)):
            raise EntradaInvalida(f"nome de skill inválido: {nome!r}")
        if nome not in item["aninhadas_negadas"]:
            item["aninhadas_negadas"].append(nome)
    _validar_registro(dados)
    gravacao = _carregar_script("gravacao_segura")
    gravacao.pasta_sem_ligacao(raiz, "registry")
    gravacao.publicar(raiz / REGISTRO_HOST, texto_json(dados).encode("utf-8"))
    return dados


def vagas_do_registro(registro: dict, projeto: str, montagem: str = MONTAGEM) -> dict:
    """Do registro ao perfil do projeto: origens e pastas só de leitura dele (no formato do WSL) e as skills negadas
    de TODOS os projetos (negação cumulativa: o que um projeto trouxe aninhado fica negado nos outros)."""
    item = registro["projetos"].get(projeto, {"origens": [], "somente_leitura": [], "aninhadas_negadas": []})
    negar = _sem_repetir(n for p in sorted(registro["projetos"]) for n in registro["projetos"][p]["aninhadas_negadas"])
    return {"somente_leitura": _sem_repetir(caminho_wsl(c, montagem) for c in [*item["origens"], *item["somente_leitura"]]),
            "negar": negar}


def _chave_de_pasta(caminho: str) -> str:
    return ntpath.normcase(ntpath.normpath(str(caminho))).rstrip(BARRA_INVERTIDA)


def fora_do_registro(registro: dict, somente_leitura=(), negar=()) -> dict:
    """Das negações dadas ao preparar-maquina.ps1, as que o registry/projetos-host.json não cobre (revisão da terceira
    rodada da integração, defeito 3): o perfil do Windows é refeito inteiro a cada preparo, e o preparar-projeto.ps1 o
    refaz só com o registro. Uma pasta de -SomenteLeitura fora de toda pasta registrada (origem ou só leitura, de
    qualquer projeto; `/mnt/<x>` vale pela unidade) e um nome de -NegarSkill que nenhum projeto registrou somem, em
    silêncio, no próximo preparo de qualquer projeto: o script deixa a pendência com eles."""
    registradas, nomes = [], set()
    for item in _objeto(_objeto(registro).get("projetos")).values():
        registradas += [_chave_de_pasta(p) for p in map(pasta_do_windows, [*item["origens"], *item["somente_leitura"]])
                        if p]
        nomes.update(item["aninhadas_negadas"])

    def coberta(pasta) -> bool:
        chave = _chave_de_pasta(pasta)
        return any(chave == r or chave.startswith(r + BARRA_INVERTIDA) for r in registradas)

    return {"somente_leitura": [p for p in _sem_repetir(somente_leitura) if not coberta(p)],
            "negar_skill": [n for n in _sem_repetir(negar) if n not in nomes]}


def _json_estrito(texto: str):
    """JSON sem chave repetida nem NaN e Infinity (o hook aviso_copia.py lê o mesmo registro assim)."""
    def objeto(pares):
        saida = {}
        for chave, valor in pares:
            if chave in saida:
                raise ValueError("chave repetida")
            saida[chave] = valor
        return saida

    def constante(nome):
        raise ValueError(f"constante fora do JSON: {nome}")

    return json.loads(texto, object_pairs_hook=objeto, parse_constant=constante)


def ultima_copia(raiz) -> dict:
    """O destino da última cópia de segurança em `registry/ultima-copia.json` (fundacao.ultima_copia/1, gravado pelo
    `backup criar` do kit), para o portão das cópias dos dois scripts do Windows (revisão da terceira rodada da
    integração, defeito 2): lido como o hook aviso_copia.py o lê, sem seguir ligação nem vínculo físico, até 64 KiB, e
    sem tocar o disco das cópias. Uma sessão forja o registro (no Windows não há sandbox): ele serve só para recusar o
    -SemBackups e sugerir a pasta no comando pronto, nunca para aceitar. `registro`: ausente, lido ou recusado (com o
    `motivo`, sem conteúdo do arquivo). `destino_windows`: o destino na forma do Windows (`/mnt/<x>/...` vira
    `X:\\...`), ou None quando fica só no Ubuntu; `pasta_das_copias`: a pasta de cima dele."""
    res = {"registro": "ausente", "destino": None, "destino_windows": None, "pasta_das_copias": None, "motivo": None}
    raiz = Path(raiz)
    try:
        if _carregar_script("gravacao_segura").com_ligacao(raiz, ULTIMA_COPIA):
            raise EntradaInvalida("o caminho passa por ligação (link simbólico ou junção)")
        arquivo = raiz / ULTIMA_COPIA
        if not os.path.lexists(arquivo):
            return res
        dados = _json_estrito(_ler_bytes_seguro(arquivo, TETO_ULTIMA_COPIA, dentro_de=raiz).decode("utf-8"))
        if not isinstance(dados, dict) or dados.get("schema_version") != ESQUEMA_ULTIMA_COPIA:
            raise EntradaInvalida(f"fora do esquema {ESQUEMA_ULTIMA_COPIA}")
        destino = dados.get("destino")
        if (not isinstance(destino, str) or not destino or len(destino) > LIMITE_DESTINO
                or any(unicodedata.category(c)[0] == "C" or unicodedata.category(c) in ("Zl", "Zp") for c in destino)):
            raise EntradaInvalida(f"destino ausente, acima de {LIMITE_DESTINO} caracteres ou com caractere de controle")
        windows = pasta_do_windows(destino)
        if windows is None and not (destino.startswith("/") and not destino.startswith("//")):
            raise EntradaInvalida("destino fora da forma: caminho absoluto esperado")
        if windows is not None and re.search(r'[*?"<>|:]', windows[2:]):
            raise EntradaInvalida("destino com caractere que uma pasta do Windows não tem")
    except (EntradaInvalida, OSError, ValueError, RecursionError) as exc:
        return {**res, "registro": "recusado", "motivo": str(exc)[:300]}
    windows = ntpath.normpath(windows) if windows else None
    return {**res, "registro": "lido", "destino": destino, "destino_windows": windows,
            "pasta_das_copias": ntpath.dirname(windows) if windows else None}


# ------------------------------------------------------------------ identidade (settings.local.json do Windows)
def identidade(titular: str, atual: dict | None = None, projeto: str | None = None, estrito: bool = False,
               sem_projeto: bool = False) -> dict:
    """`.claude/settings.local.json`: a identidade das sessões do Windows. Com o arquivo atual, acrescenta só a
    identidade e mantém o resto; outra identidade já gravada é `Conflito`. Com `estrito`, sai só a identidade (e o
    projeto, se houver). Com `sem_projeto` (1.7.10: o projeto das sessões do Windows vai ao `env` do settings.json, e
    um FUNDACAO_PROJECT no local passaria por cima dele), o projeto sai deste arquivo."""
    identificador(titular, "titular")
    novo = copy.deepcopy(atual) if isinstance(atual, dict) else {}
    env = novo.setdefault("env", {})
    if not isinstance(env, dict):
        raise EntradaInvalida("settings.local.json com 'env' que não é objeto")
    existente = env.get(CHAVE_IDENTIDADE)
    if existente not in (None, titular):
        raise Conflito(f"settings.local.json já entrega a identidade {existente!r}, não {titular!r}: só o titular "
                       f"decide a troca")
    env[CHAVE_IDENTIDADE] = titular
    if projeto is not None:
        projeto_valido(projeto)
        if env.get(CHAVE_PROJETO) not in (None, projeto):
            raise Conflito(f"settings.local.json já entrega o projeto {env[CHAVE_PROJETO]!r}, não {projeto!r}: só o "
                           f"titular decide a troca")
        env[CHAVE_PROJETO] = projeto
    if sem_projeto:
        env.pop(CHAVE_PROJETO, None)
    if estrito:
        novo = {"env": {k: env[k] for k in (CHAVE_IDENTIDADE, CHAVE_PROJETO) if k in env}}
    return novo


def conferir_identidade(dados, titular: str, projeto: str | None = None) -> list[str]:
    """`settings.local.json` só com `env` da identidade do titular e, se houver, o projeto da sessão. Hook, permissão,
    plugin, sandbox ou variável a mais (como FUNDACAO_PERMITIR_TROCA_IDENTIDADE) mudariam a sessão por fora do perfil
    fixado [Decisão; auditoria Codex Security da 1.7.6, #5]. Das chaves a mais sai só o nome; valor só sai se for um
    identificador."""
    identificador(titular, "titular")
    if not isinstance(dados, dict):
        return ["settings.local.json não é um objeto JSON"]

    def mostrar(valor) -> str:
        return repr(valor) if isinstance(valor, str) and IDENTIFICADOR.match(valor) else "(ausente ou fora do formato)"

    problemas = []
    extras = sorted(str(k) for k in dados if k != "env")
    if extras:
        problemas.append("chaves além da identidade: " + ", ".join(extras))
    env = dados.get("env")
    if not isinstance(env, dict):
        return problemas + ["sem o objeto env com a identidade"]
    extras = sorted(str(k) for k in env if k not in (CHAVE_IDENTIDADE, CHAVE_PROJETO))
    if extras:
        problemas.append("variáveis além da identidade em env: " + ", ".join(extras))
    if env.get(CHAVE_IDENTIDADE) != titular:
        problemas.append(f"a identidade entregue é {mostrar(env.get(CHAVE_IDENTIDADE))}, não a do titular {titular!r}")
    if CHAVE_PROJETO in env and env[CHAVE_PROJETO] != projeto:
        problemas.append(f"o projeto entregue é {mostrar(env[CHAVE_PROJETO])}, não o da sessão ({projeto!r})")
    return problemas


# ------------------------------------------------------------------ /etc/wsl.conf
def ajustar_wsl_conf(texto: str) -> tuple[str, bool]:
    """Um único bloco `[interop]` com `enabled=false` e `appendWindowsPath=false`; o resto do arquivo fica igual.
    Blocos `[interop]` repetidos (no caso real, três) viram um, com as outras chaves do primeiro em que aparecem."""
    original = texto
    linhas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if linhas and linhas[-1] == "":
        linhas.pop()
    preambulo, secoes = [], []  # secoes: [nome em minúsculas, linha do cabeçalho, corpo]
    for linha in linhas:
        m = re.match(r"^\s*\[([^\]]+)\]\s*$", linha)
        if m:
            secoes.append([m.group(1).strip().lower(), linha, []])
        elif secoes:
            secoes[-1][2].append(linha)
        else:
            preambulo.append(linha)

    def chave(linha: str) -> str | None:
        m = re.match(r"^\s*([A-Za-z0-9_.-]+)\s*=", linha)
        return m.group(1).lower() if m else None

    interop = [s for s in secoes if s[0] == "interop"]
    if not interop:
        if (preambulo or secoes) and (secoes[-1][2] if secoes else preambulo)[-1:] != [""]:
            (secoes[-1][2] if secoes else preambulo).append("")
        secoes.append(["interop", "[interop]", []])
        interop = [secoes[-1]]
    primeira = interop[0]
    vistas = {chave(l) for l in primeira[2] if chave(l)}
    for repetida in interop[1:]:
        for linha in repetida[2]:
            k = chave(linha)
            if k and k not in vistas:
                primeira[2].append(linha)
                vistas.add(k)
        secoes.remove(repetida)
    corpo, presentes = [], set()
    for linha in primeira[2]:
        k = chave(linha)
        if k in ("enabled", "appendwindowspath"):
            presentes.add(k)
            if linha.split("=", 1)[1].strip().lower() != "false":
                linha = ("enabled" if k == "enabled" else "appendWindowsPath") + "=false"
        corpo.append(linha)
    fim = len(corpo)
    while fim and not corpo[fim - 1].strip():
        fim -= 1
    faltam = [n + "=false" for n, k in (("enabled", "enabled"), ("appendWindowsPath", "appendwindowspath"))
              if k not in presentes]
    primeira[2] = corpo[:fim] + faltam + corpo[fim:]
    saida = list(preambulo)
    for _nome, cabecalho, corpo_secao in secoes:
        saida.append(cabecalho)
        saida.extend(corpo_secao)
    while saida and not saida[-1].strip():
        saida.pop()
    novo = "\n".join(saida) + "\n"
    return novo, novo != original


# ------------------------------------------------------------------ árvores conferidas (kit, skill, plugins)
def _ler_bytes_seguro(arquivo, teto: int, dentro_de=None) -> bytes:
    """Bytes de arquivo comum, sem seguir ligação nem vínculo físico (o caminho conferido de scripts/copia_segura.py),
    até `teto` bytes."""
    copia = _carregar_script("copia_segura")
    fd = copia.abrir_comum(arquivo, dentro_de)
    try:
        partes, total = [], 0
        while total <= teto and (bloco := os.read(fd, 1 << 16)):
            partes.append(bloco)
            total += len(bloco)
    finally:
        os.close(fd)
    if total > teto:
        raise EntradaInvalida(f"{Path(arquivo).name} acima do teto de {teto} bytes")
    return b"".join(partes)


def _ler_json_seguro(arquivo, teto: int):
    """JSON de arquivo comum, sem seguir ligação nem vínculo físico, até `teto` bytes."""
    return json.loads(_ler_bytes_seguro(arquivo, teto).decode("utf-8-sig"))


def manifesto_de_arvore(pasta, *, pastas_ignoradas=PASTAS_IGNORADAS, sufixos_ignorados=SUFIXOS_IGNORADOS,
                        teto: int = TETO_ARVORE) -> dict:
    """{caminho relativo POSIX: {"sha256", "bytes"}} dos arquivos comuns sob `pasta`, lidos pelo caminho conferido de
    `scripts/copia_segura.py`, sem seguir ligação; ligação, vínculo físico, tipo especial ou mais de `teto` arquivos
    dentro dela: EntradaInvalida. A pasta vazia ou relativa também (reconferência do lote 2: o `""` de um hashes.json
    sem o filtro seccomp virava a pasta atual do titular, e a abertura lia até 5000 arquivos dela, state/ e outros
    projetos inclusive): a pasta atual nunca é percorrida."""
    texto = os.fspath(pasta) if isinstance(pasta, (str, os.PathLike)) else ""
    if not texto or not os.path.isabs(texto):
        raise EntradaInvalida(f"a árvore precisa de um caminho absoluto (recebido {str(texto)[:80]!r}): a pasta atual "
                              "não é percorrida")
    copia = _carregar_script("copia_segura")
    base = Path(os.path.abspath(texto))
    try:
        st = os.lstat(base)
    except OSError as exc:
        raise EntradaInvalida(f"pasta ausente: {base} ({exc.strerror or exc})") from None
    if copia.e_ligacao(st) or not stat.S_ISDIR(st.st_mode):
        raise EntradaInvalida(f"{base} é ligação ou não é pasta")
    saida, pilha = {}, [base]
    while pilha:
        atual = pilha.pop()
        for nome in sorted(os.listdir(atual)):
            caminho = atual / nome
            rel = caminho.relative_to(base).as_posix()
            st = os.lstat(caminho)
            if copia.e_ligacao(st):
                raise EntradaInvalida(f"ligação dentro de {base.name}: {rel}")
            if stat.S_ISDIR(st.st_mode):
                if nome not in pastas_ignoradas:
                    pilha.append(caminho)
                continue
            if not stat.S_ISREG(st.st_mode):
                raise EntradaInvalida(f"tipo especial dentro de {base.name}: {rel}")
            if caminho.suffix in sufixos_ignorados:
                continue
            try:
                saida[rel] = copia.hash_conferido(caminho, dentro_de=base)
            except OSError as exc:
                raise EntradaInvalida(f"{rel}: {exc}") from None
            if len(saida) > teto:
                raise EntradaInvalida(f"{base.name}: mais de {teto} arquivos")
    return saida


def sha256_manifesto(manifesto: dict) -> str:
    """SHA-256 das linhas `<caminho relativo POSIX>\\t<bytes>\\t<sha256>\\n`, em ordem de caminho: a conta interna do
    HOST para a cópia da skill e para a cópia de cada plugin na área (o preparo grava, o lançador confere). O kit_sha256
    do porteiro.json usa a conta do porteiro (`kit_sha256`)."""
    texto = "".join(f"{rel}\t{m['bytes']}\t{m['sha256']}\n" for rel, m in sorted(manifesto.items()))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def sha256_arvore(pasta, **kw) -> str:
    return sha256_manifesto(manifesto_de_arvore(pasta, **kw))


def sha256_do_plugin(manifesto: dict, skill=SKILL) -> str:
    """O `plugins[].manifesto_sha256` da ficha sobre o manifesto {rel: {"sha256", "bytes"}} do HOST: a receita única do
    kit, `aberturas_plugins.sha256_do_manifesto` (o JSON compacto, com as chaves ordenadas, da lista {caminho, bytes,
    sha256} em ordem de caminho; emenda E3 dos contratos; folha da integração, I5), no lugar das linhas do HOST. A mesma
    conta no kit (`abertura preparar|verificar`, ferramenta do titular), no scripts/plugin_candidato.py e aqui; o teste
    de igualdade prende as pontas (test_host_projeto_plugins_kit.py). A cópia na área e o lançador seguem com a conta
    interna (`sha256_manifesto`), que não muda."""
    lista = [{"caminho": rel, "bytes": m["bytes"], "sha256": m["sha256"]} for rel, m in sorted(manifesto.items())]
    return modulos_do_kit(skill).plugins.sha256_do_manifesto(lista)


def funcao_do_kit(skill=SKILL):
    """`sha256_do_kit` (e a `Recusa`) do porteiro da skill, `assets/host/wsl/porteiro.py` (pacote PORTEIRO): a conta
    única do porteiro.json.kit_sha256 e da árvore "kit", que o `porteiro.py conferir` do lançador e a reconferência de
    cada pedido comparam (revisão do lote 2: o preparo usava outra conta, e o lançador nunca abriria). O módulo é
    compilado dos bytes lidos sem seguir ligação (nenhum __pycache__ entra) e só define funções e constantes; sem ele,
    ou sem a função, EntradaInvalida."""
    caminho = Path(skill) / "assets" / "host" / "wsl" / "porteiro.py"
    chave = os.path.abspath(caminho)
    if chave not in _PORTEIROS:
        try:
            dados = _ler_bytes_seguro(caminho, TETO_HASHES)
        except (OSError, ValueError) as exc:
            raise EntradaInvalida(f"a skill não tem assets/host/wsl/porteiro.py legível (pacote PORTEIRO da 1.7.10): "
                                  f"{exc}") from None
        modulo = types.ModuleType("_preparo_host_porteiro")
        modulo.__file__ = chave
        sys.dont_write_bytecode = True
        try:
            exec(compile(dados, chave, "exec"), modulo.__dict__)  # noqa: S102 - o porteiro da própria skill
        except Exception as exc:  # noqa: BLE001 - porteiro que não carrega: recusa com o motivo, sem traceback
            raise EntradaInvalida(f"o porteiro da skill não carregou ({type(exc).__name__}: {exc})") from None
        funcao = getattr(modulo, "sha256_do_kit", None)
        if not callable(funcao):
            raise EntradaInvalida("o porteiro da skill não tem sha256_do_kit (a conta do kit_sha256; pacote PORTEIRO "
                                  "da 1.7.10)")
        recusa = getattr(modulo, "Recusa", None)
        _PORTEIROS[chave] = (funcao, recusa if isinstance(recusa, type) and issubclass(recusa, Exception) else None)
    return _PORTEIROS[chave]


def kit_sha256(base, skill=SKILL) -> str:
    """SHA-256 da árvore `<base>/fundacao` pela conta do porteiro (todo arquivo conta, inclusive .pyc fora de
    __pycache__, .git e .sqlite; só as pastas __pycache__ ficam de fora). Recusa do porteiro ou erro: EntradaInvalida."""
    funcao, recusa = funcao_do_kit(skill)
    erros = (OSError, ValueError, *((recusa,) if recusa else ()))
    try:
        valor = funcao(str(base))
    except erros as exc:
        raise EntradaInvalida(f"árvore do kit em {base} recusada pela conta do porteiro: {exc}") from None
    if not (isinstance(valor, str) and SHA256.match(valor)):
        raise EntradaInvalida("o sha256_do_kit do porteiro devolveu um valor fora do formato")
    return valor


def _rel_da_copia(rel) -> bool:
    """Caminho de arquivo do manifesto que a cópia conferida grava: relativo POSIX, sem parte vazia, '.', '..', barra
    invertida, NUL, tab nem quebra de linha (a conta interna, sha256_manifesto, separa os campos por tab e quebra)."""
    return (isinstance(rel, str) and bool(rel) and not rel.startswith("/") and not any(c in rel for c in "\\\0\t\n\r")
            and all(p not in ("", ".", "..") for p in rel.split("/")))


def conferir_plugin_da_ficha(proj, item: dict, skill=SKILL) -> dict:
    """Um `plugins[]` da ficha no disco pela regra única do caminho confiável: o `aberturas_plugins.conferir_plugin` do
    kit desta cópia da skill (emendas E3 e E4 dos contratos; folha da integração, I5), no lugar da réplica do HOST
    (`problema_do_markdown`, a lista positiva e o manifesto em linhas, menos estritos que o kit). A origem desce da pasta
    do projeto sem ligação; cada arquivo é lido uma vez, conferido (lista positiva, frontmatter, contexto dinâmico,
    controle e direção) e entra no manifesto com o SHA-256 dos bytes lidos. A cópia conferida (`_copiar_arvore`) volta
    a exigir o SHA-256 de cada arquivo: o que vai para a área é o que o kit conferiu. Devolve {"erros": [texto],
    "manifesto": {rel: {"sha256", "bytes"}}, "manifesto_sha256"}; com erro, manifesto vazio e None."""
    res = _objeto(modulos_do_kit(skill).plugins.conferir_plugin(Path(proj), dict(item)))
    erros = [f"{_objeto(e).get('campo')}: {_objeto(e).get('motivo')}" for e in _lista(res.get("erros"))]
    manifesto = {}
    for a in _lista(res.get("arquivos")):
        rel, sha, n = _objeto(a).get("caminho"), _objeto(a).get("sha256"), _objeto(a).get("bytes")
        if (not _rel_da_copia(rel) or rel in manifesto or not (isinstance(sha, str) and SHA256.match(sha))
                or not isinstance(n, int) or isinstance(n, bool) or n < 0):
            erros.append(f"manifesto do validador fora da forma em {str(rel)[:80]!r}: nada copiado")
            continue
        manifesto[rel] = {"sha256": sha, "bytes": n}
    sha = res.get("manifesto_sha256")
    if not erros and not (isinstance(sha, str) and SHA256.match(sha) and sha == sha256_do_plugin(manifesto, skill)):
        erros.append("o validador do kit não devolveu o manifesto do plugin na forma da receita única: nada copiado")
    return {"erros": erros, "manifesto": {} if erros else manifesto, "manifesto_sha256": None if erros else sha}


def versao_da_skill(skill: Path) -> str:
    m = re.search(r'^\s*version:\s*"([^"]+)"', (Path(skill) / "SKILL.md").read_text(encoding="utf-8"), re.M)
    if not m or not re.fullmatch(r"[0-9A-Za-z.+-]{1,32}", m.group(1)):
        raise EntradaInvalida("SKILL.md sem a versão no formato esperado")
    return m.group(1)


# ------------------------------------------------------------------ área do titular no Ubuntu (contratos, §6)
def carregar_vigente(skill: Path = SKILL):
    """`aberturas.vigente(raiz, projeto, area)` do kit da skill (não abre o banco, não exige identidade). Sem o módulo
    (o pacote ABERTURAS da 1.7.10 ainda não integrado) ou com outro `fundacao` já carregado neste processo: uma função
    que devolve "sem ficha" (tudo fechado). Nunca importa código da raiz da fundação, gravável pelas sessões."""
    kit = Path(skill) / "assets" / "fundacao-kit"

    def fechada(motivo):
        def vigente(raiz, projeto, area):
            return {"projeto": projeto, "valida": False, "versao": None, "arquivo": None, "sha256": None,
                    "sig_sha256": None, "ficha": None, "motivo_invalida": motivo, "area": str(area)}
        return vigente

    if not (kit / "fundacao" / "core" / "aberturas.py").is_file():
        return fechada("o kit da skill não tem fundacao/core/aberturas.py (pacote ABERTURAS): tudo fechado")
    carregado = sys.modules.get("fundacao")
    if carregado is not None and not str(getattr(carregado, "__file__", "")).startswith(str(kit)):
        return fechada("outro pacote fundacao já carregado neste processo: tudo fechado")
    sys.dont_write_bytecode = True
    if str(kit) not in sys.path:
        sys.path.insert(0, str(kit))
    return importlib.import_module("fundacao.core.aberturas").vigente


def _consultar(vigente, raiz: Path, projeto: str, area: Path) -> dict:
    try:
        resultado = vigente(raiz, projeto, area)
    except Exception as exc:  # o resultado do kit decide; erro dele fecha tudo, com o motivo
        return {"valida": False, "motivo_invalida": f"aberturas.vigente falhou: {type(exc).__name__}: {exc}"}
    return resultado if isinstance(resultado, dict) else {"valida": False, "motivo_invalida": "resultado fora da forma"}


def _maior_versao(pasta: Path) -> int:
    arquivo = pasta / "maior-versao"
    if not os.path.lexists(arquivo):
        return 0
    copia = _carregar_script("copia_segura")
    fd = copia.abrir_comum(arquivo)
    try:
        texto = os.read(fd, 64).decode("ascii", "replace").strip()
    finally:
        os.close(fd)
    if not re.fullmatch(r"[0-9]{1,6}", texto):
        raise EntradaInvalida(f"{arquivo} fora da forma: o titular confere a área antes de seguir")
    return int(texto)


def _fichas_na_pasta(pasta: Path) -> list[str]:
    return sorted(n for n in (os.listdir(pasta) if pasta.is_dir() else []) if FICHA_NOME.match(n))


def instalar_ficha(raiz: Path, projeto: str, area_proj: Path, vigente, *, simular: bool, raiz_dono: bool) -> dict:
    """Da caixa de entrada (`<raiz>/.claude/projetos/<p>/ficha/`, gravada pela ferramenta do titular) para a área root:
    confere a assinatura (`vigente` na caixa), não instala versão menor que a maior já instalada (`ficha/maior-versao`)
    e copia a ficha e o `.sig` conferindo o SHA-256. Na área fica só a ficha mais nova: vencida, ela fecha tudo, sem
    voltar a uma anterior mais aberta (crítica do desenho, §3). Uma caixa de entrada só com ficha mais velha (uma
    sessão apagou a nova dali, por exemplo) não trava o preparo: a antiga fica fora, segue a da área, com aviso
    (revisão do lote 2: a recusa impedia a regeneração exigida por um projeto novo)."""
    destino = area_proj / "ficha"
    maior = _maior_versao(destino) if destino.is_dir() else 0
    caixa = raiz / ".claude" / "projetos" / projeto / "ficha"
    if not caixa.is_dir():
        return {"acao": "sem-ficha-nova", "detalhe": "caixa de entrada sem ficha", "versao": maior or None}
    r = _consultar(vigente, raiz, projeto, caixa)
    if r.get("valida") is not True:
        return {"acao": "sem-ficha-nova", "versao": maior or None,
                "detalhe": f"caixa de entrada sem ficha válida ({r.get('motivo_invalida') or 'nenhuma'})"}
    arquivo = Path(str(r.get("arquivo") or ""))
    arquivo = arquivo if arquivo.is_absolute() else caixa / arquivo
    m = FICHA_NOME.match(arquivo.name)
    versao, sha, sig_sha = r.get("versao"), r.get("sha256"), r.get("sig_sha256")
    if (not m or int(m.group(1)) != versao or not isinstance(sha, str) or not SHA256.match(sha)
            or not isinstance(sig_sha, str) or not SHA256.match(sig_sha)
            or os.path.normcase(os.path.realpath(arquivo.parent)) != os.path.normcase(os.path.realpath(caixa))):
        raise EntradaInvalida("resultado do vigente fora da forma para a ficha da caixa de entrada: nada instalado")
    if versao < maior:
        aviso = (f"a caixa de entrada só tem a ficha v{versao}, menor que a maior já instalada (v{maior}): ela não foi "
                 f"instalada (uma ficha antiga não volta) e segue a v{maior} da área; para mudar as aberturas, assine "
                 "uma versão nova (fundacao_titular.py assinar-ficha)")
        return {"acao": "sem-ficha-nova", "versao": maior, "detalhe": aviso, "aviso": aviso}
    instalada = destino / arquivo.name
    if versao == maior:
        copia = _carregar_script("copia_segura")
        if os.path.lexists(instalada) and copia.hash_conferido(instalada)["sha256"] == sha:
            return {"acao": "igual", "versao": versao, "detalhe": f"ficha v{versao} já instalada"}
        raise EntradaInvalida(f"a ficha v{versao} da caixa de entrada difere da v{versao} instalada: assine uma versão "
                              "nova em vez de trocar uma assinada")
    if simular:
        return {"acao": "instalar", "versao": versao, "detalhe": f"ficha v{versao} seria instalada na área do titular"}
    copia = _carregar_script("copia_segura")
    _pasta_area(destino, raiz_dono)
    for origem, esperado, nome in ((arquivo, sha, arquivo.name), (arquivo.with_name(arquivo.name + ".sig"), sig_sha,
                                                                  arquivo.name + ".sig")):
        temp = destino / f".{nome}.{secrets.token_hex(6)}.tmp"
        copia.copiar_conferindo(origem, temp, sha256_esperado=esperado, modo=0o644, dentro_de=caixa)
        _dono(temp, raiz_dono)
        os.replace(temp, destino / nome)
    _publicar(destino / "maior-versao", f"{versao}\n".encode("ascii"), 0o644, raiz_dono)
    for antiga in _fichas_na_pasta(destino):
        if antiga != arquivo.name:
            for nome in (antiga, antiga + ".sig"):
                if os.path.lexists(destino / nome):
                    os.unlink(destino / nome)
    return {"acao": "instalar", "versao": versao, "detalhe": f"ficha v{versao} instalada na área do titular"}


def _dono(caminho: Path, raiz_dono: bool) -> None:
    if raiz_dono:
        os.chown(caminho, 0, 0, follow_symlinks=False)


def _pasta_area(pasta: Path, raiz_dono: bool) -> Path:
    """Cria a pasta (e as de cima que faltarem) conferindo, sem seguir, cada componente desde a raiz do sistema:
    nenhum é ligação; as novas com 0755 e, como root, dono root."""
    pasta = Path(os.path.abspath(pasta))
    copia = _carregar_script("copia_segura")
    atual = Path(pasta.parts[0])
    for parte in pasta.parts[1:]:
        atual = atual / parte
        try:
            st = os.lstat(atual)
        except FileNotFoundError:
            os.mkdir(atual, 0o755)
            if os.name != "nt":
                os.chmod(atual, 0o755)
            _dono(atual, raiz_dono)
            st = os.lstat(atual)
        if copia.e_ligacao(st) or not stat.S_ISDIR(st.st_mode):
            raise EntradaInvalida(f"{atual} é ligação ou não é pasta: nada gravado ali")
    return pasta


def _publicar(destino: Path, dados: bytes, modo: int, raiz_dono: bool) -> None:
    _carregar_script("gravacao_segura").publicar(destino, dados)
    if os.name != "nt":
        os.chmod(destino, modo)
    _dono(destino, raiz_dono)


def _copiar_arvore(origem: Path, manifesto: dict, destino: Path, raiz_dono: bool, modo: int = 0o644) -> None:
    """Copia a árvore conferida para `destino` (que não pode existir): cada arquivo pela cópia única conferida
    (`copiar_conferindo`, SHA-256 do manifesto), numa pasta temporária ao lado, trocada de nome no fim."""
    copia = _carregar_script("copia_segura")
    if os.path.lexists(destino):
        raise EntradaInvalida(f"{destino} já existe")
    temp = destino.parent / f".novo-{destino.name}-{secrets.token_hex(6)}"
    _pasta_area(temp, raiz_dono)
    try:
        for rel, m in sorted(manifesto.items()):
            alvo = temp.joinpath(*rel.split("/"))
            _pasta_area(alvo.parent, raiz_dono)
            copia.copiar_conferindo(origem.joinpath(*rel.split("/")), alvo, sha256_esperado=m["sha256"], modo=modo,
                                    dentro_de=origem)
            _dono(alvo, raiz_dono)
        os.rename(temp, destino)
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise


# ------------------------------------------------------------------ cópia protegida da ferramenta do titular (I11)
# O Python fixado que o hashes.json da cópia do Windows registra, na forma que o kit aceita
# (core/aberturas_comando._PYTHON_WINDOWS; igual por teste).
PYTHON_WINDOWS = re.compile(r"[A-Za-z]:\\(?:[^\\/:*?\"<>|`$'\r\n;&]+\\)*python\.exe", re.I)


def versao_do_kit(skill=SKILL) -> str:
    """O KIT_VERSION do kit da skill, lido do texto de fundacao/__init__.py (sem importar): a cópia protegida fica em
    `<base>/<KIT_VERSION>`, a pasta que core/aberturas_comando.comando_do_titular mostra."""
    arquivo = Path(skill) / "assets" / "fundacao-kit" / "fundacao" / "__init__.py"
    try:
        texto = _ler_bytes_seguro(arquivo, 64 * 1024).decode("utf-8")
    except (OSError, ValueError) as exc:
        raise EntradaInvalida(f"o kit da skill sem fundacao/__init__.py legível ({exc})") from None
    m = VERSAO_DO_KIT.search(texto)
    if not m:
        raise EntradaInvalida("o kit da skill sem KIT_VERSION na forma x.y.z")
    return m.group(1)


def plano_da_ferramenta(skill=SKILL, base: str | None = FERRAMENTA_BASE, python: dict | None = None) -> dict:
    """A cópia protegida da ferramenta do titular (folha da integração, I11): `<base>/<KIT_VERSION>/` com
    `assets/host/fundacao_titular.py`, `assets/fundacao-kit/fundacao/**` (sem __pycache__, .pytest_cache, .git, *.pyc e
    *.sqlite, como a cópia da skill) e o `hashes.json` do esquema `fundacao.ferramenta_titular/1`, que a ferramenta
    confere antes de importar o kit (fundacao_titular.conferir_copia: exatamente esses arquivos, nenhum a mais). Tudo
    lido sem seguir ligação. `python` ({"caminho", "sha256"}) só na do Windows: o Python fixado, que o
    preparar-maquina.ps1 só registra se for instalado para todos os usuários. Devolve {"base", "versao", "destino",
    "origem", "manifesto", "hashes", "hashes_bytes", "sha256"}; nada é gravado."""
    skill = Path(os.path.realpath(skill))
    versao = versao_do_kit(skill)
    copia = _carregar_script("copia_segura")
    try:
        manifesto = {REL_FERRAMENTA: copia.hash_conferido(skill.joinpath(*REL_FERRAMENTA.split("/")), dentro_de=skill)}
    except OSError as exc:
        raise EntradaInvalida(f"a skill sem a ferramenta do titular legível sem ligação ({REL_FERRAMENTA}: "
                              f"{exc})") from None
    kit = manifesto_de_arvore(skill.joinpath(*REL_KIT_DA_FERRAMENTA.split("/")))
    manifesto.update({f"{REL_KIT_DA_FERRAMENTA}/{rel}": m for rel, m in kit.items()})
    hashes = {"schema_version": ESQUEMA_FERRAMENTA, "versao": versao,
              "arquivos": {rel: m["sha256"] for rel, m in sorted(manifesto.items())}}
    if python is not None:
        caminho, sha = _objeto(python).get("caminho"), _objeto(python).get("sha256")
        if not (isinstance(caminho, str) and PYTHON_WINDOWS.fullmatch(caminho) and isinstance(sha, str)
                and SHA256.match(sha)):
            raise EntradaInvalida(f"Python da cópia do Windows fora da forma que o kit aceita: {str(caminho)[:120]!r}")
        hashes["python"] = {"caminho": caminho, "sha256": sha}
    dados = texto_json(hashes).encode("utf-8")
    return {"base": base, "versao": versao, "destino": None if base is None else (Path(base) / versao),
            "origem": skill, "manifesto": manifesto, "hashes": hashes, "hashes_bytes": dados,
            "sha256": hashlib.sha256(dados).hexdigest()}


def conferir_ferramenta_instalada(plano: dict, raiz_dono: bool = False) -> list[str]:
    """O que a cópia protegida instalada tem de diferente do plano: a árvore inteira (os arquivos do manifesto e o
    hashes.json, nenhum a mais, nenhuma ligação), os modos (arquivos 0644, pastas 0755) e, com `raiz_dono`, o dono root
    de cada um e da pasta base (a ferramenta recusa o que esta conta altera). Lista vazia: igual."""
    destino = Path(plano["destino"])
    esperado = {**plano["manifesto"], "hashes.json": {"sha256": plano["sha256"], "bytes": len(plano["hashes_bytes"])}}
    try:
        atual = manifesto_de_arvore(destino, pastas_ignoradas=(), sufixos_ignorados=())
    except EntradaInvalida as exc:
        return [f"cópia não conferida ({exc})"]
    diferentes = sorted((set(atual) ^ set(esperado))
                        | {r for r in set(atual) & set(esperado) if atual[r] != esperado[r]})
    problemas = ([f"a cópia difere do plano em {len(diferentes)} arquivo(s): " + ", ".join(diferentes[:4])]
                 if diferentes else [])
    if os.name != "nt":
        caminhos = [(destino.parent, True), (destino, True)]
        for atual_dir, pastas, arquivos in os.walk(destino):
            caminhos += [(Path(atual_dir) / p, True) for p in pastas] + [(Path(atual_dir) / a, False) for a in arquivos]
        for caminho, e_pasta in caminhos:
            st = os.lstat(caminho)
            modo = stat.S_IMODE(st.st_mode)
            if modo != (0o755 if e_pasta else 0o644) or (raiz_dono and st.st_uid != 0):
                problemas.append(f"{caminho.as_posix()} com modo {oct(modo)} ou dono {st.st_uid} fora do esperado "
                                 f"({'0o755' if e_pasta else '0o644'}" + (", root)" if raiz_dono else ")"))
                break
    return problemas


def _instalar_ferramenta(plano: dict, raiz_dono: bool) -> dict:
    """Grava a cópia protegida do plano (folha da integração, I11): igual, nada muda; senão, a árvore inteira numa
    pasta nova ao lado (cada arquivo pela cópia conferida, com o SHA-256 do plano, sem seguir ligação), o hashes.json e
    a troca de nome; a anterior, se havia, sai depois da troca. Pastas 0755 e arquivos 0644, de dono root (no ensaio,
    do usuário); a pasta base também (é da fundação). Conferida de novo no fim: diferença = EntradaInvalida."""
    destino = Path(plano["destino"])
    item = {"item": "ferramenta-titular", "caminho": destino.as_posix()}
    base = _pasta_area(destino.parent, raiz_dono)
    if os.name != "nt":
        os.chmod(base, 0o755)
        _dono(base, raiz_dono)
    if os.path.lexists(destino) and not conferir_ferramenta_instalada(plano, raiz_dono):
        return {**item, "acao": "igual"}
    acao = "atualizar" if os.path.lexists(destino) else "criar"
    novo = destino.with_name(f".novo-{destino.name}-{secrets.token_hex(6)}")
    try:
        _copiar_arvore(plano["origem"], plano["manifesto"], novo, raiz_dono)
        _publicar(novo / "hashes.json", plano["hashes_bytes"], 0o644, raiz_dono)
        if acao == "atualizar":
            antigo = destino.with_name(f".antigo-{destino.name}-{secrets.token_hex(6)}")
            os.rename(destino, antigo)
            os.rename(novo, destino)
            if os.path.islink(antigo) or not os.path.isdir(antigo):
                os.unlink(antigo)
            else:
                shutil.rmtree(antigo, ignore_errors=True)
        else:
            os.rename(novo, destino)
    except BaseException:
        shutil.rmtree(novo, ignore_errors=True)
        raise
    problemas = conferir_ferramenta_instalada(plano, raiz_dono)
    if problemas:
        raise EntradaInvalida("a cópia protegida da ferramenta do titular não conferiu depois de gravada: "
                              + "; ".join(problemas[:3]))
    return {**item, "acao": acao}


def detectar_seccomp(bases=SECCOMP_BASES, dono: int = 0) -> dict:
    """O filtro seccomp do sandbox (`sudo npm install -g --ignore-scripts @anthropic-ai/sandbox-runtime@<versão>`,
    documentação conferida em 31/10/2026): sem ele, "sockets are unrestricted". Só caminhos fixos, sem rodar o npm
    (como root, na pasta e com o ambiente do titular, a configuração dele decidiria onde procurar e daria um
    "instalado" falso: revisão do lote 2): o pacote conta só com o package.json e os arquivos do filtro
    (`vendor/seccomp`) de dono `dono` (root), sem ligação e sem escrita para o grupo e os outros. Não instala nada; a
    prova de que o filtro age é o canário (socket AF_UNIX recusado; a lista de arquivos é confirmada nele)."""
    copia = _carregar_script("copia_segura")
    motivos = []
    for base in bases:
        pacote = Path(base) / "@anthropic-ai" / "sandbox-runtime"
        if not os.path.lexists(pacote):
            continue
        filtro = pacote / "vendor" / "seccomp"
        try:
            arquivos = manifesto_de_arvore(filtro, pastas_ignoradas=(), sufixos_ignorados=())
            if not arquivos:
                raise EntradaInvalida("vendor/seccomp sem arquivos")
            for caminho in (pacote, pacote / "package.json", pacote / "vendor", filtro,
                            *(filtro.joinpath(*rel.split("/")) for rel in arquivos)):
                st = os.lstat(caminho)
                if copia.e_ligacao(st) or (os.name != "nt" and (st.st_uid != dono or st.st_mode & 0o022)):
                    raise EntradaInvalida(f"{caminho.name} é ligação, de outra conta ou gravável por outros")
            dados = _ler_json_seguro(pacote / "package.json", TETO_JSON)
            sha = copia.hash_conferido(pacote / "package.json")["sha256"]
        except (OSError, ValueError) as exc:
            motivos.append(f"{pacote.as_posix()} não conta ({exc})")
            continue
        return {"instalado": True, "caminho": (pacote / "package.json").as_posix(), "sha256": sha,
                "versao": str(_objeto(dados).get("version")), "filtro": filtro.as_posix(),
                "filtro_sha256": sha256_manifesto(arquivos)}
    ausente = "@anthropic-ai/sandbox-runtime não instalado em " + " nem em ".join(map(str, bases))
    return {"instalado": False, "motivo": ("; ".join(motivos) or ausente) + ": sockets sem filtro"}


def planejar_instalacao(*, raiz, projeto: str, titular: str, claude, claude_versao: str, claude_sha256: str,
                        origem_hash: str, perfil_windows: str, casa: str, usuario: str, area_raiz=AREA_RAIZ,
                        bin_dir=BIN_DIR, vigente=None, ancora_base: str = ANCORA_BASE_WSL, montagem: str = MONTAGEM,
                        temp_base: str = TEMP_BASE, sonda_interop_cmd: str = SONDA_INTEROP_CMD,
                        sonda_interop_binfmt: str = SONDA_INTEROP_BINFMT, skill=SKILL, seccomp=None, hoje=None,
                        aberturas: dict | None = None, gerenciadas: str = GERENCIADAS,
                        fs_raiz: str | None = None, ferramenta_base: str | None = FERRAMENTA_BASE) -> dict:
    """Tudo o que `instalar_projeto` grava, calculado sem gravar nada (também a simulação). Problema = EntradaInvalida.
    A ficha só é aplicada com o canário aprovado (`portao_do_canario`); `fs_raiz` substitui a medida do /proc/mounts
    só nos testes de unidade (a linha de comando sempre mede). Com `ferramenta_base` (sem ela, só no ensaio), a cópia
    protegida da ferramenta do titular entra no plano (folha da integração, I11)."""
    raiz = Path(os.path.abspath(raiz))
    projeto_valido(projeto)
    identificador(titular, "titular")
    if not USUARIO_LINUX.match(str(usuario)):
        raise EntradaInvalida(f"usuário do Linux inválido: {usuario!r}")
    raiz_wsl = raiz.as_posix()
    proj = raiz / "projects" / projeto
    gravacao = _carregar_script("gravacao_segura")
    if gravacao.com_ligacao(raiz, f"projects/{projeto}") or not proj.is_dir():
        raise EntradaInvalida(f"o projeto {projeto} não existe em {raiz / 'projects'} (ou passa por ligação)")
    skill = Path(os.path.realpath(skill))
    problemas = []
    hooks = {}
    for nome in HOOKS_WSL:
        da_raiz, da_skill = raiz / ".claude" / "hooks" / nome, skill / "assets" / "hooks" / nome
        try:
            atual = _carregar_script("copia_segura").hash_conferido(da_raiz)["sha256"]
            esperado = hashlib.sha256(da_skill.read_bytes()).hexdigest()
        except OSError as exc:
            problemas.append(f"hook {nome} ausente na raiz ou na skill ({exc.strerror or exc}): rode o "
                             "preparar-maquina.ps1 no Windows")
            continue
        if atual != esperado:
            problemas.append(f"o hook {nome} da raiz difere do da skill: rode de novo o preparar-maquina.ps1 no Windows")
        hooks[str(da_raiz.as_posix())] = atual
    kit_sha = None
    try:  # a conta do porteiro (a mais estrita: só __pycache__ fica de fora), na raiz e na skill
        kit_sha = kit_sha256(raiz, skill)
        if kit_sha != kit_sha256(skill / "assets" / "fundacao-kit", skill):
            problemas.append("o kit da raiz (fundacao/) difere do kit da skill: rode antes a atualização da fundação "
                             "(atualizar_fundacao.py), para o porteiro não rodar um kit sem a trava de projeto")
    except EntradaInvalida as exc:
        problemas.append(f"kit da raiz ou da skill não conferido: {exc}")
    if not SHA256.match(str(claude_sha256)) or not VERSAO_CLAUDE.match(str(claude_versao)):
        raise EntradaInvalida("versão ou SHA-256 do Claude Code fora do formato")
    try:
        sha_claude = _carregar_script("copia_segura").hash_conferido(claude)["sha256"]
    except OSError as exc:
        raise EntradaInvalida(f"Claude Code fixado ausente ou recusado ({exc})") from None
    if sha_claude != claude_sha256:
        raise EntradaInvalida(f"o SHA-256 do Claude Code ({sha_claude}) não confere com o informado ({claude_sha256})")
    if problemas:
        raise EntradaInvalida("; ".join(problemas))
    registro = vagas_do_registro(ler_projetos_host(raiz), projeto, montagem)
    area_raiz = Path(area_raiz)
    area = area_raiz / "projetos" / projeto
    canario = portao_do_canario(area_raiz, claude_versao=claude_versao, claude_sha256=claude_sha256,
                                raiz_wsl=raiz_wsl, fs_raiz=fs_raiz)
    if aberturas is None:
        aberturas = aberturas_da_ficha(_consultar(vigente or carregar_vigente(skill), raiz, projeto, area / "ficha"),
                                       projeto, hoje, skill)
    aberturas = com_canario(aberturas, canario)  # contratos, §0: sem o canário aprovado, a ficha não é aplicada
    plugins = []
    for p in aberturas["plugins"]:
        if gravacao.com_ligacao(proj, p["origem"]):  # segunda camada (interface do PLUGINS): o kit também recusa
            raise EntradaInvalida(f"plugin {p['nome']}: a origem passa por ligação")
        res = conferir_plugin_da_ficha(proj, p, skill)  # a regra e a receita do kit (folha da integração, I5)
        if res["erros"]:
            raise EntradaInvalida(f"plugin {p['nome']}: " + "; ".join(res["erros"][:3]))
        if res["manifesto_sha256"] != p["manifesto_sha256"]:
            raise EntradaInvalida(f"plugin {p['nome']}: o manifesto da origem difere do manifesto_sha256 da ficha")
        manifesto = res["manifesto"]
        plugins.append({**p, "origem_abs": proj.joinpath(*p["origem"].split("/")), "manifesto": manifesto,
                        "arvore_sha256": sha256_manifesto(manifesto)})
    outros = [o for o in projetos_da_raiz(raiz) if o != projeto]
    perfil = perfil_wsl(raiz=raiz_wsl, projeto=projeto, perfil_windows=perfil_windows, outros_projetos=outros,
                        somente_leitura=registro["somente_leitura"], ancora_base=ancora_base, montagem=montagem,
                        negar=registro["negar"], aberturas=aberturas, temp_base=temp_base)
    manifesto_skill = manifesto_de_arvore(skill)
    sha_skill = sha256_manifesto(manifesto_skill)
    versao = versao_da_skill(skill)
    skill_copia = area_raiz / "skill" / f"{versao}-{sha_skill[:12]}"
    claude_copia = area_raiz / "claude" / claude_versao / "claude"
    arquivos = {"settings.wsl.json": texto_json(perfil).encode("utf-8"),
                "porteiro.json": texto_json({"schema_version": ESQUEMA_PORTEIRO, "raiz": raiz_wsl, "projeto": projeto,
                                             "kit_sha256": kit_sha, "assinante": titular,
                                             "operacoes": {"fundacao": {}}}).encode("utf-8"),
                "mcp.json": texto_json({"mcpServers": {}}).encode("utf-8"),
                "aberturas.json": texto_json({"schema_version": ESQUEMA_ABERTURAS, "projeto": projeto,
                                              **{k: v for k, v in aberturas.items() if k != "plugins"},
                                              "plugins": [{"nome": p["nome"], "manifesto_sha256": p["manifesto_sha256"]}
                                                          for p in plugins],
                                              "ferramentas": ferramentas_do_projeto(aberturas)}).encode("utf-8")}
    ferramentas = ",".join(ferramentas_do_projeto(aberturas))
    preparo_rel, porteiro_rel = "assets/host/preparo_host.py", "assets/host/wsl/porteiro.py"
    valores = {"RAIZ": raiz_wsl, "PROJETO": projeto, "USUARIO": usuario, "AREA": area.as_posix(),
               "SKILL": skill_copia.as_posix(), "CLAUDE_BIN": claude_copia.as_posix(), "CLAUDE_VERSAO": claude_versao,
               "CLAUDE_SHA256": claude_sha256, "CLAUDE_ORIGEM_HASH": origem_hash, "FERRAMENTAS": ferramentas,
               "PLUGINS": " ".join(p["nome"] for p in plugins),
               "PREPARO_SHA256": manifesto_skill[preparo_rel]["sha256"],
               "PORTEIRO_SHA256": manifesto_skill.get(porteiro_rel, {}).get("sha256", "0" * 64),
               "TEMP_PROJETO": temp_do_projeto(temp_base, projeto), "SONDA_INTEROP_CMD": sonda_interop_cmd,
               "SONDA_INTEROP_BINFMT": sonda_interop_binfmt}
    texto_lancador = lancador(valores)
    ficha = None
    if aberturas["valida"]:
        nome = aberturas["arquivo"]
        ficha = {"arquivo": nome, "versao": aberturas["versao"], "sha256": aberturas["sha256"],
                 "sig_sha256": aberturas["sig_sha256"], "vigencia_ate": aberturas["vigencia_ate"]}
    rastreados = {**{(area / n).as_posix(): hashlib.sha256(b).hexdigest() for n, b in arquivos.items()}, **hooks,
                  claude_copia.as_posix(): claude_sha256}
    if ficha:
        rastreados[(area / "ficha" / ficha["arquivo"]).as_posix()] = ficha["sha256"]
        rastreados[(area / "ficha" / (ficha["arquivo"] + ".sig")).as_posix()] = ficha["sig_sha256"]
    if canario["aprovado"]:  # o relatório que liberou a ficha fica fixado: trocado, o lançador não abre
        rastreados[canario["arquivo"]] = canario["sha256"]
    arvores = {"skill": {"caminho": skill_copia.as_posix(), "sha256": sha_skill},
               "kit": {"caminho": (raiz / "fundacao").as_posix(), "sha256": kit_sha, "conta": "porteiro.sha256_do_kit"},
               **{f"plugin:{p['nome']}": {"caminho": (area / "plugins" / p["nome"]).as_posix(),
                                          "sha256": p["arvore_sha256"], "manifesto_sha256": p["manifesto_sha256"]}
                  for p in plugins}}
    marcadores = _sem_repetir([*MARCADORES_OBRIGATORIOS, *MARCADORES_RECUSADOS, *_literais_do_perfil(perfil)])
    if os.path.lexists(gerenciadas):  # managed settings presentes: fixados e mostrados no relatório para o titular
        arvores["claude-code-gerenciado"] = {"caminho": Path(gerenciadas).as_posix(), "sha256": sha256_arvore(
            gerenciadas, pastas_ignoradas=(), sufixos_ignorados=())}
    sec = (seccomp or detectar_seccomp)()
    ferramenta = None
    if ferramenta_base is not None:  # a cópia protegida da ferramenta do titular (I11): uma por versão do kit
        ferramenta = plano_da_ferramenta(skill, ferramenta_base)
        ferramenta["estado"] = ("criar" if not os.path.lexists(ferramenta["destino"]) else
                                "igual" if not conferir_ferramenta_instalada(ferramenta, _e_root()) else "atualizar")
    hashes = {"schema_version": ESQUEMA_HASHES, "projeto": projeto, "raiz": raiz_wsl, "usuario": usuario, "casa": casa,
              "parametros": {"perfil_windows": caminho_wsl(perfil_windows, montagem),
                             "ancora_base": caminho_wsl(ancora_base, montagem), "temp_base": temp_base,
                             "montagem": montagem},
              "ferramentas": ferramentas, "arquivos": rastreados, "arvores": arvores, "ficha": ficha,
              "marcadores": marcadores, "seccomp": sec, "gerenciadas": Path(gerenciadas).as_posix(),
              "canario": canario,
              "claude": {"versao": claude_versao, "sha256": claude_sha256, "origem_hash": origem_hash},
              "lancador": {"caminho": (Path(bin_dir) / f"abrir-fundacao-{projeto}").as_posix(),
                           "sha256": hashlib.sha256(texto_lancador.encode("utf-8")).hexdigest()}}
    return {"raiz": raiz, "raiz_wsl": raiz_wsl, "projeto": projeto, "area_raiz": area_raiz, "area": area,
            "bin": Path(bin_dir), "aberturas": aberturas, "plugins": plugins, "perfil": perfil, "arquivos": arquivos,
            "hashes": hashes, "lancador": texto_lancador, "skill": skill, "manifesto_skill": manifesto_skill,
            "skill_copia": skill_copia, "claude": Path(claude), "claude_copia": claude_copia,
            "claude_sha256": claude_sha256, "seccomp": sec, "canario": canario, "ferramenta": ferramenta}


def _literais_do_perfil(perfil) -> list[str]:
    """Nomes literais (sem curinga) que o perfil nega na pasta de trabalho: o sandbox cria um ponto de montagem de 0
    byte para cada um que não existe, e ele fica no disco se o comando morrer sem saída normal (sandbox-runtime)."""
    env = _objeto(_objeto(perfil).get("env"))
    proj = str(env.get("FUNDACAO_RAIZ", "")) + "/projects/" + str(env.get(CHAVE_PROJETO, ""))
    nomes = []
    for regra in _lista(_objeto(_objeto(perfil).get("permissions")).get("deny")):
        if isinstance(regra, str) and regra.startswith("Read(./") and regra.endswith(")"):
            corpo = regra[len("Read(./"):-1]
            if "/" not in corpo and not any(c in corpo for c in "*?["):
                nomes.append(corpo)
    for c in _lista(_objeto(_objeto(_objeto(perfil).get("sandbox")).get("filesystem")).get("denyWrite")):
        if isinstance(c, str) and c.startswith(proj + "/") and "/" not in c[len(proj) + 1:]:
            nomes.append(c[len(proj) + 1:])
    return nomes


def instalar_projeto(*, simular: bool = False, ensaio: bool = False, **kw) -> dict:
    """Grava a área do titular do projeto (contratos do lote 2, §6): `/etc/fundacao-ia/projetos/<p>/` (perfil,
    porteiro.json, mcp.json, aberturas.json, ficha/, plugins/, hashes.json), as cópias conferidas da skill e do Claude
    Code e o lançador `/usr/local/bin/abrir-fundacao-<p>`, tudo de dono root; e o espelho legível em
    `<raiz>/.claude/projetos/<p>/` (não autoritativo). Sem root, só em `ensaio` (área e lançador em pastas dadas)."""
    if os.name == "nt":
        raise EntradaInvalida("a área do titular é do Ubuntu (WSL2): rode o preparo no terminal do Ubuntu")
    raiz_dono = _e_root()
    if not simular and not raiz_dono and not ensaio:
        raise EntradaInvalida("a área do titular é de dono root: rode com sudo (no terminal do Ubuntu, o "
                              "preparar-wsl.sh faz isso e mostra o comando)")
    vigente = kw.pop("vigente", None) or carregar_vigente(kw.get("skill", SKILL))
    raiz = Path(os.path.abspath(kw["raiz"]))
    projeto_valido(kw["projeto"])
    area = Path(kw.get("area_raiz", AREA_RAIZ)) / "projetos" / kw["projeto"]
    # 1. Tudo conferido antes de gravar: a ficha que viria da caixa de entrada (a versão menor não volta), e o plano
    # inteiro com ela e com o portão do canário (hooks, kit, Claude Code, plugins, perfil e lançador).
    ficha = instalar_ficha(raiz, kw["projeto"], area, vigente, simular=True, raiz_dono=raiz_dono)
    previa = None
    if ficha["acao"] == "instalar":
        caixa = raiz / ".claude" / "projetos" / kw["projeto"] / "ficha"
        previa = aberturas_da_ficha(_consultar(vigente, raiz, kw["projeto"], caixa), kw["projeto"], kw.get("hoje"),
                                    kw.get("skill", SKILL))
    plano = planejar_instalacao(vigente=vigente, aberturas=previa, **kw)
    if simular:
        return _relatorio(plano, ficha, simular=True)
    # 2. A ficha vai para a área root, e o plano é refeito a partir dela (a área é a fonte que vale).
    ficha = instalar_ficha(raiz, kw["projeto"], area, vigente, simular=False, raiz_dono=raiz_dono)
    plano = planejar_instalacao(vigente=vigente, **kw)
    acoes = _gravar_plano(plano, raiz_dono)
    return _relatorio(plano, ficha, simular=False, acoes=acoes)


def _gravar_plano(plano: dict, raiz_dono: bool) -> list[dict]:
    acoes = []
    area, area_raiz = plano["area"], plano["area_raiz"]
    for pasta in (area_raiz, area, area / "ficha", area / "plugins", area_raiz / "skill",
                  plano["claude_copia"].parent, plano["bin"]):
        _pasta_area(pasta, raiz_dono)
    copia = _carregar_script("copia_segura")
    if os.path.lexists(plano["skill_copia"]):
        if sha256_arvore(plano["skill_copia"]) != plano["hashes"]["arvores"]["skill"]["sha256"]:
            raise EntradaInvalida(f"a cópia da skill em {plano['skill_copia']} difere do manifesto: o titular confere")
        acoes.append({"item": "skill", "caminho": plano["skill_copia"].as_posix(), "acao": "igual"})
    else:
        _copiar_arvore(plano["skill"], plano["manifesto_skill"], plano["skill_copia"], raiz_dono)
        acoes.append({"item": "skill", "caminho": plano["skill_copia"].as_posix(), "acao": "criar"})
    destino = plano["claude_copia"]
    if os.path.lexists(destino):
        if copia.hash_conferido(destino)["sha256"] != plano["claude_sha256"]:
            raise EntradaInvalida(f"a cópia do Claude Code em {destino} difere do SHA-256 fixado: o titular confere")
        acoes.append({"item": "claude", "caminho": destino.as_posix(), "acao": "igual"})
    else:
        copia.copiar_conferindo(plano["claude"], destino, sha256_esperado=plano["claude_sha256"], modo=0o755)
        _dono(destino, raiz_dono)
        acoes.append({"item": "claude", "caminho": destino.as_posix(), "acao": "criar"})
    if plano.get("ferramenta"):  # a cópia protegida da ferramenta do titular (folha da integração, I11)
        acoes.append(_instalar_ferramenta(plano["ferramenta"], raiz_dono))
    plugins_dir = area / "plugins"
    desejados = {p["nome"] for p in plano["plugins"]}
    for nome in sorted(os.listdir(plugins_dir)):
        caminho = plugins_dir / nome
        if nome not in desejados:
            shutil.rmtree(caminho) if caminho.is_dir() and not caminho.is_symlink() else os.unlink(caminho)
            acoes.append({"item": f"plugin:{nome}", "caminho": caminho.as_posix(), "acao": "remover"})
    for p in plano["plugins"]:
        destino = plugins_dir / p["nome"]
        if os.path.lexists(destino):
            if sha256_arvore(destino, pastas_ignoradas=(), sufixos_ignorados=()) == p["arvore_sha256"]:
                acoes.append({"item": f"plugin:{p['nome']}", "caminho": destino.as_posix(), "acao": "igual"})
                continue
            shutil.rmtree(destino)
        _copiar_arvore(p["origem_abs"], p["manifesto"], destino, raiz_dono)
        acoes.append({"item": f"plugin:{p['nome']}", "caminho": destino.as_posix(), "acao": "criar"})
    for nome, dados in [*plano["arquivos"].items(), ("hashes.json", texto_json(plano["hashes"]).encode("utf-8"))]:
        acoes.append(_gravar_se_mudou(area / nome, dados, 0o644, raiz_dono, nome))
    acoes.append(_gravar_se_mudou(plano["bin"] / f"abrir-fundacao-{plano['projeto']}",
                                  plano["lancador"].encode("utf-8"), 0o755, raiz_dono, "lancador"))
    try:  # espelho legível na raiz (não autoritativo): falha vira aviso, não desfaz a área
        rel = f".claude/projetos/{plano['projeto']}"
        espelho = _carregar_script("gravacao_segura").pasta_sem_ligacao(plano["raiz"], rel)
        for nome, dados in [*plano["arquivos"].items(), ("hashes.json", texto_json(plano["hashes"]).encode("utf-8"))]:
            acoes.append(_gravar_se_mudou(espelho / nome, dados, 0o644, False, f"espelho:{nome}"))
    except OSError as exc:
        acoes.append({"item": "espelho", "caminho": rel, "acao": "aviso", "detalhe": str(exc)})
    return acoes


def _gravar_se_mudou(destino: Path, dados: bytes, modo: int, raiz_dono: bool, item: str) -> dict:
    copia = _carregar_script("copia_segura")
    sha = hashlib.sha256(dados).hexdigest()
    if os.path.lexists(destino):
        try:
            if copia.hash_conferido(destino)["sha256"] == sha:
                if os.name != "nt" and stat.S_IMODE(os.lstat(destino).st_mode) != modo:
                    os.chmod(destino, modo)
                return {"item": item, "caminho": destino.as_posix(), "acao": "igual", "sha256": sha}
        except OSError:
            pass
        acao = "atualizar"
    else:
        acao = "criar"
    _publicar(destino, dados, modo, raiz_dono)
    return {"item": item, "caminho": destino.as_posix(), "acao": acao, "sha256": sha}


def _relatorio(plano: dict, ficha: dict, *, simular: bool, acoes=None) -> dict:
    """O que o titular lê depois do preparo. Os avisos de honestidade (contratos, §0) saem cada um por si: a raiz em
    /mnt/<x> sempre (revisão do lote 2: com o filtro instalado o aviso sumia), os sockets sem filtro, o canário sem
    aprovação (a ficha não vale) e os managed settings fixados, com o SHA-256 para o titular conferir."""
    ab, canario = plano["aberturas"], plano["canario"]
    avisos = []
    if plano["raiz_wsl"].startswith(MONTAGEM):
        avisos.append("com a raiz em /mnt/<x> (disco do Windows), nas sondas de 31/10/2026 o sandbox não confinou os "
                      "comandos: o isolamento entre projetos é lógico até o canário passar no ambiente real")
    if not plano["seccomp"].get("instalado"):
        avisos.append("sockets sem filtro: o filtro seccomp do sandbox (@anthropic-ai/sandbox-runtime) não está "
                      "instalado num caminho fixo de dono root (" + str(plano["seccomp"].get("motivo")) + ")")
    if not canario["aprovado"]:
        avisos.append("sem canário aprovado, nenhuma abertura vale e a ficha não é aplicada: " + canario["motivo"])
    gerenciadas = plano["hashes"]["arvores"].get("claude-code-gerenciado")
    if gerenciadas:
        avisos.append(f"managed settings em {gerenciadas['caminho']} (valem acima do perfil do projeto) foram fixados "
                      f"pelo SHA-256 {gerenciadas['sha256']}: confira o conteúdo; se não foi você quem os pôs ali, "
                      "apague a pasta e rode o preparo de novo")
    if ficha.get("aviso"):
        avisos.append(ficha["aviso"])
    f = plano.get("ferramenta")
    if f:  # a cópia protegida da ferramenta do titular (I11): a forma do Ubuntu do comando do kit roda dela
        ferramenta = {"caminho": Path(f["destino"]).as_posix(), "versao": f["versao"], "estado": f.get("estado"),
                      "hashes_sha256": f["sha256"]}
    else:
        ferramenta = {"caminho": None, "estado": "fora do ensaio",
                      "motivo": "ensaio sem --ferramenta-base: a cópia protegida da ferramenta do titular não é gravada"}
    return {"projeto": plano["projeto"], "simulacao": simular, "area": plano["area"].as_posix(),
            "lancador": (plano["bin"] / f"abrir-fundacao-{plano['projeto']}").as_posix(), "ficha": ficha,
            "aberturas": {k: ab[k] for k in ("valida", "motivo", "versao", "rede", "webfetch", "websearch")},
            "canario": {k: canario.get(k) for k in ("aprovado", "motivo", "arquivo", "forma")},
            "gerenciadas": gerenciadas, "plugins": [p["nome"] for p in plano["plugins"]],
            "ferramentas": plano["hashes"]["ferramentas"], "seccomp": plano["seccomp"], "avisos": avisos,
            "ferramenta_titular": ferramenta, "acoes": acoes or [],
            "proximo_passo": f"abrir-fundacao-{plano['projeto']}"}


def instalar_canario(relatorio, area_raiz=AREA_RAIZ, *, ensaio: bool = False, simular: bool = False) -> dict:
    """`instalar-canario` (titular, com sudo): confere o relatório do ensaio real do canário
    (`scripts/ensaio_isolamento_wsl.py`, `fundacao.ensaio_isolamento/1` com os comandos confinados) e o copia, de dono
    root, para `<área>/canario/<versão do Claude Code>.json`. O `instalar-projeto` seguinte o confere contra o Claude
    Code fixado e a forma de caminho da raiz, o fixa no hashes.json e só então aplica a ficha (contratos, §0). Sem
    root, só em ensaio (--area-raiz explícita)."""
    if os.name == "nt":
        raise EntradaInvalida("o canário é do Ubuntu (WSL2): rode no terminal do Ubuntu")
    raiz_dono = _e_root()
    if not simular and not raiz_dono and not ensaio:
        raise EntradaInvalida("a área do titular é de dono root: rode com sudo (o preparar-wsl.sh --canario <relatório> "
                              "faz isso)")
    try:
        dados = _ler_bytes_seguro(relatorio, TETO_JSON)
        conteudo = json.loads(dados.decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise EntradaInvalida(f"relatório do canário ilegível ({exc})") from None
    motivo = conferir_relatorio_do_canario(conteudo)
    if motivo:
        raise EntradaInvalida(f"relatório do canário recusado: {motivo}")
    versao = conteudo["claude"]["versao"]
    destino = Path(area_raiz) / "canario" / f"{versao}.json"
    sha = hashlib.sha256(dados).hexdigest()
    saida = {"canario": destino.as_posix(), "versao": versao, "forma": conteudo.get("forma"), "sha256": sha,
             "simulacao": simular, "proximo_passo": "rode de novo o preparar-wsl.sh de cada projeto: a ficha só vale "
                                                    "com o canário da mesma versão do Claude Code e da forma da raiz"}
    if os.path.lexists(destino) and _sha_ou_motivo(destino) == sha:
        return {**saida, "acao": "igual"}
    acao = "atualizar" if os.path.lexists(destino) else "criar"
    if not simular:
        _pasta_area(destino.parent, raiz_dono)
        _publicar(destino, dados, 0o644, raiz_dono)
    return {**saida, "acao": acao}


def aberturas_da_area(raiz, projeto: str, area_raiz, *, vigente=None, hoje=None) -> dict:
    """A ficha da área root com o mesmo portão do `instalar-projeto` (para gerar e conferir o perfil): sem área, sem a
    versão do Claude Code fixada no hashes.json dela ou sem canário aprovado, tudo fechado."""
    area = Path(area_raiz) / "projetos" / projeto
    if not area.is_dir():
        return aberturas_fechadas()
    try:
        claude = _objeto(_objeto(_ler_json_seguro(area / "hashes.json", TETO_HASHES)).get("claude"))
    except (OSError, ValueError):
        claude = {}
    raiz = Path(os.path.abspath(raiz))
    canario = portao_do_canario(area_raiz, claude_versao=claude.get("versao"), claude_sha256=claude.get("sha256"),
                                raiz_wsl=raiz.as_posix())
    ab = aberturas_da_ficha(_consultar(vigente or carregar_vigente(), raiz, projeto, area / "ficha"), projeto, hoje)
    return com_canario(ab, canario)


# ------------------------------------------------------------------ lançador (abrir-sessao.sh -> abrir-fundacao-<p>)
def _aspas_bash(valor: str) -> str:
    return valor.replace("'", "'" + BARRA_INVERTIDA + "''")


def lancador(valores: dict, modelo: str | None = None) -> str:
    """`abrir-sessao.sh` com os valores fixados. Cada marcador do modelo fica entre aspas simples, e o valor tem as
    aspas simples escapadas: um caminho com aspas ou espaços não vira comando."""
    faltam = [k for k in CHAVES_DO_LANCADOR if k != "PLUGINS" and not str(valores.get(k, "")).strip()]
    if faltam or "PLUGINS" not in valores:
        raise EntradaInvalida("valores ausentes para o lançador: " + ", ".join(faltam or ["PLUGINS"]))
    for k in CHAVES_DO_LANCADOR:
        if any(c in str(valores[k]) for c in ("\n", "\r", "\0")):
            raise EntradaInvalida(f"{k} com quebra de linha")
    for k in ("RAIZ", "AREA", "SKILL", "CLAUDE_BIN", "TEMP_PROJETO", "SONDA_INTEROP_CMD", "SONDA_INTEROP_BINFMT"):
        if not str(valores[k]).startswith("/"):
            raise EntradaInvalida(f"{k} precisa ser caminho absoluto do Linux: {valores[k]!r}")
    for k in ("CLAUDE_SHA256", "PREPARO_SHA256", "PORTEIRO_SHA256"):
        if not SHA256.match(str(valores[k])):
            raise EntradaInvalida(f"{k} não é um SHA-256 em hexadecimal minúsculo: {valores[k]!r}")
    projeto_valido(str(valores["PROJETO"]))
    if not USUARIO_LINUX.match(str(valores["USUARIO"])):
        raise EntradaInvalida(f"usuário do Linux inválido: {valores['USUARIO']!r}")
    if not re.match(r"^[0-9]+\.[0-9]+\.[0-9]+$", str(valores["CLAUDE_VERSAO"])):
        raise EntradaInvalida(f"versão do Claude Code inválida: {valores['CLAUDE_VERSAO']!r}")
    if not re.fullmatch(r"[A-Za-z]+(,[A-Za-z]+)*", str(valores["FERRAMENTAS"])):
        raise EntradaInvalida("FERRAMENTAS fora da forma (nomes separados por vírgula)")
    if not all(IDENTIFICADOR.match(n) for n in str(valores["PLUGINS"]).split()):
        raise EntradaInvalida("PLUGINS fora da forma (nomes de plugin separados por espaço)")
    modelo = modelo if modelo is not None else MODELO_LANCADOR.read_text(encoding="utf-8")
    for m in MARCADOR.finditer(modelo):
        if modelo[m.start() - 1:m.start()] != "'" or modelo[m.end():m.end() + 1] != "'":
            raise EntradaInvalida(f"marcador fora de aspas simples no modelo do lançador: {m.group(0)}")
    texto = renderizar(modelo, {k: _aspas_bash(str(v)) for k, v in valores.items()})
    if "\r" in texto or not texto.startswith("#!/usr/bin/env bash\n"):
        raise EntradaInvalida("modelo do lançador sem a primeira linha do bash ou com CR")
    return texto


# ------------------------------------------------------------------ conferência que o lançador roda (como o usuário)
def _sha_ou_motivo(caminho: Path) -> str:
    try:
        return _carregar_script("copia_segura").hash_conferido(caminho)["sha256"]
    except OSError as exc:
        return f"(ausente ou recusado: {exc.strerror or exc})"


def _comando_de_arquivar(raiz: Path, projeto: str, arquivo: Path) -> str:
    destino = raiz / ".claude" / "projetos" / projeto / "anteriores" / datetime.now().strftime("%Y%m%dT%H%M%S")
    return f"mkdir -p {shlex.quote(destino.as_posix())} && mv {shlex.quote(arquivo.as_posix())} {shlex.quote(destino.as_posix())}/"


def _regra_aceita(regra, ferramentas: set) -> bool:
    """Regra de `permissions.allow` que o CLI grava em "não perguntar de novo" e que não afrouxa a sessão: ferramenta
    da lista do projeto (sem WebFetch nem WebSearch), sem MCP, sem curinga amplo e, nas de arquivo, só dentro do
    projeto (sem caminho absoluto, casa ou '..')."""
    m = re.fullmatch(r"([A-Za-z]+)\((.+)\)", regra) if isinstance(regra, str) else None
    if not m or m.group(1) not in ferramentas - {"WebFetch", "WebSearch"}:
        return False
    corpo = m.group(2).strip()
    if corpo in ("*", "**", ":*", "/**", "//**", "~/**", "./**") or corpo.startswith("*"):
        return False
    if m.group(1) != "Bash" and (corpo.startswith(("/", "~")) or ".." in corpo.split("/")):
        return False
    return True


def conferir_configuracoes_do_projeto(raiz: Path, projeto: str, ferramentas: set) -> list[str]:
    """`projects/<p>/.claude/settings*.json` (contratos, §6): só `settings.local.json` no formato exato aceito — só
    `permissions.allow`, com regras de `_regra_aceita`; o resto não abre, com o comando de arquivar o arquivo."""
    pasta = raiz / "projects" / projeto / ".claude"
    try:
        st = os.lstat(pasta)
    except FileNotFoundError:
        return []
    copia = _carregar_script("copia_segura")
    if copia.e_ligacao(st):
        return [f"projects/{projeto}/.claude é ligação: arquive-a ({_comando_de_arquivar(raiz, projeto, pasta)})"]
    if not stat.S_ISDIR(st.st_mode):
        return []  # arquivo no lugar da pasta: é marcador do sandbox (os marcadores decidem)
    problemas = []
    for nome in sorted(os.listdir(pasta)):
        if not re.fullmatch(r"settings.*\.json", nome, re.I):
            continue
        arquivo = pasta / nome
        recusa = None
        if nome != "settings.local.json":
            recusa = "só o settings.local.json é aceito na pasta do projeto"
        else:
            try:
                dados = _ler_json_seguro(arquivo, 64 * 1024)
                regras = _objeto(_objeto(dados).get("permissions")).get("allow")
                if (not isinstance(dados, dict) or set(dados) != {"permissions"} or set(dados["permissions"]) != {"allow"}
                        or not isinstance(regras, list) or not all(_regra_aceita(r, ferramentas) for r in regras)):
                    recusa = ("formato aceito: só permissions.allow, com regras das ferramentas do projeto, sem "
                              "WebFetch(domain:), sem mcp__ e sem curinga amplo")
            except (OSError, ValueError) as exc:
                recusa = f"ilegível ({exc})"
        if recusa:
            problemas.append(f"projects/{projeto}/.claude/{nome}: {recusa}. Para arquivar: "
                             f"{_comando_de_arquivar(raiz, projeto, arquivo)}")
    return problemas


def _marcadores(raiz: Path, projeto: str, nomes, limpar: bool) -> tuple[list, list, list]:
    """Pontos de montagem de 0 byte que o sandbox deixa na pasta de trabalho (sandbox-runtime, 31/10/2026): arquivo
    comum de 0 byte, um nome só, sem ligação — apagado (com `limpar`); pasta de editor vazia — apagada; com conteúdo,
    os de shell e git, o `.mcp.json` e o `CLAUDE.local.md` não abrem. Devolve (problemas, avisos, limpos)."""
    proj = raiz / "projects" / projeto
    problemas, avisos, limpos = [], [], []
    copia = _carregar_script("copia_segura")
    for nome in [*nomes, *MARCADORES_PASTA]:
        caminho = proj / nome
        try:
            st = os.lstat(caminho)
        except FileNotFoundError:
            continue
        if copia.e_ligacao(st):
            problemas.append(f"ligação no lugar de projects/{projeto}/{nome}: arquive-a "
                             f"({_comando_de_arquivar(raiz, projeto, caminho)})")
        elif stat.S_ISREG(st.st_mode) and st.st_size == 0 and st.st_nlink == 1:
            if limpar:
                os.unlink(caminho)  # tira só o nome (apagar depende da pasta, não do modo do arquivo)
            limpos.append(nome)
        elif stat.S_ISDIR(st.st_mode) and (nome in MARCADORES_PASTA or nome == ".claude"):
            if not os.listdir(caminho):
                if limpar:
                    os.rmdir(caminho)
                limpos.append(nome + "/")
            elif nome in MARCADORES_PASTA:
                avisos.append(f"projects/{projeto}/{nome}/ com conteúdo: mantido (o sandbox nega a escrita nela)")
        elif nome in (*MARCADORES_OBRIGATORIOS, *MARCADORES_RECUSADOS):
            problemas.append(f"projects/{projeto}/{nome} com conteúdo ou de outro tipo: a sessão não abre com ele. "
                             f"Para arquivar: {_comando_de_arquivar(raiz, projeto, caminho)}")
    for nome in (n for n in MARCADORES_LIMPEZA if n not in nomes):  # só limpeza: com conteúdo, são do projeto
        try:
            st = os.lstat(proj / nome)
        except OSError:
            continue
        if not copia.e_ligacao(st) and stat.S_ISREG(st.st_mode) and st.st_size == 0 and st.st_nlink == 1:
            if limpar:
                os.unlink(proj / nome)
            limpos.append(nome)
    for pasta in (raiz, raiz / "projects"):  # conferidos sem apagar: limpeza pela Lixeira com o OK do titular
        achados = [n for n in MARCADORES_OBRIGATORIOS if os.path.lexists(pasta / n)]
        if achados:
            avisos.append(f"marcadores do sandbox em {pasta.as_posix()}: {', '.join(achados)} (não apagados)")
    return problemas, avisos, limpos


def conferir_abertura(raiz, projeto: str, area, *, limpar: bool = False, hoje: date | None = None) -> dict:
    """O que o lançador confere antes de abrir (contratos, §6; folha do HOST, item 4), como o usuário: tudo o que o
    hashes.json da área root fixa (Claude Code, perfil, porteiro.json, mcp.json, aberturas.json, ficha, hooks da raiz,
    cópia da skill, kit da raiz pela conta do porteiro, plugins e o relatório do canário que liberou a ficha), a ficha
    vencida, a trava de manutenção (só a existência de `state/manutencao.json`), as configurações e o `.mcp.json` do
    projeto e os marcadores de 0 byte."""
    raiz, area = Path(os.path.abspath(raiz)), Path(area)
    projeto_valido(projeto)
    problemas, avisos = [], []
    try:
        hashes = _ler_json_seguro(area / "hashes.json", TETO_HASHES)
        if not isinstance(hashes, dict) or hashes.get("schema_version") != ESQUEMA_HASHES:
            raise ValueError("fora do esquema")
    except (OSError, ValueError) as exc:
        return {"ok": False, "problemas": [f"hashes.json da área do titular ausente ou ilegível ({exc}): rode de novo "
                                           "o preparo do Ubuntu (preparar-wsl.sh)"], "avisos": [], "limpos": []}
    if hashes.get("projeto") != projeto or hashes.get("raiz") != raiz.as_posix():
        problemas.append("o hashes.json da área é de outro projeto ou de outra raiz")
    for caminho, esperado in sorted(_objeto(hashes.get("arquivos")).items()):
        # Só caminho absoluto (o que o preparo grava): um relativo seria lido da pasta atual do titular.
        atual = _sha_ou_motivo(Path(caminho)) if os.path.isabs(caminho) else "(caminho relativo: não lido)"
        if atual != esperado:
            problemas.append(f"{caminho} mudou desde o preparo (esperado {str(esperado)[:12]}..., encontrado "
                             f"{atual[:40]}): se a mudança foi sua, rode de novo o preparar-wsl.sh; se não foi, não abra")
    for nome, arvore in sorted(_objeto(hashes.get("arvores")).items()):
        caminho = str(_objeto(arvore).get("caminho", ""))
        try:  # o kit pela conta do porteiro; plugins e managed settings: tudo conta, como no preparo
            if nome == "kit":  # vazio ou relativo seria a pasta atual: fora da forma (nas outras, manifesto_de_arvore)
                atual = (kit_sha256(Path(caminho).parent) if os.path.isabs(caminho) and Path(caminho).name == "fundacao"
                         else "(fora da forma)")
            else:
                kw = ({"pastas_ignoradas": (), "sufixos_ignorados": ()}
                      if nome.startswith("plugin:") or nome == "claude-code-gerenciado" else {})
                atual = sha256_arvore(caminho, **kw)
        except (EntradaInvalida, OSError) as exc:
            atual = f"(recusada: {exc})"
        if atual != _objeto(arvore).get("sha256"):
            problemas.append(f"a árvore {nome} ({caminho}) mudou desde o preparo: rode de novo o preparar-wsl.sh (se "
                             "foi uma atualização da fundação) ou não abra")
    canario = _objeto(hashes.get("canario"))
    if canario.get("aprovado") is True:  # o relatório que liberou a ficha ainda vale (o arquivo já foi conferido acima)
        claude = _objeto(hashes.get("claude"))
        atual = portao_do_canario(area.parent.parent, claude_versao=claude.get("versao"),
                                  claude_sha256=claude.get("sha256"), raiz_wsl=raiz.as_posix())
        if not atual["aprovado"] or atual["sha256"] != canario.get("sha256"):
            problemas.append(f"o canário que liberou a ficha não vale mais ({atual['motivo']}): rode de novo o "
                             "preparar-wsl.sh")
    ficha = hashes.get("ficha")
    if isinstance(ficha, dict) and ficha.get("vigencia_ate"):
        try:
            dados = _ler_json_seguro(area / "ficha" / str(ficha.get("arquivo")), TETO_JSON)
            vigencia = date.fromisoformat(str(_objeto(dados).get("vigencia_ate")))
            if vigencia < (hoje or date.today()):
                problemas.append(f"a ficha de aberturas v{ficha.get('versao')} venceu em {vigencia.isoformat()}: assine "
                                 "uma versão nova (fundacao_titular.py assinar-ficha) e rode o preparo")
        except (OSError, ValueError) as exc:
            problemas.append(f"ficha de aberturas ilegível ({exc})")
    if os.path.lexists(raiz / "state" / "manutencao.json"):
        problemas.append("a fundação está em manutenção (atualização ou cópia de segurança): espere terminar")
    gerenciadas = str(hashes.get("gerenciadas") or GERENCIADAS)
    if os.path.lexists(gerenciadas) and "claude-code-gerenciado" not in _objeto(hashes.get("arvores")):
        problemas.append(f"{gerenciadas} (managed settings, acima do perfil) apareceu depois do preparo: confira o "
                         "conteúdo e rode de novo o preparar-wsl.sh, que o fixa pelo SHA-256")
    try:  # projeto criado depois do preparo: o perfil (já conferido pelo hash acima) não nega a leitura dele
        negacoes = _lista(_objeto(_objeto(_ler_json_seguro(area / "settings.wsl.json", TETO_JSON)).get(
            "permissions")).get("deny"))
        faltam = [o for o in projetos_da_raiz(raiz) if o != projeto
                  and f"Read(/{raiz.as_posix()}/projects/{o}/**)" not in negacoes]
        if faltam:
            problemas.append("projetos criados depois do preparo, sem leitura negada no perfil deste: "
                             + ", ".join(faltam) + " (rode de novo o preparar-wsl.sh)")
    except (OSError, ValueError) as exc:
        problemas.append(f"perfil da área ilegível ({exc})")
    proj = raiz / "projects" / projeto
    copia = _carregar_script("copia_segura")
    for caminho in (raiz / "projects", proj):
        try:
            st = os.lstat(caminho)
            if copia.e_ligacao(st) or not stat.S_ISDIR(st.st_mode):
                problemas.append(f"{caminho.as_posix()} é ligação ou não é pasta")
        except OSError:
            problemas.append(f"{caminho.as_posix()} ausente")
    ferramentas = set(str(hashes.get("ferramentas", "")).split(","))
    nomes = [n for n in _lista(hashes.get("marcadores")) if isinstance(n, str) and "/" not in n and n not in ("", ".", "..")]
    p_marc, a_marc, limpos = _marcadores(raiz, projeto, nomes, limpar)
    problemas += p_marc + conferir_configuracoes_do_projeto(raiz, projeto, ferramentas)
    avisos += a_marc
    # I19: o canário não mede esta pasta. O `conclusao.carga_aninhada` cobre a skill e o agente de uma `.claude/` em
    # subpasta do projeto do ensaio (`aninhado/.claude/`), fora de `confina_comandos`; o ensaio não tem item para a
    # `.claude/` do próprio projeto (nem para comandos e hooks). Aqui é só aviso.
    for sub in ("skills", "agents", "commands", "hooks"):
        if os.path.lexists(proj / ".claude" / sub):
            avisos.append(f"projects/{projeto}/.claude/{sub} existe: com --setting-sources local não deve carregar; o "
                          "canário mede a carga aninhada numa subpasta (aninhado/.claude/, só skill e agente), não esta "
                          "pasta; não ponha peças ali, use a ficha (plugins)")
    # O filtro seccomp só é medido quando o preparo o achou instalado, nos caminhos absolutos que gravou. Sem ele, o
    # hashes.json não tem "filtro", e a árvore de "" era a pasta atual do titular, lida a cada abertura (reconferência
    # do lote 2: state/ e outros projetos inclusive, para um hash jogado fora).
    sec = _objeto(hashes.get("seccomp"))
    filtro, pacote, com_filtro = sec.get("filtro"), sec.get("caminho"), False
    if (sec.get("instalado") is True and isinstance(filtro, str) and os.path.isabs(filtro)
            and isinstance(pacote, str) and os.path.isabs(pacote)):
        try:
            com_filtro = (sha256_arvore(filtro, pastas_ignoradas=(), sufixos_ignorados=()) == sec.get("filtro_sha256")
                          and _sha_ou_motivo(Path(pacote)) == sec.get("sha256"))
        except (EntradaInvalida, OSError):
            com_filtro = False
    if not com_filtro:
        avisos.append("sockets sem filtro: o filtro seccomp do sandbox não está instalado (ou mudou)")
    return {"ok": not problemas, "problemas": problemas, "avisos": avisos, "limpos": limpos}


def limpar_marcadores(raiz, projeto: str, area) -> dict:
    """Só a limpeza dos marcadores de 0 byte (o lançador chama ao sair)."""
    raiz, area = Path(os.path.abspath(raiz)), Path(area)
    projeto_valido(projeto)
    try:
        nomes = _lista(_objeto(_ler_json_seguro(area / "hashes.json", TETO_HASHES)).get("marcadores"))
    except (OSError, ValueError):
        nomes = []
    nomes = [n for n in nomes if isinstance(n, str) and "/" not in n and n not in ("", ".", "..")] or [
        *MARCADORES_OBRIGATORIOS, *MARCADORES_RECUSADOS]
    problemas, avisos, limpos = _marcadores(raiz, projeto, nomes, True)
    return {"limpos": limpos, "problemas": problemas, "avisos": avisos}


# ------------------------------------------------------------------ pastas de trabalho de porteiro morto (lançador)
# O porteiro.py (pacote PORTEIRO) cria a pasta de trabalho com tempfile.mkdtemp(prefix="trabalho-") em
# ~/.fundacao/porteiro/<p>/ e só a apaga ao encerrar; morto por SIGKILL, ela fica, com a cópia privada do kit.
TRABALHO_DO_PORTEIRO = re.compile(r"trabalho-[a-z0-9_]{8}")


def _fila_do_argv(args: list) -> str | None:
    """O valor de --fila (ou --fila=) de uma linha de comando do porteiro, normalizado."""
    for i, arg in enumerate(args):
        if arg == "--fila" and i + 1 < len(args):
            return posixpath.normpath(args[i + 1])
        if arg.startswith("--fila="):
            return posixpath.normpath(arg[len("--fila="):])
    return None


def _fila_do_projeto(fila: str | None, projeto: str | None) -> bool:
    """A --fila de um porteiro termina em `projects/<p>/.porteiro`: é um porteiro deste projeto, de qualquer raiz."""
    return bool(fila and projeto) and fila.split("/")[-3:] == ["projects", projeto, ".porteiro"]


def _uso_da_pasta_do_porteiro(pasta: str, fila: str, proc: str = "/proc",
                              projeto: str | None = None) -> list[str] | None:
    """Por que a pasta do porteiro do projeto não pode ser limpa agora, lido em /proc só nos processos deste usuário:
    o porteiro do projeto de pé (um argumento termina em porteiro.py e a --fila é a do projeto nesta raiz ou, de outra
    raiz, termina em `/projects/<p>/.porteiro`: a pasta ~/.fundacao/porteiro/<p>/ é do nome do projeto, não da raiz;
    folha da integração, I6) e quem cita a pasta num argumento ou roda com a pasta atual dentro dela (o kit órfão de um
    porteiro morto: a cópia e o pycache_prefix ficam ali). None: /proc ilegível (na dúvida, nada sai). A prova pela
    trava do porteiro (porteiro.trava) é de limpar_trabalho_do_porteiro."""
    try:
        pids = [n for n in os.listdir(proc) if n.isdigit()]
    except OSError:
        return None
    uid, eu = os.getuid(), {os.getpid(), os.getppid()}  # este ajudante e o lançador que o chamou
    prefixos = {p.rstrip("/") + "/" for p in (pasta, os.path.realpath(pasta))}
    motivos = []
    for pid in pids:
        base = os.path.join(proc, pid)
        try:
            if int(pid) in eu or os.stat(base).st_uid != uid:
                continue
            with open(os.path.join(base, "cmdline"), "rb") as arq:
                args = [a.decode("utf-8", "surrogateescape") for a in arq.read(1 << 20).split(b"\0") if a]
        except OSError:
            continue  # o processo saiu durante a leitura
        fila_dele = _fila_do_argv(args)
        if any(posixpath.basename(a) == "porteiro.py" for a in args) and (
                fila_dele == fila or _fila_do_projeto(fila_dele, projeto)):
            motivos.append(f"o porteiro deste projeto está de pé (pid {pid}"
                           + (")" if fila_dele == fila else f", fila de outra raiz: {fila_dele})"))
        elif any(a + "/" in prefixos or any(p in a for p in prefixos) for a in args):
            motivos.append(f"o processo {pid} usa a pasta do porteiro (o kit de um porteiro encerrado?)")
        else:
            try:
                atual = os.readlink(os.path.join(base, "cwd"))
            except OSError:
                continue  # sem acesso (processo protegido, como o ssh-agent) ou já saiu
            if any((atual + "/").startswith(p) for p in prefixos):
                motivos.append(f"o processo {pid} roda dentro da pasta do porteiro")
    return motivos


def _apagar_por_descritor(fd_pai: int, nome: str, profundidade: int = 0) -> None:
    """Apaga a pasta `nome` de dentro de `fd_pai` sem seguir ligação: cada nível abre pelo descritor do de cima com
    O_DIRECTORY|O_NOFOLLOW (uma pasta trocada por ligação no meio falha, não é seguida), e ligação, arquivo e especial
    saem pelo nome. O shutil.rmtree com dir_fd faz o mesmo, mas só no Python 3.11+ (a skill aceita o 3.10)."""
    if profundidade > 64:
        raise OSError(f"{nome}: pastas fundas demais")
    fd = os.open(nome, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd_pai)
    try:
        with os.scandir(fd) as entradas:
            filhos = [(e.name, e.is_dir(follow_symlinks=False)) for e in entradas]
        for filho, e_pasta in filhos:
            if e_pasta:
                _apagar_por_descritor(fd, filho, profundidade + 1)
            else:
                os.unlink(filho, dir_fd=fd)
    finally:
        os.close(fd)
    os.rmdir(nome, dir_fd=fd_pai)


def _trava_do_porteiro(fd_pasta: int) -> tuple[int | None, str | None]:
    """A prova pela trava do porteiro (folha da integração, I6): o porteiro.py toma flock exclusivo em
    `porteiro.trava` (_tomar_unico) enquanto está de pé. Aberta pelo descritor da pasta do projeto, O_RDONLY|O_NOFOLLOW e
    sem criar; `flock(LOCK_EX|LOCK_NB)` bloqueado = um porteiro deste projeto está de pé, de qualquer raiz (mesmo
    fora do /proc visível). Tomada, a trava fica com quem limpa até o fim (um porteiro que suba no meio sai com
    "já há um porteiro deste projeto de pé", sem tocar a fila, e nenhuma pasta dele é apagada). Devolve (descritor ou
    None, motivo para manter tudo ou None); sem o arquivo, (None, None): nenhum porteiro subiu nesta casa."""
    import fcntl
    try:
        fd = os.open("porteiro.trava", os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=fd_pasta)
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        return None, f"porteiro.trava não abriu sem seguir ligação ({exc.strerror or exc}): nada apagado"
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("porteiro.trava não é arquivo comum")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None, "o porteiro deste projeto está de pé (porteiro.trava travada por outro processo)"
    except OSError as exc:
        os.close(fd)
        return None, f"a trava do porteiro não foi conferida ({exc.strerror or exc}): nada apagado"
    return fd, None


def limpar_trabalho_do_porteiro(casa, raiz, projeto: str, *, proc: str = "/proc") -> dict:
    """As pastas de trabalho (`trabalho-*`) que um porteiro morto sem encerrar (SIGKILL) deixou em
    `<casa>/.fundacao/porteiro/<p>/` (orientação do coordenador na reconferência do lote 2). O lançador chama com a
    trava de sessão do projeto na mão (o porteiro que ele inicia herda o descritor dela), antes de iniciar o porteiro e
    ao sair; nada sai enquanto o porteiro deste projeto estiver de pé, provado pela trava dele (`porteiro.trava`,
    _trava_do_porteiro) ou visto, entre os processos deste usuário, em /proc (`_uso_da_pasta_do_porteiro`, também com a
    fila de outra raiz: folha da integração, I6), enquanto alguém usar a pasta, nem sem /proc legível. Cada nível, da
    casa à pasta de trabalho, abre pelo descritor com O_NOFOLLOW e precisa ser deste usuário: ligação nunca é seguida
    (no lugar da pasta de trabalho, fica onde está). Só no Linux. Devolve {"pasta", "apagadas", "mantidas", "motivo"}."""
    projeto_valido(projeto)
    casa = os.fspath(casa) if isinstance(casa, (str, os.PathLike)) else ""
    if not casa or not os.path.isabs(casa):
        raise EntradaInvalida("--casa precisa ser um caminho absoluto (o HOME do usuário do lançador)")
    pasta = posixpath.join(posixpath.normpath(Path(casa).as_posix()), ".fundacao", "porteiro", projeto)
    saida = {"pasta": pasta, "apagadas": [], "mantidas": [], "motivo": None}
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        return {**saida, "motivo": "só no Linux (o porteiro roda no Ubuntu)"}
    fila = posixpath.join(Path(os.path.abspath(raiz)).as_posix(), "projects", projeto, ".porteiro")
    abrir = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    fds = []
    try:
        try:
            fds.append(os.open(casa, abrir))
            for parte in (".fundacao", "porteiro", projeto):
                fds.append(os.open(parte, abrir | os.O_NOFOLLOW, dir_fd=fds[-1]))
                if os.fstat(fds[-1]).st_uid != os.getuid():
                    return {**saida, "motivo": f"{parte} não é deste usuário: nada apagado"}
        except FileNotFoundError:
            return saida  # sem a pasta do porteiro, nada a limpar
        except OSError as exc:
            return {**saida, "motivo": f"a pasta do porteiro não abriu sem seguir ligação ({exc.strerror or exc}): "
                                       "nada apagado"}
        pasta_fd = fds[-1]
        with os.scandir(pasta_fd) as entradas:
            nomes = sorted(e.name for e in entradas if TRABALHO_DO_PORTEIRO.fullmatch(e.name))
        if not nomes:
            return saida
        trava, motivo = _trava_do_porteiro(pasta_fd)  # a prova pela trava vem antes do /proc (I6)
        if trava is not None:
            fds.append(trava)  # fica tomada até o fim (fechada no finally)
        if motivo:
            return {**saida, "mantidas": nomes, "motivo": motivo}
        uso = _uso_da_pasta_do_porteiro(pasta, posixpath.normpath(fila), proc, projeto)
        if uso is None or uso:
            motivo = ("/proc ilegível: não dá para saber se o porteiro está de pé" if uso is None
                      else "; ".join(uso[:3]))
            return {**saida, "mantidas": nomes, "motivo": motivo}
        for nome in nomes:
            try:
                st = os.stat(nome, dir_fd=pasta_fd, follow_symlinks=False)
                if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
                    saida["mantidas"].append(nome)
                    saida["motivo"] = f"{nome} é ligação, não é pasta ou é de outra conta: não seguida nem apagada"
                    continue
                _apagar_por_descritor(pasta_fd, nome)
                saida["apagadas"].append(nome)
            except (OSError, RecursionError) as exc:
                saida["mantidas"].append(nome)
                saida["motivo"] = f"{nome}: {exc}"
        return saida
    finally:
        for fd in fds:
            os.close(fd)


# ------------------------------------------------------------------ linha de comando
def gravar(destino, texto: str) -> None:
    """Grava inteiro ou nada: arquivo temporário ao lado e troca no fim."""
    destino = Path(destino)
    temporario = destino.with_name("." + destino.name + ".tmp")
    temporario.write_text(texto, encoding="utf-8", newline="\n")
    temporario.replace(destino)


def _entregar(texto: str, saida) -> None:
    if saida:
        gravar(saida, texto)
    else:
        sys.stdout.write(texto)


def _imprimir(dados) -> None:
    print(json.dumps(dados, ensure_ascii=False, default=str))


def _parametros_confiaveis(a, area: Path) -> tuple[dict, list]:
    """Vagas do perfil que a conferência compara: as da linha de comando, senão as do hashes.json da área root."""
    avisos, p = [], {"perfil_windows": None, "ancora_base": None, "temp_base": None}
    try:
        gravados = _objeto(_ler_json_seguro(area / "hashes.json", TETO_HASHES).get("parametros"))
    except (OSError, ValueError):
        gravados = {}
    for chave, valor in (("perfil_windows", a.perfil_windows), ("ancora_base", a.ancora_base),
                         ("temp_base", a.temp_base)):
        p[chave] = (caminho_wsl(valor) if valor and chave != "temp_base" else valor) or gravados.get(chave)
    if any(v is None for v in p.values()):
        avisos.append("vagas lidas do próprio perfil (sem --perfil-windows e sem hashes.json da área): confira a pasta "
                      "do Windows e a âncora")
    return p, avisos


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("perfil-windows", allow_abbrev=False)
    w.add_argument("--raiz", required=True)
    w.add_argument("--python", required=True)
    w.add_argument("--projeto")
    w.add_argument("--negar-skill", action="append", default=[], help="skill aninhada em pasta de dados")
    w.add_argument("--somente-leitura", action="append", default=[])
    w.add_argument("--backups", action="append", default=[])
    w.add_argument("--saida")
    for nome in ("gerar-perfil-projeto", "perfil-wsl"):
        s = sub.add_parser(nome, allow_abbrev=False)
        s.add_argument("--raiz", required=True)
        s.add_argument("--projeto", required=True)
        s.add_argument("--perfil-windows", required=True)
        s.add_argument("--area-raiz", default=AREA_RAIZ)
        s.add_argument("--temp-base", default=TEMP_BASE)
        s.add_argument("--ancora-base", default=ANCORA_BASE_WSL)
        s.add_argument("--montagem", default=MONTAGEM)
        s.add_argument("--somente-leitura", action="append", default=[], help="só para ensaio: soma ao registro")
        s.add_argument("--negar-skill", action="append", default=[], help="só para ensaio: soma ao registro")
        s.add_argument("--backups", action="append", default=[], help="saiu na 1.7.10 (recusado)")
        s.add_argument("--saida")
    k = sub.add_parser("conferir-perfil-wsl", allow_abbrev=False)
    for nome in ("--perfil", "--raiz", "--projeto"):
        k.add_argument(nome, required=True)
    for nome in ("--perfil-windows", "--ancora-base", "--temp-base", "--lancador"):
        k.add_argument(nome)
    k.add_argument("--area-raiz", default=AREA_RAIZ)
    n = sub.add_parser("instalar-projeto", allow_abbrev=False)
    for nome in ("--raiz", "--projeto", "--titular", "--claude", "--claude-versao", "--claude-sha256", "--origem-hash",
                 "--perfil-windows", "--casa", "--usuario"):
        n.add_argument(nome, required=True)
    for nome in ("--area-raiz", "--bin", "--temp-base", "--sonda-interop-cmd", "--sonda-interop-binfmt",
                 "--gerenciadas", "--ferramenta-base"):
        n.add_argument(nome)
    pf = sub.add_parser("plano-ferramenta", allow_abbrev=False)  # o preparar-maquina.ps1 (cópia do Windows, I11)
    pf.add_argument("--python", help="python.exe fixado da cópia do Windows (só um instalado para todos os usuários)")
    n.add_argument("--ancora-base", default=ANCORA_BASE_WSL)
    n.add_argument("--simular", action="store_true")
    cn = sub.add_parser("instalar-canario", allow_abbrev=False)
    cn.add_argument("--relatorio", required=True, help="relatório fundacao.ensaio_isolamento/1 do ensaio real")
    cn.add_argument("--area-raiz", help="só para ensaio, sem root (padrão: /etc/fundacao-ia, com sudo)")
    cn.add_argument("--simular", action="store_true")
    for nome in ("conferir-abertura", "limpar-marcadores"):
        c = sub.add_parser(nome, allow_abbrev=False)
        for opcao in ("--raiz", "--projeto", "--area"):
            c.add_argument(opcao, required=True)
        if nome == "conferir-abertura":
            c.add_argument("--limpar", action="store_true")
            c.add_argument("--texto", action="store_true")
    lp = sub.add_parser("limpar-porteiro", allow_abbrev=False)
    for opcao in ("--raiz", "--projeto", "--casa"):
        lp.add_argument(opcao, required=True)
    lp.add_argument("--texto", action="store_true")
    r = sub.add_parser("registrar-projeto", allow_abbrev=False)
    r.add_argument("--raiz", required=True)
    r.add_argument("--projeto", required=True)
    r.add_argument("--origem", action="append", required=True)
    r.add_argument("--somente-leitura", action="append", default=[])
    r.add_argument("--negar-skill", action="append", default=[])
    lr = sub.add_parser("ler-projetos-host", allow_abbrev=False)
    lr.add_argument("--raiz", required=True)
    lr.add_argument("--projeto")
    fr = sub.add_parser("fora-do-registro", allow_abbrev=False)  # o preparar-maquina.ps1 (defeito 3 da revisão)
    fr.add_argument("--raiz", required=True)
    fr.add_argument("--somente-leitura", action="append", default=[])
    fr.add_argument("--negar-skill", action="append", default=[])
    uc = sub.add_parser("ultima-copia", allow_abbrev=False)  # o portão das cópias dos scripts do Windows (defeito 2)
    uc.add_argument("--raiz", required=True)
    i = sub.add_parser("identidade", allow_abbrev=False)
    i.add_argument("--titular", required=True)
    i.add_argument("--projeto", help="projeto autenticado das sessões (FUNDACAO_PROJECT)")
    i.add_argument("--atual", help="settings.local.json existente: acrescenta só a identidade")
    i.add_argument("--estrito", action="store_true", help="só a identidade (e o projeto, se dado)")
    i.add_argument("--sem-projeto", action="store_true", help="tira o FUNDACAO_PROJECT (1.7.10: vai ao settings.json)")
    i.add_argument("--saida")
    d = sub.add_parser("conferir-identidade", allow_abbrev=False)
    for nome in ("--arquivo", "--titular", "--projeto"):
        d.add_argument(nome, required=True)
    cw = sub.add_parser("wsl-conf", allow_abbrev=False)
    cw.add_argument("--arquivo", required=True)
    cw.add_argument("--saida")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "perfil-windows":
            registro = ler_projetos_host(a.raiz)  # um só: as skills negadas e as pastas de TODOS os projetos (I21)
            perfil = perfil_windows(raiz=a.raiz, python=a.python, projeto=a.projeto, outros_projetos=projetos_da_raiz(
                a.raiz), somente_leitura=a.somente_leitura, backups=a.backups, registro=registro, negar=_sem_repetir(
                [*a.negar_skill, *vagas_do_registro(registro, a.projeto or "-")["negar"]]))
            _entregar(texto_json(perfil), a.saida)
        elif a.cmd in ("gerar-perfil-projeto", "perfil-wsl"):
            existentes = projetos_da_raiz(a.raiz)
            if a.projeto not in existentes:
                raise EntradaInvalida(f"projeto {a.projeto} ausente em {Path(a.raiz) / 'projects'}")
            reg = vagas_do_registro(ler_projetos_host(a.raiz), a.projeto, a.montagem)
            ab = aberturas_da_area(a.raiz, projeto_valido(a.projeto), a.area_raiz)
            perfil = perfil_wsl(raiz=a.raiz, projeto=a.projeto, perfil_windows=a.perfil_windows,
                                outros_projetos=[p for p in existentes if p != a.projeto],
                                somente_leitura=[*reg["somente_leitura"], *a.somente_leitura],
                                ancora_base=a.ancora_base, montagem=a.montagem,
                                negar=_sem_repetir([*reg["negar"], *a.negar_skill]), aberturas=ab,
                                temp_base=a.temp_base, backups=a.backups)
            _entregar(texto_json(perfil), a.saida)
        elif a.cmd == "conferir-perfil-wsl":
            perfil = json.loads(Path(a.perfil).read_text(encoding="utf-8"))
            existentes = projetos_da_raiz(a.raiz)
            problemas = ([] if a.projeto in existentes
                         else [f"projeto {a.projeto} ausente em {Path(a.raiz) / 'projects'}"])
            raiz_wsl = caminho_wsl(a.raiz)
            projeto_valido(a.projeto)
            area = Path(a.area_raiz) / "projetos" / a.projeto
            parametros, avisos = _parametros_confiaveis(a, area)
            reg = vagas_do_registro(ler_projetos_host(a.raiz), a.projeto)
            ab = aberturas_da_area(a.raiz, a.projeto, a.area_raiz)
            ferramentas = None
            if a.lancador:
                m = re.search(r"^FERRAMENTAS='([^']*)'$", Path(a.lancador).read_text(encoding="utf-8"), re.M)
                ferramentas = m.group(1) if m else "(sem FERRAMENTAS no lançador)"
            problemas += conferir_perfil_wsl(perfil, raiz_wsl, a.projeto, [p for p in existentes if p != a.projeto],
                                             parametros=parametros, aberturas=ab, somente_leitura=reg["somente_leitura"],
                                             negar=reg["negar"], ferramentas_lancador=ferramentas)
            try:  # as vagas vão no relatório
                vagas = parametros_do_perfil_wsl(perfil, raiz_wsl, a.projeto)
            except EntradaInvalida:
                vagas = None
            _imprimir({"perfil": a.perfil, "ok": not problemas, "problemas": problemas, "vagas": vagas,
                       "avisos": avisos})
            return 0 if not problemas else 1
        elif a.cmd == "instalar-projeto":
            ensaio = bool(a.area_raiz and a.bin)
            if (a.sonda_interop_cmd or a.sonda_interop_binfmt or a.temp_base or a.gerenciadas
                    or a.ferramenta_base) and not ensaio:
                raise EntradaInvalida("--temp-base, --gerenciadas, --ferramenta-base e as sondas de interoperabilidade "
                                      "são só para ensaio (com --area-raiz e --bin)")
            if a.ferramenta_base and not os.path.isabs(a.ferramenta_base):
                raise EntradaInvalida("--ferramenta-base precisa ser um caminho absoluto")
            relatorio = instalar_projeto(
                simular=a.simular, ensaio=ensaio, raiz=a.raiz, projeto=a.projeto, titular=a.titular, claude=a.claude,
                claude_versao=a.claude_versao, claude_sha256=a.claude_sha256, origem_hash=a.origem_hash,
                perfil_windows=a.perfil_windows, casa=a.casa, usuario=a.usuario, area_raiz=a.area_raiz or AREA_RAIZ,
                bin_dir=a.bin or BIN_DIR, ancora_base=a.ancora_base, temp_base=a.temp_base or TEMP_BASE,
                sonda_interop_cmd=a.sonda_interop_cmd or SONDA_INTEROP_CMD,
                sonda_interop_binfmt=a.sonda_interop_binfmt or SONDA_INTEROP_BINFMT,
                gerenciadas=a.gerenciadas or GERENCIADAS,
                ferramenta_base=(a.ferramenta_base or None) if ensaio else FERRAMENTA_BASE)
            _imprimir(relatorio)
        elif a.cmd == "plano-ferramenta":
            python = None
            if a.python:  # o Python fixado da cópia do Windows, lido sem seguir ligação
                if not PYTHON_WINDOWS.fullmatch(a.python):
                    raise EntradaInvalida(f"--python fora da forma que o kit aceita: {a.python[:120]!r}")
                python = {"caminho": a.python, "sha256": _carregar_script("copia_segura").hash_conferido(
                    a.python)["sha256"]}
            f = plano_da_ferramenta(SKILL, None, python)
            _imprimir({"versao": f["versao"], "hashes_json": f["hashes_bytes"].decode("utf-8"), "sha256": f["sha256"],
                       "arquivos": f["hashes"]["arquivos"]})
        elif a.cmd == "instalar-canario":
            _imprimir(instalar_canario(a.relatorio, a.area_raiz or AREA_RAIZ, ensaio=bool(a.area_raiz),
                                       simular=a.simular))
        elif a.cmd == "conferir-abertura":
            res = conferir_abertura(a.raiz, a.projeto, a.area, limpar=a.limpar)
            if a.texto:
                for linha in res["problemas"]:
                    print("não abre: " + linha)
                for linha in res["avisos"]:
                    print("aviso: " + linha)
                if res["limpos"]:
                    print("marcadores de 0 byte do sandbox limpos: " + ", ".join(res["limpos"]))
            else:
                _imprimir(res)
            return 0 if res["ok"] else 1
        elif a.cmd == "limpar-marcadores":
            _imprimir(limpar_marcadores(a.raiz, a.projeto, a.area))
        elif a.cmd == "limpar-porteiro":
            res = limpar_trabalho_do_porteiro(a.casa, a.raiz, a.projeto)
            if not a.texto:
                _imprimir(res)
            elif res["apagadas"]:
                print("pastas de trabalho de um porteiro encerrado sem limpar (SIGKILL) apagadas: "
                      + ", ".join(res["apagadas"]))
            if a.texto and res["mantidas"]:
                print(f"aviso: pastas de trabalho do porteiro mantidas em {res['pasta']} ({res['motivo']}): "
                      + ", ".join(res["mantidas"]))
        elif a.cmd == "registrar-projeto":
            dados = registrar_projeto(a.raiz, a.projeto, a.origem, a.somente_leitura, a.negar_skill)
            _imprimir({"registro": (Path(a.raiz) / REGISTRO_HOST).as_posix(), "projeto": a.projeto,
                       **dados["projetos"][a.projeto]})
        elif a.cmd == "ler-projetos-host":
            dados = ler_projetos_host(a.raiz)
            if a.projeto:
                projeto_valido(a.projeto)
                dados = {"projeto": a.projeto, "registrado": a.projeto in dados["projetos"],
                         **dados["projetos"].get(a.projeto, {"origens": [], "somente_leitura": [],
                                                             "aninhadas_negadas": []})}
            _imprimir(dados)
        elif a.cmd == "fora-do-registro":
            _imprimir(fora_do_registro(ler_projetos_host(a.raiz), a.somente_leitura, a.negar_skill))
        elif a.cmd == "ultima-copia":
            _imprimir(ultima_copia(a.raiz))
        elif a.cmd == "identidade":
            atual = json.loads(Path(a.atual).read_text(encoding="utf-8-sig")) if a.atual else None
            _entregar(texto_json(identidade(a.titular, atual, a.projeto, estrito=a.estrito, sem_projeto=a.sem_projeto)),
                      a.saida)
        elif a.cmd == "wsl-conf":
            arquivo = Path(a.arquivo)
            atual = arquivo.read_text(encoding="utf-8") if arquivo.is_file() else ""
            novo, mudou = ajustar_wsl_conf(atual)
            if a.saida:
                gravar(a.saida, novo)
            _imprimir({"arquivo": str(arquivo), "existia": arquivo.is_file(), "mudou": mudou, "texto": novo})
        elif a.cmd == "conferir-identidade":
            dados = Path(a.arquivo).read_bytes()
            problemas = conferir_identidade(json.loads(dados.decode("utf-8-sig")), a.titular, a.projeto)
            _imprimir({"arquivo": a.arquivo, "ok": not problemas, "titular": a.titular, "problemas": problemas,
                       "sha256": hashlib.sha256(dados).hexdigest()})
            return 0 if not problemas else 1
    except Conflito as exc:
        _imprimir({"conflito": str(exc)})
        return 1
    except (EntradaInvalida, OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        _imprimir({"erro": str(exc)})
        return 2
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # mesmo texto da --saida, também no Windows
    raise SystemExit(main())
