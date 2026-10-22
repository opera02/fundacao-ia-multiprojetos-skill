"""Componente `source_manifest` (livro A11): manifesto de fontes autorizadas.

Recebe identificadores de documentos (nunca caminhos livres), resolve-os pelo
catálogo do projeto e devolve caminho relativo, tamanho e hash. Não altera
fontes, não chama provedores e não grava memória. Arquivo inacessível aparece
como erro explícito, sem hash inventado.
Tetos (auditoria Codex Security da 1.7.6, #9; vêm em `limits` no pedido do despacho, padrão em
core/limites.py): identificadores demais recusam o pedido antes de ler qualquer documento; o repetido é
lido uma vez; arquivo acima do teto, ou que passaria do teto somado, é recusado pelo tamanho
no disco, sem ser aberto; a leitura é em blocos e para no teto se o arquivo crescer.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..core.limites import PADRAO as LIMITES_PADRAO  # o despacho manda os do registro; estes, na chamada direta

COMPONENT_VERSION = "0.2.0"
LIMITE_CATALOGO = 8 * 1024 * 1024  # data/catalog.json é lido inteiro (JSON)
_BLOCO = 1024 * 1024


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


def _ler_com_teto(path: Path, teto: int) -> bytes | None:
    """Conteúdo inteiro, ou None se passar de `teto` bytes (lê no máximo teto + 1)."""
    with open(path, "rb") as arq:
        dados = arq.read(teto + 1)
    return None if len(dados) > teto else dados


def _hash_com_teto(path: Path, teto: int) -> tuple[int, str] | None:
    """(tamanho, sha256) lidos em blocos; None se o arquivo passar de `teto` bytes durante a leitura."""
    h, total = hashlib.sha256(), 0
    with open(path, "rb") as arq:
        while bloco := arq.read(min(_BLOCO, teto - total + 1)):
            total += len(bloco)
            if total > teto:
                return None
            h.update(bloco)
    return total, h.hexdigest()


def _manifesto(request: dict, files: list, errors: list) -> dict:
    return {"component_version": COMPONENT_VERSION, "project_id": request["project_id"], "files": files,
            "errors": errors}


def run(request: dict) -> dict:
    project_dir = Path(request["project_dir"])
    limites = {**LIMITES_PADRAO, **request.get("limits", {})}
    files, errors = [], []
    catalogo = _contained(project_dir, "catalog.json")
    if catalogo is None:
        return _manifesto(request, [], [{"document_id": None, "error": "E_PATH_ESCAPE",
                                         "arquivo": "data/catalog.json"}])
    bruto = _ler_com_teto(catalogo, LIMITE_CATALOGO)
    if bruto is None:
        return _manifesto(request, [], [{"document_id": None, "error": "E_TOO_LARGE", "arquivo": "data/catalog.json",
                                         "limite": LIMITE_CATALOGO}])
    catalog = json.loads(bruto.decode("utf-8"))
    ids = request["payload"].get("document_ids", [])
    if len(ids) > limites["max_files"]:  # recusa o pedido inteiro antes de ler qualquer documento
        return _manifesto(request, [], [{"document_id": None, "error": "E_TOO_MANY_DOCUMENTS",
                                         "quantidade": len(ids), "limite": limites["max_files"]}])
    vistos, total = set(), 0
    for doc_id in ids:
        if doc_id in vistos:
            errors.append({"document_id": doc_id, "error": "E_DUPLICATE"})
            continue
        vistos.add(doc_id)
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
        tamanho = path.stat().st_size
        if tamanho > limites["file_bytes"]:  # pelo tamanho no disco: o arquivo nem é aberto
            errors.append({"document_id": doc_id, "error": "E_TOO_LARGE", "size": tamanho,
                           "limite": limites["file_bytes"]})
            continue
        if total + tamanho > limites["total_file_bytes"]:
            errors.append({"document_id": doc_id, "error": "E_TOTAL_LIMIT", "limite": limites["total_file_bytes"]})
            continue
        try:
            lido = _hash_com_teto(path, min(limites["file_bytes"], limites["total_file_bytes"] - total))
        except OSError:
            errors.append({"document_id": doc_id, "error": "E_UNREADABLE"})
            continue
        if lido is None:  # cresceu durante a leitura: passou do teto
            errors.append({"document_id": doc_id, "error": "E_TOO_LARGE", "limite": limites["file_bytes"]})
            continue
        total += lido[0]
        files.append({
            "document_id": doc_id,
            "path": path.relative_to(project_dir.resolve() / "data").as_posix(),
            "size": lido[0],
            "sha256": lido[1],
        })
    return _manifesto(request, files, errors)
