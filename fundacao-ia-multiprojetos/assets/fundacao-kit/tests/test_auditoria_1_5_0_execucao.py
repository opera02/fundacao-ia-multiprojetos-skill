"""Auditorias externas — execução, retomada, componentes e rotas (kit 1.4.1, skill 1.4.5).

Auditoria técnica da 1.4.1: A04 (saída reaproveitada sem conferir os bytes), A05 (posse vencida grava
sobre o sucessor), A06 (tempo limite do componente não encerra descendentes), A07 (prazo não barra
chamadas e renasce na retomada) e A08 (descoberta importa o pacote pai). Varredura da 1.4.5: #9 (rota
Codex sem isolamento de leitura), #11 (autorização fora da transação — parte de `tasks.py`), #14 (recibo
autodeclarado), #17 (custo negativo, NaN ou infinito fura `max_usd`) e #25 (= A08).

Cada teste de regressão exige o comportamento SEGURO e falha no kit 1.4.1 sem as correções; os três
marcados como não regressão (compatibilidade e a decisão sobre lease vencida) passam antes e depois.
Dados, identidades e "provedores" são fictícios; nada vai à rede. Corridas são posicionadas por
ganchos e eventos, com duas conexões SQLite; esperas existem só por condição (nunca como prova de ordem).
"""

from __future__ import annotations

import importlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock

from helpers import FoundationTestCase

from fundacao.adapters import cli
from fundacao.adapters.base import ProviderRequest, ProviderResult
from fundacao.core import components, events, usage
from fundacao.core.auth import Policy, resource_project
from fundacao.core.canon import canonical_json, sha256_bytes, sha256_file
from fundacao.core.contracts import AccessDenied, BudgetExhausted, FundacaoError
from fundacao.core.db import connect
from fundacao.core.routing import DEFAULT_POLICY, Router, reconcile_cost, spending_report
from fundacao.core.tasks import Budget, Coordinator, NeedsHuman, SimulatedInterrupt, StepDef


def esperar(condicao, segundos: float = 10.0) -> None:
    """Espera POR CONDIÇÃO (não por tempo fixo); falha se ela não ocorrer dentro do limite."""
    fim = time.monotonic() + segundos
    while not condicao():
        if time.monotonic() > fim:
            raise AssertionError("condição não ocorreu no limite de espera")
        time.sleep(0.005)


