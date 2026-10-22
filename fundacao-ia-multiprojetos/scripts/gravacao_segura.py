#!/usr/bin/env python3
"""Gravação na raiz da fundação sem seguir ligação nem vínculo físico, para os scripts da skill que escrevem nela
(`instrucoes_raiz.py` e `atualizar_fundacao.py`; revisão de segurança da 1.7.7, R177-ATU-03).

A raiz é gravável por quem opera a fundação: um nome previsível ali (`.AGENTS.md.tmp`, `registry/atualizacoes.jsonl`,
`registry/kit_backup/`, `evidence/atualizacoes/`) pode já ser uma ligação — link simbólico ou junção — ou um vínculo
físico (hard link, que no Windows qualquer conta cria sem privilégio) para um arquivo de fora; gravar por esse nome com
`open` comum alteraria o arquivo de fora. É o padrão mínimo do `fundacao/core/publicacao.py` do kit, reproduzido aqui
sem importar o kit (os scripts da skill não o importam):
- `publicar`: temporário de nome imprevisível na mesma pasta, criado com exclusividade (`O_CREAT | O_EXCL`;
  `O_NOFOLLOW` onde existe), conferido como arquivo regular e o mesmo que foi aberto, e posto no lugar com
  `os.replace`, que troca o nome sem gravar através dele. Destino que é ligação ou pasta: recusado;
- `criar`: arquivo novo com exclusividade (um registro nunca sobrescreve outro nem grava por um nome já existente);
- `anexar`: acrescenta ao fim sem seguir ligação nem vínculo físico (lstat antes, fstat, lstat depois);
- `com_ligacao`, `pasta_sem_ligacao`, `pasta_nova` e `desviados`: conferem, sem seguir, cada componente abaixo da raiz.
Recusa = `GravacaoRecusada` (um OSError), sem gravar nada no destino. Limite (o mesmo do kit): no Windows a biblioteca
padrão não abre arquivo relativo a um handle de pasta; trocar uma pasta ACIMA do destino por junção entre a
conferência e a gravação (corrida) ainda redireciona. Rode o atualizador sem outra sessão gravando na raiz.
"""

from __future__ import annotations

import errno
import os
import secrets
import stat
from pathlib import Path

SUBSTITUTO_DE_NOME = 0x20000000  # Windows: junção, link simbólico e afins (bit 29 da etiqueta de reparse)
_SEM_SEGUIR = getattr(os, "O_NOFOLLOW", 0)  # não existe no Windows: lá valem a exclusividade e as conferências
_BINARIO = getattr(os, "O_BINARY", 0)


class GravacaoRecusada(OSError):
    """O destino é (ou virou) ligação, pasta ou vínculo físico: nada foi gravado nele."""


def e_ligacao(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & SUBSTITUTO_DE_NOME)


def com_ligacao(raiz, rel: str) -> bool:
    """Algum componente de `rel`, abaixo da raiz, é ligação simbólica ou junção? Conferido sem seguir (como o
    guarda_caminho.py e o backup do kit; revisão de segurança da 1.7.0, VCT170-04)."""
    atual = Path(raiz)
    for parte in rel.split("/"):
        atual = atual / parte
        try:
            st = os.lstat(atual)
        except OSError:
            return False  # o resto do caminho ainda não existe
        if e_ligacao(st):
            return True
    return False


def desviados(raiz, rels) -> list:
    """Dos caminhos `rels` (relativos à raiz), os que passam por ligação ou são arquivo com vínculo físico."""
    res = []
    for rel in rels:
        try:
            st = os.lstat(Path(raiz) / rel)
        except OSError:
            st = None
        if com_ligacao(raiz, rel) or (st is not None and stat.S_ISREG(st.st_mode) and st.st_nlink != 1):
            res.append(rel)
    return res


def pasta_sem_ligacao(raiz, rel: str) -> Path:
    """Cria (se faltar) a pasta `rel` abaixo da raiz, recusando ligação em qualquer componente, antes e depois."""
    if com_ligacao(raiz, rel):
        raise GravacaoRecusada(rel + " passa por ligação (link simbólico ou junção): nada foi gravado")
    pasta = Path(raiz) / rel
    pasta.mkdir(parents=True, exist_ok=True)
    if com_ligacao(raiz, rel) or not pasta.is_dir():
        raise GravacaoRecusada(rel + " virou ligação ou não é pasta: nada foi gravado")
    return pasta


