"""Adaptadores para as CLIs oficiais (Claude Code e Codex) — rota local do titular.

Estado nesta entrega: CÓDIGO PRESENTE. A integração só vale como demonstrada
depois de uma chamada real registrada, com autenticação e orçamento confirmados
pelo titular (livro A08: teto inicial de 4 chamadas, sem repetição automática).

Formatos conferidos em 18/10/2026 (ver references/fontes-verificadas.md):
- `claude -p <instrução> --output-format json` devolve um objeto JSON com o texto
  em `result`, `is_error`, `session_id`, `total_cost_usd` e `usage`.
- `codex exec --json -` devolve JSONL; o uso fica em `turn.completed.usage`
  e a resposta em eventos `item.completed` de tipo `agent_message`. O sandbox
  padrão do exec é somente leitura; `--full-auto` foi descontinuado.
Entrada: o prompt (tarefa + dados) vai pela ENTRADA PADRÃO, em bytes UTF-8 (sem conversão de
fim de linha), nunca pela linha de comando.
`codex exec ... -` lê as instruções da entrada padrão (conferido no `--help` da 0.163.0);
`claude -p "<instrução fixa>"` recebe o resto pela entrada padrão (padrão documentado
`cat arquivo | claude -p 'consulta'`; limite documentado de 10 MB). A linha de comando só
leva opções fixas: no Windows, uma CLI instalada como `.cmd` passa a linha pelo cmd.exe,
que cortaria o prompt na primeira quebra de linha e interpretaria `&`, `|` e aspas; por
isso, numa CLI `.cmd`/`.bat`, opção com caractere especial do cmd.exe é recusada.
Prazo e teto de saída: pelo executor de `core/processo.py` (saiu daqui na 1.7.7; limites conhecidos
descritos lá). O prazo (`max_seconds`), contado desde o início do processo, vale para a CLI e todos os
descendentes (Job Object no Windows; grupo de processos no POSIX), também quando a CLI termina e deixa
órfãos com as saídas. stdout acima de 32 MiB ou stderr acima de 4 MiB: a árvore é encerrada na hora e a
chamada sai `invalid_output`, contada no teto da rota, porque a CLI começou (auditoria Codex 1.7.6, #9).
Ambiente: o processo do provedor recebe só variáveis do sistema (lista fixa) e a pasta de
configuração da própria CLI; nunca `FUNDACAO_*` (identidade) nem chaves de API — na rota de
assinatura, uma chave no ambiente faria a CLI cobrar créditos de API. Variáveis a mais só
por configuração explícita (`variaveis_extras`).
Isolamento do agente externo (opções conferidas em 18/10/2026 na documentação e no `--help`
das versões instaladas, Claude Code 2.1.302 e codex-cli 0.163.0; `--max-turns` não aparece no
`--help`, mas está definida no executável; NUNCA executado com provedor nesta entrega):
- cada chamada roda numa pasta temporária VAZIA (o agente não herda a raiz com
  `projects/` nem `state/`);
- Claude: `--tools ""` (sem ferramentas nativas), `--disallowedTools "mcp__*"` e
  `--strict-mcp-config` (sem MCP), `--restricted` (ignora configurações do usuário e do
  projeto; ferramentas de arquivo confinadas à pasta de trabalho), `--max-turns 1`,
  `--no-session-persistence`, `--permission-prompts none` e `--max-budget-usd`
  quando a rota tem teto;
- Codex: `--sandbox read-only`, `--ephemeral`, `--ignore-user-config`,
  `--ignore-rules`, `--skip-git-repo-check`. A documentação não diz se o modo
  somente leitura impede ler fora da pasta: trate como NÃO isolado para leitura.
  Por isso o adaptador NÃO roda (estado `disabled`, nada sai) sem `isolamento_leitura`:
  a descrição do isolamento EXTERNO (conta do SO, contêiner ou VM que exponha só a
  pasta de trabalho) que impede o agente de ler `state/`, outros projetos e
  configurações (varredura 1.4.5, #9). O kit não verifica a declaração: ela registra
  a decisão de quem habilita a rota, que deve prová-la com o canário abaixo.
Isso reduz a superfície, mas não é barreira: isolamento real do agente externo exige
sandbox ou conta do SO. Antes de liberar a rota, prove com um documento-canário de
outro projeto na raiz (deve continuar ausente da resposta).
Política (conferir a cada mudança de conta/canal): a OpenAI recomenda chave de
API para automação; a Anthropic distingue uso pessoal do Claude Code pela
assinatura de produtos/serviços para terceiros (exigem chave de API). Se outra
pessoa usar a fundação, desligue a rota `cli_assinatura`.
Nunca use flags de acesso irrestrito para "fazer o teste passar".
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile

from ..core import usage as usage_mod
from ..core.contracts import LimiteExcedido
from ..core.processo import executar as _processo  # executor de árvore com prazo e teto (testes o substituem aqui)
from .base import ProviderRequest, ProviderResult, Timer, build_prompt

# Falta de login só pelo aviso da própria CLI, em frase inteira: "401" ou "login" soltos não bastam (E11, F-04).
_AVISO_LOGIN = re.compile("(?<![a-z0-9])(?:not logged in|/login|claude login|codex login|invalid api key)(?![a-z0-9])")
LIMITE_ENTRADA = 9_500_000  # bytes de prompt; o Claude Code documenta 10 MB na entrada padrão
INSTRUCAO_CLAUDE = "Siga a tarefa recebida pela entrada padrao; os dados vem no mesmo texto."  # ASCII
_ESPECIAIS_CMD = set('&|<>^%"()!\r\n')
_AMBIENTE_BASE = (
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR",
    "USERNAME", "USERPROFILE", "HOME", "HOMEDRIVE", "HOMEPATH", "LOCALAPPDATA", "APPDATA", "PROGRAMDATA",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "LANG", "LC_ALL", "TZ",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "SSL_CERT_FILE", "NODE_EXTRA_CA_CERTS",
)


def _classify_failure(stderr: str) -> str:
    return "auth_missing" if _AVISO_LOGIN.search(" ".join(stderr.lower().split())) else "failed"


def ambiente_do_provedor(extras: tuple[str, ...] | list[str] = ()) -> dict:
    """Ambiente mínimo do processo do provedor: lista fixa + extras explícitos; nunca FUNDACAO_*."""
    nomes = {n.upper() for n in (*_AMBIENTE_BASE, *extras)}
    return {k: v for k, v in os.environ.items()
            if k.upper() in nomes and not k.upper().startswith("FUNDACAO_")}


def _rodar(provider_id: str, route: str, args: list[str], prompt: str, max_seconds: int,
           extras: tuple[str, ...]) -> ProviderResult | tuple[subprocess.CompletedProcess, int]:
    """Roda a CLI numa pasta temporária vazia, com o prompt pela entrada padrão.
    Falhas antes de iniciar o processo saem com dispatched=False (nada chegou ao provedor)."""
    if args[0].lower().endswith((".cmd", ".bat")) and any(ch in _ESPECIAIS_CMD for a in args[1:] for ch in a):
        return ProviderResult(provider_id, route, "failed", dispatched=False,
                              diagnostic="opção com caractere especial do cmd.exe numa CLI .cmd/.bat: recusada")
    entrada = prompt.encode("utf-8")  # bytes exatos: sem conversão de fim de linha
    if len(entrada) > LIMITE_ENTRADA:
        return ProviderResult(provider_id, route, "failed", dispatched=False,
                              diagnostic="prompt acima do limite da entrada padrão: divida a tarefa")
    with Timer() as t, tempfile.TemporaryDirectory(prefix="fundacao-provedor-", ignore_cleanup_errors=True) as vazio:
        try:
            proc = _processo(args, entrada, max_seconds, vazio, ambiente_do_provedor(extras))
        except subprocess.TimeoutExpired:
            return ProviderResult(provider_id, route, "timeout",
                                  diagnostic="tempo esgotado; reconcilie antes de repetir")
        except LimiteExcedido as exc:  # a CLI começou (conta no teto); a árvore já foi encerrada (Codex 1.7.6, #9)
            return ProviderResult(provider_id, route, "invalid_output", dispatched=True,
                                  diagnostic=f"{exc} ({exc.details.get('fluxo')}, teto de "
                                             f"{exc.details.get('teto_bytes')} bytes); nada da saída foi usado")
        except OSError as exc:  # ex.: WinError 206 (linha longa) ou executável sem permissão
            return ProviderResult(provider_id, route, "failed", dispatched=False,
                                  diagnostic=f"a CLI não pôde ser iniciada ({type(exc).__name__})")
    return proc, t.ms


def _falha(provider_id: str, route: str, proc: subprocess.CompletedProcess, ms: int) -> ProviderResult:
    # Processo iniciado: nada prova que a chamada não chegou ao provedor; conta no teto, também sem login (E11, F-04).
    return ProviderResult(provider_id, route, _classify_failure(proc.stderr), duration_ms=ms, dispatched=True,
                          diagnostic=proc.stderr.strip()[-300:])


def parse_claude_json(stdout: str) -> dict:
    data = json.loads(stdout)
    if not isinstance(data, dict):
        raise ValueError("saída JSON inesperada do claude -p")
    return {
        "text": data.get("result", ""),
        "is_error": bool(data.get("is_error", False)),
        "call_id": data.get("session_id", "unknown"),
        "usage": data.get("usage") or {},
        "cost_usd": data.get("total_cost_usd"),
        "model": next(iter((data.get("modelUsage") or {}).keys()), "unknown"),
    }


def parse_codex_jsonl(stdout: str) -> dict:
    text, usage, thread, failed = "", {}, "unknown", None
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue  # diagnóstico misturado não é dado
        event = json.loads(line)
        kind = event.get("type", "")
        if kind == "thread.started":
            thread = event.get("thread_id", thread)
        elif kind == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message":
                text = item.get("text", text)
        elif kind == "turn.completed":
            usage = event.get("usage") or {}
        elif kind in ("turn.failed", "error"):
            failed = json.dumps(event.get("error", event))[:300]
    return {"text": text, "usage": usage, "call_id": thread, "failed": failed}


class ClaudeCLIProvider:
    provider_id = "claude-cli"
    variaveis_padrao = ("CLAUDE_CONFIG_DIR", "CLAUDE_CODE_GIT_BASH_PATH")

    def __init__(self, route: str = "cli_assinatura", executable: str = "claude",
                 extra_args: list[str] | None = None, max_budget_usd: float | None = None,
                 variaveis_extras: tuple[str, ...] = ()):
        self.route = route
        self.executable = executable
        self.extra_args = list(extra_args or [])
        self.max_budget_usd = max_budget_usd  # o roteador ajusta ao saldo do teto da rota
        self.variaveis = (*self.variaveis_padrao, *variaveis_extras)

    def build_args(self, exe: str, request: ProviderRequest | None = None) -> list[str]:
        """Só opções fixas; a tarefa e os dados vão pela entrada padrão (ver `call`)."""
        args = [exe, "-p", INSTRUCAO_CLAUDE, "--output-format", "json",
                "--tools", "", "--disallowedTools", "mcp__*", "--strict-mcp-config", "--restricted",
                "--max-turns", "1", "--no-session-persistence", "--permission-prompts", "none"]
        if self.max_budget_usd is not None:
            args += ["--max-budget-usd", f"{max(self.max_budget_usd, 0):.2f}"]
        return args + self.extra_args

    def call(self, request: ProviderRequest) -> ProviderResult:
        exe = shutil.which(self.executable)
        if exe is None:
            return ProviderResult(self.provider_id, self.route, "failed", dispatched=False,
                                  diagnostic="executável não encontrado")
        saida = _rodar(self.provider_id, self.route, self.build_args(exe, request), build_prompt(request),
                       request.max_seconds, self.variaveis)
        if isinstance(saida, ProviderResult):
            return saida
        proc, ms = saida
        if proc.returncode != 0:
            return _falha(self.provider_id, self.route, proc, ms)
        try:
            parsed = parse_claude_json(proc.stdout)
        except (ValueError, json.JSONDecodeError):
            return ProviderResult(self.provider_id, self.route, "invalid_output", duration_ms=ms)
        return ProviderResult(
            provider_id=self.provider_id, route=self.route,
            state="failed" if parsed["is_error"] else "succeeded", text=parsed["text"],
            model=parsed["model"], call_id=parsed["call_id"], duration_ms=ms,
            usage=usage_mod.normalize("claude-cli", parsed["usage"], route=self.route,
                                      run_id=request.run_id, duration_ms=ms, cost_usd=parsed["cost_usd"]),
        )


class CodexCLIProvider:
    provider_id = "codex-cli"
    variaveis_padrao = ("CODEX_HOME",)

    def __init__(self, route: str = "cli_assinatura", executable: str = "codex",
                 extra_args: list[str] | None = None, variaveis_extras: tuple[str, ...] = (),
                 isolamento_leitura: str | None = None):
        self.route = route
        self.executable = executable
        self.extra_args = list(extra_args or [])
        self.variaveis = (*self.variaveis_padrao, *variaveis_extras)
        # `--sandbox read-only` restringe escrita, não leitura: o agente lê o que a identidade do SO do
        # lançador lê. Sem a descrição do isolamento externo que impede isso, a rota não roda (#9).
        self.isolamento_leitura = str(isolamento_leitura or "").strip()

    def build_args(self, exe: str, request: ProviderRequest | None = None) -> list[str]:
        # Sandbox somente leitura, sem persistir sessão, sem config.toml do usuário (servidores MCP)
        # nem regras .rules, sem exigir repositório Git; `-` = instruções pela entrada padrão.
        return [exe, "exec", "--json", "--sandbox", "read-only", "--ephemeral", "--ignore-user-config",
                "--ignore-rules", "--skip-git-repo-check", *self.extra_args, "-"]

    def call(self, request: ProviderRequest) -> ProviderResult:
        if not self.isolamento_leitura:
            return ProviderResult(self.provider_id, self.route, "disabled", dispatched=False,
                                  diagnostic="Codex CLI sem isolamento de leitura declarado: com --sandbox read-only "
                                             "o agente lê fora da pasta temporária com a identidade do lançador "
                                             "(state/, outros projetos). Rode-o sob conta do SO, contêiner ou VM que "
                                             "exponha só a pasta de trabalho e informe isso em isolamento_leitura")
        exe = shutil.which(self.executable)
        if exe is None:
            return ProviderResult(self.provider_id, self.route, "failed", dispatched=False,
                                  diagnostic="executável não encontrado")
        saida = _rodar(self.provider_id, self.route, self.build_args(exe, request), build_prompt(request),
                       request.max_seconds, self.variaveis)
        if isinstance(saida, ProviderResult):
            return saida
        proc, ms = saida
        if proc.returncode != 0:
            return _falha(self.provider_id, self.route, proc, ms)
        try:
            parsed = parse_codex_jsonl(proc.stdout)
        except json.JSONDecodeError:
            return ProviderResult(self.provider_id, self.route, "invalid_output", duration_ms=ms)
        state = "failed" if parsed["failed"] else ("succeeded" if parsed["text"] else "invalid_output")
        return ProviderResult(
            provider_id=self.provider_id, route=self.route, state=state, text=parsed["text"],
            call_id=parsed["call_id"], duration_ms=ms, diagnostic=parsed["failed"] or "",
            usage=usage_mod.normalize("codex-cli", parsed["usage"], route=self.route,
                                      run_id=request.run_id, duration_ms=ms),
        )
