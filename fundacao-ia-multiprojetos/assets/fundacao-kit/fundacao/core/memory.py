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
  diretos e indiretos registrados a partir delas (auditoria F07) — sem sair do escopo de
  onde cada aresta parte, salvo a publicação aprovada pela curadoria (auditoria #7).
- Aprovar, publicar ou retirar memória muda o corpus: incrementa a revisão de corpus do
  escopo (o comum vale para todos os projetos), o que invalida respostas guardadas, inclusive
  as negativas (auditorias A09/#23).
- A autorização é conferida de novo DENTRO de cada transação de escrita (auditoria #11), e a
  aprovação relê a revisão pendente ali: a leitura obsoleta é recusada (auditoria A10).
- Anti-envenenamento: quem propôs não aprova a própria proposta; registros com
  origem "documento" exigem aprovação humana como os demais (nunca automática).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from . import events, licoes, memory_queries, revisions
from .auth import Policy, Principal, resource_case, resource_project
from .canon import sha256_text
from .contracts import AccessDenied, NotFound, RevisionConflict, ValidationError
from .db import transaction, utcnow
from .ids import new_id

KINDS = {"fato", "hipotese", "decisao", "preferencia", "procedimento", "licao"}
ORIGINS = {"humano", "ia", "documento"}
CHANGE_KINDS = {"correcao", "mudanca_decisao"}
_ID_COM_VERSAO = re.compile(r"(.+)@([0-9]+)")
_FORMA_GOLD = re.compile(r"[a-z0-9-]+/.+@[0-9]+(?::.*)?")  # versão (`<projeto>/<id>@<n>`) ou trecho GOLD
_INTEIRO_MAXIMO = 2 ** 63 - 1  # maior INTEGER do SQLite


def recurso_da_memoria(scope: str, project_id: str | None, case_id: str | None) -> str:
    """Recurso de autorização de uma memória: 'common', 'project:<id>' ou 'case:<id>:<caso>'."""
    if scope == "common":
        return "common"
    if scope == "project":
        return resource_project(project_id or "")
    if scope == "case":
        return resource_case(project_id or "", case_id or "")
    raise ValidationError("escopo inválido", scope=scope)


def separar_versao(entidade: str) -> tuple[str, int] | None:
    """`(id, n)` para `id@n` com n inteiro que o SQLite guarda; None para os demais identificadores."""
    m = _ID_COM_VERSAO.fullmatch(entidade)
    if m is None or int(m[2]) > _INTEIRO_MAXIMO:
        return None
    return m[1], int(m[2])


def entidade_conhecida(con: sqlite3.Connection, entidade: str) -> tuple[str, str] | None:
    """`(tipo, recurso)` de uma entidade que o kit conhece — 'memoria' (`id` ou `id@revisão`), 'trecho'
    ou 'fonte' (versão GOLD, `id@versão`) — ou None para identificador externo (artefato)."""
    sql_mem = "SELECT scope, project_id, case_id FROM memory_item WHERE memory_id = ?"
    mem = con.execute(sql_mem, (entidade,)).fetchone()
    versao = separar_versao(entidade)
    if mem is None and versao:
        mem = con.execute(sql_mem, (versao[0],)).fetchone()
    if mem is not None:
        return "memoria", recurso_da_memoria(mem[0], mem[1], mem[2])
    trecho = con.execute("SELECT resource FROM chunk WHERE chunk_id = ?", (entidade,)).fetchone()
    if trecho is not None:
        return "trecho", trecho[0]
    if versao:
        src = con.execute("SELECT project_id, case_id FROM source_version WHERE source_id = ? AND version = ?",
                          versao).fetchone()
        if src is not None:
            return "fonte", resource_case(src[0], src[1]) if src[1] else resource_project(src[0])
    return None


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
        return recurso_da_memoria(scope, project_id, case_id)

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
        dados_licao = licoes.validar_proposta(kind, scope, project_id, case_id, body, source_ref, effective_from)
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
            licoes.indexar(self.con, memory_id, 1, project_id, dados_licao)
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
            # Releitura autoritativa DENTRO da transação (BEGIN IMMEDIATE serializa as gravações): a leitura de
            # antes pode ser de uma revisão que outra aprovação já substituiu, ou de memória retirada no
            # intervalo (auditoria A10), e a concessão pode ter sido revogada no intervalo (auditoria #11).
            self.policy.recheck(self.principal, "approve", resource)
            vigencia = self.con.execute("SELECT status FROM memory_item WHERE memory_id = ?", (memory_id,)).fetchone()
            if vigencia["status"] == "withdrawn" or self._retirada(memory_id):
                raise ValidationError("memória retirada não volta a vigorar por aprovação; proponha novo registro")
            atual = self._latest_revision(memory_id)
            if (atual is None or atual["state"] != "proposed" or atual["revision"] != rev["revision"]
                    or atual["body_hash"] != expected_hash):
                raise RevisionConflict("a revisão pendente mudou durante a aprovação; releia e revise a atual",
                                       expected=rev["revision"], current=atual["revision"] if atual else None)
            if atual["editor_subject"] == self.principal.principal_id:
                raise AccessDenied("quem propôs não aprova a própria proposta")
            rev = atual
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
            # A memória vigente compõe o corpus: respostas guardadas (inclusive "nada encontrado") deixam de
            # valer; no comum, em todos os projetos (auditorias A09/#23).
            revisions.incrementar_alcance(self.con, resource, "corpus_rev")
            events.emit(self.con, "memory_approved", project_id=row["project_id"],
                        subject=self.principal.principal_id,
                        payload={"memory_id": memory_id, "revision": rev["revision"]})
        return rev["revision"]

    def query(self, *, project_id: str | None = None, case_id: str | None = None,
              include_common: bool = True, text: str | None = None) -> list[dict]:
        """Somente revisões vigentes aprovadas que a identidade pode ler."""
        return memory_queries.consultar(self, project_id=project_id, case_id=case_id,
                                        include_common=include_common, text=text)

    def query_licoes(self, *, project_id: str, gatilho: str) -> list[dict]:
        """Lições aprovadas vigentes, por gatilho autorizado do projeto."""
        return memory_queries.consultar_licoes(self, project_id=project_id, gatilho=gatilho)

    def revise(self, memory_id: str, *, expected_revision: int, body: str, source_ref: str,
               reason: str, change_kind: str) -> int:
        if change_kind not in CHANGE_KINDS:
            raise ValidationError("change_kind deve ser 'correcao' ou 'mudanca_decisao'")
        if not source_ref.strip() or not reason.strip():
            raise ValidationError("correção exige fonte e motivo")
        row = self._row(memory_id)
        resource = self._resource(row["scope"], row["project_id"], row["case_id"])
        self.policy.require(self.principal, "write", resource)
        dados_licao = licoes.validar(body, source_ref) if row["kind"] == "licao" else None
        with transaction(self.con):
            self.policy.recheck(self.principal, "write", resource)  # revogação no intervalo (auditoria #11)
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
            licoes.indexar(self.con, memory_id, new_rev, row["project_id"], dados_licao)
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
        """Todas as revisões, com o conteúdo. Mesmo mapeamento das demais operações: memória de caso
        exige auditoria NO CASO (e leitura do projeto, pela política), não só no projeto (auditoria #15)."""
        row = self._row(memory_id)
        resource = self._resource(row["scope"], row["project_id"], row["case_id"])
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
            self.policy.recheck(self.principal, "approve", resource)  # revogação no intervalo (auditoria #11)
            ignoradas: list[dict] = []
            affected = withdrawal_closure(self.con, memory_id, ignoradas=ignoradas)
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
            # Cada escopo que perdeu memória vigente muda de corpus (no comum, todos os projetos; A09/#23).
            escopos = {recurso_da_memoria(*r) for r in self.con.execute(
                f"SELECT scope, project_id, case_id FROM memory_item WHERE memory_id IN ({marcas})", affected)}
            for recurso in sorted(escopos):
                revisions.incrementar_alcance(self.con, recurso, "corpus_rev")
            events.emit(self.con, "memory_withdrawn", project_id=row["project_id"],
                        subject=self.principal.principal_id,
                        payload={"affected": affected, "promocoes_canceladas": canceladas,
                                 **({"arestas_ignoradas": ignoradas} if ignoradas else {})})
            enqueue_protected(self.con, {  # outbox na mesma transação (F11)
                "entity_type": "memory", "entity_id": memory_id, "affected": affected,
                "project_id": row["project_id"], "decided_by": self.principal.principal_id,
                "reason": reason, "decided_at": utcnow()})
        flush_outbox(self.con, self.tombstone_log)
        return affected

    def record_derivation(self, memory_id: str, revision: int, derived_id: str) -> None:
        """Registra que um artefato (ex.: relatório) usou memory_id@revision.

        A aresta decide o alcance de retiradas futuras; por isso é autorizada e tipada (auditoria #7):
        quem registra precisa ler a memória de origem, a revisão precisa existir e o derivado precisa ser
        um artefato. Memória (`id` ou `id@revisão`) e versão ou trecho GOLD — inclusive identificador no
        formato `<projeto>/<id>@<versão>` — não entram por aqui: têm ciclo de vida e retirada próprios, e
        de memória para memória o único caminho é a promoção com curadoria."""
        row = self._row(memory_id)
        resource = self._resource(row["scope"], row["project_id"], row["case_id"])
        self.policy.require(self.principal, "read", resource)
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise ValidationError("revisão de origem deve ser um número inteiro")
        if not isinstance(derived_id, str) or not derived_id.strip() or derived_id != derived_id.strip():
            raise ValidationError("identificador do derivado vazio ou com espaços nas bordas")
        if _FORMA_GOLD.fullmatch(derived_id):
            raise ValidationError("identificador no formato de fonte GOLD não é derivado de memória")
        with transaction(self.con):
            self.policy.recheck(self.principal, "read", resource)  # revogação no intervalo (auditoria #11)
            if self.con.execute("SELECT 1 FROM memory_revision WHERE memory_id = ? AND revision = ?",
                                (memory_id, revision)).fetchone() is None:
                raise ValidationError("revisão de origem inexistente")
            if entidade_conhecida(self.con, derived_id) is not None:
                raise ValidationError("o derivado deve ser um artefato: memória e fonte GOLD têm ciclo de vida "
                                      "próprio (de memória para memória, só a promoção)")
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
            self.policy.recheck(self.principal, "read", resource)  # revogação no intervalo (auditoria #11)
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

    def _origem_fora_de_vigencia(self, promo: sqlite3.Row) -> bool:
        origem = self.con.execute("SELECT status FROM memory_item WHERE memory_id = ?",
                                  (promo["source_memory_id"],)).fetchone()
        return origem is None or origem["status"] != "approved" or self._retirada(promo["source_memory_id"])

    def _origem_impede(self, promo: sqlite3.Row) -> str | None:
        """Motivo para a origem não sustentar mais a publicação (retirada, fora de vigência, mudada desde o
        pedido ou sem vínculo que prove o contrário), ou None. Conferido antes e DENTRO da transação da
        decisão (F06)."""
        if self._origem_fora_de_vigencia(promo):
            return "a origem foi retirada ou deixou de estar aprovada"
        if promo["source_revision"] is None or promo["source_hash"] is None:
            # Pedido anterior ao vínculo (kit < 1.4.0; colunas criadas pela migração 3): nada prova que o
            # candidato saiu da revisão vigente. Falha fechada: só a recusa continua possível (auditoria #19).
            return ("candidato sem vínculo com a revisão da origem (pedido anterior à 1.4.0); recuse-o e peça "
                    "um novo a partir da revisão vigente")
        origem = self.con.execute("SELECT revision, approved_hash FROM memory_item WHERE memory_id = ?",
                                  (promo["source_memory_id"],)).fetchone()
        if origem["revision"] != promo["source_revision"] or origem["approved_hash"] != promo["source_hash"]:
            return "a origem mudou desde o pedido; prepare um novo candidato a partir da revisão vigente"
        return None

    def decide_promotion(self, promotion_id: str, approve: bool, expected_hash: str) -> str | None:
        self.policy.require(self.principal, "curate", "common")
        promo = self.con.execute("SELECT * FROM promotion WHERE promotion_id = ?", (promotion_id,)).fetchone()
        if promo is None or promo["decision"] != "pending":
            if promo is not None and self._origem_fora_de_vigencia(promo):
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
            self.policy.recheck(self.principal, "curate", "common")  # revogação no intervalo (auditoria #11)
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
                # Publicar no comum muda o corpus de todos os projetos (caches negativos inclusive; A09).
                revisions.incrementar_alcance(self.con, "common", "corpus_rev")
            self.con.execute(
                "UPDATE promotion SET decision = ?, decided_by = ?, decided_at = ?, published_memory_id = ?"
                " WHERE promotion_id = ?",
                ("approved" if approve else "rejected", self.principal.principal_id, now, published,
                 promotion_id),
            )
            events.emit(self.con, "promotion_decided", subject=self.principal.principal_id,
                        payload={"promotion_id": promotion_id, "approved": approve})
        return published


def _segue_aresta(con: sqlite3.Connection, pai: str, filho: str, escopo_raiz: str | None) -> bool:
    """Se a retirada segue a aresta `pai` -> `filho` (auditoria #7). Artefato (identificador que o kit não
    conhece): sim. Memória (ou `memória@revisão`): só no MESMO escopo da memória retirada — que quem retira
    já pode retirar — ou pela aresta da publicação aprovada pela curadoria. Versão ou trecho GOLD (e
    identificador nesse formato): nunca; têm retirada própria."""
    if _FORMA_GOLD.fullmatch(filho):
        return False
    conhecida = entidade_conhecida(con, filho)
    if conhecida is None:
        return True
    tipo, recurso = conhecida
    if tipo != "memoria":
        return False
    if escopo_raiz is not None and recurso == escopo_raiz:
        return True
    return con.execute("SELECT 1 FROM promotion WHERE source_memory_id = ? AND published_memory_id = ?"
                       " AND decision = 'approved'", (pai, filho)).fetchone() is not None


def withdrawal_closure(con: sqlite3.Connection, memory_id: str, *, ignoradas: list | None = None) -> list[str]:
    """Tudo o que a retirada de `memory_id` alcança: a memória, as chaves por revisão
    (`id@revisão`, usadas por `record_derivation`) e os derivados diretos e indiretos registrados a
    partir de qualquer uma delas — inclusive as revisões de memórias derivadas. Só arestas exatas
    da tabela de dependências: nada é alcançado por coincidência de prefixo (auditoria F07). E sem
    sair do escopo de quem retira (auditoria #7): memória de outro escopo (o comum, outro projeto, um
    caso) só é alcançada pela aresta da publicação aprovada pela curadoria; versão ou trecho GOLD,
    nunca (têm retirada própria). Assim, aresta gravada sem validação por kit anterior não leva a
    retirada a memória que quem retira não poderia retirar; as recusadas vão para `ignoradas`, quando
    informada. É a mesma resolução usada pela reconstrução do registro protegido (`backup`) e pelo
    reparo do `init`."""
    ordem: list[str] = []
    vistos: set[str] = set()
    raiz = con.execute("SELECT scope, project_id, case_id FROM memory_item WHERE memory_id = ?",
                       (memory_id,)).fetchone()
    escopo_raiz = recurso_da_memoria(raiz[0], raiz[1], raiz[2]) if raiz else None
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
                                        (chave,)).fetchall():
                if filho in vistos:
                    continue
                if _segue_aresta(con, chave, filho, escopo_raiz):
                    fila.append(filho)
                elif ignoradas is not None:
                    ignoradas.append({"de": chave, "para": filho})
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
