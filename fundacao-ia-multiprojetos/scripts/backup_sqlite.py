#!/usr/bin/env python3
"""Cópia consistente de um banco SQLite qualquer (projeto existente ou fundação).

Usa a API de backup do SQLite (funciona com o banco em uso) e confere
`PRAGMA integrity_check` e a contagem lógica por tabela na origem e na cópia.
Bytes diferentes entre origem e cópia são normais; compare os dados lógicos.
A origem é aberta somente leitura. Se ela estiver em modo WAL e sem os arquivos
`-wal`/`-shm` (banco fechado), o próprio SQLite os cria vazios ao abrir; a saída
lista esses arquivos em `arquivos_auxiliares_criados` (não alteram dados).

Uso: python backup_sqlite.py --origem app.sqlite --destino ref/app.sqlite
Código 1 se a integridade falhar, as contagens divergirem ou a cópia não puder ser feita
(erro em JSON; nada fica criado no destino).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def uri_somente_leitura(path: Path) -> str:
    """`as_uri()` codifica '#', '%' e espaços (sem isso, '#' vira fragmento e o SQLite abriria ou
    criaria outro arquivo). Caminho de rede (UNC) ou com o prefixo de caminho longo do Windows sai
    com autoridade (`file://servidor/...`), que o SQLite recusa: `file:////` deixa a autoridade vazia."""
    uri = Path(path).resolve().as_uri()
    if not uri.startswith("file:///"):
        uri = "file:////" + uri[len("file://"):]
    return uri + "?mode=ro"


def summary(path: Path) -> dict:
    con = sqlite3.connect(uri_somente_leitura(path), uri=True)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        counts = {}
        for t in tables:
            try:
                counts[t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            except sqlite3.OperationalError as exc:  # tabelas virtuais sem módulo carregado
                counts[t] = f"indisponivel: {exc}"
        return {"integrity_check": con.execute("PRAGMA integrity_check").fetchone()[0],
                "user_version": con.execute("PRAGMA user_version").fetchone()[0],
                "journal_mode": con.execute("PRAGMA journal_mode").fetchone()[0], "tabelas": counts}
    finally:
        con.close()


def erro(mensagem: str, exc: Exception | None = None) -> int:
    dados = {"erro": mensagem}
    if exc is not None:
        dados.update({"tipo": type(exc).__name__, "detalhe": str(exc)})
    print(json.dumps(dados, ensure_ascii=False))
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--origem", type=Path, required=True)
    ap.add_argument("--destino", type=Path, required=True)
    args = ap.parse_args()
    if args.destino.exists():
        return erro("destino já existe; não sobrescrevo uma referência")
    if not args.origem.is_file():
        # sqlite3.connect criaria um banco vazio na origem e a "referência" sairia vazia.
        return erro("origem inexistente: nada copiado e nada criado")
    auxiliares = [Path(str(args.origem) + s) for s in ("-wal", "-shm")]
    existiam = {p for p in auxiliares if p.exists()}
    # Pastas que faltam para o destino, da mais funda para a mais rasa: em caso de falha, só elas
    # (e só se vazias) são removidas — nada fica criado no destino.
    criadas = [d for d in (args.destino.parent, *args.destino.parent.parents) if not d.exists()]
    try:
        src = sqlite3.connect(uri_somente_leitura(args.origem), uri=True)  # somente leitura
        try:
            src.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()  # abre de fato antes de criar o destino
            args.destino.parent.mkdir(parents=True, exist_ok=True)
            dst = sqlite3.connect(str(args.destino))
            try:
                src.backup(dst)
                dst.execute("PRAGMA journal_mode = DELETE")  # cópia fora do WAL: conferir não cria -wal/-shm
            finally:
                dst.close()
        finally:
            src.close()
        a, b = summary(args.origem), summary(args.destino)
    except (sqlite3.Error, OSError) as exc:
        args.destino.unlink(missing_ok=True)
        for d in criadas:
            try:
                d.rmdir()
            except OSError:
                break
        return erro("cópia não realizada: o banco de origem não pôde ser lido ou o destino gravado", exc)
    ok = b["integrity_check"] == "ok" and a["tabelas"] == b["tabelas"]
    criados = sorted(str(p) for p in auxiliares if p.exists() and p not in existiam)
    print(json.dumps({"ok": ok, "origem": a, "copia": b, "arquivos_auxiliares_criados": criados},
                     ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
