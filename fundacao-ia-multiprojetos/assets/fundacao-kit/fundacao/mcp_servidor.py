"""Servidor MCP da fundação (livro A11C; R34): ferramentas de LEITURA de projeto pela
camada de autorização da fundação.

- A identidade vem do processo do servidor (`FUNDACAO_PRINCIPAL`, definida pelo lançador
  ou pela configuração do host), nunca de argumento de ferramenta.
- Cada chamada autoriza ANTES de ler (negativa registrada como `access_denied`); a
  resposta de recurso alheio não traz conteúdo.
- Sem o pacote `mcp` (SDK Python 2.x) o servidor não inicia: bloqueio explícito. Uma pasta `mcp/` sem `__init__`
  no caminho de importação (a raiz, no uso normal) não é o SDK: conta como ausente e não é importada (revisão de
  segurança da 1.7.7, terceira passada, R177C-B-03).
- Na sessão de projeto travada do Ubuntu (o cliente do porteiro ativo, ou FUNDACAO_PROJETO_TRAVADO definida), o
  servidor não inicia (1.7.10, correção do lote 2): ele abriria o banco direto, por fora da fila e do mapa do porteiro.
  A sessão usa `python -m fundacao ...`, que vai ao porteiro; o perfil do projeto também não tem MCP (mcp.json vazio).
  Com a raiz em /mnt/e, onde o sandbox não confinou os comandos (§0 dos contratos), é camada lógica.

Uso (transporte stdio):  python -m fundacao.mcp_servidor --raiz <raiz-da-fundacao>
Ferramentas: listar_projetos(), listar_documentos(projeto), buscar(projeto, consulta).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from . import KIT_VERSION, porteiro_cliente


def bloqueio_da_sessao() -> str | None:
    """O motivo para não iniciar na sessão de projeto travada, ou None fora dela: o cliente do porteiro ativo
    (FUNDACAO_PORTEIRO sem FUNDACAO_PORTEIRO_SERVIDOR) ou a trava de projeto ligada (FUNDACAO_PROJETO_TRAVADO definida,
    mesmo com valor errado, como em core/auth.py)."""
    from .core.auth import ENV_TRAVA, trava
    if porteiro_cliente.ativo():
        return ("sessão de projeto com o porteiro (FUNDACAO_PORTEIRO): o servidor MCP do kit não inicia aqui, porque "
                "abriria o banco por fora do porteiro; use `python -m fundacao ...`, que vai ao porteiro")
    if trava()[0]:
        return (f"modo travado ({ENV_TRAVA}): o servidor MCP do kit não inicia na sessão de projeto, porque abriria o "
                "banco por fora do porteiro; use `python -m fundacao ...`, que vai ao porteiro")
    return None


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
    if (motivo := bloqueio_da_sessao()) is not None:  # também para quem o monta no próprio processo (1.7.10)
        from .core.contracts import AccessDenied
        raise AccessDenied(motivo)
    if not sdk_do_mcp_instalado():  # o `main` mostra "pacote mcp ausente"; nada da pasta `mcp/` roda (R177C-B-03)
        raise ImportError("SDK do MCP ausente: nenhum pacote comum mcp no caminho de importação")
    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError

    from .cli_conhecimento import ler_catalogo
    from .core.auth import principal_from_env
    from .core.contracts import FundacaoError
    from .core.db import connect
    from .core.knowledge import KnowledgeService
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
            # O mesmo ajudante da CLI: na pasta do projeto (auditoria F04), sem seguir ligação e sem vínculo físico
            # com o catálogo de outro projeto (F6 da revisão de segurança da 1.7.9).
            return ler_catalogo(pasta)
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
    if (motivo := bloqueio_da_sessao()) is not None:  # antes de tudo: nem o banco é olhado na sessão travada
        sys.stderr.write(json.dumps({"estado": "bloqueado", "motivo": motivo}, ensure_ascii=False) + "\n")
        return 3
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
