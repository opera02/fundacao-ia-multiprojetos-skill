#!/usr/bin/python3 -I
"""Lançador da janela do navegador do projeto '{{PROJETO}}': /usr/local/bin/abrir-navegador-{{PROJETO}}, de dono root.

Gerado pelo `preparo_host.py instalar-jaula` (o preparar-wsl.sh do titular o roda com sudo) a partir do modelo da skill
fundacao-ia-multiprojetos (assets/host/wsl/abrir-navegador.py). Não edite à mão: rode de novo o preparar-wsl.sh.
É do TITULAR, no terminal do Ubuntu dele; a sessão do projeto não o roda (não há sudo na sessão: medida M1).

    abrir-navegador-{{PROJETO}} login <site>       # o titular entra num site de navegador.logins e fecha a janela
    abrir-navegador-{{PROJETO}} captcha <endereço>  # o titular resolve o desafio com a própria mão e fecha a janela

O lançador só monta um pedido de campos fechados e o entrega, pela entrada padrão, à entrada fixa da jaula
(`sudo -u fundacao-jaula <entrada> {{PROJETO}} navegador-janela`; a sudoers fixa o argv inteiro). Quem confere o alvo é a
entrada fixa (o site tem de estar na ficha), e o navegador roda dentro da jaula, com perfil e rede dela. Os valores abaixo
são fixados na geração; nada vem do ambiente nem de argumento livre. Com o Wayland pelo socket, o lançador dá ao usuário da
jaula acesso ao socket do WSLg SÓ enquanto a janela está aberta (ACL posta e tirada aqui). Sem disfarce nem evasão: nada
resolve desafio sozinho.
"""

import json
import os
import secrets
import subprocess
import sys
import time

PROJETO = '{{PROJETO}}'
ENTRADA = '{{ENTRADA}}'
USUARIO_DA_JAULA = '{{USUARIO_DA_JAULA}}'
GRAFICO = '{{GRAFICO}}'
WAYLAND = '{{WAYLAND}}'
VARIANTES = ("login", "captcha")
USO = f"uso: abrir-navegador-{PROJETO} login <site> | captcha <endereço>"


def montar_pedido(argv):
    """O pedido de campos fechados; o `alvo` é conferido pela entrada fixa (login: domínio de navegador.logins; captcha:
    endereço de navegador.dominios)."""
    if len(argv) != 2 or argv[0] not in VARIANTES or not argv[1] or len(argv[1]) > 2000:
        raise SystemExit(USO)
    return {"schema_version": "fundacao.pedido_jaula/1", "id": "t-%s-%s" % (time.strftime("%Y%m%d%H%M%S"), secrets.token_hex(3)),
            "variante": argv[0], "alvo": argv[1]}


def acl(adicionar):
    """Dá (ou tira) ao usuário da jaula o acesso ao socket Wayland do WSLg: `x` na pasta e `rw` no socket."""
    certo = True
    for alvo, permissao in ((os.path.dirname(WAYLAND), "x"), (WAYLAND, "rw")):
        args = (["/usr/bin/setfacl", "-m", f"u:{USUARIO_DA_JAULA}:{permissao}", alvo] if adicionar
                else ["/usr/bin/setfacl", "-x", f"u:{USUARIO_DA_JAULA}", alvo])
        try:
            certo = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, timeout=30,
                                   env={"PATH": "/usr/bin:/bin"}).returncode == 0 and certo
        except (OSError, subprocess.SubprocessError):
            certo = False
    return certo


def resumo(resposta, variante):
    if resposta.get("ok"):
        destino = (resposta.get("saida") or {}).get("destino")
        return "Pronto: a janela foi fechada." + (f" A página que ficou aberta foi guardada em {destino}/pagina.html do projeto."
                                                  if variante == "captcha" and destino else "")
    return "A jaula não abriu a janela: " + str(resposta.get("erro") or resposta.get("stderr") or "sem resposta")[:600]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("Rode como o seu usuário do Ubuntu, sem sudo na frente.", file=sys.stderr)
        return 2
    pedido = montar_pedido(argv)
    com_acl = GRAFICO == "wayland-socket"
    if com_acl and not acl(True):
        acl(False)
        print("Não consegui liberar o socket de janelas (WSLg) para a jaula: o pacote acl está instalado? "
              "(preparar-wsl.sh)", file=sys.stderr)
        return 1
    try:
        r = subprocess.run(["/usr/bin/sudo", "-u", USUARIO_DA_JAULA, "--", ENTRADA, PROJETO, "navegador-janela"],
                           input=json.dumps(pedido).encode("utf-8"), stdout=subprocess.PIPE, cwd="/",
                           env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "TERM": os.environ.get("TERM", "dumb")})
    finally:
        if com_acl:
            acl(False)
    try:
        resposta = json.loads(r.stdout.decode("utf-8", "replace"))
    except ValueError:
        resposta = {}
    print(resumo(resposta if isinstance(resposta, dict) else {}, pedido["variante"]))
    return 0 if r.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
