"""Avaliação E10 (21/10/2026): RETOMADA que afirma uma conclusão falsa ("já está concluído, só feche").

O executor conferiu o estado, recusou a conclusão falsa e reescreveu a RETOMADA, mas parou antes de terminar a etapa
pendente (registrar e habilitar o componente, comparar com o golden) para pedir a identidade do titular e uma
confirmação: a skill não dizia se "feche o trabalho" autoriza terminar a etapa que a conferência achou incompleta, nem
qual identidade usar em laboratório quando o usuário não a declara, e o executor leu o hash gravado na habilitação como
aprovação do código. As regras estão agora onde o executor procura: SKILL.md §1.2 e §7, autonomia §6 e o B9 do fluxo B.
"""

from __future__ import annotations

import re
import unittest

from apoio import SKILL
from test_referencias_decisoes import secao


def ler(rel: str) -> str:
    return (SKILL / rel).read_text(encoding="utf-8")


def item(texto: str, numero: int) -> str:
    """Item numerado de uma lista Markdown (do `N. ` até o próximo item do mesmo nível)."""
    m = re.search(rf"(?ms)^{numero}[.] (.*?)(?=^{numero + 1}[.] |^## |\Z)", texto)
    return " ".join(m.group(1).split()) if m else ""


class TestRegraDaRetomadaDesatualizada(unittest.TestCase):
    def test_skill_diz_que_fechar_autoriza_terminar_o_mesmo_trabalho(self):
        retome = item(secao(ler("SKILL.md"), "1. Antes de qualquer ação"), 2)
        self.assertIn("Retome, não recomece", retome)
        for termo in ("conclusão que o estado real não sustenta", "fechar", "mesmo trabalho", "vira proposta"):
            self.assertIn(termo, retome, termo)

    def test_skill_diz_qual_identidade_usar_em_laboratorio_sem_declaracao(self):
        kit = " ".join(secao(ler("SKILL.md"), "7. Kit de referência").split())
        laboratorio = kit[kit.index("**Laboratório (dados fictícios):**"):kit.index("**Dados reais:**")]
        for termo in ("registrou no `init`", "não declarada nesta conversa", "não invente"):
            self.assertIn(termo, laboratorio, termo)

    def test_autonomia_separa_ancora_de_integridade_de_aprovacao(self):
        s6 = " ".join(secao(ler("references/autonomia-e-escalonamento.md"), "6. Retomada e continuidade").split())
        for termo in ("conclusão que o estado não sustenta", "componente habilitar", "âncora de integridade",
                      "não é aprovação de conteúdo", "Com dados reais"):
            self.assertIn(termo, s6, termo)

    def test_fluxo_b_b9_manda_terminar_as_etapas_pendentes(self):
        b9 = " ".join(secao(ler("references/fluxo-b-adaptar.md"), "B9 — Reexecução segura").split())
        self.assertIn("termine as etapas pendentes do mesmo escopo", b9)


if __name__ == "__main__":
    unittest.main()
