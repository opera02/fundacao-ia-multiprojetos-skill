"""Sentinela da CI (1.7.10; crítica do desenho): teste pulado passa verde. No Ubuntu da CI, os testes que precisam
do bubblewrap e do socat (a caixa da execução isolada, o perfil de execução e o que a 1.7.10 acrescenta) não podem ser
pulados em silêncio. Com FUNDACAO_CI_EXIGE_BWRAP=1 (o `validar.yml` liga só no Ubuntu), este teste exige os dois
programas e uma caixa que abre de verdade; fora da CI, é pulado.

Revisão de segurança da 1.7.10, CI-F6: a caixa que a sentinela abria (`bwrap --ro-bind / / ... true`) não era a que os
testes sondam (`execucao_isolada.sondar_bwrap`: --unshare-all, --clearenv e as montagens do plano), e o `rodar` do
perfil exige ainda a montagem por descritor: um bubblewrap que abrisse só a caixa simples deixava os testes da caixa
pulados com a CI verde. Agora a sentinela sonda a mesma caixa, pelas mesmas funções (a do módulo da caixa e a que o
módulo do perfil recebe injetada) e a montagem por descritor; com a variável, os testes da caixa (`TestCaixaDeVerdade`
e `TestBubblewrapDeVerdade`) falham em vez de pular; e, sempre, um teste confere que todo teste dos scripts que pula
pela sondagem da caixa consulta a variável antes."""

from __future__ import annotations

import ast
import importlib.util
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from apoio import SCRIPTS

VARIAVEL = "FUNDACAO_CI_EXIGE_BWRAP"


def exige() -> bool:
    """A CI exige a caixa? Lida a cada teste (não na importação), como nos testes da caixa."""
    return os.environ.get(VARIAVEL) == "1"


def carregar_execucao_isolada():
    spec = importlib.util.spec_from_file_location("_sentinela_execucao_isolada", SCRIPTS / "execucao_isolada.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class TestSentinelaDaCaixa(unittest.TestCase):
    def setUp(self):
        if not exige():
            self.skipTest(f"só no Ubuntu da CI ({VARIAVEL}=1)")

    def test_bubblewrap_e_socat_presentes(self):
        self.assertTrue(sys.platform.startswith("linux"), sys.platform)
        for programa in ("bwrap", "socat"):
            self.assertIsNotNone(shutil.which(programa), f"{programa} ausente: os testes da caixa seriam pulados")

    def test_a_caixa_abre(self):
        r = subprocess.run(["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "true"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, f"a caixa do bubblewrap não abriu: {r.stderr.strip()}")

    def test_a_caixa_dos_testes_abre(self):
        """A mesma sondagem que decide se os testes da caixa rodam: a da execução isolada e a do perfil (CI-F6)."""
        ex = carregar_execucao_isolada()
        for nome, sondar in (("execucao_isolada", ex.sondar_bwrap), ("perfil_execucao", ex.PERFIL.sondar_bwrap)):
            with self.subTest(nome):
                caminho, motivo = sondar()
                self.assertIsNotNone(caminho, f"a caixa dos testes ({nome}) não abre: {motivo}; os testes dela "
                                              "seriam pulados")

    def test_o_rodar_do_perfil_monta_por_descritor(self):
        ex = carregar_execucao_isolada()
        caminho, motivo = ex.PERFIL.sondar_bwrap()
        self.assertIsNotNone(caminho, f"a caixa não abre: {motivo}")
        self.assertTrue(ex.PERFIL.bwrap_monta_por_descritor(caminho),
                        "o bubblewrap não monta por descritor (--ro-bind-fd): o rodar do perfil recusaria")


def _chama(no: ast.AST, nome: str) -> bool:
    """Há, dentro de `no`, uma chamada a `nome(...)` ou a `<algo>.nome(...)`?"""
    return any(isinstance(n, ast.Call) and ((isinstance(n.func, ast.Attribute) and n.func.attr == nome)
                                            or (isinstance(n.func, ast.Name) and n.func.id == nome))
               for n in ast.walk(no))


class TestNenhumTesteDaCaixaPulaNaCI(unittest.TestCase):
    """Sempre, fora da variável também (CI-F6): todo teste dos scripts que pula pela sondagem da caixa (chama
    `sondar_bwrap()` e `skipTest`/`SkipTest` na mesma função) consulta FUNDACAO_CI_EXIGE_BWRAP (o texto dela ou
    `exige()`) antes de pular, para falhar na CI em vez de pular."""

    def test_quem_pula_pela_sondagem_consulta_a_variavel(self):
        vistos = []
        for arquivo in sorted(Path(__file__).resolve().parent.glob("test_*.py")):
            texto = arquivo.read_text(encoding="utf-8")
            if "sondar_bwrap" not in texto:
                continue
            for no in ast.walk(ast.parse(texto)):
                if (isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and _chama(no, "sondar_bwrap")
                        and (_chama(no, "skipTest") or _chama(no, "SkipTest"))):
                    vistos.append(f"{arquivo.name}:{no.name}")
                    with self.subTest(f"{arquivo.name}:{no.name}"):
                        self.assertTrue(_chama(no, "exige") or any(isinstance(n, ast.Constant) and n.value == VARIAVEL
                                                                   for n in ast.walk(no)),
                                        "pula pela sondagem da caixa sem consultar a variável da CI")
        self.assertGreaterEqual(len(vistos), 2, vistos)  # TestCaixaDeVerdade e TestBubblewrapDeVerdade, ao menos


if __name__ == "__main__":
    unittest.main()
