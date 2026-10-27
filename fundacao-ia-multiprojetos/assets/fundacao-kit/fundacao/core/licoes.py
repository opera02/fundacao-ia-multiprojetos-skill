"""Contrato estruturado de lições: dado do projeto, sujeito à revisão humana.

O corpo canônico é o conteúdo aprovado pelo hash da MemoryService. O índice
FTS5 é só um derivado: a consulta sempre reconfere escopo, revisão e retirada.
Não identifica nem remove automaticamente fatos sensíveis; a revisão humana
deve conferir a abstração do gatilho e da lição antes de aprovar.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from .canon import canonical_json
from .contracts import ValidationError
from .db import utcnow

SCHEMA_VERSION = "fundacao.memory.licao/1"
CONFIANCAS = frozenset({"alta", "media", "baixa"})
_CAMPOS = frozenset({"schema_version", "gatilho", "licao", "evidencia", "confianca"})


def validar(body: str, source_ref: str) -> dict:
    def sem_duplicatas(pares):
        out = {}
        for chave, valor in pares:
            if chave in out:
                raise ValidationError("campo duplicado na lição")
            out[chave] = valor
        return out
    try:
        dados = json.loads(body, object_pairs_hook=sem_duplicatas)
    except (ValueError, TypeError) as exc:
        raise ValidationError("lição exige objeto JSON estruturado") from exc
    if not isinstance(dados, dict) or set(dados) != _CAMPOS:
        raise ValidationError("campos da lição inválidos; informe schema_version, gatilho, licao, evidencia e confianca")
    if dados["schema_version"] != SCHEMA_VERSION:
        raise ValidationError("schema_version de lição não suportado")
    for campo in ("gatilho", "licao", "evidencia", "confianca"):
        valor = dados[campo]
        if not isinstance(valor, str) or not valor.strip() or valor != valor.strip():
            raise ValidationError("campo de lição vazio ou inválido", campo=campo)
    if dados["confianca"] not in CONFIANCAS:
        raise ValidationError("confiança deve ser alta, media ou baixa")
    if dados["evidencia"] != source_ref:
        raise ValidationError("evidencia deve coincidir com source_ref")
    return dados


def serializar(*, gatilho: str, licao: str, evidencia: str, confianca: str) -> str:
    dados = {"schema_version": SCHEMA_VERSION, "gatilho": gatilho, "licao": licao,
             "evidencia": evidencia, "confianca": confianca}
    body = canonical_json(dados)
    validar(body, evidencia)
    return body


def validar_proposta(kind, scope, project_id, case_id, body, source_ref, effective_from):
    if kind != "licao":
        return None
    if scope != "project" or not project_id or case_id is not None:
        raise ValidationError("lição pertence somente ao projeto, sem case_id")
    dados = validar(body, source_ref)
    if effective_from is not None:
        instante(effective_from)
    return dados


def instante(valor: str) -> datetime:
    try:
        data = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        if data.tzinfo is None:
            raise ValueError("fuso ausente")
        return data.astimezone(timezone.utc)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValidationError("vigência exige data ISO 8601 com fuso") from exc


def vigente(row, agora=None):
    return (row["kind"] != "licao" or row["effective_from"] is None
            or instante(row["effective_from"]) <= (agora or instante(utcnow())))


def expressao_fts(gatilho: str) -> str | None:
    """Termos literais em AND; texto do usuário nunca vira linguagem do FTS."""
    if not isinstance(gatilho, str) or not gatilho.strip():
        raise ValidationError("informe o gatilho da consulta")
    termos = re.findall(r"[^\W_]+", gatilho, flags=re.UNICODE)
    return " AND ".join('"' + termo + '"' for termo in termos) or None


def indexar(con, memory_id: str, revision: int, project_id: str | None, dados: dict | None) -> None:
    if dados is None:
        return
    con.execute("INSERT INTO lesson_trigger(memory_id,revision,project_id,gatilho) VALUES (?,?,?,?)",
                (memory_id, revision, project_id, dados["gatilho"]))
