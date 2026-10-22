#!/usr/bin/env python3
"""Mudanças de cada versão com efeito e veredito, e o índice das lições com evidência.

  validar [--raiz <árvore>]   confere entrega/licoes/MUDANCAS-*.md e o LICOES.md      problema -> código 1
  indice  [--raiz <árvore>]   refaz entrega/licoes/LICOES.md a partir dos MUDANCAS    fonte inválida -> código 1

Método adaptado de Harness² (arXiv:2610.14224, github.com/google-research/harness2, commit 1cfe254, Apache-2.0): o
registro do que cada mudança fez de fato, com "confundido" como veredito honesto quando o efeito não pode ser
atribuído a uma mudança só; até três lições com evidência, ou SEM_ENTRADA; e o índice refeito a partir dos arquivos,
nunca à mão. Texto e código próprios.

Formato de `entrega/licoes/MUDANCAS-<versão>.md`:
- a linha `Versão: <versão>`, igual à do nome do arquivo;
- `## Mudanças`: tabela com as colunas de COLUNAS, uma linha por mudança (M1, M2...); veredito de VEREDITOS; efeito
  "não observado" só com o veredito "sem efeito observado";
- `## Lições`: a linha SEM_ENTRADA ou até três blocos `### L<n> — <título>` com os campos de CAMPOS. A evidência
  cita linhas da tabela (M1...) e ao menos um caminho da árvore entre crases; commits entre crases (7 a 40 dígitos
  hexadecimais) são da árvore de desenvolvimento, só conferidos na forma (a cópia pública tem outro histórico).
O validar recusa também: confiança alta numa lição apoiada só em linhas "confundido" (é palpite); caminho de
evidência que não existe com a grafia exata, absoluto, com `..` ou que passa por ligação; evidência nas pastas que a
cópia pública não leva (PRIVADAS), porque esta pasta vai para lá; caminho absoluto, pasta de usuário ou e-mail em
qualquer ponto do arquivo (o saneamento da cópia pública recusaria); fim de linha CRLF; e um LICOES.md diferente do
que o indice gera agora.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PASTA = ("entrega", "licoes")
INDICE = "LICOES.md"
NOME = re.compile(r"^MUDANCAS-(\d+\.\d+\.\d+)\.md$")
COLUNAS = ("#", "Componente", "O que mudou", "Motivo observado (onde)", "Efeito observado (onde)", "Veredito")
VEREDITOS = ("ajudou", "piorou", "sem efeito observado", "confundido")
CAMPOS = ("Gatilho", "Lição", "Evidência", "Confiança")
CONFIANCAS = ("alta", "média", "baixa")
SEM_ENTRADA = "SEM_ENTRADA"
MAX_LICOES = 3
PRIVADAS = ("entrega/auditoria/", "fundacao-ia-multiprojetos-workspace/")  # a cópia pública não leva
PESSOAL = (
    (re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]"), "caminho absoluto do Windows"),
    (re.compile(r"\\\\[A-Za-z0-9]"), "caminho de rede"),
    (re.compile(r"(?<![\w.~-])/(?:home|Users|mnt|root)/"), "pasta de usuário ou de montagem"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "e-mail"),
)
CRASE = re.compile(r"`([^`\n]+)`")
COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
CAMINHO = re.compile(r"^[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*/?$")


def e_ligacao(p: Path) -> bool:
    """Link simbólico ou junção do Windows (a mesma regra do empacotar.py)."""
    if p.is_symlink():
        return True
    is_junction = getattr(os.path, "isjunction", None)
    if is_junction is not None:
        return bool(is_junction(p))
    if os.name != "nt":
        return False
    try:
        st = os.lstat(p)
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT) and \
        getattr(st, "st_reparse_tag", None) == stat.IO_REPARSE_TAG_MOUNT_POINT


def problema_do_caminho(raiz: Path, rel: str) -> str | None:
    """None se `rel` existe na árvore com a grafia exata, é relativo, contido e não passa por ligação."""
    if rel.startswith(("/", "\\")) or "\\" in rel or re.match(r"^[A-Za-z]:", rel):
        return "caminho absoluto ou com barra invertida"
    partes = rel.rstrip("/").split("/")
    if any(p in ("", ".", "..") for p in partes):
        return "caminho com parte vazia, '.' ou '..'"
    if any((rel.rstrip("/") + "/").startswith(p) for p in PRIVADAS):
        return "pasta que a cópia pública não leva (cite a nota da versão ou o commit)"
    atual = raiz
    for parte in partes:
        try:
            nomes = os.listdir(atual)
        except OSError:
            return "não existe na árvore"
        if parte not in nomes:  # Windows e macOS não distinguem maiúsculas; a CI no Linux distingue
            return "não existe na árvore com esta grafia"
        atual = atual / parte
        if e_ligacao(atual):
            return "passa por ligação (link simbólico ou junção)"
    return None


def e_caminho(token: str) -> bool:
    """Trecho entre crases que se lê como caminho (os absolutos entram para serem recusados)."""
    if " " not in token and (re.match(r"^(?:[A-Za-z]:)?[\\/]", token) or "\\" in token):
        return True
    return bool(CAMINHO.match(token)) and ("/" in token or token.startswith(".")) and token not in (".", "..")


def celulas(linha: str) -> list[str]:
    corpo = linha.strip()[1:]
    if corpo.endswith("|") and not corpo.endswith("\\|"):
        corpo = corpo[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", corpo)]


def secoes(texto: str) -> dict[str, str]:
    """Texto antes do primeiro `## ` (chave "") e de cada `## título`, sem comentários HTML."""
    partes = re.split(r"(?m)^## +(.+?)[ \t]*$", re.sub(r"(?s)<!--.*?-->", "", texto))
    return {"": partes[0], **{partes[i].strip(): partes[i + 1] for i in range(1, len(partes) - 1, 2)}}


def ler_tabela(texto: str, nome: str, problemas: list[str]) -> dict[str, str]:
    """{id da linha: veredito} das mudanças, acumulando os problemas."""
    linhas = [l for l in texto.splitlines() if l.strip().startswith("|")]
    if len(linhas) < 3:
        problemas.append(f"{nome}: a tabela de mudanças precisa de cabeçalho, separador e ao menos uma linha")
        return {}
    if tuple(celulas(linhas[0])) != COLUNAS or not all(re.fullmatch(r":?-{3,}:?", c) for c in celulas(linhas[1])):
        problemas.append(f"{nome}: a tabela de mudanças precisa das colunas {' | '.join(COLUNAS)} e do separador")
        return {}
    vereditos: dict[str, str] = {}
    for linha in linhas[2:]:
        c = celulas(linha)
        if len(c) != len(COLUNAS):
            problemas.append(f"{nome}: linha da tabela com {len(c)} colunas (barra dentro da célula vai como \\|): "
                             f"{linha.strip()[:60]}")
            continue
        ident, componente, mudou, motivo, efeito, veredito = c
        rotulo = f"{nome}: {ident or '(sem #)'}"
        if not re.fullmatch(r"M\d+", ident) or ident in vereditos:
            problemas.append(f"{rotulo}: # precisa ser M1, M2... sem repetir")
            continue
        for campo, valor in (("o que mudou", mudou), ("motivo", motivo), ("efeito", efeito)):
            if not valor:
                problemas.append(f"{rotulo}: {campo} vazio")
        tokens = CRASE.findall(componente)
        if not tokens or any(not CAMINHO.match(t) or ".." in t.split("/") for t in tokens):
            problemas.append(f"{rotulo}: componente precisa ser caminho relativo no repositório, entre crases")
        veredito = " ".join(veredito.lower().split())
        if veredito not in VEREDITOS:
            problemas.append(f"{rotulo}: veredito fora do vocabulário ({' · '.join(VEREDITOS)})")
        elif efeito.lower().startswith("não observado") and veredito != "sem efeito observado":
            problemas.append(f"{rotulo}: efeito não observado só admite o veredito 'sem efeito observado'")
        vereditos[ident] = veredito
    return vereditos


def ler_licoes(texto: str, nome: str, vereditos: dict[str, str], raiz: Path, problemas: list[str]) -> list[dict]:
    blocos = re.split(r"(?m)^### +", texto)
    sem_entrada = blocos[0].strip() == SEM_ENTRADA
    if len(blocos) == 1:
        if not sem_entrada:
            problemas.append(f"{nome}: em Lições, escreva {SEM_ENTRADA} ou de uma a {MAX_LICOES} lições")
        return []
    if blocos[0].strip():
        problemas.append(f"{nome}: texto solto antes das lições (e {SEM_ENTRADA} não se mistura com lição)")
    if len(blocos) - 1 > MAX_LICOES:
        problemas.append(f"{nome}: {len(blocos) - 1} lições; o máximo é {MAX_LICOES}")
    licoes, vistos = [], set()
    for bloco in blocos[1:]:
        cabeca, *corpo = bloco.splitlines()
        m = re.fullmatch(r"(L\d+)\s*[—–-]\s*(.+?)\s*", cabeca)
        if not m or m.group(1) in vistos:
            problemas.append(f"{nome}: título de lição precisa ser '### L<n> — <título>', sem repetir: {cabeca[:60]}")
            continue
        ident, rotulo = m.group(1), f"{nome}: {m.group(1)}"
        vistos.add(ident)
        campos: dict[str, str] = {}
        atual = None
        for linha in corpo:
            f = re.match(r"^- ([^:]+):\s*(.*)$", linha)
            if f and f.group(1) in CAMPOS and f.group(1) not in campos:
                atual = f.group(1)
                campos[atual] = f.group(2).strip()
            elif f:
                problemas.append(f"{rotulo}: campo desconhecido ou repetido: {f.group(1)}")
                atual = None
            elif linha.strip() and atual and linha[:1].isspace():
                campos[atual] += " " + linha.strip()
            elif linha.strip():
                problemas.append(f"{rotulo}: linha fora dos campos: {linha.strip()[:60]}")
        faltam = [c for c in CAMPOS if not campos.get(c)]
        if faltam:
            problemas.append(f"{rotulo}: faltam campos: {', '.join(faltam)}")
            continue
        confianca = campos["Confiança"].strip(" .").lower()
        if confianca not in CONFIANCAS:
            problemas.append(f"{rotulo}: confiança fora do vocabulário ({' · '.join(CONFIANCAS)})")
        evidencia = campos["Evidência"]
        linhas = set(re.findall(r"\bM\d+\b", CRASE.sub(" ", evidencia)))
        if not linhas:
            problemas.append(f"{rotulo}: a evidência precisa citar ao menos uma linha da tabela (M1...)")
        for ausente in sorted(linhas - set(vereditos)):
            problemas.append(f"{rotulo}: a evidência cita {ausente}, que não está na tabela")
        caminhos = [t for t in CRASE.findall(evidencia) if not COMMIT.match(t) and e_caminho(t)]
        if not caminhos:
            problemas.append(f"{rotulo}: a evidência precisa de ao menos um caminho da árvore entre crases")
        for caminho in caminhos:
            erro = problema_do_caminho(raiz, caminho)
            if erro:
                problemas.append(f"{rotulo}: evidência `{caminho}`: {erro}")
        apoio = [vereditos[l] for l in linhas if l in vereditos]
        if apoio and all(v == "confundido" for v in apoio) and confianca == "alta":
            problemas.append(f"{rotulo}: apoiada só em linhas 'confundido', não pode ter confiança alta (é palpite)")
        licoes.append({"id": ident, "titulo": m.group(2), "gatilho": campos["Gatilho"], "licao": campos["Lição"],
                       "confianca": confianca})
    return licoes


def ler_mudancas(raiz: Path, arquivo: Path, problemas: list[str]) -> dict | None:
    nome = arquivo.name
    versao = NOME.match(nome).group(1)
    bruto = arquivo.read_bytes()
    if b"\r\n" in bruto:
        problemas.append(f"{nome}: fim de linha CRLF (grave em LF)")
    try:
        texto = bruto.decode("utf-8")
    except UnicodeDecodeError:
        problemas.append(f"{nome}: não é UTF-8")
        return None
    for rx, motivo in PESSOAL:
        for m in rx.finditer(texto):
            problemas.append(f"{nome}: {motivo} ({m.group(0)[:30]}): a pasta vai para a cópia pública")
    partes = secoes(texto)
    m = re.search(r"(?m)^Versão:\s*(\d+\.\d+\.\d+)\b", partes[""])
    if not m or m.group(1) != versao:
        problemas.append(f"{nome}: a linha 'Versão: {versao}' precisa vir antes da tabela, igual ao nome do arquivo")
    if "Mudanças" not in partes or "Lições" not in partes:
        problemas.append(f"{nome}: faltam as seções '## Mudanças' e '## Lições'")
        return None
    vereditos = ler_tabela(partes["Mudanças"], nome, problemas)
    licoes = ler_licoes(partes["Lições"], nome, vereditos, raiz, problemas)
    return {"versao": versao, "arquivo": nome, "licoes": licoes}


def chave_versao(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def carregar(raiz: Path) -> tuple[list[dict], list[str]]:
    pasta = raiz.joinpath(*PASTA)
    arquivos = sorted((p for p in pasta.glob("MUDANCAS-*.md") if p.is_file()), key=lambda p: p.name)
    problemas = [f"{p.name}: nome fora do formato MUDANCAS-<versão>.md" for p in arquivos if not NOME.match(p.name)]
    validos = [p for p in arquivos if NOME.match(p.name)]
    if not validos:
        problemas.append("nenhum MUDANCAS-<versão>.md em " + "/".join(PASTA))
    dados = [d for p in validos if (d := ler_mudancas(raiz, p, problemas))]
    return sorted(dados, key=lambda d: chave_versao(d["versao"])), problemas


def celula(texto: str) -> str:
    return " ".join(texto.split()).replace("|", "\\|")


def gerar_indice(dados: list[dict]) -> str:
    linhas = ["# Lições — índice gerado", "",
              "Gerado por `python entrega/licoes.py indice` a partir de `entrega/licoes/MUDANCAS-<versão>.md`; não",
              "edite à mão (o `validar` compara este arquivo com o que o `indice` gera). Antes de planejar uma versão,",
              "leia as lições das anteriores e trate cada uma como hipótese a reconferir, não como fato.", "",
              "| Gatilho | Lição | Confiança | Versão |", "|---|---|---|---|"]
    for d in dados:
        for li in sorted(d["licoes"], key=lambda x: int(x["id"][1:])):
            linhas.append(f"| {celula(li['gatilho'])} | {celula(li['licao'])} | {li['confianca']} | "
                          f"{d['versao']}, {li['id']} ({celula(li['titulo'])}) |")
    sem = [d["versao"] for d in dados if not d["licoes"]]
    if sem:
        linhas += ["", f"Versões sem lição ({SEM_ENTRADA}): {', '.join(sem)}."]
    return "\n".join(linhas) + "\n"


def validar(raiz: Path) -> dict:
    dados, problemas = carregar(raiz)
    indice = raiz.joinpath(*PASTA, INDICE)
    if not problemas:
        if not indice.is_file():
            problemas.append(f"{INDICE} ausente: rode python entrega/licoes.py indice")
        elif indice.read_bytes() != gerar_indice(dados).encode("utf-8"):
            problemas.append(f"{INDICE} diferente do que o indice gera (editado à mão ou MUDANCAS novo): "
                             "rode python entrega/licoes.py indice")
    return {"ok": not problemas, "arquivos": [d["arquivo"] for d in dados],
            "licoes": sum(len(d["licoes"]) for d in dados), "problemas": problemas}


def indice(raiz: Path) -> dict:
    dados, problemas = carregar(raiz)
    if problemas:
        return {"ok": False, "problemas": problemas}
    alvo = raiz.joinpath(*PASTA, INDICE)
    novo = gerar_indice(dados)
    atual = alvo.read_bytes() if alvo.is_file() else None
    acao = "igual" if atual == novo.encode("utf-8") else ("criar" if atual is None else "atualizar")
    if acao != "igual":
        tmp = alvo.with_name("." + INDICE + ".tmp")
        tmp.write_text(novo, encoding="utf-8", newline="\n")
        tmp.replace(alvo)
    return {"ok": True, "acao": acao, "arquivo": "/".join((*PASTA, INDICE)),
            "licoes": sum(len(d["licoes"]) for d in dados)}


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome in ("validar", "indice"):
        sub.add_parser(nome).add_argument("--raiz", type=Path, default=RAIZ, help="raiz da árvore (padrão: esta)")
    args = ap.parse_args(argv)
    res = (validar if args.cmd == "validar" else indice)(args.raiz.resolve())
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
