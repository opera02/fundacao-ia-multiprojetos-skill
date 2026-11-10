"""O navegador da jaula (1.7.11, lote L5; DESENHO-JAULA §5 e §8; item 12 das respostas do titular de 08/11/2026).

U (qualquer sistema): o invólucro `chromium-sem-disfarce`, o pedido e a carga do navegador (N-NAV-1, N-NAV-11), as opções
fixas que o canário decide (M6), a entrada fixa de ponta a ponta com a caixa e o proxy falsos (N-NAV-4b, N-NAV-5, N-NAV-10),
o `navegador.py jaula` com um Playwright simulado, o lançador do titular, o preparo dos downloads com pinos (comandos
falsos) e o passo 6b do `preparar-wsl.sh`. L (só no Linux; pulam com o motivo quando faltam o bwrap, o Python do sistema ou
o Chromium): o invólucro de verdade, o programa montado no bubblewrap e o Chromium real (`navigator.webdriver`, N-NAV-9).
Com `FUNDACAO_CI_EXIGE_BWRAP=1` a falta do bwrap FALHA em vez de pular. Nomes e domínios fictícios."""

from __future__ import annotations

import contextlib
import copy
import importlib.machinery
import importlib.util
import io
import re
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from apoio import SCRIPTS, SKILL, criar_ligacao_dir
from test_dominios_ficha import carregar_por_caminho
from test_jaula_bwrap import EXIGE, MOTIVO
from test_host_projeto_apoio import carregar_preparo, ficha_de_ensaio
from test_host_projeto_area import (SECAO_NAVEGADOR, USUARIO_DO_ENSAIO, VisudoFalso, ficha_aplicada, gravar_area,
                                    secao_codex)

WSL = SKILL / "assets" / "host" / "wsl"
J = carregar_por_caminho("_jaula_navegador_teste", WSL / "jaula.py")
N = carregar_por_caminho("_navegador_da_jaula_teste", SCRIPTS / "navegador.py")
CANARIO = carregar_por_caminho("_canario_navegador_teste", WSL / "canario_jaula.py")
HOJE = date(2026, 11, 8)
HASHES = {"jaula-entrar": "a" * 64, "proxy_lista.py": "b" * 64, "bwrap": "c" * 64}
FICHA = {"valida": True, "project_id": "criador",
         "navegador": {"dominios": ["*.tjsp.jus.br", "esaj.tjsp.jus.br"], "logins": ["esaj.tjsp.jus.br"],
                       "modos": ["sessao", "login", "captcha"]}}
SEGREDO = "-".join(("cookie", "ficticio", "0123456789", "ABCDEFGHIJ", "xyz"))  # valor de cookie inventado, 20+ caracteres


def involucro():
    carregador = importlib.machinery.SourceFileLoader("_involucro_teste", str(WSL / "chromium-sem-disfarce"))
    modulo = importlib.util.module_from_spec(importlib.util.spec_from_loader(carregador.name, carregador))
    carregador.exec_module(modulo)
    return modulo


W = involucro()


