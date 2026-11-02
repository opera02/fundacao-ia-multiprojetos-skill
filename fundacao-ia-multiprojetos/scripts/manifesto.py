#!/usr/bin/env python3
"""Manifesto de arquivos com hash e comparação (livro A05, A33, A35; Apêndice E).

Um hash identifica conteúdo; não é backup e não prova que o conteúdo é correto.
O que parece segredo NÃO é lido: vai para `excluidos`, com o motivo.

  criar      --raiz DIR --saida manifesto.json [--texto-canonico] [--rotulo ID] [--excluir GLOB ...]
             [--git ignorar|listar|incluir] [--pasta-segredo NOME ...] [--incluir-pasta-ignorada NOME ...]
             [--incluir-fraco GLOB ...]
  verificar  --raiz DIR --manifesto manifesto.json [--excluir GLOB ... --mudar-politica]
  comparar   --a m1.json --b m2.json
  (diferenças -> código 1; uso incorreto -> 2)

Formato 3 (1.7.10; DESENHO-1.7.10 §5.1; MELHORIAS-1.7.10, seção 1, item 10): a regra de segredo é a única da skill
(`regras_de_segredo.py`), gravada na política do dia em que o manifesto foi criado:
- pasta de segredo (`.segredos`, `.envs`, `secrets`, `.ssh`... e as extras do projeto, `--pasta-segredo
  .omniroute`), em qualquer nível: podada e registrada em `excluidos` com o motivo, sem listar nem ler o que tem
  dentro;
- nome forte (chave, credencial): em `excluidos`, não lido. Nome fraco (`*token*`, `*senha*`, `.env.example`,
  `.mcp.json`...): em `excluidos` por padrão, candidato à conferência de conteúdo (`segredos.py conferir`); depois
  dela, `--incluir-fraco GLOB` leva os que casarem;
- `.git` com modo explícito (`--git`): `listar` (padrão) registra cada `.git` em `excluidos` ("pasta do Git: estado
  lido à parte"); `ignorar` o poda calado, como o formato 2; `incluir` calcula o hash de `objects`, `refs`,
  `packed-refs` e `HEAD`, registra `config` e `hooks` como "configuração ou código do Git: nunca executar" e o resto
  do `.git` (índice, logs...) como estado fora do modo incluir — nada disso é lido;
- pasta reconstruível ignorada (`.venv`, `node_modules`, `__pycache__`...): podada e registrada em `ignoradas` (fora
  de `excluidos`); `--incluir-pasta-ignorada .venv` a leva (por exemplo, para prender a venv de um plano).
Quem lê só as chaves do formato 2 (`codigo_do_plano.fora_do_manifesto`) continua vendo tudo o que o formato 3 não lê:
`pastas_ignoradas` traz também as pastas de segredo e o `.git` (fora do modo incluir), e `padroes_de_segredo` traz
os nomes fortes e os fracos. A diferença fica para o lado seguro: o que o manifesto não prende aparece como não preso.
Esse leitor do formato 2 tem duas ressalvas conhecidas, que a integração corrige em `codigo_do_plano` (passando a
classificar pela regra única quando a política tem `modo_git`): (a) `--incluir-fraco` não o destrava — ele continua
dando os nomes fracos como não presos mesmo depois de o titular os levar; (b) uma pasta de segredo com a caixa
diferente da gravada (ex.: `Credentials/`) é podada na criação, mas como `is_secret` compara sem normalizar a caixa
ela não aparece em "fora" e fica classificada como presa.

O manifesto grava a POLÍTICA efetiva, e a verificação reconstrói o conjunto com essa mesma política: criar e
verificar descrevem os mesmos arquivos. Manifesto do formato 2 continua verificável com a política gravada, sem herdar
a regra nova. Mudar a política na verificação exige `--mudar-politica`, e a mudança aparece em `politica`, separada
das mudanças nos arquivos. Manifesto do formato 1 (sem política gravada, ou `politica` nula): os caminhos que ele lista
como excluídos continuam excluídos, com aviso para refazê-lo. Política que não é um dicionário do formato 2 (e, no
manifesto do formato 3, também do 3) é uso incorreto (código 2). A regra é uma só (`politica_efetiva`): o lançador do
fluxo B a usa para saber o que o manifesto não prende [revisão de segurança da 1.7.7, segunda passada, R177B-B-01].

--texto-canonico: para .md/.txt/.json/.py/.yaml calcula o hash após normalizar
UTF-8, LF e NFC (o mesmo arquivo com CRLF e LF dá o mesmo hash).

Ligação (link simbólico ou junção, de pasta ou de arquivo) não é seguida: vai para `excluidos`
e o destino dela não é listado nem lido. Manifesto salvo DENTRO da raiz não descreve a si mesmo:
o caminho dele vai para `politica.exclusoes_literais` (comparação literal, sem curingas, e
reaplicada na verificação). Mover o manifesto dentro da raiz depois exige gerá-lo de novo.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import importlib.util
import json
import os
import stat
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
# Formato 2 (até a 1.7.9), congelado: a política padrão do formato 2 (`politica_padrao`) e as pastas reconstruíveis
# do formato 3 (todas, menos o `.git`, que tem modo próprio).
EXCLUDE_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache", ".pytest_cache"}
SECRET_GLOBS = [".env", ".env.*", "*.pem", "*.key", "*.pfx", "*.p12", "id_rsa*", "*credentials*", "*secret*",
                "auth.json", "*.kdbx"]
TEXT_SUFFIXES = {".md", ".txt", ".json", ".py", ".yaml", ".yml", ".toml", ".csv", ".html", ".sql"}
FORMATO_2 = "fundacao.manifest/2"
FORMATO = "fundacao.manifest/3"
MODOS_GIT = ("ignorar", "listar", "incluir")
CHAVES_3 = ("padroes_fracos", "pastas_de_segredo", "pastas_incluidas", "fracos_incluidos", "exemplos_de_segredo")
# `exemplos_de_segredo` entrou na política na 1.7.10 e pode faltar num manifesto do formato 3 anterior: as demais são
# obrigatórias; a falta de `exemplos_de_segredo` é aceita (cai nos fracos do dia em `_regra_da_politica`).
CHAVES_3_OBRIGATORIAS = ("padroes_fracos", "pastas_de_segredo", "pastas_incluidas", "fracos_incluidos")
GIT_DESCE = ("objects", "refs")              # modo incluir: pastas do .git com hash de tudo o que têm
GIT_ARQUIVOS = ("packed-refs", "HEAD")       # modo incluir: arquivos do .git com hash
GIT_CODIGO = ("config", "config.worktree", "hooks")
MOTIVO_LIGACAO = "ligação (link simbólico ou junção) não seguida"
MOTIVO_GIT = "pasta do Git: estado lido à parte"
MOTIVO_GIT_ARQUIVO = "arquivo .git (aponta o repositório de uma worktree): estado lido à parte"
MOTIVO_GIT_CODIGO = "configuração ou código do Git: nunca executar (não lido)"
MOTIVO_GIT_FORA = "estado do Git fora do modo incluir (só objects, refs, packed-refs e HEAD entram): não lido"
MOTIVO_IGNORADA = "pasta reconstruível ignorada, sem descer (leve com --incluir-pasta-ignorada)"
MOTIVO_EXCLUSAO = "exclusão explícita"
BLOCO = 1 << 20
# Windows: etiqueta de ponto de nova análise "substituta de nome" (bit 29) — junção, link simbólico e
# afins, que redirecionam para outro caminho; arquivo de nuvem (OneDrive) e deduplicação não a têm.
SUBSTITUTA_DE_NOME = 0x20000000


def _carregar(nome: str):
    """Um script ao lado deste, pelo caminho (sem mexer no `sys.path`; este módulo também é carregado assim)."""
    spec = importlib.util.spec_from_file_location(f"_manifesto_{nome}", AQUI / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


REGRAS = _carregar("regras_de_segredo")  # a regra única de segredo (1.7.10)


def politica_padrao(extras: list[str] | None = None, canonical: bool = False) -> dict:
    """A política do formato 2 (congelada): a dos manifestos antigos sem política gravada e a de quem a pede direto."""
    return {"pastas_ignoradas": sorted(EXCLUDE_DIRS), "padroes_de_segredo": list(SECRET_GLOBS),
            "exclusoes_extras": sorted(set(extras or [])), "texto_canonico": canonical}


def politica_formato3(extras: list[str] | None = None, canonical: bool = False, *, modo_git: str = "listar",
                      pastas_extras=(), incluir_ignoradas=(), incluir_fracos=()) -> dict:
    """A política do formato 3 com a regra única do dia. ValueError para opção que não cabe."""
    if modo_git not in MODOS_GIT:
        raise ValueError(f"modo do .git inválido: {modo_git!r} (use {', '.join(MODOS_GIT)})")
    extras_segredo = [REGRAS.validar_pasta_extra(n) for n in pastas_extras]
    incluidas = sorted(set(incluir_ignoradas))
    for nome in incluidas:
        if nome == ".git":
            raise ValueError("o .git tem modo próprio: use --git incluir")
        if REGRAS.e_pasta_de_segredo(nome, extras_segredo):
            raise ValueError(f"{nome} é pasta de segredo: não entra no manifesto")
        if nome not in EXCLUDE_DIRS:
            raise ValueError(f"{nome} não é pasta ignorada (as ignoradas: {', '.join(sorted(EXCLUDE_DIRS))})")
    pastas_de_segredo = sorted({*REGRAS.PASTAS_DE_SEGREDO, *extras_segredo})
    ignoradas = (EXCLUDE_DIRS - {".git"} - set(incluidas)) | set(pastas_de_segredo)
    if modo_git != "incluir":
        ignoradas.add(".git")
    return {"pastas_ignoradas": sorted(ignoradas),
            # fortes e fracos (os de nome): quem lê só o formato 2 vê todos como "não lidos"
            "padroes_de_segredo": [*REGRAS.NOMES_FORTES, *(g for g in REGRAS.NOMES_FRACOS if "/" not in g)],
            "padroes_fracos": list(REGRAS.NOMES_FRACOS), "exemplos_de_segredo": list(REGRAS.EXEMPLOS_DE_SEGREDO),
            "pastas_de_segredo": pastas_de_segredo,
            "modo_git": modo_git, "pastas_incluidas": incluidas, "fracos_incluidos": sorted(set(incluir_fracos)),
            "exclusoes_extras": sorted(set(extras or [])), "texto_canonico": canonical}


def _lista_de_textos(valor) -> bool:
    return isinstance(valor, list) and all(isinstance(v, str) for v in valor)


def politica_efetiva(ref) -> tuple[dict, set[str], str | None]:
    """A política com que o `verificar` reconstrói o conjunto de `ref`, os caminhos que continuam excluídos e o aviso.
    Formato 2: a política gravada, que tem de ser um dicionário com as listas e o `texto_canonico`; formato 3: também
    as listas da regra única e o `modo_git`. Formato 1 (sem `politica`, ou com ela nula): a padrão do formato 2, e o
    que ele lista em `excluidos` continua fora. Fora disso, ValueError."""
    if not isinstance(ref, dict):
        raise ValueError("o manifesto não é um objeto JSON")
    politica = ref.get("politica")
    if politica is None:
        excluidos = ref.get("excluidos", [])
        if not isinstance(excluidos, list):
            raise ValueError("a lista de excluídos do manifesto não é uma lista")
        antigos = {e["path"] for e in excluidos if isinstance(e, dict) and isinstance(e.get("path"), str)}
        return politica_padrao([], ref.get("texto_canonico", False)), antigos, (
            "manifesto do formato 1, sem política gravada: os caminhos que ele lista como excluídos continuam "
            "excluídos; arquivos novos que caberiam numa exclusão extra aparecem como novos. Refaça-o com a versão "
            "atual para gravar a política")
    if (not isinstance(politica, dict) or not isinstance(politica.get("texto_canonico"), bool)
            or not all(_lista_de_textos(politica.get(k)) for k in ("pastas_ignoradas", "padroes_de_segredo",
                                                                    "exclusoes_extras"))
            or not _lista_de_textos(politica.get("exclusoes_literais", []))):
        raise ValueError("política do manifesto fora do formato 2: um dicionário com as listas de textos "
                         "pastas_ignoradas, padroes_de_segredo e exclusoes_extras (e exclusoes_literais, se houver) e "
                         "texto_canonico verdadeiro ou falso")
    if ((ref.get("schema_version") == FORMATO or "modo_git" in politica or any(k in politica for k in CHAVES_3))
            and (not all(_lista_de_textos(politica.get(k)) for k in CHAVES_3_OBRIGATORIAS)
                 or not _lista_de_textos(politica.get("exemplos_de_segredo", []))
                 or politica.get("modo_git") not in MODOS_GIT)):
        raise ValueError("política do manifesto fora do formato 3: além das listas do formato 2, as listas de textos "
                         f"{', '.join(CHAVES_3_OBRIGATORIAS)} (e exemplos_de_segredo, se houver) e o modo_git "
                         f"({', '.join(MODOS_GIT)})")
    return politica, set(), None


def is_secret(name: str, padroes: list[str] = SECRET_GLOBS) -> bool:
    """Regra do formato 2 (só o nome): a de quem lê a política pelas chaves antigas."""
    low = name.lower()
    return any(fnmatch.fnmatch(low, g) for g in padroes)


def file_hash(path: Path, canonical: bool) -> str:
    """SHA-256 do arquivo; texto canônico (UTF-8, LF e NFC) nos sufixos de texto com `canonical`. O resto é lido em
    blocos (um pacote grande do Git no modo incluir não vai inteiro para a memória)."""
    if canonical and path.suffix.lower() in TEXT_SUFFIXES:
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return hashlib.sha256(data).hexdigest()
        text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
        return hashlib.sha256(unicodedata.normalize("NFC", text).encode("utf-8")).hexdigest()
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while bloco := fh.read(BLOCO):
            h.update(bloco)
    return h.hexdigest()


def e_ligacao(path: Path) -> bool:
    """Link simbólico ou junção (e afins do Windows), conferido sem seguir a ligação."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & SUBSTITUTA_DE_NOME)


