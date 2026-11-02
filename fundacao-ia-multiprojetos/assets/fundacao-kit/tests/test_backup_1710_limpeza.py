"""1.7.10 — limpeza contada das pastas de preparo (desenho 1.7.10, §5.8; MELHORIAS-1.7.10, §0 item 15).

Em 31/10/2026 o `backup criar` falhou na renomeação final e o `shutil.rmtree(..., ignore_errors=True)` deixou 551 pastas
vazias com a marca somente leitura no disco das cópias, sem avisar. Agora a limpeza apaga sem seguir ligação, tira a
marca somente leitura no Windows, tenta de novo e conta o que sobrou; a contagem vai com o erro, na resposta de "não
liberar" e no aviso W_SOBRA_DO_PREPARO da CLI. Falhas de remoção são simuladas por injeção (qualquer sistema); a marca
somente leitura e o arquivo aberto sem compartilhamento são do Windows. Conteúdos fictícios.
"""

from __future__ import annotations

import gc
import io
import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio_auditoria import criar_ligacao_dir
from helpers import FoundationTestCase

from fundacao import cli_backup
from fundacao.core import backup, limpeza, preparo, projects
from fundacao.core.auth import ENV_PRINCIPAL
from fundacao.core.contracts import FundacaoError, ValidationError

CANARIO = "CANARIO-FORA-DO-PREPARO-FICTICIO"


def falhar_em(nome: str):
    """Remoção que recusa sempre o arquivo `nome` (como um antivírus que não solta) e apaga os demais."""
    real = os.unlink

    def apagar(caminho):
        if Path(caminho).name == nome:
            raise PermissionError(13, "Acesso negado (simulado)")
        return real(caminho)
    return apagar


def sem_espera():
    return mock.patch.object(limpeza, "_esperar", lambda segundos: None)


