"""Pipeline legado fictício: lê um caso JSON e gera rascunho com fatos e pendências.

Comportamento a preservar (regras de domínio do projeto):
- só fatos com documento de origem entram em "Fatos";
- campos obrigatórios ausentes viram "Pendências";
- caso sem 'case_id' ou 'facts' -> erro com código 2, sem saída parcial;
- 'case_id' fora da forma de identificador (letra ou dígito, depois letras, dígitos, '-' ou '_';
  até 64) -> o mesmo erro: o rascunho vai sempre para saida/<case_id>.md, nunca para fora de saida/.
"""
import json
import re
import sys
from pathlib import Path

from scripts.exportar import exportar

OBRIGATORIOS = ("qualificacao", "endereco_reu", "competencia")
CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


def caso_invalido() -> int:
    print(json.dumps({"error": {"code": "E_CASO_INVALIDO"}}), file=sys.stderr)
    return 2


def main() -> int:
    caso_path = Path(sys.argv[1])
    try:
        caso = json.loads(caso_path.read_text(encoding="utf-8"))
        case_id, facts = caso["case_id"], caso["facts"]
    except (KeyError, json.JSONDecodeError):
        return caso_invalido()
    if not isinstance(case_id, str) or not CASE_ID.fullmatch(case_id):
        return caso_invalido()
    saida = Path("saida").resolve()
    out = saida / f"{case_id}.md"
    # Contenção conferida antes de escrever, com os caminhos resolvidos: nem a pasta saida/ nem o
    # arquivo podem levar (por junção ou ligação simbólica) para fora da pasta de trabalho.
    if saida.parent != Path.cwd().resolve() or out.resolve().parent != saida:
        return caso_invalido()
    fatos = [f for f in facts if f.get("doc")]
    sem_fonte = [f for f in facts if not f.get("doc")]
    pend = [c for c in OBRIGATORIOS if not caso.get(c)] + [f"fato sem fonte: {f['text']}" for f in sem_fonte]
    texto = exportar(case_id, fatos, pend)
    saida.mkdir(exist_ok=True)
    out.write_text(texto, encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
