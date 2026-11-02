"""Arquivos de projects/<p>/ pelo descritor da pasta conferida (1.7.10; revisão de segurança da 1.7.10, POR-01, POR-02
e POR-03): o kit rodado pelo porteiro, fora do sandbox, conferia o caminho (`contained`, que resolve) e depois abria
pelo caminho; quem trocasse uma pasta do projeto por uma ligação no intervalo levava a gravação para fora do projeto,
fazia a leitura vir de fora e, com um FIFO no lugar do arquivo, deixava o kit parado com a vez do banco na mão.

`Pasta(pasta_projeto, partes)` é `projects/<p>/<partes...>`, com `pasta_projeto` vinda de `project_root`:
- no POSIX, projects/ é aberta pelo caminho (vem da raiz do lançador) e <p> e cada parte abaixo pelo descritor da de
  cima, com O_DIRECTORY | O_NOFOLLOW; a parte que falta nasce na primeira gravação (mkdirat) e é aberta do mesmo
  jeito. Arquivo novo: openat com O_CREAT | O_EXCL | O_NOFOLLOW. Leitura: openat com O_NOFOLLOW | O_NONBLOCK e, antes
  de ler, o fstat (só arquivo comum, de um nome só e até o teto: um FIFO é recusado na hora). Acréscimo: O_APPEND e
  O_NONBLOCK, com o nome conferido antes e depois de abrir. Troca: temporário exclusivo e renameat na mesma pasta.
  Trocar uma pasta por ligação depois de aberta não desvia nada. Nenhuma abertura espera (revisão 1 do grupo KITDEC,
  POR-03): o FIFO trocado no nome depois da conferência (ENXIO, sem leitor), o arquivo preso por um arrendamento de
  outro processo (F_SETLEASE: EWOULDBLOCK, em vez de esperar até 45 s) e, no DrvFs, a pasta aberta que foi renomeada
  (ENXIO) são recusados na hora;
- no Windows (sem dir_fd nem O_NOFOLLOW na biblioteca padrão), o padrão de cli_conhecimento._abrir_catalogo: cada
  parte pelo lstat do caminho não resolvido (sem link nem junção), de novo antes de cada operação, e o objeto aberto
  conferido pelo fstat. A troca de uma pasta entre o lstat e a abertura não é vista (o limite de core/publicacao.py).
Ligação, vínculo físico, o que não é arquivo comum ou está preso por outro processo: PathEscape, sem ler nem gravar
nada; ausente: None.
"""

from __future__ import annotations

import errno
import hashlib
import os
import secrets
import stat
from pathlib import Path

from .contracts import AlreadyExists, PathEscape
from .publicacao import publicar

_SUBSTITUTA_DE_NOME = 0x20000000  # Windows: junção, link simbólico e afins (bit 29 da etiqueta de reparse)
_BIN, _FECHAR, _SEM_SEGUIR = getattr(os, "O_BINARY", 0), getattr(os, "O_CLOEXEC", 0), getattr(os, "O_NOFOLLOW", 0)
_SEM_ESPERA = getattr(os, "O_NONBLOCK", 0)
_LER = os.O_RDONLY | _BIN | _SEM_SEGUIR | _SEM_ESPERA | _FECHAR
_NOVO = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _BIN | _SEM_SEGUIR | _FECHAR
_ACRESCIMO = os.O_WRONLY | os.O_APPEND | _BIN | _SEM_SEGUIR | _SEM_ESPERA | _FECHAR  # revisão 1 do KITDEC, POR-03
_PASTA = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | _FECHAR
# Recusa na abertura, sem esperar: O_NOFOLLOW num link (ELOOP no Linux, EMLINK no BSD; ENOTDIR na pasta); o FIFO sem
# leitor e, no DrvFs, a pasta aberta que foi renomeada (ENXIO); o arrendamento de outro processo (EWOULDBLOCK).
_RECUSA = frozenset({errno.ELOOP, errno.EMLINK, errno.ENOTDIR, errno.ENXIO, errno.EAGAIN, errno.EWOULDBLOCK})
POR_DESCRITOR = (os.name != "nt" and bool(_SEM_SEGUIR) and hasattr(os, "O_DIRECTORY")
                 and {os.open, os.mkdir, os.rename, os.unlink, os.stat} <= os.supports_dir_fd
                 and os.stat in os.supports_follow_symlinks)


def e_ligacao(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & _SUBSTITUTA_DE_NOME)


def _mesmo(a: os.stat_result, b: os.stat_result) -> bool:
    return (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


def _recusar(nome: str, pasta: bool = False):
    if pasta:
        raise PathEscape("pasta do projeto é ligação (link simbólico ou junção) ou não é pasta: recusado", pasta=nome)
    raise PathEscape("arquivo do projeto é ligação, vínculo físico, não é arquivo comum, está preso por outro processo "
                     "ou passa do teto: recusado; nada foi lido nem gravado", arquivo=nome)


def _aberto(fd: int, nome: str, teto: int, visto: os.stat_result | None = None) -> None:
    """O objeto aberto, antes de ler: arquivo comum, de um nome só, até o teto e (pelo caminho) o mesmo do lstat."""
    st = os.fstat(fd)
    if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > teto
            or (visto is not None and not _mesmo(st, visto))):
        _recusar(nome)


