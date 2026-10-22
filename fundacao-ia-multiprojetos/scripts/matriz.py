#!/usr/bin/env python3
"""Registro de requisitos R01–R51 (Apêndice B) + R52–R60 (proposta 3.0).

  init       --saida matriz.csv [--sem-30]   copia o modelo (estados iniciais honestos)
  validar    --matriz matriz.csv [--base DIR] esquema + exame das evidências (erros -> código 1)
  relatorio  --matriz matriz.csv              resumo na ordem da A36: bloqueados, inativos, ativos

Regras de ESQUEMA (livro A36/Apêndice B) — `schema_ok`:
- estados permitidos: em_desenvolvimento | implementado_ativo | implementado_inativo | bloqueado
  (não existe "concluído com ressalvas");
- `simulado` explícito em toda linha: sim | nao (vazio é recusado);
- implementado_* exige caminho_evidencia, versao_avaliada e nivel_evidencia executado/validado,
  e simulado = nao (simulação/mock não demonstra integração real);
- implementado_inativo exige demonstracao_anterior e teste_desativacao;
- bloqueado exige bloqueio, impacto e condicao_resolucao;
- os identificadores R01–R51 precisam existir, sem duplicatas nem renumeração; se a matriz
  usa a proposta 3.0 (qualquer R52–R60 presente), todos os R52–R60 precisam existir.

EXAME DAS EVIDÊNCIAS (linhas implementado_*) — `evidencias`: o caminho existe (relativo a
`--base`; padrão: a raiz da fundação quando a matriz está em `<raiz>/registry/`, senão a pasta da
matriz), não está vazio e cita a `versao_avaliada` no conteúdo; se a coluna opcional
`sha256_evidencia` estiver preenchida, o hash do arquivo confere. Esquema válido NÃO é capacidade
demonstrada: o mérito da evidência (se ela prova o requisito) continua exigindo revisão humana.

O caminho da evidência fica na base (auditoria Codex Security da 1.7.6, #7): absoluto, com unidade, `:` ou `..` é
recusado antes de tocar o disco (a recusa não diz se o alvo existe); cada parte é conferida sem seguir ligação (link
simbólico ou junção), e a folha precisa ser arquivo comum ou pasta. O arquivo é lido em blocos até 50 MB (a versão é
procurada só nos de até 5 MB, como antes); a pasta é percorrida sem atravessar ligação, e o exame para no teto de 500
itens, 16 níveis ou 50 MB lidos durante a própria varredura.

Caminho protegido não é lido (revisão de segurança da 1.7.7, R177-VAL-01): a base padrão é a raiz da fundação, e
conferir a versão ou o hash de qualquer arquivo dela seria oráculo do conteúdo. São recusados antes de tocar o disco,
com a mesma resposta exista ou não o alvo, a primeira parte `state`, `projects/<projeto>/data/` e os nomes da lista
de negação dos perfis do host (`.env*`, `secrets`, chaves, credenciais, `.ssh`, `.codex`...), comparados como o
Windows compara (sem caixa, sem ponto ou espaço no fim; nome curto 8.3 recusado); o nome real no disco é conferido
de novo depois do exame. Dentro de uma pasta de evidência, o que é protegido não é aberto. Arquivo com vínculo físico
(hard link, mais de um nome) também não é lido: o outro nome pode estar fora da base (R177-VAL-02).

Quem escolhe o `--base` não escolhe o que é protegido (revisão de segurança da 1.7.7, segunda passada, variante do
R177-VAL-01): a regra vale também para o caminho inteiro, relativo a cada raiz de fundação acima dele — a pasta com
`registry/` ou com `state/state.sqlite`, de que só a existência é consultada —, e a base acima da raiz da fundação da
matriz ou dentro de caminho protegido é recusada antes de qualquer evidência ser lida. Antes, `--base <raiz>/state`,
`--base <pai da raiz>` e `--base <raiz>/projects/<outro>/data` devolviam o oráculo de conteúdo.

Nem fora de uma fundação (revisão de segurança da 1.7.7, terceira passada, R177C-B-01): a base cujo caminho real passa
por nome da lista de negação (`.ssh`, `.codex`, `secrets`...) ou por nome curto 8.3, em qualquer parte e comparado como
o Windows compara, é recusada antes de qualquer consulta dentro dela, com a mesma resposta exista ou não o alvo; o
caminho inteiro da evidência passa pela mesma conferência. Antes, `--base ~/.ssh` com a linha `id_ed25519` saía
"conferida" quando a versão avaliada era um trecho da chave e "não cita a versão" quando não.

Acima da raiz, só o que o host nega lá (revisão de segurança da 1.7.7, quarta passada, R177D-1): as regras dos perfis
são `./**/...`, relativas à raiz da fundação; com uma raiz acima, valem as partes relativas a ela, e o caminho inteiro
só é conferido sem raiz nenhuma — salvo `.ssh` e `.codex`, que os perfis negam em `~/` e valem em qualquer lugar (uma
`registry/` plantada em `.ssh` não tira a proteção). Antes, a fundação na conta "Secretaria" (casa `*secret*`) ou sob
`credentials-antigas` tinha toda evidência recusada e nunca cumpria o critério de conclusão.
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from collections import Counter
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "templates" / "MATRIZ-REQUISITOS.csv"
STATES = ("em_desenvolvimento", "implementado_ativo", "implementado_inativo", "bloqueado")
LEVELS = ("", "documentado", "codigo_presente", "executado", "validado")
REQUIRED_IDS = [f"R{i:02d}" for i in range(1, 52)]
IDS_30 = [f"R{i:02d}" for i in range(52, 61)]
SIM = {"sim", "s", "true"}
NAO = {"nao", "não", "n", "false"}
ALCANCE = ("schema_ok = estados, campos e identificadores; evidencias = o arquivo indicado existe, não está vazio, "
           "cita a versão avaliada e confere com sha256_evidencia quando informado. Nenhum dos dois prova que a "
           "evidência demonstra o requisito: isso continua exigindo revisão humana. O caminho fica na base, sem "
           "'..' e sem passar por ligação; a leitura tem teto")
# Leitura das evidências com teto (auditoria Codex Security da 1.7.6, #7).
TETO_EVIDENCIA = 50_000_000      # bytes de um arquivo de evidência (hash em blocos)
TETO_CITACAO = 5_000_000         # a versão avaliada só é procurada em arquivo até este tamanho (como antes)
TETO_PASTA_ITENS = 500           # entradas (arquivos e pastas) examinadas numa pasta de evidência
TETO_PASTA_PROFUNDIDADE = 16     # níveis abaixo da pasta de evidência
TETO_PASTA_BYTES = 50_000_000    # bytes lidos numa pasta de evidência
BLOCO = 1 << 20
# Windows: etiqueta de ponto de nova análise "substituta de nome" (bit 29) — junção, link simbólico e afins.
SUBSTITUTA_DE_NOME = 0x20000000
# Nomes que os perfis do host negam à leitura (assets/host/*/settings*.json: permissions.deny e denyRead), em
# qualquer parte do caminho abaixo da raiz; mais a primeira parte `state` e `projects/<projeto>/data/` (R177-VAL-01).
# `NOMES_DO_PERFIL` marca os que os perfis negam também em `~/` (`~/.ssh/**`, `~/.codex`): esses valem em qualquer
# parte, acima da raiz da fundação também (quarta passada, R177D-1).
NOMES_DO_PERFIL = (".ssh", ".codex")
NOMES_PROTEGIDOS = (".env*", "secrets", "*.pem", "*.key", "*.pfx", "*.p12", "id_rsa*", "*credentials*", "*secret*",
                    "*.kdbx", "auth.json") + NOMES_DO_PERFIL
CURTO_8_3 = re.compile(r"~\d")  # nome curto do Windows (ENV~1): apelido de um nome longo
PROTEGIDO = "segredo, estado ou dados de projeto, que o host nega à leitura: não lido"


class AcimaDoTeto(Exception):
    pass


class Trocado(OSError):
    """O arquivo aberto não é o examinado: virou ligação, deixou de ser comum ou resolve fora da base."""


class VinculoFisico(OSError):
    """Arquivo com mais de um nome (hard link): o conteúdo pode ser o de um arquivo de fora da base (R177-VAL-02)."""


def base_padrao(matriz: Path) -> Path:
    pasta = Path(matriz).resolve().parent
    return pasta.parent if pasta.name == "registry" else pasta


def e_ligacao(st: os.stat_result) -> bool:
    """Link simbólico ou junção (e afins do Windows), pelo lstat — sem seguir a ligação."""
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & SUBSTITUTA_DE_NOME)


def partes_relativas(texto: str) -> list[str] | None:
    """Partes de um caminho relativo que não sai da base, ou None: raiz, unidade (`C:`), UNC, `:` e `..` (ou parte só de
    pontos e espaços) são recusados antes de qualquer acesso ao disco — a recusa não revela se o alvo existe."""
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


def protegido(base: Path, partes) -> bool:
    """Caminho (partes relativas à base) que o host nega à leitura, decidido pelo texto, sem tocar o disco: primeira
    parte `state`, nome da lista de negação ou nome curto 8.3 em qualquer parte, ou `projects/<projeto>/data` que
    chegue à parte relativa (a base pode ser a pasta de um projeto)."""
    nomes = [_nome(p) for p in partes]
    if not nomes or nomes[0] == "state" or negado(nomes):
        return True
    todas = [_nome(p) for p in Path(base).parts] + nomes
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


def protegido_na_fundacao(base: Path, partes, vistas: dict | None = None) -> bool:
    """`protegido` relativo à base e também no caminho inteiro (base real + partes), relativo a cada raiz de fundação
    acima dele: base dentro de `state/` ou de `projects/<p>/data/`, ou acima da raiz, não tira a proteção (variante do
    R177-VAL-01); nem a base em pasta negada sem raiz acima (R177C-B-01), e com raiz, só o relativo a ela (R177D-1). O
    texto decide primeiro, sem tocar o disco; depois, só a existência de `registry/` e de `state/state.sqlite` acima do
    alvo é consultada — nada é lido."""
    if protegido(base, partes):
        return True
    alvo = Path(os.path.realpath(base)).joinpath(*partes)
    raizes = raizes_acima(alvo.parent, vistas)
    if caminho_negado(alvo, raizes):  # sem raiz acima, o caminho inteiro (R177C-B-01); com raiz, o relativo (R177D-1)
        return True
    return any(protegido(r, alvo.relative_to(r).parts) for r in raizes)


def base_recusada(base: Path, matriz: Path) -> str | None:
    """Por que a base não vale, ou None: fica em pasta que o host nega à leitura — pelo caminho real, `.ssh` e `.codex`
    antes de consultar qualquer coisa dentro dela (R177C-B-01), o resto sem raiz de fundação acima (R177D-1) —, acima
    da raiz de fundação da matriz ou dentro de caminho protegido de uma fundação (variante do R177-VAL-01). Recusada,
    nenhuma evidência é lida."""
    real = Path(os.path.realpath(base))
    if negado_no_perfil(real) or caminho_negado(real, raizes_acima(real)):
        return "a base fica em pasta que o host nega à leitura (nome de segredo da lista de negação ou nome curto 8.3)"
    for raiz in raizes_acima(Path(os.path.realpath(matriz)).parent):
        if raiz != real and raiz.is_relative_to(real):
            return f"a base fica acima da raiz da fundação da matriz ({raiz})"
    if any(r != real and protegido(r, real.relative_to(r).parts) for r in raizes_acima(real)):
        return "a base fica dentro de caminho protegido (segredo, estado ou dados de projeto)"
    return None


def nome_real_protegido(base: Path, alvo: Path) -> bool:
    """O nome no disco (o Windows resolve caixa, nome curto e ponto no fim) também não pode ser protegido."""
    try:
        real = Path(os.path.realpath(base))
        return protegido_na_fundacao(real, Path(os.path.realpath(alvo)).relative_to(real).parts)
    except (OSError, ValueError):
        return True


def examinar(base: Path, partes: list[str]) -> tuple[Path, os.stat_result | None, str | None]:
    """Desce da base parte por parte com lstat: nenhuma pode ser ligação, e as do meio precisam ser pastas.
    Devolve (caminho, lstat da folha, falha: "inexistente" ou "ligacao")."""
    atual, st = base, None
    for i, parte in enumerate(partes):
        atual = atual / parte
        try:
            st = os.lstat(atual)
        except OSError:
            return atual, None, "inexistente"
        if e_ligacao(st):
            return atual, None, "ligacao"
        if i < len(partes) - 1 and not stat.S_ISDIR(st.st_mode):
            return atual, None, "inexistente"
    return atual, st, None


def blocos(p: Path, base_real: Path, teto: int):
    """Conteúdo do arquivo comum `p` em blocos, até `teto` bytes (passou: AcimaDoTeto). Abre sem seguir ligação na folha
    (POSIX) e sem esperar em FIFO; depois de abrir, confere que é o arquivo do lstat e que ele resolve dentro da base.
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
                or not Path(os.path.realpath(p)).is_relative_to(base_real)):
            raise Trocado(f"mudou entre o exame e a leitura: {p.name}")
        total = 0
        while bloco := os.read(fd, BLOCO):
            total += len(bloco)
            if total > teto:
                raise AcimaDoTeto
            yield bloco
    finally:
        os.close(fd)


