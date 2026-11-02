"""Manifesto do formato 3 (1.7.10; DESENHO-1.7.10 §5.1; MELHORIAS-1.7.10, seção 1, item 10).

A regra só de nome deixava ler, para o hash, o que está em `.segredos/` e `.envs/` e nomes como `setup_token`; o
`.git` sumia sem registro e não havia como levar uma pasta ignorada. O formato 3 usa a regra única, poda a pasta de
segredo sem ler nem listar o que tem dentro, dá modo explícito ao `.git` e leva pasta ignorada a pedido; os
manifestos do formato 2 continuam verificáveis com a política gravada, e `codigo_do_plano.fora_do_manifesto`, pela
regra única e pela mesma varredura do formato 3, vê como não preso tudo o que o formato 3 não lê. Pastas descartáveis,
conteúdo fictício.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from apoio import SCRIPTS, rodar_script

CONTEUDO_NA_PASTA_DE_SEGREDO = "conteúdo da pasta de segredo, fictício"
ARQUIVOS = {
    "a.txt": "comum",
    "src/app.py": "print('oi')\n",
    ".env": "X=1\n",
    ".segredos/setup_token": CONTEUDO_NA_PASTA_DE_SEGREDO,
    ".segredos/nome-que-nao-pode-aparecer.txt": "x",
    "x/.envs/dev.env": "Y=2\n",
    "tokenizer.py": "def tokenizar(): pass\n",
    "setup_token": "z",
    ".env.example": "Z=\n",
    ".cofre-ficticio/roteador.db": "db",
    "node_modules/dep/index.js": "module.exports = 1\n",
    ".venv/lib/mod.py": "x = 1\n",
    "__pycache__/a.cpython-312.pyc": "pyc",
    ".git/HEAD": "ref: refs/heads/main\n",
    ".git/config": "[core]\n",
    ".git/hooks/pre-commit": "#!/bin/sh\n",
    ".git/objects/ab/cdef": "objeto",
    ".git/refs/heads/main": "0" * 40 + "\n",
    ".git/packed-refs": "# pacotes\n",
    ".git/index": "indice",
    ".git/logs/HEAD": "log",
    "sub/.git": "gitdir: ../.git/worktrees/sub\n",
}


def carregar(nome: str):
    spec = importlib.util.spec_from_file_location(f"_teste_manifesto3_{nome}", SCRIPTS / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class _Arvore(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="manifesto3-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.raiz = self.base / "projeto"
        for rel, texto in ARQUIVOS.items():
            p = self.raiz / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(texto.encode("utf-8"))
        self.man = self.base / "manifesto.json"

    def criar(self, *extra, codigo: int = 0) -> dict | None:
        p = rodar_script("manifesto.py", "criar", "--raiz", self.raiz, "--saida", self.man, *extra)
        self.assertEqual(p.returncode, codigo, p.stdout + p.stderr)
        return json.loads(self.man.read_text(encoding="utf-8")) if codigo == 0 else None

    def verificar(self) -> tuple[int, dict]:
        p = rodar_script("manifesto.py", "verificar", "--raiz", self.raiz, "--manifesto", self.man)
        return p.returncode, (json.loads(p.stdout) if p.stdout.strip().startswith("{") else {})

    @staticmethod
    def caminhos(lista: list) -> list[str]:
        return sorted(e["path"] for e in lista)


class TestFormato3(_Arvore):
    def test_padrao_poda_pasta_de_segredo_lista_o_git_e_separa_as_ignoradas(self):
        m = self.criar()
        self.assertEqual(m["schema_version"], "fundacao.manifest/3")
        self.assertEqual(self.caminhos(m["arquivos"]), [".cofre-ficticio/roteador.db", "a.txt", "src/app.py"])
        excluidos = {e["path"]: e for e in m["excluidos"]}
        self.assertEqual(sorted(excluidos), [".env", ".env.example", ".git", ".segredos", "setup_token", "sub/.git",
                                             "tokenizer.py", "x/.envs"])
        self.assertEqual(excluidos[".git"]["motivo"], "pasta do Git: estado lido à parte")
        self.assertEqual(excluidos[".segredos"]["classe"], "pasta-de-segredo")
        self.assertEqual(excluidos[".env"]["classe"], "forte")
        for fraco in (".env.example", "setup_token", "tokenizer.py"):
            self.assertEqual(excluidos[fraco]["classe"], "fraco")
            self.assertIn("segredos.py conferir", excluidos[fraco]["motivo"])
        self.assertIn("worktree", excluidos["sub/.git"]["motivo"])
        self.assertEqual(self.caminhos(m["ignoradas"]), [".venv", "__pycache__", "node_modules"])

    def test_pasta_de_segredo_nao_e_lida_nem_listada(self):
        m = self.criar()
        texto = self.man.read_text(encoding="utf-8")
        self.assertNotIn("nome-que-nao-pode-aparecer", texto)
        self.assertNotIn(hashlib.sha256(CONTEUDO_NA_PASTA_DE_SEGREDO.encode()).hexdigest(), texto)
        self.assertNotIn(".segredos/", json.dumps(m["arquivos"]) + json.dumps(m["excluidos"]))

    def test_git_incluir_leva_objects_refs_packed_refs_e_head_e_nunca_le_config_e_hooks(self):
        m = self.criar("--git", "incluir")
        arquivos = self.caminhos(m["arquivos"])
        for rel in (".git/HEAD", ".git/objects/ab/cdef", ".git/refs/heads/main", ".git/packed-refs", "sub/.git"):
            self.assertIn(rel, arquivos)
        excluidos = {e["path"]: e["motivo"] for e in m["excluidos"]}
        for rel in (".git/config", ".git/hooks"):
            self.assertTrue(excluidos[rel].startswith("configuração ou código do Git: nunca executar"), excluidos)
        for rel in (".git/index", ".git/logs"):
            self.assertIn("fora do modo incluir", excluidos[rel])
        self.assertNotIn(".git", m["politica"]["pastas_ignoradas"])
        self.assertEqual(self.verificar()[0], 0)

    def test_git_ignorar_e_calado_como_no_formato_2(self):
        m = self.criar("--git", "ignorar")
        self.assertNotIn(".git", self.caminhos(m["excluidos"]))
        self.assertNotIn("sub/.git", self.caminhos(m["excluidos"]) + self.caminhos(m["arquivos"]))
        self.assertEqual(m["politica"]["modo_git"], "ignorar")

    def test_incluir_pasta_ignorada_leva_a_venv(self):
        m = self.criar("--incluir-pasta-ignorada", ".venv")
        self.assertIn(".venv/lib/mod.py", self.caminhos(m["arquivos"]))
        self.assertNotIn(".venv", self.caminhos(m["ignoradas"]))
        self.assertEqual(m["politica"]["pastas_incluidas"], [".venv"])
        self.assertEqual(self.verificar()[0], 0)

    def test_incluir_pasta_que_nao_e_ignoravel_e_uso_incorreto(self):
        for nome in (".git", ".ssh", ".segredos", "src"):
            with self.subTest(nome=nome):
                self.criar("--incluir-pasta-ignorada", nome, codigo=2)

    def test_pasta_de_segredo_extra_do_projeto(self):
        m = self.criar("--pasta-segredo", ".cofre-ficticio")
        self.assertNotIn(".cofre-ficticio/roteador.db", self.caminhos(m["arquivos"]))
        self.assertIn(".cofre-ficticio", self.caminhos(m["excluidos"]))
        self.criar("--pasta-segredo", "a/b", codigo=2)

    def test_incluir_fraco_depois_da_conferencia(self):
        m = self.criar("--incluir-fraco", "tokenizer.py")
        self.assertIn("tokenizer.py", self.caminhos(m["arquivos"]))
        self.assertIn("setup_token", self.caminhos(m["excluidos"]))
        self.assertEqual(self.verificar()[0], 0)

    def test_verificar_reconstroi_com_a_politica_gravada(self):
        self.criar()
        self.assertEqual(self.verificar(), (0, {"alterados": [], "ausentes": [], "novos": []}))
        (self.raiz / ".segredos" / "novo").write_text("x", encoding="utf-8")       # pasta de segredo: podada
        (self.raiz / "node_modules" / "outro.js").write_text("x", encoding="utf-8")  # ignorada
        (self.raiz / ".git" / "ORIG_HEAD").write_text("x", encoding="utf-8")         # .git listado, sem descer
        self.assertEqual(self.verificar()[0], 0)
        (self.raiz / "a.txt").write_text("mudou", encoding="utf-8")
        codigo, dados = self.verificar()
        self.assertEqual((codigo, dados["alterados"]), (1, ["a.txt"]))

    def test_politica_do_formato_3_incompleta_e_uso_incorreto(self):
        self.criar()
        dados = json.loads(self.man.read_text(encoding="utf-8"))
        for chave in ("padroes_fracos", "pastas_de_segredo", "modo_git"):
            with self.subTest(chave=chave):
                editado = {**dados, "politica": {k: v for k, v in dados["politica"].items() if k != chave}}
                self.man.write_text(json.dumps(editado), encoding="utf-8")
                p = rodar_script("manifesto.py", "verificar", "--raiz", self.raiz, "--manifesto", self.man)
                self.assertEqual(p.returncode, 2, p.stdout)
                self.assertIn("formato 3", p.stderr)


class TestCompatibilidade(_Arvore):
    def test_manifesto_do_formato_2_continua_verificavel_sem_herdar_a_regra_nova(self):
        manifesto = carregar("manifesto")
        antigo = manifesto.build(self.raiz.resolve(), manifesto.politica_padrao())
        self.assertEqual(antigo["schema_version"], "fundacao.manifest/2")
        # No formato 2 a regra era só de nome: o arquivo da pasta de segredo entrava (e entra, ao verificar).
        self.assertIn(".segredos/setup_token", self.caminhos(antigo["arquivos"]))
        self.assertNotIn(".git/HEAD", self.caminhos(antigo["arquivos"]))
        self.man.write_text(json.dumps(antigo), encoding="utf-8")
        self.assertEqual(self.verificar(), (0, {"alterados": [], "ausentes": [], "novos": []}))

    def test_fora_do_manifesto_do_plano_ve_o_que_o_formato_3_nao_le(self):
        # codigo_do_plano.fora_do_manifesto, pela regra única e pela mesma varredura do formato 3, vê como não preso
        # tudo o que o formato 3 não lê: a pasta de segredo, o .git e os nomes fracos.
        self.criar()
        plano = carregar("codigo_do_plano")
        ref, politica, antigos = plano.ler_manifesto(self.man.read_bytes())
        fora = plano.fora_do_manifesto(str(self.raiz.resolve()), politica, antigos, str(self.man))
        for item in (".segredos/", "x/.envs/", ".git/", "tokenizer.py", "setup_token", ".env", ".env.example",
                     "node_modules/", ".venv/", "__pycache__/"):
            self.assertIn(item, fora)
        self.assertNotIn("a.txt", fora)
        self.assertEqual(sorted(f["path"] for f in ref["arquivos"]), [".cofre-ficticio/roteador.db", "a.txt", "src/app.py"])


if __name__ == "__main__":
    unittest.main()
