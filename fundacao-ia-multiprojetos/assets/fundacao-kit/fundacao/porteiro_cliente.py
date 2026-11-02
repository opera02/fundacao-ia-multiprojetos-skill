"""Cliente do porteiro na sessão de projeto do Ubuntu (1.7.10; contratos do lote 2, §2 e §4; desenho 1.7.10, §2).

Com FUNDACAO_PORTEIRO no ambiente (a pasta da fila, exportada pelo lançador do projeto) e sem
FUNDACAO_PORTEIRO_SERVIDOR=1 (o kit rodado DENTRO do porteiro), `python -m fundacao ...` não abre o banco: vira um
pedido à fila e espera a resposta do porteiro, que roda o kit fora do sandbox, preso ao projeto do lançador
(FUNDACAO_PROJETO_TRAVADO) e com a identidade `sessao-<p>`. Para a sessão é transparente: o mesmo stdout, o mesmo
stderr e o mesmo código de saída.
- Pedido {"versao": 1, "id": "<32 hex>", "op": "fundacao", "argv": [...], "criado_em": "<ISO UTC>"}: gravado em
  `pedidos/.<id>.tmp` (criação exclusiva, sem seguir ligação) e renomeado para `pedidos/<id>.json`.
- Resposta `respostas/<id>.json`, esperada até FUNDACAO_PORTEIRO_PRAZO segundos (padrão 900). Sem sinal de vida do
  porteiro (`respostas/porteiro-vivo.json`, renovado por ele, também enquanto espera a vez do banco) há mais de
  SEM_VIDA_S segundos, o cliente desiste antes, com o motivo e o que fazer (crítica do desenho: "sinal de vida para
  falhar em segundos"). Ao desistir, diz se o pedido ainda estava na fila (não rodou: repetir é seguro) ou se o
  porteiro já o tinha tirado (pode ter rodado: conferir antes de repetir, senão sai em dobro; revisão do lote 2) — e,
  neste caso, lê a resposta mais uma vez, porque ela pode ter chegado entre a última leitura e a retirada.
- Interrompido (Ctrl+C, ou SIGTERM e SIGHUP enquanto o desvio espera), o cliente tira da fila o pedido ainda não
  atendido e diz se ele rodou, em vez de morrer calado e deixar o pedido rodar depois sem ninguém ler a resposta; o
  porteiro também não roda pedido mais velho que a idade máxima dele (revisão do lote 2).
- Desvia só quando o alvo é a raiz real: sem --raiz, ou com --raiz da mesma pasta de FUNDACAO_RAIZ (tirado do pedido:
  o porteiro põe a raiz da configuração dele). Com --raiz de outra pasta — uma fundação de ensaio, como nas suítes do
  kit —, roda aqui, como antes (crítica do desenho, "cliente do kit dentro da sessão"). Sem FUNDACAO_RAIZ (lançador
  incompleto), não se sabe qual é a raiz real: desvia sempre, e o porteiro recusa o --raiz (o lado seguro).
- Caminho relativo das opções de arquivo (OPCOES_DE_CAMINHO) vai absoluto, pela pasta atual da sessão; o porteiro só
  aceita caminho dentro de projects/<p>/. Opção abreviada não passa no porteiro (pedido tipado, sem abreviação).
Honestidade (§0 dos contratos): com a raiz em /mnt/e, onde o sandbox do Claude Code não confinou os comandos nas
sondas de 31/10/2026, a fila e a trava de projeto são camadas lógicas — um comando da sessão ainda alcança o banco e os
outros projetos por fora delas — até o canário passar no ambiente real. Só biblioteca padrão; nada de banco aqui.
"""

from __future__ import annotations

