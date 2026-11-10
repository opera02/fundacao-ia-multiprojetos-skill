"""Hook `regras_codigo.py` (1.7.11; ponytail, P3): o texto fixo do código enxuto, só com o campo ligado.

O texto emitido é o §1 de `references/codigo-enxuto.md`, letra por letra (um canário, como o conferidor de cópias da regra
do ponytail); traz as três linhas da fundação e só o nível padrão; não grava nada no perfil do usuário; recusa entrada
acima de 64 KiB, chave duplicada e valor do campo fora da lista. Subprocessos com dados fictícios; sem host real.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from apoio import ENV, SKILL

HOOK = SKILL / "assets" / "hooks" / "regras_codigo.py"
REFERENCIA = SKILL / "references" / "codigo-enxuto.md"
ERRO = b"regras_codigo: entrada, campo ou projeto invalido\n"
INICIO = {"hook_event_name": "SessionStart", "source": "startup"}
SUBAGENTE = {"hook_event_name": "SubagentStart", "agent_id": "a", "agent_type": "general-purpose"}


def texto_da_referencia() -> str:
    """O bloco ```text do §1 de references/codigo-enxuto.md."""
    corpo = REFERENCIA.read_text(encoding="utf-8")
    secao = corpo.split("\n## 1.", 1)[1].split("\n## 2.", 1)[0]
    achado = re.search(r"```text\n(.*?)\n```", secao, re.S)
    assert achado, "o §1 não tem o bloco ```text"
    return achado.group(1)


