"""A regra única de segredo (1.7.10, contratos do lote 2, §3): cada cópia das listas repete a canônica
(scripts/regras_de_segredo.py) e um teste confere a igualdade. Aqui, a cópia do kit (fundacao/core/manutencao.py),
lida pelo texto do arquivo: o kit é instalado à parte e não importa os scripts da skill, e importar o pacote do kit
neste processo misturaria o `fundacao` de outras raízes de teste. As cópias dos perfis do host têm teste no HOST."""

from __future__ import annotations

import ast
import importlib.util
import os
import unittest
from pathlib import Path

from apoio import KIT, SCRIPTS, SKILL

# Arquivos da própria skill que a regra nega de propósito (dado de avaliação que simula segredo). Nenhum código.
NEGADOS_DE_PROPOSITO = {"evals/fixtures/legado-squad/.env"}


def carregar_regras():
    spec = importlib.util.spec_from_file_location("regras_copias_teste", SCRIPTS / "regras_de_segredo.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def constantes(arquivo: Path, nomes: set[str]) -> dict:
    """Os valores literais das atribuições de primeiro nível `NOME = (...)` ou `NOME = frozenset({...})`."""
    achados = {}
    for no in ast.parse(arquivo.read_text(encoding="utf-8")).body:
        if (isinstance(no, ast.Assign) and len(no.targets) == 1 and isinstance(no.targets[0], ast.Name)
                and no.targets[0].id in nomes):
            valor = no.value
            if (isinstance(valor, ast.Call) and isinstance(valor.func, ast.Name) and valor.func.id == "frozenset"
                    and len(valor.args) == 1):
                valor = valor.args[0]
            achados[no.targets[0].id] = ast.literal_eval(valor)
    return achados


class TestCopiaDoKit(unittest.TestCase):
    def setUp(self):
        self.R = carregar_regras()
        self.kit = constantes(KIT / "fundacao" / "core" / "manutencao.py", {"PASTAS_DE_SEGREDO", "NOMES_DE_SEGREDO"})

    def test_o_kit_repete_as_pastas_e_os_nomes_fortes(self):
        self.assertEqual(set(self.kit), {"PASTAS_DE_SEGREDO", "NOMES_DE_SEGREDO"}, "constantes não achadas no kit")
        self.assertEqual(set(self.kit["PASTAS_DE_SEGREDO"]), set(self.R.PASTAS_DE_SEGREDO))
        self.assertEqual(set(self.kit["NOMES_DE_SEGREDO"]), set(self.R.NOMES_FORTES))

    def test_sem_repeticao(self):
        for nome, valor in self.kit.items():
            if isinstance(valor, tuple):
                self.assertEqual(len(valor), len(set(valor)), nome)
        for lista in (self.R.NOMES_FORTES, self.R.NOMES_FRACOS, self.R.PASTAS_DE_SEGREDO):
            self.assertEqual(len(lista), len(set(lista)))


class TestCanonicaNaoNegaOProprioCodigo(unittest.TestCase):
    def test_nenhum_arquivo_da_skill_casa_forte_ou_pasta_salvo_os_de_proposito(self):
        # Os perfis negam fortes + pastas (contratos, §3): um código da skill que casasse ficaria ilegível na sessão
        # do próprio projeto. Os fracos ficam fora desta conta (são conferidos pelo conteúdo, não negados).
        regras, achados = carregar_regras(), set()
        for raiz, pastas, arquivos in os.walk(SKILL):
            pastas[:] = [p for p in pastas if p not in ("__pycache__", ".git")]
            for nome in (*arquivos, *pastas):
                rel = (Path(raiz) / nome).relative_to(SKILL).as_posix()
                if regras.classificar(rel) in ("forte", "pasta-de-segredo"):
                    achados.add(rel)
        self.assertLessEqual(achados, NEGADOS_DE_PROPOSITO)


if __name__ == "__main__":
    unittest.main()
