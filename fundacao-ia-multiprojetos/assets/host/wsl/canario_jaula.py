#!/usr/bin/env python3
"""Canário de dentro da jaula (1.7.11, lote L3; DESENHO-JAULA §3.3): prova, de dentro, o que a caixa promete.

Programa fixo, de dono root, rodado pelo modo `canario` da jaula com as mesmas opções do modo `--como` (navegador,
janela e Codex). Imprime na saída padrão UM relatório `fundacao.canario_jaula/1`, sem valores de segredo, com um item por
prova e o motivo; código 0 se todos aprovam, 1 se algum reprova. Só biblioteca padrão. Itens:
sockets_visiveis, socket_abstrato, rede_direta, proxy_lista, proxy_fora, proxy_ip, proxy_local, proxy_sni, proxy_porta,
proc, fora_montado, escrita, capacidades, tiocsti, userns, ambiente e, no Codex, segredo_da_jaula_invisivel (informativo:
a medida M7 decide o rótulo) e sandbox_codex (sonda M7, informativa: o binário fixado testa o próprio sandbox com
`codex sandbox -- <comando>`; se ele não abre aqui, a medida é `danger-full-access` e a barreira passa a ser só a jaula).

  python3 -I -B canario_jaula.py --como navegador --dominio exemplo.org --raiz /mnt/e/raiz --env PATH,HOME,... \\
      [--isca nome-abstrato] [--userns bloqueado|anotar] [--grafico] [--terminal-proprio] [--codex <binário fixado>]

O relatório vale para a versão: o preparo grava junto o SHA-256 da entrada fixa, do proxy e do bwrap
(`fundacao.canario_jaula_instalado/1`). Itens que dependem do Linux e do bwrap só podem ser provados no ambiente real
(testes L e canário C); as funções puras daqui são testadas em qualquer sistema.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import socket
import stat
import subprocess
import sys
import time

ESQUEMA = "fundacao.canario_jaula/1"
PROXY_LOCAL = ("127.0.0.1", 3128)
SOCKET_DO_PROXY = "/run/jaula/proxy.sock"
SOCKETS_GRAFICOS = ("/run/jaula/wayland-0", "/tmp/.X11-unix/X0")
ABSTRATOS_DO_HOST = ("/tmp/.X11-unix/X0", "/tmp/.ICE-unix/1", "/org/freedesktop/DBus/session", "/run/user/1000/bus")
ENV_DO_SHELL = frozenset({"PWD", "OLDPWD", "SHLVL", "_"})  # o sh -c da ponte pode acrescentar estes nomes
SEM_ROTA = {errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EADDRNOTAVAIL, errno.EAFNOSUPPORT, errno.EACCES, errno.EPERM}
NAO_GRAVA = {errno.EROFS, errno.EACCES, errno.EPERM}
FORA_DE_TODA_FICHA = "example.com"
IPS_PROIBIDOS = ("93.184.215.14:443", "[::1]:443", "127.0.0.1:443")
NOMES_LOCAIS = ("localhost:443", "metadata.google.internal:443", "169.254.169.254:80")


def item(nome: str, aprovado: bool, motivo: str, informativo: bool = False) -> dict:
    return {"id": nome, "aprovado": bool(aprovado), "motivo": motivo, "informativo": informativo}


# --- peças puras (testadas em qualquer sistema) --------------------------------------------------------------------
def montar_clienthello(sni: str | None, ech: bool = False) -> bytes:
    """Um ClientHello mínimo e válido (um registro TLS), com o SNI dado (None: sem a extensão) e, se pedido, uma
    extensão ECH. Só serve para provar que o proxy confere o nome; não negocia nada."""
    ext = b""
    if sni is not None:
        nome = sni.encode("ascii")
        entrada = b"\x00" + len(nome).to_bytes(2, "big") + nome
        lista = len(entrada).to_bytes(2, "big") + entrada
        ext += (0).to_bytes(2, "big") + len(lista).to_bytes(2, "big") + lista
    if ech:
        carga = b"\x00" * 8
        ext += (0xFE0D).to_bytes(2, "big") + len(carga).to_bytes(2, "big") + carga
    corpo = (b"\x03\x03" + os.urandom(32) + b"\x00" + (2).to_bytes(2, "big") + b"\x13\x01" + b"\x01\x00"
             + len(ext).to_bytes(2, "big") + ext)
    handshake = b"\x01" + len(corpo).to_bytes(3, "big") + corpo
    return b"\x16\x03\x01" + len(handshake).to_bytes(2, "big") + handshake


def status_http(bruto: bytes) -> int | None:
    """O código da linha de status (`HTTP/1.x NNN ...`) ou None."""
    linha = bruto.split(b"\r\n", 1)[0].split(b" ")
    if len(linha) >= 2 and linha[0].startswith(b"HTTP/1.") and linha[1].isdigit():
        return int(linha[1])
    return None


def capacidades(texto: str) -> dict:
    """{'CapEff': int, 'CapPrm': int, ...} de /proc/self/status."""
    saida = {}
    for linha in texto.splitlines():
        nome, _, valor = linha.partition(":")
        if nome in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb") and valor.strip():
            saida[nome] = int(valor.strip(), 16)
    return saida


def pid1_e_bwrap(cmdline: bytes) -> bool:
    primeiro = cmdline.split(b"\0", 1)[0]
    return os.path.basename(primeiro.decode("utf-8", "replace")) == "bwrap"


def sockets_inesperados(achados, permitidos) -> list[str]:
    return sorted(set(achados) - set(permitidos))


def env_fora_da_lista(nomes, permitidos) -> list[str]:
    """Nomes (nunca valores) de variável que não estão na lista fixa do modo (o sh da ponte pode somar PWD e afins)."""
    return sorted(set(nomes) - set(permitidos) - ENV_DO_SHELL)


def abstratos_listados(texto_proc_net_unix: str) -> list[str]:
    """Os sockets abstratos (nome começando em '@') de /proc/net/unix: neste namespace de rede só devia haver os da jaula."""
    achados = []
    for linha in texto_proc_net_unix.splitlines()[1:]:
        partes = linha.split()
        if len(partes) >= 8 and partes[7].startswith("@"):
            achados.append(partes[7])
    return achados


# --- provas de dentro da jaula ------------------------------------------------------------------------------------
def achar_sockets(raiz: str = "/", pular=("/proc", "/sys"), teto: int = 400000) -> list[str]:
    pilha, achados, vistos = [raiz], [], 0
    while pilha and vistos < teto:
        pasta = pilha.pop()
        try:
            entradas = list(os.scandir(pasta))
        except OSError:
            continue
        for e in entradas:
            vistos += 1
            if e.path in pular:
                continue
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISSOCK(st.st_mode):
                achados.append(e.path)
            elif stat.S_ISDIR(st.st_mode):
                pilha.append(e.path)
    return sorted(achados)


def prova_sockets_visiveis(grafico: bool) -> dict:
    achados = achar_sockets()
    permitidos = {SOCKET_DO_PROXY, *(SOCKETS_GRAFICOS if grafico else ())}
    extras = sockets_inesperados(achados, permitidos)
    if extras:
        return item("sockets_visiveis", False, "socket visível fora do permitido: " + ", ".join(extras[:5]))
    if SOCKET_DO_PROXY not in achados:
        return item("sockets_visiveis", False, "o socket do proxy não está montado em /run/jaula/proxy.sock")
    return item("sockets_visiveis", True, "só o socket do proxy" + (" e o gráfico montado" if grafico else ""))


def prova_socket_abstrato(isca: str | None) -> dict:
    try:
        with open("/proc/net/unix", "r", errors="replace") as f:
            listados = abstratos_listados(f.read())
    except OSError:
        listados = []
    if listados:
        return item("socket_abstrato", False, "há socket abstrato neste namespace de rede: " + ", ".join(listados[:5]))
    alvos = list(ABSTRATOS_DO_HOST) + ([isca] if isca else [])
    for nome in alvos:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        try:
            s.connect("\0" + nome.lstrip("\0"))
            return item("socket_abstrato", False, f"conectou ao socket abstrato do host: {nome}")
        except OSError:
            pass
        finally:
            s.close()
    return item("socket_abstrato", True, f"{len(alvos)} sockets abstratos do host recusados" + (", inclusive a isca criada antes de entrar" if isca else ""))


def prova_rede_direta() -> dict:
    tentativas = [("tcp 1.1.1.1:443", socket.AF_INET, socket.SOCK_STREAM, ("1.1.1.1", 443)),
                  ("tcp [2606:4700::1111]:443", socket.AF_INET6, socket.SOCK_STREAM, ("2606:4700::1111", 443)),
                  ("udp 8.8.8.8:53", socket.AF_INET, socket.SOCK_DGRAM, ("8.8.8.8", 53))]
    for nome, familia, tipo, destino in tentativas:
        try:
            s = socket.socket(familia, tipo)
        except OSError as exc:
            if exc.errno in SEM_ROTA:
                continue
            return item("rede_direta", False, f"{nome}: erro ao criar o socket ({exc.errno})")
        s.settimeout(3)
        try:
            s.connect(destino)
            if tipo == socket.SOCK_DGRAM:
                s.send(b"\0")
            return item("rede_direta", False, f"{nome}: saiu para a rede direta")
        except OSError as exc:
            if exc.errno not in SEM_ROTA:
                return item("rede_direta", False, f"{nome}: há rota ({errno.errorcode.get(exc.errno, exc.errno)})")
        finally:
            s.close()
    return item("rede_direta", True, "sem rota para a rede (tcp v4, tcp v6 e udp)")


def pedir_connect(alvo: str, enviar: bytes | None = None, prazo: float = 15.0, proxy=PROXY_LOCAL):
    """CONNECT alvo pelo proxy da jaula. Devolve (status, o que veio depois do cabeçalho, fechou?)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(prazo)
    try:
        s.connect(proxy)
        s.sendall(f"CONNECT {alvo} HTTP/1.1\r\nHost: {alvo}\r\n\r\n".encode("ascii"))
        bruto = b""
        while b"\r\n\r\n" not in bruto and len(bruto) < 8192:
            bloco = s.recv(4096)
            if not bloco:
                break
            bruto += bloco
        status = status_http(bruto)
        resto = bruto.partition(b"\r\n\r\n")[2]
        fechou = False
        if status == 200 and enviar is not None:
            s.sendall(enviar)
            s.settimeout(5)
            try:
                dado = s.recv(4096)
                fechou = not dado
                resto += dado
            except ConnectionError:
                fechou = True
            except socket.timeout:
                fechou = False
        return status, resto, fechou
    finally:
        s.close()


