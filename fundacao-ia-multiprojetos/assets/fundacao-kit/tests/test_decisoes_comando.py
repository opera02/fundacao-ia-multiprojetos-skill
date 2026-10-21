"""Comando que o titular roda para assinar e conferir uma decisão, no formato do shell em que ele vai rodar.

Regressão da implantação real (RETOMADA da fundação de referência, achado b): a ferramenta da fundação, rodando no
WSL, imprimia o comando do PowerShell com o caminho `/mnt/e/...`. No PowerShell os caminhos são do Windows; no bash
do WSL, `/mnt/<letra>/...`. No Windows o comando gerado é executado de verdade (chave e âncora de ensaio).
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
from apoio_decisoes import Chaves

from fundacao.core import comando_titular, decisoes

BARRA = chr(92)
DEC_WSL = "/mnt/f/Pasta Ficticia/projects/p/decisoes/dec-aceite-1.json"
DEC_WIN = r"F:\Pasta Ficticia\projects\p\decisoes\dec-aceite-1.json"


class TestComandoDoTitular(unittest.TestCase):
    def test_powershell_recebe_caminho_do_windows_quando_a_fundacao_esta_no_wsl(self):
        c = decisoes.comando_para_o_titular(DEC_WSL, assinante="titular-ensaio", shell="powershell",
                                            ancora="/mnt/c/ProgramData/FundacaoIA/confianca/allowed_signers")
        self.assertEqual(c["shell"], "powershell")
        self.assertIn("'" + DEC_WIN + "'", c["assinar"])
        self.assertIn('"' + decisoes.ANCORA_WINDOWS + '"', c["conferir"])
        self.assertIn('-s "' + DEC_WIN + '.sig" < "' + DEC_WIN + '"', c["conferir"])
        self.assertTrue(c["conferir"].startswith("cmd /c '"), c["conferir"])  # o PowerShell não tem `<`
        for campo in ("assinar", "conferir"):
            self.assertNotIn("/mnt/", c[campo])
        self.assertIn("-I titular-ensaio -n fundacao-decisao", c["conferir"])
        self.assertIn("PowerShell", c["onde_abrir"])

    def test_bash_recebe_caminho_do_wsl_quando_a_fundacao_esta_no_windows(self):
        c = decisoes.comando_para_o_titular(DEC_WIN, assinante="titular-ensaio", shell="bash", ancora=decisoes.ANCORA_WINDOWS)
        self.assertEqual(c["shell"], "bash")
        self.assertIn("'" + DEC_WSL + "'", c["assinar"])
        self.assertIn("'/mnt/c/ProgramData/FundacaoIA/confianca/allowed_signers'", c["conferir"])
        self.assertIn("-s '" + DEC_WSL + ".sig' < '" + DEC_WSL + "'", c["conferir"])
        for campo in ("assinar", "conferir"):
            self.assertNotIn(BARRA, c[campo])
        self.assertIn('"$HOME/.ssh/fundacao_titular"', c["assinar"])

    def test_shell_padrao_e_o_powershell_no_windows_e_no_wsl(self):
        # A chave do titular e a âncora ficam no Windows: também numa sessão do WSL ele assina no PowerShell.
        # Desde a 1.7.4 o comando do titular mora em core/comando_titular.py (decisoes.py reexporta os nomes).
        with mock.patch.object(comando_titular, "em_wsl", return_value=True):
            self.assertEqual(decisoes.shell_padrao(), "powershell")
        with mock.patch.object(comando_titular, "em_wsl", return_value=False), \
                mock.patch.object(comando_titular, "no_windows", return_value=False):
            self.assertEqual(decisoes.shell_padrao(), "bash")
        with mock.patch.object(comando_titular, "no_windows", return_value=True):
            self.assertEqual(decisoes.shell_padrao(), "powershell")

    def test_caminho_do_wsl_fora_de_mnt_vira_caminho_de_rede_do_wsl(self):
        with mock.patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}):
            self.assertEqual(decisoes.caminho_windows("/home/titular/f/d.json"),
                             BARRA * 2 + r"wsl.localhost\Ubuntu\home\titular\f\d.json")
        with mock.patch.dict(os.environ, {"WSL_DISTRO_NAME": ""}):
            with self.assertRaises(decisoes.DecisaoInvalida):
                decisoes.caminho_windows("/home/titular/f/d.json")
        self.assertEqual(decisoes.caminho_wsl(r"C:\x\y.json"), "/mnt/c/x/y.json")
        self.assertEqual(decisoes.caminho_windows(r"C:\x\y.json"), r"C:\x\y.json")

    def test_caractere_que_quebraria_o_comando_e_recusado(self):
        for ruim, shell in ((r"E:\a%b\d.json", "powershell"), (r'E:\a"b\d.json', "powershell"),
                            ("E:/a\nb/d.json", "bash"), ("E:/a\nb/d.json", "powershell")):
            with self.subTest(ruim=ruim, shell=shell), self.assertRaises(decisoes.DecisaoInvalida):
                decisoes.comando_para_o_titular(ruim, assinante="titular-ensaio", shell=shell, ancora=decisoes.ANCORA_WINDOWS)

    def test_apostrofo_no_caminho_fica_literal_nos_dois_shells(self):
        win = r"E:\d'Ávila\projects\p\decisoes\d.json"
        ps = decisoes.comando_para_o_titular(win, assinante="titular-ensaio", shell="powershell", ancora=decisoes.ANCORA_WINDOWS)
        self.assertIn(r"'E:\d''Ávila\projects\p\decisoes\d.json'", ps["assinar"])
        sh = decisoes.comando_para_o_titular(win, assinante="titular-ensaio", shell="bash", ancora=decisoes.ANCORA_WINDOWS)
        self.assertIn("'/mnt/e/d'" + BARRA + "''Ávila/projects/p/decisoes/d.json'", sh["assinar"])


class _EnsaioReal(unittest.TestCase):
    """Decisão de ensaio numa pasta com espaço, apóstrofo e acento; chave e âncora de ensaio."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="decisoes-cmd-"))
        self.chaves = Chaves(self.tmp)
        self.pasta = self.tmp / "pasta d'ensaio com espaço" / "projects" / "p"
        (self.pasta / "outputs").mkdir(parents=True)
        (self.pasta / "decisoes").mkdir()
        entrega = self.pasta / "outputs" / "e.md"
        entrega.write_text("Entrega de ensaio.\n", encoding="utf-8")
        d = decisoes.montar_decisao(projeto="p", tarefa="t", entrega_rel="outputs/e.md",
                                    entrega_sha256=decisoes.sha256_arquivo(entrega), tipo="aceite", motivo="Aceito.",
                                    assinante="titular-ensaio", decisao_id="dec-1", agora="2026-10-21T01:00:00-0300")
        self.arq = self.pasta / "decisoes" / "dec-1.json"
        self.arq.write_bytes(decisoes.canonico(d))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ensaiar(self, shell: str, rodar) -> None:
        c = decisoes.comando_para_o_titular(self.arq, assinante="titular-ensaio", shell=shell,
                                            ancora=self.chaves.ancora, chave=self.chaves.chave())
        r = rodar(c["assinar"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(decisoes.verificar_decisao(self.arq, self.pasta, self.chaves.ancora)["valida"])
        r = rodar(c["conferir"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('Good "fundacao-decisao" signature for titular-ensaio', r.stdout + r.stderr)
        self.arq.write_bytes(self.arq.read_bytes().replace(b"Aceito.", b"Aceito!"))  # a mesma conferência recusa
        self.assertNotEqual(rodar(c["conferir"]).returncode, 0)


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"), "execução real só no Windows (PowerShell)")
class TestComandoNoPowerShell(_EnsaioReal):
    @staticmethod
    def powershell(comando: str) -> subprocess.CompletedProcess:
        # Como se o titular colasse o comando: -EncodedCommand evita qualquer requote do Python. `exit $LASTEXITCODE`
        # só no ensaio: devolve o código do ssh-keygen (o PowerShell 5.1 trata o stderr capturado como erro).
        texto = comando + "; exit $LASTEXITCODE"
        codificado = base64.b64encode(texto.encode("utf-16-le")).decode("ascii")
        return subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", codificado],
                              capture_output=True, text=True, errors="replace", timeout=120)

    def test_comando_gerado_assina_e_confere_no_powershell(self):
        self.ensaiar("powershell", self.powershell)


@unittest.skipIf(os.name == "nt" or not shutil.which("bash"), "execução real do bash só no Linux/WSL")
class TestComandoNoBash(_EnsaioReal):
    @staticmethod
    def bash(comando: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", "-c", comando], capture_output=True, text=True, errors="replace", timeout=120)

    def test_comando_gerado_assina_e_confere_no_bash(self):
        self.ensaiar("bash", self.bash)


if __name__ == "__main__":
    unittest.main()
