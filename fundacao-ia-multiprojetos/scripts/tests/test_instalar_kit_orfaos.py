"""Arquivos órfãos na atualização do kit (proposta 11 da análise do vibe-coding-toolkit, 21/10/2026).

Um arquivo que um kit ANTERIOR instalou (está em `registry/kit_install.json`) e que o kit novo retirou ou
renomeou continuava na raiz — inclusive um `tests/test_*.py` antigo, que o `unittest discover` seguia
executando — e a atualização saía "verificada". Agora o plano lista os órfãos; sem decisão nada é escrito;
com `--atualizar` eles vão para `registry/kit_backup/<carimbo>/`, de onde o retorno os devolve. Arquivo que o
kit nunca instalou (do usuário) não é órfão e não é tocado. Pastas descartáveis; nada no perfil.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from apoio import rodar_script

TESTE_ANTIGO = "import unittest\n\n\nclass TestAntigo(unittest.TestCase):\n    def test_passa(self):\n        pass\n"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class TestOrfaosDoKit(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="instalar-kit-orfaos-"))
        self.dest = self.base / "raiz"
        p = rodar_script("instalar_kit.py", "--destino", self.dest)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        # Simula um kit anterior que tinha dois arquivos que o kit desta skill não tem mais.
        self.antigos = {"tests/test_antigo_retirado.py": TESTE_ANTIGO, "fundacao/modulo_retirado.py": "X = 1\n"}
        reg = self.dest / "registry" / "kit_install.json"
        historico = json.loads(reg.read_text(encoding="utf-8"))
        for rel, texto in self.antigos.items():
            (self.dest / rel).write_text(texto, encoding="utf-8")
            historico[-1]["copiados"].append({"path": rel, "sha256": sha(self.dest / rel)})
        reg.write_text(json.dumps(historico, ensure_ascii=False, indent=2), encoding="utf-8")
        self.do_usuario = self.dest / "tests" / "test_do_usuario.py"  # o kit nunca instalou: não é órfão
        self.do_usuario.write_text(TESTE_ANTIGO, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def instalar(self, *extra):
        p = rodar_script("instalar_kit.py", "--destino", self.dest, *extra)
        try:
            return p.returncode, json.loads(p.stdout)
        except ValueError:
            self.fail("saída não é JSON: " + p.stdout[-400:] + p.stderr[-400:])

    def test_sem_decisao_lista_os_orfaos_e_nada_escreve(self):
        antes = {p: sha(p) for p in self.dest.rglob("*") if p.is_file()}
        code, res = self.instalar()
        self.assertEqual(code, 3, res)
        self.assertEqual(sorted(o["path"] for o in res["orfaos"]), sorted(self.antigos))
        self.assertTrue(res["nada_escrito"])
        self.assertEqual({p: sha(p) for p in self.dest.rglob("*") if p.is_file()}, antes)

    def test_atualizar_guarda_os_orfaos_no_backup_e_poupa_o_do_usuario(self):
        code, res = self.instalar("--atualizar")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["composicao"], "verificada")
        retirados = {o["path"]: o["sha256"] for o in res["orfaos_retirados"]}
        self.assertEqual(sorted(retirados), sorted(self.antigos))
        backup = Path(res["backup_dos_substituidos"])
        for rel in self.antigos:
            self.assertFalse((self.dest / rel).exists(), rel)
            self.assertEqual(sha(backup / rel), retirados[rel])
        self.assertTrue(self.do_usuario.is_file())
        historico = json.loads((self.dest / "registry" / "kit_install.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(o["path"] for o in historico[-1]["orfaos_retirados"]), sorted(self.antigos))
        code, res = self.instalar()  # retirados não voltam a ser órfãos
        self.assertEqual((code, res["orfaos"]), (0, []), res)

    def test_orfao_alterado_localmente_sai_marcado(self):
        rel = "fundacao/modulo_retirado.py"
        (self.dest / rel).write_text("X = 2  # alteração local\n", encoding="utf-8")
        code, res = self.instalar("--atualizar")
        self.assertEqual(code, 0, res)
        marcados = {o["path"]: o["alterado_localmente"] for o in res["orfaos_retirados"]}
        self.assertTrue(marcados[rel])
        self.assertFalse(marcados["tests/test_antigo_retirado.py"])

    def test_manter_conflitos_preserva_orfaos_como_estado_misto(self):
        code, res = self.instalar("--manter-conflitos")
        self.assertEqual(code, 3, res)
        self.assertEqual(res["composicao"], "mista")
        for rel in self.antigos:
            self.assertTrue((self.dest / rel).is_file(), rel)


if __name__ == "__main__":
    unittest.main()