def _recusados(nome: str, alvos, esperado: int = 403) -> dict:
    for alvo in alvos:
        try:
            status, _r, _f = pedir_connect(alvo)
        except OSError as exc:
            return item(nome, False, f"{alvo}: o proxy da jaula não respondeu ({type(exc).__name__})")
        if status != esperado:
            return item(nome, False, f"{alvo}: esperava {esperado} e veio {status}")
    return item(nome, True, f"{len(alvos)} destinos recusados com {esperado}")


def prova_proxy(dominio: str) -> list[dict]:
    if not dominio:
        return [item(n, False, "sem domínio da lista para provar") for n in
                ("proxy_lista", "proxy_fora", "proxy_ip", "proxy_local", "proxy_sni", "proxy_porta")]
    saida = []
    try:
        status, _r, _f = pedir_connect(f"{dominio}:443")
        saida.append(item("proxy_lista", status == 200, f"CONNECT {dominio}:443 -> {status}"))
    except OSError as exc:
        saida.append(item("proxy_lista", False, f"o proxy da jaula não respondeu ({type(exc).__name__})"))
    saida.append(_recusados("proxy_fora", [f"{FORA_DE_TODA_FICHA}:443"]))
    saida.append(_recusados("proxy_ip", IPS_PROIBIDOS))
    saida.append(_recusados("proxy_local", NOMES_LOCAIS))
    try:
        status, resto, fechou = pedir_connect(f"{dominio}:443", enviar=montar_clienthello(FORA_DE_TODA_FICHA))
        ok = status == 200 and fechou and not resto
        saida.append(item("proxy_sni", ok, "SNI de outro nome: " + ("conexão fechada sem resposta" if ok else
                                                                    f"status {status}, fechou={fechou}, bytes={len(resto)}")))
    except OSError as exc:
        saida.append(item("proxy_sni", False, f"o proxy da jaula não respondeu ({type(exc).__name__})"))
    saida.append(_recusados("proxy_porta", [f"{dominio}:22"]))
    return saida


