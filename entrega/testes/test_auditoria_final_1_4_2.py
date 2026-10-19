"""Auditoria final da 1.4.2 — `instalar_skill.py`: AF-02 (troca por duas renomeações: exceção sem sobras, queda
concluída pelo próximo comando, `remover` limpa a área de preparo), AF-03 (`name` do cabeçalho conferido) e AF-04
(ligação com este nome que aponta para outra skill é mantida).

Perfil DESCARTÁVEL (USERPROFILE e HOME temporários, conferidos antes). Falham no instalador da 1.4.2 (menos o
controle `test_af04_ligacao_para_pasta_desta_skill…`) e passam no da 1.4.3. Relatório: `auditoria/AUDITORIA-FINAL-1.4.2.md`.
"""

from __future__ import annotations

import os
import subprocess
import unittest

from test_auditoria_1_4_1 import NOME, _Base, skill_md

# Prelúdios do processo filho: a renomeação preparo -> skills/ (origem em skills-preparo) falha ou derruba o processo;
# a renomeação de retorno (skills-anteriores -> skills/) continua funcionando, como numa falha real só da versão nova.
FALHA_NA_SEGUNDA_RENOMEACAO = """
import os
_replace = os.replace
def _r(src, dst, *a, **k):
    if os.path.basename(os.path.dirname(str(src))) == 'skills-preparo':
        raise OSError(5, 'falha simulada na troca (segunda renomeacao)')
    return _replace(src, dst, *a, **k)
os.replace = _r
"""
QUEDA_ENTRE_AS_RENOMEACOES = """
import os
_replace = os.replace
def _r(src, dst, *a, **k):
    if os.path.basename(os.path.dirname(str(src))) == 'skills-preparo':
        os._exit(3)
    return _replace(src, dst, *a, **k)
os.replace = _r
"""


class _Preparo(_Base):
    @property
    def preparo(self):
        return self.perfil / ".agents" / "skills-preparo"

    def sobras(self) -> list[str]:
        return sorted(p.name for p in self.preparo.iterdir()) if self.preparo.exists() else []

    def instalar(self, origem):
        p, _ = self.rodar("instalar", "--origem", origem)
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])


class TestAF02TrocaPorDuasRenomeacoes(_Preparo):
    def test_af02_excecao_na_troca_devolve_a_anterior_sem_sobras(self):
        v1, v2 = self.nova_origem("v1", "versao-1"), self.nova_origem("v2", "versao-2")
        self.instalar(v1)
        p, saida = self.rodar("atualizar", "--origem", v2, preludio=FALHA_NA_SEGUNDA_RENOMEACAO)
        self.assertNotEqual(p.returncode, 0)
        self.assertIsNotNone(saida, f"saída não é JSON: {p.stderr[-300:]}")
        self.assertEqual(self.descricao_instalada(), "versao-1", "a versão anterior não voltou ao lugar")
        self.assertTrue((self.link / "SKILL.md").exists())
        self.assertEqual(self.sobras(), [], "a cópia preparada ficou em skills-preparo depois da falha")

    def test_af02_queda_entre_as_renomeacoes_e_concluida_pelo_proximo_comando(self):
        v1, v2 = self.nova_origem("v1", "versao-1"), self.nova_origem("v2", "versao-2")
        self.instalar(v1)
        p, _ = self.rodar("atualizar", "--origem", v2, preludio=QUEDA_ENTRE_AS_RENOMEACOES)
        self.assertFalse(self.copia.exists(), "a queda entre as renomeações não se reproduziu")
        p, saida = self.rodar("verificar", "--origem", v2)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("troca_interrompida", saida or {}, "o verificar não avisou da troca interrompida")
        p, saida = self.rodar("atualizar", "--origem", v2)
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])
        self.assertTrue(any("troca interrompida concluída" in s for s in (saida or {}).get("passos", [])), saida)
        self.assertEqual(self.descricao_instalada(), "versao-2")
        self.assertTrue((self.link / "SKILL.md").exists(), "a ligação ficou pendurada")
        self.assertEqual(self.sobras(), [])

    def test_af02_remover_limpa_a_area_de_preparo(self):
        self.instalar(self.nova_origem("v1", "versao-1"))
        sobra = self.preparo / f"{NOME}-20260101-000000"
        (sobra / "references").mkdir(parents=True)
        (sobra / "SKILL.md").write_text(skill_md("sobra"), encoding="utf-8")
        p, saida = self.rodar("remover", "--confirmar")
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])
        self.assertTrue((saida or {}).get("removido"))
        self.assertFalse(self.preparo.exists(), "a área de preparo ficou com sobras depois do remover")


class TestAF03NameDoCabecalho(_Base):
    def test_af03_origem_com_outro_name_e_recusada(self):
        outra = self.nova_origem("outro-nome", "skill-de-outro-nome")
        (outra / "SKILL.md").write_text("---\nname: outra-skill-ficticia\ndescription: x\n---\n", encoding="utf-8")
        pacote = self.empacotar(outra, self.base / "pacote-outro-nome" / f"{NOME}.skill")
        for rotulo, origem in (("pasta", outra), ("pacote", pacote)):
            with self.subTest(rotulo):
                p, saida = self.rodar("instalar", "--origem", origem)
                self.assertNotEqual(p.returncode, 0, "instalou uma skill cujo cabeçalho declara outro name")
                self.assertFalse(self.copia.exists())
                self.assertFalse(os.path.lexists(self.link))
                self.assertIn("name", (saida or {}).get("erro", ""), saida)


@unittest.skipUnless(os.name == "nt", "junção de diretório só existe no Windows")
class TestAF04LigacaoComEsteNomeParaOutraPasta(_Base):
    def juncao(self, alvo):
        self.link.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(self.link), str(alvo)], capture_output=True, text=True,
                           errors="replace")
        if r.returncode != 0:
            self.skipTest(f"junção indisponível: {r.stdout.strip()} {r.stderr.strip()}")

    def test_af04_ligacao_para_pasta_de_outra_skill_e_mantida_e_relatada(self):
        alheia = self.base / "alheia"
        alheia.mkdir()
        (alheia / "SKILL.md").write_text("---\nname: outra-skill\ndescription: x\n---\n", encoding="utf-8")
        self.juncao(alheia)
        p, saida = self.rodar("remover", "--confirmar")
        self.assertTrue(os.path.lexists(self.link), "removeu uma ligação que não é desta skill")
        self.assertTrue((alheia / "SKILL.md").exists())
        self.assertNotEqual(p.returncode, 0)
        self.assertTrue(any(m.get("acao") == "manter" and m.get("tipo") == "ligação"
                            for m in (saida or {}).get("mantidos", [])), saida)

    def test_af04_ligacao_para_pasta_desta_skill_e_removida_sem_tocar_o_alvo(self):
        """Controle: passa na 1.4.2 e na 1.4.3 (instalação manual por ligação é desta skill)."""
        manual = self.base / "manual"
        (manual / "references").mkdir(parents=True)
        (manual / "SKILL.md").write_text(skill_md("manual-por-ligacao"), encoding="utf-8")
        self.juncao(manual)
        p, saida = self.rodar("remover", "--confirmar")
        self.assertFalse(os.path.lexists(self.link))
        self.assertTrue((manual / "SKILL.md").exists(), "apagou o alvo da ligação")
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])


if __name__ == "__main__":
    unittest.main()
