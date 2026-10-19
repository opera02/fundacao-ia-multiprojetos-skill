"""Normalização de consumo entre provedores (livro A21; proposta 3.0 R1.6/R8.4).

Regras: campo ausente = "unknown" (nunca zero); contagem exata, estimativa e
faturamento observado são registros distintos; não somar subcategorias já
incluídas no total.

Fatos de formato conferidos em 18/10/2026 (ver references/fontes-verificadas.md):
- Claude (API e `claude -p --output-format json`): input_tokens NÃO inclui os
  tokens lidos/escritos em cache; entrada total = input + cache_creation + cache_read.
- Codex (`codex exec --json`, evento turn.completed): usage traz input_tokens,
  cached_input_tokens, output_tokens e reasoning_output_tokens. Que
  cached_input_tokens está contido em input_tokens foi inferido do código-fonte
  (não consta da documentação) — revalide na versão instalada.
"""

from __future__ import annotations

from typing import Any

from .contracts import SCHEMAS

UNKNOWN = "unknown"


def _get(d: dict, key: str) -> Any:
    value = d.get(key)
    return UNKNOWN if value is None else value


def normalize(provider: str, usage: dict | None, *, route: str, run_id: str,
              duration_ms: int | None = None, state: str = "succeeded",
              model: str | None = None, cost_usd: float | None = None) -> dict:
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
        "tokens": tokens,
        "duration_ms": UNKNOWN if duration_ms is None else duration_ms,
        "state": state,
        "measurement": "contador_do_provedor" if usage else "nao_observado",
        # Custo informado pelo cliente do provedor (estimativa do cliente, não fatura).
        "custo_usd": cost_usd if isinstance(cost_usd, (int, float)) else UNKNOWN,
    }


def reduction(before: float, after: float) -> float | None:
    """Redução relativa (A21): None quando a base é inválida."""
    if before <= 0:
        return None
    return 1 - after / before
