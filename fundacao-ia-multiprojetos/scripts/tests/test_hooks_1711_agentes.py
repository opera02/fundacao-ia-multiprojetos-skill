"""1.7.11, lote A1 (desenho de skills e agentes, §2.4): o `guarda_ferramentas.py` com agentes de arquivo e as travas.

Cada trava tem a prova negativa dela:
- FUNDACAO_AGENTES: o tipo de arquivo listado passa na ferramenta Agent; o tipo que não está na lista, a variável
  malformada e a variável ausente deixam o tipo de arquivo fechado, e os quatro embutidos seguem;
- `agent_type` do evento de subagente: tipo fora da lista (vazio, que não é texto, ausente com `agent_id`) nega toda
  ferramenta, e o agente de arquivo só usa as ferramentas dele;
- `cwd` do evento de subagente: fora do projeto (e sem raiz ou projeto no ambiente) nega toda ferramenta; a sessão
  principal não tem essa trava;
- Skill: com FUNDACAO_SKILLS, só o nome exato da lista; sem a variável, o comportamento de antes.
O guarda continua sem abrir arquivo, listar pasta nem criar processo (vigia de auditoria). Eventos fictícios; raiz
fictícia `/mnt/q/IA/fundacao`; o que depende de medida no canário (M-A1, M-A3, M-S6) está dito nos testes.
"""

from __future__ import annotations

import unittest

from test_hooks_1710 import FERRAMENTAS, carregar, decisao, ferramenta, motivo, rodar_vigiado

HOOK = "guarda_ferramentas.py"
RAIZ = "/mnt/q/IA/fundacao"
PROJETO = "juridico-lab"
PASTA = f"{RAIZ}/projects/{PROJETO}"
TEMP = f"/tmp/fundacao-ia-{PROJETO}"
REDATOR = "juridico-lab-redacao:redator"
REVISOR = "juridico-lab-redacao:revisor"
AGENTES = f"{REDATOR}=Read|Grep|Glob|Write|Edit,{REVISOR}=Read|Grep|Glob"
BASE = {"FUNDACAO_FERRAMENTAS": FERRAMENTAS, "FUNDACAO_RAIZ": RAIZ, "FUNDACAO_PROJECT": PROJETO}
EMBUTIDOS = ("general-purpose", "web-fetch", "Explore", "Plan")
LOCAL = {"description": "Revisar o passo 3", "prompt": "Leia outputs/x.md e aponte erros."}


def evento(nome: str, tipo="general-purpose", cwd=PASTA, agent_id="ag-1", **entrada) -> dict:
    """O evento de uma ferramenta chamada por um subagente (chaves `agent_id`, `agent_type` e `cwd` do 2.1.302)."""
    e = {"hook_event_name": "PreToolUse", "tool_name": nome, "tool_input": entrada}
    if agent_id is not None:
        e["agent_id"] = agent_id
    if tipo is not None:
        e["agent_type"] = tipo
    if cwd is not None:
        e["cwd"] = cwd
    return e


class _Base(unittest.TestCase):
    def setUp(self):
        self.m = carregar(HOOK)

    def decide(self, event: dict, **variaveis) -> str:
        env = {**BASE, **variaveis}
        return "deny" if self.m.decide(event, env) else "sem_decisao"

    def motivo(self, event: dict, **variaveis) -> str:
        negativa = self.m.decide(event, {**BASE, **variaveis})
        return negativa["hookSpecificOutput"]["permissionDecisionReason"] if negativa else ""