def prova_proc() -> dict:
    try:
        pids = [n for n in os.listdir("/proc") if n.isdigit()]
        with open("/proc/1/cmdline", "rb") as f:
            cmd1 = f.read()
    except OSError as exc:
        return item("proc", False, f"/proc ilegível ({type(exc).__name__})")
    if not pid1_e_bwrap(cmd1):
        return item("proc", False, "o PID 1 não é o bwrap: o /proc mostra processos de fora da jaula")
    return item("proc", len(pids) <= 64, f"{len(pids)} processos visíveis; o PID 1 é o bwrap")


def prova_fora_montado(raiz: str | None) -> dict:
    alvos = ["/mnt", "/mnt/c", "/root", "/etc/fundacao-ia", "/var/lib/fundacao-ia"] + ([raiz] if raiz else [])
    existem = [a for a in alvos if os.path.lexists(a)]
    try:
        casas = [c for c in os.listdir("/home") if c != "jaula"]
    except OSError:
        casas = []
    if existem or casas:
        return item("fora_montado", False, "existe dentro da jaula: " + ", ".join((existem + [f"/home/{c}" for c in casas])[:5]))
    return item("fora_montado", True, f"{len(alvos)} caminhos do host ausentes; /home só tem jaula")


def prova_escrita() -> dict:
    projeto = "/trabalho/projeto" if os.path.isdir("/trabalho/projeto") else "/trabalho"
    alvos = ["/usr", "/etc", projeto, "/run/jaula"]
    for pasta in alvos:
        caminho = f"{pasta}/.jaula-escrita-{os.getpid()}"
        try:
            fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError as exc:
            if exc.errno in NAO_GRAVA:
                continue
            return item("escrita", False, f"{pasta}: erro inesperado ({errno.errorcode.get(exc.errno, exc.errno)})")
        os.close(fd)
        try:
            os.unlink(caminho)
        except OSError:
            pass
        return item("escrita", False, f"{pasta} aceitou escrita")
    return item("escrita", True, "gravação recusada em " + ", ".join(alvos))


