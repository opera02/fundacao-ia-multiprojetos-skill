"""Revisão de segurança da 1.7.10, grupo KITCOPIA: a cópia de segurança e a restauração (KIT-F2, KIT-F7, KIT-F3, KIT-F4
e KIT-F6).

- KIT-F2: a política de backup com `State`, `STATE`, `state.`, `state `, `.`, `./state` ou `x/../state` (e o caminho
  que, por ligação no meio, cai em state/ ou sai da raiz) recusa antes de copiar; antes, as grafias com outra caixa
  levavam state/ (com o registro protegido) e a cópia verificava, mas a restauração caía no `mkdir` de state/. A cópia
  que traz state/ ou .git em files/ (feita por kit anterior) não verifica e não restaura.
- KIT-F7: `backup criar` e `backup restaurar` recusam destino dentro da raiz (<raiz>/copias e
  <raiz>/projects/<p>/outputs/x); a CLI passa a raiz viva à restauração; a próxima cópia não sugere a raiz.
- KIT-F3: o config do .git é lido como o git lê e julgado pela regra do git_projeto.py: hook.<x>.command, alias com !,
  submodule.<x>.update com ! e chaves escondidas por BOM, continuação de linha ou separador de linha do Unicode ficam
  fora; a configuração segura do `git_projeto.py montar` entra; o .git arquivo e o commondir que levam o git para fora
  de um .git levado ficam fora. Com o git (2.5x no Windows), o gancho por configuração não volta na restauração.
- KIT-F4: as pastas vazias do .git (refs/, refs/heads, refs/tags, objects/...) vão no manifesto e voltam na
  restauração; a cópia sem elas não verifica; com o git, o repositório depois de `git pack-refs --all` volta usável.
- KIT-F6: segredos_incluidos conta com a normalização da regra única (NFKC e sem caixa; pasta também no fim).
Correções da revisão 1 (no fim do arquivo):
- KIT-F4: a cópia só anota como pasta vazia o que a verificação aceita — refs/heads arquivo (reftable), objects ou refs
  arquivo, REFS/HEADS em outra caixa, ':' e '\\' no Linux —, e o manifesto com levados fora de projects/ (state, .git
  da raiz) não verifica nem recria nada.
- KIT-F3: gitdir é a pasta com HEAD na listagem, em qualquer profundidade: os hooks de modules/vendor/lib e de um gitdir
  escondido em objects/ ficam fora, o .git arquivo que leva para objects/ fica fora, e `.GIT` (ou `.git.` no Linux)
  segue a regra do .git em todos os sistemas; o gitdir absoluto dentro da raiz (o `git worktree add`) entra.
- KIT-F7: o cofre <c>/state/ com o registro, fora de uma fundação, não faz de <c> uma raiz.
Correções da revisão 2 (no fim do arquivo):
- KIT-F4: no Windows, a pasta com espaço ou ponto no fim (' ', '. ', 'x ') não é anotada nem aceita no manifesto; a
  pasta que o sistema de destino não recria (nome longo demais) não deixa a restauração liberar, sem exceção.
- KIT-F7: pela CLI, sem o banco (desastre) e com o registro num cofre, a --raiz com cara de fundação recusa o destino.
- KIT-F3: alias com opção global do git (-c) e lfs.extension ficam fora; o rebase em andamento (rebase-merge/,
  rebase-apply/) fica fora, contado; o ponteiro com caminho absoluto (git worktree add) fica fora; ramo, etiqueta e
  registro chamados config, config.worktree ou commondir (refs/, logs/) entram, e o repositório volta com eles.
- Limpeza: as pastas dos testes saem inteiras, também os objetos que o git do Windows marca somente leitura.
Correções da revisão 3 (no fim do arquivo):
- O BOM e o separador de linha dos casos do config vão por escape, com o mesmo valor (R177D-6: caractere invisível
  literal num .py da skill deixava vermelha a suíte dos scripts).
- O git dos testes roda com o caminho longo ligado (core.longpaths, do Git for Windows): com o TEMP longo, ele parava em
  'Filename too long', e o ensaio do `atualizar_fundacao.py aplicar` conta falha nova como regressão. O teste do
  reftable pula só quando o git não conhece o formato (anterior ao 2.45); outra falha do `git init` é falha.
Dados, nomes e caminhos fictícios; o git, quando usado, roda sem a configuração do sistema e do usuário.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from apoio_auditoria import criar_ligacao_dir
from helpers import FoundationTestCase

from fundacao import cli_backup
from fundacao.__main__ import _con
from fundacao.core import backup, config_git, manutencao
from fundacao.core.auth import ENV_PRINCIPAL
from fundacao.core.canon import sha256_file
from fundacao.core.contracts import ValidationError

GIT = shutil.which("git")
P = "projects/juridico-lab"
ARROBA = "@"  # montado em tempo de execução: a varredura da liberação acusa o que parece e-mail


def apagar(pasta) -> None:
    """Apaga a pasta do teste inteira (correções da revisão 2: com ignore_errors, as raízes, os destinos e as bases do
    git ficavam em %TEMP% a cada rodada): tira o somente leitura que o git do Windows põe nos objetos e, no Windows, usa
    o prefixo \\\\?\\ (nome com espaço ou ponto no fim). O rmtree não entra em ligação."""
    caminho = os.path.abspath(pasta)
    if not os.path.lexists(caminho):
        return
    if os.name == "nt" and not caminho.startswith("\\\\?\\"):
        caminho = "\\\\?\\" + caminho

    def tirar(funcao, alvo, _erro):
        try:
            os.chmod(alvo, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
            funcao(alvo)
        except OSError:
            pass
    if sys.version_info >= (3, 12):
        shutil.rmtree(caminho, onexc=tirar)
    else:
        shutil.rmtree(caminho, onerror=tirar)


class Base(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.extra = []
        self.log = self.root / "state" / "retiradas.jsonl"
        (self.root / "registry" / backup.POLITICA_BACKUP).unlink(missing_ok=True)
        self.addCleanup(apagar, self.root)  # depois do tearDown: o que o rmtree com ignore_errors deixou

    def tearDown(self):
        for p in self.extra:
            apagar(p)
        super().tearDown()

    def pasta(self, nome: str) -> Path:
        p = self.root.parent / f"{self.root.name}-{nome}"
        self.extra.append(p)
        return p

    def escrever(self, arquivos: dict) -> None:
        for rel, conteudo in arquivos.items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(conteudo if isinstance(conteudo, bytes) else conteudo.encode("utf-8"))

    def politica(self, incluir) -> None:
        (self.root / "registry" / backup.POLITICA_BACKUP).write_text(json.dumps({"incluir": incluir}),
                                                                      encoding="utf-8")

    def anexar_ao_manifesto(self, snap: Path, rel: str, conteudo: bytes) -> str:
        """Põe `rel` em files/ e no manifesto da cópia (como uma cópia de kit anterior) e devolve a âncora nova."""
        alvo = snap / "files" / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(conteudo)
        manifesto = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
        manifesto["files"].append({"path": rel, "size": len(conteudo), "sha256": sha256_file(alvo)})
        (snap / "manifest.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
        return sha256_file(snap / "manifest.json")

    def reescrever_git(self, snap: Path, **mudancas) -> str:
        manifesto = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
        for chave, valor in mudancas.items():
            if valor is None:
                manifesto["git"].pop(chave, None)
            else:
                manifesto["git"][chave] = valor
        (snap / "manifest.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
        return sha256_file(snap / "manifest.json")


# ------------------------------------------------------------------ KIT-F2
class TestPoliticaSemStateNemGit(Base):
    def test_outra_caixa_ponto_espaco_e_a_propria_raiz_recusam_antes_de_copiar(self):
        (self.root / "state" / "nota-ficticia.txt").write_text("estado fictício", encoding="utf-8")
        for incluir in (["State"], ["STATE"], ["state."], ["state "], ["."], ["./state"], ["x/../state"],
                        ["STATE/retiradas.jsonl"], [".GIT"], [".git."], ["state::$DATA"], ["docs", "./"]):
            with self.subTest(incluir=incluir):
                self.politica(incluir)
                snap = self.pasta(f"snap-{len(self.extra)}")
                with self.assertRaises(ValidationError) as ctx:
                    backup.create_backup(self.root, snap, "politica-ruim")
                self.assertIn("política de backup inválida", str(ctx.exception))
                self.assertFalse(snap.exists(), "a cópia foi feita com a política ruim")

    def test_ligacao_no_meio_que_cai_em_state_ou_sai_da_raiz_recusa(self):
        (self.root / "state" / "sub").mkdir()
        (self.root / "state" / "sub" / "nota-ficticia.txt").write_text("estado fictício", encoding="utf-8")
        fora = self.pasta("fora")
        (fora / "sub").mkdir(parents=True)
        (fora / "sub" / "nota-ficticia.txt").write_text("fora da raiz", encoding="utf-8")
        criar_ligacao_dir(self.root / "atalho", self.root / "state")
        criar_ligacao_dir(self.root / "externo", fora)
        for incluir in (["atalho/sub"], ["externo/sub"]):
            with self.subTest(incluir=incluir):
                self.politica(incluir)
                snap = self.pasta(f"snap-{len(self.extra)}")
                with self.assertRaises(ValidationError):
                    backup.create_backup(self.root, snap, "politica-por-ligacao")
                self.assertFalse(snap.exists())
        # A ligação no fim do caminho o backup não segue (como antes): passa, anotada, e nada de state/ entra.
        self.politica(["atalho", "externo"])
        m = backup.create_backup(self.root, self.pasta("snap-ligacao-no-fim"), "ligacao-no-fim")
        self.assertLessEqual({"atalho", "externo"}, set(m.get("ligacoes_nao_seguidas", [])))
        self.assertFalse(any(f["path"].startswith(("atalho/", "externo/")) for f in m["files"]))

    def test_politica_normal_continua_valendo(self):
        self.escrever({"notas/rascunho.md": "nota fictícia", "estado-do-projeto/x.md": "não é state/"})
        self.politica(["notas", "./estado-do-projeto"])
        m = backup.create_backup(self.root, self.pasta("snap"), "politica-boa")
        caminhos = {f["path"] for f in m["files"]}
        self.assertLessEqual({"notas/rascunho.md", "estado-do-projeto/x.md"}, caminhos)
        self.assertFalse(any(c.split("/")[0].lower().rstrip(". ") == "state" for c in caminhos))

    def test_copia_com_state_ou_git_em_files_nao_verifica_nem_restaura(self):
        for nome in ("State", ".GIT"):
            with self.subTest(nome=nome):
                snap = self.pasta(f"snap-{nome}")
                backup.create_backup(self.root, snap, "base")
                # Como a cópia feita por kit anterior com {"incluir": ["State"]}: files/State/ com o registro.
                ancora = self.anexar_ao_manifesto(snap, f"{nome}/retiradas.jsonl", b'{"ficticio": true}\n')
                ver = backup.verify_backup(snap, sha256_manifesto=ancora)
                self.assertEqual(ver["ancora"]["situacao"], "conferida")
                self.assertFalse(ver["ok"], "a cópia com state/ ou .git em files/ verificou")
                self.assertEqual(ver["em_state_ou_git"], [nome])
                dest = self.pasta(f"dest-{nome}")
                rep = backup.restore(snap, dest, self.log, sha256_manifesto=ancora)
                self.assertFalse(rep["released"])
                self.assertFalse(dest.exists())


# ------------------------------------------------------------------ KIT-F7
class TestDestinoForaDaRaiz(Base):
    @staticmethod
    def parser() -> argparse.ArgumentParser:
        p = argparse.ArgumentParser(prog="fundacao")
        p.add_argument("--raiz", type=Path, default=Path.cwd())
        sub = p.add_subparsers(dest="comando", required=True)
        cli_backup.registrar_parser(sub)
        return p

    def cli(self, *argv: str) -> dict:
        args = self.parser().parse_args(["--raiz", str(self.root.resolve()), "backup", *argv])
        with mock.patch.dict(os.environ, {ENV_PRINCIPAL: "operador-lab"}), \
                mock.patch("sys.stderr", new_callable=io.StringIO):
            return cli_backup.executar(args, _con)

    def test_criar_recusa_destino_dentro_da_raiz(self):
        destinos = [self.root / "copias" / "semanal", self.root / "projects" / "juridico-lab" / "outputs" / "x"]
        if os.name == "nt":  # o NTFS não distingue caixa
            destinos.append(Path(str(self.root).upper()) / "copias" / "maiusculas")
        for dentro in destinos:
            with self.subTest(destino=dentro):
                with self.assertRaises(ValidationError) as ctx:
                    backup.create_backup(self.root, dentro, "na-raiz")
                self.assertIn("dentro da raiz", str(ctx.exception))
                self.assertFalse(dentro.exists())
        self.assertFalse((self.root / "copias").exists())

    def test_restaurar_recusa_destino_dentro_da_raiz(self):
        snap = self.pasta("snap")
        ancora = backup.create_backup(self.root, snap, "fora")["sha256_manifesto"]
        for dentro in (self.root / "restaurada", self.root / "projects" / "juridico-lab" / "outputs" / "x"):
            with self.subTest(destino=dentro):
                rep = backup.restore(snap, dentro, self.log, sha256_manifesto=ancora)
                self.assertFalse(rep["released"])
                self.assertIn("dentro da raiz", rep["reason"])
                self.assertFalse(dentro.exists())
        # Registro guardado fora da raiz: a raiz viva vem da CLI (a fundação que está restaurando).
        guardado = self.pasta("guardado")
        guardado.mkdir()
        shutil.copy2(self.log, guardado / "retiradas.jsonl")
        dentro = self.root / "restaurada-pela-cli"
        res = self.cli("restaurar", "--origem", str(snap), "--destino", str(dentro), "--retiradas",
                       str(guardado / "retiradas.jsonl"), "--sha256-manifesto", ancora)
        self.assertFalse(res["released"])
        self.assertIn("dentro da raiz", res["reason"])
        self.assertFalse(dentro.exists())
        fora = self.pasta("restaurada-fora")
        res = self.cli("restaurar", "--origem", str(snap), "--destino", str(fora), "--retiradas",
                       str(guardado / "retiradas.jsonl"), "--sha256-manifesto", ancora)
        self.assertTrue(res["released"], res)

    def test_proxima_copia_nao_sugere_a_raiz(self):
        agora = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
        res = cli_backup.proxima_copia(self.root, str(self.root / "copias" / "semanal-2026-S43"), agora)
        self.assertIn("<pasta das cópias", res["destino"])
        fora = self.pasta("copias")
        res = cli_backup.proxima_copia(self.root, str(fora / "semanal-2026-S43"), agora)
        self.assertEqual(Path(res["destino"]), fora / "semanal-2026-S44")


# ------------------------------------------------------------------ KIT-F3
class TestConfigDoGitComoOGitLe(unittest.TestCase):
    def test_chaves_da_regra_do_git_projeto_ficam_fora(self):
        casos = {
            '[hook "marca"]\n\tcommand = programa-ficticio\n\tevent = pre-commit\n': "hook.command",
            '[alias]\n\tx = !programa-ficticio\n': "alias.x",
            '[submodule "s"]\n\tupdate = !programa-ficticio\n': "submodule.update",
            '[core]\n\talternateRefsCommand = programa-ficticio\n': "core.alternaterefscommand",
            '[uploadpack]\n\tpackObjectsHook = programa-ficticio\n': "uploadpack.packobjectshook",
            '[remote "o"]\n\turl = ext::programa-ficticio\n': "remote.url",
            '[url "ext::programa-ficticio"]\n\tinsteadOf = https://exemplo.invalid/\n': "url.insteadof",
            '[trailer "x"]\n\tcommand = programa-ficticio\n': "trailer.command",
            '[core]\n\tfsmonitor = true\n': "core.fsmonitor",
        }
        for texto, chave in casos.items():
            with self.subTest(texto=texto[:40]):
                self.assertEqual(manutencao.motivo_do_config(texto), f"programa configurado ({chave})")
        for texto in ('[core]\n\thooksPath = /dev/null\n\tfsmonitor = false\n\tautocrlf = input\n',
                      '[alias]\n\tst = status\n', '[diff]\n\tcommand = programa-ficticio\n',
                      '[remote "o"]\n\turl = https://exemplo.invalid/r.git\n'):
            with self.subTest(texto=texto[:40]):
                self.assertIsNone(manutencao.motivo_do_config(texto))

    def test_formatacao_nao_esconde_a_secao_de_verdade(self):
        casos = ["\ufeff[core]\n\tsshCommand = programa-ficticio\n",                     # BOM
                 "[core]\n\tx = a\u0085[user]\n\tsshCommand = programa-ficticio\n",     # separador do Unicode
                 "[core]\n\tx = a\u2028[user]\n\tsshCommand = programa-ficticio\n",
                 "[core]\n\tx = a \\\n[user]\n\tsshCommand = programa-ficticio\n",       # continuação de linha
                 "[core] sshCommand = programa-ficticio\n",                              # chave na linha da seção
                 "[CORE]\n\tSSHCOMMAND = programa-ficticio\n",
                 '[core]\n\tsshCommand = "programa-ficticio" ; comentário\n',
                 "[hook.Marca]\n\tcommand = programa-ficticio\n"]                       # subseção antiga
        for texto in casos:
            with self.subTest(texto=texto[:30]):
                self.assertTrue(str(manutencao.motivo_do_config(texto)).startswith("programa configurado"), texto)

    def test_config_que_o_git_nao_le_fica_fora_e_outro_arquivo_so_pela_url(self):
        for texto in ("[core]\x0b\tsshCommand = programa-ficticio\n", '[core]\n\teditor = "aberto\n',
                      "[core]\n\teditor = a\\q\n", b"\xef\xbb[core]\n", "[core]\n\tfsmonitor = false\x00/programa\n"):
            with self.subTest(texto=texto[:20]):
                self.assertIsNotNone(manutencao.motivo_do_config(texto))
        self.assertIsNone(manutencao.motivo_do_config("ref: refs/heads/main\n", configuracao=False))
        self.assertIsNone(manutencao.motivo_do_config(b"DIRC\x00\x00\x00\x02", configuracao=False))


class TestGitNaCopiaKitF3(Base):
    def repositorio(self, base: str, config: str) -> dict:
        return {f"{base}/.git/HEAD": "ref: refs/heads/main\n", f"{base}/.git/config": config,
                f"{base}/.git/objects/ab/cdef0123456789": bytes(range(64)),
                f"{base}/.git/refs/heads/main": "0" * 40 + "\n"}

    def test_config_com_gancho_fica_fora_e_a_segura_entra(self):
        gancho = '[core]\n\tbare = false\n[hook "marca"]\n\tcommand = programa-ficticio\n\tevent = pre-commit\n'
        segura = "[core]\n\tbare = false\n\thooksPath = /dev/null\n\tfsmonitor = false\n\tautocrlf = input\n"
        self.escrever({**self.repositorio(P, gancho), **self.repositorio(P + "/montado", segura)})
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "f3")
        caminhos = {f["path"] for f in m["files"]}
        self.assertNotIn(P + "/.git/config", caminhos, "config com hook.<x>.command entrou")
        self.assertIn(P + "/montado/.git/config", caminhos, "a configuração segura do montar ficou fora")
        fora = {e["caminho"]: e["motivo"] for e in m["git"]["config_fora"]}
        self.assertEqual(fora[P + "/.git/config"], "programa configurado (hook.command)")
        dest = self.pasta("dest")
        self.assertTrue(backup.restore(snap, dest, self.log)["released"])
        self.assertFalse((dest / P / ".git" / "config").exists())

    def test_git_arquivo_e_commondir_que_levam_para_fora_ficam_fora(self):
        q = "projects/reversa-lab"
        falso = {P + "/outputs/falso/HEAD": "ref: refs/heads/main\n",
                 P + "/outputs/falso/config": "[core]\n\tsshCommand = programa-ficticio\n",
                 P + "/outputs/falso/hooks/pre-commit": "#!/bin/sh\necho fictício\n"}
        self.escrever({**self.repositorio(P, "[core]\n\tbare = false\n"), **falso,
                       P + "/.git/worktrees/arvore/HEAD": "ref: refs/heads/outro\n",
                       P + "/.git/worktrees/arvore/commondir": "../..\n",              # o normal: entra
                       P + "/arvore/.git": "gitdir: ../.git/worktrees/arvore\n",        # o normal: entra
                       P + "/outro/.git": "gitdir: ../outputs/falso\n",
                       P + "/terceiro/.git": "gitdir: " + str(self.root / P / "outputs" / "falso") + "\n",
                       P + "/quarto/.git": "gitdir: ../../../../fora/repo.git\n",
                       P + "/.git/worktrees/desviada/commondir": "../../../outputs/falso\n",
                       q + "/.git/HEAD": "ref: refs/heads/main\n", q + "/.git/commondir": "../outputs/falso\n"})
        m = backup.create_backup(self.root, self.pasta("snap"), "f3-desvio")
        caminhos = {f["path"] for f in m["files"]}
        self.assertLessEqual({P + "/arvore/.git", P + "/.git/worktrees/arvore/commondir"}, caminhos)
        fora = {e["caminho"]: e["motivo"] for e in m["git"]["config_fora"]}
        for rel in (P + "/outro/.git", P + "/terceiro/.git", P + "/quarto/.git", q + "/.git/commondir",
                    P + "/.git/worktrees/desviada/commondir"):
            self.assertNotIn(rel, caminhos, rel)
            self.assertIn("leva o git a uma pasta", fora[rel])

    @unittest.skipUnless(GIT, "git ausente: a parte com o git real fica pulada")
    def test_com_git_o_gancho_por_configuracao_nao_volta(self):
        git = Git(self)
        repo = self.root / P / "codigo"
        git.novo(repo)
        marca = git.base / "gancho-rodou.txt"
        git(repo, "config", "hook.marca.command", "echo rodou > '" + marca.as_posix() + "'")
        git(repo, "config", "hook.marca.event", "pre-commit")
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "f3-git")
        dest = self.pasta("dest")
        self.assertTrue(backup.restore(snap, dest, self.log)["released"])
        restaurado = dest / P / "codigo"
        (restaurado / "b.txt").write_text("dois\n", encoding="utf-8")
        git(restaurado, "add", "b.txt")
        git(restaurado, "commit", "-qm", "dois")
        self.assertFalse(marca.exists(), "o gancho por configuração voltou com a restauração e rodou")


# ------------------------------------------------------------------ KIT-F4
class Git:
    """O git sem a configuração do sistema nem a do usuário, em pasta temporária (só nos testes), com o caminho longo
    ligado: core.longpaths, que só o Git for Windows lê (correções da revisão 3: com o TEMP longo, o git do Windows
    parava em 'Filename too long' no rebase e no submódulo, e o `git init` do reftable dava 'I/O error')."""

    def __init__(self, caso: unittest.TestCase):
        self.base = Path(tempfile.mkdtemp(prefix="git-kitcopia-"))
        caso.addCleanup(apagar, self.base)
        (self.base / "gitconfig-vazio").write_bytes(b"")
        self.env = {**os.environ, "HOME": str(self.base), "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": str(self.base / "gitconfig-vazio"), "GIT_TERMINAL_PROMPT": "0",
                    "GIT_CEILING_DIRECTORIES": str(Path(tempfile.gettempdir()).resolve())}
        self.caso = caso

    def __call__(self, repo: Path, *args, codigo: int | None = 0) -> subprocess.CompletedProcess:
        r = subprocess.run([GIT, "-c", "core.longpaths=true", "-c", "user.name=Teste", "-c",
                            "user.email=teste" + ARROBA + "exemplo.invalid", "-C", str(repo), *args],
                           capture_output=True, text=True, errors="replace", env=self.env, timeout=120)
        if codigo is not None:
            self.caso.assertEqual(r.returncode, codigo, f"git {args}: {r.stderr}")
        return r

    def versao(self) -> tuple[int, int] | None:
        """(maior, menor) do `git --version`; None quando a saída não traz o número."""
        r = subprocess.run([GIT, "--version"], capture_output=True, text=True, errors="replace", env=self.env,
                           timeout=60)
        numero = re.search(r"(\d+)\.(\d+)", r.stdout)
        return (int(numero.group(1)), int(numero.group(2))) if numero else None

    def novo(self, repo: Path) -> None:
        repo.mkdir(parents=True)
        self(repo, "init", "-q")
        (repo / "a.txt").write_text("um\n", encoding="utf-8")
        self(repo, "add", "a.txt")
        self(repo, "commit", "-qm", "um")


def git_sem_reftable(versao: tuple[int, int] | None, erro: str) -> bool:
    """O `git init --ref-format=reftable` falhou porque o git não conhece o formato (anterior ao 2.45)? Só então o teste
    do reftable pula; outra falha (caminho longo, disco) é falha do teste (correções da revisão 3: antes, qualquer falha
    pulava, como 'anterior ao 2.45'). Sem o número da versão, vale a mensagem do git."""
    if versao is not None:
        return versao < (2, 45)
    return "unknown option" in erro or "ref storage format" in erro


class TestPastasVaziasDoGit(Base):
    def repositorio_empacotado(self) -> None:
        self.escrever({P + "/.git/HEAD": "ref: refs/heads/main\n", P + "/.git/config": "[core]\n\tbare = false\n",
                       P + "/.git/packed-refs": "# pack-refs with: peeled fully-peeled sorted \n" + "1" * 40
                       + " refs/heads/main\n", P + "/.git/objects/pack/pack-ficticio.pack": bytes(range(32))})
        for vazia in ("refs/heads", "refs/tags", "objects/info"):
            (self.root / P / ".git" / vazia).mkdir(parents=True)

    def test_pastas_vazias_vao_no_manifesto_e_voltam_na_restauracao(self):
        self.repositorio_empacotado()
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "f4")
        vazias = set(m["git"]["pastas_vazias"])
        self.assertLessEqual({f"{P}/.git/{x}" for x in ("refs", "refs/heads", "refs/tags", "objects/info")}, vazias)
        self.assertTrue(backup.verify_backup(snap)["ok"])
        dest = self.pasta("dest")
        self.assertTrue(backup.restore(snap, dest, self.log)["released"])
        for vazia in ("refs/heads", "refs/tags", "objects/info", "objects/pack"):
            self.assertTrue((dest / P / ".git" / vazia).is_dir(), vazia)

    def test_cada_repositorio_com_head_recebe_o_minimo_mesmo_sem_a_pasta_na_origem(self):
        self.escrever({P + "/.git/HEAD": "ref: refs/heads/main\n", P + "/.git/packed-refs": "1" * 40 + " x\n"})
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "f4-minimo")
        self.assertLessEqual({f"{P}/.git/{x}" for x in ("objects", "refs", "refs/heads", "refs/tags")},
                             set(m["git"]["pastas_vazias"]))
        self.assertTrue(backup.verify_backup(snap)["ok"])

    def test_copia_sem_as_pastas_vazias_ou_com_pasta_forjada_nao_verifica(self):
        self.repositorio_empacotado()
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "f4-antiga")
        ancora = self.reescrever_git(snap, pastas_vazias=None)  # como a cópia do kit antes desta correção
        ver = backup.verify_backup(snap, sha256_manifesto=ancora)
        self.assertFalse(ver["ok"], "a cópia que voltaria sem refs/ verificou")
        self.assertEqual(ver["git_incompleto"], [{"caminho": P + "/.git", "falta": ["refs"]}])
        forjadas = ["../fora", P + "/.git/HEAD", "docs/nova", P + "/.git/refs/../../x", P + "/.git/refs"]
        ancora = self.reescrever_git(snap, pastas_vazias=forjadas)
        ver = backup.verify_backup(snap, sha256_manifesto=ancora)
        self.assertFalse(ver["ok"])
        self.assertEqual(len(ver["git_incompleto"]), 4, ver["git_incompleto"])
        dest = self.pasta("dest")
        self.assertFalse(backup.restore(snap, dest, self.log, sha256_manifesto=ancora)["released"])
        self.assertFalse(dest.exists())
        self.assertFalse((self.root.parent / "fora").exists())
        for estranho in (5, {"x": 1}):  # fora do formato: não derruba a verificação, e ela não confere
            ver = backup.verify_backup(snap, sha256_manifesto=self.reescrever_git(snap, pastas_vazias=estranho))
            self.assertFalse(ver["ok"])
            self.assertIn({"caminho": "git.pastas_vazias", "motivo": "não é uma lista"}, ver["git_incompleto"])

    @unittest.skipUnless(GIT, "git ausente: a parte com o git real fica pulada")
    def test_com_git_repositorio_depois_de_pack_refs_volta_funcionando(self):
        git = Git(self)
        repo = self.root / P / "codigo"
        git.novo(repo)
        git(repo, "pack-refs", "--all")
        self.assertEqual([p for p in (repo / ".git" / "refs" / "heads").rglob("*") if p.is_file()], [],
                         "o pack-refs deixou ref solta")
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "f4-git")
        self.assertTrue(backup.verify_backup(snap)["ok"])
        dest = self.pasta("dest")
        self.assertTrue(backup.restore(snap, dest, self.log)["released"])
        restaurado = dest / P / "codigo"
        self.assertEqual(git(restaurado, "status", "--porcelain").stdout.strip(), "")
        self.assertEqual(len(git(restaurado, "log", "--oneline").stdout.strip().splitlines()), 1)


# ------------------------------------------------------------------ KIT-F6
class TestSegredoComANormalizacaoDaRegraUnica(Base):
    SIM = ["projects/p/ｉｄ_ｒｓａ", "projects/p/ＩＤ_ＲＳＡ",
           "projects/p/.ｓｓｈ/config", "projects/p/.pgpaß", "projects/p/.ſſh/config",
           "projects/p/.docker", "projects/p/.AWS", "projects/p/ﬁle.pem"]
    NAO = ["projects/p/.env.example", "projects/p/chave.sample", "projects/p/README.md", "projects/p/tokenizer.py",
           "projects/p/.git/config", "projects/p/K.txt"]

    def test_mesma_normalizacao_da_regra_unica(self):
        sim = self.SIM + (["projects/p/.ssh\\id-ficticio"] if os.name != "nt" else [])
        for rel in sim:
            self.assertTrue(manutencao.com_cara_de_segredo(rel), rel)
        for rel in self.NAO:
            self.assertFalse(manutencao.com_cara_de_segredo(rel), rel)

    def test_segredos_incluidos_conta_como_a_regra_unica(self):
        p = "projects/reversa-lab"
        self.escrever({p + "/ｉｄ_ｒｓａ": "FICTICIO", p + "/.ｓｓｈ/config": "FICTICIO",
                       p + "/.docker": "FICTICIO", p + "/.env.example": "EXEMPLO=FICTICIO", p + "/notas.md": "nota"})
        m = backup.create_backup(self.root, self.pasta("snap"), "f6")
        self.assertEqual(m["segredos_incluidos"], 3)
        self.assertIn("3 arquivo(s) com cara de segredo", m["credentials"])


# ------------------------------------------------------------------ correções da revisão 1
class TestPastasVaziasQueAVerificacaoAceita(Base):
    """Revisão 1, defeito 1 (regressão do KIT-F4), e revisão 2, defeitos 1 e 2: a cópia anota só o que a própria
    verificação aceita — antes, o refs/heads arquivo do reftable (ou o que uma sessão grava no projeto) fazia toda cópia
    da fundação dar `backup verificar` ok false e `backup íntegro? não` na restauração —, e o manifesto com levado fora
    de projects/ não verifica nem recria nada (antes, `state` recriava state/x e a restauração caía no mkdir)."""

    def copiar_e_restaurar(self, rotulo: str):
        snap = self.pasta(f"snap-{rotulo}")
        m = backup.create_backup(self.root, snap, rotulo)
        ver = backup.verify_backup(snap)
        self.assertTrue(ver["ok"], ver.get("git_incompleto"))
        dest = self.pasta(f"dest-{rotulo}")
        rep = backup.restore(snap, dest, self.log)
        self.assertTrue(rep["released"], rep.get("reason"))
        return m, dest

    def test_refs_heads_arquivo_como_no_reftable_verifica_e_restaura(self):
        q = P + "/qualquer"
        self.escrever({q + "/.git/HEAD": "ref: refs/heads/.invalid\n",
                       q + "/.git/refs/heads": "this repository uses the reftable format\n",
                       q + "/.git/reftable/tables.list": "0x000000000001-0x000000000002-0a0b0c0d.ref\n"})
        m, dest = self.copiar_e_restaurar("reftable-sintetico")
        vazias = set(m["git"]["pastas_vazias"])
        self.assertNotIn(q + "/.git/refs/heads", vazias)
        self.assertLessEqual({q + "/.git/objects", q + "/.git/refs/tags"}, vazias)
        self.assertTrue((dest / q / ".git" / "refs" / "heads").is_file())
        self.assertTrue((dest / q / ".git" / "objects").is_dir())

    def test_objects_ou_refs_arquivo_e_refs_heads_em_outra_caixa(self):
        casos = {"objetos-arquivo": ".git/objects", "refs-arquivo": ".git/refs", "outra-caixa": ".git/REFS/HEADS"}
        for nome, arquivo in casos.items():
            self.escrever({f"{P}/{nome}/.git/HEAD": "ref: refs/heads/main\n", f"{P}/{nome}/{arquivo}": "fictício\n"})
        m, dest = self.copiar_e_restaurar("arquivo-no-lugar-de-pasta")
        for nome, arquivo in casos.items():
            with self.subTest(caso=nome):
                alvo = f"{P}/{nome}/{arquivo}".lower()
                self.assertEqual([v for v in m["git"]["pastas_vazias"]
                                  if v.lower() == alvo or v.lower().startswith(alvo + "/")], [])
                self.assertTrue((dest / P / nome / arquivo).is_file())

    @unittest.skipUnless(GIT, "git ausente: a parte com o git real fica pulada")
    def test_com_git_repositorio_reftable_verifica_e_volta_funcionando(self):
        git = Git(self)
        repo = self.root / P / "codigo-reftable"
        repo.mkdir(parents=True)
        r = git(repo, "init", "-q", "--ref-format=reftable", codigo=None)
        if r.returncode != 0 and git_sem_reftable(git.versao(), r.stderr):
            self.skipTest("git sem o formato reftable (anterior ao 2.45)")
        self.assertEqual(r.returncode, 0, "git init --ref-format=reftable: " + r.stderr)  # revisão 3: falha, não pula
        (repo / "a.txt").write_text("um\n", encoding="utf-8")
        git(repo, "add", "a.txt")
        git(repo, "commit", "-qm", "um")
        self.assertTrue((repo / ".git" / "refs" / "heads").is_file(), "o git não criou o refs/heads do reftable")
        _m, dest = self.copiar_e_restaurar("reftable")
        restaurado = dest / P / "codigo-reftable"
        self.assertEqual(len(git(restaurado, "log", "--oneline").stdout.strip().splitlines()), 1)
        self.assertEqual(git(restaurado, "status", "--porcelain").stdout.strip(), "")
        (restaurado / "b.txt").write_text("dois\n", encoding="utf-8")
        git(restaurado, "add", "b.txt")
        git(restaurado, "commit", "-qm", "dois")

    @unittest.skipIf(os.name == "nt", "no Windows, ':' e '\\' não cabem em nome de pasta")
    def test_no_linux_pasta_com_dois_pontos_ou_barra_invertida_volta(self):
        self.escrever({P + "/.git/HEAD": "ref: refs/heads/main\n", P + "/.git/packed-refs": "1" * 40 + " x\n"})
        for nome in ("a:b", "c\\d"):
            (self.root / P / ".git" / "modules" / nome / "refs" / "tags").mkdir(parents=True)
        m, dest = self.copiar_e_restaurar("dois-pontos")
        for nome in ("a:b", "c\\d"):
            with self.subTest(nome=nome):
                self.assertIn(f"{P}/.git/modules/{nome}/refs/tags", m["git"]["pastas_vazias"])
                self.assertTrue((dest / P / ".git" / "modules" / nome / "refs" / "tags").is_dir())

    def test_levado_fora_de_projects_no_manifesto_nao_verifica_nem_recria(self):
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "levados-forjados")
        casos = ((["state"], ["state/x"]), (["State"], ["State/x"]), ([".git"], [".git/hooks"]),
                 (["projects"], ["projects/nova"]))
        for i, (levados, vazias) in enumerate(casos):
            with self.subTest(levados=levados):
                ancora = self.reescrever_git(snap, levados=levados, pastas_vazias=vazias)
                ver = backup.verify_backup(snap, sha256_manifesto=ancora)
                self.assertFalse(ver["ok"])
                self.assertEqual(ver["git_incompleto"], [{"caminho": vazias[0], "motivo": "fora de um .git levado"}])
                dest = self.pasta(f"dest-forjado-{i}")
                rep = backup.restore(snap, dest, self.log, sha256_manifesto=ancora)
                self.assertFalse(rep["released"])
                self.assertEqual(rep["reason"], "backup íntegro? não")
                self.assertFalse(dest.exists())


class TestGitdirsPelaListagem(Base):
    """Revisão 1, defeitos 2, 3 e 4 (KIT-F3): gitdir é a pasta com HEAD na listagem, em qualquer profundidade, e os
    nomes do .git valem sem caixa e sem ponto ou espaço no fim em todos os sistemas."""
    GANCHO = '[hook "marca"]\n\tcommand = programa-ficticio\n\tevent = pre-commit\n'
    SCRIPT = "#!/bin/sh\necho fictício\n"

    def test_gitdir_escondido_em_objects_nao_leva_gancho_nem_config(self):
        ev = P + "/.git/objects/ev"
        self.escrever({P + "/.git/HEAD": "ref: refs/heads/main\n", P + "/.git/config": "[core]\n\tbare = false\n",
                       P + "/.git/objects/ab/cdef0123": bytes(range(32)),
                       ev + "/HEAD": "ref: refs/heads/main\n", ev + "/config": self.GANCHO,
                       ev + "/hooks/pre-commit": self.SCRIPT, ev + "/refs/heads/main": "0" * 40 + "\n",
                       P + "/sub/.git": "gitdir: ../.git/objects/ev\n",
                       P + "/outra/.git": "gitdir: " + (self.root / ev).as_posix() + "\n"})
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "gitdir-em-objects")
        caminhos = {f["path"] for f in m["files"]}
        for rel in (ev + "/config", ev + "/hooks/pre-commit", P + "/sub/.git", P + "/outra/.git"):
            self.assertNotIn(rel, caminhos, rel)
        self.assertLessEqual({ev + "/HEAD", P + "/.git/objects/ab/cdef0123"}, caminhos)
        fora = {e["caminho"]: e["motivo"] for e in m["git"]["config_fora"]}
        self.assertEqual(fora[ev + "/config"], "programa configurado (hook.command)")
        for rel in (P + "/sub/.git", P + "/outra/.git"):
            self.assertIn("leva o git a uma pasta", fora[rel])
        self.assertEqual(m["git"]["hooks_fora"], 1)
        self.assertTrue(backup.verify_backup(snap)["ok"])
        dest = self.pasta("dest")
        self.assertTrue(backup.restore(snap, dest, self.log)["released"])
        self.assertFalse((dest / ev / "hooks").exists())

    @unittest.skipUnless(GIT, "git ausente: a parte com o git real fica pulada")
    def test_com_git_gitdir_em_objects_nao_volta_com_os_ganchos(self):
        git = Git(self)
        repo = self.root / P / "codigo"
        git.novo(repo)
        ev, sub = repo / ".git" / "objects" / "ev", repo / "sub"
        git(repo, "init", "-q", "--separate-git-dir", str(ev), str(sub))
        (sub / ".git").unlink()  # o git do Windows o marca oculto, e oculto não se sobrescreve
        (sub / ".git").write_bytes(b"gitdir: ../.git/objects/ev\n")  # relativo: a cópia restaurada leva a ela mesma
        por_config, por_arquivo = git.base / "por-configuracao.txt", git.base / "por-arquivo.txt"
        git(sub, "config", "hook.marca.command", "echo rodou > '" + por_config.as_posix() + "'")
        git(sub, "config", "hook.marca.event", "pre-commit")
        gancho = ev / "hooks" / "pre-commit"
        gancho.write_bytes(("#!/bin/sh\necho rodou > '" + por_arquivo.as_posix() + "'\n").encode("utf-8"))
        gancho.chmod(0o755)
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "gitdir-em-objects-git")
        fora = {e["caminho"] for e in m["git"]["config_fora"]}
        self.assertLessEqual({P + "/codigo/sub/.git", P + "/codigo/.git/objects/ev/config"}, fora)
        self.assertNotIn(P + "/codigo/.git/objects/ev/hooks/pre-commit", {f["path"] for f in m["files"]})
        dest = self.pasta("dest")
        self.assertTrue(backup.restore(snap, dest, self.log)["released"])
        restaurado = dest / P / "codigo" / "sub"
        restaurado.mkdir(exist_ok=True)  # sub/ só tinha o .git arquivo, que ficou fora: o commit vai ao repositório de cima
        (restaurado / "b.txt").write_text("dois\n", encoding="utf-8")
        git(restaurado, "add", "b.txt")
        git(restaurado, "commit", "-qm", "dois")
        self.assertFalse(por_config.exists() or por_arquivo.exists(), "um gancho do gitdir escondido em objects/ rodou")

    def test_head_em_refs_ou_logs_e_ref_nao_gitdir(self):
        # Guarda da regra nova: refs/remotes/origin/HEAD (ref simbólica de todo clone) e logs/HEAD (registro) não fazem
        # da pasta um gitdir; o ramo remoto hooks/ramo e o registro dele entram.
        registro = "0" * 40 + " " + "1" * 40 + " registro fictício\n"
        origem, logs = P + "/.git/refs/remotes/origin", P + "/.git/logs/refs/remotes/origin"
        self.escrever({P + "/.git/HEAD": "ref: refs/heads/main\n", P + "/.git/logs/HEAD": registro,
                       origem + "/HEAD": "ref: refs/remotes/origin/main\n", origem + "/hooks/ramo": "1" * 40 + "\n",
                       logs + "/HEAD": registro, logs + "/hooks/ramo": registro})
        m = backup.create_backup(self.root, self.pasta("snap"), "head-em-refs")
        self.assertLessEqual({origem + "/hooks/ramo", logs + "/hooks/ramo"}, {f["path"] for f in m["files"]})
        self.assertEqual(m["git"]["hooks_fora"], 0)

    def test_commondir_so_leva_a_um_gitdir_da_listagem(self):
        w, v = P + "/.git/worktrees/w", P + "/.git/worktrees/v"
        self.escrever({P + "/.git/HEAD": "ref: refs/heads/main\n",
                       P + "/.git/extra/objects/info/packs": "\n", P + "/.git/extra/refs/heads/main": "0" * 40 + "\n",
                       P + "/.git/extra/hooks/pre-commit": self.SCRIPT,
                       w + "/HEAD": "ref: refs/heads/main\n", w + "/commondir": "../../extra\n",
                       v + "/HEAD": "ref: refs/heads/main\n", v + "/commondir": "../..\n"})
        m = backup.create_backup(self.root, self.pasta("snap"), "commondir")
        caminhos = {f["path"] for f in m["files"]}
        self.assertNotIn(w + "/commondir", caminhos, "commondir para pasta sem HEAD (os hooks dela entram) entrou")
        self.assertIn(v + "/commondir", caminhos)
        fora = {e["caminho"]: e["motivo"] for e in m["git"]["config_fora"]}
        self.assertIn("leva o git a uma pasta", fora[w + "/commondir"])

    def test_submodulo_com_barra_no_nome_nao_leva_os_ganchos(self):
        lib = P + "/.git/modules/vendor/lib"
        self.escrever({P + "/.git/HEAD": "ref: refs/heads/main\n", lib + "/HEAD": "ref: refs/heads/main\n",
                       lib + "/config": "[core]\n\tbare = false\n", lib + "/refs/heads/main": "0" * 40 + "\n",
                       lib + "/hooks/pre-commit": self.SCRIPT, lib + "/hooks/post-checkout": self.SCRIPT,
                       P + "/vendor/lib/.git": "gitdir: ../../.git/modules/vendor/lib\n"})
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "submodulo-com-barra")
        caminhos = {f["path"] for f in m["files"]}
        self.assertEqual([c for c in caminhos if "/hooks/" in c], [])
        self.assertLessEqual({lib + "/HEAD", lib + "/config", P + "/vendor/lib/.git"}, caminhos)
        self.assertEqual(m["git"]["hooks_fora"], 2)
        self.assertEqual([p for p in m["git"]["pastas_vazias"] if p.endswith("/hooks")], [])
        dest = self.pasta("dest")
        self.assertTrue(backup.restore(snap, dest, self.log)["released"])
        self.assertFalse((dest / lib / "hooks").exists())

    @unittest.skipUnless(GIT, "git ausente: a parte com o git real fica pulada")
    def test_com_git_submodulo_vendor_lib_nao_leva_o_gancho(self):
        git = Git(self)
        origem = git.base / "origem"
        git.novo(origem)
        repo = self.root / P / "codigo"
        git.novo(repo)
        git(repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q", origem.as_posix(), "vendor/lib")
        git(repo, "commit", "-qm", "submodulo")
        modulo = repo / ".git" / "modules" / "vendor" / "lib"
        self.assertTrue((modulo / "HEAD").is_file(), "o gitdir do submódulo não ficou em modules/vendor/lib")
        marca = git.base / "gancho-do-submodulo.txt"
        gancho = modulo / "hooks" / "pre-commit"
        gancho.write_bytes(("#!/bin/sh\necho rodou > '" + marca.as_posix() + "'\n").encode("utf-8"))
        gancho.chmod(0o755)
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "submodulo-git")
        rel = P + "/codigo/.git/modules/vendor/lib/hooks/pre-commit"
        self.assertNotIn(rel, {f["path"] for f in m["files"]})
        dest = self.pasta("dest")
        self.assertTrue(backup.restore(snap, dest, self.log)["released"])
        self.assertFalse((dest / rel).exists())
        sub = dest / P / "codigo" / "vendor" / "lib"
        (sub / "b.txt").write_text("dois\n", encoding="utf-8")
        git(sub, "add", "b.txt")
        git(sub, "commit", "-qm", "dois")
        self.assertFalse(marca.exists(), "o gancho do submódulo voltou com a restauração e rodou")

    def test_git_em_outra_caixa_segue_a_regra_em_todos_os_sistemas(self):
        nomes = [".GIT", ".Git"] + ([".git.", ".GIT "] if os.name != "nt" else [])
        for i, nome in enumerate(nomes):
            base = f"{P}/repo-{i}/{nome}"
            self.escrever({base + "/HEAD": "ref: refs/heads/main\n", base + "/config": self.GANCHO,
                           base + "/hooks/pre-commit": self.SCRIPT, base + "/objects/ab/cdef": bytes(range(16))})
        m = backup.create_backup(self.root, self.pasta("snap"), "git-outra-caixa")
        caminhos = {f["path"] for f in m["files"]}
        fora = {e["caminho"] for e in m["git"]["config_fora"]}
        self.assertEqual(m["git"]["hooks_fora"], len(nomes))
        for i, nome in enumerate(nomes):
            base = f"{P}/repo-{i}/{nome}"
            with self.subTest(nome=nome):
                self.assertIn(base, m["git"]["levados"])
                self.assertIn(base + "/config", fora)
                self.assertNotIn(base + "/hooks/pre-commit", caminhos)
                self.assertIn(base + "/objects/ab/cdef", caminhos)

    def test_git_arquivo_com_gitdir_absoluto_dentro_da_raiz_fica_fora(self):
        # Revisão 2, o que faltou: o `git worktree add` grava o gitdir absoluto; o commondir normal entra. Aperto das
        # correções da revisão 2 (KIT-F3): restaurado em outra pasta, o gitdir absoluto levava o commit ao repositório e
        # aos ganchos da origem; agora fica fora, com o motivo (antes, este teste exigia que ele entrasse).
        arvore = P + "/.git/worktrees/arvore"
        self.escrever({P + "/.git/HEAD": "ref: refs/heads/main\n", arvore + "/HEAD": "ref: refs/heads/outro\n",
                       arvore + "/commondir": "../..\n",
                       P + "/arvore/.git": "gitdir: " + (self.root / arvore).as_posix() + "\n"})
        m = backup.create_backup(self.root, self.pasta("snap"), "gitdir-absoluto")
        caminhos = {f["path"] for f in m["files"]}
        self.assertLessEqual({arvore + "/commondir"}, caminhos)
        self.assertNotIn(P + "/arvore/.git", caminhos)
        self.assertEqual(m["git"]["config_fora"], [{"caminho": P + "/arvore/.git", "motivo": config_git.ABSOLUTO}])

    def test_alvo_do_desvio_nas_formas_do_windows_e_do_wsl(self):
        from fundacao.core import config_git  # módulo da revisão de segurança da 1.7.10 (KIT-F3)
        nativa, outra = (("E:\\Fundacao\\Raiz", "/mnt/e/Fundacao/Raiz") if os.name == "nt"
                         else ("/mnt/e/Fundacao/Raiz", "E:/Fundacao/Raiz"))
        rel, alvo = "projects/p/arvore/.git", "projects/p/.git/worktrees/w"
        for forma in (nativa.replace("\\", "/"), outra, outra.lower()):
            with self.subTest(forma=forma):
                dados = ("gitdir: " + forma + "/" + alvo + "\n").encode("utf-8")
                self.assertEqual(config_git.alvo_do_desvio(dados, rel, Path(nativa), gitfile=True), alvo)
        self.assertEqual(config_git.alvo_do_desvio(b"gitdir: ../.git/worktrees/w\r\n", rel, Path(nativa), True), alvo)
        self.assertEqual(config_git.alvo_do_desvio(b"../..\n", alvo + "/commondir", Path(nativa), False),
                         "projects/p/.git")
        for fora in ("gitdir: /mnt/f/Fundacao/Raiz/" + alvo, "gitdir: F:/Fundacao/Raiz/" + alvo,
                     "gitdir: ../../../../fora"):
            with self.subTest(fora=fora):
                self.assertIsNone(config_git.alvo_do_desvio(fora.encode("utf-8"), rel, Path(nativa), True))


class TestCofreNaoEFundacao(Base):
    """Revisão 2, defeito 3 (KIT-F7): a pasta acima do state/ do registro só conta como raiz com fundacao/ ou projects/;
    o cofre que guarda o registro e o livro fora da raiz aceita a restauração ao lado."""

    def test_registro_num_cofre_sem_fundacao_libera_e_com_fundacao_recusa(self):
        snap = self.pasta("snap")
        ancora = backup.create_backup(self.root, snap, "cofre")["sha256_manifesto"]
        cofre = self.pasta("cofre")
        (cofre / "state").mkdir(parents=True)
        registro = cofre / "state" / "retiradas.jsonl"
        shutil.copy2(self.log, registro)
        rep = backup.restore(snap, cofre / "restaurada", registro, sha256_manifesto=ancora)
        self.assertTrue(rep["released"], rep.get("reason"))
        for marca in ("fundacao", "projects"):
            with self.subTest(marca=marca):
                (cofre / marca).mkdir()
                dest = cofre / f"restaurada-com-{marca}"
                rep = backup.restore(snap, dest, registro, sha256_manifesto=ancora)
                self.assertFalse(rep["released"])
                self.assertIn("dentro da raiz", rep["reason"])
                self.assertFalse(dest.exists())
                (cofre / marca).rmdir()


# ------------------------------------------------------------------ correções da revisão 2
def rodar_cli(caso: Base, *argv: str) -> dict:
    """`python -m fundacao --raiz <raiz> backup ...` (como TestDestinoForaDaRaiz.cli), com o administrador de ensaio."""
    args = TestDestinoForaDaRaiz.parser().parse_args(["--raiz", str(caso.root.resolve()), "backup", *argv])
    with mock.patch.dict(os.environ, {ENV_PRINCIPAL: "operador-lab"}), \
            mock.patch("sys.stderr", new_callable=io.StringIO):
        return cli_backup.executar(args, _con)


class TestNomeQueOSistemaNaoRecria(Base):
    """Revisão 2, defeito médio (KIT-F4): no Windows, ' ' e '. ' são listados (o lstat comum abre a pasta de cima),
    `pastas_vazias` os anotava, a verificação dava ok e a restauração caía no FileNotFoundError do `makedirs` depois de
    'backup íntegro' — qualquer sessão de projeto tornava irrestaurável toda cópia seguinte. E a pasta que o sistema de
    destino não recria (nome longo demais) não deixa a restauração liberar, em vez de levantar OSError."""

    def repositorio(self) -> None:
        self.escrever({P + "/.git/HEAD": "ref: refs/heads/main\n", P + "/.git/packed-refs": "1" * 40 + " x\n"})

    @unittest.skipUnless(os.name == "nt", "só o Windows tira o espaço e o ponto do fim do nome")
    def test_pasta_com_espaco_ou_ponto_no_fim_nao_e_anotada_e_a_copia_restaura(self):
        self.repositorio()
        estendido = "\\\\?\\" + str(self.root / P / ".git")  # como uma sessão grava, ou o DrvFs de /mnt/<letra>
        for nome in (" ", ". "):
            os.mkdir(estendido + "\\" + nome)
            os.mkdir(estendido + "\\" + nome + "\\z")
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "nome-com-espaco")
        self.assertEqual([v for v in m["git"]["pastas_vazias"] if any(p != p.rstrip(" .") for p in v.split("/"))], [])
        ver = backup.verify_backup(snap)
        self.assertTrue(ver["ok"], ver.get("git_incompleto"))
        dest = self.pasta("dest")
        rep = backup.restore(snap, dest, self.log)
        self.assertTrue(rep["released"], rep.get("reason"))
        self.assertTrue((dest / P / ".git" / "refs" / "heads").is_dir())

    @unittest.skipUnless(os.name == "nt", "só o Windows tira o espaço e o ponto do fim do nome")
    def test_manifesto_com_pasta_que_o_windows_nao_recria_nao_verifica(self):
        self.repositorio()
        snap = self.pasta("snap")
        vazias = backup.create_backup(self.root, snap, "forjada-espaco")["git"]["pastas_vazias"]
        for i, forjada in enumerate((f"{P}/.git/x /y", f"{P}/.git/ /z", f"{P}/.git/refs/tags. ")):
            with self.subTest(forjada=forjada):
                ancora = self.reescrever_git(snap, pastas_vazias=[*vazias, forjada])
                ver = backup.verify_backup(snap, sha256_manifesto=ancora)
                self.assertFalse(ver["ok"])
                self.assertIn({"caminho": forjada, "motivo": "caminho inválido"}, ver["git_incompleto"])
                dest = self.pasta(f"dest-{i}")
                rep = backup.restore(snap, dest, self.log, sha256_manifesto=ancora)
                self.assertEqual((rep["released"], rep["reason"]), (False, "backup íntegro? não"))
                self.assertFalse(dest.exists())

    def test_pasta_que_o_sistema_nao_recria_nao_libera_sem_excecao(self):
        # Como 200 letras acentuadas de uma cópia do NTFS restaurada no ext4 (mais de 255 bytes): nome que o sistema de
        # destino recusa. A verificação não sabe o limite do disco de destino; a restauração não libera, com o caminho.
        self.repositorio()
        snap = self.pasta("snap")
        vazias = backup.create_backup(self.root, snap, "nome-longo")["git"]["pastas_vazias"]
        longa = f"{P}/.git/modules/" + "a" * 300
        ancora = self.reescrever_git(snap, pastas_vazias=[*vazias, longa])
        dest = self.pasta("dest")
        rep = backup.restore(snap, dest, self.log, sha256_manifesto=ancora)
        self.assertFalse(rep["released"])
        self.assertIn("não recria", rep["reason"])
        self.assertIn(f"{P}/.git/modules/aaaa", rep["reason"])
        self.assertFalse(dest.exists())


class TestDesastreSemOBanco(Base):
    """Revisão 2 (KIT-F7): no desastre — banco perdido, registro guardado num cofre fora da raiz —, a autorização vem da
    cópia e, antes, nenhuma raiz era conferida: a restauração em <raiz>/restaurada era liberada, com os dados de todos
    os projetos e o banco dentro da raiz. A --raiz com cara de fundação agora conta."""

    def test_cli_sem_o_banco_e_com_o_registro_num_cofre_recusa_destino_na_raiz(self):
        snap = self.pasta("snap")
        ancora = backup.create_backup(self.root, snap, "desastre")["sha256_manifesto"]
        cofre = self.pasta("cofre")
        (cofre / "state").mkdir(parents=True)
        shutil.copy2(self.log, cofre / "state" / "retiradas.jsonl")
        self.con.close()
        os.replace(self.root / "state" / "state.sqlite", self.root / "state" / "state.sqlite.perdido")
        argv = ("--origem", str(snap), "--retiradas", str(cofre / "state" / "retiradas.jsonl"),
                "--sha256-manifesto", ancora)
        dentro = self.root / "restaurada"
        res = rodar_cli(self, "restaurar", *argv, "--destino", str(dentro))
        self.assertEqual(res["autorizacao"]["politica"], "cópia autenticada pela âncora")
        self.assertFalse(res["released"])
        self.assertIn("dentro da raiz", res["reason"])
        self.assertFalse(dentro.exists())
        fora = self.pasta("restaurada-fora")
        res = rodar_cli(self, "restaurar", *argv, "--destino", str(fora))
        self.assertTrue(res["released"], res.get("reason"))


class TestGitDaCopiaRevisao2(Base):
    """Revisão 2 (KIT-F3): o que ainda voltava da cópia e rodava programa ou levava o git à origem, e o que saía dela
    sem motivo (os ramos chamados config)."""
    SHA = "1" * 40 + "\n"
    REGISTRO = "0" * 40 + " " + "1" * 40 + " registro fictício\n"

    def test_alias_com_opcao_global_e_lfs_extension_ficam_fora(self):
        casos = {
            "[alias]\n\tzz = -c diff.external=programa-ficticio diff\n": "alias.zz",
            '[alias]\n\tzz = "-c \\"alias.ww=!programa-ficticio\\" ww"\n': "alias.zz",
            '[alias]\n\tzz = \\"-c\\" core.pager=programa-ficticio log\n': "alias.zz",
            "[alias]\n\tzz = --exec-path=/pasta-ficticia zz\n": "alias.zz",
            "[alias]\n\tzz = --config-env=core.pager=VARIAVEL log\n": "alias.zz",
            '[lfs "extension.marca"]\n\tclean = programa-ficticio %f\n': "lfs.clean",
            "[lfs.extension.marca]\n\tsmudge = programa-ficticio %f\n": "lfs.smudge",
            '[lfs "Extension.marca"]\n\tclean = programa-ficticio %f\n': "lfs.clean",
        }
        for texto, chave in casos.items():
            with self.subTest(texto=texto[:50]):
                self.assertEqual(manutencao.motivo_do_config(texto), f"programa configurado ({chave})")
        for texto in ("[alias]\n\tlg = log --oneline --graph\n", '[lfs "extension.marca"]\n\tpriority = 0\n',
                      "[lfs]\n\turl = https://exemplo.invalid/lfs\n"):
            with self.subTest(texto=texto[:50]):
                self.assertIsNone(manutencao.motivo_do_config(texto))

    def test_rebase_em_andamento_fica_fora_e_contado(self):
        w, todo = P + "/.git/worktrees/w", "exec programa-ficticio\n"
        self.escrever({P + "/.git/HEAD": self.SHA, P + "/.git/rebase-merge/git-rebase-todo": todo,
                       P + "/.git/rebase-merge/interactive": "", P + "/.git/REBASE-APPLY/next": "1\n",
                       w + "/HEAD": self.SHA, w + "/commondir": "../..\n", w + "/rebase-merge/git-rebase-todo": todo,
                       P + "/.git/refs/heads/rebase-merge/ramo": self.SHA})  # ramo chamado rebase-merge/...: entra
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "rebase")
        caminhos = {f["path"] for f in m["files"]}
        self.assertEqual([c for c in caminhos if "/rebase-" in c.lower() and "/refs/" not in c], [])
        self.assertIn(P + "/.git/refs/heads/rebase-merge/ramo", caminhos)
        self.assertEqual(m["git"]["operacoes_fora"], 4)
        self.assertEqual([p for p in m["git"]["pastas_vazias"] if "/rebase-" in p.lower() and "/refs/" not in p], [])
        self.assertTrue(backup.verify_backup(snap)["ok"])
        dest = self.pasta("dest")
        self.assertTrue(backup.restore(snap, dest, self.log)["released"])
        for pasta in (P + "/.git/rebase-merge", P + "/.git/REBASE-APPLY", w + "/rebase-merge"):
            self.assertFalse((dest / pasta).exists(), pasta)

    def test_ponteiros_com_caminho_absoluto_ficam_fora_e_os_relativos_entram(self):
        w, v = P + "/.git/worktrees/w", P + "/.git/worktrees/v"
        self.escrever({P + "/.git/HEAD": self.SHA, w + "/HEAD": self.SHA, v + "/HEAD": self.SHA,
                       w + "/commondir": (self.root / P / ".git").as_posix() + "\n",
                       w + "/gitdir": str(self.root / P / "w" / ".git") + "\n",
                       P + "/w/.git": "gitdir: " + str(self.root / w) + "\n",
                       v + "/commondir": "../..\n", v + "/gitdir": "../../../v/.git\n",  # git worktree --relative-paths
                       P + "/v/.git": "gitdir: ../.git/worktrees/v\n"})
        m = backup.create_backup(self.root, self.pasta("snap"), "ponteiros")
        caminhos = {f["path"] for f in m["files"]}
        fora = {e["caminho"]: e["motivo"] for e in m["git"]["config_fora"]}
        self.assertEqual(sorted(fora), sorted([w + "/commondir", w + "/gitdir", P + "/w/.git"]))
        self.assertEqual(set(fora.values()), {config_git.ABSOLUTO})
        self.assertLessEqual({v + "/commondir", v + "/gitdir", P + "/v/.git"}, caminhos)

    def test_ramos_etiqueta_e_registro_chamados_config_entram(self):
        nomes = ("feature/config", "fix/config.worktree", "feature/commondir", "feature/gitdir")
        refs = {**{f"{P}/.git/refs/heads/{n}": self.SHA for n in nomes},
                **{f"{P}/.git/logs/refs/heads/{n}": self.REGISTRO for n in nomes},
                f"{P}/.git/refs/tags/config": self.SHA, f"{P}/.git/refs/remotes/origin/config": self.SHA,
                f"{P}/.git/modules/s/refs/heads/config": self.SHA}  # no gitdir do submódulo também
        self.escrever({P + "/.git/HEAD": "ref: refs/heads/main\n", P + "/.git/config": "[core]\n\tbare = false\n",
                       P + "/.git/modules/s/HEAD": self.SHA, **refs})
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "refs-chamadas-config")
        self.assertLessEqual(set(refs) | {P + "/.git/config"}, {f["path"] for f in m["files"]})
        self.assertEqual(m["git"]["config_fora"], [])
        self.assertTrue(backup.verify_backup(snap)["ok"])
        dest = self.pasta("dest")
        self.assertTrue(backup.restore(snap, dest, self.log)["released"])
        for rel in refs:
            self.assertEqual((dest / rel).read_bytes(), (self.root / rel).read_bytes(), rel)

    @unittest.skipUnless(GIT, "git ausente: a parte com o git real fica pulada")
    def test_com_git_ramos_e_etiqueta_chamados_config_voltam_iguais(self):
        git = Git(self)
        repo = self.root / P / "codigo"
        git.novo(repo)
        for n in range(64):  # o caso que saía da cópia: a ref solta com o hash começando por dígito
            if git(repo, "rev-parse", "HEAD").stdout.strip()[:1].isdigit():
                break
            git(repo, "commit", "-q", "--allow-empty", "-m", f"vazio {n}")
        for ramo in ("feature/config", "fix/config.worktree", "feature/commondir", "outro"):
            git(repo, "branch", ramo)
        git(repo, "tag", "config")
        if not (repo / ".git" / "refs" / "heads" / "feature" / "config").is_file():
            self.skipTest("git sem refs soltas (reftable por padrão)")
        origem = git(repo, "for-each-ref").stdout
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "refs-git")
        self.assertTrue(backup.verify_backup(snap)["ok"])
        dest = self.pasta("dest")
        self.assertTrue(backup.restore(snap, dest, self.log)["released"])
        self.assertEqual(git(dest / P / "codigo", "for-each-ref").stdout, origem)
        self.assertEqual(m["git"]["config_fora"], [])

    @unittest.skipUnless(GIT, "git ausente: a parte com o git real fica pulada")
    def test_com_git_alias_com_opcao_global_nao_volta(self):
        git = Git(self)
        repo = self.root / P / "codigo"
        git.novo(repo)
        marca = git.base / "alias-rodou.txt"
        valor = "-c \"alias.ww=!echo rodou > '" + marca.as_posix() + "'\" ww"  # o valor que o git lê
        with open(repo / ".git" / "config", "a", encoding="utf-8", newline="\n") as config:
            config.write('[alias]\n\tzz = "' + valor.replace('"', '\\"') + '"\n')
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "alias-git")
        dest = self.pasta("dest")
        self.assertTrue(backup.restore(snap, dest, self.log)["released"])
        git(dest / P / "codigo", "zz", codigo=None)
        self.assertFalse(marca.exists(), "o alias com -c voltou com a restauração e rodou")
        self.assertIn(P + "/codigo/.git/config", {e["caminho"] for e in m["git"]["config_fora"]})
        git(repo, "zz", codigo=None)  # guarda: na origem, o mesmo alias roda (a sonda vale)
        self.assertTrue(marca.exists(), "o alias não rodou nem na origem: o teste não prova nada")

    @unittest.skipUnless(GIT, "git ausente: a parte com o git real fica pulada")
    def test_com_git_lfs_extension_nao_roda_no_status_da_restaurada(self):
        git = Git(self)
        if git(git.base, "lfs", "version", codigo=None).returncode != 0:
            self.skipTest("git-lfs ausente")
        sistema = git.base / "gitconfig-lfs"  # como o filter.lfs que o Git for Windows põe no config do sistema
        sistema.write_text('[filter "lfs"]\n\tclean = git-lfs clean -- %f\n\tsmudge = git-lfs smudge -- %f\n'
                           "\tprocess = git-lfs filter-process\n\trequired = true\n", encoding="utf-8")
        git.env["GIT_CONFIG_GLOBAL"] = str(sistema)
        repo = self.root / P / "codigo"
        repo.mkdir(parents=True)
        git(repo, "init", "-q")
        (repo / ".gitattributes").write_text("*.bin filter=lfs diff=lfs merge=lfs -text\n", encoding="utf-8")
        (repo / "a.bin").write_bytes(b"conteudo binario ficticio\n")
        git(repo, "add", ".gitattributes", "a.bin")
        git(repo, "commit", "-qm", "um")
        marca, script = git.base / "extensao-rodou.txt", git.base / "marca.sh"
        if " " in script.as_posix():
            self.skipTest("o git-lfs separa o comando da extensão nos espaços, sem aspas")
        script.write_bytes(("echo rodou > '" + marca.as_posix() + "'\ncat\n").encode("utf-8"))
        for nome in ("clean", "smudge"):
            git(repo, "config", f"lfs.extension.marca.{nome}", f"sh {script.as_posix()} %f")
        git(repo, "config", "lfs.extension.marca.priority", "0")
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "lfs-git")
        dest = self.pasta("dest")
        self.assertTrue(backup.restore(snap, dest, self.log)["released"])
        git(dest / P / "codigo", "status", "--porcelain", codigo=None)
        self.assertFalse(marca.exists(), "a extensão do git-lfs voltou com a restauração e rodou no git status")
        self.assertIn(P + "/codigo/.git/config", {e["caminho"] for e in m["git"]["config_fora"]})
        # Guarda: na origem, com a data mudada e o mesmo conteúdo (como o arquivo restaurado), o git status a roda.
        st = os.stat(repo / "a.bin")
        os.utime(repo / "a.bin", ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
        git(repo, "status", "--porcelain", codigo=None)
        self.assertTrue(marca.exists(), "a extensão não rodou nem na origem: o teste não prova nada")

    @unittest.skipUnless(GIT, "git ausente: a parte com o git real fica pulada")
    def test_com_git_rebase_parado_com_exec_nao_volta(self):
        git = Git(self)
        repo = self.root / P / "codigo"
        git.novo(repo)
        (repo / "b.txt").write_text("dois\n", encoding="utf-8")
        git(repo, "add", "b.txt")
        git(repo, "commit", "-qm", "dois")
        marca = git.base / "rebase-rodou.txt"
        r = git(repo, "-c", "sequence.editor=true", "rebase", "-i", "--exec", "false", "--exec",
                "echo rodou > '" + marca.as_posix() + "'", "HEAD~1", codigo=None)  # para no `exec false`
        self.assertTrue((repo / ".git" / "rebase-merge" / "git-rebase-todo").is_file(), r.stderr)
        self.assertFalse(marca.exists())
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "rebase-git")
        dest = self.pasta("dest")
        self.assertTrue(backup.restore(snap, dest, self.log)["released"])
        restaurado = dest / P / "codigo"
        git(restaurado, "rebase", "--continue", codigo=None)
        self.assertFalse(marca.exists(), "o exec do rebase parado voltou com a restauração e rodou")
        self.assertFalse((restaurado / ".git" / "rebase-merge").exists())
        self.assertGreater(m["git"]["operacoes_fora"], 0)

    @unittest.skipUnless(GIT, "git ausente: a parte com o git real fica pulada")
    def test_com_git_worktree_restaurada_nao_leva_a_origem(self):
        git = Git(self)
        repo = self.root / P / "codigo"
        git.novo(repo)
        git(repo, "worktree", "add", "-q", "../arvore")
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "worktree-git")
        dest = self.pasta("dest")
        self.assertTrue(backup.restore(snap, dest, self.log)["released"])
        marca = git.base / "gancho-da-origem.txt"  # o gancho gravado depois no repositório VIVO
        gancho = repo / ".git" / "hooks" / "pre-commit"
        gancho.parent.mkdir(exist_ok=True)
        gancho.write_bytes(("#!/bin/sh\necho rodou > '" + marca.as_posix() + "'\n").encode("utf-8"))
        gancho.chmod(0o755)
        antes = git(repo, "for-each-ref").stdout
        restaurada = dest / P / "arvore"
        (restaurada / "b.txt").write_text("dois\n", encoding="utf-8")
        git(restaurada, "add", "b.txt", codigo=None)
        git(restaurada, "commit", "-qm", "na-restaurada", codigo=None)
        self.assertFalse(marca.exists(), "o commit na árvore restaurada rodou o gancho da origem")
        self.assertEqual(git(repo, "for-each-ref").stdout, antes, "o commit na árvore restaurada gravou na origem")
        fora = {e["caminho"]: e["motivo"] for e in m["git"]["config_fora"]}
        self.assertEqual(fora.get(P + "/arvore/.git"), config_git.ABSOLUTO)
        self.assertEqual(fora.get(P + "/codigo/.git/worktrees/arvore/gitdir"), config_git.ABSOLUTO)


# ------------------------------------------------------------------ correções da revisão 3
class TestPuloDoTesteDoReftable(unittest.TestCase):
    """Revisão 3 (os testes com o git real): o teste do reftable pulava em qualquer falha do `git init
    --ref-format=reftable`. Com o TEMP longo, o git 2.56 do Windows falhava com 'I/O error' e o teste saía pulado
    como 'anterior ao 2.45', escondendo a falha. Agora pula só quando o git não conhece o formato; senão, falha."""

    def test_pula_so_quando_o_git_nao_conhece_o_formato(self):
        self.assertTrue(git_sem_reftable((2, 43), "error: unknown option `ref-format=reftable'"))
        self.assertTrue(git_sem_reftable((2, 44), "fatal: unknown ref storage format 'reftable'"))
        self.assertTrue(git_sem_reftable(None, "error: unknown option `ref-format=reftable'"))
        for versao in ((2, 45), (2, 56), (3, 0)):
            with self.subTest(versao=versao):
                self.assertFalse(git_sem_reftable(versao, "error: reftable: transaction failure: I/O error"))
        self.assertFalse(git_sem_reftable(None, "fatal: cannot mkdir .git: Filename too long"))

    @unittest.skipUnless(GIT, "git ausente: o teste do reftable fica pulado inteiro")
    def test_init_que_falha_num_git_que_conhece_o_formato_falha_o_teste(self):
        # O próprio teste do reftable, com o `git init` falhando (simulado): falha num git que conhece o formato, pula
        # num git anterior ao 2.45. Com a regra antiga (pular em qualquer falha), o primeiro caso saía pulado.
        casos = {((2, 56), "error: reftable: transaction failure: I/O error\n"): (1, 0),
                 ((2, 43), "error: unknown option `ref-format=reftable'\n"): (0, 1)}
        for (versao, erro), esperado in casos.items():
            with self.subTest(versao=versao):
                teste = TestPastasVaziasQueAVerificacaoAceita(
                    "test_com_git_repositorio_reftable_verifica_e_volta_funcionando")
                resultado = unittest.TestResult()
                falhou = subprocess.CompletedProcess([GIT, "init"], 1, "", erro)
                with mock.patch.object(Git, "__call__", return_value=falhou), \
                        mock.patch.object(Git, "versao", return_value=versao):
                    teste.run(resultado)
                self.assertEqual(resultado.errors, [])
                self.assertEqual((len(resultado.failures), len(resultado.skipped)), esperado, resultado.failures)


if __name__ == "__main__":
    unittest.main()
