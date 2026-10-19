"""CLI: operações que copiam dados de todos os projetos exigem identidade autorizada."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest

from helpers import CANARIOS, FoundationTestCase


class TestCliAutorizacao(FoundationTestCase):
    def _cli(self, principal: str | None, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "FUNDACAO_PRINCIPAL"}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if principal:
            env["FUNDACAO_PRINCIPAL"] = principal
        return subprocess.run([sys.executable, "-m", "fundacao", "--raiz", str(self.root), *args],
                              capture_output=True, text=True, encoding="utf-8", cwd=str(self.root), env=env)

    def test_backup_exige_administrador(self):
        self.write_data("juridico-lab", "segredo.md", CANARIOS["juridico-lab"])
        destino = self.root.parent / (self.root.name + "-backup")
        try:
            for quem in ("operador-engenharia", "revisor-juridico", None):
                p = self._cli(quem, "backup", "criar", "--destino", str(destino))
                self.assertEqual(p.returncode, 2, (quem, p.stdout))
                self.assertFalse(destino.exists(), quem)
                self.assertNotIn(CANARIOS["juridico-lab"], p.stdout + p.stderr)
            negativas = self.con.execute(
                "SELECT COUNT(*) FROM event WHERE kind='access_denied' AND subject='operador-engenharia'").fetchone()[0]
            self.assertGreaterEqual(negativas, 1)
            p = self._cli("operador-lab", "backup", "criar", "--destino", str(destino), "--rotulo", "teste")
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertTrue((destino / "manifest.json").exists())
        finally:
            shutil.rmtree(destino, ignore_errors=True)

    def test_exportar_eventos_exige_auditoria_da_fundacao(self):
        destino = self.root / "evidence" / "eventos.jsonl"
        p = self._cli("operador-engenharia", "eventos", "exportar", "--destino", str(destino))
        self.assertEqual(p.returncode, 2)
        self.assertIn("E_ACCESS_DENIED", p.stderr)
        self.assertFalse(destino.exists())
        p = self._cli("operador-engenharia", "eventos", "verificar")
        self.assertEqual(p.returncode, 0, p.stderr)
        p = self._cli("operador-lab", "eventos", "exportar", "--destino", str(destino))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(destino.exists())


    def test_status_e_listagem_mostram_so_projetos_autorizados(self):
        from fundacao.core.tasks import Coordinator
        Coordinator(self.root, self.con, self.jur, "juridico-lab").create_task("tarefa jurídica (fictícia)")
        reg = self.root / "registry" / "components" / "source_manifest.json"
        entrada = json.loads(reg.read_text(encoding="utf-8"))
        entrada["allowed_projects"] = ["juridico-lab"]
        reg.write_text(json.dumps(entrada), encoding="utf-8")
        st = json.loads(self._cli("operador-engenharia", "status").stdout)
        self.assertEqual((st["projetos_autorizados"], st["tarefas_por_estado"]), (["reversa-lab"], {}))
        self.assertNotIn("juridico-lab", json.dumps(st))
        self.assertEqual(self._cli(None, "componente", "listar").returncode, 2)
        self.assertNotIn("juridico-lab", self._cli("operador-engenharia", "componente", "listar").stdout)
        adm = json.loads(self._cli("operador-lab", "status").stdout)
        self.assertEqual(adm["tarefas_por_estado"], {"pending": 1})

    def test_restauracao_nao_liberada_sai_com_codigo_3(self):
        ref = self.root.parent / (self.root.name + "-ref")
        novo = self.root.parent / (self.root.name + "-restaurado")
        try:
            self.assertEqual(self._cli("operador-lab", "backup", "criar", "--destino", str(ref)).returncode, 0)
            p = self._cli("operador-lab", "backup", "restaurar", "--origem", str(ref), "--destino", str(novo))
            self.assertEqual(p.returncode, 3, p.stderr)
            self.assertIs(json.loads(p.stdout)["released"], False)
        finally:
            shutil.rmtree(ref, ignore_errors=True)
            shutil.rmtree(novo, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