def _ler(fd: int, nome: str, teto: int, resumo: bool) -> bytes | str:
    """Os bytes (ou o SHA-256, lido por partes) até o teto; o que cresceu depois do fstat é recusado."""
    partes, total, sha = [], 0, hashlib.sha256()
    while bloco := os.read(fd, min(1 << 20, teto + 1 - total)):
        total += len(bloco)
        if total > teto:
            _recusar(nome)
        if resumo:
            sha.update(bloco)
        else:
            partes.append(bloco)
    return sha.hexdigest() if resumo else b"".join(partes)


def _gravar(fd: int, dados: bytes) -> None:
    vista = memoryview(dados)
    while vista:
        vista = vista[os.write(fd, vista):]
    os.fsync(fd)


def _filha(fd: int, nome: str) -> int:
    """POSIX: o descritor da pasta `nome` dentro de `fd`, sem seguir ligação."""
    try:
        return os.open(nome, _PASTA | _SEM_SEGUIR, dir_fd=fd)
    except OSError as exc:
        if exc.errno in _RECUSA:
            _recusar(nome, pasta=True)
        raise


def dentro(caminho: Path, base: Path) -> bool:
    try:
        caminho.relative_to(base)
        return True
    except ValueError:
        return False


def ler_arquivo(caminho, teto: int) -> bytes:
    """Bytes de um arquivo comum de um nome só, até `teto`, pelo caminho (fora de projects/, como a assinatura numa
    pasta temporária): lstat, abertura com O_NOFOLLOW | O_NONBLOCK onde existem e a conferência do objeto aberto.
    Ausente: FileNotFoundError; ligação, FIFO, vínculo físico ou acima do teto: PathEscape."""
    caminho = Path(caminho)
    visto = os.lstat(caminho)
    if e_ligacao(visto) or not stat.S_ISREG(visto.st_mode):
        _recusar(caminho.name)
    try:
        fd = os.open(caminho, _LER)
    except OSError as exc:
        if exc.errno in _RECUSA:
            _recusar(caminho.name)
        raise
    try:
        _aberto(fd, caminho.name, teto, visto)
        return _ler(fd, caminho.name, teto, False)
    finally:
        os.close(fd)


