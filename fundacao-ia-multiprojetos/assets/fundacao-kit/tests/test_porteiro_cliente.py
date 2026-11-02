"""Cliente do porteiro (1.7.10; contratos do lote 2, §4): com FUNDACAO_PORTEIRO e sem FUNDACAO_PORTEIRO_SERVIDOR,
`python -m fundacao ...` vira pedido à fila (pedidos/.<id>.tmp renomeado para pedidos/<id>.json) e espera
respostas/<id>.json, transparente para a sessão (mesmo stdout, stderr e código), sem abrir o banco. Da revisão do lote
2: sem FUNDACAO_RAIZ nada roda na sessão, argv fora do UTF-8 vira erro da CLI e a desistência diz se o pedido pode ter
rodado. Da correção do lote 2: a interrupção (Ctrl+C, ou SIGTERM no desvio) tira da fila o pedido não atendido e diz
se ele rodou; a resposta que chega na hora da desistência vale. A fila é simulada numa pasta temporária por uma thread
que faz o papel do porteiro; relógio e espera injetáveis, sem sono fixo."""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import signal
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401 — põe o kit no caminho de importação

from fundacao import porteiro_cliente as cliente
from fundacao.__main__ import main

AMBIENTE = (cliente.ENV_FILA, cliente.ENV_SERVIDOR, cliente.ENV_PRAZO, cliente.ENV_RAIZ, "FUNDACAO_" + "PRINCIPAL",
            "FUNDACAO_PROJETO_TRAVADO")


def _iso(delta_s: float = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=delta_s)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class PorteiroDeEnsaio(threading.Thread):
    """Faz o papel do porteiro: lê cada pedido, guarda-o e grava a resposta (troca atômica, como o porteiro)."""

    def __init__(self, fila: Path, responder=None):
        super().__init__(daemon=True)
        self.fila, self.recebidos, self.parar = fila, [], threading.Event()
        self.responder = responder or (lambda p: {"codigo": 0, "stdout": json.dumps({"ok": True}) + "\n",
                                                  "stderr": "aviso de ensaio\n"})

    def vida(self, idade_s: float = 0) -> None:
        (self.fila / "respostas" / cliente.VIDA).write_text(json.dumps({"pid": 1, "renovada_em": _iso(idade_s)}),
                                                            encoding="utf-8")

    def run(self):
        while not self.parar.is_set():
            for arq in sorted((self.fila / "pedidos").glob("*.json")):
                pedido = json.loads(arq.read_text(encoding="utf-8"))
                arq.unlink()
                self.recebidos.append(pedido)
                resposta = self.responder(pedido)
                if resposta is None:
                    continue
                corpo = {"versao": 1, "id": pedido["id"], "truncado": False, "duracao_s": 0.01, **resposta}
                temp = self.fila / "respostas" / f".{pedido['id']}.tmp"
                temp.write_text(json.dumps(corpo, ensure_ascii=False), encoding="utf-8")
                os.replace(temp, self.fila / "respostas" / f"{pedido['id']}.json")
            self.parar.wait(0.01)


