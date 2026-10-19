"""Cache de respostas e de recuperação com isolamento e invalidação (livro A20).

Um acerto de cache pode ser uma falha de segurança. Por isso:
1. a autorização ATUAL é conferida antes de qualquer consulta ao cache;
2. a chave inclui identidade, escopo, revisão de política e de corpus,
   provedor, modelo, versão do prompt, hash do contexto e configuração;
3. na leitura, a entrada é recusada se alguma fonte usada foi retirada ou saiu de
   vigência, se as revisões mudaram (revogação vale antes do TTL) ou se o prazo venceu;
   a MESMA validação vale para a leitura normal e para a leitura por ID (auditoria F05);
4. resultados negativos ("nada encontrado") também expiram com o corpus.
Este módulo NÃO implementa CAG: cache de respostas devolve saída pronta;
CAG reutiliza estado KV de inferência (ver scripts/cag_kv_demo.py).
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter
from typing import Any

from . import events, revisions
from .auth import Policy, Principal, resource_project
from .canon import canonical_json, sha256_json
from .db import transaction, utcnow


def fonte_inelegivel(con: sqlite3.Connection, fonte: str) -> str | None:
    """Motivo para uma fonte citada não sustentar mais a resposta guardada, ou None.

    Reconhece memórias (só vigentes aprovadas), trechos e versões de fonte GOLD (só aprovadas,
    vigentes e com o hash aprovado igual ao preparado). Identificador que o kit não conhece
    (ex.: artefato externo) depende só das retiradas registradas e das revisões."""
    mem = con.execute("SELECT status FROM memory_item WHERE memory_id = ?", (fonte,)).fetchone()
    if mem is not None:
        return None if mem["status"] == "approved" else "memoria_fora_de_vigencia"
    trecho = con.execute("SELECT source_id, version FROM chunk WHERE chunk_id = ?", (fonte,)).fetchone()
    if trecho is not None:
        sid, ver = trecho["source_id"], trecho["version"]
    else:
        sid, _, txt = fonte.rpartition("@")
        if not sid or not txt.isdigit():
            return None
        ver = int(txt)
    src = con.execute("SELECT status, is_current, prepared_hash, approved_hash FROM source_version"
                      " WHERE source_id = ? AND version = ?", (sid, ver)).fetchone()
    if src is None:
        return "fonte_inexistente" if trecho is not None else None
    if src["status"] != "approved" or not src["is_current"] or src["prepared_hash"] != src["approved_hash"]:
        return "fonte_fora_de_vigencia"
    return None


def response_key(meta: dict[str, Any], question: str) -> str:
    """Chave do livro (A20): os metadados vêm do servidor, nunca do modelo."""
    payload = {
        "subject": meta["authenticated_subject"],
        "scope": meta["scope_fingerprint"],
        "policy_rev": meta["policy_revision"],
        "corpus_rev": meta["corpus_revision"],
        "provider_id": meta["provider_id"],
        "model_rev": meta["model_revision"],
        "prompt_rev": meta["prompt_revision"],
        "context_hash": meta["context_hash"],
        "generation": meta["generation_config"],
        "question": question,
    }
    return sha256_json(payload)


class ResponseCache:
    def __init__(self, con: sqlite3.Connection, principal: Principal, *, kind: str = "response"):
        self.con = con
        self.principal = principal
        self.kind = kind
        self.policy = Policy(con)
        self.stats: Counter[str] = Counter()

    def server_meta(self, project_id: str, *, provider_id: str, model_revision: str,
                    prompt_revision: str, context_hash: str, generation_config: dict) -> dict:
        policy_rev, corpus_rev = revisions.get(self.con, resource_project(project_id))
        return {
            "authenticated_subject": self.principal.principal_id,
            "scope_fingerprint": resource_project(project_id),
            "policy_revision": policy_rev,
            "corpus_revision": corpus_rev,
            "provider_id": provider_id,
            "model_revision": model_revision,
            "prompt_revision": prompt_revision,
            "context_hash": context_hash,
            "generation_config": generation_config,
        }

    def _motivo_invalida(self, row: sqlite3.Row, project_id: str) -> str | None:
        """Validação ÚNICA das duas portas (`get` e `get_by_key`; auditoria F05): projeto, identidade,
        revisões de política e de corpus, prazo e estado de cada fonte (retirada ou fora de vigência)."""
        if row["project_id"] != project_id or row["subject"] != self.principal.principal_id:
            return "escopo"
        policy_rev, corpus_rev = revisions.get(self.con, resource_project(project_id))
        if row["policy_rev"] != policy_rev or row["corpus_rev"] != corpus_rev:
            return "revisao"
        if row["expires_at"] is not None and row["expires_at"] < time.time():
            return "expirada"
        for fonte in json.loads(row["sources_json"]):
            if self.con.execute("SELECT 1 FROM tombstone WHERE entity_id = ?", (fonte,)).fetchone():
                return "fonte_retirada"
            motivo = fonte_inelegivel(self.con, fonte)
            if motivo:
                return motivo
        return None

    def _servir(self, row: sqlite3.Row | None, project_id: str) -> tuple[str, Any]:
        if row is None:
            self.stats["miss"] += 1
            return "miss", None
        if self._motivo_invalida(row, project_id):
            with transaction(self.con):
                self.con.execute("DELETE FROM cache_entry WHERE cache_key = ?", (row["cache_key"],))
            self.stats["invalid"] += 1
            return "invalid", None
        self.stats["hit"] += 1
        return "hit", json.loads(row["value_json"])

    def get(self, project_id: str, question: str, meta: dict) -> tuple[str, Any]:
        """Retorna ('hit'|'miss'|'invalid'|'denied', valor)."""
        resource = resource_project(project_id)
        if not self.policy.allowed(self.principal.principal_id, "read", resource):
            self.stats["denied"] += 1
            events.emit(self.con, "cache_denied", project_id=project_id, subject=self.principal.principal_id)
            return "denied", None
        key = response_key(meta, question)
        return self._servir(self.con.execute("SELECT * FROM cache_entry WHERE cache_key = ?", (key,)).fetchone(),
                            project_id)

    def get_by_key(self, project_id: str, key: str) -> tuple[str, Any]:
        """Leitura direta por ID antigo: mesma autorização atual (A20, passo 4) e mesma validação de
        `get` — prazo, retiradas e vigência das fontes incluídos."""
        if not self.policy.allowed(self.principal.principal_id, "read", resource_project(project_id)):
            self.stats["denied"] += 1
            events.emit(self.con, "cache_denied", project_id=project_id, subject=self.principal.principal_id)
            return "denied", None
        row = self.con.execute(
            "SELECT * FROM cache_entry WHERE cache_key = ? AND project_id = ? AND subject = ?",
            (key, project_id, self.principal.principal_id),
        ).fetchone()
        return self._servir(row, project_id)

    def put(self, project_id: str, question: str, meta: dict, value: Any, sources: list[str],
            ttl_seconds: float | None = 3600) -> str:
        # Defesa em profundidade: quem não lê o projeto também não grava no cache dele.
        self.policy.require(self.principal, "read", resource_project(project_id))
        key = response_key(meta, question)
        with transaction(self.con):
            self.con.execute(
                "INSERT OR REPLACE INTO cache_entry VALUES (?,?,?,?,?,?,?,?,?,?)",
                (key, self.kind, project_id, self.principal.principal_id, meta["policy_revision"],
                 meta["corpus_revision"], canonical_json(value), canonical_json(sorted(sources)),
                 utcnow(), time.time() + ttl_seconds if ttl_seconds else None),
            )
        return key
