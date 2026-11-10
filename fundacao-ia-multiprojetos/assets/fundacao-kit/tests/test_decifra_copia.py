"""1.7.11 — decifra da cópia cifrada para a pasta de cópia comum (desenho DESENHO-COPIA-CIFRADA-1.7.11, lote 2; provas N1, N5,
N6 e N11 do desenho).

Chave de TESTE (apoio_cifra.py); a senha vai por `--pinentry-mode loopback` só aqui (o titular a digita na janela do gpg).
Provas: cópia alterada recusa ANTES de chamar o gpg (as chamadas são contadas); a parte só é aceita com rc 0 do gpg e com o hash
da entrada igual ao do manifesto, e a parte inteira é descartada na falha; senha errada, sem senha e chave de outro par não
deixam nada; o extrator seguro recusa caminho absoluto, `..`, `\\`, `:`, ligação, dispositivo, membro repetido, membro fora de
files/ e state/ e arquivo fora do manifesto, sem escrever fora do preparo; o destino só aparece depois de tudo conferir. Conteúdos
fictícios.
"""

from __future__ import annotations

import io
import json
import shutil
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio_cifra import LOOPBACK, arquivos_de_teste, chaveiros, conteudo_da_pasta, copia_sintetica, exigir_gpg, sha

from fundacao.core import decifra_copia
from fundacao.core.backup_cifrado import MANIFESTO, cifrar_copia
from fundacao.core.canon import sha256_bytes
from fundacao.core.cifra_copia import CifraRecusada, SessaoDeCifra
from fundacao.core.contracts import ValidationError
from fundacao.core.decifra_copia import desembrulhar

import itertools

A = B = EXE = SESSAO = None
CONTADOR = itertools.count()
PARTE = 64 * 1024


def setUpModule() -> None:
    global A, B, EXE
    EXE = exigir_gpg()
    A, B = chaveiros("Teste A", "Teste B")  # divididas entre os módulos
    pasta = Path(tempfile.mkdtemp(prefix="dc-molde-"))
    unittest.addModuleCleanup(shutil.rmtree, pasta, ignore_errors=True)
    copia_sintetica(pasta / "claro", arquivos_de_teste())
    Base.molde = (pasta, cifrar_copia(pasta / "claro", pasta / "cifrada", A.publica, tamanho_parte=PARTE, exe=EXE))
    global SESSAO
    SESSAO = SessaoDeCifra(A.publica, EXE)  # a mesma chave pública vale para todas as partes forjadas
    unittest.addModuleCleanup(SESSAO.__exit__)


class _SemGpg:
    """Contexto em que qualquer chamada ao gpg (Popen ou run) falha o teste."""

    def __enter__(self):
        self.parcelas = [mock.patch("subprocess.Popen", side_effect=AssertionError("chamou o gpg")),
                         mock.patch("subprocess.run", side_effect=AssertionError("chamou o gpg"))]
        for p in self.parcelas:
            p.start()

    def __exit__(self, *_):
        for p in self.parcelas:
            p.stop()


def tar_de(claro: Path, extras=(), sem=()) -> bytes:
    """Um tar com a cópia em `claro` (como o do kit: manifest.json, state/, files/) mais os `extras` forjados, que são
    (nome, tipo, dados, destino da ligação); `sem`: nomes que ficam de fora."""
    saida = io.BytesIO()
    with tarfile.open(fileobj=saida, mode="w:", format=tarfile.PAX_FORMAT) as tar:
        for caminho in sorted(p for p in claro.rglob("*") if p.is_file()):
            nome = caminho.relative_to(claro).as_posix()
            if nome not in sem:
                info = tarfile.TarInfo(nome)
                info.size = caminho.stat().st_size
                tar.addfile(info, io.BytesIO(caminho.read_bytes()))
        for nome, tipo, dados, alvo in extras:
            info = tarfile.TarInfo(nome)
            info.type, info.size, info.linkname = tipo, len(dados), alvo
            tar.addfile(info, io.BytesIO(dados))
    return saida.getvalue()


