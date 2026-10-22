"""Auditoria Codex Security da 1.7.6 (21/10/2026), #2 — a restauração autorizava contra uma cópia não autenticada e
podia liberá-la.

Antes, a CLI lia a administração no banco DA CÓPIA antes de qualquer prova de autenticidade, e a restauração sem
âncora (sem `--sha256-manifesto` e sem livro de cópias ao lado do registro) com o código igual ao do kit era liberada
só com aviso. Uma cópia forjada e coerente (ACL de administração forjada, manifesto recalculado, código do kit)
passava nas duas. Agora a autorização vem da política da fundação viva; sem ela (origem perdida ou danificada), da
cópia autenticada pela âncora, com o banco conferido pelo hash do manifesto ancorado; sem as duas, de ninguém. Sem
âncora, a restauração não é liberada — nem com o código do kit — salvo `--aceitar-copia-sem-ancora "<motivo>"`, que
fica na resposta e na trilha. Cada teste exige o comportamento seguro; na 1.7.6 os de ataque falham por asserção.
Identidades, projetos e conteúdos são fictícios; nada é executado do código da cópia.
"""

from __future__ import annotations

import gc
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

from helpers import FoundationTestCase

from fundacao.core import backup
from fundacao.core.db import connect

MOTIVO = "cópia trazida pelo titular no disco externo, conferida à mão (fictício)"


def sha256_de(caminho: Path) -> str:
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


