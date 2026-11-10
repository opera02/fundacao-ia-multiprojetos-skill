"""Preparo da jaula do Criador no Ubuntu (1.7.11, lote L4; DESENHO-JAULA §2.1, §3.4, §7.3 e §7.4).

O que o titular instala, com sudo, para a ficha que abre `navegador` ou `outras_llm` (o `preparo_host.py` o chama; este
módulo é dele e só roda ligado a ele, por `configurar`):
- o usuário de sistema `fundacao-jaula` (sem shell, sem senha, sem casa) e as pastas de estado `/var/lib/fundacao-ia/jaula/
  <projeto>` (dono dele, 0700: o titular não as lê);
- os programas da jaula, de dono root, em `/usr/local/lib/fundacao-ia/jaula/<versão>/`: a entrada fixa, o miolo, o proxy
  de lista, o canário e os módulos de que eles dependem (a lista é conferida contra o código), com o `hashes.json`;
- a sudoers `/etc/sudoers.d/fundacao-jaula` (0440, conferida com `visudo -cf` antes de entrar): UMA linha por projeto e
  modo, com o argv inteiro fixado e SEM curinga. Modo sem linha não existe; só o `canario` ganha linha antes do relatório
  do canário da jaula; os demais, quando o relatório instalado (`instalar-canario-jaula`) aprova o modo e é da mesma
  versão da jaula (SHA-256 da entrada fixa, do proxy e do bwrap), e a ficha tem a seção;
- o `porteiro-jaula.json` do projeto (operações da sessão e tetos), o `canario-instalado.json` e a escolha da forma da
  sudoers (`instalacao.json`).
[medir M1] A forma NOPASSWD só vale se `sudo -n true` FALHAR dentro da sessão (o bwrap liga `no_new_privs`): o preparo só a usa
com o item `sudo_na_sessao` = `passou` no relatório do canário do Ubuntu instalado (F5); sem isso (ou com `--sudo-senha`) a
sudoers sai sem NOPASSWD e o lançador pede a senha uma vez por sessão. O relatório do canário da jaula só se instala se for
byte a byte a cópia que a entrada fixa guardou no estado da jaula (F3), e o `codex-exec` (o Codex da sessão) só abre com a chave
de API, nunca com a conta do ChatGPT (F1).
O `instalar_jaula` não baixa nada. Os downloads do navegador (apt da lista fixa e acl, Playwright pelo pip com hashes,
Chromium do Playwright) são do `instalar_navegador_jaula` (lote L5), que o preparar-wsl.sh mostra ANTES com endereço e
tamanho; os pacotes do pip têm SHA-256 fixados no arquivo de travas e só a árvore do Chromium fica em confiança no
primeiro uso (rotulado). O Codex (L6) tem o seu: o `instalar_codex_jaula` baixa o CLI fixado em `pins-codex.json`, confere
o tamanho e o SHA-256 ANTES de instalar e recusa se não baterem. Os lançadores do titular `abrir-navegador-<p>` (login e
captcha) e `abrir-codex-<p>` (terminal do Codex e `--login`) são instalados junto com a sudoers, quando o canário aprova o
modo. Só biblioteca padrão.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple

AQUI = Path(__file__).resolve().parent
SKILL = AQUI.parent.parent
SCRIPTS = SKILL / "scripts"
H = None  # o preparo_host (EntradaInvalida e afins): ligado por `configurar`
_CACHE: dict = {}
SUDOERS_NOME = "fundacao-jaula"
ESQUEMA_INSTALADA = "fundacao.jaula_instalada/1"
ESQUEMA_INSTALACAO = "fundacao.jaula_instalacao/1"
FORMAS_DO_SUDO = ("nopasswd", "senha")
USUARIO_LINUX = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
PROJETO_PADRAO = "[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?"
BINARIOS = (("/usr/bin/bwrap", "bubblewrap"), ("/usr/bin/socat", "socat"))
VISUDO = "/usr/sbin/visudo"
USERADD = "/usr/sbin/useradd"
RUNUSER = "/usr/sbin/runuser"
# O que a jaula carrega de dentro da pasta dela (`jaula.py` procura os irmãos ao lado dele): (origem na skill, modo). A
# lista é conferida contra o código por teste (o fecho dos módulos que o jaula.py, o proxy e o canário carregam).
ARQUIVOS_DA_JAULA = (
    ("assets/host/wsl/jaula-entrar", 0o755), ("assets/host/wsl/jaula.py", 0o644),
    ("assets/host/wsl/proxy_lista.py", 0o644), ("assets/host/wsl/dominios_ficha.py", 0o644),
    ("assets/host/wsl/canario_jaula.py", 0o644), ("assets/host/wsl/chromium-sem-disfarce", 0o755),
    ("assets/host/wsl/codex-config.toml", 0o644), ("assets/host/wsl/pins-codex.json", 0o644),
    ("scripts/navegador.py", 0o644), ("scripts/execucao_isolada.py", 0o644), ("scripts/codigo_do_plano.py", 0o644), ("scripts/manifesto.py", 0o644),
    ("scripts/perfil_execucao.py", 0o644), ("scripts/regras_de_segredo.py", 0o644),
    ("scripts/gravacao_segura.py", 0o644), ("scripts/segredos.py", 0o644), ("scripts/copia_segura.py", 0o644))
ITENS_DO_CANARIO = ("sockets_visiveis", "socket_abstrato", "rede_direta", "proxy_lista", "proxy_fora", "proxy_ip",
                    "proxy_local", "proxy_sni", "proxy_porta", "proc", "fora_montado", "escrita", "capacidades",
                    "tiocsti", "userns", "ambiente")
ITEM_DO_CODEX = "segredo_da_jaula_invisivel"
ITEM_M7_DO_CODEX = "sandbox_codex"   # a sonda M7 do canário do Codex (informativa; vira a medida sandbox_codex)
APELIDO_NO_PEDIDO = {"navegador": "nav", "navegador-janela:login": "janela-login",
                     "navegador-janela:captcha": "janela-captcha", "codex-exec": "cdx-exec",
                     "codex-titular": "cdx-titular"}


class Caminhos(NamedTuple):
    """Onde a jaula se instala. Os reais por padrão; o ensaio (sem root) os põe sob uma pasta."""
    programas: str
    estado: str
    etc: str          # a área do titular (/etc/fundacao-ia): projetos/<p>/ e jaula/
    sudoers: str
    bwrap: str = "/usr/bin/bwrap"
    ensaio: bool = False
    bin: str = "/usr/local/bin"  # os lançadores do titular (abrir-navegador-<p>), de dono root


class _Erro(ValueError):
    pass


def erro(mensagem: str) -> Exception:
    return (H.EntradaInvalida if H is not None else _Erro)(mensagem)


def configurar(host) -> None:
    """Liga o módulo ao preparo_host (a classe de erro que o main dele trata)."""
    global H
    H = host


def _carregar(chave: str, caminho: Path):
    if chave not in _CACHE:
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location(f"_preparo_jaula_{chave}", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        _CACHE[chave] = modulo
    return _CACHE[chave]


def jaula():
    """O `jaula.py` desta cópia da skill: a única fonte da versão, do usuário, dos caminhos e do esquema do relatório."""
    return _carregar("jaula", AQUI / "wsl" / "jaula.py")


def porteiro_jaula():
    return _carregar("porteiro_jaula", AQUI / "wsl" / "porteiro_jaula.py")


def _script(nome: str):
    return _carregar("script_" + nome, SCRIPTS / f"{nome}.py")


def caminhos_reais(etc: str = "/etc/fundacao-ia") -> Caminhos:
    j = jaula()
    return Caminhos(f"{j.PROGRAMAS}/{j.VERSAO_JAULA}", j.ESTADO, etc, f"/etc/sudoers.d/{SUDOERS_NOME}", j.Config().bwrap)


def programas_da_jaula(jaula_base: str | None = None) -> str:
    """Onde os programas ficam: o real, ou (ensaio) sob `jaula_base` com a versão da jaula."""
    j = jaula()
    return f"{(j.PROGRAMAS if jaula_base is None else jaula_base.rstrip('/'))}/{j.VERSAO_JAULA}"


def caminhos_de_ensaio(base, etc) -> Caminhos:
    """Tudo sob `base` (sem root): programas, estado e sudoers de mentira; a área do titular é a `etc` dada."""
    base = Path(os.path.abspath(base))
    j = jaula()
    return Caminhos((base / "programas" / j.VERSAO_JAULA).as_posix(), (base / "estado").as_posix(),
                    Path(os.path.abspath(etc)).as_posix(), (base / "sudoers.d" / SUDOERS_NOME).as_posix(),
                    (base / "bwrap").as_posix(), True, (base / "bin").as_posix())


# --- leitura e hashes ----------------------------------------------------------------------------------------------
def _sha(caminho) -> str:
    return _script("copia_segura").hash_conferido(caminho)["sha256"]


def _sha_ou_none(caminho) -> str | None:
    try:
        return _sha(caminho)
    except OSError:
        return None


def _ler_json(arquivo, teto: int = 1 << 20):
    cs = _script("copia_segura")
    fd = cs.abrir_comum(arquivo)
    try:
        partes, total = [], 0
        while total <= teto and (bloco := os.read(fd, 1 << 16)):
            partes.append(bloco)
            total += len(bloco)
    finally:
        os.close(fd)
    if total > teto:
        raise erro(f"{Path(arquivo).name} acima do teto de {teto} bytes")
    try:
        return jaula().carregar_estrito(b"".join(partes))
    except ValueError as exc:
        raise erro(f"{Path(arquivo).name} ilegível: {exc}") from None


def texto_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


# --- o que a ficha abre --------------------------------------------------------------------------------------------
def _secao_navegador(ab):
    n = ab.get("navegador") if isinstance(ab, dict) else None
    return n if isinstance(n, dict) and n.get("dominios") and n.get("modos") else None


def _item_codex(ab):
    lista = ab.get("outras_llm") if isinstance(ab, dict) else None
    return lista[0] if isinstance(lista, list) and len(lista) == 1 and isinstance(lista[0], dict) \
        and lista[0].get("modos") else None


def modos_da_ficha(ab) -> list[str]:
    """Os modos da JAULA que a ficha aplicada abre (navegador, navegador-janela, codex-exec, codex-titular), na ordem
    fixa. Sem a seção, nenhum: nada de jaula para o projeto."""
    modos = []
    n, c = _secao_navegador(ab), _item_codex(ab)
    if n and "sessao" in n["modos"]:
        modos.append("navegador")
    if n and {"login", "captcha"} & set(n["modos"]):
        modos.append("navegador-janela")
    if c and c.get("provedor") == "openai-codex" and "exec" in c["modos"]:
        modos.append("codex-exec")
    if c and c.get("provedor") == "openai-codex" and "titular" in c["modos"]:
        modos.append("codex-titular")
    return modos


def chaves_do_portao(ab, modo: str) -> list[str]:
    """As chaves do relatório instalado (`modos` do canario-instalado.json) que o modo exige da ficha."""
    if modo == "navegador-janela":
        return [f"navegador-janela:{v}" for v in ("login", "captcha") if v in _secao_navegador(ab)["modos"]]
    return [modo]


def codex_exec_fechado_pela_conta(ab) -> bool:
    """F1 (revisão de segurança da 1.7.11): a ficha pede o `codex-exec` (o Codex da sessão) e a autenticação não é a chave de
    API. Com a conta do ChatGPT o login fica no CODEX_HOME da jaula, ao alcance de um comando que o Codex rode a pedido da
    sessão: o modo não abre (nem a operação `codex` da sessão, nem a linha da sudoers). A TUI do titular segue com a conta."""
    return "codex-exec" in modos_da_ficha(ab) and not jaula().codex_exec_aberto_pela_ficha(ab)


def operacoes_da_sessao(ab) -> dict:
    """As operações que a SESSÃO pede ao porteiro da jaula: `navegador` (modo da sessão) e `codex` (exec, com o teto por
    dia da ficha; só com a chave de API, ver `codex_exec_fechado_pela_conta`). As janelas e a TUI são só dos lançadores do
    titular."""
    modos, ops = modos_da_ficha(ab), {}
    if "navegador" in modos:
        ops["navegador"] = {}
    if "codex-exec" in modos and not codex_exec_fechado_pela_conta(ab):
        ops["codex"] = {"teto_chamadas_dia": _item_codex(ab)["teto_chamadas_dia"]}
    return ops


def config_do_porteiro(raiz_wsl: str, projeto: str, ab, programas: str) -> dict | None:
    """O conteúdo do `porteiro-jaula.json` da área do projeto, ou None (a ficha não tem seção de jaula: nada é gravado e
    o lançador não sobe nada). Com a seção e sem operação para a sessão, as operações ficam vazias: a configuração
    existe (a entrada fixa lê a raiz dela), mas o lançador não sobe o porteiro."""
    if not modos_da_ficha(ab):
        return None
    pj = porteiro_jaula()
    return {"schema_version": pj.SCHEMA, "raiz": raiz_wsl, "projeto": projeto, "usuario_jaula": jaula().USUARIO,
            "entrada": f"{programas}/jaula-entrar", "operacoes": operacoes_da_sessao(ab)}


def aplicar_jaula_no_perfil(perfil: dict, proj: str, ab) -> dict:
    """O que a sessão com operações de jaula muda no perfil: a pasta `respostas` da fila da jaula não é gravável por ela
    (só o porteiro da jaula responde), como a do porteiro da fundação. Sem operação para a sessão, nada muda."""
    if not operacoes_da_sessao(ab):
        return perfil
    alvo = f"{proj}/.porteiro/jaula/respostas"
    perm = perfil.setdefault("permissions", {})
    perm["deny"] = [*(perm.get("deny") or []), f"Edit(/{alvo}/**)"]
    fs = perfil.setdefault("sandbox", {}).setdefault("filesystem", {})
    fs["denyWrite"] = [*(fs.get("denyWrite") or []), alvo]
    return perfil


def problemas_do_perfil(perfil, proj: str, ab) -> list[str]:
    """Invariante do perfil: com operações de jaula para a sessão, as respostas da fila da jaula ficam não graváveis."""
    if not operacoes_da_sessao(ab):
        return []
    alvo = f"{proj}/.porteiro/jaula/respostas"
    perfil = perfil if isinstance(perfil, dict) else {}
    deny = ((perfil.get("permissions") or {}).get("deny")) or []
    negados = (((perfil.get("sandbox") or {}).get("filesystem") or {}).get("denyWrite")) or []
    saida = []
    if alvo not in negados:
        saida.append("respostas da fila da jaula gravável pelo sandbox (falta em denyWrite)")
    if f"Edit(/{alvo}/**)" not in deny:
        saida.append("respostas da fila da jaula editáveis pela ferramenta Edit (falta em permissions.deny)")
    return saida


# --- programas da jaula ----------------------------------------------------------------------------------------------
def fontes_da_jaula(skill) -> list[dict]:
    """Os arquivos que serão instalados, com o SHA-256 lido da skill pelo caminho conferido (sem ligação nem vínculo)."""
    skill, saida = Path(skill), []
    for rel, modo in ARQUIVOS_DA_JAULA:
        origem = skill.joinpath(*rel.split("/"))
        try:
            m = _script("copia_segura").hash_conferido(origem)
        except OSError as exc:
            raise erro(f"a skill não tem {rel} legível ({exc.strerror or exc}): atualize a skill instalada") from None
        saida.append({"origem": origem, "nome": origem.name, "modo": modo, "sha256": m["sha256"], "bytes": m["bytes"]})
    return saida


def registro_da_jaula(skill, ab, programas: str) -> dict | None:
    """O que o hashes.json do projeto fixa da jaula (o lançador o reconfere na abertura): onde ficam os programas e o
    SHA-256 de cada um. None sem seção de jaula (a chave nem entra no hashes.json)."""
    if not modos_da_ficha(ab):
        return None
    return {"versao": jaula().VERSAO_JAULA, "programas": programas,
            "arquivos": {f["nome"]: f["sha256"] for f in fontes_da_jaula(skill)}, "modos": modos_da_ficha(ab),
            "operacoes": sorted(operacoes_da_sessao(ab))}


def problemas_da_abertura(hashes, sha_de) -> list[str]:
    """Na abertura da sessão (como o titular): a jaula instalada é a que o preparo do projeto fixou. `sha_de(caminho)`
    devolve o SHA-256 ou um texto com o motivo. Sem a chave `jaula`, nada a conferir."""
    registro = hashes.get("jaula") if isinstance(hashes, dict) else None
    if registro is None:
        return []
    programas, arquivos = (registro.get("programas"), registro.get("arquivos")) if isinstance(registro, dict) \
        else (None, None)
    if not isinstance(programas, str) or not os.path.isabs(programas) or not isinstance(arquivos, dict) or not arquivos:
        return ["jaula: o registro do hashes.json está fora da forma (rode de novo o preparar-wsl.sh)"]
    problemas = []
    for nome, esperado in sorted(arquivos.items()):
        atual = sha_de(Path(programas) / str(nome))
        if atual != esperado:
            problemas.append(f"jaula: {programas}/{nome} difere do preparo (esperado {str(esperado)[:12]}..., encontrado "
                             f"{str(atual)[:40]}): instale a jaula de novo (preparar-wsl.sh, com sudo)")
    return problemas


# --- sudoers -------------------------------------------------------------------------------------------------------
def escapar_sudoers(texto: str) -> str:
    """Caracteres que a sudoers lê de outro jeito (vírgula, dois-pontos, igual, barra invertida e espaço) levam barra
    invertida; nenhum nome da jaula tem esses (o caminho de ensaio pode ter)."""
    return re.sub(r"([,:=\\ ])", r"\\\1", texto)


def linhas_do_sudoers(titular: str, programas: str, pares: list[tuple[str, str]], forma: str) -> list[str]:
    """Uma linha por (projeto, modo), argv inteiro fixado. `forma`: nopasswd ou senha [medir M1]."""
    if forma not in FORMAS_DO_SUDO:
        raise erro(f"forma da sudoers desconhecida: {forma!r}")
    entrada = escapar_sudoers(f"{programas}/jaula-entrar")
    etiqueta = "NOPASSWD: " if forma == "nopasswd" else ""
    return [f"{titular} ALL=({jaula().USUARIO}) {etiqueta}{entrada} {projeto} {modo}" for projeto, modo in pares]


def texto_do_sudoers(titular: str, programas: str, pares: list[tuple[str, str]], forma: str) -> str:
    """O arquivo inteiro, ou "" sem nenhuma linha (então o arquivo existente sai)."""
    if not pares:
        return ""
    entrada = escapar_sudoers(f"{programas}/jaula-entrar")
    cabeca = ["# Gerado pelo preparo da fundacao (fundacao-ia-multiprojetos, jaula): nao edite; rode o preparar-wsl.sh.",
              "# Uma linha por projeto e modo, com o argv inteiro fixado e SEM curinga. [medir M1] A forma NOPASSWD so vale se",
              "# `sudo -n true` falhar dentro da sessao (no_new_privs do bwrap); senao, o preparo usa a forma com senha.",
              f"Defaults!{entrada} env_reset,!setenv,closefrom=3"]
    return "\n".join([*cabeca, *linhas_do_sudoers(titular, programas, sorted(set(pares)), forma)]) + "\n"


def problemas_do_texto_do_sudoers(texto: str, titular: str, programas: str) -> list[str]:
    """Confere o arquivo da sudoers ANTES do `visudo`: só as duas formas de linha permitidas, sem curinga, sem `ALL` no
    lugar do comando, sem continuação de linha, com o argv inteiro de um modo da jaula."""
    j = jaula()
    entrada = re.escape(escapar_sudoers(f"{programas}/jaula-entrar"))
    modos = "|".join(re.escape(m) for m in j.MODOS)
    regra = (re.escape(titular) + r" ALL=\(" + re.escape(j.USUARIO) + r"\) (?:NOPASSWD: )?" + entrada + " "
             + PROJETO_PADRAO + " (?:" + modos + ")")
    padroes = (re.compile("Defaults!" + entrada + " env_reset,!setenv,closefrom=3"), re.compile(regra))
    problemas, linhas_de_regra = [], 0
    for numero, linha in enumerate(texto.split("\n"), 1):
        if not linha.strip() or linha.startswith("#"):
            continue
        if "\r" in linha or "\\\n" in linha or linha.endswith("\\") or any(c in linha for c in "*?[]"):
            problemas.append(f"sudoers, linha {numero}: curinga, continuação ou caractere de controle")
        elif not any(p.fullmatch(linha) for p in padroes):
            problemas.append(f"sudoers, linha {numero}: fora das duas formas permitidas (Defaults da entrada fixa e a "
                             "regra de um projeto e modo com o argv inteiro)")
        elif not linha.startswith("Defaults!"):
            linhas_de_regra += 1
    if linhas_de_regra == 0 and not problemas:
        problemas.append("sudoers sem nenhuma regra de projeto e modo")
    return problemas


def modos_abertos(ab, relatorio, hashes_previstos: dict | None) -> tuple[list[str], dict]:
    """(modos que ganham linha na sudoers, {modo fechado: motivo}) para a ficha e o relatório instalado. O `canario` é de
    todo projeto com seção. Os outros: a ficha tem a seção E o relatório aprova o modo E é da mesma versão da jaula."""
    j = jaula()
    modos = modos_da_ficha(ab)
    if not modos:
        return [], {}
    abertos, fechados = ["canario"], {}
    for modo in modos:
        if modo == "codex-exec" and codex_exec_fechado_pela_conta(ab):  # F1: nem a linha da sudoers, qualquer que seja o canário
            fechados[modo] = j.MOTIVO_CODEX_EXEC_COM_CONTA
            continue
        if not isinstance(relatorio, dict) or relatorio.get("schema_version") != j.ESQUEMA_RELATORIO_INSTALADO:
            fechados[modo] = "falta o relatório do canário da jaula instalado (instalar-canario-jaula)"
            continue
        gravados = relatorio.get("hashes")
        if not hashes_previstos or not isinstance(gravados, dict) or any(
                gravados.get(k) != v for k, v in hashes_previstos.items()):
            fechados[modo] = "o relatório do canário é de outra versão da jaula (entrada fixa, proxy ou bwrap mudaram)"
            continue
        aprovados = relatorio.get("modos") if isinstance(relatorio.get("modos"), dict) else {}
        ok = [c for c in chaves_do_portao(ab, modo) if isinstance(aprovados.get(c), dict)
              and aprovados[c].get("aprovado") is True]
        if not ok:
            fechados[modo] = "o canário da jaula não aprovou o modo"
            continue
        abertos.append(modo)
    return abertos, fechados


def hashes_previstos(fontes: list[dict], bwrap: str) -> dict | None:
    """O que `jaula.hashes_da_instalacao` calculará com os programas instalados: a entrada fixa, o proxy e o bwrap."""
    por_nome = {f["nome"]: f["sha256"] for f in fontes}
    bw = _sha_ou_none(bwrap)
    if bw is None:
        return None
    return {"jaula-entrar": por_nome["jaula-entrar"], "proxy_lista.py": por_nome["proxy_lista.py"], "bwrap": bw}


# --- o plano -------------------------------------------------------------------------------------------------------
def projeto_da_area(area_raiz, projeto: str) -> dict | None:
    """O projeto como o `instalar-projeto` o deixou na área do titular, conferido pelo hashes.json. None: a área não tem
    seção de jaula para ele. Incoerência (porteiro-jaula.json faltando ou diferente, hash que não bate): erro."""
    area = Path(area_raiz) / "projetos" / projeto
    if not (area / "aberturas.json").is_file():
        return None
    ab = _ler_json(area / "aberturas.json")
    if not isinstance(ab, dict) or ab.get("projeto") != projeto:
        raise erro(f"{projeto}: aberturas.json da área é de outro projeto")
    modos = modos_da_ficha(ab)
    if not modos:
        return None
    hashes = _ler_json(area / "hashes.json", 8 << 20)
    arquivos = hashes.get("arquivos") if isinstance(hashes, dict) else None
    if not isinstance(arquivos, dict) or hashes.get("projeto") != projeto:
        raise erro(f"{projeto}: hashes.json da área ausente, ilegível ou de outro projeto")
    for nome in ("aberturas.json", "porteiro-jaula.json"):
        alvo = (area / nome).as_posix()
        if arquivos.get(alvo) != _sha_ou_none(area / nome):
            raise erro(f"{projeto}: {nome} não confere com o hashes.json (ou falta): rode de novo o preparo do projeto "
                       "(instalar-projeto) antes de instalar a jaula")
    conf = _ler_json(area / "porteiro-jaula.json")
    pj = porteiro_jaula()
    try:
        pj.validar_config(conf)
    except pj.Recusa as exc:
        raise erro(f"{projeto}: porteiro-jaula.json recusado: {exc}") from None
    if conf["projeto"] != projeto or conf["operacoes"] != operacoes_da_sessao(ab):
        raise erro(f"{projeto}: porteiro-jaula.json não corresponde à ficha aplicada: rode de novo o instalar-projeto")
    return {"projeto": projeto, "ab": ab, "modos": modos, "usuario": hashes.get("usuario"), "entrada": conf["entrada"],
            "raiz": conf["raiz"], "operacoes": sorted(conf["operacoes"]),
            "claude_versao": (hashes.get("claude") or {}).get("versao") if isinstance(hashes.get("claude"), dict) else None}


VERSAO_DO_CLAUDE = re.compile(r"[0-9][0-9A-Za-z._+-]{0,39}\Z")


def sudo_na_sessao_passou(etc, claude_versao) -> bool:
    """F5 (revisão de segurança da 1.7.11): a medida M1 (`sudo_na_sessao`) passou no canário do Ubuntu INSTALADO para a versão do
    Claude Code do projeto (`<etc>/canario/<versão>.json`, de dono root, instalado pelo `instalar-canario`). Só então o sudo
    sem senha vale; a medida que falhou, não foi medida ou falta (o relatório, o item, a versão) deixa a forma com senha. O
    relatório tem de ter a estrutura de um ensaio real (a regra do kit), não só o item."""
    if not isinstance(claude_versao, str) or not VERSAO_DO_CLAUDE.fullmatch(claude_versao):
        return False
    try:
        rel = _ler_json(Path(etc) / "canario" / f"{claude_versao}.json", 8 << 20)
        if H is not None and H.estrutura_do_relatorio_do_canario(rel) is not None:
            return False
    except Exception:  # noqa: BLE001 — ausente, ilegível ou fora da forma: a medida não passou
        return False
    itens = rel.get("itens") if isinstance(rel, dict) else None
    return isinstance(itens, list) and any(isinstance(i, dict) and i.get("id") == "sudo_na_sessao"
                                           and i.get("veredito") == "passou" for i in itens)


def _estado(destino: Path, esperado: str | None) -> str:
    if not os.path.lexists(destino):
        return "criar"
    return "igual" if esperado is not None and _sha_ou_none(destino) == esperado else "atualizar"


def montar_plano(skill, area_raiz, projetos: list[str], usuario: str, caminhos: Caminhos, *, forma_sudo: str = "nopasswd",
                 preparar: bool = False, ver_binarios: bool = True) -> dict:
    """Tudo o que `instalar_jaula` faz, calculado sem gravar nada. `projetos`: os da linha de comando (a área deles já
    tem de estar gravada pelo instalar-projeto). Sem seção de jaula em nenhum e sem `preparar`: `necessaria` falso."""
    if not USUARIO_LINUX.match(str(usuario)) or usuario in ("root", jaula().USUARIO):
        raise erro(f"usuário do Linux do titular inválido para a sudoers: {usuario!r}")
    if forma_sudo not in FORMAS_DO_SUDO:
        raise erro(f"forma da sudoers desconhecida: {forma_sudo!r}")
    j = jaula()
    with_jaula, sem, sem_area = [], [], []
    for p in sorted(set(projetos)):
        if not (Path(area_raiz) / "projetos" / p / "aberturas.json").is_file():
            sem_area.append(p)
            continue
        info = projeto_da_area(area_raiz, p)
        if info is None:
            sem.append(p)
            continue
        if info["usuario"] != usuario:
            raise erro(f"{p}: a área foi preparada para o usuário {info['usuario']!r}, não para {usuario!r}")
        if info["entrada"] != f"{caminhos.programas}/jaula-entrar":
            raise erro(f"{p}: o porteiro-jaula.json aponta para outra entrada fixa ({info['entrada']}): rode de novo o "
                       "instalar-projeto")
        with_jaula.append(info)
    necessaria = bool(with_jaula) or preparar
    forma_pedida, motivo_da_forma = forma_sudo, None
    if forma_sudo == "nopasswd":   # F5: sem a medida M1 aprovada pelo canário do Ubuntu, vale o sudo com senha (§10.3, alt. 1)
        sem_m1 = [i["projeto"] for i in with_jaula if not sudo_na_sessao_passou(caminhos.etc, i.get("claude_versao"))]
        if sem_m1 or not with_jaula:
            forma_sudo = "senha"
            motivo_da_forma = ("a medida M1 (sudo_na_sessao) não passou no canário do Ubuntu instalado"
                               + (f" para {', '.join(sem_m1)}" if sem_m1 else "")
                               + ": o sudo sem senha só vale se `sudo -n true` falhar dentro da sessão")
    fontes = fontes_da_jaula(skill) if necessaria else []  # sem jaula para ninguém, a skill nem precisa tê-la inteira
    previstos = hashes_previstos(fontes, caminhos.bwrap) if fontes else None
    relatorio = None
    caminho_rel = Path(caminhos.etc) / j.RELATORIO_INSTALADO
    if necessaria and caminho_rel.is_file():
        try:
            relatorio = _ler_json(caminho_rel)
        except Exception:  # noqa: BLE001 — relatório ilegível: o mesmo que ausente (os modos ficam fechados)
            relatorio = None
    pares, projetos_plano, lancadores = [], [], []
    for info in with_jaula:
        abertos, fechados = modos_abertos(info["ab"], relatorio, previstos)
        pares += [(info["projeto"], m) for m in abertos]
        projetos_plano.append({"projeto": info["projeto"], "modos_da_ficha": info["modos"], "abertos": abertos,
                               "fechados": fechados, "operacoes_da_sessao": info["operacoes"]})
        if "navegador-janela" in info["modos"]:  # o lançador do titular (L5): só existe com o modo aberto pelo canário
            lancadores.append(lancador_do_navegador(info["projeto"], caminhos, "navegador-janela" in abertos, relatorio))
        if "codex-titular" in info["modos"]:  # o do Codex (L6): entra no plano quando abre, ou para sair se já existe e fechou
            lc = lancador_do_codex(info["projeto"], caminhos, "codex-titular" in abertos)
            if lc["abrir"] or os.path.lexists(lc["caminho"]):
                lancadores.append(lc)
    texto = texto_do_sudoers(usuario, caminhos.programas, pares, forma_sudo)
    problemas = problemas_do_texto_do_sudoers(texto, usuario, caminhos.programas) if texto else []
    if problemas:
        raise erro("; ".join(problemas))
    itens = [{"origem": f["origem"].as_posix(), "destino": f"{caminhos.programas}/{f['nome']}", "modo": f["modo"],
              "sha256": f["sha256"], "bytes": f["bytes"],
              "estado": _estado(Path(caminhos.programas) / f["nome"], f["sha256"])} for f in fontes]
    pastas = [{"caminho": caminhos.estado, "dono": "root", "modo": "0755"}] + [
        {"caminho": f"{caminhos.estado}/{i['projeto']}", "dono": j.USUARIO, "modo": "0700"} for i in with_jaula]
    if not necessaria:
        pastas = []
    return {"necessaria": necessaria, "versao": j.VERSAO_JAULA, "usuario_jaula": j.USUARIO, "titular": usuario,
            "sudo": forma_sudo, "sudo_pedido": forma_pedida, "sudo_motivo": motivo_da_forma, "caminhos": caminhos._asdict(), "projetos": projetos_plano, "sem_jaula": sem, "sem_area": sem_area,
            "arquivos": itens, "pastas": pastas, "pares": pares, "sudoers": texto, "lancadores": lancadores,
            "navegador": preparar or any(m.startswith("navegador") for i in with_jaula for m in i["modos"]),
            "codex": preparar or any(m.startswith("codex") for i in with_jaula for m in i["modos"]),
            "relatorio_instalado": relatorio
            is not None, "hashes_previstos": previstos, "binarios": [] if not ver_binarios or caminhos.ensaio
            else [{"caminho": c, "pacote": p} for c, p in BINARIOS], "_fontes": fontes, "_infos": with_jaula,
            "comandos_do_canario": comandos_do_canario(with_jaula, caminhos, previstos, relatorio)}


def comandos_do_canario(infos: list[dict], caminhos: Caminhos, previstos, relatorio) -> list[dict]:
    """Para cada chave do portão que ainda não vale, o comando pronto que o titular cola no terminal do Ubuntu: o pedido do
    canário pela entrada padrão da entrada fixa (a sudoers tem a linha `canario`), a resposta num arquivo que o
    `--canario-jaula` instala. Os nomes de domínio são só os da ficha (a entrada fixa recusa os de fora)."""
    j = jaula()
    saida, aprovados = [], (relatorio.get("modos") if isinstance(relatorio, dict) and isinstance(relatorio.get("modos"),
                            dict) else {})
    validos = bool(previstos) and isinstance(relatorio, dict) and all(
        (relatorio.get("hashes") or {}).get(k) == v for k, v in (previstos or {}).items())
    for info in infos:
        ab = info["ab"]
        for modo in info["modos"]:
            como = modo
            if modo == "codex-exec" and codex_exec_fechado_pela_conta(ab):
                continue   # F1: o modo fechado pela conta não ganha comando de canário
            for chave in chaves_do_portao(ab, modo):
                if validos and isinstance(aprovados.get(chave), dict) and aprovados[chave].get("aprovado") is True:
                    continue
                variante = chave.split(":", 1)[1] if ":" in chave else None
                if como.startswith("navegador"):
                    dominios = list(_secao_navegador(ab)["dominios"])[:3]
                else:
                    dominios = list(j.CODEX_DOMINIOS[_item_codex(ab)["autenticacao"]])
                corpo = {"schema_version": j.ESQUEMA_PEDIDO, "id": "canario-" + APELIDO_NO_PEDIDO[chave] + "-%s",
                         "como": como, **({"variante": variante} if variante else {}), "dominios": dominios}
                arquivo = f"canario-{info['projeto']}-{APELIDO_NO_PEDIDO[chave]}.json"
                comando = (f"printf '{json.dumps(corpo, ensure_ascii=False, separators=(',', ':'))}' \"$(date +%s)\" | "
                           f"/usr/bin/sudo -u {j.USUARIO} {caminhos.programas}/jaula-entrar {info['projeto']} canario > "
                           f"{arquivo}")
                saida.append({"projeto": info["projeto"], "chave": chave, "arquivo": arquivo, "comando": comando})
    return saida


MARCA_DO_LANCADOR = "Lançador da janela do navegador do projeto"
LANCADOR_MODELO = AQUI / "wsl" / "abrir-navegador.py"
CAMINHO_SEM_ASPAS = re.compile(r"[^'\\\x00-\x1f\x7f]+\Z")  # vai entre aspas simples no modelo: sem aspa, barra invertida nem controle


def texto_do_lancador(projeto: str, programas: str, grafico: str) -> str:
    """O `abrir-navegador-<projeto>`: o modelo da skill com os valores FIXOS (nada vem do ambiente). O lançador só monta
    o pedido de campos fechados da janela do titular (login ou captcha) e o entrega à entrada fixa pelo sudoers."""
    j = jaula()
    if not re.fullmatch(PROJETO_PADRAO, projeto) or "--" in projeto:
        raise erro(f"projeto inválido para o lançador: {projeto!r}")
    if grafico not in j.GRAFICOS_ESCOLHIVEIS:
        raise erro(f"opção gráfica desconhecida: {grafico!r}")
    valores = {"PROJETO": projeto, "ENTRADA": f"{programas}/jaula-entrar", "USUARIO_DA_JAULA": j.USUARIO, "GRAFICO": grafico,
              "WAYLAND": j.WAYLAND_DO_WSLG}
    if not all(CAMINHO_SEM_ASPAS.fullmatch(v) for v in valores.values()):
        raise erro("valor do lançador com aspa, barra invertida ou caractere de controle")
    texto = LANCADOR_MODELO.read_text(encoding="utf-8")
    for nome, valor in valores.items():
        texto = texto.replace("{{" + nome + "}}", valor)
    if "{{" in texto or "\r" in texto:
        raise erro("o modelo do lançador do navegador tem marcador sem valor ou fim de linha CRLF")
    return texto


def lancador_do_navegador(projeto: str, caminhos: Caminhos, aberto: bool, relatorio) -> dict:
    """{projeto, caminho, abrir, texto, sha256}: `abrir` falso quando o canário ainda não abriu a janela (o lançador sai)."""
    grafico = jaula().medidas_do_modo(relatorio, "navegador-janela", "login")["grafico"]
    texto = texto_do_lancador(projeto, caminhos.programas, grafico) if aberto else ""
    return {"projeto": projeto, "caminho": f"{caminhos.bin}/abrir-navegador-{projeto}", "abrir": aberto, "texto": texto,
            "sha256": hashlib.sha256(texto.encode("utf-8")).hexdigest() if aberto else None}


MARCA_DO_LANCADOR_CODEX = "Lançador do Codex do projeto"
LANCADOR_CODEX_MODELO = AQUI / "wsl" / "abrir-codex.py"


def texto_do_lancador_codex(projeto: str, programas: str) -> str:
    """O `abrir-codex-<projeto>`: o modelo da skill com os valores FIXOS (nada vem do ambiente). Só monta o pedido fechado
    (terminal do Codex ou `--login`) e o entrega à entrada fixa pelo sudoers; o rótulo do risco da conta é o do `jaula.py`."""
    j = jaula()
    if not re.fullmatch(PROJETO_PADRAO, projeto) or "--" in projeto:
        raise erro(f"projeto inválido para o lançador: {projeto!r}")
    valores = {"PROJETO": projeto, "ENTRADA": f"{programas}/jaula-entrar", "USUARIO_DA_JAULA": j.USUARIO,
               "ROTULO": j.ROTULO_DO_CODEX_CONTA}
    if not all(CAMINHO_SEM_ASPAS.fullmatch(v) for v in valores.values()):
        raise erro("valor do lançador com aspa, barra invertida ou caractere de controle")
    texto = LANCADOR_CODEX_MODELO.read_text(encoding="utf-8")
    for nome, valor in valores.items():
        texto = texto.replace("{{" + nome + "}}", valor)
    if "{{" in texto or chr(13) in texto:
        raise erro("o modelo do lançador do Codex tem marcador sem valor ou fim de linha CRLF")
    return texto


def lancador_do_codex(projeto: str, caminhos: Caminhos, aberto: bool) -> dict:
    """Como `lancador_do_navegador`: `abrir` falso quando o canário ainda não abriu o modo do titular (o lançador sai)."""
    texto = texto_do_lancador_codex(projeto, caminhos.programas) if aberto else ""
    return {"projeto": projeto, "caminho": f"{caminhos.bin}/abrir-codex-{projeto}", "abrir": aberto, "texto": texto,
            "sha256": hashlib.sha256(texto.encode("utf-8")).hexdigest() if aberto else None}


def _instalar_lancador(l: dict, root) -> dict:
    destino = Path(l["caminho"])
    item = f"lancador:{destino.name}"
    marca = MARCA_DO_LANCADOR_CODEX if destino.name.startswith("abrir-codex-") else MARCA_DO_LANCADOR
    if not l["abrir"]:  # só sai o que o preparo gerou (a marca do modelo)
        if os.path.lexists(destino) and marca in destino.read_text(encoding="utf-8", errors="replace"):
            os.unlink(destino)
            return {"item": item, "caminho": l["caminho"], "acao": "remover"}
        return {"item": item, "caminho": l["caminho"], "acao": "igual"}
    _pasta(destino.parent, modo=0o755, dono=root, ajustar=False)
    return {"item": item, "caminho": l["caminho"], "acao": _gravar_se_mudou(destino, l["texto"].encode("utf-8"), 0o755, root)}


def texto_do_plano(plano: dict) -> list[str]:
    """O que o preparar-wsl.sh mostra ANTES de instalar (em português simples)."""
    c = plano["caminhos"]
    linhas = [f"Jaula do Criador {plano['versao']}: o que será instalado (exige administrador do Linux)"]
    if not plano["necessaria"]:
        if plano.get("sem_area"):
            return linhas + ["  a área do titular de " + ", ".join(plano["sem_area"]) + " ainda não foi gravada (o "
                             "instalar-projeto vem antes): o plano da jaula aparece depois, sem --simular"]
        return linhas + ["  nenhuma ficha vigente abre navegador nem Codex: nada a instalar (a jaula não existe para "
                         "estes projetos)"]
    linhas += [f"  usuário de sistema {plano['usuario_jaula']}: sem shell, sem senha e sem casa; guarda os logins do "
               "navegador e do Codex em pastas que você não lê",
               f"  pasta de estado {c['estado']} (root, 0755) e uma por projeto, de dono {plano['usuario_jaula']}, 0700: "
               + (", ".join(p["caminho"] for p in plano["pastas"][1:]) or "(nenhuma)"),
               f"  programas de dono root em {c['programas']}: "
               + ", ".join(f"{a['destino'].rsplit('/', 1)[1]} [{a['estado']}]" for a in plano["arquivos"])]
    if plano["sudoers"]:
        linhas.append(f"  sudoers {c['sudoers']} (0440; conferida com visudo -cf antes de entrar), forma "
                      f"{'sem senha (NOPASSWD)' if plano['sudo'] == 'nopasswd' else 'com senha'}"
                      + (" (medida M1 passou)" if plano["sudo"] == "nopasswd" else
                         f" ({plano['sudo_motivo']})" if plano.get("sudo_motivo") else " (pedida com --sudo-senha)") + ":")
        linhas += ["    " + l for l in plano["sudoers"].splitlines() if l and not l.startswith("#")]
    else:
        linhas.append(f"  sudoers {c['sudoers']}: nenhuma linha (arquivo existente sai)")
    for p in plano["projetos"]:
        fechados = "; ".join(f"{m}: {motivo}" for m, motivo in p["fechados"].items())
        linhas.append(f"  projeto {p['projeto']}: modos da ficha {', '.join(p['modos_da_ficha'])}; com linha na sudoers: "
                      f"{', '.join(p['abertos'])}" + (f"; fechados ({fechados})" if fechados else ""))
    if plano["sem_jaula"]:
        linhas.append("  sem seção de jaula na ficha (nada é criado para eles): " + ", ".join(plano["sem_jaula"]))
    pendentes = plano.get("comandos_do_canario") or []
    if pendentes:
        linhas.append("  canário da jaula (prova a caixa por dentro; sem ele esses modos ficam fechados). Depois desta "
                      "instalação, rode no terminal do Ubuntu, um por vez:")
        linhas += ["    " + c["comando"] for c in pendentes]
        linhas.append("  e rode de novo o preparar-wsl.sh com " + " ".join(f"--canario-jaula {c['arquivo']}" for c in pendentes))
    for l in plano.get("lancadores") or []:
        linhas.append(f"  lançador do titular {l['caminho']}" + (" [criar/atualizar]" if l["abrir"] else " [sai: o modo não está aberto]"))
    if plano.get("navegador"):
        linhas.append("  não inclui os downloads do navegador, que vêm no passo seguinte (instalar-navegador-jaula, com sudo): "
                      "o script mostra antes cada endereço e tamanho; os pacotes do pip têm SHA-256 fixados e só a árvore do Chromium é "
                      "registrada na 1ª instalação (confiança no primeiro uso):")
        linhas += ["    " + d for d in descricao_dos_downloads()]
    if plano.get("codex"):
        linhas.append("  não inclui o download do Codex, que vem no passo seguinte (instalar-codex-jaula, com sudo): o script "
                      "mostra antes o endereço e o tamanho, e o SHA-256 é conferido ANTES de instalar:")
        linhas += ["    " + d for d in descricao_do_codex()]
        linhas.append("  " + jaula().ROTULO_DO_CODEX_CONTA)  # o risco, dito antes de o titular instalar e entrar na conta
    return linhas


# --- instalação ----------------------------------------------------------------------------------------------------
def _rodar_de_verdade(argv: list[str], entrada: bytes | None = None) -> tuple[int, str]:
    try:
        r = subprocess.run(argv, input=entrada, capture_output=True, timeout=120,
                           env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"})
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, f"{argv[0]} não executou ({type(exc).__name__})"
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace")[:2000]


def _pasta(pasta, *, modo: int = 0o755, dono: tuple[int, int] | None = None, ajustar: bool = True) -> Path:
    """Cria a pasta (e as de cima que faltarem) conferindo, sem seguir, cada componente: nenhum é ligação. As novas e a
    final ficam com `modo`; `dono` (uid, gid), se dado, vale para as criadas e para a final. `ajustar` falso: a final,
    se já existe, fica como está (a pasta do sistema, como /etc/sudoers.d)."""
    pasta = Path(os.path.abspath(pasta))
    cs = _script("copia_segura")
    atual, criada = Path(pasta.parts[0]), False
    for parte in pasta.parts[1:]:
        atual = atual / parte
        try:
            st = os.lstat(atual)
        except FileNotFoundError:
            os.mkdir(atual, 0o755)
            criada = atual == pasta
            if dono is not None and atual != pasta:
                os.chown(atual, 0, 0)
            st = os.lstat(atual)
        if cs.e_ligacao(st) or not stat.S_ISDIR(st.st_mode):
            raise erro(f"{atual} é ligação ou não é pasta: nada gravado ali")
    if os.name != "nt" and (ajustar or criada):
        os.chmod(pasta, modo)
        if dono is not None:
            os.chown(pasta, *dono)
    return pasta


def _gravar(destino: Path, dados: bytes, modo: int, dono: tuple[int, int] | None) -> None:
    _script("gravacao_segura").publicar(destino, dados)
    if os.name != "nt":
        os.chmod(destino, modo)
        if dono is not None:
            os.chown(destino, *dono)


def _gravar_se_mudou(destino: Path, dados: bytes, modo: int, dono: tuple[int, int] | None) -> str:
    if os.path.lexists(destino) and _sha_ou_none(destino) == hashlib.sha256(dados).hexdigest():
        if os.name != "nt" and stat.S_IMODE(os.lstat(destino).st_mode) != modo:
            os.chmod(destino, modo)
        return "igual"
    acao = "atualizar" if os.path.lexists(destino) else "criar"
    _gravar(destino, dados, modo, dono)
    return acao


def _instalar_arquivo(f: dict, destino: Path, root: tuple[int, int] | None) -> str:
    if os.path.lexists(destino) and _sha_ou_none(destino) == f["sha256"]:
        if os.name != "nt" and stat.S_IMODE(os.lstat(destino).st_mode) != f["modo"]:
            os.chmod(destino, f["modo"])
        return "igual"
    acao = "atualizar" if os.path.lexists(destino) else "criar"
    temp = destino.with_name(f".novo-{destino.name}-{secrets.token_hex(4)}")
    try:
        _script("copia_segura").copiar_conferindo(f["origem"], temp, sha256_esperado=f["sha256"], modo=f["modo"])
        if root is not None:
            os.chown(temp, *root)
        os.replace(temp, destino)
    except BaseException:
        if os.path.lexists(temp):
            os.unlink(temp)
        raise
    return acao


def garantir_usuario(rodar, consultar=None) -> dict:
    """O usuário `fundacao-jaula`: existe (conferido) ou é criado como usuário de sistema, sem shell, sem casa e sem
    senha. Devolve {acao, uid, gid}."""
    nome = jaula().USUARIO
    if consultar is None:
        import pwd
        consultar = pwd.getpwnam
    try:
        conta = consultar(nome)
    except KeyError:
        conta = None
    acao = "igual"
    if conta is None:
        codigo, saida = rodar([USERADD, "--system", "--user-group", "--no-create-home", "--home-dir", "/nonexistent",
                               "--shell", "/usr/sbin/nologin", nome])
        if codigo != 0:
            raise erro(f"não consegui criar o usuário {nome}: {saida.strip()[:300]}")
        conta, acao = consultar(nome), "criar"
    if conta.pw_uid == 0 or conta.pw_uid >= 1000 or not str(conta.pw_shell).endswith(("nologin", "false")):
        raise erro(f"o usuário {nome} já existe, mas não é de sistema sem shell (uid {conta.pw_uid}, shell "
                   f"{conta.pw_shell}): confira antes de instalar a jaula")
    return {"acao": acao, "uid": conta.pw_uid, "gid": conta.pw_gid}


def instalar_jaula(plano: dict, *, simular: bool = False, raiz_dono: bool = False, rodar=None, consultar=None) -> dict:
    """Instala (ou, em `simular`, só descreve) o que `montar_plano` calculou. Sem root, só em ensaio (`Caminhos.ensaio`).
    Ordem: binários, usuário, pastas, programas e hashes.json, `instalacao.json`, sudoers (visudo antes de entrar).
    `rodar(argv) -> (código, saída)` e `consultar(nome)` substituem o sistema nos testes."""
    c = Caminhos(**plano["caminhos"])
    if not plano["necessaria"]:
        return {"acoes": [], "necessaria": False}
    if not simular and not raiz_dono and not c.ensaio:
        raise erro("a jaula é de dono root: rode com sudo (o preparar-wsl.sh faz isso e mostra o comando)")
    if c.ensaio and raiz_dono:
        raise erro("o ensaio da jaula roda sem root: com sudo, tudo vai só para os caminhos reais")
    j, acoes, rodar = jaula(), [], rodar or _rodar_de_verdade
    faltam = [b for b in plano["binarios"] if not os.access(b["caminho"], os.X_OK)]
    if simular:
        return {"acoes": [{"item": "plano", "acao": "simular"}], "necessaria": True,
                "avisos": [f"falta {b['caminho']}: sudo apt-get install -y {b['pacote']}" for b in faltam]}
    if faltam:
        raise erro(f"falta {faltam[0]['caminho']}: sudo apt-get install -y {faltam[0]['pacote']}")
    if c.ensaio and not raiz_dono:
        conta, root = {"acao": "ensaio", "uid": os.getuid() if hasattr(os, "getuid") else 0,
                       "gid": os.getgid() if hasattr(os, "getgid") else 0}, None
        jaula_dono = None
    else:
        conta = garantir_usuario(rodar, consultar)
        root, jaula_dono = (0, 0), (conta["uid"], conta["gid"])
    acoes.append({"item": f"usuario:{j.USUARIO}", "acao": conta["acao"]})
    _pasta(Path(c.programas).parent, modo=0o755, dono=root)
    _pasta(c.programas, modo=0o755, dono=root)
    _pasta(c.estado, modo=0o755, dono=root)
    for p in plano["pastas"][1:]:
        _pasta(p["caminho"], modo=0o700, dono=jaula_dono)
        acoes.append({"item": f"estado:{p['caminho'].rsplit('/', 1)[1]}", "caminho": p["caminho"], "acao": "garantir"})
    for f in plano["_fontes"]:
        acoes.append({"item": f"programa:{f['nome']}", "caminho": f"{c.programas}/{f['nome']}",
                      "acao": _instalar_arquivo(f, Path(c.programas) / f["nome"], root)})
    registro = {"schema_version": ESQUEMA_INSTALADA, "versao": j.VERSAO_JAULA,
                "arquivos": {f["nome"]: f["sha256"] for f in plano["_fontes"]}}
    acoes.append({"item": "programas:hashes.json", "caminho": f"{c.programas}/hashes.json",
                  "acao": _gravar_se_mudou(Path(c.programas) / "hashes.json", texto_json(registro).encode("utf-8"), 0o644,
                                           root)})
    _pasta(Path(c.etc) / "jaula", modo=0o755, dono=root)
    instalacao = {"schema_version": ESQUEMA_INSTALACAO, "sudo": plano["sudo"]}
    nome = porteiro_jaula().INSTALACAO_NOME
    acoes.append({"item": f"jaula:{nome}", "caminho": f"{c.etc}/jaula/{nome}",
                  "acao": _gravar_se_mudou(Path(c.etc) / "jaula" / nome, texto_json(instalacao).encode("utf-8"), 0o644,
                                           root)})
    acoes.append(_instalar_sudoers(plano, c, root, rodar))
    acoes += [_instalar_lancador(l, root) for l in plano.get("lancadores") or []]
    return {"acoes": acoes, "necessaria": True}


def _instalar_sudoers(plano: dict, c: Caminhos, root, rodar) -> dict:
    destino, texto = Path(c.sudoers), plano["sudoers"]
    if not texto:
        if os.path.lexists(destino):
            os.unlink(destino)
            return {"item": "sudoers", "caminho": c.sudoers, "acao": "remover"}
        return {"item": "sudoers", "caminho": c.sudoers, "acao": "igual"}
    problemas = problemas_do_texto_do_sudoers(texto, plano["titular"], c.programas)
    if problemas:
        raise erro("; ".join(problemas))
    dados = texto.encode("utf-8")
    if os.path.lexists(destino) and _sha_ou_none(destino) == hashlib.sha256(dados).hexdigest():
        return {"item": "sudoers", "caminho": c.sudoers, "acao": "igual"}
    _pasta(destino.parent, modo=0o755, dono=root, ajustar=False)
    temp = destino.with_name(f"{destino.name}.novo.tmp")  # nome com ponto: a sudoers o ignora até o visudo aprovar
    if os.path.lexists(temp):
        os.unlink(temp)
    try:
        _gravar(temp, dados, 0o440, root)
        codigo, saida = rodar([VISUDO, "-cf", temp.as_posix()])
        if codigo != 0:
            raise erro(f"o visudo recusou a sudoers da jaula (nada foi instalado): {saida.strip()[:400]}")
        acao = "atualizar" if os.path.lexists(destino) else "criar"
        os.replace(temp, destino)
    except BaseException:
        if os.path.lexists(temp):
            os.unlink(temp)
        raise
    return {"item": "sudoers", "caminho": c.sudoers, "acao": acao}


def acessos_da_jaula(raiz: str, projetos: list[str], rodar=None) -> list[dict]:
    """[medir] O usuário da jaula lê `projects/<p>` e grava em `outputs/` (a saída de volta) com a raiz onde ela está (em
    /mnt/<x>, o DrvFs manda nas permissões). Só diagnostica, como root, pelo runuser; o que faltar vira dica."""
    rodar = rodar or _rodar_de_verdade
    nome, saida = jaula().USUARIO, []
    for p in projetos:
        base = f"{raiz}/projects/{p}"
        for descricao, teste, alvo in (("ler", "-r", base), ("gravar em outputs/", "-w", f"{base}/outputs")):
            codigo, _ = rodar([RUNUSER, "-u", nome, "--", "/usr/bin/test", teste, alvo])
            saida.append({"projeto": p, "acesso": descricao, "ok": codigo == 0, "alvo": alvo})
    return saida


def _dica_de_acesso(alvo: str) -> str:
    if alvo.startswith("/mnt/"):
        return ("a raiz está no disco do Windows (DrvFs): as permissões vêm do /etc/wsl.conf ([automount] options, "
                "metadata/umask) [medir]")
    return f"sudo setfacl -m u:{jaula().USUARIO}:rx {alvo} (e rwx em outputs/) [medir]"


def texto_da_instalacao(res: dict, plano: dict) -> list[str]:
    """O resultado de `instalar_jaula` em linhas (o preparar-wsl.sh as mostra e procura `[criar]`, `[atualizar]`,
    `[remover]` para dizer se algo mudou)."""
    linhas = []
    for a in res.get("acoes", []):
        if a["acao"] in ("criar", "atualizar", "remover", "igual", "simular", "ensaio"):
            linhas.append(f"  [{a['acao']}] {a['item']}" + (f": {a['caminho']}" if a.get("caminho") else ""))
    for x in res.get("acessos", []):
        if not x["ok"]:
            linhas.append(f"  o usuário {jaula().USUARIO} não alcança ({x['acesso']}) {x['alvo']}: {_dica_de_acesso(x['alvo'])}")
    for a in res.get("avisos", []):
        linhas.append("  aviso: " + a)
    pendentes = plano.get("comandos_do_canario") or []
    if pendentes:
        linhas.append("  canário da jaula: rode no terminal do Ubuntu, um por vez, e depois o preparar-wsl.sh com "
                      "--canario-jaula <arquivo>:")
        linhas += ["    " + c["comando"] for c in pendentes]
    return linhas


def texto_do_canario(res: dict) -> list[str]:
    linhas = [f"  [{res['acao']}] relatório do canário da jaula: {res['canario_jaula']}"]
    for m in res["modos"]:
        linhas.append(f"  modo {m['modo']}: " + ("APROVADO" if m["aprovado"] else "REPROVADO (" + ", ".join(m["reprovados"]) + ")")
                      + f" (SHA-256 {m['sha256'][:12]}...)")
        if m.get("medidas", {}).get("sandbox_codex") == "danger-full-access":  # o rótulo que o titular lê (M7)
            linhas.append("    ATENÇÃO: " + jaula().ROTULO_SEM_SANDBOX_DO_CODEX)
    linhas.append("  aprovados no relatório instalado: " + (", ".join(res["aprovados"]) or "nenhum"))
    return linhas


# --- o navegador da jaula: o que baixa (lote L5; DESENHO-JAULA §7.4, passos 3 e 4) --------------------------------------
LOCK_DO_NAVEGADOR = "assets/host/wsl/jaula-navegador.lock"
ESQUEMA_PINS = "fundacao.pins_navegador/1"
PINS_NOME = "pins-navegador.json"
ROTULO_DOS_PINS = ("confiança no primeiro uso, só para o Chromium: o Playwright não publica hash nem tamanho do navegador "
                   "(revisão 1248, Chrome for Testing 156.0.8078.4, mais o chromium-headless-shell); a 1ª instalação registra o "
                   "SHA-256 da árvore instalada e as seguintes só aceitam a mesma. Os pacotes do pip têm SHA-256 fixados no "
                   "arquivo de travas da skill, conferidos no PyPI em 08/11/2026")
# nome==versão --hash=sha256:<64 hex>, uma linha por pacote (um hash só): nenhuma outra opção do pip, URL nem -r.
LINHA_DE_TRAVA = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9][A-Za-z0-9._+!-]*) --hash=sha256:([0-9a-f]{64})\Z")
ENV_DA_INSTALACAO = ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "HOME=/nonexistent", "PIP_CONFIG_FILE=/dev/null",
                     "PIP_DISABLE_PIP_VERSION_CHECK=1"]
DOWNLOADS = (("apt", "o apt do Ubuntu (espelhos do Ubuntu, com o apt-get update): as bibliotecas do sistema para o Chromium e o acl",
              "cerca de 150 MB"),
             ("pip", "pypi.org e files.pythonhosted.org: playwright 1.64.1, pyee 14.0.0, greenlet 3.5.6 e typing_extensions "
                     "4.16.0, rodas do Linux x86_64 com SHA-256 fixado (48.471.931 + 621.404 + 45.571 + 15.553 bytes)",
              "cerca de 49,2 MB"),
             ("chromium", "o Chromium revisão 1248 (Chrome for Testing 156.0.8078.4) e o chromium-headless-shell, pelo "
                          "playwright install, nesta ordem de endereços: https://cdn.playwright.dev/dbazure/download/playwright, "
                          "https://playwright.download.prss.microsoft.com/dbazure/download/playwright e https://cdn.playwright.dev",
              "tamanho ESTIMADO (o Playwright não o publica): cerca de 170 MB baixados e 500 MB no disco; árvore em confiança "
              "no primeiro uso"))


def descricao_dos_downloads() -> list[str]:
    return [f"{nome}: {de}; {tamanho}" for nome, de, tamanho in DOWNLOADS]


def travas_do_lock(skill) -> list[tuple[str, str]]:
    """[('playwright==1.64.1', '<sha256>'), ...] do arquivo de travas da skill: SÓ linhas `nome==versão --hash=sha256:<64>`
    (nenhuma outra opção do pip, URL nem -r: o arquivo não manda o pip para outro lugar). Sem repetição, com o playwright."""
    caminho = Path(skill) / LOCK_DO_NAVEGADOR
    try:
        texto = caminho.read_text(encoding="utf-8")
    except OSError as exc:
        raise erro(f"a skill não tem {LOCK_DO_NAVEGADOR} legível ({exc.strerror or exc})") from None
    saida = []
    for linha in texto.splitlines():
        linha = linha.split("#", 1)[0].strip()
        if not linha:
            continue
        m = LINHA_DE_TRAVA.fullmatch(linha)
        if not m:
            raise erro(f"{LOCK_DO_NAVEGADOR}: só linhas nome==versão --hash=sha256:<64 hex> (recusada: {linha[:60]!r})")
        saida.append((f"{m[1]}=={m[2]}", m[3]))
    nomes = [r.split("==")[0].lower() for r, _h in saida]
    if len(set(nomes)) != len(nomes) or "playwright" not in nomes:
        raise erro(f"{LOCK_DO_NAVEGADOR}: sem repetição e com o playwright fixado")
    return saida


def requisitos_do_lock(skill) -> list[str]:
    return [r for r, _h in travas_do_lock(skill)]


def texto_das_travas(travas: list[tuple[str, str]]) -> str:
    """O arquivo `--require-hashes` que o pip lê (gravado de dono root, a partir das linhas já conferidas)."""
    return "".join(f"{r} --hash=sha256:{h}\n" for r, h in travas)


def roda_longo(argv: list[str]) -> tuple[int, str]:
    """Como o `_rodar_de_verdade`, a partir de `/` e com prazo de 30 minutos (downloads); a saída vai ao terminal do titular."""
    try:
        r = subprocess.run(argv, stdin=subprocess.DEVNULL, timeout=1800, cwd="/" if os.name != "nt" else None)
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, f"{argv[0]} não executou ({type(exc).__name__})"
    return r.returncode, ""


def _roda(rodar, argv: list[str], o_que: str) -> None:
    codigo, saida = rodar(argv)
    if codigo != 0:
        raise erro(f"{o_que} falhou (código {codigo}): {str(saida).strip()[-300:]}")


def _pins(base: Path) -> dict:
    arquivo = base / PINS_NOME
    if not os.path.lexists(arquivo):
        return {}
    dados = _ler_json(arquivo)
    if not isinstance(dados, dict) or dados.get("schema_version") != ESQUEMA_PINS:
        raise erro(f"{PINS_NOME} fora do esquema {ESQUEMA_PINS}: apague-o só se quiser registrar tudo de novo")
    return dados


def _arvore_do_chromium(ms: Path) -> tuple[str, str] | None:
    """(nome da pasta, SHA-256 da árvore) do `chromium-<revisão>` mais novo de ms-playwright, ou None."""
    if H is None:
        raise erro("o preparo_host não está ligado ao preparo da jaula (configurar)")
    pastas = sorted((p for p in ms.glob("chromium-*") if p.is_dir() and re.fullmatch(r"chromium-[0-9]+", p.name)),
                    key=lambda p: int(p.name.split("-")[1])) if ms.is_dir() else []
    return (pastas[-1].name, H.sha256_arvore(pastas[-1])) if pastas else None


def instalar_navegador_jaula(skill, caminhos: Caminhos, plano: dict, *, preparar: bool = False, simular: bool = False,
                             raiz_dono: bool = False, rodar=None) -> dict:
    """Passos 3 e 4 do §7.4 (titular, com sudo): o apt da lista fixa do `navegador.py` (mais o acl), o venv do Playwright
    em `<programas>/navegador/venv` (`pip install --require-hashes`), o Chromium do Playwright em `ms-playwright` (versão
    do Playwright fixado), tudo de dono root e grupo `fundacao-jaula`, modo 0750: a sessão do titular não lê nem executa.
    Só com a seção navegador na ficha de algum projeto (`plano["navegador"]`) ou com `--preparar-jaula`. Hash que exigiria
    baixar para existir não se inventa: a 1ª instalação registra o que baixou em `pins-navegador.json` (rotulado), e as
    seguintes só aceitam o mesmo (pip --require-hashes; árvore do Chromium)."""
    if not plano.get("necessaria") or not plano.get("navegador"):
        return {"acoes": [], "necessaria": False}
    travas = travas_do_lock(skill)
    requisitos = [r for r, _h in travas]
    pacotes = [*_script("navegador").PACOTES_DO_SISTEMA, "acl"]
    if simular:
        return {"acoes": [{"item": "navegador", "acao": "simular"}], "necessaria": True, "downloads": descricao_dos_downloads(),
                "requisitos": requisitos, "pacotes": pacotes}
    if caminhos.ensaio and rodar is None:
        raise erro("o ensaio da jaula nunca baixa nada: use --simular")
    if not raiz_dono and not caminhos.ensaio:
        raise erro("o navegador da jaula é de dono root: rode com sudo (o preparar-wsl.sh faz isso e mostra os downloads)")
    j, rodar, acoes = jaula(), rodar or roda_longo, []
    root = (0, 0) if raiz_dono else None
    base = Path(caminhos.programas) / "navegador"
    py, ms = base / "venv" / "bin" / "python", base / "ms-playwright"
    apt = ["/usr/bin/env", "DEBIAN_FRONTEND=noninteractive", "/usr/bin/apt-get"]
    _roda(rodar, [*apt, "update", "-q"], "o apt-get update")
    _roda(rodar, [*apt, "install", "-y", *pacotes], "o apt-get install")
    acoes.append({"item": "apt:pacotes-do-navegador", "acao": "garantir"})
    _pasta(base, modo=0o750, dono=root)
    if not os.path.lexists(py):
        _roda(rodar, ["/usr/bin/python3", "-I", "-m", "venv", (base / "venv").as_posix()], "o venv do Playwright")
        acoes.append({"item": "venv", "caminho": (base / "venv").as_posix(), "acao": "criar"})
    travas_arquivo = base / "travas-com-hashes.txt"
    acoes.append({"item": "pip:travas", "caminho": travas_arquivo.as_posix(),
                  "acao": _gravar_se_mudou(travas_arquivo, texto_das_travas(travas).encode("utf-8"), 0o644, root)})
    _roda(rodar, [*ENV_DA_INSTALACAO, py.as_posix(), "-I", "-m", "pip", "install", "--require-hashes", "--no-deps",
                  "--only-binary", ":all:", "--no-input", "-r", travas_arquivo.as_posix()], "o pip install com hashes")
    acoes.append({"item": "pip:playwright", "acao": "garantir"})
    pins = _pins(base)
    atual = _arvore_do_chromium(ms)
    if atual is None:
        _roda(rodar, [*ENV_DA_INSTALACAO, f"PLAYWRIGHT_BROWSERS_PATH={ms.as_posix()}", py.as_posix(), "-I", "-m", "playwright",
                      "install", "chromium"], "o playwright install chromium")
        atual = _arvore_do_chromium(ms)
        if atual is None:
            raise erro("o playwright install terminou sem deixar a pasta chromium-<revisão> em ms-playwright")
        acoes.append({"item": "chromium", "caminho": ms.as_posix(), "acao": "criar"})
    elif (pins.get("chromium") or {}).get("arvore_sha256") not in (None, atual[1]):
        raise erro(f"o Chromium instalado ({atual[0]}) difere do pino da 1ª instalação: confira a pasta antes de seguir "
                   f"(para registrar de novo, apague {PINS_NOME} e {ms.name})")
    else:
        acoes.append({"item": "chromium", "caminho": ms.as_posix(), "acao": "igual"})
    pins = {"schema_version": ESQUEMA_PINS, "rotulo": ROTULO_DOS_PINS, "chromium": {"pasta": atual[0], "arvore_sha256": atual[1]}}
    acoes.append({"item": PINS_NOME, "caminho": (base / PINS_NOME).as_posix(),
                  "acao": _gravar_se_mudou(base / PINS_NOME, texto_json(pins).encode("utf-8"), 0o644, root)})
    if raiz_dono:  # dono root, grupo da jaula, sem acesso para os outros: a sessão do titular não lê nem executa
        _roda(rodar, ["/usr/bin/chown", "-R", f"root:{j.USUARIO}", base.as_posix()], "o chown")
        _roda(rodar, ["/usr/bin/chmod", "-R", "u=rwX,g=rX,o=", base.as_posix()], "o chmod")
    return {"acoes": acoes, "necessaria": True, "downloads": descricao_dos_downloads()}


def texto_do_navegador(res: dict) -> list[str]:
    if not res.get("necessaria"):
        return ["  navegador da jaula: nenhuma ficha vigente abre navegador (e sem --preparar-jaula): nada a instalar"]
    linhas = []
    if any(a["acao"] == "simular" for a in res["acoes"]):
        linhas.append("  navegador da jaula (nada foi baixado; este é o plano):")
        linhas += ["    " + d for d in res["downloads"]]
        linhas.append("    pacotes do apt: " + ", ".join(res["pacotes"]))
        linhas.append("    travas do pip (versões fixas): " + ", ".join(res["requisitos"]))
        return linhas
    for a in res["acoes"]:
        linhas.append(f"  [{a['acao']}] {a['item']}" + (f": {a['caminho']}" if a.get("caminho") else ""))
    return linhas


# --- o Codex da jaula: o que baixa (lote L6; DESENHO-JAULA §7.4, passo 5) ------------------------------------------------
URL_BASE_DO_CODEX = "https://github.com/openai/codex/releases/download/"
ESQUEMA_CODEX_INSTALADO = "fundacao.codex_instalado/1"
INSTALADO_NOME = "instalado.json"


def pins_do_codex(skill=None) -> dict:
    """O `pins-codex.json` da skill (versão, arquivo, tamanho e SHA-256 da API do GitHub), conferido pelo validador da
    jaula, mais o endereço. Nada vem de argumento nem do ambiente: a versão só muda com uma versão nova da skill."""
    j = jaula()
    pins = _ler_json(Path(skill or SKILL) / "assets" / "host" / "wsl" / j.PINS_DO_CODEX)
    problema = j.problema_dos_pins(pins)
    if problema:
        raise erro(f"{j.PINS_DO_CODEX} recusado: {problema}")
    return {**pins, "url": f"{URL_BASE_DO_CODEX}{pins['etiqueta']}/{pins['arquivo']}"}


def descricao_do_codex(pins: dict | None = None) -> list[str]:
    pins = pins or pins_do_codex()
    tamanho = f"{pins['tamanho']:,}".replace(",", ".")
    return [f"{pins['url']}: o CLI do Codex {pins['versao']} (Linux x86_64 musl), {tamanho} bytes (cerca de "
            f"{pins['tamanho'] // (1 << 20)} MiB)",
            f"SHA-256 fixado {pins['sha256']} (campo digest da API do GitHub, conferido em {pins.get('conferido_em', '?')}; a assinatura "
            ".sigstore existe e esta instalação não a verifica): o tamanho e o SHA-256 são conferidos ANTES de instalar"]


def baixar_https(url: str, destino, limite: int) -> None:
    """Baixa `url` (só do release fixado em github.com/openai/codex, só https, também nos redirecionamentos) para o arquivo
    NOVO `destino`, sem passar de `limite` bytes."""
    import urllib.request
    if not url.startswith(URL_BASE_DO_CODEX):
        raise erro("o preparo só baixa o release fixado de github.com/openai/codex")

    class SoHttps(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not newurl.startswith("https://"):
                raise erro("o download tentou sair de https num redirecionamento: recusado")
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    fd = os.open(destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0), 0o600)
    total = 0
    with os.fdopen(fd, "wb") as f, urllib.request.build_opener(SoHttps).open(
            urllib.request.Request(url, headers={"User-Agent": "fundacao-ia-multiprojetos"}), timeout=120) as resposta:
        while bloco := resposta.read(1 << 20):
            total += len(bloco)
            if total > limite:
                raise erro(f"o download passou do tamanho fixado ({limite} bytes): interrompido")
            f.write(bloco)


def _extrair_membro(tgz, membro: str, destino) -> tuple[str, int]:
    """O ÚNICO membro do tar.gz, como arquivo comum com o nome esperado, vai para o arquivo novo `destino` (sem
    `extractall`): (SHA-256 dos bytes gravados, tamanho)."""
    import tarfile
    with tarfile.open(tgz, "r:gz") as tar:
        itens = tar.getmembers()
        if len(itens) != 1 or itens[0].name != membro or not itens[0].isreg() or not 1 <= itens[0].size <= 600 << 20:
            raise erro(f"o arquivo do Codex não traz só o membro {membro} como arquivo comum: nada foi instalado")
        origem, h, total = tar.extractfile(itens[0]), hashlib.sha256(), 0
        fd = os.open(destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0), 0o700)
        with os.fdopen(fd, "wb") as f:
            while bloco := origem.read(1 << 20):
                h.update(bloco)
                total += len(bloco)
                f.write(bloco)
    if total != itens[0].size:
        raise erro("o membro do Codex veio incompleto: nada foi instalado")
    return h.hexdigest(), total


def instalar_codex_jaula(skill, caminhos: Caminhos, plano: dict, *, preparar: bool = False, simular: bool = False,
                         raiz_dono: bool = False, baixar=None) -> dict:
    """Passo 5 do §7.4 (titular, com sudo): baixa o CLI do Codex fixado em `pins-codex.json`, confere tamanho e SHA-256 do
    arquivo ANTES de instalar (recusa se não baterem, sem deixar nada), extrai só o membro esperado e o instala em
    `<programas>/codex/<versão>/codex` (dono root, 0755), com `instalado.json` (SHA-256 do arquivo e do binário). Só com a
    seção outras_llm na ficha de algum projeto (`plano["codex"]`) ou com --preparar-jaula. O ensaio nunca baixa."""
    if not plano.get("necessaria") or not plano.get("codex"):
        return {"acoes": [], "necessaria": False}
    pins = pins_do_codex(skill)
    if simular:
        return {"acoes": [{"item": "codex", "acao": "simular"}], "necessaria": True, "downloads": descricao_do_codex(pins)}
    if caminhos.ensaio and baixar is None:
        raise erro("o ensaio da jaula nunca baixa nada: use --simular")
    if not raiz_dono and not caminhos.ensaio:
        raise erro("o Codex da jaula é de dono root: rode com sudo (o preparar-wsl.sh faz isso e mostra o download)")
    root = (0, 0) if raiz_dono else None
    base = Path(caminhos.programas) / "codex"
    pasta, registro = base / pins["versao"], base / pins["versao"] / INSTALADO_NOME
    binario = pasta / "codex"
    try:
        antes = _ler_json(registro) if os.path.lexists(registro) else None
    except Exception:  # noqa: BLE001 — registro ilegível: instala de novo
        antes = None
    if (isinstance(antes, dict) and antes.get("sha256_arquivo") == pins["sha256"] and os.path.lexists(binario)
            and _sha_ou_none(binario) == antes.get("sha256_binario")):
        return {"acoes": [{"item": "codex", "caminho": binario.as_posix(), "acao": "igual"}], "necessaria": True}
    _pasta(base, modo=0o755, dono=root)
    _pasta(pasta, modo=0o755, dono=root)
    tmp = base / f".baixando-{secrets.token_hex(4)}"
    _pasta(tmp, modo=0o700, dono=root)
    try:
        arquivo = tmp / pins["arquivo"]
        (baixar or baixar_https)(pins["url"], arquivo, pins["tamanho"])
        lido = _script("copia_segura").hash_conferido(arquivo)
        if lido["bytes"] != pins["tamanho"] or lido["sha256"] != pins["sha256"]:
            raise erro(f"o arquivo baixado NÃO confere com o pino (tamanho {lido['bytes']} contra {pins['tamanho']}; SHA-256 "
                       f"{lido['sha256'][:16]}... contra {pins['sha256'][:16]}...): nada foi instalado")
        sha_binario, tamanho_binario = _extrair_membro(arquivo, pins["membro"], tmp / "codex")
        if os.name != "nt":
            os.chmod(tmp / "codex", 0o755)
            if root is not None:
                os.chown(tmp / "codex", *root)
        os.replace(tmp / "codex", binario)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    novo = {"schema_version": ESQUEMA_CODEX_INSTALADO, "versao": pins["versao"], "arquivo": pins["arquivo"],
            "sha256_arquivo": pins["sha256"], "sha256_binario": sha_binario, "bytes_binario": tamanho_binario}
    return {"acoes": [{"item": "codex", "caminho": binario.as_posix(), "acao": "criar" if antes is None else "atualizar"},
                      {"item": INSTALADO_NOME, "caminho": registro.as_posix(),
                       "acao": _gravar_se_mudou(registro, texto_json(novo).encode("utf-8"), 0o644, root)}], "necessaria": True}


def texto_do_codex(res: dict) -> list[str]:
    if not res.get("necessaria"):
        return ["  Codex da jaula: nenhuma ficha vigente abre o Codex (e sem --preparar-jaula): nada a instalar"]
    if any(a["acao"] == "simular" for a in res["acoes"]):
        return ["  Codex da jaula (nada foi baixado; este é o plano):", *["    " + d for d in res["downloads"]]]
    return [f"  [{a['acao']}] {a['item']}" + (f": {a['caminho']}" if a.get("caminho") else "") for a in res["acoes"]]


# --- o relatório do canário da jaula -------------------------------------------------------------------------------
def ids_do_canario(como: str) -> tuple[str, ...]:
    return ITENS_DO_CANARIO + ((ITEM_DO_CODEX, ITEM_M7_DO_CODEX) if como.startswith("codex") else ())


def classificar_resposta_do_canario(dados: bytes, hashes_atuais: dict) -> dict:
    """O que uma resposta do modo `canario` da entrada fixa (`fundacao.resposta_jaula/1`) diz, sem gravar: a chave do
    modo (navegador, navegador-janela:login, ..., codex-titular), se APROVA (recalculado pelos itens, sem confiar no
    `ok` que veio), os reprovados e o SHA-256 do arquivo. Recusa (erro) o que não é resposta real do canário desta
    jaula: outro esquema, itens que faltam ou repetem, modo sem variante, ou hashes de outra versão da jaula."""
    j = jaula()
    try:
        resp = j.carregar_estrito(dados)
    except ValueError as exc:
        raise erro(f"relatório do canário da jaula ilegível: {exc}") from None
    rel = resp.get("relatorio") if isinstance(resp, dict) else None
    if (not isinstance(resp, dict) or resp.get("schema_version") != j.ESQUEMA_RESPOSTA or resp.get("modo") != "canario"
            or not isinstance(rel, dict) or rel.get("schema_version") != j.ESQUEMA_RELATORIO):
        raise erro("não é a resposta do modo canario da entrada fixa (fundacao.resposta_jaula/1 com o relatório "
                   "fundacao.canario_jaula/1): rode o comando que o preparar-wsl.sh mostra")
    como, variante = resp.get("como"), resp.get("variante")
    if como not in j.COMO_CANARIO or rel.get("como") != como:
        raise erro("o relatório não diz de qual modo é (como)")
    if como == "navegador-janela":
        if variante not in j.VARIANTES_JANELA:
            raise erro("o relatório da janela não diz a variante (login ou captcha): ele é de uma versão sem isso; rode o "
                       "canário de novo")
        chave = f"navegador-janela:{variante}"
    elif variante is not None:
        raise erro("variante só existe no modo navegador-janela")
    else:
        chave = como
    itens = rel.get("itens")
    if not isinstance(itens, list) or not all(isinstance(i, dict) and isinstance(i.get("id"), str) for i in itens):
        raise erro("itens do relatório fora da forma")
    ids = [i["id"] for i in itens]
    if len(set(ids)) != len(ids) or set(ids) != set(ids_do_canario(como)):
        raise erro("o relatório não tem exatamente os itens do canário desta jaula (faltam ou sobram): "
                   f"faltam {sorted(set(ids_do_canario(como)) - set(ids))}, sobram {sorted(set(ids) - set(ids_do_canario(como)))}")
    if not isinstance(resp.get("hashes"), dict) or resp["hashes"] != hashes_atuais:
        raise erro("o relatório é de outra versão da jaula (a entrada fixa, o proxy ou o bwrap mudaram desde o canário): "
                   "rode o canário de novo")
    reprovados = sorted(i["id"] for i in itens if i.get("aprovado") is not True)
    return {"chave": chave, "aprovado": not reprovados, "reprovados": reprovados, "itens": len(itens),
            "sha256": hashlib.sha256(dados).hexdigest(), "gerado_em": rel.get("gerado_em"),
            "medidas": j.medidas_dos_itens(itens) if como.startswith("navegador") else j.medidas_dos_itens_do_codex(itens)}


def resposta_guardada_pela_jaula(dados: bytes, caminhos: Caminhos) -> bytes:
    """F3 (revisão de segurança da 1.7.11): o relatório que abre os modos na sudoers vale pelo que a JAULA guardou, não pela forma
    do arquivo que o titular entrega (ele o guardou numa pasta que a sessão pode gravar, e a conferência de forma não distingue o
    forjado). A entrada fixa, no modo `canario`, grava a resposta em `<estado>/<projeto>/canario/<id>.json` (usuário da jaula,
    0600, pasta 0700 que a sessão não alcança). Aqui, como root, lê-se essa cópia pelo projeto e pelo id que o arquivo diz e só se
    aceita o arquivo do titular se for IGUAL byte a byte. A forma é a mais simples que a revisão aceita: não há segundo caminho de
    instalação, e o arquivo que o titular já guardava continua sendo o que ele passa ao `--canario-jaula`."""
    j = jaula()
    try:
        resp = j.carregar_estrito(dados)
    except ValueError as exc:
        raise erro(f"relatório do canário da jaula ilegível: {exc}") from None
    projeto, ident = (resp.get("projeto"), resp.get("id")) if isinstance(resp, dict) else (None, None)
    if (not isinstance(projeto, str) or not re.fullmatch(PROJETO_PADRAO, projeto) or "--" in projeto
            or not isinstance(ident, str) or not j.PEDIDO_ID.fullmatch(ident)):
        raise erro("a resposta não diz o projeto e o id do pedido (é de uma jaula sem a guarda do canário): rode o canário de "
                   "novo, com o comando que o preparar-wsl.sh mostra")
    guardada = Path(caminhos.estado) / projeto / "canario" / f"{ident}.json"
    try:
        fd = _script("copia_segura").abrir_comum(guardada)
    except OSError:
        raise erro(f"a jaula não guardou a resposta {ident} do projeto {projeto}: o relatório tem de vir de um canário rodado "
                   "pela entrada fixa; rode o comando que o preparar-wsl.sh mostra") from None
    try:
        st = os.fstat(fd)
        if not caminhos.ensaio and os.name == "posix":   # o dono real é o usuário da jaula, e só ele grava ali
            import pwd
            if st.st_uid != pwd.getpwnam(j.USUARIO).pw_uid or st.st_mode & 0o077:
                raise erro(f"{guardada.name}: a cópia do canário não é do usuário da jaula em modo 0600")
        if st.st_size > 1 << 20:
            raise erro("a cópia do canário que a jaula guardou passa de 1 MiB")
        gravado = os.read(fd, (1 << 20) + 1)
    finally:
        os.close(fd)
    if gravado != dados:
        raise erro("o arquivo não é o que a jaula guardou para este pedido (conteúdo diferente): não vale como relatório do "
                   "canário; rode o comando que o preparar-wsl.sh mostra e use a saída dele sem editar")
    return gravado


def instalar_canario_jaula(relatorios: list, caminhos: Caminhos, *, simular: bool = False, raiz_dono: bool = False,
                           hoje: str | None = None) -> dict:
    """`instalar-canario-jaula` (titular, com sudo): confere as respostas do canário, UMA por modo (e variante), contra a
    jaula instalada e grava o `canario-instalado.json` (de dono root) que o portão da entrada fixa lê. O modo cuja resposta
    reprova entra como `aprovado: false` (revoga o aprovado antes): sem aceite de risco no lugar, o modo não abre. As
    respostas de outras modos já instaladas ficam, se a jaula não mudou. Os hashes são os dos programas INSTALADOS."""
    j = jaula()
    if not simular and not raiz_dono and not caminhos.ensaio:
        raise erro("o relatório é de dono root: rode com sudo (o preparar-wsl.sh --canario-jaula faz isso)")
    if not relatorios:
        raise erro("informe ao menos um --relatorio (a resposta do canário de um modo)")
    cfg = j.Config(programas=caminhos.programas, estado=caminhos.estado, etc=caminhos.etc, bwrap=caminhos.bwrap,
                   usuario=None)
    try:
        atuais = j.hashes_da_instalacao(cfg)
    except j.Recusa as exc:
        raise erro(f"a jaula não está instalada como o preparo a deixa ({exc}): rode o preparar-wsl.sh antes") from None
    destino = Path(caminhos.etc) / j.RELATORIO_INSTALADO
    anterior = {}
    if destino.is_file():
        try:
            velho = _ler_json(destino)
            if isinstance(velho, dict) and velho.get("hashes") == atuais and isinstance(velho.get("modos"), dict):
                anterior = velho["modos"]
        except Exception:  # noqa: BLE001 — ilegível: começa de novo
            anterior = {}
    modos, resumo = dict(anterior), []
    for arquivo in relatorios:
        try:
            dados = Path(arquivo).read_bytes() if not hasattr(arquivo, "read") else arquivo.read()
        except OSError as exc:
            raise erro(f"relatório do canário da jaula ilegível ({exc.strerror or exc})") from None
        if len(dados) > 1 << 20:
            raise erro("relatório do canário da jaula acima de 1 MiB")
        dados = resposta_guardada_pela_jaula(dados, caminhos)   # F3: vale o que a jaula guardou, não a forma do arquivo
        r = classificar_resposta_do_canario(dados, atuais)
        modos[r["chave"]] = {"aprovado": r["aprovado"], "itens": r["itens"], "relatorio_sha256": r["sha256"],
                             "gerado_em": r["gerado_em"], "reprovados": r["reprovados"],
                             **({"medidas": r["medidas"]} if r["medidas"] else {})}  # M6: as opções fixas do navegador
        resumo.append({"modo": r["chave"], "aprovado": r["aprovado"], "reprovados": r["reprovados"],
                       "sha256": r["sha256"], **({"medidas": r["medidas"]} if r["medidas"].get("sandbox_codex") else {})})
    instalado = {"schema_version": j.ESQUEMA_RELATORIO_INSTALADO, "instalado_em": hoje or time.strftime("%Y-%m-%d"),
                 "hashes": atuais, "modos": dict(sorted(modos.items()))}
    acao = "igual" if destino.is_file() and _sha_ou_none(destino) == hashlib.sha256(
        texto_json(instalado).encode("utf-8")).hexdigest() else ("atualizar" if destino.is_file() else "criar")
    if not simular and acao != "igual":
        root = (0, 0) if raiz_dono else None
        _pasta(destino.parent, modo=0o755, dono=root)
        _gravar(destino, texto_json(instalado).encode("utf-8"), 0o644, root)
    return {"canario_jaula": destino.as_posix(), "acao": acao, "simulacao": simular, "modos": resumo,
            "aprovados": sorted(k for k, v in instalado["modos"].items() if v["aprovado"] is True),
            "proximo_passo": "rode de novo o preparar-wsl.sh: a sudoers só abre os modos que este relatório aprova"}
