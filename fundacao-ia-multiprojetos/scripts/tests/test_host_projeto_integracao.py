"""HOST × PORTEIRO com o porteiro real (1.7.10; contratos do lote 2, §4 e §6; revisão do lote 2).

O porteiro.json que o `instalar-projeto` grava tem de passar no `porteiro.py conferir` real — o mesmo que o lançador
roda antes de abrir —, e a conta do kit tem de ser uma só: o preparo usa o `sha256_do_kit` do próprio porteiro (antes
usava outra receita, e o lançador nunca abriria); e a pasta de trabalho que o porteiro real deixa ao morrer por SIGKILL
sai pela limpeza do lançador, só sem ele de pé. Aqui roda com o porteiro do pacote PORTEIRO que estiver na skill;
até a integração do lote 2, a árvore do HOST não o tem e o teste fica pulado, com o motivo (o coordenador o roda na
integração). Pastas descartáveis, sem root; nada da raiz real.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from apoio import ENV
from test_host_projeto_apoio import (LINUX, PYTHON_LINUX, carregar_preparo, claude_de_ensaio, instalar,
                                     porteiro_real_na_skill, raiz_de_ensaio, skill_de_ensaio)


@unittest.skipUnless(LINUX and porteiro_real_na_skill(),
                     "o porteiro real (pacote PORTEIRO) ainda não está nesta árvore: o coordenador roda na integração")
class PorteiroReal(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="host-porteiro-1710-")).resolve()
        self.skill = skill_de_ensaio(self.base, porteiro_real=True)
        self.raiz = raiz_de_ensaio(self.base, self.skill)
        (self.base / "home").mkdir()
        self.claude = claude_de_ensaio(self.base / "claude-ensaio")
        self.area = self.base / "area" / "projetos" / "caso-real"
        self.porteiro = self.skill / "assets" / "host" / "wsl" / "porteiro.py"

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def conferir(self) -> subprocess.CompletedProcess:
        return subprocess.run([PYTHON_LINUX, "-I", "-B", str(self.porteiro), "conferir", "--config",
                               str(self.area / "porteiro.json")], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=ENV, timeout=120)

    def test_porteiro_real_aceita_o_porteiro_json_do_preparo(self):
        r = instalar(self.skill, self.raiz, self.base, "caso-real", self.claude)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        c = self.conferir()
        self.assertEqual(c.returncode, 0, c.stdout + c.stderr)
        self.assertTrue(json.loads(c.stdout)["ok"])
        m = carregar_preparo(self.skill)
        self.assertTrue(m.conferir_abertura(self.raiz, "caso-real", self.area)["ok"])

    def test_pasta_de_trabalho_do_porteiro_morto_sai_so_sem_ele(self):
        """O porteiro real cria ~/.fundacao/porteiro/<p>/trabalho-* ao servir e só a apaga ao encerrar; morto por
        SIGKILL, ela fica. A limpeza do lançador acha a pasta pelo nome e pelo lugar dele, a mantém com ele de pé e a
        apaga depois (reconferência do lote 2)."""
        r = instalar(self.skill, self.raiz, self.base, "caso-real", self.claude)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        casa = self.base / "home"
        pasta = casa / ".fundacao" / "porteiro" / "caso-real"
        m = carregar_preparo(self.skill)
        p = subprocess.Popen([PYTHON_LINUX, "-I", "-B", str(self.porteiro), "servir", "--config",
                              str(self.area / "porteiro.json"), "--fila", str(self.raiz / "projects" / "caso-real" /
                                                                             ".porteiro"),
                              "--pid-lancador", str(os.getpid())], cwd="/", stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             env={"PATH": "/usr/bin:/bin", "HOME": str(casa), "LANG": "C.UTF-8"})
        try:
            limite, nomes = time.monotonic() + 60, []
            while not nomes and time.monotonic() < limite and p.poll() is None:
                time.sleep(0.1)
                nomes = sorted(n for n in (os.listdir(pasta) if pasta.is_dir() else []) if n.startswith("trabalho-"))
            self.assertEqual(len(nomes), 1, (nomes, p.poll()))
            self.assertTrue(m.TRABALHO_DO_PORTEIRO.fullmatch(nomes[0]), nomes)
            res = m.limpar_trabalho_do_porteiro(casa, self.raiz, "caso-real")
            self.assertEqual(res["apagadas"], [], res)  # de pé: fica
            self.assertIn("porteiro deste projeto", res["motivo"])
        finally:
            p.kill()  # SIGKILL: o porteiro não chega a encerrar
            p.wait(timeout=30)
        self.assertTrue((pasta / nomes[0]).is_dir())
        res = m.limpar_trabalho_do_porteiro(casa, self.raiz, "caso-real")
        self.assertEqual(res["apagadas"], nomes, res)
        self.assertFalse(os.path.lexists(pasta / nomes[0]))

    def test_pyc_plantado_muda_as_duas_contas_juntas(self):
        r = instalar(self.skill, self.raiz, self.base, "caso-real", self.claude)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        (self.raiz / "fundacao" / "plantado.pyc").write_bytes(b"\x00bytecode de ensaio")
        self.assertEqual(self.conferir().returncode, 2)  # o porteiro recusa
        m = carregar_preparo(self.skill)
        res = m.conferir_abertura(self.raiz, "caso-real", self.area)
        self.assertTrue(any("árvore kit" in p for p in res["problemas"]), res)  # e o preparo vê o mesmo


if __name__ == "__main__":
    unittest.main()
