"""Limpeza contada das pastas de preparo do kit (1.7.10; desenho 1.7.10, §5.8; MELHORIAS-1.7.10, §0 item 15).

Até a 1.7.9, o preparo do backup e da restauração, a cópia privada do banco na autorização e a pasta temporária da
criação de projeto saíam por `shutil.rmtree(..., ignore_errors=True)`: o que não saía ficava em silêncio. Em 31/10/2026
o `backup criar` falhou na renomeação final e deixou 551 pastas vazias com a marca somente leitura no disco das cópias;
na restauração não liberada, a sobra pode ser a raiz inteira, em claro. Agora:
- `limpar(pasta, dentro_de)` apaga de baixo para cima, sem seguir ligação (link simbólico ou junção sai como ligação, e
  o que ela aponta não é tocado). No Windows, a recusa por permissão tira a marca somente leitura (`os.chmod` com
  `S_IWRITE`, que lá só mexe nesse atributo) do próprio item — sempre um item da pasta de preparo, alcançado sem
  atravessar ligação — e tenta de novo; o que resiste ganha outras passadas, com esperas curtas (antivírus ou
  indexador com o arquivo aberto). No fim, conta o que sobrou: {limpa, arquivos, pastas, ligacoes, bytes, erros}.
- `contada(pasta, dentro_de)` limpa ao sair do bloco. Na falha, a contagem vai nos detalhes do erro (erro do contrato)
  ou no atributo `sobra_do_preparo` (os demais), e a CLI do backup avisa (W_SOBRA_DO_PREPARO): nada some em silêncio.
  A sobra pode ter dados da fundação: apagá-la é do titular, depois de conferir.
Limite (o mesmo de preparo.py): na mesma conta do sistema, quem troca uma pasta por ligação exatamente entre a
conferência e a remoção ainda redireciona a operação; cada pasta é conferida (identidade e ligação) depois de listada,
e a que mudou fica, com o erro.
"""

from __future__ import annotations

import os
import stat
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from .contracts import FundacaoError
from .preparo import _e_ligacao_st, _identidade

NO_WINDOWS = os.name == "nt"
ESPERAS = (0.1, 0.5, 1.5)  # entre as passadas: curtas, para a limpeza não segurar a resposta
LIMITE_DE_ERROS = 10  # exemplos de erro na contagem: caminho relativo, tipo e código; nunca conteúdo
AVISO_SOBRA = ("a pasta de preparo não foi apagada por inteiro: veja a contagem e o caminho. Ela pode ter dados da "
               "fundação (cópia em claro); confira e apague só com o OK do titular — nada foi escondido")
# Injetáveis nos testes (falha num caminho, sem esperar de verdade).
_apagar_arquivo = os.unlink
_apagar_pasta = os.rmdir
_esperar = time.sleep


def _tirar_somente_leitura(caminho: Path) -> None:
    """Só no Windows: tira a marca somente leitura do próprio item, sem seguir ligação."""
    if os.chmod in os.supports_follow_symlinks:  # 3.13 em diante: o padrão passou a seguir a ligação
        os.chmod(caminho, stat.S_IWRITE, follow_symlinks=False)
    else:  # até o 3.12, no Windows, o chmod muda o atributo do próprio item (conferido numa junção em 31/10/2026)
        os.chmod(caminho, stat.S_IWRITE)


def _apagar_ligacao(caminho: Path) -> None:
    """Tira a ligação sem tocar o que ela aponta (no Windows, o unlink tira também junção e link de pasta)."""
    try:
        _apagar_arquivo(caminho)
    except OSError:
        if not NO_WINDOWS:
            raise
        _apagar_pasta(caminho)  # outra ligação de pasta do Windows: RemoveDirectory tira só a ligação


def _apagar(caminho: Path, funcao, erros: list) -> None:
    try:
        funcao(caminho)
        return
    except FileNotFoundError:
        return
    except OSError as exc:
        erro = exc
    if NO_WINDOWS and isinstance(erro, PermissionError):
        try:
            if os.lstat(caminho).st_nlink <= 1:  # vínculo físico (nlink>1): o chmod tiraria a marca do arquivo de fora (#7)
                _tirar_somente_leitura(caminho)
                funcao(caminho)
                return
        except FileNotFoundError:
            return
        except OSError as exc:
            erro = exc
    erros.append((caminho, erro))


def _passada(pasta: Path, erros: list) -> None:
    """Uma passada de baixo para cima, sem atravessar ligação. Cada pasta é listada e conferida em seguida: trocada
    (ligação ou outra pasta no lugar), nada do que foi listado nela é apagado."""
    try:
        st = os.lstat(pasta)
    except FileNotFoundError:
        return
    if _e_ligacao_st(st) or not stat.S_ISDIR(st.st_mode):
        _apagar(pasta, _apagar_ligacao if _e_ligacao_st(st) else _apagar_arquivo, erros)
        return
    pilha = [(pasta, _identidade(st), False)]
    while pilha:
        atual, esperada, listada = pilha.pop()
        if listada:  # os filhos já passaram
            _apagar(atual, _apagar_pasta, erros)
            continue
        try:
            with os.scandir(atual) as entradas:
                nomes = sorted(e.name for e in entradas)
            depois = os.lstat(atual)
        except FileNotFoundError:
            continue
        except OSError as exc:
            erros.append((atual, exc))
            continue
        if _e_ligacao_st(depois) or _identidade(depois) != esperada:
            erros.append((atual, OSError("pasta trocada durante a limpeza (ligação ou outra): nada dela apagado")))
            continue
        pilha.append((atual, esperada, True))
        for nome in nomes:
            caminho = atual / nome
            try:
                st = os.lstat(caminho)
            except FileNotFoundError:
                continue
            except OSError as exc:
                erros.append((caminho, exc))
                continue
            if _e_ligacao_st(st):
                _apagar(caminho, _apagar_ligacao, erros)
            elif stat.S_ISDIR(st.st_mode):
                pilha.append((caminho, _identidade(st), False))
            else:
                _apagar(caminho, _apagar_arquivo, erros)


