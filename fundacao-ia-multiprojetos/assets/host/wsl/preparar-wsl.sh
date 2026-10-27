#!/usr/bin/env bash
# Prepara o Ubuntu do WSL2 para a sessão de dados reais da fundação (skill fundacao-ia-multiprojetos).
#
# Rode no terminal do Ubuntu como o seu usuário, sem sudo na frente: o sudo pede a sua senha do Linux só no que
# exige administrador, e o script diz antes o que é. Ordem: primeiro o preparar-maquina.ps1 no Windows (hooks,
# perfis e identidade em <raiz>/.claude), depois este. Ele confere antes o que já existe (rodar de novo não repete):
#  1. pacotes do sandbox do Claude Code, bubblewrap e socat (sudo apt-get install, com internet), e o perfil do
#     AppArmor do bwrap quando o Ubuntu restringe namespaces (kernel.apparmor_restrict_unprivileged_userns = 1);
#  2. /etc/wsl.conf com um só bloco [interop] desligado (enabled=false, appendWindowsPath=false), sem repetir blocos
#     (sudo; cópia do anterior ao lado); vale depois de reiniciar o Ubuntu (wsl --terminate, no Windows);
#  3. Claude Code fixado: cópia da versão em ~/.local/share/fundacao-ia/claude/<versão>/claude, que a limpeza
#     automática de versões não apaga, com o SHA-256 conferido contra o informado (--claude-sha256, o do manifesto
#     assinado da Anthropic) ou, sem ele, o do binário atual, registrado como não conferido;
#  4. ligação da skill em ~/.claude/skills, se faltar, e conferência do que o Windows deixou na raiz: o perfil igual ao
#     que o modelo da skill gera (com os projetos da raiz negados), os hooks iguais aos da skill e o settings.local.json
#     só com a identidade do titular (--titular) e o projeto, porque a sessão o carrega inteiro;
#  5. lançador (padrão ~/abrir-fundacao.sh, do modelo abrir-sessao.sh) com os SHA-256 do Claude Code, do perfil, dos
#     hooks e do settings.local.json e o titular fixados; o ajudante confere de novo os mesmos bytes cujo hash fixa.
# O preparo só fixa o que conferiu inteiro [auditoria Codex Security da 1.7.6, #5]. Não instala o Claude Code nem faz
# o login (credencial do titular): se faltar, mostra o comando e para.
#
# Códigos: 0 pronto (ou simulação sem erro) · 1 parou (veja a linha [erro]) · 2 uso incorreto
#          · 3 falta algo que só o titular faz (instalar o Claude Code e fazer o login).
set -uo pipefail

AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SKILL_DIR=$(cd "$AQUI/../../.." && pwd)
AJUDANTE="$AQUI/../preparo_host.py"
RAIZ=""
PROJETO=""
TITULAR=""
SIMULAR=0
CLAUDE_VERSAO=""
CLAUDE_SHA256=""
LANCADOR="$HOME/abrir-fundacao.sh"
WSL_CONF="/etc/wsl.conf"
PY=""
CODIGO=0
REINICIAR=0
DISTRO=${WSL_DISTRO_NAME:-Ubuntu}

uso() {
  cat <<'FIM'
Uso: bash preparar-wsl.sh --raiz "/mnt/d/IA/fundacao" --projeto <id> --titular <id> [--simular]
       [--claude-versao <versão>] [--claude-sha256 <hash do manifesto assinado>]
       [--lancador <arquivo>] [--wsl-conf <arquivo>] [--python <python3>]
--titular é a sua identidade, a mesma do -Titular do preparar-maquina.ps1: o lançador só abre com ela.
--simular só mostra o plano (nada é alterado). Sem --claude-versao, vale a versão para a qual ~/.local/bin/claude
aponta. O hash oficial de cada versão está em platforms.linux-x64.checksum do manifesto
https://downloads.claude.ai/claude-code-releases/<versão>/manifest.json, assinado (manifest.json.sig) pela chave de
lançamento da Anthropic, impressão digital 31DD DE24 DDFA B679 F42D 7BD2 BAA9 29FF 1A7E CACE.
FIM
}

