"""Auditoria externa da 1.3.4 — frente 2, aprovação e retirada (F05–F09) e O3.

Cada teste exige o comportamento SEGURO; na 1.3.4 eles falham por asserção. Dados fictícios;
nos testes de corrida, uma barreira posiciona operações reais (duas conexões SQLite) numa ordem
determinada, sem alterar a regra decisória do código.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import unittest
from unittest import mock

from helpers import FoundationTestCase

from fundacao.core import backup
from fundacao.core.cache import ResponseCache
from fundacao.core.canon import sha256_text
from fundacao.core.contracts import FundacaoError
from fundacao.core.db import connect
from fundacao.core.knowledge import KnowledgeService
from fundacao.core.memory import MemoryService

APROVADO = {c: {"resultado": "aprovado", "evidencia": f"conferido contra a página ({c})"}
            for c in ("origem", "fidelidade", "vigencia", "acesso", "finalidade")}
REGRA = "REGRA-FICTICIA-A: toda minuta fictícia traz a seção Pendências."


class _Base(FoundationTestCase):
    def memoria_aprovada(self, corpo: str = REGRA, op: str = "op-fic-1") -> str:
        mid = MemoryService(self.con, self.jur).propose(op_id=op, scope="project", project_id="juridico-lab",
                                                        kind="procedimento", origin="humano", body=corpo,
                                                        source_ref="FONTE-FICTICIA")
        MemoryService(self.con, self.revisor).approve(mid, sha256_text(corpo))
        return mid

    def cache(self, quem=None):
        c = ResponseCache(self.con, quem or self.jur)
        m = c.server_meta("juridico-lab", provider_id="simulado-a", model_revision="sim-1", prompt_revision="p1",
                          context_hash="ctx-ficticio", generation_config={"t": "0"})
        return c, m

    def gold(self, texto: str = "TEXTO-FICTICIO-A aprovado e revisado", aprovar: bool = True):
        sid = "juridico-lab/GUIA-FIC"
        self.write_data("juridico-lab", "fontes/guia-fic.md", texto)
        kj = KnowledgeService(self.root, self.con, self.jur)
        kj.register_source("juridico-lab", sid, 1, "fontes/guia-fic.md")
        h = kj.prepare(sid, 1, [texto])
        kj.index(sid, 1)
        if aprovar:
            KnowledgeService(self.root, self.con, self.revisor).curate(sid, 1, APROVADO, h, "2099-01-01", "ensaio")
        return kj, sid, h


class TestF05CachePorChave(_Base):
    def test_f05_leitura_por_id_respeita_o_prazo(self):
        c, m = self.cache()
        with mock.patch("fundacao.core.cache.time.time", return_value=1000.0):
            key = c.put("juridico-lab", "consulta fictícia", m, "RESPOSTA-FICTICIA", [], ttl_seconds=1)
        with mock.patch("fundacao.core.cache.time.time", return_value=1002.0):
            por_id = c.get_by_key("juridico-lab", key)
            normal = c.get("juridico-lab", "consulta fictícia", m)
        self.assertNotEqual(por_id[0], "hit", "get_by_key entregou entrada expirada")
        self.assertNotEqual(normal[0], "hit")

    def test_f05_leitura_por_id_respeita_memoria_retirada(self):
        mid = self.memoria_aprovada()
        c, m = self.cache()
        key = c.put("juridico-lab", "consulta fictícia", m, REGRA, [mid])
        MemoryService(self.con, self.revisor).withdraw(mid, "retirada fictícia")
        self.assertNotEqual(c.get_by_key("juridico-lab", key)[0], "hit",
                            "get_by_key entregou conteúdo baseado em memória retirada")
        self.assertNotEqual(c.get("juridico-lab", "consulta fictícia", m)[0], "hit")

    def test_f05_entrada_valida_continua_servida_pelas_duas_portas(self):
        mid = self.memoria_aprovada()
        c, m = self.cache()
        key = c.put("juridico-lab", "consulta fictícia", m, {"r": "ok"}, [mid])
        self.assertEqual(c.get_by_key("juridico-lab", key), ("hit", {"r": "ok"}))
        self.assertEqual(c.get("juridico-lab", "consulta fictícia", m), ("hit", {"r": "ok"}))


class TestF06PromocaoDeOrigemRetirada(_Base):
    def _comuns(self) -> list[str]:
        return [r[0] for r in self.con.execute("SELECT body FROM memory_item WHERE scope = 'common'")]

    def test_f06_pendente_de_origem_retirada_nao_publica(self):
        mid = self.memoria_aprovada()
        promo, h = MemoryService(self.con, self.jur).request_promotion(
            mid, "PROCEDIMENTO-FICTICIO genérico", "candidato fictício")
        MemoryService(self.con, self.revisor).withdraw(mid, "origem inválida")
        decisao = self.con.execute("SELECT decision FROM promotion WHERE promotion_id = ?", (promo,)).fetchone()[0]
        self.assertNotEqual(decisao, "pending", "a retirada da origem não cancelou o candidato pendente")
        with self.assertRaises(FundacaoError):
            MemoryService(self.con, self.curador).decide_promotion(promo, True, h)
        self.assertEqual(self._comuns(), [], "a promoção pendente publicou origem retirada")
        vistos = [i["body"] for i in MemoryService(self.con, self.eng).query(project_id="reversa-lab")]
        self.assertNotIn("PROCEDIMENTO-FICTICIO genérico", vistos)

    def test_f06_origem_alterada_depois_do_pedido_exige_novo_candidato(self):
        mid = self.memoria_aprovada()
        promo, h = MemoryService(self.con, self.jur).request_promotion(
            mid, "PROCEDIMENTO-FICTICIO derivado da revisão 1", "candidato fictício")
        r2 = MemoryService(self.con, self.jur).revise(mid, expected_revision=1, body="REGRA-FICTICIA-B corrigida",
                                                     source_ref="FONTE-2", reason="correção", change_kind="correcao")
        MemoryService(self.con, self.revisor).approve(mid, sha256_text("REGRA-FICTICIA-B corrigida"))
        self.assertEqual(r2, 2)
        with self.assertRaises(FundacaoError):
            MemoryService(self.con, self.curador).decide_promotion(promo, True, h)
        self.assertEqual(self._comuns(), [])

    def test_f06_origem_valida_continua_publicavel(self):
        mid = self.memoria_aprovada()
        promo, h = MemoryService(self.con, self.jur).request_promotion(mid, "PROCEDIMENTO-FICTICIO ok", "candidato")
        pub = MemoryService(self.con, self.curador).decide_promotion(promo, True, h)
        self.assertIsNotNone(pub)
        self.assertEqual(self._comuns(), ["PROCEDIMENTO-FICTICIO ok"])


class TestF07RetiradaAlcancaDerivadosPorRevisao(_Base):
    def test_f07_derivado_registrado_por_revisao_e_retirado(self):
        mid = self.memoria_aprovada()
        derivado = "RELATORIO-FICTICIO-001"
        MemoryService(self.con, self.jur).record_derivation(mid, 1, derivado)
        c, m = self.cache()
        c.put("juridico-lab", "resumo do relatório?", m, "derivado fictício", [derivado])
        afetados = MemoryService(self.con, self.revisor).withdraw(mid, "retirada da regra")
        self.assertIn(derivado, afetados, "a retirada percorreu só o identificador sem revisão")
        self.assertIsNotNone(self.con.execute("SELECT 1 FROM tombstone WHERE entity_id = ?", (derivado,)).fetchone())
        self.assertNotEqual(c.get("juridico-lab", "resumo do relatório?", m)[0], "hit")
        linhas = [r for r in backup.read_tombstone_log(self.root / "state" / "retiradas.jsonl")
                  if r.get("entity_id") == mid]
        self.assertTrue(linhas and derivado in linhas[-1]["affected"], "o registro protegido não recebeu o derivado")

    def test_f07_derivado_indireto_tambem_e_alcancado(self):
        mid = self.memoria_aprovada()
        MemoryService(self.con, self.jur).record_derivation(mid, 1, "RELATORIO-FICTICIO-002")
        with self.con:
            self.con.execute("INSERT INTO dependency (parent_id, child_id, relation) VALUES (?,?,?)",
                             ("RELATORIO-FICTICIO-002", "RESUMO-FICTICIO-003", "used"))
        afetados = MemoryService(self.con, self.revisor).withdraw(mid, "retirada da regra")
        self.assertIn("RESUMO-FICTICIO-003", afetados)

    def test_f07_prefixo_coincidente_nao_e_alcancado(self):
        mid = self.memoria_aprovada()
        with self.con:
            self.con.execute("INSERT INTO dependency (parent_id, child_id, relation) VALUES (?,?,?)",
                             (mid + "x@1", "OUTRA-ENTIDADE-FICTICIA", "used"))
        afetados = MemoryService(self.con, self.revisor).withdraw(mid, "retirada da regra")
        self.assertNotIn("OUTRA-ENTIDADE-FICTICIA", afetados)

    def _retirada_antiga_so_no_banco(self, mid: str) -> None:
        """Como uma retirada feita por kit anterior: marca só a memória, no banco, sem o registro."""
        with self.con:
            self.con.execute("INSERT INTO tombstone VALUES (?,?,?,?,?,?)",
                             (mid, "juridico-lab", "revisor-juridico", "retirada antiga", "2026-01-01T00:00:00.000000Z",
                              "done"))
            self.con.execute("UPDATE memory_item SET status = 'withdrawn' WHERE memory_id = ?", (mid,))

    def test_f07_preenchimento_do_registro_inclui_derivados_por_revisao(self):
        mid = self.memoria_aprovada()
        MemoryService(self.con, self.jur).record_derivation(mid, 1, "RELATORIO-FICTICIO-004")
        self._retirada_antiga_so_no_banco(mid)
        log = self.root / "state" / "retiradas.jsonl"
        backup.backfill_tombstone_log(self.con, log)
        linhas = [r for r in backup.read_tombstone_log(log) if r.get("entity_id") == mid]
        self.assertTrue(linhas)
        self.assertIn("RELATORIO-FICTICIO-004", linhas[-1].get("affected", []),
                      "a reconstrução do registro não alcançou o derivado por revisão")

    def test_f07_init_bloqueia_derivado_de_memoria_ja_retirada(self):
        mid = self.memoria_aprovada()
        MemoryService(self.con, self.jur).record_derivation(mid, 1, "RELATORIO-FICTICIO-005")
        c, m = self.cache()
        c.put("juridico-lab", "resumo antigo?", m, "derivado fictício", ["RELATORIO-FICTICIO-005"])
        self._retirada_antiga_so_no_banco(mid)
        r = subprocess.run([sys.executable, "-B", "-m", "fundacao", "--raiz", str(self.root), "init"],
                           cwd=str(self.root), capture_output=True, text=True, encoding="utf-8",
                           env={k: v for k, v in os.environ.items() if k != "FUNDACAO_PRINCIPAL"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIsNotNone(self.con.execute("SELECT 1 FROM tombstone WHERE entity_id = 'RELATORIO-FICTICIO-005'")
                             .fetchone(), "o derivado da memória já retirada continua consumível")
        self.assertNotEqual(c.get("juridico-lab", "resumo antigo?", m)[0], "hit")


class TestF08AprovacaoGoldVinculada(_Base):
    def test_f08_aprovacao_de_a_nao_publica_b_preparada_no_intervalo(self):
        kj, sid, hash_a = self.gold(aprovar=False)
        con2 = connect(self.root / "state" / "state.sqlite")
        curador = KnowledgeService(self.root, con2, self.revisor)
        leu, liberar = threading.Event(), threading.Event()
        original = curador._source

        def pausa_depois_de_ler(*args):
            row = original(*args)
            leu.set()
            if not liberar.wait(10):
                raise RuntimeError("sincronização do teste expirou")
            return row

        curador._source = pausa_depois_de_ler
        resultado = {}

        def aprovar_a():
            try:
                resultado["decisao"] = curador.curate(sid, 1, APROVADO, hash_a, "2099-01-01", "ensaio")
            except Exception as exc:  # noqa: BLE001 — conflito explícito é o comportamento seguro
                resultado["erro"] = f"{type(exc).__name__}: {exc}"

        t = threading.Thread(target=aprovar_a)
        t.start()
        try:
            self.assertTrue(leu.wait(10))
            kj.prepare(sid, 1, ["TEXTO-FICTICIO-B sem revisão humana"])
            kj.index(sid, 1)
        finally:
            liberar.set()
            t.join(15)
            con2.close()  # antes do tearDown: banco aberto impediria apagar a pasta no Windows
        self.assertFalse(t.is_alive())
        row = self.con.execute("SELECT status, prepared_hash, approved_hash FROM source_version").fetchone()
        self.assertFalse(row["status"] == "approved" and row["prepared_hash"] != row["approved_hash"],
                         "a aprovação de A ficou valendo para o texto B")
        entregues = " ".join(h["body"] for h in kj.search("juridico-lab", "TEXTO FICTICIO"))
        self.assertNotIn("TEXTO-FICTICIO-B", entregues)
        self.assertNotEqual(resultado.get("decisao"), "approved")

    def test_f08_busca_e_citacao_recusam_hashes_divergentes(self):
        kj, sid, _h = self.gold()
        with self.con:  # estado inconsistente gravado por um caminho qualquer
            self.con.execute("UPDATE source_version SET approved_hash = 'hash-de-outro-texto'")
        self.assertEqual(kj.search("juridico-lab", "TEXTO FICTICIO"), [])
        chunk = self.con.execute("SELECT chunk_id FROM chunk LIMIT 1").fetchone()[0]
        self.assertFalse(kj.verify_citation(chunk)["valid"])


class TestF09ReprovacaoInvalidaCache(_Base):
    def _reprovar(self, sid, h, resultado="reprovado"):
        rubrica = {**APROVADO, "fidelidade": {"resultado": resultado, "evidencia": "erro identificado na revisão"}}
        return KnowledgeService(self.root, self.con, self.revisor).curate(sid, 1, rubrica, h, "2099-01-01", "ensaio")

    def test_f09_reprovar_fonte_aprovada_invalida_as_duas_portas(self):
        kj, sid, h = self.gold()
        c, m = self.cache()
        key = c.put("juridico-lab", "texto?", m, "TEXTO-FICTICIO-A aprovado e revisado", [sid + "@1"])
        self.assertEqual(self._reprovar(sid, h), "rejected")
        self.assertEqual(kj.search("juridico-lab", "TEXTO FICTICIO"), [])
        self.assertNotEqual(c.get("juridico-lab", "texto?", m)[0], "hit", "cache entregou fonte reprovada")
        self.assertNotEqual(c.get_by_key("juridico-lab", key)[0], "hit")

    def test_f09_voltar_a_pendente_tambem_invalida(self):
        kj, sid, h = self.gold()
        c, m = self.cache()
        key = c.put("juridico-lab", "texto?", m, "resposta fictícia", [sid + "@1"])
        self.assertEqual(self._reprovar(sid, h, "pendente"), "pending")
        self.assertNotEqual(c.get("juridico-lab", "texto?", m)[0], "hit")
        self.assertNotEqual(c.get_by_key("juridico-lab", key)[0], "hit")


class TestO3ApiDeProducao(unittest.TestCase):
    def test_o3_memoria_nao_expoe_modificador_de_teste(self):
        self.assertFalse(hasattr(MemoryService, "tamper_candidate_for_test"),
                         "mutador de teste continua na API de produção")


if __name__ == "__main__":
    unittest.main()
