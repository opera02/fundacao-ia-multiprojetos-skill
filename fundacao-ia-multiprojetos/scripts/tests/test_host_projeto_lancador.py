"""Lançador do projeto no Ubuntu (1.7.10; contratos do lote 2, §4 e §6; folha do HOST, item 4).

O lançador `abrir-fundacao-<p>` (modelo `assets/host/wsl/abrir-sessao.sh`) é gerado pelo `instalar-projeto` e testado
aqui num ensaio completo, sem root: área e lançador em pastas temporárias, um `claude` falso que só registra a chamada
e um porteiro de ensaio (o real é do pacote PORTEIRO). Positivos e negativos de cada recusa: Claude Code, área e hooks
alterados, ficha vencida, trava de manutenção, configurações e `.mcp.json` do projeto, interoperabilidade ligada,
marcadores, temp por projeto, outra sessão do mesmo projeto, outro usuário e o porteiro que recusa; o WSL_DISTRO_NAME no
ambiente do porteiro (emenda E1) e as pastas de trabalho de um porteiro morto por SIGKILL (reconferência do lote 2). Só
no Linux (bash, flock, /usr/bin/python3): no Windows não há onde o lançador rode.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from apoio import SKILL
from test_host_projeto_apoio import (LINUX, carregar_preparo, claude_de_ensaio, ficha_de_ensaio, gravar_ficha_na_caixa,
                                     instalar, instalar_canario, raiz_de_ensaio, relatorio_de_canario, sha,
                                     skill_de_ensaio, usuario_atual)

PODE = LINUX and bool(shutil.which("bash")) and bool(shutil.which("flock")) and Path("/usr/bin/python3").exists()
IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"


@unittest.skipUnless(PODE, "lançador do Ubuntu: só no Linux com bash, flock e /usr/bin/python3")
class Lancador(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="lancador-projeto-1710-")).resolve()
        self.registro_porteiro = self.base / "porteiro-chamadas.jsonl"
        self.skill = skill_de_ensaio(self.base, registro_porteiro=self.registro_porteiro)
        self.raiz = raiz_de_ensaio(self.base, self.skill)
        self.home = self.base / "home"
        self.home.mkdir()
        self.claude = claude_de_ensaio(self.base / "claude-ensaio")
        self.m = carregar_preparo(self.skill)
        self.area = self.base / "area" / "projetos" / "caso-real"
        self.proj = self.raiz / "projects" / "caso-real"
        self.temp = self.base / "tmp" / "fundacao-ia-caso-real"
        self.lancador = self.base / "bin" / "abrir-fundacao-caso-real"
        self.instalar()

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def instalar(self, *extra, sonda_cmd=None):
        r = instalar(self.skill, self.raiz, self.base, "caso-real", self.claude, *extra, sonda_cmd=sonda_cmd)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def abrir(self, **env_extra) -> subprocess.CompletedProcess:
        env = {"HOME": str(self.home), "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", **env_extra}
        return subprocess.run(["bash", str(self.lancador)], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=env, timeout=120)

    def chamada(self) -> dict:
        arquivo = self.home / "chamada-claude.txt"
        if not arquivo.exists():
            return {}
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
        env = dict(l[4:].split("=", 1) for l in linhas if l.startswith("ENV:") and "=" in l)
        return {"args": [l[4:] for l in linhas if l.startswith("ARG:")], "env": env,
                "pwd": next(l[4:] for l in linhas if l.startswith("PWD:")),
                "temp": next(l[12:] for l in linhas if l.startswith("TEMP_EXISTE:")),
                "conteudo": next(l[14:] for l in linhas if l.startswith("TEMP_CONTEUDO:"))}

    def porteiro(self) -> list:
        if not self.registro_porteiro.exists():
            return []
        return [json.loads(l) for l in self.registro_porteiro.read_text(encoding="utf-8").splitlines() if l.strip()]

    def nao_abriu(self, r, trecho: str):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("NÃO foi aberta", r.stderr)
        self.assertIn(trecho, r.stdout + r.stderr)
        self.assertEqual(self.chamada(), {})

    def test_abre_com_a_linha_do_contrato(self):
        r = self.abrir()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        c = self.chamada()
        ferramentas = "Bash,Read,Edit,Write,Glob,Grep,Skill,Agent,TodoWrite"
        self.assertEqual(c["args"][:9], ["--settings", f"{self.area}/settings.wsl.json", "--setting-sources", "local",
                                         "--tools", ferramentas, "--mcp-config", f"{self.area}/mcp.json",
                                         "--strict-mcp-config"])
        self.assertEqual(c["args"][9], "--allow-dangerously-skip-permissions")  # 1.7.11, DECISAO-010 item 1
        self.assertEqual(len(c["args"]), 11)
        self.assertIn("RETOMADA.md", c["args"][10])
        self.assertIn("caso-real", c["args"][10])
        self.assertEqual(c["pwd"], str(self.proj))
        env = c["env"]
        self.assertEqual(env["FUNDACAO_PROJECT"], "caso-real")
        self.assertEqual(env[IDENTIDADE], "sessao-caso-real")
        self.assertEqual(env["FUNDACAO_RAIZ"], str(self.raiz))
        self.assertEqual(env["FUNDACAO_PORTEIRO"], f"{self.proj}/.porteiro")
        self.assertEqual(env["TMPDIR"], str(self.temp))
        self.assertEqual(env["CLAUDE_CONFIG_DIR"], f"{self.home}/.local/share/fundacao-ia/config/caso-real")
        self.assertEqual(env["PATH"], "/usr/local/bin:/usr/bin:/bin")
        self.assertEqual(c["temp"], "700")
        self.assertFalse(self.temp.exists())  # apagado na saída
        perfil = json.loads((self.area / "settings.wsl.json").read_text(encoding="utf-8"))
        self.assertEqual(perfil["env"]["FUNDACAO_FERRAMENTAS"], ferramentas)  # a mesma lista do --tools
        chamadas = self.porteiro()
        self.assertEqual([c["argv"][0] for c in chamadas], ["conferir", "servir"])
        self.assertEqual(chamadas[0]["argv"], ["conferir", "--config", f"{self.area}/porteiro.json"])
        servir = chamadas[1]["argv"]
        self.assertEqual(servir[:5], ["servir", "--config", f"{self.area}/porteiro.json", "--fila", f"{self.proj}/.porteiro"])
        self.assertEqual(servir[5], "--pid-lancador")
        self.assertEqual(chamadas[1]["cwd"], "/")
        self.assertFalse([k for k in chamadas[1]["env"] if k.startswith("FUNDACAO_")])
        for pasta in ("pedidos", "respostas"):
            self.assertTrue((self.proj / ".porteiro" / pasta).is_dir())

    def test_modo_sem_perguntas_disponivel_sem_ligar_e_sem_argumento_livre(self):
        """1.7.11, DECISAO-010 item 1: a opção fixa do lançador deixa o modo disponível (Shift+Tab); nada o liga na
        abertura e nenhum argumento do terminal chega ao Claude Code."""
        self.assertEqual(self.abrir().returncode, 0)
        fixo = self.chamada()["args"]
        self.assertEqual(fixo.count("--allow-dangerously-skip-permissions"), 1)
        for ligado in ("--dangerously-skip-permissions", "--permission-mode", "bypassPermissions"):
            self.assertNotIn(ligado, fixo)
        self.home.joinpath("chamada-claude.txt").unlink()
        env = {"HOME": str(self.home), "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"}
        r = subprocess.run(["bash", str(self.lancador), "--dangerously-skip-permissions", "--permission-mode",
                            "bypassPermissions", "--settings", "/tmp/outro.json", "--tools", "Bash,WebFetch"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.chamada()["args"], fixo)  # os argumentos do terminal não passaram
        perfil = (self.area / "settings.wsl.json").read_text(encoding="utf-8")
        self.assertNotIn("bypassPermissions", perfil)  # o perfil não liga o modo (nem defaultMode)
        self.assertNotIn("defaultMode", perfil)

    def escrever_projeto_json(self, dados):
        (self.proj / "projeto.json").write_text(json.dumps(dados), encoding="utf-8")

    def test_regras_de_codigo_so_com_o_campo_de_lista_fechada(self):
        """1.7.11, ponytail P7: ausente, nada é exportado (nem o que vier do terminal); `enxuto` vira
        FUNDACAO_REGRAS_CODIGO; qualquer outro valor, ou o campo mal formado, a sessão não abre."""
        self.assertEqual(self.abrir(FUNDACAO_REGRAS_CODIGO="enxuto").returncode, 0)
        self.assertNotIn("FUNDACAO_REGRAS_CODIGO", self.chamada()["env"])
        self.home.joinpath("chamada-claude.txt").unlink()
        self.escrever_projeto_json({"project_id": "caso-real", "notes": "sem o campo"})
        self.assertEqual(self.abrir().returncode, 0)
        self.assertNotIn("FUNDACAO_REGRAS_CODIGO", self.chamada()["env"])
        self.home.joinpath("chamada-claude.txt").unlink()
        self.escrever_projeto_json({"project_id": "caso-real", "regras_codigo": "enxuto"})
        self.assertEqual(self.abrir().returncode, 0)
        self.assertEqual(self.chamada()["env"].get("FUNDACAO_REGRAS_CODIGO"), "enxuto")
        for valor in ("lite", "ultra", "Enxuto", "enxuto ", "", ["enxuto"], 1, None, True):
            with self.subTest(valor=valor):
                self.home.joinpath("chamada-claude.txt").unlink(missing_ok=True)
                self.escrever_projeto_json({"project_id": "caso-real", "regras_codigo": valor})
                self.nao_abriu(self.abrir(), "regras_codigo")

    def test_ambiente_herdado_nao_passa(self):
        r = self.abrir(FUNDACAO_PERMITIR_TROCA_IDENTIDADE="1", FUNDACAO_PROJECT="lab-a", LD_PRELOAD="/x.so",
                       PYTHONPATH="/y", NODE_OPTIONS="--require /z.js", ANTHROPIC_BASE_URL="http://exemplo.invalid",
                       SSH_AUTH_SOCK="/tmp/agente", **{IDENTIDADE: "titular"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        env = self.chamada()["env"]
        for chave in ("FUNDACAO_PERMITIR_TROCA_IDENTIDADE", "LD_PRELOAD", "PYTHONPATH", "NODE_OPTIONS",
                      "ANTHROPIC_BASE_URL", "SSH_AUTH_SOCK"):
            self.assertNotIn(chave, env)
        self.assertEqual(env["FUNDACAO_PROJECT"], "caso-real")
        self.assertEqual(env[IDENTIDADE], "sessao-caso-real")

    def test_claude_trocado_nao_abre(self):
        copia = self.base / "area" / "claude" / "2.1.302" / "claude"
        copia.write_bytes(copia.read_bytes() + b"# outro\n")
        self.nao_abriu(self.abrir(), "mudou")

    def test_area_ou_hook_alterado_nao_abre(self):
        for arquivo in (self.area / "settings.wsl.json", self.area / "porteiro.json", self.area / "mcp.json",
                        self.raiz / ".claude" / "hooks" / "guarda_caminho.py",
                        self.raiz / ".claude" / "hooks" / "guarda_ferramentas.py"):
            with self.subTest(arquivo=arquivo.name):
                original = arquivo.read_bytes()
                arquivo.write_bytes(original + b"\n")
                r = self.abrir()
                arquivo.write_bytes(original)
                self.nao_abriu(r, "mudou desde o preparo")
        self.assertEqual(self.abrir().returncode, 0)

    def aprovar_canario(self):
        """O titular rodou o ensaio real e instalou o relatório aprovado (contratos, §0: sem ele, nenhuma ficha vale)."""
        r = instalar_canario(self.skill, self.base, relatorio_de_canario(self.m, self.raiz, self.claude))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_ficha_vencida_nao_abre(self):
        self.aprovar_canario()  # 1.7.10 (contratos, §0): a ficha (e a vigência que o lançador relê) só vale com ele
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio(
            "caso-real", 1, vigencia_ate=(date.today() + timedelta(days=30)).isoformat()))
        self.instalar()
        self.assertEqual(self.abrir().returncode, 0)
        ficha = self.area / "ficha" / "ficha-v1.json"  # o tempo passou: a vigência ficou para trás
        dados = json.loads(ficha.read_text(encoding="utf-8"))
        dados["vigencia_ate"] = (date.today() - timedelta(days=1)).isoformat()
        ficha.write_text(json.dumps(dados), encoding="utf-8")
        hashes = json.loads((self.area / "hashes.json").read_text(encoding="utf-8"))
        hashes["arquivos"][ficha.as_posix()] = sha(ficha)
        (self.area / "hashes.json").write_text(json.dumps(hashes), encoding="utf-8")  # na área root, só o preparo
        self.home.joinpath("chamada-claude.txt").unlink(missing_ok=True)
        self.nao_abriu(self.abrir(), "venceu")

    def instalar_com_mcp(self, item):
        self.aprovar_canario()
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 1, mcp=[item]))
        self.instalar()

    def test_mcp_por_url_vai_ao_mcp_json_com_strict_e_esconde_o_que_a_ficha_manda(self):
        """1.7.11, lote L2: origem url: o servidor da ficha no mcp.json, --strict-mcp-config e --disallowedTools."""
        self.instalar_com_mcp({"nome": "fsn", "origem": "url", "url": "https://mcp.exemplo.org/escritorio",
                               "ferramentas": ["buscar_clientes", "get_processo"], "ocultar": ["escanear_vault"],
                               "conteudo_de_terceiros": True})
        self.assertEqual(json.loads((self.area / "mcp.json").read_text(encoding="utf-8")),
                         {"mcpServers": {"fsn": {"type": "http", "url": "https://mcp.exemplo.org/escritorio"}}})
        r = self.abrir()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = self.chamada()["args"]
        self.assertEqual(args[args.index("--disallowedTools") + 1], "mcp__fsn__escanear_vault")
        self.assertEqual(args[args.index("--mcp-config") + 2], "--strict-mcp-config")
        self.assertLess(args.index("--disallowedTools"), args.index("--allow-dangerously-skip-permissions"))
        self.assertTrue(args[-1].startswith("Sessão do projeto"))  # a opção variádica não engoliu o prompt
        env = json.loads((self.area / "settings.wsl.json").read_text(encoding="utf-8"))["env"]
        self.assertEqual(env["FUNDACAO_MCP_FERRAMENTAS"], "mcp__fsn__buscar_clientes,mcp__fsn__get_processo")

    def test_mcp_pela_conta_abre_sem_strict_e_recusa_servidor_proprio_no_claude_json(self):
        self.instalar_com_mcp({"nome": "fsn", "origem": "conta", "conector": "Conector do escritorio",
                               "ferramentas": ["buscar_clientes"], "ocultar": [], "conteudo_de_terceiros": True})
        self.assertEqual(json.loads((self.area / "mcp.json").read_text(encoding="utf-8")), {"mcpServers": {}})
        r = self.abrir()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = self.chamada()["args"]
        self.assertNotIn("--strict-mcp-config", args)
        self.assertNotIn("--disallowedTools", args)  # nada escondido: a ficha não tem `ocultar`
        self.assertEqual(args[args.index("--mcp-config") + 1], f"{self.area}/mcp.json")
        self.home.joinpath("chamada-claude.txt").unlink()
        config = self.home / ".local" / "share" / "fundacao-ia" / "config" / "caso-real"
        config.mkdir(parents=True, exist_ok=True)
        (config / ".claude.json").write_text(json.dumps({"mcpServers": {"x": {"command": "x"}}}), encoding="utf-8")
        self.nao_abriu(self.abrir(), "servidores MCP próprios")

    def test_sem_a_secao_mcp_nada_e_escondido_e_o_strict_fica(self):
        self.assertEqual(self.abrir().returncode, 0)
        args = self.chamada()["args"]
        self.assertNotIn("--disallowedTools", args)
        self.assertIn("--strict-mcp-config", args)

    def test_trava_de_manutencao_nao_abre(self):
        (self.raiz / "state").mkdir()
        (self.raiz / "state" / "manutencao.json").write_text("{}", encoding="utf-8")
        self.nao_abriu(self.abrir(), "manutenção")

    def test_configuracoes_do_projeto(self):
        pasta = self.proj / ".claude"
        pasta.mkdir()
        (pasta / "settings.local.json").write_text(json.dumps({"permissions": {"allow": ["Bash(npm test:*)"]}}),
                                                   encoding="utf-8")
        self.assertEqual(self.abrir().returncode, 0)
        self.home.joinpath("chamada-claude.txt").unlink()
        (pasta / "settings.local.json").write_text(json.dumps({"permissions": {"allow": ["mcp__x__y"]}}),
                                                   encoding="utf-8")
        r = self.abrir()
        self.nao_abriu(r, "Para arquivar: mkdir -p")

    def test_mcp_do_projeto_nao_abre(self):
        (self.proj / ".mcp.json").write_text('{"mcpServers": {"x": {"command": "x"}}}', encoding="utf-8")
        self.nao_abriu(self.abrir(), ".mcp.json")

    def test_mcp_json_acima_do_projeto_nao_abre(self):
        """F4 da revisão da 1.7.11: o .mcp.json da raiz ou de uma pasta acima dela não deixa o lançador abrir; tirado,
        abre."""
        for pasta in (self.raiz, self.raiz / "projects", self.base):
            with self.subTest(pasta=pasta.name):
                arquivo = pasta / ".mcp.json"
                arquivo.write_text('{"mcpServers": {"x": {"command": "x"}}}', encoding="utf-8")
                r = self.abrir()
                arquivo.unlink()
                self.nao_abriu(r, arquivo.as_posix())
        self.assertEqual(self.abrir().returncode, 0)

    def test_interop_ligada_nao_abre(self):
        falso = self.base / "interop" / "cmd.exe"
        falso.parent.mkdir()
        falso.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        falso.chmod(0o755)
        self.instalar(sonda_cmd=falso)
        self.nao_abriu(self.abrir(), "interoperabilidade")

    def test_interop_registrada_no_binfmt_nao_abre(self):
        """A segunda sonda: o WSLInterop registrado em binfmt_misc (habilitado) roda .exe do Windows mesmo sem o
        cmd.exe à vista. Desabilitado, abre."""
        binfmt = self.base / "sem-interop" / "binfmt"
        binfmt.mkdir(parents=True)
        (binfmt / "WSLInterop").write_text("disabled\ninterpreter /init\nflags: PF\n", encoding="utf-8")
        self.assertEqual(self.abrir().returncode, 0)
        self.home.joinpath("chamada-claude.txt").unlink()
        (binfmt / "WSLInterop-late").write_text("enabled\ninterpreter /init\nflags: PF\n", encoding="utf-8")
        self.nao_abriu(self.abrir(), "registrada")

    def test_plugin_da_ficha_entra_pelo_plugin_dir(self):
        """O --plugin-dir efetivo na linha do claude (não só o texto PLUGINS do lançador), com o canário aprovado."""
        self.aprovar_canario()
        pasta = self.proj / "plugins-candidatos" / "caso-real-revisor"
        (pasta / ".claude-plugin").mkdir(parents=True)
        (pasta / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "caso-real-revisor"}),
                                                               encoding="utf-8")
        (pasta / "agents").mkdir()
        (pasta / "agents" / "leitor.md").write_text("---\nname: leitor\n---\nlê\n", encoding="utf-8")
        manifesto = self.m.manifesto_de_arvore(pasta, pastas_ignoradas=(), sufixos_ignorados=())
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 1, plugins=[
            {"nome": "caso-real-revisor", "origem": "plugins-candidatos/caso-real-revisor",
             "manifesto_sha256": self.m.sha256_do_plugin(manifesto)}]))
        self.instalar()
        r = self.abrir()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = self.chamada()["args"]
        i = args.index("--plugin-dir")
        self.assertEqual(args[i + 1], f"{self.area}/plugins/caso-real-revisor")
        self.assertEqual(args.count("--plugin-dir"), 1)
        self.assertLess(i, args.index("--mcp-config"))
        self.assertTrue((self.area / "plugins" / "caso-real-revisor" / "agents" / "leitor.md").is_file())

    def test_casa_com_ligacao_no_caminho_da_configuracao_nao_abre(self):
        """Revisão do lote 2: ~/.local, ~/.local/share ou a pasta da fundação como ligação levariam a configuração
        (transcrições, credencial) e a trava para onde outra sessão grava."""
        outra = self.base / "de-outra-sessao"
        outra.mkdir()
        for rel in (".local", ".local/share", ".local/share/fundacao-ia", ".local/share/fundacao-ia/config",
                    ".fundacao"):
            with self.subTest(rel):
                alvo = self.home / rel
                alvo.parent.mkdir(parents=True, exist_ok=True)
                if alvo.is_dir() and not alvo.is_symlink():
                    shutil.rmtree(alvo)
                alvo.symlink_to(outra, target_is_directory=True)
                r = self.abrir()
                alvo.unlink()
                self.nao_abriu(r, "ligação")
        self.assertEqual(self.abrir().returncode, 0)
        self.assertEqual(list(outra.iterdir()), [])  # nada foi parar na pasta da ligação

    def test_prompt_manda_ler_a_skill_pelo_bash(self):
        self.assertEqual(self.abrir().returncode, 0)
        prompt = self.chamada()["args"][-1]
        hashes = json.loads((self.area / "hashes.json").read_text(encoding="utf-8"))
        self.assertIn("cat '" + hashes["arvores"]["skill"]["caminho"] + "/SKILL.md'", prompt)
        self.assertIn("ferramenta Read só alcança a pasta do projeto", prompt)

    def test_marcadores_limpos_antes_e_depois(self):
        (self.proj / ".bashrc").write_bytes(b"")
        (self.home / "criar-marcador").write_text("1", encoding="utf-8")  # o claude falso deixa um .gitmodules vazio
        r = self.abrir()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.proj / ".bashrc").exists())
        self.assertFalse((self.proj / ".gitmodules").exists())
        (self.proj / ".bashrc").write_text("alias x=y\n", encoding="utf-8")
        self.home.joinpath("chamada-claude.txt").unlink()
        self.nao_abriu(self.abrir(), ".bashrc")

    def test_temp_por_projeto_privado_e_recriado(self):
        self.temp.mkdir(parents=True)
        (self.temp / "sobra-de-outra-sessao").write_text("x", encoding="utf-8")
        r = self.abrir()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        c = self.chamada()
        self.assertEqual((c["temp"], c["conteudo"].strip()), ("700", "0"))
        self.assertFalse(self.temp.exists())
        self.temp.symlink_to(self.base)
        self.home.joinpath("chamada-claude.txt").unlink()
        self.nao_abriu(self.abrir(), "ligação")
        self.temp.unlink()

    def test_uma_sessao_por_projeto(self):
        import fcntl
        trava = self.home / ".local" / "share" / "fundacao-ia" / "travas"
        trava.mkdir(parents=True)
        with open(trava / "caso-real.trava", "a", encoding="utf-8") as f:  # outra sessão do mesmo projeto segura a trava
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            self.nao_abriu(self.abrir(), "já há uma sessão deste projeto")
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        self.assertEqual(self.abrir().returncode, 0)

    def test_porteiro_que_recusa_a_configuracao_nao_abre(self):
        Path(str(self.registro_porteiro) + ".conferir").write_text("2", encoding="utf-8")
        self.nao_abriu(self.abrir(), "porteiro recusou")
        self.assertEqual([c["argv"][0] for c in self.porteiro()], ["conferir"])  # não chegou a servir

    def test_nome_da_distribuicao_vai_ao_porteiro_na_forma_aceita(self):
        """Contratos, E1: o lançador passa o WSL_DISTRO_NAME no env -i do porteiro.py servir (o porteiro o repassa ao
        kit só para compor o comando do titular); fora da forma que o porteiro aceita, ou ausente, não passa."""
        for valor, esperado in (("Ubuntu-24.04", "Ubuntu-24.04"), ("Ubuntu;rm -rf x", None), ("x" * 65, None),
                                (None, None)):
            with self.subTest(valor=valor):
                self.registro_porteiro.unlink(missing_ok=True)
                self.home.joinpath("chamada-claude.txt").unlink(missing_ok=True)
                r = self.abrir(**({} if valor is None else {"WSL_DISTRO_NAME": valor}))
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                servir = [c for c in self.porteiro() if c["argv"][0] == "servir"]
                self.assertEqual(len(servir), 1, self.porteiro())
                self.assertEqual(servir[0]["distro"], esperado)
                self.assertEqual("WSL_DISTRO_NAME" in servir[0]["env"], esperado is not None)
                self.assertFalse([k for k in servir[0]["env"] if k.startswith("FUNDACAO_")])

    def test_pastas_de_trabalho_de_porteiro_morto_saem_ao_abrir(self):
        """Orientação do coordenador (reconferência do lote 2): o porteiro morto por SIGKILL deixa
        ~/.fundacao/porteiro/<p>/trabalho-* (com a cópia privada do kit). Com a trava na mão e sem porteiro deste
        projeto de pé, o lançador as apaga antes de iniciar o porteiro, sem seguir ligação; as de outro projeto, o
        registro e o destino das ligações ficam."""
        fora = self.base / "fora-da-casa"
        fora.mkdir()
        (fora / "importante.txt").write_text("fica\n", encoding="utf-8")
        pasta = self.home / ".fundacao" / "porteiro" / "caso-real"
        sobra = pasta / "trabalho-abcd1234"
        (sobra / "kit-x1y2z3w4" / "fundacao").mkdir(parents=True)
        (sobra / "kit-x1y2z3w4" / "fundacao" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
        (sobra / "ligada").symlink_to(fora, target_is_directory=True)
        (pasta / "registro.jsonl").write_text("{}\n", encoding="utf-8")
        de_outro = self.home / ".fundacao" / "porteiro" / "lab-a" / "trabalho-efgh5678"
        de_outro.mkdir(parents=True)
        r = self.abrir()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("trabalho-abcd1234", r.stdout)
        self.assertFalse(os.path.lexists(sobra))
        self.assertTrue(de_outro.is_dir())
        self.assertTrue((pasta / "registro.jsonl").is_file())
        self.assertEqual((fora / "importante.txt").read_text(encoding="utf-8"), "fica\n")
        self.assertEqual([c["argv"][0] for c in self.porteiro()], ["conferir", "servir"])  # e a sessão abriu

    def test_com_porteiro_do_projeto_de_pe_as_pastas_de_trabalho_ficam(self):
        """Um porteiro deste projeto de pé (aqui, um processo com a linha de comando dele) segura a limpeza, na
        abertura e na saída: a sessão abre, e o lançador avisa que as manteve."""
        sobra = self.home / ".fundacao" / "porteiro" / "caso-real" / "trabalho-abcd1234"
        sobra.mkdir(parents=True)
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", "/x/assets/host/wsl/porteiro.py",
                              "servir", "--fila", f"{self.proj}/.porteiro"], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            r = self.abrir()
        finally:
            p.kill()
            p.wait(timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(sobra.is_dir())
        self.assertIn("mantidas", r.stdout)
        self.assertIn(f"pid {p.pid}", r.stdout)

    def test_lancador_de_outro_usuario_nao_abre(self):
        self.instalar("--usuario", "outro-usuario" if usuario_atual() != "outro-usuario" else "mais-um")
        self.nao_abriu(self.abrir(), "este lançador é do usuário")

    def test_modelo_e_gerado_sao_bash_valido_com_lf(self):
        modelo = SKILL / "assets" / "host" / "wsl" / "abrir-sessao.sh"
        for arquivo in (modelo, self.lancador):
            with self.subTest(arquivo=arquivo.name):
                self.assertNotIn(b"\r", arquivo.read_bytes())
                r = subprocess.run(["bash", "-n", str(arquivo)], capture_output=True, text=True, timeout=60)
                self.assertEqual(r.returncode, 0, r.stderr)


def linhas_de_codigo(texto: str) -> list[str]:
    """As linhas do bash que não são comentário (o modelo cita as decisões em comentários)."""
    return [l.strip() for l in texto.splitlines() if l.strip() and not l.lstrip().startswith("#")]


class ModeloDoLancador(unittest.TestCase):
    """O que dá para conferir no modelo em qualquer sistema."""

    VALORES = {"RAIZ": "/mnt/e/Raiz", "PROJETO": "caso-real", "USUARIO": "titular",
               "AREA": "/etc/fundacao-ia/projetos/caso-real", "SKILL": "/etc/fundacao-ia/skill/1.7.11-abc",
               "CLAUDE_BIN": "/etc/fundacao-ia/claude/2.1.302/claude", "CLAUDE_VERSAO": "2.1.302",
               "CLAUDE_SHA256": "1" * 64, "CLAUDE_ORIGEM_HASH": "manifesto assinado", "FERRAMENTAS": "Bash,Read",
               "PLUGINS": "", "PREPARO_SHA256": "2" * 64, "PORTEIRO_SHA256": "3" * 64,
               "TEMP_PROJETO": "/tmp/fundacao-ia-caso-real", "SONDA_INTEROP_CMD": "/mnt/c/Windows/System32/cmd.exe",
               "SONDA_INTEROP_BINFMT": "/proc/sys/fs/binfmt_misc"}

    def test_modo_sem_perguntas_esta_no_lancador_de_todos_os_projetos(self):
        """1.7.11, DECISAO-010 item 1: o modelo traz a opção fixa, uma vez, depois das demais; cada lançador gerado a
        herda, qualquer que seja o projeto."""
        m = carregar_preparo()
        modelo = (SKILL / "assets" / "host" / "wsl" / "abrir-sessao.sh").read_text(encoding="utf-8")
        fixas = 'ARGS+=(--mcp-config "$AREA/mcp.json" --strict-mcp-config)'
        for projeto in ("caso-real", "estudio-de-video", "criador-de-peticoes", "a"):
            with self.subTest(projeto=projeto):
                codigo = linhas_de_codigo(m.lancador({**self.VALORES, "PROJETO": projeto}, modelo))
                opcoes = [l for l in codigo if "--allow-dangerously-skip-permissions" in l]
                self.assertEqual(opcoes, ["ARGS+=(--allow-dangerously-skip-permissions)"])
                self.assertGreater(codigo.index(opcoes[0]), codigo.index(fixas))
                for ligada in ("--dangerously-skip-permissions", "--permission-mode", "bypassPermissions"):
                    self.assertFalse([l for l in codigo if ligada in l], ligada)

    def test_mcp_no_modelo_do_lancador(self):
        """1.7.11, lote L2: o --strict-mcp-config só sai na origem conta (MCP_ESTRITO=0) e o --disallowedTools só com o que
        esconder; os dois antes da opção do modo sem perguntas, para o prompt (último) não ser engolido."""
        codigo = linhas_de_codigo((SKILL / "assets" / "host" / "wsl" / "abrir-sessao.sh").read_text(encoding="utf-8"))
        self.assertEqual([l for l in codigo if "--disallowedTools" in l], ['ARGS+=(--disallowedTools "$MCP_OCULTAR")'])
        self.assertEqual([l for l in codigo if l.startswith("ARGS+=(--mcp-config")],
                         ['ARGS+=(--mcp-config "$AREA/mcp.json" --strict-mcp-config)',
                          'ARGS+=(--mcp-config "$AREA/mcp.json")'])
        ordem = [codigo.index('ARGS+=(--disallowedTools "$MCP_OCULTAR")'),
                 codigo.index('ARGS+=(--mcp-config "$AREA/mcp.json" --strict-mcp-config)'),
                 codigo.index("ARGS+=(--allow-dangerously-skip-permissions)")]
        self.assertEqual(ordem, sorted(ordem))
        m = carregar_preparo()
        for chave in ("MCP_ESTRITO", "MCP_OCULTAR"):
            self.assertIn(chave, m.CHAVES_DO_LANCADOR)
        self.assertIn("MCP_ESTRITO='1'", m.lancador(self.VALORES))  # sem os valores novos: estrito e nada escondido
        self.assertIn("MCP_OCULTAR=''", m.lancador(self.VALORES))

    def test_nenhum_argumento_livre_chega_ao_claude_code(self):
        """O lançador não repassa o que se digita depois do nome dele: nenhum uso de $@ ou $* fora de comentário (o $1
        das funções é argumento interno), nem shift ou getopts, e a chamada do Claude Code leva só a lista fixa e o
        prompt."""
        codigo = linhas_de_codigo((SKILL / "assets" / "host" / "wsl" / "abrir-sessao.sh").read_text(encoding="utf-8"))
        for ruim in ('"$@"', "$@", "${@", "$*", "${*", "shift", "getopts"):
            self.assertFalse([l for l in codigo if ruim in l], ruim)
        chamadas = [l for l in codigo if "$CLAUDE_BIN" in l and "env -i" in l]
        self.assertEqual(chamadas, ['env -i "${AMBIENTE[@]}" "$CLAUDE_BIN" "${ARGS[@]}" "$PROMPT"'])

    def test_regras_de_codigo_do_projeto_json_lista_fechada(self):
        """1.7.11, ponytail P7: o campo `regras_codigo` do projeto.json (lido sem seguir ligação, até 64 KiB) só vale
        com `enxuto`; sem o campo ou sem o arquivo, desligado; arquivo ilegível, desligado com aviso; outro valor,
        EntradaInvalida."""
        m = carregar_preparo()
        base = Path(tempfile.mkdtemp(prefix="regras-codigo-lancador-")).resolve()
        try:
            pasta = base / "projects" / "caso-real"
            pasta.mkdir(parents=True)
            self.assertEqual(m.regras_de_codigo_do_projeto(base, "caso-real"), ("", []))  # sem arquivo
            arquivo = pasta / "projeto.json"
            for texto, esperado in (('{"project_id": "caso-real"}', ""), ('{"regras_codigo": "enxuto"}', "enxuto"),
                                    ('\ufeff{"regras_codigo": "enxuto"}', "enxuto"), ("[]", "")):
                with self.subTest(texto=texto):
                    arquivo.write_text(texto, encoding="utf-8")
                    self.assertEqual(m.regras_de_codigo_do_projeto(base, "caso-real"), (esperado, []))
            for ruim in ('"lite"', '"ultra"', '"Enxuto"', '"enxuto "', '""', '["enxuto"]', "1", "null", "true"):
                with self.subTest(valor=ruim):
                    arquivo.write_text('{"regras_codigo": ' + ruim + "}", encoding="utf-8")
                    with self.assertRaises(m.EntradaInvalida) as ctx:
                        m.regras_de_codigo_do_projeto(base, "caso-real")
                    self.assertIn("lista fechada", str(ctx.exception))
            for ilegivel in (b"nao e json", b"\xff\xfe\x00", b"x" * (64 * 1024 + 1)):
                with self.subTest(ilegivel=ilegivel[:10]):
                    arquivo.write_bytes(ilegivel)
                    valor, avisos = m.regras_de_codigo_do_projeto(base, "caso-real")
                    self.assertEqual(valor, "")
                    self.assertEqual(len(avisos), 1)
                    self.assertIn("desligadas", avisos[0])
            with self.assertRaises(ValueError):
                m.regras_de_codigo_do_projeto(base, "../x")
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_regras_de_codigo_pela_linha_de_comando_do_ajudante(self):
        """O que o lançador chama: o valor sozinho no stdout (vazio, sem campo), código 2 e JSON de erro fora da lista."""
        base = Path(tempfile.mkdtemp(prefix="regras-codigo-cli-")).resolve()
        try:
            pasta = base / "projects" / "caso-real"
            pasta.mkdir(parents=True)

            def rodar():
                return subprocess.run([sys.executable, "-I", "-B", str(SKILL / "assets" / "host" / "preparo_host.py"),
                                       "regras-codigo", "--raiz", str(base), "--projeto", "caso-real"],
                                      capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
            r = rodar()
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "\n", ""))
            (pasta / "projeto.json").write_text('{"regras_codigo": "enxuto"}', encoding="utf-8")
            r = rodar()
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "enxuto\n", ""))
            (pasta / "projeto.json").write_text('{"regras_codigo": "ultra"}', encoding="utf-8")
            r = rodar()
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("lista fechada", json.loads(r.stdout)["erro"])
            (pasta / "projeto.json").write_text("{", encoding="utf-8")
            r = rodar()
            self.assertEqual((r.returncode, r.stdout.strip()), (0, ""))
            self.assertIn("aviso:", r.stderr)
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_valores_sao_conferidos_e_aspas_escapadas(self):
        m = carregar_preparo()
        valores = {"RAIZ": "/mnt/e/Raiz D'Ávila", "PROJETO": "caso-real", "USUARIO": "titular",
                   "AREA": "/etc/fundacao-ia/projetos/caso-real", "SKILL": "/etc/fundacao-ia/skill/1.7.10-abc",
                   "CLAUDE_BIN": "/etc/fundacao-ia/claude/2.1.302/claude", "CLAUDE_VERSAO": "2.1.302",
                   "CLAUDE_SHA256": "1" * 64, "CLAUDE_ORIGEM_HASH": "manifesto assinado",
                   "FERRAMENTAS": "Bash,Read", "PLUGINS": "", "PREPARO_SHA256": "2" * 64, "PORTEIRO_SHA256": "3" * 64,
                   "TEMP_PROJETO": "/tmp/fundacao-ia-caso-real", "SONDA_INTEROP_CMD": "/mnt/c/Windows/System32/cmd.exe",
                   "SONDA_INTEROP_BINFMT": "/proc/sys/fs/binfmt_misc"}
        texto = m.lancador(valores)
        self.assertTrue(texto.startswith("#!/usr/bin/env bash\n"))
        self.assertNotIn("{{", texto)
        self.assertIn("'/mnt/e/Raiz D'" + chr(92) + "''Ávila'", texto)
        for chave, ruim in (("CLAUDE_SHA256", "abc"), ("PROJETO", "../x"), ("AREA", "relativa"),
                            ("USUARIO", "Usuario Com Espaco"), ("FERRAMENTAS", "Bash;rm"), ("PLUGINS", "../x"),
                            ("CLAUDE_VERSAO", "2.1"), ("RAIZ", "/x\ny")):
            with self.subTest(chave=chave), self.assertRaises(ValueError):
                m.lancador({**valores, chave: ruim})
        with self.assertRaises(ValueError):
            m.lancador({k: v for k, v in valores.items() if k != "PORTEIRO_SHA256"})


if __name__ == "__main__":
    unittest.main()
