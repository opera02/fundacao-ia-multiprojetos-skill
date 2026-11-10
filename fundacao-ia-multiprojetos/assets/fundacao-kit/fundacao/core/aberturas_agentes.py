"""Agentes de plugin pela ficha de aberturas (1.7.11, lote A2; desenho de skills e agentes, §2 e §4).

Um agente definido em arquivo (`agents/<nome>.md` de um plugin da ficha) só abre se o item `plugins[]` da ficha o nomeia
em `agentes[] {nome, sha256, ferramentas, modelo}`. A ficha prende o SHA-256 do arquivo, as ferramentas e o modelo; o
cabeçalho do arquivo tem de dizer o mesmo (`tools` obrigatório, igual às ferramentas da ficha, senão o subagente herdaria
todas as ferramentas da sessão). O preparo grava no perfil a variável que o `guarda_ferramentas.py` lê (FUNDACAO_AGENTES:
`<plugin>:<agente>=Ferramenta|Ferramenta`), e o guarda nega o tipo fora dela e a ferramenta fora das do agente.
Plugin sem `agentes` continua com os agentes fechados, como na 1.7.10.

Regras fixas (nenhuma assinatura as derruba):
- o plugin com `agentes` tem de se chamar `<projeto>-<nome>` (erro; os plugins só de Markdown seguem com o aviso);
- até 10 agentes por plugin e 20 na ficha; `nome` em minúsculas, números e hífen (sem repetir), igual ao `name` do
  cabeçalho e ao nome do arquivo (`agents/<nome>.md`);
- `ferramentas`: de 1 a 10 nomes, sem repetir, dentre Read, Grep, Glob, Edit, Write, TodoWrite e Bash, mais WebFetch só
  com a seção `webfetch` da ficha e WebSearch só com `websearch: true`. Nunca Agent, Task, Skill, NotebookEdit, MCP nem
  nome fora da lista (nem com especificador: `Bash(git *)`);
- `modelo` na lista fechada (inherit, sonnet, opus, haiku, fable); no cabeçalho, `model` igual (ausente só com inherit);
- `effort`, `maxTurns` e `color` do cabeçalho, quando vêm, na lista fechada ou na faixa.
O que a conferência não faz: ler o texto das instruções do agente (é o que o titular lê no REVISAO.md) nem provar o que
as ferramentas dele fazem (Bash roda comandos com a autoridade da sessão; a tela do titular diz isso).

Este módulo é irmão do aberturas_regras (carregado na chamada, pelo pacote ou pelo arquivo vizinho): só biblioteca
padrão e nenhum outro módulo do kit. `validar`, `itens` e `descrever` seguem a forma dos irmãos; `ler_cabecalho`,
`problemas_do_cabecalho` e `conferir_no_disco` são do aberturas_plugins (o cabeçalho e o hash, no disco).
"""

from __future__ import annotations

import hashlib
import re

TETO_AGENTES_PLUGIN, TETO_AGENTES_FICHA, TETO_FERRAMENTAS, TETO_ARQUIVO = 10, 20, 10, 1 << 20
CAMPOS_DO_AGENTE = ("nome", "sha256", "ferramentas", "modelo")
NOME_DO_AGENTE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")
FERRAMENTAS_BASE = ("Read", "Grep", "Glob", "Edit", "Write", "TodoWrite", "Bash")
NUNCA = frozenset({"Agent", "Task", "Skill", "NotebookEdit", "SubagentHandback"})
MODELOS = ("inherit", "sonnet", "opus", "haiku", "fable")
ESFORCOS = ("low", "medium", "high", "xhigh", "max")
CORES = ("red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan")
_CHAVE = re.compile(r"([A-Za-z][A-Za-z0-9_-]*):(?:[ \t](.*))?")
_FERRAMENTA = re.compile(r"[A-Za-z][A-Za-z0-9]{0,39}")
BOM = chr(0xFEFF)  # a marca de ordem de bytes do começo do arquivo, que o aberturas_markdown também tira


def _mostrar(valor) -> str:
    texto = ascii(valor)
    return texto[:80] + (" [...]" if len(texto) > 80 else "")


def _permitidas(R, ficha: dict) -> list[str]:
    return [*FERRAMENTAS_BASE, *(["WebFetch"] if R._lista(ficha, "webfetch") else []),
            *(["WebSearch"] if ficha.get("websearch") is True else [])]


