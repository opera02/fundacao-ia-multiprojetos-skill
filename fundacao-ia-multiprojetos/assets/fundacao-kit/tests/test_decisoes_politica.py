"""Política das decisões (`registry/politica-decisoes.json`) e âncora que vale nesta máquina.

A política diz quais tipos de decisão sobre uma entrega exigem assinatura. Onde a âncora padrão existe, ela é o
piso: a política não dispensa assinatura e outra âncora não confere decisões (uma âncora criada por quem opera a
fundação aceitaria uma chave qualquer). Sem a âncora padrão (laboratório), tipo dispensado vale sem assinatura,
como lógica da política. Assinatura inválida nunca é ignorada. Chave e âncora de ENSAIO.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import KIT
from apoio_decisoes import Chaves

from fundacao.core import decisoes


class TestPoliticaDecisoes(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="decisoes-politica-"))
        self.chaves = Chaves(self.tmp)
        self.raiz = self.tmp / "raiz"
        (self.raiz / "registry").mkdir(parents=True)
        self.pasta = self.raiz / "projects" / "p"
        (self.pasta / "outputs").mkdir(parents=True)
        (self.pasta / "decisoes").mkdir()
        self.entrega = self.pasta / "outputs" / "e.md"
        self.entrega.write_text("Entrega de ensaio.\n", encoding="utf-8")
        self.sem_ancora_padrao = mock.patch.object(decisoes, "ANCORAS_PADRAO", (str(self.tmp / "nao-existe"),))
        self.com_ancora_padrao = mock.patch.object(decisoes, "ANCORAS_PADRAO", (str(self.chaves.ancora),))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def politica(self, conteudo) -> None:
        texto = conteudo if isinstance(conteudo, str) else json.dumps(conteudo)
        (self.raiz / "registry" / decisoes.POLITICA).write_text(texto, encoding="utf-8")

    def dispensa(self, *tipos) -> None:
        self.politica({"schema_version": decisoes.SCHEMA_POLITICA,
                       "tipos": {t: {"exige_assinatura": t not in tipos} for t in decisoes.TIPOS}})

    def decisao(self, tipo: str, nome: str = "dec-1"):
        d = decisoes.montar_decisao(projeto="p", tarefa="t", entrega_rel="outputs/e.md",
                                    entrega_sha256=decisoes.sha256_arquivo(self.entrega), tipo=tipo, motivo="Decido.",
                                    assinante="titular-ensaio", decisao_id=nome, agora="2026-10-21T01:00:00-0300")
        arq = self.pasta / "decisoes" / f"{nome}.json"
        arq.write_bytes(decisoes.canonico(d))
        return arq

    def test_politica_distribuida_exige_assinatura_nos_tres_tipos(self):
        if (KIT / "registry" / "kit_install.json").exists():
            self.skipTest("raiz implantada: registry/ é configuração local; a política distribuída é conferida no kit")
        distribuida = json.loads((KIT / "registry" / decisoes.POLITICA).read_text(encoding="utf-8"))
        self.assertEqual(distribuida["schema_version"], decisoes.SCHEMA_POLITICA)
        self.assertEqual({t: r["exige_assinatura"] for t, r in distribuida["tipos"].items()},
                         {t: True for t in decisoes.TIPOS})
        with self.sem_ancora_padrao:
            sem_arquivo = decisoes.carregar_politica(self.raiz)
        self.assertTrue(all(decisoes.exige_assinatura(sem_arquivo, t) for t in decisoes.TIPOS))
        self.assertIsNone(sem_arquivo["sha256"])

    def test_tipo_dispensado_vale_sem_assinatura_so_onde_nao_ha_ancora_padrao(self):
        self.dispensa("correcao")
        with self.sem_ancora_padrao:
            pol = decisoes.carregar_politica(self.raiz)
        self.assertFalse(decisoes.exige_assinatura(pol, "correcao"))
        self.assertIsNotNone(pol["sha256"])
        r = decisoes.verificar_decisao(self.decisao("correcao"), self.pasta, None, pol)
        self.assertEqual((r["valida"], r["forca"]), (True, "sem-assinatura"), r)
        r = decisoes.verificar_decisao(self.decisao("aceite", "dec-2"), self.pasta, None, pol)
        self.assertEqual((r["valida"], r["motivo"]), (False, "assinatura ausente"))

    def test_com_a_ancora_padrao_a_politica_nao_dispensa_assinatura(self):
        self.dispensa(*decisoes.TIPOS)
        with self.com_ancora_padrao:
            pol = decisoes.carregar_politica(self.raiz)
        self.assertTrue(all(decisoes.exige_assinatura(pol, t) for t in decisoes.TIPOS))
        self.assertTrue(any("piso" in a for a in pol["avisos"]), pol["avisos"])
        r = decisoes.verificar_decisao(self.decisao("aceite"), self.pasta, self.chaves.ancora, pol)
        self.assertEqual((r["valida"], r["motivo"]), (False, "assinatura ausente"))

    def test_assinatura_invalida_nunca_e_ignorada(self):
        self.dispensa("rejeicao")
        arq = self.decisao("rejeicao")
        self.chaves.assinar(arq, chave="intruso")
        with self.sem_ancora_padrao:
            pol = decisoes.carregar_politica(self.raiz)
        self.assertFalse(decisoes.verificar_decisao(arq, self.pasta, self.chaves.ancora, pol)["valida"])
        self.assertFalse(decisoes.verificar_decisao(arq, self.pasta, None, pol)["valida"])  # sem âncora para conferir

    def test_politica_invalida_e_recusada(self):
        S = decisoes.SCHEMA_POLITICA
        for ruim in ("{nao e json", {"schema_version": "outra/1", "tipos": {}},
                     {"schema_version": S, "tipos": {"aprovado": {"exige_assinatura": False}}},
                     {"schema_version": S, "tipos": {"aceite": {"exige_assinatura": "nao"}}},
                     {"schema_version": S, "tipos": {"aceite": {"exige_assinatura": True, "outra": 1}}},
                     {"schema_version": S, "tipos": {}, "dispensar_tudo": True}):
            with self.subTest(ruim=ruim), self.sem_ancora_padrao:
                self.politica(ruim)
                with self.assertRaises(decisoes.DecisaoInvalida):
                    decisoes.carregar_politica(self.raiz)

    def test_onde_existe_a_ancora_padrao_outra_ancora_e_recusada(self):
        outra = Chaves(self.tmp / "outra")
        with self.com_ancora_padrao:
            self.assertEqual(decisoes.resolver_ancora(None), self.chaves.ancora)
            self.assertEqual(decisoes.resolver_ancora(self.chaves.ancora), self.chaves.ancora)
            with self.assertRaises(decisoes.DecisaoInvalida):
                decisoes.resolver_ancora(outra.ancora)
        with self.sem_ancora_padrao:
            self.assertEqual(decisoes.resolver_ancora(outra.ancora), outra.ancora)
            self.assertIsNone(decisoes.resolver_ancora(None))

    def test_ancora_padrao_por_sistema(self):
        esperado = ((decisoes.ANCORA_WINDOWS,) if os.name == "nt"
                    else ("/mnt/c/ProgramData/FundacaoIA/confianca/allowed_signers",
                          "/etc/fundacao-ia/confianca/allowed_signers"))
        self.assertEqual(decisoes.ANCORAS_PADRAO, esperado)


if __name__ == "__main__":
    unittest.main()