def verify_evidence(rows: list[dict], base: Path, recusa: str | None = None) -> dict:
    """Exame das evidências das linhas implementadas (separado do esquema). Com a base recusada (`recusa`, de
    `base_recusada`), nenhuma é lida: todas saem com o motivo, exista ou não o alvo."""
    conferidas, problemas, examinadas = [], [], 0
    for r in rows:
        if not r.get("estado", "").startswith("implementado") or not (r.get("caminho_evidencia") or "").strip():
            continue
        examinadas += 1
        rid, versao = r["id"], (r.get("versao_avaliada") or "").strip()
        caminho = r["caminho_evidencia"].strip()
        esperado = (r.get("sha256_evidencia") or "").strip().lower()
        achados = ([f"base das evidências recusada ({recusa}): nada foi lido"] if recusa
                   else examinar_evidencia(base, caminho, versao, esperado))
        problemas += [f"{rid}: {p}" for p in achados]
        if not achados:
            conferidas.append(rid)
    return {"base": str(base), "examinadas": examinadas, "conferidas": conferidas, "problemas": problemas}


def examinar_evidencia(base: Path, caminho: str, versao: str, esperado: str) -> list[str]:
    partes = partes_relativas(caminho)
    if partes is None:
        return [f"caminho de evidência recusado ('{caminho}'): use caminho relativo à base, sem '..', unidade nem ':'"]
    if protegido_na_fundacao(base, partes):  # antes de tocar o alvo: a resposta não diz se ele existe (R177-VAL-01)
        return [f"caminho de evidência protegido ('{caminho}'): {PROTEGIDO}"]
    alvo, st, falha = examinar(base, partes)
    if falha == "inexistente":
        return [f"evidência inexistente em '{caminho}' (base {base})"]
    if falha == "ligacao":
        return [f"evidência '{caminho}' passa por ligação (link simbólico ou junção): não seguida"]
    if nome_real_protegido(base, alvo):
        return [f"caminho de evidência protegido ('{caminho}'): {PROTEGIDO}"]
    if stat.S_ISDIR(st.st_mode):
        achados = examinar_pasta(alvo, base, caminho, versao)
        if esperado:
            achados.append(f"sha256_evidencia exige arquivo, não pasta ('{caminho}')")
        return achados
    if not stat.S_ISREG(st.st_mode):
        return [f"evidência '{caminho}' não é arquivo comum nem pasta: não lida"]
    h, inicio, total = hashlib.sha256(), bytearray(), 0
    try:
        for bloco in blocos(alvo, base, TETO_EVIDENCIA):
            h.update(bloco)
            total += len(bloco)
            if total <= TETO_CITACAO:
                inicio += bloco
    except AcimaDoTeto:
        return [f"evidência '{caminho}' acima do teto de {TETO_EVIDENCIA // 1_000_000} MB: não examinada"]
    except VinculoFisico:  # R177-VAL-02
        return [f"evidência '{caminho}' tem vínculo físico (hard link) com outro nome: não lida; copie o arquivo"]
    except OSError as exc:
        return [f"evidência '{caminho}' ilegível ({type(exc).__name__})"]
    if not total:
        return [f"evidência vazia em '{caminho}'"]
    if esperado and h.hexdigest() != esperado:
        return [f"sha256 da evidência não confere com sha256_evidencia ('{caminho}')"]
    if versao and not esperado and not (total <= TETO_CITACAO and _cita(bytes(inicio), versao)):
        return [f"evidência '{caminho}' não cita a versão avaliada '{versao}' (ou registre sha256_evidencia)"]
    return []


