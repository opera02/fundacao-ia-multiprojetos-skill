"""Lições com evidência no produto (1.7.7; método adaptado de Harness², proposta P3).

O relatório final registra, por mudança, o efeito observado e o veredito (ajudou · piorou · sem efeito observado ·
confundido) e no máximo uma lição, ou SEM_ENTRADA; as evidências ganham a linha "Lição"; e a capacidade 04 diz onde
a lição mora (memória `procedimento` do projeto, nunca do caso), que ela é hipótese na tarefa seguinte e que só
sobe para a camada comum pela promoção curada (C7).
"""

from __future__ import annotations

import unittest

from apoio import SKILL
from test_referencias_decisoes import secao

VEREDITOS = ("ajudou", "piorou", "sem efeito observado", "confundido")


def ler(rel: str) -> str:
    return (SKILL / rel).read_text(encoding="utf-8")


def plano(texto: str) -> str:
    return " ".join(texto.split())


class TestRelatorioFinal(unittest.TestCase):
    def test_tabela_de_mudancas_tem_efeito_observado_e_veredito(self):
        s5 = secao(ler("assets/templates/RELATORIO-FINAL.md"), "5. Mudanças realizadas")
        cabecalho = next(l for l in s5.splitlines() if l.startswith("| Arquivo/componente"))
        self.assertEqual([c.strip() for c in cabecalho.strip().strip("|").split("|")],
                         ["Arquivo/componente", "Tipo (código/dados/infra)", "Motivo (onde se viu)",
                          "Efeito observado (onde)", "Veredito", "Reversão"])
        texto = plano(s5)
        for trecho in (*VEREDITOS, '"não observado"', "ser adotada não prova que a mudança ajudou"):
            self.assertIn(trecho, texto)

    def test_secao_5b_pede_uma_licao_ou_sem_entrada(self):
        s5b = plano(secao(ler("assets/templates/RELATORIO-FINAL.md"), "5b. Lição (no máximo uma) ou SEM_ENTRADA"))
        for trecho in ("Gatilho", "sem fato do caso", "Evidência", "Confiança", "no máximo média", "SEM_ENTRADA",
                       "`references/capacidades/04-memoria.md`", "harness2, P3"):
            self.assertIn(trecho, s5b)


class TestEvidencias(unittest.TestCase):
    def test_linha_licao_nas_evidencias(self):
        texto = plano(secao(ler("assets/templates/EVIDENCIAS.md"), "Pendências e continuidade"))
        for trecho in ("Lição (opcional; no máximo uma, ou SEM_ENTRADA)", "gatilho", "evidência", "confiança",
                       "sem fato do caso", "como proposta"):
            self.assertIn(trecho, texto)


class TestCapacidade04Licoes(unittest.TestCase):
    def test_convencao_da_licao(self):
        s = plano(secao(ler("references/capacidades/04-memoria.md"), "Lições: memória de procedimento do projeto"))
        for trecho in ("`procedimento`", "no escopo do **projeto**, nunca no do caso", "gatilho", "evidência",
                       "confiança", "`source_ref`", "Nunca leva fato do caso", "é palpite", "**proposta**",
                       "quem propôs não aprova", "**hipótese** a reconferir", "(C7)",
                       "github.com/google-research/harness2", "commit 1cfe254", "Apache-2.0"):
            self.assertIn(trecho, s)

    def test_licao_vem_antes_da_verificacao_e_nao_some_da_promocao(self):
        texto = ler("references/capacidades/04-memoria.md")
        self.assertLess(texto.index("## Lições: memória de procedimento do projeto"), texto.index("## Verificação"))
        self.assertIn("a IA não aprova a si mesma", plano(secao(texto, "Implementação")))  # item 8 citado acima


if __name__ == "__main__":
    unittest.main()
