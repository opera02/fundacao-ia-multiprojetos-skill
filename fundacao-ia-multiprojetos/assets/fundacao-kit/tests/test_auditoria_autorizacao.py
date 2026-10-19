"""Auditoria externa da 1.3.4 — frente 1, fronteiras de autorização (F01–F04).

Cada teste exige o comportamento SEGURO. Na 1.3.4 eles falham por asserção (o registro do
vermelho fica no workspace, em auditoria-externa-1.3.4/execucoes). Identidades, projetos e
marcadores são fictícios; nenhum provedor é chamado.
"""

from __future__ import annotations

import json
import time
import unittest

from apoio_auditoria import chamar_ferramenta_mcp, criar_ligacao_dir, criar_link_arquivo, trocar_pasta_por_ligacao
from helpers import CANARIOS, FoundationTestCase

from fundacao.core import components
from fundacao.core.auth import resource_project
from fundacao.core.canon import sha256_json
from fundacao.core.contracts import AccessDenied, FundacaoError
from fundacao.core.knowledge import KnowledgeService
from fundacao.core.projects import project_root
from fundacao.core.tasks import Budget, Coordinator, NeedsHuman, SimulatedInterrupt, StepDef

MARCA_SONDA = "SONDA-EXECUTADA.txt"


def _entrada(component_id: str, entrypoint: str, *, enabled: bool = True, projetos=("juridico-lab",)) -> dict:
    return {"schema_version": "fundacao.component/1", "component_id": component_id, "version": "0.0.1",
            "kind": "tool", "enabled": enabled, "entrypoint": entrypoint,
            "allowed_projects": list(projetos), "permissions": [], "timeout_seconds": 20}


class TestF01ComponenteForaDoRegistro(FoundationTestCase):
    """F01: o despacho só aceita componente do registro confiável, com ID e código conferidos."""

    def setUp(self):
        super().setUp()
        self.write_data("reversa-lab", "ficticio.txt", CANARIOS["reversa-lab"])
        pasta = self.root / "projects" / "juridico-lab"
        # Arquivos que a própria identidade do projeto consegue gravar depois da configuração.
        (pasta / "sonda.py").write_text(
            "from pathlib import Path\n"
            "def run(request):\n"
            "    proj = Path(request['project_dir'])\n"
            f"    (proj / '{MARCA_SONDA}').write_text('executou', encoding='utf-8')\n"
            "    return {'canario': (proj.parent / 'reversa-lab' / 'data' / 'ficticio.txt').read_text()}\n",
            encoding="utf-8")
        (pasta / "sonda.json").write_text(json.dumps(_entrada("sonda", "projects.juridico-lab.sonda:run")),
                                          encoding="utf-8")
        self.marca = pasta / MARCA_SONDA

    def _sem_efeito(self, component_id: str):
        self.assertFalse(self.marca.exists(), "o código fora do registro foi executado")
        executados = self.con.execute("SELECT COUNT(*) FROM dispatch WHERE outcome = 'executed'").fetchone()[0]
        self.assertEqual(executados, 0, "um despacho executado foi registrado")
        eventos = self.con.execute("SELECT COUNT(*) FROM event WHERE kind = 'component_executed'").fetchone()[0]
        self.assertEqual(eventos, 0)

    def test_f01_travessia_relativa_e_recusada_antes_de_executar(self):
        pedido = "../../projects/juridico-lab/sonda"
        with self.assertRaises(FundacaoError):
            components.dispatch(self.root, self.con, self.jur, "juridico-lab", pedido, {})
        self._sem_efeito(pedido)

    def test_f01_caminho_absoluto_e_recusado(self):
        pedido = str(self.root / "projects" / "juridico-lab" / "sonda")
        with self.assertRaises(FundacaoError):
            components.dispatch(self.root, self.con, self.jur, "juridico-lab", pedido, {})
        self._sem_efeito(pedido)

    def test_f01_id_do_manifesto_diferente_do_pedido_e_recusado(self):
        (self.root / "registry" / "components" / "espelho.json").write_text(json.dumps(
            _entrada("outro-id", "fundacao.components.source_manifest:run")), encoding="utf-8")
        with self.assertRaises(FundacaoError):
            components.dispatch(self.root, self.con, self.jur, "juridico-lab", "espelho", {"document_ids": []})
        self._sem_efeito("espelho")

    def test_f01_ponto_de_entrada_fora_do_codigo_da_fundacao_e_recusado(self):
        # Registro legítimo, mas o código mora na pasta do projeto, que o operador altera depois.
        (self.root / "registry" / "components" / "fora.json").write_text(json.dumps(
            _entrada("fora", "projects.juridico-lab.sonda:run")), encoding="utf-8")
        with self.assertRaises(FundacaoError):
            components.dispatch(self.root, self.con, self.jur, "juridico-lab", "fora", {})
        self._sem_efeito("fora")

    def test_f01_habilitar_por_travessia_e_recusado(self):
        alvo = self.root / "projects" / "juridico-lab" / "sonda.json"
        antes = alvo.read_bytes()
        with self.assertRaises(FundacaoError):
            components.set_enabled(self.root, self.con, self.admin, "../../projects/juridico-lab/sonda", False)
        self.assertEqual(alvo.read_bytes(), antes)

    def test_f01_link_no_registro_para_fora_e_recusado(self):
        criar_link_arquivo(self.root / "registry" / "components" / "ligado.json",
                           self.root / "projects" / "juridico-lab" / "sonda.json")
        with self.assertRaises(FundacaoError):
            components.dispatch(self.root, self.con, self.jur, "juridico-lab", "ligado", {})
        self._sem_efeito("ligado")


