"""Revisão de segurança da 1.7.10, grupo KITCOPIA: as regras que o kit repete (ele não importa os scripts da skill) dão
o mesmo RESULTADO que as da skill sobre os mesmos casos — não só as mesmas listas.

- KIT-F3: `fundacao/core/config_git.py` (o que o .git leva na cópia) e `scripts/git_projeto.py`: `motivo_da_chave` dá
  o mesmo motivo para cada chave; `ler_config` dá as mesmas entradas que o próprio git (`git config --file
  --no-includes --null --list`, pelo `ler_configuracao` do git_projeto) e o mesmo veredito (roda programa ou não),
  também nos textos que escondiam a seção do leitor antigo do kit (BOM, continuação de linha, separador de linha do
  Unicode); o que o git recusa, o kit deixa fora. Correções da revisão 2: alias com opção global do git (-c) e
  lfs.extension.<x>.clean/smudge nos casos.
- KIT-F6: `manutencao.com_cara_de_segredo` (segredos_incluidos) e `regras_de_segredo.classificar` (forte ou pasta de
  segredo), com NFKC, sem caixa, pasta no fim do caminho, exemplo de segredo e barra invertida.
- KIT-F2: `regras_da_copia.motivo_da_politica` do kit e `_rel_incluida_segura` do atualizar_fundacao.py aceitam e
  recusam os mesmos caminhos da política de backup (State, STATE, state., state , ., ./state, x/../state, ligação).
- KIT-F7 (correções da revisão 1): `ancora_copia.dentro_da_copia` do kit e `_dentro_da_raiz` do atualizador dizem o
  mesmo sobre a pasta das cópias (--backups) dentro ou fora da raiz, também por ligação e, no Windows, por outra caixa.
O kit roda num processo à parte (python -I, com a pasta do kit no caminho): importar o pacote do kit aqui misturaria o
`fundacao` de outras raízes de teste. Sem git, a parte com o git real fica pulada.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import KIT, SCRIPTS, criar_ligacao_dir


def carregar(nome: str, arquivo: str):
    spec = importlib.util.spec_from_file_location(nome, SCRIPTS / arquivo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


GIT_PROJETO = carregar("_iguais_git_projeto", "git_projeto.py")
REGRAS = carregar("_iguais_regras_de_segredo", "regras_de_segredo.py")


def no_kit(codigo: str, dados) -> object:
    """Roda `codigo` com o pacote do kit num processo à parte (python -I -B): `dados` chega em JSON e o código devolve
    `resultado`, que volta em JSON."""
    inicio = "import base64, json, sys\nsys.path.insert(0, sys.argv[1])\ndados = json.loads(sys.stdin.read())\n"
    r = subprocess.run([sys.executable, "-I", "-B", "-c", inicio + codigo + "\nprint(json.dumps(resultado))",
                        str(KIT)], input=json.dumps(dados), capture_output=True, text=True, encoding="utf-8",
                       timeout=180)
    if r.returncode != 0:
        raise AssertionError(f"o código do kit falhou: {r.stderr[-2000:]}")
    return json.loads(r.stdout)


# ------------------------------------------------------------------ KIT-F3
CHAVES = [
    ("core.hookspath", "/dev/null"), ("core.hookspath", " /dev/null "), ("core.hookspath", "/tmp/ganchos"),
    ("core.hookspath", None), ("core.hookspath", ""), ("core.fsmonitor", "false"), ("core.fsmonitor", "FALSE"),
    ("core.fsmonitor", "0"), ("core.fsmonitor", "no"), ("core.fsmonitor", "off"), ("core.fsmonitor", ""),
    ("core.fsmonitor", None), ("core.fsmonitor", "true"), ("core.fsmonitor", ".git/monitor"),
    *[(f"core.{n}", "programa") for n in ("sshcommand", "editor", "pager", "askpass", "gitproxy",
                                          "alternaterefscommand")],
    ("core.worktree", "/tmp/fora"), ("core.autocrlf", "input"), ("core.bare", "false"), ("CORE.SSHCOMMAND", "x"),
    ("sequence.editor", "x"), ("diff.external", "x"), ("interactive.difffilter", "x"),
    ("uploadpack.packobjectshook", "x"), ("web.browser", "x"), ("sendemail.sendmailcmd", "x"),
    ("diff.command", "x"), ("diff.lfs.command", "x"), ("diff.lfs.textconv", "x"), ("diff.textconv", "x"),
    ("merge.driver", "x"), ("merge.ours.driver", "x"), ("merge.ours.name", "x"), ("filter.lfs.clean", "x"),
    ("filter.lfs.smudge", "x"), ("filter.lfs.process", "x"), ("filter.lfs.required", "true"), ("filter.clean", "x"),
    ("credential.helper", "store"), ("credential.helper", ""), ("credential.helper", None),
    ("credential.https://exemplo.invalid.helper", "h"), ("credential.username", "x"), ("include.path", "outro.cfg"),
    ("includeif.gitdir:/x/.path", "y.cfg"), ("includeif.onbranch:main.path", "z"),
    ("url.ext::sh -c x.insteadof", "https://"), ("url.file:///tmp/r.insteadof", "https://"),
    ("url./tmp/r.pushinsteadof", "https://"), ("url.C:/r.insteadof", "https://"), ("url.~/r.insteadof", "x"),
    ("url.https://espelho.invalid/.insteadof", "https://"), ("url.\u212a:/r.insteadof", "x"),
    ("gpg.program", "g"), ("gpg.ssh.program", "g"), ("gpg.x509.program", "g"), ("gpg.ssh.defaultkeycommand", "c"),
    ("gpg.format", "ssh"), ("tar.tgz.command", "gzip"), ("sendemail.tocmd", "x"), ("sendemail.cccmd", "x"),
    ("sendemail.headercmd", "x"), ("guitool.x.cmd", "x"), ("pager.log", "less"), ("pager.log", "false"),
    ("pager.log", "true"), ("pager.log", "1"), ("pager.log", ""), ("pager.log", None), ("pager.branch", "off"),
    ("alias.x", "!sh"), ("alias.x", " !sh"), ("alias.st", "status"), ("alias.y", None), ("difftool.x.cmd", "c"),
    ("difftool.x.path", "p"), ("mergetool.x.cmd", "c"), ("mergetool.x.path", "p"), ("browser.x.cmd", "c"),
    ("browser.x.path", "p"), ("man.x.cmd", "c"), ("man.x.path", "p"), ("man.viewer", "x"),
    ("remote.origin.uploadpack", "u"), ("remote.origin.receivepack", "r"), ("remote.origin.vcs", "v"),
    ("remote.origin.url", "ext::sh -c x"), ("remote.origin.url", "fd::1"),
    ("remote.origin.url", "https://exemplo.invalid/r.git"), ("remote.origin.pushurl", "EXT::x"),
    ("remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*"), ("submodule.s.update", "!sh"),
    ("submodule.s.update", "checkout"), ("submodule.s.update", "rebase"), ("protocol.allow", "always"),
    ("protocol.allow", "user"), ("protocol.allow", "never"), ("protocol.ext.allow", "user"),
    ("protocol.ext.allow", "never"), ("protocol.fd.allow", "always"), ("protocol.file.allow", "always"),
    ("protocol.EXT.allow", "always"), ("sendemail.smtpserver", "/usr/bin/x"),
    ("sendemail.smtpserver", "smtp.exemplo.invalid"), ("trailer.x.command", "c"), ("trailer.x.cmd", "c"),
    ("trailer.x.key", "k"), ("lfs.customtransfer.x.path", "p"), ("lfs.customtransfer.x.args", "a"),
    ("lfs.x.path", "p"), ("hook.x.command", "c"), ("hook.x.event", "pre-commit"), ("hook.command", "c"),
    ("user.name", "x"), ("", None), ("semsecao", "x"),
    # Correções da revisão 2 (KIT-F3): alias que começa por opção global do git (também entre aspas ou com \) e a
    # extensão do git-lfs rodam programa; alias comum e as outras chaves do lfs, não.
    ("alias.zz", "-c diff.external=x diff"), ("alias.zz", '"-c" x'), ("alias.zz", "'-c' x"), ("alias.zz", "\\-c x"),
    ("alias.zz", "--exec-path=/x zz"), ("alias.zz", "--config-env=core.pager=V log"), ("alias.zz", " -p log"),
    ("alias.lg", "log --oneline --graph"), ("alias.zz", "diff -- -c"), ("lfs.extension.marca.clean", "x %f"),
    ("lfs.extension.marca.smudge", "x %f"), ("lfs.Extension.marca.clean", "x"), ("lfs.extension.marca.priority", "0"),
    ("lfs.extension.clean", "x"), ("lfs.url", "https://exemplo.invalid/lfs"),
]

TEXTOS = [
    b"[core]\n\trepositoryformatversion = 0\n\tbare = false\n\thooksPath = /dev/null\n\tfsmonitor = false\n",
    b'[hook "marca"]\n\tcommand = programa-ficticio\n\tevent = pre-commit\n',
    b"[alias]\n\tx = !programa-ficticio\n\tst = status\n",
    b'[submodule "s"]\n\tupdate = !programa-ficticio\n\turl = ../s.git\n',
    b"\xef\xbb\xbf[core]\n\tsshCommand = programa-ficticio\n",
    "[core]\n\tx = a\u0085[user]\n\tsshCommand = programa-ficticio\n".encode("utf-8"),
    "[core]\n\tx = a\u2028[user]\n\tsshCommand = programa-ficticio\n".encode("utf-8"),
    b"[core]\n\tx = a \\\n[user]\n\tsshCommand = programa-ficticio\n",
    b"[core]\r\n\tsshCommand = programa-ficticio\r\n",
    b"[core]\r\tsshCommand = programa-ficticio\r",
    b"[core] sshCommand = programa-ficticio\n",
    b"[hook.Marca]\n\tcommand = programa-ficticio\n",
    b'[hook "a\\"b]c"]\n\tcommand = programa-ficticio\n',
    b'[alias]\n\tx = "!programa-ficticio" # comentario\n',
    b"[CORE]\n\tSSHCOMMAND = programa-ficticio\n",
    b"chave = valor\n",
    b'[ "x"]\n\tk = v\n',
    b"[core]\n\tbare",
    b"[a]\n\tb = x\t y  \n",
    b"[a]\n\tb\t =\t x\n",
    b"[a.]\n\tb = x\n",
    b'[a.b "c"]\n\td = x\n',
    b'[remote "origin"]\n\turl = https://exemplo.invalid/r.git\n\tfetch = +refs/heads/*:refs/remotes/origin/*\n',
    b'[includeIf "gitdir:~/x/"]\n\tpath = outra.config\n',
    b'[url "ext::programa-ficticio"]\n\tinsteadOf = https://exemplo.invalid/\n',
    b"[diff]\n\texternal = programa-ficticio\n",
    b"# comentario\n; outro\n[core]\n\tbare = false ; fim\n",
    b'[pager]\n\tlog = "less -R"\n',
    b'[alias]\n\tzz = "-c \\"alias.ww=!programa-ficticio\\" ww"\n',  # revisão 2: alias com opção global
    b'[alias]\n\tzz = \\"-c\\" core.pager=programa-ficticio log\n', b"[alias]\n\tlg = log --oneline --graph\n",
    b'[lfs "extension.marca"]\n\tclean = programa-ficticio %f\n\tpriority = 0\n', b"[lfs]\n\turl = x\n",
    # O que o git recusa (o kit deixa o config fora):
    b"\xef\xbb[core]\n", b"[core]\x0b\tsshCommand = x\n", b"[core]\n\teditor = a\\q\n", b"[]\n\tk = v\n",
    b'[core]\n\teditor = "a\n', b"[a]\n\tb.c = x\n", b'[a "b" ]\n\tc = x\n',
]


class TestRegraDoGitIgualAoGitProjeto(unittest.TestCase):
    def test_motivo_da_chave_igual_sobre_os_mesmos_casos(self):
        kit = no_kit("from fundacao.core import config_git\n"
                     "resultado = [config_git.motivo_da_chave(c, v) for c, v in dados]", CHAVES)
        skill = [GIT_PROJETO.motivo_da_chave(c, v) for c, v in CHAVES]
        self.assertEqual(len(kit), len(CHAVES))
        for caso, a, b in zip(CHAVES, kit, skill):
            with self.subTest(caso=caso):
                self.assertEqual(a, b)
        self.assertGreater(sum(1 for m in skill if m), 60, "casos que rodam programa de menos para valer")

    def test_alias_com_opcao_global_e_lfs_extension_rodam_nas_duas(self):
        # Correções da revisão 2 (KIT-F3): iguais não basta — as duas regras acusam o alias que começa por opção global
        # do git (o -c injeta qualquer config) e a extensão do git-lfs (roda no primeiro git status), não o alias comum.
        rodam = [("alias.zz", "-c diff.external=x diff"), ("alias.zz", '"-c" x'), ("alias.zz", "\\-c x"),
                 ("alias.zz", "--exec-path=/x zz"), ("lfs.extension.marca.clean", "x %f"),
                 ("lfs.extension.marca.smudge", "x %f"), ("lfs.Extension.marca.clean", "x")]
        nao_rodam = [("alias.lg", "log --oneline --graph"), ("alias.zz", "diff -- -c"),
                     ("lfs.extension.marca.priority", "0"), ("lfs.url", "https://exemplo.invalid/lfs")]
        kit = no_kit("from fundacao.core import config_git\n"
                     "resultado = [config_git.motivo_da_chave(c, v) for c, v in dados]", rodam + nao_rodam)
        for (chave, valor), do_kit in zip(rodam + nao_rodam, kit):
            with self.subTest(chave=chave, valor=valor):
                da_skill = GIT_PROJETO.motivo_da_chave(chave, valor)
                self.assertEqual(do_kit, da_skill)
                self.assertEqual(da_skill is not None, (chave, valor) in rodam)

    @unittest.skipUnless(shutil.which("git"), "git ausente: a leitura do git real fica pulada")
    def test_leitura_e_veredito_iguais_aos_do_git(self):
        kit = no_kit("from fundacao.core import config_git\n"
                     "brutos = [base64.b64decode(t) for t in dados]\n"
                     "resultado = [[config_git.ler_config(b), config_git.motivo_do_config(b)] for b in brutos]",
                     [base64.b64encode(t).decode("ascii") for t in TEXTOS])
        pasta = Path(tempfile.mkdtemp(prefix="config-git-iguais-"))
        self.addCleanup(shutil.rmtree, pasta, True)
        with GIT_PROJETO.Git() as git:
            for i, (texto, (itens, motivo)) in enumerate(zip(TEXTOS, kit)):
                with self.subTest(texto=texto[:40]):
                    arquivo = pasta / f"caso-{i}"
                    arquivo.write_bytes(texto)
                    try:
                        do_git = GIT_PROJETO.ler_configuracao(git, arquivo)
                    except GIT_PROJETO.Recusa:
                        do_git = None
                    if do_git is None:
                        self.assertIsNone(itens, "o git recusa o arquivo e o kit o leu")
                        self.assertIsNotNone(motivo, "config que o git recusa entrou na cópia")
                        continue
                    self.assertIsNotNone(itens, "o kit recusou o que o git lê")
                    # O git 2.43 troca cada espaço de dentro do valor por ' '; o 2.45 em diante guarda o caractere.
                    normal = [(c, v.replace("\t", " ").replace("\r", " ") if v else v) for c, v in itens]
                    self.assertEqual(normal, [(c, v.replace("\t", " ").replace("\r", " ") if v else v)
                                              for c, v in do_git])
                    self.assertEqual(motivo is not None, bool(GIT_PROJETO.chaves_que_rodam(do_git)), motivo)


# ------------------------------------------------------------------ KIT-F6
CAMINHOS = [
    "projects/p/\uff49\uff44_\uff52\uff53\uff41", "projects/p/\uff29\uff24_\uff32\uff33\uff21",
    "projects/p/.\uff53\uff53\uff48/config", "projects/p/.pgpa\u00df", "projects/p/.\u017f\u017fh/config",
    "projects/p/.docker", "projects/p/.aws", "projects/p/\ufb01le.pem", "projects/p/\u212a.txt",
    "projects/p/\uff53\uff45\uff43\uff52\uff45\uff54.txt", "projects/p/x.\uff50\uff45\uff4d",
    ".env", ".env.local", ".env.example", "x.example", "x.sample", "secret.sample", "id_rsa.pub", "README.md",
    "tokenizer.py", "src/secret_santa.py", "credentials_test.py", "projects/p/.git/config", "a\\.ssh\\id",
    "a/.SSH/x", ".netrc", "_netrc", "kubeconfig-x", "service-account-x.json", "x.tfstate.backup", "x.kdbx",
    "segredos", "dados/segredos/x", "Secrets/y", "x/.Omniroute/z", "_browser_profile/c", "auth.json", "AUTH.JSON",
    "chave.KEY", "x.p8", "x.ovpn", ".git-credentials", ".npmrc", ".pypirc", ".htpasswd", "a/./b/.env", "", ".",
    "a/../.ssh/x", "notas/senha.txt", "x.token", ".mcp.json",
]


class TestSegredoIgualARegraUnica(unittest.TestCase):
    def test_com_cara_de_segredo_igual_a_forte_ou_pasta_da_canonica(self):
        kit = no_kit("from fundacao.core import manutencao\n"
                     "resultado = {'contagem': [manutencao.com_cara_de_segredo(c) for c in dados],\n"
                     "             'exemplos': list(manutencao.EXEMPLOS_DE_SEGREDO)}", CAMINHOS)
        self.assertEqual(kit["exemplos"], list(REGRAS.EXEMPLOS_DE_SEGREDO))
        for caminho, conta in zip(CAMINHOS, kit["contagem"]):
            with self.subTest(caminho=caminho):
                self.assertEqual(conta, REGRAS.classificar(caminho) in ("forte", "pasta-de-segredo"))
        self.assertGreater(sum(kit["contagem"]), 25)


# ------------------------------------------------------------------ KIT-F2
POLITICAS = ["docs", "evidence/x", "em-uso", ".claude/projetos", "notas/./a", "Docs", "estado", "State", "STATE",
             "state.", "state ", ".", "./", "./state", "x/../state", "state", "state/x", ".git", ".GIT", ".git.",
             ".git/y", "..", "../fora", "...", ". ", "a/../b", "C:/x", "C:x", "/abs", "\\abs", "state::$DATA", "a:b",
             "", "   ", "docs\\..\\state", "atalho/sub", "externo/sub", "atalho"]


class TestFiltroDoAtualizador(unittest.TestCase):
    def test_incluidos_pula_state_e_git_em_qualquer_grafia(self):
        atualizador = carregar("_iguais_atualizar_filtro", "atualizar_fundacao.py")
        base = Path(tempfile.mkdtemp(prefix="politica-atualizador-"))
        self.addCleanup(shutil.rmtree, base, True)
        for rel in ("state/retiradas.jsonl", "state/nota-ficticia.txt", "modelos/peso.bin"):
            (base / rel).parent.mkdir(parents=True, exist_ok=True)
            (base / rel).write_text("x", encoding="utf-8")
        (base / "registry").mkdir()
        incluir = ["modelos", "State", "STATE", "state.", "state ", ".", "./state", "x/../state", ".GIT", "./"]
        (base / "registry" / "backup_policy.json").write_text(json.dumps({"incluir": incluir}), encoding="utf-8")
        self.assertEqual(atualizador._incluidos(base), ["modelos"])
        self.assertEqual(atualizador.contar_arquivos(base), 2)  # a política e o peso: nada de state/


class TestPoliticaIgualAoAtualizador(unittest.TestCase):
    def test_kit_e_atualizador_aceitam_e_recusam_os_mesmos_caminhos(self):
        base = Path(tempfile.mkdtemp(prefix="politica-iguais-"))
        self.addCleanup(shutil.rmtree, base, True)
        raiz, fora = base / "raiz", base / "fora"
        for pasta in (raiz / "state" / "sub", raiz / "docs", fora / "sub"):
            pasta.mkdir(parents=True)
        criar_ligacao_dir(raiz / "atalho", raiz / "state")
        criar_ligacao_dir(raiz / "externo", fora)
        atualizador = carregar("_iguais_atualizar", "atualizar_fundacao.py")
        kit = no_kit("from pathlib import Path\nfrom fundacao.core import regras_da_copia\n"
                     "resultado = [regras_da_copia.motivo_da_politica(r, Path(dados['raiz'])) is None\n"
                     "             for r in dados['casos']]", {"raiz": str(raiz), "casos": POLITICAS})
        for caso, aceito in zip(POLITICAS, kit):
            with self.subTest(caso=caso):
                self.assertEqual(aceito, atualizador._rel_incluida_segura(caso, raiz))
        recusados = {c for c, aceito in zip(POLITICAS, kit) if not aceito}
        self.assertLessEqual({"State", "STATE", "state.", "state ", ".", "./state", "x/../state", "atalho/sub",
                              "externo/sub"}, recusados)
        self.assertTrue(all(aceito for c, aceito in zip(POLITICAS, kit) if c in ("docs", "em-uso", ".claude/projetos")))


# ------------------------------------------------------------------ KIT-F7 (correções da revisão 1)
class TestDentroDaRaizIgualAoKit(unittest.TestCase):
    def test_atualizador_e_kit_dizem_o_mesmo_sobre_a_pasta_das_copias(self):
        # O `aplicar` recusa --backups dentro da raiz com a conferência do kit (ancora_copia.dentro_da_copia): caminho
        # resolvido e objeto do disco. Os dois dizem o mesmo sobre os mesmos caminhos.
        base = Path(tempfile.mkdtemp(prefix="dentro-iguais-"))
        self.addCleanup(shutil.rmtree, base, True)
        raiz, fora = base / "raiz", base / "fora"
        for pasta in (raiz / "projects" / "p" / "outputs", fora):
            pasta.mkdir(parents=True)
        criar_ligacao_dir(base / "atalho-para-dentro", raiz / "projects")
        casos = [raiz, raiz / "copias", raiz / "projects" / "p" / "outputs" / "copias", fora / "copias", base,
                 base / "raiz-irma", base / "atalho-para-dentro" / "copias"]
        if os.name == "nt":  # o NTFS não distingue caixa
            casos.append(Path(str(raiz).upper()) / "copias")
        atualizador = carregar("_iguais_dentro", "atualizar_fundacao.py")
        kit = no_kit("from fundacao.core.ancora_copia import dentro_da_copia\n"
                     "resultado = [dentro_da_copia(c, dados['raiz']) for c in dados['casos']]",
                     {"raiz": str(raiz), "casos": [str(c) for c in casos]})
        for caso, dentro in zip(casos, kit):
            with self.subTest(caso=caso):
                self.assertEqual(dentro, atualizador._dentro_da_raiz(caso, raiz))
        self.assertEqual(kit, [True, True, True, False, False, False, True] + ([True] if os.name == "nt" else []))


if __name__ == "__main__":
    unittest.main()
