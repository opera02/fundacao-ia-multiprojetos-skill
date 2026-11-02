"""Regras da cópia de segurança: o que a política inclui, para onde a cópia vai e as pastas vazias do `.git` (revisão
de segurança da 1.7.10, grupo KITCOPIA). O que o `.git` leva fica em git_na_copia.py e config_git.py.

- Política (KIT-F2): `registros_incluidos` lê a lista `incluir` de registry/backup_policy.json (ou REGISTROS_PADRAO).
  Cada caminho é relativo, sem `:` nem `..`, e não é a própria raiz; a primeira parte, sem caixa e sem ponto ou espaço
  no fim (o Windows e o DrvFs abrem `State`, `STATE`, `state.` e `state ` como `state`), não é `state` nem `.git`; e o
  caminho, resolvido (ligação no meio, nome curto) e pelo objeto do disco, fica dentro da raiz e fora de `<raiz>/state`
  e `<raiz>/.git` — a ligação do fim o backup não segue (só a anota), como antes. `protegido` lê assim um nome de
  files/: a verificação recusa a cópia que traz state/ ou .git ali (a restauração montaria a raiz com eles e cairia no
  `mkdir` de state/).
- Destino (KIT-F7): `raiz_que_contem` diz se o destino fica dentro da raiz da fundação, pelo caminho resolvido e pelo
  objeto do disco (`dentro_da_copia`), como o ensaio do atualizador (`_base_do_ensaio`): a cópia e a restauração
  recusam esse destino (a cópia ficaria ao alcance das sessões dos projetos e do backup seguinte). A pasta acima do
  state/ do registro só conta como raiz com cara de fundação (`cara_de_fundacao`: fundacao/ ou projects/): um cofre
  com o registro e o livro guardados fora não é fundação (correções da revisão 1). No desastre (banco perdido), a CLI
  passa a --raiz com cara de fundação (correções da revisão 2).
- Pastas vazias do .git (KIT-F4): a cópia lista arquivos, e o git não reconhece um .git sem refs/ ou objects/ (`git
  pack-refs` e `git gc` esvaziam refs/heads). `pastas_vazias` (as vazias vistas num .git levado e, em cada um com HEAD,
  MINIMO_DO_GIT) vai no manifesto e volta na restauração (`recriar_pastas_vazias`); `git_incompleto` aponta o
  repositório com HEAD que voltaria sem objects/ ou refs/ e a pasta anotada que não cabe num .git levado. A cópia só
  anota o que a própria verificação aceita: nada que seja arquivo copiado ou fique sob um, também sem caixa e sem ponto
  ou espaço no fim (no repositório reftable, refs/heads é arquivo; no NTFS, REFS/HEADS abre refs/heads), e nome que a
  restauração recria neste sistema (`:` e `\\` são nome válido no Linux; no Windows, o nome com espaço ou ponto no fim
  não é: ' ' e '. ' abrem a pasta de cima). O .git levado é o de projects/<projeto>/: o manifesto que diz outro (state,
  .git da raiz) não recria nada (correções da revisão 1). A pasta que mesmo assim não se recria (nome longo demais
  para o sistema de destino) não deixa a restauração liberar (correções da revisão 2).
"""

from __future__ import annotations

import json
import os
import posixpath
from pathlib import Path, PurePath

from . import preparo
from .ancora_copia import dentro_da_copia
from .contracts import ValidationError

# Registros da fundação fora do kit: entram na cópia por padrão, para o backup não precisar de um "complemento"
# (auditoria da implantação real de 2026-10-19/20: dez complementos num só dia). A raiz troca a lista em
# registry/backup_policy.json ({"incluir": [...]}); `state/` (banco e registros) tem tratamento próprio.
REGISTROS_PADRAO = ("docs", "evidence", "ferramentas", "tests", "RETOMADA.md")
POLITICA_BACKUP = "backup_policy.json"
PROTEGIDOS = ("state", ".git")
MINIMO_DO_GIT = ("objects", "refs", "refs/heads", "refs/tags")  # o que o `git init` cria e o git exige (com HEAD)


