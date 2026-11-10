"""Ambiente descartável para os testes de conformidade.

Cada teste cria uma raiz temporária com cópia do pacote, do registro e do
modelo, um banco novo e identidades de ENSAIO (simuladas). Isso testa a lógica
da política; o isolamento real exige contas/permissões do sistema operacional.
"""

from __future__ import annotations

import atexit
import functools
import gc
import os
import shutil
import stat
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

KIT = Path(__file__).resolve().parents[1]
# Mesmos artefatos operacionais de scripts/codigo_conferido.py: não são configuração de teste.
FORA_DO_REGISTRY = frozenset({"kit_backup", "kit_preparo", "kit_install.json", "atualizacoes.jsonl",
                              "inventario-host.json", "ultima-copia.json"})
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))

from fundacao.core.auth import Policy, Principal, resource_case, resource_project  # noqa: E402
from fundacao.core import backup, politica_cifra  # noqa: E402
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


_MOLDE: dict = {}


_AQUECIDOS: set = set()


def aquecer(pasta) -> None:
    """Lê 1 byte de cada arquivo comum da pasta que ainda não foi lido, em paralelo. No Windows a primeira leitura de
    um arquivo recém-criado custa ~10 ms (verificação em tempo real do sistema); lida em série pela verificação ou pela
    restauração, a cópia de ~90 arquivos gasta ~1 s; em paralelo, ~0,1 s. Só lê: não muda o que a função chamada depois
    confere."""
    frios = []
    for dono, _dirs, nomes in os.walk(pasta):  # sem seguir ligação
        for nome in nomes:
            caminho = os.path.join(dono, nome)
            try:
                st = os.lstat(caminho)
            except OSError:
                continue
            chave = (caminho, st.st_size, st.st_mtime_ns)
            if stat.S_ISREG(st.st_mode) and chave not in _AQUECIDOS:  # nunca abre FIFO, dispositivo ou ligação
                frios.append(chave)
        if len(frios) > 4000:
            return

    def ler(chave):
        try:
            with open(chave[0], "rb") as f:
                f.read(1)
            _AQUECIDOS.add(chave)
        except OSError:
            pass
    if len(frios) > 8:
        with ThreadPoolExecutor(16) as pool:
            list(pool.map(ler, frios))


def _aquecendo(funcao):
    @functools.wraps(funcao)
    def embrulho(origem, *args, **kwargs):
        try:
            aquecer(origem)
        except (OSError, TypeError, ValueError):
            pass
        return funcao(origem, *args, **kwargs)
    return embrulho


def _copiar_registry(destino: Path) -> None:
    """O registro (configuração: os testes o editam) é sempre cópia própria; sem os artefatos operacionais."""
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")

    def ignore_registry(pasta, nomes):
        fora = FORA_DO_REGISTRY.intersection(nomes) if Path(pasta) == KIT / "registry" else set()
        return set(ignore(pasta, nomes)) | fora

    shutil.copytree(KIT / "registry", destino / "registry", ignore=ignore_registry)


def _copiar_codigo(destino: Path) -> None:
    """Copia o código do kit (fundacao/, templates/) para `destino`, sem caches."""
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(KIT / "fundacao", destino / "fundacao", ignore=ignore)
    shutil.copytree(KIT / "templates", destino / "templates", ignore=ignore)


def _molde() -> dict:
    """Molde do código do kit, feito uma vez por processo (1.7.11, tempo da suíte no Windows): cada raiz de ensaio recebe
    o código por ligação física (os.link) em vez de cópia. No Windows a primeira leitura de um arquivo novo custa ~10 ms
    (verificação em tempo real), por arquivo e por raiz; a ligação não cria arquivo novo, e o molde já foi lido."""
    if not _MOLDE:
        pasta = Path(tempfile.mkdtemp(prefix="fundacao-molde-"))
        atexit.register(shutil.rmtree, pasta, ignore_errors=True)
        _copiar_codigo(pasta)
        arquivos = {}
        for dono, _dirs, nomes in os.walk(pasta):
            for nome in nomes:
                caminho = Path(dono) / nome
                caminho.read_bytes()  # aquece a verificação do sistema, uma vez
                st = caminho.stat()
                arquivos[caminho.relative_to(pasta)] = (st.st_size, st.st_mtime_ns)
        _MOLDE.update(pasta=pasta, arquivos=arquivos)
    return _MOLDE


