#!/usr/bin/env python3
"""Hook PreToolUse PREVENTIVO: nega escrita fora do projeto autenticado (proposta 3.0 R4.1).

Contrato (Claude Code, conferido em 18/10/2026): recebe o evento em JSON pela
entrada padrão; para negar, imprime
  {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                          "permissionDecision": "deny",
                          "permissionDecisionReason": "..."}}
Sem saída e código 0 = sem decisão (segue o fluxo normal de permissões).
Matcher recomendado: `Edit|Write|MultiEdit|NotebookEdit|mcp__.*` (sem `mcp__.*` o host não
encaminha ferramentas MCP ao hook).

Configuração esperada (definida pelo LANÇADOR, não pelo modelo):
  FUNDACAO_PROJECT        identificador do projeto autenticado da sessão (ex.: juridico-lab)
  FUNDACAO_RAIZ           raiz da fundação (padrão: CLAUDE_PROJECT_DIR ou diretório atual)
  FUNDACAO_MCP_PERMITIDAS ferramentas MCP liberadas, separadas por vírgula; aceita padrões com
                          `*` (ex.: `mcp__fundacao__*,mcp__ccd_*`)
Falha fechada: sem FUNDACAO_PROJECT, escrita é negada; evento ilegível ou erro inesperado
também nega. Ferramentas MCP: o hook não sabe se uma ferramenta MCP lê ou grava, então
nega toda ferramenta MCP que não esteja em FUNDACAO_MCP_PERMITIDAS (libere as de leitura
que o projeto usa). Inclua aí as ferramentas MCP de infraestrutura do PRÓPRIO host — no
aplicativo Claude Desktop, por exemplo, as `mcp__ccd_*` (plano, sessões, painéis): sem isso a
sessão em que o hook estiver instalado perde essas ferramentas (auditoria final da 1.4.2,
AF-08). Não grava conteúdo nem payload em log.
Limite: protege as ferramentas de arquivo e MCP do agente; comandos de shell precisam de
sandbox (WSL2) e regras de permissão — este hook não é fronteira completa.
"""

from __future__ import annotations

import fnmatch
import json
import os
import sys
from pathlib import Path

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def decide(event: dict, env: dict) -> dict | None:
    tool = event.get("tool_name", "")
    if tool.startswith("mcp__"):
        permitidas = {t.strip() for t in (env.get("FUNDACAO_MCP_PERMITIDAS", "") + ","
                                          + env.get("FUNDACAO_MCP_ESCRITA_PERMITIDA", "")).split(",") if t.strip()}
        # Nome exato ou padrão com `*` (fnmatch, sensível a maiúsculas): `mcp__ccd_*` libera a família.
        if any(fnmatch.fnmatchcase(tool, p) for p in permitidas):
            return None
        return deny(f"ferramenta MCP '{tool}' não liberada para este projeto")
    if tool not in WRITE_TOOLS:
        return None
    project = env.get("FUNDACAO_PROJECT", "").strip()
    if not project:
        return deny("projeto autenticado ausente (FUNDACAO_PROJECT); escrita negada")
    raiz = Path(env.get("FUNDACAO_RAIZ") or env.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".")
    allowed_root = (raiz / "projects" / project).resolve()
    tool_input = event.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not target:
        return deny("caminho de destino ausente")
    path = Path(target)
    if not path.is_absolute():
        path = Path(event.get("cwd") or raiz) / path
    try:
        path.resolve().relative_to(allowed_root)
    except ValueError:
        return deny(f"escrita fora de projects/{project}/")
    return None


def deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
        if not isinstance(event, dict):
            raise ValueError("evento não é objeto")
        result = decide(event, dict(os.environ))
    except Exception:  # noqa: BLE001 — falha fechada: qualquer erro vira negativa
        result = deny("evento ilegível ou erro no hook: negado por segurança")
    if result:
        # JSON só com ASCII: a saída independe da página de código do console (cp1252 no Windows).
        sys.stdout.write(json.dumps(result, ensure_ascii=True) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
