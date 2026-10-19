#!/usr/bin/env python3
"""Registro de retomada (livro Apêndice E §3; continuidade entre sessões e provedores).

  criar    --saida RETOMADA.md   copia o modelo (não sobrescreve)
  validar  --arquivo RETOMADA.md exige os campos mínimos preenchidos (faltas -> código 1)

Campos mínimos: objetivo, versão, estado confirmado, evidências, bloqueios,
próxima ação e efeitos já realizados (que não devem ser repetidos), além de
identificação do projeto/execução e arquivos mínimos para leitura.
Um campo vazio ou que ainda contenha "(preencher" conta como ausente. Use "nenhum" quando
não houver item — isso é uma informação, não uma omissão.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("criar"); c.add_argument("--saida", type=Path, required=True)
    v = sub.add_parser("validar"); v.add_argument("--arquivo", type=Path, required=True)
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
    lines = args.arquivo.read_text(encoding="utf-8").splitlines()
    missing = []
    for name, pattern in REQUIRED.items():
        value = field_value(lines, pattern)
        if not value or "(preencher" in value:
            missing.append(name)
    print(json.dumps({"ok": not missing, "campos_ausentes": missing}, ensure_ascii=False, indent=2))
    return 1 if missing else 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
