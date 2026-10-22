#!/usr/bin/env python3
"""Rastro do executor: comandos e caminhos das chamadas de ferramenta e o fato `acesso_ao_gabarito` (apoio de
verificar_execucoes.py, que também usa a leitura de comandos e caminhos nos acessos da E7/E9).

A leitura vem da estrutura (auditoria 1.5.0, achado 16), não de trecho de texto: cada uso de ferramenta da
transcrição (`trace.jsonl`) dá um nome (campo estruturado) e uma entrada; comando de shell é lido com shlex, em duas
leituras (escapes do bash e barras do Windows); caminho é comparado em forma canônica (caixa, barras, `.`, `..`,
pontos e espaços finais).
[Decisão; harness2, P2] Acesso ao gabarito: leitura, listagem ou busca que alcance a bancada do avaliador, outra
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
Limite: variável e substituição de comando não são resolvidas. O rastro é indício, não barreira (a barreira é a área
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
MUDA_PASTA = {"cd", "chdir", "pushd", "set-location", "sl", "push-location"}
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


def _leituras(comando: str) -> list[list[list[str]]]:
    """Comandos simples (argv) de cada leitura da linha, separados por ; & && || | ( ) e quebra de linha: como veio
    (escapes do bash) e com a barra invertida trocada por '/' (caminhos do Windows). Comentários NÃO são descartados
    (o texto depois de '#' também é examinado). Aspas sem par: a linha inteira vira um comando ilegível."""
    leituras = []
    for texto in (comando, comando.replace(BARRA_INVERTIDA, "/")):
        lex = shlex.shlex(texto, posix=True, punctuation_chars=";&|()<>\n")
        lex.whitespace, lex.whitespace_split, lex.commenters = " \t\r", True, ""
        try:
            tokens = list(lex)
        except ValueError:
            leituras.append([["(linha ilegível)", *texto.split()]])
            continue
        comandos, atual = [], []
        for tok in tokens:
            if tok and set(tok) <= CONTROLE:
                if atual:
                    comandos.append(atual)
                atual = []
            else:
                atual.append(tok)
        if atual:
            comandos.append(atual)
        leituras.append(comandos)
    return leituras


def _comandos_simples(comando: str) -> list[list[str]]:
    """Os comandos simples das duas leituras da linha (as duas contam)."""
    return [argv for leitura in _leituras(comando) for argv in leitura]


def _recursivo(argv: list[str]) -> bool:
    if _programa(argv[0]) in RECURSIVOS:
        return True
    return any(a.lower() in ("-r", "--recursive", "-recurse", "/s") or re.fullmatch(r"-[a-z]{0,2}r[a-z]{0,2}", a)
               or re.fullmatch(r"-[a-zA-Z]{0,2}R[a-zA-Z]{0,2}", a) for a in argv[1:])


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

    def caminho(self, arg: str, base: list[str], recursivo: bool, web: bool = False) -> str | None:
        texto = arg
        for forma in self.formas:  # os caminhos próprios saem antes do teste de nome (R177-VAL-06)
            texto = forma.sub("<proprio>", texto)
        if any(r in texto.lower() for r in REPOSITORIO_PUBLICO):
            return "repositório público ou árvore de desenvolvimento da skill (onde está o gabarito)"
        if any(_nome_do_gabarito(_normal(p), self.nomes) for p in _palavras(texto)):
            return "nome do gabarito, de caso ou de braço"
        if web:
            return None
        partes = _componentes(arg, base)
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

    def uso(self, nome: str, entrada, pasta: list[str]) -> tuple[str | None, list[str]]:
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
        for i, leitura in enumerate(_leituras(comando)):
            atual = list(pasta)
            for argv in leitura:
                if argv and _programa(argv[0]) in MUDA_PASTA:
                    alvo = next((a for a in reversed(argv[1:]) if not a.startswith("-")), None)
                    if alvo is None or set(alvo) & DINAMICO:
                        continue  # destino desconhecido: a pasta fica (variável não é resolvida)
                    motivo = motivo or self.caminho(alvo, atual, False)
                    atual = _componentes(alvo, atual)
                    continue
                recursivo = bool(argv) and _recursivo(argv)
                motivo = motivo or next(filter(None, (self.caminho(a, atual, recursivo) for a in argv)), None)
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
    return {"estado": "contaminada" if usos else "sem_acesso_no_rastro", "usos": usos[:20],
            "usos_de_web": web}
