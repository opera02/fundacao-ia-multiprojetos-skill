"""Preparo privado de cópia e restauração: o que é conferido é o que é copiado (auditoria Codex Security da 1.7.6, #12).

Antes, o backup e a restauração conferiam caminhos (ligação, hash) e depois reabriam os mesmos NOMES para copiar e
liberar: quem trocasse no intervalo um arquivo, a pasta da cópia, o banco ou o destino por ligação redirecionava a
leitura ou a escrita. Agora a operação fica presa aos objetos do sistema de arquivos:
- `percorrer` lista sem atravessar ligação e anota o `lstat` de cada item; pasta trocada durante a listagem recusa;
- `copiar` abre sem seguir ligação onde o sistema permite (O_NOFOLLOW), confere que o objeto aberto é o mesmo da
  listagem (dispositivo e inode) ANTES de ler qualquer byte, grava num arquivo novo e devolve o SHA-256 do que gravou;
  `resumo` faz a mesma abertura só para o hash (a verificação no lugar: revisão de segurança da 1.7.7, R177-KIT-03);
- `ligacao_no_caminho` aponta ligação no caminho ou num ancestral (a fonte e o destino recusam);
- `criar_preparo` cria a pasta de preparo ao lado do destino, com exclusividade (nunca reaproveita pasta nem
  ligação); `promover` a põe no lugar do destino por renomeação atômica, que não grava através de ligação.
Limites: na mesma conta do sistema, quem troca e destroca uma pasta exatamente durante a listagem dela, ou um ancestral
do destino durante a escrita, ainda redireciona a operação — no Windows o Python não abre sem seguir ligação nem
trabalha por pasta aberta; a reconferência antes da promoção recusa o resultado, mas o que já foi escrito do outro lado
da ligação fica lá. No Windows, a pasta de preparo — e o destino, depois da promoção — herda as permissões da pasta de
cima do destino (no Linux, 0o700): é essa pasta que só o titular deve alterar. Destino vazio criado antes é trocado
pela pasta preparada, e as permissões próprias dele não ficam: quem chama avisa (revisão de segurança da 1.7.7,
R177-KIT-05).
"""

from __future__ import annotations

import errno
import hashlib
import os
import secrets
import stat
from pathlib import Path

from .canon import sha256_file
from .contracts import ValidationError

# Windows: etiqueta de ponto de nova análise "substituta de nome" (bit 29) — junção, link simbólico e afins, que
# redirecionam para outro caminho; arquivo de nuvem (OneDrive) e deduplicação não a têm.
_SUBSTITUTA_DE_NOME = 0x20000000
# Sem seguir ligação (onde existe) e sem esperar por pipe trocado no lugar do arquivo.
_LEITURA = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
_BLOCO = 1 << 20
AVISO_DESTINO_EXISTENTE = ("o destino já existia (pasta vazia) e foi trocado pela pasta preparada: as permissões que ele "
                           "tinha não ficam — no Windows, a pasta nova herda as da pasta de cima. Para restringir o "
                           "acesso, proteja a pasta de cima do destino (que só o titular altera), não o destino.")


def _e_ligacao_st(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & _SUBSTITUTA_DE_NOME)


def _identidade(st: os.stat_result) -> tuple[int, int]:
    return st.st_dev, st.st_ino


def e_ligacao(caminho: Path) -> bool:
    """Link simbólico ou junção (e afins do Windows), conferido sem seguir a ligação."""
    try:
        return _e_ligacao_st(os.lstat(caminho))
    except OSError:
        return False


def ligacao_no_caminho(caminho: Path) -> str | None:
    """O próprio caminho ou o primeiro ancestral que é ligação; None se não houver. A raiz do volume (unidade,
    compartilhamento de rede, `/`) não conta. Caminho com ligação no meio leva a operação para outro lugar: quem chama
    recusa e pede o caminho real."""
    atual = Path(os.path.abspath(caminho))
    while atual.parent != atual:
        if e_ligacao(atual):
            return str(atual)
        atual = atual.parent
    return None


