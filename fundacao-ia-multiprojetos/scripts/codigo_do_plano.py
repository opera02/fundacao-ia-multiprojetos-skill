#!/usr/bin/env python3
"""O que prende o código que o programa importado roda, no plano de execução do fluxo B (`execucao_isolada.py`).

O SHA-256 do plano prende o programa (`comando[0]`, quase sempre o interpretador) e o comando, não o script que ele
roda: esse fica preso pelo manifesto da cópia, obrigatório com `--copia`; o comando não cita arquivo fora da cópia, e o
plano lista o que a cópia tem e o manifesto não vê [revisão de segurança da 1.7.7, R177-FB-02]. O manifesto é lido pela
mesma regra do `manifesto.py verificar` (`manifesto.politica_efetiva`: `politica` ausente ou nula é o formato 1, e o
que ele lista em `excluidos` fica fora da verificação; política que não é dicionário do formato 2, recusa), e o
arquivo que o comando cita tem de estar na lista de arquivos dele, fora dos excluídos [revisão de segurança da 1.7.7,
segunda passada, R177B-B-01]. O plano só diz que o código está preso se nada mais muda o que roda [R177B-B-02]: a
pasta de trabalho fica na cópia, fora do que o manifesto não prende; nenhuma variável pedida muda de onde o
interpretador carrega código (`PYTHONPATH`, `NODE_OPTIONS`, `LD_PRELOAD`...), nem atribuída no próprio comando (`env
NOME=VALOR`, `env -S`, código do `sh -c`), e o `-C` do `env` não muda a pasta de trabalho [terceira passada,
R177C-FB-01]; e `{entrada}`/`{ensaio}` não ficam no lugar do script, do módulo, do código do `-c`/`-e` nem do valor de
uma opção antes deles. Senão, os motivos vão para o plano (`codigo_nao_preso`) e a folha avisa. A cópia é conferida na montagem e antes e depois de cada caso, com o
SHA-256 do arquivo do manifesto e o que ela tem fora dele; a pasta gravável que fica dentro dela sai da conferência
(lá grava o programa) e vai para o plano como não presa; a que contém a cópia é recusada [R177B-B-03]. Limites: o que
o código preso faz com a entrada é comportamento dele; uma troca feita e desfeita durante um mesmo caso não é vista; de
programa fora das famílias que o plano lê (Python, shell e Node), só a posição de `{entrada}`/`{ensaio}` em relação
ao script citado da cópia, o `NOME=VALOR` e o `-C` do `env` são conferidos, não o que as outras opções dele carregam;
o que o código do `-c`/`-e` carrega por conta própria (`cd`, caminho absoluto, import montado em tempo de execução) o
plano não lê: ele mostra o comando, e quem lê é o titular; sem isolamento, o Node procura módulos também nas pastas
acima da cópia. Só lê; as recusas (`Recusa`) são as do lançador, que sai com código 2.
"""

from __future__ import annotations

import fnmatch
import glob
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

AQUI = Path(__file__).resolve().parent
MARCAS = ("{entrada}", "{ensaio}")  # trocadas a cada caso pela entrada e pela pasta do caso: nunca são código preso
# Variáveis que mudam de onde o interpretador carrega código (pasta, arquivo ou opção que carrega módulo): pedidas com
# --variavel, deixam o código NÃO PRESO [R177B-B-02]. A lista da revisão, avaliada, mais as que fazem o mesmo: bytecode,
# `site` e executável de outro lugar (Python), carregador dinâmico (LD_*, DYLD_*), módulos do iconv, gems, Java, R, PHP
# e Lua.
CARREGAM_CODIGO = frozenset({
    "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONPYCACHEPREFIX", "PYTHONPLATLIBDIR",
    "PYTHONEXECUTABLE", "NODE_OPTIONS", "NODE_PATH", "PERL5LIB", "PERLLIB", "PERL5OPT", "RUBYLIB", "RUBYOPT",
    "GEM_HOME", "GEM_PATH", "BASH_ENV", "ENV", "GCONV_PATH", "CLASSPATH", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS",
    "_JAVA_OPTIONS", "R_LIBS", "R_LIBS_USER", "R_PROFILE", "R_PROFILE_USER", "PHPRC", "PHP_INI_SCAN_DIR"})
