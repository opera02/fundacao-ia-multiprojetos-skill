"""Disco das decisões e da conclusão da tarefa (1.7.10; revisão de segurança da 1.7.10, POR-01, POR-02 e POR-03): a
decisão, a assinatura, a entrega, o registro e a saída da etapa do aceite, lidos e gravados pela pasta do projeto
conferida (core/disco_projeto.py), com os tetos de cada um.

Antes, pelo caminho: decisoes/ trocada por uma ligação no intervalo levava a decisão preparada para outro projeto ou
para state/ (state/manutencao.json vira trava de manutenção), a linha do registro e a saída da etapa do aceite também
iam para fora, o registro.jsonl e o <decisão>.json.sig ligados a um arquivo de outro projeto devolviam à sessão o
SHA-256 dele e o byte e a posição do primeiro erro de UTF-8, e um FIFO no lugar da decisão (ou da saída da etapa)
deixava o kit parado com a vez do banco na mão até o prazo do porteiro.

Os tetos cabem no tempo da vez do banco (revisão 1 do grupo KITDEC, POR-03): o registro era lido e analisado até
64 MiB, linha por linha, com a vez na mão (64 MiB de linhas "{}", cerca de 78 s de CPU pela medida da revisão; 8 MiB
delas, 4,3 s numa só análise, e a conclusão analisa duas vezes; o pedido de outro projeto esperava mais que os 15 s do
porteiro e não rodava). Agora vai até 8 MiB e 50 mil quebras de linha, contadas antes da análise (meio segundo por
análise no pior caso medido, em ext4).
"""

from __future__ import annotations

import errno
from pathlib import Path

from .canon import canonical_json, sha256_bytes
from .contracts import PathEscape
from .disco_projeto import Pasta, dentro, ler_arquivo  # noqa: F401 — decisoes.py usa por aqui
from .tasks import Coordinator, PermanentError, SaidaAlterada

TETO_DECISAO = 1 << 20      # a decisão canônica tem cerca de 1 KB
TETO_ASSINATURA = 64 << 10  # a assinatura SSHSIG, menos de 2 KB
TETO_REGISTRO = 8 << 20     # registro.jsonl: uma linha (600 a 800 bytes) por decisão registrada, cerca de 10 mil
TETO_LINHAS_REGISTRO = 50_000  # quebras de linha (\n e \r, as do splitlines), contadas antes da análise
TETO_ENTREGA = 1 << 30      # lida por partes; o teto limita o tempo com a vez do banco na mão (POR-03)
TETO_SAIDA = 1 << 20        # saída e recibo da etapa do aceite
RECUSADA = object()  # a assinatura existe, mas não é arquivo comum de um nome só até o teto: nada foi lido
ASSINATURA_RECUSADA = "assinatura recusada: ligação, vínculo físico, não é arquivo comum ou passa do teto (nada lido)"


def ler_ou_recusar(caminho, teto: int):
    """`ler_arquivo`, com o ausente como None e o recusado (ou ilegível) como RECUSADA, sem levantar."""
    try:
        return ler_arquivo(caminho, teto)
    except FileNotFoundError:
        return None
    except (OSError, PathEscape):
        return RECUSADA


def _no_projeto(pasta_projeto, caminho) -> tuple[Pasta, str]:
    """(pasta aberta, nome) de `caminho`, que quem chama já conferiu dentro de `pasta_projeto` (relativo a ela)."""
    partes = Path(caminho).relative_to(pasta_projeto).parts
    if not partes:
        raise PathEscape("caminho sem arquivo dentro do projeto: recusado", arquivo=Path(caminho).name)
    return Pasta(pasta_projeto, partes[:-1]), partes[-1]


def linhas_do_registro(bruto: bytes, registro) -> list[bytes]:
    """As linhas de registro.jsonl para a análise. Mais que TETO_LINHAS_REGISTRO quebras de linha: DecisaoInvalida
    antes de analisar qualquer linha (revisão 1 do KITDEC, POR-03: o tempo com a vez do banco na mão)."""
    if bruto.count(b"\n") + bruto.count(b"\r") > TETO_LINHAS_REGISTRO:
        from .decisoes import DecisaoInvalida  # tardio: decisoes importa este módulo
        raise DecisaoInvalida(f"registro de decisões com mais de {TETO_LINHAS_REGISTRO} linhas: recusado sem conferir "
                              "nenhuma", registro=str(registro), teto_linhas=TETO_LINHAS_REGISTRO)
    return bruto.splitlines()


