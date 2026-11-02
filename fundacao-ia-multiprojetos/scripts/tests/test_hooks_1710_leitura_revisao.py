"""Revisão independente do lote 2 da 1.7.10 sobre `assets/hooks/guarda_leitura.py`:
- o filtro `glob` do Grep vale como o Claude Code o passa ao ripgrep: dividido por espaço (o `\\s` do JavaScript) e,
  fora de `{...}`, por vírgula, um `--glob` por pedaço; `!` só exclui (sem pedaço positivo, a busca vale para tudo);
  só espaço = sem filtro. Cada pedaço e o filtro inteiro são conferidos;
- no Windows, caminho de rede ou de dispositivo (`\\\\srv\\c$`, `\\\\?\\UNC\\`, `\\\\?\\Volume{...}`,
  `\\\\wsl.localhost\\`) nega: não há como saber se chega à raiz (falha fechada); fora do Windows, `//` é `/`;
- sem FUNDACAO_RAIZ, a raiz sobe da pasta aberta em projects/<x> (CLAUDE_PROJECT_DIR e o cwd), qualquer x;
- fora do Windows, nome curto 8.3 numa unidade (`/mnt/q/IA/FUNDAC~1`) casa qualquer nome.

Fundação fictícia em pasta temporária; caminhos de rede fictícios (servidor localhost, unidade Q:), montados em tempo
de execução: o hook decide pelo texto, sem abrir nada.
"""

from __future__ import annotations

import os
import time
import unittest

from test_hooks_1710 import decisao, ferramenta, motivo
from test_hooks_1710_leitura import HOOK, _Base

B = chr(92)  # barra invertida
VOLUME = "Volume{00000000-0000-0000-0000-000000000000}"


class GlobDoGrep(_Base):
    def test_lista_por_virgula_ou_espaco_a_partir_da_raiz_e_negada(self):
        for filtro in ("registry/*.json,projects/reversa-lab/**", "registry/*.json projects/reversa-lab/**",
                       "registry/x,state/**", "registry/x,*.md", " ", "\t",
                       "registry/x" + chr(0xFEFF) + "projects/reversa-lab/**", "registry/x" + chr(0x3000) + "state/**",
                       "{registry/x,docs/y} projects/*/x", "!registry/**,!docs/**",
                       "registry/x, projects/reversa-lab/a"):
            with self.subTest(filtro=filtro):
                self.assertEqual(self.decide("Grep", pattern="senha", path=str(self.raiz), glob=filtro), "deny")
        texto = motivo(HOOK, ferramenta("Grep", pattern="x", path=str(self.raiz), glob="registry/x,state/**"),
                       **self.env)
        self.assertIn("state/", texto)

    def test_lista_que_nao_sai_do_lugar_segue(self):
        for filtro in ("*.md,*.py", "*.{ts,tsx}", "*.md *.py", "minutas/*.md,minutas/**/*.txt", "*.md,!minutas/**"):
            with self.subTest(filtro=filtro):
                self.assertEqual(self.decide("Grep", pattern="x", path=str(self.jur), glob=filtro), "sem_decisao")
        for filtro in ("registry/*.json docs/*.md", "registry/x,!y", "{registry,docs}/*.json"):
            with self.subTest(filtro=filtro):
                self.assertEqual(self.decide("Grep", pattern="x", path=str(self.raiz), glob=filtro), "sem_decisao")

    def test_divide_como_o_claude_code(self):
        dividir = self.m.filtros_do_grep
        self.assertEqual(dividir("a,b"), ["a", "b", "a,b"])
        self.assertEqual(dividir("*.{ts,tsx} x,y"), ["*.{ts,tsx}", "x", "y", "*.{ts,tsx} x,y"])
        self.assertEqual(dividir("{a, b}"), ["{a", "b}", "{a, b}"])  # o espaço divide antes das chaves
        for vazio in ("", " ", ",", " , "):
            self.assertEqual(dividir(vazio)[0], "**")
        self.assertEqual(dividir("!a,!b"), ["**"])
        self.assertEqual(dividir("a,!b"), ["a", "a,!b"])
        # o `\s` do JavaScript divide em U+FEFF e não em U+001C nem U+0085 (o do Python, ao contrário)
        self.assertEqual(dividir("a" + chr(0xFEFF) + "b")[:2], ["a", "b"])
        self.assertEqual(dividir("a\x1cb\x85c"), ["a\x1cb\x85c"])

    def test_pedacos_ou_chaves_demais_negam_longe_do_prazo(self):
        # Hook que estoura o prazo do perfil (10 s) não bloqueia: o filtro tem orçamento de 256 padrões.
        self.assertEqual(self.decide("Grep", pattern="x", path=str(self.jur), glob=",".join(["*.md"] * 257)), "deny")
        self.assertEqual(self.decide("Grep", pattern="x", path=str(self.jur), glob=",".join(["*.md"] * 256)),
                         "sem_decisao")
        self.assertEqual(self.decide("Grep", pattern="x", path=str(self.jur), glob=" ".join(["*.{a,b,c,d}"] * 65)),
                         "deny")
        inicio = time.monotonic()
        self.assertEqual(self.decide("Grep", pattern="x", path=str(self.jur),
                                     glob=" ".join(["{a,b}{c,d}{e,f}{g,h}{i,j}{k,l}/x"] * 64)), "deny")
        self.assertLess(time.monotonic() - inicio, 3)

    def test_texto_longo_demais_nega_longe_do_prazo(self):
        self.assertEqual(self.decide("Read", file_path=str(self.jur / ("a" * 4100))), "deny")
        self.assertEqual(self.decide("Grep", pattern="x", path=str(self.jur), glob="*.md," * 1000), "deny")
        inicio = time.monotonic()
        padrao = "{" + "x" * 1000000 + "{a,b}" * 7  # chave aberta: cada expansão varreria o texto inteiro
        self.assertEqual(self.decide("Glob", path=str(self.jur), pattern=padrao), "deny")
        self.assertEqual(self.decide("Grep", pattern="x", path=str(self.jur), glob=padrao), "deny")
        self.assertLess(time.monotonic() - inicio, 3)
        self.assertEqual(self.decide("Read", file_path=str(self.jur / ("a" * 200))), "sem_decisao")

    def test_ponta_a_ponta(self):
        evento = ferramenta("Grep", pattern="senha", path=str(self.raiz), glob="registry/x,*.md")
        self.assertEqual(decisao(HOOK, evento, **self.env), "deny")
        evento = ferramenta("Grep", pattern="senha", path=str(self.jur), glob="*.md,*.py")
        self.assertEqual(decisao(HOOK, evento, **self.env), "sem_decisao")


