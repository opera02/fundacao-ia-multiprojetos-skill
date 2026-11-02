"""Regras fixas da ficha de aberturas do projeto (1.7.10; contratos do lote 2, §5; DESENHO-1.7.10 §3; crítica do
desenho, "tetos que nenhuma assinatura derruba"; revisão independente do pacote ABERTURAS, 31/10/2026).

A ficha `fundacao.ficha_aberturas/1` diz o que o titular abre para UM projeto (rede para os comandos da sessão,
WebFetch, WebSearch e plugins conferidos), fechada por padrão: campo ausente ou vazio = fechado. Este módulo é o
validador de tetos fixos do preparo (`abertura preparar`), da ficha em vigor (`core/aberturas.vigente`) e da
assinatura (assets/host/fundacao_titular.py): nenhuma assinatura derruba um teto daqui. Só biblioteca padrão e nenhum
outro módulo do kit (o scripts/levantar_aberturas.py o carrega pelo caminho). Tetos (erro recusa; aviso só informa):
- esquema fechado (additionalProperties: false), com `versao` de 1 a VERSAO_MAXIMA (o que cabe em ficha-v<N>.json); as
  seções da 1.7.11 (RESERVADAS) só valem ausentes ou vazias, e preenchidas a recusa diz "1.7.11";
- domínio: nome DNS em minúsculas, sem esquema, porta, caminho, IP literal, IP escrito no nome (127.0.0.1.nip.io), DNS
  para qualquer IP (DNS_PARA_QUALQUER_IP) nem endereço local (localhost, .local...), que pelo proxy do sandbox valem
  como o localhost. Curinga só `*.<domínio registrável>` (SEGUNDO_NIVEL) e nunca sobre hospedagem compartilhada
  (SUFIXOS_COMPARTILHADOS, ou abaixo de PROVEDORES_COMPARTILHADOS); aviso para domínio largo que recebe dado por GET
  (DOMINIOS_LARGOS) e para host em hospedagem compartilhada; `webfetch.dominios` contido em `rede.dominios`;
- plugin: nome próprio do projeto e origem relativa à pasta do projeto, fora de data/ e das pastas protegidas, cada
  parte só com letra ASCII, número, ponto, hífen e sublinhado, sem terminar em ponto/espaço nem com '~' (PARTE_ORIGEM);
- `vigencia_ate` no passado recusa (na assinatura e na conferência: ficha vencida fecha tudo).
O texto livre (`motivo`, `consequencias`) é da sessão: sem controle nem invisível, até TETO_LINHAS linhas e sem duas
vazias seguidas (não apaga nem empurra a lista fixa para fora da tela); quem descreve cada abertura é `descrever`.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date

SCHEMA = "fundacao.ficha_aberturas/1"
NAMESPACE = "fundacao-abertura"  # o da ficha: o aceite de uma entrega (fundacao-decisao) nunca abre nada
OBRIGATORIOS = ("schema_version", "ficha_id", "project_id", "versao", "motivo", "consequencias")
OPCIONAIS = ("vigencia_ate", "rede", "webfetch", "websearch", "plugins")
# Para a 1.7.11 (contratos do lote 2, §5): MCP e `leitura_liberada` exigem a jaula, negações enumeradas e o canário A1.
RESERVADAS = tuple("mcp navegador git segredos outras_llm execucao leitura_liberada perfil_navegador_copiado".split())
TETO_FICHA, TETO_TEXTO, TETO_LINHAS, TETO_DOMINIOS, TETO_PLUGINS = 256 * 1024, 4000, 20, 200, 20
VERSAO_MAXIMA = 10**9 - 1  # ficha-v<N>.json com até 9 dígitos (core/aberturas.VERSAO_RE)
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
PASTAS_PROTEGIDAS = ("data", ".claude", ".porteiro", ".git", "decisoes")  # 1ª parte que nunca vira plugin (dado/protegida)
ID_PROJETO = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?")  # a de core/paths.validate_id (e sem "--")
ID_FICHA = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
NOME_PLUGIN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")
# Parte da origem de um plugin (único texto livre da sessão na tela): sem espaço, NBSP nem separador (reconferência).
PARTE_ORIGEM = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
SHA256 = re.compile(r"[0-9a-f]{64}")
DATA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_ROTULO = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_TERMINACAO = re.compile(r"[a-z]{2,63}|xn--[a-z0-9-]{1,59}")
_IPV4_COM_HIFEN = re.compile(r"(?:.*-)?(?:[0-9]{1,3}-){3}[0-9]{1,3}(?:-.*)?")
_INVISIVEIS = frozenset({"Cc", "Cf", "Cs", "Co", "Zl", "Zp"})


def mostrar(valor) -> str:
    """Valor do rascunho numa mensagem: escapado (sem controle nem escape de terminal), curto, com ' [...]' no corte."""
    return ascii(valor)[:80] + (" [...]" if len(ascii(valor)) > 80 else "")


def carregar(bruto: bytes):
    """JSON estrito: UTF-8, sem chave repetida (um leitor ficaria com a primeira, outro com a última), sem NaN nem
    Infinity e sem número fracionário (nenhum campo da ficha é). Erro: ValueError."""
    def objeto(pares):
        saida = {}
        for chave, valor in pares:
            if chave in saida:
                raise ValueError("chave repetida: " + mostrar(chave))
            saida[chave] = valor
        return saida

    def recusar(texto):
        raise ValueError("número fora do formato: " + mostrar(texto))
    try:
        return json.loads(bytes(bruto).decode("utf-8"), object_pairs_hook=objeto, parse_constant=recusar,
                          parse_float=recusar)
    except RecursionError:
        raise ValueError("JSON aninhado demais") from None


def canonico(ficha: dict) -> bytes:
    """Bytes que o titular assina: a forma das decisões assinadas (core/decisoes.canonico) — chaves ordenadas, recuo
    de 2, UTF-8 sem escapes e quebra de linha no fim."""
    return (json.dumps(ficha, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def problema_do_texto(valor, teto: int = TETO_TEXTO) -> str | None:
    if not isinstance(valor, str) or not valor.strip():
        return "texto obrigatório, não vazio"
    if len(valor) > teto:
        return f"texto acima de {teto} caracteres"
    if any(c not in "\n\t" and unicodedata.category(c) in _INVISIVEIS for c in valor):
        return "caractere de controle ou invisível (só quebra de linha e tabulação)"
    linhas = valor.split("\n")
    if len(linhas) > TETO_LINHAS:
        return f"texto acima de {TETO_LINHAS} linhas"
    if any(not a.strip() and not b.strip() for a, b in zip(linhas, linhas[1:])):
        return "duas linhas vazias seguidas: o texto da sessão não pode empurrar a lista fixa para fora da tela"
    return None


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
        avisos.append(f"curinga: vale para todo subdomínio de {base}, inclusive os que ainda não existem")
    return avisos


def problema_da_origem(origem) -> str | None:
    """A origem do plugin: caminho relativo à pasta do projeto, só com '/', fora de data/ e das pastas protegidas."""
    if not isinstance(origem, str) or not origem or len(origem) > 240:
        return "caminho relativo dentro da pasta do projeto (até 240 caracteres)"
    if "\\" in origem or ":" in origem or origem.startswith("/") or any(unicodedata.category(c) in _INVISIVEIS
                                                                         for c in origem):
        return "caminho relativo com '/': sem unidade, barra invertida nem caractere de controle"
    partes = origem.split("/")
    if any(p in ("", ".", "..") for p in partes) or len(partes) > 8:
        return "caminho sem '..', '.', parte vazia ou mais de 8 níveis"
    if any(p != p.rstrip(". ") or "~" in p for p in partes):
        return ("parte do caminho terminada em ponto ou espaço, ou com '~': o Windows tira o ponto e o espaço do fim "
                "('data./x' é data/x) e aceita o nome curto 8.3")
    if not all(PARTE_ORIGEM.fullmatch(p) for p in partes):
        return "parte da origem com espaço, NBSP ou outro separador: só letra ASCII, número, ponto, hífen e sublinhado"
    if partes[0].rstrip(". ").casefold() in PASTAS_PROTEGIDAS:
        return "dado (data/) ou pasta protegida não vira plugin: monte o candidato em plugins-candidatos/"
    return None


def _vazio(valor) -> bool:
    return valor is None or valor is False or valor in ("", [], {})


def _dominios(ficha: dict, secao: str, erro, avisos: list) -> list[str]:
    if secao not in ficha:
        return []
    bloco = ficha[secao]
    if not isinstance(bloco, dict) or set(bloco) - {"dominios"} or not isinstance(bloco.get("dominios", []), list):
        erro(secao, 'use {"dominios": [...]}, sem outros campos')
        return []
    lista, vistos = bloco.get("dominios", []), []
    if len(lista) > TETO_DOMINIOS:
        erro(secao + ".dominios", f"mais de {TETO_DOMINIOS} domínios")
    for i, dominio in enumerate(lista[:TETO_DOMINIOS]):
        motivo = problema_do_dominio(dominio) or ("domínio repetido" if dominio in vistos else None)
        if motivo:
            erro(f"{secao}.dominios[{i}]", motivo, valor=mostrar(dominio))
            continue
        vistos.append(dominio)
        if secao == "rede":  # o webfetch é contido na rede: os avisos saem uma vez só
            avisos += [{"campo": f"rede.dominios[{i}]", "dominio": dominio, "motivo": a}
                       for a in avisos_do_dominio(dominio)]
    return vistos


def _plugins(ficha: dict, projeto: str | None, erro, avisos: list) -> None:
    if "plugins" not in ficha:
        return
    lista = ficha["plugins"]
    if not isinstance(lista, list) or len(lista) > TETO_PLUGINS:
        erro("plugins", f"lista de até {TETO_PLUGINS} plugins")
        return
    nomes, origens = set(), set()
    for i, item in enumerate(lista):
        campo = f"plugins[{i}]"
        if not isinstance(item, dict) or set(item) != {"nome", "origem", "manifesto_sha256"}:
            erro(campo, 'cada plugin é {"nome", "origem", "manifesto_sha256"}, sem outros campos')
            continue
        nome, origem, sha = item["nome"], item["origem"], item["manifesto_sha256"]
        if not isinstance(nome, str) or not NOME_PLUGIN.fullmatch(nome) or nome in nomes:
            erro(campo + ".nome", "nome de plugin em minúsculas, números e hífen (até 64), sem repetir",
                 valor=mostrar(nome))
        else:
            nomes.add(nome)
            if projeto and not nome.startswith(projeto + "-"):
                avisos.append({"campo": campo + ".nome", "dominio": None,
                               "motivo": f"nome sem o prefixo do projeto ({projeto}-): use um nome próprio do projeto"})
        motivo = problema_da_origem(origem) or ("origem repetida" if origem in origens else None)
        if motivo:
            erro(campo + ".origem", motivo, valor=mostrar(origem))
        else:
            origens.add(origem)
        if not isinstance(sha, str) or not SHA256.fullmatch(sha):
            erro(campo + ".manifesto_sha256", "SHA-256 do manifesto do plugin (64 dígitos hexadecimais minúsculos)")


def _vigencia(valor, hoje: date | None, erro) -> None:
    try:
        data = date.fromisoformat(valor) if isinstance(valor, str) and DATA.fullmatch(valor) else None
    except ValueError:
        data = None
    if data is None:
        erro("vigencia_ate", "data no formato AAAA-MM-DD", valor=mostrar(valor))
    elif hoje is not None and data < hoje:
        erro("vigencia_ate", f"ficha vencida em {valor} (hoje é {hoje.isoformat()}): vencida fecha tudo; assine uma "
                             "versão nova", vencida=True)


def validar(ficha, *, projeto: str | None = None, hoje: date | None = None) -> dict:
    """Erros e avisos da ficha pelos tetos fixos, sem tocar no disco. `projeto`: o project_id esperado; `hoje`: com
    ele, `vigencia_ate` no passado recusa."""
    erros, avisos = [], []

    def erro(campo, motivo, **extra):
        erros.append({"campo": campo, "motivo": motivo, **extra})
    if not isinstance(ficha, dict):
        erro("ficha", "a ficha precisa ser um objeto JSON")
        return {"erros": erros, "avisos": avisos}
    for chave in sorted(set(ficha) - set(OBRIGATORIOS) - set(OPCIONAIS) - set(RESERVADAS)):
        erro(mostrar(chave), "campo fora do esquema da ficha (additionalProperties: false)")
    for chave in RESERVADAS:
        if chave in ficha and not _vazio(ficha[chave]):
            erro(chave, "seção reservada para a 1.7.11: nesta versão só ausente ou vazia (fechada)", versao="1.7.11")
    erros += [{"campo": c, "motivo": "campo obrigatório ausente"} for c in OBRIGATORIOS if c not in ficha]
    if "schema_version" in ficha and ficha["schema_version"] != SCHEMA:
        erro("schema_version", f"esquema desconhecido: use {SCHEMA}")
    if "ficha_id" in ficha and not (isinstance(ficha["ficha_id"], str) and ID_FICHA.fullmatch(ficha["ficha_id"])):
        erro("ficha_id", "identificador: letras, números, ponto, hífen e sublinhado (até 100)")
    pid = ficha.get("project_id")
    if "project_id" in ficha and not (isinstance(pid, str) and ID_PROJETO.fullmatch(pid) and "--" not in pid):
        erro("project_id", "identificador de projeto inválido", valor=mostrar(pid))
    elif projeto is not None and "project_id" in ficha and pid != projeto:
        erro("project_id", f"ficha de outro projeto: esperado {projeto}", valor=mostrar(pid))
    versao = ficha.get("versao")
    if "versao" in ficha and (isinstance(versao, bool) or not isinstance(versao, int)
                              or not 1 <= versao <= VERSAO_MAXIMA):
        erro("versao", f"versão é um inteiro de 1 a {VERSAO_MAXIMA}")
    for chave in ("motivo", "consequencias"):
        motivo = problema_do_texto(ficha[chave]) if chave in ficha else None
        if motivo:
            erro(chave, motivo)
    if "vigencia_ate" in ficha:
        _vigencia(ficha["vigencia_ate"], hoje, erro)
    rede = _dominios(ficha, "rede", erro, avisos)
    for dominio in _dominios(ficha, "webfetch", erro, avisos):
        if dominio not in rede:
            erro("webfetch.dominios", f"{dominio} precisa estar também em rede.dominios: o WebFetch(domain:...) libera "
                                      "o domínio também para os comandos", dominio=dominio)
    if "websearch" in ficha and not isinstance(ficha["websearch"], bool):
        erro("websearch", "websearch é true ou false")
    _plugins(ficha, projeto, erro, avisos)
    return {"erros": erros, "avisos": avisos}


def _lista(ficha, secao: str, tipo=str) -> list:
    """Os itens do tipo esperado de `secao.dominios` (texto) ou de `plugins` (objeto); o que não for lista, ou item de
    outro tipo (ficha adulterada depois do preparo), fica de fora."""
    valor = ficha.get(secao) if isinstance(ficha, dict) else None
    valor = (valor.get("dominios") if isinstance(valor, dict) else None) if secao != "plugins" else valor
    return [v for v in valor if isinstance(v, tipo)] if isinstance(valor, list) else []


def itens(ficha) -> list[tuple[str, str]]:
    """Cada abertura da ficha como (seção, item): a base da comparação entre versões (o que abre, o que fecha)."""
    pares = [("rede", d) for d in _lista(ficha, "rede")] + [("webfetch", d) for d in _lista(ficha, "webfetch")]
    if isinstance(ficha, dict) and ficha.get("websearch") is True:
        pares.append(("websearch", "sim"))
    return pares + [("plugins", str(p.get("nome"))) for p in _lista(ficha, "plugins", dict)]


def descrever(ficha) -> list[dict]:
    """Cada abertura em português simples, por código fixo (o `motivo` e as `consequencias` são da sessão)."""
    def alvo(d):
        return f"qualquer subdomínio de {d[2:]}" if d.startswith("*.") else d
    textos = {"rede": "Os comandos da sessão (terminal) poderão se conectar a {}: dados do projeto podem sair para lá.",
              "webfetch": "A ferramenta WebFetch poderá ler páginas de {}; o domínio fica liberado também para os "
                          "comandos.",
              "websearch": "A sessão poderá pesquisar na web (WebSearch): as palavras da busca saem para o serviço de "
                           "busca, e os resultados entram como conteúdo de terceiros (dado, não instrução).{}"}
    saida = [{"secao": s, "item": i, "texto": textos[s].format(alvo(i) if s != "websearch" else "")}
             for s, i in itens(ficha) if s != "plugins"]
    for p in _lista(ficha, "plugins", dict):  # a origem na forma (PARTE_ORIGEM, até 240) inteira; fora dela, mostrar()
        origem = ascii(p["origem"]) if problema_da_origem(p.get("origem")) is None else mostrar(p.get("origem"))
        saida.append({"secao": "plugins", "item": str(p.get("nome")), "texto": f"O plugin {mostrar(p.get('nome'))} (de "
                      f"{origem}; a fundação conferiu só a forma: Markdown, sem hooks, MCP nem executável; o texto das "
                      "instruções não foi revisado) entra na sessão: as skills, os agentes e os comandos dele passam a "
                      "valer como instrução."})
    return saida or [{"secao": "nenhuma", "item": "", "texto": "Esta versão não abre nada: tudo continua fechado."}]
