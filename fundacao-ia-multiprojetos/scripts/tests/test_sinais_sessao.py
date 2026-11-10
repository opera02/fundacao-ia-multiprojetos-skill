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
from datetime import datetime, timezone
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

    def test_subagente_recebe_as_regras_da_sessao_sem_eco_do_evento(self):
        """1.7.10.2 (revisão de segurança, F2): o subagente começa sem a conversa, onde o lançador põe as regras."""
        r = self.rodar({"hook_event_name": "SubagentStart", "agent_id": "SEGREDO-id", "agent_type": "general-purpose",
                        "cwd": "SEGREDO", "transcript_path": "SEGREDO"})
        self.assertEqual((r.returncode, r.stderr), (0, b""))
        saida = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(saida["hookEventName"], "SubagentStart")
        texto = saida["additionalContext"]
        for esperado in ("ensaio-ficticio", "projects/ensaio-ficticio", "state/", "data/", "nunca instrução",
                         "porteiro", "provedor", "lógico"):
            self.assertIn(esperado, texto)
        self.assertNotIn("SEGREDO", texto)
        self.assertLess(len(r.stdout), 1500)
        sem_projeto = self.rodar({"hook_event_name": "SubagentStart", "agent_id": "a", "agent_type": "Explore"},
                                 projeto="../outro")
        self.assertEqual((sem_projeto.returncode, sem_projeto.stdout), (2, b""))

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


