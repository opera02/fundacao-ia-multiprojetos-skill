"""Item I7 da integração da 1.7.10 (emenda E7 dos contratos do lote 2), na parte da trava do banco: o
`registro_atualizacao.user_version` — usado pelo `checar`, pelo `aplicar` e pelo `desfazer` do atualizar_fundacao.py —
confere `trava_banco.conferir(raiz / "state")` antes do `sqlite3.connect`. O marcador state/banco.trava do OUTRO lado
(vivo, velho ou ilegível) para na etapa `banco`, sem abrir o banco; o do mesmo lado, ou nenhum, não muda nada. Antes
da integração, o banco era aberto direto, sem a trava. Raiz descartável e marcador fictício; o "outro lado" é o oposto
do desta máquina."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from apoio import SCRIPTS

MESMO = "windows" if os.name == "nt" else "ubuntu"
OUTRO = "ubuntu" if os.name == "nt" else "windows"


def carregar(nome: str):
    spec = importlib.util.spec_from_file_location(f"_trava_i7_{nome}", SCRIPTS / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def marcador(lado: str = OUTRO, idade_s: float = 0) -> str:
    def iso(delta: float) -> str:
        return (datetime.now(timezone.utc) - timedelta(seconds=delta)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return json.dumps({"lado": lado, "host": "maquina-ficticia", "pid": 4242, "desde": iso(idade_s + 60),
                       "renovada_em": iso(idade_s)})


class RaizCase(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="trava-i7-"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.raiz = self.base / "raiz"
        (self.raiz / "state").mkdir(parents=True)
        (self.raiz / "fundacao").mkdir()
        (self.raiz / "fundacao" / "__init__.py").write_text('KIT_VERSION = "1.7.10"\n', encoding="utf-8")
        with contextlib.closing(sqlite3.connect(self.raiz / "state" / "state.sqlite")) as con:
            con.execute("CREATE TABLE ficticia (v TEXT)")
            con.execute("PRAGMA user_version = 5")
            con.commit()
        self.ra = carregar("registro_atualizacao")

    def marcar(self, conteudo: str) -> Path:
        arquivo = self.raiz / "state" / "banco.trava"
        arquivo.write_text(conteudo, encoding="utf-8")
        return arquivo


class TestUserVersionComATrava(RaizCase):
    def test_sem_marcador_e_com_o_do_mesmo_lado_abre(self):
        self.assertEqual(self.ra.user_version(self.raiz), 5)
        self.marcar(marcador(MESMO))
        self.assertEqual(self.ra.user_version(self.raiz), 5)
        self.marcar(marcador(MESMO, idade_s=10_000))  # velho do mesmo lado também não muda quem abre deste lado
        self.assertEqual(self.ra.user_version(self.raiz), 5)

    def test_marcador_vivo_do_outro_lado_para_sem_abrir_o_banco(self):
        arquivo = self.marcar(marcador(OUTRO))
        with mock.patch.object(self.ra.sqlite3, "connect", side_effect=AssertionError("abriu o banco")):
            with self.assertRaises(self.ra.Parada) as ctx:
                self.ra.user_version(self.raiz)
        p = ctx.exception
        self.assertEqual((p.etapa, p.detalhes["situacao"], p.detalhes["lado"]), ("banco", "vivo", OUTRO))
        self.assertIn("em uso", p.motivo)
        self.assertTrue(arquivo.exists(), "a conferência nunca tira o marcador")

    def test_marcador_velho_ou_ilegivel_do_outro_lado_tambem_para(self):
        for nome, conteudo, situacao in (("velho", marcador(OUTRO, idade_s=10_000), "velho"),
                                         ("ilegível", "{não é json", "ilegivel"),
                                         ("fora da forma", json.dumps({"lado": OUTRO}), "ilegivel")):
            with self.subTest(caso=nome):
                self.marcar(conteudo)
                with self.assertRaises(self.ra.Parada) as ctx:
                    self.ra.user_version(self.raiz)
                self.assertEqual((ctx.exception.etapa, ctx.exception.detalhes["situacao"]), ("banco", situacao))
                self.assertIn("banco destravar --confirmar", ctx.exception.motivo)

    def test_kit_de_outro_lugar_recusa_a_conferencia(self):
        """A trava vem do kit desta skill: com o `fundacao` carregado de outro lugar que não o kit esperado (aqui, o
        KIT apontado para a raiz), nada é conferido nem aberto, e o motivo diz isso."""
        self.assertEqual(self.ra.user_version(self.raiz), 5)  # o kit desta skill já carregado, como no uso real
        with mock.patch.object(self.ra, "KIT", self.raiz), mock.patch.object(sys, "path", list(sys.path)), \
                mock.patch.dict(sys.modules), \
                mock.patch.object(self.ra.sqlite3, "connect", side_effect=AssertionError("abriu o banco")):
            with self.assertRaises(self.ra.Parada) as ctx:
                self.ra.user_version(self.raiz)
        self.assertEqual(ctx.exception.etapa, "banco")
        self.assertIn("não foi conferida", ctx.exception.motivo)


class TestAtualizadorParaNaEtapaBanco(RaizCase):
    def test_desfazer_para_na_trava_antes_de_tudo(self):
        """O registro (mínimo e desta raiz) passa da conferência; sem a trava, o `desfazer` pararia no esquema do
        banco (etapa `desfazer`); com o marcador do outro lado, para antes, na etapa `banco`."""
        registro = self.raiz / "evidence" / "atualizacoes" / "ficticio.json"
        registro.parent.mkdir(parents=True)
        registro.write_text(json.dumps({"raiz": str(self.raiz.resolve()), "promocao": {}, "instrucoes_raiz": {}}),
                            encoding="utf-8")
        with self.assertRaises(self.ra.Parada) as ctx:
            self.ra.desfazer(registro, False)
        self.assertEqual(ctx.exception.etapa, "desfazer")  # sem marcador: o esquema (user_version 5 contra None)
        self.marcar(marcador(OUTRO))
        with self.assertRaises(self.ra.Parada) as ctx:
            self.ra.desfazer(registro, False)
        self.assertEqual((ctx.exception.etapa, ctx.exception.detalhes["situacao"]), ("banco", "vivo"))

    def test_checar_pelo_main_responde_em_json_com_a_etapa_banco(self):
        af = carregar("atualizar_fundacao")
        self.marcar(marcador(OUTRO))
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            codigo = af.main(["checar", "--raiz", str(self.raiz)])
        dados = json.loads(saida.getvalue())
        self.assertEqual(codigo, 1)
        self.assertEqual((dados["ok"], dados["etapa"], dados["situacao"], dados["lado"]), (False, "banco", "vivo",
                                                                                              OUTRO))
        self.assertNotIn("user_version", dados)
        (self.raiz / "state" / "banco.trava").unlink()
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            af.main(["checar", "--raiz", str(self.raiz)])
        self.assertEqual(json.loads(saida.getvalue())["user_version"], 5)  # sem marcador, o checar lê o banco


if __name__ == "__main__":
    unittest.main()