def percorrer(base: Path, ignorar=frozenset()) -> list[tuple[Path, bool, os.stat_result]]:
    """Itens sob `base` (pastas também), ordenados, sem atravessar ligação: (caminho, é ligação, `lstat` da listagem).
    Pasta com nome em `ignorar` fica fora. A ligação vem marcada e o que há do outro lado não é listado nem lido; cada
    pasta é conferida depois de listada — trocada por ligação ou por outra pasta no meio, ValidationError. Item ou
    pasta que some durante a listagem fica fora, como no `os.walk` (que sozinho entraria na junção do Windows)."""
    itens = []
    pilha = [(Path(base), _identidade(os.lstat(base)))]
    while pilha:
        pasta, esperada = pilha.pop()
        try:
            with os.scandir(pasta) as entradas:
                nomes = sorted(e.name for e in entradas if e.name not in ignorar)
            st = os.lstat(pasta)
        except (FileNotFoundError, NotADirectoryError):
            continue  # sumiu no meio (escritor ativo): nada dela foi lido
        if _e_ligacao_st(st) or _identidade(st) != esperada:
            raise ValidationError("pasta trocada durante a leitura (ligação ou outra pasta no lugar): repita",
                                  pasta=str(pasta))
        for nome in nomes:
            caminho = pasta / nome
            try:
                st = os.lstat(caminho)
            except FileNotFoundError:
                continue
            ligacao = _e_ligacao_st(st)
            itens.append((caminho, ligacao, st))
            if stat.S_ISDIR(st.st_mode) and not ligacao:
                pilha.append((caminho, _identidade(st)))
    return sorted(itens, key=lambda item: item[0])


def _abrir(origem: Path, listado: os.stat_result) -> tuple[int, os.stat_result]:
    """Descritor do arquivo comum `origem`, que precisa ser o mesmo objeto de `listado`; senão, nada é lido."""
    if _e_ligacao_st(listado) or not stat.S_ISREG(listado.st_mode):
        raise ValidationError("não é arquivo comum (ligação, pasta ou dispositivo): recusado", caminho=str(origem))
    try:
        fd = os.open(origem, _LEITURA)
    except OSError as exc:
        if exc.errno != errno.ELOOP:  # arquivo sumido ou sem permissão: erro de arquivo, como antes
            raise
        raise ValidationError("arquivo trocado por ligação durante a leitura: repita", caminho=str(origem)) from None
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or _identidade(st) != _identidade(listado):
        os.close(fd)
        raise ValidationError("arquivo trocado durante a leitura (ligação ou outro arquivo no lugar): repita",
                              caminho=str(origem))
    return fd, st


def ler(caminho: Path) -> bytes:
    """Bytes de um arquivo comum (ex.: o manifesto), lido sem seguir ligação, uma vez."""
    fd, _ = _abrir(Path(caminho), os.lstat(caminho))
    try:
        partes = []
        while bloco := os.read(fd, _BLOCO):
            partes.append(bloco)
        return b"".join(partes)
    finally:
        os.close(fd)


def resumo(caminho: Path, listado: os.stat_result) -> str:
    """SHA-256 do arquivo comum `caminho` — o objeto de `listado` —, aberto sem seguir ligação. A verificação no lugar
    só calcula o hash do que listou assim, nunca pelo nome (revisão de segurança da 1.7.7, R177-KIT-03)."""
    fd, _ = _abrir(Path(caminho), listado)
    try:
        calculo = hashlib.sha256()
        while bloco := os.read(fd, _BLOCO):
            calculo.update(bloco)
        return calculo.hexdigest()
    finally:
        os.close(fd)


def copiar(origem: Path, destino: Path, listado: os.stat_result) -> tuple[str, int]:
    """Copia `origem` (o objeto de `listado`) para `destino`, arquivo NOVO (nunca sobrescreve nem segue ligação no
    destino), e devolve o SHA-256 e o tamanho dos bytes gravados; a data de modificação acompanha. Falha no meio não
    deixa arquivo pela metade."""
    fd, st = _abrir(Path(origem), listado)
    try:
        resumo, tamanho = hashlib.sha256(), 0
        with open(destino, "xb") as saida:  # já existe (até ligação plantada): FileExistsError, nada sobrescrito
            try:
                while bloco := os.read(fd, _BLOCO):
                    resumo.update(bloco)
                    saida.write(bloco)
                    tamanho += len(bloco)
            except BaseException:
                saida.close()
                Path(destino).unlink(missing_ok=True)
                raise
        os.utime(destino, ns=(st.st_atime_ns, st.st_mtime_ns))
    finally:
        os.close(fd)
    return resumo.hexdigest(), tamanho


def criar_pasta(pasta: Path, criadas: set) -> None:
    """Cria `pasta` e as que faltam acima dela, uma a uma e com exclusividade, até chegar a uma de `criadas` (as que
    esta operação criou): pasta que já existe sem ter sido criada aqui (ligação plantada) faz o `mkdir` falhar."""
    if pasta in criadas or pasta.parent == pasta:
        return
    criar_pasta(pasta.parent, criadas)
    os.mkdir(pasta)
    criadas.add(pasta)


