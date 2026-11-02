#!/usr/bin/env python3
"""Rastro do executor: comandos e caminhos das chamadas de ferramenta e o fato `acesso_ao_gabarito` (apoio de
verificar_execucoes.py, que também usa a leitura de comandos e caminhos nos acessos da E7/E9).

A leitura vem da estrutura (auditoria 1.5.0, achado 16), não de trecho de texto: cada uso de ferramenta da
transcrição (`trace.jsonl`) dá um nome (campo estruturado) e uma entrada; comando de shell é lido com shlex, em duas
leituras (escapes do bash e barras do Windows); caminho é comparado em forma canônica (caixa, barras, `.`, `..`,
pontos e espaços finais). Quando a ferramenta é Bash, só a leitura POSIX efetiva participa do fato de\ncontaminação; a alternativa Windows não cria alvos a partir dos escapes dela. Ferramentas não identificadas\ncontinuam conservando as duas leituras.\n[Decisão; harness2, P2] Acesso ao gabarito: leitura, listagem ou busca que alcance a bancada do avaliador, outra
raiz do gabarito (a árvore da skill com evals/, as skills dos braços, o livro), um nome do gabarito ou o
repositório público marca a execução "contaminada". Revisão de segurança da 1.7.7 (R177-VAL-06):
- os caminhos da própria execução saem do texto antes do teste de nome (numa árvore chamada como o repositório,
  quem só lê o próprio ambiente não é contaminado);
- a pasta de outra execução na área do executor (a cópia da skill do outro braço, as saídas dele) e a raiz da
  área contam;
- curinga conta pelo que pode alcançar, casado componente a componente com a bancada e as raízes do gabarito, e
  sempre que parte da área ou de cima dela; nome com curinga casa com os nomes do gabarito (com ao menos dois
  caracteres fixos além da extensão: `*.json` sozinho não basta);
- busca recursiva a partir da área ou de cima dela conta, como a que contém a bancada;
- `cd`/`Set-Location` muda a pasta de onde partem os caminhos relativos seguintes, e o destino é examinado.
Terceira passada da revisão (R177C-B-08): o prefixo de dispositivo do Windows (caminho longo, com `UNC` para a rede)
sai dos caminhos da execução e dos do rastro antes da comparação; antes, o `?` dele contava como curinga na raiz, e
todo caminho com o prefixo, até o do próprio ambiente, marcava a execução como contaminada.
Limite: variável, substituição de comando, expansão de nome de arquivo (o programa que vem do nome de um arquivo pelo
curinga), o que o shell transforma e o shlex não (a citação ANSI-C `$'…'` e a `$"…"` do bash, a expansão de chaves e a
continuação de linha fora das aspas; o acento grave do PowerShell fora das aspas simples; no PowerShell, a linha de
comando que o programa nativo relê: aspa e apóstrofo dentro do argumento e chave no argumento sem espaço, que o runtime
do MSYS2 do sed e do gawk do Git expande) e código de shell delegado não são resolvidos; envoltórios (env, xargs, nice,
timeout, busybox, find -exec) e eval não são lidos como o programa que rodam (o script fica entre os alvos, e o nome com
curinga conta pela regra de caminho); `exec`, como `command`, é prefixo. Leitura ilegível, shell delegado identificado,
script de sed ou awk com E/S (também na linha com aquelas transformações do shell e, no PowerShell, com argumento que o
programa nativo relê: o script conta como com E/S, e o nome com curinga nele pode dar contaminada), opção de awk que o
gawk e o mawk leem de modos diferentes ou cd dinâmico deixam o isolamento não medido (se houver acesso provado por nome
ou caminho absoluto, prevalece contaminada). O "não medido" é aviso, não barreira: só "contaminada" impede a aprovação.
O rastro é indício, não barreira (a barreira é a área fora do alcance e a web negada na própria chamada).
1.7.10 (seção 2 do escopo; a classe do P1, que a 1.7.9 corrigiu só no grep/rg):
- padrão ou script não é caminho também no sed (o primeiro não-opção, ou o valor de -e/--expression; o -f é
  arquivo), no awk/gawk (o primeiro não-opção, salvo com -f, -e/--source, -E/--exec ou -W exec, que leem o programa de
  arquivo), no Select-String (-Pattern ou o primeiro posicional; -Path e -LiteralPath, também na forma -Path:<x>, são
  caminho) e no findstr (as cadeias, ou /c:; /g: e /f: são arquivo); nesses, só o nome exato do gabarito conta, salvo
  no script de sed ou awk com E/S (abaixo, CI-F7);
- os valores de rg -g/--glob/--iglob e de grep --include/--exclude/--exclude-dir (e -Include/-Exclude do
  Select-String) são globs de nome: só o nome do gabarito conta, nunca caminho a partir da raiz;
- no Bash, argumento com uma barra invertida só no começo (`\\*.json`, `\\s*TODO`) é escape, não a raiz; a barra
  invertida sozinha continua sendo a raiz no Git Bash;
- F5: o cd dentro de `{ ...; }` vale para o shell (o grupo roda nele), salvo com pipe antes ou depois, `&` depois ou
  como corpo de função, quando a pasta fica incerta; o cd depois de outro prefixo (if, nohup...) continua incerto;
- grupo de opções curtas de qualquer tamanho (`-rnwiEHs`) é lido letra a letra: até a primeira letra que leva valor,
  e o resto é o valor; sed, awk e Select-String não percorrem pastas.
Revisão de segurança da 1.7.10 (CI-F7): script de sed ou awk que roda comando ou lê e grava arquivo — no awk,
system(), getline, print e printf com > >> | ou |&, @include, @load ou -l/--load, chamada indireta, ARGV e SYMTAB; no
sed, os comandos e, r, R, w e W e as opções e e w do s; a leitura está em scripts_do_rastro.py — volta à regra da 1.7.9
nos padrões do comando (nome com curinga conta, sem conferir caminho: a expressão continua sem ser caminho) e deixa o
isolamento não medido. Antes, `awk 'BEGIN{system("cat <acima>/bancad*/gabarito*")}'` saía sem acesso. Correções da
revisão 1: os programas vão na ordem da linha (os -e colados e separados do sed, como o sed os junta); a opção longa
vale pelo prefixo único, como no getopt_long (`--expr=`, `--sourc=`), também no -W do gawk e do mawk (`-W source=`,
`-We`); o nome com versão conta (`gawk-5.4.1`, do Git Bash). Programa lido de arquivo (-f) não é resolvido, como o de
`python script.py`. Correções da revisão 2: as opções curtas do gawk com valor opcional colado (-d, -D, -L, -o e -p)
levam o resto do grupo (em `gawk -pv 'prog'`, o programa é o argumento seguinte, não o valor de -v); as transformações
do shell são procuradas fora das aspas (antes, o `$'` contava em qualquer lugar, também no `'^$'` do grep, e o acento
grave dentro das aspas simples do PowerShell), e a lista ganhou a `$"…"`, as chaves, a continuação de linha e a
releitura do programa nativo no PowerShell; `exec` passou a prefixo; na linha do PowerShell, as aspas tipográficas são
lidas como as ASCII, como o PowerShell as lê (antes, `Get-Content ‘<bancada>/evals.json’` saía sem acesso).
"""
from __future__ import annotations

