"""CI pública da 1.7.2 (Windows): o perfil do executor do GitHub tem nome curto (RUNNER~1). Depois de uma troca
interrompida com a marca ilegível (CF-04), a ligação `~/.claude/skills/<nome>` fica pendurada, e o Python devolve o
alvo dela como foi gravado (nome curto), enquanto a cópia esperada sai pelo caminho final (nome longo). O instalador
tomava a ligação por outra e recusava o `atualizar`.

Neste PC os nomes curtos estão desligados; o mesmo efeito vem de uma junção (Windows) ou de um link simbólico (Linux)
no caminho do perfil. Falha no instalador da 1.7.2 no Windows e passa na 1.7.3.
"""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

import test_conferencia_1_4_3 as cf04  # importado como módulo: a classe de origem não roda duas vezes
from test_relatorio_tecnico_1_4_0 import NOME


def apelido_para(apelido: Path, real: Path) -> None:
    """Junção (Windows) ou link simbólico (Linux) `apelido` -> `real`."""
    if os.name == "nt":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(apelido), str(real)], capture_output=True, text=True,
                           errors="replace")
        if r.returncode != 0:
            raise unittest.SkipTest(f"junção indisponível: {r.stdout} {r.stderr}")
    else:
        os.symlink(real, apelido, target_is_directory=True)


class TestCF04PerfilPorCaminhoAlternativo(cf04.TestCF04MarcaIlegivel):
    """O mesmo cenário do CF-04, com o perfil aberto por um caminho que não é o final."""

    def setUp(self):
        super().setUp()
        real = self.base / "perfil-real"
        real.mkdir()
        apelido = self.base / "perfil-apelido"
        apelido_para(apelido, real)
        self.perfil = apelido
        self.env.update(USERPROFILE=str(apelido), HOME=str(apelido))
        self.copia = apelido / ".agents" / "skills" / NOME
        self.link = apelido / ".claude" / "skills" / NOME


if __name__ == "__main__":
    unittest.main()
