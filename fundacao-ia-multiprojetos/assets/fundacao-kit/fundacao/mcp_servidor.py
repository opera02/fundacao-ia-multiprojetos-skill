"""Servidor MCP da fundação (livro A11C; R34): ferramentas de LEITURA de projeto pela
camada de autorização da fundação.

- A identidade vem do processo do servidor (`FUNDACAO_PRINCIPAL`, definida pelo lançador
  ou pela configuração do host), nunca de argumento de ferramenta.
- Cada chamada autoriza ANTES de ler (negativa registrada como `access_denied`); a
  resposta de recurso alheio não traz conteúdo.
- Sem o pacote `mcp` (SDK Python 2.x) o servidor não inicia: bloqueio explícito. Uma pasta `mcp/` sem `__init__`
  no caminho de importação (a raiz, no uso normal) não é o SDK: conta como ausente e não é importada (revisão de
  segurança da 1.7.7, terceira passada, R177C-B-03).

Uso (transporte stdio):  python -m fundacao.mcp_servidor --raiz <raiz-da-fundacao>
Ferramentas: listar_projetos(), listar_documentos(projeto), buscar(projeto, consulta).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from . import KIT_VERSION


def _pacote_de_namespace(spec) -> bool:
    """Pacote de namespace (pasta sem `__init__`): sem origem (ou com a marca "namespace" de versões antigas do
    Python), sem carregador ou com o carregador de namespace, que o Python põe ao carregá-lo."""
    return spec.origin in (None, "namespace") or spec.loader is None \
        or type(spec.loader).__name__ in ("NamespaceLoader", "_NamespaceLoader")


def sdk_do_mcp_instalado() -> bool:
    """O SDK do MCP está instalado como pacote comum? Sem pacote comum `mcp` no caminho de importação, o Python monta
    um pacote de namespace com a pasta `mcp/` que achar (a da raiz, no uso normal, com ela como pasta atual), e
    importar `mcp.server` rodaria o `server/__init__.py` dela: namespace conta como SDK ausente. A consulta não executa
    nada (`find_spec` de nome de primeiro nível só lê as pastas do caminho); já carregado sem `__spec__` (o dublê dos
    testes, posto pelo próprio processo), vale o que está carregado (R177C-B-03)."""
    try:
        spec = importlib.util.find_spec("mcp")
    except ValueError:  # em sys.modules sem __spec__: nada vem do disco
        return True
    return spec is not None and not _pacote_de_namespace(spec)


def criar_servidor(raiz: Path):
    if not sdk_do_mcp_instalado():  # o `main` mostra "pacote mcp ausente"; nada da pasta `mcp/` roda (R177C-B-03)
        raise ImportError("SDK do MCP ausente: nenhum pacote comum mcp no caminho de importação")
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
