"""Importar sem ler (1.7.10; DESENHO-1.7.10 §5.2; MELHORIAS-1.7.10, item 0.7 e seção 1, itens 10 e 11).

Na migração de 26 e 27/10, cada sessão escreveu o seu copiador. `importar.py` é o da skill: plano só com metadados,
aceite do SHA-256, cópia byte a byte com caminho, tamanho e SHA-256 (o opaco nunca é decodificado nem mostrado),
conferência; modos completo, lista de permissão e delta; `.git` em zip sem config nem hooks; SQLite pela API de
backup; extensões de host neutralizadas na cópia; retomada pelo hash; destino só dentro de projects/<projeto>/.
Pastas descartáveis, conteúdo fictício.
"""

from __future__ import annotations

import builtins
import hashlib
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from apoio import SCRIPTS, criar_ligacao_dir, rodar_script

OPACO = "conteudo opaco ficticio que nunca aparece na saida 7f3a"
ARQUIVOS = {
    "a.txt": "texto comum\r\n",
    "src/app.py": "print('oi')\n",
    "docs/guia.md": "guia\n",
    ".env": "X=1\n",
    ".segredos/setup_token": OPACO,
    ".segredos/outro": "fora\n",
    "tokenizer.py": "def tokenizar(): pass\n",
    "node_modules/x/index.js": "module.exports = 1\n",
    ".git/HEAD": "ref: refs/heads/main\n",
    ".git/config": "[core]\n",
    ".git/hooks/pre-commit": "#!/bin/sh\n",
    ".git/objects/ab/cdef": "objeto",
    ".git/refs/heads/main": "0" * 40 + "\n",
    ".git/packed-refs": "# pacotes\n",
    "squad/CLAUDE.md": "instrução antiga (dado)\n",
    "squad/.claude/skills/redator/SKILL.md": "---\nname: redator\n---\n",
    "squad/.claude/agents/a.md": "agente\n",
    "squad/.claude/settings.json": "{}\n",
    "squad/.codex/config.toml": "[x]\n",
    "clientes/joao/peticao.pdf": "pdf ficticio\n",
    "Thumbs.db": "nao e sqlite",
}


def carregar(nome: str):
    spec = importlib.util.spec_from_file_location(f"_teste_importar_{nome}", SCRIPTS / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def apagar_arvore(caminho: Path) -> None:
    """A cópia fica só leitura: no Windows, tira o atributo antes de apagar."""
    def tirar_so_leitura(func, alvo, _exc):
        try:
            os.chmod(alvo, stat.S_IWRITE | stat.S_IREAD)
            func(alvo)
        except OSError:
            pass
    shutil.rmtree(caminho, onexc=tirar_so_leitura)


def sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


class _Importacao(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="importar-")))
        self.addCleanup(apagar_arvore, self.base)
        self.origem = self.base / "origem"
        for rel, texto in ARQUIVOS.items():
            p = self.origem / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(texto.encode("utf-8"))
        db = self.origem / "dados" / "app.db"
        db.parent.mkdir()
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE itens (v TEXT)")
        con.execute("INSERT INTO itens VALUES ('um')")
        con.commit()
        con.close()
        self.raiz = self.base / "fundacao"
        (self.raiz / "projects" / "proj-a").mkdir(parents=True)
        self._marcar_raiz(self.raiz)
        self._registrar_origem(self.raiz, "proj-a", self.origem)
        self.destino = self.raiz / "projects" / "proj-a" / "data" / "origem" / "parte1"
        self.plano_arq = self.base / "planos" / "plano.json"

    @staticmethod
    def _marcar_raiz(raiz: Path) -> None:
        """Marcadores que resolver_destino exige de uma raiz de fundação: fundacao/__main__.py, registry/ e state/."""
        (raiz / "fundacao").mkdir(parents=True, exist_ok=True)
        (raiz / "fundacao" / "__main__.py").write_text("# raiz de fundação de teste\n", encoding="utf-8")
        (raiz / "registry").mkdir(exist_ok=True)
        (raiz / "state").mkdir(exist_ok=True)

    @staticmethod
    def _registrar_origem(raiz: Path, projeto: str, *origens: Path) -> None:
        """O registro fictício das origens do projeto (registry/projetos-host.json, que o titular grava com o preparo
        do host): desde a integração da 1.7.10, o plano só aceita a origem registrada para o projeto do destino."""
        dados = {"schema_version": "fundacao.projetos_host/1",
                 "projetos": {projeto: {"origens": [str(o) for o in origens], "somente_leitura": [],
                                        "aninhadas_negadas": []}}}
        (raiz / "registry" / "projetos-host.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")

    def plano(self, *extra, destino: Path | None = None, codigo: int = 0) -> dict:
        p = rodar_script("importar.py", "plano", "--origem", self.origem, "--destino", destino or self.destino,
                         "--raiz-fundacao", self.raiz, "--saida", self.plano_arq, *extra)
        self.assertEqual(p.returncode, codigo, p.stdout + p.stderr)
        if codigo:
            return {"erro": json.loads(p.stderr.strip().splitlines()[-1])["erro"]}
        saida = json.loads(p.stdout)
        saida["plano_json"] = json.loads(self.plano_arq.read_text(encoding="utf-8"))
        saida["texto"] = p.stdout + self.plano_arq.read_text(encoding="utf-8")
        return saida

    def copiar(self, sha256: str, *extra, codigo: int = 0) -> dict:
        p = rodar_script("importar.py", "copiar", "--plano", self.plano_arq, "--plano-sha256", sha256, *extra)
        self.assertEqual(p.returncode, codigo, p.stdout + p.stderr)
        self.assertNotIn(OPACO, p.stdout + p.stderr)
        if p.returncode == 2:
            return {"erro": json.loads(p.stderr.strip().splitlines()[-1])["erro"]}
        return json.loads(p.stdout)

    def conferir(self) -> tuple[int, dict]:
        p = rodar_script("importar.py", "conferir", "--manifesto", self.destino / "MANIFESTO-IMPORTACAO.json")
        return p.returncode, json.loads(p.stdout) if p.stdout.strip().startswith("{") else {}

    def manifesto(self) -> dict:
        return json.loads((self.destino / "MANIFESTO-IMPORTACAO.json").read_text(encoding="utf-8"))

    @staticmethod
    def por_caminho(itens: list) -> dict:
        return {i["caminho"]: i for i in itens}


