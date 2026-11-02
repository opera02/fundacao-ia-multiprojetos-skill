"""R179-36 F3 e F4 (1.7.10): `inspecionar_ambiente.py --somente-localizar` não abre processo nenhum, e o docstring diz o
que o script lê.

O docstring e a SKILL.md diziam que, com --somente-localizar, o inventário não executa programa externo, mas
`platform.platform()` desempacotava o `uname()` em seis campos e forçava o `processor` preguiçoso, que no Linux roda
`uname -p` (CPython, `platform._Processor.from_subprocess`); no Windows, o `uname()` do `platform` roda `ver` quando a
consulta WMI falha. O docstring dizia também que o script não lia valores de variáveis de ambiente. O teste de antes
(`test_environment_inventory_only_when_request_allows_probing_host`) conferia o texto e a presença de `/proc/mounts` no
código, não o comportamento.

Aqui o script roda num processo novo com dublês postos antes dele: `subprocess` (Popen, run, call, check_call,
check_output, getoutput, getstatusoutput) e `os` (system, popen, fork, spawn*, exec*, posix_spawn, startfile). Cada
tentativa de abrir processo fica registrada e é recusada: nada roda. Nos dois sistemas (a suíte roda no Windows e no
Ubuntu); no Windows, também com a consulta WMI falhando. Os controles provam que os dublês pegam o que deveriam: o
`platform.platform()` antigo (`uname -p` no Linux, `ver` no Windows sem WMI) e o `--version` do modo sem
--somente-localizar. Da revisão independente do pacote (1.7.10): o programa posto na pasta atual não é localizado nem
executado, nos dois modos (antes, sem NoDefaultCurrentDirectoryInExePath no Windows ou com entrada vazia no PATH, um
`git` falso ali rodava com --version). Pastas temporárias; nada fora delas é gravado."""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import ENV, SCRIPTS

SCRIPT = SCRIPTS / "inspecionar_ambiente.py"
NO_LINUX = sys.platform.startswith("linux")
NO_WINDOWS = sys.platform == "win32"

DUBLES = '''\
"""Dublês de processo do teste do inventário: toda tentativa de abrir processo fica registrada e é recusada."""
import json
import os
import runpy
import subprocess
import sys

registro, sem_wmi, alvo, *argumentos = sys.argv[1:]
tentativas = []


def recusar(nome):
    def recusado(*args, **kwargs):
        primeiro = args[0] if args else kwargs.get("args")
        if isinstance(primeiro, (list, tuple)):
            primeiro = [str(x) for x in primeiro]
        elif primeiro is not None:
            primeiro = str(primeiro)
        tentativas.append([nome, primeiro])
        raise OSError("processo recusado pelo dublê do teste: " + nome)
    return recusado


class PopenRecusado:
    def __init__(self, *args, **kwargs):
        recusar("subprocess.Popen")(*args, **kwargs)


subprocess.Popen = PopenRecusado
for nome in ("run", "call", "check_call", "check_output", "getoutput", "getstatusoutput"):
    setattr(subprocess, nome, recusar("subprocess." + nome))
for nome in ("system", "popen", "fork", "forkpty", "posix_spawn", "posix_spawnp", "startfile",
             "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe",
             "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe"):
    if hasattr(os, nome):
        setattr(os, nome, recusar("os." + nome))
if sem_wmi == "1":
    try:
        import _wmi
    except ImportError:
        pass
    else:
        def wmi_indisponivel(*args, **kwargs):
            raise OSError("WMI indisponível (simulado pelo teste)")
        _wmi.exec_query = wmi_indisponivel

codigo, extra = 0, {}
sys.argv = [alvo, *argumentos]
try:
    if alvo == "--controle-platform":
        import platform
        platform.platform()
    elif alvo == "--controle-which":
        import shutil
        extra["which"] = shutil.which(argumentos[0])
    else:
        runpy.run_path(alvo, run_name="__main__")
except SystemExit as exc:
    codigo = exc.code if isinstance(exc.code, int) else 1
with open(registro, "w", encoding="utf-8") as fh:
    json.dump({"tentativas": tentativas, "codigo": codigo, **extra}, fh)
'''
VARIAVEL_DA_PASTA_ATUAL = "NoDefaultCurrentDirectoryInExePath"


