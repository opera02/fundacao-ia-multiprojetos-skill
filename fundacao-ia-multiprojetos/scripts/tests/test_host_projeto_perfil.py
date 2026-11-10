"""Perfil do projeto no Ubuntu (1.7.10; contratos do lote 2, §3, §6 e §7; folha do HOST, itens 1 e 2).

O perfil sai do modelo `assets/host/wsl/settings.wsl.json` com o plano A (bloqueio de leitura fora das pastas de
trabalho e rede com lista estrita) mais as negações nominais do plano B — com a raiz em /mnt/e o sandbox não confinou
os comandos nas sondas de 31/10/2026, e o isolamento é lógico até o canário passar. Os segredos vêm da regra única
(fortes + pastas, nunca os fracos); `state/` fica fora do sandbox (negado e sem allowRead nem allowWrite); a fila do
porteiro só tem `respostas/` negada; a identidade é `sessao-<p>`; a ficha assinada é a única fonte de rede, WebFetch,
WebSearch e plugins (sem ficha, tudo fechado). Só biblioteca padrão; nada do host é lido nem alterado.
"""

from __future__ import annotations

import copy
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from apoio import ENV, KIT, SCRIPTS, SKILL
from test_host_projeto_apoio import carregar_preparo, ficha_de_ensaio

AJUDANTE = SKILL / "assets" / "host" / "preparo_host.py"
RAIZ = "/mnt/e/Fundacao Exemplo"
PROJ = RAIZ + "/projects/caso-real"
IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"
NEGADOS_DE_PROPOSITO = {"evals/fixtures/legado-squad/.env"}  # dado de avaliação que simula segredo (nenhum código)