# ------------------------------------------------------------------ política (KIT-F2)
def _pedacos(rel) -> list[str]:
    return [p for p in str(rel).replace("\\", "/").split("/") if p not in ("", ".")]


def _nome(parte: str) -> str:
    """O nome como o Windows e o DrvFs o abrem: sem caixa, sem fluxo (`:`) e sem ponto ou espaço no fim."""
    return parte.split(":", 1)[0].rstrip(". ").casefold()


def protegido(rel) -> bool:
    """A primeira parte de `rel` (com / ou \\) abre `state` ou `.git` da raiz."""
    partes = _pedacos(rel)
    return bool(partes) and _nome(partes[0]) in PROTEGIDOS


def motivo_da_politica(rel, raiz: Path) -> str | None:
    """Por que `rel` não pode ir na lista `incluir` da política de backup; None se pode."""
    if not isinstance(rel, str) or not rel.strip():
        return "caminho vazio"
    p = PurePath(rel)
    if p.is_absolute() or p.drive or p.root or ":" in rel or "\0" in rel:
        return "caminho absoluto, com unidade ou com ':'"
    partes = _pedacos(rel)
    if not partes:
        return "a própria raiz"
    if any(not x.rstrip(". ") for x in partes):
        return "caminho com '..'"
    if protegido(rel):
        return "caminho em state/ ou .git (sem caixa, sem ponto ou espaço no fim)"
    raiz = Path(raiz)
    alvo = raiz / rel
    if preparo.e_ligacao(alvo):  # o backup não segue a ligação do fim (fica em ligacoes_nao_seguidas): nada entra
        return None
    if not dentro_da_copia(alvo, raiz) or dentro_da_copia(raiz, alvo):
        return "resolvido, sai da raiz ou é a própria raiz (ligação no caminho)"
    if any(dentro_da_copia(alvo, raiz / nome) for nome in PROTEGIDOS):
        return "resolvido, cai em state/ ou .git (ligação, caixa ou nome curto)"
    return None


def registros_incluidos(root: Path) -> list[str]:
    """Caminhos da raiz, além do kit e do banco, que entram na cópia: a lista `incluir` de
    registry/backup_policy.json ou REGISTROS_PADRAO. Caminho que `motivo_da_politica` recusa — vazio, absoluto, com
    `..` ou `:`, a raiz, em `state/` ou `.git`, também com outra caixa, ponto ou espaço no fim, ou resolvido — recusa
    o backup antes de copiar (ValidationError)."""
    arq = Path(root) / "registry" / POLITICA_BACKUP
    if not arq.is_file():
        return list(REGISTROS_PADRAO)
    try:
        incluir = json.loads(arq.read_text(encoding="utf-8")).get("incluir")
    except (OSError, ValueError, AttributeError) as exc:
        raise ValidationError(f"política de backup ilegível (registry/{POLITICA_BACKUP})",
                              erro=type(exc).__name__) from exc
    if not isinstance(incluir, list) or not all(isinstance(x, str) and x.strip() for x in incluir):
        raise ValidationError(f"política de backup inválida: `incluir` precisa ser lista de caminhos relativos "
                              f"(registry/{POLITICA_BACKUP})")
    for rel in incluir:
        motivo = motivo_da_politica(rel, Path(root))
        if motivo:
            raise ValidationError("política de backup inválida: só caminhos relativos dentro da raiz, fora de "
                                  f"state/ e .git (registry/{POLITICA_BACKUP})", caminho=rel, motivo=motivo)
    return incluir


# ------------------------------------------------------------------ destino (KIT-F7)
def raiz_que_contem(destino, raiz=None, registro=None) -> str | None:
    """A raiz da fundação que contém `destino` (ou é ele): `raiz` e a do registro protegido `registro`
    (<raiz>/state/retiradas.jsonl), pelo caminho resolvido e pelo objeto do disco; None se nenhuma. A pasta acima do
    state/ do registro só vale com fundacao/ ou projects/ (KIT-F7, revisão 1: o cofre <c>/state/ não é fundação)."""
    pasta = Path(registro).parent if registro is not None else None
    do_registro = pasta.parent if pasta is not None and _nome(pasta.name) == "state" else None
    if do_registro is not None and not cara_de_fundacao(do_registro):
        do_registro = None
    for candidata in (raiz, do_registro):
        if candidata is not None and dentro_da_copia(destino, candidata):
            return str(candidata)
    return None


