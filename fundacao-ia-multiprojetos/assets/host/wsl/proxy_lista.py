#!/usr/bin/env python3
"""Proxy de lista da jaula (1.7.11, lote L3; DESENHO-JAULA §3.1 e §3.2): só biblioteca padrão, asyncio.

Roda como o usuário `fundacao-jaula`, FORA da jaula, iniciado pela entrada fixa (`jaula-entrar`) a cada pedido e
encerrado com ela. Escuta só num socket Unix de uma pasta 0700; dentro da jaula (sem rede, só o `lo` próprio) um
`socat` liga `127.0.0.1:3128` a esse socket. Regras, nesta ordem, sem exceção:
 1. só `CONNECT host:443` e `GET http://host/...` (forma absoluta, porta 80); outro método, outra porta, IP literal
    (v4, v6, formas numéricas abreviadas), nome local ou caractere fora de `[a-z0-9.-]`: 403;
 2. o NOME tem de estar na lista do modo ANTES de qualquer DNS (`dominios_ficha.casa`: `x` só `x`; `*.x` casa `x` e os
    subdomínios; nunca `outrox` nem `x.outro`);
 3. resolve UMA vez e recusa se QUALQUER endereço devolvido for loopback, privado, link-local, CGNAT, ULA, multicast,
    reservado, não especificado, IPv4 mapeado em IPv6 ou NAT64 de endereço proibido (a resposta mista também);
 4. conecta ao IP já resolvido; não resolve de novo (fecha o rebinding);
 5. CONNECT: o SNI do primeiro ClientHello tem de ser igual ao host do CONNECT; sem SNI, com SNI diferente, com ECH ou
    ESNI: a conexão fecha antes de qualquer byte ir ao destino;
 6. tetos: 64 conexões ao mesmo tempo, 10 minutos por conexão e um teto de bytes por pedido;
 7. registro SEM conteúdo (hora, pedido, host, porta, decisão, motivo, bytes) em `registro.jsonl`.
Limites rotulados: não vê o cabeçalho `Host` dentro do TLS (fronting por `Host` num servidor que atende vários nomes
fica de fora, porque o proxy não intercepta o TLS); o ECH que o Chromium envia como GREASE também é recusado pela
regra 5, então o invólucro do Chromium da jaula (L5) tem de desligar o ECH (`--disable-features=EncryptedClientHello`);
a conexão fica aberta até 10 minutos, e HTTP/2 e WebSocket dentro do CONNECT são a medida M8, ainda não feita.

  python3 -I -B proxy_lista.py servir --socket <arq> --dominios a,b,*.c [--registro <arq>] [--pedido <id>]
                                       [--teto-bytes N] [--pai <pid>]
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import ipaddress
import json
import os
import re
import signal
import socket
import stat
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
LIMITE_CABECALHO = 8192
PRAZO_CABECALHO_S = 10
PRAZO_CLIENTHELLO_S = 5
PRAZO_DNS_S = 5
PRAZO_CONECTAR_S = 10
PRAZO_CONEXAO_S = 600
MAX_CONEXOES = 64
MAX_REGISTROS_CLIENTHELLO = 4
LIMITE_CLIENTHELLO = 32768
TETO_BYTES_PADRAO = 64 * 1024 * 1024
BLOCO = 1 << 16
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
# Extensões do ClientHello que escondem o nome verdadeiro: encrypted_client_hello (final e rascunhos) e ESNI.
EXTENSOES_ECH = frozenset({0xFE0D, 0xFE0C, 0xFE0B, 0xFE0A, 0xFE09, 0xFE08, 0xFD00, 0xFFCE})
CARACTERES_DO_NOME = re.compile(r"[A-Za-z0-9.-]+\Z")
TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")
PORTA = re.compile(r"[0-9]{1,5}\Z")
SOMENTE_DOS_HOPS = frozenset({"proxy-connection", "proxy-authorization", "connection", "keep-alive", "host", "upgrade",
                              "te", "trailer", "transfer-encoding", "content-length", "expect"})
FRASES = {200: "Connection Established", 400: "Bad Request", 403: "Forbidden", 502: "Bad Gateway",
          503: "Service Unavailable", 504: "Gateway Timeout"}


def _irmao(nome: str):
    """Um módulo ao lado deste, pelo caminho (com `-I` a pasta do script não entra no `sys.path`)."""
    spec = importlib.util.spec_from_file_location(f"_proxy_lista_{nome}", AQUI / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


DOM = _irmao("dominios_ficha")


class Recusa(Exception):
    """Recusa do pedido. `codigo` 0: só fecha a conexão (já foi respondido 200 ao CONNECT)."""

    def __init__(self, codigo: int, motivo: str, slug: str = "recusado"):
        super().__init__(motivo)
        self.codigo, self.motivo, self.slug = codigo, motivo, slug


# --- endereços ---------------------------------------------------------------------------------------------------
_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_NAT64_LOCAL = ipaddress.ip_network("64:ff9b:1::/48")
_6A4 = ipaddress.ip_network("2002::/16")


def ip_proibido(texto) -> str | None:
    """Motivo pelo qual o endereço não pode ser destino, ou None (global e comum)."""
    try:
        ip = ipaddress.ip_address(str(texto).split("%", 1)[0])
    except ValueError:
        return "endereço ilegível"
    return _motivo_do_ip(ip)


def _motivo_do_ip(ip) -> str | None:
    if ip.is_unspecified:
        return "endereço não especificado"
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link-local"
    if ip.is_multicast:
        return "multicast"
    if ip.version == 4 and ip in _CGNAT:
        return "CGNAT (100.64/10)"
    if ip.is_private:
        return "endereço privado"
    if ip.version == 6:
        if ip.ipv4_mapped is not None:
            return "IPv4 mapeado em IPv6"
        if ip in _NAT64:
            interno = _motivo_do_ip(ipaddress.IPv4Address(ip.packed[-4:]))
            return f"NAT64 de {interno}" if interno else None
        if ip in _NAT64_LOCAL:
            return "NAT64 de uso local"
        if ip in _6A4:
            interno = _motivo_do_ip(ipaddress.IPv4Address(ip.packed[2:6]))
            return f"6to4 de {interno}" if interno else None
    if ip.is_reserved:
        return "endereço reservado"
    if not ip.is_global:
        return "endereço não global"
    return None


# --- pedido HTTP -------------------------------------------------------------------------------------------------
def analisar_cabecalho(bruto: bytes) -> tuple[str, str, list[tuple[str, str]]]:
    """(método, alvo, cabeçalhos) do início do pedido; Recusa 400 se não for HTTP/1.x bem formado."""
    texto = bruto.decode("latin-1")
    linhas = texto.split("\r\n")
    if linhas[-2:] != ["", ""]:
        raise Recusa(400, "cabeçalho sem o fim esperado", "cabecalho")
    linhas = linhas[:-2]
    if not linhas or any(any(ord(c) < 32 or ord(c) == 127 for c in linha) for linha in linhas):
        raise Recusa(400, "cabeçalho com caractere de controle", "cabecalho")
    partes = linhas[0].split(" ")
    if len(partes) != 3 or partes[2] not in ("HTTP/1.0", "HTTP/1.1") or not TOKEN.fullmatch(partes[0]) or not partes[1]:
        raise Recusa(400, "linha de pedido malformada", "cabecalho")
    cabecalhos = []
    for linha in linhas[1:]:
        nome, dois_pontos, valor = linha.partition(":")
        if not dois_pontos or not TOKEN.fullmatch(nome):
            raise Recusa(400, "cabeçalho malformado", "cabecalho")
        cabecalhos.append((nome, valor.strip(" \t")))
    return partes[0], partes[1], cabecalhos


def _destino_connect(alvo: str) -> tuple[str, int]:
    nome, dois_pontos, porta = alvo.rpartition(":")
    if not dois_pontos or not nome or not PORTA.fullmatch(porta) or any(c in nome for c in "[]@/?# "):
        raise Recusa(403, "CONNECT sem host:porta de nome (IP literal, IPv6 e usuário não passam)", "alvo")
    return nome, int(porta)


def _destino_get(alvo: str) -> tuple[str, int, str]:
    if alvo[:7].lower() != "http://":
        raise Recusa(403, "só GET na forma absoluta http://host/...", "metodo")
    resto = alvo[7:]
    fim = min((i for i in (resto.find("/"), resto.find("?"), resto.find("#")) if i >= 0), default=len(resto))
    autoridade, caminho = resto[:fim], resto[fim:] or "/"
    if "#" in caminho or any(c in autoridade for c in "[]@ ") or not autoridade:
        raise Recusa(403, "URL com fragmento, usuário, colchetes ou espaço", "alvo")
    if caminho.startswith("?"):
        caminho = "/" + caminho
    nome, dois_pontos, porta = autoridade.partition(":")
    if dois_pontos and not PORTA.fullmatch(porta):
        raise Recusa(403, "porta ilegível", "porta")
    return nome, int(porta) if dois_pontos else 80, caminho


class Politica:
    """O que o proxy decide e usa: a lista, o resolvedor, o conector, os tetos e o registro. `resolver(host, porta)` devolve
    a lista de endereços (texto); `conectar(ip, porta)` devolve (leitor, escritor): trocáveis nos testes."""

    def __init__(self, dominios, *, resolver=None, conectar=None, teto_bytes: int = TETO_BYTES_PADRAO,
                 registro: str | None = None, pedido: str = "", max_conexoes: int = MAX_CONEXOES,
                 recusar_ech: bool = True, prazo_conexao_s: float = PRAZO_CONEXAO_S,
                 prazo_clienthello_s: float = PRAZO_CLIENTHELLO_S):
        self.lista = DOM.lista_de_dominios(dominios)
        self.resolver = resolver or resolver_padrao
        self.conectar = conectar or conectar_padrao
        self.teto_bytes, self.registro, self.pedido = teto_bytes, registro, pedido
        self.max_conexoes, self.recusar_ech = max_conexoes, recusar_ech
        self.prazo_conexao_s, self.prazo_clienthello_s = prazo_conexao_s, prazo_clienthello_s
        self.ativas, self.bytes_totais = 0, 0

    def registrar(self, host, porta, decisao: str, motivo: str, nbytes: int) -> None:
        if not self.registro:
            return
        linha = json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "pedido": self.pedido,
                            "host": ascii(host)[:120] if host is not None else None, "porta": porta,
                            "decisao": decisao, "motivo": motivo, "bytes": nbytes}, ensure_ascii=True) + "\n"
        try:
            fd = os.open(self.registro, os.O_WRONLY | os.O_APPEND | os.O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0o600)
            try:
                os.write(fd, linha.encode("ascii"))
            finally:
                os.close(fd)
        except OSError:
            pass


async def resolver_padrao(host: str, porta: int) -> list[str]:
    infos = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(
        host, porta, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP), PRAZO_DNS_S)
    vistos: list[str] = []
    for _fam, _tipo, _proto, _canon, sockaddr in infos:
        if sockaddr[0] not in vistos:
            vistos.append(sockaddr[0])
    return vistos


async def conectar_padrao(ip: str, porta: int):
    return await asyncio.wait_for(asyncio.open_connection(ip.split("%", 1)[0], porta), PRAZO_CONECTAR_S)


def conferir_nome(politica: Politica, metodo_connect: bool, host_bruto: str, porta: int) -> str:
    """Regras 1 e 2, antes de qualquer DNS: devolve o host normalizado ou levanta Recusa 403."""
    if porta != (443 if metodo_connect else 80):
        raise Recusa(403, f"porta {porta} fora da padrão do método", "porta")
    if not CARACTERES_DO_NOME.fullmatch(host_bruto):
        raise Recusa(403, "nome com caractere fora de [a-z0-9.-] (IP literal, IPv6, usuário, internacional)", "nome")
    host = DOM.host_normalizado(host_bruto)
    if host is None:
        raise Recusa(403, "nome malformado", "nome")
    proibido = DOM.proibido_sempre(host)
    if proibido:
        raise Recusa(403, proibido, "ip-ou-local")
    if not DOM.casa(host, politica.lista):
        raise Recusa(403, "domínio fora da lista do modo", "fora-da-lista")
    return host


async def resolver_e_conferir(politica: Politica, host: str, porta: int) -> list[str]:
    """Regras 3 e 4: resolve UMA vez; recusa se qualquer endereço for proibido; devolve os endereços para conectar."""
    try:
        ips = await politica.resolver(host, porta)
    except (OSError, asyncio.TimeoutError, TimeoutError):
        raise Recusa(502, "o nome não resolveu", "dns") from None
    if not ips:
        raise Recusa(502, "o nome não resolveu", "dns")
    for ip in ips:
        motivo = ip_proibido(ip)
        if motivo:
            raise Recusa(403, f"o nome resolve para {motivo}", "ip-proibido")
    return list(ips)


async def abrir_destino(politica: Politica, ips: list[str], porta: int):
    erro = None
    for ip in ips:
        try:
            return await politica.conectar(ip, porta)
        except (OSError, asyncio.TimeoutError, TimeoutError) as exc:
            erro = exc
    raise Recusa(502, "não conectou ao destino" + (f" ({type(erro).__name__})" if erro else ""), "conexao")


# --- ClientHello (regra 5) ---------------------------------------------------------------------------------------
def analisar_clienthello(hs: bytes) -> tuple[str | None, bool]:
    """(server_name, tem ECH/ESNI) do handshake ClientHello completo. ValueError se malformado ou se o nome repetir."""
    if len(hs) < 4 or hs[0] != 1:
        raise ValueError("não é um ClientHello")
    tamanho = int.from_bytes(hs[1:4], "big")
    corpo = hs[4:]
    if len(corpo) != tamanho:
        raise ValueError("ClientHello incompleto ou com bytes a mais")
    pos = 0

    def ler(n: int) -> bytes:
        nonlocal pos
        if n < 0 or pos + n > len(corpo):
            raise ValueError("ClientHello truncado")
        pedaco = corpo[pos:pos + n]
        pos += n
        return pedaco

    ler(2)
    ler(32)
    ler(ler(1)[0])
    ler(int.from_bytes(ler(2), "big"))
    ler(ler(1)[0])
    if pos == len(corpo):
        return None, False
    extensoes = ler(int.from_bytes(ler(2), "big"))
    if pos != len(corpo):
        raise ValueError("bytes depois das extensões")
    nome, ech, vistos, i = None, False, set(), 0
    while i < len(extensoes):
        if i + 4 > len(extensoes):
            raise ValueError("extensão truncada")
        tipo = int.from_bytes(extensoes[i:i + 2], "big")
        n = int.from_bytes(extensoes[i + 2:i + 4], "big")
        dado = extensoes[i + 4:i + 4 + n]
        if len(dado) < n or tipo in vistos:
            raise ValueError("extensão truncada ou repetida")
        vistos.add(tipo)
        i += 4 + n
        if tipo in EXTENSOES_ECH:
            ech = True
        elif tipo == 0:
            lista = int.from_bytes(dado[:2], "big")
            if len(dado) != 2 + lista or lista < 3 or dado[2] != 0:
                raise ValueError("server_name malformado")
            tam = int.from_bytes(dado[3:5], "big")
            if 5 + tam != len(dado) or tam == 0:
                raise ValueError("server_name malformado ou com mais de um nome")
            try:
                nome = dado[5:].decode("ascii")
            except UnicodeDecodeError:
                raise ValueError("server_name fora do ASCII") from None
    return nome, ech


async def ler_clienthello(leitor: asyncio.StreamReader) -> tuple[bytes, str | None, bool]:
    """Lê o primeiro ClientHello (um ou mais registros TLS, até LIMITE_CLIENTHELLO). Devolve (bytes lidos, SNI, ECH)."""
    brutos, handshake = bytearray(), bytearray()
    for _ in range(MAX_REGISTROS_CLIENTHELLO):
        cab = await leitor.readexactly(5)
        if cab[0] != 0x16 or cab[1] != 3:
            raise Recusa(0, "o cliente não começou com um registro TLS de handshake", "tls")
        n = int.from_bytes(cab[3:5], "big")
        if n == 0 or n > 16384 + 256 or len(brutos) + 5 + n > LIMITE_CLIENTHELLO:
            raise Recusa(0, "registro TLS fora do tamanho", "tls")
        corpo = await leitor.readexactly(n)
        brutos += cab + corpo
        handshake += corpo
        if len(handshake) >= 4 and len(handshake) >= 4 + int.from_bytes(handshake[1:4], "big"):
            break
    try:
        nome, ech = analisar_clienthello(bytes(handshake))
    except ValueError as exc:
        raise Recusa(0, f"ClientHello ilegível ({exc})", "tls") from None
    return bytes(brutos), nome, ech


# --- conexão -----------------------------------------------------------------------------------------------------
class _Contagem:
    def __init__(self):
        self.bytes = 0


async def _bombear(origem, destino, politica: Politica, conta: _Contagem) -> None:
    try:
        while True:
            bloco = await origem.read(BLOCO)
            if not bloco:
                break
            conta.bytes += len(bloco)
            politica.bytes_totais += len(bloco)
            if politica.bytes_totais > politica.teto_bytes:
                raise Recusa(0, "teto de bytes do pedido", "teto")
            destino.write(bloco)
            await destino.drain()
    finally:
        try:
            if destino.can_write_eof():
                destino.write_eof()
        except (OSError, RuntimeError, AttributeError):
            pass


async def _relay(politica: Politica, leitor, escritor, leitor_up, escritor_up, conta: _Contagem) -> None:
    tarefas = [asyncio.ensure_future(_bombear(leitor, escritor_up, politica, conta)),
               asyncio.ensure_future(_bombear(leitor_up, escritor, politica, conta))]
    try:
        await asyncio.wait_for(asyncio.gather(*tarefas), politica.prazo_conexao_s)
    except asyncio.TimeoutError:
        raise Recusa(0, "prazo da conexão (10 minutos)", "prazo") from None
    finally:
        for t in tarefas:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tarefas, return_exceptions=True)


def _resposta(codigo: int, slug: str) -> bytes:
    return (f"HTTP/1.1 {codigo} {FRASES.get(codigo, 'Error')}\r\nConnection: close\r\nContent-Length: 0\r\n"
            f"X-Jaula-Recusa: {slug}\r\n\r\n").encode("ascii")


def _fechar(escritor) -> None:
    try:
        escritor.close()
    except (OSError, RuntimeError):
        pass


async def _atender(politica: Politica, leitor, escritor, ctx: dict, conta: _Contagem) -> str:
    try:
        cabecalho = await asyncio.wait_for(leitor.readuntil(b"\r\n\r\n"), PRAZO_CABECALHO_S)
    except (asyncio.LimitOverrunError, ValueError):
        raise Recusa(400, "cabeçalho grande demais", "cabecalho") from None
    except asyncio.IncompleteReadError:
        raise Recusa(400, "conexão fechada antes do fim do cabeçalho", "cabecalho") from None
    except asyncio.TimeoutError:
        raise Recusa(400, "prazo do cabeçalho", "cabecalho") from None
    metodo, alvo, cabecalhos = analisar_cabecalho(cabecalho)
    if metodo == "CONNECT":
        host_bruto, porta = _destino_connect(alvo)
        caminho = None
    elif metodo == "GET":
        host_bruto, porta, caminho = _destino_get(alvo)
    else:
        raise Recusa(403, f"método {metodo} não passa (só CONNECT :443 e GET http:// na porta 80)", "metodo")
    ctx["host"], ctx["porta"] = host_bruto, porta
    host = conferir_nome(politica, metodo == "CONNECT", host_bruto, porta)
    ctx["host"] = host
    if caminho is not None:
        nomes = {n.lower() for n, _v in cabecalhos}
        if "transfer-encoding" in nomes or any(n.lower() == "content-length" and v != "0" for n, v in cabecalhos):
            raise Recusa(403, "GET com corpo não passa", "corpo")
    ips = await resolver_e_conferir(politica, host, porta)
    if caminho is None:
        escritor.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await escritor.drain()
        try:
            brutos, sni, ech = await asyncio.wait_for(ler_clienthello(leitor), politica.prazo_clienthello_s)
        except (asyncio.IncompleteReadError, asyncio.TimeoutError):
            raise Recusa(0, "o cliente não enviou o ClientHello", "tls") from None
        if ech and politica.recusar_ech:
            raise Recusa(0, "ClientHello com ECH/ESNI (esconde o nome)", "ech")
        nome_tls = DOM.host_normalizado(sni) if sni else None
        if nome_tls is None:
            raise Recusa(0, "ClientHello sem SNI utilizável", "sni-ausente")
        if nome_tls != host:
            raise Recusa(0, "SNI diferente do host do CONNECT", "sni-diferente")
        try:
            leitor_up, escritor_up = await abrir_destino(politica, ips, porta)
        except Recusa as exc:
            raise Recusa(0, exc.motivo, exc.slug) from None  # o 200 já foi dado: só fecha
        try:
            escritor_up.write(brutos)
            await escritor_up.drain()
            await _relay(politica, leitor, escritor, leitor_up, escritor_up, conta)
        finally:
            _fechar(escritor_up)
        return "túnel TLS com SNI conferido"
    leitor_up, escritor_up = await abrir_destino(politica, ips, porta)
    try:
        omitidos = SOMENTE_DOS_HOPS
        linhas = [f"GET {caminho} HTTP/1.1", f"Host: {host}"]
        linhas += [f"{n}: {v}" for n, v in cabecalhos if n.lower() not in omitidos]
        escritor_up.write(("\r\n".join(linhas) + "\r\nConnection: close\r\n\r\n").encode("latin-1"))
        await escritor_up.drain()
        await _relay(politica, leitor, escritor, leitor_up, escritor_up, conta)
    finally:
        _fechar(escritor_up)
    return "GET http na porta 80"


async def atender(politica: Politica, leitor, escritor) -> None:
    """Uma conexão do cliente (a da jaula): nunca derruba o servidor; toda saída deixa uma linha no registro."""
    ctx: dict = {"host": None, "porta": None}
    conta = _Contagem()
    decisao, motivo = "recusado", "erro interno"
    if politica.ativas >= politica.max_conexoes:
        politica.registrar(None, None, "recusado", "mais conexões que o teto", 0)
        try:
            escritor.write(_resposta(503, "conexoes"))
            await escritor.drain()
        except (OSError, RuntimeError):
            pass
        _fechar(escritor)
        return
    politica.ativas += 1
    try:
        motivo = await _atender(politica, leitor, escritor, ctx, conta)
        decisao = "permitido"
    except Recusa as exc:
        motivo = exc.motivo
        if exc.codigo:
            try:
                escritor.write(_resposta(exc.codigo, exc.slug))
                await escritor.drain()
            except (OSError, RuntimeError):
                pass
    except (ConnectionError, OSError, asyncio.IncompleteReadError):
        motivo = "conexão interrompida"
        decisao = "permitido" if conta.bytes else "recusado"
    except asyncio.CancelledError:
        motivo = "encerrado com o proxy"
        raise
    except Exception as exc:  # noqa: BLE001 — pedido hostil não derruba o proxy
        motivo = f"erro inesperado ({type(exc).__name__})"
    finally:
        politica.ativas -= 1
        politica.registrar(ctx["host"], ctx["porta"], decisao, motivo, conta.bytes)
        _fechar(escritor)


# --- servidor, registro e linha de comando -----------------------------------------------------------------------
def resumir_registro(caminho: str, pedido: str) -> dict:
    """Do registro: o resumo das conexões do pedido (para a resposta da jaula); sem conteúdo."""
    total, permitidas, recusas = 0, 0, {}
    try:
        with open(caminho, "r", encoding="ascii", errors="replace") as f:
            for linha in f:
                try:
                    r = json.loads(linha)
                except ValueError:
                    continue
                if not isinstance(r, dict) or r.get("pedido") != pedido:
                    continue
                total += 1
                if r.get("decisao") == "permitido":
                    permitidas += 1
                else:
                    chave = (str(r.get("host")), str(r.get("porta")), str(r.get("motivo")))
                    recusas[chave] = recusas.get(chave, 0) + 1
    except OSError:
        pass
    return {"conexoes": total, "permitidas": permitidas,
            "recusas": [{"host": h, "porta": p, "motivo": m, "n": n} for (h, p, m), n in sorted(recusas.items())][:50]}


def preparar_socket(caminho: str) -> None:
    """Tira só um socket velho deste caminho (nunca arquivo comum, pasta ou ligação)."""
    try:
        st = os.lstat(caminho)
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(st.st_mode):
        raise SystemExit(f"{caminho} existe e não é um socket: nada foi apagado")
    os.unlink(caminho)


async def servir(politica: Politica, *, caminho: str | None = None, host: str | None = None, porta: int = 0,
                 pronto: asyncio.Event | None = None, parar: asyncio.Event | None = None, ligado: list | None = None):
    """Escuta no socket Unix `caminho` (jaula) ou em `host:porta` TCP (só para testes) até `parar`."""
    async def cliente(leitor, escritor):
        await atender(politica, leitor, escritor)

    if caminho:
        preparar_socket(caminho)
        anterior = os.umask(0o177)
        try:
            servidor = await asyncio.start_unix_server(cliente, path=caminho, limit=LIMITE_CABECALHO)
        finally:
            os.umask(anterior)
        os.chmod(caminho, 0o600)
    else:
        servidor = await asyncio.start_server(cliente, host or "127.0.0.1", porta, limit=LIMITE_CABECALHO)
    if ligado is not None:
        ligado.extend(s.getsockname() for s in servidor.sockets)
    if pronto is not None:
        pronto.set()
    try:
        await (parar or asyncio.Event()).wait()
    finally:
        servidor.close()
        await servidor.wait_closed()
        if caminho:
            try:
                os.unlink(caminho)
            except OSError:
                pass


def _morrer_com_o_pai(pai: int) -> None:
    """Linux: o proxy morre junto com a entrada fixa (SIGTERM do kernel) e sai se ela já morreu."""
    try:
        import ctypes
        ctypes.CDLL(None, use_errno=True).prctl(1, int(signal.SIGTERM), 0, 0, 0)  # PR_SET_PDEATHSIG
    except (OSError, AttributeError):
        pass
    if pai and os.getppid() != pai:
        raise SystemExit("a entrada fixa já morreu")


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(prog="proxy_lista.py", allow_abbrev=False, description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("servir", allow_abbrev=False)
    s.add_argument("--socket", required=True)
    s.add_argument("--dominios", required=True, help="lista com vírgulas: x ou *.x")
    s.add_argument("--registro")
    s.add_argument("--pedido", default="")
    s.add_argument("--teto-bytes", type=int, default=TETO_BYTES_PADRAO)
    s.add_argument("--pai", type=int, default=0)
    a = ap.parse_args(argv)
    _morrer_com_o_pai(a.pai)
    politica = Politica(a.dominios, teto_bytes=a.teto_bytes, registro=a.registro, pedido=a.pedido)

    async def principal():
        parar = asyncio.Event()
        for sinal in (signal.SIGTERM, signal.SIGINT):
            asyncio.get_running_loop().add_signal_handler(sinal, parar.set)
        await servir(politica, caminho=a.socket, parar=parar)

    asyncio.run(principal())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