def apagar_tudo(pasta: Path) -> None:
    """Limpeza do próprio teste (sem o código testado): tira a marca somente leitura e apaga, sem seguir ligação."""
    if not os.path.lexists(pasta):
        return
    for raiz, pastas, arquivos in os.walk(pasta):
        for nome in pastas + arquivos:
            try:
                os.chmod(os.path.join(raiz, nome), stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
            except OSError:
                pass
    shutil.rmtree(pasta, ignore_errors=True)


class TestLimpar(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="fundacao-limpeza-"))
        self.addCleanup(apagar_tudo, self.base)

    def arvore(self, nome: str = ".snap.preparo-0001") -> Path:
        pasta = self.base / nome
        for rel, texto in {"files/projects/p1/a.md": "a", "files/projects/p1/sub/b.md": "bb",
                           "state/state.sqlite": "banco fictício", "manifest.json": "{}"}.items():
            alvo = pasta / rel
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text(texto, encoding="utf-8")
        return pasta

    def test_apaga_tudo_e_conta_zero(self):
        pasta = self.arvore()
        res = limpeza.limpar(pasta, self.base)
        self.assertTrue(res["limpa"], res)
        self.assertFalse(pasta.exists())
        self.assertEqual({k: res[k] for k in ("arquivos", "pastas", "ligacoes", "bytes")},
                         {"arquivos": 0, "pastas": 0, "ligacoes": 0, "bytes": 0})
        self.assertEqual(res["erros"], [])
        self.assertTrue(limpeza.limpar(pasta, self.base)["limpa"])  # pasta que já não existe: limpa

    def test_sobra_contada_com_tentativas_e_esperas_curtas(self):
        pasta = self.arvore()
        esperas = []
        with mock.patch.object(limpeza, "_apagar_arquivo", side_effect=falhar_em("b.md")), \
                mock.patch.object(limpeza, "_esperar", side_effect=esperas.append):
            res = limpeza.limpar(pasta, self.base)
        self.assertFalse(res["limpa"])
        self.assertEqual((res["arquivos"], res["bytes"], res["ligacoes"]), (1, 2, 0))
        self.assertEqual(res["pastas"], 5)  # a do preparo, files, projects, p1 e sub: o caminho até o que ficou
        self.assertEqual(esperas, list(limpeza.ESPERAS), "a limpeza tenta de novo, com esperas curtas")
        self.assertEqual(res["erros"][0]["caminho"], "files/projects/p1/sub/b.md")
        self.assertEqual(res["erros"][0]["erro"], "PermissionError")
        self.assertEqual(res["pasta"], str(pasta))
        self.assertTrue((pasta / "files" / "projects" / "p1" / "sub" / "b.md").exists())
        self.assertFalse((pasta / "manifest.json").exists(), "o resto saiu")

    def test_nao_segue_ligacao(self):
        fora = self.base / "fora"
        fora.mkdir()
        (fora / "canario.txt").write_text(CANARIO, encoding="utf-8")
        pasta = self.arvore()
        criar_ligacao_dir(pasta / "files" / "ligada", fora)
        res = limpeza.limpar(pasta, self.base)
        self.assertTrue(res["limpa"], res)
        self.assertEqual((fora / "canario.txt").read_text(encoding="utf-8"), CANARIO, "apagou através da ligação")

    def test_ligacao_no_lugar_do_preparo_sai_como_ligacao(self):
        fora = self.base / "fora"
        fora.mkdir()
        (fora / "canario.txt").write_text(CANARIO, encoding="utf-8")
        pasta = self.base / ".snap.preparo-0002"
        criar_ligacao_dir(pasta, fora)
        res = limpeza.limpar(pasta, self.base)
        self.assertTrue(res["limpa"], res)
        self.assertFalse(os.path.lexists(pasta))
        self.assertTrue((fora / "canario.txt").exists())

    def test_fora_da_pasta_permitida_nao_apaga(self):
        pasta = self.arvore()
        outra = self.base / "outra"
        outra.mkdir()
        for dentro_de in (outra, pasta):
            with self.subTest(dentro_de=dentro_de):
                res = limpeza.limpar(pasta, dentro_de)
                self.assertFalse(res["limpa"])
                self.assertTrue((pasta / "manifest.json").exists(), "apagou fora da pasta do preparo")
                self.assertGreater(res["arquivos"], 0)
                self.assertIn("nada apagado", str(res["erros"]))

    def test_ligacao_no_meio_do_caminho_nao_apaga(self):
        real = self.base / "real"
        real.mkdir()
        (real / "dentro").mkdir()
        (real / "dentro" / "canario.txt").write_text(CANARIO, encoding="utf-8")
        criar_ligacao_dir(self.base / "via", real)
        res = limpeza.limpar(self.base / "via" / "dentro", self.base)
        self.assertFalse(res["limpa"])
        self.assertTrue((real / "dentro" / "canario.txt").exists())

    @unittest.skipUnless(os.name == "nt", "marca somente leitura que impede apagar: comportamento do Windows")
    def test_somente_leitura_sai_no_windows(self):
        pasta = self.arvore()
        for p in sorted(pasta.rglob("*"), reverse=True):
            os.chmod(p, stat.S_IREAD)  # arquivos e pastas com a marca, como as 551 de 31/10/2026
        os.chmod(pasta, stat.S_IREAD)
        with sem_espera():
            res = limpeza.limpar(pasta, self.base)
        self.assertTrue(res["limpa"], res)
        self.assertFalse(pasta.exists())

    @unittest.skipUnless(os.name == "nt", "arquivo aberto sem compartilhamento de exclusão: comportamento do Windows")
    def test_arquivo_aberto_fica_contado_no_windows(self):
        pasta = self.arvore()
        preso = pasta / "files" / "projects" / "p1" / "a.md"
        with open(preso, "rb"), sem_espera():
            res = limpeza.limpar(pasta, self.base)
        self.assertFalse(res["limpa"])
        self.assertEqual((res["arquivos"], res["bytes"]), (1, 1))
        self.assertEqual(res["erros"][0]["codigo"], 32)  # violação de compartilhamento
        self.assertTrue(limpeza.limpar(pasta, self.base)["limpa"], "solto, sai na limpeza seguinte")

    @unittest.skipUnless(os.name == "nt", "vínculo físico + marca somente leitura: comportamento do Windows")
    def test_vinculo_fisico_somente_leitura_preserva_o_arquivo_de_fora(self):
        # #7: o chmod S_IWRITE num vínculo físico (st_nlink>1) tiraria a marca somente leitura também do arquivo de fora.
        fora = self.base / "fora"
        fora.mkdir()
        original = fora / "original.bin"
        original.write_bytes(b"conteudo ficticio")
        pasta = self.base / ".snap.preparo-nlink"
        (pasta / "files").mkdir(parents=True)
        os.link(original, pasta / "files" / "vinculo.bin")  # vínculo físico: nlink = 2, mesma marca do arquivo de fora
        os.chmod(original, stat.S_IREAD)
        with sem_espera():
            res = limpeza.limpar(pasta, self.base)
        self.assertFalse(res["limpa"], "o vínculo físico somente leitura fica contado, não apagado")
        self.assertTrue((pasta / "files" / "vinculo.bin").exists(), "o vínculo físico não foi apagado")
        self.assertTrue(os.lstat(original).st_file_attributes & stat.FILE_ATTRIBUTE_READONLY,
                        "a marca somente leitura do arquivo de fora foi preservada (o chmod não tocou nele)")


