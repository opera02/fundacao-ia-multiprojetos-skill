"""Backup completo (1.5.0): os registros da fundação fora do kit — docs/, evidence/, ferramentas/, tests/ e a
RETOMADA — entram na cópia por padrão, sem o "complemento" que a implantação real precisou a cada backup
(auditoria da implantação de 2026-10-19/20). A lista é configurável em registry/backup_policy.json; caminho
inválido ou destino dentro de uma pasta copiada recusam antes de copiar; segredo continua fora."""

from __future__ import annotations

import json
import shutil

from helpers import FoundationTestCase

from fundacao.core import backup
from fundacao.core.contracts import ValidationError

REGISTROS = {"docs/GUIA.md": "guia fictício", "evidence/EVIDENCIAS.md": "índice fictício",
             "ferramentas/ajuda.py": "print('ferramenta fictícia')", "tests/test_local.py": "# teste local",
             "RETOMADA.md": "# RETOMADA fictícia"}


class TestBackupCompleto(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.extra = []
        self.log = self.root / "state" / "retiradas.jsonl"
        # Numa raiz implantada, registry/ traz a política local da fundação; este teste confere a padrão (1.5.1).
        (self.root / "registry" / backup.POLITICA_BACKUP).unlink(missing_ok=True)
        for rel, texto in {**REGISTROS, "evidence/.env": "SEGREDO=FICTICIO", "notas/rascunho.md": "fora do padrão"}.items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(texto, encoding="utf-8")

    def tearDown(self):
        for p in self.extra:
            shutil.rmtree(p, ignore_errors=True)
        super().tearDown()

    def pasta(self, nome: str):
        p = self.root.parent / f"{self.root.name}-{nome}"
        self.extra.append(p)
        return p

    def politica(self, incluir) -> None:
        (self.root / "registry" / backup.POLITICA_BACKUP).write_text(
            json.dumps({"schema_version": "fundacao.backup_policy/1", "incluir": incluir}), encoding="utf-8")

    def test_registros_entram_por_padrao_e_voltam_na_restauracao(self):
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "completo-1")
        caminhos = {f["path"] for f in m["files"]}
        self.assertLessEqual(set(REGISTROS), caminhos)
        self.assertNotIn("evidence/.env", caminhos)            # segredo continua fora
        self.assertNotIn("notas/rascunho.md", caminhos)        # fora da lista padrão
        self.assertEqual(m["registros_incluidos"], list(backup.REGISTROS_PADRAO))
        self.assertTrue(backup.verify_backup(snap)["ok"])
        dest = self.pasta("dest")
        rep = backup.restore(snap, dest, self.log)
        self.assertTrue(rep["released"], rep)
        for rel, texto in REGISTROS.items():
            self.assertEqual((dest / rel).read_text(encoding="utf-8"), texto)

    def test_politica_local_troca_a_lista(self):
        self.politica(["notas", "RETOMADA.md"])
        m = backup.create_backup(self.root, self.pasta("snap"), "completo-2")
        caminhos = {f["path"] for f in m["files"]}
        self.assertIn("notas/rascunho.md", caminhos)
        self.assertIn("RETOMADA.md", caminhos)
        self.assertNotIn("docs/GUIA.md", caminhos)
        self.assertEqual(m["registros_incluidos"], ["notas", "RETOMADA.md"])

    def test_instrucoes_da_raiz_entram_mesmo_com_politica_local(self):
        """AGENTS.md e CLAUDE.md da raiz (gerados pela skill, com o trecho do titular) vão sempre na cópia."""
        for nome in ("AGENTS.md", "CLAUDE.md"):
            (self.root / nome).write_text("instrução fictícia: " + nome, encoding="utf-8")
        self.politica(["notas"])
        snap = self.pasta("snap")
        m = backup.create_backup(self.root, snap, "instrucoes")
        self.assertLessEqual({"AGENTS.md", "CLAUDE.md"}, {f["path"] for f in m["files"]})
        dest = self.pasta("dest")
        rep = backup.restore(snap, dest, self.log)
        self.assertTrue(rep["released"], rep)
        for nome in ("AGENTS.md", "CLAUDE.md"):
            self.assertEqual((dest / nome).read_text(encoding="utf-8"), "instrução fictícia: " + nome)

    def test_politica_invalida_e_destino_dentro_da_copia_recusam_antes_de_copiar(self):
        for incluir in (["../fora"], ["state"], [str(self.root.parent / "fora")], [".git"], "docs", [""]):
            with self.subTest(incluir=incluir):
                self.politica(incluir)
                snap = self.pasta(f"snap-{len(self.extra)}")
                with self.assertRaises(ValidationError):
                    backup.create_backup(self.root, snap, "invalida")
                self.assertFalse(snap.exists())
        (self.root / "registry" / backup.POLITICA_BACKUP).unlink()
        for dentro in (self.root / "docs" / "copias" / "c1", self.root / "projects" / "copia"):
            with self.subTest(destino=dentro):
                with self.assertRaises(ValidationError):
                    backup.create_backup(self.root, dentro, "recursiva")
                self.assertFalse(dentro.exists())
