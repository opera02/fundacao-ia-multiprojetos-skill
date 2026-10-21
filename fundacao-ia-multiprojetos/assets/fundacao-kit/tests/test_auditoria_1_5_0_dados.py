"""Auditorias externas da 1.4.1 e da 1.4.5 — memória, cache, conhecimento e canonização.

A09/#21/#23 (cache), A10 (aprovação concorrente), A11 (JSON canônico), #7 (arestas de derivação),
#11 (reconfirmação da autorização dentro da transação: memória e conhecimento), #12 (versão de
fonte), #15 (histórico de caso), #18 (fonte entre casos), #19 (promoção legada sem vínculo) e a
abertura de um banco 1.4.1 pelo kit novo.

Cada teste exige o comportamento SEGURO e falha por asserção no kit 1.4.1. Dados fictícios em raiz
descartável. Nas corridas, um gancho põe a operação concorrente — feita por OUTRA conexão SQLite —
exatamente entre a checagem e a transação da operação sob teste (ordem determinada, sem espera por
tempo), sem alterar a regra decisória do código.
"""

from __future__ import annotations

import json
import sqlite3
import unittest

from helpers import KIT, FoundationTestCase, sim

import fundacao.core.canon as canon
from fundacao.core import backup, revisions
from fundacao.core.auth import Policy, resource_case, resource_project
from fundacao.core.cache import ResponseCache
from fundacao.core.canon import canonical_json, sha256_json, sha256_text
from fundacao.core.contracts import AccessDenied, FundacaoError, RevisionConflict, ValidationError
from fundacao.core.db import MIGRATIONS, connect, utcnow
from fundacao.core.knowledge import KnowledgeService
from fundacao.core.memory import MemoryService

APROVADO = {c: {"resultado": "aprovado", "evidencia": f"conferido contra a página ({c})"}
            for c in ("origem", "fidelidade", "vigencia", "acesso", "finalidade")}
VELHA = "PRAZO-FICTICIO: sexta-feira"
NOVA = "PRAZO-FICTICIO: quinta-feira"
CASO_A, CASO_B = "caso-fic-001", "caso-fic-002"


class _Base(FoundationTestCase):
    def setUp(self):
        super().setUp()
        g = self.policy.grant
        # Identidades de ensaio a mais: aprovador do outro projeto, auditor só do projeto e o caso B.
        for pid in ("revisor-engenharia", "auditor-projeto", "operador-caso-b", "revisor-caso-b"):
            self.policy.register_principal(self.admin, pid)
        for action in ("read", "approve", "audit"):
            g(self.admin, "revisor-engenharia", resource_project("reversa-lab"), action)
        for action in ("read", "audit"):
            g(self.admin, "auditor-projeto", resource_project("juridico-lab"), action)
        for pid, action in (("operador-caso-b", "write"), ("revisor-caso-b", "approve")):
            g(self.admin, pid, resource_project("juridico-lab"), "read")
            g(self.admin, pid, resource_case("juridico-lab", CASO_B), "read")
            g(self.admin, pid, resource_case("juridico-lab", CASO_B), action)

    # ----------------------------------------------------------- apoio
    def memoria(self, corpo=VELHA, *, op="op-fic-1", escopo="project", caso=None, projeto="juridico-lab",
                autor=None, revisor=None) -> str:
        mid = MemoryService(self.con, autor or self.jur).propose(
            op_id=op, scope=escopo, project_id=None if escopo == "common" else projeto, case_id=caso,
            kind="decisao", origin="humano", body=corpo, source_ref="FONTE-FICTICIA")
        MemoryService(self.con, revisor or self.revisor).approve(mid, sha256_text(corpo))
        return mid

    def corrigir(self, mid, corpo=NOVA, revisao=1):
        MemoryService(self.con, self.jur).revise(mid, expected_revision=revisao, body=corpo,
                                                 source_ref="FONTE-FICTICIA-2", reason="correção fictícia",
                                                 change_kind="correcao")
        MemoryService(self.con, self.revisor).approve(mid, sha256_text(corpo))

    def cache(self, projeto="juridico-lab", quem=None, tipo="response"):
        c = ResponseCache(self.con, quem or self.jur, kind=tipo)
        m = c.server_meta(projeto, provider_id="simulado-a", model_revision="sim-1", prompt_revision="p1",
                          context_hash="ctx-ficticio", generation_config={"t": "0"})
        return c, m

    def comum_gravavel(self):
        """Concessões de ensaio para escrever e aprovar direto no comum."""
        self.policy.grant(self.admin, self.jur.principal_id, "common", "write")
        self.policy.grant(self.admin, self.revisor.principal_id, "common", "approve")

    def publicar_no_comum(self, corpo="PROCEDIMENTO-FICTICIO comum"):
        origem = self.memoria("REGRA-FICTICIA de origem", op="op-origem")
        promo, h = MemoryService(self.con, self.jur).request_promotion(origem, corpo, "candidato fictício")
        return origem, MemoryService(self.con, self.curador).decide_promotion(promo, True, h)

    def fonte(self, sid="juridico-lab/GUIA-FIC", versao=1, texto="TEXTO-FICTICIO de guia", *, caso=None,
              autor=None, revisor=None, aprovar=True):
        rel = f"fontes/{sid.split('/', 1)[1].lower()}-v{versao}.md"
        self.write_data("juridico-lab", rel, texto)
        kj = KnowledgeService(self.root, self.con, autor or self.jur)
        kj.register_source("juridico-lab", sid, versao, rel, case_id=caso)
        h = kj.prepare(sid, versao, [texto])
        kj.index(sid, versao)
        if aprovar:
            KnowledgeService(self.root, self.con, revisor or self.revisor).curate(sid, versao, APROVADO, h,
                                                                                 "2099-01-01", "ensaio")
        return h

    def status(self, mid):
        return self.con.execute("SELECT status FROM memory_item WHERE memory_id = ?", (mid,)).fetchone()[0]

    def retirado(self, entidade) -> bool:
        return self.con.execute("SELECT 1 FROM tombstone WHERE entity_id = ?", (entidade,)).fetchone() is not None

    def revogar_depois_da_checagem(self, servico, quem, recurso, acao):
        """Gancho da corrida do #11: assim que `require` autoriza (acao, recurso), OUTRA conexão revoga a
        concessão — antes de a operação abrir a transação de escrita."""
        original = servico.policy.require
        feito = []

        def require_e_revoga(principal, action, resource):
            original(principal, action, resource)
            if not feito and (action, resource) == (acao, recurso):
                feito.append(True)
                con2 = connect(self.root / "state" / "state.sqlite")
                try:
                    Policy(con2).revoke(self.admin, quem, recurso, acao)
                finally:
                    con2.close()

        servico.policy.require = require_e_revoga
        return feito