class TestContadaEAnotacao(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="fundacao-limpeza-"))
        self.addCleanup(apagar_tudo, self.base)
        self.pasta = self.base / ".x.preparo-0003"
        (self.pasta / "sub").mkdir(parents=True)
        (self.pasta / "sub" / "preso.bin").write_bytes(b"1234")

    def falhando(self):
        return mock.patch.object(limpeza, "_apagar_arquivo", side_effect=falhar_em("preso.bin"))

    def test_erro_do_contrato_leva_a_contagem_nos_detalhes(self):
        with self.falhando(), sem_espera(), self.assertRaises(ValidationError) as ctx:
            with limpeza.contada(self.pasta, self.base):
                raise ValidationError("falha simulada")
        sobra = ctx.exception.details["sobra_do_preparo"]
        self.assertEqual((sobra["limpa"], sobra["arquivos"], sobra["bytes"]), (False, 1, 4))
        self.assertIn("sobra_do_preparo", ctx.exception.as_dict()["error"])

    def test_outro_erro_leva_a_contagem_no_atributo(self):
        with self.falhando(), sem_espera(), self.assertRaises(OSError) as ctx:
            with limpeza.contada(self.pasta, self.base):
                raise OSError(28, "disco cheio (simulado)")
        self.assertEqual(ctx.exception.sobra_do_preparo["arquivos"], 1)

    def test_limpeza_completa_nao_acrescenta_nada(self):
        with self.assertRaises(ValidationError) as ctx:
            with limpeza.contada(self.pasta, self.base):
                raise ValidationError("falha simulada")
        self.assertNotIn("sobra_do_preparo", ctx.exception.details)
        self.assertFalse(self.pasta.exists())

    def test_saida_normal_anota_as_respostas_dadas(self):
        respostas = [{"released": False}]
        with self.falhando(), sem_espera():
            with limpeza.contada(self.pasta, self.base, respostas) as sobra:
                pass
        self.assertFalse(sobra["limpa"])
        self.assertEqual(respostas[0]["sobra_do_preparo"]["arquivos"], 1)

    def test_na_falha_anota_o_erro_em_tratamento(self):
        try:
            raise FundacaoError("falha simulada")
        except FundacaoError as exc:
            with self.falhando(), sem_espera():
                sobra = limpeza.na_falha(self.pasta, self.base)
            self.assertIs(exc.details["sobra_do_preparo"]["limpa"], False)
        self.assertEqual(sobra["arquivos"], 1)

    def test_cli_avisa_a_sobra_no_stderr(self):
        erro = OSError(28, "disco cheio (simulado)")
        erro.sobra_do_preparo = {"pasta": str(self.pasta), "limpa": False, "arquivos": 2, "pastas": 1, "ligacoes": 0,
                                 "bytes": 10, "erros": []}

        def falha():
            raise erro
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err, self.assertRaises(OSError):
            cli_backup._avisando_sobra(falha)
        self.assertIn("W_SOBRA_DO_PREPARO", err.getvalue())
        self.assertIn('"arquivos": 2', err.getvalue())
        self.assertIn(str(self.pasta).replace("\\", "\\\\"), err.getvalue())


