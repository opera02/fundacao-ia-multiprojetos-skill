#!/usr/bin/env python3
"""Casamento de domínios da jaula (1.7.11, lote L3; DESENHO-JAULA §3.1, regra 2; DECISAO-010, item 5).

Uma regra só para o proxy de lista (`proxy_lista.py`) e para o que a jaula entrega ao navegador e ao Codex: a mesma do
`assets/hooks/guarda_rede.py` (host normalizado, nomes proibidos sempre, lista) e do `cobre` do kit
(`assets/fundacao-kit/fundacao/core/aberturas_regras.py`). O código da jaula roda de uma cópia de dono root que não
carrega o kit nem os hooks, por isso esta é uma CÓPIA, e o `test_dominios_ficha.py` a compara com as duas numa tabela
comum: se uma das três mudar, o teste quebra.

Regra (DECISAO-010, item 5): `x` casa só `x`; `*.x` casa `x` e todo subdomínio de `x`; nunca `outrox` nem `x.outro`.
Entrada inválida da lista (porta, barra, curinga no meio, `*.com` de um rótulo só, nome local ou IP) é ignorada: não
libera nada. Só biblioteca padrão.
"""

from __future__ import annotations

import ipaddress
import re
import unicodedata

ROTULO = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
NUMERICO = re.compile(r"(?:0x[0-9a-f]*|[0-9]+)\Z")
SUFIXOS_LOCAIS = ("localhost", "local", "internal")


def host_normalizado(texto) -> str | None:
    """Nome de host em minúsculas e ASCII (IDNA), sem o ponto final; None se não for um nome DNS aceitável.
    Cópia de `guarda_rede.host_normalizado`: nome internacional só se a ida e a volta do codec idna do Python devolvem
    o mesmo nome (ß, ς e letra posterior ao Unicode 3.2 ficam de fora)."""
    if not isinstance(texto, str) or not texto or any(c in texto for c in "%[]:@/\\ ") or not texto.isprintable():
        return None
    nome = texto.lower()
    nome = nome[:-1] if nome.endswith(".") else nome
    if not nome.isascii():
        if any(unicodedata.ucd_3_2_0.category(c) == "Cn" for c in nome):
            return None
        try:
            ascii_ = nome.encode("idna").decode("ascii")
            if ascii_.encode("ascii").decode("idna") != nome:
                return None
        except UnicodeError:
            return None
        nome = ascii_
    rotulos = nome.split(".")
    if len(nome) > 253 or not all(ROTULO.fullmatch(r) for r in rotulos):
        return None
    return nome


def proibido_sempre(host: str) -> str | None:
    """Tetos fixos que nenhuma lista abre: IP literal (inclusive `2130706433` ou `0x7f.1`) e nomes locais."""
    try:
        ipaddress.ip_address(host)
        return "IP literal"
    except ValueError:
        pass
    if NUMERICO.fullmatch(host.rsplit(".", 1)[-1]):
        return "IP literal (forma numérica)"
    if host in SUFIXOS_LOCAIS or any(host.endswith("." + s) for s in SUFIXOS_LOCAIS):
        return "nome local"
    return None


def lista_de_dominios(entradas) -> tuple[set[str], set[str]]:
    """(exatos, bases de `*.base`) da lista; `entradas` é o texto com vírgulas do FUNDACAO_DOMINIOS_WEB ou uma
    sequência de textos. Entrada inválida fica fora (não libera nada)."""
    if isinstance(entradas, str):
        entradas = entradas.split(",")
    exatos, curingas = set(), set()
    for item in entradas or ():
        if not isinstance(item, str):
            continue
        item = item.strip()
        curinga = item.startswith("*.")
        nome = host_normalizado(item[2:] if curinga else item)
        if nome is None or proibido_sempre(nome):
            continue
        if curinga:
            if "." in nome:  # `*.com` (um rótulo só) não vale
                curingas.add(nome)
        else:
            exatos.add(nome)
    return exatos, curingas


def cobre(entrada: str, host: str) -> bool:
    """A entrada (`x` ou `*.x`) cobre o host já normalizado? A mesma regra do `aberturas_regras.cobre` do kit."""
    if not isinstance(entrada, str) or not isinstance(host, str):
        return False
    if entrada.startswith("*."):
        base = entrada[2:]
        return bool(base) and (host == base or host.endswith("." + base))
    return host == entrada


def casa(host_bruto, entradas) -> bool:
    """O host (como veio do CONNECT, da URL ou do SNI) está na lista? Normaliza, recusa IP e nome local sempre e confere
    a lista. É a decisão do `guarda_rede.decide` para o host, sem a conferência da URL."""
    host = host_normalizado(host_bruto)
    if host is None or proibido_sempre(host):
        return False
    exatos, curingas = entradas if isinstance(entradas, tuple) else lista_de_dominios(entradas)
    return host in exatos or host in curingas or any(host.endswith("." + base) for base in curingas)


def expandir_curingas(dominios) -> list[str]:
    """Cada `*.x` vira `x` e `*.x`, nessa ordem, sem repetir (a do kit e a do preparo). Idempotente."""
    saida: list[str] = []
    for d in dominios:
        for item in ((d[2:], d) if isinstance(d, str) and d.startswith("*.") else (d,)):
            if item not in saida:
                saida.append(item)
    return saida


def exemplo_concreto(entradas) -> str | None:
    """Um nome da lista que se pode usar num CONNECT (o canário): o primeiro exato; senão, a base de um curinga."""
    exatos, curingas = lista_de_dominios(entradas)
    for nome in sorted(exatos) + sorted(curingas):
        return nome
    return None
