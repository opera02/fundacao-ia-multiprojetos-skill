"""`chamadores_abertos.py` (1.7.11; ponytail, P5): a definição removida no diff que ainda é chamada.

Repositórios Git descartáveis com código fictício. Só lê: a árvore e o índice ficam como estavam. Uma definição removida e
ainda chamada aparece, com `arquivo:linha`; uma que foi definida de novo (movida, ou num arquivo novo) não aparece; a
base é validada antes de qualquer comando.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import ENV, SCRIPTS

spec = importlib.util.spec_from_file_location("chamadores_abertos_teste", SCRIPTS / "chamadores_abertos.py")
MOD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MOD)

LIB = "def calcular_total(itens):\n    return sum(itens)\n\n\ndef outra_funcao():\n    return 1\n"
APP = "from lib import calcular_total\n\n\ndef principal():\n    return calcular_total([1, 2])\n"
GIT = shutil.which("git")


def escrever(base: Path, arquivos: dict) -> None:
    for rel, texto in arquivos.items():
        alvo = base / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(texto.encode("utf-8"))


@unittest.skipUnless(GIT, "git não está instalado neste ambiente")
class ChamadoresAbertos(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="chamadores-abertos-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        sem_sessao = {k: v for k, v in os.environ.items() if not k.startswith(("FUNDACAO_", "GIT_"))}
        patcher = mock.patch.dict(os.environ, sem_sessao, clear=True)  # a sessão de quem roda os testes sai do ambiente
        patcher.start()
        self.addCleanup(patcher.stop)
        self.git("init", "-q", "-b", "principal")
        escrever(self.repo, {"lib.py": LIB, "app.py": APP, "README.md": "Usa calcular_total em texto.\n"})
        self.commit("v1")

    def git(self, *args) -> str:
        env = {k: v for k, v in ENV.items() if not k.startswith(("FUNDACAO_", "GIT_"))}
        r = subprocess.run(["git", "-c", "user.name=teste", "-c", "user.email=teste",
                            "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", "-C", str(self.repo), *args],
                           capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def commit(self, mensagem: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", mensagem)

    def rodar(self, *args, cwd=None) -> subprocess.CompletedProcess:
        env = {k: v for k, v in ENV.items() if not k.startswith(("FUNDACAO_", "GIT_"))}
        return subprocess.run([sys.executable, "-I", "-B", str(SCRIPTS / "chamadores_abertos.py"), *map(str, args)],
                              capture_output=True, text=True, encoding="utf-8", env=env, timeout=120, cwd=cwd)

    def abertos(self, base="HEAD") -> dict:
        return {a["nome"]: a for a in MOD.abertos(self.repo, base)["abertos"]}

    def test_definicao_removida_e_ainda_chamada_aparece_com_arquivo_e_linha(self):
        escrever(self.repo, {"lib.py": "def outra_funcao():\n    return 1\n"})
        achados = self.abertos()
        self.assertEqual(list(achados), ["calcular_total"])
        self.assertEqual(achados["calcular_total"]["removido_de"], ["lib.py"])
        self.assertIn(("app.py", 1), achados["calcular_total"]["chamadas"])   # o import
        self.assertIn(("app.py", 5), achados["calcular_total"]["chamadas"])   # a chamada
        self.assertIn(("README.md", 1), achados["calcular_total"]["chamadas"])  # texto também aparece: é por nome

    def test_definida_de_novo_em_outro_arquivo_nao_aparece(self):
        escrever(self.repo, {"lib.py": "def outra_funcao():\n    return 1\n",
                             "novo.py": "def calcular_total(itens):\n    return sum(itens)\n"})
        self.assertEqual(self.abertos(), {})  # o arquivo novo ainda nem foi adicionado ao índice

    def test_definida_de_novo_no_mesmo_arquivo_com_outro_corpo_nao_aparece(self):
        escrever(self.repo, {"lib.py": "def calcular_total(itens, desconto=0):\n    return sum(itens) - desconto\n"
                                       "\n\ndef outra_funcao():\n    return 1\n"})
        self.assertEqual(self.abertos(), {})

    def test_removida_junto_com_os_chamadores_nao_aparece(self):
        escrever(self.repo, {"lib.py": "def outra_funcao():\n    return 1\n",
                             "app.py": "def principal():\n    return 2\n", "README.md": "Texto novo.\n"})
        self.assertEqual(self.abertos(), {})

    def test_remocao_do_arquivo_inteiro_tambem_conta(self):
        (self.repo / "lib.py").unlink()
        res = MOD.abertos(self.repo, "HEAD")
        self.assertEqual(([a["nome"] for a in res["abertos"]], res["definicoes_removidas"]), (["calcular_total"], 2))

    def test_base_e_um_commit_anterior(self):
        escrever(self.repo, {"lib.py": "def outra_funcao():\n    return 1\n"})
        self.commit("v2 sem a definicao")
        self.assertEqual(self.abertos("HEAD"), {})  # árvore igual ao HEAD: nada removido
        self.assertEqual(list(self.abertos("HEAD~1")), ["calcular_total"])  # v1 contra a árvore de agora
        self.assertEqual(MOD.abertos(self.repo, "HEAD~1")["definicoes_removidas"], 1)

    def test_nomes_curtos_e_linguagens(self):
        diff = ("diff --git a/x.js b/x.js\n--- a/x.js\n+++ b/x.js\n@@ -1,4 +0,0 @@\n"
                "-export function abrirTela() {}\n-const somar = (a, b) => a + b\n-class Painel {}\n-function ab() {}\n"
                "diff --git a/y.go b/y.go\n--- a/y.go\n+++ b/y.go\n@@ -1,1 +0,0 @@\n-func (s *Servidor) Iniciar() {}\n"
                "diff --git a/z.rs b/z.rs\n--- a/z.rs\n+++ b/z.rs\n@@ -1,1 +0,0 @@\n-pub async fn conectar() {}\n"
                "diff --git a/w.txt b/w.txt\n--- a/w.txt\n+++ b/w.txt\n@@ -1,1 +0,0 @@\n-def em_texto():\n")
        self.assertEqual(MOD.removidas(diff), {"abrirTela": ["x.js"], "somar": ["x.js"], "Painel": ["x.js"],
                                               "Iniciar": ["y.go"], "conectar": ["z.rs"]})  # `ab` tem 2 letras; .txt não conta

    def test_linha_removida_que_parece_cabecalho_nao_confunde_a_leitura(self):
        diff = ("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1,3 +1,1 @@\n--- def parece_cabecalho():\n"
                "-def verdadeira():\n+def nova():\n")
        self.assertEqual(MOD.removidas(diff), {"verdadeira": ["a.py"]})

    def test_nao_escreve_nada_no_repositorio(self):
        escrever(self.repo, {"lib.py": "def outra_funcao():\n    return 1\n", "novo.txt": "x\n"})
        antes = (self.git("status", "--porcelain=v1", "-uall"), {p.name: p.stat().st_mtime_ns for p in self.repo.iterdir()
                                                                if p.is_file()})
        self.assertEqual(list(self.abertos()), ["calcular_total"])
        depois = (self.git("status", "--porcelain=v1", "-uall"), {p.name: p.stat().st_mtime_ns for p in self.repo.iterdir()
                                                                 if p.is_file()})
        self.assertEqual(antes, depois)
        self.assertEqual(sorted(p.name for p in self.repo.iterdir()), [".git", "README.md", "app.py", "lib.py", "novo.txt"])

    def test_linha_de_comando_dois_codigos_e_a_saida(self):
        limpo = self.rodar("--repositorio", self.repo, "--base", "HEAD")
        self.assertEqual((limpo.returncode, limpo.stderr), (0, ""))
        self.assertIn("0 definições removidas, 0 ainda chamadas", limpo.stdout)
        escrever(self.repo, {"lib.py": "def outra_funcao():\n    return 1\n"})
        aberto = self.rodar("--repositorio", self.repo, "--base", "HEAD")
        self.assertEqual((aberto.returncode, aberto.stderr), (1, ""))
        linhas = aberto.stdout.splitlines()
        self.assertIn("1 definições removidas, 1 ainda chamadas", linhas[0])
        self.assertTrue(linhas[1].startswith("calcular_total (removida de lib.py): "), linhas[1])
        self.assertIn("app.py:1, app.py:5", linhas[1])

    def test_base_invalida_ou_inexistente_recusa_antes_de_rodar_git(self):
        for base in ("-x", "--output=x", "HEAD; rm -rf x", "a b", "$(x)", "../fora", "", "x" * 101, "nao-existe-mesmo",
                     "HEAD\nx"):
            with self.subTest(base=base):
                r = self.rodar("--repositorio", self.repo, "--base", base)
                self.assertEqual((r.returncode, r.stdout), (2, ""))
                self.assertIn("chamadores_abertos", r.stderr)
        self.assertFalse((self.repo / "x").exists())

    def test_pasta_que_nao_e_repositorio_ou_nao_existe_recusa(self):
        solta = self.base / "solta"
        solta.mkdir()
        for pasta in (solta, self.base / "nao-existe", self.repo / "lib.py"):
            with self.subTest(pasta=pasta.name):
                r = self.rodar("--repositorio", pasta, "--base", "HEAD")
                self.assertEqual((r.returncode, r.stdout), (2, ""))

    def test_limites_fora_da_faixa_recusam(self):
        for opcao, valor in (("--limite-nomes", 0), ("--limite-nomes", 201), ("--limite-chamadas", 0),
                             ("--limite-chamadas", 51), ("--limite-nomes", "x")):
            with self.subTest(opcao=opcao, valor=valor):
                r = self.rodar("--repositorio", self.repo, "--base", "HEAD", opcao, valor)
                self.assertEqual((r.returncode, r.stdout), (2, ""))

    def test_limite_de_chamadas_e_de_nomes(self):
        escrever(self.repo, {"lib.py": "", "chama.py": "outra_funcao()\n" + "".join(f"calcular_total({i})\n" for i in range(8))})
        achados = self.abertos()
        item = achados["calcular_total"]
        self.assertEqual((len(item["chamadas"]), item["mais"] > 0), (5, True))
        resumo = MOD.abertos(self.repo, "HEAD", limite_nomes=1, limite_chamadas=2)
        self.assertEqual((len(resumo["abertos"]), resumo["abertos_total"], len(resumo["abertos"][0]["chamadas"])),
                         (1, 2, 2))
        self.assertIn("(mais 1 nomes não listados)", MOD.formatar(resumo))

    def test_sessao_de_outro_projeto_recusa(self):
        env = {k: v for k, v in ENV.items() if not k.startswith(("FUNDACAO_", "GIT_"))}
        env["FUNDACAO_" + "PROJECT"] = "outro-projeto"
        env["FUNDACAO_" + "RAIZ"] = str(self.base / "fundacao")
        r = subprocess.run([sys.executable, "-I", "-B", str(SCRIPTS / "chamadores_abertos.py"), "--repositorio",
                            str(self.repo), "--base", "HEAD"], capture_output=True, text=True, encoding="utf-8", env=env,
                           timeout=60)
        self.assertEqual((r.returncode, r.stdout), (2, ""))
        self.assertIn("só lê repositório de projects/outro-projeto", r.stderr)


if __name__ == "__main__":
    unittest.main()
