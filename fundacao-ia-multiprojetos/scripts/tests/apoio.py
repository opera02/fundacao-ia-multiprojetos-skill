"""Apoio aos testes dos scripts da skill (pastas descartáveis; só biblioteca padrão)."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
SKILL = SCRIPTS.parent
KIT = SKILL / "assets" / "fundacao-kit"
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
ENV.pop("FUNDACAO_PRINCIPAL", None)


def rodar_script(nome: str, *args, cwd: Path | None = None, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / nome), *map(str, args)], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=ENV, timeout=timeout,
                          cwd=str(cwd) if cwd else None)


def criar_ligacao_dir(link: Path, alvo: Path) -> str:
    """Junção no Windows (`mklink /J`, sem administrador); link simbólico nos demais sistemas."""
    if os.name == "nt":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(alvo)], capture_output=True, text=True,
                           errors="replace")
        if r.returncode != 0:
            raise unittest.SkipTest(f"junção indisponível neste ambiente: {r.stdout.strip()} {r.stderr.strip()}")
        return "juncao"
    try:
        link.symlink_to(alvo, target_is_directory=True)
    except OSError as exc:
        raise unittest.SkipTest(f"link simbólico indisponível neste ambiente: {exc}") from None
    return "link-simbolico"


def versao_do_kit(base: Path) -> str:
    for linha in (base / "fundacao" / "__init__.py").read_text(encoding="utf-8").splitlines():
        if linha.startswith("KIT_VERSION"):
            return linha.split("=", 1)[1].strip().strip('"')
    raise AssertionError("KIT_VERSION não encontrado")
