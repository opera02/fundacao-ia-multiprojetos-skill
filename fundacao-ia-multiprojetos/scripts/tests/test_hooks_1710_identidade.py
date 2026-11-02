"""`assets/hooks/guarda_identidade.py` na 1.7.10 (contratos do lote 2, §7): além da troca de identidade, nega o comando
Bash ou PowerShell que cite caminho de outro projeto (`projects/<x>/`, `projects\\<x>\\`, x diferente de
FUNDACAO_PROJECT, sem caixa), rotulado como guarda-corpo: o shell pode montar o caminho e a barreira é o sandbox onde
ele confina. Também: `..` depois do próprio projeto e `../<x>` a partir de um `cwd` dentro dele; a raiz dentro de uma
pasta `projects/` não conta; URL http(s) não conta; entrada vazia nega (falha fechada).

As formas de atribuição da identidade continuam negadas (regressão da conferência da 1.4.3, CF-01, e do CEN-13); o
nome da variável é montado aqui por concatenação, como nos demais testes.
"""

from __future__ import annotations

import unittest

from test_hooks_1710 import carregar, decisao, ferramenta, motivo

HOOK = "guarda_identidade.py"
IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"
RAIZ_W = "Q:\\IA\\fundacao"
RAIZ_L = "/mnt/q/IA/fundacao"


class _Base(unittest.TestCase):
    def setUp(self):
        self.m = carregar(HOOK)
        self.env = {"FUNDACAO_PROJECT": "juridico-lab", "FUNDACAO_RAIZ": RAIZ_W}

    def decide(self, comando, tool="Bash", cwd=None, **env) -> str:
        evento = {"tool_name": tool, "tool_input": {"command": comando}}
        if cwd:
            evento["cwd"] = cwd
        return "deny" if self.m.decide(evento, {**self.env, **env}) else "sem_decisao"