def carregar():
    spec = importlib.util.spec_from_file_location("inspecionar_ambiente_179", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestInventarioSemProcesso(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="inventario-179-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.pasta, self.trabalho, apoio = self.base / "raiz", self.base / "cwd", self.base / "dubles"
        for pasta in (self.pasta, self.trabalho, apoio):
            pasta.mkdir()
        self.dubles = apoio / "dubles.py"
        self.dubles.write_text(DUBLES, encoding="utf-8", newline="\n")
        self.rodadas = 0

    def rodar(self, alvo, *args, sem_wmi: bool = False, env: dict | None = None):
        self.rodadas += 1
        registro = self.base / f"registro-{self.rodadas}.json"
        p = subprocess.run([sys.executable, "-I", "-B", str(self.dubles), str(registro), "1" if sem_wmi else "0",
                            str(alvo), *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=str(self.trabalho), env=ENV if env is None else env, timeout=120)
        self.assertTrue(registro.is_file(), p.stderr[-3000:])
        return p, json.loads(registro.read_text(encoding="utf-8"))

    def test_somente_localizar_nao_abre_processo(self):
        for sem_wmi in ((False, True) if NO_WINDOWS else (False,)):
            with self.subTest(sem_wmi=sem_wmi):
                p, dados = self.rodar(SCRIPT, "--pasta", self.pasta, "--somente-localizar", sem_wmi=sem_wmi)
                self.assertEqual(dados, {"tentativas": [], "codigo": 0}, p.stderr[-3000:])
                inventario = json.loads(p.stdout)
                self.assertEqual(inventario["schema_version"], "fundacao.inventario_ambiente/1")
                self.assertEqual(set(inventario["sistema"]), {"plataforma", "maquina", "cpus", "ram_bytes"})
                self.assertTrue(inventario["sistema"]["plataforma"])
                for nome, entrada in inventario["programas"].items():
                    self.assertFalse({"versao", "listagem", "distribuicoes"} & set(entrada), nome)
        self.assertEqual(list(self.pasta.rglob("*")) + list(self.trabalho.rglob("*")), [])  # nada gravado

    @unittest.skipUnless(NO_LINUX, "o processor preguiçoso roda `uname -p` fora do Windows")
    def test_controle_o_platform_antigo_abre_uname_no_linux(self):
        _, dados = self.rodar("--controle-platform")
        self.assertIn(["subprocess.check_output", ["uname", "-p"]], dados["tentativas"])

    @unittest.skipUnless(NO_WINDOWS, "a consulta WMI e o comando `ver` são do Windows")
    def test_controle_o_platform_antigo_roda_ver_no_windows_sem_wmi(self):
        _, dados = self.rodar("--controle-platform", sem_wmi=True)
        self.assertIn(["subprocess.check_output", "ver"], dados["tentativas"])

    def test_controle_sem_somente_localizar_os_dubles_pegam_o_version(self):
        presentes = {n: shutil.which(n) for n in carregar().SAFE_VERSION if shutil.which(n)}
        if not presentes:
            self.skipTest("nenhum dos programas de versão está no PATH deste ambiente")
        p, dados = self.rodar(SCRIPT, "--pasta", self.pasta)
        self.assertEqual(dados["codigo"], 0, p.stderr[-3000:])
        inventario = json.loads(p.stdout)
        for nome in presentes:
            with self.subTest(programa=nome):
                caminho = inventario["programas"][nome]["caminho"]
                self.assertIn(["subprocess.run", [caminho, "--version"]], dados["tentativas"])
                self.assertEqual(inventario["programas"][nome]["versao"], {"executado": False, "erro": "OSError"})

    def na_pasta_atual(self, caminho) -> bool:
        return caminho is not None and (self.trabalho / caminho).resolve().parent == self.trabalho.resolve()

    def test_programa_posto_na_pasta_atual_nao_e_localizado_nem_executado(self):
        # Revisão do pacote (1.7.10): sem NoDefaultCurrentDirectoryInExePath (o terminal comum não a define; a sessão
        # do Claude Code, sim), o shutil.which do Windows olha antes a pasta atual; nos dois sistemas, a entrada vazia
        # do PATH é a pasta atual. Um `git` falso posto ali (código importado, por exemplo) rodava com --version.
        falso = self.trabalho / ("git.bat" if NO_WINDOWS else "git")
        falso.write_text("@echo off\r\necho falso\r\n" if NO_WINDOWS else "#!/bin/sh\necho falso\n", encoding="utf-8")
        falso.chmod(0o755)
        env = {k: v for k, v in ENV.items() if k.upper() != VARIAVEL_DA_PASTA_ATUAL.upper()}
        env["PATH"] = os.pathsep + env.get("PATH", "")  # entrada vazia primeiro: a pasta atual
        _, controle = self.rodar("--controle-which", "git", env=env)
        self.assertTrue(self.na_pasta_atual(controle["which"]), controle)  # o cenário existe: o which acha o falso
        for args in ((), ("--somente-localizar",)):
            with self.subTest(args=args):
                p, dados = self.rodar(SCRIPT, "--pasta", self.pasta, *args, env=env)
                self.assertEqual(dados["codigo"], 0, p.stderr[-3000:])
                git = json.loads(p.stdout)["programas"]["git"]
                self.assertFalse(self.na_pasta_atual(git["caminho"]), git)
                self.assertTrue(git["caminho"] is None or os.path.isabs(git["caminho"]), git)
                executados = [t[1][0] if isinstance(t[1], list) else t[1] for t in dados["tentativas"]]
                self.assertFalse([x for x in executados if self.na_pasta_atual(x)], dados["tentativas"])
                real = shutil.which("git", path=os.pathsep.join(
                    x for x in env["PATH"].split(os.pathsep) if x and os.path.isabs(x)))
                if real:  # reconferência: o git de verdade, das pastas absolutas do PATH, continua localizado
                    self.assertEqual(os.path.normcase(git["caminho"] or ""), os.path.normcase(real), git)
                if git["caminho"] and not args:  # o git de verdade, do PATH, continua consultado
                    self.assertIn(["subprocess.run", [git["caminho"], "--version"]], dados["tentativas"])


class TestDocstringDoInventario(unittest.TestCase):
    def setUp(self):
        self.arvore = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        self.doc = ast.get_docstring(self.arvore)

    def test_docstring_lista_as_variaveis_de_ambiente_que_o_codigo_le(self):
        lidas = set()
        for no in ast.walk(self.arvore):
            if (isinstance(no, ast.Call) and no.args and isinstance(no.args[0], ast.Constant)
                    and ast.unparse(no.func) in ("os.environ.get", "os.getenv")):
                lidas.add(no.args[0].value)
            elif (isinstance(no, ast.Compare) and isinstance(no.left, ast.Constant) and len(no.ops) == 1
                  and isinstance(no.ops[0], (ast.In, ast.NotIn)) and ast.unparse(no.comparators[0]) == "os.environ"):
                lidas.add(no.left.value)
        self.assertGreaterEqual(lidas, {"CODESPACES", "REMOTE_CONTAINERS", "SHELL", "PYTHONUTF8", "COMSPEC",
                                        "PSModulePath"})
        for nome in sorted(lidas | {"PATH"}):  # PATH: pelo shutil.which
            with self.subTest(variavel=nome):
                self.assertIn(nome, self.doc)
        self.assertNotIn("nem valores de variáveis de ambiente", self.doc)  # a frase que não era verdade
        for trecho in ("/proc/version", "/proc/mounts", "registro (LongPathsEnabled)", "não executa programa externo"):
            self.assertIn(trecho, self.doc)

    def test_codigo_nao_chama_o_platform_que_abre_processo(self):
        chamadas = {ast.unparse(no.func) for no in ast.walk(self.arvore) if isinstance(no, ast.Call)}
        self.assertEqual(chamadas & {"platform.platform", "platform.uname", "platform.processor"}, set())
        self.assertTrue({"platform.system", "platform.release", "platform.machine"} <= chamadas)

    def test_shutil_which_so_dentro_do_localizar(self):
        # Revisão do pacote (1.7.10): a busca de programa passa toda pelo `localizar`, que não olha a pasta atual.
        fora = []
        for funcao in self.arvore.body:
            for no in ast.walk(funcao):
                if isinstance(no, ast.Call) and ast.unparse(no.func) == "shutil.which":
                    fora += [] if getattr(funcao, "name", None) == "localizar" else [getattr(funcao, "name", "?")]
        self.assertEqual(fora, [])
        self.assertIn(VARIAVEL_DA_PASTA_ATUAL, self.doc)
        self.assertIn("a pasta atual não entra", self.doc)


if __name__ == "__main__":
    unittest.main()
