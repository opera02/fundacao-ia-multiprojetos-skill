"""1.7.11 — invólucro do GnuPG da cópia cifrada (desenho DESENHO-COPIA-CIFRADA-1.7.11, lote 1; provas N7 e N10).

Chave de TESTE criada aqui, numa pasta temporária, e apagada no fim (apoio_cifra.py); sem `gpg` 2.4 no caminho fixo, o
módulo inteiro pula com o motivo. O `gpg` de PATH nunca vale; ausente ou antigo recusa com mensagem clara; só chave
pública (a privada recusa); o --homedir da cifra nasce sem chave privada; o claro só passa pelo pipe; a cifra grava arquivo
NOVO e, na falha, não deixa nada; o cabeçalho de cada parte (PKESK + dado cifrado) confere o destinatário sem chamar o gpg.
Conteúdos fictícios.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio_auditoria import criar_ligacao_dir
from apoio_cifra import CANARIO, Chaveiro, chaveiros, exigir_gpg

from fundacao.core import cifra_copia
from fundacao.core.cifra_copia import CifraRecusada, SessaoDeCifra, conferir_cabecalho, ids_do_destinatario

A = B = EXE = None


def setUpModule() -> None:
    global A, B, EXE
    EXE = exigir_gpg()
    A, B = chaveiros("Teste A", "Teste B")  # divididas entre os módulos


def programa_falso(pasta: Path, saida: str) -> str:
    """Um 'gpg' que só imprime `saida` (qualquer argumento)."""
    if os.name == "nt":
        alvo = pasta / "gpg-falso.cmd"
        alvo.write_text(f"@echo off\r\necho {saida}\r\n", encoding="ascii")
    else:
        alvo = pasta / "gpg-falso"
        alvo.write_text(f"#!/bin/sh\necho '{saida}'\n", encoding="ascii")
        alvo.chmod(0o755)
    return str(alvo)


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="cc-"))
        self.addCleanup(self._limpar)

    def _limpar(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cifrar(self, dados: bytes, chave: Chaveiro = None, nome: str = "x.gpg") -> tuple[Path, object]:
        saida = self.tmp / nome
        with SessaoDeCifra((chave or A).publica, EXE) as sessao:
            with sessao.cifrador(saida) as c:
                for i in range(0, len(dados), 7000):
                    c.write(dados[i:i + 7000])
        return saida, c


class TestPrograma(Base):
    def test_caminho_fixo_e_nao_o_do_path(self):
        """N10: um `gpg` posto antes no PATH é ignorado."""
        falso = programa_falso(self.tmp, "gpg (GnuPG) 9.9.9")
        with mock.patch.dict(os.environ, {"PATH": str(Path(falso).parent) + os.pathsep + os.environ.get("PATH", "")}):
            self.assertEqual(cifra_copia.gpg_do_sistema(), cifra_copia.GPG_WINDOWS if os.name == "nt" else cifra_copia.GPG_LINUX)
            self.assertNotEqual(cifra_copia.localizar_gpg()["exe"], falso)

    def test_ausente_recusa_com_mensagem_clara(self):
        with self.assertRaises(CifraRecusada) as e:
            cifra_copia.localizar_gpg(str(self.tmp / "nao-existe" / "gpg.exe"))
        self.assertIn("nenhuma cópia cifrada foi feita", str(e.exception))
        with mock.patch.object(cifra_copia, "gpg_do_sistema", return_value=None):
            with self.assertRaises(CifraRecusada):
                cifra_copia.localizar_gpg()

    def test_versao_antiga_recusa(self):
        with self.assertRaises(CifraRecusada) as e:
            cifra_copia.localizar_gpg(programa_falso(self.tmp, "gpg (GnuPG) 2.2.19"))
        self.assertIn("anterior ao 2.4", str(e.exception))

    def test_saida_que_nao_e_gnupg_recusa(self):
        with self.assertRaises(CifraRecusada):
            cifra_copia.localizar_gpg(programa_falso(self.tmp, "ola mundo"))

    def test_versao_real_e_aceita(self):
        info = cifra_copia.localizar_gpg()
        self.assertGreaterEqual(tuple(int(n) for n in info["versao"].split("."))[:2], (2, 4))

    @unittest.skipUnless(os.name == "nt", "o gpg de msys é do Windows")
    def test_caminho_vai_na_forma_de_msys(self):
        # Raiz de exemplo: o saneamento da cópia pública troca o nome real da raiz por um marcador e o teste deixava de
        # achar o disco (CI pública da 1.7.11).
        self.assertEqual(cifra_copia.para_gpg(r"E:\Raiz de Exemplo\x\y.gpg"), "/e/Raiz de Exemplo/x/y.gpg")
        with self.assertRaises(CifraRecusada):
            cifra_copia.para_gpg(r"\\servidor\pasta\x")

    def test_ambiente_sem_variaveis_do_gpg(self):
        with mock.patch.dict(os.environ, {"GNUPGHOME": "/nada", "GPG_AGENT_INFO": "x", "gpg_tty": "y", "OUTRA": "z"}):
            amb = cifra_copia._ambiente()
        self.assertEqual({k.upper() for k in amb} & {"GNUPGHOME", "GPG_AGENT_INFO", "GPG_TTY"}, set())
        self.assertEqual(amb.get("OUTRA"), "z")


class TestChave(Base):
    def test_destinatario_lido_da_chave_publica(self):
        with SessaoDeCifra(A.publica, EXE) as s:
            self.assertEqual(s.destinatario["principal"], A.impressao)
            self.assertEqual(len(s.destinatario["subchaves_de_cifra"]), 1)
            self.assertNotEqual(s.destinatario["subchaves_de_cifra"][0], A.impressao)
            self.assertEqual(s.gpg["exe"], EXE)

    def test_chave_privada_recusa(self):
        with self.assertRaises(CifraRecusada) as e:
            SessaoDeCifra(A.privada, EXE)
        self.assertIn("PRIVADO", str(e.exception))

    def test_arquivo_que_nao_e_chave_recusa(self):
        lixo = self.tmp / "lixo.asc"
        lixo.write_text("isto não é uma chave\n", encoding="utf-8")
        with self.assertRaises(CifraRecusada):
            SessaoDeCifra(lixo, EXE)
        with self.assertRaises(CifraRecusada):
            SessaoDeCifra(self.tmp / "ausente.asc", EXE)

    def test_arquivo_com_duas_chaves_recusa(self):
        duas = self.tmp / "duas.asc"
        duas.write_bytes(A.publica.read_bytes() + b"\n" + B.publica.read_bytes())
        with self.assertRaises(CifraRecusada) as e:
            SessaoDeCifra(duas, EXE)
        self.assertIn("exatamente uma", str(e.exception))

    def test_chave_grande_demais_recusa(self):
        grande = self.tmp / "grande.asc"
        grande.write_bytes(b"x" * (cifra_copia.TETO_CHAVE + 1))
        with self.assertRaises(CifraRecusada):
            SessaoDeCifra(grande, EXE)

    def test_ligacao_no_caminho_da_chave_recusa(self):
        real = self.tmp / "real"
        real.mkdir()
        (real / "chave.asc").write_bytes(A.publica.read_bytes())
        criar_ligacao_dir(self.tmp / "ligada", real)
        with self.assertRaises(CifraRecusada) as e:
            SessaoDeCifra(self.tmp / "ligada" / "chave.asc", EXE)
        self.assertIn("ligação", str(e.exception))

    def test_a_pasta_temporaria_da_sessao_sai(self):
        with SessaoDeCifra(A.publica, EXE) as s:
            casa = s.casa
            self.assertTrue(casa.is_dir())
        self.assertFalse(casa.exists())
        self.assertTrue(s.sobra["limpa"])


class TestCifra(Base):
    def test_cifra_e_decifra_com_a_chave_de_teste(self):
        claro = os.urandom(300_000) + CANARIO.encode()
        saida, c = self.cifrar(claro)
        self.assertEqual(c.tamanho, saida.stat().st_size)
        self.assertEqual(c.sha256, hashlib.sha256(saida.read_bytes()).hexdigest())
        self.assertNotIn(CANARIO.encode(), saida.read_bytes())
        codigo, volta = A.decifrar(saida)
        self.assertEqual((codigo, volta), (0, claro))

    def test_so_a_chave_do_destinatario_abre(self):
        saida, _ = self.cifrar(b"segredo ficticio " * 100, A)
        codigo, volta = B.decifrar(saida)
        self.assertNotEqual(codigo, 0)
        self.assertEqual(volta, b"")

    def test_o_homedir_da_cifra_nao_tem_chave_privada(self):
        vistos = []
        real = subprocess.Popen

        def espiao(args, *a, **k):
            if "--encrypt" in args:
                casa = args[args.index("--homedir") + 1]
                casa = Path(casa[1].upper() + ":" + casa[2:]) if os.name == "nt" else Path(casa)
                vistos.append(sorted(os.listdir(casa)))
            return real(args, *a, **k)

        with mock.patch("subprocess.Popen", espiao):
            self.cifrar(b"dados")
        self.assertEqual(len(vistos), 1)
        self.assertEqual(set(vistos[0]) - {"chave.asc", "random_seed", "trustdb.gpg"}, set(), vistos)
        self.assertNotIn("private-keys-v1.d", vistos[0])

    def test_gnupghome_do_ambiente_nao_vale(self):
        with mock.patch.dict(os.environ, {"GNUPGHOME": str(self.tmp / "outro")}):
            saida, _ = self.cifrar(b"dados")
        self.assertFalse((self.tmp / "outro").exists())
        self.assertEqual(A.decifrar(saida), (0, b"dados"))

    def test_nao_sobrescreve_arquivo_existente(self):
        destino = self.tmp / "ja-existe.gpg"
        destino.write_bytes(b"antigo")
        with SessaoDeCifra(A.publica, EXE) as sessao:
            with self.assertRaises(FileExistsError):
                with sessao.cifrador(destino):
                    pass
        self.assertEqual(destino.read_bytes(), b"antigo")

    def test_erro_no_bloco_apaga_a_saida_e_encerra_o_gpg(self):
        saida = self.tmp / "parcial.gpg"
        with SessaoDeCifra(A.publica, EXE) as sessao:
            with self.assertRaises(RuntimeError):
                with sessao.cifrador(saida) as c:
                    c.write(os.urandom(100_000))
                    raise RuntimeError("falha do chamador")
            self.assertIsNotNone(c._p.returncode)
        self.assertFalse(saida.exists())

    def test_gpg_que_falha_nao_deixa_saida(self):
        saida = self.tmp / "falha.gpg"
        with SessaoDeCifra(A.publica, EXE) as sessao:
            sessao.chave.unlink()  # o gpg não lê mais o destinatário: sai com código diferente de 0
            with self.assertRaises(CifraRecusada):
                with sessao.cifrador(saida) as c:
                    c.write(b"dados" * 1000)
        self.assertFalse(saida.exists())

    def test_nenhum_texto_claro_ao_lado(self):
        saida, _ = self.cifrar(CANARIO.encode() * 1000)
        self.assertEqual([p.name for p in self.tmp.iterdir() if p.is_file()], [saida.name])
        self.assertNotIn(CANARIO.encode(), saida.read_bytes())


class TestCabecalho(Base):
    """Só lê: a parte cifrada e os `keyid` das duas chaves são feitos uma vez para a classe."""

    @classmethod
    def setUpClass(cls) -> None:
        pasta = Path(tempfile.mkdtemp(prefix="cc-cab-"))
        cls.addClassCleanup(shutil.rmtree, pasta, ignore_errors=True)
        with SessaoDeCifra(A.publica, EXE) as sessao:
            with sessao.cifrador(pasta / "x.gpg") as c:
                c.write(os.urandom(50_000))
            cls.ids_a = ids_do_destinatario(sessao.destinatario)
        cls.dados = (pasta / "x.gpg").read_bytes()
        with SessaoDeCifra(B.publica, EXE) as sessao:
            cls.ids_b = ids_do_destinatario(sessao.destinatario)

    def test_cabecalho_certo_confere(self):
        self.assertIsNone(conferir_cabecalho(self.dados[:cifra_copia.PREFIXO], len(self.dados), self.ids_a))

    def test_outro_destinatario_recusa(self):
        tipo, _ = conferir_cabecalho(self.dados[:cifra_copia.PREFIXO], len(self.dados), self.ids_b)
        self.assertEqual(tipo, "destinatario")

    def test_prefixo_curto_recusa(self):
        for corte in (0, 1, 2, 10, 90):
            problema = conferir_cabecalho(self.dados[:corte], len(self.dados), self.ids_a)
            self.assertEqual(problema[0] if problema else None, "estrutura", corte)

    def test_pacote_de_dado_literal_ou_de_chave_no_topo_recusa(self):
        sessao = self.dados[:96]  # o PKESK: formato antigo, 2 + 94 bytes
        self.assertEqual(sessao[0], 0x84)
        for tag in (11, 6, 5, 7, 14):
            estranho = bytes([0xC0 | tag, 4]) + b"abcd"
            self.assertEqual(conferir_cabecalho(sessao + estranho, 9999, self.ids_a)[0], "estrutura", tag)
            self.assertEqual(conferir_cabecalho(estranho, 9999, self.ids_a)[0], "estrutura", tag)

    def test_dado_cifrado_de_tamanho_definido_fecha_com_o_arquivo(self):
        sessao = self.dados[:96]
        seipd = bytes([0xD2, 10]) + b"\x01" + b"x" * 9
        self.assertIsNone(conferir_cabecalho(sessao + seipd, len(sessao + seipd), self.ids_a))
        self.assertEqual(conferir_cabecalho(sessao + seipd, len(sessao + seipd) + 1, self.ids_a)[0], "estrutura")

    def test_lixo_recusa(self):
        for lixo in (b"\x00" * 100, b"texto simples sem cabecalho openpgp", os.urandom(8) + b"\x00"):
            self.assertEqual(conferir_cabecalho(lixo, len(lixo), self.ids_a)[0], "estrutura")

    def test_conferir_nao_chama_o_gpg(self):
        with mock.patch("subprocess.Popen", side_effect=AssertionError("chamou o gpg")), \
                mock.patch("subprocess.run", side_effect=AssertionError("chamou o gpg")):
            self.assertIsNone(conferir_cabecalho(self.dados[:cifra_copia.PREFIXO], len(self.dados), self.ids_a))


if __name__ == "__main__":
    unittest.main()