# =============================================================== A11 — JSON canônico
class TestA11JsonCanonico(unittest.TestCase):
    def test_a11_chaves_distintas_que_colidem_apos_nfc_sao_recusadas(self):
        pares = {"\u00e9": "CAMPO-FICTICIO-1", "e\u0301": "CAMPO-FICTICIO-2"}
        for valor in (pares, dict(reversed(list(pares.items()))), {"dados": [pares]}, [{"x": {"y": pares}}]):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                canonical_json(valor)

    def test_a11_entrada_sem_colisao_mantem_texto_e_hash_da_1_4_1(self):
        valor = {"b": "e\u0301", "a": 1, "c": [{"\u00e9": True, "x": None}], "d": {"z": "Z", "y": ["e\u0301"]}}
        self.assertEqual(canonical_json(valor),
                         '{"a":1,"b":"\u00e9","c":[{"x":null,"\u00e9":true}],"d":{"y":["\u00e9"],"z":"Z"}}')
        self.assertEqual(sha256_json(valor), "0a1b6a849e5267572a1b50ca4a91f58a8323823c096790819d80d69005bb3962")

    def test_a11_receita_nao_e_apresentada_como_rfc_8785(self):
        self.assertNotIn("compatível com a RFC 8785", canon.__doc__)
        modelo = KIT.parent / "templates" / "APROVACAO.json"
        if not modelo.is_file():
            self.skipTest("modelo APROVACAO.json fora desta instalação do kit")
        hash_alg = json.loads(modelo.read_text(encoding="utf-8"))["hash_alg"]
        self.assertNotIn("JSON RFC 8785)", hash_alg, "o modelo ainda promete JCS/RFC 8785")


