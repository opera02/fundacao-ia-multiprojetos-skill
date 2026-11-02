"""copia_segura.py (1.7.10, contratos do lote 2, §8): a cópia única feita fora do sandbox a partir de área que a
sessão grava — sem seguir ligação nem vínculo físico, com rehash e nada no destino quando recusa."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import SCRIPTS, criar_ligacao_dir, rodar_script


def carregar():
    spec = importlib.util.spec_from_file_location("copia_segura_teste", SCRIPTS / "copia_segura.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class TestCopiaSegura(unittest.TestCase):
    def setUp(self):
        self.mod = carregar()
        self.base = Path(tempfile.mkdtemp(prefix="copia-segura-1710-"))
        self.addCleanup(self._apagar)
        self.proj = self.base / "proj"
        self.saida = self.base / "saida"
        self.proj.mkdir()
        self.saida.mkdir()

    def _apagar(self):
        def tirar(funcao, caminho, _erro):
            os.chmod(caminho, stat.S_IWRITE | stat.S_IREAD)
            funcao(caminho)
        shutil.rmtree(self.base, onerror=tirar)

    def escrever(self, rel: str, dados: bytes) -> Path:
        p = self.proj / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(dados)
        return p

    def sobras(self) -> list[str]:
        return [p.name for p in self.saida.iterdir() if p.name.startswith(self.mod.PREFIXO_TEMP)]

    def test_copia_e_confere_o_sha256(self):
        dados = b"conteudo ficticio\n" * 1000
        origem = self.escrever("a/b/arquivo.txt", dados)
        res = self.mod.copiar_conferindo(origem, self.saida / "copia.txt", dentro_de=self.proj,
                                         sha256_esperado=hashlib.sha256(dados).hexdigest())
        self.assertEqual((self.saida / "copia.txt").read_bytes(), dados)
        self.assertEqual(res["sha256"], hashlib.sha256(dados).hexdigest())
        self.assertEqual(res["bytes"], len(dados))
        self.assertEqual(self.sobras(), [])
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.lstat(self.saida / "copia.txt").st_mode), 0o444)
            self.assertEqual(res["modo"], 0o444)
        else:
            self.assertIsNone(res["modo"])

    @unittest.skipIf(os.name == "nt", "modo de arquivo do POSIX")
    def test_modo_none_guarda_o_bit_de_execucao(self):
        origem = self.escrever("rodar.sh", b"#!/bin/sh\necho ficticio\n")
        os.chmod(origem, 0o750)
        res = self.mod.copiar_conferindo(origem, self.saida / "rodar.sh", modo=None)
        self.assertEqual(res["modo"], 0o750)
        self.assertEqual(stat.S_IMODE(os.lstat(self.saida / "rodar.sh").st_mode), 0o750)

    def test_sha256_diferente_recusa_e_nao_deixa_nada(self):
        origem = self.escrever("x.txt", b"trocado depois da proposta\n")
        with self.assertRaises(self.mod.CopiaRecusada):
            self.mod.copiar_conferindo(origem, self.saida / "x.txt", sha256_esperado="0" * 64)
        self.assertFalse(os.path.lexists(self.saida / "x.txt"))
        self.assertEqual(self.sobras(), [])

    def test_destino_existente_recusa(self):
        origem = self.escrever("x.txt", b"novo\n")
        (self.saida / "x.txt").write_bytes(b"antigo\n")
        with self.assertRaises(self.mod.CopiaRecusada):
            self.mod.copiar_conferindo(origem, self.saida / "x.txt")
        self.assertEqual((self.saida / "x.txt").read_bytes(), b"antigo\n")

    def test_origem_que_nao_e_arquivo_comum_recusa(self):
        (self.proj / "pasta").mkdir()
        with self.assertRaises(self.mod.CopiaRecusada):
            self.mod.copiar_conferindo(self.proj / "pasta", self.saida / "pasta")
        with self.assertRaises(self.mod.CopiaRecusada):
            self.mod.copiar_conferindo(self.proj / "pasta", self.saida / "pasta", dentro_de=self.proj)
        self.assertFalse(os.path.lexists(self.saida / "pasta"))

    def test_link_simbolico_de_arquivo_recusa(self):
        fora = self.base / "fora.txt"
        fora.write_bytes(b"CANARIO-FICTICIO de fora\n")
        link = self.proj / "atalho.txt"
        try:
            link.symlink_to(fora)
        except OSError as exc:
            self.skipTest(f"link simbólico de arquivo indisponível: {exc}")
        for dentro_de in (None, self.proj):
            with self.subTest(dentro_de=dentro_de), self.assertRaises(self.mod.CopiaRecusada):
                self.mod.copiar_conferindo(link, self.saida / "atalho.txt", dentro_de=dentro_de)
        self.assertFalse(os.path.lexists(self.saida / "atalho.txt"))

    def test_vinculo_fisico_recusa(self):
        fora = self.base / "fora.txt"
        fora.write_bytes(b"CANARIO-FICTICIO de fora\n")
        vinculo = self.proj / "vinculo.txt"
        try:
            os.link(fora, vinculo)
        except OSError as exc:
            self.skipTest(f"vínculo físico indisponível: {exc}")
        for dentro_de in (None, self.proj):
            with self.subTest(dentro_de=dentro_de), self.assertRaises(self.mod.CopiaRecusada):
                self.mod.copiar_conferindo(vinculo, self.saida / "vinculo.txt", dentro_de=dentro_de)
        self.assertFalse(os.path.lexists(self.saida / "vinculo.txt"))

    def test_pasta_acima_trocada_por_ligacao_para_fora_recusa(self):
        # A crítica do desenho pediu este teste: uma pasta do projeto vira ligação para fora (outro projeto, state/).
        fora = self.base / "outro-projeto"
        fora.mkdir()
        (fora / "segredo.txt").write_bytes(b"CANARIO-FICTICIO de outro projeto\n")
        criar_ligacao_dir(self.proj / "sub", fora)
        with self.assertRaises(self.mod.CopiaRecusada):
            self.mod.copiar_conferindo(self.proj / "sub" / "segredo.txt", self.saida / "s.txt", dentro_de=self.proj)
        with self.assertRaises(self.mod.CopiaRecusada):
            self.mod.hash_conferido(self.proj / "sub" / "segredo.txt", dentro_de=self.proj)
        self.assertFalse(os.path.lexists(self.saida / "s.txt"))
        self.assertEqual(self.sobras(), [])

    def test_origem_fora_de_dentro_de_recusa(self):
        fora = self.base / "fora.txt"
        fora.write_bytes(b"fora\n")
        with self.assertRaises(self.mod.CopiaRecusada):
            self.mod.copiar_conferindo(fora, self.saida / "fora.txt", dentro_de=self.proj)
        with self.assertRaises(self.mod.CopiaRecusada):
            self.mod.copiar_conferindo(self.proj / ".." / "fora.txt", self.saida / "fora.txt", dentro_de=self.proj)

    def test_pasta_do_destino_ligacao_recusa(self):
        origem = self.escrever("x.txt", b"x\n")
        alvo = self.base / "alvo"
        alvo.mkdir()
        criar_ligacao_dir(self.saida / "ligada", alvo)
        with self.assertRaises(self.mod.CopiaRecusada):
            self.mod.copiar_conferindo(origem, self.saida / "ligada" / "x.txt")
        self.assertEqual(list(alvo.iterdir()), [])

    def test_troca_entre_exame_e_abertura_recusa(self):
        # Caminho sem `dentro_de` (e o do Windows): o objeto aberto tem de ser o do exame.
        origem = self.escrever("x.txt", b"legitimo\n")
        outro = self.escrever("outro.txt", b"outro\n")
        real = os.lstat

        def lstat(caminho, *a, **k):
            return real(outro) if Path(caminho) == Path(os.path.abspath(origem)) else real(caminho, *a, **k)

        with mock.patch.object(self.mod.os, "lstat", side_effect=lstat), self.assertRaises(self.mod.CopiaRecusada):
            self.mod.copiar_conferindo(origem, self.saida / "x.txt")
        self.assertFalse(os.path.lexists(self.saida / "x.txt"))

    def test_linha_de_comando(self):
        dados = b"pela linha de comando\n"
        origem = self.escrever("cli.txt", dados)
        r = rodar_script("copia_segura.py", "copiar", "--origem", origem, "--destino", self.saida / "cli.txt",
                         "--sha256", hashlib.sha256(dados).hexdigest(), "--dentro-de", self.proj)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["sha256"], hashlib.sha256(dados).hexdigest())
        r = rodar_script("copia_segura.py", "copiar", "--origem", origem, "--destino", self.saida / "cli2.txt",
                         "--sha256", "1" * 64)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("erro", json.loads(r.stdout))
        r = rodar_script("copia_segura.py", "hash", origem)
        self.assertEqual((r.returncode, json.loads(r.stdout)["bytes"]), (0, len(dados)))


if __name__ == "__main__":
    unittest.main()
