"""Auditoria externa sobre a 1.4.1 — `instalar_kit.py`, A03: retorno que falha não pode sair como desfeito.

Na 1.4.5, uma falha na promoção seguida de falha no retorno (cópia de volta do backup) saía com `desfeito: true`,
`composicao: "nao_alterada"` e sem o caminho do backup — que guardava a única cópia da versão anterior. E duas
execuções no mesmo segundo usavam a mesma pasta de backup: a segunda sobrescrevia a cópia guardada pela primeira.

Pastas descartáveis e kit FICTÍCIO de dois arquivos (o módulo é carregado com `KIT` apontando para ele); falhas
injetadas com `mock`. Falham na 1.4.5 (menos o controle) e passam na 1.5.0.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import SCRIPTS


def carregar():
    spec = importlib.util.spec_from_file_location("instalar_kit_a03", SCRIPTS / "instalar_kit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _KitFicticio(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory(prefix="instalar-kit-a03-")
        self.addCleanup(pasta.cleanup)
        base = Path(pasta.name).resolve()
        self.mod = carregar()
        self.mod.KIT = base / "kit"
        self.dest = base / "destino"
        for raiz, conteudo in ((self.mod.KIT, "KIT-NOVO"), (self.dest, "ORIGINAL-DO-USUARIO")):
            (raiz / "fundacao").mkdir(parents=True)
            for nome in ("a.py", "b.py"):
                (raiz / "fundacao" / nome).write_text(conteudo, encoding="utf-8")

    def instalar(self, *extra) -> tuple[int, dict]:
        saida = io.StringIO()
        with mock.patch.object(sys, "argv", ["instalar_kit.py", "--destino", str(self.dest), *extra]), \
                contextlib.redirect_stdout(saida):
            codigo = self.mod.main()
        return codigo, json.loads(saida.getvalue())

    def lido(self, caminho: Path) -> str:
        return caminho.read_text(encoding="utf-8")

    def falhas(self, retorno_falha: bool):
        """Promoção de b.py falha; com `retorno_falha`, a cópia de volta de a.py (do backup) também."""
        replace, copy2 = self.mod.os.replace, self.mod.shutil.copy2

        def promocao(src, dst):
            if Path(dst) == self.dest / "fundacao" / "b.py":
                raise OSError("falha simulada na promoção de b.py")
            return replace(src, dst)

        def copia(src, dst, *a, **k):
            if retorno_falha and "kit_backup" in Path(src).parts and Path(dst) == self.dest / "fundacao" / "a.py":
                raise OSError("falha simulada no retorno de a.py")
            return copy2(src, dst, *a, **k)

        pilha = contextlib.ExitStack()
        pilha.enter_context(mock.patch.object(self.mod.os, "replace", side_effect=promocao))
        pilha.enter_context(mock.patch.object(self.mod.shutil, "copy2", side_effect=copia))
        return pilha


class TestA03RetornoQueFalha(_KitFicticio):
    def test_a03_retorno_que_falha_nao_e_declarado_desfeito(self):
        with self.falhas(retorno_falha=True):
            codigo, dados = self.instalar("--atualizar")
        self.assertEqual(codigo, 5)
        self.assertEqual(self.lido(self.dest / "fundacao" / "a.py"), "KIT-NOVO", "falha do retorno não reproduzida")
        self.assertIs(dados.get("desfeito"), False, "retorno que falhou declarado como desfeito")
        self.assertNotEqual(dados.get("composicao"), "nao_alterada")
        self.assertIn("fundacao/a.py", " ".join(dados.get("erros", [])), dados)
        backup = Path(dados.get("backup_dos_substituidos") or self.dest / "sem-backup-informado")
        self.assertEqual(self.lido(backup / "fundacao" / "a.py"), "ORIGINAL-DO-USUARIO", dados)
        registro = json.loads(self.lido(self.dest / "registry" / "kit_install.json"))
        self.assertEqual(registro[-1].get("composicao"), "indeterminada", "estado indeterminado fora do registro")

    def test_a03_controle_retorno_completo_segue_desfeito(self):
        """Controle (passa na 1.4.5 e na 1.5.0)."""
        with self.falhas(retorno_falha=False):
            codigo, dados = self.instalar("--atualizar")
        self.assertEqual(codigo, 5)
        self.assertIs(dados.get("desfeito"), True)
        self.assertEqual(dados.get("composicao"), "nao_alterada")
        self.assertEqual(self.lido(self.dest / "fundacao" / "a.py"), "ORIGINAL-DO-USUARIO")

    def test_a03_execucoes_no_mesmo_segundo_nao_dividem_o_backup(self):
        class Relogio(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return dt.datetime(2026, 10, 20, 12, 0, 0, tzinfo=tz)

        with mock.patch.object(self.mod, "datetime", Relogio):
            _, primeira = self.instalar("--atualizar")
            for nome in ("a.py", "b.py"):
                (self.dest / "fundacao" / nome).write_text("SEGUNDA-PERSONALIZACAO", encoding="utf-8")
            _, segunda = self.instalar("--atualizar")
        self.assertNotEqual(primeira["backup_dos_substituidos"], segunda["backup_dos_substituidos"])
        guardado = Path(primeira["backup_dos_substituidos"]) / "fundacao" / "a.py"
        self.assertEqual(self.lido(guardado), "ORIGINAL-DO-USUARIO", "a 2ª execução sobrescreveu o backup da 1ª")


if __name__ == "__main__":
    unittest.main()
