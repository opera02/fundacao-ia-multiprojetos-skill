"""Preparar e registrar assinatura do livro; chave e assinatura ficam com o titular."""
from pathlib import Path

from .core import decisoes, livro_assinado
from .core.auth import Policy
from .core.contracts import ValidationError
from .core.paths import contained
from .core.projects import project_root


def registrar_parser(subparsers):
    p = subparsers.add_parser("copia-assinatura", help="assinaturas do titular nas entradas do livro de cópias")
    p.add_argument("acao", choices=("preparar", "registrar"))
    p.add_argument("--projeto", required=True)
    p.add_argument("--sha256-manifesto")
    p.add_argument("--arquivo", type=Path)
    return p


def executar(args, con, principal, tombstone_log=None):
    Policy(con).require(principal, "admin", "foundation")
    projeto = project_root(args.raiz, con, principal, args.projeto, action="write")
    pasta = projeto / "outputs/copias-assinadas"
    livro = args.raiz / "state/copias.jsonl"
    if args.acao == "preparar":
        if not isinstance(args.sha256_manifesto, str) or not livro_assinado.SHA.fullmatch(args.sha256_manifesto):
            raise ValidationError("informe --sha256-manifesto com 64 dígitos hexadecimais")
        path = contained(projeto, pasta / (args.sha256_manifesto + ".json"), within=projeto)
        resultado = livro_assinado.preparar(livro, args.sha256_manifesto, principal.principal_id, path)
        ancora = decisoes.ancora_padrao()
        if ancora:
            resultado["para_o_titular"] = decisoes.comando_para_o_titular(
                path, assinante=principal.principal_id, ancora=ancora, namespace=livro_assinado.NAMESPACE)
        return resultado
    if args.arquivo is None:
        raise ValidationError("informe --arquivo (o documento preparado em outputs/copias-assinadas)")
    path = contained(projeto, args.arquivo if args.arquivo.is_absolute() else projeto / args.arquivo, within=projeto)
    if path.parent != pasta or path.suffix != ".json":
        raise ValidationError("o documento deve estar em outputs/copias-assinadas")
    return livro_assinado.registrar(livro, path)
