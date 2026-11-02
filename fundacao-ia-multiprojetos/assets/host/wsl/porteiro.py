#!/usr/bin/env python3
"""Porteiro da sessão de projeto no Ubuntu (1.7.10; contratos do lote 2, §2 e §4; desenho 1.7.10, §2 e princípio 4;
crítica do desenho: "porteiro, operação fundacao", "fila do porteiro" e "trava global do banco").

O caminho da sessão do projeto até o banco da fundação. Roda FORA do sandbox, iniciado pelo lançador do projeto, preso
à raiz, ao projeto e ao titular da configuração `porteiro.json` (área do titular, de dono root) — nunca ao ambiente da
sessão. Só biblioteca padrão; não importa nada do kit.

Linha de comando (o lançador a usa a partir da cópia conferida da skill, depois de conferir o SHA-256 deste arquivo):
  python3 -I -B porteiro.py servir --config /etc/fundacao-ia/projetos/<p>/porteiro.json \\
      --fila <raiz>/projects/<p>/.porteiro --pid-lancador <pid>
  python3 -I -B porteiro.py conferir --config <arq>     (só a configuração e o hash do kit; código 0 ou 2)
`servir` cria pedidos/ e respostas/ se faltarem, segura a trava do banco, faz o aperto de mão, atende até o processo
--pid-lancador morrer (ou SIGTERM) e solta a trava ao sair.

Cada pedido (contratos, §4):
- fila: `pedidos/` (a sessão grava; tratada como hostil) e `respostas/` (só o porteiro grava; o perfil nega escrita e
  Edit só nela, nunca na pasta-mãe). Pedido lido pelo descritor da pasta, O_NOFOLLOW|O_NONBLOCK, só arquivo comum com
  um nome só (st_nlink == 1), até 64 KiB; resposta gravada por descritor, O_NOFOLLOW|O_EXCL, e trocada atomicamente;
  sinal de vida em respostas/porteiro-vivo.json, para o cliente falhar em segundos se o porteiro parar.
- só a operação `fundacao` nesta versão; git-enviar, executar e rodar: código 2, "1.7.11".
- pedido tipado: argparse sem abreviação e mapa fixo do que a sessão usa (MAPA, MEMORIA e ABERTURA, com as opções de
  cada ação; o mesmo de COMANDOS_DA_TRAVA do kit, em fundacao/core/auth.py: há teste, que desce nos subparsers do kit);
  nunca init, projeto, acl, componente, backup, copia-assinatura, rota, aprovar ou curar, --raiz nem --ancora, e na
  1.7.10 nem eventos nem memoria licao historico (emenda E2 dos contratos); --projeto só o da configuração; caminho só
  dentro de projects/<p>/.
- idade: o pedido que esperou mais que IDADE_MAXIMA_S (fila, vez do banco e cópia conferida do kit) não roda ("não
  rodou; repita"): com o prazo do kit, cabe no corte de 120 s do Bash, e o pedido deixado por um cliente morto não roda
  depois (revisão do lote 2).
- aperto de mão: o `status` do kit da raiz, no modo travado, tem de provar projeto_travado == <p>, a identidade
  sessao-<p> e KIT_VERSION >= 1.7.10; senão todo pedido é recusado (código 2, "o kit da raiz não prova a trava").
- execução: python3 -I -B -S -X utf8 -X pycache_prefix=<pasta vazia> — nenhum .pyc de __pycache__ roda no lugar da
  fonte conferida —, pasta atual fora do projeto, ambiente mínimo; a árvore do kit fixada por SHA-256
  (porteiro.json.kit_sha256) e reconferida, com a configuração relida, antes de cada pedido. O que roda é uma cópia
  privada do kit, gravada na pasta de trabalho do porteiro no mesmo passe em que cada arquivo da raiz é lido e entra no
  hash, e apagada no fim do pedido (revisão do lote 2): a troca de um arquivo do kit da raiz depois da conferência não
  chega à execução, nem a um import tardio, e o pedido seguinte a recusa. Nada da raiz entra no caminho de importação.
  A árvore tem teto (TETO_KIT_ITENS, TETO_KIT_BYTES), conferido por fluxo antes de cada byte ir para a cópia. Prazo
  (PRAZO_KIT_S) e teto de saída, para a árvore de processos. `registry/` fica fora do hash (emenda E5; ver
  sha256_do_kit).
- um porteiro por projeto: flock em ~/.fundacao/porteiro/<p>/porteiro.trava antes de tocar a fila; com ele na mão, as
  pastas de trabalho de um porteiro morto saem (revisão do lote 2), salvo a que um processo ainda usa (o kit órfão
  dele, pela pasta atual ou por um argumento, lidos em /proc; com /proc ilegível, nenhuma sai), como no limpar-porteiro
  do HOST (reconferência 3 do lote 2); a que ficou vira aviso W_PORTEIRO_TRABALHO_MANTIDO.
- trava do banco: marcador state/banco.trava (lado ubuntu) do início ao fim, renovado; flock entre os porteiros. Quem
  espera a vez de outro porteiro segue renovando o sinal de vida (o cliente não desiste de um pedido que vai rodar).
- registro sem conteúdo: ~/.fundacao/porteiro/<p>/registro.jsonl (id, op, código, duração, quando).
- pedido hostil não derruba o porteiro: texto fora do UTF-8 é recusado, e o erro inesperado vira resposta (código 2).

Honestidade (§0 dos contratos): com a raiz em /mnt/e, onde o sandbox do Claude Code não confinou os comandos nas
sondas de 31/10/2026, a fila e a trava de projeto são camadas lógicas — um comando da sessão ainda alcança o banco e os
outros projetos por fora delas — até o canário passar no ambiente real. O núcleo de confiança é este arquivo mais o kit
inteiro da raiz (fixado por hash), não só o porteiro. A cópia privada fica na casa do usuário do Ubuntu (pasta 0700):
ela tira da execução a troca feita na raiz, mas quem roda como esse usuário fora do sandbox ainda a alcança enquanto o
pedido roda.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = "fundacao.porteiro/1"
CAMPOS_CONFIG = ("schema_version", "raiz", "projeto", "kit_sha256", "assinante", "operacoes")
CAMPOS_PEDIDO = ("versao", "id", "op", "argv", "criado_em")
OPERACOES_1711 = ("git-enviar", "executar", "rodar")
VERSAO_MINIMA = (1, 7, 10)
PREFIXO_SESSAO = "sessao-"
IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"
TETO_PEDIDO = 64 * 1024
TETO_CONFIG = 64 * 1024
TETO_STDOUT = 4 * 1024 * 1024
TETO_STDERR = 1024 * 1024
# O kit tem cerca de 50 arquivos e 0,5 MB. A cópia conferida grava cada byte antes de o hash fechar: o teto barra, antes
# de ir para o disco, o arquivo plantado na raiz que encheria o disco virtual do WSL (revisão do lote 2).
TETO_KIT_BYTES = 16 * 1024 * 1024
TETO_KIT_ITENS = 2000      # arquivos e pastas da árvore do kit
PRAZO_KIT_S = 100          # a ferramenta Bash corta em 120 s por padrão (crítica do desenho: prazo do fundacao)
# Pedido que esperou mais que IDADE_MAXIMA_S (fila, vez do banco e cópia conferida do kit, contados de criado_em) não
# roda, com "não rodou; repita": somada ao prazo do kit, a espera cabe em ORCAMENTO_S, abaixo do corte de 120 s do Bash,
# e o pedido que um cliente morto deixou na fila não roda na sessão seguinte (revisão do lote 2; há teste da soma).
IDADE_MAXIMA_S = 15
ORCAMENTO_S = 115
ADIANTADO_S = 5            # criado_em adiantado até isto passa (o mesmo relógio do computador); mais que isto, não
ESPERA_VEZ_S = IDADE_MAXIMA_S  # a vez do banco nunca é esperada além do que um pedido ainda pode esperar
INTERVALO_S = 0.2
VIDA = "porteiro-vivo.json"
VIDA_S = 5
TTL_RESPOSTA_S = 600
MARCADOR = "banco.trava"   # o mesmo formato de fundacao/core/trava_banco.py (há teste)
LADOS = ("windows", "ubuntu")
RENOVAR_S = 30
RETENTAR_S = 5             # renovação que falhou: espera para tentar de novo (revisão do lote 2)
VIVO_S = 120
PID_MAXIMO = 4194304       # o maior pid_max do Linux de 64 bits (PID_MAX_LIMIT, 2**22)
PATH_FIXO = "/usr/bin:/bin"
ID_RE = re.compile(r"[0-9a-f]{32}")
NOME_PEDIDO = re.compile(r"([0-9a-f]{32})\.json")
PROJETO_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?")
RESERVADOS = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
ASSINANTE_RE = re.compile(r"[A-Za-z0-9._@-]{1,100}")
SHA_RE = re.compile(r"[0-9a-f]{64}")
VERSAO_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
O_BINARY = getattr(os, "O_BINARY", 0)
_SUBSTITUTA_DE_NOME = 0x20000000  # Windows: junção, link simbólico e afins (bit 29 da etiqueta de reparse)

# Mapa fixo do que a sessão pede ao kit: comando -> (ações, opções com valor, opções de caminho, sinais sem valor).
# Fica igual a COMANDOS_DA_TRAVA do kit (fundacao/core/auth.py) e cada opção existe no parser do kit (há teste). Na
# 1.7.10 ficam fora `eventos` e `memoria licao historico` (emenda E2 dos contratos: leitura que pode mostrar o que não é
# do projeto, e a sessão não precisa dela; voltam na 1.7.11 só com leitura restrita ao projeto). `abertura` tem as
# opções de cada ação em ABERTURA, como os subparsers do kit (cli_aberturas): a linha dela no MAPA é a união.
MAPA = {
    "status": ((), (), (), ()),
    "tarefa": (("criar", "ver", "concluir"), ("--projeto", "--objetivo", "--chave", "--id"), ("--decisao",), ()),
    "decisao": (("preparar", "verificar", "registrar", "comando", "conferir-ancora"),
                ("--projeto", "--tarefa", "--tipo", "--entrega", "--motivo", "--decisao-id", "--shell"),
                ("--arquivo",), ()),
    "abertura": (("preparar", "verificar", "vigente"), ("--projeto", "--versao"), ("--rascunho",), ("--json",)),
    "conhecimento": (("listar", "buscar"), ("--projeto", "--consulta"), (), ()),
}
# abertura <ação> -> (opções com valor, opções de caminho, sinais): as de cada subparser do cli_aberturas, sem --arquivo
# (o kit não o tem) e, no `vigente`, sem --area (o kit travado também a recusa): item I3 da integração da 1.7.10. Opção
# de outra ação (--versao no `vigente`, --rascunho no `verificar`) é recusada pelo porteiro, não pelo kit.
ABERTURA = {
    "preparar": (("--projeto",), ("--rascunho",), ()),
    "verificar": (("--projeto", "--versao"), (), ()),
    "vigente": (("--projeto",), (), ("--json",)),
}
MEMORIA = {  # memoria licao <ação>: as opções de cada ação (aprovar, revisar, retirar e historico ficam de fora)
    "propor": ("--projeto", "--op-id", "--origem", "--vigente-desde", "--gatilho", "--licao", "--evidencia",
               "--confianca"),
    "consultar": ("--projeto", "--gatilho"),
    "pendente": ("--memoria",),
}

BOOTSTRAP = "\n".join((
    "import importlib.util, os, sys",
    "pasta = sys.argv[1]",
    "spec = importlib.util.spec_from_file_location('fundacao', os.path.join(pasta, '__init__.py'),",
    "                                              submodule_search_locations=[pasta])",
    "modulo = importlib.util.module_from_spec(spec)",
    "sys.modules['fundacao'] = modulo",
    "spec.loader.exec_module(modulo)",
    "from fundacao.__main__ import main",
    "raise SystemExit(main(sys.argv[2:]))",
))


class Recusa(Exception):
    """O porteiro recusa: o pedido sai com código 2 e o motivo em JSON no stderr da resposta."""


class VezOcupada(Recusa):
    """A vez do banco ficou com outro porteiro além do prazo. Passageira: o pedido não rodou, e no aperto de mão ela
    não vira recusa para a sessão inteira (revisão do lote 2)."""


class KitAlterado(Recusa):
    """A árvore do kit da raiz não confere com porteiro.json. Passageira: o pedido seguinte confere de novo."""


def agora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _data(texto) -> datetime | None:
    if not isinstance(texto, str):
        return None
    try:
        data = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    return data if data.tzinfo else data.replace(tzinfo=timezone.utc)


def _iso_utc(texto) -> bool:
    """Data ISO com o fuso UTC escrito ("Z" ou "+00:00"), como o cliente grava criado_em (contratos, §4)."""
    if not isinstance(texto, str) or not texto.endswith(("Z", "+00:00")):
        return False
    data = _data(texto)
    return data is not None and data.utcoffset() == timedelta(0)


def _ligacao(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & _SUBSTITUTA_DE_NOME)


def _sem_repetidas(pares):
    vistos = {}
    for chave, valor in pares:
        if chave in vistos:
            raise ValueError(f"chave repetida: {chave}")
        vistos[chave] = valor
    return vistos


def _json(dados: bytes):
    return json.loads(dados.decode("utf-8"), object_pairs_hook=_sem_repetidas)


def _ler_arquivo(caminho, teto: int, *, dir_fd=None) -> bytes:
    """Bytes de um arquivo comum de um nome só, sem seguir ligação nem travar num FIFO, até `teto`."""
    if dir_fd is None:  # sem descritor de pasta (e no Windows, sem O_NOFOLLOW): o exame sem seguir ligação antes
        try:
            if _ligacao(os.lstat(caminho)):
                raise Recusa("é ligação (link simbólico ou junção)")
        except OSError as exc:
            raise Recusa(f"não deu para examinar ({exc.strerror or type(exc).__name__})") from None
    try:
        fd = os.open(caminho, os.O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC | O_BINARY,
                     **({} if dir_fd is None else {"dir_fd": dir_fd}))
    except OSError as exc:
        raise Recusa(f"não abriu sem seguir ligação ({exc.strerror or type(exc).__name__})") from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise Recusa("não é arquivo comum (pasta, FIFO, dispositivo ou socket)")
        if st.st_nlink != 1:
            raise Recusa("tem vínculo físico (mais de um nome): o conteúdo pode ser de um arquivo de fora")
        if st.st_size > teto:
            raise Recusa(f"acima do teto de {teto} bytes")
        dados = bytearray()
        while len(dados) <= teto and (bloco := os.read(fd, 1 << 16)):
            dados += bloco
    except OSError as exc:  # falha de leitura vira recusa: o pedido sai da fila com resposta, não fica em laço
        raise Recusa(f"não deu para ler ({exc.strerror or type(exc).__name__})") from None
    finally:
        os.close(fd)
    if len(dados) > teto:
        raise Recusa(f"acima do teto de {teto} bytes")
    return bytes(dados)


# ------------------------------------------------------------------ configuração e árvore do kit
def validar_config(cfg) -> dict:
    """porteiro.json no esquema fundacao.porteiro/1, sem campo a mais (additionalProperties: false)."""
    if not isinstance(cfg, dict) or set(cfg) != set(CAMPOS_CONFIG):
        raise Recusa(f"porteiro.json fora do esquema {SCHEMA}: os campos são {', '.join(CAMPOS_CONFIG)}")
    if cfg["schema_version"] != SCHEMA:
        raise Recusa(f"porteiro.json com schema_version desconhecido (esperado {SCHEMA})")
    raiz = cfg["raiz"]
    if not isinstance(raiz, str) or not os.path.isabs(raiz) or any(c in raiz for c in "\0\r\n"):
        raise Recusa("porteiro.json: raiz precisa ser um caminho absoluto")
    projeto = cfg["projeto"]
    if (not isinstance(projeto, str) or not PROJETO_RE.fullmatch(projeto) or "--" in projeto
            or projeto in RESERVADOS):
        raise Recusa("porteiro.json: projeto fora da forma de identificador ([a-z0-9-], 1 a 40)")
    if not isinstance(cfg["kit_sha256"], str) or not SHA_RE.fullmatch(cfg["kit_sha256"]):
        raise Recusa("porteiro.json: kit_sha256 precisa ser um SHA-256 (64 hexadecimais minúsculos)")
    assinante = cfg["assinante"]
    if (not isinstance(assinante, str) or not ASSINANTE_RE.fullmatch(assinante)
            or assinante.startswith(PREFIXO_SESSAO)):
        raise Recusa("porteiro.json: assinante precisa ser a identidade do titular ([A-Za-z0-9._@-], nunca sessao-)")
    operacoes = cfg["operacoes"]
    if not isinstance(operacoes, dict) or "fundacao" not in operacoes:
        raise Recusa('porteiro.json: operacoes precisa ser {"fundacao": {}}')
    adiadas = sorted(set(operacoes) & set(OPERACOES_1711))
    if adiadas:
        raise Recusa(f"porteiro.json: as operações {', '.join(adiadas)} ficam para a 1.7.11")
    if set(operacoes) != {"fundacao"} or operacoes["fundacao"] != {}:
        raise Recusa('porteiro.json: nesta versão, operacoes é exatamente {"fundacao": {}}')
    return cfg


def carregar_config(caminho) -> tuple[dict, str]:
    """(configuração conferida, SHA-256 do arquivo). Sem seguir ligação, com teto, sem chave repetida."""
    try:
        dados = _ler_arquivo(caminho, TETO_CONFIG)
        cfg = _json(dados)
    except Recusa as exc:
        raise Recusa(f"porteiro.json ({caminho}): {exc}") from None
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise Recusa(f"porteiro.json ilegível ({type(exc).__name__}: {exc})") from None
    return validar_config(cfg), hashlib.sha256(dados).hexdigest()


def _nome_no_kit(rel: str) -> bytes:
    """O caminho relativo em bytes UTF-8, a chave da ordem do hash. Nome fora do UTF-8 (no Linux, bytes que não
    decodificam) ou com caractere de controle (a linha do hash ficaria ambígua): Recusa, nunca exceção solta."""
    try:
        dados = rel.encode("utf-8")
    except UnicodeEncodeError:
        raise Recusa(f"nome fora do UTF-8 no kit: {rel!r}") from None
    if any(c < 0x20 or c == 0x7F for c in dados):
        raise Recusa(f"nome com caractere de controle no kit: {rel!r}")
    return dados


def _passou_do_teto(base: str) -> Recusa:
    return Recusa(f"o kit da raiz passou do teto ({TETO_KIT_ITENS} arquivos e pastas, {TETO_KIT_BYTES} bytes): nada "
                  f"além do teto foi lido nem copiado; confira o que foi posto em {base} e refaça o preparo do projeto")


def _ler_e_copiar(caminho: str, rel: str, destino: str | None, teto: int) -> tuple[str, int]:
    """(SHA-256, bytes lidos) de um arquivo do kit, lido sem seguir ligação nem travar num FIFO; com `destino`, os
    mesmos bytes são gravados lá no mesmo passe (arquivo novo, exclusivo). Conferido por fluxo, parando cedo (revisão do
    lote 2): o arquivo maior que `teto` (o que ainda cabe no teto do kit) é recusado antes do primeiro byte, e o que
    cresce depois de aberto, antes de o bloco a mais ir para o disco: a cópia nunca passa do tamanho visto ao abrir."""
    h = hashlib.sha256()
    fd = os.open(caminho, os.O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC | O_BINARY)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):  # trocado entre o exame e a abertura
            raise Recusa(f"no kit, {rel} não é arquivo comum")
        if st.st_size > teto:
            raise _passou_do_teto(os.path.dirname(caminho))
        saida = None if destino is None else os.open(
            destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_NOFOLLOW | O_CLOEXEC | O_BINARY, 0o600)
        lidos = 0
        try:
            while bloco := os.read(fd, 1 << 20):
                lidos += len(bloco)
                if lidos > st.st_size:
                    raise Recusa(f"no kit, {rel} cresceu durante a leitura: confira a raiz e repita")
                h.update(bloco)
                vista = memoryview(bloco) if saida is not None else None
                while vista:
                    vista = vista[os.write(saida, vista):]
        finally:
            if saida is not None:
                os.close(saida)
    finally:
        os.close(fd)
    return h.hexdigest(), lidos


def _pasta_ilegivel(exc: OSError):
    raise Recusa(f"pasta do kit ilegível ({exc.strerror or type(exc).__name__}): {exc.filename}")


def sha256_do_kit(raiz, copiar_para: str | None = None, durante=None) -> str:
    """SHA-256 da árvore do kit da raiz (`<raiz>/fundacao`), o valor de porteiro.json.kit_sha256: para cada arquivo, em
    ordem do caminho relativo (POSIX, comparado em bytes UTF-8), a linha "<sha256 do conteúdo>  <caminho>\\n"; o
    resultado é o SHA-256 do texto todo. As pastas __pycache__ ficam de fora (o porteiro nunca lê bytecode delas:
    pycache_prefix); um .pyc fora delas entra (rodaria como módulo). Ligação, arquivo que não é comum, pasta ilegível,
    nome fora do UTF-8 ou com caractere de controle e a árvore acima de TETO_KIT_ITENS ou TETO_KIT_BYTES: Recusa. Com
    `copiar_para` (pasta vazia), cada arquivo é gravado ali no mesmo passe em que é lido e entra no hash: a cópia tem
    exatamente os bytes conferidos (kit_conferido), e nunca mais que o teto. `durante` é chamado a cada meio segundo
    de leitura (a trava do banco e o sinal de vida seguem renovados numa árvore lenta de ler, como no DrvFs).
    Limite (emenda E5 dos contratos): `registry/` fica fora do kit_sha256 — é configuração que o kit valida ao ler, e o
    perfil do projeto nega à sessão a escrita nela; com a raiz em /mnt/e, onde o sandbox não confinou os comandos
    (§0 dos contratos), isso é isolamento lógico até o canário passar."""
    base = os.path.join(str(raiz), "fundacao")
    try:
        st = os.lstat(base)
    except OSError as exc:
        raise Recusa(f"o kit da raiz não existe ({base}: {exc.strerror})") from None
    if _ligacao(st) or not stat.S_ISDIR(st.st_mode):
        raise Recusa(f"o kit da raiz ({base}) é ligação ou não é pasta")
    itens, total, n, renovar_em = [], 0, 0, time.monotonic() + 0.5
    for atual, pastas, arquivos in os.walk(base, onerror=_pasta_ilegivel, followlinks=False):
        rel_atual = os.path.relpath(atual, base)
        for nome in list(pastas):
            if _ligacao(os.lstat(os.path.join(atual, nome))):
                raise Recusa(f"ligação dentro do kit: {os.path.relpath(os.path.join(atual, nome), base)}")
        pastas[:] = [p for p in pastas if p != "__pycache__"]
        n += len(pastas)
        if n > TETO_KIT_ITENS:
            raise _passou_do_teto(base)
        if copiar_para is not None:
            for nome in pastas:
                os.mkdir(os.path.join(copiar_para, rel_atual, nome), 0o700)
        for nome in arquivos:
            if durante is not None and time.monotonic() >= renovar_em:
                try:
                    durante()
                except OSError:  # renovar falhou: a conferência segue
                    pass
                renovar_em = time.monotonic() + 0.5
            caminho = os.path.join(atual, nome)
            rel = os.path.relpath(caminho, base).replace(os.sep, "/")
            chave = _nome_no_kit(rel)
            st = os.lstat(caminho)
            if _ligacao(st) or not stat.S_ISREG(st.st_mode):
                raise Recusa(f"no kit, {rel} é ligação ou não é arquivo comum")
            n += 1
            if n > TETO_KIT_ITENS or total + st.st_size > TETO_KIT_BYTES:
                raise _passou_do_teto(base)
            destino = None if copiar_para is None else os.path.join(copiar_para, rel_atual, nome)
            sha, lidos = _ler_e_copiar(caminho, rel, destino, TETO_KIT_BYTES - total)
            total += lidos
            itens.append((chave, f"{sha}  {rel}\n"))
    return hashlib.sha256("".join(linha for _, linha in sorted(itens)).encode("utf-8")).hexdigest()


def _kit_alterado(atual: str, esperado: str) -> KitAlterado:
    return KitAlterado(f"a árvore do kit da raiz mudou desde o preparo (SHA-256 {atual[:12]}..., esperado "
                       f"{esperado[:12]}...): o porteiro não roda código não conferido; refaça o preparo do projeto")


def kit_conferido(raiz, esperado: str, pasta_trabalho: str, durante=None) -> str:
    """A cópia privada do kit que o porteiro executa (revisão do lote 2): numa pasta nova dentro de `pasta_trabalho`,
    cada arquivo do kit da raiz é lido uma vez, entra no hash e é gravado no mesmo passe. Com o hash diferente de
    `esperado` (ou a árvore recusada), a cópia sai e KitAlterado sobe. Devolve a pasta do pacote (<cópia>/fundacao);
    quem a usa apaga a pasta de cima no fim. `durante`: como em sha256_do_kit."""
    copia = tempfile.mkdtemp(prefix="kit-", dir=pasta_trabalho)
    pacote = os.path.join(copia, "fundacao")
    try:
        os.mkdir(pacote, 0o700)
        try:
            atual = sha256_do_kit(raiz, copiar_para=pacote, durante=durante)
        except KitAlterado:
            raise
        except Recusa as exc:
            raise KitAlterado(f"árvore do kit recusada: {exc}") from None
        if atual != esperado:
            raise _kit_alterado(atual, esperado)
    except BaseException:
        shutil.rmtree(copia, ignore_errors=True)
        raise
    return pacote


def _de_root(caminho) -> bool | None:
    """O arquivo e as pastas acima são de root e sem escrita de grupo ou outros (a área do titular, §6); None fora do
    POSIX. Só informa: quem decide é o lançador, que confere os hashes antes de abrir."""
    if os.name != "posix":
        return None
    atual = os.path.abspath(caminho)
    while True:
        try:
            st = os.lstat(atual)
        except OSError:
            return False
        if st.st_uid != 0 or st.st_mode & 0o022 or _ligacao(st):
            return False
        pai = os.path.dirname(atual)
        if pai == atual:
            return True
        atual = pai


def conferir(caminho) -> dict:
    """`porteiro.py conferir`: a configuração e a árvore do kit, sem abrir a fila nem o banco."""
    res = {"ok": False, "config": str(caminho)}
    try:
        cfg, sha = carregar_config(caminho)
    except Recusa as exc:
        return {**res, "motivo": str(exc)}
    res.update(raiz=cfg["raiz"], projeto=cfg["projeto"], sha256_config=sha, kit_sha256_esperado=cfg["kit_sha256"],
               configuracao_de_root=_de_root(caminho))
    try:
        res["kit_sha256_encontrado"] = sha256_do_kit(cfg["raiz"])
    except (Recusa, OSError, ValueError) as exc:  # o código de saída fica no contrato (0 ou 2), sem traceback
        return {**res, "motivo": f"árvore do kit não conferida: {exc}"}
    if res["kit_sha256_encontrado"] != cfg["kit_sha256"]:
        return {**res, "motivo": "a árvore do kit da raiz não confere com porteiro.json: refaça o preparo do projeto"}
    return {**res, "ok": True, "motivo": "configuração e árvore do kit conferidas"}


# ------------------------------------------------------------------ pedido tipado
class _Parser(argparse.ArgumentParser):
    """Sem abreviação nem ajuda; erro vira Recusa (nada de sair do processo nem de imprimir)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allow_abbrev", False)
        kwargs.setdefault("add_help", False)
        super().__init__(*args, **kwargs)

    def error(self, message):
        raise Recusa(f"pedido fora do mapa do porteiro: {message}")

    def exit(self, status=0, message=None):
        raise Recusa(f"pedido fora do mapa do porteiro: {message or 'saída pedida'}")


