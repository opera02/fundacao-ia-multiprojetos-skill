#!/usr/bin/env python3
"""Arquivos de instrução e de extensão de host dentro de uma pasta — o que o Claude Code carregaria sozinho
(análise do vibe-coding-toolkit, 21/10/2026, proposta 2).

  python instrucoes_aninhadas.py listar --raiz <pasta> [--saida <arquivo>]

Pela documentação do Claude Code (conferida em 21/10/2026), CLAUDE.md e AGENTS.md de subpastas carregam sob demanda
quando o agente lê um arquivo daquela subpasta, e skills em `.claude/skills/` de subpastas passam a valer na primeira
leitura ou edição de arquivo ali, sem configuração que desligue essa descoberta. Numa pasta de DADOS — a cópia
importada no fluxo B, etapa B1 — isso transforma dado em instrução. Este script só lê: lista cada arquivo (caminho
relativo e SHA-256; das skills, também o `name` do frontmatter) e sugere a configuração do host —
`claudeMdExcludes` para as pastas de dados e `Skill(<nome>)` nas negações, para cada skill aninhada (use os nomes
com `assets/host/preparo_host.py ... --negar-skill`). Não executa nada e não lê conteúdo além do frontmatter.
Não segue ligação (link simbólico ou junção): ela vai para `ligacoes_nao_seguidas`, e o que há do outro lado não é
lido nem inventariado. Tetos aplicados durante a varredura: 100 mil itens, 32 níveis, 5 MB por arquivo e 100 MB no
total; o que ficou de fora vai para `nao_lidos` (auditoria Codex Security da 1.7.6, #7). Arquivo com vínculo físico
(hard link, mais de um nome) também vai para `nao_lidos`, sem leitura: o outro nome pode estar fora da raiz (revisão
de segurança da 1.7.7, R177-VAL-02).
Código 0 quando leu tudo; 1 quando o inventário ficou parcial (ligação não seguida, teto, arquivo ou pasta não lida —
o resultado diz o quê); 2 se a pasta não existe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

INSTRUCOES = {"CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", "AGENTS.override.md"}
IGNORAR = {".git", "__pycache__", "node_modules", ".venv", "venv"}
EXCLUSAO_DE_DADOS = "**/projects/*/data/**"
TETO_ITENS = 100_000          # entradas examinadas (arquivos e pastas)
TETO_PROFUNDIDADE = 32        # níveis de pasta abaixo da raiz
TETO_ARQUIVO = 5_000_000      # bytes lidos de um arquivo (hash em blocos)
TETO_TOTAL = 100_000_000      # bytes lidos no total
INICIO = 65_536               # começo do SKILL.md onde se procura o `name` do frontmatter
BLOCO = 1 << 20
# Windows: etiqueta de ponto de nova análise "substituta de nome" (bit 29) — junção, link simbólico e afins.
SUBSTITUTA_DE_NOME = 0x20000000


class Trocado(OSError):
    """O arquivo aberto não é o examinado: virou ligação, deixou de ser comum ou resolve fora da raiz."""


class VinculoFisico(OSError):
    """Arquivo com mais de um nome (hard link): o conteúdo pode ser o de um arquivo de fora da raiz (R177-VAL-02)."""


def e_ligacao(st: os.stat_result) -> bool:
    """Link simbólico ou junção (e afins do Windows), pelo lstat — sem seguir a ligação."""
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & SUBSTITUTA_DE_NOME)


def percorrer(raiz: Path, situacao: dict):
    """Arquivos comuns sob a raiz, em ordem de caminho, sem atravessar ligação (a ligação vai para a situação e não é
    lida). Os tetos de itens e de profundidade valem DURANTE a varredura, não depois de ordenar."""
    vistos = 0

    def listar(pasta: Path, partes: tuple) -> list:
        nonlocal vistos
        entradas = []
        try:
            with os.scandir(pasta) as it:
                for e in it:
                    vistos += 1
                    if vistos > TETO_ITENS:
                        situacao["limites"].add("itens")
                        situacao["nao_lidos"].append({"caminho": "/".join(partes) or ".",
                                                      "motivo": f"teto de {TETO_ITENS} itens: a varredura parou aqui"})
                        break
                    entradas.append(e)
        except OSError as exc:
            situacao["nao_lidos"].append({"caminho": "/".join(partes) or ".",
                                          "motivo": f"pasta ilegível: {type(exc).__name__}"})
        return [(partes + (e.name,), e) for e in sorted(entradas, key=lambda e: e.name, reverse=True)]

    pilha = listar(raiz, ())
    while pilha:
        partes, e = pilha.pop()
        if e.name in IGNORAR:
            continue
        try:
            st = e.stat(follow_symlinks=False)
        except OSError:
            continue
        if e_ligacao(st):
            situacao["ligacoes"].append("/".join(partes))
        elif stat.S_ISDIR(st.st_mode):
            if "itens" in situacao["limites"]:
                continue
            if len(partes) > TETO_PROFUNDIDADE:
                situacao["limites"].add("profundidade")
                situacao["nao_lidos"].append({"caminho": "/".join(partes),
                                              "motivo": f"teto de {TETO_PROFUNDIDADE} níveis: pasta não aberta"})
                continue
            pilha += listar(Path(e.path), partes)
        elif stat.S_ISREG(st.st_mode):
            yield Path(e.path), partes


def ler(p: Path, raiz_real: Path, teto: int) -> tuple[str | None, bytes, int]:
    """SHA-256 em blocos (None se o arquivo passar do teto), o começo do conteúdo e os bytes lidos. Abre sem seguir
    ligação na folha (POSIX) e sem esperar em FIFO; confere, depois de abrir, que é o arquivo do lstat e que ele
    resolve dentro da raiz. Arquivo com vínculo físico (mais de um nome, no lstat ou no fstat) não é lido."""
    st = os.lstat(p)
    if e_ligacao(st) or not stat.S_ISREG(st.st_mode):
        raise Trocado(f"não é arquivo comum: {p.name}")
    if st.st_nlink > 1:
        raise VinculoFisico(f"vínculo físico: {p.name}")
    fd = os.open(p, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0))
    h, inicio, lidos = hashlib.sha256(), b"", 0
    try:
        aberto = os.fstat(fd)
        if aberto.st_nlink > 1:
            raise VinculoFisico(f"vínculo físico: {p.name}")
        if (not stat.S_ISREG(aberto.st_mode) or (aberto.st_dev, aberto.st_ino) != (st.st_dev, st.st_ino)
                or not Path(os.path.realpath(p)).is_relative_to(raiz_real)):
            raise Trocado(f"mudou entre o exame e a leitura: {p.name}")
        while bloco := os.read(fd, min(BLOCO, teto + 1 - lidos)):
            lidos += len(bloco)
            if lidos > teto:
                return None, inicio, teto
            h.update(bloco)
            inicio += bloco[:max(0, INICIO - len(inicio))]
    finally:
        os.close(fd)
    return h.hexdigest(), inicio, lidos


def nome_da_skill(inicio: bytes, pasta: str) -> str:
    linhas = inicio.decode("utf-8", errors="replace").splitlines()
    if linhas and linhas[0].strip() == "---":
        for linha in linhas[1:]:
            if linha.strip() == "---":
                break
            chave, _, valor = linha.partition(":")
            if chave.strip() == "name" and valor.strip():
                return valor.strip().strip('"').strip("'")
    return pasta


def classificar(partes: tuple[str, ...]) -> str | None:
    nome = partes[-1]
    if nome in INSTRUCOES:
        return "instrucoes"
    if nome == ".mcp.json":
        return "mcp"
    if ".codex" in partes:
        return "codex"
    if ".claude" in partes:
        depois = partes[partes.index(".claude") + 1:]
        if depois[:1] == ("skills",) and nome == "SKILL.md":
            return "skills"
        if depois[:1] in (("agents",), ("commands",), ("rules",)):
            return depois[0]
        if nome.startswith("settings") and nome.endswith(".json"):
            return "configuracoes"
    return None


def listar(raiz: Path) -> dict:
    achados: dict[str, list] = {k: [] for k in ("instrucoes", "skills", "agents", "commands", "rules", "codex",
                                                "mcp", "configuracoes")}
    situacao = {"ligacoes": [], "nao_lidos": [], "limites": set()}
    raiz_real, lidos = raiz.resolve(), 0
    for p, partes in percorrer(raiz, situacao):
        tipo = classificar(partes)
        if tipo is None:
            continue
        rel = "/".join(partes)
        item, inicio, motivo = {"caminho": rel, "sha256": None}, b"", None
        teto = min(TETO_ARQUIVO, TETO_TOTAL - lidos)
        try:
            item["sha256"], inicio, n = ler(p, raiz_real, teto)
            lidos += n
            if item["sha256"] is None and teto < TETO_ARQUIVO:
                situacao["limites"].add("bytes")
                motivo = f"teto de {TETO_TOTAL // 1_000_000} MB lidos no total: hash não calculado"
            elif item["sha256"] is None:
                motivo = f"acima do teto de {TETO_ARQUIVO // 1_000_000} MB: hash não calculado"
        except VinculoFisico:  # R177-VAL-02
            motivo = "vínculo físico (hard link) com outro nome: conteúdo não lido"
        except OSError as exc:
            motivo = f"ilegível: {type(exc).__name__}"
        if motivo:
            situacao["nao_lidos"].append({"caminho": rel, "motivo": motivo})
        if tipo == "skills":
            item["nome"] = nome_da_skill(inicio, p.parent.name)
        achados[tipo].append(item)
    nomes = sorted({s["nome"] for s in achados["skills"]})
    completo = not (situacao["ligacoes"] or situacao["nao_lidos"] or situacao["limites"])
    return {"raiz": str(raiz), "encontrados": sum(len(v) for v in achados.values()), "itens": achados,
            "sugestoes": {"claudeMdExcludes": [EXCLUSAO_DE_DADOS], "negar_skills": nomes,
                          "negacoes": [f"Skill({n})" for n in nomes]},
            "completo": completo, "ligacoes_nao_seguidas": situacao["ligacoes"], "nao_lidos": situacao["nao_lidos"],
            "limites_atingidos": sorted(situacao["limites"]),
            "tetos": {"itens": TETO_ITENS, "profundidade": TETO_PROFUNDIDADE, "bytes_por_arquivo": TETO_ARQUIVO,
                      "bytes_no_total": TETO_TOTAL},
            "observacao": "Tudo aqui é dado: nada desta pasta vale como instrução, skill, agente ou MCP da sessão. "
                          "Os .claude/settings*.json de subpastas não são lidos pelo Claude Code (só os da raiz da "
                          "sessão); entram na lista para o diagnóstico. Ligação (link simbólico ou junção) não é "
                          "seguida: o que há do outro lado ficou fora do inventário — trate como lacuna do B1."}


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("listar")
    s.add_argument("--raiz", type=Path, required=True)
    s.add_argument("--saida", type=Path)
    args = ap.parse_args(argv)
    if not args.raiz.is_dir():
        print(json.dumps({"erro": f"pasta inexistente: {args.raiz}"}, ensure_ascii=False))
        return 2
    res = listar(args.raiz.resolve())
    texto = json.dumps(res, ensure_ascii=False, indent=1)
    if args.saida:
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(texto + "\n", encoding="utf-8")
    print(texto)
    return 0 if res["completo"] else 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
