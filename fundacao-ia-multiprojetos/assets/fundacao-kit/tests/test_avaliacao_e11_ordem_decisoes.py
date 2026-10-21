"""Avaliação E11 (21/10/2026), achado F-02, e revisão de segurança da 1.7.4 (E11R-04 e E11R-05): ordem das decisões.

Na 1.7.3 valia a última decisão REGISTRADA: com o aceite e a rejeição da mesma entrega assinados, registrar a
rejeição e depois o aceite antigo concluía a tarefa (sonda A da E11). A primeira correção ordenou pela data de preparo,
mas quem prepara a decisão escreve essa data (E11R-04: rejeição datada para trás ou aceite datado para a frente
invertiam a ordem; empate de datas devolvia a vitória ao registro) e conferir e gravar ficavam em transações
separadas (E11R-05). Agora cada decisão cita, no conteúdo assinado, a decisão vigente da tarefa quando foi preparada
(`anterior_sha256`) e só entra na trilha se ela ainda for a vigente, conferido e gravado na mesma transação.
Chave e âncora de ENSAIO.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from test_decisoes_cli import DecisoesCliCase

from fundacao.core import decisoes

T0, T1 = "2026-10-01T09:00:00-0300", "2026-10-01T10:00:00-0300"
CHAINED = "preparada sobre outra decisão vigente"  # inclusive "(nenhuma)": a que não cita outra


class TestOrdemDasDecisoes(DecisoesCliCase):
    def decisao(self, tipo: str, decisao_id: str, anterior: str | None = "", quando: str = T1) -> Path:
        entrega = self.pasta / "outputs" / "entrega.md"
        d = decisoes.montar_decisao(projeto="juridico-lab", tarefa=self.tarefa, entrega_rel="outputs/entrega.md",
                                    entrega_sha256=decisoes.sha256_arquivo(entrega), tipo=tipo,
                                    motivo="Decisão de ensaio.", assinante="operador-lab", decisao_id=decisao_id,
                                    agora=quando, anterior=anterior or "")
        if anterior is None:
            d.pop("anterior_sha256", None)  # formato anterior, sem encadeamento
        arq = self.pasta / "decisoes" / f"{decisao_id}.json"
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_bytes(decisoes.canonico(d))
        self.chaves.assinar(arq)
        return arq

    def registrar(self, arq: Path):
        return self.cli("operador-lab", "decisao", "registrar", "--arquivo", str(arq))

    def registrada(self, arq: Path) -> None:
        codigo, r, erro = self.registrar(arq)
        self.assertEqual(codigo, 0, (r, erro))

    def recusado(self, arq: Path, trecho: str = CHAINED) -> None:
        codigo, r, erro = self.registrar(arq)
        self.assertEqual(codigo, 2, (r, erro))
        self.assertIn(trecho, erro)

    def nao_conclui(self, arq: Path) -> str:
        codigo, r, erro = self.cli("operador-lab", "tarefa", "concluir", "--decisao", str(arq))
        self.assertEqual(codigo, 3, (r, erro))
        self.assertFalse(r["concluida"])
        return r["motivo"]

    def test_aceite_antigo_registrado_depois_da_rejeicao_nao_conclui(self):  # sonda A da E11
        aceite = self.decisao("aceite", "dec-aceite")
        rejeicao = self.decisao("rejeicao", "dec-rejeicao")  # o aceite não estava registrado: as duas citam "nenhuma"
        self.registrada(rejeicao)
        self.recusado(aceite)
        self.nao_conclui(aceite)
        self.assertEqual([linha["tipo"] for linha in self.registro()], ["rejeicao"])

    def test_data_escrita_por_quem_prepara_nao_muda_a_ordem(self):  # E11R-04, sondas F e H
        aceite = self.decisao("aceite", "dec-aceite", quando="2026-10-01T23:59:00-2359")  # disfarçado para a frente
        rejeicao = self.decisao("rejeicao", "dec-rejeicao", quando=T0)  # datada para trás
        self.registrada(rejeicao)
        self.recusado(aceite)
        self.nao_conclui(aceite)

    def test_empate_de_datas_nao_devolve_a_vitoria_ao_registro(self):  # E11R-05, sonda E
        aceite = self.decisao("aceite", "dec-aceite", quando=T1)
        rejeicao = self.decisao("rejeicao", "dec-rejeicao", quando=T1)
        self.registrada(rejeicao)
        self.recusado(aceite)

    def test_na_ordem_natural_a_rejeicao_encadeada_supera_o_aceite(self):  # controle
        aceite = self.decisao("aceite", "dec-aceite")
        self.registrada(aceite)
        rejeicao = self.preparada("rejeicao")  # pela CLI: cita o aceite registrado
        conteudo = json.loads(rejeicao.read_text(encoding="utf-8"))
        self.assertEqual(conteudo["anterior_sha256"], decisoes.sha256_arquivo(aceite))
        self.chaves.assinar(rejeicao)
        self.registrada(rejeicao)
        self.assertIn("mais recente", self.nao_conclui(aceite))
        self.assertEqual(self.registro()[-1]["anterior_sha256"], decisoes.sha256_arquivo(aceite))

    def test_conferir_e_gravar_na_mesma_transacao(self):  # E11R-05, sonda G
        aceite = self.decisao("aceite", "dec-aceite")
        original = decisoes.vigente_na_trilha
        dentro = []

        def espiao(con, *args, **kwargs):
            dentro.append(con.in_transaction)
            return original(con, *args, **kwargs)

        with mock.patch.object(decisoes, "vigente_na_trilha", espiao):
            self.registrada(aceite)
        self.assertIn(True, dentro)  # a conferência da ordem rodou com a transação de escrita aberta

    def test_formato_anterior_sem_encadeamento_so_entra_em_tarefa_sem_decisao(self):
        primeira = self.decisao("aceite", "dec-antiga-1", anterior=None)
        self.registrada(primeira)
        self.recusado(self.decisao("rejeicao", "dec-antiga-2", anterior=None))

    def test_anterior_fora_do_formato_invalida_a_decisao(self):
        arq = self.decisao("aceite", "dec-torta", anterior="nao-e-um-hash")
        v = decisoes.verificar_decisao(arq, self.pasta, self.chaves.ancora)
        self.assertFalse(v["valida"])
        self.assertIn("anterior_sha256", v["motivo"])

    def test_aceite_encadeado_de_antemao_numa_rejeicao_futura_nao_entra(self):  # revisão da 1.7.4, E11R-06, sonda I3
        rejeicao = self.decisao("rejeicao", "dec-rejeicao")  # pronta antes, ainda não apresentada ao titular
        entrega = self.pasta / "outputs" / "entrega.md"
        d = decisoes.montar_decisao(projeto="juridico-lab", tarefa=self.tarefa, entrega_rel="outputs/entrega.md",
                                    entrega_sha256=decisoes.sha256_arquivo(entrega), tipo="aceite",
                                    motivo="Decisão de ensaio.", assinante="operador-lab",
                                    decisao_id="dec-aceite-adiantado", agora=T1,
                                    anterior=decisoes.sha256_arquivo(rejeicao))
        d["anterior_evento"] = "f" * 64  # quem prepara não conhece o evento que ainda vai registrar a rejeição
        arq = self.pasta / "decisoes" / "dec-aceite-adiantado.json"
        arq.write_bytes(decisoes.canonico(d))
        self.chaves.assinar(arq)
        self.recusado(arq)  # antes da rejeição: a vigente é "nenhuma"
        self.registrada(rejeicao)
        self.recusado(arq)  # depois: o evento citado não é o que registrou a rejeição
        self.nao_conclui(arq)
