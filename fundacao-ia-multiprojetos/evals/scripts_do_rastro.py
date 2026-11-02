#!/usr/bin/env python3
"""Script de sed ou de awk no rastro do executor: ele roda comando ou lê e grava arquivo? (apoio de
rastro_do_executor.py; revisão de segurança da 1.7.10, CI-F7, com as correções da revisão 1).

A leitura é conservadora: o que não se lê conta como entrada e saída (E/S). O falso positivo custa um "não medido" (e o
nome do gabarito com curinga passa a contar no script); o falso negativo deixa a leitura do gabarito fora do rastro.
- sed: comando a comando, como o GNU sed 4.9 compila o script, com os -e na ordem da linha, juntos por quebra de linha
  (o texto de a, i e c continua de um -e para o seguinte quando termina em barra invertida). Contam os comandos e, r,
  R, w e W e as opções e e w do s. Não contam a expressão entre delimitadores (/re/, \\cREc, s e y; o delimitador entre
  colchetes não fecha a expressão), o texto de a, i e c, os rótulos e o comentário, que vai até a quebra de linha sem
  continuação (antes, a barra invertida no fim do comentário escondia o comando seguinte).
- awk: duas leituras independentes, e basta uma para contar.
  (1) No texto cru, com as continuações juntadas: system(, getline, ARGV, SYMTAB (que alcança o ARGV no gawk),
      @include, @load e a chamada indireta (@f()), estejam onde estiverem.
  (2) Pelos símbolos do programa: cadeia, expressão regular e comentário saem; a quebra de linha depois de , { ? : ||
      && do e else e a barra invertida no fim da linha continuam o comando. Contam print e printf com > >> | ou |&
      (o > dentro de parênteses é comparação), @ seguido de nome (salvo @namespace), cadeia ou expressão que não
      fecha e caractere que o awk não lê. A barra divide depois de um operando e abre expressão nos outros casos, em
      três leituras, e basta uma contar: a do gawk (a barra depois do parêntese de if, while, for ou switch abre
      expressão; colchetes contados como no gawk), a do mawk (a barra depois de qualquer parêntese divide; depois de
      ++, --, length e das outras funções embutidas, abre expressão; colchetes do POSIX) e a do gawk sem colchetes na
      expressão (busybox). Antes, as cadeias saíam por uma expressão regular, e a aspa dentro de /"/, a continuação e o
      ; { } dentro da expressão escondiam o system(), o getline e o print com redirecionamento.
Conferido em 01/11/2026 com o --sandbox do GNU sed 4.9 e pela execução do gawk 5.4.1 (Git Bash), do gawk 5.2.1 e do
mawk 1.3.4 (Ubuntu); os casos ficam em entrega/testes/test_rastro_1710.py.
"""
from __future__ import annotations

import re

BARRA = chr(92)

# --------------------------------------------------------------------- sed
# Separadores, blocos, negação e endereços sem expressão; os comandos sem argumento (o número de l, L, q e Q passa como
# endereço); os que levam rótulo (ou versão) até espaço, `;` ou quebra de linha; e os que levam texto até o fim da
# linha, que a barra invertida continua.
_SED_ENDERECO = set(" \t\r\n;{}!,~+$IM0123456789")
_SED_SIMPLES = set("=dDgGhHnNpPxzFlLqQ")
_SED_ROTULO = set(":btTv")
_SED_TEXTO = set("aic")


def _fim_dos_colchetes(s: str, i: int) -> int | None:
    """Índice depois do `]` que fecha a expressão entre colchetes aberta em `i` (o primeiro `]`, também depois de `^`,
    é literal; a barra invertida é literal; [:classe:], [.x.] e [=x=] vão inteiros), ou None."""
    j = i + 1
    if s[j:j + 1] == "^":
        j += 1
    if s[j:j + 1] == "]":
        j += 1
    while j < len(s) and s[j] != "\n":
        if s[j] == "]":
            return j + 1
        if s[j] == "[" and s[j + 1:j + 2] in (":", ".", "="):
            k = s.find(s[j + 1] + "]", j + 2)
            if k < 0 or "\n" in s[j:k]:
                return None
            j = k + 2
        else:
            j += 1
    return None


def _fim_do_trecho(s: str, i: int, fim: str, regex: bool = False) -> int | None:
    """Índice depois do `fim` que fecha o trecho começado em `i`, ou None. A barra invertida escapa o seguinte; a
    quebra de linha sem escape não fecha (o sed recusa); na expressão (`regex`), o delimitador entre colchetes não
    fecha, como no GNU sed 4.9 (`/[/]/p`; sondado no Ubuntu e no Git Bash em 01/11/2026)."""
    while i < len(s) and s[i] != "\n":
        if s[i] == fim:
            return i + 1
        if s[i] == BARRA:
            i += 2
        elif regex and s[i] == "[":
            i = _fim_dos_colchetes(s, i)
            if i is None:
                return None
        else:
            i += 1
    return None