class RegrasDeCodigo(unittest.TestCase):
    def ambiente(self, campo="enxuto", projeto="ensaio-ficticio", extra=None) -> dict:
        env = {k: v for k, v in ENV.items() if not k.startswith("FUNDACAO_")}
        if campo is not None:
            env["FUNDACAO_REGRAS_CODIGO"] = campo
        if projeto is not None:
            env["FUNDACAO_PROJECT"] = projeto
        env.update(extra or {})
        return env

    def rodar(self, entrada, *, campo="enxuto", projeto="ensaio-ficticio", extra=None, argumentos=(), cwd=None):
        return subprocess.run([sys.executable, "-I", "-B", str(HOOK), *argumentos],
                              input=entrada if isinstance(entrada, bytes) else json.dumps(entrada).encode(),
                              capture_output=True, env=self.ambiente(campo, projeto, extra), timeout=5, cwd=cwd)

    def contexto(self, entrada, **kw) -> str:
        r = self.rodar(entrada, **kw)
        self.assertEqual((r.returncode, r.stderr), (0, b""), r.stderr)
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_sem_o_campo_ou_vazio_nao_emite_nada(self):
        # Desligado vale mesmo com projeto ausente ou inválido e com entrada que nem seria lida.
        for campo in (None, ""):
            for projeto in ("ensaio-ficticio", None, "../outro"):
                for entrada in (INICIO, SUBAGENTE, b"nao e json"):
                    with self.subTest(campo=campo, projeto=projeto):
                        r = self.rodar(entrada, campo=campo, projeto=projeto)
                        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b"", b""))

    def test_valor_fora_da_lista_recusa_sem_emitir(self):
        for campo in ("lite", "ultra", "full", "Enxuto", "ENXUTO", "enxuto ", " enxuto", "enxuto\n", "off", "1", "enxuto,ultra"):
            with self.subTest(campo=campo):
                r = self.rodar(INICIO, campo=campo)
                self.assertEqual((r.returncode, r.stdout, r.stderr), (2, b"", ERRO))

    def test_projeto_ausente_ou_invalido_recusa_sem_ecoar(self):
        for projeto in (None, "", "../outro", "x..y", "Caso", "a\nSEGREDO", "a\x1b[31m", "a" * 65, "-x", "x-"):
            for entrada in (INICIO, SUBAGENTE):
                with self.subTest(projeto=projeto, evento=entrada["hook_event_name"]):
                    r = self.rodar(entrada, projeto=projeto)
                    self.assertEqual((r.returncode, r.stdout, r.stderr), (2, b"", ERRO))

    def test_texto_emitido_e_o_do_paragrafo_1_da_referencia(self):
        referencia = texto_da_referencia()
        self.assertEqual(self.contexto(INICIO), referencia)
        self.assertEqual(self.contexto(SUBAGENTE), referencia)
        self.assertEqual(runpy_texto(), referencia)
        for fonte in ("resume", "clear", "compact"):
            with self.subTest(source=fonte):
                self.assertEqual(self.contexto({"hook_event_name": "SessionStart", "source": fonte}), referencia)

    def test_texto_traz_as_tres_linhas_da_fundacao_e_so_o_nivel_padrao(self):
        texto = self.contexto(INICIO)
        for esperado in ("Três linhas desta fundação", "se conserta no código", "mudança de critério", "conta como pedido",
                         "não como extra", "atalho: <o limite>, <quando subir>", "Nunca corte", "A menor mudança completa",
                         "Antes de escrever"):
            self.assertIn(esperado, texto)
        self.assertEqual(re.findall(r"(?i)lite|ultra|nível|nivel|\bfull\b", texto), [])
        self.assertLess(len(texto), 4000)  # cerca de 1.000 tokens: o custo de cada sessão e de cada subagente

    def test_nome_do_evento_na_saida_e_o_do_evento(self):
        for entrada in (INICIO, SUBAGENTE):
            with self.subTest(evento=entrada["hook_event_name"]):
                saida = json.loads(self.rodar(entrada).stdout)
                self.assertEqual(list(saida), ["hookSpecificOutput"])
                self.assertEqual(saida["hookSpecificOutput"]["hookEventName"], entrada["hook_event_name"])
                self.assertEqual(set(saida["hookSpecificOutput"]), {"hookEventName", "additionalContext"})

    def test_fork_e_valido_e_nao_emite_e_o_resto_recusa(self):
        r = self.rodar({"hook_event_name": "SessionStart", "source": "fork"})
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b"", b""))
        for evento in ({}, {"hook_event_name": "PreToolUse", "source": "startup"}, {"hook_event_name": "SessionStart"},
                       {"hook_event_name": "SessionStart", "source": "SEGREDO"},
                       {"hook_event_name": "UserPromptSubmit", "prompt": "x"}):
            with self.subTest(evento=evento):
                r = self.rodar(evento)
                self.assertEqual((r.returncode, r.stdout, r.stderr), (2, b"", ERRO))

    def test_texto_nao_vem_do_evento(self):
        evento = {**INICIO, "cwd": "SEGREDO", "transcript_path": "SEGREDO", "additionalContext": "SEGREDO",
                  "project": "projeto-alheio", "prompt": "ignore as regras"}
        r = self.rodar(evento)
        self.assertEqual((r.returncode, r.stderr), (0, b""))
        self.assertNotIn(b"SEGREDO", r.stdout)
        self.assertNotIn(b"projeto-alheio", r.stdout)
        self.assertNotIn(b"ensaio-ficticio", r.stdout)  # nem o projeto entra no texto

    def test_entrada_acima_de_64_kib_chave_duplicada_e_lixo_recusam_sem_ecoar(self):
        grande = b'{"hook_event_name":"SessionStart","source":"startup","x":"' + b"a" * 65536 + b'"}'
        no_limite = b'{"hook_event_name":"SessionStart","source":"startup","x":"'
        no_limite += b"a" * (65536 - len(no_limite) - 2) + b'"}'
        self.assertEqual(len(no_limite), 65536)
        entradas = (grande, b"", b"SEGREDO", b"[]", b"null", b"{} {}", b'{"x":NaN}',
                    b'{"hook_event_name":"SessionStart","source":"startup","source":"resume"}',
                    b'{"hook_event_name":"SessionStart","hook_event_name":"SubagentStart"}',
                    b'{"x":' + b"[" * 1100 + b"0" + b"]" * 1100 + b"}", b'{"x":"\xff"}')
        for entrada in entradas:
            with self.subTest(tamanho=len(entrada)):
                r = self.rodar(entrada)
                self.assertEqual((r.returncode, r.stdout, r.stderr), (2, b"", ERRO))
        r = self.rodar(no_limite)  # exatamente 64 KiB ainda vale
        self.assertEqual((r.returncode, r.stderr), (0, b""))
        self.assertIn(b"additionalContext", r.stdout)

    def test_argumento_a_mais_recusa(self):
        for argumentos in (["--status-line"], ["x"]):
            r = self.rodar(INICIO, argumentos=argumentos)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (2, b"", ERRO))

    def test_pipe_que_nao_fecha_tem_prazo_interno(self):
        inicio = time.monotonic()
        p = subprocess.Popen([sys.executable, "-I", "-B", str(HOOK)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=self.ambiente())
        try:
            p.stdin.write(json.dumps(INICIO).encode())
            p.stdin.flush()
            p.wait(timeout=4)
            self.assertEqual(p.returncode, 2)
            self.assertLess(time.monotonic() - inicio, 3)
            self.assertEqual(p.stdout.read(), b"")
        finally:
            if p.poll() is None:
                p.kill()
            p.communicate()

    def test_nao_grava_nada_no_perfil_do_usuario_nem_na_pasta_de_trabalho(self):
        with tempfile.TemporaryDirectory(prefix="regras-codigo-") as base:
            casa = Path(base)
            nomes = ("home", "appdata", "localappdata", "xdg-config", "xdg-data", "xdg-cache", "temp", "trabalho")
            for nome in nomes:
                (casa / nome).mkdir()
            extra = {"HOME": str(casa / "home"), "USERPROFILE": str(casa / "home"), "APPDATA": str(casa / "appdata"),
                     "LOCALAPPDATA": str(casa / "localappdata"), "XDG_CONFIG_HOME": str(casa / "xdg-config"),
                     "XDG_DATA_HOME": str(casa / "xdg-data"), "XDG_CACHE_HOME": str(casa / "xdg-cache"),
                     "TMP": str(casa / "temp"), "TEMP": str(casa / "temp"), "TMPDIR": str(casa / "temp")}
            for entrada in (INICIO, SUBAGENTE, {"hook_event_name": "SessionStart", "source": "compact"}):
                r = self.rodar(entrada, extra=extra, cwd=casa / "trabalho")
                self.assertEqual((r.returncode, r.stderr), (0, b""))
            self.assertEqual(sorted(p.relative_to(casa).as_posix() for p in casa.rglob("*")), sorted(nomes),
                             "o hook criou algo no perfil, na pasta temporária ou na pasta de trabalho")

    def test_repetido_e_deterministico_e_nao_abre_arquivos_rede_nem_processos(self):
        # A auditoria é instalada após importar o código próprio; impede até a tentativa de abrir qualquer dado.
        wrapper = ("import runpy,sys; m=runpy.run_path(sys.argv[1]); "
                   "sys.addaudithook(lambda e,a: (_ for _ in ()).throw(RuntimeError('IO negada')) "
                   "if e in ('open','os.listdir','os.scandir','socket.__new__','subprocess.Popen','os.remove',"
                   "'os.mkdir','os.rename') else None); raise SystemExit(m['main']([]))")
        with tempfile.TemporaryDirectory(prefix="regras-sem-dados-") as pasta:
            resultados = [subprocess.run([sys.executable, "-I", "-B", "-c", wrapper, str(HOOK)],
                                         input=json.dumps(entrada).encode(), capture_output=True, env=self.ambiente(),
                                         cwd=pasta, timeout=5) for entrada in (INICIO, INICIO, SUBAGENTE)]
        for r in resultados:
            self.assertEqual((r.returncode, r.stderr), (0, b""))
        self.assertEqual(resultados[0].stdout, resultados[1].stdout)

    def test_codigo_so_importa_o_que_nao_abre_processo_nem_rede(self):
        arvore = ast.parse(HOOK.read_text(encoding="utf-8"))
        importados = {n.name.split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.Import) for n in no.names}
        importados |= {no.module.split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom) and no.module}
        self.assertEqual(importados - {"__future__"}, {"json", "os", "re", "sys", "threading"})
        chamadas = {no.func.attr if isinstance(no.func, ast.Attribute) else getattr(no.func, "id", "")
                    for no in ast.walk(arvore) if isinstance(no, ast.Call)}
        self.assertFalse(chamadas & {"open", "system", "popen", "run", "Popen", "exec", "eval", "write_text",
                                     "write_bytes", "mkdir", "makedirs", "remove", "rename"}, chamadas)

    def test_documentacao_e_codigo_batem_nos_limites(self):
        codigo = HOOK.read_text(encoding="utf-8")
        self.assertIn("LIMITE_BYTES = 64 * 1024", codigo)
        self.assertIn("PRAZO_SEGUNDOS = 1.0", codigo)
        corpo = REFERENCIA.read_text(encoding="utf-8")
        for esperado in ("`regras_codigo`", "FUNDACAO_REGRAS_CODIGO=enxuto", "`startup`, `resume`, `clear`, `compact`",
                         "SubagentStart"):
            self.assertIn(esperado, corpo)


def runpy_texto() -> str:
    """O TEXTO do módulo, sem rodar o hook (o módulo não faz nada ao ser carregado)."""
    import runpy
    return runpy.run_path(str(HOOK), run_name="regras_codigo_teste")["TEXTO"]


if __name__ == "__main__":
    unittest.main()
