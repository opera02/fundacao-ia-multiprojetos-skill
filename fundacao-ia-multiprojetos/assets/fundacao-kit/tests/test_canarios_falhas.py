"""Canários nos caminhos de falha (proposta 9 da análise do vibe-coding-toolkit, 21/10/2026).

Os canários fictícios já provavam memória, conhecimento, MCP e eventos, mas não os caminhos de erro: o
coordenador gravava `str(erro)[:300]` da exceção de uma etapa em `step.error`, e truncar não é redigir — um
trecho de caso dentro da mensagem iria para o banco e para os backups. Agora a falha que vem da etapa (texto
escrito por quem implementa a etapa, que pode conter dado) é gravada só como tipo, tamanho e SHA-256; as
mensagens do próprio kit continuam legíveis. O diagnóstico do provedor fica só em memória: a tentativa
registrada não o leva.
"""

from __future__ import annotations

import json
import shutil

from helpers import CANARIOS, FoundationTestCase

from fundacao.adapters.base import ProviderRequest, ProviderResult
from fundacao.core import backup, events
from fundacao.core.routing import DEFAULT_POLICY, Router
from fundacao.core.tasks import Budget, Coordinator, PermanentError, StepDef, TransientError

CANARIO = CANARIOS["caso"]


class ProvedorQueFalha:
    route = "api_creditos"

    def __init__(self):
        self.provider_id = "provedor-de-ensaio"

    def call(self, request):
        return ProviderResult(self.provider_id, self.route, "failed", dispatched=False,
                              diagnostic=f"erro do provedor citando {CANARIO} na resposta")


class TestCanariosNasFalhas(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.write_data("juridico-lab", "relato.md", "Fato fictício.")
        self.coord = Coordinator(self.root, self.con, self.jur, "juridico-lab")
        self.extra = []

    def tearDown(self):
        for p in self.extra:
            shutil.rmtree(p, ignore_errors=True)
        super().tearDown()

    def banco(self) -> bytes:
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return b"".join(p.read_bytes() for p in (self.root / "state").glob("state.sqlite*") if p.is_file())

    def falhar(self, erro: Exception) -> tuple[str, dict]:
        task = self.coord.create_task("tarefa fictícia " + type(erro).__name__)
        run = self.coord.start_run(task, "fluxo", "1", [StepDef("etapa", inputs=("relato.md",), max_attempts=1)],
                                   Budget(max_calls=1))

        def etapa(ctx):
            raise erro
        return run, self.coord.run(run, {"etapa": etapa})

    def test_falha_permanente_e_transitoria_gravam_so_tipo_tamanho_e_hash(self):
        for erro in (PermanentError(f"falhou lendo o trecho {CANARIO} do documento"),
                     TransientError(f"tempo esgotado ao enviar {CANARIO}")):
            with self.subTest(tipo=type(erro).__name__):
                run, res = self.falhar(erro)
                self.assertEqual(res["state"], "failed")
                gravado = self.con.execute("SELECT error FROM step WHERE run_id = ?", (run,)).fetchone()[0]
                self.assertNotIn(CANARIO, gravado)
                self.assertIn(type(erro).__name__, gravado)
                self.assertIn("sha256", gravado)
        self.assertFalse(CANARIO.encode("utf-8") in self.banco(), "canário no arquivo do banco")

    def test_mensagem_do_proprio_kit_continua_legivel(self):
        task = self.coord.create_task("entrada que não existe")
        run = self.coord.start_run(task, "fluxo", "1", [StepDef("etapa", inputs=("ausente.md",), max_attempts=1)])
        self.coord.run(run, {"etapa": lambda ctx: "nunca roda"})
        gravado = self.con.execute("SELECT error FROM step WHERE run_id = ?", (run,)).fetchone()[0]
        self.assertIn("entrada ausente: ausente.md", gravado)

    def test_backup_e_exportacao_de_eventos_sem_o_canario(self):
        self.falhar(PermanentError(f"trecho {CANARIO}"))
        copia = self.root.parent / f"{self.root.name}-copia-canario"
        self.extra.append(copia)
        backup.create_backup(self.root, copia, "canario")
        for p in copia.rglob("*"):
            if p.is_file():
                self.assertFalse(CANARIO.encode("utf-8") in p.read_bytes(), "canário em " + p.name)
        exportado = self.root / "evidence" / "eventos-canario.jsonl"
        events.export_jsonl(self.con, exportado)
        self.assertNotIn(CANARIO, exportado.read_text(encoding="utf-8"))

    def test_diagnostico_do_provedor_nao_vai_para_a_trilha(self):
        politica = json.loads(json.dumps(DEFAULT_POLICY))
        politica["routes"]["api_creditos"]["enabled"] = True
        politica["routes"]["simulado"]["enabled"] = False
        politica["task_routes"]["default"] = ["api_creditos"]
        router = Router(self.con, self.jur, politica, {"api_creditos": ProvedorQueFalha()})
        res = router.call("default", ProviderRequest("juridico-lab", "task_1", "run_1", "Responda: PRONTO"))
        self.assertEqual(res["state"], "blocked")
        for (payload,) in self.con.execute("SELECT payload_json FROM event"):
            self.assertNotIn(CANARIO, payload)
        self.assertFalse(CANARIO.encode("utf-8") in self.banco(), "canário no arquivo do banco")