class AgentesDeArquivoNaFerramentaAgent(_Base):
    """Tipos de FUNDACAO_AGENTES na entrada da ferramenta Agent (a sessão principal chamando)."""

    def agent(self, tipo, **variaveis) -> str:
        return self.decide(ferramenta("Agent", **{**LOCAL, "subagent_type": tipo}), **variaveis)

    def test_tipo_listado_passa_e_os_embutidos_seguem(self):
        for tipo in (REDATOR, REVISOR, *EMBUTIDOS):
            with self.subTest(tipo=tipo):
                self.assertEqual(self.agent(tipo, FUNDACAO_AGENTES=AGENTES), "sem_decisao")
        for nome in ("Agent", "Task"):  # o nome antigo vale pelo mesmo item
            self.assertEqual(self.decide(ferramenta(nome, **{**LOCAL, "subagent_type": REDATOR}),
                                         FUNDACAO_FERRAMENTAS=FERRAMENTAS.replace("Agent", "Task"),
                                         FUNDACAO_AGENTES=AGENTES), "sem_decisao")

    def test_sem_a_variavel_nada_muda(self):
        """Prova negativa: ausente (ou vazia), o tipo de arquivo segue negado e os embutidos passam, como na 1.7.10.2."""
        for variaveis in ({}, {"FUNDACAO_AGENTES": ""}, {"FUNDACAO_AGENTES": "  , "}):
            with self.subTest(variaveis=variaveis):
                self.assertEqual(self.agent(REDATOR, **variaveis), "deny")
                for tipo in EMBUTIDOS:
                    self.assertEqual(self.agent(tipo, **variaveis), "sem_decisao")
        texto = self.motivo(ferramenta("Agent", **{**LOCAL, "subagent_type": REDATOR}))
        for trecho in (REDATOR, "general-purpose", "ficha de aberturas", "titular"):
            self.assertIn(trecho, texto)

    def test_tipo_fora_da_lista_e_negado(self):
        for tipo in ("juridico-lab-redacao:outro", "outro-plugin:redator", "redator", "juridico-lab-redacao:",
                     ":redator", f"{REDATOR} ", f" {REDATOR}", REDATOR.upper(), f"{REDATOR}:x", "cc-plugin-x:agente",
                     "fork", "worker", "claude-code-guide", "", 7, [REDATOR], {"t": REDATOR}):
            with self.subTest(tipo=tipo):
                self.assertEqual(self.agent(tipo, FUNDACAO_AGENTES=AGENTES), "deny")
        texto = self.motivo(ferramenta("Agent", **{**LOCAL, "subagent_type": "juridico-lab-redacao:outro"}),
                            FUNDACAO_AGENTES=AGENTES)
        self.assertIn(REDATOR, texto)  # a lista da sessão aparece na mensagem

    def test_variavel_malformada_fecha_todo_tipo_de_arquivo_e_mantem_os_embutidos(self):
        malformadas = {
            "sem '='": "juridico-lab-redacao:redator", "sem ':'": "redator=Read",
            "duas ':'": "a:b:c=Read", "agente vazio": "juridico-lab-redacao:=Read", "plugin vazio": ":redator=Read",
            "sem ferramenta": f"{REDATOR}=", "barra sobrando": f"{REDATOR}=Read|", "barra no começo": f"{REDATOR}=|Read",
            "ferramenta repetida": f"{REDATOR}=Read|Read", "agente repetido": f"{REDATOR}=Read,{REDATOR}=Grep",
            "Agent": f"{REDATOR}=Read|Agent", "Task": f"{REDATOR}=Task", "Skill": f"{REDATOR}=Skill",
            "NotebookEdit": f"{REDATOR}=NotebookEdit", "SubagentHandback": f"{REDATOR}=SubagentHandback",
            "MCP": f"{REDATOR}=mcp__fundacao__status", "especificador": f"{REDATOR}=Bash(git *)",
            "curinga": f"{REDATOR}=*", "separador errado": f"{REDATOR}=Read;Grep", "espaço no nome": "a b:c=Read",
            "11 ferramentas": f"{REDATOR}=" + "|".join(f"Ferr{i}" for i in range(11)),
            "21 agentes": ",".join(f"p:a{i}=Read" for i in range(21)),
            "texto enorme": f"{REDATOR}=Read," + "x" * 9000, "controle": f"{REDATOR}=Read\x00",
            "bom e mau juntos": f"{REVISOR}=Read,x:y",
        }
        for rotulo, valor in malformadas.items():
            with self.subTest(rotulo=rotulo):
                self.assertEqual(self.agent(REDATOR, FUNDACAO_AGENTES=valor), "deny")
                self.assertEqual(self.agent(REVISOR, FUNDACAO_AGENTES=valor), "deny")
                for tipo in EMBUTIDOS:
                    self.assertEqual(self.agent(tipo, FUNDACAO_AGENTES=valor), "sem_decisao")
        texto = self.motivo(ferramenta("Agent", **{**LOCAL, "subagent_type": REDATOR}), FUNDACAO_AGENTES="lixo")
        self.assertIn("FUNDACAO_AGENTES", texto)
        self.assertIn("malformada", texto)

    def test_variavel_que_nao_e_texto_nao_derruba_o_guarda(self):
        for valor in (5, ["a:b=Read"], {"a:b": "Read"}, True):
            with self.subTest(valor=valor):
                self.assertEqual(self.agent(REDATOR, FUNDACAO_AGENTES=valor), "deny")
                self.assertEqual(self.agent("Plan", FUNDACAO_AGENTES=valor), "sem_decisao")

    def test_so_o_tipo_muda_os_outros_campos_continuam_conferidos(self):
        for campo, valor in (("isolation", "worktree"), ("cwd", "/tmp"), ("name", "x"), ("mode", "bypass"),
                             ("politica_nova", 1)):
            with self.subTest(campo=campo):
                self.assertEqual(self.decide(ferramenta("Agent", **{**LOCAL, "subagent_type": REDATOR, campo: valor}),
                                             FUNDACAO_AGENTES=AGENTES), "deny")
        self.assertEqual(self.decide(ferramenta("Agent", **{**LOCAL, "subagent_type": REDATOR, "model": 3}),
                                     FUNDACAO_AGENTES=AGENTES), "deny")

    def test_agent_fora_da_lista_do_tools_segue_negada(self):
        self.assertEqual(self.agent(REDATOR, FUNDACAO_AGENTES=AGENTES, FUNDACAO_FERRAMENTAS="Bash,Read"), "deny")


