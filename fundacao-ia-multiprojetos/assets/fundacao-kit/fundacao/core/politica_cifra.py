"""Política da cópia cifrada (1.7.11; desenho DESENHO-COPIA-CIFRADA-1.7.11, lote 3): quando o `backup criar` cifra, de onde
vem a chave pública e os avisos de `backup situacao`.

- A chave pública da cópia fica na âncora protegida, ao lado do `allowed_signers` das decisões (C:\\ProgramData\\FundacaoIA\\
  confianca\\chave-da-copia.asc; no WSL, a mesma pelo /mnt/c). É a PRESENÇA dela que liga a cifra, e só administrador a tira:
  a política não fica em registry/, que a sessão grava. Não há opção para informar outra chave.
- Chave instalada e protegida: `backup criar` cifra. Chave instalada e NÃO protegida (gravável por esta conta, ligação no
  caminho...): recusa, sem gravar cópia em claro em silêncio. `--sem-cifra "<motivo>"` grava a cópia em claro de
  qualquer jeito; o motivo vai no livro e em registry/ultima-copia.json, e `situacao` avisa W_COPIA_EM_CLARO. Sem chave
  instalada, tudo como antes da 1.7.11 (a cópia em claro de hoje).
- `situacao` lê o registro das conferências com senha (conferencias-copia.jsonl, gravado pela ferramenta do titular na
  pasta de dados do perfil) e avisa W_CONTEUDO_NAO_CONFERIDO passados 35 dias sem uma conferência boa. É lembrete, não prova.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import decisoes, manutencao
from .comando_titular import _aspas_bash, _aspas_powershell
from .contracts import FundacaoError, ValidationError

CHAVE_WINDOWS = r"C:\ProgramData\FundacaoIA\confianca\chave-da-copia.asc"
CHAVE_WSL = "/mnt/c/ProgramData/FundacaoIA/confianca/chave-da-copia.asc"
CHAVE_POSIX = "/etc/fundacao-ia/confianca/chave-da-copia.asc"
CHAVES_PADRAO = (CHAVE_WINDOWS,) if os.name == "nt" else (CHAVE_WSL, CHAVE_POSIX)
CONFERENCIAS = "conferencias-copia.jsonl"
LIMITE_CONFERENCIA_DIAS = 35


def chave_instalada() -> Path | None:
    """A chave pública da cópia no lugar fixo desta máquina, se existir."""
    return next((Path(c) for c in CHAVES_PADRAO if Path(c).is_file()), None)


def protegida(caminho: Path) -> dict:
    """A sondagem da âncora das decisões (dono e direitos de cada ponto do caminho) aplicada à chave pública."""
    try:
        return decisoes.conferir_ancora(caminho)
    except (OSError, UnicodeDecodeError) as exc:
        return {"protegida": False, "motivo": f"a chave não pôde ser sondada ({type(exc).__name__})"}


def decidir(sem_cifra: str | None) -> dict:
    """{"modo": "cifrada" | "claro", "chave": caminho ou None, "sem_cifra": motivo, "conferencia": ...}; ValidationError se
    a chave está instalada mas não protegida (e não há --sem-cifra) ou se o motivo veio vazio."""
    motivo = sem_cifra.strip() if isinstance(sem_cifra, str) else ""
    if sem_cifra is not None and not motivo:
        raise ValidationError("--sem-cifra exige o motivo (ele fica no livro e no registro da última cópia)")
    chave = chave_instalada()
    if chave is None:
        return {"modo": "claro", "chave": None}
    if motivo:
        return {"modo": "claro", "chave": chave, "sem_cifra": motivo}
    return {"modo": "cifrada", "chave": chave, "conferencia": _exigir_protegida(chave)}


def _exigir_protegida(chave: Path) -> dict:
    conferencia = protegida(chave)
    if not conferencia.get("protegida"):
        raise ValidationError(
            f"a chave pública da cópia ({chave}) não está protegida como âncora ({conferencia.get('motivo')}): nenhuma "
            "cópia foi feita, nem em claro. Peça ao titular para reinstalá-la (preparar-maquina.ps1 -ChaveDaCopia, no UAC) "
            "ou, sabendo o risco, use --sem-cifra \"<motivo>\" para uma cópia em claro", chave=str(chave))
    return conferencia


def exigir_chave() -> Path:
    """A chave pública instalada e protegida, para `backup cifrar`; sem ela, ValidationError."""
    chave = chave_instalada()
    if chave is None:
        raise ValidationError("a chave pública da cópia não está instalada na âncora protegida (" + " ou ".join(CHAVES_PADRAO)
                              + "): peça ao titular para criá-la (preparar-chave-copia) e instalá-la no UAC")
    _exigir_protegida(chave)
    return chave


def comando_do_titular(acao: str, origem, destino=None) -> str:
    """Comando pronto da ferramenta do titular (`conferir-copia`, `decifrar-copia`), no shell desta máquina."""
    aspas, python = (_aspas_powershell, "python") if os.name == "nt" else (_aspas_bash, "python3")
    ferramenta = Path.home() / ".claude" / "skills" / "fundacao-ia-multiprojetos" / "assets" / "host" / "fundacao_titular.py"
    resto = (f" --destino {aspas(str(destino))} --sha256-manifesto {aspas('<sha256_manifesto que o backup criar devolveu>')}"
             if destino else "")  # o decifrar-copia exige a âncora que o titular guardou fora (revisão da 1.7.11, F7)
    return f"{python} -I -B -S {aspas(str(ferramenta))} {acao} --origem {aspas(str(origem))}{resto}"


def pasta_de_dados() -> Path:
    base = os.environ.get("LOCALAPPDATA") if os.name == "nt" else os.environ.get("XDG_DATA_HOME")
    return Path(base) if base else Path.home() / ".local" / "share"


def ler_conferencias(arquivo: Path | None = None) -> list[dict]:
    """As conferências com senha registradas pela ferramenta do titular ({"conferida_em", "ok", ...}); lido com teto e
    sem seguir ligação; linha ilegível não conta."""
    arquivo = arquivo or pasta_de_dados() / "FundacaoIA" / CONFERENCIAS
    try:
        bruto = manutencao._ler_com_teto(arquivo)
    except (OSError, FundacaoError):
        return []
    saida = []
    for linha in bruto.decode("utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(linha)
        except ValueError:
            continue
        if isinstance(rec, dict) and manutencao._data(rec.get("conferida_em")):
            saida.append(rec)
    return saida


def avisos(res: dict, *, chave_instalada: bool, conferencias: list[dict], agora: datetime | None = None) -> list[dict]:
    """W_COPIA_EM_CLARO e W_CONTEUDO_NAO_CONFERIDO para a resposta de `backup situacao` (`res` é o de manutencao.situacao)."""
    agora, ultima, saida = agora or datetime.now(timezone.utc), res.get("ultima_copia"), []
    if not ultima:
        return saida
    if not ultima.get("cifrada") and (chave_instalada or ultima.get("sem_cifra")):
        porque = f" Motivo registrado: {ultima['sem_cifra']}." if ultima.get("sem_cifra") else ""
        saida.append({"code": "W_COPIA_EM_CLARO", "message": (
            "a última cópia de segurança está em claro (sem cifra) e a fundação tem a chave da cópia instalada." + porque +
            " Rode `backup criar` sem --sem-cifra para cifrar.")})
    primeira = res["livro"].get("primeira_cifrada") or (ultima["criada_em"] if ultima.get("cifrada") else None)
    if primeira:
        boas = [manutencao._data(c["conferida_em"]) for c in conferencias if c.get("ok") is True]
        referencia = max([manutencao._data(primeira), *boas])
        if agora - referencia > timedelta(days=LIMITE_CONFERENCIA_DIAS):
            saida.append({"code": "W_CONTEUDO_NAO_CONFERIDO", "message": (
                f"faz mais de {LIMITE_CONFERENCIA_DIAS} dias que o conteúdo de uma cópia cifrada não é conferido com a senha "
                "(o `backup verificar` só vê as partes, não o que há dentro). O titular confere em 5 minutos: " +
                comando_do_titular("conferir-copia", ultima.get("destino") or "<pasta da última cópia>"))})
    return saida
