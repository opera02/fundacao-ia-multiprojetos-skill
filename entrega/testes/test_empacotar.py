"""Auditoria externa da 1.3.4 — `empacotar.py` (F18): a distribuição anterior só sai depois da nova validada.

`dist` descartável com pacotes FICTÍCIOS; o empacotador do skill-creator é substituído por um dublê
(subprocesso simulado) — nada é empacotado de verdade e a entrega real não é tocada.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ENTREGA = Path(__file__).resolve().parents[1]
NOME = "fundacao-ia-multiprojetos"


def carregar_modulo():
    spec = importlib.util.spec_from_file_location("empacotar_em_teste", ENTREGA / "empacotar.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestF18Empacotamento(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="empacotar-teste-"))
        self.dist = self.base / "dist"
        self.dist.mkdir()
        (self.dist / f"{NOME}.skill").write_bytes(b"PACOTE-ANTERIOR-FICTICIO")
        (self.dist / f"{NOME}-completo.zip").write_bytes(b"COMPLETO-ANTERIOR-FICTICIO")
        (self.dist / "SHA256SUMS.txt").write_text("HASHES-ANTERIORES-FICTICIOS\n", encoding="utf-8")
        self.antes = {p.name: p.read_bytes() for p in self.dist.iterdir()}
        self.skill = self.base / "fonte" / NOME
        (self.skill / "evals").mkdir(parents=True)
        (self.skill / "SKILL.md").write_text("---\nname: fundacao-ia-multiprojetos\nmetadata:\n  version: \"9.9.9\"\n---\n",
                                             encoding="utf-8")
        (self.skill / "evals" / "evals.json").write_text("{}", encoding="utf-8")
        self.creator = self.base / "skill-creator"
        (self.creator / "scripts").mkdir(parents=True)
        (self.creator / "scripts" / "package_skill.py").write_text("# dublê fictício\n", encoding="utf-8")
        self.mod = carregar_modulo()
        self.mod.DIST, self.mod.SKILL = self.dist, self.skill
        # Desde a 1.7.7 o empacotador só roda a ferramenta registrada (Codex Security da 1.7.6, #6): o dublê é
        # registrado aqui, para estes testes chegarem ao passo que nomeiam (a recusa da divergente está em
        # test_auditoria_1_7_7_pacote.py).
        self.mod.FERRAMENTA_ESPERADA = {"scripts/package_skill.py": hashlib.sha256(
            (self.creator / "scripts" / "package_skill.py").read_bytes()).hexdigest()}

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def rodar(self, efeito):
        saida = io.StringIO()
        with mock.patch.object(self.mod.subprocess, "run", side_effect=efeito), \
                mock.patch.object(sys, "argv", ["empacotar.py", "--skill-creator", str(self.creator)]), \
                contextlib.redirect_stdout(saida), contextlib.redirect_stderr(saida):
            try:
                return self.mod.main()
            except BaseException as exc:  # noqa: BLE001 — qualquer queda conta como falha do empacotamento
                return f"excecao:{type(exc).__name__}"

    def preservada(self):
        for nome, dados in self.antes.items():
            self.assertTrue((self.dist / nome).is_file(), f"{nome} foi apagado antes de a nova versão valer")
            self.assertEqual((self.dist / nome).read_bytes(), dados, f"{nome} mudou numa falha")

    @staticmethod
    def falha(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, "", "FALHA FICTICIA DO EMPACOTADOR")

    @staticmethod
    def gerar_pacote(conteudo: dict[str, str]):
        def efeito(cmd, **kw):
            destino = Path(cmd[-1])
            with zipfile.ZipFile(destino / f"{NOME}.skill", "w") as z:
                for nome, texto in conteudo.items():
                    z.writestr(nome, texto)
            return subprocess.CompletedProcess(cmd, 0, "pacote fictício gerado", "")
        return efeito

    @staticmethod
    def gerar_da_arvore(cmd, **kw):
        """Dublê fiel do package_skill: o .skill com os arquivos da árvore (cmd[-2]), sem evals/ na raiz. Desde a 1.7.7
        o pacote gerado tem de ser exatamente a árvore (#6); o pacote avulso de `gerar_pacote` seria recusado antes da
        promoção, e os testes da promoção deixariam de exercitá-la."""
        skill, destino = Path(cmd[-2]), Path(cmd[-1])
        with zipfile.ZipFile(destino / f"{NOME}.skill", "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(skill.rglob("*")):
                rel = p.relative_to(skill.parent)
                if p.is_file() and rel.parts[1] != "evals":
                    z.write(p, rel.as_posix())
        return subprocess.CompletedProcess(cmd, 0, "pacote fictício gerado", "")

    def test_f18_falha_do_empacotador_preserva_a_distribuicao_anterior(self):
        self.assertNotEqual(self.rodar(self.falha), 0)
        self.preservada()

    def test_f18_modulo_do_skill_creator_ausente_preserva(self):
        (self.creator / "scripts" / "package_skill.py").unlink()
        self.assertNotEqual(self.rodar(self.falha), 0)
        self.preservada()

    def test_f18_geracao_parcial_preserva(self):
        self.assertNotEqual(self.rodar(lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", "")), 0)
        self.preservada()

    def test_f18_pacote_sem_skill_md_na_raiz_e_recusado(self):
        self.assertNotEqual(self.rodar(self.gerar_pacote({f"{NOME}/references/x.md": "x"})), 0)
        self.preservada()

    def test_f18_falha_durante_a_promocao_devolve_o_conjunto_anterior(self):
        """Complementar (caminho novo da 1.4.0): o desfazer da promoção."""
        original, movidos = shutil.move, []

        def move_que_falha(de, para):
            movidos.append(para)
            if len(movidos) == 5:  # já arquivou os 3 anteriores e promoveu 1 novo
                raise OSError("falha fictícia na promoção")
            return original(de, para)

        with mock.patch.object(self.mod.shutil, "move", side_effect=move_que_falha):
            rc = self.rodar(self.gerar_da_arvore)
        self.assertEqual(rc, 1)
        self.preservada()
        self.assertFalse(any(p.name.startswith(".preparo-") for p in self.dist.iterdir()))

    def test_f18_sucesso_promove_conjunto_coerente_e_arquiva_o_anterior(self):
        rc = self.rodar(self.gerar_da_arvore)
        self.assertEqual(rc, 0)
        somas = {}
        for linha in (self.dist / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
            h, nome = linha.split()
            somas[nome] = h
        for nome in (f"{NOME}.skill", f"{NOME}-completo.zip"):
            self.assertEqual(hashlib.sha256((self.dist / nome).read_bytes()).hexdigest(), somas[nome], nome)
        arquivados = {p.name: p.read_bytes() for p in (self.dist / "anteriores").rglob("*") if p.is_file()}
        for nome, dados in self.antes.items():
            self.assertEqual(arquivados.get(nome), dados, f"{nome} anterior não foi arquivado")


if __name__ == "__main__":
    unittest.main()
