"""Regras de domínio da ficha de aberturas e a regra do curinga (1.7.10; 1.7.11, DECISAO-010 item 5).

Saiu de `aberturas_regras.py` (teto de linhas do kit); o `aberturas_regras` repete os nomes públicos daqui
(`problema_do_dominio`, `avisos_do_dominio`, `cobre`, `expandir_curingas` e as listas). Só biblioteca padrão e nenhum
outro módulo do kit. Domínio: nome DNS em minúsculas, sem esquema, porta, caminho, IP literal nem endereço local; curinga
só `*.<domínio registrável>` e nunca sobre hospedagem compartilhada; `*.x` vale para `x` e para os subdomínios dele.
"""

from __future__ import annotations

import re

# Hospedagem compartilhada: curinga nunca; site exato, com aviso. Os 19 dos contratos e outros da mesma natureza.
SUFIXOS_COMPARTILHADOS = tuple((
    "vercel.app github.io workers.dev googleusercontent.com netlify.app pages.dev herokuapp.com "
    "azurewebsites.net cloudfront.net appspot.com firebaseapp.com web.app ngrok.io ngrok-free.app "
    "trycloudflare.com repl.co glitch.me blob.core.windows.net s3.amazonaws.com githubusercontent.com "
    "gitlab.io onrender.com fly.dev railway.app surge.sh deno.dev r2.dev amplifyapp.com azurestaticapps.net "
    "web.core.windows.net storage.googleapis.com ngrok.app loca.lt replit.dev blogspot.com wordpress.com "
    "wixsite.com weebly.com neocities.org notion.site myshopify.com 000webhostapp.com").split())
# Provedor onde qualquer cliente publica ou recebe dados (bucket, função, túnel, DNS dinâmico, coletor), também por
# região (*.s3.sa-east-1.amazonaws.com): curinga abaixo dele nunca; host exato abaixo dele, com aviso de compartilhada.
PROVEDORES_COMPARTILHADOS = tuple((
    "amazonaws.com on.aws awsapprunner.com elasticbeanstalk.com windows.net azure.com azureedge.net "
    "azurefd.net azure-api.net cloudapp.net trafficmanager.net azurecr.io azurecontainerapps.io "
    "googleapis.com run.app cloudfunctions.net firebaseio.com firebasestorage.app supabase.co supabase.in "
    "github.dev devtunnels.ms ondigitalocean.app digitaloceanspaces.com pipedream.net cloudflarestorage.com "
    "oraclecloud.com appdomain.cloud backblazeb2.com wasabisys.com linodeobjects.com aliyuncs.com "
    "myqcloud.com hf.space streamlit.app replit.app netlify.com now.sh webhook.site requestcatcher.com "
    "beeceptor.com lhr.life serveo.net loclx.io interact.sh oast.fun oast.pro oast.live oast.site oast.online "
    "oast.me burpcollaborator.net duckdns.org ddns.net no-ip.org no-ip.biz hopto.org zapto.org sytes.net dynv6.net "
    "mooo.com ts.net ngrok.dev loophole.site localhost.run pinggy.link tunnelmole.net dyndns.org dynu.net afraid.org "
    "freeddns.org synology.me myfritz.net ngrok-free.dev ngrok.pizza bore.pub pagekite.me tunnelto.dev zrok.io "
    "playit.gg cfargotunnel.com ydns.eu dedyn.io").split())  # DNS dinâmico e túneis: reconferências de 31/10 e 01/11
DOMINIOS_LARGOS = ("docs.google.com", "drive.google.com", "pastebin.com", "gist.github.com", "github.com",
                   "gitlab.com", "bitbucket.org", "dropbox.com")
TERMINACOES_LOCAIS = ("localhost", "local", "internal", "localdomain", "lan", "home", "corp", "intranet", "private",
                      "test", "example", "invalid", "onion", "arpa")
# DNS que responde o IP escrito no nome (10-0-0-1.sslip.io) e nomes que apontam para o próprio computador: recusados.
DNS_PARA_QUALQUER_IP = ("nip.io", "sslip.io", "xip.io", "traefik.me", "localtest.me", "lvh.me", "vcap.me",
                        "lacolhost.com", "localhost.direct", "fuf.me")
# Segundo nível genérico sob o código de país (com.br, gov.br, co.uk...): `*.com.br` cobriria domínios de todo mundo.
SEGUNDO_NIVEL = frozenset("com net org gov edu mil int ac co or ne go nom jus leg mp adv eng med art blog biz info "
                          "ind inf ltd plc sch gob gouv nic tec tur".split())
_ROTULO = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_TERMINACAO = re.compile(r"[a-z]{2,63}|xn--[a-z0-9-]{1,59}")
_IPV4_COM_HIFEN = re.compile(r"(?:.*-)?(?:[0-9]{1,3}-){3}[0-9]{1,3}(?:-.*)?")


