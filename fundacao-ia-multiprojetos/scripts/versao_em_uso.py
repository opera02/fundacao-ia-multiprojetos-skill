#!/usr/bin/env python3
"""Versão em uso de um projeto (escopo 0.6 da 1.7.10; desenho §5.4): o que roda fora da proteção do sandbox — as
tarefas agendadas e os servidores — roda de `<raiz>/em-uso/<projeto>/atual/`, separada da pasta que a IA edita e
trocada só por promoção aceita pelo titular, com a lista dos arquivos e o SHA-256 de cada um.

  python versao_em_uso.py propor   --raiz R --projeto P --de <pasta de trabalho em projects/P> --lista <globs>
                                   --saida <projects/P/outputs/....json>
  python versao_em_uso.py promover --raiz R --projeto P --proposta <arq> --proposta-sha256 <h> --decisao <arq>
  python versao_em_uso.py pedir-volta --raiz R --projeto P --saida <projects/P/outputs/....json> --motivo "..."
                                   [--para <nome em anteriores/>]
  python versao_em_uso.py voltar   --raiz R --projeto P --pedido <arq> --pedido-sha256 <h> --decisao <arq>
  python versao_em_uso.py conferir --raiz R --projeto P

- `propor` (a IA, na sessão do projeto): os arquivos da pasta de trabalho que casam a lista de globs (um por linha,
  relativos à pasta, `**` atravessa pastas, `!` exclui, `#` comenta), com tamanho e SHA-256, e a diferença para a
  versão em uso atual quando ela é legível dali. Não segue ligação; deixa de fora, com o motivo, nome forte e pasta de
  segredo (a regra única, `regras_de_segredo.py`, com o padrão forte valendo também para o exemplo, como nos perfis do
  host: segredo vai pelo cofre do porteiro, nunca pela proposta), vínculo físico e as pastas que o manifesto ignora
  (`.git`, `__pycache__`, `.venv`, `node_modules`...: dependência se instala na versão em uso), a pasta que não se
  lista e o nome com caractere de controle, de formatação, separador de linha ou fora do UTF-8 (o `promover` recusa a
  proposta com ele no item ou na origem, e a decisão com ele no nome: vão para o manifesto; revisão 3 da correção do
  KIT-F1), com o motivo. A proposta, com a data e a âncora da versão em uso (`manifesto_em_uso`, o SHA-256 do manifesto
  dela, e `ultima_troca`, o da última promoção ou volta do registro: lidos de `em-uso/` ou, onde ele fica fora da
  leitura — a sessão do Ubuntu —, da cópia `outputs/versao/EM-USO-ATUAL.json` que o `promover` e o `voltar` gravam),
  fica em `outputs/` do projeto, para o aceite
  (`python -m fundacao decisao preparar --tipo aceite --entrega outputs/...`).
- `promover` (o titular, no terminal dele, fora do Claude): confere a proposta pelo SHA-256 informado, a decisão pelo
  kit da raiz (`python -m fundacao decisao verificar`, em Python isolado com só a raiz no caminho de importação, com a
  identidade do terminal do titular) — aceite, assinado, sobre essa proposta e esse SHA-256 —, copia só os arquivos
  listados pela cópia única da skill (`copia_segura.copiar_conferindo`: sem seguir ligação, descendo da pasta do
  projeto por descritor no POSIX, sem vínculo físico, conferindo o SHA-256 da proposta e guardando o bit de execução),
  prepara a versão ao lado (`em-uso/<P>/.preparo-<hex>`, mesmo volume) e a põe no lugar de `atual` por renomeação,
  guardando a anterior em `anteriores/<data>`. Nova tentativa quando o Windows recusa a renomeação por acesso negado ou
  arquivo em uso (WinError 5, 32 e 33), com as esperas do kit (1, 2, 4, 8, 15 e 30 s); se a versão nova não entra, a
  anterior volta para `atual`. Um aceite vale para uma promoção só (o registro guarda a proposta e a decisão usadas,
  como no `voltar`), e a proposta vale para a troca a partir da versão em uso de quando foi feita: a âncora dela é a de
  agora, conferida contra `em-uso/` (vazia só vale sem versão em uso; a cópia forjada só faz recusar); a data dela mais
  de 5 minutos no futuro também recusa (revisão de segurança da 1.7.10, KIT-F1: o aceite já usado da v1 repunha a v1
  depois da v2, sem assinatura nova; revisão 1 da correção: a data, gravada pela sessão, não bastava; revisão 2: a data
  atrás do registro não recusa a proposta cuja âncora confere). Depois de cada troca, e da recusa pela âncora, grava a
  âncora de agora na cópia que a sessão lê, sem passar por ligação (no POSIX, por descritor de pasta).
- `pedir-volta` (a IA, na sessão): grava em `outputs/` o pedido de volta (`fundacao.versao_em_uso.volta/1`: a anterior
  pedida, ou a mais recente, o motivo, a data do pedido e a âncora da versão em uso, lida como no `propor`), para o
  aceite do titular, como a proposta.
- `voltar` (o titular, no terminal dele): exige a decisão assinada sobre o pedido, conferida como no `promover` —
  aceite, assinado, sobre esse pedido e esse SHA-256 — e um aceite vale para uma volta só (o registro guarda o pedido
  e a decisão usados). A assinatura autoriza o voltar (e o promover) sem depender do sandbox; com a raiz em `/mnt/e`,
  o sandbox não impede um comando da sessão de mexer em `em-uso/` por fora: ali o isolamento é lógico (contratos do
  lote 2, §0). Põe de volta a anterior pedida, conferida contra o manifesto dela; a que estava em uso vai para
  `anteriores/`. O pedido, com ou sem `--para`, vale para a volta a partir da versão em uso de quando foi feito: a
  âncora dele é a de agora (promoção ou volta registrada depois do pedido a muda e recusa: sem `--para`, a mais recente
  mudou; com `--para`, o aceite guardado punha a versão pedida no lugar de outra que entrou depois dele, sem assinatura
  nova: revisão 3 da correção do KIT-F1); peça outra volta. O pedido sem `--para` com data mais de 5 minutos no futuro
  também recusa (quem grava o pedido é a sessão: a data no futuro faria toda promoção parecer anterior a ele; a âncora,
  a sessão não a prevê). O motivo com caractere de controle, de formatação ou separador de linha recusa (vai para o
  registro).
- `conferir`: refaz o SHA-256 de cada arquivo de `atual` contra o manifesto dela (`VERSAO-EM-USO.json`, dentro da
  pasta) e o do manifesto contra o registro; arquivo alterado, ausente ou a mais, ou ligação, dá código 1. O envoltório
  das tarefas e dos servidores roda isto antes de executar, e as tarefas Python rodam com `python -B`: o `__pycache__`
  em `atual` conta como a mais, como `.git` e os caches de ferramenta (um .pyc plantado ali roda mesmo com -B, que só
  não grava; revisão de segurança da 1.7.10, KIT-F5). As pastas de dependências instaladas ali (`node_modules`; `.venv`
  e `venv` só se são ambiente virtual de verdade: `pyvenv.cfg` no topo e nenhum `__init__` ou `__main__`, que faria
  delas um pacote com sombra sobre o `venv` da biblioteca padrão) ficam fora da conferência, e o conferir o diz
  (`nao_conferido` e o aviso "não conferido: <pasta>", também no stderr), nunca num ok calado; a pasta que não se lista
  (permissão) dá código 1 (`ilegiveis`: um .pyc ali roda pelo caminho sem ser visto); a anterior do `voltar` é
  conferida do mesmo jeito.
Cada promoção e cada volta vão para `em-uso/<P>/registro.jsonl`, uma linha JSON em ASCII cada (o U+2028 do motivo ou do
decisao_id, cru, partia a linha, e a troca sumia para os leitores: revisão 2 da correção do KIT-F1); se ele falhar
depois da troca, o código é 3 (a troca aconteceu), nunca a recusa de código 2 nem traceback. Registro que existe e não
se lê (pasta, permissão, bytes fora do UTF-8, linha que não é objeto JSON) recusa no `promover`, no `voltar` e no
`conferir` (não dá para saber o que ele diz), em vez de valer como vazio; o BOM do início e o fim de linha do Windows
(o registro salvo à mão pelo PowerShell 5.1 ou pelo Bloco de Notas) não recusam (revisão 3 da correção do KIT-F1). A
decisão com o decisao_id fora do formato do kit também recusa. Os perfis do host negam às ferramentas da sessão a
escrita em `em-uso/` (regra lógica: com a raiz em `/mnt/e`, o sandbox não confina os comandos da sessão, que podem mexer
em `em-uso/` por fora — e no registro, onde o promover e o voltar veem o aceite já usado; a assinatura autoriza o
promover e o voltar, mas não protege a pasta). Uma promoção ou volta por vez (`em-uso/<P>/.trava`). Saída em JSON;
recusa: {"erro": ...} no stderr e código 2. O passo do titular nos `proximos_passos` do `propor` e do `pedir-volta` (o
`promover` e o `voltar`) traz a raiz e o arquivo citados para o terminal dele (`codigo_do_plano.citar_no_terminal`), ou
vem sem comando pronto se um deles não dá para citar com segurança (terceira revisão do pacote INTEG-FLUXOB).
"""

from __future__ import annotations

