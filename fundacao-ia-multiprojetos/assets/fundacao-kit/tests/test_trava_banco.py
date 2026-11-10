"""Trava do banco entre o Windows e o Ubuntu (1.7.10; contratos do lote 2, §4): o marcador state/banco.trava do OUTRO
lado recusa abrir o banco — vivo ou velho —, o marcador velho só sai pelo comando explícito do titular (`banco
destravar --confirmar`) e quem abre do mesmo lado continua como antes. Também a saída de erro de arquivo da CLI com a
sobra do preparo (a outra mudança deste pacote em __main__.py). Raiz descartável; o "outro lado" é simulado pelo campo
`lado` do marcador (o oposto do desta máquina)."""

from __future__ import annotations

import io
import json
import os
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest import mock

from helpers import FoundationTestCase

from fundacao.__main__ import main
from fundacao.core import events, trava_banco, wsl_estado
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
        # O wsl.exe nunca roda de verdade nos testes: `_rodar_wsl` é trocado por um falso, que responde à listagem das
        # distribuições registradas e das em execução (por padrão: Ubuntu registrada, nenhuma em execução).
        self.wsl_registradas, self.wsl_ligadas, self.wsl_chamadas, self.wsl_falha = ["Ubuntu"], [], [], None
        self.rodar_wsl_original = wsl_estado._rodar_wsl
        patcher = mock.patch.object(wsl_estado, "_rodar_wsl", side_effect=self._wsl_falso)
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _utf16(nomes) -> bytes:
        return "".join(n + "\r\n" for n in nomes).encode("utf-16-le")

    def _wsl_falso(self, args, prazo_s=wsl_estado.WSL_PRAZO_S):
        self.wsl_chamadas.append(list(args))
        if isinstance(self.wsl_falha, BaseException):
            raise self.wsl_falha
        if self.wsl_falha is not None:
            return self.wsl_falha
        if args == ["-l", "-q"]:
            return 0, self._utf16(self.wsl_registradas)
        if args == ["-l", "--running", "-q"]:
            return 0, self._utf16(self.wsl_ligadas)
        raise AssertionError(f"o kit só pode listar o WSL, e não: {args}")

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