# =============================================================== A09/#23 — cache e memória
class TestA09CacheDeMemoria(_Base):
    def test_a09_correcao_aprovada_invalida_as_duas_portas_e_a_referencia_por_revisao(self):
        mid = self.memoria()
        c, m = self.cache()
        chaves = {ref: c.put("juridico-lab", f"prazo {ref}?", m, VELHA, [ref]) for ref in (mid, f"{mid}@1")}
        MemoryService(self.con, self.jur).revise(mid, expected_revision=1, body=NOVA, source_ref="FONTE-2",
                                                 reason="correção fictícia", change_kind="correcao")
        for ref, chave in chaves.items():  # correção só proposta: a vigente continua a revisão 1
            self.assertEqual(c.get_by_key("juridico-lab", chave), ("hit", VELHA), ref)
        MemoryService(self.con, self.revisor).approve(mid, sha256_text(NOVA))
        for ref, chave in chaves.items():
            self.assertNotEqual(c.get("juridico-lab", f"prazo {ref}?", m)[0], "hit", f"pergunta, {ref}")
            self.assertNotEqual(c.get_by_key("juridico-lab", chave)[0], "hit", f"chave, {ref}")
        # Com metadados novos, citar a revisão substituída não a torna consumível; a vigente serve.
        c2, m2 = self.cache()
        antiga = c2.put("juridico-lab", "referência antiga?", m2, VELHA, [f"{mid}@1"])
        self.assertNotEqual(c2.get_by_key("juridico-lab", antiga)[0], "hit")
        vigente = c2.put("juridico-lab", "referência vigente?", m2, NOVA, [f"{mid}@2"])
        self.assertEqual(c2.get_by_key("juridico-lab", vigente), ("hit", NOVA))

    def test_a09_correcao_de_memoria_comum_invalida_todos_os_projetos(self):
        self.comum_gravavel()
        mid = self.memoria(escopo="common", op="op-comum")
        alvos = []
        for projeto, quem in (("juridico-lab", self.jur), ("reversa-lab", self.eng)):
            c, m = self.cache(projeto, quem)
            alvos.append((projeto, c, m, c.put(projeto, "prazo comum?", m, VELHA, [mid])))
        self.corrigir(mid)
        for projeto, c, m, chave in alvos:
            self.assertNotEqual(c.get(projeto, "prazo comum?", m)[0], "hit", projeto)
            self.assertNotEqual(c.get_by_key(projeto, chave)[0], "hit", projeto)

    def test_a09_memoria_nova_aprovada_expira_cache_negativo_do_projeto(self):
        c, m = self.cache()
        chave = c.put("juridico-lab", "prazo?", m, "nada encontrado", [])
        self.memoria()
        self.assertNotEqual(c.get("juridico-lab", "prazo?", m)[0], "hit")
        self.assertNotEqual(c.get_by_key("juridico-lab", chave)[0], "hit")

    def test_a09_publicacao_no_comum_expira_cache_negativo_de_outro_projeto(self):
        c, m = self.cache("reversa-lab", self.eng)
        chave = c.put("reversa-lab", "procedimento?", m, "nada encontrado", [])
        self.publicar_no_comum()
        self.assertNotEqual(c.get_by_key("reversa-lab", chave)[0], "hit")

    def test_a09_entrada_no_formato_anterior_nao_gera_acerto_nem_e_apagada(self):
        # Como o kit 1.4.x grava (chave sem o formato, tipo "response") — inclusive um processo antigo ainda
        # em execução depois da atualização, com as revisões atuais. Só o formato pode recusá-la.
        c, m = self.cache()
        antiga = sha256_json({"subject": m["authenticated_subject"], "scope": m["scope_fingerprint"],
                              "policy_rev": m["policy_revision"], "corpus_rev": m["corpus_revision"],
                              "provider_id": m["provider_id"], "model_rev": m["model_revision"],
                              "prompt_rev": m["prompt_revision"], "context_hash": m["context_hash"],
                              "generation": m["generation_config"], "question": "prazo?"})
        with self.con:
            self.con.execute("INSERT INTO cache_entry VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (antiga, "response", "juridico-lab", self.jur.principal_id, m["policy_revision"],
                              m["corpus_revision"], canonical_json("RESPOSTA-FICTICIA ANTIGA"), "[]", utcnow(), None))
        linha = lambda: tuple(self.con.execute("SELECT * FROM cache_entry WHERE cache_key = ?",  # noqa: E731
                                               (antiga,)).fetchone())
        antes = linha()
        self.assertEqual(c.get_by_key("juridico-lab", antiga), ("invalid", None))
        self.assertEqual(c.get("juridico-lab", "prazo?", m), ("miss", None))
        nova = c.put("juridico-lab", "prazo?", m, "RESPOSTA-FICTICIA NOVA", [])
        self.assertNotEqual(nova, antiga)
        self.assertEqual(c.get("juridico-lab", "prazo?", m), ("hit", "RESPOSTA-FICTICIA NOVA"))
        self.assertEqual(linha(), antes, "a entrada legada foi apagada ou alterada")
        self.assertEqual(c.kind, "response")  # atributo público preservado

    def test_a09_cache_de_resposta_e_de_recuperacao_nao_se_misturam(self):
        resposta, m = self.cache()
        recuperacao, _ = self.cache(tipo="retrieval")
        kr = resposta.put("juridico-lab", "consulta?", m, "RESPOSTA-FICTICIA", [])
        kt = recuperacao.put("juridico-lab", "consulta?", m, ["TRECHO-FICTICIO"], [])
        self.assertNotEqual(kr, kt)
        self.assertEqual(resposta.get("juridico-lab", "consulta?", m), ("hit", "RESPOSTA-FICTICIA"))
        self.assertEqual(recuperacao.get("juridico-lab", "consulta?", m), ("hit", ["TRECHO-FICTICIO"]))
        self.assertNotEqual(resposta.get_by_key("juridico-lab", kt)[0], "hit")
        self.assertEqual(recuperacao.get_by_key("juridico-lab", kt), ("hit", ["TRECHO-FICTICIO"]),
                         "a leitura pela porta do outro tipo apagou a entrada")


# =============================================================== #21 — revogação do comum
class TestN21CacheERevogacaoDoComum(_Base):
    def test_21_revogar_leitura_do_comum_invalida_cache_que_cita_memoria_comum(self):
        _, pub = self.publicar_no_comum()
        c, m = self.cache("reversa-lab", self.eng)
        chave = c.put("reversa-lab", "procedimento?", m, "PROCEDIMENTO-FICTICIO comum", [pub])
        self.assertEqual(c.get_by_key("reversa-lab", chave)[0], "hit")
        self.policy.revoke(self.admin, "operador-engenharia", "common", "read")
        self.assertTrue(self.policy.allowed("operador-engenharia", "read", resource_project("reversa-lab")))
        self.assertNotEqual(c.get("reversa-lab", "procedimento?", m)[0], "hit")
        self.assertNotEqual(c.get_by_key("reversa-lab", chave)[0], "hit")
        # Nem entrada gravada depois, com revisões atuais, entrega conteúdo do comum a quem não o lê mais.
        c2, m2 = self.cache("reversa-lab", self.eng)
        nova = c2.put("reversa-lab", "procedimento de novo?", m2, "PROCEDIMENTO-FICTICIO comum", [f"{pub}@1"])
        self.assertNotEqual(c2.get_by_key("reversa-lab", nova)[0], "hit")


