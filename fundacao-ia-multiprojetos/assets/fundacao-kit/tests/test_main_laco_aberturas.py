"""Item I2 da integração da 1.7.10 (contratos do lote 2, §1, e emenda E7): `cli_aberturas` no laço das extensões do
`__main__`, nas mesmas linhas do import e da tupla (o teto de 352 linhas não sobe; test_fronteiras_codigo.py). O
`vigente` mantém o `func` próprio (não abre o banco nem exige identidade); `preparar` e `verificar` seguem pelo
`cmd_extensao`, com o banco e a identidade do lançador. Os testes passam pelo `main()` de verdade — o parser de
produção, o `raiz_da_execucao` e o modo travado do porteiro —, que antes da integração recusava `abertura` (o argparse
saía com código 2). Raiz descartável, projetos e identidades de ensaio."""

from __future__ import annotations

import argparse
import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from helpers import FoundationTestCase
from test_aberturas_cli import rascunho

from fundacao import __main__ as principal
from fundacao import cli_aberturas
from fundacao.core import decisoes
from fundacao.core.auth import ENV_ASSINANTE, ENV_PRINCIPAL, ENV_RAIZ, ENV_TRAVA


class MainCase(FoundationTestCase):
    def setUp(self):
        super().setUp()
        sem_ancora = mock.patch.object(decisoes, "ANCORAS_PADRAO", (str(self.root / "sem-ancora"),))
        sem_ancora.start()  # nada da âncora desta máquina entra no ensaio
        self.addCleanup(sem_ancora.stop)
        (self.root / "projects" / "juridico-lab" / "outputs").mkdir(parents=True, exist_ok=True)

    def main(self, *argv, quem: str | None = "operador-juridico", ambiente=None) -> tuple[int, dict | None, str]:
        saida, erro = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {}), redirect_stdout(saida), redirect_stderr(erro):
            for nome in (ENV_PRINCIPAL, ENV_TRAVA, ENV_RAIZ, ENV_ASSINANTE, "FUNDACAO_PORTEIRO"):
                os.environ.pop(nome, None)
            if quem:
                os.environ[ENV_PRINCIPAL] = quem
            os.environ.update(ambiente or {})
            codigo = principal.main(["--raiz", str(self.root), *argv])
        texto = saida.getvalue()
        return codigo, (json.loads(texto) if texto.strip() else None), erro.getvalue()

    def erro(self, stderr: str) -> dict:
        return json.loads(stderr.strip().splitlines()[-1])["error"]


class TestLacoDasExtensoes(MainCase):
    def test_abertura_no_parser_de_producao_e_o_vigente_com_o_func_proprio(self):
        p = principal.build_parser()
        comandos = next(a for a in p._actions if isinstance(a, argparse._SubParsersAction)).choices
        self.assertLessEqual({"memoria", "copia-assinatura", "conhecimento", "abertura"}, set(comandos))
        acoes = next(a for a in comandos["abertura"]._actions if isinstance(a, argparse._SubParsersAction))
        self.assertEqual((acoes.dest, set(acoes.choices)), ("acao", {"preparar", "verificar", "vigente"}))
        self.assertIs(p.parse_args(["abertura", "vigente", "--projeto", "x"]).func, cli_aberturas.cmd_vigente)
        for argv in (["preparar", "--projeto", "x", "--rascunho", "r.json"], ["verificar", "--projeto", "x"]):
            with self.subTest(acao=argv[0]):
                args = p.parse_args(["abertura", *argv])
                self.assertEqual((args.func, args.executor), (principal.cmd_extensao, cli_aberturas.executar))

    def test_vigente_pelo_main_sem_banco_nem_identidade(self):
        area = self.root / "area-vazia"
        area.mkdir()
        with mock.patch.object(principal, "_con", side_effect=AssertionError("vigente abriu o banco")):
            codigo, r, stderr = self.main("abertura", "vigente", "--projeto", "juridico-lab", "--area", str(area),
                                          "--json", quem=None)
        self.assertEqual(codigo, 0, stderr)
        self.assertEqual((r["projeto"], r["valida"], r["ficha"], r["area"]), ("juridico-lab", False, None, str(area)))

    def test_preparar_e_verificar_pelo_main_com_a_identidade_do_lancador(self):
        arquivo = self.root / "projects" / "juridico-lab" / "outputs" / "rascunho.json"
        arquivo.write_text(json.dumps(rascunho(rede={"dominios": ["pypi.org"]})), encoding="utf-8")
        codigo, r, stderr = self.main("abertura", "preparar", "--projeto", "juridico-lab", "--rascunho",
                                      "outputs/rascunho.json")
        self.assertEqual(codigo, 0, stderr)
        self.assertEqual(r["versao"], 1)
        self.assertIn("onde_rodar", r["para_o_titular"])
        codigo, r, stderr = self.main("abertura", "verificar", "--projeto", "juridico-lab")
        self.assertEqual(codigo, 0, stderr)
        self.assertEqual((r["versao"], r["valida"], r["forma_canonica"]), (1, True, True))
        codigo, r, stderr = self.main("abertura", "verificar", "--projeto", "juridico-lab", quem="operador-engenharia")
        self.assertEqual((codigo, self.erro(stderr)["code"]), (2, "E_ACCESS_DENIED"))
        codigo, r, stderr = self.main("abertura", "verificar", "--projeto", "juridico-lab", quem=None)
        self.assertEqual((codigo, self.erro(stderr)["code"]), (2, "E_ACCESS_DENIED"))  # sem identidade

    def test_modo_travado_do_porteiro_pelo_main(self):
        """A sessão do projeto pelo porteiro: `sessao-<p>` com a trava (contratos, §4). A abertura está em
        COMANDOS_DA_TRAVA; outro projeto, --area e caminho fora do projeto são recusados."""
        trava = {ENV_TRAVA: "juridico-lab", ENV_RAIZ: str(self.root)}
        sessao = "sessao-juridico-lab"
        codigo, r, stderr = self.main("abertura", "vigente", "--projeto", "juridico-lab", quem=sessao, ambiente=trava)
        self.assertEqual(codigo, 0, stderr)
        self.assertFalse(r["valida"])
        codigo, _r, stderr = self.main("abertura", "verificar", "--projeto", "juridico-lab", quem=sessao,
                                       ambiente=trava)
        self.assertEqual((codigo, self.erro(stderr)["code"]), (2, "E_NOT_FOUND"))  # passou da trava; nada preparado
        fora = self.root / "projects" / "reversa-lab" / "outputs" / "rascunho.json"
        fora.parent.mkdir(parents=True, exist_ok=True)
        fora.write_text(json.dumps(rascunho()), encoding="utf-8")
        dentro = self.root / "projects" / "juridico-lab" / "outputs"
        recusas = ((["vigente", "--projeto", "reversa-lab"], "E_ACCESS_DENIED"),
                   (["vigente", "--projeto", "juridico-lab", "--area", str(dentro)], "E_ACCESS_DENIED"),
                   (["vigente", "--projeto", "juridico-lab", "--area", str(self.root)], "E_PATH_ESCAPE"),
                   (["preparar", "--projeto", "juridico-lab", "--rascunho", str(fora)], "E_PATH_ESCAPE"))
        for argv, codigo_erro in recusas:
            with self.subTest(argv=argv):
                codigo, _r, stderr = self.main("abertura", *argv, quem=sessao, ambiente=trava)
                self.assertEqual((codigo, self.erro(stderr)["code"]), (2, codigo_erro), stderr)
        self.assertFalse((self.root / "projects" / "juridico-lab" / "outputs" / "aberturas").exists())