def arquivos_da_pasta(pasta: Path, parada: list[str], pular=lambda caminho: False):
    """Arquivos comuns sob a pasta, sem atravessar ligação nem abrir o que `pular` recusa. Os tetos de itens e de
    profundidade valem DURANTE a varredura (não depois de ordenar): passou, para e anota o motivo em `parada`."""
    vistos, pilha = 0, [(pasta, 0)]
    while pilha:
        atual, nivel = pilha.pop()
        entradas = []
        try:
            with os.scandir(atual) as it:
                for e in it:
                    vistos += 1
                    if vistos > TETO_PASTA_ITENS:
                        parada.append(f"{TETO_PASTA_ITENS} itens")
                        break
                    entradas.append(e)
        except OSError:
            continue
        subpastas = []
        for e in sorted(entradas, key=lambda e: e.name):
            if pular(Path(e.path)):  # caminho protegido: nem aberto nem lido (R177-VAL-01)
                continue
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            if e_ligacao(st):
                continue
            if stat.S_ISDIR(st.st_mode):
                if nivel + 1 > TETO_PASTA_PROFUNDIDADE:
                    parada.append(f"profundidade ({TETO_PASTA_PROFUNDIDADE} níveis)")
                    continue
                subpastas.append((Path(e.path), nivel + 1))
            elif stat.S_ISREG(st.st_mode):
                yield Path(e.path), st.st_size
        if vistos > TETO_PASTA_ITENS:
            return
        pilha.extend(reversed(subpastas))


