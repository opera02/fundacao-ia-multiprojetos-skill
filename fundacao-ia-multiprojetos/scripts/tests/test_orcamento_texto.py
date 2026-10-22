"""Orçamento do texto sempre carregado (método adaptado de Harness², P5: arXiv:2610.14224, github.com/google-research/
harness2, commit 1cfe254, Apache-2.0; texto e código próprios).

O corpo do SKILL.md, a descrição dele e o AGENTS.md que `instrucoes_raiz.py gerar` escreve na raiz entram no contexto
de toda sessão: competem com o espaço do próprio trabalho. O código do kit já tinha teto que só desce
(`assets/fundacao-kit/tests/test_fronteiras_codigo.py`); o texto sempre carregado não tinha, e o SKILL.md cresceu 23,5%
entre a 1.4.5 e a 1.7.7. Agora vale a mesma catraca, em caracteres:
- passar do teto reprova: regra nova paga com um corte ou vai para uma referência carregada sob demanda
  (`references/capacidades/08-ferramentas-hooks-mcp-skills-plugins.md` §6); subir o teto é mudança de critério;
- encolher mais que a folga sem baixar o teto também reprova: o teto acompanha o texto para baixo.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path

from apoio import SKILL, rodar_script

FOLGA = 300  # caracteres
# 1.7.7: os valores medidos quando a catraca entrou (corpo 17.466 caracteres, cerca de 4,4 a 5,8 mil tokens pela
# estimativa de 3 a 4 caracteres por token, não medida com o tokenizador).
# O AGENTS.md cita a pasta da raiz: a medida troca o caminho por `<raiz>`, para não depender da máquina (a revisão de
# segurança da 1.7.7 viu o teste falhar com uma pasta temporária mais longa). Todas as formas dele: na CI pública do
# Windows, a pasta temporária vem pelo nome curto 8.3 (RUNNER~1) e o AGENTS.md cita o caminho resolvido, com o nome
# longo, que a troca não pegava (1.7.8).
TETO = {"SKILL.md:corpo": 17466, "SKILL.md:descricao": 852, "AGENTS.md gerado": 2576}


def medir(sufixo: str = "") -> dict[str, int]:
    texto = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    _antes, frontmatter, corpo = texto.split("---", 2)
    descricao = re.search(r"^description:\s*(.*)$", frontmatter, re.M).group(1)
    raiz = Path(tempfile.mkdtemp(prefix="orcamento-texto-" + sufixo))
    try:
        p = rodar_script("instrucoes_raiz.py", "gerar", "--raiz", raiz)
        if p.returncode != 0:
            raise AssertionError("instrucoes_raiz.py gerar falhou: " + (p.stdout + p.stderr)[-400:])
        agents = (raiz / "AGENTS.md").read_text(encoding="utf-8")
        formas = {str(raiz), raiz.as_posix(), str(raiz.resolve()), raiz.resolve().as_posix()}
        for forma in sorted(formas, key=len, reverse=True):  # a mais longa antes: uma pode conter a outra
            agents = agents.replace(forma, "<raiz>")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)
    return {"SKILL.md:corpo": len(corpo), "SKILL.md:descricao": len(descricao), "AGENTS.md gerado": len(agents)}


class TestOrcamentoDoTexto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.medidas = medir()

    def test_texto_sempre_carregado_nao_passa_do_teto(self):
        acima = {k: (v, TETO[k]) for k, v in self.medidas.items() if v > TETO[k]}
        self.assertEqual(acima, {}, "texto sempre carregado acima do teto: pague com um corte ou leve a regra para uma "
                                    "referência carregada sob demanda (capacidade 08, §6)")

    def test_teto_acompanha_o_texto_para_baixo(self):
        folgados = {k: (v, TETO[k]) for k, v in self.medidas.items() if v < TETO[k] - FOLGA}
        self.assertEqual(folgados, {}, "o texto encolheu: baixe o teto em TETO")

    def test_medida_do_agents_nao_depende_da_pasta(self):
        # A mesma raiz com nomes de tamanhos diferentes dá a mesma medida (o caminho vira `<raiz>`).
        self.assertEqual(self.medidas["AGENTS.md gerado"], medir("x" * 60)["AGENTS.md gerado"])

    def test_a_medida_pega_texto_novo(self):
        # Quase certo: a mesma conta sobre um corpo com uma regra a mais passaria do teto.
        corpo = (SKILL / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[2]
        self.assertGreater(len(corpo + "\n- Regra nova." + " x" * FOLGA), TETO["SKILL.md:corpo"])


if __name__ == "__main__":
    unittest.main()
