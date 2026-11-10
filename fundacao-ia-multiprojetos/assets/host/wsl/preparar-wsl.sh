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
#     integração da 1.7.10, I11). Com --registrar-aninhadas, soma ao registro de negações as skills e os agentes aninhados
#     do projeto (o projeto já registrado com a origem; senão o preparo recusa e mostra o comando do registrar-projeto).
#     Se a ficha aplicada tem skills com scripts (1.7.11, lote S2), o mesmo passo confere as rodas que você baixou contra o
#     requirements.lock e monta a venv SEM rede, de dono root, em /usr/local/lib/fundacao-ia/skills/<p>/<plugin>/<lock>/
#     (o tempo e o disco saem no relatório); o próprio preparo cria a pasta skills/, ao lado da cópia da ferramenta;
#  6. a jaula do Criador (1.7.11, lote L4), só se a ficha aplicada de algum projeto tiver seção navegador ou outras_llm (ou com
#     --preparar-jaula): mostra ANTES o que vai instalar e então, com sudo (preparo_host.py instalar-jaula), cria o usuário de
#     sistema fundacao-jaula, as pastas de estado dele (0700), os programas de dono root em /usr/local/lib/fundacao-ia/jaula/
#     <versão>/ e a sudoers /etc/sudoers.d/fundacao-jaula (conferida com visudo -cf; uma linha por projeto e modo, sem curinga).
#     Com --canario-jaula <resposta> (repita, uma por modo), instala as respostas do canário da jaula e refaz a sudoers, que só
#     abre os modos que o canário aprovou (a resposta tem de ser a que a jaula guardou, byte a byte). A sudoers sai sem senha (NOPASSWD)
#     só com a medida M1 (sudo_na_sessao) aprovada no canário do Ubuntu; senão, ou com --sudo-senha, é a forma com senha. O
#     Codex da SESSÃO (codex-exec) não abre com a conta do ChatGPT; a janela do titular (abrir-codex-<p>) abre. 1.7.11, lote L5: o navegador da
#     jaula (só com a seção navegador na ficha, ou com --preparar-jaula) mostra ANTES cada endereço e tamanho do que baixa (apt
#     da lista fixa e acl, Playwright pelo pip com hashes, Chromium do Playwright) e então, com sudo, o instala em
#     /usr/local/lib/fundacao-ia/jaula/<versão>/navegador/ (dono root, grupo fundacao-jaula, 0750); os pacotes do pip têm
#     SHA-256 fixados no arquivo de travas, e a 1ª instalação registra só o SHA-256 da árvore do Chromium (pins-navegador.json,
#     rotulado "confiança no primeiro uso"). O lançador abrir-navegador-<p> (login e
#     captcha) vem junto com o instalar-jaula, quando o canário aprova a janela. Os downloads são feitos pelo ajudante em
#     Python (preparo_host.py instalar-navegador-jaula), nunca por este script; o ensaio nunca baixa. 1.7.11, lote L6: o Codex
#     (só com a seção outras_llm na ficha, ou com --preparar-jaula) é o passo 6c: mostra ANTES o endereço, o tamanho e o SHA-256
#     fixado em pins-codex.json e então, com sudo, o ajudante (instalar-codex-jaula) baixa o CLI, confere o tamanho e o SHA-256
#     ANTES de instalar (recusa se não baterem) e o instala em /usr/local/lib/fundacao-ia/jaula/<versão>/codex/<versão>/codex
#     (root, 0755). O lançador abrir-codex-<p> (terminal do Codex e --login) vem junto com o instalar-jaula, quando o canário
#     aprova o modo codex-titular.
# O preparo só fixa o que conferiu inteiro [auditoria Codex Security da 1.7.6, #5]. Não instala o Claude Code nem faz
# o login (credencial do titular): se faltar, mostra o comando e para. Honestidade (contratos do lote 2 da 1.7.10, §0):
# com a raiz em /mnt/<x>, o isolamento entre projetos é lógico até o canário passar no ambiente real.
#
# Códigos: 0 pronto (ou simulação sem erro) · 1 parou (veja a linha [erro]) · 2 uso incorreto (também rodado de
#          dentro de <raiz>/projects/) · 3 falta algo que só o titular faz (instalar o Claude Code, fazer o login, o npm
#          ou o corepack) · morto pelo próprio script (137) com funções exportadas ou BASH_ENV no ambiente.

