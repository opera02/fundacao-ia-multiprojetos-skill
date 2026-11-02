#!/usr/bin/env python3
"""Inventário do ambiente (livro A01; Apêndice D), com os efeitos declarados.

Identifica sistema, shell, pasta, recursos e programas presentes, separando:
  presente (arquivo encontrado) | executado (versão consultada) | não verificado.
Efeitos (auditoria da 1.4.1, A18):
  --somente-localizar  não executa programa externo: só presença e caminho. Use enquanto o
                       escopo não autorizar executar CLIs.
  sem essa opção       executa `--version` de git, node, npm, uv, claude, codex e docker,
                       `pymanager list` ou `py -0p` e `wsl --list --verbose` (lista; não inicia WSL).
  --saida ARQ          grava o JSON (cria as pastas) e recusa arquivo existente (código 1, nada
                       executado) para não apagar evidência anterior. Sem --saida, nada é gravado.
O que lê fora da pasta, nos dois modos (R179-36 F3, 1.7.10; antes, este texto dizia que não lia
valores de variáveis de ambiente):
  variáveis de ambiente  PATH, só as pastas absolutas (e PATHEXT, no Windows), para localizar os
                         programas: a pasta atual não entra (`localizar`); no Windows, onde o
                         shutil.which olha antes a pasta atual salvo com NoDefaultCurrentDirectoryInExePath,
                         o script define essa variável no próprio processo (e ela passa aos
                         programas que ele roda com --version); os valores de CODESPACES,
                         REMOTE_CONTAINERS, SHELL (grava só o nome do programa) e PYTHONUTF8; só a
                         presença de COMSPEC e PSModulePath; no Windows, PROCESSOR_ARCHITEW6432
                         e PROCESSOR_ARCHITECTURE (a arquitetura);
  sistema                CPUs, RAM e espaço livre do volume da pasta; fora do Windows, os.uname
                         (sistema, versão e arquitetura), /proc/version, /proc/mounts e se /.dockerenv
                         existe; no Windows, o registro (LongPathsEnabled) e APIs do sistema (memória,
                         volume da pasta e versão do Windows, por sys.getwindowsversion);
  Python                 as pastas de módulos do interpretador em execução, para saber se os módulos
                         opcionais existem (importlib.util.find_spec: não os importa).
Sistema e versão vêm sem processo (`sistema_operacional`). Nunca instala nada, não lê credenciais
nem muda autenticação. Para Python, consulta apenas o interpretador que já está executando este
script; outros lançadores são listados pelo gerenciador (o lançador pode instalar Python
automaticamente se não houver nenhum — por isso não executamos `python --version` às cegas).

Uso: python inspecionar_ambiente.py [--pasta DIR] [--saida inventario-<data>.json] [--somente-localizar]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SAFE_VERSION = {  # comandos de efeito conhecido (consulta de versão)
    "git": ["--version"], "node": ["--version"], "npm": ["--version"], "uv": ["--version"],
    "claude": ["--version"], "codex": ["--version"], "docker": ["--version"],
}
LIST_ONLY = ["python", "python3", "py", "pymanager", "wsl", "pwsh", "powershell", "bash"]
OPTIONAL_MODULES = ["torch", "transformers", "jsonschema", "yaml", "mcp", "langgraph", "dbos", "pytest"]


def run(cmd: list[str], timeout: int = 15) -> dict:
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"executado": False, "erro": type(exc).__name__}
    raw = p.stdout or p.stderr
    if b"\x00" in raw:  # wsl.exe responde em UTF-16LE
        text = raw.decode("utf-16-le", "replace")
    else:
        text = raw.decode("utf-8", "replace")
    return {"executado": True, "codigo_saida": p.returncode, "saida": text.replace("\x00", "").strip()[:400]}


def ram_bytes() -> int | None:
    try:
        if sys.platform == "win32":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = MS()
            ms.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            return int(ms.ullTotalPhys)
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except Exception:
        return None


def sistema_operacional() -> dict:
    """Sistema, versão e arquitetura sem abrir processo (R179-36 F3, 1.7.10).

    `platform.platform()` desempacotava o `uname()` em seis campos e forçava o `processor` preguiçoso, que no Linux
    roda `uname -p` (CPython, `platform._Processor.from_subprocess`), inclusive com --somente-localizar.
    `platform.system()`, `release()` e `machine()` não tocam o `processor` e, fora do Windows, vêm do `os.uname()`.
    No Windows, o `uname()` do `platform` roda o comando `ver` (`platform._syscmd_ver`) quando a consulta WMI falha
    (CPython 3.12, `platform._win32_ver`): lá, a versão vem de `sys.getwindowsversion()` e a arquitetura, das
    variáveis PROCESSOR_ARCHITEW6432 e PROCESSOR_ARCHITECTURE. A versão é a de major/minor/build, a mesma da consulta
    WMI; o `platform_version` vem da versão do kernel32.dll e pode ficar atrás (10.0.26100 num 10.0.26200)."""
    if sys.platform == "win32":
        versao = sys.getwindowsversion()
        maquina = os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE")
        return {"plataforma": f"Windows-{versao.major}.{versao.minor}.{versao.build}", "maquina": maquina or None}
    nome = "-".join(p for p in (platform.system(), platform.release()) if p)
    return {"plataforma": nome or None, "maquina": platform.machine() or None}


def localizar(nome: str) -> str | None:
    """Caminho absoluto do programa, procurado só nas pastas absolutas do PATH (revisão do AJUSTES-179, 1.7.10).

    A pasta atual não entra: no Windows, o shutil.which do Python 3.12 olha antes a pasta atual, salvo com
    NoDefaultCurrentDirectoryInExePath definida (o terminal comum não a define; o `main` a define no próprio processo);
    nos dois sistemas, entrada vazia ou relativa do PATH é a pasta atual. Sem isso, um git.bat ou um `git` posto na
    pasta atual (código importado é dado, não programa) seria dado como o git e rodaria com --version. O caminho
    relativo que ainda sobrar (sem a variável no Windows) é descartado: o programa fica como ausente."""
    pastas = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep) if p and os.path.isabs(p))
    caminho = shutil.which(nome, path=pastas) if pastas else None
    return caminho if caminho and os.path.isabs(caminho) else None


def access_kind() -> str:
    if sys.platform == "win32":
        return "windows_nativo"
    try:
        if "microsoft" in Path("/proc/version").read_text().lower():
            return "wsl"
    except OSError:
        pass
    if Path("/.dockerenv").exists() or os.environ.get("CODESPACES") or os.environ.get("REMOTE_CONTAINERS"):
        return "conteiner_ou_remoto"
    return "linux_ou_macos"


def sqlite_info() -> dict:
    con = sqlite3.connect(":memory:")
    try:
        con.execute("CREATE VIRTUAL TABLE t USING fts5(x, tokenize='unicode61 remove_diacritics 2')")
        fts = True
    except sqlite3.OperationalError:
        fts = False
    finally:
        con.close()
    return {"versao": sqlite3.sqlite_version, "fts5_unicode61_remove_diacritics_2": fts}


def filesystem_of(path: Path) -> str | None:
    """Tipo do sistema de arquivos da pasta (NTFS, exFAT, ext4...), sem processo externo.
    exFAT/FAT não têm permissões do SO: separar projetos em pastas ali é só organização."""
    try:
        target = path if path.exists() else Path.cwd()
        if sys.platform == "win32":
            import ctypes
            drive = os.path.splitdrive(str(target.resolve()))[0] + "\\"
            buf = ctypes.create_unicode_buffer(64)
            ok = ctypes.windll.kernel32.GetVolumeInformationW(ctypes.c_wchar_p(drive), None, 0, None, None,
                                                              None, buf, len(buf))
            return buf.value if ok else None
        best, fstype = "", None
        with open("/proc/mounts", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 3 and str(target.resolve()).startswith(parts[1]) and len(parts[1]) > len(best):
                    best, fstype = parts[1], parts[2]
        return fstype
    except (OSError, AttributeError, ValueError):
        return None


def long_paths_enabled() -> bool | None:
    """Windows: LongPathsEnabled no registro (leitura). A pasta de trabalho (cwd) de um
    processo continua limitada a 260 caracteres mesmo com o recurso ligado."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as k:
            return bool(winreg.QueryValueEx(k, "LongPathsEnabled")[0])
    except OSError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", type=Path, default=Path.cwd())
    ap.add_argument("--saida", type=Path, help="grava o JSON; recusa arquivo existente")
    ap.add_argument("--somente-localizar", action="store_true",
                    help="não executa programas externos; só registra presença e caminho")
    args = ap.parse_args()
    recusa = {"erro": "--saida já existe: escolha um nome novo para preservar a evidência anterior"}
    if args.saida and (args.saida.exists() or args.saida.is_symlink()):
        print(json.dumps(recusa, ensure_ascii=False))
        return 1
    pasta = args.pasta.resolve()
    if sys.platform == "win32":  # o shutil.which não olha a pasta atual (`localizar`)
        os.environ.setdefault("NoDefaultCurrentDirectoryInExePath", "1")
    tools = {}
    for name in sorted(set(SAFE_VERSION) | set(LIST_ONLY)):
        path = localizar(name)
        entry = {"presente": bool(path), "caminho": path}
        if path and args.somente_localizar:
            entry["nivel"] = "presente (execução desativada por --somente-localizar)"
        elif path and name in SAFE_VERSION:
            entry["versao"] = run([path, *SAFE_VERSION[name]])
            entry["nivel"] = "executado (versão)" if entry["versao"].get("executado") else "presente"
        elif path:
            entry["nivel"] = "presente (versão não consultada de propósito)"
        tools[name] = entry
    if args.somente_localizar:
        pass
    elif tools.get("pymanager", {}).get("presente"):
        tools["pymanager"]["listagem"] = run([tools["pymanager"]["caminho"], "list"])
    elif tools.get("py", {}).get("presente"):
        tools["py"]["listagem"] = run([tools["py"]["caminho"], "-0p"])
    if not args.somente_localizar and tools.get("wsl", {}).get("presente") and sys.platform == "win32":
        tools["wsl"]["distribuicoes"] = run([tools["wsl"]["caminho"], "--list", "--verbose"])  # lista, não inicia
    usage = shutil.disk_usage(pasta if pasta.exists() else Path.cwd())
    result = {
        "schema_version": "fundacao.inventario_ambiente/1",
        "observado_em": datetime.now(timezone.utc).isoformat(),
        "acesso": access_kind(),
        "sistema": {**sistema_operacional(), "cpus": os.cpu_count(), "ram_bytes": ram_bytes()},
        "pasta": {"caminho": str(pasta), "existe": pasta.exists(), "livre_bytes": usage.free,
                  "no_onedrive": "onedrive" in str(pasta).lower(),
                  "sistema_de_arquivos": (fs := filesystem_of(pasta)),
                  "comprimento_do_caminho": len(str(pasta)),
                  "caminhos_longos_windows": long_paths_enabled(),
                  "permissoes_do_so": None if fs is None else fs.upper() not in ("EXFAT", "FAT32", "FAT", "VFAT"),
                  "wsl_em_mnt_c": str(pasta).startswith("/mnt/")},
        "shell": {"COMSPEC_definido": "COMSPEC" in os.environ, "SHELL": Path(os.environ.get("SHELL", "")).name or None,
                  "PSModulePath_definido": "PSModulePath" in os.environ},
        "python_em_execucao": {"executavel": sys.executable, "versao": platform.python_version(),
                               "venv_ativo": sys.prefix != sys.base_prefix,
                               "PYTHONUTF8": os.environ.get("PYTHONUTF8") == "1"},
        "sqlite": sqlite_info(),
        "modulos_opcionais": {m: importlib.util.find_spec(m) is not None for m in OPTIONAL_MODULES},
        "programas": tools,
        "nao_verificado": [
            "autenticação e modalidade das contas (assinatura × API)", "saldo, créditos e limites",
            "sandbox efetivo", "permissões do sistema operacional entre projetos",
        ],
        "observacao": "Versão encontrada não prova autenticação nem integração funcional (livro A01/A03).",
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.saida:
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(args.saida, "x", encoding="utf-8") as fh:  # "x": nunca substitui
                fh.write(text)
        except FileExistsError:
            print(json.dumps(recusa, ensure_ascii=False))
            return 1
    print(text)
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
