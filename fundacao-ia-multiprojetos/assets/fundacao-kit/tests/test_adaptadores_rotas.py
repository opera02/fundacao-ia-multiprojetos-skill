"""A08/A21 — adaptadores CLI isolados e tetos por rota (R12–R15, R39), sem chamar provedores.

Os adaptadores são exercitados com `cli._processo` substituído: o teste confere a linha de
comando, a entrada padrão (bytes), o ambiente e a pasta de trabalho que SERIAM usados. Prazo e
entrada também são provados de verdade com "CLIs" de ensaio em Python (um neto que segura as
saídas, um eco da entrada). Nenhuma CLI de provedor é executada.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import FoundationTestCase

from fundacao.adapters import cli
from fundacao.adapters.base import ProviderRequest, ProviderResult
from fundacao.core.contracts import AccessDenied
from fundacao.core.routing import DEFAULT_POLICY, Router, reconcile_cost, spending_report

OBJETIVO = 'Resuma o guia. Linha 2 com aspas " e & e | no meio.\nLinha 3: fim.'


class Captura:
    """Substitui `cli._processo(args, entrada, prazo, cwd, env)`."""
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = ""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr
        self.chamadas = []

    def __call__(self, args, entrada, prazo, cwd, env):
        self.chamadas.append({"args": list(args), "cwd": cwd, "entrada": entrada, "env": env, "prazo": prazo,
                              "cwd_vazio": bool(cwd) and os.path.isdir(cwd) and not os.listdir(cwd)})
        return subprocess.CompletedProcess(args, self.returncode, self.stdout, self.stderr)


class PagoDeEnsaio:
    """Dublê de rota paga (teste): devolve custo conhecido ou desconhecido."""
    def __init__(self, custo, *, saiu: bool = True, estado: str = "succeeded"):
        self.custo = custo
        self.saiu = saiu
        self.estado = estado
        self.calls = 0
        self.max_budget_usd = None

    def call(self, request):
        self.calls += 1
        return ProviderResult("pago-ensaio", "api_creditos", self.estado, text="ok", dispatched=self.saiu,
                              usage={"custo_usd": self.custo})


def req(objetivo: str = OBJETIVO):
    return ProviderRequest("juridico-lab", "task_1", "run_1", objetivo,
                           [{"id": "juridico-lab/GUIA-001", "sha256": "a" * 64, "text": "Dado de várias\nlinhas."}])


AMBIENTE_SUJO = {"FUNDACAO_PRINCIPAL": "titular", "ANTHROPIC_API_KEY": "sk-fic", "OPENAI_API_KEY": "sk-fic",
                 "SEGREDO_QUALQUER": "x", "CLAUDE_CONFIG_DIR": "C:/fic/claude", "CODEX_HOME": "C:/fic/codex"}


class TestAdaptadoresIsolados(FoundationTestCase):
    def conferir_entrada_e_ambiente(self, c: dict, propria: str):
        # O prompt inteiro (todas as linhas, aspas e &) vai pela entrada padrão, em bytes UTF-8
        # sem conversão de fim de linha, e não pelo argv.
        self.assertIsInstance(c["entrada"], bytes)
        self.assertNotIn(b"\r", c["entrada"])
        texto = c["entrada"].decode("utf-8")
        self.assertIn(OBJETIVO, texto)
        self.assertIn("Dado de várias\nlinhas.", texto)
        self.assertFalse(any("Resuma o guia" in a for a in c["args"]))
        env = c["env"]
        for k in ("FUNDACAO_PRINCIPAL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "SEGREDO_QUALQUER"):
            self.assertNotIn(k, env)
        self.assertIn(propria, env)
        self.assertIn("PATH", {k.upper() for k in env})

    def test_claude_roda_em_pasta_vazia_sem_ferramentas_nem_mcp(self):
        saida = json.dumps({"result": "PRONTO", "is_error": False, "session_id": "s1",
                            "total_cost_usd": 0.01, "usage": {"input_tokens": 3, "output_tokens": 1,
                                                              "cache_creation_input_tokens": 0,
                                                              "cache_read_input_tokens": 0}})
        cap = Captura(saida)
        prov = cli.ClaudeCLIProvider(max_budget_usd=0.5)
        with mock.patch.dict(os.environ, AMBIENTE_SUJO), \
                mock.patch.object(cli.shutil, "which", return_value="claude-fic"), \
                mock.patch.object(cli, "_processo", cap):
            res = prov.call(req())
        c = cap.chamadas[0]
        self.assertTrue(c["cwd_vazio"])
        self.assertNotEqual(Path(c["cwd"]).resolve(), self.root.resolve())
        a = c["args"]
        for trecho in (["-p", cli.INSTRUCAO_CLAUDE], ["--tools", ""], ["--disallowedTools", "mcp__*"],
                       ["--max-turns", "1"], ["--max-budget-usd", "0.50"], ["--permission-prompts", "none"]):
            self.assertIn(trecho, [a[i:i + 2] for i in range(len(a) - 1)], trecho)
        for flag in ("--strict-mcp-config", "--restricted", "--no-session-persistence"):
            self.assertIn(flag, a)
        self.conferir_entrada_e_ambiente(c, "CLAUDE_CONFIG_DIR")
        self.assertEqual((res.state, res.usage["custo_usd"]), ("succeeded", 0.01))

    def test_codex_roda_em_pasta_vazia_sem_configuracao_do_usuario(self):
        jsonl = "\n".join(json.dumps(e) for e in (
            {"type": "thread.started", "thread_id": "t1"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "PRONTO"}},
            {"type": "turn.completed", "usage": {"input_tokens": 3, "output_tokens": 1}}))
        cap = Captura(jsonl)
        with mock.patch.dict(os.environ, AMBIENTE_SUJO), \
                mock.patch.object(cli.shutil, "which", return_value="codex-fic"), \
                mock.patch.object(cli, "_processo", cap):
            res = cli.CodexCLIProvider().call(req())
        c = cap.chamadas[0]
        self.assertTrue(c["cwd_vazio"])
        for flag in ("--sandbox", "read-only", "--ephemeral", "--ignore-user-config", "--ignore-rules"):
            self.assertIn(flag, c["args"])
        self.assertEqual(c["args"][-1], "-")  # instruções pela entrada padrão
        self.conferir_entrada_e_ambiente(c, "CODEX_HOME")
        self.assertEqual(res.state, "succeeded")

    def test_shim_cmd_recusa_opcao_com_caractere_especial(self):
        cap = Captura("")
        prov = cli.CodexCLIProvider(extra_args=["-c", 'model="x" & echo INJETADO'])
        with mock.patch.object(cli.shutil, "which", return_value=r"C:\fic\codex.CMD"), \
                mock.patch.object(cli, "_processo", cap):
            res = prov.call(req())
        self.assertEqual((res.state, res.dispatched), ("failed", False))
        self.assertIn("cmd.exe", res.diagnostic)
        self.assertEqual(cap.chamadas, [])
        with mock.patch.object(cli.shutil, "which", return_value=r"C:\fic\codex.CMD"), \
                mock.patch.object(cli, "_processo", Captura("")) as ok:
            cli.CodexCLIProvider().call(req())  # opções fixas passam pelo shim
        self.assertEqual(len(ok.chamadas), 1)

    def test_falha_ao_iniciar_e_prompt_grande_ficam_no_contrato(self):
        def explode(*a, **kw):
            raise FileNotFoundError(206, "A linha de comando é muito longa")
        with mock.patch.object(cli.shutil, "which", return_value="claude-fic"), \
                mock.patch.object(cli, "_processo", explode):
            res = cli.ClaudeCLIProvider().call(req())
        self.assertEqual((res.state, res.dispatched), ("failed", False))
        self.assertIn("FileNotFoundError", res.diagnostic)
        cap = Captura("")
        with mock.patch.object(cli.shutil, "which", return_value="claude-fic"), \
                mock.patch.object(cli, "_processo", cap):
            grande = cli.ClaudeCLIProvider().call(req("x" * (cli.LIMITE_ENTRADA + 1)))
        self.assertEqual((grande.state, grande.dispatched, cap.chamadas), ("failed", False, []))

    def test_sem_login_nao_conta_como_chamada(self):
        falho = Captura("", returncode=1, stderr="Error: not logged in. Run claude login.")
        with mock.patch.object(cli.shutil, "which", return_value="claude-fic"), \
                mock.patch.object(cli, "_processo", falho):
            res = cli.ClaudeCLIProvider().call(req())
        self.assertEqual((res.state, res.dispatched), ("auth_missing", False))


class TestProcessoReal(unittest.TestCase):
    """Provas reais (sem provedor): "CLIs" de ensaio em Python rodam pelo `_rodar` de verdade."""

    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp(prefix="fundacao-cli-ensaio-"))

    def tearDown(self):
        shutil.rmtree(self.pasta, ignore_errors=True)

    def test_prazo_encerra_a_arvore_de_processos(self):
        """TA-2: a "CLI" deixa um neto segurando as saídas (como o node atrás de um shim .cmd). O prazo
        precisa valer: a chamada volta perto dele e o neto é encerrado antes de escrever a marca."""
        marca = self.pasta / "neto-sobreviveu.txt"
        neto = self.pasta / "neto.py"
        neto.write_text(f"import pathlib, time\ntime.sleep(4)\npathlib.Path({str(marca)!r}).write_text('vivo')\n",
                        encoding="utf-8")
        pai = self.pasta / "cli_lenta.py"
        pai.write_text(f"import subprocess, sys, time\nsubprocess.Popen([sys.executable, {str(neto)!r}])\n"
                       "time.sleep(30)\n", encoding="utf-8")
        inicio = time.monotonic()
        res = cli._rodar("ensaio", "cli_assinatura", [sys.executable, str(pai)], "x", 1, ())
        duracao = time.monotonic() - inicio
        self.assertIsInstance(res, ProviderResult)
        self.assertEqual(res.state, "timeout")
        self.assertLess(duracao, 4, "a chamada esperou o neto terminar")
        time.sleep(max(0.0, 6 - duracao))
        self.assertFalse(marca.exists(), "o neto sobreviveu ao encerramento da árvore")

    def test_prazo_vale_com_entrada_grande_que_a_cli_nao_le(self):
        """N1: entrada maior que o buffer do pipe e uma "CLI" presa antes de ler a entrada. O prazo
        vale, a CLI é encerrada e a resposta atrasada não vira sucesso."""
        marca = self.pasta / "respondeu-tarde.txt"
        presa = self.pasta / "cli_presa.py"
        presa.write_text(f"import pathlib, time\ntime.sleep(4)\npathlib.Path({str(marca)!r}).write_text('tarde')\n"
                         "print('ok')\n", encoding="utf-8")
        inicio = time.monotonic()
        res = cli._rodar("ensaio", "cli_assinatura", [sys.executable, str(presa)], "x" * 262_144, 1, ())
        duracao = time.monotonic() - inicio
        self.assertIsInstance(res, ProviderResult)
        self.assertEqual(res.state, "timeout")
        self.assertLess(duracao, 4, "o prazo não valeu com a entrada grande")
        time.sleep(max(0.0, 6 - duracao))
        self.assertFalse(marca.exists(), "a CLI presa não foi encerrada no prazo")

    def test_neto_orfao_nao_prende_nem_sobrevive(self):
        """N7: a "CLI" responde e termina, mas deixa um neto com as saídas herdadas. A resposta volta logo
        (o neto não a prende) e o neto é encerrado (Job Object no Windows; grupo de processos nos demais)."""
        marca = self.pasta / "orfao-sobreviveu.txt"
        neto = self.pasta / "orfao.py"
        neto.write_text(f"import pathlib, time\ntime.sleep(4)\npathlib.Path({str(marca)!r}).write_text('vivo')\n",
                        encoding="utf-8")
        pai = self.pasta / "cli_que_sai.py"
        pai.write_text(f"import subprocess, sys\nsubprocess.Popen([sys.executable, {str(neto)!r}])\nprint('resposta')\n",
                       encoding="utf-8")
        inicio = time.monotonic()
        saida = cli._rodar("ensaio", "cli_assinatura", [sys.executable, str(pai)], "x", 20, ())
        duracao = time.monotonic() - inicio
        self.assertNotIsInstance(saida, ProviderResult, getattr(saida, "diagnostic", ""))
        self.assertIn("resposta", saida[0].stdout)
        self.assertLess(duracao, 4, "o neto órfão prendeu a chamada")
        time.sleep(max(0.0, 6 - duracao))
        self.assertFalse(marca.exists(), "o neto órfão sobreviveu à chamada")

    def test_entrada_padrao_chega_byte_a_byte(self):
        """TA-8: a entrada é enviada em bytes; nenhum LF vira CRLF (nem um CRLF vira CR CR LF)."""
        recebido = self.pasta / "recebido.bin"
        eco = self.pasta / "eco.py"
        eco.write_text(f"import pathlib, sys\npathlib.Path({str(recebido)!r}).write_bytes(sys.stdin.buffer.read())\n"
                       "print('{}')\n", encoding="utf-8")
        prompt = "linha 1\nlinha 2 com acento é\r\nlinha 3 & | \" fim\n"
        saida = cli._rodar("ensaio", "cli_assinatura", [sys.executable, str(eco)], prompt, 30, ())
        self.assertNotIsInstance(saida, ProviderResult, getattr(saida, "diagnostic", ""))
        self.assertEqual(recebido.read_bytes(), prompt.encode("utf-8"))


class TestTetosPorRota(FoundationTestCase):
    def politica(self, **cfg):
        p = json.loads(json.dumps(DEFAULT_POLICY))
        p["routes"]["api_creditos"].update({"enabled": True, **cfg})
        p["routes"]["simulado"]["enabled"] = False
        p["task_routes"]["default"] = ["api_creditos"]
        return p

    def test_teto_de_custo_vale_antes_da_chamada(self):
        pago = PagoDeEnsaio(0.03)
        router = Router(self.con, self.jur, self.politica(max_usd=0.05), {"api_creditos": pago})
        self.assertEqual(router.call("default", req())["state"], "succeeded")
        self.assertEqual(router.call("default", req())["state"], "succeeded")  # 0,03 < 0,05
        terceira = router.call("default", req())  # 0,06 >= 0,05
        self.assertEqual(terceira["state"], "blocked")
        self.assertEqual(terceira["attempts"][0]["skipped"], "teto de custo da rota atingido")
        self.assertEqual(pago.calls, 2)

    def test_custo_desconhecido_bloqueia_ate_reconciliar(self):
        pago = PagoDeEnsaio(None)
        router = Router(self.con, self.jur, self.politica(max_usd=1.0), {"api_creditos": pago})
        self.assertEqual(router.call("default", req())["state"], "succeeded")
        segunda = router.call("default", req())
        self.assertEqual(segunda["attempts"][0]["skipped"],
                         "custo de chamada anterior não medido: teto não verificável")
        rel = spending_report(self.con, "api_creditos")
        self.assertEqual((rel["chamadas"], len(rel["sem_custo_medido"])), (1, 1))
        tentativa = rel["sem_custo_medido"][0]
        with self.assertRaises(AccessDenied):
            reconcile_cost(self.con, self.jur, "api_creditos", tentativa, "0.02", "painel")
        feito = reconcile_cost(self.con, self.admin, "api_creditos", tentativa, "0.02", "painel do provedor")
        self.assertEqual((feito["gasto_usd"], feito["sem_custo_medido"]), ("0.020000", []))
        self.assertEqual(router.call("default", req())["state"], "succeeded")  # rota liberada
        self.assertEqual(pago.calls, 2)

    def test_tentativa_que_nao_saiu_nao_bloqueia_a_rota(self):
        """NV-9: executável ausente ou sem login não gasta nem deixa custo pendente."""
        nao_saiu = PagoDeEnsaio(None, saiu=False, estado="failed")
        router = Router(self.con, self.jur, self.politica(max_usd=1.0, max_calls=1), {"api_creditos": nao_saiu})
        self.assertEqual(router.call("default", req())["state"], "blocked")
        segunda = router.call("default", req())
        self.assertNotIn("skipped", segunda["attempts"][0])  # tentou de novo: nada foi consumido
        self.assertEqual(nao_saiu.calls, 2)
        self.assertEqual(spending_report(self.con, "api_creditos")["chamadas"], 0)

    def test_teto_de_chamadas(self):
        pago = PagoDeEnsaio(0.0)
        router = Router(self.con, self.jur, self.politica(max_calls=1), {"api_creditos": pago})
        router.call("default", req())
        self.assertEqual(router.call("default", req())["attempts"][0]["skipped"],
                         "teto de chamadas da rota atingido")

    def test_cli_rota_gasto_exige_auditoria_ou_administracao(self):
        def rodar(quem, *args):
            env = {k: v for k, v in os.environ.items() if k != "FUNDACAO_PRINCIPAL"}
            env.update({"FUNDACAO_PRINCIPAL": quem, "PYTHONDONTWRITEBYTECODE": "1"})
            return subprocess.run([sys.executable, "-m", "fundacao", "--raiz", str(self.root), "rota", *args],
                                  capture_output=True, text=True, encoding="utf-8", cwd=str(self.root), env=env)
        negado = rodar("operador-juridico", "gasto", "--rota", "api_creditos")
        self.assertEqual(negado.returncode, 2)
        self.assertIn("E_ACCESS_DENIED", negado.stderr)
        ok = rodar("operador-lab", "gasto", "--rota", "api_creditos")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["sem_custo_medido"], [])


if __name__ == "__main__":
    unittest.main()
