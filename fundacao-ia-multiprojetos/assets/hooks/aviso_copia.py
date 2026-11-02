#!/usr/bin/env python3
"""Hook SessionStart (startup|resume) do Windows: lembra a cópia semanal quando a última passa de 7 dias (1.7.10).

Contratos do lote 2 da 1.7.10, §7. Registro (pacote HOST, só no perfil do Windows): SessionStart com matcher
`startup|resume`, `python -I -B` com o caminho absoluto `<raiz>\\.claude\\hooks\\aviso_copia.py`, prazo curto (3 s).
Lê só `<raiz>/registry/ultima-copia.json` (fundacao.ultima_copia/1, gravado pelo `backup criar` e anotado pelo
`backup verificar`, kit `core/manutencao.py`): sem seguir ligação (nem `registry/` ligada), só arquivo comum com um
vínculo, até 64 KiB, conferido pelo descritor aberto. Não abre state/ nem o banco, não toca o disco das cópias (pode
estar parado) e não chama o kit: texto e comando são montados aqui no formato do `proxima_copia` do `backup situacao`
(rótulo semanal-AAAA-Sss na pasta da última cópia; PowerShell e `python` no Windows, bash e `python3` nos demais).
Sem registro, com registro recusado ou com a última cópia passando de 7 dias: devolve contexto adicional
(hookSpecificOutput.additionalContext) com a data, a idade e o comando pronto; em dia: sem saída. Do registro só vão
ao texto a data (relida e reescrita aqui) e a pasta das cópias, conferida e entre aspas no comando, com o aviso de que
veio de um arquivo que as sessões gravam; o rótulo gravado não vai. A pasta vale só se for caminho local absoluto (no
Windows, com letra de unidade; nos demais, `/` sem `//`), até 400 caracteres, sem rede (`\\\\srv`, `//srv`), URL,
controle, quebra de linha, aspas nem `;|&`$` (revisão de segurança da 1.7.10, HOOK-F2: o registro pode ser forjado e o
titular roda o comando), sem componente `.` ou `..` e com a pasta da próxima cópia fora da raiz (revisão 1 da rodada
4; comparação de texto, sem caixa no Windows: ligação e nome curto não são resolvidos, porque o disco das cópias pode
estar parado) e, no Windows, sem nome terminado em ponto ou espaço, que o Windows tira ao abrir (revisão 2 da rodada
4: `<raiz>.\\state\\x` gravava dentro da raiz); senão, o comando leva o marcador. Raiz: FUNDACAO_RAIZ,
CLAUDE_PROJECT_DIR, o `cwd` do evento ou a pasta atual (FUNDACAO_RAIZ com controle ou longa demais não vale, e o
lembrete diz que a raiz não foi identificada); sem FUNDACAO_RAIZ, a pasta aberta em projects/<p> e sem registry/ sobe
para a de cima de projects/.
Nunca bloqueia a sessão: sai sempre com código 0, lê a entrada com prazo de 1 s e cala em evento que não é SessionStart
startup|resume (inclusive ilegível); erro inesperado vira o lembrete genérico.
Lembrete, não prova (como o `backup situacao`): quem grava registry/ forja o registro; a prova é o `backup verificar`
com o sha256_manifesto guardado fora da cópia. Diferença do kit: sem tocar o disco das cópias, o rótulo da semana não
ganha o sufixo -2, -3...; se a pasta já existir com conteúdo, o `backup criar` recusa e o `backup situacao` traz o
rótulo livre.
"""
from __future__ import annotations

import json
import os
import stat
import sys
import threading
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = "fundacao.ultima_copia/1"
LIMITE_DIAS = 7
TETO = 64 * 1024
PRAZO_ENTRADA = 1.0
LIMITE_PASTA = 400
FONTES = {"startup", "resume"}
NAME_SURROGATE = 0x20000000  # links simbólicos e junções do Windows
_LEITURA = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
# O PowerShell trata como aspa simples também as tipográficas U+2018 a U+201B (kit, core/comando_titular.py).
ASPAS_SIMPLES_POWERSHELL = ("'",) + tuple(chr(c) for c in (0x2018, 0x2019, 0x201A, 0x201B))
# Revisão de segurança da 1.7.10, HOOK-F2: o que não vai ao comando proposto (aspas, também as tipográficas, e `;|&`$`).
PROIBIDOS_NA_PASTA = frozenset("\"'`$;|&") | {chr(c) for c in range(0x2018, 0x2020)}


