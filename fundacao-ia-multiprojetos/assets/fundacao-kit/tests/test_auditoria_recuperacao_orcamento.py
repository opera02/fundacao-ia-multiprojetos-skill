"""Auditoria externa da 1.3.4 — frente 3, recuperação e orçamento (F10–F12).

Cada teste exige o comportamento SEGURO; na 1.3.4 eles falham por asserção. Adaptador local
fictício (sem provedor, sem rede, custo fictício zero); falha de gravação injetada só na
fronteira do append ao registro protegido; corridas posicionadas por barreira sobre operações
reais. Cópias e restaurações em pastas descartáveis.
"""

from __future__ import annotations

import gc
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock

from helpers import FoundationTestCase

from fundacao.adapters.base import ProviderRequest, ProviderResult
from fundacao.core import backup, components
from fundacao.core.auth import Policy, resource_project
from fundacao.core.canon import sha256_text
from fundacao.core.db import connect
from fundacao.core.memory import MemoryService
from fundacao.core.routing import Router, spending_report

POLITICA = {"routes": {"api_creditos": {"enabled": True, "max_calls": 1}}, "task_routes": {"default": ["api_creditos"]}}


class _Base(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.extra = []
        self.conexoes = []
        self.log = self.root / "state" / "retiradas.jsonl"

    def tearDown(self):
        # Conexões extras fecham ANTES de apagar as pastas: no Windows, banco aberto impede apagar
        # (e a pasta sobraria no TMPDIR).
        for con in self.conexoes:
            con.close()
        gc.collect()
        for p in self.extra:
            shutil.rmtree(p, ignore_errors=True)
        super().tearDown()

    def pasta(self, nome: str):
        p = self.root.parent / f"{self.root.name}-{nome}"
        self.extra.append(p)
        return p

    def conexao(self, caminho=None):
        con = connect(caminho or self.root / "state" / "state.sqlite")
        self.conexoes.append(con)
        return con

    def cli(self, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "FUNDACAO_PRINCIPAL"}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run([sys.executable, "-B", "-m", "fundacao", "--raiz", str(self.root), *args],
                              capture_output=True, text=True, encoding="utf-8", cwd=str(self.root), env=env)

    def memoria(self, corpo="MEMORIA-FICTICIA-A", op="op-fic-1") -> str:
        mid = MemoryService(self.con, self.jur).propose(op_id=op, scope="project", project_id="juridico-lab",
                                                        kind="fato", origin="humano", body=corpo, source_ref="FIC")
        MemoryService(self.con, self.revisor).approve(mid, sha256_text(corpo))
        return mid


class TestF10ReservaDoTetoDeChamadas(_Base):
    def test_f10_duas_chamadas_simultaneas_com_teto_1_so_uma_entra_no_adaptador(self):
        entraram, transacao_aberta = [], []
        liberar, trava = threading.Event(), threading.Lock()
        cons = [self.conexao(), self.conexao()]

        class AdaptadorLocalFicticio:
            """Saída fictícia de contabilização; não há executável de provedor nem rede."""
            def __init__(self, con):
                self.con = con

            def call(self, request):
                with trava:
                    entraram.append(request.run_id)
                    transacao_aberta.append(self.con.in_transaction)
                liberar.wait(10)
                return ProviderResult("ensaio-ficticio-local", "api_creditos", "succeeded", text="FICTICIO",
                                      usage={"custo_usd": 0}, simulated=False, dispatched=True)

        routers = [Router(c, self.jur, POLITICA, {"api_creditos": AdaptadorLocalFicticio(c)}) for c in cons]
        estados = {}

        def chamar(i):
            estados[i] = routers[i].call("default", ProviderRequest("juridico-lab", "tarefa-fic", f"run-fic-{i}",
                                                                    "FICTICIO"))["state"]

        threads = [threading.Thread(target=chamar, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        prazo = time.time() + 10
        while time.time() < prazo and len(entraram) < 2 and not estados:
            time.sleep(0.01)
        liberar.set()
        for t in threads:
            t.join(15)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(len(entraram), 1, "as duas chamadas passaram pelo teto max_calls=1")
        self.assertEqual(sorted(estados.values()), ["blocked", "succeeded"])
        self.assertEqual(spending_report(self.con, "api_creditos")["chamadas"], 1)
        self.assertEqual(transacao_aberta, [False], "transação SQLite aberta durante a chamada externa")

    def test_f10_queda_durante_a_chamada_mantem_a_capacidade_consumida(self):
        class Queda(BaseException):
            """Interrupção do processo no meio da chamada (o `except` comum não a trata)."""

        class AdaptadorQueCai:
            def call(self, request):
                raise Queda()

        router = Router(self.con, self.jur, POLITICA, {"api_creditos": AdaptadorQueCai()})
        with self.assertRaises(Queda):
            router.call("default", ProviderRequest("juridico-lab", "t", "run-1", "FICTICIO"))

        class AdaptadorOk:
            calls = 0

            def call(self, request):
                AdaptadorOk.calls += 1
                return ProviderResult("ok", "api_creditos", "succeeded", usage={"custo_usd": 0}, dispatched=True)

        segunda = Router(self.con, self.jur, POLITICA, {"api_creditos": AdaptadorOk()}).call(
            "default", ProviderRequest("juridico-lab", "t", "run-2", "FICTICIO"))
        self.assertEqual(segunda["state"], "blocked", "chamada interrompida não contou no teto")
        self.assertEqual(AdaptadorOk.calls, 0)

    def test_f10_reserva_de_processo_que_caiu_e_reconciliada_por_id(self):
        """Complementar (caminho novo da 1.4.0): reserva aberta vira tentativa e é reconciliada uma vez."""
        from fundacao.core.contracts import ValidationError
        from fundacao.core.routing import reconcile_cost
        with self.con:  # reserva que um processo deixou aberta ao cair no meio da chamada
            self.con.execute("INSERT INTO route_reservation (reservation_id, route, project_id, subject, state, created_at)"
                             " VALUES ('rsv_ficticia', 'api_creditos', 'juridico-lab', 'operador-juridico', 'reserved', 'x')")
        rel = spending_report(self.con, "api_creditos")
        self.assertEqual(rel["reservas_em_andamento"], ["rsv_ficticia"])
        feito = reconcile_cost(self.con, self.admin, "api_creditos", "rsv_ficticia", "0.01", "painel fictício")
        self.assertEqual((feito["chamadas"], feito["reservas_em_andamento"], feito["sem_custo_medido"]), (1, [], []))
        with self.assertRaises(ValidationError):
            reconcile_cost(self.con, self.admin, "api_creditos", "rsv_ficticia", "0.01", "painel fictício")


class TestF11RevogacaoDuravelNoRegistro(_Base):
    def _restaurar_e_conferir(self, copia):
        alvo = self.pasta("restaurada")
        res = backup.restore(copia, alvo, self.log)
        permitido = Policy(self.conexao(alvo / "state" / "state.sqlite")).allowed(
            "operador-juridico", "read", resource_project("juridico-lab")) if res["released"] else False
        return res, permitido

    def test_f11_falha_no_registro_e_repeticao_nao_ressuscitam_o_acesso(self):
        copia = self.pasta("copia")
        backup.create_backup(self.root, copia, "antes-da-revogacao-ficticia")
        with mock.patch("fundacao.core.backup.append_tombstone_log",
                        side_effect=PermissionError("falha fictícia no registro")):
            with self.assertRaises(PermissionError):
                self.policy.revoke(self.admin, "operador-juridico", resource_project("juridico-lab"), "read")
        self.assertFalse(self.policy.allowed("operador-juridico", "read", resource_project("juridico-lab")))
        self.policy.revoke(self.admin, "operador-juridico", resource_project("juridico-lab"), "read")  # repetição
        backup.backfill_tombstone_log(self.con, self.log)  # preenchimento do init
        res, permitido = self._restaurar_e_conferir(copia)
        self.assertFalse(res["released"] and permitido, "a restauração devolveu o acesso revogado")

    def test_f11_queda_entre_o_commit_e_o_registro_e_reconciliada_no_reinicio(self):
        copia = self.pasta("copia")
        backup.create_backup(self.root, copia, "antes-da-revogacao-ficticia")

        class Queda(BaseException):
            pass

        with mock.patch("fundacao.core.backup.append_tombstone_log", side_effect=Queda()):
            with self.assertRaises(Queda):
                self.policy.revoke(self.admin, "operador-juridico", resource_project("juridico-lab"), "read")
        self.con.close()
        gc.collect()
        p = self.cli("init")  # processo novo, como um reinício
        self.con = connect(self.root / "state" / "state.sqlite")
        self.assertEqual(p.returncode, 0, p.stderr)
        res, permitido = self._restaurar_e_conferir(copia)
        self.assertFalse(res["released"] and permitido, "o reinício não reconciliou a revogação")

    def test_f11_desativacao_de_componente_interrompida_e_reconciliada_no_reinicio(self):
        reg = self.root / "registry" / "components" / "source_manifest.json"
        entrada = json.loads(reg.read_text(encoding="utf-8"))
        entrada.update(enabled=True, allowed_projects=["juridico-lab"])
        reg.write_text(json.dumps(entrada), encoding="utf-8")
        copia = self.pasta("copia")
        backup.create_backup(self.root, copia, "componente-ligado")

        class Queda(BaseException):
            pass

        with mock.patch("fundacao.core.backup.append_tombstone_log", side_effect=Queda()):
            with self.assertRaises(Queda):
                components.set_enabled(self.root, self.con, self.admin, "source_manifest", False)
        self.con.close()
        gc.collect()
        self.assertEqual(self.cli("init").returncode, 0)
        self.con = connect(self.root / "state" / "state.sqlite")
        alvo = self.pasta("restaurada")
        res = backup.restore(copia, alvo, self.log)
        ligado = json.loads((alvo / "registry" / "components" / "source_manifest.json").read_text(
            encoding="utf-8"))["enabled"] if res["released"] else False
        self.assertFalse(ligado, "o componente desligado voltou ligado na restauração")

    def test_f11_lacuna_deixada_por_kit_anterior_e_recomposta_pelo_preenchimento(self):
        from fundacao.core import events, revisions
        from fundacao.core.db import transaction
        copia = self.pasta("copia")
        backup.create_backup(self.root, copia, "antes-da-revogacao-ficticia")
        # Como na 1.3.4 com o append falhando: exclusão, revisão e evento confirmados no banco, nada no
        # registro e nenhuma intenção de exportação (o kit antigo não tinha outbox).
        with transaction(self.con):
            self.con.execute("DELETE FROM acl WHERE subject = ? AND resource = ? AND action = ?",
                             ("operador-juridico", resource_project("juridico-lab"), "read"))
            revisions.bump(self.con, resource_project("juridico-lab"), "policy_rev")
            events.emit(self.con, "acl_revoke", subject="operador-lab",
                        payload={"from": "operador-juridico", "resource": resource_project("juridico-lab"),
                                 "action": "read"})
        backup.backfill_tombstone_log(self.con, self.log)  # preenchimento do init
        revogacoes = [r for r in backup.read_tombstone_log(self.log) if r.get("entity_type") == "acl_revoke"]
        self.assertTrue(revogacoes, "o preenchimento do init não recompôs a revogação")
        res, permitido = self._restaurar_e_conferir(copia)
        self.assertFalse(res["released"] and permitido, "a restauração devolveu o acesso revogado")

    def test_f11_copia_nao_e_criada_com_lacuna_no_registro(self):
        with mock.patch("fundacao.core.backup.append_tombstone_log",
                        side_effect=PermissionError("falha fictícia no registro")):
            with self.assertRaises(PermissionError):
                self.policy.revoke(self.admin, "operador-juridico", resource_project("juridico-lab"), "read")
            with self.assertRaises(Exception):
                backup.create_backup(self.root, self.pasta("copia-com-lacuna"), "lacuna")
        # Com o registro de volta, a cópia reconcilia antes e sai normalmente.
        manifesto = backup.create_backup(self.root, self.pasta("copia-ok"), "ok")
        self.assertGreaterEqual(manifesto["retiradas"]["linhas"], 1)


class TestF12CorteCoerenteNaRestauracao(_Base):
    def _restaurar_com_escrita_na_origem(self, acao):
        copia = self.pasta("copia")
        backup.create_backup(self.root, copia, "antes")
        # A cópia é trazida para o preparo privado (1.7.7, auditoria da 1.7.6, #12; antes, shutil.copytree): a escrita
        # na origem entra no mesmo ponto — depois de lido o registro, durante a cópia, antes da reaplicação.
        original = backup.preparo.trazer_copia
        feito = []

        def copiando_enquanto_a_origem_muda(*a, **k):
            r = original(*a, **k)
            if not feito:
                feito.append(True)
                acao()
            return r

        alvo = self.pasta("restaurada")
        with mock.patch("fundacao.core.preparo.trazer_copia", side_effect=copiando_enquanto_a_origem_muda):
            res = backup.restore(copia, alvo, self.log)
        self.assertTrue(feito, "a escrita na origem não entrou durante a restauração")
        return res, alvo

    def test_f12_retirada_durante_a_restauracao_entra_ou_impede_a_liberacao(self):
        mid = self.memoria()
        res, alvo = self._restaurar_com_escrita_na_origem(
            lambda: MemoryService(self.con, self.revisor).withdraw(mid, "retirada DURANTE a restauração"))
        if res["released"]:
            con = self.conexao(alvo / "state" / "state.sqlite")
            entregues = [i["memory_id"] for i in MemoryService(con, self.jur).query(project_id="juridico-lab")]
            self.assertNotIn(mid, entregues, "o destino liberado entrega a memória retirada no intervalo")
            no_registro = [r["entity_id"] for r in backup.read_tombstone_log(alvo / "state" / "retiradas.jsonl")]
            for ent in no_registro:  # banco e registro do destino no mesmo corte
                if ent == mid:
                    self.assertIsNotNone(con.execute("SELECT 1 FROM tombstone WHERE entity_id = ?", (ent,)).fetchone())

    def test_f12_revogacao_durante_a_restauracao_entra_ou_impede_a_liberacao(self):
        res, alvo = self._restaurar_com_escrita_na_origem(
            lambda: self.policy.revoke(self.admin, "operador-juridico", resource_project("juridico-lab"), "read"))
        if res["released"]:
            permitido = Policy(self.conexao(alvo / "state" / "state.sqlite")).allowed(
                "operador-juridico", "read", resource_project("juridico-lab"))
            self.assertFalse(permitido, "o destino liberado devolve o acesso revogado no intervalo")


if __name__ == "__main__":
    unittest.main()
