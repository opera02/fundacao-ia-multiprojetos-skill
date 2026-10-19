"""Relatório técnico de auditoria da 1.4.0 — `instalar_skill.py`: COD-02, COD-03 e COD-05.

Nada é instalado no perfil real: cada execução usa um perfil DESCARTÁVEL (USERPROFILE e HOME
apontam para uma pasta temporária, conferido antes de rodar) e a origem é uma skill mínima fictícia.
Os testes falham na 1.4.0; verificação item a item em `auditoria/VERIFICACAO-RELATORIO-TECNICO-1.4.0.md`.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENTREGA = Path(__file__).resolve().parents[1]
INSTALADOR = ENTREGA / "instalar_skill.py"
NOME = "fundacao-ia-multiprojetos"
SKILL_MD = f"---\nname: {NOME}\ndescription: ficticia\n---\n"

# Prelúdio do processo filho que simula um SQLite sem FTS5 (COD-03).
SEM_FTS5 = """
import sqlite3
_conectar = sqlite3.connect
class _SemFts5:
    def __init__(self, *a, **k):
        self._con = _conectar(*a, **k)
    def execute(self, sql, *a):
        if "fts5" in sql.lower():
            raise sqlite3.OperationalError("no such module: fts5")
        return self._con.execute(sql, *a)
    def close(self):
        self._con.close()
sqlite3.connect = _SemFts5
"""


def _apagar(base: Path) -> None:
    def tornar_gravavel(func, caminho, _erro):
        os.chmod(caminho, stat.S_IWRITE)
        func(caminho)
    if sys.version_info >= (3, 12):
        shutil.rmtree(base, onexc=tornar_gravavel)
    else:
        shutil.rmtree(base, onerror=tornar_gravavel)


class _PerfilDescartavel(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="instalar-skill-relatorio-"))
        self.addCleanup(_apagar, self.base)
        self.perfil = self.base / "perfil"
        self.perfil.mkdir()
        self.origem = self.base / "origem" / NOME
        (self.origem / "references").mkdir(parents=True)
        (self.origem / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
        (self.origem / "references" / "nota.md").write_text("nota fictícia", encoding="utf-8")
        self.env = {k: v for k, v in os.environ.items() if k not in ("HOMEDRIVE", "HOMEPATH")}
        self.env.update(USERPROFILE=str(self.perfil), HOME=str(self.perfil), PYTHONDONTWRITEBYTECODE="1",
                        PYTHONUTF8="1")
        visto = subprocess.run([sys.executable, "-c", "from pathlib import Path; print(Path.home())"],
                               env=self.env, capture_output=True, text=True).stdout.strip()
        if Path(visto).resolve() != self.perfil.resolve():
            self.skipTest(f"perfil descartável não isolado (Path.home() = {visto}); nada foi executado")
        self.copia = self.perfil / ".agents" / "skills" / NOME
        self.link = self.perfil / ".claude" / "skills" / NOME

    def rodar(self, *args, preludio: str = ""):
        codigo = "\n".join([preludio, "import runpy, sys", "sys.argv = [sys.argv[1], *sys.argv[2:]]",
                            "runpy.run_path(sys.argv[0], run_name='__main__')"])
        p = subprocess.run([sys.executable, "-B", "-c", codigo, str(INSTALADOR), *map(str, args)], env=self.env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        try:
            saida = json.loads(p.stdout)
        except ValueError:
            saida = None
        return p, saida

    def instalar(self):
        p, _ = self.rodar("instalar", "--origem", self.origem)
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])


class TestCOD02RemoverInstalacaoManual(_PerfilDescartavel):
    """Na 1.4.0, `remover --confirmar` dizia `removido: true` e deixava a pasta comum em ~/.claude/skills."""

    def test_cod02_remove_a_instalacao_manual_desta_skill(self):
        self.link.mkdir(parents=True)
        (self.link / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
        p, saida = self.rodar("remover", "--confirmar")
        self.assertFalse(os.path.lexists(self.link), "a instalação manual continuou em ~/.claude/skills")
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])
        self.assertIsNotNone(saida, f"saída não é JSON: {p.stdout[-300:]} {p.stderr[-300:]}")
        self.assertTrue(saida.get("removido"))

    def test_cod02_mantem_pasta_de_outra_skill_e_nao_diz_removido(self):
        self.link.mkdir(parents=True)
        (self.link / "SKILL.md").write_text("---\nname: outra-skill\ndescription: x\n---\n", encoding="utf-8")
        p, saida = self.rodar("remover", "--confirmar")
        self.assertTrue((self.link / "SKILL.md").exists(), "apagou uma pasta que não é desta skill")
        self.assertNotEqual(p.returncode, 0, "saiu com sucesso deixando a pasta no lugar")
        self.assertIsNotNone(saida, f"saída não é JSON: {p.stdout[-300:]} {p.stderr[-300:]}")
        self.assertFalse(saida.get("removido"), "disse removido com a pasta ainda lá")
        self.assertIn(str(self.link), saida.get("restam", []))


class TestCOD05SomenteLeitura(_PerfilDescartavel):
    """Na 1.4.0, um arquivo somente leitura na cópia fazia o `remover` parar com traceback no meio."""

    def test_cod05_remove_a_copia_com_arquivo_somente_leitura(self):
        self.instalar()
        os.chmod(self.copia / "references" / "nota.md", stat.S_IREAD)
        p, saida = self.rodar("remover", "--confirmar")
        self.assertFalse(self.copia.exists(), f"a cópia ficou: {p.stderr[-400:]}")
        self.assertFalse(os.path.lexists(self.link))
        self.assertEqual(p.returncode, 0)
        self.assertTrue(saida and saida.get("removido"))

    @unittest.skipUnless(os.name == "nt", "só no Windows um arquivo aberto não pode ser apagado")
    def test_cod05_falha_que_persiste_vira_estado_parcial_relatado(self):
        self.instalar()
        with open(self.copia / "references" / "nota.md", "rb"):
            p, saida = self.rodar("remover", "--confirmar")
        self.assertNotEqual(p.returncode, 0)
        self.assertIsNotNone(saida, f"saída não é JSON: {p.stderr[-400:]}")
        self.assertFalse(saida.get("removido"))
        self.assertIn(str(self.copia), saida.get("restam", []))
        self.assertTrue(saida.get("falhas"), "a falha não foi relatada")
        self.assertNotIn("Traceback", p.stderr)


class TestCOD03Fts5Informativo(_PerfilDescartavel):
    """`verificar` informa o FTS5 com o tokenizador do kit, sem que isso reprove a instalação da skill."""

    def test_cod03_verificar_informa_fts5_do_kit_sem_mudar_ok(self):
        self.instalar()
        p, saida = self.rodar("verificar", "--origem", self.origem)
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])
        info = (saida or {}).get("informativo") or {}
        self.assertIs(info.get("fts5_unicode61_remove_diacritics_2"), True, saida)
        p, saida = self.rodar("verificar", "--origem", self.origem, preludio=SEM_FTS5)
        self.assertEqual(p.returncode, 0, "FTS5 ausente não pode reprovar uma instalação correta da skill")
        self.assertTrue(saida.get("ok"))
        self.assertIs(saida["informativo"]["fts5_unicode61_remove_diacritics_2"], False)


if __name__ == "__main__":
    unittest.main()
