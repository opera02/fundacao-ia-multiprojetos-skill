"""Sentinela da CI (1.7.10; crítica do desenho): teste pulado passa verde. No Ubuntu da CI, os testes que precisam
do bubblewrap e do socat (a caixa da execução isolada, o perfil de execução e o que a 1.7.10 acrescenta) não podem ser
pulados em silêncio. Com FUNDACAO_CI_EXIGE_BWRAP=1 (o `validar.yml` liga só no Ubuntu), este teste exige os dois
programas e uma caixa que abre de verdade; fora da CI, é pulado."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest

EXIGE = os.environ.get("FUNDACAO_CI_EXIGE_BWRAP") == "1"


@unittest.skipUnless(EXIGE, "só no Ubuntu da CI (FUNDACAO_CI_EXIGE_BWRAP=1)")
class TestSentinelaDaCaixa(unittest.TestCase):
    def test_bubblewrap_e_socat_presentes(self):
        self.assertTrue(sys.platform.startswith("linux"), sys.platform)
        for programa in ("bwrap", "socat"):
            self.assertIsNotNone(shutil.which(programa), f"{programa} ausente: os testes da caixa seriam pulados")

    def test_a_caixa_abre(self):
        r = subprocess.run(["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "true"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, f"a caixa do bubblewrap não abriu: {r.stderr.strip()}")


if __name__ == "__main__":
    unittest.main()
