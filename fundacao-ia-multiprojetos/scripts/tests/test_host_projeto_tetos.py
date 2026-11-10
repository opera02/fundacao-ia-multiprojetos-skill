"""Tetos que o preparo do host aplica (1.7.10; contratos do lote 2, §5 e §6; revisão do lote 2).

O preparo é a última conferência antes de o root copiar um plugin para a área confiável e de a ficha virar rede do
perfil: ele aplica de novo, por conta própria, os tetos do validador do kit — na integração, pelo próprio validador do
kit desta cópia da skill, sem réplica (emendas E3/E4; folha da integração, I5). Aqui: o frontmatter de skill, agente ou
comando nas formas que passavam (um `---` dentro de um valor, chave entre aspas, BOM, mapa em linha), os bytes
conferidos presos ao SHA-256 do manifesto (sem janela entre a análise e a cópia), os curingas sobre a terminação de
país e acima de hospedagem compartilhada, o projeto na forma do kit e do porteiro, o filtro seccomp procurado só em
caminhos fixos de dono root, os marcadores de 0 byte só de limpeza e os avisos de honestidade do relatório.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from test_host_projeto_apoio import LINUX, carregar_preparo

FRENTE_LIMPA = "---\nname: revisor\ndescription: lê os autos e resume\ntools: Read, Grep\n---\ncorpo\n"


class FrontmatterDoPlugin(unittest.TestCase):
    def setUp(self):
        self.m = carregar_preparo()

    def problema(self, dados: bytes) -> list:
        """As recusas do preparo (o validador do kit, folha da integração I5) para um plugin de ensaio com um agente com
        estes bytes: a réplica problema_do_markdown saiu; a lista vazia é o "passa" de antes (None)."""
        base = Path(tempfile.mkdtemp(prefix="plugin-frente-1710-"))
        try:
            pasta = base / "plugins-candidatos" / "caso-real-p"
            (pasta / ".claude-plugin").mkdir(parents=True)
            (pasta / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "caso-real-p"}), encoding="utf-8")
            (pasta / "agents").mkdir()
            (pasta / "agents" / "leitor.md").write_bytes(dados)
            return self.m.conferir_plugin_da_ficha(base, {"nome": "caso-real-p", "origem": "plugins-candidatos/caso-real-p",
                                                          "manifesto_sha256": ""})["erros"]
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_as_quatro_formas_que_passavam_e_o_controle_sao_recusados(self):
        casos = {
            "controle": "---\nname: x\nhooks:\n  PreToolUse: []\n---\n",
            "'---' dentro de um valor antes de hooks": "---\ndescription: antes --- depois\nhooks:\n  Stop: []\n---\n",
            "chave entre aspas": '---\nname: x\n"hooks": {}\n---\n',
            "mapa em linha": "---\nname: x\nconfig: {hooks: {Stop: []}}\n---\n",
            "escape": '---\nname: x\n"\\x68ooks": []\n---\n',
            "mcpServers sem caixa": "---\nname: x\nMcpServers: {}\n---\n",
            "permissionMode": "---\nname: x\npermission_mode: bypassPermissions\n---\n",
            "âncora e alias": "---\nname: &a x\noutro: *a\n---\n",
            "etiqueta": "---\nname: !!str x\n---\n",
            "mesclagem": "---\nname: x\n<<: {a: 1}\n---\n",
            "chave complexa": "---\n? hooks\n: []\n---\n",
            "frontmatter sem fim": "---\nname: x\nhooks: []\n",
        }
        for nome, texto in casos.items():
            with self.subTest(nome):
                self.assertTrue(self.problema(texto.encode("utf-8")), nome)
        # BOM: a regra única do kit (E4) tira o BOM do começo e confere o cabeçalho que vem depois (a réplica recusava
        # todo BOM); o BOM não esconde um cabeçalho proibido.
        self.assertTrue(self.problema(b"\xef\xbb\xbf" + casos["controle"].encode("utf-8")))  # BOM
        self.assertTrue(self.problema(("\n\n" + casos["controle"]).encode("utf-8")))
        self.assertTrue(self.problema(b"---\nname: x\r---\n"))  # CR solto
        self.assertTrue(self.problema("corpo com !`curl exemplo.invalid`\n".encode("utf-8")))

    def test_frontmatter_comum_passa(self):
        for texto in (FRENTE_LIMPA, "sem frontmatter\n", "---\nname: x\n---\ncorpo com --- e hooks no texto\n",
                      FRENTE_LIMPA.replace("\n", "\r\n")):
            with self.subTest(texto=texto[:30]):
                self.assertEqual(self.problema(texto.encode("utf-8")), [])
        # BOM com cabeçalho limpo passa (revisão da integração, defeito 4): a regra única do kit (emenda E4) tira o BOM
        # do começo e confere o cabeçalho que vem depois; a réplica do HOST que saiu (I5) recusava todo Markdown com
        # BOM. O BOM com hooks continua recusado (acima), e um leitor que não tire o BOM não vê cabeçalho nenhum.
        self.assertEqual(self.problema(b"\xef\xbb\xbf" + FRENTE_LIMPA.encode("utf-8")), [])

    def test_bytes_analisados_presos_ao_manifesto(self):
        """Na integração (I5) o kit lê cada arquivo uma vez, confere e põe no manifesto o SHA-256 dos bytes lidos; a
        cópia conferida exige esse SHA-256: o arquivo trocado depois da conferência não é copiado."""
        base = Path(tempfile.mkdtemp(prefix="plugin-bytes-1710-"))
        try:
            pasta = base / "plugins-candidatos" / "caso-real-p"
            (pasta / ".claude-plugin").mkdir(parents=True)
            (pasta / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "caso-real-p"}), encoding="utf-8")
            (pasta / "agents").mkdir()
            agente = pasta / "agents" / "leitor.md"
            agente.write_text(FRENTE_LIMPA, encoding="utf-8")
            res = self.m.conferir_plugin_da_ficha(base, {"nome": "caso-real-p", "origem": "plugins-candidatos/caso-real-p",
                                                         "manifesto_sha256": ""})
            self.assertEqual(res["erros"], [])
            import hashlib
            self.assertEqual(res["manifesto"]["agents/leitor.md"]["sha256"], hashlib.sha256(agente.read_bytes()).hexdigest())
            agente.write_text("---\nhooks: []\n---\n", encoding="utf-8")  # trocado depois da conferência
            destino = base / "copia"
            with self.assertRaises(OSError):
                self.m._copiar_arvore(pasta, res["manifesto"], destino, False)
            self.assertFalse(destino.exists())
        finally:
            shutil.rmtree(base, ignore_errors=True)


class DominiosDaFicha(unittest.TestCase):
    def setUp(self):
        self.m = carregar_preparo()

    def test_curingas_sobre_terminacao_ou_acima_de_hospedagem_compartilhada(self):
        for dominio in ("*.com", "*.com.br", "*.co.uk", "*.gov.br", "*.amazonaws.com", "*.windows.net",
                        "*.core.windows.net", "*.googleapis.com", "*.vercel.app", "*.s3.amazonaws.com",
                        "impressora.local", "x.test", "10.0.0.1", "*.example"):
            with self.subTest(dominio):
                self.assertTrue(self.m.problema_do_dominio(dominio), dominio)  # o do kit (I5), no lugar da réplica
        for dominio in ("pypi.org", "*.pythonhosted.org", "*.exemplo.com.br", "files.pythonhosted.org",
                        "meusite.vercel.app", "registry.npmjs.org"):
            with self.subTest(dominio):
                self.assertIsNone(self.m.problema_do_dominio(dominio), dominio)


class TetoContaItensDaFicha(unittest.TestCase):
    """DECISAO-010, item 5: o teto de 200 domínios conta os itens da ficha, não as entradas que o perfil gera."""

    def setUp(self):
        self.m = carregar_preparo()

    def resultado(self, dominios):
        return {"projeto": "caso-real", "valida": True, "versao": 1, "arquivo": "ficha-v1.json", "sha256": "a" * 64,
                "sig_sha256": "b" * 64, "ficha": {
                    "schema_version": "fundacao.ficha_aberturas/1", "ficha_id": "f1", "project_id": "caso-real",
                    "versao": 1, "motivo": "ensaio", "consequencias": "ensaio", "rede": {"dominios": dominios}}}

    def test_duzentos_curingas_geram_quatrocentas_entradas_e_valem(self):
        teto = self.m.modulos_do_kit().regras.TETO_DOMINIOS
        dominios = [f"*.d{i}.ficticio.com" for i in range(teto)]
        ab = self.m.aberturas_da_ficha(self.resultado(dominios), "caso-real")
        self.assertTrue(ab["valida"], ab["motivo"])
        self.assertEqual(len(ab["rede"]), teto)
        self.assertEqual(len(self.m.expandir_curingas(ab["rede"])), 2 * teto)
        regras = self.m.modulos_do_kit().regras
        ficha = self.resultado(dominios)["ficha"]
        self.assertEqual(regras.validar(ficha, projeto="caso-real")["erros"], [])
        ficha["rede"]["dominios"] = dominios + ["*.d999.ficticio.com"]
        self.assertEqual([e["campo"] for e in regras.validar(ficha, projeto="caso-real")["erros"]], ["rede.dominios"])


class ProjetoNaFormaDoKit(unittest.TestCase):
    def test_a_forma_do_kit_e_do_porteiro(self):
        m = carregar_preparo()
        for valor in ("caso-real", "a", "x1", "fundacao-de-ia", "a" * 40):
            self.assertEqual(m.projeto_valido(valor), valor)
        for valor in ("caso_real", "caso.real", "a--b", "-a", "a-", "con", "lpt1", "a" * 41, "Caso", "", None, "a b"):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                m.projeto_valido(valor)
        with self.assertRaises(ValueError):  # o perfil do projeto também recusa
            m.perfil_wsl(raiz="/mnt/e/F", projeto="caso_real", perfil_windows="/mnt/c/Users/<usuario>", outros_projetos=[])
        with self.assertRaises(ValueError):
            m.perfil_windows(raiz=r"E:\F", python=r"C:\Py\python.exe", projeto="caso.real")


class RelatorioDoPreparo(unittest.TestCase):
    def plano(self, **mudancas):
        plano = {"raiz_wsl": "/mnt/e/Fundacao Exemplo", "projeto": "caso-real", "area": Path("/etc/fundacao-ia/x"),
                 "bin": Path("/usr/local/bin"), "plugins": [], "seccomp": {"instalado": True},
                 "aberturas": {"valida": False, "motivo": "m", "versao": None, "rede": [], "webfetch": [],
                               "websearch": False},
                 "canario": {"aprovado": True, "motivo": "canário aprovado", "arquivo": "/x", "forma": "drvfs:/mnt/e"},
                 "hashes": {"arvores": {}, "ferramentas": "Bash"}}
        plano.update(mudancas)
        return plano

    def test_aviso_de_mnt_sai_mesmo_com_o_filtro_instalado(self):
        m = carregar_preparo()
        avisos = m._relatorio(self.plano(), {}, simular=True)["avisos"]
        self.assertTrue(any("/mnt/<x>" in a and "lógico" in a for a in avisos), avisos)
        self.assertFalse(any("sockets sem filtro" in a for a in avisos))
        avisos = m._relatorio(self.plano(raiz_wsl="/home/titular/fundacao"), {}, simular=True)["avisos"]
        self.assertFalse(any("/mnt/<x>" in a for a in avisos))
        avisos = m._relatorio(self.plano(seccomp={"instalado": False, "motivo": "ausente"}), {}, simular=True)["avisos"]
        self.assertTrue(any("sockets sem filtro" in a for a in avisos))
        self.assertTrue(any("/mnt/<x>" in a for a in avisos))  # separados: um não esconde o outro

    def test_canario_ausente_e_managed_settings_aparecem_com_o_hash(self):
        m = carregar_preparo()
        plano = self.plano(canario={"aprovado": False, "motivo": "sem canário aprovado para o Claude Code 2.1.302"},
                           hashes={"arvores": {"claude-code-gerenciado": {"caminho": "/etc/claude-code",
                                                                          "sha256": "ab" * 32}},
                                   "ferramentas": "Bash"})
        rel = m._relatorio(plano, {"aviso": "a caixa de entrada só tem a ficha v1"}, simular=True)
        self.assertTrue(any("nenhuma abertura vale" in a for a in rel["avisos"]), rel["avisos"])
        self.assertTrue(any("ab" * 32 in a and "managed settings" in a for a in rel["avisos"]), rel["avisos"])
        self.assertTrue(any("ficha v1" in a for a in rel["avisos"]))
        self.assertEqual(rel["gerenciadas"]["sha256"], "ab" * 32)
        self.assertFalse(rel["canario"]["aprovado"])


@unittest.skipUnless(LINUX, "o filtro seccomp e o dono das pastas são do Ubuntu")
class SeccompEmCaminhoFixo(unittest.TestCase):
    def setUp(self):
        self.m = carregar_preparo()
        self.base = Path(tempfile.mkdtemp(prefix="seccomp-1710-"))
        self.pacote = self.base / "node_modules" / "@anthropic-ai" / "sandbox-runtime"
        (self.pacote / "vendor" / "seccomp" / "x64").mkdir(parents=True)
        (self.pacote / "package.json").write_text('{"name": "@anthropic-ai/sandbox-runtime", "version": "0.0.1"}',
                                                  encoding="utf-8")
        (self.pacote / "vendor" / "seccomp" / "x64" / "unix-block.bpf").write_bytes(b"\x00filtro de ensaio")
        for p in [self.pacote, *self.pacote.rglob("*")]:
            os.chmod(p, 0o755 if p.is_dir() else 0o644)
        self.bases = [str(self.base / "nao-existe"), str(self.base / "node_modules")]

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_so_conta_no_caminho_fixo_do_dono_e_com_os_arquivos_do_filtro(self):
        achado = self.m.detectar_seccomp(self.bases, dono=os.getuid())
        self.assertTrue(achado["instalado"], achado)
        self.assertEqual(achado["versao"], "0.0.1")
        self.assertTrue(achado["filtro"].endswith("/vendor/seccomp"))
        self.assertFalse(self.m.detectar_seccomp(self.bases, dono=os.getuid() + 1)["instalado"])  # de outra conta
        os.chmod(self.pacote / "package.json", 0o666)
        self.assertFalse(self.m.detectar_seccomp(self.bases, dono=os.getuid())["instalado"])  # gravável por outros
        os.chmod(self.pacote / "package.json", 0o644)
        shutil.rmtree(self.pacote / "vendor")
        sem = self.m.detectar_seccomp(self.bases, dono=os.getuid())
        self.assertFalse(sem["instalado"])
        self.assertIn("sockets sem filtro", sem["motivo"])
        self.assertFalse(self.m.detectar_seccomp([str(self.base / "vazio")], dono=os.getuid())["instalado"])

    def test_o_preparo_nao_pergunta_ao_npm(self):
        self.assertNotIn("subprocess", vars(self.m))  # nada roda como root para achar o pacote


if __name__ == "__main__":
    unittest.main()
