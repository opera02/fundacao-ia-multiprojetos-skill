"""1.7.11 — `backup criar` cifrado com preparo local, texto das credenciais e restauração da pasta decifrada (desenho
DESENHO-COPIA-CIFRADA-1.7.11, §1.4 e lote 2).

Fundação de laboratório (FoundationTestCase) e chave de TESTE (apoio_cifra.py). Provas: a cópia em claro nasce só no preparo
local e ele sai no fim, também na falha; no destino só há texto cifrado (um canário num arquivo de projeto não aparece em byte
nenhum); recusas antes de gastar a cópia (espaço, preparo local dentro da raiz ou do destino ou já ocupado, chave que não serve);
o manifesto interno diz que a cópia é cifrada; a pasta decifrada se restaura como cópia comum, pela âncora interna (informada
ou do livro). Conteúdos fictícios.
"""

from __future__ import annotations

import itertools
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio_cifra import CANARIO, LOOPBACK, chaveiros, exigir_gpg
from helpers import FoundationTestCase

from fundacao.core import backup, copia_cifrada, git_na_copia
from fundacao.core.backup_cifrado import verificar_cifrada
from fundacao.core.cifra_copia import CifraRecusada
from fundacao.core.contracts import ValidationError
from fundacao.core.decifra_copia import desembrulhar

A = EXE = None
CONTADOR = itertools.count()


def setUpModule() -> None:
    global A, EXE
    EXE = exigir_gpg()
    A, = chaveiros("Teste A")  # divididas entre os módulos


class TestTextoDasCredenciais(unittest.TestCase):
    def test_o_texto_diz_se_a_copia_e_cifrada(self):
        regra = git_na_copia.RegraDaCopia.__new__(git_na_copia.RegraDaCopia)
        regra.segredos = 3
        em_claro, cifrada = regra.texto_credenciais(), regra.texto_credenciais(True)
        self.assertIn("A cópia não é cifrada", em_claro)
        self.assertIn("3 arquivo(s) com cara de segredo", em_claro)
        self.assertIn("em claro", em_claro)
        self.assertIn("CIFRADA", cifrada)
        self.assertNotIn("não é cifrada", cifrada)
        self.assertIn("dentro da cifra", cifrada)


