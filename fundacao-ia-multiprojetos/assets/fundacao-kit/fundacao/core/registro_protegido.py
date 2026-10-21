"""Leitura e validação do registro protegido (`state/retiradas.jsonl`): a linha de identidade e as retiradas,
revogações e desativações que a restauração reaplica. Linha fora do formato torna o registro inteiro ilegível (a
restauração não libera). Saiu de backup.py na 1.7.4, quando o id de componente passou a ser validado antes de virar
caminho (avaliação E11, F-03); gravar, a fila de saída e a restauração seguem em backup.py, que reexporta os nomes."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .contracts import ValidationError

REGISTRO = "registro"  # tipo da linha de identidade do registro protegido
# Campos exigidos por tipo de linha (sem `entity_type` = fonte, formato gravado pela 1.1.0).
_CAMPOS = {
    "source": ("entity_id", "decided_by", "decided_at"),
    "memory": ("entity_id", "decided_by", "decided_at"),
    "acl_revoke": ("entity_id", "principal", "resource", "action", "decided_by", "decided_at"),
    "component_disable": ("entity_id", "component_id", "decided_by", "decided_at"),
}


def _ilegivel(linha: int, motivo: str) -> ValidationError:
    return ValidationError("registro de retiradas ilegível", linha=linha, motivo=motivo)


def _ler_texto(log_path: Path) -> str | None:
    path = Path(log_path)
    if not path.exists():
        return None
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise _ilegivel(0, "não é texto UTF-8") from None


def _ler_registro(log_path: Path, *, estrito: bool = False) -> tuple[str | None, list[tuple[str, dict]]]:
    """Lê e valida o registro inteiro antes de qualquer uso. Devolve a identidade e as linhas de
    retirada/revogação (texto e objeto), sem a linha de identidade. Tipo de linha desconhecido
    (gravado por um kit mais novo) só é recusado com `estrito=True` — a restauração, que precisa
    reaplicar tudo; contar linhas (backup) e preencher retiradas (init) o aceitam."""
    texto = _ler_texto(log_path)
    if texto is None:
        return None, []
    return _analisar_registro(texto, estrito=estrito)


def _id_de_componente_valido(component_id) -> bool:
    """Mesma forma do registro de componentes: o id vira nome de arquivo em registry/components/ (avaliação E11,
    F-03: com `../`, a restauração desligava um JSON fora do destino)."""
    from .components import validate_component_id  # tardio: components chega a este módulo pelo backup
    try:
        validate_component_id(component_id)
    except ValidationError:
        return False
    return True


def _analisar_registro(texto: str, *, estrito: bool = False) -> tuple[str | None, list[tuple[str, dict]]]:
    log_id, linhas = None, []
    for n, line in enumerate(texto.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            raise _ilegivel(n, "JSON inválido") from None
        if not isinstance(rec, dict):
            raise _ilegivel(n, "linha não é objeto")
        tipo = rec.get("entity_type", "source")
        if tipo == REGISTRO:
            if log_id is not None or not isinstance(rec.get("log_id"), str) or not rec["log_id"]:
                raise _ilegivel(n, "identidade repetida ou vazia")
            log_id = rec["log_id"]
            continue
        campos = _CAMPOS.get(tipo)
        if campos is None:
            if estrito or not isinstance(tipo, str) or not isinstance(rec.get("entity_id"), str):
                raise _ilegivel(n, "tipo de linha desconhecido (registro de kit mais novo? atualize o kit)")
            linhas.append((line, rec))
            continue
        if any(not isinstance(rec.get(c), str) or not rec[c] for c in campos):
            raise _ilegivel(n, "campo obrigatório ausente")
        if tipo in ("source", "memory") and not isinstance(rec.get("reason"), str):
            raise _ilegivel(n, "motivo ausente")
        if tipo == "component_disable" and not _id_de_componente_valido(rec["component_id"]):
            raise _ilegivel(n, "component_id fora do formato do registro de componentes")
        if tipo == "source" and not re.fullmatch(r".+@\d+", rec["entity_id"]):
            raise _ilegivel(n, "fonte sem versão (esperado id@versão)")
        afetadas = rec.get("affected", [])
        if tipo == "memory" and not (isinstance(afetadas, list) and all(isinstance(a, str) for a in afetadas)):
            raise _ilegivel(n, "derivados da memória em formato inválido")
        linhas.append((line, rec))
    return log_id, linhas
