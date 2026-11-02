"""Trava do banco entre o Windows e o Ubuntu (1.7.10; contratos do lote 2, §4): o marcador state/banco.trava do OUTRO
lado recusa abrir o banco — vivo ou velho —, o marcador velho só sai pelo comando explícito do titular (`banco
destravar --confirmar`) e quem abre do mesmo lado continua como antes. Também a saída de erro de arquivo da CLI com a
sobra do preparo (a outra mudança deste pacote em __main__.py). Raiz descartável; o "outro lado" é simulado pelo campo
`lado` do marcador (o oposto do desta máquina)."""

from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest import mock

from helpers import FoundationTestCase

from fundacao.__main__ import main
from fundacao.core import trava_banco
from fundacao.core.auth import ENV_PRINCIPAL
from fundacao.core.db import conectar_somente_leitura, connect

OUTRO = "ubuntu" if trava_banco.lado_desta_maquina() == "windows" else "windows"
MESMO = trava_banco.lado_desta_maquina()


def _iso(delta_s: float = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=delta_s)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def dados_do_marcador(lado: str = OUTRO, idade_s: float = 0, **extra) -> dict:
    return {"lado": lado, "host": "maquina-ficticia", "pid": 4242, "desde": _iso(idade_s + 60),
            "renovada_em": _iso(idade_s), **extra}


class TravaBancoCase(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.estado = self.root / "state"
        self.marcador = self.estado / trava_banco.MARCADOR

    def marcar(self, lado: str = OUTRO, *, idade_s: float = 0, **extra) -> dict:
        dados = dados_do_marcador(lado, idade_s, **extra)
        self.marcador.write_text(json.dumps(dados), encoding="utf-8")
        return dados

    def cli(self, *args) -> tuple[int, dict | None, str]:
        saida, erro = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {ENV_PRINCIPAL: "operador-lab"}), redirect_stdout(saida), \
                redirect_stderr(erro):
            codigo = main(["--raiz", str(self.root), *args])
        texto = saida.getvalue()
        return codigo, (json.loads(texto) if texto.strip() else None), erro.getvalue()


class TestConferir(TravaBancoCase):
    def test_sem_marcador_e_marcador_do_mesmo_lado_nao_mudam_nada(self):
        trava_banco.conferir(self.estado)
        self.marcar(MESMO)
        trava_banco.conferir(self.estado)
        self.marcar(MESMO, idade_s=10_000)  # velho do mesmo lado também não muda quem abre deste lado
        trava_banco.conferir(self.estado)

    def test_marcador_vivo_do_outro_lado_recusa(self):
        self.marcar(OUTRO)
        with self.assertRaises(trava_banco.BancoTravado) as ctx:
            trava_banco.conferir(self.estado)
        erro = ctx.exception.as_dict()["error"]
        self.assertEqual((erro["code"], erro["situacao"], erro["lado"]), ("E_BANCO_TRAVADO", "vivo", OUTRO))
        self.assertIn("em uso", str(ctx.exception))
        self.assertTrue(self.marcador.exists(), "conferir nunca tira o marcador")

    def test_marcador_velho_do_outro_lado_recusa_e_mostra_o_comando_do_titular(self):
        self.marcar(OUTRO, idade_s=trava_banco.VIVO_S + 5)
        with self.assertRaises(trava_banco.BancoTravado) as ctx:
            trava_banco.conferir(self.estado)
        self.assertEqual(ctx.exception.details["situacao"], "velho")
        self.assertIn("banco destravar --confirmar", str(ctx.exception))
        self.assertTrue(self.marcador.exists(), "marcador velho não sai em silêncio")

    def test_lado_explicito_vale_para_os_dois_sentidos(self):
        self.marcar("ubuntu")
        trava_banco.conferir(self.estado, lado="ubuntu")
        with self.assertRaises(trava_banco.BancoTravado):
            trava_banco.conferir(self.estado, lado="windows")

    def test_marcador_ilegivel_recusa_dos_dois_lados(self):
        casos = {"lixo": lambda: self.marcador.write_bytes(b"\xff nao e json"),
                 "campo a menos": lambda: self.marcador.write_text(json.dumps({"lado": OUTRO}), encoding="utf-8"),
                 "campo a mais": lambda: self.marcar(OUTRO, projeto="x"),
                 "lado desconhecido": lambda: self.marcar("macos"),
                 "pid texto": lambda: self.marcar(OUTRO, pid="1"),
                 "acima do teto": lambda: self.marcador.write_bytes(b" " * (trava_banco.TETO + 1)),
                 "pasta": lambda: self.marcador.mkdir()}
        for nome, criar in casos.items():
            with self.subTest(caso=nome):
                criar()
                for lado in ("windows", "ubuntu"):
                    with self.assertRaises(trava_banco.BancoTravado) as ctx:
                        trava_banco.conferir(self.estado, lado=lado)
                    self.assertEqual(ctx.exception.details["situacao"], "ilegivel")
                if self.marcador.is_dir():
                    self.marcador.rmdir()
                else:
                    self.marcador.unlink()

    def test_marcador_que_e_ligacao_ou_vinculo_fisico_recusa(self):
        fora = self.root / "marcador-de-fora.json"
        fora.write_text(json.dumps(dados_do_marcador(MESMO)), encoding="utf-8")
        for tipo, criar in (("vínculo físico", lambda: os.link(fora, self.marcador)),
                            ("link simbólico", lambda: os.symlink(fora, self.marcador))):
            with self.subTest(tipo=tipo):
                try:
                    criar()
                except (OSError, NotImplementedError) as exc:
                    self.skipTest(f"{tipo} indisponível aqui: {exc}")
                with self.assertRaises(trava_banco.BancoTravado):
                    trava_banco.conferir(self.estado, lado=MESMO)  # nem do mesmo lado: não se confia no conteúdo
                self.marcador.unlink()