class TravaDoTipoDoSubagente(_Base):
    """`agent_type` do evento que vem de um subagente: fora da lista, toda ferramenta é negada."""

    TODAS = (("Read", {"file_path": "x"}), ("Bash", {"command": "ls"}), ("Write", {"file_path": "x"}),
             ("Agent", LOCAL), ("SubagentHandback", {}), ("Skill", {"skill": "x:y"}), ("mcp__fundacao__status", {}),
             ("TodoWrite", {}))

    def test_embutidos_seguem_as_regras_de_hoje(self):
        for tipo in EMBUTIDOS:
            for nome, entrada in self.TODAS[:3] + self.TODAS[7:]:
                with self.subTest(tipo=tipo, ferramenta=nome):
                    self.assertEqual(self.decide(evento(nome, tipo, **entrada)), "sem_decisao")
        self.assertEqual(self.decide(evento("Agent", "Plan", **LOCAL)), "sem_decisao")
        self.assertEqual(self.decide(evento("SubagentHandback", "Explore")), "sem_decisao")
        # a lista da sessão continua mandando: ferramenta fora dela é negada também para o embutido
        self.assertEqual(self.decide(evento("WebFetch", "Plan", url="https://x.invalid")), "deny")

    def test_tipo_fora_da_lista_nega_toda_ferramenta(self):
        tipos = ("revisor-juridico", "juridico-lab-redacao:outro", "cc-plugin-x:agente", "fork", "general-purpose ",
                 "explore", "", 7, ["Plan"], {"t": "Plan"}, True, 0, None)
        for tipo in tipos:
            for nome, entrada in self.TODAS:
                with self.subTest(tipo=tipo, ferramenta=nome):
                    e = evento(nome, None, **entrada)
                    e["agent_type"] = tipo
                    self.assertEqual(self.decide(e, FUNDACAO_AGENTES=AGENTES, FUNDACAO_MCP_PERMITIDAS="fundacao"),
                                     "deny")

    def test_agent_id_sem_agent_type_nega_tudo(self):
        for nome, entrada in self.TODAS:
            with self.subTest(ferramenta=nome):
                self.assertEqual(self.decide(evento(nome, None, **entrada), FUNDACAO_AGENTES=AGENTES), "deny")
        texto = self.motivo(evento("Read", None, file_path="x"))
        for trecho in ("'Read'", "sem tipo", "ficha de aberturas", "titular"):
            self.assertIn(trecho, texto)

    def test_agent_type_sem_agent_id_tambem_e_evento_de_subagente(self):
        self.assertEqual(self.decide(evento("Read", "Plan", agent_id=None, file_path="x")), "sem_decisao")
        self.assertEqual(self.decide(evento("Read", "estranho", agent_id=None, file_path="x")), "deny")

    def test_a_sessao_principal_nao_tem_a_trava(self):
        for nome, entrada in (("Read", {"file_path": "x"}), ("Bash", {"command": "ls"})):
            principal = {"hook_event_name": "PreToolUse", "tool_name": nome, "tool_input": entrada}
            self.assertEqual(self.decide(principal), "sem_decisao")
            self.assertEqual(self.decide({**principal, "cwd": "/tmp"}), "sem_decisao")  # um cd do Bash não trava a sessão

    def test_tipo_de_arquivo_listado_passa_e_sem_a_ficha_nega(self):
        self.assertEqual(self.decide(evento("Read", REDATOR, file_path="x"), FUNDACAO_AGENTES=AGENTES), "sem_decisao")
        self.assertEqual(self.decide(evento("Read", REDATOR, file_path="x")), "deny")  # variável ausente
        self.assertEqual(self.decide(evento("Read", REDATOR, file_path="x"), FUNDACAO_AGENTES="lixo"), "deny")
        texto = self.motivo(evento("Read", REDATOR, file_path="x"))
        for trecho in (REDATOR, "general-purpose", "ficha de aberturas"):
            self.assertIn(trecho, texto)

    def test_tipo_malformado_da_variavel_nega_o_subagente_de_arquivo_e_poupa_o_embutido(self):
        valor = f"{REDATOR}=Read|Read"
        self.assertEqual(self.decide(evento("Read", REDATOR, file_path="x"), FUNDACAO_AGENTES=valor), "deny")
        self.assertEqual(self.decide(evento("Read", "Plan", file_path="x"), FUNDACAO_AGENTES=valor), "sem_decisao")


