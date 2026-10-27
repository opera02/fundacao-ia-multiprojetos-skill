"""P8: lições de projeto, ensaiadas somente em bancos fictícios descartáveis."""

from __future__ import annotations

import argparse
import json
import sqlite3
import unittest
from unittest import mock

from helpers import FoundationTestCase
from fundacao.core import db
from fundacao.core.canon import sha256_text
from fundacao.core.contracts import AccessDenied, RevisionConflict, ValidationError
from fundacao.core.memory import MemoryService


def corpo(**mudancas):
    dados = {"schema_version": "fundacao.memory.licao/1", "gatilho": "Revisão de migração",
             "licao": "Conferir as chaves estrangeiras antes de concluir.",
             "evidencia": "ensaio-ficticio:001", "confianca": "media"}
    dados.update(mudancas)
    return json.dumps(dados, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class TestLicoes179(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.mem = MemoryService(self.con, self.jur)
        self.rev = MemoryService(self.con, self.revisor)

    def propor(self, body=None, **campos):
        return self.mem.propose(op_id=campos.pop("op_id", "licao-1"), scope="project",
                                project_id="juridico-lab", kind="licao", origin="ia",
                                body=body or corpo(), source_ref="ensaio-ficticio:001", **campos)

    def aprovar(self, mid):
        _, digest = self.rev.pending_hash(mid)
        self.rev.approve(mid, digest)

    def consultar(self, gatilho="migracao"):
        return self.mem.query_licoes(project_id="juridico-lab", gatilho=gatilho)

    def test_tipo_licao_e_proposta_nao_vira_aprovacao_por_consulta(self):
        mid = self.propor()
        self.assertEqual(self.consultar(), [])
        self.assertEqual(self.con.execute("SELECT status FROM memory_item WHERE memory_id=?", (mid,)).fetchone()[0],
                         "proposed")
        with self.assertRaises(AccessDenied):
            self.mem.approve(mid, sha256_text(corpo()))
        self.aprovar(mid)
        itens = self.consultar()
        self.assertEqual([(i["memory_id"], i["revision"], i["kind"], i["confianca"]) for i in itens],
                         [(mid, 1, "licao", "media")])
        self.assertEqual(itens[0]["schema_version"], "fundacao.memory.licao/1")
        self.assertEqual(itens[0]["licao"], "Conferir as chaves estrangeiras antes de concluir.")

    def test_fts_so_no_gatilho_sem_interpretar_operadores_do_usuario(self):
        mid = self.propor(corpo(gatilho="Compactação de contexto", licao="Revisar a migração."))
        self.aprovar(mid)
        self.assertEqual(self.consultar("migracao"), [])
        self.assertEqual([i["memory_id"] for i in self.consultar("compactacao contexto")], [mid])
        self.assertEqual(self.consultar('compactacao OR ausente'), [])
        self.assertEqual(self.consultar('" OR *'), [])

    def test_consulta_reconfere_revogacao_antes_de_entregar_licao(self):
        mid = self.propor()
        self.aprovar(mid)
        self.assertEqual(len(self.consultar()), 1)
        self.policy.revoke(self.admin, self.jur.principal_id, "project:juridico-lab", "read")
        with self.assertRaises(AccessDenied):
            self.consultar()

    def test_json_duplicado_campos_ausentes_e_corpo_nao_objeto_recusados(self):
        for body in ('{"gatilho":"x","gatilho":"y"}', '[]', '{"schema_version":"fundacao.memory.licao/1"}',
                     '{', corpo(gatilho=12), corpo(licao=None)):
            with self.subTest(body=body), self.assertRaises(ValidationError):
                self.propor(body)

    def test_licao_de_caso_ou_comum_e_recusada_tambem_pelo_banco(self):
        mid = self.propor()
        for scope, case in (("case", "caso-fic-001"), ("common", None), ("project", "caso-fic-001")):
            with self.subTest(scope=scope, case=case), self.assertRaises(sqlite3.IntegrityError):
                self.con.execute("UPDATE memory_item SET scope=?,case_id=? WHERE memory_id=?", (scope, case, mid))

    def test_nega_outro_projeto_antes_de_ler_conteudo_ou_indice(self):
        mid = self.propor(corpo(licao="MARCADOR-FICTICIO-RESTRITO"))
        self.aprovar(mid)
        trace = []
        self.con.set_trace_callback(trace.append)
        try:
            with self.assertRaises(AccessDenied):
                MemoryService(self.con, self.eng).query_licoes(project_id="juridico-lab", gatilho="migracao")
        finally:
            self.con.set_trace_callback(None)
        consultas = [q.lower() for q in trace if q.lstrip().upper().startswith("SELECT")]
        self.assertFalse(any("memory_item" in q or "memory_revision" in q or "lesson_trigger" in q for q in consultas))

    def test_campos_invalidos_escopo_caso_e_comum_sao_recusados(self):
        for campo, valor in (("gatilho", " "), ("licao", ""), ("evidencia", []),
                             ("confianca", "certeza"), ("confianca", True), ("version", "1.7.9"),
                             ("schema_version", "fundacao.memory.licao/999")):
            with self.subTest(campo=campo, valor=valor), self.assertRaises(ValidationError):
                self.propor(corpo(**{campo: valor}), op_id=campo)
        for scope, case in (("case", "caso-fic-001"), ("common", None), ("project", "caso-fic-001")):
            with self.subTest(scope=scope, case=case), self.assertRaises(ValidationError):
                self.mem.propose(op_id="escopo", scope=scope, project_id="juridico-lab", case_id=case,
                                 kind="licao", origin="ia", body=corpo(), source_ref="ensaio-ficticio:001")
        with self.assertRaises(ValidationError):
            self.propor(corpo(evidencia="outra-evidencia"))

    def test_revisao_troca_gatilho_so_apos_aprovacao_e_obsoleta_nao_retorna(self):
        mid = self.propor()
        self.aprovar(mid)
        nova = corpo(gatilho="Retomada após interrupção", licao="Conferir o estado confirmado.")
        self.mem.revise(mid, expected_revision=1, body=nova, source_ref="ensaio-ficticio:001",
                        reason="o ensaio mostrou outro gatilho", change_kind="correcao")
        self.assertEqual([i["revision"] for i in self.consultar()], [1])
        self.assertEqual(self.consultar("retomada"), [])
        with self.assertRaises(RevisionConflict):
            self.mem.revise(mid, expected_revision=1, body=nova, source_ref="ensaio-ficticio:001",
                            reason="revisão velha", change_kind="correcao")
        self.aprovar(mid)
        self.assertEqual(self.consultar(), [])
        self.assertEqual([i["revision"] for i in self.consultar("retomada")], [2])
        self.rev.withdraw(mid, "lição refutada no ensaio fictício")
        self.assertEqual(self.consultar("retomada"), [])
        with self.assertRaises(ValidationError):
            self.rev.approve(mid, sha256_text(nova))

    def test_revisao_invalida_ou_falha_do_evento_nao_grava_metade(self):
        mid = self.propor()
        self.aprovar(mid)
        with self.assertRaises(ValidationError):
            self.mem.revise(mid, expected_revision=1, body="texto solto", source_ref="ensaio-ficticio:001",
                            reason="teste", change_kind="correcao")
        with mock.patch("fundacao.core.memory.events.emit", side_effect=RuntimeError("queda simulada")):
            with self.assertRaises(RuntimeError):
                self.mem.revise(mid, expected_revision=1, body=corpo(gatilho="Outro gatilho"),
                                source_ref="ensaio-ficticio:001", reason="teste", change_kind="correcao")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM memory_revision WHERE memory_id=?", (mid,)).fetchone()[0], 1)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM lesson_trigger WHERE memory_id=?", (mid,)).fetchone()[0], 1)

    def test_vigencia_futura_nao_retorna_e_formato_invalido_recusa(self):
        mid = self.propor(effective_from="2999-01-01T00:00:00Z")
        self.aprovar(mid)
        self.assertEqual(self.consultar(), [])
        with self.assertRaises(ValidationError):
            self.propor(op_id="data-ruim", effective_from="amanhã")

    def test_reabre_indice_e_idempotencia_sem_duplicar(self):
        mid = self.propor()
        self.aprovar(mid)
        self.assertEqual(self.propor(), mid)
        self.con.close()
        self.con = db.connect(self.root / "state" / "state.sqlite")
        self.mem = MemoryService(self.con, self.jur)
        self.assertEqual([i["memory_id"] for i in self.consultar()], [mid])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM lesson_trigger").fetchone()[0], 1)

    def test_promocao_curada_publica_procedimento_sem_criar_licao_comum(self):
        mid = self.propor()
        self.aprovar(mid)
        pid, digest = self.mem.request_promotion(mid, "Conferir chaves antes de concluir.", "procedimento genérico")
        pub = MemoryService(self.con, self.curador).decide_promotion(pid, True, digest)
        row = self.con.execute("SELECT scope, kind FROM memory_item WHERE memory_id=?", (pub,)).fetchone()
        self.assertEqual(tuple(row), ("common", "procedimento"))
        self.assertEqual([i["memory_id"] for i in self.consultar()], [mid])

    def test_cli_propoe_consulta_revisa_e_retira_sem_fornecer_identidade(self):
        from fundacao.cli_memoria import executar, registrar_parser
        parser = argparse.ArgumentParser()
        registrar_parser(parser.add_subparsers(dest="cmd", required=True))
        args = parser.parse_args(["memoria", "licao", "propor", "--projeto", "juridico-lab", "--op-id", "cli-1",
                                 "--gatilho", "Revisão de migração", "--licao", "Conferir chaves.",
                                 "--evidencia", "ensaio-ficticio:001", "--confianca", "media"])
        mid = executar(args, self.con, self.jur)["memory_id"]
        busca = parser.parse_args(["memoria", "licao", "consultar", "--projeto", "juridico-lab", "--gatilho", "migracao"])
        self.assertEqual(executar(busca, self.con, self.jur), [])
        aprovar = parser.parse_args(["memoria", "licao", "aprovar", "--memoria", mid,
                                    "--hash", self.rev.pending_hash(mid)[1]])
        executar(aprovar, self.con, self.revisor)
        self.assertEqual([i["memory_id"] for i in executar(busca, self.con, self.jur)], [mid])
        revisar = parser.parse_args(["memoria", "licao", "revisar", "--memoria", mid, "--revisao", "1",
                                     "--motivo", "outro ensaio fictício", "--gatilho", "Retomada",
                                     "--licao", "Conferir o estado.", "--evidencia", "ensaio-ficticio:002",
                                     "--confianca", "baixa"])
        self.assertEqual(executar(revisar, self.con, self.jur), {"revision": 2})
        pendente = parser.parse_args(["memoria", "licao", "pendente", "--memoria", mid])
        digest = executar(pendente, self.con, self.revisor)["hash"]
        aprovar.hash = digest
        executar(aprovar, self.con, self.revisor)
        self.assertEqual(executar(busca, self.con, self.jur), [])
        retirar = parser.parse_args(["memoria", "licao", "retirar", "--memoria", mid, "--motivo", "refutada"])
        self.assertIn(mid, executar(retirar, self.con, self.revisor)["affected"])

    def test_cli_ids_alheios_e_inexistentes_tem_mesma_resposta(self):
        from fundacao.cli_memoria import executar
        from fundacao.core import events
        mid = self.propor()
        antes = events.count(self.con, "access_denied", subject=self.eng.principal_id)
        for acao in ("pendente", "aprovar", "historico", "retirar", "revisar"):
            respostas = []
            for ident in (mid, "mem-inexistente-ficticia"):
                args = argparse.Namespace(memoria_acao=acao, memoria=ident, hash="hash-ficticio",
                    motivo="ensaio", revisao=1, mudanca="correcao", gatilho="Retomada",
                    licao="Conferir estado.", evidencia="ensaio-ficticio:001", confianca="media")
                try:
                    executar(args, self.con, self.eng)
                except (AccessDenied, ValidationError) as erro:
                    respostas.append(erro.as_dict())
                else:
                    self.fail("identidade sem leitura recebeu uma resposta")
            with self.subTest(acao=acao):
                self.assertEqual(respostas[0], respostas[1])
                self.assertNotIn("juridico-lab", json.dumps(respostas))
        self.assertEqual(events.count(self.con, "access_denied", subject=self.eng.principal_id), antes + 5)
        self.assertEqual(events.verify_chain(self.con), (True, None))
        self.assertEqual(self.con.execute("SELECT revision FROM memory_item WHERE memory_id=?", (mid,)).fetchone()[0], 1)