import json
import os
import secrets
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ENV_FILA = "FUNDACAO_PORTEIRO"
ENV_SERVIDOR = "FUNDACAO_PORTEIRO_SERVIDOR"
ENV_PRAZO = "FUNDACAO_PORTEIRO_PRAZO"
ENV_RAIZ = "FUNDACAO_RAIZ"
PRAZO_PADRAO = 900.0
SEM_VIDA_S = 30.0
VIDA = "porteiro-vivo.json"   # em respostas/, gravado só pelo porteiro
TETO_PEDIDO = 64 * 1024       # o mesmo teto do porteiro
TETO_RESPOSTA = 40 * 1024 * 1024  # as saídas do kit até o teto do porteiro (5 MiB), mesmo com o escape do JSON
# As opções de caminho do mapa do porteiro (há teste). --destino saiu com `eventos` (emenda E2 dos contratos, 1.7.10).
OPCOES_DE_CAMINHO = ("--arquivo", "--decisao", "--rascunho")
CAMPOS_RESPOSTA = ("versao", "id", "codigo", "stdout", "stderr", "truncado", "duracao_s")
SINAIS_DE_TERMINO = tuple(getattr(signal, nome) for nome in ("SIGTERM", "SIGHUP") if hasattr(signal, nome))
_CRIAR = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
_LER = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)


class PorteiroIndisponivel(Exception):
    """A fila não aceitou o pedido ou o porteiro não respondeu: sai como erro da CLI (JSON no stderr, código 2)."""


def ativo(ambiente=None) -> bool:
    amb = os.environ if ambiente is None else ambiente
    return bool(amb.get(ENV_FILA, "").strip()) and amb.get(ENV_SERVIDOR, "") != "1"


