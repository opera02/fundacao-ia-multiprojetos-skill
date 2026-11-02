#!/usr/bin/env python3
"""Hook PreToolUse (Bash/PowerShell) para o regime de DADOS REAIS: nega comandos do executor
que definam ou troquem a identidade da fundação (`FUNDACAO_PRINCIPAL`) e, desde a 1.7.10, os que
citem caminho de outro projeto ou percorram todos eles.

Por quê: no kit, a identidade das operações vem da variável `FUNDACAO_PRINCIPAL`. Se o
executor puder redefini-la, qualquer identidade registrada (administrador, revisor,
curador) fica ao alcance dele, e "quem prepara não aprova" vira obediência, não barreira.
Neste regime, o lançador humano define a variável ANTES de iniciar a sessão (perfil do
terminal, atalho ou serviço) e este hook barra a alteração explícita pela sessão (ver Limite).

Exceção explícita: FUNDACAO_PERMITIR_TROCA_IDENTIDADE=1 no ambiente do lançador (laboratório);
ela vale só para a identidade, não para o caminho de outro projeto.
Contrato de saída igual ao de guarda_caminho.py; falha fechada em evento ilegível, vazio ou sem
`tool_name` (contratos do lote 2 da 1.7.10, §7). Entrada lida em bytes UTF-8 (com `-I` o Python
ignora PYTHONUTF8). Matcher recomendado: `Bash|PowerShell`, com `python3 -I -B` (Windows: `python -I -B`).
Limite: é um guarda-corpo para o caminho comum (atribuição explícita da variável). Passam por
ele, por exemplo, o nome da variável montado em tempo de execução, `python -c` que altere
`os.environ`, a chamada direta da API do kit e, com `state/` gravável pela mesma conta do SO, a
escrita direta no SQLite — por isso ampliar estes padrões não o torna barreira (revisão de
segurança da 1.4.5, #4). Não substitui conta do SO separada nem aprovação com credencial fora
do alcance do executor (desenho em references/seguranca-isolamento.md §2).
Formas cobertas: `$env:X = …`, `${env:X} = …`, `+=`; Set-Item/Set-Content/New-Item/Remove-Item/
Clear-Item sobre `env:X` (caminho com ou sem aspas, `-Path:`/`-Path=`, `Env:\\`, `-Name`, outros
parâmetros antes); `[Environment]::SetEnvironmentVariable`; set/setx/export/unset e `X=valor comando`
(conferência da 1.4.3, CF-01). Leitura e comparação (`echo`, `Get-ChildItem`, `-eq`, `==`) seguem.

Caminho de outro projeto (1.7.10; contratos do lote 2, §7; guarda-corpo, não barreira): nega o
comando que cite `projects/<x>` ou `projects\\<x>` (sem caixa, em qualquer ponto do argumento,
inclusive depois de espaço, aspa, crase, `@` ou `;|&<>`: o comando dentro de outro, como
`bash -c "..."`, `eval`, `python -c`, `Invoke-Expression` e `curl -d @arquivo`; revisão do lote 2; também
`projects.\\<x>`, que o Windows lê como `projects\\<x>`: revisão 2 da rodada 4)
com x diferente de FUNDACAO_PROJECT — sem projeto válido, qualquer x; nome com curinga, chave ou
variável (`*`, `{a,b}`, `$P`) também conta como outro. Nega ainda `..` depois do próprio projeto no
mesmo argumento (`projects/<p>/../<x>`), palavra relativa com `..` em qualquer ponto que, a partir
da pasta atual dentro de `projects/<p>`, caia em outro projeto (`../<x>/...`, `minutas/../../<x>/...` e, desde a
revisão 2 da rodada 4, `~+/../<x>`, `$PWD/../<x>` e, no PowerShell, cada item de uma lista com vírgula),
a palavra com curinga em qualquer componente que possa cair em outro projeto (`<raiz>/*/<x>`, `*/<x>`
e `*/*/` na raiz, `../../*/*`, `proj[e]cts/<x>`; revisão 1 da rodada 4; a chave conta só com vírgula no próprio
nível, expandida como o bash, ou vazia, como o `{}` do `xargs`; o extglob `@(...)`, `!(...)`... casa qualquer nome e,
fora de aspas, faz parte da palavra; revisão 2 da rodada 4) e todo comando com o `cwd` em
`<raiz>/projects/` ou dentro de outro projeto (ali todo caminho relativo, até o implícito de `rg senha`,
cai fora do projeto), salvo `cd <destino>` para fora deles. Não contam: o trecho que é a própria raiz
(FUNDACAO_RAIZ; sem ela, a pasta da instalação do hook e CLAUDE_PROJECT_DIR, cada uma subindo para a
pasta de cima do último `projects`: a pasta de um projeto não vira raiz, e a raiz pode ficar numa pasta
`projects`; veja `_raizes`), uma pasta `projects/` dentro do próprio projeto citada pelo caminho dele, e
URL http(s) na mesma palavra.
Árvore inteira (revisão de segurança da 1.7.10, HOOK-F3): nega o comando conhecido que percorre
pastas — `grep -r`, `rg`, `ag`, `ack`, `fd`, `find` (e o comando do `-exec`), `ls -R`, `tree`, `du`,
`diff -r`, `git diff --no-index`, `cp -r`, `scp -r`, `rm -r`, `chmod -R`, `mv`, `tar`, `zip`, `7z`,
`rsync`, `robocopy`, `xcopy`, `git grep`, `findstr /s`, `dir /s`, `Get-ChildItem -Recurse` (`gci -r`,
`ls -r` no PowerShell), `Copy-Item`/`Remove-Item -Recurse`, `Compress-Archive`; também depois de
`sudo`, `env`, `xargs`, `timeout`... e dentro de `bash -c`, `sh -c`, `eval`, `powershell -Command` e
`cmd /c` — cujo alvo (explícito, por `..` ou `~`; o curinga casado com o nome; sem alvo, a pasta atual;
no PowerShell, depois de `|`, as pastas que o comando anterior manda pelo cano) seja `projects/` sem
nome de projeto (com ou sem barra, fora do caminho do próprio projeto e do da raiz: conta como todos os
projetos), a raiz, uma pasta acima dela (`/`, `/mnt`, a unidade) ou outro projeto (`tar -C .. <x>`,
`<raiz>/*/<x>`); e o `cd` para `projects/`. Não nega (revisão 1 da rodada 4): a busca na raiz com a poda
dos modelos de auditoria e revisão (`find <raiz> -type d \\( -name projects -o -name state \\) -prune -o
...`, `grep -r --exclude-dir=projects --exclude-dir=state`, `Get-ChildItem -LiteralPath <raiz> |
Where-Object Name -notin 'projects','state' | Get-ChildItem -Recurse`), só com o alvo na própria raiz,
e a descida que não chega ao conteúdo de um projeto (`find .. -maxdepth 1`, `Get-ChildItem -Depth 1` na
raiz, `tree -L 1 ..`: lista de nomes, como `ls ..`; com `-exec`, um nível a menos).
Opções lidas como o programa as lê (revisão 2 da rodada 4): a opção longa pelo começo do nome (`--recur`,
`--arch`, `--dir=rec` do grep, `tar --dir=..`), o dígito no grupo de letras (`ls -1R`, `grep -2r`), a tabela de
opções longas que levam valor por programa (`grep --group-separator x`, `rg --color never`; o `--context` do `ls`
e do `cp` e o `--time` do `du` não tomam a palavra seguinte, o `--time` do `ls` toma) — a opção longa fora da
tabela, sem `=`, deixa a palavra seguinte como caminho e confere também a pasta atual —; no Get-ChildItem, `-s` (o
apelido do `-Recurse`), os parâmetros comuns com valor (`-ErrorAction`, `-ea`, `-OutVariable`...) e todos os
caminhos posicionais; `git diff` com caminhos (o `-C` é só a base dos caminhos; no `git grep` o `-C <pasta>` é alvo;
revisão 3 da rodada 4); o comando do `-exec` com o `{}` trocado pelo TEXTO do ponto de partida como foi escrito (`.`,
`..`, `minutas`; revisão 3 da rodada 4: nunca o irmão absoluto do projeto, porque o `{}` do find é sempre um caminho a
partir do ponto de partida), no `-execdir` `./` mais o último nome dele e rodando também na pasta de cima; sem o
desconto da profundidade nem a poda, que ele não respeita; `env -S '...'` (o texto vira o
comando), `env -C`/`sudo -D`/`pwsh -wd`/`Start-Process -WorkingDirectory` (o comando roda na pasta dada, conferida
como a do `cd`) e o `-ArgumentList '-c','...'` do Start-Process (cada item da lista com vírgula).
A pasta acompanha o `cd` (também `pushd`/`popd`, `Push-Location`/`Pop-Location`, o `cd` dentro de
`eval` e de `Invoke-Expression`, e o redirecionamento no meio, `cd 2>/dev/null X`): depois de `cd X &&`,
vale X; depois de `cd X;`, X e a de antes (o cd pode falhar); numa lista com `&&` e `||`, cada elo roda
nas pastas do sucesso ou da falha do anterior (`!` troca as duas); o destino que não se sabe (`$X`,
`$(...)`, `cd -`, `~-`) deixa a de antes e uma desconhecida; a lista em segundo plano (`&`) não a muda.
No Bash, `|`, parêntese, `$(...)` e crase devolvem a de antes; no PowerShell a pasta é da sessão, e `|`,
parêntese e chave não a devolvem. Revisão 2 da rodada 4: `pushd -n X` só empilha X (o `popd` seguinte vai a
ela) e `popd -n` não muda a pasta; depois de uma função ou alias com o nome `cd`, `pushd`, `popd` ou `chdir`
(`cd() {...}`, `function cd`, `alias cd=...`, `Set-Alias`), todo `cd` pode ir ao destino dado (a função pode chamar
o `builtin cd`), ficar na de antes ou ir a uma desconhecida; o texto dado pela
entrada a um lançador (`bash <<< '...'`, `echo '...' | sh`, `'...' | iex`) é analisado como comando, e o de
`. /dev/stdin <<< '...'` roda no shell atual (o `cd` de dentro vale depois); mais de 8 pastas possíveis (de `cd X;`
relativo depois de `;`, de `-execdir` com muitos pontos de partida ou de `cd` redefinido) nega, com motivo neutro e a
saída de cada ferramenta (revisão 3 da rodada 4), em vez de descartar alguma. Revisão 3 da rodada 4: o corpo de um
here-doc (`<<EOF`, `<<-EOF`) é dado que entra pela entrada padrão, lido como comando só por um lançador (`bash <<EOF`;
antes, o JSON minificado no corpo de `cat`/`python` negava); com o delimitador sem aspas, as substituições de comando
do corpo (`$(...)`, a crase) ainda são reanalisadas.
Leitura do comando (HOOK-F4 e o resíduo dele, revisão 1 da rodada 4): no Bash, fora de aspas, a barra
invertida escapa qualquer caractere e, com a quebra de linha, some, como o bash lê; `$'...'` tem os
escapes resolvidos (`\\x2e`, `\\160`), `$"..."` vale como aspas e `{a,b}` fora de aspas é expandido (até
64 por palavra; a expansão vazia some, `{cd,} ..` é `cd ..`: revisão 2 da rodada 4); a leitura antiga (a barra de
caminho do Windows fica) também é conferida, e basta uma das duas citar. A substituição de comando entre aspas
duplas (`"$(...)"`, a crase) é reanalisada; no `cmd /c`, o `^` também escapa. Revisão 2 da rodada 4: o comentário
some como o shell o lê — `#` no começo da palavra até a quebra de linha (também dentro de `$(...)`); no
PowerShell, também depois de aspas, e `<# ... #>` —, e o extglob fora de aspas (`@(...)`, `!(...)`) fica na
palavra, com o texto de dentro reanalisado (sem extglob, `!(...)` é um subshell negado).
Prazo (HOOK-F5): comando acima de 16 KiB nega; abaixo, um orçamento único para a decisão inteira (revisão 2 da
rodada 4) — o texto analisado em cada nível, as expansões de chave e cada conferência a partir de cada pasta
possível, até 8 vezes o teto — limita a conta, também com `eval` aninhado sobre o texto já expandido (antes, 3,7 KB
de `eval eval eval {a,b}...` levavam 7 s); acima dele, nega. Aninhamento de até 3 níveis (`bash -c`, `eval`,
`$(...)`, `find -exec`) e até 64 expansões de chave por palavra. Se ainda assim o prazo do perfil (10 s) estourar,
o perfil tem `onFailure: block` e o host nega o comando (visto na revisão 1 da rodada 4: "timed out; blocking
because onFailure is block").
Falsos positivos declarados: pasta `projects/` do próprio projeto citada de forma relativa
(`src/projects/x`) ou depois de um espaço no caminho dele, busca recursiva numa pasta chamada
`projects` fora da fundação (`~/projects`), texto que cite `projects/<outro>`, como a mensagem de
commit (use `git commit -F <arquivo>`), curinga que pode casar `projects/<x>` a partir da raiz
(`*/*.md`, `[a-z]*/x`, `?*/x`, e o texto com mais de 64 expansões de chave num componente, como uma lista JSON de
objetos entre aspas), a busca na raiz com uma poda diferente da dos modelos, `rg` e `ag`
sem caminho depois de `|` (buscam no que chega pelo cano; contam como a pasta atual), no PowerShell, o
percurso recursivo sem caminho depois de `|` de um comando que o guarda não acompanha, a opção longa que o guarda
não conhece no comando que percorre a pasta atual (conta também a pasta atual) e `cd X || exit; ...`, que fica
com a pasta de antes e a de X (use `cd X && ...`; revisão 2 da rodada 4); no mais, cite
pelo caminho do projeto ou use a ferramenta Read.
Limite (honestidade, §0 dos contratos): o shell monta o caminho em tempo de execução (variável,
aspas no meio do nome dentro de outro comando, nome curto do Windows, ligação), a pasta depois de um
`cd` para destino que não se sabe (variável, `$(...)`, `Join-Path`, CDPATH) ou mais funda que 128 níveis
não se acompanha, o que o `xargs` recebe pelo cano não se confere, o texto que um comando gera para outro rodar
(`eval "$(...)"`, `. <(...)`, `bash < <(...)`, `bash < script`) não se confere, e programa que percorre pastas fora da
lista (um script, `python -c`) passa; a barreira é o sandbox onde ele confina — com a raiz em /mnt/e, o
sandbox não confinou os comandos nas sondas de 31/10/2026, e no Windows o shell lê tudo.
"""

from __future__ import annotations

import bisect
import fnmatch
import json
import os
import posixpath
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
    # (a API .NET, `SetEnvironmentVariable(... FUNDACAO_PRINCIPAL`, é conferida à parte, em _api_dotnet: a forma
    # `\([^)]*` relia o resto do comando a cada ocorrência; revisão 1 da rodada 4, HOOK-F5)
    # cmd e Bash: set/setx/export/unset, com ou sem aspas em volta de NOME=valor
    r"|(?:^|[\s;&|(])(?:set|setx|export|unset)\s+[\"']?FUNDACAO_PRINCIPAL"
    # cmdlets do PowerShell sobre o drive env:: parâmetros antes (com valor ou não; `-Par:`/`-Par=`), caminho com
    # aspas opcionais, `Env:\`, e a forma `New-Item -Path env: -Name X`. Até 40 parâmetros antes (um cmdlet tem menos
    # de 30 distintos, e repetido não liga): sem o teto, `Set-Item -a Set-Item -a ...` custava o quadrado do tamanho
    # (revisão de segurança da 1.7.10, HOOK-F5). Cada parâmetro tem uma leitura só — separador `:`/`=` colado ou
    # espaço, e o valor nunca começa com `-` —: o `[\s:=]+` de antes lia `-a =` de dois jeitos, e `Set-Item -a = -a =
    # ...` custava 2^n (revisão 1 da rodada 4, HOOK-F5).
    r"|(?:Set-Item|Set-Content|New-Item|Remove-Item|Clear-Item)\s+"
    r"(?:-\w+(?:[:=]\s*|\s+)(?:(?:\"[^\"]*\"|'[^']*'|[^-\s\"'][^\s]*)\s+)?){0,40}"
    r"[\"']?env:[\\/]?(?:[\"']?\s+-Name[\s:=]+)?[\"']?FUNDACAO_PRINCIPAL",
    re.IGNORECASE)
