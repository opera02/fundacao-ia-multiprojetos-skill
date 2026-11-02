"""1.7.10 — nova tentativa na renomeação final (desenho 1.7.10, §5.8; MELHORIAS-1.7.10, §0 item 15).

Falha real de 31/10/2026: o `backup criar` rodou 22 minutos e terminou com "[WinError 5] Acesso negado" na renomeação
da pasta preparada para o destino; nada foi repetido, e a restauração dizia "o destino mudou" para a mesma causa.
Agora `preparo.promover` e `preparo.renomear` repetem só a recusa passageira do Windows (5, 32 e 33) com esperas, e a
cada tentativa conferem de novo o preparo e o destino; esgotadas, E_PROMOCAO com as tentativas e os atributos. A trava
é simulada pelo `_renomear` injetado (PermissionError com winerror), que roda em qualquer sistema; as esperas também
são injetadas. Conteúdos fictícios.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio_auditoria import criar_ligacao_dir
from helpers import FoundationTestCase

from fundacao.core import backup, preparo
from fundacao.core.contracts import ValidationError


def recusa(winerror: int = 5) -> PermissionError:
    exc = PermissionError(13, "Acesso negado (simulado)")
    exc.winerror = winerror
    return exc


class Renomeador:
    """`_renomear` injetado: recusa as `falhas` primeiras chamadas (com `winerror`) e depois renomeia de verdade."""

    def __init__(self, falhas: int, winerror: int = 5, antes=None):
        self.falhas, self.winerror, self.antes, self.chamadas = falhas, winerror, antes, 0

    def __call__(self, origem, destino):
        self.chamadas += 1
        if self.antes:
            self.antes(self.chamadas)
        if self.chamadas <= self.falhas:
            raise recusa(self.winerror)
        return os.rename(origem, destino)


class TestPromover(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="fundacao-promocao-"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.alvo = self.base / "copia"
        self.pasta = preparo.criar_preparo(self.alvo)
        (self.pasta / "manifest.json").write_text("{}", encoding="utf-8")
        self.esperas: list = []

    def promover(self, renomeador):
        with mock.patch.object(preparo, "_renomear", renomeador), \
                mock.patch.object(preparo, "_esperar", side_effect=self.esperas.append):
            return preparo.promover(self.pasta, self.alvo)

    def test_trava_passageira_passa_na_terceira_tentativa(self):
        r = Renomeador(falhas=2)
        self.assertFalse(self.promover(r))
        self.assertEqual(r.chamadas, 3)
        self.assertEqual(self.esperas, [1, 2])
        self.assertTrue((self.alvo / "manifest.json").is_file())
        self.assertFalse(self.pasta.exists())

    def test_cada_codigo_passageiro_se_repete(self):
        for codigo in (32, 33):
            with self.subTest(winerror=codigo):
                pasta = preparo.criar_preparo(self.base / f"c{codigo}")
                with mock.patch.object(preparo, "_renomear", Renomeador(falhas=1, winerror=codigo)), \
                        mock.patch.object(preparo, "_esperar"):
                    preparo.promover(pasta, self.base / f"c{codigo}")
                self.assertTrue((self.base / f"c{codigo}").is_dir())

    def test_falha_permanente_da_e_promocao_com_tentativas_e_atributos(self):
        r = Renomeador(falhas=99)
        with self.assertRaises(preparo.PromocaoRecusada) as ctx:
            self.promover(r)
        exc = ctx.exception
        self.assertEqual(exc.code, "E_PROMOCAO")
        self.assertEqual(r.chamadas, len(preparo.ESPERAS_PROMOCAO) + 1)
        self.assertEqual(self.esperas, list(preparo.ESPERAS_PROMOCAO))
        self.assertEqual(exc.details["tentativas"], 7)
        self.assertEqual(exc.details["espera_total_s"], sum(preparo.ESPERAS_PROMOCAO))
        self.assertEqual(exc.details["winerror"], 5)
        atributos = exc.details["atributos_preparo"]
        self.assertEqual(set(atributos) - {"windows"}, {"modo", "ligacao"}, "só atributos, nada do conteúdo")
        if os.name == "nt":
            self.assertIn("directory", atributos["windows"])
        self.assertIsNone(exc.details["atributos_destino"])
        self.assertNotIn("manifest", str(exc.as_dict()))
        self.assertTrue(self.pasta.is_dir(), "a promoção não apaga o preparo: quem chama limpa e conta")
        self.assertFalse(self.alvo.exists())

    def test_recusa_que_nao_e_passageira_nao_se_repete(self):
        nao_windows = PermissionError(13, "Permissão negada (simulado)")  # Linux: sem winerror
        for erro in (FileExistsError(17, "existe"), recusa(183), nao_windows, OSError(28, "disco cheio")):
            with self.subTest(erro=repr(erro)):
                chamadas = []

                def renomear(origem, destino, erro=erro):
                    chamadas.append(1)
                    raise erro
                with self.assertRaises(OSError):
                    self.promover(renomear)
                self.assertEqual(len(chamadas), 1)
        self.assertEqual(self.esperas, [])

    def test_ligacao_plantada_no_destino_entre_tentativas_nao_recebe_nada(self):
        fora = self.base / "fora"
        fora.mkdir()
        r = Renomeador(falhas=1)
        # Na espera depois da primeira recusa, o destino vira ligação para fora: a segunda tentativa confere e recusa.
        with mock.patch.object(preparo, "_renomear", r), \
                mock.patch.object(preparo, "_esperar", side_effect=lambda s: criar_ligacao_dir(self.alvo, fora)):
            with self.assertRaises(FileExistsError):
                preparo.promover(self.pasta, self.alvo)
        self.assertEqual(r.chamadas, 1, "com ligação no destino, não houve nova renomeação")
        self.assertEqual(list(fora.iterdir()), [], "a promoção gravou através da ligação")
        self.assertTrue(self.pasta.is_dir())

    def test_preparo_trocado_entre_tentativas_recusa(self):
        def trocar(segundos):
            os.rename(self.pasta, self.base / "guardado")
            os.mkdir(self.pasta)  # outra pasta com o mesmo nome
        with mock.patch.object(preparo, "_renomear", Renomeador(falhas=1)), \
                mock.patch.object(preparo, "_esperar", side_effect=trocar):
            with self.assertRaises(ValidationError):
                preparo.promover(self.pasta, self.alvo)
        self.assertFalse(self.alvo.exists())

    def test_destino_vazio_criado_antes_continua_avisado(self):
        self.alvo.mkdir()  # o titular criou a pasta antes (R177-KIT-05)
        r = Renomeador(falhas=1)
        self.assertTrue(self.promover(r), "o 'existia' é o da primeira conferência")
        self.assertEqual(r.chamadas, 2)
        self.assertTrue((self.alvo / "manifest.json").is_file())

    def test_renomear_dentro_do_preparo_tambem_repete(self):
        (self.pasta / "files").mkdir()
        r = Renomeador(falhas=2, winerror=32)
        with mock.patch.object(preparo, "_renomear", r), mock.patch.object(preparo, "_esperar"):
            self.assertEqual(preparo.renomear(self.pasta / "files", self.pasta / "raiz"), 3)
        self.assertTrue((self.pasta / "raiz").is_dir())


class TestPromocaoNoBackupENaRestauracao(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.extra = []
        self.log = self.root / "state" / "retiradas.jsonl"

    def tearDown(self):
        for p in self.extra:
            for resto in [p, *p.parent.glob(f".{p.name}.preparo-*")]:
                shutil.rmtree(resto, ignore_errors=True)
        super().tearDown()

    def pasta(self, nome: str) -> Path:
        p = self.root.parent / f"{self.root.name}-{nome}"
        self.extra.append(p)
        return p

    def test_backup_passa_com_trava_passageira(self):
        snap = self.pasta("snap")
        r = Renomeador(falhas=2)
        with mock.patch.object(preparo, "_renomear", r), mock.patch.object(preparo, "_esperar"):
            res = backup.create_backup(self.root, snap, "passageira-1710")
        self.assertEqual(r.chamadas, 3)
        self.assertTrue(backup.verify_backup(snap, sha256_manifesto=res["sha256_manifesto"])["ok"])

    def test_backup_com_falha_permanente_da_e_promocao_sem_sobra(self):
        snap = self.pasta("snap")
        with mock.patch.object(preparo, "_renomear", Renomeador(falhas=99)), mock.patch.object(preparo, "_esperar"):
            with self.assertRaises(preparo.PromocaoRecusada) as ctx:
                backup.create_backup(self.root, snap, "permanente-1710")
        self.assertEqual(ctx.exception.details["tentativas"], 7)
        self.assertFalse(snap.exists())
        self.assertEqual(list(snap.parent.glob(f".{snap.name}.preparo-*")), [], "o preparo foi limpo e contado")
        self.assertNotIn("sobra_do_preparo", ctx.exception.details)

    def test_restauracao_com_recusa_permanente_nao_diz_que_o_destino_mudou(self):
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "restauracao-1710")
        dest = self.pasta("dest")
        real = preparo.promover

        def promover_com_trava(pasta, alvo):
            with mock.patch.object(preparo, "_renomear", Renomeador(falhas=99)), mock.patch.object(preparo, "_esperar"):
                return real(pasta, alvo)
        with mock.patch.object(preparo, "promover", side_effect=promover_com_trava):
            res = backup.restore(snap, dest, self.log)
        self.assertFalse(res["released"])
        self.assertIn("recusou a renomeação", res["reason"])
        self.assertNotIn("o destino mudou", res["reason"])
        self.assertEqual(res["promocao"]["tentativas"], 7)
        self.assertFalse(dest.exists())
        self.assertEqual(list(dest.parent.glob(f".{dest.name}.preparo-*")), [], "o preparo não liberado ficou")

    def test_restauracao_com_outra_recusa_na_renomeacao_diz_a_causa(self):
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "restauracao-outra")
        dest = self.pasta("dest")
        real = preparo.promover

        def recusar(origem, destino):
            raise PermissionError(13, "Permissão negada (simulado)")  # sem winerror: não é a recusa passageira

        def promover_recusado(pasta, alvo):
            with mock.patch.object(preparo, "_renomear", recusar):
                return real(pasta, alvo)
        with mock.patch.object(preparo, "promover", side_effect=promover_recusado):
            res = backup.restore(snap, dest, self.log)
        self.assertFalse(res["released"])
        self.assertIn("a renomeação final para o destino falhou", res["reason"])
        self.assertNotIn("o destino mudou", res["reason"])
        self.assertFalse(dest.exists())

    def test_restauracao_com_validationerror_na_promocao_cita_preparo_e_destino(self):
        # #8: a nova conferência de `promover` levanta ValidationError (preparo trocado); a mensagem não pode culpar
        # só o destino, senão volta o texto enganoso que o pedido mandou corrigir.
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "restauracao-validation")
        dest = self.pasta("dest")
        erro = ValidationError("pasta de preparo trocada antes da promoção: nada foi promovido")
        with mock.patch.object(preparo, "promover", side_effect=erro):
            res = backup.restore(snap, dest, self.log)
        self.assertFalse(res["released"])
        self.assertIn("o destino ou a pasta de preparo mudou durante a restauração", res["reason"])
        self.assertNotIn("o destino mudou durante", res["reason"])
        self.assertFalse(dest.exists())

    def test_restauracao_passa_com_trava_passageira_nas_renomeacoes(self):
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "restauracao-passageira")
        dest = self.pasta("dest")
        r = Renomeador(falhas=1)
        with mock.patch.object(preparo, "_renomear", r), mock.patch.object(preparo, "_esperar"):
            res = backup.restore(snap, dest, self.log)
        self.assertTrue(res["released"], res)
        self.assertGreaterEqual(r.chamadas, 4, "files/, o banco e a promoção passaram pela nova tentativa")


if __name__ == "__main__":
    unittest.main()