def _destino(opcao: str) -> str:
    return opcao[2:].replace("-", "_")


def _com_opcoes(s: argparse.ArgumentParser, com_valor, sinais) -> None:
    for opcao in com_valor:
        s.add_argument(opcao)
    for opcao in sinais:
        s.add_argument(opcao, action="store_true")


def parser_do_mapa() -> argparse.ArgumentParser:
    p = _Parser(prog="python -m fundacao (pelo porteiro)")
    sub = p.add_subparsers(dest="comando", required=True)
    for comando, (acoes, opcoes, caminhos, sinais) in MAPA.items():
        s = sub.add_parser(comando)
        if comando == "abertura":  # um subparser por ação, com as opções dela, como no kit (item I3 da integração)
            por_acao = s.add_subparsers(dest="acao", required=True)
            for acao, (opcoes_da_acao, caminhos_da_acao, sinais_da_acao) in ABERTURA.items():
                _com_opcoes(por_acao.add_parser(acao), opcoes_da_acao + caminhos_da_acao, sinais_da_acao)
            continue
        if acoes:
            s.add_argument("acao", choices=acoes)
        _com_opcoes(s, opcoes + caminhos, sinais)
    licao = sub.add_parser("memoria").add_subparsers(dest="memoria_grupo", required=True).add_parser("licao")
    acoes = licao.add_subparsers(dest="memoria_acao", required=True)
    for acao, opcoes in MEMORIA.items():
        a = acoes.add_parser(acao)
        for opcao in opcoes:
            a.add_argument(opcao)
    return p


