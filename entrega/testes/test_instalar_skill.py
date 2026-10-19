"""Auditoria externa da 1.3.4 — `instalar_skill.py` (F17): junções sem `os.path.isjunction`.

Nada é instalado no perfil real: cada execução usa um perfil DESCARTÁVEL (USERPROFILE e HOME
apontam para uma pasta temporária, conferido antes de rodar) e a origem é uma skill mínima fictícia.
Limite declarado: este ambiente só tem Python 3.12. A ausência da API do 3.10/3.11 é SIMULADA
removendo `os.path.isjunction` no processo filho; não é um ciclo real em 3.10/3.11.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ENTREGA = Path(__file__).resolve().parents[1]
INSTALADOR = ENTREGA / "instalar_skill.py"
NOME = "fundacao-ia-multiprojetos"


def carregar_modulo():
    spec = importlib.util.spec_from_file_location("instalar_skill_em_teste", INSTALADOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # só define constantes e funções; não toca o disco
    return mod


class TestF17Juncoes(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="instalar-skill-teste-"))
        self.perfil = self.base / "perfil"
        self.perfil.mkdir()
        self.origem = self.base / "origem" / NOME
        (self.origem / "references").mkdir(parents=True)
        (self.origem / "SKILL.md").write_text("---\nname: fundacao-ia-multiprojetos\ndescription: ficticia\n---\n",
                                              encoding="utf-8")
        (self.origem / "references" / "nota.md").write_text("nota fictícia", encoding="utf-8")
        self.env = {k: v for k, v in os.environ.items() if k not in ("HOMEDRIVE", "HOMEPATH")}
        self.env.update(USERPROFILE=str(self.perfil), HOME=str(self.perfil), PYTHONDONTWRITEBYTECODE="1",
                        PYTHONUTF8="1")
        visto = subprocess.run([sys.executable, "-c", "from pathlib import Path; print(Path.home())"],
                               env=self.env, capture_output=True, text=True).stdout.strip()
        if Path(visto).resolve() != self.perfil.resolve():
            self.skipTest(f"perfil descartável não isolado (Path.home() = {visto}); nada foi executado")

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def rodar(self, *args, sem_isjunction: bool = False, versao: tuple | None = None):
        codigo = ["import os.path, runpy, sys"]
        if sem_isjunction:
            codigo.append("if hasattr(os.path, 'isjunction'): del os.path.isjunction")
        if versao:
            codigo.append(f"sys.version_info = {versao!r}")
        codigo.append("sys.argv = [sys.argv[1], *sys.argv[2:]]")
        codigo.append("runpy.run_path(sys.argv[0], run_name='__main__')")
        return subprocess.run([sys.executable, "-B", "-c", "\n".join(codigo), str(INSTALADOR), *map(str, args)],
                              env=self.env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=120)

    def ciclo(self, sem_isjunction: bool):
        link = self.perfil / ".claude" / "skills" / NOME
        copia = self.perfil / ".agents" / "skills" / NOME
        for acao, extra in (("instalar", ("--origem", self.origem)), ("verificar", ("--origem", self.origem)),
                            ("atualizar", ("--origem", self.origem)), ("remover", ("--confirmar",))):
            p = self.rodar(acao, *extra, sem_isjunction=sem_isjunction)
            self.assertEqual(p.returncode, 0, f"{acao}: {p.stdout[-500:]} {p.stderr[-500:]}")
        self.assertFalse(os.path.lexists(link), "a ligação ficou no perfil depois de remover (pendente)")
        self.assertFalse(copia.exists())

    @unittest.skipUnless(os.name == "nt", "junção de diretório só existe no Windows")
    def test_f17_juncao_e_reconhecida_sem_os_path_isjunction(self):
        alvo, link = self.base / "alvo", self.base / "ligacao"
        alvo.mkdir()
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(alvo)], capture_output=True, text=True,
                           errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        mod = carregar_modulo()
        with mock.patch.object(mod.os.path, "isjunction", None):
            self.assertTrue(mod.e_ligacao(link), "junção não reconhecida sem a API do Python 3.12")
        self.assertFalse(mod.e_ligacao(alvo))

    def test_f17_ciclo_completo_simulando_python_sem_isjunction(self):
        self.ciclo(sem_isjunction=True)

    def test_f17_ciclo_completo_com_a_api_do_python_3_12(self):
        self.ciclo(sem_isjunction=False)

    def test_f17_versao_nao_suportada_falha_antes_de_alterar(self):
        p = self.rodar("instalar", "--origem", self.origem, versao=(3, 9, 18, "final", 0))
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(sorted(x.name for x in self.perfil.iterdir()), [], "criou cópia ou ligação parcial")
        self.assertIn("3.10", p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
