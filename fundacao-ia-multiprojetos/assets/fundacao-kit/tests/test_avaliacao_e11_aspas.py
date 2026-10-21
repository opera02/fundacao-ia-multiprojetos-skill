"""Avaliação E11 (21/10/2026), achado F-01: o comando que o kit entrega ao titular para colar no PowerShell.

O PowerShell trata como aspa simples, além do apóstrofo ASCII, as aspas tipográficas U+2018, U+2019, U+201A e U+201B.
Antes, só o apóstrofo ASCII era dobrado: um caminho com uma delas (a pasta "D:/Ana’s Work" ou um nome de arquivo
escolhido por quem escreve em decisoes/) fechava a cadeia, e o resto virava comando no terminal do titular. Agora as
quatro são dobradas como a ASCII, as aspas duplas tipográficas são recusadas como a ASCII, o nome do arquivo de
decisão precisa ser um identificador de decisão e a sondagem do dono da âncora não monta o caminho dentro do comando.
No Windows, o próprio analisador do PowerShell confere que cada comando gerado é uma instrução só.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  (põe o kit no sys.path)

from fundacao.core import decisoes
from fundacao.core.contracts import ValidationError

BARRA = chr(92)
ASPAS_SIMPLES = ("'",) + tuple(chr(c) for c in (0x2018, 0x2019, 0x201A, 0x201B))
ASPAS_DUPLAS_TIPOGRAFICAS = tuple(chr(c) for c in (0x201C, 0x201D, 0x201E))


def caminho_com_injecao(aspa: str) -> str:
    return BARRA.join(("E:", "pasta" + aspa + "; Write-Output INJETADO; " + aspa + "x", "projects", "p", "decisoes",
                       "dec-1.json"))


def fora_das_cadeias(comando: str) -> str:
    """O que sobra fora das cadeias entre aspas simples, pela regra do tokenizador do PowerShell: qualquer uma das cinco
    aspas abre e fecha a cadeia, e duas seguidas dentro dela valem uma aspa literal."""
    fora, i = [], 0
    while i < len(comando):
        if comando[i] not in ASPAS_SIMPLES:
            fora.append(comando[i])
            i += 1
            continue
        i += 1
        while i < len(comando):
            if comando[i] in ASPAS_SIMPLES:
                if i + 1 < len(comando) and comando[i + 1] in ASPAS_SIMPLES:
                    i += 2
                    continue
                break
            i += 1
        i += 1
        fora.append(" <cadeia> ")
    return "".join(fora)


class TestAspasNoComandoDoTitular(unittest.TestCase):
    def comando(self, decisao: str) -> dict:
        return decisoes.comando_para_o_titular(decisao, assinante="titular-ensaio", shell="powershell",
                                               ancora=decisoes.ANCORA_WINDOWS)

    def test_cada_aspa_simples_fica_dentro_da_cadeia(self):
        for aspa in ASPAS_SIMPLES:
            c = self.comando(caminho_com_injecao(aspa))
            for campo in ("assinar", "conferir"):
                with self.subTest(aspa=hex(ord(aspa)), campo=campo):
                    sobra = fora_das_cadeias(c[campo])
                    self.assertNotIn("INJETADO", sobra, c[campo])
                    self.assertNotIn(";", sobra, c[campo])

    def test_aspas_duplas_tipograficas_sao_recusadas_como_a_ascii(self):
        for aspa in ASPAS_DUPLAS_TIPOGRAFICAS:
            with self.subTest(aspa=hex(ord(aspa))), self.assertRaises(decisoes.DecisaoInvalida):
                self.comando(BARRA.join(("E:", "a" + aspa + "b", "d.json")))

    def test_assinante_com_quebra_de_linha_no_fim_e_recusado(self):  # revisão de segurança da 1.7.4
        with self.assertRaises(decisoes.DecisaoInvalida):
            decisoes.comando_para_o_titular(caminho_com_injecao("'"), assinante="titular-ensaio" + chr(10),
                                            shell="powershell", ancora=decisoes.ANCORA_WINDOWS)

    def test_nome_do_arquivo_de_decisao_precisa_ser_identificador(self):
        raiz = Path(tempfile.mkdtemp(prefix="e11-f01-"))
        self.addCleanup(shutil.rmtree, raiz, True)
        pasta = raiz / "projects" / "p" / "decisoes"
        pasta.mkdir(parents=True)
        ruim = pasta / ("dec" + chr(0x2019) + "; Write-Output INJETADO; " + chr(0x2019) + ".json")
        ruim.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValidationError):
            decisoes.pasta_da_decisao(raiz, ruim)
        bom = pasta / "dec-aceite-20261021T010000.json"
        bom.write_text("{}", encoding="utf-8")
        self.assertEqual(decisoes.pasta_da_decisao(raiz, bom), ("p", bom.resolve()))

    def test_sondagem_do_dono_nao_monta_o_caminho_no_comando(self):
        alvo = Path(caminho_com_injecao(chr(0x2019)))
        with mock.patch.object(decisoes.subprocess, "run",
                               return_value=subprocess.CompletedProcess([], 0, "BUILTIN" + BARRA + "Administradores" + chr(10), "")) as run:
            decisoes._dono_windows(alvo)
        argumentos = run.call_args.args[0]
        self.assertFalse(any("INJETADO" in str(a) for a in argumentos), argumentos)
        self.assertIn(str(alvo), (run.call_args.kwargs.get("env") or {}).values())


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"), "analisador do PowerShell só no Windows")
class TestAnalisadorDoPowerShell(unittest.TestCase):
    @staticmethod
    def instrucoes(comando: str) -> str:
        """Instruções e erros que o analisador do PowerShell vê no comando (só analisa: nada é executado)."""
        b64 = base64.b64encode(comando.encode("utf-8")).decode("ascii")
        script = ("$c = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + b64 + "')); "
                  "$t = $null; $e = $null; "
                  "$a = [System.Management.Automation.Language.Parser]::ParseInput($c, [ref]$t, [ref]$e); "
                  "Write-Output ([string]$a.EndBlock.Statements.Count + ' ' + [string]$e.Count)")
        codificado = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", codificado],
                           capture_output=True, text=True, errors="replace", timeout=120)
        return r.stdout.strip()

    def test_comando_gerado_e_uma_instrucao_so_com_cada_aspa(self):
        for aspa in ASPAS_SIMPLES:
            c = decisoes.comando_para_o_titular(caminho_com_injecao(aspa), assinante="titular-ensaio",
                                                shell="powershell", ancora=decisoes.ANCORA_WINDOWS)
            for campo in ("assinar", "conferir"):
                with self.subTest(aspa=hex(ord(aspa)), campo=campo):
                    self.assertEqual(self.instrucoes(c[campo]), "1 0", c[campo])


if __name__ == "__main__":
    unittest.main()
