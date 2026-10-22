"""Executor de processo filho: entrada em bytes, prazo e teto de saída que valem para a árvore de processos.

Usado pelos adaptadores das CLIs dos provedores (`adapters/cli.py`) e pelo despacho de componentes
(`core/components.py`). Saiu de `adapters/cli.py` na 1.7.7, junto com o teto de saída: o núcleo não importa
mais o adaptador (a dívida conhecida de `components.py` foi paga).
Prazo: contado desde o início do processo. O filho e todos os descendentes ficam num Job Object (Windows) ou
num grupo de processos (POSIX): ao estourar o prazo e também quando o filho termina, o que restar é encerrado —
inclusive órfãos que herdaram as saídas. Entrada e saídas correm em threads próprias: se o filho não ler a
entrada (que pode passar do buffer do pipe), a gravação bloqueia, mas o prazo continua valendo. Limites: o
filho entra no Job Object logo depois de iniciado (intervalo medido de 0,15–0,25 ms; um descendente criado
nele ficaria de fora); se o sistema recusar o Job Object, vale o `taskkill /T`, que não alcança órfãos, e a
pasta temporária de trabalho de um órfão vivo fica para trás; no POSIX, o grupo de processos não alcança
descendente que crie sessão própria (`setsid`), e esse ramo não foi executado aqui.
Teto de saída [auditoria Codex Security da 1.7.6, #9]: o prazo não limita a memória — um filho escreve
gigabytes antes dele. stdout e stderr são lidos em blocos e guardados só até o teto de cada um (`tetos`; sem
ele, `TETO_STDOUT` e `TETO_STDERR`, os das rotas por CLI). Passou do teto: a árvore é encerrada na hora e a
chamada levanta `LimiteExcedido`, sem devolver o que foi lido. O teto limita o que a fundação guarda; a
memória do próprio filho não tem teto do sistema aqui.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time

from .contracts import LimiteExcedido

TETO_STDOUT = 32 * 1024 * 1024  # bytes de stdout guardados quando quem chama não informa (rotas por CLI)
TETO_STDERR = 4 * 1024 * 1024   # bytes de stderr guardados quando quem chama não informa
_BLOCO = 64 * 1024

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
    """Windows: põe o filho num Job Object com KILL_ON_JOB_CLOSE. Todo descendente nasce no mesmo
    trabalho — inclusive o que fica órfão quando o filho termina, que o `taskkill /T` não alcança —,
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
    """Encerra o filho e TODOS os descendentes: pelo Job Object (Windows) ou pelo grupo de processos
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


def executar(args: list[str], entrada: bytes, prazo: int, cwd: str, env: dict, *,
             tetos: tuple[int, int] | None = None) -> subprocess.CompletedProcess:
    """Roda `args` com a entrada em bytes, prazo contado desde o início e teto de saída, valendo para a árvore.

    Não usa `communicate(input, timeout)`: no Windows ele grava a entrada inteira ANTES de
    contar o prazo, e um filho que não lê a entrada (com mais que o buffer do pipe) prenderia
    a chamada sem limite. A gravação e as leituras correm em threads. No prazo, o filho e os
    descendentes são encerrados. Quando o filho termina, os descendentes que ficaram (inclusive
    órfãos que herdaram as saídas) também são encerrados, e a resposta volta sem esperá-los.
    `tetos`: bytes de stdout e de stderr guardados; passou de um deles, a árvore é encerrada na
    hora e a chamada levanta `LimiteExcedido`."""
    teto = dict(zip(("out", "err"), tetos or (TETO_STDOUT, TETO_STDERR)))
    extra = {} if os.name == "nt" else {"start_new_session": True}
    limite = time.monotonic() + prazo
    proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            cwd=cwd, env=env, **extra)
    trabalho = _criar_trabalho(proc)
    lidos: dict[str, bytes] = {}
    estouro: list[str] = []
    trava, fechado = threading.Lock(), []  # o Job Object não é usado depois de fechado

    def encerrar() -> None:
        with trava:
            # Sem Job Object no Windows, o `taskkill` vai pelo PID: só enquanto o filho vive (PID não reaproveitado).
            if not fechado and (trabalho is not None or os.name != "nt" or proc.poll() is None):
                _encerrar_descendentes(proc, trabalho)

    def ler(nome: str, fluxo) -> None:
        partes, total = [], 0
        try:
            while bloco := fluxo.read1(_BLOCO):
                total += len(bloco)
                if total > teto[nome]:  # passou do teto: encerra a árvore na hora e não guarda mais nada
                    estouro.append(nome)
                    encerrar()
                    return
                partes.append(bloco)
            lidos[nome] = b"".join(partes)
        except (OSError, ValueError):
            lidos[nome] = b""

    def escrever() -> None:
        try:
            proc.stdin.write(entrada)
        except (OSError, ValueError):  # o filho fechou a entrada ou já terminou
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
            encerrar()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            _aguardar((*leitores, escritor), 5)
            raise
        # O filho terminou (ou foi encerrado pelo teto): o que ele deixou rodando (e poderia segurar as saídas)
        # é encerrado agora.
        encerrar()
        _aguardar(leitores, max(0.0, limite - time.monotonic()) + 2)
        if any(t.is_alive() for t in leitores):  # sem Job Object, um órfão ainda segura as saídas
            raise subprocess.TimeoutExpired(args, prazo)
        _aguardar((escritor,), 2)
    finally:
        with trava:
            fechado.append(True)
        for t, fluxo in zip(leitores, (proc.stdout, proc.stderr)):
            if not t.is_alive():  # fechar com uma leitura em curso bloquearia até o fim dela
                try:
                    fluxo.close()
                except OSError:
                    pass
        if trabalho is not None:
            trabalho[0].CloseHandle(trabalho[1])
    if estouro:
        raise LimiteExcedido("saída do processo acima do teto: o processo e os descendentes foram encerrados",
                             fluxo="stdout" if estouro[0] == "out" else "stderr", teto_bytes=teto[estouro[0]])
    return subprocess.CompletedProcess(args, proc.returncode, lidos.get("out", b"").decode("utf-8", "replace"),
                                       lidos.get("err", b"").decode("utf-8", "replace"))
