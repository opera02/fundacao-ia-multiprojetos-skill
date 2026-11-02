"""Item I13 da integração da 1.7.10: toda forma do comando do titular (core/aberturas_comando.comando_do_titular)
chama o Python com -I -B -S, para nenhum .pth de site-packages rodar antes da ferramenta (-I não implica -S). A
ferramenta (assets/host/fundacao_titular.py) só usa a biblioteca padrão; aqui ela roda de verdade com -I -B -S (o
`verificar-ficha` numa raiz fictícia, sem terminal) e responde em JSON, sem traceback, como com -I -B. Pasta
descartável; nada é assinado nem gravado."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import ENV, SKILL

FERRAMENTA = SKILL / "assets" / "host" / "fundacao_titular.py"


class TestFerramentaDoTitularSemSite(unittest.TestCase):
    def test_verificar_ficha_roda_com_menos_s_como_sem(self):
        base = Path(tempfile.mkdtemp(prefix="titular-sem-site-"))
        self.addCleanup(shutil.rmtree, base, True)
        for opcoes in (["-I", "-B", "-S"], ["-I", "-B"]):
            with self.subTest(opcoes=" ".join(opcoes)):
                p = subprocess.run([sys.executable, *opcoes, str(FERRAMENTA), "verificar-ficha", "--raiz", str(base),
                                    "--projeto", "proj-ficticio"], capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", env=ENV, timeout=120, stdin=subprocess.DEVNULL)
                self.assertNotIn("Traceback", p.stderr)
                self.assertEqual(p.returncode, 3, p.stdout + p.stderr)  # 3: a ficha que conta não vale (não há)
                r = json.loads(p.stdout)
                self.assertFalse(r["caixa_de_entrada"]["valida"])
                self.assertFalse(r["copia_da_ferramenta"]["protegida"])  # a da skill, fora da cópia protegida

    def test_menos_s_tira_o_modulo_site(self):
        p = subprocess.run([sys.executable, "-I", "-B", "-S", "-c", "import sys; print('site' in sys.modules)"],
                           capture_output=True, text=True, env=ENV, timeout=60)
        self.assertEqual(p.stdout.strip(), "False", p.stderr)


if __name__ == "__main__":
    unittest.main()
