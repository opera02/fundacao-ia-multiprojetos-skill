"""Documentação do preparo do host: as referências apontam os scripts de `assets/host/`, declaram o que exige
administrador (UAC no Windows, sudo no Ubuntu) como passo do titular, nunca simulado como real, e só citam
parâmetros que os scripts aceitam. O checklist de dados reais e o mapa da SKILL.md levam ao preparo.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest

from apoio import ENV, SKILL

REFS = SKILL / "references"
PS1 = SKILL / "assets" / "host" / "windows" / "preparar-maquina.ps1"
SH = SKILL / "assets" / "host" / "wsl" / "preparar-wsl.sh"
SCRIPTS = ("assets/host/windows/preparar-maquina.ps1", "assets/host/wsl/preparar-wsl.sh",
           "assets/host/wsl/abrir-sessao.sh", "assets/host/wsl/settings.wsl.json")


def ler(nome: str) -> str:
    return (REFS / nome).read_text(encoding="utf-8")


def secao(texto: str, titulo: str) -> str:
    """De um título `## ...` que começa com `titulo` até o próximo `## `."""
    m = re.search(r"^## " + re.escape(titulo) + r".*?(?=^## |\Z)", texto, re.M | re.S)
    return m.group(0) if m else ""


class Referencias(unittest.TestCase):
    def test_seguranca_e_fluxo_a_apontam_os_scripts(self):
        for nome, trecho in (("seguranca-isolamento.md", secao(ler("seguranca-isolamento.md"), "5.")),
                             ("fluxo-a-implantar.md", secao(ler("fluxo-a-implantar.md"), "§Host"))):
            with self.subTest(nome=nome):
                self.assertTrue(trecho, "seção ausente")
                for script in SCRIPTS:
                    self.assertIn(script, trecho)

    def test_o_que_exige_administrador_e_do_titular_e_nunca_simulado_como_real(self):
        for nome, trecho in (("seguranca-isolamento.md", secao(ler("seguranca-isolamento.md"), "5.")),
                             ("fluxo-a-implantar.md", secao(ler("fluxo-a-implantar.md"), "§Host"))):
            with self.subTest(nome=nome):
                for termo in ("UAC", "sudo", "titular", "simula"):
                    self.assertIn(termo, trecho)
                self.assertRegex(trecho, r"[Ss]imulação nunca\s+(é|vale)")

    def test_licoes_do_caso_real_registradas(self):
        trecho = secao(ler("seguranca-isolamento.md"), "5.")
        for licao in ("(OI)(CI)", "Administradores", "allowRead", "allowWrite", "tmpfs", "[interop]"):
            self.assertIn(licao, trecho)

    def test_parametros_documentados_existem_nos_scripts(self):
        doc = secao(ler("fluxo-a-implantar.md"), "§Host") + secao(ler("seguranca-isolamento.md"), "5.")
        ps1 = PS1.read_text(encoding="utf-8-sig")
        bloco = ps1[ps1.index("param("):ps1.index("Set-StrictMode")]
        aceitos_ps1 = {m.lower() for m in re.findall(r"\$([A-Za-z]+)\b", bloco)} | {"whatif", "executionpolicy", "file"}
        for linha in (l for l in doc.splitlines() if "preparar-maquina.ps1" in l):
            for p in re.findall(r"(?<![\w-])-([A-Z][A-Za-z]+)", linha):
                self.assertIn(p.lower(), aceitos_ps1, f"-{p} em: {linha.strip()}")
        sh = SH.read_text(encoding="utf-8")
        aceitos_sh = set(re.findall(r"--[a-z0-9-]+", sh[sh.index("while [ $# -gt 0 ]"):sh.index("if [ -z \"$RAIZ\" ]")]))
        for linha in (l for l in doc.splitlines() if "preparar-wsl.sh" in l):
            for p in re.findall(r"(?<![\w-])--[a-z0-9-]+", linha):
                self.assertIn(p, aceitos_sh, f"{p} em: {linha.strip()}")


class Pontos(unittest.TestCase):
    def test_checklist_de_dados_reais_aponta_o_preparo(self):
        linhas = (SKILL / "assets" / "templates" / "CHECKLIST-DADOS-REAIS.md").read_text(encoding="utf-8").splitlines()
        itens = {int(m.group(1)): l for l in linhas if (m := re.match(r"^\| (\d+) \|", l))}
        self.assertIn("assets/host/wsl/preparar-wsl.sh", itens[6])
        self.assertIn("assets/host/windows/preparar-maquina.ps1", itens[7])
        self.assertIn("assets/host/windows/preparar-maquina.ps1", itens[11])

    def test_mapa_da_skill_leva_ao_preparo_do_host(self):
        texto = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        mapa = texto[texto.index("## 8."):texto.index("## 9.")]
        self.assertTrue(any("§Host" in l and "fluxo-a-implantar.md" in l for l in mapa.splitlines()))

    def test_capacidade_08_aponta_quem_instala_os_hooks(self):
        self.assertIn("assets/host/windows/preparar-maquina.ps1",
                      (REFS / "capacidades" / "08-ferramentas-hooks-mcp-skills-plugins.md").read_text(encoding="utf-8"))

    def test_fatos_volateis_do_preparo_conferidos_com_data(self):
        texto = ler("fontes-verificadas.md")
        for fonte in ("code.claude.com/docs/en/sandboxing", "code.claude.com/docs/en/setup",
                      "learn.microsoft.com/en-us/windows/wsl/wsl-config"):
            self.assertIn(fonte, texto)
        self.assertIn("2026-10-21", texto)

    def test_requisitos_r52_e_r53_citam_o_preparo_do_host(self):
        linhas = {l.split("|")[1].strip(): l for l in ler("requisitos.md").splitlines() if l.startswith("| R5")}
        self.assertIn("assets/host/windows/preparar-maquina.ps1", linhas["R52"])
        self.assertIn("test_host_windows.py", linhas["R52"])
        self.assertIn("assets/host/wsl/settings.wsl.json", linhas["R53"])
        self.assertIn("test_host_perfis.py", linhas["R53"])

    def test_caminhos_citados_existem(self):
        r = subprocess.run([sys.executable, "-B", str(SKILL / "scripts" / "verificar_referencias.py"), "--raiz",
                            str(SKILL)], capture_output=True, text=True, encoding="utf-8", env=ENV, timeout=120)
        self.assertEqual(json.loads(r.stdout)["ausentes"], [], r.stdout[-800:])


if __name__ == "__main__":
    unittest.main()
