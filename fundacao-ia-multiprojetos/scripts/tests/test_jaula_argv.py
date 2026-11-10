"""`assets/host/wsl/jaula.py`, `jaula-entrar` e as peças puras do `canario_jaula.py` (1.7.11, lote L3; DESENHO-JAULA §2, §3.3,
§6.3 e §8): o argv do bubblewrap montado SEM rodar, o pedido estrito, a ficha, o portão, a cópia de ida e de volta e a
conferência de segredo da saída. Roda em qualquer sistema (o bwrap de verdade é o `test_jaula_bwrap.py`). Nomes e
projetos fictícios; a chave "secreta" é uma sequência inventada."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import shutil
import stat
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from apoio import SKILL, criar_ligacao_dir
from test_dominios_ficha import carregar_por_caminho

WSL = SKILL / "assets" / "host" / "wsl"
J = carregar_por_caminho("_jaula_teste", WSL / "jaula.py")
CANARIO = carregar_por_caminho("_canario_jaula_argv", WSL / "canario_jaula.py")
HOJE = date(2026, 11, 8)
SISTEMA = [["ro-bind", "/usr", "/usr"], ["symlink", "usr/bin", "/bin"], ["symlink", "usr/lib", "/lib"]]
FDS = {d: 10 + i for i, d in enumerate(J.DADOS_GERADOS)}
# Montado por partes: o valor é o mesmo, e a varredura de segredo do pacote não o toma por chave de verdade.
SEGREDO = "-".join(("sk", "ficticio", "0123456789", "ABCDEFGHIJKLMNOP", "xyz"))
FICHA = {"valida": True, "project_id": "criador",
         "navegador": {"dominios": ["*.tjsp.jus.br", "esaj.tjsp.jus.br"], "logins": ["esaj.tjsp.jus.br"],
                       "modos": ["sessao", "login", "captcha"]},
         "outras_llm": [{"provedor": "openai-codex", "autenticacao": "conta_chatgpt", "modos": ["exec", "titular"],
                         "conteudo_de_terceiros": True, "teto_chamadas_dia": 30,
                         "r55": {"plano": "plus", "treinamento_desligado": True, "conferido_em": "2026-11-08"}}]}


def argv_de(modo, variante=None, como=None, *, projeto="criador", comando=("/usr/bin/python3", "x"), existe=lambda p: True,
            grafico=None, extras=None, fds=None):
    perfil = J.perfil_do_modo(modo, variante, como)
    fds = dict(FDS) if fds is None else fds
    if extras and any(n in perfil.segredos for n in extras):
        fds["args"] = 30
    return J.montar_argv(J.Config(), projeto, "pedido-0001", perfil, list(comando), fds=fds, grafico=grafico,
                         extras=extras, existe=existe, sistema=SISTEMA)


def opcao(argv, nome):
    """Os argumentos que seguem cada ocorrência de `nome`, até a próxima opção `--`."""
    achados = []
    for i, a in enumerate(argv):
        if a == nome:
            j = i + 1
            while j < len(argv) and not (argv[j].startswith("--") and argv[j] != "--" and j > i + 2):
                j += 1
            achados.append(argv[i + 1:i + 3])
    return achados


def antes_do_comando(argv):
    return argv[:argv.index("--")]


MODOS_DE_TESTE = [("navegador", None, None), ("navegador-janela", "login", None), ("navegador-janela", "captcha", None),
                  ("codex-exec", None, None), ("codex-titular", None, None), ("canario", None, "navegador"),
                  ("canario", None, "codex-exec")]


class ArgvFixo(unittest.TestCase):
    def test_opcoes_fixas_em_todos_os_modos(self):
        for modo, variante, como in MODOS_DE_TESTE:
            a = antes_do_comando(argv_de(modo, variante, como))
            with self.subTest(modo=modo, variante=variante, como=como):
                for fixa in ("--unshare-all", "--unshare-user", "--unshare-net", "--die-with-parent", "--clearenv"):
                    self.assertIn(fixa, a)
                self.assertIn(["ALL"], [x[:1] for x in opcao(a, "--cap-drop")])
                self.assertEqual(opcao(a, "--hostname")[0][0], "jaula")
                self.assertEqual(opcao(a, "--chdir")[0][0], "/trabalho")
                self.assertNotIn("--share-net", a)       # sem rede do host
                self.assertNotIn("--unshare-all-try", a)
                self.assertLess(a.index("--clearenv"), a.index("--setenv"))  # o ambiente é limpo antes de pôr o fixo
                self.assertEqual(a[0], "/usr/bin/bwrap")

    def test_new_session_e_disable_userns_por_modo(self):
        for modo, variante, como in MODOS_DE_TESTE:
            perfil = J.perfil_do_modo(modo, variante, como)
            a = antes_do_comando(argv_de(modo, variante, como))
            with self.subTest(modo=modo, como=como):
                self.assertEqual("--new-session" in a, not perfil.terminal)
                self.assertEqual("--disable-userns" in a, not perfil.userns_aninhado)
        self.assertIn("--new-session", argv_de("navegador"))
        self.assertNotIn("--new-session", argv_de("codex-titular"))      # o pty próprio é a sessão
        self.assertIn("--disable-userns", argv_de("codex-exec"))
        self.assertNotIn("--disable-userns", argv_de("navegador"))       # o Chromium precisa do aninhado (M6)

    def test_comeca_vazia_nada_de_fora_e_montado(self):
        # O home de quem roda o teste entra na hora, nunca escrito aqui: o saneamento da cópia pública troca o nome de
        # usuário, e o pacote dela deixaria de ser igual à fonte (liberação da 1.7.11). "/home/usuario" fica de exemplo.
        home = os.path.expanduser("~")
        proprio = (home,) if home.startswith("/home/") and len(home) > len("/home/") else ()
        proibidos = ("/mnt", "/home/usuario", "/home/titular", "/root", "/etc/fundacao-ia", "/var/lib/fundacao-ia/jaula/outro",
                     "projects/", "/data", "data/", "_browser_profile") + proprio
        for modo, variante, como in MODOS_DE_TESTE:
            a = antes_do_comando(argv_de(modo, variante, como))
            with self.subTest(modo=modo):
                self.assertNotIn(["/", "/"], [x[:2] for x in opcao(a, "--bind") + opcao(a, "--ro-bind")])
                self.assertNotIn(["/etc", "/etc"], opcao(a, "--ro-bind"))   # /etc só em itens
                for arg in a:
                    for p in proibidos:
                        self.assertNotIn(p, arg, f"{p!r} apareceu em {arg!r}")
                fontes = [x[0] for x in opcao(a, "--ro-bind") + opcao(a, "--bind")]
                self.assertTrue(all(not f.startswith(("/mnt", "/home", "/root")) for f in fontes))

    def test_etc_minimo_e_arquivos_gerados(self):
        a = antes_do_comando(argv_de("navegador"))
        ro = [x for x in opcao(a, "--ro-bind")]
        for item in J.ETC_SOMENTE_LEITURA:
            self.assertIn([item, item], ro)
        dados = opcao(a, "--ro-bind-data")
        self.assertEqual({d[1] for d in dados}, set(J.DADOS_GERADOS))
        self.assertEqual({d[0] for d in dados}, {str(n) for n in FDS.values()})
        self.assertNotIn("/etc/resolv.conf", a)                      # o DNS é do proxy
        sem_etc = antes_do_comando(argv_de("navegador", existe=lambda p: False))
        self.assertEqual([x for x in opcao(sem_etc, "--ro-bind") if x[0].startswith("/etc")], [])
        gerados = J.conteudos_gerados(1234, 1235)
        self.assertEqual(set(gerados), set(J.DADOS_GERADOS))
        self.assertIn(b"fundacao-jaula:x:1234:1235", gerados["/etc/passwd"])
        self.assertEqual(gerados["/etc/passwd"].count(b"\n"), 2)     # só a jaula e nobody
        self.assertEqual(gerados["/etc/hosts"], b"127.0.0.1 localhost\n")

    def test_sistema_so_leitura_sem_etc_proc_dev_tmp_do_execucao_isolada(self):
        reaproveitado = J.montagens_do_sistema([["ro-bind", "/usr", "/usr"], ["ro-bind", "/etc", "/etc"],
                                                ["proc", "/proc"], ["dev", "/dev"], ["tmpfs", "/tmp"],
                                                ["symlink", "usr/bin", "/bin"]])
        self.assertEqual(reaproveitado, [["ro-bind", "/usr", "/usr"], ["symlink", "usr/bin", "/bin"]])
        self.assertTrue(J.montagens_do_sistema())  # a do execucao_isolada desta máquina também carrega

    def test_tmpfs_proc_dev_shm_e_o_programa_do_canario(self):
        a = antes_do_comando(argv_de("canario", como="navegador"))
        for t in ("/tmp", "/run", "/var", "/dev/shm", "/home/jaula", "/run/jaula"):
            self.assertIn([t], [x[:1] for x in opcao(a, "--tmpfs")], t)
        self.assertIn(["/proc"], [x[:1] for x in opcao(a, "--proc")])
        self.assertIn(["/dev"], [x[:1] for x in opcao(a, "--dev")])
        self.assertEqual(opcao(a, "--size")[0][0], str(256 * 1024 * 1024))
        programa = f"{J.Config().programas}/canario_jaula.py"
        self.assertIn([programa, programa], opcao(a, "--ro-bind"))

    def test_ordem_das_montagens(self):
        a = antes_do_comando(argv_de("navegador"))
        pos = lambda *trecho: next(i for i in range(len(a)) if a[i:i + len(trecho)] == list(trecho))
        self.assertLess(pos("--tmpfs", "/home/jaula"), pos("--bind", "/var/lib/fundacao-ia/jaula/criador/navegador/perfil",
                                                           "/home/jaula/perfil"))
        self.assertLess(pos("--tmpfs", "/run/jaula"), pos("--ro-bind", "/var/lib/fundacao-ia/jaula/criador/proxy/proxy.sock",
                                                          "/run/jaula/proxy.sock"))
        self.assertLess(pos("--ro-bind", "/var/lib/fundacao-ia/jaula/criador/proxy/proxy.sock", "/run/jaula/proxy.sock"),
                        pos("--remount-ro", "/run/jaula"))                   # /run/jaula é só leitura (EROFS no canário)
        self.assertLess(pos("--tmpfs", "/tmp"), pos("--size"))
        self.assertLess(pos("--dev", "/dev"), pos("--tmpfs", "/dev/shm"))


class MontagensPorModo(unittest.TestCase):
    ESTADO = "/var/lib/fundacao-ia/jaula/criador"
    TRABALHO = ESTADO + "/trabalho/pedido-0001"

    def binds(self, modo, variante=None, como=None, **kw):
        a = antes_do_comando(argv_de(modo, variante, como, **kw))
        return opcao(a, "--bind"), opcao(a, "--ro-bind")

    def test_navegador_so_o_perfil_e_a_saida(self):
        rw, ro = self.binds("navegador")
        self.assertEqual(rw, [[self.ESTADO + "/navegador/perfil", "/home/jaula/perfil"], [self.TRABALHO + "/saida", "/trabalho/saida"]])
        self.assertFalse([x for x in ro if x[1].startswith("/trabalho")])   # nada do projeto

    def test_janela_login_usa_o_perfil_e_captcha_usa_home_temporario(self):
        rw, _ = self.binds("navegador-janela", "login")
        self.assertIn([self.ESTADO + "/navegador/perfil", "/home/jaula/perfil"], rw)
        rw, _ = self.binds("navegador-janela", "captcha")
        self.assertEqual(rw, [[self.TRABALHO + "/saida", "/trabalho/saida"]])  # sem perfil persistente

    def test_codex_exec_e_titular_veem_a_copia_so_leitura_e_gravam_na_saida(self):
        for modo in ("codex-exec", "codex-titular"):
            rw, ro = self.binds(modo)
            with self.subTest(modo=modo):
                self.assertIn([self.ESTADO + "/codex/home", "/home/jaula/codex"], rw)
                self.assertIn([self.TRABALHO + "/saida", "/trabalho/saida"], rw)
                self.assertIn([self.TRABALHO + "/projeto", "/trabalho/projeto"], ro)
                self.assertNotIn("/trabalho/projeto", [x[1] for x in rw])    # a cópia nunca é gravável

    def test_canario_nunca_monta_o_estado_persistente(self):
        for como in ("navegador", "codex-exec", "codex-titular"):
            rw, _ = self.binds("canario", como=como)
            self.assertEqual(rw, [[self.TRABALHO + "/saida", "/trabalho/saida"]])

    def test_outro_projeto_nao_aparece(self):
        a = argv_de("navegador", projeto="outro-projeto")
        self.assertTrue(any("/jaula/outro-projeto/" in x for x in a))
        self.assertFalse(any("/jaula/criador" in x for x in a))

    def test_projeto_e_pedido_invalidos_recusam(self):
        for projeto in ("../x", "A", "a--b", "", "x" * 41, "a/b"):
            with self.subTest(projeto=projeto), self.assertRaises(J.Recusa):
                argv_de("navegador", projeto=projeto)


class AmbienteEComando(unittest.TestCase):
    def test_ambiente_e_a_lista_fixa_do_modo(self):
        for modo, variante, como in MODOS_DE_TESTE:
            a = antes_do_comando(argv_de(modo, variante, como))
            nomes = {x[0] for x in opcao(a, "--setenv")}
            perfil = J.perfil_do_modo(modo, variante, como)
            esperado = {"PATH", "HOME", "TMPDIR", "LANG", "NO_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY",
                        "https_proxy", "http_proxy", "all_proxy"} | ({"PLAYWRIGHT_BROWSERS_PATH"} if perfil.familia == "navegador" else {"CODEX_HOME"})
            with self.subTest(modo=modo):
                self.assertEqual(nomes, esperado)
        for x in opcao(antes_do_comando(argv_de("navegador")), "--setenv"):
            if x[0].lower().endswith("_proxy") and x[0] != "NO_PROXY":
                self.assertEqual(x[1], "http://127.0.0.1:3128")

    def test_segredo_vai_pelo_descritor_e_nunca_pelo_argv(self):
        a = argv_de("codex-exec", extras={"OPENAI_API_KEY": SEGREDO})
        self.assertNotIn(SEGREDO, " ".join(a))
        self.assertEqual(opcao(antes_do_comando(a), "--args")[0][0], "30")
        self.assertNotIn("OPENAI_API_KEY", {x[0] for x in opcao(antes_do_comando(a), "--setenv")})
        conteudo = J.args_secretos({"OPENAI_API_KEY": SEGREDO})
        self.assertEqual(conteudo, b"--setenv\0OPENAI_API_KEY\0" + SEGREDO.encode() + b"\0")
        with self.assertRaises(J.Recusa):   # sem o descritor, não monta
            J.montar_argv(J.Config(), "criador", "pedido-0001", J.perfil_do_modo("codex-exec"), ["x"], fds=dict(FDS),
                          extras={"OPENAI_API_KEY": SEGREDO}, sistema=SISTEMA)

    def test_variavel_fora_da_lista_do_modo_recusa(self):
        for extras in ({"LD_PRELOAD": "/x"}, {"OPENAI_API_KEY": SEGREDO}, {"openai": "x"}, {"PATH": "/x"}, {"FOO": "a\0b"}):
            with self.subTest(extras=list(extras)), self.assertRaises(J.Recusa):
                argv_de("navegador", extras=extras)

    def test_o_comando_nao_entra_no_texto_do_sh(self):
        perigoso = ["/usr/bin/python3", "x; rm -rf /", "$(id)", "`id`", "--bind", "/", "/"]
        a = argv_de("navegador", comando=perigoso)
        i = a.index("--")
        self.assertEqual(a[i + 1:i + 5], ["/bin/sh", "-c", J.PONTE_SOCAT, "jaula"])
        self.assertEqual(a[i + 5:], perigoso)
        self.assertNotIn("{", J.PONTE_SOCAT)
        self.assertIn("UNIX-CONNECT:/run/jaula/proxy.sock", J.PONTE_SOCAT)
        self.assertIn("3128", J.PONTE_SOCAT)

    def test_grafico_so_na_janela_e_so_de_caminho_conhecido(self):
        wayland = {"tipo": "wayland-socket", "caminho": "/mnt/wslg/runtime-dir/wayland-0"}
        a = antes_do_comando(argv_de("navegador-janela", "login", grafico=wayland))
        self.assertIn(["/mnt/wslg/runtime-dir/wayland-0", "/run/jaula/wayland-0"], opcao(a, "--ro-bind"))
        self.assertIn(["WAYLAND_DISPLAY", "/run/jaula/wayland-0"], opcao(a, "--setenv"))
        self.assertLess(a.index("/run/jaula/wayland-0"), a.index("--remount-ro"))
        fd = antes_do_comando(argv_de("navegador-janela", "login", grafico={"tipo": "wayland-fd", "fd": 7}))
        self.assertIn(["WAYLAND_SOCKET", "7"], opcao(fd, "--setenv"))
        x11 = antes_do_comando(argv_de("navegador-janela", "login", grafico={"tipo": "x11", "caminho": "/tmp/.X11-unix/X0"}))
        self.assertIn(["/tmp/.X11-unix/X0", "/tmp/.X11-unix/X0"], opcao(x11, "--ro-bind"))
        for ruim in ({"tipo": "wayland-socket", "caminho": "/etc/shadow"}, {"tipo": "wayland-socket", "caminho": "/mnt/wslg/../c/x"},
                     {"tipo": "x11", "caminho": "/mnt/wslg/runtime-dir/wayland-0"}, {"tipo": "wayland-fd", "fd": 1},
                     {"tipo": "wayland-fd", "fd": True}, {"tipo": "outro"}, {"tipo": "x11"}):
            with self.subTest(ruim=ruim), self.assertRaises(J.Recusa):
                argv_de("navegador-janela", "login", grafico=ruim)
        for modo in ("navegador", "codex-exec", "codex-titular"):
            with self.subTest(modo=modo), self.assertRaises(J.Recusa):
                argv_de(modo, grafico=wayland)

    def test_perfis_variantes_e_limites(self):
        with self.assertRaises(J.Recusa):
            J.perfil_do_modo("navegador-janela")                    # pede a variante
        with self.assertRaises(J.Recusa):
            J.perfil_do_modo("navegador", "login")
        with self.assertRaises(J.Recusa):
            J.perfil_do_modo("canario")                             # pede 'como'
        with self.assertRaises(J.Recusa):
            J.perfil_do_modo("shell")
        self.assertIsNone(J.perfil_do_modo("navegador-janela", "captcha").estado)
        self.assertEqual(J.perfil_do_modo("navegador").prazo_s, 120)
        self.assertEqual(J.perfil_do_modo("codex-exec").prazo_s, 900)
        self.assertEqual((J.perfil_do_modo("navegador").memoria_mb, J.perfil_do_modo("codex-exec").memoria_mb), (4096, 2048))
        lim = J.limites_do_modo(J.perfil_do_modo("codex-exec"))
        self.assertEqual((lim["tempo_s"], lim["processos"], lim["memoria_bytes"]), (900, 256, 2048 * 1024 * 1024))

    def test_so_o_canario_o_navegador_e_o_codex_tem_programa_nesta_versao(self):
        """L5 deu programa ao navegador (com a carga conferida); o L6, ao Codex (com o pedido conferido por validar_pedido)."""
        perfil = J.perfil_do_modo("navegador")
        with self.assertRaises(J.Recusa):                                   # sem a carga conferida, nada roda
            J.argv_do_programa(J.Config(), "navegador", {}, perfil, ["a.org"], "/raiz", [])
        with self.assertRaises(J.Recusa) as r:                              # sem o prompt conferido, nada roda
            J.argv_do_programa(J.Config(), "codex-exec", {}, J.perfil_do_modo("codex-exec"), ["a.org"], "/raiz", [])
        self.assertIn("prompt", str(r.exception))
        cp = J.perfil_do_modo("canario", None, "codex-titular")
        comando, _ = J.argv_do_programa(J.Config(), "canario", {"como": "codex-titular"}, cp, ["*.a.org"], "/raiz", ["PATH", "HOME"])
        self.assertEqual(comando[:3], ["/usr/bin/python3", "-I", "-B"])
        self.assertIn("--terminal-proprio", comando)
        self.assertEqual(comando[comando.index("--dominio") + 1], "a.org")
        self.assertEqual(comando[comando.index("--userns") + 1], "bloqueado")


def pedido(**campos):
    base = {"schema_version": J.ESQUEMA_PEDIDO, "id": "pedido-0001"}
    base.update(campos)
    return json.dumps(base).encode()


class PedidoEstrito(unittest.TestCase):
    """N-JAU-6 e o esquema fechado por modo."""

    def recusa(self, bruto, modo="navegador"):
        with self.assertRaises(J.Recusa):
            J.validar_pedido(bruto, "criador", modo)

    def test_pedidos_validos(self):
        self.assertEqual(J.validar_pedido(pedido(), "criador", "navegador")["id"], "pedido-0001")
        self.assertEqual(J.validar_pedido(pedido(arquivos=["a/b.txt"], prompt="resuma"), "criador", "codex-exec")["arquivos"],
                         ["a/b.txt"])                                         # 1.7.11 L6: o prompt é obrigatório no codex-exec
        self.assertEqual(J.validar_pedido(pedido(variante="login"), "criador", "navegador-janela")["variante"], "login")
        self.assertEqual(J.validar_pedido(pedido(como="navegador", dominios=["a.org"]), "criador", "canario")["como"], "navegador")

    def test_chave_repetida_nan_float_campo_extra_e_tamanho(self):
        base = b'{"schema_version": "%s", "id": "pedido-0001"' % J.ESQUEMA_PEDIDO.encode()
        self.recusa(base + b', "id": "pedido-0002"}')                       # chave repetida
        self.recusa(base + b', "x": NaN}')
        self.recusa(base + b', "x": Infinity}')
        self.recusa(base + b', "x": 1.5}')
        self.recusa(pedido(comando=["/bin/sh"]))                            # campo fora do modo
        self.recusa(pedido(prompt="x"), "codex-exec")
        self.recusa(pedido(arquivos=["a"]), "navegador")                    # 'arquivos' só no codex-exec
        self.recusa(pedido(variante="login"), "navegador")
        self.recusa(base + b', "relleno": "' + b"x" * J.LIMITE_PEDIDO + b'"}')   # acima de 64 KiB
        self.recusa(b"")
        self.recusa(b"[]")
        self.recusa(b"\xff\xfe")
        self.recusa(b'{"a": ' * 2000)

    def test_esquema_e_id(self):
        self.recusa(json.dumps({"id": "pedido-0001"}).encode())
        self.recusa(json.dumps({"schema_version": "x/1", "id": "pedido-0001"}).encode())
        for ruim in ("curto", "MAIUSCULA-1", "tem espaço-1", "../../etc", "x" * 41, 1, None, ""):
            self.recusa(pedido(id=ruim))

    def test_arquivos_do_codex(self):
        for ruim in (["../x"], ["/etc/passwd"], ["a/../b"], ["a\\b"], ["c:/x"], ["a//b"], [""], [], ["a", "a"], "a",
                     [1], ["a\nb"], ["x/" * 13 + "y"], [f"f{i}" for i in range(201)]):
            with self.subTest(ruim=str(ruim)[:30]):
                self.recusa(pedido(arquivos=ruim), "codex-exec")
        self.recusa(pedido(), "codex-exec")                                  # sem lista

    def test_canario_pede_como_e_dominios(self):
        self.recusa(pedido(), "canario")
        self.recusa(pedido(como="canario", dominios=["a.org"]), "canario")
        self.recusa(pedido(como="navegador"), "canario")
        self.recusa(pedido(como="navegador", dominios=[]), "canario")
        self.recusa(pedido(como="navegador", dominios=["a.org"], variante="outra"), "canario")

    def test_modo_e_projeto_desconhecidos(self):
        self.recusa(pedido(), "shell")
        with self.assertRaises(J.Recusa):
            J.validar_pedido(pedido(), "../x", "navegador")

    def test_terminal_usa_o_pedido_padrao(self):
        p = J.validar_pedido(None, "criador", "codex-titular")
        self.assertRegex(p["id"], J.PEDIDO_ID)
        self.assertEqual(J.validar_pedido(None, "criador", "navegador-janela")["variante"], "login")
        with self.assertRaises(J.Recusa):
            J.validar_pedido(None, "criador", "codex-exec")


class FichaDominiosEPortao(unittest.TestCase):
    def doms(self, modo, **kw):
        return J.dominios_do_modo(FICHA, modo, hoje=HOJE, **kw)

    def test_dominios_por_modo(self):
        self.assertEqual(self.doms("navegador"), ["*.tjsp.jus.br", "esaj.tjsp.jus.br"])
        self.assertEqual(self.doms("navegador-janela", variante="captcha"), ["*.tjsp.jus.br", "esaj.tjsp.jus.br"])
        self.assertEqual(self.doms("codex-exec"), ["chatgpt.com", "auth.openai.com"])      # DECISAO-010: conta do ChatGPT
        outra = json.loads(json.dumps(FICHA))
        outra["outras_llm"][0]["autenticacao"] = "chave_api"
        self.assertEqual(J.dominios_do_modo(outra, "codex-titular", hoje=HOJE), ["api.openai.com"])

    def test_modo_sem_secao_ou_nao_aberto_na_ficha_recusa(self):
        sem = {"valida": True}
        for modo in ("navegador", "navegador-janela", "codex-exec", "codex-titular"):
            with self.subTest(modo=modo), self.assertRaises(J.Recusa):
                J.dominios_do_modo(sem, modo, hoje=HOJE)
        so_sessao = json.loads(json.dumps(FICHA))
        so_sessao["navegador"]["modos"] = ["sessao"]
        with self.assertRaises(J.Recusa):
            J.dominios_do_modo(so_sessao, "navegador-janela", variante="login", hoje=HOJE)
        so_exec = json.loads(json.dumps(FICHA))
        so_exec["outras_llm"][0]["modos"] = ["exec"]
        with self.assertRaises(J.Recusa):
            J.dominios_do_modo(so_exec, "codex-titular", hoje=HOJE)
        com_virgula = json.loads(json.dumps(FICHA))
        com_virgula["navegador"]["dominios"] = ["a.org,b.org"]
        with self.assertRaises(J.Recusa):
            J.dominios_do_modo(com_virgula, "navegador", hoje=HOJE)

    def test_r55_ausente_futuro_ou_velho_recusa(self):
        item = FICHA["outras_llm"][0]
        J.conferir_r55(item, HOJE)
        J.conferir_r55({"r55": {"treinamento_desligado": True, "conferido_em": (HOJE - timedelta(days=90)).isoformat()}}, HOJE)
        casos = [{}, {"r55": None}, {"r55": {"treinamento_desligado": False, "conferido_em": "2026-11-08"}},
                 {"r55": {"treinamento_desligado": True}}, {"r55": {"treinamento_desligado": True, "conferido_em": "amanhã"}},
                 {"r55": {"treinamento_desligado": True, "conferido_em": "2026-11-09"}},
                 {"r55": {"treinamento_desligado": True, "conferido_em": (HOJE - timedelta(days=91)).isoformat()}},
                 {"r55": {"treinamento_desligado": "sim", "conferido_em": "2026-11-08"}}]
        for caso in casos:
            with self.subTest(caso=caso), self.assertRaises(J.Recusa):
                J.conferir_r55(caso, HOJE)
        velho = json.loads(json.dumps(FICHA))
        velho["outras_llm"][0]["r55"]["conferido_em"] = "2026-01-01"
        with self.assertRaises(J.Recusa):
            J.dominios_do_modo(velho, "codex-exec", hoje=HOJE)       # a entrada fixa repete a conferência a cada uso

    def test_canario_so_usa_nomes_da_ficha_e_nunca_as_sentinelas(self):
        self.assertEqual(self.doms("canario", como="navegador", pedidos=["esaj.tjsp.jus.br"]), ["esaj.tjsp.jus.br"])
        for pedidos in (["outro.example"], ["esaj.tjsp.jus.br", "example.com"], ["tjsp.jus.br"]):
            with self.subTest(pedidos=pedidos), self.assertRaises(J.Recusa):
                self.doms("canario", como="navegador", pedidos=pedidos)
        com_sentinela = json.loads(json.dumps(FICHA))
        com_sentinela["navegador"]["dominios"].append("*.example.com")
        with self.assertRaises(J.Recusa):
            J.dominios_do_modo(com_sentinela, "canario", como="navegador", pedidos=["*.example.com"], hoje=HOJE)

    def test_ficha_invalida_vencida_ou_de_outro_projeto(self):
        J.conferir_ficha(FICHA, "criador", HOJE)
        for ruim in (None, [], {"valida": False}, {**FICHA, "project_id": "outro"}, {**FICHA, "projeto": "outro"},
                     {**FICHA, "vigencia_ate": "2026-11-07"}, {**FICHA, "vigencia_ate": "um dia"}):
            with self.subTest(ruim=str(ruim)[:40]), self.assertRaises(J.Recusa):
                J.conferir_ficha(ruim, "criador", HOJE)
        J.conferir_ficha({**FICHA, "vigencia_ate": "2026-11-08"}, "criador", HOJE)

    def test_portao_exige_o_relatorio_aprovado_da_mesma_versao(self):
        hashes = {"jaula-entrar": "a" * 64, "proxy_lista.py": "b" * 64, "bwrap": "c" * 64}
        bom = {"schema_version": J.ESQUEMA_RELATORIO_INSTALADO, "hashes": dict(hashes),
               "modos": {"navegador": {"aprovado": True}, "navegador-janela:login": {"aprovado": True},
                         "codex-exec": {"aprovado": False}}}
        J.conferir_portao(FICHA, "navegador", bom, hashes)
        J.conferir_portao(FICHA, "navegador-janela", bom, hashes, variante="login")
        J.conferir_portao(FICHA, "canario", None, hashes)                          # o canário roda sem relatório
        trocado = {**bom, "hashes": {**hashes, "bwrap": "d" * 64}}
        for ruim, modo, variante in ((None, "navegador", None), ({}, "navegador", None), ([], "navegador", None),
                                     ({**bom, "schema_version": "x"}, "navegador", None), (trocado, "navegador", None),
                                     ({**bom, "hashes": {}}, "navegador", None), (bom, "codex-exec", None),
                                     (bom, "codex-titular", None), (bom, "navegador-janela", "captcha"),
                                     ({**bom, "modos": {"navegador": {"aprovado": "sim"}}}, "navegador", None)):
            with self.subTest(modo=modo, variante=variante, ruim=str(ruim)[:30]), self.assertRaises(J.Recusa):
                J.conferir_portao(FICHA, modo, ruim, hashes, variante=variante)
        with self.assertRaises(J.Recusa):
            J.conferir_portao(FICHA, "navegador", bom, {})                         # sem hashes atuais, nada prova a versão


class PastaDeTeste(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="jaula-argv-1711-"))
        self.addCleanup(self._apagar)
        self.raiz = self.base / "raiz"
        self.projeto = self.raiz / "projects" / "criador"
        self.projeto.mkdir(parents=True)
        self.destino = self.base / "destino"
        self.destino.mkdir()

    def _apagar(self):
        def tirar(funcao, caminho, _erro):
            os.chmod(caminho, stat.S_IWRITE | stat.S_IREAD)
            funcao(caminho)
        shutil.rmtree(self.base, onerror=tirar)

    def escrever(self, rel, dados=b"conteudo"):
        p = self.projeto / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(dados)
        return p

    def ligar(self, link: Path, alvo: Path):
        try:
            link.symlink_to(alvo)
        except OSError as exc:
            self.skipTest(f"link simbólico indisponível neste ambiente: {exc}")


class CopiaDeIda(PastaDeTeste):
    def test_codex_exec_leva_so_o_que_o_pedido_lista(self):
        self.escrever("outputs/a.txt", b"A")
        self.escrever("notas/b.md", b"B")
        self.escrever("notas/c.md", b"C")
        r = J.copiar_ida(str(self.projeto), str(self.destino), arquivos=["outputs/a.txt", "notas/b.md"])
        self.assertEqual((r["copiados"], r["bytes"]), (2, 2))
        self.assertEqual(sorted(p.relative_to(self.destino).as_posix() for p in self.destino.rglob("*") if p.is_file()),
                         ["notas/b.md", "outputs/a.txt"])

    def test_n_cdx_8_env_e_pastas_de_segredo_ficam_fora_da_copia(self):
        for rel in (".env", "app/.env.producao", "chaves/id_rsa", "auth.json", "x/credenciais.pem", ".segredos/a.txt",
                    "_browser_profile/Default/Cookies", ".porteiro/pedidos/1.json", ".claude/settings.json",
                    ".git/config", "decisoes/DECISAO-001.md"):
            self.escrever(rel)
        self.escrever("ok.txt")
        r = J.copiar_ida(str(self.projeto), str(self.destino), arquivos=[".env", "app/.env.producao", "chaves/id_rsa",
                                                                         "auth.json", "x/credenciais.pem", ".segredos/a.txt",
                                                                         "_browser_profile/Default/Cookies", ".porteiro/pedidos/1.json",
                                                                         ".claude/settings.json", ".git/config",
                                                                         "decisoes/DECISAO-001.md", "ok.txt"])
        self.assertEqual(r["copiados"], 1)
        self.assertEqual(r["ignorados_total"], 11)
        self.assertEqual([p.name for p in self.destino.rglob("*") if p.is_file()], ["ok.txt"])

    def test_n_cdx_4_instrucao_e_config_de_projeto_plantadas_nao_chegam_a_copia(self):
        for rel in ("AGENTS.md", "sub/AGENTS.md", "CLAUDE.md", ".codex/config.toml", "sub/.codex/config.toml", "ok.md"):
            self.escrever(rel)
        r = J.copiar_ida(str(self.projeto), str(self.destino))
        self.assertEqual([p.name for p in self.destino.rglob("*") if p.is_file()], ["ok.md"])
        self.assertEqual(r["ignorados_total"], 5)
        r = J.copiar_ida(str(self.projeto), str(self.base / "d2") if (self.base / "d2").mkdir() is None else "",
                         arquivos=["AGENTS.md", ".codex/config.toml", "ok.md"])
        self.assertEqual((r["copiados"], r["ignorados_total"]), (1, 2))

    def test_titular_leva_o_projeto_inteiro_menos_as_mascaras(self):
        for rel in ("README.md", "outputs/r.txt", "src/a.py", ".env", "secrets/x", ".git/HEAD", "decisoes/d.md",
                    ".claude/h.json", ".porteiro/p.json", "src/token_store.py"):
            self.escrever(rel)
        r = J.copiar_ida(str(self.projeto), str(self.destino))
        copiados = sorted(p.relative_to(self.destino).as_posix() for p in self.destino.rglob("*") if p.is_file())
        self.assertEqual(copiados, ["README.md", "outputs/r.txt", "src/a.py"])
        self.assertFalse(r["reduzida_a_outputs"])
        self.assertTrue(any(i["caminho"] == ".env" for i in r["ignorados"]))

    def test_projeto_grande_so_leva_outputs_e_diz_isso(self):
        self.escrever("data/grande.bin", b"x" * 500)
        self.escrever("outputs/pequeno.txt", b"y")
        r = J.copiar_ida(str(self.projeto), str(self.destino), teto_bytes=100)
        self.assertTrue(r["reduzida_a_outputs"])
        self.assertEqual([p.name for p in self.destino.rglob("*") if p.is_file()], ["pequeno.txt"])
        self.escrever("outputs/enorme.bin", b"z" * 500)
        with self.assertRaises(J.Recusa):
            J.copiar_ida(str(self.projeto), str(self.base / "d2"), teto_bytes=100) if (self.base / "d2").mkdir() is None else None

    def test_n_cdx_6_ligacao_plantada_nao_e_copiada(self):
        self.escrever("ok.txt")
        alvo = self.base / "segredo-do-codex.json"
        alvo.write_bytes(b'{"token": "x"}')
        self.ligar(self.projeto / "notas.txt", alvo)
        r = J.copiar_ida(str(self.projeto), str(self.destino))
        self.assertEqual([p.name for p in self.destino.rglob("*") if p.is_file()], ["ok.txt"])
        self.assertTrue(any(i["caminho"] == "notas.txt" for i in r["ignorados"]))
        r2 = J.copiar_ida(str(self.projeto), str(self.base / "d2") if (self.base / "d2").mkdir() is None else "",
                          arquivos=["notas.txt"])
        self.assertEqual(r2["copiados"], 0)
        self.assertEqual(len(r2["ignorados"]), 1)

    def test_pasta_trocada_por_ligacao_nao_e_seguida(self):
        fora = self.base / "fora"
        fora.mkdir()
        (fora / "x.txt").write_bytes(b"de fora")
        criar_ligacao_dir(self.projeto / "pasta", fora)   # junção no Windows, link simbólico no Linux
        r = J.copiar_ida(str(self.projeto), str(self.destino), arquivos=["pasta/x.txt"])
        self.assertEqual(r["copiados"], 0)
        self.assertEqual([p for p in self.destino.rglob("*") if p.is_file()], [])


class ConferenciaDeSegredo(unittest.TestCase):
    def test_trecho_de_20_bytes_ou_mais_e_achado(self):
        c = J.contem_trecho_de_segredo
        self.assertTrue(c(b"prefixo " + SEGREDO.encode() + b" sufixo", [SEGREDO]))                 # literal inteiro
        self.assertTrue(c(b"..." + SEGREDO[5:25].encode() + b"...", [SEGREDO]))                    # 20 bytes do meio
        self.assertTrue(c(SEGREDO[:20].encode(), [SEGREDO]))                                       # 20 bytes do começo
        self.assertTrue(c(SEGREDO[-20:].encode(), [SEGREDO.encode()]))                              # 20 bytes do fim
        self.assertTrue(c(b"a" * 100 + SEGREDO[13:40].encode() + b"b" * 100, [SEGREDO]))
        self.assertFalse(c(SEGREDO[5:24].encode(), [SEGREDO]))                                     # 19 bytes: não conta
        self.assertFalse(c(b"nada a ver com a chave", [SEGREDO]))
        self.assertFalse(c(SEGREDO[:10].encode() + b"#" + SEGREDO[11:30].encode(), [SEGREDO]))     # interrompido: <20 de cada lado
        self.assertFalse(c(SEGREDO.encode(), ["curto"]))                                           # segredo curto não vale
        self.assertFalse(c(b"", [SEGREDO]))
        self.assertFalse(c(SEGREDO.encode(), []))

    def test_limite_rotulado_a_copia_transformada_passa(self):
        import base64
        self.assertFalse(J.contem_trecho_de_segredo(base64.b64encode(SEGREDO.encode()), [SEGREDO]))
        self.assertFalse(J.contem_trecho_de_segredo(SEGREDO[::-1].encode(), [SEGREDO]))


class CopiaDeVolta(PastaDeTeste):
    def setUp(self):
        super().setUp()
        self.saida = self.base / "saida"
        self.saida.mkdir()

    def gravar(self, rel, dados):
        p = self.saida / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(dados)

    def test_copia_para_pasta_nova_com_sha256(self):
        import hashlib
        self.gravar("pagina.html", b"<html>oi</html>")
        self.gravar("sub/dado.json", b"{}")
        r = J.copiar_volta(str(self.saida), str(self.projeto), "outputs/navegador/pedido-0001", segredos=[SEGREDO])
        self.assertEqual({c["arquivo"] for c in r["copiados"]}, {"pagina.html", "sub/dado.json"})
        self.assertEqual(next(c for c in r["copiados"] if c["arquivo"] == "pagina.html")["sha256"],
                         hashlib.sha256(b"<html>oi</html>").hexdigest())
        self.assertEqual((self.projeto / "outputs/navegador/pedido-0001/sub/dado.json").read_bytes(), b"{}")
        self.assertEqual(r["recusados"], [])

    def test_n_cdx_7_saida_com_a_chave_literal_nao_e_copiada(self):
        self.gravar("resposta.txt", b"a chave e " + SEGREDO.encode())
        self.gravar("parcial.txt", SEGREDO[10:35].encode())
        self.gravar("limpa.txt", b"sem segredo")
        r = J.copiar_volta(str(self.saida), str(self.projeto), "outputs/codex/pedido-0002", segredos=[SEGREDO])
        destino = self.projeto / "outputs/codex/pedido-0002"
        self.assertEqual([p.name for p in destino.iterdir()], ["limpa.txt"])
        self.assertEqual({x["arquivo"] for x in r["recusados"]}, {"resposta.txt", "parcial.txt"})
        self.assertNotIn(SEGREDO[10:30], json.dumps(r))        # a resposta diz qual arquivo, nunca o trecho
        self.assertIn("segredo", r["recusados"][0]["motivo"])

    def test_destino_que_ja_existe_recusa(self):
        self.gravar("a.txt", b"a")
        J.copiar_volta(str(self.saida), str(self.projeto), "outputs/navegador/pedido-0003")
        with self.assertRaises(J.Recusa):
            J.copiar_volta(str(self.saida), str(self.projeto), "outputs/navegador/pedido-0003")
        self.assertEqual(sorted(p.name for p in (self.projeto / "outputs/navegador/pedido-0003").iterdir()), ["a.txt"])

    def test_n_nav_10_ligacao_plantada_na_saida_e_no_destino_nao_e_seguida(self):
        fora = self.base / "fora.txt"
        fora.write_bytes(b"de fora")
        self.ligar(self.saida / "atalho.txt", fora)
        self.gravar("ok.txt", b"ok")
        r = J.copiar_volta(str(self.saida), str(self.projeto), "outputs/navegador/pedido-0004")
        self.assertEqual([c["arquivo"] for c in r["copiados"]], ["ok.txt"])
        self.assertEqual([x["arquivo"] for x in r["recusados"]], ["atalho.txt"])

    def test_n_nav_10_pasta_de_destino_que_e_ligacao_nao_recebe_a_saida(self):
        self.gravar("ok.txt", b"ok")
        (self.projeto / "outputs").mkdir()
        alvo = self.base / "alvo-externo"
        alvo.mkdir()
        criar_ligacao_dir(self.projeto / "outputs" / "codex", alvo)   # outputs/codex aponta para fora do projeto
        with self.assertRaises(J.Recusa):
            J.copiar_volta(str(self.saida), str(self.projeto), "outputs/codex/pedido-0005")
        self.assertEqual(list(alvo.iterdir()), [])

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW") and os.open in os.supports_dir_fd,
                         "L: a gravacao por descritor de pasta (dir_fd) e do POSIX")
    def test_f2_pasta_trocada_por_ligacao_no_meio_da_copia_nao_recebe_nada(self):
        """Revisao de seguranca da 1.7.11, F2: a sessao renomeia as pastas do proprio projeto. Trocar `outputs/<familia>` (ou uma
        subpasta do destino) por ligacao ENQUANTO a volta copia nao redireciona a gravacao: ela vai pelo descritor aberto."""
        cs = J._script("copia_segura")
        self.gravar("a.txt", b"a")
        self.gravar("z.txt", b"z")
        self.gravar("sub/b.txt", b"b")
        (self.projeto / "outputs" / "codex").mkdir(parents=True)
        alvo = self.base / "estado-de-outro-projeto"
        (alvo / "pedido-0009").mkdir(parents=True)             # o que a ligacao trocada alcancaria pelo caminho
        alvo_sub = self.base / "alvo-da-subpasta"
        alvo_sub.mkdir()
        real = self.base / "outputs-codex-real"
        original, trocas = cs.copiar_conferindo, []

        def com_troca(origem, destino, **kw):
            if not trocas:   # na 1a copia: a pasta-mae vira ligacao, e a subpasta do destino ja nasce como ligacao
                os.rename(self.projeto / "outputs" / "codex", real)
                os.symlink(alvo, self.projeto / "outputs" / "codex", target_is_directory=True)
                os.symlink(alvo_sub, real / "pedido-0009" / "sub", target_is_directory=True)
                trocas.append(origem)
            return original(origem, destino, **kw)
        with mock.patch.object(cs, "copiar_conferindo", com_troca):
            r = J.copiar_volta(str(self.saida), str(self.projeto), "outputs/codex/pedido-0009", segredos=[SEGREDO])
        self.assertEqual(list((alvo / "pedido-0009").iterdir()), [])     # nada caiu onde a ligacao aponta
        self.assertEqual(list(alvo_sub.iterdir()), [])
        self.assertEqual(sorted(p.name for p in (real / "pedido-0009").iterdir() if p.is_file()), ["a.txt", "z.txt"])
        self.assertEqual([x["arquivo"] for x in r["recusados"]], ["sub/b.txt"])   # a subpasta trocada recusa so o arquivo dela
        self.assertEqual(sorted(c["arquivo"] for c in r["copiados"]), ["a.txt", "z.txt"])

    def test_tetos_de_arquivos_e_bytes(self):
        for i in range(5):
            self.gravar(f"f{i}.txt", b"x" * 10)
        r = J.copiar_volta(str(self.saida), str(self.projeto), "outputs/navegador/pedido-0006", teto_arquivos=3)
        self.assertEqual(len(r["copiados"]), 3)
        self.assertEqual(r["recusados_total"], 2)
        r = J.copiar_volta(str(self.saida), str(self.projeto), "outputs/navegador/pedido-0007", teto_bytes=25)
        self.assertEqual(len(r["copiados"]), 2)

    def test_arquivo_grande_demais_para_conferir_nao_passa_sem_conferencia(self):
        self.gravar("grande.bin", b"x" * 1000)
        original = J.ORCAMENTO_CONFERENCIA
        J.ORCAMENTO_CONFERENCIA = 100
        try:
            r = J.copiar_volta(str(self.saida), str(self.projeto), "outputs/codex/pedido-0008", segredos=[SEGREDO])
        finally:
            J.ORCAMENTO_CONFERENCIA = original
        self.assertEqual(r["copiados"], [])
        self.assertIn("conferência", r["recusados"][0]["motivo"])


class InstalacaoEEntrada(PastaDeTeste):
    def etc(self, raiz="/mnt/e/raiz", relatorio=None):
        etc = self.base / "etc"
        (etc / "projetos" / "criador").mkdir(parents=True, exist_ok=True)
        (etc / "jaula").mkdir(exist_ok=True)
        (etc / "projetos" / "criador" / "porteiro-jaula.json").write_text(json.dumps({"raiz": raiz}), encoding="utf-8")
        (etc / "projetos" / "criador" / "aberturas.json").write_text(json.dumps(FICHA), encoding="utf-8")
        if relatorio is not None:
            (etc / "jaula" / "canario-instalado.json").write_text(json.dumps(relatorio), encoding="utf-8")
        return J.Config(etc=str(etc), estado=str(self.base / "estado"), programas=str(self.base / "prog"), usuario=None)

    def test_carregar_instalacao(self):
        cfg = self.etc()
        raiz, ficha, relatorio = J.carregar_instalacao(cfg, "criador", dono=None)
        self.assertEqual((raiz, ficha["project_id"], relatorio), ("/mnt/e/raiz", "criador", None))
        cfg = self.etc(relatorio={"schema_version": J.ESQUEMA_RELATORIO_INSTALADO})
        self.assertEqual(J.carregar_instalacao(cfg, "criador", dono=None)[2]["schema_version"], J.ESQUEMA_RELATORIO_INSTALADO)

    def test_raiz_e_dono_invalidos(self):
        for raiz in ("relativa", "/a/../b", "/a/", "", 5, "/a\\b"):
            with self.subTest(raiz=raiz), self.assertRaises(J.Recusa):
                J.carregar_instalacao(self.etc(raiz=raiz) if raiz != 5 else self.etc(raiz=5), "criador", dono=None) \
                    if True else None
        cfg = self.etc()
        if hasattr(os, "geteuid"):
            with self.assertRaises(J.Recusa):
                J.carregar_instalacao(cfg, "criador", dono=os.geteuid() + 1)    # não é do dono esperado
        with self.assertRaises(J.Recusa):
            J.carregar_instalacao(cfg, "outro-projeto", dono=None)               # nada instalado para ele
        with self.assertRaises(J.Recusa):
            J.carregar_instalacao(cfg, "../x", dono=None)

    def test_arquivo_de_configuracao_com_ligacao_ou_grande_recusa(self):
        cfg = self.etc()
        etc = Path(cfg.etc)
        ficha = etc / "projetos" / "criador" / "aberturas.json"
        ficha.unlink()
        self.ligar(ficha, self.base / "outra.json")
        with self.assertRaises(J.Recusa):
            J.carregar_instalacao(cfg, "criador", dono=None)
        (etc / "projetos" / "criador" / "porteiro-jaula.json").write_bytes(b" " * (2 * 1024 * 1024))
        with self.assertRaises(J.Recusa):
            J.ler_arquivo_do_root(str(etc / "projetos" / "criador" / "porteiro-jaula.json"), dono=None)

    def entrada(self):
        spec = importlib.util.spec_from_loader("_jaula_entrar_teste", importlib.machinery.SourceFileLoader(
            "_jaula_entrar_teste", str(WSL / "jaula-entrar")))
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo

    def chamar(self, argv, cfg, bruto=b"{}"):
        import contextlib
        import io

        class Entrada:
            buffer = io.BytesIO(bruto)

            def isatty(self):
                return False
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            codigo = self.entrada().main(argv, Entrada(), cfg, dono=None)
        self.texto_impresso = saida.getvalue()
        return codigo, json.loads(saida.getvalue())

    def test_a_entrada_recusa_com_codigo_2_e_json(self):
        cfg = self.etc()
        for argv in ([], ["criador"], ["criador", "navegador", "extra"], ["criador", "shell"], ["../x", "navegador"]):
            with self.subTest(argv=argv):
                codigo, resposta = self.chamar(argv, cfg, pedido())
                self.assertEqual(codigo, 2)
                self.assertFalse(resposta["ok"])
                self.assertIn("nada rodou na caixa", resposta["erro"])
        codigo, resposta = self.chamar(["criador", "navegador"], cfg, b'{"schema_version": "x"')   # JSON quebrado
        self.assertEqual(codigo, 2)
        # F3: o que a entrada fixa imprime são os MESMOS bytes que o canário guarda no estado da jaula (texto_da_resposta)
        self.assertEqual(self.texto_impresso, J.texto_da_resposta(resposta))

    def test_sem_o_relatorio_do_canario_o_modo_da_jaula_nao_abre(self):
        cfg = self.etc()
        codigo, resposta = self.chamar(["criador", "navegador"], cfg, pedido())
        self.assertEqual(codigo, 2)
        self.assertFalse(resposta["ok"])
        # n_cdx_1: um projeto sem a seção na ficha não abre o Codex, mesmo com o resto em ordem
        sem = Path(cfg.etc) / "projetos" / "criador" / "aberturas.json"
        sem.write_text(json.dumps({"valida": True, "project_id": "criador"}), encoding="utf-8")
        codigo, resposta = self.chamar(["criador", "codex-exec"], cfg, pedido(arquivos=["a.txt"], prompt="resuma"))
        self.assertEqual(codigo, 2)
        self.assertIn("outras_llm", resposta["erro"])

    def test_o_usuario_da_jaula_e_conferido(self):
        if not hasattr(os, "geteuid"):
            self.skipTest("só no Linux")
        with self.assertRaises(J.Recusa):
            J.conferir_usuario(J.Config(usuario="usuario-que-nao-existe-1711"))
        J.conferir_usuario(J.Config(usuario=None))


class CanarioPuro(unittest.TestCase):
    """As peças do canário que não dependem de estar dentro da jaula."""

    def test_status_http(self):
        self.assertEqual(CANARIO.status_http(b"HTTP/1.1 403 Forbidden\r\n\r\n"), 403)
        self.assertEqual(CANARIO.status_http(b"HTTP/1.1 200 Connection Established\r\n\r\n"), 200)
        for ruim in (b"", b"lixo", b"HTTP/2 200", b"HTTP/1.1 abc", b"\r\n"):
            self.assertIsNone(CANARIO.status_http(ruim))

    def test_capacidades(self):
        texto = "Name:\tx\nCapInh:\t0000000000000000\nCapPrm:\t0000000000000000\nCapEff:\t0000000000000000\nCapBnd:\t000001ffffffffff\n"
        self.assertEqual(CANARIO.capacidades(texto), {"CapInh": 0, "CapPrm": 0, "CapEff": 0, "CapBnd": 0x1FFFFFFFFFF})
        self.assertEqual(CANARIO.capacidades("CapEff:\t00000000a80425fb\n")["CapEff"], 0xA80425FB)
        self.assertEqual(CANARIO.capacidades(""), {})

    def test_pid1_ambiente_sockets_e_abstratos(self):
        self.assertTrue(CANARIO.pid1_e_bwrap(b"/usr/bin/bwrap\0--unshare-all\0--\0/bin/sh\0"))
        self.assertTrue(CANARIO.pid1_e_bwrap(b"bwrap\0"))
        self.assertFalse(CANARIO.pid1_e_bwrap(b"/sbin/init\0"))
        self.assertFalse(CANARIO.pid1_e_bwrap(b""))
        self.assertEqual(CANARIO.sockets_inesperados(["/run/jaula/proxy.sock", "/tmp/.X11-unix/X0"], ["/run/jaula/proxy.sock"]),
                         ["/tmp/.X11-unix/X0"])
        self.assertEqual(CANARIO.env_fora_da_lista(["PATH", "HOME", "PWD", "LD_PRELOAD", "SSH_AUTH_SOCK"], ["PATH", "HOME"]),
                         ["LD_PRELOAD", "SSH_AUTH_SOCK"])
        proc = ("Num RefCount Protocol Flags Type St Inode Path\n0000: 2 0 0 1 01 123 /run/x.sock\n"
                "0001: 2 0 0 1 01 124 @/tmp/.X11-unix/X0\n0002: 2 0 0 1 01 125\n")
        self.assertEqual(CANARIO.abstratos_listados(proc), ["@/tmp/.X11-unix/X0"])

    def test_clienthello_do_canario_e_valido_para_o_proxy(self):
        proxy = carregar_por_caminho("_proxy_lista_canario", WSL / "proxy_lista.py")
        self.assertEqual(proxy.analisar_clienthello(CANARIO.montar_clienthello("example.com")[5:]), ("example.com", False))

    def test_relatorio_tem_os_itens_do_desenho(self):
        """O relatório junta um item por prova do §3.3; as provas de verdade só rodam dentro da jaula (testes L e C)."""
        import types
        from unittest import mock
        a = types.SimpleNamespace(como="codex-exec", dominio="a.org", raiz="/raiz", env="PATH", isca="", userns="bloqueado",
                                  grafico=False, terminal_proprio=False, codex="/usr/local/lib/x/codex")
        ok = lambda nome: {"id": nome, "aprovado": True, "motivo": "ok", "informativo": False}
        nomes = ("sockets_visiveis", "socket_abstrato", "rede_direta", "proc", "fora_montado", "escrita", "capacidades",
                 "tiocsti", "userns", "ambiente", "segredo_da_jaula_invisivel", "sandbox_codex")   # a sonda M7 é do L6
        funcao = lambda n: "prova_segredo_da_jaula" if n.startswith("segredo") else f"prova_{n}"
        com = {funcao(n): mock.Mock(return_value=ok(n)) for n in nomes}
        proxy = ("proxy_lista", "proxy_fora", "proxy_ip", "proxy_local", "proxy_sni", "proxy_porta")
        with mock.patch.multiple(CANARIO, prova_proxy=mock.Mock(return_value=[ok(n) for n in proxy]), **com):
            relatorio = CANARIO.executar(a)
        self.assertEqual({i["id"] for i in relatorio["itens"]}, set(nomes) | set(proxy))
        self.assertTrue(relatorio["aprovado"])
        self.assertEqual(relatorio["schema_version"], "fundacao.canario_jaula/1")
        # uma prova que reprova, ou que quebra, reprova o relatório
        com["prova_escrita"] = mock.Mock(return_value={"id": "escrita", "aprovado": False, "motivo": "/usr aceitou escrita",
                                                       "informativo": False})
        com["prova_capacidades"] = mock.Mock(side_effect=OSError("x"))
        with mock.patch.multiple(CANARIO, prova_proxy=mock.Mock(return_value=[ok(n) for n in proxy]), **com):
            relatorio = CANARIO.executar(a)
        self.assertFalse(relatorio["aprovado"])
        self.assertEqual({i["id"] for i in relatorio["itens"] if not i["aprovado"]}, {"escrita", "capacidades"})
        a.como = "navegador"   # fora do Codex não há a prova do segredo da jaula
        with mock.patch.multiple(CANARIO, prova_proxy=mock.Mock(return_value=[]), **{k: v for k, v in com.items()}):
            ids = {i["id"] for i in CANARIO.executar(a)["itens"]}
            self.assertFalse({"segredo_da_jaula_invisivel", "sandbox_codex"} & ids)

    def test_o_canario_fora_da_jaula_nao_pode_aprovar(self):
        """As provas isoladas, sem rede nem /proc do Linux, reprovam: o canário não aprova por padrão."""
        self.assertFalse(CANARIO.prova_proxy("")[0]["aprovado"])
        self.assertFalse(CANARIO.prova_fora_montado("/raiz-que-nao-existe-1711")["aprovado"] and os.path.exists("/mnt"))


if __name__ == "__main__":
    unittest.main()
