"""Git próprio de cada projeto (escopo 0.5 da 1.7.10; desenho §5.3 e §9): `scripts/git_projeto.py`.

`montar` (de pacote, de pasta .git copiada e de zip do .git) traz só objetos e referências, sem a configuração nem os
ganchos antigos, e deixa a configuração final segura; recusa aninhar em outro repositório e destino fora do projeto.
`conferir` acusa chave que roda programa e gancho ativo, sem mostrar valor. `pacote` gera o pacote de um ramo para o
porteiro. Repositórios fictícios em pastas temporárias; sem git, os testes que o usam ficam pulados.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from apoio import SCRIPTS, rodar_script

GIT = shutil.which("git")
CANARIO = "CANARIO-CREDENCIAL-GIT"


def carregar():
    spec = importlib.util.spec_from_file_location("_teste_git_projeto", SCRIPTS / "git_projeto.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


MOD = carregar()


def json_de(r: subprocess.CompletedProcess) -> dict:
    try:
        return json.loads(r.stdout)
    except ValueError:
        raise AssertionError(f"saída não é JSON (código {r.returncode}): {r.stdout[-800:]} {r.stderr[-800:]}") from None


def erro_de(r: subprocess.CompletedProcess) -> str:
    try:
        return json.loads(r.stderr.strip().splitlines()[-1])["erro"]
    except (ValueError, IndexError, KeyError):
        return r.stderr


class TestMotivoDaChave(unittest.TestCase):
    """A regra das chaves que rodam programa, sem git."""

    def test_chaves_que_rodam_e_as_que_nao_rodam(self):
        rodam = [("core.hookspath", "/tmp/ganchos"), ("core.fsmonitor", "/tmp/monitor"), ("core.fsmonitor", None),
                 ("core.sshcommand", "ssh -i x"), ("core.editor", "vim"), ("core.pager", "less"),
                 ("filter.lfs.smudge", "git-lfs smudge"), ("filter.x.process", "p"), ("diff.x.textconv", "t"),
                 ("diff.x.command", "c"), ("merge.x.driver", "d"), ("credential.helper", "store"),
                 ("credential.https://exemplo.invalid.helper", "h"), ("include.path", "outro.cfg"),
                 ("includeif.gitdir:/x/.path", "y.cfg"), ("url.ext::sh -c x.insteadof", "https://"),
                 ("url.file:///tmp/r.insteadof", "https://"), ("gpg.program", "g"), ("alias.x", "!sh -c y"),
                 ("remote.origin.uploadpack", "u"), ("remote.origin.url", "ext::sh -c x"),
                 ("submodule.s.update", "!sh"), ("protocol.allow", "always"), ("protocol.ext.allow", "user"),
                 ("pager.log", "less -R"), ("hook.x.command", "c"), ("core.worktree", "/tmp/fora")]
        for chave, valor in rodam:
            with self.subTest(chave):
                self.assertIsNotNone(MOD.motivo_da_chave(chave, valor))
        nao_rodam = [("core.hookspath", "/dev/null"), ("core.fsmonitor", "false"), ("core.autocrlf", "input"),
                     ("credential.helper", ""), ("url.https://espelho.invalid/.insteadof", "https://"),
                     ("alias.st", "status"), ("pager.log", "false"), ("protocol.ext.allow", "never"),
                     ("remote.origin.url", "https://exemplo.invalid/r.git"), ("user.name", "x")]
        for chave, valor in nao_rodam:
            with self.subTest(chave):
                self.assertIsNone(MOD.motivo_da_chave(chave, valor))

    def test_subsecao_com_endereco_nao_aparece_no_relatorio(self):
        achados = MOD.chaves_que_rodam([("url.ext::sh -c " + CANARIO + ".insteadof", "https://")])
        self.assertEqual(achados[0]["chave"], "url.<x>.insteadof")
        self.assertNotIn(CANARIO, json.dumps(achados))

    def test_chaves_novas_que_rodam_programa(self):
        # gpg.ssh.defaultKeyCommand, tar.<x>.command, sendemail.toCmd/ccCmd/headerCmd e guitool.<x>.cmd também rodam.
        for chave, valor in (("gpg.ssh.defaultkeycommand", "ssh-add -L"), ("tar.tgz.command", "gzip -c"),
                             ("sendemail.tocmd", "getaddr"), ("sendemail.cccmd", "getaddr"),
                             ("sendemail.headercmd", "cabecalho"), ("guitool.minha.cmd", "programa")):
            with self.subTest(chave):
                self.assertIsNotNone(MOD.motivo_da_chave(chave, valor))


@unittest.skipUnless(GIT, "git ausente: os testes do git_projeto precisam dele")
class _Base(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="git-projeto-teste-")))
        self.addCleanup(MOD.apagar, self.base)
        casa = self.base / "casa"
        casa.mkdir()
        (self.base / "gitconfig-vazio").write_bytes(b"")
        self.env = {**os.environ, "HOME": str(casa), "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": str(self.base / "gitconfig-vazio")}
        self.raiz = self.base / "raiz"
        (self.raiz / "projects" / "p" / "outputs").mkdir(parents=True)
        self.marca = self.base / "gancho-rodou.txt"
        self.origem = self.base / "origem"
        self.git("init", "-q", "-b", "main", self.origem)
        (self.origem / "a.txt").write_bytes(b"um\n")
        self.git("-C", self.origem, "add", "a.txt")
        self.git("-C", self.origem, "commit", "-qm", "um")
        self.git("-C", self.origem, "branch", "outro")
        (self.origem / "b.txt").write_bytes(b"dois\n")
        self.git("-C", self.origem, "add", "b.txt")
        self.git("-C", self.origem, "commit", "-qm", "dois")
        self.git("-C", self.origem, "tag", "v1")
        self.pacote = self.base / "origem.bundle"
        self.git("-C", self.origem, "bundle", "create", self.pacote, "--all")

    def git(self, *args) -> str:
        # Na pasta temporária: na pasta atual o git acharia o repositório da própria skill (worktree do Windows).
        identidade = ["-c", "user.name=teste", "-c", "user.email=teste@localhost", "-c", "core.autocrlf=false"]
        r = subprocess.run([GIT, *identidade, *map(str, args)], env=self.env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120, cwd=str(self.base))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def envenenar(self, repo: Path) -> None:
        """Gancho que marcaria a execução, fsmonitor, filtro e credencial: nada disso pode ir para o repositório
        montado nem rodar."""
        gancho = repo / ".git" / "hooks" / "post-checkout"
        gancho.write_text(f"#!/bin/sh\necho rodou > '{self.marca.as_posix()}'\n", encoding="utf-8", newline="\n")
        os.chmod(gancho, 0o755)
        for chave, valor in (("core.fsmonitor", str(self.base / "monitor")), ("filter.x.smudge", "cat"),
                             ("core.autocrlf", "input"), ("credential.helper", f"!f() {{ echo {CANARIO}; }}; f")):
            self.git("-C", repo, "config", chave, valor)

    def montar(self, de, pasta: str = "repo", *extra) -> subprocess.CompletedProcess:
        return rodar_script("git_projeto.py", "montar", "--raiz", self.raiz, "--projeto", "p", "--de", de,
                            "--pasta", pasta, *extra)

    def configuracao(self, repo: Path) -> dict:
        saida = self.git("config", "--file", repo / ".git" / "config", "--list")
        return dict(linha.split("=", 1) for linha in saida.splitlines())

    def zip_do_git(self, repo: Path, destino: Path, extras: dict | None = None) -> Path:
        with zipfile.ZipFile(destino, "w") as zf:
            for pasta, _sub, arquivos in os.walk(repo / ".git"):
                for nome in arquivos:
                    caminho = Path(pasta) / nome
                    zf.write(caminho, ".git/" + caminho.relative_to(repo / ".git").as_posix())
            for nome, conteudo in (extras or {}).items():
                zf.writestr(nome, conteudo)
        return destino


class TestMontar(_Base):
    def conferir_montado(self, destino: Path, res: dict) -> None:
        self.assertTrue((destino / ".git").is_dir())
        self.assertFalse((destino / ".git" / "hooks").exists() and any((destino / ".git" / "hooks").iterdir()),
                         "gancho (ou exemplo) no repositório montado")
        self.assertFalse(self.marca.exists(), "o gancho da origem rodou")
        cfg = self.configuracao(destino)
        self.assertEqual(cfg.get("core.hookspath"), "/dev/null")
        self.assertEqual(cfg.get("core.fsmonitor"), "false")
        self.assertFalse([k for k in cfg if k.startswith(("filter.", "remote.", "credential.", "branch."))], cfg)
        self.assertEqual(res["ramos"], ["main", "outro"])
        self.assertEqual((res["etiquetas"], res["head"]), (1, "main"))
        self.assertEqual((destino / "b.txt").read_bytes(), b"dois\n")
        self.assertTrue(res["conferencia"]["ok"], res["conferencia"])
        self.assertNotIn(CANARIO, json.dumps(res))

    def test_de_pasta_git_sem_configuracao_nem_ganchos_antigos(self):
        self.envenenar(self.origem)
        r = self.montar(self.origem)
        self.assertEqual(r.returncode, 0, r.stderr)
        res = json_de(r)
        destino = self.raiz / "projects" / "p" / "repo"
        self.conferir_montado(destino, res)
        self.assertEqual(self.configuracao(destino).get("core.autocrlf"), "input", "autocrlf conforme a origem")
        for item in ("config", "hooks", "index"):
            self.assertIn(item, res["descartados"])
        for chave in ("core.fsmonitor", "filter.x.smudge", "credential.helper"):
            self.assertIn(chave, res["origem"]["que_rodaria_programa"])

    def test_de_pacote_com_autocrlf_explicito(self):
        r = self.montar(self.pacote, "sub/repo", "--autocrlf", "false")
        self.assertEqual(r.returncode, 0, r.stderr)
        destino = self.raiz / "projects" / "p" / "sub" / "repo"
        self.conferir_montado(destino, json_de(r))
        self.assertEqual(self.configuracao(destino).get("core.autocrlf"), "false")

    def test_de_zip_do_git(self):
        self.envenenar(self.origem)
        r = self.montar(self.zip_do_git(self.origem, self.base / "git.zip"))
        self.assertEqual(r.returncode, 0, r.stderr)
        res = json_de(r)
        self.conferir_montado(self.raiz / "projects" / "p" / "repo", res)
        self.assertIn("hooks", res["descartados"])

    def test_zip_com_caminho_suspeito_e_recusado_sem_criar_nada(self):
        zip_ = self.zip_do_git(self.origem, self.base / "git.zip", {"../fora.txt": "x"})
        r = self.montar(zip_)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("suspeita", erro_de(r))
        self.assertFalse((self.raiz / "projects" / "p" / "repo").exists())

    def test_alternates_da_origem_ficam_de_fora(self):
        (self.origem / ".git" / "objects" / "info").mkdir(exist_ok=True)
        (self.origem / ".git" / "objects" / "info" / "alternates").write_text(str(self.base / "outro") + "\n",
                                                                              encoding="utf-8")
        r = self.montar(self.origem)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("objects/info/alternates", json_de(r)["descartados"])

    def test_recusa_aninhar_em_outro_repositorio(self):
        for acima in (self.raiz / "projects" / "p", self.raiz):
            with self.subTest(str(acima)):
                (acima / ".git").mkdir()
                try:
                    r = self.montar(self.pacote)
                    self.assertEqual(r.returncode, 2, r.stdout)
                    self.assertIn("aninhado", erro_de(r))
                    self.assertFalse((self.raiz / "projects" / "p" / "repo").exists())
                finally:
                    (acima / ".git").rmdir()

    def test_pasta_com_maiusculas_de_pasta_proibida_recusa(self):
        # NTFS/WSL não distinguem maiúsculas: .GIT/.Claude/.PORTEIRO entrariam como .git/.claude/.porteiro.
        for pasta in (".GIT/repo", ".Claude/x", "sub/.PORTEIRO/r"):
            with self.subTest(pasta):
                r = self.montar(self.pacote, pasta)
                self.assertEqual(r.returncode, 2, r.stdout)
        self.assertFalse((self.raiz / "projects" / "p" / "sub").exists())

    def test_autocrlf_da_origem_mapeia_yes_e_usa_o_ultimo(self):
        cfg = self.origem / ".git" / "config"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "[core]\n\tautocrlf = false\n\tautocrlf = yes\n",
                       encoding="utf-8")
        r = self.montar(self.origem)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.configuracao(self.raiz / "projects" / "p" / "repo").get("core.autocrlf"), "true")

    def test_head_e_ramo_com_acento_nao_viram_master(self):
        acent = self.base / "acent"
        r = subprocess.run([GIT, "init", "-q", "-b", "café", str(acent)], env=self.env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", cwd=str(self.base))
        if r.returncode != 0 or not (acent / ".git").is_dir():
            self.skipTest(f"git não criou ramo acentuado neste ambiente: {r.stderr.strip()}")
        (acent / "a.txt").write_bytes(b"um\n")
        self.git("-C", acent, "add", "a.txt")
        self.git("-C", acent, "commit", "-qm", "um")
        res = json_de(self.montar(acent, "repo-acent"))
        self.assertEqual(res["head"], "café", "o HEAD acentuado foi trocado por master")
        self.assertNotIn("trocado por refs/heads/master", " ".join(res["avisos"]))
        repo = self.raiz / "projects" / "p" / "repo-acent"
        saida = self.raiz / "projects" / "p" / "outputs" / "g" / "cafe.bundle"
        rp = rodar_script("git_projeto.py", "pacote", "--repo", repo, "--ramo", "café", "--saida", saida)
        self.assertEqual(rp.returncode, 0, rp.stderr)

    def test_recusa_destino_fora_do_projeto_ou_ocupado(self):
        ocupado = self.raiz / "projects" / "p" / "ocupado"
        ocupado.mkdir()
        (ocupado / "x.txt").write_text("x", encoding="utf-8")
        for pasta in ("../outro/repo", str(self.base / "abs"), ".", ".git/repo", "a/../../fora", "ocupado"):
            with self.subTest(pasta):
                r = self.montar(self.pacote, pasta)
                self.assertEqual(r.returncode, 2, r.stdout)
        self.assertFalse((self.raiz / "projects" / "outro").exists())
        r = rodar_script("git_projeto.py", "montar", "--raiz", self.raiz, "--projeto", "Outro!", "--de", self.pacote,
                         "--pasta", "repo")
        self.assertEqual(r.returncode, 2)
        r = rodar_script("git_projeto.py", "montar", "--raiz", self.raiz, "--projeto", "ausente", "--de",
                         self.pacote, "--pasta", "repo")
        self.assertEqual(r.returncode, 2)


class TestConferirEPacote(_Base):
    def test_conferir_acusa_chaves_e_ganchos_sem_mostrar_valor(self):
        self.envenenar(self.origem)
        for chave, valor in (("include.path", "outro.cfg"), ("url.ext::sh -c x.insteadOf", "https://"),
                             ("alias.y", "!sh -c y"), ("core.hooksPath", str(self.base / "ganchos")),
                             ("core.sshCommand", "ssh -o x")):
            self.git("-C", self.origem, "config", chave, valor)
        r = rodar_script("git_projeto.py", "conferir", "--repo", self.origem)
        self.assertEqual(r.returncode, 1, r.stderr)
        res = json_de(r)
        chaves = {a.get("chave") for a in res["achados"]}
        for esperada in ("core.fsmonitor", "filter.x.smudge", "credential.helper", "include.path", "url.<x>.insteadof",
                         "alias.y", "core.hookspath", "core.sshcommand"):
            self.assertIn(esperada, chaves)
        self.assertIn("hooks/post-checkout", {a.get("gancho") for a in res["achados"]})
        self.assertNotIn(CANARIO, r.stdout + r.stderr)

    def test_conferir_recusa_commondir(self):
        # Com .git/commondir o git lê config e ganchos da pasta comum; conferir não pode devolver ok: true.
        self.assertEqual(self.montar(self.pacote).returncode, 0)
        repo = self.raiz / "projects" / "p" / "repo"
        (repo / ".git" / "commondir").write_text("../comum\n", encoding="utf-8")
        (self.base / "comum").mkdir(exist_ok=True)
        r = rodar_script("git_projeto.py", "conferir", "--repo", repo)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("commondir", erro_de(r))

    def test_repositorio_montado_passa_e_git_em_arquivo_recusa(self):
        self.assertEqual(self.montar(self.pacote).returncode, 0)
        r = rodar_script("git_projeto.py", "conferir", "--repo", self.raiz / "projects" / "p" / "repo")
        self.assertEqual(r.returncode, 0, r.stdout)
        worktree = self.base / "worktree"
        worktree.mkdir()
        (worktree / ".git").write_text("gitdir: " + str(self.origem / ".git") + "\n", encoding="utf-8")
        r = rodar_script("git_projeto.py", "conferir", "--repo", worktree)
        self.assertEqual(r.returncode, 2, r.stdout)

    def test_pacote_de_um_ramo_para_o_porteiro(self):
        self.assertEqual(self.montar(self.pacote).returncode, 0)
        repo = self.raiz / "projects" / "p" / "repo"
        saida = self.raiz / "projects" / "p" / "outputs" / "git" / "outro.bundle"
        r = rodar_script("git_projeto.py", "pacote", "--repo", repo, "--ramo", "outro", "--saida", saida)
        self.assertEqual(r.returncode, 0, r.stderr)
        res = json_de(r)
        self.assertEqual(res["sha256"], hashlib.sha256(saida.read_bytes()).hexdigest())
        self.assertEqual(res["commit"], self.git("-C", repo, "rev-parse", "outro").strip())
        heads = self.git("-C", repo, "bundle", "list-heads", saida)
        self.assertEqual([linha.split()[1] for linha in heads.splitlines()], ["refs/heads/outro"])
        self.assertEqual([p.name for p in saida.parent.iterdir()], ["outro.bundle"], "sobrou temporário")

    def test_pacote_recusa_ramo_inexistente_configuracao_que_roda_e_saida_errada(self):
        self.assertEqual(self.montar(self.pacote).returncode, 0)
        repo = self.raiz / "projects" / "p" / "repo"
        saida = self.raiz / "projects" / "p" / "outputs" / "x.bundle"
        r = rodar_script("git_projeto.py", "pacote", "--repo", repo, "--ramo", "nada", "--saida", saida)
        self.assertEqual(r.returncode, 2)
        self.assertIn("não existe", erro_de(r))
        for ramo in ("-x", "a..b", "a/"):
            r = rodar_script("git_projeto.py", "pacote", "--repo", repo, "--ramo", ramo, "--saida", saida)
            self.assertEqual(r.returncode, 2, ramo)
        r = rodar_script("git_projeto.py", "pacote", "--repo", repo, "--ramo", "main", "--saida",
                         saida.with_suffix(".txt"))
        self.assertEqual(r.returncode, 2)
        self.git("-C", repo, "config", "core.fsmonitor", str(self.base / "monitor"))
        r = rodar_script("git_projeto.py", "pacote", "--repo", repo, "--ramo", "main", "--saida", saida)
        self.assertEqual(r.returncode, 2)
        self.assertIn("rodariam programas", erro_de(r))
        self.assertFalse(saida.exists())


if __name__ == "__main__":
    unittest.main()
