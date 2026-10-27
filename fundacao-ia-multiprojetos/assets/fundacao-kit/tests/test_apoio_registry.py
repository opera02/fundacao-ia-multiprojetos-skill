"""D1 da 1.7.9: a configuração dos testes não inclui cópias antigas do código."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import helpers


class TestRegistryDoAmbienteDescartavel(unittest.TestCase):
    def test_copias_do_atualizador_ficam_fora_sem_perder_configuracao(self):
        with tempfile.TemporaryDirectory(prefix="apoio-registry-") as tmp:
            origem = Path(tmp)
            for nome in ("fundacao", "templates"):
                shutil.copytree(helpers.KIT / nome, origem / nome,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            registry = origem / "registry"
            shutil.copytree(helpers.KIT / "registry", registry)
            for nome in ("kit_backup", "kit_preparo"):
                (registry / nome).mkdir(exist_ok=True)
                (registry / nome / "canario.txt").write_text("COPIA-ANTIGA-FICTICIA", encoding="utf-8")
            for nome in ("kit_install.json", "atualizacoes.jsonl", "inventario-host.json"):
                (registry / nome).write_text("registro fictício", encoding="utf-8")
            (registry / "configuracao-local.json").write_text('{"preservar": true}', encoding="utf-8")
            # Nome igual dentro de configuração própria não é a pasta do atualizador.
            nested = registry / "configuracao-propria" / "kit_backup"
            nested.mkdir(parents=True)
            (nested / "regra.txt").write_text("preservar", encoding="utf-8")
            caso = helpers.FoundationTestCase()
            with patch.object(helpers, "KIT", origem):
                try:
                    caso.setUp()
                    copiado = caso.root / "registry"
                    self.assertEqual((copiado / "configuracao-local.json").read_bytes(),
                                     (registry / "configuracao-local.json").read_bytes())
                    self.assertEqual((copiado / "route_policy.json").read_bytes(),
                                     (registry / "route_policy.json").read_bytes())
                    self.assertTrue((copiado / "configuracao-propria/kit_backup/regra.txt").is_file())
                    for nome in ("kit_backup", "kit_preparo", "kit_install.json", "atualizacoes.jsonl",
                                 "inventario-host.json"):
                        with self.subTest(nome=nome):
                            self.assertFalse((copiado / nome).exists(), nome)
                finally:
                    caso.tearDown()
