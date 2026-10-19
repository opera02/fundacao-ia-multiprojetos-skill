"""Auditoria externa da 1.3.4 — `manifesto.py` (F14): a política de exclusões acompanha o manifesto."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from apoio import rodar_script


class TestF14Manifesto(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="manifesto-teste-"))
        self.raiz = self.base / "projeto"
        self.raiz.mkdir()
        (self.raiz / "a.txt").write_text("inalterado", encoding="utf-8")
        (self.raiz / "rascunho.tmp").write_text("excluído de propósito", encoding="utf-8")
        self.man = self.base / "manifesto.json"
        self.assertEqual(rodar_script("manifesto.py", "criar", "--raiz", self.raiz, "--saida", self.man,
                                      "--excluir", "*.tmp").returncode, 0)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def verificar(self, *extra):
        p = rodar_script("manifesto.py", "verificar", "--raiz", self.raiz, "--manifesto", self.man, *extra)
        return p, (json.loads(p.stdout) if p.stdout.strip().startswith("{") else None)

    def test_f14_arvore_inalterada_com_exclusao_personalizada_e_validada(self):
        p, dados = self.verificar()
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertEqual(dados["novos"], [], "o arquivo excluído na criação voltou como novo")

    def test_f14_mudanca_em_arquivo_incluido_continua_detectada(self):
        (self.raiz / "a.txt").write_text("alterado", encoding="utf-8")
        p, dados = self.verificar()
        self.assertEqual(p.returncode, 1)
        self.assertEqual(dados["alterados"], ["a.txt"])

    def test_f14_mudanca_de_politica_exige_opcao_explicita_e_aparece_separada(self):
        (self.raiz / "x.log").write_text("log", encoding="utf-8")
        sem, _ = self.verificar("--excluir", "*.log")
        self.assertNotEqual(sem.returncode, 0)
        com, dados = self.verificar("--excluir", "*.log", "--mudar-politica")
        self.assertEqual(com.returncode, 1, "mudança de política não é equivalência")
        self.assertTrue(dados and dados.get("politica", {}).get("mudou"))
        self.assertEqual(dados["novos"], [], "com a política nova, x.log fica excluído")

    def test_f14_manifesto_antigo_sem_politica_usa_os_excluidos_registrados(self):
        antigo = json.loads(self.man.read_text(encoding="utf-8"))
        antigo["schema_version"] = "fundacao.manifest/1"
        antigo.pop("politica", None)
        self.man.write_text(json.dumps(antigo), encoding="utf-8")
        p, dados = self.verificar()
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn("aviso", dados)


if __name__ == "__main__":
    unittest.main()
