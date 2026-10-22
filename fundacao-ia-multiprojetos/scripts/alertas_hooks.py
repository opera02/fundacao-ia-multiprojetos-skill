#!/usr/bin/env python3
"""Regra do matcher do Claude Code e alertas dos hooks do inventário do host — os do perfil, os da raiz e os dos
plugins (análise do everything-claude-code, 21/10/2026, proposta 1; R54). Usado por `inventariar_host.py`.

Matcher [Verificado 2026-10-21; code.claude.com/docs/en/hooks]: `*`, vazio ou ausente casam tudo; só letras,
dígitos, `_`, `-`, espaço, `,` e `|` formam uma lista exata (separada por `|` ou `,`, com espaços em volta) —
`Edit || Write` (só letras, espaços e `|`) é lista exata e casa só Edit e Write; qualquer outro caractere faz uma
expressão regular de JavaScript sem âncora (`Edit.*` casa também `NotebookEdit`), e só aí a alternativa vazia entre
as barras casa qualquer nome, como em `tool == "Edit" || tool == "Write"`. Em eventos sem matcher
(UserPromptSubmit, Stop e outros) o campo é ignorado. Alertas: `matcher_nunca_casa` (nenhum nome conhecido casa;
inclui evento que a documentação não lista), `matcher_casa_tudo` (em evento de ferramenta, casa também nomes
inventados; ou o evento ignora o filtro; `*` e vazio são "todas", registrados como tal, sem alerta),
`matcher_indeterminado` (a expressão não pôde ser avaliada aqui: o `re` do Python não a compila) e
`evento_fora_do_guarda` (hook do perfil ou de plugin fora do PreToolUse, o evento dos guardas da fundação). Avalia-se
o matcher inteiro e cru, não a cópia de exibição (até 200 caracteres, com caractere de controle e surrogate trocados
por espaço) que o inventário guarda dos hooks de plugin (revisão de segurança da 1.7.7, R177-VAL-03; o cru, na segunda
passada, R177B-A-01). Matcher com caractere de controle ou surrogate é expressão pela regra e sai sempre com alerta:
`matcher_casa_tudo` quando a avaliação diz, senão `matcher_indeterminado` — a cópia guardada mostra espaço onde o host
vê outro caractere. As expressões são avaliadas com o `re` do Python, aproximação da de JavaScript, num
subprocesso Python isolado (`-I -S`), com 5 s por expressão e 30 s para o inventário inteiro: expressão de mais de
4096 caracteres, que passa do tempo (retrocesso exponencial) ou que o `re` não compila sai como
`matcher_indeterminado`, e nome de servidor MCP com mais de 256 caracteres não entra na avaliação (revisão de
segurança da 1.7.7, R177-VAL-04).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time

# [Verificado 2026-10-21; code.claude.com/docs/en/tools-reference], mais os legados Task e MultiEdit.
FERRAMENTAS = tuple("""Agent Artifact AskUserQuestion Bash CronCreate CronDelete CronList Edit EndConversation
EnterPlanMode EnterWorktree ExitPlanMode ExitWorktree Glob Grep LSP ListAgents ListMcpResourcesTool Monitor MultiEdit
NotebookEdit PowerShell PushNotification Read ReadMcpResourceTool RemoteTrigger ReportFindings ScheduleWakeup
SendFeedback SendMessage SendUserFile ShareOnboardingGuide Skill SubagentHandback Task TaskCreate TaskGet TaskList
TaskOutput TaskStop TaskUpdate TodoWrite ToolSearch WaitForMcpServers WebFetch WebSearch Workflow Write""".split())
# O que o matcher filtra em cada evento [Verificado 2026-10-21; code.claude.com/docs/en/hooks].
DE_FERRAMENTA = set("PreToolUse PostToolUse PostToolUseFailure PermissionRequest PermissionDenied".split())
VALORES = {"SessionStart": ("startup", "resume", "clear", "compact", "fork"), "Setup": ("init", "maintenance"),
           "SessionEnd": ("clear", "resume", "logout", "prompt_input_exit", "other"),
           "PreCompact": ("manual", "auto"), "PostCompact": ("manual", "auto")}
SEM_MATCHER = set("""UserPromptSubmit PostToolBatch Stop TeammateIdle TaskCreated TaskCompleted WorktreeCreate
WorktreeRemove MessageDisplay CwdChanged""".split())
EVENTOS = DE_FERRAMENTA | set(VALORES) | SEM_MATCHER | set("""Notification SubagentStart SubagentStop PreModelSwitch
PostModelSwitch ConfigChange DirectoryAdded FileChanged StopFailure InstructionsLoaded UserPromptExpansion Elicitation
ElicitationResult""".split())
SO_BARRA = {"FileChanged", "StopFailure"}  # nesses dois, a lista exata aceita só letras, dígitos, `_` e `|`
INVENTADOS = ("Inventada0", "zz", "_")     # nenhuma ferramenta tem esses nomes: casar os três é casar tudo
GUARDA = "PreToolUse"                     # o evento dos guardas da fundação (guarda_caminho, guarda_identidade)
NOMES_FIXOS = INVENTADOS + FERRAMENTAS + ("mcp__x__y",) + tuple(dict.fromkeys(v for vs in VALORES.values() for v in vs))
# Limites da avaliação de uma expressão (revisão de segurança da 1.7.7, R177-VAL-04): o `re` não se interrompe por
# dentro, e um matcher com retrocesso exponencial contra o nome de um servidor MCP travava o inventário.
TETO_EXPRESSAO = 4096      # caracteres de uma expressão avaliada; acima, `matcher_indeterminado` sem avaliar
TETO_NOME = 256            # nome de ferramenta MCP mais longo que isso não entra na avaliação
TEMPO_EXPRESSAO = 5.0      # segundos por expressão, num subprocesso Python isolado (-I -S)
ORCAMENTO = 30.0           # segundos para todas as expressões de um inventário
# Caracteres que a cópia de exibição do inventário troca por espaço (inventario_plugins.CONTROLE): no matcher, fazem
# expressão e não aparecem no que fica guardado (revisão de segurança da 1.7.7, segunda passada, R177B-A-01).
CONTROLE = re.compile(r"[\x00-\x1f\x7f\ud800-\udfff]")
# O subprocesso lê {"padrao", "nomes"} e devolve os índices dos nomes que a expressão casa, ou null se não compila.
CASAR = """import json, re, sys
d = json.loads(sys.stdin.read())
try:
    rx = re.compile(d["padrao"])
