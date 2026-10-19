"""A09/A10 — coordenação, checkpoints, retomada, decisão humana e orçamento (R06–R08, R10, R39, R48)."""

from __future__ import annotations

import unittest
from pathlib import Path

from helpers import FoundationTestCase

from fundacao.core.contracts import ValidationError
from fundacao.core.tasks import (
    Budget, Coordinator, NeedsHuman, PermanentError, SimulatedInterrupt, StepDef, TransientError, validate_flow,
)

FLUXO = [
    StepDef("conferir-entradas", inputs=("relato.md",)),
    StepDef("extrair-fatos", depends_on=("conferir-entradas",), inputs=("relato.md",)),
    StepDef("elaborar-rascunho", depends_on=("extrair-fatos",)),
    StepDef("revisar-evidencias", depends_on=("elaborar-rascunho",), inputs=("relato.md",)),
]


class Contador:
    def __init__(self):
        self.n: dict[str, int] = {}

    def h(self, nome, saida=None):
        def handler(ctx):
            self.n[nome] = self.n.get(nome, 0) + 1
            return saida or f"{nome}: ok ({len(ctx.upstream)} insumos)"
        return handler


class TestFluxo(unittest.TestCase):
    def test_rejeita_dependencia_inexistente_e_ciclo(self):
        with self.assertRaises(ValidationError):
            validate_flow([StepDef("a", depends_on=("x",))])
        with self.assertRaises(ValidationError):
            validate_flow([StepDef("a", depends_on=("b",)), StepDef("b", depends_on=("a",))])


