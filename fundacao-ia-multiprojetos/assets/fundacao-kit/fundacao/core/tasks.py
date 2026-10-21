"""Coordenação persistente de tarefas em etapas (livro A09; proposta 3.0 R2.2/R3.2).

Garantias implementadas:
- Fluxo descrito como dados; dependências inexistentes e ciclos são rejeitados.
- Máquina de estados formal (contracts.ALLOWED_STEP_TRANSITIONS).
- Checkpoint por etapa: hash das entradas + referência e hash da saída.
- Transações curtas: reserva -> trabalho fora da transação -> registro.
- Retomada reaproveita etapas válidas, invalida derivadas de entradas alteradas
  e reconcilia "saída gravada, estado não confirmado" pelo banco (sem refazer).
- Limite de tentativas, orçamento de chamadas/tempo, cancelamento e decisão
  humana vinculada ao hash do conteúdo apresentado.
- Autorização ATUAL em cada operação pública (não só ao criar o coordenador) e
  execução sempre associada ao par projeto/ID antes de qualquer leitura ou efeito
  (auditoria F02/F03). Revogação durante uma etapa: a chamada ao provedor não é
  debitada, a saída não é gravada e a etapa volta a `pending` (retomável por quem
  estiver autorizado). A autorização é conferida de novo DENTRO de cada transação
  que reserva, debita, grava ou confirma (varredura 1.4.5, #11): revogação
  confirmada entre a conferência e a gravação vale.
- Saídas conferidas pelo banco (auditoria A04; varredura #14): arquivo e recibo ficam
  na pasta do projeto, que quem opera o projeto altera; o hash gravado no banco é a
  referência. A saída é relida e conferida antes de alimentar uma dependente, e a
  etapa concluída cuja saída sumiu ou mudou é refeita. Na retomada, só confirma
  "saída gravada, estado não confirmado" a saída que o banco reservou para aquela
  geração da posse, com os mesmos bytes; o recibo é só registro.
- Posse por geração (A05): `executions` (nunca reaproveitado) identifica a posse;
  cada geração grava num arquivo próprio e só publica, debita ou registra desfecho
  enquanto for a posse atual. A lease vencida só habilita a retomada por outro
  coordenador.
- Prazo (`max_seconds`) gravado na primeira execução (A07): vale no despacho de cada
  lote e em cada débito de chamada, e a retomada não o renova. É cooperativo: não
  interrompe código dentro de uma função Python (recusa novas chamadas e lotes).
Não promete execução única em serviços externos: efeitos externos exigem chave
de idempotência do destino ou reconciliação antes de repetir.
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


class SaidaAlterada(PermanentError):
    """Saída confirmada ausente, alterada ou fora do projeto: o checkpoint deixa de valer (A04/#14)."""


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
    _execution: int | None = field(default=None, repr=False)  # geração da posse da etapa (A05)

    def charge_call(self, provider_id: str) -> None:
        """Debita uma chamada do orçamento ANTES de chamar o provedor. Recusa sem debitar se a
        autorização foi revogada, se a posse desta etapa foi cancelada ou passou a outra geração,
        ou se o prazo da execução venceu."""
        self._coordinator._charge_call(self.run_id, provider_id, step_id=self.step_id,
                                       execution=self._execution)


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

    def _set_step(self, run_id: str, step_id: str, new: str, *, autorizar: bool = True, **fields: Any) -> None:
        with transaction(self.con):
            if autorizar:
                # Autorização reconferida na MESMA transação da mudança (#11). `autorizar=False` só para
                # devolver à fila a etapa de quem acabou de perder a permissão.
                self.policy.recheck(self.principal, "write", resource_project(self.project_id))
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

    def _claim(self, run_id: str, step_id: str | None, execution: int | None) -> sqlite3.Row | None:
        """Posse atual da etapa (A05): a mesma geração (`executions`, que nunca se repete), ainda
        `running`, numa execução não cancelada DESTE projeto. A lease vencida, sozinha, não tira a
        posse; tiram a retomada (que devolve a etapa a `pending`), uma nova reserva (outra geração),
        a confirmação e o cancelamento."""
        return self.con.execute(
            "SELECT s.* FROM step s JOIN run r ON r.run_id = s.run_id"
            " WHERE s.run_id = ? AND s.step_id = ? AND s.executions = ? AND s.state = 'running'"
            " AND r.project_id = ? AND r.state != 'cancelled'",
            (run_id, step_id, execution, self.project_id)).fetchone()

    # ------------------------------------------------------------ orçamento
    @staticmethod
    def _prazo_vencido(budget: dict) -> bool:
        prazo = budget.get("deadline_epoch")
        return prazo is not None and time.time() >= float(prazo)

    def _iniciar_prazo(self, run_id: str) -> None:
        """Grava o prazo (`deadline_epoch` em `budget_json`) na PRIMEIRA execução; retomadas e novas
        chamadas de `run` usam o mesmo (A07). Relógio de parede, para valer entre processos: ajuste do
        relógio do sistema desloca o prazo. Execução criada por versão anterior ganha o prazo na
        primeira chamada desta versão (o tempo gasto antes não é reconstituído)."""
        budget = json.loads(self._run_row(run_id)["budget_json"])
        if not budget.get("max_seconds") or "deadline_epoch" in budget:
            return
        with transaction(self.con):
            budget = json.loads(self._run_row(run_id)["budget_json"])  # relido: outra conexão pode tê-lo gravado
            if "deadline_epoch" in budget:
                return
            self.policy.recheck(self.principal, "write", resource_project(self.project_id))
            budget["deadline_epoch"] = time.time() + float(budget["max_seconds"])
            self.con.execute("UPDATE run SET budget_json = ?, updated_at = ? WHERE run_id = ? AND project_id = ?",
                             (json.dumps(budget), utcnow(), run_id, self.project_id))

    def _prazo_esgotado(self, run_id: str) -> bool:
        return self._prazo_vencido(json.loads(self._run_row(run_id)["budget_json"]))

    def _charge_call(self, run_id: str, provider_id: str, *, step_id: str | None = None,
                     execution: int | None = None) -> None:
        with self._lock:  # pode ser chamado por etapas paralelas
            self._charge_call_locked(run_id, provider_id, step_id=step_id, execution=execution)

    def _charge_call_locked(self, run_id: str, provider_id: str, *, step_id: str | None,
                            execution: int | None) -> None:
        self._autorizar("write")  # revogada durante a etapa: nada é debitado nem chamado (F03)
        with transaction(self.con):
            # Na transação do débito, de novo: autorização (#11), posse da etapa (A05) e prazo (A07).
            self.policy.recheck(self.principal, "write", resource_project(self.project_id))
            if execution is not None and self._claim(run_id, step_id, execution) is None:
                raise PermanentError("posse da etapa perdida (cancelada, confirmada ou assumida por outra"
                                     " execução): chamada recusada")
            budget = json.loads(self._run_row(run_id)["budget_json"])
            vencido = self._prazo_vencido(budget)
            updated = 0 if vencido else self.con.execute(
                "UPDATE run SET calls_used = calls_used + 1, updated_at = ?"
                " WHERE run_id = ? AND project_id = ? AND calls_used < ?",
                (utcnow(), run_id, self.project_id, budget["max_calls"]),
            ).rowcount
        if vencido:
            events.emit(self.con, "budget_time_exhausted", project_id=self.project_id, run_id=run_id,
                        payload={"provider_id": provider_id, "max_seconds": str(budget["max_seconds"])})
            raise BudgetExhausted("orçamento de tempo esgotado", max_seconds=budget["max_seconds"])
        if updated == 0:
            # Evento gravado fora da transação desfeita, para ficar como evidência.
            events.emit(self.con, "budget_exhausted", project_id=self.project_id, run_id=run_id,
                        payload={"provider_id": provider_id, "max_calls": budget["max_calls"]})
            raise BudgetExhausted("orçamento de chamadas esgotado", max_calls=budget["max_calls"])

    # ------------------------------------------------------------ entradas e saídas
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
                "SELECT step_id, state, output_ref, output_hash FROM step WHERE run_id = ? AND step_id = ?",
                (run_id, dep),
            ).fetchone()
            if row is None or row["state"] != "succeeded":
                raise SaidaAlterada(f"dependência sem saída confirmada: {dep}")
            # Os bytes conferidos com o hash do banco são os MESMOS entregues à etapa (A04/#14).
            dado = self._verified_output(row)
            parts["upstream"][dep] = row["output_hash"]
            try:
                texto = dado.decode("utf-8")
            except UnicodeDecodeError:
                raise PermanentError(f"saída da dependência não é texto UTF-8: {dep}") from None
            upstream[dep] = texto.replace("\r\n", "\n").replace("\r", "\n")  # como a leitura em modo texto
        return sha256_json(parts), resolved, upstream

    def _verified_output(self, row) -> bytes:
        """Lê a saída confirmada UMA vez, confere com o hash do banco e devolve esses bytes (A04/#14).
        O arquivo fica na pasta do projeto, que quem opera o projeto altera: o banco é a referência."""
        if not row["output_ref"] or not row["output_hash"]:
            raise SaidaAlterada(f"saída sem referência ou hash no banco: {row['step_id']}")
        try:
            dado = self._abs(row["output_ref"]).read_bytes()
        except PermanentError:
            raise SaidaAlterada(f"saída registrada fora da pasta do projeto: {row['step_id']}") from None
        except OSError:
            raise SaidaAlterada(f"saída confirmada ausente ou ilegível: {row['step_id']}") from None
        if sha256_bytes(dado) != row["output_hash"]:
            raise SaidaAlterada(f"saída alterada depois da confirmação: {row['step_id']}")
        return dado

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

    def _output_path(self, run_id: str, step_id: str, input_hash: str, execution: int | None = None) -> Path:
        """Arquivo da saída: um por geração da posse (`__exec-<n>`), para que uma posse antiga nunca
        grave sobre a do sucessor (A05). Sem geração, o nome anterior; saídas já confirmadas por versões
        anteriores continuam valendo pela referência e pelo hash gravados no banco."""
        sufixo = f"__exec-{execution}" if execution is not None else ""
        return self._run_dir(run_id) / f"{step_id}__{input_hash[:16]}{sufixo}.out"

    def _write_output(self, run_id: str, step_id: str, input_hash: str, data: bytes, *,
                      execution: int | None = None) -> tuple[str, str]:
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        out = self._output_path(run_id, step_id, input_hash, execution)  # conferida de novo depois de criar
        tmp = out.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, out)
        digest = sha256_bytes(data)
        # O recibo é registro para quem audita a pasta; NÃO comprova nada na retomada (quem escreve na
        # pasta do projeto poderia forjá-lo). A prova é a reserva gravada no banco antes do arquivo (#14).
        receipt = {"run_id": run_id, "step_id": step_id, "input_hash": input_hash, "output_hash": digest}
        if execution is not None:
            receipt["execution"] = execution
        rtmp = out.with_suffix(".receipt.tmp")
        rtmp.write_text(canonical_json(receipt), encoding="utf-8")
        os.replace(rtmp, out.with_suffix(".receipt.json"))
        return self._ref(out), digest

    def _descartar_saida(self, run_id: str, step_id: str, input_hash: str, execution: int) -> None:
        """Remove arquivo e recibo de uma geração que o banco não referencia (publicação desfeita)."""
        out = self._output_path(run_id, step_id, input_hash, execution)
        for caminho in (out, out.with_suffix(".receipt.json")):
            try:
                caminho.unlink()
            except OSError:
                pass  # sem referência no banco, o arquivo nunca é lido como saída

    def _saida_reservada_confere(self, run_id: str, row) -> bool:
        """Saída de uma posse interrompida entre gravar e confirmar (#14). Vale só a que o BANCO reservou
        para esta geração antes do arquivo (`output_ref` = caminho da geração, `output_hash`) e cujos
        bytes conferem. Recibo e nome de arquivo, que quem escreve na pasta do projeto forja, não
        confirmam nada: etapa sem reserva (inclusive a interrompida por versão anterior) volta à fila."""
        if not (row["input_hash"] and row["output_ref"] and row["output_hash"]):
            return False
        try:
            esperado = self._ref(self._output_path(run_id, row["step_id"], row["input_hash"], row["executions"]))
            if row["output_ref"] != esperado:
                return False
            self._verified_output(row)
        except PermanentError:
            return False
        return True

    # ------------------------------------------------------------ ciclo
    def _invalidate_changed(self, run_id: str, steps: list[StepDef], rows: dict) -> bool:
        """Invalida a primeira etapa concluída cuja entrada mudou ou cuja saída sumiu ou mudou (A04),
        e as derivadas dela."""
        for step in steps:
            row = rows[step.step_id]
            if row["state"] != "succeeded":
                continue
            if any(rows[d]["state"] != "succeeded" for d in step.depends_on):
                continue
            motivo = "invalidada: entrada alterada"
            try:
                self._verified_output(row)  # a própria saída, inclusive de etapa final (sem dependentes)
            except SaidaAlterada:
                current, motivo = None, "invalidada: saída ausente ou alterada"
            else:
                try:
                    current, _, _ = self._input_hash(run_id, step)
                except PermanentError:
                    current = None  # entrada sumiu (ou dependência inválida): trata como alterada
            if current == row["input_hash"]:
                continue
            for sid in [step.step_id, *sorted(self._dependents(steps, step.step_id))]:
                if rows[sid]["state"] == "succeeded":
                    self._set_step(run_id, sid, "pending", error=motivo)
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

    def _reservar(self, run_id: str, step: StepDef, input_hash: str | None, erro: str | None,
                  lease_seconds: float):
        """Reserva a etapa numa transação (A05/#11): autorização e estado conferidos de novo (outra
        conexão pode ter reservado, concluído ou cancelado) e geração nova da posse (`executions + 1`,
        nunca reaproveitada). A reserva limpa a saída de gerações anteriores.
        Devolve (tentativa, geração), None (nada a executar) ou "revogada"."""
        with transaction(self.con):
            if not self._ainda_autorizado("write"):
                return "revogada"
            row = self.con.execute(
                "SELECT s.state, s.attempts, s.executions, r.state AS run_state FROM step s"
                " JOIN run r ON r.run_id = s.run_id WHERE s.run_id = ? AND s.step_id = ? AND r.project_id = ?",
                (run_id, step.step_id, self.project_id)).fetchone()
            if row is None or row["state"] != "pending" or row["run_state"] == "cancelled":
                return None
            if erro or row["attempts"] >= step.max_attempts:
                self._set_step(run_id, step.step_id, "running")
                self._set_step(run_id, step.step_id, "failed", error=erro or "limite de tentativas atingido")
                return None
            attempt, execution = row["attempts"] + 1, row["executions"] + 1
            self._set_step(run_id, step.step_id, "running", attempts=attempt, executions=execution,
                           lease_until=time.time() + lease_seconds, input_hash=input_hash,
                           output_ref=None, output_hash=None)
            return attempt, execution

    def _registrar_desfecho(self, run_id: str, step: StepDef, attempt: int, execution: int,
                            kind: str, value: Any) -> str:
        """Desfecho sem saída (decisão humana, falha, negativa): só a posse atual o registra, com a
        autorização conferida na mesma transação. Devolve "ok", "perdida" ou "revogada"."""
        with transaction(self.con):
            if self._claim(run_id, step.step_id, execution) is None:
                return "perdida"  # cancelada ou assumida por outra geração: o estado do sucessor fica
            if not self._ainda_autorizado("write"):
                self._set_step(run_id, step.step_id, "pending", autorizar=False, lease_until=None,
                               error="autorização revogada durante a etapa; reenfileirada")
                return "revogada"
            if kind == "denied":
                # A negativa veio de outro recurso, não da revogação deste projeto.
                self._set_step(run_id, step.step_id, "failed", error="acesso negado durante a etapa")
            elif kind == "human":
                payload = {"question": value.question, "options": value.options}
                self._set_step(run_id, step.step_id, "waiting_human",
                               decision_json=canonical_json({**payload, "hash": sha256_json(payload)}))
            elif kind == "permanent":
                self._set_step(run_id, step.step_id, "failed", error=str(value)[:300])
            elif kind == "transient":
                self._set_step(run_id, step.step_id, "failed", error=str(value)[:300])
                if attempt < step.max_attempts:
                    self._set_step(run_id, step.step_id, "pending")
        return "ok"

    def _publicar(self, run_id: str, step: StepDef, input_hash: str, execution: int, value: Any,
                  interrupt: tuple[str, str] | None) -> str:
        """Publica a saída de uma posse em três tempos (A05/#11/#14):
        1) reserva no banco, numa transação que confere posse e autorização: `output_ref`/`output_hash`
           desta geração gravados ANTES do arquivo; é isso (e não o recibo) que comprova a saída numa
           retomada depois de queda;
        2) arquivo da geração gravado fora da transação (nome próprio: não alcança o de outra posse);
        3) confirmação, com posse e autorização conferidas de novo.
        Posse perdida ou revogação: nada é confirmado, e o arquivo que o banco deixou de referenciar é
        removido. Devolve "ok", "perdida" ou "revogada"."""
        data = value if isinstance(value, bytes) else str(value).encode("utf-8")
        digest = sha256_bytes(data)
        ref = self._ref(self._output_path(run_id, step.step_id, input_hash, execution))
        with transaction(self.con):
            if self._claim(run_id, step.step_id, execution) is None:
                return "perdida"
            if not self._ainda_autorizado("write"):
                # Revogada antes da gravação: a saída é descartada, nada é escrito.
                self._set_step(run_id, step.step_id, "pending", autorizar=False, lease_until=None,
                               error="autorização revogada antes da gravação; saída descartada")
                return "revogada"
            self.con.execute("UPDATE step SET output_ref = ?, output_hash = ?, updated_at = ?"
                             " WHERE run_id = ? AND step_id = ? AND executions = ? AND state = 'running'",
                             (ref, digest, utcnow(), run_id, step.step_id, execution))
        self._write_output(run_id, step.step_id, input_hash, data, execution=execution)
        if interrupt == (step.step_id, "before_commit"):
            raise SimulatedInterrupt(step.step_id)
        with transaction(self.con):
            row = self.con.execute(
                "SELECT s.state, s.executions, s.output_ref, r.state AS run_state FROM step s"
                " JOIN run r ON r.run_id = s.run_id WHERE s.run_id = ? AND s.step_id = ? AND r.project_id = ?",
                (run_id, step.step_id, self.project_id)).fetchone()
            if row is not None and row["executions"] == execution and row["output_ref"] == ref:
                if row["state"] == "succeeded":
                    return "ok"  # uma retomada já confirmou ESTA saída (mesma geração, bytes conferidos)
                if row["state"] != "running" or row["run_state"] == "cancelled":
                    return "perdida"  # cancelada: o arquivo fica como registro (o banco ainda o referencia)
                if self._ainda_autorizado("write"):
                    self._set_step(run_id, step.step_id, "succeeded", error=None, lease_until=None)
                    return "ok"
                self._set_step(run_id, step.step_id, "pending", autorizar=False, lease_until=None,
                               output_ref=None, output_hash=None,
                               error="autorização revogada antes da confirmação; saída descartada")
                desfecho = "revogada"
            else:
                desfecho = "perdida"  # outra geração assumiu, ou a retomada devolveu a etapa à fila
        self._descartar_saida(run_id, step.step_id, input_hash, execution)
        return desfecho

    def run(self, run_id: str, handlers: dict[str, Callable[[StepContext], Any]], *,
            interrupt: tuple[str, str] | None = None, lease_seconds: float = 60.0,
            max_parallel: int = 1) -> dict:
        """Executa etapas prontas. `max_parallel` > 1 roda etapas INDEPENDENTES em paralelo
        (horários de início/fim registrados no evento `step_timing`). O modo
        `interrupt=(step_id, 'before_commit'|'after_commit')` é um teste de retomada.
        A autorização é conferida antes de cada lote (antes de ler entradas) e de novo dentro de
        cada transação que reserva, debita, grava ou confirma; revogada no meio, a etapa volta a
        `pending` e a chamada levanta `AccessDenied` (F03/#11)."""
        self._autorizar("write")
        steps = self._steps(run_id)
        topo = validate_flow(steps)
        ordered = [next(s for s in steps if s.step_id == sid) for sid in topo]
        self._iniciar_prazo(run_id)
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
            if self._prazo_esgotado(run_id):
                events.emit(self.con, "budget_time_exhausted", project_id=self.project_id, run_id=run_id)
                return self._finish(run_id)
            prepared = []
            for step in ready[:max(1, max_parallel)]:
                erro = None
                try:
                    input_hash, inputs, upstream = self._input_hash(run_id, step)
                except SaidaAlterada:
                    continue  # dependência mudou desde a conferência: a próxima volta a invalida e refaz
                except PermanentError as exc:
                    input_hash, inputs, upstream, erro = None, {}, {}, str(exc)
                posse = self._reservar(run_id, step, input_hash, erro, lease_seconds)
                if posse == "revogada":
                    self._autorizar("write")  # registra a negativa e levanta AccessDenied
                    continue  # a permissão voltou entre as duas conferências
                if posse is None:
                    continue
                attempt, execution = posse
                prepared.append((step, attempt, input_hash,
                                 StepContext(run_id, step.step_id, attempt, inputs, upstream, self, execution)))
            if not prepared:
                continue
            if len(prepared) == 1:
                outcomes = [self._invoke(handlers[prepared[0][0].step_id], prepared[0][3])]
            else:
                with ThreadPoolExecutor(max_workers=len(prepared)) as pool:
                    futures = [pool.submit(self._invoke, handlers[p[0].step_id], p[3]) for p in prepared]
                    outcomes = [f.result() for f in futures]
            revogada = False
            for (step, attempt, input_hash, ctx), (kind, value, t0, t1) in zip(prepared, outcomes):
                events.emit(self.con, "step_timing", project_id=self.project_id, run_id=run_id,
                            payload={"step_id": step.step_id, "started": str(t0), "ended": str(t1),
                                     "parallel_batch": len(prepared)})
                if kind == "ok":
                    desfecho = self._publicar(run_id, step, input_hash, ctx._execution, value, interrupt)
                    if desfecho == "ok" and interrupt == (step.step_id, "after_commit"):
                        raise SimulatedInterrupt(step.step_id)
                else:
                    desfecho = self._registrar_desfecho(run_id, step, attempt, ctx._execution, kind, value)
                revogada = revogada or desfecho == "revogada"
            if revogada:
                self._autorizar("write")  # registra a negativa e levanta AccessDenied
        return self._finish(run_id)

    def _finish(self, run_id: str) -> dict:
        with transaction(self.con):
            # Estados lidos na mesma transação que grava o resumo (outra conexão não o deixa velho).
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
        Autorização e associação ao projeto vêm ANTES de ler ou mudar qualquer etapa (F02/F03), e a
        autorização é conferida de novo na transação de cada etapa (#11). Etapa `running` é
        confirmada se o banco reservou a saída DESTA geração e os bytes conferem (#14); senão, volta
        à fila quando a posse vence."""
        self._autorizar("write")
        self._run_row(run_id)
        now = time.time() if now is None else now
        for anterior in self.con.execute("SELECT step_id, executions FROM step WHERE run_id = ? AND state = 'running'",
                                         (run_id,)).fetchall():
            with transaction(self.con):
                row = self._claim(run_id, anterior["step_id"], anterior["executions"])
                if row is None:
                    continue  # mudou desde a leitura: confirmada, cancelada ou reservada por outra posse
                if self._saida_reservada_confere(run_id, row):
                    self._set_step(run_id, row["step_id"], "succeeded", error=None, lease_until=None)
                    events.emit(self.con, "step_reconciled", project_id=self.project_id,
                                run_id=run_id, payload={"step_id": row["step_id"]})
                elif row["lease_until"] is None or row["lease_until"] <= now:
                    self._set_step(run_id, row["step_id"], "pending", lease_until=None, output_ref=None,
                                   output_hash=None, error="posse expirada; reenfileirada")
        return self.run(run_id, handlers, **kwargs)

    def cancel(self, run_id: str) -> dict:
        self._autorizar("write")
        self._run_row(run_id)
        with transaction(self.con):
            # Execução e etapas canceladas juntas, com a autorização conferida na mesma transação (#11).
            self.policy.recheck(self.principal, "write", resource_project(self.project_id))
            self.con.execute("UPDATE run SET state = 'cancelled', updated_at = ? WHERE run_id = ? AND project_id = ?",
                             (utcnow(), run_id, self.project_id))
            for row in self._step_rows(run_id):
                if row["state"] in ("pending", "running", "waiting_human", "failed"):
                    self._set_step(run_id, row["step_id"], "cancelled")
        return self._finish(run_id)

    def decide(self, run_id: str, step_id: str, choice: str, approver: Principal, expected_hash: str) -> None:
        """Decisão humana vinculada ao conteúdo exato apresentado (hash), numa execução DESTE projeto.
        Autorizações de quem opera e de quem aprova, estado e hash são conferidos de novo na transação
        que grava a decisão (#11): revogação ou outra decisão confirmada no intervalo valem."""
        self._autorizar("write")
        self._run_row(run_id)
        recurso = resource_project(self.project_id)
        self.policy.require(approver, "approve", recurso)
        with transaction(self.con):
            self.policy.recheck(self.principal, "write", recurso)
            self.policy.recheck(approver, "approve", recurso)
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
            out_ref, out_hash = self._write_output(run_id, step_id, row["input_hash"] or "decisao",
                                                   choice.encode("utf-8"), execution=row["executions"])
            self._set_step(run_id, step_id, "succeeded", output_ref=out_ref, output_hash=out_hash,
                           decision_json=canonical_json({**decision, "choice": choice,
                                                         "approved_by": approver.principal_id}))
