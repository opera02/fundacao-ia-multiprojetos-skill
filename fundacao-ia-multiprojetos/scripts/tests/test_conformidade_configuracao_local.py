"""A suíte de conformidade de uma fundação implantada não acusa, para sempre, uma configuração local aprovada
(1.5.0; implantação real de 2026-10-20: `test_politica_distribuida_mantem_sigiloso_so_local` falhava em toda
execução depois da DECISAO-003, que mudou `task_routes.sigiloso` da raiz). A política distribuída continua
conferida no kit da skill; na raiz implantada, o `instalar_kit.py` lista a configuração preservada."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import ENV, rodar_script


class TestConformidadeComConfiguracaoLocal(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="conformidade-local-"))
        self.raiz = self.tmp / "raiz"
        r = rodar_script("instalar_kit.py", "--destino", self.raiz)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rota_sigilosa_alterada_por_decisao_nao_reprova_a_suite_da_raiz(self):
        politica = self.raiz / "registry" / "route_policy.json"
        p = json.loads(politica.read_text(encoding="utf-8"))
        p["task_routes"]["sigiloso"] = ["cli_assinatura", "local"]  # como a DECISAO-003 da fundação real
        politica.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
        r = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p",
                            "test_eventos_rotas.py"], cwd=str(self.raiz), env=ENV, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertIn("skipped=", r.stderr)  # a conferência da política distribuída é pulada, com o motivo

    def test_politica_de_backup_local_nao_reprova_a_suite_da_raiz(self):
        """1.5.1: o ensaio da atualização da fundação real recusou o kit 1.5.0 porque test_backup_completo lia o
        registry/backup_policy.json da raiz implantada em vez de conferir a política padrão."""
        (self.raiz / "registry" / "backup_policy.json").write_text(json.dumps(
            {"schema_version": "fundacao.backup_policy/1", "incluir": ["docs", "plugins", ".claude/hooks"]}),
            encoding="utf-8")
        r = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p",
                            "test_backup_completo.py"], cwd=str(self.raiz), env=ENV, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])


if __name__ == "__main__":
    unittest.main()
