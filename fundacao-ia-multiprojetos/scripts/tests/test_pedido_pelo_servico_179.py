"""1.7.9: a regra 2 da SKILL.md manda pedir o conteúdo de outro projeto pelo serviço, mesmo esperando recusa. O meio
tem de existir na CLI do kit, que é o que o agente consulta: sem ele, a regra não se cumpre e nenhuma negativa fica na
trilha. Os testes de comportamento do comando estão no kit (`tests/test_cli_conhecimento.py`)."""

from __future__ import annotations

import subprocess
import sys
import unittest

from apoio import ENV, KIT, SKILL


class TestPedidoPeloServico(unittest.TestCase):
    def test_regra_2_aponta_o_comando_do_servico(self):
        corpo = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        regra2 = " ".join(corpo.split("2. **Autorização fora do modelo.**", 1)[1].split("\n3. ", 1)[0].split())
        self.assertIn("Peça o conteúdo pelo serviço (`python -m fundacao conhecimento listar|buscar --projeto <p>`) "
                      "com a identidade autenticada, mesmo esperando recusa.", regra2)

    def test_cli_do_kit_oferece_o_comando(self):
        for acao in ("listar", "buscar"):
            with self.subTest(acao=acao):
                p = subprocess.run([sys.executable, "-B", "-m", "fundacao", "conhecimento", acao, "--help"],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV,
                                   cwd=str(KIT), timeout=60)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn("--projeto", p.stdout)
        p = subprocess.run([sys.executable, "-B", "-m", "fundacao", "--help"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=ENV, cwd=str(KIT), timeout=60)
        self.assertIn("conhecimento", p.stdout)


if __name__ == "__main__":
    unittest.main()