class _Base(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.extra = []
        self.log = self.root / "state" / "retiradas.jsonl"

    def tearDown(self):
        for p in self.extra:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
        super().tearDown()

    def pasta(self, nome: str) -> Path:
        p = self.root.parent / f"{self.root.name}-{nome}"
        self.extra.append(p)
        return p

    def cli(self, principal: str | None, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "FUNDACAO_PRINCIPAL"}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if principal:
            env["FUNDACAO_PRINCIPAL"] = principal
        return subprocess.run([sys.executable, "-m", "fundacao", "--raiz", str(self.root), *args],
                              capture_output=True, text=True, encoding="utf-8", cwd=str(self.root), env=env)

    def registro_guardado_sem_livro(self) -> Path:
        """Recuperação de desastre: só o registro protegido foi guardado, sem o livro de cópias ao lado."""
        guardado = self.pasta("guardado")
        guardado.mkdir()
        shutil.copy2(self.log, guardado / "retiradas.jsonl")
        return guardado / "retiradas.jsonl"

    def forjar_admin(self, snap: Path, quem: str) -> None:
        """Cópia forjada e autoconsistente: `quem` passa a administrar a fundação no banco da cópia, e o manifesto
        vizinho é recalculado (hash e contagens do banco); o código continua igual ao do kit."""
        db = snap / "state" / "state.sqlite"
        con = sqlite3.connect(str(db))
        con.execute("INSERT INTO acl VALUES (?, 'foundation', 'admin', 'forjado', '2026-10-21T00:00:00Z')", (quem,))
        con.commit()
        con.close()
        gc.collect()
        mf = snap / "manifest.json"
        m = json.loads(mf.read_text(encoding="utf-8"))
        m["db"] = backup.logical_summary(db, copia=True)
        m["db_sha256"] = sha256_de(db)
        mf.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")

    def admin_no_restaurado(self, raiz: Path, quem: str) -> bool:
        con = connect(raiz / "state" / "state.sqlite")
        try:
            return con.execute("SELECT 1 FROM acl WHERE subject = ? AND resource = 'foundation' AND action = 'admin'",
                               (quem,)).fetchone() is not None
        finally:
            con.close()

    def eventos_de_fim(self, raiz: Path) -> list[dict]:
        con = connect(raiz / "state" / "state.sqlite")
        try:
            return [json.loads(r["payload_json"]) for r in
                    con.execute("SELECT payload_json FROM event WHERE kind = 'restore_completed' ORDER BY seq")]
        finally:
            con.close()


class TestN2LiberacaoSoComAncoraOuAceite(_Base):
    def test_2_copia_forjada_sem_ancora_nao_e_liberada_nem_com_o_codigo_do_kit(self):
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "a2-forjada")
        original = sha256_de(snap / "manifest.json")  # a âncora que o titular guardou fora da cópia
        self.forjar_admin(snap, "operador-juridico")
        self.assertTrue(backup.verify_backup(snap)["ok"], "pré-condição: a cópia forjada é autoconsistente")
        registro = self.registro_guardado_sem_livro()
        dest = self.pasta("dest")
        res = backup.restore(snap, dest, registro)
        self.assertFalse(res["released"], "cópia forjada, sem âncora e com o código do kit, foi liberada")
        self.assertIn("--aceitar-copia-sem-ancora", res["reason"])
        self.assertFalse(dest.exists(), "nada pode ser copiado para o destino")
        res = backup.restore(snap, dest, registro, sha256_manifesto=original)
        self.assertFalse(res["released"])
        self.assertEqual(res["check"]["ancora"]["situacao"], "divergente")
        self.assertFalse(dest.exists())

    def test_2_aceite_sem_ancora_exige_motivo_e_fica_na_resposta_e_na_trilha(self):
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "a2-aceite")
        registro = self.registro_guardado_sem_livro()
        dest = self.pasta("dest")
        for sem_motivo in ("", "   ", True):
            with self.subTest(aceite=sem_motivo):
                res = backup.restore(snap, dest, registro, aceitar_copia_sem_ancora=sem_motivo)
                self.assertFalse(res["released"], "aceite sem motivo liberou a cópia sem âncora")
                self.assertFalse(dest.exists())
        ok = backup.restore(snap, dest, registro, aceitar_copia_sem_ancora=MOTIVO)
        self.assertTrue(ok["released"], ok)
        self.assertEqual(ok["ancora"]["situacao"], "ausente")
        self.assertIn("decisão explícita", ok["ressalva_ancora"])
        self.assertIn(MOTIVO, ok["ressalva_ancora"])
        self.assertIn(MOTIVO, self.eventos_de_fim(dest)[-1]["ressalva_ancora"])

    def test_2_so_a_ancora_independente_libera_sem_aceite(self):
        snap = self.pasta("snap")
        res = backup.create_backup(self.root, snap, "a2-ancora")
        registro = self.registro_guardado_sem_livro()
        certa = self.pasta("dest-digest")
        rep = backup.restore(snap, certa, registro, sha256_manifesto=res["sha256_manifesto"])
        self.assertTrue(rep["released"], rep)
        self.assertNotIn("ressalva_ancora", rep)
        pelo_livro = self.pasta("dest-livro")  # o livro de cópias ao lado do registro protegido da raiz
        rep = backup.restore(snap, pelo_livro, self.log)
        self.assertTrue(rep["released"], rep)
        self.assertEqual(rep["ancora"]["situacao"], "conferida")
        self.forjar_admin(snap, "operador-juridico")  # a mesma pasta, agora forjada: o livro não a tem
        forjada = self.pasta("dest-forjada")
        rep = backup.restore(snap, forjada, self.log)
        self.assertFalse(rep["released"])
        self.assertFalse(forjada.exists())


