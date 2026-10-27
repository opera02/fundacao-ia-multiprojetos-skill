"""Escolha explícita de modelo/esforço; dublês, sem chamadas a provedores."""
import ast
import copy
import json
from decimal import Decimal
from unittest import mock

from helpers import FoundationTestCase
from fundacao.adapters.base import ProviderRequest, ProviderResult
from fundacao.adapters.cli import ClaudeCLIProvider, CodexCLIProvider
from fundacao.core.contracts import ValidationError
from fundacao.core.politica_rotas import validar_politica
from fundacao.core.routing import DEFAULT_POLICY, Router


class Espiao:
    route = "cli_assinatura"

    def __init__(self, provider, state="succeeded"):
        self.provider_id, self.state, self.requests = provider, state, []

    def call(self, request):
        self.requests.append(request)
        return ProviderResult(self.provider_id, self.route, self.state, text="fictício",
                              model="modelo-observado", usage={"custo_usd": 0.01})


class TestModelosPorTarefa(FoundationTestCase):
    def politica(self):
        p = copy.deepcopy(DEFAULT_POLICY)
        p["schema_version"] = "fundacao.route/2"
        p["titular"] = self.admin.principal_id
        p["routes"]["cli_assinatura"].update(enabled=True, max_calls=3)
        p["task_routes"]["analise"] = ["cli_assinatura"]
        p["task_models"] = {"analise": [
            {"route": "cli_assinatura", "provider_id": "claude-cli", "model": "claude-opus-5-5", "effort": "high"},
            {"route": "cli_assinatura", "provider_id": "codex-cli", "model": "gpt-6.1-sol", "effort": "medium"}]}
        return p

    def pedido(self):
        return ProviderRequest("juridico-lab", "task-ficticia", "run-ficticia", "Análise fictícia")

    def test_politica_valida_e_tipos_invalidos_falham_fechados(self):
        p = self.politica()
        self.assertEqual(validar_politica(p), [])
        for campo, valor in (("model", "--dangerous"), ("effort", "inventado"), ("provider_id", "nao-autorizado"),
                             ("route", "rota-nao-listada"), ("model", True)):
            x = copy.deepcopy(p); x["task_models"]["analise"][0][campo] = valor
            with self.subTest(campo=campo): self.assertTrue(validar_politica(x))

    def test_dois_provedores_na_mesma_rota_e_modelo_no_rastro(self):
        p = self.politica(); a, b = Espiao("claude-cli", "failed"), Espiao("codex-cli")
        pedido = self.pedido()
        resultado = Router(self.con, self.admin, p, {("cli_assinatura", a.provider_id): a,
                                                   ("cli_assinatura", b.provider_id): b}).call("analise", pedido)
        self.assertEqual(resultado["state"], "succeeded")
        self.assertEqual((a.requests[0].model, a.requests[0].effort), ("claude-opus-5-5", "high"))
        self.assertEqual((b.requests[0].model, b.requests[0].effort), ("gpt-6.1-sol", "medium"))
        self.assertIsNone(pedido.model)
        eventos = [json.loads(x[0]) for x in self.con.execute(
            "SELECT payload_json FROM event WHERE kind='provider_attempt'")]
        self.assertEqual([x["model_requested"] for x in eventos], ["claude-opus-5-5", "gpt-6.1-sol"])
        self.assertTrue(all(x["model"] == "modelo-observado" for x in eventos))

    def test_teto_agrega_os_provedores_sem_segunda_chamada(self):
        p = self.politica(); p["routes"]["cli_assinatura"]["max_calls"] = 1
        a, b = Espiao("claude-cli", "failed"), Espiao("codex-cli")
        resultado = Router(self.con, self.admin, p, {("cli_assinatura", a.provider_id): a,
                                                   ("cli_assinatura", b.provider_id): b}).call("analise", self.pedido())
        self.assertEqual(resultado["state"], "blocked")
        self.assertEqual((len(a.requests), len(b.requests)), (1, 0))

    def test_modelo_nao_autoriza_rota_sigilosa_ignorada(self):
        p = self.politica(); p["task_models"]["sigiloso"] = p["task_models"].pop("analise")
        a = Espiao("claude-cli")
        with self.assertRaises(ValidationError):
            Router(self.con, self.admin, p, {("cli_assinatura", a.provider_id): a}).call("sigiloso", self.pedido())
        self.assertEqual(a.requests, [])

    def test_flags_explicitas_sem_executar_clis(self):
        r = self.pedido(); r.model, r.effort = "claude-opus-5-5", "high"
        args = ClaudeCLIProvider().build_args("claude-ficticio", r)
        self.assertIn("--model", args); self.assertIn(r.model, args); self.assertIn("--effort", args)
        r.model, r.effort = "gpt-6.1-sol", "medium"
        args = CodexCLIProvider().build_args("codex-ficticio", r)
        self.assertIn("--model", args); self.assertIn(r.model, args)
        config = args[args.index("-c") + 1]
        chave, valor = config.split("=", 1)
        self.assertEqual((chave, ast.literal_eval(valor)), ("model_reasoning_effort", "medium"))

    def test_codex_cmd_com_esforco_chega_ao_executor_sem_executar_cli_real(self):
        from fundacao.adapters import cli
        from test_adaptadores_rotas import Captura
        r = self.pedido(); r.model, r.effort = "gpt-6.1-sol", "medium"
        saida = '\n'.join(json.dumps(e) for e in (
            {"type": "thread.started", "thread_id": "ficticio"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "fictício"}},
            {"type": "turn.completed", "usage": {"input_tokens": 3, "output_tokens": 1}}))
        captura = Captura(saida)
        with mock.patch.object(cli.shutil, "which", return_value="C:/ficticio/codex.cmd"), \
                mock.patch.object(cli, "_processo", captura):
            resultado = CodexCLIProvider(isolamento_leitura="executor fictício substituído").call(r)
        self.assertEqual((resultado.state, resultado.text), ("succeeded", "fictício"))
        args = captura.chamadas[0]["args"]
        chave, valor = args[args.index("-c") + 1].split("=", 1)
        self.assertEqual((chave, ast.literal_eval(valor)), ("model_reasoning_effort", "medium"))

    def test_teto_financeiro_recusa_provedor_sem_limite_nas_duas_versoes(self):
        for versao in ("fundacao.route/1", "fundacao.route/2"):
            with self.subTest(schema_version=versao):
                p = self.politica(); p["schema_version"] = versao; p.pop("task_models")
                p["routes"]["cli_assinatura"]["max_usd"] = 1.0
                self.assertEqual(validar_politica(p), [])
                a = Espiao("codex-cli")
                resultado = Router(self.con, self.admin, p, {"cli_assinatura": a}).call("analise", self.pedido())
                self.assertEqual((resultado["state"], a.requests), ("blocked", []))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM route_reservation").fetchone()[0], 0)

    def test_custo_integral_na_trilha_reduz_saldo_da_proxima_chamada(self):
        from fundacao.adapters import cli
        from fundacao.core.routing import route_spending_exact
        from test_adaptadores_rotas import Captura
        p = self.politica(); p["routes"]["cli_assinatura"]["max_usd"] = 0.01
        captura = Captura(json.dumps({"result": "fictício", "total_cost_usd": 0.0000004, "usage": {}}))
        adapter = ClaudeCLIProvider()
        router = Router(self.con, self.admin, p, {("cli_assinatura", "claude-cli"): adapter})
        with mock.patch.object(cli.shutil, "which", return_value="claude-ficticio"), \
                mock.patch.object(cli, "_processo", captura):
            self.assertEqual(router.call("analise", self.pedido())["state"], "succeeded")
            self.assertEqual(route_spending_exact(self.con, "cli_assinatura")[0], Decimal("0.0000004"))
            self.assertEqual(router.call("analise", self.pedido())["state"], "succeeded")
        args = captura.chamadas[1]["args"]
        self.assertLessEqual(Decimal(args[args.index("--max-budget-usd") + 1]), Decimal("0.0099996"))
        self.assertEqual(route_spending_exact(self.con, "cli_assinatura")[0], Decimal("0.0000008"))

    def test_reconciliacao_preserva_decimal_integral_e_o_teto_usa_esse_valor(self):
        from fundacao.core import events
        from fundacao.core.routing import reconcile_cost, route_spending_exact
        evento = events.emit(self.con, "provider_attempt", payload={"route": "cli_assinatura", "simulated": False,
                             "dispatched": True, "cost_usd": None})
        reconcile_cost(self.con, self.admin, "cli_assinatura", evento, "0.01000004", "painel fictício")
        self.assertEqual(route_spending_exact(self.con, "cli_assinatura")[0], Decimal("0.01000004"))
        p = self.politica(); p["routes"]["cli_assinatura"]["max_usd"] = 0.01000002
        a = ClaudeCLIProvider()
        resultado = Router(self.con, self.admin, p, {("cli_assinatura", "claude-cli"): a}).call("analise", self.pedido())
        self.assertEqual(resultado["state"], "blocked")

    def test_provedor_externo_nao_pode_se_disfarcar_de_rota_local(self):
        p = self.politica()
        p["task_models"] = {"sigiloso": [{"route": "local", "provider_id": "claude-cli",
                                        "model": "claude-opus-5-5", "effort": "high"}]}
        p["routes"]["local"]["enabled"] = True
        a = Espiao("claude-cli"); a.route = "local"
        with self.assertRaises(ValidationError):
            Router(self.con, self.admin, p, {("local", a.provider_id): a}).call("sigiloso", self.pedido())
        self.assertEqual(a.requests, [])

    def test_extra_args_nao_sobrescreve_modelo_da_politica(self):
        r = self.pedido(); r.model, r.effort = "claude-opus-5-5", "high"
        with self.assertRaises(ValidationError):
            ClaudeCLIProvider(extra_args=["--model", "outro"]).build_args("claude-ficticio", r)

    def test_teto_decimal_exato_nao_permite_chamada_extra(self):
        from fundacao.core import events
        p = self.politica(); p["routes"]["cli_assinatura"]["max_usd"] = 0.3
        events.emit(self.con, "provider_attempt", payload={"route": "cli_assinatura", "simulated": False,
                    "dispatched": True, "cost_usd": "0.300000"})
        a = Espiao("claude-cli")
        r = Router(self.con, self.admin, p, {("cli_assinatura", a.provider_id): a}).call("analise", self.pedido())
        self.assertEqual((r["state"], len(a.requests)), ("blocked", 0))

    def test_orcamento_da_cli_nunca_arredonda_acima_do_saldo(self):
        from decimal import Decimal
        args = ClaudeCLIProvider(max_budget_usd=0.005).build_args("claude-ficticio", self.pedido())
        self.assertLessEqual(Decimal(args[args.index("--max-budget-usd") + 1]), Decimal("0.005"))

    def test_consumo_claude_inclui_modelo_real_e_pedido(self):
        r = self.pedido(); r.model, r.effort = "claude-opus-5-5", "high"
        from fundacao.adapters import cli
        from test_adaptadores_rotas import Captura
        captura = Captura(json.dumps({"result": "ok", "modelUsage": {"modelo-real": {}}, "usage": {}}))
        with mock.patch.object(cli.shutil, "which", return_value="claude-ficticio"), \
                mock.patch.object(cli, "_processo", captura):
            result = ClaudeCLIProvider().call(r)
        self.assertEqual(result.usage["model"], "modelo-real")
        self.assertEqual(result.usage["model_requested"], r.model)

    def test_varios_modelos_observados_nao_inventam_um_modelo_principal(self):
        from fundacao.adapters.cli import parse_claude_json
        parsed = parse_claude_json(json.dumps({"result": "ok", "modelUsage": {"auxiliar": {}, "principal": {}}}))
        self.assertEqual(parsed["model"], "unknown")