class TestF02ExecucaoDeOutroProjeto(FoundationTestCase):
    """F02: decisão e retomada só operam execuções do próprio projeto, sem efeito colateral."""

    def setUp(self):
        super().setUp()
        self.ca = Coordinator(self.root, self.con, self.jur, "juridico-lab")
        self.cb = Coordinator(self.root, self.con, self.eng, "reversa-lab")

    def _foto(self, run: str) -> tuple:
        etapas = [dict(r) for r in self.con.execute(
            "SELECT step_id, state, attempts, executions, input_hash, output_ref, output_hash, error,"
            " lease_until, decision_json FROM step WHERE run_id = ? ORDER BY step_id", (run,))]
        execucao = dict(self.con.execute("SELECT state, calls_used FROM run WHERE run_id = ?", (run,)).fetchone())
        eventos = self.con.execute("SELECT COUNT(*) FROM event WHERE run_id = ?", (run,)).fetchone()[0]
        saidas = sorted(p.relative_to(self.root).as_posix() for p in (self.root / "projects").rglob("*.out"))
        return etapas, execucao, eventos, saidas

    def test_f02_decisao_sobre_execucao_alheia_nao_muda_nada(self):
        task = self.cb.create_task("aprovação fictícia do reversa-lab")
        run = self.cb.start_run(task, "revisao", "1", [StepDef("revisar")])

        def humano(ctx):
            raise NeedsHuman("Aprovar o rascunho fictício?", ["aprovar", "recusar"])

        self.assertEqual(self.cb.run(run, {"revisar": humano})["state"], "waiting_human")
        # Hash calculável a partir da pergunta e das opções, sem leitura protegida.
        h = sha256_json({"question": "Aprovar o rascunho fictício?", "options": ["aprovar", "recusar"]})
        antes = self._foto(run)
        with self.assertRaises(FundacaoError):
            self.ca.decide(run, "revisar", "aprovar", self.revisor, h)
        self.assertEqual(self._foto(run), antes)

    def test_f02_retomada_de_execucao_alheia_nao_muda_etapa(self):
        task = self.cb.create_task("execução interrompida fictícia")
        run = self.cb.start_run(task, "trabalho", "1", [StepDef("trabalhar")])
        with self.assertRaises(SimulatedInterrupt):
            self.cb.run(run, {"trabalhar": lambda c: "saída fictícia"}, interrupt=("trabalhar", "before_commit"),
                        lease_seconds=0.001)
        antes = self._foto(run)
        self.assertEqual(antes[0][0]["state"], "running")
        with self.assertRaises(FundacaoError):
            self.ca.resume(run, {"trabalhar": lambda c: "não pode rodar"}, now=time.time() + 60)
        self.assertEqual(self._foto(run), antes)

    def test_f02_todas_as_operacoes_publicas_recusam_execucao_alheia(self):
        task = self.cb.create_task("execução alheia fictícia")
        run = self.cb.start_run(task, "trabalho", "1", [StepDef("trabalhar")])
        antes = self._foto(run)
        for nome, chamada in (("status", lambda: self.ca.status(run)),
                              ("run", lambda: self.ca.run(run, {"trabalhar": lambda c: "x"})),
                              ("resume", lambda: self.ca.resume(run, {"trabalhar": lambda c: "x"})),
                              ("cancel", lambda: self.ca.cancel(run))):
            with self.subTest(operacao=nome):
                with self.assertRaises(FundacaoError):
                    chamada()
                self.assertEqual(self._foto(run), antes)


