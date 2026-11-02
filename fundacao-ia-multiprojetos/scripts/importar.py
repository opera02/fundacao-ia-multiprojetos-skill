#!/usr/bin/env python3
"""Importar sem ler: copiador do fluxo B (cópia de referência) e importação de arquivos autorizados (1.7.10;
DESENHO-1.7.10 §5.2; MELHORIAS-1.7.10, item 0.7 e seção 1, itens 10 e 11).

  plano    --origem DIR --destino DIR --raiz-fundacao DIR --saida PLANO.json
           [--modo completo|lista-de-permissao] [--permitir GLOB ...] [--opaco GLOB ...] [--incluir-fraco GLOB ...]
           [--desde MANIFESTO] [--pasta-segredo NOME ...] [--reconstruivel NOME ...] [--sem-neutralizar-extensoes]
  copiar   --plano PLANO.json --plano-sha256 HASH [--manifesto-b1 MANIFESTO]
  conferir --manifesto <destino>/MANIFESTO-IMPORTACAO.json

1. `plano` lê só metadados (scandir e lstat; nenhum byte de conteúdo) e classifica cada caminho: comum (copiado),
   reconstruivel (fora: node_modules, .venv...), segredo (fora: nome forte ou fraco ou pasta de segredo da regra
   única, `regras_de_segredo.py`), opaco (autorizado com `--opaco GLOB`: copiado byte a byte, nunca decodificado,
   pesquisado nem mostrado; o nome fraco conferido por `segredos.py` entra como comum com `--incluir-fraco GLOB`),
   sqlite (copiado pela API de backup, por `backup_sqlite.py`, salvo o opaco), git (cada
   `.git` vira `<pasta>/.git.zip`, sem config nem hooks), ligacao (fora: nunca seguida) e vinculo-fisico (fora: o
   outro nome pode estar fora da origem). Grava o plano e mostra o SHA-256 do JSON canônico dele.
2. O titular aceita esse SHA-256.
3. `copiar` recalcula o plano e recusa se ele mudou. Abre cada arquivo pela abertura conferida da cópia única da skill
   (`copia_segura.abrir_comum`, contratos do lote 2, §8: no POSIX, descendo da origem pasta a pasta por descritor, sem
   seguir ligação; no Windows, exame sem seguir, o mesmo objeto (dev, ino) no descritor aberto e o caminho real dentro
   da origem), só arquivo comum com um nome só (nlink 1), com o tamanho e a data do plano; copia em fluxo para um
   temporário exclusivo calculando o SHA-256 ao mesmo tempo, compara com o manifesto do B1 quando ele tem o arquivo
   (`--manifesto-b1`), renomeia, deixa só leitura e grava `MANIFESTO-IMPORTACAO.json` (caminho, tamanho, SHA-256 e
   classe de cada arquivo; o que ficou fora, só pelo nome e pela classe). A gravação no destino continua do `Gravador`
   (por descritor de pasta no POSIX), e não do `copiar_conferindo`, que grava pelo caminho: a função única cobre a
   origem e o arquivo; o destino seguro é do `Gravador` (decisão do pacote INTEG-FLUXOB). O plano só tem metadados,
   sem SHA-256 por arquivo: o que prende o conteúdo é o hash calculado na cópia, gravado no manifesto da importação.
4. `conferir` refaz os hashes e acusa o que mudou, sumiu ou sobrou no destino.

Origem registrada (1.7.10, contratos do lote 2, §6): `plano` (e `copiar`, que o recalcula) só aceita `--origem`
listada para o projeto do destino em `registry/projetos-host.json` (`fundacao.projetos_host/1`, gravado só pelo
titular com `assets/host/preparo_host.py registrar-projeto`), lido com teto e sem seguir ligação: a própria pasta
registrada ou uma pasta dentro dela, comparadas pelo caminho real (o registro feito no Windows vale no WSL e vice-versa:
`D:\\...` e `/mnt/d/...`). Sem o registro, ou sem a origem nele, recusa com o comando pronto do registro. Nesse
comando e no `proximo_passo` do `plano`, cada caminho e nome vai citado para o terminal do titular (aspas simples do
sh/bash ou do PowerShell, `codigo_do_plano.citar_no_terminal`); o que não dá para citar com segurança (quebra de linha,
caractere de formatação, aspa dupla no Windows, aspa simples no Linux, também as tipográficas) fica sem comando pronto.

Modos: `completo` (tudo menos as exclusões) e `lista-de-permissao` (nega por padrão, para dados de terceiros: só entra
o que casa `--permitir` ou `--opaco`; o resto sai só por pasta de primeiro nível, extensão e contagem, sem nomes).
`--desde MANIFESTO` (do B1, `manifesto.py`, ou de uma importação anterior): delta para o corte, com só o que é novo ou
mudou e a lista do que sumiu; o arquivo de mesmo tamanho é conferido pelo hash durante a cópia, e o que não mudou não
fica no destino. Padrões (`--permitir`, `--opaco`) são do fnmatch sobre o caminho relativo com '/', sem caixa: '*'
também passa por '/' (`src/*` pega tudo dentro de src).
`--neutralizar-extensoes` (ligado por padrão; `--sem-neutralizar-extensoes` desliga, por exemplo para um plugin
candidato): `.claude/skills`, `.claude/agents`, `.claude/commands`, `.claude/rules`, `.codex/` e `.mcp.json` vão para
`EXTENSOES-NEUTRALIZADAS.zip` na raiz da cópia, com o mapeamento no manifesto, para nenhum host carregar skill,
agente, comando, regra ou MCP de dentro de uma cópia de dados (o contorno de 27/10/2026 virou ferramenta).
Retomada pelo hash: rodar `copiar` de novo com o mesmo plano não copia o arquivo que já está no destino com o mesmo
SHA-256 do da origem (o da origem é recalculado: a retomada não confia no que está no destino).
Os `-wal`, `-shm` e `-journal` de um banco entram no plano como `auxiliar-sqlite` (fora da cópia, contados: a API de
backup consolida o banco); num banco opaco ou cifrado, inclua-os no `--opaco` (ex.: `dados/app.db*`) para copiá-los
byte a byte, senão a cópia byte a byte de um banco sem cabeçalho com `-wal` ao lado é recusada (perderia transações).

Limites: o destino fica dentro de `projects/<projeto>/` da raiz informada, abaixo do projeto e fora das pastas ocultas
dele (.claude, .porteiro, .git...), sem ligação em nenhum ponto do caminho (no Linux, a gravação é feita por
descritor de pasta aberto sem seguir ligação; no Windows, conferindo cada pasta antes e o caminho real depois). "Sem
leitura" quer dizer que o conteúdo não é decodificado nem mostrado: o processo que copia lê os bytes. Por isso a
barreira só existe quando quem roda NÃO é o shell da IA — depois do isolamento da 1.7.10, quem roda `copiar` é o
titular, no terminal dele, com o comando pronto; a IA prepara o plano e lê o manifesto. Rodado pelo shell da IA, é só
regra. O manifesto da importação registra o SHA-256 também dos opacos (pedido da 1.7.10); senha curta num arquivo
opaco pode ser atacada por dicionário a partir desse hash: o manifesto é do projeto e não sai dele.

Códigos: 0 feito; 1 feito com diferença (do B1, ou na conferência) ou arquivo que não pôde ser copiado (o resultado
diz qual); 2 uso incorreto ou recusa (nada copiado).
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ESQUEMA_PLANO = "fundacao.importacao.plano/1"
ESQUEMA_MANIFESTO = "fundacao.importacao/1"
MANIFESTO = "MANIFESTO-IMPORTACAO.json"
ZIP_NEUTRALIZADO = "EXTENSOES-NEUTRALIZADAS.zip"
MARCA = ".importacao-em-andamento.json"
PREFIXO_TEMP = ".importando-"
MODOS = ("completo", "lista-de-permissao")
SUFIXOS_SQLITE = (".sqlite", ".sqlite3", ".db", ".db3", ".s3db", ".sl3")
AUXILIARES_SQLITE = ("-wal", "-shm", "-journal")
CABECALHO_SQLITE = b"SQLite format 3\x00"
EXTENSOES_CLAUDE = ("skills", "agents", "commands", "rules")
COPIADAS = ("comum", "opaco", "sqlite")
TETO_TEXTO_CANONICO = 64 << 20  # acima disto, o texto não é guardado para o hash canônico (comparação "nao-comparavel")
BLOCO = 1 << 20
REGISTRO_DE_ORIGENS = "projetos-host.json"  # em registry/ da raiz: as origens de cada projeto, gravadas pelo titular
ESQUEMA_PROJETOS_HOST = "fundacao.projetos_host/1"
TETO_REGISTRO = 1 << 20  # bytes lidos do registro de origens; acima disso, recusa
PREPARO_HOST = AQUI.parent / "assets" / "host" / "preparo_host.py"  # quem grava o registro (o titular)
O_BINARY = getattr(os, "O_BINARY", 0)
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
# Windows: etiqueta de ponto de nova análise "substituta de nome" (bit 29) — junção, link simbólico e afins.
SUBSTITUTA_DE_NOME = 0x20000000


def _carregar(nome: str):
    """Um script ao lado deste, pelo caminho (sem mexer no `sys.path`)."""
    spec = importlib.util.spec_from_file_location(f"_importar_{nome}", AQUI / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


REGRAS = _carregar("regras_de_segredo")
MANIFESTO_PY = _carregar("manifesto")  # pastas reconstruíveis e sufixos de texto do manifesto
COPIA = _carregar("copia_segura")  # a abertura conferida da cópia única (contratos do lote 2, §8)
CODIGO = _carregar("codigo_do_plano")  # a citação única do comando pronto para o terminal do titular


class Recusa(Exception):
    """Uso incorreto ou recusa: código 2, nada copiado (ou a cópia para no ponto em que achou a troca)."""


class Mudou(OSError):
    """O arquivo da origem mudou, foi trocado ou ganhou outro nome entre o plano e a cópia."""


class _Descartar(Exception):
    """O temporário não vira arquivo (delta: o conteúdo é igual ao da referência)."""


# ------------------------------------------------------------------------------------------------ apoio
def e_ligacao(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & SUBSTITUTA_DE_NOME)


def sha256_canonico(dados) -> str:
    texto = json.dumps(dados, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def hash_canonico(dados: bytes) -> str:
    """O hash do `manifesto.py --texto-canonico` (UTF-8, LF e NFC) sobre bytes já lidos."""
    try:
        texto = dados.decode("utf-8")
    except UnicodeDecodeError:
        return hashlib.sha256(dados).hexdigest()
    texto = texto.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(unicodedata.normalize("NFC", texto).encode("utf-8")).hexdigest()


def _n(texto: str) -> str:
    return REGRAS.normalizar(texto)


def casa(rel: str, globs) -> bool:
    return any(fnmatch.fnmatchcase(_n(rel), _n(g)) for g in globs)


def pode_conter(rel_pasta: str, globs) -> bool:
    """Algum padrão pode casar a pasta ou algo dentro dela (para mostrar o nome dela no modo lista de permissão)."""
    alvo = _n(rel_pasta)
    return any(fnmatch.fnmatchcase(alvo, _n(g)) or fnmatch.fnmatchcase(alvo + "/", _n(g))
               or _n(g).startswith(alvo + "/") for g in globs)


def texto(rel: str) -> bool:
    return Path(rel).suffix.lower() in MANIFESTO_PY.TEXT_SUFFIXES


def neutralizavel(rel: str) -> bool:
    partes = [_n(p) for p in rel.split("/")]
    if partes[-1] == ".mcp.json" or ".codex" in partes[:-1]:
        return True
    return any(p == ".claude" and partes[i + 1] in EXTENSOES_CLAUDE for i, p in enumerate(partes[:-2]))


def auxiliar_sqlite(nome: str) -> bool:
    baixo = nome.lower()
    return any(baixo.endswith(s) and baixo[:-len(s)].endswith(SUFIXOS_SQLITE) for s in AUXILIARES_SQLITE)


def data_zip(mtime_ns: int) -> tuple:
    """A data do membro do zip (UTC), dentro da faixa que o formato aceita (1980 a 2107)."""
    segundos = mtime_ns // 1_000_000_000
    if segundos < 315_532_800:  # 1980-01-01
        return (1980, 1, 1, 0, 0, 0)
    if segundos >= 4_354_819_200:  # 2108-01-01
        return (2107, 12, 31, 23, 59, 58)
    t = datetime.fromtimestamp(segundos, tz=timezone.utc)
    return (t.year, t.month, t.day, t.hour, t.minute, t.second - t.second % 2)


def _omitir_no_git(partes: tuple) -> bool:
    """config e hooks do `.git` (e dos submódulos em modules/, e config.worktree das worktrees): nunca vão para o zip.
    Dentro de refs, logs e objects os nomes são do Git (um ramo pode se chamar config)."""
    if partes[0] == "hooks" or partes in (("config",), ("config.worktree",)):
        return True
    if partes[0] in ("modules", "worktrees"):
        return "hooks" in partes[1:] or partes[-1] in ("config", "config.worktree")
    return False


# ------------------------------------------------------------------------------------------------ origem
def abrir_origem(caminho: Path, base: Path, esperado: dict | None) -> int:
    """Descritor do arquivo, aberto pela abertura conferida da cópia única (`copia_segura.abrir_comum`, contratos do
    lote 2, §8) dentro de `base` (a origem; na conferência, o destino): sem seguir ligação (no POSIX, descendo de `base`
    pasta a pasta por descritor; no Windows, exame sem seguir, o mesmo objeto no descritor aberto e o caminho real
    dentro de `base`), só arquivo comum com um nome só; e, no descritor aberto, o tamanho e a data do plano (quando
    dados). A recusa vira `Mudou`, com o motivo, e o arquivo fica nas falhas."""
    try:
        fd = COPIA.abrir_comum(caminho, dentro_de=base)
    except COPIA.CopiaRecusada as exc:
        raise Mudou(str(exc)) from None
    try:
        aberto = os.fstat(fd)
        if esperado and (aberto.st_size, aberto.st_mtime_ns) != (esperado["tamanho"], esperado["mtime_ns"]):
            raise Mudou(f"mudou depois do plano: {caminho.name}")
    except BaseException:
        os.close(fd)
        raise
    return fd


def ler_blocos(fd: int, tamanho: int | None, destino=None, guardar: bool = False) -> dict:
    """Lê o descritor até o fim, em blocos, calculando o SHA-256 (e escrevendo em `destino`); confere o tamanho."""
    h, n, partes = hashlib.sha256(), 0, []
    while bloco := os.read(fd, BLOCO):
        h.update(bloco)
        n += len(bloco)
        if destino is not None:
            destino.write(bloco)
        if guardar and n <= TETO_TEXTO_CANONICO:
            partes.append(bloco)
    if tamanho is not None and n != tamanho:
        raise Mudou("o tamanho mudou durante a cópia")
    resultado = {"sha256": h.hexdigest(), "tamanho": n}
    if guardar and n <= TETO_TEXTO_CANONICO:
        resultado["canonico"] = hash_canonico(b"".join(partes))
    return resultado


def hash_origem(caminho: Path, base: Path, item: dict, guardar: bool = False) -> dict:
    fd = abrir_origem(caminho, base, item)
    try:
        return ler_blocos(fd, item["tamanho"], guardar=guardar)
    finally:
        os.close(fd)


def listar_git(pasta: Path) -> tuple[list, list, int, int]:
    """Do `.git`: os membros do zip (caminho, tamanho, data), o omitido (config e hooks), ligações e vínculos físicos;
    só metadados."""
    membros, omitidos, ligacoes, vinculos = [], [], 0, 0
    pendentes = [(pasta, ())]
    while pendentes:
        atual, partes = pendentes.pop()
        with os.scandir(atual) as it:
            entradas = sorted(it, key=lambda e: e.name)
        for e in entradas:
            sub = partes + (e.name,)
            st = os.lstat(e.path)
            if e_ligacao(st):
                ligacoes += 1
            elif _omitir_no_git(sub):
                omitidos.append("/".join(sub) + ("/" if stat.S_ISDIR(st.st_mode) else ""))
            elif stat.S_ISDIR(st.st_mode):
                pendentes.append((Path(e.path), sub))
            elif stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
                vinculos += 1
            elif stat.S_ISREG(st.st_mode):
                membros.append(("/".join(sub), st.st_size, st.st_mtime_ns))
    return sorted(membros), sorted(omitidos), ligacoes, vinculos


def item_git(pasta: Path, rel: str) -> dict:
    membros, omitidos, ligacoes, vinculos = listar_git(pasta)
    return {"caminho": rel, "classe": "git", "zip": f"{rel}.zip", "membros": len(membros),
            "bytes": sum(m[1] for m in membros), "omitidos": omitidos[:50], "omitidos_total": len(omitidos),
            "ligacoes": ligacoes, "vinculos_fisicos": vinculos,
            "metadados_sha256": sha256_canonico([membros, omitidos, ligacoes, vinculos])}


# ------------------------------------------------------------------------------------------------ referência
def carregar_referencia(caminho: Path) -> dict:
    """Manifesto do `manifesto.py` (path, size, sha256) ou de uma importação (caminho, tamanho, sha256)."""
    try:
        dados = Path(caminho).read_bytes()
        ref = json.loads(dados)
        arquivos = ref["arquivos"]
        if not isinstance(arquivos, list):
            raise TypeError
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise Recusa(f"manifesto de referência ilegível ou fora do formato: {caminho} ({type(exc).__name__})") from None
    entradas = {}
    for f in arquivos:
        rel = f.get("path", f.get("caminho")) if isinstance(f, dict) else None
        if isinstance(rel, str) and isinstance(f.get("sha256"), str):
            tamanho = f.get("size", f.get("tamanho"))
            entradas[rel] = {"sha256": f["sha256"].lower(), "tamanho": tamanho if isinstance(tamanho, int) else None,
                             "comparavel": f.get("classe") != "sqlite"}  # cópia pela API: bytes diferentes
    politica = ref.get("politica") if isinstance(ref.get("politica"), dict) else {}
    return {"arquivo": str(caminho), "sha256": hashlib.sha256(dados).hexdigest(), "entradas": entradas,
            "canonico": bool(ref.get("texto_canonico") or politica.get("texto_canonico"))}


def comparar_com(ref: dict | None, rel: str, resultado: dict, opaco: bool) -> str | None:
    """'igual', 'diferente', 'fora-da-referencia' ou 'nao-comparavel' (o opaco, num manifesto canônico, não é
    decodificado para o hash canônico)."""
    if ref is None:
        return None
    e = ref["entradas"].get(rel)
    if e is None:
        return "fora-da-referencia"
    if not e["comparavel"]:
        return "nao-comparavel"
    if ref["canonico"] and texto(rel):
        if opaco or "canonico" not in resultado:
            return "nao-comparavel"
        return "igual" if resultado["canonico"] == e["sha256"] else "diferente"
    return "igual" if resultado["sha256"] == e["sha256"] else "diferente"


# ------------------------------------------------------------------------------------------------ plano
def parametros(args) -> dict:
    try:
        extras = sorted({REGRAS.validar_pasta_extra(n) for n in args.pasta_segredo})
        reconstruiveis = sorted({REGRAS.validar_pasta_extra(n) for n in args.reconstruivel})
    except ValueError as exc:
        raise Recusa(str(exc)) from None
    for g in (*args.permitir, *args.opaco, *args.incluir_fraco):
        if not g.strip() or "\x00" in g:
            raise Recusa(f"padrão vazio ou inválido: {g!r}")
    if args.modo == "lista-de-permissao" and not args.permitir:
        raise Recusa("o modo lista-de-permissao exige pelo menos um --permitir (o resto fica fora)")
    if args.modo == "completo" and args.permitir:
        raise Recusa("--permitir só vale no modo lista-de-permissao")
    desde = None
    if args.desde:
        caminho = Path(os.path.abspath(args.desde))
        origem_abs = os.path.abspath(args.origem)
        if caminho.is_relative_to(origem_abs) or Path(os.path.realpath(caminho)).is_relative_to(
                os.path.realpath(origem_abs)):
            raise Recusa("--desde não pode ficar dentro da origem: ponha o manifesto de referência fora dela")
        desde = {"arquivo": str(caminho), "sha256": carregar_referencia(caminho)["sha256"]}
    return {"origem": os.path.abspath(args.origem), "destino": os.path.abspath(args.destino),
            "raiz_fundacao": os.path.abspath(args.raiz_fundacao), "modo": args.modo,
            "permitir": sorted(set(args.permitir)), "opacos": sorted(set(args.opaco)),
            "fracos_incluidos": sorted(set(args.incluir_fraco)), "pastas_de_segredo_extras": extras,
            "reconstruiveis_extras": reconstruiveis, "neutralizar_extensoes": args.neutralizar, "desde": desde}


def _pasta_comum(caminho: Path, rotulo: str, existir: bool = True) -> bool:
    """A pasta existe, é pasta e não é ligação (False se não existe e `existir` é falso)."""
    try:
        st = os.lstat(caminho)
    except FileNotFoundError:
        if existir:
            raise Recusa(f"{rotulo} inexistente: {caminho}") from None
        return False
    if e_ligacao(st):
        raise Recusa(f"{rotulo} é ligação (link simbólico ou junção), que não é seguida: {caminho}")
    if not stat.S_ISDIR(st.st_mode):
        raise Recusa(f"{rotulo} não é pasta: {caminho}")
    return True


def _e_raiz_de_fundacao(pasta: Path) -> bool:
    """A pasta tem os marcadores de uma raiz de fundação: `fundacao/__main__.py` (arquivo comum) e `projects/`
    (pasta), conferidos sem seguir ligação."""
    try:
        marca = os.lstat(pasta / "fundacao" / "__main__.py")
        projetos = os.lstat(pasta / "projects")
    except OSError:
        return False
    return (not e_ligacao(marca) and stat.S_ISREG(marca.st_mode)
            and not e_ligacao(projetos) and stat.S_ISDIR(projetos.st_mode))


def _raiz_de_fundacao_acima(inicio: Path) -> Path | None:
    """Sobe de `inicio` (um caminho real) procurando uma raiz de fundação; None se não houver nenhuma."""
    atual = inicio
    while True:
        if _e_raiz_de_fundacao(atual):
            return atual
        if atual.parent == atual:
            return None
        atual = atual.parent


def resolver_destino(par: dict) -> tuple[Path, Path, list[str]]:
    """(origem, pasta do projeto, partes do destino abaixo dela), conferidos: destino dentro de projects/<projeto>/,
    abaixo do projeto, fora das pastas ocultas dele, sem ligação no caminho e sem cruzar com a origem."""
    origem, destino = Path(par["origem"]), Path(par["destino"])
    projetos = Path(par["raiz_fundacao"]) / "projects"
    _pasta_comum(origem, "a origem")
    _pasta_comum(Path(par["raiz_fundacao"]), "a raiz da fundação")
    _pasta_comum(projetos, "a pasta projects da raiz")
    marca = Path(par["raiz_fundacao"]) / "fundacao" / "__main__.py"
    try:
        st_marca = os.lstat(marca)
    except OSError:
        st_marca = None
    if st_marca is None or e_ligacao(st_marca) or not stat.S_ISREG(st_marca.st_mode):
        raise Recusa("a raiz informada não é uma raiz de fundação (falta o arquivo fundacao/__main__.py, marcador "
                     f"da raiz): {par['raiz_fundacao']}")
    _pasta_comum(Path(par["raiz_fundacao"]) / "registry", "a pasta registry da raiz")
    _pasta_comum(Path(par["raiz_fundacao"]) / "state", "a pasta state da raiz")
    env_raiz = os.environ.get("FUNDACAO_RAIZ")
    if env_raiz and Path(os.path.realpath(par["raiz_fundacao"])) != Path(os.path.realpath(env_raiz)):
        raise Recusa("a raiz informada não é a raiz da fundação definida no ambiente (FUNDACAO_RAIZ)")
    if not destino.is_relative_to(projetos):
        raise Recusa(f"o destino tem de ficar dentro de {projetos}/<projeto>/: {destino}")
    partes = destino.relative_to(projetos).parts
    if len(partes) < 2 or any(p in (".", "..") for p in partes):
        raise Recusa("o destino tem de ser uma pasta abaixo de projects/<projeto>/ (por exemplo data/origem/<parte>)")
    if partes[1].startswith("."):
        raise Recusa(f"o destino não pode ficar numa pasta oculta do projeto ({partes[1]}): elas são do host e do Git")
    projeto = projetos / partes[0]
    _pasta_comum(projeto, f"o projeto {partes[0]}")
    atual = projeto
    for p in partes[1:]:
        atual = atual / p
        if not _pasta_comum(atual, "uma pasta do caminho do destino", existir=False):
            break
    origem_real, destino_real = Path(os.path.realpath(origem)), Path(os.path.realpath(destino))
    if (destino.is_relative_to(origem) or origem.is_relative_to(destino) or destino_real.is_relative_to(origem_real)
            or origem_real.is_relative_to(destino_real)):
        raise Recusa("origem e destino não podem ficar um dentro do outro")
    projeto_real, raiz_real = Path(os.path.realpath(projeto)), Path(os.path.realpath(par["raiz_fundacao"]))
    if not destino_real.is_relative_to(projeto_real):
        raise Recusa("o caminho real do destino sai do projeto")
    if origem_real.is_relative_to(raiz_real) and not origem_real.is_relative_to(projeto_real):
        raise Recusa("a origem fica na raiz da fundação, fora do projeto do destino (outro projeto, state/...): um "
                     "projeto não importa de outro")
    if _raiz_de_fundacao_acima(origem_real) is not None and not origem_real.is_relative_to(projeto_real):
        raise Recusa("a origem fica numa raiz de fundação, fora do projeto do destino (qualquer que seja a "
                     "--raiz-fundacao informada): um projeto não importa de outro")
    conferir_origem_registrada(Path(par["raiz_fundacao"]), partes[0], origem)
    return origem, projeto, list(partes[1:])


# ------------------------------------------------------------------------------------------------ origens registradas
def caminho_local(texto) -> str | None:
    """Um caminho absoluto do registro de origens neste sistema: no POSIX, `X:\\...` vira `/mnt/x/...` (o WSL); no
    Windows, `/mnt/x/...` vira `X:\\...`. Relativo ou fora desses formatos: None (não registra nada)."""
    if not isinstance(texto, str) or not texto.strip() or "\0" in texto:
        return None
    t = texto.strip()
    unidade = re.match(r"^([A-Za-z]):[\\/](.*)$", t)
    if os.name == "nt":
        wsl = re.match(r"^/mnt/([A-Za-z])(?:/(.*))?$", t)
        if wsl:
            return f"{wsl.group(1).upper()}:\\" + (wsl.group(2) or "").replace("/", "\\")
        return t if unidade or t.startswith("\\\\") else None
    if unidade:
        return f"/mnt/{unidade.group(1).lower()}/" + unidade.group(2).replace("\\", "/")
    return t if t.startswith("/") else None


def _real(caminho) -> str:
    return os.path.normcase(os.path.realpath(caminho))


def ler_registro_de_origens(raiz: Path) -> dict | None:
    """`registry/projetos-host.json` (`fundacao.projetos_host/1`), lido sem seguir ligação (`copia_segura.abrir_comum`,
    dentro de `registry/`) e com teto; None se não existe. Fora do formato: Recusa (nada é aceito por um registro que
    não se lê)."""
    pasta = Path(raiz) / "registry"
    arquivo = pasta / REGISTRO_DE_ORIGENS
    if not os.path.lexists(arquivo):
        return None
    try:
        fd = COPIA.abrir_comum(arquivo, dentro_de=pasta)
    except COPIA.CopiaRecusada as exc:
        raise Recusa(f"o registro de origens {arquivo} não pôde ser lido sem seguir ligação ({exc})") from None
    try:
        partes, lidos = [], 0
        while lidos <= TETO_REGISTRO and (bloco := os.read(fd, min(BLOCO, TETO_REGISTRO + 1 - lidos))):
            partes.append(bloco)
            lidos += len(bloco)
    finally:
        os.close(fd)
    if lidos > TETO_REGISTRO:
        raise Recusa(f"o registro de origens {arquivo} passa do teto de {TETO_REGISTRO} bytes")
    try:
        dados = json.loads(b"".join(partes).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise Recusa(f"o registro de origens {arquivo} não é JSON em UTF-8") from None
    if (not isinstance(dados, dict) or dados.get("schema_version") != ESQUEMA_PROJETOS_HOST
            or not isinstance(dados.get("projetos"), dict)):
        raise Recusa(f"o registro de origens {arquivo} está fora do formato {ESQUEMA_PROJETOS_HOST}")
    return dados


def comando_de_registro(raiz: Path, projeto: str, origem: Path) -> str:
    """O comando que o titular roda, no terminal dele, para registrar a origem do projeto (contratos do lote 2, §6). A
    origem é escolhida pela sessão e o projeto vem do nome da pasta: cada valor vai citado para o shell de destino
    (`codigo_do_plano.citar_no_terminal`) [segunda revisão do pacote INTEG-FLUXOB]; ValueError se um deles não dá para
    citar com segurança (aí não há comando pronto). A raiz vai também, pela mesma citação: o `preparo_host.py
    registrar-projeto` a exige, e o comando sem ela saía com código 2 sem registrar nada [integração final da 1.7.10,
    item I23]."""
    python = "python" if os.name == "nt" else "python3"
    citar = CODIGO.citar_no_terminal
    return (f"{python} {citar(PREPARO_HOST)} registrar-projeto --raiz {citar(raiz)} --projeto {citar(projeto)} "
            f"--origem {citar(origem)}")


def dentro_pela_identidade(real: str, base: str) -> bool:
    """`real` é a pasta `base` ou fica dentro dela pela identidade (dispositivo e inode de `base` em `real` ou num pai
    dele), sem depender do texto: no WSL, o `/mnt/<x>` (NTFS) não distingue maiúsculas, mas a comparação de texto do
    POSIX distingue, e o registro guarda o texto digitado no Windows (`D:\\Origem` vale para `/mnt/d/origem`)
    [revisão do pacote INTEG-FLUXOB]. Erro ao examinar: não casa (falha fechada)."""
    try:
        alvo = os.stat(base)
    except OSError:
        return False
    for pasta in (real, *map(str, Path(real).parents)):
        try:
            if os.path.samestat(os.stat(pasta), alvo):
                return True
        except OSError:
            continue
    return False


def conferir_origem_registrada(raiz: Path, projeto: str, origem: Path) -> None:
    """A origem é uma das registradas para o projeto do destino (ou fica dentro de uma), pelo caminho real e, se o
    texto não casa, pela identidade da pasta (`dentro_pela_identidade`): o plano é montado pela IA, e a origem de cada
    projeto quem escolhe é o titular, no registro."""
    registro = ler_registro_de_origens(raiz)
    entrada = registro["projetos"].get(projeto) if registro else None
    origens = entrada.get("origens") if isinstance(entrada, dict) else None
    real = _real(origem)
    for texto in origens if isinstance(origens, list) else []:
        local = caminho_local(texto)
        if local is None:
            continue
        base = _real(local)
        if real == base or real.startswith(base.rstrip("\\/") + os.sep) or dentro_pela_identidade(real, local):
            return
    situacao = ("não existe" if registro is None else
                f"não lista esta origem para o projeto {CODIGO.visivel(projeto)}" if entrada is not None else
                f"não tem o projeto {CODIGO.visivel(projeto)}")
    try:  # a raiz é a do registro que esta conferência lê (I23)
        passo = f"No terminal do titular: {comando_de_registro(raiz, projeto, origem)}"
    except ValueError as exc:
        passo = (f"Não há comando pronto: {exc}, e o comando não o cita com segurança no terminal; renomeie a pasta "
                 "(a origem ou a raiz) ou o projeto e peça o plano de novo")
    raise Recusa(f"a origem {CODIGO.visivel(str(origem))} não está registrada para o projeto "
                 f"{CODIGO.visivel(projeto)}: registry/{REGISTRO_DE_ORIGENS} {situacao} (só o titular registra a "
                 f"origem de cada projeto). {passo}")


def _delta(item: dict, ref: dict) -> str:
    e = ref["entradas"].get(item["caminho"])
    if e is None:
        return "novo"
    if (item["classe"] != "sqlite" and e["comparavel"] and e["tamanho"] is not None
            and e["tamanho"] != item["tamanho"] and not (ref["canonico"] and texto(item["caminho"]))):
        return "alterado"
    return "a-conferir"


CHAVES_PARAMETROS = {"origem": str, "destino": str, "raiz_fundacao": str, "modo": str, "permitir": list,
                     "opacos": list, "fracos_incluidos": list, "pastas_de_segredo_extras": list,
                     "reconstruiveis_extras": list, "neutralizar_extensoes": bool}


def validar_parametros(par) -> dict:
    """Os parâmetros gravados no plano, no formato que o `plano` grava (o `copiar` os usa para recalcular)."""
    if (not isinstance(par, dict) or set(par) != {*CHAVES_PARAMETROS, "desde"}
            or not all(isinstance(par[k], t) for k, t in CHAVES_PARAMETROS.items())
            or par["modo"] not in MODOS
            or not all(isinstance(g, str) for k in ("permitir", "opacos", "fracos_incluidos",
                                                     "pastas_de_segredo_extras", "reconstruiveis_extras")
                       for g in par[k])
            or not (par["desde"] is None or (isinstance(par["desde"], dict)
                                             and isinstance(par["desde"].get("arquivo"), str)
                                             and isinstance(par["desde"].get("sha256"), str)))):
        raise Recusa(f"parâmetros do plano fora do formato {ESQUEMA_PLANO}")
    try:
        for nome in (*par["pastas_de_segredo_extras"], *par["reconstruiveis_extras"]):
            REGRAS.validar_pasta_extra(nome)
    except ValueError as exc:
        raise Recusa(str(exc)) from None
    return par


def montar_plano(par: dict) -> dict:
    """O plano, só com metadados. Determinístico: o `copiar` o recalcula e compara o SHA-256."""
    origem, projeto, partes = resolver_destino(validar_parametros(par))
    ref = None
    if par["desde"]:
        ref = carregar_referencia(Path(par["desde"]["arquivo"]))
        if ref["sha256"] != par["desde"]["sha256"]:
            raise Recusa(f"o manifesto de --desde mudou depois do plano: {par['desde']['arquivo']}")
    lista = par["modo"] == "lista-de-permissao"
    visiveis = [*par["permitir"], *par["opacos"]]
    opacos, extras = par["opacos"], par["pastas_de_segredo_extras"]
    reconstruiveis = (set(MANIFESTO_PY.EXCLUDE_DIRS) - {".git"}) | set(par["reconstruiveis_extras"])
    itens, fora_da_lista, todos, podadas = [], Counter(), set(), []

    def registrar(item: dict, pasta: bool = False) -> None:
        rel = item["caminho"]
        if not lista or (pode_conter(rel, visiveis) if pasta else casa(rel, visiveis)):
            itens.append(item)
        else:
            primeiro = rel.split("/")[0] if "/" in rel else "."
            if pasta:
                chave = "(pasta)"
            else:
                ext = Path(rel).suffix.lower()
                chave = ext if re.fullmatch(r"\.[a-z0-9]{1,10}", ext) else ("(outra)" if ext else "(sem extensão)")
            fora_da_lista[(primeiro, chave)] += 1

    def segredo_por_dentro(pasta: Path, rel: str) -> int:
        """Numa pasta de segredo, só metadados: o que casa --opaco entra; o resto é só contado. Não desce num `.git`
        de dentro: os internos do Git não viram cópia crua nem quando casam --opaco."""
        nao_autorizados, pendentes = 0, [(pasta, rel)]
        while pendentes:
            atual, rel_atual = pendentes.pop()
            with os.scandir(atual) as it:
                entradas = sorted(it, key=lambda e: e.name)
            for e in entradas:
                sub = f"{rel_atual}/{e.name}"
                st = os.lstat(e.path)
                if stat.S_ISDIR(st.st_mode) and not e_ligacao(st):
                    if _n(e.name) != ".git":
                        pendentes.append((Path(e.path), sub))
                    continue
                todos.add(sub)
                if stat.S_ISREG(st.st_mode) and not e_ligacao(st) and st.st_nlink == 1 and casa(sub, opacos):
                    itens.append(_com_delta({"caminho": sub, "classe": "opaco", "tamanho": st.st_size,
                                             "mtime_ns": st.st_mtime_ns}, par, ref))
                elif not auxiliar_sqlite(e.name):
                    nao_autorizados += 1
        return nao_autorizados

    pendentes = [(origem, "")]
    while pendentes:
        pasta, rel_pasta = pendentes.pop()
        try:
            with os.scandir(pasta) as it:
                entradas = sorted(it, key=lambda e: e.name)
        except OSError as exc:
            registrar({"caminho": rel_pasta or ".", "classe": "ilegivel", "motivo": type(exc).__name__}, pasta=True)
            podadas.append(rel_pasta)
            continue
        for e in entradas:
            rel = f"{rel_pasta}/{e.name}" if rel_pasta else e.name
            try:
                rel.encode("utf-8")
            except UnicodeEncodeError:
                registrar({"caminho": ascii(rel), "classe": "ilegivel", "motivo": "nome fora do UTF-8"})
                continue
            try:
                st = os.lstat(e.path)
            except OSError as exc:
                todos.add(rel)
                registrar({"caminho": rel, "classe": "ilegivel", "motivo": type(exc).__name__})
                continue
            if e_ligacao(st):
                todos.add(rel)
                podadas.append(rel)
                registrar({"caminho": rel, "classe": "ligacao"}, pasta=stat.S_ISDIR(st.st_mode))
            elif stat.S_ISDIR(st.st_mode):
                if _n(e.name) == ".git":
                    try:
                        item = item_git(Path(e.path), rel)
                    except OSError as exc:
                        item = {"caminho": rel, "classe": "ilegivel", "motivo": type(exc).__name__}
                    podadas.append(rel)
                    registrar(item, pasta=True)
                elif REGRAS.e_pasta_de_segredo(e.name, extras):
                    item = {"caminho": rel, "classe": "segredo", "regra": "pasta-de-segredo", "nao_autorizados": None}
                    if opacos:
                        try:
                            item["nao_autorizados"] = segredo_por_dentro(Path(e.path), rel)
                        except OSError as exc:
                            item["motivo"] = f"pasta ilegível: {type(exc).__name__}"
                            podadas.append(rel)
                    else:
                        podadas.append(rel)
                    registrar(item, pasta=True)
                elif e.name in reconstruiveis:
                    podadas.append(rel)
                    registrar({"caminho": rel, "classe": "reconstruivel"}, pasta=True)
                else:
                    pendentes.append((Path(e.path), rel))
            elif not stat.S_ISREG(st.st_mode):
                todos.add(rel)
                registrar({"caminho": rel, "classe": "especial"})
            else:
                todos.add(rel)
                if not auxiliar_sqlite(e.name) or casa(rel, par["opacos"]):
                    registrar(_classificar_arquivo(rel, e.name, st, par, ref))
                else:  # -wal/-shm/-journal fora da cópia (a API de backup consolida o banco): contado, não copiado
                    registrar({"caminho": rel, "classe": "auxiliar-sqlite"})
    itens.sort(key=lambda i: i["caminho"])
    reservados = {MANIFESTO, MARCA, ZIP_NEUTRALIZADO}
    zips_git = {i["zip"] for i in itens if i["classe"] == "git"}
    for i in itens:
        if i["classe"] not in COPIADAS:
            continue
        rel, base = i["caminho"], i["caminho"].rsplit("/", 1)[-1]
        if "/" not in rel and rel in reservados:
            raise Recusa(f"a origem tem um arquivo com o nome reservado da importação ({rel}): a cópia grava esse "
                         "arquivo na raiz do destino; renomeie-o na origem")
        if base.startswith(PREFIXO_TEMP) and base.endswith(".tmp"):
            raise Recusa(f"a origem tem um temporário desta ferramenta ({rel}): a limpeza da cópia o apagaria; "
                         "renomeie-o na origem")
        if rel in zips_git:
            raise Recusa(f"a origem tem {rel} ao lado de um .git que viraria esse mesmo zip: renomeie um dos dois")
    sumidos, sumidos_fora_da_lista = None, 0
    if ref is not None:
        def podado(p: str) -> bool:
            return any(p == x or p.startswith(x + "/") for x in podadas if x)
        sumidos = sorted(p for p in ref["entradas"] if p not in todos and not podado(p))
        if lista:  # na lista de permissão, nome de fora da lista não aparece nem como sumido: só a contagem
            sumidos_fora_da_lista = sum(1 for p in sumidos if not casa(p, visiveis))
            sumidos = [p for p in sumidos if casa(p, visiveis)]
    resumo = Counter(i["classe"] for i in itens)
    resumo.update({"neutralizar": sum(1 for i in itens if i.get("neutralizar"))})
    resumo.update(Counter(f"delta-{i['delta']}" for i in itens if "delta" in i))
    resumo.update({"sumidos": len(sumidos or []), "sumidos-fora-da-lista": sumidos_fora_da_lista})
    if lista:
        resumo["fora-da-lista"] = sum(fora_da_lista.values())
    avisos = []
    if "data" not in partes[:1]:
        avisos.append("o destino não fica em projects/<projeto>/data/: CLAUDE.md e AGENTS.md da cópia ficam fora das "
                      "instruções da sessão só dentro de data/ (claudeMdExcludes)")
    return {"schema_version": ESQUEMA_PLANO, "parametros": par, "projeto": projeto.name,
            "regra_de_segredo": REGRAS.listas(), "reconstruiveis": sorted(reconstruiveis), "itens": itens,
            "fora_da_lista": [{"pasta": p, "extensao": x, "quantidade": n}
                              for (p, x), n in sorted(fora_da_lista.items())],
            "sumidos": sumidos, "resumo": dict(sorted((k, v) for k, v in resumo.items() if v)), "avisos": avisos}


def _com_delta(item: dict, par: dict, ref: dict | None) -> dict:
    if par["neutralizar_extensoes"] and item["classe"] in COPIADAS and neutralizavel(item["caminho"]):
        item["neutralizar"] = True
    if ref is not None and item["classe"] in COPIADAS:
        item["delta"] = _delta(item, ref)
    return item


def _classificar_arquivo(rel: str, nome: str, st: os.stat_result, par: dict, ref: dict | None) -> dict:
    base = {"caminho": rel, "tamanho": st.st_size, "mtime_ns": st.st_mtime_ns}
    if st.st_nlink > 1:
        return {**base, "classe": "vinculo-fisico"}
    if _n(nome) == ".git":  # worktree: aponta outro repositório; vai para o zip, nunca como .git na cópia
        return {**base, "classe": "git", "zip": f"{rel}.zip", "worktree": True}
    if casa(rel, par["opacos"]):
        return _com_delta({**base, "classe": "opaco"}, par, ref)
    regra = REGRAS.classificar(rel, par["pastas_de_segredo_extras"])
    if regra == "fraco" and casa(rel, par["fracos_incluidos"]):  # conferido o conteúdo, o titular o leva
        base["fraco_incluido"] = True
    elif regra:
        return {**base, "classe": "segredo", "regra": regra}
    return _com_delta({**base, "classe": "sqlite" if nome.lower().endswith(SUFIXOS_SQLITE) else "comum"}, par, ref)


# ------------------------------------------------------------------------------------------------ destino
_POSIX = (os.name == "posix" and hasattr(os, "O_DIRECTORY") and bool(O_NOFOLLOW) and hasattr(os, "fchmod")
          and {os.open, os.mkdir, os.stat, os.unlink, os.rename} <= os.supports_dir_fd
          and os.utime in os.supports_fd)
_PASTA = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | O_NOFOLLOW | O_CLOEXEC


class Gravador:
    """Grava dentro do destino sem seguir ligação. POSIX: por descritor de pasta aberto com O_NOFOLLOW|O_DIRECTORY
    (uma pasta trocada por ligação no meio do caminho não é atravessada); Windows: conferindo cada pasta (lstat) antes
    e o caminho real depois. Cada arquivo nasce num temporário exclusivo e é renomeado no lugar; fica só leitura."""

    def __init__(self, projeto: Path, partes: list[str]):
        self.raiz = projeto.joinpath(*partes)
        if _POSIX:
            fd = os.open(projeto, _PASTA)
            try:
                self.fd = self._descer(fd, partes, criar=True)
            finally:
                os.close(fd)
        else:
            self._garantir(projeto, partes)
            self.real = Path(os.path.realpath(self.raiz))

    def fechar(self) -> None:
        if _POSIX:
            os.close(self.fd)

    # -- pastas
    @staticmethod
    def _descer(fd: int, partes, criar: bool) -> int:
        atual = os.dup(fd)
        try:
            for p in partes:
                try:
                    novo = os.open(p, _PASTA, dir_fd=atual)
                except FileNotFoundError:
                    if not criar:
                        raise
                    os.mkdir(p, 0o755, dir_fd=atual)
                    novo = os.open(p, _PASTA, dir_fd=atual)
                except OSError:
                    raise Recusa(f"ligação ou arquivo no caminho do destino ({p}): nada é gravado através "
                                 "dele") from None
                os.close(atual)
                atual = novo
            return atual
        except BaseException:
            os.close(atual)
            raise

    @staticmethod
    def _garantir(inicio: Path, partes, criar: bool = True) -> Path:
        atual = inicio
        for p in partes:
            atual = atual / p
            try:
                st = os.lstat(atual)
            except FileNotFoundError:
                if not criar:
                    raise
                os.mkdir(atual)
                st = os.lstat(atual)
            if e_ligacao(st) or not stat.S_ISDIR(st.st_mode):
                raise Recusa(f"ligação ou arquivo no caminho do destino ({p}): nada é gravado através dele")
        return atual

    # -- arquivos
    @staticmethod
    def _escrever(fh, escrever) -> dict:
        res = escrever(fh)
        fh.flush()
        if res is None:  # o hash é do que ficou gravado (o zip, por exemplo)
            fh.seek(0)
            h, n = hashlib.sha256(), 0
            while bloco := fh.read(BLOCO):
                h.update(bloco)
                n += len(bloco)
            res = {"sha256": h.hexdigest(), "tamanho": n}
        return res

    def gravar(self, rel: str, escrever, mtime_ns: int | None = None, decidir=None) -> dict | None:
        """Grava `rel` pelo `escrever(arquivo)`; `decidir(resultado)` falso descarta o temporário (None)."""
        partes = rel.split("/")
        nome, temp = partes[-1], f"{PREFIXO_TEMP}{os.urandom(6).hex()}.tmp"
        if _POSIX:
            fd_dir = self._descer(self.fd, partes[:-1], criar=True)
            try:
                fd = os.open(temp, os.O_RDWR | os.O_CREAT | os.O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600, dir_fd=fd_dir)
                try:
                    with os.fdopen(fd, "w+b") as fh:
                        res = self._escrever(fh, escrever)
                        if decidir is not None and not decidir(res):
                            raise _Descartar
                        if mtime_ns is not None:
                            os.utime(fh.fileno(), ns=(mtime_ns, mtime_ns))
                        os.fchmod(fh.fileno(), 0o444)
                    self._livre_posix(fd_dir, nome)
                    os.rename(temp, nome, src_dir_fd=fd_dir, dst_dir_fd=fd_dir)
                except BaseException as exc:
                    try:
                        os.unlink(temp, dir_fd=fd_dir)
                    except OSError:
                        pass
                    if isinstance(exc, _Descartar):
                        return None
                    raise
            finally:
                os.close(fd_dir)
            return res
        pasta = self._garantir(self.raiz, partes[:-1])
        caminho_temp, final = pasta / temp, pasta / nome
        fd = os.open(caminho_temp, os.O_RDWR | os.O_CREAT | os.O_EXCL | O_BINARY, 0o600)
        try:
            with os.fdopen(fd, "w+b") as fh:
                res = self._escrever(fh, escrever)
                if decidir is not None and not decidir(res):
                    raise _Descartar
            if not Path(os.path.realpath(pasta)).is_relative_to(self.real):
                raise Recusa(f"a pasta do destino foi trocada por ligação: {rel}")
            self._livre_caminho(final)
            os.replace(caminho_temp, final)
        except BaseException as exc:
            try:
                os.unlink(caminho_temp)
            except OSError:
                pass
            if isinstance(exc, _Descartar):
                return None
            raise
        if mtime_ns is not None:
            os.utime(final, ns=(mtime_ns, mtime_ns))
        os.chmod(final, stat.S_IREAD)
        return res

    @staticmethod
    def _livre_posix(fd_dir: int, nome: str) -> None:
        try:
            st = os.stat(nome, dir_fd=fd_dir, follow_symlinks=False)
        except FileNotFoundError:
            return
        if not stat.S_ISREG(st.st_mode):
            raise Recusa(f"há ligação ou pasta no lugar do arquivo de destino: {nome}")

    @staticmethod
    def _livre_caminho(final: Path) -> None:
        try:
            st = os.lstat(final)
        except FileNotFoundError:
            return
        if e_ligacao(st) or not stat.S_ISREG(st.st_mode):
            raise Recusa(f"há ligação ou pasta no lugar do arquivo de destino: {final.name}")
        os.chmod(final, stat.S_IWRITE | stat.S_IREAD)  # o Windows não troca arquivo só leitura

    def _abrir(self, rel: str) -> int | None:
        """Descritor de leitura de um arquivo do destino (None se não existe), sem seguir ligação."""
        partes = rel.split("/")
        if _POSIX:
            try:
                fd_dir = self._descer(self.fd, partes[:-1], criar=False)
            except FileNotFoundError:
                return None
            try:
                fd = os.open(partes[-1], os.O_RDONLY | O_NOFOLLOW | O_CLOEXEC | getattr(os, "O_NONBLOCK", 0),
                             dir_fd=fd_dir)
            except FileNotFoundError:
                return None
            except OSError:
                raise Recusa(f"ligação no lugar de um arquivo do destino: {rel}") from None
            finally:
                os.close(fd_dir)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                os.close(fd)
                raise Recusa(f"o destino tem algo que não é arquivo comum em {rel}")
            return fd
        try:
            pasta = self._garantir(self.raiz, partes[:-1], criar=False)
            st = os.lstat(pasta / partes[-1])
        except FileNotFoundError:
            return None
        if e_ligacao(st) or not stat.S_ISREG(st.st_mode):
            raise Recusa(f"ligação ou pasta no lugar de um arquivo do destino: {rel}")
        fd = os.open(pasta / partes[-1], os.O_RDONLY | O_BINARY)
        aberto = os.fstat(fd)
        if (aberto.st_dev, aberto.st_ino) != (st.st_dev, st.st_ino):
            os.close(fd)
            raise Recusa(f"arquivo do destino trocado durante a leitura: {rel}")
        return fd

    def hash_de(self, rel: str) -> str | None:
        fd = self._abrir(rel)
        if fd is None:
            return None
        try:
            return ler_blocos(fd, None)["sha256"]
        finally:
            os.close(fd)

    def ler(self, rel: str) -> bytes | None:
        fd = self._abrir(rel)
        if fd is None:
            return None
        try:
            partes = []
            while bloco := os.read(fd, BLOCO):
                partes.append(bloco)
            return b"".join(partes)
        finally:
            os.close(fd)

    def remover(self, rel: str) -> None:
        partes = rel.split("/")
        if _POSIX:
            fd_dir = self._descer(self.fd, partes[:-1], criar=False)
            try:
                self._livre_posix(fd_dir, partes[-1])
                os.unlink(partes[-1], dir_fd=fd_dir)
            except FileNotFoundError:
                pass
            finally:
                os.close(fd_dir)
            return
        final = self._garantir(self.raiz, partes[:-1], criar=False) / partes[-1]
        try:
            self._livre_caminho(final)
            os.unlink(final)
        except FileNotFoundError:
            pass

    def remover_pasta_temporaria(self, nome: str) -> None:
        """Apaga uma pasta temporária desta ferramenta (`.importando-*`) deixada na raiz do destino por uma cópia do
        SQLite interrompida. Só um nome na raiz do destino, conferido que não é ligação e que fica dentro dela."""
        if "/" in nome or not nome.startswith(PREFIXO_TEMP):
            return
        caminho = self.raiz / nome
        try:
            st = os.lstat(caminho)
        except FileNotFoundError:
            return
        if e_ligacao(st) or not stat.S_ISDIR(st.st_mode):
            return
        if Path(os.path.realpath(caminho)).is_relative_to(Path(os.path.realpath(self.raiz))):
            shutil.rmtree(caminho, ignore_errors=True)

    def nomes_na_raiz(self) -> list[str]:
        return sorted(os.listdir(self.fd if _POSIX else self.raiz))


def _json(dados):
    """O `escrever` do Gravador para um JSON (o hash sai do que ficou gravado)."""
    def escrever(fh) -> None:
        fh.write(json.dumps(dados, ensure_ascii=False, indent=1).encode("utf-8"))
    return escrever


def _temporarios(raiz: Path) -> list[tuple[str, bool]]:
    """Temporários desta ferramenta deixados por uma cópia interrompida: o arquivo `.importando-*.tmp` (em qualquer
    nível) e a pasta `.importando-*` (da cópia do SQLite pela API de backup). Cada achado é (caminho, é_pasta)."""
    achados, pendentes = [], [(raiz, "")]
    while pendentes:
        pasta, rel_pasta = pendentes.pop()
        with os.scandir(pasta) as it:
            for e in it:
                rel = f"{rel_pasta}/{e.name}" if rel_pasta else e.name
                st = os.lstat(e.path)
                if e_ligacao(st):
                    continue
                if stat.S_ISDIR(st.st_mode):
                    if e.name.startswith(PREFIXO_TEMP):
                        achados.append((rel, True))  # pasta temporária inteira (não desce)
                    else:
                        pendentes.append((Path(e.path), rel))
                elif stat.S_ISREG(st.st_mode) and e.name.startswith(PREFIXO_TEMP) and e.name.endswith(".tmp"):
                    achados.append((rel, False))
    return achados


# ------------------------------------------------------------------------------------------------ cópia
class Copia:
    def __init__(self, plano: dict, sha_plano: str, b1: dict | None):
        self.plano, self.sha_plano, self.b1 = plano, sha_plano, b1
        self.par = plano["parametros"]
        self.origem, projeto, partes = resolver_destino(self.par)
        self.ref = carregar_referencia(Path(self.par["desde"]["arquivo"])) if self.par["desde"] else None
        if self.ref and self.ref["sha256"] != self.par["desde"]["sha256"]:
            raise Recusa("o manifesto de --desde mudou depois do plano")
        self.grav = Gravador(projeto, partes)
        self.arquivos, self.git, self.fora, self.falhas, self.divergem = [], [], [], [], []
        self.contas = Counter()

    def _precisa_texto(self, item: dict) -> bool:
        canonico = (self.ref and self.ref["canonico"]) or (self.b1 and self.b1["canonico"])
        return bool(canonico) and item["classe"] != "opaco" and texto(item["caminho"])

    def _registrar(self, item: dict, res: dict, comparar: dict | None = None, **extra) -> None:
        """Registra o arquivo copiado; `comparar` é o hash dos bytes da origem quando a cópia não é byte a byte."""
        entrada = {"caminho": item["caminho"], "tamanho": res["tamanho"], "sha256": res["sha256"],
                   "classe": item["classe"], **extra}
        if "delta" in item:
            entrada["delta"] = item["delta"]
        b1 = comparar_com(self.b1, item["caminho"], comparar or res, item["classe"] == "opaco")
        if b1:
            entrada["b1"] = b1
            if b1 == "diferente":
                self.divergem.append(item["caminho"])
        self.arquivos.append(entrada)

    def _igual_a_referencia(self, item: dict, res: dict) -> bool:
        return item.get("delta") == "a-conferir" and comparar_com(self.ref, item["caminho"], res,
                                                                  item["classe"] == "opaco") == "igual"

    @staticmethod
    def _tem_wal_ao_lado(caminho: Path) -> bool:
        """Um `<banco>-wal` ao lado do banco (lstat, sem seguir ligação): sinal de transações não consolidadas."""
        try:
            os.lstat(Path(str(caminho) + "-wal"))
            return True
        except OSError:
            return False

    def copiar_arquivo(self, item: dict, **extra) -> None:
        caminho = self.origem / item["caminho"]
        existente = self.grav.hash_de(item["caminho"])
        if existente is not None:
            res = hash_origem(caminho, self.origem, item, self._precisa_texto(item))
            if res["sha256"] == existente:  # retomada pelo hash: já está no destino
                self.contas["ja_estavam"] += 1
                self._registrar(item, res, **extra)
                return
        fd = abrir_origem(caminho, self.origem, item)
        try:
            res = self.grav.gravar(item["caminho"],
                                   lambda fh: ler_blocos(fd, item["tamanho"], fh, self._precisa_texto(item)),
                                   item["mtime_ns"], decidir=lambda r: not self._igual_a_referencia(item, r))
        finally:
            os.close(fd)
        if res is None:
            self.contas["inalterados"] += 1
            return
        self.contas["copiados"] += 1
        self._registrar(item, res, **extra)

    def copiar_sqlite(self, item: dict) -> None:
        caminho = self.origem / item["caminho"]
        bytes_da_origem = None  # a cópia pela API não é byte a byte: a referência confere com os bytes da origem
        if item.get("delta") == "a-conferir" or (self.b1 is not None and item["caminho"] in self.b1["entradas"]):
            bytes_da_origem = hash_origem(caminho, self.origem, item)
        if item.get("delta") == "a-conferir" and self._igual_a_referencia(item, bytes_da_origem):
            self.contas["inalterados"] += 1
            return
        fd = abrir_origem(caminho, self.origem, item)
        try:
            cabecalho, antes = os.read(fd, len(CABECALHO_SQLITE)), os.fstat(fd)
        finally:
            os.close(fd)
        if cabecalho != CABECALHO_SQLITE:
            if self._tem_wal_ao_lado(caminho):
                self.falhas.append({"caminho": item["caminho"],
                                    "motivo": "banco sem o cabeçalho do SQLite (cifrado?) e com -wal ao lado: a cópia "
                                              "byte a byte perderia as transações não consolidadas; consolide o WAL "
                                              "ou inclua o banco e os -wal/-shm no --opaco"})
                return
            self.copiar_arquivo(item, copia="byte a byte: sem o cabeçalho do SQLite")
            return
        pasta = Path(tempfile.mkdtemp(prefix=PREFIXO_TEMP, dir=self.grav.raiz))
        try:
            if not Path(os.path.realpath(pasta)).is_relative_to(Path(os.path.realpath(self.grav.raiz))):
                raise Recusa("a pasta temporária da cópia do SQLite ficou fora do destino")
            saida = pasta / "copia.sqlite"
            p = subprocess.run([sys.executable, "-I", "-B", str(AQUI / "backup_sqlite.py"), "--origem", str(caminho),
                                "--destino", str(saida)], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=3600)
            try:
                info = json.loads(p.stdout)
            except ValueError:
                info = {}
            depois = os.lstat(caminho)
            if (depois.st_dev, depois.st_ino) != (antes.st_dev, antes.st_ino) or e_ligacao(depois):
                raise Mudou(f"trocado durante a cópia pela API de backup: {caminho.name}")
            if p.returncode != 0 or not info.get("ok"):
                self.falhas.append({"caminho": item["caminho"], "motivo": "a cópia pela API de backup não conferiu "
                                    f"(integridade ou contagens): {info.get('tipo') or info.get('erro', '?')}"})
                return
            # A pasta temporária fica no destino, onde a sessão grava: a cópia dela também passa pela abertura
            # conferida (uma ligação ou um vínculo físico posto no lugar de copia.sqlite não é copiado).
            fd = abrir_origem(saida, pasta, None)
            try:
                res = self.grav.gravar(item["caminho"], lambda fh: ler_blocos(fd, None, fh), item["mtime_ns"])
            finally:
                os.close(fd)
        finally:
            shutil.rmtree(pasta, ignore_errors=True)
        self.contas["copiados"] += 1
        self._registrar(item, res, comparar=bytes_da_origem,
                        copia="API de backup do SQLite (integridade e contagens conferidas)",
                        sqlite={"integrity_check": info["copia"]["integrity_check"],
                                "tabelas": len(info["copia"]["tabelas"])},
                        auxiliares_criados_na_origem=info.get("arquivos_auxiliares_criados", []))

    def zipar_git(self, item: dict) -> None:
        caminho = self.origem / item["caminho"]
        if item.get("worktree"):
            membros, omitidos = [(".git", item["tamanho"], item["mtime_ns"])], []
            base = caminho.parent
        else:
            membros, omitidos, ligacoes, vinculos = listar_git(caminho)  # uma listagem só: o zip sai do que foi conferido
            if sha256_canonico([membros, omitidos, ligacoes, vinculos]) != item["metadados_sha256"]:
                raise Mudou(f"o .git mudou depois do plano: {item['caminho']}")
            base = caminho

        def escrever(fh) -> None:
            with zipfile.ZipFile(fh, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
                for membro, tamanho, mtime_ns in membros:
                    fd = abrir_origem(base / membro, self.origem, {"tamanho": tamanho, "mtime_ns": mtime_ns})
                    try:
                        info = zipfile.ZipInfo(membro, date_time=data_zip(mtime_ns))
                        with zf.open(info, "w", force_zip64=tamanho > (1 << 31)) as destino:
                            ler_blocos(fd, tamanho, destino)
                    finally:
                        os.close(fd)

        res = self.grav.gravar(item["zip"], escrever)
        self.contas["git"] += 1
        self.git.append({"caminho": item["caminho"], "classe": "git", "zip": item["zip"], "tamanho": res["tamanho"],
                         "sha256": res["sha256"], "membros": len(membros), "omitidos": omitidos[:50],
                         "omitidos_total": len(omitidos), "worktree": bool(item.get("worktree")),
                         "nao_lidos": {"ligacoes": item.get("ligacoes", 0),
                                       "vinculos_fisicos": item.get("vinculos_fisicos", 0)}})

    def neutralizar(self, itens: list) -> dict | None:
        """As extensões de host vão para um zip na raiz da cópia; o hash de cada uma é o dos bytes da origem."""
        entradas = []
        if self.ref is not None:  # delta: só o que mudou entra no zip
            pendentes = []
            for item in itens:
                if item.get("delta") == "a-conferir" and self._igual_a_referencia(
                        item, hash_origem(self.origem / item["caminho"], self.origem, item)):
                    self.contas["inalterados"] += 1
                else:
                    pendentes.append(item)
            itens = pendentes
        if not itens:
            return None

        def escrever(fh) -> None:
            with zipfile.ZipFile(fh, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
                for item in itens:
                    fd = abrir_origem(self.origem / item["caminho"], self.origem, item)
                    try:
                        info = zipfile.ZipInfo(item["caminho"], date_time=data_zip(item["mtime_ns"]))
                        info.compress_type = zipfile.ZIP_DEFLATED
                        with zf.open(info, "w", force_zip64=item["tamanho"] > (1 << 31)) as destino:
                            res = ler_blocos(fd, item["tamanho"], destino, self._precisa_texto(item))
                    finally:
                        os.close(fd)
                    entradas.append((item, res))

        zip_res = self.grav.gravar(ZIP_NEUTRALIZADO, escrever)
        for item, res in entradas:
            self.contas["neutralizados"] += 1
            self._registrar(item, res, neutralizado_em=ZIP_NEUTRALIZADO)
        return {"zip": ZIP_NEUTRALIZADO, "tamanho": zip_res["tamanho"], "sha256": zip_res["sha256"],
                "membros": len(entradas)}

    def executar(self) -> dict:
        try:
            self._conferir_estado()
            self.grav.gravar(MARCA, _json({"plano_sha256": self.sha_plano}))
            para_neutralizar = []
            for item in self.plano["itens"]:
                try:
                    if item["classe"] in COPIADAS and item.get("neutralizar"):
                        para_neutralizar.append(item)
                    elif item["classe"] in ("comum", "opaco"):
                        self.copiar_arquivo(item)
                    elif item["classe"] == "sqlite":
                        self.copiar_sqlite(item)
                    elif item["classe"] == "git":
                        self.zipar_git(item)
                    else:
                        self.fora.append({k: item[k] for k in ("caminho", "classe", "regra", "nao_autorizados")
                                          if k in item})
                except Mudou as exc:
                    self.falhas.append({"caminho": item["caminho"], "motivo": str(exc)})
                except OSError as exc:
                    self.falhas.append({"caminho": item["caminho"], "motivo": f"ilegível: {type(exc).__name__}"})
            try:
                neutralizacao = self.neutralizar(para_neutralizar)
            except OSError as exc:  # Mudou também: o zip inteiro fica para a próxima rodada
                neutralizacao = None
                self.falhas += [{"caminho": i["caminho"], "motivo": f"zip das extensões não gravado: {exc}"}
                                for i in para_neutralizar]
            for rel, e_pasta in _temporarios(self.grav.raiz):
                if e_pasta:
                    self.grav.remover_pasta_temporaria(rel)
                else:
                    self.grav.remover(rel)
            manifesto = self._manifesto(neutralizacao)
            self.grav.gravar(MANIFESTO, _json(manifesto))
            self.grav.remover(MARCA)
            return manifesto
        finally:
            self.grav.fechar()

    def _conferir_estado(self) -> None:
        """Destino vazio, ou com a marca (ou o manifesto) desta mesma importação: retomada."""
        if not self.grav.nomes_na_raiz():
            return
        for nome in (MARCA, MANIFESTO):
            try:
                dados = self.grav.ler(nome)
                if dados is not None and json.loads(dados).get("plano_sha256") == self.sha_plano:
                    self.contas["retomada"] = 1
                    return
            except (ValueError, AttributeError):
                continue
        raise Recusa(f"o destino já tem arquivos que não são de uma importação deste plano: {self.grav.raiz} "
                     "(use uma pasta nova ou vazia)")

    def _manifesto(self, neutralizacao: dict | None) -> dict:
        return {"schema_version": ESQUEMA_MANIFESTO, "plano_sha256": self.sha_plano,
                "origem": self.par["origem"], "destino": self.par["destino"], "projeto": self.plano["projeto"],
                "modo": self.par["modo"], "desde": self.par["desde"],
                "manifesto_b1": self.b1 and {"arquivo": self.b1["arquivo"], "sha256": self.b1["sha256"]},
                "criado_em": datetime.now(timezone.utc).isoformat(), "hash_alg": "sha256",
                "arquivos": sorted(self.arquivos, key=lambda a: a["caminho"]),
                "git": sorted(self.git, key=lambda g: g["caminho"]), "neutralizacao": neutralizacao,
                "fora": self.fora, "fora_da_lista": self.plano["fora_da_lista"],
                "delta": None if self.ref is None else {"inalterados": self.contas["inalterados"],
                                                       "sumidos": self.plano["sumidos"]},
                "divergem_do_b1": sorted(self.divergem), "falhas": self.falhas,
                "contas": dict(sorted(self.contas.items())),
                "aviso": "cópia byte a byte: os opacos não foram decodificados, pesquisados nem mostrados; o SHA-256 "
                         "identifica o conteúdo e não prova que ele está certo"}


def carregar_plano(caminho: Path, sha: str) -> dict:
    try:
        plano = json.loads(Path(caminho).read_bytes())
    except (OSError, ValueError) as exc:
        raise Recusa(f"plano ilegível: {caminho} ({type(exc).__name__})") from None
    if sha256_canonico(plano) != sha.strip().lower():
        raise Recusa("o plano não é o aceito: o SHA-256 dele não confere com --plano-sha256")
    if (not isinstance(plano, dict) or plano.get("schema_version") != ESQUEMA_PLANO
            or not isinstance(plano.get("parametros"), dict) or not isinstance(plano.get("itens"), list)):
        raise Recusa(f"plano fora do formato {ESQUEMA_PLANO}")
    novo = montar_plano(plano["parametros"])
    if sha256_canonico(novo) != sha256_canonico(plano):
        antes = {i["caminho"]: i for i in plano["itens"]}
        agora = {i["caminho"]: i for i in novo["itens"]}
        mudou = sorted(p for p in antes.keys() | agora.keys() if antes.get(p) != agora.get(p))
        raise Recusa(f"a origem mudou depois do plano ({len(mudou)} caminho(s): {', '.join(mudou[:10])}): refaça o "
                     "plano e aceite o SHA-256 novo")
    return plano


# ------------------------------------------------------------------------------------------------ conferência
def _hash_local(caminho: Path, base: Path) -> str | None:
    try:
        st = os.lstat(caminho)
    except FileNotFoundError:
        return None
    if e_ligacao(st) or not stat.S_ISREG(st.st_mode):
        raise Mudou("ligação ou pasta no lugar do arquivo")
    fd = abrir_origem(caminho, base, None)
    try:
        return ler_blocos(fd, None)["sha256"]
    finally:
        os.close(fd)


def conferir(caminho_manifesto: Path) -> dict:
    try:
        m = json.loads(Path(caminho_manifesto).read_bytes())
        if m.get("schema_version") != ESQUEMA_MANIFESTO or not isinstance(m.get("arquivos"), list):
            raise ValueError
    except (OSError, ValueError, AttributeError):
        raise Recusa(f"manifesto de importação ilegível ou fora do formato {ESQUEMA_MANIFESTO}") from None
    raiz = Path(caminho_manifesto).parent
    raiz_real = Path(os.path.realpath(raiz))
    alterados, ausentes, problemas, esperados = [], [], [], {MANIFESTO}
    zip_neutro = None
    for e in m["arquivos"]:
        try:
            if e.get("neutralizado_em"):
                if e["neutralizado_em"] != ZIP_NEUTRALIZADO:  # o manifesto fica numa pasta gravável: nome fixo
                    raise Mudou("zip das extensões com outro nome no manifesto")
                esperados.add(ZIP_NEUTRALIZADO)
                if zip_neutro is None:
                    st = os.lstat(raiz / ZIP_NEUTRALIZADO)
                    if (e_ligacao(st) or not stat.S_ISREG(st.st_mode)
                            or not Path(os.path.realpath(raiz / ZIP_NEUTRALIZADO)).is_relative_to(raiz_real)):
                        raise Mudou("ligação ou pasta no lugar do zip das extensões")
                    zip_neutro = zipfile.ZipFile(raiz / ZIP_NEUTRALIZADO)
                h = hashlib.sha256()
                with zip_neutro.open(e["caminho"]) as fh:
                    while bloco := fh.read(BLOCO):
                        h.update(bloco)
                atual = h.hexdigest()
            else:
                esperados.add(e["caminho"])
                atual = _hash_local(raiz / e["caminho"], raiz)
        except (OSError, KeyError, zipfile.BadZipFile) as exc:
            problemas.append({"caminho": e.get("caminho"), "motivo": type(exc).__name__})
            continue
        if atual is None:
            ausentes.append(e["caminho"])
        elif atual != e["sha256"]:
            alterados.append(e["caminho"])
    if zip_neutro is not None:
        zip_neutro.close()
    zips = [(g["zip"], g["sha256"]) for g in m.get("git", [])]
    if m.get("neutralizacao"):
        zips.append((m["neutralizacao"]["zip"], m["neutralizacao"]["sha256"]))
    for rel, sha in zips:
        esperados.add(rel)
        try:
            atual = _hash_local(raiz / rel, raiz)
        except OSError as exc:
            problemas.append({"caminho": rel, "motivo": type(exc).__name__})
            continue
        if atual is None:
            ausentes.append(rel)
        elif atual != sha:
            alterados.append(rel)
    a_mais, ligacoes, pendentes = [], [], [(raiz, "")]
    while pendentes:
        pasta, rel_pasta = pendentes.pop()
        with os.scandir(pasta) as it:
            for e in it:
                rel = f"{rel_pasta}/{e.name}" if rel_pasta else e.name
                st = os.lstat(e.path)
                if e_ligacao(st):
                    ligacoes.append(rel)
                elif stat.S_ISDIR(st.st_mode):
                    pendentes.append((Path(e.path), rel))
                elif rel not in esperados:
                    a_mais.append(rel)
    return {"manifesto": str(caminho_manifesto), "alterados": sorted(alterados), "ausentes": sorted(ausentes),
            "a_mais": sorted(a_mais), "ligacoes": sorted(ligacoes), "problemas": problemas,
            "conferidos": len(m["arquivos"]) + len(zips)}


# ------------------------------------------------------------------------------------------------ linha de comando
def _uso(msg: str) -> int:
    print(json.dumps({"erro": msg}, ensure_ascii=False), file=sys.stderr)
    return 2


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plano", help="só metadados: classifica, grava o plano e mostra o SHA-256")
    p.add_argument("--origem", required=True)
    p.add_argument("--destino", required=True, help="pasta dentro de projects/<projeto>/ da raiz")
    p.add_argument("--raiz-fundacao", required=True)
    p.add_argument("--saida", type=Path, required=True, help="onde gravar o plano (fora da origem e do destino)")
    p.add_argument("--modo", choices=MODOS, default="completo")
    p.add_argument("--permitir", action="append", default=[], help="padrão do que entra (modo lista-de-permissao)")
    p.add_argument("--opaco", action="append", default=[],
                   help="padrão do que entra byte a byte, nunca decodificado (segredo autorizado pelo titular)")
    p.add_argument("--incluir-fraco", action="append", default=[],
                   help="padrão de nome fraco que entra como comum, depois de segredos.py conferir (ex.: tokenizer.py)")
    p.add_argument("--desde", help="manifesto do B1 ou de importação anterior: só o que é novo ou mudou")
    p.add_argument("--pasta-segredo", action="append", default=[], help="pasta de segredo do projeto (ex.: .omniroute)")
    p.add_argument("--reconstruivel", action="append", default=[], help="pasta reconstruível a mais (ex.: .next)")
    p.add_argument("--neutralizar-extensoes", dest="neutralizar", action="store_true",
                   help="padrão: skills, agentes, comandos, regras, .codex e .mcp.json vão para um zip na cópia")
    p.add_argument("--sem-neutralizar-extensoes", dest="neutralizar", action="store_false",
                   help="copia as extensões como estão (ex.: plugin candidato)")
    p.set_defaults(neutralizar=True)
    c = sub.add_parser("copiar", help="recalcula o plano, recusa se mudou e copia")
    c.add_argument("--plano", type=Path, required=True)
    c.add_argument("--plano-sha256", required=True)
    c.add_argument("--manifesto-b1", type=Path, help="compara cada arquivo copiado com o manifesto do B1")
    k = sub.add_parser("conferir", help="refaz os hashes da cópia")
    k.add_argument("--manifesto", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "plano":
            par = parametros(args)
            saida = Path(os.path.abspath(args.saida))
            if saida.is_relative_to(par["destino"]) or saida.is_relative_to(par["origem"]):
                return _uso("grave o plano fora da origem e do destino")
            try:  # o comando pronto do titular cita cada caminho (segunda revisão do pacote INTEG-FLUXOB)
                copiar = (f"{'python' if os.name == 'nt' else 'python3'} -I -B "
                          f"{CODIGO.citar_no_terminal(AQUI / 'importar.py')} copiar --plano "
                          f"{CODIGO.citar_no_terminal(saida)}")
            except ValueError as exc:
                return _uso(f"grave o plano noutro caminho: {exc}, e o comando pronto não o cita com segurança")
            plano = montar_plano(par)
            saida.parent.mkdir(parents=True, exist_ok=True)
            saida.write_bytes((json.dumps(plano, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
            sha = sha256_canonico(plano)
            print(json.dumps({"plano": str(saida), "sha256": sha, "origem": par["origem"], "destino": par["destino"],
                              "destino_real": os.path.realpath(par["destino"]), "raiz_fundacao": par["raiz_fundacao"],
                              "modo": par["modo"], "opaco": par["opacos"], "permitir": par["permitir"],
                              "resumo": plano["resumo"], "avisos": plano["avisos"],
                              "proximo_passo": f"{copiar} --plano-sha256 {sha}"},
                             ensure_ascii=False, indent=1))
            return 0
        if args.cmd == "copiar":
            plano = carregar_plano(args.plano, args.plano_sha256)
            par_plano = plano["parametros"]
            print(json.dumps({"copiar": "iniciando", "origem": par_plano["origem"], "destino": par_plano["destino"],
                              "destino_real": os.path.realpath(par_plano["destino"]),
                              "raiz_fundacao": par_plano["raiz_fundacao"], "modo": par_plano["modo"],
                              "opaco": par_plano["opacos"], "permitir": par_plano["permitir"],
                              "resumo": plano["resumo"]}, ensure_ascii=False, indent=1), file=sys.stderr)
            b1 = carregar_referencia(args.manifesto_b1) if args.manifesto_b1 else None
            m = Copia(plano, sha256_canonico(plano), b1).executar()
            print(json.dumps({"destino": m["destino"], "manifesto": str(Path(m["destino"]) / MANIFESTO),
                              "contas": m["contas"], "fora": len(m["fora"]), "divergem_do_b1": m["divergem_do_b1"],
                              "falhas": m["falhas"]}, ensure_ascii=False, indent=1))
            return 1 if m["falhas"] or m["divergem_do_b1"] else 0
        r = conferir(args.manifesto)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 1 if any(r[k] for k in ("alterados", "ausentes", "a_mais", "ligacoes", "problemas")) else 0
    except Recusa as exc:
        return _uso(str(exc))


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