def ler_na_pasta(caminho, teto: int, *, ausente: bytes | None = None) -> bytes:
    """Bytes de `<projeto>/<pasta>/<nome>` (a decisão, o registro), pela pasta aberta a partir do projeto. Ausente:
    `ausente`, ou FileNotFoundError."""
    caminho = Path(caminho)
    pasta, nome = _no_projeto(caminho.parent.parent, caminho)
    with pasta:
        bruto = pasta.ler(nome, teto)
    if bruto is None and ausente is None:
        raise FileNotFoundError(errno.ENOENT, "arquivo inexistente", str(caminho))
    return ausente if bruto is None else bruto


def sha256_no_projeto(pasta_projeto, alvo, *, recusar: bool = True) -> str | None:
    """SHA-256 da entrega `alvo` (resolvida e conferida dentro do projeto por quem chama), lida por partes pela pasta
    aberta, até TETO_ENTREGA; None se não existe. Ligação, FIFO, vínculo físico ou acima do teto: PathEscape (com
    `recusar` falso, None, como o ausente)."""
    try:
        pasta, nome = _no_projeto(pasta_projeto, alvo)
        with pasta:
            return pasta.ler(nome, TETO_ENTREGA, resumo=True)
    except FileNotFoundError:
        return None
    except (OSError, PathEscape):
        if recusar:
            raise
        return None


def decisao_e_assinatura(pasta_projeto, arquivo) -> tuple[bytes | None, object]:
    """(bytes da decisão ou None, bytes de `<decisão>.sig`, None se ausente ou RECUSADA), pela mesma pasta aberta. A
    decisão que é ligação, FIFO ou vínculo físico: PathEscape."""
    pasta, nome = _no_projeto(pasta_projeto, arquivo)
    with pasta:
        bruto = pasta.ler(nome, TETO_DECISAO)
        try:
            sig = pasta.ler(nome + ".sig", TETO_ASSINATURA) if bruto is not None else None
        except (OSError, PathEscape):
            sig = RECUSADA
    return bruto, sig


class CoordenadorDoAceite(Coordinator):
    """O Coordinator da conclusão da tarefa (`tarefa concluir`, o único comando do mapa do porteiro que roda uma
    execução): a saída da etapa e o recibo gravados, lidos de volta e apagados pela pasta aberta de
    outputs/runs/<execução>/ (POR-01 e POR-03). Antes, pelo caminho: outputs/ trocada por ligação levava os dois
    arquivos para fora do projeto, e um FIFO no lugar da saída deixava a conclusão repetida parada com a vez do banco na
    mão. Nomes, conteúdo e conferências são os de core/tasks.py; os outros usos do Coordinator não mudam."""

    def _pasta_da_execucao(self, run_id: str) -> Pasta:
        self._run_dir(run_id)  # a conferência de sempre: fora da pasta do projeto, PermanentError
        return Pasta(self.project_dir, (*self.runs_dir.relative_to(self.project_dir).parts, run_id))

    def _write_output(self, run_id: str, step_id: str, input_hash: str, data: bytes, *,
                      execution: int | None = None) -> tuple[str, str]:
        out = self._output_path(run_id, step_id, input_hash, execution)
        ref, digest = self._ref(out), sha256_bytes(data)
        recibo = {"run_id": run_id, "step_id": step_id, "input_hash": input_hash, "output_hash": digest}
        if execution is not None:
            recibo["execution"] = execution
        with self._pasta_da_execucao(run_id) as pasta:
            pasta.trocar(out.name, data)
            pasta.trocar(out.with_suffix(".receipt.json").name, canonical_json(recibo).encode("utf-8"))
        return ref, digest

    def _verified_output(self, row) -> bytes:
        if not row["output_ref"] or not row["output_hash"]:
            raise SaidaAlterada(f"saída sem referência ou hash no banco: {row['step_id']}")
        try:
            pasta, nome = _no_projeto(self.project_dir, self._abs(row["output_ref"]))
            with pasta:
                dado = pasta.ler(nome, TETO_SAIDA)
        except PermanentError:
            raise SaidaAlterada(f"saída registrada fora da pasta do projeto: {row['step_id']}") from None
        except (OSError, ValueError, PathEscape):
            dado = None
        if dado is None:
            raise SaidaAlterada(f"saída confirmada ausente ou ilegível: {row['step_id']}")
        if sha256_bytes(dado) != row["output_hash"]:
            raise SaidaAlterada(f"saída alterada depois da confirmação: {row['step_id']}")
        return dado

    def _descartar_saida(self, run_id: str, step_id: str, input_hash: str, execution: int) -> None:
        out = self._output_path(run_id, step_id, input_hash, execution)
        try:
            with self._pasta_da_execucao(run_id) as pasta:
                for nome in (out.name, out.with_suffix(".receipt.json").name):
                    pasta.apagar(nome, quieto=True)
        except (OSError, PathEscape, PermanentError):
            pass
