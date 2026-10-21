"""Achados da revisão de segurança independente da 1.7.0 (VCT170-01 a 03), cada um com o cenário de falha
reproduzido: caminho com `..` no registro de instalação (órfãos), registro do `desfazer` forjado e dado pessoal ou
token no inventário do host. Pastas descartáveis; nada no perfil nem numa fundação real."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import ENV, SKILL, criar_ligacao_dir, rodar_script

IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"
FORJADOS = ("fundacao/../.claude/settings.json", "tests/../projects/outro/data/caso.txt")
BS = chr(92)  # barra invertida dos caminhos do Windows, montada em execução


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class _Raiz(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="revisao-170-"))
        self.raiz = self.base / "raiz"
        r = rodar_script("instalar_kit.py", "--destino", self.raiz)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = subprocess.run([sys.executable, "-B", "-m", "fundacao", "--raiz", str(self.raiz), "init", "--admin",
                            "titular-ensaio"], cwd=str(self.raiz), env=ENV, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.env = {**ENV, IDENTIDADE: "titular-ensaio"}
        self.perfil = self.raiz / ".claude" / "settings.json"
        self.perfil.parent.mkdir(parents=True, exist_ok=True)
        self.perfil.write_text('{"permissions": {"deny": ["Read(./.env)"]}}\n', encoding="utf-8")
        self.caso = self.raiz / "projects" / "outro" / "data" / "caso.txt"
        self.caso.parent.mkdir(parents=True, exist_ok=True)
        self.caso.write_text("caso fictício de outro projeto\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def atualizar(self, *args) -> tuple:
        r = subprocess.run([sys.executable, "-B", str(SKILL / "scripts" / "atualizar_fundacao.py"), *map(str, args)],
                           env=self.env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        try:
            return r.returncode, json.loads(r.stdout)
        except ValueError:
            self.fail("saída não é JSON: " + r.stdout[-500:] + r.stderr[-500:])


class TestOrfaoComCaminhoForjado(_Raiz):
    """VCT170-01: entrada com `..` no registry/kit_install.json não pode retirar arquivo fora das áreas de código."""

    def setUp(self):
        super().setUp()
        reg = self.raiz / "registry" / "kit_install.json"
        historico = json.loads(reg.read_text(encoding="utf-8"))
        for rel, alvo in zip(FORJADOS, (self.perfil, self.caso)):
            historico[-1]["copiados"].append({"path": rel, "sha256": sha(alvo)})
        reg.write_text(json.dumps(historico, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_instalador_ignora_e_aponta_a_entrada_forjada(self):
        antes = (sha(self.perfil), sha(self.caso))
        r = rodar_script("instalar_kit.py", "--destino", self.raiz, "--atualizar")
        res = json.loads(r.stdout)
        self.assertEqual((sha(self.perfil), sha(self.caso)), antes)
        self.assertEqual(sorted(res["entradas_invalidas"]), sorted(FORJADOS))
        self.assertEqual(res.get("orfaos_retirados", []), [])

    def test_checar_recusa_atualizar_com_o_registro_adulterado(self):
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 1, chk)
        self.assertEqual(chk["mudancas"]["retirar"], [])
        self.assertTrue(any("kit_install.json" in m for m in chk["motivos"]), chk["motivos"])


class TestDesfazerComRegistroForjado(_Raiz):
    """VCT170-02: o `desfazer` não apaga fora da raiz nem sobrescreve `.claude/` a partir de um registro forjado."""

    def forjar(self, raiz_declarada: Path) -> Path:
        self.vitima = self.base / "fora-da-raiz.txt"
        self.vitima.write_text("arquivo fora da raiz\n", encoding="utf-8")
        copia = self.base / "pasta-do-atacante"
        (copia / ".claude").mkdir(parents=True)
        (copia / ".claude" / "settings.json").write_text('{"permissions": {}}\n', encoding="utf-8")
        con = sqlite3.connect(self.raiz / "state" / "state.sqlite")
        try:
            versao = con.execute("PRAGMA user_version").fetchone()[0]
        finally:
            con.close()
        reg = {"raiz": str(raiz_declarada), "user_version_antes": versao,
               "promocao": {"instalar_kit": {"substituidos": [], "copiados": [], "backup_dos_substituidos": str(copia),
                                             "orfaos_retirados": [{"path": ".claude/settings.json",
                                                                   "sha256": sha(copia / ".claude" / "settings.json")}]}},
               "instrucoes_raiz": {"gerado": True, "acoes": {"../fora-da-raiz.txt": "criar"},
                                   "sha256": {"../fora-da-raiz.txt": sha(self.vitima)}, "copia": None, "guardados": []}}
        arq = self.raiz / "evidence" / "atualizacoes" / "atualizacao-kit-9.9.9-forjado.json"
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(json.dumps(reg), encoding="utf-8")
        return arq

    def test_registro_forjado_e_recusado_sem_alterar_nada(self):
        antes = sha(self.perfil)
        code, res = self.atualizar("desfazer", "--registro", self.forjar(self.raiz))
        self.assertEqual((code, res.get("etapa")), (1, "desfazer"), res)
        self.assertTrue(self.vitima.is_file())
        self.assertEqual(sha(self.perfil), antes)

    def test_registro_que_aponta_outra_raiz_e_recusado(self):
        outra = self.base / "outra-raiz"
        outra.mkdir()
        code, res = self.atualizar("desfazer", "--registro", self.forjar(outra))
        self.assertEqual((code, res.get("etapa")), (1, "desfazer"), res)
        self.assertIn("raiz", res["motivo"])
        self.assertTrue(self.vitima.is_file())



class TestJuncaoNoCaminho(_Raiz):
    """VCT170-04 (segunda passagem da revisão): uma junção dentro da raiz (tests/elo -> .claude) faz um caminho de
    texto válido chegar ao .claude/; nem a retirada de órfãos nem o desfazer podem passar por ligação ou junção."""

    def setUp(self):
        super().setUp()
        criar_ligacao_dir(self.raiz / "tests" / "elo", self.raiz / ".claude")
        self.antes = sha(self.perfil)

    def test_instalador_e_checar_recusam_orfao_atras_de_juncao(self):
        reg = self.raiz / "registry" / "kit_install.json"
        historico = json.loads(reg.read_text(encoding="utf-8"))
        historico[-1]["copiados"].append({"path": "tests/elo/settings.json", "sha256": self.antes})
        reg.write_text(json.dumps(historico, ensure_ascii=False, indent=2), encoding="utf-8")
        r = rodar_script("instalar_kit.py", "--destino", self.raiz, "--atualizar")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("tests/elo/settings.json", json.loads(r.stdout)["fora_do_destino"])
        self.assertEqual(sha(self.perfil), self.antes)
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 1, chk)
        self.assertTrue(any("ligação" in m for m in chk["motivos"]), chk["motivos"])

    def test_desfazer_recusa_caminho_atras_de_juncao(self):
        guarda = self.raiz / "registry" / "kit_backup" / "forjado"
        (guarda / "tests" / "elo").mkdir(parents=True)
        (guarda / "tests" / "elo" / "settings.json").write_text('{"permissions": {}}\n', encoding="utf-8")
        con = sqlite3.connect(self.raiz / "state" / "state.sqlite")
        try:
            versao = con.execute("PRAGMA user_version").fetchone()[0]
        finally:
            con.close()
        reg = {"raiz": str(self.raiz), "user_version_antes": versao,
               "promocao": {"instalar_kit": {"substituidos": [], "copiados": [], "backup_dos_substituidos": str(guarda),
                                             "orfaos_retirados": [{"path": "tests/elo/settings.json",
                                                                   "sha256": sha(guarda / "tests" / "elo" / "settings.json")}]}}}
        arq = self.raiz / "evidence" / "atualizacoes" / "atualizacao-kit-9.9.9-juncao.json"
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(json.dumps(reg), encoding="utf-8")
        code, res = self.atualizar("desfazer", "--registro", arq)
        self.assertEqual((code, res.get("etapa")), (1, "desfazer"), res)
        self.assertEqual(sha(self.perfil), self.antes)


class TestInventarioSemDadoPessoalNemToken(unittest.TestCase):
    """VCT170-03: caminho de projeto de plugin e argumentos num `command` em texto único não entram no inventário."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="inventario-170-"))
        self.perfil = self.base / "perfil"
        plugins = self.perfil / ".claude" / "plugins"
        plugins.mkdir(parents=True)
        (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {"juridico@mercado": [
            {"scope": "project", "version": "1.0", "projectPath": "C:/Casos/CLIENTE-FICTICIO x Parte"}]}}),
            encoding="utf-8")
        (self.perfil / ".claude.json").write_text(json.dumps({"mcpServers": {
            "texto": {"command": "npx -y servidor --token SEGREDO-FIC-CMD"},
            "janelas": {"command": "C:/Program Files/nodejs/node.exe C:/srv/x.js --chave SEGREDO-FIC-CMD2".replace("/", BS)},
            "aspas": {"command": '"C:/Program Files/y/y.exe" --k SEGREDO-FIC-CMD3'.replace("/", BS)}}}), encoding="utf-8")
        self.saida = self.base / "inventario.json"

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_inventario_sem_caminho_de_projeto_nem_argumentos(self):
        r = rodar_script("inventariar_host.py", "gravar", "--saida", self.saida, "--perfil", self.perfil)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        texto = self.saida.read_text(encoding="utf-8")
        for proibido in ("SEGREDO-FIC-CMD", "CLIENTE-FICTICIO", "Casos"):
            self.assertNotIn(proibido, texto)
        inv = json.loads(texto)
        self.assertEqual({m["nome"]: m["executavel"] for m in inv["mcp"]},
                         {"texto": "npx", "janelas": "node.exe", "aspas": "y.exe"})
        self.assertEqual(inv["plugins"][0]["com_projeto"], True)


if __name__ == "__main__":
    unittest.main()
