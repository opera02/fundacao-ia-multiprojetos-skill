"""CI pública (proposta 6 da análise do vibe-coding-toolkit, 21/10/2026): o workflow da cópia pública roda as cinco
verificações nas duas plataformas, cinco rodadas em cada (R58, R59), com as ações fixadas por SHA de commit, permissão
só de leitura, nenhum segredo e sem credencial guardada no clone. Lê o arquivo como texto (a biblioteca padrão não
tem YAML)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
WORKFLOW = RAIZ / ".github" / "workflows" / "validar.yml"


class TestCIPublica(unittest.TestCase):
    def setUp(self):
        self.texto = WORKFLOW.read_text(encoding="utf-8")

    def test_acoes_fixadas_por_sha_com_a_versao_anotada(self):
        usos = re.findall(r"^\s*-?\s*uses:\s*(\S+)(.*)$", self.texto, re.M)
        self.assertEqual(sorted(u.split("@")[0] for u, _ in usos), ["actions/checkout", "actions/setup-python"])
        for uso, resto in usos:
            self.assertRegex(uso, r"@[0-9a-f]{40}$")
            self.assertRegex(resto, r"#\s*v\d+\.\d+\.\d+")

    def test_so_leitura_sem_segredo_e_sem_credencial_guardada(self):
        self.assertRegex(self.texto, r"(?m)^permissions:\s*\n\s+contents:\s*read\s*$")
        self.assertIn("persist-credentials: false", self.texto)
        for proibido in ("secrets.", "pull_request_target", "write-all", ": write"):
            self.assertNotIn(proibido, self.texto)

    def test_duas_plataformas_cinco_rodadas_python_3_12(self):
        self.assertRegex(self.texto, r"os:\s*\[windows-latest,\s*ubuntu-latest\]")
        self.assertRegex(self.texto, r"rodada:\s*\[1,\s*2,\s*3,\s*4,\s*5\]")
        self.assertIn('python-version: "3.12"', self.texto)
        self.assertIn("fail-fast: false", self.texto)

    def test_as_cinco_verificacoes(self):
        for trecho in ("working-directory: fundacao-ia-multiprojetos/assets/fundacao-kit",
                       "python -B -m unittest discover -s tests",
                       "python -B -m unittest discover -s scripts/tests",
                       "python -B -m unittest discover -s entrega/testes",
                       "scripts/verificar_referencias.py --raiz fundacao-ia-multiprojetos",
                       "evals/cenarios/run_cenarios.py --saida"):
            self.assertIn(trecho, self.texto)


if __name__ == "__main__":
    unittest.main()
