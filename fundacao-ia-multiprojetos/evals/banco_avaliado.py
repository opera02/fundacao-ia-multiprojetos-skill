#!/usr/bin/env python3
"""Banco SQLite do ambiente avaliado lido como DADO, com limite (apoio de verificar_execucoes.py).

O banco vem de quem foi avaliado (auditoria 1.5.0, achado 5): o esquema pode trazer visão que não termina, tabela
virtual, gatilho ou coluna gerada que consome tempo e memória. Revisão de segurança da 1.7.7 (R177-VAL-09): um
`event` plantado como visão recursiva travava a coleta. Aqui:
- o banco abre somente leitura (URI `mode=ro`), com `query_only` e `trusted_schema=OFF` (função não inócua não roda
  a partir do esquema);
- maior texto ou blob que uma consulta pode montar: `TETO_VALOR` bytes;
- tempo limite por banco aberto (`LIMITE_S`), conferido a cada `PASSOS` instruções do SQLite
  (`set_progress_handler`): a consulta que passa dele é interrompida e vira fato;
- as tabelas que o verificador lê têm de ser tabelas comuns no sqlite_master (`nao_tabelas`): visão e tabela virtual
  não são lidas. A tabela virtual é reconhecida com qualquer separador que o SQLite aceita entre CREATE e VIRTUAL
  (espaços, quebra de linha, comentário): o SQLite grava o texto normalizado, mas um esquema escrito à mão
  (`writable_schema`) com `CREATE  VIRTUAL` passava por tabela comum (segunda passada da revisão).
"""
from __future__ import annotations

import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

LIMITE_S = 5.0
PASSOS = 1000
TETO_VALOR = 10_000_000
CREATE_VIRTUAL = re.compile(r"\s*CREATE(?:\s|/\*.*?\*/|--[^\n]*\n)+VIRTUAL\b", re.IGNORECASE | re.DOTALL)


def uri_somente_leitura(caminho: Path) -> str:
    """URI `file:` somente leitura, como em scripts/backup_sqlite.py e no kit: `as_uri()` codifica
    `#`, `%` e espaços; caminho UNC ou longo do Windows sai com autoridade, que o SQLite recusa
    (`file:////` deixa a autoridade vazia)."""
    uri = Path(caminho).resolve().as_uri()
    if not uri.startswith("file:///"):
        uri = "file:////" + uri[len("file://"):]
    return uri + "?mode=ro"


@contextmanager
def aberto(caminho: Path):
    """Conexão somente leitura, sem confiar no esquema e com tempo limite (o limite começa a contar aqui)."""
    con = sqlite3.connect(uri_somente_leitura(caminho), uri=True)
    try:
        prazo = time.monotonic() + LIMITE_S
        con.set_progress_handler(lambda: int(time.monotonic() > prazo), PASSOS)
        con.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, TETO_VALOR)
        con.execute("PRAGMA trusted_schema = OFF")
        con.execute("PRAGMA query_only = ON")
        yield con
    finally:
        con.close()


def nao_tabelas(con: sqlite3.Connection, nomes: tuple[str, ...]) -> list[str]:
    """Os nomes (sem caixa, como o SQLite compara) que não são tabela comum: ausente, visão ou tabela virtual."""
    tipos = {nome.casefold(): (tipo, sql or "") for nome, tipo, sql in con.execute(
        "SELECT name, type, sql FROM sqlite_master WHERE type IN ('table', 'view')")}
    fora = []
    for nome in nomes:
        tipo, sql = tipos.get(nome.casefold(), ("ausente", ""))
        if tipo != "table" or CREATE_VIRTUAL.match(sql):
            fora.append(f"{nome} ({'tabela virtual' if tipo == 'table' else tipo})")
    return fora


def descrever(exc: sqlite3.Error) -> str:
    """Erro do SQLite como fato curto; a interrupção pelo limite diz qual foi o limite."""
    if "interrupted" in str(exc):
        return f"consulta interrompida: passou do tempo limite de {LIMITE_S:g} s por banco"
    return f"{type(exc).__name__}: {exc}"[:200]
