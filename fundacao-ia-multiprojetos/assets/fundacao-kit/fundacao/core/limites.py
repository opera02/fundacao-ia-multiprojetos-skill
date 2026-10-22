"""Tetos de recursos dos componentes (auditoria Codex Security da 1.7.6, #9).

Prazo e autorização não limitam memória: um pedido enorme, um arquivo enorme ou um filho que escreve sem parar
enchem a memória antes do prazo. O registro do componente (`registry/components/<id>.json`) pode declarar
`limits`; o que ele não declara vale pelo padrão abaixo, e nome desconhecido ou valor que não seja inteiro positivo
torna o registro inválido (erro de digitação não desliga um teto em silêncio). Quem aplica:
- o despacho (`core/components.py`) confere o pedido serializado ANTES de iniciar o processo e passa os tetos de
  stdout e stderr ao executor (`core/processo.py`), que encerra a árvore ao passar deles; o resultado decodificado
  é o JSON de stdout, limitado pelo teto dele;
- os de arquivo vão no pedido (`limits`) ao componente que lê arquivos: o `source_manifest` recusa antes de ler
  (pelo tamanho no disco) e lê em blocos, sem passar do teto.
"""

from __future__ import annotations

from .contracts import ValidationError

_MIB = 1024 * 1024
PADRAO = {
    "request_bytes": 1 * _MIB,        # pedido serializado (JSON) que vai ao componente pela entrada padrão
    "stdout_bytes": 4 * _MIB,         # resultado: o JSON que o componente escreve em stdout
    "stderr_bytes": 1 * _MIB,         # diagnóstico
    "max_files": 1000,                # documentos por pedido
    "file_bytes": 1024 * _MIB,        # bytes de cada arquivo lido
    "total_file_bytes": 4096 * _MIB,  # bytes somados dos arquivos lidos num pedido
}


def limites_do_componente(entry: dict) -> dict:
    """Tetos do componente: os declarados em `limits` sobre o padrão. Declaração inválida: ValidationError."""
    declarados = entry.get("limits", {})
    if not isinstance(declarados, dict):
        raise ValidationError("limits deve ser um objeto", component_id=entry.get("component_id"))
    desconhecidos = sorted(set(declarados) - set(PADRAO))
    if desconhecidos:
        raise ValidationError("limits com nome desconhecido", component_id=entry.get("component_id"),
                              nomes=desconhecidos, conhecidos=sorted(PADRAO))
    for nome, valor in declarados.items():
        if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
            raise ValidationError(f"limits.{nome} deve ser inteiro positivo (bytes ou quantidade)",
                                  component_id=entry.get("component_id"))
    return {**PADRAO, **declarados}