class TestPlano(_Importacao):
    def test_plano_le_so_metadados(self):
        imp = carregar("importar")
        origem = str(self.origem)
        originais = {"os": os.open, "io": io.open}

        def vigia(original):
            def abrir(caminho, *a, **k):
                if isinstance(caminho, (str, bytes, os.PathLike)) and os.path.abspath(os.fsdecode(caminho)).startswith(
                        origem):
                    raise AssertionError(f"o plano abriu um arquivo da origem: {caminho}")
                return original(caminho, *a, **k)
            return abrir

        with mock.patch.object(os, "open", vigia(originais["os"])), \
                mock.patch.object(io, "open", vigia(originais["io"])), \
                mock.patch.object(builtins, "open", vigia(originais["io"])), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            codigo = imp.main(["plano", "--origem", origem, "--destino", str(self.destino), "--raiz-fundacao",
                               str(self.raiz), "--saida", str(self.plano_arq), "--opaco", ".segredos/setup_token"])
        self.assertEqual(codigo, 0)

    def test_classes_do_plano(self):
        dados = self.plano("--opaco", ".segredos/setup_token")
        itens = self.por_caminho(dados["plano_json"]["itens"])
        esperado = {"a.txt": "comum", "src/app.py": "comum", ".env": "segredo", ".segredos": "segredo",
                    ".segredos/setup_token": "opaco", "tokenizer.py": "segredo", "node_modules": "reconstruivel",
                    ".git": "git", "dados/app.db": "sqlite", "Thumbs.db": "sqlite",
                    "squad/.claude/skills/redator/SKILL.md": "comum", "squad/.codex/config.toml": "comum",
                    "squad/.claude/settings.json": "comum"}
        for rel, classe in esperado.items():
            self.assertEqual(itens[rel]["classe"], classe, rel)
        self.assertEqual((itens[".env"]["regra"], itens["tokenizer.py"]["regra"]), ("forte", "fraco"))
        self.assertEqual((itens[".segredos"]["regra"], itens[".segredos"]["nao_autorizados"]), ("pasta-de-segredo", 1))
        self.assertNotIn(".segredos/outro", itens)
        self.assertEqual(itens[".git"]["zip"], ".git.zip")
        self.assertEqual(itens[".git"]["omitidos"], ["config", "hooks/"])
        self.assertTrue(itens["squad/.claude/skills/redator/SKILL.md"]["neutralizar"])
        self.assertTrue(itens["squad/.codex/config.toml"]["neutralizar"])
        self.assertNotIn("neutralizar", itens["squad/.claude/settings.json"])
        self.assertNotIn(OPACO, dados["texto"])
        self.assertEqual(len(dados["sha256"]), 64)

    def test_ligacao_e_vinculo_fisico_ficam_fora(self):
        fora = self.base / "fora"
        fora.mkdir()
        (fora / "externo.txt").write_text("de fora", encoding="utf-8")
        criar_ligacao_dir(self.origem / "atalho", fora)
        (self.origem / "h1.txt").write_text("vínculo", encoding="utf-8")
        try:
            os.link(self.origem / "h1.txt", self.origem / "h2.txt")
        except OSError as exc:
            self.skipTest(f"vínculo físico indisponível neste ambiente: {exc}")
        dados = self.plano()
        itens = self.por_caminho(dados["plano_json"]["itens"])
        self.assertEqual(itens["atalho"]["classe"], "ligacao")
        self.assertEqual((itens["h1.txt"]["classe"], itens["h2.txt"]["classe"]), ("vinculo-fisico", "vinculo-fisico"))
        self.assertNotIn("externo.txt", dados["texto"])

    def test_lista_de_permissao_nega_por_padrao_e_nao_mostra_nomes(self):
        dados = self.plano("--modo", "lista-de-permissao", "--permitir", "src/*", "--permitir", "docs/*.md")
        itens = self.por_caminho(dados["plano_json"]["itens"])
        self.assertEqual(sorted(itens), ["docs/guia.md", "src/app.py"])
        fora = {(f["pasta"], f["extensao"]): f["quantidade"] for f in dados["plano_json"]["fora_da_lista"]}
        self.assertEqual(fora[("clientes", ".pdf")], 1)
        for nome in ("joao", "peticao", "tokenizer", "setup_token", "redator"):
            self.assertNotIn(nome, dados["texto"])
        self.copiar(dados["sha256"])
        copiados = sorted(p.relative_to(self.destino).as_posix() for p in self.destino.rglob("*") if p.is_file())
        self.assertEqual(copiados, ["MANIFESTO-IMPORTACAO.json", "docs/guia.md", "src/app.py"])

    def test_incluir_fraco_leva_o_nome_fraco_e_nunca_o_forte(self):
        dados = self.plano("--incluir-fraco", "tokenizer.py", "--incluir-fraco", ".env")
        itens = self.por_caminho(dados["plano_json"]["itens"])
        self.assertEqual((itens["tokenizer.py"]["classe"], itens["tokenizer.py"]["fraco_incluido"]), ("comum", True))
        self.assertEqual((itens[".env"]["classe"], itens[".env"]["regra"]), ("segredo", "forte"))
        self.copiar(dados["sha256"])
        self.assertTrue((self.destino / "tokenizer.py").is_file())
        self.assertFalse((self.destino / ".env").exists())

    def test_reconstruivel_a_mais(self):
        (self.origem / ".next" / "cache").mkdir(parents=True)
        (self.origem / ".next" / "cache" / "x.js").write_text("x", encoding="utf-8")
        itens = self.por_caminho(self.plano("--reconstruivel", ".next")["plano_json"]["itens"])
        self.assertEqual(itens[".next"]["classe"], "reconstruivel")
        self.plano("--reconstruivel", "a/b", codigo=2)

    def test_opcoes_do_modo(self):
        self.assertIn("exige", self.plano("--modo", "lista-de-permissao", codigo=2)["erro"])
        self.assertIn("só vale", self.plano("--permitir", "src/*", codigo=2)["erro"])

    def test_auxiliares_sqlite_entram_no_plano_como_auxiliar_ou_opaco(self):
        (self.origem / "dados" / "app.db-wal").write_bytes(b"wal ficticio")
        (self.origem / "dados" / "app.db-shm").write_bytes(b"shm ficticio")
        itens = self.por_caminho(self.plano()["plano_json"]["itens"])
        self.assertEqual(itens["dados/app.db"]["classe"], "sqlite")
        self.assertEqual((itens["dados/app.db-wal"]["classe"], itens["dados/app.db-shm"]["classe"]),
                         ("auxiliar-sqlite", "auxiliar-sqlite"))
        # com --opaco pegando o banco e os auxiliares, os -wal/-shm entram byte a byte (opaco)
        itens2 = self.por_caminho(self.plano("--opaco", "dados/app.db*")["plano_json"]["itens"])
        self.assertEqual((itens2["dados/app.db-wal"]["classe"], itens2["dados/app.db-shm"]["classe"]),
                         ("opaco", "opaco"))

    def test_git_dentro_de_pasta_de_segredo_nao_vira_copia_crua(self):
        g = self.origem / ".segredos" / ".git"
        (g / "objects").mkdir(parents=True)
        (g / "config").write_text("[core]\n", encoding="utf-8")
        (g / "objects" / "x").write_bytes(b"objeto do git")
        dados = self.plano("--opaco", ".segredos/*")
        itens = self.por_caminho(dados["plano_json"]["itens"])
        self.assertEqual([rel for rel in itens if rel.startswith(".segredos/.git")], [])
        self.copiar(dados["sha256"])
        self.assertFalse((self.destino / ".segredos" / ".git").exists())
        self.assertTrue((self.destino / ".segredos" / "setup_token").is_file())

    def test_lista_de_permissao_nao_vaza_extensao_com_ponto_e_espaco(self):
        (self.origem / "clientes" / "arquivo.joao da silva").write_text("x", encoding="utf-8")
        dados = self.plano("--modo", "lista-de-permissao", "--permitir", "src/*")
        fora = {(f["pasta"], f["extensao"]) for f in dados["plano_json"]["fora_da_lista"]}
        self.assertIn(("clientes", "(outra)"), fora)
        self.assertNotIn("da silva", dados["texto"])

    def test_omissao_do_git_em_submodulo_e_worktree(self):
        omitir = carregar("importar")._omitir_no_git
        for partes in [("config",), ("hooks", "pre-commit"), ("modules", "objects", "config"),
                       ("modules", "sub", "hooks", "post-checkout"), ("worktrees", "wt", "config.worktree")]:
            self.assertTrue(omitir(partes), partes)
        for partes in [("objects", "ab", "cd"), ("modules", "sub", "objects", "ab", "cd"),
                       ("modules", "sub", "refs", "heads", "main")]:
            self.assertFalse(omitir(partes), partes)


