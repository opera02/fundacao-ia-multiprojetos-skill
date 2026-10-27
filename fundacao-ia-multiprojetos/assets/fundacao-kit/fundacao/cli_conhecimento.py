"""Catálogo e busca de um projeto pela autorização da fundação: as leituras do servidor MCP (listar_documentos e
buscar), na CLI. É o caminho para pedir conteúdo de um projeto, mesmo esperando recusa: a negativa fica na trilha
(access_denied) e volta como erro, sem conteúdo."""
import json

from .core.contracts import ValidationError
from .core.knowledge import KnowledgeService
from .core.paths import contained
from .core.projects import project_root


def registrar_parser(subparsers):
    p = subparsers.add_parser("conhecimento", help="catálogo e busca de um projeto, pela autorização da fundação")
    p.add_argument("acao", choices=("listar", "buscar"))
    p.add_argument("--projeto", required=True)
    p.add_argument("--consulta", default="", help="buscar: termos da busca nos trechos aprovados e vigentes")
    return p


def executar(args, con, principal, tombstone_log=None):
    if args.acao == "listar":
        pasta = project_root(args.raiz, con, principal, args.projeto, action="read")  # autoriza antes de ler
        # O catálogo e seus ancestrais ficam na pasta do projeto, como no servidor MCP (auditoria F04).
        catalogo = contained(pasta / "data", pasta / "data" / "catalog.json", within=pasta)
        try:
            documentos = sorted(json.loads(catalogo.read_text(encoding="utf-8"))) if catalogo.exists() else []
        except (TypeError, UnicodeDecodeError, ValueError):
            raise ValidationError("catálogo do projeto ilegível", projeto=args.projeto) from None
        return {"projeto": args.projeto, "documentos": documentos}
    # Como no MCP, a busca autoriza antes de olhar a consulta: o pedido sem termos também deixa a negativa na trilha.
    hits = KnowledgeService(args.raiz, con, principal, tombstone_log).search(args.projeto, args.consulta)
    return {"projeto": args.projeto,
            "trechos": [{"citacao": h["citation"], "trecho": h["body"][:500]} for h in hits]}
