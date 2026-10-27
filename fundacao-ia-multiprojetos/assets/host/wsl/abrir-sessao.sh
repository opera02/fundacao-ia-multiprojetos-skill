#!/usr/bin/env bash
# Lançador da sessão de dados reais da fundação no WSL2. Gerado pelo preparar-wsl.sh a partir do modelo da skill
# fundacao-ia-multiprojetos (assets/host/wsl/abrir-sessao.sh): não edite à mão; para mudar, rode o preparar-wsl.sh.
#
# Antes de abrir, confere o Claude Code fixado, o perfil do WSL, os três hooks da raiz e a identidade do titular
# (.claude/settings.local.json), todos pelo SHA-256 gravado no preparo, o titular fixado aqui e a interoperabilidade
# com o Windows desligada. Qualquer diferença: a sessão não abre. A identidade vem do settings.local.json
# (--setting-sources local), que a sessão carrega inteiro: por isso o hash dele também é fixado [auditoria Codex
# Security da 1.7.6, #5]; o projeto vem deste lançador. O perfil é passado por --settings e não é alterado pela sessão.
set -euo pipefail

RAIZ='{{RAIZ}}'
PROJETO='{{PROJETO}}'
TITULAR='{{TITULAR}}'
CLAUDE_BIN='{{CLAUDE_BIN}}'
CLAUDE_VERSAO='{{CLAUDE_VERSAO}}'
CLAUDE_SHA256='{{CLAUDE_SHA256}}'
CLAUDE_ORIGEM_HASH='{{CLAUDE_ORIGEM_HASH}}'
PERFIL_SHA256='{{PERFIL_SHA256}}'
HOOK_CAMINHO_SHA256='{{HOOK_CAMINHO_SHA256}}'
HOOK_IDENTIDADE_SHA256='{{HOOK_IDENTIDADE_SHA256}}'
HOOK_SINAIS_SHA256='{{HOOK_SINAIS_SHA256}}'
LOCAL_SHA256='{{LOCAL_SHA256}}'
SKILL_MD='{{SKILL_MD}}'
PERFIL="$RAIZ/.claude/settings.wsl.json"
LOCAL="$RAIZ/.claude/settings.local.json"

nao_abre() {
  printf 'A sessão de dados reais NÃO foi aberta: %s\n' "$1" >&2
  exit 1
}

confere() {  # arquivo, SHA-256 esperado, nome para a mensagem
  [ -f "$1" ] || nao_abre "$3 não existe ($1)."
  local atual
  atual=$(sha256sum "$1" | cut -d' ' -f1)
  atual=${atual#'*'}
  if [ "$atual" != "$2" ]; then
    nao_abre "$3 mudou desde o preparo (esperado $2, encontrado $atual). Se a mudança foi sua, rode de novo o preparar-wsl.sh; se não foi, não abra a sessão e avise o executor."
  fi
}

confere "$CLAUDE_BIN" "$CLAUDE_SHA256" "o Claude Code $CLAUDE_VERSAO fixado"
confere "$PERFIL" "$PERFIL_SHA256" "o perfil do WSL (.claude/settings.wsl.json)"
confere "$RAIZ/.claude/hooks/guarda_caminho.py" "$HOOK_CAMINHO_SHA256" "o hook guarda_caminho.py"
confere "$RAIZ/.claude/hooks/guarda_identidade.py" "$HOOK_IDENTIDADE_SHA256" "o hook guarda_identidade.py"
confere "$RAIZ/.claude/hooks/sinais_sessao.py" "$HOOK_SINAIS_SHA256" "o hook sinais_sessao.py"
confere "$LOCAL" "$LOCAL_SHA256" "a identidade do titular (.claude/settings.local.json)"
# O titular fixado aqui tem de ser o do settings.local.json (o preparo só fixa o arquivo com a identidade dele).
PRINCIPAL_LOCAL=$(grep -o '"FUNDACAO_PRINCIPAL"[[:space:]]*:[[:space:]]*"[^"]*"' "$LOCAL" |
  sed 's/.*"\([^"]*\)"$/\1/' | head -n 1 || true)
if [ "$PRINCIPAL_LOCAL" != "$TITULAR" ]; then
  nao_abre "o .claude/settings.local.json entrega a identidade ${PRINCIPAL_LOCAL:-(nenhuma)}, mas este lançador é do titular $TITULAR: rode de novo o preparar-wsl.sh com --titular $TITULAR."
fi
# O projeto vem deste lançador; se o settings.local.json também o entregar, tem de ser o mesmo (com os dois diferentes,
# qual vale dependeria da precedência do host: revisão de segurança da 1.7.0).
PROJETO_LOCAL=$(grep -o '"FUNDACAO_PROJECT"[[:space:]]*:[[:space:]]*"[^"]*"' "$LOCAL" |
  sed 's/.*"\([^"]*\)"$/\1/' | head -n 1 || true)  # sem a chave, nada a conferir
if [ -n "$PROJETO_LOCAL" ] && [ "$PROJETO_LOCAL" != "$PROJETO" ]; then
  nao_abre "o .claude/settings.local.json entrega o projeto $PROJETO_LOCAL, mas este lançador é do projeto $PROJETO: rode de novo o preparar-maquina.ps1 com -Projeto $PROJETO."
fi
if /mnt/c/Windows/System32/cmd.exe /c exit 0 >/dev/null 2>&1; then
  nao_abre "a interoperabilidade com o Windows está ligada (o cmd.exe abriu). Rode o preparar-wsl.sh e reinicie o Ubuntu: no PowerShell do Windows, wsl --terminate ${WSL_DISTRO_NAME:-Ubuntu}."
fi

PROMPT="Na fundação em $RAIZ, use a skill fundacao-ia-multiprojetos (se ela não aparecer, leia $SKILL_MD) e leia a RETOMADA.md antes de agir. Esta é a sessão de dados reais do projeto $PROJETO: WSL2 com o perfil .claude/settings.wsl.json, aberta pelo lançador do titular, de onde vêm a identidade e o projeto (não os atribua). Siga a próxima ação autorizada da RETOMADA sem repetir os efeitos já realizados; nenhuma chamada a provedor sem autorização registrada."

printf 'Claude Code %s fixado (hash %s, %s); perfil, hooks e identidade (%s) conferidos.\n' "$CLAUDE_VERSAO" \
  "${CLAUDE_SHA256:0:12}" "$CLAUDE_ORIGEM_HASH" "$TITULAR"
printf 'Lembrete: feche antes as sessões do Windows que operam a fundação (o banco não abre pelos dois lados ao mesmo tempo).\n'
cd "$RAIZ"
# Variáveis da fundação herdadas do terminal (FUNDACAO_PRINCIPAL, FUNDACAO_PERMITIR_TROCA_IDENTIDADE e as dos hooks)
# não passam: a identidade vem do settings.local.json conferido e o projeto, daqui.
for v in $(compgen -e); do
  case "$v" in FUNDACAO_*) unset "$v" ;; esac
done
export FUNDACAO_PROJECT="$PROJETO"
exec "$CLAUDE_BIN" --settings "$PERFIL" --setting-sources local "$PROMPT"