def sed_com_es(scripts: list[str]) -> bool:
    """Os `scripts` do sed (os -e na ordem da linha, ou o script único) têm os comandos e, r, R, w ou W, ou o s com as
    opções e ou w. O que não se lê como sed conta como E/S."""
    s, i = "\n".join(scripts), 0
    while i is not None and i < len(s):
        c = s[i]
        if c in _SED_ENDERECO or c in _SED_SIMPLES:
            i += 1
        elif c == "#":  # comentário: até a quebra de linha, sem continuação (o GNU sed 4.9 não a aceita aqui)
            fim = s.find("\n", i)
            i = len(s) if fim < 0 else fim
        elif c in "/sy" + BARRA:
            d = c if c == "/" else s[i + 1:i + 2]
            if d in ("", "\n", BARRA):
                return True
            i = _fim_do_trecho(s, i + (1 if c == "/" else 2), d, regex=c != "y")  # a troca e o y não têm colchetes
            if c in "sy" and i is not None:
                i = _fim_do_trecho(s, i, d)
            if c == "s" and i is not None:
                opcoes = re.match(r"[gpiImMew0-9]*", s[i:])[0]
                if set(opcoes) & set("ew"):
                    return True
                i += len(opcoes)
        elif c in _SED_ROTULO:
            i += 1
            while i < len(s) and s[i] in " \t":
                i += 1
            while i < len(s) and s[i] not in " \t\r\n;":
                i += 1
        elif c in _SED_TEXTO:
            i += 1
            while i < len(s) and s[i] != "\n":
                i += 2 if s[i] == BARRA else 1
        else:  # e, r, R, w, W ou o que não se lê como sed
            return True
    return i is None


# --------------------------------------------------------------------- awk
_CONTINUACAO = re.compile(r"\\\r?\n")
_AWK_CRU = re.compile(r"\bsystem\s*\(|\bgetline\b|\bARGV\b|\bSYMTAB\b|@\s*(?:include|load)\b"
                      r"|@\s*[A-Za-z_][A-Za-z0-9_:]*\s*\(")
_AWK_NOME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z_][A-Za-z0-9_]*)?")
_AWK_NUMERO = re.compile(r"(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?[A-Za-z0-9_]*")
_AWK_OPERADOR = re.compile(r"\*\*=|\*\*|\|\||\|&|&&|>>|[<>=!]=|!~|\+\+|--|[-+*%^]=|[-+*%^!<>|?:~$=()\[\]{},;@]")
_AWK_NL_IGNORADA = frozenset((",", "{", "?", ":", "||", "&&", "do", "else"))
_AWK_PALAVRAS = frozenset(("BEGIN", "END", "BEGINFILE", "ENDFILE", "function", "func", "if", "else", "while", "for",
                           "do", "break", "continue", "next", "nextfile", "exit", "return", "delete", "print",
                           "printf", "in", "case", "default", "switch"))
_AWK_EMBUTIDAS = frozenset(("length", "substr", "index", "split", "sub", "gsub", "match", "sprintf", "sin", "cos",
                            "atan2", "exp", "log", "int", "sqrt", "rand", "srand", "tolower", "toupper", "fflush",
                            "close", "system"))
_AWK_LEITURAS = ("gawk", "mawk", "sem colchetes")
# Marcas dos símbolos: cadeia, expressão regular, número, ++/-- depois de operando e o ) da condição.
CADEIA, EXPRESSAO, NUMERO, SUFIXO, CONDICAO = '""', "//", "0", "x++", ")c"


def _operando(anterior: str | None, leitura: str) -> bool:
    """A barra depois de `anterior` divide (True) ou abre expressão regular (False), na `leitura`."""
    if anterior in (CADEIA, EXPRESSAO, NUMERO, "]", ")"):
        return True
    if anterior == CONDICAO:  # o gawk espera um comando depois de `if (...)`; o mawk divide depois de todo `)`
        return leitura == "mawk"
    if anterior == SUFIXO:  # `x++ / 2`: o gawk divide; o mawk abre expressão
        return leitura != "mawk"
    if anterior is None or not _AWK_NOME.fullmatch(anterior):
        return False
    return anterior not in _AWK_PALAVRAS and not (leitura == "mawk" and anterior in _AWK_EMBUTIDAS)


def _fim_da_cadeia(s: str, i: int) -> int | None:
    """Índice depois da aspa que fecha a cadeia aberta antes de `i`, ou None (quebra de linha ou fim)."""
    while i < len(s):
        if s[i] == '"':
            return i + 1
        if s[i] == "\n":
            return None
        if s[i] == BARRA:
            continua = _CONTINUACAO.match(s, i)
            i = continua.end() if continua else i + 2
        else:
            i += 1
    return None


