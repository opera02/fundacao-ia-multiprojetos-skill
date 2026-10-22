"""Auditoria Codex Security da 1.7.6, achado #1: o portão 1 do fluxo B pedia o aceite para "executar código da origem
numa cópia isolada (B6)", e a cópia era só outra pasta de trabalho. As referências agora descrevem a fronteira real:
o plano de execução do `caracterizar.py` (SHA-256 na folha de decisões; bubblewrap no WSL; recusa sem ele, salvo
`--sem-isolamento` com o motivo e o aviso de autoridade total), o B8 pelo plano sem isolamento, com a identidade só
pelo nome, e o lançador em `references/seguranca-isolamento.md` §5 e §6. O comportamento está nos testes de
`test_auditoria_1_7_6_execucao_isolada.py`.
"""

from __future__ import annotations

import unittest

from apoio import SKILL
from test_referencias_decisoes import secao


class TestReferenciasDescrevemAFronteiraReal(unittest.TestCase):
    def ler(self, rel: str) -> str:
        return (SKILL / rel).read_text(encoding="utf-8")

    def trecho(self, rel: str, titulo: str) -> str:
        return " ".join(secao(self.ler(rel), titulo).split())

    def test_fluxo_b_pede_o_plano_no_portao_1_e_roda_por_ele(self):
        self.assertNotIn("cópia isolada", self.ler("references/fluxo-b-adaptar.md"))
        ritmo = self.trecho("references/fluxo-b-adaptar.md", "Ritmo: dois portões")
        for termo in ("**plano de execução**", "SHA-256", "`para_a_folha`", "toda a autoridade da conta",
                      "o plano de execução recalculado der outro SHA-256"):
            self.assertIn(termo, ritmo, termo)
        b6 = self.trecho("references/fluxo-b-adaptar.md", "B6 — Referência recuperável e testes de caracterização")
        for termo in ("caracterizar.py plano", "--plano-aprovado", "--manifesto", "bubblewrap", "recusa",
                      "--sem-isolamento", "terminal do Ubuntu", "nunca com nome de segredo"):
            self.assertIn(termo, b6, termo)
        b8 = self.trecho("references/fluxo-b-adaptar.md", "B8 — Comparação antes × depois")
        for termo in ("--plano-aprovado", "--variavel FUNDACAO_PRINCIPAL", "sem isolamento", "o valor vem do lançador"):
            self.assertIn(termo, b8, termo)

    def test_seguranca_e_modelos_descrevem_o_lancador(self):
        s5 = self.trecho("references/seguranca-isolamento.md", "5. Controles preventivos no host")
        for termo in ("scripts/execucao_isolada.py", "--unshare-all", "--sem-isolamento", "toda a autoridade da conta",
                      "Job Object", "não foi conferido"):
            self.assertIn(termo, s5, termo)
        s6 = self.trecho("references/seguranca-isolamento.md", "6. Limitação honesta")
        self.assertIn("Componente roda pelo despacho do kit com a autoridade da conta", s6)
        self.assertIn("caracterizar.py plano", self.ler("assets/templates/FOLHA-DE-DECISOES.md"))
        self.assertNotIn("cópia isolada", self.ler("assets/templates/DIAGNOSTICO.md"))


if __name__ == "__main__":
    unittest.main()
