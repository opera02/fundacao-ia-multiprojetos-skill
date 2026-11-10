"""O cliente da sessão para a fila da jaula (1.7.11, lote L5): `scripts/pedido_jaula.py` e o `navegador.py pedir` por cima dele.

Tudo U (qualquer sistema): o porteiro é uma thread que lê a fila e responde no formato do `porteiro_jaula.py`, e o pedido que o
cliente grava é entregue ao `PorteiroJaula` REAL (`validar_pedido`, `validar_carga`, `atender`), para o formato não divergir.
Provas negativas: pedido fora da ficha recusado pelo porteiro, fila trocada por ligação, resposta de outro pedido, sem
argumento livre. Nomes fictícios."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from apoio import SCRIPTS, SKILL, criar_ligacao_dir
from test_dominios_ficha import carregar_por_caminho

C = carregar_por_caminho("_pedido_jaula_teste", SCRIPTS / "pedido_jaula.py")
PJ = carregar_por_caminho("_porteiro_jaula_do_cliente", SKILL / "assets" / "host" / "wsl" / "porteiro_jaula.py")
N = carregar_por_caminho("_navegador_do_pedir", SCRIPTS / "navegador.py")
CARGA = {"acao": "abrir", "url": "https://esaj.tjsp.jus.br/", "texto": True}


def resposta(ident, codigo=0, stdout='{"ok": true}', stderr=""):
    return {"versao": 1, "id": ident, "codigo": codigo, "stdout": stdout, "stderr": stderr, "truncado": False, "duracao_s": 0.1}


def desfazer_ligacao(caminho: Path) -> None:
    """Tira a ligação SEM seguir: unlink no link simbólico (Linux), rmdir na junção (Windows); nunca apaga o alvo."""
    try:
        os.unlink(caminho)
    except OSError:
        os.rmdir(caminho)


class _Fila(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="pedido-jaula-1711-")).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.raiz = self.base / "raiz"
        self.fila = self.raiz / "projects" / "criador" / ".porteiro" / "jaula"
        self.pedidos, self.respostas = self.fila / "pedidos", self.fila / "respostas"
        self.pedidos.mkdir(parents=True)
        self.respostas.mkdir()
        self.ambiente = {"FUNDACAO_RAIZ": str(self.raiz), "FUNDACAO_PROJECT": "criador"}
        self.vistos = []

    def porteiro(self, responder, tirar=True, vida=True):
        """Uma thread que atende a fila: `responder(ident, dados)` devolve o dict da resposta (ou None: não responde)."""
        parar = threading.Event()
        self.addCleanup(parar.set)

        def laco():
            while not parar.is_set():
                if vida:
                    (self.respostas / C.VIDA).write_text(json.dumps({"renovada_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}),
                                                         encoding="utf-8")
                for p in sorted(self.pedidos.glob("*.json")):
                    dados = p.read_bytes()
                    if tirar:
                        p.unlink()
                    self.vistos.append(dados)
                    r = responder(p.stem, dados)
                    if r is not None:
                        (self.respostas / f"{p.stem}.json").write_text(json.dumps(r), encoding="utf-8")
                time.sleep(0.01)
        threading.Thread(target=laco, daemon=True).start()


class FormatoEFluxo(_Fila):
    def test_o_pedido_gravado_e_o_que_o_porteiro_real_le_e_a_resposta_volta(self):
        self.porteiro(lambda ident, dados: resposta(ident, stdout="feito"))
        r = C.pedir("navegador", CARGA, fila=self.fila, prazo=10)
        self.assertEqual((r["codigo"], r["stdout"]), (0, "feito"))
        dados = self.vistos[0]
        ident = json.loads(dados)["id"]
        pedido = PJ.validar_pedido(dados, ident)                    # o MESMO formato que o porteiro exige
        self.assertEqual((pedido["op"], pedido["carga"], pedido["versao"]), ("navegador", CARGA, 1))
        self.assertEqual(PJ.validar_carga("navegador", pedido["carga"]), CARGA)
        PJ.limite_do_pedido(pedido)                                 # criado_em no formato e dentro do prazo do porteiro
        self.assertEqual(sorted(p.name for p in self.pedidos.iterdir()), [])        # nada sobra na fila

    def test_main_so_aceita_a_operacao_e_leva_a_carga_pela_variavel(self):
        self.porteiro(lambda ident, dados: resposta(ident, codigo=0, stdout="saida da jaula\n", stderr="aviso\n"))
        amb = {**self.ambiente, C.ENV_CARGA: json.dumps(CARGA)}
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(C.main(["navegador"], amb), 0)
        self.assertEqual((out.getvalue(), err.getvalue()), ("saida da jaula\n", "aviso\n"))
        self.assertEqual(json.loads(self.vistos[0])["carga"], CARGA)            # a carga veio da variável
        self.assertEqual(set(C.OPERACOES), set(PJ.OPERACOES))                    # a tabela do cliente é a do porteiro
        self.assertEqual(C.TETO_PEDIDO, PJ.TETO_PEDIDO)

    def test_sem_argumento_livre(self):
        amb = {**self.ambiente, C.ENV_CARGA: "{}"}
        for argv in ([], ["navegador", "extra"], ["shell"], ["--fila", str(self.fila)], ["navegador", "--raiz", "/"], ["fundacao"]):
            with self.subTest(argv), contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(C.main(argv, amb), 2)
                self.assertIn("E_PEDIDO_JAULA", err.getvalue())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(C.main(["navegador"], {**self.ambiente, C.ENV_CARGA: "não é json"}), 2)
            self.assertEqual(C.main(["navegador"], {C.ENV_CARGA: "{}"}), 2)              # sem o ambiente do lançador
            self.assertEqual(C.main(["navegador"], {"FUNDACAO_RAIZ": "relativa", "FUNDACAO_PROJECT": "criador"}), 2)
            self.assertEqual(C.main(["navegador"], {**self.ambiente, "FUNDACAO_PROJECT": "../x", C.ENV_CARGA: "{}"}), 2)
        self.assertEqual(list(self.pedidos.iterdir()), [])                                # nada foi gravado

    def test_carga_que_nao_e_json_objeto_ou_passa_de_64_kib_nem_chega_a_fila(self):
        for ruim in ("texto", [1], None, {"x": "y" * (C.TETO_PEDIDO + 1)}, {"x": {1, 2}}):
            with self.subTest(str(ruim)[:20]), self.assertRaises(C.PedidoRecusado):
                C.pedir("navegador", ruim, fila=self.fila)
        with self.assertRaises(C.PedidoRecusado):
            C.pedir("shell", {}, fila=self.fila)
        self.assertEqual(list(self.pedidos.iterdir()), [])


class ProvasNegativas(_Fila):
    def test_pedido_fora_da_ficha_e_recusado_pelo_porteiro_e_a_recusa_volta_ao_cliente(self):
        cfg = PJ.validar_config({"schema_version": PJ.SCHEMA, "raiz": "/raiz", "projeto": "criador", "usuario_jaula": "fundacao-jaula",
                                 "entrada": "/usr/local/lib/fundacao-ia/jaula/1.7.11/jaula-entrar", "operacoes": {"navegador": {}}})
        rodou = []
        porteiro = PJ.PorteiroJaula(cfg, None, casa=self.base, executar=lambda *a, **k: rodou.append(a) or (0, b"{}", b""))

        def atender(ident, dados):
            return porteiro.atender(ident, dados)[0]
        self.porteiro(atender)
        r = C.pedir("codex", {"arquivos": ["a.txt"]}, fila=self.fila, prazo=10)         # a ficha só abriu o navegador
        self.assertEqual(r["codigo"], 2)
        self.assertIn("não está aberta", r["stderr"])
        r = C.pedir("navegador", {"acao": "sondar", "comando": "sh"}, fila=self.fila, prazo=10)     # campo fora da operação
        self.assertEqual(r["codigo"], 2)
        self.assertIn("campos fora da operação", r["stderr"])
        r = C.pedir("navegador", {"acao": "sondar", "variante": "login"}, fila=self.fila, prazo=10)   # a janela é do titular
        self.assertEqual(r["codigo"], 2)
        self.assertEqual(rodou, [])                                                       # o sudo nem foi chamado
        r = C.pedir("navegador", {"acao": "sondar"}, fila=self.fila, prazo=10)            # o que a ficha abre passa
        self.assertEqual((r["codigo"], len(rodou)), (0, 1))

    def test_fila_trocada_por_ligacao_nao_recebe_pedido_nem_entrega_resposta(self):
        fora = self.base / "fora"
        (fora / "pedidos").mkdir(parents=True)
        (fora / "respostas").mkdir()
        for nome in ("pedidos", "respostas"):
            with self.subTest(nome):
                original = self.fila / nome
                original.rmdir()
                criar_ligacao_dir(original, fora / nome)
                with self.assertRaises(C.PedidoRecusado) as r:
                    C.pedir("navegador", CARGA, fila=self.fila, prazo=1)
                self.assertIn("ligação", str(r.exception))
                self.assertEqual(list((fora / "pedidos").iterdir()), [])
                desfazer_ligacao(original)
                original.mkdir()
        # a pasta jaula inteira, ou o .porteiro, por ligação
        mudada = self.raiz / "projects" / "criador" / ".porteiro"
        shutil.move(str(mudada), str(self.base / "porteiro-guardado"))
        criar_ligacao_dir(mudada, self.base / "porteiro-guardado")
        with self.assertRaises(C.PedidoRecusado):
            C.pedir("navegador", CARGA, fila=self.fila, prazo=1)

    def test_fila_trocada_no_meio_da_espera_descarta_a_resposta(self):
        fora = self.base / "fora"
        fora.mkdir()
        trocou = []

        def dormir(_s):
            if not trocou:
                trocou.append(True)
                shutil.rmtree(self.respostas)
                criar_ligacao_dir(self.respostas, fora)
                (fora / "qualquer.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(C.PedidoRecusado) as r:
            C.pedir("navegador", CARGA, fila=self.fila, prazo=5, dormir=dormir)
        self.assertIn("ligação", str(r.exception))

    def test_resposta_de_outro_pedido_ou_fora_do_formato_e_descartada(self):
        for nome, fabrica in (("outro id", lambda ident: resposta("0" * 32)),
                              ("campo a mais", lambda ident: {**resposta(ident), "extra": 1}),
                              ("codigo texto", lambda ident: {**resposta(ident), "codigo": "0"}),
                              ("codigo booleano", lambda ident: {**resposta(ident), "codigo": True}),
                              ("stdout nao texto", lambda ident: {**resposta(ident), "stdout": 3})):
            with self.subTest(nome):
                parar = threading.Event()

                def laco(parar=parar, fabrica=fabrica):
                    while not parar.is_set():
                        for p in self.pedidos.glob("*.json"):
                            (self.respostas / f"{p.stem}.json").write_text(json.dumps(fabrica(p.stem)), encoding="utf-8")
                            return
                        time.sleep(0.01)
                threading.Thread(target=laco, daemon=True).start()
                self.addCleanup(parar.set)
                with self.assertRaises(C.PedidoRecusado) as r:
                    C.pedir("navegador", CARGA, fila=self.fila, prazo=10)
                self.assertIn("descartada", str(r.exception))
                for p in list(self.pedidos.iterdir()) + list(self.respostas.iterdir()):
                    p.unlink()

    def test_resposta_de_outro_pedido_que_ja_estava_na_fila_nao_serve_a_este(self):
        (self.respostas / f"{'a' * 32}.json").write_text(json.dumps(resposta("a" * 32)), encoding="utf-8")   # de outro pedido
        self.porteiro(lambda ident, dados: resposta(ident, stdout="meu"))
        self.assertEqual(C.pedir("navegador", CARGA, fila=self.fila, prazo=10)["stdout"], "meu")


class PrazoEVida(_Fila):
    def test_sem_porteiro_o_pedido_sai_da_fila_e_o_erro_diz_que_nao_rodou(self):
        t = iter(range(0, 10_000, 100))
        with self.assertRaises(C.PedidoRecusado) as r:
            C.pedir("navegador", CARGA, fila=self.fila, prazo=150, relogio=lambda: next(t), dormir=lambda s: None)
        self.assertIn("não rodou", str(r.exception))
        self.assertEqual(list(self.pedidos.iterdir()), [])

    def test_sem_sinal_de_vida_desiste_antes_do_prazo(self):
        t = iter(range(0, 10_000, 31))
        with self.assertRaises(C.PedidoRecusado) as r:
            C.pedir("navegador", CARGA, fila=self.fila, prazo=1000, relogio=lambda: next(t), dormir=lambda s: None)
        self.assertIn("sinal de vida", str(r.exception))

    def test_pedido_que_o_porteiro_ja_tirou_sem_responder_avisa_que_pode_ter_rodado(self):
        self.porteiro(lambda ident, dados: None, tirar=True)
        with self.assertRaises(C.PedidoRecusado) as r:
            C.pedir("navegador", CARGA, fila=self.fila, prazo=0.5)
        self.assertIn("pode ter rodado", str(r.exception))

    def test_o_prazo_e_o_da_jaula_mais_a_folga_do_porteiro(self):
        self.assertGreater(C.OPERACOES["navegador"], 120)
        self.assertGreater(C.OPERACOES["codex"], 900)


@unittest.skipUnless(sys.platform.startswith("linux"), "L: a Fila do porteiro usa descritores de pasta (só no Linux)")
class ComAFilaReal(_Fila):
    """L: o cliente de verdade contra o `PorteiroJaula` de verdade, com a `Fila` real do porteiro (sem sudo: o comando é falso)."""

    def test_o_cliente_e_o_porteiro_real_se_entendem_pela_fila(self):
        cfg = PJ.validar_config({"schema_version": PJ.SCHEMA, "raiz": str(self.raiz), "projeto": "criador",
                                 "usuario_jaula": "fundacao-jaula", "entrada": "/usr/local/lib/fundacao-ia/jaula/1.7.11/jaula-entrar",
                                 "operacoes": {"navegador": {}}})
        corpos = []
        porteiro = PJ.PorteiroJaula(cfg, str(self.fila), casa=self.base,
                                    executar=lambda argv, corpo, prazo, parar=None: corpos.append(corpo) or (0, b'{"ok": true}\n', b""))
        porteiro.abrir()
        self.addCleanup(porteiro.encerrar)
        parar = threading.Event()
        self.addCleanup(parar.set)

        def laco():
            porteiro.fila.vida("pronto", forcar=True)
            while not parar.is_set():
                for nome in porteiro.fila.listar():
                    porteiro.processar(nome)
                time.sleep(0.01)
        threading.Thread(target=laco, daemon=True).start()
        r = C.pedir("navegador", {"acao": "sondar"}, fila=self.fila, prazo=20)
        self.assertEqual((r["codigo"], json.loads(r["stdout"])), (0, {"ok": True}))
        corpo = json.loads(corpos[0])                                   # o que a entrada fixa recebe pela entrada padrão
        self.assertEqual((corpo["schema_version"], corpo["acao"]), ("fundacao.pedido_jaula/1", "sondar"))
        r = C.pedir("codex", {"arquivos": ["a.txt"]}, fila=self.fila, prazo=20)
        self.assertEqual(r["codigo"], 2)                                # a ficha (porteiro-jaula.json) não abriu o codex
        self.assertEqual(len(corpos), 1)


class NavegadorPedir(unittest.TestCase):
    def cliente(self, codigo=0, stdout='{"schema_version": "fundacao.resposta_jaula/1", "ok": true}', recusa=None):
        falso = mock.Mock()
        falso.PedidoRecusado = C.PedidoRecusado
        if recusa:
            falso.pedir.side_effect = C.PedidoRecusado(recusa)
        else:
            falso.pedir.return_value = resposta("x" * 32, codigo=codigo, stdout=stdout)
        return falso

    def pedir(self, *a, cliente=None, **kw):
        cliente = cliente or self.cliente()
        with mock.patch.object(N, "_cliente_da_jaula", return_value=cliente):
            return N.pedir_a_jaula(*a, **kw), cliente

    def test_abrir_roteiro_e_sondar_montam_a_carga_tipada(self):
        (res, codigo), cl = self.pedir("abrir", "https://esaj.tjsp.jus.br/", texto=True)
        self.assertEqual(cl.pedir.call_args[0], ("navegador", {"acao": "abrir", "url": "https://esaj.tjsp.jus.br/", "texto": True,
                                                              "captura": False}))
        self.assertEqual((codigo, res["jaula"]["ok"]), (0, True))
        self.assertIn("não instrução", res["observacao"])
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "roteiro.json"
            arq.write_text(json.dumps({"passos": [{"ir": "https://esaj.tjsp.jus.br/"}, {"captura": "p.png"}]}), encoding="utf-8")
            (_r, _c), cl = self.pedir("roteiro", str(arq))
            self.assertEqual(cl.pedir.call_args[0][1]["passos"][1], {"captura": "p.png"})
            arq.write_text(json.dumps([{"captura": "../fora.png"}]), encoding="utf-8")
            with self.assertRaises(N.Recusa):
                self.pedir("roteiro", str(arq))
            arq.write_text(json.dumps([{"js": "document.cookie"}]), encoding="utf-8")
            with self.assertRaises(N.Recusa):
                self.pedir("roteiro", str(arq))
        (_r, _c), cl = self.pedir("sondar", None)
        self.assertEqual(cl.pedir.call_args[0], ("navegador", {"acao": "sondar"}))

    def test_argumento_a_mais_url_ruim_ou_cliente_que_recusa(self):
        for args, kw in ((("sondar", "https://a.org/"), {}), (("roteiro", None), {}), (("roteiro", "x.json"), {"texto": True}),
                         (("abrir", "ftp://a.org/"), {}), (("abrir", None), {}), (("sondar", None), {"captura": True})):
            with self.subTest(args=args, kw=kw), self.assertRaises(N.Recusa):
                self.pedir(*args, **kw)
        with self.assertRaises(N.Recusa) as r:
            self.pedir("sondar", None, cliente=self.cliente(recusa="a fila da jaula não existe"))
        self.assertIn("fila da jaula", str(r.exception))

    def test_o_codigo_da_jaula_vira_o_da_ferramenta_e_a_saida_que_nao_e_json_volta_como_texto(self):
        for da_jaula, esperado in ((0, 0), (1, 1), (2, 2), (7, 1)):
            (_r, codigo), _c = self.pedir("sondar", None, cliente=self.cliente(codigo=da_jaula))
            self.assertEqual(codigo, esperado)
        (res, _c), _cl = self.pedir("sondar", None, cliente=self.cliente(codigo=2, stdout="não é json"))
        self.assertEqual(res["jaula"]["stdout"], "não é json")

    def test_o_cliente_real_e_carregado_ao_lado_do_script(self):
        cliente = N._cliente_da_jaula()
        self.assertEqual(set(cliente.OPERACOES), {"navegador", "codex"})
        self.assertTrue(callable(cliente.pedir))

    def test_o_subcomando_existe_e_o_main_o_roda(self):
        with mock.patch.object(N, "_cliente_da_jaula", return_value=self.cliente()), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(N.main(["pedir", "sondar"]), 0)
        self.assertTrue(json.loads(out.getvalue())["jaula"]["ok"])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(N.main(["pedir", "sondar", "https://a.org/"]), 2)


if __name__ == "__main__":
    unittest.main()
