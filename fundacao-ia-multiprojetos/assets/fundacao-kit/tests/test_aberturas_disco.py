"""Disco da ficha de aberturas (core/aberturas_disco.py; 1.7.10, contratos do lote 2, §5; revisão independente do
pacote ABERTURAS, 31/10/2026): a pasta aberta sem seguir ligação, a leitura e a gravação presas a ela (no POSIX, pelo
descritor) e o arquivo novo que nunca sobrescreve. Só pastas temporárias e conteúdo fictício."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import helpers  # noqa: F401  (o kit no sys.path)

from fundacao.core import aberturas_disco as disco
from fundacao.core.contracts import AlreadyExists, PathEscape


def ligar_pasta(teste: unittest.TestCase, link: Path, alvo: Path) -> None:
    """Junção no Windows (`mklink /J`, sem administrador); link simbólico nos demais."""
    if os.name == "nt":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(alvo)], capture_output=True, text=True)
        if r.returncode != 0:
            teste.skipTest(f"junção indisponível: {r.stdout} {r.stderr}")
        return
    link.symlink_to(alvo, target_is_directory=True)


class DiscoCase(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="aberturas-disco-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.raiz = self.base / "raiz"
        self.raiz.mkdir()
        self.fora = self.base / "fora"
        self.fora.mkdir()


class TestPasta(DiscoCase):
    def test_cria_le_e_lista_pela_pasta(self):
        with disco.Pasta(self.raiz, ("outputs", "aberturas"), criar=True) as pasta:
            self.assertTrue(pasta.existe)
            pasta.criar_novo("ficha-v1.json", b"{}\n")
            self.assertEqual(pasta.nomes(), ["ficha-v1.json"])
            self.assertEqual(pasta.ler("ficha-v1.json", 10), b"{}\n")
            self.assertIsNone(pasta.ler("nao-existe.json", 10))
            with self.assertRaises(disco.LeituraRecusada):
                pasta.ler("ficha-v1.json", 2)  # acima do teto
        self.assertEqual((self.raiz / "outputs" / "aberturas" / "ficha-v1.json").read_bytes(), b"{}\n")
        with disco.Pasta(self.raiz, ("nao", "existe")) as ausente:
            self.assertFalse(ausente.existe)
            self.assertEqual((ausente.nomes(), ausente.ler("x", 10)), ([], None))
        self.assertFalse((self.raiz / "nao").exists())  # sem `criar`, nada é criado

    def test_criar_novo_nunca_sobrescreve(self):
        """publicar_novo da revisão: sobre arquivo existente, E_EXISTS e o conteúdo antigo fica."""
        with disco.Pasta(self.raiz, ("caixa",), criar=True) as pasta:
            pasta.criar_novo("ficha-v1.json", b"antigo")
            with self.assertRaises(AlreadyExists) as ctx:
                pasta.criar_novo("ficha-v1.json", b"novo")
            self.assertEqual(ctx.exception.code, "E_EXISTS")
            self.assertEqual(sorted(pasta.nomes()), ["ficha-v1.json"])  # nenhum temporário sobrou
        self.assertEqual((self.raiz / "caixa" / "ficha-v1.json").read_bytes(), b"antigo")

    def test_trocar_poe_no_lugar(self):
        with disco.Pasta(self.raiz, ("caixa",), criar=True) as pasta:
            pasta.trocar("ficha-v1.json.sig", b"primeira")
            pasta.trocar("ficha-v1.json.sig", b"segunda")
            self.assertEqual(pasta.nomes(), ["ficha-v1.json.sig"])
        self.assertEqual((self.raiz / "caixa" / "ficha-v1.json.sig").read_bytes(), b"segunda")

    def test_pasta_ligada_no_caminho_recusa_e_nada_vai_para_o_outro_lado(self):
        (self.raiz / "outputs").mkdir()
        ligar_pasta(self, self.raiz / "outputs" / "aberturas", self.fora)
        for criar in (False, True):
            with self.subTest(criar=criar):
                with self.assertRaises(PathEscape) as ctx:
                    disco.Pasta(self.raiz, ("outputs", "aberturas"), criar=criar)
                self.assertEqual(ctx.exception.code, "E_PATH_ESCAPE")
        self.assertEqual(list(self.fora.iterdir()), [])
        with disco.Pasta(self.raiz, ("outputs",)) as pasta:
            with self.assertRaises(PathEscape):
                pasta.sub("aberturas")

    def test_absoluta_recusa_ligacao_em_qualquer_ponto_do_caminho(self):
        """A área do titular e a caixa de entrada: abertas da raiz do volume para baixo (o preparo do host as lê como
        root; no POSIX, sem intervalo entre conferir e abrir)."""
        (self.fora / "ficha").mkdir()
        (self.fora / "ficha" / "ficha-v1.json").write_bytes(b"{}")
        ligar_pasta(self, self.raiz / "atalho", self.fora)
        with disco.Pasta.absoluta(self.raiz) as pasta:
            self.assertTrue(pasta.existe)
            self.assertEqual(pasta.nomes(), ["atalho"])
        with self.assertRaises(PathEscape):
            disco.Pasta.absoluta(self.raiz / "atalho" / "ficha")
        with disco.Pasta.absoluta(self.base / "nao-existe" / "ficha") as ausente:
            self.assertFalse(ausente.existe)

    def test_parte_que_e_arquivo_recusa(self):
        (self.raiz / "outputs").write_bytes(b"x")
        with self.assertRaises(PathEscape):
            disco.Pasta(self.raiz, ("outputs", "aberturas"))

    def test_vinculo_fisico_nao_e_lido(self):
        (self.fora / "segredo.json").write_bytes(b'{"ficticio": 1}')
        (self.raiz / "caixa").mkdir()
        try:
            os.link(self.fora / "segredo.json", self.raiz / "caixa" / "ficha-v1.json")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"vínculo físico indisponível: {exc}")
        with disco.Pasta(self.raiz, ("caixa",)) as pasta:
            with self.assertRaises(disco.LeituraRecusada) as ctx:
                pasta.ler("ficha-v1.json", 100)
        self.assertIn("recusado", str(ctx.exception))


@unittest.skipUnless(disco.POR_DESCRITOR, "pasta aberta por descritor só no POSIX (no Windows, o caminho conferido)")
class TestPastaPeloDescritor(DiscoCase):
    """A troca de uma pasta por link DEPOIS de aberta não desvia a gravação nem a leitura (antes, o arquivo era aberto
    pelo caminho e ia para o outro lado do link)."""

    def trocar_por_link(self, pasta: Path, alvo: Path) -> Path:
        movida = pasta.with_name(pasta.name + "-movida")
        pasta.rename(movida)
        pasta.symlink_to(alvo, target_is_directory=True)
        return movida

    def test_gravacao_fica_na_pasta_aberta(self):
        (self.fora / "aberturas").mkdir()
        with disco.Pasta(self.raiz, ("outputs", "aberturas"), criar=True) as pasta:
            movida = self.trocar_por_link(self.raiz / "outputs", self.fora)
            pasta.criar_novo("ficha-v1.json", b"{}\n")
            pasta.trocar("ficha-v1.json.sig", b"sig")
        self.assertEqual(sorted(p.name for p in (movida / "aberturas").iterdir()), ["ficha-v1.json", "ficha-v1.json.sig"])
        self.assertEqual(list((self.fora / "aberturas").iterdir()), [])

    def test_leitura_fica_na_pasta_aberta(self):
        (self.raiz / "outputs").mkdir()
        (self.raiz / "outputs" / "rascunho.json").write_bytes(b'{"motivo": "do projeto"}')
        (self.fora / "rascunho.json").write_bytes(b'{"motivo": "de outro projeto (ficticio)"}')
        with disco.Pasta(self.raiz, ("outputs",)) as pasta:
            self.trocar_por_link(self.raiz / "outputs", self.fora)
            self.assertEqual(pasta.ler("rascunho.json", 100), b'{"motivo": "do projeto"}')
            self.assertEqual(pasta.nomes(), ["rascunho.json"])
        with self.assertRaises(PathEscape):  # aberta de novo, a ligação no caminho recusa
            disco.Pasta(self.raiz, ("outputs",))

    def test_link_no_nome_do_arquivo(self):
        alvo = self.fora / "de-fora.json"
        alvo.write_bytes(b"de fora (ficticio)")
        (self.raiz / "caixa").mkdir()
        (self.raiz / "caixa" / "ficha-v1.json").symlink_to(alvo)
        (self.raiz / "caixa" / "ficha-v1.json.sig").symlink_to(alvo)
        with disco.Pasta(self.raiz, ("caixa",)) as pasta:
            with self.assertRaises(disco.LeituraRecusada):
                pasta.ler("ficha-v1.json", 100)
            with self.assertRaises(AlreadyExists):
                pasta.criar_novo("ficha-v1.json", b"novo")
            pasta.trocar("ficha-v1.json.sig", b"sig")  # troca o link, não grava através dele
        self.assertEqual(alvo.read_bytes(), b"de fora (ficticio)")
        self.assertFalse((self.raiz / "caixa" / "ficha-v1.json.sig").is_symlink())
        self.assertEqual((self.raiz / "caixa" / "ficha-v1.json.sig").read_bytes(), b"sig")

    def test_fifo_nao_trava(self):
        (self.raiz / "caixa").mkdir()
        os.mkfifo(self.raiz / "caixa" / "ficha-v1.json")
        with disco.Pasta(self.raiz, ("caixa",)) as pasta:
            with self.assertRaises(disco.LeituraRecusada):
                pasta.ler("ficha-v1.json", 100)

    def test_temporario_trocado_por_link_nao_vira_vinculo_com_o_alvo(self):
        """Reconferência do pacote (01/11/2026): o vínculo do criar_novo não segue ligação. Antes (linkat com
        AT_SYMLINK_FOLLOW), o temporário trocado por um link no intervalo virava um vínculo físico com o alvo de
        fora (st_nlink 2); agora o nome novo é o próprio link, que o leitor recusa, e o alvo fica intocado."""
        alvo = self.fora / "de-fora.json"
        alvo.write_bytes(b"de fora (ficticio)")
        original = disco.Pasta._temporario

        def temporario_trocado(pasta, nome, dados):
            tmp = original(pasta, nome, dados)
            os.unlink(tmp, dir_fd=pasta._fd)
            os.symlink(alvo, tmp, dir_fd=pasta._fd)
            return tmp
        with disco.Pasta(self.raiz, ("caixa",), criar=True) as pasta:
            with unittest.mock.patch.object(disco.Pasta, "_temporario", temporario_trocado):
                pasta.criar_novo("ficha-v1.json", b"{}\n")
            self.assertEqual(os.stat(alvo).st_nlink, 1)
            with self.assertRaises(disco.LeituraRecusada):
                pasta.ler("ficha-v1.json", 100)
            self.assertEqual(pasta.nomes(), ["ficha-v1.json"])  # nenhum temporário sobrou
        self.assertEqual(alvo.read_bytes(), b"de fora (ficticio)")


if __name__ == "__main__":
    unittest.main()