class OutroProjeto(_Base):
    def test_citacao_de_outro_projeto_e_negada(self):
        for comando in ("cat projects/reversa-lab/data/a.pdf", "cat projects\\reversa-lab\\a.md",
                        "type PROJECTS\\Reversa-Lab\\a.md", 'cat "Q:/IA/fundacao/projects/reversa-lab/a"',
                        "cat '/mnt/q/IA/fundacao/projects/reversa-lab/a'",
                        "cat /mnt/q/IA/fundacao/projects/reversa-lab", "cp -r projects/reversa-lab /tmp/x",
                        "ls projects/reversa-lab", "python -m x --origem=projects/x",
                        "rg segredo projects/*/data", "cat projects/{juridico-lab,reversa-lab}/a", "cat projects/$P/a",
                        "cat projects/./reversa-lab/a", "cat projects//reversa-lab/a", 'cat "projects/"reversa-lab/a',
                        "echo x > projects/reversa-lab/a", "cat file:///mnt/q/IA/fundacao/projects/reversa-lab/a",
                        "tar cf - x | (cd projects/reversa-lab && tar xf -)", "cat projects/reversa-lab.",
                        "cat projects/juridico-lab-antigo/a", "cat projects/juridico/a"):
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando), "deny")
        texto = motivo(HOOK, ferramenta("Bash", command="cat projects/reversa-lab/a"), **self.env)
        for trecho in ("guarda-corpo", "outro projeto", "projects/reversa-lab", "python -m fundacao"):
            self.assertIn(trecho, texto)

    def test_proprio_projeto_e_comandos_comuns_seguem(self):
        for comando in ("cat projects/juridico-lab/minuta.md", "cat PROJECTS/Juridico-Lab/minuta.md",
                        "ls projects/", "ls projects", "python -m fundacao status", "git status",
                        'git -C "Q:/IA/fundacao/projects/juridico-lab/trabalho" status',
                        "cat projects/juridico-lab/src/projects/lista.js",
                        "cat /mnt/q/IA/fundacao/projects/juridico-lab/x",
                        "curl https://gitlab.exemplo/api/v4/projects/123/issues",
                        "python -m x --url=https://gitlab.exemplo/api/v4/projects/7", "echo myprojects/x",
                        "cat .projects/x", "cat ~/projects-velhos/x"):
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando), "sem_decisao")

    def test_dot_dot_depois_do_proprio_projeto(self):
        for comando in ("cat projects/juridico-lab/../reversa-lab/a", "cat projects/juridico-lab/x/../../reversa-lab/a",
                        'cat "projects/juridico-lab/a b/../../reversa-lab/a"',
                        "cat projects/juridico-lab/a\\ b/../../reversa-lab/a",
                        "cat Q:\\IA\\fundacao\\projects\\juridico-lab\\..\\reversa-lab\\a",
                        "cat projects/juridico-lab/.. /reversa-lab"):
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando), "deny")

    def test_relativo_com_dot_dot_a_partir_do_proprio_projeto(self):
        cwd = RAIZ_L + "/projects/juridico-lab/minutas"
        for comando in ("cat ../../reversa-lab/a", "cat ..\\..\\reversa-lab\\a", "cat ./../../reversa-lab/a",
                        "python -m x --entrega=../../reversa-lab/a", "cat ../../../projects/reversa-lab/a"):
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando, cwd=cwd), "deny")
        for comando in ("cat ../a.md", "cd .. && ls", "cat ../../juridico-lab/a", "ls ../..", "cat ../../../AGENTS.md"):
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando, cwd=cwd), "sem_decisao")
        # cwd fora de projects/<p> (a raiz, no Windows): o `..` não é conferido aqui
        self.assertEqual(self.decide("cat ../x", cwd=RAIZ_W), "sem_decisao")

    def test_pasta_projects_relativa_dentro_do_proprio_projeto_e_negada(self):
        # Limite declarado: sem âncora, `src/projects/x` parece outro projeto; o caminho pelo projeto passa.
        self.assertEqual(self.decide("cat src/projects/lista.js"), "deny")
        self.assertIn("pelo caminho do projeto", motivo(HOOK, ferramenta("Bash", command="cat src/projects/lista.js"),
                                                        **self.env))

    def test_raiz_dentro_de_uma_pasta_projects(self):
        env = {"FUNDACAO_RAIZ": "Q:\\Usuarios\\u\\projects\\fund"}
        self.assertEqual(self.decide("cat Q:/Usuarios/u/projects/fund/projects/juridico-lab/a", **env), "sem_decisao")
        self.assertEqual(self.decide("cat /mnt/q/Usuarios/u/projects/fund/AGENTS.md", **env), "sem_decisao")
        self.assertEqual(self.decide("cat Q:/Usuarios/u/projects/fund/projects/reversa-lab/a", **env), "deny")
        self.assertEqual(self.decide("cat Q:/Usuarios/u/projects/outra-fund/x", **env), "deny")
        env = {"FUNDACAO_RAIZ": "", "CLAUDE_PROJECT_DIR": "Q:\\Usuarios\\u\\projects\\fund\\projects\\juridico-lab"}
        self.assertEqual(self.decide("cat Q:/Usuarios/u/projects/fund/projects/juridico-lab/a", **env), "sem_decisao")
        self.assertEqual(self.decide("cat Q:/Usuarios/u/projects/fund/projects/reversa-lab/a", **env), "deny")
        # aberta no próprio projeto sem FUNDACAO_RAIZ: o projeto não vira "raiz", e o `..` depois dele conta
        self.assertEqual(self.decide("cat Q:/Usuarios/u/projects/fund/projects/juridico-lab/../reversa-lab/a", **env),
                         "deny")

    def test_sem_projeto_valido_qualquer_projeto_e_negado(self):
        for projeto in (None, "", "..", "../reversa-lab", "a/b", "juridico-lab.", "*"):
            env = {k: v for k, v in self.env.items() if k != "FUNDACAO_PROJECT"}
            if projeto is not None:
                env["FUNDACAO_PROJECT"] = projeto
            evento = {"tool_name": "Bash", "tool_input": {"command": "cat projects/juridico-lab/a"}}
            with self.subTest(projeto=projeto):
                self.assertTrue(self.m.decide(evento, env))
                evento["tool_input"]["command"] = "python -m fundacao status"
                self.assertIsNone(self.m.decide(evento, env))
        self.assertIn("sem projeto da sessão", motivo(HOOK, ferramenta("Bash", command="cat projects/x/a")))

    def test_liberacao_da_troca_de_identidade_nao_libera_outro_projeto(self):
        self.assertEqual(self.decide("cat projects/reversa-lab/a", FUNDACAO_PERMITIR_TROCA_IDENTIDADE="1"), "deny")

    def test_powershell(self):
        for comando in ("Get-Content 'Q:\\IA\\fundacao\\projects\\reversa-lab\\a'",
                        "Get-ChildItem -Path:projects\\reversa-lab -Recurse",
                        "Get-Content Q:\\IA\\fundacao` dir\\projects\\juridico-lab\\a` b\\..\\..\\reversa-lab\\x",
                        "Get-Content 'Q:\\IA\\it''s\\projects\\reversa-lab\\a'",
                        'Get-Content "Q:\\IA\\fundacao\\projects\\reversa-lab\\a"'):
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando, tool="PowerShell"), "deny")
        self.assertEqual(self.decide('Get-Content "Q:\\IA\\fundacao\\projects\\juridico-lab\\a"', tool="PowerShell"),
                         "sem_decisao")

    def test_ponta_a_ponta(self):
        self.assertEqual(decisao(HOOK, ferramenta("Bash", command="cat projects/reversa-lab/a"), **self.env), "deny")
        self.assertEqual(decisao(HOOK, ferramenta("Bash", command="cat projects/juridico-lab/a"), **self.env),
                         "sem_decisao")
        self.assertEqual(decisao(HOOK, ferramenta("Read", file_path="projects/reversa-lab/a"), **self.env),
                         "sem_decisao")  # só Bash e PowerShell


