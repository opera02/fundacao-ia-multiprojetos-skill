"""Política de rotas validada ao carregar (proposta 4 da análise do vibe-coding-toolkit, 21/10/2026).

A política é o portão de custo e sigilo e é editada à mão (a DECISAO-003 da fundação mudou
`task_routes.sigiloso` assim). Tipo errado nunca vale como outro valor: `"enabled": "false"` em
texto, teto em texto, rota citada que não existe e chave desconhecida recusam a política inteira ao
carregar; o roteador também só liga uma rota com `true` de verdade.
"""

from __future__ import annotations

import copy
import json

from helpers import KIT, FoundationTestCase

from fundacao.adapters.base import ProviderRequest
from fundacao.adapters.simulado import SimulatedProvider
from fundacao.core.contracts import ValidationError
from fundacao.core.routing import DEFAULT_POLICY, Router, load_policy, validar_politica


def politica_da_fundacao() -> dict:
    """Formato da política real da fundação deste PC (titular, teto de chamadas, DECISAO-003)."""
    p = copy.deepcopy(DEFAULT_POLICY)
    p["titular"] = "titular-ensaio"
    p["observacao"] = "texto livre do titular"
    p["routes"]["cli_assinatura"]["max_calls"] = 12
    p["task_routes"]["sigiloso"] = ["cli_assinatura", "local"]
    return p


class TestPoliticaValidaAoCarregar(FoundationTestCase):
    def gravar(self, politica, texto: str | None = None) -> None:
        arq = self.root / "registry" / "route_policy.json"
        arq.write_text(texto if texto is not None else json.dumps(politica, ensure_ascii=False), encoding="utf-8")

    def recusada(self, politica=None, texto: str | None = None) -> str:
        self.gravar(politica, texto)
        with self.assertRaises(ValidationError) as ctx:
            load_policy(self.root)
        return json.dumps(ctx.exception.as_dict(), ensure_ascii=False)

    def test_politicas_distribuidas_e_a_da_fundacao_valem(self):
        distribuida = json.loads((KIT / "registry" / "route_policy.json").read_text(encoding="utf-8"))
        for politica in (DEFAULT_POLICY, distribuida, politica_da_fundacao()):
            self.assertEqual(validar_politica(politica), [])
        self.gravar(politica_da_fundacao())
        self.assertEqual(load_policy(self.root)["routes"]["cli_assinatura"]["max_calls"], 12)

    def test_enabled_em_texto_recusa_a_politica(self):
        p = politica_da_fundacao()
        p["routes"]["api_paga"]["enabled"] = "false"
        erro = self.recusada(p)
        self.assertIn("api_paga", erro)
        self.assertIn("enabled", erro)

    def test_teto_em_texto_negativo_booleano_ou_nan_recusa(self):
        for chave, valor in (("max_calls", "12"), ("max_calls", True), ("max_calls", -1), ("max_calls", 1.5),
                             ("max_usd", "5"), ("max_usd", -0.01)):
            with self.subTest(chave=chave, valor=valor):
                p = politica_da_fundacao()
                p["routes"]["api_creditos"][chave] = valor
                self.assertIn(chave, self.recusada(p))
        texto = json.dumps(politica_da_fundacao()).replace('"max_usd": null', '"max_usd": NaN', 1)
        self.assertIn("max_usd", self.recusada(texto=texto))

    def test_rota_citada_que_nao_existe_recusa(self):
        p = politica_da_fundacao()
        p["task_routes"]["sigiloso"] = ["locla"]
        self.assertIn("locla", self.recusada(p))

    def test_chave_desconhecida_recusa(self):
        p = politica_da_fundacao()
        p["routes"]["simulado"]["enable"] = True  # erro de digitação: a chave certa é enabled
        self.assertIn("enable", self.recusada(p))
        p = politica_da_fundacao()
        p["rotas"] = {}
        self.assertIn("rotas", self.recusada(p))

    def test_ordem_vazia_repetida_ou_que_nao_e_lista_recusa(self):
        for ordem in ([], "local", ["local", "local"], [1]):
            with self.subTest(ordem=ordem):
                p = politica_da_fundacao()
                p["task_routes"]["sigiloso"] = ordem
                self.assertIn("sigiloso", self.recusada(p))

    def test_titular_e_only_titular_com_tipo_errado_recusam(self):
        p = politica_da_fundacao()
        p["titular"] = 123
        self.assertIn("titular", self.recusada(p))
        p = politica_da_fundacao()
        p["routes"]["cli_assinatura"]["only_titular"] = "true"
        self.assertIn("only_titular", self.recusada(p))

    def test_roteador_so_liga_rota_com_true_de_verdade(self):
        """Política montada em memória (sem passar pelo arquivo): o texto "false" não liga a rota."""
        for valor in ("false", "true", 1):
            with self.subTest(enabled=valor):
                p = copy.deepcopy(DEFAULT_POLICY)
                p["routes"]["simulado"]["enabled"] = valor
                router = Router(self.con, self.jur, p, {"simulado": SimulatedProvider("PRONTO")})
                motivos = dict(router.candidate_routes("default"))
                self.assertEqual(motivos["simulado"], "rota desabilitada na política")
        p = copy.deepcopy(DEFAULT_POLICY)
        router = Router(self.con, self.jur, p, {"simulado": SimulatedProvider("PRONTO")})
        self.assertEqual(dict(router.candidate_routes("default"))["simulado"], "ok")
        res = router.call("default", ProviderRequest("juridico-lab", "task_1", "run_1", "Responda: PRONTO"))
        self.assertEqual(res["state"], "succeeded_simulated")
