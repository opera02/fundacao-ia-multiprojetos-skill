"""Trava de projeto e identidade `sessao-<p>` (1.7.10; contratos do lote 2, §4): com FUNDACAO_PROJETO_TRAVADO=<p>, a
política tem um teto que nenhuma linha de ACL derruba e `sessao-<p>` tem exatamente read, write e use em project:<p>,
derivados da trava (sem linha no banco). Cada negação tem o seu teste; a CLI travada recusa o que a sessão não pede
(comando fora do mapa, --raiz diferente, qualquer --ancora, caminho fora de projects/<p>/) e o ciclo preparar →
assinar → registrar → concluir funciona com `sessao-<p>`, com o assinante vindo da configuração. Da correção do lote 2:
`eventos` e `memoria licao historico` fora do mapa (emenda E2) e o servidor MCP do kit, que não inicia na sessão
travada. Raiz descartável, identidades e chaves de ensaio."""

from __future__ import annotations

import io
import json
import os
import shutil
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from helpers import FoundationTestCase, resource_case, resource_project, sim

from fundacao import mcp_servidor, porteiro_cliente
from fundacao.__main__ import main
from fundacao.core import auth, decisoes, events
from fundacao.core.auth import ENV_PRINCIPAL, Policy, principal_from_env
from fundacao.core.contracts import AccessDenied
from fundacao.core.projects import list_projects
from fundacao.core.tasks import Coordinator

P, OUTRO = "juridico-lab", "reversa-lab"
SESSAO = "sessao-" + P
ACOES = ("admin", "read", "write", "approve", "curate", "audit", "use")