while [ $# -gt 0 ]; do
  case "$1" in
    --simular) SIMULAR=1; shift ;;
    -h|--ajuda|--help) uso; exit 0 ;;
    --raiz|--projeto|--titular|--claude-versao|--claude-sha256|--lancador|--wsl-conf|--python)
      if [ $# -lt 2 ]; then uso >&2; exit 2; fi
      case "$1" in
        --raiz) RAIZ=$2 ;;
        --projeto) PROJETO=$2 ;;
        --titular) TITULAR=$2 ;;
        --claude-versao) CLAUDE_VERSAO=$2 ;;
        --claude-sha256) CLAUDE_SHA256=$2 ;;
        --lancador) LANCADOR=$2 ;;
        --wsl-conf) WSL_CONF=$2 ;;
        --python) PY=$2 ;;
      esac
      shift 2 ;;
    *) printf 'Opção desconhecida: %s\n' "$1" >&2; uso >&2; exit 2 ;;
  esac
done

if [ -z "$RAIZ" ] || [ -z "$PROJETO" ] || [ -z "$TITULAR" ]; then uso >&2; exit 2; fi
if ! [[ $PROJETO =~ ^[a-z0-9]([a-z0-9._-]{0,62}[a-z0-9])?$ ]]; then
  printf 'Projeto inválido: %s\n' "$PROJETO" >&2; exit 2
fi
if ! [[ $TITULAR =~ ^[a-z0-9]([a-z0-9._-]{0,62}[a-z0-9])?$ ]]; then
  printf 'Titular inválido: %s\n' "$TITULAR" >&2; exit 2
fi
if [ -n "$CLAUDE_SHA256" ] && ! [[ $CLAUDE_SHA256 =~ ^[0-9a-f]{64}$ ]]; then
  printf 'SHA-256 inválido (64 dígitos hexadecimais minúsculos): %s\n' "$CLAUDE_SHA256" >&2; exit 2
fi
if [ "$(id -u)" = "0" ]; then
  echo 'Rode como o seu usuário, sem sudo na frente: o script pede o sudo só quando precisa.' >&2; exit 2
fi
if [ -z "$PY" ]; then
  if [ -x /usr/bin/python3 ]; then PY=/usr/bin/python3; else PY=$(command -v python3 || true); fi
fi
if [ -z "$PY" ]; then
  echo 'Python 3 não encontrado (os hooks também precisam dele): sudo apt-get install -y python3' >&2; exit 2
fi
RAIZ=${RAIZ%/}

relata() {  # ação, item, detalhe
  printf '  [%s] %s: %s\n' "$1" "$2" "$3"
  case "$1" in
    erro) CODIGO=1 ;;
    pendente) if [ "$CODIGO" = 0 ]; then CODIGO=3; fi ;;
  esac
}

como_root() {  # o sudo pede a sua senha do Linux
  if [ "$(id -u)" = "0" ]; then "$@"; else sudo "$@"; fi
}

grava() {  # grava no lugar de um arquivo do sistema: direto se esta conta puder, senão com o sudo
  local alvo=$1; shift
  if [ -w "$alvo" ] || { [ ! -e "$alvo" ] && [ -w "$(dirname "$alvo")" ]; }; then "$@"; else como_root "$@"; fi
}

sha_de() {
  local h
  h=$(sha256sum "$1" | cut -d' ' -f1)
  printf '%s' "${h#'*'}"
}

em_wsl() {
  [ -n "${WSL_DISTRO_NAME:-}" ] || grep -qi microsoft /proc/version 2>/dev/null
}

fim() {
  echo
  if [ "$REINICIAR" = 1 ]; then
    echo "Depois: feche as janelas do Ubuntu e, no PowerShell do Windows, rode: wsl --terminate $DISTRO"
    echo '(a interoperabilidade desligada vale a partir do próximo início do Ubuntu).'
  fi
  local msg
  case "$CODIGO" in
    0) if [ "$SIMULAR" = 1 ]; then msg='simulação: o plano acima mostra o que a execução real faria'
       else msg="Ubuntu preparado. Para abrir a sessão de dados reais: bash $LANCADOR"; fi ;;
    3) msg='falta algo que só você faz (veja a linha [pendente]); depois rode este script de novo' ;;
    *) msg='parou: veja a linha [erro]; nada além do que aparece acima foi alterado' ;;
  esac
  printf 'Resultado (código %s): %s\n' "$CODIGO" "$msg"
  exit "$CODIGO"
}

