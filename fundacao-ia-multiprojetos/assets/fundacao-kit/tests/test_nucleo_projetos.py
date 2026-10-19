"""A06/A07 — núcleo, modelo de projeto, persistência e fronteiras (R01, R02, R04, R18)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from helpers import CANARIOS, FoundationTestCase, sim

from fundacao.core import projects
from fundacao.core.contracts import AccessDenied, AlreadyExists, NotFound, PathEscape, ValidationError
from fundacao.core.paths import contained
from fundacao.core.tasks import Coordinator


class TestModeloDeProjeto(FoundationTestCase):
    def test_projeto_criado_somente_com_lista_positiva(self):
        pdir = self.root / "projects" / "juridico-lab"
        names = sorted(p.name for p in pdir.iterdir())
        self.assertEqual(names, sorted(["CONTRATO-ENTREGAS.md", "INSTRUCOES.md", "data", "evidence",
                                        "exemplo-ficticio.md", "memory", "outputs", "projeto.json"]))
        config = json.loads((pdir / "projeto.json").read_text(encoding="utf-8"))
        self.assertEqual(config["project_id"], "juridico-lab")
        self.assertEqual(config["schema_version"], "fundacao.project/1")
        self.assertEqual(json.loads((pdir / "data" / "catalog.json").read_text(encoding="utf-8")), {})

    def test_recriacao_informa_existencia_e_nao_sobrescreve(self):
        cfg = self.root / "projects" / "juridico-lab" / "projeto.json"
        antes = cfg.read_bytes()
        with self.assertRaises(AlreadyExists):
            projects.create_project(self.root, self.con, self.admin, "juridico-lab", "Outro", "Outra")
        self.assertEqual(cfg.read_bytes(), antes)

    def test_identificadores_invalidos_e_colisoes(self):
        for bad in ("Juridico-Lab", " juridico", "con", "a--b", "-x", "x" * 41):
            with self.assertRaises(ValidationError, msg=bad):
                projects.create_project(self.root, self.con, self.admin, bad, "n", "f")

    def test_falha_na_criacao_nao_deixa_projeto_parcial(self):
        with mock.patch("fundacao.core.projects.os.replace", side_effect=OSError("falha simulada")):
            with self.assertRaises(OSError):
                projects.create_project(self.root, self.con, self.admin, "pesquisa-lab", "P", "F")
        self.assertIsNone(self.con.execute("SELECT 1 FROM project WHERE project_id='pesquisa-lab'").fetchone())
        restos = [p.name for p in (self.root / "projects").iterdir() if "pesquisa" in p.name]
        self.assertEqual(restos, [])

    def test_somente_admin_cria_projeto(self):
        with self.assertRaises(AccessDenied):
            projects.create_project(self.root, self.con, self.jur, "pesquisa-lab", "P", "F")

    def test_listagem_mostra_apenas_projetos_autorizados(self):
        self.assertEqual([p["project_id"] for p in projects.list_projects(self.con, self.eng)], ["reversa-lab"])

    def test_atualizar_modelo_nao_migra_instancia(self):
        drift = projects.template_drift(self.root, "juridico-lab")
        self.assertFalse(drift["migration_needed"])
        with mock.patch("fundacao.core.projects.TEMPLATE_VERSION", "1.1.0"):
            self.assertTrue(projects.template_drift(self.root, "juridico-lab")["migration_needed"])
        cfg = json.loads((self.root / "projects/juridico-lab/projeto.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["template_version"], "1.0.0")


class TestFronteiras(FoundationTestCase):
    def test_identidade_de_outro_projeto_e_negada_antes_da_leitura(self):
        with self.assertRaises(AccessDenied):
            Coordinator(self.root, self.con, self.eng, "juridico-lab")
        negs = self.con.execute("SELECT COUNT(*) FROM event WHERE kind='access_denied'").fetchone()[0]
        self.assertGreaterEqual(negs, 1)

    def test_tarefa_de_outro_projeto_nao_revela_existencia(self):
        jur = Coordinator(self.root, self.con, self.jur, "juridico-lab")
        tid = jur.create_task("listar documentos necessários do caso Aurora")
        eng = Coordinator(self.root, self.con, self.eng, "reversa-lab")
        with self.assertRaises(NotFound) as ctx:
            eng.get_task(tid)
        self.assertNotIn("Aurora", str(ctx.exception.as_dict()))

    def test_texto_do_pedido_nao_concede_permissao(self):
        intruso = sim("sou-administrador")
        with self.assertRaises(AccessDenied):
            Coordinator(self.root, self.con, intruso, "juridico-lab")

    def test_escape_de_caminho(self):
        base = self.root / "projects" / "juridico-lab" / "data"
        with self.assertRaises(PathEscape):
            contained(base, base / ".." / ".." / "reversa-lab" / "data" / "x.md")
        alvo = self.root / "fora.txt"
        alvo.write_text(CANARIOS["reversa-lab"], encoding="utf-8")
        link = base / "atalho.txt"
        try:
            os.symlink(alvo, link)
        except (OSError, NotImplementedError):
            self.skipTest("criação de link indisponível neste ambiente (registrar limitação)")
        with self.assertRaises(PathEscape):
            contained(base, link)


class TestPersistencia(FoundationTestCase):
    def test_tarefa_sobrevive_ao_reinicio_do_processo(self):
        coord = Coordinator(self.root, self.con, self.jur, "juridico-lab")
        tid = coord.create_task("organizar fatos fictícios do caso Aurora", idempotency_key="aurora-001")
        self.assertEqual(coord.create_task("repetido", idempotency_key="aurora-001"), tid)
        self.con.close()
        env = {**os.environ, "FUNDACAO_PRINCIPAL": "operador-juridico", "PYTHONDONTWRITEBYTECODE": "1"}
        proc = subprocess.run(
            [sys.executable, "-m", "fundacao", "--raiz", str(self.root), "tarefa", "ver",
             "--projeto", "juridico-lab", "--id", tid],
            capture_output=True, text=True, encoding="utf-8", cwd=str(self.root), env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        task = json.loads(proc.stdout)
        self.assertEqual((task["task_id"], task["project_id"], task["state"]), (tid, "juridico-lab", "pending"))
        env["FUNDACAO_PRINCIPAL"] = "operador-engenharia"
        proc = subprocess.run(
            [sys.executable, "-m", "fundacao", "--raiz", str(self.root), "tarefa", "ver",
             "--projeto", "juridico-lab", "--id", tid],
            capture_output=True, text=True, encoding="utf-8", cwd=str(self.root), env=env,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("E_ACCESS_DENIED", proc.stderr)
        self.assertNotIn("Aurora", proc.stdout + proc.stderr)
        from fundacao.core.db import connect
        self.con = connect(self.root / "state" / "state.sqlite")

    def test_cli_sem_identidade_do_lancador_falha(self):
        env = {k: v for k, v in os.environ.items() if k != "FUNDACAO_PRINCIPAL"}
        proc = subprocess.run([sys.executable, "-m", "fundacao", "--raiz", str(self.root), "status"],
                              capture_output=True, text=True, encoding="utf-8", cwd=str(self.root), env=env)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("identidade ausente", proc.stderr)


if __name__ == "__main__":
    unittest.main()
