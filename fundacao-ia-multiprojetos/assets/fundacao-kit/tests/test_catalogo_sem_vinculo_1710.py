"""F6 da revisão de segurança da 1.7.9 (corrigido na 1.7.10): data/catalog.json lido por um ajudante só, na CLI
(`conhecimento listar`) e no servidor MCP (`listar_documentos`), que abre sem seguir ligação, confere com o fstat um
nome só (st_nlink == 1) e que o objeto aberto é o mesmo do caminho conferido.

Antes, `read_text` seguia o vínculo físico (hard link, que no Windows qualquer conta cria sem privilégio) do catálogo
de um projeto para o de outro, que `contained` não vê: quem lia o próprio projeto recebia os identificadores do outro.
Raiz descartável com projetos e identidades de ensaio; onde o sistema de arquivos não permite vínculo físico, o teste
é pulado."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import types
import unittest
from unittest import mock

from helpers import CANARIOS, FoundationTestCase

from fundacao import cli_conhecimento
from fundacao.core.contracts import PathEscape

IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"
TEM_MCP = importlib.util.find_spec("mcp") is not None
ALHEIO = "doc-" + CANARIOS["reversa-lab"].lower()


class TestCatalogoSemVinculo(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.alheio = self.write_data("reversa-lab", "catalog.json", json.dumps({ALHEIO: "x.md"}))
        self.proprio = self.root / "projects" / "juridico-lab" / "data" / "catalog.json"
        self.proprio.parent.mkdir(parents=True, exist_ok=True)

    def vincular(self) -> None:
        self.proprio.unlink(missing_ok=True)  # o projeto nasce com um catálogo vazio
        try:
            os.link(self.alheio, self.proprio)
        except (OSError, NotImplementedError) as exc:  # FAT/exFAT e afins
            self.skipTest(f"vínculo físico indisponível aqui: {exc}")

    def cli(self, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != IDENTIDADE}
        env.update({"PYTHONDONTWRITEBYTECODE": "1", IDENTIDADE: "operador-juridico"})
        return subprocess.run([sys.executable, "-m", "fundacao", "--raiz", str(self.root), *args], capture_output=True,
                              text=True, encoding="utf-8", cwd=str(self.root), env=env)

    def test_cli_recusa_o_vinculo_fisico_com_o_catalogo_de_outro_projeto(self):
        self.vincular()
        p = self.cli("conhecimento", "listar", "--projeto", "juridico-lab")
        self.assertEqual(p.returncode, 2, p.stdout)
        self.assertEqual(json.loads(p.stderr)["error"]["code"], "E_PATH_ESCAPE")
        self.assertNotIn(CANARIOS["reversa-lab"].lower(), (p.stdout + p.stderr).lower())

    def test_catalogo_que_e_ligacao_para_dentro_do_projeto_recusa(self):
        # F6 (1.7.10): antes, `contained` resolvia a ligação (que aponta para dentro do próprio projeto) e o lstat via
        # o alvo, não a ligação, seguindo-a. Agora o lstat do caminho não resolvido recusa antes de resolver.
        alvo = self.proprio.parent / "real.json"
        alvo.write_text(json.dumps({"doc-interno-01": "x.md"}), encoding="utf-8")
        self.proprio.unlink(missing_ok=True)
        try:
            self.proprio.symlink_to(alvo)
        except (OSError, NotImplementedError) as exc:  # Windows sem privilégio de link simbólico
            self.skipTest(f"link simbólico indisponível aqui: {exc}")
        with self.assertRaises(PathEscape):
            cli_conhecimento.ler_catalogo(self.proprio.parents[1])

    def test_controle_catalogo_comum_e_ausente(self):
        p = self.cli("conhecimento", "listar", "--projeto", "juridico-lab")
        self.assertEqual(json.loads(p.stdout), {"projeto": "juridico-lab", "documentos": []})
        self.proprio.write_text(json.dumps({"doc-aurora-01": "notas.md"}), encoding="utf-8")
        p = self.cli("conhecimento", "listar", "--projeto", "juridico-lab")
        self.assertEqual(json.loads(p.stdout), {"projeto": "juridico-lab", "documentos": ["doc-aurora-01"]})

    def test_ajudante_confere_o_fstat_depois_de_abrir(self):
        self.vincular()
        pasta = self.proprio.parents[1]
        with self.assertRaises(PathEscape):
            cli_conhecimento.ler_catalogo(pasta)
        real = os.lstat

        def lstat_de_um_nome(p, *a, **k):  # o vínculo aparece só depois do lstat (corrida): o fstat pega
            st = real(p, *a, **k)
            return types.SimpleNamespace(st_mode=st.st_mode, st_nlink=1, st_dev=st.st_dev, st_ino=st.st_ino,
                                         st_size=st.st_size, st_reparse_tag=getattr(st, "st_reparse_tag", 0))

        lidos = []
        ler = os.read
        with mock.patch.object(cli_conhecimento.os, "lstat", lstat_de_um_nome), \
                mock.patch.object(cli_conhecimento.os, "read", lambda fd, n: lidos.append(n) or ler(fd, n)):
            with self.assertRaises(PathEscape):
                cli_conhecimento.ler_catalogo(pasta)
        self.assertEqual(lidos, [], "o conteúdo foi lido antes da recusa")

    def test_o_servidor_mcp_usa_o_mesmo_ajudante(self):
        codigo = (self.root / "fundacao" / "mcp_servidor.py").read_text(encoding="utf-8")
        self.assertIn("ler_catalogo(pasta)", codigo)
        self.assertNotIn("read_text", codigo)

    @unittest.skipUnless(TEM_MCP, "pacote mcp ausente")
    def test_mcp_recusa_o_vinculo_sem_conteudo(self):
        self.vincular()
        from mcp import Client

        from fundacao.mcp_servidor import criar_servidor
        app = criar_servidor(self.root)

        async def roteiro():
            async with Client(app) as client:
                return await client.call_tool("listar_documentos", {"projeto": "juridico-lab"})

        with mock.patch.dict(os.environ, {IDENTIDADE: "operador-juridico"}):
            resposta = asyncio.run(roteiro())
        self.assertTrue(resposta.is_error)
        self.assertNotIn(CANARIOS["reversa-lab"].lower(), " ".join(c.text for c in resposta.content).lower())


if __name__ == "__main__":
    unittest.main()
