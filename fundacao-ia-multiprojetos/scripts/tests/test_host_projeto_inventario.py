"""Inventário do host lê a skill ligada pelo caminho real (1.7.10; folha do HOST, item 8; pendência do LIBERACAO).

O pre-flight do host (`verificar_fundacao.ligacao_do_instalador`) aceita em `~/.claude/skills` só a ligação do
instalador, cujo alvo final é `~/.agents/skills/<o mesmo nome>`, e percorre o conteúdo desse alvo pelo caminho real.
O `inventariar_host.skills` passa a ler o SKILL.md, a licença e o `sha_pasta` dali — do alvo resolvido uma vez —, e
não pela ligação. Perfil fictício em pasta descartável.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import SCRIPTS, criar_ligacao_dir


def carregar():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("inventariar_host_1710", SCRIPTS / "inventariar_host.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def skill(pasta: Path, nome: str) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "SKILL.md").write_text(f"---\nname: {nome}\nversion: 1.0\n---\n# x\n", encoding="utf-8")
    (pasta / "LICENSE.txt").write_text("MIT de ensaio\n", encoding="utf-8")


class SkillLigadaPeloCaminhoReal(unittest.TestCase):
    def setUp(self):
        self.m = carregar()
        self.base = Path(tempfile.mkdtemp(prefix="inventario-real-1710-")).resolve()
        self.perfil = self.base / "perfil"
        self.real = self.perfil / ".agents" / "skills" / "alfa"
        skill(self.real, "alfa")
        self.ligacao = self.perfil / ".claude" / "skills" / "alfa"
        self.ligacao.parent.mkdir(parents=True)
        criar_ligacao_dir(self.ligacao, self.real)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_le_skill_md_licenca_e_hash_pelo_alvo_real(self):
        lidos = []
        ler_texto = Path.read_text

        def espiao_ler(caminho, *a, **kw):
            lidos.append(Path(caminho))
            return ler_texto(caminho, *a, **kw)

        sha_real, licenca_real = self.m.sha_pasta, self.m.licenca
        with mock.patch.object(Path, "read_text", espiao_ler), \
                mock.patch.object(self.m, "sha_pasta", side_effect=lambda p: (lidos.append(Path(p)), sha_real(p))[1]), \
                mock.patch.object(self.m, "licenca", side_effect=lambda p: (lidos.append(Path(p)), licenca_real(p))[1]):
            itens = self.m.skills(self.perfil, None)
        ligado = next(s for s in itens if s["local"] == "perfil:.claude/skills/alfa")
        self.assertTrue(ligado["ligacao"])
        self.assertEqual(os.path.normcase(ligado["alvo"]), os.path.normcase(os.path.realpath(self.real)))
        self.assertEqual(ligado["sha256"], sha_real(self.real))
        self.assertEqual(ligado["nome"], "alfa")
        prefixo_ligacao = os.path.normcase(str(self.ligacao))
        self.assertFalse([p for p in lidos if os.path.normcase(str(p)).startswith(prefixo_ligacao)],
                         "algo foi lido pela ligação, não pelo alvo real")
        self.assertTrue([p for p in lidos if os.path.normcase(str(p)).startswith(
            os.path.normcase(os.path.realpath(self.real)))])

    def test_ligacao_quebrada_fica_de_fora(self):
        shutil.rmtree(self.real)
        nomes = [s["local"] for s in self.m.skills(self.perfil, None)]
        self.assertNotIn("perfil:.claude/skills/alfa", nomes)


if __name__ == "__main__":
    unittest.main()
