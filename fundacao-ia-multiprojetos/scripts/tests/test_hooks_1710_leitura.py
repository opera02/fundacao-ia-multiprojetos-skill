"""`assets/hooks/guarda_leitura.py` (contratos do lote 2 da 1.7.10, §7): Read, Grep e Glob negados em
`<raiz>/projects/<x>/` (x diferente de FUNDACAO_PROJECT, sem caixa) e em `<raiz>/state/`, resolvendo o caminho
relativo ao `cwd` do evento, o `path` do Grep e o padrão do Glob; padrão que possa casar outro projeto (`projects/*/`,
`**` a partir da raiz ou de `projects/`, padrão sem pasta) é negado; `..`, ligação, unidade e `/mnt/<l>` traduzidos;
sem FUNDACAO_PROJECT, todo projects/ fica fechado; com FUNDACAO_SEM_DADOS=1, `projects/*/data/**` também.

Fundação fictícia em pasta temporária; as formas de caminho de outro sistema usam a unidade fictícia Q: (`/mnt/q`),
que não existe nos ambientes de teste.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from apoio import criar_ligacao_dir
from test_hooks_1710 import carregar, decisao, ferramenta, motivo

HOOK = "guarda_leitura.py"


class _Base(unittest.TestCase):
    def setUp(self):
        self.m = carregar(HOOK)
        self.base = Path(tempfile.mkdtemp(prefix="hook-leitura-teste-"))
        self.raiz = self.base / "fund"
        self.jur = self.raiz / "projects" / "juridico-lab"
        self.rev = self.raiz / "projects" / "reversa-lab"
        for pasta in (self.jur / "minutas", self.rev / "data", self.raiz / "state", self.raiz / "registry",
                      self.base / "fora"):
            pasta.mkdir(parents=True)
        self.env = {"FUNDACAO_PROJECT": "juridico-lab", "FUNDACAO_RAIZ": str(self.raiz)}

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def decide(self, tool, cwd=None, env=None, **entrada) -> str:
        evento = {"tool_name": tool, "tool_input": entrada, "cwd": str(cwd or self.raiz)}
        return "deny" if self.m.decide(evento, {**self.env, **(env or {})}) else "sem_decisao"


class Read(_Base):
    def test_proprio_projeto_e_fora_de_projects_seguem(self):
        for alvo in (self.jur / "minutas" / "a.md", self.jur / "nao-existe.md", self.raiz / "AGENTS.md",
                     self.raiz / "registry" / "x.json", self.base / "fora" / "x.md", self.raiz / "projects",
                     self.raiz / "stateX" / "a", self.raiz / "projects-antigos" / "reversa-lab" / "a"):
            with self.subTest(alvo=str(alvo)):
                self.assertEqual(self.decide("Read", file_path=str(alvo)), "sem_decisao")

    def test_outro_projeto_e_state_negados(self):
        for alvo in (self.rev / "data" / "a.pdf", self.rev, self.raiz / "state" / "state.sqlite", self.raiz / "state",
                     self.raiz / "projects" / "projeto-novo-qualquer" / "x"):
            with self.subTest(alvo=str(alvo)):
                self.assertEqual(self.decide("Read", file_path=str(alvo)), "deny")
        texto = motivo(HOOK, ferramenta("Read", file_path=str(self.rev / "x")), **self.env)
        self.assertIn("outro projeto", texto)
        self.assertIn("python -m fundacao", texto)

    def test_caixa_ponto_final_fluxo_e_dot_dot(self):
        for alvo in (str(self.raiz / "PROJECTS" / "Reversa-Lab" / "x"), str(self.raiz / "State" / "a"),
                     str(self.raiz / "projects" / "reversa-lab." / "x"), str(self.raiz / "projects." / "reversa-lab"),
                     str(self.raiz / "state::$INDEX_ALLOCATION" / "state.sqlite"),
                     str(self.raiz / "projects" / "reversa-lab:fluxo"),
                     str(self.jur / ".." / "reversa-lab" / "x"),
                     str(self.jur / "minutas" / ".." / ".." / ".." / "state")):
            with self.subTest(alvo=alvo):
                self.assertEqual(self.decide("Read", file_path=alvo), "deny")

    def test_relativo_ao_cwd_do_evento(self):
        self.assertEqual(self.decide("Read", cwd=self.jur, file_path="../reversa-lab/data/a.pdf"), "deny")
        self.assertEqual(self.decide("Read", cwd=self.jur, file_path="..\\reversa-lab\\a.pdf"), "deny")
        self.assertEqual(self.decide("Read", cwd=self.jur, file_path="../../state/x"), "deny")
        self.assertEqual(self.decide("Read", cwd=self.jur, file_path="minutas/a.md"), "sem_decisao")
        self.assertEqual(self.decide("Read", cwd=self.raiz, file_path="projects/reversa-lab/x"), "deny")
        self.assertEqual(self.decide("Read", cwd=self.raiz, file_path="projects/juridico-lab/x"), "sem_decisao")

    def test_ligacao_no_proprio_projeto_para_outro_projeto_e_negada(self):
        criar_ligacao_dir(self.jur / "atalho", self.rev)
        self.assertEqual(self.decide("Read", file_path=str(self.jur / "atalho" / "data" / "a.pdf")), "deny")
        criar_ligacao_dir(self.base / "fora" / "estado", self.raiz / "state")
        self.assertEqual(self.decide("Read", file_path=str(self.base / "fora" / "estado" / "x")), "deny")

    def test_raiz_por_ligacao_definida_pelo_lancador(self):
        atalho = self.base / "raiz-atalho"
        criar_ligacao_dir(atalho, self.raiz)
        env = {"FUNDACAO_RAIZ": str(atalho)}
        self.assertEqual(self.decide("Read", env=env, file_path=str(self.rev / "x")), "deny")
        self.assertEqual(self.decide("Read", env=env, file_path=str(atalho / "projects" / "reversa-lab" / "x")), "deny")
        self.assertEqual(self.decide("Read", env=env, file_path=str(atalho / "projects" / "juridico-lab" / "x")),
                         "sem_decisao")

    def test_formas_de_outro_sistema_traduzidas(self):
        env = {"FUNDACAO_RAIZ": "Q:\\IA\\fundacao"}
        for alvo in ("/mnt/q/IA/fundacao/projects/reversa-lab/x", "Q:/IA/fundacao/projects/reversa-lab/x",
                     "q:\\ia\\FUNDACAO\\projects\\reversa-lab\\x", "\\\\?\\Q:\\IA\\fundacao\\projects\\reversa-lab\\x",
                     "//mnt/q/IA/fundacao/state/x", "\\\\.\\Q:\\IA\\fundacao\\state\\x"):
            with self.subTest(alvo=alvo):
                self.assertEqual(self.decide("Read", env=env, file_path=alvo), "deny")
        env = {"FUNDACAO_RAIZ": "/mnt/q/IA/fundacao"}
        self.assertEqual(self.decide("Read", env=env, file_path="Q:\\IA\\fundacao\\projects\\reversa-lab\\x"), "deny")
        self.assertEqual(self.decide("Read", env=env, file_path="Q:\\IA\\fundacao\\projects\\juridico-lab\\x"),
                         "sem_decisao")

    def test_sem_projeto_valido_fecha_todo_projects(self):
        for projeto in (None, "", " ", ".", "..", "../reversa-lab", "juridico-lab/x", "juridico-lab\\x", "a..b",
                        "juridico-lab.", "*"):
            env = dict(self.env)
            env.pop("FUNDACAO_PROJECT")
            if projeto is not None:
                env["FUNDACAO_PROJECT"] = projeto
            evento = {"tool_name": "Read", "tool_input": {"file_path": str(self.jur / "a.md")}, "cwd": str(self.raiz)}
            with self.subTest(projeto=projeto):
                self.assertTrue(self.m.decide(evento, env))
                evento["tool_input"]["file_path"] = str(self.raiz / "registry" / "x.json")
                self.assertIsNone(self.m.decide(evento, env))

    def test_raiz_sem_fundacao_raiz_pelo_diretorio_do_projeto(self):
        # Sessão aberta em projects/<p> sem FUNDACAO_RAIZ: a pasta de cima de projects/ também vale como raiz.
        env = {"FUNDACAO_PROJECT": "juridico-lab", "CLAUDE_PROJECT_DIR": str(self.jur)}
        evento = {"tool_name": "Read", "tool_input": {"file_path": str(self.rev / "x")}, "cwd": str(self.jur)}
        self.assertTrue(self.m.decide(evento, env))
        evento["tool_input"]["file_path"] = str(self.jur / "x")
        self.assertIsNone(self.m.decide(evento, env))
        env = {"FUNDACAO_PROJECT": "juridico-lab", "CLAUDE_PROJECT_DIR": str(self.raiz)}
        evento["tool_input"]["file_path"] = str(self.raiz / "state" / "x")
        self.assertTrue(self.m.decide(evento, env))


class SemDados(_Base):
    def test_pasta_de_dados_negada_inclusive_a_do_proprio_projeto(self):
        (self.jur / "data").mkdir()
        env = {"FUNDACAO_SEM_DADOS": "1"}
        self.assertEqual(self.decide("Read", env=env, file_path=str(self.jur / "data" / "a.pdf")), "deny")
        self.assertEqual(self.decide("Read", env=env, file_path=str(self.jur / "Data" / "a.pdf")), "deny")
        self.assertEqual(self.decide("Glob", env=env, path=str(self.jur), pattern="**/*.pdf"), "deny")
        self.assertEqual(self.decide("Read", env=env, file_path=str(self.jur / "minutas" / "a.md")), "sem_decisao")
        self.assertEqual(self.decide("Glob", env=env, path=str(self.jur / "minutas"), pattern="**"), "sem_decisao")
        self.assertEqual(self.decide("Read", file_path=str(self.jur / "data" / "a.pdf")), "sem_decisao")
        self.assertIn("FUNDACAO_SEM_DADOS", motivo(HOOK, ferramenta("Read", file_path=str(self.jur / "data" / "a")),
                                                   FUNDACAO_SEM_DADOS="1", **self.env))

    def test_sem_a_pasta_de_dados_propria(self):
        # No Windows (NTFS, sem caixa) a busca no próprio projeto segue enquanto não houver data/; nos demais, vale.
        esperado = "sem_decisao" if os.name == "nt" else "deny"
        self.assertEqual(self.decide("Glob", env={"FUNDACAO_SEM_DADOS": "1"}, path=str(self.jur), pattern="**"),
                         esperado)
        self.assertEqual(self.decide("Glob", env={"FUNDACAO_SEM_DADOS": "0"}, path=str(self.jur), pattern="**"),
                         "sem_decisao")


class Glob(_Base):
    def test_padroes_que_podem_casar_outro_projeto_sao_negados(self):
        for padrao in ("**/*.md", "*", "*.md", "AGENTS.md", "./*.md", "projects/*/INSTRUCOES.md", "projects/**",
                       "projects/**/x", "projects/reversa-lab/**", "Projects/Reversa-Lab/*", "projects/r*/x",
                       "projects/[a-z]*/x", "p*/r*/**", "s*/**", "state/*", "**/state/x",
                       "{registry,projects/reversa-lab}/**", "projects/{juridico-lab,reversa-lab}/*",
                       "{a,{b,projects/reversa-lab}}/x", "projects/juridico-lab/../reversa-lab/*",
                       "projects/@(reversa-lab)/*", "projects\\reversa-lab\\*", "./projects/./reversa-lab/x"):
            with self.subTest(padrao=padrao):
                self.assertEqual(self.decide("Glob", pattern=padrao), "deny")
        texto = motivo(HOOK, {**ferramenta("Glob", pattern="**/*.md"), "cwd": str(self.raiz)}, **self.env)
        self.assertIn("restrinja", texto)
        self.assertIn("projects/juridico-lab/", texto)

    def test_padroes_que_nao_saem_do_lugar_seguem(self):
        for padrao in ("registry/*.json", "projects/juridico-lab/**", "projects/juridico-lab/**/*.md",
                       "projects/JURIDICO-LAB/minutas/*", "docs/**/*.md", "registry/**", "{registry,docs}/*.json",
                       "stateX/**", "projects/juridico-lab"):
            with self.subTest(padrao=padrao):
                self.assertEqual(self.decide("Glob", pattern=padrao), "sem_decisao")

    def test_padrao_que_casa_a_propria_pasta_de_outro_projeto_e_negado(self):
        # Conservador: `projects/*` casa a pasta de cada projeto (não só arquivos soltos em projects/).
        for padrao in ("projects/*", "projects/*.md", "projects/?eversa-lab"):
            with self.subTest(padrao=padrao):
                self.assertEqual(self.decide("Glob", pattern=padrao), "deny")

    def test_pasta_de_busca(self):
        self.assertEqual(self.decide("Glob", path=str(self.jur), pattern="**/*.md"), "sem_decisao")
        self.assertEqual(self.decide("Glob", path=str(self.jur), pattern="*"), "sem_decisao")
        self.assertEqual(self.decide("Glob", path=str(self.rev), pattern="*.md"), "deny")
        self.assertEqual(self.decide("Glob", path=str(self.raiz / "projects"), pattern="*/x.md"), "deny")
        self.assertEqual(self.decide("Glob", path=str(self.raiz / "projects"), pattern="juridico-lab/*"),
                         "sem_decisao")
        self.assertEqual(self.decide("Glob", path=str(self.base), pattern="**/*.md"), "deny")  # acima da raiz
        self.assertEqual(self.decide("Glob", path=str(self.base / "fora"), pattern="**/*.md"), "sem_decisao")
        self.assertEqual(self.decide("Glob", cwd=self.jur, path="..", pattern="*/x"), "deny")
        self.assertEqual(self.decide("Glob", path=str(self.jur), pattern="../*/x"), "deny")
        self.assertEqual(self.decide("Glob", path=str(self.jur), pattern="../juridico-lab/*"), "sem_decisao")

    def test_padrao_absoluto(self):
        self.assertEqual(self.decide("Glob", path=str(self.base / "fora"),
                                     pattern=str(self.raiz / "projects" / "*" / "x.md")), "deny")
        self.assertEqual(self.decide("Glob", path=str(self.base / "fora"), pattern=str(self.raiz) + "/**"), "deny")
        self.assertEqual(self.decide("Glob", path=str(self.base / "fora"), pattern=str(self.jur) + "/**"),
                         "sem_decisao")
        self.assertEqual(self.decide("Glob", env={"FUNDACAO_RAIZ": "Q:\\IA\\fundacao"},
                                     pattern="/mnt/q/IA/fundacao/projects/*/x"), "deny")

    def test_ligacao_no_trecho_literal_do_padrao(self):
        criar_ligacao_dir(self.jur / "atalho", self.rev)
        self.assertEqual(self.decide("Glob", path=str(self.jur), pattern="atalho/**"), "deny")
        self.assertEqual(self.decide("Glob", path=str(self.jur / "atalho"), pattern="*.md"), "deny")

    def test_padrao_sem_leitura_simples_nega(self):
        self.assertEqual(self.decide("Glob", path=str(self.jur), pattern="**/../../reversa-lab/x"), "deny")
        self.assertEqual(self.decide("Glob", path=str(self.jur), pattern="{a,b}" * 7 + "/x"), "deny")  # 128 expansões
        self.assertEqual(self.decide("Glob", path=str(self.jur), pattern="{a,b}" * 5 + "/x"), "sem_decisao")


class Grep(_Base):
    def test_busca_a_partir_da_raiz_ou_de_projects_e_negada(self):
        self.assertEqual(self.decide("Grep", pattern="x"), "deny")  # sem path: a pasta atual (a raiz)
        self.assertEqual(self.decide("Grep", pattern="x", path=str(self.raiz)), "deny")
        self.assertEqual(self.decide("Grep", pattern="x", path=str(self.raiz / "projects")), "deny")
        self.assertEqual(self.decide("Grep", pattern="x", path=str(self.rev)), "deny")
        self.assertEqual(self.decide("Grep", pattern="x", path=str(self.raiz / "state")), "deny")
        self.assertEqual(self.decide("Grep", pattern="x", path=str(self.raiz / "state" / "state.sqlite")), "deny")
        self.assertIn("restrinja", motivo(HOOK, {**ferramenta("Grep", pattern="x"), "cwd": str(self.raiz)},
                                          **self.env))

    def test_busca_no_proprio_projeto_ou_fora_de_projects_segue(self):
        for pasta in (self.jur, self.jur / "minutas", self.raiz / "registry", self.raiz / "AGENTS.md",
                      self.base / "fora"):
            with self.subTest(pasta=str(pasta)):
                self.assertEqual(self.decide("Grep", pattern="x", path=str(pasta)), "sem_decisao")
        self.assertEqual(self.decide("Grep", cwd=self.jur, pattern="x"), "sem_decisao")

    def test_filtro_glob(self):
        raiz = str(self.raiz)
        self.assertEqual(self.decide("Grep", pattern="x", path=raiz, glob="projects/juridico-lab/**"), "sem_decisao")
        self.assertEqual(self.decide("Grep", pattern="x", path=raiz, glob="registry/*.json"), "sem_decisao")
        for filtro in ("*.md", "*.{ts,tsx}", "**/*.py", "projects/*/x", "!**/node_modules/**", "!x", "",
                       "projects/reversa-lab/**"):
            with self.subTest(filtro=filtro):
                self.assertEqual(self.decide("Grep", pattern="x", path=raiz, glob=filtro), "deny")
        self.assertEqual(self.decide("Grep", pattern="x", path=str(self.jur), glob="*.md"), "sem_decisao")


class EntradaRuim(_Base):
    def test_campo_ausente_ou_de_tipo_errado_nega(self):
        for evento in (ferramenta("Read"), ferramenta("Read", file_path=""), ferramenta("Read", file_path=7),
                       ferramenta("Glob"), ferramenta("Glob", pattern=""), ferramenta("Glob", pattern=["*"]),
                       ferramenta("Grep", pattern="x", path=7), ferramenta("Grep", pattern="x", glob=["*.md"]),
                       {"tool_name": "Read", "tool_input": "x"}, {"tool_name": "Read"},
                       ferramenta("Read", file_path="a\x00b")):
            with self.subTest(evento=evento):
                self.assertEqual(decisao(HOOK, evento, **self.env), "deny")

    def test_outras_ferramentas_sem_decisao(self):
        for evento in (ferramenta("Write", file_path=str(self.rev / "x")), ferramenta("Bash", command="cat x"),
                       ferramenta("ReadMcpResourceTool", uri="x"), ferramenta("LS", path=str(self.rev))):
            with self.subTest(evento=evento["tool_name"]):
                self.assertEqual(decisao(HOOK, evento, **self.env), "sem_decisao")

    def test_ponta_a_ponta_pelo_processo(self):
        self.assertEqual(decisao(HOOK, ferramenta("Read", file_path=str(self.rev / "x")), **self.env), "deny")
        self.assertEqual(decisao(HOOK, ferramenta("Read", file_path=str(self.jur / "x")), **self.env), "sem_decisao")
        evento = {**ferramenta("Glob", pattern="*.md"), "cwd": str(self.raiz)}
        self.assertEqual(decisao(HOOK, evento, **self.env), "deny")

    def test_til_vira_a_pasta_pessoal(self):
        pessoal = {"HOME": str(self.raiz), "USERPROFILE": str(self.raiz)}
        self.assertEqual(decisao(HOOK, ferramenta("Read", file_path="~/projects/reversa-lab/x"), **self.env,
                                 **pessoal), "deny")
        self.assertEqual(decisao(HOOK, ferramenta("Glob", path=str(self.base / "fora"), pattern="~/state/*"),
                                 **self.env, **pessoal), "deny")
        self.assertEqual(decisao(HOOK, ferramenta("Read", file_path="~/registry/x.json"), **self.env, **pessoal),
                         "sem_decisao")


if __name__ == "__main__":
    unittest.main()
