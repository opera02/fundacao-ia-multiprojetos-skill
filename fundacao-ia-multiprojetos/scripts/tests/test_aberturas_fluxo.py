"""Fluxo inteiro da ficha de aberturas (1.7.10, contratos do lote 2, §5), numa fundação fictícia descartável:
levantamento (scripts/levantar_aberturas.py) -> preparo pelo kit (`abertura preparar`) -> assinatura pela ferramenta
fixa do titular (assets/host/fundacao_titular.py) -> ficha em vigor (`aberturas.vigente`, como o preparo do host a
chama). Chaves, âncora, identidades e projeto de ENSAIO; a confirmação do titular é injetada."""

from __future__ import annotations

import gc
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from apoio import KIT

if str(KIT) not in sys.path:  # o kit desta skill, o mesmo que a ferramenta do titular carrega
    sys.path.insert(0, str(KIT))
from fundacao import cli_aberturas  # noqa: E402
from fundacao.core import aberturas, decisoes  # noqa: E402
from fundacao.core.auth import Policy  # noqa: E402
from fundacao.core.backup import ensure_tombstone_log  # noqa: E402
from fundacao.core.db import connect  # noqa: E402
from fundacao.core.projects import create_project  # noqa: E402
from test_fundacao_titular import TITULAR  # noqa: E402
from test_levantar_aberturas import LEVANTAR  # noqa: E402

HOJE = date(2026, 10, 31)


class TestFluxoDaFicha(unittest.TestCase):
    def setUp(self):
        try:
            keygen = decisoes.ssh_keygen()
        except FileNotFoundError as exc:
            self.skipTest(f"ssh-keygen indisponível neste ambiente: {exc}")
        self.base = Path(tempfile.mkdtemp(prefix="aberturas-fluxo-"))
        self.raiz = self.base / "raiz"
        for area in ("fundacao", "templates"):
            shutil.copytree(KIT / area, self.raiz / area, ignore=shutil.ignore_patterns("__pycache__"))
        self.con = connect(self.raiz / "state" / "state.sqlite")
        ensure_tombstone_log(self.raiz / "state" / "retiradas.jsonl")
        self.titular = Policy(self.con).bootstrap_admin("titular-ensaio")
        create_project(self.raiz, self.con, self.titular, "juridico-lab", "Laboratório jurídico", "Fluxos fictícios")
        self.chave = self.base / "chaves" / "titular-ensaio"
        self.chave.parent.mkdir()
        subprocess.run([keygen, "-q", "-t", "ed25519", "-N", "", "-C", "titular-ensaio", "-f", str(self.chave)],
                       check=True, capture_output=True)
        self.ancora = self.base / "ancora" / "allowed_signers"
        self.ancora.parent.mkdir()
        pub = Path(str(self.chave) + ".pub").read_text(encoding="ascii").strip()
        self.ancora.write_text(f'titular-ensaio namespaces="fundacao-decisao,fundacao-abertura" {pub}\n',
                               encoding="ascii")
        padrao = mock.patch.object(decisoes, "ANCORAS_PADRAO", (str(self.ancora),))
        padrao.start()
        self.addCleanup(padrao.stop)

    def tearDown(self):
        self.con.close()
        gc.collect()
        shutil.rmtree(self.base, ignore_errors=True)

    def test_levantar_preparar_assinar_e_vigente(self):
        pasta = self.raiz / "projects" / "juridico-lab"
        (pasta / "requirements.txt").write_text("requests==2.0\n", encoding="utf-8")
        levantado = LEVANTAR.levantar(pasta, "juridico-lab")
        self.assertEqual(levantado["rascunho"]["rede"]["dominios"], ["files.pythonhosted.org", "pypi.org"])
        rascunho = {**levantado["rascunho"], "motivo": "Instalar as dependências do projeto (palavras fictícias).",
                    "consequencias": "Os comandos da sessão acessam o PyPI."}
        (pasta / "outputs" / "rascunho.json").write_text(json.dumps(rascunho, ensure_ascii=False), encoding="utf-8")

        preparada = cli_aberturas.preparar(self.raiz, self.con, self.titular, "juridico-lab", Path("outputs/rascunho.json"))
        self.assertEqual(preparada["versao"], 1)
        caixa = aberturas.caixa_de_entrada(self.raiz, "juridico-lab")
        self.assertFalse(aberturas.vigente(self.raiz, "juridico-lab", caixa, hoje=HOJE)["valida"])  # só preparada

        saida = io.StringIO()
        codigo = TITULAR.assinar_ficha(self.raiz, "juridico-lab", chave=self.chave, confirmar=lambda _t: "juridico-lab",
                                       saida=saida, hoje=HOJE)
        self.assertEqual(codigo, 0, saida.getvalue())

        r = aberturas.vigente(self.raiz, "juridico-lab", caixa, hoje=HOJE)
        self.assertTrue(r["valida"], r)
        self.assertEqual((r["versao"], r["ficha"]["rede"]["dominios"]), (1, ["files.pythonhosted.org", "pypi.org"]))
        self.assertEqual(r["sha256"], preparada["sha256"])

        # Fechar = versão nova sem o item; a maior assinada vale, e a v1 (mais aberta) não volta.
        fechado = {**rascunho, "rede": {"dominios": []}}
        (pasta / "outputs" / "rascunho.json").write_text(json.dumps(fechado, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(cli_aberturas.preparar(self.raiz, self.con, self.titular, "juridico-lab",
                                                Path("outputs/rascunho.json"))["versao"], 2)
        self.assertEqual(TITULAR.assinar_ficha(self.raiz, "juridico-lab", chave=self.chave, saida=io.StringIO(),
                                               confirmar=lambda _t: "juridico-lab", hoje=HOJE), 0)
        r = aberturas.vigente(self.raiz, "juridico-lab", caixa, hoje=HOJE)
        self.assertEqual((r["valida"], r["versao"], r["ficha"]["rede"]), (True, 2, {"dominios": []}))
        Path(str(caixa / "ficha-v2.json") + ".sig").write_bytes(b"estragada")
        r = aberturas.vigente(self.raiz, "juridico-lab", caixa, hoje=HOJE)
        self.assertEqual((r["valida"], r["versao"], r["ficha"]), (False, 2, None))


if __name__ == "__main__":
    unittest.main()
