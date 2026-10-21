"""A08/A21/A32 — trilha encadeada, consumo normalizado, rotas e alternativa autorizada (R12–R15, R39–R41)."""

from __future__ import annotations

import copy
import json
import unittest

from helpers import KIT, FoundationTestCase

from fundacao.adapters.base import ProviderRequest
from fundacao.adapters.cli import parse_claude_json, parse_codex_jsonl
from fundacao.adapters.simulado import SimulatedProvider
from fundacao.core import events, usage
from fundacao.core.routing import DEFAULT_POLICY, Router


class TestTrilha(FoundationTestCase):
    def test_cadeia_integra_e_adulteracao_detectada(self):
        ok, bad = events.verify_chain(self.con)
        self.assertTrue(ok)
        seq = self.con.execute("SELECT seq FROM event ORDER BY seq LIMIT 1 OFFSET 2").fetchone()[0]
        self.con.execute("UPDATE event SET payload_json = '{\"adulterado\":true}' WHERE seq = ?", (seq,))
        ok, bad = events.verify_chain(self.con)
        self.assertFalse(ok)
        self.assertEqual(bad, seq)

    def test_eventos_nao_guardam_conteudo(self):
        for row in self.con.execute("SELECT payload_json FROM event"):
            self.assertNotIn("SEGREDO", row["payload_json"])


class TestConsumo(unittest.TestCase):
    def test_claude_soma_categorias_de_cache(self):
        u = usage.normalize("claude-cli", {"input_tokens": 10, "cache_creation_input_tokens": 100,
                                           "cache_read_input_tokens": 1000, "output_tokens": 5},
                            route="cli_assinatura", run_id="run_x")
        self.assertEqual(u["tokens"]["input_total"], 1110)
        self.assertEqual(u["tokens"]["input_cached"], 1000)

    def test_codex_cached_contido_e_ausente_e_unknown(self):
        u = usage.normalize("codex-cli", {"input_tokens": 24763, "cached_input_tokens": 24448,
                                          "output_tokens": 122}, route="cli_assinatura", run_id="run_y")
        self.assertEqual(u["tokens"]["input_total"], 24763)
        self.assertEqual(u["tokens"]["reasoning"], "unknown")
        vazio = usage.normalize("claude-cli", None, route="cli_assinatura", run_id="run_z")
        self.assertEqual(vazio["tokens"]["input_total"], "unknown")
        self.assertEqual(vazio["measurement"], "nao_observado")

    def test_reducao(self):
        self.assertEqual(usage.reduction(12000, 6000), 0.5)
        self.assertIsNone(usage.reduction(0, 10))

    def test_parsers_das_cli_com_amostras_documentais(self):
        """Amostras construídas a partir da documentação (NÃO são saídas reais capturadas)."""
        c = parse_claude_json(json.dumps({"type": "result", "is_error": False, "result": "PRONTO",
                                          "session_id": "s1", "total_cost_usd": 0.0,
                                          "usage": {"input_tokens": 3, "output_tokens": 2}}))
        self.assertEqual((c["text"], c["is_error"]), ("PRONTO", False))
        jsonl = "\n".join([
            "aviso de diagnóstico que não é JSON",
            json.dumps({"type": "thread.started", "thread_id": "t1"}),
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "PRONTO"}}),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 9, "cached_input_tokens": 0,
                                                             "output_tokens": 1}}),
        ])
        x = parse_codex_jsonl(jsonl)
        self.assertEqual((x["text"], x["call_id"], x["failed"]), ("PRONTO", "t1", None))