# =============================================================== A10 — aprovação concorrente
class TestA10AprovacaoConcorrente(_Base):
    def _atrasada(self, mid, concorrente):
        """Aprovação pela OUTRA conexão: lê a revisão pendente, e então `concorrente` roda na conexão
        principal (completa, com commit) antes de a aprovação atrasada abrir a transação."""
        con2 = connect(self.root / "state" / "state.sqlite")
        self.addCleanup(con2.close)
        atrasada = MemoryService(con2, self.revisor)
        original, chamadas = atrasada._latest_revision, []

        def ler_e_deixar_outro_agir(memory_id):
            row = original(memory_id)
            if not chamadas:
                chamadas.append(row["revision"])
                concorrente()
            return row

        atrasada._latest_revision = ler_e_deixar_outro_agir
        return atrasada

    def test_a10_aprovacao_atrasada_nao_reverte_revisao_nova_ja_aprovada(self):
        mid = MemoryService(self.con, self.jur).propose(op_id="op-corrida", scope="project",
                                                        project_id="juridico-lab", kind="decisao",
                                                        origin="humano", body=VELHA, source_ref="FONTE-FICTICIA")

        def corrige_e_aprova():
            MemoryService(self.con, self.jur).revise(mid, expected_revision=1, body=NOVA, source_ref="FONTE-2",
                                                     reason="mudança fictícia", change_kind="mudanca_decisao")
            MemoryService(self.con, self.revisor).approve(mid, sha256_text(NOVA))

        with self.assertRaises(RevisionConflict):
            self._atrasada(mid, corrige_e_aprova).approve(mid, sha256_text(VELHA))
        atual = self.con.execute("SELECT status, revision, body FROM memory_item WHERE memory_id = ?",
                                 (mid,)).fetchone()
        self.assertEqual(tuple(atual), ("approved", 2, NOVA), "a aprovação antiga desfez a revisão nova")
        estados = [r[0] for r in self.con.execute(
            "SELECT state FROM memory_revision WHERE memory_id = ? ORDER BY revision", (mid,))]
        self.assertEqual(estados, ["proposed", "approved"])

    def test_a10_aprovacao_atrasada_nao_devolve_memoria_retirada_a_vigencia(self):
        mid = self.memoria()
        MemoryService(self.con, self.jur).revise(mid, expected_revision=1, body=NOVA, source_ref="FONTE-2",
                                                 reason="correção fictícia", change_kind="correcao")

        def retirar():
            MemoryService(self.con, self.revisor).withdraw(mid, "retirada fictícia")

        with self.assertRaises(FundacaoError):
            self._atrasada(mid, retirar).approve(mid, sha256_text(NOVA))
        self.assertEqual(self.status(mid), "withdrawn")


