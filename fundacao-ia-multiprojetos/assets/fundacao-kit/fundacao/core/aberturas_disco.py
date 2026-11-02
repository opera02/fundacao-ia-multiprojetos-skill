"""Disco da ficha de aberturas: sem seguir ligação e preso à pasta aberta (1.7.10; contratos do lote 2, §5; revisão
independente do pacote ABERTURAS, 31/10/2026: a pasta era conferida pelo caminho e o arquivo, aberto ou criado depois
também pelo caminho; quem trocasse `outputs/` por um link no intervalo criava a ficha em outra pasta ou fazia o
rascunho ser lido de outro projeto).

`Pasta(base, partes, criar=False)` é a pasta `base/partes...`, cada parte abaixo de `base` sem ligação:
- no POSIX, cada parte é aberta pelo descritor da de cima (O_DIRECTORY | O_NOFOLLOW; criada por mkdirat com `criar`),
  e a listagem, a leitura e a gravação usam o descritor da pasta (listdir do descritor, openat, linkat, renameat e
  unlinkat): trocar uma pasta por ligação depois de aberta não desvia nada, e ligação no caminho recusa (PathEscape);
- no Windows, a biblioteca padrão não abre por pasta aberta nem tem O_NOFOLLOW: cada parte é conferida pelo caminho
  (lstat, sem junção nem link) e o arquivo é aberto em seguida, com a conferência do objeto aberto (fstat). Uma troca
  de pasta entre as duas coisas não é vista (o limite de core/preparo.py e core/publicacao.py); lá valem o exame, a
  conferência do objeto e, na ficha, a assinatura do titular sobre os bytes.
`base` é de confiança (a raiz, a pasta do projeto, a área do titular): vem do lançador ou da ferramenta do titular e é
aberta seguindo ligação; quem precisa confere antes que não há ligação nela nem acima (preparo.ligacao_no_caminho).
Arquivo lido: só comum, de um nome só (st_nlink 1), até o teto; FIFO não trava (O_NONBLOCK). `criar_novo` nunca
sobrescreve (AlreadyExists); `trocar` põe o arquivo no lugar por renomeação, que troca um link plantado no nome sem
gravar através dele.
"""

from __future__ import annotations

import errno
import os
import secrets
import stat
from pathlib import Path

from .contracts import AlreadyExists, PathEscape
from .publicacao import publicar

_SUBSTITUTA_DE_NOME = 0x20000000  # Windows: junção, link simbólico e afins (bit 29 da etiqueta de reparse)
_FECHAR = getattr(os, "O_CLOEXEC", 0)
_LEITURA = (os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            | _FECHAR)
_ESCRITA = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0) | _FECHAR
_PASTA = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | _FECHAR
_LIGACAO = frozenset({errno.ELOOP, errno.EMLINK, errno.ENOTDIR})  # O_NOFOLLOW num link: ELOOP (Linux), EMLINK (BSD)
POR_DESCRITOR = (os.name != "nt" and hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW")
                 and {os.open, os.mkdir, os.link, os.rename, os.unlink, os.stat} <= os.supports_dir_fd
                 and os.listdir in os.supports_fd and os.link in os.supports_follow_symlinks)


class LeituraRecusada(OSError):
    """Ligação, vínculo físico, arquivo que não é comum ou acima do teto: nada foi lido."""


def e_ligacao(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & _SUBSTITUTA_DE_NOME)


def _ler_fd(fd: int, nome: str, teto: int, examinado: os.stat_result | None = None) -> bytes:
    aberto = os.fstat(fd)
    if (not stat.S_ISREG(aberto.st_mode) or aberto.st_nlink != 1 or aberto.st_size > teto
            or (examinado is not None and (aberto.st_dev, aberto.st_ino) != (examinado.st_dev, examinado.st_ino))):
        raise LeituraRecusada(f"{nome}: recusado (não é arquivo comum de um nome só, passa de {teto} bytes ou foi "
                              "trocado entre o exame e a leitura)")
    partes, total = [], 0
    while bloco := os.read(fd, min(1 << 20, teto + 1 - total)):
        partes.append(bloco)
        total += len(bloco)
        if total > teto:
            raise LeituraRecusada(f"{nome}: recusado (acima de {teto} bytes)")
    return b"".join(partes)


