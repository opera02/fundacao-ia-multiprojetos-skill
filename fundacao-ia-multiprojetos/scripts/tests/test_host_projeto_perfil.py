"""Perfil do projeto no Ubuntu (1.7.10; contratos do lote 2, §3, §6 e §7; folha do HOST, itens 1 e 2).

O perfil sai do modelo `assets/host/wsl/settings.wsl.json` com o plano A (bloqueio de leitura fora das pastas de
trabalho e rede com lista estrita) mais as negações nominais do plano B — com a raiz em /mnt/e o sandbox não confinou
os comandos nas sondas de 31/10/2026, e o isolamento é lógico até o canário passar. Os segredos vêm da regra única
(fortes + pastas, nunca os fracos); `state/` fica fora do sandbox (negado e sem allowRead nem allowWrite); a fila do
porteiro só tem `respostas/` negada; a identidade é `sessao-<p>`; a ficha assinada é a única fonte de rede, WebFetch,
WebSearch e plugins (sem ficha, tudo fechado). Só biblioteca padrão; nada do host é lido nem alterado.
"""

from __future__ import annotations

import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
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
        self.assertEqual(env["FUNDACAO_FERRAMENTAS"], "Bash,Read,Edit,Write,Glob,Grep,Skill,Task,TodoWrite")
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
                    self.assertEqual(h["onFailure"], "block")
                    vistos[(evento, g["matcher"])] = Path(h["args"][2]).name
                    self.assertTrue(h["args"][2].startswith(RAIZ + "/.claude/hooks/"))
        self.assertEqual(vistos, {("SessionStart", "compact"): "sinais_sessao.py",
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
        self.assertEqual(p["sandbox"]["network"]["allowedDomains"], ["pypi.org", "*.pythonhosted.org"])
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
                 "reservada 1.7.11": dict(mcp=[{"nome": "x"}]),
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
            "ferramenta a mais": lambda p: p["env"].update(FUNDACAO_FERRAMENTAS=p["env"]["FUNDACAO_FERRAMENTAS"] + ",Agent"),
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
