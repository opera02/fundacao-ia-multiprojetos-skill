"""Pasta temporária própria dos testes das avaliações (revisão de segurança da 1.7.7, terceira passada, R177C-T-01).

`isolamento.conferir_vizinhanca` recusa a área do executor e a pasta cega com nome do gabarito ao lado de uma das
três pastas acima delas (`<algo>-workspace`, `eval-N`, `iteration-N`, `evals`...). A área padrão do preparo e as
pastas que os testes criam ficam na pasta temporária do sistema: no Windows, as três pastas acima são %TEMP%,
%LOCALAPPDATA% e AppData. Uma pasta `<skill>-workspace` deixada ali pelo skill-creator fazia 11 testes falharem (e
4 classes nem montarem), e o resultado dependia da máquina de quem roda a liberação. A regra está certa: o executor
que lista as pastas acima da área veria o workspace. O que mudou foi o teste.

`ligar()` cria uma pasta nova na pasta temporária do sistema, duas pastas de nome neutro abaixo dela, e põe a mais
funda em `tempfile.tempdir` e em TMPDIR, TEMP e TMP (os processos filhos herdam): as três pastas acima de tudo o
que os testes criam são deles. Devolve a função que desfaz (e apaga a pasta); o módulo de teste a registra com
`unittest.addModuleCleanup`:

    BASE = _modulo("base_temporaria_<módulo>", Path(__file__).with_name("base_temporaria.py"))

    def setUpModule():
        unittest.addModuleCleanup(BASE.ligar())

Lido pelo caminho (como os módulos de evals/), não como pacote: funciona com `unittest discover` e com o módulo de
teste carregado à parte.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

VARIAVEIS = ("TMPDIR", "TEMP", "TMP")


def ligar():
    """Liga a pasta temporária própria e devolve a função que a desliga (ambiente e `tempfile.tempdir` como
    estavam; a pasta é apagada)."""
    antes = {nome: os.environ.get(nome) for nome in VARIAVEIS}, tempfile.tempdir
    raiz = Path(tempfile.mkdtemp(prefix="base-")).resolve()
    base = raiz / "b" / "t"
    base.mkdir(parents=True)
    for nome in VARIAVEIS:
        os.environ[nome] = str(base)
    tempfile.tempdir = str(base)

    def desligar() -> None:
        for nome, valor in antes[0].items():
            if valor is None:
                os.environ.pop(nome, None)
            else:
                os.environ[nome] = valor
        tempfile.tempdir = antes[1]
        shutil.rmtree(raiz, ignore_errors=True)

    return desligar