@unittest.skipUnless(os.name == "nt", "caminho de rede e de dispositivo: só no Windows")
class RedeNoWindows(_Base):
    def test_caminho_de_rede_ou_de_dispositivo_nega(self):
        env = {"FUNDACAO_RAIZ": "Q:" + B + "IA" + B + "fundacao"}
        for alvo in ("//localhost/Q$/IA/fundacao/projects/reversa-lab/x", "//?/UNC/localhost/Q$/IA/fundacao/state/x",
                     "//wsl.localhost/Ubuntu/mnt/q/IA/fundacao/projects/reversa-lab/x", "//127.0.0.1/Q$/x",
                     B * 2 + "localhost" + B + "Q$" + B + "IA" + B + "x", B * 2 + "wsl$" + B + "Ubuntu" + B + "home",
                     B * 2 + "?" + B + "UNC" + B + "localhost" + B + "Q$" + B + "x", B * 2 + "?" + B + VOLUME + B + "x",
                     B * 2 + "." + B + "pipe" + B + "x", B + "??" + B + "UNC" + B + "srv" + B + "c" + B + "x",
                     "//?/GLOBALROOT/Device/HarddiskVolume3/x"):
            with self.subTest(alvo=alvo):
                self.assertEqual(self.decide("Read", env=env, file_path=alvo), "deny")
        self.assertEqual(self.decide("Grep", env=env, pattern="x", path="//?/" + VOLUME + "/IA/fundacao/projects/"
                                                                         "reversa-lab"), "deny")
        self.assertEqual(self.decide("Glob", env=env, pattern="//localhost/Q$/IA/fundacao/**"), "deny")
        self.assertEqual(self.decide("Grep", pattern="x", path=str(self.jur), glob="*.md,//srv/c/**"), "deny")
        texto = motivo(HOOK, ferramenta("Read", file_path="//localhost/Q$/x"), **self.env)
        for trecho in ("guarda-corpo", "rede ou de dispositivo", "pela unidade"):
            self.assertIn(trecho, texto)

    def test_unidade_com_prefixo_de_dispositivo_segue_traduzida(self):
        for prefixo in (B * 2 + "?" + B, B * 2 + "." + B, B + "??" + B, "//?/"):
            with self.subTest(prefixo=prefixo):
                self.assertEqual(self.decide("Read", file_path=prefixo + str(self.jur / "a.md")), "sem_decisao")
                self.assertEqual(self.decide("Read", file_path=prefixo + str(self.rev / "a.md")), "deny")


