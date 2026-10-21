"""As referências da skill descrevem a barreira de decisões assinadas que o kit tem (1.6.0).

Cada subcomando de `python -m fundacao decisao` e o `tarefa concluir` aparecem onde o executor os procura: §2 de
`references/seguranca-isolamento.md` (o que a barreira protege, a política e o piso da âncora), os portões do fluxo B
(uma assinatura por portão) e `references/comunicacao-leigo.md` §3 (como pedir a assinatura ao titular leigo). Falha
quando a CLI ganha um subcomando que a documentação não cita, ou a documentação cita um que não existe.
"""

from __future__ import annotations

import re
import sys
import unittest

from apoio import KIT, SKILL

sys.path.insert(0, str(KIT))
from fundacao.__main__ import build_parser  # noqa: E402


def secao(texto: str, titulo: str) -> str:
    """Trecho de um título Markdown até o próximo do mesmo nível ou acima (`#` dentro de bloco de código não conta)."""
    linhas, dentro, nivel, trecho = texto.splitlines(), False, None, []
    for linha in linhas:
        if linha.startswith("```"):
            dentro = not dentro
        m = None if dentro or linha.startswith("```") else re.match(r"^(#+) ", linha)
        if nivel is None:
            if m and linha[len(m.group(0)):].startswith(titulo):
                nivel = len(m.group(1))
            continue
        if m and len(m.group(1)) <= nivel:
            break
        trecho.append(linha)
    return "\n".join(trecho)


def acoes(comando: str) -> list[str]:
    sub = next(a for a in build_parser()._actions if getattr(a, "choices", None) and comando in a.choices)
    acao = next(a for a in sub.choices[comando]._actions if a.dest == "acao")
    return list(acao.choices)


class TestReferenciasDaBarreira(unittest.TestCase):
    def ler(self, rel: str) -> str:
        return (SKILL / rel).read_text(encoding="utf-8")

    def test_seguranca_secao_2_descreve_cada_subcomando_a_politica_e_o_piso(self):
        s2 = secao(self.ler("references/seguranca-isolamento.md"), "2. Identidade e autorização")
        self.assertTrue(s2)
        for acao in acoes("decisao"):
            self.assertIn(f"decisao {acao}", s2, acao)
        self.assertIn("tarefa concluir", s2)
        for termo in ("registry/politica-decisoes.json", "fundacao-decisao", "allowed_signers", "piso"):
            self.assertIn(termo, s2, termo)
        citados = set(re.findall(r"decisao ([a-z-]+)", s2)) - {"assinada", "do"}
        self.assertLessEqual(citados, set(acoes("decisao")), "subcomando citado que a CLI não tem")

    def test_portoes_do_fluxo_b_dizem_como_assinar_e_concluir(self):
        ritmo = secao(self.ler("references/fluxo-b-adaptar.md"), "Ritmo: dois portões")
        for termo in ("decisao preparar", "decisao registrar", "tarefa concluir", "correcao"):
            self.assertIn(termo, ritmo, termo)

    def test_comunicacao_com_leigo_ensina_a_pedir_a_assinatura(self):
        s3 = secao(self.ler("references/comunicacao-leigo.md"), "3. Comando que o titular precisa rodar")
        for termo in ("para_o_titular", "senha", "PowerShell", "Good"):
            self.assertIn(termo, s3, termo)

    def test_lista_de_comandos_do_kit_no_fluxo_a_tem_o_ciclo_da_decisao(self):
        kit = secao(self.ler("references/fluxo-a-implantar.md"), "§Kit")
        for termo in ("decisao preparar", "decisao registrar", "tarefa concluir"):
            self.assertIn(termo, kit, termo)

    def test_skill_aponta_para_a_barreira(self):
        texto = self.ler("SKILL.md")
        self.assertIn("tarefa concluir", texto)
        self.assertRegex(texto, r"decis[õo]es assinadas[^\n]*seguranca-isolamento\.md")


if __name__ == "__main__":
    unittest.main()