def problema_da_ferramenta(nome, permitidas) -> str | None:
    if not isinstance(nome, str) or not nome:
        return "nome de ferramenta: texto"
    if nome in NUNCA or nome.startswith("mcp__"):
        return f"{nome} nunca vale para agente de plugin (delegar, chamar skill ou usar ferramenta de terceiro)"
    if nome == "WebFetch" and nome not in permitidas:
        return "WebFetch só com a seção webfetch da ficha"
    if nome == "WebSearch" and nome not in permitidas:
        return "WebSearch só com websearch: true na ficha"
    if nome not in permitidas:
        return "ferramenta fora da lista (" + ", ".join(permitidas) + "); sem especificador entre parênteses"
    return None


def _agente(R, a, campo: str, permitidas, vistos: set, erro) -> bool:
    if not isinstance(a, dict) or set(a) != set(CAMPOS_DO_AGENTE):
        erro(campo, "cada agente é {" + ", ".join(CAMPOS_DO_AGENTE) + "}, sem outros campos")
        return False
    nome, sha, ferramentas = a["nome"], a["sha256"], a["ferramentas"]
    if not isinstance(nome, str) or not NOME_DO_AGENTE.fullmatch(nome) or nome in vistos:
        erro(campo + ".nome", "nome do agente em minúsculas, números e hífen (até 64), sem repetir no plugin",
             valor=R.mostrar(nome))
    else:
        vistos.add(nome)
    if not isinstance(sha, str) or not R.SHA256.fullmatch(sha):
        erro(campo + ".sha256", "SHA-256 do arquivo do agente (64 dígitos hexadecimais minúsculos)")
    if not isinstance(ferramentas, list) or not 1 <= len(ferramentas) <= TETO_FERRAMENTAS:
        erro(campo + ".ferramentas", f"lista de 1 a {TETO_FERRAMENTAS} ferramentas (o agente sem lista herdaria todas)")
    else:
        for k, f in enumerate(ferramentas):
            motivo = problema_da_ferramenta(f, permitidas) or ("ferramenta repetida" if f in ferramentas[:k] else None)
            if motivo:
                erro(f"{campo}.ferramentas[{k}]", motivo, valor=R.mostrar(f))
    if a["modelo"] not in MODELOS:
        erro(campo + ".modelo", "modelo: " + ", ".join(MODELOS), valor=R.mostrar(a["modelo"]))
    return True


def validar(R, ficha: dict, hoje, erro, avisos: list) -> None:
    plugins = ficha.get("plugins")
    if not isinstance(plugins, list):
        return
    projeto = ficha.get("project_id") if isinstance(ficha.get("project_id"), str) else None
    permitidas, total = _permitidas(R, ficha), 0
    for i, item in enumerate(plugins):
        if not isinstance(item, dict) or "agentes" not in item:
            continue
        campo, lista = f"plugins[{i}].agentes", item["agentes"]
        if not isinstance(lista, list) or len(lista) > TETO_AGENTES_PLUGIN:
            erro(campo, f"lista de até {TETO_AGENTES_PLUGIN} agentes (vazia ou ausente: os agentes do plugin ficam "
                        "fechados)")
            continue
        nome = item.get("nome")
        if lista and projeto and isinstance(nome, str) and not nome.startswith(projeto + "-"):
            erro(f"plugins[{i}].nome", f"plugin com agentes tem de se chamar {projeto}-<nome>: o agente vira "
                 "<plugin>:<agente> e o prefixo do projeto evita o choque de nomes entre projetos", valor=R.mostrar(nome))
        vistos: set = set()
        total += sum(_agente(R, a, f"{campo}[{j}]", permitidas, vistos, erro) for j, a in enumerate(lista))
    if total > TETO_AGENTES_FICHA:
        erro("plugins", f"mais de {TETO_AGENTES_FICHA} agentes na ficha")


def _agentes(ficha):
    """(plugin, agente) de cada agente da ficha na forma de dicionário; o resto (ficha adulterada) fica de fora."""
    lista = ficha.get("plugins") if isinstance(ficha, dict) else None
    for p in lista if isinstance(lista, list) else []:
        for a in (p.get("agentes") if isinstance(p, dict) and isinstance(p.get("agentes"), list) else []):
            if isinstance(a, dict):
                yield p, a


def itens(ficha) -> list[tuple[str, str]]:
    """Cada agente como (seção, item), com o início do SHA-256: arquivo trocado aparece como o que fecha e o que abre."""
    return [("agentes", f"{p.get('nome')}:{a.get('nome')} (SHA-256 {str(a.get('sha256'))[:12]})")
            for p, a in _agentes(ficha)]