class IdentidadeContinua(_Base):
    def test_atribuicoes_negadas_e_leituras_livres(self):
        negadas = [f"export {IDENTIDADE}=titular", f"{IDENTIDADE}=titular python -m fundacao status",
                   f"set {IDENTIDADE}=titular", f"unset {IDENTIDADE}"]
        for comando in negadas:
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando), "deny")
        for comando in (f"$env:{IDENTIDADE} = 'titular'", f"Set-Item -Path env:{IDENTIDADE} -Value titular",
                        f"Remove-Item 'env:{IDENTIDADE}'",
                        f"[Environment]::SetEnvironmentVariable('{IDENTIDADE}','x')"):
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando, tool="PowerShell"), "deny")
        for tool, comando in (("Bash", f'echo "${IDENTIDADE}"'), ("PowerShell", f"echo $env:{IDENTIDADE}"),
                              ("PowerShell", f"if ($env:{IDENTIDADE} -eq 'titular') {{ 'ok' }}")):
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando, tool=tool), "sem_decisao")
        self.assertIn(IDENTIDADE, motivo(HOOK, ferramenta("Bash", command=negadas[0]), **self.env))

    def test_liberacao_de_laboratorio_vale_so_para_a_identidade(self):
        self.assertEqual(self.decide(f"export {IDENTIDADE}=titular", FUNDACAO_PERMITIR_TROCA_IDENTIDADE="1"),
                         "sem_decisao")

    def test_entrada_vazia_ou_sem_ferramenta_nega(self):
        for entrada in (b"", b"{}", b'{"tool_input": {"command": "ls"}}', b'{"tool_name": "Bash", "tool_input": 7}'):
            with self.subTest(entrada=entrada):
                self.assertEqual(decisao(HOOK, entrada, **self.env), "deny")


if __name__ == "__main__":
    unittest.main()
