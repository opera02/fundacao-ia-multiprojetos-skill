"""A verificação de citação não recupera texto antes de autorizar o recurso."""
import json
import sqlite3

from helpers import FoundationTestCase
from fundacao.core.auth import resource_case, resource_project
from fundacao.core.contracts import NotFound
from fundacao.core.knowledge import KnowledgeService


class TestVerifyCitationAutorizacao(FoundationTestCase):
    TEXTO = "CANARIO-FICTICIO-CITACAO: revisão humana antes da entrega."
    FONTE = "juridico-lab/CITACAO-FIC"

    def publicar(self, case_id=None):
        self.write_data("juridico-lab", "fontes/citacao-fic.md", self.TEXTO)
        autor = KnowledgeService(self.root, self.con, self.jur)
        autor.register_source("juridico-lab", self.FONTE, 1, "fontes/citacao-fic.md", case_id=case_id)
        preparado = autor.prepare(self.FONTE, 1, [self.TEXTO])
        autor.index(self.FONTE, 1)
        rubrica = {k: {"resultado": "aprovado", "evidencia": "página fictícia conferida"}
                   for k in ("origem", "fidelidade", "vigencia", "acesso", "finalidade")}
        KnowledgeService(self.root, self.con, self.revisor).curate(
            self.FONTE, 1, rubrica, preparado, "2026-11-18", "laboratório fictício")
        return "juridico-lab/CITACAO-FIC@1:p1:c1:w80-o15-v1"

    def observar(self, principal, chunk_id):
        leituras = []

        def autorizar(action, tabela, coluna, banco, origem):
            if action == sqlite3.SQLITE_READ:
                leituras.append((tabela, coluna))
            return sqlite3.SQLITE_OK

        self.con.set_authorizer(autorizar)
        try:
            resposta = KnowledgeService(self.root, self.con, principal).verify_citation(chunk_id)
        finally:
            self.con.set_authorizer(None)
        return resposta, leituras

    def assert_negado_sem_conteudo(self, principal, chunk_id):
        resposta, leituras = self.observar(principal, chunk_id)
        self.assertEqual(resposta, {"chunk_id": chunk_id, "valid": False,
                                   "reason": "trecho inexistente ou sem acesso"})
        self.assertNotIn(("chunk", "body"), leituras, "texto do trecho recuperado antes da negativa")
        self.assertNotIn(("source_version", "prepared_json"), leituras,
                         "texto preparado recuperado antes da negativa")

    def test_trecho_de_outro_projeto_nao_recupera_body_e_registra_negativa(self):
        chunk_id = self.publicar()
        self.assert_negado_sem_conteudo(self.eng, chunk_id)
        evento = self.con.execute("SELECT payload_json FROM event WHERE kind = 'access_denied'"
                                  " ORDER BY seq DESC LIMIT 1").fetchone()
        self.assertEqual(json.loads(evento[0])["resource"], "project:juridico-lab")

    def test_citacao_valida_preserva_texto_e_referencia(self):
        chunk_id = self.publicar()
        resposta, leituras = self.observar(self.jur, chunk_id)
        self.assertEqual(resposta, {"chunk_id": chunk_id, "valid": True,
                                   "citation": "juridico-lab/CITACAO-FIC@1, p. 1", "body": self.TEXTO})
        self.assertIn(("chunk", "body"), leituras)

    def test_id_inexistente_tem_mesmo_contrato_da_negativa(self):
        self.assert_negado_sem_conteudo(self.jur, "juridico-lab/AUSENTE@1:p1:c1:w80-o15-v1")

    def test_revogacao_da_leitura_do_projeto_impede_recuperar_texto(self):
        chunk_id = self.publicar()
        self.assertTrue(KnowledgeService(self.root, self.con, self.jur).verify_citation(chunk_id)["valid"])
        self.policy.revoke(self.admin, self.jur.principal_id, resource_project("juridico-lab"), "read")
        self.assert_negado_sem_conteudo(self.jur, chunk_id)

    def test_caso_valido_preserva_citacao(self):
        chunk_id = self.publicar(case_id="caso-fic-001")
        resposta, _ = self.observar(self.jur, chunk_id)
        self.assertTrue(resposta["valid"])
        self.assertEqual(resposta["body"], self.TEXTO)

    def test_caso_vazio_preserva_recurso_do_projeto(self):
        chunk_id = self.publicar(case_id="")
        resposta, _ = self.observar(self.jur, chunk_id)
        self.assertTrue(resposta["valid"])
        self.assertEqual(resposta["body"], self.TEXTO)

    def test_concessao_do_caso_sem_leitura_do_projeto_nao_recupera_texto(self):
        chunk_id = self.publicar(case_id="caso-fic-001")
        self.policy.revoke(self.admin, self.jur.principal_id, resource_project("juridico-lab"), "read")
        self.assert_negado_sem_conteudo(self.jur, chunk_id)

    def test_revogacao_do_caso_nao_recupera_texto(self):
        chunk_id = self.publicar(case_id="caso-fic-001")
        self.policy.revoke(self.admin, self.jur.principal_id,
                           resource_case("juridico-lab", "caso-fic-001"), "read")
        self.assert_negado_sem_conteudo(self.jur, chunk_id)

    def test_retirada_sem_limpeza_dos_chunks_nao_entrega_texto(self):
        chunk_id = self.publicar()
        # Estado de retirada antes da limpeza assíncrona: o trecho ainda existe.
        with self.con:
            self.con.execute("UPDATE source_version SET status = 'withdrawn', is_current = 0"
                             " WHERE source_id = ? AND version = 1", (self.FONTE,))
        resposta, leituras = self.observar(self.jur, chunk_id)
        self.assertEqual(resposta, {"chunk_id": chunk_id, "valid": False, "reason": "fonte withdrawn"})
        self.assertNotIn(("chunk", "body"), leituras)

    def test_tombstone_sem_limpeza_bloqueia_trecho_ainda_presente(self):
        chunk_id = self.publicar()
        with self.con:
            self.con.execute("INSERT INTO tombstone VALUES (?,?,?,?,?,?)",
                             (chunk_id, "juridico-lab", self.revisor.principal_id,
                              "retirada fictícia antes da limpeza", "2026-10-24", "pending"))
        resposta, leituras = self.observar(self.jur, chunk_id)
        self.assertEqual(resposta, {"chunk_id": chunk_id, "valid": False, "reason": "retirada"})
        self.assertNotIn(("chunk", "body"), leituras)

    def test_vinculo_divergente_entre_projeto_do_chunk_e_fonte_nao_recupera_texto(self):
        chunk_id = self.publicar()
        # Corrupção fictícia: index() normalmente deriva esses campos da fonte.
        with self.con:
            self.con.execute("UPDATE chunk SET project_id = ?, resource = ? WHERE chunk_id = ?",
                             ("reversa-lab", "project:reversa-lab", chunk_id))
        self.assert_negado_sem_conteudo(self.eng, chunk_id)

    def test_vinculo_divergente_entre_caso_da_fonte_e_resource_nao_recupera_texto(self):
        chunk_id = self.publicar(case_id="caso-fic-001")
        with self.con:
            self.con.execute("UPDATE chunk SET resource = ? WHERE chunk_id = ?",
                             ("project:juridico-lab", chunk_id))
        self.policy.revoke(self.admin, self.jur.principal_id,
                           resource_case("juridico-lab", "caso-fic-001"), "read")
        self.assert_negado_sem_conteudo(self.jur, chunk_id)

    def assert_fonte_negada_sem_texto(self, principal):
        leituras = []

        def autorizar(action, tabela, coluna, banco, origem):
            if action == sqlite3.SQLITE_READ:
                leituras.append((tabela, coluna))
            return sqlite3.SQLITE_OK

        self.con.set_authorizer(autorizar)
        try:
            with self.assertRaisesRegex(NotFound, "fonte não encontrada"):
                KnowledgeService(self.root, self.con, principal)._source(self.FONTE, 1)
        finally:
            self.con.set_authorizer(None)
        self.assertNotIn(("source_version", "prepared_json"), leituras,
                         "fonte recuperou texto preparado antes da autorização")
        evento = self.con.execute("SELECT payload_json FROM event WHERE kind = 'access_denied'"
                                  " ORDER BY seq DESC LIMIT 1").fetchone()
        self.assertEqual(json.loads(evento[0])["action"], "read")

    def test_source_direto_de_outro_projeto_nao_recupera_texto_preparado(self):
        self.publicar()
        self.assert_fonte_negada_sem_texto(self.eng)

    def test_source_direto_revogado_nao_recupera_texto_preparado(self):
        self.publicar()
        self.policy.revoke(self.admin, self.jur.principal_id, resource_project("juridico-lab"), "read")
        self.assert_fonte_negada_sem_texto(self.jur)

    def test_source_direto_caso_revogado_nao_recupera_texto_preparado(self):
        self.publicar(case_id="caso-fic-001")
        self.policy.revoke(self.admin, self.jur.principal_id,
                           resource_case("juridico-lab", "caso-fic-001"), "read")
        self.assert_fonte_negada_sem_texto(self.jur)

    def test_source_direto_caso_exige_tambem_concessao_do_projeto(self):
        self.publicar(case_id="caso-fic-001")
        self.policy.revoke(self.admin, self.jur.principal_id, resource_project("juridico-lab"), "read")
        self.assert_fonte_negada_sem_texto(self.jur)

    def test_source_direto_autorizado_preserva_row_e_texto(self):
        self.publicar(case_id="caso-fic-001")
        fonte = KnowledgeService(self.root, self.con, self.jur)._source(self.FONTE, 1)
        self.assertEqual(fonte["project_id"], "juridico-lab")
        self.assertEqual(fonte["case_id"], "caso-fic-001")
        self.assertEqual(json.loads(fonte["prepared_json"])["pages"], [self.TEXTO])

    def test_source_mudando_de_escopo_entre_consultas_nao_entrega_fonte(self):
        self.publicar()
        servico = KnowledgeService(self.root, self.con, self.jur)
        allowed = servico.policy.allowed

        def autorizar_e_mudar(subject, action, resource):
            resultado = allowed(subject, action, resource)
            self.con.execute("UPDATE source_version SET case_id = 'caso-sem-concessao' WHERE source_id = ?",
                             (self.FONTE,))
            return resultado

        servico.policy.allowed = autorizar_e_mudar
        with self.assertRaisesRegex(NotFound, "fonte não encontrada"):
            servico._source(self.FONTE, 1)

    def test_source_mudando_de_projeto_entre_consultas_nao_entrega_fonte(self):
        self.publicar()
        servico = KnowledgeService(self.root, self.con, self.jur)
        allowed = servico.policy.allowed

        def autorizar_e_mudar(subject, action, resource):
            resultado = allowed(subject, action, resource)
            self.con.execute("UPDATE source_version SET project_id = 'reversa-lab' WHERE source_id = ?",
                             (self.FONTE,))
            return resultado

        servico.policy.allowed = autorizar_e_mudar
        with self.assertRaisesRegex(NotFound, "fonte não encontrada"):
            servico._source(self.FONTE, 1)