def percorrer(root: Path, pastas_ignoradas: set[str]) -> list[tuple[Path, bool]]:
    """Formato 2. Caminhos sob `root`, ordenados, sem atravessar ligação (A12): a ligação vem marcada (True) e o
    que há do outro lado não é listado. `os.walk` sozinho entraria na junção do Windows."""
    itens = []
    for pasta, subpastas, nomes in os.walk(root):
        atual = Path(pasta)
        for nome in sorted(subpastas):
            if nome in pastas_ignoradas or e_ligacao(atual / nome):
                subpastas.remove(nome)
                if nome not in pastas_ignoradas:
                    itens.append((atual / nome, True))
        itens.extend((atual / nome, e_ligacao(atual / nome)) for nome in nomes)
    return sorted(itens)


def _hash_na_raiz(path: Path, rel: str, raiz_real: Path, canonical: bool, files: list, excluded: list) -> None:
    try:
        if not path.resolve().is_relative_to(raiz_real):  # trocado por ligação depois da listagem
            excluded.append({"path": rel, "motivo": "caminho resolvido fora da raiz: não lido"})
            return
        files.append({"path": rel, "size": path.stat().st_size, "sha256": file_hash(path, canonical)})
    except OSError as exc:
        excluded.append({"path": rel, "motivo": f"ilegível: {type(exc).__name__}"})


