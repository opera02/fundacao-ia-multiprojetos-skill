"""1.7.10 — o `.git` dos projetos na cópia e a contagem de segredos (desenho 1.7.10, §5.3 e §5.8; MELHORIAS-1.7.10,
§0 item 5 e §1 item 10).

Até a 1.7.9 o backup excluía `.git` em qualquer profundidade, e o manifesto dizia "credenciais não incluídas" enquanto
pastas como `.segredos` e `.envs` entravam. Agora o `.git` entra só dentro de projects/<projeto>/ (fora de data/ e de
pastas reconstruíveis), por cópia crua — o kit não executa git —, sem hooks, sem *.lock e sem config com credencial ou
programa; o manifesto conta os levados e os excluídos, com o motivo. O que tem cara de segredo continua entrando e é
contado, sem leitura. Os repositórios são montados como arquivos (sem git); credenciais montadas em tempo de execução.
"""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from unittest import mock

from helpers import FoundationTestCase

from fundacao.core import backup, manutencao, preparo

USUARIO = "operador"
SEGREDO_NA_URL = "Z" * 6 + "fic" + "ticio"  # valor fictício montado em tempo de execução
ARROBA = "@"  # endereços montados em tempo de execução: a varredura da liberação acusa o que parece e-mail
URL_COM_CREDENCIAL = "https://" + USUARIO + ":" + SEGREDO_NA_URL + ARROBA + "exemplo.invalid/repo.git"
REMOTO_SSH = "git" + ARROBA + "exemplo.invalid:dono/repo.git"  # forma scp, sem credencial


def config_git(url: str, extra: str = "") -> str:
    return ("[core]\n\trepositoryformatversion = 0\n\tbare = false\n" + extra
            + '[remote "origin"]\n\turl = ' + url + "\n\tfetch = +refs/heads/*:refs/remotes/origin/*\n")


class TestRegraDoConfig(unittest.TestCase):
    def test_motivos(self):
        casos = {
            config_git(REMOTO_SSH): None,
            config_git("ssh://git" + ARROBA + "exemplo.invalid/dono/repo.git"): None,
            config_git("https://exemplo.invalid/dono/repo.git"): None,
            # Aperto da revisão de segurança da 1.7.10 (KIT-F3): a regra é a do git_projeto.py, que trata
            # core.fsmonitor = true (o monitor embutido) como programa; antes, aqui, o config entrava.
            config_git("https://exemplo.invalid/repo.git", "\tfsmonitor = true\n"): "programa configurado (core.fsmonitor)",
            config_git(URL_COM_CREDENCIAL): "credencial em URL de remoto",
            config_git("https://" + SEGREDO_NA_URL + ARROBA + "exemplo.invalid/repo.git"):
                "credencial em URL de remoto",
            config_git("ssh://" + USUARIO + ":" + SEGREDO_NA_URL + ARROBA + "exemplo.invalid/r.git"):
                "credencial em URL de remoto",
            '[url "' + URL_COM_CREDENCIAL + '"]\n\tinsteadOf = https://exemplo.invalid/\n':
                "credencial em URL de remoto",
            '[http "https://exemplo.invalid/"]\n\textraheader = AUTHORIZATION: basic ' + SEGREDO_NA_URL + "\n":
                "cabeçalho de autenticação (http.extraheader)",
            config_git("https://exemplo.invalid/r.git", "\tfsmonitor = .git/monitor.sh\n"):
                "programa configurado (core.fsmonitor)",
            config_git("https://exemplo.invalid/r.git", "\thooksPath = ferramentas/ganchos\n"):
                "programa configurado (core.hookspath)",
            '[filter "x"]\n\tsmudge = programa-ficticio %f\n': "programa configurado (filter.smudge)",
            '[includeIf "gitdir:~/x/"]\n\tpath = outra.config\n': "inclusão de outra configuração (includeif.path)",
            '[credential]\n\thelper = store\n': "programa configurado (credential.helper)",
            '[credential]\n\thelper =\n': None,
            # 1.7.10 (#10): chaves que faltavam e a seção pager com qualquer chave.
            '[diff]\n\texternal = programa-ficticio\n': "programa configurado (diff.external)",
            '[remote "origin"]\n\tuploadpack = /usr/bin/programa-ficticio\n': "programa configurado (remote.uploadpack)",
            '[remote "origin"]\n\treceivepack = /usr/bin/programa-ficticio\n':
                "programa configurado (remote.receivepack)",
            '[core]\n\tworktree = /tmp/arvore-ficticia\n': "programa configurado (core.worktree)",
            '[protocol "ext"]\n\tallow = always\n': "programa configurado (protocol.allow)",
            '[pager]\n\tlog = /usr/bin/programa-ficticio\n': "programa configurado (pager.log)",
            '[pager]\n\tbranch = false\n': None,
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto[:60]):
                motivo = manutencao.motivo_do_config(texto)
                self.assertEqual(motivo, esperado)
                if motivo:
                    self.assertNotIn(SEGREDO_NA_URL, motivo, "o motivo não pode trazer o valor")

    def test_cara_de_segredo(self):
        sim = ["projects/p/.segredos/setup_token", "projects/p/.envs/prod", "projects/p/secrets/a.json",
               "projects/p/x/id_rsa", "projects/p/cert.PEM", "projects/p/.env.local", "projects/p/_browser_profile/c",
               "projects/p/Credentials.json", "projects/p/.omniroute/credenciais"]  # .omniroute: 1.7.10 (#9)
        nao = ["projects/p/INSTRUCOES.md", "projects/p/src/tokenizer.py", "projects/p/.git/config", "docs/GUIA.md"]
        for rel in sim:
            self.assertTrue(manutencao.com_cara_de_segredo(rel), rel)
        for rel in nao:
            self.assertFalse(manutencao.com_cara_de_segredo(rel), rel)


