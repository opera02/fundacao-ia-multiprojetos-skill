"""Hook `assets/hooks/guarda_caminho.py` — ligações e junções (revisão de segurança da 1.4.5, #13).

Até a 1.4.5 o hook resolvia `projects/<projeto>` e aceitava o destino que caísse dentro dele: com a
pasta do projeto (ou `projects/`) trocada por junção ou link, a "raiz permitida" passava a ser o alvo
da ligação e a escrita fora da fundação era liberada; `FUNDACAO_PROJECT` com `..` ou separador
ampliava a raiz; ligação dentro do projeto (vetor de troca entre a checagem e a abertura) passava.
Esses testes falham na 1.4.5 e passam depois. Controles: escrita comum no projeto e raiz da fundação
acessada por junção definida pelo lançador seguem sem decisão.

Eventos PreToolUse fictícios pela entrada padrão; pastas descartáveis; junção no Windows (`mklink /J`).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import ENV, SKILL, criar_ligacao_dir

HOOK = SKILL / "assets" / "hooks" / "guarda_caminho.py"


def decisao(evento: dict, **variaveis: str) -> str:
    """`deny`, `sem_decisao` ou o erro do processo."""
    env = {k: v for k, v in ENV.items() if not k.startswith("FUNDACAO_")}
    env.update(variaveis)
    p = subprocess.run([sys.executable, "-B", str(HOOK)], input=json.dumps(evento), capture_output=True,
                       text=True, encoding="utf-8", env=env, timeout=60)
    if p.returncode != 0:
        return f"codigo={p.returncode}: {p.stderr[-200:]}"
    if not p.stdout.strip():
        return "sem_decisao"
    return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"]


def escrever(alvo: Path | str, ferramenta: str = "Write", cwd: Path | None = None) -> dict:
    chave = "notebook_path" if ferramenta == "NotebookEdit" else "file_path"
    evento = {"tool_name": ferramenta, "tool_input": {chave: str(alvo)}}
    if cwd is not None:
        evento["cwd"] = str(cwd)
    return evento


class _Base(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="hook-caminho-teste-"))
        self.raiz = self.base / "fund"
        self.jur = self.raiz / "projects" / "juridico-lab"
        self.rev = self.raiz / "projects" / "reversa-lab"
        self.fora = self.base / "fora"
        for pasta in (self.jur, self.rev, self.fora):
            pasta.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def decide(self, evento: dict, projeto: str = "juridico-lab", raiz: Path | None = None) -> str:
        return decisao(evento, FUNDACAO_PROJECT=projeto, FUNDACAO_RAIZ=str(raiz or self.raiz))


class TestPastaDoProjetoRedirecionada(_Base):
    """A raiz permitida não pode ser ligação: o alvo da ligação não vira 'o projeto'."""

    def test_pasta_do_projeto_ligada_para_fora_da_fundacao_e_negada(self):
        self.jur.rmdir()
        criar_ligacao_dir(self.jur, self.fora)
        self.assertEqual(self.decide(escrever(self.jur / "x.md")), "deny")
        self.assertEqual(self.decide(escrever(self.fora / "x.md")), "deny")

    def test_pasta_do_projeto_ligada_para_outro_projeto_e_negada(self):
        self.jur.rmdir()
        criar_ligacao_dir(self.jur, self.rev)
        self.assertEqual(self.decide(escrever(self.jur / "x.md")), "deny")
        self.assertEqual(self.decide(escrever(self.rev / "x.md", "Edit")), "deny")

    def test_pasta_projects_ligada_para_outro_lugar_e_negada(self):
        outra = self.base / "outra" / "projects"
        (outra / "juridico-lab").mkdir(parents=True)
        shutil.rmtree(self.raiz / "projects")
        criar_ligacao_dir(self.raiz / "projects", outra)
        self.assertEqual(self.decide(escrever(self.raiz / "projects" / "juridico-lab" / "x.md")), "deny")
        self.assertEqual(self.decide(escrever(outra / "juridico-lab" / "x.md")), "deny")

    def test_projeto_que_nao_e_filho_exato_de_projects_e_negado(self):
        for projeto, alvo in ((".", self.raiz / "projects" / "x.md"),
                              ("..", self.raiz / "state" / "state.sqlite"),
                              ("juridico-lab/../reversa-lab", self.rev / "x.md"),
                              (r"juridico-lab\..\reversa-lab", self.rev / "x.md")):
            with self.subTest(projeto=projeto):
                self.assertEqual(self.decide(escrever(alvo), projeto=projeto), "deny")


class TestLigacaoNoCaminhoDoDestino(_Base):
    """Ligação abaixo da raiz é vetor de troca entre a checagem e a abertura: negada mesmo apontando para dentro."""

    def test_ligacao_dentro_do_projeto_para_o_proprio_projeto_e_negada(self):
        real = self.jur / "real"
        real.mkdir()
        criar_ligacao_dir(self.jur / "saida", real)
        self.assertEqual(self.decide(escrever(self.jur / "saida" / "x.md")), "deny")
        self.assertEqual(self.decide(escrever(self.jur / "saida" / "n.ipynb", "NotebookEdit")), "deny")

    def test_atalho_externo_para_o_projeto_e_negado(self):
        atalho = self.base / "atalho"
        criar_ligacao_dir(atalho, self.jur)
        self.assertEqual(self.decide(escrever(atalho / "x.md")), "deny")

    def test_controle_ligacao_para_outro_projeto_ja_era_negada(self):
        criar_ligacao_dir(self.jur / "data", self.rev)
        self.assertEqual(self.decide(escrever(self.jur / "data" / "x.md")), "deny")


class TestControlesSeguemLiberados(_Base):
    """Passam na 1.4.5 e depois: o endurecimento não bloqueia o uso legítimo."""

    def test_escrita_comum_no_projeto_segue(self):
        existente = self.jur / "minuta.md"
        existente.write_text("ficticio\n", encoding="utf-8")
        for evento in (escrever(self.jur / "nova" / "x.md"), escrever(existente, "Edit"),
                       escrever("rel.md", cwd=self.jur)):
            with self.subTest(evento=evento):
                self.assertEqual(self.decide(evento), "sem_decisao")

    def test_raiz_da_fundacao_por_juncao_definida_pelo_lancador_segue(self):
        atalho = self.base / "raiz-atalho"
        criar_ligacao_dir(atalho, self.raiz)
        self.assertEqual(self.decide(escrever(atalho / "projects" / "juridico-lab" / "x.md"), raiz=atalho),
                         "sem_decisao")
        self.assertEqual(self.decide(escrever(self.jur / "x.md"), raiz=atalho), "sem_decisao")
        self.assertEqual(self.decide(escrever(atalho / "projects" / "reversa-lab" / "x.md"), raiz=atalho), "deny")

    def test_fora_do_projeto_continua_negado(self):
        for alvo in (self.rev / "x.md", self.raiz / "registry" / "x.json", self.fora / "x.md",
                     self.jur / ".." / "reversa-lab" / "y.md"):
            with self.subTest(alvo=str(alvo)):
                self.assertEqual(self.decide(escrever(alvo)), "deny")


if __name__ == "__main__":
    unittest.main()
