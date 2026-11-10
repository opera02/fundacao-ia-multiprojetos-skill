"""1.7.11, lote A2 (desenho de skills e agentes, §2.3, §2.4 e §3.5): o preparo do host leva ao perfil os agentes de arquivo
e as skills dos plugins da ficha.

O que o lote muda no preparo, com a prova negativa de cada regra:
- a ficha: `plugins[].agentes[]` lido pelo `aberturas_da_ficha` (o validador é o do kit, sem réplica): ferramenta fora da
  lista (Agent, Skill, MCP, especificador, WebFetch sem a abertura na ficha), plugin com agentes sem o prefixo do projeto
  e campo a mais recusam e fecham tudo; o plugin sem agentes segue com a forma de antes;
- o perfil: FUNDACAO_AGENTES e FUNDACAO_SKILLS saem SEMPRE que há ficha válida (a dos agentes vazia e a das skills "-" sem agente nem skill) e nunca sem
  ela, no formato que o `guarda_ferramentas.py` (lote A1) lê (conferido com o próprio guarda); perfil adulterado em
  qualquer um dos dois (agente a mais, ferramenta a mais, skill a mais, variável sumida) é acusado;
- o plugin no disco: arquivo do agente trocado depois da assinatura, ferramenta do cabeçalho fora da ficha e tipo fora
  da lista recusam (`conferir_plugin_da_ficha`, pela regra do kit);
- a abertura: o valor do perfil sai do `aberturas.json` instalado e as skills dele são as da cópia dos plugins na área.
A instalação inteira (canário, cópia dos plugins) só roda no Linux. Só dados fictícios, em pastas temporárias.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from apoio import KIT, SKILL
from test_host_projeto_apoio import (LINUX, carregar_preparo, gravar_ficha_na_caixa)
from test_host_projeto_perfil import RAIZ, Base, resultado_de_ensaio

PROJETO = "caso-real"
PLUGIN = "caso-real-redacao"
REDATOR = {"nome": "redator", "sha256": "a" * 64, "ferramentas": ["Read", "Grep", "Glob", "Write", "Edit"],
           "modelo": "sonnet"}
REVISOR = {"nome": "revisor", "sha256": "b" * 64, "ferramentas": ["Read", "Grep"], "modelo": "inherit"}
VALOR = f"{PLUGIN}:redator=Read|Grep|Glob|Write|Edit,{PLUGIN}:revisor=Read|Grep"


def plugin(nome=PLUGIN, **extra) -> dict:
    return {"nome": nome, "origem": f"plugins-candidatos/{nome}", "manifesto_sha256": "c" * 64, **extra}


def carregar_guarda():
    spec = importlib.util.spec_from_file_location("guarda_ferramentas_a2", SKILL / "assets" / "hooks" /
                                                  "guarda_ferramentas.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class FichaComAgentes(Base):
    def ab(self, plugins, **secoes):
        return self.m.aberturas_da_ficha(resultado_de_ensaio(plugins=plugins, **secoes), PROJETO)

    def test_plugin_com_agentes_vale_e_vai_para_as_aberturas(self):
        ab = self.ab([plugin(agentes=[REDATOR, REVISOR])])
        self.assertTrue(ab["valida"], ab["motivo"])
        self.assertEqual(ab["plugins"][0]["agentes"], [REDATOR, REVISOR])
        self.assertIsNot(ab["plugins"][0]["agentes"][0], REDATOR)  # cópia: a ficha lida não é mexida pelo perfil

    def test_plugin_sem_agentes_ou_com_a_lista_vazia_segue_com_a_forma_de_antes(self):
        for p in (plugin(), plugin(agentes=[])):
            with self.subTest(agentes="agentes" in p):
                ab = self.ab([p])
                self.assertTrue(ab["valida"], ab["motivo"])
                self.assertEqual(ab["plugins"], [{"nome": PLUGIN, "origem": f"plugins-candidatos/{PLUGIN}",
                                                  "manifesto_sha256": "c" * 64}])

    def test_agente_fora_das_regras_da_ficha_fecha_tudo(self):
        ruins = {
            "ferramenta Agent": [dict(REDATOR, ferramentas=["Read", "Agent"])],
            "ferramenta Skill": [dict(REDATOR, ferramentas=["Skill"])],
            "ferramenta MCP": [dict(REDATOR, ferramentas=["mcp__fsn__buscar_clientes"])],
            "especificador": [dict(REDATOR, ferramentas=["Bash(git *)"])],
            "WebFetch sem a abertura": [dict(REDATOR, ferramentas=["Read", "WebFetch"])],
            "WebSearch sem a abertura": [dict(REDATOR, ferramentas=["WebSearch"])],
            "sem ferramentas": [dict(REDATOR, ferramentas=[])],
            "modelo fora da lista": [dict(REDATOR, modelo="claude-sonnet-5-5")],
            "campo a mais": [dict(REDATOR, tools=["Bash"])],
            "nome repetido": [REDATOR, dict(REDATOR, sha256="d" * 64)],
            "hash fora da forma": [dict(REDATOR, sha256="A" * 64)],
        }
        for nome, agentes in ruins.items():
            with self.subTest(nome):
                ab = self.ab([plugin(agentes=agentes)])
                self.assertFalse(ab["valida"], nome)
                self.assertEqual(ab["plugins"], [])

    def test_plugin_com_agentes_sem_o_prefixo_do_projeto_fecha_tudo(self):
        ab = self.ab([plugin("redacao", agentes=[REDATOR])])
        self.assertFalse(ab["valida"])
        self.assertIn("plugins[0].nome", ab["motivo"])
        self.assertTrue(self.ab([plugin("redacao")])["valida"])  # sem agentes, o prefixo segue só como aviso

    def test_webfetch_e_websearch_abrem_pela_ficha(self):
        com = self.ab([plugin(agentes=[dict(REDATOR, ferramentas=["Read", "WebFetch", "WebSearch"])])],
                      rede={"dominios": ["docs.exemplo.com.br"]}, webfetch={"dominios": ["docs.exemplo.com.br"]},
                      websearch=True)
        self.assertTrue(com["valida"], com["motivo"])

    def test_plugin_com_campo_desconhecido_segue_fechando_tudo(self):
        for extra in ({"scripts": []}, {"hooks": []}):  # skills_com_scripts passou a ser conhecida no lote S2
            with self.subTest(extra=extra):
                self.assertFalse(self.ab([plugin(agentes=[REDATOR], **extra)])["valida"])

    def test_forma_do_preparo_recusa_sem_o_kit_o_que_o_guarda_nao_entende(self):
        for ruim in ("redator", [5], [{"nome": "Redator"}], [dict(REDATOR, ferramentas=["Agent"])],
                     [dict(REDATOR, ferramentas=["Read"] * 2)], [dict(REDATOR, modelo="x")],
                     [dict(REDATOR, ferramentas=[f"F{i}" for i in range(11)])], [dict(REDATOR, sha256="x")]):
            with self.subTest(ruim=str(ruim)[:50]):
                with self.assertRaises(self.m.EntradaInvalida):
                    self.m.agentes_do_plugin(PLUGIN, ruim)
        self.assertEqual(self.m.agentes_do_plugin(PLUGIN, None), [])
        self.assertEqual(self.m.agentes_do_plugin(PLUGIN, []), [])


class PerfilComAgentesESkills(Base):
    def ab(self, agentes=(REDATOR, REVISOR), skills=(f"{PLUGIN}:ola",), valida=True):
        base = {**self.m.aberturas_fechadas(), "valida": valida, "skills": list(skills)}
        return {**base, "plugins": [plugin(agentes=copy.deepcopy(list(agentes)))] if agentes is not None else []}

    def test_com_ficha_as_duas_variaveis_saem_no_formato_do_guarda(self):
        ab = self.ab()
        p = self.perfil(aberturas=ab)
        self.assertEqual(p["env"]["FUNDACAO_AGENTES"], VALOR)
        self.assertEqual(p["env"]["FUNDACAO_SKILLS"], f"{PLUGIN}:ola")
        self.assertEqual(self.m.conferir_perfil_wsl(p, RAIZ, PROJETO, aberturas=ab), [])
        guarda = carregar_guarda()  # o formato é o que o guarda do lote A1 lê, bem formado
        agentes, bem_formada = guarda.agentes_de_arquivo(p["env"]["FUNDACAO_AGENTES"])
        self.assertTrue(bem_formada)
        self.assertEqual(agentes, {f"{PLUGIN}:redator": frozenset(REDATOR["ferramentas"]),
                                   f"{PLUGIN}:revisor": frozenset(REVISOR["ferramentas"])})
        skills, bem_formada = guarda.skills_da_ficha(p["env"]["FUNDACAO_SKILLS"])
        self.assertEqual((skills, bem_formada), (frozenset({f"{PLUGIN}:ola"}), True))

    def test_o_guarda_decide_com_o_que_o_preparo_gerou(self):
        """O elo preparo -> guarda: com o perfil gerado, o tipo da ficha passa, a ferramenta fora das do agente, o tipo
        fora da lista, a skill de fora e a pasta fora do projeto são negados (as provas do guarda, no formato real)."""
        guarda = carregar_guarda()
        env = dict(self.perfil(aberturas=self.ab())["env"])
        pasta = f"{RAIZ}/projects/{PROJETO}"

        def decide(nome, tipo="general-purpose", cwd=pasta, subagente=True, **entrada):
            evento = {"tool_name": nome, "tool_input": entrada}
            if subagente:
                evento.update(agent_id="a1", agent_type=tipo, cwd=cwd)
            return guarda.decide(evento, env)
        agente = f"{PLUGIN}:redator"
        self.assertIsNone(decide("Agent", subagente=False, subagent_type=agente, description="d", prompt="p"))
        self.assertIsNotNone(decide("Agent", subagente=False, subagent_type=f"{PLUGIN}:fantasma", description="d",
                                    prompt="p"))
        self.assertIsNotNone(decide("Agent", subagente=False, subagent_type="outro:redator", description="d",
                                    prompt="p"))
        self.assertIsNone(decide("Read", agente))
        self.assertIsNone(decide("Edit", agente))
        self.assertIsNotNone(decide("Bash", agente, command="ls"))  # fora das ferramentas do agente
        self.assertIsNotNone(decide("Read", f"{PLUGIN}:fantasma"))  # tipo fora da lista nega tudo
        self.assertIsNotNone(decide("Read", agente, cwd="/tmp"))  # pasta fora do projeto
        self.assertIsNone(decide("Skill", subagente=False, skill=f"{PLUGIN}:ola"))
        for fora in ("outro:ola", "claude-api", f"{PLUGIN}:intrusa", "ola"):
            self.assertIsNotNone(decide("Skill", subagente=False, skill=fora), fora)

    def test_ficha_valida_sem_agente_nem_skill_leva_agentes_vazia_e_skills_com_traco_e_o_guarda_nega_toda_skill(self):
        for ab in (self.ab(agentes=(), skills=()), self.ab(agentes=None, skills=())):
            with self.subTest(plugins=len(ab["plugins"])):
                p = self.perfil(aberturas=ab)
                self.assertEqual((p["env"]["FUNDACAO_AGENTES"], p["env"]["FUNDACAO_SKILLS"]), ("", "-"))
                self.assertEqual(self.m.conferir_perfil_wsl(p, RAIZ, PROJETO, aberturas=ab), [])
        guarda = carregar_guarda()
        self.assertEqual(guarda.agentes_de_arquivo(""), ({}, True))
        self.assertEqual(guarda.skills_da_ficha("-"), (frozenset(), True))  # F13: o valor que o preparo grava hoje
        self.assertEqual(guarda.skills_da_ficha(""), (frozenset(), True))  # perfis anteriores valem até o novo preparo
        self.assertEqual(self.m.SEM_SKILLS, guarda.SEM_SKILLS)  # o preparo e o guarda dizem o mesmo valor
        self.assertEqual(self.m.valor_das_skills([]), "-")
        self.assertEqual(self.m.valor_das_skills(None), "-")

    def test_sem_ficha_valida_so_a_variavel_das_skills_existe_e_com_traco(self):
        """F8 e F13 da revisão final: o perfil sem ficha válida leva o FUNDACAO_SKILLS "-" (nenhuma skill, valor não vazio:
        o guarda nega toda Skill, em vez de seguir a lista do --tools), e o FUNDACAO_AGENTES não existe."""
        for ab in (self.m.aberturas_fechadas(), self.ab(valida=False)):
            p = self.perfil(aberturas=ab)
            self.assertNotIn("FUNDACAO_AGENTES", p["env"])
            self.assertEqual(p["env"]["FUNDACAO_SKILLS"], "-")
            self.assertEqual(self.m.conferir_perfil_wsl(p, RAIZ, PROJETO, aberturas=ab), [])
            guarda = carregar_guarda()
            self.assertEqual(guarda.skills_da_ficha(p["env"]["FUNDACAO_SKILLS"]), (frozenset(), True))
        p = self.perfil()
        p["env"]["FUNDACAO_AGENTES"] = ""
        achados = self.m.conferir_perfil_wsl(p, RAIZ, PROJETO, aberturas=self.m.aberturas_fechadas())
        self.assertTrue([a for a in achados if "FUNDACAO_AGENTES" in a and "ausente" in a], achados)

    def test_projeto_sem_ficha_o_guarda_nega_a_skill_inclusive_a_plantada_na_subpasta(self):
        """F8: com o perfil gerado sem ficha, a Skill está na lista do --tools mas o guarda a nega por nome."""
        guarda = carregar_guarda()
        env = dict(self.perfil(aberturas=self.m.aberturas_fechadas())["env"])
        self.assertIn("Skill", env["FUNDACAO_FERRAMENTAS"].split(","))
        for nome in ("s", "x", f"{PLUGIN}:ola", "claude-api"):
            with self.subTest(skill=nome):
                evento = {"tool_name": "Skill", "tool_input": {"skill": nome}}
                self.assertEqual(guarda.decide(evento, env)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_sem_ficha_valida_a_variavel_das_skills_ausente_ou_cheia_e_acusada(self):
        """O invariante exige a variável, com ou sem `aberturas` na conferência, e "-" sem ficha válida."""
        fechada = self.m.aberturas_fechadas()
        for aberturas in (fechada, None):
            with self.subTest(aberturas=aberturas is not None):
                p = self.perfil()
                p["env"].pop("FUNDACAO_SKILLS")
                achados = self.m.conferir_perfil_wsl(p, RAIZ, PROJETO, aberturas=aberturas)
                self.assertTrue([a for a in achados if "FUNDACAO_SKILLS" in a and "ausente" in a], achados)
        p = self.perfil()
        p["env"]["FUNDACAO_SKILLS"] = f"{PLUGIN}:ola"
        self.assertTrue(self.m.conferir_perfil_wsl(p, RAIZ, PROJETO, aberturas=fechada))

    def test_perfil_sem_disableSkillShellExecution_falha_no_invariante(self):
        for ab in (self.m.aberturas_fechadas(), self.ab()):
            bom = self.perfil(aberturas=ab)
            self.assertEqual(self.m.conferir_perfil_wsl(bom, RAIZ, PROJETO, aberturas=ab), [])
            for nome, mudanca in (("ausente", lambda p: p.pop("disableSkillShellExecution")),
                                  ("falso", lambda p: p.update(disableSkillShellExecution=False)),
                                  ("texto", lambda p: p.update(disableSkillShellExecution="true"))):
                with self.subTest(nome=nome, ficha=ab["valida"]):
                    p = copy.deepcopy(bom)
                    mudanca(p)
                    achados = self.m.conferir_perfil_wsl(p, RAIZ, PROJETO, aberturas=ab)
                    self.assertTrue([a for a in achados if "disableSkillShellExecution" in a], achados)

    def test_perfil_adulterado_e_acusado(self):
        ab = self.ab()
        bom = self.perfil(aberturas=ab)
        casos = {
            "agente a mais": lambda p: p["env"].update(FUNDACAO_AGENTES=VALOR + f",{PLUGIN}:intruso=Read"),
            "ferramenta a mais no agente": lambda p: p["env"].update(FUNDACAO_AGENTES=VALOR + "|Bash"),
            "agente de outro plugin": lambda p: p["env"].update(FUNDACAO_AGENTES=VALOR.replace(PLUGIN, "outro", 1)),
            "ordem das ferramentas trocada": lambda p: p["env"].update(
                FUNDACAO_AGENTES=VALOR.replace("Read|Grep|Glob", "Grep|Read|Glob")),
            "agente a menos": lambda p: p["env"].update(FUNDACAO_AGENTES=VALOR.split(",")[0]),
            "variável de agentes sumida": lambda p: p["env"].pop("FUNDACAO_AGENTES"),
            "skill a mais": lambda p: p["env"].update(FUNDACAO_SKILLS=f"{PLUGIN}:ola,embutida:qualquer"),
            "skill de outro plugin": lambda p: p["env"].update(FUNDACAO_SKILLS="outro:ola"),
            "variável de skills vazia": lambda p: p["env"].update(FUNDACAO_SKILLS=""),
            "variável de skills com traço havendo skill": lambda p: p["env"].update(FUNDACAO_SKILLS="-"),
            "variável de skills sumida": lambda p: p["env"].pop("FUNDACAO_SKILLS"),
        }
        for nome, mudanca in casos.items():
            with self.subTest(nome):
                p = copy.deepcopy(bom)
                mudanca(p)
                self.assertTrue(self.m.conferir_perfil_wsl(p, RAIZ, PROJETO, aberturas=ab), nome)
        self.assertEqual(self.m.conferir_perfil_wsl(bom, RAIZ, PROJETO, aberturas=ab), [])

    def test_perfil_com_agentes_nao_vale_sem_a_ficha_que_os_abre(self):
        bom = self.perfil(aberturas=self.ab())
        self.assertTrue(self.m.conferir_perfil_wsl(bom, RAIZ, PROJETO, aberturas=self.m.aberturas_fechadas()))
        sem_agentes = self.ab(agentes=())
        self.assertTrue(self.m.conferir_perfil_wsl(bom, RAIZ, PROJETO, aberturas=sem_agentes))

    def test_listas_fora_da_forma_do_guarda_nao_viram_perfil(self):
        gigante = [f"{PLUGIN}:{'s' * 60}{i:04d}" for i in range(200)]  # acima de 8192 caracteres
        with self.assertRaises(self.m.EntradaInvalida):
            self.perfil(aberturas=self.ab(skills=gigante))
        for ruim in (["sem-dois-pontos"], ["a:b:c"], ["a: b"], [f"{PLUGIN}:ola", f"{PLUGIN}:ola"], ["a:"], [":b"]):
            with self.subTest(ruim=ruim):
                with self.assertRaises(self.m.EntradaInvalida):
                    self.perfil(aberturas=self.ab(skills=ruim))
        mais = [dict(REDATOR, nome=f"agente-{i}") for i in range(21)]
        with self.assertRaises(self.m.EntradaInvalida):
            self.perfil(aberturas=self.ab(agentes=mais))


class SkillsDosPlugins(unittest.TestCase):
    def setUp(self):
        self.m = carregar_preparo()
        self.base = Path(tempfile.mkdtemp(prefix="skills-plugins-a2-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)

    def test_skill_pelo_manifesto_e_so_a_pasta_de_skill_com_skill_md(self):
        manifesto = {"skills/ola/SKILL.md": 1, "skills/ola/apoio/guia.md": 1, "skills/zeta/SKILL.md": 1,
                     "skills/sem-skill-md/guia.md": 1, "skills/fundo/a/SKILL.md": 1, "skills/SKILL.md": 1,
                     "skills/com espaco/SKILL.md": 1, "skills/skill-md/skill.md": 1, "agents/redator.md": 1,
                     "commands/ola/SKILL.md": 1, ".claude-plugin/plugin.json": 1}
        self.assertEqual(self.m.skills_do_manifesto(PLUGIN, manifesto), [f"{PLUGIN}:ola", f"{PLUGIN}:zeta"])
        self.assertEqual(self.m.skills_do_manifesto(PLUGIN, {}), [])
        self.assertEqual(self.m.skills_do_manifesto(PLUGIN, None), [])

    def test_skills_da_area_seguem_a_regra_do_manifesto_sem_seguir_ligacao(self):
        area = self.base / "area"
        for rel in ("skills/ola/SKILL.md", "skills/ola/apoio/guia.md", "skills/zeta/SKILL.md", "skills/sem/guia.md",
                    "skills/maiuscula/skill.md" if os.name != "nt" else "skills/outra/guia.md"):
            alvo = area / "plugins" / PLUGIN / rel
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text("x\n", encoding="utf-8")
        (area / "plugins" / PLUGIN / "skills" / "arquivo-solto").write_text("x\n", encoding="utf-8")
        plugins = [{"nome": PLUGIN}, {"nome": "caso-real-ausente"}]
        self.assertEqual(self.m.skills_da_area(area, plugins), [f"{PLUGIN}:ola", f"{PLUGIN}:zeta"])
        try:  # uma skill que é ligação para fora não conta
            (area / "plugins" / PLUGIN / "skills" / "ligada").symlink_to(self.base, target_is_directory=True)
        except (OSError, NotImplementedError):
            return
        self.assertEqual(self.m.skills_da_area(area, plugins), [f"{PLUGIN}:ola", f"{PLUGIN}:zeta"])


class PluginNoDisco(unittest.TestCase):
    """O plugin com agente pela regra do kit, no caminho que o preparo usa (`conferir_plugin_da_ficha`)."""

    def setUp(self):
        self.m = carregar_preparo()
        self.proj = Path(tempfile.mkdtemp(prefix="plugin-agentes-a2-"))
        self.addCleanup(shutil.rmtree, self.proj, ignore_errors=True)
        self.pasta = self.proj / "plugins-candidatos" / PLUGIN

    def montar(self, agente_md: str) -> dict:
        shutil.rmtree(self.pasta, ignore_errors=True)
        for rel, texto in {".claude-plugin/plugin.json": json.dumps({"name": PLUGIN, "version": "0.1.0"}),
                           "skills/ola/SKILL.md": "---\nname: ola\ndescription: ensaio\n---\nx\n",
                           "agents/redator.md": agente_md}.items():
            alvo = self.pasta.joinpath(*rel.split("/"))
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text(texto, encoding="utf-8", newline="\n")
        manifesto = self.m.manifesto_de_arvore(self.pasta, pastas_ignoradas=(), sufixos_ignorados=())
        return {"nome": PLUGIN, "origem": f"plugins-candidatos/{PLUGIN}",
                "manifesto_sha256": self.m.sha256_do_plugin(manifesto)}

    @staticmethod
    def agente_md(tools="Read, Grep, Glob, Write, Edit", modelo="sonnet") -> str:
        return (f"---\nname: redator\ndescription: Redige a minuta (fictício).\ntools: {tools}\nmodel: {modelo}\n---\n\n"
                "Você redige a minuta.\n")

    def conferir(self, item) -> dict:
        return self.m.conferir_plugin_da_ficha(self.proj, item)

    def com_agentes(self, base: dict, **mudanca) -> dict:
        sha = hashlib.sha256((self.pasta / "agents" / "redator.md").read_bytes()).hexdigest()
        return {**base, "agentes": [dict(REDATOR, sha256=sha, **mudanca)]}

    def test_agente_conferido_pelo_kit_vale_e_o_manifesto_e_o_de_antes(self):
        base = self.montar(self.agente_md())
        res = self.conferir(self.com_agentes(base))
        self.assertEqual(res["erros"], [])
        self.assertEqual(res["manifesto_sha256"], base["manifesto_sha256"])
        self.assertTrue(res["manifesto"])

    def test_arquivo_do_agente_trocado_depois_da_assinatura_recusa(self):
        base = self.montar(self.agente_md())
        item = self.com_agentes(base)
        (self.pasta / "agents" / "redator.md").write_text(self.agente_md() + "Instrução nova.\n", encoding="utf-8",
                                                          newline="\n")
        res = self.conferir(item)
        self.assertTrue(res["erros"])
        self.assertEqual(res["manifesto"], {})
        self.assertIsNone(res["manifesto_sha256"])

    def test_ferramenta_do_cabecalho_fora_da_ficha_recusa(self):
        base = self.montar(self.agente_md(tools="Read, Grep, Glob, Write, Edit, Bash"))
        res = self.conferir(self.com_agentes(base))
        self.assertTrue([e for e in res["erros"] if "tools do cabeçalho" in e], res["erros"])
        sem = self.montar(self.agente_md().replace("tools: Read, Grep, Glob, Write, Edit\n", ""))
        self.assertTrue([e for e in self.conferir(self.com_agentes(sem))["erros"] if "sem tools" in e])

    def test_modelo_do_cabecalho_diferente_da_ficha_recusa(self):
        base = self.montar(self.agente_md(modelo="opus"))
        res = self.conferir(self.com_agentes(base))
        self.assertTrue([e for e in res["erros"] if "model do cabeçalho" in e], res["erros"])

    def test_agente_da_ficha_sem_arquivo_recusa(self):
        base = self.montar(self.agente_md())
        item = {**base, "agentes": [dict(REDATOR, nome="fantasma")]}
        self.assertTrue([e for e in self.conferir(item)["erros"] if "não tem o arquivo" in e])


class AberturaDosAgentes(unittest.TestCase):
    """`conferir-abertura`: o valor do perfil sai do aberturas.json instalado, e as skills dele são as da cópia."""

    def setUp(self):
        self.m = carregar_preparo()
        self.area = Path(tempfile.mkdtemp(prefix="abertura-agentes-a2-"))
        self.addCleanup(shutil.rmtree, self.area, ignore_errors=True)
        copia = self.area / "plugins" / PLUGIN / "skills" / "ola"
        copia.mkdir(parents=True)
        (copia / "SKILL.md").write_text("x\n", encoding="utf-8")
        self.instaladas = {"valida": True, "plugins": [{"nome": PLUGIN, "manifesto_sha256": "c" * 64,
                                                       "agentes": copy.deepcopy([REDATOR, REVISOR])}], "skills": [f"{PLUGIN}:ola"]}
        self.perfil = {"env": {"FUNDACAO_AGENTES": VALOR, "FUNDACAO_SKILLS": f"{PLUGIN}:ola"}}
        self.gravar()

    def gravar(self):
        (self.area / "settings.wsl.json").write_text(json.dumps(self.perfil), encoding="utf-8")
        (self.area / "aberturas.json").write_text(json.dumps(self.instaladas), encoding="utf-8")

    def problemas(self) -> list[str]:
        return self.m.problemas_dos_agentes_da_abertura(self.area)

    def test_perfil_igual_ao_aberturas_json_confere(self):
        self.assertEqual(self.problemas(), [])

    def test_cada_divergencia_e_acusada(self):
        casos = {
            "agente a mais no perfil": lambda: self.perfil["env"].update(FUNDACAO_AGENTES=VALOR + f",{PLUGIN}:x=Read"),
            "ferramenta a mais no perfil": lambda: self.perfil["env"].update(FUNDACAO_AGENTES=VALOR + "|Bash"),
            "skill a mais no perfil": lambda: self.perfil["env"].update(FUNDACAO_SKILLS=f"{PLUGIN}:ola,x:y"),
            "variável sumida": lambda: self.perfil["env"].pop("FUNDACAO_SKILLS"),
            "ferramenta a mais no aberturas.json": lambda: self.instaladas["plugins"][0]["agentes"][1].update(
                ferramentas=["Read", "Grep", "Bash"]),
            "skill do aberturas.json sem cópia": lambda: self.instaladas.update(skills=[f"{PLUGIN}:ola", f"{PLUGIN}:z"]),
            "ficha inválida com variável": lambda: self.instaladas.update(valida=False),
        }
        for nome, mudanca in casos.items():
            with self.subTest(nome):
                self.setUp()
                mudanca()
                self.gravar()
                self.assertTrue(self.problemas(), nome)

    def test_skill_a_mais_na_copia_dos_plugins_e_acusada(self):
        extra = self.area / "plugins" / PLUGIN / "skills" / "intrusa"
        extra.mkdir()
        (extra / "SKILL.md").write_text("x\n", encoding="utf-8")
        self.assertTrue([p for p in self.problemas() if "skills do aberturas.json" in p])

    def test_arquivos_ilegiveis_sao_acusados(self):
        (self.area / "aberturas.json").write_text("{", encoding="utf-8")
        self.assertTrue(self.problemas())
        (self.area / "aberturas.json").unlink()
        self.assertTrue(self.problemas())


@unittest.skipUnless(LINUX, "a área do titular é do Ubuntu (WSL2): instalar-projeto só roda no Linux")
class InstalarComAgentes(unittest.TestCase):
    """A instalação inteira (ensaio, sem root): a ficha com agente e a skill do plugin chegam ao perfil, ao
    aberturas.json e à conferência da abertura; agente trocado na cópia root não abre. NÃO RODADO no Windows."""

    def setUp(self):
        from test_host_projeto_area import _Base
        self.caso = _Base("setUp")
        self.caso.setUp()
        self.addCleanup(self.caso.tearDown)

    def test_instalacao_leva_agentes_e_skills_ao_perfil(self):
        c = self.caso
        c.aprovar_canario()
        pasta = c.proj / "plugins-candidatos" / PLUGIN
        texto = PluginNoDisco.agente_md()
        for rel, conteudo in {".claude-plugin/plugin.json": json.dumps({"name": PLUGIN, "version": "0.1.0"}),
                              "skills/ola/SKILL.md": "---\nname: ola\ndescription: ensaio\n---\nx\n",
                              "agents/redator.md": texto}.items():
            alvo = pasta.joinpath(*rel.split("/"))
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text(conteudo, encoding="utf-8", newline="\n")
        manifesto = c.m.manifesto_de_arvore(pasta, pastas_ignoradas=(), sufixos_ignorados=())
        agente = dict(REDATOR, sha256=hashlib.sha256(texto.encode("utf-8")).hexdigest())
        gravar_ficha_na_caixa(c.raiz, PROJETO, {
            "schema_version": "fundacao.ficha_aberturas/1", "ficha_id": "ficha-caso-real-v1", "project_id": PROJETO,
            "versao": 1, "motivo": "ensaio", "consequencias": "ensaio",
            "plugins": [{"nome": PLUGIN, "origem": f"plugins-candidatos/{PLUGIN}",
                         "manifesto_sha256": c.m.sha256_do_plugin(manifesto), "agentes": [agente]}]})
        c.instalar()
        perfil = json.loads((c.area / "settings.wsl.json").read_text(encoding="utf-8"))
        self.assertEqual(perfil["env"]["FUNDACAO_AGENTES"], f"{PLUGIN}:redator=Read|Grep|Glob|Write|Edit")
        self.assertEqual(perfil["env"]["FUNDACAO_SKILLS"], f"{PLUGIN}:ola")
        instaladas = json.loads((c.area / "aberturas.json").read_text(encoding="utf-8"))
        self.assertEqual(instaladas["plugins"][0]["agentes"], [agente])
        self.assertEqual(instaladas["skills"], [f"{PLUGIN}:ola"])
        self.assertEqual(c.m.conferir_abertura(c.raiz, PROJETO, c.area)["problemas"], [])
        copia = c.area / "plugins" / PLUGIN / "agents" / "redator.md"  # agente trocado na cópia root: não abre
        os.chmod(copia, 0o644)
        copia.write_text(texto + "Instrução nova.\n", encoding="utf-8")
        self.assertTrue(c.m.conferir_abertura(c.raiz, PROJETO, c.area)["problemas"])


if __name__ == "__main__":
    unittest.main()
