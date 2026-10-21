"""Fronteiras do código e teto de tamanho, conferidos pela árvore sintática (proposta 10 da análise do
vibe-coding-toolkit, 21/10/2026).

As regras eram só texto (references/principios-e-evidencias.md; db.py liga foreign_keys, busy_timeout e WAL em
cada conexão). Agora valem como teste, só com a biblioteca padrão e sem executar o código lido:
- SQLite só é aberto por core/db.py, core/backup.py e __main__.py (as conexões com as PRAGMAs da fundação);
- o núcleo (core/) não importa adaptador — a dívida conhecida fica enumerada e não pode crescer;
- nada de print fora dos pontos de entrada; só biblioteca padrão (o SDK mcp só no servidor MCP);
- arquivo novo fica em até 350 linhas; arquivo maior tem teto que não sobe e que precisa descer quando o
  arquivo encolhe (divisão por responsabilidade, não por tamanho).
Cada regra é testada também contra trechos de código certos, errados e "quase certos" (apelido, outro objeto).
"""

from __future__ import annotations

import ast
import sys
import unittest

from helpers import KIT

PACOTE = KIT / "fundacao"
ABREM_SQLITE = {"fundacao/core/db.py", "fundacao/core/backup.py", "fundacao/__main__.py"}
PONTOS_DE_ENTRADA = {"fundacao/__main__.py", "fundacao/mcp_servidor.py"}
TERCEIROS = {"fundacao/mcp_servidor.py": {"mcp"}}
# Dívida conhecida: components.py usa adapters.cli._processo (contenção do processo no Windows). Não cresce.
DIVIDA_NUCLEO_ADAPTADOR = {"fundacao/core/components.py"}
LIMITE, FOLGA = 350, 30
TETO = {"fundacao/__main__.py": 384, "fundacao/adapters/cli.py": 405, "fundacao/core/backup.py": 882,
        "fundacao/core/decisoes.py": 786, "fundacao/core/knowledge.py": 442, "fundacao/core/memory.py": 560,
        "fundacao/core/tasks.py": 803}


def modulos() -> dict[str, ast.Module]:
    return {p.relative_to(KIT).as_posix(): ast.parse(p.read_text(encoding="utf-8"))
            for p in sorted(PACOTE.rglob("*.py")) if "__pycache__" not in p.parts}


def abre_sqlite(arvore: ast.Module) -> bool:
    apelidos, funcoes = set(), set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            apelidos |= {a.asname or a.name for a in no.names if a.name == "sqlite3"}
        elif isinstance(no, ast.ImportFrom) and no.module == "sqlite3":
            funcoes |= {a.asname or a.name for a in no.names if a.name == "connect"}
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call):
            f = no.func
            if isinstance(f, ast.Attribute) and f.attr == "connect" and isinstance(f.value, ast.Name) \
                    and f.value.id in apelidos:
                return True
            if isinstance(f, ast.Name) and f.id in funcoes:
                return True
    return False


def importa_adaptador(arvore: ast.Module) -> bool:
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom):
            modulo = no.module or ""
            if (no.level and modulo.split(".")[0] == "adapters") or modulo.startswith("fundacao.adapters"):
                return True
            if no.level >= 2 and not modulo and any(a.name == "adapters" for a in no.names):
                return True
        elif isinstance(no, ast.Import) and any(a.name.startswith("fundacao.adapters") for a in no.names):
            return True
    return False


def usa_print(arvore: ast.Module) -> bool:
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print"
               for n in ast.walk(arvore))


def de_terceiros(arvore: ast.Module) -> set[str]:
    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes |= {a.name.split(".")[0] for a in no.names}
        elif isinstance(no, ast.ImportFrom) and no.level == 0 and no.module:
            nomes.add(no.module.split(".")[0])
    return {n for n in nomes if n not in sys.stdlib_module_names and n != "fundacao"}


class TestRegrasContraTrechos(unittest.TestCase):
    """As próprias regras, contra casos certos, errados e quase certos."""

    def test_detectores(self):
        p = ast.parse
        self.assertTrue(abre_sqlite(p("import sqlite3\nsqlite3.connect('x')")))
        self.assertTrue(abre_sqlite(p("import sqlite3 as _sq\n_sq.connect('x')")))
        self.assertTrue(abre_sqlite(p("from sqlite3 import connect as c\nc('x')")))
        self.assertFalse(abre_sqlite(p("import sqlite3\nconexao.connect()")))
        self.assertTrue(importa_adaptador(p("from ..adapters.cli import _processo")))
        self.assertTrue(importa_adaptador(p("from fundacao.adapters import base")))
        self.assertTrue(importa_adaptador(p("from .. import adapters")))
        self.assertFalse(importa_adaptador(p("from .db import connect\nfrom ..components import x")))
        self.assertTrue(usa_print(p("print('x')")))
        self.assertFalse(usa_print(p("logger.print('x')\nsys.stdout.write('x')")))
        self.assertEqual(de_terceiros(p("import json, requests\nfrom mcp import x\nfrom .core import y")),
                         {"requests", "mcp"})


class TestFronteirasDoKit(unittest.TestCase):
    def setUp(self):
        self.mods = modulos()

    def test_sqlite_so_nos_modulos_de_banco(self):
        self.assertEqual(sorted(r for r, a in self.mods.items() if abre_sqlite(a)), sorted(ABREM_SQLITE))

    def test_nucleo_nao_depende_de_adaptador(self):
        violacoes = {r for r, a in self.mods.items() if r.startswith("fundacao/core/") and importa_adaptador(a)}
        self.assertEqual(violacoes - DIVIDA_NUCLEO_ADAPTADOR, set(), "dependência nova do núcleo para adaptador")
        self.assertEqual(DIVIDA_NUCLEO_ADAPTADOR - violacoes, set(), "dívida paga: tire da lista")

    def test_sem_print_fora_dos_pontos_de_entrada(self):
        self.assertEqual(sorted(r for r, a in self.mods.items() if r not in PONTOS_DE_ENTRADA and usa_print(a)), [])

    def test_so_biblioteca_padrao(self):
        terceiros = {r: de_terceiros(a) - TERCEIROS.get(r, set()) for r, a in self.mods.items()}
        self.assertEqual({r: n for r, n in terceiros.items() if n}, {})

    def test_teto_de_tamanho_so_desce(self):
        linhas = {p.relative_to(KIT).as_posix(): len(p.read_text(encoding="utf-8").splitlines())
                  for p in sorted(PACOTE.rglob("*.py")) if "__pycache__" not in p.parts}
        acima = {r: n for r, n in linhas.items() if n > TETO.get(r, LIMITE)}
        self.assertEqual(acima, {}, "arquivo novo até 350 linhas; teto existente não sobe — divida por responsabilidade")
        folgados = {r: (linhas.get(r), t) for r, t in TETO.items() if r not in linhas or linhas[r] < t - FOLGA
                    or t <= LIMITE}
        self.assertEqual(folgados, {}, "o arquivo encolheu (ou sumiu): baixe o teto em TETO")


if __name__ == "__main__":
    unittest.main()