PRINCIPAL = re.compile("FUNDACAO_PRINCIPAL", re.IGNORECASE)  # sem o nome, o PADRAO não casa: a busca linear vem antes
API_DOTNET = re.compile(r"SetEnvironmentVariable\(", re.IGNORECASE)

# 1.7.10: `projects` como componente de caminho dentro de um argumento (início, separador, `=`, `:`, `,`, `{`, `(` e,
# desde a revisão do lote 2, espaço, aspa, crase, `@`, `;`, `|`, `&`, `<` e `>`: o comando dentro de outro), seguido de
# separador(es) e de `./` opcionais; o nome vai até o próximo separador, espaço, aspa, crase ou `;|&<>`. Revisão 2 da
# rodada 4: ponto e espaço depois de `projects` (`projects.\x`), que o Windows tira do nome, como no guarda_leitura.
CITACAO = re.compile(r"(?:^|(?<=[\s\\/=:,{(\"'`@;|&<>]))projects[ .]*[\\/]+(?:\.[\\/]+)*([^\\/\s\"'`;|&<>]*)",
                     re.IGNORECASE)
FIM_DO_CAMINHO = re.compile(r"[,=:;{}()|&<>\s\"'`]")  # onde termina o caminho do próprio projeto dentro do argumento
PALAVRA = re.compile(r"[\s\"'`;|&<>]")  # o que separa as palavras de um comando dentro de outro (`bash -c "..."`)
SAIDAS = {"cd", "chdir", "pushd", "set-location", "sl", "push-location"}  # mudam a pasta (o único comando que segue com
                                                                           # a pasta atual proibida)
VOLTAS = {"popd", "pop-location"}  # voltam à pasta que o pushd guardou (revisão 1 da rodada 4)
EMPILHAM = {"pushd", "push-location"}
SEPARADORES = re.compile(r"[\\/]+")
BARRA = re.compile(r"[\\/]")
COMPONENTE = re.compile(r"[^\\/]+")
URL_DE_REDE = re.compile(r"https?://", re.IGNORECASE)
NOME_SIMPLES = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?\Z")
UNIDADE = re.compile(r"/+mnt/([a-z])(?=/|\Z)|([a-z]):(?=/|\Z)", re.IGNORECASE)
BASH_DO_WINDOWS = re.compile(r"/(?:cygdrive/)?([a-z])(?=/|\Z)", re.IGNORECASE)
TETO_COMANDO = 16 * 1024  # revisão de segurança da 1.7.10, HOOK-F5: acima disso nega, longe do prazo do perfil (10 s)
ORCAMENTO = 8 * TETO_COMANDO  # revisão 2 da rodada 4 (HOOK-F5): o trabalho da decisão inteira (_Contexto.gastar)
LIMITE_PASTAS = 8  # revisão 2 da rodada 4 (HOOK-F3): pastas possíveis acompanhadas; acima, nega (não descarta)
TODOS = "todos os projetos"
ANINHADO = "comando aninhado demais (mais de 3 níveis de bash -c, eval, $(...), find -exec, powershell -Command...)"
_SEM_CD = object()  # o comando simples não muda a pasta
DESCONHECIDA = object()  # o que vem pelo cano (PowerShell) não se sabe

# Revisão de segurança da 1.7.10, HOOK-F3: comandos que percorrem a árvore. nome: (letras curtas que o tornam
# recursivo, "" se sempre percorre; letras curtas que levam valor; o 1º operando é um padrão; sem caminho, percorre a
# pasta atual).
_GREP, _SEMPRE, _COM_OPCAO = ("rR", "efmABCdD", True, True), ("", "", False, False), ("R", "", False, False)
PERCORRE = {**dict.fromkeys(("grep", "egrep", "fgrep"), _GREP), "rgrep": ("", "efmABCdD", True, True),
            "rg": ("", "efgtTmABCjMrE", True, True), "tree": ("", "LPIoHT", False, True),
            "du": ("", "BdtX", False, True), "diff": ("r", "CUDFILSxX", False, False),  # diff -r: revisão 1, rodada 4
            **dict.fromkeys(("ag", "ack", "ack-grep", "pt", "sift"), ("", "ABCGgmpW", True, True)),
            **dict.fromkeys(("fd", "fdfind"), ("", "edtEcjxXS", True, True)),
            **dict.fromkeys(("ls", "dir", "vdir", "get-childitem", "gci"), ("R", "IwT", False, True)),
            "cp": ("rRa", "St", False, False), "scp": ("r", "cFiJlmoPS", False, False), "rm": ("rR", "", False, False),
            "findstr": ("R", "", True, False),
            **dict.fromkeys(("copy-item", "cpi", "copy", "remove-item", "ri", "del", "erase", "rmdir", "rd", "chmod",
                             "chown", "chgrp"), _COM_OPCAO),
            **dict.fromkeys(("mv", "move", "move-item", "mi", "tar", "bsdtar", "zip", "7z", "7za", "7zr", "rsync",
                             "robocopy", "xcopy", "compress-archive"), _SEMPRE)}
SO_POWERSHELL = {"get-childitem", "gci", "copy-item", "cpi", "remove-item", "ri", "move-item", "mi", "compress-archive"}
SO_WINDOWS = {"rd", "del", "erase", "findstr", "xcopy", "robocopy"}  # programas do Windows: `/x` é sempre chave
DO_CMD = SO_WINDOWS | {"dir", "rmdir", "tree"}  # aceitam chaves `/x` do Windows (os três também existem no Bash)
CURINGA_PROPRIO = DO_CMD | SO_POWERSHELL | {"7z", "7za", "7zr"}  # o curinga é do programa, que desce da pasta dele
ENVOLTORIOS = {"sudo", "doas", "env", "nice", "ionice", "nohup", "time", "timeout", "command", "builtin", "exec",
               "xargs", "stdbuf", "unbuffer", "watch", "busybox", "setsid", "chronic", "strace", "ltrace", "wsl",
               "start", "start-process", "saps", "if", "then", "else", "elif", "do", "while", "until", "!", "{", "}",
               ".", "call"}
# Revisão 1 da rodada 4: envoltório cujas opções que levam valor são só estas letras — o comando é a primeira palavra
# que não é opção dele (`time echo ls -R /` é o `echo`); nos demais (`sudo -u x`, `timeout 10`, `xargs -I {}`...), o
# primeiro nome conhecido, como antes.
SIMPLES = {"time": "fo", "nohup": "", "setsid": "", "chronic": "", "command": "", "builtin": "", "exec": "a",
           "nice": "n", "stdbuf": "ioe", "unbuffer": "", "if": "", "then": "", "else": "", "elif": "", "do": "",
           "while": "", "until": "", "!": "", "{": "", "}": "", "call": ""}
LANCADORES = {"bash", "sh", "zsh", "dash", "ksh", "mksh", "fish", "eval", "su", "runuser"}  # o texto é lido como Bash
LANCADORES_PS = {"powershell", "pwsh", "cmd", "iex", "invoke-expression"}  # o texto é lido como PowerShell (ou cmd)
NO_SHELL_ATUAL = {"eval", "iex", "invoke-expression"}  # rodam no shell atual: o `cd` de dentro vale depois
CONHECIDOS = set(PERCORRE) | SAIDAS | VOLTAS | LANCADORES | LANCADORES_PS | {"git", "find"}
GREPS = {"grep", "egrep", "fgrep", "rgrep"}
RECURSIVAS_LONGAS = ("recursive", "dereference-recursive", "archive")  # pelo começo do nome (revisão 2 da rodada 4)
REDEFINIVEIS = SAIDAS | VOLTAS  # função ou alias com esse nome: o destino do cd não se sabe (revisão 2 da rodada 4)
ENTRADA_PADRAO = {"/dev/stdin", "/dev/fd/0", "/proc/self/fd/0"}  # `. /dev/stdin <<< '...'` roda o texto no shell atual


def _tabela(valor: str, sem: str = "", caminho: str = "") -> dict:
    return {**dict.fromkeys(sem.split(), "s"), **dict.fromkeys(valor.split(), "v"),
            **dict.fromkeys(caminho.split(), "c")}


# Revisão 2 da rodada 4 (HOOK-F3): opções longas por programa — "v" leva valor na palavra seguinte (sem `=`), "c" é um
# caminho (conferido como alvo), "s" não leva valor (ou só com `=`); o nome vale pelo começo, como no getopt_long
# (_longa). A opção fora da tabela, sem `=`, deixa a palavra seguinte como operando e, no comando que sem caminho
# percorre a pasta atual, faz conferir também a pasta atual (antes, uma tabela única: o `--context` do `ls` e do `cp`
# e o `--time` do `du` tomavam o caminho como valor, e `grep --group-separator x` e `rg --color never` davam o padrão
# como caminho; o `--time` do `ls` toma o valor, como no ls 9.4).
_LONGAS_GREP = _tabela("after-context before-context binary-files context devices directories exclude exclude-dir "
                       "exclude-from file group-separator include label max-count regexp",
                       "basic-regexp binary byte-offset color colour count dereference-recursive extended-regexp "
                       "files-with-matches files-without-match fixed-strings help ignore-case initial-tab invert-match "
                       "line-buffered line-number line-regexp no-filename no-group-separator no-ignore-case "
                       "no-messages null null-data only-matching perl-regexp quiet recursive silent text version "
                       "with-filename word-regexp")
LONGAS = {
    **dict.fromkeys(GREPS, _LONGAS_GREP),
    "rg": _tabela("after-context before-context color colors context context-separator dfa-size-limit encoding engine "
                  "field-context-separator field-match-separator file generate glob hostname-bin hyperlink-format "
                  "iglob ignore-file max-columns max-count max-depth max-filesize maxdepth path-separator pre pre-glob "
                  "regex-size-limit regexp replace sort sortr threads type type-add type-clear type-not",
                  "binary block-buffered byte-offset case-sensitive column count count-matches crlf debug files "
                  "files-with-matches files-without-match fixed-strings follow glob-case-insensitive heading help "
                  "hidden ignore-case ignore-file-case-insensitive include-zero invert-match json line-buffered "
                  "line-number line-regexp max-columns-preview mmap multiline multiline-dotall no-config no-filename "
                  "no-heading no-hidden no-ignore no-ignore-dot no-ignore-exclude no-ignore-files no-ignore-global "
                  "no-ignore-messages no-ignore-parent no-ignore-vcs no-line-number no-messages no-mmap "
                  "no-require-git no-unicode null null-data one-file-system only-matching passthru pcre2 pretty quiet "
                  "search-zip smart-case sort-files stats text trim type-list unrestricted version vimgrep "
                  "with-filename word-regexp"),
    **dict.fromkeys(("ag", "ack", "ack-grep", "pt", "sift"), _tabela(
        "after after-context before before-context context depth file-search-regex ignore ignore-dir ignore-file match "
        "max-count output pager path-to-ignore type workers",
        "all-types color count files-with-matches files-without-matches follow heading help hidden ignore-case "
        "literal no-heading nocolor smart-case unrestricted version word-regexp")),
    **dict.fromkeys(("fd", "fdfind"), _tabela(
        "and batch-size changed-before changed-within color exact-depth exclude exec exec-batch extension format "
        "ignore-file max-depth max-results min-depth owner path-separator size threads type",
        "absolute-path case-sensitive fixed-strings follow full-path glob help hidden ignore-case list-details "
        "no-ignore no-ignore-vcs one-file-system print0 prune regex show-errors unrestricted version",
        "base-directory search-path")),
    **dict.fromkeys(("ls", "dir", "vdir"), _tabela(
        "block-size format hide ignore indicator-style quoting-style sort tabsize time time-style width",
        "all almost-all author classify color context dereference dereference-command-line directory dired escape "
        "file-type full-time group-directories-first help hide-control-chars human-readable hyperlink ignore-backups "
        "inode kibibytes literal no-group numeric-uid-gid quote-name recursive reverse show-control-chars si size "
        "version zero")),
    "du": _tabela("block-size exclude exclude-from files0-from max-depth threshold time-style",
                  "all apparent-size bytes count-links dereference dereference-args help human-readable inodes "
                  "no-dereference null one-file-system separate-dirs si summarize time total version"),
    "tree": _tabela("charset filelimit gitfile hintro houtro infofile sort timefmt",
                    "device dirsfirst du filesfirst fromfile fromtabfile gitignore help ignore-case info inodes "
                    "matchdirs metafirst noreport nolinks prune si version"),
    "cp": _tabela("no-preserve sparse suffix", caminho="target-directory"),
    "mv": _tabela("suffix", caminho="target-directory"),
    "diff": _tabela("changed-group-format exclude exclude-from horizon-lines ignore-matching-lines label line-format "
                    "new-group-format new-line-format old-group-format old-line-format palette show-function-line "
                    "starting-file tabsize unchanged-group-format unchanged-line-format width",
                    caminho="from-file to-file"),
    "rsync": _tabela("backup-dir block-size bwlimit chmod chown compare-dest compress-choice compress-level contimeout "
                     "copy-dest exclude exclude-from filter groupmap iconv include include-from info link-dest "
                     "log-file max-delete max-size min-size modify-window out-format partial-dir password-file port "
                     "protocol remote-option rsh rsync-path skip-compress sockopts suffix temp-dir timeout usermap",
                     caminho="files-from"),
    "git": _tabela("after-context before-context context file max-count max-depth regexp threads"),
}
LONGAS_PADRAO = _tabela("exclude exclude-from from include include-from reference suffix",
                        caminho="files-from target-directory")
PS_DE_CAMINHO = ("path", "literalpath", "pspath", "destination", "destinationpath")
# Revisão 2 da rodada 4 (HOOK-F3): os parâmetros comuns com valor (`-ErrorAction SilentlyContinue`, `-ea 0`...) — antes
# o valor virava o caminho, e o caminho real sumia; os apelidos valem só inteiros.
PS_COM_VALOR = ("filter", "include", "exclude", "depth", "attributes", "encoding", "compressionlevel", "erroraction",
                "warningaction", "informationaction", "progressaction", "errorvariable", "warningvariable",
                "informationvariable", "outvariable", "outbuffer", "pipelinevariable")
PS_COM_VALOR_EXATO = {"ea", "wa", "infa", "proga", "ev", "wv", "iv", "ov", "ob", "pv"}
PS_OPCOES_COM_VALOR = {"-executionpolicy", "-ep", "-windowstyle", "-inputformat", "-outputformat", "-workingdirectory",
                       "-wd"}
