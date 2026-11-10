"""1.7.11 — cópia de segurança cifrada: partes, manifesto externo e conferência sem senha (desenho DESENHO-COPIA-CIFRADA-1.7.11,
lotes 1 e 2 em parte; provas N1, N2, N3, N4 (sem o `gpg`), N7, N8 e a do destinatário errado).

Chave de TESTE criada aqui e apagada no fim (apoio_cifra.py); sem `gpg` 2.4, o módulo pula com o motivo. A cópia é montada
na hora (ou pelo `backup criar`, no teste da cópia real) e a decifra de conferência usa a chave de teste. A conferência sem
senha nunca chama o `gpg`: os testes de adulteração contam as chamadas. Conteúdos fictícios.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio_auditoria import criar_ligacao_dir
from apoio_cifra import CANARIO, arquivos_de_teste, chaveiros, conteudo_da_pasta, copia_sintetica, exigir_gpg, sha
from helpers import FoundationTestCase

from fundacao.core import backup, cifra_copia
from fundacao.core.backup_cifrado import MANIFESTO, cifrar_copia, verificar_cifrada
from fundacao.core.canon import sha256_bytes
from fundacao.core.cifra_copia import CifraRecusada
from fundacao.core.contracts import ValidationError

A = B = EXE = None
PARTE = 64 * 1024  # limite pequeno: a cópia de teste vira várias partes


def setUpModule() -> None:
    global A, B, EXE
    EXE = exigir_gpg()
    A, B = chaveiros("Teste A", "Teste B")  # divididas entre os módulos


class _ProibidoChamar:
    """Contexto em que qualquer chamada ao gpg (Popen ou run) falha o teste."""

    def __enter__(self):
        self.a = mock.patch("subprocess.Popen", side_effect=AssertionError("chamou o gpg"))
        self.b = mock.patch("subprocess.run", side_effect=AssertionError("chamou o gpg"))
        self.a.start(), self.b.start()
        return self

    def __exit__(self, *_):
        self.a.stop(), self.b.stop()


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="bc-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.arquivos = arquivos_de_teste()
        self.claro = self.tmp / "claro"
        self.manifesto = copia_sintetica(self.claro, self.arquivos)
        self.destino = self.tmp / "cifrada"

    def cifrar(self, destino=None, chave=None, **kw) -> dict:
        return cifrar_copia(self.claro, destino or self.destino, (chave or A).publica, tamanho_parte=PARTE, exe=EXE, **kw)

    def partes(self, pasta=None) -> list[Path]:
        return sorted((pasta or self.destino).glob("parte-*.gpg"))

    def reescrever_manifesto(self, pasta: Path, mudar) -> str:
        """Quem forja: altera o manifesto externo e devolve o SHA-256 novo dele (a âncora que o forjador anunciaria)."""
        caminho = pasta / MANIFESTO
        m = json.loads(caminho.read_text(encoding="utf-8"))
        mudar(m)
        bruto = json.dumps(m, ensure_ascii=False, indent=2).encode("utf-8")
        caminho.write_bytes(bruto)
        return sha256_bytes(bruto)


class TestCifrar(Base):
    def test_as_partes_remontam_a_pasta_da_cópia(self):
        r = self.cifrar()
        self.assertTrue(r["cifrada"])
        membros = A.extrair(self.destino, self.tmp / "volta")
        self.assertGreaterEqual(len(self.partes()), 3, "o limite de parte devia dar várias partes")
        self.assertEqual(conteudo_da_pasta(self.tmp / "volta"), conteudo_da_pasta(self.claro))
        self.assertTrue((self.tmp / "volta" / "files" / "projects" / "vazio").is_dir(), "pasta vazia da cópia")
        planos = [n for parte in membros for n in parte if (self.tmp / "volta" / n).is_file()]
        self.assertEqual(len(planos), len(set(planos)), "nenhum arquivo aparece em duas partes")
        self.assertEqual(sorted(planos), sorted(conteudo_da_pasta(self.claro)))
        self.assertEqual(r["sha256_manifesto_interno"], sha((self.claro / "manifest.json").read_bytes()))

    def test_arquivo_maior_que_a_parte_fica_numa_parte_so(self):
        self.cifrar()
        membros = A.extrair(self.destino, self.tmp / "volta")
        onde = [i for i, parte in enumerate(membros) if "files/projects/p2/grande.bin" in parte]
        self.assertEqual(len(onde), 1)
        arquivos = [m for m in membros[onde[0]] if (self.tmp / "volta" / m).is_file()]
        self.assertEqual(arquivos, ["files/projects/p2/grande.bin"])

    def test_a_parte_final_leva_o_banco_e_o_manifesto_interno(self):
        self.cifrar()
        membros = A.extrair(self.destino, self.tmp / "volta")
        self.assertEqual(membros[-1], ["state/state.sqlite", "manifest.json"])
        self.assertEqual(self.partes()[-1].name, "parte-final.gpg")

    def test_manifesto_externo_sem_nomes_de_arquivo(self):
        r = self.cifrar()
        bruto = (self.destino / MANIFESTO).read_bytes()
        m = json.loads(bruto)
        self.assertEqual(sha256_bytes(bruto), r["sha256_manifesto"])
        self.assertEqual({"schema_version", "label", "created_at", "kit_version", "gpg_versao", "formato", "destinatario",
                          "sha256_manifesto_interno", "arquivos", "bytes", "tamanho_parte", "partes", "leia_me"}, set(m))
        self.assertEqual(m["destinatario"]["principal"], A.impressao)
        self.assertEqual(m["arquivos"], len(self.arquivos))
        for parte in m["partes"]:
            self.assertEqual(set(parte), {"nome", "tamanho", "sha256", "membros"})
            self.assertEqual(sha((self.destino / parte["nome"]).read_bytes()), parte["sha256"])
        for nome in list(self.arquivos) + ["projects", "caso.txt", "grande.bin", "state.sqlite", "files/"]:
            self.assertNotIn(nome.encode(), bruto)

    def test_nenhum_texto_em_claro_ao_lado_das_partes(self):
        """N7 e N8: a pasta tem só manifesto, partes e LEIA-ME; o canário (no nome e no conteúdo) e a chave privada não
        aparecem em byte nenhum; cada parte só tem PKESK + dado cifrado."""
        self.cifrar()
        nomes = sorted(p.name for p in self.destino.iterdir())
        self.assertEqual(nomes, sorted(["LEIA-ME.txt", MANIFESTO] + [p.name for p in self.partes()]))
        todos = b"".join(p.read_bytes() for p in self.destino.iterdir())
        for marca in (CANARIO.encode(), b"PRIVATE KEY BLOCK", b"state.sqlite", b"create table"):
            self.assertNotIn(marca, todos)
        self.assertEqual([p.name for p in self.tmp.iterdir() if p.name.startswith(".")], [], "sobra de preparo")
        r = verificar_cifrada(self.destino)
        self.assertNotIn("estrutura_invalida", r)

    def test_o_manifesto_interno_decifrado_e_o_da_ancora(self):
        r = self.cifrar()
        A.extrair(self.destino, self.tmp / "volta")
        self.assertEqual(sha((self.tmp / "volta" / "manifest.json").read_bytes()), r["sha256_manifesto_interno"])

    def test_ancora_no_livro(self):
        livro = self.tmp / "state" / "copias.jsonl"
        r = self.cifrar(livro=livro)
        linha = json.loads(livro.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual((linha["sha256_manifesto"], linha["cifrada"], linha["sha256_manifesto_interno"]),
                         (r["sha256_manifesto"], True, r["sha256_manifesto_interno"]))
        v = verificar_cifrada(self.destino, livro=livro)
        self.assertTrue(v["ok"])
        self.assertEqual((v["ancora"]["situacao"], v["ancora"]["fonte"]), ("conferida", "livro de cópias"))

    def test_so_a_chave_do_destinatario_abre_as_partes(self):
        self.cifrar()
        for parte in self.partes():
            codigo, claro = B.decifrar(parte)
            self.assertNotEqual(codigo, 0, parte.name)
            self.assertEqual(claro, b"")


class TestRecusasDaCifra(Base):
    def assertNada(self):
        self.assertFalse(self.destino.exists())
        self.assertEqual([p.name for p in self.tmp.iterdir() if p.name.startswith(".")], [], "sobra de preparo")

    def test_arquivo_mudado_depois_do_manifesto(self):
        (self.claro / "files" / "projects" / "p1" / "a.bin").write_bytes(os.urandom(30_000))
        with self.assertRaises(ValidationError):
            self.cifrar()
        self.assertNada()

    def test_arquivo_trocado_por_outro_do_mesmo_tamanho(self):
        alvo = self.claro / "files" / "projects" / "p1" / "b.bin"
        alvo.write_bytes(bytes(b ^ 1 for b in alvo.read_bytes()))
        with self.assertRaises(ValidationError) as e:
            self.cifrar()
        self.assertIn("não confere", str(e.exception))
        self.assertNada()

    def test_arquivo_a_mais_ausente_ou_de_outro_tamanho(self):
        extra = self.claro / "files" / "novo.txt"
        extra.write_text("a mais", encoding="utf-8")
        with self.assertRaises(ValidationError):
            self.cifrar()
        extra.unlink()
        (self.claro / "files" / "AGENTS.md").unlink()
        with self.assertRaises(ValidationError):
            self.cifrar()
        self.assertNada()

    def test_ligacao_na_pasta_da_copia(self):
        criar_ligacao_dir(self.claro / "files" / "fora", self.tmp)
        with self.assertRaises(ValidationError):
            self.cifrar()
        self.assertNada()

    def test_destino_ocupado_ou_dentro_da_copia(self):
        self.destino.mkdir()
        (self.destino / "x").write_text("já tinha", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.cifrar()
        with self.assertRaises(ValidationError):
            self.cifrar(destino=self.claro / "files" / "cifrada")

    def test_chave_privada_ou_ausente_nao_cria_cifrada(self):
        with self.assertRaises(CifraRecusada):
            cifrar_copia(self.claro, self.destino, A.privada, tamanho_parte=PARTE, exe=EXE)
        with self.assertRaises(CifraRecusada):
            cifrar_copia(self.claro, self.destino, self.tmp / "sem-chave.asc", tamanho_parte=PARTE, exe=EXE)
        with self.assertRaises(CifraRecusada):
            cifrar_copia(self.claro, self.destino, A.publica, tamanho_parte=PARTE, exe=str(self.tmp / "gpg-que-nao-existe"))
        self.assertNada()

    def test_gpg_que_morre_no_meio_nao_promove_nada(self):
        escritas = []
        original = cifra_copia.Cifrador.write

        def matar_na_terceira(self, dados):
            escritas.append(1)
            if len(escritas) == 3:
                self._p.kill()
                self._p.wait()
            return original(self, dados)

        with mock.patch.object(cifra_copia.Cifrador, "write", matar_na_terceira):
            with self.assertRaises(CifraRecusada):
                self.cifrar()
        self.assertNada()

    def test_parte_pequena_demais(self):
        with self.assertRaises(ValidationError):
            cifrar_copia(self.claro, self.destino, A.publica, tamanho_parte=10, exe=EXE)
        self.assertNada()


class TestVerificarSemSenha(Base):
    """A cópia cifrada é feita uma vez para a classe (molde); cada teste trabalha numa cópia de arquivos dela."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.molde = Path(tempfile.mkdtemp(prefix="bc-molde-"))
        cls.addClassCleanup(shutil.rmtree, cls.molde, ignore_errors=True)
        cls.arquivos_molde = arquivos_de_teste()
        copia_sintetica(cls.molde / "claro", cls.arquivos_molde)
        cls.r_molde = cifrar_copia(cls.molde / "claro", cls.molde / "cifrada", A.publica, tamanho_parte=PARTE, exe=EXE)

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="bc-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.arquivos, self.claro, self.destino = self.arquivos_molde, self.tmp / "claro", self.tmp / "cifrada"
        shutil.copytree(self.molde / "claro", self.claro)
        shutil.copytree(self.molde / "cifrada", self.destino)
        self.r = self.r_molde
        self.ancora = self.r["sha256_manifesto"]

    def verificar(self, pasta=None, **kw) -> dict:
        with _ProibidoChamar():  # a conferência sem senha não chama o gpg
            return verificar_cifrada(pasta or self.destino, **kw)

    def test_copia_integra(self):
        v = self.verificar(sha256_manifesto=self.ancora, destinatario_esperado=A.impressao)
        self.assertTrue(v["ok"], v)
        self.assertEqual((v["cifrada"], v["conteudo_conferido"], v["partes"]), (True, False, len(self.partes())))
        self.assertIn("exige a senha", v["conteudo"])
        self.assertEqual(v["ancora"]["situacao"], "conferida")
        self.assertEqual(v["sha256_manifesto_interno"], self.r["sha256_manifesto_interno"])
        self.assertEqual(v["copia"]["rotulo"], "teste-cifrado")

    def test_sem_ancora_avisa(self):
        v = self.verificar()
        self.assertTrue(v["ok"])
        self.assertEqual(v["ancora"]["situacao"], "ausente")
        self.assertIn("aviso_ancora", v)

    def test_n1_um_byte_trocado_numa_parte(self):
        parte = self.partes()[1]
        dados = bytearray(parte.read_bytes())
        dados[len(dados) // 2] ^= 1
        parte.write_bytes(bytes(dados))
        v = self.verificar(sha256_manifesto=self.ancora)
        self.assertFalse(v["ok"])
        self.assertEqual(v["changed"], [parte.name])

    def test_n2_copia_refeita_com_a_mesma_chave_publica_e_manifesto_recalculado(self):
        outra = self.tmp / "refeita"
        cifrar_copia(self.claro, outra, A.publica, tamanho_parte=PARTE, exe=EXE, label="forjada")
        self.assertTrue(self.verificar(outra)["ok"], "sem âncora, a cópia refeita passa: é a âncora que a desmascara")
        v = self.verificar(outra, sha256_manifesto=self.ancora)
        self.assertFalse(v["ok"])
        self.assertEqual(v["ancora"]["situacao"], "divergente")

    def test_n3_parte_apagada_a_mais_ou_trocada_de_nome(self):
        p1, p2 = self.partes()[:2]
        p1_dados, p2_dados = p1.read_bytes(), p2.read_bytes()
        p1.write_bytes(p2_dados)
        p2.write_bytes(p1_dados)
        v = self.verificar(sha256_manifesto=self.ancora)
        self.assertEqual((v["ok"], sorted(v["changed"])), (False, sorted([p1.name, p2.name])))
        p1.write_bytes(p1_dados)
        p2.write_bytes(p2_dados)
        (self.destino / "extra.txt").write_text("a mais", encoding="utf-8")
        v = self.verificar(sha256_manifesto=self.ancora)
        self.assertEqual((v["ok"], v["extras"]), (False, ["extra.txt"]))
        (self.destino / "extra.txt").unlink()
        p2.unlink()
        v = self.verificar(sha256_manifesto=self.ancora)
        self.assertEqual((v["ok"], v["missing"]), (False, [p2.name]))

    def test_parte_trocada_por_ligacao(self):
        parte = self.partes()[0]
        shutil.move(parte, self.tmp / "guardada.gpg")
        criar_ligacao_dir(parte, self.tmp)  # junção (Windows) ou link simbólico no lugar da parte
        v = self.verificar(sha256_manifesto=self.ancora)
        self.assertFalse(v["ok"])
        self.assertIn(parte.name, v["ligacoes"])

    def test_pasta_a_mais_dentro_da_copia_cifrada(self):
        (self.destino / "subpasta").mkdir()
        (self.destino / "subpasta" / "x.txt").write_text("x", encoding="utf-8")
        v = self.verificar(sha256_manifesto=self.ancora)
        self.assertFalse(v["ok"])
        self.assertIn("subpasta", v["extras"])

    def test_n4_parte_truncada(self):
        """Truncada sem recalcular nada: tamanho e hash acusam. Truncada com o manifesto refeito pelo forjador: a âncora
        guardada fora acusa; sem âncora, o cabeçalho de uma parte cortada no começo também."""
        parte = self.partes()[1]
        inteira = parte.read_bytes()
        parte.write_bytes(inteira[:-100])
        v = self.verificar(sha256_manifesto=self.ancora)
        self.assertEqual((v["ok"], v["changed"]), (False, [parte.name]))

        def refazer(corte):
            def mudar(m):
                for p in m["partes"]:
                    if p["nome"] == parte.name:
                        p["tamanho"], p["sha256"] = corte, sha(inteira[:corte])
            parte.write_bytes(inteira[:corte])
            return self.reescrever_manifesto(self.destino, mudar)

        novo = refazer(len(inteira) - 100)
        self.assertEqual(self.verificar(sha256_manifesto=self.ancora)["ancora"]["situacao"], "divergente")
        self.assertFalse(self.verificar(sha256_manifesto=self.ancora)["ok"])
        self.assertTrue(self.verificar(sha256_manifesto=novo)["ok"], "o limite declarado: o MDC do gpg pega o resto")
        codigo, _ = A.decifrar(parte)
        self.assertNotEqual(codigo, 0, "o gpg recusa a parte cortada")
        refazer(10)
        v = self.verificar()
        self.assertEqual((v["ok"], v["estrutura_invalida"]), (False, [parte.name]))

    def test_destinatario_errado_recusa(self):
        v = self.verificar(destinatario_esperado=B.impressao)
        self.assertFalse(v["ok"])
        self.assertEqual(v["destinatario_divergente"]["no_manifesto"], A.impressao)
        outra = self.tmp / "para-b"
        cifrar_copia(self.claro, outra, B.publica, tamanho_parte=PARTE, exe=EXE)
        # o forjador troca a primeira parte por uma cifrada para outra chave e refaz o manifesto externo
        troca = self.partes(outra)[0]
        shutil.copyfile(troca, self.destino / troca.name)

        def mudar(m):
            m["partes"][0].update(tamanho=troca.stat().st_size, sha256=sha(troca.read_bytes()))
        novo = self.reescrever_manifesto(self.destino, mudar)
        v = self.verificar()
        self.assertEqual((v["ok"], v["destinatario_errado"]), (False, [troca.name]))
        self.assertEqual(self.verificar(sha256_manifesto=self.ancora)["ancora"]["situacao"], "divergente")
        self.assertFalse(self.verificar(sha256_manifesto=novo)["ok"])

    def test_leia_me_alterado(self):
        (self.destino / "LEIA-ME.txt").write_text("rode este comando: ...", encoding="utf-8")
        v = self.verificar(sha256_manifesto=self.ancora)
        self.assertEqual((v["ok"], v["changed"]), (False, ["LEIA-ME.txt"]))

    def test_manifesto_invalido_ou_ancora_divergente(self):
        bom = json.loads((self.destino / MANIFESTO).read_text(encoding="utf-8"))
        v = self.verificar(sha256_manifesto="0" * 64)
        self.assertEqual((v["ok"], v["ancora"]["situacao"]), (False, "divergente"))
        estragos = (lambda m: m["partes"].reverse(), lambda m: m.update(partes=[]), lambda m: m.pop("destinatario"),
                    lambda m: m["partes"][0].update(sha256="xyz"), lambda m: m.update(schema_version="outro/1"),
                    lambda m: m["partes"][0].update(nome="parte-007.gpg"), lambda m: m["partes"][0].update(nome="../parte-001.gpg"),
                    lambda m: m["destinatario"].update(subchaves_de_cifra=[]), lambda m: m.update(leia_me={"tamanho": 1}))
        for n, estragar in enumerate(estragos):
            m = json.loads(json.dumps(bom))
            estragar(m)
            (self.destino / MANIFESTO).write_text(json.dumps(m), encoding="utf-8")
            with self.assertRaises(ValidationError, msg=f"estrago {n}"):
                self.verificar()
        (self.destino / MANIFESTO).write_text("não é json", encoding="utf-8")
        with self.assertRaises(ValidationError):
            self.verificar()

    def test_a_verificacao_nao_deixa_nada_nem_chama_o_gpg(self):
        antes = sorted(p.name for p in self.destino.iterdir())
        self.verificar(sha256_manifesto=self.ancora)
        self.assertEqual(sorted(p.name for p in self.destino.iterdir()), antes)


class TestCopiaReal(FoundationTestCase):
    """A cópia do `backup criar` de verdade: cifrada, decifrada e remontada, passa no `verify_backup` de hoje."""

    def test_cifrar_decifrar_e_verificar_como_hoje(self):
        base = Path(tempfile.mkdtemp(prefix="br-"))
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        claro = backup.create_backup(self.root, base / "claro", "lab-cifrado")
        r = cifrar_copia(base / "claro", base / "cifrada", A.publica, tamanho_parte=1 << 20, exe=EXE)
        self.assertEqual(r["sha256_manifesto_interno"], claro["sha256_manifesto"])
        v = verificar_cifrada(base / "cifrada", sha256_manifesto=r["sha256_manifesto"], destinatario_esperado=A.impressao)
        self.assertTrue(v["ok"], v)
        A.extrair(base / "cifrada", base / "volta")
        depois = backup.verify_backup(base / "volta", sha256_manifesto=claro["sha256_manifesto"])
        self.assertTrue(depois["ok"], depois)
        self.assertEqual(depois["ancora"]["situacao"], "conferida")
        self.assertEqual(conteudo_da_pasta(base / "volta"), conteudo_da_pasta(base / "claro"))


if __name__ == "__main__":
    unittest.main()
