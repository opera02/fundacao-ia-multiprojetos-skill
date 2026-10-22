"""Revisão de segurança da 1.7.7 — resíduos no inventário do host (R177-VAL-03, -04 e -05).

- VAL-03: o matcher de hook de plugin era cortado em 200 caracteres antes de avaliar e de comparar — o que vinha
  depois (`|.*`, que casa tudo) não era visto, e o `verificar` não acusava mudança ali. Agora a avaliação e a
  comparação usam o matcher inteiro (sem caracteres de controle), o inventário guarda a cópia curta e o SHA-256 do
  inteiro, e expressão que o `re` do Python não compila sai com `matcher_indeterminado`. A regra oficial do matcher
  [Verificado 2026-10-21; code.claude.com/docs/en/hooks] desfaz a contradição do docstring: `Edit || Write` (só
  letras, espaços e `|`) é lista exata; a alternativa vazia casa qualquer nome só numa expressão.
- VAL-04: conteúdo de plugin derrubava ou travava o inventário — URL malformada (`urlsplit` lança `ValueError`),
  surrogate solto num nome (o UTF-8 recusa gravar) e matcher com retrocesso exponencial contra o nome de um servidor
  MCP (mais de 25 s com 40 caracteres). Agora a URL ruim dá host nulo, o surrogate vira espaço e cada expressão é
  avaliada num subprocesso com tempo limite e orçamento total, com teto de tamanho do padrão e dos nomes; o que não
  se avalia sai como `matcher_indeterminado`.
- VAL-05: só a atribuição de shell (`VAR=valor`) saía do campo `executavel`; a do PowerShell (`$env:NOME='…';`) ia
  inteira para o inventário gravado, com o valor. Agora o campo guarda só um nome de executável (letras, dígitos,
  `_`, `.`, `+` e `-`); fora disso, nulo.

Perfil fictício numa pasta descartável (HOME falso); o canário é montado em execução e não pode aparecer em nenhuma
saída. Cada teste falha na revisão f1bdc88 e passa depois da correção; os controles mostram o uso legítimo.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from apoio import ENV, SCRIPTS, SKILL

CANARIO = "CANARIO-FIC-" + "R177"  # montado em execução; não pode aparecer em nenhuma saída
LONGO = "Edit|Write|" * 18 + "NotebookEdit"  # 210 caracteres de lista exata: os 200 primeiros casam Edit e Write


def carregar(nome: str):
    spec = importlib.util.spec_from_file_location(f"_revisao_177_{nome}", SCRIPTS / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def escrever(p: Path, conteudo) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(conteudo if isinstance(conteudo, str) else json.dumps(conteudo), encoding="utf-8", newline="\n")
    return p


class _Host(unittest.TestCase):
    """Perfil com um plugin instalado (`teste@mercado`) e uma raiz; cada teste escreve os hooks e o MCP que precisa."""

    ORIGEM = "plugin:teste@mercado|user"

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="revisao-177-inventario-")).resolve()
        self.perfil, self.raiz = self.base / "perfil", self.base / "raiz"
        self.plugins = self.perfil / ".claude" / "plugins"
        self.plugin = self.plugins / "cache" / "mercado" / "teste" / "1.0.0"
        escrever(self.plugins / "installed_plugins.json", {"version": 2, "plugins": {
            "teste@mercado": [{"scope": "user", "version": "1.0.0", "installPath": str(self.plugin)}]}})
        escrever(self.plugin / ".claude-plugin" / "plugin.json", {"name": "teste", "version": "1.0.0"})
        self.raiz.mkdir()
        self.saida = self.base / "inventario.json"

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def hooks_do_plugin(self, mapa: dict) -> None:
        escrever(self.plugin / "hooks" / "hooks.json", {"hooks": mapa})

    def rodar(self, *args, timeout: int = 120) -> tuple[int, str]:
        r = subprocess.run([sys.executable, "-B", str(SCRIPTS / "inventariar_host.py"), *map(str, args),
                            "--perfil", str(self.perfil), "--raiz", str(self.raiz)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=ENV, timeout=timeout)
        self.assertNotIn(CANARIO, r.stdout + r.stderr)
        return r.returncode, r.stdout + r.stderr

    def gravar(self, timeout: int = 120) -> dict:
        code, saida = self.rodar("gravar", "--saida", self.saida, timeout=timeout)
        self.assertEqual(code, 0, saida[-1500:])
        texto = self.saida.read_text(encoding="utf-8")
        self.assertNotIn(CANARIO, texto)
        return json.loads(texto)


class TestMatcherInteiro(_Host):
    """R177-VAL-03: avaliação e comparação pelo matcher inteiro; a cópia guardada é só para exibição."""

    def test_o_que_vem_depois_de_200_caracteres_e_avaliado(self):
        inteiro = LONGO + "|.*"
        self.hooks_do_plugin({"PreToolUse": [{"matcher": inteiro, "hooks": [{"type": "command", "command": "node"}]},
                                             {"matcher": "Edit|(?<=a+)Write", "hooks": [{"type": "command",
                                                                                          "command": "node"}]}]})
        inv = self.gravar()
        h = inv["hooks"][0]
        self.assertEqual((h["matcher"], h.get("matcher_sha256")),
                         (inteiro[:200], hashlib.sha256(inteiro.encode("utf-8")).hexdigest()))
        self.assertNotIn("_matcher_inteiro", json.dumps(inv))
        alertas = {(a["alerta"], a["matcher"]) for a in inv["alertas"]}
        self.assertIn(("matcher_casa_tudo", inteiro[:200]), alertas)          # cortado, parecia lista exata
        self.assertIn(("matcher_indeterminado", "Edit|(?<=a+)Write"), alertas)  # o re do Python não compila

    def test_verificar_acusa_mudanca_depois_de_200_caracteres(self):
        mapa = {"PreToolUse": [{"matcher": LONGO + "|.*", "hooks": [{"type": "command", "command": "node"}]}]}
        self.hooks_do_plugin(mapa)
        self.gravar()
        code, saida = self.rodar("verificar", "--inventario", self.saida)
        self.assertEqual(code, 0, saida[-1500:])
        mapa["PreToolUse"][0]["matcher"] = LONGO + "|Bash"                      # mesma cópia de 200 caracteres
        self.hooks_do_plugin(mapa)
        code, saida = self.rodar("verificar", "--inventario", self.saida)
        self.assertEqual(code, 1, "a mudança depois do caractere 200 passou sem diferença: " + saida[-800:])
        dif = json.loads(saida)["diferencas"]["hooks"]
        self.assertTrue(dif["alterados"] or (dif["adicionados"] and dif["removidos"]), dif)

    def test_regra_oficial_da_alternativa_vazia(self):
        ah = carregar("alertas_hooks")
        self.assertEqual(ah.avaliar_matcher("PreToolUse", "Edit || Write"), ("exato", None, None))
        self.assertEqual(ah.avaliar_matcher("PreToolUse", "a || b")[:2], ("exato", "matcher_nunca_casa"))
        self.assertEqual(ah.avaliar_matcher("PreToolUse", 'tool == "Edit" || tool == "Write"')[:2],
                         ("expressao", "matcher_casa_tudo"))
        self.assertEqual(ah.avaliar_matcher("Notification", "(?<=x+)y")[1], "matcher_indeterminado")
        ref = (SKILL / "references" / "capacidades" / "08-ferramentas-hooks-mcp-skills-plugins.md").read_text(
            encoding="utf-8")
        for nome, texto in (("docstring", ah.__doc__), ("referência §2", ref)):
            with self.subTest(onde=nome):
                plano = " ".join(texto.split())
                self.assertIn("`Edit || Write` (só letras, espaços e `|`) é lista exata", plano)
                self.assertIn('`tool == "Edit" || tool == "Write"`', plano)
                self.assertNotIn("`a || b`", plano)                            # a afirmação contraditória saiu


class TestConteudoDePluginNaoDerruba(_Host):
    """R177-VAL-04: o inventário termina e registra o que não pôde avaliar."""

    def test_url_malformada_da_host_nulo(self):
        self.hooks_do_plugin({"Stop": [{"hooks": [{"type": "http", "url": "http://[::1"}]}]})
        escrever(self.plugin / ".mcp.json", {"mcpServers": {"remoto": {"type": "http", "url": "http://[x]/v1"}}})
        escrever(self.perfil / ".claude.json", {"mcpServers": {"conta": {"type": "http", "url": "https://[::1/v1"}}})
        escrever(self.plugins / "known_marketplaces.json", {"m": {"source": {"source": "url",
                                                                             "url": "http://a／b@c/"}}})
        inv = self.gravar()
        self.assertEqual([h["host"] for h in inv["hooks"]], [None])
        self.assertEqual({m["nome"]: m["host"] for m in inv["mcp"]}, {"conta": None, "remoto": None})
        self.assertEqual([c["host"] for c in inv["catalogos"]], [None])

    def test_surrogate_solto_vira_espaco(self):
        escrever(self.plugin / "hooks" / "hooks.json", '{"hooks": {"PreToolUse\\ud800": [{"matcher": "Edit\\udc00", '
                                                       '"hooks": [{"type": "command", "command": "node"}]}]}}')
        escrever(self.plugin / ".mcp.json", '{"mcpServers": {"srv\\ud800": {"command": "node"}}}')
        inv = self.gravar()
        self.assertEqual([(h["evento"], h["matcher"]) for h in inv["hooks"]], [("PreToolUse ", "Edit ")])
        self.assertEqual([m["nome"] for m in inv["mcp"]], ["srv "])

    def test_retrocesso_exponencial_nao_trava(self):
        escrever(self.plugin / ".mcp.json", {"mcpServers": {"a" * 40: {"command": "node"}}})
        self.hooks_do_plugin({"PreToolUse": [{"matcher": "^mcp__(a+)+$", "hooks": [{"type": "command",
                                                                                     "command": "node"}]}]})
        inicio = time.monotonic()
        inv = self.gravar(timeout=90)  # na f1bdc88, não termina (2^39 caminhos de retrocesso)
        self.assertLess(time.monotonic() - inicio, 60)
        self.assertEqual([(a["alerta"], a["matcher"]) for a in inv["alertas"]],
                         [("matcher_indeterminado", "^mcp__(a+)+$")])

    def test_tetos_da_avaliacao(self):
        ah = carregar("alertas_hooks")
        with mock.patch.object(ah.subprocess, "run", side_effect=AssertionError("avaliou")):
            self.assertEqual(ah.avaliar_matcher("PreToolUse", "x." * 3000)[1], "matcher_indeterminado")  # longo
            esgotado = ah.Avaliador(orcamento=0)
            self.assertEqual(ah.avaliar_matcher("PreToolUse", "Edit.*", avaliador=esgotado)[1],
                             "matcher_indeterminado")
            self.assertEqual(ah.avaliar_matcher("PreToolUse", "Edit|Write"), ("exato", None, None))  # sem subprocesso
        entradas = []
        real = ah.subprocess.run

        def espiar(*args, **kwargs):
            entradas.append(json.loads(kwargs["input"]))
            return real(*args, **kwargs)

        with mock.patch.object(ah.subprocess, "run", side_effect=espiar):
            curto, longo = "mcp__srv__x", "mcp__" + "b" * 300 + "__x"
            self.assertEqual(ah.avaliar_matcher("PreToolUse", "^mcp__srv__.*$", (curto, longo)), ("expressao", None,
                                                                                                    None))
        self.assertIn(curto, entradas[0]["nomes"])
        self.assertNotIn(longo, entradas[0]["nomes"])                           # nome acima do teto não entra


class TestExecutavelSoNome(_Host):
    """R177-VAL-05: o campo `executavel` guarda só o nome do executável, nunca uma atribuição."""

    def test_atribuicao_do_powershell_nao_vaza(self):
        simples, dupla = f"$env:CHAVE_X='{CANARIO}'; node srv.js", f'$env:CHAVE_X="{CANARIO}"; python x.py'
        escrever(self.perfil / ".claude.json", {"mcpServers": {"ps": {"command": simples}}})
        escrever(self.raiz / ".claude" / "settings.json", {"hooks": {"PreToolUse": [
            {"matcher": "Write", "hooks": [{"type": "command", "command": dupla}]}]}})
        self.hooks_do_plugin({"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": simples}]}]})
        escrever(self.plugin / ".mcp.json", {"mcpServers": {"pl": {"command": dupla}}})
        inv = self.gravar()
        self.assertEqual(sorted((m["onde"], m["executavel"]) for m in inv["mcp"]),
                         [(self.ORIGEM, None), ("usuario", None)])
        self.assertEqual([(h["origem"], h["executavel"]) for h in inv["hooks"]],
                         [("raiz:settings.json", None), (self.ORIGEM, None)])

    def test_controle_nomes_legitimos_continuam(self):
        executavel = carregar("inventariar_host").nome_do_executavel
        casos = {"node": "node", "npx -y pacote": "npx", "C:/ferramentas/node.exe --x": "node.exe",
                 '"C:/Program Files/ferramenta/srv.exe" --k v': "srv.exe", "CHAVE=valor node a.js": "node",
                 r"C:\Python312\python.exe -B x.py": "python.exe", "python3.12 -B x.py": "python3.12",
                 "/usr/bin/python3 -B guarda.py": "python3", "g++ -v": "g++"}
        for comando, nome in casos.items():
            with self.subTest(comando=comando):
                self.assertEqual(executavel(comando), nome)
        for comando in ("$env:CHAVE='x'; node", "& 'C:/x/srv.exe' --k", "--chave=x node", ""):
            with self.subTest(comando=comando):
                self.assertIsNone(executavel(comando))


if __name__ == "__main__":
    unittest.main()