class TestDestino(_Importacao):
    def test_destino_tem_de_ficar_abaixo_de_um_projeto_da_raiz(self):
        casos = {"fora de projects": self.base / "outro-lugar" / "x",
                 "o próprio projeto": self.raiz / "projects" / "proj-a",
                 "pasta oculta do projeto": self.raiz / "projects" / "proj-a" / ".claude" / "x",
                 "projeto inexistente": self.raiz / "projects" / "nao-existe" / "x"}
        for rotulo, destino in casos.items():
            with self.subTest(rotulo):
                self.plano(destino=destino, codigo=2)
                self.assertFalse(destino.exists() and any(destino.iterdir()), rotulo)

    def test_ligacao_no_caminho_do_destino_recusa(self):
        fora = self.base / "fora"
        fora.mkdir()
        criar_ligacao_dir(self.raiz / "projects" / "proj-a" / "data", fora)
        self.assertIn("ligação", self.plano(codigo=2)["erro"])
        self.assertEqual(list(fora.iterdir()), [])

    def test_ligacao_criada_depois_do_aceite_recusa_e_nada_sai_do_projeto(self):
        dados = self.plano()
        fora = self.base / "fora"
        fora.mkdir()
        (self.raiz / "projects" / "proj-a" / "data").mkdir()
        criar_ligacao_dir(self.raiz / "projects" / "proj-a" / "data" / "origem", fora)
        self.copiar(dados["sha256"], codigo=2)
        self.assertEqual(list(fora.iterdir()), [], "gravou através da ligação")

    def test_origem_em_outro_projeto_da_raiz_recusa(self):
        outro = self.raiz / "projects" / "proj-b" / "dados"
        outro.mkdir(parents=True)
        (outro / "x.txt").write_text("de outro projeto", encoding="utf-8")
        p = rodar_script("importar.py", "plano", "--origem", outro, "--destino", self.destino, "--raiz-fundacao",
                         self.raiz, "--saida", self.plano_arq)
        self.assertEqual(p.returncode, 2, p.stdout)
        self.assertIn("um projeto não importa de outro", p.stderr)

    def test_plano_dentro_do_destino_ou_da_origem_recusa(self):
        for saida in (self.destino / "plano.json", self.origem / "plano.json"):
            p = rodar_script("importar.py", "plano", "--origem", self.origem, "--destino", self.destino,
                             "--raiz-fundacao", self.raiz, "--saida", saida)
            self.assertEqual(p.returncode, 2, p.stdout)
            self.assertFalse(saida.exists())

    def test_destino_com_arquivos_de_outra_importacao_recusa(self):
        dados = self.plano()
        self.destino.mkdir(parents=True)
        (self.destino / "alheio.txt").write_text("de antes", encoding="utf-8")
        self.assertIn("não são de uma importação deste plano", self.copiar(dados["sha256"], codigo=2)["erro"])

    def test_raiz_sem_marcadores_recusa(self):
        # uma pasta com projects/<p>/ mas sem os marcadores da raiz não serve como --raiz-fundacao
        falsa = self.base / "falsa"
        (falsa / "projects" / "proj-a").mkdir(parents=True)
        destino = falsa / "projects" / "proj-a" / "data" / "x"
        p = rodar_script("importar.py", "plano", "--origem", self.origem, "--destino", destino,
                         "--raiz-fundacao", falsa, "--saida", self.plano_arq)
        self.assertEqual(p.returncode, 2, p.stdout)
        self.assertIn("raiz de fundação", p.stderr)
        self.assertFalse(self.plano_arq.exists())

    def test_origem_em_outra_fundacao_com_raiz_falsa_recusa(self):
        # a origem está numa fundação real (self.raiz); o destino aponta uma raiz falsa, com marcadores
        outro = self.raiz / "projects" / "proj-b" / "dados"
        outro.mkdir(parents=True)
        (outro / "x.txt").write_text("de outro projeto", encoding="utf-8")
        falsa = self.base / "falsa"
        (falsa / "projects" / "proj-a").mkdir(parents=True)
        self._marcar_raiz(falsa)
        destino = falsa / "projects" / "proj-a" / "data" / "x"
        p = rodar_script("importar.py", "plano", "--origem", outro, "--destino", destino,
                         "--raiz-fundacao", falsa, "--saida", self.plano_arq)
        self.assertEqual(p.returncode, 2, p.stdout)
        self.assertIn("um projeto não importa de outro", p.stderr)

    def test_item_com_nome_reservado_da_importacao_recusa(self):
        (self.origem / "MANIFESTO-IMPORTACAO.json").write_text("{}", encoding="utf-8")
        self.assertIn("nome reservado", self.plano(codigo=2)["erro"])


