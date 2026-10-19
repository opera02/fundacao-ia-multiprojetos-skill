"""Executor isolado de componentes: lê a requisição em stdin e devolve JSON em stdout.

Chamado somente por `components.dispatch`, depois da autorização. Diagnóstico
vai para stderr; stdout fica reservado ao resultado.
"""

from __future__ import annotations

import importlib
import json
import sys


def main() -> int:
    module_name, func_name = sys.argv[1], sys.argv[2]
    # Defesa em profundidade (o despacho já conferiu): só código da própria fundação.
    if not module_name.startswith("fundacao.components.") or not func_name.isidentifier():
        sys.stderr.write("ponto de entrada fora de fundacao.components: recusado\n")
        return 2
    request = json.loads(sys.stdin.read())
    module = importlib.import_module(module_name)
    result = getattr(module, func_name)(request)
    # JSON só com ASCII: o resultado chega íntegro qualquer que seja a página de código do console.
    sys.stdout.write(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
