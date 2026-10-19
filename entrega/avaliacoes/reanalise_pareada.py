#!/usr/bin/env python3
"""Reanálise PAREADA do benchmark histórico das avaliações com subagentes (auditoria F19).

O resumo do `aggregate_benchmark` comparava a média dos 8 cenários com a skill (E1–E8) com a média
dos 7 sem a skill (E1–E7): cenários diferentes nos dois lados. Aqui a diferença é calculada par a
par, só nos cenários que têm as duas configurações; o cenário só com a skill (E8) vai à parte.
`tool_calls` e `errors` saíram 0 em todos os runs porque não foram coletados (valor padrão do
agregador): ficam como `nao_medido`. Um run por configuração e cenário: não há estimativa de
variabilidade do mesmo pedido. Os números são da skill 1.0.0 (iteração 1): não medem a 1.3.4 nem a 1.4.0.

Uso: python reanalise_pareada.py [--benchmark <benchmark.json>] [--saida <json>]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PADRAO = AQUI / "subagentes-iteracao-1" / "benchmark.json"
SAIDA = AQUI / "reanalise-pareada-iteracao-1.json"


def reanalisar(bench: dict) -> dict:
    pares: dict[int, dict] = {}
    for r in bench["runs"]:
        pares.setdefault(r["eval_id"], {})[r["configuration"]] = r["result"]
    completos = {e: p for e, p in sorted(pares.items()) if set(p) == {"with_skill", "without_skill"}}
    so_com = {e: p["with_skill"] for e, p in sorted(pares.items()) if set(p) == {"with_skill"}}
    pareado: dict = {"pares": len(completos), "cenarios": [f"E{e}" for e in completos]}
    for m in ("time_seconds", "tokens"):
        com = statistics.mean(p["with_skill"][m] for p in completos.values())
        sem = statistics.mean(p["without_skill"][m] for p in completos.values())
        deltas = [p["with_skill"][m] - p["without_skill"][m] for p in completos.values()]
        pareado[m] = {"media_com_skill": round(com, 2), "media_sem_skill": round(sem, 2),
                      "delta_medio": round(statistics.mean(deltas), 2),
                      "delta_relativo_pct": round(statistics.mean(deltas) / sem * 100, 2),
                      "por_cenario": {f"E{e}": d for e, d in zip(completos, deltas)}}
    pareado["pass_rate"] = {f"E{e}": {"com": p["with_skill"]["pass_rate"], "sem": p["without_skill"]["pass_rate"]}
                            for e, p in completos.items()}
    zerados = {k: all(r["result"].get(k) == 0 for r in bench["runs"]) for k in ("tool_calls", "errors")}
    return {
        "fonte": "benchmark.json da iteração 1 (skill 1.0.0); recálculo determinístico, não é rodada nova",
        "publicado_antes": bench.get("run_summary", {}).get("delta"),
        "pareado": pareado,
        "so_com_a_skill": {f"E{e}": {"time_seconds": r["time_seconds"], "tokens": r["tokens"],
                                     "pass_rate": r["pass_rate"]} for e, r in so_com.items()},
        "telemetria": {k: ("nao_medido" if zerados[k] else "medido") for k in zerados},
        "limites": ["um run por configuração e cenário: sem variabilidade do mesmo pedido",
                    "E2–E7 tinham o kit instalado na linha de base: mede o ganho das instruções sobre o kit",
                    "unidades de tempo e tokens do benchmark histórico; não é custo faturado",
                    "não mede a 1.3.4 nem a 1.4.0"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--benchmark", type=Path, default=PADRAO)
    ap.add_argument("--saida", type=Path, default=SAIDA)
    a = ap.parse_args()
    res = reanalisar(json.loads(a.benchmark.read_text(encoding="utf-8")))
    a.saida.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    p = res["pareado"]
    print(json.dumps({"pares": p["pares"], "delta_tempo_s": p["time_seconds"]["delta_medio"],
                      "delta_tokens": p["tokens"]["delta_medio"], "telemetria": res["telemetria"],
                      "saida": str(a.saida)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
