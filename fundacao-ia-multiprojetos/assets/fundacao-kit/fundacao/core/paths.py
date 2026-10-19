"""Identificadores e contenção de caminhos.

Pastas separadas organizam, mas não isolam. Toda leitura passa por
`contained()` e pela autorização do serviço (livro, A07; Path.resolve não
autentica ninguém).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .contracts import PathEscape, ValidationError

ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def validate_id(value: str, kind: str = "identificador") -> str:
    """Aceita somente a forma canônica; não normaliza silenciosamente."""
    if not isinstance(value, str):
        raise ValidationError(f"{kind} deve ser texto")
    if value != value.strip():
        raise ValidationError(f"{kind} com espaços nas bordas: use a forma canônica")
    if not ID_RE.match(value) or "--" in value:
        raise ValidationError(
            f"{kind} inválido: use 1-40 caracteres [a-z0-9-], sem hífen nas pontas ou duplo",
            value=value,
        )
    if value in WINDOWS_RESERVED:
        raise ValidationError(f"{kind} usa nome reservado do Windows", value=value)
    return value


def contained(root: Path, candidate: Path, *, within: Path | None = None) -> Path:
    """Resolve `candidate` e garante que permaneça dentro de `root` (inclui links).

    `within`: raiz confiável que também precisa conter o caminho final. Use quando `root` é uma
    subpasta que quem opera o projeto pode trocar por ligação (ex.: `data/` dentro da pasta do
    projeto): se `root` apontar para fora de `within`, o caminho é recusado (auditoria F04).
    """
    root_r = Path(root).resolve()
    cand = Path(candidate)
    if not cand.is_absolute():
        cand = root_r / cand
    cand_r = cand.resolve()
    for base in (root_r, Path(within).resolve() if within is not None else None):
        if base is None:
            continue
        try:
            cand_r.relative_to(base)
        except ValueError:
            raise PathEscape("caminho fora da raiz autorizada", root=str(Path(root).name)) from None
    return cand_r


def exact_child(parent: Path, name: str) -> Path:
    """`parent/name` resolvido, recusando se `name` for ligação que redireciona para outro lugar.

    `parent` é confiável (ex.: `projects/`); o filho precisa ser ele mesmo, não um atalho para a
    pasta de outro projeto (auditoria F04)."""
    base = Path(parent).resolve()
    final = (base / name).resolve()
    if os.path.normcase(str(final)) != os.path.normcase(str(base / name)):
        raise PathEscape("pasta redirecionada por ligação: recusada", nome=name)
    return final
