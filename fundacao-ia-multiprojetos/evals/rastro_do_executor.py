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
Limite: variável, substituição de comando e código de shell delegado não são resolvidos. Leitura ilegível,\nshell delegado identificado ou cd dinâmico deixam o isolamento não medido
(se houver acesso provado por nome ou caminho absoluto, prevalece contaminada). O rastro é indício, não barreira (a barreira é a área
fora do alcance e a web negada na própria chamada).
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
# (revalidacao-claude-20261025, pendência P1).
PREFIXOS_DO_SHELL = {"{", "!", "if", "elif", "then", "else", "do", "while", "until", "time", "command", "builtin",
                     "nohup"}
PROCURA_TEXTO = {"grep", "egrep", "fgrep", "zgrep", "rg"}
# Opções com valor separado: o valor não é o padrão posicional (e continua conferido como caminho). No GNU grep, o
# valor de --color é opcional e só vale com `=`; no rg, é obrigatório.
COM_VALOR = {
    "grep": {"-A", "-B", "-C", "-m", "-d", "-D", "--after-context", "--before-context", "--context", "--max-count",
             "--include", "--exclude", "--exclude-dir", "--exclude-from", "--label", "--binary-files", "--devices",
             "--directories", "--group-separator"},
    "rg": {"-A", "-B", "-C", "-m", "-g", "-t", "-T", "-j", "-M", "-E", "-r", "-d", "--after-context",
           "--before-context", "--context", "--max-count", "--glob", "--iglob", "--type", "--type-not", "--threads",
           "--max-columns", "--encoding", "--replace", "--max-depth", "--ignore-file", "--sort", "--sortr",
           "--type-add", "--pre", "--pre-glob", "--max-filesize", "--path-separator", "--colors", "--color"},
}
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
        comandos, atual = [], []
        for tok in tokens:
            if tok and set(tok) <= CONTROLE:
                if atual:
                    _emitir(comandos, atual)
                atual = []
                comandos.extend([ABRE] if c == "(" else [FECHA] for c in tok if c in "()")
            else:
                atual.append(tok)
        if atual:
            _emitir(comandos, atual)
        leituras.append(comandos)
    return leituras


def _sem_prefixo(argv: list[str]) -> list[str]:
    """O comando sem `{`, `!`, palavras de if/while/for e `time`/`command`/`builtin`/`nohup` antes do programa; um
    prefixo sozinho fica como veio. Atribuições (`NOME=valor`) ficam: a CLI da fundação as confere."""
    i = 0
    while i < len(argv) - 1 and argv[i] in PREFIXOS_DO_SHELL:
        i += 1
    return argv[i:]


def _emitir(comandos: list[list[str]], argv: list[str]) -> None:
    """Acrescenta o comando sem prefixo. O cd depois de prefixo (`{ cd X; } | head`, `f() { cd X; }`, `nohup cd X`)
    vira [CD_INCERTO, ...]: se ele muda o shell depende de pipeline, função ou do prefixo, e a pasta fica incerta."""
    limpo = _sem_prefixo(argv)
    if len(limpo) < len(argv) and _programa(limpo[0]) in MUDA_PASTA:
        comandos.append([CD_INCERTO, *limpo])
    else:
        comandos.append(limpo)


def _comandos_simples(comando: str) -> list[list[str]]:
    """Os comandos simples das duas leituras da linha (as duas contam), sem as marcas."""
    return [argv[1:] if argv[:1] == [CD_INCERTO] else argv
            for leitura in _leituras(comando) for argv in leitura if argv not in ([ABRE], [FECHA])]


def _recursivo(argv: list[str], powershell: bool = False) -> bool:
    """Programa recursivo ou opção de recursão. Fora do PowerShell, todo grupo curto de opções com r ou R (`-r`,
    `-rnE`, `-IR`, `-Hrn`, `-1R`) e `-d recurse` do grep. No PowerShell, as regras antigas (grupos de até 5 letras
    com r minúsculo entre minúsculas ou com R) e `-Recurse`, para não tomar `-Force` nem `-Filter` por recursão."""
    programa = _programa(argv[0])
    if programa in RECURSIVOS:
        return True
    so_maiusculo = programa == "ls" and not powershell  # no ls do POSIX, -r é ordem inversa; recursão é -R
    for j, a in enumerate(argv[1:], 1):
        if a in ("--recursive", "--directories=recurse", "-drecurse") or a.lower() in ("-recurse", "/s"):
            return True
        if a == "-R" or (a == "-r" and not so_maiusculo):
            return True
        if a in ("-d", "--directories") and argv[j + 1:j + 2] == ["recurse"]:
            return True
        if powershell:
            if re.fullmatch(r"-[a-z]{0,2}r[a-z]{0,2}", a) or re.fullmatch(r"-[a-zA-Z]{0,2}R[a-zA-Z]{0,2}", a):
                return True
        elif re.fullmatch(r"-[A-Za-z0-9]{1,6}", a) and ("R" in a or ("r" in a and not so_maiusculo)):
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