def _fim_da_expressao(s: str, i: int, leitura: str) -> int | None:
    """Índice depois da barra que fecha a expressão regular aberta antes de `i`, ou None. Colchetes: no gawk, contados
    como no awkgram.y (o `]` logo depois de `[` ou `[^` é literal; só `[:` abre dentro de outro); no mawk, os do POSIX;
    na terceira leitura, nenhum."""
    dentro, inicio, tamanho, ultimo = 0, -1, 0, ""
    while i < len(s):
        c = s[i]
        if c == "\n":
            return None
        if c == BARRA:
            continua = _CONTINUACAO.match(s, i)
            if continua:
                i = continua.end()
                continue
            if i + 1 >= len(s):
                return None
            ultimo, tamanho, i = s[i + 1], tamanho + 2, i + 2
            continue
        if leitura == "mawk" and c == "[":
            i = _fim_dos_colchetes(s, i)
            if i is None:
                return None
            ultimo, tamanho = "]", tamanho + 1
            continue
        if leitura == "gawk" and c == "[":
            if s[i + 1:i + 2] == ":" or dentro == 0:
                dentro += 1
            if dentro == 1:
                inicio = tamanho
        elif leitura == "gawk" and c == "]":  # o `]` avulso também desconta (`/]a[/` fecha na segunda barra)
            if dentro > 0 and (tamanho == inicio + 1 or (tamanho == inicio + 2 and ultimo == "^")):
                pass
            else:
                dentro -= 1
                if dentro == 0:
                    inicio = -1
        elif c == "/" and dentro <= 0:
            return i + 1
        ultimo, tamanho, i = c, tamanho + 1, i + 1
    return None


def _simbolos(s: str, leitura: str) -> list[str] | None:
    """Os símbolos do programa na `leitura`, sem cadeias, expressões e comentários (viram marcas) e sem as quebras de
    linha que o awk ignora; None se uma cadeia ou expressão não fecha ou se há caractere que o awk não lê."""
    simbolos, condicoes, i = [], [], 0
    while i < len(s):
        c, anterior = s[i], (simbolos[-1] if simbolos else None)
        if c in " \t\r":
            i += 1
        elif c == BARRA:  # fora de cadeia e de expressão, só a continuação
            continua = _CONTINUACAO.match(s, i)
            if not continua:
                return None
            i = continua.end()
        elif c == "\n":
            if anterior not in (None, "\n") and anterior not in _AWK_NL_IGNORADA:
                simbolos.append("\n")
            i += 1
        elif c == "#":  # comentário até a quebra de linha, sem continuação (no gawk e no mawk)
            fim = s.find("\n", i)
            i = len(s) if fim < 0 else fim
        elif c == '"':
            i = _fim_da_cadeia(s, i + 1)
            if i is None:
                return None
            simbolos.append(CADEIA)
        elif c == "/" and not _operando(anterior, leitura):
            i = _fim_da_expressao(s, i + 1, leitura)
            if i is None:
                return None
            simbolos.append(EXPRESSAO)
        elif c == "/":
            igual = s[i + 1:i + 2] == "="
            simbolos.append("/=" if igual else "/")
            i += 2 if igual else 1
        elif (achado := _AWK_NOME.match(s, i) or _AWK_NUMERO.match(s, i) or _AWK_OPERADOR.match(s, i)):
            simbolo, i = achado[0], achado.end()
            if simbolo[0].isdigit() or simbolo[0] == ".":
                simbolo = NUMERO
            elif simbolo == "(":
                condicoes.append(anterior in ("if", "while", "for", "switch"))
            elif simbolo == ")":
                simbolo = CONDICAO if condicoes and condicoes.pop() else ")"
            elif simbolo in ("++", "--") and _operando(anterior, "gawk"):
                simbolo = SUFIXO
            simbolos.append(simbolo)
        else:
            return None
    return simbolos


def _redireciona(simbolos: list[str], k: int) -> bool:
    """O print ou printf que começa em `k` tem > >> | ou |&. O > dentro de parênteses é comparação, como no gawk; o
    comando vai até ; { } ou quebra de linha fora de parênteses."""
    profundidade = 0
    for simbolo in simbolos[k:]:
        if simbolo == "(":
            profundidade += 1
        elif simbolo in (")", CONDICAO):
            profundidade -= 1
        elif simbolo in ("|", "|&", ">>") or (simbolo == ">" and profundidade <= 0):
            return True
        elif simbolo in (";", "\n", "{", "}") and profundidade <= 0:
            return False
    return False


def _es_nos_simbolos(simbolos: list[str]) -> bool:
    for k, simbolo in enumerate(simbolos):
        if simbolo in ("system", "getline", "ARGV", "SYMTAB"):
            return True
        if simbolo == "@" and simbolos[k + 1:k + 2] not in ([EXPRESSAO], ["namespace"]):
            return True
        if simbolo in ("print", "printf") and _redireciona(simbolos, k + 1):
            return True
    return False


def awk_com_es(programa: str) -> bool:
    """O programa de awk roda comando ou lê e grava arquivo (ver o cabeçalho): no texto cru ou em uma das três leituras
    dos símbolos."""
    if _AWK_CRU.search(_CONTINUACAO.sub("", programa)):
        return True
    for leitura in _AWK_LEITURAS:
        simbolos = _simbolos(programa, leitura)
        if simbolos is None or _es_nos_simbolos(simbolos):
            return True
    return False
