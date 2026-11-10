"""A tela e a assinatura da ficha com agentes de plugin (1.7.11, lote A2; assets/host/fundacao_titular.py).

O titular vê cada agente e as ferramentas dele por código fixo, antes da pergunta, e a comparação com a ficha anterior
mostra o agente que passa a abrir (com o início do SHA-256 do arquivo: arquivo trocado é um item que fecha e outro que
abre). A ferramenta recusa, sem assinar nada, a ficha cujo agente não bate com o arquivo (hash, ferramentas do
cabeçalho, nome do arquivo), que tem ferramenta fora da lista ou cujo plugin não leva o prefixo do projeto, e o kit da
raiz sem o `aberturas_agentes.py` ou com outro (o módulo entrou no VALIDADOR). Raiz, chaves e âncora de ENSAIO em pastas
temporárias; sem `ssh-keygen`, pula."""

from __future__ import annotations

import hashlib
import json
import unittest

import test_fundacao_titular as base
from test_fundacao_titular import PROJETO, K, TITULAR, ficha

PLUGIN = f"{PROJETO}-redacao"
SEPARADOR = "---- Daqui até a pergunta, só texto fixo desta ferramenta ----"


def agente_md(tools="Read, Grep, Glob, Write, Edit", modelo="sonnet") -> str:
    return (f"---\nname: redator\ndescription: Redige a minuta (fictício).\ntools: {tools}\nmodel: {modelo}\n---\n\n"
            "Você redige a minuta.\n")