def contar(pasta: Path) -> dict:
    """O que existe sob `pasta` (ela inclusive), sem atravessar ligação: arquivos, pastas, ligações e bytes."""
    conta = {"arquivos": 0, "pastas": 0, "ligacoes": 0, "bytes": 0}
    pilha = [Path(pasta)]
    while pilha:
        atual = pilha.pop()
        try:
            st = os.lstat(atual)
        except OSError:
            continue
        if _e_ligacao_st(st):
            conta["ligacoes"] += 1
        elif stat.S_ISDIR(st.st_mode):
            conta["pastas"] += 1
            try:
                with os.scandir(atual) as entradas:
                    pilha.extend(Path(e.path) for e in entradas)
            except OSError:
                pass  # pasta que não se lista conta só ela
        else:
            conta["arquivos"] += 1
            conta["bytes"] += st.st_size
    return conta


def _ligacao_no_meio(base: Path, pasta: Path) -> bool:
    """Alguma pasta entre `base` e `pasta` (as duas fora) é ligação: apagar ali iria para outro lugar."""
    partes = pasta.relative_to(base).parts
    for i in range(1, len(partes)):
        try:
            if _e_ligacao_st(os.lstat(base.joinpath(*partes[:i]))):
                return True
        except OSError:
            continue
    return False


def _descrever(caminho: Path, pasta: Path, exc: BaseException) -> dict:
    try:
        rel = Path(caminho).relative_to(pasta).as_posix()
    except ValueError:
        rel = str(caminho)
    codigo = getattr(exc, "winerror", None) or getattr(exc, "errno", None)
    # Erro do sistema: tipo e código bastam. Recusa da própria limpeza (sem código): o motivo, que não tem conteúdo.
    return {"caminho": rel, "erro": type(exc).__name__, "codigo": codigo, **({} if codigo else {"motivo": str(exc)})}


def limpar(pasta, dentro_de) -> dict:
    """Apaga `pasta` — pasta de preparo criada pelo kit dentro de `dentro_de` — e conta o que sobrou (ver o módulo).
    Pasta fora de `dentro_de`, ou com ligação no meio do caminho, não é apagada: vai contada, com o erro. Nunca levanta:
    a limpeza não esconde o erro principal de quem chama."""
    pasta, base = Path(os.path.abspath(pasta)), Path(os.path.abspath(dentro_de))
    erros: list = []
    try:
        if pasta == base or base not in pasta.parents:
            erros.append((pasta, ValueError("fora da pasta em que o kit cria o preparo: nada apagado")))
        elif _ligacao_no_meio(base, pasta):
            erros.append((pasta, ValueError("ligação no caminho da pasta de preparo: nada apagado")))
        else:
            for espera in (*ESPERAS, None):
                erros = []
                _passada(pasta, erros)
                if espera is None or not os.path.lexists(pasta):
                    break
                _esperar(espera)
    except Exception as exc:  # defeito inesperado: conta e informa, sem trocar o erro de quem chama
        erros.append((pasta, exc))
    sobrou = os.path.lexists(pasta)
    conta = contar(pasta) if sobrou else {"arquivos": 0, "pastas": 0, "ligacoes": 0, "bytes": 0}
    return {"pasta": str(pasta), "limpa": not sobrou, **conta,
            "erros": [_descrever(c, pasta, e) for c, e in erros[:LIMITE_DE_ERROS]]}


def anotar(exc: BaseException, sobra: dict) -> None:
    """Põe a contagem da sobra no erro: nos detalhes, se é erro do contrato (sai no JSON da CLI); senão, no atributo
    `sobra_do_preparo`, que a CLI do backup mostra como W_SOBRA_DO_PREPARO. Limpeza completa não acrescenta nada."""
    if sobra.get("limpa", True):
        return
    if isinstance(exc, FundacaoError):
        exc.details.setdefault("sobra_do_preparo", dict(sobra))
        return
    try:
        exc.sobra_do_preparo = dict(sobra)
    except AttributeError:  # exceção sem atributos próprios: fica só a contagem devolvida a quem limpou
        pass


def no_resultado(sobra: dict) -> dict:
    """{"sobra_do_preparo": ...} para juntar a uma resposta, só quando a limpeza não foi completa."""
    return {} if sobra.get("limpa", True) else {"sobra_do_preparo": dict(sobra)}


@contextmanager
def contada(pasta, dentro_de, respostas=()):
    """Limpa `pasta` ao sair do bloco, com ou sem erro. Na falha, a contagem vai com o erro (`anotar`). Na saída
    normal, fica no dicionário entregue e, se sobrou algo, também em cada resposta de `respostas` — as de "não liberar"
    dadas com o preparo existindo, que já tinham sido devolvidas quando a limpeza roda."""
    sobra: dict = {}
    try:
        yield sobra
    except BaseException as exc:
        sobra.update(limpar(pasta, dentro_de))
        anotar(exc, sobra)
        raise
    sobra.update(limpar(pasta, dentro_de))
    for resposta in respostas:
        resposta.update(no_resultado(sobra))


def na_falha(pasta, dentro_de) -> dict:
    """Dentro de um `except`: limpa `pasta` e anota a sobra no erro em tratamento (ver `anotar`)."""
    sobra = limpar(pasta, dentro_de)
    exc = sys.exc_info()[1]
    if exc is not None:
        anotar(exc, sobra)
    return sobra
