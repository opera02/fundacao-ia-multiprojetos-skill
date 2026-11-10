"""Medida do WSL pelo Windows (1.7.11; saiu de trava_banco.py para este arquivo não passar do teto de linhas): o caminho
absoluto do wsl.exe da pasta de sistema, a chamada só de listagem (`-l`, `-l --running`, sempre com `-q`) e a leitura
dos nomes em UTF-16. Quem decide o que a medida significa é trava_banco.wsl_em_execucao."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

WSL_PRAZO_S = 8  # tempo-limite de cada chamada ao wsl.exe: acima disto, "não medido" (e nada é tirado)


def _wsl_do_sistema() -> str | None:
    """Caminho absoluto do wsl.exe da pasta de sistema do Windows; nunca o nome nu, que CreateProcess buscaria na
    pasta atual. None fora do Windows ou sem o arquivo."""
    raiz = os.environ.get("SystemRoot") or os.environ.get("windir")
    if os.name != "nt" or not raiz:
        return None
    exe = Path(raiz) / "System32" / "wsl.exe"
    return str(exe) if exe.is_file() else None


def _rodar_wsl(args: list[str], prazo_s: float = WSL_PRAZO_S) -> tuple[int, bytes]:
    """Roda `wsl.exe <args>` (só listagem) e devolve (código de saída, stdout em bytes). Levanta OSError, ou
    subprocess.SubprocessError (inclusive TimeoutExpired), quando não roda. Ponto único que os testes trocam."""
    exe = _wsl_do_sistema()
    if exe is None:
        raise FileNotFoundError("wsl.exe do sistema ausente")
    env = {k: v for k, v in os.environ.items() if k != "WSL_UTF8"}  # sem ela a saída é UTF-16, que é o que se lê
    r = subprocess.run([exe, *args], capture_output=True, timeout=prazo_s, stdin=subprocess.DEVNULL, env=env,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode, r.stdout


def _nomes_do_wsl(dados: bytes) -> list[str] | None:
    """Os nomes (um por linha) da saída `-q` do wsl.exe, em UTF-16 LE; None se a saída não é UTF-16 legível."""
    if len(dados) % 2:
        return None
    try:
        texto = dados.decode("utf-16-le")
    except UnicodeDecodeError:
        return None
    return [linha.strip() for linha in texto.lstrip("\ufeff").splitlines() if linha.strip()]
