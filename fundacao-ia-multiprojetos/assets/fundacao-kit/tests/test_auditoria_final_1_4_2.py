"""Auditoria final da 1.4.2 — kit: contrato da CLI com opções ausentes (AF-01) e leitura sem escrita (AF-09).

AF-01: opção obrigatória ausente (`projeto criar` sem `--nome`, `tarefa criar` sem `--objetivo`…) saía como
traceback, código 1 e sem JSON; o contrato da CLI é JSON no stderr e código 2.
AF-09: o coordenador exigia `write` no projeto até para ler; identidade só de leitura ou auditoria não
consultava tarefas. Agora abrir exige `read` e cada operação que muda estado exige `write` na própria operação.
Os três testes falham no kit 1.4.0 (skill 1.4.2) e passam no 1.4.1 (skill 1.4.3).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

from helpers import FoundationTestCase, sim

from fundacao.core.auth import resource_project
from fundacao.core.contracts import AccessDenied
from fundacao.core.tasks import Budget, Coordinator, StepDef


class _Cli(FoundationTestCase):
    def cli(self, principal: str | None, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "FUNDACAO_PRINCIPAL"}
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
        if principal:
            env["FUNDACAO_PRINCIPAL"] = principal
        return subprocess.run([sys.executable, "-B", "-m", "fundacao", "--raiz", str(self.root), *args],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              cwd=str(self.root), env=env)


class TestAF01OpcoesObrigatorias(_Cli):
    def test_af01_opcao_obrigatoria_ausente_sai_em_json_com_codigo_2(self):
        casos = {
            "projeto criar sem --nome": ("operador-lab", ["projeto", "criar", "--id", "gama-lab"]),
            "projeto drift sem --id": ("operador-lab", ["projeto", "drift"]),
            "tarefa criar sem --objetivo": ("operador-juridico", ["tarefa", "criar", "--projeto", "juridico-lab"]),
            "tarefa ver sem --id": ("operador-juridico", ["tarefa", "ver", "--projeto", "juridico-lab"]),
            "componente habilitar sem --id": ("operador-lab", ["componente", "habilitar"]),
            "acl conceder sem --recurso": ("operador-lab", ["acl", "conceder", "--principal", "operador-juridico"]),
        }
        for rotulo, (quem, args) in casos.items():
            with self.subTest(rotulo):
                p = self.cli(quem, *args)
                self.assertEqual(p.returncode, 2, (rotulo, p.stdout[-300:], p.stderr[-300:]))
                self.assertNotIn("Traceback", p.stderr, rotulo)
                erro = json.loads(p.stderr.strip().splitlines()[-1])["error"]
                self.assertIn("--", erro["message"], rotulo)


class TestAF09LeituraSemEscrita(_Cli):
    def setUp(self):
        super().setUp()
        self.policy.register_principal(self.admin, "leitor-juridico")
        self.policy.grant(self.admin, "leitor-juridico", resource_project("juridico-lab"), "read")
        self.leitor = sim("leitor-juridico")
        self.task = Coordinator(self.root, self.con, self.jur, "juridico-lab").create_task("tarefa fictícia")

    def test_af09_identidade_so_de_leitura_consulta_tarefas(self):
        coord = Coordinator(self.root, self.con, self.leitor, "juridico-lab")  # 1.4.0: AccessDenied aqui
        self.assertEqual(coord.get_task(self.task)["task_id"], self.task)
        p = self.cli("leitor-juridico", "tarefa", "ver", "--projeto", "juridico-lab", "--id", self.task)
        self.assertEqual(p.returncode, 0, p.stdout[-300:] + p.stderr[-300:])
        self.assertEqual(json.loads(p.stdout)["task_id"], self.task)

    def test_af09_identidade_so_de_leitura_nao_escreve(self):
        coord = Coordinator(self.root, self.con, self.leitor, "juridico-lab")
        with self.assertRaises(AccessDenied):
            coord.create_task("indevida (fictícia)")
        with self.assertRaises(AccessDenied):
            coord.start_run(self.task, "fluxo", "1", [StepDef("a")], Budget(max_calls=1))
        with self.assertRaises(AccessDenied):
            coord.cancel("run_inexistente")
        p = self.cli("leitor-juridico", "tarefa", "criar", "--projeto", "juridico-lab", "--objetivo", "indevida")
        self.assertEqual(p.returncode, 2)
        self.assertIn("E_ACCESS_DENIED", p.stderr)
        n = self.con.execute("SELECT COUNT(*) FROM event WHERE kind='access_denied' AND subject='leitor-juridico'").fetchone()[0]
        self.assertGreaterEqual(n, 3)


if __name__ == "__main__":
    unittest.main()
