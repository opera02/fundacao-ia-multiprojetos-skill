"""Cenário bloqueado por dependência opcional ausente (1.7.2). A primeira CI pública (1.7.1) mostrou que o CEN-10
(torch e transformers) e o CEN-15 (SDK mcp) dependem de pacotes que só existem no computador do titular: ali eles
rodam e precisam passar; num ambiente sem eles, o cenário fica BLOQUEADO — nunca PASSOU — e reprova a execução,
salvo com --opcionais-ausentes-bloqueiam, que só a CI pública usa (o bloqueio aparece no resultado)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
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


class TestCen11SemPyYaml(unittest.TestCase):
    """CI pública da 1.7.2: o CEN-11 lia o cabeçalho do SKILL.md com o PyYAML, que só existe no computador do
    titular, e saía FALHOU (ModuleNotFoundError) no Windows e no Ubuntu. Sem o PyYAML ele fica BLOQUEADO, e as
    verificações que não dependem dele rodam assim mesmo."""

    def test_sem_pyyaml_o_cen11_fica_bloqueado_e_confere_o_resto(self):
        rc = carregar()
        tinha, guardado = "yaml" in sys.modules, sys.modules.get("yaml")
        sys.modules["yaml"] = None  # `import yaml` falha e find_spec devolve None, como num Python sem o pacote
        try:
            with tempfile.TemporaryDirectory() as tmp:
                d = rc.cen11(Path(tmp)).as_dict()
        finally:
            if tinha:
                sys.modules["yaml"] = guardado
            else:
                del sys.modules["yaml"]
        self.assertEqual(rc.situacao(d), "BLOQUEADO", d)
        self.assertIn("PyYAML", d["bloqueado"])
        feitas = {v["verificacao"]: v["passou"] for v in d["verificacoes"]}
        self.assertTrue(feitas.get("um único SKILL.md no pacote"), feitas)
        self.assertTrue(feitas.get("SKILL.md enxuto (< 500 linhas)"), feitas)


class TestBloqueioNaoEscondeFalha(unittest.TestCase):
    """Revisão de segurança da 1.7.3 (VCT170-06): o CEN-11 é o primeiro cenário que bloqueia e segue verificando, e a
    opção da CI perdoava o cenário inteiro, inclusive uma verificação que rodou e falhou. O bloqueio perdoa só o que
    não rodou."""

    def setUp(self):
        self.rc = carregar()

    def test_bloqueado_com_verificacao_falha_reprova_mesmo_na_ci(self):
        c = self.rc.Cenario("CEN-XX", "parcial", "estrutural", "R35")
        c.bloquear("pacote opcional ausente")
        c.check("verificação que rodou", True, False, False)
        d = c.as_dict()
        self.assertEqual(self.rc.situacao(d), "FALHOU")
        self.assertEqual(self.rc.codigo_de_saida([d], opcionais_bloqueiam=True), 1)

    def test_cen11_sem_pyyaml_reprova_skill_aninhada_e_cabecalho_ausente(self):
        def aninhada(skill: Path) -> str:
            (skill / "assets" / "outra").mkdir(parents=True)
            (skill / "SKILL.md").write_text("---" + chr(10) + "name: x" + chr(10) + "---" + chr(10) + "# x" + chr(10),
                                            encoding="utf-8")
            (skill / "assets" / "outra" / "SKILL.md").write_text("# outra" + chr(10), encoding="utf-8")
            return "um único SKILL.md no pacote"

        def sem_cabecalho(skill: Path) -> str:
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("# Sem cabeçalho" + chr(10), encoding="utf-8")
            return "cabeçalho entre --- no início do SKILL.md"

        rc = self.rc
        for montar in (aninhada, sem_cabecalho):
            with self.subTest(caso=montar.__name__), tempfile.TemporaryDirectory() as tmp:
                skill = Path(tmp) / "skill"
                verificacao = montar(skill)
                original, rc.SKILL = rc.SKILL, skill
                tinha, guardado = "yaml" in sys.modules, sys.modules.get("yaml")
                sys.modules["yaml"] = None
                try:
                    d = rc.cen11(Path(tmp) / "trabalho").as_dict()
                finally:
                    rc.SKILL = original
                    if tinha:
                        sys.modules["yaml"] = guardado
                    else:
                        del sys.modules["yaml"]
                feitas = {v["verificacao"]: v["passou"] for v in d["verificacoes"]}
                self.assertIs(feitas.get(verificacao), False, feitas)
                self.assertEqual(rc.situacao(d), "FALHOU", d)
                self.assertEqual(rc.codigo_de_saida([d], opcionais_bloqueiam=True), 1)


if __name__ == "__main__":
    unittest.main()
