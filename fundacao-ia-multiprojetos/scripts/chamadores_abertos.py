#!/usr/bin/env python3
"""Chamadores em aberto: a definição que o diff removeu e que o código ainda chama.

  python chamadores_abertos.py --repositorio PASTA --base REF [--limite-nomes N] [--limite-chamadas N]

[Decisão; ponytail, P5 — ideia da conferência "chamadores em aberto" da faixa do ponytail (MIT;
AVISOS-DE-TERCEIROS.md), reescrita como script de fechamento de lote; nenhum trecho do original.] Compara REF com a
árvore de trabalho (`git diff`), junta os nomes de funções, classes e métodos cuja definição foi removida e procura cada
nome no repositório (`git grep`, também nos arquivos novos ainda não rastreados). Um nome que ainda é definido em algum
lugar (movido, renomeado por cópia ou definido de novo) não conta. Os que sobram são chamadores em aberto: o tipo de
defeito em que uma remoção deixa uma chamada sem destino, que custou rodadas na integração da 1.7.10.

Honestidade: é expressão regular sobre linhas, não analisador. Acusa por nome, em qualquer arquivo de texto (um
comentário, uma frase ou um nome igual de outra coisa também aparece), e perde definição que o regex não reconhece
(`nome = outro` ou chamada dinâmica). Confira cada `arquivo:linha` antes de agir.
Só lê: roda `git diff` e `git grep` com argumentos fixos (sem shell, sem programa externo de diff nem conversão de
texto, sem pedir senha), não grava no repositório e não usa rede. REF é um nome de ramo, etiqueta ou commit conferido
antes (`[A-Za-z0-9._/~^@{}-]`, sem começar por '-'). Na sessão de um projeto (FUNDACAO_PROJECT), só lê repositório de
dentro de `projects/<projeto>/`. Códigos: 0 nenhum chamador em aberto; 1 há chamadores em aberto; 2 recusado ou erro.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
VARIAVEL_PROJETO, VARIAVEL_RAIZ = "FUNDACAO_" + "PROJECT", "FUNDACAO_" + "RAIZ"
ID_PROJETO = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
REFERENCIA = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/~^@{}-]{0,99}")
LIMITE_DIFF = 16 * 1024 * 1024
PRAZO_GIT = 60
NOMES_POR_BUSCA = 40
NOME_MINIMO = 3
_NOME = r"([A-Za-z_][A-Za-z0-9_]*)"
_JS = r"([A-Za-z_$][A-Za-z0-9_$]*)"
_MODIFICADORES = r"(?:(?:export|default|public|private|protected|internal|static|final|override|open|abstract|async)\s+)*"
DEFINICOES = {
    "py": [rf"^\s*(?:async\s+)?def\s+{_NOME}", rf"^\s*class\s+{_NOME}"],
    "js": [rf"^\s*{_MODIFICADORES}function\*?\s+{_JS}", rf"^\s*{_MODIFICADORES}class\s+{_JS}",
           rf"^\s*(?:export\s+)?(?:const|let|var)\s+{_JS}\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|{_JS}\s*=>)"],
    "go": [rf"^\s*func\s+(?:\([^)]*\)\s*)?{_NOME}"],
    "rs": [rf"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+{_NOME}"],
    "rb": [rf"^\s*def\s+(?:self\.)?{_NOME}", rf"^\s*(?:class|module)\s+{_NOME}"],
    "outras": [rf"^\s*{_MODIFICADORES}(?:fun|func|function)\s+{_NOME}",
               rf"^\s*{_MODIFICADORES}(?:class|interface|enum|record)\s+{_NOME}"],
}
LINGUAGEM = {".py": "py", ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js", ".ts": "js", ".tsx": "js",
             ".go": "go", ".rs": "rs", ".rb": "rb", ".java": "outras", ".kt": "outras", ".swift": "outras",
             ".cs": "outras", ".php": "outras"}
COMPILADAS = {lang: [re.compile(p) for p in ps] for lang, ps in DEFINICOES.items()}


class Recusado(ValueError):
    """Uso incorreto ou repositório fora da regra: nada foi executado."""


def definicao(extensao: str, linha: str) -> str | None:
    """O nome que a linha define (função, classe ou método) na linguagem da extensão, ou None."""
    for rx in COMPILADAS.get(LINGUAGEM.get(extensao.lower(), ""), []):
        m = rx.match(linha)
        if m:
            return next(g for g in m.groups() if g)
    return None


def removidas(diff: str) -> dict[str, list[str]]:
    """{nome: arquivos} das definições removidas num `git diff -U0` (só as linhas '-' de dentro de um bloco)."""
    achadas: dict[str, list[str]] = {}
    arquivo, no_bloco = "", False
    for linha in diff.splitlines():
        if linha.startswith("diff --git "):
            arquivo, no_bloco = "", False
        elif not no_bloco and linha.startswith("--- "):
            alvo = linha[4:].split("\t", 1)[0]
            arquivo = alvo[2:] if alvo.startswith("a/") else ""
        elif linha.startswith("@@"):
            no_bloco = True
        elif no_bloco and linha.startswith("-") and arquivo:
            nome = definicao(os.path.splitext(arquivo)[1], linha[1:])
            if nome and len(nome) >= NOME_MINIMO and arquivo not in achadas.setdefault(nome, []):
                achadas[nome].append(arquivo)
    return achadas


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0", LC_ALL="C")
    try:
        r = subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "core.quotepath=off", "-C", str(repo), *args],
                           capture_output=True, stdin=subprocess.DEVNULL, env=env, timeout=PRAZO_GIT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Recusado(f"git não rodou ({exc.__class__.__name__})") from None
    if len(r.stdout) > LIMITE_DIFF:
        raise Recusado("saída do git acima de 16 MiB: reduza o intervalo")
    return r


def _texto(r: subprocess.CompletedProcess) -> str:
    return r.stdout.decode("utf-8", "replace")


def _dentro_da_sessao(pasta: Path) -> None:
    """Na sessão de um projeto, só repositório de `<FUNDACAO_RAIZ>/projects/<p>` (a variável só restringe)."""
    da_sessao = os.environ.get(VARIAVEL_PROJETO)
    if not da_sessao:
        return
    real = Path(os.path.normcase(os.path.realpath(pasta)))
    raiz = os.environ.get(VARIAVEL_RAIZ)
    if not ID_PROJETO.fullmatch(da_sessao):
        dentro = False
    elif raiz:
        dentro = real.is_relative_to(os.path.normcase(os.path.join(os.path.realpath(raiz), "projects", da_sessao)))
    else:
        partes = real.parts
        indices = [i for i in range(len(partes) - 1) if partes[i] == "projects"]
        dentro = bool(indices) and all(partes[i + 1] == da_sessao for i in indices)
    if not dentro:
        raise Recusado(f"o projeto da sessão é {da_sessao}: o script só lê repositório de projects/{da_sessao}")


def _pasta_de_repositorio(repositorio) -> Path:
    pasta = Path(os.path.abspath(repositorio))
    if not pasta.is_dir() or pasta.is_symlink():
        raise Recusado(f"{pasta}: não é uma pasta (ou é ligação)")
    _dentro_da_sessao(pasta)
    if _git(pasta, "rev-parse", "--is-inside-work-tree").returncode != 0:
        raise Recusado(f"{pasta}: não é um repositório Git")
    return pasta


def abertos(repositorio, base: str, limite_nomes: int = 20, limite_chamadas: int = 5) -> dict:
    """{"base", "definicoes_removidas", "abertos": [{"nome", "removido_de", "chamadas": [(arquivo, linha)], "mais"}]}."""
    if not REFERENCIA.fullmatch(base or ""):
        raise Recusado(f"--base {base!r}: nome de ramo, etiqueta ou commit (letras, números e . _ / ~ ^ @ {{ }} -)")
    pasta = _pasta_de_repositorio(repositorio)
    if _git(pasta, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").returncode != 0:
        raise Recusado(f"--base {base}: não é um commit deste repositório")
    r = _git(pasta, "diff", "--no-ext-diff", "--no-textconv", "--no-color", "--no-renames", "-U0", base, "--")
    if r.returncode != 0:
        raise Recusado("git diff falhou")
    nomes = removidas(_texto(r))
    ainda_definidos: set[str] = set()
    chamadas: dict[str, list[tuple[str, int]]] = {n: [] for n in nomes}
    lista = sorted(nomes)
    for i in range(0, len(lista), NOMES_POR_BUSCA):
        grupo = lista[i:i + NOMES_POR_BUSCA]
        busca = ["grep", "-n", "-I", "-w", "-F", "--no-color", "--no-textconv", "--untracked", "--exclude-standard"]
        for nome in grupo:
            busca += ["-e", nome]
        achado = _git(pasta, *busca, "--")
        if achado.returncode not in (0, 1):
            raise Recusado("git grep falhou")
        for linha in _texto(achado).splitlines():
            m = re.match(r"^(.+?):(\d+):(.*)$", linha)
            if not m:
                continue
            arquivo, numero, texto = m.group(1), int(m.group(2)), m.group(3)
            palavras = set(re.findall(r"[A-Za-z0-9_$]+", texto))
            definida = definicao(os.path.splitext(arquivo)[1], texto)
            for nome in grupo:
                if nome in palavras:
                    if definida == nome:
                        ainda_definidos.add(nome)
                    else:
                        chamadas[nome].append((arquivo, numero))
    saida = []
    for nome in lista:
        if nome in ainda_definidos or not chamadas[nome]:
            continue
        mostrados = chamadas[nome][:limite_chamadas]
        saida.append({"nome": nome, "removido_de": nomes[nome], "chamadas": mostrados,
                      "mais": len(chamadas[nome]) - len(mostrados)})
    return {"base": base, "definicoes_removidas": len(nomes), "abertos": saida[:limite_nomes],
            "abertos_total": len(saida)}


def formatar(res: dict) -> str:
    linhas = [f"chamadores_abertos: base {res['base']}: {res['definicoes_removidas']} definições removidas, "
              f"{res['abertos_total']} ainda chamadas"]
    for item in res["abertos"]:
        locais = ", ".join(f"{a}:{n}" for a, n in item["chamadas"]) + (f" (+{item['mais']})" if item["mais"] else "")
        linhas.append(f"{item['nome']} (removida de {', '.join(item['removido_de'])}): {locais}")
    if res["abertos_total"] > len(res["abertos"]):
        linhas.append(f"(mais {res['abertos_total'] - len(res['abertos'])} nomes não listados)")
    return "\n".join(linhas)


def main(argv: list | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", newline="\n")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Definições removidas no diff que ainda são chamadas (só lê).")
    ap.add_argument("--repositorio", required=True, help="pasta do repositório Git")
    ap.add_argument("--base", required=True, help="ramo, etiqueta ou commit contra o qual comparar a árvore de trabalho")
    ap.add_argument("--limite-nomes", type=int, default=20, help="quantos nomes listar (padrão 20)")
    ap.add_argument("--limite-chamadas", type=int, default=5, help="quantas chamadas por nome (padrão 5)")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    try:
        if not (1 <= args.limite_nomes <= 200 and 1 <= args.limite_chamadas <= 50):
            raise Recusado("--limite-nomes de 1 a 200 e --limite-chamadas de 1 a 50")
        res = abertos(args.repositorio, args.base, args.limite_nomes, args.limite_chamadas)
    except Recusado as exc:
        print(f"chamadores_abertos: {exc}", file=sys.stderr)
        return 2
    print(formatar(res))
    return 1 if res["abertos_total"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