class Recusado(Exception):
    """Registro que não se lê com segurança (o motivo vai ao texto, sem conteúdo do arquivo)."""


def _aspas_powershell(texto: str) -> str:
    return "'" + "".join(c + c if c in ASPAS_SIMPLES_POWERSHELL else c for c in texto) + "'"


def _aspas_bash(texto: str) -> str:
    return "'" + texto.replace("'", "'" + chr(92) + "''") + "'"


def _ligacao(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & NAME_SURROGATE)


def _data(texto) -> datetime | None:
    """Data ISO com fuso (a do kit, terminada em Z); sem fuso vale UTC; None se não for data."""
    if not isinstance(texto, str) or len(texto) > 64:
        return None
    try:
        data = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    return data if data.tzinfo else data.replace(tzinfo=timezone.utc)


def _texto_limpo(texto) -> str | None:
    """Texto do registro ou do ambiente que pode ir a um comando: sem controle nem formatação invisível."""
    if not isinstance(texto, str) or not texto or len(texto) > LIMITE_PASTA:
        return None
    if any(unicodedata.category(c)[0] == "C" or unicodedata.category(c) in ("Zl", "Zp") for c in texto):
        return None
    return texto


def _dentro(pasta: str, raiz: str) -> bool:
    """A pasta é a raiz ou fica dentro dela (texto normalizado, sem caixa no Windows; sem tocar o disco). Revisão 2 da
    rodada 4 (HOOK-F2): `abspath`, que no Windows é o GetFullPathNameW e tira o ponto e o espaço do fim de cada nome,
    como o Windows faz ao abrir (`<raiz>.\\state\\x` é `<raiz>\\state\\x`; o `normpath` os deixava)."""
    a, b = (os.path.normcase(os.path.abspath(p)) for p in (pasta, raiz))
    try:
        return os.path.commonpath([a, b]) == b
    except ValueError:  # unidades diferentes, ou um relativo
        return False


def _pasta_local(texto, raiz: str | None = None) -> str | None:
    """A pasta das cópias do registro que pode ir ao comando (revisão de segurança da 1.7.10, HOOK-F2): caminho local
    absoluto — no Windows, letra de unidade e barra; nos demais, `/` sem `//` —, sem rede, URL, controle, quebra de
    linha, aspas nem `;|&`$`; desde a revisão 1 da rodada 4, sem componente `.` ou `..` (`C:\\Copias\\..\\..\\Users\\x`)
    e com a pasta da próxima cópia (a de cima do destino gravado) fora da raiz. Revisão 2 da rodada 4: no Windows, sem
    nome terminado em ponto ou espaço (`<raiz>.\\state\\x`, que o Windows lê como `<raiz>\\state\\x`). None se não
    serve (o comando leva o marcador)."""
    pasta = _texto_limpo(texto)
    if not pasta or PROIBIDOS_NA_PASTA & set(pasta) or "://" in pasta:
        return None
    componentes = pasta.replace("\\", "/").split("/")
    if any(c and not c.strip(" .") for c in componentes):
        return None
    if os.name == "nt" and any(c != c.rstrip(" .") for c in componentes):
        return None
    if os.name == "nt":
        local = len(pasta) > 2 and pasta[0].isascii() and pasta[0].isalpha() and pasta[1] == ":" and pasta[2] in "\\/"
        if not local or ":" in pasta[2:]:
            return None
    elif not pasta.startswith("/") or pasta.startswith("//"):
        return None
    return None if raiz and _dentro(str(Path(pasta).parent), raiz) else pasta


def _objeto_sem_duplicatas(pares):
    objeto = {}
    for chave, valor in pares:
        if chave in objeto:
            raise ValueError("chave duplicada")
        objeto[chave] = valor
    return objeto


