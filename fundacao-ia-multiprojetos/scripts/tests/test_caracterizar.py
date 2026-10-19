"""Auditoria externa da 1.3.4 — `caracterizar.py` (F13): comparação integral e efeitos isolados por caso."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import rodar_script


class TestF13Caracterizacao(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="caracterizar-teste-"))
        self.proj = self.base / "projeto"
        (self.proj / "entradas").mkdir(parents=True)
        (self.proj / "entradas" / "um.json").write_text("{}", encoding="utf-8")
        self.antigo, self.novo = self.proj / "antigo.py", self.proj / "novo.py"
        self.golden = self.base / "golden.json"

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def gravar(self, *extra):
        return rodar_script("caracterizar.py", "gravar", "--entradas", self.proj / "entradas" / "*.json",
                            "--saida", self.golden, *extra, "--", sys.executable, self.antigo, "{entrada}")

    def comparar(self, *extra):
        p = rodar_script("caracterizar.py", "comparar", "--golden", self.golden, *extra,
                         "--", sys.executable, self.novo, "{entrada}")
        return p, (json.loads(p.stdout) if p.stdout.strip().startswith("{") else None)

    def test_f13_mudanca_depois_de_20000_caracteres_e_detectada(self):
        self.antigo.write_text("print('A' * 20000 + 'ANTIGO')\n", encoding="utf-8")
        self.novo.write_text("print('A' * 20000 + 'REGRESSAO')\n", encoding="utf-8")
        self.assertEqual(self.gravar().returncode, 0)
        p, dados = self.comparar()
        self.assertNotEqual(p.returncode, 0, "mudança na saída integral passou como equivalente")
        self.assertTrue(dados and dados["divergencias"])
        self.assertIn("stdout", dados["divergencias"][0]["campos_divergentes"])

    def test_f13_arquivo_que_deixa_de_ser_produzido_e_detectado(self):
        saida = self.proj / "saidas"
        saida.mkdir()
        self.antigo.write_text("from pathlib import Path\nPath('saidas/resultado.txt').write_text('esperado')\n",
                               encoding="utf-8")
        self.novo.write_text("pass\n", encoding="utf-8")
        self.assertEqual(self.gravar("--cwd", self.proj, "--pasta-saida", saida).returncode, 0)
        p, dados = self.comparar("--cwd", self.proj, "--pasta-saida", saida)
        self.assertTrue((saida / "resultado.txt").exists(), "o arquivo antigo ficou (e não pode mascarar a falta)")
        self.assertNotEqual(p.returncode, 0, "o programa parou de produzir o arquivo e a comparação não viu")
        self.assertTrue(dados and dados["divergencias"])

    def test_f13_saida_integral_igual_continua_equivalente(self):
        texto = "print('B' * 30000 + 'IGUAL')\n"
        self.antigo.write_text(texto, encoding="utf-8")
        self.novo.write_text(texto, encoding="utf-8")
        self.assertEqual(self.gravar().returncode, 0)
        p, dados = self.comparar()
        self.assertEqual(p.returncode, 0, p.stdout[-400:])
        self.assertEqual(dados["divergencias"], [])

    def test_f13_pasta_de_ensaio_isolada_por_caso(self):
        ensaio = self.base / "ensaio-novo"
        programa = "import sys, pathlib\npathlib.Path(sys.argv[2], 'saida.txt').write_text('ok:' + pathlib.Path(sys.argv[1]).name)\n"
        self.antigo.write_text(programa, encoding="utf-8")
        self.novo.write_text(programa, encoding="utf-8")
        g = rodar_script("caracterizar.py", "gravar", "--entradas", self.proj / "entradas" / "*.json", "--saida",
                         self.golden, "--ensaio", ensaio, "--", sys.executable, self.antigo, "{entrada}", "{ensaio}")
        self.assertEqual(g.returncode, 0, g.stderr[-400:])
        p = rodar_script("caracterizar.py", "comparar", "--golden", self.golden, "--ensaio", ensaio,
                         "--", sys.executable, self.novo, "{entrada}", "{ensaio}")
        self.assertEqual(p.returncode, 0, p.stdout[-400:] + p.stderr[-400:])

    def test_f13_nao_limpa_pasta_do_usuario_sem_marca_de_ensaio(self):
        pasta_usuario = self.base / "pasta-do-usuario"
        pasta_usuario.mkdir()
        (pasta_usuario / "importante.txt").write_text("não apagar", encoding="utf-8")
        self.antigo.write_text("print('x')\n", encoding="utf-8")
        p = rodar_script("caracterizar.py", "gravar", "--entradas", self.proj / "entradas" / "*.json", "--saida",
                         self.golden, "--ensaio", pasta_usuario, "--", sys.executable, self.antigo, "{entrada}")
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual((pasta_usuario / "importante.txt").read_text(encoding="utf-8"), "não apagar")


if __name__ == "__main__":
    unittest.main()