def caminho_no_projeto(cfg: dict, valor: str) -> str:
    """O caminho resolvido (relativo vale a partir da pasta do projeto), só se ficar dentro de projects/<p>/."""
    projeto = os.path.realpath(os.path.join(cfg["raiz"], "projects", cfg["projeto"]))
    alvo = os.path.realpath(valor if os.path.isabs(valor) else os.path.join(projeto, valor))
    try:
        dentro = os.path.commonpath([projeto, alvo]) == projeto
    except ValueError:
        dentro = False
    if not dentro:
        raise Recusa(f"caminho fora de projects/{cfg['projeto']}/: recusado")
    return alvo


def argv_do_kit(argv, cfg: dict) -> list[str]:
    """O argv que o kit recebe, montado pelo porteiro a partir do pedido tipado: a raiz da configuração, o comando e
    a ação do mapa e cada opção na forma --opcao=valor (valor que começa com hífen não vira opção)."""
    if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
        raise Recusa("argv do pedido precisa ser uma lista de textos")
    if any("\0" in a for a in argv):
        raise Recusa("argv do pedido com caractere nulo")
    ns = parser_do_mapa().parse_args(argv)
    saida = ["--raiz", cfg["raiz"], ns.comando]
    if ns.comando == "memoria":
        saida += ["licao", ns.memoria_acao]
        opcoes, caminhos, sinais = MEMORIA[ns.memoria_acao], (), ()
    elif ns.comando == "abertura":  # só as opções da ação pedida (ABERTURA; item I3 da integração)
        saida.append(ns.acao)
        opcoes, caminhos, sinais = ABERTURA[ns.acao]
    else:
        acoes, opcoes, caminhos, sinais = MAPA[ns.comando]
        if acoes:
            saida.append(ns.acao)
    for opcao in opcoes:
        valor = getattr(ns, _destino(opcao))
        if valor is None:
            continue
        if opcao == "--projeto" and valor != cfg["projeto"]:
            raise Recusa(f"pelo porteiro desta sessão, só o projeto {cfg['projeto']}")
        saida.append(f"{opcao}={valor}")
    for opcao in caminhos:
        valor = getattr(ns, _destino(opcao))
        if valor is not None:
            saida.append(f"{opcao}={caminho_no_projeto(cfg, valor)}")
    saida += [opcao for opcao in sinais if getattr(ns, _destino(opcao))]
    return saida