def _recusar_constante(_):
    raise ValueError("constante não JSON")


def ler_registro(raiz: str) -> dict | None:
    """O registro da última cópia; None se não existe; Recusado se não se lê com segurança."""
    pasta = os.path.join(raiz, "registry")
    arquivo = os.path.join(pasta, "ultima-copia.json")
    try:
        if _ligacao(os.lstat(pasta)):
            raise Recusado("a pasta registry/ é ligação")
        st = os.lstat(arquivo)
    except FileNotFoundError:
        return None
    if _ligacao(st) or not stat.S_ISREG(st.st_mode):
        raise Recusado("não é arquivo comum")
    if st.st_nlink != 1 or st.st_size > TETO:
        raise Recusado("vínculo físico ou acima do teto")
    fd = os.open(arquivo, _LEITURA)
    try:
        aberto = os.fstat(fd)
        if (not stat.S_ISREG(aberto.st_mode) or aberto.st_nlink != 1
                or (aberto.st_dev, aberto.st_ino) != (st.st_dev, st.st_ino)):
            raise Recusado("trocado durante a leitura")
        partes, total = [], 0
        while total <= TETO and (bloco := os.read(fd, min(65536, TETO + 1 - total))):
            partes.append(bloco)
            total += len(bloco)
    finally:
        os.close(fd)
    if total > TETO:
        raise Recusado("acima do teto")
    try:
        dados = json.loads(b"".join(partes).decode("utf-8"), object_pairs_hook=_objeto_sem_duplicatas,
                           parse_constant=_recusar_constante)
    except (ValueError, RecursionError):
        raise Recusado("JSON ilegível") from None
    if not isinstance(dados, dict) or dados.get("schema_version") != SCHEMA:
        raise Recusado("formato desconhecido")
    return dados


def _acima_do_projeto(raiz: str) -> str:
    """Sem FUNDACAO_RAIZ, a pasta aberta em projects/<p> (ou em projects/) e sem registry/ vale pela pasta de cima de
    projects/, como no guarda_leitura: o comando do lembrete não leva a uma raiz errada (revisão do lote 2)."""
    partes = Path(raiz).parts
    i = max((k for k in range(1, len(partes)) if partes[k].casefold() == "projects"), default=None)
    if i is None or os.path.isdir(os.path.join(raiz, "registry")):
        return raiz
    return str(Path(*partes[:i]))


def proxima_copia(raiz: str | None, anterior: str | None, agora: datetime) -> dict:
    """Comandos da próxima cópia e da verificação, como o `proxima_copia` do kit (sem tocar o disco das cópias)."""
    ano, semana, _ = agora.isocalendar()
    rotulo = f"semanal-{ano}-S{semana:02d}"
    pasta = Path(anterior).parent if anterior else None
    destino = str(pasta / rotulo) if pasta else f"<pasta das cópias, de preferência em outro disco>/{rotulo}"
    aspas, python = (_aspas_powershell, "python") if os.name == "nt" else (_aspas_bash, "python3")
    cli = f"{python} -m fundacao --raiz {aspas(raiz) if raiz else '<pasta da fundação>'} backup"
    return {"rotulo": rotulo, "destino": destino,
            "criar": f"{cli} criar --destino {aspas(destino)} --rotulo {rotulo}",
            "verificar": f"{cli} verificar --origem {aspas(destino)}",
            "antes": ("rode na pasta da fundação, com as sessões dos projetos fechadas (a cópia trava a manutenção "
                      "enquanto roda)" + ("" if pasta else "; troque a pasta das cópias no destino"))}


