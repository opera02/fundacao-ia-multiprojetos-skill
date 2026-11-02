"""Terceira revisão do pacote INTEG-FLUXOB (lote 2 da 1.7.10): o comando pronto continua literal no terminal errado, e
os passos que sobraram com aspas duplas passam pela citação única.

3. O texto feito para o Linux (`codigo_do_plano.citar_no_terminal` do sh) deixava de ser seguro se o titular, por
engano, o colasse no PowerShell, o terminal de costume dele no Windows: o PowerShell fecha a cadeia nas aspas
tipográficas U+2018 a U+201B, que o sh trata como letra, e também no `'\\''` do sh; um nome com U+2019 executava o que
vinha nele. Agora o sh recusa (renomeie-o) o valor com qualquer dessas cinco aspas, e o texto fica uma cadeia só nos
dois terminais.
4. O passo do titular do `versao_em_uso.py` (o `promover` e o `voltar`, que ele roda fora do Claude) e o aviso do
`git_projeto.py` (rodar de novo o `instrucoes_aninhadas.py listar`) punham a raiz, o arquivo e o repositório entre
aspas duplas, em que `$` e a crase valem: agora cada um vai pela citação única, ou o passo vem sem comando pronto.
Prova: a leitura do analisador do PowerShell (Windows) e, no sistema de cada um, o comando rodado de verdade com um
programa no lugar do script, que só grava o argv que recebe, e nomes hostis que criariam arquivos se escapassem das
aspas. Dados fictícios em pastas temporárias.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_integ_fluxob_1710_comando import (ASPAS_PS, HOSTIL_PS, HOSTIL_SH, NO_WINDOWS, PASTA_HOSTIL, PASTA_PS,
                                             PASTA_SH, POWERSHELL, VALORES_HOSTIS, analisador_do_powershell, argvs,
                                             cadeias_do_powershell, rodar_no_terminal)
from test_integ_fluxob_1710_git import MOD as GIT
from test_integ_fluxob_1710_importar import _Importacao
from test_integ_fluxob_1710_perfil import EX
from test_integ_fluxob_1710_versao import MOD as VERSAO

CODIGO, PERFIL = EX.CODIGO, EX.PERFIL
# Nomes que um código importado poderia trazer, com e sem as aspas simples que o PowerShell reconhece.
NOMES = [*VALORES_HOSTIS, HOSTIL_SH, HOSTIL_PS, PASTA_SH, PASTA_PS, "token\u2019; New-Item INJ-x; \u2019.py",
         "a\u201bb", "it's", "x \u201c$(touch INJ-y)\u201d"]
ECO = ("import json, sys\n"  # o programa no lugar do script: grava o argv que recebe (o primeiro é o arquivo)
       "with open(sys.argv[1], 'w', encoding='utf-8') as f:\n"
       "    json.dump(sys.argv[2:], f)\n")


class TestTextoDoShColadoNoPowerShell(unittest.TestCase):
    def test_o_sh_recusa_as_cinco_aspas_simples_e_o_powershell_as_dobra(self):
        for aspa in ASPAS_PS:
            valor = f"orig{aspa}; New-Item INJ; {aspa}x"
            with self.subTest(aspa=ascii(aspa)):
                with self.assertRaises(ValueError) as ctx:
                    CODIGO.citar_no_terminal(valor, powershell=False)
                self.assertIn("aspa simples", str(ctx.exception))
                self.assertEqual(cadeias_do_powershell(CODIGO.citar_no_terminal(valor, powershell=True)),
                                 ("<c>", [valor]))

    def test_o_texto_do_sh_e_uma_cadeia_so_pela_regra_do_powershell(self):
        for nome in NOMES:
            with self.subTest(nome=ascii(nome)):
                try:
                    citado = CODIGO.citar_no_terminal(nome, powershell=False)
                except ValueError:
                    self.assertTrue(set(nome) & set(ASPAS_PS), "o sh só recusa aqui o nome com aspa simples")
                    continue
                self.assertEqual(cadeias_do_powershell(citado), ("<c>", [nome]))

    @unittest.skipUnless(POWERSHELL, "analisador do PowerShell só no Windows")
    def test_o_b7_do_sh_colado_no_powershell_so_tem_cadeias_constantes(self):
        politica = CODIGO.MANIFESTO.politica_formato3(incluir_ignoradas=[".venv"])
        for nome in NOMES:
            with self.subTest(nome=ascii(nome)):
                try:
                    comando = PERFIL.comando_do_b7("/tmp/raiz", "/tmp/manifesto.json", politica, [f"pkg/{nome}"],
                                                   powershell=False)
                except ValueError:
                    self.assertTrue(set(nome) & set(ASPAS_PS))
                    continue
                _erros, comandos = analisador_do_powershell(comando)  # o && do sh é erro no 5.1: nada roda
                self.assertFalse([e for c in comandos for e in c if e.startswith("<")], comandos)
                self.assertEqual(comandos, argvs(comando, powershell=False), "as mesmas palavras do sh, nenhuma a mais")


class _ComEco(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="integ-terminal-")))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.terminal = self.base / "terminal"  # a pasta atual do shell: os INJ-* cairiam aqui
        self.terminal.mkdir()
        self.eco, self.gravado = self.base / "eco.py", self.base / "argv.json"
        self.eco.write_text(ECO, encoding="utf-8")

    def argv_no_terminal(self, comando: str, programa: str) -> list[str]:
        """O argv que o programa recebe quando o titular cola o comando no terminal do sistema (sh no Linux,
        PowerShell no Windows), com o eco no lugar de `programa`."""
        citar = CODIGO.citar_no_terminal
        trocado = comando.replace(programa, f"{citar(self.eco)} {citar(self.gravado)}", 1)
        self.assertNotEqual(trocado, comando, f"o comando não tem {programa}: {comando}")
        if POWERSHELL:
            erros, comandos = analisador_do_powershell(trocado)
            self.assertEqual(erros, 0, trocado)
            self.assertFalse([e for c in comandos for e in c if e.startswith("<")], comandos)
        if NO_WINDOWS and not POWERSHELL:
            self.skipTest("sem PowerShell para rodar o comando")
        r = rodar_no_terminal(trocado, self.terminal)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
        self.assertEqual(os.listdir(self.terminal), [], "nada do nome saiu das aspas")
        return json.loads(self.gravado.read_text(encoding="utf-8"))


class TestPassoDoTitularDaVersaoEmUso(_ComEco):
    def projeto(self, raiz: Path) -> Path:
        projeto = raiz / "projects" / "p"
        (projeto / "trabalho").mkdir(parents=True)
        (projeto / "trabalho" / "app.py").write_bytes(b"print('v1')\n")
        (self.base / "lista.txt").write_text("**/*.py\n", encoding="utf-8")
        return projeto

    def comando(self, res: dict) -> str:
        passo = res["proximos_passos"][-1]
        self.assertIn("fora do Claude: ", passo)
        return passo.split("fora do Claude: ", 1)[1].replace("<projects/p/decisoes/<id>.json>", "decisao.json")

    def test_promover_e_voltar_vao_literais_ao_programa(self):
        raiz = self.base / f"raiz {PASTA_HOSTIL}"
        projeto = self.projeto(raiz)
        saida = projeto / "outputs" / "versao" / f"proposta {PASTA_HOSTIL}.json"
        res = VERSAO.propor(raiz, "p", projeto / "trabalho", self.base / "lista.txt", saida)
        self.assertEqual(self.argv_no_terminal(self.comando(res), "<skill>/scripts/versao_em_uso.py"),
                         ["promover", "--raiz", str(raiz), "--projeto", "p", "--proposta", str(saida),
                          "--proposta-sha256", res["sha256"], "--decisao", "decisao.json"])
        pedido = VERSAO.pedir_volta(raiz, "p", projeto / "outputs" / "versao" / f"volta {PASTA_HOSTIL}.json",
                                    motivo="voltar a anterior (fictício)")
        self.assertEqual(self.argv_no_terminal(self.comando(pedido), "<skill>/scripts/versao_em_uso.py"),
                         ["voltar", "--raiz", str(raiz), "--projeto", "p", "--pedido", pedido["pedido"],
                          "--pedido-sha256", pedido["sha256"], "--decisao", "decisao.json"])

    def test_sem_comando_pronto_quando_nao_da_para_citar(self):
        raiz = self.base / "raiz\u202ex"  # U+202E inverteria o que o titular lê
        projeto = self.projeto(raiz)
        res = VERSAO.propor(raiz, "p", projeto / "trabalho", self.base / "lista.txt",
                            projeto / "outputs" / "versao" / "proposta.json")
        pedido = VERSAO.pedir_volta(raiz, "p", projeto / "outputs" / "versao" / "volta.json", motivo="fictício")
        for passo, acao in ((res["proximos_passos"][-1], "promover da proposta"),
                            (pedido["proximos_passos"][-1], "voltar do pedido")):
            with self.subTest(acao=acao):
                self.assertIn(f"roda o {acao}; não há comando pronto", passo)
                self.assertNotIn("--raiz", passo)
                self.assertNotIn("\u202e", passo)


class TestAvisoDoGitProjeto(_ComEco):
    def repositorio(self, nome: str) -> Path:
        repo = self.base / nome / "repo"
        repo.mkdir(parents=True)
        (repo / "AGENTS.md").write_text("# instruções antigas (dado)\n", encoding="utf-8")
        return repo

    def test_os_dois_avisos_citam_o_repositorio(self):
        repo = self.repositorio(PASTA_HOSTIL)
        programa = GIT.CODIGO.citar_no_terminal(GIT.AQUI / "instrucoes_aninhadas.py")
        with mock.patch.object(GIT.INSTRUCOES, "listar", side_effect=OSError("falha simulada")):
            _resumo, avisos = GIT.instrucoes_do_repositorio(repo, "repo")
        aviso = next(a for a in avisos if "não rodou" in a)
        comando = aviso.split("): rode ", 1)[1].rsplit(" antes de abrir uma sessão ali", 1)[0]
        self.assertEqual(self.argv_no_terminal(comando, programa), ["listar", "--raiz", str(repo)])
        completo = GIT.INSTRUCOES.listar(repo)
        with mock.patch.object(GIT.INSTRUCOES, "listar", return_value={**completo, "completo": False}):
            _resumo, avisos = GIT.instrucoes_do_repositorio(repo, "repo")
        comando = next(a for a in avisos if "ficou parcial" in a).split("para conferir, rode ", 1)[1]
        self.assertEqual(self.argv_no_terminal(comando, programa), ["listar", "--raiz", str(repo)])

    def test_sem_comando_pronto_quando_nao_da_para_citar(self):
        repo = self.repositorio("orig\u202ex")
        with mock.patch.object(GIT.INSTRUCOES, "listar", side_effect=OSError("falha simulada")):
            _resumo, avisos = GIT.instrucoes_do_repositorio(repo, "repo")
        aviso = next(a for a in avisos if "não rodou" in a)
        self.assertIn("não há comando pronto", aviso)
        self.assertNotIn("listar --raiz", aviso)
        self.assertNotIn("\u202e", aviso)


@unittest.skipIf(NO_WINDOWS, "no Windows, o comando é do PowerShell, que dobra a aspa simples")
class TestImportarComAspaSimplesNoLinux(_Importacao):
    def test_origem_com_aspa_simples_fica_sem_comando_no_sh(self):
        for aspa in ASPAS_PS:
            with self.subTest(aspa=ascii(aspa)):
                origem = self.base / "fontes" / f"orig{aspa}; touch INJ; {aspa}x"
                origem.mkdir()
                (origem / "a.txt").write_text("a\n", encoding="utf-8")
                erro = self.plano(origem=origem, codigo=2)["erro"]
                self.assertIn("Não há comando pronto", erro)
                self.assertIn("aspa simples", erro)
                self.assertNotIn("registrar-projeto", erro)  # o comando começa por --raiz desde o I23


if __name__ == "__main__":
    unittest.main()
