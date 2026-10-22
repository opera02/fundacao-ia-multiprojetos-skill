"""Auditoria Codex Security da 1.7.6, #9: pedido de componente e saída de subprocesso sem teto de memória.

Até a 1.7.6, o executor de processos lia stdout e stderr até o fim (`read()`): só o prazo os limitava, e um filho
podia encher a memória da fundação antes dele. O despacho mandava o pedido inteiro, e o `source_manifest` lia cada
arquivo inteiro, sem limite de quantidade nem de tamanho. Agora: tetos por componente (`limits` no registro, padrão
seguro em core/limites.py), leitura em blocos com teto no executor (core/processo.py), que encerra a árvore de
processos ao passar dele, e o `source_manifest` recusa antes de ler (stat) e lê em blocos. Os testes de regressão
falham no kit 1.7.6 (a saída fica no relatório da 1.7.7); os marcados como controle passam antes e depois.
Componentes, "CLIs" e dados são de ensaio; nenhum provedor é chamado.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import tempfile
import time
import tracemalloc
import unittest
from pathlib import Path
from unittest import mock

from helpers import FoundationTestCase
from test_auditoria_1_5_0_execucao import processo_terminou

from fundacao.adapters import cli
from fundacao.adapters.base import ProviderResult
from fundacao.components import source_manifest
from fundacao.core import components
from fundacao.core.contracts import FundacaoError, ValidationError

MIB = 1024 * 1024
# Filho que cria um neto (marca se sobreviver), escreve muito num fluxo e depois espera: só o teto o para cedo.
_VERBOSO = """\
import pathlib, subprocess, sys, time
neto = subprocess.Popen([sys.executable, "-c", "import pathlib, sys, time; time.sleep(20); "
                         "pathlib.Path(sys.argv[1]).write_text('vivo')", {marca!r}],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
pathlib.Path({pidfile!r}).write_text(str(neto.pid))
fluxo = sys.{fluxo}.buffer
for _ in range({blocos}):
    fluxo.write(b"x" * 65536)
fluxo.flush()
time.sleep(60)
"""


class _ComNeto:
    def neto_encerrado(self, pidfile: Path, marca: Path) -> None:
        self.assertTrue(pidfile.exists(), "o filho não chegou a criar o neto (carga da máquina?)")
        self.assertTrue(processo_terminou(int(pidfile.read_text()), 5), "o neto sobreviveu ao estouro do teto")
        self.assertFalse(marca.exists())


class TestTetoNoDespachoDeComponentes(FoundationTestCase, _ComNeto):
    def registrar(self, component_id: str, codigo: str, **campos) -> None:
        (self.root / "fundacao" / "components" / f"{component_id}.py").write_text(codigo, encoding="utf-8")
        entrada = {"schema_version": "fundacao.component/1", "component_id": component_id, "version": "0.0.1",
                   "kind": "tool", "enabled": True, "entrypoint": f"fundacao.components.{component_id}:run",
                   "allowed_projects": ["juridico-lab"], "permissions": [], "timeout_seconds": 15, **campos}
        (self.root / "registry" / "components" / f"{component_id}.json").write_text(json.dumps(entrada),
                                                                                    encoding="utf-8")

    def despachar(self, component_id: str, payload=None) -> dict:
        return components.dispatch(self.root, self.con, self.jur, "juridico-lab", component_id, payload or {})

    def verboso(self, component_id: str, fluxo: str, blocos: int, limits: dict) -> tuple[Path, Path]:
        pidfile, marca = self.root / f"{component_id}.pid", self.root / f"{component_id}-NETO-SOBREVIVEU.txt"
        corpo = _VERBOSO.format(marca=str(marca), pidfile=str(pidfile), fluxo=fluxo, blocos=blocos)
        self.registrar(component_id, "def run(request):\n" + "".join(f"    {linha}\n" for linha in corpo.splitlines())
                       + "    return {}\n", limits=limits)
        return pidfile, marca

    def test_stdout_acima_do_teto_encerra_a_arvore_na_hora_com_memoria_limitada(self):
        pidfile, marca = self.verboso("verboso_out", "stdout", 1024, {"stdout_bytes": 1 * MIB})  # 64 MiB
        tracemalloc.start()
        inicio = time.monotonic()
        try:
            with self.assertRaises(FundacaoError) as ctx:
                self.despachar("verboso_out")
        finally:
            pico = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
        duracao = time.monotonic() - inicio
        self.assertEqual(ctx.exception.code, "E_LIMITE_EXCEDIDO", str(ctx.exception))
        self.assertLess(duracao, 8, "a árvore não foi encerrada ao passar do teto (esperou o prazo)")
        self.assertLess(pico, 16 * MIB, "a saída foi guardada além do teto")
        self.neto_encerrado(pidfile, marca)

    def test_stderr_acima_do_teto_encerra_a_arvore_na_hora(self):
        pidfile, marca = self.verboso("verboso_err", "stderr", 64, {"stderr_bytes": 256 * 1024})  # 4 MiB
        inicio = time.monotonic()
        with self.assertRaises(FundacaoError) as ctx:
            self.despachar("verboso_err")
        self.assertEqual(ctx.exception.code, "E_LIMITE_EXCEDIDO", str(ctx.exception))
        self.assertLess(time.monotonic() - inicio, 8)
        self.neto_encerrado(pidfile, marca)

    def test_pedido_acima_do_teto_nem_inicia_o_componente(self):
        marca = self.root / "COMPONENTE-INICIADO.txt"
        self.registrar("marcador", f"import pathlib\ndef run(request):\n    pathlib.Path({str(marca)!r}).write_text('x')\n"
                                   "    return {}\n")
        with self.assertRaises(FundacaoError) as ctx:
            self.despachar("marcador", {"dados": "x" * (2 * MIB)})  # acima do padrão (1 MiB)
        self.assertEqual(ctx.exception.code, "E_LIMITE_EXCEDIDO", str(ctx.exception))
        self.assertFalse(marca.exists(), "o componente foi iniciado com o pedido acima do teto")
        self.assertEqual(components.dispatch_count(self.con, "marcador", "executed"), 0)
        self.despachar("marcador", {"dados": "x" * 1000})  # controle: dentro do teto, roda
        self.assertTrue(marca.exists())

    def test_teto_do_registro_com_nome_ou_valor_invalido_e_recusado(self):
        for limits in ({"stdout_bites": 10}, {"stdout_bytes": 0}, {"stdout_bytes": True}, ["stdout_bytes"]):
            with self.subTest(limits=limits):
                self.registrar("teto_errado", "def run(request):\n    return {}\n", limits=limits)
                inventario = {c["component_id"]: c for c in components.discover(self.root)}
                self.assertEqual(inventario["teto_errado"]["health"], "registro_invalido")
                with self.assertRaises(ValidationError):
                    self.despachar("teto_errado")

    def test_despacho_passa_os_tetos_do_registro_ao_source_manifest(self):
        reg = self.root / "registry" / "components" / "source_manifest.json"
        entrada = json.loads(reg.read_text(encoding="utf-8"))
        entrada.update(allowed_projects=["juridico-lab"], limits={"max_files": 1})
        reg.write_text(json.dumps(entrada), encoding="utf-8")
        components.set_enabled(self.root, self.con, self.admin, "source_manifest", True)
        self.write_data("juridico-lab", "docs/a.md", "a")
        self.write_data("juridico-lab", "catalog.json", json.dumps({"doc-a": "docs/a.md", "doc-b": "docs/a.md"}))
        res = self.despachar("source_manifest", {"document_ids": ["doc-a", "doc-b"]})["result"]
        self.assertEqual(res["files"], [])
        self.assertEqual([e["error"] for e in res["errors"]], ["E_TOO_MANY_DOCUMENTS"])

    def test_resultado_dentro_do_teto_continua_igual(self):  # controle
        self.registrar("normal", "def run(request):\n    return {'ok': True, 'texto': 'ação nº 1'}\n")
        self.assertEqual(self.despachar("normal")["result"], {"ok": True, "texto": "ação nº 1"})


class TestTetoNaSaidaDoProvedor(unittest.TestCase, _ComNeto):
    """O mesmo executor nas rotas por CLI: "CLI" de ensaio em Python pelo `_rodar` de verdade."""

    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp(prefix="fundacao-cli-teto-"))

    def tearDown(self):
        shutil.rmtree(self.pasta, ignore_errors=True)

    def test_saida_acima_do_teto_encerra_a_cli_e_conta_a_chamada(self):
        pidfile, marca = self.pasta / "neto.pid", self.pasta / "NETO-SOBREVIVEU.txt"
        falsa = self.pasta / "cli_verbosa.py"
        falsa.write_text(_VERBOSO.format(marca=str(marca), pidfile=str(pidfile), fluxo="stdout", blocos=640),  # 40 MiB
                         encoding="utf-8")
        inicio = time.monotonic()
        res = cli._rodar("ensaio", "cli_assinatura", [sys.executable, str(falsa)], "x", 12, ())
        duracao = time.monotonic() - inicio
        self.assertIsInstance(res, ProviderResult, "a saída acima do teto voltou como resposta")
        self.assertEqual((res.state, res.dispatched), ("invalid_output", True), res.diagnostic)
        self.assertLess(duracao, 8, "a CLI não foi encerrada ao passar do teto (esperou o prazo)")
        self.neto_encerrado(pidfile, marca)


class TestSourceManifestComTetos(FoundationTestCase):
    """O componente distribuído recusa ANTES de ler e lê em blocos (chamado no próprio processo, com o pedido do
    despacho)."""

    def setUp(self):
        super().setUp()
        self.pasta = self.root / "projects" / "juridico-lab"
        self.write_data("juridico-lab", "docs/a.md", "a" * 4096)
        self.write_data("juridico-lab", "docs/b.md", "b" * 4096)
        self.write_data("juridico-lab", "catalog.json", json.dumps({"doc-a": "docs/a.md", "doc-b": "docs/b.md"}))

    def rodar(self, ids: list, limits: dict | None = None) -> tuple[dict, list[str]]:
        abertos, abrir = [], io.open

        def espiao(arquivo, *args, **kwargs):
            abertos.append(Path(arquivo).name if not isinstance(arquivo, int) else str(arquivo))
            return abrir(arquivo, *args, **kwargs)

        pedido = {"project_id": "juridico-lab", "project_dir": str(self.pasta), "payload": {"document_ids": ids}}
        if limits is not None:
            pedido["limits"] = limits
        with mock.patch("io.open", espiao), mock.patch("builtins.open", espiao):
            return source_manifest.run(pedido), abertos

    def test_ids_demais_sao_recusados_antes_de_ler(self):
        res, abertos = self.rodar(["doc-a", "doc-b", "doc-a"], {"max_files": 2})
        self.assertEqual(res["files"], [])
        self.assertEqual([e["error"] for e in res["errors"]], ["E_TOO_MANY_DOCUMENTS"])
        self.assertFalse({"a.md", "b.md"} & set(abertos), "leu documento de um pedido recusado")

    def test_id_repetido_e_lido_uma_vez(self):
        res, abertos = self.rodar(["doc-a", "doc-a"])
        self.assertEqual([f["document_id"] for f in res["files"]], ["doc-a"])
        self.assertEqual(res["errors"], [{"document_id": "doc-a", "error": "E_DUPLICATE"}])
        self.assertEqual(abertos.count("a.md"), 1)

    def test_arquivo_acima_do_teto_e_recusado_sem_ler(self):
        res, abertos = self.rodar(["doc-a"], {"file_bytes": 1024})
        self.assertEqual(res["files"], [])
        self.assertEqual([(e["document_id"], e["error"]) for e in res["errors"]], [("doc-a", "E_TOO_LARGE")])
        self.assertNotIn("a.md", abertos, "abriu o arquivo acima do teto")

    def test_teto_somado_dos_arquivos(self):
        res, abertos = self.rodar(["doc-a", "doc-b"], {"total_file_bytes": 6000})
        self.assertEqual([f["document_id"] for f in res["files"]], ["doc-a"])
        self.assertEqual([(e["document_id"], e["error"]) for e in res["errors"]], [("doc-b", "E_TOTAL_LIMIT")])
        self.assertNotIn("b.md", abertos)

    def test_catalogo_acima_do_teto_e_recusado(self):
        with mock.patch.object(source_manifest, "LIMITE_CATALOGO", 16, create=True):
            res, _ = self.rodar(["doc-a"])
        self.assertEqual(res["files"], [])
        self.assertEqual([(e["document_id"], e["error"]) for e in res["errors"]], [(None, "E_TOO_LARGE")])

    def test_dentro_dos_tetos_o_manifesto_continua_igual(self):  # controle
        res, _ = self.rodar(["doc-a", "doc-b"])
        self.assertEqual([(f["document_id"], f["path"], f["size"]) for f in res["files"]],
                         [("doc-a", "docs/a.md", 4096), ("doc-b", "docs/b.md", 4096)])
        self.assertEqual([f["sha256"] for f in res["files"]],
                         [hashlib.sha256(b"a" * 4096).hexdigest(), hashlib.sha256(b"b" * 4096).hexdigest()])
        self.assertEqual(res["errors"], [])


if __name__ == "__main__":
    unittest.main()
