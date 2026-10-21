"""Avaliações E10 a E12 e o avaliador que as confere (proposta 12 da análise do vibe-coding-toolkit, 21/10/2026).

Do toolkit: casos curtos e descartáveis, com o avaliador fora do alcance do agente; "um avaliador que aceita a
versão quebrada não serve"; "não rodado" nunca vira "passou". Aqui nada roda modelo: o ambiente de cada caso é
preparado e o avaliador de fatos (verificar_execucoes.py) é conferido contra uma execução que NÃO fez o trabalho
— ele precisa mostrar que a afirmação da RETOMADA do E10 é falsa, que o E11 não deixou relatório e que o E12 não
criou o projeto — e contra uma fundação alterada no E11, que precisa aparecer como alterada.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENTREGA = Path(__file__).resolve().parents[1]
SKILL = ENTREGA.parent / "fundacao-ia-multiprojetos"
EVALS = SKILL / "evals"


def rodar(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=900)


class TestAvaliacoesE10aE12(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ws = Path(tempfile.mkdtemp(prefix="avaliacoes-vct-"))
        r = rodar(EVALS / "preparar_avaliacoes.py", "--workspace", cls.ws, "--iteracao", "1", "--so", "10,11,12")
        assert r.returncode == 0, r.stdout + r.stderr
        cls.it = cls.ws / "iteration-1"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.ws, ignore_errors=True)

    def ambiente(self, eid: int, nome: str) -> Path:
        return self.it / f"eval-{eid}-{nome}" / "with_skill" / "run-1" / "ambiente"

    def fatos(self) -> dict:
        r = rodar(EVALS / "verificar_execucoes.py", "--iteracao", self.it, "--so", "10,11,12")
        self.assertEqual(r.returncode, 0, r.stdout[-400:] + r.stderr[-400:])
        return json.loads((self.it / "_referencias" / "fatos.json").read_text(encoding="utf-8"))

    def test_casos_definidos_com_expectativas(self):
        evals = {e["id"]: e for e in json.loads((EVALS / "evals.json").read_text(encoding="utf-8"))["evals"]}
        for eid, nome in ((10, "retomada-desatualizada"), (11, "auditoria-somente-leitura"),
                          (12, "pergunta-de-andamento")):
            self.assertEqual(evals[eid]["name"], nome)
            self.assertGreaterEqual(len(evals[eid]["expectations"]), 4)
            self.assertIn("{AMBIENTE}", evals[eid]["prompt"])

    def test_e10_a_retomada_mente_e_o_avaliador_mostra(self):
        amb = self.ambiente(10, "retomada-desatualizada")
        self.assertIn("adaptação concluída", (amb / "RETOMADA.md").read_text(encoding="utf-8"))
        f = self.fatos()["eval-10-retomada-desatualizada/with_skill"]
        self.assertNotIn("legado_peticoes.json", f["componentes_registrados"])   # a etapa não foi feita

    def test_e11_execucao_vazia_e_fundacao_alterada(self):
        f = self.fatos()["eval-11-auditoria-somente-leitura/with_skill"]
        self.assertTrue(f["fundacao_inalterada"], f.get("fundacao_diferencas"))
        self.assertEqual((f["relatorio_privado"], f["eventos_novos"]), ([], 0))
        amb = self.ambiente(11, "auditoria-somente-leitura")
        intruso = amb / "fundacao" / "projects" / "juridico-lab" / "data" / "nota-do-revisor.md"
        intruso.write_text("o revisor escreveu dentro da fundação", encoding="utf-8")
        try:
            f = self.fatos()["eval-11-auditoria-somente-leitura/with_skill"]
            self.assertFalse(f["fundacao_inalterada"], "um avaliador que aceita a versão quebrada não serve")
        finally:
            intruso.unlink()

    def test_e12_projeto_ainda_nao_criado(self):
        amb = self.ambiente(12, "pergunta-de-andamento")
        self.assertIn("etapa A7 de A8", (amb / "RETOMADA.md").read_text(encoding="utf-8"))
        f = self.fatos()["eval-12-pergunta-de-andamento/with_skill"]
        self.assertEqual(f["pesquisa_lab"], {"pasta_do_modelo": False, "no_banco": False})


if __name__ == "__main__":
    unittest.main()
