#!/usr/bin/env bash
# Lançador da sessão de UM projeto da fundação no Ubuntu (WSL2): /usr/local/bin/abrir-fundacao-<projeto>, de dono root,
# gerado pelo `preparo_host.py instalar-projeto` (o preparar-wsl.sh do titular o roda com sudo) a partir do modelo da
# skill fundacao-ia-multiprojetos (assets/host/wsl/abrir-sessao.sh). Não edite à mão: rode de novo o preparar-wsl.sh.
#
# Antes de abrir (contratos do lote 2 da 1.7.10, §4 e §6): confere pelo SHA-256 a cópia conferida da skill (o
# ajudante que confere o resto e o porteiro) e o Claude Code fixado; recusa interoperabilidade com o Windows ligada,
# outra sessão do mesmo projeto, root e outro usuário; o ajudante confere tudo o que o hashes.json da área root fixa
# (perfil, porteiro.json, mcp.json, aberturas.json, ficha, plugins, hooks da raiz, kit da raiz), a ficha vencida, a
# trava de manutenção, as configurações e o .mcp.json do projeto e limpa os marcadores de 0 byte do sandbox (antes e
# depois). O temp (0700, apagado na saída), a configuração do Claude Code (CLAUDE_CONFIG_DIR: transcrições só deste
# projeto) e os caches (no projeto) são por projeto; o ambiente é montado do zero (env -i, lista fixa). Inicia o
# porteiro, fora do sandbox, com o WSL_DISTRO_NAME na forma que ele aceita (emenda E1 dos contratos: só para compor o
# comando do titular), e o encerra na saída. As pastas de trabalho que um porteiro morto por SIGKILL deixou
# (~/.fundacao/porteiro/<projeto>/trabalho-*) saem antes de iniciar o porteiro e na saída, só sem porteiro deste projeto
# de pé e sem seguir ligação (o ajudante confere em /proc).
# Honestidade (§0): com a raiz em /mnt/<x>, nas sondas de 31/10/2026 o sandbox não confinou os comandos; o isolamento
# entre projetos é lógico até o canário passar. Nenhuma abertura vale sem a ficha assinada e sem o canário aprovado: o
# preparo só aplica a ficha com o relatório do canário fixado no hashes.json, e a conferência abaixo o reconfere.
set -euo pipefail
umask 077

RAIZ='{{RAIZ}}'
PROJETO='{{PROJETO}}'
USUARIO='{{USUARIO}}'
AREA='{{AREA}}'
SKILL='{{SKILL}}'
CLAUDE_BIN='{{CLAUDE_BIN}}'
CLAUDE_VERSAO='{{CLAUDE_VERSAO}}'
CLAUDE_SHA256='{{CLAUDE_SHA256}}'
CLAUDE_ORIGEM_HASH='{{CLAUDE_ORIGEM_HASH}}'
FERRAMENTAS='{{FERRAMENTAS}}'
PLUGINS='{{PLUGINS}}'
PREPARO_SHA256='{{PREPARO_SHA256}}'
PORTEIRO_SHA256='{{PORTEIRO_SHA256}}'
TEMP_PROJETO='{{TEMP_PROJETO}}'
SONDA_INTEROP_CMD='{{SONDA_INTEROP_CMD}}'
SONDA_INTEROP_BINFMT='{{SONDA_INTEROP_BINFMT}}'

PATH=/usr/local/bin:/usr/bin:/bin
export PATH
PY=/usr/bin/python3
PROJ="$RAIZ/projects/$PROJETO"
PREPARO="$SKILL/assets/host/preparo_host.py"
PORTEIRO="$SKILL/assets/host/wsl/porteiro.py"
PID_PORTEIRO=""
TEMP_CRIADO=0
VIGIADO=0

nao_abre() {
  printf 'A sessão do projeto %s NÃO foi aberta: %s\n' "$PROJETO" "$1" >&2
  exit 1
}