def cara_de_fundacao(pasta) -> bool:
    """A pasta tem fundacao/ ou projects/: conta como raiz de fundação sem o banco legível (o registro guardado ao lado
    e, no desastre, a --raiz da CLI; KIT-F7, correções das revisões 1 e 2)."""
    return any((Path(pasta) / nome).is_dir() for nome in ("fundacao", "projects"))


# ------------------------------------------------------------------ pastas vazias do .git (KIT-F4)
def _acima(caminhos) -> set[str]:
    """As pastas acima de cada caminho (relativo, com /)."""
    pastas: set[str] = set()
    for caminho in caminhos:
        pasta = posixpath.dirname(caminho)
        while pasta and pasta not in pastas:
            pastas.add(pasta)
            pasta = posixpath.dirname(pasta)
    return pastas


def chave(partes) -> str:
    """O caminho (partes, ou texto com /) como o Windows e o DrvFs o abrem: cada parte por `_nome`."""
    return "/".join(_nome(p) for p in (partes.split("/") if isinstance(partes, str) else partes))


_RESERVADOS_NT = frozenset({"con", "prn", "aux", "nul", "conin$", "conout$", *(f"{d}{n}" for d in ("com", "lpt")
                                                                                     for n in "123456789")})


def parte_valida(parte: str) -> bool:
    """Parte de caminho que a restauração recria neste sistema: não vazia, sem `.`, `..` nem NUL; no Windows, também sem
    `<>:"\\|?*`, controle, nome de dispositivo (CON, NUL...) nem espaço ou ponto no fim — o Win32 os tira: ' ' e '. '
    abrem a pasta de cima, e 'x ' no meio do caminho cai no FileNotFoundError do `makedirs` (KIT-F4, revisão 2 das
    correções). No Linux, `:` e `\\` são nome válido, como em ancora_copia: a cópia feita lá verifica, e a restauração
    no Windows a recusa sem cair no `makedirs`."""
    if parte in ("", ".", "..") or "\0" in parte:
        return False
    return os.name != "nt" or not (any(c in '<>:"\\|?*' or c < " " for c in parte) or parte != parte.rstrip(" .")
                                   or parte.split(".", 1)[0].rstrip(" ").casefold() in _RESERVADOS_NT)


def _sob_arquivo(rel: str, arquivos: set) -> bool:
    """`rel` (ou uma pasta acima dele) é, sem caixa e sem ponto ou espaço no fim, um arquivo da cópia (`arquivos`, já
    por `chave`): a restauração não cria pasta ali (o `makedirs` cairia no arquivo)."""
    partes = rel.split("/")
    return any(chave(partes[:i]) in arquivos for i in range(1, len(partes) + 1))


def pastas_vazias(pastas, arquivos, levados) -> list[str]:
    """As pastas que a restauração recria: as vistas dentro de um .git levado sem arquivo copiado embaixo e, em cada .git
    levado com HEAD, as de MINIMO_DO_GIT que nenhum arquivo traz — sem o que a verificação recusaria (`_vazias`): o
    que é arquivo copiado ou fica sob um (o refs/heads do reftable) e o nome que este sistema não recria."""
    copiados, levados = set(arquivos), [g for g in levados if _levado(g)]
    arquivos_n = {chave(a) for a in copiados}
    com_head = {chave(posixpath.dirname(a)) for a in copiados if _nome(posixpath.basename(a)) == "head"}
    minimo = {f"{g}/{m}" for g in levados if chave(g) in com_head for m in MINIMO_DO_GIT}
    vistas = {p for p in pastas if any(p == g or p.startswith(g + "/") for g in levados)}
    return sorted(p for p in (vistas | minimo) - _acima(copiados)
                  if all(parte_valida(x) for x in p.split("/")) and not _sob_arquivo(p, arquivos_n))


