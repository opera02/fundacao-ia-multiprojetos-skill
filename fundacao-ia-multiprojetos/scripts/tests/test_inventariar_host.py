"""Inventário do ecossistema do host (proposta 15 da análise do vibe-coding-toolkit, 21/10/2026; R54).

O inventário de componentes da fundação cobria pacotes, modelo, kit, três arquivos do host e a skill da
fundação — não as outras skills, os plugins, os servidores MCP nem os hooks de terceiros que o host carrega.
`inventariar_host.py` lê só a estrutura (perfil fictício aqui), aponta nomes repetidos e a primeira linha da
licença, e NUNCA leva valores de `env`, `headers`, argumentos de servidor MCP ou dados da conta.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from apoio import criar_ligacao_dir, rodar_script

EMAIL_FICTICIO = "titular" + chr(64) + "exemplo.invalid"  # montado em execução: a cópia pública recusa e-mail no texto
SEGREDOS = ("SEGREDO-FIC-ARG", "SEGREDO-FIC-ENV", "SEGREDO-FIC-CODEX", EMAIL_FICTICIO, "SEGREDO-FIC-URL")


def skill(pasta: Path, nome: str, licenca: str | None = None) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "SKILL.md").write_text(f"---\nname: {nome}\ndescription: ficticia\nmetadata:\n  version: \"1.0\"\n---\n# x\n",
                                    encoding="utf-8")
    if licenca:
        (pasta / "LICENSE.txt").write_text(licenca + "\nresto da licença\n", encoding="utf-8")


class TestInventarioDoHost(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="inventario-host-"))
        self.perfil, self.raiz = self.base / "perfil", self.base / "raiz"
        skill(self.perfil / ".claude" / "skills" / "alfa", "alfa")
        skill(self.perfil / ".agents" / "skills" / "alfa-copia", "alfa")
        skill(self.perfil / ".agents" / "skills" / "docx", "docx", "© 2025 Fornecedor. All rights reserved.")
        skill(self.base / "fora" / "beta", "beta")
        self.tipo_ligacao = criar_ligacao_dir(self.perfil / ".claude" / "skills" / "beta", self.base / "fora" / "beta")
        plugins = self.perfil / ".claude" / "plugins"
        plugins.mkdir(parents=True)
        (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
            "superpowers@mercado": [{"scope": "user", "version": "5.1.0", "installPath": "x", "installedAt": "t"}]}}),
            encoding="utf-8")
        (plugins / "known_marketplaces.json").write_text(json.dumps({"mercado": {
            "source": {"source": "github", "repo": "dono/mercado"}, "installLocation": "y"}}), encoding="utf-8")
        (self.perfil / ".claude.json").write_text(json.dumps({
            "oauthAccount": {"emailAddress": EMAIL_FICTICIO},
            "mcpServers": {"docs": {"type": "stdio", "command": "C:/ferramentas/node.exe",
                                    "args": ["--token", "SEGREDO-FIC-ARG"], "env": {"API_KEY": "SEGREDO-FIC-ENV"}}},
            "projects": {str(self.raiz): {"mcpServers": {"remoto": {"type": "http",
                                                                     "url": "https://mcp.exemplo.invalid/v1?k=SEGREDO-FIC-URL",
                                                                     "headers": {"Authorization": "SEGREDO-FIC-ENV"}}}}}}),
            encoding="utf-8")
        (self.perfil / ".codex").mkdir()
        (self.perfil / ".codex" / "config.toml").write_text(
            '[mcp_servers.leitor]\ncommand = "npx"\nargs = ["-y", "pacote"]\nenv = { CHAVE_FICTICIA = "SEGREDO-FIC-CODEX" }\n',
            encoding="utf-8")
        hooks = self.raiz / ".claude" / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "guarda.py").write_text("print('guarda')\n", encoding="utf-8")
        (self.raiz / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [{
            "matcher": "Write", "hooks": [{"type": "command", "command": "python",
                                           "args": ["-B", str(hooks / "guarda.py")]}]}]}}), encoding="utf-8")
        self.saida = self.base / "inventario.json"

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def rodar(self, *args):
        p = rodar_script("inventariar_host.py", *args, "--perfil", self.perfil, "--raiz", self.raiz)
        try:
            return p.returncode, json.loads(p.stdout)
        except ValueError:
            self.fail("saída não é JSON: " + p.stdout[-400:] + p.stderr[-400:])

    def test_statusline_tem_presenca_tipo_hash_sem_expor_comando(self):
        import hashlib
        comando = "powershell.exe -Command SEGREDO-FICTICIO-STATUS"
        cfg = self.raiz / ".claude/settings.json"
        dados = json.loads(cfg.read_text(encoding="utf-8"))
        dados["statusLine"] = {"type": "command", "command": comando}
        cfg.write_text(json.dumps(dados), encoding="utf-8")
        code, _ = self.rodar("gravar", "--saida", self.saida)
        self.assertEqual(code, 0)
        bruto = self.saida.read_text(encoding="utf-8")
        self.assertNotIn("SEGREDO-FICTICIO-STATUS", bruto)
        sinais = {s["origem"]: s for s in json.loads(bruto).get("status_lines", [])}
        self.assertEqual(sinais.get("raiz:settings.json"), {
            "origem": "raiz:settings.json", "presente": True, "tipo": "command",
            "comando_sha256": hashlib.sha256(comando.encode()).hexdigest()})
        self.assertEqual(sinais.get("perfil:settings.json"), {
            "origem": "perfil:settings.json", "presente": False, "tipo": None, "comando_sha256": None})

    def test_statusline_trocada_removida_ou_com_outro_tipo_aparece(self):
        cfg = self.raiz / ".claude/settings.json"
        original = json.loads(cfg.read_text(encoding="utf-8"))
        original["statusLine"] = {"type": "command", "command": "python sinais_sessao.py --status-line"}
        cfg.write_text(json.dumps(original), encoding="utf-8")
        self.rodar("gravar", "--saida", self.saida)
        for nova in ({"type": "command", "command": "powershell.exe OUTRO-COMANDO-FICTICIO"},
                     {"type": "outro", "command": original["statusLine"]["command"]}, None):
            with self.subTest(status=nova):
                dados = dict(original)
                if nova is None:
                    dados.pop("statusLine")
                else:
                    dados["statusLine"] = nova
                cfg.write_text(json.dumps(dados), encoding="utf-8")
                code, res = self.rodar("verificar", "--inventario", self.saida)
                self.assertEqual(code, 1, res)
                self.assertEqual(res.get("diferencas", {}).get("status_lines", {}).get("alterados"),
                                 ["raiz:settings.json"])

    def test_inventario_anterior_sem_statusline_fica_pendente(self):
        self.rodar("gravar", "--saida", self.saida)
        antes = json.loads(self.saida.read_text(encoding="utf-8"))
        antes.pop("status_lines", None)
        self.saida.write_text(json.dumps(antes), encoding="utf-8")
        code, res = self.rodar("verificar", "--inventario", self.saida)
        self.assertEqual(code, 1, res)
        self.assertIs(res.get("ok"), False)
        self.assertIs(res.get("conferencia_pendente"), True)

    def test_gravar_inventaria_sem_segredos(self):
        code, res = self.rodar("gravar", "--saida", self.saida)
        self.assertEqual(code, 0, res)
        texto = self.saida.read_text(encoding="utf-8")
        for segredo in SEGREDOS:
            self.assertNotIn(segredo, texto)
        inv = json.loads(texto)
        nomes = sorted(s["nome"] for s in inv["skills"])
        self.assertEqual(nomes, ["alfa", "alfa", "beta", "docx"])
        self.assertEqual(inv["duplicatas"], [{"nome": "alfa", "locais": sorted(
            s["local"] for s in inv["skills"] if s["nome"] == "alfa")}])
        beta = next(s for s in inv["skills"] if s["nome"] == "beta")
        self.assertTrue(beta["ligacao"])
        docx = next(s for s in inv["skills"] if s["nome"] == "docx")
        self.assertTrue(docx["licenca_restritiva_declarada"])
        self.assertEqual(inv["plugins"][0]["id"], "superpowers@mercado")
        self.assertEqual(inv["plugins"][0]["versao"], "5.1.0")
        mcp = {(m["cliente"], m["nome"]): m for m in inv["mcp"]}
        self.assertEqual(mcp[("claude", "docs")]["executavel"], "node.exe")
        self.assertEqual(mcp[("claude", "remoto")]["host"], "mcp.exemplo.invalid")
        self.assertEqual(mcp[("codex", "leitor")]["executavel"], "npx")
        self.assertEqual(len(inv["hooks"]), 1)
        self.assertEqual(len(inv["hooks"][0]["scripts"]), 1)

    def test_verificar_aponta_o_que_mudou(self):
        self.rodar("gravar", "--saida", self.saida)
        code, res = self.rodar("verificar", "--inventario", self.saida)
        self.assertEqual(code, 0, res)
        (self.perfil / ".agents" / "skills" / "docx" / "SKILL.md").write_text("---\nname: docx\n---\nmudou\n",
                                                                            encoding="utf-8")
        (self.raiz / ".claude" / "hooks" / "guarda.py").write_text("print('outra')\n", encoding="utf-8")
        code, res = self.rodar("verificar", "--inventario", self.saida)
        self.assertEqual(code, 1, res)
        self.assertEqual(sorted(res["diferencas"]["skills"]["alterados"]), ["perfil:.agents/skills/docx"])
        self.assertEqual(len(res["diferencas"]["hooks"]["alterados"]), 1)


class TestAtualizacaoConfereOInventario(unittest.TestCase):
    """O `atualizar_fundacao.py aplicar` termina conferindo o inventário do host, sem bloquear."""

    setUp, tearDown, rodar = TestInventarioDoHost.setUp, TestInventarioDoHost.tearDown, TestInventarioDoHost.rodar

    def test_conferencia_informa_sem_bloquear(self):
        import importlib.util
        from apoio import SCRIPTS
        spec = importlib.util.spec_from_file_location("atualizar_fundacao", SCRIPTS / "atualizar_fundacao.py")
        af = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(af)
        self.assertIsNone(af._inventario_host(self.raiz))                       # sem inventário: nada
        arq = self.raiz / "registry" / "inventario-host.json"
        code, res = self.rodar("gravar", "--saida", arq)
        self.assertEqual(code, 0, res)
        self.assertEqual(af._inventario_host(self.raiz), {"conferido": True, "sem_mudancas": True, "mudancas": {}})
        (self.raiz / ".claude" / "hooks" / "guarda.py").write_text("print('outra')", encoding="utf-8")
        res = af._inventario_host(self.raiz)
        self.assertEqual((res["sem_mudancas"], res["mudancas"]), (False, {"hooks": {"alterados": 1}}))


if __name__ == "__main__":
    unittest.main()
