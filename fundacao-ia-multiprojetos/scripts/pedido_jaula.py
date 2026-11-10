#!/usr/bin/env python3
"""Cliente da sessão para a fila da jaula (1.7.11, lote L5; DESENHO-JAULA §2.1 e §7.3): o caminho da SESSÃO até o porteiro
da jaula (`assets/host/wsl/porteiro_jaula.py`), genérico: o navegador (L5) e o Codex (L6) o reusam.

    FUNDACAO_CARGA='{"acao": "sondar"}' python pedido_jaula.py navegador

Sem argumento livre: o único argumento é a operação, de uma tabela fixa (navegador, codex), e a carga (JSON, até 64 KiB)
vai pela variável FUNDACAO_CARGA, nunca pelo argv (legível por todos em /proc). A fila é sempre
`<FUNDACAO_RAIZ>/projects/<FUNDACAO_PROJECT>/.porteiro/jaula` (as duas variáveis vêm do lançador do projeto): nada de
caminho de fila vem de argumento. O pedido é `{"versao": 1, "id": <32 hex>, "op", "carga", "criado_em"}`, gravado em
`pedidos/.<id>.tmp` (criação exclusiva, sem seguir ligação) e renomeado para `pedidos/<id>.json`. A resposta é
`respostas/<id>.json` e só vale se for do formato do porteiro e do MESMO id. Quem decide se o pedido vale é o porteiro
(operação que a ficha não abriu, campo fora da operação, prazo) e, depois dele, a entrada fixa da jaula: este cliente não
valida a carga. A fila, a pasta pedidos/ e a pasta respostas/ não podem ser ligação (ou junção): a resposta de uma fila
trocada não é de quem a sessão pensa. Sem sinal de vida do porteiro (`respostas/porteiro-vivo.json`) ou passado o prazo, o
pedido ainda na fila sai dela, e o erro diz se ele pode ter rodado. Só biblioteca padrão.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
OPERACOES = {"navegador": 160.0, "codex": 960.0}   # o prazo de espera: o da jaula (120 s e 900 s) mais a folga do porteiro
ENV_CARGA = "FUNDACAO_CARGA"
SEM_VIDA_S = 30.0
VIDA = "porteiro-vivo.json"
TETO_PEDIDO = 64 * 1024
TETO_RESPOSTA = 512 * 1024
CAMPOS_RESPOSTA = ("versao", "id", "codigo", "stdout", "stderr", "truncado", "duracao_s")
PROJETO = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?\Z")
_LER = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
_CRIAR = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)


class PedidoRecusado(Exception):
    """O pedido não chegou à jaula, ou a resposta não é confiável: código 2 na linha de comando."""


def _gravacao():
    spec = importlib.util.spec_from_file_location("_pedido_jaula_gravacao", AQUI / "gravacao_segura.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def fila_do_projeto(ambiente=None) -> Path:
    """A fila da jaula do projeto da sessão, só pelo ambiente do lançador; recusa o que passa por ligação."""
    amb = os.environ if ambiente is None else ambiente
    raiz, projeto = (amb.get("FUNDACAO_RAIZ") or "").strip(), (amb.get("FUNDACAO_PROJECT") or "").strip()
    if not raiz or not os.path.isabs(raiz) or not PROJETO.fullmatch(projeto) or "--" in projeto:
        raise PedidoRecusado("sem FUNDACAO_RAIZ e FUNDACAO_PROJECT do lançador do projeto: abra a sessão pelo lançador")
    return Path(raiz) / "projects" / projeto / ".porteiro" / "jaula"


def conferir_fila(fila: Path) -> None:
    """A fila e as duas pastas existem e nenhum componente do caminho a partir da raiz é ligação ou junção."""
    raiz = fila.parents[3]   # <raiz>/projects/<p>/.porteiro/jaula
    rel = fila.relative_to(raiz).as_posix()
    for sub in ("", "/pedidos", "/respostas"):
        if _gravacao().com_ligacao(raiz, rel + sub) or not (raiz / (rel + sub)).is_dir():
            raise PedidoRecusado(f"a fila da jaula ({rel + sub}) não existe ou passa por ligação: abra a sessão pelo lançador "
                                 "do projeto (se o porteiro da jaula não subiu, a ficha não abre a jaula)")


def _ler_json(caminho: Path, teto: int):
    try:
        fd = os.open(caminho, _LER)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise PedidoRecusado(f"resposta da jaula ilegível ({type(exc).__name__}): {caminho.name}") from None
    try:
        dados = bytearray()
        while bloco := os.read(fd, 1 << 16):
            dados += bloco
            if len(dados) > teto:
                raise PedidoRecusado(f"resposta da jaula acima do teto ({teto} bytes)")
    finally:
        os.close(fd)
    try:
        return json.loads(bytes(dados).decode("utf-8"))
    except ValueError:
        return None   # o porteiro grava por troca atômica: incompleto aqui é só uma troca no meio; lê de novo


def _resposta(respostas: Path, ident: str) -> dict | None:
    resposta = _ler_json(respostas / f"{ident}.json", TETO_RESPOSTA)
    if resposta is None:
        return None
    if not (isinstance(resposta, dict) and set(resposta) == set(CAMPOS_RESPOSTA) and resposta["id"] == ident
            and type(resposta["codigo"]) is int and isinstance(resposta["stdout"], str) and isinstance(resposta["stderr"], str)):
        raise PedidoRecusado("resposta da jaula fora do formato, ou de outro pedido: descartada")
    return resposta


def _vivo(respostas: Path) -> bool:
    try:
        renovada = datetime.fromisoformat(str(_ler_json(respostas / VIDA, 4096)["renovada_em"]).replace("Z", "+00:00"))
    except (PedidoRecusado, TypeError, KeyError, ValueError):
        return False
    return (datetime.now(timezone.utc) - renovada).total_seconds() < SEM_VIDA_S


def _retirar(caminho: Path) -> str:
    try:
        os.unlink(caminho)
    except FileNotFoundError:
        return "tomado"
    except OSError:
        return "preso"
    return "retirado"


def _desistir(situacao: str, motivo: str) -> PedidoRecusado:
    if situacao == "retirado":
        return PedidoRecusado(f"{motivo}; o pedido saiu da fila sem ser atendido (não rodou): pode repetir")
    return PedidoRecusado(f"{motivo}; o porteiro já tinha tirado o pedido da fila e ele pode ter rodado: confira o efeito "
                          "(a pasta de saída da jaula, em outputs/) antes de repetir")


def pedir(op: str, carga: dict, *, fila=None, prazo: float | None = None, intervalo: float = 0.05, ambiente=None,
          relogio=time.monotonic, dormir=time.sleep) -> dict:
    """Grava o pedido, espera a resposta e a devolve (campos do porteiro: codigo, stdout, stderr, ...)."""
    if op not in OPERACOES:
        raise PedidoRecusado(f"operação desconhecida: a sessão pede só {', '.join(OPERACOES)}")
    if not isinstance(carga, dict):
        raise PedidoRecusado("a carga é um objeto JSON")
    fila = Path(fila) if fila is not None else fila_do_projeto(ambiente)
    conferir_fila(fila)
    pedidos, respostas = fila / "pedidos", fila / "respostas"
    ident = secrets.token_hex(16)
    try:
        dados = json.dumps({"versao": 1, "id": ident, "op": op, "carga": carga, "criado_em":
                            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")}, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise PedidoRecusado("a carga não é JSON em UTF-8") from None
    if len(dados) > TETO_PEDIDO:
        raise PedidoRecusado(f"pedido acima de {TETO_PEDIDO} bytes: encurte a carga")
    temporario, final, prazo = pedidos / f".{ident}.tmp", pedidos / f"{ident}.json", prazo or OPERACOES[op]
    situacao = None
    try:
        try:
            fd = os.open(temporario, _CRIAR, 0o600)
            try:
                vista = memoryview(dados)
                while vista:
                    vista = vista[os.write(fd, vista):]
            finally:
                os.close(fd)
            os.rename(temporario, final)
        except OSError as exc:
            _retirar(temporario)
            raise PedidoRecusado(f"a fila da jaula não aceitou o pedido ({type(exc).__name__}: {exc})") from None
        inicio, espera = relogio(), intervalo
        while True:
            conferir_fila(fila)   # a fila trocada por ligação no meio da espera não entrega resposta
            if (resposta := _resposta(respostas, ident)) is not None:
                return resposta
            decorrido = relogio() - inicio
            if decorrido >= prazo:
                motivo = f"a jaula não respondeu em {prazo:.0f} s"
            elif decorrido >= SEM_VIDA_S and not _vivo(respostas):
                motivo = f"o porteiro da jaula não dá sinal de vida há mais de {SEM_VIDA_S:.0f} s (feche a sessão e reabra pelo lançador)"
            else:
                dormir(espera)
                espera = min(espera * 1.5, 0.25)
                continue
            situacao = _retirar(final)
            if situacao == "tomado" and (resposta := _resposta(respostas, ident)) is not None:
                return resposta
            raise _desistir(situacao, motivo)
    except KeyboardInterrupt:
        raise _desistir(situacao or _retirar(final), "o comando foi interrompido") from None


def main(argv: list[str] | None = None, ambiente=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    amb = os.environ if ambiente is None else ambiente
    try:
        if len(argv) != 1 or argv[0] not in OPERACOES:
            raise PedidoRecusado(f"uso: {ENV_CARGA}='<json>' pedido_jaula.py {{{'|'.join(OPERACOES)}}} (sem outro argumento)")
        try:
            carga = json.loads(amb.get(ENV_CARGA) or "{}")
        except ValueError:
            raise PedidoRecusado(f"{ENV_CARGA} não é JSON") from None
        resposta = pedir(argv[0], carga, ambiente=amb)
    except PedidoRecusado as exc:
        sys.stderr.write(json.dumps({"error": {"code": "E_PEDIDO_JAULA", "message": str(exc)}}, ensure_ascii=False) + "\n")
        return 2
    sys.stdout.write(resposta["stdout"])
    sys.stderr.write(resposta["stderr"])
    return resposta["codigo"]


if __name__ == "__main__":
    raise SystemExit(main())
