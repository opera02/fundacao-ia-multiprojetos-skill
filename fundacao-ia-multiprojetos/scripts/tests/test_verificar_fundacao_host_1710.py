"""Passo do host do verificar_fundacao.py neste PC (1.7.10; o passo falhava sempre aqui, RETOMADA de 26/10/2026).

- Em ~/.claude/skills e <raiz>/.claude/skills, só a ligação do instalador é aceita: primeiro nível e alvo final
  exatamente ~/.agents/skills/<o mesmo nome>, que existe; ligação para outro nome, para fora ou mais funda continua
  recusada.
- Em ~/.claude/plugins, arquivo de plugin com secret ou credentials no nome vira aviso, sem ser aberto; se uma fonte de
  hooks de plugin o cita (o inventário o leria), o passo continua recusado; os outros nomes protegidos também.
- Hooks do perfil do outro sistema (settings.wsl.json por /mnt/<l>/, settings.json por unidade) são traduzidos antes de
  resolver, para caírem nas áreas permitidas da raiz; /mnt/<l>/ fora delas continua recusado.
- Marcadores do sandbox na raiz: arquivo comum de 0 byte é aviso; .mcp.json comum até o teto e pastas .vscode/.idea
  também viram aviso; nos arquivos de shell e git, conteúdo ou pasta falham, e ligação/vínculo físico falham em qualquer um.
Perfis e raízes fictícios em pastas descartáveis; o inventário não roda (o executor é substituído)."""

from __future__ import annotations

import builtins
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import SCRIPTS, criar_ligacao_dir

CANARIO = "CONTEUDO-FICTICIO-NAO-DEVE-SER-LIDO"