CHAVE_CMD = re.compile(r"(?:/[A-Za-z?]+(?::[^/]*)?)+\Z")  # `/s`, `/s/b`, `/c:texto`, `/d:a;b`
UMA_CHAVE = re.compile(r"/([A-Za-z?]+)(?::([^/]*))?")
PREFIXO = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=|(?:\$[\w:{}]+|[+\-*/]?=|\[[\w.\[\]]+\])\Z")
CASA = re.compile(r"(?:~|\$HOME|\$\{HOME\}|\$env:(?:HOME|USERPROFILE)|%USERPROFILE%)(?=[\\/]|\Z)", re.IGNORECASE)
PASTA_DA_VEZ = re.compile(r"(?:\$PWD|\$\{PWD\}|~\+)(?=[\\/]|\Z)", re.IGNORECASE)
DISPOSITIVO = re.compile(r"(?://[?.]/|/\?\?/)(?=[a-z]:(?:/|\Z))", re.IGNORECASE)
CURINGA = re.compile(r"[*?\[{]")
# Revisão 1 da rodada 4 (HOOK-F3 e o resíduo do HOOK-F4): o curinga de um componente (do shell ou do programa), que pode
# casar `projects` ou o nome de outro projeto; a sequência `{1..3}` só dá números ou uma letra. Revisão 2 da rodada 4: a
# chave conta só com vírgula no próprio nível (expandida e cada opção conferida, como o bash) — antes, qualquer `{` ou
# `(` casava qualquer nome, e JSON, dicionário, `'{0}/{1}' -f` e `[0-9]{2}/` citados da raiz negavam —; o extglob
# (`@(...)`, `!(...)`, `*(...)`...) e o `{}` do `xargs -I{}` e do `find -exec` casam qualquer nome.
CURINGA_PALAVRA = re.compile(r"[*?\[{]|[@+!]\(")
SEQUENCIA = re.compile(r"\{(?:-?\d+\.\.-?\d+|[A-Za-z]\.\.[A-Za-z])(?:\.\.-?\d+)?\}")
DIFICIL = re.compile(r"[@+!?*]\(|\{\}")
LIMITE_EXPANSOES = 64
REDIR_FD = re.compile(r"(?:\d+|\{[A-Za-z_][A-Za-z0-9_]*\})\Z")  # Bash: o descritor antes do operador (`2>`, `{fd}>`)
REDIR_FD_PS = re.compile(r"[1-6*]\Z")  # PowerShell: `2>`, `*>`
ANSI_C = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v",
          "\\": "\\", "'": "'", '"': '"', "?": "?"}
HEX = frozenset("0123456789abcdefABCDEF")
PROTEGE = str.maketrans({"{": "\ue000", ",": "\ue001", "}": "\ue002"})  # chave e vírgula entre aspas: o bash não as
RESTAURA = str.maketrans({"\ue000": "{", "\ue001": ",", "\ue002": "}"})  # expande
ACOES_DO_FIND = {"-exec", "-execdir", "-ok", "-okdir", "-delete"}
TAR_COM_VALOR = "fCTXbHKLNgVI"  # letras do tar que levam valor (`C` é a pasta dos operandos seguintes)
LISTAGENS_PS = {"get-childitem", "gci", "ls", "dir"}  # dão ao cano os filhos das pastas
ITENS_PS = {"get-item", "gi"}  # dão ao cano a própria pasta
FILTROS_PS = {"where-object", "where", "?"}
PASSAM_PS = {"sort-object", "sort", "select-object", "select"}
RECEBE_DO_CANO = SO_POWERSHELL | {"ls", "dir", "copy", "del", "erase", "rmdir", "rd", "move"}  # no PowerShell, sem
                                                                                                 # caminho, as do `|`


def deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def _troca_identidade(comando: str) -> bool:
    """A atribuição ou remoção da identidade: o PADRAO, e `SetEnvironmentVariable(` com o nome antes do primeiro `)`
    seguinte (a API .NET), conferido com as posições guardadas numa passada (revisão 1 da rodada 4, HOOK-F5)."""
    nomes = [m.start() for m in PRINCIPAL.finditer(comando)]
    if not nomes:
        return False
    if PADRAO.search(comando):
        return True
    fechos = [i for i, c in enumerate(comando) if c == ")"]
    for m in API_DOTNET.finditer(comando):
        j, k = bisect.bisect_left(fechos, m.end()), bisect.bisect_left(nomes, m.end())
        if k < len(nomes) and (j == len(fechos) or nomes[k] < fechos[j]):
            return True
    return False


class _Excesso(Exception):
    """O comando passa do que o guarda confere a tempo (chaves, pastas possíveis ou trabalho demais): nega, com este
    motivo."""


class _Simples:
    """Um comando simples: as palavras (cada uma nas duas leituras), o separador que o fecha, os alvos de
    redirecionamento (conferidos como citação, não como argumento: `cd 2>/dev/null X` vai para X) e o texto das
    substituições de comando entre aspas duplas (reanalisado: `"$(grep -r x ..)"`). Revisão 1 da rodada 4. Revisão 2:
    `aqui`, o texto dos here-strings (`<<< '...'`), que vira comando se quem o lê é um lançador (`bash <<< '...'`)."""

    __slots__ = ("palavras", "separador", "redir", "subst", "aqui")

    def __init__(self, palavras: list, separador: str | None, redir: list, subst: list, aqui: list | None = None):
        self.palavras, self.separador, self.redir, self.subst = palavras, separador, redir, subst
        self.aqui = [] if aqui is None else aqui


def _comandos(comando: str, powershell: bool, ctx: _Contexto | None = None) -> list[_Simples]:
    """Os comandos simples do texto com o separador que fecha cada um (`;`, `&&`, `||`, `|`, `&`, quebra de linha,
    parêntese, crase no Bash, chave no PowerShell); cada palavra sem as aspas em duas leituras: (a do shell, a antiga).
    Bash, fora de aspas: `\\` escapa qualquer caractere e, com a quebra de linha, some, como o bash lê (revisão de
    segurança da 1.7.10, HOOK-F4); a leitura antiga mantém a barra antes de caractere comum (caminho do Windows) e a
    quebra. Entre aspas duplas, `\\` escapa `"`, `\\`, `$` e a crase. PowerShell: a crase escapa qualquer caractere (a
    quebra escapada some só na segunda leitura); as aspas dobradas valem dentro de aspas. Revisão 1 da rodada 4: o
    redirecionamento (`>`, `2>`, `&>`, `<<<`, `{fd}>`...) leva a palavra seguinte para `redir`; a palavra vazia entre
    aspas fica (`cd ""` não é `cd`); `$'...'` e `$"..."` do bash; `{a,b}` fora de aspas expandido (_chaves); a
    substituição de comando entre aspas duplas vai para `subst`. Revisão 2 da rodada 4: o comentário some (`#` no
    começo da palavra até a quebra de linha; no PowerShell, também logo depois de aspas, e `<# ... #>`); o extglob fora
    de aspas (`@(...)`, `!(...)`...) fica na palavra, e o texto de dentro vai para `subst` (sem extglob, `!(...)` é um
    subshell negado); o alvo de `<<<` vai também para `aqui`; o texto e as expansões entram no orçamento (ctx).
    Revisão 3 da rodada 4: o corpo do here-doc (`<<EOF`, `<<-EOF`), das linhas depois da quebra de linha até a do
    delimitador, é dado, não comando (_corpo_do_heredoc). Linear no tamanho."""
    if ctx is not None:
        ctx.gastar(len(comando))
    escape = "`" if powershell else "\\"
    fim = set(";|&\n()") | (set("{}") if powershell else {"`"})
    comandos, shell, antiga, corpos = [], [], [], []
    atual = _Simples([], None, [], [])
    citada = alvo = fechou = cru_antes = False

    def fecha(separador: str | None) -> None:
        nonlocal atual, citada, alvo
        if shell or antiga or citada:
            palavra = ("".join(shell), "".join(antiga))
            novas = [palavra] if powershell else _chaves(palavra, citada, ctx)
            (atual.redir if alvo else atual.palavras).extend(novas)
            if alvo == "<<<":  # here-string: o texto que entra (revisão 2 da rodada 4)
                atual.aqui.extend(nova[0] for nova in novas)
            elif alvo in ("<<", "<<-"):  # here-doc: o corpo vem depois da quebra de linha (revisão 3 da rodada 4)
                corpos.append((atual, palavra[0].translate(RESTAURA), alvo == "<<-", citada))
            shell.clear()
            antiga.clear()
            citada = alvo = False
        if separador is None:
            return
        alvo = False
        if atual.palavras or atual.redir or atual.subst:
            atual.separador = separador
            comandos.append(atual)
            atual = _Simples([], None, [], [])
        elif separador in ("(", ")", "`", "{", "}", "|"):  # o escopo e o cano contam sem comando antes
            comandos.append(_Simples([], separador, [], []))

    aspa, i, n = None, 0, len(comando)
    while i < n:
        ch, prox = comando[i], comando[i + 1:i + 2]
        um = dois = None  # o que entra em cada leitura (None: nada)
        cru = False  # fora de aspas e sem escape: no Bash, a chave e a vírgula dele expandem
        depois_de_aspas, fechou = fechou, False
        comeco = not (shell or antiga or citada) or (powershell and depois_de_aspas)  # onde um comentário pode abrir
        if aspa == "'":
            if ch != "'":
                um = dois = ch
            elif powershell and prox == "'":
                um = dois = "'"
                i += 1
            else:
                aspa, fechou = None, True
        elif aspa == '"':
            if ch == escape and prox and (powershell or prox in '"\\$`\n'):
                um, dois = ("", "\n") if prox == "\n" and not powershell else (prox, prox)
                i += 1
            elif ch == '"' and powershell and prox == '"':
                um = dois = '"'
                i += 1
            elif ch == '"':
                aspa, fechou = None, True
            elif (ch == "$" and prox == "(") or (ch == "`" and not powershell):
                # Revisão 1 da rodada 4 (HOOK-F3): a substituição de comando entre aspas roda; o texto dela é
                # reanalisado, e a palavra fica com ele (a CITACAO o vê).
                ini = i + (2 if ch == "$" else 1)
                fecho = _fecho(comando, ini, powershell, "$" if ch == "$" else "`")
                dentro = comando[ini:fecho]
                atual.subst.append(dentro if ch == "$" else re.sub(r"\\([$`\\])", r"\1", dentro))
                shell.append(comando[i:fecho + 1] if powershell else comando[i:fecho + 1].translate(PROTEGE))
                antiga.append(comando[i:fecho + 1])
                i = fecho + 1
                continue
            else:
                um = dois = ch
        elif comeco and (ch == "#" or (powershell and ch == "<" and prox == "#")):
            # Revisão 2 da rodada 4 (HOOK-F3): o comentário some, como o shell o lê — antes, `true #; cd X &&` mudava a
            # pasta acompanhada; o `<# ... #>` do PowerShell separa as palavras.
            if ch == "#":
                quebra = comando.find("\n", i)
                i = n if quebra < 0 else quebra
            else:
                fecho = comando.find("#>", i + 2)
                i = n if fecho < 0 else fecho + 2
                fecha(None)
            cru_antes = False
            continue
        elif ch == escape and prox:
            i += 1
            citada = True
            if prox == "\n":
                um, dois = ("\n", "") if powershell else ("", "\n")
            elif powershell or prox.isspace() or prox in "\"';|&<>()":
                um = dois = prox
            else:
                um, dois = prox, ch + prox
        elif ch == "$" and prox == "'" and not powershell:  # `$'...'` (revisão 1 da rodada 4: `$'\x2e\x2e'` é `..`)
            texto, fecho = _ansi_c(comando, i + 2)
            shell.append(texto.translate(PROTEGE))
            antiga.append(comando[i + 2:fecho])
            citada, i, cru_antes = True, fecho + 1, False
            continue
        elif ch == "$" and prox == '"' and not powershell:  # `$"..."` do bash: aspas duplas
            aspa, citada = '"', True
            i += 1
        elif ch in "\"'":
            aspa, citada = ch, True
        elif ch == "(" and not powershell and cru_antes and shell[-1] in "@!+?*":
            # Revisão 2 da rodada 4 (HOOK-F3): extglob (`@(projects)/x`, `!(state)`) — o bash o lê como parte da palavra
            # (antes, o `(` fechava a palavra e o padrão sumia); sem extglob, `!(...)` é um subshell negado, e o texto
            # de dentro também é reanalisado.
            fecho = _fecho(comando, i + 1, False, "(")
            atual.subst.append(comando[i + 1:fecho])
            shell.append(comando[i:fecho + 1].translate(PROTEGE))
            antiga.append(comando[i:fecho + 1])
            i, cru_antes = fecho + 1, False
            continue
        elif ch == ">" or (ch == "<" and not (powershell and not comeco)) or (ch == "&" and prox == ">" and
                                                                             not powershell):
            # (no PowerShell, o `<` no meio da palavra é letra: `a<#x#>b` é uma palavra só; revisão 2 da rodada 4)
            if shell and not citada and (REDIR_FD_PS if powershell else REDIR_FD).match("".join(shell)):
                shell.clear()  # o número do descritor faz parte do operador (`2>`, `{fd}>`, `*>`)
                antiga.clear()
            else:
                fecha(None)
            cru_antes = False
            if not powershell and ch in "<>" and prox == "(":  # `<(...)` e `>(...)`: substituição de processo
                i += 1
                continue
            entrada = "" if powershell else next((op for op in ("<<<", "<<-", "<<") if comando.startswith(op, i)), "")
            i, alvo = _operador(comando, i)
            alvo = entrada if entrada and alvo else alvo
            continue
        elif ch in fim:
            duplo = ch in "&|" and prox == ch  # `&&` e `||`
            fecha(ch * 2 if duplo else ch)
            i += 1 if duplo else 0
            if ch == "\n" and corpos:  # os here-docs da linha: o corpo de cada um, em ordem (revisão 3 da rodada 4)
                for dono, delimitador, tira, cotado in corpos:
                    corpo, i = _corpo(comando, i + 1, delimitador, tira)
                    _corpo_do_heredoc(dono, corpo, cotado)
                    i -= 1
                corpos.clear()
        elif ch.isspace():
            fecha(None)
        else:
            um = dois = ch
            cru = True
        if um is not None:
            shell.append(um if cru or powershell else um.translate(PROTEGE))
            antiga.append(dois)
        cru_antes = cru
        i += 1
    fecha(";")
    return comandos


def _operador(comando: str, i: int) -> tuple[int, bool]:
    """O redirecionamento que começa em `i` (`<`, `>`, `>>`, `>|`, `<>`, `<<`, `<<-`, `<<<`, `&>`, `&>>`, `>&`, `<&`):
    onde ele termina e se a palavra seguinte é o alvo (`>&2`, `2>&1` e `>&-` só duplicam ou fecham um descritor)."""
    n, j = len(comando), i + 1 if comando[i] == "&" else i
    op, j = comando[j], j + 1
    if op == "<" and comando.startswith("<<", j):
        j += 2
    elif op == "<" and comando.startswith("<", j):
        j += 2 if comando.startswith("-", j + 1) else 1
    elif comando[j:j + 1] in ((">", "|") if op == ">" else (">",)):
        j += 1
    if comando[i] != "&" and comando.startswith("&", j):
        k = j + 1
        while k < n and comando[k].isdigit():
            k += 1
        k += 1 if k == j + 1 and comando.startswith("-", k) else 0
        if k > j + 1 and (k == n or comando[k].isspace() or comando[k] in ";|&()<>`"):
            return k, False
        return j + 1, True
    return j, True


def _corpo(texto: str, i: int, delimitador: str, tira: bool) -> tuple[str, int]:
    """O corpo de um here-doc (`<<EOF`) a partir da linha que começa em `i`, até a linha que é só o delimitador (com
    `<<-`, as tabulações do começo de cada linha e da linha do delimitador são ignoradas, como no bash): o texto do
    corpo e o índice do começo da linha seguinte à do delimitador (o fim do texto, se não fecha). Revisão 3 da rodada
    4 (HOOK-F3/F5: o JSON minificado no corpo negava)."""
    linhas, n = [], len(texto)
    while i <= n:
        quebra = texto.find("\n", i)
        fim = n if quebra < 0 else quebra
        linha = texto[i:fim]
        if (linha.lstrip("\t") if tira else linha) == delimitador:
            return "\n".join(linhas), min(fim + 1, n)
        linhas.append(linha)
        if quebra < 0:
            break
        i = fim + 1
    return "\n".join(linhas), n


