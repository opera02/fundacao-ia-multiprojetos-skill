"""Registro e ciclo de vida de componentes (livro A11, A34).

Descoberta, instalação, habilitação, saúde e autorização são estados distintos.
`discover()` só lê o registro JSON — nunca importa nem executa o componente, nem
os pacotes das dependências declaradas (auditoria A08; varredura #25).
`dispatch()` confere habilitação e autorização ANTES de iniciar o componente e
executa-o em subprocesso com timeout real (no Windows não é possível
interromper com segurança uma função no mesmo processo). O prazo vale para a
árvore de processos: descendentes do componente são encerrados no prazo e
quando ele termina (auditoria A06).
"""

from __future__ import annotations

import importlib.machinery
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..adapters.cli import _processo
from . import events
from .auth import Policy, Principal, resource_project
from .canon import sha256_file
from .contracts import (
    SCHEMAS, ComponentDisabled, DependencyUnavailable, FundacaoError, NotFound, PathEscape,
    ValidationError, require_fields,
)
from .db import transaction, utcnow
from .paths import contained, validate_id
from .projects import project_root

REGISTRY_FIELDS = (
    "schema_version", "component_id", "version", "kind", "enabled", "entrypoint",
    "allowed_projects", "permissions", "timeout_seconds",
)
KINDS = {"tool", "adapter", "hook", "mcp_server", "skill", "plugin", "workflow", "service"}
HOST_PREFIX = "host-skill:"  # componente que o host lê do disco (ex.: skill de projeto do Claude Code)


def registry_dir(root: Path) -> Path:
    return Path(root) / "registry" / "components"


def validate_entry(entry: dict) -> dict:
    require_fields(entry, ("schema_version", "component_id", "version", "kind", "entrypoint"), "registro")
    if entry["schema_version"] != SCHEMAS["component"]:
        raise ValidationError("schema_version de componente não suportado")
    validate_id(entry["component_id"].replace("_", "-"), "component_id")
    if entry["kind"] not in KINDS:
        raise ValidationError("kind desconhecido", kind=entry["kind"])
    if not isinstance(entry.get("enabled"), bool):
        raise ValidationError("enabled deve ser booleano")
    if ":" not in entry["entrypoint"]:
        raise ValidationError("entrypoint deve ter a forma modulo:funcao")
    if not isinstance(entry.get("allowed_projects"), list):
        raise ValidationError("allowed_projects deve ser lista")
    if not isinstance(entry.get("timeout_seconds"), int) or entry["timeout_seconds"] <= 0:
        raise ValidationError("timeout_seconds deve ser inteiro positivo")
    return entry


def discover(root: Path) -> list[dict]:
    """Inventário sem efeitos: lê JSON, valida e informa estado. Não importa código."""
    found = []
    for path in sorted(registry_dir(root).glob("*.json")):
        try:
            # Mesma leitura do despacho: nome do arquivo = component_id, caminho contido no registro.
            entry = load_entry(root, path.stem)
        except (ValidationError, PathEscape, NotFound, json.JSONDecodeError) as exc:
            found.append({"component_id": path.stem, "installed": True, "enabled": False,
                          "health": "registro_invalido", "motivo": str(exc), "allowed_projects": []})
            continue
        missing = [d for d in entry.get("requires_modules", []) if not modulo_disponivel(d)]
        found.append({
            "component_id": entry["component_id"],
            "version": entry["version"],
            "kind": entry["kind"],
            "installed": True,
            "enabled": entry["enabled"],
            "health": "dependencia_ausente" if missing else "nao_consultada",
            "missing_dependencies": missing,
            "allowed_projects": entry["allowed_projects"],
            "purpose": entry.get("purpose", ""),
        })
    return found


