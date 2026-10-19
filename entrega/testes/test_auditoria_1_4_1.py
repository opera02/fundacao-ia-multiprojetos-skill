"""Auditoria sobre a 1.4.1 — `instalar_skill.py`: SEC-02 (integridade do pacote conferida antes de extrair),
OPS-01 (instalação e atualização atômicas, com retorno) e o controle do SEC-01 (nomes que tentam sair da
pasta, com os exemplos do relatório).

Perfil DESCARTÁVEL, como nos demais testes do instalador. Os testes de SEC-02 e OPS-01 falham na 1.4.1; o
controle do SEC-01 passa nas duas versões. Verificação: `auditoria/VERIFICACAO-AUDITORIA-1.4.1.md`.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from test_relatorio_tecnico_1_4_0 import NOME, _PerfilDescartavel

# Prelúdio do processo filho: a PRIMEIRA cópia de árvore (a da versão nova) termina incompleta e falha.
FALHA_NA_PRIMEIRA_COPIA = """
import pathlib, shutil
_copiar = shutil.copytree
_feitas = []
def _copia_que_falha(src, dst, *a, **k):
    _feitas.append(dst)
    if len(_feitas) == 1:
        _copiar(src, dst, *a, **k)
        for p in pathlib.Path(dst).rglob('nota.md'):
            p.unlink()
        raise OSError(28, 'falha simulada no meio da cópia (disco cheio)')
    return _copiar(src, dst, *a, **k)