# Revisão de segurança da 1.7.10, CI-F3: o ambiente de quem chama não escolhe os programas deste preparo, que pede o
# sudo. Um ~/.bashrc pode exportar funções (export -f sudo, cd, id, até os embutidos exit, unset e set) ou o BASH_ENV,
# e o bash as importa antes da primeira linha. Com elas no ambiente, o preparo para aqui, só com sintaxe e programas
# por caminho absoluto (função não tem nome com barra), sem rodar nada que venha do ambiente. 1.7.11 (revisão do lote B,
# N2): também SHELLOPTS (xtrace), BASHOPTS e PS4, que o bash importa do ambiente e que fariam o PS4 rodar código do
# usuário a cada linha do script, também depois do primeiro sudo.
case $'\n'"$(/usr/bin/env)" in
  *$'\n'BASH_FUNC_*|*$'\n'BASH_ENV=?*|*$'\n'SHELLOPTS=?*|*$'\n'BASHOPTS=?*|*$'\n'PS4=?*)
    /usr/bin/printf '%s\n' '[erro] este terminal traz funções exportadas (export -f), BASH_ENV, SHELLOPTS, BASHOPTS ou PS4, que trocariam os comandos deste preparo (ele pede o sudo): nada foi feito.' \
      'Rode num terminal sem o perfil do shell, com o comando do modelo da skill (/usr/bin/env -i ... /usr/bin/bash --noprofile --norc <skill>/assets/host/wsl/preparar-wsl.sh ...).' >&2
    /usr/bin/kill -s KILL "$$" ;;
esac
PATH_DE_QUEM_CHAMOU=$PATH  # só o ensaio volta a ele (as ferramentas falsas dos testes, sem sudo no ajudante)
PATH=/usr/sbin:/usr/bin:/sbin:/bin
BASH_ENV= ENV= CDPATH= GLOBIGNORE= LD_PRELOAD= LD_LIBRARY_PATH= LD_AUDIT=
IFS=$' \t\n'
export PATH
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
PREPARAR_JAULA=0
REGISTRAR_ANINHADAS=0
SUDO_SENHA=0
CANARIOS_JAULA=()
CODIGO=0
REINICIAR=0
DISTRO=${WSL_DISTRO_NAME:-Ubuntu}
LANCADORES=()

uso() {
  cat <<'FIM'
Uso: bash preparar-wsl.sh --raiz "/mnt/d/IA/fundacao" --projeto <id> [--projeto <id>]... --titular <id> [--simular]
       [--claude-versao <versão>] [--claude-sha256 <hash do manifesto assinado>] [--perfil-windows /mnt/c/Users/<usuario>]
       [--seccomp-versao <versão>] [--canario <relatório do ensaio>] [--wsl-conf <arquivo>] [--python <python3>]
       [--lancador <lançador antigo>] [--preparar-jaula] [--canario-jaula <resposta do canário de um modo>]...
       [--sudo-senha] [--registrar-aninhadas]
--titular é a sua identidade, a mesma do -Titular do preparar-maquina.ps1: ela assina as decisões que o porteiro
registra. --canario instala o relatório do ensaio real (ensaio_isolamento_wsl.py rodar): sem ele, nenhuma abertura da
ficha vale; reprovado, ele revoga e só vale no projeto com o seu aceite de risco assinado
(fundacao_titular.py aceitar-risco). --preparar-jaula instala a jaula do Criador mesmo sem seção de jaula na ficha (para o
canário); --canario-jaula instala a resposta do canário da jaula de um modo (repita, uma por modo); --sudo-senha é a forma
da sudoers com senha (a sem senha só entra com a medida M1 aprovada no canário do Ubuntu: `sudo -n true` tem de falhar dentro da
sessão; sem ela, a forma com senha vale mesmo sem a opção). --registrar-aninhadas soma
ao registro de negações as skills e os agentes aninhados em projects/<p> (o projeto tem de estar no registro, com a origem).
--simular só mostra o plano
(nada é alterado). Sem --claude-versao, vale a versão para a qual
~/.local/bin/claude aponta. O hash oficial de cada versão está em platforms.linux-x64.checksum do manifesto
https://downloads.claude.ai/claude-code-releases/<versão>/manifest.json, assinado (manifest.json.sig) pela chave de
lançamento da Anthropic, impressão digital 31DD DE24 DDFA B679 F42D 7BD2 BAA9 29FF 1A7E CACE.
Só para ensaio (sem sudo, em pastas temporárias): --area-raiz, --bin, --temp-base, --sonda-interop-cmd,
--sonda-interop-binfmt e --ferramenta-base (a cópia protegida da ferramenta do titular; sem ela, o ensaio não a grava). No
ensaio, as rodas e a venv das skills com scripts vão para <area-raiz>/skills-ensaio, não para /usr/local/lib/fundacao-ia/skills.
FIM
}