def prova_capacidades() -> dict:
    try:
        with open("/proc/self/status", "r") as f:
            caps = capacidades(f.read())
    except OSError as exc:
        return item("capacidades", False, f"/proc/self/status ilegível ({type(exc).__name__})")
    ativas = {k: v for k, v in caps.items() if k in ("CapEff", "CapPrm") and v != 0}
    return item("capacidades", bool(caps) and not ativas, "CapEff e CapPrm zerados" if caps and not ativas else
                f"capacidades ativas ou ilegíveis: {sorted(ativas) or 'nenhuma lida'}")


def prova_tiocsti(terminal_proprio: bool) -> dict:
    try:
        import fcntl
        import termios
    except ImportError:
        return item("tiocsti", False, "termios indisponível")
    try:
        fd = os.open("/dev/tty", os.O_RDWR)
        os.close(fd)
        if not terminal_proprio:
            return item("tiocsti", False, "/dev/tty abriu: a jaula herdou um terminal")
    except OSError:
        pass
    for fd in (0, 1, 2):
        if not os.isatty(fd):
            continue
        try:
            fcntl.ioctl(fd, termios.TIOCSTI, b"x")
        except OSError:
            continue
        if not terminal_proprio:
            return item("tiocsti", False, f"TIOCSTI funcionou no terminal herdado (fd {fd})")
        return item("tiocsti", True, "TIOCSTI funciona só no pty próprio da jaula (modo com terminal)", informativo=True)
    return item("tiocsti", True, "sem terminal herdado ou TIOCSTI recusado")