class ClienteCase(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="porteiro-cliente-1710-"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.raiz = self.base / "raiz"
        self.fila = self.raiz / "projects" / "proj-ficticio" / ".porteiro"
        (self.fila / "pedidos").mkdir(parents=True)
        (self.fila / "respostas").mkdir()
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        for nome in AMBIENTE:
            os.environ.pop(nome, None)

    def porteiro(self, responder=None) -> PorteiroDeEnsaio:
        p = PorteiroDeEnsaio(self.fila, responder)
        p.vida()
        p.start()
        self.addCleanup(p.join, 5)
        self.addCleanup(p.parar.set)
        return p

    def na_sessao(self) -> None:
        os.environ[cliente.ENV_FILA] = str(self.fila)
        os.environ[cliente.ENV_RAIZ] = str(self.raiz)


class TestDesvio(ClienteCase):
    def test_ativo_so_com_a_fila_e_fora_do_porteiro(self):
        self.assertFalse(cliente.ativo({}))
        self.assertTrue(cliente.ativo({cliente.ENV_FILA: "/tmp/fila"}))
        self.assertFalse(cliente.ativo({cliente.ENV_FILA: "/tmp/fila", cliente.ENV_SERVIDOR: "1"}))
        self.assertFalse(cliente.ativo({cliente.ENV_FILA: "  "}))

    def test_raiz_real_sai_do_pedido_e_outra_raiz_roda_aqui(self):
        amb = {cliente.ENV_RAIZ: str(self.raiz)}
        atual = str(self.raiz / "projects" / "proj-ficticio")
        self.assertEqual(cliente.preparar_argv(["status"], amb, atual), ["status"])
        self.assertEqual(cliente.preparar_argv(["--raiz", str(self.raiz), "status"], amb, atual), ["status"])
        self.assertEqual(cliente.preparar_argv([f"--raiz={self.raiz}", "status"], amb, atual), ["status"])
        self.assertEqual(cliente.preparar_argv(["--raiz", "../..", "status"], amb, atual), ["status"])  # mesma pasta
        ensaio = self.base / "ensaio"
        ensaio.mkdir()
        self.assertIsNone(cliente.preparar_argv(["--raiz", str(ensaio), "status"], amb, atual))
        # sem a raiz real (lançador incompleto): o argv inteiro vai ao porteiro, que recusa o --raiz (revisão do lote 2)
        self.assertEqual(cliente.preparar_argv(["--raiz", str(self.raiz), "status"], {}, atual),
                         ["--raiz", str(self.raiz), "status"])
        # --raiz depois do subcomando não é a opção global: vai como está (o porteiro recusa)
        self.assertEqual(cliente.preparar_argv(["status", "--raiz", str(ensaio)], amb, atual),
                         ["status", "--raiz", str(ensaio)])

    def test_caminhos_relativos_vao_absolutos_pela_pasta_atual(self):
        atual = str(self.raiz / "projects" / "proj-ficticio")
        argv = cliente.preparar_argv(["decisao", "registrar", "--arquivo", "decisoes/d.json"], {}, atual)
        self.assertEqual(argv, ["decisao", "registrar",
                                "--arquivo=" + os.path.abspath(os.path.join(atual, "decisoes", "d.json"))])
        argv = cliente.preparar_argv(["tarefa", "concluir", "--decisao=decisoes/d.json", "--objetivo", "outputs/x"],
                                     {}, atual)
        self.assertEqual(argv[2], "--decisao=" + os.path.abspath(os.path.join(atual, "decisoes", "d.json")))
        self.assertEqual(argv[3:], ["--objetivo", "outputs/x"], "texto livre não é caminho")
        self.assertEqual(cliente.preparar_argv(["decisao", "verificar", "--arquivo"], {}, atual),
                         ["decisao", "verificar", "--arquivo"])

    def test_pedido_na_forma_do_contrato_e_resposta_transparente(self):
        porteiro = self.porteiro(lambda p: {"codigo": 3, "stdout": '{"valida": false}\n', "stderr": "aviso ê\n"})
        resposta = cliente.pedir(self.fila, ["decisao", "verificar", "--arquivo=/x"], prazo=10)
        self.assertEqual((resposta["codigo"], resposta["stdout"], resposta["stderr"]), (3, '{"valida": false}\n',
                                                                                         "aviso ê\n"))
        [pedido] = porteiro.recebidos
        self.assertEqual(set(pedido), {"versao", "id", "op", "argv", "criado_em"})
        self.assertEqual((pedido["versao"], pedido["op"], pedido["argv"]),
                         (1, "fundacao", ["decisao", "verificar", "--arquivo=/x"]))
        self.assertRegex(pedido["id"], r"^[0-9a-f]{32}$")
        self.assertIsNotNone(datetime.fromisoformat(pedido["criado_em"].replace("Z", "+00:00")))
        self.assertEqual([p.name for p in (self.fila / "pedidos").iterdir()], [], "o temporário foi renomeado")

    def test_main_desvia_sem_abrir_o_banco_e_devolve_o_mesmo_codigo(self):
        self.na_sessao()
        porteiro = self.porteiro(lambda p: {"codigo": 2, "stdout": "", "stderr": '{"error": {"code": "E_X"}}\n'})
        saida, erro = io.StringIO(), io.StringIO()
        with redirect_stdout(saida), redirect_stderr(erro), \
                mock.patch("fundacao.__main__._con", side_effect=AssertionError("o cliente abriu o banco")):
            codigo = main(["--raiz", str(self.raiz), "tarefa", "ver", "--projeto", "proj-ficticio", "--id", "t"])
        self.assertEqual((codigo, saida.getvalue(), erro.getvalue()), (2, "", '{"error": {"code": "E_X"}}\n'))
        self.assertEqual(porteiro.recebidos[0]["argv"], ["tarefa", "ver", "--projeto", "proj-ficticio", "--id", "t"])
        self.assertFalse((self.raiz / "state").exists(), "nada do banco foi criado na sessão")

    def test_dentro_do_porteiro_e_com_outra_raiz_nao_desvia(self):
        self.na_sessao()
        os.environ[cliente.ENV_SERVIDOR] = "1"
        self.assertIsNone(cliente.desviar(["status"]))
        del os.environ[cliente.ENV_SERVIDOR]
        ensaio = self.base / "ensaio"
        ensaio.mkdir()
        self.assertIsNone(cliente.desviar(["--raiz", str(ensaio), "status"]))

    def test_sem_a_raiz_do_lancador_nada_roda_aqui(self):
        """Revisão do lote 2: com a fila e sem FUNDACAO_RAIZ, nem a raiz real nem outra rodam na sessão (abririam o
        banco direto); o pedido vai ao porteiro, que recusa o --raiz pelo mapa."""
        os.environ[cliente.ENV_FILA] = str(self.fila)
        porteiro = self.porteiro(lambda p: {"codigo": 2, "stdout": "", "stderr": '{"error": {"code": "E_PORTEIRO"}}\n'})
        saida, erro = io.StringIO(), io.StringIO()
        with redirect_stdout(saida), redirect_stderr(erro), \
                mock.patch("fundacao.__main__._con", side_effect=AssertionError("a sessão abriu o banco")):
            codigo = main(["--raiz", str(self.raiz), "status"])
        self.assertEqual((codigo, saida.getvalue()), (2, ""))
        self.assertEqual(porteiro.recebidos[0]["argv"], ["--raiz", str(self.raiz), "status"])
        self.assertFalse((self.raiz / "state").exists())

    def test_argv_fora_do_utf8_vira_erro_da_cli_sem_traceback(self):
        """Revisão do lote 2: no Linux, bytes fora do UTF-8 no argv chegam como substitutos soltos."""
        with self.assertRaises(cliente.PorteiroIndisponivel) as ctx:
            cliente.pedir(self.fila, ["tarefa", "criar", "--objetivo", "\udcff"], prazo=10)
        self.assertIn("UTF-8", str(ctx.exception))
        self.assertEqual(list((self.fila / "pedidos").iterdir()), [], "nada entrou na fila")
        self.na_sessao()
        erro = io.StringIO()
        with redirect_stderr(erro):
            codigo = cliente.desviar(["tarefa", "criar", "--objetivo", "\udcff"])
        self.assertEqual(codigo, 2)
        self.assertEqual(json.loads(erro.getvalue())["error"]["code"], "E_PORTEIRO")


class TestEspera(ClienteCase):
    def relogio(self, passo: float):
        agora = [0.0]

        def ler():
            agora[0] += passo
            return agora[0]
        return ler

    def test_prazo_estourado_tira_o_pedido_da_fila(self):
        (self.fila / "respostas" / cliente.VIDA).write_text(json.dumps({"pid": 1, "renovada_em": _iso()}),
                                                            encoding="utf-8")
        with self.assertRaises(cliente.PorteiroIndisponivel) as ctx:
            cliente.pedir(self.fila, ["status"], prazo=5, sem_vida=1000, relogio=self.relogio(1.0),
                          dormir=lambda _s: None)
        self.assertIn("não respondeu", str(ctx.exception))
        self.assertEqual(list((self.fila / "pedidos").iterdir()), [])

    def test_sem_sinal_de_vida_falha_em_segundos(self):
        for vida in (None, 120):  # sem o arquivo, ou renovado há dois minutos
            with self.subTest(vida=vida):
                arq = self.fila / "respostas" / cliente.VIDA
                arq.unlink(missing_ok=True)
                if vida is not None:
                    arq.write_text(json.dumps({"pid": 1, "renovada_em": _iso(vida)}), encoding="utf-8")
                with self.assertRaises(cliente.PorteiroIndisponivel) as ctx:
                    cliente.pedir(self.fila, ["status"], prazo=900, sem_vida=3, relogio=self.relogio(1.0),
                                  dormir=lambda _s: None)
                self.assertIn("sinal de vida", str(ctx.exception))
                self.assertEqual(list((self.fila / "pedidos").iterdir()), [])

    def test_desistencia_diz_se_o_pedido_rodou_ou_nao(self):
        """Revisão do lote 2: o pedido que ainda estava na fila não rodou (repetir é seguro); o que o porteiro já tinha
        tirado pode ter rodado (conferir antes de repetir, senão a tarefa ou a lição sai em dobro)."""
        with self.assertRaises(cliente.PorteiroIndisponivel) as ctx:  # ninguém tirou o pedido: o cliente o tira
            cliente.pedir(self.fila, ["status"], prazo=900, sem_vida=3, relogio=self.relogio(1.0),
                          dormir=lambda _s: None)
        self.assertIn("não rodou", str(ctx.exception))
        tomado = threading.Event()
        porteiro = PorteiroDeEnsaio(self.fila, lambda pedido: tomado.set())  # tira da fila e não responde
        porteiro.start()
        self.addCleanup(porteiro.join, 5)
        self.addCleanup(porteiro.parar.set)
        for prazo, sem_vida, trecho in ((900, 3, "sinal de vida"), (3, 900, "não respondeu")):
            with self.subTest(trecho=trecho):
                tomado.clear()
                with self.assertRaises(cliente.PorteiroIndisponivel) as ctx:
                    cliente.pedir(self.fila, ["tarefa", "criar", "--objetivo", "fictícia"], prazo=prazo,
                                  sem_vida=sem_vida, relogio=self.relogio(1.0), dormir=lambda _s: tomado.wait(5))
                self.assertIn(trecho, str(ctx.exception))
                self.assertIn("pode ter rodado", str(ctx.exception))
                self.assertNotIn("não rodou", str(ctx.exception))
        self.assertEqual(len(porteiro.recebidos), 2)

    def test_resposta_fora_do_formato_e_fila_ausente(self):
        self.porteiro(lambda p: {"codigo": "0", "stdout": "", "stderr": ""})
        with self.assertRaises(cliente.PorteiroIndisponivel):
            cliente.pedir(self.fila, ["status"], prazo=10)
        with self.assertRaises(cliente.PorteiroIndisponivel):
            cliente.pedir(self.base / "nao-existe", ["status"], prazo=10)

    def test_desviar_transforma_a_falha_em_erro_da_cli(self):
        self.na_sessao()
        os.environ[cliente.ENV_PRAZO] = "0.2"
        erro = io.StringIO()
        with redirect_stderr(erro):
            codigo = cliente.desviar(["status"])
        self.assertEqual(codigo, 2)
        self.assertEqual(json.loads(erro.getvalue())["error"]["code"], "E_PORTEIRO")

    def test_prazo_do_ambiente(self):
        self.assertEqual(cliente._prazo({}), cliente.PRAZO_PADRAO)
        self.assertEqual(cliente._prazo({cliente.ENV_PRAZO: "30"}), 30.0)
        for ruim in ("abc", "0", "-5", "1e9"):
            self.assertEqual(cliente._prazo({cliente.ENV_PRAZO: ruim}), cliente.PRAZO_PADRAO, ruim)

    def test_pedido_grande_demais_nao_entra_na_fila(self):
        with self.assertRaises(cliente.PorteiroIndisponivel):
            cliente.pedir(self.fila, ["tarefa", "criar", "--objetivo=" + "x" * (cliente.TETO_PEDIDO + 1)], prazo=10)
        self.assertEqual(list((self.fila / "pedidos").iterdir()), [])

    def test_resposta_que_chega_na_hora_da_desistencia_vale(self):
        """Correção do lote 2: a resposta pode chegar entre a última leitura e a retirada; o cliente lê mais uma vez
        antes de desistir, em vez de dizer "pode ter rodado" de um pedido que já respondeu."""
        retirar = cliente._retirar

        def o_porteiro_tira_e_responde_antes(caminho):
            situacao = retirar(caminho)
            if caminho.suffix != ".json" or situacao != "retirado":
                return situacao
            corpo = {"versao": 1, "id": caminho.stem, "codigo": 0, "stdout": '{"ok": true}\n', "stderr": "",
                     "truncado": False, "duracao_s": 0.01}
            (self.fila / "respostas" / caminho.name).write_text(json.dumps(corpo), encoding="utf-8")
            return "tomado"  # para o cliente, o porteiro tirou o pedido primeiro e já respondeu
        with mock.patch.object(cliente, "_retirar", side_effect=o_porteiro_tira_e_responde_antes):
            resposta = cliente.pedir(self.fila, ["status"], prazo=3, sem_vida=900, relogio=self.relogio(1.0),
                                     dormir=lambda _s: None)
        self.assertEqual((resposta["codigo"], resposta["stdout"]), (0, '{"ok": true}\n'))


class TestInterrupcao(ClienteCase):
    """Correção do lote 2: interrompido, o cliente tira da fila o pedido ainda não atendido e diz se ele rodou, em vez
    de morrer calado e deixar o pedido rodar depois sem ninguém para ler a resposta."""

    def pedir_interrompido(self, dormir) -> str:
        try:
            cliente.pedir(self.fila, ["tarefa", "criar", "--objetivo", "fictícia"], prazo=900, sem_vida=900,
                          relogio=lambda: 0.0, dormir=dormir)
        except KeyboardInterrupt:
            self.fail("a interrupção escapou do cliente: o pedido ficou na fila para rodar sem ninguém")
        except cliente.PorteiroIndisponivel as exc:
            return str(exc)
        self.fail("o cliente não desistiu")

    def test_ctrl_c_na_espera_tira_o_pedido_da_fila(self):
        def ctrl_c(_s):
            raise KeyboardInterrupt
        erro = self.pedir_interrompido(ctrl_c)
        self.assertIn("interrompido", erro)
        self.assertIn("não rodou", erro)
        self.assertEqual(list((self.fila / "pedidos").iterdir()), [], "o pedido saiu da fila")

    def test_ctrl_c_depois_de_o_porteiro_tirar_diz_que_pode_ter_rodado(self):
        tomado = threading.Event()
        porteiro = PorteiroDeEnsaio(self.fila, lambda pedido: tomado.set())  # tira da fila e não responde
        porteiro.start()
        self.addCleanup(porteiro.join, 5)
        self.addCleanup(porteiro.parar.set)

        def ctrl_c_depois(_s):
            tomado.wait(5)
            raise KeyboardInterrupt
        erro = self.pedir_interrompido(ctrl_c_depois)
        self.assertIn("pode ter rodado", erro)
        self.assertNotIn("não rodou", erro)

    def test_sigterm_no_desvio_vira_interrupcao_e_o_tratador_volta(self):
        if signal.getsignal(signal.SIGTERM) != signal.SIG_DFL:
            self.skipTest("o processo dos testes já trata o SIGTERM")
        self.na_sessao()
        os.environ[cliente.ENV_PRAZO] = "5"  # sem o tratador, o cliente desiste sozinho: falha limpa, sem matar nada
        (self.fila / "respostas" / cliente.VIDA).write_text(json.dumps({"pid": 1, "renovada_em": _iso()}),
                                                            encoding="utf-8")
        visto = {}

        def sinal():
            visto["tratador"] = signal.getsignal(signal.SIGTERM)
            if callable(visto["tratador"]):  # no padrão, o SIGTERM mataria o processo dos testes
                signal.raise_signal(signal.SIGTERM)
        disparo = threading.Timer(0.3, sinal)
        disparo.start()
        self.addCleanup(disparo.cancel)
        erro = io.StringIO()
        with redirect_stderr(erro):
            codigo = cliente.desviar(["tarefa", "criar", "--objetivo", "fictícia"])
        disparo.join(5)
        self.assertTrue(callable(visto.get("tratador")), "o desvio não tratou o SIGTERM")
        self.assertEqual(codigo, 2)
        mensagem = json.loads(erro.getvalue())["error"]["message"]
        self.assertIn("interrompido", mensagem)
        self.assertIn("não rodou", mensagem)
        self.assertEqual(list((self.fila / "pedidos").iterdir()), [], "o pedido saiu da fila")
        self.assertEqual(signal.getsignal(signal.SIGTERM), signal.SIG_DFL, "o tratador de antes voltou")


class TestSemBanco(unittest.TestCase):
    def test_o_cliente_nao_importa_o_banco(self):
        texto = Path(cliente.__file__).read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"^\s*(import sqlite3|from \.core|from fundacao)", texto, re.M))


if __name__ == "__main__":
    unittest.main()
