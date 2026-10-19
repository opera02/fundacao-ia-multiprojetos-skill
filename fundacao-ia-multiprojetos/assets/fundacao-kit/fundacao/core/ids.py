"""Identificadores ordenáveis no tempo (UUIDv7, RFC 9562) com prefixo legível."""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """Gera um UUID versão 7 (48 bits de milissegundos + bits aleatórios)."""
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76  # versão 7
    value |= ((rand >> 62) & 0xFFF) << 64  # rand_a (12 bits)
    value |= 0b10 << 62  # variante RFC 4122/9562
    value |= rand & ((1 << 62) - 1)  # rand_b (62 bits)
    return uuid.UUID(int=value)


def new_id(prefix: str) -> str:
    """Ex.: new_id('run') -> 'run_01926f3a-7c1e-7b2a-9c1d-3f0e8a1b2c3d'."""
    if not prefix.isidentifier():
        raise ValueError("prefixo inválido")
    return f"{prefix}_{uuid7()}"