class TestCriarCifrada(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.base = Path(tempfile.mkdtemp(prefix="cc-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.local, self.destino = self.base / "local", self.base / "cifrada"
        self.log = self.root / "state" / "retiradas.jsonl"
        self.write_data("juridico-lab", "fontes/caso.md", f"conteudo do caso {CANARIO}\n")

    def criar(self, **kw) -> dict:
        kw.setdefault("preparo_local", self.local)
        kw.setdefault("tamanho_parte", 1 << 20)
        return copia_cifrada.criar_cifrada(self.root, self.destino, "lab-cifrado", kw.pop("chave", A.publica), exe=EXE, **kw)

    def assertSemSobra(self) -> None:
        self.assertFalse(self.local.exists(), "o preparo local não saiu")
        self.assertEqual([p.name for p in self.base.iterdir() if p.name.startswith(".")], [], "sobra de preparo")

    def test_copia_comum_continua_dizendo_que_nao_e_cifrada(self):
        comum = backup.create_backup(self.root, self.base / "comum", "comum")
        self.assertIn("A cópia não é cifrada", comum["credentials"])

    def test_espaco_insuficiente_recusa_antes_de_copiar(self):
        with mock.patch.object(backup, "create_backup") as copiar:
            with self.assertRaises(ValidationError) as e:
                self.criar(fator_de_espaco=1e12)
        copiar.assert_not_called()
        self.assertIn("espaço livre insuficiente", str(e.exception))
        self.assertSemSobra()
        self.assertFalse(self.destino.exists())

    def test_o_estimado_conta_a_fundacao(self):
        estimado = copia_cifrada.estimar_bytes(self.root)
        self.assertGreater(estimado, 100_000)
        self.assertGreaterEqual(estimado, (self.root / "state" / "state.sqlite").stat().st_size)

    def test_preparo_local_no_lugar_errado(self):
        casos = {"dentro da raiz": self.root / "preparo", "dentro do destino": self.destino / "local",
                 "igual ao destino": self.destino}
        for nome, local in casos.items():
            with self.subTest(nome), mock.patch.object(backup, "create_backup") as copiar:
                with self.assertRaises(ValidationError):
                    self.criar(preparo_local=local)
                copiar.assert_not_called()
        self.local.mkdir()
        (self.local / "sobra.txt").write_text("de uma cópia anterior", encoding="utf-8")
        with self.assertRaises(ValidationError) as e:
            self.criar()
        self.assertIn("já existe", str(e.exception))
        self.assertTrue((self.local / "sobra.txt").exists(), "o que já existia não é apagado")
        self.local.joinpath("sobra.txt").unlink()
        self.local.rmdir()
        self.destino.mkdir()
        (self.destino / "x").write_text("ocupado", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.criar()

    def test_chave_que_nao_serve_recusa_antes_da_copia(self):
        with mock.patch.object(backup, "create_backup") as copiar:
            with self.assertRaises(CifraRecusada):
                self.criar(chave=A.privada)
            with self.assertRaises(CifraRecusada):
                self.criar(chave=self.base / "sem-chave.asc")
        copiar.assert_not_called()
        self.assertSemSobra()
        self.assertFalse(self.destino.exists())

    def test_falha_na_cifra_apaga_o_preparo_local(self):
        with mock.patch.object(copia_cifrada, "cifrar_copia", side_effect=CifraRecusada("falha simulada")):
            with self.assertRaises(CifraRecusada):
                self.criar()
        self.assertSemSobra()
        self.assertFalse(self.destino.exists())

    def test_copia_em_claro_que_nao_confere_nao_e_cifrada(self):
        ruim = {"ok": False, "changed": ["x"], "ancora": {"situacao": "conferida"}}
        with mock.patch.object(backup, "verify_backup", return_value=ruim), \
                mock.patch.object(copia_cifrada, "cifrar_copia") as cifrar:
            with self.assertRaises(ValidationError) as e:
                self.criar()
        cifrar.assert_not_called()
        self.assertIn("nada foi cifrado", str(e.exception))
        self.assertSemSobra()

    def test_arquivo_mudado_no_preparo_local_antes_de_cifrar_recusa(self):
        real = backup.verify_backup

        def mudar_depois(local, **kw):
            res = real(local, **kw)
            alvo = next(p for p in (local / "files").rglob("*") if p.is_file() and p.stat().st_size > 5)
            alvo.write_bytes(bytes(b ^ 1 for b in alvo.read_bytes()))
            return res

        with mock.patch.object(backup, "verify_backup", mudar_depois):
            with self.assertRaises(ValidationError):
                self.criar()
        self.assertSemSobra()
        self.assertFalse(self.destino.exists())


class TestCopiaCifradaFeliz(unittest.TestCase):
    """O caminho feliz é feito UMA vez para a classe (fundação de laboratório e `criar_cifrada`); os testes só leem o
    resultado ou trabalham em pastas próprias dentro dela."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.lab = FoundationTestCase("run")  # só para usar o setUp/tearDown da fundação de laboratório
        cls.lab.setUp()
        cls.addClassCleanup(cls._desmontar)
        cls.root, cls.log = cls.lab.root, cls.lab.root / "state" / "retiradas.jsonl"
        cls.base = Path(tempfile.mkdtemp(prefix="cc-feliz-"))
        cls.addClassCleanup(shutil.rmtree, cls.base, ignore_errors=True)
        cls.local, cls.destino = cls.base / "local", cls.base / "cifrada"
        cls.lab.write_data("juridico-lab", "fontes/caso.md", f"conteudo do caso {CANARIO}\n")
        cls.r = copia_cifrada.criar_cifrada(cls.root, cls.destino, "lab-cifrado", A.publica, exe=EXE, preparo_local=cls.local,
                                            tamanho_parte=1 << 20)

    @classmethod
    def _desmontar(cls) -> None:
        cls.lab.doCleanups()
        cls.lab.tearDown()

    def assertSemSobra(self) -> None:
        self.assertFalse(self.local.exists(), "o preparo local não saiu")
        self.assertEqual([p.name for p in self.base.iterdir() if p.name.startswith(".")], [], "sobra de preparo")

    def test_fluxo_completo(self):
        r = self.r
        self.assertTrue(r["cifrada"])
        self.assertSemSobra()
        self.assertNotIn("sobra_do_preparo", r)
        self.assertNotEqual(r["sha256_manifesto"], r["sha256_manifesto_interno"])
        self.assertTrue(r["verificacao"]["ok"])
        self.assertEqual(r["destinatario"]["principal"], A.impressao)
        self.assertEqual(r["preparo_local"], str(self.local))
        nomes = sorted(p.name for p in self.destino.iterdir())
        self.assertEqual(nomes[0], "LEIA-ME.txt")
        self.assertTrue(all(n.startswith("parte-") or n in ("LEIA-ME.txt", "manifesto-cifrado.json") for n in nomes), nomes)
        todos = b"".join(p.read_bytes() for p in self.destino.iterdir())
        self.assertNotIn(CANARIO.encode(), todos, "texto em claro no disco das cópias")
        self.assertNotIn(b"manifest.json", todos)
        self.assertTrue(verificar_cifrada(self.destino, sha256_manifesto=r["sha256_manifesto"])["ok"])
        self.assertEqual(r["label"], "lab-cifrado")
        self.assertIn("files", r)  # a lista de arquivos da cópia em claro, para --detalhar

    def test_livro_tem_a_ancora_do_conteudo_e_a_da_cifrada(self):
        r = self.r
        linhas = [json.loads(x) for x in (self.root / "state" / "copias.jsonl").read_text(encoding="utf-8").splitlines()]
        claro = [x for x in linhas if not x.get("cifrada")]
        cifrada = [x for x in linhas if x.get("cifrada")]
        self.assertEqual([x["sha256_manifesto"] for x in claro], [r["sha256_manifesto_interno"]])
        self.assertEqual([x["sha256_manifesto"] for x in cifrada], [r["sha256_manifesto"]])
        self.assertEqual(cifrada[0]["sha256_manifesto_interno"], r["sha256_manifesto_interno"])
        self.assertEqual(cifrada[0]["destinatario"]["principal"], A.impressao)
        self.assertEqual(cifrada[0]["destino"], str(self.destino))

    def test_o_manifesto_interno_diz_que_a_copia_e_cifrada(self):
        r = self.r
        dec = self.base / f"dec-{next(CONTADOR)}"
        desembrulhar(self.destino, dec, A.casa, sha256_manifesto=r["sha256_manifesto"], exe=EXE, extras_gpg=LOOPBACK)
        interno = json.loads((dec / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("CIFRADA", interno["credentials"])
        self.assertNotIn("não é cifrada", interno["credentials"])
        comum = backup.create_backup(self.root, self.base / "comum", "comum")
        self.assertIn("A cópia não é cifrada", comum["credentials"])

    def test_a_pasta_decifrada_se_restaura_pela_ancora_interna(self):
        r = self.r
        dec = self.base / f"dec-{next(CONTADOR)}"
        d = desembrulhar(self.destino, dec, A.casa, sha256_manifesto=r["sha256_manifesto"], exe=EXE, extras_gpg=LOOPBACK)
        self.assertEqual(d["sha256_manifesto_interno"], r["sha256_manifesto_interno"])
        rest = self.base / f"restaurada-{next(CONTADOR)}"
        informada = backup.restore(dec, rest, self.log, sha256_manifesto=r["sha256_manifesto_interno"])
        self.assertTrue(informada["released"], informada)
        self.assertEqual(informada["ancora"]["situacao"], "conferida")
        self.assertEqual(
            sum(1 for p in rest.rglob("caso.md") if CANARIO in p.read_text(encoding="utf-8")), 1)
        do_livro = backup.restore(dec, rest.with_name(rest.name + "-2"), self.log)  # sem informar: o livro tem a âncora do conteúdo
        self.assertTrue(do_livro["released"], do_livro)
        self.assertEqual(do_livro["ancora"]["fonte"], "livro de cópias")
        recusa = backup.restore(dec, rest.with_name(rest.name + "-3"), self.log, sha256_manifesto=r["sha256_manifesto"])
        self.assertFalse(recusa["released"], "a âncora do manifesto EXTERNO não é a do conteúdo")


if __name__ == "__main__":
    unittest.main()
