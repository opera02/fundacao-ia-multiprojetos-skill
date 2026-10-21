"""Validação da política de rotas (registry/route_policy.json) ao carregar — análise do vibe-coding-toolkit,
21/10/2026, proposta 4. Tipo errado nunca vale como outro valor: `"enabled": "false"` em texto, teto em texto,
booleano, negativo ou NaN, rota citada que não existe e chave desconhecida são problemas, e a política com
problema não vale de jeito nenhum (falha fechada, em `routing.load_policy`).

Na raiz implantada, `registry/` é configuração local, e a rota `sigiloso` pode se afastar da distribuída por decisão
do titular (proposta 5): o desvio só vale com o SHA-256 da política em registry/configuracao-decidida.json, ligado a
uma decisão que existe dentro da raiz (`desvio_sem_decisao`, conferido pela suíte de conformidade)."""

from __future__ import annotations

import json
import math
from pathlib import Path

from .canon import sha256_file

CHAVES_DA_POLITICA = {"schema_version", "titular", "observacao", "routes", "task_routes"}
CHAVES_DA_ROTA = {"enabled", "only_titular", "max_calls", "max_usd", "observacao"}
CONFIGURACAO_DECIDIDA = "configuracao-decidida.json"  # em registry/: arquivo de configuração -> hash e decisão
SCHEMA_DECIDIDA = "fundacao.configuracao_decidida/1"


def _booleano(valor) -> bool:
    return isinstance(valor, bool)


def _inteiro_nao_negativo(valor) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor >= 0


def _numero_nao_negativo(valor) -> bool:
    return (isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor)
            and valor >= 0)


def validar_politica(policy) -> list[str]:
    """Problemas da política de rotas; lista vazia = válida. Só aceita o tipo certo: texto "false",
    teto em texto, booleano no lugar de número, rota inexistente ou chave desconhecida são problemas."""
    if not isinstance(policy, dict):
        return ["a política não é um objeto JSON"]
    problemas = []
    if policy.get("schema_version") != "fundacao.route/1":
        problemas.append("schema_version desconhecido (esperado fundacao.route/1)")
    problemas += [f"chave desconhecida na política: {c}" for c in sorted(set(policy) - CHAVES_DA_POLITICA)]
    titular = policy.get("titular")
    if titular is not None and not (isinstance(titular, str) and titular.strip()):
        problemas.append("titular deve ser texto (a identidade do assinante) ou null")
    if not isinstance(policy.get("observacao", ""), str):
        problemas.append("observacao deve ser texto")
    rotas = policy.get("routes")
    if not isinstance(rotas, dict) or not rotas:
        problemas.append("routes deve ser um objeto com ao menos uma rota")
        rotas = {}
    for nome, cfg in rotas.items():
        if not isinstance(cfg, dict):
            problemas.append(f"rota {nome}: deve ser um objeto")
            continue
        problemas += [f"rota {nome}: chave desconhecida {c}" for c in sorted(set(cfg) - CHAVES_DA_ROTA)]
        for chave in ("enabled", "only_titular"):
            if not _booleano(cfg.get(chave)):
                problemas.append(f"rota {nome}: {chave} deve ser true ou false, sem aspas")
        if cfg.get("max_calls") is not None and not _inteiro_nao_negativo(cfg["max_calls"]):
            problemas.append(f"rota {nome}: max_calls deve ser inteiro maior ou igual a zero, ou null")
        if cfg.get("max_usd") is not None and not _numero_nao_negativo(cfg["max_usd"]):
            problemas.append(f"rota {nome}: max_usd deve ser número maior ou igual a zero, ou null")
        if not isinstance(cfg.get("observacao", ""), str):
            problemas.append(f"rota {nome}: observacao deve ser texto")
    ordens = policy.get("task_routes")
    if not isinstance(ordens, dict) or not ordens:
        problemas.append("task_routes deve ser um objeto com ao menos um tipo de tarefa")
        ordens = {}
    for tipo, ordem in ordens.items():
        if not isinstance(ordem, list) or not ordem or not all(isinstance(r, str) for r in ordem):
            problemas.append(f"task_routes.{tipo}: deve ser uma lista não vazia de nomes de rota")
            continue
        if len(set(ordem)) != len(ordem):
            problemas.append(f"task_routes.{tipo}: rota repetida")
        problemas += [f"task_routes.{tipo}: a rota {r} não existe em routes" for r in ordem if r not in rotas]
    return problemas


def hashes_decididos(raiz, arquivo: str) -> set[str]:
    """SHA-256 que uma decisão registrada aprova para `arquivo` (relativo à raiz), lidos de
    registry/configuracao-decidida.json. Item cuja decisão não existe dentro da raiz não conta; registro ilegível
    não aprova nada (falha fechada)."""
    raiz = Path(raiz)
    try:
        dados = json.loads((raiz / "registry" / CONFIGURACAO_DECIDIDA).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    if not isinstance(dados, dict) or dados.get("schema_version") != SCHEMA_DECIDIDA:
        return set()
    aprovados = set()
    for item in dados.get("itens") if isinstance(dados.get("itens"), list) else ():
        if not isinstance(item, dict) or item.get("arquivo") != arquivo or not isinstance(item.get("sha256"), str):
            continue
        decisao = item.get("decisao")
        rel = Path(decisao) if isinstance(decisao, str) and decisao.strip() else None
        if rel is None or rel.is_absolute() or rel.drive or rel.root or ".." in rel.parts:
            continue
        if (raiz / rel).is_file():
            aprovados.add(item["sha256"].lower())
    return aprovados


def desvio_sem_decisao(raiz) -> str | None:
    """Problema, se a rota `sigiloso` da política da raiz se afasta da distribuída sem decisão registrada; senão None."""
    from .routing import DEFAULT_POLICY, load_policy  # tardio: routing importa este módulo

    local = load_policy(raiz)["task_routes"].get("sigiloso")
    if local == DEFAULT_POLICY["task_routes"]["sigiloso"]:
        return None
    if sha256_file(Path(raiz) / "registry" / "route_policy.json") in hashes_decididos(raiz, "registry/route_policy.json"):
        return None
    return ("a rota sigilosa da política local (registry/route_policy.json) difere da distribuída e o SHA-256 dela não "
            "está ligado a uma decisão registrada em registry/" + CONFIGURACAO_DECIDIDA + ": registre a decisão "
            "(capacidade 03 da skill) ou volte à política distribuída")
