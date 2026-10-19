"""Auditoria externa da 1.3.4 — `matriz.py` (F16): esquema válido não é evidência examinada."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from apoio import SKILL, rodar_script

MODELO = SKILL / "assets" / "templates" / "MATRIZ-REQUISITOS.csv"


class TestF16Matriz(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="matriz-teste-"))
        (self.base / "registry").mkdir()
        self.mat = self.base / "registry" / "requisitos.csv"
        shutil.copyfile(MODELO, self.mat)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def editar(self, rid: str, **campos):
        with self.mat.open(encoding="utf-8", newline="") as fh:
            linhas = list(csv.DictReader(fh))
        nomes = list(linhas[0].keys()) + [k for k in campos if k not in linhas[0]]
        for r in linhas:
            if r["id"] == rid:
                r.update(campos)
        with self.mat.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=nomes, lineterminator="\n")
            w.writeheader()
            w.writerows(linhas)

    def validar(self):
        p = rodar_script("matriz.py", "validar", "--matriz", self.mat)
        return p, json.loads(p.stdout)

    def test_f16_evidencia_inexistente_e_simulacao_vazia_falham_com_mensagem_especifica(self):
        self.editar("R12", estado="implementado_ativo", nivel_evidencia="validado", simulado="",
                    versao_avaliada="versao-nao-verificada", caminho_evidencia="evidence/nao-existe.json")
        p, dados = self.validar()
        self.assertEqual(p.returncode, 1, "linha ativa sem evidência verificável foi aceita")
        erros = " | ".join(dados["erros"])
        self.assertIn("R12", erros)
        self.assertIn("simulado", erros)
        self.assertIn("evidência", erros)

    def test_f16_saida_distingue_esquema_de_evidencia_examinada(self):
        p, dados = self.validar()
        self.assertEqual(p.returncode, 0, dados)
        self.assertIs(dados.get("schema_ok"), True, "a saída não distingue o esquema da evidência")
        self.assertEqual(dados.get("evidencias", {}).get("examinadas"), 0)
        self.assertIn("alcance", dados)

    def test_f16_evidencia_que_existe_e_cita_a_versao_e_examinada(self):
        ev = self.base / "evidence" / "R12.md"
        ev.parent.mkdir()
        ev.write_text("Execução de ensaio do kit 1.4.0: teto por rota conferido (fictício).", encoding="utf-8")
        self.editar("R12", estado="implementado_ativo", nivel_evidencia="executado", simulado="nao",
                    versao_avaliada="kit 1.4.0", caminho_evidencia="evidence/R12.md")
        p, dados = self.validar()
        self.assertEqual(p.returncode, 0, dados)
        self.assertEqual(dados.get("evidencias", {}).get("examinadas"), 1, "evidência não examinada")
        self.assertEqual(dados.get("evidencias", {}).get("conferidas"), ["R12"])

    def test_f16_evidencia_que_nao_cita_a_versao_avaliada_falha(self):
        ev = self.base / "evidence" / "R12.md"
        ev.parent.mkdir()
        ev.write_text("Execução de ensaio sem identificação de versão.", encoding="utf-8")
        self.editar("R12", estado="implementado_ativo", nivel_evidencia="executado", simulado="nao",
                    versao_avaliada="kit 1.4.0", caminho_evidencia="evidence/R12.md")
        p, dados = self.validar()
        self.assertEqual(p.returncode, 1)
        self.assertTrue(any("R12" in e and "versão" in e for e in dados["erros"]), dados["erros"])

    def test_f16_hash_registrado_que_nao_confere_falha(self):
        ev = self.base / "evidence" / "R12.md"
        ev.parent.mkdir()
        ev.write_text("kit 1.4.0: ensaio fictício.", encoding="utf-8")
        self.editar("R12", estado="implementado_ativo", nivel_evidencia="executado", simulado="nao",
                    versao_avaliada="kit 1.4.0", caminho_evidencia="evidence/R12.md",
                    sha256_evidencia=hashlib.sha256(b"outro conteudo").hexdigest())
        p, dados = self.validar()
        self.assertEqual(p.returncode, 1)
        self.assertTrue(any("R12" in e and "sha256" in e for e in dados["erros"]), dados["erros"])


if __name__ == "__main__":
    unittest.main()
