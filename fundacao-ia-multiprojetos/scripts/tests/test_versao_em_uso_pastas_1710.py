"""Revisão 1 da correção do grupo VERSAO (revisão de segurança da 1.7.10, rodada 4), KIT-F5: `scripts/versao_em_uso.py`.

A pasta com a listagem negada (chmod 0o311 no POSIX; no Windows, a ACL que nega só RD) continua alcançável pelo
caminho: um .pyc plantado em `atual/__pycache__/` assim rodava, e o os.walk sem onerror a pulava calado (o conferir
dava código 0). Agora ela vai para `ilegiveis` (código 1, com a dica), a anterior do voltar com ela é recusada e o
propor a põe nos excluídos. E `.venv`/`venv` só ficam fora da conferência se são ambiente virtual de verdade
(`pyvenv.cfg` no topo, sem `__init__` nem `__main__`): uma venv/ com eles faz sombra ao venv da biblioteca padrão para
o python -m venv rodado de atual/ (sem -I), e o conferir dizia só "não conferido".
A verificação do kit é simulada, como nos testes do pacote. Raiz fictícia em pasta temporária.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import SCRIPTS, rodar_script

PYC = f"util.{sys.implementation.cache_tag}.pyc"


def carregar():
    spec = importlib.util.spec_from_file_location("_teste_versao_pastas_1710", SCRIPTS / "versao_em_uso.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


MOD = carregar()


def aceite(alvo: dict):
    """A verificação simulada do kit: aceite assinado sobre a entrega `alvo`; uma decisão por entrega, como no kit."""
    v = {"valida": True, "tipo": "aceite", "forca": "assinatura", "motivo": "decisão assinada pelo titular",
         "entrega": {"caminho": alvo["entrega"], "sha256": alvo["sha256"]}, "decisao_id": "dec-" + alvo["sha256"][:8],
         "sha256_decisao": hashlib.sha256(b"decisao ficticia de " + alvo["sha256"].encode()).hexdigest()}
    return lambda _raiz, _decisao: v


class _Raiz(unittest.TestCase):
    """Uma versão em uso (util.QUEM = 'LEGITIMO') promovida com o aceite simulado."""

    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="versao-pastas-")))
        self.addCleanup(MOD._apagar, self.base)
        self.raiz = self.base / "raiz"
        self.projeto = self.raiz / "projects" / "p"
        self.trabalho = self.projeto / "trabalho"
        self.trabalho.mkdir(parents=True)
        (self.trabalho / "main.py").write_bytes(b"import util\nprint('resultado:', util.QUEM)\n")
        (self.projeto / "decisoes").mkdir()
        self.decisao = self.projeto / "decisoes" / "dec.json"
        self.decisao.write_text("{}", encoding="utf-8")
        self.lista = self.base / "lista.txt"
        self.lista.write_text("**/*.py\n", encoding="utf-8")
        self.em_uso = self.raiz / "em-uso" / "p"
        self.atual = self.em_uso / "atual"
        self.promover(self.propor("v1.json", "LEGITIMO"))

    def propor(self, nome: str, quem: str) -> dict:
        (self.trabalho / "util.py").write_bytes(f"QUEM = {quem!r}\n".encode())
        return MOD.propor(self.raiz, "p", self.trabalho, self.lista, self.projeto / "outputs" / "versao" / nome)

    def promover(self, proposta: dict) -> dict:
        return MOD.promover(self.raiz, "p", proposta["proposta"], proposta["sha256"], self.decisao,
                            verificar=aceite(proposta))

    def em_uso_agora(self) -> bytes:
        return (self.atual / "util.py").read_bytes()

    def conferir_pela_linha_de_comando(self):
        return rodar_script("versao_em_uso.py", "conferir", "--raiz", self.raiz, "--projeto", "p")


class TestPastaQueNaoSeLista(_Raiz):
    @staticmethod
    def negar_listagem(alvo: Path):
        """O os.scandir (o que o os.walk usa) que nega a listagem de `alvo`, como o chmod 0o311 e a ACL sem RD."""
        real, negada = os.scandir, os.path.normcase(os.path.abspath(alvo))

        def scandir(caminho="."):
            if not isinstance(caminho, int) and os.path.normcase(os.path.abspath(caminho)) == negada:
                raise PermissionError(13, "listagem negada (simulada pelo teste)", os.fspath(caminho))
            return real(caminho)
        return mock.patch.object(os, "scandir", scandir)

    @staticmethod
    def plantar_pyc(pasta: Path) -> Path:
        (pasta / "__pycache__").mkdir()
        (pasta / "__pycache__" / PYC).write_bytes(b"\0")
        return pasta / "__pycache__"

    def test_conferir_acusa_a_pasta_que_nao_se_lista(self):
        with self.negar_listagem(self.plantar_pyc(self.atual)):
            res = MOD.conferir(self.raiz, "p")
            with mock.patch.object(sys, "stdout", io.StringIO()), mock.patch.object(sys, "stderr", io.StringIO()):
                codigo = MOD.main(["conferir", "--raiz", str(self.raiz), "--projeto", "p"])
        self.assertEqual((res["a_mais"], res["ilegiveis"], res["ok"], codigo), ([], ["__pycache__"], False, 1))
        self.assertIn("pasta que não se lista", res["dica"])

    @unittest.skipIf(os.name == "nt", "chmod não nega a listagem no Windows (lá, a ACL; aqui, o os.scandir simulado)")
    def test_no_posix_com_chmod_pela_linha_de_comando(self):
        pasta = self.plantar_pyc(self.atual)
        os.chmod(pasta, 0o311)
        self.addCleanup(os.chmod, pasta, 0o755)
        try:
            os.listdir(pasta)
        except PermissionError:
            pass
        else:
            self.skipTest("a listagem não foi negada (rodando como root?)")
        r = self.conferir_pela_linha_de_comando()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["ilegiveis"], ["__pycache__"])

    def test_voltar_recusa_a_anterior_com_pasta_que_nao_se_lista(self):
        self.promover(self.propor("v2.json", "v2"))
        anterior = self.em_uso / "anteriores" / sorted(os.listdir(self.em_uso / "anteriores"))[0]
        pedido = MOD.pedir_volta(self.raiz, "p", self.projeto / "outputs" / "versao" / "volta.json",
                                 motivo="voltar a anterior (fictício)")
        with self.negar_listagem(self.plantar_pyc(anterior)), self.assertRaises(MOD.Recusa) as ctx:
            MOD.voltar(self.raiz, "p", pedido["pedido"], pedido["sha256"], self.decisao, verificar=aceite(pedido))
        self.assertIn("pasta que não se lista", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v2'\n")

    def test_propor_poe_a_pasta_que_nao_se_lista_nos_excluidos(self):
        (self.trabalho / "lib").mkdir()
        (self.trabalho / "lib" / "x.py").write_bytes(b"X = 1\n")
        with self.negar_listagem(self.trabalho / "lib"):
            res = self.propor("v2.json", "v2")
        self.assertTrue(any(e["caminho"] == "lib/" and "não se lista" in e["motivo"] for e in res["excluidos"]))
        self.assertNotIn("lib/x.py", [a["caminho"] for a in json.loads(Path(res["proposta"]).read_bytes())["arquivos"]])


class TestVenvSoDeVerdade(_Raiz):
    def plantar(self, *rels: str) -> None:
        for rel in rels:
            (self.atual / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.atual / rel).write_bytes(b"print('PLANTADO')\n")

    def test_venv_sem_pyvenv_cfg_conta_como_a_mais(self):
        self.plantar("venv/__init__.py", "venv/__main__.py")
        res = MOD.conferir(self.raiz, "p")
        self.assertEqual((res["a_mais"], res["nao_conferido"], res["ok"]),
                         (["venv/__init__.py", "venv/__main__.py"], [], False))
        r = self.conferir_pela_linha_de_comando()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_venv_com_pyvenv_cfg_e_init_conta_e_faria_sombra(self):
        # O pyvenv.cfg sozinho não basta: com __init__ e __main__, a venv/ é um pacote, e o python -m venv rodado de
        # atual/ sem -I roda o código plantado no lugar do venv da biblioteca padrão; com -I, não.
        self.plantar("venv/pyvenv.cfg", "venv/__init__.py", "venv/__main__.py")
        res = MOD.conferir(self.raiz, "p")
        self.assertEqual(res["a_mais"], ["venv/__init__.py", "venv/__main__.py", "venv/pyvenv.cfg"])
        self.assertFalse(res["ok"])
        rodar = dict(cwd=str(self.atual), capture_output=True, text=True, encoding="utf-8", errors="replace",
                     timeout=120)
        sem_i = subprocess.run([sys.executable, "-E", "-s", "-B", "-m", "venv", "--help"], **rodar)
        com_i = subprocess.run([sys.executable, "-I", "-B", "-m", "venv", "--help"], **rodar)
        self.assertIn("PLANTADO", sem_i.stdout)
        self.assertNotIn("PLANTADO", com_i.stdout + com_i.stderr)
        self.assertEqual(com_i.returncode, 0, com_i.stderr)
        # Só o __init__, em outra caixa: no NTFS o Python o acha por stat, sem caixa, e a venv/ ainda é pacote.
        (self.atual / "venv" / "__main__.py").unlink()
        (self.atual / "venv" / "__init__.py").rename(self.atual / "venv" / "__INIT__.PY")
        self.assertEqual(MOD.conferir(self.raiz, "p")["a_mais"], ["venv/__INIT__.PY", "venv/pyvenv.cfg"])

    def test_ambiente_virtual_de_verdade_nao_conferido_e_dito(self):
        self.plantar(".venv/pyvenv.cfg", ".venv/lib/site-packages/m.py", "node_modules/m/index.js")
        res = MOD.conferir(self.raiz, "p")
        self.assertEqual((res["a_mais"], res["nao_conferido"], res["ok"]), ([], [".venv/", "node_modules/"], True))
        self.assertIn("não conferido: .venv/", res["aviso"])
        r = self.conferir_pela_linha_de_comando()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("não conferido: .venv/", json.loads(r.stderr)["aviso"])


if __name__ == "__main__":
    unittest.main()