# =============================================================== #11 — reconfirmação na transação
class TestN11ReconfirmacaoNaTransacao(_Base):
    PROJ = resource_project("juridico-lab")

    def test_11_aprovar_memoria(self):
        mid = MemoryService(self.con, self.jur).propose(op_id="op-11a", scope="project", project_id="juridico-lab",
                                                        kind="fato", origin="humano", body=VELHA, source_ref="F")
        svc = MemoryService(self.con, self.revisor)
        feito = self.revogar_depois_da_checagem(svc, "revisor-juridico", self.PROJ, "approve")
        with self.assertRaises(AccessDenied):
            svc.approve(mid, sha256_text(VELHA))
        self.assertTrue(feito)
        self.assertEqual(self.status(mid), "proposed")

    def test_11_retirar_memoria(self):
        mid = self.memoria()
        svc = MemoryService(self.con, self.revisor)
        self.revogar_depois_da_checagem(svc, "revisor-juridico", self.PROJ, "approve")
        with self.assertRaises(AccessDenied):
            svc.withdraw(mid, "retirada fictícia")
        self.assertEqual(self.status(mid), "approved")
        self.assertFalse(self.retirado(mid))

    def test_11_revisar_memoria(self):
        mid = self.memoria()
        svc = MemoryService(self.con, self.jur)
        self.revogar_depois_da_checagem(svc, "operador-juridico", self.PROJ, "write")
        with self.assertRaises(AccessDenied):
            svc.revise(mid, expected_revision=1, body=NOVA, source_ref="F2", reason="r", change_kind="correcao")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM memory_revision WHERE memory_id = ?",
                                          (mid,)).fetchone()[0], 1)

    def test_11_pedir_e_decidir_promocao(self):
        mid = self.memoria()
        svc = MemoryService(self.con, self.jur)
        self.revogar_depois_da_checagem(svc, "operador-juridico", self.PROJ, "read")
        with self.assertRaises(AccessDenied):
            svc.request_promotion(mid, "PROCEDIMENTO-FICTICIO", "candidato")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM promotion").fetchone()[0], 0)
        mid2 = self.memoria("REGRA-FICTICIA 2", op="op-11b")
        promo, h = MemoryService(self.con, self.revisor).request_promotion(mid2, "PROCEDIMENTO-FICTICIO 2", "c")
        curador = MemoryService(self.con, self.curador)
        self.revogar_depois_da_checagem(curador, "curador-comum", "common", "curate")
        with self.assertRaises(AccessDenied):
            curador.decide_promotion(promo, True, h)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM memory_item WHERE scope = 'common'").fetchone()[0], 0)

    def test_11_registrar_derivacao(self):
        mid = self.memoria()
        svc = MemoryService(self.con, self.jur)
        feito = self.revogar_depois_da_checagem(svc, "operador-juridico", self.PROJ, "read")
        with self.assertRaises(AccessDenied):
            svc.record_derivation(mid, 1, "RELATORIO-FICTICIO-11")
        self.assertTrue(feito, "o registro de derivação não passou pela autorização")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM dependency WHERE child_id = ?",
                                          ("RELATORIO-FICTICIO-11",)).fetchone()[0], 0)

    def test_11_registrar_preparar_e_indexar_fonte(self):
        self.write_data("juridico-lab", "fontes/g.md", "TEXTO-FICTICIO")
        kj = KnowledgeService(self.root, self.con, self.jur)
        self.revogar_depois_da_checagem(kj, "operador-juridico", self.PROJ, "write")
        with self.assertRaises(AccessDenied):
            kj.register_source("juridico-lab", "juridico-lab/GUIA-11", 1, "fontes/g.md")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM source_version").fetchone()[0], 0)
        self.policy.grant(self.admin, "operador-juridico", self.PROJ, "write")
        kj = KnowledgeService(self.root, self.con, self.jur)
        kj.register_source("juridico-lab", "juridico-lab/GUIA-11", 1, "fontes/g.md")
        self.revogar_depois_da_checagem(kj, "operador-juridico", self.PROJ, "write")
        with self.assertRaises(AccessDenied):
            kj.prepare("juridico-lab/GUIA-11", 1, ["TEXTO-FICTICIO"])
        self.assertIsNone(self.con.execute("SELECT prepared_hash FROM source_version").fetchone()[0])
        self.policy.grant(self.admin, "operador-juridico", self.PROJ, "write")
        kj = KnowledgeService(self.root, self.con, self.jur)
        kj.prepare("juridico-lab/GUIA-11", 1, ["TEXTO-FICTICIO"])
        self.revogar_depois_da_checagem(kj, "operador-juridico", self.PROJ, "write")
        with self.assertRaises(AccessDenied):
            kj.index("juridico-lab/GUIA-11", 1)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM chunk").fetchone()[0], 0)

    def test_11_retirar_fonte(self):
        self.fonte()
        kr = KnowledgeService(self.root, self.con, self.revisor)
        self.revogar_depois_da_checagem(kr, "revisor-juridico", self.PROJ, "approve")
        with self.assertRaises(AccessDenied):
            kr.withdraw("juridico-lab/GUIA-FIC", 1, "retirada fictícia")
        self.assertFalse(self.retirado("juridico-lab/GUIA-FIC@1"))
        self.assertEqual(self.con.execute("SELECT status FROM source_version").fetchone()[0], "approved")