class TestF03RevogacaoComCoordenadorVivo(FoundationTestCase):
    """F03: a autorização atual vale em cada operação, não só na construção do coordenador."""

    def _revogar_tudo(self):
        for acao in ("read", "write", "use"):
            self.policy.revoke(self.admin, "operador-juridico", resource_project("juridico-lab"), acao)

    def _saidas(self) -> list[str]:
        return sorted(p.name for p in (self.root / "projects" / "juridico-lab").rglob("*.out"))

    def test_f03_instancia_antiga_nega_como_a_nova(self):
        self.write_data("juridico-lab", "ficticio.txt", "CANARIO-LEITURA-APOS-REVOGACAO")
        ca = Coordinator(self.root, self.con, self.jur, "juridico-lab")
        task = ca.create_task("CANARIO-OBJETIVO-REVOGADO")
        run = ca.start_run(task, "fluxo", "1", [StepDef("ler", inputs=("ficticio.txt",))], Budget(max_calls=2))
        self._revogar_tudo()
        with self.assertRaises(AccessDenied):
            Coordinator(self.root, self.con, self.jur, "juridico-lab")
        lidos: list[str] = []

        def ler(ctx):
            ctx.charge_call("provedor-ficticio-sem-rede")
            lidos.append(ctx.inputs["ficticio.txt"].read_text(encoding="utf-8"))
            return "CANARIO-SAIDA"

        for nome, chamada in (("get_task", lambda: ca.get_task(task)),
                              ("status", lambda: ca.status(run)),
                              ("start_run", lambda: ca.start_run(task, "fluxo-novo", "1", [StepDef("x")])),
                              ("run", lambda: ca.run(run, {"ler": ler})),
                              ("resume", lambda: ca.resume(run, {"ler": ler})),
                              ("create_task", lambda: ca.create_task("outra tarefa fictícia")),
                              ("cancel", lambda: ca.cancel(run))):
            with self.subTest(operacao=nome):
                with self.assertRaises(AccessDenied):
                    chamada()
        self.assertEqual(lidos, [])
        self.assertEqual(self.con.execute("SELECT calls_used FROM run WHERE run_id = ?", (run,)).fetchone()[0], 0)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM run").fetchone()[0], 1)
        self.assertEqual(self.con.execute("SELECT state FROM step WHERE run_id = ?", (run,)).fetchone()[0], "pending")
        self.assertEqual(self._saidas(), [])

    def test_f03_revogacao_durante_a_etapa_nao_debita_nem_grava_e_e_reconciliavel(self):
        ca = Coordinator(self.root, self.con, self.jur, "juridico-lab")
        task = ca.create_task("revogação no meio da execução (fictícia)")
        run = ca.start_run(task, "fluxo", "1", [StepDef("a"), StepDef("b", depends_on=("a",))], Budget(max_calls=3))

        def a_revogada(ctx):
            self.policy.revoke(self.admin, "operador-juridico", resource_project("juridico-lab"), "write")
            ctx.charge_call("provedor-ficticio-sem-rede")
            return "saída de a"

        with self.assertRaises(AccessDenied):
            ca.run(run, {"a": a_revogada, "b": lambda c: "saída de b"})
        estados = {r["step_id"]: r["state"] for r in self.con.execute("SELECT step_id, state FROM step WHERE run_id = ?", (run,))}
        self.assertEqual(estados, {"a": "pending", "b": "pending"})
        self.assertEqual(self.con.execute("SELECT calls_used FROM run WHERE run_id = ?", (run,)).fetchone()[0], 0)
        self.assertEqual(self._saidas(), [])
        # Reconciliável: com a permissão de volta, a retomada conclui sem repetir efeitos.
        self.policy.grant(self.admin, "operador-juridico", resource_project("juridico-lab"), "write")

        def a_normal(ctx):
            ctx.charge_call("provedor-ficticio-sem-rede")
            return "saída de a"

        res = Coordinator(self.root, self.con, self.jur, "juridico-lab").resume(run, {"a": a_normal, "b": lambda c: "b"})
        self.assertEqual(res["state"], "succeeded")
        self.assertEqual(self.con.execute("SELECT calls_used FROM run WHERE run_id = ?", (run,)).fetchone()[0], 1)

    def test_f03_revogacao_antes_de_gravar_descarta_a_saida(self):
        ca = Coordinator(self.root, self.con, self.jur, "juridico-lab")
        task = ca.create_task("revogação antes da gravação (fictícia)")
        run = ca.start_run(task, "fluxo", "1", [StepDef("a")])

        def a(ctx):
            self.policy.revoke(self.admin, "operador-juridico", resource_project("juridico-lab"), "write")
            return "não pode ser gravada"

        with self.assertRaises(AccessDenied):
            ca.run(run, {"a": a})
        self.assertEqual(self.con.execute("SELECT state FROM step WHERE run_id = ?", (run,)).fetchone()[0], "pending")
        self.assertEqual(self._saidas(), [])


