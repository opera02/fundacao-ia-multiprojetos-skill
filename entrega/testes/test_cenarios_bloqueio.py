"""Cenário bloqueado por dependência opcional ausente (1.7.2). A primeira CI pública (1.7.1) mostrou que o CEN-10
(torch e transformers) e o CEN-15 (SDK mcp) dependem de pacotes que só existem no computador do titular: ali eles
rodam e precisam passar; num ambiente sem eles, o cenário fica BLOQUEADO — nunca PASSOU — e reprova a execução,
salvo com --opcionais-ausentes-bloqueiam, que só a CI pública usa (o bloqueio aparece no resultado)."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[2] / "fundacao-ia-multiprojetos" / "evals" / "cenarios" / "run_cenarios.py"


def carregar():
    spec = importlib.util.spec_from_file_location("run_cenarios_bloqueio", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestCenarioBloqueado(unittest.TestCase):
    def setUp(self):
        self.rc = carregar()

    def test_bloqueado_nunca_passa_e_aparece_no_resultado(self):
        c = self.rc.Cenario("CEN-XX", "ensaio", "real-local", "R00")
        c.bloquear("pacote opcional ausente")
        d = c.as_dict()
        self.assertFalse(c.passou)
        self.assertEqual(d["bloqueado"], "pacote opcional ausente")
        self.assertEqual(self.rc.situacao(d), "BLOQUEADO")

    def test_bloqueio_reprova_salvo_na_ci(self):
        ok = self.rc.Cenario("CEN-01", "ok", "real-local", "R00")
        ok.check("verificação", True, True, True)
        bloqueado = self.rc.Cenario("CEN-10", "bloqueado", "real-local", "R26")
        bloqueado.bloquear("torch ausente")
        falhou = self.rc.Cenario("CEN-02", "falhou", "real-local", "R00")
        falhou.check("verificação", True, False, False)
        resultados = [ok.as_dict(), bloqueado.as_dict()]
        self.assertEqual(self.rc.codigo_de_saida(resultados, opcionais_bloqueiam=False), 1)
        self.assertEqual(self.rc.codigo_de_saida(resultados, opcionais_bloqueiam=True), 0)
        self.assertEqual(self.rc.codigo_de_saida(resultados + [falhou.as_dict()], opcionais_bloqueiam=True), 1)


if __name__ == "__main__":
    unittest.main()