def _levado(g) -> bool:
    """Um .git que a cópia leva: projects/<projeto>/.../.git, sem caixa e sem ponto ou espaço no fim (KIT-F4, revisão
    2: `state`, `State` ou o `.git` da raiz no manifesto não recriam nada)."""
    partes = g.split("/") if isinstance(g, str) else []
    return (len(partes) >= 3 and all(parte_valida(p) for p in partes) and _nome(partes[0]) == "projects"
            and _nome(partes[-1]) == ".git")


def _git(manifest: dict) -> tuple[dict, list[str]]:
    """A seção `git` do manifesto e os .git levados (só os de projects/); fora do formato (cópia forjada ou de kit
    anterior), vazias."""
    git = manifest.get("git") if isinstance(manifest.get("git"), dict) else {}
    levados = git.get("levados") if isinstance(git.get("levados"), list) else []
    return git, [g for g in levados if _levado(g)]


def _arquivos(manifest: dict) -> list[str]:
    return [p for p in (f.get("path") for f in manifest.get("files") or [] if isinstance(f, dict)) if isinstance(p, str)]


def _vazias(manifest: dict) -> tuple[list[str], list[dict]]:
    """(as pastas vazias aceitas, as recusadas com o motivo): cada uma com partes que este sistema recria
    (`parte_valida`), dentro de um .git levado de projects/ e sem arquivo da cópia no caminho, também sem caixa."""
    git, levados = _git(manifest)
    arquivos_n = {chave(a) for a in _arquivos(manifest)}
    vazias = git.get("pastas_vazias")
    aceitas, recusadas = [], [] if vazias is None or isinstance(vazias, list) else [
        {"caminho": "git.pastas_vazias", "motivo": "não é uma lista"}]
    for rel in vazias if isinstance(vazias, list) else []:
        if not isinstance(rel, str) or not all(parte_valida(p) for p in rel.split("/")):
            recusadas.append({"caminho": str(rel)[:200], "motivo": "caminho inválido"})
        elif not any(rel == g or rel.startswith(g + "/") for g in levados):
            recusadas.append({"caminho": rel[:200], "motivo": "fora de um .git levado"})
        elif _sob_arquivo(rel, arquivos_n):
            recusadas.append({"caminho": rel[:200], "motivo": "é um arquivo da cópia (ou fica dentro de um)"})
        else:
            aceitas.append(rel)
    return aceitas, recusadas


def git_incompleto(manifest: dict) -> list[dict]:
    """O que deixaria um repositório da cópia inutilizável na restauração: .git levado com HEAD que voltaria sem objects/
    ou refs/ (cópia anterior a esta correção ou manifesto alterado) e pasta vazia anotada que a restauração recusa.
    objects/ ou refs/ que a cópia traz como arquivo voltam como estavam na origem: não é falta (o git também não abriria
    a origem)."""
    aceitas, recusadas = _vazias(manifest)
    arquivos = _arquivos(manifest)
    arquivos_n = {chave(a) for a in arquivos}
    presentes = {chave(p) for p in _acima(arquivos) | set(aceitas) | _acima(aceitas)}
    for g in _git(manifest)[1]:
        if chave(f"{g}/HEAD") in arquivos_n:
            falta = [m for m in ("objects", "refs")
                     if chave(f"{g}/{m}") not in presentes and not _sob_arquivo(f"{g}/{m}", arquivos_n)]
            if falta:
                recusadas.append({"caminho": g, "falta": falta})
    return recusadas


def recriar_pastas_vazias(raiz: Path, manifest: dict) -> str | None:
    """Recria em `raiz` (a raiz preparada da restauração, já conferida e sem ligação) as pastas vazias do .git que o
    manifesto anota e que `git_incompleto` aceita: nenhuma cai em arquivo da cópia nem sai de projects/<p>/.../.git.
    Devolve None, ou a pasta que este sistema não recriou, com o erro: a restauração não libera (antes, o OSError
    escapava depois de 'backup íntegro' — nome longo demais para o destino, como 200 letras acentuadas do NTFS no ext4;
    KIT-F4, revisão 2 das correções)."""
    for rel in _vazias(manifest)[0]:
        try:
            os.makedirs(Path(raiz, *rel.split("/")), exist_ok=True)
        except OSError as exc:
            return f"{rel[:200]} ({type(exc).__name__}: {exc.strerror or exc})"
    return None
