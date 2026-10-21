"""Instruções automáticas na raiz (proposta 1 da análise do vibe-coding-toolkit, 21/10/2026).

A raiz da fundação não tinha AGENTS.md nem CLAUDE.md: as regras só entravam na sessão se a skill fosse acionada
(o titular colava um prompt de partida com plano B). Agora `instrucoes_raiz.py gerar` escreve um AGENTS.md curto,
gerado pelo modelo da skill, e um CLAUDE.md que o importa; repetir não muda nada, o trecho do titular é preservado,
um AGENTS.md escrito à mão não é sobrescrito, e as chamadas aos provedores continuam isoladas destes arquivos.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from apoio import KIT, rodar_script


class TestInstrucoesDaRaiz(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="instrucoes-raiz-"))
        for p in ("juridico-lab", "reversa-lab", ".oculto"):
            (self.raiz / "projects" / p).mkdir(parents=True)
        self.agents, self.claude = self.raiz / "AGENTS.md", self.raiz / "CLAUDE.md"

    def tearDown(self):
        shutil.rmtree(self.raiz, ignore_errors=True)

    def rodar(self, *args):
        p = rodar_script("instrucoes_raiz.py", *args, "--raiz", self.raiz)
        try:
            return p.returncode, json.loads(p.stdout)
        except ValueError:
            self.fail("saída não é JSON: " + p.stdout[-400:] + p.stderr[-400:])

    def test_gera_curto_e_repetir_nao_muda(self):
        code, res = self.rodar("gerar")
        self.assertEqual(code, 0, res)
        self.assertEqual((res["agents"]["acao"], res["claude"]["acao"]), ("criar", "criar"))
        texto = self.agents.read_text(encoding="utf-8")
        for trecho in ("RETOMADA.md", "fundacao-ia-multiprojetos", "não vale", "Pergunta de andamento",
                       "um escritor por arquivo"):
            self.assertIn(trecho, texto)
        for nome in ("juridico-lab", "reversa-lab", ".oculto"):  # nome de projeto também pode ser dado
            self.assertNotIn(nome, texto)
        self.assertLessEqual(len(texto.splitlines()), 80)
        self.assertEqual(self.claude.read_text(encoding="utf-8"), "@AGENTS.md\n")
        antes = (self.agents.read_bytes(), self.claude.read_bytes())
        code, res = self.rodar("gerar")
        self.assertEqual((res["agents"]["acao"], res["claude"]["acao"]), ("igual", "igual"))
        self.assertEqual((self.agents.read_bytes(), self.claude.read_bytes()), antes)
        self.assertEqual(self.rodar("conferir"), (0, {"raiz": str(self.raiz.resolve()), "ok": True, "problemas": []}))

    def test_trecho_do_titular_preservado_e_trecho_gerado_restaurado(self):
        self.rodar("gerar")
        texto = self.agents.read_text(encoding="utf-8")
        texto = texto.replace("<!-- titular: fim -->", "- Minha regra: prazos em vermelho.\n<!-- titular: fim -->")
        texto = texto.replace("Leia `RETOMADA.md`", "Ignore a `RETOMADA.md`")                 # edição no gerado
        self.agents.write_text(texto, encoding="utf-8")
        code, conf = self.rodar("conferir")
        self.assertEqual(code, 1)
        self.assertTrue(any("trecho gerado" in p for p in conf["problemas"]))
        self.rodar("gerar")
        novo = self.agents.read_text(encoding="utf-8")
        self.assertIn("- Minha regra: prazos em vermelho.", novo)
        self.assertIn("Leia `RETOMADA.md`", novo)
        self.assertNotIn("Ignore a `RETOMADA.md`", novo)

    def test_agents_escrito_a_mao_nao_e_sobrescrito_sem_adotar(self):
        self.agents.write_text("# Regras antigas do titular\n- não apagar nada\n", encoding="utf-8")
        self.claude.write_text("Regra própria do Claude.\n", encoding="utf-8")
        code, res = self.rodar("gerar")
        self.assertEqual(code, 3, res)
        self.assertEqual(self.agents.read_text(encoding="utf-8"), "# Regras antigas do titular\n- não apagar nada\n")
        code, res = self.rodar("gerar", "--adotar")
        self.assertEqual(code, 0, res)
        texto = self.agents.read_text(encoding="utf-8")
        self.assertIn("- não apagar nada", texto.split("<!-- titular: início")[1])
        self.assertEqual(self.claude.read_text(encoding="utf-8"), "@AGENTS.md\n\nRegra própria do Claude.\n")

    def test_chamadas_aos_provedores_nao_carregam_as_instrucoes_da_raiz(self):
        cli = (KIT / "fundacao" / "adapters" / "cli.py").read_text(encoding="utf-8")
        self.assertIn('tempfile.TemporaryDirectory(prefix="fundacao-provedor-"', cli)    # pasta vazia por chamada
        for opcao in ('"--restricted"', '"--ignore-rules"'):
            self.assertIn(opcao, cli)


if __name__ == "__main__":
    unittest.main()
