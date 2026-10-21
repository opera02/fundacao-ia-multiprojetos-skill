"""Avaliação E11 (21/10/2026), achado F-05: o desvio da rota `sigiloso` valia por existir um arquivo, e a conferência
só rodava na suíte de conformidade.

`configuracao-decidida.json` ligava o SHA-256 da política a uma "decisão" que bastava existir dentro da raiz (um .md
qualquer), e `load_policy`/`Router` aceitavam qualquer ordem válida em `sigiloso`. Agora a decisão citada precisa ser
um aceite VÁLIDO do módulo de decisões (assinado e conferido contra a âncora) cuja entrega é uma cópia exata da
política e que é a decisão VIGENTE da sua tarefa na trilha (registrado e não superado: revisão de segurança da 1.7.4,
E11R-01 e E11R-02), conferido sobre os mesmos bytes que valem (E11R-03); sem ele, ao carregar a política o desvio fica
sem efeito (vale a rota distribuída, só local) e o roteador mostra cada rota ignorada. Chave e âncora de ENSAIO.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest import mock

from test_decisoes_cli import DecisoesCliCase

from fundacao.core import decisoes
from fundacao.core.canon import sha256_file
from fundacao.core.politica_rotas import CONFIGURACAO_DECIDIDA, desvio_sem_decisao
from fundacao.core.routing import DEFAULT_POLICY, Router, load_policy

DESVIO = ["cli_assinatura", "local"]  # como a DECISAO-003 da fundação de referência
IGNORADA = ("cli_assinatura", "desvio da rota sigilosa sem decisão assinada: ignorado")


class TestDesvioDaRotaSigilosa(DecisoesCliCase):
    def setUp(self):
        super().setUp()
        self.politica = self.root / "registry" / "route_policy.json"
        self.gravar_politica(DESVIO)

    def gravar_politica(self, sigiloso) -> None:
        p = copy.deepcopy(DEFAULT_POLICY)
        p["task_routes"]["sigiloso"] = sigiloso
        self.politica.write_text(json.dumps(p), encoding="utf-8")

    def decisao(self, tipo: str = "aceite", assinar: bool = True, entrega: Path | None = None,
                decisao_id: str = "dec-aceite-politica", registrar: bool = True, assinante: str = "operador-lab") -> str:
        if entrega is None:
            entrega = self.pasta / "outputs" / "politica-de-rotas.json"
            entrega.write_bytes(self.politica.read_bytes())
        d = decisoes.montar_decisao(projeto="juridico-lab", tarefa=self.tarefa,
                                    entrega_rel=entrega.relative_to(self.pasta).as_posix(),
                                    entrega_sha256=decisoes.sha256_arquivo(entrega), tipo=tipo,
                                    motivo="Aprovo a rota sigilosa desta política.", assinante=assinante,
                                    decisao_id=decisao_id, agora="2026-10-01T10:00:00-0300")
        arq = self.pasta / "decisoes" / f"{decisao_id}.json"
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_bytes(decisoes.canonico(d))
        if assinar:
            self.chaves.assinar(arq)
        if registrar:  # quem opera registra; a recusa (sem assinatura, fora da ordem) faz parte dos casos negativos
            self.cli("operador-lab", "decisao", "registrar", "--arquivo", str(arq))
        return arq.relative_to(self.root).as_posix()

    def citar(self, decisao: str, sha256: str | None = None) -> None:
        (self.root / "registry" / CONFIGURACAO_DECIDIDA).write_text(json.dumps({
            "schema_version": "fundacao.configuracao_decidida/1",
            "itens": [{"arquivo": "registry/route_policy.json", "sha256": sha256 or sha256_file(self.politica),
                       "decisao": decisao}]}), encoding="utf-8")

    def sem_efeito(self) -> None:
        self.assertIsNotNone(desvio_sem_decisao(self.root))
        self.assertEqual(load_policy(self.root)["task_routes"]["sigiloso"], DEFAULT_POLICY["task_routes"]["sigiloso"])

    def test_arquivo_qualquer_dentro_da_raiz_nao_aprova(self):  # cenário da E11
        md = self.root / "docs" / "decisoes" / "DECISAO-009.md"
        md.parent.mkdir(parents=True)
        md.write_text("# DECISAO-009 (fictícia)\n", encoding="utf-8")
        self.citar("docs/decisoes/DECISAO-009.md")
        self.sem_efeito()

    def test_aceite_assinado_sobre_a_politica_exata_aprova(self):  # controle
        self.citar(self.decisao())
        self.assertIsNone(desvio_sem_decisao(self.root))
        self.assertEqual(load_policy(self.root)["task_routes"]["sigiloso"], DESVIO)

    def test_o_que_nao_e_aceite_assinado_da_politica_nao_aprova(self):
        outra = self.pasta / "outputs" / "outra.md"
        outra.write_text("Outra entrega.\n", encoding="utf-8")
        casos = {"rejeição assinada": lambda: self.decisao("rejeicao"),
                 "aceite sem assinatura": lambda: self.decisao(assinar=False),
                 "aceite de outra entrega": lambda: self.decisao(entrega=outra),
                 "arquivo fora de decisoes/": lambda: "projects/juridico-lab/outputs/outra.md",
                 "caminho que sai da raiz": lambda: "../fora/dec-aceite-politica.json"}
        for nome, citar in casos.items():
            with self.subTest(nome):
                self.citar(citar())
                self.sem_efeito()

    def test_politica_mudada_depois_do_aceite_volta_a_distribuida(self):
        self.citar(self.decisao())
        self.gravar_politica(DESVIO + ["simulado"])
        self.sem_efeito()

    def test_roteador_mostra_a_rota_ignorada(self):
        policy = load_policy(self.root)
        rotas = Router(self.con, self.admin, policy, {}).candidate_routes("sigiloso")
        self.assertEqual(rotas, [("local", "rota desabilitada na política"), IGNORADA])
        self.assertNotIn(IGNORADA, Router(self.con, self.admin, policy, {}).candidate_routes("default"))

    def test_aceite_nao_registrado_nao_aprova(self):  # revisão da 1.7.4, E11R-01 e E11R-02
        self.citar(self.decisao(registrar=False))
        self.sem_efeito()

    def test_rejeicao_registrada_depois_revoga_o_desvio(self):  # E11R-01, sonda A da revisão
        self.citar(self.decisao())
        self.assertEqual(load_policy(self.root)["task_routes"]["sigiloso"], DESVIO)
        rejeicao = self.preparada("rejeicao")  # pela CLI: cita o aceite vigente
        self.chaves.assinar(rejeicao)
        codigo, r, erro = self.cli("operador-lab", "decisao", "registrar", "--arquivo", str(rejeicao))
        self.assertEqual(codigo, 0, (r, erro))
        self.sem_efeito()

    def test_laboratorio_sem_ancora_exige_aceite_registrado_por_quem_aprova(self):  # E11R-02, sonda B
        (self.root / "registry" / "politica-decisoes.json").write_text(json.dumps({
            "schema_version": "fundacao.politica_decisoes/1", "tipos": {"aceite": {"exige_assinatura": False}}}),
            encoding="utf-8")
        with mock.patch.object(decisoes, "ANCORAS_PADRAO", (str(self.root / "sem-ancora" / "allowed_signers"),)):
            self.citar(self.decisao(assinar=False, registrar=False, assinante="operador-juridico"))
            self.sem_efeito()
            self.citar(self.decisao(assinar=False, decisao_id="dec-aceite-lab"))  # registrado por quem aprova
            self.assertIsNone(desvio_sem_decisao(self.root))

    def test_troca_do_arquivo_entre_ler_e_conferir_nao_aplica_desvio(self):  # E11R-03, sondas C e D
        self.citar(self.decisao())  # aceite vigente sobre o DESVIO
        aprovada = self.politica.read_bytes()
        self.gravar_politica(["api_paga", "local"])  # outra política, sem aceite

        def troca(caminho, *args, **kwargs):  # na 1.7.4 de antes, o hash era de uma segunda leitura do arquivo
            self.politica.write_bytes(aprovada)
            return sha256_file(caminho)

        with mock.patch("fundacao.core.politica_rotas.sha256_file", troca, create=True):
            efetiva = load_policy(self.root)["task_routes"]["sigiloso"]
        self.assertEqual(efetiva, DEFAULT_POLICY["task_routes"]["sigiloso"])
