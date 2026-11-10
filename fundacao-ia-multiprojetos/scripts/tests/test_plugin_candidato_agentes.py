"""A sugestão do campo `agentes` da ficha pelo scripts/plugin_candidato.py (1.7.11, lote A2).

O `conferir`, o `montar` e o `revisar` trazem, para cada agente do candidato que tem `tools` no cabeçalho e arquivo
`agents/<name>.md`, o item `{nome, sha256, ferramentas, modelo}` que a ficha leva. É sugestão: o kit (aberturas_agentes)
é quem recusa o que não bate com o arquivo, e aqui se prova que a sugestão, posta na ficha, passa na regra do kit, e que a
troca do arquivo depois dela a faz falhar. Pastas descartáveis com dados fictícios; nada do candidato é executado."""

from __future__ import annotations

import hashlib
import sys
import unittest

from apoio import KIT
from test_plugin_candidato import AGENTE_OK, MOD, Fundacao

if str(KIT) not in sys.path:  # o kit desta skill, pelo caminho (o mesmo que a ferramenta do titular carrega)
    sys.path.insert(0, str(KIT))

from fundacao.core import aberturas_plugins as plugins  # noqa: E402


class AgentesParaAFicha(Fundacao, unittest.TestCase):
    def sha_do_agente(self, pasta, nome="revisor") -> str:
        return hashlib.sha256((pasta / "agents" / f"{nome}.md").read_bytes()).hexdigest()

    def test_agente_com_tools_vira_item_da_ficha(self):
        pasta = self.candidato()
        res = MOD.conferir(pasta)
        self.assertEqual(res["agentes_para_a_ficha"], [{"nome": "revisor", "sha256": self.sha_do_agente(pasta),
                                                        "ferramentas": ["Read", "Grep"], "modelo": "sonnet"}])

    def test_sem_model_a_sugestao_e_inherit(self):
        pasta = self.candidato({"agents/revisor.md": AGENTE_OK.replace("model: sonnet\n", "")})
        self.assertEqual(MOD.conferir(pasta)["agentes_para_a_ficha"][0]["modelo"], "inherit")

    def test_sem_tools_ou_com_nome_diferente_do_arquivo_fica_de_fora(self):
        sem_tools = self.candidato({"agents/revisor.md": AGENTE_OK.replace("tools: Read, Grep\n", "")})
        self.assertEqual(MOD.conferir(sem_tools)["agentes_para_a_ficha"], [])
        outro = self.candidato({"agents/revisor.md": AGENTE_OK.replace("name: revisor", "name: outro")})
        self.assertEqual(MOD.conferir(outro)["agentes_para_a_ficha"], [])
        especificador = self.candidato({"agents/revisor.md": AGENTE_OK.replace("tools: Read, Grep", "tools: Read, Bash(git *)")})
        item = MOD.conferir(especificador)["agentes_para_a_ficha"]
        self.assertTrue(all("(" not in f for a in item for f in a["ferramentas"]), item)

    def test_candidato_recusado_nao_sugere_nada(self):
        pasta = self.candidato({"hooks/aviso.sh": "echo ficticio\n"})
        res = MOD.conferir(pasta)
        self.assertFalse(res["conforme"])
        self.assertEqual(res["agentes_para_a_ficha"], [])

    def test_a_sugestao_passa_na_regra_do_kit_e_a_troca_do_arquivo_depois_dela_falha(self):
        pasta = self.candidato()
        res = MOD.conferir(pasta)
        item = {"nome": "demo-kit", "origem": "plugins-candidatos/demo-kit", "manifesto_sha256": res["manifesto_sha256"],
                "agentes": res["agentes_para_a_ficha"]}
        self.assertEqual(plugins.conferir_plugin(self.proj, item)["erros"], [])
        (pasta / "agents" / "revisor.md").write_text(AGENTE_OK + "Instrução nova.\n", encoding="utf-8")
        self.assertTrue(plugins.conferir_plugin(self.proj, item)["erros"])

    def test_revisao_traz_o_item_de_agentes(self):
        pasta = self.candidato()
        texto, res = MOD.revisar(pasta)
        self.assertIn("Aceito abrir estes agentes", texto)
        self.assertIn(res["agentes_para_a_ficha"][0]["sha256"], texto)
        sem_agente = self.candidato(sem=("agents/revisor.md",))
        self.assertNotIn("Aceito abrir estes agentes", MOD.revisar(sem_agente)[0])

    def test_montar_devolve_a_sugestao_e_deixa_a_ficha_de_antes(self):
        origem = self.origem_arvore()
        res = MOD.montar(self.raiz, "demo", "demo-kit", origem)
        self.assertEqual(set(res["ficha"]), {"nome", "origem", "manifesto_sha256"})
        self.assertEqual([a["nome"] for a in res["agentes_para_a_ficha"]], ["revisor"])


if __name__ == "__main__":
    unittest.main()