def _substituicoes_do_corpo(corpo: str) -> list[str]:
    """As substituições de comando de um corpo de here-doc sem aspas (`$(...)`, a crase), que o bash roda: o texto de
    cada uma, para reanalisar (revisão 3 da rodada 4). Uma passada; a barra invertida escapa `$`, a crase e ela mesma,
    como no corpo sem aspas."""
    achados, i, n = [], 0, len(corpo)
    while i < n:
        ch = corpo[i]
        if ch == "\\" and i + 1 < n:
            i += 2
        elif ch == "$" and corpo.startswith("(", i + 1):
            fecho = _fecho(corpo, i + 2, False, "$")
            achados.append(corpo[i + 2:fecho])
            i = fecho + 1
        elif ch == "`":
            fecho = _fecho(corpo, i + 1, False, "`")
            achados.append(re.sub(r"\\([$`\\])", r"\1", corpo[i + 1:fecho]))
            i = fecho + 1
        else:
            i += 1
    return achados


def _corpo_do_heredoc(dono: _Simples, corpo: str, cotado: bool) -> None:
    """O corpo de um here-doc (revisão 3 da rodada 4, HOOK-F3/F5): dado que entra pela entrada padrão (`aqui`), lido
    como comando só por um lançador (`bash <<EOF`) — e então o JSON minificado no corpo de `cat`/`python` não é mais
    palavra de comando (antes, `{...}` com mais de 64 combinações negava). Com o delimitador sem aspas, as
    substituições de comando do corpo rodam e são reanalisadas (vão para `subst`)."""
    dono.aqui.append(corpo)
    if not cotado:
        dono.subst.extend(_substituicoes_do_corpo(corpo))


def _fecho(texto: str, i: int, powershell: bool, contexto: str) -> int:
    """Onde fecha a substituição de comando aberta antes de `i` (`$(`: contexto "$"; a crase do Bash: contexto "`"; o
    extglob: contexto "("), com as aspas, os escapes, os parênteses, as substituições aninhadas e, fora da crase, os
    comentários no caminho (revisão 2 da rodada 4: o bash não fecha `"$(echo #)"` no `)` do comentário): o índice do
    `)` ou da crase que a fecha; o fim do texto, se não fecha. Uma passada."""
    escape, pilha, n, comeco = "`" if powershell else "\\", [contexto], len(texto), True
    while i < n:
        ch, topo = texto[i], pilha[-1]
        if topo in "($" and comeco and (ch == "#" or (powershell and texto.startswith("<#", i))):
            if ch == "#":
                quebra = texto.find("\n", i)
                i = n if quebra < 0 else quebra
            else:
                fecho = texto.find("#>", i + 2)
                i = n if fecho < 0 else fecho + 2
            continue
        comeco = ch.isspace() or ch in ";|&()<>" or (powershell and ch in "{}")
        if topo == "'":
            if ch == "'":
                pilha.pop()
        elif ch == escape and i + 1 < n:
            i += 1
        elif topo == '"':
            if ch == '"':
                pilha.pop()
            elif ch == "$" and texto.startswith("(", i + 1):
                pilha.append("$")
                i += 1
            elif ch == "`":
                pilha.append("`")
        elif ch == "`" and not powershell:
            if topo == "`":
                pilha.pop()
            else:
                pilha.append("`")
        elif ch in "'\"":
            pilha.append(ch)
        elif ch == "(":
            pilha.append("(")
        elif ch == ")" and topo in "($":
            pilha.pop()
        if not pilha:
            return i
        i += 1
    return n


def _ansi_c(texto: str, i: int) -> tuple[str, int]:
    """`$'...'` do bash a partir de `i` (depois de `$'`): o texto com os escapes resolvidos (`\\x2e`, `\\160`,
    `\\u0070`, `\\n`, `\\cX`...) e o índice da aspa que fecha (o fim do texto, se não fecha)."""
    res, n = [], len(texto)
    while i < n and texto[i] != "'":
        if texto[i] != "\\" or i + 1 >= n:
            res.append(texto[i])
            i += 1
            continue
        c, i = texto[i + 1], i + 2
        if c in ANSI_C:
            res.append(ANSI_C[c])
        elif c in "01234567" or (c in "xuU" and i < n and texto[i] in HEX):
            ini, base = (i - 1, 8) if c in "01234567" else (i, 16)
            fim, digitos = min(n, ini + ({"x": 2, "u": 4, "U": 8}.get(c, 3))), "01234567" if base == 8 else HEX
            j = ini
            while j < fim and texto[j] in digitos:
                j += 1
            valor = int(texto[ini:j], base)
            res.append(chr(valor & 0xFF) if base == 8 else chr(valor) if valor <= 0x10FFFF else "?")
            i = j
        elif c == "c" and i < n:
            res.append(chr(ord(texto[i]) & 0x1F))
            i += 1
        else:
            res.append("\\" + c)
    return "".join(res), min(i, n)


def _grupo(p: str) -> list[str] | None:
    """As opções da chave mais à esquerda que fecha e tem vírgula no próprio nível (uma passada, como no
    guarda_leitura); `${...}` não expande. None sem ela."""
    pilha, achados = [], []
    for i, ch in enumerate(p):
        if ch == "{":
            pilha.append((i, None if i and p[i - 1] == "$" else []))
        elif ch == "," and pilha and pilha[-1][1] is not None:
            pilha[-1][1].append(i)
        elif ch == "}" and pilha and (aberta := pilha.pop())[1]:
            achados.append((aberta[0], i, aberta[1]))
    if not achados:
        return None
    ini, fim, virgulas = min(achados)
    return [p[:ini] + p[a + 1:b] + p[fim + 1:] for a, b in zip([ini, *virgulas], [*virgulas, fim])]


def _expandir(texto: str) -> list[str]:
    """`{a,b}` expandido na ordem do bash (aninhado inclusive); mais de 64 nega (_Excesso)."""
    pendentes, prontos = [texto], []
    while pendentes:
        p = pendentes.pop()
        opcoes = _grupo(p)
        if opcoes is None:
            prontos.append(p)
        else:
            pendentes.extend(reversed(opcoes))
        if len(prontos) + len(pendentes) > LIMITE_EXPANSOES:
            raise _Excesso(f"palavra com chaves `{{a,b}}` demais para conferir (mais de {LIMITE_EXPANSOES} expansões; "
                           "revisão 1 da rodada 4): escreva os caminhos por extenso")
    return prontos


def _chaves(palavra: tuple[str, str], citada: bool, ctx: _Contexto | None) -> list[tuple[str, str]]:
    """A palavra do Bash com `{a,b}` fora de aspas expandido, como o bash faz antes de tudo (revisão 1 da rodada 4:
    `{..,x}/<outro>` e `{projects,x}/<outro>` escondiam o caminho); cada expansão com a leitura antiga. Revisão 2 da
    rodada 4: a expansão vazia de uma palavra sem aspas some, como no bash (`{cd,} ..` é `cd ..`), e as expansões
    entram no orçamento da decisão (antes, um teto por chamada: o `eval` aninhado o multiplicava)."""
    shell, antiga = palavra
    if "{" not in shell or "," not in shell or "}" not in shell:
        return [(shell.translate(RESTAURA), antiga)]
    novas = [(x.translate(RESTAURA), antiga) for x in _expandir(shell) if x or citada]
    if ctx is not None:
        ctx.gastar(sum(len(x) for x, _ in novas))
    return novas


def _so_pontos(comp: str) -> bool:
    """`..` também com ponto ou espaço a mais no fim (o Windows os ignora)."""
    return comp.count(".") >= 2 and not comp.strip(" .")


def _partes(caminho: str, base: list[str] | None = None) -> list[str]:
    """Caminho em partes sem caixa: unidade e /mnt/<l> viram `<l>:`; `.` e `..` resolvidos no texto. Com `base`
    (partes de uma pasta), o caminho é relativo a ela."""
    t = caminho.replace("\\", "/")
    m = None if base else UNIDADE.match(t) or (BASH_DO_WINDOWS.match(t) if os.name == "nt" else None)
    if base:
        partes = list(base)
    elif m:
        partes, t = [next(g for g in m.groups() if g).lower() + ":"], t[m.end():]
    else:
        partes = ["/" if t.startswith("/") else ""]
    for comp in t.split("/"):
        if comp in ("", "."):
            continue
        if _so_pontos(comp):
            if len(partes) > 1:
                partes.pop()
            continue
        partes.append(comp.rstrip(" .").casefold())
    return partes


def _corte(partes: list[str], de: int = 1) -> int:
    """Onde a raiz termina: no último `projects` a partir de `de` (a pasta de um projeto não vira raiz)."""
    return max((i for i in range(de, len(partes)) if partes[i] == "projects"), default=len(partes))


def _raizes(env: dict, nome: str | None = None) -> list[list[str]]:
    """A raiz em partes: FUNDACAO_RAIZ; sem ela, a pasta da instalação do hook (§7: `<raiz>/.claude/hooks/`, que a
    sessão não escolhe), inteira se tiver projects/<nome do projeto da sessão>, e CLAUDE_PROJECT_DIR, cada uma subindo
    para a pasta de cima do último `projects` (para pasta dentro da raiz da instalação, só o de dentro dela): a pasta
    do projeto não vira raiz, senão calaria o `..` dele, e a raiz pode ficar numa pasta `projects` (`~/projects/fund`;
    reconferência do lote 2). A raiz só serve para NÃO contar um trecho e para ancorar a pasta atual."""
    texto = (env.get("FUNDACAO_RAIZ") or "").strip()
    if texto:
        return [_partes(texto)]
    hooks, res = os.path.dirname(os.path.abspath(__file__)), []
    if [os.path.basename(p).casefold() for p in (hooks, os.path.dirname(hooks))] == ["hooks", ".claude"]:
        pasta = os.path.dirname(os.path.dirname(hooks))
        raiz = _partes(pasta)
        inteira = bool(nome) and os.path.lexists(os.path.join(pasta, "projects", nome))
        res.append(raiz if inteira else raiz[:_corte(raiz)])
    texto = (env.get("CLAUDE_PROJECT_DIR") or "").strip()
    if texto:
        aberta = _partes(texto)
        res.append(aberta[:_corte(aberta, next((len(r) for r in res if aberta[:len(r)] == r), 1))])
    return res


def _formas(raiz: list[str]) -> list[list[str]]:
    """A raiz e os outros nomes dela que o curinga não deixa traduzir (revisão de segurança da 1.7.10, HOOK-F3): fora
    do Windows, /mnt/<l> e o apelido /mnt/wslg/distro do disco da distribuição; no Windows, /<l>, /cygdrive/<l> e, como
    a leitura literal (UNIDADE), /mnt/<l> (revisão 1 da rodada 4)."""
    cabeca = raiz[0] if raiz else ""
    letra = cabeca[0] if len(cabeca) == 2 and cabeca[1] == ":" else None
    if os.name == "nt":
        return [raiz] + ([["/", letra] + raiz[1:], ["/", "cygdrive", letra] + raiz[1:], ["/", "mnt", letra] + raiz[1:]]
                         if letra else [])
    if letra:
        return [raiz, ["/", "mnt", letra] + raiz[1:], ["/", "mnt", "wslg", "distro", "mnt", letra] + raiz[1:]]
    return [raiz] + ([["/", "mnt", "wslg", "distro"] + raiz[1:]] if cabeca == "/" else [])


class _Contexto:
    """O que vale para a decisão inteira: o projeto da sessão, as raízes (e os outros nomes delas) e a pasta do
    evento; `limite` é o tamanho de texto além do qual um trecho não é a raiz (HOOK-F5). Revisão 2 da rodada 4: o
    orçamento (`gasto`, até ORCAMENTO) e se um `cd` foi redefinido (função ou alias: o destino não se sabe)."""

    def __init__(self, env: dict, cwd) -> None:
        self.p = (env.get("FUNDACAO_PROJECT") or "").strip()
        self.projeto = self.p.casefold() if NOME_SIMPLES.fullmatch(self.p) and ".." not in self.p else None
        self.raizes = _raizes(env, self.p if self.projeto else None)
        self.cwd = _partes(cwd) if isinstance(cwd, str) and cwd else None
        self.formas = [f for r in self.raizes for f in _formas(r)]
        self.limite = 2 * max((sum(len(c) + 1 for c in r) + 8 for r in self.raizes), default=0) + 64
        self.gasto, self.cd_incerto = 0, False

    def gastar(self, quanto: int) -> None:
        """Revisão 2 da rodada 4 (HOOK-F5): um orçamento só para a decisão inteira — o texto analisado em cada nível,
        as expansões de chave e cada conferência a partir de cada pasta possível; acima de ORCAMENTO, nega (antes, o
        `eval` aninhado reanalisava o texto já expandido em cada nível: 3,7 KB levavam 7 s)."""
        self.gasto += quanto
        if self.gasto > ORCAMENTO:
            raise _Excesso("comando grande, aninhado ou com pastas possíveis demais para conferir no prazo do perfil "
                           "(revisão 2 da rodada 4): divida o comando")


def _dentro_da_raiz(arg: str, ini: int, fim: int, nome: str, ctx: _Contexto) -> bool:
    """`projects/<nome>` que é parte do caminho da própria raiz (a raiz fica dentro de uma pasta `projects/`): vale o
    trecho antes inteiro ou a palavra, com ou sem o `@`/`=` da frente (caminho dentro de outro comando). Trecho mais
    longo que a raiz não é ela, e a citação conta (revisão de segurança da 1.7.10, HOOK-F5: a conta não relê o
    começo do argumento a cada citação)."""
    janela = max(ini, fim - ctx.limite)
    corte = max(arg.rfind("@", janela, fim), arg.rfind("=", janela, fim))
    for comeco in {0, ini, corte + 1 if corte >= 0 else ini}:
        trecho = arg[comeco:fim] if fim - comeco <= ctx.limite else ""
        if trecho and (trecho.startswith(("/", "\\")) or UNIDADE.match(trecho.replace("\\", "/"))):
            partes = _partes(trecho) + ["projects", nome.rstrip(" .").casefold()]
            if any(len(partes) <= len(r) and r[:len(partes)] == partes for r in ctx.raizes):
                return True
    return False


def _citacoes(arg: str, ctx: _Contexto) -> str | None:
    """`projects/<x>` de outro projeto no argumento, salvo o trecho da raiz, a URL na mesma palavra e a pasta
    `projects/` dentro do caminho do próprio projeto; e o `..` depois do próprio projeto. Linear (revisão de segurança
    da 1.7.10, HOOK-F5): o começo da palavra, a URL, as barras e os `..` vêm de posições guardadas numa passada."""
    inicios = [m.end() for m in PALAVRA.finditer(arg)]
    urls = [(m.start(), m.end()) for m in URL_DE_REDE.finditer(arg)]
    barras = [m.start() for m in BARRA.finditer(arg)]
    pontos = [m.start() for m in COMPONENTE.finditer(arg) if _so_pontos(m.group())]
    fim_proprio = -1
    for m in CITACAO.finditer(arg):
        nome = m.group(1).rstrip(" .")
        if m.start() < fim_proprio or not nome:
            continue
        k = bisect.bisect_right(inicios, m.start())
        ini = inicios[k - 1] if k else 0  # a URL e a raiz contam só na mesma palavra
        u = bisect.bisect_left(urls, (ini, -1))
        if (u < len(urls) and urls[u][1] <= m.start()) or _dentro_da_raiz(arg, ini, m.start(), nome, ctx):
            continue
        if ctx.projeto is None or nome.casefold() != ctx.projeto:
            quem = "sem projeto da sessão válido (FUNDACAO_PROJECT)" if ctx.projeto is None else "de outro projeto"
            return f"o comando cita caminho {quem} (projects/{nome[:60]})"
        j = bisect.bisect_left(barras, m.end())
        if _so_pontos(arg[m.end():barras[j] if j < len(barras) else len(arg)]) or (pontos and pontos[-1] > m.end()):
            return f"o comando sai do próprio projeto por `..` (projects/{ctx.p}/..)"
        corte = FIM_DO_CAMINHO.search(arg, m.end())
        fim_proprio = corte.start() if corte else len(arg)
    return None


