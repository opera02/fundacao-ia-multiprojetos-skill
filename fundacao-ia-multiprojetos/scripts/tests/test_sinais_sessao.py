"""Sinais próprios do host em subprocessos fictícios; sem serviço, rede ou host real."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from apoio import ENV, SKILL
from test_host_perfis import carregar

HOOK = SKILL / "assets" / "hooks" / "sinais_sessao.py"


class SinaisSessao(unittest.TestCase):
    def rodar(self, entrada, *, projeto="ensaio-ficticio", status=False, extra=None):
        env = {k: v for k, v in ENV.items() if not k.startswith("FUNDACAO_")}
        if projeto is not None:
            env["FUNDACAO_PROJECT"] = projeto
        env.update(extra or {})
        return subprocess.run([sys.executable, "-I", "-B", str(HOOK), *(["--status-line"] if status else [])],
                              input=entrada if isinstance(entrada, bytes) else json.dumps(entrada).encode(),
                              capture_output=True, env=env, timeout=5)

    def test_compact_lembra_conferencia_sem_declarar_conclusao(self):
        r = self.rodar({"hook_event_name": "SessionStart", "source": "compact"})
        self.assertEqual(r.returncode, 0, r.stderr)
        saida = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(saida["hookEventName"], "SessionStart")
        texto = saida["additionalContext"]
        for esperado in ("ensaio-ficticio", "RETOMADA.md", "arquivos citados", "autorização", "compactação"):
            self.assertIn(esperado, texto)
        self.assertNotIn("concluído", texto.lower())
        self.assertLess(len(r.stdout), 1200)

    def test_outros_inicios_validos_nao_injetam_contexto(self):
        for source in ("startup", "resume", "clear", "fork"):
            with self.subTest(source=source):
                r = self.rodar({"hook_event_name": "SessionStart", "source": source})
                self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b"", b""))

    def test_status_usa_so_o_projeto_do_lancador_e_o_ponteiro(self):
        r = self.rodar({"cwd": "C:/Perfis/SEGREDO", "project": "outro-projeto", "cost": {"tokens": 999},
                        "model": {"display_name": "SEGREDO"}, "transcript_path": "SEGREDO"}, status=True)
        self.assertEqual((r.returncode, r.stderr), (0, b""))
        self.assertEqual(r.stdout, b"Fundacao | projeto: ensaio-ficticio | retomada: RETOMADA.md\n")

    def test_projeto_ausente_ou_invalido_falha_sem_ecoar(self):
        for projeto in (None, "", "../outro", "x..y", "Caso", "a\nSEGREDO", "a\x1b[31m", "a" * 65):
            for status in (False, True):
                with self.subTest(projeto=projeto, status=status):
                    r = self.rodar({"hook_event_name": "SessionStart", "source": "compact"},
                                   projeto=projeto, status=status)
                    self.assertEqual(r.returncode, 2)
                    self.assertEqual(r.stdout, b"")
                    self.assertEqual(r.stderr, b"sinais_sessao: entrada ou projeto invalido\n")

    def test_json_invalido_duplicado_profundo_ou_excessivo_falha_sem_ecoar(self):
        entradas = (b"", b"SEGREDO", b"[]", b"null", b'{} {}', b'{"x":NaN}',
                    b'{"source":"compact","source":"resume"}', b'{"x":"' + b"a" * 65536 + b'"}',
                    b'{"x":' + b'[' * 1100 + b'0' + b']' * 1100 + b'}', b'{"x":"\xff"}')
        for entrada in entradas:
            for status in (False, True):
                with self.subTest(tamanho=len(entrada), status=status):
                    r = self.rodar(entrada, status=status)
                    self.assertEqual(r.returncode, 2)
                    self.assertEqual(r.stdout, b"")
                    self.assertEqual(r.stderr, b"sinais_sessao: entrada ou projeto invalido\n")

    def test_evento_nao_e_fonte_de_projeto_nem_de_caminho(self):
        r = self.rodar({"hook_event_name": "SessionStart", "source": "compact", "project": "outro",
                        "cwd": "SEGREDO", "transcript_path": "SEGREDO", "additionalContext": "SEGREDO"})
        self.assertEqual(r.returncode, 0)
        self.assertNotIn(b"SEGREDO", r.stdout + r.stderr)
        self.assertNotIn(b"outro", r.stdout)
        for evento in ({}, {"hook_event_name": "PreToolUse", "source": "compact"},
                       {"hook_event_name": "SessionStart", "source": "SEGREDO"}):
            self.assertEqual(self.rodar(evento).returncode, 2)

    def test_repetido_e_deterministico_e_nao_abre_arquivos_nem_rede(self):
        # A auditoria é instalada após importar o código próprio; impede até a tentativa de abrir qualquer dado.
        wrapper = ("import runpy,sys; m=runpy.run_path(sys.argv[1]); "
                   "sys.addaudithook(lambda e,a: (_ for _ in ()).throw(RuntimeError('IO negada')) "
                   "if e in ('open','os.listdir','os.scandir','socket.__new__','subprocess.Popen') else None); "
                   "raise SystemExit(m['main']([]))")
        env = {k: v for k, v in ENV.items() if not k.startswith("FUNDACAO_")}
        env["FUNDACAO_PROJECT"] = "ensaio-ficticio"
        evento = {"hook_event_name": "SessionStart", "source": "compact", "transcript_path": "nao-ler"}
        with tempfile.TemporaryDirectory(prefix="sinais-sem-dados-") as pasta:
            resultados = [subprocess.run([sys.executable, "-I", "-B", "-c", wrapper, str(HOOK)],
                                        input=json.dumps(evento).encode(), capture_output=True, env=env,
                                        cwd=pasta, timeout=5) for _ in range(2)]
        for r in resultados:
            self.assertEqual((r.returncode, r.stderr), (0, b""))
        self.assertEqual(resultados[0].stdout, resultados[1].stdout)

    def test_pipe_que_nao_fecha_tem_prazo_interno(self):
        env = {k: v for k, v in ENV.items() if not k.startswith("FUNDACAO_")}
        env["FUNDACAO_PROJECT"] = "ensaio-ficticio"
        inicio = time.monotonic()
        p = subprocess.Popen([sys.executable, "-I", "-B", str(HOOK)], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        try:
            p.stdin.write(b'{"hook_event_name":"SessionStart","source":"compact"}')
            p.stdin.flush()
            p.wait(timeout=4)
            self.assertEqual(p.returncode, 2)
            self.assertLess(time.monotonic() - inicio, 3)
            self.assertEqual(p.stdout.read(), b"")
        finally:
            if p.poll() is None:
                p.kill()
            p.communicate()


class IntegracaoDosSinais(unittest.TestCase):
    def test_modelos_tem_compact_exec_form_e_status_sem_relaxar_guardas(self):
        m = carregar()
        perfis = (m.perfil_windows(raiz=r"E:\Raiz Ficticia", python=r"C:\Py\python.exe"),
                  m.perfil_wsl(raiz="/tmp/raiz-ficticia", projeto="ficticio", perfil_windows="/tmp/perfil",
                               outros_projetos=[]))
        for perfil in perfis:
            with self.subTest(perfil=perfil["hooks"]):
                grupo = perfil["hooks"]["SessionStart"]
                self.assertEqual(len(grupo), 1)
                self.assertEqual(grupo[0]["matcher"], "compact")
                hook = grupo[0]["hooks"][0]
                self.assertEqual(hook["args"][-1].split("/")[-1].split("\\")[-1], "sinais_sessao.py")
                self.assertEqual(hook["args"][:2], ["-I", "-B"])
                self.assertEqual(hook["timeout"], 3)
                self.assertEqual(hook["onFailure"], "block")
                self.assertIn("statusLine", perfil)
                self.assertEqual(perfil["statusLine"]["type"], "command")
                self.assertNotIn("FUNDACAO_PROJECT", perfil["env"])
                self.assertEqual(len(perfil["hooks"]["PreToolUse"]), 2)
        self.assertEqual(m.conferir_perfil_wsl(perfis[1], "/tmp/raiz-ficticia", "ficticio", []), [])
        perfis[1]["hooks"]["SessionStart"][0]["hooks"][0]["onFailure"] = "continue"
        self.assertTrue(m.conferir_perfil_wsl(perfis[1], "/tmp/raiz-ficticia", "ficticio", []))

    @unittest.skipUnless(os.name == "nt", "comando do modelo Windows: somente Windows")
    def test_status_windows_preserva_entrada_e_caminho_com_metacaracteres(self):
        m = carregar()
        env = {k: v for k, v in ENV.items() if not k.startswith("FUNDACAO_")}
        env["FUNDACAO_PROJECT"] = "ficticio"
        with tempfile.TemporaryDirectory(prefix="status ' $() ` ficticio-") as pasta:
            raiz = Path(pasta)
            hooks = raiz / ".claude" / "hooks"
            hooks.mkdir(parents=True)
            shutil.copyfile(HOOK, hooks / HOOK.name)
            perfil = m.perfil_windows(raiz=str(raiz), python=sys.executable)
            r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                                perfil["statusLine"]["command"]], input=b'{"cwd":"SEGREDO"}',
                               capture_output=True, env=env, timeout=10)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(r.stdout.replace(b"\r\n", b"\n"),
                             b"Fundacao | projeto: ficticio | retomada: RETOMADA.md\n")
            self.assertFalse(r.stderr)

    @unittest.skipIf(os.name == "nt", "comando do modelo WSL: somente Linux")
    def test_status_wsl_preserva_entrada_e_caminho_com_metacaracteres(self):
        m = carregar()
        env = {k: v for k, v in ENV.items() if not k.startswith("FUNDACAO_")}
        env["FUNDACAO_PROJECT"] = "ficticio"
        with tempfile.TemporaryDirectory(prefix="status ' $() ` ficticio-") as pasta:
            raiz = Path(pasta)
            hooks = raiz / ".claude" / "hooks"
            hooks.mkdir(parents=True)
            shutil.copyfile(HOOK, hooks / HOOK.name)
            perfil = m.perfil_wsl(raiz=str(raiz), projeto="ficticio", perfil_windows="/tmp/perfil-ficticio",
                                  outros_projetos=[])
            r = subprocess.run(["/bin/sh", "-c", perfil["statusLine"]["command"]],
                               input=b'{"cwd":"SEGREDO"}', capture_output=True, env=env, timeout=10)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(r.stdout, b"Fundacao | projeto: ficticio | retomada: RETOMADA.md\n")
            self.assertFalse(r.stderr)


if __name__ == "__main__":
    unittest.main()
