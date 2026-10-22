#!/usr/bin/env python3
"""Código conferido antes de rodar: o `atualizar_fundacao.py` não executa nada da raiz que ainda não conferiu
(auditoria Codex Security da 1.7.6, #8).

Antes, o `checar` importava o pacote da própria raiz (`python -m fundacao eventos verificar`, com a raiz como pasta
atual) e o ensaio descobria os testes na árvore viva (`unittest discover`): um módulo alterado ou um
`tests/test_*.py` plantado rodava antes de a raiz ser conferida. Agora:
- `inventario`: lista, sem seguir ligação, os arquivos das áreas de código (`fundacao/`, `templates/`, `tests/`) e
  confere cada um pelo hash do kit novo ou pelo registrado na instalação. Executável que nenhum dos dois conhece
  (`.py`, `.pyw`, `.pyc` fora do `__pycache__`, `.pyd`, `.so`), executável com outro hash e ligação fazem recusar;
- `preparar_copia`: copia para uma pasta nova só os arquivos conferidos, conferindo o hash dos bytes copiados (troca
  feita depois da conferência para ali). O código antigo e os testes do ensaio rodam dessas cópias, nunca da raiz;
  registry/ vai junto, sem as cópias do código que o instalador guarda ali (revisão de segurança da 1.7.7, R177-ATU-01);
- `python_isolado`: `python -I` (sem a pasta atual, sem PYTHONPATH nem o site do usuário) com só a cópia conferida,
  ou o kit da própria skill, no caminho de importação. `__pycache__` nunca é copiado: roda só a fonte conferida;
- `apagar_bytecode`: o `__pycache__` não é conferido (o Python o refaz da fonte), mas um `.pyc` de hash não conferido
  plantado ali roda no lugar da fonte no uso normal; a promoção o apaga das áreas de código, sem seguir ligação, e
  `__pycache__` que é ligação recusa como as demais (revisão de segurança da 1.7.7, R177-ATU-02);
- `primeiro_nivel`: o uso normal (`python -m fundacao` com a raiz como pasta atual) põe a raiz no caminho de
  importação, à frente da biblioteca padrão; o inventário confere também os módulos (`.py`, `.pyw`, `.pyc`, `.pyd`,
  `.so`), os `.pth` e os pacotes (pasta com `__init__` executável) do primeiro nível, e o `__pycache__` dali sai na
  promoção (segunda passada, R177B-B-06). Eles nunca vão para as cópias, que levam só as áreas de código. A pasta com
  o nome de um pacote que o kit importa de fora da biblioteca padrão (IMPORTADOS_DE_FORA: `mcp`) entra mesmo sem
  `__init__`: sem o SDK instalado, o Python a monta como pacote de namespace e roda o que ela tiver (terceira passada,
  R177C-B-03).
Limite: o hash "registrado na instalação" vem de registry/kit_install.json, que a mesma conta grava; quem troca o
código e o registro juntos passa por "versão anterior" (references/seguranca-isolamento.md §6). O ganho é que nada
roda antes da conferência, e o que roda é exatamente o que foi conferido.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import shutil
import stat
import sys
from pathlib import Path

AREAS_DE_CODIGO = ("fundacao", "templates", "tests")
DERIVADOS = {"__pycache__", ".pytest_cache"}  # não são conferidos nem copiados; nada roda deles
# O que o instalador e o atualizador guardam em registry/ não é configuração: cópias do código (kit_backup/,
# kit_preparo/), históricos e o inventário do host. A cópia dos testes não os leva: o `FoundationTestCase` do kit copia
# registry/ para cada raiz de teste, e o fonte antigo guardado em kit_backup/ pela promoção do ensaio virava regressão
# falsa (revisão de segurança da 1.7.7, R177-ATU-01).
FORA_DOS_DADOS = {"registry": frozenset({"kit_backup", "kit_preparo", "kit_install.json", "atualizacoes.jsonl",
                                         "inventario-host.json"})}
EXECUTAVEIS = (".py", ".pyw", ".pyc", ".pyd", ".so")  # o que o Python importa de uma pasta no caminho
EXECUTAVEIS_NA_RAIZ = EXECUTAVEIS + (".pth",)  # no primeiro nível da raiz, também o que o `site` leria (R177B-B-06)
# Módulos de primeiro nível que o kit importa de fora da biblioteca padrão (o SDK do MCP, em mcp_servidor.py). Pacote
# comum da biblioteca padrão ou instalado sempre vence um pacote de namespace; sem ele, o Python monta o namespace com
# a pasta da raiz que tiver o nome, mesmo sem `__init__`, e roda o que ela tiver. Em minúsculas, comparados sem caixa,
# como o Windows compara; tests/test_revisao_seguranca_177c_atualizador.py os deriva dos fontes do kit pela árvore
# sintática e para se divergirem (R177C-B-03).
IMPORTADOS_DE_FORA = ("mcp",)
MODULO_VALIDO = re.compile(r"[_a-z]\w*\.py$", re.IGNORECASE)  # o mesmo filtro de nomes do unittest discover
SUBSTITUTA_DE_NOME = 0x20000000  # Windows: junção, link simbólico e afins (bit 29 da etiqueta de reparse)

# Programas para `python_isolado`. O preâmbulo põe a pasta de código conferida (1º argumento) no caminho.
PREAMBULO = "import sys\nsys.path.insert(0, sys.argv.pop(1))\n"
CLI = "import runpy\nrunpy.run_module('fundacao', run_name='__main__', alter_sys=True)\n"
CADEIA = """import json
from pathlib import Path
from fundacao.core.db import conectar_somente_leitura
from fundacao.core.events import verify_chain
con = conectar_somente_leitura(Path(sys.argv[1]) / "state" / "state.sqlite")
try:
    ok, ruim = verify_chain(con)
