"""Integração final da 1.7.10, item I7 da folha (emenda E7, a parte do Git do projeto): o `git_projeto.py montar` grava
no `.git/info/exclude` do repositório montado a fila do porteiro e os caches da sessão, presos à raiz do repositório
(`/.porteiro/` e `/.cache/`: é onde eles ficam quando o repositório é a pasta do projeto), sem `.gitignore` versionado.

O `git status` e o `git add -A` não os pegam (as respostas do porteiro trazem saída do kit; os caches, pacotes
baixados); o histórico não muda, o que ele já tem continua visto, e a mesma pasta mais abaixo continua sendo do código.
A gravação não segue ligação e guarda o que já houver no arquivo. Repositórios fictícios em pastas temporárias; sem git,
os testes do `montar` são pulados.
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

from apoio import SCRIPTS, criar_ligacao_dir, rodar_script

GIT = shutil.which("git")
LINHAS = ["/.porteiro/", "/.cache/"]


def carregar():
    spec = importlib.util.spec_from_file_location("_teste_integ_i7_exclude", SCRIPTS / "git_projeto.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


MOD = carregar()


def linhas_do_exclude(repo: Path) -> list[str]:
    return (repo / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()


@unittest.skipUnless(GIT, "git ausente: o montar precisa dele")
class TestExcludeDoRepositorioMontado(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="integ-i7-")))
        self.addCleanup(MOD.apagar, self.base)
        casa = self.base / "casa"
        casa.mkdir()
        (self.base / "gitconfig-vazio").write_bytes(b"")
        self.env = {**os.environ, "HOME": str(casa), "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": str(self.base / "gitconfig-vazio")}
        self.raiz = self.base / "raiz"
        (self.raiz / "projects" / "p").mkdir(parents=True)
        self.origem = self.base / "origem"
        self.git("init", "-q", "-b", "main", self.origem)
        for rel, texto in {"a.txt": "um\n", ".cache/versionado.txt": "do histórico\n"}.items():
            (self.origem / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.origem / rel).write_text(texto, encoding="utf-8", newline="\n")
        self.git("-C", self.origem, "add", "-A")
        self.git("-C", self.origem, "commit", "-qm", "um")
        self.repo = self.raiz / "projects" / "p" / "repo"

    def git(self, *args) -> str:
        # Na pasta temporária: na pasta atual o git acharia o repositório da própria skill (worktree do Windows).
        identidade = ["-c", "user.name=teste", "-c", "user.email=teste@localhost", "-c", "core.autocrlf=false"]
        r = subprocess.run([GIT, *identidade, *map(str, args)], env=self.env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120, cwd=str(self.base))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def montar(self) -> dict:
        r = rodar_script("git_projeto.py", "montar", "--raiz", self.raiz, "--projeto", "p", "--de", self.origem,
                         "--pasta", "repo")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def status(self) -> list[str]:
        saida = self.git("-C", self.repo, "status", "--porcelain", "--untracked-files=all")
        return sorted(linha for linha in saida.splitlines() if linha.strip())

    def escrever(self, rels) -> None:
        for rel in rels:
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text("conteúdo fictício\n", encoding="utf-8")

    def test_montar_grava_a_fila_e_os_caches_no_exclude_local(self):
        res = self.montar()
        for linha in LINHAS:
            self.assertIn(linha, linhas_do_exclude(self.repo))
        self.assertEqual(res["configuracao"][".git/info/exclude"], LINHAS)
        self.assertFalse((self.repo / ".gitignore").exists(), "sem .gitignore versionado")
        self.assertEqual(self.status(), [], "o montar não muda a árvore de trabalho")
        # O que a sessão grava na raiz quando o repositório é a pasta do projeto, e o que é do código.
        self.escrever([".porteiro/respostas/r1.json", ".porteiro/pedidos/p1.json", ".cache/npm/pacote.tgz",
                       ".cache/pip/roda.whl", "novo.txt", "sub/.cache/y.txt", "sub/.porteiro/z.txt"])
        self.assertEqual(self.status(), ["?? novo.txt", "?? sub/.cache/y.txt", "?? sub/.porteiro/z.txt"])
        origem = self.git("-C", self.repo, "check-ignore", "-v", ".porteiro/respostas/r1.json")
        self.assertIn(".git/info/exclude", origem.replace("\\", "/"))
        self.git("-C", self.repo, "add", "-A")
        levados = self.git("-C", self.repo, "diff", "--cached", "--name-only").split()
        self.assertEqual(sorted(levados), ["novo.txt", "sub/.cache/y.txt", "sub/.porteiro/z.txt"])

    def test_o_exclude_nao_esconde_o_que_o_historico_ja_tem(self):
        self.montar()
        self.assertEqual(self.git("-C", self.repo, "log", "--format=%H", "main"),
                         self.git("-C", self.origem, "log", "--format=%H", "main"), "o histórico não muda")
        (self.repo / ".cache" / "versionado.txt").write_text("mudou\n", encoding="utf-8")
        self.assertEqual(self.status(), [" M .cache/versionado.txt"])


class TestGravarExclusoes(unittest.TestCase):
    """A gravação do exclude, sem git: a pasta `.git` é de mentira."""

    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="integ-i7-gravar-")))
        self.addCleanup(MOD.apagar, self.base)
        self.repo = self.base / "repo"
        (self.repo / ".git").mkdir(parents=True)
        self.info = self.repo / ".git" / "info"

    def test_grava_uma_vez_e_guarda_o_que_ja_havia(self):
        self.info.mkdir()
        (self.info / "exclude").write_bytes(b"*.log")  # sem quebra de linha no fim
        self.assertEqual(MOD.gravar_exclusoes(self.repo), LINHAS)
        self.assertEqual(MOD.gravar_exclusoes(self.repo), LINHAS)
        linhas = linhas_do_exclude(self.repo)
        self.assertEqual(linhas[0], "*.log")
        for linha in LINHAS:
            self.assertEqual(linhas.count(linha), 1, linhas)
        self.assertEqual([p.name for p in self.info.iterdir()], ["exclude"], "sobrou temporário")

    def test_pasta_info_por_ligacao_recusa_sem_gravar_fora(self):
        fora = self.base / "fora"
        fora.mkdir()
        criar_ligacao_dir(self.info, fora)
        with self.assertRaises((OSError, MOD.Recusa)):
            MOD.gravar_exclusoes(self.repo)
        self.assertEqual(list(fora.iterdir()), [])

    def test_exclude_por_ligacao_recusa_sem_gravar_fora(self):
        self.info.mkdir()
        alvo = self.base / "alvo.txt"
        alvo.write_text("original\n", encoding="utf-8")
        try:
            os.symlink(alvo, self.info / "exclude")
        except OSError as exc:
            self.skipTest(f"link simbólico de arquivo indisponível aqui: {exc}")
        with self.assertRaises((OSError, MOD.Recusa)):
            MOD.gravar_exclusoes(self.repo)
        self.assertEqual(alvo.read_text(encoding="utf-8"), "original\n")


if __name__ == "__main__":
    unittest.main()
