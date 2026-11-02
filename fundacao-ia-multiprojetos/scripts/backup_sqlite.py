#!/usr/bin/env python3
"""Cópia consistente de um banco SQLite qualquer (projeto existente ou fundação).

Usa a API de backup do SQLite (funciona com o banco em uso) e confere
`PRAGMA integrity_check` e a contagem lógica por tabela na origem e na cópia. A origem é
resumida no MESMO snapshot que foi copiado (a transação de leitura abre antes da cópia):
um escritor concorrente não faz a conferência comparar outro instante.
Bytes diferentes entre origem e cópia são normais; compare os dados lógicos.
Erro ao contar interrompe (vira erro, nunca dado). Só a tabela virtual cujo módulo não
existe neste Python (ex.: vec0) fica sem contagem, declarada em `tabelas_nao_contadas`.
A origem é aberta somente leitura. Se ela estiver em modo WAL e sem os arquivos
`-wal`/`-shm` (banco fechado), o próprio SQLite os cria vazios ao abrir; a saída
lista esses arquivos em `arquivos_auxiliares_criados` (não alteram dados).

Antes de abrir a origem, a trava do banco entre o Windows e o Ubuntu (item I7 da integração da
1.7.10; emenda E7 dos contratos do lote 2): o marcador `banco.trava` do OUTRO lado na pasta do
banco (o state/ da fundação, que o porteiro do Ubuntu segura; num banco de projeto, normalmente
ausente) recusa, vivo, velho ou ilegível. A regra vem do kit desta skill (core/trava_banco.py).

Uso: python backup_sqlite.py --origem app.sqlite --destino ref/app.sqlite
Código 1 se a integridade falhar, as contagens divergirem, o banco estiver travado pelo outro lado
ou a cópia não puder ser feita (erro em JSON; nada fica criado no destino).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[1] / "assets" / "fundacao-kit"  # o kit desta skill (a trava do banco)


def _trava_banco():
    """core/trava_banco.py do kit DESTA skill (item I7 da integração da 1.7.10), importado só quando um banco vai ser
    aberto; um `fundacao` carregado de outro lugar recusa, como em assets/host/fundacao_titular.py."""
    if str(KIT) not in sys.path:
        sys.path.insert(0, str(KIT))
    from fundacao.core import trava_banco
    if not Path(trava_banco.__file__).resolve().is_relative_to(KIT.resolve()):
        raise ImportError("o kit carregado não é o desta skill (" + str(trava_banco.__file__) + ")")
    return trava_banco


def conferir_trava(origem: Path) -> None:
    """A trava do banco antes de abrir `origem`: o marcador do outro lado na pasta dele levanta BancoTravado; sem o kit
    desta skill, ImportError (a cópia não é feita sem a conferência). Sem marcador, ou com o do mesmo lado, nada."""
    _trava_banco().conferir(Path(origem).parent)


def uri_somente_leitura(path: Path) -> str:
    """`as_uri()` codifica '#', '%' e espaços (sem isso, '#' vira fragmento e o SQLite abriria ou
    criaria outro arquivo). Caminho de rede (UNC) ou com o prefixo de caminho longo do Windows sai
    com autoridade (`file://servidor/...`), que o SQLite recusa: `file:////` deixa a autoridade vazia."""
    uri = Path(path).resolve().as_uri()
    if not uri.startswith("file:///"):
        uri = "file:////" + uri[len("file://"):]
    return uri + "?mode=ro"


def identificador(nome: str) -> str:
    """Nome de tabela entre aspas, com as aspas internas dobradas (nome não pode ir como parâmetro)."""
    return '"' + nome.replace('"', '""') + '"'


def resumo(con: sqlite3.Connection) -> dict:
    """Integridade, `user_version` e contagem por tabela pela conexão dada — na origem, a mesma
    transação de leitura que fez a cópia (A14). Erro de contagem interrompe (A15); só a tabela
    virtual cujo módulo não está carregado fica fora, declarada à parte."""
    counts, nao_contadas = {}, {}
    # No LIKE, `_` é curinga: sem o escape, uma tabela `sqlite1` ficaria sem contagem.
    for nome, sql in con.execute(r"SELECT name, sql FROM sqlite_master WHERE type = 'table'"
                                 r" AND name NOT LIKE 'sqlite\_%' ESCAPE '\' ORDER BY name").fetchall():
        try:
            counts[nome] = con.execute(f"SELECT COUNT(*) FROM {identificador(nome)}").fetchone()[0]
        except sqlite3.OperationalError as exc:
            if not (str(sql or "").lstrip().upper().startswith("CREATE VIRTUAL TABLE")
                    and "no such module" in str(exc)):
                raise
            nao_contadas[nome] = str(exc)
    dados = {"integrity_check": con.execute("PRAGMA integrity_check").fetchone()[0],
             "user_version": con.execute("PRAGMA user_version").fetchone()[0],
             "journal_mode": con.execute("PRAGMA journal_mode").fetchone()[0], "tabelas": counts}
    if nao_contadas:
        dados["tabelas_nao_contadas"] = nao_contadas
    return dados


def summary(path: Path) -> dict:
    conferir_trava(path)  # antes de abrir (item I7 da integração)
    con = sqlite3.connect(uri_somente_leitura(path), uri=True)
    try:
        con.execute("BEGIN")  # todas as contagens no mesmo instante
        return resumo(con)
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
    try:  # antes de abrir a origem e de criar qualquer coisa no destino (item I7 da integração; emenda E7)
        trava = _trava_banco()
    except ImportError as exc:
        return erro("cópia não realizada: a trava do banco (banco.trava) não foi conferida, porque o kit desta skill "
                    "não carregou; nada copiado e nada criado", exc)
    try:
        trava.conferir(args.origem.parent)
    except trava.BancoTravado as exc:
        return erro("cópia não realizada: o banco de origem está (ou pode estar) em uso pelo outro lado ("
                    + trava.MARCADOR + " na pasta dele); nada copiado e nada criado", exc)
    auxiliares = [Path(str(args.origem) + s) for s in ("-wal", "-shm")]
    existiam = {p for p in auxiliares if p.exists()}
    # Pastas que faltam para o destino, da mais funda para a mais rasa: em caso de falha, só elas
    # (e só se vazias) são removidas — nada fica criado no destino.
    criadas = [d for d in (args.destino.parent, *args.destino.parent.parents) if not d.exists()]
    criou_destino = False
    try:
        src = sqlite3.connect(uri_somente_leitura(args.origem), uri=True)  # somente leitura
        try:
            # A transação de leitura fixa o snapshot: a cópia e o resumo da origem leem o mesmo instante.
            src.execute("BEGIN")
            src.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()  # abre de fato antes de criar o destino
            args.destino.parent.mkdir(parents=True, exist_ok=True)
            with args.destino.open("xb"):  # criação exclusiva: na falha, só se apaga o que foi criado aqui
                criou_destino = True
            dst = sqlite3.connect(str(args.destino))
            try:
                src.backup(dst)
                dst.execute("PRAGMA journal_mode = DELETE")  # cópia fora do WAL: conferir não cria -wal/-shm
                a, b = resumo(src), resumo(dst)
            finally:
                dst.close()
        finally:
            src.close()
    except (sqlite3.Error, OSError) as exc:
        if criou_destino:
            args.destino.unlink(missing_ok=True)
        for d in criadas:
            try:
                d.rmdir()
            except OSError:
                break
        return erro("cópia não realizada: o banco de origem não pôde ser lido ou o destino gravado", exc)
    ok = (b["integrity_check"] == "ok" and a["tabelas"] == b["tabelas"]
          and a.get("tabelas_nao_contadas") == b.get("tabelas_nao_contadas"))
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
