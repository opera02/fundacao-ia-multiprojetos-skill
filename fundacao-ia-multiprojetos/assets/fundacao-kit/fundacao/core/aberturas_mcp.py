"""Seção `mcp` da ficha de aberturas (1.7.11; DESENHO-JAULA §4.3 e §7.2; DECISAO-011): só o conector do escritório (um
servidor), com todas as ferramentas dele, as de consulta e as que gravam, em lista nominal (sem curinga). O campo
`ferramentas` guarda a lista inteira (até a 1.7.11 ele se chamava `consulta`, nome que ficou enganoso quando a lista
passou a ter as de gravação, DECISAO-011; o nome velho é recusado com mensagem clara, sem migração: nenhuma ficha
assinada tinha a seção); a fundação separa cada ferramenta pelo NOME em "consulta" ou "grava"
(`classificar_ferramenta`) para a tela do titular mostrar as que gravam em separado, com o risco, antes da assinatura.
O nome não prova o que a ferramenta faz: quem decide é o servidor, e o que não tem nome claro de consulta conta como
"grava". Fica fechado, sem assinatura que derrube: outro servidor, curinga, MCP
local (comando, argumentos, variáveis, cabeçalhos), URL fora da regra e nome fora da forma. Saiu de `aberturas_regras.py`
(teto de linhas do kit); o `aberturas_regras` o chama em `validar`, `itens` e `descrever`, passando a si mesmo como `R`
(mostrar, problema_do_dominio e as listas de hospedagem compartilhada). Só biblioteca padrão e nenhum outro módulo do kit.
"""

from __future__ import annotations

import re

# MCP (DESENHO-JAULA §4.3 e §7.2): só o conector do escritório (um servidor). Teto de 32 ferramentas por lista: o conector
# tem 24 hoje (17 de consulta e 7 que gravam ou escaneiam), então sobram 8 para ele crescer sem nova regra, e uma lista
# acima de 32 já não é "as ferramentas do conector do escritório" (seria outro servidor ou um curinga disfarçado). Mais
# ferramentas pedem decisão própria do titular e este teto revisto no kit.
TETO_MCP_SERVIDORES, TETO_MCP_FERRAMENTAS = 1, 32
NOME_MCP = re.compile(r"[a-z0-9-]{1,32}")
NOME_FERRAMENTA = re.compile(r"[a-z][a-z0-9_]{0,63}")
PREFIXOS_DE_CONSULTA = tuple("buscar_ get_ obter_ listar_ relatorio_ consultar_ pesquisar_ ler_ agregar_ search_ list_ "
                             "read_ fetch_".split())
# Uma ferramenta só é "consulta" se começa por um prefixo de consulta E nenhuma parte do nome (separada por `_`) é um
# destes verbos: `buscar_e_apagar` e `get_set_valor` contam como "grava".
VERBOS_DE_GRAVACAO = frozenset((
    "criar atualizar salvar apagar excluir deletar remover confirmar cancelar propor tratar enviar publicar mover "
    "gravar editar alterar set create update delete write send post put patch upsert insert remove "
    "executar rodar run exec execute replace add append push submit sync sincronizar aprovar assinar importar").split())
MENSAGEM_MCP_LOCAL = ("MCP local fica fechado: nada de comando, argumentos, variáveis ou cabeçalhos; só o conector do "
                      "escritório, pela conta ou por URL https")
CAMPOS_MCP = ("nome", "origem", "conector", "url", "ferramentas", "ocultar", "conteudo_de_terceiros")
MENSAGEM_CONSULTA_RENOMEADA = ('o campo "consulta" foi renomeado para "ferramentas" (a lista tem as de consulta e as que '
                               'gravam): troque o nome e assine de novo')
CAMPOS_MCP_LOCAL = ("comando", "argv", "command", "args", "env", "headers")
ORIGENS_MCP = ("conta", "url")
CAMINHO_URL = re.compile(r"/[A-Za-z0-9._~%!$&'()*+,;=:@/-]*")


def problema_do_conector(conector) -> str | None:
    """O nome do conector como aparece na conta do claude.ai: texto ASCII imprimível de até 64 caracteres, sem `__`
    (o nome completo da ferramenta é `mcp__<servidor>__<ferramenta>`) nem espaço nas pontas."""
    if not isinstance(conector, str) or not conector or len(conector) > 64:
        return "nome do conector: texto de 1 a 64 caracteres"
    if any(not 32 <= ord(c) <= 126 for c in conector) or conector != conector.strip() or "__" in conector:
        return "nome do conector: só ASCII imprimível, sem espaço nas pontas e sem '__'"
    return None


