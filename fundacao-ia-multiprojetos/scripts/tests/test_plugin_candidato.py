"""plugin_candidato.py (1.7.10; DESENHO-1.7.10 §8.2; contratos do lote 2, §5 `plugins[]`, §6 e §8; pacote PLUGINS):
o manifesto canônico do candidato (o contrato com o instalador do preparo do host), o `montar` — forma, nome e recusas
de origem e destino — e a linha de comando. Pastas descartáveis com dados fictícios; nada do candidato é executado.

As regras de conteúdo e a revisão estão em test_plugin_candidato_regras.py; ligação, junção, vínculo físico e FIFO, em
test_plugin_candidato_ligacoes.py (rodados também no Ubuntu). A sessão de quem roda os testes (FUNDACAO_PROJECT,
FUNDACAO_RAIZ) sai do ambiente: o script recusa candidato de outro projeto que o da sessão.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import ENV, KIT, SCRIPTS, SKILL

VARIAVEL_PROJETO, VARIAVEL_RAIZ = "FUNDACAO_" + "PROJECT", "FUNDACAO_" + "RAIZ"
SKILL_OK = ("---\nname: ola\ndescription: Diz olá em português (skill fictícia de teste).\n"
            "allowed-tools: Read, Grep\n---\n\n# Olá\n\nResponda com um olá curto.\n")
AGENTE_OK = ("---\nname: revisor\ndescription: Revisa textos fictícios.\ntools: Read, Grep\nmodel: sonnet\n---\n\n"
             "Revise o texto indicado.\n")
COMANDO_OK = "---\ndescription: Resume o arquivo indicado.\nargument-hint: <arquivo>\n---\n\nResuma $ARGUMENTS.\n"
GUIA = "# Guia\n\nTexto fictício de apoio.\n"


def carregar():
    spec = importlib.util.spec_from_file_location("plugin_candidato_teste", SCRIPTS / "plugin_candidato.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


MOD = carregar()


def ambiente_sem_sessao(**extra) -> dict:
    env = {k: v for k, v in ENV.items() if k not in (VARIAVEL_PROJETO, VARIAVEL_RAIZ)}
    env.update(extra)
    return env


def rodar(*args, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / "plugin_candidato.py"), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=ambiente_sem_sessao() if env is None else env, timeout=180)


def escrever(base: Path, arquivos: dict) -> None:
    """{rel: texto | bytes | None}: None cria a pasta."""
    for rel, conteudo in arquivos.items():
        alvo = base / rel
        if conteudo is None:
            alvo.mkdir(parents=True, exist_ok=True)
            continue
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(conteudo if isinstance(conteudo, bytes) else conteudo.encode("utf-8"))


def distingue_caixa(base: Path) -> bool:
    """O sistema de arquivos de `base` guarda dois nomes que só diferem pela caixa? (O NTFS visto pelo DrvFs do WSL,
    em /mnt/c, não guarda: o segundo nome abre o primeiro arquivo.)"""
    sonda = Path(tempfile.mkdtemp(prefix="sonda-caixa-", dir=base))
    (sonda / "Sonda").write_bytes(b"1")
    (sonda / "sonda").write_bytes(b"2")
    return len(os.listdir(sonda)) == 2


def guarda_modo(base: Path) -> bool:
    """O sistema de arquivos de `base` guarda o modo 0o444? (O DrvFs sem a opção metadata mostra 0o555.)"""
    fd, nome = tempfile.mkstemp(prefix="sonda-modo-", dir=base)
    os.close(fd)
    os.chmod(nome, 0o444)
    return stat.S_IMODE(os.lstat(nome).st_mode) == 0o444


class Fundacao:
    """Mistura dos testes: raiz fictícia com os projetos `demo` e `outro`, sem a sessão de quem roda os testes."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="plugin-candidato-1710-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.raiz = self.base / "fundacao"
        self.proj = self.raiz / "projects" / "demo"
        self.outro = self.raiz / "projects" / "outro"
        self.proj.mkdir(parents=True)
        self.outro.mkdir()
        sem_sessao = {k: v for k, v in os.environ.items() if k not in (VARIAVEL_PROJETO, VARIAVEL_RAIZ)}
        patcher = mock.patch.dict(os.environ, sem_sessao, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def candidato(self, extras: dict | None = None, nome: str = "demo-kit", sem: tuple = ()) -> Path:
        """Um candidato conforme, montado à mão em projects/demo/plugins-candidatos/<nome> (refeito do zero)."""
        pasta = self.proj / "plugins-candidatos" / nome
        shutil.rmtree(pasta, ignore_errors=True)
        arquivos = {".claude-plugin/plugin.json": json.dumps({"name": nome, "description": "Plugin fictício."}),
                    "skills/ola/SKILL.md": SKILL_OK, "skills/ola/referencias/guia.md": GUIA,
                    "agents/revisor.md": AGENTE_OK, "commands/resumo.md": COMANDO_OK, "LICENSE": "Licença fictícia.\n"}
        for rel in sem:
            arquivos.pop(rel)
        arquivos.update(extras or {})
        pasta.mkdir(parents=True)
        escrever(pasta, arquivos)
        return pasta

    def origem_arvore(self, extras: dict | None = None, pasta: str = "importado/.claude") -> Path:
        """Uma `.claude/` fictícia de projeto importado: componentes, configuração e hook (que não vêm)."""
        origem = self.proj / pasta
        arquivos = {"skills/ola/SKILL.md": SKILL_OK, "skills/ola/referencias/guia.md": GUIA,
                    "agents/revisor.md": AGENTE_OK, "commands/resumo.md": COMANDO_OK, "settings.json": "{}\n",
                    "hooks/aviso.sh": "echo ficticio\n", ".mcp.json": '{"mcpServers": {}}\n'}
        arquivos.update(extras or {})
        origem.mkdir(parents=True)
        escrever(origem, arquivos)
        return origem

    def arquivos_de(self, pasta: Path) -> list:
        return sorted(p.relative_to(pasta).as_posix() for p in pasta.rglob("*") if p.is_file())


class TestManifesto(Fundacao, unittest.TestCase):
    def test_forma_e_json_canonico(self):
        pasta = self.candidato({"skills/ola/referências/índice.md": "Acentos no caminho.\n"})
        dados, sha = MOD.manifesto(pasta)
        self.assertEqual(set(dados), {"schema_version", "nome", "arquivos"})
        self.assertEqual((dados["schema_version"], dados["nome"]), ("fundacao.plugin_candidato/1", "demo-kit"))
        caminhos = [a["caminho"] for a in dados["arquivos"]]
        self.assertEqual(caminhos, sorted(caminhos))
        self.assertEqual(caminhos, self.arquivos_de(pasta))
        self.assertIn("skills/ola/referências/índice.md", caminhos)
        for item in dados["arquivos"]:
            corpo = (pasta / item["caminho"]).read_bytes()
            self.assertEqual(set(item), {"caminho", "bytes", "sha256"})
            self.assertEqual((item["bytes"], item["sha256"]), (len(corpo), hashlib.sha256(corpo).hexdigest()))
        # A receita única do kit (emenda E3; integração, item I4): o JSON compacto só da lista `arquivos`.
        canonico = json.dumps(dados["arquivos"], sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False).encode("utf-8")
        self.assertIn("referências".encode("utf-8"), canonico)  # sem escapar o que não é ASCII
        self.assertEqual(sha, hashlib.sha256(canonico).hexdigest())

    def test_mesma_arvore_mesmo_hash_e_um_byte_muda(self):
        pasta = self.candidato()
        dados, sha = MOD.manifesto(pasta)
        self.assertEqual(MOD.manifesto(pasta), (dados, sha))
        copia = self.base / "outra-maquina" / pasta.name
        shutil.copytree(pasta, copia)
        self.assertEqual(MOD.manifesto(copia)[1], sha, "a mesma árvore, em outro lugar, dá o mesmo hash")
        alvo = copia / "skills" / "ola" / "referencias" / "guia.md"
        corpo = bytearray(alvo.read_bytes())
        corpo[3] ^= 0x01
        alvo.write_bytes(bytes(corpo))
        self.assertNotEqual(MOD.manifesto(copia)[1], sha)

    def test_o_nome_entra_pelo_plugin_json(self):
        # Receita única do kit (emenda E3; integração, item I4): o hash é só da lista de arquivos, sem o nome da pasta;
        # o nome fica preso pelo plugin.json, que entra no hash. A mesma árvore em outra pasta dá o mesmo hash, mas o
        # conferir dela recusa (o name do plugin.json difere da pasta), e outro name muda o hash.
        pasta = self.candidato()
        sha = MOD.manifesto(pasta)[1]
        outra = self.base / "demo-kit2"
        shutil.copytree(pasta, outra)
        self.assertEqual(MOD.manifesto(outra)[1], sha)
        self.assertIn("name tem de ser demo-kit2", " ".join(MOD.conferir(outra)["motivos"]))
        self.assertNotEqual(MOD.manifesto(self.candidato(nome="demo-kit3"))[1], sha)

    def test_conferir_e_manifesto_dao_o_mesmo_hash(self):
        pasta = self.candidato()
        res = MOD.conferir(pasta)
        self.assertTrue(res["conforme"], res["motivos"])
        self.assertEqual((res["manifesto"], res["manifesto_sha256"]), MOD.manifesto(pasta))

    def test_pasta_que_nao_existe_ou_arquivo_recusa(self):
        with self.assertRaises(MOD.CandidatoRecusado):
            MOD.manifesto(self.proj / "plugins-candidatos" / "nao-existe")
        arquivo = self.proj / "um-arquivo"
        arquivo.write_text("x", encoding="utf-8")
        with self.assertRaises(MOD.CandidatoRecusado):
            MOD.manifesto(arquivo)

    def test_nome_forte_e_pasta_de_segredo_recusam_sem_ler(self):
        # Regra única (contratos §3; revisão do pacote PLUGINS): o nome forte nunca é lido, nem para o hash.
        pasta = self.candidato({"skills/ola/id_rsa": "chave fictícia\n", "skills/ola/segredos/nota.md": "x\n"})
        real, real_ler, lidos = MOD.COPIA.hash_conferido, MOD._ler, []

        def registrar(caminho, dentro_de=None):
            lidos.append(Path(caminho).relative_to(pasta).as_posix())
            return real(caminho, dentro_de=dentro_de)

        def registrar_ler(caminho, dentro_de):  # revisão da integração, rodada 2: o manifesto passou a ler por _ler
            lidos.append(Path(caminho).relative_to(pasta).as_posix())
            return real_ler(caminho, dentro_de)

        with mock.patch.object(MOD.COPIA, "hash_conferido", side_effect=registrar), \
                mock.patch.object(MOD, "_ler", side_effect=registrar_ler), \
                self.assertRaises(MOD.CandidatoRecusado) as ctx:
            MOD.manifesto(pasta)
        self.assertEqual(lidos, [], "nada é lido quando o candidato tem nome forte ou pasta de segredo")
        motivos = " ".join(ctx.exception.motivos)
        self.assertIn("skills/ola/id_rsa", motivos)
        self.assertIn("skills/ola/segredos/nota.md", motivos)

    def test_bytes_lidos_acima_do_teto_recusam(self):
        # O exame soma o tamanho visto; um arquivo que cresce até a leitura não passa do teto em silêncio.
        # Revisão da integração, rodada 2: o manifesto lê cada arquivo por _ler (os mesmos bytes no hash e na
        # conferência do conteúdo, em todo sistema), não mais pelo hash_conferido: o arquivo que cresce vem de lá.
        pasta = self.candidato()
        real = MOD._ler

        def cresceu(caminho, dentro_de):
            dados = real(caminho, dentro_de)
            return dados + b"x" * (MOD.TETO["arquivo"] + 1 - len(dados)) if Path(caminho).name == "guia.md" else dados

        with mock.patch.object(MOD, "_ler", side_effect=cresceu), \
                self.assertRaises(MOD.CandidatoRecusado) as ctx:
            MOD.manifesto(pasta)
        self.assertIn("bytes lidos passam do teto", str(ctx.exception))


class TestMontar(Fundacao, unittest.TestCase):
    def test_monta_no_formato_de_plugin_do_claude_code(self):
        origem = self.origem_arvore()
        res = MOD.montar(self.raiz, "demo", "kit", origem)
        destino = self.proj / "plugins-candidatos" / "demo-kit"
        self.assertEqual((Path(res["candidato"]), res["nome"], res["origem"]),
                         (destino, "demo-kit", "importado/.claude"))
        plugin = json.loads((destino / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(set(plugin), {"name", "description"})
        self.assertEqual(plugin["name"], "demo-kit")
        copiados = ["skills/ola/SKILL.md", "skills/ola/referencias/guia.md", "agents/revisor.md", "commands/resumo.md"]
        for rel in copiados:
            self.assertEqual((destino / rel).read_bytes(), (origem / rel).read_bytes(), rel)
        self.assertEqual(self.arquivos_de(destino), sorted([".claude-plugin/plugin.json", *copiados]))
        self.assertEqual(sorted(res["nao_copiados"]), [".mcp.json", "hooks/", "settings.json"])
        self.assertTrue(any("1.7.11" in aviso for aviso in res["avisos"]), res["avisos"])
        self.assertEqual(res["manifesto_sha256"], MOD.manifesto(destino)[1])
        self.assertEqual(res["ficha"], {"nome": "demo-kit", "origem": "plugins-candidatos/demo-kit",
                                        "manifesto_sha256": res["manifesto_sha256"]})
        self.assertEqual({c["invocacao"] for c in res["componentes"]},
                         {"/demo-kit:ola", "demo-kit:revisor", "/demo-kit:resumo"})
        self.assertTrue(MOD.conferir(destino)["conforme"])
        self.assertEqual([p.name for p in (self.proj / "plugins-candidatos").iterdir()], ["demo-kit"],
                         "a pasta temporária da montagem não sobra")
        if os.name != "nt":
            with self.subTest("modo 0o444"):
                if not guarda_modo(self.base):
                    self.skipTest("o sistema de arquivos destes temporários não guarda o modo (DrvFs sem metadata)")
                self.assertEqual(stat.S_IMODE(os.lstat(destino / "skills/ola/SKILL.md").st_mode), 0o444)
                self.assertEqual(stat.S_IMODE(os.lstat(destino / ".claude-plugin/plugin.json").st_mode), 0o444)

    def test_skill_avulsa_vira_skills_com_o_nome_da_pasta(self):
        # A licença dentro da skill vai em Markdown: em skills/ o kit só aceita .md (integração, item I12).
        origem = self.proj / "trazidas" / "pesquisa"
        origem.mkdir(parents=True)
        escrever(origem, {"SKILL.md": SKILL_OK.replace("name: ola", "name: pesquisa"), "LICENSE.md": "MIT fictícia\n",
                          "referencias/fontes.md": GUIA})
        res = MOD.montar(self.raiz, "demo", "pesquisa", origem)
        destino = self.proj / "plugins-candidatos" / "demo-pesquisa"
        self.assertEqual(self.arquivos_de(destino),
                         [".claude-plugin/plugin.json", "skills/pesquisa/LICENSE.md", "skills/pesquisa/SKILL.md",
                          "skills/pesquisa/referencias/fontes.md"])
        self.assertEqual(res["nao_copiados"], [])
        self.assertEqual([c["invocacao"] for c in res["componentes"]], ["/demo-pesquisa:pesquisa"])

    def test_licenca_da_raiz_da_origem_vem_junto_e_o_resto_nao(self):
        origem = self.origem_arvore({"LICENSE": "Licença fictícia.\n", "README.md": "Leia-me fictício.\n"})
        res = MOD.montar(self.raiz, "demo", "kit", origem)
        destino = Path(res["candidato"])
        self.assertEqual((destino / "LICENSE").read_text(encoding="utf-8"), "Licença fictícia.\n")
        self.assertIn("README.md", res["nao_copiados"])
        self.assertFalse((destino / "README.md").exists())

    def test_descricao_propria_e_recusa_de_descricao_com_controle(self):
        origem = self.origem_arvore()
        res = MOD.montar(self.raiz, "demo", "kit", origem, descricao="Kit fictício do projeto demo.")
        plugin = json.loads((Path(res["candidato"]) / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin["description"], "Kit fictício do projeto demo.")
        for descricao in ("", "   ", "cor\x1b[31m escondida", "x" * 1025):
            with self.subTest(descricao=descricao[:20]), self.assertRaises(MOD.CandidatoRecusado):
                MOD.montar(self.raiz, "demo", "kit2", origem, descricao=descricao)
        self.assertFalse((self.proj / "plugins-candidatos" / "demo-kit2").exists())

    def test_nomes_recusados(self):
        # Integração, item I12: o nome do plugin segue o NOME_PLUGIN da ficha (até 64 caracteres com o projeto).
        origem = self.origem_arvore()
        casos = (("Demo", "kit"), ("demo_x", "kit"), ("-demo", "kit"), ("demo", "a:b"), ("demo", "kit."),
                 ("demo", "com espaço"), ("demo", ""), ("demo", "-kit"), ("demo", "x" * 124), ("demo", "açúcar"),
                 ("demo", "x" * 60))
        for projeto, nome in casos:
            with self.subTest(projeto=projeto, nome=nome), self.assertRaises(MOD.CandidatoRecusado):
                MOD.montar(self.raiz, projeto, nome, origem)
        self.assertFalse((self.proj / "plugins-candidatos").exists())
        self.assertEqual(MOD.montar(self.raiz, "demo", "x" * 59, origem)["nome"], "demo-" + "x" * 59)

    def test_nome_fora_do_kebab_case_monta_com_aviso(self):
        # O validador do Claude Code 2.1.302 aceita `[A-Za-z0-9][-A-Za-z0-9._]*` e avisa fora do kebab-case. Integração,
        # item I12: a ficha só aceita minúsculas, números e hífen (NOME_PLUGIN); "Kit_v2" recusa; o aviso fica no '--'.
        origem = self.origem_arvore()
        with self.assertRaises(MOD.CandidatoRecusado):
            MOD.montar(self.raiz, "demo", "Kit_v2", origem)
        res = MOD.montar(self.raiz, "demo", "kit--v2", origem)
        self.assertEqual(res["nome"], "demo-kit--v2")
        self.assertTrue(any("kebab-case" in aviso for aviso in res["avisos"]), res["avisos"])
        self.assertTrue(any("kebab-case" in aviso for aviso in MOD.conferir(res["candidato"])["avisos"]))
        res = MOD.montar(self.raiz, "demo", "kit", origem)
        self.assertFalse(any("kebab-case" in aviso for aviso in res["avisos"]), res["avisos"])
        self.assertFalse(any("Anthropic" in aviso for aviso in res["avisos"]), res["avisos"])

    def test_nome_que_passa_por_um_da_anthropic_monta_com_aviso(self):
        # O validador do Claude Code 2.1.302 recusa ou avisa nome de terceiro com claude, anthropic ou cc-plugin. Em
        # minúsculas: a ficha não aceita "kit-Claude" (NOME_PLUGIN; integração, item I12).
        origem = self.origem_arvore()
        for nome in ("claude-tools", "anthropic", "kit-claude"):
            with self.subTest(nome=nome):
                res = MOD.montar(self.raiz, "demo", nome, origem)
                self.assertTrue(any("passa por um da Anthropic" in aviso for aviso in res["avisos"]), res["avisos"])

    def test_nome_valido(self):
        for nome in ("demo-kit", "demo-kit.v2", "a", "A_b-1", "x" * 128):
            self.assertTrue(MOD.nome_valido(nome), nome)
        for nome in ("", "-x", ".x", "a:b", "kit.", "com espaço", "á", "x" * 129, None, "a\n", "a/b", "a\\b"):
            self.assertFalse(MOD.nome_valido(nome), nome)

    def test_origem_fora_do_projeto_ou_que_nao_e_pasta_recusa(self):
        escrever(self.outro, {"skills/x/SKILL.md": SKILL_OK})
        fora = self.base / "fora"
        escrever(fora, {"skills/x/SKILL.md": SKILL_OK})
        arquivo = self.proj / "um-arquivo.md"
        arquivo.write_text("x", encoding="utf-8")
        casos = (self.outro / "skills" / "x", self.outro, fora, self.raiz, self.proj, self.proj / "nao-existe",
                 arquivo, self.proj / "a" / ".." / ".." / "outro" / "skills" / "x")
        for origem in casos:
            with self.subTest(origem=origem), self.assertRaises(MOD.CandidatoRecusado):
                MOD.montar(self.raiz, "demo", "kit", origem)
        self.assertFalse((self.proj / "plugins-candidatos").exists())
        self.assertFalse((self.outro / "plugins-candidatos").exists())

    def test_origem_que_contem_o_destino_recusa(self):
        candidatos = self.proj / "plugins-candidatos"
        escrever(candidatos, {"skills/ola/SKILL.md": SKILL_OK})
        with self.assertRaises(MOD.CandidatoRecusado):
            MOD.montar(self.raiz, "demo", "kit", candidatos)
        self.assertFalse((candidatos / "demo-kit").exists())

    def test_origem_em_data_monta_com_aviso(self):
        origem = self.origem_arvore(pasta="data/copia/.claude")
        res = MOD.montar(self.raiz, "demo", "kit", origem)
        self.assertTrue(any("data/" in aviso for aviso in res["avisos"]), res["avisos"])
        self.assertTrue(MOD.conferir(res["candidato"])["conforme"])

    def test_destino_existente_recusa_e_nao_muda(self):
        origem = self.origem_arvore()
        res = MOD.montar(self.raiz, "demo", "kit", origem)
        antes = MOD.manifesto(res["candidato"])
        (origem / "skills" / "ola" / "referencias" / "guia.md").write_text("Outro texto.\n", encoding="utf-8")
        with self.assertRaises(MOD.CandidatoRecusado) as ctx:
            MOD.montar(self.raiz, "demo", "kit", origem)
        self.assertIn("já existe", str(ctx.exception))
        self.assertEqual(MOD.manifesto(res["candidato"]), antes)

    def test_conteudo_recusado_nao_grava_nada(self):
        origem = self.origem_arvore({"skills/ola/rodar.py": "print('ficticio')\n"})
        with self.assertRaises(MOD.CandidatoRecusado) as ctx:
            MOD.montar(self.raiz, "demo", "kit", origem)
        self.assertTrue(any("rodar.py" in m and "1.7.11" in m for m in ctx.exception.motivos), ctx.exception.motivos)
        self.assertFalse((self.proj / "plugins-candidatos").exists())

    def test_origem_sem_componentes_recusa(self):
        origem = self.proj / "vazia"
        escrever(origem, {"README.md": "nada\n", "notas/x.md": "x\n"})
        with self.assertRaises(MOD.CandidatoRecusado) as ctx:
            MOD.montar(self.raiz, "demo", "kit", origem)
        self.assertIn("não tem skill, agente nem comando", str(ctx.exception))

    def test_copia_trocada_depois_da_conferencia_recusa_e_nao_deixa_nada(self):
        # O rehash da cópia (sha256_esperado) pega o arquivo trocado entre a conferência e a cópia.
        origem = self.origem_arvore()
        real = MOD.COPIA.copiar_conferindo

        def trocar_e_copiar(origem_arq, destino_arq, **kw):
            if Path(origem_arq).name == "guia.md":
                Path(origem_arq).write_text("Trocado depois da conferência.\n", encoding="utf-8")
            return real(origem_arq, destino_arq, **kw)

        with mock.patch.object(MOD.COPIA, "copiar_conferindo", side_effect=trocar_e_copiar), \
                self.assertRaises(MOD.CandidatoRecusado):
            MOD.montar(self.raiz, "demo", "kit", origem)
        self.assertEqual(list((self.proj / "plugins-candidatos").iterdir()), [], "nem o candidato nem o temporário")

    def test_sessao_de_outro_projeto_ou_outra_raiz_recusa(self):
        origem = self.origem_arvore()
        os.environ[VARIAVEL_PROJETO] = "outro"
        with self.assertRaises(MOD.CandidatoRecusado):
            MOD.montar(self.raiz, "demo", "kit", origem)
        os.environ[VARIAVEL_PROJETO] = "demo"
        os.environ[VARIAVEL_RAIZ] = str(self.base / "outra-raiz")
        with self.assertRaises(MOD.CandidatoRecusado):
            MOD.montar(self.raiz, "demo", "kit", origem)
        os.environ[VARIAVEL_RAIZ] = str(self.raiz)
        self.assertEqual(MOD.montar(self.raiz, "demo", "kit", origem)["nome"], "demo-kit")


class TestLinhaDeComando(Fundacao, unittest.TestCase):
    def test_montar_conferir_e_revisar(self):
        origem = self.origem_arvore()
        r = rodar("montar", "--raiz", self.raiz, "--projeto", "demo", "--nome", "kit", "--origem", origem)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        montado = json.loads(r.stdout)
        destino = Path(montado["candidato"])
        r = rodar("conferir", "--pasta", destino)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        conferido = json.loads(r.stdout)
        self.assertTrue(conferido["conforme"])
        self.assertEqual(conferido["manifesto_sha256"], montado["manifesto_sha256"])
        self.assertEqual(conferido["manifesto_sha256"], MOD.manifesto(destino)[1])
        r = rodar("revisar", "--pasta", destino)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(r.stdout.startswith("# Revisão do plugin candidato `demo-kit`"))
        saida = self.proj / "outputs" / "plugins" / "kit" / "REVISAO.md"
        r = rodar("revisar", "--pasta", destino, "--saida", saida)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["revisao"], str(saida))
        self.assertIn(montado["manifesto_sha256"], saida.read_text(encoding="utf-8"))

    def test_recusas_saem_com_codigo_2_e_os_motivos(self):
        pasta = self.candidato({"skills/ola/rodar.sh": "echo ficticio\n"})
        r = rodar("conferir", "--pasta", pasta)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        res = json.loads(r.stdout)
        self.assertFalse(res["conforme"])
        self.assertIsNone(res["manifesto_sha256"])
        self.assertTrue(any("rodar.sh" in m for m in res["motivos"]))
        r = rodar("conferir", "--pasta", self.candidato(), env=ambiente_sem_sessao(**{VARIAVEL_PROJETO: "outro"}))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["erro"], "recusado")
        r = rodar("montar", "--raiz", self.raiz, "--projeto", "demo")
        self.assertEqual(r.returncode, 2, "argumentos faltando")
        r = rodar("montar", "--raiz", self.raiz, "--projeto", "demo", "--nome", "kit", "--origem", self.outro)
        self.assertEqual((r.returncode, json.loads(r.stdout)["erro"]), (2, "recusado"))

    def test_sessao_nao_le_outro_projeto_fora_de_plugins_candidatos(self):
        # Revisão do pacote PLUGINS: na sessão demo, `revisar` de projects/outro/importado/.claude imprimia o texto do
        # outro projeto; agora recusa antes de ler (código 2, sem nada do outro projeto na saída).
        canario = "CANARIO-FICTICIO do projeto outro"
        importado = self.outro / "importado" / ".claude"
        escrever(importado, {"skills/x/SKILL.md": SKILL_OK, "skills/x/nota.md": canario + "\n"})
        escrever(self.outro / "data", {"nota.md": canario + "\n"})
        sessao = ambiente_sem_sessao(**{VARIAVEL_PROJETO: "demo", VARIAVEL_RAIZ: str(self.raiz)})
        for acao, pasta in (("revisar", importado), ("conferir", importado), ("conferir", self.outro / "data"),
                            ("revisar", self.outro / "data")):
            with self.subTest(acao=acao, pasta=pasta.name):
                r = rodar(acao, "--pasta", pasta, env=sessao)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertEqual(json.loads(r.stdout)["erro"], "recusado")
                self.assertNotIn("CANARIO", r.stdout + r.stderr)
        r = rodar("revisar", "--pasta", self.candidato(), env=sessao)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class TestRegrasRepetidas(unittest.TestCase):
    def test_nome_de_skill_igual_ao_do_preparo_do_host(self):
        texto = (SKILL / "assets" / "host" / "preparo_host.py").read_text(encoding="utf-8")
        achado = re.search(r'^NOME_DE_SKILL = re\.compile\((r".*")\)$', texto, re.M)
        self.assertIsNotNone(achado, "NOME_DE_SKILL sumiu do preparo_host.py")
        self.assertEqual(MOD.NOME_DE_SKILL.pattern, ast.literal_eval(achado.group(1)))

    def test_id_de_projeto_igual_ao_do_kit(self):
        texto = (KIT / "fundacao" / "core" / "paths.py").read_text(encoding="utf-8")
        achado = re.search(r'^ID_RE = re\.compile\((r".*")\)$', texto, re.M)
        self.assertIsNotNone(achado, "ID_RE sumiu do fundacao/core/paths.py")
        self.assertEqual(MOD.ID_PROJETO.pattern, ast.literal_eval(achado.group(1)))


if __name__ == "__main__":
    unittest.main()