class TestRotas(FoundationTestCase):
    def route_policy(self, **routes):
        p = json.loads(json.dumps(DEFAULT_POLICY))
        p["titular"] = "operador-juridico"
        for name, enabled in routes.items():
            p["routes"][name]["enabled"] = enabled
        return p

    def req(self):
        return ProviderRequest("juridico-lab", "task_1", "run_1", "Responda apenas: PRONTO",
                               [{"id": "D1", "sha256": "0" * 64, "text": "fictício"}])

    def test_rota_de_assinatura_so_para_o_titular(self):
        router = Router(self.con, self.eng, self.route_policy(cli_assinatura=True),
                        {"cli_assinatura": SimulatedProvider("assinatura-sim"), "simulado": SimulatedProvider()})
        motivos = dict(router.candidate_routes("default"))
        self.assertEqual(motivos["cli_assinatura"], "rota restrita ao titular")

    def test_alternativa_autorizada_apos_falha_e_bloqueio_sem_repeticao(self):
        principal = SimulatedProvider("principal", fail_with="auth_missing")
        alternativa = SimulatedProvider("alternativa")
        router = Router(self.con, self.jur, self.route_policy(cli_assinatura=True, local=True),
                        {"cli_assinatura": principal, "local": alternativa})
        res = router.call("default", self.req())
        self.assertEqual(res["state"], "succeeded_simulated")  # nunca "succeeded" indistinto
        self.assertTrue(res["result"].simulated)  # simulação rotulada, não prova provedor real
        self.assertEqual(principal.calls, 1)
        router2 = Router(self.con, self.jur, self.route_policy(cli_assinatura=True, simulado=False),
                         {"cli_assinatura": SimulatedProvider("p", fail_with="timeout")})
        res2 = router2.call("default", self.req())
        self.assertEqual(res2["state"], "blocked")
        self.assertEqual(sum(1 for a in res2["attempts"] if "state" in a), 1)

    def test_politica_distribuida_mantem_sigiloso_so_local(self):
        from fundacao.core.routing import load_policy
        if (KIT / "registry" / "kit_install.json").exists():
            # Raiz implantada: registry/ é configuração local (o instalar_kit.py a preserva). A rota sigilosa pode
            # mudar por decisão do titular, mas só vale com aceite assinado sobre a política exata; sem ele, a ordem
            # local fica sem efeito ao carregar (proposta 5; avaliação E11, F-05). Confere a rota que vale de fato.
            from fundacao.core.politica_rotas import desvio_sem_decisao
            efetiva = load_policy(KIT)["task_routes"]["sigiloso"]
            if desvio_sem_decisao(KIT) is not None:
                self.assertEqual(efetiva, DEFAULT_POLICY["task_routes"]["sigiloso"])
            return
        distribuida = load_policy(self.root)
        self.assertEqual(distribuida["task_routes"]["sigiloso"], DEFAULT_POLICY["task_routes"]["sigiloso"])
        self.assertEqual(distribuida["task_routes"]["sigiloso"], ["local"])

    def test_sigiloso_nao_escoa_para_rota_paga_quando_a_local_falha(self):
        # mesmo com api_paga habilitada e configurada, a falha da rota local bloqueia (não escoa)
        p = copy.deepcopy(DEFAULT_POLICY)
        p["routes"]["local"]["enabled"] = True
        p["routes"]["api_paga"]["enabled"] = True
        paga = SimulatedProvider("api-paga-sim")
        router = Router(self.con, self.jur, p, {"local": SimulatedProvider("local", fail_with="timeout"),
                                                "api_paga": paga})
        res = router.call("sigiloso", self.req())
        self.assertEqual(res["state"], "blocked")
        self.assertEqual(paga.calls, 0)

    def test_rota_sigilosa_nao_cai_em_destino_nao_autorizado(self):
        router = Router(self.con, self.jur, self.route_policy(), {"simulado": SimulatedProvider()})
        res = router.call("sigiloso", self.req())
        self.assertEqual(res["state"], "blocked")
        from fundacao.core.contracts import ValidationError
        with self.assertRaises(ValidationError):
            router.call("tipo-nao-declarado", self.req())  # falha fechada


if __name__ == "__main__":
    unittest.main()