finally:
    con.close()
print(json.dumps({"cadeia_integra": ok, "primeiro_evento_quebrado": ruim}))
"""
RUNNER = r"""import json, os, unittest
sys.path.insert(0, os.path.join(sys.path[0], "tests"))  # como o `discover -s tests` na raiz: tests/ e a raiz
suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(m) for m in json.loads(sys.argv[1]))
ids = []
def coletar(s):
    for t in s:
        coletar(t) if isinstance(t, unittest.TestSuite) else ids.append(t.id())
coletar(suite)
with open(os.devnull, "w", encoding="utf-8") as nada:
    r = unittest.TextTestRunner(stream=nada, verbosity=0).run(suite)
falhas = r.failures + r.errors
print(json.dumps({"total": r.testsRun, "ids": sorted(ids), "falhas": sorted(t.id() for t, _ in falhas),
                  "detalhes": {t.id(): tb[-1200:] for t, tb in falhas}, "pulados": len(r.skipped),
                  "pulados_ids": {t.id(): str(m)[:200] for t, m in r.skipped}}))
"""


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def executavel(rel: str) -> bool:
    return rel.lower().endswith(EXECUTAVEIS)


def ligacao(p: Path) -> bool:
    """Link simbólico ou junção, conferido sem seguir."""
    try:
        st = os.lstat(p)
    except OSError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & SUBSTITUTA_DE_NOME)


def percorrer(base: Path, areas: tuple = AREAS_DE_CODIGO) -> tuple[dict, list]:
    """Arquivos das `areas` de `base` (caminho relativo -> caminho) e as ligações nelas, sem atravessar ligação nem
    pasta derivada. `os.walk` sozinho entraria na junção do Windows."""
    base = Path(base)
    arquivos, ligacoes = {}, []
    for area in areas:
        if ligacao(base / area):
            ligacoes.append(area)
            continue
        for pasta, subpastas, nomes in os.walk(base / area):
            atual = Path(pasta)
            for nome in sorted(subpastas):
                if nome in DERIVADOS or ligacao(atual / nome):
                    subpastas.remove(nome)
                    if ligacao(atual / nome):  # também `__pycache__` que é ligação (R177-ATU-02)
                        ligacoes.append((atual / nome).relative_to(base).as_posix())
            for nome in nomes:
                rel = (atual / nome).relative_to(base).as_posix()
                if ligacao(atual / nome):
                    ligacoes.append(rel)
                else:
                    arquivos[rel] = atual / nome
    return arquivos, sorted(ligacoes)


def primeiro_nivel(base: Path) -> tuple[dict, list]:
    """Executáveis do primeiro nível de `base`, fora das áreas de código (caminho relativo -> caminho): módulo ou `.pth`
    solto e o `__init__` de pasta que é pacote; e as ligações com esses nomes ou com o de `__pycache__`. Sem seguir
    ligação, salvo para ver se a pasta do outro lado é pacote (R177B-B-06). A pasta com nome de IMPORTADOS_DE_FORA
    entra mesmo sem `__init__` (pacote de namespace), com todos os executáveis dela, como uma área de código; a
    ligação com esse nome ou dentro dela, sem seguir (R177C-B-03)."""
    base, arquivos, ligacoes = Path(base), {}, []
    try:
        nomes = sorted(os.listdir(base))
    except OSError:
        return arquivos, ligacoes
    for nome in nomes:
        caminho = base / nome
        if nome in AREAS_DE_CODIGO or nome == "__pycache__":  # as áreas têm o inventário delas; o `bytecode`, este
            if nome == "__pycache__" and ligacao(caminho):
                ligacoes.append(nome)
            continue
        if nome.lower() in IMPORTADOS_DE_FORA:  # namespace que o kit importaria sem o SDK instalado (R177C-B-03)
            da_pasta, elos = percorrer(base, (nome,))
            arquivos.update({rel: p for rel, p in da_pasta.items() if executavel(rel)})
            ligacoes += elos
            continue
        if nome.lower().endswith(EXECUTAVEIS_NA_RAIZ):
            if ligacao(caminho):
                ligacoes.append(nome)
            elif caminho.is_file():
                arquivos[nome] = caminho
            continue
        try:  # pacote: pasta com `__init__` executável (o `os.listdir` lê a pasta do outro lado da ligação, sem rodar)
            inits = [n for n in sorted(os.listdir(caminho)) if n.lower().startswith("__init__.") and executavel(n)]
        except OSError:
            continue  # não é pasta
        if inits and ligacao(caminho):
            ligacoes.append(nome)
        elif inits:
            arquivos.update({nome + "/" + init: caminho / init for init in inits})
    return arquivos, sorted(ligacoes)


def inventario(base: Path, do_kit: dict, registrados: dict) -> dict:
    """O que as áreas de código de `base` têm: `conferidos` (caminho -> sha256 igual ao do kit novo ou ao registrado
    na instalação), executáveis `a_mais` (nenhum dos dois conhece o caminho), executáveis `alterados` (conhecidos,
    com outro hash) e `ligacoes`. Arquivo de dados desconhecido (ex.: um .md do titular em templates/) fica de fora.
    O primeiro nível da raiz também (`primeiro_nivel`): executável ali que nem o kit novo nem o registro conhecem, com
    este hash, vai para `a_mais`; o conhecido não vai para `conferidos`, que são as cópias (R177B-B-06). Inclusive o
    que está dentro da pasta `mcp/`, mesmo sem `__init__` (R177C-B-03)."""
    arquivos, ligacoes = percorrer(base)
    soltos, ligacoes_na_raiz = primeiro_nivel(base)
    res = {"conferidos": {}, "a_mais": [], "alterados": [], "ligacoes": sorted(ligacoes + ligacoes_na_raiz)}
    for rel, caminho in sorted(arquivos.items()):
        atual = sha(caminho)
        if atual in (do_kit.get(rel), registrados.get(rel)):
            res["conferidos"][rel] = atual
        elif executavel(rel):
            res["alterados" if rel in do_kit or rel in registrados else "a_mais"].append(rel)
    res["a_mais"] = sorted(res["a_mais"] + [rel for rel, caminho in soltos.items()
                                            if sha(caminho) not in (do_kit.get(rel), registrados.get(rel))])
    return res


def preparar_copia(origem: Path, arquivos: dict, destino: Path, areas: tuple = AREAS_DE_CODIGO,
                   dados: tuple = ()) -> None:
    """Copia para `destino` (pasta nova) exatamente os `arquivos` (caminho -> sha256), conferindo o hash dos bytes
    lidos antes de gravá-los, e as pastas de `dados` como estão, menos o que FORA_DOS_DADOS tira delas. Recusa
    (ValueError) ligação ou executável fora da lista nas `areas` da origem e arquivo da lista ausente, atrás de ligação
    ou diferente."""
    vistos, ligacoes = percorrer(origem, areas)
    a_mais = sorted(rel for rel in vistos if executavel(rel) and rel not in arquivos)
    if ligacoes or a_mais:
        raise ValueError("ligação ou executável fora da lista conferida: " + ", ".join((ligacoes + a_mais)[:5]))
    Path(destino).mkdir(parents=True)
    for rel, esperado in sorted(arquivos.items()):
        if rel not in vistos:
            raise ValueError("ausente ou atrás de ligação: " + rel)
        conteudo = vistos[rel].read_bytes()
        if hashlib.sha256(conteudo).hexdigest() != esperado:
            raise ValueError("diferente do conferido: " + rel)
        alvo = Path(destino) / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(conteudo)
    for pasta in dados:
        _copiar_dados(Path(origem) / pasta, Path(destino) / pasta, FORA_DOS_DADOS.get(pasta, frozenset()))


def _copiar_dados(origem: Path, destino: Path, fora: frozenset = frozenset()) -> None:
    """Pasta de dados (registry/, que os testes do kit copiam) como está, sem atravessar ligação nem levar as pastas
    derivadas nem os nomes de `fora` no primeiro nível. Não fica no caminho de importação como módulo próprio: é lida,
    não executada."""
    if ligacao(origem) or not origem.is_dir():
        return
    for pasta, subpastas, nomes in os.walk(origem):
        atual = Path(pasta)
        tirar = fora if atual == origem else frozenset()
        subpastas[:] = [n for n in sorted(subpastas) if n not in DERIVADOS | tirar and not ligacao(atual / n)]
        (destino / atual.relative_to(origem)).mkdir(parents=True, exist_ok=True)
        for nome in nomes:
            if nome not in tirar and not ligacao(atual / nome):
                shutil.copy2(atual / nome, destino / atual.relative_to(origem) / nome)


def bytecode(base: Path, areas: tuple = AREAS_DE_CODIGO) -> list:
    """Pastas `__pycache__` das `areas` de `base` e a do primeiro nível (R177B-B-06), as que são ligação inclusive,
    achadas sem atravessar ligação."""
    base = Path(base)
    achadas = ["__pycache__"] if ligacao(base / "__pycache__") or (base / "__pycache__").is_dir() else []
    for area in areas:
        if ligacao(base / area) or not (base / area).is_dir():
            continue
        for pasta, subpastas, _nomes in os.walk(base / area):
            atual = Path(pasta)
            achadas += [(atual / n).relative_to(base).as_posix() for n in subpastas if n == "__pycache__"]
            subpastas[:] = [n for n in sorted(subpastas) if n not in DERIVADOS and not ligacao(atual / n)]
    return sorted(achadas)


def apagar_bytecode(base: Path, areas: tuple = AREAS_DE_CODIGO) -> tuple:
    """Apaga as pastas `__pycache__` das `areas` sem seguir ligação: a que é ligação sai sozinha, e o alvo dela fica
    como estava. Devolve (apagadas, falhas); depois da promoção, o Python só roda bytecode refeito da fonte conferida
    (R177-ATU-02)."""
    apagadas, falhas = [], []
    for rel in bytecode(base, areas):
        caminho = Path(base) / rel
        try:
            if ligacao(caminho):
                try:
                    os.unlink(caminho)
                except OSError:
                    os.rmdir(caminho)  # junção e link de pasta do Windows: sai o nome, o alvo não é tocado
            else:
                shutil.rmtree(caminho)  # não atravessa ligação de dentro (3.8+)
            apagadas.append(rel)
        except OSError as exc:
            falhas.append(rel + " (" + type(exc).__name__ + ": " + str(exc)[:120] + ")")
    return apagadas, falhas


def modulos_de_teste(arquivos, padrao: str) -> list:
    """Os módulos que o `unittest discover -s tests -p <padrao>` importaria, tirados da lista conferida (não da pasta):
    arquivo direto em tests/, ou em subpasta que seja pacote (com __init__.py), de nome válido casado com o padrão."""
    pacotes = {rel[:-len("/__init__.py")] for rel in arquivos if rel.endswith("/__init__.py")}
    modulos = []
    for rel in arquivos:
        partes = rel.split("/")
        if partes[0] != "tests" or len(partes) < 2 or not MODULO_VALIDO.match(partes[-1]) \
                or not fnmatch.fnmatch(partes[-1], padrao):
            continue
        if all("/".join(partes[:i]) in pacotes for i in range(2, len(partes))):
            modulos.append(".".join(partes[1:])[:-3])
    return sorted(modulos)


def python_isolado(codigo: Path, programa: str, *args) -> list:
    """Comando que roda `programa` com a pasta conferida `codigo` à frente da biblioteca padrão no caminho de
    importação e nada mais: `-I` tira a pasta atual, o PYTHONPATH e o site do usuário; `-B` não grava bytecode;
    `-X utf8` mantém o UTF-8 que o `-I` deixaria de ler do ambiente (PYTHONUTF8)."""
    return [sys.executable, "-I", "-B", "-X", "utf8", "-c", PREAMBULO + programa, str(codigo), *map(str, args)]
