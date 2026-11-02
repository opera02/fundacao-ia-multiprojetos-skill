"""Manutenção da fundação (1.7.10; desenho 1.7.10, §5.8 e §7.1; MELHORIAS-1.7.10, §0 itens 5, 14 e 15).

- Trava de manutenção (`state/manutencao.json`: motivo, pid, host, desde): o `backup criar` trava no início e destrava
  no fim, também na falha, e o lançador do Ubuntu não abre sessão com ela. Trava que já existia (o atualizador trava o
  `aplicar` e chama o backup) não é trocada nem removida por quem não a criou.
- Última cópia (`registry/ultima-copia.json`, fundacao.ultima_copia/1): gravada pelo `backup criar` e pelo `backup
  verificar` com sucesso, por temporário e troca atômica (publicacao.publicar), em LF. Fica em registry/ para o aviso de
  início de sessão do Windows ler sem abrir state/. `situacao` junta o registro e o livro de cópias (state/copias.jsonl,
  lido com teto e sem seguir ligação) e avisa quando a última cópia passa de LIMITE_DIAS. É lembrete, não prova: quem
  grava state/ e registry/ forja os dois; a prova é o `backup verificar` com o sha256_manifesto guardado fora.
- O que a cópia leva a mais: o `.git` dos projetos, pela `RegraDaCopia` (git_na_copia.py; saiu daqui nas correções da
  revisão 1 do grupo KITCOPIA, revisão de segurança da 1.7.10), que lê aqui o teto de leitura (TETO_CONFIG). Com cara
  de segredo (a regra única de scripts/regras_de_segredo.py, NFKC e sem caixa: há teste do resultado, KIT-F6) entra
  como antes — só o `.env` fica fora — contado em `segredos_incluidos`, sem ler (`com_cara_de_segredo`).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import socket
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePath

from . import preparo, publicacao
from .ancora_copia import LIVRO_COPIAS
from .config_git import motivo_do_config  # noqa: F401 — a regra do config saiu para lá (KIT-F3)
from .contracts import FundacaoError, ValidationError
from .db import utcnow

TRAVA = PurePath("state", "manutencao.json")
ULTIMA_COPIA = PurePath("registry", "ultima-copia.json")
SCHEMA_ULTIMA_COPIA = "fundacao.ultima_copia/1"
LIMITE_DIAS = 7
_CRIAR = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)


def _ler_com_teto(arquivo: Path) -> bytes:
    from .livro_assinado import _ler  # tardio: o leitor de sempre, com teto e sem seguir ligação nem vínculo físico
    return _ler(arquivo)


def _json_do_arquivo(arquivo: Path):
    try:
        return json.loads(_ler_com_teto(arquivo))
    except (OSError, ValueError, FundacaoError) as exc:  # ligação, vínculo físico, acima do teto ou ilegível
        return {"ilegivel": type(exc).__name__}


def _data(texto) -> datetime | None:
    """Data ISO com fuso (a do `utcnow`, terminada em Z); None se não for data."""
    if not isinstance(texto, str):
        return None
    try:
        data = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    return data if data.tzinfo else data.replace(tzinfo=timezone.utc)


def _sem_ligacao(arquivo: Path) -> Path:
    ligada = preparo.ligacao_no_caminho(arquivo.parent)
    if ligada:
        raise ValidationError("o caminho passa por ligação (link simbólico ou junção): recusado", caminho=ligada)
    return arquivo


# ------------------------------------------------------------------ trava de manutenção
def ler(raiz) -> dict | None:
    """A trava em vigor; None sem trava. Trava ilegível (ligação, vínculo físico, lixo) também vale como trava."""
    arquivo = Path(raiz) / TRAVA
    if not os.path.lexists(arquivo):
        return None
    dados = _json_do_arquivo(arquivo)
    return dados if isinstance(dados, dict) else {"ilegivel": "formato"}


def travar(raiz, motivo: str) -> dict | None:
    """Grava a trava com exclusividade, sem seguir ligação, e a devolve; None se já havia trava (fica como está)."""
    arquivo = _sem_ligacao(Path(raiz) / TRAVA)
    arquivo.parent.mkdir(exist_ok=True)
    trava = {"motivo": motivo, "pid": os.getpid(), "host": socket.gethostname(), "desde": utcnow()}
    try:
        fd = os.open(arquivo, _CRIAR, 0o644)
    except FileExistsError:  # outra manutenção em andamento (ou ligação no lugar): não é desta operação
        return None
    try:
        publicacao._gravar_tudo(fd, (json.dumps(trava, ensure_ascii=False) + "\n").encode("utf-8"))
    except BaseException:
        os.close(fd)
        os.unlink(arquivo)
        raise
    os.close(fd)
    return trava


def destravar(raiz, trava: dict | None = None) -> bool:
    """Tira a trava; com `trava` (a devolvida por `travar`), só se o arquivo ainda for ela. Devolve se tirou."""
    arquivo = _sem_ligacao(Path(raiz) / TRAVA)
    if trava is not None and ler(raiz) != trava:
        return False
    try:
        os.unlink(arquivo)  # tira o nome: ligação no lugar sai como ligação
    except FileNotFoundError:
        return False
    return True


@contextmanager
def travada(raiz, motivo: str):
    """Trava durante o bloco e destrava no fim, também na falha — só a trava que o bloco criou. Se tirá-la falhar, ela
    fica (o lançador continua recusando: o lado seguro) e o motivo vai em `nao_removida` da trava entregue."""
    trava = travar(raiz, motivo)
    try:
        yield trava
    finally:
        if trava is not None:
            try:
                destravar(raiz, trava)
            except (OSError, FundacaoError) as exc:
                trava["nao_removida"] = f"{type(exc).__name__}: {exc}"


# ------------------------------------------------------------------ última cópia
def ler_ultima_copia(raiz) -> dict | None:
    """O registro da última cópia; None se não existe; {"ilegivel": ...} se não é um registro válido."""
    arquivo = Path(raiz) / ULTIMA_COPIA
    if not os.path.lexists(arquivo):
        return None
    dados = _json_do_arquivo(arquivo)
    if isinstance(dados, dict) and "ilegivel" in dados:
        return dados
    if (not isinstance(dados, dict) or dados.get("schema_version") != SCHEMA_ULTIMA_COPIA
            or _data(dados.get("criada_em")) is None):
        return {"ilegivel": "formato"}
    return dados


def registrar_copia(raiz, *, rotulo, criada_em: str, destino: str, verificada_em: str | None = None) -> None:
    """Grava registry/ultima-copia.json por temporário e troca atômica, em LF; ligação no caminho recusa."""
    arquivo = _sem_ligacao(Path(raiz) / ULTIMA_COPIA)
    registro = {"schema_version": SCHEMA_ULTIMA_COPIA, "rotulo": rotulo, "criada_em": criada_em,
                "verificada_em": verificada_em, "destino": destino}
    publicacao.publicar(arquivo, (json.dumps(registro, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def registrar_verificacao(raiz, *, rotulo, criada_em: str, destino: str) -> str:
    """Depois de um `backup verificar` com sucesso: anota `verificada_em` (a cópia verificada passa a ser a registrada),
    salvo quando ela é mais antiga que a registrada, que fica como estava. Devolve o que fez."""
    atual = ler_ultima_copia(raiz) or {}
    antes, agora = _data(atual.get("criada_em")), _data(criada_em)
    if antes and agora and antes > agora:
        return "cópia mais antiga que a registrada: registry/ultima-copia.json ficou como estava"
    registrar_copia(raiz, rotulo=rotulo, criada_em=criada_em, destino=destino, verificada_em=utcnow())
    return "verificação anotada em registry/ultima-copia.json"


def copias_do_livro(raiz) -> dict:
    """O livro de cópias (state/copias.jsonl), lido com teto e sem seguir ligação: situação, quantas cópias e a última.
    Linha ilegível não conta; entrada assinada vale pela entrada que traz (a assinatura não é conferida aqui)."""
    livro, vazio = Path(raiz) / "state" / LIVRO_COPIAS, {"entradas": 0, "ultima": None}
    if not os.path.lexists(livro):
        return {"situacao": "ausente", **vazio}
    try:
        bruto = _ler_com_teto(livro)
    except (OSError, FundacaoError) as exc:
        return {"situacao": "recusado", "motivo": f"{type(exc).__name__}: {exc}"[:200], **vazio}
    copias = {}
    for linha in bruto.decode("utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(linha)
        except ValueError:
            continue
        if isinstance(rec, dict) and isinstance(rec.get("documento"), dict):
            rec = rec["documento"].get("entrada")
        if isinstance(rec, dict) and _data(rec.get("criado_em")):
            copias[rec.get("sha256_manifesto") or rec["criado_em"]] = rec
    ultima = max(copias.values(), key=lambda r: _data(r["criado_em"]), default=None)
    return {"situacao": "lido", "entradas": len(copias), "ultima": ultima and {
        "rotulo": ultima.get("rotulo"), "criada_em": ultima["criado_em"], "destino": ultima.get("destino")}}


def situacao(raiz, agora: datetime | None = None) -> dict:
    """Idade da última cópia — a mais nova entre o registro e o livro — e o aviso quando passa de LIMITE_DIAS."""
    agora = agora or datetime.now(timezone.utc)
    livro, registro = copias_do_livro(raiz), ler_ultima_copia(raiz)
    res = {"limite_dias": LIMITE_DIAS, "livro": livro, "registro": registro, "trava_de_manutencao": ler(raiz)}
    if res["trava_de_manutencao"]:  # #3: trava de outra operação (o atualizador?) que não saiu
        res["aviso_trava"] = (f"há uma trava de manutenção desde {res['trava_de_manutencao'].get('desde')}: se a "
                              "operação dela já terminou, apague state/manutencao.json depois de conferir")
    candidatas = [c for c in (livro["ultima"], registro) if isinstance(c, dict) and _data(c.get("criada_em"))]
    if not candidatas:
        return {**res, "ultima_copia": None, "idade_dias": None, "em_dia": False,
                "aviso": "nenhuma cópia de segurança registrada nesta fundação: faça uma (comando em proxima_copia)"}
    ultima = max(candidatas, key=lambda c: _data(c["criada_em"]))
    verificada = registro.get("verificada_em") if registro is ultima or (
        isinstance(registro, dict) and registro.get("criada_em") == ultima["criada_em"]) else None
    idade = agora - _data(ultima["criada_em"])
    res.update(ultima_copia={"rotulo": ultima.get("rotulo"), "criada_em": ultima["criada_em"],
                             "destino": ultima.get("destino"), "verificada_em": verificada},
               idade_dias=max(idade.days, 0), em_dia=idade <= timedelta(days=LIMITE_DIAS))
    if not res["em_dia"]:
        res["aviso"] = (f"a última cópia de segurança tem {idade.days} dias (mais de {LIMITE_DIAS}): faça uma cópia "
                        "nova (comando em proxima_copia)")
    return res


# ------------------------------------------------------------------ segredos (e o teto da RegraDaCopia)
PASTAS_DE_SEGREDO = frozenset({".segredos", "segredos", ".secrets", "secrets", ".envs", ".ssh", ".gnupg", ".aws",
                               ".azure", ".kube", ".docker", "credentials", "_browser_profile", ".omniroute"})
NOMES_DE_SEGREDO = (".env", ".env.*", "*.pem", "*.key", "*.pfx", "*.p12", "id_rsa*", "id_ed25519*", "id_ecdsa*",
                    "id_dsa*", "*.ppk", "*.jks", "*.keystore", "*.p8", "*.ovpn", ".netrc", "_netrc", ".npmrc",
                    ".pypirc", ".pgpass", ".htpasswd", "*.tfvars", "*.tfstate*", "kubeconfig*",
                    "service-account*.json", "*credentials*", "*secret*", "auth.json", "*.kdbx", ".git-credentials")
EXEMPLOS_DE_SEGREDO = (".env.example", "*.example", "*.sample")  # fracos na regra única, mesmo casando um forte


def _normalizar(texto) -> str:
    """Como a regra única compara (regras_de_segredo.normalizar): NFKC e sem caixa (KIT-F6)."""
    return unicodedata.normalize("NFKC", str(texto)).casefold()


_PASTAS_N = frozenset(_normalizar(p) for p in PASTAS_DE_SEGREDO)
_FORTE, _EXEMPLO = (re.compile("|".join(fnmatch.translate(_normalizar(g)) for g in lista))  # um teste por arquivo
                    for lista in (NOMES_DE_SEGREDO, EXEMPLOS_DE_SEGREDO))
TETO_CONFIG = 1 << 20  # git_na_copia.RegraDaCopia: acima disto, config, commondir e .git arquivo ficam fora; o resto, cru


def com_cara_de_segredo(rel) -> bool:
    """Forte ou pasta de segredo na regra única (regras_de_segredo.classificar), pelo caminho e sem ler: as partes com /
    e \\ como separadores, em NFKC e sem caixa; pasta de segredo em qualquer parte, também a última; exemplo de segredo
    (`.env.example`, `*.sample`) não conta, como lá (revisão de segurança da 1.7.10, KIT-F6)."""
    partes = [_normalizar(p) for p in PurePath(rel).as_posix().replace("\\", "/").split("/") if p not in ("", ".")]
    if not partes:
        return False
    return any(p in _PASTAS_N for p in partes) or (not _EXEMPLO.match(partes[-1]) and bool(_FORTE.match(partes[-1])))
