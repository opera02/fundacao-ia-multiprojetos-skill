"""Âncora com `fundacao-copia` (folha da integração, I22; já faltava na 1.7.9).

O livro de cópias assinado (`core/livro_assinado.py`) confere a assinatura do titular com `ssh-keygen -Y verify -n
fundacao-copia` contra a mesma âncora das decisões e das fichas; a linha que o `preparar-maquina.ps1` gravava só
permitia `fundacao-decisao` e `fundacao-abertura`, e o OpenSSH recusa o namespace fora da lista: a adoção do livro não
conferia. Aqui: a sonda real do `ssh-keygen` (o OpenSSH do Windows e o do Git para Windows, ou o `/usr/bin` do Linux)
sobre a linha que o script grava, numa pasta temporária com chave fictícia sem senha (só no teste); e o kit
(`core/decisoes.py`, `core/aberturas.py`, `core/livro_assinado.py`, `core/comando_titular.py`) aceitando a linha com os
três namespaces. A âncora padrão desta máquina é trocada pela de ensaio (nada de `C:\\ProgramData` é lido). A forma da
linha é a do `Get-LinhaAncora` (o `test_host_windows` a confere com o PowerShell); o `$NAMESPACES` vem do próprio script.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import SKILL

PS1 = SKILL / "assets" / "host" / "windows" / "preparar-maquina.ps1"
FERRAMENTA = SKILL / "assets" / "host" / "fundacao_titular.py"
TRES = ["fundacao-decisao", "fundacao-abertura", "fundacao-copia"]
DA_1710_DE_ANTES = "fundacao-decisao,fundacao-abertura"
AMBIENTE = {k: v for k, v in os.environ.items() if k != "SSH_AUTH_SOCK"}  # nenhum ssh-agent entra na sonda


def namespaces_do_script() -> str:
    m = re.search(r"^\$NAMESPACES = '([^']*)'", PS1.read_text(encoding="utf-8-sig"), re.M)
    if not m:
        raise AssertionError("$NAMESPACES ausente no preparar-maquina.ps1")
    return m.group(1)


def linha_da_ancora(publica: str, namespaces: str) -> bytes:
    """A linha como o preparar-maquina.ps1 a grava (Get-LinhaAncora; o arquivo em UTF-8 sem BOM, com CRLF)."""
    return (f'titular namespaces="{namespaces}" ' + " ".join(publica.split()) + "\r\n").encode("utf-8")


def keygens() -> list[str]:
    """O ssh-keygen do sistema (OpenSSH do Windows ou /usr/bin) e, no Windows, o do Git para Windows, se houver."""
    if os.name == "nt":
        candidatos = [Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "OpenSSH" / "ssh-keygen.exe",
                      Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "usr" / "bin" /
                      "ssh-keygen.exe"]
    else:
        candidatos = [Path("/usr/bin/ssh-keygen")]
    return [str(c) for c in candidatos if c.is_file()]


class _Sonda(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="ancora-copia-1710-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.n = 0  # cada assinatura num arquivo novo: o ssh-keygen pergunta antes de sobrescrever um .sig

    def chave(self, exe: str) -> tuple[Path, str]:
        """Chave fictícia sem senha (só no teste: o preparo recusa chave sem senha), numa pasta só dela."""
        pasta = self.base / ("chave-" + hashlib.sha256(exe.encode("utf-8")).hexdigest()[:8])
        pasta.mkdir()
        destino = pasta / "titular-ensaio"
        subprocess.run([exe, "-q", "-t", "ed25519", "-N", "", "-C", "ensaio-ficticio", "-f", str(destino)], check=True,
                       capture_output=True, timeout=60, env=AMBIENTE)
        return destino, Path(str(destino) + ".pub").read_text(encoding="ascii").strip()

    def assinar(self, exe: str, chave: Path, namespace: str, dados: bytes = b'{"ensaio": "dados ficticios"}\n') -> Path:
        self.n += 1
        alvo = chave.parent / f"documento-{self.n}-{namespace}.json"
        alvo.write_bytes(dados)
        r = subprocess.run([exe, "-Y", "sign", "-f", str(chave), "-n", namespace, str(alvo)], capture_output=True,
                           timeout=60, env=AMBIENTE)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        return alvo

    def verificar(self, exe: str, ancora: Path, alvo: Path, namespace: str) -> tuple[int, str]:
        r = subprocess.run([exe, "-Y", "verify", "-f", str(ancora), "-I", "titular", "-n", namespace, "-s",
                            str(alvo) + ".sig"], input=alvo.read_bytes(), capture_output=True, timeout=60, env=AMBIENTE)
        return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace")


@unittest.skipUnless(keygens(), "ssh-keygen indisponível neste ambiente")
class SondaDoSshKeygen(_Sonda):
    def test_namespaces_do_script_sao_os_tres(self):
        self.assertEqual(namespaces_do_script().split(","), TRES)

    def test_linha_nova_aceita_fundacao_copia_e_recusa_outro_namespace(self):
        """Com a linha que o script grava, -Y verify passa nos três namespaces e recusa fundacao-outra; contraprova: a
        linha da 1.7.10 de antes (sem fundacao-copia) recusa a assinatura do livro de cópias."""
        for exe in keygens():
            with self.subTest(ssh_keygen=exe):
                chave, publica = self.chave(exe)
                nova, antiga = chave.parent / "allowed_signers", chave.parent / "allowed_signers-1710-de-antes"
                nova.write_bytes(linha_da_ancora(publica, namespaces_do_script()))
                antiga.write_bytes(linha_da_ancora(publica, DA_1710_DE_ANTES))
                assinados = {namespace: self.assinar(exe, chave, namespace) for namespace in TRES}
                for namespace, alvo in assinados.items():
                    codigo, saida = self.verificar(exe, nova, alvo, namespace)
                    self.assertEqual(codigo, 0, saida)
                    self.assertIn(f'Good "{namespace}" signature for titular', saida)
                codigo, saida = self.verificar(exe, nova, self.assinar(exe, chave, "fundacao-outra"), "fundacao-outra")
                self.assertNotEqual(codigo, 0, saida)
                codigo, saida = self.verificar(exe, antiga, assinados["fundacao-copia"], "fundacao-copia")
                self.assertNotEqual(codigo, 0, saida)


def kit():
    """Os módulos do kit desta skill, como a ferramenta do titular os carrega (fundacao_titular.kit)."""
    spec = importlib.util.spec_from_file_location("_fundacao_titular_ancora_copia", FERRAMENTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    k = modulo.kit()
    from fundacao.core import comando_titular, livro_assinado  # o mesmo pacote que kit() pôs no sys.path
    k.livro, k.comando = livro_assinado, comando_titular
    return k


@unittest.skipUnless(keygens(), "ssh-keygen indisponível neste ambiente")
class KitAceitaALinhaComOsTres(_Sonda):
    def setUp(self):
        super().setUp()
        self.k = kit()
        self.exe = self.k.decisoes.ssh_keygen_do_sistema()
        if not self.exe:
            self.skipTest("sem o ssh-keygen do sistema (o kit só aceita o dele)")
        self.chave_arq, self.publica = self.chave(self.exe)
        self.ancora = self.base / "ancora" / "allowed_signers"
        self.ancora.parent.mkdir()
        self.escrever(namespaces_do_script())
        padrao = mock.patch.object(self.k.decisoes, "ANCORAS_PADRAO", (str(self.ancora),))
        padrao.start()
        self.addCleanup(padrao.stop)

    def escrever(self, namespaces: str) -> None:
        self.ancora.write_bytes(linha_da_ancora(self.publica, namespaces))

    def test_decisoes_e_aberturas_leem_e_conferem_os_tres(self):
        linhas = self.k.decisoes.ler_ancora(self.ancora)
        self.assertEqual([li["namespaces"] for li in linhas], [TRES])
        for namespace in TRES:
            self.assertTrue(self.k.aberturas.namespace_permitido(linhas[0]["namespaces"], namespace), namespace)
            alvo = self.assinar(self.exe, self.chave_arq, namespace)
            r = self.k.decisoes.verificar_assinatura(alvo, self.ancora, "titular", namespace=namespace)
            self.assertTrue(r["ok"], r)
        self.assertFalse(self.k.aberturas.namespace_permitido(linhas[0]["namespaces"], "fundacao-outra"))
        ficha = self.assinar(self.exe, self.chave_arq, "fundacao-abertura")
        r = self.k.aberturas.conferir_assinatura(ficha.read_bytes(), Path(str(ficha) + ".sig").read_bytes(), self.ancora)
        self.assertEqual((r["ok"], r.get("assinante")), (True, "titular"), r)

    def test_livro_assinado_confere_em_fundacao_copia_e_a_linha_de_antes_recusa(self):
        """O _verificar do livro (a âncora padrão trocada pela de ensaio e dada por protegida: a sondagem das ACL é de
        outros testes) aceita a assinatura em fundacao-copia com a linha nova; com a da 1.7.10 de antes, recusa."""
        livro = self.k.livro
        doc = {"schema_version": livro.SCHEMA, "assinante": "titular", "registrado_em": "2026-11-01T00:00:00Z",
               "entrada": {"sha256_manifesto": "ab" * 32}}
        alvo = self.assinar(self.exe, self.chave_arq, "fundacao-copia", livro._documento(doc))
        assinatura = Path(str(alvo) + ".sig").read_bytes()
        with mock.patch.object(self.k.decisoes, "conferir_ancora", return_value={"protegida": True}):
            self.assertTrue(livro._verificar(doc, assinatura)["ok"])
            self.escrever(DA_1710_DE_ANTES)
            with self.assertRaises(self.k.contracts.ValidationError):
                livro._verificar(doc, assinatura)

    def test_comando_do_titular_confere_com_a_linha_nova(self):
        """O comando pronto do kit (comando_titular, namespace fundacao-copia), rodado como o titular o rodaria."""
        alvo = self.assinar(self.exe, self.chave_arq, "fundacao-copia")
        shell = "powershell" if os.name == "nt" else "bash"
        cmd = self.k.comando.comando_para_o_titular(alvo, assinante="titular", ancora=self.ancora, shell=shell,
                                                    namespace="fundacao-copia")
        self.assertIn("-n fundacao-copia", cmd["conferir"])
        if os.name == "nt":  # como o test_decisoes_comando do kit: -EncodedCommand, sem nenhuma requotação do Python
            texto = cmd["conferir"] + "; exit $LASTEXITCODE"
            argv = ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
                    base64.b64encode(texto.encode("utf-16-le")).decode("ascii")]
        else:
            argv = ["bash", "-c", cmd["conferir"]]
        r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
                           env=AMBIENTE)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(cmd["esperado_ao_conferir"], r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
