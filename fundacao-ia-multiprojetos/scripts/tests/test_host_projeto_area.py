"""Área do titular no Ubuntu e conferência do lançador (1.7.10; contratos do lote 2, §6; folha do HOST, itens 3 e 4).

`preparo_host.py instalar-projeto` grava, de dono root, `/etc/fundacao-ia/projetos/<p>/` (perfil, porteiro.json,
mcp.json, aberturas.json, ficha/, plugins/, hashes.json), as cópias conferidas da skill e do Claude Code e o lançador
`/usr/local/bin/abrir-fundacao-<p>`. Aqui roda em modo de ensaio (--area-raiz e --bin em pastas temporárias, sem
root), com os substitutos do apoio para as peças dos outros pacotes. A conferência que o lançador roda
(`conferir-abertura`) acusa cada arquivo fixado que mudou, a ficha vencida, a trava de manutenção, as configurações e o
`.mcp.json` do projeto e limpa os marcadores de 0 byte do sandbox. Os de instalação só no Linux (a área é do Ubuntu).
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import stat
import tempfile
import unittest
from datetime import date
from pathlib import Path

from test_host_projeto_apoio import (LINUX, carregar_preparo, claude_de_ensaio, ficha_de_ensaio,
                                     gravar_ficha_na_caixa, instalar, instalar_canario, raiz_de_ensaio,
                                     relatorio_de_canario, sha, skill_de_ensaio)


def fotografia(*pastas: Path) -> dict:
    out = {}
    for pasta in pastas:
        for p in sorted(Path(pasta).rglob("*")) if Path(pasta).exists() else []:
            out[str(p)] = sha(p) if p.is_file() else "<pasta>"
    return out


class _Base(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="area-titular-1710-")).resolve()
        self.skill = skill_de_ensaio(self.base)
        self.raiz = raiz_de_ensaio(self.base, self.skill)
        (self.base / "home").mkdir()
        self.claude = claude_de_ensaio(self.base / "claude-ensaio")
        self.m = carregar_preparo(self.skill)
        self.area = self.base / "area" / "projetos" / "caso-real"
        self.proj = self.raiz / "projects" / "caso-real"

    def tearDown(self):
        for p in sorted(self.base.rglob("*"), reverse=True):  # cópias 0444/0555 da área: o rmtree precisa da escrita
            try:
                if not p.is_symlink():
                    os.chmod(p, 0o700 if p.is_dir() else 0o600)
            except OSError:
                pass
        shutil.rmtree(self.base, ignore_errors=True)

    def instalar(self, *extra, simular=False, codigo=0):
        r = instalar(self.skill, self.raiz, self.base, "caso-real", self.claude, *extra, simular=simular)
        self.assertEqual(r.returncode, codigo, r.stdout + r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def aprovar_canario(self, **mudancas):
        """O titular rodou o ensaio real e instalou o relatório aprovado (contratos, §0: sem ele, nenhuma ficha vale)."""
        r = instalar_canario(self.skill, self.base, relatorio_de_canario(self.m, self.raiz, self.claude, **mudancas))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)


@unittest.skipUnless(LINUX, "a área do titular é do Ubuntu (WSL2): instalar-projeto só roda no Linux")
class InstalarProjeto(_Base):
    def test_grava_a_area_o_lancador_e_o_espelho(self):
        rel = self.instalar()
        for nome in ("settings.wsl.json", "porteiro.json", "mcp.json", "aberturas.json", "hashes.json"):
            arquivo = self.area / nome
            self.assertTrue(arquivo.is_file(), nome)
            self.assertEqual(stat.S_IMODE(arquivo.stat().st_mode), 0o644, nome)
            espelho = self.raiz / ".claude" / "projetos" / "caso-real" / nome
            self.assertEqual(sha(espelho), sha(arquivo), nome)  # espelho legível, não autoritativo
        porteiro = json.loads((self.area / "porteiro.json").read_text(encoding="utf-8"))
        conta_do_porteiro = self.m.funcao_do_kit(self.skill)[0]  # a mesma conta que o porteiro.py conferir usa
        self.assertEqual(porteiro, {"schema_version": "fundacao.porteiro/1", "raiz": self.raiz.as_posix(),
                                    "projeto": "caso-real", "kit_sha256": conta_do_porteiro(self.raiz),
                                    "assinante": "titular", "operacoes": {"fundacao": {}}})
        self.assertEqual(json.loads((self.area / "mcp.json").read_text(encoding="utf-8")), {"mcpServers": {}})
        self.assertFalse(json.loads((self.area / "aberturas.json").read_text(encoding="utf-8"))["valida"])
        lancador = self.base / "bin" / "abrir-fundacao-caso-real"
        self.assertEqual(stat.S_IMODE(lancador.stat().st_mode), 0o755)
        texto = lancador.read_text(encoding="utf-8")
        for trecho in (sha(self.claude), f"AREA='{self.area.as_posix()}'", "--strict-mcp-config", "PLUGINS=''",
                       "FERRAMENTAS='Bash,Read,Edit,Write,Glob,Grep,Skill,Agent,TodoWrite'"):
            self.assertIn(trecho, texto)
        hashes = json.loads((self.area / "hashes.json").read_text(encoding="utf-8"))
        copia = Path(hashes["arvores"]["skill"]["caminho"])
        self.assertTrue((copia / "assets" / "host" / "wsl" / "porteiro.py").is_file())
        self.assertEqual(sha(self.base / "area" / "claude" / "2.1.302" / "claude"), sha(self.claude))
        perfil = json.loads((self.area / "settings.wsl.json").read_text(encoding="utf-8"))
        self.assertEqual(self.m.conferir_perfil_wsl(
            perfil, self.raiz.as_posix(), "caso-real", ["lab-a"], aberturas=self.m.aberturas_fechadas(),
            parametros={"perfil_windows": "/mnt/c/Users/<usuario>", "ancora_base": "/mnt/c/ProgramData/FundacaoIA",
                        "temp_base": (self.base / "tmp").as_posix()}), [])
        self.assertEqual(rel["proximo_passo"], "abrir-fundacao-caso-real")

    def test_segunda_vez_nada_muda(self):
        self.instalar()
        antes = fotografia(self.base / "area", self.base / "bin")
        rel = self.instalar()
        self.assertEqual(fotografia(self.base / "area", self.base / "bin"), antes)
        self.assertEqual({a["acao"] for a in rel["acoes"]}, {"igual"})

    def test_simulacao_nao_grava_nada(self):
        rel = self.instalar(simular=True)
        self.assertTrue(rel["simulacao"])
        self.assertFalse((self.base / "area").exists())
        self.assertFalse((self.base / "bin").exists())

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "processo root: a recusa sem root não se aplica")
    def test_sem_root_e_sem_ensaio_recusa(self):
        import subprocess
        import sys
        from apoio import ENV
        r = subprocess.run([sys.executable, "-I", "-B", str(self.skill / "assets" / "host" / "preparo_host.py"),
                            "instalar-projeto", "--raiz", str(self.raiz), "--projeto", "caso-real", "--titular",
                            "titular", "--claude", str(self.claude), "--claude-versao", "2.1.302", "--claude-sha256",
                            sha(self.claude), "--origem-hash", "ensaio", "--perfil-windows", "/mnt/c/Users/<usuario>", "--casa",
                            str(self.base / "home"), "--usuario", "ensaio"], capture_output=True, text=True, env=ENV,
                           timeout=120)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("sudo", r.stdout)

    def test_hook_ou_kit_da_raiz_diferente_recusa_sem_gravar(self):
        hook = self.raiz / ".claude" / "hooks" / "guarda_leitura.py"
        kit = self.raiz / "fundacao" / "__init__.py"
        for arquivo, trecho in ((hook, "guarda_leitura"), (kit, "kit da raiz")):
            with self.subTest(trecho):
                original = arquivo.read_bytes()
                arquivo.write_bytes(original + b"# alterado\n")
                r = instalar(self.skill, self.raiz, self.base, "caso-real", self.claude)
                arquivo.write_bytes(original)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn(trecho, r.stdout)
                self.assertFalse((self.base / "area").exists())
                self.assertFalse((self.base / "bin").exists())

    def test_ficha_da_caixa_de_entrada_e_versoes(self):
        self.aprovar_canario()  # 1.7.10 (contratos, §0): sem o canário aprovado, a ficha não vale
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 2, rede={"dominios": ["pypi.org"]}))
        rel = self.instalar()
        self.assertEqual(rel["ficha"]["acao"], "instalar")
        ficha = self.area / "ficha"
        self.assertEqual(sorted(os.listdir(ficha)), ["ficha-v2.json", "ficha-v2.json.sig", "maior-versao"])
        self.assertEqual((ficha / "maior-versao").read_text(encoding="ascii").strip(), "2")
        perfil = json.loads((self.area / "settings.wsl.json").read_text(encoding="utf-8"))
        self.assertEqual(perfil["sandbox"]["network"]["allowedDomains"], ["pypi.org"])
        self.assertTrue(json.loads((self.area / "aberturas.json").read_text(encoding="utf-8"))["valida"])
        caixa = self.raiz / ".claude" / "projetos" / "caso-real" / "ficha"
        for nome in os.listdir(caixa):
            os.unlink(caixa / nome)
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 1))
        r = instalar(self.skill, self.raiz, self.base, "caso-real", self.claude)
        # revisão do lote 2: a ficha menor não volta, mas não trava o preparo (segue a v2 da área, com aviso)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("menor que a maior", r.stdout)
        self.assertEqual(json.loads(r.stdout)["ficha"]["acao"], "sem-ficha-nova")
        self.assertEqual(sorted(os.listdir(ficha)), ["ficha-v2.json", "ficha-v2.json.sig", "maior-versao"])
        os.unlink(caixa / "ficha-v1.json")
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 2, websearch=True))
        r = instalar(self.skill, self.raiz, self.base, "caso-real", self.claude)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("difere da v2 instalada", r.stdout)
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 3))
        self.instalar()
        self.assertEqual(sorted(os.listdir(ficha)), ["ficha-v3.json", "ficha-v3.json.sig", "maior-versao"])
        perfil = json.loads((self.area / "settings.wsl.json").read_text(encoding="utf-8"))
        self.assertEqual(perfil["sandbox"]["network"]["allowedDomains"], [])  # a v3 fechou a rede

    def test_pyc_fora_do_pycache_no_kit_da_raiz_conta(self):
        """Revisão do lote 2: a conta antiga deixava de fora os .pyc e um módulo sem fonte pode ser importado. Pela
        conta do porteiro, o .pyc plantado faz o kit da raiz diferir do da skill: nada é gravado."""
        plantado = self.raiz / "fundacao" / "plantado.pyc"
        plantado.write_bytes(b"\x00bytecode de ensaio")
        r = instalar(self.skill, self.raiz, self.base, "caso-real", self.claude)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("kit da raiz", r.stdout)
        self.assertFalse((self.base / "area").exists())
        plantado.unlink()
        (self.raiz / "fundacao" / "__pycache__").mkdir(exist_ok=True)
        (self.raiz / "fundacao" / "__pycache__" / "x.cpython-312.pyc").write_bytes(b"\x00")  # o porteiro não lê
        self.instalar()

    def test_versao_menor_na_caixa_nao_trava_a_regeneracao_por_projeto_novo(self):
        self.aprovar_canario()
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 2, rede={"dominios": ["pypi.org"]}))
        self.instalar()
        caixa = self.raiz / ".claude" / "projetos" / "caso-real" / "ficha"
        for nome in os.listdir(caixa):  # uma sessão apagou a nova da caixa e deixou uma velha
            os.unlink(caixa / nome)
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 1))
        (self.raiz / "projects" / "lab-novo").mkdir()
        self.assertFalse(self.m.conferir_abertura(self.raiz, "caso-real", self.area)["ok"])  # exige a regeneração
        rel = self.instalar()
        self.assertEqual(rel["ficha"]["acao"], "sem-ficha-nova")
        perfil = json.loads((self.area / "settings.wsl.json").read_text(encoding="utf-8"))
        self.assertIn(f"Read(/{self.raiz.as_posix()}/projects/lab-novo/**)", perfil["permissions"]["deny"])
        self.assertEqual(perfil["sandbox"]["network"]["allowedDomains"], ["pypi.org"])  # segue a v2 da área
        self.assertTrue(self.m.conferir_abertura(self.raiz, "caso-real", self.area)["ok"])

    def test_managed_settings_presentes_vao_ao_relatorio_com_o_hash(self):
        gerenciadas = self.base / "claude-code-gerenciado"
        gerenciadas.mkdir()
        (gerenciadas / "managed-settings.json").write_text('{"permissions": {}}', encoding="utf-8")
        rel = self.instalar()
        esperado = self.m.sha256_arvore(gerenciadas, pastas_ignoradas=(), sufixos_ignorados=())
        self.assertEqual(rel["gerenciadas"]["sha256"], esperado)
        self.assertTrue(any("managed settings" in a and esperado in a for a in rel["avisos"]), rel["avisos"])

    def test_agentes_nas_managed_settings_recusam_o_preparo(self):
        """Revisão de segurança da 1.7.10.2, F1: um agente das managed settings toma o lugar do embutido de mesmo
        nome, e o guarda das ferramentas confere o tipo pelo nome: o preparo recusa e não grava nada."""
        agentes = self.base / "claude-code-gerenciado" / ".claude" / "agents"
        agentes.mkdir(parents=True)
        (agentes / "gp.md").write_text("---\nname: general-purpose\n---\nficticio\n", encoding="utf-8")
        r = instalar(self.skill, self.raiz, self.base, "caso-real", self.claude)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(".claude/agents existe", r.stdout + r.stderr)
        self.assertFalse((self.area / "settings.wsl.json").exists())

    def test_projeto_fora_da_forma_do_kit_nao_ganha_area(self):
        (self.raiz / "projects" / "caso_real").mkdir()
        r = instalar(self.skill, self.raiz, self.base, "caso_real", self.claude)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("forma do kit", r.stdout)
        self.assertFalse((self.base / "area").exists())

    def plugin(self, nome="caso-real-revisor", extras=()) -> tuple[Path, str]:
        pasta = self.proj / "plugins-candidatos" / nome
        (pasta / ".claude-plugin").mkdir(parents=True)
        (pasta / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": nome, "version": "0.1.0"}),
                                                               encoding="utf-8")
        (pasta / "skills" / "revisor").mkdir(parents=True)
        (pasta / "skills" / "revisor" / "SKILL.md").write_text("---\nname: revisor\ndescription: ensaio\n---\nx\n",
                                                                encoding="utf-8")
        (pasta / "agents").mkdir()
        (pasta / "agents" / "leitor.md").write_text("---\nname: leitor\n---\ny\n", encoding="utf-8")
        for rel, texto in extras:
            (pasta / rel).parent.mkdir(parents=True, exist_ok=True)
            (pasta / rel).write_text(texto, encoding="utf-8")
        manifesto = self.m.manifesto_de_arvore(pasta, pastas_ignoradas=(), sufixos_ignorados=())
        return pasta, self.m.sha256_do_plugin(manifesto)  # a receita do manifesto da ficha (uma função só)

    def test_plugin_conferido_e_copiado(self):
        self.aprovar_canario()  # 1.7.10 (contratos, §0): sem o canário aprovado, a ficha não vale
        _pasta, sha_manifesto = self.plugin()
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 1, plugins=[
            {"nome": "caso-real-revisor", "origem": "plugins-candidatos/caso-real-revisor",
             "manifesto_sha256": sha_manifesto}]))
        self.instalar()
        copia = self.area / "plugins" / "caso-real-revisor"
        self.assertTrue((copia / "skills" / "revisor" / "SKILL.md").is_file())
        self.assertIn("PLUGINS='caso-real-revisor'", (self.base / "bin" / "abrir-fundacao-caso-real").read_text(
            encoding="utf-8"))
        self.assertEqual(self.m.conferir_abertura(self.raiz, "caso-real", self.area)["problemas"], [])

    def test_plugin_fora_da_lista_ou_com_manifesto_diferente_recusa(self):
        self.aprovar_canario()  # 1.7.10 (contratos, §0): sem o canário aprovado, a ficha (e o plugin) nem é aplicada
        casos = {"hook": (("hooks/hooks.json", "{}"),), "script": (("skills/revisor/roda.py", "print(1)\n"),),
                 "comando com !": (("commands/c.md", "!`curl exemplo.invalid`\n"),)}
        for n, (nome, extras) in enumerate(casos.items()):
            with self.subTest(nome):
                _pasta, sha_manifesto = self.plugin(f"caso-real-p{n}", extras)
                caixa = self.raiz / ".claude" / "projetos" / "caso-real" / "ficha"
                shutil.rmtree(caixa, ignore_errors=True)
                gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 1, plugins=[
                    {"nome": f"caso-real-p{n}", "origem": f"plugins-candidatos/caso-real-p{n}",
                     "manifesto_sha256": sha_manifesto}]))
                r = instalar(self.skill, self.raiz, self.base, "caso-real", self.claude)
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertIn("1.7.11", r.stdout)
        _pasta, _sha = self.plugin("caso-real-outro")
        shutil.rmtree(self.raiz / ".claude" / "projetos" / "caso-real" / "ficha")
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 1, plugins=[
            {"nome": "caso-real-outro", "origem": "plugins-candidatos/caso-real-outro", "manifesto_sha256": "0" * 64}]))
        r = instalar(self.skill, self.raiz, self.base, "caso-real", self.claude)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("manifesto", r.stdout)

    def test_plugin_com_frontmatter_disfarcado_recusa(self):
        """Revisão do lote 2: as quatro formas de pôr hooks no frontmatter de um agente que a conferência antiga
        deixava passar (um '---' dentro de um valor, chave entre aspas, BOM e mapa em linha) param o preparo."""
        self.aprovar_canario()
        formas = {"traço triplo no valor": "---\ndescription: a --- b\nhooks:\n  Stop: []\n---\nx\n",
                  "chave entre aspas": '---\nname: x\n"hooks": {"Stop": []}\n---\nx\n',
                  "BOM": "\ufeff---\nname: x\nhooks: []\n---\nx\n",
                  "mapa em linha": "---\nname: x\nconfig: {hooks: {Stop: []}}\n---\nx\n"}
        caixa = self.raiz / ".claude" / "projetos" / "caso-real" / "ficha"
        for n, (nome, texto) in enumerate(formas.items()):
            with self.subTest(nome):
                _pasta, sha_manifesto = self.plugin(f"caso-real-f{n}", (("agents/disfarce.md", texto),))
                shutil.rmtree(caixa, ignore_errors=True)
                gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 1, plugins=[
                    {"nome": f"caso-real-f{n}", "origem": f"plugins-candidatos/caso-real-f{n}",
                     "manifesto_sha256": sha_manifesto}]))
                r = instalar(self.skill, self.raiz, self.base, "caso-real", self.claude)
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertIn("agents/disfarce.md", r.stdout)
                self.assertFalse((self.area / "plugins" / f"caso-real-f{n}").exists())

    def test_plugin_com_ligacao_recusa(self):
        self.aprovar_canario()  # 1.7.10 (contratos, §0): sem o canário aprovado, a ficha (e o plugin) nem é aplicada
        pasta, _sha = self.plugin("caso-real-ligado")
        (pasta / "agents" / "fora.md").symlink_to(self.raiz / "RETOMADA.md")
        manifesto_sha = "1" * 64
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 1, plugins=[
            {"nome": "caso-real-ligado", "origem": "plugins-candidatos/caso-real-ligado",
             "manifesto_sha256": manifesto_sha}]))
        r = instalar(self.skill, self.raiz, self.base, "caso-real", self.claude)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("ligação", r.stdout)


@unittest.skipUnless(LINUX, "a conferência do lançador lê a área instalada, só no Linux")
class ConferirAbertura(_Base):
    def setUp(self):
        super().setUp()
        self.aprovar_canario()  # 1.7.10 (contratos, §0): a ficha (e a vigência que o lançador relê) só vale com ele
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 1, vigencia_ate="2999-12-31"))
        self.instalar()

    def conferir(self, **kw):
        return self.m.conferir_abertura(self.raiz, "caso-real", self.area, **kw)

    def test_instalado_confere(self):
        res = self.conferir()
        self.assertTrue(res["ok"], res)

    def test_cada_arquivo_fixado_que_muda_e_acusado(self):
        hashes = json.loads((self.area / "hashes.json").read_text(encoding="utf-8"))
        copia = Path(hashes["arvores"]["skill"]["caminho"])
        alvos = [self.area / "settings.wsl.json", self.area / "porteiro.json", self.area / "mcp.json",
                 self.area / "aberturas.json", self.area / "ficha" / "ficha-v1.json",
                 self.raiz / ".claude" / "hooks" / "guarda_ferramentas.py",
                 self.base / "area" / "claude" / "2.1.302" / "claude", copia / "assets" / "host" / "wsl" / "porteiro.py",
                 self.raiz / "fundacao" / "__init__.py"]
        for alvo in alvos:
            with self.subTest(alvo=alvo.name):
                modo = stat.S_IMODE(alvo.stat().st_mode)
                os.chmod(alvo, 0o644)
                original = alvo.read_bytes()
                alvo.write_bytes(original + b"\n")
                res = self.conferir()
                alvo.write_bytes(original)
                os.chmod(alvo, modo)
                self.assertFalse(res["ok"], alvo)
        self.assertTrue(self.conferir()["ok"])

    def test_ficha_vencida_recusa(self):
        self.assertTrue(self.conferir(hoje=date(2999, 12, 31))["ok"])
        res = self.conferir(hoje=date(3000, 1, 1))
        self.assertFalse(res["ok"])
        self.assertTrue(any("venceu" in p for p in res["problemas"]), res)

    def test_trava_de_manutencao_recusa(self):
        (self.raiz / "state").mkdir()
        (self.raiz / "state" / "manutencao.json").write_text("{}", encoding="utf-8")
        res = self.conferir()
        self.assertTrue(any("manutenção" in p for p in res["problemas"]), res)
        (self.raiz / "state" / "manutencao.json").unlink()
        self.assertTrue(self.conferir()["ok"])

    def test_projeto_criado_depois_recusa(self):
        (self.raiz / "projects" / "lab-novo").mkdir()
        res = self.conferir()
        self.assertTrue(any("lab-novo" in p for p in res["problemas"]), res)

    def test_projeto_novo_recusa_com_mensagem_simples_e_o_comando_pronto(self):
        """1.7.11 (C25): a recusa continua (os perfis dos outros ainda não negam a pasta do novo), mas é uma mensagem só,
        em português simples, que diz qual projeto falta preparar e traz o comando do preparar-wsl.sh com a raiz, o
        titular, a pasta do Windows e o Claude Code fixado, lidos da área instalada."""
        (self.raiz / "projects" / "lab-novo").mkdir()
        res = self.conferir()
        self.assertFalse(res["ok"])
        self.assertEqual(len(res["problemas"]), 1, res)
        texto = res["problemas"][0]
        self.assertIn("o projeto lab-novo ainda não foi preparado no Ubuntu", texto)
        self.assertIn("terminal do Ubuntu", texto)
        comando = texto.splitlines()[-1]
        hashes = json.loads((self.area / "hashes.json").read_text(encoding="utf-8"))
        self.assertIn("preparar-wsl.sh", comando)
        self.assertIn(f"--raiz {shlex.quote(hashes['raiz'])}", comando)
        self.assertIn("--projeto caso-real --projeto lab-novo --titular", comando)  # os preparados e o que falta
        self.assertIn(f"--claude-versao {hashes['claude']['versao']} --claude-sha256 {hashes['claude']['sha256']}",
                      comando)
        # Nenhum marcador sem preencher produzido pelo código (o caminho de ensaio pode ter `<usuario>`: não conta).
        for marcador in ("<pasta da skill instalada>", "<pasta da fundação", "<sua pasta do Windows", "<seu nome de titular>",
                         "<versão do Claude Code>", "<hash do manifesto assinado>"):
            self.assertNotIn(marcador, comando)
        # Preparado o projeto novo (a área dele existe), o perfil deste continua anterior: o texto muda, a recusa fica.
        (self.base / "area" / "projetos" / "lab-novo").mkdir()
        self.assertIn("o perfil desta sessão é anterior ao preparo de lab-novo", self.conferir()["problemas"][0])

    def test_configuracoes_do_projeto(self):
        pasta = self.proj / ".claude"
        pasta.mkdir()
        local = pasta / "settings.local.json"
        aceito = {"permissions": {"allow": ["Bash(npm test:*)", "Read(src/**)"]}}
        local.write_text(json.dumps(aceito), encoding="utf-8")
        self.assertTrue(self.conferir()["ok"])
        recusados = {"webfetch": {"permissions": {"allow": ["WebFetch(domain:exemplo.invalid)"]}},
                     "mcp": {"permissions": {"allow": ["mcp__servidor__ferramenta"]}},
                     "curinga amplo": {"permissions": {"allow": ["Bash(*)"]}},
                     "ferramenta sem argumento": {"permissions": {"allow": ["Bash"]}},
                     "fora do projeto": {"permissions": {"allow": ["Edit(//mnt/e/outro/**)"]}},
                     "casa": {"permissions": {"allow": ["Read(~/.ssh/**)"]}},
                     "chave a mais": {"permissions": {"allow": []}, "hooks": {}},
                     "negação": {"permissions": {"allow": [], "deny": []}}}
        for nome, dados in recusados.items():
            with self.subTest(nome):
                local.write_text(json.dumps(dados), encoding="utf-8")
                res = self.conferir()
                self.assertFalse(res["ok"], nome)
                self.assertTrue(any("mkdir -p" in p and "mv " in p for p in res["problemas"]), res)
        local.write_text(json.dumps(aceito), encoding="utf-8")
        (pasta / "settings.json").write_text("{}", encoding="utf-8")
        self.assertFalse(self.conferir()["ok"])

    def test_mcp_e_claude_local_do_projeto(self):
        for nome in (".mcp.json", "CLAUDE.local.md"):
            with self.subTest(nome):
                arquivo = self.proj / nome
                arquivo.write_bytes(b"")
                res = self.conferir(limpar=True)
                self.assertTrue(res["ok"], res)
                self.assertFalse(arquivo.exists())  # marcador de 0 byte: limpo
                arquivo.write_text("{}", encoding="utf-8")
                self.assertFalse(self.conferir()["ok"])
                arquivo.unlink()

    def test_mcp_json_em_pasta_acima_do_projeto_recusa(self):
        """F4 da revisão da 1.7.11: sem o --strict-mcp-config o Claude Code lê o .mcp.json de cada pasta acima da de
        trabalho. Na raiz, em projects/ e numa pasta intermediária acima da raiz (de qualquer tamanho, ou ligação), a
        abertura é recusada com o arquivo achado e o titular como quem o tira; sem eles, abre."""
        self.assertTrue(self.conferir()["ok"])
        for pasta in (self.raiz, self.raiz / "projects", self.base):
            for nome, criar in (("com conteúdo", lambda a: a.write_text('{"mcpServers": {}}', encoding="utf-8")),
                                ("de 0 byte", lambda a: a.write_bytes(b"")),
                                ("ligação", lambda a: a.symlink_to(self.raiz / "RETOMADA.md"))):
                with self.subTest(pasta=pasta.name, tipo=nome):
                    arquivo = pasta / ".mcp.json"
                    criar(arquivo)
                    res = self.conferir()
                    arquivo.unlink()
                    self.assertFalse(res["ok"], res)
                    achou = [p for p in res["problemas"] if arquivo.as_posix() in p]
                    self.assertEqual(len(achou), 1, res)
                    self.assertIn("titular", achou[0])
                    self.assertIn("mv -- ", achou[0])
        self.assertTrue(self.conferir()["ok"])

    def test_skill_ou_agente_aninhado_plantado_depois_do_preparo_recusa(self):
        """F8 da revisão final da 1.7.11: o perfil só nega o que o registro tinha no preparo; a abertura refaz o inventário
        e recusa a skill ou o agente que a sessão plantou depois, com o comando pronto do registrar-projeto. Registrado
        (e o preparo refeito), a abertura deixa de acusar; nome que o registro não aceita pede neutralizar o arquivo."""
        def acusados():
            return [p for p in self.conferir()["problemas"] if "aninhad" in p]

        def plantar(rel, texto):
            alvo = self.proj / rel
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text(texto, encoding="utf-8")
        self.assertTrue(self.conferir()["ok"])
        plantar("outputs/x/.claude/skills/s/SKILL.md", "---\nname: s\ndescription: d\n---\ncorpo\n")
        res = self.conferir()
        self.assertFalse(res["ok"], res)
        achou = acusados()
        self.assertEqual(len(achou), 1, res)
        for trecho in ("skill s", "registrar-projeto", "--negar-skill 's'", "--projeto 'caso-real'", "abertura"):
            self.assertIn(trecho, achou[0])
        plantar("outputs/x/.claude/agents/plantado.md", "---\nname: plantado\ndescription: d\ntools: Read\n---\n")
        self.assertIn("--negar-agente 'plantado'", acusados()[0])
        origem = self.base / "origem-registrada"
        origem.mkdir()
        self.m.registrar_projeto(self.raiz, "caso-real", [str(origem)], negar=["s"], negar_agente=["plantado"])
        self.assertEqual(acusados(), [])  # registrado: o nome não falta mais
        plantar("outputs/y/.claude/agents/general-purpose.md", "---\nname: general-purpose\ndescription: d\n---\n")
        achou = acusados()  # embutido: o registro o recusa, e a abertura pede para neutralizar o arquivo
        self.assertEqual(len(achou), 1, achou)
        self.assertIn("neutralize", achou[0])
        self.assertIn("outputs/y/.claude/agents/general-purpose.md", achou[0])
        self.assertNotIn("--negar-agente 'general-purpose'", achou[0])  # a forma real do comando (shlex)
        self.assertNotIn("general-purpose'", achou[0].split("registrar-projeto", 1)[-1])

    def test_inventario_parcial_das_aninhadas_recusa_com_a_ferramenta_agent_e_so_avisa_sem_ela(self):
        """F8, o que faltava (3ª passada): o inventário parcial (pasta de nome ignorado) com a ferramenta Agent aberta no perfil
        RECUSA a abertura; sem a ferramenta Agent no perfil, continua só aviso."""
        (self.proj / "node_modules").mkdir()
        (self.proj / "node_modules" / "x.txt").write_text("x\n", encoding="utf-8")  # pasta pulada: inventário parcial
        arquivo = self.area / "hashes.json"
        hashes = json.loads(arquivo.read_text(encoding="utf-8"))
        self.assertIn("Agent", hashes["ferramentas"].split(","))
        res = self.conferir()
        achou = [p for p in res["problemas"] if "parcial" in p]
        self.assertEqual(len(achou), 1, res)
        self.assertFalse(res["ok"], res)
        self.assertIn("ferramenta Agent", achou[0])
        self.assertEqual([a for a in res["avisos"] if "parcial" in a], [])  # não repete como aviso
        hashes["ferramentas"] = ",".join(f for f in hashes["ferramentas"].split(",") if f != "Agent")
        arquivo.write_text(json.dumps(hashes), encoding="utf-8")
        res = self.conferir()
        self.assertEqual([p for p in res["problemas"] if "aninhad" in p or "parcial" in p], [])
        self.assertTrue([a for a in res["avisos"] if "parcial" in a], res["avisos"])

    def test_marcadores_de_zero_byte(self):
        (self.proj / ".bashrc").write_bytes(b"")
        (self.proj / ".env").write_bytes(b"")
        res = self.conferir()
        self.assertTrue(res["ok"], res)
        self.assertTrue((self.proj / ".bashrc").exists())  # sem --limpar, só aponta
        res = self.conferir(limpar=True)
        self.assertEqual(sorted(res["limpos"]), [".bashrc", ".env"])
        self.assertFalse((self.proj / ".bashrc").exists())
        (self.proj / ".env").write_text("CHAVE_DE_ENSAIO_FICTICIA\n", encoding="utf-8")
        self.assertTrue(self.conferir(limpar=True)["ok"])  # .env com conteúdo é do projeto: fica e não trava
        self.assertTrue((self.proj / ".env").exists())
        (self.proj / ".gitconfig").write_text("[core]\n", encoding="utf-8")
        self.assertFalse(self.conferir()["ok"])  # de shell e git com conteúdo: não abre
        (self.proj / ".gitconfig").unlink()
        (self.proj / ".gitconfig").symlink_to(self.raiz / "RETOMADA.md")
        self.assertFalse(self.conferir()["ok"])
        (self.proj / ".gitconfig").unlink()
        (self.proj / ".vscode").mkdir()
        self.assertIn(".vscode/", self.conferir(limpar=True)["limpos"])
        (self.proj / ".vscode").mkdir()
        (self.proj / ".vscode" / "settings.json").write_text("{}", encoding="utf-8")
        res = self.conferir()
        self.assertTrue(res["ok"])
        self.assertTrue(any(".vscode" in a for a in res["avisos"]))

    def test_marcadores_so_de_limpeza(self):
        """As sondas viram o sandbox deixar .npmrc e .yarnrc* de 0 byte: com 0 byte saem; com conteúdo são do projeto
        (ficam, e a sessão abre)."""
        (self.proj / ".npmrc").write_bytes(b"")
        (self.proj / ".yarnrc").write_bytes(b"")
        (self.proj / ".yarnrc.yml").write_text("nodeLinker: node-modules\n", encoding="utf-8")
        res = self.conferir(limpar=True)
        self.assertTrue(res["ok"], res)
        self.assertEqual(sorted(n for n in res["limpos"] if n.startswith((".npm", ".yarn"))), [".npmrc", ".yarnrc"])
        self.assertFalse((self.proj / ".npmrc").exists())
        self.assertTrue((self.proj / ".yarnrc.yml").exists())
        self.assertEqual(self.m.limpar_marcadores(self.raiz, "caso-real", self.area)["problemas"], [])

    def test_marcadores_de_limpeza_da_1_7_11(self):
        """Os nomes de 0 byte do canário de 02/11 (.env, bunfig.toml, package*.json, pnpm-lock.yaml, yarn.lock) saem; com
        conteúdo ficam; outro arquivo de 0 byte (README.md) não está na lista e fica."""
        nomes = (".env", "bunfig.toml", "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock")
        for nome in nomes:
            (self.proj / nome).write_bytes(b"")
        (self.proj / "README.md").write_bytes(b"")
        res = self.m.limpar_marcadores(self.raiz, "caso-real", self.area)
        self.assertEqual(sorted(n for n in res["limpos"] if n in nomes), sorted(nomes))
        self.assertEqual(res["problemas"], [])
        self.assertFalse(any((self.proj / n).exists() for n in nomes))
        self.assertTrue((self.proj / "README.md").exists())
        (self.proj / "package.json").write_text("{}\n", encoding="utf-8")
        self.assertEqual(self.m.limpar_marcadores(self.raiz, "caso-real", self.area)["problemas"], [])
        self.assertTrue((self.proj / "package.json").exists())

    def test_pyc_plantado_no_kit_da_raiz_e_acusado(self):
        (self.raiz / "fundacao" / "plantado.pyc").write_bytes(b"\x00bytecode de ensaio")
        res = self.conferir()
        self.assertFalse(res["ok"])
        self.assertTrue(any("árvore kit" in p for p in res["problemas"]), res)

    def test_managed_settings_que_aparecem_ou_mudam_recusam(self):
        """DESENHO §9: managed settings ficam acima do perfil e, no WSL, /etc/claude-code pode ser gravável pelo
        usuário. Os que aparecem depois do preparo não abrem; os que existiam ficam fixados pelo SHA-256."""
        gerenciadas = self.base / "claude-code-gerenciado"
        gerenciadas.mkdir()
        (gerenciadas / "managed-settings.json").write_text('{"sandbox": {"enabled": false}}', encoding="utf-8")
        res = self.conferir()
        self.assertTrue(any("managed settings" in p for p in res["problemas"]), res)
        self.instalar()  # o titular conferiu e preparou de novo: agora fixado
        self.assertTrue(self.conferir()["ok"])
        (gerenciadas / "managed-settings.json").write_text('{"hooks": {}}', encoding="utf-8")
        self.assertFalse(self.conferir()["ok"])

    def test_hashes_ausente_recusa(self):
        os.unlink(self.area / "hashes.json")
        res = self.conferir()
        self.assertFalse(res["ok"])
        self.assertIn("hashes.json", res["problemas"][0])

    def regravar_hashes(self, mudar) -> None:
        """Muda o hashes.json da área (na área root, só o preparo grava; aqui, o ensaio faz o papel do preparo)."""
        arquivo = self.area / "hashes.json"
        modo = stat.S_IMODE(arquivo.stat().st_mode)
        os.chmod(arquivo, 0o644)
        hashes = json.loads(arquivo.read_text(encoding="utf-8"))
        mudar(hashes)
        arquivo.write_text(json.dumps(hashes), encoding="utf-8")
        os.chmod(arquivo, modo)

    def conferir_lendo_da_raiz(self) -> tuple[dict, list]:
        """A conferência com a pasta atual na raiz (o terminal do titular pode estar em qualquer pasta) e cada leitura
        do caminho conferido anotada."""
        from unittest import mock
        copia = self.m._carregar_script("copia_segura")
        original, lidos = copia.hash_conferido, []

        def espiao(caminho, *args, **kw):
            lidos.append(Path(os.path.abspath(caminho)).as_posix())
            return original(caminho, *args, **kw)

        antes = os.getcwd()
        os.chdir(self.raiz)
        try:
            with mock.patch.object(copia, "hash_conferido", espiao):
                res = self.conferir()
        finally:
            os.chdir(antes)
        return res, lidos

    def proibidos(self, lidos: list) -> list:
        fora = ((self.raiz / "state").as_posix() + "/", (self.raiz / "projects" / "lab-a").as_posix() + "/")
        return [l for l in lidos if l.startswith(fora)]

    def test_sem_filtro_seccomp_a_pasta_atual_nao_e_percorrida(self):
        """Reconferência do lote 2: sem o filtro, o hashes.json não tem 'filtro', e a árvore de '' era a pasta atual
        do titular (até 5000 arquivos a cada abertura, state/ e outros projetos inclusive). Agora só o aviso."""
        self.regravar_hashes(lambda h: h.update(seccomp={"instalado": False, "motivo": "ensaio"}))
        (self.raiz / "state").mkdir()
        (self.raiz / "state" / "x.sqlite").write_bytes(b"banco de ensaio")
        (self.raiz / "projects" / "lab-a" / "y.md").write_text("de outro projeto\n", encoding="utf-8")
        res, lidos = self.conferir_lendo_da_raiz()
        self.assertTrue(res["ok"], res)
        self.assertTrue(any("sockets sem filtro" in a for a in res["avisos"]), res["avisos"])
        self.assertTrue(lidos)  # o espião vê as leituras (os arquivos fixados da área)
        self.assertEqual(self.proibidos(lidos), [])
        self.assertFalse([l for l in lidos if l.startswith(self.raiz.as_posix() + "/") and "/.claude/hooks/" not in l],
                         lidos)  # da raiz, só os hooks fixados
        # o filtro "instalado" com o caminho vazio (hashes.json fora da forma) também não percorre a pasta atual
        self.regravar_hashes(lambda h: h.update(seccomp={"instalado": True, "filtro": "", "caminho": "",
                                                         "filtro_sha256": "0" * 64, "sha256": "0" * 64}))
        res, lidos = self.conferir_lendo_da_raiz()
        self.assertTrue(any("sockets sem filtro" in a for a in res["avisos"]), res["avisos"])
        self.assertEqual(self.proibidos(lidos), [])

    def test_caminho_vazio_ou_relativo_no_hashes_nao_le_a_pasta_atual(self):
        """Uma árvore sem caminho (ou um arquivo fixado relativo) não é lida da pasta atual: vira problema."""
        (self.raiz / "state").mkdir()
        (self.raiz / "state" / "x.sqlite").write_bytes(b"banco de ensaio")
        mudancas = {"árvore sem caminho": lambda h: h["arvores"]["skill"].pop("caminho"),
                    "kit relativo": lambda h: h["arvores"]["kit"].update(caminho="fundacao"),
                    "arquivo relativo": lambda h: h["arquivos"].update({"state/x.sqlite": "0" * 64})}
        original = (self.area / "hashes.json").read_text(encoding="utf-8")
        for nome, mudar in mudancas.items():
            with self.subTest(nome):
                self.regravar_hashes(mudar)
                res, lidos = self.conferir_lendo_da_raiz()
                self.regravar_hashes(lambda h: h.clear() or h.update(json.loads(original)))
                self.assertFalse(res["ok"], res)
                self.assertEqual(self.proibidos(lidos), [])
        self.assertTrue(self.conferir()["ok"])


class PecasPuras(unittest.TestCase):
    """O que dá para conferir sem a área instalada (também no Windows)."""

    def setUp(self):
        self.m = carregar_preparo()

    def test_regras_aceitas_no_settings_local(self):
        ferramentas = {"Bash", "Read", "Edit", "Write", "Glob", "Grep", "WebFetch"}
        for regra in ("Bash(npm test:*)", "Bash(pytest -q)", "Read(src/**)", "Edit(docs/*.md)"):
            self.assertTrue(self.m._regra_aceita(regra, ferramentas), regra)
        for regra in ("Bash(*)", "Bash", "WebFetch(domain:x.example)", "mcp__a__b", "Edit(/abs/**)",
                      "Read(~/.ssh/**)", "Read(../fora/**)", "Agent(x)", 5, "Read(**)"):
            self.assertFalse(self.m._regra_aceita(regra, ferramentas), regra)

    def test_manifesto_e_o_mesmo_texto_documentado(self):
        base = Path(tempfile.mkdtemp(prefix="manifesto-1710-"))
        try:
            (base / "a").mkdir()
            (base / "a" / "x.md").write_bytes(b"x")
            (base / "y.md").write_bytes(b"yy")
            manifesto = self.m.manifesto_de_arvore(base)
            import hashlib
            texto = "".join(f"{rel}\t{m['bytes']}\t{m['sha256']}\n" for rel, m in sorted(manifesto.items()))
            self.assertEqual(self.m.sha256_manifesto(manifesto), hashlib.sha256(texto.encode()).hexdigest())
            self.assertEqual(sorted(manifesto), ["a/x.md", "y.md"])
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_arvore_de_caminho_vazio_ou_relativo_e_recusada(self):
        """Reconferência do lote 2: a pasta vazia (ou relativa) virava a pasta atual. Recusada antes de ler nada."""
        base = Path(tempfile.mkdtemp(prefix="arvore-relativa-1710-"))
        antes = os.getcwd()
        try:
            (base / "fundacao").mkdir()
            (base / "fundacao" / "x.py").write_bytes(b"x = 1\n")
            os.chdir(base)
            for valor in ("", ".", "fundacao", Path(""), Path("fundacao"), None):
                with self.subTest(valor=valor), self.assertRaises(self.m.EntradaInvalida):
                    self.m.manifesto_de_arvore(valor)
            with self.assertRaises(self.m.EntradaInvalida):
                self.m.sha256_arvore("", pastas_ignoradas=(), sufixos_ignorados=())
            self.assertEqual(sorted(self.m.manifesto_de_arvore(base / "fundacao")), ["x.py"])  # absoluto: lê
        finally:
            os.chdir(antes)
            shutil.rmtree(base, ignore_errors=True)


# ------------------------------------------------------------------------------------------ jaula do Criador (1.7.11, L4)
# O usuário `fundacao-jaula`, os programas de dono root, a sudoers conferida, o `porteiro-jaula.json` da área, o registro no
# hashes.json e a conferência na abertura (DESENHO-JAULA §2.1, §3.4, §7.3 e §7.4). As peças puras e a instalação em pasta de
# ensaio (sem root, com o `visudo` e o `useradd` falsos) rodam em qualquer sistema; o `instalar-projeto` e o lançador, só no
# Linux. Nomes fictícios; o usuário do titular é `dono-da-sessao`.
import copy as _copy  # noqa: E402
import re as _re  # noqa: E402
import subprocess as _subprocess  # noqa: E402
import sys as _sys  # noqa: E402

from apoio import ENV as _ENV, SKILL as _SKILL  # noqa: E402

USUARIO_DO_ENSAIO = "dono-da-sessao"
CLAUDE_DE_ENSAIO = "2.1.302"
RAIZ_DE_EXEMPLO = "/mnt/e/Raiz Exemplo"
SECAO_NAVEGADOR = {"dominios": ["esaj.exemplo.org", "*.tribunal.exemplo.org"], "logins": ["esaj.exemplo.org"],
                   "modos": ["sessao", "login", "captcha"]}


def secao_codex(modos=("exec", "titular"), teto=30, autenticacao="conta_chatgpt") -> list:
    return [{"provedor": "openai-codex", "autenticacao": autenticacao, "modos": list(modos),
             "conteudo_de_terceiros": True, "teto_chamadas_dia": teto,
             "r55": {"plano": "plano-teste", "treinamento_desligado": True, "conferido_em": date.today().isoformat()}}]


def ficha_aplicada(m, **secoes) -> dict:
    """A ficha como `aberturas_da_ficha` a devolve com as seções dadas (o que o preparo grava no aberturas.json)."""
    ab = m.aberturas_fechadas()
    ab.update({"valida": True, "motivo": "ficha de aberturas assinada e vigente", "versao": 1,
               "ficha_id": "ficha-caso-real-v1", "arquivo": "ficha-v1.json"})
    ab.update(_copy.deepcopy(secoes))
    return ab


def gravar_area(base: Path, m, ab: dict, caminhos, projeto="caso-real", usuario=USUARIO_DO_ENSAIO) -> Path:
    """A área do titular como o `instalar-projeto` a deixa, para a ficha dada: aberturas.json, porteiro-jaula.json (só com
    seção de jaula) e hashes.json que os fixa. O `instalar-projeto` só roda no Linux; isto roda em qualquer sistema."""
    pj = m.preparo_jaula()
    area = base / "area" / "projetos" / projeto
    area.mkdir(parents=True, exist_ok=True)
    arquivos = {"aberturas.json": m.texto_json({"schema_version": "fundacao.aberturas_instaladas/1", "projeto": projeto,
                                                **{k: v for k, v in ab.items() if k != "plugins"}, "plugins": [],
                                                "ferramentas": m.ferramentas_do_projeto(ab)})}
    conf = pj.config_do_porteiro(RAIZ_DE_EXEMPLO, projeto, ab, caminhos.programas)
    if conf:
        arquivos["porteiro-jaula.json"] = m.texto_json(conf)
    for nome, texto in arquivos.items():
        (area / nome).write_text(texto, encoding="utf-8", newline="\n")
    hashes = {"schema_version": "fundacao.hashes_projeto/1", "projeto": projeto, "raiz": RAIZ_DE_EXEMPLO,
              "usuario": usuario, "claude": {"versao": CLAUDE_DE_ENSAIO, "sha256": "c" * 64},
              "arquivos": {(area / n).as_posix(): sha(area / n) for n in arquivos}}
    (area / "hashes.json").write_text(m.texto_json(hashes), encoding="utf-8", newline="\n")
    return area


def relatorio_do_ubuntu(m, sudo="passou", **mudancas) -> dict:
    """O relatorio do canario do Ubuntu (`fundacao.ensaio_isolamento/1`) como o `instalar-canario` o deixa em
    `<etc>/canario/<versao>.json`, completo (a regra do kit o aceita): so o veredito da medida M1 (`sudo_na_sessao`) varia."""
    itens = [{"id": ident, "classe": classe, "veredito": "nao_medido" if classe == "informativo" else "passou"}
             for ident, classe in m.SONDAS_DO_CANARIO.items()]
    for item in itens:
        if item["id"] == "sudo_na_sessao":
            item["veredito"] = sudo
    rel = {"schema_version": "fundacao.ensaio_isolamento/1", "data": "2026-10-31T12:00:00Z", "simulado": False,
           "forma": "ext4", "sistema_de_arquivos": "ext4", "claude": {"versao": CLAUDE_DE_ENSAIO, "sha256": "c" * 64},
           "sandbox_ligado": True, "perfil": {"gerado": True}, "temp": {"do_lancador": True}, "itens": itens,
           "conclusao": {"forma": "ext4", "sistema_de_arquivos": "ext4", "confina_comandos": True, "motivo": "ensaio"}}
    rel.update(mudancas)
    return rel


def instalar_relatorio_do_ubuntu(m, caminhos, sudo="passou", **mudancas) -> Path:
    """Grava o relatorio do canario do Ubuntu na area (a pasta `etc` dos caminhos), como o `instalar-canario` faz."""
    destino = Path(caminhos.etc) / "canario" / f"{CLAUDE_DE_ENSAIO}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(relatorio_do_ubuntu(m, sudo, **mudancas)), encoding="utf-8", newline=chr(10))
    return destino


def guardar_resposta_do_canario(caminhos, dados: bytes) -> bytes:
    """O que a entrada fixa faz no modo `canario` (F3): guarda a resposta em `<estado>/<projeto>/canario/<id>.json`. Os testes
    de unidade a gravam a mao, byte a byte igual ao arquivo que o titular entrega; devolve os mesmos bytes."""
    resp = json.loads(dados.decode("utf-8"))
    pasta = Path(caminhos.estado) / resp["projeto"] / "canario"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{resp['id']}.json").write_bytes(dados)
    return dados


class VisudoFalso:
    """O `rodar` de ensaio: guarda o que o preparo pediu e diz o que o `visudo` responderia (o texto conferido fica)."""

    def __init__(self, codigo_do_visudo=0):
        self.codigo, self.chamadas, self.conferidos = codigo_do_visudo, [], []

    def __call__(self, argv, entrada=None):
        self.chamadas.append(list(argv))
        if argv[0].endswith("visudo"):
            self.conferidos.append((argv[-1], Path(argv[-1]).read_text(encoding="utf-8")))
            return (self.codigo, "sudoers: erro de sintaxe de ensaio") if self.codigo else (0, "parsed OK")
        return 0, ""


def fecho_das_dependencias(skill: Path) -> set:
    """Os arquivos que o jaula-entrar, o jaula.py, o proxy e o canário carregam do disco, seguindo cada módulo carregado
    pelo caminho (`_script("x")`, `_carregar("x")`, `_irmao("x")` e `AQUI / "x.py"`)."""
    # chromium-sem-disfarce (L5) não é módulo carregado: é o executable_path do Chromium dentro da caixa, montado por modo.
    # O modelo do config.toml e o pino do binário do Codex (L6) também não são módulos: o jaula.py os lê pelo `AQUI / "x.ext"`.
    achados, pendentes = set(), ["jaula-entrar", "jaula.py", "proxy_lista.py", "canario_jaula.py", "dominios_ficha.py",
                                 "chromium-sem-disfarce", "codex-config.toml", "pins-codex.json"]
    while pendentes:
        nome = pendentes.pop()
        if nome in achados:
            continue
        for pasta in (skill / "assets" / "host" / "wsl", skill / "scripts"):
            if (pasta / nome).is_file():
                achados.add(nome)
                texto = (pasta / nome).read_text(encoding="utf-8")
                novos = _re.findall(r'(?:_script|_carregar|_irmao)\("([a-z_]+)"\)', texto)
                pendentes += [n + ".py" for n in novos]
                pendentes += [n + ".py" for n in _re.findall(r'AQUI / "([a-z_]+)\.py"', texto)]
                break
    return achados


class JaulaPecasPuras(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = carregar_preparo()
        cls.pj = cls.m.preparo_jaula()
        cls.j = cls.pj.jaula()
        cls.programas = f"{cls.j.PROGRAMAS}/{cls.j.VERSAO_JAULA}"

    def ab(self, **secoes):
        return ficha_aplicada(self.m, **secoes)

    def test_modos_e_operacoes_que_cada_secao_abre(self):
        pj = self.pj
        self.assertEqual(pj.modos_da_ficha(self.m.aberturas_fechadas()), [])
        self.assertEqual(pj.modos_da_ficha(self.ab()), [])
        completo = self.ab(navegador=SECAO_NAVEGADOR, outras_llm=secao_codex(autenticacao="chave_api"))
        self.assertEqual(pj.modos_da_ficha(completo), ["navegador", "navegador-janela", "codex-exec", "codex-titular"])
        self.assertEqual(pj.operacoes_da_sessao(completo), {"navegador": {}, "codex": {"teto_chamadas_dia": 30}})
        so_janela = self.ab(navegador={**SECAO_NAVEGADOR, "modos": ["login"]})
        self.assertEqual(pj.modos_da_ficha(so_janela), ["navegador-janela"])
        self.assertEqual(pj.operacoes_da_sessao(so_janela), {})  # a janela é só do titular: nada para a sessão
        so_titular = self.ab(outras_llm=secao_codex(("titular",)))
        self.assertEqual((pj.modos_da_ficha(so_titular), pj.operacoes_da_sessao(so_titular)), (["codex-titular"], {}))
        self.assertEqual(pj.chaves_do_portao(completo, "navegador-janela"),
                         ["navegador-janela:login", "navegador-janela:captcha"])
        self.assertEqual(pj.chaves_do_portao(so_janela, "navegador-janela"), ["navegador-janela:login"])
        self.assertEqual(pj.chaves_do_portao(completo, "codex-exec"), ["codex-exec"])

    def test_f1_o_codex_da_sessao_nao_abre_com_a_conta_do_chatgpt_e_a_janela_do_titular_abre(self):
        """Prova negativa da F1: com `conta_chatgpt`, nem a operacao `codex` da sessao (porteiro) nem a linha `codex-exec` da
        sudoers (relatorio que aprova tudo) existem; o `codex-titular` segue com a conta. Com `chave_api`, o modo abre."""
        pj, j = self.pj, self.j
        conta = self.ab(navegador=SECAO_NAVEGADOR, outras_llm=secao_codex())
        self.assertTrue(pj.codex_exec_fechado_pela_conta(conta))
        self.assertEqual(pj.operacoes_da_sessao(conta), {"navegador": {}})
        conf = pj.config_do_porteiro(RAIZ_DE_EXEMPLO, "caso-real", conta, self.programas)
        self.assertNotIn("codex", conf["operacoes"])
        self.assertNotIn("codex", pj.registro_da_jaula(_SKILL, conta, self.programas)["operacoes"])
        todos = self.relatorio({"navegador": True, "navegador-janela:login": True, "codex-exec": True, "codex-titular": True})
        abertos, fechados = pj.modos_abertos(conta, todos, self.hashes_do_relatorio())
        self.assertEqual(abertos, ["canario", "navegador", "navegador-janela", "codex-titular"])
        self.assertEqual(fechados, {"codex-exec": j.MOTIVO_CODEX_EXEC_COM_CONTA})
        self.assertIn("chave de API do projeto, com teto de gasto", fechados["codex-exec"])
        self.assertIn("abrir-codex-<projeto>", fechados["codex-exec"])
        comandos = pj.comandos_do_canario([{"projeto": "caso-real", "ab": conta, "modos": pj.modos_da_ficha(conta)}],
                                          pj.caminhos_reais(), None, None)
        self.assertNotIn("codex-exec", [c["chave"] for c in comandos])
        so_exec = self.ab(outras_llm=secao_codex(("exec",)))   # a ficha que so pede o exec: nenhuma operacao, nenhuma linha
        self.assertEqual(pj.operacoes_da_sessao(so_exec), {})
        self.assertEqual(pj.modos_abertos(so_exec, todos, self.hashes_do_relatorio())[0], ["canario"])
        api = self.ab(outras_llm=secao_codex(autenticacao="chave_api"))
        self.assertFalse(pj.codex_exec_fechado_pela_conta(api))
        self.assertEqual(pj.operacoes_da_sessao(api), {"codex": {"teto_chamadas_dia": 30}})
        self.assertEqual(pj.modos_abertos(api, todos, self.hashes_do_relatorio())[0], ["canario", "codex-exec", "codex-titular"])

    def test_porteiro_jaula_json_so_com_secao_e_valido_para_o_porteiro(self):
        pj, pjaula = self.pj, self.pj.porteiro_jaula()
        self.assertIsNone(pj.config_do_porteiro(RAIZ_DE_EXEMPLO, "caso-real", self.ab(), self.programas))
        conf = pj.config_do_porteiro(RAIZ_DE_EXEMPLO, "caso-real", self.ab(navegador=SECAO_NAVEGADOR,
                                                                         outras_llm=secao_codex(autenticacao="chave_api")),
                                     self.programas)
        self.assertEqual(conf, {"schema_version": "fundacao.porteiro_jaula/1", "raiz": RAIZ_DE_EXEMPLO,
                                "projeto": "caso-real", "usuario_jaula": "fundacao-jaula",
                                "entrada": f"{self.programas}/jaula-entrar",
                                "operacoes": {"navegador": {}, "codex": {"teto_chamadas_dia": 30}}})
        self.assertIs(pjaula.validar_config(conf), conf)
        so_janela = pj.config_do_porteiro(RAIZ_DE_EXEMPLO, "caso-real",
                                          self.ab(navegador={**SECAO_NAVEGADOR, "modos": ["captcha"]}), self.programas)
        self.assertEqual(so_janela["operacoes"], {})  # existe (a entrada fixa lê a raiz), mas o lançador não sobe nada

    def test_sudoers_uma_linha_por_projeto_e_modo_com_o_argv_inteiro_e_sem_curinga(self):
        pj = self.pj
        pares = [("caso-real", "canario"), ("caso-real", "navegador"), ("outro-caso", "canario"), ("caso-real", "navegador")]
        texto = pj.texto_do_sudoers("dono-da-sessao", self.programas, pares, "nopasswd")
        regras = [l for l in texto.splitlines() if l and not l.startswith("#")]
        self.assertEqual(regras[0], f"Defaults!{self.programas}/jaula-entrar env_reset,!setenv,closefrom=3")
        self.assertEqual(regras[1:], [f"dono-da-sessao ALL=(fundacao-jaula) NOPASSWD: {self.programas}/jaula-entrar {p} {m}"
                                      for p, m in sorted(set(pares))])
        self.assertEqual(pj.problemas_do_texto_do_sudoers(texto, "dono-da-sessao", self.programas), [])
        for c in "*?[]\\":
            self.assertNotIn(c, "".join(regras))
        self.assertEqual(pj.texto_do_sudoers("dono-da-sessao", self.programas, [], "nopasswd"), "")  # sem modo: sem arquivo
        for modo in self.j.MODOS:  # o renderizador nunca produz curinga, para nenhum modo
            t = pj.texto_do_sudoers("dono-da-sessao", self.programas, [("caso-real", modo)], "senha")
            self.assertEqual(pj.problemas_do_texto_do_sudoers(t, "dono-da-sessao", self.programas), [], modo)

    def test_sudoers_com_curinga_ou_fora_do_modelo_e_recusada(self):
        """Prova negativa: o conferidor do texto recusa o que abriria mais que um argv fixo."""
        pj, p = self.pj, self.programas
        bom = pj.texto_do_sudoers("dono-da-sessao", p, [("caso-real", "navegador")], "nopasswd")
        regra = f"dono-da-sessao ALL=(fundacao-jaula) NOPASSWD: {p}/jaula-entrar caso-real navegador"
        ruins = {
            "curinga no projeto": regra.replace("caso-real", "*"), "curinga no modo": regra.replace("navegador", "*"),
            "curinga parcial": regra.replace("caso-real", "caso-*"), "interrogação": regra.replace("navegador", "n?"),
            "ALL no comando": "dono-da-sessao ALL=(fundacao-jaula) NOPASSWD: ALL",
            "ALL como usuário": regra.replace("(fundacao-jaula)", "(ALL)"), "root": regra.replace("(fundacao-jaula)", "(root)"),
            "outro titular": regra.replace("dono-da-sessao", "outro-usuario"),
            "outro programa": regra.replace(f"{p}/jaula-entrar", "/usr/bin/env"),
            "outra pasta": regra.replace(p, "/tmp/jaula"), "argv a mais": regra + " extra",
            "argv sem o modo": regra.rsplit(" ", 1)[0], "modo inventado": regra.replace("navegador", "shell"),
            "dois comandos": regra + f", {p}/jaula-entrar caso-real canario", "continuação": regra + " \\",
            "SETENV": regra.replace("NOPASSWD:", "NOPASSWD: SETENV:"), "negação": regra.replace("NOPASSWD:", "!NOPASSWD:"),
            "Defaults solto": "Defaults !authenticate", "grupo": "%sudo ALL=(ALL:ALL) ALL",
            "projeto com ponto": regra.replace("caso-real", "../x"), "vazio": ""}
        for nome, linha in ruins.items():
            with self.subTest(nome):
                texto = bom + linha + "\n" if nome != "vazio" else "# só comentário\n"
                self.assertTrue(pj.problemas_do_texto_do_sudoers(texto, "dono-da-sessao", p), texto)

    def test_sudoers_com_senha_nao_tem_nopasswd(self):
        t = self.pj.texto_do_sudoers("dono-da-sessao", self.programas, [("caso-real", "canario")], "senha")
        self.assertNotIn("NOPASSWD", "\n".join(l for l in t.splitlines() if not l.startswith("#")))
        self.assertIn("ALL=(fundacao-jaula) " + self.programas, t)
        with self.assertRaises(self.m.EntradaInvalida):
            self.pj.texto_do_sudoers("dono-da-sessao", self.programas, [("caso-real", "canario")], "qualquer")

    def test_caminho_com_caractere_especial_da_sudoers_e_escapado(self):
        pj = self.pj
        programas = "/mnt/e/Raiz de Ensaio/jaula:1/1.7.11"
        t = pj.texto_do_sudoers("dono-da-sessao", programas, [("caso-real", "canario")], "nopasswd")
        self.assertIn("/mnt/e/Raiz\\ de\\ Ensaio/jaula\\:1/1.7.11/jaula-entrar caso-real canario", t)
        self.assertEqual(pj.problemas_do_texto_do_sudoers(t, "dono-da-sessao", programas), [])

    def hashes_do_relatorio(self, **m):
        return {"jaula-entrar": "a" * 64, "proxy_lista.py": "b" * 64, "bwrap": "c" * 64, **m}

    def relatorio(self, aprovados, hashes=None):
        return {"schema_version": self.j.ESQUEMA_RELATORIO_INSTALADO, "hashes": hashes or self.hashes_do_relatorio(),
                "modos": {k: {"aprovado": v} for k, v in aprovados.items()}}

    def test_o_relatorio_decide_que_modos_ganham_linha(self):
        pj = self.pj
        ab = self.ab(navegador=SECAO_NAVEGADOR, outras_llm=secao_codex(autenticacao="chave_api"))
        previstos = self.hashes_do_relatorio()
        sem, motivos = pj.modos_abertos(ab, None, previstos)
        self.assertEqual(sem, ["canario"])  # só o canário, até o titular instalar o relatório
        self.assertEqual(sorted(motivos), ["codex-exec", "codex-titular", "navegador", "navegador-janela"])
        rel = self.relatorio({"navegador": True, "navegador-janela:captcha": True, "codex-exec": False})
        abertos, fechados = pj.modos_abertos(ab, rel, previstos)
        self.assertEqual(abertos, ["canario", "navegador", "navegador-janela"])  # basta uma variante aprovada
        self.assertEqual(sorted(fechados), ["codex-exec", "codex-titular"])
        self.assertIn("não aprovou", fechados["codex-exec"])
        for mudanca in ("jaula-entrar", "proxy_lista.py", "bwrap"):  # outra versão da jaula: nada abre
            mudado = self.hashes_do_relatorio(**{mudanca: "d" * 64})
            abertos, fechados = pj.modos_abertos(ab, self.relatorio({"navegador": True}, mudado), previstos)
            self.assertEqual(abertos, ["canario"], mudanca)
            self.assertIn("outra versão", fechados["navegador"])
        self.assertEqual(pj.modos_abertos(ab, self.relatorio({"navegador": True}), None)[0], ["canario"])  # sem bwrap
        self.assertEqual(pj.modos_abertos(self.ab(), rel, previstos), ([], {}))  # sem seção: nem o canário

    def test_o_relatorio_de_outro_esquema_nao_abre_nada(self):
        ab = self.ab(navegador=SECAO_NAVEGADOR)
        rel = {**self.relatorio({"navegador": True}), "schema_version": "outro/1"}
        self.assertEqual(self.pj.modos_abertos(ab, rel, self.hashes_do_relatorio())[0], ["canario"])

    def test_perfil_nega_a_escrita_nas_respostas_da_fila_da_jaula(self):
        pj = self.pj
        proj = f"{RAIZ_DE_EXEMPLO}/projects/caso-real"
        alvo = f"{proj}/.porteiro/jaula/respostas"
        base = {"permissions": {"deny": ["Read(x)"]}, "sandbox": {"filesystem": {"denyWrite": ["/a"]}}}
        sem = pj.aplicar_jaula_no_perfil(_copy.deepcopy(base), proj, self.ab(navegador={**SECAO_NAVEGADOR, "modos": ["login"]}))
        self.assertEqual(sem, base)  # sem operação da sessão (só janela do titular), o perfil não muda
        com = pj.aplicar_jaula_no_perfil(_copy.deepcopy(base), proj, self.ab(navegador=SECAO_NAVEGADOR))
        self.assertEqual(com["permissions"]["deny"], ["Read(x)", f"Edit(/{alvo}/**)"])
        self.assertEqual(com["sandbox"]["filesystem"]["denyWrite"], ["/a", alvo])
        ab = self.ab(navegador=SECAO_NAVEGADOR)
        self.assertEqual(pj.problemas_do_perfil(com, proj, ab), [])
        self.assertEqual(len(pj.problemas_do_perfil(base, proj, ab)), 2)  # perfil sem as negações: o invariante acusa
        self.assertEqual(pj.problemas_do_perfil(base, proj, self.ab()), [])

    def test_perfil_gerado_para_a_ficha_com_jaula_passa_nos_invariantes(self):
        m = self.m
        ab = self.ab(navegador=SECAO_NAVEGADOR)
        perfil = m.perfil_wsl(raiz=RAIZ_DE_EXEMPLO, projeto="caso-real", perfil_windows="/mnt/c/Users/<usuario>",
                              outros_projetos=["lab-a"], aberturas=ab)
        alvo = f"{RAIZ_DE_EXEMPLO}/projects/caso-real/.porteiro/jaula/respostas"
        self.assertIn(alvo, perfil["sandbox"]["filesystem"]["denyWrite"])
        self.assertIn(f"Edit(/{alvo}/**)", perfil["permissions"]["deny"])
        self.assertEqual(m.invariantes_perfil_wsl(perfil, RAIZ_DE_EXEMPLO, "caso-real", ab), [])
        perfil["sandbox"]["filesystem"]["denyWrite"].remove(alvo)
        self.assertTrue([p for p in m.invariantes_perfil_wsl(perfil, RAIZ_DE_EXEMPLO, "caso-real", ab) if "jaula" in p])
        sem = m.perfil_wsl(raiz=RAIZ_DE_EXEMPLO, projeto="caso-real", perfil_windows="/mnt/c/Users/<usuario>",
                           outros_projetos=["lab-a"], aberturas=self.ab())
        self.assertNotIn(alvo, sem["sandbox"]["filesystem"]["denyWrite"])  # sem seção de jaula, o perfil é o de antes

    def test_a_lista_de_arquivos_instalados_e_o_fecho_do_que_a_jaula_carrega(self):
        """Se um lote novo (L5, L6) fizer a jaula carregar mais um módulo, este teste acusa: o preparo tem de instalá-lo."""
        listados = {Path(rel).name for rel, _ in self.pj.ARQUIVOS_DA_JAULA}
        self.assertEqual(fecho_das_dependencias(_SKILL), listados)
        for rel, modo in self.pj.ARQUIVOS_DA_JAULA:
            self.assertTrue((_SKILL / rel).is_file(), rel)
            self.assertNotIn(b"\r", (_SKILL / rel).read_bytes(), rel)  # CR no shebang quebra o exec
            self.assertEqual(modo, 0o755 if rel.endswith(("jaula-entrar", "chromium-sem-disfarce")) else 0o644, rel)

    def test_os_itens_esperados_do_canario_sao_os_que_o_programa_emite(self):
        """O `instalar-canario-jaula` exige exatamente estes itens: todos aparecem, entre aspas, no canario_jaula.py, e o
        programa não emite id que a lista não tenha (um relatório com item a mais ou a menos é recusado)."""
        texto = (_SKILL / "assets" / "host" / "wsl" / "canario_jaula.py").read_text(encoding="utf-8")
        esperados = set(self.pj.ids_do_canario("codex-exec"))
        for item in esperados:
            self.assertRegex(texto, rf'"{item}"', item)
        emitidos = set(_re.findall(r'(?:item|_recusados)\("([a-z_]+)"', texto))
        emitidos |= set(_re.findall(r'\("(proxy_[a-z]+)"', texto))
        self.assertLessEqual(emitidos, esperados)
        self.assertEqual(len(esperados), 18)   # 1.7.11 L6: mais a sonda M7 do Codex (sandbox_codex)
        self.assertEqual(self.pj.ids_do_canario("navegador-janela"), self.pj.ITENS_DO_CANARIO)

    def test_a_entrada_fixa_e_executavel_no_git(self):
        rel = "fundacao-ia-multiprojetos/assets/host/wsl/jaula-entrar"
        try:
            r = _subprocess.run(["git", "-C", str(_SKILL), "ls-files", "-s", "--", "assets/host/wsl/jaula-entrar"],
                                capture_output=True, text=True, timeout=60)
        except (OSError, _subprocess.SubprocessError):
            self.skipTest("git indisponível")
        if r.returncode != 0 or not r.stdout.strip():
            self.skipTest("a skill não está num repositório git (cópia instalada): o preparo põe o modo 0755 de qualquer jeito")
        self.assertTrue(r.stdout.startswith("100755 "), rel + ": " + r.stdout)
        self.assertEqual(self.pj.ARQUIVOS_DA_JAULA[0], ("assets/host/wsl/jaula-entrar", 0o755))

    def test_registro_no_hashes_e_conferencia_na_abertura(self):
        pj, ab = self.pj, self.ab(navegador=SECAO_NAVEGADOR)
        self.assertIsNone(pj.registro_da_jaula(_SKILL, self.ab(), self.programas))
        reg = pj.registro_da_jaula(_SKILL, ab, self.programas)
        self.assertEqual(set(reg), {"versao", "programas", "arquivos", "modos", "operacoes"})
        self.assertEqual(reg["operacoes"], ["navegador"])
        self.assertEqual(set(reg["arquivos"]), {Path(rel).name for rel, _ in pj.ARQUIVOS_DA_JAULA})
        instalado = dict(reg["arquivos"])

        def sha_de(caminho):
            return instalado.get(Path(caminho).name, "(ausente ou recusado)")
        hashes = {"jaula": reg}
        self.assertEqual(pj.problemas_da_abertura(hashes, sha_de), [])
        self.assertEqual(pj.problemas_da_abertura({}, sha_de), [])  # projeto sem jaula: nada a conferir
        instalado["jaula.py"] = "0" * 64
        problemas = pj.problemas_da_abertura(hashes, sha_de)
        self.assertEqual(len(problemas), 1)
        self.assertIn("jaula.py", problemas[0])
        del instalado["proxy_lista.py"]
        self.assertEqual(len(pj.problemas_da_abertura(hashes, sha_de)), 2)
        for ruim in ({"programas": "relativo", "arquivos": {"a": "b"}}, {"programas": "/x", "arquivos": {}}, "texto", []):
            self.assertTrue(pj.problemas_da_abertura({"jaula": ruim}, sha_de), ruim)

    def test_comandos_do_canario_sao_so_da_ficha_e_cabem_no_pedido_da_jaula(self):
        pj, j = self.pj, self.j
        base = Path(tempfile.mkdtemp(prefix="canario-comandos-")).resolve()
        try:
            caminhos = pj.caminhos_de_ensaio(base / "e", base / "area")
            ab = self.ab(navegador=SECAO_NAVEGADOR, outras_llm=secao_codex(autenticacao="chave_api"))
            cmds = pj.comandos_do_canario([{"projeto": "caso-real", "ab": ab, "modos": pj.modos_da_ficha(ab)}], caminhos,
                                          None, None)
            self.assertEqual([c["chave"] for c in cmds], ["navegador", "navegador-janela:login", "navegador-janela:captcha",
                                                          "codex-exec", "codex-titular"])
            for c in cmds:
                with self.subTest(c["chave"]):
                    self.assertIn(f"/usr/bin/sudo -u fundacao-jaula {caminhos.programas}/jaula-entrar caso-real canario",
                                  c["comando"])
                    self.assertTrue(c["comando"].endswith("> " + c["arquivo"]))
                    corpo = _re.match(r"printf '(.*)' \"\$\(date \+%s\)\" \|", c["comando"]).group(1)
                    pedido = json.loads(corpo.replace("%s", "1760000000"))
                    self.assertEqual(pedido["schema_version"], j.ESQUEMA_PEDIDO)
                    self.assertTrue(j.PEDIDO_ID.fullmatch(pedido["id"]), pedido["id"])
                    self.assertIn(pedido["como"], j.COMO_CANARIO)
                    self.assertEqual(pedido.get("variante"), c["chave"].split(":")[1] if ":" in c["chave"] else None)
                    permitidos = (ab["navegador"]["dominios"] if pedido["como"].startswith("navegador")
                                  else list(j.CODEX_DOMINIOS["chave_api"]))
                    self.assertTrue(set(pedido["dominios"]) <= set(permitidos))
                    # a entrada fixa aceita o pedido (esquema fechado por modo)
                    j.validar_pedido(json.dumps(pedido).encode("utf-8"), "caso-real", "canario")
            # com o relatório instalado e válido, só os modos que faltam
            previstos = {"jaula-entrar": "a" * 64, "proxy_lista.py": "b" * 64, "bwrap": "c" * 64}
            rel = {"hashes": previstos, "modos": {"navegador": {"aprovado": True}, "codex-exec": {"aprovado": False}}}
            faltam = pj.comandos_do_canario([{"projeto": "caso-real", "ab": ab, "modos": pj.modos_da_ficha(ab)}],
                                            caminhos, previstos, rel)
            self.assertEqual([c["chave"] for c in faltam], ["navegador-janela:login", "navegador-janela:captcha",
                                                            "codex-exec", "codex-titular"])
        finally:
            shutil.rmtree(base, ignore_errors=True)


class JaulaInstalacao(unittest.TestCase):
    """O plano e a instalação em pasta de ensaio (sem root), com o `visudo` e o `useradd` falsos."""

    @classmethod
    def setUpClass(cls):
        cls.m = carregar_preparo()
        cls.pj = cls.m.preparo_jaula()
        cls.j = cls.pj.jaula()

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="jaula-instalacao-teste-")).resolve()
        (self.base / "jaula-ensaio").mkdir()
        self.caminhos = self.pj.caminhos_de_ensaio(self.base / "jaula-ensaio", self.base / "area")
        Path(self.caminhos.bwrap).write_bytes(b"bwrap de ensaio\n")
        self.ab = ficha_aplicada(self.m, navegador=SECAO_NAVEGADOR, outras_llm=secao_codex(autenticacao="chave_api"))
        self.area = gravar_area(self.base, self.m, self.ab, self.caminhos)
        instalar_relatorio_do_ubuntu(self.m, self.caminhos)   # F5: a medida M1 passou no canario do Ubuntu (o padrao dos testes)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def plano(self, forma="nopasswd", preparar=False, projetos=("caso-real",), usuario=USUARIO_DO_ENSAIO):
        return self.pj.montar_plano(_SKILL, self.base / "area", list(projetos), usuario, self.caminhos, forma_sudo=forma,
                                    preparar=preparar)

    def instalar(self, plano=None, rodar=None, **kw):
        rodar = rodar or VisudoFalso()
        return self.pj.instalar_jaula(plano or self.plano(), rodar=rodar, **kw), rodar

    def test_sem_secao_de_jaula_nada_e_planejado_e_nada_e_gravado(self):
        gravar_area(self.base, self.m, ficha_aplicada(self.m), self.caminhos, "outro-caso")
        plano = self.plano(projetos=("outro-caso",))
        self.assertFalse(plano["necessaria"])
        self.assertEqual(plano["sem_jaula"], ["outro-caso"])
        self.assertEqual(self.pj.instalar_jaula(plano, rodar=VisudoFalso()), {"acoes": [], "necessaria": False})
        self.assertFalse(Path(self.caminhos.programas).exists())
        self.assertFalse(Path(self.caminhos.sudoers).exists())
        self.assertFalse((self.area.parent / "outro-caso" / "porteiro-jaula.json").exists())
        self.assertIn("nada a instalar", " ".join(self.pj.texto_do_plano(plano)))
        self.assertTrue(self.plano(projetos=("outro-caso",), preparar=True)["necessaria"])  # --preparar-jaula

    def test_projeto_sem_area_ainda_nao_tem_plano_e_o_texto_diz_por_que(self):
        plano = self.plano(projetos=("projeto-novo",))
        self.assertFalse(plano["necessaria"])
        self.assertEqual(plano["sem_area"], ["projeto-novo"])
        self.assertIn("ainda não foi gravada", " ".join(self.pj.texto_do_plano(plano)))

    def test_plano_mostra_o_que_vai_instalar_antes_de_instalar(self):
        plano = self.plano()
        self.assertTrue(plano["necessaria"])
        texto = "\n".join(self.pj.texto_do_plano(plano))
        for trecho in ("fundacao-jaula", "sem shell, sem senha e sem casa", "0700", "jaula-entrar [criar]",
                       "sudoers", "visudo -cf", "NOPASSWD", "medida M1 passou", "caso-real", "canario",
                       "não inclui os downloads do navegador", "cdn.playwright.dev", "--canario-jaula",
                       "não inclui o download do Codex", "instalar-codex-jaula", "rust-v0.166.0", "SHA-256 fixado"):
            self.assertIn(trecho, texto)
        self.assertEqual(plano["pares"], [("caso-real", "canario")])  # sem relatório, só o canário
        self.assertFalse(Path(self.caminhos.programas).exists())  # planejar não grava
        self.assertEqual({a["estado"] for a in plano["arquivos"]}, {"criar"})

    def test_instalacao_de_ensaio_grava_programas_hashes_instalacao_e_sudoers(self):
        res, rodar = self.instalar()
        programas = Path(self.caminhos.programas)
        for rel, modo in self.pj.ARQUIVOS_DA_JAULA:
            instalado = programas / Path(rel).name
            self.assertEqual(sha(instalado), sha(_SKILL / rel), rel)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(instalado.stat().st_mode), modo, rel)
        hashes = json.loads((programas / "hashes.json").read_text(encoding="utf-8"))
        self.assertEqual(hashes["schema_version"], "fundacao.jaula_instalada/1")
        self.assertEqual(hashes["arquivos"], {Path(rel).name: sha(_SKILL / rel) for rel, _ in self.pj.ARQUIVOS_DA_JAULA})
        etc = Path(self.caminhos.etc)
        self.assertEqual(json.loads((etc / "jaula" / "instalacao.json").read_text(encoding="utf-8")),
                         {"schema_version": "fundacao.jaula_instalacao/1", "sudo": "nopasswd"})
        estado = Path(self.caminhos.estado)
        self.assertTrue((estado / "caso-real").is_dir())
        sudoers = Path(self.caminhos.sudoers).read_text(encoding="utf-8")
        self.assertIn(f"{USUARIO_DO_ENSAIO} ALL=(fundacao-jaula) NOPASSWD: ", sudoers)
        self.assertEqual(self.pj.problemas_do_texto_do_sudoers(sudoers, USUARIO_DO_ENSAIO, self.caminhos.programas), [])
        self.assertEqual(len(rodar.conferidos), 1)  # o visudo viu o texto ANTES de ele entrar no lugar
        arq, visto = rodar.conferidos[0]
        self.assertEqual(visto, sudoers)
        self.assertNotEqual(Path(arq), Path(self.caminhos.sudoers))
        self.assertEqual(rodar.chamadas[0][:2], [self.pj.VISUDO, "-cf"])
        self.assertEqual(sorted(p.name for p in Path(self.caminhos.sudoers).parent.iterdir()), ["fundacao-jaula"])

    def test_a_pasta_instalada_carrega_sozinha_sem_a_arvore_da_skill(self):
        """A jaula de dono root não tem `scripts/` nem `assets/` ao lado: tudo o que o jaula.py, o proxy e o canário
        carregam tem de estar na pasta plana instalada (a lista de arquivos é o fecho; aqui ela carrega de verdade)."""
        import importlib.util as iu
        self.instalar()
        programas = Path(self.caminhos.programas)

        def carregar(nome, arquivo):
            spec = iu.spec_from_file_location(nome, programas / arquivo)
            modulo = iu.module_from_spec(spec)
            spec.loader.exec_module(modulo)
            return modulo
        jaula = carregar("_instalada_jaula", "jaula.py")
        self.assertEqual(Path(jaula.AQUI), programas)
        for nome in ("execucao_isolada", "copia_segura", "gravacao_segura", "regras_de_segredo"):
            modulo = jaula._script(nome)
            self.assertEqual(Path(modulo.__file__).parent, programas, nome)  # veio da pasta instalada, não da skill
        carregar("_instalada_proxy", "proxy_lista.py")
        carregar("_instalada_canario", "canario_jaula.py")
        self.assertTrue(Path(jaula.DOM.__file__).parent == programas)

    def test_a_segunda_vez_nada_muda(self):
        self.instalar()
        antes = {str(p): sha(p) for p in self.base.rglob("*") if p.is_file()}
        res, rodar = self.instalar()
        self.assertEqual({a["acao"] for a in res["acoes"]} - {"garantir", "ensaio"}, {"igual"})
        self.assertEqual({str(p): sha(p) for p in self.base.rglob("*") if p.is_file()}, antes)
        self.assertEqual(rodar.chamadas, [])  # sudoers igual: nem chama o visudo

    def test_programa_alterado_e_reposto(self):
        self.instalar()
        alvo = Path(self.caminhos.programas) / "jaula.py"
        alvo.write_bytes(alvo.read_bytes() + b"# adulterado\n")
        res, _ = self.instalar()
        self.assertEqual([a["acao"] for a in res["acoes"] if a["item"] == "programa:jaula.py"], ["atualizar"])
        self.assertEqual(sha(alvo), sha(_SKILL / "assets" / "host" / "wsl" / "jaula.py"))

    def test_visudo_que_recusa_nao_instala_a_sudoers_e_nao_deixa_sobra(self):
        with self.assertRaises(self.m.EntradaInvalida) as ctx:
            self.instalar(rodar=VisudoFalso(codigo_do_visudo=1))
        self.assertIn("visudo recusou", str(ctx.exception))
        self.assertFalse(Path(self.caminhos.sudoers).exists())
        pasta = Path(self.caminhos.sudoers).parent
        self.assertEqual(list(pasta.iterdir()) if pasta.exists() else [], [])  # nem o temporário
        self.instalar()  # e a próxima vez, com o visudo bom, instala
        self.assertTrue(Path(self.caminhos.sudoers).is_file())

    def test_sudoers_existente_nao_e_trocada_se_o_visudo_recusa(self):
        self.instalar()
        antes = Path(self.caminhos.sudoers).read_bytes()
        plano = self.plano(forma="senha")
        with self.assertRaises(self.m.EntradaInvalida):
            self.instalar(plano, rodar=VisudoFalso(codigo_do_visudo=1))
        self.assertEqual(Path(self.caminhos.sudoers).read_bytes(), antes)

    def test_forma_com_senha_vai_para_a_sudoers_e_para_a_instalacao(self):
        self.instalar(self.plano(forma="senha"))
        sudoers = Path(self.caminhos.sudoers).read_text(encoding="utf-8")
        self.assertNotIn("NOPASSWD", "\n".join(l for l in sudoers.splitlines() if not l.startswith("#")))
        instalacao = json.loads((Path(self.caminhos.etc) / "jaula" / "instalacao.json").read_text(encoding="utf-8"))
        self.assertEqual(instalacao["sudo"], "senha")

    def test_f5_o_sudo_sem_senha_so_com_a_medida_m1_aprovada_no_canario_do_ubuntu(self):
        """Sem o item `sudo_na_sessao` = `passou` no relatorio instalado do canario do Ubuntu, a sudoers sai COM senha."""
        m, c = self.m, self.caminhos
        relatorio = Path(c.etc) / "canario" / f"{CLAUDE_DE_ENSAIO}.json"
        plano = self.plano()
        self.assertEqual((plano["sudo"], plano["sudo_pedido"], plano["sudo_motivo"]), ("nopasswd", "nopasswd", None))
        self.assertIn("NOPASSWD", plano["sudoers"])
        sem_item = relatorio_do_ubuntu(m)
        sem_item["itens"] = [i for i in sem_item["itens"] if i["id"] != "sudo_na_sessao"]
        casos = {"falhou": lambda: instalar_relatorio_do_ubuntu(m, c, "falhou"),
                 "nao medida": lambda: instalar_relatorio_do_ubuntu(m, c, "nao_medido"),
                 "sem o item": lambda: relatorio.write_text(json.dumps(sem_item), encoding="utf-8"),
                 "so o item, sem a forma de um ensaio real": lambda: relatorio.write_text(json.dumps(
                     {"itens": [{"id": "sudo_na_sessao", "veredito": "passou"}]}), encoding="utf-8"),
                 "ilegivel": lambda: relatorio.write_text("{", encoding="utf-8"),
                 "ausente": lambda: relatorio.unlink()}
        for nome, preparar in casos.items():
            preparar()
            with self.subTest(nome):
                plano = self.plano()
                self.assertEqual((plano["sudo"], plano["sudo_pedido"]), ("senha", "nopasswd"))
                self.assertIn("medida M1 (sudo_na_sessao) não passou", plano["sudo_motivo"])
                self.assertIn("caso-real", plano["sudo_motivo"])
                self.assertNotIn("NOPASSWD", "\n".join(l for l in plano["sudoers"].splitlines() if not l.startswith("#")))
                self.assertIn("com senha (a medida M1", "\n".join(self.pj.texto_do_plano(plano)))
        self.instalar()   # e a instalacao grava a forma efetiva
        instalacao = json.loads((Path(c.etc) / "jaula" / "instalacao.json").read_text(encoding="utf-8"))
        self.assertEqual(instalacao["sudo"], "senha")
        self.assertNotIn("NOPASSWD", "\n".join(l for l in Path(c.sudoers).read_text(encoding="utf-8").splitlines()
                                              if not l.startswith("#")))
        instalar_relatorio_do_ubuntu(m, c, "passou")   # medida aprovada: volta ao sem senha
        self.assertEqual(self.plano()["sudo"], "nopasswd")
        forcada = self.plano(forma="senha")   # --sudo-senha continua valendo, com ou sem a medida
        self.assertEqual((forcada["sudo"], forcada["sudo_motivo"]), ("senha", None))
        self.assertIn("pedida com --sudo-senha", "\n".join(self.pj.texto_do_plano(forcada)))
        outra = Path(c.etc) / "canario" / "9.9.9.json"   # relatorio de outra versao do Claude Code nao vale
        relatorio.rename(outra)
        self.assertEqual(self.plano()["sudo"], "senha")
        outra.unlink()
        self.assertEqual(self.plano(preparar=True, projetos=("outro-caso",))["sudo"], "senha")   # sem projeto com prova: senha

    def test_f1_com_a_conta_do_chatgpt_a_sudoers_nao_ganha_a_linha_do_codex_da_sessao(self):
        """A ficha com `conta_chatgpt` e o relatorio que aprova `codex-exec` e `codex-titular`: so o titular ganha linha."""
        ab = ficha_aplicada(self.m, outras_llm=secao_codex())
        gravar_area(self.base, self.m, ab, self.caminhos)
        plano = self.plano()
        rel = {"schema_version": self.j.ESQUEMA_RELATORIO_INSTALADO, "hashes": plano["hashes_previstos"],
               "modos": {"codex-exec": {"aprovado": True}, "codex-titular": {"aprovado": True}}}
        destino = Path(self.caminhos.etc) / self.j.RELATORIO_INSTALADO
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(rel), encoding="utf-8")
        plano = self.plano()
        self.assertEqual(plano["pares"], [("caso-real", "canario"), ("caso-real", "codex-titular")])
        self.assertNotIn("codex-exec", plano["sudoers"].split("Defaults!")[1])
        self.assertEqual(plano["projetos"][0]["fechados"], {"codex-exec": self.j.MOTIVO_CODEX_EXEC_COM_CONTA})
        self.assertEqual(plano["projetos"][0]["operacoes_da_sessao"], [])
        texto = "\n".join(self.pj.texto_do_plano(plano))
        self.assertIn("chave de API do projeto, com teto de gasto", texto)   # o titular lê o que fazer
        conf = json.loads((self.area / "porteiro-jaula.json").read_text(encoding="utf-8"))
        self.assertEqual(conf["operacoes"], {})

    def test_sem_mais_projetos_com_jaula_a_sudoers_sai(self):
        self.instalar()
        self.assertTrue(Path(self.caminhos.sudoers).exists())
        gravar_area(self.base, self.m, ficha_aplicada(self.m), self.caminhos)  # a ficha nova fechou a jaula
        res, _ = self.instalar(self.plano(preparar=True))
        self.assertFalse(Path(self.caminhos.sudoers).exists())
        self.assertIn("remover", [a["acao"] for a in res["acoes"] if a["item"] == "sudoers"])

    def test_simulacao_nao_grava_nada(self):
        antes = {str(p) for p in self.base.rglob("*")}
        res = self.pj.instalar_jaula(self.plano(), simular=True, rodar=VisudoFalso())
        self.assertEqual(res["acoes"][0]["acao"], "simular")
        self.assertEqual({str(p) for p in self.base.rglob("*")}, antes)

    def test_sem_root_e_fora_de_ensaio_recusa(self):
        reais = self.pj.Caminhos(**{**self.caminhos._asdict(), "ensaio": False})
        plano = {**self.plano(), "caminhos": reais._asdict()}
        with self.assertRaises(self.m.EntradaInvalida) as ctx:
            self.pj.instalar_jaula(plano, rodar=VisudoFalso())
        self.assertIn("sudo", str(ctx.exception))
        with self.assertRaises(self.m.EntradaInvalida):  # o ensaio também não roda com root
            self.pj.instalar_jaula(self.plano(), raiz_dono=True, rodar=VisudoFalso())

    def test_binario_que_falta_para_com_o_comando_do_apt(self):
        plano = {**self.plano(), "binarios": [{"caminho": str(self.base / "nao-tem-bwrap"), "pacote": "bubblewrap"}]}
        with self.assertRaises(self.m.EntradaInvalida) as ctx:
            self.pj.instalar_jaula(plano, rodar=VisudoFalso())
        self.assertIn("apt-get install -y bubblewrap", str(ctx.exception))
        self.assertFalse(Path(self.caminhos.programas).exists())
        res = self.pj.instalar_jaula(plano, simular=True, rodar=VisudoFalso())
        self.assertIn("apt-get install -y bubblewrap", res["avisos"][0])

    def test_usuario_ou_entrada_incoerentes_param_o_plano(self):
        with self.assertRaises(self.m.EntradaInvalida) as ctx:
            self.plano(usuario="outro-usuario")
        self.assertIn(USUARIO_DO_ENSAIO, str(ctx.exception))
        for ruim in ("root", "fundacao-jaula", "Maiuscula", "com espaco", ""):
            with self.subTest(ruim), self.assertRaises(self.m.EntradaInvalida):
                self.plano(usuario=ruim)
        outro = self.pj.Caminhos(**{**self.caminhos._asdict(), "programas": self.caminhos.programas + "-x"})
        with self.assertRaises(self.m.EntradaInvalida) as ctx:
            self.pj.montar_plano(_SKILL, self.base / "area", ["caso-real"], USUARIO_DO_ENSAIO, outro)
        self.assertIn("outra entrada fixa", str(ctx.exception))

    def test_area_adulterada_ou_incoerente_para_o_plano(self):
        conf = self.area / "porteiro-jaula.json"
        original = conf.read_bytes()
        conf.write_bytes(original.replace(b'"navegador": {}', b'"navegador": {}, "codex-exec": {}'))
        with self.assertRaises(self.m.EntradaInvalida):  # não bate com o hashes.json
            self.plano()
        conf.write_bytes(original)
        self.plano()
        (self.area / "porteiro-jaula.json").unlink()
        with self.assertRaises(self.m.EntradaInvalida):
            self.plano()

    def test_usuario_da_jaula_e_criado_como_de_sistema_sem_shell(self):
        pj = self.pj
        contas, chamadas = {}, []

        class Conta:
            def __init__(self, uid=991, shell="/usr/sbin/nologin"):
                self.pw_uid, self.pw_gid, self.pw_shell = uid, uid, shell

        def consultar(nome):
            if nome not in contas:
                raise KeyError(nome)
            return contas[nome]

        def rodar(argv, entrada=None):
            chamadas.append(argv)
            contas[argv[-1]] = Conta()
            return 0, ""
        res = pj.garantir_usuario(rodar, consultar)
        self.assertEqual(res, {"acao": "criar", "uid": 991, "gid": 991})
        self.assertEqual(chamadas, [[pj.USERADD, "--system", "--user-group", "--no-create-home", "--home-dir", "/nonexistent",
                                     "--shell", "/usr/sbin/nologin", "fundacao-jaula"]])
        self.assertEqual(pj.garantir_usuario(rodar, consultar)["acao"], "igual")
        self.assertEqual(len(chamadas), 1)
        for conta in (Conta(uid=1000), Conta(uid=0), Conta(shell="/bin/bash")):  # existe, mas não é o usuário de sistema
            contas["fundacao-jaula"] = conta
            with self.subTest(uid=conta.pw_uid, shell=conta.pw_shell), self.assertRaises(self.m.EntradaInvalida):
                pj.garantir_usuario(rodar, consultar)
        contas.clear()
        with self.assertRaises(self.m.EntradaInvalida):
            pj.garantir_usuario(lambda argv, entrada=None: (9, "useradd: falhou"), consultar)

    def test_a_entrada_fixa_confere_a_configuracao_pelo_hashes_do_projeto(self):
        """jaula.carregar_instalacao: o porteiro-jaula.json e o aberturas.json são os que o preparo fixou."""
        j = self.j
        cfg = j.Config(etc=self.caminhos.etc, estado=self.caminhos.estado, programas=self.caminhos.programas, usuario=None)
        raiz, ficha, relatorio = j.carregar_instalacao(cfg, "caso-real", dono=None, hashes=True)
        self.assertEqual((raiz, ficha["projeto"], relatorio), (RAIZ_DE_EXEMPLO, "caso-real", None))
        for nome in ("aberturas.json", "porteiro-jaula.json"):
            alvo = self.area / nome
            original = alvo.read_bytes()
            alvo.write_bytes(original.replace(b"{", b"{ ", 1))  # JSON ainda válido, conteúdo diferente
            with self.subTest(nome), self.assertRaises(j.Recusa) as ctx:
                j.carregar_instalacao(cfg, "caso-real", dono=None, hashes=True)
            self.assertIn("hashes.json", str(ctx.exception))
            alvo.write_bytes(original)
        # sem o hashes.json, ou com o arquivo fora dele, ou de outro projeto
        hashes = self.area / "hashes.json"
        original = hashes.read_bytes()
        for nome, mudanca in {"arquivo fora": lambda d: d["arquivos"].pop(next(iter(d["arquivos"]))),
                              "outro projeto": lambda d: d.update(projeto="outro"),
                              "outro esquema": lambda d: d.update(schema_version="x/1")}.items():
            novo = json.loads(original)
            mudanca(novo)
            hashes.write_text(json.dumps(novo), encoding="utf-8")
            with self.subTest(nome), self.assertRaises(j.Recusa):
                j.carregar_instalacao(cfg, "caso-real", dono=None, hashes=True)
        hashes.unlink()
        with self.assertRaises(j.Recusa):
            j.carregar_instalacao(cfg, "caso-real", dono=None, hashes=True)

    def test_so_o_dono_conferido_liga_a_conferencia_pelo_hashes_por_padrao(self):
        j = self.j
        cfg = j.Config(etc=self.caminhos.etc, estado=self.caminhos.estado, programas=self.caminhos.programas, usuario=None)
        (self.area / "hashes.json").unlink()
        j.carregar_instalacao(cfg, "caso-real", dono=None)  # só os testes de unidade chamam sem a conferência
        if hasattr(os, "geteuid"):
            with self.assertRaises(j.Recusa):
                j.carregar_instalacao(cfg, "caso-real", dono=os.geteuid())  # com o dono conferido, o hashes.json é exigido

    def test_o_pedido_de_canario_da_resposta_inclui_a_versao_da_jaula(self):
        """A resposta do modo canario leva `como`, `variante` e `hashes`: o `instalar-canario-jaula` os exige."""
        texto = (_SKILL / "assets" / "host" / "wsl" / "jaula.py").read_text(encoding="utf-8")
        self.assertIn('resposta["hashes"] = hashes_atuais if hashes_atuais is not None else hashes_da_instalacao(cfg)', texto)
        self.assertIn('resposta["variante"] = variante', texto)


@unittest.skipUnless(LINUX, "o instalar-projeto e o lançador rodam no Linux (a área é do Ubuntu)")
class JaulaNaAreaDoProjeto(_Base):
    """O `instalar-projeto` com ficha de jaula: porteiro-jaula.json, registro no hashes.json, perfil e conferência na abertura."""

    def setUp(self):
        super().setUp()
        for rel, _ in self.m.preparo_jaula().ARQUIVOS_DA_JAULA:  # a cópia de ensaio da skill só tem 3 scripts
            if rel.startswith("scripts/"):
                shutil.copyfile(_SKILL / rel, self.skill / rel)
        self.programas = self.base / "jaula-ensaio" / "programas"
        self.aprovar_canario()

    def instalar_com_jaula(self, **secoes):
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 1, **secoes))
        return self.instalar("--jaula-base", str(self.programas))

    def hashes(self):
        return json.loads((self.area / "hashes.json").read_text(encoding="utf-8"))

    def test_ficha_com_jaula_grava_o_porteiro_jaula_o_registro_e_o_perfil(self):
        rel = self.instalar_com_jaula(navegador=SECAO_NAVEGADOR, outras_llm=secao_codex())
        conf = json.loads((self.area / "porteiro-jaula.json").read_text(encoding="utf-8"))
        self.assertEqual(conf["operacoes"], {"navegador": {}})   # F1: a ficha de hoje so tem a conta: o Codex da sessao fica fechado
        self.assertEqual(conf["entrada"], f"{self.programas.as_posix()}/{self.m.preparo_jaula().jaula().VERSAO_JAULA}/jaula-entrar")
        hashes = self.hashes()
        self.assertEqual(hashes["arquivos"][(self.area / "porteiro-jaula.json").as_posix()], sha(self.area / "porteiro-jaula.json"))
        self.assertEqual(set(hashes["jaula"]["arquivos"]), {Path(r).name for r, _ in self.m.preparo_jaula().ARQUIVOS_DA_JAULA})
        self.assertEqual(hashes["jaula"]["operacoes"], ["navegador"])
        self.assertEqual(rel["jaula"], hashes["jaula"])
        self.assertTrue(any("jaula" in a for a in rel["avisos"]))
        perfil = json.loads((self.area / "settings.wsl.json").read_text(encoding="utf-8"))
        alvo = f"{self.proj.as_posix()}/.porteiro/jaula/respostas"
        self.assertIn(alvo, perfil["sandbox"]["filesystem"]["denyWrite"])
        self.assertIn(f"Edit(/{alvo}/**)", perfil["permissions"]["deny"])
        self.assertEqual(sha(self.raiz / ".claude" / "projetos" / "caso-real" / "porteiro-jaula.json"),
                         sha(self.area / "porteiro-jaula.json"))  # espelho legível
        antes = fotografia(self.base / "area", self.base / "bin")
        self.instalar("--jaula-base", str(self.programas))
        self.assertEqual(fotografia(self.base / "area", self.base / "bin"), antes)  # a segunda vez nada muda

    def test_ficha_sem_secao_de_jaula_nao_grava_nada_de_jaula(self):
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 1, rede={"dominios": ["pypi.org"]}))
        self.instalar()
        self.assertFalse((self.area / "porteiro-jaula.json").exists())
        self.assertNotIn("jaula", self.hashes())
        perfil = json.loads((self.area / "settings.wsl.json").read_text(encoding="utf-8"))
        self.assertFalse([d for d in perfil["permissions"]["deny"] if "jaula" in d])
        self.assertTrue(self.m.conferir_abertura(self.raiz, "caso-real", self.area)["ok"])

    def test_porteiro_jaula_json_antigo_sai_quando_a_ficha_nova_fecha_a_jaula(self):
        self.instalar_com_jaula(navegador=SECAO_NAVEGADOR)
        self.assertTrue((self.area / "porteiro-jaula.json").is_file())
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 2))  # a v2 sem jaula
        rel = self.instalar()
        self.assertFalse((self.area / "porteiro-jaula.json").exists())
        self.assertIn("remover", [a["acao"] for a in rel["acoes"] if a["item"] == "porteiro-jaula.json"])
        self.assertNotIn("jaula", self.hashes())

    def test_a_abertura_exige_a_jaula_instalada_como_o_preparo_fixou(self):
        if not Path("/usr/sbin/visudo").exists():
            self.skipTest("precisa do visudo (/usr/sbin/visudo) para conferir a sudoers de ensaio")
        self.instalar_com_jaula(navegador=SECAO_NAVEGADOR)
        res = self.m.conferir_abertura(self.raiz, "caso-real", self.area)
        self.assertFalse(res["ok"])
        self.assertTrue(any(p.startswith("jaula:") for p in res["problemas"]), res)
        r = _subprocess.run([_sys.executable, "-I", "-B", str(self.skill / "assets" / "host" / "preparo_host.py"),
                             "instalar-jaula", "--raiz", str(self.raiz), "--projeto", "caso-real", "--usuario",
                             self._usuario(), "--area-raiz", str(self.base / "area"), "--ensaio-base",
                             str(self.base / "jaula-ensaio"), "--texto"], capture_output=True, text=True,
                            encoding="utf-8", env=_ENV, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("[criar] programa:jaula-entrar", r.stdout)
        self.assertTrue(self.m.conferir_abertura(self.raiz, "caso-real", self.area)["ok"])
        alvo = self.programas / self.m.preparo_jaula().jaula().VERSAO_JAULA / "jaula.py"
        alvo.write_bytes(alvo.read_bytes() + b"# adulterado\n")
        res = self.m.conferir_abertura(self.raiz, "caso-real", self.area)
        self.assertFalse(res["ok"])
        self.assertTrue(any("jaula.py" in p for p in res["problemas"]), res)

    def _usuario(self) -> str:
        from test_host_projeto_apoio import usuario_atual
        return usuario_atual()

    def test_plano_jaula_pela_linha_de_comando_e_o_codigo_quando_nao_ha_jaula(self):
        base = [_sys.executable, "-I", "-B", str(self.skill / "assets" / "host" / "preparo_host.py"), "plano-jaula",
                "--raiz", str(self.raiz), "--projeto", "caso-real", "--usuario", self._usuario(), "--area-raiz",
                str(self.base / "area"), "--ensaio-base", str(self.base / "jaula-ensaio"), "--texto"]
        self.instalar()
        r = _subprocess.run(base, capture_output=True, text=True, encoding="utf-8", env=_ENV, timeout=120)
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)  # sem seção: a jaula não existe para o projeto
        self.assertIn("nada a instalar", r.stdout)
        self.assertFalse((self.base / "jaula-ensaio" / "programas").exists())
        self.instalar_com_jaula(navegador=SECAO_NAVEGADOR)
        r = _subprocess.run(base, capture_output=True, text=True, encoding="utf-8", env=_ENV, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("sudoers", r.stdout)
        self.assertFalse((self.base / "jaula-ensaio" / "programas").exists())  # planejar não grava


if __name__ == "__main__":
    unittest.main()