def cifrada_forjada(pasta: Path, claro: Path, tar_bytes: bytes, chave=None) -> str:
    """Uma cópia cifrada de uma parte só (a final) com o `tar_bytes` dado, para a chave de teste, com o manifesto externo
    consistente (hashes certos): o forjador que passou pela âncora. Devolve o SHA-256 do manifesto externo."""
    pasta.mkdir()
    sessao = SESSAO if chave in (None, A) else SessaoDeCifra(chave.publica, EXE)
    with sessao.cifrador(pasta / "parte-final.gpg") as cifrador:
        cifrador.write(tar_bytes)
    parte = pasta / "parte-final.gpg"
    interno = sha((claro / "manifest.json").read_bytes())
    externo = {"schema_version": "fundacao.backup_cifrado/1", "label": "forjada", "created_at": "2026-11-08T12:00:00.000000Z",
               "kit_version": "x", "gpg_versao": "2.4.9", "formato": "tar-pax+openpgp-seipd",
               "destinatario": {"principal": A.impressao, "subchaves_de_cifra": [A.subchave]},
               "sha256_manifesto_interno": interno, "arquivos": 0, "bytes": 0, "tamanho_parte": PARTE,
               "partes": [{"nome": parte.name, "tamanho": parte.stat().st_size, "sha256": sha(parte.read_bytes()),
                           "membros": 1}]}
    bruto = json.dumps(externo, indent=2).encode("utf-8")
    (pasta / MANIFESTO).write_bytes(bruto)
    return sha256_bytes(bruto)


class Base(unittest.TestCase):
    """A cópia em claro e a cifrada são feitas UMA vez para o módulo (molde); cada teste trabalha numa cópia de arquivos."""

    molde = None  # (pasta, resultado do cifrar_copia), feito no setUpModule

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="dc-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.claro, self.cifrada, self.volta = self.tmp / "claro", self.tmp / "cifrada", self.tmp / "volta"
        shutil.copytree(self.molde[0] / "claro", self.claro)
        shutil.copytree(self.molde[0] / "cifrada", self.cifrada)
        self.r = self.molde[1]
        self.ancora = self.r["sha256_manifesto"]

    def desembrulhar(self, origem=None, casa=None, **kw) -> dict:
        kw.setdefault("sha256_manifesto", self.ancora)
        kw.setdefault("extras_gpg", LOOPBACK)
        kw.setdefault("encerrar", False)  # o agente fica entre os testes (a partida custa ~1 s); os que dependem dele o encerram
        return desembrulhar(origem or self.cifrada, self.volta, casa or A.casa, exe=EXE, **kw)

    def assertNada(self) -> None:
        self.assertFalse(self.volta.exists(), "o destino apareceu")
        self.assertEqual([p.name for p in self.tmp.iterdir() if p.name.startswith(".")], [], "sobra de preparo")


