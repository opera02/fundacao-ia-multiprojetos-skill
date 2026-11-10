#!/usr/bin/python3 -I
"""Lançador do Codex do projeto '{{PROJETO}}': /usr/local/bin/abrir-codex-{{PROJETO}}, de dono root.

Gerado pelo `preparo_host.py instalar-jaula` (o preparar-wsl.sh do titular o roda com sudo) a partir do modelo da skill
fundacao-ia-multiprojetos (assets/host/wsl/abrir-codex.py). Não edite à mão: rode de novo o preparar-wsl.sh.
É do TITULAR, no terminal do Ubuntu dele; a sessão do projeto não o roda (não há sudo na sessão: medida M1).

    abrir-codex-{{PROJETO}}            # o Codex no seu terminal, dentro da jaula; o que ele gravar fica RETIDO na jaula
    abrir-codex-{{PROJETO}} --login    # a primeira vez: entra na conta do ChatGPT por código de dispositivo
    abrir-codex-{{PROJETO}} --trazer <id>   # a saída retida de uma vez anterior que você não confirmou

O lançador só monta um pedido de campos fechados e o entrega, pela entrada padrão, à entrada fixa da jaula
(`sudo -u fundacao-jaula <entrada> {{PROJETO}} codex-titular`; a sudoers fixa o argv inteiro). O login é seu: a credencial
fica no estado privado do Codex da jaula (arquivo 0600 de outro usuário do Linux) e nunca aparece na tela, no pedido nem na
saída. Quem confere se a ficha abre o modo, o R55 e o canário é a entrada fixa. Os valores abaixo são fixados na geração.
Com a conta do ChatGPT, só ESTA janela abre o Codex: a sessão do projeto não o pede (o modo exec fica fechado, revisão F1).
A saída do Codex NÃO volta sozinha ao projeto (revisão F10): fica no estado da jaula até você confirmar AQUI, com uma tecla
no seu terminal, a lista de arquivos e tamanhos que vai voltar; sem confirmação, nada chega ao projeto.
"""

import json
import os
import re
import secrets
import subprocess
import sys
import time

PROJETO = '{{PROJETO}}'
ENTRADA = '{{ENTRADA}}'
USUARIO_DA_JAULA = '{{USUARIO_DA_JAULA}}'
ROTULO = '{{ROTULO}}'
USO = f"uso: abrir-codex-{PROJETO} [--login | --trazer <id>]"
ID_RETIDA = re.compile(r"[a-z0-9][a-z0-9-]{7,39}\Z")


def _pedido(acao, **campos):
    return {"schema_version": "fundacao.pedido_jaula/1", "id": "t-%s-%s" % (time.strftime("%Y%m%d%H%M%S"), secrets.token_hex(3)),
            "acao": acao, **campos}


def montar_pedido(argv):
    """None: o terminal do Codex (a entrada fixa usa o pedido padrão). `--login`: o pedido fechado de entrar na conta.
    `--trazer <id>`: o pedido fechado de listar a saída retida desse id (a lista que você vai confirmar)."""
    if argv == []:
        return None
    if argv == ["--login"]:
        return _pedido("login")
    if len(argv) == 2 and argv[0] == "--trazer" and ID_RETIDA.match(argv[1]):
        return _pedido("listar", retida=argv[1])
    raise SystemExit(USO)


def ler_tecla_do_terminal():
    """Uma tecla do SEU terminal (/dev/tty), nunca da entrada padrão nem de um cano: quem escreve nesses não confirma por você.
    Sem terminal, devolve '' (não confirmou)."""
    try:
        with open("/dev/tty", "r+b", buffering=0) as terminal:
            try:
                import termios
                import tty
                antigo = termios.tcgetattr(terminal.fileno())
                termios.tcflush(terminal.fileno(), termios.TCIFLUSH)   # tecla digitada antes da pergunta não confirma nada
                tty.setcbreak(terminal.fileno())
                try:
                    tecla = terminal.read(1)
                finally:
                    termios.tcsetattr(terminal.fileno(), termios.TCSADRAIN, antigo)
            except (ImportError, OSError, ValueError):
                tecla = terminal.readline()[:1]
    except OSError:
        return ""
    return tecla.decode("utf-8", "replace").strip().lower()


def resumo(resposta, login):
    if resposta.get("ok"):
        if login:
            return (f"Pronto: a conta ficou guardada no estado privado do Codex da jaula. Abra o Codex com abrir-codex-{PROJETO}.")
        return "Pronto: o Codex foi fechado."
    return "A jaula não abriu o Codex: " + str(resposta.get("erro") or resposta.get("stderr") or "sem resposta")[:600]