import argparse
import contextlib
import getpass
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ESQUEMA_PROPOSTA = "fundacao.versao_em_uso.proposta/1"
ESQUEMA_VOLTA = "fundacao.versao_em_uso.volta/1"
ESQUEMA_VERSAO = "fundacao.versao_em_uso/1"
ESQUEMA_ESTADO = "fundacao.versao_em_uso.estado/1"
MANIFESTO_DA_VERSAO = "VERSAO-EM-USO.json"  # dentro de atual/: a renomeação leva a versão e o manifesto juntos
# A âncora da versão em uso que a proposta e o pedido de volta levam (revisão 1 da correção do KIT-F1): o SHA-256 do
# manifesto de atual/ e o da última promoção ou volta do registro (muda a cada troca, mesmo a que repõe uma versão já
# usada, e leva o instante de quem trocou: a sessão não a prevê). A cópia dela que a sessão lê fica em outputs/.
ANCORA = ("manifesto_em_uso", "ultima_troca")
ESTADO_PARA_A_SESSAO = "outputs/versao/EM-USO-ATUAL.json"  # relativo à pasta do projeto
ID_PROJETO = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")  # o identificador do kit (fundacao/core/paths.py)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
NOME_ANTERIOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")  # um nome em anteriores/ (data, com -N se repetir)
# O decisao_id no formato do kit (`DECISAO_ID_RE` de fundacao/core/decisoes.py): o `preparar` o exige, mas o `verificar`
# devolve o da decisão como está, e ele vai para o registro (revisão 2 da correção do KIT-F1: linha do registro
# partida por U+2028).
DECISAO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
ESPERAS = (1, 2, 4, 8, 15, 30)  # as do kit na promoção (desenho da 1.7.10, §5.8): cerca de 1 minuto no total
TRANSITORIOS = (5, 32, 33)  # Windows: acesso negado, arquivo em uso, trecho travado (antivírus, Explorador)
TETO_LISTADOS = 200  # pastas ignoradas citadas pelo nome no resultado; acima disso, a contagem
# Quanto a data do pedido de volta sem --para (e a da proposta) pode estar à frente do relógio de quem roda o voltar
# (e o promover): a sessão grava o pedido e a proposta; o titular roda o voltar e o promover no terminal dele. Acima
# disso, recusa (segunda revisão do pacote INTEG-FLUXOB; na proposta, revisão de segurança da 1.7.10, KIT-F1).
FOLGA_DO_RELOGIO = timedelta(minutes=5)
IDENTIDADE = "FUNDACAO_PRINCIPAL"  # só lida, para o registro: quem promove é o titular, no terminal dele
_SEM_SEGUIR = getattr(os, "O_NOFOLLOW", 0)
_BINARIO = getattr(os, "O_BINARY", 0)
# A cópia da âncora para a sessão, gravada do terminal do titular na pasta em que a sessão grava: no POSIX, por
# descritor de pasta (revisão 2 da correção do KIT-F1: corrida na pasta da cópia), como o `Gravador` do fluxo B.
_POR_DESCRITOR = (os.name == "posix" and hasattr(os, "O_DIRECTORY") and bool(_SEM_SEGUIR)
                  and {os.open, os.mkdir, os.unlink, os.rename} <= os.supports_dir_fd)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_PASTA = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | _SEM_SEGUIR | _CLOEXEC


class Recusa(Exception):
    """Nada foi trocado em `atual`: quem chama sai com código 2 e esta mensagem."""