def _ligar_codigo(destino: Path) -> None:
    molde = _molde()
    for dono, dirs, nomes in os.walk(molde["pasta"]):
        alvo = destino / Path(dono).relative_to(molde["pasta"])
        alvo.mkdir(parents=True, exist_ok=True)
        for nome in nomes:
            try:
                os.link(Path(dono) / nome, alvo / nome)
            except OSError:  # sistema de arquivos sem ligação física: copia
                shutil.copy2(Path(dono) / nome, alvo / nome)


def _conferir_molde() -> list[str]:
    """Os arquivos do molde que um teste alterou no lugar (a ligação física divide o conteúdo com o molde): são
    refeitos a partir do kit e devolvidos, para o teste falhar alto em vez de contaminar os seguintes."""
    molde = _molde()
    alterados = []
    for rel, (tamanho, mtime) in molde["arquivos"].items():
        try:
            st = (molde["pasta"] / rel).stat()
            igual = (st.st_size, st.st_mtime_ns) == (tamanho, mtime)
        except OSError:
            igual = False
        if not igual:
            alterados.append(rel.as_posix())
            (molde["pasta"] / rel).unlink(missing_ok=True)
            shutil.copy2(KIT / rel, molde["pasta"] / rel)
    return alterados


class FoundationTestCase(unittest.TestCase):
    """Cria raiz descartável com dois projetos e identidades de ensaio.

    O código do kit entra na raiz por ligação física com um molde (veja `_molde`): o teste que altera esse código no
    lugar (escrever em fundacao/..., ou um comando que o reescreve) falha no tearDown; ele marca `CODIGO_PROPRIO = True`
    para receber uma cópia só dele. Criar arquivo novo ou trocar o arquivo por outro não precisa disso."""

    CODIGO_PROPRIO = False

    def setUp(self) -> None:
        # 1.7.11: a chave da cópia cifrada é a desta máquina; os testes não a veem (os da cifra instalam a própria).
        patch = mock.patch.object(politica_cifra, "CHAVES_PADRAO", ())
        patch.start()
        self.addCleanup(patch.stop)
        for nome in ("verify_backup", "restore"):  # a cópia lida é aquecida antes (veja `aquecer`)
            aquecendo = mock.patch.object(backup, nome, _aquecendo(getattr(backup, nome)))
            aquecendo.start()
            self.addCleanup(aquecendo.stop)
        self.root = Path(tempfile.mkdtemp(prefix="fundacao-teste-"))
        _copiar_registry(self.root)
        if self.CODIGO_PROPRIO:
            _copiar_codigo(self.root)
        else:
            _ligar_codigo(self.root)
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

    def desvincular(self, caminho: Path) -> None:
        """Troca o arquivo ligado ao molde por uma cópia só desta raiz, antes de alterá-lo no lugar."""
        caminho = Path(caminho)
        dados, st = caminho.read_bytes(), caminho.stat()
        caminho.unlink()
        caminho.write_bytes(dados)
        os.utime(caminho, ns=(st.st_atime_ns, st.st_mtime_ns))

    def tearDown(self) -> None:
        try:
            self.con.close()
        finally:
            gc.collect()
            shutil.rmtree(self.root, ignore_errors=True)
            alterados = [] if self.CODIGO_PROPRIO else _conferir_molde()
            if alterados:
                raise AssertionError(f"o teste alterou no lugar o código compartilhado do molde {alterados[:3]}: "
                                     "marque CODIGO_PROPRIO = True na classe")

    def write_data(self, project_id: str, rel: str, text: str) -> Path:
        path = self.root / "projects" / project_id / "data" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path
