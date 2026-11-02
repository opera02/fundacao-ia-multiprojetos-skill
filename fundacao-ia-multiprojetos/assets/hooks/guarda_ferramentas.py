#!/usr/bin/env python3
"""Hook PreToolUse da sessão de projeto no Ubuntu: lista positiva de ferramentas (contratos do lote 2 da 1.7.10, §7).

Registro (pacote HOST, só no perfil WSL de projeto): matcher `.*`, comando `python3 -I -B` com o caminho absoluto
`<raiz>/.claude/hooks/guarda_ferramentas.py`. Decide só pelo nome da ferramenta (`tool_name`), sem ler arquivo nem a
entrada da ferramenta:
- FUNDACAO_FERRAMENTAS: nomes exatos, separados por vírgula — a mesma lista do `--tools` do lançador. Ausente ou vazia:
  nega tudo (falha fechada). Sem curinga: `*` só casaria uma ferramenta chamada `*`.
- `mcp__<servidor>__<ferramenta>`: só com o servidor em FUNDACAO_MCP_PERMITIDAS, escrito como o nome do servidor ou
  como `mcp__<servidor>__*`. Padrões largos (`mcp__*`, `mcp__ccd_*`) não liberam nada aqui; nome com `__` ambíguo
  (mais de um separador, `___`) é negado. A lista é vazia na 1.7.10: MCP de terceiro roda fora do sandbox e só abre
  com a jaula (1.7.11).
- Qualquer outro nome é negado, inclusive ferramenta nova de uma versão do Claude Code (mensagens entre sessões,
  agendamentos, Artifact): o `--tools` fecha as conhecidas e este hook as que aparecerem (CRITICA-DESENHO, "ferramentas
  internas do Claude Code"; REESCOPO, item 5).
Saída: a negação no formato do guarda_caminho.py, em JSON só com ASCII; liberado = sem saída (segue o fluxo normal de
permissões e os demais hooks). Evento ilegível, vazio, sem `tool_name` ou erro inesperado: nega.
Limite (honestidade, §0 dos contratos): guarda-corpo do processo do Claude Code, não barreira de SO. Um mod ou uma
aprovação que ignore hooks passa por cima, e com a raiz em /mnt/e o sandbox não confinou os comandos nas sondas de
31/10/2026: lá o isolamento entre projetos é lógico até o canário passar no ambiente real.
"""

from __future__ import annotations

import json
import os
import re
import sys

LIMITE_NOME = 120
SERVIDOR = re.compile(r"[A-Za-z0-9_.-]+\Z")
PADRAO_DO_SERVIDOR = re.compile(r"mcp__([A-Za-z0-9_.-]+)__\*\Z")


def deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def _lista(texto: str | None) -> list[str]:
    return [item.strip() for item in (texto or "").split(",") if item.strip()]


def _mostravel(nome: str) -> str:
    """O nome para a mensagem: só caracteres imprimíveis, com teto (o nome vem do evento)."""
    limpo = "".join(c if c.isprintable() else "?" for c in nome)
    return limpo if len(limpo) <= LIMITE_NOME else limpo[:LIMITE_NOME] + "..."


def servidores_permitidos(texto: str | None) -> set[str]:
    """Servidores MCP liberados: o nome exato ou `mcp__<servidor>__*`; os demais padrões não liberam nada."""
    servidores = set()
    for item in _lista(texto):
        m = PADRAO_DO_SERVIDOR.fullmatch(item)
        nome = m.group(1) if m else item
        if SERVIDOR.fullmatch(nome) and "__" not in nome:
            servidores.add(nome)
    return servidores


def servidor_mcp(nome: str) -> str | None:
    """O servidor de `mcp__<servidor>__<ferramenta>`; None quando o nome é ambíguo ou malformado."""
    resto = nome[len("mcp__"):]
    if resto.count("__") != 1 or "___" in resto:
        return None
    servidor, ferramenta = resto.split("__")
    return servidor if servidor and ferramenta and SERVIDOR.fullmatch(servidor) else None


def decide(event: dict, env: dict) -> dict | None:
    nome = event.get("tool_name")
    if not isinstance(nome, str) or not nome:
        return deny("evento sem nome de ferramenta: negado por segurança")
    ferramentas = set(_lista(env.get("FUNDACAO_FERRAMENTAS")))
    if not ferramentas:
        return deny("lista de ferramentas da sessão ausente (FUNDACAO_FERRAMENTAS): tudo negado. Abra a sessão pelo "
                    "lançador do projeto, que define a lista junto com o --tools.")
    if nome.startswith("mcp__"):
        servidor = servidor_mcp(nome)
        if servidor is None:
            return deny(f"nome de ferramenta MCP ambíguo ou malformado ('{_mostravel(nome)}'): negado")
        if servidor in servidores_permitidos(env.get("FUNDACAO_MCP_PERMITIDAS")):
            return None
        return deny(f"o servidor MCP '{_mostravel(servidor)}' não está liberado para este projeto "
                    "(FUNDACAO_MCP_PERMITIDAS). MCP de terceiro roda fora do sandbox: só abre com a ficha de "
                    "aberturas assinada pelo titular e a jaula (1.7.11).")
    if nome in ferramentas:
        return None
    return deny(f"a ferramenta '{_mostravel(nome)}' está fora da lista fechada desta sessão (FUNDACAO_FERRAMENTAS, a "
                "mesma do --tools do lançador). Só a ficha de aberturas do projeto, assinada pelo titular, abre "
                "ferramenta nesta sessão (na 1.7.10: WebFetch e WebSearch); se ela for necessária, peça ao titular.")


def _recusar(*_):
    raise ValueError("entrada inválida")


def _objeto_sem_duplicatas(pares):
    objeto = {}
    for chave, valor in pares:
        if chave in objeto:
            _recusar()
        objeto[chave] = valor
    return objeto


def main() -> int:
    try:
        # Bytes em UTF-8: com -I o Python ignora PYTHONUTF8 e leria a entrada na página de código do Windows.
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"), object_pairs_hook=_objeto_sem_duplicatas,
                           parse_constant=_recusar)
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
