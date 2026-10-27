"""GOLD (curadoria) e RAG lexical com autorização (livro A15–A18; proposta 3.0 R6/R7).

Fluxo: registrar fonte (original imutável) -> preparar (texto por página, hash do
derivado) -> curar com rubrica de 5 critérios -> aprovar o hash exato -> indexar
em trechos com receita versionada e IDs determinísticos -> recuperar com a
autorização aplicada NO SQL, antes do top-k -> citar trecho@versão:página.

- Um índice FTS5 por projeto (evita vazamento de estatística IDF entre projetos).
- Tokenizador unicode61 remove_diacritics 2 (português; porter é para inglês).
- Retirada: marcador (tombstone) primeiro, limpeza dos derivados depois;
  a limpeza pode ser interrompida e retomada sem reabrir o consumo.
- Busca lexical não mede verdade nem concede permissão: bm25 só ordena.
- Um identificador de fonte pertence a um só escopo (projeto e caso): a curadoria só
  substitui versões do mesmo escopo (auditoria #18). Versão nova é inteiro positivo, como
  o registro protegido de retiradas a representa (`id@<n>`; auditoria #12).
- A autorização é conferida de novo dentro de cada transação de escrita (auditoria #11).
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from . import events, revisions
from .auth import Policy, Principal, resource_case, resource_project
from .canon import canonical_json, sha256_file, sha256_text
from .contracts import NotFound, RevisionConflict, ValidationError
from .citacoes import fonte_autorizada, verificar_citacao
from .db import transaction, utcnow
from .paths import contained, validate_id
from .projects import verified_project_dir

RUBRIC = ("origem", "fidelidade", "vigencia", "acesso", "finalidade")
RUBRIC_VALUES = {"aprovado", "reprovado", "pendente"}
DEFAULT_RECIPE = (80, 15)  # palavras por trecho, sobreposição (A16)
VERSAO_MAXIMA = 2 ** 63 - 1  # maior INTEGER do SQLite


def _versao(version, *, minima: int) -> int:
    """Versão como o registro protegido de retiradas a lê (`id@<dígitos>`): inteiro de verdade (bool não
    conta), a partir de `minima` e dentro do INTEGER do SQLite. Sem isso, `id@-1` ou `id@True` iriam ao
    registro, e a leitura estrita dele (init, backup, restauração) pararia (auditoria #12)."""
    if isinstance(version, bool) or not isinstance(version, int) or not minima <= version <= VERSAO_MAXIMA:
        raise ValidationError(f"versão de fonte deve ser número inteiro de {minima} em diante")
    return version


def fts_table(project_id: str) -> str:
    return "fts_" + validate_id(project_id, "project_id").replace("-", "_")


def split_pages(pages: list[str], source: str, version: int, size: int = 80, overlap: int = 15):
    """Divisor didático por páginas (A16). Gera IDs determinísticos e hash por trecho."""
    if not 0 <= overlap < size:
        raise ValidationError("sobreposição inválida")
    recipe = f"w{size}-o{overlap}-v1"
    for page_no, text in enumerate(pages, 1):
        words = text.split()
        start, part = 0, 1
        while start < len(words):
            end = min(start + size, len(words))
            body = " ".join(words[start:end])
            yield {
                "chunk_id": f"{source}@{version}:p{page_no}:c{part}:{recipe}",
                "page": page_no, "ordinal": part, "body": body,
                "body_hash": sha256_text(body), "recipe": recipe,
            }
            if end == len(words):
                break
            start, part = end - overlap, part + 1


def fts_query(text: str, limit_terms: int = 12) -> str | None:
    """Prepara a expressão FTS5 com termos citados (sem operadores vindos do usuário)."""
    terms = re.findall(r"\w+", text, flags=re.UNICODE)[:limit_terms]
    terms = [t for t in terms if len(t) > 1]
    if not terms:
        return None
    return " OR ".join('"' + t.replace('"', "") + '"' for t in terms)


class KnowledgeService:
    def __init__(self, root: Path, con: sqlite3.Connection, principal: Principal,
                 tombstone_log: Path | None = None):
        self.root = Path(root)
        self.con = con
        self.principal = principal
        self.policy = Policy(con)
        # Registro de retiradas fora dos arquivos do backup, para reaplicar após restaurar.
        # Em operação real, replique-o fora da máquina (proposta 3.0, backup 3-2-1-1-0).
        self.tombstone_log = Path(tombstone_log) if tombstone_log else self.root / "state" / "retiradas.jsonl"

    def _resource(self, project_id: str, case_id: str | None) -> str:
        return resource_case(project_id, case_id) if case_id else resource_project(project_id)

    def _ensure_fts(self, project_id: str) -> str:
        table = fts_table(project_id)
        self.con.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING fts5(body, tokenize='unicode61 remove_diacritics 2')"
        )
        return table

    def _drop_chunks(self, project_id: str, source_id: str, version: int) -> int:
        table = fts_table(project_id)
        has_table = self.con.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        rows = self.con.execute(
            "SELECT chunk_rowid, chunk_id FROM chunk WHERE source_id = ? AND version = ?", (source_id, version)
        ).fetchall()
        for row in rows:
            if has_table:
                self.con.execute(f"DELETE FROM {table} WHERE rowid = ?", (row["chunk_rowid"],))
            self.con.execute("DELETE FROM dependency WHERE child_id = ?", (row["chunk_id"],))
            self.con.execute("DELETE FROM cache_entry WHERE sources_json LIKE ?", (f'%"{row["chunk_id"]}"%',))
        self.con.execute("DELETE FROM chunk WHERE source_id = ? AND version = ?", (source_id, version))
        return len(rows)

    def _source(self, source_id: str, version: int) -> sqlite3.Row:
        return fonte_autorizada(self.con, self.policy, self.principal, source_id, version)

    # ------------------------------------------------------------ origem
    def register_source(self, project_id: str, source_id: str, version: int, rel_path: str,
                        case_id: str | None = None, purpose: str = "") -> str:
        resource = self._resource(project_id, case_id)
        self.policy.require(self.principal, "write", resource)
        _versao(version, minima=1)
        if not source_id.startswith(f"{project_id}/") or len(source_id) <= len(project_id) + 1:
            # Identificador qualificado pelo projeto: dois projetos nunca disputam o mesmo nome,
            # então registrar não revela o que existe em outro projeto.
            raise ValidationError("identificador de fonte deve ser '<projeto>/<id>'", exemplo=f"{project_id}/GUIA-001")
        pasta = verified_project_dir(self.root, project_id)
        data_dir = pasta / "data"
        path = contained(data_dir, data_dir / rel_path, within=pasta)  # data/ trocada por ligação: recusa (F04)
        if not path.is_file():
            raise NotFound("arquivo de origem inexistente", rel_path=rel_path)
        digest = sha256_file(path)
        with transaction(self.con):
            self.policy.recheck(self.principal, "write", resource)  # revogação no intervalo (auditoria #11)
            # Um identificador pertence a um só escopo (projeto e caso). Sem isso, a versão nova registrada
            # noutro caso substituiria, na curadoria, a fonte vigente deste (auditoria #18).
            outro_escopo = self.con.execute("SELECT 1 FROM source_version WHERE source_id = ?"
                                            " AND (project_id <> ? OR case_id IS NOT ?)",
                                            (source_id, project_id, case_id)).fetchone()
            if outro_escopo:
                raise ValidationError("identificador de fonte já usado em outro escopo; escolha outro identificador")
            existing = self.con.execute(
                "SELECT original_hash FROM source_version WHERE source_id = ? AND version = ?", (source_id, version)
            ).fetchone()
            if existing:
                if existing["original_hash"] != digest:
                    raise ValidationError("mesma versão com conteúdo diferente: registre nova versão")
                return digest  # reingestão idempotente
            self.con.execute(
                "INSERT INTO source_version (source_id, version, project_id, case_id, rel_path, original_hash,"
                " status, purpose, registered_by, registered_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (source_id, version, project_id, case_id, rel_path, digest, "pending", purpose,
                 self.principal.principal_id, utcnow()),
            )
            events.emit(self.con, "source_registered", project_id=project_id, subject=self.principal.principal_id,
                        payload={"source": f"{source_id}@{version}", "hash": digest})
        return digest

    def prepare(self, source_id: str, version: int, pages: list[str]) -> str:
        """Grava o texto preparado por página (a extração em si é feita fora)."""
        src = self._source(source_id, version)
        resource = self._resource(src["project_id"], src["case_id"])
        self.policy.require(self.principal, "write", resource)
        if src["status"] in ("withdrawn", "superseded"):
            raise ValidationError("fonte retirada ou substituída não é preparada novamente")
        prepared = canonical_json({"pages": pages})
        digest = sha256_text(prepared)
        if src["prepared_hash"] == digest:
            return digest  # nada mudou
        with transaction(self.con):
            self.policy.recheck(self.principal, "write", resource)  # revogação no intervalo (auditoria #11)
            # Estado lido DENTRO da transação: uma curadoria concorrente não usa a leitura antiga (F08).
            atual = self.con.execute("SELECT status, prepared_hash FROM source_version WHERE source_id = ? AND version = ?",
                                     (source_id, version)).fetchone()
            if atual["status"] in ("withdrawn", "superseded"):
                raise ValidationError("fonte retirada ou substituída não é preparada novamente")
            if atual["prepared_hash"] == digest:
                return digest
            # Nova preparação invalida os trechos derivados da anterior (e os caches que os citam).
            self._drop_chunks(src["project_id"], source_id, version)
            self.con.execute(
                "UPDATE source_version SET prepared_json = ?, prepared_hash = ?, prepared_by = ?,"
                " status = 'pending', is_current = 0, approved_by = NULL, approved_hash = NULL"
                " WHERE source_id = ? AND version = ?",
                (prepared, digest, self.principal.principal_id, source_id, version),
            )
            if atual["status"] == "approved":
                revisions.bump(self.con, resource_project(src["project_id"]), "corpus_rev")
            events.emit(self.con, "source_prepared", project_id=src["project_id"],
                        payload={"source": f"{source_id}@{version}", "prepared_hash": digest})
        return digest

    # ------------------------------------------------------------ curadoria GOLD
    def curate(self, source_id: str, version: int, rubric: dict, expected_prepared_hash: str,
               review_due: str, purpose: str) -> str:
        src = self._source(source_id, version)
        resource = self._resource(src["project_id"], src["case_id"])
        self.policy.require(self.principal, "approve", resource)
        if set(rubric) != set(RUBRIC):
            raise ValidationError("rubrica deve avaliar exatamente: " + ", ".join(RUBRIC))
        for crit, item in rubric.items():
            if item.get("resultado") not in RUBRIC_VALUES or not item.get("evidencia"):
                raise ValidationError("cada critério precisa de resultado e evidência", criterio=crit)
        if src["prepared_hash"] != expected_prepared_hash:
            raise ValidationError("o texto preparado mudou após a revisão; curadoria recusada")
        if src["prepared_by"] == self.principal.principal_id:
            raise ValidationError("quem preparou não aprova o próprio texto")
        decision = "approved" if all(i["resultado"] == "aprovado" for i in rubric.values()) else (
            "rejected" if any(i["resultado"] == "reprovado" for i in rubric.values()) else "pending")
        with transaction(self.con):
            # Leitura e validação autoritativas DENTRO da transação (BEGIN IMMEDIATE serializa com a
            # preparação): o hash revisado tem de ser o que continua gravado (auditoria F08).
            self.policy.recheck(self.principal, "approve", resource)
            atual = self.con.execute(
                "SELECT status, prepared_hash, prepared_by FROM source_version WHERE source_id = ? AND version = ?",
                (source_id, version)).fetchone()
            if atual is None:
                raise NotFound("fonte não encontrada")
            if atual["status"] == "withdrawn":
                raise ValidationError("fonte retirada não volta por curadoria; registre nova versão")
            if atual["prepared_hash"] != expected_prepared_hash:
                raise RevisionConflict("o texto preparado mudou durante a curadoria; revise a versão nova",
                                       source=f"{source_id}@{version}")
            if atual["prepared_by"] == self.principal.principal_id:
                raise ValidationError("quem preparou não aprova o próprio texto")
            era_consumivel = atual["status"] == "approved"
            if decision == "approved":
                self.con.execute(  # só versões do mesmo escopo, mesmo com colisão gravada por kit anterior (#18)
                    "UPDATE source_version SET status = 'superseded', is_current = 0"
                    " WHERE source_id = ? AND version <> ? AND status = 'approved'"
                    " AND project_id = ? AND case_id IS ?",
                    (source_id, version, src["project_id"], src["case_id"]),
                )
            alteradas = self.con.execute(
                "UPDATE source_version SET status = ?, rubric_json = ?, approved_by = ?, approved_hash = ?,"
                " review_due = ?, purpose = ?, is_current = ? WHERE source_id = ? AND version = ?"
                " AND prepared_hash = ?",
                (decision, canonical_json(rubric),
                 self.principal.principal_id if decision == "approved" else None,
                 expected_prepared_hash if decision == "approved" else None,
                 review_due, purpose, 1 if decision == "approved" else 0, source_id, version,
                 expected_prepared_hash),
            ).rowcount
            if alteradas != 1:
                raise RevisionConflict("curadoria não aplicada: a preparação mudou", source=f"{source_id}@{version}")
            # Entrar OU sair do conjunto consumível muda o corpus: reprovar ou devolver a pendente
            # uma fonte que estava aprovada também invalida as respostas guardadas (auditoria F09).
            if decision == "approved" or era_consumivel:
                revisions.bump(self.con, resource_project(src["project_id"]), "corpus_rev")
            events.emit(self.con, "source_curated", project_id=src["project_id"],
                        subject=self.principal.principal_id,
                        payload={"source": f"{source_id}@{version}", "decision": decision})
        return decision

    # ------------------------------------------------------------ índice
    def index(self, source_id: str, version: int, size: int = DEFAULT_RECIPE[0],
              overlap: int = DEFAULT_RECIPE[1]) -> int:
        """Indexa a preparação vigente. Pode ser feito antes da aprovação (área de
        preparo): a busca só entrega trechos de versões aprovadas e vigentes, então a
        troca de versão ocorre sem lacuna na aprovação (A18)."""
        src = self._source(source_id, version)
        self.policy.require(self.principal, "write", self._resource(src["project_id"], src["case_id"]))
        if src["status"] not in ("pending", "approved") or not src["prepared_json"]:
            raise ValidationError("somente versões preparadas, não retiradas, são indexadas")
        resource = self._resource(src["project_id"], src["case_id"])
        table = self._ensure_fts(src["project_id"])
        added = 0
        with transaction(self.con):
            self.policy.recheck(self.principal, "write", resource)  # revogação no intervalo (auditoria #11)
            # Texto lido DENTRO da transação: os trechos correspondem à preparação gravada agora,
            # não a uma leitura anterior a uma preparação concorrente (F08).
            atual = self.con.execute("SELECT status, prepared_json FROM source_version WHERE source_id = ? AND version = ?",
                                     (source_id, version)).fetchone()
            if atual["status"] not in ("pending", "approved") or not atual["prepared_json"]:
                raise ValidationError("somente versões preparadas, não retiradas, são indexadas")
            pages = json.loads(atual["prepared_json"])["pages"]
            for ch in split_pages(pages, source_id, version, size, overlap):
                if self.con.execute("SELECT 1 FROM chunk WHERE chunk_id = ?", (ch["chunk_id"],)).fetchone():
                    continue  # reindexação idempotente
                cur = self.con.execute(
                    "INSERT INTO chunk (chunk_id, source_id, version, project_id, resource, page, ordinal,"
                    " body, body_hash, recipe) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (ch["chunk_id"], source_id, version, src["project_id"], resource, ch["page"],
                     ch["ordinal"], ch["body"], ch["body_hash"], ch["recipe"]),
                )
                self.con.execute(f"INSERT INTO {table} (rowid, body) VALUES (?, ?)", (cur.lastrowid, ch["body"]))
                self.con.execute(
                    "INSERT INTO dependency (parent_id, child_id, relation) VALUES (?,?,?) ON CONFLICT DO NOTHING",
                    (f"{source_id}@{version}", ch["chunk_id"], "wasDerivedFrom"),
                )
                added += 1
            events.emit(self.con, "source_indexed", project_id=src["project_id"],
                        payload={"source": f"{source_id}@{version}", "chunks_added": added})
        return added

    def search(self, project_id: str, query: str, k: int = 5) -> list[dict]:
        """Recuperação com autorização e estado aplicados no SQL, antes do top-k."""
        self.policy.require(self.principal, "read", resource_project(project_id))
        expr = fts_query(query)
        if expr is None:
            return []
        table = fts_table(project_id)
        if not self.con.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone():
            return []
        sql = (
            f"SELECT c.chunk_id, c.source_id, c.version, c.page, c.body, bm25({table}) AS score"
            f" FROM {table} JOIN chunk c ON c.chunk_rowid = {table}.rowid"
            " JOIN source_version s ON s.source_id = c.source_id AND s.version = c.version"
            f" WHERE {table} MATCH ? AND s.status = 'approved' AND s.is_current = 1"
            " AND s.approved_hash IS NOT NULL AND s.prepared_hash = s.approved_hash"  # aprovado = este texto (F08)
            " AND s.project_id = ? AND c.project_id = ?"
            " AND NOT EXISTS (SELECT 1 FROM tombstone t WHERE t.entity_id = c.source_id || '@' || c.version)"
            " AND NOT EXISTS (SELECT 1 FROM tombstone t WHERE t.entity_id = c.chunk_id)"
            " AND EXISTS (SELECT 1 FROM acl a WHERE a.subject = ? AND a.resource = c.resource AND a.action = 'read')"
            f" ORDER BY bm25({table}) LIMIT ?"
        )
        rows = self.con.execute(sql, (expr, project_id, project_id, self.principal.principal_id, k)).fetchall()
        result = []
        seen = set()
        for r in rows:
            if r["chunk_id"] in seen:
                continue
            seen.add(r["chunk_id"])
            result.append({
                "chunk_id": r["chunk_id"],
                "citation": f"{r['source_id']}@{r['version']}, p. {r['page']}",
                "body": r["body"], "score": r["score"],
            })
        events.emit(self.con, "retrieval", project_id=project_id, subject=self.principal.principal_id,
                    payload={"k": k, "returned": [r["chunk_id"] for r in result]})
        return result

    def verify_citation(self, chunk_id: str) -> dict:
        """Confere existência, vigência e acesso do trecho citado (o suporte semântico
        da afirmação continua exigindo revisão)."""
        return verificar_citacao(self.con, self.policy, self.principal, self._source, chunk_id)

    # ------------------------------------------------------------ ciclo de vida
    def derived(self, entity_id: str) -> list[str]:
        rows = self.con.execute(
            "WITH RECURSIVE affected(id) AS ("
            " SELECT child_id FROM dependency WHERE parent_id = ?"
            " UNION SELECT d.child_id FROM dependency d JOIN affected a ON d.parent_id = a.id)"
            " SELECT id FROM affected", (entity_id,)
        ).fetchall()
        return sorted(r["id"] for r in rows)

    def withdraw(self, source_id: str, version: int, reason: str, *, stop_after: int | None = None) -> dict:
        """Retira a fonte do consumo: marcador primeiro, limpeza dos derivados depois.
        `stop_after` interrompe a limpeza (teste) — o marcador continua bloqueando. Versão que o registro
        protegido não representa (negativa, gravada por kit anterior) é recusada antes de qualquer gravação:
        tire-a de uso reprovando-a na curadoria (auditoria #12)."""
        _versao(version, minima=0)
        src = self._source(source_id, version)
        resource = self._resource(src["project_id"], src["case_id"])
        self.policy.require(self.principal, "approve", resource)
        entity = f"{source_id}@{version}"
        from .backup import enqueue_protected, flush_outbox  # import tardio evita ciclo
        with transaction(self.con):
            self.policy.recheck(self.principal, "approve", resource)  # revogação no intervalo (auditoria #11)
            self.con.execute(
                "INSERT INTO tombstone VALUES (?,?,?,?,?,?) ON CONFLICT(entity_id) DO NOTHING",
                (entity, src["project_id"], self.principal.principal_id, reason, utcnow(), "pending"),
            )
            self.con.execute(
                "UPDATE source_version SET status = 'withdrawn', is_current = 0 WHERE source_id = ? AND version = ?",
                (source_id, version),
            )
            revisions.bump(self.con, resource_project(src["project_id"]), "corpus_rev")
            events.emit(self.con, "source_withdrawn", project_id=src["project_id"],
                        subject=self.principal.principal_id, payload={"source": entity})
            enqueue_protected(self.con, {  # outbox na mesma transação (auditoria F11)
                "entity_type": "source", "entity_id": entity, "project_id": src["project_id"],
                "decided_by": self.principal.principal_id,
                "reason": reason, "decided_at": utcnow(),
            })
        resultado = self.cleanup(entity, stop_after=stop_after)  # o marcador já bloqueia; a limpeza vem antes
        flush_outbox(self.con, self.tombstone_log)
        return resultado

    def cleanup(self, entity: str, *, stop_after: int | None = None) -> dict:
        tomb = self.con.execute("SELECT * FROM tombstone WHERE entity_id = ?", (entity,)).fetchone()
        if tomb is None:
            raise NotFound("marcador de retirada inexistente")
        table = fts_table(tomb["project_id"])
        removed = 0
        for child in self.derived(entity):
            if stop_after is not None and removed >= stop_after:
                return {"entity": entity, "removed": removed, "cleanup_state": "pending"}
            with transaction(self.con):
                row = self.con.execute("SELECT chunk_rowid FROM chunk WHERE chunk_id = ?", (child,)).fetchone()
                if row:
                    self.con.execute(f"DELETE FROM {table} WHERE rowid = ?", (row["chunk_rowid"],))
                    self.con.execute("DELETE FROM chunk WHERE chunk_id = ?", (child,))
                self.con.execute("DELETE FROM cache_entry WHERE sources_json LIKE ?", (f'%"{child}"%',))
                self.con.execute(
                    "INSERT INTO tombstone VALUES (?,?,?,?,?,?) ON CONFLICT(entity_id) DO NOTHING",
                    (child, tomb["project_id"], tomb["decided_by"], "derivado de " + entity, utcnow(), "done"),
                )
                removed += 1
        with transaction(self.con):
            self.con.execute("DELETE FROM cache_entry WHERE sources_json LIKE ?", (f'%"{entity}%',))
            self.con.execute("UPDATE tombstone SET cleanup_state = 'done' WHERE entity_id = ?", (entity,))
            events.emit(self.con, "withdrawal_cleanup_done", project_id=tomb["project_id"],
                        payload={"entity": entity, "removed": removed})
        return {"entity": entity, "removed": removed, "cleanup_state": "done"}