_PREFIXOS_QUE_CARREGAM = ("LD_", "DYLD_", "LUA_PATH", "LUA_CPATH", "LUA_INIT")
# Os interpretadores cujas opções o plano lê. "codigo": a opção traz o código no próprio comando (`-c`, `-m`, `-e`...),
# e o que vem depois são argumentos dele; "valor": a opção leva valor, que não é o script; "carrega": entre essas, as
# que carregam código de um caminho. Python e shell agrupam letras (`-BX utf8`, `-ec 'cmd'`); no shell, o código do
# `-c` é o primeiro operando.
_FAMILIAS = {
    "python": {"codigo": {"-c", "-m"}, "valor": {"-W", "-X", "--check-hash-based-pycs"}, "carrega": set()},
    "sh": {"codigo": {"-c"}, "valor": {"-o", "+o", "-O", "+O", "--rcfile", "--init-file"},
           "carrega": {"--rcfile", "--init-file"}},
    "node": {"codigo": {"-e", "--eval", "-p", "--print", "-pe"},
             "valor": {"-r", "--require", "--import", "--loader", "--experimental-loader", "--env-file", "-C",
                       "--conditions", "--input-type", "--title", "--inspect-port", "--disable-warning"},
             "carrega": {"-r", "--require", "--import", "--loader", "--experimental-loader", "--env-file"}},
}
_SEMPRE_CAMINHO = {"--env-file", "--rcfile", "--init-file"}  # o valor é um arquivo, nunca o nome de um módulo
_LUGAR = {"fora": "fica fora da cópia", "solto": "fica em parte da cópia que o manifesto não prende"}


class Recusa(Exception):
    """O plano não pode ser montado ou rodado: quem chama sai com código 2 e esta mensagem."""


