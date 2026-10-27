"""Comandos de backup, com identidade e conexão fornecidas pela entrada principal."""
import json
import sys

from .core import backup, livro_assinado, preparo
from .core.auth import Policy, principal_from_env
from .core.ancora_copia import _fundacao_viva
from .core.contracts import FundacaoError, ValidationError


def executar(args, conectar):
    if args.acao == "criar":
        if not args.destino:
            raise FundacaoError("informe --destino (pasta nova ou vazia para a cópia)")
        con = conectar(args.raiz)
        try:
            Policy(con).require(principal_from_env(con), "admin", "foundation")
        finally:
            con.close()
        return backup.create_backup(args.raiz, args.destino, args.rotulo)
    if not args.origem:
        raise FundacaoError("informe --origem (pasta da cópia)")
    if getattr(args, "exigir_livro_assinado", False):
        # Com raiz viva, a ACL atual deve negar antes de ler manifesto ou livro.
        # Sem raiz viva, a assinatura ainda vem antes de confiar na ACL da cópia.
        # autorizar() reconfere a autorização depois da prova, inclusive revogações.
        _fundacao_viva(args.raiz, args.origem)
    livro = (args.raiz / "state" / backup.LIVRO_COPIAS if args.acao == "verificar"
             else args.retiradas.parent / backup.LIVRO_COPIAS if args.retiradas else None)
    if getattr(args, "exigir_livro_assinado", False):
        if livro is None or backup.dentro_da_copia(livro, args.origem):
            raise ValidationError("livro assinado deve ficar fora da cópia")
        sha = livro_assinado.ancora_do_livro(livro, preparo.ler(args.origem / "manifest.json"))
        if args.sha256_manifesto and args.sha256_manifesto != sha:
            raise ValidationError("hash informado diverge da assinatura do livro")
        args.sha256_manifesto = sha  # prova criptográfica verificada, não o hash de uma entrada sem assinatura
    autorizacao = backup.autorizar(args.raiz, args.origem, sha256_manifesto=args.sha256_manifesto, livro=livro)
    if args.acao == "verificar":
        return {**backup.verify_backup(args.origem, sha256_manifesto=args.sha256_manifesto, livro=livro),
                "autorizacao": autorizacao}
    if not args.destino:
        raise FundacaoError("informe --destino (pasta nova)")
    resultado = backup.restore(args.origem, args.destino, args.retiradas, executado_por=autorizacao["identidade"],
                               aceitar_registro_nao_comprovado=args.aceitar_registro_nao_comprovado,
                               sha256_manifesto=args.sha256_manifesto, livro=livro,
                               aceitar_copia_sem_ancora=args.aceitar_copia_sem_ancora)
    resultado["autorizacao"] = autorizacao
    if resultado.get("released") and resultado.get("aviso_ancora"):
        codigo = "W_ANCORA_DO_LIVRO" if resultado["ancora"]["situacao"] == "conferida" else "W_COPIA_SEM_ANCORA"
        sys.stderr.write(json.dumps({"aviso": {"code": codigo, "message": resultado["aviso_ancora"]}},
                                    ensure_ascii=False) + "\n")
    return resultado