class TestMigracaoLicoes179(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:", isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        with mock.patch.object(db, "MIGRATIONS", db.MIGRATIONS[:4]):
            db.migrate(self.con)
        self.con.execute("INSERT INTO project VALUES ('projeto-ficticio','Fictício','Ensaio','1','project/1','active','ensaio','2026')")
        self.con.execute("INSERT INTO memory_item VALUES ('mem-fic','project','projeto-ficticio',NULL,'procedimento','humano',"
                         "'approved',1,'Texto legado','hash','evidencia','autor','revisor','hash',NULL,'2026')")
        self.con.execute("INSERT INTO memory_revision VALUES ('mem-fic',1,'Texto legado','hash','evidencia','criação',"
                         "'criacao','autor','2026','approved','revisor','2026')")
        self.con.execute("INSERT INTO promotion VALUES ('promo-fic','mem-fic','Candidato','hash','teste','autor','2026',"
                         "'pending',NULL,NULL,NULL,1,'hash')")
        self.con.execute("CREATE INDEX indice_mem_ficticio ON memory_item(project_id, kind)")
        self.con.execute("CREATE TRIGGER gatilho_mem_ficticio AFTER UPDATE OF body ON memory_item "
                         "BEGIN INSERT INTO meta VALUES ('gatilho-ficticio',NEW.body); END")

    def tearDown(self):
        self.con.close()

    def test_migra_v4_preservando_dados_indices_gatilhos_fk_e_idempotencia(self):
        antes = {t: [tuple(r) for r in self.con.execute(f"SELECT * FROM {t}")]
                 for t in ("memory_item", "memory_revision", "promotion")}
        self.assertGreater(db.migrate(self.con), 4)
        for t, linhas in antes.items():
            self.assertEqual([tuple(r) for r in self.con.execute(f"SELECT * FROM {t}")], linhas)
        self.assertEqual(self.con.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(self.con.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertTrue(self.con.execute("SELECT 1 FROM sqlite_master WHERE name='indice_mem_ficticio'").fetchone())
        self.con.execute("UPDATE memory_item SET body='Atualizado' WHERE memory_id='mem-fic'")
        self.assertEqual(self.con.execute("SELECT value FROM meta WHERE key='gatilho-ficticio'").fetchone()[0], "Atualizado")
        versao = db.migrate(self.con)
        self.assertEqual(db.migrate(self.con), versao)
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute("DELETE FROM memory_item WHERE memory_id='mem-fic'")

    def test_falha_na_migracao_reverte_esquema_dados_indice_e_user_version(self):
        antes = [tuple(r) for r in self.con.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY name")]
        def negar_fts(acao, nome, *_):
            return sqlite3.SQLITE_DENY if acao == sqlite3.SQLITE_CREATE_VTABLE else sqlite3.SQLITE_OK
        self.con.set_authorizer(negar_fts)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                db.migrate(self.con)
        finally:
            self.con.set_authorizer(None)
        self.assertEqual(self.con.execute("PRAGMA user_version").fetchone()[0], 4)
        self.assertEqual(self.con.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual([tuple(r) for r in self.con.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY name")], antes)
        self.assertEqual(self.con.execute("SELECT body FROM memory_item").fetchone()[0], "Texto legado")
        self.assertFalse(self.con.in_transaction)

    def test_migracao_preserva_view_e_trigger_de_outra_tabela(self):
        self.con.execute("CREATE VIEW memoria_ficticia AS SELECT memory_id,body FROM memory_item")
        self.con.execute("CREATE TRIGGER outra_tabela_ficticia AFTER INSERT ON meta BEGIN "
                         "UPDATE memory_item SET source_ref=NEW.value WHERE memory_id='mem-fic'; END")
        db.migrate(self.con)
        self.assertEqual(self.con.execute("SELECT body FROM memoria_ficticia").fetchone()[0], "Texto legado")
        self.assertEqual(self.con.execute("SELECT source_ref FROM memory_item").fetchone()[0], "evidencia")
        self.con.execute("INSERT INTO meta VALUES ('outra-evidencia','referencia-nova')")
        self.assertEqual(self.con.execute("SELECT source_ref FROM memory_item").fetchone()[0], "referencia-nova")

    def test_banco_futuro_e_transacao_aberta_sao_recusados_sem_alterar(self):
        self.con.execute("PRAGMA user_version=999")
        with self.assertRaises(RuntimeError):
            db.migrate(self.con)
        self.assertEqual(self.con.execute("PRAGMA user_version").fetchone()[0], 999)
        self.con.execute("PRAGMA user_version=4")
        self.con.execute("BEGIN")
        with self.assertRaises(RuntimeError):
            db.migrate(self.con)
        self.assertTrue(self.con.in_transaction)
        self.con.execute("ROLLBACK")

    def test_fk_legada_invalida_impede_migracao_e_reverte_tudo(self):
        self.con.execute("PRAGMA foreign_keys=OFF")
        self.con.execute("UPDATE memory_item SET project_id='projeto-inexistente'")
        self.con.execute("PRAGMA foreign_keys=ON")
        with self.assertRaisesRegex(RuntimeError, "estrangeira"):
            db.migrate(self.con)
        self.assertEqual(self.con.execute("PRAGMA user_version").fetchone()[0], 4)
        self.assertEqual(self.con.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(self.con.execute("SELECT project_id FROM memory_item").fetchone()[0], "projeto-inexistente")
        self.assertFalse(self.con.execute("SELECT 1 FROM sqlite_master WHERE name='lesson_trigger'").fetchone())


if __name__ == "__main__":
    unittest.main()
