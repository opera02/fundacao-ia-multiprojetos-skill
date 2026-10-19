"""Componente `source_manifest` (livro A11): manifesto de fontes autorizadas.

Recebe identificadores de documentos (nunca caminhos livres), resolve-os pelo
catálogo do projeto e devolve caminho relativo, tamanho e hash. Não altera
fontes, não chama provedores e não grava memória. Arquivo inacessível aparece
como erro explícito, sem hash inventado.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

COMPONENT_VERSION = "0.1.1"


def _contained(project_dir: Path, rel: str) -> Path | None:
    """Caminho em `data/` do projeto, resolvido. Recusa o que sai de `data/` e também a pasta
    `data/` trocada por ligação para fora do projeto (o resolvido precisa ficar sob a pasta
    REAL do projeto, não sob o destino da ligação)."""
    data_lex = project_dir.resolve() / "data"
    cand = (data_lex / rel).resolve()
    try:
        cand.relative_to(data_lex)
    except ValueError:
        return None
    return cand


def run(request: dict) -> dict:
    project_dir = Path(request["project_dir"])
    files, errors = [], []
    catalogo = _contained(project_dir, "catalog.json")
    if catalogo is None:
        return {"component_version": COMPONENT_VERSION, "project_id": request["project_id"], "files": [],
                "errors": [{"document_id": None, "error": "E_PATH_ESCAPE", "arquivo": "data/catalog.json"}]}
    catalog = json.loads(catalogo.read_text(encoding="utf-8"))
    for doc_id in request["payload"].get("document_ids", []):
        rel = catalog.get(doc_id)
        if rel is None:
            errors.append({"document_id": doc_id, "error": "E_NOT_IN_CATALOG"})
            continue
        path = _contained(project_dir, rel)
        if path is None:
            errors.append({"document_id": doc_id, "error": "E_PATH_ESCAPE"})
            continue
        if not path.is_file():
            errors.append({"document_id": doc_id, "error": "E_UNREADABLE"})
            continue
        data = path.read_bytes()
        files.append({
            "document_id": doc_id,
            "path": path.relative_to(project_dir.resolve() / "data").as_posix(),
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    return {
        "component_version": COMPONENT_VERSION,
        "project_id": request["project_id"],
        "files": files,
        "errors": errors,
    }
