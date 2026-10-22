"""Revisão de segurança da 1.7.7, terceira passada: variantes que as correções da segunda deixaram passar.

- R177C-FB-01 (baixa): no plano de execução do fluxo B (`scripts/codigo_do_plano.py`), variável que muda de onde o
  código é carregado atribuída no próprio comando, por um programa que o plano não lê (`env PYTHONPATH=<fora>
  python3 app.py {entrada}`, também no `-S` do `env` e no valor de opção), ou no código do `sh -c`, deixava a folha
  dizendo "preso"; o `-C` do `env` (outra pasta de trabalho) também. No WSL o bubblewrap não monta a pasta de fora, e o
  código não roda; sem isolamento, roda. Agora o plano marca o código como NÃO PRESO, com o motivo, como a variável
  pedida com `--variavel` [R177B-B-02].

Programas e dados fictícios, em pastas descartáveis; os planos são montados sem isolamento (nada roda).
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import SCRIPTS

MOTIVO = "revisão da 1.7.7, terceira passada: programas fictícios do próprio teste"


def carregar(nome: str):
    spec = importlib.util.spec_from_file_location(f"_revisao_177c_{nome}", SCRIPTS / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class TestC01VariavelAtribuidaNoComando(unittest.TestCase):
    def setUp(self):
        self.ex = carregar("execucao_isolada")
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="r177c-fb01-")))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.copia = self.base / "copia"
        (self.copia / "entradas").mkdir(parents=True)
        (self.copia / "entradas" / "um.json").write_text("{}", encoding="utf-8")
        self.app = self.copia / "app.py"
        self.app.write_text("import sys\nprint('da cópia', sys.argv[1:])\n", encoding="utf-8")
        (self.copia / "app.js").write_text("console.log('ok')\n", encoding="utf-8")
        r = subprocess.run([sys.executable, "-B", str(SCRIPTS / "manifesto.py"), "criar", "--raiz", str(self.copia),
                            "--saida", str(self.base / "manifesto.json")], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.fora = self.base / "fora"  # a pasta de fora da cópia de onde viria o código
        self.fora.mkdir()
        sistema = self.base / "sistema"  # programas de mentira, só para o plano (nada roda)
        sistema.mkdir()
        for nome in ("env", "sh", "systemd-run"):
            (sistema / nome).write_bytes(b"programa ficticio\n")
        self.env, self.sh, self.run = sistema / "env", sistema / "sh", sistema / "systemd-run"

    def plano(self, comando) -> dict:
        return self.ex.montar_plano("gravar", [str(c) for c in comando], copia=self.copia,
                                    manifesto=self.base / "manifesto.json", cwd=None,
                                    entradas=[str(self.copia / "entradas" / "um.json")], gravavel=None,
                                    limites=self.ex.limites(30), variaveis=[], sem_isolamento=MOTIVO)

    def test_c01_variavel_que_carrega_codigo_atribuida_no_comando_marca_nao_preso(self):
        folha = carregar("folha_do_plano")
        fora, app, env, sh = self.fora, self.app, self.env, self.sh
        nao_presos = {
            "env PYTHONPATH=<fora> python3 app.py": ([env, f"PYTHONPATH={fora}", "python3", app, "{entrada}"],
                                                     "PYTHONPATH"),
            "env -S 'PYTHONPATH=<fora> python3'": ([env, "-S", f"PYTHONPATH={fora} python3", app, "{entrada}"],
                                                   "PYTHONPATH"),
            "env -SPYTHONPATH=<fora>": ([env, f"-SPYTHONPATH={fora}", "python3", app, "{entrada}"], "PYTHONPATH"),
            "env -iS com a variável colada": ([env, f"-iSPYTHONSTARTUP={fora}/x.py", "python3", app], "PYTHONSTARTUP"),
            "env --split-string=LD_PRELOAD=<fora>": ([env, f"--split-string=LD_PRELOAD={fora}/x.so python3", app],
                                                     "LD_PRELOAD"),
            "env -i NODE_OPTIONS=--require=<fora>": ([env, "-i", f"NODE_OPTIONS=--require={fora}/x.js", "node",
                                                      self.copia / "app.js"], "NODE_OPTIONS"),
            "systemd-run --setenv=PYTHONPATH=<fora>": ([self.run, f"--setenv=PYTHONPATH={fora}", "python3", app],
                                                       "PYTHONPATH"),
            "env -C <fora> python3 app.py": ([env, "-C", fora, "python3", "app.py", "{entrada}"], "-C"),
            "env --chdir=<fora> python3 app.py": ([env, f"--chdir={fora}", "python3", "app.py"], "--chdir"),
            "env -iC <fora> python3 app.py": ([env, "-iC", fora, "python3", "app.py"], "-iC"),
            "sh -c 'PYTHONPATH=<fora> python3 app.py'": ([sh, "-c", f'PYTHONPATH={fora} python3 {app} "$1"', "sh",
                                                          "{entrada}"], "PYTHONPATH"),
            "sh -c 'export LD_PRELOAD=<fora>;...'": ([sh, "-c", f'export LD_PRELOAD={fora}/x.so;cat "$1"', "sh",
                                                      "{entrada}"], "LD_PRELOAD"),
        }
        for nome, (comando, motivo) in nao_presos.items():
            with self.subTest(nome):
                plano = self.plano(comando)
                self.assertTrue(plano["codigo_executado"].startswith("NÃO PRESO"), plano["codigo_executado"])
                self.assertIn(motivo, plano["codigo_executado"])
                texto = folha.para_a_folha(plano, "0" * 64)
                self.assertIn("ATENÇÃO: o código que o programa roda NÃO está preso", texto)
                self.assertIn(motivo, texto)

    def test_d4_variantes_do_env_que_mudam_a_pasta_marcam_nao_preso(self):
        # R177D-4 (conferência final): abreviação do --chdir que o getopt aceita, opção dentro do -S e o env atrás de
        # outro programa ainda deixavam a folha dizendo "preso".
        fora, env = self.fora, self.env
        nice, timeout = self.env.parent / "nice", self.env.parent / "timeout"
        for programa in (nice, timeout):
            programa.write_bytes(b"programa ficticio\n")
        nao_presos = {
            "env --ch=<fora>": [env, f"--ch={fora}", "python3", "app.py"],
            "env --chd <fora>": [env, "--chd", fora, "python3", "app.py"],
            "env -S--chdir=<fora> (o -S'--chdir=...' depois do shell)": [env, f"-S--chdir={fora}", "python3", "app.py"],
            "env -S '-i -C <fora>'": [env, "-S", f"-i -C {fora}", "python3", "app.py"],
            "nice env -C <fora>": [nice, "env", "-C", fora, "python3", "app.py"],
            "timeout 9 env --chdir=<fora>": [timeout, "9", "env", f"--chdir={fora}", "python3", "app.py"],
            "nice env PYTHONPATH=<fora>": [nice, "env", f"PYTHONPATH={fora}", "python3", "app.py"],
        }
        for nome, comando in nao_presos.items():
            with self.subTest(nome):
                plano = self.plano(comando)
                self.assertTrue(plano["codigo_executado"].startswith("NÃO PRESO"), plano["codigo_executado"])
        presos = {
            "env --config=x (não é o --chdir)": [env, "--config=x", "python3", self.app],
            "nice -n 5 python3 app.py": [nice, "-n", "5", "python3", self.app, "{entrada}"],
            "timeout 9 env python3 app.py": [timeout, "9", "env", "python3", self.app, "{entrada}"],
        }
        for nome, comando in presos.items():
            with self.subTest(nome):
                plano = self.plano(comando)
                self.assertTrue(plano["codigo_executado"].startswith("preso pelo manifesto"), plano["codigo_executado"])

    def test_c01_variavel_que_nao_carrega_codigo_ou_depois_do_script_continua_preso(self):
        presos = {
            "env NODE_ENV=production TZ=UTC python3 app.py": [self.env, "NODE_ENV=production", "TZ=UTC", "python3",
                                                              self.app, "{entrada}"],
            "env -u LANG python3 app.py": [self.env, "-u", "LANG", "python3", self.app, "{entrada}"],
            "env python3 app.py PYTHONPATH=x (argumento do script)": [self.env, "python3", self.app,
                                                                      "PYTHONPATH=x", "{entrada}"],
            "sh -c 'NODE_ENV=production cat \"$1\"'": [self.sh, "-c", 'NODE_ENV=production cat "$1"', "sh",
                                                       "{entrada}"],
            "systemd-run --env=prod (opção, não variável)": [self.run, self.app, "--env=prod", "{entrada}"],
        }
        for nome, comando in presos.items():
            with self.subTest(nome):
                plano = self.plano(comando)
                self.assertTrue(plano["codigo_executado"].startswith("preso pelo manifesto"),
                                plano["codigo_executado"])


if __name__ == "__main__":
    unittest.main()