class Pasta:
    """`projects/<p>/<partes...>` sem ligação abaixo de projects/ (ver o módulo). As partes que faltam nascem na
    primeira gravação. Use com `with`: no POSIX, o descritor fica aberto até o fim do bloco."""

    def __init__(self, pasta_projeto, partes=()):
        projeto = Path(pasta_projeto)
        self.caminho = projeto.joinpath(*partes)
        self._base, self._partes, self._fd, self._faltam = projeto.parent, (projeto.name, *partes), None, tuple(partes)
        try:
            if POR_DESCRITOR:
                base = os.open(self._base, _PASTA)
                try:
                    self._fd = _filha(base, projeto.name)  # a pasta do projeto precisa existir
                finally:
                    os.close(base)
            self._antes()
        except BaseException:
            self.fechar()
            raise

    def __enter__(self) -> "Pasta":
        return self

    def __exit__(self, *_exc) -> None:
        self.fechar()

    def fechar(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def _antes(self, criar: bool = False) -> bool:
        """Antes de cada operação: no POSIX, desce pelas partes que faltavam (criando-as, para gravar); no Windows,
        confere de novo a cadeia pelo caminho. Devolve se a pasta existe."""
        if not POR_DESCRITOR:
            return self._conferir(criar)
        while self._faltam:
            if criar:
                try:
                    os.mkdir(self._faltam[0], 0o777, dir_fd=self._fd)
                except FileExistsError:
                    pass
            try:
                filha = _filha(self._fd, self._faltam[0])
            except FileNotFoundError:
                if criar:
                    raise
                return False
            os.close(self._fd)
            self._fd, self._faltam = filha, self._faltam[1:]
        return True

    def _conferir(self, criar: bool) -> bool:
        """Windows: cada parte abaixo de projects/ pelo lstat do caminho não resolvido; a que falta nasce com `criar`
        (a pasta do projeto, nunca)."""
        if not stat.S_ISDIR(os.stat(self._base).st_mode):
            _recusar(self._base.name, pasta=True)
        atual = self._base
        for i, parte in enumerate(self._partes):
            atual = atual / parte
            if criar and i:
                try:
                    os.mkdir(atual)
                except FileExistsError:
                    pass
            try:
                st = os.lstat(atual)
            except FileNotFoundError:
                if criar or not i:
                    raise
                return False
            if e_ligacao(st) or not stat.S_ISDIR(st.st_mode):
                _recusar(parte, pasta=True)
        return True

    def _abrir(self, nome: str, modo: int) -> int:
        try:
            if POR_DESCRITOR:
                return os.open(nome, modo, 0o666, dir_fd=self._fd)
            return os.open(self.caminho / nome, modo, 0o666)
        except OSError as exc:
            if exc.errno in _RECUSA:
                _recusar(nome)
            raise

    def lstat(self, nome: str) -> os.stat_result | None:
        try:
            if not self._antes():
                return None
            if POR_DESCRITOR:
                return os.stat(nome, dir_fd=self._fd, follow_symlinks=False)
            return os.lstat(self.caminho / nome)
        except FileNotFoundError:
            return None
        except OSError as exc:  # no DrvFs, a pasta aberta e depois renomeada: ENXIO (revisão 1 do KITDEC)
            if exc.errno == errno.ENXIO:
                _recusar(nome)
            raise

    def ler(self, nome: str, teto: int, *, resumo: bool = False) -> bytes | str | None:
        """Bytes de `nome` (com `resumo`, o SHA-256 dele, lido por partes): arquivo comum, de um nome só e até `teto`,
        sem seguir ligação nem travar num FIFO. Ausente: None."""
        visto = None
        if not POR_DESCRITOR:  # sem O_NOFOLLOW: o exame sem seguir ligação antes (e o mesmo objeto depois)
            visto = self.lstat(nome)
            if visto is None:
                return None
            if e_ligacao(visto) or not stat.S_ISREG(visto.st_mode):
                _recusar(nome)
        elif not self._antes():
            return None
        try:
            fd = self._abrir(nome, _LER)
        except FileNotFoundError:
            return None
        try:
            _aberto(fd, nome, teto, visto)
            return _ler(fd, nome, teto, resumo)
        finally:
            os.close(fd)

    def criar_novo(self, nome: str, dados: bytes, aviso: str = "o arquivo já existe; nada foi sobrescrito",
                   **detalhes) -> None:
        """`nome` como arquivo NOVO (O_CREAT | O_EXCL | O_NOFOLLOW): nada é sobrescrito nem gravado através de uma
        ligação no nome (AlreadyExists, com `aviso`)."""
        self._antes(criar=True)
        try:
            fd = self._abrir(nome, _NOVO)
        except FileExistsError:
            raise AlreadyExists(aviso, **detalhes) from None
        try:
            _gravar(fd, dados)
        except BaseException:
            os.close(fd)
            self.apagar(nome, quieto=True)
            raise
        os.close(fd)

    def anexar(self, nome: str, dados: bytes) -> None:
        """Acrescenta `dados` ao fim de `nome` (criado se faltar), como core/publicacao.anexar, mas pela pasta aberta:
        ligação, vínculo físico ou outro objeto no nome, antes ou depois de abrir, recusa sem gravar. A abertura não
        espera (O_NONBLOCK): o FIFO trocado no nome depois da conferência e o arquivo arrendado por outro processo
        recusam na hora, sem prender a vez do banco do porteiro (revisão 1 do KITDEC, POR-03)."""
        self._antes(criar=True)
        for _ in range(2):  # criado por outro entre a conferência e a criação: confere de novo, agora como existente
            antes = self.lstat(nome)
            if antes is not None and (e_ligacao(antes) or not stat.S_ISREG(antes.st_mode) or antes.st_nlink != 1):
                _recusar(nome)
            try:
                fd = self._abrir(nome, _ACRESCIMO | (os.O_CREAT | os.O_EXCL if antes is None else 0))
                break
            except FileExistsError:
                continue
        else:
            _recusar(nome)
        try:
            aberto, depois = os.fstat(fd), self.lstat(nome)
            if (not stat.S_ISREG(aberto.st_mode) or aberto.st_nlink != 1 or depois is None or e_ligacao(depois)
                    or not _mesmo(aberto, depois) or (antes is not None and not _mesmo(aberto, antes))):
                _recusar(nome)
            _gravar(fd, dados)
        finally:
            os.close(fd)

    def trocar(self, nome: str, dados: bytes) -> None:
        """Põe `dados` em `nome`, novo ou no lugar do antigo, por temporário exclusivo e renomeação na mesma pasta: um
        link plantado no nome é trocado, nunca seguido (no Windows, por core/publicacao.publicar)."""
        self._antes(criar=True)
        if not POR_DESCRITOR:
            publicar(self.caminho / nome, dados)
            return
        tmp = f".{nome}.{secrets.token_hex(8)}.tmp"
        fd = self._abrir(tmp, _NOVO)
        try:
            try:
                _gravar(fd, dados)
            finally:
                os.close(fd)
            os.rename(tmp, nome, src_dir_fd=self._fd, dst_dir_fd=self._fd)
        except BaseException:
            self.apagar(tmp, quieto=True)
            raise

    def apagar(self, nome: str, *, quieto: bool = False) -> None:
        """Tira o nome, sem seguir ligação; ausente, nada. `quieto`: nenhuma falha sobe (limpeza de uma falha que já
        está saindo)."""
        try:
            if not self._antes():
                return
            if POR_DESCRITOR:
                os.unlink(nome, dir_fd=self._fd)
            else:
                os.unlink(self.caminho / nome)
        except FileNotFoundError:
            pass
        except (OSError, PathEscape):
            if not quieto:
                raise
