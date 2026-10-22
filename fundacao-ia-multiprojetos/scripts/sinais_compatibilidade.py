#!/usr/bin/env python3
"""Sinais objetivos de compatibilidade de um projeto existente (Fluxo B, etapa B3).

Varre o código-fonte em busca de sinais que pesam na classificação:
  - caminhos absolutos ou '..' saindo da raiz (isolamento por projeto);
  - credenciais embutidas em código ou arquivos de segredo presentes;
  - chamadas de rede/serviços externos (dependência e efeito externo);
  - ausência de testes; dependências declaradas sem versão fixada.
O relatório SUGERE uma classe (integração direta · adaptação por interfaces ·
refatoração delimitada · bloqueio nas condições atuais) com os motivos. A decisão
final é registrada no plano de adaptação, com as evidências do diagnóstico — este
script não lê conteúdo de casos nem valores de segredos (só o nome do arquivo e a
linha onde há atribuição suspeita).

Não segue ligação (link simbólico ou junção): ela vai para `ligacoes_nao_seguidas` e o que há do outro lado não é
lido. Tetos aplicados durante a varredura: 100 mil itens, 32 níveis, 5 MB por arquivo e 200 MB no total; o que ficou
de fora vai para `nao_lidos`, e a leitura parcial entra nos motivos — a classe nunca sai "integração direta" assim
(auditoria Codex Security da 1.7.6, #7). Arquivo com vínculo físico (hard link, mais de um nome) também vai para
`nao_lidos`, sem leitura: o outro nome pode estar fora da raiz (revisão de segurança da 1.7.7, R177-VAL-02).

Uso: python sinais_compatibilidade.py --raiz PROJETO [--saida sinais.json]
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import stat
import sys
from pathlib import Path

CODE_SUFFIXES = {".py", ".js", ".ts", ".ps1", ".sh", ".bat", ".cmd", ".rb", ".go", ".java", ".cs"}
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules"}
SECRET_FILES = [".env", ".env.*", "*.pem", "*.key", "*.pfx", "auth.json", "*credentials*"]
ABS_PATH = re.compile(r"""["'](?:[A-Za-z]:[\\/]|/(?:home|Users|mnt|srv|var|etc)/)[^"']+["']""")
PARENT_ESCAPE = re.compile(r"""["'][^"']*\.\.[\\/][^"']*["']""")
CRED_ASSIGN = re.compile(r"""(?i)\b(api[_-]?key|token|senha|password|secret|chave)\w*\s*[:=]\s*["'][^"']{6,}["']""")
NETWORK = re.compile(r"""(?i)\b(requests\.(get|post|put)|urllib\.request|http\.client|httpx\.|fetch\(|socket\.|smtplib|ftplib)""")
TETO_ITENS = 100_000          # entradas examinadas (arquivos e pastas)
TETO_PROFUNDIDADE = 32        # níveis de pasta abaixo da raiz
TETO_ARQUIVO = 5_000_000      # bytes lidos de um arquivo
TETO_TOTAL = 200_000_000      # bytes lidos no total
BLOCO = 1 << 20
# Windows: etiqueta de ponto de nova análise "substituta de nome" (bit 29) — junção, link simbólico e afins.
SUBSTITUTA_DE_NOME = 0x20000000


class AcimaDoTeto(Exception):
    pass


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
        if e.name in SKIP_DIRS:
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


def ler_texto(p: Path, raiz_real: Path, teto: int) -> tuple[str, int]:
    """Texto do arquivo comum `p` e os bytes lidos, em blocos até `teto` bytes (passou: AcimaDoTeto). Abre sem seguir
    ligação na folha (POSIX) e sem esperar em FIFO; confere, depois de abrir, que é o arquivo do lstat e que resolve
    dentro da raiz. Arquivo com vínculo físico (mais de um nome, no lstat ou no fstat) não é lido."""
    st = os.lstat(p)
    if e_ligacao(st) or not stat.S_ISREG(st.st_mode):
        raise Trocado(f"não é arquivo comum: {p.name}")
    if st.st_nlink > 1:
        raise VinculoFisico(f"vínculo físico: {p.name}")
    fd = os.open(p, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0))
    try:
        aberto = os.fstat(fd)
        if aberto.st_nlink > 1:
            raise VinculoFisico(f"vínculo físico: {p.name}")
        if (not stat.S_ISREG(aberto.st_mode) or (aberto.st_dev, aberto.st_ino) != (st.st_dev, st.st_ino)
                or not Path(os.path.realpath(p)).is_relative_to(raiz_real)):
            raise Trocado(f"mudou entre o exame e a leitura: {p.name}")
        dados = bytearray()
        while bloco := os.read(fd, min(BLOCO, teto + 1 - len(dados))):
            dados += bloco
            if len(dados) > teto:
                raise AcimaDoTeto
    finally:
        os.close(fd)
    return dados.decode("utf-8", errors="replace"), len(dados)


