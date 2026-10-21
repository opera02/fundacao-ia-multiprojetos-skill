"""Perfis do host na 1.7.0 (análise do vibe-coding-toolkit, 21/10/2026, propostas 2 e 3, e a decisão 4 do titular).

- Os dois perfis trazem claudeMdExcludes para `**/projects/*/data/**`: CLAUDE.md e AGENTS.md de uma cópia importada
  não carregam como instrução quando o agente lê arquivos ali (documentação do Claude Code, 21/10/2026).
- Skill aninhada, que nenhuma configuração exclui, sai negada por nome (`Skill(<nome>)`) com --negar-skill.
- O perfil de dados reais nega WebFetch e WebSearch, a saída que o sandbox de rede (só shell) não cobre; a
  conferência do perfil acusa a falta.
- `identidade --projeto` entrega o projeto autenticado (FUNDACAO_PROJECT), sem trocar o que o titular já gravou.
"""

from __future__ import annotations

import importlib.util
import json
import unittest

from apoio import SKILL

HOST = SKILL / "assets" / "host"


def carregar():
    spec = importlib.util.spec_from_file_location("preparo_host_vct", HOST / "preparo_host.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TestPerfisDaVersao170(unittest.TestCase):
    def setUp(self):
        self.m = carregar()
        self.kw = dict(raiz=r"E:\Fundacao Exemplo", projeto="caso-real", perfil_windows=r"C:\Perfis\titular",
                       outros_projetos=["lab-a"])

    def test_pastas_de_dados_excluidas_nos_dois_perfis(self):
        win = self.m.perfil_windows(raiz=r"E:\Fundacao Exemplo", python=r"C:\Py\python.exe")
        wsl = self.m.perfil_wsl(**self.kw)
        for perfil in (win, wsl):
            self.assertEqual(perfil["claudeMdExcludes"], ["**/projects/*/data/**"])

    def test_web_negada_so_no_perfil_de_dados_reais(self):
        win = self.m.perfil_windows(raiz=r"E:\Fundacao Exemplo", python=r"C:\Py\python.exe")
        wsl = self.m.perfil_wsl(**self.kw)
        self.assertTrue({"WebFetch", "WebSearch"} <= set(wsl["permissions"]["deny"]))
        self.assertFalse({"WebFetch", "WebSearch"} & set(win["permissions"]["deny"]))  # laboratório pesquisa

    def test_conferencia_acusa_web_liberada_e_falta_de_exclusao(self):
        perfil = self.m.perfil_wsl(**self.kw)
        raiz = "/mnt/e/Fundacao Exemplo"
        self.assertEqual(self.m.conferir_perfil_wsl(perfil, raiz), [])
        sem_web = json.loads(json.dumps(perfil))
        sem_web["permissions"]["deny"] = [r for r in sem_web["permissions"]["deny"] if not r.startswith("Web")]
        self.assertTrue(any("WebFetch" in p for p in self.m.conferir_perfil_wsl(sem_web, raiz)))
        sem_exclusao = json.loads(json.dumps(perfil))
        del sem_exclusao["claudeMdExcludes"]
        self.assertTrue(any("claudeMdExcludes" in p for p in self.m.conferir_perfil_wsl(sem_exclusao, raiz)))

    def test_skill_aninhada_negada_por_nome(self):
        win = self.m.perfil_windows(raiz=r"E:\Fundacao Exemplo", python=r"C:\Py\python.exe",
                                    negar=["squad-peticoes", "squad-peticoes"])
        self.assertEqual([r for r in win["permissions"]["deny"] if r.startswith("Skill(")], ["Skill(squad-peticoes)"])
        wsl = self.m.perfil_wsl(**self.kw, negar=["revisor:legado"])
        self.assertIn("Skill(revisor:legado)", wsl["permissions"]["deny"])
        with self.assertRaises(ValueError):
            self.m.perfil_windows(raiz=r"E:\Fundacao Exemplo", python=r"C:\Py\python.exe", negar=["../fora"])

    def test_identidade_com_projeto_sem_trocar_o_do_titular(self):
        novo = self.m.identidade("titular-ensaio", {"env": {"OUTRA": "1"}}, "fundacao-de-ia")
        self.assertEqual(novo["env"], {"OUTRA": "1", "FUNDACAO_" + "PRINCIPAL": "titular-ensaio",
                                       "FUNDACAO_PROJECT": "fundacao-de-ia"})
        self.assertEqual(self.m.identidade("titular-ensaio", novo, "fundacao-de-ia"), novo)       # idempotente
        with self.assertRaises(self.m.Conflito):
            self.m.identidade("titular-ensaio", novo, "outro-projeto")


if __name__ == "__main__":
    unittest.main()
