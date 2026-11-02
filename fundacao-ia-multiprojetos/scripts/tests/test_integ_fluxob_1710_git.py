"""Integração do fluxo B na 1.7.10 (pacote INTEG-FLUXOB do lote 2), item 4: o `git_projeto.py montar` passa o
repositório montado pela conferência do `instrucoes_aninhadas.py` e avisa, na saída, o que o Claude Code ou o Codex
carregariam sozinhos dali (`AGENTS.md`, `CLAUDE.md`, `.claude/`, `.codex/`, `.mcp.json`), dizendo que, com o Git
próprio, o Codex lê o `AGENTS.md` da raiz desse Git para baixo. É aviso: o código de saída continua 0. Revisão do
pacote: o resumo da conferência que não roda tem as mesmas chaves, e só `data/` com a caixa exata cala o aviso do
`claudeMdExcludes`. Repositórios fictícios em pastas temporárias; sem git, os do `montar` são pulados.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import SCRIPTS, rodar_script

GIT = shutil.which("git")
EXTENSOES = {"AGENTS.md": "# instruções antigas (dado)\n", "CLAUDE.md": "# instruções antigas (dado)\n",
             ".claude/skills/redator/SKILL.md": "---\nname: redator\n---\n", ".codex/config.toml": "[x]\n",
             ".mcp.json": "{}\n"}


def carregar():
    spec = importlib.util.spec_from_file_location("_teste_integ_git", SCRIPTS / "git_projeto.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


MOD = carregar()


@unittest.skipUnless(GIT, "git ausente: o montar precisa dele")
class TestInstrucoesNoRepositorioMontado(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="integ-git-")))
        self.addCleanup(MOD.apagar, self.base)
        casa = self.base / "casa"
        casa.mkdir()
        (self.base / "gitconfig-vazio").write_bytes(b"")
        self.env = {**os.environ, "HOME": str(casa), "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": str(self.base / "gitconfig-vazio")}
        self.raiz = self.base / "raiz"
        (self.raiz / "projects" / "p").mkdir(parents=True)

    def git(self, *args) -> None:
        identidade = ["-c", "user.name=teste", "-c", "user.email=teste@localhost", "-c", "core.autocrlf=false"]
        r = subprocess.run([GIT, *identidade, *map(str, args)], env=self.env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120, cwd=str(self.base))
        self.assertEqual(r.returncode, 0, r.stderr)

    def origem(self, nome: str, arquivos: dict) -> Path:
        repo = self.base / nome
        self.git("init", "-q", "-b", "main", repo)
        for rel, texto in {"src/app.py": "print('ok')\n", **arquivos}.items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text(texto, encoding="utf-8", newline="\n")
        self.git("-C", repo, "add", "-A")
        self.git("-C", repo, "commit", "-qm", "um")
        return repo

    def montar(self, de: Path, pasta: str) -> dict:
        r = rodar_script("git_projeto.py", "montar", "--raiz", self.raiz, "--projeto", "p", "--de", de,
                         "--pasta", pasta)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def test_avisa_das_extensoes_e_do_agents_md_do_codex(self):
        res = self.montar(self.origem("com-extensoes", EXTENSOES), "repo")
        conf = res["instrucoes_aninhadas"]
        self.assertEqual(conf["encontrados"], 5)
        self.assertEqual(sorted(conf["itens"]["instrucoes"]), ["AGENTS.md", "CLAUDE.md"])
        self.assertEqual(conf["itens"]["skills"], [".claude/skills/redator/SKILL.md"])
        self.assertEqual((conf["itens"]["codex"], conf["itens"]["mcp"]), ([".codex/config.toml"], [".mcp.json"]))
        self.assertEqual(conf["negar_skills"], ["redator"])
        self.assertTrue(conf["completo"])
        aviso = next(a for a in res["avisos"] if "carregam sozinhos" in a)
        for trecho in ("o Codex", "AGENTS.md da raiz desse Git para baixo", "fora de data/", "--negar-skill redator"):
            self.assertIn(trecho, aviso)
        self.assertTrue(res["conferencia"]["ok"], "o aviso não muda a conferência do Git")

    def test_em_data_nao_repete_o_aviso_do_claude_md_excludes(self):
        res = self.montar(self.origem("em-data", {"AGENTS.md": "# antigo\n"}), "data/repo")
        aviso = next(a for a in res["avisos"] if "carregam sozinhos" in a)
        self.assertIn("AGENTS.md da raiz desse Git", aviso)
        self.assertNotIn("fora de data/", aviso)

    def test_repositorio_sem_extensoes_nao_avisa(self):
        res = self.montar(self.origem("limpo", {}), "repo")
        self.assertEqual(res["instrucoes_aninhadas"]["encontrados"], 0)
        self.assertFalse([a for a in res["avisos"] if "carregam sozinhos" in a])
        self.assertIn("AGENTS.md da raiz desse Git", res["instrucoes_aninhadas"]["codex"])


class TestResumoDasInstrucoes(unittest.TestCase):
    """Revisão do pacote: o resumo do erro tem as mesmas chaves do resumo normal, e o aviso do claudeMdExcludes só se
    cala em `data/` com a caixa exata (o padrão **/projects/*/data/** não garante `Data/`). Sem git: a conferência
    roda direto na pasta."""

    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="integ-git-resumo-")))
        self.addCleanup(MOD.apagar, self.base)
        (self.base / "AGENTS.md").write_text("# instruções antigas (dado)\n", encoding="utf-8")

    def test_conferencia_que_nao_roda_devolve_as_mesmas_chaves(self):
        normal, _avisos = MOD.instrucoes_do_repositorio(self.base, "repo")
        with mock.patch.object(MOD.INSTRUCOES, "listar", side_effect=OSError("falha simulada")):
            erro, avisos = MOD.instrucoes_do_repositorio(self.base, "repo")
        self.assertEqual(set(erro) - {"erro"}, set(normal))
        self.assertEqual((erro["encontrados"], erro["completo"], erro["erro"]), (None, False, "OSError"))
        self.assertEqual((erro["contagem"], erro["itens"], erro["negar_skills"]), ({}, {}, []))
        self.assertTrue(any("não rodou" in a for a in avisos))

    def test_so_data_com_a_caixa_exata_cala_o_aviso_do_claude_md_excludes(self):
        for rel, avisa in (("data/repo", False), ("Data/repo", True), ("DATA/repo", True), ("repo", True)):
            with self.subTest(rel=rel):
                _res, avisos = MOD.instrucoes_do_repositorio(self.base, rel)
                aviso = next(a for a in avisos if "carregam sozinhos" in a)
                self.assertEqual("fora de data/" in aviso, avisa)


if __name__ == "__main__":
    unittest.main()
