"""Portão do canário no preparo do host (1.7.10; contratos do lote 2, §0; SONDAS de 31/10/2026; revisão do lote 2).

"Nenhuma abertura vale sem o resultado do canário": a ficha assinada só é aplicada com o relatório
`fundacao.ensaio_isolamento/1` do ensaio real (pacote CANARIO) instalado pelo titular (`preparo_host.py
instalar-canario`, com sudo), do mesmo Claude Code fixado (versão e SHA-256) e da mesma forma de caminho da raiz (ext4
ou drvfs:/mnt/<x>, medida no /proc/mounts). Sem ele, tudo fechado, e o relatório do preparo diz por quê; com ele, o
relatório fica fixado no hashes.json e o lançador o reconfere. Ensaio sem root (área em pasta temporária), com os
substitutos do apoio para as peças dos outros pacotes. As peças puras rodam em qualquer sistema. O aviso do lançador
sobre `projects/<p>/.claude/<sub>` diz só o que o canário mede (I19): a carga de uma `.claude/` em subpasta do projeto,
não a do próprio projeto.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import SCRIPTS
from test_host_projeto_apoio import (LINUX, carregar_preparo, claude_de_ensaio, ficha_de_ensaio,
                                     gravar_ficha_na_caixa, instalar, instalar_canario, raiz_de_ensaio,
                                     relatorio_de_canario, sha, skill_de_ensaio)

SHA_CLAUDE = "c" * 64
# O que o aviso diz do canário (I19): a subpasta que o item da carga usa e o que ela tem.
AVISO_DO_CANARIO = ("o canário mede a carga aninhada numa subpasta (aninhado/.claude/, só skill e agente), "
                    "não esta pasta")


def relatorio(forma="ext4", fs="ext4", **mudancas) -> dict:
    """Relatório de ensaio montado à mão (as peças puras não medem nada)."""
    base = {"schema_version": "fundacao.ensaio_isolamento/1", "data": "2026-10-31T12:00:00Z", "simulado": False,
            "forma": forma, "sistema_de_arquivos": fs, "claude": {"versao": "2.1.302", "sha256": SHA_CLAUDE},
            "conclusao": {"forma": forma, "sistema_de_arquivos": fs, "confina_comandos": True, "motivo": "ensaio"}}
    base.update(mudancas)
    return base


def carregar_ensaio():
    """O canário (`scripts/ensaio_isolamento_wsl.py`), pelo caminho: o aviso do lançador é conferido contra o que ele
    mede (I19). Carregar não cria nada."""
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("ensaio_isolamento_aviso_i19", SCRIPTS / "ensaio_isolamento_wsl.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class PecasDoCanario(unittest.TestCase):
    def setUp(self):
        self.m = carregar_preparo()

    def conferir(self, rel, **kw):
        return self.m.conferir_relatorio_do_canario(rel, claude_versao="2.1.302", claude_sha256=SHA_CLAUDE, **kw)

    def test_forma_do_caminho(self):
        f = self.m.forma_do_caminho
        self.assertEqual(f("/home/titular/fundacao", "ext4"), "ext4")
        self.assertEqual(f("/mnt/e/Fundacao Exemplo", "9p"), "drvfs:/mnt/e")
        self.assertEqual(f("/mnt/d/IA/fundacao", "drvfs"), "drvfs:/mnt/d")
        for caminho, fs in (("/mnt/e/x", "ext4"), ("/home/x", "9p"), ("/tmp/x", "tmpfs"), ("/home/x", "nao_medido")):
            self.assertIsNone(f(caminho, fs), (caminho, fs))

    def test_relatorio_aprovado_e_cada_recusa(self):
        self.assertIsNone(self.conferir(relatorio(), forma="ext4"))
        self.assertIsNone(self.conferir(relatorio("drvfs:/mnt/e/ensaio", "9p"), forma="drvfs:/mnt/e"))
        casos = {
            "outro esquema": relatorio(schema_version="fundacao.ensaio_isolamento/2"),
            "simulação": relatorio(simulado=True),
            "sem a marca de real": {k: v for k, v in relatorio().items() if k != "simulado"},
            "comandos não confinados": relatorio(conclusao={"forma": "ext4", "confina_comandos": False}),
            "confinamento não provado": relatorio(conclusao={"forma": "ext4", "confina_comandos": None}),
            "outra versão do Claude Code": relatorio(claude={"versao": "2.1.303", "sha256": SHA_CLAUDE}),
            "outro binário": relatorio(claude={"versao": "2.1.302", "sha256": "d" * 64}),
            "sem o binário": relatorio(claude={}),
            "ext4 rotulado, medido em 9p": relatorio("ext4", "9p"),
            "drvfs rotulado, medido em ext4": relatorio("drvfs:/mnt/e/ensaio", "ext4"),
            "forma da conclusão diferente": relatorio(conclusao={"forma": "drvfs:/mnt/e/x", "confina_comandos": True}),
        }
        for nome, rel in casos.items():
            with self.subTest(nome):
                self.assertTrue(self.conferir(rel, forma="ext4"), nome)
        self.assertIn("forma", self.conferir(relatorio("drvfs:/mnt/e/ensaio", "9p"), forma="ext4"))
        self.assertIn("forma", self.conferir(relatorio("drvfs:/mnt/d/ensaio", "9p"), forma="drvfs:/mnt/e"))

    def test_portao_le_so_a_area_e_confere_versao_binario_e_forma(self):
        base = Path(tempfile.mkdtemp(prefix="canario-portao-1710-"))
        try:
            area = base / "area"
            kw = dict(claude_versao="2.1.302", claude_sha256=SHA_CLAUDE, raiz_wsl="/home/titular/fundacao")
            sem = self.m.portao_do_canario(area, fs_raiz="ext4", **kw)
            self.assertFalse(sem["aprovado"])
            self.assertIn("instalar-canario", sem["motivo"])
            (area / "canario").mkdir(parents=True)
            (area / "canario" / "2.1.302.json").write_text(json.dumps(relatorio()), encoding="utf-8")
            com = self.m.portao_do_canario(area, fs_raiz="ext4", **kw)
            self.assertTrue(com["aprovado"], com)
            self.assertEqual(com["sha256"], sha(area / "canario" / "2.1.302.json"))
            self.assertFalse(self.m.portao_do_canario(area, fs_raiz="9p", **{**kw, "raiz_wsl": "/mnt/e/F"})["aprovado"])
            self.assertFalse(self.m.portao_do_canario(area, fs_raiz="tmpfs", **kw)["aprovado"])
            self.assertFalse(self.m.portao_do_canario(area, fs_raiz="ext4", **{**kw, "claude_sha256": "e" * 64})[
                "aprovado"])
            self.assertFalse(self.m.portao_do_canario(area, fs_raiz="ext4", **{**kw, "claude_versao": None})["aprovado"])
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_ficha_valida_sem_canario_fecha_tudo(self):
        aberta = {**self.m.aberturas_fechadas(), "valida": True, "versao": 3, "rede": ["pypi.org"],
                  "webfetch": ["pypi.org"], "websearch": True}
        fechada = self.m.com_canario(aberta, {"aprovado": False, "motivo": "sem canário"})
        self.assertFalse(fechada["valida"])
        self.assertEqual((fechada["rede"], fechada["webfetch"], fechada["websearch"]), ([], [], False))
        self.assertIn("canário", fechada["motivo"])
        self.assertIs(self.m.com_canario(aberta, {"aprovado": True}), aberta)


class AvisoDaClaudeDoProjeto(unittest.TestCase):
    """I19 (segunda rodada da integração): o aviso do lançador sobre `projects/<p>/.claude/<sub>` não promete medida que
    o canário não faz. O `conclusao.carga_aninhada` cobre a skill e o agente de uma `.claude/` numa subpasta do projeto
    do ensaio (`aninhado/.claude/`), não a `.claude/` do próprio projeto, que o ensaio não tem; o texto antigo dizia
    "(medido no canário)". A conferência do lançador roda com uma área mínima (o aviso não depende do resto da área, e
    os problemas dela não importam aqui): em qualquer sistema."""

    SUBPASTAS = ("skills", "agents", "commands", "hooks")

    def setUp(self):
        self.m = carregar_preparo()
        self.base = Path(tempfile.mkdtemp(prefix="aviso-claude-1710-")).resolve()
        self.raiz = self.base / "Fundacao Ensaio"
        self.proj = self.raiz / "projects" / "caso-real"
        self.proj.mkdir(parents=True)
        self.area = self.base / "area" / "projetos" / "caso-real"
        self.area.mkdir(parents=True)
        hashes = {"schema_version": self.m.ESQUEMA_HASHES, "projeto": "caso-real", "raiz": self.raiz.as_posix(),
                  "gerenciadas": (self.base / "sem-gerenciadas").as_posix()}  # nada do /etc da máquina
        (self.area / "hashes.json").write_text(json.dumps(hashes), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def avisos_da_pasta(self) -> list:
        """Os avisos da conferência do lançador sobre a `.claude/` do projeto."""
        avisos = self.m.conferir_abertura(self.raiz, "caso-real", self.area)["avisos"]
        return [a for a in avisos if a.startswith("projects/caso-real/.claude/")]

    def test_cada_subpasta_avisa_sem_prometer_a_medida_do_canario(self):
        for sub in self.SUBPASTAS:
            with self.subTest(sub):
                (self.proj / ".claude" / sub).mkdir(parents=True)
                try:
                    avisos = self.avisos_da_pasta()
                finally:
                    shutil.rmtree(self.proj / ".claude")
                self.assertEqual(len(avisos), 1, avisos)
                aviso = avisos[0]
                self.assertTrue(aviso.startswith(f"projects/caso-real/.claude/{sub} existe: "), aviso)
                self.assertIn("com --setting-sources local não deve carregar", aviso)  # a expectativa continua
                self.assertNotIn("medido no canário", aviso)  # o texto antigo: o canário não mede esta pasta
                self.assertIn(AVISO_DO_CANARIO, aviso)
                self.assertIn("não ponha peças ali, use a ficha (plugins)", aviso)

    def test_sem_as_subpastas_nao_avisa(self):
        self.assertEqual(self.avisos_da_pasta(), [])
        (self.proj / ".claude" / "outra").mkdir(parents=True)
        self.assertEqual(self.avisos_da_pasta(), [])

    def test_o_que_o_aviso_diz_do_canario_e_o_que_o_ensaio_mede(self):
        """O aviso confere com `scripts/ensaio_isolamento_wsl.py`: o item da carga (classe `carga`, fora de
        `confina_comandos`) abre a sessão com `--setting-sources local` (e o controle com `local,project`) e usa uma
        `.claude/` em subpasta do projeto do ensaio, só com skills/ e agents/; nada do ensaio fica na `.claude/` do
        próprio projeto. Se o ensaio passar a medir esta pasta, o aviso muda junto."""
        ensaio = carregar_ensaio()
        base = self.base / "canario"  # só caminhos: nada é criado
        c = ensaio._caminhos(base)
        medida = c["an_claude"].relative_to(c["a"]).as_posix()
        self.assertEqual(medida, "aninhado/.claude")
        itens = ensaio._itens_do_ensaio(base)
        todos = [*itens["pastas"], *itens["arquivos"], *itens["artefatos"], *itens["pastas_artefato"]]
        propria = c["a"] / ".claude"
        self.assertEqual([p for p in todos if p == propria or propria in p.parents], [])
        com_claude = [p.relative_to(c["a"]).parts for p in todos
                      if c["a"] in p.parents and ".claude" in p.relative_to(c["a"]).parts]
        self.assertTrue(com_claude)
        for partes in com_claude:
            self.assertEqual(partes[:2], ("aninhado", ".claude"), partes)
        self.assertEqual({partes[2] for partes in com_claude if len(partes) > 2}, {"skills", "agents"})
        sonda = next(s for s in ensaio.SONDAS if s["id"] == "skill_agente_aninhado")
        self.assertEqual(sonda["classe"], "carga")
        sessoes = sonda["sessoes"](base, {}, "n0", {})
        self.assertEqual([s.get("setting_sources", "local") for s in sessoes], ["local", "local,project"])
        (self.proj / ".claude" / "skills").mkdir(parents=True)
        aviso, = self.avisos_da_pasta()
        self.assertIn(f"numa subpasta ({medida}/, só skill e agente), não esta pasta", aviso)


@unittest.skipUnless(LINUX, "a área do titular é do Ubuntu (WSL2): instalar-canario e instalar-projeto só no Linux")
class PortaoNoPreparo(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="canario-preparo-1710-")).resolve()
        self.skill = skill_de_ensaio(self.base)
        self.raiz = raiz_de_ensaio(self.base, self.skill)
        (self.base / "home").mkdir()
        self.claude = claude_de_ensaio(self.base / "claude-ensaio")
        self.m = carregar_preparo(self.skill)
        self.area = self.base / "area" / "projetos" / "caso-real"
        self.canario = self.base / "area" / "canario" / "2.1.302.json"
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 1, rede={"dominios": ["pypi.org"]},
                                                                      webfetch={"dominios": ["pypi.org"]}))

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def instalar(self, codigo=0):
        r = instalar(self.skill, self.raiz, self.base, "caso-real", self.claude)
        self.assertEqual(r.returncode, codigo, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def ler(self, nome):
        return json.loads((self.area / nome).read_text(encoding="utf-8"))

    def test_sem_canario_a_ficha_fica_instalada_mas_nao_vale(self):
        rel = self.instalar()
        self.assertFalse(rel["canario"]["aprovado"])
        self.assertTrue(any("sem canário aprovado" in a for a in rel["avisos"]), rel["avisos"])
        self.assertTrue((self.area / "ficha" / "ficha-v1.json").is_file())  # instalada, não aplicada
        perfil = self.ler("settings.wsl.json")
        self.assertEqual(perfil["sandbox"]["network"]["allowedDomains"], [])
        self.assertIn("WebFetch", perfil["permissions"]["deny"])
        aberturas = self.ler("aberturas.json")
        self.assertFalse(aberturas["valida"])
        self.assertIn("canário", aberturas["motivo"])
        hashes = self.ler("hashes.json")
        self.assertIsNone(hashes["ficha"])
        self.assertFalse(hashes["canario"]["aprovado"])
        self.assertTrue(self.m.conferir_abertura(self.raiz, "caso-real", self.area)["ok"])

    def test_canario_aprovado_aplica_a_ficha_e_fica_fixado(self):
        r = instalar_canario(self.skill, self.base, relatorio_de_canario(self.m, self.raiz, self.claude))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["acao"], "criar")
        r = instalar_canario(self.skill, self.base, relatorio_de_canario(self.m, self.raiz, self.claude))
        self.assertEqual(json.loads(r.stdout)["acao"], "igual")
        rel = self.instalar()
        self.assertTrue(rel["canario"]["aprovado"], rel["canario"])
        self.assertEqual(self.ler("settings.wsl.json")["sandbox"]["network"]["allowedDomains"], ["pypi.org"])
        hashes = self.ler("hashes.json")
        self.assertEqual(hashes["arquivos"][self.canario.as_posix()], sha(self.canario))
        self.assertEqual(hashes["claude"]["sha256"], sha(self.claude))
        self.assertTrue(self.m.conferir_abertura(self.raiz, "caso-real", self.area)["ok"])
        dados = json.loads(self.canario.read_text(encoding="utf-8"))
        dados["data"] = "2026-11-01T00:00:00Z"  # trocado depois do preparo (na área real, só o root grava ali)
        self.canario.write_text(json.dumps(dados), encoding="utf-8")
        res = self.m.conferir_abertura(self.raiz, "caso-real", self.area)
        self.assertFalse(res["ok"])
        self.assertTrue(any("2.1.302.json" in p for p in res["problemas"]), res)

    def test_com_o_canario_aprovado_o_aviso_da_claude_do_projeto_nao_diz_que_ele_a_mediu(self):
        """I19: o canário aprovado (fixado no hashes.json) não tem item para a `.claude/` do projeto. Com ela, a sessão
        abre (só aviso), e o aviso diz o que o canário mede, sem o "(medido no canário)" de antes."""
        r = instalar_canario(self.skill, self.base, relatorio_de_canario(self.m, self.raiz, self.claude))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.instalar()["canario"]["aprovado"])
        (self.raiz / "projects" / "caso-real" / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
        res = self.m.conferir_abertura(self.raiz, "caso-real", self.area)
        self.assertTrue(res["ok"], res)
        avisos = [a for a in res["avisos"] if a.startswith("projects/caso-real/.claude/")]
        self.assertEqual(len(avisos), 1, res["avisos"])
        self.assertNotIn("medido no canário", avisos[0])
        self.assertIn(AVISO_DO_CANARIO, avisos[0])

    def test_canario_de_outro_binario_ou_de_outra_forma_nao_vale(self):
        claude = {"binario": "/x/claude", "versao": "2.1.302", "sha256": "0" * 64}
        outra_forma = ({"forma": "drvfs:/mnt/e/ensaio", "sistema_de_arquivos": "9p"}
                       if self.m.tipo_de_fs(self.raiz) == "ext4" else {"forma": "ext4", "sistema_de_arquivos": "ext4"})
        outra_forma["conclusao"] = {**outra_forma, "confina_comandos": True}
        for nome, mudancas in (("outro binário", {"claude": claude}), ("outra forma de caminho", outra_forma)):
            with self.subTest(nome):
                rel = relatorio_de_canario(self.m, self.raiz, self.claude)
                rel.update(mudancas)
                r = instalar_canario(self.skill, self.base, rel)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # válido sozinho; o preparo confere o resto
                rel = self.instalar()
                self.assertFalse(rel["canario"]["aprovado"], rel["canario"])
                self.assertEqual(self.ler("settings.wsl.json")["sandbox"]["network"]["allowedDomains"], [])

    def test_instalar_canario_recusa_o_que_nao_e_relatorio_real_e_nao_grava(self):
        """Só o que não é relatório real do ensaio é recusado. Desde a 1.7.10.1 (pedido do titular de 02/11/2026,
        DECISAO-007), o relatório real que não prova o confinamento vai como revogação: ver o teste abaixo."""
        casos = {"simulação": {"simulado": True},
                 "outro esquema": {"schema_version": "fundacao.ensaio_isolamento_simulado/1"},
                 "sem a conclusão": {"conclusao": {"forma": None}}}
        for nome, mudancas in casos.items():
            with self.subTest(nome):
                r = instalar_canario(self.skill, self.base, relatorio_de_canario(self.m, self.raiz, self.claude,
                                                                                 **mudancas))
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("recusado", r.stdout)
                self.assertFalse(self.canario.exists())

    def test_relatorio_real_reprovado_vai_como_revogacao_e_fecha_a_ficha_aprovada(self):
        """1.7.10.1 (a direção do CAN-2 do lote B): o relatório real com false ou null substitui o aprovado da mesma
        versão do Claude Code; o lançador recusa abrir até o preparo, que fecha as aberturas (sem aceite de risco)."""
        r = instalar_canario(self.skill, self.base, relatorio_de_canario(self.m, self.raiz, self.claude))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.instalar()["canario"]["aprovado"])
        for confina in (False, None):
            with self.subTest(confina=confina):
                forma = relatorio_de_canario(self.m, self.raiz, self.claude)["forma"]
                ruim = relatorio_de_canario(self.m, self.raiz, self.claude, conclusao={
                    "forma": forma, "confina_comandos": confina, "motivo": "leitura_outro_projeto falhou"},
                    data=f"2026-11-02T00:00:0{int(confina is None)}Z")
                r = instalar_canario(self.skill, self.base, ruim)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                saida = json.loads(r.stdout)
                self.assertEqual((saida["aprovado"], saida["acao"]), (False, "atualizar"), saida)
                self.assertIn("revogação", saida["proximo_passo"])
                self.assertEqual(sha(self.canario), sha(self.base / "relatorio-canario.json"))
                if confina is False:  # o lançador da área preparada com o aprovado recusa abrir
                    res = self.m.conferir_abertura(self.raiz, "caso-real", self.area)
                    self.assertFalse(res["ok"])
                rel = self.instalar()
                self.assertFalse(rel["canario"]["aprovado"], rel["canario"])
                self.assertTrue(rel["canario"]["reprovado"]["sha256"], rel["canario"])
                self.assertEqual(self.ler("settings.wsl.json")["sandbox"]["network"]["allowedDomains"], [])
                self.assertTrue(self.m.conferir_abertura(self.raiz, "caso-real", self.area)["ok"])

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "processo root: a recusa sem root não se aplica")
    def test_sem_root_e_sem_ensaio_recusa(self):
        import subprocess
        import sys
        from apoio import ENV
        arquivo = self.base / "relatorio.json"
        arquivo.write_text(json.dumps(relatorio_de_canario(self.m, self.raiz, self.claude)), encoding="utf-8")
        r = subprocess.run([sys.executable, "-I", "-B", str(self.skill / "assets" / "host" / "preparo_host.py"),
                            "instalar-canario", "--relatorio", str(arquivo)], capture_output=True, text=True, env=ENV,
                           timeout=120)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("sudo", r.stdout)

    def test_gerar_e_conferir_o_perfil_usam_o_mesmo_portao(self):
        import subprocess
        import sys
        from apoio import ENV

        def rodar(*args):
            return subprocess.run([sys.executable, "-I", "-B", str(self.skill / "assets" / "host" / "preparo_host.py"),
                                   *map(str, args)], capture_output=True, text=True, encoding="utf-8", env=ENV,
                                  timeout=120)
        comum = ("--raiz", self.raiz, "--projeto", "caso-real", "--perfil-windows", "/mnt/c/Users/<usuario>",
                 "--area-raiz", self.base / "area", "--temp-base", (self.base / "tmp").as_posix())
        for aprovado in (False, True):
            with self.subTest(aprovado=aprovado):
                if aprovado:
                    r = instalar_canario(self.skill, self.base, relatorio_de_canario(self.m, self.raiz, self.claude))
                    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.instalar()
                r = rodar("conferir-perfil-wsl", "--perfil", self.area / "settings.wsl.json", *comum)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                saida = self.base / f"gerado-{aprovado}.json"
                r = rodar("gerar-perfil-projeto", *comum, "--saida", saida)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(json.loads(saida.read_text(encoding="utf-8"))["sandbox"]["network"]["allowedDomains"],
                                 ["pypi.org"] if aprovado else [])


if __name__ == "__main__":
    unittest.main()
