"""Auditoria Codex Security da 1.7.6 (21/10/2026), #12 — o backup e a restauração conferiam caminhos e depois
reabriam os mesmos nomes para copiar e liberar.

Quem pudesse trocar, no intervalo, uma pasta da cópia, a pasta `files/`, o banco (`state/`) ou o destino por ligação
(junção no Windows, link simbólico no Linux) fazia a restauração ler e gravar fora, ou liberar bytes que ninguém
conferiu; no backup, um arquivo trocado depois da listagem levava conteúdo de fora da raiz. Agora a cópia é trazida
para um preparo privado ao lado do destino (pasta criada com exclusividade), cada arquivo é aberto sem seguir ligação
e conferido como o objeto listado, a verificação e a reaplicação usam só o preparo, os arquivos são conferidos de novo
contra o manifesto logo antes da promoção (renomeação atômica) e ligação no caminho (ou num ancestral) da cópia ou do
destino recusa. As trocas são feitas no ponto exato: depois da verificação, durante a leitura e antes da promoção.
Cada teste exige o comportamento seguro; na 1.7.6 os de ataque falham. Conteúdos fictícios.
"""

from __future__ import annotations

import gc
import json
import os
import shutil
import sqlite3
import stat
import unittest
from pathlib import Path
from unittest import mock

from apoio_auditoria import criar_ligacao_dir, trocar_pasta_por_ligacao
from helpers import FoundationTestCase

from fundacao.core import backup
from fundacao.core.contracts import ValidationError
from fundacao.core.db import connect

CANARIO = "CANARIO-FORA-DA-COPIA-FICTICIO"


def e_ligacao(p: Path) -> bool:
    try:
        st = os.lstat(p)
    except OSError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & 0x20000000)


