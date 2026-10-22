"""Inventário do host por dentro dos plugins (análise do everything-claude-code, 21/10/2026, proposta 1; R54).

O inventário lia dos plugins só id, versão e escopo: os hooks que eles trazem (início de sessão, depois da
ferramenta, pedido de permissão) não apareciam, nem os servidores MCP e as skills dos plugins sincronizados. E um
matcher que nunca casa, ou que casa tudo (`tool == "Edit" || tool == "Write"`), passava sem alerta. Perfil fictício
numa pasta descartável (HOME falso): o plugin com hook aparece com origem `plugin:`; os matchers defeituosos são
acusados e os perfis da própria skill não; o canário plantado em `env`, argumentos, cabeçalhos e URL não sai;
`installPath` fora de `~/.claude/plugins/` não é lido; ligação (junção no Windows) não é seguida; o `verificar`
acusa hook acrescentado e lê o inventário do esquema 1.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import ENV, SCRIPTS, SKILL, criar_ligacao_dir


def carregar(nome: str):
    spec = importlib.util.spec_from_file_location(nome, SCRIPTS / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


IP, AH = carregar("inventario_plugins"), carregar("alertas_hooks")
CANARIO = "CANARIO-FIC-" + "7Q2"  # montado em execução; não pode aparecer em nenhuma saída
RAIZ_P = "${CLAUDE_PLUGIN_ROOT}"
ORIGEM = "plugin:guardiao@mercado|user"


def escrever(p: Path, conteudo) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(conteudo if isinstance(conteudo, str) else json.dumps(conteudo), encoding="utf-8", newline="\n")
    return p


def skill(pasta: Path, linha_description: str) -> None:
    escrever(pasta / "SKILL.md", f"---\nname: {pasta.name}\n{linha_description}\nlicense: MIT\n---\n# corpo\n")


class _Perfil(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="inventario-plugins-")).resolve()
        self.perfil, self.raiz = self.base / "perfil", self.base / "raiz"
        self.plugins = self.perfil / ".claude" / "plugins"
        self.guardiao = self.plugins / "cache" / "mercado" / "guardiao" / "1.0.0"
        g = self.guardiao
        escrever(g / ".claude-plugin" / "plugin.json", {
            "name": "guardiao", "version": "1.0.0", "skills": "./extra-skills",
            "hooks": ["./config/extra.json", {"Notification": [{"matcher": "permission_prompt", "hooks": [
                {"type": "mcp_tool", "server": "srv", "tool": "notificar", "input": {"x": CANARIO}}]}]}],
            "mcpServers": [{"embutido": {"command": "node", "args": ["--token", CANARIO], "env": {"K": CANARIO}}},
                           "./pacote.mcpb"]})
        self.hooks_json = escrever(g / "hooks" / "hooks.json", {"description": "fictício", "hooks": {
            "SessionStart": [{"matcher": "startup|resume|clear|compact", "hooks": [
                {"type": "command", "command": f'"{RAIZ_P}/hooks/inicio.sh" --chave {CANARIO}'},
                {"type": "command", "command": "bash", "args": [f"{RAIZ_P}/lib/x.sh"]}]}],
            "PostToolUse": [{"matcher": 'tool == "Edit" || tool == "Write"', "hooks": [
                {"type": "command", "command": "node", "args": [f"{RAIZ_P}/scripts/depois.js", f"--k={CANARIO}"]}]}],
            "PreToolUse": [{"matcher": 'tool == "Bash" && tool_input.command matches "(npm run dev)"', "hooks": [
                {"type": "command", "command": f"API_KEY={CANARIO} node x.js"}]}]}})
        escrever(g / "config" / "extra.json", {"hooks": {"Stop": [{"hooks": [
            {"type": "http", "url": f"https://hooks.exemplo.invalid/x?k={CANARIO}", "headers": {"A": CANARIO}}]}]}})
        self.inicio = escrever(g / "hooks" / "inicio.sh", "echo inicio\n")
        self.depois = escrever(g / "scripts" / "depois.js", "console.log(1)\n")
        escrever(g / ".mcp.json", {"mcpServers": {
            "remoto": {"type": "http", "url": f"https://mcp.exemplo.invalid/v1?token={CANARIO}",
                       "headers": {"Authorization": "Bearer " + CANARIO}},
            "local": {"command": f"TOKEN_X={CANARIO} C:/ferramentas/srv.exe --key {CANARIO}", "env": {"S": CANARIO}}}})
        skill(g / "skills" / "alfa", "description: Descrição A")                        # 11 caracteres
        skill(g / "skills" / "beta", "description: >\n  Linha um\n  linha dois")          # 19
        skill(g / "extra-skills" / "gama", 'description: "Entre aspas"')                  # 11
        fora = self.base / "pasta-externa"
        escrever(fora / "lib" / "x.sh", "echo fora\n")
        skill(fora / "delta", "description: " + "d" * 50)
        criar_ligacao_dir(g / "lib", fora / "lib")                    # ligação dentro do plugin
        criar_ligacao_dir(g / "skills" / "delta", fora / "delta")
        for nome in ("fugitivo", "juncao-alvo"):                      # hooks que NÃO podem ser lidos
            escrever(fora / nome / "hooks" / "hooks.json", {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
                {"type": "command", "command": f"externo-{nome}"}]}]}})
        criar_ligacao_dir(self.plugins / "cache" / "mercado" / "juncao", fora / "juncao-alvo")
        escrever(self.plugins / "installed_plugins.json", {"version": 2, "plugins": {
            "guardiao@mercado": [{"scope": "user", "version": "1.0.0", "installPath": str(g)}],
            "fugitivo@mercado": [{"scope": "project", "version": "1.0", "projectPath": "C:/Casos/CLIENTE-FICTICIO",
                                  "installPath": str(fora / "fugitivo")}],
            "juncao@mercado": [{"scope": "user", "version": "1.0",
                                "installPath": str(self.plugins / "cache" / "mercado" / "juncao")}]}})
        s = self.plugins / "synced" / "conta-ficticia" / "sincronizado"
        escrever(s / ".claude-plugin" / "plugin.json", {"name": "sincronizado", "version": "2.0"})
        escrever(s / "hooks" / "hooks.json", {"hooks": {"UserPromptSubmit": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "python"}]}]}})
        escrever(s / ".mcp.json", {"mcpServers": {"docs": {"type": "http", "url": "https://docs.exemplo.invalid/mcp"}}})
        skill(s / "skills" / "s1", "description: abc")
        escrever(self.plugins / "synced" / ".bucket-ficticio", "x")
        escrever(self.raiz / ".claude" / "settings.json", {"hooks": {"PreToolUse": [{"matcher": "Write", "hooks": [
            {"type": "command", "command": "python", "args": ["-B", "guarda.py"]}]}]}})
        self.saida = self.base / "inventario.json"

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def rodar(self, *args, python=("-B",)):
        r = subprocess.run([sys.executable, *python, str(SCRIPTS / "inventariar_host.py"), *map(str, args),
                            "--perfil", str(self.perfil), "--raiz", str(self.raiz)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=ENV, timeout=180)
        self.assertNotIn(CANARIO, r.stdout + r.stderr)
        try:
            return r.returncode, json.loads(r.stdout)
        except ValueError:
            self.fail("saída não é JSON: " + r.stdout[-400:] + r.stderr[-400:])

    def gravar(self) -> dict:
        code, res = self.rodar("gravar", "--saida", self.saida)
        self.assertEqual(code, 0, res)
        self.res = res
        return json.loads(self.saida.read_text(encoding="utf-8"))


class TestPluginsPorDentro(_Perfil):
    def test_plugin_com_hook_aparece_com_origem_de_plugin(self):
        inv = self.gravar()
        self.assertEqual(inv["schema_version"], "fundacao.inventario-host/2")
        do_plugin = [h for h in inv["hooks"] if h["origem"] == ORIGEM]
        self.assertEqual(sorted({h["evento"] for h in do_plugin}),
                         ["Notification", "PostToolUse", "PreToolUse", "SessionStart", "Stop"])
        inicio = next(h for h in do_plugin if h["evento"] == "SessionStart" and h["executavel"] == "inicio.sh")
        sha = hashlib.sha256(self.inicio.read_bytes()).hexdigest()
        self.assertEqual(inicio["scripts"], [{"caminho": "hooks/inicio.sh", "sha256": sha}])
        depois = next(h for h in do_plugin if h["evento"] == "PostToolUse")
        self.assertEqual((depois["executavel"], depois["scripts"][0]["sha256"]),
                         ("node", hashlib.sha256(self.depois.read_bytes()).hexdigest()))
        self.assertEqual(next(h for h in do_plugin if h["evento"] == "PreToolUse")["executavel"], "node")
        self.assertEqual(next(h for h in do_plugin if h["evento"] == "Stop")["host"], "hooks.exemplo.invalid")
        notif = next(h for h in do_plugin if h["evento"] == "Notification")
        self.assertEqual((notif["tipo"], notif["servidor"], notif["ferramenta"]), ("mcp_tool", "srv", "notificar"))
        self.assertIn({"id": "sincronizado@synced", "versao": "2.0", "escopo": "synced", "com_projeto": False},
                      inv["plugins"])
        self.assertIn("plugin:sincronizado@synced|synced", {h["origem"] for h in inv["hooks"]})
        skills = {s["origem"]: (s["skills"], s["caracteres_descricao"]) for s in inv["skills_de_plugins"]}
        self.assertEqual(skills, {ORIGEM: (3, 41), "plugin:sincronizado@synced|synced": (1, 3)})
        custo = inv["custo_de_contexto_estimado"]
        self.assertEqual((custo["skills_de_plugins"], custo["caracteres_descricao"], custo["tokens_estimados"]),
                         (4, 44, 11))
        self.assertIn("estimativa", custo["rotulo"])
        self.assertEqual(inv["plugins_lidos_por_dentro"], 2)

    def test_canario_de_mcp_e_de_hook_nao_aparece(self):
        inv = self.gravar()
        texto = self.saida.read_text(encoding="utf-8")
        self.assertNotIn(CANARIO, texto)
        mcp = {m["nome"]: m for m in inv["mcp"] if m["onde"] == ORIGEM}
        self.assertEqual(sorted(mcp), ["embutido", "local", "remoto"])
        self.assertEqual((mcp["remoto"]["tipo"], mcp["remoto"]["host"]), ("http", "mcp.exemplo.invalid"))
        self.assertEqual(mcp["local"]["executavel"], "srv.exe")
        self.assertEqual(mcp["embutido"]["executavel"], "node")
        self.assertTrue(all(set(m) <= {"cliente", "nome", "onde", "tipo", "executavel", "host"} for m in inv["mcp"]))
        self.assertIn({"origem": ORIGEM, "motivo": "pacote MCP (.mcpb, .dxt ou URL): não aberto"},
                      inv["plugins_nao_lidos"])

    def test_install_path_fora_da_pasta_de_plugins_nao_e_lido(self):
        inv = self.gravar()
        texto = self.saida.read_text(encoding="utf-8")
        for proibido in ("pasta-externa", "externo-fugitivo", "CLIENTE-FICTICIO"):
            self.assertNotIn(proibido, texto)
        self.assertIn({"origem": "plugin:fugitivo@mercado|project",
                       "motivo": "installPath fora da pasta de plugins: não lido"}, inv["plugins_nao_lidos"])
        self.assertFalse([h for h in inv["hooks"] if "fugitivo" in h["origem"]])

    def test_ligacao_dentro_da_pasta_de_plugins_nao_e_seguida(self):
        inv = self.gravar()
        texto = self.saida.read_text(encoding="utf-8")
        self.assertNotIn("externo-juncao-alvo", texto)
        self.assertIn({"origem": "plugin:juncao@mercado|user", "motivo": "installPath: ligação não seguida"},
                      inv["plugins_nao_lidos"])
        lib = next(h for h in inv["hooks"] if h["origem"] == ORIGEM and h["executavel"] == "bash")
        self.assertEqual(lib["scripts"], [{"caminho": "lib/x.sh", "nao_lido": "ligação não seguida"}])
        self.assertIn({"origem": ORIGEM, "motivo": "ligação não seguida", "item": "delta"}, inv["plugins_nao_lidos"])

    def test_verificar_acusa_hook_acrescentado(self):
        self.gravar()
        code, res = self.rodar("verificar", "--inventario", self.saida, python=("-I", "-B"))  # vizinhos sem sys.path
        self.assertEqual(code, 0, res)
        dados = json.loads(self.hooks_json.read_text(encoding="utf-8"))
        dados["hooks"]["PreToolUse"].append({"matcher": "Write", "hooks": [{"type": "command", "command": "novo"}]})
        escrever(self.hooks_json, dados)
        escrever(self.depois, "console.log(2)\n")
        code, res = self.rodar("verificar", "--inventario", self.saida)
        self.assertEqual(code, 1, res)
        self.assertEqual(res["diferencas"]["hooks"]["adicionados"], [ORIGEM + "|PreToolUse|Write|0"])
        self.assertEqual(len(res["diferencas"]["hooks"]["alterados"]), 1)        # o script mudou de hash
        self.assertEqual(res["diferencas"]["hooks"]["removidos"], [])
        self.assertIn(ORIGEM + " PreToolUse", res["alertas"]["matcher_nunca_casa"])

    def test_verificar_le_o_inventario_do_esquema_1(self):
        inv = self.gravar()

        def de_plugin(item: dict) -> bool:
            return str(item.get("origem", item.get("onde", ""))).startswith("plugin:")

        v1 = {"schema_version": "fundacao.inventario-host/1", "gerado_em": inv["gerado_em"], "perfil": inv["perfil"],
              "raiz": inv["raiz"], "skills": inv["skills"], "duplicatas": inv["duplicatas"],
              "plugins": [p for p in inv["plugins"] if p["escopo"] != "synced"], "catalogos": inv["catalogos"],
              "mcp": [m for m in inv["mcp"] if not de_plugin(m)],
              "hooks": [{k: v for k, v in h.items() if k not in ("tipo", "matcher_tipo")}
                        for h in inv["hooks"] if not de_plugin(h)]}
        escrever(self.saida, v1)
        code, res = self.rodar("verificar", "--inventario", self.saida)
        self.assertEqual(code, 1, res)
        self.assertIn("esquema fundacao.inventario-host/1", res["aviso"])
        self.assertTrue(all(not d["alterados"] and not d["removidos"] for d in res["diferencas"].values()), res)
        self.assertTrue(all(k.startswith("plugin:") for k in res["diferencas"]["hooks"]["adicionados"]))
        self.assertEqual(res["diferencas"]["plugins"]["adicionados"], ["sincronizado@synced|synced|False"])


class TestAlertasDeMatcher(_Perfil):
    def test_matchers_defeituosos_sao_acusados(self):
        inv = self.gravar()
        achados = {(a["alerta"], a["origem"], a["evento"]) for a in inv["alertas"]}
        self.assertIn(("matcher_nunca_casa", ORIGEM, "PreToolUse"), achados)
        self.assertIn(("matcher_casa_tudo", ORIGEM, "PostToolUse"), achados)
        self.assertIn(("matcher_casa_tudo", "plugin:sincronizado@synced|synced", "UserPromptSubmit"), achados)
        fora = {(o, e) for a, o, e in achados if a == "evento_fora_do_guarda"}
        self.assertEqual(fora, {(ORIGEM, e) for e in ("Notification", "PostToolUse", "SessionStart", "Stop")}
                         | {("plugin:sincronizado@synced|synced", "UserPromptSubmit")})
        self.assertFalse([a for a in inv["alertas"] if a["origem"].startswith("raiz:")])
        self.assertFalse([a for a in achados if a[2] == "SessionStart" and a[0] != "evento_fora_do_guarda"])
        self.assertIn("alternativa vazia", next(a["motivo"] for a in inv["alertas"]
                                                if a["alerta"] == "matcher_casa_tudo" and a["evento"] == "PostToolUse"))
        self.assertIn(ORIGEM + " PostToolUse", self.res["alertas"]["matcher_casa_tudo"])

    def test_regra_do_matcher(self):
        casos = {("PreToolUse", None): None, ("PreToolUse", "*"): None, ("PreToolUse", ""): None,
                 ("PreToolUse", "Edit|Write"): None, ("PreToolUse", "Edit, Write"): None,
                 ("PreToolUse", "^Notebook"): None, ("PreToolUse", "mcp__memory__.*"): None,
                 ("PreToolUse", "mcp__github__criar"): None, ("PostToolUse", "Edit.*"): None,
                 ("SessionStart", "startup|compact"): None, ("Notification", "qualquer_tipo"): None,
                 ("PreToolUse", "Bassh"): "matcher_nunca_casa", ("PreToolUse", "Bash(git *)"): "matcher_nunca_casa",
                 ("PreToolUse", "mcp__memory"): "matcher_nunca_casa", ("SessionStart", "Bash"): "matcher_nunca_casa",
                 ("PreTooluse", "Bash"): "matcher_nunca_casa", ("PreToolUse", ".*"): "matcher_casa_tudo",
                 ("PreToolUse", "(Edit|)"): "matcher_casa_tudo", ("Stop", "Bash"): "matcher_casa_tudo",
                 # Regra oficial (revisão de segurança da 1.7.7, R177-VAL-03): só letras, espaços e `|` é lista
                 # exata, mesmo com `||`; a alternativa vazia casa tudo numa expressão; o que o re não compila
                 # fica indeterminado.
                 ("PreToolUse", "Edit || Write"): None, ("PreToolUse", "a || b"): "matcher_nunca_casa",
                 ("PreToolUse", 'tool == "Edit" || tool == "Write"'): "matcher_casa_tudo",
                 ("PreToolUse", "Edit|(?<=a+)Write"): "matcher_indeterminado"}
        for (evento, matcher), esperado in casos.items():
            with self.subTest(evento=evento, matcher=matcher):
                self.assertEqual(AH.avaliar_matcher(evento, matcher)[1], esperado)
        self.assertEqual(AH.avaliar_matcher("PreToolUse", "*")[0], "todas")

    def test_perfis_da_skill_passam_sem_alerta(self):
        hooks = []
        for perfil in sorted((SKILL / "assets" / "host").rglob("settings*.json")):
            for evento, grupos in json.loads(perfil.read_text(encoding="utf-8")).get("hooks", {}).items():
                hooks += [{"origem": "raiz:" + perfil.name, "evento": evento, "matcher": g.get("matcher")}
                          for g in grupos for _ in g.get("hooks", [])]
        self.assertGreaterEqual(len(hooks), 4)
        self.assertEqual(AH.alertas(hooks, []), [])


class TestLeituraContida(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="leitura-contida-")).resolve()
        escrever(self.base / "a" / "b.json", {"x": 1})
        escrever(self.base / "grande.txt", "x" * 64)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_caminho_para_fora_e_recusado_sem_ler(self):
        leitor = IP._Leitor()
        for rel, motivo in (("C:/Windows/win.ini", "caminho absoluto"), ("/etc/passwd", "caminho absoluto"),
                            ("../fora.json", "caminho com .. ou :"), ("a/../../x", "caminho com .. ou :"),
                            ("a/b.json:fluxo", "caminho com .. ou :"), ("/".join("p" * 9), "caminho fundo demais"),
                            ("a/nada.json", "ausente"), ("a", "pasta no lugar do arquivo")):
            with self.subTest(rel=rel):
                self.assertEqual(leitor.ler(self.base, rel), motivo)
        self.assertEqual(leitor.bytes, 0)
        self.assertEqual(leitor.ler_json(self.base, "a/b.json", "o", []), {"x": 1})

    def test_tetos_valem_durante_a_varredura(self):
        leitor = IP._Leitor()
        self.assertEqual(leitor.ler(self.base, "grande.txt", limite=10), "arquivo grande demais")
        self.assertEqual(leitor.ler(self.base, "grande.txt", limite=10, truncar=True), b"x" * 10)
        teto = dict(IP.TETO)
        try:
            IP.TETO["bytes"] = 20
            self.assertEqual(leitor.ler(self.base, "grande.txt", limite=64, truncar=True), "teto de leitura atingido")
            IP.TETO["entradas"] = 1
            for i in range(3):
                (self.base / "muitas" / str(i)).mkdir(parents=True)
            with self.assertRaises(IP._Teto):
                leitor.pastas(self.base / "muitas", "o", [])
        finally:
            IP.TETO.clear()
            IP.TETO.update(teto)


if __name__ == "__main__":
    unittest.main()