@unittest.skipUnless(MESMO == "windows", "a saída sozinha do marcador do Ubuntu é do lado do Windows")
class TestLiberacaoSozinha(TravaBancoCase):
    """1.7.11 (lição 6 da 1.7.10.2): marcador velho do Ubuntu, deste host, com o WSL desligado, sai sozinho na abertura
    do banco para escrita, com o evento gravado antes. Qualquer dúvida mantém a recusa de antes."""

    VELHO = trava_banco.VIVO_S + 5

    def marcar_elegivel(self, **extra) -> dict:
        return self.marcar("ubuntu", idade_s=self.VELHO, **{"host": trava_banco._host_local(), **extra})

    def eventos(self) -> list:
        return self.con.execute("SELECT * FROM event WHERE kind = ?", (trava_banco.EVENTO_LIBERADO,)).fetchall()

    def test_elegivel_sai_sozinho_no_connect_com_evento_e_aviso(self):
        dados = self.marcar_elegivel()
        erro = io.StringIO()
        with mock.patch.dict(os.environ, {ENV_PRINCIPAL: "operador-lab"}), redirect_stderr(erro):
            connect(self.estado / "state.sqlite").close()
        self.assertFalse(self.marcador.exists())
        (evento,) = self.eventos()
        carga = json.loads(evento["payload_json"])
        self.assertEqual(carga["marcador"], dados)
        self.assertEqual(carga["wsl"], {"medido": True, "em_execucao": [], "registradas": ["Ubuntu"]})
        self.assertEqual((carga["lado"], carga["principal"], carga["pid"]), ("windows", "operador-lab", os.getpid()))
        self.assertGreaterEqual(carga["renovado_ha_s"], self.VELHO)
        self.assertEqual(evento["subject"], trava_banco.MARCADOR)
        aviso = json.loads(erro.getvalue())["aviso"]
        self.assertEqual((aviso["code"], aviso["marcador_removido"]), ("W_BANCO_MARCADOR_VELHO_LIBERADO", dados))
        self.assertEqual(events.verify_chain(self.con), (True, None))
        self.assertIn(["-l", "--running", "-q"], self.wsl_chamadas)

    def test_host_com_outra_caixa_vale_o_mesmo_host(self):
        self.marcar_elegivel(host=trava_banco._host_local().swapcase())
        connect(self.estado / "state.sqlite").close()
        self.assertFalse(self.marcador.exists())

    def test_comando_da_cli_abre_o_banco_depois_de_o_marcador_sair(self):
        self.marcar_elegivel()
        codigo, saida, erro = self.cli("status")
        self.assertEqual(codigo, 0, erro)
        self.assertIsNone(saida["projeto_travado"])
        self.assertIn("W_BANCO_MARCADOR_VELHO_LIBERADO", erro)
        self.assertFalse(self.marcador.exists())
        self.assertEqual(len(self.eventos()), 1)

    def assertNada(self, msg: str, esperado: str | None = None):
        """Nada sai: o connect recusa, o marcador fica e nenhum evento de saída é gravado."""
        with self.assertRaises(trava_banco.BancoTravado, msg=msg) as ctx:
            connect(self.estado / "state.sqlite")
        self.assertTrue(self.marcador.exists(), msg)
        self.assertEqual(self.eventos(), [], msg)
        if esperado:
            self.assertIn(esperado, ctx.exception.details.get("nao_tirado_sozinho", "") + str(ctx.exception))

    def test_wsl_em_execucao_nada_sai(self):
        self.marcar_elegivel()
        self.wsl_ligadas = ["Ubuntu"]
        self.assertNada("WSL ligado", "em execução")
        self.wsl_ligadas = ["docker-desktop"]  # qualquer distribuição, não só o Ubuntu
        self.assertNada("outra distribuição ligada", "docker-desktop")

    def test_marcador_recente_nada_sai(self):
        self.marcar("ubuntu", idade_s=10, host=trava_banco._host_local())
        self.assertNada("marcador recente", "em uso")
        self.assertEqual(self.wsl_chamadas, [], "marcador recente nem pergunta ao WSL")

    def test_outro_host_nada_sai_e_nem_pergunta_ao_wsl(self):
        self.marcar("ubuntu", idade_s=self.VELHO)  # host "maquina-ficticia"
        self.assertNada("outro host", "outro host")
        self.assertEqual(self.wsl_chamadas, [])

    def test_wsl_que_falha_nada_sai(self):
        self.marcar_elegivel()
        falhas = {"wsl.exe ausente": FileNotFoundError("sem wsl"),
                  "tempo esgotado": subprocess.TimeoutExpired("wsl.exe", 8),
                  "erro do sistema": OSError(5, "negado"),
                  "código de erro": (4294967295, b""),
                  "código de erro com nomes": (1, self._utf16(["Ubuntu"])),
                  "saída ímpar": (0, b"abc"),
                  "sem nenhuma registrada": (0, b"")}
        for nome, falha in falhas.items():
            with self.subTest(falha=nome):
                self.wsl_falha = falha
                self.assertNada(nome, "não deu para medir o WSL")

    def test_sem_distribuicao_registrada_e_saida_vazia_e_duvida(self):
        self.marcar_elegivel()
        self.wsl_registradas = []  # `-l -q` vazia: pode ser falha disfarçada
        self.assertNada("sem registradas", "nenhuma distribuição registrada")

    def test_marcador_do_windows_ilegivel_ou_vivo_nada_sai(self):
        casos = {"lado windows": lambda: self.marcar("windows", idade_s=self.VELHO, host=trava_banco._host_local()),
                 "ilegível": lambda: self.marcador.write_bytes(b"lixo"),
                 "vivo": lambda: self.marcar("ubuntu", host=trava_banco._host_local())}
        for nome, criar in casos.items():
            with self.subTest(caso=nome):
                criar()
                if nome == "lado windows":
                    connect(self.estado / "state.sqlite").close()  # do mesmo lado: abre como sempre, sem tirar
                    self.assertTrue(self.marcador.exists())
                else:
                    self.assertNada(nome)
                self.marcador.unlink()

    def test_marcador_renovado_durante_a_medida_nada_sai(self):
        self.marcar_elegivel()
        original = self._wsl_falso

        def renova(args, prazo_s=0):
            self.marcar("ubuntu", host=trava_banco._host_local())  # o porteiro acorda no meio da medida
            return original(args)

        with mock.patch.object(wsl_estado, "_rodar_wsl", side_effect=renova):
            self.assertNada("renovado durante a medida", "mudou")

    def test_falha_ao_gravar_o_evento_deixa_o_marcador(self):
        self.marcar_elegivel()
        with mock.patch.object(events, "emit", side_effect=OSError("disco cheio (simulado)")):
            with self.assertRaises(OSError):
                connect(self.estado / "state.sqlite")
        self.assertTrue(self.marcador.exists(), "sem evento, o marcador não sai")

    def test_so_a_abertura_para_escrita_tira(self):
        self.marcar_elegivel()
        with self.assertRaises(trava_banco.BancoTravado):
            conectar_somente_leitura(self.estado / "state.sqlite")
        with self.assertRaises(trava_banco.BancoTravado):
            trava_banco.conferir(self.estado)  # a conferência simples (backup, atualização) também só recusa
        self.assertTrue(self.marcador.exists())
        self.assertEqual(self.wsl_chamadas, [])

    def test_destravar_do_titular_continua_igual(self):
        self.marcar_elegivel()
        self.wsl_ligadas = ["Ubuntu"]  # o comando explícito do titular não consulta o WSL
        self.assertTrue(trava_banco.destravar(self.estado, confirmar=True)["removido"])
        self.assertEqual(self.wsl_chamadas, [])


