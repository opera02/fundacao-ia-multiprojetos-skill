"""Coordenação persistente de tarefas em etapas (livro A09; proposta 3.0 R2.2/R3.2).

Garantias implementadas:
- Fluxo descrito como dados; dependências inexistentes e ciclos são rejeitados.
- Máquina de estados formal (contracts.ALLOWED_STEP_TRANSITIONS).
- Checkpoint por etapa: hash das entradas + referência e hash da saída.
- Transações curtas: reserva -> trabalho fora da transação -> registro.
- Retomada reaproveita etapas válidas, invalida derivadas de entradas alteradas
  e reconcilia "saída gravada, estado não confirmado" pelo recibo (sem refazer).
- Limite de tentativas, orçamento de chamadas/tempo, cancelamento e decisão
  humana vinculada ao hash do conteúdo apresentado.
- Autorização ATUAL em cada operação pública (não só ao criar o coordenador) e
  execução sempre associada ao par projeto/ID antes de qualquer leitura ou efeito
  (auditoria F02/F03). Revogação durante uma etapa: a chamada ao provedor não é
  debitada, a saída não é gravada e a etapa volta a `pending` (retomável por quem
  estiver autorizado).
Não promete execução única em serviços externos: efeitos externos exigem chave
de idempotência do destino ou reconciliação do recibo antes de repetir.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import events
from .auth import Policy, Principal, resource_project
from .canon import canonical_json, sha256_bytes, sha256_file, sha256_json
from .contracts import (
    SCHEMAS, AccessDenied, BudgetExhausted, NotFound, PathEscape, ValidationError, check_transition,
)
from .db import transaction, utcnow
from .ids import new_id
from .paths import contained, validate_id
from .projects import project_root


@dataclass(frozen=True)
class StepDef:
    step_id: str
    depends_on: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()  # caminhos relativos à pasta data/ do projeto
    max_attempts: int = 3


@dataclass
class Budget:
    max_calls: int = 4  # teto inicial do livro (A08) para chamadas reais
    max_seconds: float | None = None


class NeedsHuman(Exception):
    def __init__(self, question: str, options: list[str]):
        super().__init__(question)
        self.question = question
        self.options = options


class TransientError(Exception):
    """Falha que pode passar com nova tentativa (ex.: timeout de rede)."""


class PermanentError(Exception):
    """Falha que não se resolve repetindo (login ausente, entrada inválida, permissão)."""


class SimulatedInterrupt(Exception):
    """Interrupção controlada de teste (substitui encerrar processos desconhecidos)."""


@dataclass
class StepContext:
    run_id: str
    step_id: str
    attempt: int
    inputs: dict[str, Path]
    upstream: dict[str, str]
    _coordinator: "Coordinator" = field(repr=False)

    def charge_call(self, provider_id: str) -> None:
        """Debita uma chamada do orçamento ANTES de chamar o provedor."""
        self._coordinator._charge_call(self.run_id, provider_id)


def validate_flow(steps: list[StepDef]) -> list[str]:
    ids = [s.step_id for s in steps]
    if len(set(ids)) != len(ids):
        raise ValidationError("etapas duplicadas no fluxo")
    for s in steps:
        validate_id(s.step_id, "step_id")
        for dep in s.depends_on:
            if dep not in ids:
                raise ValidationError("dependência inexistente", step=s.step_id, missing=dep)
        if s.max_attempts < 1:
            raise ValidationError("max_attempts deve ser >= 1", step=s.step_id)
    order: list[str] = []
    state: dict[str, int] = {}
    graph = {s.step_id: s.depends_on for s in steps}

    def visit(node: str, path: tuple[str, ...]) -> None:
        if state.get(node) == 2:
            return
        if state.get(node) == 1:
            raise ValidationError("ciclo de dependências", cycle=list(path + (node,)))
        state[node] = 1
        for dep in graph[node]:
            visit(dep, path + (node,))
        state[node] = 2
        order.append(node)

    for s in steps:
        visit(s.step_id, ())
    return order


class Coordinator:
    def __init__(self, root: Path, con: sqlite3.Connection, principal: Principal, project_id: str):
        self.root = Path(root)
        self.con = con
        self.principal = principal
        self.project_id = project_id
        self.policy = Policy(con)
        # Autorização aplicada ao abrir o projeto, fora do modelo — e repetida em cada operação, com a
        # ação de cada uma: abrir exige só leitura, para que uma identidade de leitura ou auditoria
        # consulte tarefas e execuções; tudo o que muda estado exige escrita na própria operação
        # (auditoria final da 1.4.2, AF-09).
        self.project_dir = project_root(self.root, con, principal, project_id, action="read")
        self.data_dir = self.project_dir / "data"
        self.runs_dir = self.project_dir / "outputs" / "runs"
        self._lock = threading.Lock()

    # ------------------------------------------------------------ autorização
    def _autorizar(self, action: str) -> None:
        """Política ATUAL antes da operação (a construção não basta: a permissão pode ter sido
        revogada depois). Nega com evento `access_denied`, sem ler nem alterar nada (F03)."""
        project_root(self.root, self.con, self.principal, self.project_id, action=action)

    def _ainda_autorizado(self, action: str = "write") -> bool:
        return self.policy.allowed(self.principal.principal_id, action, resource_project(self.project_id))

    # ------------------------------------------------------------ tarefas
    def create_task(self, objective: str, idempotency_key: str | None = None) -> str:
        if not objective.strip():
            raise ValidationError("objetivo vazio")
        self._autorizar("write")
        # Chave de idempotência vale DENTRO do projeto: a mesma chave em outro projeto é outra
        # tarefa (antes, a colisão global revelava que a chave existia em outro projeto).
        chave = f"{self.project_id}::{idempotency_key}" if idempotency_key else None
        if chave:
            row = self.con.execute("SELECT task_id FROM task WHERE idempotency_key = ?", (chave,)).fetchone()
            if row:
                return row["task_id"]
        task_id = new_id("task")
        with transaction(self.con):
            self.policy.recheck(self.principal, "write", resource_project(self.project_id))
            now = utcnow()
            self.con.execute(
                "INSERT INTO task VALUES (?,?,?,?,?,?,?,?,?)",
                (task_id, self.project_id, objective, "pending", chave,
                 SCHEMAS["task"], self.principal.principal_id, now, now),
            )
            events.emit(self.con, "task_created", project_id=self.project_id,
                        subject=self.principal.principal_id, task_id=task_id)
        return task_id

    def _task_row(self, task_id: str) -> sqlite3.Row:
        row = self.con.execute("SELECT * FROM task WHERE task_id = ? AND project_id = ?",
                               (task_id, self.project_id)).fetchone()
        if row is None:
            # Mesmo erro para inexistente e alheio: não revela existência em outro projeto.
            raise NotFound("tarefa não encontrada neste projeto")
        return row

    def get_task(self, task_id: str) -> dict:
        self._autorizar("read")
        task = dict(self._task_row(task_id))
        if task["idempotency_key"] and "::" in task["idempotency_key"]:
            task["idempotency_key"] = task["idempotency_key"].split("::", 1)[1]
        return task

    # ------------------------------------------------------------ execuções
    def start_run(self, task_id: str, flow_id: str, flow_version: str,
                  steps: list[StepDef], budget: Budget | None = None) -> str:
        self._autorizar("write")
        self._task_row(task_id)
        validate_flow(steps)
        existing = self.con.execute(
            "SELECT run_id FROM run WHERE task_id = ? AND flow_id = ? AND flow_version = ? AND project_id = ?",
            (task_id, flow_id, flow_version, self.project_id),
        ).fetchone()
        if existing:
            return existing["run_id"]  # repetir a solicitação não cria nova execução
        budget = budget or Budget()
        run_id = new_id("run")
        flow_json = canonical_json([asdict(s) for s in steps])
        with transaction(self.con):
            self.policy.recheck(self.principal, "write", resource_project(self.project_id))
            now = utcnow()
            self.con.execute(
                "INSERT INTO run (run_id, task_id, project_id, flow_id, flow_version, flow_json,"
                " state, budget_json, created_by, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, task_id, self.project_id, flow_id, flow_version, flow_json, "pending",
                 json.dumps(asdict(budget)), self.principal.principal_id, now, now),
            )
            for s in steps:
                self.con.execute(
                    "INSERT INTO step (run_id, step_id, state, updated_at) VALUES (?,?,?,?)",
                    (run_id, s.step_id, "pending", now),
                )
            events.emit(self.con, "run_created", project_id=self.project_id, run_id=run_id,
                        task_id=task_id, subject=self.principal.principal_id,
                        payload={"flow_id": flow_id, "flow_version": flow_version})
        return run_id

    def _run_row(self, run_id: str) -> sqlite3.Row:
        """Execução pelo par projeto/ID: alheia responde igual a inexistente, sem efeito (F02)."""
        row = self.con.execute("SELECT * FROM run WHERE run_id = ? AND project_id = ?",
                               (run_id, self.project_id)).fetchone()
        if row is None:
            raise NotFound("execução não encontrada neste projeto")
        return row

    def _steps(self, run_id: str) -> list[StepDef]:
        return [StepDef(**{**d, "depends_on": tuple(d["depends_on"]), "inputs": tuple(d["inputs"])})
                for d in json.loads(self._run_row(run_id)["flow_json"])]

    def _step_rows(self, run_id: str) -> list[dict]:
        return [dict(r) for r in self.con.execute(
            "SELECT step_id, state, attempts, executions, input_hash, output_ref, output_hash, error"
            " FROM step WHERE run_id = ? ORDER BY rowid", (run_id,))]

    def status(self, run_id: str) -> list[dict]:
        self._autorizar("read")
        self._run_row(run_id)
        return self._step_rows(run_id)

    def _set_step(self, run_id: str, step_id: str, new: str, **fields: Any) -> None:
        with transaction(self.con):
            # A mutação vale só para etapa de execução DESTE projeto, conferida na mesma transação.
            row = self.con.execute(
                "SELECT s.state FROM step s JOIN run r ON r.run_id = s.run_id"
                " WHERE s.run_id = ? AND s.step_id = ? AND r.project_id = ?",
                (run_id, step_id, self.project_id)).fetchone()
            if row is None:
                raise NotFound("execução não encontrada neste projeto")
            cur = row["state"]
            check_transition(cur, new)
            sets = ["state = ?", "updated_at = ?"]
            params: list[Any] = [new, utcnow()]
            for key, value in fields.items():
                sets.append(f"{key} = ?")
                params.append(value)
            params += [run_id, step_id]
            self.con.execute(f"UPDATE step SET {', '.join(sets)} WHERE run_id = ? AND step_id = ?", params)
            events.emit(self.con, f"step_{new}", project_id=self.project_id, run_id=run_id,
                        subject=self.principal.principal_id,
                        payload={"step_id": step_id, "from": cur})

    def _charge_call(self, run_id: str, provider_id: str) -> None:
        with self._lock:  # pode ser chamado por etapas paralelas
            self._charge_call_locked(run_id, provider_id)

    def _charge_call_locked(self, run_id: str, provider_id: str) -> None:
        self._autorizar("write")  # revogada durante a etapa: nada é debitado nem chamado (F03)
        budget = json.loads(self._run_row(run_id)["budget_json"])
        with transaction(self.con):
            updated = self.con.execute(
                "UPDATE run SET calls_used = calls_used + 1, updated_at = ?"
                " WHERE run_id = ? AND project_id = ? AND calls_used < ?",
                (utcnow(), run_id, self.project_id, budget["max_calls"]),
            ).rowcount
        if updated == 0:
            # Evento gravado fora da transação desfeita, para ficar como evidência.
            events.emit(self.con, "budget_exhausted", project_id=self.project_id, run_id=run_id,
                        payload={"provider_id": provider_id, "max_calls": budget["max_calls"]})
            raise BudgetExhausted("orçamento de chamadas esgotado", max_calls=budget["max_calls"])

    def _input_hash(self, run_id: str, step: StepDef) -> tuple[str, dict[str, Path], dict[str, str]]:
        resolved: dict[str, Path] = {}
        parts: dict[str, Any] = {"inputs": {}, "upstream": {}}
        for rel in step.inputs:
            try:
                # `data/` trocada por ligação para outro projeto também é recusada (F04).
                path = contained(self.data_dir, self.data_dir / rel, within=self.project_dir)
            except PathEscape:
                raise PermanentError(f"entrada fora da pasta de dados do projeto: {rel}") from None
            if not path.exists():
                raise PermanentError(f"entrada ausente: {rel}")
            resolved[rel] = path
            parts["inputs"][rel] = sha256_file(path)
        upstream: dict[str, str] = {}
        for dep in step.depends_on:
            row = self.con.execute(
                "SELECT output_ref, output_hash FROM step WHERE run_id = ? AND step_id = ?",
                (run_id, dep),
            ).fetchone()
            parts["upstream"][dep] = row["output_hash"]
            upstream[dep] = self._abs(row["output_ref"]).read_text(encoding="utf-8") if row["output_ref"] else ""
        return sha256_json(parts), resolved, upstream

    def _dependents(self, steps: list[StepDef], step_id: str) -> set[str]:
        out: set[str] = set()
        frontier = {step_id}
        while frontier:
            nxt = {s.step_id for s in steps if set(s.depends_on) & frontier} - out
            out |= nxt
            frontier = nxt
        return out

    def _ref(self, path: Path) -> str:
        """Referência relativa à raiz da fundação: após restaurar em outra pasta, a cópia
        continua lendo as próprias saídas (antes gravava caminho absoluto da origem)."""
        return Path(path).resolve().relative_to(self.root.resolve()).as_posix()

    def _abs(self, ref: str) -> Path:
        p = Path(ref)
        alvo = p if p.is_absolute() else self.root / p
        try:
            return contained(self.project_dir, alvo)  # saída de outro projeto não é lida (F04)
        except PathEscape:
            raise PermanentError("saída registrada fora da pasta do projeto") from None

    def _run_dir(self, run_id: str) -> Path:
        """Pasta das saídas da execução, contida na pasta do projeto: `outputs/` trocada por ligação
        para outro projeto é recusada antes de gravar ou ler (F04)."""
        try:
            return contained(self.project_dir, self.runs_dir / run_id)
        except PathEscape:
            raise PermanentError("pasta de saídas fora da pasta do projeto") from None

    def _write_output(self, run_id: str, step_id: str, input_hash: str, data: bytes) -> tuple[str, str]:
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        run_dir = self._run_dir(run_id)  # conferida de novo depois de criar as pastas
        out = run_dir / f"{step_id}__{input_hash[:16]}.out"
        tmp = out.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, out)
        digest = sha256_bytes(data)
        receipt = {"run_id": run_id, "step_id": step_id, "input_hash": input_hash, "output_hash": digest}
        rtmp = out.with_suffix(".receipt.tmp")
        rtmp.write_text(canonical_json(receipt), encoding="utf-8")
        os.replace(rtmp, out.with_suffix(".receipt.json"))
        return self._ref(out), digest

    # ------------------------------------------------------------ ciclo
    def _invalidate_changed(self, run_id: str, steps: list[StepDef], rows: dict) -> bool:
        """Invalida a primeira etapa concluída cuja entrada mudou, e suas derivadas."""
        for step in steps:
            row = rows[step.step_id]
            if row["state"] != "succeeded":
                continue
            if any(rows[d]["state"] != "succeeded" for d in step.depends_on):
                continue
            try:
                current, _, _ = self._input_hash(run_id, step)
            except PermanentError:
                current = None  # entrada sumiu: trata como alterada
            if current == row["input_hash"]:
                continue
            for sid in [step.step_id, *sorted(self._dependents(steps, step.step_id))]:
                if rows[sid]["state"] == "succeeded":
                    self._set_step(run_id, sid, "pending", error="invalidada: entrada alterada")
            return True
        return False

    def _invoke(self, handler: Callable[[StepContext], Any], ctx: StepContext) -> tuple:
        t0 = time.time()
        try:
            result = handler(ctx)
        except NeedsHuman as hum:
            return ("human", hum, t0, time.time())
        except AccessDenied as exc:
            return ("denied", exc, t0, time.time())
        except (PermanentError, BudgetExhausted) as exc:
            return ("permanent", exc, t0, time.time())
        except TransientError as exc:
            return ("transient", exc, t0, time.time())
        return ("ok", result, t0, time.time())

    def run(self, run_id: str, handlers: dict[str, Callable[[StepContext], Any]], *,
            interrupt: tuple[str, str] | None = None, lease_seconds: float = 60.0,
            max_parallel: int = 1) -> dict:
        """Executa etapas prontas. `max_parallel` > 1 roda etapas INDEPENDENTES em paralelo
        (horários de início/fim registrados no evento `step_timing`). O modo
        `interrupt=(step_id, 'before_commit'|'after_commit')` é um teste de retomada.
        A autorização é conferida antes de cada lote (antes de ler entradas) e de novo antes de
        gravar cada saída; revogada no meio, a etapa volta a `pending` e a chamada levanta
        `AccessDenied` (F03)."""
        self._autorizar("write")
        steps = self._steps(run_id)
        topo = validate_flow(steps)
        ordered = [next(s for s in steps if s.step_id == sid) for sid in topo]
        budget = json.loads(self._run_row(run_id)["budget_json"])
        started = time.monotonic()
        while True:
            self._autorizar("write")
            if self._run_row(run_id)["state"] == "cancelled":
                break
            rows = {r["step_id"]: dict(r) for r in self.con.execute(
                "SELECT * FROM step WHERE run_id = ?", (run_id,))}
            if self._invalidate_changed(run_id, ordered, rows):
                continue
            ready = [s for s in ordered if rows[s.step_id]["state"] == "pending"
                     and all(rows[d]["state"] == "succeeded" for d in s.depends_on)]
            if not ready:
                break
            if budget.get("max_seconds") and time.monotonic() - started > budget["max_seconds"]:
                events.emit(self.con, "budget_time_exhausted", project_id=self.project_id, run_id=run_id)
                return self._finish(run_id)
            prepared = []
            for step in ready[:max(1, max_parallel)]:
                row = rows[step.step_id]
                try:
                    input_hash, inputs, upstream = self._input_hash(run_id, step)
                except PermanentError as exc:
                    self._set_step(run_id, step.step_id, "running")
                    self._set_step(run_id, step.step_id, "failed", error=str(exc))
                    continue
                if row["attempts"] >= step.max_attempts:
                    self._set_step(run_id, step.step_id, "running")
                    self._set_step(run_id, step.step_id, "failed", error="limite de tentativas atingido")
                    continue
                self._set_step(run_id, step.step_id, "running", attempts=row["attempts"] + 1,
                               executions=row["executions"] + 1, lease_until=time.time() + lease_seconds,
                               input_hash=input_hash)
                ctx = StepContext(run_id, step.step_id, row["attempts"] + 1, inputs, upstream, self)
                prepared.append((step, row, input_hash, ctx))
            if not prepared:
                continue
            if len(prepared) == 1:
                outcomes = [self._invoke(handlers[prepared[0][0].step_id], prepared[0][3])]
            else:
                with ThreadPoolExecutor(max_workers=len(prepared)) as pool:
                    futures = [pool.submit(self._invoke, handlers[p[0].step_id], p[3]) for p in prepared]
                    outcomes = [f.result() for f in futures]
            revogada = False
            for (step, row, input_hash, _ctx), (kind, value, t0, t1) in zip(prepared, outcomes):
                events.emit(self.con, "step_timing", project_id=self.project_id, run_id=run_id,
                            payload={"step_id": step.step_id, "started": str(t0), "ended": str(t1),
                                     "parallel_batch": len(prepared)})
                if kind == "denied":
                    if self._ainda_autorizado("write"):
                        # A negativa veio de outro recurso, não da revogação deste projeto.
                        self._set_step(run_id, step.step_id, "failed", error="acesso negado durante a etapa")
                    else:
                        revogada = True
                        self._set_step(run_id, step.step_id, "pending", lease_until=None,
                                       error="autorização revogada durante a etapa; reenfileirada")
                elif kind == "human":
                    payload = {"question": value.question, "options": value.options}
                    self._set_step(run_id, step.step_id, "waiting_human",
                                   decision_json=canonical_json({**payload, "hash": sha256_json(payload)}))
                elif kind == "permanent":
                    self._set_step(run_id, step.step_id, "failed", error=str(value)[:300])
                elif kind == "transient":
                    self._set_step(run_id, step.step_id, "failed", error=str(value)[:300])
                    if row["attempts"] + 1 < step.max_attempts:
                        self._set_step(run_id, step.step_id, "pending")
                elif not self._ainda_autorizado("write"):
                    # Revogada antes da gravação: a saída é descartada, nada é escrito.
                    revogada = True
                    self._set_step(run_id, step.step_id, "pending", lease_until=None,
                                   error="autorização revogada antes da gravação; saída descartada")
                else:
                    data = value if isinstance(value, bytes) else str(value).encode("utf-8")
                    out_ref, out_hash = self._write_output(run_id, step.step_id, input_hash, data)
                    if interrupt == (step.step_id, "before_commit"):
                        raise SimulatedInterrupt(step.step_id)
                    self._set_step(run_id, step.step_id, "succeeded", output_ref=out_ref,
                                   output_hash=out_hash, error=None, lease_until=None)
                    if interrupt == (step.step_id, "after_commit"):
                        raise SimulatedInterrupt(step.step_id)
            if revogada:
                self._autorizar("write")  # registra a negativa e levanta AccessDenied
        return self._finish(run_id)

    def _finish(self, run_id: str) -> dict:
        states = [r["state"] for r in self.con.execute("SELECT state FROM step WHERE run_id = ?", (run_id,))]
        if self._run_row(run_id)["state"] == "cancelled":
            final = "cancelled"
        elif all(s == "succeeded" for s in states):
            final = "succeeded"
        elif any(s == "waiting_human" for s in states):
            final = "waiting_human"
        elif any(s == "failed" for s in states):
            final = "failed"
        else:
            final = "pending"
        with transaction(self.con):
            self.con.execute("UPDATE run SET state = ?, updated_at = ? WHERE run_id = ? AND project_id = ?",
                             (final, utcnow(), run_id, self.project_id))
            # A tarefa reflete a execução mais recente (antes ficava "pending" para sempre).
            self.con.execute("UPDATE task SET state = ?, updated_at = ? WHERE task_id = "
                             "(SELECT task_id FROM run WHERE run_id = ? AND project_id = ?)",
                             (final, utcnow(), run_id, self.project_id))
            events.emit(self.con, "run_state", project_id=self.project_id, run_id=run_id,
                        payload={"state": final})
        return {"run_id": run_id, "state": final, "steps": self._step_rows(run_id)}

    def resume(self, run_id: str, handlers: dict[str, Callable[[StepContext], Any]], *,
               now: float | None = None, **kwargs: Any) -> dict:
        """Reconcilia o estado persistido antes de continuar (não usa a memória da conversa).
        Autorização e associação ao projeto vêm ANTES de ler ou mudar qualquer etapa (F02/F03)."""
        self._autorizar("write")
        self._run_row(run_id)
        now = time.time() if now is None else now
        for row in self.con.execute("SELECT * FROM step WHERE run_id = ? AND state = 'running'", (run_id,)).fetchall():
            reconciled = False
            run_dir = self._run_dir(run_id)
            if row["input_hash"] and run_dir.exists():
                out = run_dir / f"{row['step_id']}__{row['input_hash'][:16]}.out"
                receipt_path = out.with_suffix(".receipt.json")
                if out.exists() and receipt_path.exists():
                    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                    digest = sha256_file(out)
                    if (receipt.get("run_id") == run_id and receipt.get("step_id") == row["step_id"]
                            and receipt.get("input_hash") == row["input_hash"]
                            and receipt.get("output_hash") == digest):
                        self._set_step(run_id, row["step_id"], "succeeded", output_ref=self._ref(out),
                                       output_hash=digest, error=None, lease_until=None)
                        events.emit(self.con, "step_reconciled", project_id=self.project_id,
                                    run_id=run_id, payload={"step_id": row["step_id"]})
                        reconciled = True
            if not reconciled and (row["lease_until"] is None or row["lease_until"] <= now):
                self._set_step(run_id, row["step_id"], "pending", error="posse expirada; reenfileirada")
        return self.run(run_id, handlers, **kwargs)

    def cancel(self, run_id: str) -> dict:
        self._autorizar("write")
        self._run_row(run_id)
        with transaction(self.con):
            self.con.execute("UPDATE run SET state = 'cancelled', updated_at = ? WHERE run_id = ? AND project_id = ?",
                             (utcnow(), run_id, self.project_id))
        for row in self._step_rows(run_id):
            if row["state"] in ("pending", "running", "waiting_human", "failed"):
                self._set_step(run_id, row["step_id"], "cancelled")
        return self._finish(run_id)

    def decide(self, run_id: str, step_id: str, choice: str, approver: Principal, expected_hash: str) -> None:
        """Decisão humana vinculada ao conteúdo exato apresentado (hash), numa execução DESTE projeto."""
        self._autorizar("write")
        self._run_row(run_id)
        self.policy.require(approver, "approve", resource_project(self.project_id))
        row = self.con.execute(
            "SELECT s.* FROM step s JOIN run r ON r.run_id = s.run_id"
            " WHERE s.run_id = ? AND s.step_id = ? AND r.project_id = ?",
            (run_id, step_id, self.project_id)).fetchone()
        if row is None or row["state"] != "waiting_human":
            raise ValidationError("etapa não aguarda decisão")
        decision = json.loads(row["decision_json"])
        if decision["hash"] != expected_hash:
            raise ValidationError("conteúdo mudou desde a apresentação; aprovação anterior não vale")
        if choice not in decision["options"]:
            raise ValidationError("opção inexistente")
        out_ref, out_hash = self._write_output(run_id, step_id, row["input_hash"] or "decisao", choice.encode("utf-8"))
        self._set_step(run_id, step_id, "succeeded", output_ref=out_ref, output_hash=out_hash,
                       decision_json=canonical_json({**decision, "choice": choice,
                                                     "approved_by": approver.principal_id}))
