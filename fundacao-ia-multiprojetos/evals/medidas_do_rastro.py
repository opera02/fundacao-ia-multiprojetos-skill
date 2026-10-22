#!/usr/bin/env python3
"""Medidas de uma partida lidas do rastro do `claude -p --output-format stream-json` (apoio de livro_avaliacoes.py).

[Decisão; harness2, P1] O modelo vem do rastro, nunca da memória de quem anota: `system/init` traz o modelo e a
versão da CLI; `result`, o custo informado pelo cliente (estimativa dele, não fatura), turnos, duração, consumo e,
se presentes, os modelos usados (`modelUsage`, `model`); as mensagens `assistant` mostram os modelos que de fato
responderam. Tudo passa pela regra do kit desta skill (fundacao/core/usage.py): campo ausente = "unknown", nunca 0.
Formato conferido até a 1.7.6; confira-o na versão instalada da CLI antes de uma rodada (campo ausente vira
"unknown", não erro). Revisão de segurança da 1.7.7 (R177-VAL-08): o modelo esperado tem de ser o do `init` E o das
respostas; no `result`, só ele e os auxiliares declarados no `abrir` (`problema_de_modelo`).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

KIT_CORE = Path(__file__).resolve().parents[1] / "assets" / "fundacao-kit" / "fundacao" / "core"
UNKNOWN = "unknown"


def _uso_do_kit():
    """fundacao/core/usage.py do kit DESTA skill (nunca o de um ambiente avaliado), num pacote com nome próprio."""
    nome = "_kit_desta_skill_core"
    if f"{nome}.usage" not in sys.modules:
        pacote = importlib.util.spec_from_file_location(nome, KIT_CORE / "__init__.py",
                                                        submodule_search_locations=[str(KIT_CORE)])
        sys.modules[nome] = importlib.util.module_from_spec(pacote)
        pacote.loader.exec_module(sys.modules[nome])
        spec = importlib.util.spec_from_file_location(f"{nome}.usage", KIT_CORE / "usage.py")
        sys.modules[f"{nome}.usage"] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sys.modules[f"{nome}.usage"])
    return sys.modules[f"{nome}.usage"]


def _inteiro(valor):
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else None


def medidas_do_rastro(transcricao: Path | None, rotulo: str, estado: str) -> dict:
    """Modelo, turnos, duração, custo e consumo lidos dos eventos `system/init`, `assistant` e `result`."""
    init, resultado, modelos = {}, {}, set()
    linhas = transcricao.read_text(encoding="utf-8", errors="replace").splitlines() if transcricao else []
    for linha in linhas:
        try:
            obj = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("type") == "system" and obj.get("subtype") == "init" and not init:
            init = obj
        elif obj.get("type") == "result":
            resultado = obj
        elif obj.get("type") == "assistant" and isinstance(obj.get("message"), dict) \
                and isinstance(obj["message"].get("model"), str):
            modelos.add(obj["message"]["model"])
    modelo = init.get("model") if isinstance(init.get("model"), str) else (
        next(iter(modelos)) if len(modelos) == 1 else None)
    duracao, turnos = _inteiro(resultado.get("duration_ms")), _inteiro(resultado.get("num_turns"))
    uso = resultado.get("usage") if isinstance(resultado.get("usage"), dict) else None
    no_resultado = set(resultado["modelUsage"]) if isinstance(resultado.get("modelUsage"), dict) else set()
    no_resultado |= {resultado["model"]} if isinstance(resultado.get("model"), str) else set()
    consumo = _uso_do_kit().normalize("claude-cli", uso, route="avaliacao", run_id=rotulo, duration_ms=duracao,
                                      state=estado, model=modelo,
                                      cost_usd=resultado.get("total_cost_usd", resultado.get("cost_usd")))
    return {"modelo": modelo or UNKNOWN, "modelos_no_rastro": sorted(modelos),
            "modelos_no_resultado": sorted(str(m) for m in no_resultado),
            "turnos": UNKNOWN if turnos is None else turnos,
            "duracao_s": UNKNOWN if duracao is None else round(duracao / 1000, 1),
            "versao_cli": init["claude_code_version"] if isinstance(init.get("claude_code_version"), str) else UNKNOWN,
            "resultado_com_erro": resultado["is_error"] if isinstance(resultado.get("is_error"), bool) else UNKNOWN,
            "consumo": consumo}


def problema_de_modelo(medidas: dict, esperado: str, auxiliares=(), exige_resposta: bool = True) -> str | None:
    """Uma linha se o rastro mostra outro modelo — no `init`, nas respostas ou, além dos auxiliares declarados, no
    `result` — ou não mostra quem respondeu; None se confere. Na 1.7.7, o `init` do modelo esperado bastava, ainda
    que as respostas viessem de outro (R177-VAL-08)."""
    init, respostas = medidas.get("modelo", UNKNOWN), medidas.get("modelos_no_rastro") or []
    outros = sorted({m for m in (init, *respostas) if m not in (esperado, UNKNOWN)}
                    | {m for m in medidas.get("modelos_no_resultado") or [] if m != esperado and m not in auxiliares})
    if outros:
        return f"outro modelo, resultado não comparável — observado {', '.join(outros)}, esperado {esperado}"
    if init == UNKNOWN and not respostas:
        return f"modelo não observado no rastro (esperado {esperado})"
    if exige_resposta and not respostas:
        return f"nenhuma resposta com modelo no rastro: quem respondeu não foi observado (esperado {esperado})"
    return None
