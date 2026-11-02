#!/usr/bin/env bash
# Prepara o Ubuntu do WSL2 para as sessões de PROJETO da fundação (skill fundacao-ia-multiprojetos, 1.7.10).
#
# Rode no terminal do Ubuntu como o seu usuário, sem sudo na frente: o sudo pede a sua senha do Linux só no que exige
# administrador, e o script diz antes o que é. Ordem: primeiro o preparar-maquina.ps1 (ou o preparar-projeto.ps1) no
# Windows (hooks em <raiz>/.claude/hooks), depois este. Ele confere antes o que já existe (rodar de novo não repete):
#  1. pacotes: bubblewrap e socat (sandbox do Claude Code), python3-venv, npm e corepack (ferramentas dos projetos,
#     instaladas fora de /home: G1) e o perfil do AppArmor do bwrap quando o Ubuntu restringe namespaces;
#  1b. o filtro seccomp do sandbox (npm install -g --ignore-scripts @anthropic-ai/sandbox-runtime@<versão>, a partir
#     de / e sem rodar os scripts do pacote; documentação oficial conferida em 31/10/2026), só com --seccomp-versao;
#     sem ele, o relatório diz "sockets sem filtro";
#  1d. com --canario <relatório>, o relatório do ensaio real do canário (scripts/ensaio_isolamento_wsl.py) vai para a
#     área do titular (sudo; preparo_host.py instalar-canario): sem ele, nenhuma ficha de aberturas é aplicada; o real
#     que não aprova (false ou null) vai como revogação da mesma versão do Claude Code, o preparo dos projetos segue e
#     só o projeto com o aceite de risco do titular para esse relatório (fundacao_titular.py aceitar-risco) abre;
#  2. /etc/wsl.conf com um só bloco [interop] desligado (enabled=false, appendWindowsPath=false), sem repetir blocos
#     (sudo; cópia do anterior ao lado); vale depois de reiniciar o Ubuntu (wsl --terminate, no Windows);
#  3. Claude Code fixado: cópia da versão em ~/.local/share/fundacao-ia/claude/<versão>/claude, que a limpeza
#     automática de versões não apaga, com o SHA-256 conferido contra o informado (--claude-sha256, o do manifesto
#     assinado da Anthropic) ou, sem ele, o do binário atual, registrado como não conferido;
#  4. o lançador único da 1.7.9 (~/abrir-fundacao.sh) é aposentado: a cópia fica ao lado e ele passa a mostrar o
#     comando novo (cada projeto tem o seu);
#  5. para cada --projeto, a área do titular de dono root (sudo): preparo_host.py instalar-projeto grava
#     /etc/fundacao-ia/projetos/<p>/ (perfil, porteiro.json, mcp.json, aberturas.json, ficha, plugins, hashes.json),
#     as cópias conferidas da skill e do Claude Code e o lançador /usr/local/bin/abrir-fundacao-<p>; ele confere antes
#     os hooks da raiz (iguais aos da skill), o kit da raiz (igual ao da skill) e a ficha assinada da caixa de entrada.
#     Grava também a cópia protegida da ferramenta do titular em /usr/local/lib/fundacao-ia/<versão do kit>/ (root,
#     0755/0644, com o hashes.json que ela confere): dela roda a forma do Ubuntu de assinar a ficha (folha da
#     integração da 1.7.10, I11).
# O preparo só fixa o que conferiu inteiro [auditoria Codex Security da 1.7.6, #5]. Não instala o Claude Code nem faz
# o login (credencial do titular): se faltar, mostra o comando e para. Honestidade (contratos do lote 2 da 1.7.10, §0):
# com a raiz em /mnt/<x>, o isolamento entre projetos é lógico até o canário passar no ambiente real.
#
# Códigos: 0 pronto (ou simulação sem erro) · 1 parou (veja a linha [erro]) · 2 uso incorreto
#          · 3 falta algo que só o titular faz (instalar o Claude Code, fazer o login, o npm ou o corepack).
set -uo pipefail

AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SKILL_DIR=$(cd "$AQUI/../../.." && pwd)
AJUDANTE="$AQUI/../preparo_host.py"
RAIZ=""
PROJETOS=()
TITULAR=""
SIMULAR=0
CLAUDE_VERSAO=""
CLAUDE_SHA256=""
LANCADOR="$HOME/abrir-fundacao.sh"
WSL_CONF="/etc/wsl.conf"
PY=""
PERFIL_WINDOWS=""
AREA_RAIZ=""
BIN_DIR=""
TEMP_BASE=""
SONDA_CMD=""
SONDA_BINFMT=""
FERRAMENTA_BASE=""
SECCOMP_VERSAO=""
CANARIO=""
CODIGO=0
REINICIAR=0
DISTRO=${WSL_DISTRO_NAME:-Ubuntu}
LANCADORES=()

uso() {
  cat <<'FIM'
Uso: bash preparar-wsl.sh --raiz "/mnt/d/IA/fundacao" --projeto <id> [--projeto <id>]... --titular <id> [--simular]
       [--claude-versao <versão>] [--claude-sha256 <hash do manifesto assinado>] [--perfil-windows /mnt/c/Users/<usuario>]
       [--seccomp-versao <versão>] [--canario <relatório do ensaio>] [--wsl-conf <arquivo>] [--python <python3>]
       [--lancador <lançador antigo>]
--titular é a sua identidade, a mesma do -Titular do preparar-maquina.ps1: ela assina as decisões que o porteiro
registra. --canario instala o relatório do ensaio real (ensaio_isolamento_wsl.py rodar): sem ele, nenhuma abertura da
ficha vale; reprovado, ele revoga e só vale no projeto com o seu aceite de risco assinado
(fundacao_titular.py aceitar-risco). --simular só mostra o plano (nada é alterado). Sem --claude-versao, vale a versão para a qual
~/.local/bin/claude aponta. O hash oficial de cada versão está em platforms.linux-x64.checksum do manifesto
https://downloads.claude.ai/claude-code-releases/<versão>/manifest.json, assinado (manifest.json.sig) pela chave de
lançamento da Anthropic, impressão digital 31DD DE24 DDFA B679 F42D 7BD2 BAA9 29FF 1A7E CACE.
Só para ensaio (sem sudo, em pastas temporárias): --area-raiz, --bin, --temp-base, --sonda-interop-cmd,
--sonda-interop-binfmt e --ferramenta-base (a cópia protegida da ferramenta do titular; sem ela, o ensaio não a grava).
FIM
}

while [ $# -gt 0 ]; do
  case "$1" in
    --simular) SIMULAR=1; shift ;;
    -h|--ajuda|--help) uso; exit 0 ;;
    --raiz|--projeto|--titular|--claude-versao|--claude-sha256|--lancador|--wsl-conf|--python|--perfil-windows|--area-raiz|--bin|--temp-base|--sonda-interop-cmd|--sonda-interop-binfmt|--ferramenta-base|--seccomp-versao|--canario)
      if [ $# -lt 2 ]; then uso >&2; exit 2; fi
      case "$1" in
        --raiz) RAIZ=$2 ;;
        --projeto) PROJETOS+=("$2") ;;
        --titular) TITULAR=$2 ;;
        --claude-versao) CLAUDE_VERSAO=$2 ;;
        --claude-sha256) CLAUDE_SHA256=$2 ;;
        --lancador) LANCADOR=$2 ;;
        --wsl-conf) WSL_CONF=$2 ;;
        --python) PY=$2 ;;
        --perfil-windows) PERFIL_WINDOWS=$2 ;;
        --area-raiz) AREA_RAIZ=$2 ;;
        --bin) BIN_DIR=$2 ;;
        --temp-base) TEMP_BASE=$2 ;;
        --sonda-interop-cmd) SONDA_CMD=$2 ;;
        --sonda-interop-binfmt) SONDA_BINFMT=$2 ;;
        --ferramenta-base) FERRAMENTA_BASE=$2 ;;
        --seccomp-versao) SECCOMP_VERSAO=$2 ;;
        --canario) CANARIO=$2 ;;
      esac
      shift 2 ;;
    *) printf 'Opção desconhecida: %s\n' "$1" >&2; uso >&2; exit 2 ;;
  esac