def modulo_disponivel(nome: Any) -> bool:
    """Diz se `nome` (ex.: `pacote.modulo`) pode ser importado SEM importar nada (A08; varredura #25).

    `importlib.util.find_spec("pacote.modulo")` importa `pacote`, isto é, executa o `__init__.py`
    dele no processo da fundação — inclusive para componente desabilitado, só por listar. Aqui os
    localizadores padrão são consultados nível a nível, sem executar código dos pacotes; módulo já
    importado conta como disponível. Conservador: pacote que monta o `__path__` ao ser importado, ou
    que dependa de localizador próprio em `sys.meta_path`, aparece como ausente."""
    partes = nome.split(".") if isinstance(nome, str) else []
    if not partes or not all(p.isidentifier() for p in partes):
        return False
    busca = None
    for i in range(len(partes)):
        qualificado = ".".join(partes[:i + 1])
        carregado = sys.modules.get(qualificado)
        if carregado is not None:
            busca = getattr(carregado, "__path__", None)
            continue
        if i > 0 and busca is None:
            return False  # o nível anterior é módulo, não pacote
        spec = None
        if i == 0:
            spec = (importlib.machinery.BuiltinImporter.find_spec(qualificado)
                    or importlib.machinery.FrozenImporter.find_spec(qualificado))
        spec = spec or importlib.machinery.PathFinder.find_spec(qualificado, busca)
        if spec is None:
            return False
        busca = spec.submodule_search_locations
    return True


def validate_component_id(component_id: str) -> str:
    """Forma canônica do ID (letras minúsculas, dígitos, hífen e sublinhado). Conferida ANTES de
    montar qualquer caminho: travessia (`../`), caminho absoluto e separadores são recusados."""
    if not isinstance(component_id, str):
        raise ValidationError("component_id deve ser texto")
    try:
        validate_id(component_id.replace("_", "-"), "component_id")
    except ValidationError:
        raise ValidationError("component_id inválido: use só o identificador do registro") from None
    return component_id


def entry_path(root: Path, component_id: str) -> Path:
    """Arquivo do registro confiável para o ID, resolvido e contido em `registry/components`."""
    validate_component_id(component_id)
    base = registry_dir(root)
    return contained(base, base / f"{component_id}.json", within=Path(root))


def load_entry(root: Path, component_id: str) -> dict:
    path = entry_path(root, component_id)
    if not path.is_file():
        raise NotFound("componente desconhecido", component_id=component_id)
    entry = validate_entry(json.loads(path.read_text(encoding="utf-8")))
    if entry["component_id"] != component_id:
        raise ValidationError("o registro declara outro component_id; recusado", component_id=component_id)
    return entry


def is_host_entry(entry: dict) -> bool:
    """Componente lido pelo host (ex.: skill do Claude Code), não executado pelo kit."""
    return str(entry.get("entrypoint", "")).startswith(HOST_PREFIX)


def entrypoint_file(root: Path, entry: dict) -> Path:
    """Arquivo do código do ponto de entrada: só módulos do próprio código da fundação
    (`fundacao.components.<modulo>:<funcao>`), contido em `fundacao/components`. Código guardado
    na pasta de um projeto, que quem opera o projeto altera, não é despachado (auditoria F01)."""
    module, _, func = entry["entrypoint"].partition(":")
    partes = module.split(".")
    if (len(partes) < 3 or partes[:2] != ["fundacao", "components"]
            or not all(p.isidentifier() for p in partes) or not func.isidentifier()):
        raise ValidationError("ponto de entrada fora do código da fundação (fundacao.components.<modulo>:<funcao>)",
                              component_id=entry["component_id"])
    base = Path(root) / "fundacao" / "components"
    alvo = base.joinpath(*partes[2:])
    arquivo = alvo.with_suffix(".py") if alvo.with_suffix(".py").is_file() else alvo / "__init__.py"
    arquivo = contained(base, arquivo, within=Path(root))
    if not arquivo.is_file():
        raise NotFound("código do componente ausente", component_id=entry["component_id"])
    return arquivo


