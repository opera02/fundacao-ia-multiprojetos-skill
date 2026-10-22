"""Revisão de segurança da 1.7.7, quarta passada — o `verificar` com arquivo de forma inesperada (R177D-3).

O tipo inesperado (9b689e2) descartava o arquivo inteiro na primeira parte fora da forma, e o registro de "não lido"
era comparado só por origem e motivo. Com o inventário de referência gravado com UMA parte fora da forma —
`settings.json` com `"allow": "Bash(*)"`, `.claude.json` com um servidor de `args: [1]`, `hooks.json` de plugin com
`"Stop": 5` —, um hook com `curl`, um servidor MCP novo ou o matcher trocado para `.*` no mesmo arquivo passavam no
`verificar` sem diferença (no 02b6884, apareciam). Agora o registro de "não lido" guarda o SHA-256 do arquivo, que entra
na chave de comparação (qualquer mudança no arquivo aparece), e só a parte fora da forma fica de fora — a menor que a
contém numa lista ou num objeto de chaves livres (o grupo, o hook, o servidor, o evento), ou a chave da raiz —; o resto
é lido, com os alertas de sempre.

Perfil fictício numa pasta descartável (HOME falso; o apoio de test_revisao_seguranca_177c_inventario.py). Cada teste
falha no HEAD revisado (59b3813) e passa depois da correção; os controles mostram o uso legítimo.
"""

from __future__ import annotations

import hashlib
import unittest

from test_revisao_seguranca_177_inventario import carregar
from test_revisao_seguranca_177c_inventario import _Restaura


def hook(comando: str, matcher: str = "Edit") -> dict:
    return {"matcher": matcher, "hooks": [{"type": "command", "command": comando}]}


class TestVerificarComParteForaDaForma(_Restaura):
    """Os três casos do revisor: a troca no arquivo com uma parte fora da forma aparece no `verificar`."""

    def casos(self) -> dict:
        lido = {"hooks do settings.json": lambda inv: any(h["origem"] == "perfil:settings.json" for h in inv["hooks"]),
                "docs do .claude.json": lambda inv: "docs" in [m["nome"] for m in inv["mcp"]],
                "hook Bash do plugin": lambda inv: any(h["origem"] == self.ORIGEM and h["matcher"] == "Bash"
                                                       for h in inv["hooks"])}
        return {
            "settings.json com permissions.allow em texto": (
                self.perfil / ".claude" / "settings.json",
                {"hooks": {"PreToolUse": [hook("python g.py")]}, "permissions": {"allow": "Bash(*)"}},
                {"hooks": {"PreToolUse": [hook("python g.py")], "UserPromptSubmit": [hook("curl x", "*")]},
                 "permissions": {"allow": "Bash(*)"}},
                "hooks", lido["hooks do settings.json"]),
            ".claude.json com um servidor de args [1]": (
                self.perfil / ".claude.json",
                {"mcpServers": {"docs": {"command": "npx"}},
                 "projects": {"C:/outro": {"mcpServers": {"z": {"args": [1]}}}}},
                {"mcpServers": {"docs": {"command": "npx"}, "novo": {"command": "curl"}},
                 "projects": {"C:/outro": {"mcpServers": {"z": {"args": [1]}}}}},
                "mcp", lido["docs do .claude.json"]),
            "hooks.json de plugin com Stop: 5": (
                self.plugin / "hooks" / "hooks.json",
                {"hooks": {"PreToolUse": [hook("python3 x.py", "Bash")], "Stop": 5}},
                {"hooks": {"PreToolUse": [hook("python3 x.py", ".*")], "Stop": 5}},
                "hooks", lido["hook Bash do plugin"]),
        }

    def test_troca_no_arquivo_com_parte_fora_da_forma_aparece(self):
        for nome, (alvo, antes, depois, categoria, _lido) in self.casos().items():
            with self.subTest(caso=nome), self.plantado(alvo, antes):
                self.gravar_de_novo()
                with self.plantado(alvo, depois):
                    code, res = self.verificar(self.saida)
                self.assertEqual(code, 1, "a troca passou sem diferença")  # no 59b3813: código 0
                self.assertTrue(any(res["diferencas"][categoria].values()), res["diferencas"])

    def test_so_a_parte_fora_da_forma_fica_de_fora_com_o_hash(self):
        for nome, (alvo, antes, _depois, _categoria, lido) in self.casos().items():
            with self.subTest(caso=nome), self.plantado(alvo, antes):
                inv = self.gravar_de_novo()
                registros = [n for n in inv["arquivos_nao_lidos"] + inv["plugins_nao_lidos"]
                             if "forma inesperada" in n["motivo"]]
                self.assertEqual(len(registros), 1, registros)
                self.assertEqual(registros[0].get("sha256"), hashlib.sha256(alvo.read_bytes()).hexdigest())
                self.assertIn("o resto foi lido", registros[0]["motivo"])
                self.assertTrue(lido(inv), "a parte na forma não foi lida")  # no 59b3813: o arquivo inteiro de fora
                self.assertEqual(self.verificar(self.saida)[0], 0)

    def test_mudanca_so_na_parte_de_fora_ou_no_ilegivel_aparece_pelo_hash(self):
        settings, hooks = self.perfil / ".claude" / "settings.json", self.plugin / "hooks" / "hooks.json"
        casos = [(settings, {"permissions": {"allow": "Bash(*)"}}, {"permissions": {"allow": "Bash(rm *)"}},
                  "arquivos_nao_lidos"),
                 (hooks, "{ruim", "{ruim, outra coisa", "plugins_nao_lidos"),  # o JSON ilegível também leva o hash
                 (self.perfil / ".claude.json", "{ruim", "{ruim de novo", "arquivos_nao_lidos")]
        for alvo, antes, depois, categoria in casos:
            with self.subTest(arquivo=alvo.name, antes=str(antes)[:30]), self.plantado(alvo, antes):
                self.gravar_de_novo()
                with self.plantado(alvo, depois):  # só o que fica de fora muda: motivo igual, conteúdo outro
                    code, res = self.verificar(self.saida)
                self.assertEqual(code, 1, "a mudança no arquivo não lido passou sem diferença")  # no 59b3813: 0
                self.assertTrue(res["diferencas"][categoria]["adicionados"], res["diferencas"])