def processo_terminou(pid: int, segundos: float) -> bool:
    """True se o processo `pid` terminar dentro de `segundos` (espera do próprio SO, sem sondar marcas)."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k32.WaitForSingleObject.restype = wintypes.DWORD
        k32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        k32.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = k32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return True  # não existe mais
        try:
            return k32.WaitForSingleObject(handle, int(segundos * 1000)) == 0  # WAIT_OBJECT_0
        finally:
            k32.CloseHandle(handle)
    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


class _Base(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.con2 = connect(self.root / "state" / "state.sqlite")  # "outro processo" da corrida

    def tearDown(self):
        self.con2.close()
        super().tearDown()

    def nova_execucao(self, etapas, budget=None, con=None):
        coord = Coordinator(self.root, con or self.con, self.jur, "juridico-lab")
        task = coord.create_task("auditoria de execução (fictícia)")
        return coord, coord.start_run(task, "auditoria", "1", etapas, budget)

    def etapa(self, run: str, step_id: str = "a"):
        return self.con.execute("SELECT * FROM step WHERE run_id = ? AND step_id = ?", (run, step_id)).fetchone()

    def saidas(self) -> list[str]:
        return sorted(p.name for p in (self.root / "projects" / "juridico-lab").rglob("*.out"))

    def revogar_depois(self, alvo, metodo: str, quem: str, acao: str, *, armado: bool = True) -> dict:
        """Troca `alvo.metodo` por um gancho: assim que uma chamada ARMADA retorna, a outra conexão revoga
        a concessão. Posiciona a corrida "conferiu → revogaram → gravou" sem depender de tempo."""
        original = getattr(alvo, metodo)
        estado = {"armado": armado, "revogado": False}

        def gancho(*args, **kwargs):
            resultado = original(*args, **kwargs)
            if estado["armado"]:
                estado["armado"] = False
                Policy(self.con2).revoke(self.admin, quem, resource_project("juridico-lab"), acao)
                estado["revogado"] = True
            return resultado

        setattr(alvo, metodo, gancho)
        return estado


class TestA04A14SaidasConferidasPeloBanco(_Base):
    """A04/#14: o hash gravado no banco é a referência; arquivo e recibo na pasta do projeto, não."""

    def test_a04_dependencia_alterada_nao_e_consumida(self):
        coord, run = self.nova_execucao([StepDef("a"), StepDef("b", depends_on=("a",))])
        execucoes_a, consumidos = [], []
        handlers = {"a": lambda c: execucoes_a.append(1) or "ORIGINAL-FICTICIO",
                    "b": lambda c: consumidos.append(c.upstream["a"]) or "B-FICTICIO"}
        with self.assertRaises(SimulatedInterrupt):
            coord.run(run, handlers, interrupt=("a", "after_commit"))
        (self.root / self.etapa(run)["output_ref"]).write_text("ALTERADO-FICTICIO", encoding="utf-8")
        res = coord.resume(run, handlers)
        self.assertNotIn("ALTERADO-FICTICIO", consumidos, "saída alterada consumida sob o hash antigo")
        self.assertEqual(res["state"], "succeeded")
        self.assertEqual(consumidos, ["ORIGINAL-FICTICIO"])
        self.assertEqual(len(execucoes_a), 2, "a etapa com saída alterada devia ser refeita")

    def test_a04_saida_final_alterada_ou_removida_e_refeita(self):
        for remover in (False, True):
            with self.subTest(remover=remover):
                coord, run = self.nova_execucao([StepDef("a")])
                execucoes = []
                handlers = {"a": lambda c: execucoes.append(1) or "ORIGINAL-FICTICIO"}
                res = coord.run(run, handlers)
                saida = self.root / res["steps"][0]["output_ref"]
                if remover:
                    saida.unlink()
                else:
                    saida.write_text("ALTERADO-FICTICIO", encoding="utf-8")
                res = coord.resume(run, handlers)
                self.assertEqual(res["state"], "succeeded")
                self.assertEqual(len(execucoes), 2, "checkpoint com saída inválida foi reaproveitado")
                nova = self.root / res["steps"][0]["output_ref"]
                self.assertEqual(nova.read_text(encoding="utf-8"), "ORIGINAL-FICTICIO")
                self.assertEqual(sha256_file(nova), res["steps"][0]["output_hash"])

    def test_14_recibo_forjado_nao_confirma_etapa_que_nao_terminou(self):
        coord, run = self.nova_execucao([StepDef("a")])

        class Queda(BaseException):
            """O processo cai depois de reservar a etapa, antes de qualquer saída."""

        def cai(ctx):
            raise Queda()

        with self.assertRaises(Queda):
            coord.run(run, {"a": cai})
        linha = self.etapa(run)
        self.assertEqual(linha["state"], "running")
        ih = linha["input_hash"]  # visível a quem só lê o projeto (status)
        forjado = b"RESULTADO-FORJADO-FICTICIO"
        pasta = self.root / "projects" / "juridico-lab" / "outputs" / "runs" / run
        pasta.mkdir(parents=True, exist_ok=True)
        for nome in (f"a__{ih[:16]}.out", f"a__{ih[:16]}__exec-1.out"):  # nome antigo e nome por geração
            out = pasta / nome
            out.write_bytes(forjado)
            recibo = {"run_id": run, "step_id": "a", "input_hash": ih, "output_hash": sha256_bytes(forjado),
                      "execution": 1, "written_at": str(time.time())}
            out.with_suffix(".receipt.json").write_text(canonical_json(recibo), encoding="utf-8")
        execucoes = []
        res = coord.resume(run, {"a": lambda c: execucoes.append(1) or "RESULTADO-REAL-FICTICIO"},
                           now=time.time() + 120)
        self.assertEqual(execucoes, [1], "o recibo forjado confirmou uma etapa que nunca terminou")
        self.assertEqual(res["state"], "succeeded")
        self.assertEqual((self.root / res["steps"][0]["output_ref"]).read_bytes(), b"RESULTADO-REAL-FICTICIO")
        n = self.con.execute("SELECT COUNT(*) FROM event WHERE kind = 'step_reconciled' AND run_id = ?",
                             (run,)).fetchone()[0]
        self.assertEqual(n, 0)


