"""Restauração reaplica revogação com o mesmo alcance de revisões do serviço (1.5.0; scan da 1.4.5, #21): revogar
leitura no comum muda a política do comum e de todos os projetos, então caches de projeto que citam o comum não
servem mais na raiz restaurada."""

from __future__ import annotations

import shutil
import sqlite3

from helpers import FoundationTestCase

from fundacao.core import backup, revisions
from fundacao.core.db import connect


def politica(con, escopo: str) -> int:
    return revisions.get(con, escopo)[0]


class TestRestauracaoRevisoes(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.snap = self.root.parent / (self.root.name + "-snap")
        self.dest = self.root.parent / (self.root.name + "-dest")

    def tearDown(self):
        shutil.rmtree(self.snap, ignore_errors=True)
        shutil.rmtree(self.dest, ignore_errors=True)
        super().tearDown()

    def test_revogacao_no_comum_reaplicada_alcanca_os_projetos(self):
        backup.create_backup(self.root, self.snap, "rev-comum")
        copia = sqlite3.connect((self.snap / "state" / "state.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
        copia.row_factory = sqlite3.Row
        try:
            antes = politica(copia, "project:juridico-lab")
        finally:
            copia.close()
        self.policy.revoke(self.admin, "operador-juridico", "common", "read")
        rep = backup.restore(self.snap, self.dest, self.root / "state" / "retiradas.jsonl")
        self.assertTrue(rep["released"], rep)
        con2 = connect(self.dest / "state" / "state.sqlite")
        try:
            self.assertGreater(politica(con2, "project:juridico-lab"), antes)
        finally:
            con2.close()
