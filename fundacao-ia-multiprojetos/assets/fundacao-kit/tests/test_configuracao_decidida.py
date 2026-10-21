"""Política local que se afasta da distribuída na rota sigilosa só vale com decisão registrada (análise do
vibe-coding-toolkit, 21/10/2026, proposta 5). Antes, na raiz implantada, o teste da política distribuída era pulado
sempre, e um desvio da rota `sigiloso` passava em silêncio. Agora o desvio precisa do SHA-256 da política em
registry/configuracao-decidida.json, ligado a uma decisão que existe dentro da raiz."""

from __future__ import annotations

import copy
import json

from helpers import FoundationTestCase

from fundacao.core.canon import sha256_file
from fundacao.core.politica_rotas import CONFIGURACAO_DECIDIDA, desvio_sem_decisao
from fundacao.core.routing import DEFAULT_POLICY

DECISAO = "docs/decisoes/DECISAO-009.md"


class TestConfiguracaoDecidida(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.politica = self.root / "registry" / "route_policy.json"
        self.gravar_politica(["cli_assinatura", "local"])

    def gravar_politica(self, sigiloso) -> None:
        p = copy.deepcopy(DEFAULT_POLICY)
        p["task_routes"]["sigiloso"] = sigiloso
        self.politica.write_text(json.dumps(p), encoding="utf-8")

    def registrar(self, sha256: str, decisao: str = DECISAO, criar_decisao: bool = True) -> None:
        if criar_decisao:
            (self.root / DECISAO).parent.mkdir(parents=True, exist_ok=True)
            (self.root / DECISAO).write_text("# DECISAO-009 (fictícia)\n", encoding="utf-8")
        (self.root / "registry" / CONFIGURACAO_DECIDIDA).write_text(json.dumps({
            "schema_version": "fundacao.configuracao_decidida/1",
            "itens": [{"arquivo": "registry/route_policy.json", "sha256": sha256, "decisao": decisao}]}),
            encoding="utf-8")

    def test_desvio_sem_registro_e_problema(self):
        self.assertIn("decisão registrada", desvio_sem_decisao(self.root))

    def test_desvio_com_hash_e_decisao_vale(self):
        self.registrar(sha256_file(self.politica))
        self.assertIsNone(desvio_sem_decisao(self.root))

    def test_politica_mudada_depois_do_registro_e_problema(self):
        self.registrar(sha256_file(self.politica))
        self.gravar_politica(["cli_assinatura", "local", "simulado"])
        self.assertIsNotNone(desvio_sem_decisao(self.root))

    def test_decisao_ausente_ou_fora_da_raiz_nao_conta(self):
        h = sha256_file(self.politica)
        for decisao, criar in ((DECISAO, False), ("../fora/DECISAO-009.md", False), (str(self.root / DECISAO), True)):
            with self.subTest(decisao=decisao):
                self.registrar(h, decisao, criar)
                self.assertIsNotNone(desvio_sem_decisao(self.root))

    def test_registro_ilegivel_nao_aprova_nada(self):
        self.registrar(sha256_file(self.politica))
        (self.root / "registry" / CONFIGURACAO_DECIDIDA).write_text("{ilegível", encoding="utf-8")
        self.assertIsNotNone(desvio_sem_decisao(self.root))

    def test_politica_igual_a_distribuida_nao_precisa_de_registro(self):
        self.gravar_politica(DEFAULT_POLICY["task_routes"]["sigiloso"])
        self.assertIsNone(desvio_sem_decisao(self.root))
