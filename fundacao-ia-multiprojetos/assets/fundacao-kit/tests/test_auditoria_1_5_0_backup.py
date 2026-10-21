"""Auditoria da 1.4.5 — backup e restauração do kit (#24 e #8 do relatório de varredura).

#24: o backup não segue ligação (junção ou link simbólico) de projeto para fora da raiz, e uma
ligação dentro da cópia não confere. #8: a cópia é conferida por uma âncora guardada FORA dela — o
SHA-256 do manifest.json, devolvido pelo `backup criar` e anotado no livro de cópias da fundação
(`state/copias.jsonl`, ao lado do registro protegido). Sem âncora, cópia que não consta no livro ou
cujo código difere do kit que restaura só é liberada por decisão explícita. A CLI da âncora é
conferida em `test_restauracao.py`.
Cada teste exige o comportamento seguro; na 1.4.5 (base a8e74c4) os de ataque falham por asserção.
Identidades, projetos e conteúdos são fictícios; nada é executado do código da cópia.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import unittest
from pathlib import Path

from apoio_auditoria import criar_ligacao_dir, criar_link_arquivo
from helpers import FoundationTestCase

from fundacao.core import backup
from fundacao.core.db import connect

EXTERNO = "CREDENCIAL-FICTICIA-FORA-DA-RAIZ"


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
                shutil.rmtree(p, ignore_errors=True)  # não atravessa junção (3.8+)
            else:
                p.unlink(missing_ok=True)
        super().tearDown()

    def pasta(self, nome: str) -> Path:
        p = self.root.parent / f"{self.root.name}-{nome}"
        self.extra.append(p)
        return p

    def registro_guardado_sem_livro(self) -> Path:
        """Recuperação de desastre: só o registro protegido foi guardado, sem o livro ao lado."""
        guardado = self.pasta("guardado")
        guardado.mkdir()
        shutil.copy2(self.log, guardado / "retiradas.jsonl")
        return guardado / "retiradas.jsonl"

    def eventos_de_fim(self, raiz: Path) -> list[dict]:
        con = connect(raiz / "state" / "state.sqlite")
        try:
            return [json.loads(r["payload_json"]) for r in
                    con.execute("SELECT payload_json FROM event WHERE kind = 'restore_completed' ORDER BY seq")]
        finally:
            con.close()


class TestN24BackupNaoSegueLigacao(_Base):
    def setUp(self):
        super().setUp()
        self.fora = self.pasta("fora")
        self.fora.mkdir()
        (self.fora / "credencial.txt").write_text(EXTERNO, encoding="utf-8")

    def assert_sem_conteudo_externo(self, snap: Path):
        copiados = [p for p in (snap / "files").rglob("*") if p.is_file()]
        self.assertFalse([p for p in copiados if EXTERNO.encode() in p.read_bytes()],
                         "o backup copiou conteúdo de fora da raiz")

    def test_24_juncao_de_projeto_para_fora_nao_entra_na_copia(self):
        dados = self.root / "projects" / "juridico-lab" / "data"
        dados.mkdir(parents=True, exist_ok=True)
        tipo = criar_ligacao_dir(dados / "atalho", self.fora)
        snap = self.pasta("snap")
        res = backup.create_backup(self.root, snap, "n24")
        self.assertEqual([f["path"] for f in res["files"] if "atalho" in f["path"]], [],
                         f"{tipo}: o backup seguiu a ligação")
        self.assert_sem_conteudo_externo(snap)
        self.assertEqual(res["ligacoes_nao_seguidas"], ["projects/juridico-lab/data/atalho"])
        self.assertIn("ligaç", res["aviso"])
        self.assertTrue(backup.verify_backup(snap)["ok"])

    def test_24_link_de_arquivo_para_fora_nao_entra_na_copia(self):
        criar_link_arquivo(self.root / "projects" / "juridico-lab" / "inocente.md", self.fora / "credencial.txt")
        snap = self.pasta("snap")
        res = backup.create_backup(self.root, snap, "n24-arquivo")
        self.assertNotIn("projects/juridico-lab/inocente.md", [f["path"] for f in res["files"]])
        self.assertEqual(res["ligacoes_nao_seguidas"], ["projects/juridico-lab/inocente.md"])
        self.assert_sem_conteudo_externo(snap)

    def test_24_ligacao_dentro_da_copia_nao_confere_nem_e_restaurada(self):
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "n24-copia")
        vazia = self.pasta("alvo-vazio")  # vazia agora; poderia ser preenchida entre a conferência e a cópia
        vazia.mkdir()
        criar_ligacao_dir(snap / "files" / "projects" / "juridico-lab" / "atalho", vazia)
        ver = backup.verify_backup(snap)
        self.assertFalse(ver["ok"], "ligação dentro da cópia passou na verificação")
        self.assertEqual(ver["ligacoes"], ["projects/juridico-lab/atalho"])
        dest = self.pasta("dest")
        self.assertFalse(backup.restore(snap, dest, self.log)["released"])
        self.assertFalse(dest.exists())


class TestN8AncoraExterna(_Base):
    def recalcular_manifesto(self, snap: Path, rel: str | None = None) -> None:
        """Quem escreve na pasta da cópia também recalcula o manifesto vizinho (hash, tamanho, banco)."""
        mf = snap / "manifest.json"
        m = json.loads(mf.read_text(encoding="utf-8"))
        for f in m["files"]:
            if f["path"] == rel:
                alvo = snap / "files" / rel
                f.update(sha256=sha256_de(alvo), size=alvo.stat().st_size)
        m["db_sha256"] = sha256_de(snap / "state" / "state.sqlite")
        mf.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")

    def forjar_codigo(self, snap: Path) -> None:
        init = snap / "files" / "fundacao" / "__init__.py"
        init.write_text(init.read_text(encoding="utf-8") + "\nCODIGO_INJETADO = True  # fictício\n", encoding="utf-8")
        self.recalcular_manifesto(snap, "fundacao/__init__.py")

    def test_8_criar_devolve_a_ancora_e_a_anota_no_livro_fora_da_copia(self):
        snap = self.pasta("snap")
        res = backup.create_backup(self.root, snap, "a8")
        self.assertEqual(res["sha256_manifesto"], sha256_de(snap / "manifest.json"))
        livro = self.root / "state" / backup.LIVRO_COPIAS
        anotadas = [json.loads(linha)["sha256_manifesto"] for linha in livro.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(anotadas, [res["sha256_manifesto"]])
        self.assertEqual(list(snap.rglob(backup.LIVRO_COPIAS)), [], "o livro de cópias não pode ir para a cópia")
        self.assertNotIn("sha256_manifesto", json.loads((snap / "manifest.json").read_text(encoding="utf-8")))

    def test_8_codigo_trocado_com_manifesto_recalculado_nao_e_liberado(self):
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "a8-codigo")
        original = sha256_de(snap / "manifest.json")  # a âncora que o operador guardou fora da cópia
        self.forjar_codigo(snap)
        self.assertTrue(backup.verify_backup(snap)["ok"], "pré-condição: o manifesto vizinho confere com a cópia forjada")
        dest = self.pasta("dest")
        res = backup.restore(snap, dest, self.log)
        self.assertFalse(res["released"], "cópia com código trocado e manifesto recalculado foi liberada")
        self.assertIn("âncora", res["reason"])
        self.assertFalse(dest.exists(), "nada pode ser copiado para o destino")
        res = backup.restore(snap, dest, self.log, sha256_manifesto=original)
        self.assertFalse(res["released"])
        self.assertEqual(res["check"]["ancora"]["situacao"], "divergente")
        self.assertFalse(dest.exists())

    def test_8_banco_forjado_com_manifesto_recalculado_nao_e_liberado(self):
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "a8-banco")
        con = sqlite3.connect(str(snap / "state" / "state.sqlite"))
        con.execute("UPDATE acl SET resource = 'foundation', action = 'admin' WHERE subject = 'operador-engenharia'"
                    " AND resource = 'project:reversa-lab' AND action = 'read'")  # mesmas contagens
        con.commit()
        con.close()
        self.recalcular_manifesto(snap)
        self.assertTrue(backup.verify_backup(snap)["ok"], "pré-condição: o manifesto vizinho confere com o banco forjado")
        dest = self.pasta("dest")
        res = backup.restore(snap, dest, self.log)
        self.assertFalse(res["released"], "administração forjada na cópia foi liberada")
        self.assertFalse(dest.exists())

    def test_8_sem_livro_a_ancora_informada_confere_e_a_errada_recusa(self):
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "a8-desastre")
        ancora = sha256_de(snap / "manifest.json")
        registro = self.registro_guardado_sem_livro()
        errada = self.pasta("dest-errada")
        self.assertFalse(backup.restore(snap, errada, registro, sha256_manifesto="0" * 64)["released"])
        self.assertFalse(errada.exists())
        certa = self.pasta("dest-certa")
        res = backup.restore(snap, certa, registro, sha256_manifesto=" " + ancora.upper() + " ")
        self.assertTrue(res["released"], res)
        self.assertEqual(res["ancora"]["situacao"], "conferida")
        self.assertNotIn("aviso_ancora", res)
        self.assertEqual(self.eventos_de_fim(certa)[-1]["ancora"], "conferida")

    def test_8_sem_ancora_e_com_o_codigo_do_kit_libera_com_aviso_alto(self):
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "a8-sem-ancora")
        dest = self.pasta("dest")
        res = backup.restore(snap, dest, self.registro_guardado_sem_livro())
        self.assertTrue(res["released"], res)
        self.assertEqual(res["ancora"]["situacao"], "ausente")
        self.assertIn("--sha256-manifesto", res["aviso_ancora"])
        self.assertEqual(self.eventos_de_fim(dest)[-1]["ancora"], "ausente")

    def test_8_codigo_diferente_sem_ancora_exige_decisao_explicita(self):
        init = self.root / "fundacao" / "__init__.py"
        init.write_text(init.read_text(encoding="utf-8") + "\n# personalização local (fictícia)\n", encoding="utf-8")
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "a8-kit")
        ancora = sha256_de(snap / "manifest.json")
        registro = self.registro_guardado_sem_livro()
        dest = self.pasta("dest")
        res = backup.restore(snap, dest, registro)
        self.assertFalse(res["released"])
        self.assertEqual(res["codigo_diferente"], ["fundacao/__init__.py"])
        self.assertFalse(dest.exists())
        aceito = backup.restore(snap, dest, registro, aceitar_copia_sem_ancora=True)
        self.assertTrue(aceito["released"], aceito)
        self.assertIn("decisão explícita", aceito["ressalva_ancora"])
        self.assertIn("decisão explícita", self.eventos_de_fim(dest)[-1]["ressalva_ancora"])
        com_ancora = backup.restore(snap, self.pasta("dest-ancorado"), registro, sha256_manifesto=ancora)
        self.assertTrue(com_ancora["released"], com_ancora)


if __name__ == "__main__":
    unittest.main()
