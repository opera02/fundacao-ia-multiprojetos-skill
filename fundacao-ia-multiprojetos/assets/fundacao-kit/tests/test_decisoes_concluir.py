"""`python -m fundacao tarefa concluir --decisao <arq>`: conclui a tarefa só com o aceite válido sobre a entrega exata.

Achado (c) da RETOMADA da fundação de referência: o kit só tinha `tarefa criar|ver`, e a tarefa ficava `pending`
para sempre. O aceite precisa estar assinado (conforme a política), registrado e ser a decisão mais recente da
tarefa no registro do projeto E na trilha de eventos. A conclusão é uma execução de uma etapa que repete a
conferência; repetir devolve a mesma execução. Chave e âncora de ENSAIO.
"""

from __future__ import annotations

import json
from pathlib import Path

from test_decisoes_cli import DecisoesCliCase

from fundacao.core import decisoes
from fundacao.core.tasks import Coordinator


class TestConcluirTarefa(DecisoesCliCase):
    def decidida(self, tipo="aceite", assinar=True, registrar=True) -> Path:
        arq = self.preparada(tipo)
        if assinar:
            self.chaves.assinar(arq)
        if registrar:
            codigo, r, erro = self.cli("operador-lab", "decisao", "registrar", "--arquivo", str(arq))
            self.assertEqual(codigo, 0, (r, erro))
        return arq

    def concluir(self, arq: Path, quem="operador-lab", *extra):
        return self.cli(quem, "tarefa", "concluir", "--decisao", str(arq), *extra)

    def estado(self) -> str:
        return Coordinator(self.root, self.con, self.admin, "juridico-lab").get_task(self.tarefa)["state"]

    def execucoes(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM run WHERE task_id = ?", (self.tarefa,)).fetchone()[0]

    def recusa(self, arq: Path) -> str:
        codigo, r, erro = self.concluir(arq)
        self.assertEqual(codigo, 3, (r, erro))
        self.assertFalse(r["concluida"])
        self.assertEqual((self.estado(), self.execucoes()), ("pending", 0))
        return r["motivo"]

    def test_aceite_assinado_registrado_e_mais_recente_conclui_e_repetir_devolve_a_mesma_execucao(self):
        arq = self.decidida()
        codigo, r, erro = self.concluir(arq)
        self.assertEqual(codigo, 0, erro)
        self.assertEqual((r["concluida"], r["task_state"], r["run_state"], r["task_id"]),
                         (True, "succeeded", "succeeded", self.tarefa))
        run = self.con.execute("SELECT flow_id, flow_version FROM run WHERE run_id = ?", (r["run_id"],)).fetchone()
        self.assertEqual((run["flow_id"], run["flow_version"]), (decisoes.FLUXO_ACEITE, arq.stem))
        codigo, de_novo, erro = self.concluir(arq)
        self.assertEqual((codigo, de_novo["run_id"], de_novo["concluida"]), (0, r["run_id"], True), erro)
        self.assertEqual(self.execucoes(), 1)

    def test_aceite_sem_assinatura_nao_conclui(self):
        self.assertIn("assinatura ausente", self.recusa(self.decidida(assinar=False, registrar=False)))

    def test_aceite_nao_registrado_nao_conclui(self):
        self.assertIn("registrado", self.recusa(self.decidida(registrar=False)))

    def test_correcao_nao_conclui(self):
        self.assertIn("só um aceite", self.recusa(self.decidida("correcao")))

    def test_aceite_superado_por_decisao_posterior_nao_conclui(self):
        aceite = self.decidida()
        self.decidida("correcao")
        self.assertIn("mais recente", self.recusa(aceite))

    def test_entrega_alterada_depois_do_aceite_nao_conclui(self):
        arq = self.decidida()
        (self.pasta / "outputs" / "entrega.md").write_text("Entrega trocada depois do aceite.\n", encoding="utf-8")
        self.assertIn("entrega ausente ou alterada", self.recusa(arq))

    def test_registro_editado_que_diverge_da_trilha_nao_conclui(self):
        aceite = self.decidida()
        self.decidida("correcao")
        reg = self.pasta / "decisoes" / "registro.jsonl"
        linhas = reg.read_text(encoding="utf-8").splitlines()
        reg.write_text(linhas[0] + "\n", encoding="utf-8")  # alguém apaga a correção do registro do projeto
        self.assertIn("divergem", self.recusa(aceite))

    def test_concluir_exige_escrita_e_a_decisao_do_projeto_informado(self):
        arq = self.decidida()
        codigo, _r, erro = self.concluir(arq, "revisor-juridico")
        self.assertEqual(codigo, 2)
        self.assertIn("E_ACCESS_DENIED", erro)
        codigo, _r, erro = self.concluir(arq, "operador-lab", "--projeto", "reversa-lab")
        self.assertEqual(codigo, 2)
        self.assertIn("outro projeto", erro)
        self.assertEqual((self.estado(), self.execucoes()), ("pending", 0))

    def test_criar_e_ver_continuam_exigindo_o_projeto(self):
        codigo, _r, erro = self.cli("operador-lab", "tarefa", "ver", "--id", self.tarefa)
        self.assertEqual(codigo, 2)
        self.assertIn("--projeto", erro)
        codigo, r, erro = self.cli("operador-lab", "tarefa", "ver", "--projeto", "juridico-lab", "--id", self.tarefa)
        self.assertEqual((codigo, r["state"]), (0, "pending"), erro)


    def test_aceite_escrito_so_no_registro_do_projeto_sem_a_trilha_nao_conclui(self):
        # Revisão independente: o registro fica na pasta do projeto (quem opera o projeto escreve); a trilha, no banco.
        arq = self.decidida(registrar=False)
        v = decisoes.verificar_decisao(arq, self.pasta, self.chaves.ancora)
        linha = {k: v[k] for k in ("decisao_id", "tipo", "task_id", "sha256_decisao", "entrega")}
        (self.pasta / "decisoes" / "registro.jsonl").write_text(json.dumps(linha) + "\n", encoding="utf-8")
        self.assertIn("trilha", self.recusa(arq))

if __name__ == "__main__":
    import unittest
    unittest.main()