class TestGitNaCopia(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.extra = []
        self.log = self.root / "state" / "retiradas.jsonl"

    def tearDown(self):
        for p in self.extra:
            shutil.rmtree(p, ignore_errors=True)
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

    def repositorio(self, base: str, config: str) -> dict:
        return {f"{base}/.git/HEAD": "ref: refs/heads/main\n", f"{base}/.git/config": config,
                f"{base}/.git/objects/ab/cdef0123456789": bytes(range(64)),
                f"{base}/.git/refs/heads/main": "0" * 40 + "\n",
                f"{base}/.git/refs/heads/hooks/ramo-ficticio": "1" * 40 + "\n",  # ramo chamado hooks/...: entra
                f"{base}/.git/hooks/pre-commit": "#!/bin/sh\necho hook fictício\n",
                f"{base}/.git/modules/sub/hooks/post-checkout": "#!/bin/sh\n",
                f"{base}/.git/modules/sub/HEAD": "ref: refs/heads/main\n",
                f"{base}/.git/index.lock": "", f"{base}/.git/refs/heads/main.lock": ""}

    def test_git_dos_projetos_entra_com_as_regras(self):
        p = "projects/juridico-lab"
        self.escrever({
            **self.repositorio(p, config_git(REMOTO_SSH)),
            **self.repositorio(p + "/trabalho/outro", config_git(URL_COM_CREDENCIAL)),
            p + "/data/origem/.git/HEAD": "ref: refs/heads/main\n",
            p + "/venv/src/pacote/.git/HEAD": "ref: refs/heads/main\n",
            "docs/.git/HEAD": "ref: refs/heads/main\n",
            "projects/.git/HEAD": "ref: refs/heads/main\n",
            p + "/arvore/.git": "gitdir: ../.git/worktrees/arvore\n",  # arquivo .git de worktree: entra com o projeto
        })
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "git-1710")
        caminhos = {f["path"] for f in m["files"]}
        for rel in (".git/HEAD", ".git/config", ".git/objects/ab/cdef0123456789", ".git/refs/heads/main",
                    ".git/refs/heads/hooks/ramo-ficticio", ".git/modules/sub/HEAD"):
            self.assertIn(f"{p}/{rel}", caminhos)
        self.assertIn(p + "/arvore/.git", caminhos)
        for rel in (".git/hooks/pre-commit", ".git/modules/sub/hooks/post-checkout", ".git/index.lock",
                    ".git/refs/heads/main.lock"):
            self.assertNotIn(f"{p}/{rel}", caminhos)
        self.assertIn(p + "/trabalho/outro/.git/HEAD", caminhos)
        self.assertNotIn(p + "/trabalho/outro/.git/config", caminhos, "config com credencial entrou")
        for fora in (p + "/data/origem/.git/HEAD", p + "/venv/src/pacote/.git/HEAD", "docs/.git/HEAD",
                     "projects/.git/HEAD"):
            self.assertNotIn(fora, caminhos)
        git = m["git"]
        self.assertEqual(git["levados"], sorted([p + "/.git", p + "/arvore/.git", p + "/trabalho/outro/.git"]))
        motivos = {e["caminho"]: e["motivo"] for e in git["excluidos"]}
        self.assertIn("data/", motivos[p + "/data/origem/.git"])
        self.assertIn("reconstruível", motivos[p + "/venv/src/pacote/.git"])
        self.assertIn("fora de projects", motivos["docs/.git"])
        self.assertIn("fora de projects", motivos["projects/.git"])
        self.assertEqual(git["config_fora"], [{"caminho": p + "/trabalho/outro/.git/config",
                                               "motivo": "credencial em URL de remoto"}])
        self.assertEqual((git["hooks_fora"], git["travas_fora"]), (4, 4))
        self.assertNotIn(".git", m["excluded"])
        # Nada da credencial foi para a cópia, nem para o disco do preparo.
        for arq in snap.rglob("*"):
            if arq.is_file():
                self.assertNotIn(SEGREDO_NA_URL.encode(), arq.read_bytes(), arq)
        self.assertTrue(backup.verify_backup(snap)["ok"])
        dest = self.pasta("dest")
        rep = backup.restore(snap, dest, self.log)
        self.assertTrue(rep["released"], rep)
        for rel in (".git/objects/ab/cdef0123456789", ".git/config", ".git/HEAD"):
            self.assertEqual((dest / p / rel).read_bytes(), (self.root / p / rel).read_bytes(), rel)
        self.assertFalse((dest / p / ".git" / "hooks").exists())

    def test_segredos_entram_contados_e_env_continua_fora(self):
        p = "projects/reversa-lab"
        self.escrever({p + "/.segredos/setup_token": "FICTICIO", p + "/.envs/producao": "FICTICIO",
                       p + "/chaves/servidor.pem": "FICTICIO", p + "/.env": "FICTICIO", p + "/notas.md": "nota"})
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "segredos-1710")
        caminhos = {f["path"] for f in m["files"]}
        self.assertNotIn(p + "/.env", caminhos)
        self.assertLessEqual({p + "/.segredos/setup_token", p + "/.envs/producao", p + "/chaves/servidor.pem"},
                             caminhos)
        self.assertEqual(m["segredos_incluidos"], 3)
        self.assertIn("3 arquivo(s) com cara de segredo", m["credentials"])
        self.assertNotIn("não incluídas", m["credentials"])
        manifesto = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifesto["segredos_incluidos"], 3)
        self.assertIn("git", manifesto)

    def test_config_incluido_com_credencial_fica_fora(self):
        # #1: antes, só `config`/`config.worktree` eram conferidos; um arquivo puxado por include.path entrava em claro.
        p = "projects/juridico-lab"
        self.escrever({p + "/.git/HEAD": "ref: refs/heads/main\n",
                       p + "/.git/config": "[core]\n\tbare = false\n[include]\n\tpath = config-remoto\n",
                       p + "/.git/config-remoto": '[remote "origin"]\n\turl = ' + URL_COM_CREDENCIAL + "\n"})
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "incluido-1710")
        caminhos = {f["path"] for f in m["files"]}
        self.assertIn(p + "/.git/HEAD", caminhos)
        self.assertNotIn(p + "/.git/config", caminhos)          # include.path: fica fora
        self.assertNotIn(p + "/.git/config-remoto", caminhos)   # credencial em URL: fica fora, agora conferido
        fora = {e["caminho"]: e["motivo"] for e in m["git"]["config_fora"]}
        self.assertIn("include.path", fora[p + "/.git/config"])
        self.assertEqual(fora[p + "/.git/config-remoto"], "credencial em URL de remoto")
        for arq in snap.rglob("*"):
            if arq.is_file():
                self.assertNotIn(SEGREDO_NA_URL.encode(), arq.read_bytes(), arq)

    def test_config_acima_do_teto_fica_fora_e_outro_arquivo_vai_cru(self):
        # Reconferência das correções: acima do teto, config/config.worktree ficam fora sem conferir (como antes do #1);
        # outro arquivo do .git acima do teto (ex.: packed-refs grande) continua copiado cru.
        p = "projects/juridico-lab"
        self.escrever({p + "/.git/HEAD": "ref: refs/heads/main\n",
                       p + "/.git/config": "[core]\n\tbare = false\n" + "# comentário fictício\n" * 8,
                       p + "/.git/packed-refs": "0" * 40 + " refs/heads/main\n" * 4})
        snap = self.pasta("snap")
        with mock.patch.object(manutencao, "TETO_CONFIG", 64):
            m = backup.create_backup(self.root, snap, "teto-1710")
        caminhos = {f["path"] for f in m["files"]}
        self.assertNotIn(p + "/.git/config", caminhos)
        self.assertIn(p + "/.git/packed-refs", caminhos)
        fora = {e["caminho"]: e["motivo"] for e in m["git"]["config_fora"]}
        self.assertEqual(fora[p + "/.git/config"], "config grande demais para conferir")

    def test_submodulo_chamado_refs_ou_logs_nao_fura_as_regras(self):
        # #6: o gitdir de um submódulo pode se chamar refs/logs/hooks; as regras valem a partir do começo do gitdir.
        p = "projects/juridico-lab"
        self.escrever({p + "/.git/HEAD": "ref: refs/heads/main\n",
                       p + "/.git/modules/refs/HEAD": "ref: refs/heads/main\n",
                       p + "/.git/modules/refs/hooks/post-checkout": "#!/bin/sh\n",  # hook do submódulo 'refs'
                       p + "/.git/modules/logs/config": '[remote "o"]\n\turl = ' + URL_COM_CREDENCIAL + "\n"})
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "submodulo-1710")
        caminhos = {f["path"] for f in m["files"]}
        self.assertIn(p + "/.git/modules/refs/HEAD", caminhos)
        self.assertNotIn(p + "/.git/modules/refs/hooks/post-checkout", caminhos, "hook de submódulo entrou")
        self.assertNotIn(p + "/.git/modules/logs/config", caminhos, "config de submódulo com credencial entrou")
        self.assertEqual(m["git"]["hooks_fora"], 1)
        fora = {e["caminho"]: e["motivo"] for e in m["git"]["config_fora"]}
        self.assertEqual(fora[p + "/.git/modules/logs/config"], "credencial em URL de remoto")
        for arq in snap.rglob("*"):
            if arq.is_file():
                self.assertNotIn(SEGREDO_NA_URL.encode(), arq.read_bytes(), arq)

    def test_git_que_some_durante_a_copia_nao_derruba_e_avisa(self):
        # #2: um arquivo do .git de repositório vivo some (git gc) no meio da cópia: era FileNotFoundError que derrubava.
        p = "projects/juridico-lab"
        self.escrever({p + "/.git/HEAD": "ref: refs/heads/main\n",
                       p + "/.git/objects/ab/cdef": bytes(range(32)),
                       p + "/.git/config": "[core]\n\tbare = false\n"})
        snap = self.pasta("snap")
        real_copiar = preparo.copiar

        def sumindo(origem, destino, listado):
            if Path(origem).as_posix().endswith(".git/objects/ab/cdef"):
                raise FileNotFoundError(2, "sumiu (simulado)")
            return real_copiar(origem, destino, listado)
        with mock.patch.object(preparo, "copiar", side_effect=sumindo):
            m = backup.create_backup(self.root, snap, "sumiu-1710")
        caminhos = {f["path"] for f in m["files"]}
        self.assertIn(p + "/.git/HEAD", caminhos)
        self.assertNotIn(p + "/.git/objects/ab/cdef", caminhos)
        self.assertEqual(m["git"]["mudaram_durante_a_copia"], [p + "/.git/objects/ab/cdef"])
        self.assertIn("mudaram durante a cópia", m.get("aviso", ""))
        self.assertTrue(backup.verify_backup(snap)["ok"], "a cópia sem o arquivo que sumiu ainda confere")