class TestMedidaDoWsl(TravaBancoCase):
    @unittest.skipUnless(MESMO == "windows", "o WSL só se mede pelo Windows")
    def test_medida_em_utf16_com_ou_sem_bom(self):
        self.wsl_registradas, self.wsl_ligadas = ["Ubuntu", "docker-desktop"], ["Ubuntu"]
        medida = trava_banco.wsl_em_execucao()
        self.assertEqual(medida, {"medido": True, "em_execucao": ["Ubuntu"], "registradas": ["Ubuntu", "docker-desktop"]})
        with mock.patch.object(wsl_estado, "_rodar_wsl", return_value=(0, "\ufeffUbuntu\r\n".encode("utf-16-le"))):
            self.assertEqual(trava_banco.wsl_em_execucao()["em_execucao"], ["Ubuntu"])

    def test_fora_do_windows_nao_mede(self):
        with mock.patch.object(trava_banco, "lado_desta_maquina", return_value="ubuntu"):
            self.assertFalse(trava_banco.wsl_em_execucao()["medido"])
        self.assertEqual(self.wsl_chamadas, [])

    @unittest.skipUnless(os.name == "nt", "caminho do sistema do Windows")
    def test_wsl_exe_so_pelo_caminho_absoluto_do_sistema(self):
        sistema = self.root / "Windows"
        (sistema / "System32").mkdir(parents=True)
        with mock.patch.dict(os.environ, {"SystemRoot": str(sistema)}):
            self.assertIsNone(wsl_estado._wsl_do_sistema(), "sem o arquivo, nada; nunca o nome nu")
            (sistema / "System32" / "wsl.exe").write_bytes(b"")
            self.assertEqual(wsl_estado._wsl_do_sistema(), str(sistema / "System32" / "wsl.exe"))

    @unittest.skipUnless(os.name == "nt", "wsl.exe do Windows")
    def test_roda_sem_a_variavel_de_utf8_e_com_prazo(self):
        sistema = self.root / "Windows"
        (sistema / "System32").mkdir(parents=True)
        (sistema / "System32" / "wsl.exe").write_bytes(b"")
        resposta = subprocess.CompletedProcess([], 0, stdout=b"x", stderr=b"")
        with mock.patch.dict(os.environ, {"SystemRoot": str(sistema), "WSL_UTF8": "1"}),                 mock.patch("subprocess.run", return_value=resposta) as rodar:
            self.assertEqual(self.rodar_wsl_original(["-l", "-q"]), (0, b"x"))
        comando = rodar.call_args.args[0]
        self.assertEqual(comando, [str(sistema / "System32" / "wsl.exe"), "-l", "-q"])
        self.assertEqual(rodar.call_args.kwargs["timeout"], wsl_estado.WSL_PRAZO_S)
        self.assertNotIn("WSL_UTF8", rodar.call_args.kwargs["env"])
        self.assertFalse(rodar.call_args.kwargs.get("shell"))


class TestSituacaoComWsl(TravaBancoCase):
    @unittest.skipUnless(MESMO == "windows", "o WSL só se mede pelo Windows")
    def test_situacao_diz_se_o_wsl_esta_ligado_e_o_que_fazer(self):
        self.marcar("ubuntu", idade_s=trava_banco.VIVO_S + 5, host=trava_banco._host_local())
        codigo, r, erro = self.cli("banco", "situacao")
        self.assertEqual((codigo, r["wsl"]["medido"], r["wsl"]["em_execucao"]), (0, True, []), erro)
        self.assertIn("sai sozinho", r["o_que_fazer"])
        self.assertIn("banco destravar --confirmar", r["o_que_fazer"])
        self.assertTrue(self.marcador.exists(), "a situação nunca tira o marcador")
        self.wsl_ligadas = ["Ubuntu"]
        r = self.cli("banco", "situacao")[1]
        self.assertEqual(r["wsl"]["em_execucao"], ["Ubuntu"])
        self.assertIn("está ligado", r["o_que_fazer"])
        self.assertNotIn("sai sozinho na próxima", r["o_que_fazer"].split("Com ele fechado")[0])
        self.wsl_falha = OSError(2, "sem wsl")
        r = self.cli("banco", "situacao")[1]
        self.assertEqual(r["wsl"]["medido"], False)
        self.assertIn("Não deu para ver se o Ubuntu está ligado", r["o_que_fazer"])
        self.assertTrue(self.marcador.exists())

    @unittest.skipUnless(MESMO == "windows", "o WSL só se mede pelo Windows")
    def test_situacao_de_outro_host_nao_promete_saida_sozinha(self):
        self.marcar("ubuntu", idade_s=trava_banco.VIVO_S + 5)  # host fictício
        r = self.cli("banco", "situacao")[1]
        self.assertIn("não sai sozinho", r["o_que_fazer"])
        self.assertIn("outro host", r["o_que_fazer"])

    def test_situacao_sem_marcador_nao_traz_o_que_fazer(self):
        r = self.cli("banco", "situacao")[1]
        self.assertNotIn("o_que_fazer", r)


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
