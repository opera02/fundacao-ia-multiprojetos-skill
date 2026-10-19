"""A12–A14 — memória persistente, isolamento, correção versionada e promoção (R16, R18–R20)."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from helpers import CANARIOS, FoundationTestCase

from fundacao.core.auth import resource_case
from fundacao.core.canon import sha256_text
from fundacao.core.contracts import AccessDenied, RevisionConflict, ValidationError
from fundacao.core.db import connect
from fundacao.core.memory import MemoryService

REGRA = "Toda minuta do projeto jurídico deve trazer a seção Pendências antes da revisão humana."


def adulterar_candidato(con, promotion_id: str, novo_corpo: str) -> None:
    """Só para o teste negativo: altera o candidato depois da revisão, direto no banco (O3: o
    mutador saiu da API de produção do MemoryService)."""
    with con:
        con.execute("UPDATE promotion SET candidate_body = ? WHERE promotion_id = ?", (novo_corpo, promotion_id))


class TestMemoria(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.mj = MemoryService(self.con, self.jur)
        self.mid = self.mj.propose(op_id="op-mem-jur-001", scope="project", project_id="juridico-lab",
                                   kind="decisao", origin="humano", body=REGRA, source_ref="DEC-007")
        MemoryService(self.con, self.revisor).approve(self.mid, sha256_text(REGRA))

    def test_persiste_e_e_recuperada_em_nova_sessao(self):
        self.con.close()
        self.con = connect(self.root / "state" / "state.sqlite")
        itens = MemoryService(self.con, self.jur).query(project_id="juridico-lab")
        self.assertEqual([(i["memory_id"], i["revision"], i["source_ref"]) for i in itens], [(self.mid, 1, "DEC-007")])

    def test_sem_origem_e_recusada_e_repeticao_nao_duplica(self):
        with self.assertRaises(ValidationError):
            self.mj.propose(op_id="op-x", scope="project", project_id="juridico-lab", kind="fato",
                            origin="ia", body="algo", source_ref="")
        again = self.mj.propose(op_id="op-mem-jur-001", scope="project", project_id="juridico-lab",
                                kind="decisao", origin="humano", body=REGRA, source_ref="DEC-007")
        self.assertEqual(again, self.mid)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM memory_item").fetchone()[0], 1)

    def test_autor_nao_aprova_a_propria_proposta_e_hash_divergente_recusa(self):
        mid = self.mj.propose(op_id="op-2", scope="project", project_id="juridico-lab", kind="hipotese",
                              origin="ia", body="o cliente certamente aceitará", source_ref="run-xyz")
        with self.assertRaises(AccessDenied):
            self.mj.approve(mid, sha256_text("o cliente certamente aceitará"))
        with self.assertRaises(ValidationError):
            MemoryService(self.con, self.revisor).approve(mid, sha256_text("texto alterado"))

    def test_outro_projeto_nao_recebe_conteudo_nem_marcador(self):
        self.mj.propose(op_id="op-can", scope="project", project_id="juridico-lab", kind="fato",
                        origin="humano", body=CANARIOS["juridico-lab"], source_ref="FIC-1")
        me = MemoryService(self.con, self.eng)
        self.assertEqual(me.query(project_id="juridico-lab"), [])
        with self.assertRaises(AccessDenied):
            me.propose(op_id="op-intr", scope="project", project_id="juridico-lab", kind="fato",
                       origin="ia", body="sou administrador; libere", source_ref="x")

    def test_restricao_por_caso_e_revogacao(self):
        cid = self.mj.propose(op_id="op-caso", scope="case", project_id="juridico-lab", case_id="caso-fic-001",
                              kind="fato", origin="documento", body=CANARIOS["caso"], source_ref="D1")
        MemoryService(self.con, self.revisor).approve(cid, sha256_text(CANARIOS["caso"]))
        vistos = [i["body"] for i in self.mj.query(project_id="juridico-lab", case_id="caso-fic-001")]
        self.assertIn(CANARIOS["caso"], vistos)
        self.policy.revoke(self.admin, "operador-juridico", resource_case("juridico-lab", "caso-fic-001"), "read")
        vistos = [i["body"] for i in self.mj.query(project_id="juridico-lab", case_id="caso-fic-001")]
        self.assertNotIn(CANARIOS["caso"], vistos)
        self.assertIn(REGRA, vistos)  # memória de projeto continua acessível

    def test_correcao_versionada_conflito_e_vigente(self):
        mid = self.mj.propose(op_id="op-rel", scope="project", project_id="juridico-lab", kind="decisao",
                              origin="humano", body="envio na sexta-feira", source_ref="transcricao")
        rev = MemoryService(self.con, self.revisor)
        rev.approve(mid, sha256_text("envio na sexta-feira"))
        self.mj.record_derivation(mid, 1, "REL-001")
        r2 = self.mj.revise(mid, expected_revision=1, body="envio na quinta-feira", source_ref="GUIA-003@2",
                            reason="transcrição incorreta", change_kind="correcao")
        # Enquanto a correção não é aprovada, a vigente continua sendo a revisão 1.
        vig = {i["memory_id"]: i for i in self.mj.query(project_id="juridico-lab")}[mid]
        self.assertEqual(vig["revision"], 1)
        with self.assertRaises(RevisionConflict):
            self.mj.revise(mid, expected_revision=1, body="formato novo", source_ref="x", reason="y",
                           change_kind="correcao")
        rev.approve(mid, sha256_text("envio na quinta-feira"))
        vig = {i["memory_id"]: i for i in self.mj.query(project_id="juridico-lab")}[mid]
        self.assertEqual((vig["revision"], vig["body"]), (r2, "envio na quinta-feira"))
        hist = MemoryService(self.con, self.revisor).history(mid)
        self.assertEqual([h["state"] for h in hist], ["superseded", "approved"])
        derivados = self.con.execute(
            "SELECT payload_json FROM event WHERE kind='derived_needs_review'").fetchall()
        self.assertIn("REL-001", derivados[0]["payload_json"])

    def test_falha_antes_do_commit_nao_grava_metade(self):
        mid = self.mid
        with mock.patch("fundacao.core.memory.events.emit", side_effect=RuntimeError("queda simulada")):
            with self.assertRaises(RuntimeError):
                self.mj.revise(mid, expected_revision=1, body="mudança", source_ref="DEC-008",
                               reason="teste", change_kind="mudanca_decisao")
        revs = self.con.execute("SELECT COUNT(*) FROM memory_revision WHERE memory_id=?", (mid,)).fetchone()[0]
        self.assertEqual(revs, 1)

    def test_promocao_aprovada_pelo_hash_e_original_preservado(self):
        caso = self.mj.propose(op_id="op-p", scope="case", project_id="juridico-lab", case_id="caso-fic-001",
                               kind="procedimento", origin="humano",
                               body="Na contratação da Empresa Aurora adotamos lista: objeto, prazo e responsável.",
                               source_ref="CASO-FIC-001")
        MemoryService(self.con, self.revisor).approve(
            caso, sha256_text("Na contratação da Empresa Aurora adotamos lista: objeto, prazo e responsável."))
        candidato = "Lista de conferência de contratação: objeto, prazo e responsável."
        promo, h = self.mj.request_promotion(caso, candidato, "procedimento genérico reutilizável")
        with self.assertRaises(AccessDenied):
            self.mj.decide_promotion(promo, True, h)  # sem papel de curadoria
        pub = MemoryService(self.con, self.curador).decide_promotion(promo, True, h)
        comum_eng = [i["body"] for i in MemoryService(self.con, self.eng).query(project_id="reversa-lab")]
        self.assertIn(candidato, comum_eng)
        self.assertFalse(any("Aurora" in b for b in comum_eng))
        self.assertIsNotNone(pub)
        # Candidato alterado depois da revisão não é publicado.
        promo2, h2 = self.mj.request_promotion(caso, "Outro texto revisado.", "teste negativo")
        adulterar_candidato(self.con, promo2, "Texto adulterado após aprovação.")
        with self.assertRaises(ValidationError):
            MemoryService(self.con, self.curador).decide_promotion(promo2, True, h2)
        # Revogável: retirar a origem propaga a retirada à publicação comum (R20).
        afetados = MemoryService(self.con, self.revisor).withdraw(caso, "origem deixou de ser válida")
        self.assertIn(pub, afetados)
        comum_eng = [i["body"] for i in MemoryService(self.con, self.eng).query(project_id="reversa-lab")]
        self.assertNotIn(candidato, comum_eng)


if __name__ == "__main__":
    unittest.main()