def carregar():
    spec = importlib.util.spec_from_file_location("_verificar_host_1710", SCRIPTS / "verificar_fundacao.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="verificar-host-1710-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.raiz, self.perfil = self.base / "fundacao-ficticia", self.base / "perfil-ficticio"
        (self.raiz / "registry").mkdir(parents=True)
        (self.raiz / "registry" / "inventario-host.json").write_text("{}", encoding="utf-8")
        self.agentes = self.perfil / ".agents" / "skills"
        for nome in ("minha-skill", "outra-skill"):
            (self.agentes / nome).mkdir(parents=True)
            (self.agentes / nome / "SKILL.md").write_text("---\nname: " + nome + "\n---\n", encoding="utf-8")
        (self.perfil / ".claude" / "skills").mkdir(parents=True)
        self.mod = carregar()

    def seguro(self) -> tuple:
        avisos = []
        return self.mod.host_seguro(self.raiz, self.perfil, avisos), avisos


class TestLigacaoDoInstalador(Base):
    def test_ligacao_do_instalador_aceita_no_perfil_e_na_raiz(self):
        criar_ligacao_dir(self.perfil / ".claude" / "skills" / "minha-skill", self.agentes / "minha-skill")
        (self.raiz / ".claude" / "skills").mkdir(parents=True)
        criar_ligacao_dir(self.raiz / ".claude" / "skills" / "outra-skill", self.agentes / "outra-skill")
        ok, avisos = self.seguro()
        self.assertTrue(ok, avisos)
        self.assertIn("minha-skill", " ".join(avisos))
        self.assertIn("outra-skill", " ".join(avisos))

    def test_outra_ligacao_continua_recusada(self):
        fora = self.base / "fora" / "minha-skill"
        fora.mkdir(parents=True)
        (fora / "SKILL.md").write_text(CANARIO, encoding="utf-8")
        skills = self.perfil / ".claude" / "skills"
        casos = {"outro nome": (skills / "apelido", self.agentes / "minha-skill"),
                 "fora de ~/.agents/skills": (skills / "minha-skill", fora),
                 "a pasta de cima": (skills / "skills", self.agentes)}
        for caso, (link, alvo) in casos.items():
            with self.subTest(caso=caso):
                criar_ligacao_dir(link, alvo)
                try:
                    self.assertFalse(self.seguro()[0])
                finally:
                    os.rmdir(link) if os.name == "nt" else link.unlink()
        pasta = skills / "grupo"
        pasta.mkdir()
        criar_ligacao_dir(pasta / "minha-skill", self.agentes / "minha-skill")  # segundo nível
        self.assertFalse(self.seguro()[0])

    def test_alvo_que_e_ligacao_no_caminho_esperado_recusa(self):
        real = self.base / "real" / "minha-skill"
        real.mkdir(parents=True)
        destino = self.agentes / "terceira"
        criar_ligacao_dir(destino, real)  # ~/.agents/skills/terceira é ligação: não é o alvo do instalador
        criar_ligacao_dir(self.perfil / ".claude" / "skills" / "terceira", destino)
        self.assertFalse(self.mod.ligacao_do_instalador(self.perfil / ".claude" / "skills" / "terceira", self.perfil))
        self.assertFalse(self.seguro()[0])


class TestNomesDePlugin(Base):
    def plugin(self, hooks: dict | None = None, manifesto: dict | None = None) -> Path:
        raiz = self.perfil / ".claude" / "plugins" / "cache" / "loja-ficticia" / "seguranca" / "0.1.0"
        (raiz / "scripts" / "lib").mkdir(parents=True)
        (raiz / "scripts" / "lib" / "secret.py").write_text("# " + CANARIO + "\n", encoding="utf-8")
        (raiz / "tests").mkdir()
        (raiz / "tests" / "test_no_credentials_notice.py").write_text("# " + CANARIO + "\n", encoding="utf-8")
        (raiz / ".claude-plugin").mkdir()
        (raiz / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifesto or {"name": "seguranca"}),
                                                             encoding="utf-8")
        if hooks is not None:
            (raiz / "hooks").mkdir()
            (raiz / "hooks" / "hooks.json").write_text(json.dumps(hooks), encoding="utf-8")
        return raiz

    def espiao(self):
        abertos, os_open, open_ = [], os.open, builtins.open

        def abrir_os(caminho, *a, **k):
            abertos.append(str(caminho))
            return os_open(caminho, *a, **k)

        def abrir(caminho, *a, **k):
            abertos.append(str(caminho))
            return open_(caminho, *a, **k)

        return abertos, mock.patch("os.open", abrir_os), mock.patch("builtins.open", abrir)

    def test_nome_de_codigo_vira_aviso_sem_leitura(self):
        self.plugin(hooks={"hooks": {"PreToolUse": [{"hooks": [{"type": "command",
                                                                "command": "python ${CLAUDE_PLUGIN_ROOT}/h.py"}]}]}})
        abertos, p1, p2 = self.espiao()
        with p1, p2:
            ok, avisos = self.seguro()
        self.assertTrue(ok, avisos)
        self.assertEqual([a for a in abertos if "secret" in a.lower() or "credentials" in a.lower()], [])
        texto = " ".join(avisos)
        self.assertIn("2 arquivo(s) de plugin", texto)
        self.assertIn("scripts/lib/secret.py", texto)
        self.assertNotIn(CANARIO, texto)

    def test_hook_que_cita_o_arquivo_mantem_a_recusa(self):
        comando = {"type": "command", "command": "python \"${CLAUDE_PLUGIN_ROOT}/scripts/lib/Secret.py\""}
        self.plugin(hooks={"hooks": {"SessionStart": [{"hooks": [comando]}]}})
        self.assertFalse(self.seguro()[0])

    def test_arquivo_de_hooks_apontado_pelo_manifesto_tambem_conta(self):
        raiz = self.plugin(manifesto={"name": "seguranca", "hooks": "./config/meus-hooks.json"})
        (raiz / "config").mkdir()
        (raiz / "config" / "meus-hooks.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [
            {"type": "command", "command": "python ${CLAUDE_PLUGIN_ROOT}/scripts/lib/secret.py"}]}]}}),
            encoding="utf-8")
        self.assertFalse(self.seguro()[0])
        (raiz / "config" / "meus-hooks.json").write_text(json.dumps({"hooks": {}}), encoding="utf-8")
        self.assertTrue(self.seguro()[0])

    def test_manifesto_na_raiz_do_plugin_tambem_conta(self):
        raiz = self.plugin()
        (raiz / "plugin.json").write_text(json.dumps({"name": "seguranca", "hooks": "h/eventos.json"}),
                                          encoding="utf-8")
        (raiz / "h").mkdir()
        (raiz / "h" / "eventos.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [
            {"type": "command", "command": "python ${CLAUDE_PLUGIN_ROOT}/tests/test_no_credentials_notice.py"}]}]}}),
            encoding="utf-8")
        self.assertFalse(self.seguro()[0])

    def test_outros_nomes_protegidos_e_pasta_de_credenciais_continuam_recusados(self):
        raiz = self.plugin()
        for rel, pasta in ((".env", False), ("chave.pem", False), ("secret.key", False), ("credentials", True),
                           ("id_rsa", False)):
            with self.subTest(rel=rel):
                alvo = raiz / rel
                alvo.mkdir() if pasta else alvo.write_text(CANARIO, encoding="utf-8")
                try:
                    self.assertFalse(self.seguro()[0])
                finally:
                    alvo.rmdir() if pasta else alvo.unlink()
        self.assertTrue(self.seguro()[0])

    def test_fora_dos_plugins_o_nome_continua_recusado(self):
        (self.agentes / "minha-skill" / "secret.py").write_text(CANARIO, encoding="utf-8")
        self.assertFalse(self.seguro()[0])