def _padroes(argv: list[str]) -> tuple[set[int], bool]:
    """Num grep/rg: (posições dos argumentos que são padrão de busca, não caminho; se não sobra caminho
    posicional). Padrão é o valor de -e/--regexp e, sem -e/--regexp/-f/--file, o primeiro argumento posicional. O
    valor de -f/--file é arquivo lido e continua caminho. Antes, o padrão contava como caminho, e um que começava por
    barra invertida valia como a raiz (pendência P1 da fase revalidacao-claude-20261025)."""
    programa = _programa(argv[0]) if argv else ""
    if programa not in PROCURA_TEXTO:
        return set(), False
    com_valor = COM_VALOR["rg" if programa == "rg" else "grep"]
    sem_padrao = programa == "rg" and any(a in ("--files", "--type-list") for a in argv[1:])  # só caminhos
    padroes, posicionais, explicito, i = set(), [], False, 1
    while i < len(argv):
        a = argv[i]
        if a == "--":
            posicionais += range(i + 1, len(argv))
            break
        if a in ("-e", "--regexp", "-f", "--file"):
            if a in ("-e", "--regexp"):
                padroes.add(i + 1)
            explicito, i = True, i + 2
            continue
        if a.startswith(("--regexp=", "--file=")):
            explicito, i = True, i + 1
            continue
        if a in com_valor:
            i += 2
            continue
        if a.startswith("-") and len(a) > 1:
            letras = a[1:] if not a.startswith("--") else ""
            k = next((j for j, c in enumerate(letras) if c in "ef"), None)
            if k is not None:  # -ePADRAO e -fARQUIVO colados, ou -rne PADRAO e -rf ARQUIVO com o valor a seguir
                explicito = True
                if k == len(letras) - 1:
                    if letras[k] == "e":
                        padroes.add(i + 1)
                    i += 2
                    continue
            i += 1
            continue
        posicionais.append(i)
        i += 1
    if not explicito and not sem_padrao and posicionais:
        padroes.add(posicionais.pop(0))
    return padroes, not posicionais


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


def _componentes(texto: str, base: list[str]) -> list[str]:
    """Componentes canônicos do caminho: absoluto como veio; relativo a partir de `base` (a pasta corrente do
    executor: o ambiente, até um `cd`); `..` sobe um nível. O prefixo de dispositivo do Windows antes de uma letra de
    unidade ou de `UNC` sai, como em `isolamento.resolvido`; antes, o `?` contava como curinga na raiz e todo caminho
    com o prefixo, até o do próprio ambiente, contaminava. Com outra coisa depois (volume, GLOBALROOT), o `?` fica e
    conta como curinga (terceira passada da revisão de segurança da 1.7.7, R177C-B-08)."""
    partes = [] if ABSOLUTO.match(texto.strip("'\"")) else list(base)
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
                padrao: bool = False) -> str | None:
        """Motivo de contaminação do argumento, ou None. `web`: só nomes. `padrao` (padrão de grep/rg): só o nome
        exato do gabarito e o repositório, porque curinga de regex não designa arquivo."""
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
        if web:
            return None
        if base is None and not ABSOLUTO.match(arg):
            return None  # relativo sem pasta conhecida: nao e prova de acesso nem de isolamento
        partes = _componentes(arg, base or [])
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
        powershell = nome.lower() == "powershell"
        leituras = _leituras(comando)
        if nome.lower() == "bash":
            # O shell foi identificado pelo campo estruturado. A alternativa Windows
            # transforma escapes Bash (\\; e \\(, por exemplo) em um alvo / inexistente.
            leituras = leituras[:1]
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
                    motivo = motivo or next(filter(None, (self.caminho(a, atual, False) for a in argv[2:])), None)
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
                    motivo = motivo or next(filter(None, (self.caminho(a, atual, False) for a in argv[1:])), None)
                    if (alvo is None or set(alvo) & (DINAMICO | CURINGA | {"~"})
                            or (atual is None and not ABSOLUTO.match(alvo))):
                        self.pasta_incerta = True
                        atual = None
                        continue
                    atual = _componentes(alvo, atual or [])
                    continue
                recursivo = bool(argv) and _recursivo(argv, powershell)
                padroes, sem_caminho = _padroes(argv)
                alvos = [a for j, a in enumerate(argv) if j not in padroes]
                buscados = [argv[j] for j in sorted(padroes) if j < len(argv)]
                # --opcao=valor: o valor é conferido como caminho. Sem recursão (`--exclude-dir=/` não percorre a raiz),
                # salvo nas opções de pasta (`tar --directory=`); o de --regexp= é padrão.
                valores, pastas = [], []
                for a in alvos:
                    if a.startswith("-") and "=" in a:
                        opcao, valor = a.split("=", 1)
                        if opcao == "--regexp":
                            buscados.append(valor)
                        elif valor:
                            (pastas if opcao in OPCOES_DE_PASTA else valores).append(valor)
                if sem_caminho and recursivo:
                    alvos.append(".")  # grep -r sem caminho percorre a pasta corrente
                motivo = motivo or next(filter(None, (self.caminho(a, atual, recursivo) for a in alvos + pastas)),
                                        None)
                motivo = motivo or next(filter(None, (self.caminho(v, atual, False) for v in valores)), None)
                # O padrão não é caminho, mas buscar um nome do gabarito ou o repositório continua contando.
                motivo = motivo or next(filter(None, (self.caminho(b, atual, False, padrao=True)
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