class TestDesembrulhar(Base):
    def test_a_pasta_decifrada_e_a_copia_de_antes(self):
        with mock.patch.object(decifra_copia, "encerrar_agente") as agente:  # o padrão do kit: encerra no fim
            r = desembrulhar(self.cifrada, self.volta, A.casa, exe=EXE, sha256_manifesto=self.ancora, extras_gpg=LOOPBACK)
        self.assertTrue(r["ok"])
        self.assertEqual(conteudo_da_pasta(self.volta), conteudo_da_pasta(self.claro))
        self.assertTrue((self.volta / "files" / "projects" / "vazio").is_dir())
        self.assertEqual((r["sha256_manifesto_interno"], r["partes"]), (self.r["sha256_manifesto_interno"], len(self.r["partes"])))
        self.assertEqual(r["ancora"]["situacao"], "conferida")
        self.assertEqual(r["arquivos"], len(conteudo_da_pasta(self.claro)))
        agente.assert_called_once()
        self.assertNotIn("sobra_do_preparo", r)
        self.assertEqual([p.name for p in self.tmp.iterdir() if p.name.startswith(".")], [])

    def test_o_agente_do_gpg_e_encerrado_no_fim_tambem_na_falha(self):
        decifra_copia.encerrar_agente(EXE, A.casa)  # senão o agente lembra da senha certa dos outros testes
        with mock.patch.object(decifra_copia, "encerrar_agente") as agente:
            with self.assertRaises(CifraRecusada):
                self.desembrulhar(extras_gpg=("--pinentry-mode", "loopback", "--passphrase", "errada"), encerrar=True)
        agente.assert_called_once()

    def test_n1_parte_alterada_recusa_antes_do_gpg(self):
        parte = sorted(self.cifrada.glob("parte-*.gpg"))[1]
        dados = bytearray(parte.read_bytes())
        dados[len(dados) // 2] ^= 1
        parte.write_bytes(bytes(dados))
        with _SemGpg():
            with self.assertRaises(ValidationError) as e:
                self.desembrulhar()
        self.assertEqual(e.exception.details["verificacao"]["changed"], [parte.name])
        self.assertIn("o gpg não foi chamado", str(e.exception))
        self.assertNada()

    def test_n2_cifrada_refeita_com_outra_ancora_recusa_antes_do_gpg(self):
        outra = self.tmp / "refeita"
        cifrar_copia(self.claro, outra, A.publica, tamanho_parte=PARTE, exe=EXE, label="forjada")
        with _SemGpg():
            with self.assertRaises(ValidationError):
                self.desembrulhar(outra)
        self.assertNada()

    def test_sem_ancora_so_com_a_aceitacao_explicita(self):
        with _SemGpg():
            with self.assertRaises(ValidationError) as e:
                self.desembrulhar(sha256_manifesto=None)
        self.assertIn("âncora", str(e.exception))
        self.assertNada()
        r = self.desembrulhar(sha256_manifesto=None, aceitar_sem_ancora=True)
        self.assertEqual(r["ancora"]["situacao"], "ausente")
        self.assertIn("aviso_ancora", r)

    def test_destinatario_esperado_diferente_recusa_antes_do_gpg(self):
        with _SemGpg():
            with self.assertRaises(ValidationError):
                self.desembrulhar(destinatario_esperado=B.impressao)
        self.assertNada()

    def test_n5_senha_errada_ou_sem_pinentry_nao_deixa_nada(self):
        for extras in (("--pinentry-mode", "loopback", "--passphrase", "errada"),
                       ("--pinentry-mode", "loopback", "--passphrase", ""), ("--pinentry-mode", "error")):
            with self.subTest(extras=extras):
                decifra_copia.encerrar_agente(EXE, A.casa)  # senão o agente lembra da senha certa dos outros testes
                with self.assertRaises(CifraRecusada) as e:
                    self.desembrulhar(extras_gpg=extras)
                self.assertNotEqual(e.exception.details["codigo_gpg"], 0)
                self.assertIn("a parte inteira foi descartada", str(e.exception))
                self.assertNada()

    def test_chave_de_outro_par_nao_abre(self):
        with self.assertRaises(CifraRecusada):
            self.desembrulhar(casa=B.casa, extras_gpg=LOOPBACK)
        self.assertNada()

    def test_n6_bloco_alterado_com_os_hashes_recalculados(self):
        """Quem altera uma parte E refaz o manifesto externo (e passa pela âncora): o MDC do gpg para a decifra, a parte
        inteira sai e as partes que já tinham sido extraídas também; nada é liberado."""
        parte = sorted(self.cifrada.glob("parte-*.gpg"))[1]
        dados = bytearray(parte.read_bytes())
        dados[len(dados) // 2] ^= 1
        parte.write_bytes(bytes(dados))
        manifesto = json.loads((self.cifrada / MANIFESTO).read_text(encoding="utf-8"))
        for p in manifesto["partes"]:
            if p["nome"] == parte.name:
                p["sha256"] = sha(bytes(dados))
        bruto = json.dumps(manifesto, indent=2).encode("utf-8")
        (self.cifrada / MANIFESTO).write_bytes(bruto)
        extraidas = []
        original = decifra_copia._extrair

        def contar(*args):
            extraidas.append(1)
            return original(*args)

        with mock.patch.object(decifra_copia, "_extrair", contar):
            with self.assertRaises(CifraRecusada) as e:
                self.desembrulhar(sha256_manifesto=sha256_bytes(bruto))
        self.assertEqual(extraidas, [1], "a primeira parte foi extraída; a alterada não")
        self.assertTrue(e.exception.details["entrada_confere"], "o hash da entrada confere: quem recusou foi o MDC do gpg")
        self.assertEqual(e.exception.details["codigo_gpg"], 2)
        self.assertIn("nada foi liberado", str(e.exception))
        self.assertNada()

    def test_parte_que_muda_durante_a_leitura_e_descartada(self):
        """O hash é recalculado no caminho da entrada do gpg: trocar o arquivo depois da conferência não passa."""
        parte = sorted(self.cifrada.glob("parte-*.gpg"))[0]
        original = decifra_copia._decifrar_parte

        def trocar_antes(exe, casa, extras, caminho, info, saida):
            if caminho.name == parte.name:
                dados = bytearray(caminho.read_bytes())
                dados[-5] ^= 1  # mesmo tamanho, outro conteúdo, depois da conferência sem o gpg
                caminho.write_bytes(bytes(dados))
            return original(exe, casa, extras, caminho, info, saida)

        with mock.patch.object(decifra_copia, "_decifrar_parte", trocar_antes):
            with self.assertRaises(CifraRecusada) as e:
                self.desembrulhar()
        self.assertFalse(e.exception.details["entrada_confere"])
        self.assertNada()

    def test_destino_ocupado_ou_dentro_da_cifrada_e_chaveiro_longo(self):
        self.volta.mkdir()
        (self.volta / "x").write_text("já tinha", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.desembrulhar()
        with self.assertRaises(ValidationError):
            desembrulhar(self.cifrada, self.cifrada / "dentro", A.casa, exe=EXE, sha256_manifesto=self.ancora)
        shutil.rmtree(self.volta)
        longo = self.tmp / ("x" * 120)
        with _SemGpg():
            with self.assertRaises(CifraRecusada) as e:
                self.desembrulhar(casa=longo)
        self.assertIn("limite medido", str(e.exception))


class TestExtratorSeguro(Base):
    """N11: o forjador que passou pela âncora monta a parte com tar à vontade; o extrator não escreve fora do preparo nem
    aceita nada além de arquivo e pasta nos lugares do formato."""

    def forjar(self, extras=(), sem=()) -> dict:
        forjada = self.tmp / f"forjada-{next(CONTADOR)}"
        ancora = cifrada_forjada(forjada, self.claro, tar_de(self.claro, extras, sem), A)
        return {"origem": forjada, "sha256_manifesto": ancora}

    def recusado(self, extras, texto: str, tipo=CifraRecusada) -> None:
        with self.assertRaises(tipo) as e:
            self.desembrulhar(**self.forjar(extras))
        self.assertIn(texto, str(e.exception))
        self.assertNada()
        self.assertFalse((self.tmp / "fora.txt").exists())
        self.assertFalse((self.tmp.parent / "fora.txt").exists())

    def test_a_cifrada_forjada_sem_defeito_passa(self):
        """Controle: o forjador que não erra o formato é igual a uma cópia boa (a âncora é que o desmascara)."""
        r = self.desembrulhar(**self.forjar())
        self.assertTrue(r["ok"])

    def test_caminho_absoluto_e_pai(self):
        for nome in ("/fora.txt", "files/../../fora.txt", "../fora.txt", "files/a/../../../fora.txt"):
            with self.subTest(nome=nome):
                self.recusado([(nome, tarfile.REGTYPE, b"x", "")], "fora do formato")

    def test_barra_invertida_dois_pontos_e_unidade(self):
        for nome in ("files\\fora.txt", "files/a:b", "files/C:/fora.txt", "C:/fora.txt"):
            with self.subTest(nome=nome):
                self.recusado([(nome, tarfile.REGTYPE, b"x", "")], "fora do formato")

    def test_fora_de_files_e_state(self):
        for nome in ("fundacao/codigo.py", "state/outro.db", "state/state.sqlite/x", "manifest.json/x", "extra.txt"):
            with self.subTest(nome=nome):
                self.recusado([(nome, tarfile.REGTYPE, b"x", "")], "fora do formato")

    def test_ligacao_dispositivo_e_fifo(self):
        for tipo in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE, tarfile.FIFOTYPE):
            with self.subTest(tipo=tipo):
                self.recusado([("files/ligacao", tipo, b"", "../../fora.txt")], "não é arquivo nem pasta")

    def test_membro_repetido(self):
        self.recusado([("files/AGENTS.md", tarfile.REGTYPE, b"outro conteudo", "")], "duas vezes")

    def test_arquivo_a_mais_que_o_manifesto_nao_confere(self):
        self.recusado([("files/extra.txt", tarfile.REGTYPE, b"a mais", "")], "não confere com o manifesto interno",
                      ValidationError)

    def test_arquivo_trocado_dentro_do_tar_nao_confere(self):
        forjada = self.tmp / f"forjada-{next(CONTADOR)}"
        ancora = cifrada_forjada(forjada, self.claro, tar_de(self.claro, [("files/AGENTS.md", tarfile.REGTYPE, b"x", "")],
                                                           sem=("files/AGENTS.md",)), A)
        with self.assertRaises(ValidationError):
            self.desembrulhar(origem=forjada, sha256_manifesto=ancora)
        self.assertNada()

    def test_manifesto_interno_diferente_do_ancorado(self):
        copia_sintetica(self.tmp / "outro", {"x.txt": b"outro"})
        forjada = self.tmp / f"forjada-{next(CONTADOR)}"
        ancora = cifrada_forjada(forjada, self.claro, tar_de(self.tmp / "outro"), A)
        with self.assertRaises(ValidationError) as e:
            self.desembrulhar(origem=forjada, sha256_manifesto=ancora)
        self.assertIn("não é o ancorado", str(e.exception))
        self.assertNada()

    def test_pasta_de_estado_sem_manifesto_nao_libera(self):
        forjada = self.tmp / f"forjada-{next(CONTADOR)}"
        ancora = cifrada_forjada(forjada, self.claro, tar_de(self.claro, sem=("manifest.json",)), A)
        with self.assertRaises(ValidationError):
            self.desembrulhar(origem=forjada, sha256_manifesto=ancora)
        self.assertNada()


if __name__ == "__main__":
    unittest.main()
