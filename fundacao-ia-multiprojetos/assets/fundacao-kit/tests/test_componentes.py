"""A11/A34 — descoberta sem execução, habilitação, autorização, timeout e dependências (R32, R47)."""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from helpers import CANARIOS, FoundationTestCase

from fundacao.core import components
from fundacao.core.contracts import AccessDenied, ComponentDisabled, DependencyUnavailable, FundacaoError


class TestComponentes(FoundationTestCase):
    def setUp(self):
        super().setUp()
        reg = self.root / "registry" / "components" / "source_manifest.json"
        entry = json.loads(reg.read_text(encoding="utf-8"))
        entry["allowed_projects"] = ["juridico-lab", "reversa-lab"]
        reg.write_text(json.dumps(entry), encoding="utf-8")
        self.write_data("juridico-lab", "docs/aurora.md", "Relato fictício " + CANARIOS["juridico-lab"])
        self.write_data("juridico-lab", "catalog.json", json.dumps({
            "doc-aurora-01": "docs/aurora.md", "doc-fuga": "../../reversa-lab/data/x.md"}))
        self.write_data("reversa-lab", "docs/caixasim.md", "Especificação " + CANARIOS["reversa-lab"])
        self.write_data("reversa-lab", "catalog.json", json.dumps({"doc-caixasim-01": "docs/caixasim.md"}))

    def _bomba(self):
        """Componente cujo import teria efeito: a descoberta não pode importá-lo."""
        mod = self.root / "fundacao" / "components" / "bomba.py"
        mod.write_text("raise RuntimeError('import executado')\n", encoding="utf-8")
        reg = self.root / "registry" / "components" / "bomba.json"
        reg.write_text(json.dumps({
            "schema_version": "fundacao.component/1", "component_id": "bomba", "version": "0.1.0",
            "kind": "tool", "enabled": True, "entrypoint": "fundacao.components.bomba:run",
            "allowed_projects": ["juridico-lab"], "permissions": [], "timeout_seconds": 5}), encoding="utf-8")

    def test_texto_acentuado_independe_da_pagina_de_codigo(self):
        mod = self.root / "fundacao" / "components" / "acentos.py"
        mod.write_text(
            "import subprocess, sys\n"
            "def run(request):\n"
            "    filho = subprocess.run([sys.executable, '-c', \"print('Petição — ação nº 1 ✓')\"],\n"
            "                           capture_output=True, text=True, encoding='utf-8')\n"
            "    return {'direto': 'Pendências: competência — ✓', 'filho': filho.stdout.strip(),\n"
            "            'codigo_filho': filho.returncode}\n", encoding="utf-8")
        (self.root / "registry" / "components" / "acentos.json").write_text(json.dumps({
            "schema_version": "fundacao.component/1", "component_id": "acentos", "version": "0.1.0",
            "kind": "tool", "enabled": True, "entrypoint": "fundacao.components.acentos:run",
            "allowed_projects": ["juridico-lab"], "permissions": [], "timeout_seconds": 30}), encoding="utf-8")
        with mock.patch.dict(os.environ):
            os.environ.pop("PYTHONUTF8", None)
            os.environ.pop("PYTHONIOENCODING", None)
            res = components.dispatch(self.root, self.con, self.jur, "juridico-lab", "acentos", {})["result"]
        self.assertEqual(res["direto"], "Pendências: competência — ✓")
        self.assertEqual((res["codigo_filho"], res["filho"]), (0, "Petição — ação nº 1 ✓"))

    def test_ambiente_minimo_tem_perfil_mas_nao_segredos(self):
        mod = self.root / "fundacao" / "components" / "ambiente.py"
        mod.write_text("import os\n"
                       "def run(request):\n"
                       "    return {k: (k in os.environ) for k in ('USERNAME', 'USERPROFILE', 'CHAVE_SECRETA_FIC')}\n",
                       encoding="utf-8")
        (self.root / "registry" / "components" / "ambiente.json").write_text(json.dumps({
            "schema_version": "fundacao.component/1", "component_id": "ambiente", "version": "0.1.0",
            "kind": "tool", "enabled": True, "entrypoint": "fundacao.components.ambiente:run",
            "allowed_projects": ["juridico-lab"], "permissions": [], "timeout_seconds": 30}), encoding="utf-8")
        with mock.patch.dict(os.environ, {"USERNAME": "fic", "USERPROFILE": str(self.root),
                                          "CHAVE_SECRETA_FIC": "nao-repassar"}):
            res = components.dispatch(self.root, self.con, self.jur, "juridico-lab", "ambiente", {})["result"]
        self.assertEqual(res, {"USERNAME": True, "USERPROFILE": True, "CHAVE_SECRETA_FIC": False})

    def test_descoberta_nao_importa_nem_executa(self):
        self._bomba()
        inventario = {c["component_id"]: c for c in components.discover(self.root)}
        self.assertIn("bomba", inventario)
        self.assertFalse(inventario["source_manifest"]["enabled"])
        self.assertEqual(components.dispatch_count(self.con, "bomba"), 0)

    def test_desabilitado_nega_antes_do_ponto_de_entrada(self):
        with self.assertRaises(ComponentDisabled):
            components.dispatch(self.root, self.con, self.jur, "juridico-lab", "source_manifest",
                                {"document_ids": ["doc-aurora-01"]})
        self.assertEqual(components.dispatch_count(self.con, "source_manifest", "executed"), 0)
        self.assertEqual(components.dispatch_count(self.con, "source_manifest", "denied_disabled"), 1)

    def test_mesma_interface_nos_dois_projetos_sem_mistura(self):
        components.set_enabled(self.root, self.con, self.admin, "source_manifest", True)
        a = components.dispatch(self.root, self.con, self.jur, "juridico-lab", "source_manifest",
                                {"document_ids": ["doc-aurora-01", "doc-fuga", "doc-caixasim-01"]})
        b = components.dispatch(self.root, self.con, self.eng, "reversa-lab", "source_manifest",
                                {"document_ids": ["doc-caixasim-01", "doc-aurora-01"]})
        self.assertEqual([f["document_id"] for f in a["result"]["files"]], ["doc-aurora-01"])
        erros_a = {e["document_id"]: e["error"] for e in a["result"]["errors"]}
        self.assertEqual(erros_a, {"doc-fuga": "E_PATH_ESCAPE", "doc-caixasim-01": "E_NOT_IN_CATALOG"})
        self.assertEqual([f["document_id"] for f in b["result"]["files"]], ["doc-caixasim-01"])
        self.assertNotIn(CANARIOS["juridico-lab"], json.dumps(b))
        self.assertEqual(set(a["result"]), set(b["result"]))  # mesmo contrato

    def test_identidade_sem_acesso_nao_executa(self):
        components.set_enabled(self.root, self.con, self.admin, "source_manifest", True)
        with self.assertRaises(AccessDenied):
            components.dispatch(self.root, self.con, self.eng, "juridico-lab", "source_manifest",
                                {"document_ids": ["doc-aurora-01"]})
        self.assertEqual(components.dispatch_count(self.con, "source_manifest", "executed"), 0)

    def test_dependencia_ausente_fica_bloqueada(self):
        reg = self.root / "registry" / "components" / "source_manifest.json"
        entry = json.loads(reg.read_text(encoding="utf-8"))
        entry.update(enabled=True, requires_modules=["modulo_inexistente_xyz"])
        reg.write_text(json.dumps(entry), encoding="utf-8")
        inv = {c["component_id"]: c for c in components.discover(self.root)}
        self.assertEqual(inv["source_manifest"]["health"], "dependencia_ausente")
        with self.assertRaises(DependencyUnavailable):
            components.dispatch(self.root, self.con, self.jur, "juridico-lab", "source_manifest",
                                {"document_ids": ["doc-aurora-01"]})

    def test_timeout_real_em_subprocesso(self):
        mod = self.root / "fundacao" / "components" / "lento.py"
        mod.write_text("import time\ndef run(req):\n    time.sleep(5)\n    return {}\n", encoding="utf-8")
        (self.root / "registry" / "components" / "lento.json").write_text(json.dumps({
            "schema_version": "fundacao.component/1", "component_id": "lento", "version": "0.1.0",
            "kind": "tool", "enabled": True, "entrypoint": "fundacao.components.lento:run",
            "allowed_projects": ["juridico-lab"], "permissions": [], "timeout_seconds": 1}), encoding="utf-8")
        with self.assertRaises(FundacaoError) as ctx:
            components.dispatch(self.root, self.con, self.jur, "juridico-lab", "lento", {})
        self.assertIn("tempo limite", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