import fnmatch
import importlib.util
import json
import re
import shlex
import unicodedata
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("_isolamento_do_rastro", SKILL / "evals" / "isolamento.py")
iso = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(iso)
_spec = importlib.util.spec_from_file_location("_scripts_do_rastro", SKILL / "evals" / "scripts_do_rastro.py")
scripts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scripts)
_sed_com_es, _awk_com_es = scripts.sed_com_es, scripts.awk_com_es
CHAVE_DE_CAMINHO = re.compile(r"path|file|dir|glob|uri|url|target|source|dest", re.IGNORECASE)
BARRA_INVERTIDA = chr(92)
SEPARADORES = re.compile("[" + re.escape("/" + BARRA_INVERTIDA) + r"\s'\",;:()=+<>|&]+")
CURINGA, DINAMICO, CONTROLE = set("*?["), set("$%`{"), set(";&|()\n")
RECURSIVOS = {"rg", "find", "tree", "du", "robocopy", "xcopy", "tar", "zip", "7z", "rsync", "compress-archive"}
SHELLS_DELEGADOS = {"bash", "sh", "dash", "zsh", "ksh", "powershell", "pwsh", "cmd"}
MUDA_PASTA = {"cd", "chdir", "pushd", "set-location", "sl", "push-location"}
ABRE, FECHA = "(abre parêntese)", "(fecha parêntese)"  # marcas de _leituras; nenhum token do shlex as forma
CD_INCERTO = "(cd depois de prefixo)"  # marca de _leituras: cd dentro de chaves, de if ou depois de nohup
# O que o shell põe antes do programa. A receita do esqueleto grava a saída de `{ <comando>; }`: com o `{` no lugar
# do programa, `find` e `rg` não contavam como busca recursiva e a chamada ao serviço não era reconhecida
# (revalidacao-claude-20261025, pendência P1). O `exec` roda o programa no lugar do shell, como o `command` (revisão de
# segurança da 1.7.10, CI-F7, revisão 2: `exec awk 'BEGIN{system(…)}'` não era lido como awk).
PREFIXOS_DO_SHELL = {"{", "!", "if", "elif", "then", "else", "do", "while", "until", "time", "command", "builtin",
                     "nohup", "exec"}
# Programas cujo argumento pode ser padrão ou script (a classe do P1), por família. No GNU grep, o valor de --color é
# opcional e só vale com `=`; no rg, é obrigatório.
FAMILIAS = {**{p: "grep" for p in ("grep", "egrep", "fgrep", "zgrep")}, "rg": "rg", "sed": "sed", "gsed": "sed",
            **{p: "awk" for p in ("awk", "gawk", "mawk", "nawk", "original-awk", "goawk")}, "select-string": "sls",
            "sls": "sls", "findstr": "findstr"}
SEM_RECURSAO = {"sed", "awk", "sls"}  # não percorrem pastas: o -r do sed é a regex estendida
# Papel do valor de cada opção que leva valor: "padrao" (só o nome exato do gabarito conta), "glob" (glob de nome: só
# o nome do gabarito conta), "arquivo" e "valor" (conferidos como caminho, sem recursão). `curtas`: letra -> papel (o
# resto do grupo é o valor; sem resto, o próximo argumento); `explicitas`: com elas, o primeiro posicional não é o
# padrão; `opcionais`: letra cujo valor só vem colado (`-i.bak` do sed).
_CONTEXTO = dict.fromkeys(("--after-context", "--before-context", "--context", "--max-count"), "valor")
OPCOES = {
    "grep": {"curtas": {"e": "padrao", "f": "arquivo", **dict.fromkeys("ABCmdD", "valor")},
             "longas": {"--regexp": "padrao", "--file": "arquivo", "--include": "glob", "--exclude": "glob",
                        "--exclude-dir": "glob", "--exclude-from": "arquivo", **_CONTEXTO,
                        **dict.fromkeys(("--label", "--binary-files", "--devices", "--directories",
                                         "--group-separator"), "valor")},
             "explicitas": {"e", "f", "--regexp", "--file"}},
    "rg": {"curtas": {"e": "padrao", "f": "arquivo", "g": "glob", **dict.fromkeys("ABCmtTjMErd", "valor")},
           "longas": {"--regexp": "padrao", "--file": "arquivo", "--glob": "glob", "--iglob": "glob",
                      "--pre-glob": "glob", "--ignore-file": "arquivo", "--pre": "arquivo", **_CONTEXTO,
                      **dict.fromkeys(("--type", "--type-not", "--threads", "--max-columns", "--encoding", "--replace",
                                       "--max-depth", "--sort", "--sortr", "--type-add", "--max-filesize",
                                       "--path-separator", "--colors", "--color"), "valor")},
           "explicitas": {"e", "f", "--regexp", "--file"}},
    "sed": {"curtas": {"e": "programa", "f": "arquivo", "l": "valor"}, "opcionais": {"i"},
            "explicitas": {"e", "f", "--expression", "--file"}},
    "awk": {"curtas": {"f": "arquivo", "e": "programa", "F": "padrao", "v": "padrao", "i": "arquivo", "l": "arquivo",
                       "W": "valor", "E": "arquivo"},
            # -d, -D, -L, -o e -p do gawk: valor opcional, só colado, que leva o resto do grupo (`-pv`: o perfil vai
            # para o arquivo v, e o programa é o argumento seguinte; gawk --help do 5.4.1 e do 5.2.1; o mawk recusa
            # essas letras) (revisão de segurança da 1.7.10, CI-F7, revisão 2)
            "opcionais": set("dDLop"),
            "explicitas": {"f", "e", "E", "--file", "--source", "--exec"}},
}
# Opções longas do sed e do awk, todas (com e sem valor), porque o getopt_long aceita o prefixo único (`--expr=`,
# `--sourc=`); papel None: sem valor ou com valor opcional, que só vem colado. O -W do gawk é a opção longa; o do mawk
# leva as dele, também abreviadas e em lista com vírgulas (`-We arq`, `-W i,exec arq`). Sondado no GNU sed 4.9, no gawk
# 5.4.1 e 5.2.1 e no mawk 1.3.4 em 01/11/2026 (revisão de segurança da 1.7.10, CI-F7, revisão 1).
LONGAS = {
    "sed": {**dict.fromkeys(("binary", "debug", "follow-symlinks", "help", "in-place", "null-data", "posix", "quiet",
                             "regexp-extended", "sandbox", "separate", "silent", "unbuffered", "version",
                             "zero-terminated")),
            "expression": "programa", "file": "arquivo", "line-length": "valor"},
    "gawk": {**dict.fromkeys(("bignum", "characters-as-bytes", "copyright", "csv", "debug", "dump-variables",
                              "gen-pot", "help", "lint", "lint-old", "no-optimize", "non-decimal-data", "nostalgia",
                              "optimize", "persist", "posix", "pretty-print", "profile", "re-interval", "sandbox",
                              "trace", "traditional", "use-lc-numeric", "version")),
             "assign": "padrao", "exec": "arquivo", "field-separator": "padrao", "file": "arquivo",
             "include": "arquivo", "load": "arquivo", "source": "programa"},
    "mawk": {**dict.fromkeys(("compat", "dump", "help", "interactive", "posix", "random", "sprintf", "usage",
                              "version")), "exec": "arquivo"},
}
LISTA_DO_PAPEL = {"padrao": "padroes", "programa": "padroes", "glob": "globs", "arquivo": "valores",
                  "valor": "valores", "pasta": "pastas"}
# Select-String: parâmetros que levam valor (com o papel; "caminho" fica entre os alvos) e os apelidos.
PARAMETROS_SLS = {"pattern": "padrao", "path": "caminho", "literalpath": "caminho", "include": "glob",
                  "exclude": "glob", "context": "valor", "encoding": "valor", "culture": "valor",
                  "inputobject": "valor"}