def examinar_pasta(pasta: Path, base: Path, caminho: str, versao: str) -> list[str]:
    """Pasta de evidência: algum arquivo comum e, com versão avaliada, algum que a cite."""
    parada, lidos, achou, vistas = [], 0, False, {}
    for arq, tamanho in arquivos_da_pasta(pasta, parada,
                                          lambda p: protegido_na_fundacao(base, p.relative_to(base).parts, vistas)):
        achou = True
        if not versao:
            return []
        if tamanho > TETO_CITACAO:
            continue
        if lidos + tamanho > TETO_PASTA_BYTES:
            parada.append(f"{TETO_PASTA_BYTES // 1_000_000} MB lidos")
            break
        try:
            dados = b"".join(blocos(arq, base, TETO_CITACAO))
        except (AcimaDoTeto, OSError):
            continue
        lidos += len(dados)
        if _cita(dados, versao):
            return []
    teto = f" (o exame parou no teto de {parada[0]})" if parada else ""
    if not achou:
        return [f"pasta de evidência vazia em '{caminho}'{teto}"]
    return [f"nenhuma evidência em '{caminho}' cita a versão avaliada '{versao}'{teto}"]


def _cita(dados: bytes, versao: str) -> bool:
    return versao.lower() in dados.decode("utf-8", "ignore").lower()


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def validate(rows: list[dict]) -> list[str]:
    errors = []
    ids = [r["id"] for r in rows]
    for dup, n in Counter(ids).items():
        if n > 1:
            errors.append(f"{dup}: identificador duplicado")
    for rid in REQUIRED_IDS:
        if rid not in ids:
            errors.append(f"{rid}: requisito do Apêndice B ausente")
    if any(rid in ids for rid in IDS_30):
        for rid in IDS_30:
            if rid not in ids:
                errors.append(f"{rid}: requisito da proposta 3.0 ausente (a matriz usa R52–R60)")
    for r in rows:
        rid, st = r["id"], r.get("estado", "")
        if st not in STATES:
            errors.append(f"{rid}: estado inválido '{st}'")
            continue
        if r.get("nivel_evidencia", "") not in LEVELS:
            errors.append(f"{rid}: nivel_evidencia inválido '{r.get('nivel_evidencia')}'")
        simulado = (r.get("simulado") or "").strip().lower()
        if simulado not in SIM | NAO:
            errors.append(f"{rid}: simulado vazio ou inválido '{r.get('simulado') or ''}': use sim ou nao")
        if st.startswith("implementado"):
            for field in ("caminho_evidencia", "versao_avaliada"):
                if not r.get(field, "").strip():
                    errors.append(f"{rid}: {st} sem {field}")
            if r.get("nivel_evidencia") not in ("executado", "validado"):
                errors.append(f"{rid}: {st} exige evidência executada ou validada")
            if simulado in SIM:
                errors.append(f"{rid}: simulação não demonstra o requisito; mantenha em_desenvolvimento ou bloqueado")
        if st == "implementado_inativo":
            for field in ("demonstracao_anterior", "teste_desativacao"):
                if not r.get(field, "").strip():
                    errors.append(f"{rid}: implementado_inativo sem {field}")
        if st == "bloqueado":
            for field in ("bloqueio", "impacto", "condicao_resolucao"):
                if not r.get(field, "").strip():
                    errors.append(f"{rid}: bloqueado sem {field}")
    return errors


