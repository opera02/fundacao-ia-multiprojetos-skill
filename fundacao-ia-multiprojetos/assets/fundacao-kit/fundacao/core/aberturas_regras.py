"""Regras fixas da ficha de aberturas do projeto (1.7.10; contratos do lote 2, §5; DESENHO-1.7.10 §3; crítica do
desenho, "tetos que nenhuma assinatura derruba"; revisão independente do pacote ABERTURAS, 31/10/2026).

A ficha `fundacao.ficha_aberturas/1` diz o que o titular abre para UM projeto (rede para os comandos da sessão,
WebFetch, WebSearch e plugins conferidos), fechada por padrão: campo ausente ou vazio = fechado. Este módulo é o
validador de tetos fixos do preparo (`abertura preparar`), da ficha em vigor (`core/aberturas.vigente`) e da
assinatura (assets/host/fundacao_titular.py): nenhuma assinatura derruba um teto daqui. Só biblioteca padrão; os
irmãos aberturas_dominios, aberturas_mcp, aberturas_agentes, aberturas_scripts e aberturas_jaula (teto de linhas) são
carregados na chamada, pelo pacote ou, se este foi carregado pelo caminho (scripts/levantar_aberturas.py), pelo arquivo
vizinho. Tetos (erro recusa; aviso só informa):
- esquema fechado (additionalProperties: false), com `versao` de 1 a VERSAO_MAXIMA (o que cabe em ficha-v<N>.json); as
  seções ainda reservadas (RESERVADAS) só valem ausentes ou vazias, e preenchidas a recusa diz "1.7.11"; as seções
  `mcp`, `navegador` e `outras_llm` (1.7.11, DESENHO-JAULA §7) têm esquema, lista fechada e tetos próprios abaixo;
- curinga (DECISAO-010, item 5): `*.x` vale para `x` e para todo subdomínio dele (`cobre`, `expandir_curingas`);
- domínio: nome DNS em minúsculas, sem esquema, porta, caminho, IP literal, IP escrito no nome (127.0.0.1.nip.io), DNS
  para qualquer IP (DNS_PARA_QUALQUER_IP) nem endereço local (localhost, .local...), que pelo proxy do sandbox valem
  como o localhost. Curinga só `*.<domínio registrável>` (SEGUNDO_NIVEL) e nunca sobre hospedagem compartilhada
  (SUFIXOS_COMPARTILHADOS, ou abaixo de PROVEDORES_COMPARTILHADOS); aviso para domínio largo que recebe dado por GET
  (DOMINIOS_LARGOS) e para host em hospedagem compartilhada; `webfetch.dominios` contido em `rede.dominios`;
- plugin: nome próprio do projeto e origem relativa à pasta do projeto, fora de data/ e das pastas protegidas, cada
  parte só com letra ASCII, número, ponto, hífen e sublinhado, sem terminar em ponto/espaço nem com '~' (PARTE_ORIGEM);
  o campo opcional `agentes` (1.7.11, lote A2) abre os agentes de arquivo do plugin: regras em aberturas_agentes.py,
  e o `skills_com_scripts` (lote S1) os scripts Python e o lock das skills, presos por hash: aberturas_scripts.py; o
  plugin com um dos dois tem de se chamar `<projeto>-<nome>` (aos outros, o prefixo é só aviso);
- `vigencia_ate` no passado recusa (na assinatura e na conferência: ficha vencida fecha tudo).
O texto livre (`motivo`, `consequencias`) é da sessão: sem controle nem invisível, até TETO_LINHAS linhas e sem duas
vazias seguidas (não apaga nem empurra a lista fixa para fora da tela); quem descreve cada abertura é `descrever`.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import re
import types
import unicodedata
from datetime import date

SCHEMA = "fundacao.ficha_aberturas/1"
NAMESPACE = "fundacao-abertura"  # o da ficha: o aceite de uma entrega (fundacao-decisao) nunca abre nada
OBRIGATORIOS = ("schema_version", "ficha_id", "project_id", "versao", "motivo", "consequencias")
OPCIONAIS = ("vigencia_ate", "rede", "webfetch", "websearch", "plugins", "mcp", "navegador", "outras_llm")
# Seções ainda fechadas (contratos do lote 2, §5): só valem ausentes ou vazias. A 1.7.11 abriu `mcp`, `navegador` e
# `outras_llm` (DESENHO-JAULA §7, DECISAO-010); `perfil_navegador_copiado` segue recusada (decisão do titular de
# 08/11/2026: perfil novo; DECISAO-005, item 8).
# Módulos irmãos: agentes dos plugins; mcp; navegador e outras_llm.
SECOES_1711 = ("aberturas_agentes", "aberturas_scripts", "aberturas_mcp", "aberturas_jaula")
_IRMAOS: dict = {}


def _irmao(nome: str):
    """Módulo ao lado deste: pelo pacote do kit, ou, se este foi carregado pelo caminho (scripts/levantar_aberturas.py),
    pelo arquivo vizinho. É o único acoplamento com o resto do kit, e só em tempo de chamada."""
    if nome not in _IRMAOS:
        if __package__:
            _IRMAOS[nome] = importlib.import_module("." + nome, __package__)
        else:
            spec = importlib.util.spec_from_file_location(nome, os.path.join(os.path.dirname(__file__), nome + ".py"))
            _IRMAOS[nome] = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_IRMAOS[nome])
    return _IRMAOS[nome]


def _contexto():
    """Este módulo, para os irmãos usarem `mostrar`, `problema_do_dominio` e afins (sem importar este arquivo)."""
    return types.SimpleNamespace(**globals())


_D = _irmao("aberturas_dominios")  # as regras de domínio e do curinga: aberturas_dominios.py (os mesmos nomes públicos)
(SUFIXOS_COMPARTILHADOS, PROVEDORES_COMPARTILHADOS, DOMINIOS_LARGOS, TERMINACOES_LOCAIS, DNS_PARA_QUALQUER_IP,
 SEGUNDO_NIVEL, problema_do_dominio, avisos_do_dominio, cobre, expandir_curingas, _sob) = (
    _D.SUFIXOS_COMPARTILHADOS, _D.PROVEDORES_COMPARTILHADOS, _D.DOMINIOS_LARGOS, _D.TERMINACOES_LOCAIS,
    _D.DNS_PARA_QUALQUER_IP, _D.SEGUNDO_NIVEL, _D.problema_do_dominio, _D.avisos_do_dominio, _D.cobre,
    _D.expandir_curingas, _D._sob)
RESERVADAS = tuple("git segredos execucao leitura_liberada perfil_navegador_copiado".split())
TETO_FICHA, TETO_TEXTO, TETO_LINHAS, TETO_DOMINIOS, TETO_PLUGINS = 256 * 1024, 4000, 20, 200, 20
VERSAO_MAXIMA = 10**9 - 1  # ficha-v<N>.json com até 9 dígitos (core/aberturas.VERSAO_RE)
PASTAS_PROTEGIDAS = ("data", ".claude", ".porteiro", ".git", "decisoes")  # 1ª parte que nunca vira plugin (dado/protegida)
ID_PROJETO = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?")  # a de core/paths.validate_id (e sem "--")
ID_FICHA = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
NOME_PLUGIN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")
# Parte da origem de um plugin (único texto livre da sessão na tela): sem espaço, NBSP nem separador (reconferência).
PARTE_ORIGEM = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
SHA256 = re.compile(r"[0-9a-f]{64}")
DATA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
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
        if not isinstance(item, dict) or not {"nome", "origem", "manifesto_sha256"} <= set(item) <= {
                "nome", "origem", "manifesto_sha256", "agentes", "skills_com_scripts"}:
            erro(campo, 'cada plugin é {"nome", "origem", "manifesto_sha256"} e, se abrir agentes ou scripts, "agentes" e '
                        '"skills_com_scripts"; sem outros campos')
            continue
        nome, origem, sha = item["nome"], item["origem"], item["manifesto_sha256"]
        if not isinstance(nome, str) or not NOME_PLUGIN.fullmatch(nome) or nome in nomes:
            erro(campo + ".nome", "nome de plugin em minúsculas, números e hífen (até 64), sem repetir",
                 valor=mostrar(nome))
        else:
            nomes.add(nome)
            if projeto and not nome.startswith(projeto + "-") and not (item.get("agentes")
                                                                       or item.get("skills_com_scripts")):  # irmãos: erro
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


def _chave(chave) -> str:
    """O nome do campo no caminho do erro: puro se for um nome comum, escapado (mostrar) se não for."""
    return chave if isinstance(chave, str) and re.fullmatch(r"[A-Za-z0-9_]{1,40}", chave) else mostrar(chave)


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
            erro(chave, "seção reservada para a 1.7.11: nesta versão só ausente ou vazia (fechada)"
                 + ("; o perfil do navegador é sempre novo e só do projeto (decisão do titular de 08/11/2026; "
                    "DECISAO-005, item 8)" if chave == "perfil_navegador_copiado" else ""), versao="1.7.11")
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
    for nome in SECOES_1711:
        _irmao(nome).validar(_contexto(), ficha, hoje, erro, avisos)
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
    pares += [("plugins", str(p.get("nome"))) for p in _lista(ficha, "plugins", dict)]
    for nome in SECOES_1711:
        pares += _irmao(nome).itens(ficha)
    return pares


def alvo(d: str) -> str:
    return f"{d[2:]} e qualquer subdomínio de {d[2:]}" if d.startswith("*.") else d


def descrever(ficha) -> list[dict]:
    """Cada abertura em português simples, por código fixo (o `motivo` e as `consequencias` são da sessão)."""
    textos = {"rede": "Os comandos da sessão (terminal) poderão se conectar a {}: dados do projeto podem sair para lá.",
              "webfetch": "A ferramenta WebFetch poderá ler páginas de {}; o domínio fica liberado também para os "
                          "comandos.",
              "websearch": "A sessão poderá pesquisar na web (WebSearch): as palavras da busca saem para o serviço de "
                           "busca, e os resultados entram como conteúdo de terceiros (dado, não instrução).{}"}
    saida = [{"secao": s, "item": i, "texto": textos[s].format(alvo(i) if s != "websearch" else "")}
             for s, i in itens(ficha) if s in textos]
    for p in _lista(ficha, "plugins", dict):  # a origem na forma (PARTE_ORIGEM, até 240) inteira; fora dela, mostrar()
        origem = ascii(p["origem"]) if problema_da_origem(p.get("origem")) is None else mostrar(p.get("origem"))
        forma = ("Markdown e os scripts Python listados abaixo, sem hooks nem MCP" if p.get("skills_com_scripts")
                 else "Markdown, sem hooks, MCP nem executável")
        saida.append({"secao": "plugins", "item": str(p.get("nome")), "texto": f"O plugin {mostrar(p.get('nome'))} (de "
                      f"{origem}; a fundação conferiu só a forma: {forma}; o texto das "
                      "instruções não foi revisado) entra na sessão: as skills, os agentes e os comandos dele passam a "
                      "valer como instrução."})
    for nome in SECOES_1711:
        saida += _irmao(nome).descrever(_contexto(), ficha)
    return saida or [{"secao": "nenhuma", "item": "", "texto": "Esta versão não abre nada: tudo continua fechado."}]
