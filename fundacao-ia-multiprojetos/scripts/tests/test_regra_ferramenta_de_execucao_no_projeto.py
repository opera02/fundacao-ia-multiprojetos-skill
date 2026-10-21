"""Avaliação E10, nova execução (skill 1.7.4, 21/10/2026): o executor comparou o legado com o golden pela fundação,
mas com um script temporário da própria sessão, fora do ambiente avaliado; a RETOMADA citou outro arquivo (o módulo do
componente). Quem retomasse não conseguiria repetir a comparação. A regra está agora no fluxo B: a ferramenta de
execução fica no projeto, numa pasta só dela, sem definir identidade, com a pasta inteira registrada por manifesto
citado no relatório do portão 2 (B7); o B8 confere o manifesto e o que ele não vê e roda a ferramenta com -P (-I no
3.10) antes de cada comparação, e para na divergência; o B9 a procura, a reescreve e repete a comparação no escopo
da decisão, citando cada artefato pelo caminho real. As conferências vieram da revisão de segurança da 1.7.6
(R176-01 a R176-05).
"""

from __future__ import annotations

import unittest

from apoio import SKILL
from test_referencias_decisoes import secao


def passo(titulo: str) -> str:
    texto = (SKILL / "references/fluxo-b-adaptar.md").read_text(encoding="utf-8")
    return " ".join(secao(texto, titulo).split())


class TestFerramentaDeExecucaoNoProjeto(unittest.TestCase):
    def test_b7_guarda_a_ferramenta_de_execucao_no_projeto(self):
        b7 = passo("B7 — Mudanças pequenas e verificáveis")
        for termo in ("**ferramenta de execução**", "roda os casos do golden **pela fundação**", "fica **no projeto**",
                      "pasta só dela", "pasta temporária da sessão", "manifesto.py criar", "com `excluidos` 0",
                      "caminho e o SHA-256 do manifesto no relatório do portão 2"):
            self.assertIn(termo, b7, termo)

    def test_b7_ferramenta_nao_define_identidade(self):
        # Revisão de segurança da 1.7.6 (R176-02): sem regra, uma ferramenta persistente podia levar a identidade
        # gravada no arquivo e repeti-la depois, com dados reais, sob o aval do manifesto.
        b7 = passo("B7 — Mudanças pequenas e verificáveis")
        for termo in ("do projeto autenticado", "**não define identidade**", "`principal_from_env`",
                      "nunca monta `Principal(...)` nem grava `FUNDACAO_PRINCIPAL`", "a identidade de ensaio vai no comando"):
            self.assertIn(termo, b7, termo)

    def test_b8_compara_pela_ferramenta_do_projeto(self):
        b8 = passo("B8 — Comparação antes × depois")
        # Revisão de segurança da 1.7.6 (R176-01): o hash de um arquivo só não cobre o que a ferramenta importa nem diz
        # o que fazer quando não confere; a pasta inteira vai por manifesto, a ferramenta roda sem a pasta dela no
        # caminho de importação e a divergência para a execução. É conferência contra mudança, não barreira.
        for termo in ("ferramenta de execução que ficou no projeto", "manifesto.py verificar", "`python -P`",
                      "não barreira", "não rode, registre e pare"):
            self.assertIn(termo, b8, termo)
        # Segunda passada da mesma revisão: o `verificar` não pega ferramenta e manifesto trocados juntos (resíduo do
        # R176-01) nem o que o manifesto não vê (R176-04), e o `-P` só existe a partir do Python 3.11 (R176-05).
        for termo in ("confira o SHA-256 do arquivo do manifesto com o citado no relatório",
                      "não vê ligação (link ou junção)", "tem de dar `excluidos` 0",
                      "não põe a própria pasta no caminho de importação", "`python -P` (Python 3.11 ou mais novo)",
                      "`python -I`", "sem nenhum dos dois, não rode e pare",
                      # Terceira passada: o `criar` descarta, sem listar, as pastas que ignora (__pycache__, .venv...).
                      "nenhuma pasta ou ligação com nome que ele ignora pode existir nela"):
            self.assertIn(termo, b8, termo)

    def test_portao_2_para_quando_a_ferramenta_diverge(self):
        ritmo = passo("Ritmo: dois portões")
        self.assertIn("a ferramenta de execução divergir do manifesto dela (B7)", ritmo)

    def test_b9_procura_a_ferramenta_e_repete_a_comparacao(self):
        b9 = passo("B9 — Reexecução segura")
        for termo in ("ferramenta de execução no projeto", "recrie a ferramenta no projeto escrevendo-a de novo",
                      "não copie a da pasta temporária", "repita a comparação (B8) no escopo da decisão que cobriu a primeira",
                      "pelo caminho real", "pode ser repetida pela ferramenta do projeto"):
            self.assertIn(termo, b9, termo)


if __name__ == "__main__":
    unittest.main()