def _sob(base: str, sufixos) -> bool:
    return any(base == s or base.endswith("." + s) for s in sufixos)


def problema_do_dominio(dominio) -> str | None:
    """Motivo da recusa de `dominio` (`nome` ou `*.nome`), ou None."""
    if not isinstance(dominio, str) or not dominio:
        return "domínio precisa ser texto não vazio"
    curinga = dominio.startswith("*.")
    base = dominio[2:] if curinga else dominio
    if any(c in base for c in ":[]/@?#\\ "):
        return "só o nome do domínio: sem esquema, porta, caminho, usuário nem IP literal (IPv6)"
    if "*" in base:
        return "curinga só no começo, na forma *.<domínio registrável>"
    if base != base.lower() or base.endswith(".") or len(base) > 253:
        return "use a forma canônica: minúsculas, sem ponto no fim, até 253 caracteres"
    rotulos = base.split(".")
    if not all(_ROTULO.fullmatch(r) for r in rotulos):
        return "domínio inválido: só letras minúsculas sem acento, números, hífen e ponto (nome internacional em xn--)"
    if rotulos[-1].isdigit():
        return "IP literal não é aceito: use o nome do domínio"
    if _sob(base, TERMINACOES_LOCAIS):
        return "endereço local ou reservado (localhost, .local, .internal e afins) não é aceito"
    if (any(all(r.isdigit() for r in rotulos[i:i + 4]) for i in range(len(rotulos) - 3))
            or any(_IPV4_COM_HIFEN.fullmatch(r) for r in rotulos)):
        return "IP escrito no nome (127.0.0.1.nip.io, 10-0-0-1.exemplo.com) não é aceito: pelo proxy, vale como o IP"
    if _sob(base, DNS_PARA_QUALQUER_IP):
        return "serviço de DNS que aponta para qualquer IP ou para o próprio computador (nip.io, localtest.me e afins)"
    if curinga and (len(rotulos) < 2 or (len(rotulos) == 2 and rotulos[0] in SEGUNDO_NIVEL and len(rotulos[1]) == 2)):
        return "curinga só sobre domínio registrável (*.<nome>.<terminação>), nunca sobre a terminação (*.com, *.com.br)"
    if len(rotulos) < 2 or not _TERMINACAO.fullmatch(rotulos[-1]):
        return "domínio sem terminação válida: precisa de nome e terminação, como exemplo.com.br"
    if curinga and (_sob(base, SUFIXOS_COMPARTILHADOS + PROVEDORES_COMPARTILHADOS)
                    or any(s.endswith("." + base) for s in SUFIXOS_COMPARTILHADOS)):
        return "curinga sobre hospedagem compartilhada (qualquer pessoa publica um site ali): liste o site exato"
    return None


def avisos_do_dominio(dominio: str) -> list[str]:
    curinga = dominio.startswith("*.")
    base = dominio[2:] if curinga else dominio
    avisos = []
    if any(base == d or base.endswith("." + d) or (curinga and d.endswith("." + base)) for d in DOMINIOS_LARGOS):
        avisos.append("domínio largo que recebe dado por GET (formulário, documento, colagem): dados do projeto podem "
                      "sair por ele")
    if _sob(base, SUFIXOS_COMPARTILHADOS + PROVEDORES_COMPARTILHADOS):
        avisos.append("site em hospedagem compartilhada (qualquer pessoa publica ali): confira de quem é o site")
    if curinga:
        avisos.append(f"curinga: vale para {base} e para todo subdomínio dele, inclusive os que ainda não existem")
    return avisos


def cobre(entrada: str, host: str) -> bool:
    """A entrada da ficha (`x` ou `*.x`) cobre o host? `x` cobre só `x`; `*.x` cobre `x` e todo subdomínio de `x`
    (DECISAO-010, item 5), nunca `outrox` nem `x.outro`. É a mesma regra do assets/hooks/guarda_rede.py."""
    if not isinstance(entrada, str) or not isinstance(host, str):
        return False
    if entrada.startswith("*."):
        base = entrada[2:]
        return bool(base) and (host == base or host.endswith("." + base))
    return host == entrada


def expandir_curingas(dominios) -> list[str]:
    """Cada `*.x` da ficha vira `x` e `*.x`, nessa ordem, sem repetir: o que o perfil gera para a rede do sandbox e
    para as regras `WebFetch(domain:)`. O teto de TETO_DOMINIOS conta os itens da ficha, não os gerados. Idempotente."""
    saida: list[str] = []
    for d in dominios:
        for item in ((d[2:], d) if isinstance(d, str) and d.startswith("*.") else (d,)):
            if item not in saida:
                saida.append(item)
    return saida
