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
  fechada) até a administração reconciliar o custo da tentativa (`rota custo`);
- resposta de rota simulada sai como `succeeded_simulated`, nunca como `succeeded`.
- com teto, a capacidade é RESERVADA numa transação curta antes do despacho e a reserva é
  finalizada por ID junto com o registro da tentativa; chamadas simultâneas não passam do
  teto, e chamada interrompida continua contando até a administração reconciliar (F10).
"""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path

from . import events
from .auth import Policy, Principal
from .contracts import ValidationError
from .db import transaction, utcnow
from .ids import new_id

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


def load_policy(root: Path) -> dict:
    path = Path(root) / "registry" / "route_policy.json"
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_POLICY))
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("schema_version") != "fundacao.route/1":
        raise ValidationError("route_policy com schema_version desconhecido")
    return policy


class Router:
    def __init__(self, con: sqlite3.Connection, principal: Principal, policy: dict,
                 adapters: dict[str, object]):
        self.con = con
        self.principal = principal
        self.policy = policy
        self.adapters = adapters  # rota -> adaptador

    def _gasto_da_rota(self, route: str) -> tuple[float, int, list[str]]:
        return route_spending(self.con, route)

    def candidate_routes(self, task_kind: str) -> list[tuple[str, str]]:
        """[(rota, motivo_de_exclusao_ou_'ok')]"""
        order = self.policy["task_routes"].get(task_kind)
        if order is None:
            # Falha fechada: tipo de tarefa sem rota declarada não herda a rota padrão.
            raise ValidationError("tipo de tarefa sem rotas declaradas na política", task_kind=task_kind)
        out = []
        for route in order:
            cfg = self.policy["routes"].get(route)
            if cfg is None or not cfg.get("enabled"):
                out.append((route, "rota desabilitada na política"))
            elif cfg.get("only_titular") and self.principal.principal_id != self.policy.get("titular"):
                out.append((route, "rota restrita ao titular"))
            elif route not in self.adapters:
                out.append((route, "adaptador não configurado"))
            else:
                motivo = self._teto(route, cfg)
                out.append((route, motivo or "ok"))
        return out

    def _teto(self, route: str, cfg: dict) -> str | None:
        """Tetos declarados na política valem ANTES da chamada (sem teto = sem limite declarado)."""
        if cfg.get("max_calls") is None and cfg.get("max_usd") is None:
            return None
        gasto, chamadas, pendentes = self._gasto_da_rota(route)
        if cfg.get("max_calls") is not None and chamadas >= cfg["max_calls"]:
            return "teto de chamadas da rota atingido"
        if cfg.get("max_usd") is not None:
            if pendentes:
                return "custo de chamada anterior não medido: teto não verificável"
            if gasto >= cfg["max_usd"]:
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
                   dispatched: bool, custo, reserva: str | None) -> str:
        """Tentativa registrada e reserva finalizada NA MESMA transação; finalização idempotente por ID
        (`AND state = 'reserved'`): repetir não conta duas vezes."""
        with transaction(self.con):
            evento = events.emit(self.con, "provider_attempt", project_id=request.project_id,
                                 subject=self.principal.principal_id, run_id=request.run_id,
                                 payload={"route": route, "provider_id": provider_id, "state": state,
                                          "simulated": simulated, "dispatched": dispatched,
                                          "cost_usd": f"{custo:.6f}" if isinstance(custo, (int, float)) else None,
                                          **({"reservation_id": reserva} if reserva else {})})
            if reserva:
                self.con.execute(
                    "UPDATE route_reservation SET state = ?, finalized_at = ?, attempt_event_id = ?"
                    " WHERE reservation_id = ? AND state = 'reserved'",
                    ("released" if dispatched is False else "finalized", utcnow(), evento, reserva))
        return evento

    def call(self, task_kind: str, request) -> dict:
        attempts = []
        for route, reason in self.candidate_routes(task_kind):
            if reason != "ok":
                attempts.append({"route": route, "skipped": reason})
                continue
            adapter = self.adapters[route]
            cfg = self.policy["routes"].get(route) or {}
            reserva = None
            if cfg.get("max_calls") is not None or cfg.get("max_usd") is not None:
                reserva, motivo = self._reservar(route, cfg, request)
                if reserva is None:  # outra chamada levou a capacidade entre a triagem e a reserva
                    attempts.append({"route": route, "skipped": motivo})
                    continue
            if cfg.get("max_usd") is not None and hasattr(adapter, "max_budget_usd"):
                adapter.max_budget_usd = cfg["max_usd"] - self._gasto_da_rota(route)[0]  # saldo do teto
            try:
                result = adapter.call(request)
            except BaseException:
                if reserva:
                    # Desfecho desconhecido: conta como chamada que saiu, com custo não medido (falha
                    # fechada); a administração reconcilia pelo `rota custo`.
                    self._registrar(route, request, provider_id="desconhecido", state="interrompida",
                                    simulated=False, dispatched=True, custo=None, reserva=reserva)
                raise
            custo = (result.usage or {}).get("custo_usd")
            attempts.append({"route": route, "state": result.state, "simulated": result.simulated})
            self._registrar(route, request, provider_id=result.provider_id, state=result.state,
                            simulated=result.simulated, dispatched=result.dispatched, custo=custo, reserva=reserva)
            if result.state == "succeeded":
                # Simulação nunca vira "sucesso" indistinto: o estado diz que foi simulada.
                estado = "succeeded_simulated" if result.simulated else "succeeded"
                return {"state": estado, "result": result, "attempts": attempts}
            # Falha nesta rota: segue para a próxima AUTORIZADA, sem repetir a mesma.
        events.emit(self.con, "provider_blocked", project_id=request.project_id, run_id=request.run_id,
                    payload={"attempts": attempts})
        return {"state": "blocked", "result": None, "attempts": attempts}


def _reservas_em_andamento(con: sqlite3.Connection, route: str) -> list[str]:
    try:
        return [r[0] for r in con.execute("SELECT reservation_id FROM route_reservation WHERE route = ?"
                                          " AND state = 'reserved' ORDER BY created_at", (route,))]
    except sqlite3.OperationalError:  # banco sem a migração 4 (só leitura de cópia antiga)
        return []


def route_spending(con: sqlite3.Connection, route: str) -> tuple[float, int, list[str]]:
    """Gasto das tentativas REAIS da rota: (custo, chamadas, tentativas sem custo medido).
    Não contam: simulação e tentativa que não saiu (dispatched=false). Tentativa antiga sem o
    campo conta como saída (conservador). Custo reconciliado pela administração prevalece.
    Reserva em andamento (chamada ainda no adaptador, ou processo que caiu no meio) conta como
    chamada e como custo não medido: o teto vale também para chamadas simultâneas (F10)."""
    total, chamadas, pendentes = _gasto_registrado(con, route)
    reservas = _reservas_em_andamento(con, route)
    return total, chamadas + len(reservas), pendentes + reservas


def _gasto_registrado(con: sqlite3.Connection, route: str) -> tuple[float, int, list[str]]:
    reconciliado = {}
    for (payload,) in con.execute("SELECT payload_json FROM event WHERE kind = 'provider_cost_reconciled'"):
        p = json.loads(payload)
        reconciliado[p["attempt_event_id"]] = p["cost_usd"]
    total, chamadas, pendentes = 0.0, 0, []
    for event_id, payload in con.execute(
            "SELECT event_id, payload_json FROM event WHERE kind = 'provider_attempt' ORDER BY seq"):
        p = json.loads(payload)
        if p.get("route") != route or p.get("simulated") or p.get("dispatched") is False:
            continue
        chamadas += 1
        custo = reconciliado.get(event_id, p.get("cost_usd"))
        if custo is not None:
            total += float(custo)  # decimal em texto (JSON canônico não aceita float)
        else:
            pendentes.append(event_id)
    return total, chamadas, pendentes


def spending_report(con: sqlite3.Connection, route: str) -> dict:
    total, chamadas, pendentes = _gasto_registrado(con, route)
    reservas = _reservas_em_andamento(con, route)
    return {"rota": route, "chamadas": chamadas, "gasto_usd": f"{total:.6f}", "sem_custo_medido": pendentes,
            "reservas_em_andamento": reservas}


def reconcile_cost(con: sqlite3.Connection, admin: Principal, route: str, attempt_event_id: str,
                   cost_usd: str, fonte: str) -> dict:
    """Registra o custo de uma tentativa sem custo medido, conferido pela administração numa fonte
    externa (painel ou fatura do provedor). Libera o teto de custo da rota; uma vez por tentativa."""
    Policy(con).require(admin, "admin", "foundation")
    try:
        valor = Decimal(str(cost_usd))
    except InvalidOperation:
        raise ValidationError("custo inválido: use decimal em dólares, ex.: 0.0123") from None
    if not valor.is_finite() or valor < 0:
        raise ValidationError("custo inválido: use decimal em dólares, ex.: 0.0123")
    if not str(fonte).strip():
        raise ValidationError("informe a fonte do custo (ex.: painel do provedor, fatura)")
    if str(attempt_event_id).startswith("rsv_"):
        attempt_event_id = _fechar_reserva(con, admin, route, attempt_event_id)
    row = con.execute("SELECT payload_json FROM event WHERE kind = 'provider_attempt' AND event_id = ?",
                      (attempt_event_id,)).fetchone()
    if row is None:
        raise ValidationError("tentativa inexistente", attempt_event_id=attempt_event_id)
    p = json.loads(row[0])
    if p.get("route") != route or p.get("simulated"):
        raise ValidationError("a tentativa não é uma chamada real desta rota", attempt_event_id=attempt_event_id)
    if p.get("cost_usd") is not None:
        raise ValidationError("a tentativa já tem custo medido", attempt_event_id=attempt_event_id)
    for (payload,) in con.execute("SELECT payload_json FROM event WHERE kind = 'provider_cost_reconciled'"):
        if json.loads(payload).get("attempt_event_id") == attempt_event_id:
            raise ValidationError("custo desta tentativa já reconciliado", attempt_event_id=attempt_event_id)
    texto = f"{valor:.6f}"
    events.emit(con, "provider_cost_reconciled", subject=admin.principal_id,
                payload={"attempt_event_id": attempt_event_id, "route": route, "cost_usd": texto,
                         "fonte": str(fonte).strip()[:200]})
    return {"reconciliado": attempt_event_id, "custo_usd": texto, **spending_report(con, route)}


def _fechar_reserva(con: sqlite3.Connection, admin: Principal, route: str, reservation_id: str) -> str:
    """Reserva que ficou aberta (processo caiu durante a chamada) vira tentativa registrada, de custo
    não medido, para a administração reconciliar. Idempotente por ID: reserva já fechada devolve a
    tentativa que a fechou."""
    with transaction(con):
        row = con.execute("SELECT state, project_id, attempt_event_id FROM route_reservation"
                          " WHERE reservation_id = ? AND route = ?", (reservation_id, route)).fetchone()
        if row is None:
            raise ValidationError("reserva inexistente nesta rota", attempt_event_id=reservation_id)
        if row["state"] != "reserved":
            if not row["attempt_event_id"]:
                raise ValidationError("reserva liberada sem chamada: não há custo", attempt_event_id=reservation_id)
            return row["attempt_event_id"]
        evento = events.emit(con, "provider_attempt", project_id=row["project_id"], subject=admin.principal_id,
                             payload={"route": route, "provider_id": "desconhecido", "state": "interrompida",
                                      "simulated": False, "dispatched": True, "cost_usd": None,
                                      "reservation_id": reservation_id, "fechada_pela_administracao": True})
        con.execute("UPDATE route_reservation SET state = 'finalized', finalized_at = ?, attempt_event_id = ?"
                    " WHERE reservation_id = ? AND state = 'reserved'", (utcnow(), evento, reservation_id))
    return evento
