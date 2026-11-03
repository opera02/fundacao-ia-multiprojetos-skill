"""Hooks da 1.7.10 (contratos do lote 2, §7): auxiliares comuns, `guarda_ferramentas.py` e o que vale para todos.

`guarda_ferramentas.py` (PreToolUse `.*`, só no perfil WSL de projeto): lista positiva de FUNDACAO_FERRAMENTAS (a mesma
do `--tools` do lançador); `mcp__<servidor>__*` só com o servidor em FUNDACAO_MCP_PERMITIDAS; variável ausente ou
vazia nega tudo. Para os hooks novos (`guarda_ferramentas`, `guarda_rede`, `guarda_leitura`, `aviso_copia`) e o
`guarda_identidade`: só biblioteca padrão, rodam com `-I -B`, falham fechados (os PreToolUse) ou calam sem bloquear
(o aviso), saem com JSON só com ASCII e não abrem arquivo (o aviso abre só o registro da última cópia, no teste dele).
Os docstrings dizem a verdade do §0: guarda-corpo, e com a raiz em /mnt/e o sandbox não confina os comandos.

Eventos fictícios pela entrada padrão; ambiente sem as FUNDACAO_* da sessão que roda os testes.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

from apoio import ENV, SKILL

HOOKS = SKILL / "assets" / "hooks"
NOVOS = ("guarda_ferramentas.py", "guarda_rede.py", "guarda_leitura.py", "aviso_copia.py")
PRE_TOOL_USE = ("guarda_ferramentas.py", "guarda_rede.py", "guarda_leitura.py", "guarda_identidade.py")
FERRAMENTAS = "Bash,Read,Edit,Write,Glob,Grep,Skill,Agent,TodoWrite"


def ambiente(**variaveis: str) -> dict:
    """Sem as FUNDACAO_* nem o CLAUDE_PROJECT_DIR de quem roda os testes (numa sessão, apontariam a raiz real)."""
    env = {k: v for k, v in ENV.items() if not k.startswith("FUNDACAO_") and k != "CLAUDE_PROJECT_DIR"}
    env.update(variaveis)
    return env


def rodar(hook: str, entrada, timeout: int = 30, **variaveis: str) -> subprocess.CompletedProcess:
    """O hook como o host o chama (`python -I -B`), com a entrada em bytes (objeto vira JSON)."""
    dados = entrada if isinstance(entrada, bytes) else json.dumps(entrada).encode("utf-8")
    return subprocess.run([sys.executable, "-I", "-B", str(HOOKS / hook)], input=dados, capture_output=True,
                          env=ambiente(**variaveis), timeout=timeout)


def decisao(hook: str, entrada, **variaveis: str) -> str:
    """`deny`, `sem_decisao` ou o erro do processo (a saída tem de ser JSON só com ASCII)."""
    p = rodar(hook, entrada, **variaveis)
    if p.returncode != 0:
        return f"codigo={p.returncode}: {p.stderr[-200:]!r}"
    if not p.stdout.strip():
        return "sem_decisao"
    if not p.stdout.isascii():
        return "saida-nao-ascii"
    saida = json.loads(p.stdout)["hookSpecificOutput"]
    if saida.get("hookEventName") != "PreToolUse":
        return f"evento-errado: {saida}"
    return saida["permissionDecision"]


def motivo(hook: str, entrada, **variaveis: str) -> str:
    p = rodar(hook, entrada, **variaveis)
    return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecisionReason"] if p.stdout.strip() else ""


def carregar(hook: str):
    """O módulo do hook, para chamar `decide` direto (sem __pycache__ em assets/hooks/)."""
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(Path(hook).stem + "_1710", HOOKS / hook)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# Vigia de auditoria, instalado depois de importar o hook: abrir arquivo (salvo o de PERMITIDO, se houver), listar
# pasta, criar socket ou processo encerra na hora com o código 97 — o `main()` dos hooks engole exceção e negaria
# calado.
VIGIA = """
import os, runpy, sys
m = runpy.run_path(sys.argv[1])
PERMITIDO = os.path.normcase(sys.argv[2]) if len(sys.argv) > 2 else None
def vigia(evento, args):
    if evento == 'open' and PERMITIDO and os.path.normcase(str(args[0])) == PERMITIDO:
        return
    if evento in ('open', 'os.listdir', 'os.scandir', 'socket.__new__', 'subprocess.Popen'):
        os.write(2, ('IO negada: ' + evento + ' ' + repr(args)[:200] + chr(10)).encode('utf-8', 'replace'))
        os._exit(97)
