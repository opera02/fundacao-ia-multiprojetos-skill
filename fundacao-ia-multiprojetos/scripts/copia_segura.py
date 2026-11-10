#!/usr/bin/env python3
"""Cópia de arquivo feita FORA do sandbox a partir de área que a sessão grava (1.7.10; crítica do desenho e
contratos do lote 2, §8): a função única para o preparo dos plugins, a promoção da versão em uso e a importação.

O titular (ou o porteiro) copia, fora do sandbox, arquivos de uma árvore que a sessão do projeto controla. Uma
ligação simbólica, uma junção ou um vínculo físico plantados ali fariam a cópia ler um arquivo de fora (outro
projeto, `state/`, a chave do titular) e levá-lo para onde a sessão o veja. Por isso, `copiar_conferindo`:

1. com `dentro_de`, no POSIX, abre a origem descendo pasta a pasta por descritor (`O_DIRECTORY|O_NOFOLLOW` em cada
   nível e `O_NOFOLLOW` no arquivo): uma pasta acima trocada por ligação é recusada, sem janela entre exame e
   abertura; nos demais casos, examina sem seguir ligação (`lstat`), abre com `O_NOFOLLOW` onde existir e confere no
   descritor aberto que é o mesmo objeto do exame (`st_dev`, `st_ino`) e, com `dentro_de`, que o caminho real fica
   dentro dessa pasta;
2. só aceita arquivo comum com um nome só (`st_nlink == 1`); `O_NONBLOCK` faz um FIFO plantado não travar a leitura;
3. copia em fluxo para um temporário exclusivo (`O_CREAT|O_EXCL|O_NOFOLLOW`) ao lado do destino, calculando o
   SHA-256 dos bytes lidos ao mesmo tempo, e confere o SHA-256 esperado, quando dado (o rehash contra o manifesto ou
   a proposta aceita: um conteúdo trocado no caminho é recusado mesmo onde o exame tem janela);
4. aplica o modo (fora do Windows) e renomeia para o destino, que não pode existir.

Destino por descritor de pasta (`descer_pastas` e `pasta_fd=`, só POSIX; revisão de segurança da 1.7.11, F2): quando a pasta
do destino está dentro de uma árvore que a sessão também grava (a volta da saída da jaula para `projects/<p>/outputs/`), o
caminho pode ser trocado por ligação entre a conferência e a gravação. `descer_pastas` abre cada pasta com
`O_DIRECTORY|O_NOFOLLOW` a partir da anterior e devolve o descritor da última; `copiar_conferindo(..., pasta_fd=fd)` cria o
temporário e renomeia relativos a esse descritor (`dir_fd`), então uma troca depois da abertura não muda onde o arquivo cai.

Erro: `CopiaRecusada` (subclasse de `OSError`); o temporário é apagado e nada fica no destino. A pasta do destino é
de quem chama (ex.: criada por `gravacao_segura.pasta_sem_ligacao`): aqui só se confere que ela é pasta e não
ligação. Limite (o mesmo do kit): no Windows não há `O_NOFOLLOW` nem abertura por descritor de pasta; a defesa é o
exame, a conferência do objeto aberto e do caminho real e, sobretudo, o SHA-256 esperado. O kit não importa este
módulo (tem a sua cópia conferida em `core/preparo.py`).

Linha de comando (ex.: no preparo do Ubuntu), saída JSON; código 0 feito, 2 recusado:
  python3 -I -B copia_segura.py copiar --origem <arq> --destino <arq> [--sha256 <hex>] [--dentro-de <pasta>]
  python3 -I -B copia_segura.py hash <arq> [--dentro-de <pasta>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

O_BINARY = getattr(os, "O_BINARY", 0)
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
# Windows: etiqueta de ponto de nova análise "substituta de nome" (bit 29) — junção, link simbólico e afins.
SUBSTITUTA_DE_NOME = 0x20000000
BLOCO = 1 << 20
PREFIXO_TEMP = ".copiando-"
_POR_DESCRITOR = (os.name == "posix" and bool(O_NOFOLLOW) and hasattr(os, "O_DIRECTORY")
                  and os.open in os.supports_dir_fd)


class CopiaRecusada(OSError):
    """A cópia foi recusada: nada foi gravado no destino."""


def e_ligacao(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & SUBSTITUTA_DE_NOME)


def _motivo(exc: OSError) -> str:
    return exc.strerror or str(exc)


def _abrir_por_descritor(base: Path, partes: list[str]) -> int:
    """POSIX: desce de `base` até o arquivo, cada pasta com `O_DIRECTORY|O_NOFOLLOW` e o arquivo com `O_NOFOLLOW`."""
    fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
    try:
        for parte in partes[:-1]:
            novo = os.open(parte, os.O_RDONLY | os.O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = novo
        return os.open(partes[-1], os.O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK, dir_fd=fd)
    finally:
        os.close(fd)


def descer_pastas(base, partes: list[str], *, criar: bool = False, ultima_nova: bool = False) -> int:
    """POSIX: descritor da pasta `base/partes...`, cada nível aberto com `O_DIRECTORY|O_NOFOLLOW` relativo ao anterior (ligação
    no caminho é recusada, sem janela entre exame e abertura). `base`: caminho ou descritor de pasta (esse não é fechado).
    `criar`: cria (0o755, por `dir_fd`) a parte que falta. `ultima_nova`: a última parte tem de ser criada agora (se já existe,
    `FileExistsError`). Erro de sistema (`OSError`): nada fica aberto."""
    if not _POR_DESCRITOR:
        raise CopiaRecusada("abrir pasta por descritor só existe no POSIX")
    flags = os.O_RDONLY | os.O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
    fd = os.dup(base) if isinstance(base, int) else os.open(base, flags)
    try:
        for i, parte in enumerate(partes):
            if parte in ("", ".", "..") or "/" in parte:
                raise CopiaRecusada(f"{parte!r}: parte de caminho inválida")
            nova = ultima_nova and i == len(partes) - 1
            if criar or nova:
                try:
                    os.mkdir(parte, 0o755, dir_fd=fd)
                except FileExistsError:
                    if nova:
                        raise
            novo = os.open(parte, flags, dir_fd=fd)
            os.close(fd)
            fd = novo
        return fd
    except BaseException:
        os.close(fd)
        raise


def _conferir_aberto(fd: int, nome: str, antes: os.stat_result | None) -> None:
    aberto = os.fstat(fd)
    if not stat.S_ISREG(aberto.st_mode):
        raise CopiaRecusada(f"{nome}: não é arquivo comum")
    if aberto.st_nlink != 1:
        raise CopiaRecusada(f"{nome}: tem vínculo físico (mais de um nome): o conteúdo pode ser de um arquivo de fora")
    if antes is not None and (aberto.st_dev, aberto.st_ino) != (antes.st_dev, antes.st_ino):
        raise CopiaRecusada(f"{nome}: trocado entre o exame e a abertura")


def abrir_comum(origem, dentro_de=None) -> int:
    """Descritor de leitura da origem, conferido: arquivo comum, um nome só e, com `dentro_de`, dentro dessa pasta."""
    origem = Path(os.path.abspath(origem))
    nome = origem.name
    if dentro_de is not None:
        base = Path(os.path.abspath(dentro_de))
        rel = os.path.relpath(origem, base)
        partes = Path(rel).parts
        if rel == "." or not partes or partes[0] == ".." or Path(rel).is_absolute():
            raise CopiaRecusada(f"{nome}: fica fora de {base}")
        if _POR_DESCRITOR:
            try:
                fd = _abrir_por_descritor(base, list(partes))
            except OSError as exc:
                raise CopiaRecusada(f"{nome}: não abriu sem seguir ligação ({_motivo(exc)})") from None
            try:
                _conferir_aberto(fd, nome, None)
            except BaseException:
                os.close(fd)
                raise
            return fd
    try:
        antes = os.lstat(origem)
    except OSError as exc:
        raise CopiaRecusada(f"{nome}: não deu para examinar ({_motivo(exc)})") from None
    if e_ligacao(antes) or not stat.S_ISREG(antes.st_mode):
        raise CopiaRecusada(f"{nome}: é ligação ou não é arquivo comum")
    if antes.st_nlink != 1:
        raise CopiaRecusada(f"{nome}: tem vínculo físico (mais de um nome): o conteúdo pode ser de um arquivo de fora")
    try:
        fd = os.open(origem, os.O_RDONLY | O_BINARY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK)
    except OSError as exc:
        raise CopiaRecusada(f"{nome}: não abriu sem seguir ligação ({_motivo(exc)})") from None
    try:
        _conferir_aberto(fd, nome, antes)
        if dentro_de is not None and not Path(os.path.realpath(origem)).is_relative_to(os.path.realpath(dentro_de)):
            raise CopiaRecusada(f"{nome}: o caminho real fica fora de {dentro_de}")
    except BaseException:
        os.close(fd)
        raise
    return fd


def hash_conferido(origem, dentro_de=None) -> dict:
    """SHA-256 e tamanho dos bytes lidos pelo mesmo caminho conferido da cópia."""
    fd = abrir_comum(origem, dentro_de)
    h, n = hashlib.sha256(), 0
    try:
        while bloco := os.read(fd, BLOCO):
            h.update(bloco)
            n += len(bloco)
    finally:
        os.close(fd)
    return {"sha256": h.hexdigest(), "bytes": n}


def copiar_conferindo(origem, destino, *, sha256_esperado: str | None = None, modo: int | None = 0o444,
                      dentro_de=None, pasta_fd: int | None = None) -> dict:
    """Copia `origem` para `destino` (que não pode existir) pelo caminho conferido; devolve sha256, bytes e o modo
    aplicado (None no Windows). `modo=None` guarda o bit de execução da origem (`modo & 0o755`). `pasta_fd`: o descritor da
    pasta do destino (de `descer_pastas`); então só o NOME de `destino` vale e tudo (existência, temporário, modo, renomeação)
    é relativo a esse descritor, sem seguir caminho."""
    destino = Path(os.path.abspath(destino)) if pasta_fd is None else Path(Path(destino).name)
    if pasta_fd is not None:
        try:
            st_pasta = os.fstat(pasta_fd)
        except OSError as exc:
            raise CopiaRecusada(f"{destino.name}: a pasta do destino não abriu ({_motivo(exc)})") from None
        if not stat.S_ISDIR(st_pasta.st_mode):
            raise CopiaRecusada(f"{destino.name}: a pasta do destino não é pasta")
        try:
            os.stat(destino.name, dir_fd=pasta_fd, follow_symlinks=False)
            raise CopiaRecusada(f"{destino.name}: o destino já existe")
        except FileNotFoundError:
            pass
        temp = Path(f"{PREFIXO_TEMP}{os.urandom(6).hex()}.tmp")
    else:
        if os.path.lexists(destino):
            raise CopiaRecusada(f"{destino.name}: o destino já existe")
        try:
            st_pasta = os.lstat(destino.parent)
        except OSError as exc:
            raise CopiaRecusada(f"{destino.parent}: a pasta do destino não existe ({_motivo(exc)})") from None
        if e_ligacao(st_pasta) or not stat.S_ISDIR(st_pasta.st_mode):
            raise CopiaRecusada(f"{destino.parent}: a pasta do destino é ligação ou não é pasta")
        temp = destino.parent / f"{PREFIXO_TEMP}{os.urandom(6).hex()}.tmp"
    fd = abrir_comum(origem, dentro_de)
    criado = False
    try:
        aplicado = None if os.name == "nt" else (
            modo if modo is not None else stat.S_IMODE(os.fstat(fd).st_mode) & 0o755)
        try:
            saida = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_BINARY | O_NOFOLLOW | O_CLOEXEC, 0o600,
                            dir_fd=pasta_fd)
        except OSError as exc:
            raise CopiaRecusada(f"{destino.name}: não deu para criar o temporário ({_motivo(exc)})") from None
        criado = True
        h, n = hashlib.sha256(), 0
        try:
            while bloco := os.read(fd, BLOCO):
                h.update(bloco)
                n += len(bloco)
                vista = memoryview(bloco)
                while vista:
                    vista = vista[os.write(saida, vista):]
            os.fsync(saida)
            if aplicado is not None:   # pelo descritor aberto (O_EXCL|O_NOFOLLOW): o chmod por nome seguiria uma ligação posta no lugar
                os.fchmod(saida, aplicado)
        finally:
            os.close(saida)
        sha = h.hexdigest()
        if sha256_esperado is not None and sha != sha256_esperado.strip().lower():
            raise CopiaRecusada(f"{Path(origem).name}: o SHA-256 lido ({sha[:12]}...) difere do esperado "
                                f"({sha256_esperado.strip().lower()[:12]}...): nada foi gravado")
        if pasta_fd is None:
            if os.path.lexists(destino):
                raise CopiaRecusada(f"{destino.name}: o destino apareceu durante a cópia")
            os.rename(temp, destino)  # no Windows falha se o destino existir; no POSIX, a conferência logo acima
        else:
            try:
                os.stat(destino.name, dir_fd=pasta_fd, follow_symlinks=False)
                raise CopiaRecusada(f"{destino.name}: o destino apareceu durante a cópia")
            except FileNotFoundError:
                pass
            os.rename(temp, destino.name, src_dir_fd=pasta_fd, dst_dir_fd=pasta_fd)
        criado = False
    except CopiaRecusada:
        raise
    except OSError as exc:  # leitura, gravação ou renomeação: o contrato é sempre CopiaRecusada, sem nada no destino
        raise CopiaRecusada(f"{destino.name}: a cópia falhou ({_motivo(exc)}): nada foi gravado") from None
    finally:
        os.close(fd)
        if criado:
            try:
                os.unlink(temp, dir_fd=pasta_fd)
            except OSError:
                pass
    return {"sha256": sha, "bytes": n, "modo": aplicado}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="copia_segura.py", allow_abbrev=False,
                                description="Cópia e hash de arquivo sem seguir ligação nem vínculo físico.")
    sub = p.add_subparsers(dest="acao", required=True)
    c = sub.add_parser("copiar", allow_abbrev=False)
    c.add_argument("--origem", required=True)
    c.add_argument("--destino", required=True)
    c.add_argument("--sha256")
    c.add_argument("--dentro-de")
    h = sub.add_parser("hash", allow_abbrev=False)
    h.add_argument("arquivo")
    h.add_argument("--dentro-de")
    args = p.parse_args(argv)
    try:
        if args.acao == "copiar":
            res = copiar_conferindo(args.origem, args.destino, sha256_esperado=args.sha256, dentro_de=args.dentro_de)
        else:
            res = hash_conferido(args.arquivo, args.dentro_de)
    except CopiaRecusada as exc:
        print(json.dumps({"erro": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