# =============================================================== #7 — arestas de derivação
class TestN7ArestasDeDerivacao(_Base):
    def test_7_aprovador_de_projeto_nao_retira_memoria_comum_por_aresta(self):
        _, pub = self.publicar_no_comum()
        propria = self.memoria("REGRA-FICTICIA do aprovador", op="op-propria")
        atacante = MemoryService(self.con, self.revisor)
        with self.assertRaises(FundacaoError):
            atacante.record_derivation(propria, 1, pub)
        with self.assertRaises(FundacaoError):
            atacante.record_derivation(propria, 1, f"{pub}@1")
        # Aresta gravada sem validação (kit anterior): a retirada não a segue.
        with self.con:
            self.con.execute("INSERT OR IGNORE INTO dependency (parent_id, child_id, relation) VALUES (?,?,?)",
                             (f"{propria}@1", pub, "used"))
        afetados = atacante.withdraw(propria, "retirada fictícia")
        self.assertNotIn(pub, afetados)
        self.assertEqual(self.status(pub), "approved")
        self.assertFalse(self.retirado(pub))
        vistos = [i["memory_id"] for i in MemoryService(self.con, self.eng).query(project_id="reversa-lab")]
        self.assertIn(pub, vistos, "a memória comum sumiu para os outros projetos")
        evento = json.loads(self.con.execute("SELECT payload_json FROM event WHERE kind = 'memory_withdrawn'"
                                             " ORDER BY seq DESC LIMIT 1").fetchone()[0])
        self.assertIn({"de": f"{propria}@1", "para": pub}, evento["arestas_ignoradas"])  # fica na trilha

    def test_7_nao_alcanca_memoria_de_outro_projeto_nem_de_caso_sem_acesso(self):
        alheia = self.memoria("REGRA-FICTICIA da engenharia", op="op-eng", projeto="reversa-lab", autor=self.eng,
                              revisor=sim("revisor-engenharia"))
        caso_b = self.memoria("FATO-FICTICIO do caso B", op="op-caso-b", escopo="case", caso=CASO_B,
                              autor=sim("operador-caso-b"), revisor=sim("revisor-caso-b"))
        propria = self.memoria("REGRA-FICTICIA do aprovador", op="op-propria")
        atacante = MemoryService(self.con, self.revisor)
        for alvo in (alheia, caso_b):
            with self.subTest(alvo=alvo), self.assertRaises(FundacaoError):
                atacante.record_derivation(propria, 1, alvo)
        with self.con:
            for alvo in (alheia, caso_b):
                self.con.execute("INSERT OR IGNORE INTO dependency (parent_id, child_id, relation) VALUES (?,?,?)",
                                 (f"{propria}@1", alvo, "used"))
        afetados = atacante.withdraw(propria, "retirada fictícia")
        for alvo in (alheia, caso_b):
            self.assertNotIn(alvo, afetados)
            self.assertEqual(self.status(alvo), "approved")

    def test_7_fonte_gold_nao_e_derivado_de_memoria(self):
        self.fonte()
        propria = self.memoria(op="op-propria")
        atacante = MemoryService(self.con, self.revisor)
        trecho = self.con.execute("SELECT chunk_id FROM chunk").fetchone()[0]
        for alvo in ("juridico-lab/GUIA-FIC@1", trecho, "reversa-lab/GUIA-FUTURA@1"):
            with self.subTest(alvo=alvo), self.assertRaises(FundacaoError):
                atacante.record_derivation(propria, 1, alvo)
        with self.con:
            self.con.execute("INSERT OR IGNORE INTO dependency (parent_id, child_id, relation) VALUES (?,?,?)",
                             (f"{propria}@1", "juridico-lab/GUIA-FIC@1", "used"))
        atacante.withdraw(propria, "retirada fictícia")
        self.assertFalse(self.retirado("juridico-lab/GUIA-FIC@1"), "a retirada de memória retirou fonte GOLD")
        self.assertTrue(KnowledgeService(self.root, self.con, self.jur).search("juridico-lab", "TEXTO FICTICIO guia"))

    def test_7_aresta_legada_no_mesmo_escopo_continua_seguida(self):
        # Compatibilidade: aresta antiga entre memórias do MESMO projeto (quem retira pode retirar as duas).
        origem = self.memoria(op="op-origem-7")
        derivada = self.memoria("REGRA-FICTICIA derivada", op="op-derivada-7")
        with self.con:
            self.con.execute("INSERT OR IGNORE INTO dependency (parent_id, child_id, relation) VALUES (?,?,?)",
                             (f"{origem}@1", derivada, "used"))
        with self.assertRaises(ValidationError):  # nova aresta de memória para memória: só pela promoção
            MemoryService(self.con, self.jur).record_derivation(origem, 1, derivada)
        afetados = MemoryService(self.con, self.revisor).withdraw(origem, "retirada fictícia")
        self.assertIn(derivada, afetados)
        self.assertEqual(self.status(derivada), "withdrawn")

    def test_7_origem_precisa_existir_e_ser_legivel(self):
        mid = self.memoria()
        with self.assertRaises(AccessDenied):
            MemoryService(self.con, self.eng).record_derivation(mid, 1, "RELATORIO-FICTICIO-ALHEIO")
        with self.assertRaises(ValidationError):
            MemoryService(self.con, self.jur).record_derivation(mid, 99, "RELATORIO-FICTICIO-99")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM dependency WHERE relation = 'used'").fetchone()[0], 0)

    def test_7_artefato_do_proprio_projeto_e_publicacao_continuam_alcancados(self):
        origem, pub = self.publicar_no_comum()
        mj = MemoryService(self.con, self.jur)
        mj.record_derivation(origem, 1, "RELATORIO-FICTICIO-7")
        mj.record_derivation(origem, 1, "juridico-lab/RELATORIO-FICTICIO-8")
        MemoryService(self.con, self.eng).record_derivation(pub, 1, "RESUMO-FICTICIO-DO-COMUM")
        afetados = MemoryService(self.con, self.revisor).withdraw(origem, "retirada fictícia")
        for derivado in ("RELATORIO-FICTICIO-7", "juridico-lab/RELATORIO-FICTICIO-8", pub, "RESUMO-FICTICIO-DO-COMUM"):
            self.assertIn(derivado, afetados)
            self.assertTrue(self.retirado(derivado), derivado)
        self.assertEqual(self.status(pub), "withdrawn")