def _pasta_atual(partes, raizes: list[list[str]], projeto: str | None) -> str | None:
    """A pasta em `<raiz>/projects/` ou dentro de outro projeto (sem projeto válido, de qualquer um): dali todo caminho
    relativo, até o implícito (`rg senha`, `find`), cai fora do próprio projeto (revisão do lote 2)."""
    for r in raizes if partes else ():
        if partes[:len(r)] == r and partes[len(r):len(r) + 1] == ["projects"]:
            if len(partes) == len(r) + 1:
                return "a pasta atual é projects/, de todos os projetos"
            if partes[len(r) + 1] != projeto:
                return f"a pasta atual é de outro projeto (projects/{partes[len(r) + 1][:60]})"
    return None


def _sai_da_pasta(comandos: list[_Simples], ctx: _Contexto) -> bool:
    """`cd <destino>` (ou `cd` sozinho) para fora de projects/ e de outro projeto: a saída da pasta atual proibida (vale
    a leitura que sai; na antiga, o caminho do Windows com a barra invertida)."""
    reais = [c.palavras for c in comandos if c.palavras]
    if len(reais) != 1 or len(reais[0]) > 2 or reais[0][0][0].casefold() not in SAIDAS:
        return False
    for alvo in dict.fromkeys(reais[0][1] if len(reais[0]) == 2 else ("~",)):
        alvo = alvo.replace("\\", "/")
        destino = _partes(alvo) if alvo.startswith(("/", "~")) or UNIDADE.match(alvo) else _partes(alvo, ctx.cwd)
        if _pasta_atual(destino, ctx.raizes, ctx.projeto) is None:
            return True
    return False


def outro_projeto(comando: str, env: dict, cwd, powershell: bool = False) -> str | None:
    """O motivo da negação quando o comando cita caminho de outro projeto ou percorre todos eles; None se não."""
    ctx = _Contexto(env, cwd)
    try:
        comandos = _comandos(comando, powershell, ctx)
        motivo = _pasta_atual(ctx.cwd, ctx.raizes, ctx.projeto)
        if motivo and not _sai_da_pasta(comandos, ctx):
            return f"{motivo}; saia com cd e o caminho absoluto da raiz ou do próprio projeto"
        return _analisar(comandos, ctx, powershell, 0, [ctx.cwd])[0]
    except _Excesso as exc:
        return str(exc)


def _uniao(a: list, b: list) -> list:
    """As pastas possíveis das duas listas, sem repetir. Revisão 2 da rodada 4 (HOOK-F3): mais de LIMITE_PASTAS nega —
    antes ficavam a primeira e as três últimas, e a pasta real do meio (a raiz, depois de dois `cd` que falham) se
    perdia. Revisão 3 da rodada 4: motivo neutro — o excesso vem de `cd` relativo depois de `;`, de `-execdir` com
    muitos pontos de partida ou de `cd` redefinido, não só do primeiro —, com a saída de cada ferramenta."""
    res = []
    for pasta in a + b:
        if pasta not in res:
            res.append(pasta)
    if len(res) > LIMITE_PASTAS:
        raise _Excesso(f"pastas possíveis demais para acompanhar (mais de {LIMITE_PASTAS}: `cd X;` relativo depois de "
                       "`;`, `find -execdir` com muitos pontos de partida ou `cd` redefinido; revisão 2 da rodada 4): "
                       "divida o comando; no Bash, `cd X && ...`; no PowerShell, caminhos absolutos ou `-LiteralPath`")
    return res


def _aninhado(texto: str, modo: bool, ctx: _Contexto, prof: int, possiveis: list) -> tuple[str | None, list]:
    """O texto analisado como comando um nível abaixo (lançador, substituição, here-string, `env -S`); o nível é
    conferido antes de gastar o orçamento (revisão 2 da rodada 4)."""
    if prof + 1 > 3:
        return ANINHADO, possiveis
    return _analisar(_comandos(texto, modo, ctx), ctx, modo, prof + 1, possiveis)


def _redefine(cmd: _Simples, powershell: bool) -> bool:
    """Função ou alias com o nome de um comando que muda a pasta (`cd() { ...; }`, `function cd`, `alias cd=...`,
    `Set-Alias sl ...`): depois dela, o destino de todo `cd` não se sabe (revisão 2 da rodada 4: `cd() { :; }; cd X &&
    grep -r x .` roda o grep na pasta de antes)."""
    textos = [w[0].casefold() for w in cmd.palavras]
    if not textos:
        return False
    if any(t.split("function:", 1)[1].strip("\\/{}=") in REDEFINIVEIS for t in textos if "function:" in t):
        return True  # `Set-Item function:Set-Location {...}`, `${function:cd} = {...}` (PowerShell)
    if textos[0] in ("function", "filter") and len(textos) > 1:
        nomes = [textos[1].split("(")[0]]
    elif not powershell and len(textos) == 1 and cmd.separador == "(":  # `cd() {...}`, `cd () {...}`
        nomes = textos
    elif textos[0] == "alias":
        nomes = [t.split("=", 1)[0] for t in textos[1:]]
    elif textos[0] in ("set-alias", "new-alias", "sal", "nal"):
        nomes = textos[1:]
    else:
        return False
    return any(nome.lstrip("-") in REDEFINIVEIS or nome.split(":", 1)[-1] in REDEFINIVEIS for nome in nomes)


def _analisar(comandos: list[_Simples], ctx: _Contexto, powershell: bool, prof: int,
              base: list) -> tuple[str | None, list]:
    """Cada comando simples: as palavras e os alvos de redirecionamento, nas duas leituras (_palavra), as
    substituições de comando entre aspas (reanalisadas um nível abaixo) e o percurso da árvore (HOOK-F3), a partir de
    cada pasta em que ele pode rodar (None: não se sabe; sem nenhuma conhecida, a do evento). Revisão 1 da rodada 4:
    numa lista com `&&` e `||`, o elo roda com as pastas do sucesso ou da falha do anterior — o `cd` que falha deixa a
    pasta como estava, e `!` troca as duas (`cd X || cd Y && z` pode rodar em X; `cd /nada && true || z`, na de
    antes) —; no começo e depois de `;`, com as duas juntas; a lista que vai para o segundo plano (`&`) não muda a
    pasta. Bash: cada parte de um cano (`|`), parêntese, `$(...)` e crase rodam à parte e não a mudam. PowerShell: a
    pasta é da sessão — o que mudou num cano, num parêntese ou numa chave soma-se à de antes; o que o comando manda
    pelo `|` vai ao seguinte (_cano). Devolve também as pastas possíveis no fim (o `eval` as leva adiante). Revisão 2
    da rodada 4: a função ou o alias com o nome de um `cd` torna desconhecido o destino dos seguintes (_redefine); o
    texto dos here-strings e as palavras do comando anterior do cano (o que ele escreve) vão ao comando, que os lê se
    for um lançador (`bash <<< '...'`, `echo '...' | sh`, `'...' | iex`); `pushd -n` e `popd -n` só mexem na pilha;
    mais de LIMITE_PASTAS pastas possíveis nega (_uniao)."""
    if prof > 3:
        return ANINHADO, base
    ok, falha, lider, inicio, entrada = list(base), list(base), None, list(base), list(base)
    pilha, crase, guardadas, cano, em_cano, nega, antes, mudou = [], False, [], None, False, False, (ok, falha), []
    anterior = None  # o comando anterior do cano (o que ele escreve: as palavras e o here-string)
    for cmd in comandos:
        if not em_cano:  # um elo da lista: as pastas em que ele (o cano inteiro) pode rodar
            entrada = ok if lider == "&&" else falha if lider == "||" else _uniao(ok, falha)
            inicio = entrada if lider is None else inicio
            antes, mudou = (ok, falha), []
            nega = bool(cmd.palavras) and cmd.palavras[0][0] == "!"
        ctx.cd_incerto = ctx.cd_incerto or _redefine(cmd, powershell)
        for texto in cmd.subst:
            motivo, final = _aninhado(texto, powershell, ctx, prof, entrada)
            if motivo:
                return motivo, _uniao(ok, falha)
            entrada = _uniao(entrada, final) if powershell else entrada
        bases = [b for b in entrada if b is not None] or ([ctx.cwd] if ctx.cwd else [])
        for palavra in cmd.palavras + cmd.redir:
            motivo = _palavra(palavra, bases, ctx, powershell)
            if motivo:
                return motivo, _uniao(ok, falha)
        escrito = cmd.aqui + ([w[0] for w in (anterior.palavras if powershell else anterior.palavras[1:])]
                              + anterior.aqui if em_cano and anterior is not None else [])
        motivo, efeito = (_percorre(cmd.palavras, ctx, bases, entrada, powershell, prof, cano, escrito)
                          if cmd.palavras else (None, _SEM_CD))
        if motivo:
            return motivo, _uniao(ok, falha)
        destino, separador = entrada, cmd.separador
        if efeito is not _SEM_CD:
            tipo = efeito[0]
            if tipo == "desempilha":
                destino = guardadas.pop() if guardadas else _uniao(entrada, [None])
            elif tipo == "desempilha?":  # `popd +N`: fica onde está ou vai à do topo
                destino = _uniao(entrada, guardadas.pop() if guardadas else [None])
            elif tipo == "tira":  # `popd -n`: só tira da pilha (revisão 2 da rodada 4)
                guardadas = guardadas[:-1]
            elif tipo == "empilha -n":  # `pushd -n X`: só empilha X, e o popd seguinte vai a ela (revisão 2)
                guardadas = (guardadas + [efeito[1]])[-64:]
            else:  # a pilha do pushd guarda até 64 (as mais antigas saem: o popd delas não se sabe)
                guardadas = (guardadas + [entrada])[-64:] if tipo == "empilha" else guardadas
                destino = efeito[1]
        anterior = cmd if separador == "|" else None
        cano = _cano(cmd.palavras, bases, cano) if powershell and separador == "|" else None
        if separador == "|":  # o cano continua; no PowerShell, o que ele mudar soma-se no fim
            mudou, em_cano = (_uniao(mudou, destino) if powershell else mudou), True
            continue
        if em_cano:  # o fim de um cano: no Bash, cada parte rodou à parte
            elo_ok = elo_falha = _uniao(entrada, _uniao(mudou, destino)) if powershell else entrada
        else:
            elo_ok, elo_falha = destino, entrada
        elo_ok, elo_falha = (elo_falha, elo_ok) if nega else (elo_ok, elo_falha)
        if lider == "&&":
            ok, falha = elo_ok, _uniao(elo_falha, antes[1])
        elif lider == "||":
            ok, falha = _uniao(elo_ok, antes[0]), elo_falha
        else:
            ok, falha = elo_ok, elo_falha
        ok, falha = (inicio, inicio) if separador == "&" else (ok, falha)  # segundo plano: a lista roda à parte
        em_cano, lider = False, separador if separador in ("&&", "||") else None
        if separador in ("(", "{") or (separador == "`" and not crase):
            pilha.append((ok, falha, guardadas[:]))
            ok = falha = entrada
            crase = crase or separador == "`"
        elif separador in (")", "}", "`") and pilha:
            ok_antes, falha_antes, guardadas_antes = pilha.pop()
            dentro = _uniao(ok, falha)
            ok, falha = ((_uniao(ok_antes, dentro), _uniao(falha_antes, dentro)) if powershell
                         else (ok_antes, falha_antes))
            guardadas = guardadas if powershell else guardadas_antes
            crase = False if separador == "`" else crase
    return None, _uniao(ok, falha)


def _palavra(palavra: tuple[str, str], bases: list, ctx: _Contexto, powershell: bool = False) -> str | None:
    """As conferências de citação de uma palavra, nas duas leituras: `projects/<x>` (CITACAO), o `..` relativo que cai
    em outro projeto e o curinga que pode cair nele (revisão 1 da rodada 4). Revisão 2 da rodada 4: no PowerShell,
    também cada item de uma lista com vírgula (`minutas\\a.md,..\\<outro>\\x`); cada conferência a partir de uma pasta
    entra no orçamento."""
    textos = list(palavra) + ([p for t in palavra if "," in t for p in t.split(",")] if powershell else [])
    for texto in dict.fromkeys(textos):
        motivo = _citacoes(texto, ctx) if "projects" in texto.casefold() else None
        for b in bases if not motivo and texto.count(".") >= 2 else ():
            ctx.gastar(len(texto) + 8)
            motivo = _relativo_para_outro(texto, b, ctx.projeto)
            if motivo:
                break
        if not motivo and CURINGA_PALAVRA.search(texto):
            motivo = _curinga_para_outro(texto, bases, ctx)
        if motivo:
            return motivo
    return None


def _relativo_para_outro(arg: str, cwd_partes, projeto) -> str | None:
    """Argumento relativo com `..` em qualquer ponto (`../<x>`, `minutas/../../<x>`: reconferência do lote 2) que, a
    partir de um cwd dentro de projects/<p>, cai em outro projeto: o argumento inteiro e cada palavra dele (comando
    dentro de outro), também depois de `=` ou de `@` (revisão do lote 2). O absoluto (`/`, `~`, unidade, URL) fica
    com a CITACAO; `~+` e `$PWD` são a pasta atual (revisão 2 da rodada 4: `~+/../<x>` passava)."""
    if not cwd_partes or projeto is None:
        return None
    k = next((i for i in range(len(cwd_partes) - 2, 0, -1)
              if cwd_partes[i] == "projects" and cwd_partes[i + 1] == projeto), None)
    if k is None:
        return None
    palavras = [arg] + PALAVRA.split(arg)
    for candidato in dict.fromkeys(c for pal in palavras for c in (pal, pal.split("=", 1)[-1], pal.lstrip("@"))):
        vez = PASTA_DA_VEZ.match(candidato)
        candidato = "." + candidato[vez.end():] if vez else candidato
        t = candidato.replace("\\", "/")
        if t.startswith(("/", "~")) or UNIDADE.match(t) or URL_DE_REDE.match(t) or not any(
                _so_pontos(c) for c in SEPARADORES.split(t)):
            continue
        destino = _partes(candidato, base=cwd_partes)
        if destino[:k + 1] == cwd_partes[:k + 1] and len(destino) > k + 1 and destino[k + 1] != projeto:
            return f"o comando sai do próprio projeto para outro (projects/{destino[k + 1][:60]}) por `..`"
    return None


# ------------------------------------------------------------------ revisão 1 da rodada 4: curinga em qualquer ponto
def _casa(comp: str, nome: str | None, projeto: str | None) -> bool:
    """O componente (sem caixa; com curinga do shell ou do programa, ou não) pode ser `nome`? `nome` None: outro
    projeto — qualquer nome diferente do da sessão, e o curinga conta como outro. Revisão 2 da rodada 4: a chave com
    vírgula no próprio nível é expandida como o bash e cada opção conferida (a sem vírgula é literal); o extglob e o
    `{}` casam qualquer nome; mais de 64 expansões contam como qualquer nome (falso positivo declarado)."""
    curinga = CURINGA_PALAVRA.search(comp)
    if nome is None:
        return bool(curinga) or projeto is None or comp != projeto
    if not curinga:
        return comp == nome
    padrao = SEQUENCIA.sub(lambda m: "[-0-9]*" if m.group()[1] in "-0123456789" else "[a-z]", comp)
    if DIFICIL.search(padrao):
        return True
    try:
        opcoes = _expandir(padrao)
    except _Excesso:
        return True
    return any(fnmatch.fnmatchcase(nome, p.replace("[^", "[!")) for p in opcoes)


def _em_outro(partes: list[str], ctx: _Contexto) -> str | None:
    """O caminho (com curinga) pode cair dentro de outro projeto — `<raiz>/projects/<x>`, x diferente do projeto da
    sessão, numa das formas da raiz — ou passar por ele com `**`? O componente que o alcança; None se não."""
    for forma in ctx.formas:
        molde = forma + ["projects", None]
        for i, comp in enumerate(partes):
            if "**" in comp:
                return comp
            if not _casa(comp, molde[i], ctx.projeto):
                break
            if i == len(molde) - 1:
                return comp
    return None