class TestLimpezaNoBackupNaRestauracaoENoProjeto(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.extra = []
        self.log = self.root / "state" / "retiradas.jsonl"

    def tearDown(self):
        for p in self.extra:
            for resto in [p, *p.parent.glob(f".{p.name}.preparo-*")]:
                apagar_tudo(resto)
        super().tearDown()

    def pasta(self, nome: str) -> Path:
        p = self.root.parent / f"{self.root.name}-{nome}"
        self.extra.append(p)
        return p

    def preparos(self, destino: Path) -> list[Path]:
        return list(destino.parent.glob(f".{destino.name}.preparo-*"))

    def test_falha_do_backup_leva_a_sobra_do_preparo(self):
        snap = self.pasta("snap")
        recusa = preparo.PromocaoRecusada("recusa simulada", tentativas=7)
        with mock.patch.object(preparo, "promover", side_effect=recusa), \
                mock.patch.object(limpeza, "_apagar_arquivo", side_effect=falhar_em("manifest.json")), sem_espera():
            with self.assertRaises(preparo.PromocaoRecusada) as ctx:
                backup.create_backup(self.root, snap, "sobra-1710")
        sobra = ctx.exception.details["sobra_do_preparo"]
        self.assertEqual((sobra["limpa"], sobra["arquivos"], sobra["pastas"]), (False, 1, 1))
        self.assertEqual(len(self.preparos(snap)), 1, "a sobra é a contada, e só ela")
        self.assertFalse(snap.exists())

    def test_falha_do_backup_sem_sobra_nao_deixa_preparo(self):
        snap = self.pasta("snap")
        with mock.patch.object(preparo, "promover", side_effect=OSError(28, "disco cheio (simulado)")):
            with self.assertRaises(OSError) as ctx:
                backup.create_backup(self.root, snap, "sobra-1710-b")
        self.assertFalse(hasattr(ctx.exception, "sobra_do_preparo"))
        self.assertEqual(self.preparos(snap), [])

    def test_restauracao_nao_liberada_informa_a_sobra(self):
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "sobra-restauracao")
        dest = self.pasta("dest")
        with mock.patch.object(preparo, "reconferir", return_value=["projects/juridico-lab/INSTRUCOES.md"]), \
                mock.patch.object(limpeza, "_apagar_arquivo", side_effect=falhar_em("manifest.json")), sem_espera():
            res = backup.restore(snap, dest, self.log)
        self.assertFalse(res["released"])
        self.assertIn("mudou antes da promoção", res["reason"])
        self.assertEqual(res["sobra_do_preparo"]["arquivos"], 1)
        self.assertFalse(dest.exists())

    def test_restauracao_liberada_informa_a_sobra(self):
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "sobra-restauracao-2")
        dest = self.pasta("dest")
        with mock.patch.object(limpeza, "_apagar_arquivo", side_effect=falhar_em("manifest.json")), sem_espera():
            res = backup.restore(snap, dest, self.log)
        self.assertTrue(res["released"], res)
        self.assertEqual(res["sobra_do_preparo"]["arquivos"], 1)
        limpo = backup.restore(snap, self.pasta("dest-2"), self.log)
        self.assertTrue(limpo["released"], limpo)
        self.assertNotIn("sobra_do_preparo", limpo)
        self.assertEqual(self.preparos(self.root.parent / f"{self.root.name}-dest-2"), [])

    def test_resposta_recusada_antes_do_preparo_nao_tem_sobra(self):
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "sem-registro")
        res = backup.restore(snap, self.pasta("dest"), None)
        self.assertFalse(res["released"])
        self.assertIn("registro de retiradas indisponível", res["reason"])
        self.assertNotIn("sobra_do_preparo", res)

    def test_copia_privada_do_banco_na_autorizacao_conta_a_sobra(self):
        snap = self.pasta("snap")
        ancora = backup.create_backup(self.root, snap, "autorizacao-1710")["sha256_manifesto"]
        self.con.close()
        gc.collect()
        for nome in ("state.sqlite", "state.sqlite-wal", "state.sqlite-shm"):  # sem fundação viva: decide a cópia
            (self.root / "state" / nome).unlink(missing_ok=True)
        with mock.patch.dict(os.environ, {ENV_PRINCIPAL: "operador-lab"}), \
                mock.patch.object(limpeza, "_apagar_arquivo", side_effect=falhar_em("state.sqlite")), sem_espera():
            res = backup.autorizar(self.root, snap, sha256_manifesto=ancora)
        self.assertEqual(res["politica"], "cópia autenticada pela âncora")
        sobra = res["sobra_do_preparo"]
        self.assertEqual(sobra["arquivos"], 1)
        self.assertTrue(Path(sobra["pasta"]).name.startswith("fundacao-autorizacao-"))
        apagar_tudo(Path(sobra["pasta"]))
        with mock.patch.dict(os.environ, {ENV_PRINCIPAL: "operador-lab"}):
            self.assertNotIn("sobra_do_preparo", backup.autorizar(self.root, snap, sha256_manifesto=ancora))

    def test_criacao_de_projeto_que_falha_conta_a_sobra(self):
        def recusar(config):
            if config.get("project_id") == "novo-lab":
                raise ValidationError("configuração recusada (simulado)")
            return config
        pdir = self.root / "projects"
        with mock.patch.object(projects, "validate_config", side_effect=recusar), \
                mock.patch.object(limpeza, "_apagar_arquivo", side_effect=falhar_em("INSTRUCOES.md")), sem_espera():
            with self.assertRaises(ValidationError) as ctx:
                projects.create_project(self.root, self.con, self.admin, "novo-lab", "Novo", "Finalidade fictícia")
        sobra = ctx.exception.details["sobra_do_preparo"]
        self.assertEqual(sobra["arquivos"], 1)
        restos = list(pdir.glob(".tmp-novo-lab-*"))
        self.assertEqual(len(restos), 1)
        apagar_tudo(restos[0])
        with mock.patch.object(projects, "validate_config", side_effect=recusar):
            with self.assertRaises(ValidationError) as ctx:
                projects.create_project(self.root, self.con, self.admin, "novo-lab", "Novo", "Finalidade fictícia")
        self.assertNotIn("sobra_do_preparo", ctx.exception.details)
        self.assertEqual(list(pdir.glob(".tmp-novo-lab-*")), [])


if __name__ == "__main__":
    unittest.main()
