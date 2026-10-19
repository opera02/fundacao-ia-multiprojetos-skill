"""Memória persistente autorizada (livro A12–A14; proposta 3.0 R5.x).

- Registro externo à conversa, com escopo (comum/projeto/caso), tipo epistêmico
  (fato/hipótese/decisão/preferência/procedimento), origem (humano/IA/documento),
  estado, revisão, fonte e responsável.
- A consulta filtra pela política ANTES de devolver qualquer conteúdo e entrega
  somente a revisão vigente aprovada; correções pendentes não somem com a vigente.
- Correção versionada com revisão esperada: conflito é detectado, nunca sobrescrito.
- Estado corrente, revisão e evento gravados na mesma transação.
- Promoção ao comum: candidato depurado, aprovação ligada ao hash exato, novo
  registro (o original restrito permanece). O candidato fica vinculado à revisão e ao
  hash da origem; origem retirada, fora de vigência ou mudada desde o pedido impede a
  publicação, e retirar a origem encerra os candidatos pendentes (auditoria F06).
- Retirada alcança a memória, suas chaves por revisão (`id@revisão`) e os derivados
  diretos e indiretos registrados a partir delas (auditoria F07).
- Anti-envenenamento: quem propôs não aprova a própria proposta; registros com
  origem "documento" exigem aprovação humana como os demais (nunca automática).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import events
from .auth import Policy, Principal, resource_case, resource_project
from .canon import sha256_text
from .contracts import AccessDenied, NotFound, RevisionConflict, ValidationError
from .db import transaction, utcnow
from .ids import new_id

KINDS = {"fato", "hipotese", "decisao", "preferencia", "procedimento"}
ORIGINS = {"humano", "ia", "documento"}
CHANGE_KINDS = {"correcao", "mudanca_decisao"}


class MemoryService:
    def __init__(self, con: sqlite3.Connection, principal: Principal, tombstone_log: Path | None = None):
        self.con = con
        self.principal = principal
        self.policy = Policy(con)
        # Registro protegido de retiradas (fora do backup), o mesmo usado pelas fontes:
        # sem ele, a restauração faria a memória eliminada reaparecer.
        self.tombstone_log = Path(tombstone_log) if tombstone_log else None

    @staticmethod
    def _resource(scope: str, project_id: str | None, case_id: str | None) -> str:
        if scope == "common":
            return "common"
        if scope == "project":
            return resource_project(project_id or "")
        if scope == "case":
            return resource_case(project_id or "", case_id or "")
        raise ValidationError("escopo inválido", scope=scope)

    def _row(self, memory_id: str) -> sqlite3.Row:
        row = self.con.execute("SELECT * FROM memory_item WHERE memory_id = ?", (memory_id,)).fetchone()
        if row is None:
            raise NotFound("memória não encontrada")
        return row

    def _latest_revision(self, memory_id: str) -> sqlite3.Row:
        return self.con.execute(
            "SELECT * FROM memory_revision WHERE memory_id = ? ORDER BY revision DESC LIMIT 1",
            (memory_id,),
        ).fetchone()

    def propose(self, *, op_id: str, scope: str, kind: str, origin: str, body: str,
                source_ref: str, project_id: str | None = None, case_id: str | None = None,
                effective_from: str | None = None) -> str:
        if kind not in KINDS or origin not in ORIGINS:
            raise ValidationError("tipo ou origem inválidos", kind=kind, origin=origin)
        if not source_ref or not source_ref.strip():
            raise ValidationError("memória sem origem é recusada; informe source_ref")
        if not body.strip():
            raise ValidationError("conteúdo vazio")
        resource = self._resource(scope, project_id, case_id)
        self.policy.require(self.principal, "write", resource)
        chave = f"{resource}::{op_id}"  # operação idempotente DENTRO do escopo
        existing = self.con.execute("SELECT result_ref FROM op_key WHERE op_id = ?", (chave,)).fetchone()
        if existing:
            return existing["result_ref"]  # repetir a mesma operação não duplica o registro
        memory_id = new_id("mem")
        now = utcnow()
        digest = sha256_text(body)
        with transaction(self.con):
            self.policy.recheck(self.principal, "write", resource)
            self.con.execute(
                "INSERT INTO memory_item VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (memory_id, scope, project_id, case_id, kind, origin, "proposed", 1, body, digest,
                 source_ref, self.principal.principal_id, None, None, effective_from, now),
            )
            self.con.execute(
                "INSERT INTO memory_revision VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (memory_id, 1, body, digest, source_ref, "criação", "criacao",
                 self.principal.principal_id, now, "proposed", None, None),
            )
            self.con.execute("INSERT INTO op_key VALUES (?,?,?,?)", (chave, "memory.propose", memory_id, now))
            events.emit(self.con, "memory_proposed", project_id=project_id, subject=self.principal.principal_id,
                        payload={"memory_id": memory_id, "scope": scope, "origin": origin})
        return memory_id

    def pending_hash(self, memory_id: str) -> tuple[int, str]:
        """Revisão pendente e seu hash, para o revisor aprovar o conteúdo exato."""
        row = self.con.execute("SELECT * FROM memory_item WHERE memory_id = ?", (memory_id,)).fetchone()
        rev = None
        if row is not None:
            resource = self._resource(row["scope"], row["project_id"], row["case_id"])
            if self.policy.allowed(self.principal.principal_id, "read", resource):
                rev = self._latest_revision(memory_id)
            else:
                # alheia responde igual a inexistente; a sondagem fica registrada
                events.emit(self.con, "access_denied", subject=self.principal.principal_id,
                            payload={"action": "read", "resource": resource, "source": self.principal.source})
        if rev is None or rev["state"] != "proposed":
            raise ValidationError("não há revisão pendente")
        return rev["revision"], rev["body_hash"]

    def approve(self, memory_id: str, expected_hash: str) -> int:
        row = self._row(memory_id)
        resource = self._resource(row["scope"], row["project_id"], row["case_id"])
        self.policy.require(self.principal, "approve", resource)
        rev = self._latest_revision(memory_id)
        if rev is None or rev["state"] != "proposed":
            raise ValidationError("não há revisão pendente de aprovação")
        if rev["editor_subject"] == self.principal.principal_id:
            raise AccessDenied("quem propôs não aprova a própria proposta")
        if rev["body_hash"] != expected_hash:
            raise ValidationError("o conteúdo mudou após a revisão; aprovação recusada")
        now = utcnow()
        with transaction(self.con):
            self.con.execute(
                "UPDATE memory_revision SET state = 'superseded' WHERE memory_id = ? AND state = 'approved'",
                (memory_id,),
            )
            self.con.execute(
                "UPDATE memory_revision SET state = 'approved', approved_by = ?, approved_at = ?"
                " WHERE memory_id = ? AND revision = ?",
                (self.principal.principal_id, now, memory_id, rev["revision"]),
            )
            self.con.execute(
                "UPDATE memory_item SET status = 'approved', revision = ?, body = ?, body_hash = ?,"
                " source_ref = ?, approved_by = ?, approved_hash = ?, recorded_at = ? WHERE memory_id = ?",
                (rev["revision"], rev["body"], rev["body_hash"], rev["source_ref"],
                 self.principal.principal_id, expected_hash, now, memory_id),
            )
            events.emit(self.con, "memory_approved", project_id=row["project_id"],
                        subject=self.principal.principal_id,
                        payload={"memory_id": memory_id, "revision": rev["revision"]})
        return rev["revision"]

    def query(self, *, project_id: str | None = None, case_id: str | None = None,
              include_common: bool = True, text: str | None = None) -> list[dict]:
        """Somente revisões vigentes aprovadas que a identidade pode ler."""
        out = []
        for row in self.con.execute(
            "SELECT * FROM memory_item WHERE status = 'approved' ORDER BY recorded_at"
        ).fetchall():
            if row["scope"] == "common":
                if not include_common:
                    continue
            elif row["project_id"] != project_id:
                continue
            if row["scope"] == "case" and row["case_id"] != case_id:
                continue
            resource = self._resource(row["scope"], row["project_id"], row["case_id"])
            if not self.policy.allowed(self.principal.principal_id, "read", resource):
                continue  # filtrado antes de qualquer entrega
            if self.con.execute("SELECT 1 FROM tombstone WHERE entity_id = ?", (row["memory_id"],)).fetchone():
                continue
            if text and text.lower() not in row["body"].lower():
                continue
            out.append({
                "memory_id": row["memory_id"], "revision": row["revision"], "scope": row["scope"],
                "kind": row["kind"], "origin": row["origin"], "body": row["body"],
                "source_ref": row["source_ref"], "approved_by": row["approved_by"],
            })
        return out

    def revise(self, memory_id: str, *, expected_revision: int, body: str, source_ref: str,
               reason: str, change_kind: str) -> int:
        if change_kind not in CHANGE_KINDS:
            raise ValidationError("change_kind deve ser 'correcao' ou 'mudanca_decisao'")
        if not source_ref.strip() or not reason.strip():
            raise ValidationError("correção exige fonte e motivo")
        row = self._row(memory_id)
        resource = self._resource(row["scope"], row["project_id"], row["case_id"])
        self.policy.require(self.principal, "write", resource)
        with transaction(self.con):
            latest = self._latest_revision(memory_id)["revision"]
            if latest != expected_revision:
                raise RevisionConflict(
                    "revisão desatualizada: releia a vigente e compare antes de gravar",
                    expected=expected_revision, current=latest,
                )
            new_rev = latest + 1
            now = utcnow()
            self.con.execute(
                "INSERT INTO memory_revision VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (memory_id, new_rev, body, sha256_text(body), source_ref, reason, change_kind,
                 self.principal.principal_id, now, "proposed", None, None),
            )
            for dep in self.con.execute(
                "SELECT child_id FROM dependency WHERE parent_id = ?", (f"{memory_id}@{row['revision']}",)
            ).fetchall():
                events.emit(self.con, "derived_needs_review", project_id=row["project_id"],
                            payload={"derived_id": dep["child_id"], "memory_id": memory_id,
                                     "from_revision": row["revision"]})
            events.emit(self.con, "memory_revision_proposed", project_id=row["project_id"],
                        subject=self.principal.principal_id,
                        payload={"memory_id": memory_id, "revision": new_rev, "change_kind": change_kind})
        return new_rev

    def history(self, memory_id: str) -> list[dict]:
        row = self._row(memory_id)
        resource = "common" if row["scope"] == "common" else resource_project(row["project_id"])
        self.policy.require(self.principal, "audit", resource)
        return [dict(r) for r in self.con.execute(
            "SELECT revision, state, body, source_ref, reason, change_kind, editor_subject, recorded_at,"
            " approved_by FROM memory_revision WHERE memory_id = ? ORDER BY revision", (memory_id,))]

    def withdraw(self, memory_id: str, reason: str) -> list[str]:
        """Retira a memória e propaga a retirada aos derivados (publicação no comum, artefatos
        registrados por `memory_id@revisão`, derivados indiretos) e encerra candidatos pendentes."""
        row = self._row(memory_id)
        resource = self._resource(row["scope"], row["project_id"], row["case_id"])
        self.policy.require(self.principal, "approve", resource)
        from .backup import enqueue_protected, flush_outbox  # import tardio evita ciclo
        with transaction(self.con):
            affected = withdrawal_closure(self.con, memory_id)
            agora = utcnow()
            for entity in affected:
                self.con.execute(
                    "INSERT INTO tombstone VALUES (?,?,?,?,?,?) ON CONFLICT(entity_id) DO NOTHING",
                    (entity, row["project_id"], self.principal.principal_id, reason, agora, "done"),
                )
                self.con.execute("UPDATE memory_item SET status = 'withdrawn' WHERE memory_id = ?", (entity,))
            # Candidato pendente cuja origem saiu de vigência não pode mais ser publicado (F06).
            marcas = ",".join("?" * len(affected))
            canceladas = [r[0] for r in self.con.execute(
                f"SELECT promotion_id FROM promotion WHERE decision = 'pending' AND source_memory_id IN ({marcas})",
                affected)]
            for pid in canceladas:
                self.con.execute("UPDATE promotion SET decision = 'rejected', decided_by = ?, decided_at = ?"
                                 " WHERE promotion_id = ? AND decision = 'pending'",
                                 (self.principal.principal_id, agora, pid))
            events.emit(self.con, "memory_withdrawn", project_id=row["project_id"],
                        subject=self.principal.principal_id,
                        payload={"affected": affected, "promocoes_canceladas": canceladas})
            enqueue_protected(self.con, {  # outbox na mesma transação (F11)
                "entity_type": "memory", "entity_id": memory_id, "affected": affected,
                "project_id": row["project_id"], "decided_by": self.principal.principal_id,
                "reason": reason, "decided_at": utcnow()})
        flush_outbox(self.con, self.tombstone_log)
        return affected

    def record_derivation(self, memory_id: str, revision: int, derived_id: str) -> None:
        """Registra que um artefato (ex.: relatório) usou memory_id@revision."""
        with transaction(self.con):
            self.con.execute(
                "INSERT INTO dependency (parent_id, child_id, relation) VALUES (?,?,?) ON CONFLICT DO NOTHING",
                (f"{memory_id}@{revision}", derived_id, "used"),
            )

    # ------------------------------------------------------------ promoção
    def request_promotion(self, memory_id: str, candidate_body: str, justification: str) -> tuple[str, str]:
        row = self._row(memory_id)
        resource = self._resource(row["scope"], row["project_id"], row["case_id"])
        self.policy.require(self.principal, "read", resource)
        if row["status"] != "approved" or self._retirada(memory_id):
            raise ValidationError("só memória aprovada pode originar candidato à base comum")
        promotion_id = new_id("promo")
        digest = sha256_text(candidate_body)
        with transaction(self.con):
            # O candidato fica vinculado à revisão e ao hash da origem no momento do pedido (F06).
            self.con.execute(
                "INSERT INTO promotion (promotion_id, source_memory_id, candidate_body, candidate_hash,"
                " justification, requested_by, requested_at, decision, decided_by, decided_at,"
                " published_memory_id, source_revision, source_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (promotion_id, memory_id, candidate_body, digest, justification,
                 self.principal.principal_id, utcnow(), "pending", None, None, None,
                 row["revision"], row["approved_hash"]),
            )
            events.emit(self.con, "promotion_requested", project_id=row["project_id"],
                        subject=self.principal.principal_id, payload={"promotion_id": promotion_id})
        return promotion_id, digest

    def _retirada(self, entity_id: str) -> bool:
        return self.con.execute("SELECT 1 FROM tombstone WHERE entity_id = ?", (entity_id,)).fetchone() is not None

    def _origem_impede(self, promo: sqlite3.Row) -> str | None:
        """Motivo para a origem não sustentar mais a publicação (retirada, fora de vigência ou mudada
        desde o pedido), ou None. Conferido antes e DENTRO da transação da decisão (F06)."""
        origem = self.con.execute("SELECT status, revision, approved_hash FROM memory_item WHERE memory_id = ?",
                                  (promo["source_memory_id"],)).fetchone()
        if origem is None or origem["status"] != "approved" or self._retirada(promo["source_memory_id"]):
            return "a origem foi retirada ou deixou de estar aprovada"
        if promo["source_revision"] is not None and (origem["revision"] != promo["source_revision"]
                                                     or origem["approved_hash"] != promo["source_hash"]):
            return "a origem mudou desde o pedido; prepare um novo candidato a partir da revisão vigente"
        return None

    def decide_promotion(self, promotion_id: str, approve: bool, expected_hash: str) -> str | None:
        self.policy.require(self.principal, "curate", "common")
        promo = self.con.execute("SELECT * FROM promotion WHERE promotion_id = ?", (promotion_id,)).fetchone()
        if promo is None or promo["decision"] != "pending":
            if promo is not None and self._origem_impede(promo):
                raise ValidationError("promoção encerrada: a origem foi retirada; nada foi publicado")
            raise ValidationError("promoção inexistente ou já decidida")
        if promo["requested_by"] == self.principal.principal_id:
            raise AccessDenied("quem pediu a promoção não a aprova")
        if sha256_text(promo["candidate_body"]) != expected_hash or promo["candidate_hash"] != expected_hash:
            events.emit(self.con, "promotion_blocked_hash", subject=self.principal.principal_id,
                        payload={"promotion_id": promotion_id})
            raise ValidationError("candidato alterado após a revisão; publicação recusada")
        if approve:
            motivo = self._origem_impede(promo)
            if motivo:
                events.emit(self.con, "promotion_blocked_origin", subject=self.principal.principal_id,
                            payload={"promotion_id": promotion_id, "motivo": motivo})
                raise ValidationError(f"publicação recusada: {motivo}")
        now = utcnow()
        published = None
        with transaction(self.con):
            atual = self.con.execute("SELECT * FROM promotion WHERE promotion_id = ?", (promotion_id,)).fetchone()
            if atual["decision"] != "pending" or atual["candidate_hash"] != expected_hash:
                raise ValidationError("promoção decidida ou alterada durante a curadoria; nada foi publicado")
            if approve and self._origem_impede(atual):
                raise ValidationError("publicação recusada: a origem mudou durante a curadoria")
            if approve:
                published = new_id("mem")
                self.con.execute(
                    "INSERT INTO memory_item VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (published, "common", None, None, "procedimento", "humano", "approved", 1,
                     promo["candidate_body"], expected_hash, f"promocao:{promotion_id}",
                     promo["requested_by"], self.principal.principal_id, expected_hash, None, now),
                )
                self.con.execute(
                    "INSERT INTO memory_revision VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (published, 1, promo["candidate_body"], expected_hash, f"promocao:{promotion_id}",
                     "publicação aprovada", "criacao", promo["requested_by"], now, "approved",
                     self.principal.principal_id, now),
                )
                self.con.execute(
                    "INSERT INTO dependency (parent_id, child_id, relation) VALUES (?,?,?)",
                    (promo["source_memory_id"], published, "wasDerivedFrom"),
                )
            self.con.execute(
                "UPDATE promotion SET decision = ?, decided_by = ?, decided_at = ?, published_memory_id = ?"
                " WHERE promotion_id = ?",
                ("approved" if approve else "rejected", self.principal.principal_id, now, published,
                 promotion_id),
            )
            events.emit(self.con, "promotion_decided", subject=self.principal.principal_id,
                        payload={"promotion_id": promotion_id, "approved": approve})
        return published


def withdrawal_closure(con: sqlite3.Connection, memory_id: str) -> list[str]:
    """Tudo o que a retirada de `memory_id` alcança: a memória, as chaves por revisão
    (`id@revisão`, usadas por `record_derivation`) e os derivados diretos e indiretos registrados a
    partir de qualquer uma delas — inclusive as revisões de memórias derivadas. Só arestas exatas
    da tabela de dependências: nada é alcançado por coincidência de prefixo (auditoria F07).
    É a mesma resolução usada pela reconstrução do registro protegido (`backup`)."""
    ordem: list[str] = []
    vistos: set[str] = set()
    fila = [memory_id]
    while fila:
        atual = fila.pop(0)
        if atual in vistos:
            continue
        vistos.add(atual)
        ordem.append(atual)
        chaves = [atual]
        if con.execute("SELECT 1 FROM memory_item WHERE memory_id = ?", (atual,)).fetchone():
            for (rev,) in con.execute("SELECT revision FROM memory_revision WHERE memory_id = ? ORDER BY revision",
                                      (atual,)):
                chave = f"{atual}@{rev}"
                if chave not in vistos:
                    vistos.add(chave)
                    ordem.append(chave)
                    chaves.append(chave)
        for chave in chaves:
            for (filho,) in con.execute("SELECT child_id FROM dependency WHERE parent_id = ? ORDER BY child_id",
                                        (chave,)):
                if filho not in vistos:
                    fila.append(filho)
    return ordem


def repair_withdrawn_derivations(con: sqlite3.Connection) -> list[dict]:
    """Para memórias já retiradas (inclusive por kit anterior à 1.4.0, que não percorria as chaves
    por revisão), marca como retirados os derivados que ainda estavam consumíveis. Idempotente;
    o `init` chama e registra o resultado no registro protegido."""
    reparos = []
    for row in con.execute(
            "SELECT t.entity_id, t.project_id, t.decided_by, t.reason FROM tombstone t"
            " JOIN memory_item m ON m.memory_id = t.entity_id ORDER BY t.decided_at, t.entity_id").fetchall():
        mid = row[0]
        alcance = withdrawal_closure(con, mid)
        novos = [i for i in alcance if not con.execute("SELECT 1 FROM tombstone WHERE entity_id = ?", (i,)).fetchone()]
        if not novos:
            continue
        from .backup import enqueue_protected  # import tardio evita ciclo
        with transaction(con):
            agora = utcnow()
            for i in novos:
                con.execute("INSERT INTO tombstone VALUES (?,?,?,?,?,?) ON CONFLICT(entity_id) DO NOTHING",
                            (i, row[1], row[2] or "desconhecido", f"derivado de {mid} (reparo na atualização)", agora,
                             "done"))
                con.execute("UPDATE memory_item SET status = 'withdrawn' WHERE memory_id = ?", (i,))
            events.emit(con, "memory_withdrawal_repaired", project_id=row[1],
                        payload={"memory_id": mid, "novos": novos})
            enqueue_protected(con, {"entity_type": "memory", "entity_id": mid, "affected": alcance,
                                    "project_id": row[1], "decided_by": row[2] or "desconhecido",
                                    "reason": row[3] or "", "decided_at": utcnow(),
                                    "origem": "reparo-na-atualizacao"})
        reparos.append({"memory_id": mid, "project_id": row[1], "decided_by": row[2] or "desconhecido",
                        "reason": row[3] or "", "affected": alcance, "novos": novos})
    return reparos