class TestPoda(unittest.TestCase):
    """A poda: sai a menor parte que contém o erro (numa lista ou num objeto de chaves livres) ou a chave da raiz."""

    def test_regra_da_poda(self):
        ip = carregar("inventario_plugins")
        settings, mcp = ip.FORMAS["settings.json"], ip.FORMAS[".mcp.json do plugin"]
        podado, erros = ip.podar({"hooks": {"PreToolUse": [{"matcher": ["x"], "hooks": []},
                                                           {"matcher": "Edit", "hooks": [
                                                               {"type": "command", "command": 1},
                                                               {"type": "command", "command": "ok"}]}],
                                            "Stop": 5},
                                  "permissions": {"allow": "x"}, "env": {"A": [1]}}, settings)
        self.assertEqual(podado, {"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [
            {"type": "command", "command": "ok"}]}]}, "env": {"A": [1]}})  # o que a forma não cobre fica como está
        self.assertEqual(erros, ["hooks.*[0].matcher: lista em vez de texto",
                                 "hooks.*[1].hooks[0].command: número em vez de texto",
                                 "hooks.*: número em vez de lista", "permissions.allow: texto em vez de lista"])
        self.assertIs(ip.podar([1], settings)[0], ip.REMOVIDO)
        self.assertEqual(ip.podar({"x": 1}, None), ({"x": 1}, []))
        self.assertEqual(ip.podar({"srv": {"command": "npx"}, "description": "x"}, mcp),  # o mapa na raiz do arquivo
                         ({"srv": {"command": "npx"}, "description": "x"}, []))
        self.assertEqual(ip.podar({"srv": {"command": ["npx"]}, "ok": {"command": "node"}}, mcp),
                         ({"ok": {"command": "node"}}, ["*.command: lista em vez de texto"]))
        self.assertEqual(ip.forma_inesperada({"permissions": {"allow": "x"}}, settings),
                         "permissions.allow: texto em vez de lista")  # o primeiro ponto, como antes
        self.assertEqual(ip.motivo_da_forma("JSON", {}, ["a: x", "b: y"]),
                         "JSON de forma inesperada (a: x e mais 1): o resto foi lido")


if __name__ == "__main__":
    unittest.main()