class FerramentasDoAgenteDeArquivo(_Base):
    """Cada agente de arquivo fica só com as ferramentas dele (a sessão tem outras, como o Bash)."""

    def test_ferramenta_da_lista_passa(self):
        for nome in ("Read", "Grep", "Glob", "Write", "Edit"):
            with self.subTest(ferramenta=nome):
                self.assertEqual(self.decide(evento(nome, REDATOR, file_path="x"), FUNDACAO_AGENTES=AGENTES),
                                 "sem_decisao")
        for nome in ("Read", "Grep", "Glob"):
            self.assertEqual(self.decide(evento(nome, REVISOR, pattern="x"), FUNDACAO_AGENTES=AGENTES), "sem_decisao")

    def test_ferramenta_fora_da_lista_do_agente_e_negada_mesmo_na_da_sessao(self):
        for tipo, fora in ((REDATOR, ("Bash", "TodoWrite", "Agent", "Skill", "WebFetch", "mcp__fundacao__x")),
                           (REVISOR, ("Bash", "Write", "Edit", "TodoWrite", "Agent", "Task", "Skill"))):
            for nome in fora:
                with self.subTest(tipo=tipo, ferramenta=nome):
                    entrada = LOCAL if nome in ("Agent", "Task") else {}
                    self.assertEqual(self.decide(evento(nome, tipo, **entrada), FUNDACAO_AGENTES=AGENTES,
                                                 FUNDACAO_FERRAMENTAS=FERRAMENTAS + ",Task,WebFetch,mcp__fundacao__x",
                                                 FUNDACAO_MCP_PERMITIDAS="fundacao"), "deny")
        texto = self.motivo(evento("Bash", REVISOR, command="ls"), FUNDACAO_AGENTES=AGENTES)
        for trecho in (REVISOR, "'Bash'", "Glob, Grep, Read", "ficha de aberturas", "titular"):
            self.assertIn(trecho, texto)

    def test_agente_nao_chama_outro_agente(self):
        self.assertEqual(self.decide(evento("Agent", REDATOR, **{**LOCAL, "subagent_type": "Plan"}),
                                     FUNDACAO_AGENTES=AGENTES), "deny")

    def test_a_ferramenta_do_agente_tambem_tem_de_estar_na_lista_da_sessao(self):
        self.assertEqual(self.decide(evento("Write", REDATOR, file_path="x"), FUNDACAO_AGENTES=AGENTES,
                                     FUNDACAO_FERRAMENTAS="Read,Grep,Glob,Agent"), "deny")
        self.assertEqual(self.decide(evento("Read", REDATOR, file_path="x"), FUNDACAO_AGENTES=AGENTES,
                                     FUNDACAO_FERRAMENTAS="Read,Grep,Glob,Agent"), "sem_decisao")

    def test_o_relatorio_de_volta_nao_conta_como_ferramenta_do_agente(self):
        """Decisão do lote: o `SubagentHandback` fica fora da conta (senão o agente não devolve o resultado); com o
        Agent fora da lista da sessão ele segue negado, como hoje. Se o canário (M-A3) mostrar que o evento dele não
        traz o tipo do agente, a trava do tipo o nega: mede-se lá."""
        self.assertEqual(self.decide(evento("SubagentHandback", REVISOR), FUNDACAO_AGENTES=AGENTES), "sem_decisao")
        self.assertEqual(self.decide(evento("SubagentHandback", REVISOR), FUNDACAO_AGENTES=AGENTES,
                                     FUNDACAO_FERRAMENTAS="Read,Grep,Glob"), "deny")

    def test_agente_embutido_nao_perde_ferramenta(self):
        self.assertEqual(self.decide(evento("Bash", "general-purpose", command="ls"), FUNDACAO_AGENTES=AGENTES),
                         "sem_decisao")