def _cabecalho(root: Path, politica: dict, formato: str) -> dict:
    return {"schema_version": formato, "raiz": root.name, "criado_em": datetime.now(timezone.utc).isoformat(),
            "hash_alg": "sha256", "texto_canonico": politica["texto_canonico"], "politica": politica}


def build(root: Path, politica: dict, excluidos_extra: set[str] | None = None) -> dict:
    """O manifesto de `root` pela política: a do formato 3 (com `modo_git`) ou a do formato 2."""
    if "modo_git" in politica:
        return _build3(root, politica, excluidos_extra)
    files, excluded = [], []
    raiz_real = root.resolve()
    literais = set(politica.get("exclusoes_literais", []))  # sem curingas: `manifest[1].json` é só ele
    for path, ligacao in percorrer(root, set(politica["pastas_ignoradas"])):
        rel = path.relative_to(root)
        if ligacao:
            excluded.append({"path": rel.as_posix(), "motivo": MOTIVO_LIGACAO})
            continue
        if not path.is_file():
            continue
        if (is_secret(path.name, politica["padroes_de_segredo"])
                or any(fnmatch.fnmatch(rel.as_posix(), g) for g in politica["exclusoes_extras"])
                or rel.as_posix() in literais
                or rel.as_posix() in (excluidos_extra or set())):
            excluded.append({"path": rel.as_posix(), "motivo": "segredo/credencial ou exclusão explícita"})
            continue
        _hash_na_raiz(path, rel.as_posix(), raiz_real, politica["texto_canonico"], files, excluded)
    return {**_cabecalho(root, politica, FORMATO_2), "arquivos": files, "excluidos": excluded,
            "aviso": "manifesto identifica conteúdo; não é cópia de segurança"}