class TestAberturaDoBanco(TravaBancoCase):
    def test_connect_e_leitura_recusam_com_o_outro_lado_e_abrem_com_o_mesmo(self):
        banco = self.estado / "state.sqlite"
        self.marcar(OUTRO)
        with self.assertRaises(trava_banco.BancoTravado):
            connect(banco)
        with self.assertRaises(trava_banco.BancoTravado):
            conectar_somente_leitura(banco)
        self.marcar(MESMO)
        connect(banco).close()
        conectar_somente_leitura(banco).close()

    def test_connect_recusa_antes_de_criar_o_banco(self):
        outra = self.root / "outra-raiz" / "state"
        outra.mkdir(parents=True)
        (outra / trava_banco.MARCADOR).write_text(json.dumps(dados_do_marcador(OUTRO)), encoding="utf-8")
        with self.assertRaises(trava_banco.BancoTravado):
            connect(outra / "state.sqlite")
        self.assertFalse((outra / "state.sqlite").exists())

    def test_cli_status_recusa_com_o_outro_lado_e_segue_com_o_mesmo(self):
        self.marcar(OUTRO)
        codigo, saida, erro = self.cli("status")
        self.assertEqual((codigo, saida), (2, None))
        self.assertEqual(json.loads(erro)["error"]["code"], "E_BANCO_TRAVADO")
        self.marcar(MESMO)
        codigo, saida, erro = self.cli("status")
        self.assertEqual(codigo, 0, erro)
        self.assertIsNone(saida["projeto_travado"])