def validar_pedido(dados: bytes, ident: str) -> dict:
    """{"versao": 1, "id": "<32 hex>", "op", "argv": [str], "criado_em"}, sem campo a mais; o id é o do arquivo."""
    try:
        pedido = _json(dados)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise Recusa("pedido ilegível (JSON em UTF-8, sem chave repetida)") from None
    if not isinstance(pedido, dict) or set(pedido) != set(CAMPOS_PEDIDO):
        raise Recusa(f"pedido fora do formato: os campos são {', '.join(CAMPOS_PEDIDO)}")
    if type(pedido["versao"]) is not int or pedido["versao"] != 1:
        raise Recusa("versão do pedido desconhecida (esperada 1)")
    if not isinstance(pedido["id"], str) or not ID_RE.fullmatch(pedido["id"]) or pedido["id"] != ident:
        raise Recusa("id do pedido inválido: 32 hexadecimais minúsculos, o mesmo do nome do arquivo")
    if not isinstance(pedido["op"], str) or not isinstance(pedido["criado_em"], str) or len(pedido["criado_em"]) > 64:
        raise Recusa("pedido fora do formato: op e criado_em são textos")
    if not isinstance(pedido["argv"], list) or not all(isinstance(a, str) for a in pedido["argv"]):
        raise Recusa("argv do pedido precisa ser uma lista de textos")
    try:  # o JSON aceita "\ud800": sem esta conferência, o caminho ou o Popen levantariam fora de Recusa e OSError
        for texto in (pedido["op"], *pedido["argv"]):
            texto.encode("utf-8")
    except UnicodeEncodeError:
        raise Recusa("pedido com texto fora do UTF-8 (substituto solto): recusado") from None
    if not _iso_utc(pedido["criado_em"]):
        raise Recusa("pedido fora do formato: criado_em precisa ser data ISO em UTC (contratos, §4)")
    return pedido


def _pedido_vencido(idade: float) -> Recusa:
    return Recusa(f"o pedido esperou {idade:.0f} s na fila e na vez do banco (máximo {IDADE_MAXIMA_S} s): não rodou; "
                  "repita")


def _dentro_do_limite(limite: float) -> None:
    """A conferência da idade do pedido com a vez na mão, antes e depois da cópia conferida do kit (a cópia também
    conta): passou do limite de limite_do_pedido, Recusa sem rodar nada."""
    if time.monotonic() > limite:
        raise _pedido_vencido(IDADE_MAXIMA_S + time.monotonic() - limite)


def limite_do_pedido(pedido: dict, agora: datetime | None = None) -> float:
    """Até quando (relógio monotônico) o pedido ainda pode começar a rodar: criado_em + IDADE_MAXIMA_S (revisão do lote
    2). Já vencido, ou com criado_em adiantado mais que ADIANTADO_S: Recusa ("não rodou"). Assim, a espera somada à
    execução cabe no corte de 120 s do Bash, e o pedido que um cliente morto (Ctrl+C, SIGKILL, o corte) deixou na fila
    não roda depois, sem ninguém para ler a resposta. O adiantado conta como idade zero: não espera além do máximo."""
    idade = ((agora or datetime.now(timezone.utc)) - _data(pedido["criado_em"])).total_seconds()
    if idade < -ADIANTADO_S:
        raise Recusa(f"criado_em está {-idade:.0f} s no futuro (relógio da sessão adiantado?): não rodou; repita")
    if idade > IDADE_MAXIMA_S:
        raise _pedido_vencido(idade)
    return time.monotonic() + IDADE_MAXIMA_S - max(idade, 0.0)


def resposta_de_recusa(ident: str, exc: Exception, inicio: float) -> dict:
    erro = {"error": {"code": "E_PORTEIRO", "message": str(exc)}}
    return {"versao": 1, "id": ident, "codigo": 2, "stdout": "", "stderr": json.dumps(erro, ensure_ascii=False) + "\n",
            "truncado": False, "duracao_s": round(time.monotonic() - inicio, 3)}


# ------------------------------------------------------------------ execução do kit
def ambiente_do_kit(cfg: dict) -> dict:
    """O ambiente mínimo do kit (contratos, §4), mais o que a emenda E1 dos contratos acrescenta: o assinante da
    configuração (FUNDACAO_ASSINANTE, o titular que assina as decisões preparadas; nunca é a identidade da sessão nem
    amplia permissão) e, no WSL, o nome da distribuição (WSL_DISTRO_NAME, só para compor o comando do titular para
    caminho do Linux, wsl.localhost/<distribuição>; o lançador do HOST o passa no env -i do `servir`)."""
    amb = {"FUNDACAO_RAIZ": cfg["raiz"], IDENTIDADE: PREFIXO_SESSAO + cfg["projeto"],
           "FUNDACAO_PROJETO_TRAVADO": cfg["projeto"], "FUNDACAO_PORTEIRO_SERVIDOR": "1",
           "FUNDACAO_ASSINANTE": cfg["assinante"], "PATH": PATH_FIXO}
    distro = os.environ.get("WSL_DISTRO_NAME", "").strip()
    if distro and re.fullmatch(r"[A-Za-z0-9._-]{1,64}", distro):
        amb["WSL_DISTRO_NAME"] = distro
    return amb


def _matar(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)  # o grupo inteiro (start_new_session): o kit e os descendentes
    except (ProcessLookupError, PermissionError, OSError):
        pass