class TravaCase(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.env = mock.patch.dict(os.environ, {})
        self.env.start()
        self.addCleanup(self.env.stop)
        for nome in (auth.ENV_TRAVA, ENV_PRINCIPAL, auth.ENV_ASSINANTE, auth.ENV_RAIZ):
            os.environ.pop(nome, None)

    def travar(self, projeto: str | None = P, quem: str | None = SESSAO, assinante: str | None = None) -> None:
        for nome, valor in ((auth.ENV_TRAVA, projeto), (ENV_PRINCIPAL, quem), (auth.ENV_ASSINANTE, assinante)):
            if valor is None:
                os.environ.pop(nome, None)
            else:
                os.environ[nome] = valor
        os.environ[auth.ENV_RAIZ] = str(self.root)

    def cli(self, *args, raiz=None) -> tuple[int, dict | None, str]:
        saida, erro = io.StringIO(), io.StringIO()
        with redirect_stdout(saida), redirect_stderr(erro):
            codigo = main(["--raiz", str(raiz or self.root), *args])
        texto = saida.getvalue()
        return codigo, (json.loads(texto) if texto.strip() else None), erro.getvalue()

    def erro(self, texto: str) -> dict:
        return json.loads(texto)["error"]


class TestPolitica(TravaCase):
    def test_sessao_tem_exatamente_read_write_use_no_projeto_travado(self):
        self.travar()
        policy = Policy(self.con)
        for acao in ACOES:
            with self.subTest(acao=acao):
                self.assertEqual(policy.allowed(SESSAO, acao, resource_project(P)), acao in ("read", "write", "use"))

    def test_sessao_nega_foundation_common_outro_projeto_e_casos(self):
        self.travar()
        policy = Policy(self.con)
        negados = ["foundation", "common", resource_project(OUTRO), resource_case(P, "caso-fic-001"),
                   resource_case(OUTRO, "caso-fic-001"), "project:", "outra-coisa"]
        for recurso in negados:
            for acao in ACOES:
                with self.subTest(recurso=recurso, acao=acao):
                    self.assertFalse(policy.allowed(SESSAO, acao, recurso))

    def test_sessao_sem_trava_ou_com_trava_de_outro_projeto_tudo_negado_mesmo_com_acl(self):
        self.policy.register_principal(self.admin, SESSAO)  # alguém registrou e concedeu por engano
        self.policy.grant(self.admin, SESSAO, resource_project(P), "read")
        self.policy.grant(self.admin, SESSAO, "foundation", "admin")
        for trava in (None, OUTRO, "Valor Invalido", "../x"):
            with self.subTest(trava=trava):
                self.travar(trava)
                policy = Policy(self.con)
                for recurso in (resource_project(P), "foundation", resource_project(OUTRO), "common"):
                    for acao in ACOES:
                        self.assertFalse(policy.allowed(SESSAO, acao, recurso), (recurso, acao))
                with self.assertRaises(AccessDenied):
                    principal_from_env(self.con)

    def test_identidade_de_sessao_vem_da_trava_sem_linha_no_banco(self):
        self.travar()
        me = principal_from_env(self.con)
        self.assertEqual((me.principal_id, me.source), (SESSAO, "trava-de-projeto"))
        self.assertIsNone(self.con.execute("SELECT 1 FROM principal WHERE principal_id = ?", (SESSAO,)).fetchone())
        self.assertIsNone(self.con.execute("SELECT 1 FROM acl WHERE subject = ?", (SESSAO,)).fetchone())
        self.assertEqual(self.con.execute("PRAGMA user_version").fetchone()[0], 5)

    def test_teto_vale_para_o_titular_travado(self):
        self.travar(quem="operador-lab")
        policy = Policy(self.con)
        self.assertTrue(policy.allowed("operador-lab", "write", resource_project(P)))  # pelas concessões dele
        for recurso, acao in (("foundation", "admin"), ("foundation", "audit"), (resource_project(P), "approve"),
                              (resource_project(P), "audit"), (resource_project(OUTRO), "read"), ("common", "curate")):
            with self.subTest(recurso=recurso, acao=acao):
                self.assertFalse(policy.allowed("operador-lab", acao, recurso))
        self.assertTrue(policy.allowed("operador-juridico", "read", "common"))  # do comum, só a leitura
        self.assertFalse(policy.allowed("operador-juridico", "write", "common"))
        self.assertFalse(policy.allowed("curador-comum", "curate", "common"))

    def test_trava_invalida_nega_ate_o_administrador(self):
        self.travar("Nome Errado", quem="operador-lab")
        self.assertFalse(Policy(self.con).allowed("operador-lab", "admin", "foundation"))
        self.assertFalse(Policy(self.con).allowed("operador-lab", "read", resource_project(P)))

    def test_sem_trava_nada_muda(self):
        policy = Policy(self.con)
        self.assertTrue(policy.allowed("operador-lab", "admin", "foundation"))
        self.assertTrue(policy.allowed("operador-lab", "read", resource_project(OUTRO)))
        self.assertTrue(policy.allowed("curador-comum", "curate", "common"))

    def test_listagem_travada_mostra_so_o_projeto_mesmo_ao_administrador(self):
        self.travar(quem="operador-lab")
        self.assertEqual([p["project_id"] for p in list_projects(self.con, sim("operador-lab"))], [P])
        self.travar()
        self.assertEqual([p["project_id"] for p in list_projects(self.con, sim(SESSAO))], [P])

    def test_administracao_recusada_no_modo_travado(self):
        self.travar(quem="operador-lab")
        with self.assertRaises(AccessDenied):
            Policy(self.con).bootstrap_admin("outro-admin")
        with self.assertRaises(AccessDenied):
            self.policy.grant(self.admin, "operador-juridico", resource_project(OUTRO), "read")
        with self.assertRaises(AccessDenied):
            self.policy.register_principal(self.admin, "nova-identidade")


class TestCliTravada(TravaCase):
    def test_status_mostra_a_trava_a_versao_e_so_o_projeto(self):
        self.travar()
        codigo, st, erro = self.cli("status")
        self.assertEqual(codigo, 0, erro)
        self.assertEqual((st["identidade"], st["projetos_autorizados"], st["projeto_travado"]), (SESSAO, [P], P))
        self.assertEqual(st["eventos_diagnostico_global"], "nao_medido_sem_permissao")
        self.assertIn("kit_version", st)
        self.assertNotIn(OUTRO, json.dumps(st))

    def test_tarefa_do_proprio_projeto_e_negada_no_outro(self):
        alheia = Coordinator(self.root, self.con, self.admin, OUTRO).create_task("tarefa de outro projeto")
        self.travar()
        with self.assertRaises(AccessDenied):  # nem o titular, travado, alcança o outro projeto
            Coordinator(self.root, self.con, self.admin, OUTRO)
        codigo, r, erro = self.cli("tarefa", "criar", "--projeto", P, "--objetivo", "tarefa fictícia")
        self.assertEqual(codigo, 0, erro)
        row = self.con.execute("SELECT created_by FROM task WHERE task_id = ?", (r["task_id"],)).fetchone()
        self.assertEqual(row["created_by"], SESSAO)
        codigo, _r, erro = self.cli("tarefa", "ver", "--projeto", P, "--id", r["task_id"])
        self.assertEqual(codigo, 0, erro)
        for args in (("tarefa", "criar", "--projeto", OUTRO, "--objetivo", "x"),
                     ("tarefa", "ver", "--projeto", OUTRO, "--id", alheia),
                     ("conhecimento", "listar", "--projeto", OUTRO),
                     ("conhecimento", "buscar", "--projeto", OUTRO, "--consulta", "x"),
                     ("memoria", "licao", "consultar", "--projeto", OUTRO, "--gatilho", "x")):
            with self.subTest(args=args[:2]):
                codigo, _r, erro = self.cli(*args)
                self.assertEqual(codigo, 2, erro)
                self.assertEqual(self.erro(erro)["code"], "E_ACCESS_DENIED")
        negativas = events.count(self.con, "access_denied")
        self.assertGreaterEqual(negativas, 5)

    def test_comandos_fora_do_mapa_sao_recusados(self):
        self.travar()
        casos = [("init", "--admin", "x"), ("projeto", "listar"), ("projeto", "criar", "--id", "novo", "--nome", "N",
                                                                      "--finalidade", "F"),
                 ("acl", "registrar", "--principal", "intrusa"), ("componente", "listar"),
                 ("backup", "criar", "--destino", str(self.root / "projects" / P / "outputs" / "copia")),
                 ("rota", "gasto", "--rota", "x"), ("banco", "situacao"),
                 ("copia-assinatura", "preparar", "--projeto", P, "--sha256-manifesto", "a" * 64),
                 ("memoria", "licao", "aprovar", "--memoria", "m", "--hash", "h"),
                 ("memoria", "licao", "retirar", "--memoria", "m", "--motivo", "x"),
                 ("memoria", "licao", "revisar", "--memoria", "m", "--revisao", "1", "--motivo", "x", "--gatilho", "g",
                  "--licao", "l", "--evidencia", "e", "--confianca", "alta")]
        for args in casos:
            with self.subTest(args=args[:2]):
                codigo, _r, erro = self.cli(*args)
                self.assertEqual(codigo, 2, erro)
                self.assertIn("modo travado", self.erro(erro)["message"])
        self.assertIsNone(self.con.execute("SELECT 1 FROM principal WHERE principal_id = 'intrusa'").fetchone())

    def test_raiz_diferente_e_ancora_recusadas(self):
        self.travar()
        outra = self.root.parent / (self.root.name + "-outra")
        outra.mkdir()
        self.addCleanup(shutil.rmtree, outra, True)
        codigo, _r, erro = self.cli("status", raiz=outra)
        self.assertEqual(codigo, 2)
        self.assertIn("raiz do lançador", self.erro(erro)["message"])
        os.environ.pop(auth.ENV_RAIZ)
        self.assertEqual(self.cli("status")[0], 2)  # sem a raiz do lançador, nada roda travado
        os.environ[auth.ENV_RAIZ] = str(self.root)
        for args in (("decisao", "conferir-ancora", "--ancora", str(self.root / "a")),
                     ("tarefa", "concluir", "--decisao", str(self.root / "projects" / P / "decisoes" / "d.json"),
                      "--ancora", str(self.root / "a"))):
            with self.subTest(args=args[:2]):
                codigo, _r, erro = self.cli(*args)
                self.assertEqual(codigo, 2)
                self.assertIn("--ancora", self.erro(erro)["message"])

    def test_caminho_de_argumento_fora_do_projeto_recusado(self):
        self.travar()
        fora = self.root / "projects" / OUTRO / "decisoes" / "d.json"
        for args in (("decisao", "verificar", "--arquivo", str(fora)),
                     ("tarefa", "concluir", "--decisao", str(self.root / "state" / "x.json"))):
            with self.subTest(args=args[:2]):
                codigo, _r, erro = self.cli(*args)
                self.assertEqual(codigo, 2)
                self.assertEqual(self.erro(erro)["code"], "E_PATH_ESCAPE")
        # `eventos` saiu do mapa na 1.7.10 (emenda E2): recusado antes do caminho, sem gravar nada
        codigo, _r, erro = self.cli("eventos", "exportar", "--destino", str(self.root / "evidence" / "e.jsonl"))
        self.assertEqual(codigo, 2)
        self.assertIn("modo travado", self.erro(erro)["message"])
        self.assertFalse((self.root / "evidence" / "e.jsonl").exists())

    def test_eventos_e_historico_fora_do_mapa_na_1710(self):
        """Emenda E2 dos contratos: leitura que pode mostrar o que não é do projeto sai do mapa do modo travado (volta
        na 1.7.11 só com leitura restrita ao projeto), mesmo com o caminho dentro do projeto."""
        self.assertNotIn("eventos", auth.COMANDOS_DA_TRAVA)
        self.assertNotIn("historico", auth.COMANDOS_DA_TRAVA["memoria"])
        self.travar()
        codigo, r, erro = self.cli("memoria", "licao", "propor", "--projeto", P, "--op-id", "op-e2", "--gatilho",
                                   "quando houver prazo fictício", "--licao", "conferir o prazo fictício",
                                   "--evidencia", "outputs/nota.md", "--confianca", "media")
        self.assertEqual(codigo, 0, erro)
        destino = self.root / "projects" / P / "outputs" / "e.jsonl"
        for args in (("eventos", "verificar"), ("eventos", "exportar", "--destino", str(destino)),
                     ("memoria", "licao", "historico", "--memoria", r["memory_id"])):
            with self.subTest(args=args[:2]):
                codigo, _r, erro = self.cli(*args)
                self.assertEqual(codigo, 2)
                self.assertEqual(self.erro(erro)["code"], "E_ACCESS_DENIED")
                self.assertIn("modo travado", self.erro(erro)["message"])
        self.assertFalse(destino.exists())

    def test_auditoria_e_historico_negados_a_sessao(self):
        self.travar()
        for args in (("eventos", "verificar"),
                     ("eventos", "exportar", "--destino", str(self.root / "projects" / P / "outputs" / "e.jsonl"))):
            with self.subTest(args=args):
                codigo, _r, erro = self.cli(*args)
                self.assertEqual(codigo, 2)
                self.assertEqual(self.erro(erro)["code"], "E_ACCESS_DENIED")
        codigo, r, erro = self.cli("memoria", "licao", "propor", "--projeto", P, "--op-id", "op-1", "--gatilho",
                                   "quando houver prazo fictício", "--licao", "conferir o prazo fictício",
                                   "--evidencia", "outputs/nota.md", "--confianca", "media")
        self.assertEqual(codigo, 0, erro)
        codigo, _r, erro = self.cli("memoria", "licao", "historico", "--memoria", r["memory_id"])
        self.assertEqual(codigo, 2)
        self.assertEqual(self.erro(erro)["code"], "E_ACCESS_DENIED")
        codigo, pend, erro = self.cli("memoria", "licao", "pendente", "--memoria", r["memory_id"])
        self.assertEqual(codigo, 0, erro)
        self.assertIn("hash", pend)

    def test_sessao_sem_trava_na_cli_tudo_negado(self):
        self.travar(None)
        codigo, _r, erro = self.cli("status")
        self.assertEqual(codigo, 2)
        self.assertEqual(self.erro(erro)["code"], "E_ACCESS_DENIED")


class TestDecisaoDaSessao(TravaCase):
    """preparar → titular assina → registrar → concluir, com a identidade `sessao-<p>` (assinante da configuração)."""

    def setUp(self):
        super().setUp()
        from apoio_decisoes import Chaves
        self.base_chaves = self.root.parent / (self.root.name + "-chaves")
        self.addCleanup(shutil.rmtree, self.base_chaves, True)
        self.chaves = Chaves(self.base_chaves, principal="operador-lab")
        padrao = mock.patch.object(decisoes, "ANCORAS_PADRAO", (str(self.chaves.ancora),))
        padrao.start()
        self.addCleanup(padrao.stop)
        self.pasta = self.root / "projects" / P
        (self.pasta / "outputs" / "entrega.md").write_text("Entrega de ensaio (fictícia).\n", encoding="utf-8")

    def preparar(self, tarefa: str) -> tuple[int, dict | None, str]:
        return self.cli("decisao", "preparar", "--projeto", P, "--tarefa", tarefa, "--entrega", "outputs/entrega.md",
                        "--tipo", "aceite", "--motivo", "Aceito a entrega de ensaio.")

    def test_ciclo_completo_com_a_sessao_e_o_assinante_da_configuracao(self):
        self.travar(assinante="operador-lab")
        codigo, r, erro = self.cli("tarefa", "criar", "--projeto", P, "--objetivo", "entrega de ensaio")
        self.assertEqual(codigo, 0, erro)
        tarefa = r["task_id"]
        codigo, r, erro = self.preparar(tarefa)
        self.assertEqual(codigo, 0, erro)
        arq = Path(r["decisao"])
        self.assertEqual(json.loads(arq.read_text(encoding="utf-8"))["assinante"], "operador-lab")
        self.assertNotIn("avisos", r)
        self.assertIn("-I operador-lab", r["para_o_titular"]["conferir"])
        self.chaves.assinar(arq)  # o titular assina no terminal dele
        codigo, r, erro = self.cli("decisao", "registrar", "--arquivo", str(arq))
        self.assertEqual(codigo, 0, erro)
        self.assertEqual((r["valida"], r["registro"], r["linha"]["registrado_por"]), (True, "registrada agora", SESSAO))
        codigo, r, erro = self.cli("tarefa", "concluir", "--decisao", str(arq))
        self.assertEqual(codigo, 0, erro)
        self.assertTrue(r["concluida"], r)
        self.assertEqual(Coordinator(self.root, self.con, self.admin, P).get_task(tarefa)["state"], "succeeded")

    def test_sem_assinante_configurado_a_decisao_nao_vale(self):
        self.travar()
        tarefa = Coordinator(self.root, self.con, self.admin, P).create_task("entrega de ensaio")
        codigo, r, erro = self.preparar(tarefa)
        self.assertEqual(codigo, 0, erro)
        arq = Path(r["decisao"])
        self.assertEqual(json.loads(arq.read_text(encoding="utf-8"))["assinante"], SESSAO)
        self.assertTrue(any("não está na âncora" in a for a in r["avisos"]))
        self.chaves.assinar(arq)
        codigo, r, _erro = self.cli("decisao", "registrar", "--arquivo", str(arq))
        self.assertEqual((codigo, r["valida"]), (3, False))

    def test_assinante_da_configuracao_precisa_ser_identidade_registrada(self):
        tarefa = Coordinator(self.root, self.con, self.admin, P).create_task("entrega de ensaio")
        for nome in ("nao-registrado", "sessao-" + OUTRO):
            with self.subTest(assinante=nome):
                self.travar(assinante=nome)
                codigo, _r, erro = self.preparar(tarefa)
                self.assertEqual(codigo, 2)
                self.assertEqual(self.erro(erro)["code"], "E_ACCESS_DENIED")
        self.assertFalse((self.pasta / "decisoes").exists() and any((self.pasta / "decisoes").glob("*.json")))

    def test_assinante_da_configuracao_so_vale_na_sessao_travada(self):
        os.environ[auth.ENV_ASSINANTE] = "operador-lab"
        os.environ[ENV_PRINCIPAL] = "operador-juridico"  # sem trava: a identidade de sempre assina
        tarefa = Coordinator(self.root, self.con, self.admin, P).create_task("entrega de ensaio")
        codigo, r, erro = self.preparar(tarefa)
        self.assertEqual(codigo, 0, erro)
        self.assertEqual(json.loads(Path(r["decisao"]).read_text(encoding="utf-8"))["assinante"], "operador-juridico")


class TestServidorMcpNaSessaoTravada(TravaCase):
    """Correção do lote 2 (orientação do coordenador): o servidor MCP do kit abriria o banco direto, por fora da fila e
    do mapa do porteiro; na sessão travada ele não inicia, e a sessão usa `python -m fundacao ...` (o porteiro)."""

    def setUp(self):
        super().setUp()
        for nome in (porteiro_cliente.ENV_FILA, porteiro_cliente.ENV_SERVIDOR):
            os.environ.pop(nome, None)

    def iniciar(self) -> tuple[int, str, mock.MagicMock]:
        erro = io.StringIO()
        with redirect_stderr(erro), mock.patch.object(mcp_servidor, "criar_servidor") as criar:
            codigo = mcp_servidor.main(["--raiz", str(self.root)])  # o servidor de ensaio não lê a entrada padrão
        return codigo, erro.getvalue(), criar

    def test_nao_inicia_com_o_cliente_do_porteiro_nem_com_a_trava(self):
        casos = {"cliente do porteiro": {porteiro_cliente.ENV_FILA: str(self.root / "projects" / P / ".porteiro")},
                 "trava de projeto": {auth.ENV_TRAVA: P}, "trava com valor errado": {auth.ENV_TRAVA: "Valor Errado"}}
        for nome, ambiente in casos.items():
            with self.subTest(caso=nome), mock.patch.dict(os.environ, ambiente):
                codigo, erro, criar = self.iniciar()
                self.assertEqual(codigo, 3, erro)
                saida = json.loads(erro)
                self.assertEqual(saida["estado"], "bloqueado")
                self.assertIn("porteiro", saida["motivo"])
                criar.assert_not_called()
                with self.assertRaises(AccessDenied):  # nem montado no próprio processo
                    mcp_servidor.criar_servidor(self.root)

    def test_fora_da_sessao_travada_inicia_como_antes(self):
        codigo, erro, criar = self.iniciar()
        self.assertEqual(codigo, 0, erro)
        criar.assert_called_once()
        with mock.patch.dict(os.environ, {porteiro_cliente.ENV_FILA: "/tmp/fila", porteiro_cliente.ENV_SERVIDOR: "1"}):
            self.assertIsNone(mcp_servidor.bloqueio_da_sessao())  # dentro do porteiro, sem trava: só a trava conta


if __name__ == "__main__":
    import unittest
    unittest.main()