def prova_userns(esperado: str) -> dict:
    try:
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
    except (OSError, AttributeError):
        return item("userns", False, "libc indisponível")
    pid = os.fork()
    if pid == 0:
        os._exit(0 if libc.unshare(0x10000000) == 0 else 1)  # CLONE_NEWUSER
    _p, estado = os.waitpid(pid, 0)
    criou = os.WIFEXITED(estado) and os.WEXITSTATUS(estado) == 0
    if esperado == "bloqueado":
        return item("userns", not criou, "namespace de usuário aninhado recusado" if not criou else "criou namespace de usuário aninhado")
    return item("userns", True, "namespace de usuário aninhado " + ("permitido (o Chromium precisa; medida M6)" if criou else "recusado"), informativo=True)


# Os prefixos do motivo do item `sandbox_codex` são lidos pela entrada fixa (jaula.SANDBOX_CODEX_*): os textos são os mesmos.
SANDBOX_CODEX_ABERTO = "sandbox próprio do Codex aberto"
SANDBOX_CODEX_RECUSADO = "sandbox próprio do Codex recusado"
PRAZO_DA_SONDA_S = 40


def prova_sandbox_codex(codex: str, rodar=subprocess.run) -> dict:
    """Medida M7: o binário fixado do Codex testa o próprio sandbox DENTRO da jaula (`codex sandbox -- <comando>`, que usa o
    config.toml imposto: workspace-write, sem rede). Aberto: roda ainda dois comandos que um sandbox que confina recusa (rede
    pela ponte do proxy e escrita fora da pasta de trabalho) e diz se confinou. Recusado: o motivo vai no relatório e a medida
    passa a ser `danger-full-access` (sem aprovar nem reprovar o modo: a barreira é só a jaula). Não achar o binário, ou a
    sonda estourar o prazo, REPROVA (nada foi medido) e nunca vira medida."""
    if not codex or not os.path.isfile(codex) or not os.access(codex, os.X_OK):
        return item("sandbox_codex", False, "o binário do Codex fixado não está na jaula: nada foi medido")
    ambiente = {n: os.environ[n] for n in ("PATH", "HOME", "TMPDIR", "LANG", "CODEX_HOME") if n in os.environ}

    def sondar(*comando):
        try:
            r = rodar([codex, "sandbox", "--", *comando], cwd="/trabalho/saida", env=ambiente, stdin=subprocess.DEVNULL,
                      capture_output=True, timeout=PRAZO_DA_SONDA_S)
        except subprocess.TimeoutExpired:
            return None, "passou do prazo"
        except OSError as exc:
            return None, f"não executou ({type(exc).__name__})"
        texto = r.stderr.decode("utf-8", "replace") if isinstance(r.stderr, bytes) else str(r.stderr or "")
        return r.returncode, " ".join("".join(c if c.isprintable() else " " for c in texto).split())[-120:]
    codigo, erro = sondar("/bin/true")
    if codigo is None:
        return item("sandbox_codex", False, f"a sonda do sandbox do Codex falhou ({erro}): nada foi medido")
    if codigo != 0:
        return item("sandbox_codex", True, f"{SANDBOX_CODEX_RECUSADO} (código {codigo}: {erro or 'sem mensagem'}): os comandos do Codex "
                    "rodam sem ele e a barreira é só a jaula", informativo=True)
    fugas = []
    if sondar("/usr/bin/python3", "-I", "-c", "import socket;s=socket.socket();s.settimeout(3);s.connect(('127.0.0.1',3128))")[0] == 0:
        fugas.append("rede")
    if sondar("/bin/sh", "-c", ": > /home/jaula/fora-do-trabalho")[0] == 0:
        fugas.append("escrita fora da pasta de trabalho")
    if fugas:
        return item("sandbox_codex", True, f"{SANDBOX_CODEX_ABERTO}, mas NÃO confinou: {', '.join(fugas)} (a barreira segue sendo a "
                    "jaula)", informativo=True)
    return item("sandbox_codex", True, f"{SANDBOX_CODEX_ABERTO} e confinou a rede e a escrita fora da pasta de trabalho",
                informativo=True)