def _curinga_para_outro(texto: str, bases: list, ctx: _Contexto) -> str | None:
    """Palavra com curinga (`*`, `?`, classe, chave, extglob) que, a partir de cada pasta possível (ou absoluta), pode
    cair dentro de outro projeto: `<raiz>/*/<x>`, `../../*/*`, `proj[e]cts/<x>` e `*/<x>` na raiz (revisão 1 da rodada
    4, HOOK-F3 e o resíduo do HOOK-F4). A palavra inteira e cada pedaço dela (comando dentro de outro), também depois de
    `=` e de `@`."""
    pedacos = dict.fromkeys(c for p in [texto] + PALAVRA.split(texto) for c in (p, p.split("=", 1)[-1], p.lstrip("@")))
    for pedaco in pedacos:
        if not pedaco or not CURINGA_PALAVRA.search(pedaco) or URL_DE_REDE.match(pedaco):
            continue
        for base in bases or [None]:
            ctx.gastar(len(pedaco) + 8)
            partes = _resolver(pedaco, base)
            alcance = _em_outro(partes, ctx) if partes is not None and partes != ["//"] else None
            if alcance:
                return (f"o comando cita, com curinga, caminho que pode ser de outro projeto ('{pedaco[:60]}' alcança "
                        f"projects/{alcance[:60]})")
    return None


# ------------------------------------------------------------------ HOOK-F3: comandos que percorrem a árvore
def _nome(palavra: tuple[str, str]) -> str:
    """O nome do comando sem pasta, extensão do Windows nem caixa ('' se não é conhecido nem envoltório)."""
    for texto in palavra:
        nome = re.split(r"[\\/]", texto)[-1].casefold()
        nome = nome[:-4] if nome.endswith((".exe", ".cmd", ".bat", ".com")) else nome
        if nome in CONHECIDOS or nome in ENVOLTORIOS:
            return nome
    return ""


def _partida(palavras) -> tuple[int | None, tuple | None, str | None, int]:
    """Onde está o comando: depois de atribuições e palavras-chave; depois de um envoltório simples (`time`, `nohup`,
    `if`, `!`...), a primeira palavra que não é opção dele (revisão 1 da rodada 4: `time echo ls -R /` é o `echo`);
    depois de um envoltório com opções que levam valor (`sudo -u x`, `timeout 10`, `xargs -I {}`...) ou de uma opção
    longa sem `=`, o primeiro nome conhecido; None se não há. Revisão 2 da rodada 4: `command -v x` e `command -V x`
    não rodam x (None); as opções do `env` e do `sudo` são lidas — devolve também a pasta do `env -C`/`sudo -D`, o
    texto do `env -S` e o índice da palavra depois das opções deles."""
    envolto, valores, k, pasta, texto_s, depois = False, None, 0, None, None, 0
    while k < len(palavras):
        nome, texto = _nome(palavras[k]), palavras[k][0]
        if nome in CONHECIDOS:
            return k, pasta, texto_s, depois
        if nome in ("env", "sudo"):
            k, achada, dividido = _opcoes_do_envoltorio(nome, palavras, k + 1)
            pasta, texto_s, depois = achada or pasta, dividido if dividido is not None else texto_s, k
            envolto = True
            continue
        if nome in ("start-process", "saps", "start"):  # `Start-Process -WorkingDirectory <pasta>`
            achada, seguinte = _pasta_do_start(palavras, k + 1)
            pasta, depois = (achada, seguinte) if achada is not None else (pasta, depois)
        if nome == "command" and _so_consulta(palavras[k + 1:]):
            return None, pasta, texto_s, depois
        if nome in ENVOLTORIOS:
            envolto = envolto or nome not in SIMPLES
            valores = SIMPLES.get(nome, "")
        elif envolto:
            pass
        elif valores is not None and texto.startswith("--") and "=" not in texto and len(texto) > 2:
            envolto = True  # opção longa que pode levar valor: o primeiro nome conhecido (conservador)
        elif valores is not None and texto.startswith("-") and len(texto) > 1:
            k += 1 if len(texto) == 2 and texto[1] in valores else 0
        elif not PREFIXO.match(texto):
            return None, pasta, texto_s, depois
        k += 1
    return None, pasta, texto_s, depois


def _pasta_do_start(palavras, j: int) -> tuple[tuple | None, int]:
    """O `-WorkingDirectory` do Start-Process (`-wo`, `-WorkingDirectory:x`), a pasta em que o programa roda, e o
    índice da palavra seguinte ao valor (revisão 2 da rodada 4); (None, j) sem ele."""
    for k in range(j, len(palavras)):
        texto, antiga = palavras[k]
        chave, dois, _ = texto[1:].casefold().partition(":") if texto.startswith("-") else ("", "", "")
        if len(chave) >= 2 and "workingdirectory".startswith(chave):
            if dois:
                return (texto.partition(":")[2], antiga.partition(":")[2]), k + 1
            return (palavras[k + 1] if k + 1 < len(palavras) else ("", "")), k + 2
    return None, j


def _so_consulta(resto) -> bool:
    """`command -v x` e `command -V x` (também `-pv`) só dizem se x existe, sem rodá-lo (revisão 2 da rodada 4)."""
    for texto, _ in resto:
        if texto == "--" or not texto.startswith("-") or len(texto) < 2:
            return False
        if "v" in texto[1:] or "V" in texto[1:]:
            return True
    return False


def _opcoes_do_envoltorio(nome: str, palavras, j: int) -> tuple[int, tuple | None, str | None]:
    """As opções do `env` e do `sudo` a partir de `j` (revisão 2 da rodada 4): o índice da palavra depois delas, a
    pasta do `env -C`/`--chdir` e do `sudo -D`/`--chdir` (as duas leituras) e o texto do `env -S`/`--split-string`,
    que o env divide em palavras (`env -S 'grep -r x ..'`). As outras opções que levam valor tomam o valor."""
    if nome == "env":
        letras, longas = "uCSaP", {"chdir": "C", "split-string": "S", "unset": "u", "argv0": "a"}
        da_pasta, do_texto = "C", "S"
    else:
        letras = "CDghpRrtTUu"
        longas = {"chdir": "D", "close-from": "C", "group": "g", "host": "h", "prompt": "p", "chroot": "R",
                  "role": "r", "type": "t", "command-timeout": "T", "other-user": "U", "user": "u"}
        da_pasta, do_texto = "D", ""
    pasta = texto = None
    while j < len(palavras):
        atual, antiga = palavras[j]
        letra = valor = None
        if atual == "--":
            return j + 1, pasta, texto
        if atual.startswith("--"):
            chave, igual, resto = atual[2:].partition("=")
            achadas = [c for c in longas if c.startswith(chave)] if chave else []
            letra = longas[achadas[0]] if len(achadas) == 1 else None
            if letra and igual:
                valor = (resto, antiga.partition("=")[2])
        elif atual.startswith("-") and len(atual) > 1:
            for i, c in enumerate(atual[1:], 1):
                if c in letras:
                    letra = c
                    valor = (atual[i + 1:], antiga[i + 1:]) if atual[i + 1:] else None
                    break
        else:
            return j, pasta, texto
        if letra and valor is None:  # o valor é a palavra seguinte
            j += 1
            valor = palavras[j] if j < len(palavras) else ("", "")
        pasta = valor if letra == da_pasta else pasta
        texto = valor[0] if letra == do_texto and do_texto else texto
        j += 1
    return j, pasta, texto


def _chave_do_windows(nome: str, texto: str, ps: bool) -> bool:
    """`/s`, `/s/b`, `/c:x` de programa do Windows: sempre nos que só existem lá (findstr, robocopy...) e no PowerShell
    e no cmd; no Git Bash, para `dir`, `rmdir` e `tree`, só chave curta (`/f`, `/s/b`: `/mnt/q/...` é caminho); no
    Bash do Linux, `/x` é caminho."""
    if nome not in DO_CMD or not CHAVE_CMD.match(texto):
        return False
    return ps or nome in SO_WINDOWS or (os.name == "nt" and all(len(c) <= 2 for c, _ in UMA_CHAVE.findall(texto)))


def _recursivo(nome: str, textos: list[str], curtas: str, valores: str, ps: bool) -> bool:
    """A opção que faz o comando descer nas pastas: as letras curtas dele (antes de uma que leva valor), `--recursive`,
    `-d recurse` (grep), `/s` (cmd) e, no PowerShell, `-Recurse` (e o apelido `-s`) e `-Depth` (o PowerShell aceita o
    começo do nome). Revisão 2 da rodada 4: a opção longa pelo começo do nome (`--recur`, `--arch`, como o
    getopt_long), o valor do `-d`/`--directories` do grep pelo começo (`-d rec`) e o dígito no grupo de letras
    (`ls -1R`, `grep -2r`)."""
    for k, texto in enumerate(textos):
        baixo = texto.casefold()
        if baixo.startswith("--"):
            chave, igual, valor = baixo[2:].partition("=")
            if len(chave) >= 3 and any(r.startswith(chave) for r in RECURSIVAS_LONGAS):
                return True
            if nome in GREPS and len(chave) >= 3 and "directories".startswith(chave):
                valor = valor if igual else (textos[k + 1].casefold() if k + 1 < len(textos) else "")
                if valor and "recurse".startswith(valor):
                    return True
            continue
        if _chave_do_windows(nome, texto, ps) and any("s" in c for c, _ in UMA_CHAVE.findall(baixo)):
            return True
        if texto.startswith("-") and len(texto) > 1:
            chave = baixo[1:].split(":", 1)[0]
            if ps and chave and (chave == "s" or "recurse".startswith(chave) or "depth".startswith(chave)):
                return True
            for j, letra in enumerate(texto[1:], 1):
                if letra in curtas:
                    return True
                if nome in GREPS and letra == "d":  # `-d recurse`, `-drec`: o valor pelo começo (revisão 2)
                    valor = (texto[j + 1:] or (textos[k + 1] if k + 1 < len(textos) else "")).casefold()
                    if valor and "recurse".startswith(valor):
                        return True
                    break
                if letra in valores or not (letra.isalpha() or letra.isdigit()):
                    break
    return False


def _longa(nome: str, chave: str) -> tuple[str, str | None]:
    """A opção longa (sem `--` e sem `=`) do programa pelo nome inteiro ou pelo começo, como no getopt_long: (o nome,
    "v" leva valor, "c" é caminho, "s" não leva valor) ou (a chave, None) fora da tabela ou ambígua (revisão 2 da
    rodada 4)."""
    tabela = LONGAS.get(nome, LONGAS_PADRAO)
    if chave in tabela:
        return chave, tabela[chave]
    achadas = [c for c in tabela if c.startswith(chave)] if len(chave) >= 2 else []
    tipos = {tabela[c] for c in achadas}
    return (achadas[0], tipos.pop()) if len(tipos) == 1 else (chave, None)


def _operandos(nome: str, palavras, valores: str, ps: bool) -> tuple[list, list, bool, bool]:
    """(operandos na ordem, caminhos dados por opção, se o padrão veio por opção: `-e`, `-f`, `--regexp`, `--file`,
    `/c:`, `/g:`, e se uma opção longa fora da tabela, sem `=`, pode ter tomado um valor), sem as opções e os valores
    delas; depois de `--`, tudo é operando. Revisão 2 da rodada 4: as opções longas pela tabela do programa (_longa);
    a opção fora dela deixa a palavra seguinte como operando; no PowerShell, os parâmetros comuns com valor; o dígito
    no grupo de letras não o encerra."""
    posicionais, nomeados, por_opcao, incerta, k, fim = [], [], False, False, 0, False
    while k < len(palavras):
        texto, antiga = palavras[k]
        baixo, proxima = texto.casefold(), palavras[k + 1] if k + 1 < len(palavras) else None
        if fim or texto == "-" or not texto.startswith("-"):
            if not fim and _chave_do_windows(nome, texto, ps):
                for chave, valor in UMA_CHAVE.findall(texto):
                    por_opcao |= chave.casefold() in ("c", "g")
                    nomeados += [(d, d) for d in valor.split(";") if d] if chave.casefold() == "d" else []
            else:
                posicionais.append(palavras[k])
        elif texto == "--":
            fim = True
        elif texto.startswith("--"):
            chave, igual, _ = baixo[2:].partition("=")
            cheia, tipo = _longa(nome, chave)
            por_opcao |= tipo == "v" and cheia in ("regexp", "file")
            if tipo == "c" and igual:
                nomeados.append((texto.partition("=")[2], antiga.partition("=")[2]))
            elif tipo in ("c", "v") and proxima and not igual:
                nomeados += [proxima] if tipo == "c" else []
                k += 1
            elif tipo is None and not igual:
                incerta = True  # a palavra seguinte fica como operando; a pasta atual também conta (_percorre)
        elif ps:
            chave, dois, _ = baixo[1:].partition(":")
            if chave and any(p.startswith(chave) for p in PS_DE_CAMINHO):
                if dois:
                    nomeados.append((texto.partition(":")[2], antiga.partition(":")[2]))
                elif proxima:
                    nomeados.append(proxima)
                    k += 1
            elif chave and (chave in PS_COM_VALOR_EXATO or any(p.startswith(chave) for p in PS_COM_VALOR)) and (
                    not dois and proxima):
                k += 1
        else:
            for j, letra in enumerate(texto[1:], 1):
                if letra in valores:
                    por_opcao |= letra in "ef"
                    k += 1 if j == len(texto) - 1 and proxima else 0
                    break
                if not (letra.isalpha() or letra.isdigit()):
                    break
        k += 1
    return posicionais, nomeados, por_opcao, incerta


def _resolver(texto: str, base, pai: bool = False) -> list[str] | None:
    """O alvo em partes, relativo à `base`; `~` e `$HOME` expandidos, `$PWD` e `~+` são a pasta atual; com `pai`, o
    curinga no último nome vale pela pasta dele. None se não dá para saber (outra variável, `~-`, `~nome`, relativo sem
    pasta). No Windows, caminho de rede ou de dispositivo sem unidade (`\\\\srv\\c`) vira ['//']: não se sabe aonde
    chega."""
    m = CASA.match(texto) or PASTA_DA_VEZ.match(texto)
    if not m and texto.startswith("~"):  # `~-` (a pasta anterior), `~nome` (a casa de outra conta): revisão 1, rodada 4
        return None
    t = ((os.path.expanduser("~") if m.re is CASA else ".") + texto[m.end():]) if m else texto
    if "$" in t or re.search(r"%[^%\s]+%", t):
        return None
    t = DISPOSITIVO.sub("", t.replace("\\", "/"), count=1)
    if pai:
        cabeca, barra, ultimo = t.rstrip("/").rpartition("/")
        if CURINGA.search(ultimo):
            t = (cabeca or "/") if barra else "."
    if os.name == "nt" and t.startswith("//"):
        return ["//"]
    if t.startswith("/") or UNIDADE.match(t):
        return _partes(t)
    return _partes(t, base) if base is not None else None


def _cobre(partes: list[str], alvo: list[str]) -> str | None:
    """'tudo' se as partes (com curinga) casam o alvo inteiro ou o passam com `**`; 'acima' se casam um começo dele."""
    for i, comp in enumerate(partes):
        if "**" in comp:
            return "tudo"
        if i >= len(alvo) or not _casa(comp, alvo[i], None):
            return None
    return "tudo" if len(partes) == len(alvo) else "acima"


def _alcance(partes: list[str], ctx: _Contexto) -> tuple[str, int] | None:
    """Se a pasta (com curinga) é projects/ da raiz (todos os projetos), a raiz ou uma pasta acima dela: o rótulo e a
    quantos níveis abaixo dela começa o conteúdo de um projeto (0 com `**`; revisão 1 da rodada 4)."""
    if partes == ["//"]:
        return "um caminho de rede ou de dispositivo (não se sabe se chega à raiz)", 0
    fundo = any("**" in c for c in partes)
    for forma in ctx.formas:
        if _cobre(partes, forma + ["projects"]) == "tudo":
            return TODOS, 0 if fundo else 2
        cobre = _cobre(partes, forma)
        if cobre == "tudo":
            return "a raiz", 0 if fundo else 3
        if cobre:
            return "uma pasta acima da raiz", 0 if fundo else 3 + len(forma) - len(partes)
    return None


