#!/usr/bin/env python3
"""Registro de requisitos R01–R51 (Apêndice B) + R52–R60 (proposta 3.0).

  init       --saida matriz.csv [--sem-30]   copia o modelo (estados iniciais honestos)
  validar    --matriz matriz.csv [--base DIR] esquema + exame das evidências (erros -> código 1)
  relatorio  --matriz matriz.csv              resumo na ordem da A36: bloqueados, inativos, ativos

Regras de ESQUEMA (livro A36/Apêndice B) — `schema_ok`:
- estados permitidos: em_desenvolvimento | implementado_ativo | implementado_inativo | bloqueado
  (não existe "concluído com ressalvas");
- `simulado` explícito em toda linha: sim | nao (vazio é recusado);
- implementado_* exige caminho_evidencia, versao_avaliada e nivel_evidencia executado/validado,
  e simulado = nao (simulação/mock não demonstra integração real);
- implementado_inativo exige demonstracao_anterior e teste_desativacao;
- bloqueado exige bloqueio, impacto e condicao_resolucao;
- os identificadores R01–R51 precisam existir, sem duplicatas nem renumeração; se a matriz
  usa a proposta 3.0 (qualquer R52–R60 presente), todos os R52–R60 precisam existir.

EXAME DAS EVIDÊNCIAS (linhas implementado_*) — `evidencias`: o caminho existe (relativo a
`--base`; padrão: a raiz da fundação quando a matriz está em `<raiz>/registry/`, senão a pasta da
matriz), não está vazio e cita a `versao_avaliada` no conteúdo; se a coluna opcional
`sha256_evidencia` estiver preenchida, o hash do arquivo confere. Esquema válido NÃO é capacidade
demonstrada: o mérito da evidência (se ela prova o requisito) continua exigindo revisão humana.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "templates" / "MATRIZ-REQUISITOS.csv"
STATES = ("em_desenvolvimento", "implementado_ativo", "implementado_inativo", "bloqueado")
LEVELS = ("", "documentado", "codigo_presente", "executado", "validado")
REQUIRED_IDS = [f"R{i:02d}" for i in range(1, 52)]
IDS_30 = [f"R{i:02d}" for i in range(52, 61)]
SIM = {"sim", "s", "true"}
NAO = {"nao", "não", "n", "false"}
ALCANCE = ("schema_ok = estados, campos e identificadores; evidencias = o arquivo indicado existe, não está vazio, "
           "cita a versão avaliada e confere com sha256_evidencia quando informado. Nenhum dos dois prova que a "
           "evidência demonstra o requisito: isso continua exigindo revisão humana")


def base_padrao(matriz: Path) -> Path:
    pasta = Path(matriz).resolve().parent
    return pasta.parent if pasta.name == "registry" else pasta


def verify_evidence(rows: list[dict], base: Path) -> dict:
    """Exame das evidências das linhas implementadas (separado do esquema)."""
    conferidas, problemas, examinadas = [], [], 0
    for r in rows:
        if not r.get("estado", "").startswith("implementado") or not (r.get("caminho_evidencia") or "").strip():
            continue
        examinadas += 1
        rid, versao = r["id"], (r.get("versao_avaliada") or "").strip()
        caminho = Path(r["caminho_evidencia"].strip())
        alvo = caminho if caminho.is_absolute() else base / caminho
        esperado = (r.get("sha256_evidencia") or "").strip().lower()
        antes = len(problemas)
        if not alvo.exists():
            problemas.append(f"{rid}: evidência inexistente em '{caminho}' (base {base})")
        elif alvo.is_dir():
            arquivos = [p for p in sorted(alvo.rglob("*")) if p.is_file()][:500]
            if not arquivos:
                problemas.append(f"{rid}: pasta de evidência vazia em '{caminho}'")
            elif versao and not any(_cita(p, versao) for p in arquivos):
                problemas.append(f"{rid}: nenhuma evidência em '{caminho}' cita a versão avaliada '{versao}'")
            if esperado:
                problemas.append(f"{rid}: sha256_evidencia exige arquivo, não pasta ('{caminho}')")
        else:
            dados = alvo.read_bytes()
            if not dados:
                problemas.append(f"{rid}: evidência vazia em '{caminho}'")
            elif esperado and hashlib.sha256(dados).hexdigest() != esperado:
                problemas.append(f"{rid}: sha256 da evidência não confere com sha256_evidencia ('{caminho}')")
            elif versao and not _cita(alvo, versao) and not esperado:
                problemas.append(f"{rid}: evidência '{caminho}' não cita a versão avaliada '{versao}' "
                                 "(ou registre sha256_evidencia)")
        if len(problemas) == antes:
            conferidas.append(rid)
    return {"base": str(base), "examinadas": examinadas, "conferidas": conferidas, "problemas": problemas}


def _cita(arquivo: Path, versao: str) -> bool:
    try:
        if arquivo.stat().st_size > 5_000_000:
            return False
        return versao.lower() in arquivo.read_bytes().decode("utf-8", "ignore").lower()
    except OSError:
        return False


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def validate(rows: list[dict]) -> list[str]:
    errors = []
    ids = [r["id"] for r in rows]
    for dup, n in Counter(ids).items():
        if n > 1:
            errors.append(f"{dup}: identificador duplicado")
    for rid in REQUIRED_IDS:
        if rid not in ids:
            errors.append(f"{rid}: requisito do Apêndice B ausente")
    if any(rid in ids for rid in IDS_30):
        for rid in IDS_30:
            if rid not in ids:
                errors.append(f"{rid}: requisito da proposta 3.0 ausente (a matriz usa R52–R60)")
    for r in rows:
        rid, st = r["id"], r.get("estado", "")
        if st not in STATES:
            errors.append(f"{rid}: estado inválido '{st}'")
            continue
        if r.get("nivel_evidencia", "") not in LEVELS:
            errors.append(f"{rid}: nivel_evidencia inválido '{r.get('nivel_evidencia')}'")
        simulado = (r.get("simulado") or "").strip().lower()
        if simulado not in SIM | NAO:
            errors.append(f"{rid}: simulado vazio ou inválido '{r.get('simulado') or ''}': use sim ou nao")
        if st.startswith("implementado"):
            for field in ("caminho_evidencia", "versao_avaliada"):
                if not r.get(field, "").strip():
                    errors.append(f"{rid}: {st} sem {field}")
            if r.get("nivel_evidencia") not in ("executado", "validado"):
                errors.append(f"{rid}: {st} exige evidência executada ou validada")
            if simulado in SIM:
                errors.append(f"{rid}: simulação não demonstra o requisito; mantenha em_desenvolvimento ou bloqueado")
        if st == "implementado_inativo":
            for field in ("demonstracao_anterior", "teste_desativacao"):
                if not r.get(field, "").strip():
                    errors.append(f"{rid}: implementado_inativo sem {field}")
        if st == "bloqueado":
            for field in ("bloqueio", "impacto", "condicao_resolucao"):
                if not r.get(field, "").strip():
                    errors.append(f"{rid}: bloqueado sem {field}")
    return errors


def report(rows: list[dict]) -> dict:
    order = {"bloqueado": 0, "implementado_inativo": 1, "em_desenvolvimento": 2, "implementado_ativo": 3}
    by_state = Counter(r["estado"] for r in rows)
    lines = [
        {k: r.get(k, "") for k in ("id", "categoria", "estado", "nivel_evidencia", "bloqueio", "impacto",
                                   "condicao_resolucao", "caminho_evidencia", "responsavel_proximo_passo")}
        for r in sorted(rows, key=lambda r: (order.get(r["estado"], 9), r["id"]))
    ]
    return {"por_estado": dict(by_state), "total": len(rows), "linhas": lines}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init"); i.add_argument("--saida", type=Path, required=True)
    i.add_argument("--sem-30", action="store_true", help="omite R52–R60 (proposta 3.0)")
    v = sub.add_parser("validar"); v.add_argument("--matriz", type=Path, required=True)
    v.add_argument("--base", type=Path, help="pasta a que os caminhos de evidência são relativos")
    r = sub.add_parser("relatorio"); r.add_argument("--matriz", type=Path, required=True)
    args = ap.parse_args()
    if args.cmd == "init":
        if args.saida.exists():
            print(json.dumps({"erro": "matriz já existe; não sobrescrevo (atualize as linhas afetadas)"},
                             ensure_ascii=False))
            return 1
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        if args.sem_30:
            rows = [x for x in load(TEMPLATE) if x["id"] in REQUIRED_IDS]
            with args.saida.open("w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
                w.writeheader()
                w.writerows(rows)
        else:
            shutil.copyfile(TEMPLATE, args.saida)
        print(json.dumps({"criada": str(args.saida)}, ensure_ascii=False))
        return 0
    rows = load(args.matriz)
    if args.cmd == "validar":
        errors = validate(rows)
        evid = verify_evidence(rows, (args.base or base_padrao(args.matriz)).resolve())
        todos = errors + evid["problemas"]
        print(json.dumps({"ok": not todos, "schema_ok": not errors, "erros": todos, "erros_schema": errors,
                          "evidencias": evid, "linhas": len(rows), "alcance": ALCANCE}, ensure_ascii=False, indent=2))
        return 1 if todos else 0
    print(json.dumps(report(rows), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
