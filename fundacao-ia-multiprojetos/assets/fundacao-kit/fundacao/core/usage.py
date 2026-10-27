"""Normalização de consumo entre provedores (livro A21; proposta 3.0 R1.6/R8.4).

Regras: campo ausente = "unknown" (nunca zero); contagem exata, estimativa e
faturamento observado são registros distintos; não somar subcategorias já
incluídas no total. Custo só vale como número finito e >= 0 (conferido em
Decimal); negativo, NaN, infinito ou booleano = "unknown" (varredura 1.4.5, #17).

Fatos de formato conferidos em 18/10/2026 (ver references/fontes-verificadas.md):
- Claude (API e `claude -p --output-format json`): input_tokens NÃO inclui os
  tokens lidos/escritos em cache; entrada total = input + cache_creation + cache_read.
- Codex (`codex exec --json`, evento turn.completed): usage traz input_tokens,
  cached_input_tokens, output_tokens e reasoning_output_tokens. Que
  cached_input_tokens está contido em input_tokens foi inferido do código-fonte
  (não consta da documentação) — revalide na versão instalada.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .contracts import SCHEMAS

UNKNOWN = "unknown"


def custo_decimal(valor: Any, *, texto: bool = False) -> Decimal | None:
    """Custo em dólares como Decimal finito e >= 0, ou None (= desconhecido).

    Aceita `int`/`float` (o que o provedor ou o adaptador informa) e, com `texto=True`, o decimal em
    texto gravado na trilha. Negativo, NaN, infinito, booleano ou texto inválido = desconhecido: numa
    rota com teto de custo, desconhecido bloqueia até a administração reconciliar (falha fechada). Sem
    isso, um custo negativo reduzia o gasto acumulado e um NaN anulava a comparação com `max_usd` (#17).
    O `json` do Python aceita `NaN` e `Infinity` na saída de um provedor."""
    if isinstance(valor, bool) or not (isinstance(valor, (int, float)) or (texto and isinstance(valor, str))):
        return None
    try:
        decimal = Decimal(str(valor).strip())
    except (InvalidOperation, ValueError):
        return None
    if not decimal.is_finite() or decimal < 0:
        return None
    return decimal.copy_abs()  # -0 vira 0


def _get(d: dict, key: str) -> Any:
    value = d.get(key)
    return UNKNOWN if value is None else value


def normalize(provider: str, usage: dict | None, *, route: str, run_id: str,
              duration_ms: int | None = None, state: str = "succeeded",
              model: str | None = None, cost_usd: float | None = None,
              model_requested: str | None = None, effort_requested: str | None = None) -> dict:
    usage = usage or {}
    if provider in ("claude-cli", "claude-api"):
        parts = [usage.get("input_tokens"), usage.get("cache_creation_input_tokens"),
                 usage.get("cache_read_input_tokens")]
        input_total = sum(parts) if all(isinstance(p, int) for p in parts) else UNKNOWN
        tokens = {
            "input_total": input_total,
            "input_cached": _get(usage, "cache_read_input_tokens"),
            "cache_write": _get(usage, "cache_creation_input_tokens"),
            "output": _get(usage, "output_tokens"),
            "reasoning": UNKNOWN,
        }
    elif provider in ("codex-cli",):
        tokens = {
            "input_total": _get(usage, "input_tokens"),
            "input_cached": _get(usage, "cached_input_tokens"),
            "cache_write": UNKNOWN,
            "output": _get(usage, "output_tokens"),
            "reasoning": _get(usage, "reasoning_output_tokens"),
        }
    else:
        tokens = {k: _get(usage, k) for k in ("input_total", "input_cached", "cache_write", "output", "reasoning")}
    return {
        "schema_version": SCHEMAS["usage"],
        "run_id": run_id,
        "provider_id": provider,
        "route": route,
        "model": model or UNKNOWN,
        "model_requested": model_requested or UNKNOWN,
        "effort_requested": effort_requested or UNKNOWN,
        "tokens": tokens,
        "duration_ms": UNKNOWN if duration_ms is None else duration_ms,
        "state": state,
        "measurement": "contador_do_provedor" if usage else "nao_observado",
        # Custo informado pelo cliente do provedor (estimativa do cliente, não fatura); inválido = unknown.
        "custo_usd": cost_usd if custo_decimal(cost_usd) is not None else UNKNOWN,
    }


def reduction(before: float, after: float) -> float | None:
    """Redução relativa (A21): None quando a base é inválida."""
    if before <= 0:
        return None
    return 1 - after / before