while [ $# -gt 0 ]; do
  case "$1" in
    --simular) SIMULAR=1; shift ;;
    --preparar-jaula) PREPARAR_JAULA=1; shift ;;
    --sudo-senha) SUDO_SENHA=1; shift ;;
    --registrar-aninhadas) REGISTRAR_ANINHADAS=1; shift ;;
    -h|--ajuda|--help) uso; exit 0 ;;
    --raiz|--projeto|--titular|--claude-versao|--claude-sha256|--lancador|--wsl-conf|--python|--perfil-windows|--area-raiz|--bin|--temp-base|--sonda-interop-cmd|--sonda-interop-binfmt|--ferramenta-base|--seccomp-versao|--canario|--canario-jaula)
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
        --canario-jaula) CANARIOS_JAULA+=("$2") ;;
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
  PATH=$PATH_DE_QUEM_CHAMOU  # o ensaio não roda o ajudante com sudo; o como_root chama o sudo pelo caminho absoluto
fi

# Revisão de segurança da 1.7.10, CI-F1: este script não roda de dentro de <raiz>/projects/ (uma cópia da skill que a
# sessão guardou ou mostrou num checklist, numa pasta que ela grava): no modo real (que pede o sudo), de projects/ de
# qualquer fundação; na simulação e no ensaio, contra a fundação que o contém. A raiz de fundação é o pai de uma pasta
# projects (sem caixa) que tem registry/; vale o caminho dado e o real.
fundacao_que_contem() {
  local p=$1 nome
  while [ -n "$p" ] && [ "$p" != / ]; do
    nome=${p##*/}
    if [ "${nome,,}" = projects ] && [ -d "${p%/*}/registry" ]; then
      printf '%s' "${p%/*}"
      return 0
    fi
    p=${p%/*}
  done
  return 1
}
FUNDACAO_DO_SCRIPT=$(fundacao_que_contem "$AQUI" || fundacao_que_contem "$(cd "$AQUI" && pwd -P)" || true)
if [ -n "$FUNDACAO_DO_SCRIPT" ]; then
  if { [ "$SIMULAR" = 0 ] && [ "$ENSAIO" = 0 ]; } || [ "$FUNDACAO_DO_SCRIPT" -ef "$RAIZ" ]; then
    printf '%s\n' "[erro] este preparar-wsl.sh fica dentro de $FUNDACAO_DO_SCRIPT/projects/, pasta que as sessões dos projetos gravam: ele não roda daqui (nada foi alterado)." \
      'Rode o da skill instalada, com o comando do modelo da skill (nunca o de uma cópia que a sessão mostrou ou guardou num projeto): /usr/bin/env -i HOME="$HOME" PATH=/usr/bin:/bin /usr/bin/bash --noprofile --norc /mnt/c/Users/<usuario>/.claude/skills/fundacao-ia-multiprojetos/assets/host/wsl/preparar-wsl.sh ... (troque <usuario> pelo seu usuário do Windows)' >&2
    exit 2
  fi
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

como_root() {  # o sudo pede a sua senha do Linux; pelo caminho absoluto (revisão de segurança da 1.7.10, CI-F3)
  if [ "$(id -u)" = "0" ]; then "$@"; else /usr/bin/sudo "$@"; fi
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

# 1d. Relatório do canário (contratos do lote 2, §0): sem ele aprovado, a ficha de nenhum projeto é aplicada.
# Revisão de segurança da 1.7.10: o instalar-canario recalcula a conclusão pelos itens e mostra antes de gravar, como
# root (no stderr, que aparece aqui), o resumo dos itens e o SHA-256 do arquivo (CAN-1). Desde a 1.7.10.1, o relatório
# real que não aprova (false ou null) vai como revogação e substitui o aprovado da mesma versão (CAN-2); o preparo dos
# projetos abaixo segue e fecha as aberturas, salvo no projeto com o aceite de risco do titular para esse relatório.
# Só o arquivo que não é relatório real do ensaio é recusado (código 1, sem os projetos), e com ele o que diz true (confina)
# sem os itens confirmarem, inclusive o de um ensaio anterior (1.7.11, N1): esse não vira revogação.
if [ -n "$CANARIO" ]; then
  args_canario=(instalar-canario --relatorio "$CANARIO")
  if [ "$ENSAIO" = 1 ]; then args_canario+=(--area-raiz "$AREA_RAIZ"); fi
  if [ "$SIMULAR" = 1 ]; then args_canario+=(--simular); fi
  echo "Relatório do canário: confira no resumo abaixo o SHA-256 com o que o rodar do ensaio mostrou ao gravá-lo."
  if [ "$ENSAIO" = 1 ] || [ "$SIMULAR" = 1 ]; then
    saida=$("$PY" -I -B "$AJUDANTE" "${args_canario[@]}"); r=$?
  else
    echo "Instalando o relatório do canário na área do titular (dono root): o sudo vai pedir a sua senha do Linux."
    saida=$(/usr/bin/sudo "$PY" -I -B "$AJUDANTE" "${args_canario[@]}"); r=$?  # CI-F3: o sudo pelo caminho absoluto
  fi
  if [ "$r" != 0 ]; then
    relata erro canario "o relatório do canário foi recusado (não é o relatório real do ensaio desta versão da skill, ou diz que confina sem os itens confirmarem, ou é de um ensaio anterior que se diz aprovado): $saida"
  elif printf '%s' "$saida" | grep -q '"aprovado": false'; then
    relata revogar canario "o relatório real não aprova (conclusão false ou null): vai como revogação; o preparo dos projetos abaixo fecha as aberturas, salvo onde houver o seu aceite de risco deste relatório: $saida"
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
    if [ "$REGISTRAR_ANINHADAS" = 1 ]; then args+=(--registrar-aninhadas); fi
    if [ "$ENSAIO" = 1 ]; then
      args+=(--area-raiz "$AREA_RAIZ" --bin "$BIN_DIR" --jaula-base "$AREA_RAIZ/jaula-ensaio/programas")
      args+=(--skills-base "$AREA_RAIZ/skills-ensaio")
      [ -z "$TEMP_BASE" ] || args+=(--temp-base "$TEMP_BASE")
      [ -z "$SONDA_CMD" ] || args+=(--sonda-interop-cmd "$SONDA_CMD")
      [ -z "$SONDA_BINFMT" ] || args+=(--sonda-interop-binfmt "$SONDA_BINFMT")
      [ -z "$FERRAMENTA_BASE" ] || args+=(--ferramenta-base "$FERRAMENTA_BASE")
    fi
    if [ "$SIMULAR" = 1 ]; then
      if saida=$("$PY" -I -B "$AJUDANTE" "${args[@]}" --simular); then
        relata instalar "projeto $PROJETO" "área do titular e lançador abrir-fundacao-$PROJETO (sudo: exige administrador do Linux; skills com scripts da ficha: rodas conferidas e venv sem rede em /usr/local/lib/fundacao-ia/skills). Plano: $saida"
      else
        relata erro "projeto $PROJETO" "o preparo recusou: $saida"
      fi
      continue
    fi
    if [ "$ENSAIO" = 1 ]; then
      saida=$("$PY" -I -B "$AJUDANTE" "${args[@]}"); r=$?
    else
      echo "Gravando a área do titular do projeto $PROJETO (dono root): o sudo vai pedir a sua senha do Linux."
      saida=$(/usr/bin/sudo "$PY" -I -B "$AJUDANTE" "${args[@]}"); r=$?  # CI-F3: o sudo pelo caminho absoluto
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

# 6. Jaula do Criador (1.7.11, lote L4). Mostra o plano ANTES de instalar. Sem seção de jaula em nenhuma ficha aplicada (e sem
# --preparar-jaula) nada é criado: "igual". Os downloads do navegador (apt, Playwright, Chromium) são do passo 6b abaixo, que os
# mostra, com endereço e tamanho, antes de baixar; o do Codex é o passo 6c (lote L6), com o SHA-256 conferido antes de instalar. A
# sudoers só abre os modos que o canário da jaula aprovou.
if [ "$CLAUDE_OK" = 1 ] && [ "$CODIGO" != 1 ]; then
  args_jaula=(--raiz "$RAIZ" --usuario "$(id -un)")
  for PROJETO in "${PROJETOS[@]}"; do args_jaula+=(--projeto "$PROJETO"); done
  if [ "$SUDO_SENHA" = 1 ]; then args_jaula+=(--sudo-senha); fi
  if [ "$PREPARAR_JAULA" = 1 ]; then args_jaula+=(--preparar-jaula); fi
  args_canario_jaula=()
  for arquivo in "${CANARIOS_JAULA[@]+"${CANARIOS_JAULA[@]}"}"; do args_canario_jaula+=(--relatorio "$arquivo"); done
  if [ "$ENSAIO" = 1 ]; then
    args_jaula+=(--area-raiz "$AREA_RAIZ" --ensaio-base "$AREA_RAIZ/jaula-ensaio")
    args_canario_jaula+=(--area-raiz "$AREA_RAIZ" --ensaio-base "$AREA_RAIZ/jaula-ensaio")
  fi
  # O ajudante da jaula: como o seu usuário no ensaio; com o sudo, pelo caminho absoluto (CI-F3), no real.
  chama_jaula() {
    if [ "$ENSAIO" = 1 ]; then "$PY" -I -B "$AJUDANTE" "$@"; else /usr/bin/sudo "$PY" -I -B "$AJUDANTE" "$@"; fi
  }
  plano_jaula=$("$PY" -I -B "$AJUDANTE" plano-jaula "${args_jaula[@]}" --texto); r=$?
  if [ "$r" = 4 ]; then
    relata igual jaula "$(printf '%s' "$plano_jaula" | tail -n 1 | sed 's/^ *//')"
    if [ ${#CANARIOS_JAULA[@]} -gt 0 ]; then
      relata erro jaula '--canario-jaula sem jaula instalada: a ficha aplicada não tem seção de jaula (ou use --preparar-jaula)'
    fi
  elif [ "$r" != 0 ]; then
    relata erro jaula "o preparo da jaula recusou: $plano_jaula"
  else
    printf '%s\n' "$plano_jaula"
    if [ "$SIMULAR" = 1 ]; then
      relata instalar jaula 'usuário fundacao-jaula, pastas, programas de dono root e sudoers conferida (sudo: exige administrador do Linux; o plano está acima)'
    else
      if [ "$ENSAIO" = 0 ]; then echo "Instalando a jaula (dono root): o sudo vai pedir a sua senha do Linux."; fi
      saida=$(chama_jaula instalar-jaula "${args_jaula[@]}" --texto); r=$?
      if [ "$r" != 0 ]; then
        relata erro jaula "a instalação da jaula parou: $saida"
      else
        printf '%s\n' "$saida"
        if printf '%s' "$saida" | grep -q '^  \[\(criar\|atualizar\|remover\)\]'; then
          relata atualizar jaula 'usuário, pastas, programas de dono root e sudoers da jaula conferidos e gravados (veja acima)'
        else
          relata igual jaula 'nada mudou'
        fi
        if printf '%s' "$saida" | grep -q 'não alcança'; then
          relata pendente jaula-acesso 'o usuário da jaula não alcança a pasta do projeto (veja acima) [medir]'
        fi
        # 6b. O navegador da jaula (lote L5): o plano com endereço e tamanho de cada download vem ANTES; o ensaio nunca baixa.
        plano_nav=$("$PY" -I -B "$AJUDANTE" instalar-navegador-jaula "${args_jaula[@]}" --simular --texto); r=$?
        if [ "$r" != 0 ]; then
          relata erro navegador-jaula "o plano do navegador da jaula foi recusado: $plano_nav"
        elif printf '%s' "$plano_nav" | grep -q 'nada a instalar'; then
          relata igual navegador-jaula 'a ficha não abre navegador (e sem --preparar-jaula): nada a baixar'
        elif [ "$ENSAIO" = 1 ]; then
          printf '%s\n' "$plano_nav"
          relata aviso navegador-jaula 'ensaio: nada é baixado'
        else
          printf '%s\n' "$plano_nav"
          echo "Baixando o navegador da jaula (dono root): o sudo vai pedir a sua senha do Linux."
          saida=$(chama_jaula instalar-navegador-jaula "${args_jaula[@]}" --texto); r=$?
          if [ "$r" != 0 ]; then
            relata erro navegador-jaula "a instalação do navegador da jaula parou: $saida"
          else
            printf '%s\n' "$saida"
            relata criar navegador-jaula 'apt, Playwright (com hashes) e Chromium conferidos e instalados (veja acima)'
          fi
        fi
        # 6c. O Codex da jaula (lote L6): o plano com endereço, tamanho e SHA-256 vem ANTES; o ensaio nunca baixa. O download e a
        # conferência do tamanho e do SHA-256 (antes de instalar; recusa se não baterem) são do ajudante em Python.
        plano_cdx=$("$PY" -I -B "$AJUDANTE" instalar-codex-jaula "${args_jaula[@]}" --simular --texto); r=$?
        if [ "$r" != 0 ]; then
          relata erro codex-jaula "o plano do Codex da jaula foi recusado: $plano_cdx"
        elif printf '%s' "$plano_cdx" | grep -q 'nada a instalar'; then
          relata igual codex-jaula 'a ficha não abre o Codex (e sem --preparar-jaula): nada a baixar'
        elif [ "$ENSAIO" = 1 ]; then
          printf '%s\n' "$plano_cdx"
          relata aviso codex-jaula 'ensaio: nada é baixado'
        else
          printf '%s\n' "$plano_cdx"
          echo "Instalando o Codex da jaula (dono root; só baixa se ainda não estiver instalado igual): o sudo vai pedir a sua senha do Linux."
          saida=$(chama_jaula instalar-codex-jaula "${args_jaula[@]}" --texto); r=$?
          if [ "$r" != 0 ]; then
            relata erro codex-jaula "a instalação do Codex da jaula parou: $saida"
          else
            printf '%s\n' "$saida"
            if printf '%s' "$saida" | grep -q '^  \[\(criar\|atualizar\)\]'; then
              relata criar codex-jaula 'Codex fixado baixado, com tamanho e SHA-256 conferidos antes de instalar (veja acima)'
            else
              relata igual codex-jaula 'o Codex fixado já estava instalado igual: nada foi baixado'
            fi
          fi
        fi
        if [ ${#CANARIOS_JAULA[@]} -gt 0 ]; then
          saida=$(chama_jaula instalar-canario-jaula "${args_canario_jaula[@]}" --texto); r=$?
          if [ "$r" != 0 ]; then
            relata erro canario-jaula "a resposta do canário da jaula foi recusada: $saida"
          else
            printf '%s\n' "$saida"
            relata criar canario-jaula 'respostas do canário da jaula conferidas e gravadas; a sudoers é refeita a seguir'
            saida=$(chama_jaula instalar-jaula "${args_jaula[@]}" --texto); r=$?
            if [ "$r" != 0 ]; then relata erro jaula "refazer a sudoers parou: $saida"; else printf '%s\n' "$saida"; fi
          fi
        fi
      fi
    fi
  fi
else
  relata aviso jaula 'não verificada: o preparo dos projetos acima não terminou'
fi

fim
