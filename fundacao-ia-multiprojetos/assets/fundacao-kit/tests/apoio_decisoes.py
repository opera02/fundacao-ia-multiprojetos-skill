"""Apoio aos testes das decisões assinadas: chaves e âncora de ENSAIO, geradas na hora numa pasta temporária.

Nunca usa a chave nem a âncora do titular: as chaves de ensaio não têm senha e somem com a pasta. Sem
`ssh-keygen` no sistema, o teste que depende dele é pulado e o motivo fica no relatório.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from fundacao.core import decisoes


def keygen() -> str:
    try:
        return decisoes.ssh_keygen()
    except FileNotFoundError as exc:
        raise unittest.SkipTest(f"ssh-keygen indisponível neste ambiente: {exc}") from None


class Chaves:
    """Duas chaves de ensaio (`titular-ensaio` e `intruso`) e uma âncora que só conhece a do titular de ensaio."""

    def __init__(self, base: Path, principal: str = "titular-ensaio"):
        self.principal = principal
        self.pasta = Path(base) / "chaves"
        self.pasta.mkdir(parents=True)
        for nome in ("titular-ensaio", "intruso"):
            subprocess.run([keygen(), "-q", "-t", "ed25519", "-N", "", "-C", nome, "-f", str(self.pasta / nome)],
                           check=True, capture_output=True)
        self.ancora = Path(base) / "ancora" / "allowed_signers"
        self.ancora.parent.mkdir(parents=True)
        pub = (self.pasta / "titular-ensaio.pub").read_text(encoding="ascii").strip()
        self.ancora.write_text(f'{principal} namespaces="{decisoes.NAMESPACE}" {pub}\n', encoding="ascii")

    def chave(self, nome: str = "titular-ensaio") -> Path:
        return self.pasta / nome

    def assinar(self, arquivo: Path, chave: str = "titular-ensaio", namespace: str = decisoes.NAMESPACE) -> Path:
        sig = Path(str(arquivo) + ".sig")
        sig.unlink(missing_ok=True)
        subprocess.run([keygen(), "-Y", "sign", "-f", str(self.chave(chave)), "-n", namespace, str(arquivo)],
                       check=True, capture_output=True)
        return sig