class TestCompatibilidadeDasSaidas(_Base):
    """Não regressão (passa antes e depois): saídas e leitura de versões anteriores continuam valendo."""

    def test_saida_confirmada_com_nome_anterior_continua_valendo(self):
        coord, run = self.nova_execucao([StepDef("a"), StepDef("b", depends_on=("a",))])
        execucoes_a, consumidos = [], []
        handlers = {"a": lambda c: execucoes_a.append(1) or "SAIDA-ANTIGA-FICTICIA",
                    "b": lambda c: consumidos.append(c.upstream["a"]) or "B-FICTICIO"}
        with self.assertRaises(SimulatedInterrupt):
            coord.run(run, handlers, interrupt=("a", "after_commit"))
        linha = self.etapa(run)
        atual = self.root / linha["output_ref"]
        antigo = atual.with_name(f"a__{linha['input_hash'][:16]}.out")  # nome usado pelo kit 1.4.1
        atual.rename(antigo)
        with self.con:
            self.con.execute("UPDATE step SET output_ref = ? WHERE run_id = ? AND step_id = 'a'",
                             (antigo.relative_to(self.root).as_posix(), run))
        res = coord.resume(run, handlers)
        self.assertEqual(res["state"], "succeeded")
        self.assertEqual((len(execucoes_a), consumidos), (1, ["SAIDA-ANTIGA-FICTICIA"]))

    def test_texto_da_dependencia_mantem_fim_de_linha_normalizado(self):
        coord, run = self.nova_execucao([StepDef("a"), StepDef("b", depends_on=("a",))])
        consumidos = []
        res = coord.run(run, {"a": lambda c: "linha 1\r\nlinha 2\rfim",
                              "b": lambda c: consumidos.append(c.upstream["a"]) or "ok"})
        self.assertEqual(res["state"], "succeeded")
        self.assertEqual(consumidos, ["linha 1\nlinha 2\nfim"])


