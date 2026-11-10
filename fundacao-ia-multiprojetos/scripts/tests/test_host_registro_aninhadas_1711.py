"""1.7.11, lote A3 (desenho de skills e agentes, §4.4; provas N-REG-1 e N-REG-2): o registro de negações que só cresce,
os agentes aninhados e o aviso do preparo.

O que o lote muda, com a prova negativa de cada regra:
- `registry/projetos-host.json` no esquema `fundacao.projetos_host/2` (`agentes_negados`), que ainda lê o /1; o que se
  grava é sempre o /2; forma errada, nome fora do padrão e `agentes_negados` fora do /2 recusam;
- o registro só cresce: nenhum caminho tira nome dele (nem uma opção de remoção existe), e a nova rodada com menos
  nomes não apaga os de antes;
- o perfil do Ubuntu e o do Windows negam `Agent(<nome>)` dos agentes aninhados do registro de TODOS os projetos, e a
  conferência do perfil acusa a negação que sumiu;
- `instrucoes_aninhadas` nomeia os agentes (o `name` e o nome do arquivo), e o nome fora do padrão vai para
  `neutralizar`, nunca para o registro;
- o preparo avisa a skill e o agente aninhados fora do registro, cada nome com o comando pronto; com
  `--registrar-aninhadas` os soma na mesma rodada; inventário parcial é aviso, não recusa;
- a skill de plugin com pasta de nome que o guarda não lê (fica fora do FUNDACAO_SKILLS) também sai no aviso.
Os testes do instalar-projeto só rodam no Linux (a área é do Ubuntu); os do PowerShell, só no Windows. Dados fictícios.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from apoio import ENV, SCRIPTS, SKILL
from test_host_projeto_apoio import LINUX, carregar_preparo, gravar_ficha_na_caixa

AJUDANTE = SKILL / "assets" / "host" / "preparo_host.py"
SKILL_MD = "---\nname: {}\ndescription: ensaio\n---\ncorpo\n"
AGENTE_MD = "---\nname: {}\ndescription: ensaio\ntools: Read\n---\ncorpo\n"
NOMES_RUINS = ("com espaco", "a/b", "..", "", "nome\n", "acentuação", "x" * 129, "-comeca", "chave{x}", "a;b", "a b\u202e")


def rodar(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(AJUDANTE), *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=ENV, timeout=120, stdin=subprocess.DEVNULL)


def escrever(pasta: Path, rel: str, texto: str) -> None:
    alvo = pasta.joinpath(*rel.split("/"))
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(texto, encoding="utf-8", newline="\n")


def com_aninhadas(raiz: Path, projeto: str = "caso-real") -> None:
    """A skill `scrapling-juridico` e o agente `revisor-arquivo` (que se chama `revisor-externo` no cabeçalho) numa pasta
    de dados do projeto."""
    dados = raiz / "projects" / projeto / "data"
    escrever(dados, ".claude/skills/scrapling-juridico/SKILL.md", SKILL_MD.format("scrapling-juridico"))
    escrever(dados, ".claude/agents/revisor-arquivo.md", AGENTE_MD.format("revisor-externo"))


class Base(unittest.TestCase):
    def setUp(self):
        self.m = carregar_preparo()
        self.base = Path(tempfile.mkdtemp(prefix="registro-a3-")).resolve()
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.raiz = self.base / "Fundacao Ensaio"
        for nome in ("caso-real", "lab-a"):
            (self.raiz / "projects" / nome).mkdir(parents=True)
        self.origem = self.base / "Origem Registrada"
        self.origem.mkdir()
        self.arquivo = self.raiz / "registry" / "projetos-host.json"

    def registro(self) -> dict:
        return json.loads(self.arquivo.read_text(encoding="utf-8"))

    def nomes(self, chave: str) -> set:
        return {n for i in self.registro()["projetos"].values() for n in i[chave]}


class EsquemaEQueSoCresce(Base):
    def test_le_o_esquema_1_e_grava_o_2_sem_perder_nada(self):
        antigo = {"schema_version": "fundacao.projetos_host/1", "projetos": {"caso-real": {
            "origens": [str(self.origem)], "somente_leitura": [], "aninhadas_negadas": ["squad-a"]}}}
        escrever(self.raiz, "registry/projetos-host.json", json.dumps(antigo))
        lido = self.m.ler_projetos_host(self.raiz)
        self.assertEqual(lido["schema_version"], "fundacao.projetos_host/2")
        self.assertEqual(lido["projetos"]["caso-real"]["agentes_negados"], [])
        self.assertEqual(self.m.vagas_do_registro(lido, "caso-real")["negar"], ["squad-a"])
        self.m.registrar_projeto(self.raiz, "lab-a", [str(self.origem)], negar_agente=["revisor-x"])
        gravado = self.registro()
        self.assertEqual(gravado["schema_version"], "fundacao.projetos_host/2")
        self.assertEqual(gravado["projetos"]["caso-real"]["aninhadas_negadas"], ["squad-a"])
        self.assertEqual(gravado["projetos"]["lab-a"]["agentes_negados"], ["revisor-x"])
        importar = importlib.util.spec_from_file_location("_importar_a3", SCRIPTS / "importar.py")
        modulo = importlib.util.module_from_spec(importar)
        importar.loader.exec_module(modulo)
        for esquema in ("1", "2"):  # o importar lê as origens dos dois
            escrever(self.raiz, "registry/projetos-host.json",
                     json.dumps({**antigo, "schema_version": "fundacao.projetos_host/" + esquema}))
            self.assertIn("caso-real", modulo.ler_registro_de_origens(self.raiz)["projetos"])

    def test_forma_do_esquema_2_e_recusada(self):
        item = {"origens": [], "somente_leitura": [], "aninhadas_negadas": [], "agentes_negados": []}
        ruins = {"2 sem agentes_negados": ("2", {k: v for k, v in item.items() if k != "agentes_negados"}),
                 "1 com agentes_negados": ("1", item),
                 "agentes_negados não lista": ("2", {**item, "agentes_negados": "revisor"}),
                 "nome com espaço": ("2", {**item, "agentes_negados": ["com espaco"]}),
                 "nome com quebra de linha": ("2", {**item, "agentes_negados": ["revisor\n"]}),
                 "skill com quebra de linha": ("2", {**item, "aninhadas_negadas": ["squad\n"]}),
                 "chave a mais": ("2", {**item, "extra": []}),
                 "esquema 3": ("3", item)}
        for nome, (esquema, valor) in ruins.items():
            with self.subTest(nome):
                escrever(self.raiz, "registry/projetos-host.json", json.dumps(
                    {"schema_version": "fundacao.projetos_host/" + esquema, "projetos": {"caso-real": valor}}))
                with self.assertRaises(ValueError):
                    self.m.ler_projetos_host(self.raiz)

    def test_o_registro_so_cresce(self):
        self.m.registrar_projeto(self.raiz, "caso-real", [str(self.origem)], negar=["squad-a"], negar_agente=["ag-a"])
        self.m.registrar_aninhadas(self.raiz, "lab-a", ["squad-b"], ["ag-b"])
        antes = self.registro()
        bruto = self.arquivo.read_bytes()
        # tirar nome: nenhuma chamada o faz, e a mesma rodada sem novidade nem reescreve o arquivo
        self.m.registrar_projeto(self.raiz, "caso-real", [str(self.origem)], negar=[], negar_agente=[])
        self.m.registrar_aninhadas(self.raiz, "lab-a", [], [])
        self.m.registrar_aninhadas(self.raiz, "lab-a", ["squad-b"], ["ag-b"])
        self.assertEqual(self.arquivo.read_bytes(), bruto)
        self.m.registrar_aninhadas(self.raiz, "caso-real", ["squad-c"], [])
        depois = self.registro()
        self.assertEqual(depois["projetos"]["caso-real"]["aninhadas_negadas"], ["squad-a", "squad-c"])
        self.assertEqual(depois["projetos"]["caso-real"]["agentes_negados"], ["ag-a"])
        self.assertEqual(depois["projetos"]["lab-a"], antes["projetos"]["lab-a"])
        for opcao in ("--remover-agente", "--tirar-skill", "--limpar-negadas", "--substituir"):
            with self.subTest(opcao):
                r = rodar("registrar-projeto", "--raiz", self.raiz, "--projeto", "caso-real", "--origem", self.origem,
                          opcao, "ag-a")
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)  # a opção não existe
        self.assertEqual(self.registro(), depois)

    def test_nome_fora_do_padrao_nao_entra_no_registro(self):
        for ruim in NOMES_RUINS:
            with self.subTest(repr(ruim)):
                for chamada in (lambda: self.m.registrar_projeto(self.raiz, "caso-real", [str(self.origem)],
                                                                 negar_agente=["bom", ruim]),
                                lambda: self.m.registrar_projeto(self.raiz, "caso-real", [str(self.origem)],
                                                                 negar=["bom", ruim]),
                                lambda: self.m.registrar_aninhadas(self.raiz, "caso-real", [ruim], ["bom"]),
                                lambda: self.m.registrar_aninhadas(self.raiz, "caso-real", ["bom"], [ruim])):
                    with self.assertRaises(self.m.EntradaInvalida):
                        chamada()
                    self.assertFalse(self.arquivo.exists())  # nada gravado, nem o "bom" que vinha junto
        r = rodar("registrar-projeto", "--raiz", self.raiz, "--projeto", "caso-real", "--origem", self.origem,
                  "--negar-agente", "com espaco")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertFalse(self.arquivo.exists())

    def test_nome_com_dois_pontos_ou_de_agente_embutido_nao_entra_no_registro(self):
        """F9 da revisão final da 1.7.11: o registro vale para todos os projetos; ':' é o separador de <plugin>:<nome> da
        ficha, e o nome de agente embutido fecharia o embutido em todo perfil. Recusa sem gravar nada."""
        embutidos = self.m.AGENTES_EMBUTIDOS
        self.assertEqual(set(embutidos), {"general-purpose", "web-fetch", "Explore", "Plan"})
        casos = [("agente", n) for n in embutidos] + [("agente", "p:a"), ("skill", "a:b"), ("skill", "plugin:skill")]
        for rotulo, ruim in casos:
            with self.subTest(rotulo=rotulo, nome=ruim):
                chave = {"negar_agente": ["bom", ruim]} if rotulo == "agente" else {"negar": ["bom", ruim]}
                with self.assertRaises(self.m.EntradaInvalida) as e:
                    self.m.registrar_projeto(self.raiz, "caso-real", [str(self.origem)], **chave)
                self.assertIn("neutralize", str(e.exception))
                nomes = ([], ["bom", ruim]) if rotulo == "agente" else (["bom", ruim], [])
                with self.assertRaises(self.m.EntradaInvalida):
                    self.m.registrar_aninhadas(self.raiz, "caso-real", *nomes)
                self.assertFalse(self.arquivo.exists())  # nada gravado, nem o "bom" que vinha junto
        for opcao, ruim in (("--negar-agente", "general-purpose"), ("--negar-skill", "a:b"), ("--negar-agente", "x:y")):
            r = rodar("registrar-projeto", "--raiz", self.raiz, "--projeto", "caso-real", "--origem", self.origem,
                      opcao, ruim)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertFalse(self.arquivo.exists())
        # skill com nome de agente embutido, ou agente com nome parecido: seguem valendo
        self.m.registrar_projeto(self.raiz, "caso-real", [str(self.origem)], negar=["general-purpose"],
                                 negar_agente=["general-purpose-2", "explore"])
        self.assertEqual(self.nomes("agentes_negados"), {"general-purpose-2", "explore"})

    def test_a_lista_de_embutidos_e_a_do_guarda(self):
        spec = importlib.util.spec_from_file_location("_guarda_f9", SKILL / "assets" / "hooks" / "guarda_ferramentas.py")
        guarda = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guarda)
        self.assertEqual(set(self.m.AGENTES_EMBUTIDOS), set(guarda.TIPOS_DO_AGENTE))

    def test_linha_de_comando_registra_e_le_os_agentes(self):
        r = rodar("registrar-projeto", "--raiz", self.raiz, "--projeto", "caso-real", "--origem", self.origem,
                  "--negar-skill", "squad-a", "--negar-agente", "ag-a", "--negar-agente", "ag-b")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["agentes_negados"], ["ag-a", "ag-b"])
        r = rodar("ler-projetos-host", "--raiz", self.raiz, "--projeto", "lab-a")
        self.assertEqual(json.loads(r.stdout)["agentes_negados"], [])
        r = rodar("fora-do-registro", "--raiz", self.raiz, "--negar-agente", "ag-a", "--negar-agente", "ag-z")
        self.assertEqual(json.loads(r.stdout)["negar_agente"], ["ag-z"])


class PerfilNegaOsAgentes(Base):
    RAIZ = "/mnt/e/Fundacao Exemplo"

    def kw(self, **extra):
        return {**dict(raiz=r"E:\Fundacao Exemplo", projeto="caso-real", perfil_windows=r"C:\Users\<usuario>",
                       outros_projetos=["lab-a"], negar=["squad-x"], negar_agente=["revisor-externo"]), **extra}

    def test_perfil_do_ubuntu_nega_agent_e_a_conferencia_acusa_a_falta(self):
        perfil = self.m.perfil_wsl(**self.kw())
        deny = perfil["permissions"]["deny"]
        self.assertIn("Agent(revisor-externo)", deny)
        self.assertIn("Skill(squad-x)", deny)
        self.assertEqual(self.m.conferir_perfil_wsl(perfil, self.RAIZ, "caso-real", ["lab-a"]), [])  # lê do perfil
        self.assertEqual(self.m.conferir_perfil_wsl(perfil, self.RAIZ, "caso-real", ["lab-a"],
                                                    negar_agente=["revisor-externo"]), [])
        tirado = json.loads(json.dumps(perfil))
        tirado["permissions"]["deny"].remove("Agent(revisor-externo)")
        problemas = self.m.conferir_perfil_wsl(tirado, self.RAIZ, "caso-real", ["lab-a"],
                                               negar_agente=["revisor-externo"])  # o do registro, o confiável
        self.assertTrue(any("perfil diferente" in p for p in problemas), problemas)
        with self.assertRaises(self.m.EntradaInvalida):
            self.m.perfil_wsl(**self.kw(negar_agente=["com espaco"]))

    def test_perfil_do_windows_nega_agent(self):
        perfil = self.m.perfil_windows(raiz=r"E:\Fundacao Exemplo", python=r"C:\Python\python.exe", projeto="caso-real",
                                       negar=["squad-x"], negar_agente=["revisor-externo", "revisor-externo"])
        self.assertEqual(perfil["permissions"]["deny"].count("Agent(revisor-externo)"), 1)

    def test_negacao_de_agente_vale_para_todos_os_projetos(self):
        self.m.registrar_aninhadas(self.raiz, "lab-a", ["squad-b"], ["ag-b"])
        self.m.registrar_aninhadas(self.raiz, "caso-real", [], ["ag-a", "ag-b"])
        vagas = self.m.vagas_do_registro(self.m.ler_projetos_host(self.raiz), "caso-real")
        self.assertEqual((vagas["negar"], vagas["negar_agente"]), (["squad-b"], ["ag-a", "ag-b"]))
        outras = self.m.vagas_do_registro(self.m.ler_projetos_host(self.raiz), "projeto-sem-registro")
        self.assertEqual(outras["negar_agente"], ["ag-a", "ag-b"])


class AninhadasForaDoRegistro(Base):
    def registrar_o_projeto(self) -> None:
        """O projeto já no registro, com a origem: condição para somar as aninhadas (lote S2)."""
        self.m.registrar_projeto(self.raiz, "caso-real", [str(self.origem)])

    def test_registrar_de_projeto_fora_do_registro_recusa_com_o_comando_pronto_e_nada_grava(self):
        com_aninhadas(self.raiz)
        for simular in (True, False):
            with self.subTest(simular=simular):
                with self.assertRaises(self.m.EntradaInvalida) as e:
                    self.m.aninhadas_fora_do_registro(self.raiz, "caso-real", registrar=True, simular=simular)
                for trecho in ("ainda não está no registro", "registrar-projeto", "--origem", "scrapling-juridico",
                               "--negar-agente"):
                    self.assertIn(trecho, str(e.exception))
                self.assertFalse(self.arquivo.exists())
        r = rodar("aninhadas-fora-do-registro", "--raiz", self.raiz, "--projeto", "caso-real", "--registrar")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("registrar-projeto", json.loads(r.stdout)["erro"])
        self.assertFalse(self.arquivo.exists())
        self.m.aninhadas_fora_do_registro(self.raiz, "caso-real")  # só conferir (sem registrar) segue valendo
    def test_agentes_ganham_nome_do_cabecalho_e_do_arquivo(self):
        com_aninhadas(self.raiz)
        escrever(self.raiz / "projects" / "caso-real", "data/.claude/agents/Estranho.md", AGENTE_MD.format("Nome com espaço"))
        inst = SCRIPTS / "instrucoes_aninhadas.py"
        spec = importlib.util.spec_from_file_location("_inst_a3", inst)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        res = modulo.listar(self.raiz / "projects" / "caso-real")
        self.assertEqual(res["sugestoes"]["negar_agentes"], ["Estranho", "revisor-arquivo", "revisor-externo"])
        self.assertEqual(res["sugestoes"]["negacoes_agentes"][0], "Agent(Estranho)")
        fora = res["agentes_fora_do_padrao"]
        self.assertEqual([(i["nome"], i["negar_pelo_arquivo"]) for i in fora], [("Nome com espaço", "Estranho")])
        self.assertIn("data/.claude/agents/Estranho.md", res["neutralizar"])  # o ARQUIVO do agente
        self.assertFalse(any("Nome com" in n for n in res["sugestoes"]["negar_agentes"]))

    def test_n_reg_1_e_2_avisa_com_o_comando_pronto_e_nao_grava(self):
        com_aninhadas(self.raiz)
        self.m.registrar_projeto(self.raiz, "lab-a", [str(self.origem)])
        antes = self.arquivo.read_bytes()
        res = self.m.aninhadas_fora_do_registro(self.raiz, "caso-real")
        self.assertEqual((res["skills"], res["agentes"]), (["scrapling-juridico"], ["revisor-arquivo", "revisor-externo"]))
        texto = "\n".join(res["avisos"])
        for trecho in ("scrapling-juridico", "revisor-externo", "registrar-projeto", "--negar-skill", "--negar-agente",
                       "--registrar-aninhadas"):
            self.assertIn(trecho, texto)
        self.assertIn("--origem '<pasta de origem do projeto>'", res["comando"])  # o projeto ainda não tem origem
        self.assertEqual(self.arquivo.read_bytes(), antes)  # só avisou
        self.m.registrar_projeto(self.raiz, "caso-real", [str(self.origem)])
        self.assertIn(str(self.origem), self.m.aninhadas_fora_do_registro(self.raiz, "caso-real")["comando"])

    def test_registrar_aninhadas_soma_na_mesma_rodada_e_nada_sai(self):
        com_aninhadas(self.raiz)
        self.registrar_o_projeto()
        self.m.registrar_projeto(self.raiz, "lab-a", [str(self.origem)], negar=["squad-antiga"], negar_agente=["ag-a"])
        simulada = self.m.aninhadas_fora_do_registro(self.raiz, "caso-real", registrar=True, simular=True)
        self.assertIsNone(simulada["registrado"])
        self.assertNotIn("scrapling-juridico", self.nomes("aninhadas_negadas"))  # simular não grava
        res = self.m.aninhadas_fora_do_registro(self.raiz, "caso-real", registrar=True)
        self.assertEqual(res["registrado"], {"skills": ["scrapling-juridico"], "agentes": ["revisor-arquivo", "revisor-externo"]})
        self.assertIn("somados ao registro", "\n".join(res["avisos"]))
        self.assertEqual(self.nomes("aninhadas_negadas"), {"squad-antiga", "scrapling-juridico"})
        self.assertEqual(self.nomes("agentes_negados"), {"ag-a", "revisor-arquivo", "revisor-externo"})
        depois = self.arquivo.read_bytes()
        outra = self.m.aninhadas_fora_do_registro(self.raiz, "caso-real", registrar=True)  # nada novo
        self.assertEqual((outra["skills"], outra["agentes"], outra["avisos"]), ([], [], []))
        self.assertEqual(self.arquivo.read_bytes(), depois)

    def test_nome_fora_do_padrao_vai_para_neutralizar_e_nunca_para_o_registro(self):
        raiz_dados = self.raiz / "projects" / "caso-real" / "data"
        escrever(raiz_dados, ".claude/skills/Skill Estranha/SKILL.md", SKILL_MD.format("Skill Estranha"))
        escrever(raiz_dados, ".claude/agents/ok.md", AGENTE_MD.format("Agente Estranho"))
        self.registrar_o_projeto()
        res = self.m.aninhadas_fora_do_registro(self.raiz, "caso-real", registrar=True)
        self.assertEqual((res["skills"], res["agentes"]), ([], ["ok"]))  # só o que se aceita (o nome do arquivo)
        self.assertEqual(len(res["fora_do_padrao"]), 1)
        self.assertEqual(len(res["agentes_fora_do_padrao"]), 1)
        self.assertIn("data/.claude/skills/Skill Estranha", res["neutralizar"])
        self.assertIn("data/.claude/agents/ok.md", res["neutralizar"])
        self.assertTrue(any("neutralize" in a and "fora do padrão" in a for a in res["avisos"]), res["avisos"])
        self.assertEqual((self.nomes("aninhadas_negadas"), self.nomes("agentes_negados")), (set(), {"ok"}))

    def test_nome_que_o_registro_recusa_vai_para_neutralizar_e_nao_para_o_comando(self):
        """F9: a skill com ':' no nome e o agente com nome de embutido, achados na aninhada, não entram em `skills` nem em
        `agentes` (nem no comando pronto, nem no --registrar-aninhadas): vão para `nao_registraveis` e `neutralizar`."""
        dados = self.raiz / "projects" / "caso-real" / "data"
        escrever(dados, ".claude/skills/boa/SKILL.md", SKILL_MD.format("boa"))
        escrever(dados, ".claude/skills/capa/SKILL.md", SKILL_MD.format("outro-plugin:skill"))
        escrever(dados, ".claude/agents/general-purpose.md", AGENTE_MD.format("general-purpose"))
        escrever(dados, ".claude/agents/disfarce.md", AGENTE_MD.format("Explore"))
        self.registrar_o_projeto()
        antes = self.m.aninhadas_fora_do_registro(self.raiz, "caso-real")
        self.assertEqual(len(antes["avisos_de_recusa"]), 2)  # o que falta no registro e o que o registro recusa
        self.assertNotIn("general-purpose", antes["comando"])
        self.assertNotIn("outro-plugin:skill", antes["comando"])
        res = self.m.aninhadas_fora_do_registro(self.raiz, "caso-real", registrar=True)
        self.assertEqual((res["skills"], res["agentes"]), (["boa", "capa"], ["disfarce"]))
        achados = {(i["tipo"], i["nome"]): i["caminho"] for i in res["nao_registraveis"]}
        self.assertEqual(achados, {("skill", "outro-plugin:skill"): "data/.claude/skills/capa",
                                   ("agente", "general-purpose"): "data/.claude/agents/general-purpose.md",
                                   ("agente", "Explore"): "data/.claude/agents/disfarce.md"})
        for caminho in achados.values():
            self.assertIn(caminho, res["neutralizar"])
        self.assertEqual((self.nomes("aninhadas_negadas"), self.nomes("agentes_negados")),
                         ({"boa", "capa"}, {"disfarce"}))
        self.assertTrue(any("neutralize o arquivo" in a and "general-purpose" in a for a in res["avisos"]), res["avisos"])

    def test_inventario_parcial_e_aviso_nao_recusa(self):
        com_aninhadas(self.raiz)
        escrever(self.raiz / "projects" / "caso-real", "node_modules/x.txt", "x\n")  # pasta pulada: parcial
        self.registrar_o_projeto()
        res = self.m.aninhadas_fora_do_registro(self.raiz, "caso-real", registrar=True)
        self.assertFalse(res["completo"])
        self.assertTrue(any("parcial" in a for a in res["avisos"]))
        self.assertEqual(self.nomes("aninhadas_negadas"), {"scrapling-juridico"})  # os nomes lidos entram
        sem = self.m.aninhadas_fora_do_registro(self.raiz, "projeto-que-nao-existe")
        self.assertFalse(sem["conferido"])  # a pasta não existe: aviso, sem exceção
        self.assertIn("NÃO conferidos", sem["avisos"][0])

    def test_f8_inventario_parcial_recusa_a_abertura_so_com_a_ferramenta_agent_aberta(self):
        """3ª passada, F8: a sessão torna o inventário parcial (pasta de nome ignorado) e põe um agente onde ele não vê. Com a
        ferramenta Agent aberta no perfil a abertura recusa; sem ela, continua só aviso (o `res` fica o mesmo)."""
        com_aninhadas(self.raiz)
        escrever(self.raiz / "projects" / "caso-real", "node_modules/agents/x.md", AGENTE_MD.format("plantado"))
        self.registrar_o_projeto()
        self.m.aninhadas_fora_do_registro(self.raiz, "caso-real", registrar=True)   # o que se vê está registrado
        problemas, avisos = self.m._aninhadas_na_abertura(self.raiz, "caso-real", True)
        self.assertEqual(len(problemas), 1, problemas)
        for trecho in ("parcial", "ferramenta Agent", "pasta de nome ignorado", "a abertura não segue"):
            self.assertIn(trecho, problemas[0])
        self.assertEqual([a for a in avisos if "parcial" in a], [])
        problemas, avisos = self.m._aninhadas_na_abertura(self.raiz, "caso-real", False)   # sem a ferramenta Agent: só aviso
        self.assertEqual(problemas, [])
        self.assertEqual(len([a for a in avisos if "parcial" in a]), 1)
        problemas, _ = self.m._aninhadas_na_abertura(self.raiz, "caso-real")   # o padrão da função é não recusar
        self.assertEqual(problemas, [])
        (self.raiz / "projects" / "caso-real" / "node_modules" / "agents" / "x.md").unlink()
        (self.raiz / "projects" / "caso-real" / "node_modules" / "agents").rmdir()
        (self.raiz / "projects" / "caso-real" / "node_modules").rmdir()
        self.assertEqual(self.m._aninhadas_na_abertura(self.raiz, "caso-real", True), ([], []))   # completo: nada a recusar

    def test_sem_o_comando_pronto_o_aviso_ainda_diz_o_que_fazer(self):
        """O comando é um auxílio: se a citação para o terminal não carrega, os nomes e o --registrar-aninhadas ficam."""
        com_aninhadas(self.raiz)
        real = self.m._carregar_script

        def sem_citacao(nome):
            if nome == "codigo_do_plano":
                raise OSError("ausente")
            return real(nome)

        with unittest.mock.patch.object(self.m, "_carregar_script", sem_citacao):
            res = self.m.aninhadas_fora_do_registro(self.raiz, "caso-real")
        self.assertIsNone(res["comando"])
        texto = "\n".join(res["avisos"])
        self.assertIn("scrapling-juridico", texto)
        self.assertIn("--registrar-aninhadas", texto)

    def test_listar_sai_com_1_quando_o_agente_tem_nome_fora_do_padrao(self):
        pasta = self.raiz / "projects" / "caso-real"
        com_aninhadas(self.raiz)
        comando = [sys.executable, "-B", str(SCRIPTS / "instrucoes_aninhadas.py"), "listar", "--raiz", str(pasta)]
        kw = dict(capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, timeout=120,
                  stdin=subprocess.DEVNULL)
        self.assertEqual(subprocess.run(comando, **kw).returncode, 0)
        escrever(pasta, "data/.claude/agents/ok.md", AGENTE_MD.format("Agente Estranho"))
        self.assertEqual(subprocess.run(comando, **kw).returncode, 1)

    def test_linha_de_comando(self):
        com_aninhadas(self.raiz)
        r = rodar("aninhadas-fora-do-registro", "--raiz", self.raiz, "--projeto", "caso-real")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["skills"], ["scrapling-juridico"])
        self.assertFalse(self.arquivo.exists())
        self.registrar_o_projeto()
        r = rodar("aninhadas-fora-do-registro", "--raiz", self.raiz, "--projeto", "caso-real", "--registrar")
        self.assertEqual(json.loads(r.stdout)["registrado"]["skills"], ["scrapling-juridico"])
        self.assertEqual(self.nomes("agentes_negados"), {"revisor-arquivo", "revisor-externo"})
        self.assertEqual(rodar("aninhadas-fora-do-registro", "--raiz", self.raiz, "--projeto", "..").returncode, 2)


class SkillsDePluginForaDoGuarda(Base):
    def test_pasta_que_o_guarda_nao_le_e_apontada(self):
        manifesto = {"skills/ola/SKILL.md": 1, "skills/com espaco/SKILL.md": 1, "skills/" + "x" * 65 + "/SKILL.md": 1,
                     "skills/sem-skill-md/guia.md": 1, "agents/redator.md": 1}
        self.assertEqual(self.m.skills_fora_do_guarda("caso-real-p", manifesto),
                         ["caso-real-p:com espaco", "caso-real-p:" + "x" * 65])
        self.assertEqual(self.m.skills_do_manifesto("caso-real-p", manifesto), ["caso-real-p:ola"])
        self.assertEqual(self.m.skills_fora_do_guarda("caso-real-p", {}), [])


@unittest.skipUnless(LINUX, "a área do titular é do Ubuntu (WSL2): instalar-projeto só roda no Linux. NÃO RODADO no Windows")
class InstalarProjetoAvisaEregistra(unittest.TestCase):
    def setUp(self):
        from test_host_projeto_area import _Base
        self.caso = _Base("setUp")
        self.caso.setUp()
        self.addCleanup(self.caso.tearDown)
        self.registro = self.caso.raiz / "registry" / "projetos-host.json"
        com_aninhadas(self.caso.raiz)

    def deny(self) -> list:
        perfil = json.loads((self.caso.area / "settings.wsl.json").read_text(encoding="utf-8"))
        return perfil["permissions"]["deny"]

    def test_avisa_a_skill_e_o_agente_aninhados_fora_do_registro(self):
        rel = self.caso.instalar()
        texto = "\n".join(rel["avisos"])
        for trecho in ("scrapling-juridico", "revisor-externo", "registrar-projeto", "--negar-agente"):
            self.assertIn(trecho, texto)
        self.assertEqual(rel["aninhadas"]["skills"], ["scrapling-juridico"])
        self.assertFalse(self.registro.exists())
        self.assertNotIn("Agent(revisor-externo)", self.deny())

    def registrar_o_projeto(self) -> None:
        """O projeto já no registro, com a origem (o `registrar-projeto`): condição para o --registrar-aninhadas."""
        origem = self.caso.base / "Origem Registrada"
        origem.mkdir()
        self.caso.m.registrar_projeto(self.caso.raiz, "caso-real", [str(origem)])

    def test_registrar_aninhadas_de_projeto_fora_do_registro_recusa_com_o_comando_pronto(self):
        """Lote S2 (A3): o registro não nasce só com os nomes (entrava com as origens vazias): recusa, na simulação e na
        execução real, e o erro traz o comando do registrar-projeto com a origem a preencher."""
        for simular in (True, False):
            with self.subTest(simular=simular):
                erro = self.caso.instalar("--registrar-aninhadas", simular=simular, codigo=2)["erro"]
                for trecho in ("ainda não está no registro", "registrar-projeto", "--origem", "--negar-skill",
                               "scrapling-juridico", "--negar-agente"):
                    self.assertIn(trecho, erro)
                self.assertFalse(self.registro.exists())
                self.assertFalse((self.caso.base / "area" / "projetos").exists())
        self.caso.instalar()  # sem a opção, só avisa (como antes)

    def test_registrar_aninhadas_sem_nada_a_registrar_nao_exige_o_registro(self):
        shutil.rmtree(self.caso.proj / "data")  # projeto sem skill nem agente aninhados (fluxo A, sem origem)
        rel = self.caso.instalar("--registrar-aninhadas")
        self.assertIsNone(rel["aninhadas"]["registrado"])
        self.assertFalse(self.registro.exists())

    def test_registrar_aninhadas_soma_ao_registro_e_o_perfil_ja_nega(self):
        self.registrar_o_projeto()
        antes = self.registro.read_bytes()
        simulada = self.caso.instalar("--registrar-aninhadas", simular=True)
        self.assertEqual(self.registro.read_bytes(), antes)  # a simulação não grava
        self.assertIn("execução real", "\n".join(simulada["avisos"]))
        rel = self.caso.instalar("--registrar-aninhadas")
        self.assertEqual(rel["aninhadas"]["registrado"]["agentes"], ["revisor-arquivo", "revisor-externo"])
        dados = json.loads(self.registro.read_text(encoding="utf-8"))["projetos"]["caso-real"]
        self.assertEqual(dados["aninhadas_negadas"], ["scrapling-juridico"])
        deny = self.deny()
        for regra in ("Skill(scrapling-juridico)", "Agent(revisor-arquivo)", "Agent(revisor-externo)"):
            self.assertIn(regra, deny)
        segunda = self.caso.instalar()  # já registrado: nenhum aviso de falta
        self.assertNotIn("FORA do registro", "\n".join(segunda["avisos"]))
        self.assertEqual(json.loads(self.registro.read_text(encoding="utf-8"))["projetos"]["caso-real"], dados)

    def test_skill_de_plugin_com_pasta_que_o_guarda_nao_le_sai_no_aviso(self):
        import test_host_projeto_agentes as a2
        c = self.caso
        c.aprovar_canario()
        pasta = c.proj / "plugins-candidatos" / a2.PLUGIN
        texto = a2.PluginNoDisco.agente_md()
        for rel, conteudo in {".claude-plugin/plugin.json": json.dumps({"name": a2.PLUGIN, "version": "0.1.0"}),
                              "skills/ola/SKILL.md": "---\nname: ola\ndescription: ensaio\n---\nx\n",
                              "skills/com espaco/SKILL.md": "---\nname: x\ndescription: ensaio\n---\nx\n",
                              "agents/redator.md": texto}.items():
            escrever(pasta, rel, conteudo)
        import hashlib
        manifesto = c.m.manifesto_de_arvore(pasta, pastas_ignoradas=(), sufixos_ignorados=())
        agente = dict(a2.REDATOR, sha256=hashlib.sha256(texto.encode("utf-8")).hexdigest())
        gravar_ficha_na_caixa(c.raiz, a2.PROJETO, {
            "schema_version": "fundacao.ficha_aberturas/1", "ficha_id": "ficha-caso-real-v1", "project_id": a2.PROJETO,
            "versao": 1, "motivo": "ensaio", "consequencias": "ensaio",
            "plugins": [{"nome": a2.PLUGIN, "origem": f"plugins-candidatos/{a2.PLUGIN}",
                         "manifesto_sha256": c.m.sha256_do_plugin(manifesto), "agentes": [agente]}]})
        rel = c.instalar()
        self.assertIn(f"{a2.PLUGIN}:com espaco", "\n".join(rel["avisos"]))
        perfil = json.loads((c.area / "settings.wsl.json").read_text(encoding="utf-8"))
        self.assertEqual(perfil["env"]["FUNDACAO_SKILLS"], f"{a2.PLUGIN}:ola")  # a de pasta ruim ficou de fora


@unittest.skipUnless(os.name == "nt", "o PowerShell dos scripts do titular é o do Windows")
class PowerShellDoRegistro(unittest.TestCase):
    """O preparar-projeto.ps1 avisa (e, com -RegistrarAninhadas, soma ao registro) e o preparar-maquina.ps1 aceita
    -NegarAgente. PowerShell de verdade, pastas descartáveis e chave de ensaio com senha, `stdin` fechado."""

    def setUp(self):
        import test_host_windows as w
        if w.ELEVADO:
            self.skipTest("o script recusa rodar elevado (código 2), por desenho")
        self.w = w
        self.caso = w._Base("setUp")
        self.caso.setUp()
        self.addCleanup(self.caso.tearDown)
        w.gerar_chave(self.caso.chave, w.SENHA_DE_ENSAIO)  # a chave do titular pronta: nada espera entrada
        com_aninhadas(self.caso.raiz)
        self.registro = self.caso.raiz / "registry" / "projetos-host.json"

    def projeto(self, *args):
        c = self.caso
        c.n += 1
        rel = c.base / f"projeto-{c.n}.json"
        cmd = [self.w.POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
               str(c.ps1.parent / "preparar-projeto.ps1"), "-Raiz", str(c.raiz), "-Titular", "titular", "-Projeto",
               "caso-real", "-Chave", str(c.chave), "-Ancora", str(c.ancora), "-Ferramentas", str(c.ferramentas),
               "-Python", sys.executable, "-Distribuicao", "Ensaio-Sem-Distro", "-SemBackups", "-Relatorio", str(rel),
               *map(str, args)]
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV,
                           timeout=300, stdin=subprocess.DEVNULL)
        return p, (json.loads(rel.read_text(encoding="utf-8")) if rel.is_file() else None)

    def deny(self) -> list:
        return json.loads((self.caso.raiz / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]

    def test_avisa_com_o_comando_pronto_e_nao_grava_o_registro(self):
        antes = self.w.fotografia(self.caso.raiz)
        p, rel = self.projeto("-Simular")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        texto = "\n".join(rel["avisos"])
        for trecho in ("scrapling-juridico", "revisor-externo", "registrar-projeto", "--negar-agente",
                       "-RegistrarAninhadas"):
            self.assertIn(trecho, texto)
        self.assertEqual(rel["aninhadas"]["skills"], ["scrapling-juridico"])
        self.assertEqual(self.w.fotografia(self.caso.raiz), antes)
        # Lote S2 (A3): projeto fora do registro com nome a negar não entra só com os nomes, nem na simulação
        p, rel = self.projeto("-Simular", "-RegistrarAninhadas")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        for trecho in ("ainda não está no registro", "registrar-projeto", "--origem", "scrapling-juridico"):
            self.assertIn(trecho, rel["mensagem"])
        self.assertEqual(self.w.fotografia(self.caso.raiz), antes)
        self.registrar_o_projeto()
        antes = self.w.fotografia(self.caso.raiz)
        p, rel = self.projeto("-Simular", "-RegistrarAninhadas")  # registrado: a simulação não grava, nem com a opção
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("execução real", "\n".join(rel["avisos"]))
        self.assertEqual(self.w.fotografia(self.caso.raiz), antes)

    def test_registrar_aninhadas_de_projeto_fora_do_registro_recusa_sem_simular(self):
        p, rel = self.projeto("-SemUAC", "-RegistrarAninhadas")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("--origem", rel["mensagem"])
        self.assertFalse(self.registro.exists())
        self.assertFalse((self.caso.raiz / ".claude" / "settings.json").exists()
                         and "Skill(scrapling-juridico)" in self.deny())

    def registrar_o_projeto(self) -> None:
        origem = self.caso.base / "Origem Registrada"
        origem.mkdir(exist_ok=True)
        r = rodar("registrar-projeto", "--raiz", self.caso.raiz, "--projeto", "caso-real", "--origem", origem)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_registrar_aninhadas_soma_ao_registro_e_o_perfil_ja_nega(self):
        self.registrar_o_projeto()
        p, rel = self.projeto("-SemUAC", "-RegistrarAninhadas")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        item = json.loads(self.registro.read_text(encoding="utf-8"))["projetos"]["caso-real"]
        self.assertEqual((item["aninhadas_negadas"], item["agentes_negados"]),
                         (["scrapling-juridico"], ["revisor-arquivo", "revisor-externo"]))
        for regra in ("Skill(scrapling-juridico)", "Agent(revisor-arquivo)", "Agent(revisor-externo)"):
            self.assertIn(regra, self.deny())
        self.assertIn("somados ao registro", "\n".join(rel["avisos"]))
        p, rel = self.projeto("-SemUAC")  # já registrado: sem aviso de falta, e o registro não muda
        self.assertNotIn("FORA do registro", "\n".join(rel["avisos"]))
        self.assertEqual(json.loads(self.registro.read_text(encoding="utf-8"))["projetos"]["caso-real"], item)

    def test_preparar_maquina_aceita_negar_agente_e_deixa_a_pendencia(self):
        p, rel = self.caso.rodar("-SemUAC", "-Projeto", "caso-real", "-NegarAgente", "ag-x,ag-y")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        for regra in ("Agent(ag-x)", "Agent(ag-y)"):
            self.assertIn(regra, self.deny())
        pendencias = "\n".join(rel["pendencias"])
        self.assertIn("-NegarAgente ag-x", pendencias)
        self.assertIn("--negar-agente", pendencias)


if __name__ == "__main__":
    unittest.main()