CHAVES_SLS = ("simplematch", "casesensitive", "allmatches", "notmatch", "quiet", "list", "raw", "noemphasis")
APELIDOS_SLS = {"lp": "literalpath", "pspath": "literalpath"}
LETRAS_DO_FINDSTR = set("belrsixvnmopafcgd")
VALOR_DO_FINDSTR = {"c": "padrao", "g": "arquivo", "f": "arquivo", "d": "pasta", "a": "valor"}
# Cópia pública e árvore com evals/: o nome do repositório basta (está em toda URL dele); o dono não entra no texto,
# que vai para a cópia pública, cujo saneamento recusa o nome de usuário.
REPOSITORIO_PUBLICO = ("fundacao-ia-multiprojetos-skill",)
FERRAMENTAS_DE_WEB = ("WebFetch", "WebSearch")
ABSOLUTO = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/])")


# --------------------------------------------------------------------- leitura do rastro
def _usos_de_ferramenta(obj):
    if isinstance(obj, dict):
        if obj.get("type") == "tool_use" and "input" in obj:
            yield str(obj.get("name", "?")), obj["input"]
        for v in obj.values():
            yield from _usos_de_ferramenta(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _usos_de_ferramenta(v)


def _normal(palavra: str) -> str:
    """Componente de caminho na forma canônica do Windows: caixa e pontos/espaços finais não distinguem."""
    return unicodedata.normalize("NFC", palavra).lower().rstrip(" .")


def _palavras(texto: str) -> list[str]:
    """Componentes do texto: separados por barras, espaços, aspas e pontuação de código; '.' some."""
    return [p for p in SEPARADORES.split(texto) if p and p != "."]


def _programa(arg: str) -> str:
    nome = arg.replace(BARRA_INVERTIDA, "/").rsplit("/", 1)[-1].lower()
    return nome[:-4] if nome.endswith(".exe") else nome


def _sem_versao(nome: str) -> str:
    """O nome do programa sem a versão do fim (`gawk-5.4.1`, que o Git Bash traz, é o gawk; CI-F7, revisão 1)."""
    return nome if nome in FAMILIAS else re.sub(r"-?[0-9]+(?:\.[0-9]+)*$", "", nome)


def _familia(arg: str) -> str | None:
    return FAMILIAS.get(_sem_versao(_programa(arg)))


def _implementacao(arg: str) -> str | None:
    """sed, gawk ou mawk; "awk" quando o nome não diz qual (awk, nawk): valem as leituras do gawk e do mawk."""
    nome, familia = _sem_versao(_programa(arg)), _familia(arg)
    return nome if nome in ("gawk", "mawk") else familia


def _resolvida(tabela: dict, nome: str) -> str | None:
    """A opção longa pelo nome inteiro ou por um prefixo único, como no getopt_long; ambígua ou desconhecida: None."""
    if nome in tabela:
        return nome
    candidatas = [o for o in tabela if o.startswith(nome)] if nome else []
    return candidatas[0] if len(candidatas) == 1 else None


def _opcao_longa(implementacao: str, nome: str) -> tuple[str | None, str | None, bool]:
    """(opção, papel, incerta) da opção longa `nome` do sed ou do awk. No awk sem implementação conhecida, vale a
    leitura com papel (a mais conservadora); se o gawk e o mawk a leem de modos diferentes (`--i`: include no gawk,
    interactive no mawk), a opção fica incerta e o isolamento, não medido."""
    tabelas = ("gawk", "mawk") if implementacao == "awk" else (implementacao,)
    leituras = [(LONGAS[t][o], o) for t in tabelas if (o := _resolvida(LONGAS[t], nome)) is not None]
    com_papel = [(papel, opcao) for papel, opcao in leituras if papel is not None]
    if not com_papel:
        return (leituras[0][1] if leituras else None), None, False
    papel, opcao = com_papel[0]
    return opcao, papel, len({p for p, _ in leituras}) > 1


def _tokens(texto: str, *, posix: bool = True) -> list[str]:
    lex = shlex.shlex(texto, posix=posix, punctuation_chars=";&|()<>\n")
    lex.whitespace, lex.whitespace_split, lex.commenters = " \t\r", True, ""
    return list(lex)


def _leituras(comando: str) -> list[list[list[str]]]:
    """Comandos simples (argv) de cada leitura da linha, separados por ; & && || | ( ) e quebra de linha: como veio
    (escapes do bash) e com a barra invertida trocada por '/' (caminhos do Windows). Comentários NÃO são descartados
    (o texto depois de '#' também é examinado). Aspas sem par: a linha inteira vira um comando ilegível. Cada ( e )
    entra como a marca [ABRE] ou [FECHA], para a pasta corrente: no POSIX, o cd dentro de ( ) ou $( ) não vale depois
    do parêntese. Cada comando sai sem o que o shell põe antes do programa (`{`, `!`, `then`, `time`...); o cd
    depois de um desses prefixos sai marcado com [CD_INCERTO]."""
    leituras = []
    for texto in (comando, comando.replace(BARRA_INVERTIDA, "/")):
        try:
            tokens = _tokens(texto)
        except ValueError:
            if leituras and leituras[0] and leituras[0][0][0] != "(linha ilegível)":
                continue  # alternativa Windows invalida nao desfaz uma leitura Bash valida
            leituras.append([["(linha ilegível)", *texto.split()]])
            continue
        # Todo ( e ) separa comandos, inclusive o `\(` do find, que o shlex devolve como pontuação: dividir a expressão
        # do find perde a poda, mas tratar o parêntese do meio como palavra colava `$( … )` e o corpo de função ao
        # comando de fora (terceira revisão da R179-33). O lado conservador é dividir.
        itens, atual = [], []
        for tok in tokens:
            if tok and set(tok) <= CONTROLE:
                if atual:
                    itens.append(("comando", atual))
                atual = []
                itens.append(("controle", tok))
            else:
                atual.append(tok)
        if atual:
            itens.append(("comando", atual))
        grupos, comandos = _grupos(itens), []
        for i, (tipo, valor) in enumerate(itens):
            if tipo == "controle":
                comandos.extend([ABRE] if c == "(" else [FECHA] for c in valor if c in "()")
            else:
                _emitir(comandos, valor, any(inicio <= i <= fim and not efetivo for inicio, fim, efetivo in grupos))
        leituras.append(comandos)
    return leituras


def _pipe(controle: str) -> bool:
    return controle.strip() in ("|", "|&")


def _grupos(itens: list) -> list[tuple[int, int, bool]]:
    """(item que abre, item que fecha, efetivo) de cada grupo `{ ...; }` (F5, 1.7.10): o grupo roda no próprio shell —
    o cd dentro dele vale depois — salvo com pipe antes ou depois, `&` depois (segundo plano) ou como corpo de função
    (`f() { ...; }`); grupo sem o `}` fica incerto."""
    grupos, pilha = [], []
    for i, (tipo, valor) in enumerate(itens):
        if tipo != "comando":
            continue
        if valor[0] == "}" and pilha:
            inicio = pilha.pop()
            antes = itens[inicio - 1][1] if inicio and itens[inicio - 1][0] == "controle" else ""
            depois = itens[i + 1][1] if i + 1 < len(itens) and itens[i + 1][0] == "controle" else ""
            efetivo = not (_pipe(antes) or _pipe(depois) or depois.strip() == "&" or antes.endswith(")"))
            grupos.append((inicio, i, efetivo))
            continue
        for tok in valor:  # os `{` entre os prefixos abrem grupo
            if tok not in PREFIXOS_DO_SHELL:
                break
            if tok == "{":
                pilha.append(i)
    return grupos + [(inicio, len(itens), False) for inicio in pilha]


def _sem_prefixo(argv: list[str]) -> list[str]:
    """O comando sem `{`, `!`, palavras de if/while/for e `time`/`command`/`builtin`/`nohup`/`exec` antes do programa;
    um prefixo sozinho fica como veio. Atribuições (`NOME=valor`) ficam: a CLI da fundação as confere."""
    i = 0
    while i < len(argv) - 1 and argv[i] in PREFIXOS_DO_SHELL:
        i += 1
    return argv[i:]


def _emitir(comandos: list[list[str]], argv: list[str], grupo_incerto: bool = False) -> None:
    """Acrescenta o comando sem prefixo. O cd depois de prefixo que não seja `{` (`if cd X`, `nohup cd X`) ou dentro
    de grupo que não roda no shell (`{ cd X; } | head`, `f() { cd X; }`) vira [CD_INCERTO, ...]: a pasta fica incerta.
    O cd de `{ cd X; }` vale (F5, 1.7.10)."""
    limpo = _sem_prefixo(argv)
    so_chaves = all(t == "{" for t in argv[:len(argv) - len(limpo)])
    if _programa(limpo[0]) in MUDA_PASTA and (grupo_incerto or not so_chaves):
        comandos.append([CD_INCERTO, *limpo])
    else:
        comandos.append(limpo)


def _comandos_simples(comando: str) -> list[list[str]]:
    """Os comandos simples das duas leituras da linha (as duas contam), sem as marcas."""
    return [argv[1:] if argv[:1] == [CD_INCERTO] else argv
            for leitura in _leituras(comando) for argv in leitura if argv not in ([ABRE], [FECHA])]


def _letras(familia: str | None, a: str) -> tuple[str, str | None, str | None]:
    """Grupo curto de opções lido letra a letra (1.7.10; antes, só grupos de até 6 letras contavam): (letras sem valor,
    letra que leva valor ou None, valor colado ou None). Na família conhecida, a primeira letra que leva valor fica com
    o resto do grupo (`-A3r`: o 3r é o valor do -A); fora dela, todas as letras contam."""
    regra = OPCOES.get(familia or "", {})
    curtas, opcionais = regra.get("curtas", {}), regra.get("opcionais", set())
    letras = a[1:]
    for k, c in enumerate(letras):
        if c in curtas:
            return letras[:k], c, letras[k + 1:] or None
        if c in opcionais:
            return letras[:k + 1], None, None
    return letras, None, None


def _chaves_do_findstr(a: str) -> tuple[str, str | None] | None:
    """(letras, valor depois de `:`) de um argumento de opções do findstr (`/spin`, `/c:texto`), ou None."""
    m = re.fullmatch(r"[/-]([A-Za-z]+)(?::(.*))?", a, re.S)
    if not m or not (set(m[1].lower()) <= LETRAS_DO_FINDSTR or m[1].lower() in ("off", "offline")):
        return None
    return m[1].lower(), m[2]


def _recursivo(argv: list[str], powershell: bool = False) -> bool:
    """Programa recursivo ou opção de recursão. Fora do PowerShell, todo grupo curto de opções com r ou R (`-r`,
    `-rnE`, `-IR`, `-Hrn`, `-1R`, `-rnwiEHs`: letra a letra, em qualquer tamanho) e `-d recurse` do grep; o /s do
    findstr, também em grupo (`/spin`). No PowerShell, as regras antigas (grupos de até 5 letras com r minúsculo entre
    minúsculas ou com R) e `-Recurse`, para não tomar `-Force` nem `-Filter` por recursão — mas grep e rg sob o
    PowerShell seguem a leitura letra a letra, como fora dele (`grep -rnwiEHs`, 1.7.10). Sed, awk e Select-String não
    percorrem pastas (o -r do sed é a regex estendida)."""
    programa = _programa(argv[0])
    familia = _familia(argv[0])
    if programa in RECURSIVOS:
        return True
    if familia in SEM_RECURSAO:
        return False
    if familia == "findstr":
        return any((c := _chaves_do_findstr(a)) is not None and "s" in c[0] and c[0] not in ("off", "offline")
                   for a in argv[1:])
    so_maiusculo = programa == "ls" and not powershell  # no ls do POSIX, -r é ordem inversa; recursão é -R
    for j, a in enumerate(argv[1:], 1):
        if a in ("--recursive", "--directories=recurse", "-drecurse") or a.lower() in ("-recurse", "/s"):
            return True
        if a == "-R" or (a == "-r" and not so_maiusculo):
            return True
        if a in ("-d", "--directories") and argv[j + 1:j + 2] == ["recurse"]:
            return True
        if powershell and familia not in ("grep", "rg"):
            if re.fullmatch(r"-[a-z]{0,2}r[a-z]{0,2}", a) or re.fullmatch(r"-[a-zA-Z]{0,2}R[a-zA-Z]{0,2}", a):
                return True
        elif re.fullmatch(r"-[A-Za-z0-9]+", a):
            letras = _letras(familia, a)[0]
            if "R" in letras or ("r" in letras and not so_maiusculo):
                return True
    return False


OPCOES_DE_PASTA = {"--directory", "--dir", "--chdir", "--cwd", "--root", "--basedir", "--base-dir"}
# Parâmetros comuns do PowerShell que levam valor: no Set-Location, o valor deles não é o alvo.
PARAMETROS_COMUNS_PS = {"-erroraction", "-ea", "-errorvariable", "-ev", "-warningaction", "-wa", "-warningvariable",
                        "-wv", "-informationaction", "-infa", "-informationvariable", "-iv", "-outvariable", "-ov",
                        "-outbuffer", "-ob", "-pipelinevariable", "-pv", "-stackname"}


def _sem_parametros_comuns(args: list[str]) -> list[str]:
    """Os argumentos do Set-Location sem os parâmetros comuns que levam valor (`-ErrorAction SilentlyContinue`); com
    `-Path` ou `-LiteralPath`, só o valor dele."""
    saida, i = [], 0
    while i < len(args):
        nome = args[i].lower().split(":", 1)[0]
        if nome in ("-path", "-literalpath", "-lp", "-pspath") and ":" not in args[i] and i + 1 < len(args):
            return [args[i + 1]]
        if nome in PARAMETROS_COMUNS_PS:
            i += 1 if ":" in args[i] else 2
            continue
        saida.append(args[i])
        i += 1
    return saida


def _sem_redirecao(argv: list[str]) -> list[str]:
    """Os argumentos sem os redirecionamentos (`2>/dev/null`, `>&2`, `> arq`, `&>arq`): saem o operador, o número
    antes dele e o alvo depois. O alvo do cd é o último argumento que sobra."""
    saida, i = [], 0
    while i < len(argv):
        a = argv[i]
        if a and set(a) <= set("<>&"):
            if saida and saida[-1].isdigit():
                saida.pop()
            i += 2
            continue
        saida.append(a)
        i += 1
    return saida


def _papeis(argv: list[str]) -> dict:
    """O papel de cada argumento de um programa que busca texto ou roda script (grep, rg, sed, awk, Select-String e
    findstr): `padroes`, `globs`, `valores` e `pastas` (posições), `colados` ([papel, texto] de valor colado numa
    opção, que sai dos alvos: `consumidos`) e `sem_caminho` (nenhum caminho posicional). Padrão é o valor de
    -e/--regexp (no sed, -e/--expression; no awk, -e/--source, -F e -v) e, sem opção explícita, o primeiro posicional;
    o valor de -f/--file é arquivo lido e continua caminho. Antes, só grep e rg, e o padrão que começava por barra
    invertida valia como a raiz (P1 da fase revalidacao-claude-20261025; a classe inteira na 1.7.10). No sed e no awk,
    também `programas` ([posição, texto] do programa, para lê-los na ordem da linha), `extensao` (gawk com -l/--load) e
    `incerto` (opção que o gawk e o mawk leem de modos diferentes) (CI-F7, revisão 1)."""
    res = {"padroes": [], "globs": [], "valores": [], "pastas": [], "colados": [], "consumidos": set(),
           "sem_caminho": False, "programas": [], "extensao": False, "incerto": False}
    familia = _familia(argv[0]) if argv else None
    if familia == "sls":
        return _papeis_sls(argv, res)
    if familia == "findstr":
        return _papeis_findstr(argv, res)
    if familia is None:
        return res
    regra, implementacao = OPCOES[familia], _implementacao(argv[0])
    sem_padrao = familia == "rg" and any(a in ("--files", "--type-list") for a in argv[1:])  # só caminhos
    posicionais, explicito, i = [], False, 1
    while i < len(argv):
        a = argv[i]
        if a == "--":
            posicionais += range(i + 1, len(argv))
            break
        papel, colado, opcao = None, None, None
        if a.startswith("--") and familia in ("sed", "awk"):  # prefixo único, como no getopt_long
            nome, igual, valor = a[2:].partition("=")
            opcao, papel, incerta = _opcao_longa(implementacao, nome)
            colado, res["incerto"] = (valor if igual else None), res["incerto"] or incerta
            explicito = explicito or (papel is not None and f"--{opcao}" in regra["explicitas"])
        elif a.startswith("--"):
            nome, igual, valor = a.partition("=")
            papel, colado = regra["longas"].get(nome), (valor if igual else None)
            explicito = explicito or (papel is not None and nome in regra["explicitas"])
        elif a.startswith("-") and len(a) > 1:
            _livres, letra, colado = _letras(familia, a)
            if familia == "awk" and letra == "W":
                i, w_explicito = _opcoes_w(argv, i, colado, implementacao, res)
                explicito = explicito or w_explicito
                continue
            papel, opcao = (regra["curtas"].get(letra) if letra else None), ("load" if letra == "l" else None)
            explicito = explicito or letra in regra["explicitas"]
        else:
            posicionais.append(i)
            i += 1
            continue
        res["extensao"] = res["extensao"] or (familia == "awk" and opcao == "load")
        if papel is None:  # opção sem valor (ou longa desconhecida, que fica como antes)
            i += 1
        elif colado is not None:
            _guardar(res, argv, papel, i, colado)
            res["consumidos"].add(i)
            i += 1
        else:
            _guardar(res, argv, papel, i + 1)
            i += 2
    if not explicito and not sem_padrao and posicionais:
        _guardar(res, argv, "programa" if familia in ("sed", "awk") else "padrao", posicionais.pop(0))
    res["sem_caminho"] = not posicionais
    return res


def _guardar(res: dict, argv: list[str], papel: str, posicao: int, colado: str | None = None) -> None:
    """O valor de uma opção (colado ou na `posicao` de argv) na lista do papel; o programa também em `programas`."""
    if colado is not None:
        res["colados"].append([papel, colado])
    elif posicao < len(argv):
        res[LISTA_DO_PAPEL[papel]].append(posicao)
    else:
        return
    if papel == "programa":
        res["programas"].append((posicao, argv[posicao] if colado is None else colado))


def _opcoes_w(argv: list[str], i: int, colado: str | None, implementacao: str, res: dict) -> tuple[int, bool]:
    """O -W do awk em `i`: `-W opção[=valor]` ou `-Wopção[=valor]`, a opção longa do gawk ou a lista do mawk (com
    vírgulas); o valor que falta é o argumento seguinte. Devolve (próximo índice, se o programa veio por opção)."""
    if colado is None:
        if i + 1 >= len(argv):
            return i + 1, False
        texto, j = argv[i + 1], i + 2
        res["consumidos"].add(i + 1)
    else:
        texto, j = colado, i + 1
        res["consumidos"].add(i)
    explicito = False
    for item in texto.split(","):
        nome, igual, valor = item.partition("=")
        opcao, papel, incerta = _opcao_longa(implementacao, nome)
        res["incerto"] = res["incerto"] or incerta
        res["extensao"] = res["extensao"] or opcao == "load"
        explicito = explicito or (papel is not None and f"--{opcao}" in OPCOES["awk"]["explicitas"])
        if papel is not None and igual:
            _guardar(res, argv, papel, i, valor)
        elif papel is not None:
            _guardar(res, argv, papel, j)
            j += 1
    return j, explicito


def _parametro_sls(nome: str) -> str | None:
    """O parâmetro do Select-String pelo nome, apelido ou prefixo único (como o PowerShell os aceita), ou None."""
    nome = APELIDOS_SLS.get(nome, nome)
    if nome in PARAMETROS_SLS or nome in CHAVES_SLS:
        return nome
    candidatos = [p for p in (*PARAMETROS_SLS, *CHAVES_SLS) if p.startswith(nome)]
    return candidatos[0] if len(candidatos) == 1 else None


def _papeis_sls(argv: list[str], res: dict) -> dict:
    """Select-String: -Pattern (ou o primeiro posicional) é padrão; -Path e -LiteralPath (ou o segundo posicional) são
    caminho; -Include e -Exclude são globs de nome; parâmetro comum com valor (-ErrorAction...) é valor."""
    posicionais, nomeado, i = [], False, 1
    while i < len(argv):
        a = argv[i]
        if a.startswith("-") and len(a) > 1 and not a[1:2].isdigit():
            nome, dois_pontos, colado = a[1:].lower().partition(":")
            param = _parametro_sls(nome)
            papel = PARAMETROS_SLS.get(param) if param else ("valor" if "-" + nome in PARAMETROS_COMUNS_PS else None)
            nomeado = nomeado or param == "pattern"
            if papel is None:
                i += 1
            elif dois_pontos:
                # -Path:<x>/-LiteralPath:<x> (forma com dois-pontos) também é caminho: vai como 'pasta' (conferida
                # como caminho), não fica fora dos alvos (1.7.10).
                res["colados"].append(["pasta" if papel == "caminho" else papel, a.split(":", 1)[1]])
                res["consumidos"].add(i)
                i += 1
            else:
                if papel != "caminho" and i + 1 < len(argv):
                    res[LISTA_DO_PAPEL[papel]].append(i + 1)
                i += 2
            continue
        posicionais.append(i)
        i += 1
    if not nomeado and posicionais:
        res["padroes"].append(posicionais.pop(0))
    res["sem_caminho"] = not posicionais
    return res


def _papeis_findstr(argv: list[str], res: dict) -> dict:
    """findstr: as cadeias (o primeiro posicional) ou /c:<cadeia> são padrão; /g: e /f: são arquivo; /d: são pastas
    (separadas por ponto e vírgula); o resto dos posicionais, arquivos."""
    posicionais, explicito = [], False
    for i, a in enumerate(argv[1:], 1):
        chaves = _chaves_do_findstr(a)
        if chaves is None:
            posicionais.append(i)
            continue
        letras, valor = chaves
        papel = VALOR_DO_FINDSTR.get(letras[-1]) if valor is not None else None
        if papel is None:
            continue
        explicito = explicito or letras[-1] in "cg"
        res["consumidos"].add(i)
        res["colados"] += [[papel, v] for v in (valor.split(";") if papel == "pasta" else [valor]) if v]
    if not explicito and posicionais:
        res["padroes"].append(posicionais.pop(0))
    res["sem_caminho"] = not posicionais
    return res


def _script_com_es(argv: list[str], scripts: list[str]) -> bool:
    """O sed ou o awk de `argv` roda comando ou lê e grava arquivo pelos `scripts` (os programas, na ordem da linha: o
    primeiro posicional ou os -e/--expression do sed e os -e/--source do awk; os do sed vão juntos, como o sed os junta)
    ou, no gawk, por extensão carregada (-l/--load, também abreviada ou no -W). A leitura dos scripts está em
    scripts_do_rastro.py (CI-F7 e a revisão 1)."""
    familia = _familia(argv[0]) if argv else None
    if familia == "sed":
        return _sed_com_es(scripts)
    if familia != "awk":
        return False
    return _papeis(argv)["extensao"] or any(_awk_com_es(s) for s in scripts) or (
        len(scripts) > 1 and _awk_com_es("\n".join(scripts)))


# O que o shell transforma e o shlex não, no texto que chega ao sed e ao awk (revisão de segurança da 1.7.10, CI-F7,
# revisão 2). O PowerShell lê as aspas tipográficas como as ASCII (sondado no Windows PowerShell 5.1 em 01/11/2026); o
# shlex não as conhece, e `Get-Content ‘<bancada>/evals.json’` saía sem acesso: na linha do PowerShell, viram ASCII.
ASPAS_SIMPLES_PS, ASPAS_DUPLAS_PS = "'\u2018\u2019\u201a\u201b", '"\u201c\u201d\u201e'
ASPAS_TIPOGRAFICAS = str.maketrans(ASPAS_SIMPLES_PS[1:] + ASPAS_DUPLAS_PS[1:], "'" * 4 + '"' * 3)


def _expansao_do_bash(comando: str) -> bool:
    """A linha tem, fora das aspas, o que o bash transforma e o shlex não: a citação ANSI-C (`$'…'`) e a `$"…"`, a
    continuação (barra invertida e quebra de linha: o bash tira as duas, o shlex deixa a quebra, e `'sys'\\⏎'tem'` vira
    system) e a expansão de chaves (`-e1{a,e}` vira `-e1a` e `-e1e`; não contam `${`, `{}` e o `{` antes de espaço, o
    do grupo). As aspas são lidas como o shlex as lê: nas simples, nada; nas duplas, só o escape. Antes, o `$'` contava
    em qualquer lugar, também no `'^$'` do grep (CI-F7, revisão 2)."""
    aspa, i = None, 0
    while i < len(comando):
        c, seguinte = comando[i], comando[i + 1:i + 2]
        if aspa == "'":
            aspa = None if c == "'" else aspa
        elif aspa == '"':
            if c == BARRA_INVERTIDA:
                i += 1
            elif c == '"':
                aspa = None
        elif c == BARRA_INVERTIDA:
            if seguinte == "\n":
                return True
            i += 1
        elif c in "'\"":
            aspa = c
        elif c == "$" and seguinte in ("'", '"'):
            return True
        elif c == "{" and comando[i - 1:i] != "$" and seguinte not in ("", " ", "\t", "\r", "\n", "}"):
            return True
        i += 1
    return False


def _acento_grave_do_powershell(comando: str) -> bool:
    """A linha tem acento grave fora das aspas simples: o PowerShell o decodifica nas aspas duplas e na palavra sem
    aspas (`n, `t, `u{…}); nas simples, ele é literal, e o apóstrofo dentro das duplas não abre aspas. Antes, contava
    também dentro das aspas simples (CI-F7, revisão 2)."""
    simples = duplas = False
    for c in comando:
        if simples:
            simples = c not in ASPAS_SIMPLES_PS
        elif c == "`":
            return True
        elif duplas:
            duplas = c not in ASPAS_DUPLAS_PS
        else:
            simples, duplas = c in ASPAS_SIMPLES_PS, c in ASPAS_DUPLAS_PS
    return False


def _relido_no_windows(arg: str) -> bool:
    """O argumento chega mudado ao programa nativo, que relê a linha de comando que o PowerShell monta: com aspa dupla
    ou apóstrofo (o Windows PowerShell 5.1 não escapa a aspa de dentro, e o runtime do MSYS2, do sed e do gawk do Git,
    lê os dois como aspas e junta ou separa argumentos) ou com chave e sem espaço (sem espaço, o PowerShell não põe
    aspas, e o MSYS2 expande as chaves: `{sys{tem,x}(x)}` chega como `system(x)` e `sysx(x)`). Sondado no Windows
    PowerShell 5.1 com o gawk 5.4.1 e o sed 4.9 do Git em 01/11/2026 (CI-F7, revisão 2)."""
    return bool(set(arg) & set("\"'")) or (bool(set(arg) & set("{}")) and not re.search(r"\s", arg))


def _caminhos(nome: str, entrada) -> list[str]:
    """Valores de caminho da entrada (chaves de caminho; `pattern` só no Glob, onde é caminho)."""
    if not isinstance(entrada, dict):
        return []
    valores = []
    for chave, valor in entrada.items():
        if CHAVE_DE_CAMINHO.search(str(chave)) or (nome == "Glob" and chave == "pattern"):
            valores += [v for v in (valor if isinstance(valor, list) else [valor]) if isinstance(v, str)]
    return valores


def _textos(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _textos(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _textos(v)


# --------------------------------------------------------------------- acesso ao gabarito (todas; harness2, P2)
def nomes_do_gabarito(it: Path) -> set[str]:
    """Nomes que só quem procura o gabarito digita: arquivos da bancada, pastas dos casos, casos e braços fixos."""
    evals = json.loads((SKILL / "evals" / "evals.json").read_text(encoding="utf-8"))["evals"]
    nomes = set(iso.NOMES_DO_GABARITO) | set(iso.BRACOS_FIXOS) | {it.name} | {p.name for p in it.glob("eval-*")}
    nomes |= {ev["name"] for ev in evals} | {f"eval-{ev['id']}-{ev['name']}" for ev in evals}
    return {_normal(n) for n in nomes}


def _canonico(caminho: Path) -> list[str]:
    return [_normal(p) for p in _palavras(str(iso.resolvido(caminho)))]


def _absoluto(texto: str, bash: bool = False) -> bool:
    """Caminho absoluto (com unidade, barra ou barra invertida no começo). No Bash, uma barra invertida só no começo
    (`\\*.json`, `\\s*TODO`, sem outra barra depois) é escape, não a raiz (1.7.10); sozinha, continua sendo a raiz do
    disco no Git Bash."""
    t = texto.strip("'\"")
    if bash and len(t) > 1 and t[0] == BARRA_INVERTIDA and not re.search(r"[\\/]", t[1:]):
        return False
    return bool(ABSOLUTO.match(t))


def _componentes(texto: str, base: list[str], bash: bool = False) -> list[str]:
    """Componentes canônicos do caminho: absoluto como veio; relativo a partir de `base` (a pasta corrente do
    executor: o ambiente, até um `cd`); `..` sobe um nível. O prefixo de dispositivo do Windows antes de uma letra de
    unidade ou de `UNC` sai, como em `isolamento.resolvido`; antes, o `?` contava como curinga na raiz e todo caminho
    com o prefixo, até o do próprio ambiente, contaminava. Com outra coisa depois (volume, GLOBALROOT), o `?` fica e
    conta como curinga (terceira passada da revisão de segurança da 1.7.7, R177C-B-08)."""
    partes = [] if _absoluto(texto, bash) else list(base)
    palavras = _palavras(texto)
    if not partes and palavras[:1] == ["?"] and len(palavras) > 1:
        seguinte = _normal(palavras[1])
        if seguinte == "unc":
            palavras = palavras[2:]
        elif len(seguinte) == 1 and seguinte.isalpha():
            palavras = palavras[1:]
    for palavra in palavras:
        if palavra == "..":  # antes de _normal, que tira os pontos finais
            if partes:
                partes.pop()
        else:
            partes.append(_normal(palavra))
    return partes


def _dentro(partes: list[str], raiz: list[str]) -> bool:
    return len(partes) >= len(raiz) and partes[:len(raiz)] == raiz


def _fixo(partes: list[str]) -> list[str]:
    """Os componentes antes do primeiro curinga: a pasta de onde o curinga parte."""
    return next((partes[:i] for i, p in enumerate(partes) if set(p) & CURINGA), partes)


def _alcanca(partes: list[str], raiz: list[str]) -> bool:
    """O caminho com curinga pode designar `raiz` ou algo dentro dela: a parte fixa é um prefixo da raiz e os
    componentes seguintes casam com os dela (`**` casa qualquer profundidade)."""
    fixo = _fixo(partes)
    if len(fixo) == len(partes) or not _dentro(raiz, fixo):
        return False
    for padrao, nome in zip(partes[len(fixo):], raiz[len(fixo):]):
        if padrao == "**":
            return True
        if not fnmatch.fnmatchcase(nome, padrao):
            return False
    return len(partes) >= len(raiz)


def _nome_do_gabarito(componente: str, proibidos: set[str]) -> bool:
    if componente in proibidos:
        return True
    if not set(componente) & CURINGA:
        return False
    fixos = re.sub(r"\[[^\]]*\]|[*?]", "", componente)
    return len(fixos.split(".")[0]) >= 2 and any(fnmatch.fnmatchcase(n, componente) for n in proibidos)


def _forma_propria(caminho: Path) -> re.Pattern:
    """O caminho próprio como aparece num texto: barras de qualquer tipo, sem caixa, `C:` ou `/c` (Git Bash)."""
    partes = [p for p in re.split(r"[\\/]+", str(iso.resolvido(caminho))) if p]
    inicio = ""
    if partes and re.fullmatch(r"[A-Za-z]:", partes[0]):
        inicio = f"(?:{re.escape(partes[0])}|/{re.escape(partes[0][0])})"
        partes = partes[1:]
    return re.compile(inicio + "".join(r"[\\/]+" + re.escape(p) for p in partes) + r"(?![\w.-])", re.IGNORECASE)


class _Exame:
    """Contexto de uma execução: bancada, outras raízes do gabarito, pastas próprias e área do executor."""

    def __init__(self, bancada: Path, nomes: set[str], proprios, area, protegidas):
        self.proprios = [_canonico(c) for c in proprios]
        self.formas = sorted((_forma_propria(c) for c in proprios), key=lambda f: len(f.pattern), reverse=True)
        self.nomes = nomes - {p for caminho in self.proprios for p in caminho}  # layout antigo: caso e braço no caminho
        self.raizes = [("a bancada do avaliador", _canonico(bancada))] + [
            ("outra raiz do gabarito (árvore da skill, skill de um braço ou livro)", _canonico(p)) for p in protegidas]
        self.area = _canonico(area) if area else None
        self.pasta_incerta = False

    def caminho(self, arg: str, base: list[str] | None, recursivo: bool, web: bool = False,
                padrao: bool = False, glob: bool = False, bash: bool = False) -> str | None:
        """Motivo de contaminação do argumento, ou None. `web`: só nomes. `padrao` (padrão ou script de grep, rg,
        sed, awk, Select-String, findstr): só o nome exato do gabarito e o repositório, porque curinga de regex não
        designa arquivo. `glob` (rg -g, grep --include... e o script de sed ou awk com E/S, CI-F7): só o nome do
        gabarito, também com curinga, nunca caminho a partir da raiz. `bash`: a barra invertida só no começo é escape
        (1.7.10)."""
        texto = arg
        for forma in self.formas:  # os caminhos próprios saem antes do teste de nome (R177-VAL-06)
            texto = forma.sub("<proprio>", texto)
        if any(r in texto.lower() for r in REPOSITORIO_PUBLICO):
            return "repositório público ou árvore de desenvolvimento da skill (onde está o gabarito)"
        if padrao:
            exato = any(_normal(p) in self.nomes for p in _palavras(texto))
            return "nome do gabarito, de caso ou de braço" if exato else None
        if any(_nome_do_gabarito(_normal(p), self.nomes) for p in _palavras(texto)):
            return "nome do gabarito, de caso ou de braço"
        if web or glob:
            return None
        if base is None and not _absoluto(arg, bash):
            return None  # relativo sem pasta conhecida: nao e prova de acesso nem de isolamento
        partes = _componentes(arg, base or [], bash)
        fixo = _fixo(partes)
        if any(_dentro(fixo, p) for p in self.proprios):
            return None
        for papel, raiz in self.raizes:
            if _dentro(fixo, raiz):
                return f"caminho dentro de {papel}"
            if _alcanca(partes, raiz):
                return f"curinga que alcança {papel}"
            if recursivo and _dentro(raiz, fixo):
                return f"busca recursiva em pasta que contém {papel}"
        if self.area is not None:
            if _dentro(fixo, self.area):
                return "pasta de outra execução (ou a raiz da área) na área do executor"
            if (recursivo or fixo != partes) and _dentro(self.area, fixo):
                return "curinga ou busca recursiva a partir da área do executor ou de cima dela"
        return None

    def uso(self, nome: str, entrada, pasta: list[str] | None) -> tuple[str | None, list[str] | None]:
        """(motivo, pasta corrente depois do uso)."""
        if nome in FERRAMENTAS_DE_WEB:
            return next(filter(None, (self.caminho(t, pasta, False, web=True) for t in _textos(entrada))), None), pasta
        entrada = entrada if isinstance(entrada, dict) else {}
        comando = entrada.get("command")
        if not isinstance(comando, str):
            caminhos = _caminhos(nome, entrada)
            if nome == "Glob" and isinstance(entrada.get("path"), str) and isinstance(entrada.get("pattern"), str) \
                    and not ABSOLUTO.match(entrada["pattern"]):  # o padrão relativo parte da pasta dada
                caminhos.append(entrada["path"].rstrip("/" + BARRA_INVERTIDA) + "/" + entrada["pattern"])
            recursivo = nome in ("Grep", "Glob")
            return next(filter(None, (self.caminho(c, pasta, recursivo) for c in caminhos)), None), pasta
        # A pasta corrente segue a leitura que vale no shell: escapes no Bash, barras do Windows no PowerShell.
        motivo, depois, valida = None, pasta, 1 if nome.lower() == "powershell" else 0
        powershell, bash = nome.lower() == "powershell", nome.lower() == "bash"
        if powershell:  # as aspas tipográficas são aspas no PowerShell (CI-F7, revisão 2)
            comando = comando.translate(ASPAS_TIPOGRAFICAS)
        leituras = _leituras(comando)
        if nome.lower() == "bash":
            # O shell foi identificado pelo campo estruturado. A alternativa Windows
            # transforma escapes Bash (\\; e \\(, por exemplo) em um alvo / inexistente.
            leituras = leituras[:1]
        # O script de sed ou awk é lido na leitura POSIX, que guarda as barras invertidas dele (a outra as troca por /
        # e desfaz `/\s+$/p`); na outra, só se a POSIX for ilegível (CI-F7).
        posix_ilegivel = bool(leituras[0]) and leituras[0][0][:1] == ["(linha ilegível)"]
        leitura_do_script = 1 if posix_ilegivel and len(leituras) > 1 else 0
        # O que o shell transforma e o shlex não, fora das aspas: no bash, `$'…'`, `$"…"`, chaves e continuação de
        # linha; no PowerShell, o acento grave fora das aspas simples (CI-F7, revisões 1 e 2). Ferramenta que não é
        # nem uma nem outra: as duas regras.
        escapes = (not powershell and _expansao_do_bash(comando)) or (not bash and _acento_grave_do_powershell(comando))
        for i, leitura in enumerate(leituras):
            atual = list(pasta) if pasta is not None else None
            pilha = []  # pasta de antes de cada ( aberto; no PowerShell, o Set-Location entre parênteses vale depois
            for argv in leitura:
                if argv in ([ABRE], [FECHA]):
                    if not powershell:
                        if argv == [ABRE]:
                            pilha.append(atual)
                        elif pilha:
                            atual = pilha.pop()  # a incerteza já marcada dentro do ( ) continua valendo
                    continue
                if argv[:1] == [CD_INCERTO]:  # todo argumento conta como caminho; a pasta seguinte fica incerta
                    motivo = motivo or next(filter(None, (self.caminho(a, atual, False, bash=bash)
                                                          for a in argv[2:])), None)
                    self.pasta_incerta, atual = True, None
                    continue
                if argv and argv[0] == "(linha ilegível)" and i == valida:
                    self.pasta_incerta = True
                    atual = None  # um prefixo completo pode ter mudado a pasta antes do erro
                if argv and _programa(argv[0]) in SHELLS_DELEGADOS and argv[1:] not in (
                        ["--version"], ["--help"], ["-?"]):
                    # O programa interno não foi analisado. Seu cd não muda o shell
                    # externo, mas a ausência de acesso não pode ser aprovada.
                    self.pasta_incerta = True
                if argv and _programa(argv[0]) in MUDA_PASTA:
                    # O alvo é o último argumento depois de tirar os redirecionamentos (`cd X 2>/dev/null`); antes,
                    # era `/dev/null`. Todo argumento, inclusive o alvo de um redirecionamento, conta como caminho.
                    args = _sem_redirecao(argv[1:])
                    args = _sem_parametros_comuns(args) if powershell else args
                    alvo = next((a for a in reversed(args) if not a.startswith("-")), None)
                    motivo = motivo or next(filter(None, (self.caminho(a, atual, False, bash=bash)
                                                          for a in argv[1:])), None)
                    if (alvo is None or set(alvo) & (DINAMICO | CURINGA | {"~"})
                            or (atual is None and not _absoluto(alvo, bash))):
                        self.pasta_incerta = True
                        atual = None
                        continue
                    atual = _componentes(alvo, atual or [], bash)
                    continue
                recursivo = bool(argv) and _recursivo(argv, powershell)
                papeis = _papeis(argv)
                fora = set().union(*(papeis[k] for k in ("padroes", "globs", "valores", "pastas")),
                                   papeis["consumidos"])
                alvos = [a for j, a in enumerate(argv) if j not in fora]
                por_papel = {k: [argv[j] for j in sorted(papeis[k]) if j < len(argv)]
                             for k in ("padroes", "globs", "valores", "pastas")}
                for papel, texto in papeis["colados"]:
                    por_papel[LISTA_DO_PAPEL[papel]].append(texto)
                buscados, globs, valores, pastas = (por_papel[k] for k in ("padroes", "globs", "valores", "pastas"))
                # --opcao=valor de opção sem papel conhecido: o valor é conferido como caminho. Sem recursão
                # (`--exclude-dir=/` não percorre a raiz), salvo nas opções de pasta (`tar --directory=`).
                for a in alvos:
                    if a.startswith("-") and "=" in a:
                        opcao, valor = a.split("=", 1)
                        if opcao == "--regexp":
                            buscados.append(valor)
                        elif valor:
                            (pastas if opcao in OPCOES_DE_PASTA else valores).append(valor)
                if papeis["sem_caminho"] and recursivo:
                    alvos.append(".")  # grep -r sem caminho percorre a pasta corrente
                motivo = motivo or next(filter(None, (self.caminho(a, atual, recursivo, bash=bash)
                                                      for a in alvos + pastas)), None)
                motivo = motivo or next(filter(None, (self.caminho(v, atual, False, bash=bash) for v in valores)),
                                        None)
                # Padrão e glob de nome não são caminho, mas o nome do gabarito ou o repositório neles continua contando.
                motivo = motivo or next(filter(None, (self.caminho(g, atual, False, glob=True) for g in globs)), None)
                # Script de sed ou awk que roda comando ou lê e grava arquivo: o nome com curinga conta, como no glob de
                # nome (a regra da 1.7.9), e o isolamento fica não medido (revisão de segurança da 1.7.10, CI-F7). Os
                # programas vão na ordem da linha; na linha com escape que o shlex não decodifica (`sed $'#\n1e …'`,
                # ou `sed "#`n1e …"` no PowerShell), o script do sed ou do awk conta como com E/S (CI-F7, revisão 1),
                # e também no PowerShell com argumento que o programa nativo relê (CI-F7, revisão 2).
                programas = [texto for _, texto in sorted(papeis["programas"], key=lambda p: p[0])]
                relido = powershell and any(_relido_no_windows(a) for a in argv[1:])
                com_es = i == leitura_do_script and bool(argv) and _familia(argv[0]) in ("sed", "awk") and (
                    escapes or relido or _script_com_es(argv, programas))
                self.pasta_incerta = self.pasta_incerta or com_es or papeis["incerto"]
                motivo = motivo or next(filter(None, (self.caminho(b, atual, False, padrao=not com_es, glob=com_es)
                                                      for b in buscados)), None)
            if i == valida:
                depois = atual
        return motivo, depois


def acesso_ao_gabarito(trace: Path, bancada: Path, nomes: set[str], proprios: tuple[Path, ...],
                       area: Path | None = None, protegidas: tuple[Path, ...] = ()) -> dict:
    """Leitura, listagem ou busca do executor que alcança a bancada, outra raiz do gabarito, um nome do gabarito, o
    repositório público ou a pasta de outra execução: "contaminada" — as asserções desta execução não podem ser
    aprovadas. Sem trace: "nao_medido". `proprios`: o ambiente (primeiro: de onde partem os caminhos relativos) e as
    demais pastas entregues ao executor (saídas, a pasta da execução com a cópia da skill); `area`: a área do
    executor (layout desde a 1.7.7); `protegidas`: as outras raízes do gabarito."""
    if not trace.is_file():
        return {"estado": "nao_medido", "usos": []}
    exame = _Exame(bancada, nomes, proprios, area, protegidas)
    usos, web, pasta = [], 0, list(exame.proprios[0])
    for linha in trace.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            obj = json.loads(linha)
        except json.JSONDecodeError:
            continue
        for nome, entrada in _usos_de_ferramenta(obj):
            web += nome in FERRAMENTAS_DE_WEB
            motivo, pasta = exame.uso(nome, entrada, pasta)
            if motivo:
                usos.append({"ferramenta": nome, "trecho": json.dumps(entrada, ensure_ascii=False)[:200],
                             "motivo": motivo})
    return {"estado": "contaminada" if usos else ("nao_medido" if exame.pasta_incerta else "sem_acesso_no_rastro"),
            "pasta_incerta": exame.pasta_incerta, "usos": usos[:20],
            "usos_de_web": web}
