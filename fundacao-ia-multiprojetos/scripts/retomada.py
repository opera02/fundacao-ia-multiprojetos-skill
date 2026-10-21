#!/usr/bin/env python3
"""Registro de retomada (livro Apêndice E §3; continuidade entre sessões e provedores).

  criar    --saida RETOMADA.md   copia o modelo (não sobrescreve)
  validar  --arquivo RETOMADA.md exige os campos mínimos preenchidos (faltas -> código 1)
  arquivar --arquivo RETOMADA.md --historico <pasta> [--nome <arquivo>]
           guarda a versão inteira (não sobrescreve), confere byte a byte e acrescenta o ponteiro
           "Histórico arquivado: <caminho> (sha256 <hash>)"; depois, reescreva o índice de forma enxuta

Campos mínimos: objetivo, versão, estado confirmado, evidências, bloqueios,
próxima ação e efeitos já realizados (que não devem ser repetidos), além de
identificação do projeto/execução e arquivos mínimos para leitura.
Um campo vazio ou que ainda contenha "(preencher" conta como ausente. Use "nenhum" quando
não houver item — isso é uma informação, não uma omissão.

A validação é ESTRUTURAL: confere o preenchimento; não autentica quem escreveu, não confirma
evidências e não torna válida nenhuma autorização — o arquivo é índice de estado, não fonte de
permissão (auditoria da 1.4.1, A17). Sem "Origem das autorizações" preenchida, a saída traz um
aviso, que não bloqueia.

Índice enxuto (análise do vibe-coding-toolkit, 21/10/2026, proposta 7): acima de 12 KB, 150 linhas ou linha com
mais de 600 caracteres, o `validar` avisa (não bloqueia) e indica o `arquivar`. Ponteiro para histórico ausente
ou alterado reprova; e cada item de "Ações já realizadas que não devem ser repetidas" de um histórico arquivado
precisa continuar listado no índice — conferido pela parte do item antes do primeiro ":" (resumir o resto pode).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "templates" / "RETOMADA.md"
REQUIRED = {
    "project_id": r"^project_id:",
    "run_id de referência": r"^run_id de referência:",
    "objetivo atual": r"^Objetivo atual:",
    "versão do código/configuração": r"^Versão do código/configuração:",
    "estado confirmado": r"^Estado confirmado:",
    "evidências": r"^Evidências:",
    "arquivos mínimos para leitura": r"^Arquivos mínimos para leitura:",
    "bloqueios": r"^Bloqueios de acesso, custo ou decisão:",
    "próxima ação autorizada": r"^Próxima ação autorizada:",
    "efeitos já realizados": r"^Ações já realizadas que não devem ser repetidas:",
    "última conferência": r"^Última conferência do registro:",
}
ORIGEM = r"^Origem das autorizações:"
EFEITOS = r"^Ações já realizadas que não devem ser repetidas:"
CAMPO = re.compile(r"^[A-Za-zÀ-ú_ /]+:")
PONTEIRO = re.compile(r"^Histórico arquivado:\s*(?P<caminho>\S+)\s+\(sha256 (?P<sha>[0-9a-f]{64})\)")
LIMITE_BYTES, LIMITE_LINHAS, LIMITE_LINHA = 12_000, 150, 600
VALIDACAO = "estrutural (preenchimento): não autentica autor, autorizações nem evidências"


def field_value(lines: list[str], pattern: str) -> str:
    for idx, line in enumerate(lines):
        if re.match(pattern, line.strip()):
            value = line.split(":", 1)[1].strip()
            nxt = idx + 1
            while not value and nxt < len(lines) and lines[nxt].strip() and not re.match(r"^[A-Za-zÀ-ú_ /]+:", lines[nxt].strip()):
                value = lines[nxt].strip()
                nxt += 1
            if not value and nxt < len(lines):
                follow = []
                while nxt < len(lines) and re.match(r"^\s*(\d+\.|-)\s+\S", lines[nxt]):
                    follow.append(lines[nxt].strip())
                    nxt += 1
                value = " ".join(follow)
            return value
    return ""


def secao(lines: list[str], pattern: str) -> list[str]:
    """Linhas de um campo de várias linhas: da linha do campo até o próximo campo."""
    for idx, line in enumerate(lines):
        if re.match(pattern, line.strip()):
            fim = idx + 1
            while fim < len(lines) and not CAMPO.match(lines[fim].strip()):
                fim += 1
            return lines[idx:fim]
    return []


def itens_nao_repetir(lines: list[str]) -> list[str]:
    """Chave de cada item de "Ações já realizadas...": o texto do item antes do primeiro ":" (até 100 caracteres)."""
    itens = []
    for line in secao(lines, EFEITOS)[1:]:
        if line.strip().startswith("- "):
            texto = " ".join(line.strip()[2:].split())
            itens.append(texto.split(":", 1)[0].strip()[:100])
    return itens


def historicos(arquivo: Path, lines: list[str]) -> list[dict]:
    out = []
    for line in lines:
        m = PONTEIRO.match(line.strip())
        if not m:
            continue
        caminho = (arquivo.parent / m.group("caminho")).resolve()
        if not caminho.is_file():
            estado = "ausente"
        else:
            estado = "conferido" if hashlib.sha256(caminho.read_bytes()).hexdigest() == m.group("sha") else "alterado"
        out.append({"caminho": m.group("caminho"), "sha256": m.group("sha"), "estado": estado, "_abs": caminho})
    return out


def tamanho(texto: str, lines: list[str]) -> tuple[dict, list[str]]:
    medida = {"bytes": len(texto.encode("utf-8")), "linhas": len(lines),
              "maior_linha": max((len(l) for l in lines), default=0)}
    avisos = []
    if medida["bytes"] > LIMITE_BYTES:
        avisos.append(f"índice grande: {medida['bytes']} bytes (limite sugerido {LIMITE_BYTES // 1000} KB)")
    if medida["linhas"] > LIMITE_LINHAS:
        avisos.append(f"índice longo: {medida['linhas']} linhas (limite sugerido {LIMITE_LINHAS} linhas)")
    if medida["maior_linha"] > LIMITE_LINHA:
        avisos.append(f"linha com {medida['maior_linha']} caracteres (limite sugerido {LIMITE_LINHA} caracteres)")
    if avisos:
        avisos.append("arquive o histórico (retomada.py arquivar) e deixe o índice só com o estado atual e uma "
                      "linha por efeito já realizado")
    return medida, avisos


def validar(arquivo: Path) -> dict:
    texto = arquivo.read_text(encoding="utf-8")
    lines = texto.splitlines()
    missing = []
    for name, pattern in REQUIRED.items():
        value = field_value(lines, pattern)
        if not value or "(preencher" in value:
            missing.append(name)
    origem = field_value(lines, ORIGEM)
    avisos = [] if origem and "(preencher" not in origem else [
        "origem das autorizações não registrada: permissões e próxima ação valem só se confirmadas na conversa atual"]
    medida, avisos_tamanho = tamanho(texto, lines)
    avisos += avisos_tamanho
    hist = historicos(arquivo, lines)
    atuais = set(itens_nao_repetir(lines))
    ausentes = []
    for h in hist:
        if h["estado"] == "conferido":
            antigos = itens_nao_repetir(h["_abs"].read_text(encoding="utf-8").splitlines())
            ausentes += [i for i in antigos if i not in atuais and i not in ausentes]
    ok = not missing and all(h["estado"] == "conferido" for h in hist) and not ausentes
    return {"ok": ok, "campos_ausentes": missing, "avisos": avisos, "tamanho": medida,
            "historicos": [{k: v for k, v in h.items() if k != "_abs"} for h in hist],
            "itens_do_historico_ausentes": ausentes, "validacao": VALIDACAO}


def arquivar(arquivo: Path, pasta: Path, nome: str | None) -> tuple[int, dict]:
    original = arquivo.read_bytes()
    nome = nome or f"RETOMADA-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.md"
    destino = pasta / nome
    if destino.exists():
        return 1, {"ok": False, "erro": f"o histórico {destino} já existe; não sobrescrevo"}
    pasta.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(original)
    h = hashlib.sha256(original).hexdigest()
    if hashlib.sha256(destino.read_bytes()).hexdigest() != h:  # releitura antes de qualquer outra mudança
        destino.unlink()
        return 1, {"ok": False, "erro": "a cópia do histórico não conferiu; nada foi alterado"}
    try:
        rel = destino.resolve().relative_to(arquivo.resolve().parent).as_posix()
    except ValueError:
        rel = destino.resolve().as_posix()
    ponteiro = f"Histórico arquivado: {rel} (sha256 {h})"
    lines = original.decode("utf-8").splitlines()
    pos = next((i for i, l in enumerate(lines) if re.match(REQUIRED["project_id"], l.strip())), 0)
    lines.insert(pos, ponteiro)
    arquivo.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return 0, {"ok": True, "historico": str(destino), "sha256": h, "ponteiro": ponteiro,
               "itens_nao_repetir": len(itens_nao_repetir(lines)),
               "proximo_passo": "reescreva a RETOMADA de forma enxuta: estado atual e uma linha por item de "
                                "'Ações já realizadas' (a parte antes do primeiro ':' é conferida pelo validar)"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("criar"); c.add_argument("--saida", type=Path, required=True)
    v = sub.add_parser("validar"); v.add_argument("--arquivo", type=Path, required=True)
    a = sub.add_parser("arquivar"); a.add_argument("--arquivo", type=Path, required=True)
    a.add_argument("--historico", type=Path, required=True, help="pasta dos históricos (ex.: evidence/retomada)")
    a.add_argument("--nome", help="nome do arquivo do histórico (padrão: RETOMADA-<data>.md)")
    args = ap.parse_args()
    if args.cmd == "criar":
        if args.saida.exists():
            print(json.dumps({"erro": "RETOMADA já existe; atualize-a em vez de recriar"}, ensure_ascii=False))
            return 1
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TEMPLATE, args.saida)
        print(json.dumps({"criada": str(args.saida)}, ensure_ascii=False))
        return 0
    if not args.arquivo.exists():
        print(json.dumps({"ok": False, "erro": "arquivo de retomada inexistente"}, ensure_ascii=False))
        return 1
    if args.cmd == "arquivar":
        codigo, res = arquivar(args.arquivo, args.historico, args.nome)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return codigo
    res = validar(args.arquivo)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
