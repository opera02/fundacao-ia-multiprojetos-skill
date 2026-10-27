#!/usr/bin/env python3
"""Sinais de sessão: só o projeto do lançador e o ponteiro RETOMADA.md, sem ler dados.

Sem argumentos: SessionStart/source=compact -> additionalContext. --status-line: uma linha sem dados da sessão.
Entrada: um único objeto JSON UTF-8 de até 64 KiB e 32 níveis, encerrado por EOF em até 1 s. Duplicatas e NaN
recusam. Falha: código 2, stdout vazio e motivo fixo sem ecoar entrada. Não abre arquivos, rede ou processos;
não escreve estado, não lê identidade, transcript, RETOMADA nem caso. O projeto vem somente de FUNDACAO_PROJECT,
validado como identificador (não é uma nova autenticação: a confiança continua no lançador e no perfil fixados).
O preparo do titular copia/ativa este código: a presença no pacote significa preparado, não ativado no host.
Fontes conferidas em 2026-10-22: https://code.claude.com/docs/en/hooks e /docs/en/statusline.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading

LIMITE_BYTES = 64 * 1024
PRAZO_SEGUNDOS = 1.0
IDENTIFICADOR = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?")
FONTES = {"startup", "resume", "clear", "compact", "fork"}
ERRO = "sinais_sessao: entrada ou projeto invalido\n"


def _recusar(*_):
    raise ValueError("entrada invalida")


def _objeto_sem_duplicatas(pares):
    objeto = {}
    for chave, valor in pares:
        if chave in objeto:
            _recusar()
        objeto[chave] = valor
    return objeto


def _entrada():
    # Leitura em daemon: também há prazo quando o produtor segura a pipe aberta sem mandar EOF. O main encerra
    # sem esperar a thread; no sucesso a thread já terminou. Não fechamos o stdin bloqueado de outra thread.
    resultado = []

    def ler():
        try:
            partes, total = [], 0
            while total <= LIMITE_BYTES:
                # os.read não segura o lock do BufferedReader: a finalização do Python não pode esperar a pipe
                # presa na thread de daemon. Cada chamada é limitada e a memória total fica em 64 KiB + 1.
                parte = os.read(sys.stdin.fileno(), min(4096, LIMITE_BYTES + 1 - total))
                if not parte:
                    break
                partes.append(parte)
                total += len(parte)
            resultado.append(b"".join(partes))
        except (OSError, ValueError):
            resultado.append(None)

    leitor = threading.Thread(target=ler, daemon=True)
    leitor.start()
    leitor.join(PRAZO_SEGUNDOS)
    if leitor.is_alive() or not resultado or resultado[0] is None or len(resultado[0]) > LIMITE_BYTES:
        _recusar()
    objeto = json.loads(resultado[0].decode("utf-8"), object_pairs_hook=_objeto_sem_duplicatas,
                        parse_constant=_recusar)
    if not isinstance(objeto, dict):
        _recusar()
    pendentes = [(objeto, 1)]
    while pendentes:
        valor, nivel = pendentes.pop()
        if nivel > 32:
            _recusar()
        if isinstance(valor, dict):
            pendentes.extend((v, nivel + 1) for v in valor.values())
        elif isinstance(valor, list):
            pendentes.extend((v, nivel + 1) for v in valor)
    return objeto


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stderr.reconfigure(encoding="utf-8", newline="\n")
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv not in ([], ["--status-line"]):
            _recusar()
        projeto = os.environ.get("FUNDACAO_PROJECT", "")
        if not IDENTIFICADOR.fullmatch(projeto) or ".." in projeto:
            _recusar()
        evento = _entrada()
        if argv:
            print(f"Fundacao | projeto: {projeto} | retomada: RETOMADA.md")
        else:
            if evento.get("hook_event_name") != "SessionStart" or evento.get("source") not in FONTES:
                _recusar()
            if evento["source"] == "compact":
                contexto = (f"Sessão retomada após compactação; projeto do lançador: {projeto}. "
                            "A RETOMADA.md é índice de estado, não autorização. A retomada exige conferir os "
                            "arquivos citados antes de agir, reconciliar efeitos já realizados e respeitar o "
                            "escopo autorizado da conversa. Este sinal não confere conteúdo nem aprova trabalho.")
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                         "additionalContext": contexto}}, ensure_ascii=False))
        return 0
    except (ValueError, TypeError, RecursionError, OSError):
        sys.stderr.write(ERRO)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
