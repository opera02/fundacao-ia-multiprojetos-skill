"""Avaliação E11 (21/10/2026), achado F-04: falha da CLI classificada como "sem login" por um trecho do texto
deixava de contar no teto de chamadas.

Bastava "401", "login", "credentials", "authenticate" ou "unauthorized" em qualquer ponto do erro ("rate limit
exceeded (request req_9f401a)", sonda C da E11) para a tentativa sair como `auth_missing` com `dispatched=False`:
fora de `max_calls`/`max_usd`, com a reserva liberada. Agora toda chamada cujo processo começou conta no teto (não
há como provar que ela não chegou ao provedor), e a falta de login só é reconhecida pelo aviso da própria CLI, em
frase inteira — o rótulo é diagnóstico. Nenhuma CLI de provedor é executada (`cli._processo` substituído).
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from helpers import FoundationTestCase
from test_adaptadores_rotas import ISOLAMENTO_FIC, Captura, req

from fundacao.adapters import cli
from fundacao.core.routing import DEFAULT_POLICY, Router, spending_report


def falha_do_claude(stderr: str):
    falho = Captura("", returncode=1, stderr=stderr)
    with mock.patch.object(cli.shutil, "which", return_value="claude-fic"), mock.patch.object(cli, "_processo", falho):
        return cli.ClaudeCLIProvider().call(req())


class TestClassificacaoDaFalha(unittest.TestCase):
    def test_trecho_solto_no_erro_nao_vira_falta_de_login(self):  # sonda C da E11
        for stderr in ("rate limit exceeded (request req_9f401a)", "overloaded; session 7401 retry later",
                       "upstream error: credentials rotated by the provider",
                       "status page: https://exemplo.invalid/login"):
            with self.subTest(stderr=stderr):
                res = falha_do_claude(stderr)
                self.assertEqual((res.state, res.dispatched), ("failed", True))

    def test_aviso_de_login_da_cli_e_reconhecido_e_conta_como_chamada(self):
        for stderr in ("Error: not logged in. Run claude login.", "Not logged in - Please run /login",
                       "Invalid API key - Please run /login"):
            with self.subTest(stderr=stderr):
                res = falha_do_claude(stderr)
                self.assertEqual((res.state, res.dispatched), ("auth_missing", True))

    def test_codex_sem_login_tambem_conta(self):
        falho = Captura("", returncode=1, stderr="Error: Not logged in. Run `codex login` first.")
        with mock.patch.object(cli.shutil, "which", return_value="codex-fic"), \
                mock.patch.object(cli, "_processo", falho):
            res = cli.CodexCLIProvider(isolamento_leitura=ISOLAMENTO_FIC).call(req())
        self.assertEqual((res.state, res.dispatched), ("auth_missing", True))


class TestTetoComFalhaDaCli(FoundationTestCase):
    def test_falha_com_401_no_texto_gasta_o_teto_de_chamadas(self):
        p = json.loads(json.dumps(DEFAULT_POLICY))
        p["routes"]["api_creditos"].update({"enabled": True, "max_calls": 1})
        p["routes"]["simulado"]["enabled"] = False
        p["task_routes"]["default"] = ["api_creditos"]
        falho = Captura("", returncode=1, stderr="rate limit exceeded (request req_9f401a)")
        with mock.patch.object(cli.shutil, "which", return_value="claude-fic"), \
                mock.patch.object(cli, "_processo", falho):
            router = Router(self.con, self.jur, p, {"api_creditos": cli.ClaudeCLIProvider(route="api_creditos")})
            self.assertEqual(router.call("default", req())["state"], "blocked")
            segunda = router.call("default", req())
        self.assertEqual(segunda["attempts"][0].get("skipped"), "teto de chamadas da rota atingido")
        self.assertEqual(len(falho.chamadas), 1)
        self.assertEqual(spending_report(self.con, "api_creditos")["chamadas"], 1)


if __name__ == "__main__":
    unittest.main()