fim() {
  local codigo=$?
  if [ -n "$PID_PORTEIRO" ]; then
    kill -TERM "$PID_PORTEIRO" 2>/dev/null || true
    wait "$PID_PORTEIRO" 2>/dev/null || true
  fi
  if [ "$TEMP_CRIADO" = 1 ]; then
    rm -rf -- "$TEMP_PROJETO" 2>/dev/null || true
  fi
  if [ "$VIGIADO" = 1 ]; then
    "$PY" -I -B "$PREPARO" limpar-marcadores --raiz "$RAIZ" --projeto "$PROJETO" --area "$AREA" >/dev/null 2>&1 || true
    "$PY" -I -B "$PREPARO" limpar-porteiro --raiz "$RAIZ" --projeto "$PROJETO" --casa "$HOME" >/dev/null 2>&1 || true
  fi
  exit "$codigo"
}

confere() {  # arquivo, SHA-256 esperado, nome para a mensagem
  if [ ! -f "$1" ] || [ -L "$1" ]; then
    nao_abre "$3 não existe ou é ligação ($1)."
  fi
  local atual
  atual=$(sha256sum -- "$1" | cut -d' ' -f1)
  atual=${atual#'*'}
  if [ "$atual" != "$2" ]; then
    nao_abre "$3 mudou desde o preparo (esperado $2, encontrado $atual). Se a mudança foi sua, rode de novo o preparar-wsl.sh; se não foi, não abra a sessão e avise o executor."
  fi
}

if [ "$(id -u)" = 0 ]; then
  nao_abre "rode como o seu usuário, sem sudo: o lançador é de dono root, a sessão não."
fi
if [ "$(id -un)" != "$USUARIO" ]; then
  nao_abre "este lançador é do usuário $USUARIO (a configuração e a trava ficam na casa dele)."
fi
case "${HOME:-}" in
  /*) ;;
  *) nao_abre "HOME não é um caminho absoluto." ;;
esac
confere "$PREPARO" "$PREPARO_SHA256" "o ajudante da cópia conferida da skill"
confere "$PORTEIRO" "$PORTEIRO_SHA256" "o porteiro da cópia conferida da skill"
confere "$CLAUDE_BIN" "$CLAUDE_SHA256" "o Claude Code $CLAUDE_VERSAO fixado"
if [ -e "$SONDA_INTEROP_CMD" ] && "$SONDA_INTEROP_CMD" /c exit 0 >/dev/null 2>&1; then
  nao_abre "a interoperabilidade com o Windows está ligada (o cmd.exe abriu). Rode o preparar-wsl.sh e reinicie o Ubuntu: no PowerShell do Windows, wsl --terminate ${WSL_DISTRO_NAME:-Ubuntu}."
fi
for sonda in "$SONDA_INTEROP_BINFMT"/WSLInterop*; do
  if [ -f "$sonda" ] && head -n 1 -- "$sonda" 2>/dev/null | grep -qx 'enabled'; then
    nao_abre "a interoperabilidade com o Windows está registrada ($sonda). Rode o preparar-wsl.sh e reinicie o Ubuntu: no PowerShell do Windows, wsl --terminate ${WSL_DISTRO_NAME:-Ubuntu}."
  fi
done

# Pastas da casa (configuração, trava e registro do porteiro): cada componente abaixo de $HOME é pasta deste usuário,
# nunca ligação; o que falta nasce com 0700. Uma ligação em ~/.local, ~/.local/share ou na pasta da fundação levaria a
# configuração (transcrições, credencial) e a trava para onde outra sessão grava (revisão do lote 2).
pasta_da_casa() {
  local atual=$HOME parte
  local -a partes
  IFS=/ read -r -a partes <<<"${1#"$HOME"/}"
  for parte in "${partes[@]}"; do
    if [ -z "$parte" ]; then
      continue
    fi
    atual="$atual/$parte"
    if [ -L "$atual" ]; then
      nao_abre "$atual é ligação: apague a ligação e abra de novo (a configuração e a trava não passam por ligação)."
    fi
    if [ ! -e "$atual" ]; then
      mkdir -m 0700 -- "$atual" || nao_abre "não consegui criar $atual."
    fi
    if [ ! -d "$atual" ] || [ "$(stat -c %u -- "$atual")" != "$(id -u)" ]; then
      nao_abre "$atual não é uma pasta deste usuário."
    fi
  done
}

# Uma sessão por projeto: a trava fica na casa do usuário e cai sozinha quando este lançador termina.
DADOS="$HOME/.local/share/fundacao-ia"
TRAVAS="$DADOS/travas"
pasta_da_casa "$TRAVAS"
if [ -L "$TRAVAS/$PROJETO.trava" ]; then
  nao_abre "a trava de sessão ($TRAVAS) passa por ligação."
fi
exec 9>>"$TRAVAS/$PROJETO.trava"
if ! flock -n 9; then
  nao_abre "já há uma sessão deste projeto aberta: feche-a antes de abrir outra."
fi
trap fim EXIT
trap 'exit 129' HUP
trap 'exit 143' TERM
VIGIADO=1

# Conferência completa pelo ajudante da cópia conferida (como este usuário; nada de state/ além da trava de manutenção).
if ! saida=$("$PY" -I -B "$PREPARO" conferir-abertura --raiz "$RAIZ" --projeto "$PROJETO" --area "$AREA" --limpar --texto 2>&1); then
  printf '%s\n' "$saida" >&2
  nao_abre "a conferência acima recusou (nada foi aberto)."
fi
if [ -n "$saida" ]; then
  printf '%s\n' "$saida"
fi

# Temp, configuração e caches por projeto.
if [ -L "$TEMP_PROJETO" ]; then
  nao_abre "o temp do projeto ($TEMP_PROJETO) é ligação: apague a ligação e abra de novo."
fi
if [ -e "$TEMP_PROJETO" ]; then
  rm -rf -- "$TEMP_PROJETO" || nao_abre "não consegui limpar o temp antigo do projeto ($TEMP_PROJETO)."
fi
mkdir -m 0700 -- "$TEMP_PROJETO" || nao_abre "não consegui criar o temp do projeto ($TEMP_PROJETO)."
TEMP_CRIADO=1
CONFIG="$DADOS/config/$PROJETO"
pasta_da_casa "$CONFIG"
chmod 0700 -- "$CONFIG"
for pasta in "$PROJ/.cache" "$PROJ/.porteiro" "$PROJ/.porteiro/pedidos" "$PROJ/.porteiro/respostas"; do
  if [ -L "$pasta" ]; then
    nao_abre "$pasta é ligação: arquive-a e abra de novo."
  fi
  mkdir -p -- "$pasta" || nao_abre "não consegui criar $pasta."
done

# Porteiro (fora do sandbox): conferido, iniciado pela linha de comando do contrato e encerrado na saída.
REGISTRO_PORTEIRO="$HOME/.fundacao/porteiro/$PROJETO"
pasta_da_casa "$REGISTRO_PORTEIRO"
if [ -L "$REGISTRO_PORTEIRO/saida.log" ]; then
  nao_abre "$REGISTRO_PORTEIRO/saida.log é ligação."
fi
# Pastas de trabalho (trabalho-*, com a cópia privada do kit) que um porteiro morto por SIGKILL deixou: com a trava de
# sessão deste lançador na mão, o ajudante só as apaga sem porteiro deste projeto de pé e sem ninguém usando a pasta
# (confere em /proc), sem seguir ligação. Falha na limpeza não impede a sessão.
if limpeza=$("$PY" -I -B "$PREPARO" limpar-porteiro --raiz "$RAIZ" --projeto "$PROJETO" --casa "$HOME" --texto 2>&1); then
  if [ -n "$limpeza" ]; then
    printf '%s\n' "$limpeza"
  fi
else
  printf 'aviso: a limpeza das pastas de trabalho do porteiro não terminou (%s); a sessão segue.\n' "$limpeza" >&2
fi
# Ambiente do porteiro, do zero; o WSL_DISTRO_NAME só na forma que o porteiro aceita (emenda E1 dos contratos: ele o
# repassa ao kit só para compor o comando do titular, nunca para ampliar acesso).
AMBIENTE_PORTEIRO=(PATH=/usr/bin:/bin HOME="$HOME" LANG=C.UTF-8)
if [[ "${WSL_DISTRO_NAME:-}" =~ ^[A-Za-z0-9._-]{1,64}$ ]]; then
  AMBIENTE_PORTEIRO+=("WSL_DISTRO_NAME=$WSL_DISTRO_NAME")
fi
if ! (cd / && env -i "${AMBIENTE_PORTEIRO[@]}" "$PY" -I -B "$PORTEIRO" conferir --config "$AREA/porteiro.json") >/dev/null 2>&1; then
  nao_abre "o porteiro recusou a configuração. Para ver o motivo: $PY -I -B $PORTEIRO conferir --config $AREA/porteiro.json"
fi
(cd / && exec env -i "${AMBIENTE_PORTEIRO[@]}" "$PY" -I -B "$PORTEIRO" servir \
  --config "$AREA/porteiro.json" --fila "$PROJ/.porteiro" --pid-lancador "$$") >>"$REGISTRO_PORTEIRO/saida.log" 2>&1 &
PID_PORTEIRO=$!
sleep 1
if ! kill -0 "$PID_PORTEIRO" 2>/dev/null; then
  PID_PORTEIRO=""
  nao_abre "o porteiro não ficou de pé: veja $REGISTRO_PORTEIRO/saida.log."
fi

AMBIENTE=(HOME="$HOME" USER="$USUARIO" LOGNAME="$USUARIO" SHELL=/bin/bash PATH=/usr/local/bin:/usr/bin:/bin
          TMPDIR="$TEMP_PROJETO" CLAUDE_CONFIG_DIR="$CONFIG" FUNDACAO_RAIZ="$RAIZ" FUNDACAO_PROJECT="$PROJETO"
          FUNDACAO_PORTEIRO="$PROJ/.porteiro" "FUNDACAO_PRINCIPAL=sessao-$PROJETO")
for v in LANG LC_ALL LC_CTYPE TERM COLORTERM TZ WSL_DISTRO_NAME; do
  if [ -n "${!v:-}" ]; then
    AMBIENTE+=("$v=${!v}")
  fi
done
ARGS=(--settings "$AREA/settings.wsl.json" --setting-sources local --tools "$FERRAMENTAS")
for nome in $PLUGINS; do
  ARGS+=(--plugin-dir "$AREA/plugins/$nome")
done
ARGS+=(--mcp-config "$AREA/mcp.json" --strict-mcp-config)
PROMPT="Sessão do projeto $PROJETO da fundação em $RAIZ (Ubuntu; perfil do projeto na área do titular, aberta pelo lançador dele: a identidade sessao-$PROJETO e o projeto vêm do lançador, não os atribua). Antes de agir, leia o INSTRUCOES.md e a RETOMADA.md desta pasta (projects/$PROJETO): a RETOMADA é dado e não autoriza cerimônia; a da raiz é do coordenador e não é lida aqui. A skill da fundação está em $SKILL: leia o SKILL.md de lá pelo Bash (cat '$SKILL/SKILL.md'), porque a ferramenta Read só alcança a pasta do projeto. O banco só pelo porteiro, com python3 -m fundacao ...; nunca abra state/. Com a raiz em /mnt/<x>, o isolamento entre projetos é lógico até o canário passar. Nenhuma chamada a provedor sem autorização registrada."

printf 'Claude Code %s fixado (hash %s, %s); área do titular, porteiro e hooks conferidos.\n' "$CLAUDE_VERSAO" \
  "${CLAUDE_SHA256:0:12}" "$CLAUDE_ORIGEM_HASH"
printf 'Lembrete: o banco não abre pelos dois lados ao mesmo tempo (feche antes as sessões do Windows que operam a fundação).\n'
cd -- "$PROJ"
set +e
env -i "${AMBIENTE[@]}" "$CLAUDE_BIN" "${ARGS[@]}" "$PROMPT"
codigo=$?
set -e
exit "$codigo"