def set_enabled(root: Path, con: sqlite3.Connection, admin: Principal, component_id: str,
                enabled: bool) -> dict:
    Policy(con).require(admin, "admin", "foundation")
    path = entry_path(root, component_id)
    entry = load_entry(root, component_id)
    entry["enabled"] = enabled
    if enabled and not is_host_entry(entry):
        # A habilitação aprova ESTE código: o despacho recusa se ele mudar depois (auditoria F01).
        entry["entrypoint_sha256"] = sha256_file(entrypoint_file(root, entry))
    from .backup import enqueue_protected, flush_outbox  # import tardio evita ciclo
    with transaction(con):
        events.emit(con, "component_enabled" if enabled else "component_disabled",
                    subject=admin.principal_id, payload={"component_id": component_id,
                                                         "version": entry["version"]})
        if not enabled:
            # Desativação vai para o registro protegido (fora do backup): restaurar uma cópia anterior
            # a reaplica; senão, o componente desligado voltaria ligado. Intenção gravada na mesma
            # transação do evento (outbox), ANTES de mudar o arquivo: se algo cair no meio, o lado
            # que sobra é o seguro (auditoria F11).
            enqueue_protected(con, {
                "entity_type": "component_disable", "entity_id": f"componente:{component_id}",
                "component_id": component_id, "decided_by": admin.principal_id, "decided_at": utcnow()})
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    if not enabled:
        flush_outbox(con, Path(root) / "state" / "retiradas.jsonl")
    avisos = host_warnings(root, entry)
    return {**entry, "avisos": avisos} if avisos else entry


def host_warnings(root: Path, entry: dict) -> list[dict]:
    """Componente lido pelo host (`host-skill:<caminho do SKILL.md>`): o registro não liga nem
    desliga a pasta que o host lê. Avisa quando o estado do registro e o do disco divergem — sem
    apagar nem mover nada (achado N1: desabilitar no registro não desliga uma skill de host)."""
    if not is_host_entry(entry):
        return []
    caminho = Path(entry["entrypoint"][len(HOST_PREFIX):])
    alvo = caminho if caminho.is_absolute() else Path(root) / caminho
    pasta = alvo.parent if alvo.name.lower() == "skill.md" else alvo
    rel = pasta.as_posix() if caminho.is_absolute() else (caminho.parent if alvo.name.lower() == "skill.md"
                                                          else caminho).as_posix()
    if not entry["enabled"] and alvo.exists():
        return [{"codigo": "W_SKILL_DE_HOST_AINDA_NO_DISCO",
                 "mensagem": ("desabilitado só no registro da fundação: a pasta da skill continua no disco e o host "
                              "(ex.: Claude Code) continua carregando-a. Para retirá-la do host, mova ou remova a pasta "
                              "indicada (passo 2 da retirada). Nada foi apagado nem movido."),
                 "entrypoint": entry["entrypoint"], "pasta": rel}]
    if entry["enabled"] and not alvo.exists():
        return [{"codigo": "W_SKILL_DE_HOST_AUSENTE",
                 "mensagem": "habilitado no registro, mas o arquivo da skill não existe: o host não vai carregá-la",
                 "entrypoint": entry["entrypoint"], "pasta": rel}]
    return []


def _record(con: sqlite3.Connection, entry: dict, project_id: str | None, subject: str,
            outcome: str) -> None:
    with transaction(con):
        con.execute(
            "INSERT INTO dispatch (component_id, component_version, project_id, subject, outcome, ts)"
            " VALUES (?,?,?,?,?,?)",
            (entry["component_id"], entry["version"], project_id, subject, outcome, utcnow()),
        )


def dispatch_count(con: sqlite3.Connection, component_id: str, outcome: str = "executed") -> int:
    return con.execute(
        "SELECT COUNT(*) FROM dispatch WHERE component_id = ? AND outcome = ?",
        (component_id, outcome),
    ).fetchone()[0]


