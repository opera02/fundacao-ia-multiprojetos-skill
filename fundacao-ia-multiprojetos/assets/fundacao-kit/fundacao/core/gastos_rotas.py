"""Contabilidade e reconciliação das rotas; separada do despacho na 1.7.9."""
from __future__ import annotations

import json
import sqlite3
from decimal import Decimal, InvalidOperation

from . import events
from .auth import Policy, Principal
from .contracts import ValidationError
from .db import transaction, utcnow
from .usage import custo_decimal


def texto_do_custo(valor: Decimal) -> str:
    """Decimal integral na trilha; seis casas mínimas conservam o formato legado."""
    inteiro, _, fracao = format(valor, "f").partition(".")
    return inteiro + "." + fracao.ljust(6, "0")


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
    chamada e como custo não medido: o teto vale também para chamadas simultâneas (F10).
    Custo gravado inválido (negativo, NaN, infinito — kit anterior) também conta como não medido (#17)."""
    total, chamadas, pendentes = _gasto_registrado(con, route)
    reservas = _reservas_em_andamento(con, route)
    return float(total), chamadas + len(reservas), pendentes + reservas


def route_spending_exact(con, route):
    """A comparação de tetos preserva Decimal; a API antiga continua devolvendo float."""
    total, chamadas, pendentes = _gasto_registrado(con, route)
    reservas = _reservas_em_andamento(con, route)
    return total, chamadas + len(reservas), pendentes + reservas


def _gasto_registrado(con: sqlite3.Connection, route: str) -> tuple[float, int, list[str]]:
    reconciliado = {}
    for (payload,) in con.execute("SELECT payload_json FROM event WHERE kind = 'provider_cost_reconciled'"):
        p = json.loads(payload)
        reconciliado[p["attempt_event_id"]] = p["cost_usd"]
    total, chamadas, pendentes = Decimal(0), 0, []
    for event_id, payload in con.execute(
            "SELECT event_id, payload_json FROM event WHERE kind = 'provider_attempt' ORDER BY seq"):
        p = json.loads(payload)
        if p.get("route") != route or p.get("simulated") or p.get("dispatched") is False:
            continue
        chamadas += 1
        # Decimal em texto (JSON canônico não aceita float); negativo, NaN ou infinito = não medido.
        custo = custo_decimal(reconciliado.get(event_id, p.get("cost_usd")), texto=True)
        if custo is not None:
            total += custo
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
    if custo_decimal(p.get("cost_usd"), texto=True) is not None:  # custo gravado inválido pode ser reconciliado
        raise ValidationError("a tentativa já tem custo medido", attempt_event_id=attempt_event_id)
    for (payload,) in con.execute("SELECT payload_json FROM event WHERE kind = 'provider_cost_reconciled'"):
        if json.loads(payload).get("attempt_event_id") == attempt_event_id:
            raise ValidationError("custo desta tentativa já reconciliado", attempt_event_id=attempt_event_id)
    texto = texto_do_custo(valor)
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