if [ "$SIMULAR" = 1 ]; then
  echo 'Fundação de IA: preparo do Ubuntu (WSL2) para a sessão de dados reais   [SIMULAÇÃO: nada foi alterado]'
else
  echo 'Fundação de IA: preparo do Ubuntu (WSL2) para a sessão de dados reais'
fi
echo "Raiz: $RAIZ   Projeto: $PROJETO   Titular: $TITULAR"

# 0. Ambiente
if em_wsl; then
  relata igual ambiente "WSL2 ($DISTRO)"
elif [ "$SIMULAR" = 1 ]; then
  relata aviso ambiente 'este terminal não é o do WSL; a simulação segue só para mostrar o plano'
else
  relata erro ambiente 'rode no terminal do Ubuntu do WSL2'
  fim
fi

# 1. Pacotes do sandbox
faltam=()
command -v bwrap >/dev/null 2>&1 || faltam+=(bubblewrap)
command -v socat >/dev/null 2>&1 || faltam+=(socat)
if [ ${#faltam[@]} -eq 0 ]; then
  relata igual pacotes 'bubblewrap e socat presentes'
elif [ "$SIMULAR" = 1 ]; then
  relata instalar pacotes "sudo apt-get install -y ${faltam[*]} (exige administrador do Linux: o sudo pede a sua senha; usa a internet)"
else
  echo "Instalando ${faltam[*]}: o sudo vai pedir a sua senha do Linux."
  if como_root apt-get update -q && como_root apt-get install -y "${faltam[@]}" && command -v bwrap >/dev/null 2>&1 &&
     command -v socat >/dev/null 2>&1; then
    relata criar pacotes "instalados: ${faltam[*]}"
  else
    relata erro pacotes "a instalação não terminou; rode: sudo apt-get install -y ${faltam[*]}"
  fi
fi

# 1b. AppArmor do Ubuntu 24.04 ou mais novo (documentação do sandbox do Claude Code)
restrito=$(sysctl -n kernel.apparmor_restrict_unprivileged_userns 2>/dev/null || true)
if [ "$restrito" != "1" ]; then
  relata igual apparmor "não restringe o bubblewrap (sysctl: ${restrito:-ausente}); nada a fazer"
elif [ -f /etc/apparmor.d/bwrap ]; then
  relata igual apparmor 'perfil /etc/apparmor.d/bwrap presente'
elif [ "$SIMULAR" = 1 ]; then
  relata criar apparmor 'perfil /etc/apparmor.d/bwrap (userns só para o bwrap) e sudo systemctl reload apparmor (exige administrador do Linux)'
else
  if printf '%s\n' 'abi <abi/4.0>,' 'include <tunables/global>' '' 'profile bwrap /usr/bin/bwrap flags=(unconfined) {' \
       '  userns,' '  include if exists <local/bwrap>' '}' | como_root tee /etc/apparmor.d/bwrap >/dev/null &&
     como_root systemctl reload apparmor; then
    relata criar apparmor 'perfil /etc/apparmor.d/bwrap gravado e AppArmor recarregado'
  else
    relata erro apparmor 'não consegui gravar /etc/apparmor.d/bwrap ou recarregar o AppArmor'
  fi
fi

# 2. /etc/wsl.conf: um só bloco [interop] desligado
if ! estado=$("$PY" -I -B "$AJUDANTE" wsl-conf --arquivo "$WSL_CONF"); then
  relata erro wsl.conf "não consegui ler $WSL_CONF: $estado"
elif printf '%s' "$estado" | grep -q '"mudou": false'; then
  relata igual wsl.conf "$WSL_CONF com um só bloco [interop] desligado"
elif [ "$SIMULAR" = 1 ]; then
  relata atualizar wsl.conf "$WSL_CONF com um só bloco [interop] (enabled=false, appendWindowsPath=false), cópia do anterior ao lado (sudo)"
  REINICIAR=1
else
  tmp=$(mktemp)
  carimbo=$(date +%Y%m%dT%H%M%S)
  if "$PY" -I -B "$AJUDANTE" wsl-conf --arquivo "$WSL_CONF" --saida "$tmp" >/dev/null &&
     { [ ! -e "$WSL_CONF" ] || grava "$WSL_CONF" cp -p "$WSL_CONF" "$WSL_CONF.anterior-$carimbo"; } &&
     grava "$WSL_CONF" install -m 0644 "$tmp" "$WSL_CONF"; then
    relata atualizar wsl.conf "$WSL_CONF com um só bloco [interop] desligado; anterior em $WSL_CONF.anterior-$carimbo"
    REINICIAR=1
  else
    relata erro wsl.conf "não consegui gravar $WSL_CONF"
  fi
  rm -f "$tmp"
fi

# 3. Claude Code fixado por hash
VERSOES="$HOME/.local/share/claude/versions"
if [ -z "$CLAUDE_VERSAO" ]; then
  alvo=$(readlink -f "$HOME/.local/bin/claude" 2>/dev/null || true)
  case "$alvo" in "$VERSOES"/*) CLAUDE_VERSAO=${alvo##*/} ;; esac
fi
CLAUDE_OK=0
CLAUDE_HASH=""
ORIGEM_HASH=""
FIXO="$HOME/.local/share/fundacao-ia/claude/${CLAUDE_VERSAO:-sem-versao}/claude"
if [ -z "$CLAUDE_VERSAO" ] || ! [[ $CLAUDE_VERSAO =~ ^[0-9]+[.][0-9]+[.][0-9]+$ ]] || [ ! -f "$VERSOES/$CLAUDE_VERSAO" ]; then
  relata pendente claude "Claude Code ${CLAUDE_VERSAO:-(versão não encontrada)} ausente em $VERSOES. Instale no Ubuntu com: curl -fsSL https://claude.ai/install.sh | bash -s ${CLAUDE_VERSAO:-stable}; depois faça o login (claude, e /exit) e rode este script de novo"
else
  CLAUDE_HASH=$(sha_de "$VERSOES/$CLAUDE_VERSAO")
  if [ -n "$CLAUDE_SHA256" ] && [ "$CLAUDE_HASH" != "$CLAUDE_SHA256" ]; then
    relata erro claude "o SHA-256 do Claude Code $CLAUDE_VERSAO ($CLAUDE_HASH) não confere com o informado ($CLAUDE_SHA256): esse binário não é fixado"
  else
    if [ -n "$CLAUDE_SHA256" ]; then ORIGEM_HASH='conferido com o hash informado, do manifesto assinado da Anthropic'
    else ORIGEM_HASH='binário atual, não conferido contra o manifesto assinado'; fi
    CLAUDE_OK=1
    if [ -f "$FIXO" ] && [ "$(sha_de "$FIXO")" = "$CLAUDE_HASH" ]; then
      relata igual claude "$CLAUDE_VERSAO fixado em $FIXO (SHA-256 $CLAUDE_HASH; $ORIGEM_HASH)"
    elif [ "$SIMULAR" = 1 ]; then
      relata criar claude "copiar $VERSOES/$CLAUDE_VERSAO para $FIXO e fixar o SHA-256 $CLAUDE_HASH ($ORIGEM_HASH)"
    elif mkdir -p "$(dirname "$FIXO")" && cp "$VERSOES/$CLAUDE_VERSAO" "$FIXO.novo" && chmod 0555 "$FIXO.novo" &&
         mv -f "$FIXO.novo" "$FIXO" && [ "$(sha_de "$FIXO")" = "$CLAUDE_HASH" ]; then
      relata criar claude "$CLAUDE_VERSAO fixado em $FIXO (SHA-256 $CLAUDE_HASH; $ORIGEM_HASH)"
    else
      CLAUDE_OK=0
      relata erro claude "não consegui copiar o Claude Code para $FIXO"
    fi
  fi
fi

# 4. Ligação da skill e o que o Windows preparou na raiz
LIGACAO="$HOME/.claude/skills/fundacao-ia-multiprojetos"
if [ -e "$LIGACAO" ] || [ -L "$LIGACAO" ]; then
  relata igual skill "$LIGACAO presente"
elif [ "$SIMULAR" = 1 ]; then
  relata criar skill "ligação $LIGACAO para $SKILL_DIR"
elif mkdir -p "$(dirname "$LIGACAO")" && ln -s "$SKILL_DIR" "$LIGACAO"; then
  relata criar skill "ligação $LIGACAO para $SKILL_DIR"
else
  relata erro skill "não consegui criar a ligação $LIGACAO"
fi
PERFIL="$RAIZ/.claude/settings.wsl.json"
if [ ! -f "$PERFIL" ]; then
  relata erro perfil "$PERFIL não existe: rode antes, no PowerShell do Windows, o preparar-maquina.ps1 com -Projeto $PROJETO"
elif saida=$("$PY" -I -B "$AJUDANTE" conferir-perfil-wsl --perfil "$PERFIL" --raiz "$RAIZ" --projeto "$PROJETO"); then
  relata igual perfil "$PERFIL igual ao do modelo da skill (SHA-256 $(sha_de "$PERFIL")); confira as vagas: $saida"
else
  relata erro perfil "$PERFIL não é o que o modelo da skill gera para esta raiz ($saida): rode de novo o preparar-maquina.ps1 no Windows com -Projeto $PROJETO"
fi
for h in guarda_caminho.py guarda_identidade.py sinais_sessao.py; do
  if [ ! -f "$RAIZ/.claude/hooks/$h" ]; then
    relata erro "hook $h" "ausente em $RAIZ/.claude/hooks: rode o preparar-maquina.ps1 no Windows"
  elif cmp -s "$RAIZ/.claude/hooks/$h" "$SKILL_DIR/assets/hooks/$h"; then
    relata igual "hook $h" "igual ao da skill (SHA-256 $(sha_de "$RAIZ/.claude/hooks/$h"))"
  else
    relata erro "hook $h" "difere do hook da skill ($SKILL_DIR/assets/hooks/$h): rode de novo o preparar-maquina.ps1 no Windows"
  fi
done
LOCAL="$RAIZ/.claude/settings.local.json"
if [ ! -f "$LOCAL" ]; then
  relata erro identidade "$LOCAL ausente: rode o preparar-maquina.ps1 no Windows"
elif saida=$("$PY" -I -B "$AJUDANTE" conferir-identidade --arquivo "$LOCAL" --titular "$TITULAR" --projeto "$PROJETO"); then
  relata igual identidade "$LOCAL só com a identidade de $TITULAR (SHA-256 $(sha_de "$LOCAL"))"
else
  relata erro identidade "$LOCAL não serve para a sessão de dados reais, que o carrega inteiro ($saida): rode de novo, no Windows, o preparar-maquina.ps1 com -Titular $TITULAR -Projeto $PROJETO (ele deixa só a identidade e guarda o anterior em .claude/anteriores)"
fi

# 5. Lançador com os hashes fixados (o ajudante confere de novo os mesmos bytes cujo hash fixa)
if [ "$CLAUDE_OK" = 1 ] && [ "$CODIGO" != 1 ]; then
  args=(lancador --raiz "$RAIZ" --projeto "$PROJETO" --titular "$TITULAR" --claude "$FIXO" --claude-versao "$CLAUDE_VERSAO"
        --claude-sha256 "$CLAUDE_HASH" --origem-hash "$ORIGEM_HASH" --skill-md "$SKILL_DIR/SKILL.md")
  if ! novo=$("$PY" -I -B "$AJUDANTE" "${args[@]}" --saida -); then
    relata erro lancador "o modelo do lançador recusou: $novo"
  elif [ -f "$LANCADOR" ] && [ "$(cat "$LANCADOR")" = "$novo" ]; then
    relata igual lancador "$LANCADOR (SHA-256 $(sha_de "$LANCADOR"))"
  else
    acao=criar
    if [ -f "$LANCADOR" ]; then acao=atualizar; fi
    if [ "$SIMULAR" = 1 ]; then
      relata "$acao" lancador "$LANCADOR, com os SHA-256 do Claude Code, do perfil, dos hooks e da identidade fixados"
    elif { [ "$acao" = criar ] || cp -p "$LANCADOR" "$LANCADOR.anterior-$(date +%Y%m%dT%H%M%S)"; } &&
         "$PY" -I -B "$AJUDANTE" "${args[@]}" --saida "$LANCADOR.novo" >/dev/null && chmod 0755 "$LANCADOR.novo" &&
         mv -f "$LANCADOR.novo" "$LANCADOR"; then
      relata "$acao" lancador "$LANCADOR (SHA-256 $(sha_de "$LANCADOR"))"
    else
      relata erro lancador "não consegui gravar $LANCADOR"
    fi
  fi
fi

fim