class TestA05PosseDaEtapa(_Base):
    """A05: a geração da posse (`executions`) é conferida na transação que publica, debita ou registra."""

    def test_a05_executor_com_posse_vencida_nao_grava_sobre_o_sucessor(self):
        primeiro, run = self.nova_execucao([StepDef("a")])
        segundo = Coordinator(self.root, self.con2, self.jur, "juridico-lab")
        comecou, liberar = threading.Event(), threading.Event()
        erros, recusas = [], []

        def lento(ctx):
            comecou.set()
            if not liberar.wait(10):
                raise RuntimeError("sincronização do teste esgotada")
            try:
                ctx.charge_call("provedor-ficticio-sem-rede")  # posse já substituída: não pode debitar
            except Exception as exc:  # noqa: BLE001 — o tipo da recusa é o que se registra
                recusas.append(type(exc).__name__)
            return "EXECUTOR-ANTIGO-FICTICIO"

        def rodar_primeiro():
            try:
                primeiro.run(run, {"a": lento}, lease_seconds=0)  # posse vence logo: a retomada pode assumir
            except BaseException as exc:  # noqa: BLE001
                erros.append(f"{type(exc).__name__}: {exc}")

        t = threading.Thread(target=rodar_primeiro)
        t.start()
        try:
            self.assertTrue(comecou.wait(10))

            def novo(ctx):
                ctx.charge_call("provedor-ficticio-sem-rede")
                return "SUCESSOR-FICTICIO"

            self.assertEqual(segundo.resume(run, {"a": novo})["state"], "succeeded")
        finally:
            liberar.set()
            t.join(15)
        self.assertFalse(t.is_alive())
        linha = self.etapa(run)
        saida = self.root / linha["output_ref"]
        self.assertEqual(sha256_file(saida), linha["output_hash"], "o executor antigo gravou sobre o sucessor")
        self.assertEqual(saida.read_text(encoding="utf-8"), "SUCESSOR-FICTICIO")
        self.assertEqual(recusas, ["PermanentError"], "a posse substituída ainda debitou chamada")
        self.assertEqual(self.con.execute("SELECT calls_used FROM run WHERE run_id = ?", (run,)).fetchone()[0], 1)
        self.assertEqual(erros, [])

    def test_a05_cancelamento_durante_a_etapa_nao_publica(self):
        coord, run = self.nova_execucao([StepDef("a")])

        def cancela(ctx):
            coord.cancel(run)
            return "CANCELADO-FICTICIO"

        res = coord.run(run, {"a": cancela})
        self.assertEqual(res["state"], "cancelled")
        self.assertEqual(self.saidas(), [])

    def test_a05_posse_vencida_sem_sucessor_ainda_publica(self):
        """Decisão de projeto (não regressão da auditoria): a lease só habilita a retomada por outro
        coordenador; enquanto ninguém assume, a geração continua dona da etapa e o resultado vale."""
        coord, run = self.nova_execucao([StepDef("a")])
        res = coord.run(run, {"a": lambda c: "ATRASADO-FICTICIO"}, lease_seconds=0)
        self.assertEqual(res["state"], "succeeded")
        self.assertEqual(res["steps"][0]["executions"], 1)


class TestA07Prazo(_Base):
    """A07: prazo gravado na primeira execução; vale no débito e não renasce na retomada."""

    def test_a07_chamada_depois_do_prazo_e_recusada(self):
        coord, run = self.nova_execucao([StepDef("a")], Budget(max_calls=4, max_seconds=0.5))
        debitos, recusas = [], []

        def handler(ctx):
            limite = time.time() + 0.6  # o prazo (0,5 s) começou antes, no início do run()
            esperar(lambda: time.time() > limite)
            try:
                ctx.charge_call("provedor-ficticio-sem-rede")
                debitos.append(1)
            except BudgetExhausted:
                recusas.append(1)
                raise
            return "FICTICIO"

        res = coord.run(run, {"a": handler})
        self.assertEqual(debitos, [], "chamada debitada depois do prazo")
        self.assertEqual(recusas, [1])
        self.assertEqual(res["state"], "failed")
        self.assertEqual(self.con.execute("SELECT calls_used FROM run WHERE run_id = ?", (run,)).fetchone()[0], 0)

    def test_a07_retomada_nao_renova_o_prazo(self):
        coord, run = self.nova_execucao([StepDef("a"), StepDef("b", depends_on=("a",))],
                                        Budget(max_calls=4, max_seconds=1.0))
        executou_b = []
        handlers = {"a": lambda c: "FICTICIO", "b": lambda c: executou_b.append(1) or "FICTICIO"}
        with self.assertRaises(SimulatedInterrupt):
            coord.run(run, handlers, interrupt=("a", "after_commit"))
        fim_primeira = time.time()  # o prazo foi gravado antes disto
        esperar(lambda: time.time() > fim_primeira + 1.05)
        res = Coordinator(self.root, self.con, self.jur, "juridico-lab").resume(run, handlers)
        self.assertEqual(executou_b, [], "a retomada ganhou um prazo novo")
        self.assertNotEqual(res["state"], "succeeded")
        n = self.con.execute("SELECT COUNT(*) FROM event WHERE kind = 'budget_time_exhausted' AND run_id = ?",
                             (run,)).fetchone()[0]
        self.assertGreaterEqual(n, 1)


