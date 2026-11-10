"""Agentes de plugin pela ficha de aberturas (1.7.11, lote A2; desenho de skills e agentes, §2 e §4).

O item `plugins[].agentes[] {nome, sha256, ferramentas, modelo}` da ficha abre os agentes de arquivo do plugin. Cada
regra tem a prova negativa dela:
- ficha: ferramenta fora da lista (Agent, Task, Skill, NotebookEdit, MCP, especificador), WebFetch e WebSearch sem a
  abertura na ficha, lista vazia ou grande demais, modelo fora da lista, campo a mais ou a menos, nome repetido, tetos
  de 10 por plugin e 20 na ficha, e o prefixo `<projeto>-` obrigatório só para o plugin com agentes;
- disco: arquivo trocado depois da assinatura (o SHA-256 da ficha não é o do arquivo), arquivo ausente ou com outro nome,
  e o cabeçalho que diz outra coisa que a ficha (sem `tools`, ferramenta a mais ou a menos, modelo, nome) ou fora da lista
  fechada (effort, maxTurns, color).
Só dados fictícios, em pastas temporárias; nada do plugin é executado.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from helpers import KIT  # noqa: F401 (o kit no sys.path)

from fundacao.core import aberturas_agentes as agentes
from fundacao.core import aberturas_plugins as plugins
from fundacao.core import aberturas_regras as regras

HOJE = date(2026, 11, 8)
PROJETO = "juridico-lab"
PLUGIN = "juridico-lab-redacao"
ORIGEM = f"plugins-candidatos/{PLUGIN}"
FERRAMENTAS = ["Read", "Grep", "Glob", "Write", "Edit"]


def cabecalho(nome="redator", tools="Read, Grep, Glob, Write, Edit", modelo="sonnet", extra="") -> str:
    linhas = [f"name: {nome}", "description: Redige a minuta (fictício)."]
    if tools is not None:
        linhas.append(f"tools: {tools}")
    if modelo is not None:
        linhas.append(f"model: {modelo}")
    return "---\n" + "\n".join(linhas) + ("\n" + extra if extra else "") + "\n---\n\nVocê redige a minuta.\n"


def agente(nome="redator", sha="a" * 64, ferramentas=None, modelo="sonnet") -> dict:
    return {"nome": nome, "sha256": sha, "ferramentas": list(FERRAMENTAS if ferramentas is None else ferramentas),
            "modelo": modelo}


def plugin(nome=PLUGIN, **extra) -> dict:
    return {"nome": nome, "origem": f"plugins-candidatos/{nome}", "manifesto_sha256": "b" * 64, **extra}


def ficha(plugins_=None, **extra) -> dict:
    base = {"schema_version": regras.SCHEMA, "ficha_id": "aberturas-juridico-lab", "project_id": PROJETO, "versao": 1,
            "motivo": "Liberar um agente de redação no plugin do projeto.",
            "consequencias": "A sessão poderá chamar o agente de redação."}
    base.update({"plugins": plugins_} if plugins_ is not None else {})
    base.update(extra)
    return base


def erros(f) -> list[dict]:
    return regras.validar(f, projeto=PROJETO, hoje=HOJE)["erros"]


def campos(f) -> list[str]:
    return [e["campo"] for e in erros(f)]


class FichaDosAgentes(unittest.TestCase):
    def test_agente_conforme_vale_e_aparece_em_itens_e_na_tela(self):
        f = ficha([plugin(agentes=[agente(), agente("revisor", "c" * 64, ["Read", "Grep"], "inherit")])])
        self.assertEqual(erros(f), [])
        self.assertEqual([i for s, i in regras.itens(f) if s == "agentes"],
                         [f"{PLUGIN}:redator (SHA-256 {'a' * 12})", f"{PLUGIN}:revisor (SHA-256 {'c' * 12})"])
        linhas = [d for d in regras.descrever(f) if d["secao"] == "agentes"]
        self.assertEqual([d["item"] for d in linhas], [repr(f"{PLUGIN}:redator"), repr(f"{PLUGIN}:revisor")])
        self.assertIn("com as ferramentas 'Read', 'Grep', 'Glob', 'Write', 'Edit' e o modelo 'sonnet'", linhas[0]["texto"])
        self.assertIn("SHA-256 aaaaaaaa…", linhas[0]["texto"])
        self.assertIn("conferiu na forma, e não no texto", linhas[0]["texto"])
        self.assertIn("o mesmo da sessão (inherit)", linhas[1]["texto"])
        self.assertNotIn("Bash", linhas[0]["texto"])
        self.assertFalse(any(d.get("grava") for d in linhas))

    def test_a_tela_diz_quando_o_agente_tem_bash_ou_rede(self):
        f = ficha([plugin(agentes=[agente(ferramentas=["Read", "Bash", "WebSearch"])])], websearch=True)
        self.assertEqual(erros(f), [])
        texto = next(d["texto"] for d in regras.descrever(f) if d["secao"] == "agentes")
        self.assertIn("Com Bash, ele roda comandos com a mesma autoridade dos comandos da sessão", texto)
        self.assertIn("WebFetch ou WebSearch", texto)

    def test_sem_agentes_ou_com_a_lista_vazia_nada_abre_e_o_plugin_de_markdown_segue_com_aviso(self):
        for p in (plugin(nome="outro-nome"), plugin(nome="outro-nome", agentes=[])):
            with self.subTest(agentes="agentes" in p):
                f = ficha([p])
                resultado = regras.validar(f, projeto=PROJETO, hoje=HOJE)
                self.assertEqual(resultado["erros"], [])  # sem o prefixo: só aviso, as fichas em vigor seguem valendo
                self.assertTrue([a for a in resultado["avisos"] if "prefixo do projeto" in a["motivo"]])
                self.assertEqual([s for s, _ in regras.itens(f) if s == "agentes"], [])
                self.assertFalse([d for d in regras.descrever(f) if d["secao"] == "agentes"])

    def test_plugin_com_agentes_sem_o_prefixo_do_projeto_e_erro(self):
        f = ficha([plugin(nome="redacao", agentes=[agente()])])
        achados = [e for e in erros(f) if e["campo"] == "plugins[0].nome"]
        self.assertEqual(len(achados), 1)
        self.assertIn(f"{PROJETO}-<nome>", achados[0]["motivo"])
        com_prefixo = regras.validar(ficha([plugin(agentes=[agente()])]), projeto=PROJETO, hoje=HOJE)
        self.assertEqual((com_prefixo["erros"], com_prefixo["avisos"]), ([], []))

    def test_ferramenta_fora_da_lista_recusa(self):
        for nome in ("Agent", "Task", "Skill", "NotebookEdit", "SubagentHandback", "mcp__fsn__buscar_clientes",
                     "Bash(git *)", "Read(./x)", "MultiEdit", "bash", "*", "", None, 5, ["Read"]):
            with self.subTest(ferramenta=nome):
                f = ficha([plugin(agentes=[agente(ferramentas=["Read", nome])])])
                self.assertEqual(campos(f), ["plugins[0].agentes[0].ferramentas[1]"])

    def test_webfetch_e_websearch_so_com_a_abertura_na_ficha(self):
        for nome, abertura in (("WebFetch", {"rede": {"dominios": ["docs.exemplo.com.br"]},
                                              "webfetch": {"dominios": ["docs.exemplo.com.br"]}}),
                               ("WebSearch", {"websearch": True})):
            with self.subTest(ferramenta=nome):
                p = [plugin(agentes=[agente(ferramentas=["Read", nome])])]
                achados = erros(ficha(p))
                self.assertEqual([e["campo"] for e in achados], ["plugins[0].agentes[0].ferramentas[1]"])
                self.assertIn(f"{nome} só com", achados[0]["motivo"])
                self.assertEqual(erros(ficha(p, **abertura)), [])
        self.assertTrue(erros(ficha([plugin(agentes=[agente(ferramentas=["WebSearch"])])], websearch=False)))

    def test_lista_de_ferramentas_vazia_repetida_ou_acima_de_10_recusa(self):
        for lista in ([], ["Read", "Read"], FERRAMENTAS + ["TodoWrite", "Bash", "Glob"], "Read", None):
            with self.subTest(lista=lista):
                f = ficha([plugin(agentes=[dict(agente(), ferramentas=lista)])])
                self.assertTrue([c for c in campos(f) if c.startswith("plugins[0].agentes[0].ferramentas")])

    def test_modelo_fora_da_lista_fechada_recusa(self):
        for modelo in ("claude-sonnet-5-5", "Sonnet", "", None, 5, "inherit "):
            with self.subTest(modelo=modelo):
                self.assertEqual(campos(ficha([plugin(agentes=[agente(modelo=modelo)])])),
                                 ["plugins[0].agentes[0].modelo"])
        for modelo in agentes.MODELOS:
            self.assertEqual(erros(ficha([plugin(agentes=[agente(modelo=modelo)])])), [])

    def test_forma_do_agente_campo_a_mais_ou_a_menos_nome_e_hash(self):
        a_mais = dict(agente(), tools=["Bash"])
        sem_modelo = {k: v for k, v in agente().items() if k != "modelo"}
        for ruim in (a_mais, sem_modelo, "redator", None, ["redator"]):
            with self.subTest(agente=str(ruim)[:40]):
                self.assertEqual(campos(ficha([plugin(agentes=[ruim])])), ["plugins[0].agentes[0]"])
        for nome in ("Redator", "redator:x", "../x", "x" * 65, "", None, "-x", "redator "):
            with self.subTest(nome=nome):
                self.assertEqual(campos(ficha([plugin(agentes=[agente(nome=nome)])])), ["plugins[0].agentes[0].nome"])
        for sha in ("A" * 64, "a" * 63, "", None, "g" * 64):
            with self.subTest(sha=sha):
                self.assertEqual(campos(ficha([plugin(agentes=[agente(sha=sha)])])), ["plugins[0].agentes[0].sha256"])
        repetido = campos(ficha([plugin(agentes=[agente(), agente(sha="c" * 64)])]))
        self.assertEqual(repetido, ["plugins[0].agentes[1].nome"])

    def test_agentes_nao_e_lista_ou_passa_de_10_por_plugin(self):
        for valor in ("redator", {"nome": "redator"}, None, 5):
            with self.subTest(valor=str(valor)):
                self.assertEqual(campos(ficha([plugin(agentes=valor)])), ["plugins[0].agentes"])
        onze = [agente(f"agente-{i}", f"{i:x}" * 64) for i in range(11)]
        self.assertEqual(campos(ficha([plugin(agentes=onze)])), ["plugins[0].agentes"])
        dez = [agente(f"agente-{i}", f"{i:x}" * 64) for i in range(10)]
        self.assertEqual(erros(ficha([plugin(agentes=dez)])), [])

    def test_mais_de_20_agentes_na_ficha_recusa(self):
        def com(n):
            return [plugin(nome=f"{PROJETO}-p{i}", agentes=[agente(f"a{j}", "d" * 64) for j in range(n)])
                    for i in range(3)]
        self.assertEqual(erros(ficha(com(6))), [])  # 18
        self.assertEqual(campos(ficha(com(7))), ["plugins"])  # 21

    def test_plugin_com_campo_desconhecido_segue_recusado(self):
        self.assertEqual(campos(ficha([plugin(scripts=[])])), ["plugins[0]"])
        self.assertEqual(campos(ficha([{"nome": PLUGIN, "origem": ORIGEM, "agentes": []}])), ["plugins[0]"])  # sem hash

    def test_ficha_adulterada_nao_derruba_itens_nem_descrever(self):
        for ruim in ({"plugins": [plugin(agentes="x")]}, {"plugins": [plugin(agentes=[5, None, {"nome": 1}])]},
                     {"plugins": "x"}, {"plugins": [5]}):
            with self.subTest(ruim=str(ruim)[:50]):
                regras.itens(ruim)
                regras.descrever(ruim)


class ArquivosDoAgente(unittest.TestCase):
    """O plugin no disco contra o item da ficha: o hash do arquivo, o nome do arquivo e o cabeçalho."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="aberturas-agentes-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.pasta = self.base / "plugins-candidatos" / PLUGIN

    def montar(self, arquivos: dict | None = None) -> None:
        shutil.rmtree(self.pasta, ignore_errors=True)
        padrao = {".claude-plugin/plugin.json": json.dumps({"name": PLUGIN, "description": "Plugin fictício."}),
                  "skills/ola/SKILL.md": "---\nname: ola\ndescription: Olá (fictício).\n---\n\nCorpo.\n",
                  "agents/redator.md": cabecalho(), "agents/revisor.md": cabecalho("revisor", "Read, Grep", "inherit")}
        for rel, texto in {**padrao, **(arquivos or {})}.items():
            if texto is None:
                continue
            alvo = self.pasta.joinpath(*rel.split("/"))
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_bytes(texto.encode("utf-8") if isinstance(texto, str) else texto)

    def sha(self, rel: str) -> str:
        return hashlib.sha256(self.pasta.joinpath(*rel.split("/")).read_bytes()).hexdigest()

    def item(self, lista=None) -> dict:
        res = plugins.conferir_pasta_do_plugin(self.pasta, PLUGIN)
        self.assertEqual(res["erros"], [])
        lista = lista if lista is not None else [agente("redator", self.sha("agents/redator.md")),
                                                 agente("revisor", self.sha("agents/revisor.md"), ["Read", "Grep"],
                                                        "inherit")]
        return {"nome": PLUGIN, "origem": ORIGEM, "manifesto_sha256": res["manifesto_sha256"], "agentes": lista}

    def conferir(self, item: dict) -> dict:
        return plugins.conferir_plugin(self.base, item)

    def motivos(self, item: dict) -> str:
        return " | ".join(f"{e['campo']}: {e['motivo']}" for e in self.conferir(item)["erros"])

    def test_agentes_conformes_valem_e_o_manifesto_continua_o_mesmo(self):
        self.montar()
        item = self.item()
        res = self.conferir(item)
        self.assertEqual(res["erros"], [])
        self.assertEqual(res["manifesto_sha256"], item["manifesto_sha256"])
        sem = {k: v for k, v in item.items() if k != "agentes"}
        self.assertEqual(self.conferir(sem)["manifesto_sha256"], item["manifesto_sha256"])  # a lista não entra no hash

    def test_arquivo_trocado_depois_da_assinatura_recusa(self):
        self.montar()
        item = self.item()
        (self.pasta / "agents" / "redator.md").write_text(cabecalho(extra="maxTurns: 5") + "Outro texto.\n",
                                                          encoding="utf-8")
        texto = self.motivos(item)
        self.assertIn("o plugin mudou desde o manifesto da ficha", texto)  # o manifesto do plugin já acusa
        # mesmo com o manifesto refeito, o hash do agente na ficha não é o do arquivo novo
        novo = plugins.conferir_pasta_do_plugin(self.pasta, PLUGIN)["manifesto_sha256"]
        refeito = dict(item, manifesto_sha256=novo)
        achados = self.conferir(refeito)
        self.assertEqual(len(achados["erros"]), 1)
        self.assertIn("SHA-256 do arquivo difere de agentes[].sha256", achados["erros"][0]["motivo"])
        self.assertEqual(achados["erros"][0]["campo"], f"plugin {PLUGIN}: agents/redator.md")
        # o hash do agente refeito também fecha o caso
        self.assertEqual(self.conferir(dict(refeito, agentes=[agente("redator", self.sha("agents/redator.md"))]))["erros"],
                         [])

    def test_agente_da_ficha_sem_arquivo_ou_com_outro_nome_de_arquivo_recusa(self):
        self.montar()
        item = self.item([agente("fantasma", "e" * 64)])
        self.assertIn("não tem o arquivo agents/<nome>.md", self.motivos(item))
        self.montar({"agents/redator.md": None, "agents/outro-nome.md": cabecalho()})
        item = self.item([agente("redator", self.sha("agents/outro-nome.md"))])
        self.assertIn("não tem o arquivo agents/<nome>.md", self.motivos(item))

    def test_agentes_da_ficha_fora_da_forma_nao_derrubam_a_conferencia(self):
        self.montar()
        for lista in ("redator", [5], [None], [{"nome": ["x"]}], [{"nome": "../x"}]):
            with self.subTest(lista=str(lista)):
                self.assertTrue(self.conferir(self.item(lista))["erros"])

    def test_cabecalho_que_diz_outra_coisa_que_a_ficha_recusa(self):
        casos = {
            "sem tools (herdaria todas as ferramentas)": (cabecalho(tools=None), "sem tools no cabeçalho"),
            "ferramenta a mais no cabeçalho": (cabecalho(tools="Read, Grep, Glob, Write, Edit, Bash"),
                                               "difere de agentes[].ferramentas"),
            "ferramenta a menos no cabeçalho": (cabecalho(tools="Read, Grep"), "difere de agentes[].ferramentas"),
            "ferramenta repetida": (cabecalho(tools="Read, Read, Grep, Glob, Write, Edit"), "difere de agentes"),
            "tools com especificador": (cabecalho(tools="Read, Grep, Glob, Write, Edit(./x)"), "fora do formato simples"),
            "tools com curinga": (cabecalho(tools="Re*"), "fora do formato simples"),
            "tools repetido": (cabecalho(extra="tools: Read"), "tools repetido"),
            "nome diferente": (cabecalho(nome="outro"), "name do cabeçalho ('outro') difere"),
            "modelo diferente": (cabecalho(modelo="opus"), "model do cabeçalho ('opus') difere"),
            "sem modelo (a ficha diz sonnet)": (cabecalho(modelo=None), "model do cabeçalho (None) difere"),
            "modelo com id completo": (cabecalho(modelo="claude-sonnet-5-5"), "difere de agentes[].modelo"),
            "effort fora da lista": (cabecalho(extra="effort: extremo"), "effort do cabeçalho fora da lista"),
            "maxTurns fora da faixa": (cabecalho(extra="maxTurns: 500"), "maxTurns do cabeçalho fora de 1 a 200"),
            "maxTurns zero": (cabecalho(extra="maxTurns: 0"), "maxTurns do cabeçalho fora de 1 a 200"),
            "cor fora da lista": (cabecalho(extra="color: roxinho"), "color do cabeçalho fora da lista"),
            "sem description": (cabecalho().replace("description: Redige a minuta (fictício).\n", ""), "sem description"),
            "sem cabeçalho": ("Só texto, sem cabeçalho.\n", "cabeçalho fora da forma"),
        }
        for nome, (texto, esperado) in casos.items():
            with self.subTest(nome):
                self.montar({"agents/redator.md": texto})
                item = self.item([agente("redator", self.sha("agents/redator.md"))])
                self.assertIn(esperado, self.motivos(item))

    def test_cabecalho_com_inherit_aceita_model_ausente_ou_inherit(self):
        for modelo in (None, "inherit"):
            with self.subTest(modelo=modelo):
                self.montar({"agents/redator.md": cabecalho(modelo=modelo)})
                item = self.item([agente("redator", self.sha("agents/redator.md"), modelo="inherit")])
                self.assertEqual(self.conferir(item)["erros"], [])
        self.montar({"agents/redator.md": cabecalho(modelo="haiku")})
        item = self.item([agente("redator", self.sha("agents/redator.md"), modelo="inherit")])
        self.assertIn("difere de agentes[].modelo", self.motivos(item))

    def test_formas_validas_do_tools_no_cabecalho(self):
        formas = ("Read, Grep, Glob, Write, Edit", "[Read, Grep, Glob, Write, Edit]", '"Read, Grep, Glob, Write, Edit"',
                  "Edit, Write, Glob, Grep, Read  # em outra ordem", "\n  - Read\n  - Grep\n  - Glob\n  - Write\n  - Edit")
        for tools in formas:
            with self.subTest(tools=tools):
                self.montar({"agents/redator.md": cabecalho(tools=tools)})
                item = self.item([agente("redator", self.sha("agents/redator.md"))])
                self.assertEqual(self.conferir(item)["erros"], [], tools)

    def test_cabecalho_com_chave_que_o_kit_ja_recusa_segue_recusado(self):
        for extra in ("permissionMode: bypassPermissions", "mcpServers: x", "hooks: x", "isolation: worktree",
                      "skills: x", "memory: user"):
            with self.subTest(extra=extra):
                self.montar({"agents/redator.md": cabecalho(extra=extra)})
                res = plugins.conferir_pasta_do_plugin(self.pasta, PLUGIN)
                self.assertTrue(res["erros"], extra)

    def test_plugin_sem_agentes_na_ficha_nao_e_afetado(self):
        self.montar({"agents/redator.md": cabecalho(tools=None)})  # sem tools: vale como candidato, o agente fica fechado
        res = plugins.conferir_pasta_do_plugin(self.pasta, PLUGIN)
        item = {"nome": PLUGIN, "origem": ORIGEM, "manifesto_sha256": res["manifesto_sha256"]}
        self.assertEqual(self.conferir(item)["erros"], [])
        self.assertEqual(self.conferir(dict(item, agentes=[]))["erros"], [])


if __name__ == "__main__":
    unittest.main()