def dispatch(root: Path, con: sqlite3.Connection, principal: Principal, project_id: str,
             component_id: str, payload: dict[str, Any]) -> dict:
    """Executa um componente somente se habilitado, permitido e autorizado.

    O ID é conferido antes de qualquer leitura; o registro lido é o de `registry/components` (o
    `component_id` declarado tem de ser o pedido); o código precisa estar em `fundacao/components`
    e, se a habilitação registrou o hash dele, continuar igual (auditoria F01). Tudo isso antes
    de importar código, criar processo ou registrar despacho executado."""
    try:
        entry = load_entry(root, component_id)
    except (ValidationError, PathEscape) as exc:
        events.emit(con, "component_rejected", project_id=None, subject=principal.principal_id,
                    payload={"motivo": str(exc)})
        raise
    if is_host_entry(entry):
        _record(con, entry, project_id, principal.principal_id, "denied_host_component")
        raise ValidationError("componente lido pelo host (host-skill:); o kit não o executa",
                              component_id=component_id)
    if not entry["enabled"]:
        _record(con, entry, project_id, principal.principal_id, "denied_disabled")
        raise ComponentDisabled("componente desabilitado; nada foi iniciado", component_id=component_id)
    if project_id not in entry["allowed_projects"]:
        _record(con, entry, project_id, principal.principal_id, "denied_project")
        raise ComponentDisabled("componente não habilitado para este projeto", component_id=component_id)
    try:
        Policy(con).require(principal, "use", resource_project(project_id))
        proj_dir = project_root(root, con, principal, project_id, action="read")
    except FundacaoError:
        _record(con, entry, project_id, principal.principal_id, "denied_access")
        raise
    try:
        codigo = entrypoint_file(root, entry)
        aprovado = entry.get("entrypoint_sha256")
        if aprovado and sha256_file(codigo) != aprovado:
            raise ValidationError("o código do componente mudou desde a habilitação; revise e habilite de novo",
                                  component_id=component_id)
    except FundacaoError:
        _record(con, entry, project_id, principal.principal_id, "denied_entrypoint")
        raise
    missing = [d for d in entry.get("requires_modules", []) if not modulo_disponivel(d)]
    if missing:
        _record(con, entry, project_id, principal.principal_id, "denied_dependency")
        raise DependencyUnavailable("dependência ausente", component_id=component_id, missing=missing)
    module, func = entry["entrypoint"].split(":", 1)
    request = {"project_id": project_id, "project_dir": str(proj_dir), "payload": payload}
    # Ambiente mínimo: sem chaves nem tokens; só o que bibliotecas comuns exigem para rodar
    # (perfil, temporários e localidade — no Windows, torch/transformers precisam de USERNAME/USERPROFILE).
    env = {k: v for k, v in os.environ.items() if k in (
        "PATH", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "USERNAME", "USERPROFILE", "HOME", "HOMEDRIVE",
        "HOMEPATH", "LOCALAPPDATA", "APPDATA", "LANG", "LC_ALL", "TZ")}
    env["PYTHONPATH"] = str(Path(root).resolve())
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # Componente e subprocessos dele em UTF-8, mesmo com console cp1252 no Windows
    # (sem isso, texto acentuado podia virar saída vazia ou erro silencioso).
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    _record(con, entry, project_id, principal.principal_id, "executed")
    try:
        # O executor de árvore dos adaptadores (adapters/cli.py): o prazo vale para o componente E para
        # os descendentes (Job Object no Windows; grupo de processos nos demais), e o que o componente
        # deixar rodando ao terminar também é encerrado (auditoria A06). Limites documentados lá.
        proc = _processo([sys.executable, "-m", "fundacao.core.runner", module, func],
                         json.dumps(request).encode("utf-8"), entry["timeout_seconds"],
                         str(Path(root).resolve()), env)
    except subprocess.TimeoutExpired:
        events.emit(con, "component_timeout", project_id=project_id, subject=principal.principal_id,
                    payload={"component_id": component_id})
        raise FundacaoError("tempo limite do componente excedido", component_id=component_id) from None
    if proc.returncode != 0:
        raise FundacaoError("componente falhou", component_id=component_id,
                            stderr=proc.stderr.strip()[-400:])
    result = json.loads(proc.stdout)
    events.emit(con, "component_executed", project_id=project_id, subject=principal.principal_id,
                payload={"component_id": component_id, "version": entry["version"]})
    return {"component_id": component_id, "version": entry["version"], "result": result}
