"""A jaula DE VERDADE (1.7.11, lote L3; DESENHO-JAULA §8, tipo L): o argv de `jaula.montar_argv` rodado no bubblewrap.

Só no Linux com um bwrap que abre o sandbox; nos outros sistemas PULA com o motivo. Com `FUNDACAO_CI_EXIGE_BWRAP=1` (a CI
do Ubuntu, onde o bwrap é instalado no passo da CI) a falta do bwrap FALHA em vez de pular. Os testes que usam a ponte do
proxy pedem também o `socat`. O canário completo pede um domínio real com DNS em `FUNDACAO_JAULA_DOMINIO` (opcional).
Não precisa de sudo nem do usuário `fundacao-jaula`: o estado fica numa pasta temporária. Nomes e domínios fictícios."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from apoio import SKILL
from test_dominios_ficha import carregar_por_caminho

WSL = SKILL / "assets" / "host" / "wsl"
EXIGE = os.environ.get("FUNDACAO_CI_EXIGE_BWRAP") == "1"
PREFIXO_PROXY = "http://127.0.0.1:3128"


def motivo_de_nao_rodar() -> str | None:
    if not sys.platform.startswith("linux"):
        return f"sistema {sys.platform}: o bubblewrap só existe no Linux/WSL"
    if not hasattr(os, "memfd_create"):
        return "este Python não tem os.memfd_create"
    caminho = shutil.which("bwrap")
    if not caminho:
        return "bubblewrap (bwrap) não encontrado no PATH"
    try:
        # As montagens são as da jaula (`jaula.montagens_do_sistema`): no Ubuntu 24.04, /bin, /lib e /lib64 são ligações para
        # usr/, e sem elas o carregador do ELF não existe dentro da caixa ("execvp /usr/bin/true: No such file").
        montagens = carregar_por_caminho("_jaula_sonda_bwrap", WSL / "jaula.py").montagens_do_sistema()
        argv = [caminho, "--unshare-all", "--unshare-user", "--die-with-parent",
                *[item for m in montagens for item in (f"--{m[0]}", *m[1:])], "--", "/usr/bin/true"]
        r = subprocess.run(argv, capture_output=True, env={}, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"o bwrap não abriu ({type(exc).__name__})"
    if r.returncode != 0:
        return "o bwrap não abriu o sandbox aqui: " + r.stderr.decode("utf-8", "replace").strip()[-200:]
    return None


MOTIVO = motivo_de_nao_rodar()


class JaulaNoBwrap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if MOTIVO:
            if EXIGE:
                raise AssertionError(f"FUNDACAO_CI_EXIGE_BWRAP=1 e não há bwrap utilizável: {MOTIVO}")
            raise unittest.SkipTest(MOTIVO)
        cls.J = carregar_por_caminho("_jaula_bwrap_teste", WSL / "jaula.py")

    def setUp(self):
        J = self.J
        self.base = Path(tempfile.mkdtemp(prefix="jaula-bwrap-1711-"))
        self.addCleanup(self._apagar)
        self.cfg = J.Config(bwrap=shutil.which("bwrap"), estado=str(self.base / "estado"), programas=str(self.base / "prog"),
                            python="/usr/bin/python3", usuario=None)
        self.estado = self.base / "estado" / "criador"
        self.trabalho = self.estado / "trabalho" / "pedido-0001"
        for pasta in ("proxy", "navegador/perfil", "codex/home", "trabalho/pedido-0001/saida", "trabalho/pedido-0001/projeto"):
            (self.estado / pasta).mkdir(parents=True)
        (self.base / "prog").mkdir()
        os.chmod(self.estado, 0o700)
        self.raiz = self.base / "raiz-da-fundacao"
        self.raiz.mkdir()
        (self.trabalho / "projeto" / "arquivo.txt").write_text("do projeto", encoding="utf-8")
        self.proxies = []
        self.fds = []

    def _apagar(self):
        for p in self.proxies:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        for fd in self.fds:
            try:
                os.close(fd)
            except OSError:
                pass

        def tirar(funcao, caminho, _erro):
            os.chmod(caminho, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
            funcao(caminho)
        shutil.rmtree(self.base, onerror=tirar)

    def subir_proxy(self, dominios: str):
        if not shutil.which("socat") and not os.path.exists("/usr/bin/socat"):
            self.skipTest("o socat não está instalado (a ponte do proxy depende dele)")
        sock = self.estado / "proxy" / "proxy.sock"
        p = subprocess.Popen([sys.executable, "-B", str(WSL / "proxy_lista.py"), "servir", "--socket", str(sock),
                              "--dominios", dominios, "--registro", str(self.estado / "proxy" / "registro.jsonl"),
                              "--pedido", "pedido-0001"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, env={})
        self.proxies.append(p)
        fim = time.monotonic() + 10
        while time.monotonic() < fim and not sock.exists():
            time.sleep(0.05)
        self.assertTrue(sock.exists(), "o proxy de lista não abriu o socket")

    def rodar(self, comando: list[str], modo="navegador", variante=None, como=None, com_proxy=False, timeout=90):
        J = self.J
        if not com_proxy:  # a jaula monta o socket do proxy; sem proxy, um arquivo comum faz o papel dele nos testes sem ponte
            (self.estado / "proxy" / "proxy.sock").touch()
        perfil = J.perfil_do_modo(modo, variante, como)
        fds = {}
        for destino, dados in J.conteudos_gerados(os.getuid(), os.getgid()).items():
            fds[destino] = J._memfd("jaula", dados)
        self.fds += list(fds.values())
        saved = dict(J.PROGRAMAS_DO_MODO)
        J.PROGRAMAS_DO_MODO.clear()
        try:
            argv = J.montar_argv(self.cfg, "criador", "pedido-0001", perfil, comando, fds=fds)
        finally:
            J.PROGRAMAS_DO_MODO.update(saved)
        return subprocess.run(argv, capture_output=True, env={}, pass_fds=tuple(fds.values()), timeout=timeout)

    def python_dentro(self, codigo: str, **kw):
        r = self.rodar(["/usr/bin/python3", "-I", "-B", "-c", codigo], **kw)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace")[-500:])
        return json.loads(r.stdout.decode("utf-8"))

    # --- o que a jaula não tem ---------------------------------------------------------------------------------------
    def test_n_nav_6_nada_do_host_existe_dentro_da_jaula(self):
        for modo, como in (("navegador", None), ("codex-exec", None), ("canario", "navegador")):
            with self.subTest(modo=modo):
                dentro = self.python_dentro(
                    "import json,os\nalvos=['/mnt','/mnt/c','/root','/etc/fundacao-ia','/var/lib/fundacao-ia',%r,%r,'/proc/1/root/mnt']\n"
                    "print(json.dumps({'existem':[a for a in alvos if os.path.lexists(a)],'home':sorted(os.listdir('/home'))}))"
                    % (str(self.raiz), str(self.estado)), modo=modo, como=como)
                self.assertEqual(dentro["existem"], [])
                self.assertEqual(dentro["home"], ["jaula"])

    def test_escrita_so_nos_lugares_certos(self):
        dentro = self.python_dentro(
            "import json,os\nr={}\nfor p in ['/usr','/etc','/trabalho/projeto','/run/jaula','/trabalho','/home/jaula','/trabalho/saida','/tmp']:\n"
            "    try:\n        fd=os.open(p+'/escrita-teste',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd);r[p]='gravou'\n"
            "    except OSError as e:\n        r[p]=e.errno\nprint(json.dumps(r))", modo="codex-exec")
        nao_grava = {30, 13, 1}  # EROFS, EACCES, EPERM
        for p in ("/usr", "/etc", "/trabalho/projeto", "/run/jaula", "/trabalho"):
            self.assertIn(dentro[p], nao_grava, f"{p}: {dentro[p]}")
        for p in ("/home/jaula", "/trabalho/saida", "/tmp"):
            self.assertEqual(dentro[p], "gravou", p)
        self.assertTrue((self.trabalho / "saida" / "escrita-teste").exists())      # a saída aparece no host
        self.assertEqual(list((self.trabalho / "projeto").iterdir()), [self.trabalho / "projeto" / "arquivo.txt"])

    def test_o_projeto_aparece_so_leitura_no_codex_e_nao_no_navegador(self):
        cod = self.python_dentro("import json,os;print(json.dumps(sorted(os.listdir('/trabalho'))))", modo="codex-exec")
        self.assertEqual(cod, ["projeto", "saida"])
        nav = self.python_dentro("import json,os;print(json.dumps(sorted(os.listdir('/trabalho'))))")
        self.assertEqual(nav, ["saida"])

    def test_perfil_do_navegador_so_no_modo_que_o_usa(self):
        (self.estado / "navegador" / "perfil" / "marca").write_text("x", encoding="utf-8")
        login = self.python_dentro("import json,os;print(json.dumps(os.listdir('/home/jaula/perfil')))", modo="navegador-janela",
                                   variante="login")
        self.assertEqual(login, ["marca"])
        captcha = self.python_dentro("import json,os;print(json.dumps(sorted(os.listdir('/home/jaula'))))", modo="navegador-janela",
                                     variante="captcha")
        self.assertEqual(captcha, [])                                        # perfil temporário: HOME vazio
        canario = self.python_dentro("import json,os;print(json.dumps(sorted(os.listdir('/home/jaula'))))", modo="canario",
                                     como="navegador")
        self.assertEqual(canario, [])

    def test_capacidades_ambiente_e_pid1(self):
        dentro = self.python_dentro(
            "import json,os\nst=open('/proc/self/status').read()\ncap={l.split(':')[0]:int(l.split(':')[1],16) for l in st.splitlines() if l.startswith(('CapEff','CapPrm'))}\n"
            "print(json.dumps({'cap':cap,'env':sorted(os.environ),'pid1':open('/proc/1/cmdline','rb').read().split(b'\\0')[0].decode(),"
            "'pids':len([n for n in os.listdir('/proc') if n.isdigit()]),'pwd':os.environ.get('PWD')}))")
        self.assertEqual(dentro["cap"], {"CapEff": 0, "CapPrm": 0})
        self.assertTrue(dentro["pid1"].endswith("bwrap"))
        self.assertLess(dentro["pids"], 10)
        permitidos = {"PATH", "HOME", "TMPDIR", "LANG", "NO_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy",
                      "http_proxy", "all_proxy", "PLAYWRIGHT_BROWSERS_PATH", "CODEX_HOME"}
        # PWD não é da lista fixa: quem o define é o próprio bubblewrap, depois do --chdir (o --unsetenv não o tira). Vale só
        # com o valor /trabalho, a pasta atual da jaula.
        self.assertEqual(set(dentro["env"]) - permitidos - {"PWD"}, set())
        if "PWD" in dentro["env"]:
            self.assertEqual(dentro["pwd"], "/trabalho")
        self.assertFalse({n for n in dentro["env"] if "KEY" in n or "TOKEN" in n or "SSH" in n or "DISPLAY" in n})

    def test_sem_terminal_herdado_e_sem_userns_aninhado_no_codex(self):
        dentro = self.python_dentro(
            "import ctypes,json,os\ntry:\n    os.close(os.open('/dev/tty',os.O_RDWR));tty='abriu'\nexcept OSError as e:\n    tty=e.errno\n"
            "pid=os.fork()\nif pid==0:\n    os._exit(0 if ctypes.CDLL(None).unshare(0x10000000)==0 else 1)\n"
            "_,st=os.waitpid(pid,0)\nprint(json.dumps({'tty':tty,'userns':os.WEXITSTATUS(st)==0}))", modo="codex-exec")
        self.assertNotEqual(dentro["tty"], "abriu")
        self.assertFalse(dentro["userns"], "o namespace de usuário aninhado deveria estar bloqueado no Codex (--disable-userns)")

    # --- a rede ------------------------------------------------------------------------------------------------------
    def test_sem_rede_direta_e_sem_sockets_alem_do_proxy(self):
        dentro = self.python_dentro(
            "import json,socket\nr={}\nfor nome,fam,tipo,dest in [('v4',socket.AF_INET,socket.SOCK_STREAM,('1.1.1.1',443)),"
            "('v6',socket.AF_INET6,socket.SOCK_STREAM,('2606:4700::1111',443)),('udp',socket.AF_INET,socket.SOCK_DGRAM,('8.8.8.8',53))]:\n"
            "    s=socket.socket(fam,tipo);s.settimeout(3)\n    try:\n        s.connect(dest);r[nome]='saiu'\n"
            "    except OSError as e:\n        r[nome]=e.errno\nprint(json.dumps(r))")
        import errno
        sem_rota = {errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EAFNOSUPPORT, errno.EADDRNOTAVAIL, errno.EACCES, errno.EPERM}
        for nome, valor in dentro.items():
            self.assertIn(valor, sem_rota, f"{nome}: {valor}")

    def pedir(self, alvo: str, extra: str = "") -> int | None:
        codigo = ("import json,socket,sys\ns=socket.create_connection(('127.0.0.1',3128),timeout=20)\n"
                  "s.sendall(('CONNECT %s HTTP/1.1\\r\\nHost: x\\r\\n\\r\\n').encode())\nb=s.recv(4096)\n"
                  "print(json.dumps(int(b.split(b' ')[1]) if b.startswith(b'HTTP/1.') else None))" % alvo)
        return self.python_dentro(codigo, modo="codex-exec", com_proxy=True)

    def test_n_nav_2_e_n_cdx_2_o_proxy_dentro_da_jaula_recusa_o_que_esta_fora_da_lista(self):
        self.subir_proxy("api.exemplo.org")
        for alvo in ("example.com:443", "chatgpt.com:443", "127.0.0.1:443", "[::1]:443", "localhost:443",
                     "169.254.169.254:80", "api.exemplo.org:22"):
            with self.subTest(alvo=alvo):
                self.assertEqual(self.pedir(alvo), 403)
        registro = (self.estado / "proxy" / "registro.jsonl").read_text(encoding="ascii")
        self.assertGreaterEqual(registro.count('"recusado"'), 7)

    def test_a_ponte_para_o_proxy_nao_chega_ao_socket_fora_do_que_foi_montado(self):
        self.subir_proxy("api.exemplo.org")
        dentro = self.python_dentro(
            "import json,os,socket\ns=socket.socket(socket.AF_UNIX);r={}\nfor p in ['/run/jaula/proxy.sock']:\n"
            "    try:\n        s.connect(p);r[p]='conectou'\n    except OSError as e:\n        r[p]=e.errno\n"
            "for ab in ['\\0/tmp/.X11-unix/X0','\\0/run/dbus/system_bus_socket']:\n    t=socket.socket(socket.AF_UNIX)\n"
            "    try:\n        t.connect(ab);r[ab]='conectou'\n    except OSError as e:\n        r[ab]=e.errno\nprint(json.dumps(r))", com_proxy=True)
        self.assertEqual(dentro["/run/jaula/proxy.sock"], "conectou")
        self.assertNotIn("conectou", [v for k, v in dentro.items() if k != "/run/jaula/proxy.sock"])

    # --- o canário completo dentro da jaula (opcional: pede DNS real) -----------------------------------------------
    def test_n_jau_3_canario_dentro_da_jaula(self):
        dominio = os.environ.get("FUNDACAO_JAULA_DOMINIO")
        if not dominio:
            self.skipTest("defina FUNDACAO_JAULA_DOMINIO com um domínio real (ex.: um da ficha) para rodar o canário completo")
        J = self.J
        shutil.copy(WSL / "canario_jaula.py", self.base / "prog" / "canario_jaula.py")
        self.subir_proxy(dominio)
        perfil = J.perfil_do_modo("canario", None, "navegador")
        visiveis, _ = J.ambiente_do_modo(self.cfg, perfil)
        fds = {d: J._memfd("jaula", dados) for d, dados in J.conteudos_gerados(os.getuid(), os.getgid()).items()}
        self.fds += list(fds.values())
        comando = ["/usr/bin/python3", "-I", "-B", f"{self.cfg.programas}/canario_jaula.py", "--como", "navegador",
                   "--dominio", dominio, "--raiz", str(self.raiz), "--userns", "anotar", "--env", ",".join(sorted(visiveis))]
        argv = J.montar_argv(self.cfg, "criador", "pedido-0001", perfil, comando, fds=fds)
        r = subprocess.run(argv, capture_output=True, env={}, pass_fds=tuple(fds.values()), timeout=240)
        relatorio = json.loads(r.stdout.decode("utf-8"))
        reprovados = [(i["id"], i["motivo"]) for i in relatorio["itens"] if not i["aprovado"]]
        self.assertEqual(reprovados, [], "itens do canário da jaula reprovados")
        self.assertTrue(relatorio["aprovado"])


if __name__ == "__main__":
    unittest.main()
