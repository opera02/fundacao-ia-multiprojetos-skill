"""Seletor de rota e alternativa em caso de indisponibilidade (livro A08, A34; 3.0 R1.1).

A política (registry/route_policy.json) lista, por tipo de tarefa, as rotas em
ordem de preferência. Regras:
- rota de assinatura só para o titular declarado (se outra pessoa usa a
  fundação, ela fica desligada);
- alternativa só para destinos AUTORIZADOS na política — nunca enviar dados a
  outro provedor automaticamente;
- cada tentativa é registrada (motivo, rota, resultado); sem repetição infinita;
- erros permanentes (login ausente, entrada inválida) não são repetidos na mesma rota;
- tetos por rota (`max_calls`, `max_usd`) valem antes da chamada e contam só as tentativas
  que saíram para o provedor; custo não medido bloqueia rota com teto de custo (falha
  fechada) até a administração reconciliar o custo da tentativa (`rota custo`). Custo
  informado negativo, NaN ou infinito conta como não medido, ao gravar e ao somar (#17);
- resposta de rota simulada sai como `succeeded_simulated`, nunca como `succeeded`.
- a política é validada ao carregar e falha fechada (análise do vibe-coding-toolkit, 21/10/2026,
  proposta 4): tipo errado nunca vale como outro valor — `"enabled": "false"` em texto, teto em
  texto, booleano, negativo ou NaN, rota citada que não existe e chave desconhecida recusam a
  política inteira; o roteador só liga uma rota com `true` de verdade.
- a rota `sigiloso` que se afasta da distribuída só vale com aceite assinado do titular sobre a política exata
  (avaliação E11, F-05); sem ele, ao carregar vale a distribuída e o roteador mostra cada rota ignorada.
- com teto, a capacidade é RESERVADA numa transação curta antes do despacho e a reserva é
  finalizada por ID junto com o registro da tentativa; chamadas simultâneas não passam do
  teto, e chamada interrompida continua contando até a administração reconciliar (F10).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import events
from .auth import Policy, Principal
from .canon import sha256_bytes
from .contracts import ValidationError
from .db import transaction, utcnow
from .ids import new_id
from .gastos_rotas import route_spending, route_spending_exact, spending_report, reconcile_cost, texto_do_custo
from .modelos_tarefa import alvos_da_tarefa
from .politica_rotas import desvio_sem_decisao, validar_politica
from .usage import custo_decimal

DEFAULT_POLICY = {
    "schema_version": "fundacao.route/1",
    "titular": None,
    "routes": {
        "cli_assinatura": {"enabled": False, "only_titular": True},
        "api_creditos": {"enabled": False, "only_titular": False, "max_usd": None},
        "api_paga": {"enabled": False, "only_titular": False, "max_usd": None},
        "local": {"enabled": False, "only_titular": False},
        "simulado": {"enabled": True, "only_titular": False},
    },
    "task_routes": {
        "default": ["cli_assinatura", "api_creditos", "local", "simulado"],
        "sigiloso": ["local"],
    },
}
DESVIO_IGNORADO = "_desvio_sigiloso_ignorado"  # chave que load_policy acrescenta quando a ordem local não vale


def ler_politica(root: Path) -> tuple[dict, str | None]:
    """Política validada e o SHA-256 dos MESMOS bytes lidos (None: sem arquivo, vale a distribuída)."""
    path = Path(root) / "registry" / "route_policy.json"
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_POLICY)), None
    bruto = path.read_bytes()
    policy = json.loads(bruto.decode("utf-8"))
    problemas = validar_politica(policy)
    if problemas:
        # Falha fechada: política com problema não vale de jeito nenhum (nenhuma rota é usada).
        raise ValidationError("route_policy inválida: " + "; ".join(problemas), problemas=problemas)
    return policy, sha256_bytes(bruto)


def load_policy(root: Path, *, conferir_desvio: bool = True) -> dict:
    policy, sha = ler_politica(root)
    if sha is None:
        return policy
    motivo = desvio_sem_decisao(root, policy, sha) if conferir_desvio else None
    if motivo:
        # Falha fechada para o sigilo (avaliação E11, F-05): sem aceite assinado, a ordem local não vale.
        policy[DESVIO_IGNORADO] = {"ordem_local": policy["task_routes"]["sigiloso"], "motivo": motivo}
        policy["task_routes"]["sigiloso"] = list(DEFAULT_POLICY["task_routes"]["sigiloso"])
    return policy


class Router:
    def __init__(self, con: sqlite3.Connection, principal: Principal, policy: dict,
                 adapters: dict[str, object]):
        self.con = con
        self.principal = principal
        self.policy = policy
        self.adapters = adapters  # rota -> adaptador

    def _gasto_da_rota(self, route: str) -> tuple[float, int, list[str]]:
        return route_spending_exact(self.con, route)

    def candidate_routes(self, task_kind: str) -> list[tuple[str, str]]:
        """[(rota, motivo_de_exclusao_ou_'ok')]"""
        order = self.policy["task_routes"].get(task_kind)
        if order is None:
            # Falha fechada: tipo de tarefa sem rota declarada não herda a rota padrão.
            raise ValidationError("tipo de tarefa sem rotas declaradas na política", task_kind=task_kind)
        out = []
        for route in order:
            cfg = self.policy["routes"].get(route)
            if cfg is None or cfg.get("enabled") is not True:  # texto "false" ou 1 não ligam a rota
                out.append((route, "rota desabilitada na política"))
            elif cfg.get("only_titular") and self.principal.principal_id != self.policy.get("titular"):
                out.append((route, "rota restrita ao titular"))
            elif route not in self.adapters and not any(isinstance(k, tuple) and k[0] == route for k in self.adapters):
                out.append((route, "adaptador não configurado"))
            else:
                motivo = self._teto(route, cfg)
                out.append((route, motivo or "ok"))
        ignorado = self.policy.get(DESVIO_IGNORADO) if task_kind == "sigiloso" else None
        for route in (ignorado or {}).get("ordem_local", []):
            if route not in order:
                out.append((route, "desvio da rota sigilosa sem decisão assinada: ignorado"))
        return out

    def _teto(self, route: str, cfg: dict) -> str | None:
        """Tetos declarados na política valem ANTES da chamada (sem teto = sem limite declarado)."""
        if cfg.get("max_calls") is None and cfg.get("max_usd") is None:
            return None
        gasto, chamadas, pendentes = self._gasto_da_rota(route)
        if cfg.get("max_calls") is not None and chamadas >= cfg["max_calls"]:
            return "teto de chamadas da rota atingido"
        if cfg.get("max_usd") is not None:
            teto = custo_decimal(cfg["max_usd"])
            if teto is None:  # NaN ou negativo anulariam a comparação abaixo
                return "teto de custo inválido na política: rota bloqueada"
            if pendentes:
                return "custo de chamada anterior não medido: teto não verificável"
            if gasto >= teto:
                return "teto de custo da rota atingido"
        return None

    def _reservar(self, route: str, cfg: dict, request) -> tuple[str | None, str | None]:
        """Reserva a capacidade da rota numa transação CURTA, antes do despacho (BEGIN IMMEDIATE
        serializa entre conexões e processos): a verificação do teto conta as chamadas registradas e
        as reservas em andamento. A transação fecha antes da chamada externa (auditoria F10)."""
        with transaction(self.con):
            motivo = self._teto(route, cfg)
            if motivo:
                return None, motivo
            reserva = new_id("rsv")
            self.con.execute(
                "INSERT INTO route_reservation (reservation_id, route, project_id, subject, state, created_at)"
                " VALUES (?,?,?,?,?,?)",
                (reserva, route, request.project_id, self.principal.principal_id, "reserved", utcnow()))
        return reserva, None

    def _registrar(self, route: str, request, *, provider_id: str, state: str, simulated: bool,
                   dispatched: bool, custo, reserva: str | None, model: str = "unknown") -> str:
        """Tentativa registrada e reserva finalizada NA MESMA transação; finalização idempotente por ID
        (`AND state = 'reserved'`): repetir não conta duas vezes. Custo inválido (negativo, NaN,
        infinito, booleano) é gravado como não medido: a rota com teto fica bloqueada até reconciliar."""
        custo = custo_decimal(custo)
        with transaction(self.con):
            evento = events.emit(self.con, "provider_attempt", project_id=request.project_id,
                                 subject=self.principal.principal_id, run_id=request.run_id,
                                 payload={"route": route, "provider_id": provider_id, "state": state,
                                          "simulated": simulated, "dispatched": dispatched,
                                          "model": model, "model_requested": request.model or "unknown",
                                          "effort_requested": request.effort or "unknown",
                                          "cost_usd": texto_do_custo(custo) if custo is not None else None,
                                          **({"reservation_id": reserva} if reserva else {})})
            if reserva:
                self.con.execute(
                    "UPDATE route_reservation SET state = ?, finalized_at = ?, attempt_event_id = ?"
                    " WHERE reservation_id = ? AND state = 'reserved'",
                    ("released" if dispatched is False else "finalized", utcnow(), evento, reserva))
        return evento

    def call(self, task_kind: str, request) -> dict:
        attempts = []
        motivos = dict(self.candidate_routes(task_kind))
        for route, adapter, pedido in alvos_da_tarefa(self.policy, task_kind, self.adapters, request):
            reason = motivos.get(route, "rota não autorizada")
            if reason != "ok":
                attempts.append({"route": route, "skipped": reason})
                continue
            if adapter is None:
                attempts.append({"route": route, "skipped": "provedor não configurado"})
                continue
            cfg = self.policy["routes"].get(route) or {}
            # /1 e /2: saldo contábil não substitui o mecanismo preventivo por chamada.
            # O mecanismo da CLI usa estimativa do cliente; não garante fatura máxima.
            if cfg.get("max_usd") is not None and not hasattr(adapter, "max_budget_usd"):
                attempts.append({"route": route, "skipped": "provedor sem teto financeiro por chamada verificável"})
                continue
            reserva = None
            if cfg.get("max_calls") is not None or cfg.get("max_usd") is not None:
                reserva, motivo = self._reservar(route, cfg, request)
                if reserva is None:  # outra chamada levou a capacidade entre a triagem e a reserva
                    attempts.append({"route": route, "skipped": motivo})
                    continue
            if cfg.get("max_usd") is not None and hasattr(adapter, "max_budget_usd"):
                adapter.max_budget_usd = custo_decimal(cfg["max_usd"]) - self._gasto_da_rota(route)[0]
            try:
                result = adapter.call(pedido)
            except BaseException:
                if reserva:
                    # Desfecho desconhecido: conta como chamada que saiu, com custo não medido (falha
                    # fechada); a administração reconcilia pelo `rota custo`.
                    self._registrar(route, pedido, provider_id="desconhecido", state="interrompida",
                                    simulated=False, dispatched=True, custo=None, reserva=reserva)
                raise
            custo = (result.usage or {}).get("custo_usd")
            attempts.append({"route": route, "state": result.state, "simulated": result.simulated})
            self._registrar(route, pedido, provider_id=result.provider_id, state=result.state,
                            simulated=result.simulated, dispatched=result.dispatched, custo=custo, reserva=reserva,
                            model=result.model)
            if result.state == "succeeded":
                # Simulação nunca vira "sucesso" indistinto: o estado diz que foi simulada.
                estado = "succeeded_simulated" if result.simulated else "succeeded"
                return {"state": estado, "result": result, "attempts": attempts}
            # Falha nesta rota: segue para a próxima AUTORIZADA, sem repetir a mesma.
        events.emit(self.con, "provider_blocked", project_id=request.project_id, run_id=request.run_id,
                    payload={"attempts": attempts})
        return {"state": "blocked", "result": None, "attempts": attempts}