def aviso(raiz: str | None, agora: datetime) -> str | None:
    """O texto do lembrete; None quando a última cópia registrada está em dia."""
    anterior = None
    try:
        registro = ler_registro(raiz) if raiz else None
        if not raiz:
            situacao = ("a pasta da fundação não foi identificada (FUNDACAO_RAIZ), e o registro da última cópia não "
                        "foi lido")
        elif registro is None:
            situacao = "nenhuma cópia registrada nesta fundação (registry/ultima-copia.json)"
        else:
            criada = _data(registro.get("criada_em"))
            if criada is None or criada > agora + timedelta(days=1):
                raise Recusado("data da cópia ausente, inválida ou no futuro")
            idade = agora - criada
            if idade <= timedelta(days=LIMITE_DIAS):
                return None
            verificada = _data(registro.get("verificada_em"))
            situacao = (f"a última cópia registrada (registry/ultima-copia.json) é de {criada:%d/%m/%Y}, há "
                        f"{idade.days} dias (mais de {LIMITE_DIAS}); "
                        + (f"verificada em {verificada:%d/%m/%Y}" if verificada else "sem verificação registrada"))
            anterior = _pasta_local(registro.get("destino"), raiz)
    except Recusado as exc:
        situacao = f"o registro da última cópia (registry/ultima-copia.json) foi recusado: {exc}"
    except OSError as exc:
        situacao = f"o registro da última cópia (registry/ultima-copia.json) não pôde ser lido ({type(exc).__name__})"
    comandos = proxima_copia(raiz, anterior, agora)
    origem = (" A pasta das cópias no comando veio de registry/ultima-copia.json, que as sessões gravam: confira-a "
              "com o titular antes de rodar." if anterior else "")
    return (f"Lembrete de cópia de segurança: {situacao}. Proponha ao titular a cópia semanal; "
            f"{comandos['antes']}:\n  {comandos['criar']}\nDepois, a conferência:\n  {comandos['verificar']}\n"
            "Este lembrete só lê o registro; não confere a cópia (a prova é o backup verificar). "
            "Para a situação completa: backup situacao." + origem)


def _entrada() -> dict | None:
    """O evento, lido com prazo (a pipe pode não fechar); None se ilegível ou fora do prazo."""
    resultado = []

    def ler():
        try:
            partes, total = [], 0
            while total <= TETO:
                parte = os.read(sys.stdin.fileno(), min(4096, TETO + 1 - total))
                if not parte:
                    break
                partes.append(parte)
                total += len(parte)
            resultado.append(b"".join(partes))
        except (OSError, ValueError):
            resultado.append(None)

    leitor = threading.Thread(target=ler, daemon=True)
    leitor.start()
    leitor.join(PRAZO_ENTRADA)
    if leitor.is_alive() or not resultado or resultado[0] is None or len(resultado[0]) > TETO:
        return None
    try:
        evento = json.loads(resultado[0].decode("utf-8"), object_pairs_hook=_objeto_sem_duplicatas,
                            parse_constant=_recusar_constante)
    except (ValueError, RecursionError):
        return None
    return evento if isinstance(evento, dict) else None


def main() -> int:
    try:
        evento = _entrada()
        if not evento or evento.get("hook_event_name") != "SessionStart" or evento.get("source") not in FONTES:
            return 0
        cwd = evento.get("cwd") if isinstance(evento.get("cwd"), str) else None
        raiz = _texto_limpo(os.environ.get("FUNDACAO_RAIZ") or os.environ.get("CLAUDE_PROJECT_DIR") or cwd
                            or os.getcwd())
        raiz = os.path.abspath(raiz) if raiz else None
        if raiz and not os.environ.get("FUNDACAO_RAIZ"):
            raiz = _acima_do_projeto(raiz)
        try:
            texto = aviso(raiz, datetime.now(timezone.utc))
        except Exception:  # noqa: BLE001 — lembrete nunca bloqueia: erro vira o lembrete genérico
            texto = ("Lembrete de cópia de segurança: não foi possível conferir o registro da última cópia "
                     "(registry/ultima-copia.json). Confira com o comando backup situacao e proponha a cópia semanal "
                     "ao titular, se for o caso.")
        if texto:
            saida = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": texto}}
            # JSON só com ASCII: a saída independe da página de código do console (cp1252 no Windows).
            sys.stdout.write(json.dumps(saida, ensure_ascii=True) + "\n")
            sys.stdout.flush()
    except Exception:  # noqa: BLE001 — nunca bloqueia a sessão
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