def problema_da_url_mcp(R, url) -> str | None:
    """A URL do servidor remoto (origem `url`): só https, sem porta, usuário, parâmetros nem fragmento; o host passa
    pela `problema_do_dominio` (de `R`, o aberturas_regras), sem curinga e sem hospedagem compartilhada (nem com aviso)."""
    if not isinstance(url, str) or not url or len(url) > 300:
        return "URL do servidor: texto de até 300 caracteres"
    if any(not 33 <= ord(c) <= 126 for c in url) or "\\" in url:
        return "URL com espaço, controle, barra invertida ou fora do ASCII"
    if not url.startswith("https://"):
        return "só https"
    resto = url[len("https://"):]
    autoridade, barra, caminho = resto.partition("/")
    caminho = barra + caminho
    if any(c in url for c in "?#") or "@" in autoridade or ":" in autoridade or "[" in autoridade:
        return "URL sem usuário, porta, parâmetros nem fragmento"
    if autoridade != autoridade.lower() or "*" in autoridade:
        return "host em minúsculas e sem curinga"
    motivo = R.problema_do_dominio(autoridade)
    if motivo:
        return "host do servidor: " + motivo
    if R._sob(autoridade, R.SUFIXOS_COMPARTILHADOS + R.PROVEDORES_COMPARTILHADOS):
        return "host em hospedagem compartilhada (qualquer pessoa publica ali) não vale como servidor MCP"
    if caminho and not CAMINHO_URL.fullmatch(caminho):
        return "caminho da URL com caractere fora do aceito"
    return None


def problema_do_nome_da_ferramenta(nome) -> str | None:
    """Motivo da recusa do NOME de uma ferramenta (forma exata, sem curinga), ou None."""
    if not isinstance(nome, str) or not NOME_FERRAMENTA.fullmatch(nome) or "__" in nome or nome.endswith("_"):
        return "nome de ferramenta: [a-z][a-z0-9_]{0,63}, sem '__' nem '_' no fim"
    return None


def classificar_ferramenta(nome: str) -> str:
    """"consulta" ou "grava", só pelo nome: consulta é o nome que começa por um prefixo de consulta e não tem, em
    nenhuma parte separada por `_`, um verbo de gravação. Todo o resto (verbo de gravação, nome sem prefixo de consulta
    como `escanear_vault`) é "grava": na dúvida, a tela do titular mostra a ferramenta entre as que gravam."""
    if nome.startswith(PREFIXOS_DE_CONSULTA) and not set(nome.split("_")) & VERBOS_DE_GRAVACAO:
        return "consulta"
    return "grava"


def _nomes(R, valor, campo: str, teto: int, erro, *, minimo: int) -> list[str]:
    if not isinstance(valor, list) or not minimo <= len(valor) <= teto:
        erro(campo, f"lista de {minimo} a {teto} nomes exatos de ferramenta" if minimo
             else f"lista de até {teto} nomes exatos de ferramenta")
        return []
    vistos: list[str] = []
    for i, nome in enumerate(valor):
        motivo = problema_do_nome_da_ferramenta(nome)
        motivo = motivo or ("nome repetido" if nome in vistos else None)
        if motivo:
            erro(f"{campo}[{i}]", motivo, valor=R.mostrar(nome))
        else:
            vistos.append(nome)
    return vistos