def executar_kit(cfg: dict, argv_kit: list[str], *, pasta_trabalho: str, prazo: float = PRAZO_KIT_S,
                 tetos: tuple[int, int] = (TETO_STDOUT, TETO_STDERR), durante=None, parar=None,
                 antes_de_rodar=None) -> dict:
    """Roda o kit da raiz com o argv montado, a partir da cópia privada conferida (kit_conferido: KitAlterado se a
    árvore não confere), apagada no fim. `durante` é chamado enquanto a cópia é feita e enquanto o kit roda (a trava e
    o sinal de vida seguem renovados); `parar` (Event) encerra antes. `antes_de_rodar`, chamado com a cópia pronta e
    antes de o processo começar, recusa sem rodar nada (a idade do pedido, que conta também a cópia: revisão do lote
    2). Prazo e teto valem para a árvore de processos (grupo próprio)."""
    kit = kit_conferido(cfg["raiz"], cfg["kit_sha256"], pasta_trabalho, durante)
    try:
        if antes_de_rodar is not None:
            antes_de_rodar()
        return _rodar_kit(cfg, kit, argv_kit, pasta_trabalho, prazo, tetos, durante, parar)
    finally:
        shutil.rmtree(os.path.dirname(kit), ignore_errors=True)


def _rodar_kit(cfg: dict, kit: str, argv_kit: list[str], pasta_trabalho: str, prazo: float, tetos: tuple[int, int],
               durante, parar) -> dict:
    """O processo do kit (o pacote em `kit`), com o Python isolado, o ambiente mínimo, o prazo e o teto de saída. O
    pycache_prefix aponta para a pasta de trabalho, onde não há bytecode da cópia: roda a fonte conferida."""
    cmd = [sys.executable or "/usr/bin/python3", "-I", "-B", "-S", "-X", "utf8",
           "-X", f"pycache_prefix={pasta_trabalho}", "-c", BOOTSTRAP, kit, *argv_kit]
    inicio = time.monotonic()
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            cwd=pasta_trabalho, env=ambiente_do_kit(cfg), start_new_session=True, close_fds=True)
    lidos, cortado = {"out": bytearray(), "err": bytearray()}, []

    def ler(nome: str, fluxo, teto: int) -> None:
        try:
            while bloco := fluxo.read1(1 << 16):
                falta = teto - len(lidos[nome])
                lidos[nome] += bloco[:max(falta, 0)]
                if len(bloco) > falta:  # passou do teto: guarda até ele e encerra a árvore
                    cortado.append(nome)
                    _matar(proc)
                    return
        except (OSError, ValueError):
            pass

    leitores = [threading.Thread(target=ler, args=a, daemon=True)
                for a in (("out", proc.stdout, tetos[0]), ("err", proc.stderr, tetos[1]))]
    for t in leitores:
        t.start()
    motivo = None
    while True:
        try:
            proc.wait(timeout=INTERVALO_S)
            break
        except subprocess.TimeoutExpired:
            pass
        if durante is not None:
            try:
                durante()
            except OSError:  # renovar a trava ou o sinal de vida falhou: o kit segue até o fim ou o prazo
                pass
        if time.monotonic() - inicio > prazo:
            motivo = f"o kit passou do prazo de {prazo:.0f} s: o processo e os descendentes foram encerrados"
        elif parar is not None and parar.is_set():
            motivo = "o porteiro está encerrando: o pedido não terminou"
        if motivo:
            _matar(proc)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            break
    _matar(proc)  # o que o kit deixou rodando (e poderia segurar as saídas)
    for t in leitores:
        t.join(timeout=5)
    for fluxo in (proc.stdout, proc.stderr):
        fluxo.close()
    stdout = bytes(lidos["out"]).decode("utf-8", "replace")
    stderr = bytes(lidos["err"]).decode("utf-8", "replace")
    codigo = proc.returncode if proc.returncode is not None and proc.returncode >= 0 else 2
    if cortado and not motivo:
        motivo = "saída do kit acima do teto: guardado até o teto, e o processo foi encerrado"
    if motivo:
        codigo = 2
        stderr += json.dumps({"error": {"code": "E_PORTEIRO", "message": motivo}}, ensure_ascii=False) + "\n"
    return {"codigo": codigo, "stdout": stdout, "stderr": stderr, "truncado": bool(cortado),
            "duracao_s": round(time.monotonic() - inicio, 3)}


def _versao(texto) -> tuple[int, ...] | None:
    m = VERSAO_RE.fullmatch(texto) if isinstance(texto, str) else None
    return tuple(int(n) for n in m.groups()) if m else None


def apertar_mao(cfg: dict, rodar) -> dict:
    """O `status` do kit da raiz no modo travado prova a trava: projeto_travado, identidade sessao-<p>, só o projeto
    nas listagens e KIT_VERSION >= 1.7.10. Sem a prova: Recusa (o porteiro recusa todo pedido)."""
    r = rodar(["--raiz", cfg["raiz"], "status"])
    falhas = []
    try:
        st = json.loads(r["stdout"]) if r["codigo"] == 0 else None
    except ValueError:
        st = None
    if not isinstance(st, dict):
        falhas.append(f"o status não respondeu (código {r['codigo']}): {r['stderr'].strip()[:300]}")
        st = {}
    p = cfg["projeto"]
    if st and st.get("projeto_travado") != p:
        falhas.append(f"projeto_travado={st.get('projeto_travado')!r}, esperado {p!r}")
    versao = _versao(st.get("kit_version"))
    if st and (versao is None or versao < VERSAO_MINIMA):
        falhas.append(f"kit_version={st.get('kit_version')!r}: precisa ser 1.7.10 ou mais nova")
    if st and st.get("identidade") != PREFIXO_SESSAO + p:
        falhas.append(f"identidade={st.get('identidade')!r}, esperada {PREFIXO_SESSAO + p!r}")
    autorizados = st.get("projetos_autorizados")
    if st and (not isinstance(autorizados, list) or not set(autorizados) <= {p}):
        falhas.append("o status listou outro projeto")
    if falhas:
        raise Recusa("o kit da raiz não prova a trava (" + "; ".join(falhas) + "): atualize a fundação para a 1.7.10 "
                     "ou mais nova e refaça o preparo do projeto")
    return {"kit_version": st["kit_version"], "projeto_travado": p}


# ------------------------------------------------------------------ trava do banco (marcador + flock)
def ler_marcador(pasta_estado: str) -> dict | None:
    """O marcador state/banco.trava; None sem marcador; {"ilegivel": motivo} quando não dá para confiar nele."""
    try:
        dados = _ler_arquivo(os.path.join(pasta_estado, MARCADOR), 4096)
    except Recusa as exc:
        return None if not os.path.lexists(os.path.join(pasta_estado, MARCADOR)) else {"ilegivel": str(exc)}
    try:
        m = _json(dados)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return {"ilegivel": "JSON ilegível"}
    campos = ("lado", "host", "pid", "desde", "renovada_em")
    if not (isinstance(m, dict) and set(m) == set(campos) and m["lado"] in LADOS and isinstance(m["host"], str)
            and type(m["pid"]) is int and _data(m["desde"]) and _data(m["renovada_em"])):
        return {"ilegivel": "fora da forma do marcador"}
    return m