def _sem_nome(texto: str, partes, ctx: _Contexto) -> bool:
    """`projects` sem nome de projeto no fim do caminho (com ou sem barra), fora do caminho do próprio projeto e do da
    raiz: conta como todos os projetos (HOOK-F3), como a CITACAO conta `projects/<x>`."""
    comps = [c for c in texto.replace("\\", "/").split("/") if c not in ("", ".")]
    if not comps or comps[-1].rstrip(" .").casefold() != "projects":
        return False
    antes = "/".join(comps[:-1]).casefold()
    if ctx.projeto and re.search(r"(?:^|/)projects/" + re.escape(ctx.projeto) + r"[ .]*(?:/|\Z)", antes):
        return False
    return partes is None or not any(_cobre(partes, forma) for forma in ctx.formas)


def _motivo_do_alvo(partes, texto: str | None, ctx: _Contexto, profundidade, acao: bool, poda: bool) -> str | None:
    """O que o alvo alcança e o comando percorre: outro projeto; projects/ inteira, a raiz ou acima dela — salvo a
    poda dos modelos com o alvo na raiz e a descida (`profundidade`) que não chega ao conteúdo de um projeto (com
    `acao`, como o `-exec`, um nível a menos). Revisão 1 da rodada 4."""
    outro = _em_outro(partes, ctx) if partes is not None and partes != ["//"] else None
    if outro:
        return f"outro projeto (projects/{outro[:60]})"
    alcance = _alcance(partes, ctx) if partes is not None else None
    if alcance is None and texto is not None and _sem_nome(texto, partes, ctx):
        alcance = (TODOS, 2)
    if alcance is None or (poda and alcance[0] == "a raiz"):
        return None
    if profundidade is not None and profundidade < alcance[1] - (1 if acao else 0):
        return None
    return alcance[0]


def _checar(nome: str, alvos, implicito: bool, bases, ctx: _Contexto, pai: bool, profundidade: int | None = None,
            acao: bool = False, poda: bool = False) -> str | None:
    """O alvo (cada leitura, a partir de cada pasta) que alcança projects/ inteira, a raiz, acima dela ou outro
    projeto; sem alvo, a pasta atual (_motivo_do_alvo)."""
    dica = f"restrinja o caminho a projects/{ctx.p or '<projeto>'}/ (ou a uma pasta fora de projects/ e de state/)"
    for palavra in alvos:
        for texto in dict.fromkeys(palavra):
            for base in (bases or [None]) if texto and not URL_DE_REDE.match(texto) else ():
                ctx.gastar(len(texto) + 8)
                motivo = _motivo_do_alvo(_resolver(texto, base, pai), texto, ctx, profundidade, acao, poda)
                if motivo:
                    return f"o comando percorre {motivo} ({nome} em '{texto[:60]}'); {dica}"
    for base in bases if implicito else ():
        ctx.gastar(8)
        motivo = _motivo_do_alvo(base, None, ctx, profundidade, acao, poda)
        if motivo:
            return f"o comando percorre {motivo} ({nome} sem caminho, na pasta atual); {dica}"
    return None


def _junta(textos: list[str], ps: bool) -> str:
    """As palavras de volta num texto de comando (`cmd /c dir /s X`, `bash -c grep -r x /`), com aspas onde há
    espaço."""
    def cita(t: str) -> str:
        if not any(c.isspace() for c in t):
            return t
        return "'" + t.replace("'", "''" if ps else "'\\''") + "'"
    return " ".join(cita(t) for t in textos)


def _percorre(palavras, ctx: _Contexto, bases, possiveis, powershell: bool, prof: int, cano=None, escrito=()):
    """HOOK-F3: (motivo, efeito) do comando simples. Efeito: _SEM_CD; ("cd", pastas) ou ("empilha", pastas), uma por
    pasta possível (com a de antes e None quando o destino não se sabe); ("desempilha",) e, desde a revisão 2 da rodada
    4, ("desempilha?",), ("tira",) e ("empilha -n", pastas) (_volta, _saida). `cano`: o que o comando anterior do
    PowerShell manda pelo `|` (_cano). `escrito`: o texto que entra pela entrada padrão (here-string, o comando
    anterior do cano), que o lançador lê como comando e o `. /dev/stdin` roda no shell atual (revisão 2 da rodada 4)."""
    if escrito and len(palavras) > 1 and palavras[0][0] in (".", "source") and palavras[1][0] in ENTRADA_PADRAO:
        destinos = []
        for texto in escrito:
            motivo, final = _aninhado(texto, False, ctx, prof, possiveis)
            if motivo:
                return motivo, _SEM_CD
            destinos = _uniao(destinos, final)
        return None, ("cd", destinos)
    k, pasta, texto_s, depois = _partida(palavras)
    if pasta is not None:  # `env -C <pasta>`, `sudo -D <pasta>`: o comando roda nela (revisão 2 da rodada 4)
        motivo = _entra_em_projects(pasta, bases, ctx, palavras[0][0])
        if motivo:
            return motivo, _SEM_CD
        bases = possiveis = [p for b in bases or [None] for p in [_resolver(pasta[0], b)] if p is not None] or [None]
        for palavra in palavras[depois:]:
            motivo = _palavra(palavra, bases, ctx, powershell)
            if motivo:
                return motivo, _SEM_CD
    if texto_s is not None:  # `env -S '...'`: o texto vira as palavras do comando (revisão 2 da rodada 4)
        resto = _junta([w[0] for w in palavras[depois:]], False)
        return _aninhado(f"{texto_s} {resto}", False, ctx, prof, possiveis)[0], _SEM_CD
    if k is None:
        return None, _SEM_CD
    nome, resto = _nome(palavras[k]), palavras[k + 1:]
    textos = [w[0] for w in resto]
    if nome in VOLTAS:
        return None, _volta(textos, ctx, powershell)
    if nome in SAIDAS:
        motivo, efeito = _saida(nome, resto, ctx, bases, possiveis, powershell)
        return motivo, (_SEM_CD if pasta is not None else efeito)
    if nome in LANCADORES or nome in LANCADORES_PS:
        return _lancador(nome, textos, ctx, possiveis, prof, escrito, powershell)
    if nome == "find":
        return _find(textos, resto, ctx, bases, possiveis, powershell, prof), _SEM_CD
    if nome == "git":
        return _git(textos, resto, ctx, bases), _SEM_CD
    if nome in ("tar", "bsdtar"):
        return _tar(resto, ctx, bases), _SEM_CD
    if nome not in PERCORRE:
        return None, _SEM_CD
    curtas, valores, com_padrao, implicito = PERCORRE[nome]
    ps = powershell or nome in SO_POWERSHELL
    if curtas and not _recursivo(nome, textos, curtas, valores, ps):
        return None, _SEM_CD
    posicionais, nomeados, por_opcao, incerta = _operandos(nome, resto, valores, ps)
    if com_padrao and not por_opcao and not (nome == "rg" and "--files" in textos):
        posicionais = posicionais[1:]
    extras = []
    if ps and nome in LISTAGENS_PS:  # o 2º é o -Filter; depois, o valor de um parâmetro que o guarda não conhece
        posicionais, extras = posicionais[:1], posicionais[1:]  # (revisão 2 da rodada 4: todos são conferidos)
    elif nome == "robocopy":
        posicionais = posicionais[:2]  # depois vêm os filtros de nome
    alvos, pai = posicionais + nomeados, ps or nome in CURINGA_PROPRIO
    if ps:  # a lista do PowerShell com vírgula: um alvo por item (revisão 2 da rodada 4)
        alvos, extras = _virgulas(alvos), _virgulas(extras)
    if not alvos and powershell and cano is not None and nome in RECEBE_DO_CANO:  # recebe as pastas pelo cano
        if cano is DESCONHECIDA:
            return (f"o {palavras[k][0]} recursivo recebe pelo cano (`|`) pastas que o guarda não acompanha: dê o "
                    "caminho (-LiteralPath) ou use a poda dos modelos (Get-ChildItem -LiteralPath <raiz> | "
                    "Where-Object Name -notin 'projects','state' | ...)"), _SEM_CD
        return _checar(nome, cano[0], False, cano[1], ctx, pai, None, False, cano[2] and cano[3]), _SEM_CD
    poda = nome in GREPS and _poda_do_grep(textos)
    profundidade = _profundidade(nome, textos, ps)
    motivo = _checar(nome, alvos, implicito and (not alvos or incerta), bases, ctx, pai, profundidade, False, poda)
    return motivo or _checar(nome, extras, False, bases, ctx, False, profundidade, False, poda), _SEM_CD


def _virgulas(palavras) -> list:
    """No PowerShell, a lista com vírgula (`.,..`, `minutas,..`): um item por palavra, nas duas leituras (revisão 2 da
    rodada 4)."""
    res = []
    for shell, antiga in palavras:
        if "," not in shell and "," not in antiga:
            res.append((shell, antiga))
            continue
        a, b = shell.split(","), antiga.split(",")
        res += list(zip(a, b)) if len(a) == len(b) else [(x, x) for x in a + b]
    return [p for p in res if p[0] or p[1]]


def _entra_em_projects(alvo: tuple[str, str], bases, ctx: _Contexto, nome: str) -> str | None:
    """A pasta de destino (do cd, do `env -C`) que é projects/ da raiz: todos os projetos."""
    for texto in dict.fromkeys(alvo):
        for base in bases or [None]:
            partes = _resolver(texto, base)
            if (partes is not None and (_alcance(partes, ctx) or ("",))[0] == TODOS) or _sem_nome(texto, partes, ctx):
                return f"o comando entra em projects/, a pasta de {TODOS} ({nome} {texto[:60]})"
    return None


def _volta(textos: list[str], ctx: _Contexto, powershell: bool) -> tuple:
    """popd e Pop-Location: volta à pasta que o pushd guardou ("desempilha",). Revisão 2 da rodada 4: `popd -n` só tira
    da pilha ("tira",); `popd +N`/`-N` e o popd depois de redefinir um cd ficam onde estão ou vão à do topo
    ("desempilha?",)."""
    if ctx.cd_incerto:
        return ("desempilha?",)
    if not powershell and any(t.startswith("-") and not t.startswith("--") and "n" in t[1:] for t in textos):
        return ("tira",)
    if any(re.fullmatch(r"[+-]\d+", t) for t in textos):
        return ("desempilha?",)
    return ("desempilha",)


def _saida(nome: str, resto, ctx: _Contexto, bases, possiveis, powershell: bool):
    """cd, pushd, Set-Location e Push-Location: nega a entrada em projects/ (todos os projetos); o efeito é a pasta de
    destino a partir de cada possível — a de antes e uma desconhecida quando o destino não se sabe (`$X`, `$(pwd)`,
    `cd -`, `~-`) ou passa de 128 níveis (revisão 1 da rodada 4: antes, a pasta real se perdia no `&&`). Revisão 2 da
    rodada 4: `pushd -n X` não muda a pasta, só empilha X; depois de uma função ou alias com o nome de um cd
    (_redefine), o destino não se sabe: o de sempre (ela pode chamar o `builtin cd`), a de antes e uma desconhecida."""
    alvo = _alvo_da_saida(nome, resto, powershell)
    motivo = _entra_em_projects(alvo, bases, ctx, nome) if alvo else None
    if motivo:
        return motivo, _SEM_CD
    novas = []
    for pasta in possiveis:
        destino = _resolver(alvo[0], pasta) if alvo is not None else None
        sabido = destino is not None and len(destino) <= 128
        novas += ([destino] if sabido else []) + ([pasta, None] if ctx.cd_incerto or not sabido else [])
    if nome == "pushd" and not powershell and "-n" in [w[0] for w in resto] and not ctx.cd_incerto:
        return None, ("empilha -n", _uniao([], novas))
    return None, ("empilha" if nome in EMPILHAM else "cd", _uniao([], novas))


def _alvo_da_saida(nome: str, resto, ps: bool) -> tuple[str, str] | None:
    """A pasta de destino do cd/pushd/Set-Location (as duas leituras), depois das opções (`-P`, `--`, `-Path`,
    `-LiteralPath:X`, `-StackName x`); None se não se sabe aonde vai: `cd -`, `pushd +1`, `pushd` e `Set-Location` sem
    caminho. `cd` sozinho, no Bash, vai para a casa."""
    k = 0
    while k < len(resto):
        palavra, texto = resto[k], resto[k][0]
        if texto in ("-", "+") or (nome in EMPILHAM and re.fullmatch(r"[+-]\d+", texto)):
            return None
        if ps and texto.startswith("-"):
            chave, dois, _ = texto[1:].casefold().partition(":")
            if chave and ("literalpath".startswith(chave) or chave in ("pspath", "lp")
                          or (len(chave) >= 3 and "path".startswith(chave))):
                if dois:
                    return texto.partition(":")[2], palavra[1].partition(":")[2]
                return resto[k + 1] if k + 1 < len(resto) else None
            k += 2 if chave and "stackname".startswith(chave) and not dois else 1
        elif texto == "--":
            return resto[k + 1] if k + 1 < len(resto) else (("~", "~") if nome in ("cd", "chdir") else None)
        elif texto.startswith("-"):
            k += 1
        else:
            return palavra
    return ("~", "~") if not ps and nome in ("cd", "chdir") else None


def _lancador(nome: str, textos: list[str], ctx: _Contexto, possiveis, prof: int, escrito=(), lista: bool = False):
    """O comando dentro de outro (`bash -c`, `eval`, `powershell -Command`, `cmd /c`, `iex`): cada texto com espaço e o
    resto junto, analisados como comando um nível abaixo (no `cmd`, também sem o `^`, que escapa). O `eval` (as
    palavras juntadas com espaço, como ele faz) e o `Invoke-Expression` rodam no shell atual: o `cd` de dentro vale
    para o que vem depois (revisão 1 da rodada 4: `eval cd <raiz> && grep -r x .`). Revisão 2 da rodada 4: o texto que
    entra pela entrada padrão (`escrito`: here-string, o comando anterior do cano) também, quando o lançador o lê como
    comando (_le_a_entrada: `bash <<< 'grep -r x ..'` passava); o `-WorkingDirectory` do pwsh é a pasta do texto; com
    `lista` (a linha é do PowerShell), cada item de uma lista com vírgula também (`Start-Process powershell
    -ArgumentList '-c','gci -r ..'`)."""
    j, modo, no_atual, pasta = 0, nome in LANCADORES_PS, nome in NO_SHELL_ATUAL, None
    while j < len(textos) and (textos[j].startswith("-") or CHAVE_CMD.match(textos[j])):
        if textos[j].casefold() in ("-workingdirectory", "-wd") and j + 1 < len(textos):
            pasta = textos[j + 1]
        j += 2 if textos[j].casefold() in PS_OPCOES_COM_VALOR else 1
    dentro = [t for t in textos[j:] if any(c.isspace() or c in ";|&()<>`{}" for c in t)]
    if no_atual and textos[j:]:
        dentro.append(" ".join(textos[j:]))
    elif len(textos) - j > 1:
        dentro.append(_junta(textos[j:], modo))
    if escrito and _le_a_entrada(nome, textos, j):
        dentro += list(escrito) + ([" ".join(escrito)] if len(escrito) > 1 else [])
    if lista:
        dentro += [p for t in textos if "," in t for p in t.split(",")
                   if any(c.isspace() or c in ";|&()<>`{}" for c in p)]
    if nome == "cmd":
        dentro += [re.sub(r"\^(.)", r"\1", t) for t in dentro if "^" in t]
    if pasta is not None:
        motivo = _entra_em_projects((pasta, pasta), [p for p in possiveis if p is not None], ctx, nome)
        if motivo:
            return motivo, _SEM_CD
        possiveis = [r for p in possiveis for r in [_resolver(pasta, p)] if r is not None] or [None]
    destinos = []
    for texto in dict.fromkeys(dentro):
        motivo, final = _aninhado(texto, modo, ctx, prof, possiveis)
        if motivo:
            return motivo, _SEM_CD
        destinos = _uniao(destinos, final) if no_atual and final != possiveis else destinos
    return None, (("cd", destinos) if destinos else _SEM_CD)


