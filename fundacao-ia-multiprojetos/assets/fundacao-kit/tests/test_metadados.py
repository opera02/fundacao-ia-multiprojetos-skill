"""Metadados entre projetos: existência, nomes e contagens não vazam (achados F01–F03, O2–O3).

Respostas para "alheio" e "inexistente" são iguais; a sondagem fica registrada como negativa.
"""

from __future__ import annotations

import sqlite3
import unittest

from helpers import CANARIOS, FoundationTestCase

from fundacao.core.cache import ResponseCache
from fundacao.core.contracts import AccessDenied, NotFound, ValidationError
from fundacao.core.db import MIGRATIONS, migrate
from fundacao.core.knowledge import KnowledgeService
from fundacao.core.memory import MemoryService
from fundacao.core.tasks import Coordinator


class TestMetadados(FoundationTestCase):
    def negativas(self, quem: str) -> int:
        return self.con.execute("SELECT COUNT(*) FROM event WHERE kind='access_denied' AND subject=?",
                                (quem,)).fetchone()[0]

    def test_fonte_qualificada_e_sondagem_indistinguivel(self):
        self.write_data("juridico-lab", "fontes/g1.md", "texto " + CANARIOS["juridico-lab"])
        self.write_data("reversa-lab", "fontes/x.md", "outro texto")
        kj = KnowledgeService(self.root, self.con, self.jur)
        ke = KnowledgeService(self.root, self.con, self.eng)
        with self.assertRaises(ValidationError):
            kj.register_source("juridico-lab", "GUIA-001", 1, "fontes/g1.md")  # sem qualificação
        kj.register_source("juridico-lab", "juridico-lab/GUIA-001", 1, "fontes/g1.md")
        with self.assertRaises(ValidationError):  # não usa o prefixo de outro projeto
            ke.register_source("reversa-lab", "juridico-lab/GUIA-001", 1, "fontes/x.md")
        antes = self.negativas("operador-engenharia")
        mensagens = []
        for sid in ("juridico-lab/GUIA-001", "juridico-lab/NAO-EXISTE"):
            with self.assertRaises(NotFound) as ctx:
                ke.prepare(sid, 1, ["x"])
            mensagens.append(str(ctx.exception))
        self.assertEqual(mensagens[0], mensagens[1])
        self.assertEqual(self.negativas("operador-engenharia"), antes + 1)

    def test_citacao_alheia_igual_a_inexistente(self):
        self.write_data("juridico-lab", "fontes/g2.md", "Lista de anexos com nome, versão e origem.")
        kj = KnowledgeService(self.root, self.con, self.jur)
        kj.register_source("juridico-lab", "juridico-lab/GUIA-002", 1, "fontes/g2.md")
        kj.prepare("juridico-lab/GUIA-002", 1, ["Lista de anexos com nome, versão e origem."])
        kj.index("juridico-lab/GUIA-002", 1)
        chunk_id = self.con.execute("SELECT chunk_id FROM chunk").fetchone()[0]
        ke = KnowledgeService(self.root, self.con, self.eng)
        alheia = ke.verify_citation(chunk_id)
        inexistente = ke.verify_citation("juridico-lab/NADA@1#p1-0")
        self.assertEqual({k: v for k, v in alheia.items() if k != "chunk_id"},
                         {k: v for k, v in inexistente.items() if k != "chunk_id"})
        self.assertNotIn("body", alheia)

    def test_chave_de_idempotencia_vale_por_projeto(self):
        cj = Coordinator(self.root, self.con, self.jur, "juridico-lab")
        ce = Coordinator(self.root, self.con, self.eng, "reversa-lab")
        t1 = cj.create_task("tarefa jurídica (fictícia)", idempotency_key="lote-1")
        t2 = ce.create_task("tarefa de engenharia (fictícia)", idempotency_key="lote-1")
        self.assertNotEqual(t1, t2)
        self.assertEqual(cj.create_task("repetida", idempotency_key="lote-1"), t1)
        self.assertEqual(cj.get_task(t1)["idempotency_key"], "lote-1")

    def test_operacao_de_memoria_vale_por_escopo(self):
        mj, me = MemoryService(self.con, self.jur), MemoryService(self.con, self.eng)
        a = mj.propose(op_id="op-1", scope="project", project_id="juridico-lab", kind="fato", origin="humano",
                       body="fato A (fictício)", source_ref="FIC-A")
        b = me.propose(op_id="op-1", scope="project", project_id="reversa-lab", kind="fato", origin="humano",
                       body="fato B (fictício)", source_ref="FIC-B")
        self.assertNotEqual(a, b)
        self.assertEqual(mj.propose(op_id="op-1", scope="project", project_id="juridico-lab", kind="fato",
                                    origin="humano", body="fato A (fictício)", source_ref="FIC-A"), a)

    def test_revisao_pendente_alheia_igual_a_inexistente(self):
        mid = MemoryService(self.con, self.jur).propose(
            op_id="op-p", scope="project", project_id="juridico-lab", kind="fato", origin="humano",
            body="pendente (fictício)", source_ref="FIC")
        me = MemoryService(self.con, self.eng)
        mensagens = []
        for alvo in (mid, "mem_inexistente"):
            with self.assertRaises(ValidationError) as ctx:
                me.pending_hash(alvo)
            mensagens.append(str(ctx.exception))
        self.assertEqual(mensagens[0], mensagens[1])

    def test_cache_put_exige_leitura_do_projeto(self):
        c = ResponseCache(self.con, self.eng)
        meta = c.server_meta("reversa-lab", provider_id="s", model_revision="m", prompt_revision="p",
                             context_hash="c", generation_config={})
        with self.assertRaises(AccessDenied):
            c.put("juridico-lab", "pergunta", meta, {"r": 1}, ["x"])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM cache_entry").fetchone()[0], 0)

    def test_migracao_2_qualifica_chaves_antigas(self):
        # Banco realmente no esquema 1. Reduzir só user_version do banco atual
        # deixa o CHECK e o FTS da migração 5 presentes e não simula uma versão antiga.
        with sqlite3.connect(":memory:", isolation_level=None) as antiga:
            antiga.row_factory = sqlite3.Row
            antiga.executescript(MIGRATIONS[0])
            antiga.execute("PRAGMA foreign_keys = ON")
            antiga.execute("PRAGMA user_version = 1")
            for tabela in ("principal", "acl", "project", "revision_counter"):
                linhas = self.con.execute(f"SELECT * FROM {tabela}").fetchall()
                if linhas:
                    valores = ",".join("?" for _ in linhas[0])
                    antiga.executemany(f"INSERT INTO {tabela} VALUES ({valores})", linhas)
            Coordinator(self.root, antiga, self.jur, "juridico-lab").create_task(
                "antiga (fictícia)", idempotency_key="k-antiga")
            antiga.execute("UPDATE task SET idempotency_key = 'k-antiga'")
            self.assertNotIn("'licao'", antiga.execute(
                "SELECT sql FROM sqlite_master WHERE name='memory_item'").fetchone()[0])
            self.assertEqual(migrate(antiga), len(MIGRATIONS))
            self.assertEqual(antiga.execute("SELECT idempotency_key FROM task").fetchone()[0],
                             "juridico-lab::k-antiga")
            self.assertEqual(migrate(antiga), len(MIGRATIONS))  # repetir não reaplica migração


if __name__ == "__main__":
    unittest.main()
