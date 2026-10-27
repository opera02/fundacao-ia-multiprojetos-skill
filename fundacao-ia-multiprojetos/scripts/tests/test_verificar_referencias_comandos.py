"""Comandos citados nas referências conferidos contra o código (proposta 8 da análise do vibe-coding-toolkit).

A skill mediu: 10 das 66 intervenções do titular na implantação vieram de instruções que não rodavam como
escritas (references/comunicacao-leigo.md). Agora `verificar_referencias.py` também lê, pela árvore sintática
(sem executar nada), o `argparse` de cada script citado — e o da CLI do kit (`python -m fundacao`) — e acusa
subcomando, ação ou opção que não existe, ou opção abreviada. Pasta descartável com uma skill fictícia.
"""

from __future__ import annotations

import importlib.util
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

from apoio import SCRIPTS, SKILL

spec = importlib.util.spec_from_file_location("verificar_referencias", SCRIPTS / "verificar_referencias.py")
vr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vr)

FERRAMENTA = textwrap.dedent('''
    import argparse


    def comuns(p):
        p.add_argument("--raiz", required=True)


    def main():
        ap = argparse.ArgumentParser()
        ap.add_argument("--verbose", action="store_true")
        sub = ap.add_subparsers(dest="cmd", required=True)
        c = sub.add_parser("criar")
        comuns(c)
        c.add_argument("--saida")
        g = c.add_mutually_exclusive_group()
        g.add_argument("--rapido", action="store_true")
        v = sub.add_parser("validar", aliases=["conferir"])
        v.add_argument("--arquivo")
        return ap
''')
CLI = textwrap.dedent('''
    import argparse


    def build_parser():
        p = argparse.ArgumentParser(prog="fundacao")
        p.add_argument("--raiz")
        sub = p.add_subparsers(dest="comando", required=True)
        s = sub.add_parser("init"); s.add_argument("--admin")
        s = sub.add_parser("projeto"); s.add_argument("acao", choices=["criar", "listar"])
        s.add_argument("--id"); s.add_argument("--nome")
        return p
''')


class TestComandosCitados(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="verificar-comandos-"))
        (self.raiz / "scripts").mkdir()
        (self.raiz / "scripts" / "ferramenta.py").write_text(FERRAMENTA, encoding="utf-8")
        kit = self.raiz / "assets" / "fundacao-kit" / "fundacao"
        kit.mkdir(parents=True)
        (kit / "__main__.py").write_text(CLI, encoding="utf-8")
        (self.raiz / "references").mkdir()

    def tearDown(self):
        shutil.rmtree(self.raiz, ignore_errors=True)

    def conferir(self, texto: str) -> dict:
        (self.raiz / "references" / "guia.md").write_text(textwrap.dedent(texto), encoding="utf-8")
        return vr.check(self.raiz)

    def problemas(self, res: dict) -> list[tuple[str, str]]:
        return sorted((p["opcao"], p["problema"]) for p in res["comandos_com_problema"])

    def test_comandos_certos_passam(self):
        res = self.conferir("""
            Rode `python <skill>/scripts/ferramenta.py criar --raiz <raiz> --saida <ref> --rapido`.
            ```
            python -B <skill>/scripts/ferramenta.py --verbose validar --arquivo RETOMADA.md   # comentário --nada
            python <skill>/scripts/ferramenta.py conferir --arquivo x.md
            python scripts/ferramenta.py criar --raiz . [--rapido]
            cd <raiz> && python -m fundacao --raiz <raiz> projeto criar --id lab --nome "Lab de ensaio"
            python -m fundacao projeto listar | criar --id outro
            python -m fundacao init --admin <id-do-titular>
            ```
        """)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["comandos_com_problema"], [])
        self.assertGreaterEqual(res["comandos_conferidos"], 7)

    def test_opcao_inexistente_ou_renomeada_e_acusada(self):
        res = self.conferir("Rode `python <skill>/scripts/ferramenta.py criar --raiz <r> --destino <d>`.\n")
        self.assertFalse(res["ok"])
        self.assertEqual(self.problemas(res), [("--destino", "opção inexistente")])

    def test_subcomando_e_acao_inexistentes_sao_acusados(self):
        res = self.conferir("""
            ```
            python <skill>/scripts/ferramenta.py apagar --raiz <r>
            python -m fundacao projeto apagar --id lab
            ```
        """)
        self.assertEqual(self.problemas(res), [("apagar", "ação inexistente"), ("apagar", "subcomando inexistente")])

    def test_opcao_de_outro_subcomando_e_abreviada_sao_acusadas(self):
        res = self.conferir("""
            ```
            python <skill>/scripts/ferramenta.py validar --saida <ref>
            python <skill>/scripts/ferramenta.py criar --raiz <r> --sai <ref>
            ```
        """)
        self.assertEqual(self.problemas(res), [("--sai", "opção abreviada (use --saida)"), ("--saida", "opção inexistente")])

    def test_as_referencias_desta_skill_nao_citam_opcao_inexistente(self):
        res = vr.check(SKILL)
        self.assertEqual(res["comandos_com_problema"], [], "comandos citados que não rodam como escritos")
        self.assertGreater(res["comandos_conferidos"], 40)

    def test_extensoes_da_cli_registradas_no_laco_sao_lidas(self):
        # 1.7.9 (R179-37): subcomando de módulo de extensão (`for m in (...): m.registrar_parser(sub)`) é conferido;
        # módulo fora do laço não vira subcomando.
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "principal.py").write_text(textwrap.dedent('''
                import argparse


                def montar():
                    p = argparse.ArgumentParser()
                    sub = p.add_subparsers(dest="cmd", required=True)
                    sub.add_parser("status")
                    from . import cli_a
                    for modulo in (cli_a,):
                        modulo.registrar_parser(sub).set_defaults(executor=modulo.executar)
                    return p
            '''), encoding="utf-8")
            (pasta / "cli_a.py").write_text(textwrap.dedent('''
                def registrar_parser(subparsers):
                    p = subparsers.add_parser("conhecimento")
                    p.add_argument("acao", choices=("listar", "buscar"))
                    p.add_argument("--projeto", required=True)
                    return p
            '''), encoding="utf-8")
            (pasta / "cli_fora.py").write_text(
                'def registrar_parser(subparsers):\n    subparsers.add_parser("fora")\n', encoding="utf-8")
            parser = vr.estrutura_argparse(pasta / "principal.py")
        self.assertEqual(sorted(parser.subcomandos), ["conhecimento", "status"])
        self.assertEqual(vr.conferir_comando(parser, ["conhecimento", "listar", "--projeto", "<p>"]), [])
        self.assertEqual(vr.conferir_comando(parser, ["conhecimento", "ler"]), [("ler", "ação inexistente")])
        self.assertEqual(vr.conferir_comando(parser, ["fora"]), [("fora", "subcomando inexistente")])


if __name__ == "__main__":
    unittest.main()
