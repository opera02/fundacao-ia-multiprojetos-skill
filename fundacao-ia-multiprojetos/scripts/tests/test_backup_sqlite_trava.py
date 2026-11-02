"""Item I7 da integração da 1.7.10 (emenda E7 dos contratos do lote 2), na parte da trava do banco: o
`backup_sqlite.py` confere `trava_banco.conferir` na pasta da origem antes do `sqlite3.connect`. O marcador
`banco.trava` do OUTRO lado (o state/ da fundação que o porteiro do Ubuntu segura) recusa, vivo, velho ou ilegível:
código 1, erro em JSON, nada aberto e nada criado no destino. O do mesmo lado, ou nenhum (o banco de um projeto
qualquer), não muda nada. Antes da integração, a origem era aberta direto. Pastas descartáveis e dados fictícios."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from apoio import ENV, SCRIPTS

MESMO = "windows" if os.name == "nt" else "ubuntu"
OUTRO = "ubuntu" if os.name == "nt" else "windows"


def carregar():
    spec = importlib.util.spec_from_file_location("_trava_i7_backup_sqlite", SCRIPTS / "backup_sqlite.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def marcador(lado: str = OUTRO, idade_s: float = 0) -> str:
    def iso(delta: float) -> str:
        return (datetime.now(timezone.utc) - timedelta(seconds=delta)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return json.dumps({"lado": lado, "host": "maquina-ficticia", "pid": 4242, "desde": iso(idade_s + 60),
                       "renovada_em": iso(idade_s)})


class TestBackupSqliteComATrava(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="trava-i7-sqlite-"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.estado = self.base / "raiz" / "state"
        self.estado.mkdir(parents=True)
        self.origem = self.estado / "state.sqlite"
        with contextlib.closing(sqlite3.connect(self.origem)) as con:
            con.execute("PRAGMA journal_mode = WAL")
            con.execute("CREATE TABLE itens (v TEXT)")
            con.execute("INSERT INTO itens VALUES ('fictício')")
            con.commit()
        self.mod = carregar()

    def main(self, destino: Path, origem: Path | None = None) -> tuple[int, dict]:
        saida = io.StringIO()
        argv = [str(SCRIPTS / "backup_sqlite.py"), "--origem", str(origem or self.origem), "--destino", str(destino)]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(saida):
            codigo = self.mod.main()
        return codigo, json.loads(saida.getvalue())

    def marcar(self, conteudo: str, pasta: Path | None = None) -> None:
        ((pasta or self.estado) / "banco.trava").write_text(conteudo, encoding="utf-8")

    def test_sem_marcador_e_com_o_do_mesmo_lado_copia(self):
        codigo, r = self.main(self.base / "ref" / "copia-1.sqlite")
        self.assertEqual((codigo, r["ok"], r["copia"]["tabelas"]), (0, True, {"itens": 1}))
        self.marcar(marcador(MESMO))
        codigo, r = self.main(self.base / "ref" / "copia-2.sqlite")
        self.assertEqual((codigo, r["ok"]), (0, True))

    def test_marcador_vivo_do_outro_lado_recusa_sem_abrir_nem_criar(self):
        self.marcar(marcador(OUTRO))
        destino = self.base / "ref" / "sub" / "copia.sqlite"
        with mock.patch.object(self.mod.sqlite3, "connect", side_effect=AssertionError("abriu o banco")):
            codigo, r = self.main(destino)
        self.assertEqual((codigo, r["tipo"]), (1, "BancoTravado"))
        self.assertIn("em uso pelo outro lado", r["erro"])
        self.assertIn("em uso", r["detalhe"])
        self.assertFalse((self.base / "ref").exists(), "nada criado no destino")
        self.assertEqual(sorted(p.name for p in self.estado.iterdir()), ["banco.trava", "state.sqlite"])  # sem -wal

    def test_marcador_velho_ou_ilegivel_do_outro_lado_recusa_com_o_comando_do_titular(self):
        for n, conteudo in enumerate((marcador(OUTRO, idade_s=10_000), "lixo que não é json")):
            with self.subTest(n=n):
                self.marcar(conteudo)
                codigo, r = self.main(self.base / f"copia-{n}.sqlite")
                self.assertEqual((codigo, r["tipo"]), (1, "BancoTravado"))
                self.assertIn("banco destravar --confirmar", r["detalhe"])
                self.assertFalse((self.base / f"copia-{n}.sqlite").exists())

    def test_banco_de_projeto_sem_marcador_na_pasta_dele_nao_muda(self):
        """A trava é da pasta do banco: o marcador do state/ da fundação não toca o banco de outra pasta."""
        self.marcar(marcador(OUTRO))
        projeto = self.base / "projeto-ficticio" / "app.sqlite"
        projeto.parent.mkdir()
        shutil.copy2(self.origem, projeto)
        codigo, r = self.main(self.base / "ref" / "app.sqlite", origem=projeto)
        self.assertEqual((codigo, r["ok"]), (0, True))

    def test_summary_tambem_confere(self):
        self.assertEqual(self.mod.summary(self.origem)["tabelas"], {"itens": 1})
        self.marcar(marcador(OUTRO))
        with self.assertRaises(Exception) as ctx:
            self.mod.summary(self.origem)
        self.assertEqual(type(ctx.exception).__name__, "BancoTravado")

    def test_com_menos_i_como_o_importar_chama(self):
        """O importar.py roda `python -I -B backup_sqlite.py`: sem a pasta do script no sys.path, o kit desta skill
        ainda é achado (pelo caminho do arquivo), e a recusa sai em JSON."""
        self.marcar(marcador(OUTRO))
        destino = self.base / "ref" / "copia.sqlite"
        p = subprocess.run([sys.executable, "-I", "-B", str(SCRIPTS / "backup_sqlite.py"), "--origem", str(self.origem),
                            "--destino", str(destino)], capture_output=True, text=True, encoding="utf-8", env=ENV,
                           timeout=120)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertEqual(json.loads(p.stdout)["tipo"], "BancoTravado")
        self.assertFalse(destino.exists())


if __name__ == "__main__":
    unittest.main()
