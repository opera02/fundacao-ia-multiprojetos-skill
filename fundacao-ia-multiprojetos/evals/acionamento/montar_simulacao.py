#!/usr/bin/env python3
"""Simulação de acionamento: monta o catálogo de skills concorrentes e pontua as escolhas.

O mecanismo real do host decide pelo nome + descrição de cada skill. Esta simulação
entrega a um agente separado o catálogo (descrições reais lidas dos SKILL.md instalados,
em ordem embaralhada) e as consultas SEM o gabarito; depois compara as escolhas.
É uma aproximação rotulada — não substitui `run_eval.py` do skill-creator (que usa
`claude -p` e consome cota; exige autorização).

  montar   --catalogo <skills.txt com um caminho de SKILL.md por linha> --saida <dir>
  pontuar  --respostas <respostas.json> --saida <dir>
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
EVALS = SKILL / "evals" / "trigger-evals.json"


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    import yaml  # usado só nesta ferramenta de avaliação
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def montar(catalogo: Path, saida: Path) -> int:
    caminhos = [Path(l.strip()) for l in catalogo.read_text(encoding="utf-8").splitlines() if l.strip()]
    skills = []
    for p in [SKILL / "SKILL.md", *caminhos]:
        fm = frontmatter(p)
        if fm.get("name") and fm.get("description"):
            skills.append({"name": str(fm["name"]), "description": " ".join(str(fm["description"]).split())})
    rnd = random.Random(20261018)
    rnd.shuffle(skills)
    consultas = json.loads(EVALS.read_text(encoding="utf-8"))
    ordem = list(range(len(consultas)))
    rnd.shuffle(ordem)
    saida.mkdir(parents=True, exist_ok=True)
    linhas = ["# Catálogo de skills disponíveis (nome: descrição)", ""]
    linhas += [f"- **{s['name']}**: {s['description']}" for s in skills]
    linhas += ["", "# Consultas", ""]
    linhas += [f"{i + 1}. {consultas[j]['query']}" for i, j in enumerate(ordem)]
    (saida / "simulacao-prompt.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    (saida / "ordem.json").write_text(json.dumps(ordem), encoding="utf-8")
    # O mapa de ordem é parte da evidência: sem ele, `pontuar` não se reproduz (auditoria F19).
    print(json.dumps({"skills_no_catalogo": len(skills), "consultas": len(consultas),
                      "entregar_juntos": ["simulacao-prompt.md", "ordem.json", "respostas.json", "resultado.json"]},
                     ensure_ascii=False))
    return 0


def pontuar(respostas: Path, saida: Path) -> int:
    consultas = json.loads(EVALS.read_text(encoding="utf-8"))
    mapa = saida / "ordem.json"
    if not mapa.is_file():
        print(json.dumps({"erro": f"{mapa} ausente: sem o mapa de ordem a pontuação não se reproduz"},
                         ensure_ascii=False), file=sys.stderr)
        return 2
    ordem = json.loads(mapa.read_text(encoding="utf-8"))
    resp = json.loads(respostas.read_text(encoding="utf-8"))
    linhas, acertos = [], 0
    for i, j in enumerate(ordem):
        escolha = (resp.get(str(i + 1)) or {}).get("skill") or "nenhuma"
        acionou = escolha == "fundacao-ia-multiprojetos"
        ok = acionou == consultas[j]["should_trigger"]
        acertos += ok
        linhas.append({"n": i + 1, "query": consultas[j]["query"], "esperado": consultas[j]["should_trigger"],
                       "escolha": escolha, "acertou": ok})
    tp = sum(1 for l in linhas if l["esperado"] and l["escolha"] == "fundacao-ia-multiprojetos")
    fp = sum(1 for l in linhas if not l["esperado"] and l["escolha"] == "fundacao-ia-multiprojetos")
    pos = sum(1 for l in linhas if l["esperado"])
    res = {"tipo": "simulação por agente separado (não é o mecanismo real do host)", "acertos": acertos,
           "total": len(linhas), "verdadeiros_positivos": tp, "positivos": pos, "falsos_positivos": fp,
           "ordem": ordem, "linhas": linhas}
    (saida / "resultado.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "linhas"}, ensure_ascii=False))
    return 0 if acertos == len(linhas) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("montar"); m.add_argument("--catalogo", type=Path, required=True); m.add_argument("--saida", type=Path, required=True)
    p = sub.add_parser("pontuar"); p.add_argument("--respostas", type=Path, required=True); p.add_argument("--saida", type=Path, required=True)
    a = ap.parse_args()
    return montar(a.catalogo, a.saida) if a.cmd == "montar" else pontuar(a.respostas, a.saida)


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
