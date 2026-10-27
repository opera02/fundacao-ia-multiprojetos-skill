"""Ambiente descartável para os testes de conformidade.

Cada teste cria uma raiz temporária com cópia do pacote, do registro e do
modelo, um banco novo e identidades de ENSAIO (simuladas). Isso testa a lógica
da política; o isolamento real exige contas/permissões do sistema operacional.
"""

from __future__ import annotations

import gc
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
# Mesmos artefatos operacionais de scripts/codigo_conferido.py: não são configuração de teste.
FORA_DO_REGISTRY = frozenset({"kit_backup", "kit_preparo", "kit_install.json", "atualizacoes.jsonl",
                              "inventario-host.json"})
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))

from fundacao.core.auth import Policy, Principal, resource_case, resource_project  # noqa: E402
from fundacao.core.backup import ensure_tombstone_log  # noqa: E402
from fundacao.core.db import connect  # noqa: E402
from fundacao.core.projects import create_project  # noqa: E402

CANARIOS = {
    "juridico-lab": "JUR-SEGREDO-FIC",
    "reversa-lab": "ENG-SEGREDO-FIC",
    "caso": "CASO-SEGREDO-FIC",
}


def sim(principal_id: str) -> Principal:
    return Principal(principal_id, "teste-simulado")


class FoundationTestCase(unittest.TestCase):
    """Cria raiz descartável com dois projetos e identidades de ensaio."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="fundacao-teste-"))
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
        def ignore_registry(pasta, nomes):
            fora = FORA_DO_REGISTRY.intersection(nomes) if Path(pasta) == KIT / "registry" else set()
            return set(ignore(pasta, nomes)) | fora

        shutil.copytree(KIT / "fundacao", self.root / "fundacao", ignore=ignore)
        shutil.copytree(KIT / "registry", self.root / "registry", ignore=ignore_registry)
        shutil.copytree(KIT / "templates", self.root / "templates", ignore=ignore)
        self.con = connect(self.root / "state" / "state.sqlite")
        ensure_tombstone_log(self.root / "state" / "retiradas.jsonl")  # como faz o `init`
        self.policy = Policy(self.con)
        self.admin = self.policy.bootstrap_admin("operador-lab")
        self.admin = sim("operador-lab")
        create_project(self.root, self.con, self.admin, "juridico-lab", "Laboratório jurídico",
                       "Fluxos fictícios de petição, honorários, proposta e contrato")
        create_project(self.root, self.con, self.admin, "reversa-lab", "Laboratório de engenharia reversa",
                       "Estudo do CaixaSim")
        for pid in ("operador-juridico", "operador-engenharia", "curador-comum", "revisor-juridico"):
            self.policy.register_principal(self.admin, pid)
        g = self.policy.grant
        for action in ("read", "write", "use"):
            g(self.admin, "operador-juridico", resource_project("juridico-lab"), action)
            g(self.admin, "operador-engenharia", resource_project("reversa-lab"), action)
        g(self.admin, "operador-juridico", resource_case("juridico-lab", "caso-fic-001"), "read")
        g(self.admin, "operador-juridico", resource_case("juridico-lab", "caso-fic-001"), "write")
        for action in ("read", "approve", "audit"):
            g(self.admin, "revisor-juridico", resource_project("juridico-lab"), action)
        g(self.admin, "revisor-juridico", resource_case("juridico-lab", "caso-fic-001"), "read")
        g(self.admin, "revisor-juridico", resource_case("juridico-lab", "caso-fic-001"), "approve")
        for pid in ("operador-juridico", "operador-engenharia", "curador-comum", "revisor-juridico"):
            g(self.admin, pid, "common", "read")
        g(self.admin, "curador-comum", "common", "curate")
        self.jur = sim("operador-juridico")
        self.eng = sim("operador-engenharia")
        self.curador = sim("curador-comum")
        self.revisor = sim("revisor-juridico")

    def tearDown(self) -> None:
        try:
            self.con.close()
        finally:
            gc.collect()
            shutil.rmtree(self.root, ignore_errors=True)

    def write_data(self, project_id: str, rel: str, text: str) -> Path:
        path = self.root / "projects" / project_id / "data" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path