class TestN2AutorizacaoNaoVemDaCopiaNaoAutenticada(_Base):
    def test_2_cli_com_fundacao_viva_nao_autoriza_pela_acl_forjada_na_copia(self):
        snap = self.pasta("snap")
        self.assertEqual(self.cli("operador-lab", "backup", "criar", "--destino", str(snap)).returncode, 0)
        self.forjar_admin(snap, "operador-juridico")  # a cópia diz que operador-juridico administra a fundação
        registro = self.registro_guardado_sem_livro()
        dest = self.pasta("dest")
        for acao, extra in (("verificar", []), ("restaurar", ["--destino", str(dest), "--retiradas", str(registro)])):
            with self.subTest(acao=acao):
                p = self.cli("operador-juridico", "backup", acao, "--origem", str(snap), *extra)
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIn("E_ACCESS_DENIED", p.stderr)
        self.assertFalse(dest.exists())

    def test_2_cli_administrador_revogado_depois_da_copia_nao_restaura(self):
        self.policy.grant(self.admin, "operador-engenharia", "foundation", "admin")
        snap = self.pasta("snap")
        self.assertEqual(self.cli("operador-engenharia", "backup", "criar", "--destino", str(snap)).returncode, 0)
        self.policy.revoke(self.admin, "operador-engenharia", "foundation", "admin")
        dest = self.pasta("dest")
        p = self.cli("operador-engenharia", "backup", "restaurar", "--origem", str(snap), "--destino", str(dest),
                     "--retiradas", str(self.log))
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("E_ACCESS_DENIED", p.stderr)
        self.assertFalse(dest.exists())
        ok = self.cli("operador-lab", "backup", "restaurar", "--origem", str(snap), "--destino", str(dest),
                      "--retiradas", str(self.log))
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertFalse(self.admin_no_restaurado(dest, "operador-engenharia"), "revogação posterior não reaplicada")

    def test_2_sem_fundacao_viva_so_a_copia_ancorada_autoriza(self):
        snap = self.pasta("snap")
        p = self.cli("operador-lab", "backup", "criar", "--destino", str(snap))
        self.assertEqual(p.returncode, 0, p.stderr)
        ancora = json.loads(p.stdout)["sha256_manifesto"]
        registro = self.registro_guardado_sem_livro()
        self.con.close()
        gc.collect()
        for nome in ("state.sqlite", "state.sqlite-wal", "state.sqlite-shm", backup.LIVRO_COPIAS):
            (self.root / "state" / nome).unlink(missing_ok=True)  # desastre: a fundação viva e o livro se perderam
        dest = self.pasta("dest")
        restaurar = ("backup", "restaurar", "--origem", str(snap), "--destino", str(dest), "--retiradas", str(registro))
        sem = self.cli("operador-lab", *restaurar)
        self.assertEqual(sem.returncode, 2, sem.stdout + sem.stderr)
        self.assertIn("E_ACCESS_DENIED", sem.stderr)
        self.assertIn("--sha256-manifesto", sem.stderr)
        self.assertFalse(dest.exists())
        negado = self.cli("operador-juridico", *restaurar, "--sha256-manifesto", ancora)
        self.assertEqual(negado.returncode, 2, negado.stdout + negado.stderr)
        self.assertIn("E_ACCESS_DENIED", negado.stderr)
        ok = self.cli("operador-lab", *restaurar, "--sha256-manifesto", ancora)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        saida = json.loads(ok.stdout)
        self.assertTrue(saida["released"])
        self.assertEqual(saida["autorizacao"]["identidade"], "operador-lab")
        self.assertIn("âncora", saida["autorizacao"]["politica"])
        self.assertFalse((self.root / "state" / "state.sqlite").exists(), "nada pode ser criado na origem")
        self.forjar_admin(snap, "operador-juridico")  # forjada depois: o digest guardado não confere mais
        forjada = self.pasta("dest-forjada")
        p = self.cli("operador-juridico", "backup", "restaurar", "--origem", str(snap), "--destino", str(forjada),
                     "--retiradas", str(registro), "--sha256-manifesto", ancora, "--aceitar-copia-sem-ancora", MOTIVO)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("E_ACCESS_DENIED", p.stderr)
        self.assertFalse(forjada.exists())

    def test_2_cli_sem_ancora_so_libera_com_aceite_e_avisa(self):
        snap = self.pasta("snap")
        self.assertEqual(self.cli("operador-lab", "backup", "criar", "--destino", str(snap)).returncode, 0)
        registro = self.registro_guardado_sem_livro()
        dest = self.pasta("dest")
        restaurar = ("backup", "restaurar", "--origem", str(snap), "--destino", str(dest), "--retiradas", str(registro))
        r = self.cli("operador-lab", *restaurar)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertFalse(json.loads(r.stdout)["released"])
        self.assertFalse(dest.exists())
        r = self.cli("operador-lab", *restaurar, "--aceitar-copia-sem-ancora", MOTIVO)
        self.assertEqual(r.returncode, 0, r.stderr)
        saida = json.loads(r.stdout)
        self.assertEqual(saida["ancora"]["situacao"], "ausente")
        self.assertIn(MOTIVO, saida["ressalva_ancora"])
        self.assertIn("W_COPIA_SEM_ANCORA", r.stderr)


if __name__ == "__main__":
    unittest.main()