def _mesma_pasta(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:  # uma das duas não existe: compara os nomes normalizados
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def preparar_argv(argv: list[str], ambiente=None, pasta_atual=None) -> list[str] | None:
    """O argv do pedido, ou None quando o comando roda aqui (--raiz de outra pasta que não a raiz real, com
    FUNDACAO_RAIZ presente). Só o --raiz escrito por extenso e antes do subcomando conta como raiz (é onde a CLI o
    aceita). Sem FUNDACAO_RAIZ, o argv inteiro vai ao porteiro, que recusa o --raiz (revisão do lote 2)."""
    amb = os.environ if ambiente is None else ambiente
    atual = str(pasta_atual or os.getcwd())
    raiz_real = amb.get(ENV_RAIZ, "").strip()
    saida, i, antes_do_subcomando = [], 0, True
    while i < len(argv):
        ficha = argv[i]
        nome, igual, valor = ficha.partition("=")
        if antes_do_subcomando and nome == "--raiz":
            if not igual:
                if i + 1 >= len(argv):
                    return list(argv)  # --raiz sem valor: o porteiro responde com o erro de sempre
                valor, i = argv[i + 1], i + 1
            if not raiz_real:  # não se sabe qual é a raiz real: rodar aqui abriria o banco dela direto
                return list(argv)
            if not _mesma_pasta(os.path.join(atual, valor), raiz_real):
                return None
            i += 1
            continue
        if nome in OPCOES_DE_CAMINHO and not antes_do_subcomando and (
                igual or (i + 1 < len(argv) and not argv[i + 1].startswith("-"))):
            if not igual:
                valor, i = argv[i + 1], i + 1
            saida.append(f"{nome}={os.path.abspath(os.path.join(atual, valor))}")
            i += 1
            continue
        if not ficha.startswith("-"):
            antes_do_subcomando = False
        saida.append(ficha)
        i += 1
    return saida


def _agora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _ler_json(caminho: Path, teto: int):
    """JSON do arquivo, sem seguir ligação, com teto; None se não existe ou ainda está incompleto."""
    try:
        fd = os.open(caminho, _LER)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise PorteiroIndisponivel(f"resposta do porteiro ilegível ({type(exc).__name__}): {caminho.name}") from None
    try:
        dados = bytearray()
        while bloco := os.read(fd, 1 << 20):
            dados += bloco
            if len(dados) > teto:
                raise PorteiroIndisponivel(f"resposta do porteiro acima do teto ({teto} bytes)")
    finally:
        os.close(fd)
    try:
        return json.loads(bytes(dados).decode("utf-8"))
    except ValueError:
        return None  # o porteiro grava por troca atômica; incompleto aqui só por troca no meio: lê de novo


def vivo(respostas: Path, sem_vida: float = SEM_VIDA_S) -> bool:
    """O porteiro renovou o sinal de vida há menos de `sem_vida` segundos."""
    try:
        vida = _ler_json(respostas / VIDA, 4096)
        renovada = datetime.fromisoformat(str(vida["renovada_em"]).replace("Z", "+00:00"))
    except (PorteiroIndisponivel, TypeError, KeyError, ValueError):
        return False
    return (datetime.now(timezone.utc) - renovada).total_seconds() < sem_vida


def _retirar(caminho: Path) -> str:
    """Tira o pedido da fila: "retirado" (o porteiro não o viu), "tomado" (o porteiro já o tinha tirado) ou "preso"
    (não saiu: o porteiro ainda pode atendê-lo)."""
    try:
        os.unlink(caminho)
    except FileNotFoundError:
        return "tomado"
    except OSError:
        return "preso"
    return "retirado"


def _desistencia(situacao: str, motivo: str, repetir: str) -> PorteiroIndisponivel:
    """O erro de quem desiste de esperar, com o que fazer conforme o pedido estava (revisão do lote 2: repetir um
    pedido que o porteiro já tinha tirado da fila pode criar em dobro a tarefa, a lição ou a decisão)."""
    if situacao == "retirado":
        return PorteiroIndisponivel(f"{motivo}; o pedido saiu da fila sem ser atendido (não rodou): {repetir}")
    estado = ("o porteiro já tinha tirado o pedido da fila, e ele pode ter rodado (ou ainda rodar)"
              if situacao == "tomado" else "o pedido não saiu da fila, e o porteiro ainda pode atendê-lo")
    return PorteiroIndisponivel(f"{motivo}; {estado}: confira o efeito (por exemplo, com `tarefa ver` ou `status`) "
                                f"antes de repetir; {repetir}")


def _resposta(respostas: Path, ident: str) -> dict | None:
    """A resposta conferida do pedido `ident`; None enquanto ela não chegou."""
    resposta = _ler_json(respostas / f"{ident}.json", TETO_RESPOSTA)
    if resposta is None:
        return None
    if not (isinstance(resposta, dict) and set(resposta) == set(CAMPOS_RESPOSTA) and resposta["id"] == ident
            and type(resposta["codigo"]) is int and isinstance(resposta["stdout"], str)
            and isinstance(resposta["stderr"], str)):
        raise PorteiroIndisponivel("resposta do porteiro fora do formato")
    return resposta


def _gravar_pedido(temporario: Path, pedido: Path, dados: bytes) -> None:
    """O temporário exclusivo, sem seguir ligação, renomeado para o nome que o porteiro lê."""
    try:
        fd = os.open(temporario, _CRIAR, 0o600)
        try:
            vista = memoryview(dados)
            while vista:
                vista = vista[os.write(fd, vista):]
        finally:
            os.close(fd)
        os.rename(temporario, pedido)
    except OSError as exc:
        _retirar(temporario)
        raise PorteiroIndisponivel(f"a fila do porteiro não aceitou o pedido ({type(exc).__name__}: {exc})") from None


def pedir(fila, argv: list[str], *, prazo: float = PRAZO_PADRAO, sem_vida: float = SEM_VIDA_S,
          intervalo: float = 0.05, relogio=time.monotonic, dormir=time.sleep) -> dict:
    """Grava o pedido na fila e espera a resposta (relógio e espera injetáveis nos testes). Devolve a resposta
    conferida; falha: PorteiroIndisponivel, e o pedido ainda não atendido sai da fila — também na interrupção
    (KeyboardInterrupt: Ctrl+C, ou SIGTERM e SIGHUP pelo desvio), em vez de ficar para rodar sem ninguém que leia a
    resposta (revisão do lote 2)."""
    fila = Path(fila)
    pedidos, respostas = fila / "pedidos", fila / "respostas"
    if not pedidos.is_dir() or not respostas.is_dir():
        raise PorteiroIndisponivel(f"a fila do porteiro não existe ({fila}): abra a sessão pelo lançador do projeto")
    ident = secrets.token_hex(16)
    try:  # no Linux, o argv traz bytes fora do UTF-8 como substitutos soltos: erro da CLI, não traceback
        dados = json.dumps({"versao": 1, "id": ident, "op": "fundacao", "argv": list(argv),
                            "criado_em": _agora_iso()}, ensure_ascii=False).encode("utf-8")
    except UnicodeEncodeError:
        raise PorteiroIndisponivel("argumento com texto fora do UTF-8: o porteiro só aceita texto em UTF-8") from None
    if len(dados) > TETO_PEDIDO:
        raise PorteiroIndisponivel(f"pedido acima de {TETO_PEDIDO} bytes: encurte os textos do comando")
    temporario, pedido = pedidos / f".{ident}.tmp", pedidos / f"{ident}.json"
    situacao = None
    try:
        _gravar_pedido(temporario, pedido, dados)
        inicio, espera = relogio(), intervalo
        while (resposta := _resposta(respostas, ident)) is None:
            decorrido = relogio() - inicio
            if decorrido >= prazo:
                motivo = f"o porteiro não respondeu em {prazo:.0f} s ({ENV_PRAZO})"
                repetir = "se o lançador ainda está aberto, repita; senão, reabra a sessão por ele"
            elif decorrido >= sem_vida and not vivo(respostas, sem_vida):
                motivo = f"o porteiro não dá sinal de vida há mais de {sem_vida:.0f} s"
                repetir = "feche a sessão e reabra pelo lançador do projeto"
            else:
                dormir(espera)
                espera = min(espera * 1.5, 0.25)
                continue
            situacao = _retirar(pedido)
            if situacao == "tomado" and (resposta := _resposta(respostas, ident)) is not None:
                return resposta  # chegou entre a última leitura e a retirada (revisão do lote 2)
            raise _desistencia(situacao, motivo, repetir)
        return resposta
    except KeyboardInterrupt:
        if _retirar(temporario) == "retirado":  # interrompido antes do nome final: nem chegou à fila
            situacao = "retirado"
        raise _desistencia(situacao or _retirar(pedido), "o comando foi interrompido",
                           "só repita se ainda precisar") from None


def _interromper(_sinal, _quadro):
    raise KeyboardInterrupt


def _interromper_nos_sinais() -> dict:
    """SIGTERM e SIGHUP viram KeyboardInterrupt enquanto o desvio espera, para o pedido ainda na fila sair dela
    (revisão do lote 2). Só os que estão no padrão (nunca troca um sinal ignorado de propósito, como o do nohup) e só
    na thread principal (fora dela, o signal recusa). Devolve os tratadores trocados, para voltar no fim."""
    trocados = {}
    for sinal in SINAIS_DE_TERMINO:
        try:
            if signal.getsignal(sinal) == signal.SIG_DFL:
                trocados[sinal] = signal.signal(sinal, _interromper)
        except (ValueError, OSError):
            pass
    return trocados


def _voltar_sinais(trocados: dict) -> None:
    for sinal, tratador in trocados.items():
        try:
            signal.signal(sinal, tratador)
        except (ValueError, OSError):
            pass


def _prazo(ambiente=None) -> float:
    amb = os.environ if ambiente is None else ambiente
    try:
        valor = float(amb.get(ENV_PRAZO, "") or PRAZO_PADRAO)
    except ValueError:
        return PRAZO_PADRAO
    return valor if 0 < valor <= 86400 else PRAZO_PADRAO


def desviar(argv: list[str] | None = None) -> int | None:
    """Para `__main__.main`: None quando o comando roda aqui; senão, o código do pedido atendido pelo porteiro, com o
    stdout e o stderr dele já escritos."""
    if not ativo():
        return None
    argv = list(sys.argv[1:] if argv is None else argv)
    pedido = preparar_argv(argv)
    if pedido is None:
        return None
    trocados = _interromper_nos_sinais()
    try:
        resposta = pedir(os.environ[ENV_FILA].strip(), pedido, prazo=_prazo())
    except PorteiroIndisponivel as exc:
        sys.stderr.write(json.dumps({"error": {"code": "E_PORTEIRO", "message": str(exc)}}, ensure_ascii=False) + "\n")
        return 2
    finally:
        _voltar_sinais(trocados)
    sys.stdout.write(resposta["stdout"])
    sys.stderr.write(resposta["stderr"])
    sys.stdout.flush()
    return resposta["codigo"]
