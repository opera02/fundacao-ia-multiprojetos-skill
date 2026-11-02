"""Trava do banco entre o Windows e o Ubuntu (1.7.10; contratos do lote 2, §4; crítica do desenho, lente de
viabilidade, "trava global do banco").

A regra de AGENTS.md — o banco `state/state.sqlite` nunca é aberto pelo Windows e pelo WSL ao mesmo tempo — passa a ser
conferida, não só seguida:
- Marcador `state/banco.trava`, JSON com `lado` ("windows" ou "ubuntu"), `host`, `pid`, `desde` e `renovada_em`, gravado
  por quem segura o banco por tempo longo: o porteiro do Ubuntu (`assets/host/wsl/porteiro.py`), do início ao fim da
  sessão do projeto, renovado a cada RENOVAR_S segundos e com `flock` entre os porteiros (vários projetos abertos).
- `conferir`, chamada por `core/db.py` ao abrir o banco: marcador do OUTRO lado recusa (`BancoTravado`), vivo ou velho;
  marcador do mesmo lado, ou nenhum, não muda nada (quem abre do mesmo lado continua como antes). Marcador ilegível
  (ligação, outro tipo de arquivo, acima do teto, fora da forma) também recusa: não se sabe de que lado ele é.
- Marcador velho (sem renovação há mais de VIVO_S segundos) não sai sozinho, nunca em silêncio: só pelo comando
  explícito do titular, `python -m fundacao banco destravar --confirmar`, que recusa o marcador ainda vivo.
Limites (registre sempre): no Windows o kit só confere — os comandos curtos do coordenador não gravam marcador, e o
porteiro não os vê; a trava de manutenção (`state/manutencao.json`) cobre o backup e a atualização. O marcador é um
arquivo comum da raiz: quem grava `state/` o forja ou o apaga. É guarda-corpo contra o engano, não barreira contra uma
sessão tomada; com a raiz em /mnt/e, onde o sandbox não confinou os comandos nas sondas de 31/10/2026, um comando da
sessão do Ubuntu ainda alcança o banco por fora do porteiro (camada lógica, até o canário passar no ambiente real).
"""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

from .contracts import FundacaoError, ValidationError

MARCADOR = "banco.trava"  # na pasta do banco (state/)
LADOS = ("windows", "ubuntu")
CAMPOS = ("lado", "host", "pid", "desde", "renovada_em")
VIVO_S = 120    # renovado há menos que isto: vivo (o porteiro renova a cada RENOVAR_S)
RENOVAR_S = 30
TETO = 4096     # bytes: o marcador é pequeno; maior que isto não é marcador
_SUBSTITUTA_DE_NOME = 0x20000000  # Windows: junção, link simbólico e afins (bit 29 da etiqueta de reparse)
_LER = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)


class BancoTravado(FundacaoError):
    """O banco está (ou pode estar) em uso pelo outro lado: não abre. Sai pelo contrato da CLI (código 2)."""

    code = "E_BANCO_TRAVADO"


def lado_desta_maquina() -> str:
    return "windows" if os.name == "nt" else "ubuntu"


def _data(texto) -> datetime | None:
    if not isinstance(texto, str):
        return None
    try:
        data = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    return data if data.tzinfo else data.replace(tzinfo=timezone.utc)


def valido(marcador) -> bool:
    """O marcador na forma do contrato: os cinco campos, o lado conhecido, o pid inteiro e as duas datas."""
    return (isinstance(marcador, dict) and set(marcador) == set(CAMPOS) and marcador["lado"] in LADOS
            and isinstance(marcador["host"], str) and type(marcador["pid"]) is int
            and _data(marcador["desde"]) is not None and _data(marcador["renovada_em"]) is not None)


def ler(pasta) -> dict | None:
    """O marcador da pasta do banco; None sem marcador; {"ilegivel": motivo} quando não dá para confiar no que há ali
    (ligação, outro tipo de arquivo, vínculo físico, acima do teto, fora da forma). Não segue ligação."""
    arquivo = Path(pasta) / MARCADOR
    try:
        antes = os.lstat(arquivo)
    except FileNotFoundError:
        return None
    except OSError as exc:
        return {"ilegivel": type(exc).__name__}
    if (stat.S_ISLNK(antes.st_mode) or getattr(antes, "st_reparse_tag", 0) & _SUBSTITUTA_DE_NOME
            or not stat.S_ISREG(antes.st_mode)):
        return {"ilegivel": "não é arquivo comum (ligação ou outro tipo)"}
    if antes.st_nlink != 1 or antes.st_size > TETO:
        return {"ilegivel": "vínculo físico ou acima do teto"}
    try:
        fd = os.open(arquivo, _LER)
        try:
            dados = os.read(fd, TETO + 1)
        finally:
            os.close(fd)
        marcador = json.loads(dados.decode("utf-8"))
    except (OSError, ValueError) as exc:  # some no meio, ligação no lugar, lixo ou outro código
        return {"ilegivel": type(exc).__name__}
    return marcador if valido(marcador) else {"ilegivel": "fora da forma do marcador"}


