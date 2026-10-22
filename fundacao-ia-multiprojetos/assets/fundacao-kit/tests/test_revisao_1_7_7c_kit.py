"""Revisão de segurança da 1.7.7, terceira passada, área do kit — defesa em profundidade do R177C-B-03: o servidor MCP
não importa um pacote de namespace `mcp`.

Sem o SDK do MCP instalado, `from mcp.server import MCPServer` com uma pasta `mcp/` sem `__init__` no começo do
caminho de importação (a raiz da fundação no uso normal, `python -m fundacao.mcp_servidor` com ela como pasta atual)
monta um pacote de namespace e roda o `mcp/server/__init__.py` da pasta. Agora `mcp_servidor.sdk_do_mcp_instalado()`
só aceita um pacote comum (`importlib.util.find_spec`, que não executa nada): o namespace conta como "pacote mcp
ausente" e nada da pasta roda. O inventário do atualizador da skill recusa a mesma pasta antes
(`scripts/codigo_conferido.py`).

Pastas e identidades fictícias. No cenário, o SDK instalado fica fora do caminho (`python -S`, sem site-packages); o
dublê do registro de ferramentas, que os testes usam quando o SDK falta, continua valendo.
"""

from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path
from unittest import mock

from apoio_auditoria import chamar_ferramenta_mcp
from helpers import FoundationTestCase

from fundacao import mcp_servidor

SEM_SDK = "há um pacote mcp comum fora do site neste Python: o namespace não vence aqui"


def codigo_que_marca(marcador: Path) -> str:
    """Linhas que um atacante plantaria: gravam o marcador quando o módulo é importado."""
    return "from pathlib import Path\nPath(" + repr(str(marcador)) + ").write_text('rodou', encoding='utf-8')\n"


def plantar_namespace(pasta: Path, marcador: Path) -> None:
    """`mcp/server/__init__.py` sem `mcp/__init__.py`: a pasta `mcp/` só vira pacote como namespace."""
    (pasta / "mcp" / "server").mkdir(parents=True)
    (pasta / "mcp" / "server" / "__init__.py").write_text(codigo_que_marca(marcador), encoding="utf-8")


class TestServidorNaoImportaNamespace(FoundationTestCase):
    """O cenário do achado, com o servidor de verdade num processo à parte e a raiz como pasta atual."""

    def rodar(self, *args: str) -> subprocess.CompletedProcess:
        """Python sem site-packages (`-S`) e sem as variáveis PYTHON* (`-E`): a raiz, pasta atual, abre o caminho de
        importação, como no uso normal."""
        return subprocess.run([sys.executable, "-E", "-S", "-B", "-X", "utf8", *args], cwd=str(self.root),
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)

    def test_mcp_sem_init_no_comeco_do_caminho_nao_roda(self):
        marcador = self.root / "marcador-mcp"
        plantar_namespace(self.root, marcador)
        self.rodar("-c", "import mcp.server")
        if not marcador.exists():
            self.skipTest(SEM_SDK)
        marcador.unlink()  # controle: importado, o pacote de namespace roda o que a pasta tiver
        r = self.rodar("-m", "fundacao.mcp_servidor", "--raiz", str(self.root))
        self.assertFalse(marcador.exists(), "o servidor MCP importou o pacote de namespace plantado")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("pacote mcp ausente", r.stderr)


class TestDecisaoDoSdk(unittest.TestCase):
    """A decisão, no próprio processo: pacote comum vale; namespace, achado ou já carregado, não."""

    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp(prefix="sdk-mcp-"))
        self.addCleanup(shutil.rmtree, self.pasta, ignore_errors=True)

    def test_pacote_comum_vale_e_namespace_nao(self):
        namespace = mcp_servidor._pacote_de_namespace
        self.assertFalse(namespace(importlib.util.find_spec("json")))
        nome = "ns_" + uuid.uuid4().hex[:8]
        (self.pasta / nome / "sub").mkdir(parents=True)
        self.assertTrue(namespace(importlib.machinery.PathFinder.find_spec(nome, [str(self.pasta)])))  # só achado
        with mock.patch.object(sys, "path", [str(self.pasta), *sys.path]):
            try:
                modulo = importlib.import_module(nome)  # namespace não tem código: nada roda
                self.assertTrue(namespace(modulo.__spec__))  # carregado: com o carregador de namespace
            finally:
                sys.modules.pop(nome, None)

    def test_namespace_no_comeco_do_caminho_sem_sdk_conta_como_ausente(self):
        marcador = self.pasta / "marcador-mcp"
        plantar_namespace(self.pasta, marcador)
        instalado = importlib.util.find_spec("mcp")
        sdk = os.path.normcase(str(Path(instalado.origin).parents[1])) if instalado and instalado.origin else None
        resto = [p for p in sys.path if os.path.normcase(os.path.abspath(p or ".")) != sdk]
        if getattr(importlib.machinery.PathFinder.find_spec("mcp", resto), "loader", None) is not None:
            self.skipTest(SEM_SDK)  # outro pacote comum mcp no caminho, fora da pasta do SDK achado
        with mock.patch.object(sys, "path", [str(self.pasta), *resto]), mock.patch.dict(sys.modules):
            for nome in [n for n in sys.modules if n == "mcp" or n.startswith("mcp.")]:
                del sys.modules[nome]  # o SDK já carregado por outro teste sai só aqui dentro
            with self.assertRaises(ImportError):
                mcp_servidor.criar_servidor(self.pasta)
            self.assertFalse(marcador.exists(), "o pacote de namespace plantado foi importado")
            self.assertFalse(mcp_servidor.sdk_do_mcp_instalado())

    def test_duble_ja_carregado_continua_valendo(self):
        with mock.patch.dict(sys.modules, {"mcp": types.ModuleType("mcp")}):
            self.assertTrue(mcp_servidor.sdk_do_mcp_instalado())  # posto pelo próprio processo: nada vem do disco


class TestDubleDoSdkSemOPacote(FoundationTestCase):
    """O uso legítimo sem o SDK: o apoio dos testes troca o pacote pelo dublê do registro de ferramentas, e o servidor
    da fundação continua montando as ferramentas reais sobre ele."""

    def test_ferramenta_pelo_duble_quando_o_sdk_falta(self):
        self.write_data("juridico-lab", "catalog.json", json.dumps({"doc-aurora-01": "docs/a.md"}))
        with mock.patch.dict(sys.modules, {"mcp": None}):  # `import mcp` falha: o apoio usa o dublê
            erro, texto, modo = chamar_ferramenta_mcp(self.root, "operador-juridico", "listar_documentos",
                                                      {"projeto": "juridico-lab"})
        self.assertEqual((erro, modo), (False, "duble-do-registro-mcp"), texto)
        self.assertIn("doc-aurora-01", texto)


if __name__ == "__main__":
    unittest.main()