def _carregar(nome: str):
    """Um script ao lado deste, pelo caminho (sem mexer no `sys.path`)."""
    spec = importlib.util.spec_from_file_location(f"_codigo_do_plano_{nome}", AQUI / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


MANIFESTO = _carregar("manifesto")  # as regras do que o manifesto não vê: ligação, nome de segredo, pasta ignorada


def dentro(caminho: str, pasta: str) -> bool:
    return Path(caminho).is_relative_to(pasta)  # comparação do texto do caminho, sem resolver ligação


def citados(comando: list[str], cwd: str) -> list[str]:
    """Os arquivos que o comando cita depois do programa (o script, quase sempre), pelo caminho absoluto."""
    return [os.path.abspath(os.path.join(cwd, a)) for a in map(str, comando[1:])
            if "{" not in a and os.path.isfile(os.path.join(cwd, a))]


def _normal(rel: str) -> str:
    return os.path.normcase(rel.replace("/", os.sep))


def nao_preso(rel: str, fora: list[str]) -> bool:
    """O caminho, relativo à cópia, cai no que o manifesto não prende: o próprio item, uma pasta ignorada, uma ligação
    ou a pasta gravável."""
    rel = _normal(rel)
    for item in fora:
        base = _normal(item.removesuffix(" (ligação)").rstrip("/"))
        if rel == base or rel.startswith(base + os.sep):
            return True
    return False


def ler_manifesto(dados: bytes) -> tuple[dict, dict, set[str]]:
    """O manifesto, a política com que o `verificar` o confere e o que continua excluído (formato 1), pela regra única
    de `manifesto.politica_efetiva` [R177B-B-01]; a lista de arquivos tem caminho e SHA-256 em cada item."""
    try:
        ref = json.loads(dados)
        politica, antigos, _aviso = MANIFESTO.politica_efetiva(ref)
        if not isinstance(ref.get("excluidos", []), list) or not all(
                isinstance(f, dict) and isinstance(f.get("path"), str) and isinstance(f.get("sha256"), str)
                for f in ref["arquivos"]):
            raise ValueError("a lista de arquivos ou a de excluídos fora do formato")
    except (ValueError, KeyError, TypeError) as exc:
        raise Recusa(f"manifesto ilegível ou fora do formato de scripts/manifesto.py: {exc}") from None
    return ref, politica, antigos


def gravavel_na_copia(copia: str, gravavel: str | None) -> str | None:
    """A pasta gravável relativa à cópia, se fica dentro dela: sai da conferência e não fica presa. A que contém a cópia
    é recusada: o programa poderia trocar o próprio código entre os casos [R177B-B-03]."""
    if not gravavel:
        return None
    if dentro(copia, gravavel):
        raise Recusa(f"a pasta gravável {gravavel} contém a cópia: o programa poderia trocar o próprio código entre os "
                     "casos, e a cópia deixaria de ser conferível; use uma pasta ao lado da cópia ou dentro dela")
    return Path(gravavel).relative_to(copia).as_posix() if dentro(gravavel, copia) else None


def fora_do_manifesto(copia: str, politica: dict, antigos: set[str], arquivo: str,
                      gravavel: str | None = None) -> list[str]:
    """O que a cópia tem e o manifesto não vê, logo não prende: ligação, nome de segredo, exclusão dele e pasta que ele
    ignora (`.venv`, `node_modules`, `__pycache__`...), pela política com que o `verificar` o confere (`ler_manifesto`);
    sem seguir ligação nem entrar no que ele ignora nem na pasta gravável (`gravavel`, relativa à cópia), que o plano dá
    à parte. Vai para o plano: um item novo depois do aceite muda o hash e para a execução entre os casos."""
    ignoradas, segredos = set(politica["pastas_ignoradas"]), politica["padroes_de_segredo"]
    extras = politica["exclusoes_extras"]
    literais = set(politica.get("exclusoes_literais", [])) | antigos  # formato 1: os excluídos que ele lista
    if dentro(arquivo, copia):  # o próprio manifesto, guardado na cópia, fica preso pelo SHA-256 do plano
        literais.discard(Path(arquivo).relative_to(copia).as_posix())
    achados, pendentes = [], [Path(copia)]
    try:
        while pendentes:
            for item in pendentes.pop().iterdir():
                rel = item.relative_to(copia).as_posix()
                if gravavel and _normal(rel) == _normal(gravavel):
                    continue  # lá grava o programa: o plano a dá à parte, como não presa
                if MANIFESTO.e_ligacao(item):
                    achados.append(f"{rel} (ligação)")
                elif item.is_dir() and item.name in ignoradas:
                    achados.append(rel + "/")
                elif item.is_dir():
                    pendentes.append(item)
                elif (MANIFESTO.is_secret(item.name, segredos) or any(fnmatch.fnmatch(rel, g) for g in extras)
                      or rel in literais):
                    achados.append(rel)
    except OSError as exc:
        raise Recusa(f"cópia ilegível: {copia} ({type(exc).__name__})") from None
    return sorted(achados)


def conferir_citados(comando: list[str], cwd: str, copia: str) -> None:
    """O que o comando cita fica na cópia: o manifesto só prende a cópia."""
    for alvo in citados(comando, cwd):
        if not dentro(alvo, copia):
            raise Recusa(f"o comando cita {alvo}, fora da cópia {copia}: o manifesto só prende a cópia; ponha o "
                         "arquivo nela (e refaça o manifesto) ou, se for dado, passe-o como entrada")


def _soltos(fora: list[str], gravavel: str | None) -> list[str]:
    """O que o manifesto não prende na cópia: o que ele não vê e a pasta gravável que fica nela."""
    return [*fora, *([gravavel + "/"] if gravavel else [])]


def conferir_presos(comando: list[str], cwd: str, copia: str, ref: dict, fora: list[str],
                    gravavel: str | None = None) -> None:
    """E o manifesto o prende: está na lista de arquivos dele, fora dos excluídos, e não é excluído, ignorado nem
    ligação pela política [R177B-B-01], nem fica na pasta gravável [R177B-B-03]."""
    arquivos = {_normal(f["path"]) for f in ref["arquivos"]}
    excluidos = {_normal(e["path"]) for e in ref.get("excluidos", [])
                 if isinstance(e, dict) and isinstance(e.get("path"), str)}
    for alvo in citados(comando, cwd):
        rel = Path(alvo).relative_to(copia).as_posix()
        if _normal(rel) not in arquivos or _normal(rel) in excluidos or nao_preso(rel, _soltos(fora, gravavel)):
            raise Recusa(f"o comando cita {alvo}, que o manifesto não prende (fora da lista de arquivos dele, nos "
                         "excluídos, ligação, nome de segredo, exclusão dele, pasta que ele ignora ou pasta "
                         "gravável): refaça o manifesto sem excluí-lo ou tire-o dali")


def conferir_copia(plano: dict) -> None:
    """Na montagem e antes e depois de cada caso [R177B-B-03]: o arquivo do manifesto ainda tem o SHA-256 do plano, a
    cópia confere com ele pela regra do `verificar` e o que ela tem fora dele é o do plano. A pasta gravável que fica
    na cópia sai da conferência (lá grava o programa) sem ser lida."""
    man, copia = plano["manifesto"], plano["copia"]
    try:
        dados = Path(man["arquivo"]).read_bytes()
    except OSError as exc:
        raise Recusa(f"manifesto ilegível: {man['arquivo']} ({type(exc).__name__})") from None
    if hashlib.sha256(dados).hexdigest() != man["sha256"]:
        raise Recusa(f"o manifesto {man['arquivo']} não tem mais o SHA-256 do plano: foi trocado depois do aceite")
    ref, politica, antigos = ler_manifesto(dados)
    gravavel, conferencia = man.get("pasta_gravavel_na_copia"), politica
    if gravavel:  # sem ler o que o programa gravou: o que estiver lá sai do conjunto, e o manifesto não o prende
        conferencia = {**politica, "exclusoes_extras": [*politica["exclusoes_extras"], glob.escape(gravavel) + "/*"]}
    try:
        atual = MANIFESTO.build(Path(copia).resolve(), conferencia, antigos)
    except OSError as exc:
        raise Recusa(f"cópia ilegível: {copia} ({type(exc).__name__})") from None
    mudou = [f"{tipo}: {rel}" for tipo, lista in MANIFESTO.diff(ref, atual).items() for rel in lista
             if not nao_preso(rel, _soltos([], gravavel))]
    fora = fora_do_manifesto(copia, politica, antigos, man["arquivo"], gravavel)
    mudou += [f"novo fora do manifesto: {x}" for x in sorted(set(fora) - set(man["fora_do_manifesto"]))]
    mudou += [f"sumiu de fora do manifesto: {x}" for x in sorted(set(man["fora_do_manifesto"]) - set(fora))]
    if mudou:
        raise Recusa("a cópia difere do manifesto do plano: " + "; ".join(mudou)[:600])


def carrega_codigo(nome: str) -> bool:
    """A variável muda de onde o interpretador carrega código (o Windows não distingue maiúsculas)."""
    nome = nome.upper()
    return nome in CARREGAM_CODIGO or nome.startswith(_PREFIXOS_QUE_CARREGAM)


def _atribuidas(texto: str) -> list[str]:
    """As variáveis que carregam código atribuídas no texto, como a pedida com --variavel [R177C-FB-01]: `NOME=VALOR`
    num pedaço dele entre espaços e separadores do shell (o `-S` do `env`, o código do `sh -c`), também como valor de
    opção (`--setenv=NOME=VALOR`, `-SNOME=VALOR`, `-iSNOME=VALOR`). Opção com nome de variável (`--env=x`) não conta."""
    achadas = []
    for pedaco in re.split(r"[\s;&|()`'\"]+", texto):
        candidatos = [pedaco]
        if pedaco.startswith("-"):
            candidatos.append(pedaco.partition("=")[2])
            if not pedaco.startswith("--"):  # letras agrupadas: o valor pode vir colado a qualquer uma delas
                candidatos += [pedaco[k:] for k in range(2, len(pedaco)) if pedaco[1:k].isalpha()]
        for candidato in candidatos:
            nome = re.match(r"([A-Za-z_][A-Za-z0-9_]*)=", candidato)
            if nome and carrega_codigo(nome.group(1)) and nome.group(1) not in achadas:
                achadas.append(nome.group(1))
    return achadas


def _marcado(texto: str) -> bool:
    return any(m in texto for m in MARCAS)


def _onde(caminho: str, copia: str, soltos: list[str]) -> str:
    """"preso" (na cópia, no que o manifesto prende), "solto" (na cópia, no que ele não prende) ou "fora"."""
    caminho = os.path.abspath(caminho)
    if not dentro(caminho, copia):
        return "fora"
    rel = Path(caminho).relative_to(copia).as_posix()
    return "solto" if rel != "." and nao_preso(rel, soltos) else "preso"


def _parece_caminho(valor: str) -> bool:
    return valor.startswith((".", "/", "\\", "file:")) or bool(re.match(r"[A-Za-z]:", valor))


def _caminho_do_valor(valor: str, cwd: str) -> str:
    """O arquivo que o valor da opção indica: relativo à pasta de trabalho, ou o de um endereço `file:`."""
    if valor.startswith("file:"):
        valor = unquote(urlparse(valor).path)
        valor = valor[1:] if re.match(r"/[A-Za-z]:", valor) else valor  # file:///C:/... no Windows
    return os.path.join(cwd, valor)


def _familia(*programas: str) -> str | None:
    """A família do interpretador pelo nome do programa (o do comando ou o de verdade, atrás de ligação)."""
    for programa in programas:
        nome = os.path.basename(programa).lower().removesuffix(".exe")
        if re.fullmatch(r"(python|pypy)[0-9.]*w?|py", nome):
            return "python"
        if nome in ("sh", "bash", "dash", "zsh", "ksh", "ash", "mksh"):
            return "sh"
        if nome in ("node", "nodejs"):
            return "node"
    return None


def _ler_comando(familia: str, args: list[str]) -> tuple[list[tuple[str, str]], tuple[str, str] | None, int | None]:
    """As opções do interpretador: os valores dados antes do código, a opção que traz o código no próprio comando com
    o valor dela (ou None) e o índice do operando que ele roda como script (ou None: sem script)."""
    tabela, valores, c_do_shell, i = _FAMILIAS[familia], [], False, 0
    while i < len(args):
        a, prox = args[i], (args[i + 1] if i + 1 < len(args) else "")
        if a == "--":
            i += 1
            break
        if len(a) < 2 or a[0] not in ("-+" if familia == "sh" else "-"):
            break  # o primeiro operando
        if a.startswith("--") or familia == "node":  # opção longa (o Node não agrupa letras)
            nome, igual, resto = a.partition("=")
            if nome in tabela["codigo"]:
                return valores, (nome, resto if igual else prox), None
            if igual or nome in tabela["valor"]:
                valores.append((nome, resto if igual else prox))
            i += 2 if nome in tabela["valor"] and not igual else 1
            continue
        passo = 1
        for j, letra in enumerate(a[1:], 1):  # letras agrupadas: a que leva valor pega o resto ou o próximo
            opcao, resto = a[0] + letra, a[j + 1:]
            if opcao in tabela["codigo"] and familia == "sh":
                c_do_shell = True
            elif opcao in tabela["codigo"]:
                return valores, (opcao, resto or prox), None
            elif opcao in tabela["valor"]:
                valores.append((opcao, resto or prox))
                passo = 1 if resto else 2
                break
        i += passo
    if i >= len(args):
        return valores, None, None
    return (valores, ("-c", args[i]), None) if c_do_shell else (valores, None, i)


def _motivos_do_interpretador(familia: str, args: list[str], cwd: str, copia: str, soltos: list[str]) -> list[str]:
    valores, codigo, script = _ler_comando(familia, args)
    motivos = []
    for opcao, valor in valores:
        if _marcado(valor):
            motivos.append(f"{valor} no valor de {opcao}, antes do script")
        elif (opcao in _FAMILIAS[familia]["carrega"] and (opcao in _SEMPRE_CAMINHO or _parece_caminho(valor))
              and (onde := _onde(_caminho_do_valor(valor, cwd), copia, soltos)) != "preso"):
            motivos.append(f"{opcao} {valor} carrega código que {_LUGAR[onde]}")
        elif familia == "python" and opcao == "-X" and valor.startswith("pycache_prefix"):
            motivos.append(f"-X {valor} faz o Python ler bytecode de outra pasta")
    if codigo:
        opcao, valor = codigo
        if _marcado(valor):
            motivos.append(f"{valor} no código de {opcao}")
        elif opcao == "-m" and (onde := _onde(os.path.join(cwd, *valor.split(".")), copia, soltos)) != "preso":
            motivos.append(f"o módulo {valor} {_LUGAR[onde]}")
        if familia == "sh":  # [R177C-FB-01]
            motivos += [f"o código do {opcao} atribui {nome}, que muda de onde o código é carregado"
                        for nome in _atribuidas(valor)]
    elif script is not None:
        alvo = args[script]
        if _marcado(alvo):
            motivos.append(f"{alvo} no lugar do script")
        elif alvo != "-" and (onde := _onde(os.path.join(cwd, alvo), copia, soltos)) != "preso":
            motivos.append(f"o script {alvo} {_LUGAR[onde]}")
    return motivos


def _e_env(caminho: str) -> bool:
    return os.path.basename(caminho).lower().removesuffix(".exe") == "env"


def _muda_a_pasta(texto: str) -> bool:
    """O argumento do `env` (ou um pedaço dele entre espaços, como no `-S`) muda a pasta de trabalho: `-C`, agrupado
    com as letras que o env aceita antes dele, ou `--chdir` e as abreviações que o getopt aceita (`--ch=`), também
    colado ao `-S` (`-S--chdir=...`) [R177C-FB-01; conferência final, R177D-4]."""
    for pedaco in re.split(r"[\s;&|()`'\"]+", texto):
        candidatos = [pedaco]
        if pedaco.startswith("-") and not pedaco.startswith("--"):  # o valor pode vir colado a qualquer letra
            candidatos += [pedaco[k:] for k in range(2, len(pedaco)) if pedaco[1:k].isalpha()]
        if any(re.match(r"-[0iv]*C|--c(?:h(?:d(?:i(?:r)?)?)?)?(?:=|$)", c) for c in candidatos):
            return True
    return False


def _motivos_de_outro_programa(programas: tuple[str, str], args: list[str], cwd: str, copia: str) -> list[str]:
    """Programa que o plano não lê: {entrada}/{ensaio} só ficam de fora do código depois do script citado da cópia (um
    arquivo dela que não vem logo depois de uma opção, de que poderia ser o valor). Antes dele, variável que carrega
    código atribuída no comando (`env PYTHONPATH=...`) e o `-C` do `env`, que muda a pasta de trabalho, também deixam o
    código NÃO PRESO [R177C-FB-01], inclusive com o `env` atrás de outro programa (`nice env -C`, `timeout 9 env
    --chdir=`) [R177D-4]. `programas`: o do comando e o de verdade, atrás de ligação."""
    nome, motivos = os.path.basename(programas[0]), []
    env = any(_e_env(p) for p in programas)
    for i, arg in enumerate(args):
        if _marcado(arg):
            return motivos + [f"{arg} sem um script da cópia antes: o plano não lê as opções de {nome} e não sabe se "
                              f"ele roda {arg} como código"]
        alvo = os.path.abspath(os.path.join(cwd, arg))
        if os.path.isfile(alvo) and dentro(alvo, copia) and (i == 0 or not args[i - 1].startswith("-")):
            return motivos
        motivos += [f"{arg} atribui {var}, que muda de onde o código é carregado" for var in _atribuidas(arg)]
        if env and _muda_a_pasta(arg):
            motivos.append(f"{arg}: o env roda o comando em outra pasta de trabalho, de onde ele carrega o código")
        env = env or _e_env(arg)  # o env atrás de outro programa: o que vem depois são as opções dele (R177D-4)
    return motivos


def motivos_nao_preso(comando: list[str], cwd: str, copia: str, programa: str, fora: list[str], variaveis,
                      gravavel: str | None = None) -> list[str]:
    """Por que o código que o programa roda não fica preso pelo manifesto, além do que `fora_do_manifesto` lista
    [R177B-B-02]: a pasta de trabalho fora da cópia ou no que ela não prende (a pasta gravável, inclusive); variável
    pedida que muda de onde o código é carregado; e {entrada}/{ensaio} no lugar do código. `programa`: o caminho
    resolvido no plano."""
    soltos, motivos = _soltos(fora, gravavel), []
    onde = _onde(cwd, copia, soltos)
    if onde != "preso":
        motivos.append(f"a pasta de trabalho {cwd} {_LUGAR[onde]}, e o programa carrega dela módulos e caminhos "
                       "relativos")
    motivos += [f"a variável {nome} muda de onde o código é carregado" for nome in sorted(variaveis)
                if carrega_codigo(nome)]
    args = [str(a) for a in comando[1:]]
    familia = _familia(str(comando[0]), os.path.realpath(programa))
    if familia:
        motivos += _motivos_do_interpretador(familia, args, cwd, copia, soltos)
    elif _onde(programa, copia, soltos) != "preso":  # programa da cópia: o que vem depois são argumentos dele
        motivos += _motivos_de_outro_programa((str(comando[0]), os.path.realpath(programa)), args, cwd, copia)
    return motivos