class TestAutorizacaoNaTransacao11(_Base):
    """#11 (tasks.py): revogação confirmada entre a conferência e a transação de escrita vale."""

    def test_11_revogacao_antes_da_reserva_nao_executa_a_etapa(self):
        coord, run = self.nova_execucao([StepDef("a")])
        efeitos = []
        estado = self.revogar_depois(coord, "_input_hash", "operador-juridico", "write")
        with self.assertRaises(AccessDenied):
            coord.run(run, {"a": lambda c: efeitos.append("executou") or "FICTICIO"})
        self.assertTrue(estado["revogado"])
        self.assertEqual(efeitos, [], "a etapa rodou depois da revogação")
        self.assertEqual(self.etapa(run)["state"], "pending")

    def test_11_revogacao_entre_conferir_e_debitar_nao_debita(self):
        coord, run = self.nova_execucao([StepDef("a")], Budget(max_calls=2))
        estado = self.revogar_depois(coord, "_autorizar", "operador-juridico", "write", armado=False)
        chamou_provedor = []

        def handler(ctx):
            estado["armado"] = True  # só a conferência do débito dispara a revogação
            ctx.charge_call("provedor-ficticio-sem-rede")
            chamou_provedor.append(1)
            return "FICTICIO"

        with self.assertRaises(AccessDenied):
            coord.run(run, {"a": handler})
        self.assertTrue(estado["revogado"])
        self.assertEqual(chamou_provedor, [])
        self.assertEqual(self.con.execute("SELECT calls_used FROM run WHERE run_id = ?", (run,)).fetchone()[0], 0)
        self.assertEqual(self.etapa(run)["state"], "pending")

    def test_11_revogacao_entre_gravar_e_confirmar_nao_confirma(self):
        coord, run = self.nova_execucao([StepDef("a")])
        estado = self.revogar_depois(coord, "_write_output", "operador-juridico", "write")
        with self.assertRaises(AccessDenied):
            coord.run(run, {"a": lambda c: "SAIDA-FICTICIA"})
        self.assertTrue(estado["revogado"])
        linha = self.etapa(run)
        self.assertNotEqual(linha["state"], "succeeded", "saída confirmada depois da revogação")
        self.assertIsNone(linha["output_ref"])
        self.assertEqual(self.saidas(), [], "arquivo sem confirmação ficou na pasta")

    def test_11_cancelamento_com_revogacao_no_meio_nao_cancela(self):
        coord, run = self.nova_execucao([StepDef("a")])
        self.revogar_depois(coord, "_autorizar", "operador-juridico", "write")
        with self.assertRaises(AccessDenied):
            coord.cancel(run)
        self.assertEqual(self.con.execute("SELECT state FROM run WHERE run_id = ?", (run,)).fetchone()[0], "pending")
        self.assertEqual(self.etapa(run)["state"], "pending")

    def test_11_retomada_com_revogacao_no_meio_nao_reconcilia(self):
        coord, run = self.nova_execucao([StepDef("a")])
        with self.assertRaises(SimulatedInterrupt):
            coord.run(run, {"a": lambda c: "FICTICIO"}, interrupt=("a", "before_commit"))
        self.revogar_depois(coord, "_autorizar", "operador-juridico", "write")
        with self.assertRaises(AccessDenied):
            coord.resume(run, {"a": lambda c: "FICTICIO"})
        self.assertEqual(self.etapa(run)["state"], "running")
        n = self.con.execute("SELECT COUNT(*) FROM event WHERE kind = 'step_reconciled' AND run_id = ?",
                             (run,)).fetchone()[0]
        self.assertEqual(n, 0)

    def test_11_decisao_com_aprovador_revogado_no_meio_nao_vale(self):
        coord, run = self.nova_execucao([StepDef("decidir")])

        def pergunta(ctx):
            raise NeedsHuman("Aprovar o rascunho fictício?", ["sim", "nao"])

        self.assertEqual(coord.run(run, {"decidir": pergunta})["state"], "waiting_human")
        h = json.loads(self.etapa(run, "decidir")["decision_json"])["hash"]
        estado = self.revogar_depois(coord.policy, "require", "revisor-juridico", "approve")
        with self.assertRaises(AccessDenied):
            coord.decide(run, "decidir", "sim", self.revisor, h)
        self.assertTrue(estado["revogado"])
        linha = self.etapa(run, "decidir")
        self.assertEqual(linha["state"], "waiting_human", "decisão gravada com aprovação revogada")
        self.assertEqual(self.saidas(), [])


