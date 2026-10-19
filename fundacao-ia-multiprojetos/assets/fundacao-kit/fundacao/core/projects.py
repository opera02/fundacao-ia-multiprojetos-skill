"""Projetos criados a partir de um modelo reutilizável (livro A07).

- Lista positiva de arquivos do modelo (nada de bancos, caches, casos ou segredos).
- Criação atômica: pasta temporária -> validação -> renomeação + registro na
  mesma transação. Falha não deixa projeto parcial ativo.
- Reexecução não sobrescreve: a segunda criação informa que a instância existe.
- Atualizar o modelo NÃO migra instâncias existentes; migração é explícita.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from pathlib import Path

from .. import TEMPLATE_VERSION
from . import events
from .auth import Policy, Principal, resource_project
from .contracts import SCHEMAS, AlreadyExists, NotFound, ValidationError, require_fields
from .db import transaction, utcnow
from .ids import new_id
from .paths import contained, exact_child, validate_id

TEMPLATE_FILES = ("INSTRUCOES.md", "CONTRATO-ENTREGAS.md", "exemplo-ficticio.md")
CONFIG_NAME = "projeto.json"
PROJECT_DIRS = ("data", "memory", "evidence", "outputs")
CONFIG_FIELDS = (
    "schema_version", "project_id", "display_name", "purpose", "template_version",
    "enabled_components", "data_root", "memory_root",
)


def projects_dir(root: Path) -> Path:
    return Path(root) / "projects"


def validate_config(config: dict) -> dict:
    require_fields(config, CONFIG_FIELDS[:-3] + ("data_root", "memory_root"), CONFIG_NAME)
    if config["schema_version"] != SCHEMAS["project"]:
        raise ValidationError("schema_version de projeto não suportado", found=config["schema_version"])
    validate_id(config["project_id"], "project_id")
    if not isinstance(config.get("enabled_components"), list):
        raise ValidationError("enabled_components deve ser lista")
    unknown = set(config) - set(CONFIG_FIELDS) - {"notes"}
    if unknown:
        raise ValidationError("campos desconhecidos na configuração", fields=sorted(unknown))
    return config


def verified_project_dir(root: Path, project_id: str) -> Path:
    """Pasta do projeto resolvida, sem redirecionamento: `projects/<id>` precisa ser a própria pasta,
    não uma ligação para a de outro projeto (auditoria F04). Não autoriza: use `project_root`."""
    validate_id(project_id, "project_id")
    return exact_child(projects_dir(root), project_id)


def load_config(root: Path, project_id: str) -> dict:
    pasta = verified_project_dir(root, project_id)
    path = contained(pasta, pasta / CONFIG_NAME)
    if not path.exists():
        raise NotFound("projeto sem configuração", project_id=project_id)
    return validate_config(json.loads(path.read_text(encoding="utf-8")))


def _collision(root: Path, con: sqlite3.Connection, project_id: str) -> str | None:
    lowered = project_id.lower()
    for row in con.execute("SELECT project_id FROM project"):
        if row["project_id"].lower() == lowered:
            return "registro"
    pdir = projects_dir(root)
    if pdir.exists():
        for entry in pdir.iterdir():
            if entry.name.lower() == lowered:
                return "pasta"
    return None


def create_project(
    root: Path,
    con: sqlite3.Connection,
    principal: Principal,
    project_id: str,
    display_name: str,
    purpose: str,
    enabled_components: list[str] | None = None,
) -> dict:
    policy = Policy(con)
    policy.require(principal, "admin", "foundation")
    validate_id(project_id, "project_id")
    if not display_name.strip() or not purpose.strip():
        raise ValidationError("nome e finalidade são obrigatórios")
    where = _collision(root, con, project_id)
    if where:
        raise AlreadyExists(
            "projeto já existe; nada foi alterado", project_id=project_id, detected_in=where
        )

    template = Path(root) / "templates" / "project"
    pdir = projects_dir(root)
    pdir.mkdir(parents=True, exist_ok=True)
    tmp = pdir / f".tmp-{project_id}-{new_id('tmp')[-8:]}"
    tmp.mkdir()
    final = pdir / project_id
    try:
        for name in TEMPLATE_FILES:  # lista positiva
            src = template / name
            if src.exists():
                shutil.copy2(src, tmp / name)
        for sub in PROJECT_DIRS:
            (tmp / sub).mkdir()
        (tmp / "data" / "catalog.json").write_text("{}\n", encoding="utf-8")
        config = validate_config(
            {
                "schema_version": SCHEMAS["project"],
                "project_id": project_id,
                "display_name": display_name,
                "purpose": purpose,
                "template_version": TEMPLATE_VERSION,
                "enabled_components": list(enabled_components or []),
                "data_root": "data",
                "memory_root": "memory",
            }
        )
        (tmp / CONFIG_NAME).write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        with transaction(con):
            policy.recheck(principal, "admin", "foundation")
            con.execute(
                "INSERT INTO project VALUES (?,?,?,?,?,?,?,?)",
                (project_id, display_name, purpose, TEMPLATE_VERSION, SCHEMAS["project"],
                 "active", principal.principal_id, utcnow()),
            )
            for action in ("read", "write", "approve", "audit", "use"):
                con.execute(
                    "INSERT INTO acl VALUES (?,?,?,?,?) ON CONFLICT DO NOTHING",
                    (principal.principal_id, resource_project(project_id), action,
                     principal.principal_id, utcnow()),
                )
            os.replace(tmp, final)  # renomeação atômica no mesmo volume
            events.emit(
                con, "project_created", project_id=project_id, subject=principal.principal_id,
                payload={"template_version": TEMPLATE_VERSION},
            )
    except BaseException:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        raise
    return config


def list_projects(con: sqlite3.Connection, principal: Principal) -> list[dict]:
    """Lista somente projetos que a identidade pode ler."""
    policy = Policy(con)
    rows = con.execute("SELECT * FROM project WHERE status = 'active' ORDER BY project_id")
    return [
        dict(row) for row in rows
        if policy.allowed(principal.principal_id, "read", resource_project(row["project_id"]))
    ]


def project_root(root: Path, con: sqlite3.Connection, principal: Principal, project_id: str,
                 action: str = "read") -> Path:
    """Resolve a pasta do projeto somente após autorizar a identidade."""
    validate_id(project_id, "project_id")
    Policy(con).require(principal, action, resource_project(project_id))
    row = con.execute(
        "SELECT status FROM project WHERE project_id = ?", (project_id,)
    ).fetchone()
    if row is None or row["status"] != "active":
        raise NotFound("projeto inexistente ou inativo", project_id=project_id)
    return verified_project_dir(root, project_id)


def template_drift(root: Path, project_id: str) -> dict:
    """Compara a versão do modelo da instância com a atual (não migra nada)."""
    config = load_config(root, project_id)
    return {
        "project_id": project_id,
        "instance_template_version": config["template_version"],
        "current_template_version": TEMPLATE_VERSION,
        "migration_needed": config["template_version"] != TEMPLATE_VERSION,
    }
