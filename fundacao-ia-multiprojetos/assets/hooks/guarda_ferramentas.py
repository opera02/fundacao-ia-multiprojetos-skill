#!/usr/bin/env python3
"""Hook PreToolUse da sessão de projeto no Ubuntu: lista positiva de ferramentas (contratos do lote 2 da 1.7.10, §7).

Registro (pacote HOST, só no perfil WSL de projeto): matcher `.*`, comando `python3 -I -B` com o caminho absoluto
`<raiz>/.claude/hooks/guarda_ferramentas.py`. Decide pelo nome da ferramenta (`tool_name`), sem ler arquivo; a entrada
só é lida na ferramenta de subagentes:
- FUNDACAO_FERRAMENTAS: nomes exatos, separados por vírgula — a mesma lista do `--tools` do lançador. Ausente ou vazia:
  nega tudo (falha fechada). Sem curinga: `*` só casaria uma ferramenta chamada `*`.
- Subagentes (1.7.10.2): no Claude Code 2.1.302 a ferramenta se chama `Agent`; o `--tools` ainda aceita o nome antigo
  `Task`, e o evento chega como `Agent`. Os dois nomes valem pelo mesmo item da lista. A entrada passa por uma lista
  fechada de campos (CAMPOS_DO_AGENTE): `isolation` (`remote` leva o agente para a nuvem; `worktree` cria uma cópia
  git), `cwd` (outra pasta de trabalho), `name`, `team_name` e `mode` (agente com nome, equipe) e qualquer campo novo
  são negados; cada campo aceito tem o tipo conferido (texto ou booleano), sem depender da validação do binário. O
  `subagent_type`, quando vem, só com um dos nomes de TIPOS_DO_AGENTE, os dos tipos embutidos. O guarda confere o nome,
  não a origem da definição: no 2.1.302, uma definição de outra fonte com o mesmo nome toma o lugar da embutida. Com o
  `--setting-sources local` do lançador, as de usuário e de projeto não carregam, e as de plugin levam o prefixo do
  plugin; o preparo recusa agentes nas managed settings (`/etc/claude-code/.claude/agents`). `SubagentHandback`, o
  canal do relatório do subagente para quem o chamou, vale com o mesmo item da lista. O agente local roda no mesmo
  processo; pelo esquema lido no binário 2.1.302 (03/11/2026), o evento de hook que vem de um subagente traz
  `agent_id` e `agent_type`, e as ferramentas dele passam por estes hooks, pelo perfil e pelo sandbox da sessão. No
  `web-fetch` embutido, isso não foi localizado: a prova 13 do checklist do projeto mede.
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
AGENTE = frozenset({"Agent", "Task"})  # o nome da 2.1.302 e o antigo, que o --tools ainda aceita
RELATORIO_DO_SUBAGENTE = "SubagentHandback"  # o relatório do subagente para quem o chamou (2.1.302)
# Os campos aceitos e o tipo de cada um (o esquema da 2.1.302: textos e o booleano do segundo plano).
CAMPOS_DO_AGENTE = {"description": str, "prompt": str, "subagent_type": str, "model": str, "effort": str,
                    "run_in_background": bool}
TIPOS_DO_AGENTE = frozenset({"general-purpose", "web-fetch", "Explore", "Plan"})  # embutidos; sem tipo: general-purpose
CAMPOS_NEGADOS_DO_AGENTE = {
    "isolation": "'remote' leva o agente para a nuvem e 'worktree' cria uma cópia git",
    "cwd": "o agente rodaria em outra pasta de trabalho",
    "name": "agente com nome é endereçado por mensagens entre agentes (equipes)",
    "team_name": "equipes de agentes ficam fora desta sessão",
    "mode": "o modo de permissão do agente é o da sessão",
}


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


def conferir_agente(entrada) -> dict | None:
    """A entrada da ferramenta de subagentes: só os campos de CAMPOS_DO_AGENTE; o agente roda local, nesta pasta."""
    if not isinstance(entrada, dict):
        return deny("entrada da ferramenta Agent ilegível: negada por segurança")
    for campo in sorted(entrada, key=str):
        if campo in CAMPOS_DO_AGENTE:
            if not isinstance(entrada[campo], CAMPOS_DO_AGENTE[campo]):  # null também: o campo vem com o tipo dele
                return deny(f"o campo '{campo}' da ferramenta Agent veio fora do tipo esperado "
                            f"({CAMPOS_DO_AGENTE[campo].__name__}): negado por segurança; repita com o valor certo ou "
                            "sem o campo.")
            continue
        if campo in CAMPOS_NEGADOS_DO_AGENTE:
            return deny(f"a ferramenta Agent com o campo '{campo}' está negada nesta sessão "
                        f"({CAMPOS_NEGADOS_DO_AGENTE[campo]}): repita sem ele. O agente roda local, nesta pasta, com "
                        "os mesmos hooks, o mesmo perfil e o mesmo sandbox.")
        return deny(f"o campo '{_mostravel(str(campo))}' da ferramenta Agent está fora da lista fechada desta sessão "
                    f"({', '.join(sorted(CAMPOS_DO_AGENTE))}): repita sem ele; se ele for necessário, peça ao titular.")
    tipo = entrada.get("subagent_type")
    if tipo is not None and tipo not in TIPOS_DO_AGENTE:
        return deny(f"o tipo de subagente '{_mostravel(str(tipo))}' está fora da lista desta sessão "
                    f"({', '.join(sorted(TIPOS_DO_AGENTE))}): agente definido em arquivo (do projeto, de pasta de dados "
                    "ou de plugin) traz ferramentas, MCP e hooks próprios, que este guarda não confere. Use um desses "
                    "tipos (sem tipo, vale o general-purpose) ou peça ao titular.")
    return None


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
    if nome in AGENTE and ferramentas & AGENTE:
        return conferir_agente(event.get("tool_input"))
    if nome == RELATORIO_DO_SUBAGENTE and ferramentas & AGENTE:
        return None
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
