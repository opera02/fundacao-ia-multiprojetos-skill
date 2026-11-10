"""`assets/host/wsl/porteiro_jaula.py` e o trecho do lançador que o sobe (1.7.11, lote L4; DESENHO-JAULA §2.1 e §7.3).

O porteiro da jaula é o caminho da SESSÃO até a jaula: pedidos tipados, comando FIXO (`sudo -n -u fundacao-jaula --
<entrada fixa> <projeto> <modo>`), modo de uma tabela, nada do pedido no argv. Provas negativas: o porteiro recusa o que
está fora do comando fixo (operação desconhecida, modo do titular, campo extra, operação que a ficha não abriu), a ficha
sem seção de jaula não sobe nada (o lançador só sobe com o `porteiro-jaula.json`, e o `conferir` distingue "sem
operações") e o teto de chamadas por dia vale. As peças puras rodam em qualquer sistema; a fila de verdade e o lançador só
no Linux. Nomes fictícios; `<usuario>` e a raiz de exemplo.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apoio import SKILL
from test_dominios_ficha import carregar_por_caminho
from test_host_projeto_apoio import LINUX, carregar_preparo

WSL = SKILL / "assets" / "host" / "wsl"
PJ = carregar_por_caminho("_porteiro_jaula_teste", WSL / "porteiro_jaula.py")
J = carregar_por_caminho("_jaula_do_porteiro_teste", WSL / "jaula.py")
ENTRADA = "/usr/local/lib/fundacao-ia/jaula/1.7.11/jaula-entrar"
ID = "a1" * 16
RESPOSTA_DA_JAULA = b'{"schema_version": "fundacao.resposta_jaula/1", "modo": "navegador", "ok": true}\n'


def config(**operacoes) -> dict:
    return {"schema_version": PJ.SCHEMA, "raiz": "/mnt/e/Raiz Exemplo", "projeto": "criador",
            "usuario_jaula": "fundacao-jaula", "entrada": ENTRADA, "operacoes": operacoes}


def bruto(op="navegador", carga=None, ident=ID, criado_em=None, **extras) -> bytes:
    corpo = {"versao": 1, "id": ident, "op": op, "carga": {} if carga is None else carga,
             "criado_em": criado_em or PJ.agora_iso(), **extras}
    return json.dumps(corpo).encode("utf-8")


class Gravador:
    """O `executar` de ensaio: guarda o que o porteiro mandou rodar e devolve o que se combinou."""

    def __init__(self, retorno=(0, RESPOSTA_DA_JAULA, b"")):
        self.retorno, self.chamadas = retorno, []

    def __call__(self, argv, entrada, prazo, parar=None):
        self.chamadas.append({"argv": list(argv), "entrada": entrada, "prazo": prazo})
        if isinstance(self.retorno, Exception):
            raise self.retorno
        return self.retorno


class Base(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="porteiro-jaula-teste-")).resolve()
        self.dono_antes, PJ.DONO_ESPERADO = PJ.DONO_ESPERADO, None  # os arquivos de teste são do usuário do teste

    def tearDown(self):
        PJ.DONO_ESPERADO = self.dono_antes
        shutil.rmtree(self.base, ignore_errors=True)

    def porteiro(self, cfg=None, executar=None):
        executar = executar or Gravador()
        return PJ.PorteiroJaula(cfg or config(navegador={}, codex={"teto_chamadas_dia": 3}), None, casa=self.base,
                                executar=executar), executar


class Configuracao(Base):
    def test_a_configuracao_valida_e_a_sem_operacoes(self):
        for cfg in (config(), config(navegador={}), config(codex={"teto_chamadas_dia": 30}),
                    config(navegador={}, codex={"teto_chamadas_dia": 1})):
            self.assertIs(PJ.validar_config(cfg), cfg)

    def test_cada_campo_fora_do_esquema_e_recusado(self):
        casos = {"campo a mais": {**config(), "sudo": "nopasswd"}, "schema": {**config(), "schema_version": "x/1"},
                 "usuário da jaula": {**config(), "usuario_jaula": "root"},
                 "entrada relativa": {**config(), "entrada": "jaula-entrar"},
                 "entrada com ..": {**config(), "entrada": "/usr/local/../jaula-entrar"},
                 "entrada com outro nome": {**config(), "entrada": "/usr/local/lib/fundacao-ia/jaula/1.7.11/sh"},
                 "entrada com espaço": {**config(), "entrada": "/usr/local/lib/x y/jaula-entrar"},
                 "raiz relativa": {**config(), "raiz": "Raiz"}, "raiz com ..": {**config(), "raiz": "/mnt/../e"},
                 "projeto com --": {**config(), "projeto": "a--b"}, "projeto vazio": {**config(), "projeto": ""},
                 "operacoes lista": {**config(), "operacoes": []},
                 "falta campo": {k: v for k, v in config().items() if k != "entrada"}}
        for nome, cfg in casos.items():
            with self.subTest(nome), self.assertRaises(PJ.Recusa):
                PJ.validar_config(cfg)

    def test_so_a_sessao_tem_operacao_e_cada_uma_com_a_forma_dela(self):
        for ruim in ({"canario": {}}, {"navegador-janela": {}}, {"codex-titular": {}}, {"shell": {}}, {"codex-exec": {}},
                     {"navegador": {"url": "https://exemplo.org"}}, {"codex": {}}, {"codex": {"teto_chamadas_dia": 0}},
                     {"codex": {"teto_chamadas_dia": 101}}, {"codex": {"teto_chamadas_dia": True}},
                     {"codex": {"teto_chamadas_dia": 5, "modo": "codex-titular"}},
                     {"codex": {"teto_chamadas_dia": "5"}}):
            with self.subTest(ruim), self.assertRaises(PJ.Recusa):
                PJ.validar_config(config(**ruim))

    def test_carregar_config_estrito_e_sem_ligacao(self):
        arquivo = self.base / "porteiro-jaula.json"
        arquivo.write_text(json.dumps(config(navegador={})), encoding="utf-8")
        self.assertEqual(PJ.carregar_config(arquivo)["projeto"], "criador")
        arquivo.write_text('{"schema_version": "x", "schema_version": "y"}', encoding="utf-8")  # chave repetida
        with self.assertRaises(PJ.Recusa):
            PJ.carregar_config(arquivo)
        arquivo.write_text(json.dumps(config(navegador={})).replace('"criador"', '"criador", "x": NaN'), encoding="utf-8")
        with self.assertRaises(PJ.Recusa):
            PJ.carregar_config(arquivo)
        arquivo.write_bytes(b" " * (PJ.TETO_CONFIG + 1))
        with self.assertRaises(PJ.Recusa):
            PJ.carregar_config(arquivo)
        with self.assertRaises(PJ.Recusa):
            PJ.carregar_config(self.base / "nao-existe.json")

    def test_o_dono_esperado_e_root(self):
        PJ.DONO_ESPERADO = 0
        arquivo = self.base / "porteiro-jaula.json"
        arquivo.write_text(json.dumps(config()), encoding="utf-8")
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            with self.assertRaises(PJ.Recusa):
                PJ.carregar_config(arquivo)  # o arquivo é do usuário do teste, não de root
        self.assertEqual(PJ.DONO_ESPERADO, 0)

    def test_a_tabela_da_sessao_cabe_na_jaula(self):
        """O que o porteiro encaminha é aceito pela entrada fixa: modos da sessão, campos e prazo."""
        self.assertEqual({o["modo"] for o in PJ.OPERACOES.values()}, {"navegador", "codex-exec"})
        for op, spec in PJ.OPERACOES.items():
            with self.subTest(op):
                self.assertIn(spec["modo"], J.MODOS)
                self.assertLessEqual(set(spec["campos"]), J.CAMPOS_POR_MODO[spec["modo"]])
                self.assertGreater(spec["prazo_s"], J.PERFIS[spec["modo"]].prazo_s)
        self.assertEqual(PJ.USUARIO_JAULA, J.USUARIO)
        self.assertEqual(PJ.ESQUEMA_PEDIDO_DA_JAULA, J.ESQUEMA_PEDIDO)


class Pedido(Base):
    def test_pedido_valido(self):
        pedido = PJ.validar_pedido(bruto("codex", {"arquivos": ["a.txt"]}), ID)
        self.assertEqual((pedido["op"], pedido["carga"]), ("codex", {"arquivos": ["a.txt"]}))

    def test_cada_pedido_fora_do_formato_e_recusado(self):
        agora = PJ.agora_iso()
        corpo = {"versao": 1, "id": ID, "op": "navegador", "carga": {}, "criado_em": agora}
        casos = {"campo a mais": {**corpo, "argv": ["sh"]}, "falta carga": {k: v for k, v in corpo.items() if k != "carga"},
                 "versão 2": {**corpo, "versao": 2}, "versão bool": {**corpo, "versao": True},
                 "id de outro arquivo": {**corpo, "id": "b2" * 16}, "id curto": {**corpo, "id": "a1"},
                 "op canario": {**corpo, "op": "canario"}, "op janela": {**corpo, "op": "navegador-janela"},
                 "op do modo": {**corpo, "op": "codex-exec"}, "op shell": {**corpo, "op": "sh -c x"},
                 "op lista": {**corpo, "op": ["navegador"]}, "carga lista": {**corpo, "carga": []},
                 "data ruim": {**corpo, "criado_em": "ontem"}, "data sem Z": {**corpo, "criado_em": agora[:-1]}}
        for nome, c in casos.items():
            with self.subTest(nome), self.assertRaises(PJ.Recusa):
                PJ.validar_pedido(json.dumps(c).encode("utf-8"), ID)
        for ruim in (b"\xff\xfe", b"[]", b'{"versao": 1, "versao": 1}', b'{"versao": NaN}', b"{" * 100000):
            with self.subTest(ruim[:20]), self.assertRaises(PJ.Recusa):
                PJ.validar_pedido(ruim, ID)

    def test_pedido_velho_ou_do_futuro_nao_roda(self):
        agora = datetime.now(timezone.utc)
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        for deslocamento in (timedelta(seconds=-60), timedelta(seconds=60)):
            pedido = PJ.validar_pedido(bruto(criado_em=(agora + deslocamento).strftime(fmt)), ID)
            with self.subTest(deslocamento), self.assertRaises(PJ.Recusa):
                PJ.limite_do_pedido(pedido, agora)
        pedido = PJ.validar_pedido(bruto(criado_em=agora.strftime(fmt)), ID)
        PJ.limite_do_pedido(pedido, agora)  # no prazo: passa

    def test_a_carga_tem_so_os_campos_da_operacao(self):
        self.assertEqual(PJ.validar_carga("navegador", {}), {})
        # 1.7.11 L6: a carga do Codex leva o prompt (1 a 32 KiB) e a lista de arquivos
        boa = {"prompt": "resuma", "arquivos": ["a.txt", "b/c.md"]}
        self.assertEqual(PJ.validar_carga("codex", boa), boa)
        # L5: a sessão pede ações do navegador com os campos da ação; o resto (modo, variante, alvo da janela, comando)
        # nunca é campo da sessão.
        carga_boa = {"acao": "abrir", "url": "https://exemplo.org", "texto": True}
        self.assertEqual(PJ.validar_carga("navegador", carga_boa), carga_boa)
        ruins = [("navegador", {"alvo": "esaj.exemplo.org"}), ("navegador", {"variante": "login"}),
                 ("navegador", {"acao": "abrir", "comando": "sh"}), ("navegador", {"argv": ["sh"]}),
                 ("navegador", {"modo": "canario"}),
                 ("codex", {"arquivos": ["a.txt"], "modo": "codex-titular"}), ("codex", {"arquivos": ["a"], "variante": "login"}),
                 ("codex", {"arquivos": ["a"], "como": "navegador"}), ("codex", {"arquivos": ["a"], "argv": ["sh"]}),
                 ("codex", {"arquivos": ["a"], "comando": "sh"}), ("codex", {}), ("codex", {"arquivos": []}),
                 ("codex", {"arquivos": "a.txt"}), ("codex", {"arquivos": [1]}),
                 ("codex", {"arquivos": ["a"] * (PJ.TETO_ARQUIVOS + 1)})]
        for op, carga in ruins:
            with self.subTest(op=op, carga=str(carga)[:50]), self.assertRaises(PJ.Recusa):
                PJ.validar_carga(op, carga)


class ComandoFixo(Base):
    """N-JAU-2 do lado do porteiro: o argv vem do código e da configuração, nunca do pedido."""

    def test_o_argv_e_o_fixo_de_cada_operacao(self):
        cfg = config(navegador={}, codex={"teto_chamadas_dia": 3})
        self.assertEqual(PJ.argv_da_jaula(cfg, "navegador"),
                         ["/usr/bin/sudo", "-n", "-u", "fundacao-jaula", "--", ENTRADA, "criador", "navegador"])
        self.assertEqual(PJ.argv_da_jaula(cfg, "codex"),
                         ["/usr/bin/sudo", "-n", "-u", "fundacao-jaula", "--", ENTRADA, "criador", "codex-exec"])

    def test_o_pedido_valido_roda_so_o_comando_fixo_e_leva_a_carga_pela_entrada_padrao(self):
        p, grav = self.porteiro()
        resposta, linha = p.atender(ID, bruto("codex", {"prompt": "resuma", "arquivos": ["a.txt"]}))
        self.assertEqual(resposta["codigo"], 0, resposta)
        (chamada,) = grav.chamadas
        self.assertEqual(chamada["argv"], PJ.argv_da_jaula(p.cfg, "codex"))
        self.assertEqual(json.loads(chamada["entrada"]),
                         {"schema_version": "fundacao.pedido_jaula/1", "id": ID, "prompt": "resuma", "arquivos": ["a.txt"]})
        self.assertNotIn(ID.encode(), " ".join(chamada["argv"]).encode())  # nada do pedido no argv
        self.assertEqual(chamada["prazo"], PJ.OPERACOES["codex"]["prazo_s"])
        self.assertEqual((linha["op"], linha["modo"], linha["rodou"]), ("codex", "codex-exec", True))
        self.assertEqual(json.loads(resposta["stdout"])["modo"], "navegador")  # a resposta da jaula, adiante

    def test_o_que_esta_fora_do_comando_fixo_e_recusado_e_nada_roda(self):
        p, grav = self.porteiro(config(navegador={}))
        pedidos = {
            "operação do titular (canario)": bruto("canario"), "operação da janela": bruto("navegador-janela"),
            "operação que o modo chama": bruto("codex-exec"), "operação inventada": bruto("sh"),
            "operação que a ficha não abriu (codex)": bruto("codex", {"arquivos": ["a.txt"]}),
            "modo escolhido na carga": bruto("navegador", {"modo": "canario"}),
            "argv na carga": bruto("navegador", {"argv": ["sh", "-c", "id"]}),
            "comando fora da carga": bruto("navegador", {}, comando="sh"), "argv no pedido": bruto(argv=["sh"]),
            "id de outro arquivo": bruto(ident="b2" * 16), "pedido velho": bruto(
                criado_em=(datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")),
            "lixo": b"\x00\x01"}
        for nome, dados in pedidos.items():
            with self.subTest(nome):
                resposta, linha = p.atender(ID, dados)
                self.assertEqual(resposta["codigo"], 2, resposta)
                self.assertIn("E_PORTEIRO_JAULA", resposta["stderr"])
                self.assertFalse(linha["rodou"])
        self.assertEqual(grav.chamadas, [])

    def test_configuracao_sem_operacoes_nao_atende_nada(self):
        """A ficha sem seção de jaula (ou só com as janelas do titular): nenhuma operação da sessão."""
        p, grav = self.porteiro(config())
        for op, carga in (("navegador", {}), ("codex", {"arquivos": ["a.txt"]})):
            resposta, _ = p.atender(ID, bruto(op, carga))
            self.assertEqual(resposta["codigo"], 2)
        self.assertEqual(grav.chamadas, [])

    def test_resposta_da_jaula_e_o_que_o_sudo_recusa(self):
        for retorno, codigo, trecho in (
                ((0, RESPOSTA_DA_JAULA, b""), 0, "resposta_jaula"),
                ((1, RESPOSTA_DA_JAULA, b""), 1, "resposta_jaula"),
                ((2, b'{"ok": false, "erro": "recusa"}', b""), 2, "recusa"),
                ((1, b"", b"sudo: a password is required\n"), 2, "password is required"),
                ((1, b"", b"sudo: sorry, you are not allowed to execute"), 2, "not allowed"),
                ((0, b"lixo que nao e json", b""), 2, "a jaula não respondeu"),
                ((7, RESPOSTA_DA_JAULA, b"x"), 2, "a jaula não respondeu"),
                (PJ.Recusa("a jaula passou do prazo"), 2, "passou do prazo")):
            with self.subTest(str(retorno)[:40]):
                p, _ = self.porteiro(executar=Gravador(retorno))
                resposta, linha = p.atender(ID, bruto())
                self.assertEqual(resposta["codigo"], codigo, resposta)
                self.assertIn(trecho, resposta["stdout"] + resposta["stderr"])
                self.assertEqual(linha["codigo"], codigo)

    def test_saida_enorme_e_cortada(self):
        grande = b'{"x": "' + b"a" * (PJ.TETO_STDOUT + 1000) + b'"}'
        p, _ = self.porteiro(executar=Gravador((0, grande, b"")))
        resposta, _ = p.atender(ID, bruto())
        self.assertTrue(resposta["truncado"])
        self.assertLessEqual(len(resposta["stdout"]), PJ.TETO_STDOUT)

    def test_o_comando_fixo_e_o_que_a_sudoers_do_preparo_libera(self):
        """O argv do porteiro tem uma linha exata na sudoers do preparo, para o projeto e o modo da operação."""
        m = carregar_preparo()
        pj = m.preparo_jaula()
        programas = ENTRADA.rsplit("/", 1)[0]
        pares = [("criador", "canario"), ("criador", "navegador"), ("criador", "codex-exec")]
        texto = pj.texto_do_sudoers("<usuario>", programas, pares, "nopasswd")
        cfg = config(navegador={}, codex={"teto_chamadas_dia": 3})
        for op in ("navegador", "codex"):
            argv = PJ.argv_da_jaula(cfg, op)
            regra = f"<usuario> ALL=(fundacao-jaula) NOPASSWD: {' '.join(argv[argv.index('--') + 1:])}"
            self.assertIn(regra, texto.splitlines())


class TetoPorDia(Base):
    def test_o_teto_do_codex_vale_e_so_conta_o_que_chegou_a_jaula(self):
        p, grav = self.porteiro(config(codex={"teto_chamadas_dia": 2}))
        hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ontem = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        p.privada.mkdir(parents=True)
        for dia, op, rodou in ((ontem, "codex", True), (hoje, "navegador", True), (hoje, "codex", False)):
            PJ.registrar(p.registro, {"id": "x", "op": op, "rodou": rodou, "em": dia + "T10:00:00Z"})
        self.assertEqual(PJ.chamadas_de_hoje(p.registro, "codex", hoje), 0)
        carga = {"prompt": "resuma", "arquivos": ["a.txt"]}
        for i in range(2):
            resposta, linha = p.atender(f"{i:032x}", bruto("codex", carga, ident=f"{i:032x}"))
            self.assertEqual(resposta["codigo"], 0, resposta)
            PJ.registrar(p.registro, linha)
        self.assertEqual(PJ.chamadas_de_hoje(p.registro, "codex", hoje), 2)
        resposta, linha = p.atender(ID, bruto("codex", carga))
        self.assertEqual(resposta["codigo"], 2)
        self.assertIn("teto de 2 chamadas por dia", resposta["stderr"])
        self.assertFalse(linha["rodou"])
        self.assertEqual(len(grav.chamadas), 2)

    def test_registro_ilegivel_nao_conta_nada(self):
        self.assertEqual(PJ.chamadas_de_hoje(self.base / "nao-existe", "codex", "2026-11-08"), 0)
        arquivo = self.base / "r.jsonl"
        arquivo.write_text("lixo\n[1]\n", encoding="utf-8")
        self.assertEqual(PJ.chamadas_de_hoje(arquivo, "codex", "2026-11-08"), 0)


class FormaDoSudo(Base):
    def test_padrao_e_a_forma_sem_senha_e_a_escolha_do_preparo_vale(self):
        etc = str(self.base)
        self.assertEqual(PJ.forma_do_sudo(etc), "nopasswd")
        arquivo = self.base / PJ.INSTALACAO_NOME
        arquivo.write_text(json.dumps({"schema_version": PJ.ESQUEMA_INSTALACAO, "sudo": "senha"}), encoding="utf-8")
        self.assertEqual(PJ.forma_do_sudo(etc), "senha")
        for ruim in ({"schema_version": PJ.ESQUEMA_INSTALACAO, "sudo": "qualquer"}, {"sudo": "senha"}, []):
            arquivo.write_text(json.dumps(ruim), encoding="utf-8")
            with self.subTest(ruim), self.assertRaises(PJ.Recusa):
                PJ.forma_do_sudo(etc)

    def test_preparar_sudo_so_age_na_forma_com_senha(self):
        chamadas = []

        class Resultado:
            returncode = 0

        def rodar(argv, env=None):
            chamadas.append((argv, env))
            return Resultado()
        etc = str(self.base)
        self.assertEqual(PJ.preparar_sudo(etc, rodar), 0)
        self.assertEqual(chamadas, [])
        (self.base / PJ.INSTALACAO_NOME).write_text(
            json.dumps({"schema_version": PJ.ESQUEMA_INSTALACAO, "sudo": "senha"}), encoding="utf-8")
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(PJ.preparar_sudo(etc, rodar), 0)
        self.assertEqual(chamadas[0][0], ["/usr/bin/sudo", "-v"])
        self.assertEqual(set(chamadas[0][1]), {"PATH", "LANG", "TERM"})  # ambiente mínimo


    def test_f11_o_ticket_do_sudo_e_invalidado_quando_o_porteiro_termina_so_na_forma_com_senha(self):
        """3ª passada, F11: `sudo -k` (que nunca pede senha) no fim do porteiro, só na forma com senha, sem esperar entrada."""
        chamadas = []

        def rodar(argv, **kw):
            chamadas.append((argv, kw))
        etc = str(self.base)
        self.assertFalse(PJ.invalidar_sudo(etc, rodar))                                   # nopasswd: não há ticket
        self.assertEqual(chamadas, [])
        (self.base / PJ.INSTALACAO_NOME).write_text(
            json.dumps({"schema_version": PJ.ESQUEMA_INSTALACAO, "sudo": "senha"}), encoding="utf-8")
        self.assertTrue(PJ.invalidar_sudo(etc, rodar))
        argv, kw = chamadas[0]
        self.assertEqual(argv, ["/usr/bin/sudo", "-k"])
        self.assertEqual(set(kw["env"]), {"PATH", "LANG"})
        self.assertEqual((kw["stdin"], kw["timeout"]), (subprocess.DEVNULL, 10))   # nada espera entrada
        for erro in (OSError("sem sudo"), subprocess.TimeoutExpired("sudo", 10)):
            def quebra(argv, **kw):
                raise erro
            self.assertFalse(PJ.invalidar_sudo(etc, quebra))                              # falha não derruba o porteiro
        (self.base / PJ.INSTALACAO_NOME).write_text("lixo", encoding="utf-8")
        self.assertFalse(PJ.invalidar_sudo(etc, rodar))                                   # instalação ilegível: nada roda
        self.assertEqual(len(chamadas), 1)

    def test_f11_o_porteiro_invalida_o_ticket_ao_terminar_pela_linha_de_comando(self):
        from unittest import mock
        so_posix = types.SimpleNamespace(name="posix", open=os.open, supports_dir_fd={os.open})   # o porteiro só sobe no Linux
        args = ["servir", "--config", "x", "--fila", "y", "--pid-lancador", "4242"]
        with mock.patch.object(PJ, "invalidar_sudo") as inv, mock.patch.object(PJ, "os", so_posix),                 mock.patch.object(PJ, "carregar_config", return_value={"operacoes": ["navegador"], "projeto": "criador"}),                 mock.patch.object(PJ, "PorteiroJaula") as classe:
            classe.return_value.servir.return_value = 0
            self.assertEqual(PJ.main(args), 0)
            self.assertEqual(inv.call_count, 1)
            classe.return_value.servir.side_effect = PJ.Recusa("não subiu")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(PJ.main(args), 2)
            self.assertEqual(inv.call_count, 2)                                              # também quando o porteiro nem sobe


class Executar(Base):
    @unittest.skipUnless(LINUX, "o comando fixo roda em sessão própria: só no Linux")
    def test_executar_sudo_com_um_programa_de_verdade_e_o_prazo(self):
        codigo, saida, erro = PJ.executar_sudo(["/bin/sh", "-c", "cat; echo e >&2"], b"entrada", 10)
        self.assertEqual((codigo, saida, erro), (0, b"entrada", b"e\n"))
        with self.assertRaises(PJ.Recusa):
            PJ.executar_sudo(["/bin/sh", "-c", "sleep 30"], b"", 1.2)
        parar = __import__("threading").Event()
        parar.set()
        with self.assertRaises(PJ.Recusa):
            PJ.executar_sudo(["/bin/sh", "-c", "sleep 30"], b"", 30, parar)


@unittest.skipUnless(LINUX and getattr(os, "supports_dir_fd", None) and os.open in os.supports_dir_fd,
                     "a fila usa descritores de pasta: só no Linux")
class FilaDeVerdade(Base):
    """A `Fila` do porteiro.py em `.porteiro/jaula`: o pedido sai da fila, a resposta entra por troca atômica e o registro
    não leva conteúdo."""

    def setUp(self):
        super().setUp()
        self.raiz = self.base / "Raiz Exemplo"
        self.fila = self.raiz / "projects" / "criador" / ".porteiro" / "jaula"
        self.fila.parent.mkdir(parents=True)
        self.grav = Gravador()
        cfg = {**config(navegador={}), "raiz": str(self.raiz)}
        self.p = PJ.PorteiroJaula(cfg, str(self.fila), os.getpid(), casa=self.base / "casa", executar=self.grav)
        (self.base / "casa").mkdir()
        self.p.privada.mkdir(parents=True)
        self.p.fila.abrir()

    def tearDown(self):
        self.p.encerrar()
        super().tearDown()

    def test_pedido_na_fila_vira_resposta_e_registro(self):
        (self.fila / "pedidos" / f"{ID}.json").write_bytes(bruto("navegador"))
        self.p.processar(f"{ID}.json")
        self.assertFalse((self.fila / "pedidos" / f"{ID}.json").exists())
        resposta = json.loads((self.fila / "respostas" / f"{ID}.json").read_text(encoding="utf-8"))
        self.assertEqual((resposta["id"], resposta["codigo"]), (ID, 0))
        (linha,) = [json.loads(l) for l in self.p.registro.read_text(encoding="utf-8").splitlines()]
        self.assertEqual((linha["op"], linha["rodou"], linha["codigo"]), ("navegador", True, 0))
        self.assertNotIn("carga", linha)

    def test_pedido_hostil_na_fila_recebe_recusa_e_nao_roda(self):
        (self.fila / "pedidos" / f"{ID}.json").write_bytes(bruto("canario"))
        outro = "b2" * 16
        (self.fila / "pedidos" / f"{outro}.json").write_bytes(b"\xff\xfe")
        for nome in (f"{ID}.json", f"{outro}.json"):
            self.p.processar(nome)
            resposta = json.loads((self.fila / "respostas" / nome).read_text(encoding="utf-8"))
            self.assertEqual(resposta["codigo"], 2)
        self.assertEqual(self.grav.chamadas, [])

    def test_ligacao_na_fila_nao_e_seguida(self):
        alvo = self.base / "segredo.json"
        alvo.write_bytes(bruto("navegador"))
        try:
            (self.fila / "pedidos" / f"{ID}.json").symlink_to(alvo)
        except OSError:
            self.skipTest("link simbólico indisponível")
        self.p.processar(f"{ID}.json")
        self.assertEqual(self.grav.chamadas, [])
        self.assertEqual(json.loads((self.fila / "respostas" / f"{ID}.json").read_text(encoding="utf-8"))["codigo"], 2)

    def test_fila_de_outro_projeto_e_recusada(self):
        cfg = {**config(navegador={}), "raiz": str(self.raiz)}
        with self.assertRaises(PJ.Recusa):
            PJ.PorteiroJaula(cfg, str(self.raiz / "projects" / "outro" / ".porteiro" / "jaula"), 1, casa=self.base)


class LinhaDeComando(Base):
    def escrever(self, cfg) -> Path:
        arquivo = self.base / "porteiro-jaula.json"
        arquivo.write_text(json.dumps(cfg), encoding="utf-8")
        return arquivo

    def rodar(self, *args) -> tuple[int, str, str]:
        import contextlib
        import io
        saida, erro = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
            codigo = PJ.main(list(args))
        return codigo, saida.getvalue(), erro.getvalue()

    def test_conferir_distingue_com_operacoes_sem_operacoes_e_recusa(self):
        codigo, saida, _ = self.rodar("conferir", "--config", str(self.escrever(config(navegador={}))))
        self.assertEqual((codigo, json.loads(saida)["operacoes"]), (0, ["navegador"]))
        codigo, saida, _ = self.rodar("conferir", "--config", str(self.escrever(config())))
        self.assertEqual((codigo, json.loads(saida)["operacoes"]), (3, []))
        codigo, _, erro = self.rodar("conferir", "--config", str(self.escrever({**config(), "x": 1})))
        self.assertEqual(codigo, 2)
        self.assertIn("E_PORTEIRO_JAULA", erro)

    def test_servir_sem_operacoes_nao_sobe_nada(self):
        """Ficha sem operações de jaula para a sessão: `servir` recusa antes de tocar a fila ou o processo do lançador."""
        codigo, _, erro = self.rodar("servir", "--config", str(self.escrever(config())), "--fila", str(self.base / "f"),
                                     "--pid-lancador", str(os.getpid()))
        self.assertEqual(codigo, 2)
        self.assertIn("não abre operações", erro)
        self.assertFalse((self.base / "f").exists())

    def test_servir_recusa_pid_invalido(self):
        for pid in ("0", "1", "-1", str(PJ.PID_MAXIMO + 1)):
            codigo, _, erro = self.rodar("servir", "--config", str(self.escrever(config(navegador={}))), "--fila",
                                         str(self.base / "f"), "--pid-lancador", pid)
            self.assertEqual(codigo, 2, pid)

    def test_sem_acao_ou_com_opcao_desconhecida_o_argparse_recusa(self):
        for args in ((), ("servir",), ("conferir",), ("conferir", "--config", "x", "--demais", "1")):
            with self.subTest(args), self.assertRaises(SystemExit):
                self.rodar(*args)


class TrechoDoLancador(unittest.TestCase):
    """O trecho do `abrir-sessao.sh` que sobe o porteiro da jaula, conferido no texto do modelo (qualquer sistema)."""

    @classmethod
    def setUpClass(cls):
        cls.texto = (WSL / "abrir-sessao.sh").read_text(encoding="utf-8")
        cls.codigo = [l.strip() for l in cls.texto.splitlines() if l.strip() and not l.lstrip().startswith("#")]

    def test_so_sobe_com_o_porteiro_jaula_json_da_area(self):
        (entrada,) = [i for i, l in enumerate(self.codigo) if l == 'if [ -f "$AREA/porteiro-jaula.json" ]; then']
        usos = [i for i, l in enumerate(self.codigo) if "$PORTEIRO_JAULA" in l and not l.startswith("PORTEIRO_JAULA=")]
        self.assertTrue(usos)
        self.assertTrue(all(i > entrada for i in usos), "o porteiro da jaula só roda dentro do if do arquivo")
        sobe = [l for l in self.codigo if '"$PORTEIRO_JAULA" servir' in l]
        self.assertEqual(len(sobe), 1)
        self.assertIn('exec env -i PATH=/usr/bin:/bin HOME="$HOME" LANG=C.UTF-8 "$PY" -I -B "$PORTEIRO_JAULA" servir', sobe[0])
        seguintes = " ".join(self.codigo[self.codigo.index(sobe[0]):self.codigo.index(sobe[0]) + 3])
        self.assertIn('--config "$AREA/porteiro-jaula.json" --fila "$PROJ/.porteiro/jaula" --pid-lancador "$$"', seguintes)

    def test_o_conferir_manda_e_so_o_codigo_zero_sobe(self):
        texto = " ".join(self.codigo)
        self.assertIn("0)", self.codigo)
        self.assertIn("3) ;;", self.codigo)  # válido sem operações: nada a subir
        self.assertRegex(texto, r'\*\) nao_abre "o porteiro da jaula recusou a configuração')
        self.assertIn('"$PORTEIRO_JAULA" conferir --config "$AREA/porteiro-jaula.json"', texto)

    def test_encerra_com_o_lancador_e_nao_troca_as_variaveis_do_modelo(self):
        self.assertIn('kill -TERM "$PID_PORTEIRO_JAULA" 2>/dev/null || true', self.codigo)
        m = carregar_preparo()
        self.assertEqual(sorted(set(m.MARCADOR.findall(self.texto))), sorted(m.CHAVES_DO_LANCADOR))  # nenhum marcador novo
        for ruim in ('"$@"', "$@", "$*", "shift", "getopts"):
            self.assertFalse([l for l in self.codigo if ruim in l], ruim)

    def test_f11_o_lancador_invalida_o_ticket_do_sudo_ao_sair_so_se_subiu_a_jaula(self):
        """3ª passada, F11: `sudo -k` no `fim()` (que roda em toda saída), só depois de o `preparar-sudo` ter sido tentado."""
        fim = self.codigo[self.codigo.index("fim() {"):]
        fim = fim[:fim.index("}")]
        self.assertIn('if [ "$SUDO_DA_JAULA" = 1 ]; then', fim)
        self.assertIn("/usr/bin/sudo -k </dev/null >/dev/null 2>&1 || true", fim)
        self.assertEqual(self.codigo.count("SUDO_DA_JAULA=0"), 1)
        (marca,) = [i for i, l in enumerate(self.codigo) if l == "SUDO_DA_JAULA=1"]
        (prepara,) = [i for i, l in enumerate(self.codigo) if '"$PORTEIRO_JAULA" preparar-sudo' in l]
        self.assertLess(marca, prepara)                                                      # marcado antes do sudo -v: falha também limpa
        (zero,) = [i for i, l in enumerate(self.codigo) if l == "0)"]
        self.assertLess(zero, marca)                                                         # e só dentro do caso que sobe o porteiro
        self.assertTrue(any(l.startswith("trap fim EXIT") for l in self.codigo))

    def test_lancador_gerado_leva_o_trecho_e_a_fila_da_jaula(self):
        m = carregar_preparo()
        valores = {"RAIZ": "/mnt/e/Raiz", "PROJETO": "criador", "USUARIO": "dono-da-sessao",
                   "AREA": "/etc/fundacao-ia/projetos/criador", "SKILL": "/etc/fundacao-ia/skill/1.7.11-abc",
                   "CLAUDE_BIN": "/etc/fundacao-ia/claude/2.1.302/claude", "CLAUDE_VERSAO": "2.1.302",
                   "CLAUDE_SHA256": "1" * 64, "CLAUDE_ORIGEM_HASH": "manifesto assinado", "FERRAMENTAS": "Bash,Read",
                   "PLUGINS": "", "PREPARO_SHA256": "2" * 64, "PORTEIRO_SHA256": "3" * 64,
                   "TEMP_PROJETO": "/tmp/fundacao-ia-criador", "SONDA_INTEROP_CMD": "/mnt/c/Windows/System32/cmd.exe",
                   "SONDA_INTEROP_BINFMT": "/proc/sys/fs/binfmt_misc"}
        gerado = m.lancador(valores, self.texto)
        self.assertIn('"$PROJ/.porteiro/jaula/respostas"', gerado)
        self.assertNotIn("{{", gerado)


def porteiro_jaula_falso(registro: Path) -> str:
    """O `porteiro_jaula.py` de ensaio: registra cada chamada (sem conteúdo) e o fim; `conferir` devolve o código do
    arquivo de controle (padrão 0); `servir` espera o lançador morrer (ou falha, se o controle mandar).

    A parte de biblioteca (esquema, recusa, validação da configuração e nome da instalação) é a do `porteiro_jaula.py`
    real da árvore: o preparo importa esta cópia para validar o `porteiro-jaula.json`, e só a linha de comando é falsa."""
    real = SKILL / "assets" / "host" / "wsl" / "porteiro_jaula.py"
    return ('#!/usr/bin/env python3\n'
            'import importlib.util, json, os, signal, sys, time\n'
            '_ESPEC = importlib.util.spec_from_file_location("_porteiro_jaula_real", ' + repr(str(real)) + ')\n'
            '_REAL = importlib.util.module_from_spec(_ESPEC)\n'
            '_ESPEC.loader.exec_module(_REAL)\n'
            'SCHEMA, Recusa, validar_config = _REAL.SCHEMA, _REAL.Recusa, _REAL.validar_config\n'
            'INSTALACAO_NOME = _REAL.INSTALACAO_NOME\n'
            'REGISTRO = ' + repr(str(registro)) + '\n\n\n'
            'def anotar(**d):\n'
            '    with open(REGISTRO, "a", encoding="utf-8") as f:\n'
            '        f.write(json.dumps(d) + "\\n")\n\n\n'
            'def principal(args):\n'
            '    anotar(argv=args, cwd=os.getcwd(), env=sorted(os.environ))\n'
            '    if args[:1] == ["conferir"]:\n'
            '        controle = REGISTRO + ".conferir"\n'
            '        return int(open(controle).read()) if os.path.exists(controle) else 0\n'
            '    if args[:1] == ["servir"]:\n'
            '        if os.path.exists(REGISTRO + ".servir-falha"):\n'
            '            return 1\n'
            '        pid = int(args[args.index("--pid-lancador") + 1])\n'
            '        signal.signal(signal.SIGTERM, lambda *_: (anotar(fim=True), sys.exit(0)))\n'
            '        while True:\n'
            '            try:\n'
            '                os.kill(pid, 0)\n'
            '            except OSError:\n'
            '                return 0\n'
            '            time.sleep(0.1)\n'
            '    return 0\n\n\n'
            'if __name__ == "__main__":\n'
            '    sys.exit(principal(sys.argv[1:]))\n')


@unittest.skipUnless(LINUX and shutil.which("bash") and shutil.which("flock") and Path("/usr/bin/python3").exists(),
                     "lançador do Ubuntu: só no Linux com bash, flock e /usr/bin/python3")
class LancadorSobeOPorteiroDaJaula(unittest.TestCase):
    """O lançador de verdade num ensaio sem root, com o `claude` e o `porteiro_jaula.py` falsos (o real exige a
    configuração de dono root): sobe só com o `porteiro-jaula.json` e o `conferir` em 0; sem a seção de jaula, nada."""

    SECAO = {"dominios": ["esaj.exemplo.org"], "logins": [], "modos": ["sessao"]}

    def setUp(self):
        from test_host_projeto_apoio import claude_de_ensaio, raiz_de_ensaio, skill_de_ensaio
        self.base = Path(tempfile.mkdtemp(prefix="lancador-jaula-1711-")).resolve()
        self.registro = self.base / "porteiro-jaula-chamadas.jsonl"
        self.skill = skill_de_ensaio(self.base)
        self.m = carregar_preparo(self.skill)
        self.pj = self.m.preparo_jaula()
        for rel, _ in self.pj.ARQUIVOS_DA_JAULA:  # a cópia de ensaio da skill só tem 3 scripts
            if rel.startswith("scripts/"):
                shutil.copyfile(SKILL / rel, self.skill / rel)
        (self.skill / "assets" / "host" / "wsl" / "porteiro_jaula.py").write_text(
            porteiro_jaula_falso(self.registro), encoding="utf-8", newline="\n")
        self.raiz = raiz_de_ensaio(self.base, self.skill)
        self.home = self.base / "home"
        self.home.mkdir()
        self.claude = claude_de_ensaio(self.base / "claude-ensaio")
        self.area = self.base / "area" / "projetos" / "caso-real"
        self.proj = self.raiz / "projects" / "caso-real"
        self.lancador = self.base / "bin" / "abrir-fundacao-caso-real"

    def tearDown(self):
        for p in sorted(self.base.rglob("*"), reverse=True):
            try:
                if not p.is_symlink():
                    os.chmod(p, 0o700 if p.is_dir() else 0o600)
            except OSError:
                pass
        shutil.rmtree(self.base, ignore_errors=True)

    def instalar(self, **secoes):
        from test_host_projeto_apoio import (ficha_de_ensaio, gravar_ficha_na_caixa, instalar, instalar_canario,
                                             relatorio_de_canario, usuario_atual)
        r = instalar_canario(self.skill, self.base, relatorio_de_canario(self.m, self.raiz, self.claude))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 1, **secoes))
        r = instalar(self.skill, self.raiz, self.base, "caso-real", self.claude, "--jaula-base",
                     str(self.base / "jaula" / "programas"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        if secoes:  # os programas da jaula (a conferência na abertura exige a jaula como o preparo a fixou)
            caminhos = self.pj.caminhos_de_ensaio(self.base / "jaula", self.base / "area")
            plano = self.pj.montar_plano(self.skill, self.base / "area", ["caso-real"], usuario_atual(), caminhos)
            self.pj.instalar_jaula(plano, rodar=lambda argv, entrada=None: (0, ""))

    def abrir(self) -> subprocess.CompletedProcess:
        env = {"HOME": str(self.home), "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"}
        return subprocess.run(["bash", str(self.lancador)], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=env, timeout=120)

    def chamadas(self) -> list:
        if not self.registro.exists():
            return []
        return [json.loads(l) for l in self.registro.read_text(encoding="utf-8").splitlines() if l.strip()]

    def test_ficha_sem_secao_de_jaula_nao_sobe_nada(self):
        self.instalar()
        self.assertFalse((self.area / "porteiro-jaula.json").exists())
        r = self.abrir()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.chamadas(), [])  # nem o conferir
        self.assertFalse((self.proj / ".porteiro" / "jaula").exists())

    def test_com_operacoes_para_a_sessao_sobe_o_porteiro_e_o_encerra_com_o_lancador(self):
        self.instalar(navegador=self.SECAO)
        r = self.abrir()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        chamadas = self.chamadas()
        self.assertEqual([c["argv"][0] for c in chamadas if "argv" in c], ["conferir", "preparar-sudo", "servir"])
        servir = next(c for c in chamadas if c.get("argv", [""])[0] == "servir")
        self.assertEqual(servir["argv"][:5], ["servir", "--config", f"{self.area}/porteiro-jaula.json", "--fila",
                                              f"{self.proj}/.porteiro/jaula"])
        self.assertEqual(servir["argv"][5], "--pid-lancador")
        self.assertEqual(servir["cwd"], "/")
        self.assertFalse([k for k in servir["env"] if k.startswith("FUNDACAO_")])
        for pasta in ("pedidos", "respostas"):
            self.assertTrue((self.proj / ".porteiro" / "jaula" / pasta).is_dir())
        self.assertIn({"fim": True}, chamadas)  # o lançador o encerrou (TERM) ao sair

    def test_so_janela_do_titular_a_configuracao_existe_e_nada_sobe(self):
        self.instalar(navegador={**self.SECAO, "modos": ["login"]})
        self.assertTrue((self.area / "porteiro-jaula.json").is_file())
        Path(str(self.registro) + ".conferir").write_text("3", encoding="utf-8")  # o conferir real diz: sem operações
        r = self.abrir()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([c["argv"][0] for c in self.chamadas()], ["conferir"])

    def test_configuracao_recusada_pelo_porteiro_da_jaula_impede_a_abertura(self):
        self.instalar(navegador=self.SECAO)
        Path(str(self.registro) + ".conferir").write_text("2", encoding="utf-8")
        r = self.abrir()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("NÃO foi aberta", r.stderr)
        self.assertIn("o porteiro da jaula recusou a configuração", r.stderr)
        self.assertFalse((self.home / "chamada-claude.txt").exists())

    def test_porteiro_que_nao_fica_de_pe_impede_a_abertura(self):
        self.instalar(navegador=self.SECAO)
        Path(str(self.registro) + ".servir-falha").write_text("1", encoding="utf-8")
        r = self.abrir()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("o porteiro da jaula não ficou de pé", r.stderr)
        self.assertFalse((self.home / "chamada-claude.txt").exists())

    def test_jaula_nao_instalada_impede_a_abertura_pela_conferencia(self):
        """A jaula que o preparo do projeto fixou tem de estar instalada: sem ela o lançador nem chega ao porteiro."""
        from test_host_projeto_apoio import (ficha_de_ensaio, gravar_ficha_na_caixa, instalar, instalar_canario,
                                             relatorio_de_canario)
        instalar_canario(self.skill, self.base, relatorio_de_canario(self.m, self.raiz, self.claude))
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 1, navegador=self.SECAO))
        instalar(self.skill, self.raiz, self.base, "caso-real", self.claude, "--jaula-base",
                 str(self.base / "jaula" / "programas"))
        r = self.abrir()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("jaula:", r.stdout + r.stderr)
        self.assertEqual(self.chamadas(), [])


class UmaCopiaDoLancador(unittest.TestCase):
    def test_o_trecho_e_o_mesmo_que_o_modelo_tem_uma_vez_so(self):
        texto = (WSL / "abrir-sessao.sh").read_text(encoding="utf-8")
        self.assertEqual(texto.count("Porteiro da jaula (1.7.11, lote L4"), 1)
        self.assertEqual(len(re.findall(r'\bPORTEIRO_JAULA="\$SKILL/assets/host/wsl/porteiro_jaula.py"', texto)), 1)


if __name__ == "__main__":
    unittest.main()