def descrever(R, ficha) -> list[dict]:
    saida = []
    for p, a in _agentes(ficha):
        tipo = R.mostrar(f"{p.get('nome')}:{a.get('nome')}")
        ferramentas = a.get("ferramentas") if isinstance(a.get("ferramentas"), list) else []
        modelo = "o mesmo da sessão (inherit)" if a.get("modelo") == "inherit" else R.mostrar(a.get("modelo"))
        texto = (f"O agente {tipo} poderá ser chamado pela sessão como subagente, com as ferramentas "
                 f"{', '.join(R.mostrar(f) for f in ferramentas)} e o modelo {modelo}. Ele segue as instruções do arquivo "
                 f"dele (SHA-256 {str(a.get('sha256'))[:8]}…), que a fundação conferiu na forma, e não no texto. Roda "
                 "com as regras e os limites da sessão.")
        if "Bash" in ferramentas:
            texto += " Com Bash, ele roda comandos com a mesma autoridade dos comandos da sessão."
        if {"WebFetch", "WebSearch"} & set(ferramentas):
            texto += " Com WebFetch ou WebSearch, ele alcança o que a ficha abre na rede."
        saida.append({"secao": "agentes", "item": tipo, "texto": texto})
    return saida


# ------------------------------------------------------------------ o arquivo do agente (aberturas_plugins)
def _sem_comentario(valor: str) -> str:
    valor = valor.strip()
    return valor if valor[:1] in "'\"" else re.sub(r"\s+#.*\Z", "", valor)


def _sem_aspas(valor: str) -> str:
    valor = valor.strip()
    return valor[1:-1] if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"" else valor


def ler_cabecalho(dados: bytes) -> dict | None:
    """O cabeçalho do agente: {chave: [valor cru de cada ocorrência]}, o valor sendo o resto da linha da chave e as
    linhas seguintes recuadas ou com '-', unidas por quebra de linha. None: sem cabeçalho na forma (a abertura `---` na
    primeira linha com conteúdo e o fechamento `---`). O aberturas_markdown confere as chaves e o conteúdo à parte."""
    try:
        linhas = dados.decode("utf-8").removeprefix(BOM).splitlines()
    except UnicodeDecodeError:
        return None
    inicio = next((i for i, linha in enumerate(linhas) if linha.strip()), None)
    if inicio is None or linhas[inicio].rstrip(" \t") != "---":
        return None
    fim = next((i for i in range(inicio + 1, len(linhas)) if linhas[i].rstrip(" \t") == "---"), None)
    if fim is None:
        return None
    ocorrencias: dict[str, list[list[str]]] = {}
    atual = None
    for linha in linhas[inicio + 1:fim]:
        if not linha.strip() or linha.lstrip().startswith("#"):
            continue
        if linha[0] in " \t-":
            if atual is not None:
                atual.append(linha)
            continue
        achada = _CHAVE.fullmatch(linha)
        atual = [achada.group(2) or ""] if achada else None
        if achada:
            ocorrencias.setdefault(achada.group(1), []).append(atual)
    return {chave: ["\n".join(o) for o in lista] for chave, lista in ocorrencias.items()}


def _um(cabecalho: dict, chave: str, motivos: list) -> str | None:
    """O valor de uma linha só da chave, sem aspas nem comentário; None se ausente. Repetida, em várias linhas ou
    vazia: motivo, e None."""
    valores = cabecalho.get(chave, [])
    if len(valores) > 1:
        motivos.append(f"{chave} repetido no cabeçalho")
    elif valores and "\n" in valores[0].strip():
        motivos.append(f"{chave} em mais de uma linha (use o valor numa linha só)")
    elif valores:
        valor = _sem_aspas(_sem_comentario(valores[0]))
        if valor:
            return valor
        motivos.append(f"{chave} vazio no cabeçalho")
    return None


def ferramentas_do_cabecalho(valor: str) -> list[str] | None:
    """Os nomes do `tools` (texto separado por vírgula, lista entre colchetes ou lista com '-'); None quando foge disso
    (especificador entre parênteses, curinga, misto, item vazio ou fora da forma de nome)."""
    primeira, _, resto = valor.partition("\n")
    primeira, itens = _sem_comentario(primeira), []
    if primeira:
        if resto.strip():
            return None
        texto = _sem_aspas(primeira)
        texto = texto[1:-1] if texto.startswith("[") and texto.endswith("]") else texto
        itens = [_sem_aspas(p) for p in texto.split(",")]
    else:
        for linha in resto.split("\n"):
            linha = _sem_comentario(linha)
            if linha and not linha.startswith("-"):
                return None
            if linha:
                itens.append(_sem_aspas(linha[1:]))
    return itens if itens and all(_FERRAMENTA.fullmatch(i) for i in itens) else None