def _regra_da_politica(politica: dict) -> dict:
    """As listas da regra única gravadas na política (os fortes são os de `padroes_de_segredo` que não são fracos).
    `exemplos_de_segredo` vem da política do dia; faltando (manifesto do formato 3 anterior à 1.7.10), cai nos fracos
    de hoje que são exemplos."""
    fracos = politica["padroes_fracos"]
    exemplos = politica.get("exemplos_de_segredo")
    if exemplos is None:
        exemplos = [g for g in REGRAS.EXEMPLOS_DE_SEGREDO if g in fracos]
    return {"fortes": [g for g in politica["padroes_de_segredo"] if g not in fracos], "fracos": fracos,
            "exemplos": list(exemplos), "pastas": politica["pastas_de_segredo"]}


def _casa_glob(rel: str, globs) -> bool:
    alvo = REGRAS.normalizar(rel)
    return any(fnmatch.fnmatchcase(alvo, REGRAS.normalizar(g)) for g in globs)


def _percorrer_git(pasta: Path, rel: str, arquivos: list, excluidos: list) -> None:
    """Uma pasta `.git` no modo `incluir`: o que entra no hash vai para `arquivos` (sem classificar nome: dentro de
    objects e refs os nomes são do Git); config e hooks e o resto vão para `excluidos`, sem leitura."""
    try:
        with os.scandir(pasta) as it:
            entradas = sorted(it, key=lambda e: e.name)
    except OSError as exc:
        excluidos.append({"path": rel, "motivo": f"pasta ilegível: {type(exc).__name__}", "classe": "ilegivel"})
        return
    for e in entradas:
        sub, caminho = f"{rel}/{e.name}", Path(e.path)
        if e_ligacao(caminho):
            excluidos.append({"path": sub, "motivo": MOTIVO_LIGACAO, "classe": "ligacao"})
        elif e.name in GIT_CODIGO:
            excluidos.append({"path": sub, "motivo": MOTIVO_GIT_CODIGO, "classe": "git-codigo"})
        elif e.name in GIT_ARQUIVOS and e.is_file(follow_symlinks=False):
            arquivos.append((caminho, sub, False))
        elif e.name in GIT_DESCE and e.is_dir(follow_symlinks=False):
            pendentes = [(caminho, sub)]
            while pendentes:
                atual, rel_atual = pendentes.pop()
                try:
                    with os.scandir(atual) as it:
                        filhos = sorted(it, key=lambda x: x.name)
                except OSError as exc:
                    excluidos.append({"path": rel_atual, "motivo": f"pasta ilegível: {type(exc).__name__}",
                                      "classe": "ilegivel"})
                    continue
                for f in filhos:
                    rel_f, cam_f = f"{rel_atual}/{f.name}", Path(f.path)
                    if e_ligacao(cam_f):
                        excluidos.append({"path": rel_f, "motivo": MOTIVO_LIGACAO, "classe": "ligacao"})
                    elif f.is_dir(follow_symlinks=False):
                        pendentes.append((cam_f, rel_f))
                    elif f.is_file(follow_symlinks=False):
                        arquivos.append((cam_f, rel_f, False))
        else:
            excluidos.append({"path": sub, "motivo": MOTIVO_GIT_FORA, "classe": "git"})