class TestCopia(_Importacao):
    def test_copia_completa_byte_a_byte_e_conferencia(self):
        dados = self.plano("--opaco", ".segredos/setup_token")
        r = self.copiar(dados["sha256"])
        self.assertEqual(r["falhas"], [])
        for rel in ("a.txt", "src/app.py", "docs/guia.md", "squad/CLAUDE.md", "squad/.claude/settings.json",
                    "clientes/joao/peticao.pdf", ".segredos/setup_token", "Thumbs.db"):
            copia, original = self.destino / rel, self.origem / rel
            self.assertEqual(copia.read_bytes(), original.read_bytes(), rel)
            self.assertFalse(os.stat(copia).st_mode & stat.S_IWUSR, f"{rel} não ficou só leitura")
            self.assertEqual(os.stat(copia).st_mtime_ns // 10**6, os.stat(original).st_mtime_ns // 10**6, rel)
        for rel in (".env", ".segredos/outro", "tokenizer.py", "node_modules", ".git", "squad/.claude/skills",
                    "squad/.codex", "squad/.claude/agents"):
            self.assertFalse((self.destino / rel).exists(), rel)
        m = self.manifesto()
        arquivos = self.por_caminho(m["arquivos"])
        self.assertEqual(arquivos[".segredos/setup_token"]["classe"], "opaco")
        self.assertEqual(arquivos[".segredos/setup_token"]["sha256"], sha(OPACO))
        self.assertEqual(arquivos["a.txt"]["sha256"], sha(ARQUIVOS["a.txt"]))
        self.assertEqual(arquivos["Thumbs.db"]["copia"], "byte a byte: sem o cabeçalho do SQLite")
        self.assertNotIn(OPACO, json.dumps(m, ensure_ascii=False))
        self.assertEqual(self.conferir(), (0, self.conferir()[1]))
        self.assertEqual(self.conferir()[1]["alterados"], [])

    def test_git_em_zip_sem_config_nem_hooks(self):
        dados = self.plano()
        self.copiar(dados["sha256"])
        with zipfile.ZipFile(self.destino / ".git.zip") as zf:
            self.assertEqual(sorted(zf.namelist()), ["HEAD", "objects/ab/cdef", "packed-refs", "refs/heads/main"])
            self.assertEqual(zf.read("HEAD"), ARQUIVOS[".git/HEAD"].encode())
        git = self.manifesto()["git"][0]
        self.assertEqual((git["caminho"], git["zip"], git["omitidos"]), (".git", ".git.zip", ["config", "hooks/"]))

    def test_git_de_worktree_vai_para_o_zip(self):
        (self.origem / "sub").mkdir()
        (self.origem / "sub" / ".git").write_text("gitdir: ../../repo/.git/worktrees/sub\n", encoding="utf-8")
        dados = self.plano()
        self.copiar(dados["sha256"])
        self.assertFalse((self.destino / "sub" / ".git").exists())
        with zipfile.ZipFile(self.destino / "sub" / ".git.zip") as zf:
            self.assertEqual(zf.namelist(), [".git"])

    def test_extensoes_de_host_neutralizadas_num_zip(self):
        dados = self.plano()
        self.copiar(dados["sha256"])
        with zipfile.ZipFile(self.destino / "EXTENSOES-NEUTRALIZADAS.zip") as zf:
            self.assertEqual(sorted(zf.namelist()), ["squad/.claude/agents/a.md",
                                                     "squad/.claude/skills/redator/SKILL.md",
                                                     "squad/.codex/config.toml"])
        neutros = [a for a in self.manifesto()["arquivos"] if a.get("neutralizado_em")]
        self.assertEqual(len(neutros), 3)
        self.assertEqual(self.conferir()[0], 0)

    def test_sem_neutralizar_copia_as_extensoes(self):
        dados = self.plano("--sem-neutralizar-extensoes")
        self.copiar(dados["sha256"])
        self.assertTrue((self.destino / "squad" / ".claude" / "skills" / "redator" / "SKILL.md").is_file())
        self.assertFalse((self.destino / "EXTENSOES-NEUTRALIZADAS.zip").exists())

    def test_sqlite_pela_api_de_backup(self):
        dados = self.plano()
        self.copiar(dados["sha256"])
        entrada = self.por_caminho(self.manifesto()["arquivos"])["dados/app.db"]
        self.assertTrue(entrada["copia"].startswith("API de backup do SQLite"))
        self.assertEqual(entrada["sqlite"], {"integrity_check": "ok", "tabelas": 1})
        con = sqlite3.connect((self.destino / "dados" / "app.db").resolve().as_uri() + "?mode=ro", uri=True)
        try:
            self.assertEqual(con.execute("SELECT v FROM itens").fetchall(), [("um",)])
        finally:
            con.close()

    def test_sha256_errado_recusa_sem_criar_nada(self):
        self.plano()
        self.assertIn("não é o aceito", self.copiar("0" * 64, codigo=2)["erro"])
        self.assertFalse(self.destino.exists())

    def test_origem_que_mudou_depois_do_plano_recusa(self):
        dados = self.plano()
        (self.origem / "src" / "app.py").write_text("print('trocado depois do aceite')\n", encoding="utf-8")
        erro = self.copiar(dados["sha256"], codigo=2)["erro"]
        self.assertIn("a origem mudou depois do plano", erro)
        self.assertIn("src/app.py", erro)
        self.assertFalse(self.destino.exists())

    def test_retomada_pelo_hash(self):
        dados = self.plano("--opaco", ".segredos/setup_token")
        self.copiar(dados["sha256"])
        r = self.copiar(dados["sha256"])
        self.assertEqual(r["contas"].get("retomada"), 1)
        self.assertGreaterEqual(r["contas"].get("ja_estavam", 0), 8)
        self.assertEqual(self.conferir()[0], 0)
        self.assertFalse((self.destino / ".importacao-em-andamento.json").exists())

    def test_conferir_nao_sai_do_destino_pelo_manifesto_editado(self):
        dados = self.plano()
        self.copiar(dados["sha256"])
        manifesto = self.destino / "MANIFESTO-IMPORTACAO.json"
        m = self.manifesto()
        fora = os.path.relpath(self.origem / "a.txt", self.destino).replace(os.sep, "/")  # o arquivo da origem
        self.assertTrue((self.destino / fora).is_file())
        for entrada in m["arquivos"]:
            if entrada.get("neutralizado_em"):
                entrada["neutralizado_em"] = "../../fora.zip"
            elif entrada["caminho"] == "a.txt":
                entrada["caminho"] = fora
        os.chmod(manifesto, stat.S_IWRITE | stat.S_IREAD)
        manifesto.write_text(json.dumps(m), encoding="utf-8")
        codigo, r = self.conferir()
        self.assertEqual(codigo, 1)
        problemas = {p["caminho"] for p in r["problemas"]}
        self.assertIn(fora, problemas)
        self.assertNotIn(fora, r["alterados"] + r["ausentes"])
        self.assertIn("squad/.claude/skills/redator/SKILL.md", problemas)

    def test_conferir_acusa_alterado_ausente_e_a_mais(self):
        dados = self.plano()
        self.copiar(dados["sha256"])
        alvo = self.destino / "a.txt"
        os.chmod(alvo, stat.S_IWRITE | stat.S_IREAD)
        alvo.write_text("mexido depois da cópia", encoding="utf-8")
        os.chmod(self.destino / "docs" / "guia.md", stat.S_IWRITE | stat.S_IREAD)
        (self.destino / "docs" / "guia.md").unlink()
        (self.destino / "plantado.txt").write_text("x", encoding="utf-8")
        codigo, r = self.conferir()
        self.assertEqual(codigo, 1)
        self.assertEqual((r["alterados"], r["ausentes"], r["a_mais"]), (["a.txt"], ["docs/guia.md"], ["plantado.txt"]))

    def test_sqlite_sem_cabecalho_com_wal_falha_em_vez_de_perder_transacoes(self):
        (self.origem / "dados" / "cofre.db").write_bytes(b"CIFRADO-SQLCIPHER" + os.urandom(64))  # sem cabeçalho
        (self.origem / "dados" / "cofre.db-wal").write_bytes(b"transacao nao consolidada")
        dados = self.plano()
        itens = self.por_caminho(dados["plano_json"]["itens"])
        self.assertEqual((itens["dados/cofre.db"]["classe"], itens["dados/cofre.db-wal"]["classe"]),
                         ("sqlite", "auxiliar-sqlite"))
        r = self.copiar(dados["sha256"], codigo=1)
        self.assertIn("dados/cofre.db", {f["caminho"] for f in r["falhas"]})
        self.assertFalse((self.destino / "dados" / "cofre.db").exists())

    def test_pasta_temporaria_do_sqlite_removida_na_retomada(self):
        dados = self.plano()
        self.copiar(dados["sha256"])
        sobra = self.destino / ".importando-abcdef12"   # pasta de uma cópia do SQLite interrompida
        sobra.mkdir()
        (sobra / "copia.sqlite").write_bytes(b"sobra de copia interrompida")
        self.copiar(dados["sha256"])  # retomada: a limpeza apaga a pasta temporária
        self.assertFalse(sobra.exists())

    def test_subpasta_do_destino_trocada_por_ligacao_durante_a_copia_recusa(self):
        imp = carregar("importar")
        (self.origem / "caso").mkdir()
        (self.origem / "caso" / "dois.txt").write_text("dois", encoding="utf-8")
        (self.origem / "caso" / "um.txt").write_text("um", encoding="utf-8")
        fora = self.base / "fora"
        fora.mkdir()
        dados = self.plano()
        original = imp.Copia.copiar_arquivo

        def troca_no_meio(self2, item, **extra):
            original(self2, item, **extra)
            if item["caminho"] == "caso/dois.txt":  # troca a subpasta já criada por uma ligação para fora
                sub = self2.grav.raiz / "caso"
                apagar_arvore(sub)
                criar_ligacao_dir(sub, fora)

        with mock.patch.object(imp.Copia, "copiar_arquivo", troca_no_meio), \
                mock.patch.object(sys, "stdout", io.StringIO()), mock.patch.object(sys, "stderr", io.StringIO()):
            codigo = imp.main(["copiar", "--plano", str(self.plano_arq), "--plano-sha256", dados["sha256"]])
        self.assertEqual(codigo, 2)
        self.assertEqual(list(fora.iterdir()), [], "gravou através da ligação")


class TestDeltaEB1(_Importacao):
    def b1(self) -> Path:
        man = self.base / "b1" / "manifesto.json"
        p = rodar_script("manifesto.py", "criar", "--raiz", self.origem, "--saida", man)
        self.assertEqual(p.returncode, 0, p.stderr)
        return man

    def test_delta_traz_so_o_novo_e_o_que_mudou_e_lista_o_que_sumiu(self):
        b1 = self.b1()
        (self.origem / "a.txt").write_bytes(b"texto COMUM\r\n")  # mesmo tamanho, conteúdo novo
        (self.origem / "src" / "app.py").write_text("print('mudou de tamanho')\n", encoding="utf-8")
        (self.origem / "novo.txt").write_text("novo\n", encoding="utf-8")
        (self.origem / "docs" / "guia.md").unlink()
        dados = self.plano("--desde", b1)
        itens = self.por_caminho(dados["plano_json"]["itens"])
        self.assertEqual((itens["a.txt"]["delta"], itens["src/app.py"]["delta"], itens["novo.txt"]["delta"]),
                         ("a-conferir", "alterado", "novo"))
        self.assertEqual(dados["plano_json"]["sumidos"], ["docs/guia.md"])
        self.copiar(dados["sha256"])
        copiados = sorted(p.relative_to(self.destino).as_posix() for p in self.destino.rglob("*") if p.is_file())
        self.assertIn("a.txt", copiados)
        self.assertIn("src/app.py", copiados)
        self.assertIn("novo.txt", copiados)
        for igual in ("squad/CLAUDE.md", "clientes/joao/peticao.pdf", "squad/.claude/settings.json"):
            self.assertNotIn(igual, copiados)
        m = self.manifesto()
        self.assertGreaterEqual(m["delta"]["inalterados"], 3)
        self.assertEqual(m["delta"]["sumidos"], ["docs/guia.md"])

    def test_delta_na_lista_de_permissao_nao_mostra_sumido_de_fora_da_lista(self):
        b1 = self.b1()
        (self.origem / "docs" / "guia.md").unlink()
        (self.origem / "clientes" / "joao" / "peticao.pdf").unlink()
        dados = self.plano("--desde", b1, "--modo", "lista-de-permissao", "--permitir", "docs/*",
                           "--permitir", "src/*")
        self.assertEqual(dados["plano_json"]["sumidos"], ["docs/guia.md"])
        self.assertEqual(dados["resumo"]["sumidos-fora-da-lista"], 1)
        for nome in ("joao", "peticao"):
            self.assertNotIn(nome, dados["texto"])

    def test_manifesto_do_b1_acusa_o_que_mudou_desde_ele(self):
        b1 = self.b1()
        (self.origem / "a.txt").write_bytes(b"texto COMUM\r\n")
        dados = self.plano()
        r = self.copiar(dados["sha256"], "--manifesto-b1", b1, codigo=1)
        self.assertEqual(r["divergem_do_b1"], ["a.txt"])
        arquivos = self.por_caminho(self.manifesto()["arquivos"])
        self.assertEqual((arquivos["a.txt"]["b1"], arquivos["src/app.py"]["b1"]), ("diferente", "igual"))

    def test_desde_que_mudou_depois_do_plano_recusa(self):
        b1 = self.b1()
        dados = self.plano("--desde", b1)
        with b1.open("a", encoding="utf-8") as fh:  # o JSON continua o mesmo; os bytes, não
            fh.write("\n")
        self.assertIn("--desde mudou", self.copiar(dados["sha256"], codigo=2)["erro"])

    def test_retomada_com_b1_canonico_mantem_a_divergencia(self):
        man = self.base / "b1" / "manifesto.json"
        p = rodar_script("manifesto.py", "criar", "--raiz", self.origem, "--saida", man, "--texto-canonico")
        self.assertEqual(p.returncode, 0, p.stderr)
        (self.origem / "a.txt").write_bytes(b"texto DIFERENTE\n")  # divergência canônica real desde o B1
        dados = self.plano()
        r1 = self.copiar(dados["sha256"], "--manifesto-b1", man, codigo=1)
        self.assertEqual(r1["divergem_do_b1"], ["a.txt"])
        r2 = self.copiar(dados["sha256"], "--manifesto-b1", man, codigo=1)  # retomada pelo hash
        self.assertEqual(r2["contas"].get("retomada"), 1)
        self.assertEqual(r2["divergem_do_b1"], ["a.txt"])  # a divergência não vira "nao-comparavel" na retomada
        self.assertEqual(self.por_caminho(self.manifesto()["arquivos"])["a.txt"]["b1"], "diferente")


@unittest.skipUnless(sys.platform.startswith("linux"), "a gravação por descritor de pasta é do Linux")
class TestLinux(unittest.TestCase):
    def test_gravacao_por_descritor_de_pasta(self):
        self.assertTrue(carregar("importar")._POSIX)


if __name__ == "__main__":
    unittest.main()
