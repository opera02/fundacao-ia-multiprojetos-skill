"""Lado do WSL do preparo do host: o lançador `assets/host/wsl/abrir-sessao.sh` (Claude Code fixado por hash,
perfil e hooks conferidos, prompt de retomada) e o `assets/host/wsl/preparar-wsl.sh`.

1.7.10: o lançador é por projeto (`abrir-fundacao-<p>`, na área do titular de dono root, gerado pelo
`preparo_host.py instalar-projeto`) e usa flock, /usr/bin/python3 e o porteiro: os testes rodam só no Linux, num
ensaio completo sem root (área e lançador em pastas temporárias, com a cópia de ensaio da skill do
`test_host_projeto_apoio`). No Windows ficam pulados com o motivo: o `bash.exe` da System32 abriria a distribuição do
WSL, e a fundação não pode ter o banco aberto pelos dois lados ao mesmo tempo. O `claude` é um script falso que só
registra como foi chamado. As recusas novas do lançador estão em `test_host_projeto_lancador.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import ENV, SKILL
from test_host_projeto_apoio import (LINUX, carregar_preparo, claude_de_ensaio, instalar, raiz_de_ensaio,
                                     skill_de_ensaio, usuario_atual)

HOST = SKILL / "assets" / "host"
LANCADOR = HOST / "wsl" / "abrir-sessao.sh"
PREPARAR = HOST / "wsl" / "preparar-wsl.sh"
BASH = shutil.which("bash") if LINUX else None
PODE = bool(BASH) and bool(shutil.which("flock")) and Path("/usr/bin/python3").exists()
IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"


def sha(caminho: Path) -> str:
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def rodar_bash(script: Path, *args, env_extra: dict | None = None, cwd: Path | None = None):
    env = {k: v for k, v in ENV.items() if not k.startswith("FUNDACAO_")}
    env.update(env_extra or {})
    return subprocess.run([BASH, str(script), *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, timeout=300, cwd=str(cwd) if cwd else None)


def montar_raiz(base: Path, projeto: str = "caso-real"):
    """Raiz de ensaio como o preparo do Windows a deixa (hooks e kit iguais aos da skill de ensaio)."""
    skill = skill_de_ensaio(base)
    return skill, raiz_de_ensaio(base, skill, projeto, outros=("lab-a",))


@unittest.skipUnless(PODE, "1.7.10: o lançador do projeto roda no Linux (bash, flock e /usr/bin/python3)")
class LancadorNoBash(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="lancador-bash-teste-")).resolve()  # nome longo (TEMP curto no GitHub)
        self.skill, self.raiz = montar_raiz(self.base)
        self.home = self.base / "home"
        self.home.mkdir()
        self.claude = claude_de_ensaio(self.base / "bin-claude")
        self.area = self.base / "area" / "projetos" / "caso-real"
        self.lancador = self.base / "bin" / "abrir-fundacao-caso-real"
        self.gerar_lancador()

    def gerar_lancador(self, *extra):
        """O que o preparar-wsl.sh fixa: a área do titular com o perfil e os hashes, e o lançador do projeto."""
        r = instalar(self.skill, self.raiz, self.base, "caso-real", self.claude, *extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def abrir(self, **env):
        return rodar_bash(self.lancador, env_extra={"HOME": str(self.home), "PATH": "/usr/bin:/bin", **env})

    def chamada(self) -> list:
        arquivo = self.home / "chamada-claude.txt"
        return arquivo.read_text(encoding="utf-8").splitlines() if arquivo.exists() else []

    def test_abre_com_o_perfil_fixado_o_projeto_e_o_prompt_de_retomada(self):
        r = self.abrir()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        linhas = self.chamada()
        args = [l[4:] for l in linhas if l.startswith("ARG:")]
        self.assertEqual(args[:4], ["--settings", str(self.area / "settings.wsl.json"), "--setting-sources", "local"])
        self.assertEqual(len(args), 10)
        self.assertIn("RETOMADA.md", args[9])
        self.assertIn("caso-real", args[9])
        self.assertIn("ENV:FUNDACAO_PROJECT=caso-real", linhas)
        self.assertIn("PWD:" + str(self.raiz / "projects" / "caso-real"), linhas)  # 1.7.10: a pasta do projeto

    def test_claude_trocado_nao_abre(self):
        copia = self.base / "area" / "claude" / "2.1.302" / "claude"
        with open(copia, "a", encoding="utf-8", newline="\n") as f:
            f.write("# outro binário\n")
        r = self.abrir()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("mudou", r.stderr)
        self.assertEqual(self.chamada(), [])

    def test_perfil_ou_hook_alterado_nao_abre(self):
        for arquivo in (self.area / "settings.wsl.json",
                        self.raiz / ".claude" / "hooks" / "guarda_caminho.py",
                        self.raiz / ".claude" / "hooks" / "guarda_identidade.py",
                        self.raiz / ".claude" / "hooks" / "sinais_sessao.py"):
            with self.subTest(arquivo=arquivo.name):
                original = arquivo.read_bytes()
                arquivo.write_bytes(original + b"\n")
                r = self.abrir()
                arquivo.write_bytes(original)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("mudou", r.stdout + r.stderr)
                self.assertEqual(self.chamada(), [])

    def test_sem_a_identidade_do_titular_nao_abre(self):
        """1.7.10: a identidade da sessão (sessao-<p>) e o resto vêm da área do titular; sem o hashes.json dela, o
        lançador não tem o que conferir e não abre."""
        (self.area / "hashes.json").unlink()
        r = self.abrir()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("hashes.json", r.stdout + r.stderr)
        self.assertEqual(self.chamada(), [])

    def test_projeto_do_settings_local_da_raiz_nao_troca_o_projeto_do_lancador(self):
        """Revisão de segurança da 1.7.0 (pendência): com dois projetos entregues, qual vale dependeria da precedência
        do host. Na 1.7.10 a sessão abre na pasta do projeto e não carrega o settings.local.json da raiz: o projeto é
        sempre o do lançador, e o local da raiz com outro projeto não muda nada (a sessão abre, no projeto do
        lançador; o nome antigo, "..._nao_abre", era da 1.7.9 e foi trocado na revisão do lote 2)."""
        local = self.raiz / ".claude" / "settings.local.json"
        local.write_text(json.dumps({"env": {IDENTIDADE: "titular", "FUNDACAO_PROJECT": "outro-projeto"}}),
                         encoding="utf-8")
        r = self.abrir()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ENV:FUNDACAO_PROJECT=caso-real", self.chamada())

    def test_settings_local_alterado_depois_do_preparo_nao_abre(self):
        """Auditoria Codex Security da 1.7.6, #5: o settings.local.json que a sessão carrega (na 1.7.10, o da pasta do
        projeto) só vale com permissions.allow no formato aceito; outra identidade, a troca de identidade liberada ou
        um hook acrescentado: a sessão não abre."""
        pasta = self.raiz / "projects" / "caso-real" / ".claude"
        pasta.mkdir()
        local = pasta / "settings.local.json"
        casos = {"outra identidade": {"env": {IDENTIDADE: "outra-pessoa"}},
                 "troca liberada": {"env": {"FUNDACAO_PERMITIR_TROCA_IDENTIDADE": "1"}},
                 "hook": {"permissions": {"allow": []},
                          "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
                                                                                   "command": "/tmp/x"}]}]}}}
        for nome, dados in casos.items():
            with self.subTest(nome):
                local.write_text(json.dumps(dados), encoding="utf-8", newline="\n")
                r = self.abrir()
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("settings.local.json", r.stdout + r.stderr)
                self.assertEqual(self.chamada(), [])
        local.write_text(json.dumps({"permissions": {"allow": ["Bash(npm test:*)"]}}), encoding="utf-8")
        self.assertEqual(self.abrir().returncode, 0)

    def test_identidade_diferente_da_fixada_no_lancador_nao_abre(self):
        """O lançador fixa o usuário do Linux dono da configuração e da trava: o de outro usuário não abre."""
        self.gerar_lancador("--usuario", "outra-pessoa" if usuario_atual() != "outra-pessoa" else "mais-uma")
        r = self.abrir()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("usuário", r.stderr)
        self.assertEqual(self.chamada(), [])

    def test_variaveis_da_fundacao_do_terminal_nao_passam_para_a_sessao(self):
        """O projeto e a identidade da sessão vêm do lançador: FUNDACAO_* herdadas do terminal (inclusive
        FUNDACAO_PERMITIR_TROCA_IDENTIDADE) não chegam à sessão."""
        r = self.abrir(FUNDACAO_PERMITIR_TROCA_IDENTIDADE="1", FUNDACAO_PROJECT="outro-projeto",
                       FUNDACAO_MCP_ESCRITA_PERMITIDA="mcp__*", **{IDENTIDADE: "outra-pessoa"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        linhas = self.chamada()
        self.assertFalse([l for l in linhas if l.startswith("ENV:FUNDACAO_PERMITIR_TROCA_IDENTIDADE=")])
        self.assertFalse([l for l in linhas if l.startswith("ENV:FUNDACAO_MCP_ESCRITA_PERMITIDA=")])
        self.assertIn("ENV:" + IDENTIDADE + "=sessao-caso-real", linhas)
        self.assertIn("ENV:FUNDACAO_PROJECT=caso-real", linhas)

    def test_modelo_do_lancador_e_bash_valido_com_fim_de_linha_lf(self):
        self.assertNotIn(b"\r", LANCADOR.read_bytes())
        r = subprocess.run([BASH, "-n", str(self.lancador)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)


BLOCO = "[interop]" + chr(10) + "enabled=false" + chr(10) + "appendWindowsPath=false" + chr(10)
VAZIO = "#!/usr/bin/env bash" + chr(10) + "exit 0" + chr(10)
DPKG_INSTALADO = "#!/usr/bin/env bash" + chr(10) + "printf 'install ok installed'" + chr(10)


def fotografia(*pastas: Path) -> dict:
    out = {}
    for pasta in pastas:
        for q in sorted(Path(pasta).rglob("*")) if Path(pasta).is_dir() else [Path(pasta)]:
            out[str(q)] = sha(q) if q.is_file() else "<pasta>"
    return out


@unittest.skipUnless(PODE, "1.7.10: o preparar-wsl.sh grava a área do titular no Linux (bash e /usr/bin/python3)")
class PrepararWslNoBash(unittest.TestCase):
    """O preparo do Ubuntu num ambiente descartável: casa, wsl.conf, área do titular e Claude Code falsos, sem sudo e
    sem rede (o ensaio usa --area-raiz e --bin em pastas temporárias)."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="preparar-wsl-teste-")).resolve()  # nome longo (TEMP curto no GitHub)
        self.skill, self.raiz = montar_raiz(self.base)
        self.preparar = self.skill / "assets" / "host" / "wsl" / "preparar-wsl.sh"
        self.home = self.base / "home"
        versoes = self.home / ".local" / "share" / "claude" / "versions"
        versoes.mkdir(parents=True)
        self.binario = versoes / "2.1.302"
        self.binario.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8", newline=chr(10))
        self.binario.chmod(0o755)
        self.falsos = self.base / "bin-falso"
        self.falsos.mkdir()
        self.conf = self.base / "wsl.conf"
        self.conf.write_text("[boot]" + chr(10) + "systemd=true" + chr(10) + (chr(10) + BLOCO) * 3, encoding="utf-8",
                             newline=chr(10))
        (self.base / "tmp").mkdir()

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def preparar_wsl(self, *args, wsl: bool = False, pacotes: bool = False, ensaio: bool = True):
        if pacotes:
            for nome in ("bwrap", "socat", "npm", "corepack"):
                (self.falsos / nome).write_text(VAZIO, encoding="utf-8", newline=chr(10))
                (self.falsos / nome).chmod(0o755)
            (self.falsos / "dpkg-query").write_text(DPKG_INSTALADO, encoding="utf-8", newline=chr(10))
            (self.falsos / "dpkg-query").chmod(0o755)
        env = {"HOME": str(self.home), "PATH": str(self.falsos) + os.pathsep + "/usr/bin:/bin"}
        if wsl:
            env["WSL_DISTRO_NAME"] = "Ensaio"
        extra = ["--area-raiz", self.base / "area", "--bin", self.base / "bin", "--temp-base", self.base / "tmp",
                 "--sonda-interop-cmd", self.base / "sem-interop", "--sonda-interop-binfmt",
                 self.base / "sem-interop"] if ensaio else []
        return rodar_bash(self.preparar, "--raiz", self.raiz, "--projeto", "caso-real", "--titular", "titular",
                          "--wsl-conf", self.conf, "--python", "/usr/bin/python3", "--claude-versao", "2.1.302",
                          "--perfil-windows", "/mnt/c/Users/<usuario>", *extra, *args, env_extra=env)

    def test_simulacao_mostra_o_plano_e_nao_grava_nada(self):
        antes = fotografia(self.home, self.raiz, self.conf)
        r = self.preparar_wsl("--simular")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(fotografia(self.home, self.raiz, self.conf), antes)
        self.assertFalse((self.base / "area").exists())
        faltam = [pacote for pacote, binario in (("bubblewrap", "bwrap"), ("socat", "socat"))
                  if not shutil.which(binario, path=str(self.falsos) + os.pathsep + "/usr/bin:/bin")]
        for trecho in ("SIMULAÇÃO", *faltam, "sudo", "wsl --terminate", sha(self.binario), "não conferido",
                       "abrir-fundacao-caso-real", "sockets sem filtro"):
            self.assertIn(trecho, r.stdout)

    def test_hash_informado_diferente_do_binario_e_recusado(self):
        r = self.preparar_wsl("--simular", "--claude-sha256", "0" * 64)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("não confere", r.stdout + r.stderr)

    def test_sem_o_perfil_do_windows_para_e_aponta_o_preparar_maquina(self):
        """1.7.10: o Windows não grava mais o perfil do Ubuntu; o que ele deixa na raiz são os hooks. Sem eles, o
        preparo para e aponta o preparar-maquina.ps1."""
        (self.raiz / ".claude" / "hooks" / "guarda_caminho.py").unlink()
        r = self.preparar_wsl("--simular")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("preparar-maquina.ps1", r.stdout + r.stderr)

    def test_sem_argumentos_mostra_o_uso(self):
        r = rodar_bash(self.preparar, env_extra={"HOME": str(self.home)})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("--raiz", r.stdout + r.stderr)

    def test_execucao_real_fixa_o_claude_e_e_idempotente(self):
        r = self.preparar_wsl("--claude-sha256", sha(self.binario), wsl=True, pacotes=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        texto = self.conf.read_text(encoding="utf-8")
        self.assertEqual(texto.count("[interop]"), 1)
        self.assertEqual(len(list(self.base.glob("wsl.conf.anterior-*"))), 1)
        copia = self.home / ".local" / "share" / "fundacao-ia" / "claude" / "2.1.302" / "claude"
        self.assertEqual(sha(copia), sha(self.binario))
        lancador = self.base / "bin" / "abrir-fundacao-caso-real"
        conteudo = lancador.read_text(encoding="utf-8")
        area = self.base / "area" / "projetos" / "caso-real"
        for valor in (sha(self.binario), str(area), "caso-real", "/claude/2.1.302/claude", "manifesto"):
            self.assertIn(valor, conteudo)
        antes = fotografia(self.home, self.raiz, self.conf, self.base / "area", self.base / "bin")
        r2 = self.preparar_wsl("--claude-sha256", sha(self.binario), wsl=True, pacotes=True)
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertEqual(fotografia(self.home, self.raiz, self.conf, self.base / "area", self.base / "bin"), antes)
        self.assertEqual(len(list(self.base.glob("wsl.conf.anterior-*"))), 1)
        self.assertNotIn("[criar]", r2.stdout)
        self.assertNotIn("[atualizar]", r2.stdout)

    def test_so_fixa_o_que_confere(self):
        """Auditoria Codex Security da 1.7.6, #5: o preparo fixava no lançador o hash do que encontrasse. Na 1.7.10, os
        hooks da raiz diferentes dos da skill, o kit da raiz diferente do da skill e a falta da pasta do Windows (que o
        perfil nega) param o script (código 1) sem gravar o lançador."""
        hook = self.raiz / ".claude" / "hooks" / "guarda_identidade.py"
        kit = self.raiz / "fundacao" / "__init__.py"
        casos = {  # nome: (mudança, argumentos a mais, item com [erro], trecho da mensagem)
            "hook diferente do da skill": (lambda: hook.write_bytes(hook.read_bytes() + b"# alterado\n"), (),
                                           "projeto caso-real", "guarda_identidade"),
            "kit diferente do da skill": (lambda: kit.write_bytes(kit.read_bytes() + b"# alterado\n"), (),
                                          "projeto caso-real", "kit da raiz"),
            "sem a pasta do Windows": (lambda: None, ("--perfil-windows", ""), "perfil-windows", "--perfil-windows"),
        }
        originais = {p: p.read_bytes() for p in (hook, kit)}
        lancador = self.base / "bin" / "abrir-fundacao-caso-real"
        for nome, (mudanca, extra, item, trecho) in casos.items():
            with self.subTest(nome):
                mudanca()
                r = self.preparar_wsl("--claude-sha256", sha(self.binario), *extra, wsl=True, pacotes=True)
                for p, conteudo in originais.items():
                    p.write_bytes(conteudo)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                erros = [l for l in r.stdout.splitlines() if l.strip().startswith(f"[erro] {item}:")]
                self.assertTrue(erros and trecho in erros[0], r.stdout)
                self.assertFalse(lancador.exists())
        r = self.preparar_wsl("--claude-sha256", sha(self.binario), wsl=True, pacotes=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(sha(self.binario), lancador.read_text(encoding="utf-8"))

    def test_canario_pelo_preparo_do_ubuntu(self):
        """1.7.10 (contratos, §0): --canario leva o relatório do ensaio real à área do titular. O que não é relatório
        real é recusado (código 1) e nada vai para a área; desde a 1.7.10.1, o real que não prova o confinamento vai
        como revogação ([revogar] canario) e o preparo dos projetos segue, com tudo fechado."""
        from test_host_projeto_apoio import relatorio_de_canario
        m = carregar_preparo(self.skill)
        relatorio = self.base / "relatorio-canario.json"
        canario = self.base / "area" / "canario" / "2.1.302.json"
        simulado = relatorio_de_canario(m, self.raiz, self.binario, simulado=True)
        relatorio.write_text(json.dumps(simulado), encoding="utf-8")
        r = self.preparar_wsl("--claude-sha256", sha(self.binario), "--canario", relatorio, wsl=True, pacotes=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue([l for l in r.stdout.splitlines() if l.strip().startswith("[erro] canario:")], r.stdout)
        self.assertFalse(canario.exists())
        forma = relatorio_de_canario(m, self.raiz, self.binario)["forma"]
        ruim = relatorio_de_canario(m, self.raiz, self.binario, conclusao={"forma": forma, "confina_comandos": False})
        relatorio.write_text(json.dumps(ruim), encoding="utf-8")
        r = self.preparar_wsl("--claude-sha256", sha(self.binario), "--canario", relatorio, wsl=True, pacotes=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue([l for l in r.stdout.splitlines() if l.strip().startswith("[revogar] canario:")], r.stdout)
        self.assertEqual(sha(canario), sha(relatorio))
        relatorio.write_text(json.dumps(relatorio_de_canario(m, self.raiz, self.binario)), encoding="utf-8")
        r = self.preparar_wsl("--claude-sha256", sha(self.binario), "--canario", relatorio, wsl=True, pacotes=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sha(canario), sha(relatorio))
        self.assertIn("[criar] canario:", r.stdout)

    def test_ensaio_com_ferramenta_base_grava_a_copia_protegida(self):
        """Folha da integração da 1.7.10, I11: o preparo do Ubuntu grava a cópia protegida da ferramenta do titular (no
        ensaio, em --ferramenta-base, repassada ao instalar-projeto); de novo, nada muda. Sem a opção, o ensaio não a
        grava (os outros testes)."""
        from apoio import versao_do_kit
        ferramentas = self.base / "ferramentas"
        r = self.preparar_wsl("--claude-sha256", sha(self.binario), "--ferramenta-base", ferramentas, wsl=True,
                              pacotes=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        copia = ferramentas / versao_do_kit(self.skill / "assets" / "fundacao-kit")
        hashes = json.loads((copia / "hashes.json").read_text(encoding="utf-8"))
        self.assertEqual(hashes["schema_version"], "fundacao.ferramenta_titular/1")
        self.assertEqual(sha(copia / "assets" / "host" / "fundacao_titular.py"),
                         hashes["arquivos"]["assets/host/fundacao_titular.py"])
        antes = fotografia(ferramentas)
        r = self.preparar_wsl("--claude-sha256", sha(self.binario), "--ferramenta-base", ferramentas, wsl=True,
                              pacotes=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(fotografia(ferramentas), antes)
        self.assertNotIn("[atualizar]", r.stdout)

    def test_titular_e_obrigatorio(self):
        r = rodar_bash(self.preparar, "--raiz", self.raiz, "--projeto", "caso-real", "--simular",
                       env_extra={"HOME": str(self.home)})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("--titular", r.stdout + r.stderr)

    def test_script_bash_valido_com_fim_de_linha_lf(self):
        self.assertNotIn(b"\r", PREPARAR.read_bytes())
        r = subprocess.run([BASH, "-n", str(PREPARAR)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)


class ModelosSemBash(unittest.TestCase):
    """O que dá para conferir em qualquer sistema: os scripts do Ubuntu em LF e o lançador do modelo bem formado."""

    def test_scripts_em_lf_e_marcadores_entre_aspas(self):
        for arquivo in (LANCADOR, PREPARAR):
            self.assertNotIn(b"\r", arquivo.read_bytes(), arquivo.name)
        m = carregar_preparo()
        self.assertEqual(sorted(set(m.MARCADOR.findall(LANCADOR.read_text(encoding="utf-8")))),
                         sorted(m.CHAVES_DO_LANCADOR))


if __name__ == "__main__":
    unittest.main()