class TravaDoCwdDoSubagente(_Base):
    FORA = ("/tmp", "/", "", RAIZ, f"{RAIZ}/projects", f"{RAIZ}/projects/reversa-lab", f"{RAIZ}/projects/reversa-lab/data",
            f"{PASTA}/../reversa-lab", f"{PASTA}/../../..", f"{PASTA}/x/../../reversa-lab/y", f"{PASTA}-2", f"{PASTA}x/a",
            f"{RAIZ}/state", "projects/juridico-lab", "./projects/juridico-lab", f"//mnt/q/IA/fundacao/projects/{PROJETO}",
            f"{PASTA}\x00/x", f"{PASTA}\n/x", "/mnt/q/IA/fundação/projects/juridico-lab-x", "C:\\fundacao\\projects",
            7, ["x"], {"cwd": PASTA}, True)

    def test_dentro_do_projeto_passa(self):
        for cwd in (PASTA, PASTA + "/", PASTA + "/outputs", f"{PASTA}/data/sub/pasta", f"{PASTA}/a/../b",
                    f"{PASTA}//outputs"):
            for tipo in ("Plan", REDATOR):
                with self.subTest(cwd=cwd, tipo=tipo):
                    self.assertEqual(self.decide(evento("Read", tipo, cwd=cwd, file_path="x"),
                                                 FUNDACAO_AGENTES=AGENTES), "sem_decisao")

    def test_fora_do_projeto_nega_toda_ferramenta(self):
        for cwd in self.FORA:
            for tipo, nome in (("Plan", "Read"), ("general-purpose", "Bash"), (REDATOR, "Write"), ("Explore", "Grep")):
                with self.subTest(cwd=cwd, tipo=tipo, ferramenta=nome):
                    e = evento(nome, tipo, cwd=None, command="ls", file_path="x", pattern="x")
                    e["cwd"] = cwd
                    self.assertEqual(self.decide(e, FUNDACAO_AGENTES=AGENTES), "deny")
        texto = self.motivo(evento("Read", "Plan", cwd="/tmp", file_path="x"))
        for trecho in ("'/tmp'", "'Plan'", "fora da pasta do projeto", "projects/<projeto>"):
            self.assertIn(trecho, texto)

    def test_evento_sem_cwd_nega(self):
        self.assertEqual(self.decide(evento("Read", "Plan", cwd=None, file_path="x")), "deny")
        self.assertIn("sem pasta de trabalho", self.motivo(evento("Read", "Plan", cwd=None, file_path="x")))

    def test_sem_raiz_ou_projeto_no_ambiente_nega(self):
        for faltando in ("FUNDACAO_RAIZ", "FUNDACAO_PROJECT"):
            env = {k: v for k, v in BASE.items() if k != faltando}
            with self.subTest(faltando=faltando):
                self.assertEqual("deny" if self.m.decide(evento("Read", "Plan", file_path="x"), env) else "sem_decisao",
                                 "deny")
        for valor in ("../x", "a/b", "", ".", "..", "x" * 100, 5, None):
            with self.subTest(projeto=valor):
                self.assertEqual(self.decide(evento("Read", "Plan", file_path="x"), FUNDACAO_PROJECT=valor), "deny")
        for raiz in ("relativa/raiz", "", "//mnt/q", "/mnt/q\n", 5, None):
            with self.subTest(raiz=raiz):
                self.assertEqual(self.decide(evento("Read", "Plan", file_path="x"), FUNDACAO_RAIZ=raiz), "deny")

    def test_temp_do_projeto_vale_so_com_o_nome_certo(self):
        for tmp, cwd, esperado in ((TEMP, TEMP, "sem_decisao"), (TEMP, TEMP + "/sub", "sem_decisao"),
                                   (TEMP, "/tmp", "deny"), (TEMP, "/tmp/fundacao-ia-reversa-lab", "deny"),
                                   (TEMP, TEMP + "-2/x", "deny"),
                                   ("/tmp", "/tmp", "deny"), ("/", "/", "deny"), ("/fundacao-ia-" + PROJETO,
                                                                                  "/fundacao-ia-" + PROJETO, "deny"),
                                   ("/tmp/fundacao-ia-reversa-lab", "/tmp/fundacao-ia-reversa-lab", "deny"),
                                   ("tmp/fundacao-ia-" + PROJETO, "tmp/fundacao-ia-" + PROJETO, "deny")):
            with self.subTest(tmpdir=tmp, cwd=cwd):
                self.assertEqual(self.decide(evento("Read", "Plan", cwd=cwd, file_path="x"), TMPDIR=tmp), esperado)

    def test_a_trava_nao_depende_do_agente_de_arquivo(self):
        """Vale sem FUNDACAO_AGENTES (o lote A1 vale sozinho, sem agente aberto)."""
        self.assertEqual(self.decide(evento("Read", "Plan", cwd="/tmp", file_path="x")), "deny")

    def test_pela_linha_de_comando_como_o_host_chama(self):
        """O hook de verdade (`python -I -B`): negativa em JSON só com ASCII, mesmo com acento no `cwd` do evento."""
        variaveis = {**BASE, "FUNDACAO_AGENTES": AGENTES}
        self.assertEqual(decisao(HOOK, evento("Read", REDATOR, file_path="x"), **variaveis), "sem_decisao")
        self.assertEqual(decisao(HOOK, evento("Bash", REDATOR, command="ls"), **variaveis), "deny")
        self.assertEqual(decisao(HOOK, evento("Read", "Plan", cwd="/mnt/q/IA/fundação"), **variaveis), "deny")
        self.assertEqual(decisao(HOOK, evento("Read", "fantasma", file_path="x"), **variaveis), "deny")
        self.assertIn("fora da pasta do projeto", motivo(HOOK, evento("Read", "Plan", cwd="/tmp/ação"), **variaveis))