_PACOTE = "pacote_sonda_a08"


class TestA06A08Componentes(_Base):
    def _registrar(self, component_id: str, **campos) -> None:
        entrada = {"schema_version": "fundacao.component/1", "component_id": component_id, "version": "0.0.1",
                   "kind": "tool", "enabled": True, "entrypoint": f"fundacao.components.{component_id}:run",
                   "allowed_projects": ["juridico-lab"], "permissions": [], "timeout_seconds": 20, **campos}
        (self.root / "registry" / "components" / f"{component_id}.json").write_text(json.dumps(entrada),
                                                                                    encoding="utf-8")

    def test_a06_tempo_limite_encerra_os_descendentes_do_componente(self):
        pidfile = self.root / "neto.pid"
        marca = self.root / "NETO-SOBREVIVEU-FICTICIO.txt"
        neto = f"import pathlib, time; time.sleep(30); pathlib.Path({str(marca)!r}).write_text('vivo')"
        (self.root / "fundacao" / "components" / "pai_lento.py").write_text(
            "import pathlib, subprocess, sys, time\n"
            "def run(request):\n"
            f"    filho = subprocess.Popen([sys.executable, '-c', {neto!r}], stdin=subprocess.DEVNULL,\n"
            "                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
            f"    pathlib.Path({str(pidfile)!r}).write_text(str(filho.pid))\n"
            "    time.sleep(60)\n"
            "    return {}\n", encoding="utf-8")
        self._registrar("pai_lento", timeout_seconds=4)
        pid = None
        try:
            with self.assertRaises(FundacaoError) as ctx:
                components.dispatch(self.root, self.con, self.jur, "juridico-lab", "pai_lento", {})
            self.assertIn("tempo limite", str(ctx.exception))
            self.assertTrue(pidfile.exists(), "o componente não chegou a criar o neto (carga da máquina?)")
            pid = int(pidfile.read_text())
            self.assertTrue(processo_terminou(pid, 5), "o neto sobreviveu ao tempo limite do componente")
            self.assertFalse(marca.exists())
        finally:
            if pid is not None and not processo_terminou(pid, 0):
                try:
                    os.kill(pid, signal.SIGTERM)  # limpeza do teste quando o kit falha
                except OSError:
                    pass

    def _pacote_com_efeito(self):
        pacote = self.root / _PACOTE
        pacote.mkdir()
        marca = self.root / "IMPORTOU-PACOTE-PAI-FICTICIO.txt"
        (pacote / "__init__.py").write_text(
            f"import pathlib\npathlib.Path({str(marca)!r}).write_text('importado')\n", encoding="utf-8")
        (pacote / "filho.py").write_text("", encoding="utf-8")
        sys.path.insert(0, str(self.root))
        importlib.invalidate_caches()
        self.addCleanup(lambda: [sys.modules.pop(n, None) for n in (_PACOTE, f"{_PACOTE}.filho")])
        self.addCleanup(sys.path.remove, str(self.root))
        return marca

    def test_a08_descoberta_nao_importa_o_pacote_pai(self):
        marca = self._pacote_com_efeito()
        reg = self.root / "registry" / "components" / "source_manifest.json"
        entrada = json.loads(reg.read_text(encoding="utf-8"))
        entrada.update(enabled=False, requires_modules=[f"{_PACOTE}.filho", f"{_PACOTE}.inexistente"])
        reg.write_text(json.dumps(entrada), encoding="utf-8")
        inventario = {c["component_id"]: c for c in components.discover(self.root)}
        self.assertFalse(marca.exists(), "a descoberta executou o __init__.py da dependência")
        self.assertNotIn(_PACOTE, sys.modules)
        self.assertEqual(inventario["source_manifest"]["missing_dependencies"], [f"{_PACOTE}.inexistente"])

    def test_a08_despacho_confere_dependencia_sem_importar_no_processo_da_fundacao(self):
        marca = self._pacote_com_efeito()
        self.write_data("juridico-lab", "catalog.json", "{}")
        reg = self.root / "registry" / "components" / "source_manifest.json"
        entrada = json.loads(reg.read_text(encoding="utf-8"))
        entrada.update(enabled=True, allowed_projects=["juridico-lab"], requires_modules=[f"{_PACOTE}.filho"])
        reg.write_text(json.dumps(entrada), encoding="utf-8")
        res = components.dispatch(self.root, self.con, self.jur, "juridico-lab", "source_manifest",
                                  {"document_ids": []})
        self.assertEqual(res["result"]["files"], [])
        self.assertFalse(marca.exists(), "o despacho importou o pacote pai no processo da fundação")


