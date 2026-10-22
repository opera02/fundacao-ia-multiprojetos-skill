"""Revisão de segurança da 1.7.7, terceira passada — JSON (e TOML) com tipo inesperado no perfil, na raiz, num plugin
ou no inventário relido (R177C-B-02, tipo inesperado; a família do R177-VAL-04: conteúdo de terceiro não derruba nem
trava o inventário).

O `inventariar_host.py` percorria os arquivos do perfil e da raiz sem conferir a forma: lista no topo, `"hooks": [..]`,
`"mcpServers": [..]`, `"projects": [..]`, o `hooks` de um grupo ou o `args` de um hook como número, o `mcp_servers` do
Codex como lista ou texto e a chave de projeto do `.claude.json` com NUL faziam o `gravar` e o `verificar` saírem com 1,
sem saída (AttributeError, TypeError, ValueError); o `verificar` caía também com o inventário relido de forma
inesperada. O leitor dos plugins não caía, mas descartava em silêncio o manifesto, o `.mcp.json` e o grupo de forma
inesperada, e o matcher, o comando e o `permissions` fora do tipo esperado passavam sem aviso. Agora a forma esperada
de cada arquivo fica num lugar só (`inventario_plugins.FORMAS`, conferida por `forma_inesperada`): o arquivo que foge
dela vale como ilegível, com o motivo — em `plugins_nao_lidos` (plugin) ou em `arquivos_nao_lidos` (perfil e raiz) —,
sem reproduzir chave livre, que pode ser o caminho de um projeto.

Perfil fictício numa pasta descartável (HOME falso; o apoio de test_revisao_seguranca_177_inventario.py). Cada teste
falha no HEAD revisado (2a594a7) e passa depois da correção; os controles mostram o uso legítimo.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

from apoio import ENV, SCRIPTS, SKILL
from test_revisao_seguranca_177_inventario import carregar
from test_revisao_seguranca_177c_inventario import _Restaura

FORMA = "de forma inesperada ("


def grupo(matcher="Edit", hooks=None) -> dict:
    return {"matcher": matcher, "hooks": [{"type": "command", "command": "node"}] if hooks is None else hooks}


class TestTipoInesperadoNoPerfilENaRaiz(_Restaura):
    """Arquivo do perfil ou da raiz de forma inesperada vale como ilegível, com o motivo em `arquivos_nao_lidos`."""

    def casos(self) -> list[tuple[str, Path, object]]:
        p, r, settings = self.perfil, self.raiz, self.perfil / ".claude" / "settings.json"
        catalogo, toml = self.plugins / "known_marketplaces.json", self.perfil / ".codex" / "config.toml"
        return [
            ("perfil:known_marketplaces.json", catalogo, [1]),
            ("perfil:known_marketplaces.json", catalogo, {"m": [1]}),
            ("perfil:known_marketplaces.json", catalogo, {"m": {"source": {"source": "github", "repo": ["x"]}}}),
            ("perfil:settings.json", settings, [1]),
            ("perfil:settings.json", settings, {"hooks": [1]}),
            ("perfil:settings.json", settings, {"hooks": {"PreToolUse": [grupo(hooks=5)]}}),
            ("perfil:settings.json", settings, {"hooks": {"PreToolUse": [grupo(hooks=[
                {"type": "command", "command": "x", "args": 5}])]}}),
            ("perfil:settings.json", settings, {"hooks": {"PreToolUse": [grupo(matcher=["Edit"])]}}),
            ("perfil:settings.json", settings, {"hooks": {"PreToolUse": [grupo(hooks=[
                {"type": "command", "command": ["node", "x"]}])]}}),
            ("perfil:settings.json", settings, {"permissions": 5}),
            ("perfil:settings.json", settings, {"permissions": {"deny": "Read(./.env)"}}),
            ("perfil:.claude.json", p / ".claude.json", [1]),
            ("perfil:.claude.json", p / ".claude.json", {"mcpServers": [1]}),
            ("perfil:.claude.json", p / ".claude.json", {"mcpServers": {"s": {"command": ["npx"]}}}),
            ("perfil:.claude.json", p / ".claude.json", {"projects": [1]}),
            ("perfil:.claude.json", p / ".claude.json", {"projects": {str(r): {"mcpServers": [1]}}}),
            ("raiz:.mcp.json", r / ".mcp.json", [1]),
            ("raiz:.mcp.json", r / ".mcp.json", {"mcpServers": [1]}),
            ("raiz:settings.local.json", r / ".claude" / "settings.local.json", {"hooks": "x"}),
            ("perfil:config.toml", toml, "mcp_servers = [1]\n"),
            ("perfil:config.toml", toml, 'mcp_servers = "x"\n'),
            ("perfil:config.toml", toml, "[mcp_servers]\nx = 1\n"),
        ]

    def test_gravar_e_verificar_terminam_com_o_motivo(self):
        limpo = self.base / "limpo.json"
        code, saida = self.rodar("gravar", "--saida", limpo)  # o inventário do perfil são, para comparar
        self.assertEqual(code, 0, saida[-800:])
        for origem, alvo, conteudo in self.casos():
            with self.subTest(origem=origem, conteudo=json.dumps(conteudo)[:70]), self.plantado(alvo, conteudo):
                inv = self.gravar_de_novo()  # no 2a594a7: código 1, sem saída, ou nenhum motivo
                motivos = [n["motivo"] for n in inv["arquivos_nao_lidos"] if n["origem"] == origem]
                self.assertEqual(len(motivos), 1, inv["arquivos_nao_lidos"])
                self.assertIn(FORMA, motivos[0])
                self.assertNotIn(self.base.name, motivos[0], "o motivo reproduziu a chave de um projeto")
                self.assertEqual(self.verificar(self.saida)[0], 0)
                code, res = self.verificar(limpo)
                self.assertEqual(code, 1, "o arquivo que deixou de ser lido passou sem diferença")
                self.assertTrue(res["diferencas"]["arquivos_nao_lidos"]["adicionados"], res["diferencas"])

    def test_installed_plugins_de_forma_inesperada_vai_para_os_plugins_nao_lidos(self):
        for conteudo in ([1], {"plugins": [1]}, {"plugins": {"teste@mercado": {"installPath": str(self.plugin)}}},
                         {"plugins": {"teste@mercado": [{"scope": "user", "installPath": 5}]}}):
            with self.subTest(conteudo=json.dumps(conteudo)[:70]), \
                    self.plantado(self.plugins / "installed_plugins.json", conteudo):
                inv = self.gravar_de_novo()  # no 2a594a7: código 1 nos dois primeiros; sem esse motivo nos outros
                self.assertTrue(any(n["origem"] == "installed_plugins.json" and FORMA in n["motivo"]
                                    for n in inv["plugins_nao_lidos"]), inv["plugins_nao_lidos"])
                self.assertEqual(inv["arquivos_nao_lidos"], [], "o mesmo arquivo anotado duas vezes")
                self.assertEqual(self.verificar(self.saida)[0], 0)

    def test_chave_de_projeto_com_nul_nao_derruba(self):
        conteudo = {"mcpServers": {"docs": {"command": "npx"}}, "projects": {"a\u0000b": {"mcpServers": {}}}}
        with self.plantado(self.perfil / ".claude.json", conteudo):
            inv = self.gravar_de_novo()  # no 2a594a7: código 1, sem saída (ValueError do resolve)
            self.assertIn("docs", [m["nome"] for m in inv["mcp"]])
            self.assertEqual(inv["arquivos_nao_lidos"], [])  # o projeto com NUL só não é a raiz
            self.assertEqual(self.verificar(self.saida)[0], 0)

    def test_controle_perfil_e_raiz_legitimos(self):
        host = json.loads((SKILL / "assets" / "host" / "windows" / "settings.json").read_text(encoding="utf-8"))
        arquivos = {
            self.perfil / ".claude" / "settings.json": {"permissions": {"deny": ["Read(./.env)"], "allow": []},
                                                        "hooks": {"PreToolUse": [{"matcher": "Edit|Write", "hooks": [
                                                            {"type": "command", "command": "python",
                                                             "args": ["-B", "g.py"], "timeout": 30}]}]}},
            self.perfil / ".claude.json": {"mcpServers": {"docs": {"type": "stdio", "command": "npx",
                                                                   "args": ["-y", "x"], "env": {"K": "v"}}},
                                           "projects": {str(self.raiz): {"allowedTools": [], "mcpServers": {
                                               "r": {"type": "http", "url": "https://x.exemplo.invalid/mcp"}}}}},
            self.raiz / ".mcp.json": {"mcpServers": {"m": {"command": "node", "args": ["s.js"]}}},
            self.raiz / ".claude" / "settings.json": host,  # o perfil que a skill instala na raiz
            self.plugins / "known_marketplaces.json": {"m": {"source": {"source": "github", "repo": "o/m"},
                                                             "installLocation": "y"}},
            self.perfil / ".codex" / "config.toml": '[mcp_servers.leitor]\ncommand = "npx"\nargs = ["-y", "p"]\n',
        }
        with contextlib.ExitStack() as pilha:
            for alvo, conteudo in arquivos.items():
                pilha.enter_context(self.plantado(alvo, conteudo))
            inv = self.gravar_de_novo()
            self.assertEqual(inv.get("arquivos_nao_lidos", []), [])  # controle: passa antes e depois da correção
            self.assertEqual(inv["plugins_nao_lidos"], [])
            self.assertEqual({(m["cliente"], m["nome"]) for m in inv["mcp"]},
                             {("claude", "docs"), ("claude", "r"), ("claude", "m"), ("codex", "leitor")})
            origens = [h["origem"] for h in inv["hooks"]]
            self.assertIn("perfil:settings.json", origens)
            self.assertEqual(origens.count("raiz:settings.json"), sum(len(g["hooks"]) for gs in host["hooks"].values()
                                                                      for g in gs))
            self.assertEqual(self.verificar(self.saida)[0], 0)


class TestTipoInesperadoNoPlugin(_Restaura):
    """Arquivo de plugin de forma inesperada vai para `plugins_nao_lidos` com o motivo, em vez de sumir em silêncio."""

    def test_arquivo_do_plugin_de_forma_inesperada_vai_para_os_nao_lidos(self):
        casos = [("hooks/hooks.json", [1]), ("hooks/hooks.json", {"hooks": [1]}),
                 ("hooks/hooks.json", {"hooks": {"PreToolUse": [grupo(hooks=5)]}}),
                 ("hooks/hooks.json", {"hooks": {"PreToolUse": [grupo(matcher=["Edit"])]}}),
                 ("hooks/hooks.json", {"hooks": {"PreToolUse": [grupo(hooks=[{"type": "command", "command": [1]}])]}}),
                 (".mcp.json", [1]), (".mcp.json", {"mcpServers": [1]}), (".mcp.json", {"srv": {"command": ["npx"]}}),
                 (".claude-plugin/plugin.json", [1]), (".claude-plugin/plugin.json", {"name": "teste", "hooks": 5}),
                 (".claude-plugin/plugin.json", {"name": "teste", "skills": [5]}),
                 (".claude-plugin/plugin.json", {"name": "teste", "mcpServers": [5]})]
        for rel, conteudo in casos:
            with self.subTest(arquivo=rel, conteudo=json.dumps(conteudo)[:70]), \
                    self.plantado(self.plugin / rel, conteudo):
                inv = self.gravar_de_novo()  # no 2a594a7: sem motivo, ou "sem o objeto hooks"
                motivos = [n["motivo"] for n in inv["plugins_nao_lidos"] if n.get("item") == rel]
                self.assertEqual(len(motivos), 1, inv["plugins_nao_lidos"])
                self.assertTrue(motivos[0].startswith("JSON " + FORMA), motivos[0])
                self.assertEqual(self.verificar(self.saida)[0], 0)


class TestInventarioRelidoDeFormaInesperada(_Restaura):
    """O `verificar` relê o inventário gravado: de forma inesperada, sai com 1 e o motivo, sem cair."""

    def test_verificar_termina_com_o_motivo(self):
        self.gravar_de_novo()
        bom = json.loads(self.saida.read_text(encoding="utf-8"))
        for troca in ({"hooks": 5}, {"skills": [1]}, {"mcp": [{"cliente": ["x"]}]}, {"perfil": 5}, {"raiz": ["x"]},
                      {"perfil": "a\u0000b"}):
            with self.subTest(troca=json.dumps(troca)):
                self.saida.write_text(json.dumps({**bom, **troca}), encoding="utf-8")
                r = subprocess.run([sys.executable, "-B", str(SCRIPTS / "inventariar_host.py"), "verificar",
                                    "--inventario", str(self.saida)], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", env=ENV, timeout=120)  # perfil e raiz do arquivo
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr[-600:])
                try:
                    res = json.loads(r.stdout)
                except ValueError:
                    self.fail("o verificar caiu sem JSON (no 2a594a7: TypeError, KeyError ou ValueError): "
                              + r.stderr[-600:])
                self.assertFalse(res["ok"])
                self.assertIn("forma inesperada", res["erro"])


class TestRegraDaForma(unittest.TestCase):
    """A forma num lugar só: nulo vale como ausente, chave livre sai como `*`, e os perfis da skill passam."""

    def test_regra_e_controles(self):
        ip, ah = carregar("inventario_plugins"), carregar("alertas_hooks")
        f, formas = ip.forma_inesperada, ip.FORMAS
        self.assertIsNone(f(None, formas["settings.json"]))
        self.assertIsNone(f({"hooks": None, "env": [1], "outra": {"x": 5}}, formas["settings.json"]))
        self.assertEqual(f([1], formas["settings.json"]), "raiz: lista em vez de objeto")
        self.assertEqual(f({"hooks": {"PreToolUse": [{"hooks": 5}]}}, formas["settings.json"]),
                         "hooks.*[0].hooks: número em vez de lista")
        self.assertEqual(f({"projects": {"C:/Clientes/Fulano": {"mcpServers": [1]}}}, formas[".claude.json"]),
                         "projects.*.mcpServers: lista em vez de objeto")  # a chave do projeto não sai
        self.assertEqual(f({"hooks": True}, formas["plugin.json"]), "hooks: booleano em vez de texto, objeto ou lista")
        self.assertEqual(f({"hooks": ["x", {"Stop": [{"hooks": [{"command": 1}]}]}]}, formas["plugin.json"]),
                         "hooks[1].*[0].hooks[0].command: número em vez de texto")  # o erro da forma que tem o tipo
        self.assertEqual(f({"mcp_servers": {"x": 1}}, formas["config.toml"]), "mcp_servers.*: número em vez de objeto")
        for perfil in (SKILL / "assets" / "host" / "windows" / "settings.json",
                       SKILL / "assets" / "host" / "wsl" / "settings.wsl.json"):  # os perfis que a skill instala
            with self.subTest(perfil=perfil.name):
                self.assertIsNone(f(json.loads(perfil.read_text(encoding="utf-8")), formas["settings.json"]))
        manifesto = {"name": "g", "version": 1, "skills": "./extra", "hooks": ["./x.json", {"Notification": [
            {"matcher": "p", "hooks": [{"type": "mcp_tool", "server": "s", "tool": "t", "input": {"x": 1}}]}]}],
            "mcpServers": [{"e": {"command": "node", "args": ["a"], "env": {"K": "v"}}}, "./p.mcpb"]}
        self.assertIsNone(f(manifesto, formas["plugin.json"]))  # as formas do manifesto que o host aceita
        hooks = [{"origem": "perfil:settings.json", "evento": None, "matcher": ["x"]},
                 {"origem": "o", "evento": "PreToolUse", "matcher": 5}]
        self.assertTrue(ah.alertas(hooks, [{"cliente": "claude", "nome": 5, "onde": None}]))  # controle: já não caía


if __name__ == "__main__":
    unittest.main()
