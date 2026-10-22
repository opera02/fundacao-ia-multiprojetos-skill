#!/usr/bin/env python3
"""Plugins do host por dentro: os hooks, os servidores MCP e as skills que cada plugin carrega (análise do
everything-claude-code, 21/10/2026, proposta 1; R54). Usado por `inventariar_host.py`; os alertas de matcher ficam
em `alertas_hooks.py`.

Só lê, sem rede e sem executar nada, e só dentro de `<perfil>/.claude/plugins/`: o `installPath` de cada instalação
de `installed_plugins.json` e as pastas de `synced/` (plugins sincronizados do claude.ai) [Verificado 2026-10-21;
code.claude.com/docs/en/plugins/loading]. Caminho absoluto fora dessa pasta, `..`, ligação (link simbólico ou
junção) e arquivo não regular não são lidos nem seguidos: o motivo vai para `plugins_nao_lidos`, sem o caminho;
tetos de profundidade, entradas e bytes valem durante a varredura (achado [7] da auditoria Codex da 1.7.6). Caminho
com NUL também é recusado antes do disco (o `os.lstat` lançava `ValueError` e derrubava o inventário: revisão de
segurança da 1.7.7, segunda passada, R177B-A-02). JSON com mais de 100 níveis de lista e objeto, ou que estoura o
limite de recursão do `json` (`RecursionError`, que só o `ValueError` não pegava: o `gravar` e o `verificar` saíam com
1, sem saída), vai para `plugins_nao_lidos` com o motivo, como o ilegível; `decodificar` é a mesma leitura que o
`inventariar_host.py` usa no perfil e na raiz (terceira passada, R177C-B-02). `MemoryError` não é tratado: o arquivo
tem teto de 2 MB e a varredura, de 32 MB. A forma esperada de cada arquivo (do plugin, do perfil e da raiz) fica num
lugar só, `FORMAS`, conferida por `forma_inesperada`: o arquivo que foge dela — lista no topo, `"hooks": [..]`, matcher
ou comando que não é texto — vai para `plugins_nao_lidos` com o motivo, em vez de sumir em silêncio ou derrubar o
`inventariar_host.py` (terceira passada, R177C-B-02, tipo inesperado). Só a parte fora da forma fica de fora (`podar`:
a menor que contém o erro numa lista ou num objeto de chaves livres, ou a chave da raiz), o resto é lido, e o registro
de "não lido" guarda o SHA-256 do arquivo, que o `verificar` compara: descartar o arquivo inteiro e comparar só o
motivo escondia a troca de um hook no mesmo arquivo (quarta passada, R177D-3).
Hooks (`hooks/hooks.json` e o campo `hooks` do manifesto): evento, matcher, tipo, nome do executável (nunca
argumentos) e SHA-256 dos scripts citados pela raiz do plugin, dentro da pasta dele. Do matcher ficam a cópia de
exibição (até 200 caracteres, com caractere de controle e surrogate trocados por espaço) e o SHA-256 do inteiro cru,
que é o avaliado pelos alertas e o comparado pelo `verificar` (revisão de segurança da 1.7.7, R177-VAL-03; o cru, e não
o saneado, na segunda passada, R177B-A-01). MCP (`.mcp.json` e
`mcpServers`): nome, tipo, executável ou host — nunca `env`, `headers` nem argumentos. Skills (`skills/` e o campo
`skills`): quantidade e caracteres de `description`, base de uma estimativa de contexto (não é medida).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from urllib.parse import urlsplit

# `aninhamento`: níveis de lista e objeto num JSON (ou TOML) do perfil ou de plugin; o `settings.json` tem 6, e o
# `json.dumps` com recuo do `gravar` estoura perto de mil (revisão de segurança da 1.7.7, terceira passada, R177C-B-02).
TETO = {"profundidade": 8, "entradas": 20000, "bytes": 32 * 2**20, "arquivo": 2 * 2**20, "aninhamento": 100}
CABECA_DA_SKILL = 64 * 1024               # o frontmatter fica no começo do SKILL.md
SUBSTITUTA_DE_NOME = 0x20000000           # Windows: junção, link simbólico e afins (st_reparse_tag)
RAIZ_DO_PLUGIN = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}|\$CLAUDE_PLUGIN_ROOT\b|%CLAUDE_PLUGIN_ROOT%")
NULO = "caminho com caractere nulo"       # o os.lstat lançava ValueError e derrubava o inventário (R177B-A-02)
ANINHADO = "JSON aninhado demais"         # o json.loads lançava RecursionError e derrubava o inventário (R177C-B-02)
SEM_O_CAMINHO = ("caminho absoluto", "caminho com .. ou :", "caminho fundo demais", "ausente",
                 NULO)                    # texto do manifesto, que não é reproduzido
PASTA = "pasta no lugar do arquivo"
MARCAS = (".claude-plugin/plugin.json", "hooks/hooks.json", ".mcp.json", "skills")  # o que faz uma pasta ser plugin
LIMITE_MATCHER = 200                      # cópia de exibição do matcher; avaliação e comparação usam o inteiro cru
CONTROLE = re.compile(r"[\x00-\x1f\x7f\ud800-\udfff]")  # trocados por espaço só no que é exibido (R177B-A-01)


def _sem_controle(valor) -> str | None:
    """Texto inteiro vindo de arquivo de terceiro, para EXIBIÇÃO: sem caracteres de controle nem surrogate solto
    (`\\ud800` num JSON de plugin derrubava a gravação em UTF-8 do inventário; revisão de segurança da 1.7.7,
    R177-VAL-04). O que é avaliado ou comparado usa o texto cru (segunda passada, R177B-A-01)."""
    return None if valor is None else CONTROLE.sub(" ", str(valor))


def _host(url) -> str | None:
    """Host da URL; a malformada (colchete aberto, caractere que a normalização recusa) dá None em vez de derrubar o
    inventário com `ValueError` (revisão de segurança da 1.7.7, R177-VAL-04)."""
    try:
        return urlsplit(str(url or "")).hostname
    except ValueError:
        return None


def _texto(valor, limite: int = 200) -> str | None:
    """Texto vindo de arquivo de terceiro: sem caracteres de controle e com tamanho limitado."""
    texto = _sem_controle(valor)
    return None if texto is None else texto[:limite]


def _matcher(valor) -> dict:
    """Campos do matcher: a cópia de exibição (saneada e cortada) e o SHA-256 do inteiro cru, e o inteiro cru para os
    alertas (sai antes de gravar). Cortar antes de avaliar escondia o que vinha depois do corte (revisão de segurança
    da 1.7.7, R177-VAL-03); sanear antes de avaliar trocava o controle por espaço — `Edit|\\u0001|`, expressão que casa
    tudo, virava a lista exata `Edit| |`, com o hash dela (segunda passada, R177B-A-01)."""
    if valor is None:
        return {"matcher": None}
    inteiro = str(valor)
    return {"matcher": _sem_controle(inteiro)[:LIMITE_MATCHER],
            "matcher_sha256": hashlib.sha256(inteiro.encode("utf-8", "surrogatepass")).hexdigest(),
            "_matcher_inteiro": inteiro}


def _norm(rel) -> str:
    return "/".join(p for p in str(rel).replace("\\", "/").split("/") if p not in ("", "."))


def _lista(valor) -> list:
    return valor if isinstance(valor, list) else [valor] if valor else []


def _nao_lido(origem: str, rel, motivo: str, sha256: str | None = None) -> dict:
    """O motivo de não ler; o caminho só quando o arquivo existe dentro da pasta (texto de manifesto que aponta para
    fora ou para nada não é reproduzido); o SHA-256 quando o arquivo foi lido, para que o `verificar` acuse qualquer
    mudança nele (quarta passada, R177D-3)."""
    perto = rel is not None and motivo not in SEM_O_CAMINHO
    return {"origem": origem, "motivo": motivo, **({"item": _texto(_norm(rel), 120)} if perto else {}),
            **({"sha256": sha256} if sha256 else {})}


class AninhadoDemais(ValueError):
    """JSON (ou TOML) com mais níveis de lista e objeto que o teto, ou que estoura o limite de recursão do leitor: um
    ValueError, tratado como o arquivo inválido (revisão de segurança da 1.7.7, terceira passada, R177C-B-02)."""


def aninhado_demais(valor) -> bool:
    """Mais níveis de lista e objeto (dict) que `TETO["aninhamento"]`, contados sem recursão."""
    pilha = [(valor, 1)] if isinstance(valor, (dict, list)) else []
    while pilha:
        atual, nivel = pilha.pop()
        if nivel > TETO["aninhamento"]:
            return True
        filhos = atual.values() if isinstance(atual, dict) else atual
        pilha.extend((f, nivel + 1) for f in filhos if isinstance(f, (dict, list)))
    return False


def decodificar(texto: str, carregar=json.loads):
    """`json.loads` (ou `tomllib.loads`, em `carregar`) de arquivo do perfil ou de plugin. O aninhamento que estoura o
    limite de recursão (`RecursionError`, que derrubava o inventário) ou passa do teto vira `AninhadoDemais`; o valor
    que o `json` aceita, mas o `json.dumps` com recuo do `gravar` não, também (R177C-B-02)."""
    try:
        dados = carregar(texto)
    except RecursionError:
        raise AninhadoDemais(ANINHADO) from None
    if aninhado_demais(dados):
        raise AninhadoDemais(ANINHADO)
    return dados


# A forma esperada de cada arquivo lido, num lugar só (revisão de segurança da 1.7.7, terceira passada, R177C-B-02,
# tipo inesperado): os objetos e as listas que os leitores percorrem e os textos que viram comando, argumento, matcher,
# endereço ou caminho; o resto (versão, escopo, `env`...) é livre. `None` = qualquer valor; `str` = texto; `[f]` =
# lista de f; `{"*": f}` = objeto de valores f; `{"chave": f}` = objeto em que a chave, quando presente e não nula,
# tem a forma f (as outras são livres); `(f, g)` = uma das formas, a do tipo do valor, e com `None` nela, o valor de
# outro tipo passa. Nulo vale como ausente em qualquer ponto.
EXECUCAO = {"type": str, "command": str, "args": [str], "url": str}  # um hook ou um servidor MCP
EVENTOS = {"*": [{"matcher": str, "hooks": [EXECUCAO]}]}             # o mapa de eventos dos hooks
SERVIDORES = {"*": EXECUCAO}                                          # o mapa de servidores MCP
FORMAS = {
    "settings.json": {"hooks": EVENTOS, "permissions": {"allow": [str], "ask": [str], "deny": [str]}},
    ".claude.json": {"mcpServers": SERVIDORES, "projects": {"*": {"mcpServers": SERVIDORES}}},
    ".mcp.json": {"mcpServers": SERVIDORES},
    # O do plugin pode ser o próprio mapa, sem `mcpServers`: cada objeto da raiz é um servidor (o resto é livre).
    ".mcp.json do plugin": {"mcpServers": SERVIDORES, "*": (EXECUCAO, None)},
    "config.toml": {"mcp_servers": SERVIDORES},
    "installed_plugins.json": {"plugins": {"*": [{"installPath": str}]}},
    "known_marketplaces.json": {"*": {"source": {"source": str, "repo": str, "url": str}}},
    "plugin.json": {"hooks": (str, EVENTOS, [(str, EVENTOS)]), "mcpServers": (str, SERVIDORES, [(str, SERVIDORES)]),
                    "skills": (str, [str])},
    "hooks.json": {"hooks": EVENTOS},
}
TIPOS = ((dict, "objeto"), (list, "lista"), (str, "texto"), (bool, "booleano"), ((int, float), "número"))


def _tipo(valor) -> str:
    return next((nome for tipo, nome in TIPOS if isinstance(valor, tipo)), "outro valor")


def _esperado(forma) -> str:
    if isinstance(forma, tuple):
        nomes = list(dict.fromkeys(_esperado(f) for f in forma if f is not None))
        return ", ".join(nomes[:-1]) + " ou " + nomes[-1] if len(nomes) > 1 else nomes[0]
    return "texto" if forma is str else "lista" if isinstance(forma, list) else "objeto"


class _Removido:
    def __repr__(self) -> str:
        return "REMOVIDO"


REMOVIDO = _Removido()  # a parte que sai da poda (o arquivo inteiro, quando é a raiz)


def podar(valor, forma, onde: str = "", raiz: bool = True) -> tuple:
    """(o valor só com as partes na forma, ou `REMOVIDO`; os pontos que fugiram dela, como `hooks.*[0].hooks: número
    em vez de lista`). Sai a menor parte que contém o erro e está numa lista ou num objeto de chaves livres — o grupo,
    o hook, o servidor, a instalação, o evento —; fora delas, a chave da raiz do arquivo; e a raiz de outro tipo sai
    inteira. O resto é lido: descartar o arquivo inteiro na primeira parte fora da forma escondia o que ele carregava
    (quarta passada, R177D-3). A chave livre sai como `*` (a de um projeto do `.claude.json` é um caminho, que pode
    trazer nome de cliente). A profundidade é a da forma, não a do valor (o aninhamento tem teto em `decodificar`)."""
    lugar = onde or "raiz"
    if forma is None or valor is None:
        return valor, []
    if isinstance(forma, tuple):  # uma das formas: a do tipo do valor; sem ela, só passa quem tem `None` na tupla
        escolhida = next((f for f in forma if f is not None and _esperado(f) == _tipo(valor)), None)
        if escolhida is None:
            return (valor, []) if None in forma else (REMOVIDO, [f"{lugar}: {_tipo(valor)} em vez de "
                                                                   f"{_esperado(forma)}"])
        return podar(valor, escolhida, onde, raiz)
    if forma is str:
        return (valor, []) if isinstance(valor, str) else (REMOVIDO, [f"{lugar}: {_tipo(valor)} em vez de texto"])
    if isinstance(forma, list):
        if not isinstance(valor, list):
            return REMOVIDO, [f"{lugar}: {_tipo(valor)} em vez de lista"]
        saida, erros = [], []
        for i, item in enumerate(valor):  # cada item é uma parte: o que sai é só ele
            podado, erro = podar(item, forma[0], f"{onde}[{i}]", False)
            erros += erro
            if podado is not REMOVIDO:
                saida.append(podado)
        return saida, erros
    if not isinstance(valor, dict):
        return REMOVIDO, [f"{lugar}: {_tipo(valor)} em vez de objeto"]
    saida, erros = {}, []
    for chave, item in valor.items():
        livre = chave == "*" or chave not in forma
        podado, erro = podar(item, forma.get("*") if livre else forma[chave],
                             (f"{onde}." if onde else "") + ("*" if livre else chave), False)
        erros += erro
        if podado is not REMOVIDO:
            saida[chave] = podado
        elif not (livre or raiz):  # a chave nomeada de um registro leva o registro junto
            return REMOVIDO, erros
    return saida, erros


def forma_inesperada(valor, forma, onde: str = "") -> str | None:
    """O primeiro ponto em que o valor foge da forma (o mesmo texto da `podar`), ou None (R177C-B-02, tipo
    inesperado): para o inventário relido, que vale inteiro ou não vale."""
    erros = podar(valor, forma, onde)[1]
    return erros[0] if erros else None


def motivo_da_forma(formato: str, podado, erros: list) -> str:
    """O motivo do arquivo com parte fora da forma: o primeiro ponto, quantos mais, e se o resto foi lido (R177D-3)."""
    resumo = erros[0] + (f" e mais {len(erros) - 1}" if len(erros) > 1 else "")
    return f"{formato} de forma inesperada ({resumo})" + ("" if podado is REMOVIDO else ": o resto foi lido")


class _Teto(Exception):
    """Teto de entradas atingido: a varredura para ali."""


class _Leitor:
    """Leitura contida numa pasta: sem caminho absoluto, `..`, `:`, NUL nem ligação em nenhum trecho; só arquivo
    regular; tetos de entradas e de bytes contados durante a varredura, não depois. Todo acesso ao disco pega
    `ValueError` junto com `OSError`: nome que o sistema recusa vira motivo, não queda (R177B-A-02)."""

    def __init__(self):
        self.entradas = self.bytes = 0

    def caminho(self, base: Path, rel) -> Path | str:
        texto = str(rel).replace("\\", "/")
        if "\x00" in texto:  # antes de tocar o disco, como `..` e `:` (R177B-A-02)
            return NULO
        partes = [p for p in texto.split("/") if p not in ("", ".")]
        if texto.startswith("/") or re.match(r"[A-Za-z]:", texto):
            return "caminho absoluto"
        if ".." in partes or any(":" in p for p in partes):
            return "caminho com .. ou :"
        if len(partes) > TETO["profundidade"]:
            return "caminho fundo demais"
        atual = base
        for parte in partes:  # cada trecho conferido sem seguir ligação (lstat)
            atual = atual / parte
            try:
                st = os.lstat(atual)
            except (OSError, ValueError):
                return "ausente"
            if stat.S_ISLNK(st.st_mode) or getattr(st, "st_reparse_tag", 0) & SUBSTITUTA_DE_NOME:
                return "ligação não seguida"
        return atual

    def pasta(self, base: Path, rel) -> Path | None:
        p = self.caminho(base, rel)
        try:
            return p if isinstance(p, Path) and stat.S_ISDIR(os.lstat(p).st_mode) else None
        except (OSError, ValueError):  # sumiu depois da conferência
            return None

    def ler(self, base: Path, rel, limite: int = TETO["arquivo"], truncar: bool = False) -> bytes | str:
        p = self.caminho(base, rel)
        if isinstance(p, str):
            return p
        try:
            st = os.lstat(p)
        except (OSError, ValueError):  # sumiu depois da conferência
            return "ausente"
        if not stat.S_ISREG(st.st_mode):
            return PASTA if stat.S_ISDIR(st.st_mode) else "não é arquivo regular"
        if st.st_size > limite and not truncar:
            return "arquivo grande demais"
        if self.bytes + min(st.st_size, limite) > TETO["bytes"]:
            return "teto de leitura atingido"
        try:
            with open(p, "rb") as fh:
                fst = os.fstat(fh.fileno())
                if (fst.st_dev, fst.st_ino) != (st.st_dev, st.st_ino):  # trocado depois da conferência
                    return "arquivo trocado durante a leitura"
                dados = fh.read(min(st.st_size, limite))
        except (OSError, ValueError):
            return "ilegível"
        self.bytes += len(dados)
        return dados

    def ler_json(self, base: Path, rel, origem: str, nao_lidos: list, obrigatorio: bool = False, forma=None):
        """O JSON de `rel` (só as partes na `forma`, de `FORMAS`), ou None. Ilegível, aninhado demais (R177C-B-02) ou
        com parte fora da forma (R177C-B-02, tipo inesperado) vai para `nao_lidos` com o motivo e o SHA-256 do
        arquivo, que o `verificar` compara (R177D-3); o ausente só é anotado quando `obrigatorio`."""
        dados, sha = self.ler(base, rel), None
        if isinstance(dados, bytes):
            sha = hashlib.sha256(dados).hexdigest()
            try:
                dados = decodificar(dados.decode("utf-8-sig"))
            except AninhadoDemais:  # antes, o RecursionError derrubava o inventário (R177C-B-02)
                dados = ANINHADO
            except ValueError:
                dados = "JSON ilegível"
            else:
                podado, erros = podar(dados, forma)
                if not erros:
                    return dados
                nao_lidos.append(_nao_lido(origem, rel, motivo_da_forma("JSON", podado, erros), sha))
                return None if podado is REMOVIDO else podado  # só a parte fora da forma fica de fora (R177D-3)
        if dados != "ausente" or obrigatorio:
            nao_lidos.append(_nao_lido(origem, rel, dados, sha))
        return None

    def pastas(self, pasta: Path, origem: str, nao_lidos: list, nomear: bool = True) -> list[str]:
        """Subpastas reais de `pasta`, em ordem; ligação vai para `nao_lidos` (com o nome só se `nomear`)."""
        nomes = []
        try:
            with os.scandir(pasta) as it:
                for entrada in it:
                    self.entradas += 1
                    if self.entradas > TETO["entradas"]:
                        raise _Teto
                    nomes.append(entrada.name)
        except (OSError, ValueError):
            return []
        out = []
        for nome in sorted(nomes):
            if self.pasta(pasta, nome):
                out.append(nome)
            elif self.caminho(pasta, nome) == "ligação não seguida":
                nao_lidos.append(_nao_lido(origem, nome if nomear else None, "ligação não seguida"))
        return out


def _instalados(leitor: _Leitor, raiz: Path, nao_lidos: list) -> list[tuple[str, Path, None]]:
    """Uma origem por pasta instalada, `plugin:<id>|<escopos>` (escopos do mesmo id na mesma pasta juntos). O
    `installPath` é comparado como texto com a pasta de plugins, sem resolver ligação; o de fora não é lido."""
    dados = leitor.ler_json(raiz, "installed_plugins.json", "installed_plugins.json", nao_lidos,
                            forma=FORMAS["installed_plugins.json"])
    registro = dados.get("plugins") if isinstance(dados, dict) else None
    base = os.path.normcase(os.path.normpath(str(raiz))) + os.sep
    grupos: dict[tuple, list] = {}
    for pid, lista in sorted((registro if isinstance(registro, dict) else {}).items()):
        for inst in [i for i in lista if isinstance(i, dict)] if isinstance(lista, list) else []:
            caminho, rel, motivo = inst.get("installPath"), None, "installPath fora da pasta de plugins: não lido"
            if not isinstance(caminho, str) or not caminho.strip():
                motivo = "installPath ausente"
            elif ".." in re.split(r"[\\/]", caminho):
                motivo = "installPath com .."
            elif os.path.isabs(caminho) and os.path.normcase(os.path.normpath(caminho)).startswith(base):
                rel = os.path.normpath(caminho)[len(base):]
            chave = (_texto(pid, 120), os.path.normcase(rel) if rel else motivo)
            grupos.setdefault(chave, [rel, motivo, set()])[2].add(_texto(inst.get("scope"), 40) or "?")
    out = []
    for (pid, _), (rel, motivo, escopos) in sorted(grupos.items()):
        origem = f"plugin:{pid}|{'+'.join(sorted(escopos))}"
        if not rel:
            nao_lidos.append({"origem": origem, "motivo": motivo})
        elif pasta := leitor.pasta(raiz, rel):
            out.append((origem, pasta, None))
        else:
            achado = leitor.caminho(raiz, rel)
            nao_lidos.append({"origem": origem, "motivo": "installPath: " + (achado if isinstance(achado, str)
                                                                             else "não é pasta")})
    return out


def _sincronizados(leitor: _Leitor, raiz: Path, nao_lidos: list) -> list[tuple[str, Path, str]]:
    """Plugins de `synced/`; a pasta da conta fica no meio, e o nome dela não é registrado."""
    def parece(pasta: Path) -> bool:
        return any(isinstance(leitor.caminho(pasta, marca), Path) for marca in MARCAS)

    sync = leitor.caminho(raiz, "synced")
    if isinstance(sync, str):
        if sync != "ausente":
            nao_lidos.append({"origem": "synced", "motivo": sync})
        return []
    achados = []
    for nome in leitor.pastas(sync, "synced", nao_lidos, nomear=False):
        if parece(sync / nome):
            achados.append((nome, sync / nome))
        else:
            achados += [(sub, sync / nome / sub) for sub in leitor.pastas(sync / nome, "synced", nao_lidos, False)
                        if parece(sync / nome / sub)]
    return [(f"plugin:{_texto(n, 120)}@synced|synced", p, f"{_texto(n, 120)}@synced") for n, p in achados]


def _scripts(leitor: _Leitor, raiz: Path, pecas: list) -> list[dict]:
    """SHA-256 dos arquivos que o comando cita pela raiz do plugin; nunca os argumentos. O caminho só sai quando o
    arquivo existe dentro da pasta do plugin."""
    out, vistos = [], set()
    for peca in pecas:
        limpa = str(peca).replace('"', "").replace("'", "")
        m = RAIZ_DO_PLUGIN.search(limpa)
        rel = _norm(re.split(r"[;&|<>()]", limpa[m.end():])[0]) if m else ""
        if rel and rel not in vistos:
            vistos.add(rel)
            dados = leitor.ler(raiz, rel)
            if isinstance(dados, bytes):
                out.append({"caminho": _texto(rel), "sha256": hashlib.sha256(dados).hexdigest()})
            elif dados not in ("ausente", PASTA):
                out.append({"caminho": None if dados in SEM_O_CAMINHO else _texto(rel), "nao_lido": dados})
    return out


def _hooks(leitor: _Leitor, origem: str, raiz: Path, manifesto: dict, executavel, nao_lidos: list) -> list[dict]:
    """`hooks/hooks.json` (com a chave `hooks`) e o campo `hooks` do manifesto: caminho, objeto ou lista."""
    mapas, vistos = [], set()
    for i, fonte in enumerate(["hooks/hooks.json"] + _lista(manifesto.get("hooks"))):
        if isinstance(fonte, dict):
            mapas.append(fonte)  # no manifesto, o objeto já é o mapa de eventos
        elif isinstance(fonte, str) and _norm(fonte) not in vistos:  # o mesmo arquivo não conta duas vezes
            vistos.add(_norm(fonte))
            anotados = len(nao_lidos)
            dados = leitor.ler_json(raiz, fonte, origem, nao_lidos, obrigatorio=i > 0, forma=FORMAS["hooks.json"])
            if isinstance(dados, dict) and isinstance(dados.get("hooks"), dict):
                mapas.append(dados["hooks"])
            elif dados is not None and len(nao_lidos) == anotados:  # o `hooks` podado já foi anotado (R177D-3)
                nao_lidos.append(_nao_lido(origem, fonte, "sem o objeto hooks (o host não carrega)"))
    out = []
    for mapa in mapas:
        for evento, grupos in sorted(mapa.items(), key=lambda par: str(par[0])):
            for grupo in grupos if isinstance(grupos, list) else []:
                lista = grupo.get("hooks") if isinstance(grupo, dict) else None
                for h in [h for h in lista if isinstance(h, dict)] if isinstance(lista, list) else []:
                    tipo = _texto(h.get("type"), 40)
                    item = {"origem": origem, "evento": _texto(evento, 80), **_matcher(grupo.get("matcher")),
                            "tipo": tipo, "executavel": None, "scripts": []}
                    if tipo == "http":
                        item["host"] = _texto(_host(h.get("url")), 120)
                    elif tipo == "mcp_tool":
                        item.update(servidor=_texto(h.get("server"), 120), ferramenta=_texto(h.get("tool"), 120))
                    elif h.get("command"):
                        comando, args = str(h["command"]), h.get("args")
                        item["executavel"] = _texto(executavel(RAIZ_DO_PLUGIN.sub("", comando)), 120)
                        item["scripts"] = _scripts(leitor, raiz, [comando, *map(str, args)] if isinstance(args, list)
                                                   else comando.split())  # forma exec ou de shell
                    out.append(item)
    return out


def _mcp(leitor: _Leitor, origem: str, raiz: Path, manifesto: dict, item_mcp, nao_lidos: list) -> list[dict]:
    """`.mcp.json` e o campo `mcpServers` do manifesto; pacote `.mcpb`/`.dxt` e URL não são abertos."""
    servidores: dict = {}
    for fonte in [".mcp.json"] + _lista(manifesto.get("mcpServers")):
        dados, inline = fonte, isinstance(fonte, dict)  # no manifesto, o objeto já é o mapa de servidores
        if isinstance(fonte, str) and (fonte.lower().endswith((".mcpb", ".dxt")) or re.match(r"(?i)https?:", fonte)):
            nao_lidos.append({"origem": origem, "motivo": "pacote MCP (.mcpb, .dxt ou URL): não aberto"})
            continue
        if isinstance(fonte, str):  # a forma cobre também o arquivo que é o próprio mapa, sem `mcpServers`
            dados = leitor.ler_json(raiz, fonte, origem, nao_lidos, obrigatorio=fonte != ".mcp.json",
                                    forma=FORMAS[".mcp.json do plugin"])
        if isinstance(dados, dict):
            mapa = dados if inline or not isinstance(dados.get("mcpServers"), dict) else dados["mcpServers"]
            servidores.update({str(n): c for n, c in mapa.items() if isinstance(c, dict)})  # o último vence
    out = []
    for nome, cfg in servidores.items():
        item = item_mcp("claude", _texto(nome, 120), cfg, origem)
        out.append({k: _texto(v, 120) if k in ("tipo", "executavel", "host") else v for k, v in item.items()})
    return out


def _descricao(texto: str) -> str:
    """`description` do frontmatter: numa linha, entre aspas ou em bloco (`>` ou `|`)."""
    linhas = texto.lstrip(chr(0xFEFF)).splitlines()
    partes, dentro = [], False
    for linha in linhas[1:] if linhas and linhas[0].strip() == "---" else []:
        if linha.strip() == "---":
            break
        if linha[:1] not in (" ", "\t") and ":" in linha:
            chave, _, valor = linha.partition(":")
            dentro = chave.strip() == "description"
            if dentro:
                partes = [] if valor.strip()[:1] in (">", "|") else [valor.strip()]
        elif dentro and linha.strip():
            partes.append(linha.strip())
    descricao = " ".join(partes).strip()
    return descricao[1:-1] if len(descricao) > 1 and descricao[0] == descricao[-1] in "\"'" else descricao


def _skills(leitor: _Leitor, origem: str, raiz: Path, manifesto: dict, nao_lidos: list) -> dict:
    """`skills/<nome>/SKILL.md`, as pastas do campo `skills` e o plugin que é uma skill só (SKILL.md na raiz)."""
    declaradas = [x for x in _lista(manifesto.get("skills")) if isinstance(x, str)]
    arquivos = [] if leitor.pasta(raiz, "skills") or declaradas else ["SKILL.md"]
    for rel in ["skills"] + declaradas:
        pasta = leitor.caminho(raiz, rel)
        if isinstance(pasta, str):
            if rel != "skills" or pasta != "ausente":
                nao_lidos.append(_nao_lido(origem, rel, pasta))
            continue
        prefixo = _norm(rel) + "/" if _norm(rel) else ""
        if isinstance(leitor.caminho(raiz, prefixo + "SKILL.md"), Path):
            arquivos.append(prefixo + "SKILL.md")
        else:
            arquivos += [prefixo + nome + "/SKILL.md" for nome in leitor.pastas(pasta, origem, nao_lidos)]
    n = caracteres = 0
    for rel in dict.fromkeys(arquivos):
        dados = leitor.ler(raiz, rel, CABECA_DA_SKILL, truncar=True)
        if isinstance(dados, bytes):
            n, caracteres = n + 1, caracteres + len(_descricao(dados.decode("utf-8", "replace")))
        elif dados != "ausente":
            nao_lidos.append(_nao_lido(origem, rel, dados))
    return {"origem": origem, "skills": n, "caracteres_descricao": caracteres}


def ler(perfil: Path, executavel, item_mcp) -> dict:
    """Hooks, MCP e skills dos plugins instalados e sincronizados de `perfil`. `executavel` e `item_mcp` vêm do
    inventário do host: um só lugar decide o que sai de um comando e de um servidor MCP."""
    raiz = Path(perfil) / ".claude" / "plugins"
    res = {"hooks": [], "mcp": [], "skills": [], "nao_lidos": [], "sincronizados": [], "lidos": 0}
    leitor = _Leitor()
    if not leitor.pasta(raiz.parent, raiz.name):
        if leitor.caminho(raiz.parent, raiz.name) == "ligação não seguida":
            res["nao_lidos"].append({"origem": ".claude/plugins", "motivo": "ligação não seguida"})
        return res
    nl = res["nao_lidos"]
    try:
        for origem, pasta, sincronizado in _instalados(leitor, raiz, nl) + _sincronizados(leitor, raiz, nl):
            manifesto = leitor.ler_json(pasta, ".claude-plugin/plugin.json", origem, nl, forma=FORMAS["plugin.json"])
            manifesto = manifesto if isinstance(manifesto, dict) else {}
            if sincronizado:  # sem registro de instalação: entra na lista de plugins pelo manifesto
                res["sincronizados"].append({"id": sincronizado, "versao": _texto(manifesto.get("version"), 60),
                                             "escopo": "synced", "com_projeto": False})
            res["hooks"] += _hooks(leitor, origem, pasta, manifesto, executavel, nl)
            res["mcp"] += _mcp(leitor, origem, pasta, manifesto, item_mcp, nl)
            res["skills"].append(_skills(leitor, origem, pasta, manifesto, nl))
            res["lidos"] += 1
    except _Teto:
        nl.append({"origem": "*", "motivo": f"teto de {TETO['entradas']} entradas: varredura interrompida"})
    return res