def scan(root: Path) -> dict:
    signals = {"caminho_absoluto": [], "escape_da_raiz": [], "credencial_embutida": [],
               "arquivo_de_segredo": [], "rede_ou_servico_externo": [], "dependencia_sem_versao": []}
    has_tests = False
    situacao = {"ligacoes": [], "nao_lidos": [], "limites": set()}
    raiz_real, lidos = root.resolve(), 0

    def ler(path: Path, rel: str) -> str | None:
        nonlocal lidos
        teto = min(TETO_ARQUIVO, TETO_TOTAL - lidos)
        try:
            texto, n = ler_texto(path, raiz_real, teto)
        except AcimaDoTeto:
            if teto < TETO_ARQUIVO:
                situacao["limites"].add("bytes")
            motivo = (f"teto de {TETO_TOTAL // 1_000_000} MB lidos no total" if teto < TETO_ARQUIVO
                      else f"acima do teto de {TETO_ARQUIVO // 1_000_000} MB")
            situacao["nao_lidos"].append({"caminho": rel, "motivo": motivo + ": não lido"})
            return None
        except VinculoFisico:  # R177-VAL-02
            situacao["nao_lidos"].append({"caminho": rel,
                                          "motivo": "vínculo físico (hard link) com outro nome: não lido"})
            return None
        except OSError as exc:
            situacao["nao_lidos"].append({"caminho": rel, "motivo": f"ilegível: {type(exc).__name__}"})
            return None
        lidos += n
        return texto

    for path, partes in percorrer(root, situacao):
        rel = "/".join(partes)
        name = path.name.lower()
        if any(fnmatch.fnmatch(name, g) for g in SECRET_FILES):
            signals["arquivo_de_segredo"].append(rel)
            continue  # não lê segredos
        if name.startswith("test") or "tests" in partes:
            has_tests = True
        if name in ("requirements.txt",):
            texto = ler(path, rel)
            for i, line in enumerate((texto or "").splitlines(), 1):
                line = line.strip()
                if line and not line.startswith("#") and "==" not in line:
                    signals["dependencia_sem_versao"].append(f"{rel}:{i}")
        if path.suffix.lower() not in CODE_SUFFIXES:
            continue
        texto = ler(path, rel)
        for i, line in enumerate((texto or "").splitlines(), 1):
            loc = f"{rel}:{i}"
            if ABS_PATH.search(line):
                signals["caminho_absoluto"].append(loc)
            if PARENT_ESCAPE.search(line):
                signals["escape_da_raiz"].append(loc)
            if CRED_ASSIGN.search(line):
                signals["credencial_embutida"].append(loc)
            if NETWORK.search(line):
                signals["rede_ou_servico_externo"].append(loc)
    reasons = []
    if signals["caminho_absoluto"] or signals["escape_da_raiz"]:
        reasons.append("acesso a caminhos fora da raiz do projeto: isolamento exige refatoração")
    if signals["credencial_embutida"]:
        reasons.append("credencial embutida no código: mover para cofre antes de integrar")
    if signals["rede_ou_servico_externo"]:
        reasons.append("dependência de rede/serviço externo: confirmar acesso, custo e idempotência")
    if not has_tests:
        reasons.append("sem testes: criar caracterização (golden master) antes de mudar")
    if signals["arquivo_de_segredo"]:
        reasons.append("arquivo de segredo presente: excluir de cópias, manifestos e contexto")
    if signals["dependencia_sem_versao"]:
        reasons.append("dependências sem versão fixada: registrar versões antes de reconstruir")
    if situacao["ligacoes"]:
        reasons.append("ligações (link simbólico ou junção) não seguidas: o outro lado não foi examinado; confira "
                       "para onde apontam (podem sair da raiz)")
    if situacao["nao_lidos"] or situacao["limites"]:
        reasons.append("varredura parcial (teto atingido ou arquivo não lido): sinais podem faltar")
    if (signals["caminho_absoluto"] or signals["escape_da_raiz"]) and signals["rede_ou_servico_externo"] \
            and signals["credencial_embutida"]:
        suggested = "bloqueio nas condições atuais"
    elif signals["caminho_absoluto"] or signals["escape_da_raiz"] or signals["credencial_embutida"]:
        suggested = "refatoração delimitada"
    elif reasons:
        suggested = "adaptação por interfaces"
    else:
        suggested = "integração direta"
    return {"schema_version": "fundacao.sinais_compatibilidade/1", "raiz": root.name,
            "sinais": signals, "tem_testes": has_tests, "classe_sugerida": suggested,
            "motivos": reasons,
            "completo": not (situacao["ligacoes"] or situacao["nao_lidos"] or situacao["limites"]),
            "ligacoes_nao_seguidas": situacao["ligacoes"], "nao_lidos": situacao["nao_lidos"],
            "limites_atingidos": sorted(situacao["limites"]),
            "tetos": {"itens": TETO_ITENS, "profundidade": TETO_PROFUNDIDADE, "bytes_por_arquivo": TETO_ARQUIVO,
                      "bytes_no_total": TETO_TOTAL},
            "aviso": "sugestão baseada em sinais estáticos; confirme com o diagnóstico (B1–B2) e registre a decisão"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", type=Path, required=True)
    ap.add_argument("--saida", type=Path)
    args = ap.parse_args()
    result = scan(args.raiz.resolve())
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.saida:
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
