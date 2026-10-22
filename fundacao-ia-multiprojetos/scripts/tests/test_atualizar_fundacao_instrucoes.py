"""Instruções da raiz na atualização da fundação (proposta 1 da análise do vibe-coding-toolkit, 21/10/2026).

`atualizar_fundacao.py aplicar` regenera o AGENTS.md e o CLAUDE.md da raiz depois da promoção, guardando antes os
que já existiam em registry/kit_backup/instrucoes-<carimbo>/, e a cópia DEPOIS os leva junto. O `desfazer` devolve
o anterior (ou apaga o que a atualização criou), salvo se o arquivo foi editado depois. Um AGENTS.md escrito à mão
não bloqueia a atualização: fica como está e o resumo pede a decisão do titular (`--adotar`). Com o kit igual (só a
skill mudou), o `aplicar` regenera as instruções que ficaram com o texto anterior (1.7.7).
Pastas descartáveis; identidade de ensaio; nada no perfil.
"""

from __future__ import annotations

import hashlib
import json
import re
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


class TestInstrucoesComKitIgual(unittest.TestCase):
    """Defeito anotado pelo titular na 1.7.6: com o kit igual, o `aplicar` terminava em "nada a fazer" e as instruções
    da raiz ficavam com o texto da versão anterior da skill (na liberação da 1.7.6 o AGENTS.md foi regenerado à mão).
    Agora, com o kit igual, o `aplicar` regenera as instruções quando o texto que a skill geraria difere do atual, com
    registro (hash antes e depois) e retorno pelo `desfazer`; sem diferença não toca em nada; AGENTS.md escrito à mão
    continua intocado."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="atualizar-instrucoes-kit-igual-"))
        self.raiz, self.backups = self.tmp / "raiz", self.tmp / "backups"
        r = rodar_script("instalar_kit.py", "--destino", self.raiz)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = subprocess.run([sys.executable, "-B", "-m", "fundacao", "--raiz", str(self.raiz), "init", "--admin",
                            "titular-ensaio"], cwd=str(self.raiz), env=ENV, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.env = {**ENV, IDENTIDADE: "titular-ensaio"}
        self.agents, self.claude = self.raiz / "AGENTS.md", self.raiz / "CLAUDE.md"
        self.registros = self.raiz / "evidence" / "atualizacoes"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    atualizar = TestInstrucoesNaAtualizacao.atualizar

    def aplicar(self) -> tuple:
        return self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups,
                              "--padrao-testes", "test_nenhum_*.py")

    def test_kit_igual_regenera_instrucoes_de_versao_anterior_e_registra(self):
        r = rodar_script("instrucoes_raiz.py", "gerar", "--raiz", self.raiz)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        texto = self.agents.read_text(encoding="utf-8")
        antigo = re.sub(r"(Gerado pela skill `fundacao-ia-multiprojetos` )\S+\.", r"\g<1>1.0.0.", texto, count=1)
        antigo = antigo.replace("<!-- titular: fim -->", "- prazos em vermelho\n<!-- titular: fim -->")
        self.assertNotEqual(antigo, texto)
        self.agents.write_text(antigo, encoding="utf-8", newline="\n")
        anterior = sha(self.agents)
        code, res = self.aplicar()
        self.assertEqual(code, 0, res)
        self.assertTrue(res.get("registro"), res)
        reg = json.loads(Path(res["registro"]).read_text(encoding="utf-8"))
        instr = reg["instrucoes_raiz"]
        self.assertTrue(instr["gerado"], instr)
        self.assertEqual(instr["acoes"], {"AGENTS.md": "atualizar", "CLAUDE.md": "igual"})
        self.assertEqual(instr["guardados"], [{"path": "AGENTS.md", "sha256_anterior": anterior}])  # hash antes
        self.assertEqual(instr["sha256"]["AGENTS.md"], sha(self.agents))                          # e depois
        self.assertEqual((Path(instr["copia"]) / "AGENTS.md").read_bytes().decode("utf-8"), antigo)
        conferir = rodar_script("instrucoes_raiz.py", "conferir", "--raiz", self.raiz)
        self.assertEqual(conferir.returncode, 0, conferir.stdout)
        self.assertIn("- prazos em vermelho", self.agents.read_text(encoding="utf-8"))             # trecho do titular
        self.assertTrue(any("AGENTS.md" in linha for linha in res["resumo"]), res["resumo"])
        self.assertFalse(self.backups.exists())                                 # código igual: sem cópia do código
        # Repetir não muda nada nem grava registro novo.
        registros, atual = sorted(self.registros.iterdir()), self.agents.read_bytes()
        code, res2 = self.aplicar()
        self.assertEqual(code, 0, res2)
        self.assertTrue(res2["nada_a_fazer"], res2)
        self.assertEqual((sorted(self.registros.iterdir()), self.agents.read_bytes()), (registros, atual))
        # O `desfazer` devolve o AGENTS.md anterior.
        code, des = self.atualizar("desfazer", "--registro", res["registro"])
        self.assertEqual(code, 0, des)
        self.assertEqual(sha(self.agents), anterior)
        self.assertEqual(des["instrucoes"], {"devolvidas": ["AGENTS.md"], "apagadas": [], "mantidas": []})

    def test_kit_igual_sem_diferenca_nao_toca_e_escrito_a_mao_fica(self):
        self.agents.write_text("# Regras do titular\n", encoding="utf-8")
        antes = sha(self.agents)
        code, res = self.aplicar()
        self.assertEqual(code, 0, res)
        self.assertEqual(sha(self.agents), antes)                               # sem a marca da skill: intocado
        self.assertFalse(self.claude.exists())
        self.assertFalse(self.registros.exists())
        self.assertTrue(any("--adotar" in linha for linha in res["resumo"]), res["resumo"])
        r = rodar_script("instrucoes_raiz.py", "gerar", "--raiz", self.raiz, "--adotar")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        atual = (self.agents.read_bytes(), self.claude.read_bytes())
        code, res = self.aplicar()
        self.assertEqual(code, 0, res)
        self.assertTrue(res["nada_a_fazer"], res)
        self.assertEqual((self.agents.read_bytes(), self.claude.read_bytes()), atual)
        self.assertFalse(self.registros.exists())


if __name__ == "__main__":
    unittest.main()
