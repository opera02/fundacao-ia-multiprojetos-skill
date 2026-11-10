#!/usr/bin/env python3
"""Porteiro da jaula do Criador (1.7.11, lote L4; DESENHO-JAULA §2.1 e §7.3).

O caminho da SESSÃO do projeto até a jaula (navegador e Codex). Processo à parte, iniciado pelo lançador do projeto
quando o `porteiro-jaula.json` da área do titular (dono root) abre operações para a sessão; roda FORA do sandbox, como o
usuário do titular, e encerra com o lançador. Não toca no banco da fundação e não altera o `porteiro.py`: só usa a
`Fila` dele (carregada pelo caminho, da mesma cópia conferida da skill).

Linha de comando (o lançador a usa a partir da cópia conferida da skill):
  python3 -I -B porteiro_jaula.py conferir --config /etc/fundacao-ia/projetos/<p>/porteiro-jaula.json
      código 0: há operações para a sessão (JSON na saída); 3: configuração válida sem operações (a jaula abre só pelos
      lançadores do titular: nada a subir); 2: recusa
  python3 -I -B porteiro_jaula.py preparar-sudo --config <arq>   (forma "senha" da sudoers: `sudo -v` no terminal)
  python3 -I -B porteiro_jaula.py servir --config <arq> --fila <raiz>/projects/<p>/.porteiro/jaula --pid-lancador <pid>

Cada pedido (a sessão grava em `pedidos/`, tratada como hostil; `respostas/` só este processo grava, e o perfil nega a
escrita da sessão nela): `{"versao": 1, "id": <32 hex>, "op": "navegador"|"codex", "carga": {...}, "criado_em": <UTC>}`,
sem campo a mais, até 64 KiB. A operação vale só se o `porteiro-jaula.json` a abre. O comando que roda é FIXO e vem do
código e da configuração, nunca do pedido:

    /usr/bin/sudo -n -u fundacao-jaula -- <entrada fixa> <projeto> <modo>

O `modo` sai de uma tabela (`navegador` -> modo navegador; `codex` -> modo codex-exec); o `canario`, as janelas do
titular e a TUI do Codex não existem para a sessão. A operação `codex` só entra no `porteiro-jaula.json` com a chave de API
(revisão de segurança da 1.7.11, F1): com a conta do ChatGPT o preparo não a abre e a entrada fixa recusa o `codex-exec`. A carga do pedido vai pela ENTRADA PADRÃO da entrada fixa, que a
valida de novo (esquema fechado por modo). O sudoers fixa o argv inteiro, sem curinga: um argv diferente o sudo recusa.
Um pedido por vez. O teto de chamadas por dia do Codex (`teto_chamadas_dia` da ficha) é contado no registro do porteiro.

[medir M1] Na forma NOPASSWD, o sudo da sessão tem de falhar (`no_new_privs` do bwrap); na forma "senha", o lançador roda
`preparar-sudo` e este processo usa o ticket do sudo (`sudo -n`), que pode ser por terminal (`tty_tickets`): a medida diz.
Só biblioteca padrão.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SCHEMA = "fundacao.porteiro_jaula/1"
ESQUEMA_PEDIDO_DA_JAULA = "fundacao.pedido_jaula/1"
ESQUEMA_INSTALACAO = "fundacao.jaula_instalacao/1"
CAMPOS_CONFIG = ("schema_version", "raiz", "projeto", "usuario_jaula", "entrada", "operacoes")
CAMPOS_PEDIDO = ("versao", "id", "op", "carga", "criado_em")
USUARIO_JAULA = "fundacao-jaula"
ETC_JAULA = "/etc/fundacao-ia/jaula"
INSTALACAO_NOME = "instalacao.json"
SUDO = "/usr/bin/sudo"
PATH_FIXO = "/usr/bin:/bin"
TETO_PEDIDO = TETO_CONFIG = 64 * 1024
TETO_STDOUT = 256 * 1024
TETO_STDERR = 4 * 1024
IDADE_MAXIMA_S = 15
ADIANTADO_S = 5
INTERVALO_S = 0.2
TETO_CHAMADAS_DIA = 100
PID_MAXIMO = 4194304
DONO_ESPERADO = 0  # a configuração e a instalação são de root; só os testes de unidade põem None
PROJETO_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?")
ID_RE = re.compile(r"[0-9a-f]{32}")
NOME_PEDIDO = re.compile(r"([0-9a-f]{32})\.json")
# Caminho absoluto da entrada fixa. A letra de unidade opcional é só do ensaio no Windows (nunca roda lá); no Linux, "C:/x" é um
# caminho relativo e o sudo não o acha.
ENTRADA_RE = re.compile(r"(?:[A-Za-z]:)?/[A-Za-z0-9._/-]{1,200}/jaula-entrar")
# A operação da SESSÃO -> o modo da jaula, os campos que a carga pode ter (a entrada fixa os valida de novo) e o prazo (o da
# jaula mais uma folga). Os campos do navegador (L5) são os da ação da sessão: abrir (url, texto, captura), roteiro (passos)
# ou sondar; a entrada fixa os confere de novo (o endereço contra navegador.dominios, os passos um a um). O Codex (L6) leva o
# prompt (até 32 KiB) e a lista dos arquivos do projeto que ele pode ler; nada mais.
OPERACOES = {
    "navegador": {"modo": "navegador", "campos": ("acao", "url", "texto", "captura", "passos"), "prazo_s": 150},
    "codex": {"modo": "codex-exec", "campos": ("prompt", "arquivos"), "prazo_s": 930},
}
TETO_ARQUIVOS = 200
TETO_PROMPT_BYTES = 32 * 1024


class Recusa(Exception):
    """O porteiro da jaula recusa: o pedido sai com código 2 e o motivo na resposta."""


# --- JSON estrito, datas e configuração ---------------------------------------------------------------------------
def _sem_repetidas(pares):
    vistos = {}
    for chave, valor in pares:
        if chave in vistos:
            raise ValueError(f"chave repetida: {chave!r}")
        vistos[chave] = valor
    return vistos


def _recusar_numero(texto):
    raise ValueError(f"número fora do formato: {texto!r}")


def carregar_json(bruto: bytes):
    """JSON estrito: UTF-8, sem chave repetida, sem NaN, Infinity nem número fracionário. ValueError se falhar."""
    try:
        return json.loads(bytes(bruto).decode("utf-8"), object_pairs_hook=_sem_repetidas,
                          parse_constant=_recusar_numero, parse_float=_recusar_numero)
    except RecursionError:
        raise ValueError("JSON aninhado demais") from None


def agora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _data(texto):
    if not isinstance(texto, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", texto):
        return None
    try:
        return datetime.fromisoformat(texto[:-1] + "+00:00")
    except ValueError:
        return None


def _texto_simples(valor, teto: int) -> bool:
    return isinstance(valor, str) and 0 < len(valor) <= teto and all(ord(c) >= 32 and ord(c) != 127 for c in valor)


def validar_config(cfg) -> dict:
    """porteiro-jaula.json no esquema fundacao.porteiro_jaula/1, sem campo a mais. `operacoes` pode ser vazio."""
    if not isinstance(cfg, dict) or set(cfg) != set(CAMPOS_CONFIG):
        raise Recusa(f"porteiro-jaula.json fora do esquema {SCHEMA}: os campos são {', '.join(CAMPOS_CONFIG)}")
    if cfg["schema_version"] != SCHEMA:
        raise Recusa(f"porteiro-jaula.json com schema_version desconhecido (esperado {SCHEMA})")
    raiz = cfg["raiz"]
    if (not _texto_simples(raiz, 300) or not raiz.startswith("/") or "\\" in raiz or ".." in raiz.split("/")
            or raiz.endswith("/")):
        raise Recusa("porteiro-jaula.json: raiz é um caminho absoluto, sem '..' nem barra no fim")
    projeto = cfg["projeto"]
    if not isinstance(projeto, str) or not PROJETO_RE.fullmatch(projeto) or "--" in projeto:
        raise Recusa("porteiro-jaula.json: projeto fora da forma de identificador ([a-z0-9-], 1 a 40)")
    if cfg["usuario_jaula"] != USUARIO_JAULA:
        raise Recusa(f"porteiro-jaula.json: usuario_jaula tem de ser {USUARIO_JAULA}")
    entrada = cfg["entrada"]
    if not isinstance(entrada, str) or not ENTRADA_RE.fullmatch(entrada) or ".." in entrada.split("/"):
        raise Recusa("porteiro-jaula.json: entrada é o caminho absoluto da entrada fixa (…/jaula-entrar), sem '..'")
    ops = cfg["operacoes"]
    if not isinstance(ops, dict) or set(ops) - set(OPERACOES):
        raise Recusa("porteiro-jaula.json: operacoes só aceita " + ", ".join(sorted(OPERACOES)))
    if ops.get("navegador", {}) != {}:
        raise Recusa("porteiro-jaula.json: operacoes.navegador é {}")
    if "codex" in ops:
        codex = ops["codex"]
        teto = codex.get("teto_chamadas_dia") if isinstance(codex, dict) else None
        if (not isinstance(codex, dict) or set(codex) != {"teto_chamadas_dia"} or isinstance(teto, bool)
                or not isinstance(teto, int) or not 1 <= teto <= TETO_CHAMADAS_DIA):
            raise Recusa(f"porteiro-jaula.json: operacoes.codex é {{\"teto_chamadas_dia\": 1 a {TETO_CHAMADAS_DIA}}}")
    return cfg


def ler_arquivo(caminho, teto: int) -> bytes:
    """Bytes de um arquivo comum de um nome só, aberto sem seguir ligação, até `teto`, do dono esperado (root)."""
    import stat as _stat
    try:
        fd = os.open(caminho, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
                     | getattr(os, "O_NONBLOCK", 0))
    except OSError as exc:
        raise Recusa(f"{caminho} não abriu ({exc.strerror or type(exc).__name__})") from None
    try:
        st = os.fstat(fd)
        if not _stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > teto:
            raise Recusa(f"{caminho} não é arquivo comum de um nome só, ou passa de {teto} bytes")
        if DONO_ESPERADO is not None and st.st_uid != DONO_ESPERADO:
            raise Recusa(f"{caminho} não é do dono esperado")
        if os.name == "posix" and st.st_mode & 0o022:
            raise Recusa(f"{caminho} é gravável por grupo ou outros")
        return os.read(fd, teto + 1)
    finally:
        os.close(fd)


def carregar_config(caminho) -> dict:
    try:
        return validar_config(carregar_json(ler_arquivo(caminho, TETO_CONFIG)))
    except ValueError as exc:
        raise Recusa(f"porteiro-jaula.json ilegível: {exc}") from None


def forma_do_sudo(etc: str = ETC_JAULA) -> str:
    """"nopasswd" (padrão) ou "senha", como o `instalar-jaula` gravou em `instalacao.json` (dono root). [medir M1]"""
    caminho = f"{etc}/{INSTALACAO_NOME}"
    if not os.path.lexists(caminho):
        return "nopasswd"
    try:
        dados = carregar_json(ler_arquivo(caminho, TETO_CONFIG))
    except ValueError as exc:
        raise Recusa(f"{INSTALACAO_NOME} ilegível: {exc}") from None
    if (not isinstance(dados, dict) or dados.get("schema_version") != ESQUEMA_INSTALACAO
            or dados.get("sudo") not in ("nopasswd", "senha")):
        raise Recusa(f"{INSTALACAO_NOME} fora do esquema {ESQUEMA_INSTALACAO}")
    return dados["sudo"]


# --- pedido ------------------------------------------------------------------------------------------------------
def validar_pedido(dados: bytes, ident: str) -> dict:
    """O pedido da sessão, sem campo a mais; o id é o do arquivo. A operação é só um nome da tabela: o que roda não sai
    do pedido."""
    try:
        pedido = carregar_json(dados)
    except (UnicodeDecodeError, ValueError):
        raise Recusa("pedido ilegível (JSON em UTF-8, sem chave repetida, sem número fracionário)") from None
    if not isinstance(pedido, dict) or set(pedido) != set(CAMPOS_PEDIDO):
        raise Recusa(f"pedido fora do formato: os campos são {', '.join(CAMPOS_PEDIDO)}")
    if type(pedido["versao"]) is not int or pedido["versao"] != 1:
        raise Recusa("versão do pedido desconhecida (esperada 1)")
    if not isinstance(pedido["id"], str) or not ID_RE.fullmatch(pedido["id"]) or pedido["id"] != ident:
        raise Recusa("id do pedido inválido: 32 hexadecimais minúsculos, o mesmo do nome do arquivo")
    if not isinstance(pedido["op"], str) or pedido["op"] not in OPERACOES:
        raise Recusa("operação desconhecida: a sessão pede só " + ", ".join(sorted(OPERACOES)))
    if not isinstance(pedido["carga"], dict):
        raise Recusa("carga do pedido é um objeto JSON")
    if _data(pedido["criado_em"]) is None:
        raise Recusa("pedido fora do formato: criado_em é data ISO em UTC")
    return pedido


def limite_do_pedido(pedido: dict, agora: datetime | None = None) -> float:
    """Até quando (relógio monotônico) o pedido ainda pode começar: criado_em + IDADE_MAXIMA_S. Vencido ou adiantado
    demais: Recusa, sem rodar (o pedido que um cliente morto deixou na fila não roda depois)."""
    idade = ((agora or datetime.now(timezone.utc)) - _data(pedido["criado_em"])).total_seconds()
    if idade < -ADIANTADO_S:
        raise Recusa(f"criado_em está {-idade:.0f} s no futuro (relógio da sessão adiantado?): não rodou; repita")
    if idade > IDADE_MAXIMA_S:
        raise Recusa(f"o pedido esperou {idade:.0f} s na fila (máximo {IDADE_MAXIMA_S} s): não rodou; repita")
    return time.monotonic() + IDADE_MAXIMA_S - max(idade, 0.0)


def validar_carga(op: str, carga: dict) -> dict:
    """Só os campos que a operação tem; a entrada fixa valida o valor de cada um de novo. `modo`, `variante`, `como`,
    `argv` e `comando` não são campos de nenhuma operação da sessão."""
    extras = set(carga) - set(OPERACOES[op]["campos"])
    if extras:
        raise Recusa(f"campos fora da operação {op}: {', '.join(sorted(map(ascii, extras)))[:120]}")
    if op == "codex":
        arquivos = carga.get("arquivos")
        if (not isinstance(arquivos, list) or not 1 <= len(arquivos) <= TETO_ARQUIVOS
                or not all(isinstance(a, str) for a in arquivos)):
            raise Recusa(f"arquivos: de 1 a {TETO_ARQUIVOS} caminhos do projeto")
        prompt = carga.get("prompt")
        try:
            tamanho = len(prompt.encode("utf-8")) if isinstance(prompt, str) else 0
        except UnicodeEncodeError:
            tamanho = 0
        if not 1 <= tamanho <= TETO_PROMPT_BYTES:
            raise Recusa(f"prompt: texto de 1 a {TETO_PROMPT_BYTES // 1024} KiB (a entrada fixa confere de novo o que ele pode ter)")
    return carga


def argv_da_jaula(cfg: dict, op: str, sudo: str = SUDO) -> list[str]:
    """O comando FIXO: sudo sem senha para o usuário da jaula, a entrada fixa da configuração, o projeto da
    configuração e o modo da tabela. Nada do pedido entra aqui."""
    return [sudo, "-n", "-u", USUARIO_JAULA, "--", cfg["entrada"], cfg["projeto"], OPERACOES[op]["modo"]]


def corpo_para_a_jaula(op: str, ident: str, carga: dict) -> bytes:
    """O pedido da jaula (fundacao.pedido_jaula/1): o id da fila e os campos da carga, pela entrada padrão."""
    return json.dumps({"schema_version": ESQUEMA_PEDIDO_DA_JAULA, "id": ident, **carga}, ensure_ascii=False).encode("utf-8")


# --- execução ----------------------------------------------------------------------------------------------------
def executar_sudo(argv: list[str], entrada: bytes, prazo: float, parar: threading.Event | None = None
                  ) -> tuple[int, bytes, bytes]:
    """(código, stdout, stderr) do comando fixo, em sessão própria, com ambiente mínimo e pasta atual `/`. Estourou o
    prazo, ou o porteiro foi encerrado: o grupo de processos é morto e o pedido volta como recusa."""
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd="/",
                            env={"PATH": PATH_FIXO, "LANG": "C.UTF-8"}, close_fds=True, start_new_session=True)
    fim = time.monotonic() + prazo
    primeira = True
    while True:
        try:
            saida, erro = proc.communicate(input=entrada if primeira else None, timeout=1.0)
            return proc.returncode, saida, erro
        except subprocess.TimeoutExpired:
            primeira = False
            if time.monotonic() > fim or (parar is not None and parar.is_set()):
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (OSError, AttributeError):
                    proc.kill()
                proc.communicate()
                raise Recusa("a jaula passou do prazo (ou o porteiro foi encerrado) e foi morta") from None


def resposta_de(ident: str, codigo: int, stdout: str, stderr: str, inicio: float, truncado: bool = False) -> dict:
    return {"versao": 1, "id": ident, "codigo": codigo, "stdout": stdout, "stderr": stderr, "truncado": truncado,
            "duracao_s": round(time.monotonic() - inicio, 3)}


def resposta_de_recusa(ident: str, exc: Exception, inicio: float) -> dict:
    erro = {"error": {"code": "E_PORTEIRO_JAULA", "message": str(exc)}}
    return resposta_de(ident, 2, "", json.dumps(erro, ensure_ascii=False) + "\n", inicio)


def resposta_da_jaula(ident: str, codigo: int, saida: bytes, erro: bytes, inicio: float) -> dict:
    """A resposta da entrada fixa passada adiante (código 0, 1 ou 2 dela). Sem JSON na saída, o sudo recusou (M1?)."""
    texto = saida[:TETO_STDOUT].decode("utf-8", "replace")
    truncado = len(saida) > TETO_STDOUT
    if codigo not in (0, 1, 2) or not texto.lstrip().startswith("{"):
        sudo = erro[:TETO_STDERR].decode("utf-8", "replace").strip()
        return resposta_de_recusa(ident, Recusa("a jaula não respondeu (o sudo recusou o argv fixo, a forma da sudoers "
                                                f"não vale ou a jaula não está instalada): {sudo[:300]}"), inicio)
    return resposta_de(ident, codigo, texto, erro[:TETO_STDERR].decode("utf-8", "replace"), inicio, truncado)


# --- registro e teto por dia --------------------------------------------------------------------------------------
def chamadas_de_hoje(registro: Path, op: str, hoje: str) -> int:
    """Quantas chamadas de `op` chegaram à jaula hoje (UTC), pelo registro do porteiro."""
    try:
        linhas = Path(registro).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return 0
    total = 0
    for linha in linhas:
        try:
            r = json.loads(linha)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("op") == op and r.get("rodou") is True and str(r.get("em", ""))[:10] == hoje:
            total += 1
    return total


def registrar(registro: Path, linha: dict) -> None:
    """Uma linha por pedido, sem conteúdo (nem carga, nem saída): id, op, modo, se chegou à jaula, código e duração."""
    try:
        fd = os.open(registro, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_CLOEXEC", 0), 0o600)
        try:
            os.write(fd, (json.dumps(linha, ensure_ascii=False) + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    except OSError as exc:
        sys.stderr.write(json.dumps({"aviso": f"registro do porteiro da jaula não gravado ({exc})"}) + "\n")


# --- o porteiro --------------------------------------------------------------------------------------------------
def _porteiro():
    """O `porteiro.py` ao lado deste arquivo (a mesma cópia conferida da skill): só a `Fila` é usada."""
    spec = importlib.util.spec_from_file_location("_porteiro_jaula_porteiro", AQUI / "porteiro.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class PorteiroJaula:
    def __init__(self, cfg: dict, fila: str | None, pid_lancador: int = 0, *, casa: Path | None = None, executar=None,
                 sudo: str = SUDO):
        self.cfg = cfg
        self.sudo = sudo
        self.executar = executar or executar_sudo
        self.pid_lancador = pid_lancador
        self.parar = threading.Event()
        self.privada = Path(casa or Path.home()) / ".fundacao" / "porteiro" / cfg["projeto"]
        self.registro = self.privada / "jaula-registro.jsonl"
        self.fila = None
        if fila is not None:
            esperado = os.path.join(cfg["raiz"], "projects", cfg["projeto"], ".porteiro", "jaula")
            if os.path.normpath(fila) != os.path.normpath(esperado):
                raise Recusa(f"a fila ({fila}) não é a do projeto da configuração ({esperado})")
            self.fila = _porteiro().Fila(fila)
        self.unico = None
        self.ignorados: set[str] = set()

    # ---- um pedido
    def atender(self, ident: str, dados: bytes, agora: datetime | None = None) -> tuple[dict, dict]:
        """(resposta, linha do registro). Tudo o que não for do comando fixo é recusa com o motivo."""
        inicio = time.monotonic()
        linha = {"id": ident, "op": None, "modo": None, "rodou": False}
        try:
            pedido = validar_pedido(dados, ident)
            op = linha["op"] = pedido["op"]
            if op not in self.cfg["operacoes"]:
                raise Recusa(f"a operação {op} não está aberta para este projeto (a ficha não a abre, ou ela é dos "
                             "lançadores do titular)")
            prazo_pedido = limite_do_pedido(pedido, agora)
            carga = validar_carga(op, pedido["carga"])
            teto = self.cfg["operacoes"][op].get("teto_chamadas_dia")
            if teto is not None and chamadas_de_hoje(self.registro, op, (agora or datetime.now(timezone.utc)).strftime(
                    "%Y-%m-%d")) >= teto:
                raise Recusa(f"o teto de {teto} chamadas por dia da operação {op} (ficha) foi atingido: tente amanhã, ou "
                             "o titular assina uma ficha com outro teto")
            if time.monotonic() > prazo_pedido:
                raise Recusa("o pedido venceu antes de rodar: não rodou; repita")
            linha["modo"] = OPERACOES[op]["modo"]
            argv = argv_da_jaula(self.cfg, op, self.sudo)
            linha["rodou"] = True
            codigo, saida, erro = self.executar(argv, corpo_para_a_jaula(op, ident, carga), OPERACOES[op]["prazo_s"],
                                                self.parar)
            resposta = resposta_da_jaula(ident, codigo, saida, erro, inicio)
        except (Recusa, OSError) as exc:
            resposta = resposta_de_recusa(ident, exc, inicio)
        linha.update({"codigo": resposta["codigo"], "duracao_s": resposta["duracao_s"], "em": agora_iso()})
        return resposta, linha

    def processar(self, nome: str) -> None:
        if nome.startswith(".") or nome in self.ignorados:
            return
        m = NOME_PEDIDO.fullmatch(nome)
        if not m:
            if nome.endswith(".json"):  # sem id não há resposta: sai da fila
                if self.fila.retirar(nome) is False:
                    self.ignorados.add(nome)
            return
        ident, inicio = m.group(1), time.monotonic()
        try:
            dados, resposta = self.fila.ler(nome), None
        except Exception as exc:  # noqa: BLE001 — a Fila recusa com a Recusa dela: o pedido sai com resposta
            dados, resposta = None, resposta_de_recusa(ident, Recusa(str(exc)), inicio)
        retirado = self.fila.retirar(nome)  # quem tira o nome da fila primeiro decide se o pedido roda
        if retirado is None:
            return
        if retirado is False:
            self.ignorados.add(nome)
            if resposta is None:
                resposta = resposta_de_recusa(ident, Recusa("o pedido não saiu da fila: não rodou; repita"), inicio)
        linha = {"id": ident, "op": None, "modo": None, "rodou": False, "codigo": 2, "duracao_s": 0.0, "em": agora_iso()}
        if resposta is None:
            try:
                resposta, linha = self.atender(ident, dados)
            except Exception as exc:  # noqa: BLE001 — última rede: o pedido hostil ou um defeito não derrubam o porteiro
                resposta = resposta_de_recusa(ident, Recusa(f"erro interno do porteiro da jaula ({type(exc).__name__}): "
                                                            "confira o efeito antes de repetir"), inicio)
        self.fila.responder(ident, resposta)
        registrar(self.registro, linha)

    # ---- ciclo
    def abrir(self) -> None:
        import fcntl
        casa = Path(self.privada).parents[2]
        atual = casa
        for parte in Path(self.privada).relative_to(casa).parts:
            atual = atual / parte
            try:
                atual.mkdir(mode=0o700)
            except FileExistsError:
                pass
            if atual.is_symlink() or not atual.is_dir():
                raise Recusa(f"{atual} é ligação ou não é pasta")
        fd = os.open(self.privada / "porteiro-jaula.trava", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise Recusa("já há um porteiro da jaula deste projeto de pé (outra sessão aberta)") from None
        self.unico = fd
        self.fila.abrir()

    def servir(self) -> int:
        signal.signal(signal.SIGTERM, lambda *_: self.parar.set())
        signal.signal(signal.SIGHUP, lambda *_: self.parar.set())
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            os.setsid()
        except OSError:
            pass
        try:
            self.abrir()
        except (Recusa, OSError) as exc:
            sys.stderr.write(json.dumps({"error": {"code": "E_PORTEIRO_JAULA", "message": str(exc)}}, ensure_ascii=False)
                             + "\n")
            self.encerrar()
            return 2
        try:
            self.fila.vida("pronto", forcar=True)
            while not self.parar.is_set() and processo_vivo(self.pid_lancador):
                try:
                    self.fila.vida("pronto")
                    self.fila.limpar()
                    for nome in self.fila.listar():
                        if self.parar.is_set():
                            break
                        self.processar(nome)
                except OSError as exc:
                    sys.stderr.write(json.dumps({"aviso": {"code": "W_PORTEIRO_JAULA_FILA", "message": str(exc)}},
                                                ensure_ascii=False) + "\n")
                self.parar.wait(INTERVALO_S)
        finally:
            self.encerrar()
        return 0

    def encerrar(self) -> None:
        try:
            if self.fila is not None:
                self.fila.fechar()
        except OSError:
            pass
        if self.unico is not None:
            os.close(self.unico)
            self.unico = None


def processo_vivo(pid: int) -> bool:
    """O processo do lançador ainda roda (zumbi conta como morto); fora de 2..PID_MAXIMO nunca conta como vivo."""
    if not 1 < pid <= PID_MAXIMO:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, OverflowError):
        return False
    except PermissionError:
        return True
    try:
        with open(f"/proc/{pid}/stat", "rb") as arq:
            return arq.read().rsplit(b")", 1)[1].split()[0] != b"Z"
    except (OSError, IndexError):
        return True


def preparar_sudo(etc: str = ETC_JAULA, rodar=subprocess.run) -> int:
    """Forma "senha" da sudoers [medir M1]: o `sudo -v` no terminal do titular, antes da sessão, para o ticket valer
    (`sudo -n` do porteiro). Na forma NOPASSWD, nada a fazer."""
    if forma_do_sudo(etc) != "senha":
        return 0
    print("A jaula pede a sua senha do Linux uma vez por sessão (sudo -v):", file=sys.stderr)
    env = {"PATH": PATH_FIXO, "LANG": "C.UTF-8", "TERM": os.environ.get("TERM", "dumb")}
    return rodar([SUDO, "-v"], env=env).returncode


def invalidar_sudo(etc: str = ETC_JAULA, rodar=subprocess.run) -> bool:
    """F11 (3ª passada da revisão de segurança da 1.7.11): na forma "senha", o ticket do sudo que o `preparar-sudo` renovou não fica
    vivo depois que o porteiro da jaula termina (`sudo -k`, que nunca pede senha). Falha aqui não muda o código de saída do porteiro.
    Devolve se rodou. O lançador faz o mesmo no terminal dele ao sair (`abrir-sessao.sh`). Limite: o terminal próprio do porteiro
    (`setsid` com pty novo, para o ticket ser de outro terminal que não o da sessão) fica para a 1.7.12."""
    try:
        if forma_do_sudo(etc) != "senha":
            return False
        rodar([SUDO, "-k"], env={"PATH": PATH_FIXO, "LANG": "C.UTF-8"}, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
              stderr=subprocess.DEVNULL, timeout=10, check=False)
    except (Recusa, OSError, subprocess.SubprocessError):
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8", errors="backslashreplace")
    p = argparse.ArgumentParser(prog="porteiro_jaula.py", allow_abbrev=False,
                                description="Porteiro da jaula do Criador (1.7.11, L4).")
    sub = p.add_subparsers(dest="acao", required=True)
    for nome in ("conferir", "preparar-sudo"):
        sub.add_parser(nome, allow_abbrev=False).add_argument("--config", required=True)
    s = sub.add_parser("servir", allow_abbrev=False)
    s.add_argument("--config", required=True)
    s.add_argument("--fila", required=True)
    s.add_argument("--pid-lancador", type=int, required=True)
    args = p.parse_args(argv)
    try:
        cfg = carregar_config(args.config)
        if args.acao == "conferir":
            print(json.dumps({"ok": True, "projeto": cfg["projeto"], "operacoes": sorted(cfg["operacoes"])}))
            return 0 if cfg["operacoes"] else 3
        if args.acao == "preparar-sudo":
            return preparar_sudo()
        if not 1 < args.pid_lancador <= PID_MAXIMO:
            raise Recusa(f"pid do lançador inválido (entre 2 e {PID_MAXIMO}): {args.pid_lancador}")
        if not cfg["operacoes"]:
            raise Recusa("a configuração não abre operações para a sessão: nada a servir")
        if os.name != "posix" or os.open not in os.supports_dir_fd:
            raise Recusa("o porteiro da jaula roda só no Linux (WSL2)")
        try:
            return PorteiroJaula(cfg, args.fila, args.pid_lancador).servir()
        finally:
            invalidar_sudo()   # F11: o porteiro terminou (ou nem subiu): o ticket do sudo não fica de pé
    except (Recusa, OSError) as exc:
        print(json.dumps({"error": {"code": "E_PORTEIRO_JAULA", "message": str(exc)}}, ensure_ascii=False),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
