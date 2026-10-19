"""A11C — servidor MCP da fundação (R34): descoberta, chamada autorizada e negativa entre projetos.

Conexão em processo pelo SDK oficial (`mcp`). Ignorado quando o pacote não está instalado.
O ensaio com processo separado (stdio) fica em `scripts/mcp_ensaio.py` da skill.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import unittest
from unittest import mock

from helpers import CANARIOS, FoundationTestCase

TEM_MCP = importlib.util.find_spec("mcp") is not None


@unittest.skipUnless(TEM_MCP, "pacote mcp ausente")
class TestServidorMCP(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.write_data("juridico-lab", "catalog.json", json.dumps({"doc-aurora-01": "docs/a.md"}))
        self.write_data("reversa-lab", "catalog.json", json.dumps({"doc-" + CANARIOS["reversa-lab"].lower(): "x.md"}))

    def chamar(self, principal: str):
        from mcp import Client

        from fundacao.mcp_servidor import criar_servidor
        app = criar_servidor(self.root)

        async def roteiro():
            async with Client(app) as client:
                nomes = sorted(t.name for t in (await client.list_tools()).tools)
                proprios = await client.call_tool("listar_documentos", {"projeto": "juridico-lab"})
                alheio = await client.call_tool("listar_documentos", {"projeto": "reversa-lab"})
                return nomes, proprios, alheio

        with mock.patch.dict(os.environ, {"FUNDACAO_PRINCIPAL": principal}):
            return asyncio.run(roteiro())

    def test_descoberta_chamada_e_negativa(self):
        nomes, proprios, alheio = self.chamar("operador-juridico")
        self.assertEqual(nomes, ["buscar", "listar_documentos", "listar_projetos"])
        self.assertFalse(proprios.is_error)
        self.assertIn("doc-aurora-01", json.dumps([c.text for c in proprios.content]))
        self.assertTrue(alheio.is_error)
        texto = " ".join(c.text for c in alheio.content)
        self.assertIn("acesso negado", texto)
        self.assertNotIn(CANARIOS["reversa-lab"].lower(), texto.lower())
        n = self.con.execute("SELECT COUNT(*) FROM event WHERE kind='access_denied' AND subject=?",
                             ("operador-juridico",)).fetchone()[0]
        self.assertGreaterEqual(n, 1)


if __name__ == "__main__":
    unittest.main()