done

if [ -z "$RAIZ" ] || [ ${#PROJETOS[@]} -eq 0 ] || [ -z "$TITULAR" ]; then uso >&2; exit 2; fi
for PROJETO in "${PROJETOS[@]}"; do  # a forma do kit e do porteiro: [a-z0-9-], 1 a 40, sem '--'
  if ! [[ $PROJETO =~ ^[a-z0-9]([a-z0-9-]{0,38}[a-z0-9])?$ ]] || [[ $PROJETO == *--* ]]; then
    printf 'Projeto inválido: %s (1 a 40 letras minúsculas, dígitos ou -, sem - nas pontas nem --)\n' "$PROJETO" >&2
    exit 2
  fi
done
if ! [[ $TITULAR =~ ^[a-z0-9]([a-z0-9._-]{0,62}[a-z0-9])?$ ]]; then
  printf 'Titular inválido: %s\n' "$TITULAR" >&2; exit 2
fi
if [ -n "$CLAUDE_SHA256" ] && ! [[ $CLAUDE_SHA256 =~ ^[0-9a-f]{64}$ ]]; then
  printf 'SHA-256 inválido (64 dígitos hexadecimais minúsculos): %s\n' "$CLAUDE_SHA256" >&2; exit 2
fi
if [ -n "$SECCOMP_VERSAO" ] && ! [[ $SECCOMP_VERSAO =~ ^[0-9]+[.][0-9]+[.][0-9]+$ ]]; then
  printf 'Versão do filtro seccomp inválida (x.y.z): %s\n' "$SECCOMP_VERSAO" >&2; exit 2
fi
ENSAIO=0
if [ -n "$AREA_RAIZ" ] || [ -n "$BIN_DIR" ] || [ -n "$TEMP_BASE" ] || [ -n "$SONDA_CMD" ] || [ -n "$SONDA_BINFMT" ] ||
   [ -n "$FERRAMENTA_BASE" ]; then
  if [ -z "$AREA_RAIZ" ] || [ -z "$BIN_DIR" ]; then
    echo 'Ensaio: --area-raiz e --bin vão juntos (e as outras opções de ensaio só com eles).' >&2; exit 2
  fi
  ENSAIO=1
fi
if [ "$(id -u)" = "0" ]; then
  echo 'Rode como o seu usuário, sem sudo na frente: o script pede o sudo só quando precisa.' >&2; exit 2
fi
if [ -z "$PY" ]; then
  if [ -x /usr/bin/python3 ]; then PY=/usr/bin/python3; else PY=$(command -v python3 || true); fi
fi
if [ -z "$PY" ]; then
  echo 'Python 3 não encontrado (os hooks e o porteiro também precisam dele): sudo apt-get install -y python3' >&2; exit 2
fi
RAIZ=${RAIZ%/}
if [ -z "$PERFIL_WINDOWS" ]; then
  case "$SKILL_DIR" in
    /mnt/[a-z]/Users/*) PERFIL_WINDOWS=$(printf '%s' "$SKILL_DIR" | cut -d/ -f1-5) ;;
  esac
fi

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

instala_pacotes() {  # pacotes do apt; devolve 0 se instalou
  echo "Instalando $*: o sudo vai pedir a sua senha do Linux."
  como_root apt-get update -q && como_root apt-get install -y "$@"
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
       else msg="Ubuntu preparado. Para abrir a sessão de cada projeto: ${LANCADORES[*]:-(nenhum)}"; fi ;;
    3) msg='falta algo que só você faz (veja a linha [pendente]); depois rode este script de novo' ;;
    *) msg='parou: veja a linha [erro]; nada além do que aparece acima foi alterado' ;;
  esac
  printf 'Resultado (código %s): %s\n' "$CODIGO" "$msg"
  exit "$CODIGO"
}

if [ "$SIMULAR" = 1 ]; then
  echo 'Fundação de IA: preparo do Ubuntu (WSL2) para as sessões de projeto   [SIMULAÇÃO: nada foi alterado]'
else
  echo 'Fundação de IA: preparo do Ubuntu (WSL2) para as sessões de projeto'
fi
echo "Raiz: $RAIZ   Projetos: ${PROJETOS[*]}   Titular: $TITULAR"

# 0. Ambiente
if em_wsl; then
  relata igual ambiente "WSL2 ($DISTRO)"
elif [ "$SIMULAR" = 1 ] || [ "$ENSAIO" = 1 ]; then
  relata aviso ambiente 'este terminal não é o do WSL; segue só para mostrar o plano (ou o ensaio)'
else
  relata erro ambiente 'rode no terminal do Ubuntu do WSL2'
  fim
fi

# 1. Pacotes do sandbox e das ferramentas dos projetos (G1: fora de /home, que o perfil do projeto não lê)
faltam=()
command -v bwrap >/dev/null 2>&1 || faltam+=(bubblewrap)
command -v socat >/dev/null 2>&1 || faltam+=(socat)
if ! command -v dpkg-query >/dev/null 2>&1 || ! dpkg-query -W -f='${Status}' python3-venv 2>/dev/null | grep -q 'install ok installed'; then
  faltam+=(python3-venv)
fi
if ! command -v npm >/dev/null 2>&1 && ! command -v node >/dev/null 2>&1; then
  faltam+=(nodejs npm)
fi
if [ ${#faltam[@]} -eq 0 ]; then
  relata igual pacotes 'bubblewrap, socat e python3-venv presentes'
elif [ "$SIMULAR" = 1 ]; then
  relata instalar pacotes "sudo apt-get install -y ${faltam[*]} (exige administrador do Linux: o sudo pede a sua senha; usa a internet)"
elif instala_pacotes "${faltam[@]}" && command -v bwrap >/dev/null 2>&1 && command -v socat >/dev/null 2>&1; then
  relata criar pacotes "instalados: ${faltam[*]}"
else
  relata erro pacotes "a instalação não terminou; rode: sudo apt-get install -y ${faltam[*]}"
fi
if ! command -v npm >/dev/null 2>&1; then
  if command -v node >/dev/null 2>&1; then
    relata pendente npm 'o node está instalado sem o npm: instale o npm do mesmo jeito que instalou o node (o preparo não troca o node)'
  fi
elif ! command -v corepack >/dev/null 2>&1; then
  relata pendente corepack 'corepack ausente: sudo npm install -g corepack@<versão fixada> (e rode este script de novo)'
else
  relata igual npm "npm e corepack presentes ($(npm --version 2>/dev/null || echo '?'))"
fi

# 1b. Filtro seccomp do sandbox (sem ele, "sockets are unrestricted")
if [ -z "$SECCOMP_VERSAO" ]; then
  relata aviso seccomp 'sockets sem filtro: o filtro seccomp do sandbox não foi pedido (--seccomp-versao <versão>, decisão do titular); /tmp, /run, /var/run, /mnt/wsl e /mnt/wslg ficam negados no perfil'
elif ! command -v npm >/dev/null 2>&1; then
  relata pendente seccomp 'o filtro seccomp precisa do npm (veja a linha do npm)'
elif [ "$SIMULAR" = 1 ]; then
  relata instalar seccomp "sudo npm install -g --ignore-scripts @anthropic-ai/sandbox-runtime@$SECCOMP_VERSAO (exige administrador do Linux; usa a internet)"
elif (cd / && como_root npm install -g --ignore-scripts "@anthropic-ai/sandbox-runtime@$SECCOMP_VERSAO"); then
  relata criar seccomp "@anthropic-ai/sandbox-runtime@$SECCOMP_VERSAO instalado sem rodar scripts do pacote (o preparo o confere nos caminhos fixos)"
else
  relata erro seccomp "não consegui instalar o filtro; rode: cd / && sudo npm install -g --ignore-scripts @anthropic-ai/sandbox-runtime@$SECCOMP_VERSAO"
fi

# 1c. AppArmor do Ubuntu 24.04 ou mais novo (documentação do sandbox do Claude Code)
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

# 4. O lançador único da 1.7.9 é aposentado (cada projeto tem o seu na 1.7.10)
AVISO_ANTIGO="# fundacao-ia-multiprojetos 1.7.10: lançador aposentado"
if [ -f "$LANCADOR" ] && ! grep -qF "$AVISO_ANTIGO" "$LANCADOR" 2>/dev/null; then
  if [ "$SIMULAR" = 1 ]; then
    relata atualizar lancador-antigo "$LANCADOR (1.7.9) passa a mostrar o comando novo; a cópia fica em $LANCADOR.anterior-<data>"
  elif cp -p "$LANCADOR" "$LANCADOR.anterior-$(date +%Y%m%dT%H%M%S)" &&
       printf '%s\n' '#!/usr/bin/env bash' "$AVISO_ANTIGO" \
         "echo 'Na 1.7.10 cada projeto tem o seu lançador: abrir-fundacao-<projeto> (veja o preparar-wsl.sh).' >&2" \
         'exit 1' >"$LANCADOR.novo" && chmod 0755 "$LANCADOR.novo" && mv -f "$LANCADOR.novo" "$LANCADOR"; then
    relata atualizar lancador-antigo "$LANCADOR aposentado (a cópia do anterior ficou ao lado)"
  else
    relata erro lancador-antigo "não consegui aposentar $LANCADOR"
  fi
fi

# 1d. Relatório do canário (contratos do lote 2, §0): sem ele aprovado, a ficha de nenhum projeto é aplicada. Desde a
# 1.7.10.1, o relatório real que não aprova (false ou null) vai como revogação e substitui o aprovado da mesma versão;
# o preparo dos projetos abaixo segue e fecha as aberturas, salvo no projeto com o aceite de risco do titular para
# esse relatório. Só o arquivo que não é relatório real do ensaio é recusado (código 1, sem os projetos).
if [ -n "$CANARIO" ]; then
  args_canario=(instalar-canario --relatorio "$CANARIO")
  if [ "$ENSAIO" = 1 ]; then args_canario+=(--area-raiz "$AREA_RAIZ"); fi
  if [ "$SIMULAR" = 1 ]; then args_canario+=(--simular); fi
  if [ "$ENSAIO" = 1 ] || [ "$SIMULAR" = 1 ]; then
    saida=$("$PY" -I -B "$AJUDANTE" "${args_canario[@]}"); r=$?
  else
    echo "Instalando o relatório do canário na área do titular (dono root): o sudo vai pedir a sua senha do Linux."
    saida=$(sudo "$PY" -I -B "$AJUDANTE" "${args_canario[@]}"); r=$?
  fi
  if [ "$r" != 0 ]; then
    relata erro canario "o relatório do canário foi recusado (não é o relatório real do ensaio): $saida"
  elif printf '%s' "$saida" | grep -q '"aprovado": false'; then
    relata revogar canario "o relatório real não aprova (false ou null): vai como revogação; o preparo dos projetos abaixo fecha as aberturas, salvo onde houver o seu aceite de risco deste relatório: $saida"
  elif printf '%s' "$saida" | grep -q '"acao": "igual"'; then
    relata igual canario "relatório do canário já na área do titular: $saida"
  else
    relata criar canario "relatório do canário conferido e gravado na área do titular: $saida"
  fi
else
  relata aviso canario 'sem --canario: nenhuma abertura da ficha vale até o titular rodar o ensaio (scripts/ensaio_isolamento_wsl.py) e instalar o relatório'
fi

# 5. Área do titular (dono root) e lançador de cada projeto
if [ -z "$PERFIL_WINDOWS" ]; then
  relata erro perfil-windows 'informe --perfil-windows /mnt/c/Users/<usuario> (o seu usuário do Windows) (a pasta do Windows que o perfil do projeto nega)'
fi
CLAUDE_FONTE="$FIXO"
if [ "$SIMULAR" = 1 ] && [ ! -f "$FIXO" ]; then
  CLAUDE_FONTE="$VERSOES/$CLAUDE_VERSAO"  # na simulação a cópia fixada ainda não existe: o mesmo binário, mesmo hash
fi
if [ "$CLAUDE_OK" = 1 ] && [ "$CODIGO" != 1 ]; then
  for PROJETO in "${PROJETOS[@]}"; do
    args=(instalar-projeto --raiz "$RAIZ" --projeto "$PROJETO" --titular "$TITULAR" --claude "$CLAUDE_FONTE"
          --claude-versao "$CLAUDE_VERSAO" --claude-sha256 "$CLAUDE_HASH" --origem-hash "$ORIGEM_HASH"
          --perfil-windows "$PERFIL_WINDOWS" --casa "$HOME" --usuario "$(id -un)")
    if [ "$ENSAIO" = 1 ]; then
      args+=(--area-raiz "$AREA_RAIZ" --bin "$BIN_DIR")
      [ -z "$TEMP_BASE" ] || args+=(--temp-base "$TEMP_BASE")
      [ -z "$SONDA_CMD" ] || args+=(--sonda-interop-cmd "$SONDA_CMD")
      [ -z "$SONDA_BINFMT" ] || args+=(--sonda-interop-binfmt "$SONDA_BINFMT")
      [ -z "$FERRAMENTA_BASE" ] || args+=(--ferramenta-base "$FERRAMENTA_BASE")
    fi
    if [ "$SIMULAR" = 1 ]; then
      if saida=$("$PY" -I -B "$AJUDANTE" "${args[@]}" --simular); then
        relata instalar "projeto $PROJETO" "área do titular e lançador abrir-fundacao-$PROJETO (sudo: exige administrador do Linux). Plano: $saida"
      else
        relata erro "projeto $PROJETO" "o preparo recusou: $saida"
      fi
      continue
    fi
    if [ "$ENSAIO" = 1 ]; then
      saida=$("$PY" -I -B "$AJUDANTE" "${args[@]}"); r=$?
    else
      echo "Gravando a área do titular do projeto $PROJETO (dono root): o sudo vai pedir a sua senha do Linux."
      saida=$(sudo "$PY" -I -B "$AJUDANTE" "${args[@]}"); r=$?
    fi
    if [ "$r" != 0 ]; then
      relata erro "projeto $PROJETO" "o preparo recusou: $saida"
      continue
    fi
    lanc=$(printf '%s' "$saida" | grep -o '"lancador": "[^"]*"' | head -n 1 | sed 's/.*: "\(.*\)"$/\1/')
    if printf '%s' "$saida" | grep -q '"acao": "\(criar\|atualizar\|remover\|instalar\)"'; then
      relata atualizar "projeto $PROJETO" "área do titular e lançador $lanc conferidos e gravados. Relatório: $saida"
    else
      relata igual "projeto $PROJETO" "área do titular e lançador $lanc (nada mudou)"
    fi
    LANCADORES+=("$lanc")
  done
fi

fim
