"""Pipeline legado fictício: lê um caso JSON e gera rascunho com fatos e pendências.

Comportamento a preservar (regras de domínio do projeto):
- só fatos com documento de origem entram em "Fatos";
- campos obrigatórios ausentes viram "Pendências";
- caso sem 'case_id' ou 'facts' -> erro com código 2, sem saída parcial.
"""
import json
import sys
from pathlib import Path

from scripts.exportar import exportar

OBRIGATORIOS = ("qualificacao", "endereco_reu", "competencia")


def main() -> int:
    caso_path = Path(sys.argv[1])
    try:
        caso = json.loads(caso_path.read_text(encoding="utf-8"))
        case_id, facts = caso["case_id"], caso["facts"]
    except (KeyError, json.JSONDecodeError):
        print(json.dumps({"error": {"code": "E_CASO_INVALIDO"}}), file=sys.stderr)
        return 2
    fatos = [f for f in facts if f.get("doc")]
    sem_fonte = [f for f in facts if not f.get("doc")]
    pend = [c for c in OBRIGATORIOS if not caso.get(c)] + [f"fato sem fonte: {f['text']}" for f in sem_fonte]
    texto = exportar(case_id, fatos, pend)
    out = Path("saida") / f"{case_id}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(texto, encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