shutil.copytree = _copia_que_falha
"""

PAYLOADS_DO_RELATORIO = ["../../../../root/.bashrc", "../../../../etc/cron.hourly/malicious_job.sh",
                         "../../../../home/user/.ssh/authorized_keys"]


def skill_md(descricao: str) -> str:
    return f"---\nname: {NOME}\ndescription: {descricao}\n---\n"


class _Base(_PerfilDescartavel):
    def nova_origem(self, rotulo: str, descricao: str, binario: bool = False) -> Path:
        o = self.base / f"origem-{rotulo}" / NOME
        (o / "references").mkdir(parents=True)
        (o / "SKILL.md").write_text(skill_md(descricao), encoding="utf-8")
        (o / "references" / "nota.md").write_text(f"nota {descricao}", encoding="utf-8")
        if binario:  # dados comprimidos de verdade, para a corrupção cair no meio deles
            (o / "references" / "dados.bin").write_bytes(os.urandom(48 * 1024))
        return o

    def empacotar(self, origem: Path, destino: Path, extra: dict[str, str] | None = None) -> Path:
        destino.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(origem.rglob("*")):
                if p.is_file():
                    z.write(p, f"{NOME}/{p.relative_to(origem).as_posix()}")
            for nome, conteudo in (extra or {}).items():
                z.writestr(nome, conteudo)
        return destino

    def descricao_instalada(self) -> str | None:
        p = self.copia / "SKILL.md"
        if not p.exists():
            return None
        return p.read_text(encoding="utf-8").split("description: ", 1)[1].split("\n", 1)[0]


class TestSEC02IntegridadeAntesDeExtrair(_Base):
    """Na 1.4.1 o instalador não olhava o SHA256SUMS.txt ao lado do pacote nem aceitava um hash informado."""

    def pacote_com_manifesto(self, alterado: bool) -> Path:
        pasta = self.base / "download"
        pacote = self.empacotar(self.origem, pasta / f"{NOME}.skill")
        (pasta / "SHA256SUMS.txt").write_text(f"{hashlib.sha256(pacote.read_bytes()).hexdigest()}  {NOME}.skill\n",
                                              encoding="utf-8")
        if alterado:  # zip válido, com um arquivo a mais, depois de o manifesto ser gerado
            self.empacotar(self.origem, pacote, {f"{NOME}/scripts/acrescentado.py": "print('terceiro')\n"})
        return pacote

    def test_sec02_pacote_que_diverge_do_SHA256SUMS_ao_lado_e_recusado(self):
        p, saida = self.rodar("instalar", "--origem", self.pacote_com_manifesto(alterado=True))
        self.assertFalse(self.copia.exists(), "instalou um pacote que diverge do SHA256SUMS.txt ao lado dele")
        self.assertFalse(os.path.lexists(self.link))
        self.assertNotEqual(p.returncode, 0)
        self.assertIsNotNone(saida, f"saída não é JSON: {p.stdout[-300:]} {p.stderr[-300:]}")
        self.assertIs((saida.get("integridade_do_pacote") or {}).get("ok"), False, saida)

    def test_sec02_pacote_que_confere_e_instalado_e_a_conferencia_relatada(self):
        p, saida = self.rodar("instalar", "--origem", self.pacote_com_manifesto(alterado=False))
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])
        integridade = (saida or {}).get("integridade_do_pacote") or {}
        self.assertIs(integridade.get("ok"), True, saida)
        self.assertIn("SHA256SUMS.txt", integridade.get("conferido_com", []))

    def test_sec02_hash_informado_que_nao_confere_e_recusado(self):
        pacote = self.empacotar(self.origem, self.base / "avulso" / f"{NOME}.skill")
        p, saida = self.rodar("instalar", "--origem", pacote, "--sha256", "0" * 64)
        self.assertFalse(self.copia.exists())
        self.assertNotEqual(p.returncode, 0)
        self.assertIsNotNone(saida, f"saída não é JSON: {p.stdout[-300:]} {p.stderr[-300:]}")
        self.assertIs((saida.get("integridade_do_pacote") or {}).get("ok"), False, saida)

    def test_sec02_pacote_corrompido_vira_erro_em_json_sem_instalar(self):
        pacote = self.empacotar(self.nova_origem("bin", "com-binario", binario=True),
                                self.base / "avulso" / f"{NOME}.skill")
        dados = bytearray(pacote.read_bytes())
        meio = len(dados) // 2
        dados[meio:meio + 64] = bytes(64)
        pacote.write_bytes(bytes(dados))
        p, saida = self.rodar("instalar", "--origem", pacote)
        self.assertFalse(self.copia.exists())
        self.assertNotEqual(p.returncode, 0)
        self.assertIsNotNone(saida, f"saída não é JSON: {p.stderr[-300:]}")
        self.assertIn("erro", saida)
        self.assertNotIn("Traceback", p.stderr)


class TestOPS01InstalacaoAtomica(_Base):
    """Na 1.4.1 uma falha no meio da cópia deixava uma cópia parcial no lugar da instalação."""

    def test_ops01_falha_na_atualizacao_mantem_a_versao_anterior_inteira(self):
        v1, v2 = self.nova_origem("v1", "versao-1"), self.nova_origem("v2", "versao-2")
        p, _ = self.rodar("instalar", "--origem", v1)
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])
        p, saida = self.rodar("atualizar", "--origem", v2, preludio=FALHA_NA_PRIMEIRA_COPIA)
        self.assertEqual(self.descricao_instalada(), "versao-1", "a versão anterior não ficou no lugar")
        self.assertTrue((self.copia / "references" / "nota.md").exists(), "a cópia instalada ficou incompleta")
        self.assertTrue((self.link / "SKILL.md").exists(), "a ligação deixou de levar à skill")
        self.assertNotEqual(p.returncode, 0)
        self.assertIsNotNone(saida, f"saída não é JSON: {p.stderr[-300:]}")
        self.assertIn("erro", saida)

    def test_ops01_falha_na_instalacao_nao_deixa_copia_parcial(self):
        p, saida = self.rodar("instalar", "--origem", self.origem, preludio=FALHA_NA_PRIMEIRA_COPIA)
        self.assertFalse(self.copia.exists(), "ficou uma cópia parcial em ~/.agents/skills")
        self.assertFalse(os.path.lexists(self.link))
        self.assertNotEqual(p.returncode, 0)
        self.assertIsNotNone(saida, f"saída não é JSON: {p.stderr[-300:]}")
        self.assertIn("erro", saida)

    def test_ops01_ligacao_em_conflito_e_recusada_antes_de_copiar(self):
        self.link.mkdir(parents=True)
        (self.link / "SKILL.md").write_text(skill_md("pasta-que-ja-estava-la"), encoding="utf-8")
        p, saida = self.rodar("instalar", "--origem", self.origem)
        self.assertFalse(self.copia.exists(), "copiou a skill antes de recusar a ligação em conflito")
        self.assertNotEqual(p.returncode, 0)
        self.assertIsNotNone(saida, f"saída não é JSON: {p.stderr[-300:]}")
        self.assertIn("erro", saida)
        self.assertIn("pasta-que-ja-estava-la", (self.link / "SKILL.md").read_text(encoding="utf-8"))


class TestSEC01ControleNomesQueTentamSair(_Base):
    """Controle (passa na 1.4.1 e na 1.4.2): o `zipfile` já saneia os nomes; nada é escrito fora."""

    def test_sec01_nomes_do_relatorio_nao_escrevem_fora_da_area(self):
        ingenuos = [(Path(tempfile.gettempdir()) / "x" / n).resolve() for n in PAYLOADS_DO_RELATORIO]
        antes = [p.exists() for p in ingenuos]
        pacote = self.empacotar(self.origem, self.base / "pacote" / f"{NOME}.skill",
                                {n: "conteúdo fictício" for n in PAYLOADS_DO_RELATORIO})
        p, saida = self.rodar("instalar", "--origem", pacote)
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])
        self.assertEqual([p.exists() for p in ingenuos], antes, "algum nome escapou da pasta de extração")
        nomes = {q.name for q in self.perfil.rglob("*") if q.is_file()}
        self.assertFalse(nomes & {".bashrc", "malicious_job.sh", "authorized_keys"}, nomes)
        self.assertEqual(sorted(q.relative_to(self.copia).as_posix() for q in self.copia.rglob("*") if q.is_file()),
                         ["SKILL.md", "references/nota.md"])


if __name__ == "__main__":
    unittest.main()