def _carregar(nome: str):
    """Um script ao lado deste, pelo caminho (sem mexer no `sys.path`)."""
    spec = importlib.util.spec_from_file_location(f"_versao_em_uso_{nome}", AQUI / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


MANIFESTO = _carregar("manifesto")  # as pastas ignoradas
GRAVACAO = _carregar("gravacao_segura")  # gravar sem seguir ligação nem vínculo físico
CONFERIDO = _carregar("codigo_conferido")  # Python isolado com só a raiz no caminho (o kit da raiz)
COPIA = _carregar("copia_segura")  # a cópia única feita fora do sandbox (contratos do lote 2, §8)
CODIGO = _carregar("codigo_do_plano")  # a citação única do comando pronto para o terminal do titular
REGRAS = MANIFESTO.REGRAS  # a regra única de segredo (regras_de_segredo.py)
_POLITICA = MANIFESTO.politica_padrao()
IGNORADAS = frozenset(_POLITICA["pastas_ignoradas"])
# As pastas de dependências instaladas na versão em uso: o conferir não as confere e o diz ("não conferido"); as outras
# pastas que o manifesto ignora (o __pycache__ que o Python grava ao rodar, .git, caches de ferramenta) contam como a
# mais em `atual` e na anterior do voltar (revisão de segurança da 1.7.10, KIT-F5). `.venv` e `venv` só quando são
# ambiente virtual de verdade (`_e_dependencia`).
DEPENDENCIAS = frozenset({".venv", "venv", "node_modules"})
AMBIENTES_VIRTUAIS = frozenset({".venv", "venv"})

# Injetáveis nos testes: a renomeação e a espera da nova tentativa.
_renomear = os.rename
_esperar = time.sleep


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _instante() -> str:
    """A data da proposta, do pedido de volta e de cada linha do registro, com microssegundos: o `promover` e o
    `voltar` sem `--para` comparam a da entrega com as do registro para saber se houve troca depois dela."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _data_iso(texto) -> datetime | None:
    """A data ISO com fuso (a de `_instante` ou a de `_agora`), ou None."""
    if not isinstance(texto, str):
        return None
    try:
        valor = datetime.fromisoformat(texto)
    except ValueError:
        return None
    return valor if valor.tzinfo is not None else None


def _carimbo() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def _e_ligacao(caminho) -> bool:
    try:
        return GRAVACAO.e_ligacao(os.lstat(caminho))
    except OSError:
        return False


def _dentro(caminho: Path, pasta: Path) -> bool:
    return Path(os.path.abspath(caminho)).is_relative_to(os.path.abspath(pasta))


def _pasta_do_projeto(raiz: Path, projeto: str) -> Path:
    if not ID_PROJETO.match(projeto or ""):
        raise Recusa(f"projeto {projeto!r}: identificador inválido (minúsculas, números e hífen)")
    pasta = raiz / "projects" / projeto
    if _e_ligacao(raiz / "projects") or _e_ligacao(pasta) or not pasta.is_dir():
        raise Recusa(f"{pasta} não existe ou é ligação")
    return pasta


def _rel_dentro(caminho: Path, pasta: Path, oque: str) -> str:
    """O caminho relativo (com /) de `caminho` dentro de `pasta`, sem ligação em nenhum componente."""
    caminho = Path(os.path.abspath(caminho))
    if not _dentro(caminho, pasta):
        raise Recusa(f"{oque} {caminho} fica fora de {pasta}")
    rel = caminho.relative_to(os.path.abspath(pasta)).as_posix()
    if rel != "." and GRAVACAO.com_ligacao(pasta, rel):
        raise Recusa(f"{oque} {caminho} passa por ligação (link simbólico ou junção)")
    return rel


def segredo(rel: str) -> bool:
    """Nome forte ou pasta de segredo em algum ponto do caminho, pela regra única (NFKC e sem caixa); o padrão forte
    vale também para o exemplo (`.env.example` casa `.env.*`), como nas negações dos perfis do host e na regra do
    manifesto até a 1.7.9. Os nomes fracos (`*token*`...) não ficam de fora: código como `tokenizer.py` é proposto."""
    return REGRAS.classificar(rel, exemplos=()) in ("forte", "pasta-de-segredo")


def _com_invisivel(texto: str) -> bool:
    """Caractere de controle, de formatação, substituto isolado ou separador de linha ou de parágrafo
    (`codigo_do_plano.INVISIVEIS`): o motivo do pedido e o nome da entrega (que a sessão escreve) com um deles recusam
    antes de tudo (revisão 2 da correção do KIT-F1: linha do registro partida por U+2028; defesa em profundidade: o
    registro já grava em ASCII e se lê partido só em "\\n")."""
    return any(unicodedata.category(c) in CODIGO.INVISIVEIS for c in texto)


def rel_valido(texto) -> bool:
    if not isinstance(texto, str) or not texto or len(texto) > 4096 or "\\" in texto or "\0" in texto:
        return False
    partes = texto.split("/")
    return (not texto.startswith("/") and not re.match(r"^[A-Za-z]:", texto) and texto != MANIFESTO_DA_VERSAO
            and all(p not in ("", ".", "..") for p in partes))


# --- globs -----------------------------------------------------------------------------------------------------------
def regex_do_glob(padrao: str) -> re.Pattern:
    """Glob relativo à pasta de trabalho, com `/`: `*` e `?` ficam numa pasta, `**` atravessa; terminado em `/`, a
    pasta inteira."""
    p = padrao.strip().replace("\\", "/").lstrip("/")
    p = p + "**" if p.endswith("/") else p
    saida, i = "", 0
    while i < len(p):
        if p.startswith("**/", i):
            saida, i = saida + "(?:.*/)?", i + 3
        elif p.startswith("**", i):
            saida, i = saida + ".*", i + 2
        elif p[i] == "*":
            saida, i = saida + "[^/]*", i + 1
        elif p[i] == "?":
            saida, i = saida + "[^/]", i + 1
        elif p[i] == "[" and (fim := p.find("]", i + 2)) > i:
            classe = p[i + 1:fim]
            classe = "^" + classe[1:] if classe.startswith("!") else classe
            saida, i = saida + "[" + classe.replace("\\", "\\\\") + "]", fim + 1
        else:
            saida, i = saida + re.escape(p[i]), i + 1
    return re.compile(saida + r"\Z")


def ler_lista(arquivo: Path) -> tuple[list[re.Pattern], list[re.Pattern], list[str]]:
    try:
        linhas = Path(arquivo).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise Recusa(f"--lista ilegível: {arquivo} ({type(exc).__name__})") from None
    incluir, excluir, padroes = [], [], []
    for linha in (l.strip() for l in linhas):
        if not linha or linha.startswith("#"):
            continue
        padroes.append(linha)
        try:
            rx = regex_do_glob(linha.lstrip("!"))
        except re.error:
            raise Recusa(f"--lista {arquivo}: glob inválido {linha!r}") from None
        (excluir if linha.startswith("!") else incluir).append(rx)
    if not incluir:
        raise Recusa(f"--lista {arquivo}: nenhum glob de inclusão")
    return incluir, excluir, padroes


# --- leitura conferida -----------------------------------------------------------------------------------------------
def _abrir_comum(caminho: Path):
    """Abre para leitura um arquivo comum, sem seguir ligação, com um nome só (sem vínculo físico)."""
    antes = os.lstat(caminho)
    if GRAVACAO.e_ligacao(antes) or not stat.S_ISREG(antes.st_mode):
        raise Recusa(f"{caminho} é ligação ou não é arquivo comum")
    if antes.st_nlink != 1:
        raise Recusa(f"{caminho} tem vínculo físico (mais de um nome): o conteúdo pode ser o de um arquivo de fora")
    f = os.fdopen(os.open(caminho, os.O_RDONLY | _SEM_SEGUIR | _BINARIO), "rb")
    aberto = os.fstat(f.fileno())
    if (aberto.st_dev, aberto.st_ino) != (antes.st_dev, antes.st_ino):
        f.close()
        raise Recusa(f"{caminho} foi trocado enquanto era aberto")
    return f


def hash_do_arquivo(caminho: Path) -> tuple[str, int]:
    h, total = hashlib.sha256(), 0
    with _abrir_comum(caminho) as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
            total += len(bloco)
    return h.hexdigest(), total


def _copiar_conferindo(origem: Path, destino: Path, esperado: str, dentro_de: Path) -> int | None:
    """Pela cópia única da skill (`copia_segura.copiar_conferindo`, contratos do lote 2, §8): sem seguir ligação (no
    POSIX, descendo de `dentro_de`, a pasta do projeto, por descritor), só arquivo comum com um nome só, em fluxo para
    um temporário exclusivo, com o SHA-256 da proposta conferido antes de ir para o destino (troca depois da proposta:
    recusa). `modo=None`: fora do Windows guarda o bit de execução da origem (modo & 0o755), que vai para o manifesto;
    no Windows o modo não tem sentido e volta None."""
    try:
        res = COPIA.copiar_conferindo(origem, destino, sha256_esperado=esperado, modo=None, dentro_de=dentro_de)
        return res["modo"]
    except COPIA.CopiaRecusada as exc:
        if "difere do esperado" in str(exc):  # a mensagem do SHA-256 trocado na cópia única
            raise Recusa(f"{origem} difere da proposta aceita ({exc}); nada foi trocado; proponha de novo") from None
        raise Recusa(f"{origem}: {exc}; nada foi trocado") from None


def _modo_valido(modo) -> bool:
    return modo is None or (isinstance(modo, int) and not isinstance(modo, bool) and 0 <= modo <= 0o777)


def _entrada_do_manifesto(item: dict, modo: int | None) -> dict:
    entrada = {k: item.get(k) for k in ("caminho", "tamanho", "sha256")}
    if modo is not None:  # no Windows não há modo: a entrada fica igual à das versões anteriores
        entrada["modo"] = modo
    return entrada


def percorrer(pasta: Path, situacao: dict, podar=IGNORADAS):
    """(rel, caminho) dos arquivos sob `pasta`, sem atravessar ligação nem as pastas podadas: `podar` é o conjunto dos
    nomes (no `propor`, as que o manifesto ignora) ou, no conferir, a função (caminho, nome) das de dependências
    (`_e_dependencia`, KIT-F5); ligação vai para `situacao["ligacoes"]`, pasta podada para `situacao["ignoradas"]` e a
    pasta que não se lista para `situacao["ilegiveis"]` ("." se é a própria `pasta`): o os.walk sem `onerror` a pulava
    calado, e um .pyc ali, aberto pelo caminho, rodava sem o conferir vê-lo (revisão 1 da correção do KIT-F5)."""
    def ilegivel(exc: OSError) -> None:
        nome = getattr(exc, "filename", None)
        try:
            rel = os.path.relpath(nome, pasta).replace(os.sep, "/") if nome else "?"
        except (TypeError, ValueError):
            rel = str(nome)
        situacao.setdefault("ilegiveis", []).append(rel)

    for atual, subpastas, arquivos in os.walk(pasta, onerror=ilegivel):
        base = Path(atual)
        for nome in sorted(subpastas):
            rel = (base / nome).relative_to(pasta).as_posix()
            if _e_ligacao(base / nome):
                subpastas.remove(nome)
                situacao["ligacoes"].append(rel)
            elif (podar(base / nome, nome) if callable(podar) else nome in podar):
                subpastas.remove(nome)
                situacao["ignoradas"].append(rel + "/")
        for nome in sorted(arquivos):
            rel = (base / nome).relative_to(pasta).as_posix()
            if _e_ligacao(base / nome):
                situacao["ligacoes"].append(rel)
            else:
                yield rel, base / nome


# --- versão em uso ---------------------------------------------------------------------------------------------------
def _em_uso(raiz: Path, projeto: str) -> Path:
    return raiz / "em-uso" / projeto


def ler_manifesto(pasta: Path) -> tuple[dict, bytes]:
    arquivo = pasta / MANIFESTO_DA_VERSAO
    try:
        with _abrir_comum(arquivo) as f:
            bruto = f.read()
        dados = json.loads(bruto.decode("utf-8"))
    except (OSError, ValueError, Recusa) as exc:
        raise Recusa(f"manifesto da versão ilegível: {arquivo} ({type(exc).__name__})") from None
    if (not isinstance(dados, dict) or dados.get("schema_version") != ESQUEMA_VERSAO
            or not isinstance(dados.get("arquivos"), list)
            or not all(isinstance(a, dict) and rel_valido(a.get("caminho")) and SHA256.match(str(a.get("sha256")))
                       and _modo_valido(a.get("modo")) for a in dados["arquivos"])):
        raise Recusa(f"manifesto da versão fora do formato {ESQUEMA_VERSAO}: {arquivo}")
    return dados, bruto


def _e_dependencia(caminho: Path, nome: str) -> bool:
    """A pasta de dependências instaladas que o conferir não confere (e diz): `node_modules`; `.venv` e `venv` só se são
    ambiente virtual de verdade — `pyvenv.cfg` (arquivo comum) no topo e nenhum `__init__` ou `__main__` ali, de
    qualquer extensão e em qualquer caixa (no NTFS, o Python acha o `__init__` por stat, sem caixa), que faria dela um
    pacote: uma venv/ assim em atual/ fazia sombra ao venv da biblioteca padrão para quem roda de lá, e o conferir dizia
    só "não conferido" (revisão 1 da correção do KIT-F5). Fora disso, os arquivos dela contam."""
    if nome not in DEPENDENCIAS:
        return False
    if nome not in AMBIENTES_VIRTUAIS:
        return True
    try:
        cfg = os.lstat(caminho / "pyvenv.cfg")
        nomes = os.listdir(caminho)
    except OSError:
        return False
    return stat.S_ISREG(cfg.st_mode) and not any(n.split(".")[0].casefold() in ("__init__", "__main__") for n in nomes)


def conferir_pasta(pasta: Path) -> dict:
    """O que difere entre a pasta e o manifesto dela: alterados, ausentes, a mais, ligações e pastas que não se listam.
    Só as pastas de dependências ficam de fora, ditas em `nao_conferido`; o `__pycache__` e as outras que o manifesto
    ignora contam (revisão de segurança da 1.7.10, KIT-F5: um .pyc plantado ali rodava, e o conferir dizia ok)."""
    dados, bruto = ler_manifesto(pasta)
    esperados = {a["caminho"]: a["sha256"] for a in dados["arquivos"]}
    modos = {a["caminho"]: a.get("modo") for a in dados["arquivos"]}
    situacao = {"ligacoes": [], "ignoradas": [], "ilegiveis": []}
    vistos, alterados, modo_diferente = set(), [], []
    for rel, caminho in percorrer(pasta, situacao, _e_dependencia):
        if rel == MANIFESTO_DA_VERSAO:
            continue
        vistos.add(rel)
        if rel in esperados:
            try:
                atual = hash_do_arquivo(caminho)[0]
            except (OSError, Recusa):
                atual = None
            if atual != esperados[rel]:
                alterados.append(rel)
            if os.name != "nt" and modos.get(rel) is not None:  # no Windows o modo do manifesto não é conferido
                try:
                    atual_modo = stat.S_IMODE(os.lstat(caminho).st_mode) & 0o755
                except OSError:
                    atual_modo = None
                if atual_modo != modos[rel]:
                    modo_diferente.append(rel)
    return {"pasta": str(pasta), "manifesto_sha256": _sha256(bruto), "arquivos": len(esperados),
            "alterados": sorted(alterados), "ausentes": sorted(set(esperados) - vistos),
            "a_mais": sorted(vistos - set(esperados)), "ligacoes": sorted(situacao["ligacoes"]),
            "modo_diferente": sorted(modo_diferente), "nao_conferido": sorted(situacao["ignoradas"]),
            "ilegiveis": sorted(situacao["ilegiveis"])}


def _difere(conferencia: dict) -> bool:
    """A pasta difere do manifesto dela (o conferir dá código 1; o voltar recusa a anterior)."""
    return any(conferencia.get(k) for k in ("alterados", "ausentes", "a_mais", "ligacoes", "modo_diferente",
                                            "ilegiveis"))


def _avisar(res: dict) -> dict:
    """Em palavras, o que a conferência não olhou e as dicas do `__pycache__` a mais e da pasta que não se lista
    (KIT-F5): nunca um ok calado."""
    if pastas := res.get("nao_conferido"):
        citadas = ", ".join(pastas[:10]) + (f" e mais {len(pastas) - 10}" if len(pastas) > 10 else "")
        res["aviso"] = (f"não conferido: {citadas} (dependências instaladas: o conferir não olha o conteúdo delas, e "
                        "código posto ali roda sem acusação)")
    dicas = []
    if any("__pycache__" in rel.split("/") for rel in res.get("a_mais", ())):
        dicas.append("__pycache__ conta como a mais: rode as tarefas Python com python -B, que não o grava; um .pyc "
                     "ali pode ser código plantado: confira de onde veio antes de apagá-lo")
    if res.get("ilegiveis"):
        dicas.append(f"pasta que não se lista ({', '.join(res['ilegiveis'][:10])}): um .pyc ali roda pelo caminho sem "
                     "o conferir vê-lo; confira as permissões dela e de onde veio o que há nela")
    if dicas:
        res["dica"] = "; ".join(dicas)
    return res


def _linhas_do_registro(registro: Path, para_que: str) -> list[dict] | None:
    """As linhas do registro, cada uma um objeto JSON; None se ele não existe. O registro que existe e não se lê (pasta,
    permissão, bytes fora do UTF-8) recusa, com `para_que` no motivo: valer como vazio liberaria o reuso de um aceite
    e a anterior sem promoção, e o UnicodeDecodeError saía como traceback (código 1) [revisão do pacote
    INTEG-FLUXOB]. As linhas se partem só em "\\n", e a linha que não é objeto JSON também recusa (revisão 2 da
    correção do KIT-F1: linha do registro partida por U+2028): o splitlines() partia também em U+2028, U+2029 e U+0085,
    que o motivo do pedido e o decisao_id da decisão levavam crus; cada pedaço era pulado, e a troca sumia para todos os
    leitores (o aceite já usado valia de novo, e a última troca não mudava). A linha antiga com o separador cru dentro
    de uma cadeia é lida inteira (o JSON o aceita ali); a linha em branco é pulada. O BOM do início sai, como o fim de
    linha do Windows: a recusa manda conferir a linha, e o PowerShell 5.1 (Set-Content e Out-File com -Encoding utf8)
    e o Bloco de Notas antigo salvam o registro com ele (revisão 3 da correção do KIT-F1: a linha 1, certa à vista,
    recusava)."""
    try:
        texto = registro.read_bytes().decode("utf-8-sig")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise Recusa(f"o registro {registro} não se lê ({type(exc).__name__}): {para_que}; nada foi trocado") from None
    itens = []
    for n, linha in enumerate(texto.split("\n"), 1):
        if not linha.strip(" \t\r"):
            continue
        try:
            item = json.loads(linha)
        except ValueError:
            item = None
        if not isinstance(item, dict):
            raise Recusa(f"o registro {registro} tem a linha {n} fora do formato (não é um objeto JSON; uma gravação "
                         f"interrompida deixa a última assim): {para_que}; nada foi trocado; confira essa linha antes "
                         "de promover ou voltar")
        itens.append(item)
    return itens


def _ativos(registro: Path) -> list[str] | None:
    """Os SHA-256 dos manifestos que as promoções e voltas puseram em uso, em ordem; None sem registro (ilegível:
    recusa, `_linhas_do_registro`)."""
    itens = _linhas_do_registro(registro, "não dá para conferir a versão em uso contra ele")
    if itens is None:
        return None
    return [item.get("manifesto_sha256") for item in itens if item.get("acao") in ("promover", "voltar")]


def _ultimo_ativo(registro: Path) -> str | None:
    """O SHA-256 do manifesto que a última promoção ou volta pôs em uso, pelo registro."""
    ativos = _ativos(registro)
    return ativos[-1] if ativos else None


def _ja_usados(registro: Path) -> set[str]:
    """Os SHA-256 das entregas (a proposta ou o pedido de volta) e das decisões que já fizeram uma troca: um aceite vale
    para uma troca só (no `voltar` desde a integração do fluxo B; no `promover` desde a revisão de segurança da 1.7.10,
    KIT-F1). Sem registro, nenhum; registro que não se lê recusa (falha fechada: não dá para saber se o aceite já foi
    usado)."""
    itens = _linhas_do_registro(registro, "não dá para saber se este aceite já foi usado")
    return {str(item[k]) for item in itens or [] if item.get("acao") in ("promover", "voltar")
            for k in ("proposta_sha256", "pedido_sha256", "sha256_decisao") if item.get(k)}


_ja_usados_na_volta = _ja_usados  # o nome da integração do fluxo B


def _houve_troca_depois(registro: Path, criado_em: datetime, para_que: str) -> bool:
    """Promoção ou volta registrada depois de `criado_em` (a data da entrega do aceite); a linha sem data legível conta
    como posterior. Só escolhe a mensagem da recusa pela âncora vazia: a entrega feita sem versão em uso, quando outra
    entrou depois dela, ouve "mudou", não "não diz qual versão" (revisão 2 da correção do KIT-F1). Nunca recusa a
    entrega cuja âncora confere: a data é da sessão, e o relógio do Ubuntu atrás do registro recusava a honesta."""
    for item in _linhas_do_registro(registro, para_que) or []:
        if item.get("acao") in ("promover", "voltar"):
            quando = _data_iso(item.get("quando"))
            if quando is None or quando > criado_em:
                return True
    return False


# --- âncora da versão em uso (revisão 1 da correção do KIT-F1) -------------------------------------------------------
# A proposta e o pedido de volta sem --para valiam pela data, que a sessão grava: com ela no futuro, o promover recusava
# na hora, o aceite ficava guardado e, passada a data, valia depois de outras trocas (a v1 voltava por cima da v2). A
# âncora, a sessão não a prevê: é conferida contra em-uso/ e só vale vazia sem versão em uso (a data, depois da
# revisão 2 da correção, só escolhe a mensagem da âncora vazia).
def _ultima_troca(registro: Path) -> str | None:
    """O SHA-256 da última promoção ou volta do registro (a linha, em JSON de chaves ordenadas), ou None sem troca
    registrada; registro que existe e não se lê recusa."""
    itens = _linhas_do_registro(registro, "não dá para saber qual é a versão em uso")
    trocas = [item for item in itens or [] if item.get("acao") in ("promover", "voltar")]
    return _sha256(json.dumps(trocas[-1], sort_keys=True).encode("ascii")) if trocas else None


def _estado_em_uso(em_uso: Path) -> dict:
    """A âncora da versão em uso (`ANCORA`), lida de `em-uso/<P>/`: o SHA-256 do manifesto de `atual` (None sem versão
    em uso) e o da última troca do registro (o manifesto não basta: a volta repõe o de uma versão já usada)."""
    return {"manifesto_em_uso": _manifesto_em_uso(em_uso / "atual"),
            "ultima_troca": _ultima_troca(em_uso / "registro.jsonl")}


def _ancora_valida(valor) -> bool:
    return valor is None or (isinstance(valor, str) and SHA256.fullmatch(valor) is not None)


def _ler_estado(pasta_projeto: Path, projeto: str) -> dict | None:
    """A cópia da âncora para a sessão (`ESTADO_PARA_A_SESSAO`), lida sem seguir ligação; None se falta, não se lê ou
    foge do formato."""
    try:
        with _abrir_comum(pasta_projeto / ESTADO_PARA_A_SESSAO) as f:
            dados = json.loads(f.read().decode("utf-8"))
    except (OSError, ValueError, Recusa):
        return None
    if (not isinstance(dados, dict) or dados.get("schema_version") != ESQUEMA_ESTADO
            or dados.get("projeto") != projeto or not all(_ancora_valida(dados.get(k)) for k in ANCORA)):
        return None
    return {k: dados.get(k) for k in ANCORA}


def _ancora_lida(raiz: Path, projeto: str, pasta_projeto: Path) -> dict:
    """A âncora que o `propor` e o `pedir-volta` gravam na entrega: a de `em-uso/` quando a versão em uso se lê daqui;
    senão (na sessão do Ubuntu, `em-uso/` fica fora da leitura e parece ausente) a da cópia que o `promover` e o
    `voltar` gravam; sem as duas, vazia, que só vale sem versão em uso. Cópia forjada só faz o promover recusar: ele
    confere contra `em-uso/`."""
    em_uso = _em_uso(raiz, projeto)
    if os.path.isdir(em_uso / "atual"):
        try:
            return _estado_em_uso(em_uso)
        except Recusa:
            pass
    return _ler_estado(pasta_projeto, projeto) or dict.fromkeys(ANCORA)


def _gravar_copia(pasta_projeto: Path, bruto: bytes) -> None:
    """Grava a cópia da âncora (`ESTADO_PARA_A_SESSAO`) do terminal do titular na pasta em que a sessão grava, sem
    passar por ligação (revisão 2 da correção do KIT-F1: corrida na pasta da cópia — conferir as pastas pelo caminho e
    gravar pelo caminho deixava a sessão trocar `outputs/versao` por ligação entre as duas coisas, e o titular gravava
    a cópia em qualquer pasta em que ele grava, como `em-uso/<P>/atual/`). No POSIX, como o `Gravador` do fluxo B:
    desce da pasta do projeto por descritor (`O_DIRECTORY|O_NOFOLLOW` em cada pasta, criada se falta), cria o
    temporário exclusivo e o renomeia, tudo relativo ao descritor da pasta. No Windows (isolamento lógico: a biblioteca
    padrão não abre relativo a um handle de pasta), o caminho real da pasta é conferido antes de pôr o temporário no
    lugar (desviado: o temporário é apagado, nada fica) e depois (desviado: falha, e o aviso o diz)."""
    *pastas, nome = Path(ESTADO_PARA_A_SESSAO).parts
    temp = f".{nome}.{secrets.token_hex(8)}.tmp"
    if _POR_DESCRITOR:
        fd = os.open(pasta_projeto, _PASTA)
        try:
            for parte in pastas:
                try:
                    novo = os.open(parte, _PASTA, dir_fd=fd)
                except FileNotFoundError:
                    os.mkdir(parte, 0o755, dir_fd=fd)
                    novo = os.open(parte, _PASTA, dir_fd=fd)
                os.close(fd)
                fd = novo
            arquivo = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _SEM_SEGUIR | _CLOEXEC, 0o666, dir_fd=fd)
            try:
                try:
                    GRAVACAO._gravar_tudo(arquivo, bruto)
                finally:
                    os.close(arquivo)
                os.rename(temp, nome, src_dir_fd=fd, dst_dir_fd=fd)  # troca o nome: uma ligação no lugar não é seguida
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(temp, dir_fd=fd)
                raise
        finally:
            os.close(fd)
        return
    pasta = GRAVACAO.pasta_sem_ligacao(pasta_projeto, "/".join(pastas))
    esperada = os.path.normcase(os.path.join(os.path.realpath(pasta_projeto), *pastas))

    def conferir_a_pasta(gravada: bool) -> None:
        if os.path.normcase(os.path.realpath(pasta)) != esperada:
            raise GRAVACAO.GravacaoRecusada(
                f"{'/'.join(pastas)} foi trocada por ligação durante a gravação: " + (
                    "a cópia pode ter ido para fora do projeto; confira a pasta" if gravada else "nada foi gravado"))
    tmp = pasta / temp
    GRAVACAO.criar(tmp, bruto)
    try:
        conferir_a_pasta(False)
        GRAVACAO.conferir_destino(pasta / nome)
        os.replace(tmp, pasta / nome)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    conferir_a_pasta(True)


def _publicar_estado(pasta_projeto: Path, projeto: str, estado: dict) -> str | None:
    """Do terminal do titular: a âncora de agora na cópia que a sessão lê, sem passar por ligação (`_gravar_copia`).
    Devolve None, ou o erro: a troca, se houve, já aconteceu; só a próxima entrega da sessão do Ubuntu sai sem a âncora,
    e o promover a recusa e grava a cópia de novo."""
    bruto = (json.dumps({"schema_version": ESQUEMA_ESTADO, "projeto": projeto, **{k: estado[k] for k in ANCORA},
                         "gravado_em": _agora()}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        _gravar_copia(pasta_projeto, bruto)
    except OSError as exc:
        return f"{type(exc).__name__}: {exc}"[:300]
    return None


def _publicar_estado_atual(em_uso: Path, pasta_projeto: Path, projeto: str) -> str | None:
    """Depois da troca: a âncora nova na cópia da sessão; nunca recusa (a troca já aconteceu)."""
    try:
        return _publicar_estado(pasta_projeto, projeto, _estado_em_uso(em_uso))
    except (Recusa, OSError, ValueError) as exc:
        return f"{type(exc).__name__}: {exc}"[:300]


_VENCIDA = {
    "proposta": {
        "vazia": "a proposta não diz qual versão estava em uso quando foi feita (manifesto_em_uso e ultima_troca "
                 "vazios: o propor os lê de em-uso/ ou, onde ele fica fora da leitura, como na sessão do Ubuntu, da "
                 "cópia que o promover e o voltar gravam)",
        "mudou": "a versão em uso mudou depois da proposta (houve promoção ou volta depois dela): o aceite é da troca "
                 "a partir da que estava em uso quando ela foi feita",
        "refazer": "proponha de novo (propor) e peça o aceite dela",
        "para_que": "não dá para saber se a versão em uso mudou depois da proposta"},
    "pedido": {  # com ou sem --para (revisão 3 da correção do KIT-F1)
        "vazia": "o pedido não diz qual versão estava em uso quando foi feito (manifesto_em_uso e ultima_troca "
                 "vazios: o pedir-volta os lê como o propor)",
        "mudou": "houve promoção ou volta depois do pedido: o aceite é da volta a partir da versão em uso de quando "
                 "ele foi feito",
        "refazer": "peça outra volta (pedir-volta, com --para <nome em anteriores/> se quiser uma certa) e o aceite "
                   "dela",
        "para_que": "não dá para saber se houve promoção depois do pedido"}}


def _recusar_entrega_vencida(em_uso: Path, pasta_projeto: Path, projeto: str, dados: dict, desde: datetime,
                             oque: str) -> None:
    """A proposta e o pedido de volta (com ou sem `--para`: revisão 3 da correção do KIT-F1) valem para a troca a partir
    da versão em uso de quando foram feitos: a âncora deles é a de agora; quando não é, recusa, e a de agora vai para a
    cópia da sessão (a próxima entrega sai certa).
    A âncora que confere já prova que nenhuma troca foi registrada depois da entrega (a última troca leva o instante de
    quem trocou): a data, que a sessão grava, não recusa — a segunda camada recusava a proposta e o pedido honestos
    quando o relógio do Ubuntu estava atrás do registro, e rodar no mesmo sistema não resolvia (revisão 2 da correção
    do KIT-F1). A data só escolhe a mensagem da âncora vazia (`_houve_troca_depois`)."""
    textos = _VENCIDA[oque]
    agora = _estado_em_uso(em_uso)
    if all(dados.get(k) == agora[k] for k in ANCORA):
        return
    falha = _publicar_estado(pasta_projeto, projeto, agora)
    nota = (f"; a âncora de agora foi gravada em {ESTADO_PARA_A_SESSAO}" if falha is None else
            f"; a âncora de agora não foi gravada em {ESTADO_PARA_A_SESSAO} ({falha})")
    vazia = all(dados.get(k) is None for k in ANCORA)  # feita sem versão em uso, ou sem ler a âncora
    motivo = textos["vazia"] if vazia and not _houve_troca_depois(em_uso / "registro.jsonl", desde,
                                                                  textos["para_que"]) else textos["mudou"]
    raise Recusa(f"{motivo}{nota}; {textos['refazer']}; nada foi trocado")


def conferir(raiz, projeto: str) -> dict:
    raiz = Path(os.path.abspath(raiz))
    _pasta_do_projeto(raiz, projeto)
    em_uso = _em_uso(raiz, projeto)
    atual = em_uso / "atual"
    if _e_ligacao(em_uso) or _e_ligacao(atual) or not atual.is_dir():
        raise Recusa(f"não há versão em uso de {projeto} ({atual} ausente ou ligação): nada deve rodar dela")
    res = conferir_pasta(atual)
    ativo = _ultimo_ativo(em_uso / "registro.jsonl")
    res["manifesto_confere_com_o_registro"] = None if ativo is None else ativo == res["manifesto_sha256"]
    res["ok"] = not (_difere(res) or res["manifesto_confere_com_o_registro"] is False)
    return _avisar(res)


# --- propor ----------------------------------------------------------------------------------------------------------
def propor(raiz, projeto: str, de, lista, saida) -> dict:
    raiz = Path(os.path.abspath(raiz))
    pasta_projeto = _pasta_do_projeto(raiz, projeto)
    de = Path(os.path.abspath(de))
    origem = _rel_dentro(de, pasta_projeto, "--de")
    if not de.is_dir():
        raise Recusa(f"--de {de} não é pasta")
    saida = Path(os.path.abspath(saida))
    rel_saida = _rel_dentro(saida, pasta_projeto / "outputs", "--saida")
    if saida.suffix != ".json" or rel_saida == ".":
        raise Recusa("--saida é um arquivo .json dentro de outputs/ do projeto (o aceite assina uma entrega de lá)")
    incluir, excluir, padroes = ler_lista(Path(lista))
    situacao = {"ligacoes": [], "ignoradas": [], "ilegiveis": []}
    arquivos, excluidos = [], []
    for rel, caminho in percorrer(de, situacao):
        if not any(rx.match(rel) for rx in incluir) or any(rx.match(rel) for rx in excluir):
            continue
        if _com_invisivel(rel):  # o promover o recusa; o substituto isolado nem se grava em UTF-8 (revisão 3, KIT-F1)
            excluidos.append({"caminho": CODIGO.visivel(rel), "motivo": "nome com caractere de controle, de "
                              "formatação, separador de linha ou fora do UTF-8: renomeie o arquivo"})
            continue
        if segredo(rel):
            excluidos.append({"caminho": rel, "motivo": "nome ou pasta de segredo: segredo vai pelo cofre, não pela "
                                                        "proposta"})
            continue
        if not rel_valido(rel):
            excluidos.append({"caminho": rel, "motivo": "nome reservado ou fora do formato"})
            continue
        try:
            sha, tamanho = hash_do_arquivo(caminho)
        except (OSError, Recusa) as exc:
            excluidos.append({"caminho": rel, "motivo": f"não lido: {str(exc)[:160]}"})
            continue
        arquivos.append({"caminho": rel, "tamanho": tamanho, "sha256": sha})
    excluidos += [{"caminho": rel, "motivo": "ligação não seguida"} for rel in situacao["ligacoes"]
                  if any(rx.match(rel) for rx in incluir)]
    excluidos += [{"caminho": rel if rel in (".", "?") else rel + "/", "motivo": "pasta que não se lista (permissão): "
                   "o que há nela não foi proposto"} for rel in situacao["ilegiveis"]]  # revisão 1 do KIT-F5
    if not arquivos:
        raise Recusa("a lista não casou nenhum arquivo da pasta de trabalho")
    vistos = {}
    for item in arquivos:
        if item["caminho"].casefold() in vistos:  # no Windows os dois seriam o mesmo arquivo
            raise Recusa(f"{item['caminho']} e {vistos[item['caminho'].casefold()]} diferem só em maiúsculas")
        vistos[item["caminho"].casefold()] = item["caminho"]
    atual = _em_uso(raiz, projeto) / "atual"
    # A data e a âncora da versão em uso (de em-uso/ ou da cópia da sessão): o promover as confere (KIT-F1).
    proposta = {"schema_version": ESQUEMA_PROPOSTA, "projeto": projeto, "origem": origem, "criada_em": _instante(),
                **_ancora_lida(raiz, projeto, pasta_projeto),
                "lista": {"arquivo": str(lista), "padroes": padroes}, "arquivos": arquivos, "excluidos": excluidos}
    bruto = (json.dumps(proposta, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    GRAVACAO.pasta_sem_ligacao(pasta_projeto, Path("outputs", rel_saida).parent.as_posix())
    GRAVACAO.publicar(saida, bruto)
    sha = _sha256(bruto)
    entrega = Path("outputs", rel_saida).as_posix()
    return {"proposta": str(saida), "sha256": sha, "entrega": entrega, "arquivos": len(arquivos),
            "excluidos": excluidos, "pastas_ignoradas": _resumo(situacao["ignoradas"]),
            "diferenca": _diferenca(atual, arquivos),
            "proximos_passos": [
                f'python -m fundacao tarefa criar --projeto {projeto} --objetivo "promover a versão em uso"',
                f"python -m fundacao decisao preparar --projeto {projeto} --tarefa <task_id> --tipo aceite "
                f'--entrega {entrega} --motivo "<as palavras do titular>"',
                passo_do_titular("promover", raiz, projeto, "proposta", saida, sha)]}


def passo_do_titular(acao: str, raiz: Path, projeto: str, entrada: str, arquivo: Path, sha: str) -> str:
    """O último passo do aceite, que o titular roda no terminal dele, fora do Claude: o `promover` da proposta ou o
    `voltar` do pedido (`entrada`), com a raiz e o arquivo citados para o shell de destino
    (`codigo_do_plano.citar_no_terminal`), em vez de entre aspas duplas, em que `$` e a crase valem [terceira revisão do
    pacote INTEG-FLUXOB]; `<skill>` e `<id>` ficam para a IA completar. Sem comando pronto se um deles não dá para
    citar com segurança. O projeto e o SHA-256 vão como estão: só letras, números e hífen."""
    inicio = "o titular assina com o comando de para_o_titular e, no terminal dele, fora do Claude"
    try:
        raiz_citada, arquivo_citado = CODIGO.citar_no_terminal(raiz), CODIGO.citar_no_terminal(arquivo)
    except ValueError as exc:
        artigo, de = _ARTIGOS[entrada]
        return (f"{inicio}, roda o {acao} {de} {entrada}; não há comando pronto: {exc}, e o comando não o cita com "
                f"segurança no terminal; grave-{artigo} noutro caminho (--saida) ou renomeie a pasta, e refaça este "
                "passo")
    return (f"{inicio}: {'python' if os.name == 'nt' else 'python3'} <skill>/scripts/versao_em_uso.py {acao} --raiz "
            f"{raiz_citada} --projeto {projeto} --{entrada} {arquivo_citado} --{entrada}-sha256 {sha} --decisao "
            f"<projects/{projeto}/decisoes/<id>.json>")


def _resumo(itens: list[str]) -> dict:
    return {"total": len(itens), "primeiras": itens[:TETO_LISTADOS]}


def _manifesto_em_uso(atual: Path) -> str | None:
    """O SHA-256 do manifesto da versão em uso, ou None se ela não existe ou não se lê daqui (na sessão do Ubuntu,
    `em-uso/` fica fora da leitura, e a pasta escondida parece ausente: a âncora vem da cópia, `_ancora_lida`)."""
    try:
        return _sha256(ler_manifesto(atual)[1])
    except Recusa:
        return None


def _diferenca(atual: Path, arquivos: list[dict]) -> dict | None:
    """Novos, alterados e removidos em relação à versão em uso; None se ela não existe ou não é legível daqui (na
    sessão do Ubuntu, `em-uso/` fica fora da leitura: a diferença sai no `promover`)."""
    try:
        dados, _bruto = ler_manifesto(atual)
    except Recusa:
        return None
    antes = {a["caminho"]: a["sha256"] for a in dados["arquivos"]}
    depois = {a["caminho"]: a["sha256"] for a in arquivos}
    return {"novos": sorted(depois.keys() - antes.keys()), "removidos": sorted(antes.keys() - depois.keys()),
            "alterados": sorted(r for r in antes.keys() & depois.keys() if antes[r] != depois[r])}


# --- promover e voltar -----------------------------------------------------------------------------------------------
def _transitorio(exc: BaseException) -> bool:
    return isinstance(exc, PermissionError) and getattr(exc, "winerror", None) in TRANSITORIOS


def renomear(origem: Path, destino: Path) -> int:
    """`os.rename` com nova tentativa no erro transitório do Windows; devolve as tentativas."""
    for tentativa, espera in enumerate((*ESPERAS, None), 1):
        try:
            _renomear(origem, destino)
            return tentativa
        except OSError as exc:
            if espera is None or not _transitorio(exc):
                raise
            _esperar(espera)
    raise AssertionError("inalcançável")


def _nome_livre(pasta: Path, base: str) -> Path:
    candidato, n = pasta / base, 1
    while os.path.lexists(candidato):
        n += 1
        candidato = pasta / f"{base}-{n}"
    return candidato


def _trocar(em_uso: Path, nova: Path) -> tuple[str | None, int]:
    """Põe `nova` no lugar de `atual` e guarda a que estava em `anteriores/`; se a nova não entra, a anterior volta.
    A troca é por renomeações em sequência (no Linux o renameat2 RENAME_EXCHANGE seria atômico, mas é opcional e não
    é usado aqui). Durante uma promoção, o código 2 daqui quer dizer "não rode as tarefas agora; tente de novo": a
    anterior pode estar guardada em `anteriores/` à espera de voltar para `atual`."""
    atual, anterior, tentativas = em_uso / "atual", None, 0
    if os.path.lexists(atual):
        if _e_ligacao(atual) or not atual.is_dir():
            raise Recusa(f"{atual} é ligação ou não é pasta: confira-a antes de promover")
        anterior = _nome_livre(em_uso / "anteriores", _carimbo())
        tentativas += renomear(atual, anterior)
    try:
        tentativas += renomear(nova, atual)
    except OSError as exc:
        if anterior is not None:
            try:
                renomear(anterior, atual)
            except OSError as exc2:
                raise Recusa(f"a versão nova não entrou ({exc}) e a anterior não voltou ({exc2}): ela está em "
                             f"{anterior}; renomeie-a para {atual} antes de rodar as tarefas") from None
        raise Recusa(f"o sistema recusou pôr a versão nova no lugar depois de {len(ESPERAS) + 1} tentativas ({exc}); "
                     "a anterior continua em uso; não rode as tarefas agora; algum programa segurava a pasta "
                     "(antivírus, Explorador): feche-o e tente de novo") from None
    return (anterior.name if anterior else None), tentativas


@contextlib.contextmanager
def _trava(em_uso: Path):
    trava = em_uso / ".trava"
    try:
        fd = os.open(trava, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _SEM_SEGUIR | _BINARIO, 0o600)
    except FileExistsError:
        raise Recusa(f"outra promoção ou volta em andamento ({trava}); se nenhuma estiver rodando, apague esse "
                     "arquivo e repita") from None
    try:
        os.write(fd, json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "desde": _agora()}).encode())
    finally:
        os.close(fd)
    try:
        yield
    finally:
        os.unlink(trava)


def _quem() -> str:
    try:
        return os.environ.get(IDENTIDADE) or getpass.getuser()
    except (OSError, KeyError, ImportError):
        return "desconhecido"


def _registrar(em_uso: Path, linha: dict) -> None:
    """Uma linha JSON em ASCII por troca (revisão 2 da correção do KIT-F1: linha do registro partida por U+2028): com
    ensure_ascii=False, U+2028, U+2029 e U+0085 do motivo, do decisao_id ou do nome da entrega iam crus e partiam
    a linha para os leitores, e o substituto isolado estourava o encode depois da troca; em ASCII, todos saem
    escapados."""
    linha = {"quando": _instante(), "por": _quem(), **linha}
    GRAVACAO.anexar(em_uso / "registro.jsonl",
                    (json.dumps(linha, ensure_ascii=True, sort_keys=True) + "\n").encode("ascii"))


def _conferir_registro(em_uso: Path) -> None:
    """Antes de trocar: o registro aceita o anexar (ausente, ou arquivo comum sem ligação nem vínculo físico). Assim
    um registro que já é ligação ou pasta recusa (código 2) antes de qualquer troca, não depois dela."""
    registro = em_uso / "registro.jsonl"
    try:
        st = os.lstat(registro)
    except FileNotFoundError:
        return
    GRAVACAO._exigir_simples(registro, st)


def _anexar_registro(em_uso: Path, linha: dict) -> str | None:
    """Depois da troca (a versão nova já está em uso): anexa ao registro, repetindo no erro transitório do Windows.
    Devolve None se gravou, ou o texto do erro se não — aí o chamador sai com código 3 (a troca aconteceu), nunca com
    a recusa de código 2 (que diria, falsamente, que nada mudou)."""
    for espera in (*ESPERAS, None):
        try:
            _registrar(em_uso, linha)
            return None
        except OSError as exc:
            if espera is None or not _transitorio(exc):
                return str(exc)
            _esperar(espera)
        except (ValueError, TypeError) as exc:  # o JSON ou o encode da linha (o UnicodeEncodeError é um ValueError):
            return f"{type(exc).__name__}: {exc}"[:300]  # código 3, nunca traceback (revisão 2 da correção do KIT-F1)
    return "inalcançável"


def _apagar(pasta: Path) -> int:
    """Apaga a preparação que falhou, tirando o somente leitura; devolve quantos itens sobraram (contados, não
    engolidos, como a limpeza do kit na 1.7.10)."""
    def tirar(funcao, caminho, _erro):
        try:
            os.chmod(caminho, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
            funcao(caminho)
        except OSError:
            pass
    if not os.path.lexists(pasta):
        return 0
    if sys.version_info >= (3, 12):
        shutil.rmtree(pasta, onexc=tirar)
    else:
        shutil.rmtree(pasta, onerror=tirar)
    return sum(len(d) + len(a) for _r, d, a in os.walk(pasta)) + (1 if os.path.lexists(pasta) else 0)


def verificar_decisao_pelo_kit(raiz: Path, decisao: Path) -> dict:
    """`python -m fundacao decisao verificar` pelo kit da raiz, em Python isolado (`-I`) com só a raiz no caminho de
    importação — o uso normal —, com o ambiente do terminal do titular (a identidade dele)."""
    comando = CONFERIDO.python_isolado(raiz, CONFERIDO.CLI, "--raiz", raiz, "decisao", "verificar", "--arquivo",
                                       decisao)
    try:
        r = subprocess.run(comando, cwd=str(raiz), capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Recusa(f"o kit da raiz não rodou ({type(exc).__name__})") from None
    try:
        dados = json.loads(r.stdout) if r.returncode in (0, 3) else None
    except ValueError:
        dados = None
    if not isinstance(dados, dict):
        raise Recusa(f"o kit da raiz não conferiu a decisão (código {r.returncode}): {r.stderr.strip()[-500:]}; rode "
                     "no terminal do titular, com a identidade dele")
    return dados


def validar_proposta(dados, projeto: str) -> tuple[str, list[dict]]:
    if not isinstance(dados, dict) or dados.get("schema_version") != ESQUEMA_PROPOSTA:
        raise Recusa(f"proposta fora do formato {ESQUEMA_PROPOSTA}")
    if dados.get("projeto") != projeto:
        raise Recusa(f"a proposta é do projeto {dados.get('projeto')!r}, não de {projeto}")
    origem, arquivos = dados.get("origem"), dados.get("arquivos")
    # A origem e o caminho de cada item vão para o manifesto: com caractere invisível, recusam antes de tudo (revisão 3
    # da correção do KIT-F1: o substituto isolado estourava o encode do manifesto, com traceback e código 1).
    if (not (origem == "." or rel_valido(origem)) or _com_invisivel(origem) or not isinstance(arquivos, list)
            or not arquivos):
        raise Recusa("proposta sem origem válida ou sem arquivos")
    vistos = set()
    for item in arquivos:
        if (not isinstance(item, dict) or not rel_valido(item.get("caminho")) or _com_invisivel(item["caminho"])
                or segredo(item["caminho"]) or any(p in IGNORADAS for p in item["caminho"].split("/"))
                or not SHA256.match(str(item.get("sha256")))):
            raise Recusa("item fora do formato, com caminho inválido (ou com caractere de controle, de formatação ou "
                         "separador de linha), de segredo ou em pasta que a conferência ignora na proposta: "
                         f"{str(item)[:160]}")
        if item["caminho"].casefold() in vistos:
            raise Recusa(f"caminho repetido na proposta (sem diferença de maiúsculas): {item['caminho']}")
        vistos.add(item["caminho"].casefold())
    _exigir_ancora_no_formato(dados, "proposta")
    return origem, arquivos


def _exigir_ancora_no_formato(dados: dict, oque: str) -> None:
    for campo in ANCORA:
        if not _ancora_valida(dados.get(campo)):
            raise Recusa(f"{oque} com a âncora da versão em uso ({campo}) fora do formato: SHA-256 ou null")


def data_da_proposta(dados: dict, *, agora: datetime | None = None) -> datetime:
    """A data da proposta (`criada_em`, ISO com fuso), obrigatória (KIT-F1). Quem grava a proposta é a sessão: a data
    mais de `FOLGA_DO_RELOGIO` à frente do relógio de quem promove recusa, como no pedido de volta sem `--para`. O que
    prende a proposta à versão em uso de quando foi feita é a âncora (`_recusar_entrega_vencida`): a data no futuro só
    recusava na hora e, passada ela, valia depois de outras trocas (revisão 1 da correção do KIT-F1); e a data atrás do
    registro não recusa mais a proposta cuja âncora confere (revisão 2: o relógio do Ubuntu atrás a recusava)."""
    criada_em = _data_iso(dados.get("criada_em"))
    if criada_em is None:
        raise Recusa("proposta sem a data (criada_em, ISO com fuso): proponha de novo (propor); nada foi trocado")
    if criada_em > (agora or datetime.now(timezone.utc)) + FOLGA_DO_RELOGIO:
        raise Recusa("proposta com data no futuro (criada_em): não dá para saber qual versão estava em uso quando ela "
                     "foi feita; proponha de novo (propor); nada foi trocado")
    return criada_em


_ARTIGOS = {"proposta": ("a", "da"), "pedido": ("o", "do")}  # a proposta / o pedido; da proposta / do pedido


def _ler_entrega(arquivo, pasta_projeto: Path, sha_informado: str, oque: str) -> tuple[str, str, dict]:
    """A entrega do aceite (proposta ou pedido de volta), em `outputs/` do projeto, lida sem seguir ligação e conferida
    pelo SHA-256 informado: (caminho relativo ao projeto, SHA-256, conteúdo)."""
    arquivo = Path(os.path.abspath(arquivo))
    rel = _rel_dentro(arquivo, pasta_projeto, f"--{oque}")
    if not rel.startswith("outputs/"):
        raise Recusa(f"--{oque} fica em outputs/ do projeto (a entrega do aceite)")
    if _com_invisivel(rel):  # o nome vai para o registro (revisão 2 da correção do KIT-F1)
        raise Recusa(f"--{oque} com caractere de controle, de formatação ou separador de linha no nome "
                     f"({ascii(rel)}): {_ARTIGOS[oque][0]} {oque} se grava de novo com outro nome; nada foi trocado")
    with _abrir_comum(arquivo) as f:
        bruto = f.read()
    sha = _sha256(bruto)
    if sha != str(sha_informado).strip().lower():
        raise Recusa(f"{_ARTIGOS[oque][0]} {oque} não tem o SHA-256 informado (tem {sha}): nada foi trocado")
    try:
        return rel, sha, json.loads(bruto.decode("utf-8"))
    except ValueError:
        raise Recusa(f"{oque} ilegível") from None


def _conferir_aceite(raiz: Path, pasta_projeto: Path, decisao, rel: str, sha: str, verificar, oque: str) -> tuple[
        dict, Path]:
    """A decisão do titular sobre a entrega, pelo kit da raiz (`verificar`): aceite, assinado, sobre essa entrega e esse
    SHA-256 — a mesma conferência no `promover` e no `voltar`. O decisao_id no formato do kit e o SHA-256 da decisão
    vão para o registro: fora do formato, recusam (revisão 2 da correção do KIT-F1: o decisao_id com U+2028, assinado
    de verdade, partia a linha do registro)."""
    decisao = Path(os.path.abspath(decisao))
    if _com_invisivel(_rel_dentro(decisao, pasta_projeto / "decisoes", "--decisao")):  # vai para o manifesto
        raise Recusa(f"--decisao com caractere de controle, de formatação ou separador de linha no nome "
                     f"({ascii(decisao.name)}): nada foi trocado")  # revisão 3 da correção do KIT-F1
    v = verificar(raiz, decisao)
    entrega = v.get("entrega") if isinstance(v.get("entrega"), dict) else {}
    valida, decisao_id, sha_decisao = v.get("valida") is True, v.get("decisao_id"), v.get("sha256_decisao")
    problemas = [motivo for falhou, motivo in (
        (not valida, f"decisão inválida: {v.get('motivo')}"),
        (v.get("tipo") != "aceite", "a decisão não é um aceite"),
        (v.get("forca") != "assinatura", "o aceite não está assinado pelo titular"),
        (entrega.get("caminho") != rel, f"o aceite é de outra entrega ({entrega.get('caminho')})"),
        (entrega.get("sha256") != sha, f"o aceite é de outra versão {_ARTIGOS[oque][1]} {oque} (SHA-256 diferente)"),
        (valida and (not isinstance(decisao_id, str) or not DECISAO_ID.fullmatch(decisao_id)),
         f"a decisão tem o decisao_id fora do formato do kit ({ascii(decisao_id)[:120]}): prepare-a de novo"),
        (valida and (not isinstance(sha_decisao, str) or not SHA256.fullmatch(sha_decisao)),
         "a verificação do kit não trouxe o SHA-256 da decisão"))
        if falhou]
    if problemas:
        raise Recusa("; ".join(problemas) + "; nada foi trocado")
    return v, decisao


def _recusar_proposta_vencida(em_uso: Path, pasta_projeto: Path, projeto: str, sha: str, v: dict, dados: dict,
                              criada_em: datetime) -> None:
    """Revisão de segurança da 1.7.10, KIT-F1 (o aceite já usado da v1 repunha a v1 depois da v2, sem assinatura nova):
    um aceite vale para uma promoção só, e a proposta vale para a troca a partir da versão em uso de quando foi feita —
    a âncora dela é a de agora, vazia só sem versão em uso (`_recusar_entrega_vencida`; revisão 1 da correção: a data
    sozinha, gravada pela sessão, não bastava; revisão 2: e não recusa mais a proposta cuja âncora confere)."""
    _recusar_aceite_usado(em_uso, sha, v, "proposta")
    _recusar_entrega_vencida(em_uso, pasta_projeto, projeto, dados, criada_em, "proposta")


def promover(raiz, projeto: str, proposta, proposta_sha256: str, decisao, *, verificar=None) -> dict:
    verificar = verificar or verificar_decisao_pelo_kit
    raiz = Path(os.path.abspath(raiz))
    pasta_projeto = _pasta_do_projeto(raiz, projeto)
    rel_proposta, sha, dados = _ler_entrega(proposta, pasta_projeto, proposta_sha256, "proposta")
    origem, arquivos = validar_proposta(dados, projeto)
    criada_em = data_da_proposta(dados)
    v, decisao = _conferir_aceite(raiz, pasta_projeto, decisao, rel_proposta, sha, verificar, "proposta")
    em_uso = GRAVACAO.pasta_sem_ligacao(raiz, f"em-uso/{projeto}")
    GRAVACAO.pasta_sem_ligacao(raiz, f"em-uso/{projeto}/anteriores")
    de = pasta_projeto if origem == "." else pasta_projeto / origem
    with _trava(em_uso):
        _conferir_registro(em_uso)  # antes de qualquer troca: registro inválido recusa (código 2), sem mexer em atual
        # Com a trava: duas promoções, uma só passa.
        _recusar_proposta_vencida(em_uso, pasta_projeto, projeto, sha, v, dados, criada_em)
        preparo = em_uso / f".preparo-{secrets.token_hex(4)}"
        os.mkdir(preparo, 0o755)
        try:
            modos = {}
            for item in arquivos:
                if GRAVACAO.com_ligacao(pasta_projeto, f"{origem}/{item['caminho']}" if origem != "." else
                                        item["caminho"]):
                    raise Recusa(f"{item['caminho']} passa por ligação na pasta de trabalho")
                pai = item["caminho"].rpartition("/")[0]
                if pai:  # a pasta do arquivo na preparação, sem ligação em nenhum componente
                    GRAVACAO.pasta_sem_ligacao(preparo, pai)
                modos[item["caminho"]] = _copiar_conferindo(de / item["caminho"], preparo / item["caminho"],
                                                            item["sha256"], pasta_projeto)
            manifesto = {"schema_version": ESQUEMA_VERSAO, "projeto": projeto, "promovida_em": _agora(),
                         "origem": origem, "proposta": {"arquivo": rel_proposta, "sha256": sha},
                         "decisao": {"arquivo": decisao.relative_to(pasta_projeto).as_posix(),
                                     "decisao_id": v.get("decisao_id"), "sha256_decisao": v.get("sha256_decisao")},
                         "arquivos": [_entrada_do_manifesto(item, modos[item["caminho"]]) for item in arquivos]}
            bruto_manifesto = (json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            GRAVACAO.criar(preparo / MANIFESTO_DA_VERSAO, bruto_manifesto)
            diferenca = _diferenca(em_uso / "atual", arquivos)
            anterior, tentativas = _trocar(em_uso, preparo)
        except BaseException:
            sobra = _apagar(preparo)
            if sobra:
                sys.stderr.write(json.dumps({"aviso": f"sobraram {sobra} itens em {preparo}: apague-os"},
                                            ensure_ascii=False) + "\n")
            raise
        # A versão nova já está em uso: o registro é o último passo e sua falha não desfaz a troca (código 3, não 2).
        falha = _anexar_registro(em_uso, {"acao": "promover", "proposta": rel_proposta, "proposta_sha256": sha,
                                          "decisao_id": v.get("decisao_id"), "sha256_decisao": v.get("sha256_decisao"),
                                          "anterior": anterior, "arquivos": len(arquivos),
                                          "manifesto_sha256": _sha256(bruto_manifesto),
                                          "tentativas_de_renomear": tentativas})
        copia = _publicar_estado_atual(em_uso, pasta_projeto, projeto)  # a âncora nova para a sessão (KIT-F1)
    return _avisar_copia({"promovida": True, "atual": str(em_uso / "atual"), "anterior": anterior,
                          "arquivos": len(arquivos), "diferenca": diferenca,
                          "manifesto_sha256": _sha256(bruto_manifesto), "tentativas_de_renomear": tentativas,
                          "registro": str(em_uso / "registro.jsonl") if falha is None else f"falhou: {falha}"},
                         pasta_projeto, copia)


def _avisar_copia(res: dict, pasta_projeto: Path, falha: str | None) -> dict:
    """O resultado do `promover` e do `voltar` diz onde ficou a cópia da âncora para a sessão, ou por que não ficou (no
    aviso, que também vai para o stderr: a troca aconteceu; o próximo propor da sessão do Ubuntu sai sem a âncora, e o
    promover o recusa e grava a cópia de novo)."""
    res["estado_para_a_sessao"] = str(pasta_projeto / ESTADO_PARA_A_SESSAO) if falha is None else f"falhou: {falha}"
    if falha is not None:
        aviso = (f"a cópia da âncora para a sessão ({ESTADO_PARA_A_SESSAO}) não foi gravada: {falha}; a próxima "
                 "proposta da sessão do Ubuntu sai sem ela, e o promover a recusa e grava a cópia de novo")
        res["aviso"] = f"{res['aviso']}; {aviso}" if res.get("aviso") else aviso
    return res


def pedir_volta(raiz, projeto: str, saida, *, para: str | None = None, motivo: str = "") -> dict:
    """A IA, na sessão: o pedido de volta (`fundacao.versao_em_uso.volta/1`) em `outputs/` do projeto, a entrega que o
    titular aceita e assina antes do `voltar` (pendência do FLUXOB-B ligada na integração da 1.7.10). A anterior pedida
    é conferida no `voltar`; o pedido leva a âncora da versão em uso, lida como no `propor` (de `em-uso/` ou da cópia da
    sessão), que o `voltar` confere (revisão 1 da correção do KIT-F1; com `--para` também, desde a revisão 3)."""
    raiz = Path(os.path.abspath(raiz))
    pasta_projeto = _pasta_do_projeto(raiz, projeto)
    saida = Path(os.path.abspath(saida))
    rel_saida = _rel_dentro(saida, pasta_projeto / "outputs", "--saida")
    if saida.suffix != ".json" or rel_saida == ".":
        raise Recusa("--saida é um arquivo .json dentro de outputs/ do projeto (o aceite assina uma entrega de lá)")
    if para is not None and not NOME_ANTERIOR.match(para):
        raise Recusa(f"--para {para!r}: use o nome de uma pasta em anteriores/ (letras, números, ponto e hífen)")
    if not str(motivo).strip():
        raise Recusa('--motivo "...": as palavras do titular vão no pedido que ele assina')
    if _com_invisivel(str(motivo)):  # revisão 2 da correção do KIT-F1: o voltar o recusaria
        raise Recusa("--motivo com caractere de controle, de formatação ou separador de linha (U+2028, U+2029, U+0085, "
                     "quebra de linha): escreva as palavras do titular numa linha só")
    pedido = {"schema_version": ESQUEMA_VOLTA, "projeto": projeto, "para": para, "motivo": str(motivo).strip(),
              "pedido_id": secrets.token_hex(8), "criado_em": _instante(),  # pedido_id: um aceite, uma volta
              **_ancora_lida(raiz, projeto, pasta_projeto)}
    bruto = (json.dumps(pedido, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    GRAVACAO.pasta_sem_ligacao(pasta_projeto, Path("outputs", rel_saida).parent.as_posix())
    GRAVACAO.publicar(saida, bruto)
    sha, entrega = _sha256(bruto), Path("outputs", rel_saida).as_posix()
    return {"pedido": str(saida), "sha256": sha, "entrega": entrega, "para": para or "a anterior mais recente",
            "proximos_passos": [
                f'python -m fundacao tarefa criar --projeto {projeto} --objetivo "voltar a versão em uso"',
                f"python -m fundacao decisao preparar --projeto {projeto} --tarefa <task_id> --tipo aceite "
                f'--entrega {entrega} --motivo "<as palavras do titular>"',
                passo_do_titular("voltar", raiz, projeto, "pedido", saida, sha)]}


_REUSO = {"pedido": "este pedido (ou esta decisão) já pôs uma anterior de volta: um aceite vale para uma volta só; "
                    "peça outra volta (pedir-volta) e o aceite dela; nada foi trocado",
          "proposta": "esta proposta (ou esta decisão) já fez uma troca da versão em uso: um aceite vale para uma "
                      "promoção só; proponha de novo (propor) e peça o aceite dela; nada foi trocado"}


def _recusar_aceite_usado(em_uso: Path, sha_entrega: str, v: dict, oque: str = "pedido") -> None:
    """Um aceite vale para uma troca só: a entrega (o pedido ou, desde o KIT-F1, a proposta) ou a decisão que já fez
    uma troca é recusada."""
    usados = _ja_usados(em_uso / "registro.jsonl")
    if sha_entrega in usados or (v.get("sha256_decisao") and str(v.get("sha256_decisao")) in usados):
        raise Recusa(_REUSO[oque])


def validar_pedido(dados, projeto: str, *, agora: datetime | None = None) -> tuple[str | None, str, datetime]:
    """(anterior pedida ou None para a mais recente, motivo, data do pedido) do pedido de volta. A data (`criado_em`,
    ISO com fuso) é obrigatória: sem `--para`, ela diz qual era a anterior mais recente, e por isso não pode estar no
    futuro além da folga do relógio (`FOLGA_DO_RELOGIO`): quem grava o pedido é a sessão, e com a data no futuro
    nenhuma promoção posterior a ele recusaria o voltar [segunda revisão do pacote INTEG-FLUXOB]. Com `--para`, a data
    não escolhe nada (e a diferença de relógio entre a sessão e o terminal do titular não recusa): o que prende o
    pedido, com ou sem `--para`, à versão em uso de quando foi feito é a âncora (revisão 3 da correção do KIT-F1)."""
    if not isinstance(dados, dict) or dados.get("schema_version") != ESQUEMA_VOLTA:
        raise Recusa(f"pedido fora do formato {ESQUEMA_VOLTA}")
    if dados.get("projeto") != projeto:
        raise Recusa(f"o pedido é do projeto {dados.get('projeto')!r}, não de {projeto}")
    para, motivo, criado_em = dados.get("para"), dados.get("motivo"), _data_iso(dados.get("criado_em"))
    if para is not None and (not isinstance(para, str) or not NOME_ANTERIOR.match(para)):
        raise Recusa("pedido com a anterior (para) fora do formato: o nome de uma pasta em anteriores/")
    if not isinstance(motivo, str) or not motivo.strip():
        raise Recusa("pedido sem motivo")
    if _com_invisivel(motivo):  # vai para o registro (revisão 2 da correção do KIT-F1: linha partida por U+2028)
        raise Recusa("pedido com o motivo fora do formato (caractere de controle, de formatação, substituto isolado ou "
                     "separador de linha, como U+2028): faça-o de novo com pedir-volta; nada foi trocado")
    if criado_em is None:
        raise Recusa("pedido sem a data (criado_em, ISO com fuso): faça-o de novo com pedir-volta")
    if para is None and criado_em > (agora or datetime.now(timezone.utc)) + FOLGA_DO_RELOGIO:
        raise Recusa("pedido sem --para com data no futuro (criado_em): a anterior mais recente da data dele não se "
                     "confere; faça-o de novo com pedir-volta (ou com --para <nome em anteriores/>); nada foi trocado")
    _exigir_ancora_no_formato(dados, "pedido")
    return para, motivo.strip(), criado_em


def voltar(raiz, projeto: str, pedido, pedido_sha256: str, decisao, *, verificar=None) -> dict:
    """O titular, no terminal dele: põe de volta a anterior do pedido aceito e assinado, conferida como no `promover`
    (`_conferir_aceite`); um aceite vale para uma volta só, e o pedido, com ou sem `--para` (com ele desde a revisão 3
    da correção do KIT-F1), não vale depois de uma promoção ou volta posterior a ele (a âncora:
    `_recusar_entrega_vencida`). Nada é trocado antes das conferências."""
    verificar = verificar or verificar_decisao_pelo_kit
    raiz = Path(os.path.abspath(raiz))
    pasta_projeto = _pasta_do_projeto(raiz, projeto)
    rel_pedido, sha, dados = _ler_entrega(pedido, pasta_projeto, pedido_sha256, "pedido")
    para, motivo, criado_em = validar_pedido(dados, projeto)
    v, _decisao = _conferir_aceite(raiz, pasta_projeto, decisao, rel_pedido, sha, verificar, "pedido")
    em_uso = _em_uso(raiz, projeto)
    anteriores = em_uso / "anteriores"
    if _e_ligacao(em_uso) or _e_ligacao(anteriores) or not anteriores.is_dir():
        raise Recusa(f"não há versão anterior de {projeto} para voltar")
    _recusar_aceite_usado(em_uso, sha, v)
    # O pedido, com ou sem --para, vale para a volta a partir da versão em uso de quando foi feito (revisão 3 da
    # correção do KIT-F1: o pedido com --para, assinado e não usado, punha a versão pedida no lugar de outra que entrou
    # depois dele, sem assinatura nova; a âncora ele já levava).
    _recusar_entrega_vencida(em_uso, pasta_projeto, projeto, dados, criado_em, "pedido")
    nomes = sorted(n for n in os.listdir(anteriores) if (anteriores / n).is_dir() and not _e_ligacao(anteriores / n))
    escolhida = para or (nomes[-1] if nomes else None)
    if not escolhida or escolhida not in nomes:
        raise Recusa(f"anterior {escolhida!r} inexistente; há: {', '.join(nomes) or 'nenhuma'}")
    conferencia = conferir_pasta(anteriores / escolhida)
    if _difere(conferencia):  # com a dica, como no conferir (revisão 1 da correção do KIT-F5)
        dica = _avisar(dict(conferencia)).get("dica")
        raise Recusa(f"a anterior {escolhida} difere do manifesto dela: {json.dumps(conferencia)[:400]}"
                     + (f"; {dica}" if dica else ""))
    ativos = _ativos(em_uso / "registro.jsonl")
    if ativos is not None and conferencia["manifesto_sha256"] not in ativos:
        raise Recusa(f"a anterior {escolhida} tem um manifesto que nenhuma promoção do registro pôs em uso: confira-a")
    with _trava(em_uso):
        _conferir_registro(em_uso)  # antes da troca, como no promover: registro inválido recusa sem mexer em atual
        _recusar_aceite_usado(em_uso, sha, v)  # de novo, já com a trava: duas voltas com o mesmo aceite, uma só passa
        # e nenhuma troca entrou entre a conferência de cima e a trava (com ou sem --para: revisão 3 da correção)
        _recusar_entrega_vencida(em_uso, pasta_projeto, projeto, dados, criado_em, "pedido")
        saiu, tentativas = _trocar(em_uso, anteriores / escolhida)
        falha = _anexar_registro(em_uso, {"acao": "voltar", "para": escolhida, "saiu_para": saiu, "motivo": motivo,
                                          "pedido": rel_pedido, "pedido_sha256": sha,
                                          "decisao_id": v.get("decisao_id"), "sha256_decisao": v.get("sha256_decisao"),
                                          "manifesto_sha256": conferencia["manifesto_sha256"],
                                          "tentativas_de_renomear": tentativas})
        copia = _publicar_estado_atual(em_uso, pasta_projeto, projeto)  # a âncora nova para a sessão (KIT-F1)
    return _avisar_copia(_avisar({"voltou": True, "atual": str(em_uso / "atual"), "de_anteriores": escolhida,
                                  "a_que_saiu": saiu,
                                  "registro": str(em_uso / "registro.jsonl") if falha is None else f"falhou: {falha}",
                                  "nao_conferido": conferencia["nao_conferido"]}), pasta_projeto, copia)


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("propor", help="lista com SHA-256 dos arquivos da pasta de trabalho (a IA)")
    p.add_argument("--raiz", type=Path, required=True)
    p.add_argument("--projeto", required=True)
    p.add_argument("--de", type=Path, required=True, help="pasta de trabalho dentro de projects/<projeto>/")
    p.add_argument("--lista", type=Path, required=True, help="arquivo com os globs, um por linha")
    p.add_argument("--saida", type=Path, required=True, help="proposta .json em projects/<projeto>/outputs/")
    m = sub.add_parser("promover", help="põe a proposta aceita em uso (o titular, fora do Claude)")
    m.add_argument("--raiz", type=Path, required=True)
    m.add_argument("--projeto", required=True)
    m.add_argument("--proposta", type=Path, required=True)
    m.add_argument("--proposta-sha256", required=True)
    m.add_argument("--decisao", type=Path, required=True, help="aceite assinado em projects/<projeto>/decisoes/")
    q = sub.add_parser("pedir-volta", help="o pedido de volta para o aceite do titular (a IA)")
    q.add_argument("--raiz", type=Path, required=True)
    q.add_argument("--projeto", required=True)
    q.add_argument("--saida", type=Path, required=True, help="pedido .json em projects/<projeto>/outputs/")
    q.add_argument("--para", help="nome em anteriores/ (padrão: a mais recente; promoção ou volta depois do pedido o "
                                  "invalida)")
    q.add_argument("--motivo", required=True, help="as palavras do titular")
    v = sub.add_parser("voltar", help="põe de volta a anterior do pedido aceito (o titular, fora do Claude)")
    v.add_argument("--raiz", type=Path, required=True)
    v.add_argument("--projeto", required=True)
    v.add_argument("--pedido", type=Path, required=True, help="o pedido de volta, em projects/<projeto>/outputs/")
    v.add_argument("--pedido-sha256", required=True)
    v.add_argument("--decisao", type=Path, required=True, help="aceite assinado em projects/<projeto>/decisoes/")
    c = sub.add_parser("conferir", help="confere a versão em uso contra o manifesto dela")
    c.add_argument("--raiz", type=Path, required=True)
    c.add_argument("--projeto", required=True)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "propor":
            res = propor(args.raiz, args.projeto, args.de, args.lista, args.saida)
        elif args.cmd == "promover":
            res = promover(args.raiz, args.projeto, args.proposta, args.proposta_sha256, args.decisao)
        elif args.cmd == "pedir-volta":
            res = pedir_volta(args.raiz, args.projeto, args.saida, para=args.para, motivo=args.motivo)
        elif args.cmd == "voltar":
            res = voltar(args.raiz, args.projeto, args.pedido, args.pedido_sha256, args.decisao)
        else:
            res = conferir(args.raiz, args.projeto)
    except (Recusa, OSError) as exc:
        print(json.dumps({"erro": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if res.get("aviso"):  # o que não foi conferido também no stderr, onde o envoltório registra (KIT-F5)
        print(json.dumps({"aviso": res["aviso"]}, ensure_ascii=False), file=sys.stderr)
    if args.cmd == "conferir" and not res["ok"]:
        return 1
    if args.cmd in ("promover", "voltar") and str(res.get("registro", "")).startswith("falhou:"):
        return 3  # a troca aconteceu, mas o registro não foi gravado: não é a recusa de código 2
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
