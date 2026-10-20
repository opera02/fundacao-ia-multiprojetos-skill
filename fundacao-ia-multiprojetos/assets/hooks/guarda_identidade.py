#!/usr/bin/env python3
"""Hook PreToolUse (Bash/PowerShell) para o regime de DADOS REAIS: nega comandos do executor
que definam ou troquem a identidade da fundação (`FUNDACAO_PRINCIPAL`).

Por quê: no kit, a identidade das operações vem da variável `FUNDACAO_PRINCIPAL`. Se o
executor puder redefini-la, qualquer identidade registrada (administrador, revisor,
curador) fica ao alcance dele, e "quem prepara não aprova" vira obediência, não barreira.
Neste regime, o lançador humano define a variável ANTES de iniciar a sessão (perfil do
terminal, atalho ou serviço) e este hook barra a alteração explícita pela sessão (ver Limite).

Exceção explícita: FUNDACAO_PERMITIR_TROCA_IDENTIDADE=1 no ambiente do lançador (laboratório).
Contrato de saída igual ao de guarda_caminho.py; falha fechada em evento ilegível.
Matcher recomendado: `Bash|PowerShell`.
Limite: é um guarda-corpo para o caminho comum (atribuição explícita da variável). Passam por
ele, por exemplo, o nome da variável montado em tempo de execução, `python -c` que altere
`os.environ` e a chamada direta da API do kit. Não substitui conta do SO separada nem aprovação
com credencial fora do alcance do executor.
Formas cobertas: `$env:X = …`, `${env:X} = …`, `+=`; Set-Item/Set-Content/New-Item/Remove-Item/
Clear-Item sobre `env:X` (caminho com ou sem aspas, `-Path:`/`-Path=`, `Env:\\`, `-Name`, outros
parâmetros antes); `[Environment]::SetEnvironmentVariable`; set/setx/export/unset e `X=valor comando`
(conferência da 1.4.3, CF-01). Leitura e comparação (`echo`, `Get-ChildItem`, `-eq`, `==`) seguem.
"""

from __future__ import annotations

import json
import os
import re
import sys

SHELL_TOOLS = {"Bash", "PowerShell"}
# Só ATRIBUIÇÃO ou remoção da variável. Ler o valor (`echo $env:FUNDACAO_PRINCIPAL`, `Get-ChildItem`, `-eq`)
# não é troca de identidade e segue o fluxo normal (auditoria final da 1.4.2, AF-07). As formas explícitas que
# a 1.4.3 deixava passar — caminho `env:` entre aspas, `-Path:`/`-Path=`, `Env:\`, `Remove-Item` entre aspas,
# `+=`, `New-Item -Path env: -Name`, parâmetro com valor antes de `-Path` — são negadas (conferência da 1.4.3, CF-01).
PADRAO = re.compile(
    # atribuição ou composição (`=`, `+=`, `-=`…), não comparação (`==`, `-eq`); `${env:X} =` pelo `\}?`
    r"FUNDACAO_PRINCIPAL\}?\s*[+\-*/]?=(?!=)"
    # API .NET
    r"|SetEnvironmentVariable\([^)]*FUNDACAO_PRINCIPAL"
    # cmd e Bash: set/setx/export/unset, com ou sem aspas em volta de NOME=valor
    r"|(?:^|[\s;&|(])(?:set|setx|export|unset)\s+[\"']?FUNDACAO_PRINCIPAL"
    # cmdlets do PowerShell sobre o drive env:: parâmetros antes (com valor ou não; `-Par:`/`-Par=`), caminho com
    # aspas opcionais, `Env:\`, e a forma `New-Item -Path env: -Name X`
    r"|(?:Set-Item|Set-Content|New-Item|Remove-Item|Clear-Item)\s+"
    r"(?:-\w+[\s:=]+(?:(?:\"[^\"]*\"|'[^']*'|[^-\s\"'][^\s]*)\s+)?)*"
    r"[\"']?env:[\\/]?(?:[\"']?\s+-Name[\s:=]+)?[\"']?FUNDACAO_PRINCIPAL",
    re.IGNORECASE)


def deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def decide(event: dict, env: dict) -> dict | None:
    if event.get("tool_name") not in SHELL_TOOLS:
        return None
    if env.get("FUNDACAO_PERMITIR_TROCA_IDENTIDADE") == "1":
        return None
    comando = str((event.get("tool_input") or {}).get("command", ""))
    if PADRAO.search(comando):
        return deny("a identidade da fundação é definida pelo lançador, não pela sessão (FUNDACAO_PRINCIPAL)")
    return None


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
