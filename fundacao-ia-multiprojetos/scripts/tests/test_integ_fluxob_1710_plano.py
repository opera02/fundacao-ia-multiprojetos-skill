"""Integração do fluxo B na 1.7.10 (pacote INTEG-FLUXOB do lote 2), item 1: com a política do formato 3 (`modo_git`),
`codigo_do_plano.fora_do_manifesto` classifica pela regra única, e não pelas chaves do formato 2 (defeito 8 do
FLUXOB-A, deferido à integração).

Antes: a pasta de segredo com a caixa diferente da gravada (`Credentials/`) era podada pelo manifesto mas ficava como
presa no plano; o nome fraco levado com `--incluir-fraco` depois do `segredos.py conferir` continuava não preso (o plano
não destravava); e o `.git` do modo incluir não listava o que o manifesto não lê. Pastas descartáveis, conteúdo
fictício.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import SCRIPTS, rodar_script

MOTIVO = "fixture própria e fictícia do teste da integração do fluxo B"


def carregar(nome: str):
    spec = importlib.util.spec_from_file_location(f"_teste_integ_plano_{nome}", SCRIPTS / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


EX = carregar("execucao_isolada")
CODIGO = EX.CODIGO
ARQUIVOS = {"app.py": "print('ok')\n", "tokenizer.py": "def tokenizar(texto):\n    return texto.split()\n",
            "setup_token": "valor de teste\n", "Credentials/chave.txt": "conteúdo fictício\n",
            "Credentials/run.py": "print('de dentro')\n", "entradas/um.json": "{}\n"}
GIT = {".git/HEAD": "ref: refs/heads/main\n", ".git/config": "[core]\n", ".git/hooks/pre-commit": "#!/bin/sh\n",
       ".git/objects/ab/cdef": "objeto", ".git/refs/heads/main": "0" * 40 + "\n", ".git/packed-refs": "# pacotes\n",
       ".git/index": "indice", ".git/logs/HEAD": "log", "sub/.git": "gitdir: ../.git/worktrees/sub\n"}


class _Copia(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="integ-plano-")))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.copia = self.base / "copia"
        self.escrever(ARQUIVOS)
        self.man = self.base / "manifesto.json"

    def escrever(self, arquivos: dict) -> None:
        for rel, texto in arquivos.items():
            p = self.copia / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(texto, encoding="utf-8", newline="\n")

    def manifesto(self, *extra) -> Path:
        r = rodar_script("manifesto.py", "criar", "--raiz", self.copia, "--saida", self.man, *extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return self.man

    def fora(self) -> list[str]:
        _ref, politica, antigos = CODIGO.ler_manifesto(self.man.read_bytes())
        return CODIGO.fora_do_manifesto(str(self.copia), politica, antigos, str(self.man))

    def plano(self, script: str, cwd: Path | None = None) -> dict:
        """Plano sem isolamento (vale em qualquer sistema), com a cópia e o manifesto: nada roda."""
        return EX.montar_plano("gravar", [sys.executable, str(self.copia / script), "{entrada}"], copia=str(self.copia),
                               manifesto=str(self.man), cwd=str(cwd) if cwd else None,
                               entradas=[str(self.copia / "entradas" / "um.json")], gravavel=None,
                               limites=EX.limites(30), variaveis=[], sem_isolamento=MOTIVO)


class TestRegraUnicaNoPlano(_Copia):
    def test_pasta_de_segredo_com_outra_caixa_fica_fora_e_nao_presa(self):
        self.manifesto()
        fora = self.fora()
        self.assertIn("Credentials/", fora)
        self.assertFalse([f for f in fora if f.startswith("Credentials/") and f != "Credentials/"],
                         "a pasta de segredo é dada inteira, sem listar o que tem dentro")
        with self.assertRaises(EX.Recusa) as ctx:  # o script dentro dela não está preso
            self.plano("Credentials/run.py")
        self.assertIn("que o manifesto não prende", str(ctx.exception))
        plano = self.plano("app.py", cwd=self.copia / "Credentials")  # pasta de trabalho no que ele não prende
        self.assertTrue(plano["codigo_executado"].startswith("NÃO PRESO"), plano["codigo_executado"])
        self.assertTrue(any("pasta de trabalho" in m for m in plano["codigo_nao_preso"]), plano["codigo_nao_preso"])

    def test_incluir_fraco_depois_do_segredos_conferir_destrava_o_plano(self):
        self.manifesto()
        self.assertIn("tokenizer.py", self.fora())
        with self.assertRaises(EX.Recusa) as ctx:
            self.plano("tokenizer.py")
        self.assertIn("que o manifesto não prende", str(ctx.exception))
        # B7: o titular confere o conteúdo e leva o nome fraco; o plano passa a prender o script.
        conferencia = rodar_script("segredos.py", "conferir", self.copia / "tokenizer.py")
        self.assertEqual(conferencia.returncode, 0, conferencia.stdout + conferencia.stderr)
        self.manifesto("--incluir-fraco", "tokenizer.py")
        fora = self.fora()
        self.assertNotIn("tokenizer.py", fora)
        self.assertIn("setup_token", fora, "o fraco não levado continua fora")
        plano = self.plano("tokenizer.py")
        self.assertTrue(plano["codigo_executado"].startswith("preso pelo manifesto"), plano["codigo_executado"])
        EX.conferir(plano)  # a cópia confere com o plano, sem diferença

    def test_novo_nome_fraco_depois_do_aceite_para_a_execucao(self):
        self.manifesto()
        plano = self.plano("app.py")
        EX.conferir(plano)
        (self.copia / "novo_token.txt").write_text("x\n", encoding="utf-8")
        with self.assertRaises(EX.Recusa) as ctx:
            EX.conferir(plano)
        self.assertIn("novo fora do manifesto: novo_token.txt", str(ctx.exception))


class TestGitPeloModo(_Copia):
    def setUp(self):
        super().setUp()
        self.escrever(GIT)

    def test_listar_e_ignorar_deixam_o_git_inteiro_fora(self):
        for modo in ("listar", "ignorar"):
            with self.subTest(modo=modo):
                self.manifesto("--git", modo)
                fora = self.fora()
                self.assertIn(".git/", fora)
                self.assertIn("sub/.git", fora, "o arquivo .git de uma worktree também não fica preso")
                self.assertFalse([f for f in fora if f.startswith(".git/") and f != ".git/"], fora)

    def test_incluir_lista_config_hooks_e_o_resto_do_git(self):
        self.manifesto("--git", "incluir")
        fora = self.fora()
        for item in (".git/config", ".git/hooks/", ".git/index", ".git/logs/"):
            self.assertIn(item, fora)
        for preso in (".git/", ".git/HEAD", ".git/packed-refs", ".git/objects/ab/cdef", ".git/refs/heads/main",
                      "sub/.git"):
            self.assertNotIn(preso, fora)
        plano = self.plano("app.py")
        self.assertEqual(sorted(plano["manifesto"]["fora_do_manifesto"]), sorted(fora))
        EX.conferir(plano)
        (self.copia / ".git" / "hooks" / "post-checkout").write_text("#!/bin/sh\n", encoding="utf-8")
        EX.conferir(plano)  # dentro de hooks/, que fica fora inteiro: não muda o que o plano lista
        (self.copia / ".git" / "FETCH_HEAD").write_text("x\n", encoding="utf-8")
        with self.assertRaises(EX.Recusa):
            EX.conferir(plano)


@unittest.skipUnless(sys.platform.startswith("linux"), "nome fora do UTF-8 (bytes no caminho): Linux")
class TestNomeForaDoUtf8(_Copia):
    """Revisão do pacote: o ramo do nome fora do UTF-8 (`ascii`) de `_fora_do_formato3` e de `_fora_do_git`, como o
    manifesto o registra."""

    def criar_em_bytes(self, rel: bytes) -> None:
        fd = os.open(os.fsencode(str(self.copia)) + b"/" + rel, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        try:
            os.write(fd, b"conteudo ficticio\n")
        finally:
            os.close(fd)

    def test_nome_fora_do_utf8_sai_como_ascii_e_o_plano_monta(self):
        self.criar_em_bytes(b"relat\xf3rio.txt")
        self.manifesto()
        nome = ascii("relat\udcf3rio.txt")
        self.assertIn(nome, self.fora())
        plano = self.plano("app.py")
        self.assertIn(nome, plano["manifesto"]["fora_do_manifesto"])
        EX.conferir(plano)  # a cópia confere com o plano, com o nome fora do UTF-8 fora dele

    def test_nome_fora_do_utf8_dentro_do_git_do_modo_incluir(self):
        self.escrever(GIT)
        # O manifesto vem antes dos nomes: com eles dentro do .git, o manifesto.py criar ainda falha no modo incluir
        # (pendência fora do pacote, registrada); o plano lê o .git pela varredura dele mesmo.
        self.manifesto("--git", "incluir")
        self.criar_em_bytes(b".git/estado-\xf3")
        self.criar_em_bytes(b".git/refs/heads/ram\xf3")
        fora = self.fora()
        self.assertIn(ascii(".git/estado-\udcf3"), fora)
        self.assertIn(ascii(".git/refs/heads/ram\udcf3"), fora)
        self.assertNotIn(".git/refs/heads/main", fora, "o resto de refs/ continua preso")


class TestFormatoAntigo(_Copia):
    def test_manifesto_do_formato_2_continua_pelas_chaves_antigas(self):
        manifesto = CODIGO.MANIFESTO
        self.man.write_text(json.dumps(manifesto.build(self.copia, manifesto.politica_padrao())), encoding="utf-8")
        fora = self.fora()
        self.assertNotIn("tokenizer.py", fora, "no formato 2 o tokenizer.py está na lista de arquivos (preso)")
        self.assertNotIn("Credentials/", fora, "o formato 2 lia a pasta: o plano não muda de regra por baixo dele")


if __name__ == "__main__":
    unittest.main()