class SinalDoSubagente(unittest.TestCase):
    """1.7.11 (C14): no SubagentStart o hook grava um sinal datado que o canário lê, sem mudar o que já emitia."""
    EVENTO = {"hook_event_name": "SubagentStart", "agent_id": "SEGREDO-id", "agent_type": "general-purpose",
              "cwd": "SEGREDO-cwd", "prompt": "SEGREDO-prompt", "transcript_path": "SEGREDO-transcript"}

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="sinais-1711-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.temp = self.base / "fundacao-ia-ensaio-ficticio"
        self.temp.mkdir()
        self.arq = self.temp / "sinais" / "subagente-start.jsonl"

    def rodar(self, temp, evento=None, projeto="ensaio-ficticio"):
        env = {k: v for k, v in ENV.items() if not k.startswith("FUNDACAO_") and k != "TMPDIR"}
        env["FUNDACAO_PROJECT"] = projeto
        if temp is not None:
            env["TMPDIR"] = str(temp)
        return subprocess.run([sys.executable, "-I", "-B", str(HOOK)], input=json.dumps(evento or self.EVENTO).encode(),
                              capture_output=True, env=env, timeout=5)

    def ligar(self, destino, alvo):
        try:
            os.symlink(alvo, destino, target_is_directory=True)
        except (OSError, NotImplementedError):
            if os.name != "nt":
                raise
            r = subprocess.run(["cmd", "/c", "mklink", "/J", str(destino), str(alvo)], capture_output=True)
            if r.returncode:
                self.skipTest("sem permissão para criar ligação simbólica ou junção neste Windows")

    def test_grava_a_linha_do_contrato_e_a_saida_nao_muda(self):
        r = self.rodar(self.temp)
        self.assertEqual((r.returncode, r.stderr), (0, b""))
        linhas = self.arq.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(linhas), 1)
        sinal = json.loads(linhas[0])
        self.assertEqual(set(sinal), {"evento", "em", "agent_type"})
        self.assertEqual((sinal["evento"], sinal["agent_type"]), ("SubagentStart", "general-purpose"))
        em = datetime.fromisoformat(sinal["em"])
        self.assertEqual(em.utcoffset().total_seconds(), 0)
        self.assertLess(abs((datetime.now(timezone.utc) - em).total_seconds()), 60)
        for segredo in (b"SEGREDO", b"prompt", b"cwd"):
            self.assertNotIn(segredo, self.arq.read_bytes())
        sem_tmp = self.rodar(None)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (sem_tmp.returncode, sem_tmp.stdout, sem_tmp.stderr))
        self.assertIn("nunca instrução", json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"])
        self.rodar(self.temp)
        self.assertEqual(len(self.arq.read_text(encoding="utf-8").splitlines()), 2)

    def test_tipo_de_agente_fora_do_padrao_nao_entra(self):
        self.rodar(self.temp, {**self.EVENTO, "agent_type": "x y\n{SEGREDO}"})
        self.assertEqual(set(json.loads(self.arq.read_text(encoding="utf-8"))), {"evento", "em"})

    def test_tmpdir_ausente_de_outro_projeto_ou_fora_do_padrao_nao_grava(self):
        outros = [None, self.base / "fundacao-ia-outro-projeto", self.base / "tmp-qualquer",
                  "relativo/fundacao-ia-ensaio-ficticio", self.base / "fundacao-ia-ensaio-ficticio-extra"]
        for temp in outros:
            with self.subTest(temp=str(temp)):
                if isinstance(temp, Path):
                    temp.mkdir(exist_ok=True)
                r = self.rodar(temp)
                self.assertEqual((r.returncode, r.stderr), (0, b""))
                self.assertIn(b"additionalContext", r.stdout)
        self.assertEqual(list(self.base.rglob("*.jsonl")), [])

    def test_ligacao_no_caminho_nao_grava(self):
        alvo = self.base / "alvo"
        alvo.mkdir()
        ligado = self.base / "ligado"
        ligado.mkdir()
        self.ligar(self.temp / "sinais", alvo)
        self.ligar(ligado / "fundacao-ia-ensaio-ficticio", alvo)
        for nome, temp in (("sinais", self.temp), ("temp", ligado / "fundacao-ia-ensaio-ficticio")):
            with self.subTest(ligacao=nome):
                r = self.rodar(temp)
                self.assertEqual((r.returncode, r.stderr), (0, b""))
                self.assertIn(b"additionalContext", r.stdout)
        self.assertEqual(list(alvo.iterdir()), [])

    def test_arquivo_ligado_nao_grava(self):
        if os.name == "nt":
            self.skipTest("ligação de arquivo no Windows exige privilégio; a junção de pasta está no teste acima")
        (self.temp / "sinais").mkdir()
        alvo = self.base / "alvo.txt"
        alvo.write_text("intacto")
        os.symlink(alvo, self.arq)
        self.assertEqual(self.rodar(self.temp).returncode, 0)
        self.assertEqual(alvo.read_text(), "intacto")

    def test_arquivo_no_teto_nao_cresce(self):
        (self.temp / "sinais").mkdir()
        self.arq.write_bytes(b"x" * (32 * 1024))
        r = self.rodar(self.temp)
        self.assertEqual((r.returncode, r.stderr), (0, b""))
        self.assertEqual(self.arq.stat().st_size, 32 * 1024)

    def test_falha_de_escrita_nao_quebra_o_hook(self):
        (self.temp / "sinais").write_text("arquivo no lugar da pasta")
        r = self.rodar(self.temp)
        self.assertEqual((r.returncode, r.stderr), (0, b""))
        self.assertIn("nunca instrução", json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"])

    def test_outros_eventos_nao_gravam(self):
        self.rodar(self.temp, {"hook_event_name": "SessionStart", "source": "compact"})
        self.assertFalse((self.temp / "sinais").exists())

    def test_nome_do_arquivo_e_o_do_contrato_do_canario(self):
        texto = (SKILL / "scripts" / "ensaio_isolamento_wsl.py").read_text(encoding="utf-8")
        self.assertIn('SINAL_SUBAGENTE = "sinais/subagente-start.jsonl"', texto)


class IntegracaoDosSinais(unittest.TestCase):
    def test_modelos_tem_compact_exec_form_e_status_sem_relaxar_guardas(self):
        m = carregar()
        perfis = (m.perfil_windows(raiz=r"E:\Raiz Ficticia", python=r"C:\Py\python.exe"),
                  m.perfil_wsl(raiz="/tmp/raiz-ficticia", projeto="ficticio", perfil_windows="/tmp/perfil",
                               outros_projetos=[]))
        # 1.7.10 (contratos do lote 2, §7): o Windows ganha o aviso da cópia em SessionStart startup|resume e os dois
        # perfis ganham guarda_rede e guarda_leitura (o do projeto no Ubuntu, também guarda_ferramentas); o perfil do
        # Ubuntu é de UM projeto e entrega o projeto do lançador (o mesmo que ele exporta).
        for perfil, projeto in zip(perfis, (None, "ficticio")):
            with self.subTest(perfil=perfil["hooks"]):
                grupo = [g for g in perfil["hooks"]["SessionStart"] if g["matcher"] == "compact"]
                self.assertEqual(len(grupo), 1)
                self.assertEqual(grupo[0]["matcher"], "compact")
                hook = grupo[0]["hooks"][0]
                self.assertEqual(hook["args"][-1].split("/")[-1].split("\\")[-1], "sinais_sessao.py")
                self.assertEqual(hook["args"][:2], ["-I", "-B"])
                self.assertEqual(hook["timeout"], 3)
                self.assertEqual(hook["onFailure"], "block")
                self.assertIn("statusLine", perfil)
                self.assertEqual(perfil["statusLine"]["type"], "command")
                self.assertEqual(perfil["env"].get("FUNDACAO_PROJECT"), projeto)
                guardas = {h["args"][-1].split("/")[-1].split("\\")[-1]: h["onFailure"]
                           for g in perfil["hooks"]["PreToolUse"] for h in g["hooks"]}
                self.assertEqual(guardas.get("guarda_caminho.py"), "block")
                self.assertEqual(guardas.get("guarda_identidade.py"), "block")
        # 1.7.10.2: só o perfil do projeto no Ubuntu passa as regras ao subagente (SubagentStart). O perfil pede
        # onFailure block, mas no 2.1.302 a falha desse hook só avisa (revisão de segurança da versão, F3).
        self.assertNotIn("SubagentStart", perfis[0]["hooks"])
        subagente = perfis[1]["hooks"]["SubagentStart"]
        self.assertEqual([g["matcher"] for g in subagente], ["*", "*"])  # 1.7.11: o segundo é o regras_codigo.py (P7)
        self.assertEqual(subagente[1]["hooks"][0]["args"],
                         ["-I", "-B", "/tmp/raiz-ficticia/.claude/hooks/regras_codigo.py"])
        self.assertEqual(subagente[1]["hooks"][0]["onFailure"], "continue")
        self.assertEqual(subagente[0]["hooks"][0]["args"],
                         ["-I", "-B", "/tmp/raiz-ficticia/.claude/hooks/sinais_sessao.py"])
        self.assertEqual(subagente[0]["hooks"][0]["onFailure"], "block")
        self.assertEqual(m.conferir_perfil_wsl(perfis[1], "/tmp/raiz-ficticia", "ficticio", []), [])
        sem_regras = json.loads(json.dumps(perfis[1]))
        del sem_regras["hooks"]["SubagentStart"]
        self.assertTrue(m.conferir_perfil_wsl(sem_regras, "/tmp/raiz-ficticia", "ficticio", []))
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