class TravaDoBanco:
    """Segura o banco pelo lado do Ubuntu enquanto o porteiro roda (contratos, §4). O marcador state/banco.trava vale
    para o Windows (o kit de lá recusa abrir); entre os porteiros, flock em arquivos no ext4 da casa: `donos`
    compartilhado do início ao fim (o último a sair tira o marcador) e `vez` exclusivo durante cada execução do kit."""

    def __init__(self, raiz: str, pasta_local: Path):
        self.estado = os.path.join(raiz, "state")
        self.marcador = os.path.join(self.estado, MARCADOR)
        chave = hashlib.sha256(os.path.realpath(raiz).encode("utf-8")).hexdigest()[:16]
        self.donos = os.path.join(str(pasta_local), f"banco-{chave}.donos")
        self.vez = os.path.join(str(pasta_local), f"banco-{chave}.vez")
        self.fd_donos = None
        self.segura = False
        self.desde = None
        self.ultima = 0.0

    def _abrir_trava(self, caminho: str) -> int:
        return os.open(caminho, os.O_RDWR | os.O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0o600)

    def tomar(self) -> str | None:
        """Grava o marcador do Ubuntu; devolve o motivo quando não dá (marcador do Windows, ilegível, sem state/)."""
        import fcntl
        if self.fd_donos is None:
            fd = self._abrir_trava(self.donos)
            fcntl.flock(fd, fcntl.LOCK_SH)  # espera só um porteiro que esteja saindo (exclusivo por um instante)
            self.fd_donos = fd
        atual = ler_marcador(self.estado)
        if atual is not None and ("ilegivel" in atual or atual["lado"] != "ubuntu"):
            self._largar()
            if "ilegivel" in atual:
                return (f"o marcador do banco ({self.marcador}) não é legível ({atual['ilegivel']}): confira-o; "
                        "o titular o tira com `python -m fundacao banco destravar --confirmar`")
            return (f"o banco está em uso pelo {atual['lado']} (host {atual['host']}, pid {atual['pid']}, renovado em "
                    f"{atual['renovada_em']}): feche o que o usa lá e repita o pedido")
        self.desde = atual["desde"] if atual else agora_iso()
        try:
            self._gravar()
        except OSError as exc:
            self._largar()
            return f"não deu para gravar o marcador do banco em state/ ({exc.strerror or type(exc).__name__})"
        self.segura = True
        return None

    def _gravar(self) -> None:
        st = os.lstat(self.estado)
        if _ligacao(st) or not stat.S_ISDIR(st.st_mode):
            raise OSError(f"{self.estado} é ligação ou não é pasta")
        dados = json.dumps({"lado": "ubuntu", "host": socket.gethostname(), "pid": os.getpid(), "desde": self.desde,
                            "renovada_em": agora_iso()}, ensure_ascii=False).encode("utf-8")
        temp = os.path.join(self.estado, f".{MARCADOR}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o644)
        try:
            try:
                vista = memoryview(dados)
                while vista:
                    vista = vista[os.write(fd, vista):]
            finally:
                os.close(fd)
            os.replace(temp, self.marcador)  # troca o nome: ligação no lugar sai, sem seguir para o destino dela
        except OSError:  # disco cheio, o Windows com o marcador aberto: o temporário não fica em state/
            try:
                os.unlink(temp)
            except OSError:
                pass
            raise
        self.ultima = time.monotonic()

    def renovar(self, forcar: bool = False) -> str | None:
        """Renova a cada RENOVAR_S segundos; o marcador que mudou de lado (ou ficou ilegível) faz largar a trava. Se a
        gravação falha, a próxima tentativa espera RETENTAR_S segundos (não a cada volta do laço)."""
        if not self.segura or (not forcar and time.monotonic() - self.ultima < RENOVAR_S):
            return None
        atual = ler_marcador(self.estado)
        if atual is not None and ("ilegivel" in atual or atual["lado"] != "ubuntu"):
            self.segura = False
            return "o marcador do banco mudou de lado durante a sessão: os pedidos esperam a trava de novo"
        try:
            self._gravar()
        except OSError as exc:
            self.ultima = time.monotonic() - RENOVAR_S + RETENTAR_S
            return f"não deu para renovar o marcador do banco ({exc})"
        return None

    def _largar(self) -> None:
        if self.fd_donos is not None:
            os.close(self.fd_donos)  # fechar solta o flock
            self.fd_donos = None
        self.segura = False

    def soltar(self) -> None:
        """Sai da lista de donos; o último porteiro a sair tira o marcador do Ubuntu."""
        import fcntl
        if self.fd_donos is None:
            return
        try:
            fcntl.flock(self.fd_donos, fcntl.LOCK_UN)
            try:
                fcntl.flock(self.fd_donos, fcntl.LOCK_EX | fcntl.LOCK_NB)
                ultimo = True
            except BlockingIOError:
                ultimo = False
            atual = ler_marcador(self.estado) if ultimo and self.segura else None
            if atual is not None and "ilegivel" not in atual and atual["lado"] == "ubuntu":
                try:
                    os.unlink(self.marcador)
                except FileNotFoundError:
                    pass
        finally:
            self._largar()

    @contextmanager
    def na_vez(self, espera: float | None = None, durante=None, parar=None):
        """Exclusivo entre os porteiros desta raiz durante uma execução do kit (o banco não abre por dois ao mesmo
        tempo, nem do mesmo lado: o SQLite sobre o DrvFs não tem trava confiável entre processos). Enquanto espera
        (até `espera`, padrão ESPERA_VEZ_S; quem atende um pedido passa o que ainda falta para a idade máxima dele),
        chama `durante` — a trava e o sinal de vida seguem renovados, e o cliente não desiste de um pedido que já saiu
        da fila e vai rodar (revisão do lote 2) — e desiste se `parar` (Event) for marcado."""
        import fcntl
        fd = self._abrir_trava(self.vez)
        try:
            limite = time.monotonic() + (ESPERA_VEZ_S if espera is None else espera)
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() > limite:
                        raise VezOcupada("o banco está ocupado por outro porteiro há mais que o prazo: o pedido não "
                                         "rodou; repita") from None
                    if parar is not None and parar.is_set():
                        raise Recusa("o porteiro está encerrando: o pedido não rodou") from None
                    if durante is not None:
                        try:
                            durante()
                        except OSError:
                            pass
                    time.sleep(0.05)
            yield
        finally:
            os.close(fd)


# ------------------------------------------------------------------ fila
def _pasta_filha(fd_pai: int, nome: str) -> int:
    """Descritor da pasta `nome` dentro de `fd_pai`, criada se faltar; ligação no lugar: Recusa."""
    try:
        os.mkdir(nome, 0o755, dir_fd=fd_pai)
    except FileExistsError:
        pass
    try:
        return os.open(nome, os.O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC, dir_fd=fd_pai)
    except OSError as exc:
        raise Recusa(f"a fila do porteiro tem {nome} que não é pasta comum ({exc.strerror})") from None


class Fila:
    """A fila de projects/<p>/.porteiro: descritores de pedidos/ e respostas/ abertos uma vez, sem seguir ligação."""

    def __init__(self, pasta: str):
        self.pasta = os.path.normpath(pasta)
        self.pedidos = self.respostas = None
        self.ultima_vida = self.ultima_limpeza = 0.0

    def abrir(self) -> None:
        pai, nome = os.path.split(self.pasta)
        try:
            fd_pai = os.open(pai, os.O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        except OSError as exc:
            raise Recusa(f"a pasta do projeto ({pai}) não abriu sem seguir ligação ({exc.strerror})") from None
        try:
            fd_fila = _pasta_filha(fd_pai, nome)
        finally:
            os.close(fd_pai)
        try:
            self.pedidos = _pasta_filha(fd_fila, "pedidos")
            self.respostas = _pasta_filha(fd_fila, "respostas")
        finally:
            os.close(fd_fila)
        self.limpar(tudo=True)

    def listar(self) -> list[str]:
        return sorted(os.listdir(self.pedidos))

    def ler(self, nome: str) -> bytes:
        try:
            return _ler_arquivo(nome, TETO_PEDIDO, dir_fd=self.pedidos)
        except Recusa as exc:
            raise Recusa(f"pedido recusado: {exc}") from None

    def retirar(self, nome: str) -> bool | None:
        """Tira o nome da fila (ligação sai como ligação); pasta só se estiver vazia. True: tirou; None: o nome já
        não estava (o cliente desistiu e o tirou antes: quem tira primeiro decide se o pedido roda); False: ficou."""
        try:
            os.unlink(nome, dir_fd=self.pedidos)
        except FileNotFoundError:
            return None
        except (IsADirectoryError, PermissionError):
            try:
                os.rmdir(nome, dir_fd=self.pedidos)
            except OSError:
                return False
        except OSError:
            return False
        return True

    def _gravar(self, nome: str, dados: bytes) -> None:
        temp = f".{nome}.{secrets.token_hex(4)}.tmp"
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o644, dir_fd=self.respostas)
        try:
            try:
                vista = memoryview(dados)
                while vista:
                    vista = vista[os.write(fd, vista):]
            finally:
                os.close(fd)
            os.replace(temp, nome, src_dir_fd=self.respostas, dst_dir_fd=self.respostas)
        except OSError:
            try:
                os.unlink(temp, dir_fd=self.respostas)
            except OSError:
                pass
            raise

    def responder(self, ident: str, resposta: dict) -> bool:
        """Grava respostas/<id>.json (temporário exclusivo e troca); resposta que já existe não é trocada. Texto que
        não codifica (substituto solto numa mensagem) vira "?": a resposta sai sempre."""
        nome = f"{ident}.json"
        try:
            os.stat(nome, dir_fd=self.respostas, follow_symlinks=False)
            return False
        except FileNotFoundError:
            pass
        self._gravar(nome, json.dumps(resposta, ensure_ascii=False).encode("utf-8", "replace"))
        return True

    def vida(self, estado: str, forcar: bool = False) -> None:
        if not forcar and time.monotonic() - self.ultima_vida < VIDA_S:
            return
        self._gravar(VIDA, json.dumps({"pid": os.getpid(), "renovada_em": agora_iso(), "estado": estado}).encode())
        self.ultima_vida = time.monotonic()

    def limpar(self, tudo: bool = False) -> None:
        """Respostas e temporários com mais de TTL_RESPOSTA_S (ou todos, na abertura e no fim)."""
        if not tudo and time.monotonic() - self.ultima_limpeza < 60:
            return
        self.ultima_limpeza = time.monotonic()
        for nome in os.listdir(self.respostas):
            if not (NOME_PEDIDO.fullmatch(nome) or (nome.startswith(".") and nome.endswith(".tmp"))):
                continue
            try:
                if tudo or time.time() - os.stat(nome, dir_fd=self.respostas, follow_symlinks=False).st_mtime > \
                        TTL_RESPOSTA_S:
                    os.unlink(nome, dir_fd=self.respostas)
            except OSError:
                pass

    def fechar(self) -> None:
        if self.respostas is None:
            return
        try:
            os.unlink(VIDA, dir_fd=self.respostas)
        except OSError:
            pass
        self.limpar(tudo=True)
        for fd in (self.pedidos, self.respostas):
            os.close(fd)
        self.pedidos = self.respostas = None


# ------------------------------------------------------------------ o porteiro
def processo_vivo(pid: int) -> bool:
    """O processo do lançador ainda roda. Fora de 2..PID_MAXIMO nunca conta como vivo: os.kill(0, 0) e os.kill(-1, 0)
    sempre dão certo (grupo e todos os processos), o init nunca morre, e acima do pid_t o os.kill levanta
    OverflowError, que escaparia do laço de `servir` com traceback (revisões do lote 2)."""
    if not 1 < pid <= PID_MAXIMO:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, OverflowError):
        return False
    except PermissionError:
        return True
    try:  # zumbi (terminou e ninguém o recolheu) conta como morto
        with open(f"/proc/{pid}/stat", "rb") as arq:
            return arq.read().rsplit(b")", 1)[1].split()[0] != b"Z"
    except (OSError, IndexError):
        return True


