"""Lado do WSL do preparo do host: o lançador `assets/host/wsl/abrir-sessao.sh` (Claude Code fixado por hash,
perfil e hooks conferidos, prompt de retomada) e o `assets/host/wsl/preparar-wsl.sh`.

Os scripts rodam num bash de verdade: no Windows, só o do Git for Windows. O `bash.exe` da System32 abriria a
distribuição do WSL, e a fundação não pode ter o banco aberto pelo Windows e pelo WSL ao mesmo tempo; sem o bash
do Git, os testes ficam pulados com o motivo. O `claude` é um script falso que só registra como foi chamado.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import ENV, SKILL

HOST = SKILL / "assets" / "host"
LANCADOR = HOST / "wsl" / "abrir-sessao.sh"
PREPARAR = HOST / "wsl" / "preparar-wsl.sh"


def bash_de_teste() -> str | None:
    if os.name != "nt":
        return shutil.which("bash")
    git = shutil.which("git")
    if not git:
        return None
    sistema = Path(os.environ.get("SystemRoot", "C:/Windows")).resolve()
    for pasta in Path(git).resolve().parents[1:3]:
        candidato = pasta / "bin" / "bash.exe"
        if candidato.is_file() and sistema not in candidato.resolve().parents:
            return str(candidato)
    return None


BASH = bash_de_teste()


def posix(caminho: Path) -> str:
    """Caminho como o bash vê: no Git for Windows, `/c/...`."""
    if os.name != "nt":
        return str(caminho)
    s = Path(caminho).resolve().as_posix()
    return "/" + s[0].lower() + s[2:]


def ajudante():
    sys.dont_write_bytecode = True  # sem __pycache__ em assets/host/ (o CEN-11 acusa)
    spec = importlib.util.spec_from_file_location("preparo_host", HOST / "preparo_host.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def sha(caminho: Path) -> str:
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


FALSO = ("#!/usr/bin/env bash\n"
         'for a in "$@"; do echo "ARG:$a"; done > "$SAIDA_FALSA"\n'
         'echo "PROJETO:${FUNDACAO_PROJECT:-}" >> "$SAIDA_FALSA"\n'
         'echo "PWD:$(pwd)" >> "$SAIDA_FALSA"\n')


def rodar_bash(script: Path, *args, env_extra: dict | None = None, cwd: Path | None = None):
    env = {k: v for k, v in ENV.items() if not k.startswith("FUNDACAO_")}
    env.update(env_extra or {})
    return subprocess.run([BASH, posix(script), *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, timeout=180, cwd=str(cwd) if cwd else None)


def montar_raiz(base: Path, projeto: str = "caso-real") -> Path:
    """Raiz de ensaio com os hooks da skill, o perfil do WSL gerado pelo modelo e a identidade do titular."""
    raiz = base / "Fundação Teste"
    hooks = raiz / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    (raiz / "projects" / projeto).mkdir(parents=True)
    for nome in ("guarda_caminho.py", "guarda_identidade.py"):
        shutil.copyfile(SKILL / "assets" / "hooks" / nome, hooks / nome)
    m = ajudante()
    # a raiz como o ajudante a vê quando o preparar-wsl.sh o chama (no Git for Windows, /mnt/c/...)
    perfil = m.perfil_wsl(raiz=m.caminho_wsl(str(raiz)), projeto=projeto, perfil_windows="/mnt/c/Perfis/titular",
                          outros_projetos=[])
    (raiz / ".claude" / "settings.wsl.json").write_text(m.texto_json(perfil), encoding="utf-8", newline="\n")
    (raiz / ".claude" / "settings.local.json").write_text(m.texto_json(m.identidade("titular")), encoding="utf-8",
                                                          newline="\n")
    return raiz


@unittest.skipUnless(BASH, "bash do Git for Windows (ou do Linux) indisponível: lançador não testado aqui")
class LancadorNoBash(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="lancador-bash-teste-")).resolve()  # nome longo (TEMP curto no GitHub)
        self.raiz = montar_raiz(self.base)
        self.claude = self.base / "bin" / "claude"
        self.claude.parent.mkdir()
        self.claude.write_text(FALSO, encoding="utf-8", newline="\n")
        self.claude.chmod(0o755)  # no Linux, sem o bit de execução o bash não roda o binário falso (126)
        self.saida = self.base / "chamada.txt"
        m = ajudante()
        texto = m.lancador({
            "RAIZ": posix(self.raiz), "PROJETO": "caso-real", "CLAUDE_BIN": posix(self.claude),
            "CLAUDE_VERSAO": "2.1.302", "CLAUDE_SHA256": sha(self.claude), "CLAUDE_ORIGEM_HASH": "informado",
            "PERFIL_SHA256": sha(self.raiz / ".claude" / "settings.wsl.json"),
            "HOOK_CAMINHO_SHA256": sha(self.raiz / ".claude" / "hooks" / "guarda_caminho.py"),
            "HOOK_IDENTIDADE_SHA256": sha(self.raiz / ".claude" / "hooks" / "guarda_identidade.py"),
            "SKILL_MD": "/mnt/c/Perfis/titular/.claude/skills/fundacao-ia-multiprojetos/SKILL.md"})
        self.lancador = self.base / "abrir-fundacao.sh"
        self.lancador.write_text(texto, encoding="utf-8", newline="\n")

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def abrir(self):
        return rodar_bash(self.lancador, env_extra={"SAIDA_FALSA": posix(self.saida)})

    def test_abre_com_o_perfil_fixado_o_projeto_e_o_prompt_de_retomada(self):
        r = self.abrir()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        linhas = self.saida.read_text(encoding="utf-8").splitlines()
        args = [l[4:] for l in linhas if l.startswith("ARG:")]
        self.assertEqual(args[:4], ["--settings", posix(self.raiz) + "/.claude/settings.wsl.json",
                                    "--setting-sources", "local"])
        self.assertEqual(len(args), 5)
        self.assertIn("RETOMADA.md", args[4])
        self.assertIn("caso-real", args[4])
        self.assertIn("PROJETO:caso-real", linhas)
        self.assertIn("PWD:" + posix(self.raiz), linhas)

    def test_claude_trocado_nao_abre(self):
        with open(self.claude, "a", encoding="utf-8", newline="\n") as f:
            f.write("# outro binário\n")
        r = self.abrir()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("mudou", r.stderr)
        self.assertFalse(self.saida.exists())

    def test_perfil_ou_hook_alterado_nao_abre(self):
        for arquivo in (self.raiz / ".claude" / "settings.wsl.json",
                        self.raiz / ".claude" / "hooks" / "guarda_caminho.py",
                        self.raiz / ".claude" / "hooks" / "guarda_identidade.py"):
            with self.subTest(arquivo=arquivo.name):
                original = arquivo.read_bytes()
                arquivo.write_bytes(original + b"\n")
                r = self.abrir()
                arquivo.write_bytes(original)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("mudou", r.stderr)
                self.assertFalse(self.saida.exists())

    def test_sem_a_identidade_do_titular_nao_abre(self):
        (self.raiz / ".claude" / "settings.local.json").unlink()
        r = self.abrir()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("identidade", r.stderr)
        self.assertFalse(self.saida.exists())

    def test_projeto_do_settings_local_diferente_do_lancador_nao_abre(self):
        """Revisão de segurança da 1.7.0 (pendência): o lançador exporta o projeto e o settings.local.json também o
        entrega; com os dois diferentes, qual vale dependeria da precedência do host. A sessão não abre."""
        local = self.raiz / ".claude" / "settings.local.json"
        m = ajudante()
        for projeto, abre in (("outro-projeto", False), ("caso-real", True)):
            with self.subTest(projeto=projeto):
                local.write_text(m.texto_json(m.identidade("titular", projeto=projeto)), encoding="utf-8", newline="\n")
                r = self.abrir()
                self.assertEqual(r.returncode == 0, abre, r.stdout + r.stderr)
                if not abre:
                    self.assertIn("projeto", r.stderr)
                    self.assertFalse(self.saida.exists())

    def test_modelo_do_lancador_e_bash_valido_com_fim_de_linha_lf(self):
        self.assertNotIn(b"\r", LANCADOR.read_bytes())
        r = subprocess.run([BASH, "-n", posix(self.lancador)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)



BLOCO = "[interop]" + chr(10) + "enabled=false" + chr(10) + "appendWindowsPath=false" + chr(10)
VAZIO = "#!/usr/bin/env bash" + chr(10) + "exit 0" + chr(10)


def fotografia(*pastas: Path) -> dict:
    out = {}
    for pasta in pastas:
        for q in sorted(Path(pasta).rglob("*")) if Path(pasta).is_dir() else [Path(pasta)]:
            out[str(q)] = sha(q) if q.is_file() else "<pasta>"
    return out


@unittest.skipUnless(BASH, "bash do Git for Windows (ou do Linux) indisponível: preparar-wsl.sh não testado aqui")
class PrepararWslNoBash(unittest.TestCase):
    """O preparo do Ubuntu num ambiente descartável: casa, wsl.conf e Claude Code falsos, sem sudo e sem rede."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="preparar-wsl-teste-")).resolve()  # nome longo (TEMP curto no GitHub)
        self.raiz = montar_raiz(self.base)
        self.home = self.base / "home"
        versoes = self.home / ".local" / "share" / "claude" / "versions"
        versoes.mkdir(parents=True)
        self.binario = versoes / "2.1.302"
        self.binario.write_text(FALSO, encoding="utf-8", newline=chr(10))
        self.binario.chmod(0o755)
        (self.home / ".claude" / "skills" / "fundacao-ia-multiprojetos").mkdir(parents=True)  # ligação já feita
        self.falsos = self.base / "bin-falso"
        self.falsos.mkdir()
        self.conf = self.base / "wsl.conf"
        self.conf.write_text("[boot]" + chr(10) + "systemd=true" + chr(10) + (chr(10) + BLOCO) * 3, encoding="utf-8",
                             newline=chr(10))

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def preparar(self, *args, wsl: bool = False, pacotes: bool = False):
        if pacotes:
            for nome in ("bwrap", "socat"):
                (self.falsos / nome).write_text(VAZIO, encoding="utf-8", newline=chr(10))
        env = {"HOME": posix(self.home), "PATH": str(self.falsos) + os.pathsep + os.environ.get("PATH", "")}
        if wsl:
            env["WSL_DISTRO_NAME"] = "Ensaio"
        return rodar_bash(PREPARAR, "--raiz", posix(self.raiz), "--projeto", "caso-real", "--wsl-conf",
                          posix(self.conf), "--python", posix(Path(sys.executable)), "--claude-versao", "2.1.302",
                          *args, env_extra=env)

    def test_simulacao_mostra_o_plano_e_nao_grava_nada(self):
        antes = fotografia(self.home, self.raiz, self.conf)
        r = self.preparar("--simular")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(fotografia(self.home, self.raiz, self.conf), antes)
        for trecho in ("SIMULAÇÃO", "bubblewrap", "socat", "sudo", "wsl --terminate", sha(self.binario),
                       "não conferido", "abrir-fundacao.sh"):
            self.assertIn(trecho, r.stdout)

    def test_hash_informado_diferente_do_binario_e_recusado(self):
        r = self.preparar("--simular", "--claude-sha256", "0" * 64)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("não confere", r.stdout + r.stderr)

    def test_sem_o_perfil_do_windows_para_e_aponta_o_preparar_maquina(self):
        (self.raiz / ".claude" / "settings.wsl.json").unlink()
        r = self.preparar("--simular")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("preparar-maquina.ps1", r.stdout + r.stderr)

    def test_sem_argumentos_mostra_o_uso(self):
        r = rodar_bash(PREPARAR, env_extra={"HOME": posix(self.home)})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("--raiz", r.stdout + r.stderr)

    def test_execucao_real_fixa_o_claude_e_e_idempotente(self):
        r = self.preparar("--claude-sha256", sha(self.binario), wsl=True, pacotes=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        texto = self.conf.read_text(encoding="utf-8")
        self.assertEqual(texto.count("[interop]"), 1)
        self.assertEqual(len(list(self.base.glob("wsl.conf.anterior-*"))), 1)
        copia = self.home / ".local" / "share" / "fundacao-ia" / "claude" / "2.1.302" / "claude"
        self.assertEqual(sha(copia), sha(self.binario))
        lancador = self.home / "abrir-fundacao.sh"
        conteudo = lancador.read_text(encoding="utf-8")
        for valor in (sha(self.binario), sha(self.raiz / ".claude" / "settings.wsl.json"), "caso-real",
                      "/fundacao-ia/claude/2.1.302/claude", "manifesto"):
            self.assertIn(valor, conteudo)
        antes = fotografia(self.home, self.raiz, self.conf)
        r2 = self.preparar("--claude-sha256", sha(self.binario), wsl=True, pacotes=True)
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertEqual(fotografia(self.home, self.raiz, self.conf), antes)
        self.assertEqual(len(list(self.base.glob("wsl.conf.anterior-*"))), 1)
        self.assertNotIn("[criar]", r2.stdout)
        self.assertNotIn("[atualizar]", r2.stdout)

    def test_script_bash_valido_com_fim_de_linha_lf(self):
        self.assertNotIn(b"\r", PREPARAR.read_bytes())
        r = subprocess.run([BASH, "-n", posix(PREPARAR)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