def problemas_do_cabecalho(agente: dict, cabecalho: dict) -> list[str]:
    """O que o cabeçalho diz de diferente da ficha (nome, tools, model) ou fora da lista fechada (effort, maxTurns,
    color); vazio se confere."""
    motivos: list[str] = []
    nome = _um(cabecalho, "name", motivos)
    if nome != agente.get("nome"):
        motivos.append(f"name do cabeçalho ({_mostrar(nome)}) difere de agentes[].nome da ficha "
                       f"({_mostrar(agente.get('nome'))})")
    valores = cabecalho.get("tools", [])
    if not valores:
        motivos.append("sem tools no cabeçalho: o agente herdaria todas as ferramentas da sessão (a ficha exige tools)")
    elif len(valores) > 1:
        motivos.append("tools repetido no cabeçalho")
    else:
        lidas = ferramentas_do_cabecalho(valores[0])
        if lidas is None:
            motivos.append("tools fora do formato simples (nomes separados por vírgula, sem parênteses nem curinga)")
        elif len(set(lidas)) != len(lidas) or set(lidas) != set(agente.get("ferramentas") or ()):
            motivos.append(f"tools do cabeçalho ({', '.join(lidas)}) difere de agentes[].ferramentas da ficha "
                           f"({', '.join(map(str, agente.get('ferramentas') or ()))})")
    modelo, esperado = _um(cabecalho, "model", motivos), agente.get("modelo")
    if not (modelo == esperado or (esperado == "inherit" and modelo is None)):
        motivos.append(f"model do cabeçalho ({_mostrar(modelo)}) difere de agentes[].modelo da ficha ({_mostrar(esperado)})")
    for chave, validos in (("effort", ESFORCOS), ("color", CORES)):
        valor = _um(cabecalho, chave, motivos)
        if valor is not None and valor not in validos:
            motivos.append(f"{chave} do cabeçalho fora da lista ({', '.join(validos)}): {_mostrar(valor)}")
    turnos = _um(cabecalho, "maxTurns", motivos)
    if turnos is not None and not (re.fullmatch(r"[0-9]{1,3}", turnos) and 1 <= int(turnos) <= 200):
        motivos.append(f"maxTurns do cabeçalho fora de 1 a 200: {_mostrar(turnos)}")
    if not any(v.strip() for v in cabecalho.get("description", [])):
        motivos.append("agente sem description no cabeçalho (o Claude Code não o carrega)")
    return motivos


def conferir_no_disco(aberta, plugin: str | None, agentes, arquivos: list) -> list[dict]:
    """Os agentes da ficha contra o plugin já conferido: o arquivo `agents/<nome>.md` existe, o SHA-256 do manifesto é o
    da ficha, uma segunda leitura (pela pasta aberta, sem seguir ligação) dá o mesmo SHA-256 e o cabeçalho diz o mesmo
    que a ficha. Cada problema: {campo, motivo}. Ficha fora da forma ou arquivo não lido: problema, nunca exceção."""
    erros: list[dict] = []

    def erro(rel, motivo, **extra):
        erros.append({"campo": f"plugin {plugin or ''}: {rel}", "motivo": motivo, **extra})
    if not isinstance(agentes, list) or not all(isinstance(a, dict) for a in agentes):
        erro("agentes", "agentes da ficha fora da forma (lista de objetos)")
        return erros
    manifesto = {a["caminho"]: a["sha256"] for a in arquivos}
    try:
        pasta = aberta.sub("agents")
    except Exception:  # noqa: BLE001 - pasta trocada por ligação ou ilegível: nenhum agente vale
        pasta = None
    for a in agentes:
        nome = a.get("nome")
        rel = f"agents/{nome}.md"
        if not isinstance(nome, str) or not NOME_DO_AGENTE.fullmatch(nome) or rel not in manifesto:
            erro(rel, "o agente da ficha não tem o arquivo agents/<nome>.md no plugin (o nome do arquivo é o do agente)")
            continue
        if manifesto[rel] != a.get("sha256"):
            erro(rel, "o SHA-256 do arquivo difere de agentes[].sha256 da ficha: prepare a ficha de novo",
                 calculado=manifesto[rel])
            continue
        try:
            dados = pasta.ler(f"{nome}.md", TETO_ARQUIVO) if pasta is not None else None
        except Exception:  # noqa: BLE001 - ligação, tamanho ou leitura: recusa com o motivo geral
            dados = None
        if dados is None or hashlib.sha256(dados).hexdigest() != manifesto[rel]:
            erro(rel, "o arquivo do agente não foi relido igual ao do manifesto (trocado durante a conferência?)")
            continue
        cabecalho = ler_cabecalho(dados)
        for motivo in (["cabeçalho fora da forma conferida"] if cabecalho is None
                       else problemas_do_cabecalho(a, cabecalho)):
            erro(rel, motivo)
    return erros
