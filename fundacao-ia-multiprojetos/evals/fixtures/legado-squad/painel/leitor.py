"""Painel legado: lista os agentes do squad.

Divergência de contrato (didática, livro A02 p13): este leitor espera
`squad.agents` como lista de STRINGS, mas o manifesto atual usa OBJETOS.
"""
import json
import sys
from pathlib import Path


def main() -> int:
    squad = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print("Agentes: " + ", ".join(squad["agents"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
