"""Revisão de segurança da 1.7.7, terceira passada — JSON muito aninhado no perfil ou num plugin (R177C-B-02).

`json.loads` lança RecursionError com aninhamento fundo (`"[" * 5000 + "]" * 5000`, 10 KB), e o leitor dos plugins só
tratava ValueError: um `hooks.json`, `.mcp.json` ou `plugin.json` assim fazia o `gravar` e o `verificar` do
`inventariar_host.py` saírem com 1, sem saída. A mesma falha estava nos outros pontos que leem o perfil e a raiz
(`installed_plugins.json`, `known_marketplaces.json`, `settings*.json`, `.claude.json` e `.mcp.json`; o
`.codex/config.toml`, pelo `tomllib`, já com 600 níveis) e no valor que o `json.loads` aceita mas o `json.dumps` com
recuo do `gravar` não (1500 níveis num `matcher`, `version`, `repo` ou `type`). Agora JSON e TOML com mais níveis de
lista e objeto que o teto — ou que estouram o limite de recursão — são tratados como o JSON inválido: o arquivo de
plugin vai para `plugins_nao_lidos` com o motivo, e o do perfil ou da raiz é ignorado como o ilegível. O
`alertas_hooks.py` não lê JSON do perfil: a expressão aninhada de um matcher já saía `matcher_indeterminado`
(controle abaixo).

Perfil fictício numa pasta descartável (HOME falso; o apoio de test_revisao_seguranca_177_inventario.py). Cada teste
falha no HEAD revisado (db7e68e) e passa depois da correção; os controles mostram o uso legítimo.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import unittest
from pathlib import Path

from test_revisao_seguranca_177_inventario import _Host, carregar, escrever

FUNDO = "[" * 5000 + "]" * 5000  # 10 KB: o json.loads estoura o limite de recursão
ANINHADO = "JSON aninhado demais"


def aninhar(niveis: int) -> list:
    """Lista com `niveis` níveis (`[]` tem um), montada sem recursão."""
    valor: list = []
    for _ in range(niveis - 1):
        valor = [valor]
    return valor


class _Restaura(_Host):
    """O perfil do `_Host`, com o arquivo plantado devolvido ao de antes na saída do bloco: um aninhado por vez."""

    @staticmethod
    @contextlib.contextmanager
    def plantado(alvo: Path, conteudo):
        antes = alvo.read_bytes() if alvo.exists() else None
        escrever(alvo, conteudo)
        try:
            yield
        finally:
            if antes is None:
                alvo.unlink(missing_ok=True)
            else:
                alvo.write_bytes(antes)

    def gravar_de_novo(self) -> dict:
        self.saida.unlink(missing_ok=True)
        return self.gravar()

    def verificar(self, inventario: Path) -> tuple[int, dict]:
        code, saida = self.rodar("verificar", "--inventario", inventario)
        try:
            return code, json.loads(saida)
        except ValueError:
            self.fail(f"o verificar saiu com {code} sem JSON: " + saida[-800:])


class TestJsonAninhadoNoPlugin(_Restaura):
    """`hooks.json`, `.mcp.json` e `plugin.json` aninhados demais vão para `plugins_nao_lidos`, com o motivo."""

    def test_json_fundo_no_plugin_nao_derruba_gravar_nem_verificar(self):
        self.hooks_do_plugin({"PreToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "node"}]}]})
        limpo = self.base / "limpo.json"
        code, saida = self.rodar("gravar", "--saida", limpo)  # o inventário do plugin são, para comparar
        self.assertEqual(code, 0, saida[-800:])
        for rel in ("hooks/hooks.json", ".mcp.json", ".claude-plugin/plugin.json"):
            with self.subTest(arquivo=rel), self.plantado(self.plugin / rel, FUNDO):
                inv = self.gravar_de_novo()  # no db7e68e: código 1, sem saída (RecursionError)
                sha = hashlib.sha256((self.plugin / rel).read_bytes()).hexdigest()  # desde a R177D-3, o do arquivo
                self.assertIn({"origem": self.ORIGEM, "motivo": ANINHADO, "item": rel, "sha256": sha},
                              inv["plugins_nao_lidos"])
                self.assertEqual(self.verificar(self.saida)[0], 0)
                code, res = self.verificar(limpo)
                self.assertEqual(code, 1, "o arquivo que deixou de ser lido passou sem diferença")
                self.assertTrue(res["diferencas"]["plugins_nao_lidos"]["adicionados"], res["diferencas"])

    def test_controle_plugin_legitimo_continua_lido(self):
        self.hooks_do_plugin({"PreToolUse": [{"matcher": "Edit|Write", "hooks": [
            {"type": "command", "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/fmt.py"}]}]})
        escrever(self.plugin / "hooks" / "fmt.py", "print('ok')\n")
        escrever(self.plugin / ".mcp.json", {"mcpServers": {"fmt": {"command": "npx", "args": ["-y", "fmt-mcp"]}}})
        inv = self.gravar_de_novo()
        self.assertEqual(inv["plugins_nao_lidos"], [])
        self.assertEqual([(h["origem"], h["matcher"]) for h in inv["hooks"]], [(self.ORIGEM, "Edit|Write")])
        self.assertEqual(len(inv["hooks"][0]["scripts"]), 1)
        self.assertIn("fmt", [m["nome"] for m in inv["mcp"]])
        self.assertEqual(self.verificar(self.saida)[0], 0)


class TestJsonAninhadoNoPerfil(_Restaura):
    """Os arquivos do perfil e da raiz aninhados demais são ignorados como o ilegível; o inventário termina."""

    def alvos(self) -> dict[str, Path]:
        return {"installed_plugins.json": self.plugins / "installed_plugins.json",
                "known_marketplaces.json": self.plugins / "known_marketplaces.json",
                "settings.json do perfil": self.perfil / ".claude" / "settings.json",
                ".claude.json": self.perfil / ".claude.json",
                "settings.json da raiz": self.raiz / ".claude" / "settings.json",
                "settings.local.json da raiz": self.raiz / ".claude" / "settings.local.json",
                ".mcp.json da raiz": self.raiz / ".mcp.json"}

    def test_json_fundo_no_perfil_e_na_raiz(self):
        for nome, alvo in self.alvos().items():
            with self.subTest(arquivo=nome), self.plantado(alvo, FUNDO):
                inv = self.gravar_de_novo()  # no db7e68e: código 1, sem saída (RecursionError)
                self.assertEqual(self.verificar(self.saida)[0], 0)
                if nome == "installed_plugins.json":  # o leitor dos plugins diz por que não leu
                    self.assertIn(ANINHADO, [n["motivo"] for n in inv["plugins_nao_lidos"]])

    def test_toml_fundo_do_codex(self):
        toml = self.perfil / ".codex" / "config.toml"
        with self.plantado(toml, "a = " + "[" * 600 + "]" * 600):
            inv = self.gravar_de_novo()  # no db7e68e: código 1, sem saída (RecursionError do tomllib)
            self.assertEqual([m for m in inv["mcp"] if m["cliente"] == "codex"], [])
            self.assertEqual(self.verificar(self.saida)[0], 0)
        with self.plantado(toml, '[mcp_servers.fmt]\ncommand = "npx"\n'):  # controle: o TOML legítimo é lido
            self.assertIn(("codex", "fmt", "npx"), [(m["cliente"], m["nome"], m.get("executavel"))
                                                    for m in self.gravar_de_novo()["mcp"]])

    def test_valor_que_o_json_aceita_mas_o_gravar_nao(self):
        meio = aninhar(1500)  # o json.loads aceita; o json.dumps com recuo do gravar estourava
        casos = {
            "matcher no settings.json do perfil": (self.perfil / ".claude" / "settings.json", {"hooks": {
                "PreToolUse": [{"matcher": meio, "hooks": [{"type": "command", "command": "x"}]}]}}),
            "version no installed_plugins.json": (self.plugins / "installed_plugins.json", {"version": 2, "plugins": {
                "teste@mercado": [{"scope": "user", "version": meio, "installPath": str(self.plugin)}]}}),
            "repo no known_marketplaces.json": (self.plugins / "known_marketplaces.json", {
                "m": {"source": {"source": "github", "repo": meio}}}),
            "type no .mcp.json da raiz": (self.raiz / ".mcp.json", {"mcpServers": {"s": {"type": meio,
                                                                                         "command": "npx"}}}),
        }
        for nome, (alvo, conteudo) in casos.items():
            with self.subTest(caso=nome), self.plantado(alvo, conteudo):
                self.gravar_de_novo()  # no db7e68e: código 1, sem saída (RecursionError no json.dumps)
                self.assertNotIn("[[[[[[[[", self.saida.read_text(encoding="utf-8"))
                self.assertEqual(self.verificar(self.saida)[0], 0)

    def test_no_teto_o_valor_do_perfil_entra_e_o_inventario_relido_confere(self):
        # A `version` de uma instalação vai crua para o inventário (o matcher, desde o tipo inesperado, só como texto).
        ip = carregar("inventario_plugins")
        perto = aninhar(ip.TETO["aninhamento"] - 4)  # o arquivo fica no teto: a versão a quatro níveis da raiz dele
        with self.plantado(self.plugins / "installed_plugins.json", {"version": 2, "plugins": {"teste@mercado": [
                {"scope": "user", "version": perto, "installPath": str(self.plugin)}]}}):
            inv = self.gravar_de_novo()
            self.assertIn(perto, [p["versao"] for p in inv["plugins"]])
            self.assertEqual(self.verificar(self.saida)[0], 0, "o verificar recusou o inventário que o gravar fez")


class TestRegra(_Restaura):
    """A leitura comum: o teto, o RecursionError e o que continua inválido; o alerta do matcher, como antes."""

    def test_regra_e_controles(self):
        ip, ih, ah = carregar("inventario_plugins"), carregar("inventariar_host"), carregar("alertas_hooks")
        teto = ip.TETO["aninhamento"]
        self.assertEqual(ip.decodificar(json.dumps(aninhar(teto))), aninhar(teto))  # no teto: lido
        for texto in (json.dumps(aninhar(teto + 1)), FUNDO, '{"a": ' * 3000 + "1" + "}" * 3000):
            with self.subTest(texto=texto[:12]), self.assertRaises(ip.AninhadoDemais):
                ip.decodificar(texto)
        self.assertTrue(issubclass(ip.AninhadoDemais, ValueError), "tratado como o JSON inválido")
        self.assertTrue(ip.aninhado_demais(aninhar(100_000)))  # contado sem recursão
        for invalido in ("{", "1" * 5000, '{"a": NaN'):  # inválido e número acima do limite de dígitos
            with self.subTest(invalido=invalido[:12]):
                with self.assertRaises(ValueError) as erro:
                    ip.decodificar(invalido)
                self.assertNotIsInstance(erro.exception, ip.AninhadoDemais)
        escrever(self.plugin / "fundo.json", FUNDO)
        escrever(self.plugin / "ok.json", {"x": [1, {"y": 2}]})
        nao_lidos = []
        leitor = ip._Leitor()
        self.assertIsNone(leitor.ler_json(self.plugin, "fundo.json", "o", nao_lidos))
        sha = hashlib.sha256((self.plugin / "fundo.json").read_bytes()).hexdigest()  # desde a R177D-3, o do arquivo
        self.assertEqual(nao_lidos, [{"origem": "o", "motivo": ANINHADO, "item": "fundo.json", "sha256": sha}])
        self.assertEqual(leitor.ler_json(self.plugin, "ok.json", "o", []), {"x": [1, {"y": 2}]})
        self.assertIsNone(ih.ler_json(self.plugin / "fundo.json"))
        self.assertEqual(ih.ler_json(self.plugin / "ok.json"), {"x": [1, {"y": 2}]})
        self.assertEqual(ah.avaliar_matcher("PreToolUse", "(" * 1000 + "Edit" + ")" * 1000)[:2],
                         ("expressao", "matcher_indeterminado"))  # a expressão aninhada já não derrubava


if __name__ == "__main__":
    unittest.main()
