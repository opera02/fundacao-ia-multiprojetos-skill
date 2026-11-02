"""Canário do WSL (1.7.10, pacote CANARIO; reconferência REV2, contratos §6 e §7): o ensaio convive com os hooks do
pacote HOOKS e mede o perfil e o lançador do pacote HOST. O `preparar` copia os 6 hooks do perfil para
`<base>/.claude/hooks` (sem eles o PreToolUse com `onFailure: block` barraria tudo); o `rodar` confere que o perfil
gerado aponta para essas cópias, com o mesmo SHA-256, e que o TMPDIR do lançador está no `allowRead`. Os testes de
integração rodam o `decide()` dos hooks reais e o `gerar-perfil-projeto` real quando a árvore já os tem (pulados com o
motivo até a integração dos pacotes); o de ponta a ponta usa um binário FALSO no lugar do Claude Code, que devolve
transcrições stream-json (nada abre o Claude Code de verdade)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from apoio import ENV, SCRIPTS
from test_ensaio_isolamento import HOOKS, LINUX, Base, _ctx, executor_bom

HOOKS_REAIS = SCRIPTS.parent / "assets" / "hooks"
PREPARO_REAL = SCRIPTS.parent / "assets" / "host" / "preparo_host.py"


def _tem(arquivo: Path, trecho: str) -> bool:
    try:
        return trecho in arquivo.read_text(encoding="utf-8")
    except OSError:
        return False


HOOKS_INTEGRADOS = all((HOOKS_REAIS / n).is_file() for n in HOOKS) and _tem(HOOKS_REAIS / "guarda_identidade.py",
                                                                            "def outro_projeto")
HOST_INTEGRADO = _tem(PREPARO_REAL, '"gerar-perfil-projeto"') and _tem(PREPARO_REAL, "def temp_do_projeto")
MOTIVO_HOOKS = "depende do pacote HOOKS integrado (os 6 hooks do perfil em assets/hooks, com o guarda de outro projeto)"
MOTIVO_HOST = ("depende do pacote HOST integrado (preparo_host.py gerar-perfil-projeto) e do Linux (os caminhos do "
               "perfil são do Ubuntu)")


def perfil_como_o_host(base: Path, temp_base: str, hooks=HOOKS, *, pasta: Path | None = None) -> dict:
    """O pedaço do perfil do HOST que o ensaio confere: os hooks em `<raiz>/.claude/hooks` com `python3 -I -B` e o
    temp do projeto no allowRead (preparo_host._montar_perfil_wsl)."""
    pasta = pasta or base / ".claude" / "hooks"
    grupos = [{"matcher": "*", "hooks": [{"type": "command", "command": "/usr/bin/python3",
                                          "args": ["-I", "-B", (pasta / n).as_posix()], "onFailure": "block"}]}
              for n in hooks]
    return {"env": {"FUNDACAO_FERRAMENTAS": "Bash,Read"}, "hooks": {"PreToolUse": grupos},
            "sandbox": {"enabled": True, "filesystem": {
                "allowRead": [(base / "fundacao").as_posix(), temp_base.rstrip("/") + "/fundacao-ia-ensaio-a"],
                "denyRead": ["/tmp"]}}}


class TestHooksNoPreparar(Base):
    def test_preparar_copia_os_6_hooks_com_o_sha256_no_plano(self):
        plano = self.mod.preparar(self.base)
        self.assertEqual(sorted(plano["hooks"]), sorted(HOOKS))
        for nome in HOOKS:
            copia = self.base / ".claude" / "hooks" / nome
            self.assertEqual(copia.read_bytes(), (self.mod.HOOKS_ORIGEM / nome).read_bytes())
            self.assertEqual(plano["hooks"][nome], self.mod._sha256(copia.read_bytes()))

    def test_preparar_sem_um_hook_na_skill_recusa_sem_criar_nada(self):
        (self.mod.HOOKS_ORIGEM / "guarda_leitura.py").unlink()
        with self.assertRaises(self.mod.Erro) as ctx:
            self.mod.preparar(self.base)
        self.assertIn("depende do pacote HOOKS integrado", str(ctx.exception))
        self.assertIn("guarda_leitura.py", str(ctx.exception))
        self.assertFalse(self.base.exists())
        self.assertEqual(list(self.temp_base.iterdir()), [])

    @unittest.skipUnless(LINUX, "ligação simbólica conferida no Linux")
    def test_hook_que_e_ligacao_na_skill_recusa(self):
        alvo = self.mod.HOOKS_ORIGEM / "guarda_rede.py"
        real = self.tmp / "fora.py"
        real.write_text("# outro\n", encoding="utf-8")
        alvo.unlink()
        alvo.symlink_to(real)
        with self.assertRaises(self.mod.Erro):
            self.mod.preparar(self.base)


class TestConferirPerfil(Base):
    def setUp(self):
        super().setUp()
        self.plano = self.mod.preparar(self.base)
        self.arq = self.tmp / "perfil.json"

    def conferir(self, perfil: dict) -> list:
        self.arq.write_text(json.dumps(perfil), encoding="utf-8")
        return self.mod.conferir_perfil_do_ensaio(self.arq, self.base, self.plano)

    def test_perfil_que_aponta_para_as_copias_serve(self):
        self.assertEqual(self.conferir(perfil_como_o_host(self.base, self.temp_base.as_posix())), [])

    def test_cada_defeito_do_perfil_ou_dos_hooks_recusa(self):
        tb = self.temp_base.as_posix()
        casos = {
            "sem hook nenhum": ({**perfil_como_o_host(self.base, tb), "hooks": {}}, "hook nenhum"),
            "hook não preparado": (perfil_como_o_host(self.base, tb, (*HOOKS, "aviso_copia.py")), "não foi preparado"),
            "hook fora da pasta": (perfil_como_o_host(self.base, tb, pasta=self.tmp / "outra"),
                                   "fora de .claude/hooks"),
            "TMPDIR fora do allowRead": (perfil_como_o_host(self.base, (self.tmp / "x").as_posix()), "allowRead"),
        }
        for nome, (perfil, trecho) in casos.items():
            with self.subTest(nome):
                problemas = self.conferir(perfil)
                self.assertTrue(any(trecho in p for p in problemas), problemas)

    def test_hook_alterado_ou_ausente_recusa(self):
        perfil = perfil_como_o_host(self.base, self.temp_base.as_posix())
        hook = self.base / ".claude" / "hooks" / "guarda_identidade.py"
        hook.write_text("# trocado depois do preparar\n", encoding="utf-8")
        self.assertTrue(any("mudou desde o preparar" in p for p in self.conferir(perfil)))
        hook.unlink()
        self.assertTrue(any("ausente" in p for p in self.conferir(perfil)))

    def test_rodar_recusa_o_perfil_que_nao_serve_antes_das_sessoes(self):
        perfil = perfil_como_o_host(self.base, (self.tmp / "x").as_posix())
        self.arq.write_text(json.dumps(perfil), encoding="utf-8")
        chamadas = []

        def exe(base, proj, sessao):
            chamadas.append(sessao["rotulo"])
            return executor_bom(self.plano["nonce"])(base, proj, sessao)

        with self.assertRaises(self.mod.Erro):
            self.mod.rodar(self.base, executor=exe, perfil_info={"gerado": True, "arquivo": self.arq.as_posix()},
                           sandbox_ligado=True, linux=True, contexto=_ctx())
        self.assertEqual(chamadas, [])
        self.arq.write_text(json.dumps(perfil_como_o_host(self.base, self.temp_base.as_posix())), encoding="utf-8")
        rel = self.mod.rodar(self.base, executor=exe, perfil_info={"gerado": True, "arquivo": self.arq.as_posix()},
                             sandbox_ligado=True, linux=True, contexto=_ctx())
        self.assertIs(rel["conclusao"]["confina_comandos"], True)


class TestLinhaDeComandoDoRodar(Base):
    """O `rodar` real pela linha de comando, até antes da primeira sessão (o "Claude Code" é o próprio Python, que
    responde `--version` com x.y.z; nenhum `claude -p` roda)."""

    def setUp(self):
        super().setUp()
        self.mod.preparar(self.base)
        self.config = self.mod.config_do_ensaio(self.base)  # no ext4 da casa do teste (REV3), não na base

    def rodar(self, *extra):
        r = subprocess.run([sys.executable, "-B", str(SCRIPTS / "ensaio_isolamento_wsl.py"), "rodar", "--base",
                            str(self.base), "--claude", sys.executable, "--temp-base", self.temp_base.as_posix(),
                            *map(str, extra)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=self.env, timeout=120)
        return r, json.loads(r.stdout)

    def test_sem_login_na_configuracao_do_ensaio_recusa_com_o_comando(self):
        r, saida = self.rodar()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("CLAUDE_CONFIG_DIR=", saida["erro"])
        self.assertIn("/login", saida["erro"])

    def test_hook_divergente_do_plano_recusa_codigo_2(self):
        (self.config / ".credentials.json").write_text("{}", encoding="utf-8")  # login fictício (só a existência)
        preparo = self.tmp / "preparo_falso.py"
        perfil = perfil_como_o_host(self.base, self.temp_base.as_posix())
        preparo.write_text("import sys\n"
                           "i = sys.argv.index('--saida')\n"
                           f"open(sys.argv[i + 1], 'w', encoding='utf-8').write({json.dumps(perfil)!r})\n",
                           encoding="utf-8", newline="\n")
        (self.base / ".claude" / "hooks" / "guarda_ferramentas.py").write_text("# trocado\n", encoding="utf-8")
        r, saida = self.rodar("--preparo-host", preparo)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("guarda_ferramentas.py mudou", saida["erro"])
        self.assertNotIn("rodado_em", json.loads((self.base / "plano.json").read_text(encoding="utf-8")))

    @unittest.skipUnless(LINUX, "a base só é conferida contra o caminho da forma no Linux")
    def test_base_fora_do_caminho_da_forma_drvfs_recusa(self):
        """O preparar confere a base contra a forma; o rodar real confere de novo (o plano pode ter sido trocado)."""
        (self.config / ".credentials.json").write_text("{}", encoding="utf-8")
        plano = json.loads((self.base / "plano.json").read_text(encoding="utf-8"))
        plano["forma"] = "drvfs:/mnt/e/ensaio-canario"
        (self.base / "plano.json").write_text(json.dumps(plano), encoding="utf-8", newline="\n")
        r, saida = self.rodar()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("caminho da forma drvfs", saida["erro"])

    @unittest.skipUnless(hasattr(os, "geteuid"), "a recusa de root é do POSIX")
    def test_root_recusa(self):
        import contextlib
        import io
        from unittest import mock
        saida = io.StringIO()
        with mock.patch.object(self.mod.os, "geteuid", lambda: 0), \
                mock.patch.object(self.mod, "conferir_claude", lambda c, v: ("2.1.302", "0" * 64)), \
                contextlib.redirect_stdout(saida):
            codigo = self.mod.main(["rodar", "--base", str(self.base), "--claude", sys.executable,
                                    "--temp-base", self.temp_base.as_posix()])
        self.assertEqual(codigo, 2)
        self.assertIn("sem sudo", json.loads(saida.getvalue())["erro"])


@unittest.skipUnless(HOOKS_INTEGRADOS, MOTIVO_HOOKS)
class TestIntegracaoComOsHooksReais(Base):
    """O `decide()` dos hooks REAIS (copiados pela base) sobre todos os comandos das sondas: as variantes por
    subprocesso e os controles passam (o sandbox é quem mede); a leitura literal do outro projeto é negada pelo
    guarda-corpo de texto (o esperado, documentado no limite do guarda_identidade)."""

    def setUp(self):
        super().setUp()
        self.mod.HOOKS_ORIGEM = HOOKS_REAIS
        self.plano = self.mod.preparar(self.base)
        self.env = {"FUNDACAO_PROJECT": "ensaio-a", "FUNDACAO_RAIZ": self.base.as_posix(),
                    "FUNDACAO_FERRAMENTAS": "Bash,Read,Edit,Write,Glob,Grep,Skill,Task,TodoWrite",
                    "FUNDACAO_MCP_PERMITIDAS": ""}

    def carregar_hook(self, nome):
        spec = importlib.util.spec_from_file_location("hook_" + nome[:-3], self.base / ".claude" / "hooks" / nome)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo

    def sessoes(self):
        ctx = _ctx(barramentos=("/run/user/1000/bus",))
        for sonda in self.mod.SONDAS:
            yield from sonda["sessoes"](self.base, self.plano, self.plano["nonce"], ctx)
        yield self.mod._sessao_seccomp(self.plano["nonce"])

    def test_guarda_identidade_deixa_as_variantes_do_so_e_nega_a_literal_do_outro_projeto(self):
        guarda = self.carregar_hook("guarda_identidade.py")
        cwd = (self.base / "projects" / "ensaio-a").as_posix()
        negados, liberados = [], 0
        for ses in self.sessoes():
            for papel, rot, cmd in zip(ses["papeis"], ses["rotulos_comandos"], ses["comandos"]):
                decisao = guarda.decide({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": cwd}, self.env)
                if decisao is None:
                    liberados += 1
                    continue
                negados.append((ses["rotulo"], rot))
                self.assertEqual(papel, "permissao", (ses["rotulo"], rot, decisao))
        self.assertEqual(negados, [("leitura_outro", "cat")])
        self.assertGreater(liberados, 20)

    def test_guarda_ferramentas_libera_o_bash_da_lista_e_nega_o_resto(self):
        guarda = self.carregar_hook("guarda_ferramentas.py")
        self.assertIsNone(guarda.decide({"tool_name": "Bash"}, self.env))
        self.assertIsNotNone(guarda.decide({"tool_name": "WebFetch"}, self.env))

    def test_o_hook_roda_como_processo_com_python_isolado(self):
        """Como o perfil o registra (`python3 -I -B <raiz>/.claude/hooks/...`): a cópia da base responde."""
        hook = self.base / ".claude" / "hooks" / "guarda_identidade.py"
        cwd = (self.base / "projects" / "ensaio-a").as_posix()
        sonda = next(s for s in self.mod.SONDAS if s["id"] == "leitura_outro_projeto")
        ses = sonda["sessoes"](self.base, self.plano, self.plano["nonce"], _ctx())[0]
        amb = {**ENV, **self.env}
        for cmd, negado in ((ses["comandos"][1], True), (ses["comandos"][2], False)):
            evento = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": cwd})
            r = subprocess.run([sys.executable, "-I", "-B", str(hook)], input=evento.encode("utf-8"),
                               capture_output=True, env=amb, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(b'"deny"' in r.stdout, negado, (cmd, r.stdout))


@unittest.skipUnless(LINUX and HOST_INTEGRADO, MOTIVO_HOST)
class TestIntegracaoComOPerfilDoHost(Base):
    """O `gerar-perfil-projeto` REAL do HOST sobre a base do ensaio: o perfil aponta os hooks para as cópias da base,
    reabre o TMPDIR do lançador e nega /tmp, state/ e o outro projeto; e serve ao ensaio sem ajuste."""

    def test_perfil_real_do_host_serve_ao_ensaio(self):
        if HOOKS_INTEGRADOS:
            self.mod.HOOKS_ORIGEM = HOOKS_REAIS
        plano = self.mod.preparar(self.base)
        destino = self.base / "perfil-ensaio-a.settings.json"
        info = self.mod.gerar_perfil_pelo_host(PREPARO_REAL, self.base, destino)
        self.assertTrue(info["gerado"], info)
        self.assertEqual(self.mod.conferir_perfil_do_ensaio(destino, self.base, plano), [])
        perfil = json.loads(destino.read_text(encoding="utf-8"))
        args = [h["args"][-1] for grupos in perfil["hooks"].values() for g in grupos for h in g["hooks"]]
        self.assertEqual(sorted(Path(a).name for a in args), sorted(HOOKS))
        fs = perfil["sandbox"]["filesystem"]
        self.assertIn(self.temp_base.as_posix() + "/fundacao-ia-ensaio-a", fs["allowRead"])
        self.assertIn("/tmp", fs["denyRead"])
        negacoes = perfil["permissions"]["deny"]
        self.assertIn(f"Read(/{self.base.as_posix()}/state/**)", negacoes)
        self.assertIn(f"Read(/{self.base.as_posix()}/projects/ensaio-b/**)", negacoes)
        self.assertIs(self.mod.sandbox_ligado_do_perfil(destino), True)
        self.assertIn("Bash", self.mod.ferramentas_do_perfil(destino).split(","))


CLAUDE_FALSO = r'''#!/usr/bin/python3
"""Binário FALSO do teste no lugar do Claude Code: simula uma sessão confinada e devolve stream-json."""
import json, os, re, subprocess, sys
from pathlib import Path
if "--version" in sys.argv:
    print("2.1.302 (Claude Code)")
    sys.exit(0)
aqui = Path(__file__).resolve().parent
fontes = sys.argv[sys.argv.index("--setting-sources") + 1]
with open(aqui / "sessoes.jsonl", "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"argv": sys.argv[1:-1], "env": dict(os.environ), "cwd": os.getcwd()}) + "\n")
init = {"type": "system", "subtype": "init", "tools": ["Bash"], "mcp_servers": [], "skills": [], "agents": [],
        "plugins": []}
if "--plugin-dir" in sys.argv:
    init["plugins"] = [{"name": "ensaio-plugin", "path": sys.argv[sys.argv.index("--plugin-dir") + 1]}]
if fontes == "local,project":
    init["skills"], init["agents"] = ["ensaio-aninhada"], ["ensaio-agente"]
saida = [init]
for n, linha in enumerate(re.findall(r"^\d+\. (.*)$", sys.argv[-1], re.M)):
    m = re.search(r"; echo FIM-([0-9a-f]+)-(\d+)-\$\?$", linha)
    nonce, i = m.group(1), m.group(2)
    texto, erro = None, False
    if "PY-OK-" in linha:
        texto = f"PY-OK-{nonce}\nFIM-{nonce}-{i}-0"
    elif linha.startswith("/usr/bin/curl"):
        texto = f"REDE-{nonce}-000-403\nFIM-{nonce}-{i}-56"
    elif "TEMP-" in linha:
        tmp = os.environ.get("TMPDIR", "")
        texto = f"TEMP-{nonce}|{tmp}|{tmp}\nFIM-{nonce}-{i}-0"
    elif "ensaio-so.json" in linha or "LEIA.md" in linha or linha.startswith("echo plugin-ping"):
        r = subprocess.run(["/bin/bash", "-c", linha], capture_output=True, text=True)
        texto = r.stdout + r.stderr
    elif linha.startswith(("cat ", "echo ", "mv ")):
        texto, erro = "Claude requested permissions to use Bash, but you haven't granted it yet.", True
    else:
        texto = f"PermissionError: sandbox\nFIM-{nonce}-{i}-1"
    saida.append({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": f"t{n}", "name": "Bash", "input": {"command": linha}}]}})
    saida.append({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": f"t{n}", "content": texto, "is_error": erro}]}})
saida.append({"type": "result", "subtype": "success", "result": "feito"})
print("\n".join(json.dumps(e) for e in saida))
'''


@unittest.skipUnless(LINUX and HOST_INTEGRADO, MOTIVO_HOST)
class TestPontaAPontaComClaudeFalso(Base):
    """preparar → login (fictício) → rodar → limpar pela linha de comando, com o perfil REAL do HOST e um binário
    falso no lugar do Claude Code. Prova o argv e o ambiente do lançador em cada sessão (nada do ambiente do titular
    passa) e o relatório inteiro; o temp-base do teste não é o /tmp do lançador, então o item do temp fica não medido
    e a conclusão, indefinida (código 1), de propósito."""

    def test_rodar_pela_cli_com_o_perfil_do_host(self):
        from test_ensaio_isolamento import copia_do_script, rodar_copia
        alvo = copia_do_script(self.tmp / "skill-copia")
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        claude = bin_dir / "claude"
        claude.write_text(CLAUDE_FALSO, encoding="utf-8", newline="\n")
        claude.chmod(0o755)
        tb = self.temp_base.as_posix()
        r = rodar_copia(alvo, "preparar", "--base", self.base, "--temp-base", tb, env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        config = self.mod.config_do_ensaio(self.base)  # o HOME do teste é a casa descartável (REV3)
        self.assertEqual(json.loads(r.stdout)["config"], config.as_posix())
        (config / ".credentials.json").write_text("{}", encoding="utf-8")
        chave = "ANTHROPIC_" + "API_KEY"
        amb = {**self.env, chave: "valor-ficticio-de-teste", "PATH": "/opt/shim:" + ENV.get("PATH", "")}
        r = subprocess.run([sys.executable, "-B", str(alvo), "rodar", "--base", str(self.base), "--claude",
                            str(claude), "--preparo-host", str(PREPARO_REAL), "--temp-base", tb,
                            "--saida", str(self.tmp / "relatorio.json")], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=amb, timeout=300)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        rel = json.loads((self.tmp / "relatorio.json").read_text(encoding="utf-8"))
        por = {i["id"]: i for i in rel["itens"]}
        for sid in ("leitura_outro_projeto", "leitura_state", "escrita_fora_do_projeto", "rede_fora_da_lista",
                    "fila_porteiro", "skill_agente_aninhado", "plugin_setting_sources_local"):
            self.assertEqual(por[sid]["veredito"], "passou", (sid, por[sid]["motivo"]))
        self.assertIn(por["socket_barramento"]["veredito"], ("passou", "nao_medido"))
        self.assertEqual(por["temp_outro_projeto"]["veredito"], "nao_medido")
        self.assertIn("difere do lançador", por["temp_outro_projeto"]["motivo"])
        self.assertIsNone(rel["conclusao"]["confina_comandos"])
        self.assertIs(rel["perfil"]["gerado"], True)
        self.assertIs(rel["sandbox_ligado"], True)
        self.assertIs(rel["seccomp_presente"], True)
        self.assertEqual(rel["claude"]["versao"], "2.1.302")
        sessoes = [json.loads(x) for x in (bin_dir / "sessoes.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertGreaterEqual(len(sessoes), 11)  # 12 com um barramento no host
        perfil = (self.base / "perfil-ensaio-a.settings.json").as_posix()
        ferramentas = json.loads(Path(perfil).read_text(encoding="utf-8"))["env"]["FUNDACAO_FERRAMENTAS"]
        esperadas = {"HOME", "USER", "LOGNAME", "SHELL", "PATH", "TMPDIR", "CLAUDE_CONFIG_DIR", "FUNDACAO_RAIZ",
                     "FUNDACAO_PROJECT", "FUNDACAO_PORTEIRO", "FUNDACAO_" + "PRINCIPAL"}
        for s in sessoes:
            argv, env = s["argv"], s["env"]
            self.assertEqual(argv[argv.index("--settings") + 1], perfil)
            self.assertEqual(argv[argv.index("--tools") + 1], ferramentas)
            self.assertIn(argv[argv.index("--setting-sources") + 1], ("local", "local,project"))
            self.assertIn("--strict-mcp-config", argv)
            self.assertNotIn(chave, env)
            self.assertEqual(set(env) - {"LANG", "LC_ALL", "LC_CTYPE", "TERM", "COLORTERM", "TZ", "WSL_DISTRO_NAME"},
                             esperadas, sorted(env))
            self.assertEqual(env["PATH"], "/usr/local/bin:/usr/bin:/bin")
            self.assertEqual(env["TMPDIR"], tb + "/fundacao-ia-ensaio-a")
            self.assertEqual(env["CLAUDE_CONFIG_DIR"], config.as_posix())
            self.assertEqual(s["cwd"], str(self.base / "projects" / "ensaio-a"))
        r = rodar_copia(alvo, "limpar", "--base", self.base, "--temp-base", tb, env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        resumo = json.loads(r.stdout)
        self.assertEqual((resumo["sobras"], resumo["restantes"]), ([], []), resumo)
        self.assertFalse(self.base.exists())
        self.assertEqual(list(self.temp_base.iterdir()), [])
        self.assertFalse(config.exists())  # o login fictício sai com a configuração


if __name__ == "__main__":
    unittest.main()