class TestN12PreparoPrivado(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.extra = []
        self.log = self.root / "state" / "retiradas.jsonl"

    def tearDown(self):
        for p in reversed(self.extra):  # ligações primeiro, sem atravessar
            if e_ligacao(p):
                try:
                    os.unlink(p)
                except OSError:
                    os.rmdir(p)
            elif p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
        super().tearDown()

    def pasta(self, nome: str) -> Path:
        p = self.root.parent / f"{self.root.name}-{nome}"
        self.extra.append(p)
        return p

    def copia(self, rotulo: str) -> Path:
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, rotulo)
        return snap

    def fora_com_canario(self, nome: str, arquivo: str) -> Path:
        fora = self.pasta(nome)
        fora.mkdir()
        (fora / arquivo).write_text(f"conteúdo de fora da cópia: {CANARIO}\n", encoding="utf-8")
        return fora

    def tem_canario(self, raiz: Path) -> bool:
        """Algum arquivo sob `raiz` (sem atravessar ligação) traz o marcador de fora?"""
        if not raiz.is_dir() or e_ligacao(raiz):
            return False
        for pasta, subpastas, nomes in os.walk(raiz):
            subpastas[:] = [s for s in subpastas if not e_ligacao(Path(pasta) / s)]
            for nome in nomes:
                p = Path(pasta) / nome
                if not e_ligacao(p) and CANARIO.encode() in p.read_bytes():
                    return True
        return False

    def depois_da_verificacao(self, acao):
        """Executa `acao` logo depois da (primeira) verificação da restauração: o intervalo que o #12 explorava."""
        real, feito = backup.verify_backup, []

        def envolver(*args, **kwargs):
            resultado = real(*args, **kwargs)
            if not feito:
                feito.append(True)
                acao()
            return resultado
        return mock.patch.object(backup, "verify_backup", side_effect=envolver)

    def admin_no_restaurado(self, raiz: Path, quem: str) -> bool:
        con = connect(raiz / "state" / "state.sqlite")
        try:
            return con.execute("SELECT 1 FROM acl WHERE subject = ? AND resource = 'foundation' AND action = 'admin'",
                               (quem,)).fetchone() is not None
        finally:
            con.close()

    def test_12_pasta_da_copia_trocada_depois_da_verificacao_nao_traz_nada_de_fora(self):
        snap = self.copia("a12-pasta")
        original = (snap / "files" / "projects" / "juridico-lab" / "INSTRUCOES.md").read_bytes()
        fora = self.fora_com_canario("fora", "INSTRUCOES.md")
        dest = self.pasta("dest")
        with self.depois_da_verificacao(
                lambda: trocar_pasta_por_ligacao(snap / "files" / "projects" / "juridico-lab", fora)):
            res = backup.restore(snap, dest, self.log)
        self.assertFalse(self.tem_canario(dest), "a restauração trouxe conteúdo de fora da cópia")
        self.assertTrue(res["released"], res)  # o que vale é o que foi conferido, já trazido para o preparo
        self.assertEqual((dest / "projects" / "juridico-lab" / "INSTRUCOES.md").read_bytes(), original)

    def test_12_fonte_alterada_depois_da_verificacao_nao_chega_ao_destino(self):
        snap = self.copia("a12-fonte")
        alvo = snap / "files" / "projects" / "juridico-lab" / "INSTRUCOES.md"
        original = alvo.read_bytes()
        dest = self.pasta("dest")
        alterado = original + "\nalterado na cópia depois da verificação (fictício)\n".encode("utf-8")
        with self.depois_da_verificacao(lambda: alvo.write_bytes(alterado)):
            res = backup.restore(snap, dest, self.log)
        self.assertTrue(res["released"], res)
        self.assertEqual((dest / "projects" / "juridico-lab" / "INSTRUCOES.md").read_bytes(), original,
                         "a restauração liberou bytes que ninguém conferiu")

    def test_12_raiz_files_trocada_depois_da_verificacao_nao_traz_codigo_de_fora(self):
        snap = self.copia("a12-files")
        fora = self.pasta("fora-files")
        shutil.copytree(snap / "files", fora)
        (fora / "fundacao" / "injetado.py").write_text(f"# {CANARIO}\n", encoding="utf-8")
        dest = self.pasta("dest")
        with self.depois_da_verificacao(lambda: trocar_pasta_por_ligacao(snap / "files", fora)):
            res = backup.restore(snap, dest, self.log)
        self.assertFalse((dest / "fundacao" / "injetado.py").exists(), "código de fora da cópia foi restaurado")
        self.assertFalse(self.tem_canario(dest))
        self.assertTrue(res["released"], res)

    def test_12_banco_trocado_depois_da_verificacao_nao_e_restaurado(self):
        snap = self.copia("a12-banco")
        fora = self.pasta("fora-state")
        fora.mkdir()
        shutil.copy2(snap / "state" / "state.sqlite", fora / "state.sqlite")
        con = sqlite3.connect(str(fora / "state.sqlite"))
        con.execute("INSERT INTO acl VALUES ('operador-juridico', 'foundation', 'admin', 'forjado', '2026-10-21')")
        con.commit()
        con.close()
        gc.collect()
        dest = self.pasta("dest")
        with self.depois_da_verificacao(lambda: trocar_pasta_por_ligacao(snap / "state", fora)):
            res = backup.restore(snap, dest, self.log)
        if dest.exists():
            self.assertFalse(self.admin_no_restaurado(dest, "operador-juridico"), "o banco de fora foi restaurado")
        self.assertTrue(res["released"], res)

    def test_12_destino_trocado_por_ligacao_nao_recebe_nada(self):
        snap = self.copia("a12-destino")
        fora = self.pasta("fora-destino")
        fora.mkdir()
        dest = self.pasta("dest")
        with self.depois_da_verificacao(lambda: criar_ligacao_dir(dest, fora)):
            res = backup.restore(snap, dest, self.log)
        self.assertEqual(list(fora.iterdir()), [], "a restauração gravou através da ligação no destino")
        self.assertFalse(res["released"], res)
        self.assertEqual(list(dest.parent.glob(f".{dest.name}.preparo-*")), [], "o preparo não liberado ficou")

    def test_12_preparo_alterado_antes_da_promocao_nao_e_liberado(self):
        snap = self.copia("a12-promocao")
        real = backup.logical_summary

        def alterar(db_path, *args, **kwargs):
            pasta = Path(db_path).parent
            if (pasta / backup.MARCA_NAO_LIBERADA).exists():  # a raiz que está sendo montada
                alvo = pasta.parent / "projects" / "juridico-lab" / "INSTRUCOES.md"
                alvo.write_text(alvo.read_text(encoding="utf-8") + "\nalterado depois da conferência (fictício)\n",
                                encoding="utf-8")
            return real(db_path, *args, **kwargs)
        dest = self.pasta("dest")
        with mock.patch.object(backup, "logical_summary", side_effect=alterar):
            res = backup.restore(snap, dest, self.log)
        self.assertFalse(res["released"], "arquivo alterado depois da conferência foi liberado")
        self.assertFalse(dest.exists(), "o destino só recebe a raiz liberada")
        self.assertIn("projects/juridico-lab/INSTRUCOES.md", res["reason"])
        self.assertEqual(list(dest.parent.glob(f".{dest.name}.preparo-*")), [], "o preparo não liberado ficou")

    def test_12_troca_durante_a_leitura_da_copia_recusa_sem_ler_de_fora(self):
        from fundacao.core import preparo  # na 1.7.6 não existe: a cópia era lida no lugar, pelo nome
        snap = self.copia("a12-leitura")
        fora = self.fora_com_canario("fora", "INSTRUCOES.md")
        real, trocado = preparo.copiar, []

        def copiar(origem, destino, listado):
            if not trocado and Path(origem).name == "INSTRUCOES.md" and "juridico-lab" in Path(origem).parts:
                trocar_pasta_por_ligacao(snap / "files" / "projects" / "juridico-lab", fora)
                trocado.append(True)
            return real(origem, destino, listado)
        dest = self.pasta("dest")
        with mock.patch.object(preparo, "copiar", side_effect=copiar):
            res = backup.restore(snap, dest, self.log)
        self.assertTrue(trocado)
        self.assertFalse(res["released"], res)
        self.assertIn("trocad", res["reason"])
        self.assertFalse(dest.exists())
        self.assertEqual(list(dest.parent.glob(f".{dest.name}.preparo-*")), [])

    def test_12_backup_nao_copia_arquivo_trocado_por_ligacao_depois_da_listagem(self):
        alvo = self.write_data("juridico-lab", "alvo12/segredo-alvo.md", "conteúdo legítimo (fictício)")
        fora = self.fora_com_canario("fora-backup", "segredo-alvo.md")
        real, trocado = backup._files, []

        def envolver(root, ligacoes=None, extras=()):
            for item in real(root, ligacoes, extras):
                caminho = item[0] if isinstance(item, tuple) else item
                if not trocado and caminho.name == alvo.name:
                    trocar_pasta_por_ligacao(caminho.parent, fora)
                    trocado.append(True)
                yield item
        snap = self.pasta("snap")
        with mock.patch.object(backup, "_files", side_effect=envolver):
            res = backup.create_backup(self.root, snap, "a12-backup")
        self.assertTrue(trocado)
        self.assertFalse(self.tem_canario(snap), "o backup copiou conteúdo de fora da raiz")
        self.assertIn("projects/juridico-lab/data/alvo12/segredo-alvo.md", res.get("ligacoes_nao_seguidas", []))

    def test_12_destino_do_backup_trocado_por_ligacao_nao_recebe_nada(self):
        fora = self.pasta("fora-backup-destino")
        fora.mkdir()
        snap = self.pasta("snap")
        real = backup.registros_incluidos

        def plantar(root):  # entre a conferência do destino e a criação dele
            criar_ligacao_dir(snap, fora)
            return real(root)
        with mock.patch.object(backup, "registros_incluidos", side_effect=plantar):
            with self.assertRaises(FileExistsError):  # a promoção não grava através da ligação
                backup.create_backup(self.root, snap, "a12-destino-backup")
        self.assertEqual(list(fora.iterdir()), [], "o backup gravou através da ligação no destino")
        self.assertEqual(list(snap.parent.glob(f".{snap.name}.preparo-*")), [], "o preparo da cópia ficou")

    def test_12_ligacao_num_ancestral_da_copia_ou_do_destino_recusa(self):
        pai = self.pasta("pai-real")
        pai.mkdir()
        via = self.pasta("pai-ligado")
        criar_ligacao_dir(via, pai)
        snap = pai / "snap"
        backup.create_backup(self.root, snap, "a12-ancestral")
        res = backup.restore(snap, via / "dest", self.log)
        self.assertFalse(res["released"], "restaurou através de um ancestral que é ligação")
        self.assertIn("ligação", res["reason"])
        self.assertFalse((pai / "dest").exists())
        dest = self.pasta("dest")
        res = backup.restore(via / "snap", dest, self.log)
        self.assertFalse(res["released"])
        self.assertFalse(dest.exists())
        with self.assertRaises(ValidationError):
            backup.create_backup(self.root, via / "snap2", "a12-ancestral-2")
        self.assertFalse((pai / "snap2").exists())

    def test_12_caminho_do_manifesto_fora_da_copia_e_estrutura_invalida(self):
        snap = self.copia("a12-manifesto")
        mf = snap / "manifest.json"
        m = json.loads(mf.read_text(encoding="utf-8"))
        for ruim in ("../fora.txt", "/etc/passwd", "projects/../../x", "state/state.sqlite", ""):
            with self.subTest(caminho=ruim):
                m2 = {**m, "files": [*m["files"], {"path": ruim, "sha256": "0" * 64, "size": 0}]}
                mf.write_text(json.dumps(m2, ensure_ascii=False), encoding="utf-8")
                with self.assertRaises(ValidationError):
                    backup.verify_backup(snap)


if __name__ == "__main__":
    unittest.main()
