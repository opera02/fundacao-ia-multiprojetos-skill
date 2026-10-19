"""A20/A05/A35 — caches com isolamento e invalidação; backup, restauração e retiradas (R28, R31, R44, R45)."""

from __future__ import annotations

import shutil
import unittest

from helpers import FoundationTestCase

from fundacao.core import backup
from fundacao.core.auth import resource_project
from fundacao.core.cache import ResponseCache
from fundacao.core.db import connect
from fundacao.core.knowledge import KnowledgeService
from test_conhecimento import APROVADO, G2P1, G3V1


class TestCache(FoundationTestCase):
    def meta(self, cache, project="juridico-lab"):
        return cache.server_meta(project, provider_id="simulado-a", model_revision="sim-1",
                                 prompt_revision="p1", context_hash="ctx", generation_config={"t": "0"})

    def test_frio_quente_e_outra_identidade(self):
        c = ResponseCache(self.con, self.jur)
        m = self.meta(c)
        self.assertEqual(c.get("juridico-lab", "dia do relatório?", m)[0], "miss")
        c.put("juridico-lab", "dia do relatório?", m, {"resposta": "quinta"}, ["juridico-lab/GUIA-003@2"])
        self.assertEqual(c.get("juridico-lab", "dia do relatório?", m), ("hit", {"resposta": "quinta"}))
        ce = ResponseCache(self.con, self.eng)
        self.assertEqual(ce.get("juridico-lab", "dia do relatório?", self.meta(ce))[0], "denied")

    def test_revogacao_vale_antes_do_ttl_inclusive_por_id(self):
        c = ResponseCache(self.con, self.jur)
        m = self.meta(c)
        key = c.put("juridico-lab", "q", m, {"r": 1}, ["juridico-lab/GUIA-001@1"], ttl_seconds=3600)
        self.policy.revoke(self.admin, "operador-juridico", resource_project("juridico-lab"), "read")
        self.assertEqual(c.get("juridico-lab", "q", m)[0], "denied")
        self.assertEqual(c.get_by_key("juridico-lab", key)[0], "denied")

    def test_fonte_retirada_e_corpus_alterado_invalidam(self):
        self.write_data("juridico-lab", "fontes/g2.md", G2P1)
        kj = KnowledgeService(self.root, self.con, self.jur)
        kr = KnowledgeService(self.root, self.con, self.revisor)
        kj.register_source("juridico-lab", "juridico-lab/GUIA-002", 1, "fontes/g2.md")
        h = kj.prepare("juridico-lab/GUIA-002", 1, [G2P1])
        kj.index("juridico-lab/GUIA-002", 1)
        kr.curate("juridico-lab/GUIA-002", 1, APROVADO, h, "2026-11-18", "lab")
        c = ResponseCache(self.con, self.jur)
        m = self.meta(c)
        c.put("juridico-lab", "anexos?", m, {"r": "nome, versão, origem"}, ["juridico-lab/GUIA-002@1"])
        self.assertEqual(c.get("juridico-lab", "anexos?", m)[0], "hit")
        kr.withdraw("juridico-lab/GUIA-002", 1, "retirada")
        self.assertIn(c.get("juridico-lab", "anexos?", m)[0], ("invalid", "miss"))
        # Resultado negativo antigo não pode persistir depois de nova fonte aprovada.
        m2 = self.meta(c)
        c.put("juridico-lab", "relatório?", m2, {"r": "nada encontrado"}, [])
        self.write_data("juridico-lab", "fontes/g3.md", G3V1)
        kj.register_source("juridico-lab", "juridico-lab/GUIA-003", 1, "fontes/g3.md")
        h3 = kj.prepare("juridico-lab/GUIA-003", 1, [G3V1])
        kr.curate("juridico-lab/GUIA-003", 1, APROVADO, h3, "2026-11-18", "lab")
        self.assertEqual(c.get("juridico-lab", "relatório?", m2)[0], "invalid")


class TestBackupRestauracao(FoundationTestCase):
    def test_referencia_restaurada_reaplica_retiradas(self):
        self.write_data("juridico-lab", "fontes/g2.md", G2P1)
        kj = KnowledgeService(self.root, self.con, self.jur)
        kr = KnowledgeService(self.root, self.con, self.revisor)
        kj.register_source("juridico-lab", "juridico-lab/GUIA-002", 1, "fontes/g2.md")
        h = kj.prepare("juridico-lab/GUIA-002", 1, [G2P1])
        kj.index("juridico-lab/GUIA-002", 1)
        kr.curate("juridico-lab/GUIA-002", 1, APROVADO, h, "2026-11-18", "lab")
        snap = self.root.parent / (self.root.name + "-snapshot")
        manifest = backup.create_backup(self.root, snap, "baseline-a05-001")
        self.assertEqual(manifest["db"]["integrity_check"], "ok")
        self.assertTrue(backup.verify_backup(snap)["ok"])
        # Retirada DEPOIS do snapshot, registrada no log protegido.
        kr.withdraw("juridico-lab/GUIA-002", 1, "retirada posterior ao snapshot")
        destino = self.root.parent / (self.root.name + "-restaurado")
        try:
            sem_log = backup.restore(snap, destino, None)
            self.assertFalse(sem_log["released"])
            shutil.rmtree(destino, ignore_errors=True)
            rep = backup.restore(snap, destino, kj.tombstone_log)
            self.assertTrue(rep["released"])
            self.assertEqual(rep["reapplied"], ["juridico-lab/GUIA-002@1"])
            con2 = connect(destino / "state" / "state.sqlite")
            try:
                ks = KnowledgeService(destino, con2, self.jur)
                self.assertEqual(ks.search("juridico-lab", "anexos nome versão origem"), [])
            finally:
                con2.close()
        finally:
            shutil.rmtree(snap, ignore_errors=True)
            shutil.rmtree(destino, ignore_errors=True)

    def test_prova_negativa_de_integridade_e_destino_novo(self):
        snap = self.root.parent / (self.root.name + "-snap2")
        try:
            backup.create_backup(self.root, snap, "baseline-a05-002")
            alvo = snap / "files" / "projects" / "juridico-lab" / "INSTRUCOES.md"
            alvo.write_text("alterado", encoding="utf-8")
            (snap / "files" / "projects" / "reversa-lab" / "INSTRUCOES.md").unlink()
            res = backup.verify_backup(snap)
            self.assertFalse(res["ok"])
            self.assertEqual(res["changed"], ["projects/juridico-lab/INSTRUCOES.md"])
            self.assertEqual(res["missing"], ["projects/reversa-lab/INSTRUCOES.md"])
            with self.assertRaises(FileExistsError):
                backup.restore(snap, self.root, None)  # nunca sobre a origem
            with self.assertRaises(FileExistsError):
                backup.create_backup(self.root, snap, "outra")  # não substitui referência anterior
        finally:
            shutil.rmtree(snap, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