class InvolucroDoChromium(unittest.TestCase):
    def test_tira_o_disfarce_e_o_que_abriria_a_rede_e_forca_o_resto(self):
        entrada = ["--disable-blink-features=AutomationControlled", "--no-proxy-server", "--proxy-bypass-list=<-loopback>",
                   "--host-resolver-rules=MAP * 1.2.3.4", "--load-extension=/x", "--disable-extensions-except=/x",
                   "--disable-web-security", "--remote-debugging-address=0.0.0.0", "--proxy-server=http://outro:1",
                   "--headless", "--user-data-dir=/home/jaula/perfil"]
        saida, recusa = W.filtrar(entrada)
        self.assertIsNone(recusa)
        for tirado in ("AutomationControlled", "--no-proxy-server", "bypass", "host-resolver", "load-extension",
                       "extensions-except", "web-security", "0.0.0.0", "outro:1"):
            self.assertFalse([a for a in saida if tirado in a], tirado)
        self.assertEqual(saida[-3:], ["--enable-automation", "--disable-features=EncryptedClientHello",
                                      "--proxy-server=http://127.0.0.1:3128"])
        self.assertEqual(saida[:2], ["--headless", "--user-data-dir=/home/jaula/perfil"])

    def test_so_o_token_do_disfarce_sai_e_o_ech_e_sempre_desligado(self):
        saida, _ = W.filtrar(["--disable-blink-features=Foo,AutomationControlled", "--disable-features=A,B",
                              "--disable-features=C", "--enable-features=EncryptedClientHello,Bom", "--enable-automation"])
        self.assertIn("--disable-blink-features=Foo", saida)
        self.assertEqual([a for a in saida if a.startswith("--disable-features")], ["--disable-features=A,B,C,EncryptedClientHello"])
        self.assertIn("--enable-features=Bom", saida)
        self.assertEqual(saida.count("--enable-automation"), 1)
        sozinho, _ = W.filtrar(["--enable-features=EncryptedClientHello"])
        self.assertFalse([a for a in sozinho if a.startswith("--enable-features")])

    def test_remote_debugging_address_so_em_127_0_0_1(self):
        self.assertIn("--remote-debugging-address=127.0.0.1", W.filtrar(["--remote-debugging-address=127.0.0.1"])[0])

    def test_user_data_dir_fora_da_casa_da_jaula_e_recusado(self):
        for ruim in ("--user-data-dir=/tmp/perfil", "--user-data-dir=/home/jaulax", "--user-data-dir=/home/jaula/../etc",
                     "--user-data-dir=/mnt/c/User" + "s/x/Chrome", "--user-data-dir", "--user-data-dir="):
            with self.subTest(ruim):
                saida, recusa = W.filtrar([ruim])
                self.assertEqual(saida, [])
                self.assertIn("user-data-dir", recusa)
        self.assertIsNone(W.filtrar(["--user-data-dir=/home/jaula"])[1])

    def test_acha_o_chrome_mais_novo_e_nunca_o_headless_shell(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(W.chromium_do_playwright(d))
            for pasta, nome in (("chromium-1100/chrome-linux", "chrome"), ("chromium-1169/chrome-linux", "chrome"),
                                ("chromium_headless_shell-1169/chrome-linux", "headless_shell"),
                                ("chromium-2000/chrome-linux", "outro")):
                (Path(d) / pasta).mkdir(parents=True)
                (Path(d) / pasta / nome).write_bytes(b"x")
                os.chmod(Path(d) / pasta / nome, 0o755)
            self.assertEqual(Path(W.chromium_do_playwright(d)).parts[-3:], ("chromium-1169", "chrome-linux", "chrome"))
            self.assertIsNone(W.chromium_do_playwright(str(Path(d) / "nao-existe")))

    def test_main_entrega_ao_chromium_recusa_ou_diz_que_falta(self):
        with tempfile.TemporaryDirectory() as d:
            with contextlib.redirect_stderr(io.StringIO()) as erro:
                self.assertEqual(W.main(["--x"], {"PLAYWRIGHT_BROWSERS_PATH": d}), 127)
            self.assertIn("não está instalado", erro.getvalue())
            chrome = Path(d) / "chromium-1169" / "chrome-linux" / "chrome"
            chrome.parent.mkdir(parents=True)
            chrome.write_bytes(b"x")
            os.chmod(chrome, 0o755)
            with mock.patch.object(W.os, "execv") as execv:
                W.main(["--no-proxy-server", "--headless"], {"PLAYWRIGHT_BROWSERS_PATH": d})
            real, argv = execv.call_args[0]
            self.assertEqual((real, argv[0]), (str(chrome), str(chrome)))
            self.assertNotIn("--no-proxy-server", argv)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(W.main(["--user-data-dir=/tmp/x"], {"PLAYWRIGHT_BROWSERS_PATH": d}), 2)

    def test_o_arquivo_tem_lf_shebang_isolado_e_nao_importa_o_projeto(self):
        bruto = (WSL / "chromium-sem-disfarce").read_bytes()
        self.assertNotIn(b"\r", bruto)
        self.assertTrue(bruto.startswith(b"#!/usr/bin/python3 -I\n"))
        for proibido in (b"socket", b"urllib", b"subprocess", b"requests"):   # sem rede e sem rodar outro programa
            self.assertNotIn(proibido, bruto)

    def test_o_involucro_e_executavel_no_git(self):
        try:
            r = subprocess.run(["git", "-C", str(SKILL), "ls-files", "-s", "--", "assets/host/wsl/chromium-sem-disfarce"],
                               capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            self.skipTest("git indisponível")
        if r.returncode != 0 or not r.stdout.strip():
            self.skipTest("o invólucro ainda não está no índice do git (o coordenador usa git add --chmod=+x); o preparo põe 0755 de qualquer jeito")
        self.assertTrue(r.stdout.startswith("100755 "), r.stdout)


def pedido(**campos):
    base = {"schema_version": J.ESQUEMA_PEDIDO, "id": "pedido-nav-0001"}
    base.update(campos)
    return json.dumps(base).encode()


MEDIDAS = {"sandbox_proprio": True, "grafico": "wayland-socket"}
DOMINIOS = FICHA["navegador"]["dominios"]


class PedidoECargaDoNavegador(unittest.TestCase):
    def carga(self, campos, modo="navegador", medidas=MEDIDAS, ficha=FICHA):
        return J.carga_do_navegador(J.validar_pedido(pedido(**campos), "criador", modo), modo, DOMINIOS, ficha, medidas)

    def recusa(self, campos, modo="navegador"):
        with self.assertRaises(J.Recusa):
            self.carga(campos, modo)

    def test_abrir_roteiro_e_sondar_validos(self):
        c = self.carga({"acao": "abrir", "url": "https://esaj.tjsp.jus.br/cpopg", "texto": True})
        self.assertEqual(c, {"acao": "abrir", "sandbox": True, "url": "https://esaj.tjsp.jus.br/cpopg", "texto": True,
                             "captura": False})
        c = self.carga({"acao": "abrir", "url": "https://www.tjsp.jus.br/"})      # o curinga cobre subdomínio (e o principal)
        self.assertEqual(c["url"], "https://www.tjsp.jus.br/")
        c = self.carga({"acao": "roteiro", "passos": [{"ir": "https://tjsp.jus.br/"}, {"texto": "body"}, {"captura": "p.png"}]})
        self.assertEqual(len(c["passos"]), 3)
        self.assertEqual(self.carga({"acao": "sondar"}), {"acao": "sondar", "sandbox": True})

    def test_n_nav_1_url_fora_da_lista_e_recusada_antes_de_abrir(self):
        for url in ("https://example.com/", "https://esaj.tjsp.jus.br.evil.org/", "https://xtjsp.jus.br/",
                    "https://tjsp.jus.br.evil.org/", "https://127.0.0.1/", "https://[::1]/", "https://localhost/",
                    "https://usuario:senha" + "@" + "esaj.tjsp.jus.br/",  # por partes: a varredura de segredo
                    "https://esaj.tjsp.jus.br:8443/", "file:///etc/passwd",
                    "javascript:alert(1)", "ftp://esaj.tjsp.jus.br/", "https:///x", "https://esaj.tjsp.jus.br/\n", "x" * 2001, "", None, 7):
            with self.subTest(url=str(url)[:40]):
                self.recusa({"acao": "abrir", "url": url})
        self.recusa({"acao": "roteiro", "passos": [{"ir": "https://example.com/"}]})          # também dentro do roteiro

    def test_n_nav_11_nao_ha_passo_de_javascript_envio_de_arquivo_nem_cookie(self):
        for passo in ({"js": "document.cookie"}, {"evaluate": "1"}, {"upload": "/etc/passwd"}, {"cookie": "x"},
                       {"preencher": "#a", "valor": "x", "js": "1"}, {"clicar": "a", "ir": "https://esaj.tjsp.jus.br/"},
                       {"captura": "../fora.png"}, {"captura": "a/b.png"}, {"captura": "c:/x.png"}, {"captura": "p.html"},
                       {"captura": "/etc/passwd"}, {}, "ir", 3):
            with self.subTest(passo=str(passo)):
                self.recusa({"acao": "roteiro", "passos": [passo]})
        self.recusa({"acao": "roteiro", "passos": []})
        self.recusa({"acao": "roteiro", "passos": [{"esperar": 1}] * 201})

    def test_campos_fora_da_acao_e_tipos_errados(self):
        self.recusa({"acao": "abrir", "url": "https://esaj.tjsp.jus.br/", "passos": [{"texto": "b"}]})
        self.recusa({"acao": "roteiro", "passos": [{"texto": "body"}], "url": "https://esaj.tjsp.jus.br/"})
        self.recusa({"acao": "sondar", "url": "https://esaj.tjsp.jus.br/"})
        self.recusa({"acao": "abrir", "url": "https://esaj.tjsp.jus.br/", "texto": "sim"})
        self.recusa({"acao": "abrir", "url": "https://esaj.tjsp.jus.br/", "captura": 1})
        self.recusa({"acao": "executar"})
        self.recusa({})
        for intruso in ("sandbox", "grafico", "perfil", "comando", "argv", "variante", "alvo", "arquivos"):
            with self.subTest(intruso), self.assertRaises(J.Recusa):
                J.validar_pedido(pedido(acao="sondar", **{intruso: "x"}), "criador", "navegador")   # nem chega à carga

    def test_janela_login_so_nos_sites_de_login_e_captcha_so_na_lista(self):
        c = self.carga({"variante": "login", "alvo": "ESAJ.tjsp.jus.br"}, "navegador-janela")
        self.assertEqual(c, {"acao": "janela", "variante": "login", "url": "https://esaj.tjsp.jus.br/", "sandbox": True,
                             "grafico": "wayland"})
        c = self.carga({"variante": "captcha", "alvo": "https://www.tjsp.jus.br/consulta"}, "navegador-janela")
        self.assertEqual((c["variante"], c["url"]), ("captcha", "https://www.tjsp.jus.br/consulta"))
        for campos in ({"variante": "login", "alvo": "www.tjsp.jus.br"},            # está em dominios, mas não em logins
                       {"variante": "login", "alvo": "example.com"}, {"variante": "login"},
                       {"variante": "login", "alvo": "https://esaj.tjsp.jus.br/"},
                       {"variante": "captcha", "alvo": "https://example.com/"}, {"variante": "captcha"},
                       {"variante": "outra", "alvo": "esaj.tjsp.jus.br"}):
            with self.subTest(campos=campos):
                self.recusa(campos, "navegador-janela")
        sem_logins = copy.deepcopy(FICHA)
        sem_logins["navegador"]["logins"] = []
        with self.assertRaises(J.Recusa):
            self.carga({"variante": "login", "alvo": "esaj.tjsp.jus.br"}, "navegador-janela", ficha=sem_logins)

    def test_o_pedido_de_terminal_da_janela_pede_o_alvo(self):
        padrao = J.validar_pedido(None, "criador", "navegador-janela")
        with self.assertRaises(J.Recusa):
            J.carga_do_navegador(padrao, "navegador-janela", DOMINIOS, FICHA, MEDIDAS)


class OpcoesFixasDoCanario(unittest.TestCase):
    """M6: o que o canário decide entra como opção fixa; o padrão é a mais segura; a ficha e a sessão não escolhem."""

    def test_o_padrao_e_sandbox_proprio_ligado_e_wayland_pelo_socket(self):
        for rel in (None, {}, {"modos": {}}, {"modos": {"navegador": {"aprovado": True}}}, {"modos": {"navegador": []}}):
            self.assertEqual(J.medidas_do_modo(rel, "navegador"), {"sandbox_proprio": True, "grafico": "wayland-socket"})

    def test_so_o_canario_instalado_desliga_o_sandbox_proprio_e_so_com_recusado(self):
        rel = {"modos": {"navegador": {"medidas": {"userns_aninhado": "recusado"}},
                         "navegador-janela:login": {"medidas": {"userns_aninhado": "permitido", "grafico": "x11"}},
                         "navegador-janela:captcha": {"medidas": {"userns_aninhado": "talvez", "grafico": "wayland-fd"}}}}
        self.assertEqual(J.medidas_do_modo(rel, "navegador"), {"sandbox_proprio": False, "grafico": "wayland-socket"})
        self.assertEqual(J.medidas_do_modo(rel, "navegador-janela", "login"), {"sandbox_proprio": True, "grafico": "x11"})
        # valor desconhecido ou que esta versão não liga (wayland-fd pede closefrom_override na sudoers): o padrão
        self.assertEqual(J.medidas_do_modo(rel, "navegador-janela", "captcha"), {"sandbox_proprio": True, "grafico": "wayland-socket"})

    def test_o_x11_so_aparece_na_janela_e_o_wayland_padrao_e_o_socket_do_wslg(self):
        self.assertFalse(J.PERFIS["navegador"].grafico)
        self.assertTrue(J.PERFIS["navegador-janela"].grafico)
        self.assertEqual(J.GRAFICOS_ESCOLHIVEIS["wayland-socket"][1], {"tipo": "wayland-socket", "caminho": J.WAYLAND_DO_WSLG})
        self.assertEqual(set(J.GRAFICOS_ESCOLHIVEIS), {"wayland-socket", "x11"})
        with self.assertRaises(J.Recusa):                    # a sessão (modo navegador) nunca monta socket gráfico
            J.validar_grafico({"tipo": "x11", "caminho": J.X11_DO_WSLG}, J.PERFIS["navegador"])

    def test_o_userns_do_canario_e_lido_do_texto_que_o_proprio_canario_escreve(self):
        import ctypes
        for saiu, esperado in ((0, "permitido"), (1, "recusado")):       # o filho do canário saiu com 0 (criou) ou com 1
            with mock.patch.object(ctypes, "CDLL"), mock.patch.object(CANARIO.os, "fork", create=True, return_value=7),                     mock.patch.object(CANARIO.os, "waitpid", create=True, return_value=(7, 0)),                     mock.patch.object(CANARIO.os, "WIFEXITED", create=True, return_value=True),                     mock.patch.object(CANARIO.os, "WEXITSTATUS", create=True, return_value=saiu):
                item = CANARIO.prova_userns("anotar")        # a função REAL do canário: o texto lido é o que ela escreve
            self.assertTrue(item["motivo"].startswith(J.USERNS_PERMITIDO if esperado == "permitido" else J.USERNS_RECUSADO))
            self.assertEqual(J.medidas_dos_itens([item]), {"userns_aninhado": esperado})
        for nada in ([], None, "x", [{"id": "outro"}], [{"id": "userns", "motivo": 3}], [{"id": "userns", "motivo": "?"}]):
            self.assertEqual(J.medidas_dos_itens(nada), {})

    def test_sem_teto_de_espaco_virtual_no_navegador_e_com_teto_no_codex(self):
        nav = J.limites_do_modo(J.PERFIS["navegador"])
        self.assertGreater(nav["memoria_bytes"], 1 << 40)                       # o V8 reserva uma área virtual enorme
        self.assertEqual((nav["tempo_s"], nav["processos"]), (120, 1024))     # o Chromium sobe dezenas de threads (NPROC conta threads)
        self.assertEqual(J.limites_do_modo(J.PERFIS["codex-exec"])["processos"], 256)   # os outros modos não mudam
        self.assertEqual(J.limites_do_modo(J.PERFIS["codex-exec"])["memoria_bytes"], 2048 * 1024 * 1024)
        self.assertEqual(J.PERFIS["navegador"].memoria_mb, 4096)                # o desenho (§2.4) segue registrado

    def test_o_programa_do_navegador_roda_o_python_do_venv_sem_shell_e_sem_segredo(self):
        cfg = J.Config(programas="/usr/local/lib/fundacao-ia/jaula/1.7.11", usuario=None)
        carga = {"acao": "abrir", "url": "https://esaj.tjsp.jus.br/", "sandbox": True}
        comando, extras = J.argv_do_programa(cfg, "navegador", {}, J.PERFIS["navegador"], DOMINIOS, "/raiz", [], carga=carga)
        self.assertEqual(comando, [f"{cfg.programas}/navegador/venv/bin/python", "-I", "-B", f"{cfg.programas}/navegador.py",
                                   "jaula"])
        self.assertEqual(list(extras), ["FUNDACAO_CARGA"])          # a carga (URL, valor de preenchimento) vai pelo descritor
        self.assertEqual(json.loads(extras["FUNDACAO_CARGA"]), carga)
        self.assertNotIn("tjsp", " ".join(comando))

    def test_etc_e_um_tmpfs_proprio_so_leitura_no_fim_e_a_raiz_tambem(self):
        """Montar só arquivos dentro de /etc faria o bwrap criar a pasta na raiz temporária, gravável (visto no Ubuntu)."""
        cfg = J.Config(estado="/var/lib/fundacao-ia/jaula", programas="/usr/local/lib/fundacao-ia/jaula/1.7.11", usuario=None)
        fds = {d: 10 + i for i, d in enumerate(J.DADOS_GERADOS)}
        for modo, variante, como in (("navegador", None, None), ("navegador-janela", "captcha", None), ("codex-exec", None, None),
                                     ("codex-titular", None, None), ("canario", None, "navegador")):
            a = J.montar_argv(cfg, "criador", "pedido-nav-0001", J.perfil_do_modo(modo, variante, como), ["/x"], fds=fds,
                              existe=lambda p: True, sistema=[["ro-bind", "/usr", "/usr"]])
            with self.subTest(modo=modo):
                tmpfs = [i for i, x in enumerate(a) if x == "--tmpfs" and a[i + 1] == "/etc"]
                dentro = [i for i, x in enumerate(a) if x in ("--ro-bind", "--ro-bind-data") and a[i + 2].startswith("/etc/")]
                remonta = [i for i, x in enumerate(a) if x == "--remount-ro" and a[i + 1] == "/etc"]
                self.assertEqual((len(tmpfs), len(remonta)), (1, 1))
                self.assertTrue(dentro and tmpfs[0] < min(dentro) and max(dentro) < remonta[0])
                raiz = [i for i, x in enumerate(a) if x == "--remount-ro" and a[i + 1] == "/"]
                montagens = [i for i, x in enumerate(a[:a.index("--")]) if x.startswith("--") and x.endswith("bind")
                             or x in ("--tmpfs", "--bind-data", "--ro-bind-data")]
                self.assertEqual(len(raiz), 1)
                self.assertGreater(raiz[0], max(montagens))                     # depois de TODAS as montagens
                self.assertLess(raiz[0], a.index("--chdir"))

    def test_montagens_do_navegador_programas_perfil_e_nada_do_projeto(self):
        cfg = J.Config(estado="/var/lib/fundacao-ia/jaula", programas="/usr/local/lib/fundacao-ia/jaula/1.7.11", usuario=None)
        fds = {d: 10 + i for i, d in enumerate(J.DADOS_GERADOS)}
        sistema = [["ro-bind", "/usr", "/usr"]]
        for modo, variante in (("navegador", None), ("navegador-janela", "login"), ("navegador-janela", "captcha")):
            perfil = J.perfil_do_modo(modo, variante)
            grafico = {"tipo": "wayland-socket", "caminho": J.WAYLAND_DO_WSLG} if perfil.grafico else None
            a = J.montar_argv(cfg, "criador", "pedido-nav-0001", perfil, ["/x"], fds=fds, grafico=grafico, sistema=sistema,
                              existe=lambda p: True)
            with self.subTest(modo=modo, variante=variante):
                for programa in ("navegador.py", "gravacao_segura.py", "chromium-sem-disfarce", "navegador"):
                    destino = f"{cfg.programas}/{programa}"
                    i = a.index(destino)
                    self.assertEqual((a[i - 1], a[i], a[i + 1]), ("--ro-bind", destino, destino))
                self.assertNotIn("--disable-userns", a)                       # o sandbox próprio do Chromium precisa do aninhado
                self.assertNotIn("/trabalho/projeto", a)
                self.assertEqual("/home/jaula/perfil" in a, variante != "captcha")
                self.assertEqual("/run/jaula/wayland-0" in a, perfil.grafico)
                self.assertFalse([x for x in a if x.startswith("/mnt") and x != J.WAYLAND_DO_WSLG])


class _Entrar(unittest.TestCase):
    """A entrada fixa de ponta a ponta, com o proxy, o bwrap e os descritores falsos (nada roda no Linux)."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="jaula-nav-1711-")).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.estado_p = self.base / "estado" / "criador"
        self.perfil = self.estado_p / "navegador" / "perfil"
        self.perfil.mkdir(parents=True)
        (self.estado_p / "proxy").mkdir()
        for pasta in (self.estado_p, self.estado_p / "navegador", self.perfil):     # a entrada fixa exige 0700 (no Linux)
            os.chmod(pasta, 0o700)
        self.raiz = self.base / "raiz"
        self.projeto = self.raiz / "projects" / "criador"
        (self.projeto / "outputs").mkdir(parents=True)
        self.cfg = J.Config(bwrap="/usr/bin/bwrap", python="/usr/bin/python3", estado=str(self.base / "estado"),
                            programas=str(self.base / "prog"), etc=str(self.base / "etc"), usuario=None)
        self.relatorio = {"schema_version": J.ESQUEMA_RELATORIO_INSTALADO, "hashes": HASHES,
                          "modos": {c: {"aprovado": True} for c in ("navegador", "navegador-janela:login",
                                                                    "navegador-janela:captcha")}}
        self.rodadas, self.memfds = [], {}
        self.escreve = {}                    # o que a "jaula" grava em /trabalho/saida (nome -> bytes)
        self.segredos = [SEGREDO]            # o que o navegador.py guardaria no perfil privado
        self.stdout = b"{}"                  # o que o navegador.py imprime (a resposta que vai a sessao)
        ex = J._script("execucao_isolada")
        for alvo, novo in ((ex, ("_rodar", self.rodar_falso)), (J, ("subir_proxy", mock.Mock())), (J, ("parar_proxy", mock.Mock())),
                           (J, ("_resumo_do_proxy", mock.Mock(return_value={}))),
                           (J, ("_memfd", self.memfd_falso))):
            p = mock.patch.object(alvo, *novo)
            p.start()
            self.addCleanup(p.stop)

    def memfd_falso(self, nome, dados):
        self.memfds[nome] = dados
        return os.open(os.devnull, os.O_RDONLY)

    def carga_enviada(self) -> dict:
        """A carga que a jaula recebeu: pelo descritor `--args` (nunca pelo argv, que `ps` mostra a todos)."""
        partes = self.memfds["jaula-args"].split(b"\0")
        self.assertEqual(partes[:2], [b"--setenv", b"FUNDACAO_CARGA"])
        for argv in self.rodadas:
            self.assertNotIn("tjsp", " ".join(argv))
        return json.loads(partes[2].decode("utf-8"))

    def rodar_falso(self, argv, cwd, env, lim, pass_fds=()):
        self.rodadas.append(list(argv))
        saida = Path(argv[argv.index("/trabalho/saida") - 1])
        for nome, dados in self.escreve.items():
            (saida / nome).write_bytes(dados)
        if self.segredos is not None and "--bind" in argv:
            (self.perfil / J.ARQUIVO_DE_SEGREDOS).write_text(json.dumps(self.segredos), encoding="utf-8")
        return {"codigo": 0, "stdout": self.stdout, "stderr": b""}

    def entrar(self, modo, **campos):
        return J.entrar(self.cfg, "criador", modo, pedido(**campos), raiz=str(self.raiz), ficha=FICHA,
                        relatorio=self.relatorio, hoje=HOJE, hashes_atuais=HASHES)


class EntrarDoNavegador(_Entrar):
    def test_abrir_roda_a_carga_conferida_e_a_saida_volta_para_pasta_nova(self):
        self.escreve = {"resultado.json": b"{}", "captura.png": b"PNG"}
        r = self.entrar("navegador", acao="abrir", url="https://esaj.tjsp.jus.br/", captura=True)
        self.assertTrue(r["ok"], r)
        argv = self.rodadas[0]
        comando = argv[argv.index("--") + 1:]
        self.assertEqual(comando[-1], "jaula")                                   # ...o python do venv, -I -B, navegador.py, jaula
        carga = self.carga_enviada()
        self.assertEqual(carga, {"acao": "abrir", "sandbox": True, "url": "https://esaj.tjsp.jus.br/", "texto": False,
                                 "captura": True})
        self.assertEqual(sorted(c["arquivo"] for c in r["saida"]["copiados"]), ["captura.png", "resultado.json"])
        destino = self.projeto / "outputs" / "navegador" / "pedido-nav-0001"
        self.assertEqual(sorted(p.name for p in destino.iterdir()), ["captura.png", "resultado.json"])
        self.assertFalse((self.estado_p / "trabalho" / "pedido-nav-0001").exists())   # a pasta de trabalho some

    def test_n_nav_1_url_fora_da_lista_nao_chega_a_rodar_nem_a_criar_nada(self):
        with self.assertRaises(J.Recusa):
            self.entrar("navegador", acao="abrir", url="https://example.com/")
        self.assertEqual(self.rodadas, [])
        self.assertFalse((self.estado_p / "trabalho").exists())

    def test_n_nav_5_chave_do_windows_no_perfil_privado_recusa(self):
        import base64
        for campo, prefixo in (("encrypted_key", b"DPAPI"), ("app_bound_encrypted_key", b"APPB")):
            with self.subTest(campo):
                chave = base64.b64encode(prefixo + b"\x01\x00\x00\x00" + b"x" * 20).decode()
                (self.perfil / "Local State").write_text(json.dumps({"os_crypt": {campo: chave}}), encoding="utf-8")
                with self.assertRaises(J.Recusa) as r:
                    self.entrar("navegador", acao="sondar")
                self.assertIn("Windows", str(r.exception))
                self.assertEqual(self.rodadas, [])
        (self.perfil / "Local State").write_text(json.dumps({"os_crypt": {}}), encoding="utf-8")   # perfil do Linux: passa
        self.assertTrue(self.entrar("navegador", acao="sondar")["ok"])

    def test_n_nav_4b_nao_existe_importacao_do_perfil_do_windows(self):
        texto = (WSL / "jaula.py").read_text(encoding="utf-8") + (SCRIPTS / "navegador.py").read_text(encoding="utf-8")
        for ausente in ("Login Data", "importar_perfil", "copiar_perfil", "perfil_navegador_copiado"):
            self.assertNotIn(ausente, texto)
        self.assertNotIn("perfil", J.CAMPOS_POR_MODO["navegador"] | J.CAMPOS_POR_MODO["navegador-janela"])

    def test_saida_com_valor_de_cookie_do_perfil_nao_volta_para_o_projeto(self):
        self.escreve = {"resultado.json": b"{}", "vazou.txt": ("a=" + SEGREDO + ";").encode(), "limpo.txt": b"nada"}
        r = self.entrar("navegador", acao="abrir", url="https://esaj.tjsp.jus.br/")
        self.assertEqual(sorted(c["arquivo"] for c in r["saida"]["copiados"]), ["limpo.txt", "resultado.json"])
        self.assertEqual([x["arquivo"] for x in r["saida"]["recusados"]], ["vazou.txt"])
        self.assertNotIn(SEGREDO, json.dumps(r))
        self.assertFalse((self.projeto / "outputs" / "navegador" / "pedido-nav-0001" / "vazou.txt").exists())

    def test_f6_valor_de_cookie_na_saida_padrao_nao_volta_para_a_sessao(self):
        """Revisao de seguranca da 1.7.11, F6: a conferencia de segredo que a pasta de saida tem vale tambem para o texto que
        o navegador imprime e que a resposta leva a sessao (antes so o Codex a tinha)."""
        self.stdout = ('{"texto": "sessao=' + SEGREDO + '"}').encode()
        r = self.entrar("navegador", acao="abrir", url="https://esaj.tjsp.jus.br/", texto=True)
        self.assertEqual(r["stdout"], J.RETIDO)
        self.assertNotIn(SEGREDO, json.dumps(r))
        self.assertNotIn("aviso", r)                                  # o aviso de terceiros e do Codex
        self.stdout = b'{"texto": "pagina sem segredo"}'               # sem o valor, a resposta segue inteira
        r = J.entrar(self.cfg, "criador", "navegador", pedido(id="pedido-nav-0002", acao="abrir", url="https://esaj.tjsp.jus.br/"),
                     raiz=str(self.raiz), ficha=FICHA, relatorio=self.relatorio, hoje=HOJE, hashes_atuais=HASHES)
        self.assertIn("pagina sem segredo", r["stdout"])

    def test_sem_o_arquivo_de_segredos_a_saida_nao_volta(self):
        self.segredos = None
        self.escreve = {"resultado.json": b"{}"}
        self.stdout = b'{"texto": "nao da para conferir"}'
        r = self.entrar("navegador", acao="sondar")
        self.assertEqual(r["saida"]["copiados"], [])
        self.assertEqual((r["stdout"], r["stderr"]), (J.RETIDO, J.RETIDO))   # F6: sem como conferir, nada vai a sessao
        self.assertIn("segredos", r["saida"]["erro"])
        self.assertFalse((self.projeto / "outputs" / "navegador").exists())

    def test_n_nav_10_ligacao_plantada_em_outputs_nao_e_seguida(self):
        fora = self.base / "fora"
        fora.mkdir()
        (self.projeto / "outputs" / "navegador").mkdir()
        criar_ligacao_dir(self.projeto / "outputs" / "navegador" / "pedido-nav-0001", fora)
        self.escreve = {"resultado.json": b"{}"}
        r = self.entrar("navegador", acao="sondar")
        self.assertEqual(r["saida"]["copiados"], [])
        self.assertEqual(list(fora.iterdir()), [])

    def test_ligacao_na_saida_da_jaula_nao_e_copiada(self):
        saida_ruim = {"resultado.json": b"{}"}
        self.escreve = saida_ruim
        antigo = self.rodar_falso

        def com_ligacao(argv, cwd, env, lim, pass_fds=()):
            r = antigo(argv, cwd, env, lim, pass_fds)
            alvo = Path(argv[argv.index("/trabalho/saida") - 1])
            try:
                (alvo / "elo").symlink_to(self.base / "estado")
            except (OSError, NotImplementedError):
                self.skipTest("link simbólico indisponível neste ambiente")
            return r
        with mock.patch.object(J._script("execucao_isolada"), "_rodar", com_ligacao):
            r = self.entrar("navegador", acao="sondar")
        self.assertEqual([c["arquivo"] for c in r["saida"]["copiados"]], ["resultado.json"])
        self.assertEqual([x["arquivo"] for x in r["saida"]["recusados"]], ["elo"])

    def test_a_medida_de_recusado_gravada_pelo_root_desliga_o_sandbox_proprio(self):
        self.relatorio["modos"]["navegador"]["medidas"] = {"userns_aninhado": "recusado"}
        self.entrar("navegador", acao="sondar")
        self.assertIs(self.carga_enviada()["sandbox"], False)

    def test_a_janela_de_login_monta_o_socket_do_wslg_e_o_perfil_e_a_do_captcha_nao(self):
        r = self.entrar("navegador-janela", variante="login", alvo="esaj.tjsp.jus.br")
        self.assertTrue(r["ok"], r)
        argv = self.rodadas[0]
        i = argv.index(J.WAYLAND_DO_WSLG)
        self.assertEqual(argv[i - 1:i + 2], ["--ro-bind", J.WAYLAND_DO_WSLG, "/run/jaula/wayland-0"])
        self.assertIn("/home/jaula/perfil", argv)
        carga = self.carga_enviada()
        self.assertEqual((carga["acao"], carga["variante"], carga["url"], carga["grafico"]),
                         ("janela", "login", "https://esaj.tjsp.jus.br/", "wayland"))
        self.rodadas.clear()
        r = J.entrar(self.cfg, "criador", "navegador-janela", pedido(id="pedido-nav-0002", variante="captcha",
                                                                     alvo="https://www.tjsp.jus.br/x"),
                     raiz=str(self.raiz), ficha=FICHA, relatorio=self.relatorio, hoje=HOJE, hashes_atuais=HASHES)
        self.assertTrue(r["ok"], r)
        self.assertNotIn("/home/jaula/perfil", self.rodadas[0])               # perfil temporário
        self.assertEqual(r["saida"]["recusados"], [])

    def test_modo_navegador_nunca_monta_socket_grafico_mesmo_com_medida_x11(self):
        self.relatorio["modos"]["navegador"]["medidas"] = {"grafico": "x11"}
        self.entrar("navegador", acao="sondar")
        self.assertNotIn(J.X11_DO_WSLG, self.rodadas[0])
        self.assertNotIn(J.WAYLAND_DO_WSLG, self.rodadas[0])

    def test_sem_o_canario_aprovado_da_janela_ela_nao_abre(self):
        self.relatorio["modos"]["navegador-janela:login"]["aprovado"] = False
        with self.assertRaises(J.Recusa):
            self.entrar("navegador-janela", variante="login", alvo="esaj.tjsp.jus.br")
        self.assertEqual(self.rodadas, [])


class PlaywrightFalso:
    """O `playwright.sync_api` simulado: anota lançamentos e ações; o contexto fecha sozinho depois de `fecha_apos` esperas."""

    def __init__(self, cookies=(), fecha_apos=3):
        self.lancamentos, self.acoes, self.cookies, self.fecha_apos = [], [], list(cookies), fecha_apos
        self.falha_no_ir = False
        self.estado = {"cookies": [], "origins": []}              # o storage_state do contexto simulado

    def modulos(self) -> dict:
        falso = self

        class Pagina:
            url = "about:blank"

            def goto(self, url, **_kw):
                if falso.falha_no_ir:
                    raise RuntimeError("rede caiu")
                falso.acoes.append(("ir", url))
                self.url = url
                return types.SimpleNamespace(status=200)

            def title(self):
                return "Página fictícia"

            def inner_text(self, seletor, **_kw):
                return "texto visível"

            def screenshot(self, path, **_kw):
                Path(path).write_bytes(b"PNG")

            def evaluate(self, js):
                falso.acoes.append(("js", js))
                return True

            def content(self):
                return "<html>desafio resolvido pelo titular</html>"

        class Contexto:
            browser = types.SimpleNamespace(version="999.0 fictício")

            def __init__(self):
                self.pages, self.chamadas, self.ao_fechar, self.fechado = [], 0, [], False

            def new_page(self):
                self.pages.append(Pagina())
                return self.pages[-1]

            def set_default_timeout(self, ms):
                pass

            def cookies(self):
                if self.fechado:
                    raise RuntimeError("contexto fechado")
                return [{"name": f"c{i}", "value": v} for i, v in enumerate(falso.cookies)]

            def storage_state(self):
                if self.fechado:
                    raise RuntimeError("contexto fechado")
                return json.loads(json.dumps(falso.estado))

            def add_cookies(self, cookies):
                falso.acoes.append(("cookies", cookies))

            def on(self, evento, funcao):
                self.ao_fechar.append(funcao)

            def wait_for_event(self, evento, timeout=0):
                self.chamadas += 1
                if self.chamadas >= falso.fecha_apos:
                    self.fechado = True
                    for f in self.ao_fechar:
                        f()
                    return
                raise TimeoutError("sem fechar")

            def close(self):
                falso.acoes.append(("fechou",))

        class Chromium:
            def launch_persistent_context(self, pasta, **kw):
                falso.lancamentos.append((pasta, kw))
                return Contexto()

        class Gerente:
            chromium = Chromium()

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False
        pacote = types.ModuleType("playwright")
        api = types.ModuleType("playwright.sync_api")
        api.sync_playwright = lambda: Gerente()
        pacote.sync_api = api
        return {"playwright": pacote, "playwright.sync_api": api}


class NavegadorPyDentroDaJaula(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="nav-dentro-1711-")).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.perfil, self.saida = self.base / "perfil", self.base / "saida"
        self.falso = PlaywrightFalso(cookies=[SEGREDO, "curto"])
        for alvo, valor in (("PERFIL_DA_JAULA", str(self.perfil)), ("SAIDA_DA_JAULA", str(self.saida))):
            p = mock.patch.object(N, alvo, valor)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(sys.modules, self.falso.modulos())
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:3128", "NO_PROXY": ""})
        p.start()
        self.addCleanup(p.stop)

    def rodar(self, **carga):
        return N.executar_na_jaula(json.dumps(carga))

    def opcoes(self):
        return self.falso.lancamentos[-1][1]

    def test_o_chromium_e_o_involucro_com_o_perfil_fixo_e_as_opcoes_seguras(self):
        res, codigo = self.rodar(acao="abrir", url="https://esaj.tjsp.jus.br/", texto=True, captura=True)
        self.assertEqual(codigo, 0)
        pasta, kw = self.falso.lancamentos[0]
        self.assertEqual(pasta, str(self.perfil))
        self.assertEqual(Path(kw["executable_path"]).name, "chromium-sem-disfarce")
        self.assertIs(kw["chromium_sandbox"], True)                              # o padrão: sandbox próprio do Chromium LIGADO
        self.assertIs(kw["accept_downloads"], False)
        self.assertIs(kw["headless"], True)
        self.assertFalse({"user_agent", "color_scheme", "ignore_default_args", "env"} & set(kw))     # nada de disfarce nem de troca
        for arg in ("--disable-extensions", "--disable-sync", "--no-first-run", "--password-store=basic"):
            self.assertIn(arg, kw["args"])
        self.assertTrue([a for a in kw["args"] if a.startswith("--disable-features=") and "EncryptedClientHello" in a])
        self.assertEqual(kw["proxy"], {"server": "http://127.0.0.1:3128"})
        self.assertFalse([a for a in kw["args"] if "AutomationControlled" in a or "--no-sandbox" in a])
        self.assertEqual((res["url"], res["texto"]), ("https://esaj.tjsp.jus.br/", "texto visível"))
        self.assertEqual((self.saida / "captura.png").read_bytes(), b"PNG")
        self.assertEqual(json.loads((self.saida / "resultado.json").read_text(encoding="utf-8"))["url"], res["url"])

    def test_sandbox_falso_vira_chromium_sandbox_falso_e_o_preenchimento_automatico_fica_desligado(self):
        self.rodar(acao="abrir", url="https://esaj.tjsp.jus.br/", sandbox=False)
        self.assertIs(self.opcoes()["chromium_sandbox"], False)
        prefs = json.loads((self.perfil / "Default" / "Preferences").read_text(encoding="utf-8"))
        self.assertIs(prefs["autofill"]["profile_enabled"], False)
        self.assertIs(prefs["autofill"]["credit_card_enabled"], False)
        self.assertIs(prefs["credentials_enable_service"], False)
        (self.perfil / "Default" / "Preferences").write_text(json.dumps({"autofill": {"outro": 1}, "x": 2}), encoding="utf-8")
        N.gravar_preferencias(self.perfil)                                       # mescla, não apaga
        prefs = json.loads((self.perfil / "Default" / "Preferences").read_text(encoding="utf-8"))
        self.assertEqual((prefs["x"], prefs["autofill"]["outro"], prefs["autofill"]["profile_enabled"]), (2, 1, False))

    def test_os_valores_de_cookie_de_20_caracteres_ou_mais_ficam_no_perfil_privado(self):
        self.rodar(acao="sondar")
        arquivo = self.perfil / N.ARQUIVO_DE_SEGREDOS
        self.assertEqual(json.loads(arquivo.read_text(encoding="utf-8")), [SEGREDO])
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(arquivo.stat().st_mode), 0o600)
        self.falso.cookies = []                                                  # a próxima execução soma, não perde
        self.rodar(acao="sondar")
        self.assertEqual(json.loads(arquivo.read_text(encoding="utf-8")), [SEGREDO])
        self.assertEqual(N.ARQUIVO_DE_SEGREDOS, J.ARQUIVO_DE_SEGREDOS)           # o programa e a entrada fixa combinam o nome
        self.assertEqual(N.TAMANHO_DE_SEGREDO, J.TAMANHO_SEGREDO_MINIMO)

    def test_o_cookie_entra_na_conferencia_ja_na_largada_mesmo_se_o_pedido_morre(self):
        self.falso.falha_no_ir = True
        with self.assertRaises(RuntimeError):
            self.rodar(acao="abrir", url="https://esaj.tjsp.jus.br/")
        self.assertEqual(json.loads((self.perfil / N.ARQUIVO_DE_SEGREDOS).read_text(encoding="utf-8")), [SEGREDO])

    def test_o_login_da_janela_sobrevive_a_ela_com_o_cookie_de_sessao_e_a_sessao_o_carrega(self):
        sessao = "-".join(("sessao", "ficticia", "0123456789", "ABCDEFGHIJ"))     # cookie de sessão: sem validade (expires -1)
        self.falso.estado = {"cookies": [{"name": "JSESSIONID", "value": sessao, "domain": "esaj.tjsp.jus.br", "path": "/",
                                          "expires": -1}], "origins": []}
        self.falso.cookies = []                                  # o perfil do Chromium não guardou o cookie de sessão
        self.rodar(acao="janela", variante="login", url="https://esaj.tjsp.jus.br/", grafico="wayland")   # o contexto já fechou
        arquivo = self.perfil / N.ARQUIVO_DE_ESTADO
        self.assertEqual(json.loads(arquivo.read_text(encoding="utf-8"))["cookies"][0]["value"], sessao)
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(arquivo.stat().st_mode), 0o600)
        self.assertIn(sessao, json.loads((self.perfil / N.ARQUIVO_DE_SEGREDOS).read_text(encoding="utf-8")))
        self.falso.acoes.clear()
        self.falso.estado = {"cookies": [], "origins": []}       # a sessão abre um contexto novo, sem o cookie
        self.rodar(acao="abrir", url="https://esaj.tjsp.jus.br/cpopg")
        carregados = next(a[1] for a in self.falso.acoes if a[0] == "cookies")
        self.assertEqual(carregados[0]["name"], "JSESSIONID")
        self.assertEqual(N.ARQUIVO_DE_ESTADO, J.ARQUIVO_DE_ESTADO)

    def test_o_estado_do_navegador_nunca_volta_para_o_projeto(self):
        sessao = "-".join(("sessao", "ficticia", "0123456789", "ABCDEFGHIJ"))
        self.falso.estado = {"cookies": [{"name": "s", "value": sessao, "domain": "a.org", "path": "/", "expires": -1}],
                             "origins": []}
        self.rodar(acao="janela", variante="login", url="https://esaj.tjsp.jus.br/")
        segredos = J.segredos_do_perfil(str(self.perfil))
        self.assertIn(sessao, segredos)
        saida, projeto = self.base / "saida-do-pedido", self.base / "projeto"
        saida.mkdir()
        projeto.mkdir()
        (saida / "estado.json").write_bytes((self.perfil / N.ARQUIVO_DE_ESTADO).read_bytes())    # o estado inteiro, copiado
        (saida / "so-o-valor.txt").write_text("x=" + sessao, encoding="utf-8")
        (saida / "limpo.txt").write_text("nada", encoding="utf-8")
        (saida / J.ARQUIVO_DE_ESTADO).write_text("{}", encoding="utf-8")                          # nem pelo nome
        r = J.copiar_volta(str(saida), str(projeto), "outputs/navegador/pedido-nav-0003", segredos=segredos)
        self.assertEqual([c["arquivo"] for c in r["copiados"]], ["limpo.txt"])
        self.assertEqual(sorted(x["arquivo"] for x in r["recusados"]),
                         sorted([J.ARQUIVO_DE_ESTADO, "estado.json", "so-o-valor.txt"]))
        for passo in ({"estado": "x"}, {"storage_state": "x"}, {"cookies": "x"}):           # nenhum passo lê o estado
            with self.assertRaises(N.Recusa):
                N.validar_passos([passo], em_jaula=True)

    def test_navegador_morto_nao_prende_a_espera_da_janela(self):
        self.falso.fecha_apos = 10 ** 6                      # a espera falha na hora, sempre: nunca "fecha"
        res, _ = self.rodar(acao="janela", variante="captcha", url="https://esaj.tjsp.jus.br/")
        self.assertEqual(res["pagina_salva"]["arquivo"], "pagina.html")

    def test_sondar_diz_que_o_webdriver_e_verdadeiro_e_so_abre_about_blank(self):
        res, codigo = self.rodar(acao="sondar", sandbox=True)
        self.assertEqual((codigo, res["webdriver"], res["sandbox_proprio"], res["versao"]), (0, True, True, "999.0 fictício"))
        self.assertEqual([a for a in self.falso.acoes if a[0] == "ir"], [("ir", "about:blank")])

    def test_roteiro_grava_as_capturas_so_na_saida_da_jaula(self):
        res, codigo = self.rodar(acao="roteiro", passos=[{"ir": "https://esaj.tjsp.jus.br/"}, {"captura": "p1.png"}])
        self.assertEqual(codigo, 0)
        self.assertEqual((self.saida / "p1.png").read_bytes(), b"PNG")
        self.assertEqual(res["resultados"][1]["captura"], str(self.saida / "p1.png"))
        with self.assertRaises(N.Recusa):
            self.rodar(acao="roteiro", passos=[{"captura": "../fora.png"}])
        with self.assertRaises(N.Recusa):
            self.rodar(acao="roteiro", passos=[{"js": "1"}])

    def test_a_janela_do_captcha_guarda_a_ultima_pagina_e_a_do_login_nao_guarda_nada(self):
        res, _ = self.rodar(acao="janela", variante="captcha", url="https://esaj.tjsp.jus.br/", grafico="wayland")
        kw = self.opcoes()
        self.assertIs(kw["headless"], False)
        self.assertIn("--ozone-platform=wayland", kw["args"])
        self.assertEqual(res["pagina_salva"]["arquivo"], "pagina.html")
        self.assertIn("desafio resolvido pelo titular", (self.saida / "pagina.html").read_text(encoding="utf-8"))
        # a ferramenta só ESPERA: nenhuma ação de clique, preenchimento ou script sobre o desafio
        self.assertEqual([a[0] for a in self.falso.acoes if a[0] not in ("ir", "fechou")], [])
        shutil.rmtree(self.saida)
        res, _ = self.rodar(acao="janela", variante="login", url="https://esaj.tjsp.jus.br/", grafico="x11")
        self.assertIn("--ozone-platform=x11", self.opcoes()["args"])
        self.assertIsNone(res["pagina_salva"])
        self.assertFalse((self.saida / "pagina.html").exists())

    def test_carga_fora_do_esquema_e_recusada_e_o_main_devolve_2(self):
        for ruim in ("{", "[]", json.dumps({"acao": "outra"}), json.dumps({"acao": "sondar", "perfil": "/x"}),
                     json.dumps({"url": "https://a.org"})):
            with self.subTest(ruim), self.assertRaises(N.Recusa):
                N.ler_carga_da_jaula(ruim)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(N.main(["jaula", json.dumps({"acao": "outra"})]), 2)
        with contextlib.redirect_stdout(io.StringIO()) as saida:
            self.assertEqual(N.main(["jaula", json.dumps({"acao": "sondar"})]), 0)
        self.assertTrue(json.loads(saida.getvalue())["webdriver"])

    def test_sem_playwright_ou_sem_chromium_a_mensagem_e_do_titular_sem_sudo(self):
        with mock.patch.dict(sys.modules, {"playwright": None, "playwright.sync_api": None}), \
                self.assertRaises(N.NaoInstalado) as r:
            self.rodar(acao="sondar")
        self.assertEqual(str(r.exception), N.SEM_PLAYWRIGHT_NA_JAULA)
        erro = self.falso.modulos()
        gerente = erro["playwright.sync_api"].sync_playwright()
        gerente.chromium.launch_persistent_context = mock.Mock(side_effect=RuntimeError("Executable doesn't exist at /x"))
        erro["playwright.sync_api"].sync_playwright = lambda: gerente
        with mock.patch.dict(sys.modules, erro), self.assertRaises(N.NaoInstalado) as r:
            self.rodar(acao="sondar")
        self.assertEqual(str(r.exception), N.SEM_CHROMIUM_NA_JAULA)
        for texto in (N.SEM_PLAYWRIGHT_NA_JAULA, N.SEM_CHROMIUM_NA_JAULA):
            self.assertNotIn("sudo", texto.lower())

    def test_chave_do_windows_so_com_dpapi_ou_app_bound(self):
        import base64
        self.assertIsNone(N.chave_do_windows(self.perfil))                      # perfil novo, sem Local State
        self.perfil.mkdir()
        (self.perfil / "Local State").write_text(json.dumps({"os_crypt": {"encrypted_key": base64.b64encode(b"DPAPI" + b"x" * 9).decode()}}),
                                                 encoding="utf-8")
        self.assertIn("DPAPI", N.chave_do_windows(self.perfil))
        (self.perfil / "Local State").write_text("{}", encoding="utf-8")
        self.assertIsNone(N.chave_do_windows(self.perfil))
        (self.perfil / "Local State").write_text("não é json", encoding="utf-8")
        self.assertIsNone(N.chave_do_windows(self.perfil))


class PreparoDoNavegador(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = carregar_preparo()
        cls.pj = cls.m.preparo_jaula()

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="preparo-nav-1711-")).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        (self.base / "jaula-ensaio").mkdir()
        self.caminhos = self.pj.caminhos_de_ensaio(self.base / "jaula-ensaio", self.base / "area")
        Path(self.caminhos.bwrap).write_bytes(b"bwrap de ensaio\n")

    # --- o arquivo de travas ------------------------------------------------------------------------------------
    def test_o_arquivo_de_travas_da_skill_tem_nome_versao_e_sha256_de_cada_pacote(self):
        travas = self.pj.travas_do_lock(SKILL)
        self.assertEqual([r for r, _h in travas], ["playwright==1.64.1", "pyee==14.0.0", "greenlet==3.5.6",
                                                   "typing_extensions==4.16.0"])
        self.assertTrue(all(re.fullmatch("[0-9a-f]{64}", h) for _r, h in travas))
        self.assertEqual(len({h for _r, h in travas}), 4)
        texto = (WSL / "jaula-navegador.lock").read_text(encoding="utf-8")
        self.assertIn("Chromium NÃO tem hash", texto)          # a confiança no primeiro uso é só da árvore do Chromium
        self.assertIn("confiança no primeiro uso", texto)
        self.assertIn("1248", texto)
        self.assertIn("156.0.8078.4", texto)
        self.assertEqual(self.pj.texto_das_travas(travas).count("--hash=sha256:"), 4)

    def test_travas_sem_hash_com_opcao_do_pip_url_ou_repeticao_sao_recusadas(self):
        h = "a" * 64
        for ruim in ("playwright==1.0.0", f"--index-url https://outro.org/simple\nplaywright==1.0.0 --hash=sha256:{h}",
                     f"-r outro.txt\nplaywright==1.0.0 --hash=sha256:{h}", f"playwright @ https://a.org/x.whl --hash=sha256:{h}",
                     f"playwright>=1.0 --hash=sha256:{h}", f"playwright==1.0.0 --hash=sha256:{h} --hash=sha256:{'b' * 64}",
                     f"playwright==1.0.0 --hash=sha256:{h} --index-url=https://x", "playwright==1.0.0 --hash=sha256:" + "A" * 64,
                     "playwright==1.0.0 --hash=sha256:" + "a" * 63, f"pyee==1.0.0 --hash=sha256:{h}",
                     f"playwright==1.0.0 --hash=sha256:{h}\nPlaywright==2.0.0 --hash=sha256:{h}", ""):
            with self.subTest(ruim[:40]), tempfile.TemporaryDirectory() as d:
                destino = Path(d) / self.pj.LOCK_DO_NAVEGADOR
                destino.parent.mkdir(parents=True)
                destino.write_text(ruim, encoding="utf-8")
                with self.assertRaises(self.m.EntradaInvalida):
                    self.pj.travas_do_lock(d)

    # --- os downloads, com comandos falsos -----------------------------------------------------------------------
    def plano(self, preparar=True):
        return {"necessaria": True, "navegador": preparar}

    def instalar(self, rodar, **kw):
        return self.pj.instalar_navegador_jaula(SKILL, self.caminhos, self.plano(), rodar=rodar, **kw)

    def falso(self, pip_falha=False):
        chamadas = []
        base = Path(self.caminhos.programas) / "navegador"

        def rodar(argv):
            chamadas.append(list(argv))
            if pip_falha and "pip" in argv:
                return 1, "hash diferente"
            if argv[-2:] == ["venv", (base / "venv").as_posix()]:
                (base / "venv" / "bin").mkdir(parents=True)
                (base / "venv" / "bin" / "python").write_bytes(b"py")
            elif argv[-2:] == ["install", "chromium"]:
                pasta = base / "ms-playwright" / "chromium-1248" / "chrome-linux"
                pasta.mkdir(parents=True)
                (pasta / "chrome").write_bytes(b"chrome ficticio")
            return 0, ""
        return rodar, chamadas

    def test_a_instalacao_usa_so_o_pip_com_hashes_das_travas_e_registra_so_a_arvore_do_chromium(self):
        rodar, chamadas = self.falso()
        res = self.instalar(rodar)
        self.assertIn("update -q", " ".join(chamadas[0]))
        install = next(c for c in chamadas if "apt-get" in " ".join(c) and "install" in c)
        pacotes = install[install.index("install") + 2:]
        self.assertEqual(pacotes[:-1], list(self.pj._script("navegador").PACOTES_DO_SISTEMA))
        self.assertEqual(pacotes[-1], "acl")
        self.assertFalse([c for c in chamadas if "download" in c])                  # nada de pip download nem de pino do pip
        pip = next(c for c in chamadas if "pip" in c and "install" in c)
        self.assertEqual(pip[pip.index("install"):pip.index("-r")], ["install", "--require-hashes", "--no-deps", "--only-binary",
                                                                     ":all:", "--no-input"])
        self.assertNotIn("--no-index", pip)
        base = Path(self.caminhos.programas) / "navegador"
        self.assertEqual(pip[pip.index("-r") + 1], (base / "travas-com-hashes.txt").as_posix())
        self.assertEqual(pip[:2], ["/usr/bin/env", "-i"])                           # ambiente limpo, sem configuração do pip
        self.assertIn("PIP_CONFIG_FILE=/dev/null", pip)
        self.assertEqual((base / "travas-com-hashes.txt").read_text(encoding="utf-8"),
                         self.pj.texto_das_travas(self.pj.travas_do_lock(SKILL)))   # o arquivo é o das travas da skill
        playwright = next(c for c in chamadas if c[-2:] == ["install", "chromium"])
        self.assertTrue(any(a.startswith("PLAYWRIGHT_BROWSERS_PATH=") for a in playwright))
        pins = json.loads((base / "pins-navegador.json").read_text(encoding="utf-8"))
        self.assertEqual(set(pins), {"schema_version", "rotulo", "chromium"})       # o pip não tem pino: tem hash na trava
        self.assertEqual(pins["schema_version"], self.pj.ESQUEMA_PINS)
        for trecho in ("confiança no primeiro uso", "1248", "156.0.8078.4", "chromium-headless-shell"):
            self.assertIn(trecho, pins["rotulo"])
        self.assertEqual(pins["chromium"]["pasta"], "chromium-1248")
        self.assertRegex(pins["chromium"]["arvore_sha256"], "^[0-9a-f]{64}$")
        self.assertTrue(res["necessaria"])

    def test_a_segunda_vez_nao_baixa_o_chromium_de_novo_e_o_pip_segue_com_hashes(self):
        rodar, chamadas = self.falso()
        self.instalar(rodar)
        chamadas.clear()
        self.instalar(rodar)
        self.assertFalse([c for c in chamadas if c[-2:] == ["install", "chromium"]])
        self.assertTrue([c for c in chamadas if "--require-hashes" in c])

    def test_chromium_diferente_do_pino_para_tudo(self):
        rodar, _ = self.falso()
        self.instalar(rodar)
        (Path(self.caminhos.programas) / "navegador" / "ms-playwright" / "chromium-1248" / "chrome-linux" / "chrome").write_bytes(b"outro")
        with self.assertRaises(self.m.EntradaInvalida) as r:
            self.instalar(rodar)
        self.assertIn("difere do pino", str(r.exception))

    def test_pip_que_recusa_o_hash_ou_comando_que_falha_para_antes_do_chromium(self):
        rodar, chamadas = self.falso(pip_falha=True)
        with self.assertRaises(self.m.EntradaInvalida) as r:
            self.instalar(rodar)
        self.assertIn("falhou", str(r.exception))
        self.assertFalse([c for c in chamadas if c[-2:] == ["install", "chromium"]])
        self.assertFalse((Path(self.caminhos.programas) / "navegador" / "pins-navegador.json").exists())
        with self.assertRaises(self.m.EntradaInvalida):
            self.instalar(lambda argv: (100, "sem rede"))

    def test_so_com_a_secao_ou_com_preparar_e_o_ensaio_nunca_baixa_de_verdade(self):
        self.assertEqual(self.pj.instalar_navegador_jaula(SKILL, self.caminhos, {"necessaria": True, "navegador": False}),
                         {"acoes": [], "necessaria": False})
        simulado = self.pj.instalar_navegador_jaula(SKILL, self.caminhos, self.plano(), simular=True)
        self.assertFalse((Path(self.caminhos.programas) / "navegador").exists())
        texto = "\n".join(self.pj.texto_do_navegador(simulado))
        for endereco in ("pypi.org", "files.pythonhosted.org", "https://cdn.playwright.dev/dbazure/download/playwright",
                         "https://playwright.download.prss.microsoft.com/dbazure/download/playwright", "49,2 MB",
                         "48.471.931", "ESTIMADO", "1248", "156.0.8078.4", "playwright==1.64.1"):
            self.assertIn(endereco, texto)
        with self.assertRaises(self.m.EntradaInvalida) as r:                         # ensaio sem comando falso: não baixa
            self.pj.instalar_navegador_jaula(SKILL, self.caminhos, self.plano())
        self.assertIn("nunca baixa", str(r.exception))
        with self.assertRaises(self.m.EntradaInvalida):                              # sem ensaio e sem root
            self.pj.instalar_navegador_jaula(SKILL, self.pj.Caminhos(**{**self.caminhos._asdict(), "ensaio": False}),
                                             self.plano(), rodar=lambda a: (0, ""))

    # --- o lançador do titular ------------------------------------------------------------------------------------
    def lancador(self, grafico="wayland-socket", projeto="criador"):
        texto = self.pj.texto_do_lancador(projeto, "/usr/local/lib/fundacao-ia/jaula/1.7.11", grafico)
        ns = {"__name__": "lancador"}
        exec(compile(texto, "abrir-navegador", "exec"), ns)
        return texto, ns

    def test_o_lancador_tem_so_valores_fixos_e_monta_o_pedido_fechado(self):
        texto, ns = self.lancador()
        self.assertNotIn("{{", texto)
        self.assertIn(self.pj.MARCA_DO_LANCADOR, texto)
        self.assertEqual((ns["PROJETO"], ns["USUARIO_DA_JAULA"], ns["GRAFICO"], ns["WAYLAND"]),
                         ("criador", "fundacao-jaula", "wayland-socket", J.WAYLAND_DO_WSLG))
        p = ns["montar_pedido"](["login", "esaj.tjsp.jus.br"])
        self.assertEqual(set(p), {"schema_version", "id", "variante", "alvo"})
        J.validar_pedido(json.dumps(p).encode(), "criador", "navegador-janela")   # a entrada fixa aceita o pedido
        for ruim in ([], ["login"], ["abrir", "x"], ["login", ""], ["login", "a", "b"], ["login", "x" * 2001]):
            with self.subTest(ruim), self.assertRaises(SystemExit):
                ns["montar_pedido"](ruim)

    def test_o_lancador_chama_so_o_sudo_com_o_argv_fixo_e_poe_e_tira_a_acl(self):
        _, ns = self.lancador()
        chamadas = []

        def run(args, **kw):
            chamadas.append((list(args), kw))
            return types.SimpleNamespace(returncode=0, stdout=json.dumps({"ok": True, "saida": {"destino": "outputs/navegador/t"}}).encode())
        ns["subprocess"] = types.SimpleNamespace(run=run, DEVNULL=-3, PIPE=-1, SubprocessError=Exception)
        ns["os"] = types.SimpleNamespace(path=os.path, environ={"TERM": "xterm"}, geteuid=lambda: 1000)
        with contextlib.redirect_stdout(io.StringIO()) as saida:
            self.assertEqual(ns["main"](["captcha", "https://www.tjsp.jus.br/x"]), 0)
        argvs = [c[0] for c in chamadas]
        self.assertEqual([a[:2] for a in argvs[:2]], [["/usr/bin/setfacl", "-m"]] * 2)
        sudo = argvs[2]
        self.assertEqual(sudo[:5], ["/usr/bin/sudo", "-u", "fundacao-jaula", "--", "/usr/local/lib/fundacao-ia/jaula/1.7.11/jaula-entrar"])
        self.assertEqual(sudo[5:], ["criador", "navegador-janela"])
        corpo = json.loads(chamadas[2][1]["input"])
        self.assertEqual((corpo["variante"], corpo["alvo"]), ("captcha", "https://www.tjsp.jus.br/x"))
        self.assertEqual([a[:2] for a in argvs[3:]], [["/usr/bin/setfacl", "-x"]] * 2)     # a ACL sai ao fechar a janela
        self.assertIn("pagina.html", saida.getvalue())

    def test_a_acl_sai_mesmo_se_a_jaula_falha_e_o_x11_nao_usa_acl(self):
        _, ns = self.lancador()
        chamadas = []

        def run(args, **kw):
            chamadas.append(list(args))
            if args[0].endswith("sudo"):
                raise OSError("sem sudo")
            return types.SimpleNamespace(returncode=0, stdout=b"")
        ns["subprocess"] = types.SimpleNamespace(run=run, DEVNULL=-3, PIPE=-1, SubprocessError=Exception)
        ns["os"] = types.SimpleNamespace(path=os.path, environ={}, geteuid=lambda: 1000)
        with self.assertRaises(OSError):
            ns["main"](["login", "esaj.tjsp.jus.br"])
        self.assertEqual([c[1] for c in chamadas if c[0].endswith("setfacl")], ["-m", "-m", "-x", "-x"])
        _, x11 = self.lancador("x11")
        chamadas.clear()
        x11["subprocess"], x11["os"] = ns["subprocess"], ns["os"]
        with contextlib.suppress(OSError):
            x11["main"](["login", "esaj.tjsp.jus.br"])
        self.assertFalse([c for c in chamadas if c[0].endswith("setfacl")])

    def test_o_lancador_recusa_valor_que_vira_codigo(self):
        for projeto in ("Ruim", "a--b", "x'; import os #", "../x"):
            with self.subTest(projeto), self.assertRaises(self.m.EntradaInvalida):
                self.pj.texto_do_lancador(projeto, "/usr/local/lib/x", "wayland-socket")
        for programas in ("/usr/local/lib/x'y", "/usr/local/lib/x\\y", "/usr/local/lib/x\ny"):
            with self.subTest(programas), self.assertRaises(self.m.EntradaInvalida):
                self.pj.texto_do_lancador("criador", programas, "wayland-socket")
        with self.assertRaises(self.m.EntradaInvalida):
            self.pj.texto_do_lancador("criador", "/usr/local/lib/x", "wayland-fd")

    # --- o plano e a instalação da jaula com o navegador ------------------------------------------------------------
    def area(self):
        ab = ficha_aplicada(self.m, navegador=SECAO_NAVEGADOR, outras_llm=secao_codex())
        gravar_area(self.base, self.m, ab, self.caminhos)
        return ab

    def aprovar(self, plano, medidas=None, aprovados=("navegador", "navegador-janela:login", "navegador-janela:captcha")):
        rel = {"schema_version": self.pj.jaula().ESQUEMA_RELATORIO_INSTALADO, "hashes": plano["hashes_previstos"],
               "modos": {c: {"aprovado": True, **({"medidas": medidas} if medidas else {})} for c in aprovados}}
        destino = Path(self.caminhos.etc) / self.pj.jaula().RELATORIO_INSTALADO
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(rel), encoding="utf-8")

    def montar(self):
        return self.pj.montar_plano(SKILL, self.base / "area", ["caso-real"], USUARIO_DO_ENSAIO, self.caminhos)

    def test_o_lancador_so_existe_com_o_canario_aprovado_e_entra_com_o_plano_e_o_instalar(self):
        self.area()
        plano = self.montar()
        self.assertEqual([(l["abrir"], l["texto"]) for l in plano["lancadores"]], [(False, "")])
        self.assertTrue(plano["navegador"])
        self.assertIn("pypi.org", "\n".join(self.pj.texto_do_plano(plano)))
        res = self.pj.instalar_jaula(plano, rodar=VisudoFalso())
        lancador = Path(self.caminhos.bin) / "abrir-navegador-caso-real"
        self.assertFalse(lancador.exists())                                         # sem canário, sem lançador
        self.assertEqual([a["acao"] for a in res["acoes"] if a["item"].startswith("lancador")], ["igual"])
        self.aprovar(plano)
        plano = self.montar()
        res = self.pj.instalar_jaula(plano, rodar=VisudoFalso())
        self.assertEqual([a["acao"] for a in res["acoes"] if a["item"].startswith("lancador")], ["criar"])
        self.assertEqual(lancador.read_text(encoding="utf-8"), plano["lancadores"][0]["texto"])
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(lancador.stat().st_mode), 0o755)
        self.assertIn(("caso-real", "navegador-janela"), plano["pares"])
        res = self.pj.instalar_jaula(self.montar(), rodar=VisudoFalso())
        self.assertEqual([a["acao"] for a in res["acoes"] if a["item"].startswith("lancador")], ["igual"])
        # o canário revogado tira o lançador; arquivo que não é do preparo fica
        self.aprovar(plano, aprovados=("navegador",))
        res = self.pj.instalar_jaula(self.montar(), rodar=VisudoFalso())
        self.assertEqual([a["acao"] for a in res["acoes"] if a["item"].startswith("lancador")], ["remover"])
        lancador.write_text("#!/bin/sh\necho meu\n", encoding="utf-8")
        self.pj.instalar_jaula(self.montar(), rodar=VisudoFalso())
        self.assertTrue(lancador.exists())

    def test_a_medida_do_canario_vai_para_o_relatorio_instalado_e_para_o_lancador(self):
        itens = [{"id": i, "aprovado": True, "motivo": "ok", "informativo": False} for i in self.pj.ITENS_DO_CANARIO]
        for item in itens:
            if item["id"] == "userns":
                item["motivo"] = "namespace de usuário aninhado recusado"
        j = self.pj.jaula()
        resposta = {"schema_version": j.ESQUEMA_RESPOSTA, "modo": "canario", "como": "navegador", "id": "x-12345678",
                    "ok": True, "hashes": HASHES, "relatorio": {"schema_version": j.ESQUEMA_RELATORIO, "como": "navegador",
                                                                 "itens": itens, "gerado_em": "2026-11-08", "aprovado": True}}
        r = self.pj.classificar_resposta_do_canario(json.dumps(resposta).encode(), HASHES)
        self.assertEqual((r["chave"], r["aprovado"], r["medidas"]), ("navegador", True, {"userns_aninhado": "recusado"}))
        codex = {**resposta, "como": "codex-exec", "relatorio": {**resposta["relatorio"], "como": "codex-exec",
                                                                  "itens": itens + [{"id": i, "aprovado": True, "motivo": "ok", "informativo": True}
                                                                                    for i in (self.pj.ITEM_DO_CODEX, self.pj.ITEM_M7_DO_CODEX)]}}
        self.assertEqual(self.pj.classificar_resposta_do_canario(json.dumps(codex).encode(), HASHES)["medidas"], {})

    def test_perfil_navegador_copiado_e_recusado_citando_a_escolha_do_titular(self):
        resultado = {"projeto": "caso-real", "valida": True, "versao": 2, "arquivo": "/area/ficha/ficha-v2.json",
                     "sha256": "a" * 64, "sig_sha256": "b" * 64,
                     "ficha": ficha_de_ensaio("caso-real", 2, perfil_navegador_copiado={
                         "origem": "data/x_browser_profile", "manifesto_sha256": "a" * 64})}
        ab = self.m.aberturas_da_ficha(resultado, "caso-real")
        self.assertFalse(ab["valida"])                                  # o preparo não aplica nem importa o perfil do Windows
        for trecho in ("perfil_navegador_copiado", "08/11/2026", "perfil novo", "janela do navegador", "não copia nem importa"):
            self.assertIn(trecho, ab["motivo"])

    def test_o_passo_6b_do_preparar_wsl_so_chama_o_ajudante_e_o_ensaio_nunca_baixa(self):
        texto = (WSL / "preparar-wsl.sh").read_text(encoding="utf-8")
        passo = texto[texto.index("# 6b. O navegador da jaula"):texto.index("if [ ${#CANARIOS_JAULA[@]} -gt 0 ]; then\n          saida=$(chama_jaula instalar-canario-jaula")]
        codigo = " ".join(l.strip() for l in passo.splitlines() if not l.lstrip().startswith("#"))
        for baixa in ("apt-get", "pip ", "curl", "wget", "playwright install", "npm "):
            self.assertNotIn(baixa, codigo)
        self.assertIn('instalar-navegador-jaula "${args_jaula[@]}" --simular --texto', codigo)       # o plano vem antes
        self.assertLess(codigo.index("--simular"), codigo.index("chama_jaula instalar-navegador-jaula"))
        self.assertIn('elif [ "$ENSAIO" = 1 ]', codigo)
        self.assertIn("nada é baixado", codigo)


@unittest.skipUnless(sys.platform.startswith("linux"), "o invólucro e a caixa são do Linux")
class NavegadorNaJaulaLinux(unittest.TestCase):
    """L: o invólucro de verdade, o programa montado no bubblewrap e o Chromium real (pulam com o motivo)."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="jaula-nav-linux-1711-")).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.ms = self.base / "prog" / "navegador" / "ms-playwright"
        chrome = self.ms / "chromium-1169" / "chrome-linux" / "chrome"
        chrome.parent.mkdir(parents=True)
        chrome.write_text('#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a"; done\n', encoding="utf-8")
        os.chmod(chrome, 0o755)

    def test_o_involucro_executado_de_verdade_entrega_so_os_argumentos_filtrados(self):
        if not Path("/usr/bin/python3").exists():
            self.skipTest("sem /usr/bin/python3")
        r = subprocess.run(["/usr/bin/python3", "-I", str(WSL / "chromium-sem-disfarce"),
                            "--disable-blink-features=AutomationControlled", "--no-proxy-server", "--headless"],
                           capture_output=True, text=True, env={"PLAYWRIGHT_BROWSERS_PATH": str(self.ms)}, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        linhas = r.stdout.splitlines()
        self.assertEqual(linhas, ["--headless", "--enable-automation", "--disable-features=EncryptedClientHello",
                                  "--proxy-server=http://127.0.0.1:3128"])

    def jaula(self):
        if MOTIVO:
            if EXIGE:
                raise AssertionError(f"FUNDACAO_CI_EXIGE_BWRAP=1 e não há bwrap utilizável: {MOTIVO}")
            self.skipTest(MOTIVO)
        prog = self.base / "prog"
        for origem in (SCRIPTS / "navegador.py", SCRIPTS / "gravacao_segura.py", WSL / "chromium-sem-disfarce"):
            shutil.copy(origem, prog / origem.name)
        estado = self.base / "estado" / "criador"
        for sub in ("navegador/perfil", "proxy", "trabalho/pedido-nav-0001/saida"):
            (estado / sub).mkdir(parents=True, exist_ok=True)       # o teste chama jaula() mais de uma vez
        (estado / "proxy" / "proxy.sock").touch()
        os.chmod(estado, 0o700)
        return J.Config(bwrap=shutil.which("bwrap"), estado=str(self.base / "estado"), programas=str(prog),
                        python="/usr/bin/python3", usuario=None), estado

    def rodar_na_caixa(self, comando, modo="navegador", variante=None):
        cfg, _ = self.jaula()
        perfil = J.perfil_do_modo(modo, variante)
        fds = {d: J._memfd("jaula", dados) for d, dados in J.conteudos_gerados(os.getuid(), os.getgid()).items()}
        self.addCleanup(lambda: [os.close(fd) for fd in fds.values()])
        argv = J.montar_argv(cfg, "criador", "pedido-nav-0001", perfil, comando, fds=fds)
        return subprocess.run(argv, capture_output=True, env={}, pass_fds=tuple(fds.values()), timeout=90)

    def test_o_programa_do_navegador_carrega_na_caixa_e_sem_playwright_diz_o_que_o_titular_faz(self):
        cfg, _ = self.jaula()
        r = self.rodar_na_caixa(["/usr/bin/python3", "-I", "-B", f"{cfg.programas}/navegador.py", "jaula",
                                 json.dumps({"acao": "sondar"})])
        self.assertEqual(r.returncode, 3, r.stderr.decode("utf-8", "replace")[-400:])
        self.assertIn("Playwright da jaula", json.loads(r.stderr.decode("utf-8"))["erro"])

    def test_n_nav_9_o_involucro_dentro_da_caixa_tira_as_flags_e_ve_so_o_chromium_montado(self):
        cfg, _ = self.jaula()
        r = self.rodar_na_caixa(["/usr/bin/python3", "-I", "-B", f"{cfg.programas}/chromium-sem-disfarce",
                                 "--disable-blink-features=AutomationControlled", "--host-resolver-rules=MAP * 1.2.3.4"])
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace")[-400:])
        linhas = r.stdout.decode("utf-8").splitlines()
        self.assertEqual(linhas[0], "--enable-automation")
        self.assertFalse([l for l in linhas if "AutomationControlled" in l or "host-resolver" in l])

    def test_n_nav_9_navigator_webdriver_e_verdadeiro_no_chromium_de_verdade(self):
        base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
        if not base or W.chromium_do_playwright(base) is None:
            self.skipTest("defina PLAYWRIGHT_BROWSERS_PATH com um Chromium do Playwright instalado (o passo 4 do preparar-wsl.sh "
                          "o instala na jaula, de dono root); aqui só o Python do teste precisa do playwright")
        try:
            import playwright.sync_api  # noqa: F401
        except ImportError:
            self.skipTest("o Python do teste não tem o pacote playwright")
        pasta = self.base / "aqui"
        pasta.mkdir()
        shutil.copy(WSL / "chromium-sem-disfarce", pasta / "chromium-sem-disfarce")
        os.chmod(pasta / "chromium-sem-disfarce", 0o755)
        with mock.patch.object(N, "AQUI", pasta), mock.patch.object(N, "PERFIL_DA_JAULA", str(self.base / "perfil")), \
                mock.patch.object(N, "SAIDA_DA_JAULA", str(self.base / "saida")):
            res, codigo = N.executar_na_jaula(json.dumps({"acao": "sondar", "sandbox": False}))
        self.assertEqual(codigo, 0)
        self.assertIs(res["webdriver"], True)               # o disfarce padrão do Playwright está fora


if __name__ == "__main__":
    unittest.main()