def ler_arquivo(caminho, teto: int) -> bytes:
    """Bytes de um arquivo comum de um nome só, pelo caminho: lstat, O_NOFOLLOW onde existe e a conferência do objeto
    aberto. Ausente: FileNotFoundError; o resto: LeituraRecusada (ou o OSError da abertura)."""
    caminho = Path(caminho)
    st = os.lstat(caminho)
    if e_ligacao(st) or not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > teto:
        raise LeituraRecusada(f"{caminho.name}: recusado (ligação, vínculo físico, não é arquivo comum ou acima de "
                              f"{teto} bytes)")
    fd = os.open(caminho, _LEITURA)
    try:
        return _ler_fd(fd, caminho.name, teto, st)
    finally:
        os.close(fd)


def _recusar_pasta(parte: str):
    raise PathEscape("pasta é ligação (link simbólico ou junção) ou não é pasta: recusado", pasta=parte)


def _descer(fd: int, partes: tuple, criar: bool) -> int | None:
    """POSIX: a partir de `fd` (que passa a ser desta função), o descritor da pasta final, cada parte aberta sem seguir
    ligação; None se uma parte falta (sem `criar`)."""
    try:
        for parte in partes:
            if criar:
                try:
                    os.mkdir(parte, dir_fd=fd)
                except FileExistsError:
                    pass
            try:
                proxima = os.open(parte, _PASTA | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if criar:
                    raise
                return None
            except OSError as exc:
                if exc.errno in _LIGACAO:
                    _recusar_pasta(parte)
                raise
            os.close(fd)
            fd = proxima
        final, fd = fd, None
        return final
    finally:
        if fd is not None:
            os.close(fd)


def _conferir_pelo_caminho(base: Path, partes: tuple, criar: bool) -> bool:
    """Windows: cada parte abaixo de `base` conferida pelo caminho (sem junção nem link); False se uma parte falta."""
    try:
        if not stat.S_ISDIR(os.stat(base).st_mode):
            _recusar_pasta(base.name)
    except FileNotFoundError:
        if criar:
            raise
        return False
    atual = base
    for parte in partes:
        atual = atual / parte
        if criar:
            try:
                os.mkdir(atual)
            except FileExistsError:
                pass
        try:
            st = os.lstat(atual)
        except FileNotFoundError:
            if criar:
                raise
            return False
        if e_ligacao(st) or not stat.S_ISDIR(st.st_mode):
            _recusar_pasta(parte)
    return True


class Pasta:
    """A pasta `base/partes...` sem ligação abaixo de `base` (ver o módulo). `existe` falso: uma parte não existe (sem
    `criar`), e a pasta não tem nada. Use com `with`: no POSIX, o descritor fica aberto até o fim do bloco."""

    def __init__(self, base, partes=(), *, criar: bool = False):
        self.caminho, self._fd = Path(base).joinpath(*partes), None
        if not POR_DESCRITOR:
            self.existe = _conferir_pelo_caminho(Path(base), tuple(partes), criar)
            return
        try:
            fd = os.open(base, _PASTA)
        except FileNotFoundError:
            if criar:
                raise
            fd = None
        except NotADirectoryError:
            _recusar_pasta(Path(base).name)
        self._fd = None if fd is None else _descer(fd, tuple(partes), criar)
        self.existe = self._fd is not None

    @classmethod
    def absoluta(cls, caminho) -> "Pasta":
        """A pasta de um caminho absoluto, aberta da raiz do volume para baixo, cada parte sem seguir ligação: a
        ligação em qualquer ponto do caminho recusa, e no POSIX não há intervalo entre conferir e abrir (a área do
        titular e a caixa de entrada, lidas também pelo preparo do host, como root)."""
        caminho = Path(os.path.abspath(caminho))
        return cls(caminho.anchor, caminho.parts[1:])

    def __enter__(self) -> "Pasta":
        return self

    def __exit__(self, *_exc) -> None:
        self.fechar()

    def fechar(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def nomes(self) -> list[str]:
        if not self.existe:
            return []
        return sorted(os.listdir(self._fd if self._fd is not None else self.caminho))

    def lstat(self, nome: str) -> os.stat_result:
        if self._fd is not None:
            return os.stat(nome, dir_fd=self._fd, follow_symlinks=False)
        return os.lstat(self.caminho / nome)

    def sub(self, nome: str) -> "Pasta":
        """A pasta filha `nome`, sem seguir ligação (PathEscape se for ligação ou não for pasta)."""
        filha = Pasta.__new__(Pasta)
        filha.caminho, filha._fd = self.caminho / nome, None
        if self._fd is not None:
            filha._fd = _descer(os.dup(self._fd), (nome,), False)
            filha.existe = filha._fd is not None
        else:
            filha.existe = _conferir_pelo_caminho(self.caminho, (nome,), False)
        return filha

    def ler(self, nome: str, teto: int) -> bytes | None:
        """Bytes de `nome`, arquivo comum de um nome só e até `teto`, sem seguir ligação; None se não existe."""
        if not self.existe:
            return None
        if self._fd is None:
            try:
                return ler_arquivo(self.caminho / nome, teto)
            except FileNotFoundError:
                return None
        try:
            fd = os.open(nome, _LEITURA, dir_fd=self._fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            if exc.errno in _LIGACAO:
                raise LeituraRecusada(f"{nome}: recusado (ligação)") from None
            raise
        try:
            return _ler_fd(fd, nome, teto)
        finally:
            os.close(fd)

    def _temporario(self, nome: str, dados: bytes) -> str:
        tmp = f".{nome}.{secrets.token_hex(8)}.tmp"
        fd = (os.open(tmp, _ESCRITA, 0o644, dir_fd=self._fd) if self._fd is not None
              else os.open(self.caminho / tmp, _ESCRITA, 0o644))
        try:
            vista = memoryview(dados)
            while vista:
                vista = vista[os.write(fd, vista):]
            os.fsync(fd)
        except BaseException:
            os.close(fd)
            self._apagar(tmp)
            raise
        os.close(fd)
        return tmp

    def _apagar(self, nome: str) -> None:
        try:
            if self._fd is not None:
                os.unlink(nome, dir_fd=self._fd)
            else:
                os.unlink(self.caminho / nome)
        except FileNotFoundError:
            pass

    def criar_novo(self, nome: str, dados: bytes) -> None:
        """`nome` como arquivo NOVO: temporário exclusivo nesta pasta, depois vínculo (POSIX) ou renomeação (Windows),
        que falham se o nome já existe, também como ligação. Nada é sobrescrito (AlreadyExists). O vínculo não segue
        ligação (linkat sem AT_SYMLINK_FOLLOW): um temporário trocado por link no intervalo não vira um vínculo físico
        com o alvo dele (reconferência do pacote; o leitor recusaria de todo modo, pelo st_nlink)."""
        tmp = self._temporario(nome, dados)
        try:
            if self._fd is None:
                os.rename(self.caminho / tmp, self.caminho / nome)
            else:
                try:
                    os.link(tmp, nome, src_dir_fd=self._fd, dst_dir_fd=self._fd, follow_symlinks=False)
                except FileExistsError:
                    raise
                except OSError:  # sistema de arquivos sem vínculo físico: confere e renomeia
                    try:
                        self.lstat(nome)
                    except FileNotFoundError:
                        os.rename(tmp, nome, src_dir_fd=self._fd, dst_dir_fd=self._fd)
                    else:
                        raise FileExistsError(nome) from None
        except FileExistsError:
            raise AlreadyExists("o arquivo já existe; nada foi sobrescrito", arquivo=nome) from None
        finally:
            self._apagar(tmp)

    def trocar(self, nome: str, dados: bytes) -> None:
        """Põe `dados` em `nome`, novo ou no lugar do antigo, por temporário e renomeação (no Windows, por
        core/publicacao.publicar): um link plantado no nome é trocado, nunca seguido."""
        if self._fd is None:
            publicar(self.caminho / nome, dados)
            return
        tmp = self._temporario(nome, dados)
        try:
            os.rename(tmp, nome, src_dir_fd=self._fd, dst_dir_fd=self._fd)
        finally:
            self._apagar(tmp)
