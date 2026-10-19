"""Provedor SIMULADO, claramente rotulado (simulated=True, route='simulado').

Serve para testar contrato, falhas, orçamento e retomada sem custo. Nunca
comprova a participação de um provedor real (livro A08, A36).
"""

from __future__ import annotations

from ..core.canon import sha256_text
from .base import ProviderRequest, ProviderResult, Timer


class SimulatedProvider:
    route = "simulado"

    def __init__(self, provider_id: str = "simulado-a", *, fail_with: str | None = None,
                 invalid_output: bool = False):
        self.provider_id = provider_id
        self.fail_with = fail_with
        self.invalid_output = invalid_output
        self.calls = 0

    def call(self, request: ProviderRequest) -> ProviderResult:
        self.calls += 1
        with Timer() as t:
            if self.fail_with:
                state, text = self.fail_with, ""
            elif self.invalid_output:
                state, text = "invalid_output", "{saida-quebrada"
            else:
                ids = ", ".join(item["id"] for item in request.context) or "nenhum dado"
                state = "succeeded"
                text = f"[SIMULADO {self.provider_id}] objetivo recebido; dados citados: {ids}"
        return ProviderResult(
            provider_id=self.provider_id, route=self.route, state=state, text=text,
            model="simulado", call_id="sim-" + sha256_text(request.run_id + str(self.calls))[:12],
            duration_ms=t.ms, usage={}, simulated=True,
        )