def prova_ambiente(permitidos) -> dict:
    extras = env_fora_da_lista(os.environ, permitidos)
    return item("ambiente", not extras, "só as variáveis da lista fixa do modo" if not extras else
                "variáveis fora da lista: " + ", ".join(extras[:8]))


def prova_segredo_da_jaula() -> dict:
    """Codex (medida M7): o que um comando do Codex enxerga do segredo. Informativo: o rótulo do limite sai daqui."""
    achados = []
    for base in ("/home", "/trabalho", "/tmp"):
        for pasta, _d, arquivos in os.walk(base):
            achados += [os.path.join(pasta, a) for a in arquivos if a == "auth.json"]
    chaves = 0
    try:
        for n in os.listdir("/proc"):
            if n.isdigit():
                try:
                    with open(f"/proc/{n}/environ", "rb") as f:
                        chaves += sum(1 for v in f.read().split(b"\0") if v.split(b"=", 1)[0].endswith((b"KEY", b"TOKEN")))
                except OSError:
                    pass
    except OSError:
        pass
    return item("segredo_da_jaula_invisivel", True, f"auth.json visível: {len(achados)}; processos com variável de chave "
                f"ou token legível: {chaves} (se houver, o limite fica rotulado: medida M7)", informativo=True)


def executar(a) -> dict:
    provas = [("sockets_visiveis", lambda: [prova_sockets_visiveis(a.grafico)]),
              ("socket_abstrato", lambda: [prova_socket_abstrato(a.isca)]),
              ("rede_direta", lambda: [prova_rede_direta()]),
              ("proxy", lambda: prova_proxy(a.dominio)),
              ("proc", lambda: [prova_proc()]),
              ("fora_montado", lambda: [prova_fora_montado(a.raiz)]),
              ("escrita", lambda: [prova_escrita()]),
              ("capacidades", lambda: [prova_capacidades()]),
              ("tiocsti", lambda: [prova_tiocsti(a.terminal_proprio)]),
              ("userns", lambda: [prova_userns(a.userns)]),
              ("ambiente", lambda: [prova_ambiente([n for n in a.env.split(",") if n])])]
    if a.como.startswith("codex"):
        provas.append(("segredo_da_jaula_invisivel", lambda: [prova_segredo_da_jaula()]))
        provas.append(("sandbox_codex", lambda: [prova_sandbox_codex(a.codex)]))
    itens = []
    for nome, funcao in provas:
        try:
            itens += funcao()
        except Exception as exc:  # noqa: BLE001 — uma prova que quebra reprova, não derruba o relatório
            itens.append(item(nome, False, f"a prova falhou ({type(exc).__name__})"))
    return {"schema_version": ESQUEMA, "modo": "canario", "como": a.como,
            "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "itens": itens,
            "aprovado": all(i["aprovado"] for i in itens)}


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(prog="canario_jaula.py", allow_abbrev=False)
    ap.add_argument("--como", required=True, choices=["navegador", "navegador-janela", "codex-exec", "codex-titular"])
    ap.add_argument("--dominio", default="")
    ap.add_argument("--raiz", default="")
    ap.add_argument("--env", default="")
    ap.add_argument("--isca", default="")
    ap.add_argument("--userns", choices=["bloqueado", "anotar"], default="bloqueado")
    ap.add_argument("--grafico", action="store_true")
    ap.add_argument("--terminal-proprio", action="store_true")
    ap.add_argument("--codex", default="")
    a = ap.parse_args(argv)
    relatorio = executar(a)
    sys.stdout.write(json.dumps(relatorio, ensure_ascii=False) + "\n")
    return 0 if relatorio["aprovado"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
