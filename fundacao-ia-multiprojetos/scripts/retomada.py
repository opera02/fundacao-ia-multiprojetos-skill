#!/usr/bin/env python3
"""Registro de retomada (livro Apêndice E §3; continuidade entre sessões e provedores).

  criar    --saida RETOMADA.md   copia o modelo (não sobrescreve)
  validar  --arquivo RETOMADA.md exige os campos mínimos preenchidos (faltas -> código 1)
  arquivar --arquivo RETOMADA.md --historico <pasta> [--nome <arquivo>]
           guarda a versão inteira (não sobrescreve), confere byte a byte e acrescenta o ponteiro
           "Histórico arquivado: <caminho> (sha256 <hash>)"; depois, reescreva o índice de forma enxuta

Campos mínimos: objetivo, versão, estado confirmado, evidências, bloqueios,
próxima ação e efeitos já realizados (que não devem ser repetidos), além de
identificação do projeto/execução e arquivos mínimos para leitura.
Um campo vazio ou que ainda contenha "(preencher" conta como ausente. Use "nenhum" quando
não houver item — isso é uma informação, não uma omissão.

A validação é ESTRUTURAL: confere o preenchimento; não autentica quem escreveu, não confirma
evidências e não torna válida nenhuma autorização — o arquivo é índice de estado, não fonte de
permissão (auditoria da 1.4.1, A17). Sem "Origem das autorizações" preenchida, a saída traz um
aviso, que não bloqueia.

Índice enxuto (análise do vibe-coding-toolkit, 21/10/2026, proposta 7): acima de 12 KB, 150 linhas ou linha com
mais de 600 caracteres, o `validar` avisa (não bloqueia) e indica o `arquivar`. Ponteiro para histórico ausente
ou alterado reprova; e cada item de "Ações já realizadas que não devem ser repetidas" de um histórico arquivado
precisa continuar listado no índice — conferido pela parte do item antes do primeiro ":" (resumir o resto pode).

O histórico fica na pasta da RETOMADA (auditoria Codex Security da 1.7.6, #7): ponteiro absoluto, com unidade, `:`
ou `..` reprova sem tocar o disco; cada parte do caminho é conferida sem seguir ligação (link simbólico ou junção),
e o arquivo, comum e de até 5 MB, é lido uma vez — o texto conferido pelo hash é o mesmo de onde saem os itens. O
`arquivar` recusa pasta de histórico fora da pasta da RETOMADA ou que passe por ligação, e `--nome` com caminho.

Ponteiro para caminho protegido não é lido (revisão de segurança da 1.7.7, R177-VAL-01), pelo mesmo critério do
`matriz.py validar`: primeira parte `state`, `projects/<projeto>/data/` e os nomes da lista de negação dos perfis do
host, comparados como o Windows compara; a recusa vem antes de tocar o disco e não diz se o alvo existe (o estado do
ponteiro era oráculo de existência e de tamanho). O `arquivar` não grava histórico em caminho protegido. Histórico com
vínculo físico (hard link, mais de um nome) não é lido: o outro nome pode estar fora da pasta (R177-VAL-02).

A pasta da RETOMADA faz o papel da base e não tira a proteção (revisão de segurança da 1.7.7, segunda passada, variante
do R177-VAL-01): a regra vale também para o caminho inteiro, relativo a cada raiz de fundação acima dele — a pasta com
`registry/` ou com `state/state.sqlite`, de que só a existência é consultada. Antes, a RETOMADA acima da raiz, em
`state/` ou no `data/` de um projeto lia o histórico protegido e entregava os itens dele.

Nem fora de uma fundação (revisão de segurança da 1.7.7, terceira passada, R177C-B-01): com a pasta da RETOMADA cujo
caminho real passa por nome da lista de negação (`.ssh`, `.codex`, `secrets`...) ou por nome curto 8.3, em qualquer
parte e comparado como o Windows compara, o `validar` e o `arquivar` recusam antes de abrir a RETOMADA, com a mesma
resposta exista ela ou não; o ponteiro e o destino do histórico passam pela mesma conferência. Antes, uma RETOMADA em
`~/.ssh` conferia o hash de qualquer arquivo de lá ("conferido" ou "alterado") e entregava os itens do histórico.

Acima da raiz, só o que o host nega lá (revisão de segurança da 1.7.7, quarta passada, R177D-1): as regras dos perfis
são `./**/...`, relativas à raiz da fundação; com uma raiz acima, valem as partes relativas a ela, e o caminho inteiro
só é conferido sem raiz nenhuma — salvo `.ssh` e `.codex`, que os perfis negam em `~/` e valem em qualquer lugar.
Antes, a RETOMADA da fundação na conta "Secretaria" (casa `*secret*`) era recusada no `validar` e no `arquivar`.

O próprio arquivo também (revisão de segurança da 1.7.7, quarta passada, R177D-2): o nome da RETOMADA passa pela mesma
regra antes de qualquer leitura — `.env`, `.credentials.json`, `secrets` ou `chave.pem` recusados, exista ou não o
arquivo —; ela é lida sem seguir ligação, sem vínculo físico (no lstat e, depois de abrir, no fstat) e com o teto do
histórico, e o `arquivar` a reescreve por temporário e troca de nome (`gravacao_segura.publicar`), nunca através do
nome. Antes, `arquivar --arquivo <pasta comum>/.env` copiava o conteúdo inteiro para o histórico e inseria o ponteiro
no original, e a RETOMADA que era vínculo físico de `.ssh/id_ed25519` alterava a chave.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:  # carregado por caminho (testes): o módulo vizinho também tem de ser achado
    sys.path.append(str(AQUI))
import gravacao_segura as gravacao  # noqa: E402  (reescrita sem seguir ligação nem vínculo físico; R177D-2)

TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "templates" / "RETOMADA.md"
REQUIRED = {
    "project_id": r"^project_id:",
    "run_id de referência": r"^run_id de referência:",
    "objetivo atual": r"^Objetivo atual:",
    "versão do código/configuração": r"^Versão do código/configuração:",
    "estado confirmado": r"^Estado confirmado:",
    "evidências": r"^Evidências:",
    "arquivos mínimos para leitura": r"^Arquivos mínimos para leitura:",
    "bloqueios": r"^Bloqueios de acesso, custo ou decisão:",
    "próxima ação autorizada": r"^Próxima ação autorizada:",
    "efeitos já realizados": r"^Ações já realizadas que não devem ser repetidas:",
    "última conferência": r"^Última conferência do registro:",
}
ORIGEM = r"^Origem das autorizações:"
EFEITOS = r"^Ações já realizadas que não devem ser repetidas:"
CAMPO = re.compile(r"^[A-Za-zÀ-ú_ /]+:")
PONTEIRO = re.compile(r"^Histórico arquivado:\s*(?P<caminho>\S+)\s+\(sha256 (?P<sha>[0-9a-f]{64})\)")
LIMITE_BYTES, LIMITE_LINHAS, LIMITE_LINHA = 12_000, 150, 600
VALIDACAO = "estrutural (preenchimento): não autentica autor, autorizações nem evidências"
TETO_HISTORICO = 5_000_000  # bytes de um histórico arquivado (a maior RETOMADA real tinha 38 KB)
BLOCO = 1 << 20
# Windows: etiqueta de ponto de nova análise "substituta de nome" (bit 29) — junção, link simbólico e afins.
SUBSTITUTA_DE_NOME = 0x20000000
# Os mesmos de `matriz.py` (o teste da revisão de segurança da 1.7.7 confere que valem igual): nomes que os perfis
# do host negam à leitura, em qualquer parte abaixo da raiz; mais a primeira parte `state` e `projects/<projeto>/data/`.
# `NOMES_DO_PERFIL`: os que os perfis negam também em `~/`, que valem acima da raiz também (quarta passada, R177D-1).
NOMES_DO_PERFIL = (".ssh", ".codex")
NOMES_PROTEGIDOS = (".env*", "secrets", "*.pem", "*.key", "*.pfx", "*.p12", "id_rsa*", "*credentials*", "*secret*",
                    "*.kdbx", "auth.json") + NOMES_DO_PERFIL
CURTO_8_3 = re.compile(r"~\d")  # nome curto do Windows (ENV~1): apelido de um nome longo
PROTEGIDO = "caminho protegido (segredo, estado ou dados de projeto, que o host nega à leitura): não lido"


class AcimaDoTeto(Exception):
    pass


class Trocado(OSError):
    """O arquivo aberto não é o examinado: virou ligação, deixou de ser comum ou resolve fora da pasta."""


class VinculoFisico(OSError):
    """Arquivo com mais de um nome (hard link): o conteúdo pode ser o de um arquivo de fora da pasta (R177-VAL-02)."""


def field_value(lines: list[str], pattern: str) -> str:
    for idx, line in enumerate(lines):
        if re.match(pattern, line.strip()):
            value = line.split(":", 1)[1].strip()
            nxt = idx + 1
            while not value and nxt < len(lines) and lines[nxt].strip() and not re.match(r"^[A-Za-zÀ-ú_ /]+:", lines[nxt].strip()):
                value = lines[nxt].strip()
                nxt += 1
            if not value and nxt < len(lines):
                follow = []
                while nxt < len(lines) and re.match(r"^\s*(\d+\.|-)\s+\S", lines[nxt]):
                    follow.append(lines[nxt].strip())
                    nxt += 1
                value = " ".join(follow)
            return value
    return ""


def secao(lines: list[str], pattern: str) -> list[str]:
    """Linhas de um campo de várias linhas: da linha do campo até o próximo campo."""
    for idx, line in enumerate(lines):
        if re.match(pattern, line.strip()):
            fim = idx + 1
            while fim < len(lines) and not CAMPO.match(lines[fim].strip()):
                fim += 1
            return lines[idx:fim]
    return []


def itens_nao_repetir(lines: list[str]) -> list[str]:
    """Chave de cada item de "Ações já realizadas...": o texto do item antes do primeiro ":" (até 100 caracteres)."""
    itens = []
    for line in secao(lines, EFEITOS)[1:]:
        if line.strip().startswith("- "):
            texto = " ".join(line.strip()[2:].split())
            itens.append(texto.split(":", 1)[0].strip()[:100])
    return itens


def e_ligacao(st: os.stat_result) -> bool:
    """Link simbólico ou junção (e afins do Windows), pelo lstat — sem seguir a ligação."""
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & SUBSTITUTA_DE_NOME)


def partes_relativas(texto: str) -> list[str] | None:
    """Partes de um caminho relativo que não sai da pasta, ou None: raiz, unidade (`C:`), UNC, `:` e `..` (ou parte só
    de pontos e espaços) são recusados antes de qualquer acesso ao disco — a recusa não revela se o alvo existe."""
    texto = texto.replace(chr(92), "/")
    if not texto or texto.startswith("/") or ":" in texto or "\0" in texto:
        return None
    partes = [p for p in texto.split("/") if p not in ("", ".")]
    return partes if partes and all(p.strip(". ") for p in partes) else None


def _nome(parte: str) -> str:
    """O nome como o Windows o compara: sem ponto nem espaço no fim e sem diferença de caixa."""
    return parte.rstrip(". ").casefold()


def negado(nomes) -> bool:
    """Algum nome (já comparável, de `_nome`) da lista de negação dos perfis do host ou nome curto 8.3: a regra das
    partes relativas, a mesma no caminho inteiro (terceira passada, R177C-B-01)."""
    return any(CURTO_8_3.search(n) or any(fnmatch.fnmatchcase(n, g) for g in NOMES_PROTEGIDOS) for n in nomes)


def protegido(pasta: Path, partes) -> bool:
    """Caminho (partes relativas à pasta) que o host nega à leitura, decidido pelo texto, sem tocar o disco
    (R177-VAL-01): primeira parte `state`, nome da lista de negação ou nome curto 8.3 em qualquer parte, ou
    `projects/<projeto>/data` que chegue à parte relativa."""
    nomes = [_nome(p) for p in partes]
    if not nomes or nomes[0] == "state" or negado(nomes):
        return True
    todas = [_nome(p) for p in Path(pasta).parts] + nomes
    return any(todas[i] == "projects" and todas[i + 2] == "data"
               for i in range(max(0, len(todas) - len(nomes) - 2), len(todas) - 2))


def raizes_acima(pasta: Path, vistas: dict | None = None) -> list[Path]:
    """`pasta` e as de cima com a forma de raiz de fundação — `registry/` ou `state/state.sqlite` —, da mais próxima à
    mais distante. Só a existência das duas é consultada; `vistas` guarda o que já foi visto numa varredura."""
    vistas = {} if vistas is None else vistas
    achadas = []
    for p in (pasta, *pasta.parents):
        if p not in vistas:
            vistas[p] = os.path.isdir(p / "registry") or os.path.isfile(p / "state" / "state.sqlite")
        if vistas[p]:
            achadas.append(p)
    return achadas


def _partes(caminho) -> list[str]:
    return [_nome(p) for p in re.split(r"[\\/]", str(caminho)) if p]


def negado_no_perfil(caminho) -> bool:
    """Alguma parte do caminho é um dos `NOMES_DO_PERFIL` (`.ssh`, `.codex`), que os perfis do host negam em `~/` e não
    só abaixo da raiz: vale em qualquer lugar, acima da raiz da fundação também (quarta passada, R177D-1). Os nomes
    saem da própria lista de negação. Decidido pelo texto: nada é consultado no disco."""
    globos = [g for g in NOMES_PROTEGIDOS if g in NOMES_DO_PERFIL]
    return any(fnmatch.fnmatchcase(n, g) for n in _partes(caminho) for g in globos)


def caminho_negado(caminho, raizes=()) -> bool:
    """O caminho (o real, que quem chama já resolveu) passa por nome que o host nega à leitura. Sem raiz de fundação
    acima (`raizes` vazio), em qualquer parte (terceira passada, R177C-B-01); com raiz, as partes relativas a ela ficam
    com `protegido`, e aqui só os `NOMES_DO_PERFIL` — o host nega `./**/...`, relativo à raiz, e a conta "Secretaria"
    acima dela não é negada (quarta passada, R177D-1). Decidido pelo texto: nada é consultado no disco."""
    return negado_no_perfil(caminho) or not raizes and negado(_partes(caminho))


def protegido_na_fundacao(pasta: Path, partes, vistas: dict | None = None) -> bool:
    """`protegido` relativo à pasta e também no caminho inteiro (pasta real + partes), relativo a cada raiz de fundação
    acima dele: RETOMADA dentro de `state/` ou de `projects/<p>/data/`, ou acima da raiz, não tira a proteção (variante
    do R177-VAL-01); nem a pasta negada sem raiz acima (R177C-B-01), e com raiz, só o relativo a ela (R177D-1). O texto
    decide primeiro, sem tocar o disco; depois, só a existência de `registry/` e de `state/state.sqlite` acima do alvo
    é consultada — nada é lido."""
    if protegido(pasta, partes):
        return True
    alvo = Path(os.path.realpath(pasta)).joinpath(*partes)
    raizes = raizes_acima(alvo.parent, vistas)
    if caminho_negado(alvo, raizes):  # sem raiz acima, o caminho inteiro (R177C-B-01); com raiz, o relativo (R177D-1)
        return True
    return any(protegido(r, alvo.relative_to(r).parts) for r in raizes)


def pasta_recusada(arquivo: Path) -> str | None:
    """Por que a RETOMADA não vale, ou None: o próprio nome do arquivo é da lista de negação, que o host nega em
    qualquer lugar abaixo da raiz (quarta passada, R177D-2), ou a pasta real dela cai em caminho que o host nega —
    `.ssh` e `.codex` em qualquer lugar, o resto sem raiz de fundação acima (R177C-B-01 e R177D-1). Decidido antes de
    abrir a RETOMADA ou o histórico: a resposta não diz se existem."""
    pasta = Path(os.path.realpath(Path(arquivo).parent))
    if negado([_nome(Path(arquivo).name)]) or negado_no_perfil(pasta) or caminho_negado(pasta, raizes_acima(pasta)):
        return ("a RETOMADA fica em caminho que o host nega à leitura (nome de segredo da lista de negação ou nome "
                "curto 8.3): nada foi lido nem gravado")
    return None


def ler_retomada(arquivo: Path) -> bytes:
    """A RETOMADA, lida como o histórico: sem seguir ligação nem vínculo físico (no lstat e, depois de abrir, no fstat),
    dentro da pasta dela e até 5 MB — um vínculo físico de `.ssh/id_ed25519` numa pasta comum fazia o `arquivar` copiar
    a chave e reescrevê-la (quarta passada, R177D-2). Recusa: `AcimaDoTeto` ou OSError (`VinculoFisico`, `Trocado`)."""
    return ler_contido(Path(arquivo), Path(os.path.realpath(Path(arquivo).parent)), TETO_HISTORICO)


def recusa_da_leitura(exc: BaseException) -> str:
    """Por que a RETOMADA não foi lida, para a saída (R177D-2)."""
    if isinstance(exc, VinculoFisico):
        return "a RETOMADA tem vínculo físico (hard link) com outro nome: nada foi lido nem gravado; copie o arquivo"
    if isinstance(exc, Trocado):
        return "a RETOMADA é ligação (link simbólico ou junção) ou não é arquivo comum: nada foi lido nem gravado"
    if isinstance(exc, AcimaDoTeto):
        return f"RETOMADA acima de {TETO_HISTORICO // 1_000_000} MB: nada foi lido nem gravado; reduza o índice antes"
    return f"RETOMADA ilegível ({type(exc).__name__}): nada foi lido nem gravado"


def nome_real_protegido(pasta: Path, alvo: Path) -> bool:
    """O nome no disco (o Windows resolve caixa, nome curto e ponto no fim) também não pode ser protegido."""
    try:
        real = Path(os.path.realpath(pasta))
        return protegido_na_fundacao(real, Path(os.path.realpath(alvo)).relative_to(real).parts)
    except (OSError, ValueError):
        return True


def falha_no_caminho(pasta: Path, partes) -> str | None:
    """Desce da pasta parte por parte com lstat, sem seguir: "ligacao" se alguma parte que existe é ligação, "ausente"
    se falta uma parte ou se uma do meio não é pasta, None se o caminho inteiro existe sem ligação."""
    atual = pasta
    for i, parte in enumerate(partes):
        atual = atual / parte
        try:
            st = os.lstat(atual)
        except OSError:
            return "ausente"
        if e_ligacao(st):
            return "ligacao"
        if i < len(partes) - 1 and not stat.S_ISDIR(st.st_mode):
            return "ausente"
    return None


def ler_contido(p: Path, pasta_real: Path, teto: int) -> bytes:
    """Lê o arquivo comum `p` em blocos, até `teto` bytes (passou: AcimaDoTeto). Abre sem seguir ligação na folha
    (POSIX) e sem esperar em FIFO; depois de abrir, confere que é o arquivo do lstat e que resolve dentro da pasta.
    Arquivo com vínculo físico (mais de um nome, no lstat ou no fstat) não é lido: VinculoFisico."""
    st = os.lstat(p)
    if e_ligacao(st) or not stat.S_ISREG(st.st_mode):
        raise Trocado(f"não é arquivo comum: {p.name}")
    if st.st_nlink > 1:
        raise VinculoFisico(f"vínculo físico: {p.name}")
    fd = os.open(p, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0))
    try:
        aberto = os.fstat(fd)
        if aberto.st_nlink > 1:
            raise VinculoFisico(f"vínculo físico: {p.name}")
        if (not stat.S_ISREG(aberto.st_mode) or (aberto.st_dev, aberto.st_ino) != (st.st_dev, st.st_ino)
                or not Path(os.path.realpath(p)).is_relative_to(pasta_real)):
            raise Trocado(f"mudou entre o exame e a leitura: {p.name}")
        dados = bytearray()
        while bloco := os.read(fd, min(BLOCO, teto + 1 - len(dados))):
            dados += bloco
            if len(dados) > teto:
                raise AcimaDoTeto
        return bytes(dados)
    finally:
        os.close(fd)


def ler_historico(pasta: Path, caminho: str, sha: str) -> tuple[str, str | None]:
    """Estado do histórico apontado e, se conferido, o texto que foi conferido pelo hash."""
    partes = partes_relativas(caminho)
    if partes is None:
        return "fora da pasta da RETOMADA: não lido", None
    if protegido_na_fundacao(pasta, partes):  # antes de tocar o alvo: a resposta não diz se ele existe (R177-VAL-01)
        return PROTEGIDO, None
    falha = falha_no_caminho(pasta, partes)
    if falha:
        return ("ligação (link simbólico ou junção): não seguida" if falha == "ligacao" else "ausente"), None
    alvo = pasta.joinpath(*partes)
    if nome_real_protegido(pasta, alvo):
        return PROTEGIDO, None
    try:
        dados = ler_contido(alvo, pasta.resolve(), TETO_HISTORICO)
    except AcimaDoTeto:
        return f"acima do teto de {TETO_HISTORICO // 1_000_000} MB: não lido", None
    except VinculoFisico:  # R177-VAL-02
        return "vínculo físico (hard link) com outro nome: não lido", None
    except OSError:
        return "não é arquivo comum ou ilegível", None
    if hashlib.sha256(dados).hexdigest() != sha:
        return "alterado", None
    return "conferido", dados.decode("utf-8", errors="replace")


def historicos(arquivo: Path, lines: list[str]) -> list[dict]:
    pasta = Path(os.path.abspath(arquivo.parent))
    out = []
    for line in lines:
        m = PONTEIRO.match(line.strip())
        if not m:
            continue
        estado, texto = ler_historico(pasta, m.group("caminho"), m.group("sha"))
        out.append({"caminho": m.group("caminho"), "sha256": m.group("sha"), "estado": estado, "_texto": texto})
    return out


def tamanho(texto: str, lines: list[str]) -> tuple[dict, list[str]]:
    medida = {"bytes": len(texto.encode("utf-8")), "linhas": len(lines),
              "maior_linha": max((len(l) for l in lines), default=0)}
    avisos = []
    if medida["bytes"] > LIMITE_BYTES:
        avisos.append(f"índice grande: {medida['bytes']} bytes (limite sugerido {LIMITE_BYTES // 1000} KB)")
    if medida["linhas"] > LIMITE_LINHAS:
        avisos.append(f"índice longo: {medida['linhas']} linhas (limite sugerido {LIMITE_LINHAS} linhas)")
    if medida["maior_linha"] > LIMITE_LINHA:
        avisos.append(f"linha com {medida['maior_linha']} caracteres (limite sugerido {LIMITE_LINHA} caracteres)")
    if avisos:
        avisos.append("arquive o histórico (retomada.py arquivar) e deixe o índice só com o estado atual e uma "
                      "linha por efeito já realizado")
    return medida, avisos


def validar(arquivo: Path) -> dict:
    try:  # sem seguir ligação nem vínculo físico, com teto (R177D-2); as quebras de linha como as do read_text
        texto = ler_retomada(arquivo).decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except (AcimaDoTeto, OSError, ValueError) as exc:
        return {"ok": False, "erro": recusa_da_leitura(exc), "validacao": VALIDACAO}
    lines = texto.splitlines()
    missing = []
    for name, pattern in REQUIRED.items():
        value = field_value(lines, pattern)
        if not value or "(preencher" in value:
            missing.append(name)
    origem = field_value(lines, ORIGEM)
    avisos = [] if origem and "(preencher" not in origem else [
        "origem das autorizações não registrada: permissões e próxima ação valem só se confirmadas na conversa atual"]
    medida, avisos_tamanho = tamanho(texto, lines)
    avisos += avisos_tamanho
    hist = historicos(arquivo, lines)
    atuais = set(itens_nao_repetir(lines))
    ausentes = []
    for h in hist:
        if h["estado"] == "conferido":  # o mesmo texto que o hash conferiu (lido uma vez)
            antigos = itens_nao_repetir(h["_texto"].splitlines())
            ausentes += [i for i in antigos if i not in atuais and i not in ausentes]
    ok = not missing and all(h["estado"] == "conferido" for h in hist) and not ausentes
    return {"ok": ok, "campos_ausentes": missing, "avisos": avisos, "tamanho": medida,
            "historicos": [{k: v for k, v in h.items() if k != "_texto"} for h in hist],
            "itens_do_historico_ausentes": ausentes, "validacao": VALIDACAO}


def arquivar(arquivo: Path, pasta: Path, nome: str | None) -> tuple[int, dict]:
    try:  # sem seguir ligação nem vínculo físico, até o teto do histórico, que o validar leria (R177D-2)
        original = ler_retomada(arquivo)
    except (AcimaDoTeto, OSError) as exc:
        return 1, {"ok": False, "erro": recusa_da_leitura(exc)}
    nome = nome or f"RETOMADA-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.md"
    if partes_relativas(nome) != [nome]:
        return 1, {"ok": False, "erro": f"--nome '{nome}' precisa ser só o nome do arquivo (sem pasta, '..' nem ':')"}
    # O histórico fica na pasta da RETOMADA e não passa por ligação: o ponteiro é sempre relativo e o validar o confere.
    raiz = Path(os.path.abspath(arquivo.parent))
    try:
        partes = Path(os.path.abspath(pasta)).relative_to(raiz).parts
    except ValueError:
        return 1, {"ok": False, "erro": f"a pasta do histórico ({pasta}) fica fora da pasta da RETOMADA; nada foi "
                                        "alterado (use, por exemplo, evidence/retomada)"}
    rel = "/".join((*partes, nome))
    if partes_relativas(rel) != [*partes, nome]:
        return 1, {"ok": False, "erro": f"a pasta do histórico ({pasta}) tem nome que o validar recusa ('..', ':' ou "
                                        "só pontos); nada foi alterado"}
    if protegido_na_fundacao(raiz, [*partes, nome]):  # o validar não leria o histórico (R177-VAL-01 e a variante)
        return 1, {"ok": False, "erro": f"o histórico ({rel}) ficaria em caminho protegido (segredo, estado ou dados "
                                        "de projeto), que o validar não lê; nada foi alterado"}
    if falha_no_caminho(raiz, partes) == "ligacao":  # "ausente" serve: o que falta é criado abaixo, sem ligação
        return 1, {"ok": False, "erro": f"a pasta do histórico ({pasta}) passa por ligação (link simbólico ou "
                                        "junção); nada foi alterado"}
    destino = raiz.joinpath(*partes, nome)
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return 1, {"ok": False, "erro": f"a pasta do histórico ({pasta}) não pôde ser usada: {type(exc).__name__}"}
    try:  # O_EXCL: não sobrescreve nem segue ligação já plantada no nome
        fd = os.open(destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
    except FileExistsError:
        return 1, {"ok": False, "erro": f"o histórico {destino} já existe; não sobrescrevo"}
    with os.fdopen(fd, "wb") as fh:
        fh.write(original)
    h = hashlib.sha256(original).hexdigest()
    try:  # releitura antes de qualquer outra mudança
        relido = ler_contido(destino, raiz.resolve(), TETO_HISTORICO)
    except (AcimaDoTeto, OSError):
        relido = b""
    if hashlib.sha256(relido).hexdigest() != h:
        destino.unlink()
        return 1, {"ok": False, "erro": "a cópia do histórico não conferiu; nada foi alterado"}
    ponteiro = f"Histórico arquivado: {rel} (sha256 {h})"
    lines = original.decode("utf-8").splitlines()
    pos = next((i for i, l in enumerate(lines) if re.match(REQUIRED["project_id"], l.strip())), 0)
    lines.insert(pos, ponteiro)
    try:  # temporário e troca de nome: nunca através do nome, que pode ter virado ligação ou vínculo físico (R177D-2)
        gravacao.publicar(arquivo, ("\n".join(lines) + "\n").encode("utf-8"))
    except OSError as exc:
        destino.unlink(missing_ok=True)  # o histórico recém-criado sai com o resto: nada fica pela metade
        return 1, {"ok": False, "erro": f"a RETOMADA não pôde ser reescrita ({type(exc).__name__}): nada foi alterado"}
    return 0, {"ok": True, "historico": str(destino), "sha256": h, "ponteiro": ponteiro,
               "itens_nao_repetir": len(itens_nao_repetir(lines)),
               "proximo_passo": "reescreva a RETOMADA de forma enxuta: estado atual e uma linha por item de "
                                "'Ações já realizadas' (a parte antes do primeiro ':' é conferida pelo validar)"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("criar"); c.add_argument("--saida", type=Path, required=True)
    v = sub.add_parser("validar"); v.add_argument("--arquivo", type=Path, required=True)
    a = sub.add_parser("arquivar"); a.add_argument("--arquivo", type=Path, required=True)
    a.add_argument("--historico", type=Path, required=True, help="pasta dos históricos (ex.: evidence/retomada)")
    a.add_argument("--nome", help="nome do arquivo do histórico (padrão: RETOMADA-<data>.md)")
    args = ap.parse_args()
    if args.cmd == "criar":
        if args.saida.exists():
            print(json.dumps({"erro": "RETOMADA já existe; atualize-a em vez de recriar"}, ensure_ascii=False))
            return 1
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TEMPLATE, args.saida)
        print(json.dumps({"criada": str(args.saida)}, ensure_ascii=False))
        return 0
    recusa = pasta_recusada(args.arquivo)  # antes de tocar o disco: não diz se a RETOMADA existe (R177C-B-01)
    if recusa or not args.arquivo.exists():
        print(json.dumps({"ok": False, "erro": recusa or "arquivo de retomada inexistente"}, ensure_ascii=False))
        return 1
    if args.cmd == "arquivar":
        codigo, res = arquivar(args.arquivo, args.historico, args.nome)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return codigo
    res = validar(args.arquivo)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