def pasta_nova(raiz, rel: str) -> Path:
    """Cria a pasta `rel`, que ainda não pode existir (nem como ligação), abaixo de pastas sem ligação no caminho."""
    mae, _, nome = rel.rpartition("/")
    pasta = (pasta_sem_ligacao(raiz, mae) if mae else Path(raiz)) / nome
    pasta.mkdir()
    if com_ligacao(raiz, rel):
        raise GravacaoRecusada(rel + " virou ligação: nada foi gravado")
    return pasta


def _mesmo(a: os.stat_result, b: os.stat_result) -> bool:
    return (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


def _recusar(destino: Path, motivo: str):
    raise GravacaoRecusada(destino.name + ": " + motivo + "; nada foi gravado nele")


def _gravar_tudo(fd: int, dados: bytes) -> None:
    vista = memoryview(dados)
    while vista:
        vista = vista[os.write(fd, vista):]
    os.fsync(fd)


def conferir_destino(destino) -> None:
    """Recusa destino que exista como ligação ou pasta (ausente passa): `publicar` troca o nome, não grava por ele."""
    try:
        st = os.lstat(destino)
    except FileNotFoundError:
        return
    if e_ligacao(st) or not stat.S_ISREG(st.st_mode):
        _recusar(Path(destino), "é ligação (link simbólico ou junção) ou pasta")


def criar(destino, dados: bytes) -> None:
    """Grava `dados` num arquivo NOVO: nome já existente (também ligação ou vínculo físico) falha sem gravar nada."""
    destino = Path(destino)
    fd = os.open(destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _SEM_SEGUIR | _BINARIO, 0o666)
    try:
        aberto = os.fstat(fd)
        if not stat.S_ISREG(aberto.st_mode) or aberto.st_nlink != 1 or not _mesmo(aberto, os.lstat(destino)):
            _recusar(destino, "trocado ao ser criado")
        _gravar_tudo(fd, dados)
    finally:
        os.close(fd)


def publicar(destino, dados: bytes) -> None:
    """Grava `dados` em `destino` por um temporário imprevisível na mesma pasta e `os.replace` (ver o módulo)."""
    destino = Path(destino)
    conferir_destino(destino)
    tmp = destino.with_name("." + destino.name + "." + secrets.token_hex(8) + ".tmp")
    criar(tmp, dados)
    try:
        visto = os.lstat(tmp)
        if e_ligacao(visto) or visto.st_nlink != 1:  # trocado entre fechar e pôr no lugar
            _recusar(destino, "temporário trocado antes de ir para o lugar")
        conferir_destino(destino)
        os.replace(tmp, destino)
    except BaseException:
        try:
            os.unlink(tmp)  # tira só o nome: se alguém o trocou por ligação, o alvo dela não muda
        except OSError:
            pass
        raise


def _exigir_simples(destino: Path, st: os.stat_result) -> None:
    if e_ligacao(st) or not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        _recusar(destino, "é ligação (link simbólico ou junção), pasta ou arquivo com vínculo físico")


def anexar(destino, dados: bytes) -> None:
    """Acrescenta `dados` ao fim de `destino` sem seguir ligação nem vínculo físico (ver o módulo)."""
    destino = Path(destino)
    for _ in range(2):  # criado por outro entre a conferência e a criação: confere de novo, agora como existente
        try:
            antes = os.lstat(destino)
            _exigir_simples(destino, antes)
        except FileNotFoundError:
            antes = None
        criar_ = os.O_CREAT | os.O_EXCL if antes is None else 0
        try:
            fd = os.open(destino, os.O_WRONLY | os.O_APPEND | criar_ | _SEM_SEGUIR | _BINARIO, 0o666)
            break
        except FileExistsError:
            continue
        except OSError as exc:
            if exc.errno == errno.ELOOP:  # virou link simbólico depois da conferência (O_NOFOLLOW)
                _recusar(destino, "trocado por ligação")
            raise
    else:
        _recusar(destino, "trocado durante a gravação")
    try:
        aberto, depois = os.fstat(fd), os.lstat(destino)
        if (not stat.S_ISREG(aberto.st_mode) or aberto.st_nlink != 1 or e_ligacao(depois) or not _mesmo(aberto, depois)
                or (antes is not None and not _mesmo(aberto, antes))):
            _recusar(destino, "trocado por ligação ou vínculo físico durante a gravação")
        _gravar_tudo(fd, dados)
    finally:
        os.close(fd)