class SkillSoDaFicha(_Base):
    SKILL = {"skill": "juridico-lab-redacao:peticao"}

    def skill(self, entrada, **variaveis) -> str:
        return self.decide(ferramenta("Skill", **entrada), **variaveis)

    def test_sem_a_variavel_o_comportamento_e_o_de_hoje(self):
        for entrada in (self.SKILL, {"skill": "pdf"}, {"skill": "qualquer:coisa", "args": "x"}, {}, {"skill_nome": "x"}):
            with self.subTest(entrada=entrada):
                self.assertEqual(self.skill(entrada), "sem_decisao")
        self.assertEqual(self.skill(self.SKILL, FUNDACAO_FERRAMENTAS="Read,Bash"), "deny")  # fora do --tools

    def test_com_a_variavel_so_o_nome_exato_da_lista(self):
        lista = "juridico-lab-redacao:peticao,juridico-lab-redacao:revisao"
        for nome in ("juridico-lab-redacao:peticao", "juridico-lab-redacao:revisao"):
            self.assertEqual(self.skill({"skill": nome}, FUNDACAO_SKILLS=lista), "sem_decisao")
        self.assertEqual(self.skill({"skill": "juridico-lab-redacao:peticao", "args": "x"}, FUNDACAO_SKILLS=lista),
                         "sem_decisao")
        for nome in ("pdf", "docx", "peticao", "juridico-lab-redacao:outra", "outro-plugin:peticao", "cc-plugin-x:y",
                     "juridico-lab-redacao:peticao ", " juridico-lab-redacao:peticao", "/juridico-lab-redacao:peticao",
                     "JURIDICO-LAB-REDACAO:PETICAO", "juridico-lab-redacao:peticao:x", "juridico-lab-redacao:", "", "*"):
            with self.subTest(skill=nome):
                self.assertEqual(self.skill({"skill": nome}, FUNDACAO_SKILLS=lista), "deny")
        texto = self.motivo(ferramenta("Skill", skill="pdf"), FUNDACAO_SKILLS=lista)
        for trecho in ("'pdf'", "FUNDACAO_SKILLS", "ficha de aberturas", "<plugin>:<skill>", "titular"):
            self.assertIn(trecho, texto)

    def test_variavel_vazia_ou_malformada_nega_toda_skill(self):
        for valor in ("", " , ", "peticao", "a:b:c", "a:b,peticao", "a b:c", "a:b;c:d", "a:b," + "x" * 9000, "a:b\x00", 5):
            with self.subTest(valor=valor):
                for nome in ("a:b", "c:d", "pdf"):
                    self.assertEqual(self.skill({"skill": nome}, FUNDACAO_SKILLS=valor), "deny")
        self.assertIn("malformada", self.motivo(ferramenta("Skill", skill="a:b"), FUNDACAO_SKILLS="lixo"))

    def test_traco_e_nenhuma_skill_bem_formada_e_nega_toda_skill(self):
        """F13: o preparo grava "-" sem skill (valor não vazio, que não depende do repasse de variável vazia ao hook). O
        guarda lê "-" como nenhuma skill, bem formada (a negação não diz "malformada"); a vazia, de perfil anterior, segue
        igual; "-" no meio de uma lista é malformado."""
        self.assertEqual(self.m.skills_da_ficha("-"), (frozenset(), True))
        self.assertEqual(self.m.skills_da_ficha(""), (frozenset(), True))
        for valor in ("-", ""):
            for nome in ("a:b", "pdf", "-", ""):
                with self.subTest(valor=valor, skill=nome):
                    self.assertEqual(self.skill({"skill": nome}, FUNDACAO_SKILLS=valor), "deny")
            self.assertNotIn("malformada", self.motivo(ferramenta("Skill", skill="a:b"), FUNDACAO_SKILLS=valor))
        for valor in ("a:b,-", "-,a:b", "--", " - x"):
            with self.subTest(valor=valor):
                self.assertEqual(self.m.skills_da_ficha(valor), (frozenset(), False))
                self.assertEqual(self.skill({"skill": "a:b"}, FUNDACAO_SKILLS=valor), "deny")

    def test_entrada_que_o_guarda_nao_reconhece_nega(self):
        """A forma da entrada da Skill no hook é a medir (M-S6): o que não tem `skill` em texto é negado."""
        for entrada in ({}, {"skill": None}, {"skill": 7}, {"skill": ["a:b"]}, {"skill_nome": "a:b"}, {"command": "a:b"}):
            with self.subTest(entrada=entrada):
                self.assertEqual(self.skill(entrada, FUNDACAO_SKILLS="a:b"), "deny")
        for bruto in (None, "a:b", ["a:b"], 5):
            self.assertEqual("deny" if self.m.decide({"tool_name": "Skill", "tool_input": bruto},
                                                      {**BASE, "FUNDACAO_SKILLS": "a:b"}) else "sem_decisao", "deny")

    def test_skill_fora_do_tools_segue_negada_mesmo_na_lista(self):
        self.assertEqual(self.skill({"skill": "a:b"}, FUNDACAO_SKILLS="a:b", FUNDACAO_FERRAMENTAS="Read,Bash"), "deny")

    def test_subagente_embutido_segue_a_lista_e_o_de_arquivo_nao_tem_skill(self):
        self.assertEqual(self.decide(evento("Skill", "Plan", skill="a:b"), FUNDACAO_SKILLS="a:b"), "sem_decisao")
        self.assertEqual(self.decide(evento("Skill", "Plan", skill="pdf"), FUNDACAO_SKILLS="a:b"), "deny")
        self.assertEqual(self.decide(evento("Skill", REDATOR, skill="a:b"), FUNDACAO_SKILLS="a:b",
                                     FUNDACAO_AGENTES=AGENTES), "deny")


