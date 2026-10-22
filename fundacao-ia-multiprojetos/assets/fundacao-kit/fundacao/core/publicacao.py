"""Publicação segura de arquivos em pastas que outros escrevem (auditoria Codex Security da 1.7.6, #11).

A pasta de um projeto é escrita por quem opera o projeto; `registry/components`, por quem tem a conta do SO.
Um nome previsível ali pode já ser uma ligação — link simbólico, junção ou outro ponto de nova análise do
Windows que redirecione o nome — ou um vínculo físico (hard link, que no Windows qualquer conta cria sem
privilégio) para um arquivo de fora. Gravar por esse nome com `open` comum alteraria o arquivo de fora com a
autoridade da fundação. Um só caminho para gravar ali:

- `publicar(destino, dados)`: temporário de nome imprevisível na MESMA pasta, criado com exclusividade
  (`O_CREAT | O_EXCL`; `O_NOFOLLOW` onde existe), conferido como arquivo regular e o mesmo que foi aberto
  (fstat e lstat), gravado com `fsync` e posto no lugar com `os.replace`, que troca o nome sem gravar através
  dele. Destino que é ligação ou pasta: recusado (`PathEscape`), sem mudar nada.
- `anexar(destino, dados)`: acrescenta ao fim de um registro (ex.: `decisoes/registro.jsonl`). Recusa ligação,
  pasta e vínculo físico, e só grava se o arquivo aberto for o mesmo visto antes e depois de abrir (lstat
  antes, fstat, lstat depois). `conferir_para_anexar` faz a mesma recusa antes de outros efeitos.

Limites: a pasta de destino é a que quem chama conferiu (`paths.contained`). No Windows, a biblioteca padrão
não abre arquivo relativo a um handle de pasta: trocar uma pasta ACIMA do destino por junção entre a
conferência e a gravação (corrida) ainda pode levar o arquivo publicado, com o nome dele, para outra pasta.
Na mesma conta do SO, quem escreve na pasta também escreve no arquivo de fora por conta própria: o ganho é não
emprestar a gravação da fundação a quem só alcança a pasta do projeto (hooks e permissões do host).
"""

from __future__ import annotations

import errno
import os
import secrets
import stat
from pathlib import Path

from .contracts import PathEscape

# Windows: ponto de nova análise "substituto de nome" (bit 29 da etiqueta) — junção, link simbólico e afins, que
# redirecionam para outro caminho; arquivo de nuvem (OneDrive) e deduplicação não o têm (critério de backup.py).
_SUBSTITUTO_DE_NOME = 0x20000000
_SEM_SEGUIR = getattr(os, "O_NOFOLLOW", 0)  # não existe no Windows: lá valem a exclusividade e as conferências
_BINARIO = getattr(os, "O_BINARY", 0)


def _ligacao(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & _SUBSTITUTO_DE_NOME)


def _mesmo(a: os.stat_result, b: os.stat_result) -> bool:
    return (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


def _recusar(destino: Path, motivo: str):
    raise PathEscape(f"{motivo}: recusado; nada foi gravado", arquivo=destino.name)


def _gravar_tudo(fd: int, dados: bytes) -> None:
    vista = memoryview(dados)
    while vista:
        vista = vista[os.write(fd, vista):]
    os.fsync(fd)


def _conferir_destino(destino: Path) -> None:
    try:
        st = os.lstat(destino)
    except FileNotFoundError:
        return
    if _ligacao(st) or not stat.S_ISREG(st.st_mode):
        _recusar(destino, "destino é ligação (link simbólico ou junção) ou pasta")


def publicar(destino, dados: bytes) -> None:
    """Grava `dados` em `destino` por um temporário imprevisível na mesma pasta e `os.replace` (ver o módulo)."""
    destino = Path(destino)
    _conferir_destino(destino)
    tmp = destino.with_name(f"{destino.name}.{secrets.token_hex(8)}.tmp")  # nome curto: caminho longo no Windows
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _SEM_SEGUIR | _BINARIO, 0o666)
    try:
        try:
            aberto = os.fstat(fd)
            if not stat.S_ISREG(aberto.st_mode) or not _mesmo(aberto, os.lstat(tmp)):
                _recusar(destino, "temporário trocado ao ser criado")
            _gravar_tudo(fd, dados)
        finally:
            os.close(fd)
        visto = os.lstat(tmp)
        if _ligacao(visto) or not _mesmo(aberto, visto):  # trocado entre fechar e pôr no lugar
            _recusar(destino, "temporário trocado antes de ir para o lugar")
        _conferir_destino(destino)
        os.replace(tmp, destino)
    except BaseException:
        try:
            os.unlink(tmp)  # tira só o nome: se alguém o trocou por ligação, o alvo dela não muda
        except OSError:
            pass
        raise


def _exigir_simples(destino: Path, st: os.stat_result) -> None:
    if _ligacao(st) or not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        _recusar(destino, "registro é ligação (link simbólico ou junção), pasta ou arquivo com vínculo físico")


def conferir_para_anexar(destino) -> Path:
    """Recusa, sem gravar nada, registro que `anexar` recusaria (ausente passa: `anexar` o cria); devolve o caminho."""
    destino = Path(destino)
    try:
        _exigir_simples(destino, os.lstat(destino))
    except FileNotFoundError:
        pass
    return destino


def anexar(destino, dados: bytes) -> None:
    """Acrescenta `dados` ao fim de `destino` sem seguir ligação nem vínculo físico (ver o módulo)."""
    destino = Path(destino)
    for _ in range(2):  # criado por outro entre a conferência e a criação: confere de novo, agora como existente
        try:
            antes = os.lstat(destino)
            _exigir_simples(destino, antes)
        except FileNotFoundError:
            antes = None
        criar = os.O_CREAT | os.O_EXCL if antes is None else 0
        try:
            fd = os.open(destino, os.O_WRONLY | os.O_APPEND | criar | _SEM_SEGUIR | _BINARIO, 0o666)
            break
        except FileExistsError:
            continue
        except OSError as exc:
            if exc.errno == errno.ELOOP:  # virou link simbólico depois da conferência (O_NOFOLLOW)
                _recusar(destino, "registro trocado por ligação")
            raise
    else:
        _recusar(destino, "registro trocado durante a gravação")
    try:
        aberto, depois = os.fstat(fd), os.lstat(destino)
        if (not stat.S_ISREG(aberto.st_mode) or aberto.st_nlink != 1 or _ligacao(depois) or not _mesmo(aberto, depois)
                or (antes is not None and not _mesmo(aberto, antes))):
            _recusar(destino, "registro trocado por ligação ou vínculo físico durante a gravação")
        _gravar_tudo(fd, dados)
    finally:
        os.close(fd)