class TestDestravar(TravaBancoCase):
    def test_situacao_sem_abrir_o_banco(self):
        codigo, r, erro = self.cli("banco", "situacao")
        self.assertEqual((codigo, r["situacao"]), (0, "ausente"), erro)
        self.marcar(OUTRO, idade_s=trava_banco.VIVO_S + 5)
        with mock.patch("fundacao.__main__._con", side_effect=AssertionError("abriu o banco")):
            codigo, r, erro = self.cli("banco", "situacao")
        self.assertEqual((codigo, r["situacao"], r["conteudo"]["lado"]), (0, "velho", OUTRO), erro)
        self.assertIn("banco destravar --confirmar", r["para_o_titular"])

    def test_destravar_exige_confirmar_e_tira_so_o_velho(self):
        self.marcar(OUTRO, idade_s=trava_banco.VIVO_S + 5)
        codigo, _r, erro = self.cli("banco", "destravar")
        self.assertEqual(codigo, 2)
        self.assertIn("--confirmar", erro)
        self.assertTrue(self.marcador.exists())
        codigo, r, erro = self.cli("banco", "destravar", "--confirmar")
        self.assertEqual((codigo, r["removido"], r["situacao"]), (0, True, "velho"), erro)
        self.assertFalse(self.marcador.exists())
        codigo, r, erro = self.cli("banco", "destravar", "--confirmar")
        self.assertEqual((codigo, r["removido"], r["situacao"]), (0, False, "ausente"), erro)

    def test_destravar_recusa_o_marcador_vivo(self):
        self.marcar(OUTRO)
        codigo, _r, erro = self.cli("banco", "destravar", "--confirmar")
        self.assertEqual(codigo, 2)
        self.assertEqual(json.loads(erro)["error"]["code"], "E_BANCO_TRAVADO")
        self.assertTrue(self.marcador.exists())

    def test_destravar_tira_marcador_ilegivel_e_ligacao_sem_seguir(self):
        self.marcador.write_bytes(b"lixo")
        self.assertEqual(trava_banco.destravar(self.estado, confirmar=True)["situacao"], "ilegivel")
        self.assertFalse(self.marcador.exists())
        alvo = self.root / "alvo-ficticio.json"
        alvo.write_text("{}", encoding="utf-8")
        try:
            os.symlink(alvo, self.marcador)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"link simbólico indisponível aqui: {exc}")
        self.assertTrue(trava_banco.destravar(self.estado, confirmar=True)["removido"])
        self.assertTrue(alvo.exists(), "o destino da ligação não é tocado")

    def test_status_volta_a_abrir_depois_de_destravar(self):
        self.marcar(OUTRO, idade_s=trava_banco.VIVO_S + 5)
        self.assertEqual(self.cli("status")[0], 2)
        self.assertEqual(self.cli("banco", "destravar", "--confirmar")[0], 0)
        self.assertEqual(self.cli("status")[0], 0)


class TestErroDeArquivoNaCli(TravaBancoCase):
    """A outra mudança deste pacote na saída de erro de `main()` (__main__.py, 1.7.10; pendência do BACKUP; revisão do
    lote 2: faltava o teste): o erro de arquivo leva a sobra do preparo, quando há, junto do código E_ARQUIVO."""

    def test_sobra_do_preparo_vai_no_erro_de_arquivo(self):
        erro = OSError(28, "disco cheio (simulado)")
        erro.sobra_do_preparo = {"pasta": str(self.root / "preparo-ficticio"), "limpa": False, "arquivos": 2,
                                 "pastas": 1, "ligacoes": 0, "bytes": 10, "erros": []}
        with mock.patch("fundacao.cli_backup.executar", side_effect=erro):
            codigo, saida, texto = self.cli("backup", "situacao")
        self.assertEqual((codigo, saida), (2, None))
        falha = json.loads(texto.strip().splitlines()[-1])["error"]
        self.assertEqual((falha["code"], falha["tipo"]), ("E_ARQUIVO", "OSError"))
        self.assertEqual(falha["sobra_do_preparo"], erro.sobra_do_preparo)

    def test_erro_de_arquivo_sem_sobra_nao_leva_o_campo(self):
        with mock.patch("fundacao.cli_backup.executar", side_effect=OSError(5, "falha de leitura (simulada)")):
            codigo, _saida, texto = self.cli("backup", "situacao")
        self.assertEqual(codigo, 2)
        falha = json.loads(texto.strip().splitlines()[-1])["error"]
        self.assertEqual(falha["code"], "E_ARQUIVO")
        self.assertNotIn("sobra_do_preparo", falha)


if __name__ == "__main__":
    import unittest
    unittest.main()