class TestMarcadoresDoSandbox(Base):
    def passos(self) -> dict:
        def executar(cmd, timeout):
            return 0, {"ok": True}, ""
        with mock.patch.object(self.mod, "executar", executar):
            res = self.mod.verificar(self.raiz, perfil=self.perfil)
        return {p["id"]: p for p in res["passos"]}

    def test_zero_byte_e_aviso_e_o_passo_segue(self):
        for nome in (".bashrc", ".gitconfig", ".mcp.json", ".vscode", ".idea"):
            (self.raiz / nome).write_bytes(b"")
        host = self.passos()["host"]
        self.assertEqual(host["estado"], "ok", host)
        self.assertIn(".mcp.json", " ".join(host["avisos"]))
        self.assertNotIn("marcadores_recusados", host)

    def test_conteudo_ou_pasta_dos_arquivos_de_shell_e_git_falham(self):
        (self.raiz / ".bashrc").write_text("echo " + CANARIO + "\n", encoding="utf-8")
        (self.raiz / ".gitconfig").mkdir()  # arquivo de git como pasta: continua falha
        (self.raiz / ".profile").write_bytes(b"")
        host = self.passos()["host"]
        self.assertEqual(host["estado"], "falhou", host)
        self.assertEqual(host["marcadores_recusados"], {".bashrc": "com conteúdo", ".gitconfig": "pasta"})
        self.assertNotIn(CANARIO, json.dumps(host))
        (self.raiz / ".bashrc").unlink()
        (self.raiz / ".gitconfig").rmdir()
        criar_ligacao_dir(self.raiz / ".idea", self.base)  # .idea é pasta de editor, mas a ligação recusa sempre
        self.assertEqual(self.passos()["host"]["marcadores_recusados"], {".idea": "ligação"})

    def test_mcp_com_conteudo_e_pastas_de_editor_sao_aviso(self):
        (self.raiz / ".mcp.json").write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
        (self.raiz / ".vscode").mkdir()
        (self.raiz / ".idea").mkdir()
        host = self.passos()["host"]
        self.assertEqual(host["estado"], "ok", host)
        self.assertNotIn("marcadores_recusados", host)
        texto = " ".join(host.get("avisos", []))
        for nome in (".mcp.json", ".vscode", ".idea"):
            self.assertIn(nome, texto)
        self.assertNotIn(CANARIO, json.dumps(host))

    def test_mcp_acima_do_teto_falha(self):
        (self.raiz / ".mcp.json").write_bytes(b"{}")
        with mock.patch.object(self.mod, "TETO_ENTRADA", 1):  # força o .mcp.json acima do teto
            host = self.passos()["host"]
        self.assertEqual(host["estado"], "falhou", host)
        self.assertEqual(host["marcadores_recusados"], {".mcp.json": "acima do teto"})

    def test_lista_igual_a_obrigatoria_do_bwrap(self):
        self.assertEqual(set(self.mod.MARCADORES_DO_SANDBOX),
                         {".bashrc", ".bash_profile", ".zshrc", ".zprofile", ".profile", ".gitconfig", ".gitmodules",
                          ".ripgreprc", ".mcp.json", ".vscode", ".idea"})