class SemEntradaSaidaNemSegredo(_Base):
    def test_o_guarda_nao_abre_arquivo_nem_cria_processo(self):
        """Vigia de auditoria: abrir arquivo, listar pasta, criar socket ou processo encerra com o código 97."""
        variaveis = {**BASE, "FUNDACAO_AGENTES": AGENTES, "FUNDACAO_SKILLS": "a:b", "TMPDIR": TEMP}
        for e in (evento("Read", REDATOR, file_path="x"), evento("Bash", REDATOR, command="ls"),
                  evento("Read", "Plan", cwd="/tmp"), evento("Read", None), ferramenta("Skill", skill="a:b"),
                  ferramenta("Agent", **{**LOCAL, "subagent_type": REDATOR})):
            with self.subTest(ferramenta=e["tool_name"]):
                p = rodar_vigiado(HOOK, e, **variaveis)
                self.assertEqual(p.returncode, 0, p.stderr[-300:])
                self.assertTrue(p.stdout.isascii())

    def test_a_mensagem_nao_leva_controle_nem_texto_longo_do_evento(self):
        texto = self.motivo(evento("Read", "x" * 5000 + "\n\x1b[31m", file_path="y"))
        self.assertLess(len(texto), 1500)
        self.assertNotIn("\x1b", texto)
        self.assertNotIn("\n", texto)
        texto = self.motivo(evento("Read", "Plan", cwd="/tmp/" + "c" * 5000 + "\n\x1b[31m"))
        self.assertLess(len(texto), 1500)


if __name__ == "__main__":
    unittest.main()