class TestF04ContencaoDeArquivos(FoundationTestCase):
    """F04 (núcleo e MCP): o arquivo final e seus ancestrais ficam na pasta do projeto autorizado."""

    def setUp(self):
        super().setUp()
        self.write_data("juridico-lab", "catalog.json", json.dumps({"doc-aurora-01": "docs/a.md"}))
        self.write_data("reversa-lab", "catalog.json", json.dumps({"doc-" + CANARIOS["reversa-lab"].lower(): "x.md",
                                                                   "doc-caixasim": "caixasim.md"}))
        self.write_data("reversa-lab", "caixasim.md", "Especificação " + CANARIOS["reversa-lab"])

    def _dados_jur_apontam_para_reversa(self):
        return trocar_pasta_por_ligacao(self.root / "projects" / "juridico-lab" / "data",
                                        self.root / "projects" / "reversa-lab" / "data")

    def test_f04_catalogo_mcp_por_link_de_arquivo_e_negado(self):
        catalogo = self.root / "projects" / "juridico-lab" / "data" / "catalog.json"
        catalogo.unlink()
        criar_link_arquivo(catalogo, self.root / "projects" / "reversa-lab" / "data" / "catalog.json")
        erro, texto, _modo = chamar_ferramenta_mcp(self.root, "operador-juridico", "listar_documentos",
                                                   {"projeto": "juridico-lab"})
        self.assertTrue(erro, "o catálogo de outro projeto foi entregue pela ligação")
        self.assertNotIn(CANARIOS["reversa-lab"].lower(), texto.lower())

    def test_f04_catalogo_mcp_por_ligacao_da_pasta_de_dados_e_negado(self):
        self._dados_jur_apontam_para_reversa()
        erro, texto, _modo = chamar_ferramenta_mcp(self.root, "operador-juridico", "listar_documentos",
                                                   {"projeto": "juridico-lab"})
        self.assertTrue(erro, "o catálogo de outro projeto foi entregue pela ligação")
        self.assertNotIn(CANARIOS["reversa-lab"].lower(), texto.lower())

    def test_f04_pasta_do_projeto_redirecionada_e_recusada(self):
        trocar_pasta_por_ligacao(self.root / "projects" / "juridico-lab", self.root / "projects" / "reversa-lab")
        with self.assertRaises(FundacaoError):
            project_root(self.root, self.con, self.jur, "juridico-lab")

    def test_f04_entrada_da_etapa_por_ligacao_e_recusada(self):
        self._dados_jur_apontam_para_reversa()
        coord = Coordinator(self.root, self.con, self.jur, "juridico-lab")
        task = coord.create_task("entrada por ligação (fictícia)")
        run = coord.start_run(task, "fluxo", "1", [StepDef("ler", inputs=("caixasim.md",))])
        lidos = []
        try:
            coord.run(run, {"ler": lambda c: lidos.append(c.inputs["caixasim.md"].read_text(encoding="utf-8")) or "ok"})
        except FundacaoError:
            pass
        self.assertEqual(lidos, [], "a etapa leu arquivo de outro projeto pela ligação")
        self.assertNotEqual(self.con.execute("SELECT state FROM step WHERE run_id = ?", (run,)).fetchone()[0],
                            "succeeded")

    def test_f04_saida_da_etapa_nao_e_gravada_por_ligacao(self):
        (self.root / "projects" / "reversa-lab" / "outputs").mkdir(exist_ok=True)
        trocar_pasta_por_ligacao(self.root / "projects" / "juridico-lab" / "outputs",
                                 self.root / "projects" / "reversa-lab" / "outputs")
        coord = Coordinator(self.root, self.con, self.jur, "juridico-lab")
        task = coord.create_task("saída por ligação (fictícia)")
        run = coord.start_run(task, "fluxo", "1", [StepDef("gravar")])
        try:
            coord.run(run, {"gravar": lambda c: "CANARIO-GRAVADO-NO-OUTRO-PROJETO"})
        except Exception:  # noqa: BLE001 — recusar com erro também é seguro; o que importa é não gravar
            pass
        alheios = [p for p in (self.root / "projects" / "reversa-lab" / "outputs").rglob("*") if p.is_file()]
        self.assertEqual(alheios, [], "a saída foi gravada na pasta de outro projeto")

    def test_f04_registro_de_fonte_por_ligacao_e_recusado(self):
        self._dados_jur_apontam_para_reversa()
        with self.assertRaises(FundacaoError):
            KnowledgeService(self.root, self.con, self.jur).register_source(
                "juridico-lab", "juridico-lab/GUIA-LIGADO", 1, "caixasim.md")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM source_version").fetchone()[0], 0)

    def test_f04_componente_de_manifesto_nao_le_por_ligacao(self):
        reg = self.root / "registry" / "components" / "source_manifest.json"
        entrada = json.loads(reg.read_text(encoding="utf-8"))
        entrada.update(enabled=True, allowed_projects=["juridico-lab"])
        reg.write_text(json.dumps(entrada), encoding="utf-8")
        self._dados_jur_apontam_para_reversa()
        try:
            res = components.dispatch(self.root, self.con, self.jur, "juridico-lab", "source_manifest",
                                      {"document_ids": ["doc-caixasim"]})
        except FundacaoError:
            return  # recusado antes de ler: seguro
        self.assertEqual(res["result"]["files"], [], "o manifesto leu arquivo de outro projeto pela ligação")


if __name__ == "__main__":
    unittest.main()
