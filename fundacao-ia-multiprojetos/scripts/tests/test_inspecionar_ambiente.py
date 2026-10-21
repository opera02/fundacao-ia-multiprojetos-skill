"""`scripts/inspecionar_ambiente.py` — efeitos declarados (auditoria da 1.4.1, A18).

Apresentado como "somente leitura", o inventário executava CLIs (sem `--somente-localizar`) e
`--saida` substituía em silêncio um inventário anterior (evidência). Agora `--saida` recusa arquivo
existente (código 1, nada executado nem gravado); sem `--saida`, nada é gravado. Os testes usam
`--somente-localizar`: nenhum programa externo é executado. A recusa falha na 1.4.5; os controles passam.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from apoio import rodar_script


class TestInventarioEfeitos(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="inventario-teste-"))
        self.pasta = self.base / "raiz"
        self.trabalho = self.base / "cwd"
        self.pasta.mkdir()
        self.trabalho.mkdir()

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def rodar(self, *args):
        return rodar_script("inspecionar_ambiente.py", "--pasta", self.pasta, "--somente-localizar", *args,
                            cwd=self.trabalho)

    def test_saida_existente_e_recusada_sem_alterar(self):
        anterior = self.pasta / "evidence" / "ambiente" / "inventario.json"
        anterior.parent.mkdir(parents=True)
        anterior.write_text('{"evidencia": "anterior"}\n', encoding="utf-8")
        p = self.rodar("--saida", anterior)
        self.assertEqual(p.returncode, 1, p.stdout[-300:])
        self.assertIn("erro", json.loads(p.stdout))
        self.assertEqual(anterior.read_text(encoding="utf-8"), '{"evidencia": "anterior"}\n')

    def test_controle_saida_nova_e_gravada_sem_executar_programas(self):
        nova = self.pasta / "evidence" / "ambiente" / "inventario-2026-10-20.json"
        p = self.rodar("--saida", nova)
        self.assertEqual(p.returncode, 0, p.stderr[-300:])
        dados = json.loads(nova.read_text(encoding="utf-8"))
        self.assertEqual(dados["schema_version"], "fundacao.inventario_ambiente/1")
        for nome, entrada in dados["programas"].items():
            with self.subTest(programa=nome):
                self.assertFalse({"versao", "listagem", "distribuicoes"} & set(entrada))

    def test_controle_sem_saida_nada_e_gravado(self):
        p = self.rodar()
        self.assertEqual(p.returncode, 0, p.stderr[-300:])
        self.assertEqual(json.loads(p.stdout)["schema_version"], "fundacao.inventario_ambiente/1")
        self.assertEqual([x for x in self.base.rglob("*") if x.is_file()], [])


if __name__ == "__main__":
    unittest.main()
