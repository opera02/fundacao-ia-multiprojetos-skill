"""Servidor MCP da fundação (livro A11C; R34): ferramentas de LEITURA de projeto pela
camada de autorização da fundação.

- A identidade vem do processo do servidor (`FUNDACAO_PRINCIPAL`, definida pelo lançador
  ou pela configuração do host), nunca de argumento de ferramenta.
- Cada chamada autoriza ANTES de ler (negativa registrada como `access_denied`); a
  resposta de recurso alheio não traz conteúdo.
- Sem o pacote `mcp` (SDK Python 2.x) o servidor não inicia: bloqueio explícito.

Uso (transporte stdio):  python -m fundacao.mcp_servidor --raiz <raiz-da-fundacao>
Ferramentas: listar_projetos(), listar_documentos(projeto), buscar(projeto, consulta).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import KIT_VERSION


def criar_servidor(raiz: Path):
    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError

    from .core.auth import principal_from_env
    from .core.contracts import FundacaoError
    from .core.db import connect
    from .core.knowledge import KnowledgeService
    from .core.paths import contained
    from .core.projects import list_projects, project_root

    raiz = Path(raiz).resolve()
    app = MCPServer("fundacao-ia-multiprojetos", version=KIT_VERSION, log_level="WARNING",
                    instructions="Ferramentas de leitura da fundação; a identidade é a do processo do servidor.")

    def _executar(fn):
        con = connect(raiz / "state" / "state.sqlite")
        try:
            return fn(con, principal_from_env(con))
        except FundacaoError as exc:
            raise ToolError(str(exc)) from None  # mensagem curta, sem conteúdo protegido
        finally:
            con.close()

    @app.tool()
    def listar_projetos() -> list[str]:
        """Projetos que a identidade desta sessão pode ler."""
        return _executar(lambda con, me: [p["project_id"] for p in list_projects(con, me)])

    @app.tool()
    def listar_documentos(projeto: str) -> list[str]:
        """Identificadores do catálogo (data/catalog.json) de um projeto autorizado."""
        def fn(con, me):
            pasta = project_root(raiz, con, me, projeto, action="read")  # autoriza antes de ler
            # O arquivo final e seus ancestrais ficam na pasta do projeto: ligação para o catálogo
            # (ou a pasta de dados) de outro projeto é recusada antes da leitura (auditoria F04).
            catalogo = contained(pasta / "data", pasta / "data" / "catalog.json", within=pasta)
            return sorted(json.loads(catalogo.read_text(encoding="utf-8"))) if catalogo.exists() else []
        return _executar(fn)

    @app.tool()
    def buscar(projeto: str, consulta: str) -> list[dict]:
        """Trechos aprovados e vigentes do projeto (busca do kit), com citação verificável."""
        def fn(con, me):
            hits = KnowledgeService(raiz, con, me).search(projeto, consulta)
            return [{"citacao": h["citation"], "trecho": h["body"][:500]} for h in hits]
        return _executar(fn)

    return app


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", type=Path, required=True)
    args = ap.parse_args(argv)
    if not (args.raiz / "state" / "state.sqlite").is_file():
        sys.stderr.write(json.dumps({"estado": "bloqueado", "motivo": "fundação sem banco de estado"},
                                    ensure_ascii=False) + "\n")
        return 3
    if (args.raiz / "state" / "restauracao-nao-liberada.json").exists():
        sys.stderr.write(json.dumps({"estado": "bloqueado", "motivo": "raiz de restauração não liberada"},
                                    ensure_ascii=False) + "\n")
        return 3
    try:
        app = criar_servidor(args.raiz)
    except ImportError:
        sys.stderr.write(json.dumps({"estado": "bloqueado", "motivo": "pacote mcp ausente; instalar exige autorização"},
                                    ensure_ascii=False) + "\n")
        return 3
    app.run()  # stdio
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
