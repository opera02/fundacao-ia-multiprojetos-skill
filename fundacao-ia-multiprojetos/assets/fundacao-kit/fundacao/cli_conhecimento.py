"""Catálogo e busca de um projeto pela autorização da fundação: as leituras do servidor MCP (listar_documentos e
buscar), na CLI. É o caminho para pedir conteúdo de um projeto, mesmo esperando recusa: a negativa fica na trilha
(access_denied) e volta como erro, sem conteúdo.

O catálogo (data/catalog.json) é lido por um ajudante só, `ler_catalogo`, aqui e no servidor MCP (F6 da revisão de
segurança da 1.7.9, 1.7.10): sem seguir ligação, com um nome só (vínculo físico com o catálogo de outro projeto é
recusado) e o objeto aberto igual ao do caminho conferido."""
import json
import os
import stat
from pathlib import Path

from .core.contracts import PathEscape, ValidationError
from .core.knowledge import KnowledgeService
from .core.paths import contained
from .core.projects import project_root

LIMITE_CATALOGO = 8 * 1024 * 1024  # o mesmo teto de components/source_manifest.py: o catálogo é lido inteiro
_SUBSTITUTO_DE_NOME = 0x20000000  # Windows: junção, link simbólico e afins (bit 29 da etiqueta de reparse)


def _ligacao(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & _SUBSTITUTO_DE_NOME)


def _abrir_catalogo(pasta: Path) -> int | None:
    """Abre pasta/data/catalog.json sem seguir ligação em nível nenhum, ou None se não existe. No POSIX, desce pela
    cadeia (data, depois catalog.json) com dir_fd e O_NOFOLLOW, sem corrida; sem dir_fd (Windows), o lstat de `data` e
    de `catalog.json` não resolvidos (em ler_catalogo) já recusou ligação e o O_NOFOLLOW guarda o último componente."""
    comum = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    nofollow, direc = getattr(os, "O_NOFOLLOW", 0), getattr(os, "O_DIRECTORY", 0)
    if os.open in os.supports_dir_fd and nofollow:
        try:
            dir_proj = os.open(pasta, comum | direc)
        except FileNotFoundError:
            return None
        try:
            try:
                dir_dados = os.open("data", comum | direc | nofollow, dir_fd=dir_proj)
            except FileNotFoundError:
                return None
            except OSError as exc:
                raise PathEscape("pasta data/ do projeto é ligação: recusado") from exc
            try:
                try:
                    return os.open("catalog.json", comum | nofollow, dir_fd=dir_dados)
                except FileNotFoundError:
                    return None
                except OSError as exc:
                    raise PathEscape("catálogo do projeto é ligação: recusado") from exc
            finally:
                os.close(dir_dados)
        finally:
            os.close(dir_proj)
    try:
        return os.open(pasta / "data" / "catalog.json", comum | nofollow)
    except FileNotFoundError:
        return None


def ler_catalogo(pasta: Path) -> list:
    """Identificadores de data/catalog.json da `pasta` do projeto (já autorizada por quem chama); sem catálogo, lista
    vazia. `data` e `catalog.json` são conferidos pelo lstat do caminho NÃO resolvido (antes de `contained`, que
    resolve e seguiria a ligação — F6): nenhum dos dois pode ser ligação, o catálogo precisa ser arquivo comum de um
    nome só (st_nlink == 1) e resolver dentro da pasta do projeto. A abertura não segue ligação em nível nenhum (no
    POSIX, pela cadeia de pastas com dir_fd e O_NOFOLLOW) e, depois de aberto, o fstat confere de novo um nome só e que
    é o mesmo objeto do lstat. Antes, `contained` resolvia o caminho antes do lstat, e a ligação de data/catalog.json
    para dentro do projeto era seguida (F6)."""
    pasta = Path(pasta)
    dados_dir, caminho = pasta / "data", pasta / "data" / "catalog.json"
    try:
        st_dir = os.lstat(dados_dir)
    except FileNotFoundError:
        return []
    if _ligacao(st_dir) or not stat.S_ISDIR(st_dir.st_mode):
        raise PathEscape("pasta data/ do projeto é ligação ou não é pasta: recusado")
    try:
        antes = os.lstat(caminho)
    except FileNotFoundError:
        return []
    if _ligacao(antes) or not stat.S_ISREG(antes.st_mode) or antes.st_nlink != 1:
        raise PathEscape("catálogo do projeto é ligação, vínculo físico ou não é arquivo comum: recusado")
    contained(dados_dir, caminho, within=pasta)  # data/ e o catálogo resolvem dentro do projeto
    fd = _abrir_catalogo(pasta)
    if fd is None:
        return []
    try:
        aberto = os.fstat(fd)
        if (aberto.st_nlink != 1 or not stat.S_ISREG(aberto.st_mode)
                or (aberto.st_dev, aberto.st_ino) != (antes.st_dev, antes.st_ino)):
            raise PathEscape("catálogo do projeto com vínculo físico ou trocado durante a leitura: recusado")
        dados = bytearray()
        while bloco := os.read(fd, min(1 << 20, LIMITE_CATALOGO + 1 - len(dados))):
            dados += bloco
            if len(dados) > LIMITE_CATALOGO:
                raise ValidationError("catálogo do projeto acima do teto", limite=LIMITE_CATALOGO)
    finally:
        os.close(fd)
    try:
        return sorted(json.loads(bytes(dados).decode("utf-8")))
    except (TypeError, UnicodeDecodeError, ValueError):
        raise ValidationError("catálogo do projeto ilegível") from None


def registrar_parser(subparsers):
    p = subparsers.add_parser("conhecimento", help="catálogo e busca de um projeto, pela autorização da fundação")
    p.add_argument("acao", choices=("listar", "buscar"))
    p.add_argument("--projeto", required=True)
    p.add_argument("--consulta", default="", help="buscar: termos da busca nos trechos aprovados e vigentes")
    return p


def executar(args, con, principal, tombstone_log=None):
    if args.acao == "listar":
        pasta = project_root(args.raiz, con, principal, args.projeto, action="read")  # autoriza antes de ler
        try:
            return {"projeto": args.projeto, "documentos": ler_catalogo(pasta)}
        except (ValidationError, PathEscape) as exc:
            exc.details.setdefault("projeto", args.projeto)
            raise
    # Como no MCP, a busca autoriza antes de olhar a consulta: o pedido sem termos também deixa a negativa na trilha.
    hits = KnowledgeService(args.raiz, con, principal, tombstone_log).search(args.projeto, args.consulta)
    return {"projeto": args.projeto,
            "trechos": [{"citacao": h["citation"], "trecho": h["body"][:500]} for h in hits]}