# =============================================================== #12 — versão de fonte
class TestN12VersaoDeFonte(_Base):
    def test_12_versao_que_o_registro_protegido_nao_representa_e_recusada_no_registro(self):
        self.write_data("juridico-lab", "fontes/g.md", "TEXTO-FICTICIO")
        kj = KnowledgeService(self.root, self.con, self.jur)
        for versao in (-1, 0, True, 1.0, "1", 2 ** 63):
            with self.subTest(versao=versao), self.assertRaises(ValidationError):
                kj.register_source("juridico-lab", "juridico-lab/GUIA-VERSAO", versao, "fontes/g.md")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM source_version").fetchone()[0], 0)

    def test_12_retirada_de_versao_legada_negativa_nao_envenena_o_registro(self):
        # Linha gravada por kit anterior, que aceitava versão negativa no registro.
        with self.con:
            self.con.execute(
                "INSERT INTO source_version (source_id, version, project_id, case_id, rel_path, original_hash,"
                " status, registered_by, registered_at) VALUES (?,?,?,?,?,?,?,?,?)",
                ("juridico-lab/GUIA-LEGADA", -1, "juridico-lab", None, "fontes/x.md", "0" * 64, "pending",
                 "operador-juridico", "2026-01-01T00:00:00.000000Z"))
        kr = KnowledgeService(self.root, self.con, self.revisor)
        for versao in (-1, True):
            with self.subTest(versao=versao), self.assertRaises(ValidationError):
                kr.withdraw("juridico-lab/GUIA-LEGADA", versao, "retirada fictícia")
        log = self.root / "state" / "retiradas.jsonl"
        backup.read_tombstone_log(log)  # continua legível: init, backup e restauração seguem funcionando
        self.assertEqual(backup.outbox_pending(self.con), 0)
        self.assertNotIn("@-1", log.read_text(encoding="utf-8"))

    def test_12_retirada_com_versao_bool_nao_grava_id_true_no_registro(self):
        self.fonte()  # juridico-lab/GUIA-FIC, versão 1, aprovada
        kr = KnowledgeService(self.root, self.con, self.revisor)
        with self.assertRaises(ValidationError):  # True vale 1 no SQLite, mas viraria `id@True` no registro
            kr.withdraw("juridico-lab/GUIA-FIC", True, "retirada fictícia")
        backup.read_tombstone_log(self.root / "state" / "retiradas.jsonl")
        self.assertFalse(self.retirado("juridico-lab/GUIA-FIC@True"))
        self.assertEqual(self.con.execute("SELECT status FROM source_version").fetchone()[0], "approved")


# =============================================================== #15 — histórico de caso
class TestN15HistoricoDeCaso(_Base):
    def test_15_auditor_do_projeto_sem_acesso_ao_caso_nao_le_o_historico(self):
        caso = self.memoria("CASO-SEGREDO-FIC", op="op-caso", escopo="case", caso=CASO_A)
        projeto = self.memoria(op="op-projeto")
        auditor = MemoryService(self.con, sim("auditor-projeto"))
        with self.assertRaises(AccessDenied):
            auditor.history(caso)
        self.assertEqual([h["state"] for h in auditor.history(projeto)], ["approved"])
        self.policy.grant(self.admin, "auditor-projeto", resource_case("juridico-lab", CASO_A), "audit")
        self.assertEqual([h["body"] for h in auditor.history(caso)], ["CASO-SEGREDO-FIC"])


# =============================================================== #18 — fonte entre casos
class TestN18FontePorCaso(_Base):
    SID = "juridico-lab/GUIA-CASO"

    def test_18_identificador_do_caso_a_nao_e_registrado_no_caso_b(self):
        self.fonte(self.SID, 1, "TEXTO-FICTICIO do caso A", caso=CASO_A)
        self.write_data("juridico-lab", "fontes/b.md", "TEXTO-FICTICIO do caso B")
        kb = KnowledgeService(self.root, self.con, sim("operador-caso-b"))
        for versao in (1, 2):
            with self.subTest(versao=versao), self.assertRaises(ValidationError):
                kb.register_source("juridico-lab", self.SID, versao, "fontes/b.md", case_id=CASO_B)
        row = self.con.execute("SELECT status, is_current, case_id FROM source_version WHERE source_id = ?",
                               (self.SID,)).fetchall()
        self.assertEqual([tuple(r) for r in row], [("approved", 1, CASO_A)])

    def test_18_curadoria_so_substitui_versoes_do_mesmo_caso(self):
        self.fonte(self.SID, 1, "TEXTO-FICTICIO do caso A", caso=CASO_A)
        # Colisão gravada por kit anterior: a mesma fonte registrada no caso B, versão 2.
        self.write_data("juridico-lab", "fontes/b.md", "TEXTO-FICTICIO do caso B")
        with self.con:
            self.con.execute(
                "INSERT INTO source_version (source_id, version, project_id, case_id, rel_path, original_hash,"
                " status, registered_by, registered_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (self.SID, 2, "juridico-lab", CASO_B, "fontes/b.md", "0" * 64, "pending", "operador-caso-b",
                 "2026-01-01T00:00:00.000000Z"))
        h2 = KnowledgeService(self.root, self.con, sim("operador-caso-b")).prepare(
            self.SID, 2, ["TEXTO-FICTICIO do caso B"])
        KnowledgeService(self.root, self.con, sim("revisor-caso-b")).curate(self.SID, 2, APROVADO, h2,
                                                                            "2099-01-01", "ensaio")
        a = self.con.execute("SELECT status, is_current FROM source_version WHERE source_id = ? AND version = 1",
                             (self.SID,)).fetchone()
        self.assertEqual(tuple(a), ("approved", 1), "a curadoria do caso B substituiu a fonte do caso A")