def _le_a_entrada(nome: str, textos: list[str], j: int) -> bool:
    """O lançador lê o comando da entrada padrão (revisão 2 da rodada 4): bash, sh... sem `-c` e sem script (ou com
    `-s`), su e runuser sem `-c`; powershell, pwsh, cmd e iex sem texto de comando; o `eval` não lê."""
    if nome == "eval":
        return False
    if nome in LANCADORES_PS:
        return not textos[j:]
    curtas = "".join(t[1:] for t in textos[:j] if t.startswith("-") and not t.startswith("--"))
    return "c" not in curtas and (nome in ("su", "runuser") or not textos[j:] or "s" in curtas)


def _find(textos, resto, ctx: _Contexto, bases, possiveis, powershell: bool, prof: int) -> str | None:
    """find: os caminhos antes da expressão (depois de `-H`, `-L`, `-P`, `-D x`, `-Ox` e `--`), com o `-maxdepth` e a
    poda dos modelos; o comando do `-exec` é conferido também, um nível de aninhamento abaixo (revisão 1 da rodada 4:
    `find . -exec find . -exec ...` custava o quadrado do tamanho e estourava a pilha). Revisão 2 da rodada 4: o `{}`
    do `-exec` vira cada ponto de partida (o próprio é achado), e o comando é analisado inteiro, sem o desconto do
    `-maxdepth` nem a poda, que ele não respeita (`find .. -maxdepth 0 -exec grep -r x {} +` lia todos os projetos);
    no `-execdir`, ele roda na pasta de cada achado: a do ponto de partida e a de cima dele (como o find a escreve:
    `find ../.. -execdir` roda em `..`). Revisão 3 da rodada 4 (HOOK-F3): o `{}` vira o TEXTO do ponto de partida como
    foi escrito (`.`, `..`, `minutas`; as duas leituras), não o absoluto resolvido — o `{}` do find é sempre um caminho
    a partir do ponto de partida, nunca um irmão dele, então `find . -exec mv {} {}.bak` não cita `projects/<p>.bak`
    (regressão de uso normal na pasta do próprio projeto); no `-execdir`, `./` mais o último nome do ponto de partida,
    analisado a partir das pastas de cima (como o find a escreve: `find . -execdir ... {}` dá `./.`)."""
    j = 0
    while j < len(textos) and (textos[j] in ("-H", "-L", "-P", "-D") or textos[j].startswith("-O")):
        j += 2 if textos[j] == "-D" else 1
    j += 1 if j < len(textos) and textos[j] == "--" else 0
    caminhos = []
    while j < len(textos) and not textos[j].startswith(("-", "(", "!", ")", ",")):
        caminhos.append(resto[j])
        j += 1
    expressao = textos[j:]
    motivo = _checar("find", caminhos, not caminhos, bases, ctx, False, _maxdepth(expressao),
                     any(t in ACOES_DO_FIND for t in expressao), _poda_do_find(expressao))
    pontos = caminhos or [(".", ".")]  # as duas leituras de cada ponto de partida (revisão 3 da rodada 4)
    partidas = [r for b in bases or [None] for c in pontos
                for r in [_resolver(c[0].replace("\\", "/"), b)] if r is not None and r != ["//"]]
    while not motivo and j < len(textos):
        if textos[j] in ("-exec", "-execdir", "-ok", "-okdir"):
            if prof >= 3:
                return ANINHADO
            fim = next((x for x in range(j + 1, len(textos)) if textos[x] in (";", "+")), len(textos))
            if textos[j] in ("-execdir", "-okdir"):  # `./` + o último nome do ponto de partida (revisão 3 da rodada 4)
                trocas = [("./" + (posixpath.basename(a.replace("\\", "/").rstrip("/")) or "."),
                           "./" + (posixpath.basename(b.replace("\\", "/").rstrip("/")) or ".")) for a, b in pontos]
                de_cima = [posixpath.dirname(c[0].replace("\\", "/").rstrip("/")) for c in pontos]
                pastas = _uniao([], partidas + [r for base in bases or [None] for c in de_cima
                                                for r in [_resolver(c or ".", base)] if r is not None])
            else:  # `-exec`/`-ok`: o `{}` é o texto do ponto de partida como foi escrito (revisão 3 da rodada 4)
                trocas, pastas = pontos, possiveis
            palavras = []
            for w in resto[j + 1:fim]:
                tem = "{}" in w[0] or "{}" in w[1]
                ctx.gastar(len(w[0]) + len(w[1]) + (sum(2 * (len(a) + len(b)) for a, b in trocas) if tem else 0))
                palavras += [(w[0].replace("{}", a), w[1].replace("{}", b)) for a, b in trocas] if tem else [w]
            motivo = _analisar([_Simples(palavras, ";", [], [])], ctx, powershell, prof + 1, pastas or possiveis)[0]
            j = fim
        j += 1
    return motivo


def _maxdepth(expressao: list[str]) -> int | None:
    """O `-maxdepth` do find (o maior, se repetido); None sem ele ou com valor que não é número."""
    valores = [expressao[k + 1] for k, t in enumerate(expressao[:-1]) if t == "-maxdepth"]
    return max(int(v) for v in valores) if valores and all(v.isdigit() for v in valores) else None


def _poda_do_find(expressao: list[str]) -> bool:
    """A poda dos modelos de auditoria e revisão: `[-type d] \\( -name projects -o -name state \\) -prune -o ...` — a
    ordem dos nomes, `-iname`, `-or`, `-a` e `-maxdepth`/`-mindepth`/`-xdev` antes à vontade; sem `-depth` nem
    `-delete`, que anulam o `-prune` (revisão 1 da rodada 4)."""
    t = list(expressao)
    if "-depth" in t or "-d" in t or "-delete" in t:
        return False
    i = 0
    while i < len(t) and t[i] in ("-maxdepth", "-mindepth", "-xdev", "-mount", "-noleaf"):
        i += 2 if t[i] in ("-maxdepth", "-mindepth") else 1

    def pula(*opcoes: str) -> bool:
        nonlocal i
        if i < len(t) and t[i] in opcoes:
            i += 1
            return True
        return False

    if t[i:i + 2] == ["-type", "d"]:
        i += 2
        pula("-a", "-and")
    if not pula("("):
        return False
    nomes = []
    for vez in (0, 1):
        if (vez and not pula("-o", "-or")) or t[i:i + 1] not in (["-name"], ["-iname"]) or i + 1 >= len(t):
            return False
        nomes.append(t[i + 1] if t[i] == "-name" else t[i + 1].casefold())
        i += 2
    if not pula(")"):
        return False
    pula("-a", "-and")
    return sorted(nomes) == ["projects", "state"] and pula("-prune") and pula("-o", "-or")


def _poda_do_grep(textos: list[str]) -> bool:
    """`--exclude-dir` que casa `projects` e `state` (a forma dos modelos; revisão 1 da rodada 4)."""
    valores = [t.partition("=")[2] for t in textos if t.startswith("--exclude-dir=")]
    valores += [textos[k + 1] for k, t in enumerate(textos[:-1]) if t == "--exclude-dir"]
    return all(any(fnmatch.fnmatchcase(nome, v) for v in valores) for nome in ("projects", "state"))


def _git(textos, resto, ctx: _Contexto, bases) -> str | None:
    """`git grep` (`-C <pasta>` também é alvo) e `git diff --no-index` (revisão 1 da rodada 4), que percorrem
    pastas. Revisão 2 da rodada 4: todo `git diff` com caminhos (com um deles fora do repositório, o git compara as
    pastas sozinho, sem `--no-index`), e os caminhos valem a partir do `-C`. Revisão 3 da rodada 4: o `-C <pasta>` é
    alvo só no `git grep` (que busca nela inteira); no `git diff` ele é só a base dos caminhos, que confere os
    posicionais e os nomeados — `git -C <raiz> diff --stat` e `git -C <raiz> diff HEAD~1 -- RETOMADA.md` seguem, e o
    modelo da auditoria roda o git assim (`git ... -C <pasta>`)."""
    j, pasta = 0, []
    while j < len(textos) and textos[j].startswith("-"):
        if textos[j] in ("-C", "-c", "--git-dir", "--work-tree", "--namespace") and j + 1 < len(textos):
            pasta += [resto[j + 1]] if textos[j] == "-C" else []
            j += 1
        j += 1
    sub = textos[j].casefold() if j < len(textos) else ""
    if sub not in ("grep", "diff"):
        return None
    pastas = [r for b in bases or [None] for p in pasta for r in [_resolver(p[0], b)] if r is not None] or bases
    if sub == "grep":
        motivo = _checar("git grep", pasta, False, bases, ctx, False)  # `git grep -C <pasta>` busca na pasta inteira
        posicionais, nomeados, por_opcao, _ = _operandos("git", resto[j + 1:], "efABCmO", False)
        alvos = (posicionais if por_opcao else posicionais[1:]) + nomeados
        return motivo or _checar("git grep", alvos, not alvos, pastas, ctx, False)
    posicionais, nomeados, _, _ = _operandos("git", resto[j + 1:], "", False)
    return _checar("git diff", posicionais + nomeados, False, pastas, ctx, False)


def _tar(resto, ctx: _Contexto, bases) -> str | None:
    """tar: `-C <pasta>` (`-C<pasta>`, `--directory[=]<pasta>`, o `C` de um grupo de letras) muda a pasta dos operandos
    seguintes (revisão 1 da rodada 4: `tar czf x.tgz -C .. <projeto>` é o próprio projeto); o valor das letras que
    levam valor (`f`, `T`, `X`...) não é operando; sem operando depois do último `-C`, a pasta dele é o alvo (a
    extração grava nela). O valor de opção longa sem `=` fica como operando (conservador). Revisão 2 da rodada 4: o
    `--directory` pelo começo do nome (`--dir=..`), como o getopt_long."""
    grupos, operandos, pastas, fila, ultima = [], [], bases, [], None

    def muda(palavra: tuple[str, str]) -> None:  # mais funda que 128 não se acompanha (prazo), como no cd
        nonlocal operandos, pastas, ultima
        grupos.append((operandos, pastas))
        ultima, operandos = (palavra, pastas), []
        pastas = [p for b in (pastas or [None]) for p in [_resolver(palavra[0], b)] if p is not None and len(p) <= 128]

    k = 0
    while k < len(resto):
        palavra, texto = resto[k], resto[k][0]
        k += 1
        if fila:
            if fila.pop(0) == "C":
                muda(palavra)
        elif texto == "--":
            operandos += resto[k:]
            break
        elif texto.startswith("--"):
            chave, igual, valor = texto[2:].partition("=")
            diretorio = len(chave) >= 3 and "directory".startswith(chave)
            if diretorio and igual:
                muda((valor, palavra[1].partition("=")[2]))
            elif diretorio:
                fila.append("C")
        elif (texto.startswith("-") and len(texto) > 1) or (k == 1 and texto.isalpha()):
            antigo, letras = not texto.startswith("-"), texto.lstrip("-")
            for j, letra in enumerate(letras):
                if letra not in TAR_COM_VALOR:
                    continue
                if antigo:  # estilo antigo (`czf x.tgz`): cada letra que leva valor toma a próxima palavra
                    fila.append(letra)
                    continue
                if j + 1 < len(letras):  # `-Cpasta`, `-fx.tgz`: o resto do grupo é o valor
                    if letra == "C":
                        muda((letras[j + 1:], palavra[1][j + 2:]))
                else:
                    fila.append(letra)
                break
        else:
            operandos.append(palavra)
    grupos.append((operandos, pastas))
    for alvos, pastas_do_grupo in grupos:
        motivo = _checar("tar", alvos, False, pastas_do_grupo, ctx, False)
        if motivo:
            return motivo
    return _checar("tar -C", [ultima[0]], False, ultima[1], ctx, False) if ultima and not operandos else None


def _profundidade(nome: str, textos: list[str], ps: bool) -> int | None:
    """Até onde o comando desce (a pasta dada é 0, os filhos 1, como o `-maxdepth` do find): o `-Depth` do
    Get-ChildItem mais 1 e o `-L` do tree; None sem limite (revisão 1 da rodada 4)."""
    valores = []
    for k, texto in enumerate(textos):
        proximo = textos[k + 1] if k + 1 < len(textos) else ""
        if ps and nome in LISTAGENS_PS and texto.startswith("-"):
            chave, dois, valor = texto[1:].casefold().partition(":")
            if len(chave) >= 2 and "depth".startswith(chave):
                valor = valor if dois else proximo
                valores.append(int(valor) + 1 if valor.isdigit() else -1)
        elif nome == "tree" and texto == "-L":
            valores.append(int(proximo) if proximo.isdigit() else -1)
    return None if not valores or -1 in valores else max(valores)


def _cano(palavras, bases, anterior):
    """O que este comando do PowerShell manda pelo `|` ao seguinte (revisão 1 da rodada 4): Get-ChildItem dá os filhos
    das pastas dele e Get-Item a própria pasta — (alvos, pastas, poda, filhos); Where-Object, Sort-Object e
    Select-Object passam o que receberam (o Where-Object dos modelos, `Name -notin 'projects','state'`, poda); o resto,
    DESCONHECIDA."""
    if not palavras:
        return DESCONHECIDA
    nome = re.split(r"[\\/]", palavras[0][0])[-1].casefold()
    resto = palavras[1:]
    if nome in LISTAGENS_PS or nome in ITENS_PS:
        posicionais, nomeados, _, _ = _operandos("get-childitem", resto, "", True)
        return posicionais[:1] + nomeados or [(".", ".")], bases, False, nome in LISTAGENS_PS
    if anterior is None or anterior is DESCONHECIDA or nome not in FILTROS_PS | PASSAM_PS:
        return DESCONHECIDA
    if nome in FILTROS_PS:
        textos = [w[0].casefold() for w in resto]
        poda = (len(textos) >= 3 and textos[0] == "name" and textos[1] in ("-notin", "-inotin", "-cnotin")
                and sorted("".join(textos[2:]).split(",")) == ["projects", "state"])
        return anterior[0], anterior[1], anterior[2] or poda, anterior[3]
    return anterior


def decide(event: dict, env: dict) -> dict | None:
    tool = event.get("tool_name")
    if not isinstance(tool, str) or not tool:
        return deny("evento sem nome de ferramenta: negado por segurança")
    if tool not in SHELL_TOOLS:
        return None
    comando = str((event.get("tool_input") or {}).get("command", ""))
    if len(comando) > TETO_COMANDO:
        return deny(f"guarda_identidade (guarda-corpo): comando com mais de 16 KiB ({len(comando)} caracteres; o teto "
                    f"é {TETO_COMANDO}): negado, porque a conferência não caberia no prazo do perfil (revisão de "
                    "segurança da 1.7.10). Divida o comando ou grave o conteúdo com a ferramenta Write.")
    if env.get("FUNDACAO_PERMITIR_TROCA_IDENTIDADE") != "1" and _troca_identidade(comando):
        return deny("a identidade da fundação é definida pelo lançador, não pela sessão (FUNDACAO_PRINCIPAL)")
    motivo = outro_projeto(comando, env, event.get("cwd"), powershell=tool == "PowerShell")
    if motivo:
        return deny(f"guarda_identidade (guarda-corpo): {motivo}. Dado de outro projeto só pelo serviço da fundação "
                    "(python -m fundacao ...), com a identidade do lançador; se for uma pasta `projects/` dentro do "
                    "próprio projeto, cite-a pelo caminho do projeto ou use a ferramenta Read.")
    return None


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