class _PagoFicticio:
    """Adaptador de ensaio: devolve o custo pedido (válido ou não); não há provedor nem rede."""

    def __init__(self, custos):
        self.custos = list(custos)
        self.calls = 0
        self.max_budget_usd = None

    def call(self, request):
        self.calls += 1
        custo = self.custos.pop(0) if self.custos else 0.01
        return ProviderResult("pago-ficticio", "api_creditos", "succeeded", text="FICTICIO", dispatched=True,
                              usage={"custo_usd": custo})


def _politica(rota: str, **cfg) -> dict:
    p = json.loads(json.dumps(DEFAULT_POLICY))
    p["routes"][rota].update({"enabled": True, **cfg})
    p["routes"]["simulado"]["enabled"] = False
    p["task_routes"]["default"] = [rota]
    return p


def _pedido() -> ProviderRequest:
    return ProviderRequest("juridico-lab", "tarefa-fic", "run-fic", "FICTICIO")


class TestR17CustoInformado(_Base):
    def test_17_custo_invalido_nao_reduz_nem_anula_o_teto(self):
        for custo in (-1.0, float("nan"), float("-inf")):
            with self.subTest(custo=custo):
                rota = "api_paga"
                self.con.execute("DELETE FROM event WHERE kind = 'provider_attempt'")  # trilha não é o foco aqui
                pago = _PagoFicticio([custo, 0.04, 0.04, 0.04])
                router = Router(self.con, self.jur, _politica(rota, max_usd=0.05), {rota: pago})
                estados = [router.call("default", _pedido())["state"] for _ in range(3)]
                self.assertEqual(pago.calls, 1, f"custo {custo!r} deixou passar chamadas além do teto")
                self.assertEqual(estados, ["succeeded", "blocked", "blocked"])
                rel = spending_report(self.con, rota)
                self.assertEqual(len(rel["sem_custo_medido"]), 1, "custo inválido não ficou como desconhecido")

    def test_17_normalizacao_trata_custo_invalido_como_desconhecido(self):
        for custo in (-0.01, float("nan"), float("inf"), float("-inf"), True, "0.01"):
            with self.subTest(custo=custo):
                u = usage.normalize("claude-cli", {}, route="cli_assinatura", run_id="run-fic", cost_usd=custo)
                self.assertEqual(u["custo_usd"], usage.UNKNOWN)
        for custo in (0, 0.0, 0.01, 3):
            with self.subTest(custo=custo):
                u = usage.normalize("claude-cli", {}, route="cli_assinatura", run_id="run-fic", cost_usd=custo)
                self.assertEqual(u["custo_usd"], custo)
        parsed = cli.parse_claude_json('{"result": "ok", "total_cost_usd": NaN}')  # JSON do Python aceita NaN
        u = usage.normalize("claude-cli", {}, route="cli_assinatura", run_id="run-fic", cost_usd=parsed["cost_usd"])
        self.assertEqual(u["custo_usd"], usage.UNKNOWN)

    def test_17_custo_invalido_ja_registrado_bloqueia_e_pode_ser_reconciliado(self):
        for rota, gravado in (("api_creditos", "nan"), ("api_paga", "-5.000000")):
            with self.subTest(gravado=gravado):
                # Como o kit anterior gravava: o texto do número, sem validação.
                tentativa = events.emit(self.con, "provider_attempt", project_id="juridico-lab",
                                        subject="operador-juridico",
                                        payload={"route": rota, "provider_id": "legado-ficticio",
                                                 "state": "succeeded", "simulated": False, "dispatched": True,
                                                 "cost_usd": gravado})
                pago = _PagoFicticio([0.01])
                router = Router(self.con, self.jur, _politica(rota, max_usd=0.05), {rota: pago})
                bloqueado = router.call("default", _pedido())
                self.assertEqual(bloqueado["state"], "blocked")
                self.assertEqual(bloqueado["attempts"][0]["skipped"],
                                 "custo de chamada anterior não medido: teto não verificável")
                self.assertEqual(pago.calls, 0)
                feito = reconcile_cost(self.con, self.admin, rota, tentativa, "0.01", "fatura fictícia")
                self.assertEqual((feito["gasto_usd"], feito["sem_custo_medido"]), ("0.010000", []))
                self.assertEqual(router.call("default", _pedido())["state"], "succeeded")
                self.assertEqual(pago.calls, 1)