def _percorrer3(root: Path, politica: dict) -> tuple[list, list, list]:
    """Formato 3: (arquivos a ler, excluídos, ignoradas), sem atravessar ligação nem descer no que fica fora."""
    pastas_segredo, modo = politica["pastas_de_segredo"], politica["modo_git"]
    reconstruiveis = set(politica["pastas_ignoradas"]) - set(pastas_segredo) - {".git"}
    arquivos, excluidos, ignoradas = [], [], []
    pendentes = [(root, "")]
    while pendentes:
        pasta, rel_pasta = pendentes.pop()
        try:
            with os.scandir(pasta) as it:
                entradas = sorted(it, key=lambda e: e.name)
        except OSError as exc:
            excluidos.append({"path": rel_pasta or ".", "motivo": f"pasta ilegível: {type(exc).__name__}",
                              "classe": "ilegivel"})
            continue
        for e in entradas:
            rel, caminho = (f"{rel_pasta}/{e.name}" if rel_pasta else e.name), Path(e.path)
            try:
                rel.encode("utf-8")
            except UnicodeEncodeError:
                excluidos.append({"path": ascii(rel), "motivo": "nome fora do UTF-8: não lido", "classe": "ilegivel"})
                continue
            if e_ligacao(caminho):
                excluidos.append({"path": rel, "motivo": MOTIVO_LIGACAO, "classe": "ligacao"})
                continue
            if REGRAS.e_pasta_de_segredo(e.name, (), pastas_segredo):
                excluidos.append({"path": rel, "motivo": REGRAS.motivo("pasta-de-segredo"),
                                  "classe": "pasta-de-segredo"})
                continue
            e_pasta = e.is_dir(follow_symlinks=False)
            if REGRAS.normalizar(e.name) == ".git":
                if modo == "listar":
                    excluidos.append({"path": rel, "motivo": MOTIVO_GIT if e_pasta else MOTIVO_GIT_ARQUIVO,
                                      "classe": "git"})
                elif modo == "incluir" and e_pasta:
                    _percorrer_git(caminho, rel, arquivos, excluidos)
                elif modo == "incluir" and e.is_file(follow_symlinks=False):
                    arquivos.append((caminho, rel, False))
                continue
            if e_pasta:
                if e.name in reconstruiveis:
                    ignoradas.append({"path": rel, "motivo": MOTIVO_IGNORADA})
                else:
                    pendentes.append((caminho, rel))
            elif e.is_file(follow_symlinks=False):
                arquivos.append((caminho, rel, True))
    return arquivos, excluidos, ignoradas