def validar(R, ficha: dict, hoje, erro, avisos: list) -> None:
    if "mcp" not in ficha or R._vazio(ficha["mcp"]):
        return
    lista = ficha["mcp"]
    if not isinstance(lista, list) or len(lista) > TETO_MCP_SERVIDORES:
        erro("mcp", f"lista de até {TETO_MCP_SERVIDORES} servidor (só o conector do escritório; outro conector pede "
                    "decisão própria do titular)")
        return
    nomes: set[str] = set()
    for i, item in enumerate(lista):
        campo = f"mcp[{i}]"
        if not isinstance(item, dict):
            erro(campo, "cada servidor é um objeto com " + ", ".join(CAMPOS_MCP))
            continue
        for chave in sorted(set(item) - set(CAMPOS_MCP), key=str):
            erro(f"{campo}.{R._chave(chave)}", MENSAGEM_MCP_LOCAL if chave in CAMPOS_MCP_LOCAL
                 else MENSAGEM_CONSULTA_RENOMEADA if chave == "consulta"
                 else "campo fora do esquema (additionalProperties: false)")
        nome, origem = item.get("nome"), item.get("origem")
        if not isinstance(nome, str) or not NOME_MCP.fullmatch(nome) or nome in nomes:
            erro(campo + ".nome", "nome do servidor em [a-z0-9-] (até 32), sem repetir", valor=R.mostrar(nome))
        else:
            nomes.add(nome)
        if origem not in ORIGENS_MCP:
            erro(campo + ".origem", "origem: 'conta' (conector da conta do claude.ai) ou 'url'", valor=R.mostrar(origem))
        elif origem == "conta":
            motivo = problema_do_conector(item.get("conector"))
            if motivo:
                erro(campo + ".conector", motivo, valor=R.mostrar(item.get("conector")))
            if item.get("url") is not None:
                erro(campo + ".url", "origem 'conta' não tem URL (url fica null ou ausente)")
        else:
            motivo = problema_da_url_mcp(R, item.get("url"))
            if motivo:
                erro(campo + ".url", motivo, valor=R.mostrar(item.get("url")))
            else:
                avisos.append({"campo": campo + ".url", "dominio": None,
                               "motivo": "servidor MCP por URL: o login (OAuth) fica no perfil do projeto; confira de "
                                         "quem é o servidor"})
            if item.get("conector") is not None:
                erro(campo + ".conector", "origem 'url' não tem nome de conector (conector fica null ou ausente)")
        liberadas = _nomes(R, item.get("ferramentas"), campo + ".ferramentas", TETO_MCP_FERRAMENTAS, erro, minimo=1)
        ocultar = _nomes(R, item.get("ocultar", []), campo + ".ocultar", TETO_MCP_FERRAMENTAS, erro, minimo=0)
        if set(liberadas) & set(ocultar):
            erro(campo + ".ocultar", "ferramenta em ferramentas e em ocultar ao mesmo tempo", valor=R.mostrar(
                sorted(set(liberadas) & set(ocultar))[0]))
        if item.get("conteudo_de_terceiros") is not True:
            erro(campo + ".conteudo_de_terceiros", "tem de ser true: as respostas do servidor entram na sessão como "
                                                   "conteúdo de terceiros")


def _textos(valor) -> list[str]:
    return [v for v in valor if isinstance(v, str)] if isinstance(valor, list) else []


def _servidores(ficha) -> list[dict]:
    valor = ficha.get("mcp") if isinstance(ficha, dict) else None
    return [s for s in valor if isinstance(s, dict)] if isinstance(valor, list) else []


def _separadas(servidor: dict) -> tuple[list[str], list[str]]:
    """As ferramentas liberadas do servidor, em (consulta, grava), na ordem da ficha, pelo nome."""
    nomes = _textos(servidor.get("ferramentas"))
    return ([n for n in nomes if classificar_ferramenta(n) == "consulta"],
            [n for n in nomes if classificar_ferramenta(n) == "grava"])


def itens(ficha) -> list[tuple[str, str]]:
    """Cada ferramenta liberada como (seção, item): "mcp" para as de consulta e "mcp-grava" para as que gravam, para a
    comparação entre versões mostrar em separado o que passa a gravar."""
    pares = []
    for s in _servidores(ficha):
        consulta, grava = _separadas(s)
        pares += [("mcp", f"{s.get('nome')}:{f}") for f in consulta]
        pares += [("mcp-grava", f"{s.get('nome')}:{f}") for f in grava]
    return pares


def descrever(R, ficha) -> list[dict]:
    """Uma linha fixa para as ferramentas de consulta e, em separado (`grava: True`), outra para as que gravam: a tela do
    titular mostra esta última à parte, com o risco, antes da assinatura."""
    saida = []
    for s in _servidores(ficha):
        nome = R.mostrar(s.get("nome"))
        quem = (f"no conector {R.mostrar(s.get('conector'))} da sua conta" if s.get("origem") == "conta"
                else f"no servidor {R.mostrar(s.get('url'))}")
        consulta, grava = _separadas(s)
        if consulta:
            saida.append({"secao": "mcp", "item": nome, "texto": (
                f"A sessão poderá CONSULTAR {quem} (chamado {nome}) as ferramentas "
                f"{', '.join(R.mostrar(f) for f in consulta)}: ela verá dados que o servidor entregar, inclusive de outros "
                "clientes; as respostas entram como conteúdo de terceiros (dado, não instrução).")})
        if grava:
            saida.append({"secao": "mcp-grava", "item": nome, "grava": True, "texto": (
                f"A sessão poderá GRAVAR {quem} (chamado {nome}) com as ferramentas "
                f"{', '.join(R.mostrar(f) for f in grava)}: ela poderá criar, mudar e apagar dados do escritório, inclusive "
                "de outros clientes. Um texto malicioso numa página ou num documento pode tentar levar a sessão a usar "
                "essas ferramentas; se a sessão rodar sem perguntas, ela grava sem pedir a sua confirmação. A fundação "
                "separou as ferramentas só pelo nome: o que cada uma faz de fato quem decide é o servidor, e a que não "
                "tem nome claro de consulta aparece aqui.")})
    return saida