sys.addaudithook(vigia)
raise SystemExit(m['main']())
"""


def rodar_vigiado(hook: str, entrada, *permitido: str, **variaveis: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", "-B", "-c", VIGIA, str(HOOKS / hook), *permitido],
                          input=json.dumps(entrada).encode("utf-8"), capture_output=True, env=ambiente(**variaveis),
                          timeout=30)


def ferramenta(nome, **entrada) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": nome, "tool_input": entrada}


class TodosOsHooksDaVersao(unittest.TestCase):
    """Só biblioteca padrão, falha fechada em entrada ruim, saída ASCII e a honestidade do §0 nos docstrings."""

    def test_so_biblioteca_padrao(self):
        for nome in NOVOS + ("guarda_identidade.py",):
            with self.subTest(hook=nome):
                arvore = ast.parse((HOOKS / nome).read_text(encoding="utf-8"))
                importados = {a.name.split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.Import)
                              for a in no.names}
                importados |= {no.module.split(".")[0] for no in ast.walk(arvore)
                               if isinstance(no, ast.ImportFrom) and no.module}
                self.assertEqual(sorted(importados - set(sys.stdlib_module_names) - {"__future__"}), [])

    def test_docstrings_dizem_guarda_corpo_e_o_limite_de_mnt_e(self):
        for nome in PRE_TOOL_USE:
            with self.subTest(hook=nome):
                doc = ast.get_docstring(ast.parse((HOOKS / nome).read_text(encoding="utf-8")))
                self.assertIn("guarda-corpo", doc)
                self.assertIn("/mnt/e", doc)
                self.assertIn("não confin", doc)
        doc = ast.get_docstring(ast.parse((HOOKS / "aviso_copia.py").read_text(encoding="utf-8")))
        self.assertIn("Lembrete, não prova", doc)
        self.assertIn("Nunca bloqueia a sessão", doc)

    def test_entrada_ruim_nega_nos_pre_tool_use(self):
        ruins = (b"", b"isto nao e JSON", b"[1, 2]", b"null", b'"texto"', b'{"tool_name": "Read", "tool_name": "Bash"}',
                 b'{"tool_name": NaN}', b'{"tool_name": "Bash"} {}', b"\xff\xfe", b'{"tool_input": {}}',
                 b'{"tool_name": 7}', b'{"tool_name": ""}', b"[" * 100000 + b"]" * 100000)
        for nome in PRE_TOOL_USE:
            for entrada in ruins:
                with self.subTest(hook=nome, entrada=entrada[:40]):
                    self.assertEqual(decisao(nome, entrada, FUNDACAO_FERRAMENTAS=FERRAMENTAS,
                                             FUNDACAO_PROJECT="juridico-lab"), "deny")

    def test_nao_abrem_arquivo_nem_rede_nem_processo(self):
        eventos = {"guarda_ferramentas.py": ferramenta("Bash", command="ls"),
                   "guarda_rede.py": ferramenta("WebFetch", url="https://docs.exemplo.com.br/x", prompt="resuma"),
                   "guarda_leitura.py": ferramenta("Read", file_path="/tmp/fundacao-ficticia/projects/outro/x.md"),
                   "guarda_identidade.py": ferramenta("Bash", command="cat projects/outro/x.md")}
        variaveis = dict(FUNDACAO_FERRAMENTAS=FERRAMENTAS, FUNDACAO_PROJECT="juridico-lab",
                         FUNDACAO_RAIZ="/tmp/fundacao-ficticia", FUNDACAO_DOMINIOS_WEB="docs.exemplo.com.br")
        esperado = {"guarda_ferramentas.py": b"", "guarda_rede.py": b""}
        for nome, evento in eventos.items():
            with self.subTest(hook=nome):
                p = rodar_vigiado(nome, evento, **variaveis)
                self.assertEqual(p.returncode, 0, p.stderr[-300:])
                self.assertNotIn(b"IO negada", p.stderr)
                if nome in esperado:
                    self.assertEqual(p.stdout, esperado[nome])  # liberado: sem saída
                else:
                    self.assertIn(b'"deny"', p.stdout)  # a negação também sai sem abrir nada

    def test_saida_ascii_mesmo_com_nome_fora_do_cp1252(self):
        p = rodar("guarda_ferramentas.py", ferramenta("Ferramenta☃"), FUNDACAO_FERRAMENTAS=FERRAMENTAS)
        self.assertEqual(p.returncode, 0)
        self.assertTrue(p.stdout.isascii())
        self.assertIn("Ferramenta☃", json.loads(p.stdout)["hookSpecificOutput"]["permissionDecisionReason"])


class GuardaFerramentas(unittest.TestCase):
    HOOK = "guarda_ferramentas.py"

    def setUp(self):
        self.m = carregar(self.HOOK)

    def decide(self, nome, **env):
        return "deny" if self.m.decide({"tool_name": nome, "tool_input": {}}, env) else "sem_decisao"

    def test_ferramenta_da_lista_segue(self):
        for nome in FERRAMENTAS.split(","):
            with self.subTest(nome=nome):
                self.assertEqual(self.decide(nome, FUNDACAO_FERRAMENTAS=FERRAMENTAS), "sem_decisao")
        self.assertEqual(decisao(self.HOOK, ferramenta("Read", file_path="x"), FUNDACAO_FERRAMENTAS=FERRAMENTAS),
                         "sem_decisao")

    def test_fora_da_lista_e_negada_com_o_nome_e_o_caminho_da_ficha(self):
        for nome in ("WebFetch", "WebSearch", "SendMessage", "ListAgents", "RemoteTrigger", "CronCreate", "Artifact",
                     "PushNotification", "EnterWorktree", "FerramentaNovaDe2027", "bash", "BASH", "Bash ", "*"):
            with self.subTest(nome=nome):
                self.assertEqual(self.decide(nome, FUNDACAO_FERRAMENTAS=FERRAMENTAS), "deny")
        texto = motivo(self.HOOK, ferramenta("SendMessage"), FUNDACAO_FERRAMENTAS=FERRAMENTAS)
        for trecho in ("'SendMessage'", "FUNDACAO_FERRAMENTAS", "--tools", "ficha de aberturas", "titular"):
            self.assertIn(trecho, texto)

    def test_lista_ausente_vazia_ou_so_virgulas_nega_tudo(self):
        for valor in (None, "", " ", ",", " , ,"):
            env = {} if valor is None else {"FUNDACAO_FERRAMENTAS": valor}
            for nome in ("Bash", "Read", "mcp__fundacao__status"):
                with self.subTest(valor=valor, nome=nome):
                    self.assertEqual(self.decide(nome, FUNDACAO_MCP_PERMITIDAS="fundacao", **env), "deny")
        self.assertEqual(decisao(self.HOOK, ferramenta("Read", file_path="x")), "deny")
        self.assertIn("FUNDACAO_FERRAMENTAS", motivo(self.HOOK, ferramenta("Read")))

    def test_sem_curinga_na_lista(self):
        for lista in ("*", ".*", "B*", "Bash*"):
            with self.subTest(lista=lista):
                self.assertEqual(self.decide("Bash", FUNDACAO_FERRAMENTAS=lista), "deny")

    def test_mcp_so_com_o_servidor_liberado(self):
        for liberadas in ("fundacao", "mcp__fundacao__*", " outro , fundacao "):
            with self.subTest(liberadas=liberadas):
                self.assertEqual(self.decide("mcp__fundacao__status", FUNDACAO_FERRAMENTAS=FERRAMENTAS,
                                             FUNDACAO_MCP_PERMITIDAS=liberadas), "sem_decisao")
                self.assertEqual(self.decide("mcp__outro2__x", FUNDACAO_FERRAMENTAS=FERRAMENTAS,
                                             FUNDACAO_MCP_PERMITIDAS=liberadas), "deny")
        texto = motivo(self.HOOK, ferramenta("mcp__playwright__navegar"), FUNDACAO_FERRAMENTAS=FERRAMENTAS)
        for trecho in ("'playwright'", "FUNDACAO_MCP_PERMITIDAS", "1.7.11"):
            self.assertIn(trecho, texto)

    def test_mcp_com_lista_vazia_da_1710_ou_padrao_largo_nega(self):
        for liberadas in (None, "", "mcp__*", "mcp__ccd_*", "*", "mcp__fundacao__status", "mcp__fund*__*",
                          "Fundacao"):
            env = {"FUNDACAO_FERRAMENTAS": FERRAMENTAS}
            if liberadas is not None:
                env["FUNDACAO_MCP_PERMITIDAS"] = liberadas
            with self.subTest(liberadas=liberadas):
                self.assertEqual(self.decide("mcp__fundacao__status", **env), "deny")
                self.assertEqual(self.decide("mcp__ccd_session__send_message", **env), "deny")

    def test_nome_mcp_ambiguo_ou_malformado_nega(self):
        for nome in ("mcp__", "mcp____x", "mcp__fundacao__", "mcp__fundacao", "mcp__fundacao__a__b",
                     "mcp__fundacao___x", "mcp__fund acao__x", "mcp__fundacao/x__y"):
            with self.subTest(nome=nome):
                self.assertEqual(self.decide(nome, FUNDACAO_FERRAMENTAS=FERRAMENTAS + ",mcp__fundacao__x",
                                             FUNDACAO_MCP_PERMITIDAS="fundacao"), "deny")

    def test_mcp_na_lista_de_ferramentas_nao_basta(self):
        self.assertEqual(self.decide("mcp__fundacao__status", FUNDACAO_FERRAMENTAS="mcp__fundacao__status"), "deny")

    def test_entrada_grande_de_ferramenta_liberada_segue(self):
        conteudo = "linha ficticia\n" * 200000  # cerca de 3 MB, como um Write grande
        self.assertEqual(decisao(self.HOOK, ferramenta("Write", file_path="x.md", content=conteudo),
                                 FUNDACAO_FERRAMENTAS=FERRAMENTAS), "sem_decisao")

    def test_nome_longo_ou_com_controle_vai_curto_e_limpo_na_mensagem(self):
        texto = motivo(self.HOOK, ferramenta("X" * 5000 + "\n\x1b[31m"), FUNDACAO_FERRAMENTAS=FERRAMENTAS)
        self.assertLess(len(texto), 700)
        self.assertNotIn("\x1b", texto)
        self.assertNotIn("\n", texto)


class GuardaFerramentasAgente(unittest.TestCase):
    """1.7.10.2: a ferramenta de subagentes do Claude Code 2.1.302 (`Agent`; o `Task` antigo vale pelo mesmo item da
    lista) passa com os campos do agente local e um tipo embutido da lista, e é negada com os campos que o levam para a
    nuvem, para uma cópia git, para outra pasta ou para uma equipe, e com agente definido em arquivo (esquema da
    ferramenta lido no binário 2.1.302 em 03/11/2026)."""
    HOOK = "guarda_ferramentas.py"
    LOCAL = {"description": "Revisar o passo 3", "prompt": "Leia outputs/x.md e aponte erros.",
             "subagent_type": "general-purpose", "model": "sonnet", "effort": "high", "run_in_background": False}

    def setUp(self):
        self.m = carregar(self.HOOK)

    def decide(self, nome, entrada, lista=FERRAMENTAS):
        return "deny" if self.m.decide({"tool_name": nome, "tool_input": entrada},
                                       {"FUNDACAO_FERRAMENTAS": lista}) else "sem_decisao"

    def test_agente_local_segue(self):
        for entrada in (self.LOCAL, {"description": "ler", "prompt": "Leia a lei.", "subagent_type": "web-fetch"},
                        {"description": "procurar", "prompt": "Ache os testes.", "subagent_type": "Explore"},
                        {"description": "planejar", "prompt": "Planeje."}, {}):
            with self.subTest(entrada=entrada):
                self.assertEqual(self.decide("Agent", entrada), "sem_decisao")
        self.assertEqual(decisao(self.HOOK, ferramenta("Agent", **self.LOCAL), FUNDACAO_FERRAMENTAS=FERRAMENTAS),
                         "sem_decisao")

    def test_task_e_agent_valem_pelo_mesmo_item_da_lista(self):
        antiga = FERRAMENTAS.replace("Agent", "Task")
        for nome in ("Agent", "Task"):
            for lista in (FERRAMENTAS, antiga):
                with self.subTest(nome=nome, lista=lista):
                    self.assertEqual(self.decide(nome, self.LOCAL, lista), "sem_decisao")
            with self.subTest(nome=nome, lista="sem subagentes"):
                self.assertEqual(self.decide(nome, self.LOCAL, "Bash,Read,Edit,Write"), "deny")
        texto = motivo(self.HOOK, ferramenta("Agent", **self.LOCAL), FUNDACAO_FERRAMENTAS="Bash,Read")
        self.assertIn("'Agent'", texto)
        self.assertIn("FUNDACAO_FERRAMENTAS", texto)

    def test_nuvem_copia_git_outra_pasta_e_equipe_negadas(self):
        casos = {"isolation": ("remote", "worktree"), "cwd": ("/tmp/fundacao-ficticia/projects/outro",),
                 "name": ("revisor",), "team_name": ("equipe",), "mode": ("bypassPermissions", "acceptEdits")}
        for campo, valores in casos.items():
            for valor in valores:
                for nome in ("Agent", "Task"):
                    with self.subTest(campo=campo, valor=valor, nome=nome):
                        self.assertEqual(self.decide(nome, {**self.LOCAL, campo: valor}), "deny")
            texto = motivo(self.HOOK, ferramenta("Agent", **{**self.LOCAL, campo: valores[0]}),
                           FUNDACAO_FERRAMENTAS=FERRAMENTAS)
            for trecho in (f"'{campo}'", "repita sem ele"):
                self.assertIn(trecho, texto)
        texto = motivo(self.HOOK, ferramenta("Agent", **{**self.LOCAL, "isolation": "remote"}),
                       FUNDACAO_FERRAMENTAS=FERRAMENTAS)
        self.assertIn("nuvem", texto)

    def test_tipo_de_subagente_so_os_embutidos_da_lista(self):
        for tipo in ("general-purpose", "web-fetch", "Explore", "Plan"):
            with self.subTest(tipo=tipo):
                self.assertEqual(self.decide("Agent", {**self.LOCAL, "subagent_type": tipo}), "sem_decisao")
        for tipo in ("revisor-juridico", "claude-code-guide", "statusline-setup", "fork", "worker", "general-purpose ",
                     "explore", "", 7, ["general-purpose"], {"tipo": "Plan"}):
            with self.subTest(tipo=tipo):
                self.assertEqual(self.decide("Agent", {**self.LOCAL, "subagent_type": tipo}), "deny")
        texto = motivo(self.HOOK, ferramenta("Agent", **{**self.LOCAL, "subagent_type": "revisor-juridico"}),
                       FUNDACAO_FERRAMENTAS=FERRAMENTAS)
        for trecho in ("'revisor-juridico'", "general-purpose", "web-fetch", "titular"):
            self.assertIn(trecho, texto)

    def test_campo_aceito_fora_do_tipo_e_negado_sem_depender_do_binario(self):
        """Revisão de segurança da 1.7.10.2 (endurecimento; H5): `subagent_type: null` e `model` objeto passavam."""
        casos = {"subagent_type": (None, 7, ["Plan"]), "model": ({"provedor": "outro"}, None, 3),
                 "description": (7, None, {"x": 1}), "prompt": (["p"], None), "effort": (1, None),
                 "run_in_background": ("sim", 1, None)}
        for campo, valores in casos.items():
            for valor in valores:
                with self.subTest(campo=campo, valor=valor):
                    self.assertEqual(self.decide("Agent", {**self.LOCAL, campo: valor}), "deny")
        texto = motivo(self.HOOK, ferramenta("Agent", **{**self.LOCAL, "run_in_background": "sim"}),
                       FUNDACAO_FERRAMENTAS=FERRAMENTAS)
        for trecho in ("'run_in_background'", "bool"):
            self.assertIn(trecho, texto)

    def test_relatorio_do_subagente_segue_com_o_item_dos_subagentes(self):
        """`SubagentHandback` (2.1.302) leva o relatório do subagente a quem o chamou: negado, o relatório se perderia."""
        for lista in (FERRAMENTAS, FERRAMENTAS.replace("Agent", "Task")):
            with self.subTest(lista=lista):
                self.assertEqual(self.decide("SubagentHandback", {"message": "relatório"}, lista), "sem_decisao")
        self.assertEqual(self.decide("SubagentHandback", {"message": "relatório"}, "Bash,Read"), "deny")
        self.assertEqual(decisao(self.HOOK, ferramenta("SubagentHandback", message="x"),
                                 FUNDACAO_FERRAMENTAS=FERRAMENTAS), "sem_decisao")

    def test_campo_novo_e_negado_com_a_lista_dos_aceitos(self):
        self.assertEqual(self.decide("Agent", {**self.LOCAL, "politica_nova": True}), "deny")
        texto = motivo(self.HOOK, ferramenta("Agent", **{**self.LOCAL, "politica_nova": 1}),
                       FUNDACAO_FERRAMENTAS=FERRAMENTAS)
        for trecho in ("'politica_nova'", "description", "run_in_background", "titular"):
            self.assertIn(trecho, texto)

    def test_entrada_ilegivel_do_agente_nega(self):
        for entrada in (None, [], "texto", 7, ["description"]):
            with self.subTest(entrada=entrada):
                self.assertEqual(self.decide("Agent", entrada), "deny")
        self.assertEqual(decisao(self.HOOK, {"tool_name": "Agent"}, FUNDACAO_FERRAMENTAS=FERRAMENTAS), "deny")

    def test_campo_com_controle_vai_curto_e_limpo_na_mensagem(self):
        texto = motivo(self.HOOK, ferramenta("Agent", **{**self.LOCAL, "c" * 5000 + "\n\x1b[31m": 1}),
                       FUNDACAO_FERRAMENTAS=FERRAMENTAS)
        self.assertLess(len(texto), 800)
        self.assertNotIn("\x1b", texto)
        self.assertNotIn("\n", texto)

    def test_outras_ferramentas_nao_tem_a_entrada_lida(self):
        self.assertEqual(self.decide("Bash", {"isolation": "remote", "cwd": "/", "name": "x"}), "sem_decisao")


if __name__ == "__main__":
    unittest.main()