@unittest.skipIf(os.name == "nt", "fora do Windows `//` é `/` (no Windows, caminho de rede)")
class BarraDuplaForaDoWindows(_Base):
    def test_barra_dupla_no_comeco_vale_como_uma(self):
        self.assertEqual(self.decide("Read", file_path="/" + str(self.rev / "x")), "deny")
        self.assertEqual(self.decide("Read", file_path="/" + str(self.jur / "x")), "sem_decisao")
        padrao = "/" + str(self.base.parent) + "/*/fund/projects/reversa-lab/*"  # curinga no lugar da pasta temporária
        self.assertEqual(self.decide("Glob", path=str(self.base / "fora"), pattern=padrao), "deny")


class RaizSemFundacaoRaiz(_Base):
    def sem_raiz(self, tool, cwd, env, **entrada) -> str:
        evento = {"tool_name": tool, "tool_input": entrada, "cwd": str(cwd)}
        return "deny" if self.m.decide(evento, env) else "sem_decisao"

    def test_aberta_no_projeto_sem_projeto_da_sessao_ou_com_outro(self):
        for env in ({"CLAUDE_PROJECT_DIR": str(self.jur)},
                    {"CLAUDE_PROJECT_DIR": str(self.jur), "FUNDACAO_PROJECT": "reversa-lab"}):
            with self.subTest(env=env):
                self.assertEqual(self.sem_raiz("Read", self.jur, env, file_path=str(self.raiz / "state" / "x")), "deny")
                self.assertEqual(self.sem_raiz("Read", self.jur, env, file_path=str(self.jur / "x.md")), "deny")
                self.assertEqual(self.sem_raiz("Read", self.jur, env, file_path="../../state/x"), "deny")
                self.assertEqual(self.sem_raiz("Read", self.jur, env, file_path=str(self.raiz / "registry" / "x")),
                                 "sem_decisao")
        env = {"CLAUDE_PROJECT_DIR": str(self.jur)}
        self.assertEqual(self.sem_raiz("Read", self.jur, env, file_path=str(self.rev / "x.md")), "deny")
        self.assertEqual(decisao(HOOK, {**ferramenta("Read", file_path=str(self.rev / "x")), "cwd": str(self.jur)},
                                 CLAUDE_PROJECT_DIR=str(self.jur)), "deny")

    def test_pela_pasta_atual(self):
        env = {"FUNDACAO_PROJECT": "juridico-lab"}  # sem CLAUDE_PROJECT_DIR: vale o cwd do evento
        pasta = self.raiz / "projects"
        self.assertEqual(self.sem_raiz("Read", pasta, env, file_path="reversa-lab/x"), "deny")
        self.assertEqual(self.sem_raiz("Read", pasta, env, file_path="juridico-lab/x"), "sem_decisao")
        self.assertEqual(self.sem_raiz("Read", self.jur / "minutas", env, file_path="../../reversa-lab/x"), "deny")
        self.assertEqual(self.sem_raiz("Glob", self.jur, env, pattern="../*/x"), "deny")
        env["CLAUDE_PROJECT_DIR"] = str(self.raiz)
        self.assertEqual(self.sem_raiz("Read", self.rev, env, file_path="x.md"), "deny")  # a pasta atual é de outro


@unittest.skipIf(os.name == "nt", "no Windows o caminho real expande o nome curto")
class NomeCurtoNaUnidade(_Base):
    def test_nome_curto_casa_qualquer_nome(self):
        env = {"FUNDACAO_RAIZ": "/mnt/q/IA/fundacao"}
        for alvo in ("/mnt/q/IA/FUNDAC~1/projects/reversa-lab/x", "/mnt/q/IA~1/fundacao/state/x",
                     "/mnt/q/IA/fundacao/PROJEC~1/reversa-lab/x", "/mnt/q/IA/fundacao/projects/JURIDI~1/x"):
            with self.subTest(alvo=alvo):
                self.assertEqual(self.decide("Read", env=env, file_path=alvo), "deny")
        for alvo in ("/mnt/q/IA/fundacao/projects/juridico-lab/x", "/mnt/q/OUTRA~1/x", "/home/u/FUNDAC~1/state/x"):
            with self.subTest(alvo=alvo):
                self.assertEqual(self.decide("Read", env=env, file_path=alvo), "sem_decisao")
        self.assertEqual(self.decide("Glob", env=env, path="/mnt/q/IA/FUNDAC~1", pattern="state/*"), "deny")


if __name__ == "__main__":
    unittest.main()
