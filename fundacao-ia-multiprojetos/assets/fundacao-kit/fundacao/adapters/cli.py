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
Prazo: contado desde o início do processo. A CLI e todos os descendentes ficam num Job Object
(Windows) ou num grupo de processos (POSIX): ao estourar `max_seconds` e também quando a CLI
termina, o que restar é encerrado — inclusive órfãos que herdaram as saídas. Entrada e saídas
correm em threads próprias: se a CLI não ler a entrada (que pode passar do buffer do pipe), a
gravação bloqueia, mas o prazo continua valendo. Limites: a CLI entra no Job Object logo depois
de iniciada (intervalo medido de 0,15–0,25 ms; um descendente criado nele ficaria de fora); se
o sistema recusar o Job Object, vale o `taskkill /T`, que não alcança órfãos, e a pasta
temporária de trabalho de um órfão vivo fica para trás; no POSIX, o grupo de processos não
alcança descendente que crie sessão própria (`setsid`), e esse ramo não foi executado aqui.
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
import shutil
import signal
import subprocess
import tempfile
import threading
import time

from ..core import usage as usage_mod
from .base import ProviderRequest, ProviderResult, Timer, build_prompt

_AUTH_HINTS = ("not logged in", "login", "authenticate", "unauthorized", "401", "credentials")
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
    low = stderr.lower()
    return "auth_missing" if any(h in low for h in _AUTH_HINTS) else "failed"


def ambiente_do_provedor(extras: tuple[str, ...] | list[str] = ()) -> dict:
    """Ambiente mínimo do processo do provedor: lista fixa + extras explícitos; nunca FUNDACAO_*."""
    nomes = {n.upper() for n in (*_AMBIENTE_BASE, *extras)}
    return {k: v for k, v in os.environ.items()
            if k.upper() in nomes and not k.upper().startswith("FUNDACAO_")}


if os.name == "nt":  # estruturas do Job Object (ver _criar_trabalho)
    import ctypes
    from ctypes import wintypes

    class _ContadoresES(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _LimitesBasicos(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _LimitesEstendidos(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _LimitesBasicos), ("IoInfo", _ContadoresES),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


def _criar_trabalho(proc: subprocess.Popen):
    """Windows: põe a CLI num Job Object com KILL_ON_JOB_CLOSE. Todo descendente nasce no mesmo
    trabalho — inclusive o que fica órfão quando a CLI termina, que o `taskkill /T` não alcança —,
    e encerrar o trabalho encerra todos. Devolve None se o sistema recusar (cai no `taskkill`)."""
    if os.name != "nt":
        return None
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
        k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        k32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
        k32.CloseHandle.argtypes = (wintypes.HANDLE,)
        job = k32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = _LimitesEstendidos()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not (k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))  # 9 = estendidas
                and k32.AssignProcessToJobObject(job, int(proc._handle))):
            k32.CloseHandle(job)
            return None
        return (k32, job)
    except (OSError, AttributeError, ValueError):
        return None


def _encerrar_descendentes(proc: subprocess.Popen, trabalho) -> None:
    """Encerra a CLI e TODOS os descendentes: pelo Job Object (Windows) ou pelo grupo de processos
    (POSIX, `start_new_session`). Sem Job Object no Windows, o `taskkill /T` alcança só a árvore viva."""
    if trabalho is not None:
        k32, job = trabalho
        k32.TerminateJobObject(job, 1)
    elif os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=30)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        proc.kill()
    except OSError:
        pass


def _aguardar(tarefas, segundos: float) -> None:
    """Espera as threads com um prazo único para todas (não um prazo por thread)."""
    fim = time.monotonic() + segundos
    for t in tarefas:
        t.join(timeout=max(0.0, fim - time.monotonic()))


def _processo(args: list[str], entrada: bytes, prazo: int, cwd: str, env: dict) -> subprocess.CompletedProcess:
    """Roda a CLI com a entrada em bytes e prazo contado desde o início, valendo para a árvore.

    Não usa `communicate(input, timeout)`: no Windows ele grava a entrada inteira ANTES de
    contar o prazo, e uma CLI que não lê a entrada (com mais que o buffer do pipe) prenderia
    a chamada sem limite. A gravação e as leituras correm em threads. No prazo, a CLI e os
    descendentes são encerrados. Quando a CLI termina, os descendentes que ficaram (inclusive
    órfãos que herdaram as saídas) também são encerrados, e a resposta volta sem esperá-los."""
    extra = {} if os.name == "nt" else {"start_new_session": True}
    limite = time.monotonic() + prazo
    proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            cwd=cwd, env=env, **extra)
    trabalho = _criar_trabalho(proc)
    lidos: dict[str, bytes] = {}

    def ler(nome: str, fluxo) -> None:
        try:
            lidos[nome] = fluxo.read()
        except (OSError, ValueError):
            lidos[nome] = b""

    def escrever() -> None:
        try:
            proc.stdin.write(entrada)
        except (OSError, ValueError):  # a CLI fechou a entrada ou já terminou
            pass
        finally:
            try:
                proc.stdin.close()
            except (OSError, ValueError):
                pass

    leitores = [threading.Thread(target=ler, args=(n, f), daemon=True)
                for n, f in (("out", proc.stdout), ("err", proc.stderr))]
    escritor = threading.Thread(target=escrever, daemon=True)
    for t in (*leitores, escritor):
        t.start()
    try:
        try:
            proc.wait(timeout=max(0.0, limite - time.monotonic()))
        except subprocess.TimeoutExpired:
            _encerrar_descendentes(proc, trabalho)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            _aguardar((*leitores, escritor), 5)
            raise
        # A CLI terminou: o que ela deixou rodando (e poderia segurar as saídas) é encerrado agora.
        if trabalho is not None or os.name != "nt":
            _encerrar_descendentes(proc, trabalho)
        _aguardar(leitores, max(0.0, limite - time.monotonic()) + 2)
        if any(t.is_alive() for t in leitores):  # sem Job Object, um órfão ainda segura as saídas
            raise subprocess.TimeoutExpired(args, prazo)
        _aguardar((escritor,), 2)
    finally:
        for t, fluxo in zip(leitores, (proc.stdout, proc.stderr)):
            if not t.is_alive():  # fechar com uma leitura em curso bloquearia até o fim dela
                try:
                    fluxo.close()
                except OSError:
                    pass
        if trabalho is not None:
            trabalho[0].CloseHandle(trabalho[1])
    return subprocess.CompletedProcess(args, proc.returncode, lidos.get("out", b"").decode("utf-8", "replace"),
                                       lidos.get("err", b"").decode("utf-8", "replace"))


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
        except OSError as exc:  # ex.: WinError 206 (linha longa) ou executável sem permissão
            return ProviderResult(provider_id, route, "failed", dispatched=False,
                                  diagnostic=f"a CLI não pôde ser iniciada ({type(exc).__name__})")
    return proc, t.ms


def _falha(provider_id: str, route: str, proc: subprocess.CompletedProcess, ms: int) -> ProviderResult:
    estado = _classify_failure(proc.stderr)
    # Sem login a CLI não chega ao provedor; outras falhas podem ter consumido (conservador).
    return ProviderResult(provider_id, route, estado, duration_ms=ms, dispatched=estado != "auth_missing",
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