def _build3(root: Path, politica: dict, excluidos_extra: set[str] | None = None) -> dict:
    files, excluded = [], []
    raiz_real = root.resolve()
    literais = set(politica.get("exclusoes_literais", [])) | set(excluidos_extra or set())
    regra = _regra_da_politica(politica)
    arquivos, excluidos_da_varredura, ignoradas = _percorrer3(root, politica)
    excluded += excluidos_da_varredura
    for path, rel, classificar in arquivos:  # o que vem do .git (modo incluir) não passa pela regra de nome
        classe = REGRAS.classificar(rel, **regra) if classificar else None
        if classe == "fraco" and _casa_glob(rel, politica["fracos_incluidos"]):
            classe = None  # conferido o conteúdo, o titular o leva (--incluir-fraco)
        if classe:
            excluded.append({"path": rel, "motivo": REGRAS.motivo(classe), "classe": classe})
        elif any(fnmatch.fnmatch(rel, g) for g in politica["exclusoes_extras"]) or rel in literais:
            excluded.append({"path": rel, "motivo": MOTIVO_EXCLUSAO, "classe": "exclusao"})
        else:
            _hash_na_raiz(path, rel, raiz_real, politica["texto_canonico"], files, excluded)
    return {**_cabecalho(root, politica, FORMATO), "arquivos": sorted(files, key=lambda f: f["path"]),
            "excluidos": sorted(excluded, key=lambda e: e["path"]),
            "ignoradas": sorted(ignoradas, key=lambda e: e["path"]),
            "aviso": "manifesto identifica conteúdo; não é cópia de segurança"}


def diff(a: dict, b: dict) -> dict:
    ma = {f["path"]: f["sha256"] for f in a["arquivos"]}
    mb = {f["path"]: f["sha256"] for f in b["arquivos"]}
    return {
        "alterados": sorted(p for p in ma.keys() & mb.keys() if ma[p] != mb[p]),
        "ausentes": sorted(ma.keys() - mb.keys()),
        "novos": sorted(mb.keys() - ma.keys()),
    }