class TestCaminhoDeHookDoOutroSistema(Base):
    """ALTA 1: o hook do perfil do outro sistema é traduzido antes de resolver, senão o passo falha sempre aqui."""

    def _hooks(self) -> None:
        (self.raiz / ".claude" / "hooks").mkdir(parents=True)
        (self.raiz / ".claude" / "hooks" / "guarda.py").write_bytes(b"")

    def _config(self, nome: str, alvo: str) -> None:
        (self.raiz / ".claude").mkdir(exist_ok=True)
        (self.raiz / ".claude" / nome).write_text(json.dumps({"hooks": {"PreToolUse": [{"hooks": [
            {"type": "command", "command": "python", "args": [alvo]}]}]}}), encoding="utf-8")

    def test_traducao_entre_os_sistemas(self):
        trad = self.mod._caminho_no_sistema
        self.assertEqual(trad("/mnt/e/Projeto/.claude/hooks/x.py", "nt"), "e:/Projeto/.claude/hooks/x.py")
        self.assertEqual(trad("E:/Projeto/.claude/hooks/x.py", "posix"), "/mnt/e/Projeto/.claude/hooks/x.py")
        self.assertEqual(trad("D:\\IA\\x.py".replace("\\", "/"), "posix"), "/mnt/d/IA/x.py")
        self.assertEqual(trad("/home/u/.claude/hooks/x.py", "nt"), "/home/u/.claude/hooks/x.py")  # nativo não muda
        self.assertEqual(trad("/home/u/.claude/hooks/x.py", "posix"), "/home/u/.claude/hooks/x.py")

    def test_raiz_dada_por_nome_diferente_do_real_continua_valendo(self):
        """O runner do Windows entrega a pasta temporária com nome curto 8.3 (C:\\Users\\RUNNER~1\\...), e o realpath
        do arquivo vem com o nome longo: a leitura contida compara com a pasta real, não com a pasta como foi dada.
        O realpath é trocado por um que devolve outra forma do mesmo lugar (nada depende de haver nome curto aqui)."""
        self._hooks()
        self._config("settings.json", str(self.raiz / ".claude" / "hooks" / "guarda.py"))
        original = os.path.realpath
        dada = str(Path(original(self.raiz)))

        def outra_forma(caminho, *args, **kw):
            real = str(original(caminho, *args, **kw))
            return dada + "-longo" + real[len(dada):] if real.startswith(dada) else real

        with mock.patch("os.path.realpath", outra_forma):
            ok, avisos = self.seguro()
        self.assertTrue(ok, avisos)

    @unittest.skipUnless(os.name == "nt", "o /mnt/<l>/ do perfil do WSL só se traduz para unidade no Windows")
    def test_no_windows_hooks_do_wsl_e_do_windows_resolvem_na_raiz(self):
        self._hooks()
        drive = self.raiz.drive[0].lower()
        resto = self.raiz.as_posix()[len(self.raiz.drive):].lstrip("/")
        self._config("settings.json", str(self.raiz / ".claude" / "hooks" / "guarda.py"))  # unidade: nativo no Windows
        self._config("settings.wsl.json", "/mnt/" + drive + "/" + resto + "/.claude/hooks/guarda.py")  # WSL por /mnt/
        ok, avisos = self.seguro()
        self.assertTrue(ok, avisos)
        self._config("settings.wsl.json", "/mnt/c/Users/<usuario>-ninguem/fora/x.py")  # /mnt/ fora das áreas: recusa
        self.assertFalse(self.seguro()[0])

    @unittest.skipUnless(os.name != "nt", "a unidade do perfil do Windows só se traduz para /mnt/ no POSIX")
    def test_no_posix_o_hook_por_unidade_e_traduzido_e_conferido(self):
        self._hooks()
        self._config("settings.wsl.json", str(self.raiz / ".claude" / "hooks" / "guarda.py"))  # nativo POSIX
        ok, avisos = self.seguro()
        self.assertTrue(ok, avisos)
        self._config("settings.json", "D:/IA/fundacao/.claude/hooks/x.py")  # unidade -> /mnt/d/... fora das áreas
        self.assertFalse(self.seguro()[0])


if __name__ == "__main__":
    unittest.main()