class TestRetomada(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.write_data("juridico-lab", "relato.md", "Pagamento em abril. FICTÍCIO.")
        self.coord = Coordinator(self.root, self.con, self.jur, "juridico-lab")
        self.task = self.coord.create_task("preparar relatório do caso Aurora")
        self.run_id = self.coord.start_run(self.task, "relatorio", "1", FLUXO, Budget(max_calls=4))
        self.c = Contador()
        self.handlers = {s.step_id: self.c.h(s.step_id) for s in FLUXO}

    def test_repetir_solicitacao_nao_cria_outra_execucao(self):
        self.assertEqual(self.coord.start_run(self.task, "relatorio", "1", FLUXO), self.run_id)

    def test_interrupcao_apos_extracao_e_retomada_sem_repetir(self):
        with self.assertRaises(SimulatedInterrupt):
            self.coord.run(self.run_id, self.handlers, interrupt=("extrair-fatos", "after_commit"))
        res = self.coord.resume(self.run_id, self.handlers)
        self.assertEqual(res["state"], "succeeded")
        self.assertEqual(self.c.n["extrair-fatos"], 1)
        execs = {s["step_id"]: s["executions"] for s in res["steps"]}
        self.assertTrue(all(v == 1 for v in execs.values()), execs)

    def test_saida_gravada_sem_confirmacao_e_reconciliada_pelo_recibo(self):
        with self.assertRaises(SimulatedInterrupt):
            self.coord.run(self.run_id, self.handlers, interrupt=("extrair-fatos", "before_commit"))
        estado = {s["step_id"]: s["state"] for s in self.coord.status(self.run_id)}
        self.assertEqual(estado["extrair-fatos"], "running")
        res = self.coord.resume(self.run_id, self.handlers)
        self.assertEqual(res["state"], "succeeded")
        self.assertEqual(self.c.n["extrair-fatos"], 1)  # não reexecutou o efeito já gravado
        n = self.con.execute("SELECT COUNT(*) FROM event WHERE kind='step_reconciled'").fetchone()[0]
        self.assertEqual(n, 1)

    def test_fonte_alterada_invalida_apenas_derivados(self):
        self.coord.run(self.run_id, self.handlers)
        self.write_data("juridico-lab", "relato.md", "Pagamento em maio. FICTÍCIO.")
        res = self.coord.run(self.run_id, self.handlers)
        self.assertEqual(res["state"], "succeeded")
        self.assertEqual(self.c.n["conferir-entradas"], 2)
        self.assertEqual(self.c.n["elaborar-rascunho"], 2)

    def test_dependencia_falha_bloqueia_etapas_seguintes(self):
        def falha(ctx):
            raise PermanentError("entrada inválida")
        self.handlers["extrair-fatos"] = falha
        res = self.coord.run(self.run_id, self.handlers)
        estados = {s["step_id"]: s["state"] for s in res["steps"]}
        self.assertEqual(estados["extrair-fatos"], "failed")
        self.assertEqual(estados["elaborar-rascunho"], "pending")
        self.assertNotIn("elaborar-rascunho", self.c.n)
        self.assertEqual(res["state"], "failed")

    def test_erro_transitorio_respeita_limite_de_tentativas(self):
        tentativas = {"n": 0}

        def instavel(ctx):
            tentativas["n"] += 1
            raise TransientError("timeout simulado")
        self.handlers["extrair-fatos"] = instavel
        res = self.coord.run(self.run_id, self.handlers)
        self.assertEqual(tentativas["n"], 3)
        self.assertEqual(res["state"], "failed")

    def test_orcamento_esgotado_interrompe_chamadas(self):
        chamadas = {"n": 0}

        def chama(ctx):
            for _ in range(10):
                ctx.charge_call("simulado-a")
                chamadas["n"] += 1
            return "nunca chega"
        self.handlers["extrair-fatos"] = chama
        res = self.coord.run(self.run_id, self.handlers)
        self.assertEqual(chamadas["n"], 4)
        self.assertEqual(res["state"], "failed")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM event WHERE kind='budget_exhausted'").fetchone()[0], 1)

    def test_cancelamento(self):
        res = self.coord.cancel(self.run_id)
        self.assertEqual(res["state"], "cancelled")
        self.assertEqual(self.coord.run(self.run_id, self.handlers)["state"], "cancelled")
        self.assertEqual(self.c.n, {})


class TestParalelismo(FoundationTestCase):
    def test_independentes_em_paralelo_e_dependente_aguarda(self):
        import json
        import time as _t
        coord = Coordinator(self.root, self.con, self.jur, "juridico-lab")
        task = coord.create_task("extrator e conferente em paralelo")
        fluxo = [StepDef("extrator"), StepDef("conferente"),
                 StepDef("consolidador", depends_on=("extrator", "conferente"))]
        run = coord.start_run(task, "paralelo", "1", fluxo)

        def lento(nome):
            def h(ctx):
                _t.sleep(0.4)
                return nome
            return h
        handlers = {"extrator": lento("fatos"), "conferente": lento("pendencias"),
                    "consolidador": lambda c: f"{c.upstream['extrator']}+{c.upstream['conferente']}"}
        res = coord.run(run, handlers, max_parallel=2)
        self.assertEqual(res["state"], "succeeded")
        tempos = {}
        for row in self.con.execute("SELECT payload_json FROM event WHERE kind='step_timing' AND run_id=?", (run,)):
            p = json.loads(row["payload_json"])
            tempos[p["step_id"]] = (float(p["started"]), float(p["ended"]), p["parallel_batch"])
        a, b, c = tempos["extrator"], tempos["conferente"], tempos["consolidador"]
        self.assertEqual((a[2], b[2]), (2, 2))
        self.assertLess(max(a[0], b[0]), min(a[1], b[1]))  # sobreposição real
        self.assertGreaterEqual(c[0], max(a[1], b[1]))      # dependente aguardou


class TestDecisaoHumana(FoundationTestCase):
    def test_decisao_vinculada_ao_conteudo_e_tarefas_independentes_continuam(self):
        self.write_data("juridico-lab", "relato.md", "FICTÍCIO")
        coord = Coordinator(self.root, self.con, self.jur, "juridico-lab")
        task = coord.create_task("entrega com objetivos incompatíveis")
        fluxo = [StepDef("escolher-objetivo"), StepDef("tarefa-independente", inputs=("relato.md",)),
                 StepDef("redigir", depends_on=("escolher-objetivo",))]
        run = coord.start_run(task, "decisao", "1", fluxo)

        def pergunta(ctx):
            raise NeedsHuman("Qual objetivo prevalece?", ["restituição", "entrega do produto"])
        handlers = {"escolher-objetivo": pergunta, "tarefa-independente": lambda c: "feito",
                    "redigir": lambda c: "rascunho com " + c.upstream["escolher-objetivo"]}
        res = coord.run(run, handlers)
        estados = {s["step_id"]: s["state"] for s in res["steps"]}
        self.assertEqual(estados["tarefa-independente"], "succeeded")
        self.assertEqual(estados["escolher-objetivo"], "waiting_human")
        with self.assertRaises(ValidationError):
            coord.decide(run, "escolher-objetivo", "restituição", self.revisor, "hash-errado")
        import json
        row = self.con.execute("SELECT decision_json FROM step WHERE run_id=? AND step_id='escolher-objetivo'",
                               (run,)).fetchone()
        h = json.loads(row["decision_json"])["hash"]
        coord.decide(run, "escolher-objetivo", "restituição", self.revisor, h)
        res = coord.run(run, handlers)
        self.assertEqual(res["state"], "succeeded")


class TestReferenciasRelativas(FoundationTestCase):
    def test_saida_referenciada_relativa_a_raiz(self):
        coord = Coordinator(self.root, self.con, self.jur, "juridico-lab")
        t = coord.create_task("referência relativa (fictícia)", idempotency_key="ref-rel")
        r = coord.start_run(t, "f", "1", [StepDef("a"), StepDef("b", depends_on=("a",))], Budget(max_calls=2))
        coord.run(r, {"a": lambda ctx: "saida-a", "b": lambda ctx: "saida-b"})
        refs = [row[0] for row in self.con.execute("SELECT output_ref FROM step WHERE run_id = ?", (r,))]
        self.assertEqual(len(refs), 2)
        for ref in refs:
            self.assertFalse(Path(ref).is_absolute(), ref)
            self.assertTrue((self.root / ref).exists(), ref)


class TestEstadoDaTarefa(FoundationTestCase):
    def test_tarefa_reflete_execucao_concluida_e_cancelada(self):
        coord = Coordinator(self.root, self.con, self.jur, "juridico-lab")
        t1 = coord.create_task("tarefa concluída (fictícia)", idempotency_key="estado-1")
        r1 = coord.start_run(t1, "f", "1", [StepDef("a")], Budget(max_calls=1))
        self.assertEqual(coord.get_task(t1)["state"], "pending")
        self.assertEqual(coord.run(r1, {"a": lambda ctx: "ok"})["state"], "succeeded")
        self.assertEqual(coord.get_task(t1)["state"], "succeeded")
        t2 = coord.create_task("tarefa cancelada (fictícia)", idempotency_key="estado-2")
        r2 = coord.start_run(t2, "f", "1", [StepDef("a")], Budget(max_calls=1))
        coord.cancel(r2)
        self.assertEqual(coord.get_task(t2)["state"], "cancelled")


if __name__ == "__main__":
    unittest.main()