def report(rows: list[dict]) -> dict:
    order = {"bloqueado": 0, "implementado_inativo": 1, "em_desenvolvimento": 2, "implementado_ativo": 3}
    by_state = Counter(r["estado"] for r in rows)
    lines = [
        {k: r.get(k, "") for k in ("id", "categoria", "estado", "nivel_evidencia", "bloqueio", "impacto",
                                   "condicao_resolucao", "caminho_evidencia", "responsavel_proximo_passo")}
        for r in sorted(rows, key=lambda r: (order.get(r["estado"], 9), r["id"]))
    ]
    return {"por_estado": dict(by_state), "total": len(rows), "linhas": lines}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init"); i.add_argument("--saida", type=Path, required=True)
    i.add_argument("--sem-30", action="store_true", help="omite R52–R60 (proposta 3.0)")
    v = sub.add_parser("validar"); v.add_argument("--matriz", type=Path, required=True)
    v.add_argument("--base", type=Path, help="pasta a que os caminhos de evidência são relativos")
    r = sub.add_parser("relatorio"); r.add_argument("--matriz", type=Path, required=True)
    args = ap.parse_args()
    if args.cmd == "init":
        if args.saida.exists():
            print(json.dumps({"erro": "matriz já existe; não sobrescrevo (atualize as linhas afetadas)"},
                             ensure_ascii=False))
            return 1
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        if args.sem_30:
            rows = [x for x in load(TEMPLATE) if x["id"] in REQUIRED_IDS]
            with args.saida.open("w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
                w.writeheader()
                w.writerows(rows)
        else:
            shutil.copyfile(TEMPLATE, args.saida)
        print(json.dumps({"criada": str(args.saida)}, ensure_ascii=False))
        return 0
    rows = load(args.matriz)
    if args.cmd == "validar":
        errors = validate(rows)
        base = (args.base or base_padrao(args.matriz)).resolve()
        evid = verify_evidence(rows, base, base_recusada(base, args.matriz))  # variante do R177-VAL-01
        todos = errors + evid["problemas"]
        print(json.dumps({"ok": not todos, "schema_ok": not errors, "erros": todos, "erros_schema": errors,
                          "evidencias": evid, "linhas": len(rows), "alcance": ALCANCE}, ensure_ascii=False, indent=2))
        return 1 if todos else 0
    print(json.dumps(report(rows), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
