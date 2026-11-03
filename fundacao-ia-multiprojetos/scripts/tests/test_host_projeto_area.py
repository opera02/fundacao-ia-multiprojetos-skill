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


if __name__ == "__main__":
    unittest.main()