def idade_s(marcador: dict | None, agora: datetime | None = None) -> float | None:
    """Segundos desde a última renovação; None sem marcador legível."""
    if not marcador or "ilegivel" in marcador:
        return None
    return ((agora or datetime.now(timezone.utc)) - _data(marcador["renovada_em"])).total_seconds()


def situacao(marcador: dict | None, agora: datetime | None = None) -> str:
    """"ausente", "ilegivel", "vivo" (renovado há menos de VIVO_S segundos) ou "velho"."""
    if marcador is None:
        return "ausente"
    if "ilegivel" in marcador:
        return "ilegivel"
    return "vivo" if idade_s(marcador, agora) < VIVO_S else "velho"


def _comando_destravar(pasta: Path) -> str:
    return f'python -m fundacao --raiz "{Path(pasta).parent}" banco destravar --confirmar'


def _recusa(pasta: Path, marcador: dict, lado: str, agora: datetime | None) -> BancoTravado:
    arquivo = Path(pasta) / MARCADOR
    s = situacao(marcador, agora)
    if s == "ilegivel":
        return BancoTravado(f"o marcador {arquivo} existe e não é legível ({marcador['ilegivel']}): o banco não abre "
                            "sem saber de que lado ele está em uso. Confira-o à mão; se nada usa o banco, o titular o "
                            f"tira com: {_comando_destravar(pasta)}", situacao=s)
    detalhes = {k: marcador[k] for k in CAMPOS}
    idade = round(idade_s(marcador, agora) or 0)
    if s == "vivo":
        return BancoTravado(f"o banco está em uso pelo {marcador['lado']} (host {marcador['host']}, pid "
                            f"{marcador['pid']}, desde {marcador['desde']}, renovado há {idade} s): feche o que o usa "
                            f"lá (no Ubuntu, as sessões de projeto) antes de abri-lo pelo {lado}", situacao=s,
                            **detalhes)
    return BancoTravado(f"há um marcador antigo do {marcador['lado']} (host {marcador['host']}, sem renovação há "
                        f"{idade} s): se nada usa o banco lá — feche as sessões e confira —, o titular o tira com: "
                        f"{_comando_destravar(pasta)}", situacao=s, **detalhes)


def conferir(pasta, *, lado: str | None = None, agora: datetime | None = None) -> None:
    """Chamada ao abrir o banco da pasta `pasta` (state/): recusa com marcador do outro lado ou ilegível. Sem marcador,
    ou com o do mesmo lado, não faz nada."""
    marcador = ler(pasta)
    if marcador is None:
        return
    lado = lado or lado_desta_maquina()
    if "ilegivel" not in marcador and marcador["lado"] == lado:
        return
    raise _recusa(Path(pasta), marcador, lado, agora)


def descrever(pasta, agora: datetime | None = None) -> dict:
    """`banco situacao`: o marcador e a situação dele, sem abrir o banco nem exigir identidade."""
    marcador = ler(pasta)
    s = situacao(marcador, agora)
    res = {"marcador": str(Path(pasta) / MARCADOR), "situacao": s, "lado_desta_maquina": lado_desta_maquina(),
           "vivo_ate_s": VIVO_S}
    if marcador is not None:
        res["conteudo"] = marcador
        res["renovado_ha_s"] = idade_s(marcador, agora)
        if s in ("velho", "ilegivel"):
            res["para_o_titular"] = _comando_destravar(Path(pasta))
    return res


def destravar(pasta, *, confirmar: bool, agora: datetime | None = None) -> dict:
    """Comando explícito do titular: tira o marcador velho ou ilegível, só com `confirmar`. Marcador vivo (ainda
    renovado por quem segura o banco) é recusado: feche a sessão de lá primeiro. Sem marcador, nada a fazer."""
    pasta = Path(pasta)
    marcador = ler(pasta)
    s = situacao(marcador, agora)
    if marcador is None:
        return {"removido": False, "situacao": s, "mensagem": "não há marcador: o banco não está travado"}
    if s == "vivo":
        raise BancoTravado(f"o marcador ainda é renovado pelo {marcador['lado']} (pid {marcador['pid']}, há "
                           f"{round(idade_s(marcador, agora) or 0)} s): feche a sessão de lá; ele sai sozinho quando o "
                           "porteiro termina", situacao=s)
    if not confirmar:
        raise ValidationError("confirme que nada usa o banco do outro lado (sessões do Ubuntu fechadas) e repita com "
                              "--confirmar", situacao=s, conteudo=marcador)
    try:
        os.unlink(pasta / MARCADOR)  # tira o nome: ligação no lugar sai como ligação, sem tocar o destino
    except FileNotFoundError:
        return {"removido": False, "situacao": "ausente", "mensagem": "o marcador já tinha saído"}
    return {"removido": True, "situacao": s, "marcador_removido": marcador}


def executar(pasta, acao: str, *, confirmar: bool = False) -> dict:
    """`python -m fundacao banco situacao|destravar [--confirmar]` (a CLI entrega a pasta state/ da raiz)."""
    if acao == "destravar":
        return destravar(pasta, confirmar=confirmar)
    if acao == "situacao":
        return descrever(pasta)
    raise ValidationError("ação do banco desconhecida", acao=acao)