def _pasta_privada(caminho: Path) -> None:
    """A pasta e as de cima, a partir da casa (~/.fundacao, ~/.fundacao/porteiro, ...), criadas com 0700."""
    casa = Path.home()
    partes = Path(caminho).relative_to(casa).parts
    atual = casa
    for parte in partes:
        atual = atual / parte
        try:
            atual.mkdir(mode=0o700)
        except FileExistsError:
            pass
        st = os.lstat(atual)
        if _ligacao(st) or not stat.S_ISDIR(st.st_mode):
            raise Recusa(f"{atual} é ligação ou não é pasta")


def _tomar_unico(caminho: Path) -> int:
    """flock exclusivo, sem esperar, em ~/.fundacao/porteiro/<p>/porteiro.trava: um porteiro por projeto nesta casa. O
    segundo sai com Recusa antes de tocar a fila, e não apaga as respostas nem o sinal de vida do primeiro (revisão do
    lote 2, sonda S6; o lançador do HOST já recusa a segunda sessão do projeto: isto é defesa em profundidade)."""
    import fcntl
    fd = os.open(caminho, os.O_RDWR | os.O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise Recusa("já há um porteiro deste projeto de pé (outra sessão do projeto aberta): feche-a e abra de "
                     "novo") from None
    return fd


def _uso_das_pastas(pastas: list[str], proc: str = "/proc") -> dict[str, list[str]] | None:
    """Quem ainda usa cada pasta de `pastas`, lido em /proc: o processo com a pasta atual dentro dela ou que a cita num
    argumento. O kit roda com a pasta atual e o pycache_prefix na pasta de trabalho, em sessão própria: morto o porteiro
    por SIGKILL, o kit segue vivo, órfão, dentro dela (reconferência 3 do lote 2). A regra é a do limpar-porteiro do
    HOST (preparo_host._uso_da_pasta_do_porteiro). Devolve {pasta: [pid, ...]}, só das usadas; None com /proc ilegível
    (na dúvida, nada sai). O processo que saiu durante a leitura não conta; o protegido (sem acesso à pasta atual, como
    o ssh-agent) conta só pelos argumentos, como no HOST."""
    try:
        pids = sorted((n for n in os.listdir(proc) if n.isascii() and n.isdigit()), key=int)
    except OSError:
        return None
    prefixos = {p: {p.rstrip(os.sep) + os.sep, os.path.realpath(p).rstrip(os.sep) + os.sep} for p in pastas}
    uso: dict[str, list[str]] = {}
    for pid in pids:
        base = os.path.join(proc, pid)
        try:
            with open(os.path.join(base, "cmdline"), "rb") as arq:
                args = [a.decode("utf-8", "surrogateescape") + os.sep for a in arq.read(1 << 20).split(b"\0") if a]
        except OSError:
            args = []  # saiu durante a leitura (ou é de outra conta, com o /proc restrito)
        try:
            atual = os.readlink(os.path.join(base, "cwd")) + os.sep
        except OSError:
            atual = ""  # protegido (como o ssh-agent) ou já saiu: conta só pelos argumentos
        for pasta, pref in prefixos.items():
            if any(atual.startswith(p) or any(p in a for a in args) for p in pref):
                uso.setdefault(pasta, []).append(pid)
    return uso


def _limpar_trabalho_antigo(pasta: Path, proc: str = "/proc") -> dict:
    """As pastas trabalho-* que um porteiro morto sem encerrar deixou (o SIGKILL no meio de um pedido deixa a cópia do
    kit). Só com a trava de um porteiro por projeto na mão: nenhuma delas é de um porteiro de pé (revisão do lote 2).
    A que um processo ainda usa fica (o kit órfão do porteiro morto, _uso_das_pastas), e com /proc ilegível nenhuma
    sai, como no limpar-porteiro do HOST (reconferência 3 do lote 2): sai numa partida seguinte, sem quem a usa.
    Ligação nunca é seguida. Devolve {"apagadas", "mantidas", "motivo"} (o motivo, só com alguma mantida)."""
    candidatas = []
    for nome in sorted(os.listdir(pasta)):
        if not nome.startswith("trabalho-"):
            continue
        caminho = os.path.join(pasta, nome)
        try:
            st = os.lstat(caminho)
        except OSError:
            continue
        if stat.S_ISDIR(st.st_mode) and not _ligacao(st):
            candidatas.append(caminho)
    saida = {"apagadas": [], "mantidas": [], "motivo": None}
    uso = _uso_das_pastas(candidatas, proc) if candidatas else {}
    if uso is None:
        nomes = [os.path.basename(c) for c in candidatas]
        return {**saida, "mantidas": nomes, "motivo": "/proc ilegível: não dá para saber se um processo ainda usa as "
                f"pastas de trabalho de um porteiro encerrado (na dúvida, nada sai): {', '.join(nomes)}"}
    motivos = []
    for caminho in candidatas:
        nome = os.path.basename(caminho)
        if caminho in uso:
            saida["mantidas"].append(nome)
            motivos.append(f"{nome} (em uso pelo processo {', '.join(uso[caminho][:3])}: o kit órfão de um porteiro "
                           "morto por SIGKILL?)")
            continue
        shutil.rmtree(caminho, ignore_errors=True)
        if os.path.lexists(caminho):
            saida["mantidas"].append(nome)
            motivos.append(f"{nome} (não saiu inteira)")
        else:
            saida["apagadas"].append(nome)
    if motivos:
        saida["motivo"] = "pastas de trabalho de um porteiro encerrado mantidas: " + "; ".join(motivos)
    return saida


class Porteiro:
    def __init__(self, caminho_config, fila: str, pid_lancador: int):
        self.caminho_config = str(caminho_config)
        self.cfg, self.sha_config = carregar_config(self.caminho_config)
        esperado = os.path.join(self.cfg["raiz"], "projects", self.cfg["projeto"], ".porteiro")
        if os.path.normpath(fila) != os.path.normpath(esperado):
            raise Recusa(f"a fila ({fila}) não é a do projeto da configuração ({esperado})")
        self.pid_lancador = pid_lancador
        self.fila = Fila(fila)
        self.local = Path.home() / ".fundacao" / "porteiro"
        self.privada = self.local / self.cfg["projeto"]
        self.trava = TravaDoBanco(self.cfg["raiz"], self.local)
        self.parar = threading.Event()
        self.aperto = None
        self.recusa_permanente = None
        self.trabalho = None
        self.limpeza = None
        self.unico = None
        self.iniciado = False
        self.ignorados: set[str] = set()

    # ---- estado
    def estado(self) -> str:
        """No sinal de vida: "iniciando" (o primeiro aperto de mão ainda corre), "pronto", "aguardando" (falta a trava
        do banco, a vez ou o aperto de mão: o próximo pedido tenta de novo) ou "recusando" (o aperto de mão falhou:
        todo pedido é recusado até a sessão ser reaberta)."""
        if not self.iniciado:
            return "iniciando"
        if self.recusa_permanente:
            return "recusando"
        return "pronto" if self.aperto and self.trava.segura else "aguardando"

    def reconferir_config(self) -> None:
        """porteiro.json relido, antes de cada pedido: o mesmo SHA-256 do início."""
        _cfg, sha = carregar_config(self.caminho_config)
        if sha != self.sha_config:
            raise Recusa("porteiro.json mudou durante a sessão: feche e reabra a sessão pelo lançador")

    def reconferir(self) -> None:
        """A configuração relida e a árvore do kit da raiz (antes de tomar a trava do banco). Em cada execução, a
        conferência da árvore é a da cópia privada (executar_kit)."""
        self.reconferir_config()
        atual = sha256_do_kit(self.cfg["raiz"])
        if atual != self.cfg["kit_sha256"]:
            raise _kit_alterado(atual, self.cfg["kit_sha256"])

    def garantir_pronto(self, espera: float | None = None) -> None:
        """A trava do banco e o aperto de mão (uma vez). O que não deu fica para o próximo pedido — inclusive a vez do
        banco ocupada e o kit alterado, que são passageiros —; o aperto que falhou vale para a sessão inteira. Num
        pedido, `espera` é o que ainda falta para a idade máxima dele (a vez não é esperada além disso)."""
        if self.recusa_permanente:
            raise Recusa(self.recusa_permanente)
        if self.trava.segura and self.aperto is not None:
            return
        self.reconferir()
        if not self.trava.segura:
            motivo = self.trava.tomar()
            if motivo:
                raise Recusa(motivo)
        if self.aperto is None:
            try:
                with self.trava.na_vez(espera, durante=self.manter, parar=self.parar):
                    self.aperto = apertar_mao(self.cfg, self.rodar)
            except (VezOcupada, KitAlterado):
                raise  # o próximo pedido tenta o aperto de novo (revisão do lote 2)
            except Recusa as exc:
                self.recusa_permanente = str(exc)
                self.trava.soltar()  # sem o aperto, nada abre o banco: o Windows não fica travado à toa
                raise

    def manter(self) -> None:
        self.trava.renovar()
        self.fila.vida(self.estado())

    def rodar(self, argv_kit: list[str], antes_de_rodar=None) -> dict:
        return executar_kit(self.cfg, argv_kit, pasta_trabalho=self.trabalho, durante=self.manter, parar=self.parar,
                            antes_de_rodar=antes_de_rodar)

    # ---- pedidos
    def atender(self, ident: str, dados: bytes) -> tuple[dict, str | None]:
        inicio, op = time.monotonic(), None
        try:
            pedido = validar_pedido(dados, ident)
            op = pedido["op"] if pedido["op"] in ("fundacao", *OPERACOES_1711) else "desconhecida"
            if pedido["op"] in OPERACOES_1711:
                raise Recusa(f"a operação {pedido['op']} fica para a 1.7.11: nesta versão o porteiro só atende "
                             "`fundacao`")
            if pedido["op"] != "fundacao":
                raise Recusa("operação desconhecida: nesta versão o porteiro só atende `fundacao`")
            limite = limite_do_pedido(pedido)  # vencido: não roda (revisão do lote 2)
            self.garantir_pronto(espera=max(0.0, limite - time.monotonic()))
            argv_kit = argv_do_kit(pedido["argv"], self.cfg)
            with self.trava.na_vez(max(0.0, limite - time.monotonic()), durante=self.manter, parar=self.parar):
                self.reconferir_config()
                _dentro_do_limite(limite)  # com a vez na mão; e de novo com a cópia pronta, antes de o kit começar
                # O que roda é a cópia privada feita no mesmo passe da conferência (executar_kit): a troca no kit
                # da raiz antes da cópia é recusada (KitAlterado); depois dela, não chega à execução.
                rodado = self.rodar(argv_kit, antes_de_rodar=lambda: _dentro_do_limite(limite))
                return {"versao": 1, "id": ident, **rodado}, op
        except (Recusa, OSError) as exc:  # erro de arquivo também volta como resposta: o cliente não espera à toa
            return resposta_de_recusa(ident, exc, inicio), op

    def processar(self, nome: str) -> None:
        if nome.startswith(".") or nome in self.ignorados:
            return  # temporário do cliente (ainda sendo gravado) ou entrada que não sai da fila
        m = NOME_PEDIDO.fullmatch(nome)
        if not m:
            if nome.endswith(".json"):  # nome fora da forma: sem id não há resposta; sai da fila
                if self.fila.retirar(nome) is False:
                    self.ignorados.add(nome)
                self.registrar(None, None, 2, 0.0)
            return
        ident, inicio, op = m.group(1), time.monotonic(), None
        try:
            dados = self.fila.ler(nome)
        except Recusa as exc:
            resposta = resposta_de_recusa(ident, exc, inicio)
        else:
            resposta = None
        # Quem tira o nome da fila primeiro decide se o pedido roda, também quando a leitura falhou (revisão do lote 2).
        retirado = self.fila.retirar(nome)
        if retirado is None:
            return  # o cliente que desistiu (ou outro porteiro) tirou primeiro: nem roda nem responde
        if retirado is False:  # o nome ficou (unlink recusado): não roda, e o "não rodou" do cliente vale
            self.ignorados.add(nome)
            if resposta is None:
                resposta = resposta_de_recusa(ident, Recusa("o pedido não saiu da fila: não rodou; repita"), inicio)
        if resposta is None:
            try:
                resposta, op = self.atender(ident, dados)
            except Exception as exc:  # última rede: o pedido hostil ou um defeito não derrubam o porteiro
                motivo = Recusa(f"erro interno do porteiro ({type(exc).__name__}): confira o efeito antes de repetir")
                resposta = resposta_de_recusa(ident, motivo, inicio)
        self.fila.responder(ident, resposta)
        self.registrar(ident, op, resposta["codigo"], resposta["duracao_s"])

    def registrar(self, ident, op, codigo: int, duracao: float) -> None:
        """Uma linha por pedido, sem conteúdo (nem argv, nem saída): id, op, código, duração e quando."""
        linha = json.dumps({"id": ident, "op": op, "codigo": codigo, "duracao_s": duracao, "em": agora_iso()})
        try:
            fd = os.open(self.privada / "registro.jsonl",
                         os.O_WRONLY | os.O_APPEND | os.O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0o600)
            try:
                os.write(fd, (linha + "\n").encode("utf-8"))
            finally:
                os.close(fd)
        except OSError as exc:
            sys.stderr.write(json.dumps({"aviso": f"registro do porteiro não gravado ({exc})"}) + "\n")

    # ---- ciclo
    def abrir(self) -> None:
        """As pastas privadas, a trava de um porteiro por projeto (antes de tocar a fila), a limpeza das pastas de
        trabalho de um porteiro morto (salvo a que um processo ainda usa: self.limpeza), a pasta de trabalho (privada:
        o pycache_prefix, a pasta atual do kit e as cópias conferidas dele) e a fila."""
        _pasta_privada(self.local)
        _pasta_privada(self.privada)
        self.unico = _tomar_unico(self.privada / "porteiro.trava")
        self.limpeza = _limpar_trabalho_antigo(self.privada)
        self.trabalho = tempfile.mkdtemp(prefix="trabalho-", dir=self.privada)
        self.fila.abrir()

    def servir(self) -> int:
        signal.signal(signal.SIGTERM, lambda *_: self.parar.set())
        signal.signal(signal.SIGHUP, lambda *_: self.parar.set())
        signal.signal(signal.SIGINT, signal.SIG_IGN)  # o Ctrl+C da sessão não derruba o porteiro
        try:
            os.setsid()  # sem terminal de controle (o lançador também pode iniciá-lo assim)
        except OSError:
            pass
        try:
            self.abrir()
        except (Recusa, OSError) as exc:
            sys.stderr.write(json.dumps({"error": {"code": "E_PORTEIRO", "message": str(exc)}}, ensure_ascii=False)
                             + "\n")
            self.encerrar()
            return 2
        try:
            if self.limpeza and self.limpeza["mantidas"]:  # só aviso: a sessão segue; a pasta sai numa partida seguinte
                sys.stderr.write(json.dumps({"aviso": {"code": "W_PORTEIRO_TRABALHO_MANTIDO",
                                                       "message": self.limpeza["motivo"]}}, ensure_ascii=False) + "\n")
            try:
                self.garantir_pronto()
            except (Recusa, OSError) as exc:  # segue de pé, com o motivo (o cliente não espera à toa)
                codigo = "W_PORTEIRO_RECUSANDO" if self.recusa_permanente else "W_PORTEIRO_AGUARDANDO"  # passageiro
                sys.stderr.write(json.dumps({"aviso": {"code": codigo, "message": str(exc)}}, ensure_ascii=False)
                                 + "\n")
            self.iniciado = True
            self.fila.vida(self.estado(), forcar=True)
            while not self.parar.is_set() and processo_vivo(self.pid_lancador):
                try:
                    self.manter()
                    self.fila.limpar()
                    for nome in self.fila.listar():
                        if self.parar.is_set():
                            break
                        self.processar(nome)
                except OSError as exc:  # um pedido ou a fila falhou: avisa e segue atendendo
                    sys.stderr.write(json.dumps({"aviso": {"code": "W_PORTEIRO_FILA", "message": str(exc)}},
                                                ensure_ascii=False) + "\n")
                self.parar.wait(INTERVALO_S)
        finally:
            self.encerrar()
        return 0

    def encerrar(self) -> None:
        try:
            self.fila.fechar()
        except OSError:
            pass
        try:
            self.trava.soltar()
        except OSError:
            pass
        if self.trabalho:
            shutil.rmtree(self.trabalho, ignore_errors=True)
        if self.unico is not None:  # por último: o porteiro seguinte só limpa depois que este terminou
            os.close(self.unico)
            self.unico = None


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):  # nome fora do UTF-8 numa mensagem sai escapado, sem derrubar a saída
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8", errors="backslashreplace")
    p = argparse.ArgumentParser(prog="porteiro.py", allow_abbrev=False,
                                description="Porteiro da sessão de projeto da fundação no Ubuntu (1.7.10).")
    sub = p.add_subparsers(dest="acao", required=True)
    s = sub.add_parser("servir", allow_abbrev=False)
    s.add_argument("--config", required=True)
    s.add_argument("--fila", required=True)
    s.add_argument("--pid-lancador", type=int, required=True)
    c = sub.add_parser("conferir", allow_abbrev=False)
    c.add_argument("--config", required=True)
    args = p.parse_args(argv)
    if args.acao == "conferir":
        res = conferir(args.config)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["ok"] else 2
    if not 1 < args.pid_lancador <= PID_MAXIMO:  # 0, -1 e 1 (init) nunca morrem; acima do pid_t, OverflowError
        print(json.dumps({"error": {"code": "E_PORTEIRO", "message": "pid do lançador inválido (precisa estar entre 2 "
                                    f"e {PID_MAXIMO}): {args.pid_lancador}"}}, ensure_ascii=False), file=sys.stderr)
        return 2
    if os.name != "posix" or not hasattr(os, "killpg") or os.open not in os.supports_dir_fd:
        print(json.dumps({"error": {"code": "E_PORTEIRO", "message": "o porteiro roda só no Linux (WSL2)"}},
                         ensure_ascii=False), file=sys.stderr)
        return 2
    try:
        porteiro = Porteiro(args.config, args.fila, args.pid_lancador)
    except (Recusa, OSError) as exc:
        print(json.dumps({"error": {"code": "E_PORTEIRO", "message": str(exc)}}, ensure_ascii=False), file=sys.stderr)
        return 2
    return porteiro.servir()


if __name__ == "__main__":
    sys.exit(main())