# =============================================================== #19 — promoção legada
class TestN19PromocaoLegadaSemVinculo(_Base):
    def _legada(self, mid, corpo="PROCEDIMENTO-FICTICIO legado"):
        promo, h = MemoryService(self.con, self.jur).request_promotion(mid, corpo, "candidato fictício")
        with self.con:  # como uma linha pendente criada antes da migração 3 (sem vínculo com a origem)
            self.con.execute("UPDATE promotion SET source_revision = NULL, source_hash = NULL"
                             " WHERE promotion_id = ?", (promo,))
        return promo, h

    def comuns(self):
        return self.con.execute("SELECT COUNT(*) FROM memory_item WHERE scope = 'common'").fetchone()[0]

    def test_19_pendente_sem_vinculo_nao_publica_depois_da_correcao_da_origem(self):
        mid = self.memoria()
        promo, h = self._legada(mid)
        self.corrigir(mid)
        with self.assertRaises(ValidationError):
            MemoryService(self.con, self.curador).decide_promotion(promo, True, h)
        self.assertEqual(self.comuns(), 0)

    def test_19_pendente_sem_vinculo_falha_fechado_e_pode_ser_recusada(self):
        mid = self.memoria()
        promo, h = self._legada(mid)
        curador = MemoryService(self.con, self.curador)
        with self.assertRaises(ValidationError):
            curador.decide_promotion(promo, True, h)
        self.assertEqual(self.comuns(), 0)
        self.assertIsNone(curador.decide_promotion(promo, False, h))
        self.assertEqual(self.con.execute("SELECT decision FROM promotion WHERE promotion_id = ?",
                                          (promo,)).fetchone()[0], "rejected")


# =============================================================== banco 1.4.1 aberto pelo kit novo
class TestBanco141AbertoPeloKitNovo(FoundationTestCase):
    def _banco_1_4_1(self):
        caminho = self.root / "legado" / "state.sqlite"
        caminho.parent.mkdir(parents=True)
        raw = sqlite3.connect(str(caminho), isolation_level=None)
        try:
            for numero, script in enumerate(MIGRATIONS[:4], start=1):  # esquema exato da 1.4.1 (user_version 4)
                raw.execute("BEGIN IMMEDIATE")
                if callable(script):
                    script(raw)
                else:
                    for comando in [s.strip() for s in script.split(";") if s.strip()]:
                        raw.execute(comando)
                raw.execute(f"PRAGMA user_version = {numero}")
                raw.execute("COMMIT")
            agora = "2026-01-01T00:00:00.000000Z"
            raw.execute("INSERT INTO project VALUES ('proj-legado','Legado','Ensaio','1.0.0','1','active','adm',?)",
                        (agora,))
            raw.execute("INSERT INTO principal VALUES ('leitor-legado', '', ?)", (agora,))
            raw.execute("INSERT INTO acl VALUES ('leitor-legado','project:proj-legado','read','adm',?)", (agora,))
            raw.execute("INSERT INTO memory_item VALUES ('mem-legada','project','proj-legado',NULL,'fato','humano',"
                        "'approved',2,'B','hb','F','autor','rev','hb',NULL,?)", (agora,))
            raw.execute("INSERT INTO promotion (promotion_id, source_memory_id, candidate_body, candidate_hash,"
                        " justification, requested_by, requested_at, decision) VALUES"
                        " ('promo-legada','mem-legada','C','hc','j','autor',?,'pending')", (agora,))
            for chave, fontes in (("chave-legada-1", '["mem-legada"]'), ("chave-legada-2", "[]")):
                raw.execute("INSERT INTO cache_entry VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (chave, "response", "proj-legado", "leitor-legado", 1, 1, '"RESPOSTA-FICTICIA"',
                             fontes, agora, None))
        finally:
            raw.close()
        return caminho

    def test_abrir_banco_1_4_1_preserva_dados_e_nao_serve_cache_legado(self):
        caminho = self._banco_1_4_1()
        for _abertura in range(2):  # abrir e reabrir: nada muda no banco, nada legado é servido
            con = connect(caminho)
            try:
                self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], len(MIGRATIONS))
                self.assertEqual(con.execute("SELECT decision FROM promotion").fetchone()[0], "pending")
                self.assertEqual(tuple(con.execute("SELECT status, revision FROM memory_item").fetchone()),
                                 ("approved", 2))
                self.assertEqual(revisions.get(con, "project:proj-legado"), (1, 1))
                c = ResponseCache(con, sim("leitor-legado"))
                for chave in ("chave-legada-1", "chave-legada-2"):
                    self.assertEqual(c.get_by_key("proj-legado", chave), ("invalid", None), chave)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM cache_entry").fetchone()[0], 2, "apagou o legado")
            finally:
                con.close()


if __name__ == "__main__":
    unittest.main()