def espelhar(origem: Path, destino: Path, pular=()) -> dict:
    """Copia a árvore `origem` para `destino` (pasta nova) pelo `copiar`, recriando as pastas com exclusividade. Devolve
    as ligações (e o que não é arquivo comum) encontradas — não copiadas — e os arquivos pulados pelo nome (`pular`)."""
    os.mkdir(destino)
    achados = {"ligacoes": [], "pulados": []}
    for caminho, ligacao, st in percorrer(origem):
        rel = caminho.relative_to(origem)
        if stat.S_ISDIR(st.st_mode) and not ligacao:
            os.mkdir(destino / rel)  # já existe sem ter sido criada aqui (ligação plantada): FileExistsError
        elif ligacao or not stat.S_ISREG(st.st_mode):
            achados["ligacoes"].append(rel.as_posix())
        elif caminho.name in pular:
            achados["pulados"].append(rel.as_posix())
        else:
            copiar(caminho, destino / rel, st)
    return achados


def trazer_copia(origem: Path, espelho: Path, pular=()) -> dict:
    """Traz uma cópia de backup para o preparo: manifest.json, files/ e state/state.sqlite, cada arquivo preso ao objeto
    listado e sem seguir ligação; arquivo com nome em `pular` (metadados do sistema) fica fora. Ligação encontrada não
    é copiada: vem nos achados ("files/" e "state/" quando é a própria pasta). Depois disso, nada é lido da origem."""
    os.mkdir(espelho)
    os.mkdir(espelho / "state")
    achados = {"ligacoes": [f"{rel}/" for rel in ("files", "state") if e_ligacao(origem / rel)], "pulados": []}
    for rel in ["manifest.json"] + ([] if "state/" in achados["ligacoes"] else ["state/state.sqlite"]):
        if os.path.lexists(origem / rel):  # ausente: a verificação aponta
            copiar(origem / rel, espelho / rel, os.lstat(origem / rel))
    if "files/" in achados["ligacoes"] or not (origem / "files").is_dir():
        os.mkdir(espelho / "files")
    else:
        espelhado = espelhar(origem / "files", espelho / "files", pular)
        achados["ligacoes"] += espelhado["ligacoes"]
        achados["pulados"] = espelhado["pulados"]
    return achados


def reconferir(raiz: Path, esperado: dict) -> list[str]:
    """O que, na raiz preparada, não confere mais com `esperado` (caminho relativo com / -> SHA-256; None = precisa
    existir, sem conferir o conteúdo): arquivo mudado, ausente, a mais ou ligação. Chamada logo antes da promoção.
    Pasta não conta (a cópia não lista pastas, e pasta vazia não traz conteúdo)."""
    vistos, ruins = set(), []
    for caminho, ligacao, st in percorrer(raiz):
        if stat.S_ISDIR(st.st_mode) and not ligacao:
            continue
        rel = caminho.relative_to(raiz).as_posix()
        vistos.add(rel)
        if ligacao or rel not in esperado or (esperado[rel] is not None and sha256_file(caminho) != esperado[rel]):
            ruins.append(rel)
    return sorted(ruins + [rel for rel in esperado if rel not in vistos])


def criar_preparo(alvo: Path) -> Path:
    """Pasta de preparo ao lado de `alvo` (mesmo volume, para a promoção ser uma renomeação), criada agora, com
    exclusividade e, onde o sistema permite, só para esta conta (0o700)."""
    alvo = Path(os.path.abspath(alvo))
    alvo.parent.mkdir(parents=True, exist_ok=True)
    pasta = alvo.parent / f".{alvo.name}.preparo-{secrets.token_hex(4)}"
    os.mkdir(pasta, 0o700)
    ligada = ligacao_no_caminho(pasta)
    if ligada:  # um ancestral virou ligação depois da conferência de quem chama
        os.rmdir(pasta)
        raise ValidationError("ligação no caminho do destino: informe o caminho real", caminho=ligada)
    return pasta


def promover(pasta: Path, alvo: Path) -> bool:
    """Põe a `pasta` preparada no lugar de `alvo` por renomeação atômica no mesmo volume e confere que o destino é o
    objeto preparado. Destino vazio (pasta real) sai antes; destino que é ligação, que não está vazio ou que reaparece
    no intervalo faz a renomeação falhar — nada é gravado através dele. Devolve se o destino já existia: as permissões
    próprias dele não ficam, e quem chama avisa com AVISO_DESTINO_EXISTENTE (R177-KIT-05)."""
    alvo = Path(os.path.abspath(alvo))
    esperada = _identidade(os.lstat(pasta))
    existia = os.path.lexists(alvo)
    if existia:
        if e_ligacao(alvo) or not alvo.is_dir() or any(alvo.iterdir()):
            raise FileExistsError("destino ocupado ou trocado por ligação: nada foi gravado nele")
        os.rmdir(alvo)
    os.rename(pasta, alvo)  # Windows: falha se o destino existir; Linux: se não for pasta vazia
    st = os.lstat(alvo)
    if _e_ligacao_st(st) or _identidade(st) != esperada:
        raise ValidationError("destino trocado durante a promoção: confira-o antes de usar", destino=str(alvo))
    return existia