def regras():
    import importlib.util
    spec = importlib.util.spec_from_file_location("regras_perfil_1710", SCRIPTS / "regras_de_segredo.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def rodar(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(AJUDANTE), *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=ENV, timeout=120)


class Base(unittest.TestCase):
    def setUp(self):
        self.m = carregar_preparo()
        self.kw = dict(raiz=r"E:\Fundacao Exemplo", projeto="caso-real", perfil_windows=r"C:\Users\<usuario>",
                       outros_projetos=["lab-b", "lab-a"], somente_leitura=[r"D:\Origem Ç"], negar=["squad-x"])

    def perfil(self, **extra):
        return self.m.perfil_wsl(**{**self.kw, **extra})

    def negacoes(self, perfil) -> list:
        return perfil["permissions"]["deny"]


class PlanoAMaisNegacoesNominais(Base):
    def test_plano_a_ligado_e_rede_estrita(self):
        p = self.perfil()
        self.assertIs(p["permissions"]["blockReadsOutsideWorkingDirectories"], True)
        self.assertIs(p["sandbox"]["network"]["strictAllowlist"], True)
        self.assertEqual(p["sandbox"]["network"]["allowedDomains"], [])
        self.assertIs(p["sandbox"]["enabled"], True)
        self.assertIs(p["sandbox"]["allowUnsandboxedCommands"], False)
        self.assertNotIn("excludedCommands", p["sandbox"])
        for chave, valor in (("syncClaudeAiSkills", False), ("syncClaudeAiPlugins", False),
                             ("disableClaudeAiConnectors", True)):
            self.assertIs(p[chave], valor)

    def test_negacoes_nominais_do_plano_b(self):
        negadas = self.negacoes(self.perfil())
        for regra in (f"Read(/{RAIZ}/state/**)", f"Read(/{RAIZ}/projects/lab-a/**)", f"Read(/{RAIZ}/projects/lab-b/**)",
                      f"Read(/{RAIZ}/.claude/projetos/lab-a/**)", f"Read(/{RAIZ}/.claude/projetos/lab-b/**)",
                      "Read(//mnt/d/**)", "Read(//mnt/c/Users/<usuario>/**)", "Read(~/.claude/projects/**)",
                      "Read(~/.claude/history.jsonl)", "Read(~/.claude/file-history/**)", "Read(~/.claude/paste-cache/**)",
                      "Read(~/.claude/session-env/**)", "Read(~/.claude/sessions/**)",
                      "Read(~/.claude/shell-snapshots/**)", "Read(~/.claude/todos/**)", "Read(~/.claude/plans/**)",
                      "Read(~/.claude/backups/**)", "Read(~/.codex/**)", "Read(~/.fundacao/**)"):
            self.assertIn(regra, negadas)
        self.assertNotIn(f"Read(/{RAIZ}/projects/caso-real/**)", negadas)
        self.assertNotIn(f"Read(/{RAIZ}/.claude/projetos/caso-real/**)", negadas)

    def test_unidade_e_pasta_do_windows_da_propria_raiz_nao_sao_negadas(self):
        negadas = self.negacoes(self.perfil(raiz=r"D:\IA\fundacao", somente_leitura=[]))
        self.assertNotIn("Read(//mnt/d/**)", negadas)  # negar a unidade da raiz fecharia o próprio projeto
        negadas = self.negacoes(self.perfil(raiz=r"C:\Users\<usuario>\fundacao", somente_leitura=[]))
        self.assertNotIn("Read(//mnt/c/Users/<usuario>/**)", negadas)

    def test_sockets_negados_salvo_o_temp_do_projeto(self):
        fs = self.perfil(temp_base="/tmp")["sandbox"]["filesystem"]
        for caminho in ("/tmp", "/run", "/var/run", "/mnt/wsl", "/mnt/wslg"):
            self.assertIn(caminho, fs["denyRead"])
        self.assertEqual(fs["allowRead"][-1], "/tmp/fundacao-ia-caso-real")
        self.assertEqual(fs["allowRead"][0], RAIZ + "/fundacao")  # o kit, para o cliente do porteiro

    def test_state_fora_do_sandbox_sem_a_armadilha_do_tmpfs(self):
        fs = self.perfil()["sandbox"]["filesystem"]
        for chave in ("allowRead", "allowWrite"):
            self.assertFalse([c for c in fs[chave] if c.startswith(RAIZ + "/state")], chave)
        self.assertEqual(fs["allowWrite"], [])

    def test_escrita_negada_so_em_respostas_da_fila_e_nas_areas_do_titular(self):
        fs = self.perfil()["sandbox"]["filesystem"]
        for caminho in (RAIZ + "/.claude", RAIZ + "/registry", PROJ + "/.claude", PROJ + "/.porteiro/respostas",
                        PROJ + "/CLAUDE.local.md", RAIZ + "/projects/lab-a", "/mnt/c/ProgramData/FundacaoIA",
                        "/mnt/d/Origem Ç"):
            self.assertIn(caminho, fs["denyWrite"])
        for caminho in (PROJ, PROJ + "/.porteiro", PROJ + "/.porteiro/pedidos"):
            self.assertNotIn(caminho, fs["denyWrite"])  # a mãe da fila fica gravável (contratos, §4)
        negadas = self.negacoes(self.perfil())
        for regra in (f"Edit(/{PROJ}/.porteiro/respostas/**)", f"Edit(/{PROJ}/.claude/**)", f"Edit(/{RAIZ}/.claude/**)",
                      "Edit(//mnt/c/ProgramData/FundacaoIA/**)", f"Edit(/{RAIZ}/registry/**)"):
            self.assertIn(regra, negadas)
        self.assertNotIn(f"Edit(/{PROJ}/.porteiro/**)", negadas)

    def test_ambiente_da_sessao_do_projeto(self):
        env = self.perfil()["env"]
        self.assertEqual(env[IDENTIDADE], "sessao-caso-real")
        self.assertEqual(env["FUNDACAO_PROJECT"], "caso-real")
        self.assertEqual(env["FUNDACAO_RAIZ"], RAIZ)
        self.assertEqual(env["FUNDACAO_PORTEIRO"], PROJ + "/.porteiro")
        self.assertEqual(env["FUNDACAO_FERRAMENTAS"], "Bash,Read,Edit,Write,Glob,Grep,Skill,Agent,TodoWrite")
        self.assertEqual(env["FUNDACAO_MCP_PERMITIDAS"], "")
        self.assertEqual(env["FUNDACAO_DOMINIOS_WEB"], "")
        self.assertEqual(env["DISABLE_AUTOUPDATER"], "1")
        self.assertEqual(env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"], "1")
        self.assertEqual(env["CLAUDE_CODE_DISABLE_WEB_FETCH"], "1")
        for chave, sub in (("XDG_CACHE_HOME", ""), ("npm_config_cache", "/npm"), ("PIP_CACHE_DIR", "/pip"),
                           ("UV_CACHE_DIR", "/uv")):
            self.assertEqual(env[chave], PROJ + "/.cache" + sub)
        for proibida in ("FUNDACAO_PROJETO_TRAVADO", "FUNDACAO_PORTEIRO_SERVIDOR", "FUNDACAO_WEBSEARCH"):
            self.assertNotIn(proibida, env)

    def test_hooks_do_contrato_com_python3_isolado(self):
        p = self.perfil()
        vistos = {}
        for evento, grupos in p["hooks"].items():
            for g in grupos:
                for h in g["hooks"]:
                    self.assertEqual(h["command"], "/usr/bin/python3")
                    self.assertEqual(h["args"][:2], ["-I", "-B"])
                    nome = Path(h["args"][2]).name
                    # 1.7.11 (ponytail, P7): o hook das regras de código só orienta e não bloqueia; os demais, sim.
                    self.assertEqual(h["onFailure"], "continue" if nome == "regras_codigo.py" else "block")
                    vistos[(evento, g["matcher"], nome)] = nome
                    self.assertTrue(h["args"][2].startswith(RAIZ + "/.claude/hooks/"))
        vistos = {(e, m): n for (e, m, n) in vistos if n != "regras_codigo.py"} | {
            (e, m + " [regras]"): n for (e, m, n) in vistos if n == "regras_codigo.py"}
        self.assertEqual(vistos, {("SessionStart", "compact"): "sinais_sessao.py",
                                  ("SessionStart", "startup|resume|clear|compact [regras]"): "regras_codigo.py",
                                  ("SubagentStart", "* [regras]"): "regras_codigo.py",
                                  ("SubagentStart", "*"): "sinais_sessao.py",
                                  ("PreToolUse", "*"): "guarda_ferramentas.py",
                                  ("PreToolUse", "Edit|Write|MultiEdit|NotebookEdit|mcp__.*"): "guarda_caminho.py",
                                  ("PreToolUse", "Bash|PowerShell"): "guarda_identidade.py",
                                  ("PreToolUse", "WebFetch|WebSearch"): "guarda_rede.py",
                                  ("PreToolUse", "Read|Grep|Glob"): "guarda_leitura.py"})

    def test_skill_aninhada_negada_e_backups_recusados(self):
        self.assertIn("Skill(squad-x)", self.negacoes(self.perfil()))
        with self.assertRaises(ValueError):
            self.perfil(backups=[r"D:\Backups"])
        with self.assertRaises(ValueError):
            self.perfil(somente_leitura=[r"E:\Fundacao Exemplo\projects\lab-a"])  # dentro da raiz

    def test_sem_marcador_sobrando_e_deterministico(self):
        a, b = self.m.texto_json(self.perfil()), self.m.texto_json(self.perfil())
        self.assertEqual(a, b)
        self.assertNotIn("{{", a)


class RegraUnicaDeSegredo(Base):
    """Contratos, §3: os perfis negam os fortes + as pastas da regra única, nunca os fracos."""

    def test_igual_a_regra_unica(self):
        R = regras()
        listas = R.listas()
        for perfil in (self.perfil(), self.m.perfil_windows(raiz=r"E:\Fundacao Exemplo", python=r"C:\Py\python.exe")):
            achados = self.m.segredos_do_perfil(perfil)
            self.assertEqual(achados["fortes"], set(listas["nomes_fortes"]))
            self.assertEqual(achados["pastas"], set(listas["pastas_de_segredo"]))
            negadas = " ".join(perfil["permissions"]["deny"])
            for fraco in ("*token*", "*senha*", "*password*", "settings.local.json", ".mcp.json"):
                self.assertNotIn("/" + fraco + ")", negadas)

    def test_lista_divergente_e_acusada(self):
        p = self.perfil()
        p["permissions"]["deny"].remove("Read(./**/*.ppk)")
        self.assertTrue(any("regra única" in x for x in self.m.invariantes_perfil_wsl(p, RAIZ, "caso-real")))

    def test_nenhum_arquivo_da_skill_nem_do_kit_casa_as_negacoes_de_segredo(self):
        """Uma negação que pegasse código da skill ou do kit deixaria a sessão do próprio projeto sem ler o que roda."""
        achados = self.m.segredos_do_perfil(self.perfil())
        casados = set()
        for raiz, pastas, arquivos in os.walk(SKILL):
            pastas[:] = [p for p in pastas if p not in ("__pycache__", ".git")]
            for nome in (*arquivos, *pastas):
                rel = (Path(raiz) / nome).relative_to(SKILL).as_posix()
                partes = [p.casefold() for p in rel.split("/")]
                if any(fnmatch.fnmatchcase(partes[-1], f.casefold()) for f in achados["fortes"]) or any(
                        p in {x.casefold() for x in achados["pastas"]} for p in partes):
                    casados.add(rel)
        self.assertLessEqual(casados, NEGADOS_DE_PROPOSITO)
        self.assertTrue(KIT.is_relative_to(SKILL))  # o kit está dentro da skill: entrou na varredura


class FichaDeAberturas(Base):
    """Mapeamento da ficha (contratos, §6): sem ficha válida, tudo fechado; com ela, só o que ela abre."""

    def resultado(self, **secoes):
        return {"projeto": "caso-real", "valida": True, "versao": 2, "arquivo": "/area/ficha/ficha-v2.json",
                "sha256": "a" * 64, "sig_sha256": "b" * 64, "ficha": ficha_de_ensaio("caso-real", 2, **secoes)}

    def test_sem_ficha_tudo_fechado(self):
        for resultado in (None, {"valida": False, "motivo_invalida": "sem ficha"}, {"valida": True, "ficha": None}):
            with self.subTest(resultado=resultado):
                ab = self.m.aberturas_da_ficha(resultado, "caso-real")
                self.assertFalse(ab["valida"])
                self.assertEqual((ab["rede"], ab["webfetch"], ab["websearch"], ab["plugins"]), ([], [], False, []))

    def test_ficha_valida_abre_so_o_que_lista(self):
        ab = self.m.aberturas_da_ficha(self.resultado(rede={"dominios": ["pypi.org", "*.pythonhosted.org"]},
                                                      webfetch={"dominios": ["pypi.org"]}, websearch=True), "caso-real")
        self.assertTrue(ab["valida"], ab["motivo"])
        p = self.perfil(aberturas=ab)
        # DECISAO-010, item 5: o curinga cobre o domínio principal, e o perfil gera `x` e `*.x`
        self.assertEqual(p["sandbox"]["network"]["allowedDomains"], ["pypi.org", "pythonhosted.org", "*.pythonhosted.org"])
        self.assertEqual(ab["rede"], ["pypi.org", "*.pythonhosted.org"])  # a ficha segue com os itens dela
        self.assertEqual(p["permissions"]["allow"], ["WebFetch(domain:pypi.org)"])
        self.assertNotIn("WebFetch", p["permissions"]["deny"])
        self.assertNotIn("WebSearch", p["permissions"]["deny"])
        env = p["env"]
        self.assertEqual(env["FUNDACAO_DOMINIOS_WEB"], "pypi.org")
        self.assertEqual(env["FUNDACAO_WEBSEARCH"], "1")
        self.assertNotIn("CLAUDE_CODE_DISABLE_WEB_FETCH", env)
        self.assertEqual(env["FUNDACAO_FERRAMENTAS"].split(",")[-2:], ["WebFetch", "WebSearch"])
        self.assertEqual(self.m.conferir_perfil_wsl(p, RAIZ, "caso-real", aberturas=ab), [])
        self.assertTrue(self.m.conferir_perfil_wsl(p, RAIZ, "caso-real", aberturas=self.m.aberturas_fechadas()))

    def test_ficha_fora_dos_tetos_fecha_tudo(self):
        casos = {"ip literal": dict(rede={"dominios": ["10.0.0.1"]}),
                 "localhost": dict(rede={"dominios": ["localhost"]}),
                 "local": dict(rede={"dominios": ["impressora.local"]}),
                 "curinga compartilhado": dict(rede={"dominios": ["*.vercel.app"]}),
                 "curinga de tld": dict(rede={"dominios": ["*.com"]}),
                 "webfetch fora da rede": dict(rede={"dominios": ["a.example"]}, webfetch={"dominios": ["b.example"]}),
                 "reservada 1.7.11": dict(git=[{"pasta": "repo"}]),
                 "perfil copiado do navegador": dict(perfil_navegador_copiado={"origem": "data/x_browser_profile",
                                                                                "manifesto_sha256": "a" * 64}),
                 "mcp com gravação": dict(mcp=[dict(MCP_DO_ESCRITORIO, ferramentas=["salvar_nota"])]),
                 "mcp fora da forma": dict(mcp=[{"nome": "x"}]),
                 "navegador com perfil": dict(navegador=dict(NAVEGADOR_DO_TJSP, perfil="copiado")),
                 "codex por chave de api": dict(outras_llm=[dict(CODEX_PELA_CONTA, autenticacao="chave_api")]),
                 "vencida": dict(vigencia_ate="2020-01-01"),
                 "campo desconhecido": dict(extra=True),
                 "plugin fora da forma": dict(plugins=[{"nome": "x", "origem": "../fora", "manifesto_sha256": "c" * 64}]),
                 "websearch texto": dict(websearch="sim")}
        for nome, secoes in casos.items():
            with self.subTest(nome):
                ab = self.m.aberturas_da_ficha(self.resultado(**secoes), "caso-real")
                self.assertFalse(ab["valida"], nome)
                self.assertEqual(ab["rede"], [])
        outro = self.resultado()
        outro["ficha"]["project_id"] = "lab-a"
        self.assertFalse(self.m.aberturas_da_ficha(outro, "caso-real")["valida"])


MCP_DO_ESCRITORIO = {"nome": "fsn", "origem": "conta", "conector": "Conector do escritorio",
                     "ferramentas": ["buscar_clientes", "get_processo", "relatorio_prazos"],
                     "ocultar": ["salvar_nota", "propor_operacoes", "escanear_vault"], "conteudo_de_terceiros": True}
NAVEGADOR_DO_TJSP = {"dominios": ["*.tjsp.jus.br", "esaj.tjsp.jus.br"], "logins": ["esaj.tjsp.jus.br"],
                     "modos": ["sessao", "login", "captcha"]}
CODEX_PELA_CONTA = {"provedor": "openai-codex", "autenticacao": "conta_chatgpt", "modos": ["exec", "titular"],
                    "conteudo_de_terceiros": True, "teto_chamadas_dia": 30,
                    "r55": {"plano": "Plus", "treinamento_desligado": True, "conferido_em": "2026-11-08"}}


def resultado_de_ensaio(**secoes) -> dict:
    return {"projeto": "caso-real", "valida": True, "versao": 2, "arquivo": "/area/ficha/ficha-v2.json",
            "sha256": "a" * 64, "sig_sha256": "b" * 64, "ficha": ficha_de_ensaio("caso-real", 2, **secoes)}


class SecoesDaJaulaLidasSemAplicar(Base):
    """1.7.11, lote L1: o preparo LÊ mcp, navegador e outras_llm pelo validador do kit. O mcp é aplicado desde o lote L2
    (classe McpDoEscritorioNoPerfil); navegador e outras_llm ainda não mudam o perfil."""

    HOJE = date(2026, 11, 9)

    def ab(self, **secoes):
        return self.m.aberturas_da_ficha(resultado_de_ensaio(**secoes), "caso-real", self.HOJE)

    def test_le_as_tres_secoes_e_as_devolve(self):
        ab = self.ab(mcp=[MCP_DO_ESCRITORIO], navegador=NAVEGADOR_DO_TJSP, outras_llm=[CODEX_PELA_CONTA])
        self.assertTrue(ab["valida"], ab["motivo"])
        self.assertEqual(ab["mcp"], [MCP_DO_ESCRITORIO])
        self.assertEqual(ab["navegador"], NAVEGADOR_DO_TJSP)
        self.assertEqual(ab["outras_llm"], [CODEX_PELA_CONTA])
        self.assertEqual(ab["secoes_lidas_nao_aplicadas"], ["navegador", "outras_llm"])  # o mcp o L2 aplica

    def test_sem_as_secoes_nada_muda(self):
        ab = self.ab(rede={"dominios": ["pypi.org"]})
        self.assertTrue(ab["valida"], ab["motivo"])
        self.assertEqual((ab["mcp"], ab["outras_llm"], ab["secoes_lidas_nao_aplicadas"]), ([], [], []))
        self.assertEqual(ab["navegador"], self.m.aberturas_fechadas()["navegador"])

    def test_navegador_e_codex_ainda_nao_mudam_o_perfil(self):
        """navegador e outras_llm não mudam o perfil (nem a rede, nem o conector), salvo (lote L4) a fila da jaula: com
        operação da sessão, as respostas do porteiro da jaula não são graváveis por ela, como as do porteiro da fundação."""
        sem = self.perfil(aberturas=self.ab(rede={"dominios": ["pypi.org"]}))
        com_ab = self.ab(rede={"dominios": ["pypi.org"]}, navegador=NAVEGADOR_DO_TJSP, outras_llm=[CODEX_PELA_CONTA])
        self.assertTrue(com_ab["valida"], com_ab["motivo"])
        com = self.perfil(aberturas=com_ab)
        alvo = f"{RAIZ}/projects/caso-real/.porteiro/jaula/respostas"
        igual = json.loads(json.dumps(com))
        igual["sandbox"]["filesystem"]["denyWrite"].remove(alvo)
        igual["permissions"]["deny"].remove(f"Edit(/{alvo}/**)")
        self.assertEqual(sem, igual)  # a única diferença é a fila da jaula
        self.assertIs(com["disableClaudeAiConnectors"], True)
        self.assertEqual(com["env"]["FUNDACAO_MCP_PERMITIDAS"], "")
        self.assertNotIn("tjsp", json.dumps(com))
        self.assertEqual(self.m.conferir_perfil_wsl(com, RAIZ, "caso-real", aberturas=com_ab), [])

    def test_recusas_do_kit_fecham_tudo(self):
        casos = {"mcp com campo de gravação": dict(mcp=[dict(MCP_DO_ESCRITORIO, gravacao=["salvar_nota"])]),
                 "mcp local": dict(mcp=[dict(MCP_DO_ESCRITORIO, comando="servidor")]),
                 "mcp sem conteúdo de terceiros": dict(mcp=[dict(MCP_DO_ESCRITORIO, conteudo_de_terceiros=False)]),
                 "navegador com perfil copiado": dict(navegador=dict(NAVEGADOR_DO_TJSP, perfil="copiado")),
                 "navegador com IP": dict(navegador={"dominios": ["10.0.0.1"], "modos": ["sessao"]}),
                 "codex com conferência velha": dict(outras_llm=[dict(CODEX_PELA_CONTA, r55={
                     **CODEX_PELA_CONTA["r55"], "conferido_em": "2026-01-01"})]),
                 "codex com treinamento ligado": dict(outras_llm=[dict(CODEX_PELA_CONTA, r55={
                     **CODEX_PELA_CONTA["r55"], "treinamento_desligado": False})]),
                 "perfil copiado": dict(perfil_navegador_copiado={"origem": "data/x_browser_profile"})}
        for nome, secoes in casos.items():
            with self.subTest(nome):
                ab = self.ab(**secoes)
                self.assertFalse(ab["valida"], nome)
                self.assertEqual((ab["rede"], ab["mcp"], ab["outras_llm"]), ([], [], []))

    def test_secao_nova_vazia_vale_e_nao_conta_como_lida(self):
        ab = self.ab(mcp=[], navegador={}, outras_llm=[])
        self.assertTrue(ab["valida"], ab["motivo"])
        self.assertEqual(ab["secoes_lidas_nao_aplicadas"], [])


MCP_POR_URL = {"nome": "fsn", "origem": "url", "url": "https://mcp.exemplo.org/escritorio",
               "ferramentas": ["buscar_clientes", "get_processo"], "ocultar": ["escanear_vault"],
               "conteudo_de_terceiros": True}
# Decisão do titular de 08/11/2026: a gravação do conector vale se a ficha a lista, como a consulta.
MCP_COM_GRAVACAO = dict(MCP_DO_ESCRITORIO, ferramentas=["buscar_clientes", "get_processo", "salvar_nota", "propor_operacoes",
                                                     "confirmar_operacoes"], ocultar=["escanear_vault"])
SERVIDOR_DA_CONTA = "claude_ai_Conector_do_escritorio"  # [medir M3] o nome que o preparo espera
LANCADOR_VALORES = {
    "RAIZ": RAIZ, "PROJETO": "caso-real", "USUARIO": "titular", "AREA": "/etc/fundacao-ia/projetos/caso-real",
    "SKILL": "/etc/fundacao-ia/skill/1.7.11-abc", "CLAUDE_BIN": "/etc/fundacao-ia/claude/2.1.302/claude",
    "CLAUDE_VERSAO": "2.1.302", "CLAUDE_SHA256": "1" * 64, "CLAUDE_ORIGEM_HASH": "manifesto assinado",
    "FERRAMENTAS": "Bash,Read", "PLUGINS": "", "PREPARO_SHA256": "2" * 64, "PORTEIRO_SHA256": "3" * 64,
    "TEMP_PROJETO": "/tmp/fundacao-ia-caso-real", "SONDA_INTEROP_CMD": "/mnt/c/Windows/System32/cmd.exe",
    "SONDA_INTEROP_BINFMT": "/proc/sys/fs/binfmt_misc"}


class McpDoEscritorioNoPerfil(Base):
    """1.7.11, lote L2 (DESENHO-JAULA §4 e §7.3): o perfil, o mcp.json e a conferência do MCP da ficha. As aberturas são
    montadas direto (a regra da ficha é do kit, testada lá), para a prova não depender do que o kit aceita."""

    def ab(self, *mcp, valida=True):
        return {**self.m.aberturas_fechadas(), "valida": valida, "mcp": list(mcp)}

    def test_origem_conta_liga_o_conector_e_lista_as_ferramentas_exatas(self):
        ab = self.ab(MCP_DO_ESCRITORIO)
        p = self.perfil(aberturas=ab)
        env = p["env"]
        self.assertEqual(env["FUNDACAO_MCP_PERMITIDAS"], SERVIDOR_DA_CONTA)
        nomes = [f"mcp__{SERVIDOR_DA_CONTA}__{f}" for f in MCP_DO_ESCRITORIO["ferramentas"]]
        self.assertEqual(env["FUNDACAO_MCP_FERRAMENTAS"], ",".join(nomes))
        self.assertEqual(p["permissions"]["allow"], nomes)
        for oculta in MCP_DO_ESCRITORIO["ocultar"]:
            self.assertIn(f"mcp__{SERVIDOR_DA_CONTA}__{oculta}", p["permissions"]["deny"])
        self.assertEqual(env["MAX_MCP_OUTPUT_TOKENS"], "25000")
        self.assertIs(p["disableClaudeAiConnectors"], False)
        self.assertEqual(self.m.conferir_perfil_wsl(p, RAIZ, "caso-real", aberturas=ab), [])
        self.assertEqual(self.m.mcp_json(self.m.mcp_da_ficha(ab)), {"mcpServers": {}})  # a conta não usa o arquivo
        self.assertFalse(self.m.mcp_da_ficha(ab)["estrito"])  # [medir M3] a rota conta abre sem o --strict-mcp-config

    def test_origem_url_poe_o_servidor_no_mcp_json_e_deixa_os_conectores_desligados(self):
        ab = self.ab(MCP_POR_URL)
        p = self.perfil(aberturas=ab)
        self.assertEqual(p["env"]["FUNDACAO_MCP_PERMITIDAS"], "fsn")
        self.assertEqual(p["env"]["FUNDACAO_MCP_FERRAMENTAS"], "mcp__fsn__buscar_clientes,mcp__fsn__get_processo")
        self.assertIs(p["disableClaudeAiConnectors"], True)
        mcp = self.m.mcp_da_ficha(ab)
        self.assertTrue(mcp["estrito"])
        self.assertEqual(self.m.mcp_json(mcp), {"mcpServers": {"fsn": {"type": "http", "url": MCP_POR_URL["url"]}}})
        self.assertEqual(self.m.conferir_perfil_wsl(p, RAIZ, "caso-real", aberturas=ab), [])

    def test_ferramenta_de_gravacao_listada_vale_como_a_de_consulta(self):
        ab = self.ab(MCP_COM_GRAVACAO)
        p = self.perfil(aberturas=ab)
        for f in ("salvar_nota", "propor_operacoes", "confirmar_operacoes"):
            self.assertIn(f"mcp__{SERVIDOR_DA_CONTA}__{f}", p["env"]["FUNDACAO_MCP_FERRAMENTAS"].split(","))
            self.assertIn(f"mcp__{SERVIDOR_DA_CONTA}__{f}", p["permissions"]["allow"])
        self.assertEqual(self.m.conferir_perfil_wsl(p, RAIZ, "caso-real", aberturas=ab), [])  # sem invariante de gravação
        self.assertTrue(self.m.conferir_perfil_wsl(p, RAIZ, "caso-real", aberturas=self.ab()))  # ficha fechada: acusa

    def test_nome_velho_consulta_e_recusado_com_mensagem_clara(self):
        """DECISAO-011: o campo `consulta` virou `ferramentas`. Nenhuma ficha assinada tinha a seção, então não há
        migração: o nome velho é recusado (no perfil e na ficha lida), com a mensagem que diz o novo."""
        velho = {k: v for k, v in MCP_POR_URL.items() if k != "ferramentas"}
        velho["consulta"] = ["buscar_clientes", "get_processo"]
        for ab in (self.ab(velho), self.ab({**velho, "ferramentas": ["buscar_clientes"]})):  # sem a nova e com as duas
            with self.assertRaises(self.m.EntradaInvalida) as ctx:
                self.m.mcp_da_ficha(ab)
            self.assertIn('renomeado para "ferramentas"', str(ctx.exception))
            with self.assertRaises(self.m.EntradaInvalida):
                self.perfil(aberturas=ab)
        lida = self.m.aberturas_da_ficha(resultado_de_ensaio(mcp=[velho]), "caso-real")
        self.assertFalse(lida["valida"])
        self.assertIn("consulta", lida["motivo"])
        self.assertTrue(self.m.aberturas_da_ficha(resultado_de_ensaio(mcp=[MCP_POR_URL]), "caso-real")["valida"])

    def test_sem_a_secao_o_perfil_e_o_de_antes(self):
        fechado = self.perfil()
        self.assertNotIn("FUNDACAO_AGENTES", fechado["env"])  # sem ficha válida, a variável dos agentes não existe
        self.assertEqual(fechado["env"]["FUNDACAO_SKILLS"], "-")  # F8 e F13: e a das skills sai "-" (o guarda nega a Skill)
        self.assertIs(fechado["disableSkillShellExecution"], True)  # F8: sem o `!` do corpo das skills
        self.assertEqual(self.perfil(aberturas=self.m.aberturas_fechadas()), fechado)
        com_ficha = self.perfil(aberturas=self.ab())  # ficha válida sem MCP: as duas variáveis do lote A2 (agentes vazia, skills "-")
        self.assertEqual((com_ficha["env"].pop("FUNDACAO_AGENTES"), com_ficha["env"]["FUNDACAO_SKILLS"]), ("", "-"))
        self.assertEqual(com_ficha, fechado)
        self.assertEqual(fechado["env"]["FUNDACAO_MCP_PERMITIDAS"], "")
        self.assertEqual(fechado["env"]["FUNDACAO_MCP_FERRAMENTAS"], "")  # presente e vazia: o guarda fica estrito
        self.assertNotIn("MAX_MCP_OUTPUT_TOKENS", fechado["env"])
        self.assertFalse([r for r in fechado["permissions"]["allow"] + fechado["permissions"]["deny"]
                          if r.startswith("mcp__")])
        self.assertIs(fechado["disableClaudeAiConnectors"], True)
        self.assertEqual(self.m.mcp_json(None), {"mcpServers": {}})
        self.assertIsNone(self.m.mcp_da_ficha(self.ab()))

    def test_perfil_adulterado_e_acusado(self):
        ab = self.ab(MCP_DO_ESCRITORIO)
        bom = self.perfil(aberturas=ab)
        servidor = f"mcp__{SERVIDOR_DA_CONTA}__"
        casos = {
            "ferramenta a mais na lista": lambda p: p["env"].update(
                FUNDACAO_MCP_FERRAMENTAS=p["env"]["FUNDACAO_MCP_FERRAMENTAS"] + "," + servidor + "salvar_nota"),
            "ferramenta a mais só no allow": lambda p: p["permissions"]["allow"].append(servidor + "salvar_nota"),
            "ferramenta a menos no allow": lambda p: p["permissions"]["allow"].pop(),
            "servidor com curinga": lambda p: p["env"].update(FUNDACAO_MCP_PERMITIDAS="mcp__*"),
            "dois servidores": lambda p: p["env"].update(FUNDACAO_MCP_PERMITIDAS=SERVIDOR_DA_CONTA + ",outro"),
            "outro servidor": lambda p: p["env"].update(FUNDACAO_MCP_PERMITIDAS="outro"),
            "lista de outro servidor": lambda p: p["env"].update(FUNDACAO_MCP_FERRAMENTAS="mcp__outro__buscar_x"),
            "lista sem a variável": lambda p: p["env"].pop("FUNDACAO_MCP_FERRAMENTAS"),
            "lista vazia com servidor": lambda p: p["env"].update(FUNDACAO_MCP_FERRAMENTAS=""),
            "nome com dois separadores": lambda p: p["env"].update(
                FUNDACAO_MCP_FERRAMENTAS=p["env"]["FUNDACAO_MCP_FERRAMENTAS"] + "," + servidor + "a__b"),
            "ferramenta escondida liberada": lambda p: p["permissions"]["deny"].remove(servidor + "escanear_vault"),
            "conectores da conta desligados": lambda p: p.update(disableClaudeAiConnectors=True),
            "sem teto de resposta": lambda p: p["env"].pop("MAX_MCP_OUTPUT_TOKENS"),
        }
        for nome, mudanca in casos.items():
            with self.subTest(nome):
                p = copy.deepcopy(bom)
                mudanca(p)
                self.assertTrue(self.m.conferir_perfil_wsl(p, RAIZ, "caso-real", aberturas=ab), nome)
        fora = {"conectores ligados": lambda p: p.update(disableClaudeAiConnectors=False),
                "servidor sem ficha": lambda p: p["env"].update(FUNDACAO_MCP_PERMITIDAS="fsn"),
                "allow de MCP sem ficha": lambda p: p["permissions"]["allow"].append("mcp__fsn__x"),
                "lista sem ficha": lambda p: p["env"].update(FUNDACAO_MCP_FERRAMENTAS="mcp__fsn__x")}
        for nome, mudanca in fora.items():  # fora da ficha: conectores ligados, ou MCP no perfil, sem a seção
            with self.subTest(nome):
                p = self.perfil()
                mudanca(p)
                self.assertTrue(self.m.conferir_perfil_wsl(p, RAIZ, "caso-real", aberturas=self.ab()), nome)
                self.assertTrue(self.m.conferir_perfil_wsl(p, RAIZ, "caso-real"), nome)
        self.assertTrue(self.m.conferir_perfil_wsl(bom, RAIZ, "caso-real"))  # o perfil com MCP, sem ficha vigente

    def test_forma_da_secao_recusada_pelo_preparo(self):
        ruins = {"dois servidores": [MCP_DO_ESCRITORIO, MCP_POR_URL],
                 "ferramentas vazia": [dict(MCP_POR_URL, ferramentas=[])],
                 "nome com dois sublinhados": [dict(MCP_POR_URL, ferramentas=["buscar__x"])],
                 "nome com sublinhado no fim": [dict(MCP_POR_URL, ferramentas=["buscar_"])],
                 "nome repetido": [dict(MCP_POR_URL, ferramentas=["buscar_x", "buscar_x"])],
                 "nome com maiúscula": [dict(MCP_POR_URL, ferramentas=["Buscar_x"])],
                 "ferramenta em ferramentas e em ocultar": [dict(MCP_POR_URL, ocultar=["get_processo"])],
                 "mais de 40 ferramentas": [dict(MCP_POR_URL, ferramentas=[f"buscar_{i}" for i in range(41)])],
                 "url http": [dict(MCP_POR_URL, url="http://mcp.exemplo.org/x")],
                 "url com porta": [dict(MCP_POR_URL, url="https://mcp.exemplo.org:8443/x")],
                 "url com usuário": [dict(MCP_POR_URL, url="https://u" + "@" + "mcp.exemplo.org/x")],
                 "origem desconhecida": [dict(MCP_POR_URL, origem="local")],
                 "conector só com símbolos": [dict(MCP_DO_ESCRITORIO, conector="!!!")],
                 "nome do servidor fora da forma": [dict(MCP_POR_URL, nome="Fsn")]}
        for nome, lista in ruins.items():
            with self.subTest(nome), self.assertRaises(self.m.EntradaInvalida):
                self.m.mcp_da_ficha(self.ab(*lista))
        # o conector sem letra nem número é recusado já na leitura da ficha: tudo fechado
        fechada = self.m.aberturas_da_ficha(resultado_de_ensaio(mcp=[dict(MCP_DO_ESCRITORIO, conector="!!!")]),
                                            "caso-real", date(2026, 11, 9))
        self.assertFalse(fechada["valida"])

    def test_nome_do_servidor_da_conta(self):
        for conector, esperado in (("Conector do escritorio", SERVIDOR_DA_CONTA), ("Meu.Conector", "claude_ai_Meu_Conector"),
                                   ("A  B", "claude_ai_A_B"), (" x-y ", "claude_ai_x-y"), ("Ç!a", "claude_ai_a")):
            with self.subTest(conector=conector):
                self.assertEqual(self.m.servidor_do_conector(conector), esperado)
        for ruim in ("", "!!!", None, 3):
            with self.subTest(ruim=ruim), self.assertRaises(self.m.EntradaInvalida):
                self.m.servidor_do_conector(ruim)

    def test_lancador_recebe_o_que_esconder_e_se_e_estrito(self):
        """O texto do lançador (sem rodá-lo): MCP_OCULTAR e MCP_ESTRITO vêm dos valores, com a forma conferida."""
        padrao = self.m.lancador(LANCADOR_VALORES)
        self.assertIn("MCP_ESTRITO='1'", padrao)
        self.assertIn("MCP_OCULTAR=''", padrao)
        oculta = "mcp__fsn__escanear_vault,mcp__fsn__validar_frontmatter"
        com = self.m.lancador({**LANCADOR_VALORES, "MCP_ESTRITO": "0", "MCP_OCULTAR": oculta})
        self.assertIn("MCP_ESTRITO='0'", com)
        self.assertIn(f"MCP_OCULTAR='{oculta}'", com)
        for chave, ruim in (("MCP_ESTRITO", "2"), ("MCP_ESTRITO", ""), ("MCP_OCULTAR", "Bash"),
                            ("MCP_OCULTAR", "mcp__fsn__a,"), ("MCP_OCULTAR", "mcp__fsn__a; rm"),
                            ("MCP_OCULTAR", "mcp__fsn__a mcp__fsn__b")):
            with self.subTest(chave=chave, ruim=ruim), self.assertRaises(ValueError):
                self.m.lancador({**LANCADOR_VALORES, chave: ruim})


class McpNaConferenciaDaAbertura(Base):
    """`conferir-abertura` (lote L2): o perfil tem o MCP que o hashes.json registrou; e, sem o --strict-mcp-config (origem
    conta), o `.claude.json` da configuração do projeto não traz servidores MCP próprios."""

    def setUp(self):
        super().setUp()
        self.base = Path(tempfile.mkdtemp(prefix="mcp-abertura-")).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.area = self.base / "area"
        self.area.mkdir()
        self.casa = self.base / "casa"
        self.config = self.casa / ".local" / "share" / "fundacao-ia" / "config" / "caso-real"
        self.config.mkdir(parents=True)
        ab = {**self.m.aberturas_fechadas(), "valida": True, "mcp": [MCP_DO_ESCRITORIO]}
        self.mcp = self.m.mcp_da_ficha(ab)
        self.perfil_conta = self.perfil(aberturas=ab)
        self.registro = {k: self.mcp[k] for k in ("nome", "origem", "servidor", "ferramentas", "ocultar", "estrito")}
        self.hashes = {"casa": self.casa.as_posix(), "mcp": self.registro}

    def gravar_perfil(self, perfil):
        (self.area / "settings.wsl.json").write_text(json.dumps(perfil), encoding="utf-8")

    def problemas(self, hashes=None):
        return self.m.problemas_do_mcp_da_abertura(self.area, self.hashes if hashes is None else hashes, "caso-real")

    def test_conta_sem_servidores_proprios_confere(self):
        self.gravar_perfil(self.perfil_conta)
        self.assertEqual(self.problemas(), [])
        (self.config / ".claude.json").write_text(json.dumps({"mcpServers": {}, "projects": {"/x": {"mcpServers": {}}}}),
                                                  encoding="utf-8")
        self.assertEqual(self.problemas(), [])

    def test_servidor_proprio_no_claude_json_nao_abre(self):
        self.gravar_perfil(self.perfil_conta)
        for dados in ({"mcpServers": {"x": {"command": "x"}}}, {"projects": {"/p": {"mcpServers": {"x": {}}}}}):
            with self.subTest(dados=dados):
                (self.config / ".claude.json").write_text(json.dumps(dados), encoding="utf-8")
                achados = self.problemas()
                self.assertTrue(any("servidores MCP próprios" in a for a in achados), achados)
        (self.config / ".claude.json").write_text("{", encoding="utf-8")
        self.assertTrue(any("ilegível" in a for a in self.problemas()))
        # com o --strict-mcp-config (origem url) o arquivo nem é aberto
        (self.config / ".claude.json").write_text(json.dumps({"mcpServers": {"x": {}}}), encoding="utf-8")
        url = {**self.m.aberturas_fechadas(), "valida": True, "mcp": [MCP_POR_URL]}
        self.gravar_perfil(self.perfil(aberturas=url))
        registro_url = {k: v for k, v in self.m.mcp_da_ficha(url).items() if k in self.registro}
        self.assertEqual(self.problemas({**self.hashes, "mcp": registro_url}), [])

    def test_perfil_diferente_do_registro_ou_sem_registro_nao_abre(self):
        self.gravar_perfil(self.perfil_conta)
        self.assertTrue(self.problemas({**self.hashes, "mcp": None}))  # o perfil abre MCP e o registro não
        menos = {**self.registro, "ferramentas": self.registro["ferramentas"][:-1]}
        self.assertTrue(self.problemas({**self.hashes, "mcp": menos}))
        self.gravar_perfil(self.perfil())  # perfil fechado e registro com MCP
        self.assertTrue(self.problemas())
        self.assertEqual(self.problemas({**self.hashes, "mcp": None}), [])
        self.assertTrue(self.problemas({**self.hashes, "mcp": "texto"}))
        (self.area / "settings.wsl.json").write_text("{", encoding="utf-8")
        self.assertTrue(self.problemas({**self.hashes, "mcp": None}))

    def test_sem_a_casa_no_registro_nao_abre_sem_strict(self):
        self.gravar_perfil(self.perfil_conta)
        self.assertTrue(any("casa" in a for a in self.problemas({"mcp": self.registro})))


class CuringaCobreODominioPrincipal(Base):
    """DECISAO-010, item 5: na ficha `*.x` vale para `x` e para os subdomínios; o perfil gera `x` e `*.x`."""

    def test_perfil_gera_x_e_curinga_na_rede_no_webfetch_e_no_hook(self):
        ab = self.m.aberturas_da_ficha(resultado_de_ensaio(rede={"dominios": ["*.tjsp.jus.br", "pypi.org"]},
                                                           webfetch={"dominios": ["*.tjsp.jus.br"]}), "caso-real")
        self.assertTrue(ab["valida"], ab["motivo"])
        p = self.perfil(aberturas=ab)
        self.assertEqual(p["sandbox"]["network"]["allowedDomains"], ["tjsp.jus.br", "*.tjsp.jus.br", "pypi.org"])
        self.assertEqual(p["permissions"]["allow"], ["WebFetch(domain:tjsp.jus.br)", "WebFetch(domain:*.tjsp.jus.br)"])
        self.assertEqual(p["env"]["FUNDACAO_DOMINIOS_WEB"], "tjsp.jus.br,*.tjsp.jus.br")
        self.assertEqual(self.m.conferir_perfil_wsl(p, RAIZ, "caso-real", aberturas=ab), [])
        # a leitura do próprio perfil reconstrói o mesmo perfil: a expansão é idempotente
        vagas = self.m.parametros_do_perfil_wsl(p, RAIZ, "caso-real")
        self.assertEqual(vagas["aberturas"]["rede"], ["tjsp.jus.br", "*.tjsp.jus.br", "pypi.org"])
        # o perfil não diz quais plugins a ficha tem (isso é o lote A2): a parte dos plugins vem da ficha
        lido = {**vagas["aberturas"], "valida": ab["valida"], "plugins": ab["plugins"], "skills": []}
        self.assertEqual(self.perfil(aberturas=lido), p)

    def test_prova_negativa_nao_cobre_outro_nome(self):
        ab = self.m.aberturas_da_ficha(resultado_de_ensaio(rede={"dominios": ["*.x.com"]}), "caso-real")
        p = self.perfil(aberturas=ab)
        rede = p["sandbox"]["network"]["allowedDomains"]
        self.assertEqual(rede, ["x.com", "*.x.com"])
        self.assertNotIn("outrox.com", rede)
        self.assertNotIn("x.com.outro", rede)
        # a conferência exige a lista exata: sem a expansão, ou com um nome a mais, o perfil é acusado
        p["sandbox"]["network"]["allowedDomains"] = ["*.x.com"]
        self.assertTrue(self.m.conferir_perfil_wsl(p, RAIZ, "caso-real", aberturas=ab))
        p["sandbox"]["network"]["allowedDomains"] = ["x.com", "*.x.com", "outrox.com"]
        self.assertTrue(self.m.conferir_perfil_wsl(p, RAIZ, "caso-real", aberturas=ab))

    def test_curinga_em_sufixo_publico_continua_recusado(self):
        for dominio in ("*.com", "*.com.br", "*.gov.br", "*.vercel.app"):
            with self.subTest(dominio):
                self.assertFalse(self.m.aberturas_da_ficha(resultado_de_ensaio(rede={"dominios": [dominio]}),
                                                           "caso-real")["valida"])

    def test_expandir_e_a_mesma_regra_do_kit(self):
        regras_do_kit = self.m.modulos_do_kit().regras
        for lista in (["a.com"], ["*.a.com"], ["*.a.com", "a.com"], ["a.com", "*.a.com", "*.b.org", "c.net"],
                      ["*.b.org", "b.org"], []):
            with self.subTest(lista=lista):
                self.assertEqual(self.m.expandir_curingas(lista), regras_do_kit.expandir_curingas(lista))
                self.assertEqual(self.m.expandir_curingas(self.m.expandir_curingas(lista)),
                                 self.m.expandir_curingas(lista))  # idempotente


class ConferirPerfil(Base):
    """`conferir-perfil-wsl`: os invariantes, o perfil inteiro igual ao gerado e a lista do --tools."""

    def conferir(self, perfil, **kw):
        return self.m.conferir_perfil_wsl(perfil, RAIZ, "caso-real", ["lab-a", "lab-b"], **kw)

    def test_gerado_passa(self):
        self.assertEqual(self.conferir(self.perfil()), [])
        self.assertEqual(self.m.conferir_perfil_wsl(self.perfil(), RAIZ), [])

    def test_enfraquecimentos_sao_acusados(self):
        def fs(p):
            return p["sandbox"]["filesystem"]

        casos = {
            "mãe da fila negada": lambda p: fs(p)["denyWrite"].append(PROJ + "/.porteiro"),
            "respostas graváveis": lambda p: fs(p)["denyWrite"].remove(PROJ + "/.porteiro/respostas"),
            "state legível": lambda p: fs(p)["allowRead"].append(RAIZ + "/state"),
            "state gravável": lambda p: fs(p)["allowWrite"].append(RAIZ + "/state"),
            "state sem negação": lambda p: p["permissions"]["deny"].remove(f"Read(/{RAIZ}/state/**)"),
            "outra identidade": lambda p: p["env"].update({IDENTIDADE: "titular"}),
            "ferramenta a mais": lambda p: p["env"].update(FUNDACAO_FERRAMENTAS=p["env"]["FUNDACAO_FERRAMENTAS"] + ",Task"),
            "rede aberta": lambda p: p["sandbox"]["network"]["allowedDomains"].append("exemplo.invalid"),
            "rede sem lista estrita": lambda p: p["sandbox"]["network"].update(strictAllowlist=False),
            "plano A desligado": lambda p: p["permissions"].update(blockReadsOutsideWorkingDirectories=False),
            "outro projeto legível": lambda p: p["permissions"]["deny"].remove(f"Read(/{RAIZ}/projects/lab-a/**)"),
            "casa legível": lambda p: p["permissions"]["deny"].remove("Read(~/.claude/projects/**)"),
            "socket visível": lambda p: fs(p)["denyRead"].remove("/run"),
            "web liberada": lambda p: p["permissions"]["deny"].remove("WebFetch"),
            "mcp liberado": lambda p: p["env"].update(FUNDACAO_MCP_PERMITIDAS="mcp__*"),
            "hook sem -I": lambda p: p["hooks"]["PreToolUse"][0]["hooks"][0].update(args=["-B", "x.py"]),
            "matcher trocado": lambda p: p["hooks"]["PreToolUse"][0].update(matcher=".*"),
            "escrita fora do projeto": lambda p: fs(p)["allowWrite"].append("/mnt/d"),
            "comando excluído": lambda p: p["sandbox"].update(excludedCommands=["git"]),
            "chave desconhecida": lambda p: p.update(apiKeyHelper="/tmp/x"),
            "troca de identidade": lambda p: p["env"].update(FUNDACAO_PERMITIR_TROCA_IDENTIDADE="1"),
            "travado no perfil": lambda p: p["env"].update(FUNDACAO_PROJETO_TRAVADO="caso-real"),
        }
        for nome, mudanca in casos.items():
            with self.subTest(nome):
                p = self.perfil()
                mudanca(p)
                self.assertTrue(self.conferir(p), nome)

    def test_projeto_criado_depois_e_acusado_e_o_que_saiu_nao_libera(self):
        problemas = self.m.conferir_perfil_wsl(self.perfil(), RAIZ, "caso-real", ["lab-a", "lab-b", "lab-novo"])
        self.assertTrue(any("lab-novo" in p for p in problemas), problemas)
        self.assertEqual(self.m.conferir_perfil_wsl(self.perfil(), RAIZ, "caso-real", ["lab-a"]), [])

    def test_vagas_confiaveis_valem_mais_que_as_do_perfil(self):
        p = self.perfil()
        par = {"perfil_windows": "/mnt/c/Users/<usuario>", "ancora_base": "/mnt/c/ProgramData/FundacaoIA",
               "temp_base": "/tmp"}
        self.assertEqual(self.conferir(p, parametros=par, somente_leitura=["/mnt/d/Origem Ç"], negar=["squad-x"]), [])
        self.assertTrue(self.conferir(p, parametros={**par, "perfil_windows": "/mnt/c/Users/<usuario>-outro"}))
        self.assertTrue(self.conferir(p, somente_leitura=[]))  # pasta só de leitura que o registro não tem
        self.assertTrue(self.conferir(p, negar=["squad-x", "squad-y"]))  # negação que sumiu do perfil

    def test_ferramentas_iguais_as_do_lancador(self):
        p = self.perfil()
        self.assertEqual(self.conferir(p, ferramentas_lancador=p["env"]["FUNDACAO_FERRAMENTAS"]), [])
        self.assertTrue(any("--tools" in x for x in self.conferir(p, ferramentas_lancador="Bash,Read")))


class LinhaDeComando(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="perfil-projeto-1710-"))
        self.raiz = self.base / "Fundacao Exemplo"
        for nome in ("caso-real", "lab-a"):
            (self.raiz / "projects" / nome).mkdir(parents=True)
        self.area = self.base / "area-inexistente"

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_gerar_e_conferir(self):
        saida = self.base / "settings.wsl.json"
        comum = ("--raiz", self.raiz, "--projeto", "caso-real", "--perfil-windows", "/mnt/c/Users/<usuario>",
                 "--area-raiz", self.area)
        r = rodar("gerar-perfil-projeto", *comum, "--saida", saida)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        perfil = json.loads(saida.read_text(encoding="utf-8"))
        self.assertTrue(perfil["sandbox"]["network"]["strictAllowlist"])
        r = rodar("conferir-perfil-wsl", "--perfil", saida, *comum)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(json.loads(r.stdout)["ok"])
        (self.raiz / "projects" / "lab-novo").mkdir()
        r = rodar("conferir-perfil-wsl", "--perfil", saida, *comum)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("lab-novo", r.stdout)

    def test_projeto_ausente_e_backups_recusados_sem_gravar(self):
        saida = self.base / "perfil.json"
        for extra in (("--projeto", "nao-existe"), ("--projeto", "caso-real", "--backups", r"D:\Backups")):
            with self.subTest(extra=extra):
                r = rodar("gerar-perfil-projeto", "--raiz", self.raiz, "--perfil-windows", "/mnt/c/Users/<usuario>",
                          "--area-raiz", self.area, *extra, "--saida", saida)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertFalse(saida.exists())


class ModeloDoPerfil(unittest.TestCase):
    def test_modelo_sem_cr_e_com_o_matcher_documentado_de_todas(self):
        bruto = (SKILL / "assets" / "host" / "wsl" / "settings.wsl.json").read_bytes()
        self.assertNotIn(b"\r", bruto)
        modelo = json.loads(bruto.decode("utf-8"))
        matchers = [g["matcher"] for g in modelo["hooks"]["PreToolUse"]]
        self.assertIn("*", matchers)  # "todas" na documentação; ".*" o alertas_hooks acusa como "casa tudo"
        self.assertNotIn(".*", matchers)


if __name__ == "__main__":
    unittest.main()
