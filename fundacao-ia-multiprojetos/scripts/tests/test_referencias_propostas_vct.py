"""Referências das propostas da análise do vibe-coding-toolkit (21/10/2026): cada regra nova está escrita no
lugar certo da skill, com as palavras que a tornam executável."""

from __future__ import annotations

import unittest

from apoio import SKILL

REF = SKILL / "references"


def ler(rel: str) -> str:
    return (REF / rel).read_text(encoding="utf-8")


class TestOndasDeAgentes(unittest.TestCase):
    """Proposta 14: paralelismo em ondas (Arquivos / Depende de / Recursos) e armadilhas no pacote."""

    def test_regra_de_ondas_na_capacidade_02(self):
        texto = ler("capacidades/02-agentes-subagentes.md")
        for trecho in ("**Arquivos:**", "**Depende de:**", "**Recursos:**", "Um escritor por arquivo",
                       "executor não faz commit", "`state/state.sqlite`", "roda em série",
                       "armadilhas já conhecidas", "confirmar que parou"):
            self.assertIn(trecho, texto)



class TestReavaliacaoDoComportamento(unittest.TestCase):
    """Proposta 12: quando repetir as avaliações de comportamento, e onde."""

    def test_gatilho_no_fluxo_c(self):
        texto = ler("fluxo-c-operar.md")
        for trecho in ("**Reavaliação do comportamento**", "E10 (RETOMADA desatualizada)", "CEN-13",
                       "fora** de uma fundação", '"não rodada", nunca "passou"', "teste de fumaça"):
            self.assertIn(trecho, texto)


class TestRevisaoDeSeguranca(unittest.TestCase):
    """Proposta 13: modelo de revisão de segurança por versão e achado com cenário de falha e confiança."""

    def test_modelo_e_colunas(self):
        modelo = (SKILL / "assets" / "templates" / "REVISAO-SEGURANCA.md").read_text(encoding="utf-8")
        for trecho in ("somente leitura", "diff exato", "Confiança", "Origem: introduzido", "Cenário de falha concreto",
                       "Contraevidência", "não estabelece que a versão é segura", "SHA-256 antes = depois"):
            self.assertIn(trecho, modelo)
        auditoria = (SKILL / "assets" / "templates" / "AUDITORIA.md").read_text(encoding="utf-8")
        for trecho in ("Cenário de falha concreto", "Confiança", "Origem (introduzido", "é palpite"):
            self.assertIn(trecho, auditoria)
        self.assertIn("assets/templates/REVISAO-SEGURANCA.md", ler("fluxo-c-operar.md"))

if __name__ == "__main__":
    unittest.main()