except Exception:
    rx = None
print(json.dumps(None if rx is None else [i for i, n in enumerate(d["nomes"]) if rx.search(n)]))
"""


class Avaliador:
    """Expressões avaliadas num subprocesso, com tempo limite por expressão e orçamento total; o resultado de cada
    uma fica guardado (o mesmo matcher em vários hooks é avaliado uma vez)."""

    def __init__(self, orcamento: float = ORCAMENTO):
        self.fim, self.feitas = time.monotonic() + orcamento, {}

    def casar(self, padrao: str, nomes: tuple) -> set | str:
        """Os nomes que a expressão casa ou, se não foi possível avaliar, o motivo."""
        if (padrao, nomes) not in self.feitas:
            self.feitas[(padrao, nomes)] = self._avaliar(padrao, nomes)
        return self.feitas[(padrao, nomes)]

    def _avaliar(self, padrao: str, nomes: tuple) -> set | str:
        prazo = min(TEMPO_EXPRESSAO, self.fim - time.monotonic())
        if prazo <= 0:
            return "orçamento de avaliação do inventário esgotado: expressão não avaliada"
        try:
            r = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", CASAR], capture_output=True, encoding="utf-8",
                               errors="replace", input=json.dumps({"padrao": padrao, "nomes": list(nomes)}),
                               timeout=prazo)
            indices = json.loads(r.stdout)
        except subprocess.TimeoutExpired:
            return f"a avaliação passou de {prazo:.1f} s (retrocesso exponencial?): expressão não avaliada"
        except (OSError, ValueError):
            return "a avaliação da expressão não rodou"
        if indices is None:
            return "expressão que o re do Python não compila (o host usa a de JavaScript)"
        if not isinstance(indices, list):
            return "a avaliação da expressão não rodou"
        return {nomes[i] for i in indices if isinstance(i, int) and 0 <= i < len(nomes)}


def avaliar_matcher(evento: str, matcher, nomes_mcp: tuple = (), avaliador: Avaliador | None = None
                    ) -> tuple[str, str | None, str | None]:
    """(forma do matcher, alerta ou None, motivo). `nomes_mcp`: ferramentas MCP conhecidas (`mcp__<servidor>__x`);
    `avaliador`: o do inventário (tempo e resultados compartilhados); sem ele, um novo. Com caractere de controle ou
    surrogate, nunca sai sem alerta (R177B-A-01)."""
    if evento not in EVENTOS:
        return "evento desconhecido", "matcher_nunca_casa", "evento que a documentação não lista: o hook não roda"
    if matcher in (None, "", "*"):
        return "todas", None, None
    m = str(matcher)
    if evento in SEM_MATCHER:
        return "ignorado", "matcher_casa_tudo", "evento sem matcher: o filtro é ignorado e o hook roda sempre"
    forma, alerta, motivo = _pela_regra(evento, m, nomes_mcp, avaliador)
    if CONTROLE.search(m) and alerta != "matcher_casa_tudo":
        return forma, "matcher_indeterminado", ("caractere de controle ou surrogate no matcher (na cópia guardada, "
                                                "espaço): o host o trata como expressão; confira à mão")
    return forma, alerta, motivo


def _pela_regra(evento: str, m: str, nomes_mcp: tuple, avaliador: Avaliador | None
                ) -> tuple[str, str | None, str | None]:
    """A regra do matcher em evento que filtra: lista exata ou expressão avaliada (a forma, o alerta e o motivo)."""
    ferramenta, so_barra = evento in DE_FERRAMENTA, evento in SO_BARRA
    nomes_mcp = tuple(n for n in nomes_mcp if len(n) <= TETO_NOME)
    conhecidos = set(FERRAMENTAS + ("mcp__x__y",) + nomes_mcp) if ferramenta else VALORES.get(evento)
    if re.fullmatch(r"[A-Za-z0-9_|]*" if so_barra else r"[A-Za-z0-9_\-, |]*", m):  # lista exata
        nomes = [n.strip() for n in re.split(r"\|" if so_barra else r"[|,]", m) if n.strip()]
        if conhecidos is None or any(n in conhecidos or ferramenta and re.fullmatch(r"mcp__.+__.+", n) for n in nomes):
            return "exato", None, None
        dica = " (MCP: mcp__<servidor>__<ferramenta> ou mcp__<servidor>__.*)" if "mcp__" in m else ""
        return "exato", "matcher_nunca_casa", "nenhum nome conhecido na lista exata" + dica
    if len(m) > TETO_EXPRESSAO:
        return "expressao", "matcher_indeterminado", (f"expressão com {len(m)} caracteres, acima do teto de "
                                                       f"{TETO_EXPRESSAO}: não avaliada; confira à mão")
    casados = (avaliador or Avaliador()).casar(m, NOMES_FIXOS + nomes_mcp)
    if isinstance(casados, str):  # não compila (R177-VAL-03), passou do tempo ou do orçamento (R177-VAL-04)
        return "expressao", "matcher_indeterminado", casados + "; confira à mão"
    if ferramenta and all(n in casados for n in INVENTADOS):
        vazia = "||" in m or m.startswith("|") or m.endswith("|") or "(|" in m or "|)" in m
        return "expressao", "matcher_casa_tudo", ("alternativa vazia (||) casa qualquer nome" if vazia
                                                  else "a expressão casa qualquer nome, até um inventado")
    if conhecidos is None or any(n in casados for n in conhecidos) or ferramenta and re.match(r"\^?\(?mcp__", m):
        return "expressao", None, None  # MCP fora do inventário: o nome da ferramenta não é conhecido aqui
    return "expressao", "matcher_nunca_casa", "nenhum nome conhecido casa a expressão"


def alertas(hooks: list[dict], mcp: list[dict]) -> list[dict]:
    """Alertas de todos os hooks do inventário; anota em cada hook a forma do matcher (`matcher_tipo`)."""
    nomes = set()
    for m in mcp:  # servidores MCP do inventário viram nomes de ferramenta conhecidos
        if m.get("cliente") == "claude" and m.get("nome"):
            nomes.add(f"mcp__{m['nome']}__x")
            if str(m.get("onde", "")).startswith("plugin:"):
                nomes.add(f"mcp__plugin_{str(m['onde'])[7:].split('@')[0].split('|')[0]}_{m['nome']}__x")
    out, avaliador = [], Avaliador()  # um orçamento de tempo para o inventário inteiro (R177-VAL-04)
    for h in hooks:  # o inteiro e cru, quando o inventário guarda só a cópia de exibição (R177-VAL-03, R177B-A-01)
        matcher = h.get("_matcher_inteiro", h.get("matcher"))
        forma, alerta, motivo = avaliar_matcher(str(h.get("evento")), matcher, tuple(sorted(nomes)), avaliador)
        h["matcher_tipo"] = forma
        base = {"origem": h.get("origem"), "evento": h.get("evento"), "matcher": h.get("matcher")}
        if alerta:
            out.append({"alerta": alerta, **base, "motivo": motivo})
        if not str(h.get("origem", "")).startswith("raiz:") and h.get("evento") != GUARDA:
            out.append({"alerta": "evento_fora_do_guarda", **base, "motivo": "hook de terceiro em evento que o guarda "
                        "(PreToolUse) não vê; roda fora do sandbox, com os dados que o host lhe entregar"})
    return out


def resumo(lista: list[dict]) -> dict:
    """Para a saída do `gravar` e do `verificar`: cada alerta com as origens e os eventos em que aparece."""
    out: dict[str, list] = {}
    for a in lista:
        out.setdefault(a["alerta"], []).append(f"{a['origem']} {a['evento']}")
    return {k: sorted(set(v)) for k, v in sorted(out.items())}