class TitularComAgentes(base.TitularCase):
    tela = base.TestTelaDoTitular.tela

    def montar_plugin(self, texto: str | None = None, nome: str = PLUGIN) -> dict:
        pasta = self.projeto / "plugins-candidatos" / nome
        for rel, conteudo in {".claude-plugin/plugin.json": json.dumps({"name": nome, "version": "0.1.0"}),
                              "skills/ola/SKILL.md": "---\nname: ola\ndescription: Ola (fictício).\n---\n\nCorpo.\n",
                              "agents/redator.md": texto if texto is not None else agente_md()}.items():
            alvo = pasta.joinpath(*rel.split("/"))
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text(conteudo, encoding="utf-8", newline="\n")
        return {"nome": nome, "origem": f"plugins-candidatos/{nome}",
                "manifesto_sha256": K.plugins.conferir_pasta_do_plugin(pasta, nome)["manifesto_sha256"]}

    def agente(self, plugin: str = PLUGIN, **mudanca) -> dict:
        sha = hashlib.sha256((self.projeto / "plugins-candidatos" / plugin / "agents" / "redator.md").read_bytes()
                             ).hexdigest()
        return {"nome": "redator", "sha256": sha, "ferramentas": ["Read", "Grep", "Glob", "Write", "Edit"],
                "modelo": "sonnet", **mudanca}

    def ficha_com_agente(self, **mudanca) -> dict:
        item = self.montar_plugin()
        return ficha(plugins=[{**item, "agentes": [self.agente(**mudanca)]}])

    def test_a_tela_mostra_o_agente_com_as_ferramentas_e_a_comparacao_o_que_abre(self):
        item = self.montar_plugin(agente_md("Read, Bash"))
        f = ficha(plugins=[{**item, "agentes": [self.agente(ferramentas=["Read", "Bash"])]}])
        linhas, _ = self.tela(f)
        fixas = linhas[linhas.index(SEPARADOR) + 1:]
        texto = " ".join(fixas)
        sha8 = f["plugins"][0]["agentes"][0]["sha256"][:8]
        for trecho in (f"O agente '{PLUGIN}:redator' poderá ser chamado pela sessão como subagente",
                       "com as ferramentas 'Read', 'Bash' e o modelo 'sonnet'", f"SHA-256 {sha8}…",
                       "conferiu na forma, e não no texto", "Roda com as regras e os limites da sessão",
                       "Com Bash, ele roda comandos com a mesma autoridade dos comandos da sessão",
                       f"passa a abrir: agentes {PLUGIN}:redator (SHA-256 {sha8}"):
            self.assertIn(trecho, texto)
        numeradas = [linha for linha in fixas if "poderá ser chamado pela sessão como subagente" in linha]
        self.assertEqual(len(numeradas), 1)
        self.assertRegex(numeradas[0], r"^  [0-9]+\. ")  # na lista numerada, como as outras aberturas

    def test_ficha_com_agente_conforme_assina(self):
        self.preparar(self.ficha_com_agente())
        codigo, _texto = self.assinar()
        self.assertEqual(codigo, 0)
        self.assertTrue((self.caixa / "ficha-v1.json").is_file())

    def test_arquivo_do_agente_trocado_depois_de_preparar_a_ficha_recusa_sem_assinar(self):
        self.preparar(self.ficha_com_agente())
        (self.projeto / "plugins-candidatos" / PLUGIN / "agents" / "redator.md").write_text(
            agente_md() + "Instrução nova.\n", encoding="utf-8", newline="\n")
        self.recusa("não passa nos tetos fixos")

    def test_agente_fora_das_regras_recusa_sem_assinar(self):
        casos = {
            "hash do agente diferente do arquivo": self.ficha_com_agente(sha256="e" * 64),
            "ferramenta do cabeçalho diferente da ficha": self.ficha_com_agente(ferramentas=["Read"]),
            "ferramenta Agent": self.ficha_com_agente(ferramentas=["Read", "Agent"]),
            "WebFetch sem a abertura na ficha": self.ficha_com_agente(ferramentas=["Read", "WebFetch"]),
            "modelo diferente do cabeçalho": self.ficha_com_agente(modelo="opus"),
            "agente sem o arquivo": self.ficha_com_agente(nome="fantasma"),
        }
        for nome, f in casos.items():
            with self.subTest(nome):
                self.preparar(f)
                self.recusa("não passa nos tetos fixos")

    def test_plugin_com_agentes_sem_o_prefixo_do_projeto_recusa(self):
        item = self.montar_plugin(nome="redacao")
        self.preparar(ficha(plugins=[{**item, "agentes": [self.agente("redacao")]}]))
        self.recusa("plugins[0].nome")

    def test_kit_da_raiz_sem_ou_com_outro_aberturas_agentes_recusa(self):
        self.preparar(self.ficha_com_agente())
        da_raiz = self.raiz / "fundacao" / "core" / "aberturas_agentes.py"
        original = da_raiz.read_bytes()
        da_raiz.write_bytes(original + b"\n# alterado na raiz\n")
        self.recusa("aberturas_agentes.py do kit da raiz difere")
        da_raiz.unlink()
        self.recusa("não tem fundacao/core/aberturas_agentes.py")
        da_raiz.write_bytes(original)
        self.assertEqual(self.assinar()[0], 0, "com o kit da raiz igual, assina")

    def test_kit_da_raiz_sem_ou_com_outro_aberturas_scripts_recusa(self):
        """O aberturas_scripts.py decide quais .py e locks o plugin pode levar (1.7.11, lote S1): trocado na raiz, falsearia
        a validação da ficha que o titular assina."""
        self.preparar(self.ficha_com_agente())
        da_raiz = self.raiz / "fundacao" / "core" / "aberturas_scripts.py"
        original = da_raiz.read_bytes()
        da_raiz.write_bytes(original + b"\n# alterado na raiz\n")
        self.recusa("aberturas_scripts.py do kit da raiz difere")
        da_raiz.unlink()
        self.recusa("não tem fundacao/core/aberturas_scripts.py")
        da_raiz.write_bytes(original)
        self.assertEqual(self.assinar()[0], 0, "com o kit da raiz igual, assina")

    def test_o_modulo_novo_esta_no_validador_da_ferramenta(self):
        self.assertIn("fundacao/core/aberturas_agentes.py", TITULAR.VALIDADOR)
        self.assertIn("fundacao/core/aberturas_scripts.py", TITULAR.VALIDADOR)
        for rel in TITULAR.VALIDADOR:
            self.assertTrue((base.KIT / rel).is_file(), rel)


if __name__ == "__main__":
    unittest.main()