def _uso(msg: str) -> int:
    print(json.dumps({"erro": msg}, ensure_ascii=False), file=sys.stderr)
    return 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("criar"); c.add_argument("--raiz", type=Path, required=True)
    c.add_argument("--saida", type=Path, required=True); c.add_argument("--texto-canonico", action="store_true")
    c.add_argument("--rotulo"); c.add_argument("--excluir", action="append", default=[])
    c.add_argument("--git", choices=MODOS_GIT, default="listar",
                   help="o .git: listar (padrão: em excluidos, com o motivo), ignorar (calado) ou incluir (hash de "
                        "objects, refs, packed-refs e HEAD; config e hooks nunca lidos)")
    c.add_argument("--pasta-segredo", action="append", default=[],
                   help="pasta de segredo do projeto (ex.: .omniroute), podada em qualquer nível como as da regra")
    c.add_argument("--incluir-pasta-ignorada", action="append", default=[],
                   help="leva uma pasta reconstruível hoje ignorada (ex.: .venv, para prender a venv de um plano)")
    c.add_argument("--incluir-fraco", action="append", default=[],
                   help="leva os arquivos de nome fraco que casam o padrão, depois de segredos.py conferir")
    v = sub.add_parser("verificar"); v.add_argument("--raiz", type=Path, required=True)
    v.add_argument("--manifesto", type=Path, required=True)
    v.add_argument("--excluir", action="append", default=[], help="exclusões a mais (exige --mudar-politica)")
    v.add_argument("--mudar-politica", action="store_true", help="aceita verificar com política diferente da gravada")
    k = sub.add_parser("comparar"); k.add_argument("--a", type=Path, required=True); k.add_argument("--b", type=Path, required=True)
    args = ap.parse_args()
    if args.cmd == "criar":
        raiz = args.raiz.resolve()
        try:
            politica = politica_formato3(args.excluir, args.texto_canonico, modo_git=args.git,
                                         pastas_extras=args.pasta_segredo,
                                         incluir_ignoradas=args.incluir_pasta_ignorada,
                                         incluir_fracos=args.incluir_fraco)
        except ValueError as exc:
            return _uso(str(exc))
        saida = args.saida.resolve()
        if saida.is_relative_to(raiz):
            # A13: o manifesto não entra no conjunto que descreve — nem na criação, nem na verificação.
            politica["exclusoes_literais"] = [saida.relative_to(raiz).as_posix()]
        m = build(raiz, politica)
        m["rotulo"] = args.rotulo
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"arquivos": len(m["arquivos"]), "excluidos": len(m["excluidos"]),
                          "ignoradas": len(m["ignoradas"]), "formato": FORMATO, "saida": str(args.saida)},
                         ensure_ascii=False))
        return 0
    if args.cmd == "verificar":
        ref = json.loads(args.manifesto.read_text(encoding="utf-8"))
        try:  # formato 1: a política extra não foi gravada; os excluídos listados, sim
            politica, excluidos_antigos, aviso = politica_efetiva(ref)
        except ValueError as exc:
            return _uso(f"{args.manifesto}: {exc}")
        mudanca = None
        if args.excluir:
            if not args.mudar_politica:
                return _uso("verificar com exclusões diferentes das gravadas muda a política; repita com "
                            "--mudar-politica (a mudança aparece separada das mudanças nos arquivos)")
            nova = {**politica, "exclusoes_extras": sorted(set(politica["exclusoes_extras"]) | set(args.excluir))}
            mudanca = {"mudou": nova != politica, "antes": politica, "depois": nova}
            politica = nova
        cur = build(args.raiz.resolve(), politica, excluidos_antigos)
        if mudanca:
            # O que a política nova passa a excluir não é "ausente": sai do domínio da comparação.
            fora = {e["path"] for e in cur["excluidos"]}
            mudanca["passam_a_excluidos"] = sorted(f["path"] for f in ref["arquivos"] if f["path"] in fora)
            ref = {**ref, "arquivos": [f for f in ref["arquivos"] if f["path"] not in fora]}
        d = diff(ref, cur)
        if mudanca:
            d["politica"] = mudanca
        if aviso:
            d["aviso"] = aviso
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return 1 if any(d[k] for k in ("alterados", "ausentes", "novos")) or (mudanca and mudanca["mudou"]) else 0
    a = json.loads(args.a.read_text(encoding="utf-8"))
    b = json.loads(args.b.read_text(encoding="utf-8"))
    d = diff(a, b)
    if a.get("politica") != b.get("politica"):
        d["politica_diferente"] = {"a": a.get("politica"), "b": b.get("politica")}
    print(json.dumps(d, ensure_ascii=False, indent=2))
    return 1 if any(d[k] for k in ("alterados", "ausentes", "novos")) or "politica_diferente" in d else 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