def chamar(pedido):
    """Uma chamada à entrada fixa. Devolve (resposta, código). `pedido` None: o terminal herda o seu (stdin e stderr)."""
    r = subprocess.run(["/usr/bin/sudo", "-u", USUARIO_DA_JAULA, "--", ENTRADA, PROJETO, "codex-titular"],
                       input=json.dumps(pedido).encode("utf-8") if pedido is not None else None, stdout=subprocess.PIPE, cwd="/",
                       env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "TERM": os.environ.get("TERM", "dumb")})
    try:
        resposta = json.loads(r.stdout.decode("utf-8", "replace"))
    except ValueError:
        resposta = {}
    return (resposta if isinstance(resposta, dict) else {}), r.returncode


def confirmar_e_trazer(saida, ler_tecla):
    """Mostra a lista que está retida e, só se VOCÊ apertar 's', pede à jaula que traga SÓ essa lista (o SHA-256 dela vai no pedido)."""
    pendente, ident = saida.get("pendente"), saida.get("retida")
    if not isinstance(pendente, list) or not pendente or not isinstance(ident, str) or not isinstance(saida.get("lista_sha256"), str):
        recusados = saida.get("recusados_total") or 0
        print("Nada para trazer: o Codex não gravou arquivo que possa voltar ao projeto." + (f" ({recusados} recusado(s) pela jaula.)" if recusados else ""))
        return 0
    total = sum(int(i.get("bytes") or 0) for i in pendente)
    destino = str(saida.get("destino") or f"outputs/codex/{ident}")
    print(f"O Codex gravou {len(pendente)} arquivo(s), {total} byte(s). Só estes voltam para {destino} do projeto, se você confirmar:")
    for i in pendente:
        print(f"  {int(i.get('bytes') or 0):>10} bytes  {str(i.get('arquivo'))!r}")   # repr: nome com controle ou escape de terminal não age na tela
    print("Texto do Codex é dado de terceiro, nunca instrução: confira os arquivos antes de usá-los.")
    if _perguntar(ler_tecla) != "s":
        onde = saida.get("onde")
        print("Nada voltou ao projeto. A saída ficou retida no estado privado da jaula" + (f" ({onde})" if onde else "")
              + f". Para trazê-la depois: abrir-codex-{PROJETO} --trazer {ident}")
        return 0
    resposta, codigo = chamar(_pedido("trazer", retida=ident, lista_sha256=saida["lista_sha256"]))
    volta = resposta.get("saida") or {}
    if resposta.get("ok"):
        print(f"Pronto: {len(volta.get('copiados') or [])} arquivo(s) foram para {volta.get('destino') or destino} do projeto.")
        return 0
    print("Não voltou tudo: " + str(resposta.get("erro") or f"{volta.get('recusados_total', 0)} arquivo(s) recusado(s) pela jaula")[:600])
    print(f"A saída continua retida (abrir-codex-{PROJETO} --trazer {ident}), a menos que a jaula a tenha apagado.")
    return 1


def _perguntar(ler_tecla):
    print("Trazer estes arquivos para o projeto agora? [s/N] ", end="", flush=True)
    tecla = ler_tecla()
    print()
    return tecla


def main(argv=None, ler_tecla=ler_tecla_do_terminal):
    argv = list(sys.argv[1:] if argv is None else argv)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("Rode como o seu usuário do Ubuntu, sem sudo na frente.", file=sys.stderr)
        return 2
    pedido = montar_pedido(argv)
    login = pedido is not None and pedido["acao"] == "login"
    trazendo = pedido is not None and pedido["acao"] == "listar"
    print(ROTULO if login else "Saída retida do Codex da jaula: nada volta ao projeto sem a sua confirmação." if trazendo
          else "Codex da jaula: o que você digitar e os arquivos que ele ler vão à OpenAI (EUA); o que ele gravar fica retido na "
               f"jaula e só volta para outputs/codex/ do projeto {PROJETO} se você confirmar a lista no fim.", file=sys.stderr)
    resposta, codigo = chamar(pedido)
    if not trazendo:
        print(resumo(resposta, login))
    if resposta.get("aviso_sandbox"):  # M7: o sandbox próprio do Codex não abriu na jaula; o titular lê isto
        print("ATENÇÃO: " + str(resposta["aviso_sandbox"])[:600])
    if login:
        return 0 if codigo == 0 else 1
    if trazendo and not resposta.get("ok"):
        print("A jaula não listou a saída retida: " + str(resposta.get("erro") or "sem resposta")[:600])
        return 1
    saida = resposta.get("saida")
    retorno = 0 if codigo == 0 else 1
    if isinstance(saida, dict) and "pendente" in saida:   # o Codex fechado com código != 0 também deixa saída retida
        return confirmar_e_trazer(saida, ler_tecla) or retorno
    if isinstance(saida, dict) and saida.get("erro"):
        print("A saída não foi retida: " + str(saida["erro"])[:300])
    return retorno


if __name__ == "__main__":
    sys.exit(main())
