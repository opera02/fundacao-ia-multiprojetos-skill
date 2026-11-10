"""`backup criar` cifrado (1.7.11; desenho DESENHO-COPIA-CIFRADA-1.7.11, §1.4): a cópia em claro nasce num PREPARO LOCAL (no
disco interno, fora da raiz e fora do disco das cópias), é conferida, cifrada para a chave pública, a cifrada é conferida sem a
senha e o preparo local é apagado. No disco das cópias só chega texto cifrado.

1. recusa preparo local dentro da raiz, dentro do destino ou já ocupado, e espaço livre menor que 2,5 vezes o estimado;
2. confere a chave pública (gpg, sem chave privada) ANTES de gastar minutos na cópia;
3. `create_backup(..., cifrada=True)` no preparo local (o manifesto interno diz que a cópia vai cifrada);
4. `verify_backup` do preparo local contra a âncora dele (= `sha256_manifesto_interno`);
5. `cifrar_copia`: lê o preparo local preso ao objeto listado e confere o SHA-256 de cada arquivo ao cifrar; promove;
6. `verificar_cifrada` sem senha (âncora, tamanho, hash, destinatário);
7. apaga o preparo local (limpeza contada: o que não sair vai em `sobra_do_preparo`).
O livro de cópias fica com a âncora do conteúdo (a do preparo local, gravada pelo `create_backup`) e com a da cifrada
(`cifrada: true`, `sha256_manifesto_interno`, `destinatario`): a pasta decifrada se restaura pela primeira. Falhou em qualquer
passo: nenhuma cópia cifrada promovida e o preparo local apagado.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import backup, limpeza
from .ancora_copia import LIVRO_COPIAS, dentro_da_copia
from .backup_cifrado import TAMANHO_PARTE, cifrar_copia, verificar_cifrada
from .cifra_copia import SessaoDeCifra
from .contracts import ValidationError
from .politica_cifra import pasta_de_dados

FATOR_DE_ESPACO = 2.5
_PULAR = frozenset(backup.EXCLUDE_PARTS) - {".git"}


def preparo_local_padrao(rotulo: str) -> Path:
    """%LOCALAPPDATA%\\FundacaoIA\\preparo-copias\\<rótulo> (no Linux, ~/.local/share/...)."""
    return pasta_de_dados() / "FundacaoIA" / "preparo-copias" / rotulo


def estimar_bytes(raiz: Path) -> int:
    """Tamanho do que a cópia leva (`FILE_DIRS` e o banco), por uma passada de `scandir` (sem abrir arquivo); conta o `.git` e
    tudo o mais por cima, e não conta o que a cópia pula. É estimativa: serve para recusar antes de começar."""
    total, pilha = 0, [Path(raiz) / "state" / "state.sqlite"]
    pilha += [Path(raiz) / nome for nome in backup.FILE_DIRS]
    while pilha:
        atual = pilha.pop()
        try:
            if atual.is_file():
                total += atual.stat().st_size
            elif atual.is_dir():
                with os.scandir(atual) as entradas:
                    for e in entradas:
                        if e.is_dir(follow_symlinks=False):
                            if e.name not in _PULAR:
                                pilha.append(Path(e.path))
                        elif e.is_file(follow_symlinks=False):
                            total += e.stat(follow_symlinks=False).st_size
        except OSError:
            continue
    return total


def _livre(pasta: Path) -> int:
    existente = Path(os.path.abspath(pasta))
    while not existente.exists() and existente.parent != existente:
        existente = existente.parent
    return shutil.disk_usage(existente).free


def criar_cifrada(raiz, destino, rotulo: str, chave_publica, *, preparo_local=None, tamanho_parte: int = TAMANHO_PARTE,
                  exe: str | None = None, fator_de_espaco: float = FATOR_DE_ESPACO) -> dict:
    """Cópia cifrada de `raiz` em `destino` (pasta nova), com o preparo local. Devolve o resultado do `create_backup` (lista
    de arquivos, git, db...) com os campos da cifrada por cima: `sha256_manifesto` é o do manifesto externo (a âncora a
    guardar), `sha256_manifesto_interno` o do conteúdo, `created_at` o da cifrada."""
    raiz, destino = Path(os.path.abspath(raiz)), Path(os.path.abspath(destino))
    local = Path(os.path.abspath(preparo_local or preparo_local_padrao(rotulo)))
    if dentro_da_copia(local, raiz) or dentro_da_copia(destino, raiz):
        raise ValidationError("o preparo local e o destino da cópia cifrada ficam fora da raiz da fundação",
                              preparo_local=str(local), destino=str(destino))
    if dentro_da_copia(local, destino) or dentro_da_copia(destino, local):
        raise ValidationError("o preparo local e o destino da cópia cifrada não podem conter um ao outro")
    if os.path.lexists(local):
        raise ValidationError("o preparo local já existe (sobra de uma cópia anterior?): confira e apague-o, ou use outro "
                              "--preparo-local", preparo_local=str(local))
    if destino.exists() and any(destino.iterdir()):
        raise FileExistsError("destino de backup não vazio: não substitua uma referência anterior")
    estimado = estimar_bytes(raiz)
    livre = _livre(local)
    if livre < fator_de_espaco * estimado:
        raise ValidationError(f"espaço livre insuficiente para o preparo local: {livre} bytes livres, {fator_de_espaco} vezes "
                              f"o estimado ({estimado} bytes) é o mínimo; use outro --preparo-local", livre=livre,
                              estimado=estimado, preparo_local=str(local))
    with SessaoDeCifra(chave_publica, exe):  # chave e gpg conferidos antes da cópia longa
        pass
    with limpeza.contada(local, local.parent) as sobra:
        copia = backup.create_backup(raiz, local, rotulo, cifrada=True)
        conferida = backup.verify_backup(local, sha256_manifesto=copia["sha256_manifesto"])
        if not conferida["ok"]:
            raise ValidationError("a cópia em claro do preparo local não conferiu contra a âncora dela: nada foi cifrado",
                                  verificacao=conferida)
        cifrada = cifrar_copia(local, destino, chave_publica, label=rotulo, tamanho_parte=tamanho_parte,
                               livro=raiz / "state" / LIVRO_COPIAS, exe=exe)
        verificacao = verificar_cifrada(destino, sha256_manifesto=cifrada["sha256_manifesto"],
                                        destinatario_esperado=cifrada["destinatario"]["principal"])
        if not verificacao["ok"]:
            raise ValidationError("a cópia cifrada recém-criada não passou na conferência sem senha: não use esta cópia",
                                  verificacao=verificacao, destino=str(destino))
    resultado = {**copia, "cifrada": True, "created_at": cifrada["created_at"], "created_at_interno": copia["created_at"],
                 "sha256_manifesto": cifrada["sha256_manifesto"], "sha256_manifesto_interno": cifrada["sha256_manifesto_interno"],
                 "destinatario": cifrada["destinatario"], "gpg_versao": cifrada["gpg_versao"], "partes": cifrada["partes"],
                 "preparo_local": str(local), "verificacao": verificacao, **limpeza.no_resultado(sobra)}
    resultado.pop("aviso", None)  # o texto junto das cópias em claro; os avisos da cifrada vão na lista
    avisos = [*(copia.get("avisos") or []), *(cifrada.get("avisos") or [])]
    if avisos:
        resultado["avisos"] = avisos
    else:
        resultado.pop("avisos", None)
    return resultado
