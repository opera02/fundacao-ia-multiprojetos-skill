"""Hash canônico reprodutível entre Windows e WSL.

Texto: UTF-8, sem BOM, quebras de linha LF, normalização Unicode NFC.
JSON: receita própria do kit — chaves ordenadas por ponto de código (`sort_keys` do Python),
sem espaços, UTF-8 sem escapes ASCII e NFC nas strings e nas chaves. NÃO é o JCS da RFC 8785
(que não normaliza Unicode e ordena as chaves por unidades UTF-16; auditoria A11). Floats são
rejeitados para evitar divergência de serialização (use strings decimais, como o livro
recomenda), e chaves distintas que ficariam iguais depois da NFC também: seriam fundidas em
silêncio, e o hash cobriria só uma delas. Entrada sem colisão produz o mesmo texto e o mesmo
hash das versões anteriores.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any

HASH_ALG = "sha256"


def canonical_text(text: str) -> str:
    """Normaliza texto: remove BOM, converte CRLF/CR em LF e aplica NFC."""
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", text)


def _reject_floats(value: Any) -> None:
    if isinstance(value, float):
        raise ValueError("JSON canônico não aceita float; use string decimal")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("chaves JSON devem ser strings")
            _reject_floats(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_floats(item)


def canonical_json(value: Any) -> str:
    """Serialização determinística (ordem de chaves, sem espaços, NFC nas strings e nas chaves).
    Chaves que colidem depois da NFC são recusadas (ValueError), nunca fundidas."""
    _reject_floats(value)

    def norm(obj: Any) -> Any:
        if isinstance(obj, str):
            return unicodedata.normalize("NFC", obj)
        if isinstance(obj, dict):
            saida = {}
            for chave, item in obj.items():
                nfc = unicodedata.normalize("NFC", chave)
                if nfc in saida:  # a compreensão de dicionário guardaria só a última, sem aviso (A11)
                    raise ValueError("chaves JSON distintas ficam iguais depois da normalização NFC")
                saida[nfc] = norm(item)
            return saida
        if isinstance(obj, (list, tuple)):
            return [norm(v) for v in obj]
        return obj

    return json.dumps(norm(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(canonical_text(text).encode("utf-8"))


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def sha256_file(path: Path, *, text_mode: bool = False) -> str:
    """Hash do arquivo. Em `text_mode`, aplica a normalização canônica de texto."""
    data = Path(path).read_bytes()
    if text_mode:
        return sha256_text(data.decode("utf-8"))
    return sha256_bytes(data)
