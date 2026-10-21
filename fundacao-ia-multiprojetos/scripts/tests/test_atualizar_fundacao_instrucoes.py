"""Instruções da raiz na atualização da fundação (proposta 1 da análise do vibe-coding-toolkit, 21/10/2026).

`atualizar_fundacao.py aplicar` regenera o AGENTS.md e o CLAUDE.md da raiz depois da promoção, guardando antes os
que já existiam em registry/kit_backup/instrucoes-<carimbo>/, e a cópia DEPOIS os leva junto. O `desfazer` devolve
o anterior (ou apaga o que a atualização criou), salvo se o arquivo foi editado depois. Um AGENTS.md escrito à mão
não bloqueia a atualização: fica como está e o resumo pede a decisão do titular (`--adotar`).
Pastas descartáveis; identidade de ensaio; nada no perfil.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import ENV, SKILL, rodar_script, versao_do_kit

IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"
CLAUDE_DO_TITULAR = "Regra própria do titular para o Claude.\n"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class TestInstrucoesNaAtualizacao(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="atualizar-instrucoes-"))
        self.raiz, self.backups = self.tmp / "raiz", self.tmp / "backups"
        r = rodar_script("instalar_kit.py", "--destino", self.raiz)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = subprocess.run([sys.executable, "-B", "-m", "fundacao", "--raiz", str(self.raiz), "init", "--admin",
                            "titular-ensaio"], cwd=str(self.raiz), env=ENV, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.env = {**ENV, IDENTIDADE: "titular-ensaio"}
        self.agents, self.claude = self.raiz / "AGENTS.md", self.raiz / "CLAUDE.md"
        # A raiz finge estar num kit anterior (só a versão muda), para a atualização ter o que promover.
        init = self.raiz / "fundacao" / "__init__.py"
        atual = 'KIT_VERSION = "' + versao_do_kit(self.raiz) + '"'
        init.write_text(init.read_text(encoding="utf-8").replace(atual, 'KIT_VERSION = "1.0.0"'), encoding="utf-8")
        reg = self.raiz / "registry" / "kit_install.json"
        historico = json.loads(reg.read_text(encoding="utf-8"))
        for item in historico[-1]["copiados"]:
            if item["path"] == "fundacao/__init__.py":
                item["sha256"] = sha(init)
        reg.write_text(json.dumps(historico, ensure_ascii=False, indent=2), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def atualizar(self, *args) -> tuple:
        r = subprocess.run([sys.executable, "-B", str(SKILL / "scripts" / "atualizar_fundacao.py"), *map(str, args)],
                           env=self.env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=900)
        try:
            return r.returncode, json.loads(r.stdout)
        except ValueError:
            self.fail("saída não é JSON: " + r.stdout[-500:] + r.stderr[-500:])

    def aplicar(self) -> tuple:
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups,
                                   "--padrao-testes", "test_nenhum_*.py")
        self.assertEqual(code, 0, res)
        return res, json.loads(Path(res["registro"]).read_text(encoding="utf-8"))

    def test_gera_na_promocao_vai_na_copia_depois_e_desfazer_devolve(self):
        self.claude.write_text(CLAUDE_DO_TITULAR, encoding="utf-8")
        antes = sha(self.claude)
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(chk["instrucoes_raiz"], {"AGENTS.md": "criar", "CLAUDE.md": "atualizar"}, chk)
        self.assertFalse(self.agents.exists())                                  # checar só lê
        res, reg = self.aplicar()
        self.assertIn("<!-- fundacao: início", self.agents.read_text(encoding="utf-8"))
        self.assertEqual(self.claude.read_text(encoding="utf-8"), "@AGENTS.md\n\n" + CLAUDE_DO_TITULAR)
        instr = reg["instrucoes_raiz"]
        self.assertTrue(instr["gerado"], instr)
        self.assertEqual(instr["guardados"], [{"path": "CLAUDE.md", "sha256_anterior": antes}])
        self.assertTrue(any("AGENTS.md" in linha for linha in res["resumo"]), res["resumo"])
        manifesto = json.loads((Path(reg["depois"]["pasta"]) / "manifest.json").read_text(encoding="utf-8"))
        self.assertLessEqual({"AGENTS.md", "CLAUDE.md"}, {f["path"] for f in manifesto["files"]})
        code, des = self.atualizar("desfazer", "--registro", res["registro"])
        self.assertEqual(code, 0, des)
        self.assertFalse(self.agents.exists())                                  # criado pela atualização
        self.assertEqual(sha(self.claude), antes)                               # devolvido como era
        self.assertEqual(des["instrucoes"], {"devolvidas": ["CLAUDE.md"], "apagadas": ["AGENTS.md"], "mantidas": []})

    def test_editado_depois_da_atualizacao_fica_no_desfazer(self):
        res, _reg = self.aplicar()
        texto = self.agents.read_text(encoding="utf-8")
        self.agents.write_text(texto.replace("<!-- titular: fim -->", "- prazos em vermelho\n<!-- titular: fim -->"),
                               encoding="utf-8")
        code, des = self.atualizar("desfazer", "--registro", res["registro"])
        self.assertEqual(code, 0, des)
        self.assertIn("- prazos em vermelho", self.agents.read_text(encoding="utf-8"))
        self.assertEqual(des["instrucoes"], {"devolvidas": [], "apagadas": ["CLAUDE.md"], "mantidas": ["AGENTS.md"]})

    def test_agents_escrito_a_mao_nao_bloqueia_nem_e_alterado(self):
        self.agents.write_text("# Regras do titular\n", encoding="utf-8")
        antes = sha(self.agents)
        res, reg = self.aplicar()
        self.assertEqual(sha(self.agents), antes)
        self.assertFalse(self.claude.exists())
        self.assertFalse(reg["instrucoes_raiz"]["gerado"])
        self.assertIn("conflito", reg["instrucoes_raiz"])
        self.assertTrue(any("--adotar" in linha for linha in res["resumo"]), res["resumo"])


if __name__ == "__main__":
    unittest.main()