class _Captura:
    """Substitui `cli._processo`: registra a chamada e devolve a saída pronta (nenhuma CLI roda)."""

    def __init__(self, stdout: str):
        self.stdout = stdout
        self.chamadas = []

    def __call__(self, args, entrada, prazo, cwd, env):
        self.chamadas.append(list(args))
        return subprocess.CompletedProcess(args, 0, self.stdout, "")


class TestR09RotaCodex(unittest.TestCase):
    JSONL = "\n".join(json.dumps(e) for e in (
        {"type": "thread.started", "thread_id": "t-fic"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "PRONTO"}},
        {"type": "turn.completed", "usage": {"input_tokens": 3, "output_tokens": 1}}))

    def _chamar(self, prov):
        cap = _Captura(self.JSONL)
        with mock.patch.object(cli.shutil, "which", return_value="codex-fic"), \
                mock.patch.object(cli, "_processo", cap):
            return prov.call(ProviderRequest("juridico-lab", "t", "r", "FICTICIO")), cap

    def test_09_codex_sem_isolamento_de_leitura_declarado_nao_executa(self):
        res, cap = self._chamar(cli.CodexCLIProvider())
        self.assertEqual(cap.chamadas, [], "o Codex rodou sem isolamento de leitura declarado")
        self.assertEqual((res.state, res.dispatched), ("disabled", False))
        self.assertIn("isolamento", res.diagnostic)
        res, cap = self._chamar(cli.CodexCLIProvider(isolamento_leitura="conta do SO dedicada (ensaio fictício)"))
        self.assertEqual(len(cap.chamadas), 1)
        self.assertEqual(res.state, "succeeded")


if __name__ == "__main__":
    unittest.main()
