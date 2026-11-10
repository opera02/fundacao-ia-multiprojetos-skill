#!/usr/bin/env python3
"""Hook PreToolUse de rede das ferramentas web: WebFetch só para domínio da lista, WebSearch só aberto (1.7.10).

Contratos do lote 2 da 1.7.10, §2 e §7. Registro (pacote HOST, perfis WSL e Windows): matcher `WebFetch|WebSearch`,
`python3 -I -B` (Windows: `python -I -B`) com o caminho absoluto `<raiz>/.claude/hooks/guarda_rede.py`.
- WebFetch: só `http`/`https`, sem usuário ou senha na URL, sem porta além da padrão do esquema, sem IP literal (nem
  as formas numéricas abreviadas), sem `localhost`, `*.localhost`, `*.local` e `*.internal`, e só com o host em
  FUNDACAO_DOMINIOS_WEB (vírgulas; `dominio` casa só ele; `*.dominio` casa o próprio domínio e os subdomínios,
  DECISAO-010 item 5 da 1.7.11; nunca `outrodominio` nem `dominio.outro`). URL malformada, com espaço, controle, barra invertida ou `%` no host: nega.
  Nome internacional que o codec idna do Python e o Node do Claude Code leem diferente (ß, ς, letra posterior ao
  Unicode 3.2): nega, na URL e na lista (revisão do lote 2). Lista ausente ou vazia: nega todo WebFetch. A decisão
  é `deny`, nunca pergunta: os domínios de documentação pré-aprovados do Claude Code não passam por fora da lista
  (mapa, fato 16 da documentação oficial).
- WebSearch: só com FUNDACAO_WEBSEARCH=1; senão, nega.
- Entrada da lista inválida (com barra, porta, curinga no meio, `*.` de um rótulo só) é ignorada: não libera nada.
Os valores vêm do perfil gerado da ficha de aberturas assinada (pacote HOST); o validador dos tetos da ficha
(sufixos de hospedagem compartilhada, domínio registrável) é o do pacote ABERTURAS — aqui fica a conferência da
chamada. Saída: a negação no formato do guarda_caminho.py, em JSON só com ASCII; liberado = sem saída (seguem as
regras `WebFetch(domain:...)` do perfil). Evento ilegível, vazio, sem `tool_name` ou erro: nega.
Limite (honestidade, §0 dos contratos): guarda-corpo da ferramenta do Claude Code, não do shell. O `curl` do shell
segue as regras de rede do sandbox, que, com a raiz em /mnt/e, não confinou os comandos de arquivo nas sondas de
31/10/2026; e um domínio liberado aqui também recebe dado por GET: a ficha diz isso ao titular.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import sys
import unicodedata
import urllib.parse

ESQUEMAS = {"http": 80, "https": 443}
LIMITE_URL = 8192
ROTULO = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
NUMERICO = re.compile(r"(?:0x[0-9a-f]*|[0-9]+)\Z")
SUFIXOS_LOCAIS = ("localhost", "local", "internal")


def deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def host_normalizado(texto: str) -> str | None:
    """Nome de host em minúsculas e ASCII (IDNA), sem o ponto final; None se não for um nome DNS aceitável.

    Nome internacional só se a ida e a volta do codec idna do Python (IDNA 2003, Unicode 3.2) devolvem o mesmo nome:
    ele troca ß por ss e ς por σ (e U+200C/U+200D, que já caem como não imprimíveis), o analisador WHATWG do Node
    (Claude Code) mantém, e a busca iria a outro domínio (`straße` → `xn--strae-oqa`, não `strasse`); letra que o
    Unicode 3.2 não tinha (cheroqui minúsculo) o Node ainda mapeia (revisão do lote 2)."""
    if not texto or any(c in texto for c in "%[]:@/\\ ") or not texto.isprintable():
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


def lista_de_dominios(texto: str | None) -> tuple[set[str], set[str]]:
    """(exatos, bases de `*.base`) de FUNDACAO_DOMINIOS_WEB; entrada inválida fica fora (não libera nada)."""
    exatos, curingas = set(), set()
    for item in (texto or "").split(","):
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


def conferir_url(url) -> tuple[str | None, str | None]:
    """(host normalizado, None) ou (None, motivo da recusa)."""
    if not isinstance(url, str) or not url or len(url) > LIMITE_URL:
        return None, "URL ausente ou longa demais"
    if any(c.isspace() or not c.isprintable() for c in url) or "\\" in url:
        return None, "URL com espaço, controle ou barra invertida"
    try:
        partes = urllib.parse.urlsplit(url)
        porta = partes.port
    except ValueError:
        return None, "URL malformada"
    if partes.scheme not in ESQUEMAS or not url.lower().startswith(partes.scheme + "://"):
        return None, "só http e https"
    if "@" in partes.netloc:
        return None, "URL com usuário ou senha"
    if porta is not None and porta != ESQUEMAS[partes.scheme]:
        return None, f"porta {porta} fora da padrão do esquema"
    host = host_normalizado(partes.hostname or "")
    if host is None:
        return None, "host malformado"
    motivo = proibido_sempre(host)
    if motivo:
        return None, motivo
    return host, None


def decide(event: dict, env: dict) -> dict | None:
    tool = event.get("tool_name")
    if not isinstance(tool, str) or not tool:
        return deny("evento sem nome de ferramenta: negado por segurança")
    if tool == "WebSearch":
        if env.get("FUNDACAO_WEBSEARCH") == "1":
            return None
        return deny("WebSearch fechado neste projeto: só abre com a ficha de aberturas assinada pelo titular "
                    "(websearch: true), que liga FUNDACAO_WEBSEARCH=1 no perfil")
    if tool != "WebFetch":
        return None
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return deny("WebFetch sem entrada legível: negado")
    host, motivo = conferir_url(tool_input.get("url"))
    if host is None:
        return deny(f"WebFetch negado: {motivo}")
    exatos, curingas = lista_de_dominios(env.get("FUNDACAO_DOMINIOS_WEB"))
    if host in exatos or host in curingas or any(host.endswith("." + base) for base in curingas):
        return None
    return deny(f"WebFetch negado: o domínio {host} não está na lista do projeto (FUNDACAO_DOMINIOS_WEB). Domínio "
                "novo só entra pela ficha de aberturas assinada pelo titular (webfetch.dominios).")


def _recusar(*_):
    raise ValueError("entrada inválida")


def _objeto_sem_duplicatas(pares):
    objeto = {}
    for chave, valor in pares:
        if chave in objeto:
            _recusar()
        objeto[chave] = valor
    return objeto


def main() -> int:
    try:
        # Bytes em UTF-8: com -I o Python ignora PYTHONUTF8 e leria a entrada na página de código do Windows.
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"), object_pairs_hook=_objeto_sem_duplicatas,
                           parse_constant=_recusar)
        if not isinstance(event, dict):
            raise ValueError("evento não é objeto")
        result = decide(event, dict(os.environ))
    except Exception:  # noqa: BLE001 — falha fechada: qualquer erro vira negativa
        result = deny("evento ilegível ou erro no hook: negado por segurança")
    if result:
        # JSON só com ASCII: a saída independe da página de código do console (cp1252 no Windows).
        sys.stdout.write(json.dumps(result, ensure_ascii=True) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
