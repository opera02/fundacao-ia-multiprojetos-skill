"""Revisão de segurança da 1.7.7 sobre a correção do achado #1 da auditoria Codex Security da 1.7.6 (o plano de
execução do fluxo B, `scripts/execucao_isolada.py`). Dois pontos e uma nota:

- R177-FB-02 (média): o SHA-256 aprovado prendia o programa (`comando[0]`, quase sempre o interpretador), não o
  script que ele roda; o `--manifesto`, que prende a cópia, era opcional e a folha não dizia nada disso. Reprodução do
  revisor: plano com `--copia` e sem `--manifesto`, hash aprovado, `app.py` trocado -> o `gravar` rodou o script
  trocado. Agora `--copia` exige `--manifesto`, o comando não cita arquivo fora da cópia, o plano lista o que a cópia
  tem e o manifesto não vê, e sem cópia (só sem isolamento) o plano marca o código como não preso; a folha diz cada
  caso em letras claras.
- R177-FB-01 (baixa): a folha não listava entradas nem a pasta gravável e afirmava "nada da sua pasta pessoal"; no
  isolamento, uma entrada fora da cópia (até da pasta pessoal ou de outro projeto) era montada e lida. Agora a folha
  lista e avisa, e no isolamento entradas e `--pasta-saida` ficam dentro da cópia ou do projeto dela.
- Nota: `run_case` sem plano rodava sem isolamento por padrão; agora exige o plano ou o motivo explícito.

Programas e dados fictícios, em pastas descartáveis. O plano isolado é montado com o caminho do bubblewrap informado
(nada roda nele), e o que ele monta é conferido por `conferir`: vale no Windows e no Linux.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import ENV, SCRIPTS

MOTIVO = "revisão da 1.7.7: programas fictícios do próprio teste"
SEM_ISOLAMENTO = ("--sem-isolamento", MOTIVO)
BWRAP = "/usr/bin/bwrap"  # só o caminho: o plano isolado é montado e conferido, não executado


def carregar(nome: str):
    spec = importlib.util.spec_from_file_location(f"_revisao_177_fb_{nome}", SCRIPTS / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def cli(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / "caracterizar.py"), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, timeout=300)


def erro(p: subprocess.CompletedProcess) -> str:
    """A mensagem `{"erro": ...}` do stderr (ou o stderr inteiro, se não houver)."""
    for linha in reversed(p.stderr.strip().splitlines()):
        try:
            return json.loads(linha)["erro"]
        except (ValueError, KeyError, TypeError):
            continue
    return p.stderr


def pasta(teste: unittest.TestCase, prefixo: str) -> Path:
    """Pasta descartável pelo caminho real (sem nome curto do Windows nem ligação no caminho)."""
    base = Path(os.path.realpath(tempfile.mkdtemp(prefix=prefixo)))
    teste.addCleanup(shutil.rmtree, base, ignore_errors=True)
    return base


def manifesto_de(raiz: Path, saida: Path) -> Path:
    r = subprocess.run([sys.executable, "-B", str(SCRIPTS / "manifesto.py"), "criar", "--raiz", str(raiz), "--saida",
                        str(saida)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return saida


class TestFB02CodigoPreso(unittest.TestCase):
    """Pela linha de comando, sem isolamento (vale em qualquer sistema): o que o hash e o manifesto prendem."""

    def setUp(self):
        self.base = pasta(self, "r177-fb02-")
        self.copia = self.base / "copia"
        (self.copia / "entradas").mkdir(parents=True)
        (self.copia / "entradas" / "um.json").write_text("{}", encoding="utf-8")
        self.app = self.copia / "app.py"
        self.app.write_text("import sys\nprint('caso', sys.argv[1][-7:])\n", encoding="utf-8")
        self.golden = self.base / "golden.json"
        self.marca = self.base / "trocado-rodou.txt"

    def args(self, *extra, cmd=None) -> list:
        return ["--entradas", self.copia / "entradas" / "*.json", *extra, *SEM_ISOLAMENTO, "--",
                *(cmd or [sys.executable, self.app, "{entrada}"])]

    def trocar_o_script(self) -> None:
        self.app.write_text(f"import pathlib\npathlib.Path({str(self.marca)!r}).write_text('rodou')\n",
                            encoding="utf-8")

    def test_fb02_copia_sem_manifesto_recusa_e_o_script_trocado_nao_roda(self):
        # A reprodução do revisor: plano com --copia e sem --manifesto, hash aprovado, app.py trocado depois.
        args = self.args("--copia", self.copia)
        p = cli("plano", *args)
        aprovado = json.loads(p.stdout)["sha256"] if p.returncode == 0 else "0" * 64
        self.trocar_o_script()
        g = cli("gravar", "--plano-aprovado", aprovado, "--saida", self.golden, *args)
        self.assertFalse(self.marca.exists(), "rodou o script trocado depois do aceite")
        self.assertEqual(g.returncode, 2, g.stdout + g.stderr)
        self.assertEqual(p.returncode, 2, "plano com --copia e sem --manifesto foi aceito")
        self.assertIn("--manifesto", erro(p))
        self.assertFalse(self.golden.exists())

    def test_fb02_com_manifesto_a_folha_diz_que_o_codigo_esta_preso_por_ele(self):
        manifesto = manifesto_de(self.copia, self.base / "manifesto.json")
        p = cli("plano", *self.args("--copia", self.copia, "--manifesto", manifesto))
        self.assertEqual(p.returncode, 0, p.stderr)
        dados = json.loads(p.stdout)
        plano, folha = dados["plano"], dados["para_a_folha"]
        self.assertTrue(plano["codigo_executado"].startswith("preso pelo manifesto"), plano["codigo_executado"])
        self.assertEqual(plano["manifesto"]["fora_do_manifesto"], [])
        self.assertIn(f"Código importado preso pelo manifesto {manifesto} (SHA-256 {plano['manifesto']['sha256']})",
                      folha)
        self.assertIn("inclusive os módulos que o programa importa dela", folha)
        self.assertNotIn("ATENÇÃO: só o programa", folha)
        # E prende de fato: o script trocado depois do aceite não roda.
        self.trocar_o_script()
        g = cli("gravar", "--plano-aprovado", dados["sha256"], "--saida", self.golden,
                *self.args("--copia", self.copia, "--manifesto", manifesto))
        self.assertEqual(g.returncode, 2, g.stdout + g.stderr)
        self.assertIn("manifesto", erro(g))
        self.assertFalse(self.marca.exists(), "rodou o script trocado depois do aceite")

    def test_fb02_sem_copia_o_plano_marca_o_codigo_como_nao_preso_e_a_folha_avisa(self):
        p = cli("plano", *self.args())
        self.assertEqual(p.returncode, 0, p.stderr)
        dados = json.loads(p.stdout)
        plano, folha = dados["plano"], dados["para_a_folha"]
        self.assertTrue(plano["codigo_executado"].startswith("NÃO PRESO"), plano["codigo_executado"])
        self.assertIsNone(plano["manifesto"])
        self.assertIn(f"ATENÇÃO: só o programa {plano['programa']['caminho']} está preso pelo hash", folha)
        self.assertIn("o código que ele roda", folha)
        self.assertNotIn("preso pelo manifesto", folha)

    def test_fb02_comando_que_cita_script_fora_da_copia_e_recusado(self):
        # Com cópia e manifesto, o script do comando tem de estar na cópia: fora dela, o manifesto não o prende.
        manifesto = manifesto_de(self.copia, self.base / "manifesto.json")
        fora = self.base / "fora.py"
        fora.write_text("print('fora da cópia')\n", encoding="utf-8")
        p = cli("plano", *self.args("--copia", self.copia, "--manifesto", manifesto,
                                    cmd=[sys.executable, fora, "{entrada}"]))
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("fora da cópia", erro(p))
        self.assertIn(str(fora), erro(p))

    def test_fb02_manifesto_que_exclui_o_script_recusa_e_modulo_excluido_aparece(self):
        # Manifesto editado à mão, guardado na própria cópia: a exclusão literal tira o arquivo do `verificar`. O script
        # do comando assim excluído é recusado; um módulo excluído vai para fora_do_manifesto e para a folha.
        (self.copia / "util.py").write_text("X = 1\n", encoding="utf-8")
        manifesto = manifesto_de(self.copia, self.copia / "manifesto.json")

        def excluir(nome: str) -> None:
            dados = json.loads(manifesto.read_text(encoding="utf-8"))
            dados["politica"]["exclusoes_literais"].append(nome)
            dados["arquivos"] = [f for f in dados["arquivos"] if f["path"] != nome]
            manifesto.write_text(json.dumps(dados), encoding="utf-8")

        excluir("util.py")
        p = cli("plano", *self.args("--copia", self.copia, "--manifesto", manifesto))
        self.assertEqual(p.returncode, 0, p.stderr)
        dados = json.loads(p.stdout)
        self.assertEqual(dados["plano"]["manifesto"]["fora_do_manifesto"], ["util.py"], "o próprio manifesto não é aviso")
        self.assertIn("não vê nem prende (ligação, nome de segredo, exclusão dele ou pasta que ele ignora): util.py",
                      dados["para_a_folha"])
        excluir("app.py")
        p = cli("plano", *self.args("--copia", self.copia, "--manifesto", manifesto))
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("que o manifesto não prende", erro(p))

    def test_fb02_o_que_o_manifesto_nao_ve_vai_para_o_plano_e_um_novo_muda_o_hash(self):
        (self.copia / "node_modules" / "dep").mkdir(parents=True)
        (self.copia / "node_modules" / "dep" / "index.js").write_text("module.exports = 1\n", encoding="utf-8")
        (self.copia / "config.secret").write_text("ficticio\n", encoding="utf-8")
        manifesto = manifesto_de(self.copia, self.base / "manifesto.json")
        args = self.args("--copia", self.copia, "--manifesto", manifesto)
        p = cli("plano", *args)
        self.assertEqual(p.returncode, 0, p.stderr)
        dados = json.loads(p.stdout)
        self.assertEqual(dados["plano"]["manifesto"]["fora_do_manifesto"], ["config.secret", "node_modules/"])
        for item in ("config.secret", "node_modules/", "não vê nem prende"):
            self.assertIn(item, dados["para_a_folha"])
        # Uma pasta que o manifesto ignora, criada depois do aceite: o `verificar` não a vê, mas o plano muda.
        (self.copia / "__pycache__").mkdir()
        (self.copia / "__pycache__" / "app.cpython-312.pyc").write_bytes(b"pyc ficticio")
        g = cli("gravar", "--plano-aprovado", dados["sha256"], "--saida", self.golden, *args)
        self.assertEqual(g.returncode, 2, g.stdout + g.stderr)
        self.assertIn("o plano mudou", erro(g))
        self.assertFalse(self.golden.exists())


class TestFB02NoIsolamento(unittest.TestCase):
    def test_fb02_copia_sem_manifesto_recusa_tambem_no_isolamento(self):
        ex = carregar("execucao_isolada")
        copia = pasta(self, "r177-fb02-bwrap-") / "copia"
        copia.mkdir()
        (copia / "app.sh").write_text("echo ok\n", encoding="utf-8")
        with self.assertRaises(ex.Recusa) as ctx:
            ex.montar_plano("gravar", [str(copia / "app.sh")], copia=copia, manifesto=None, cwd=None, entradas=[],
                            gravavel=None, limites=ex.limites(30), variaveis=[], sem_isolamento=None, bwrap=BWRAP)
        self.assertIn("--manifesto", str(ctx.exception))


class TestFB01EntradasEPastaGravavel(unittest.TestCase):
    """Plano isolado montado com o caminho do bwrap informado; a cópia fica num projeto de uma fundação fictícia."""

    def setUp(self):
        self.ex = carregar("execucao_isolada")
        self.base = pasta(self, "r177-fb01-")
        self.raiz = self.base / "raiz"
        (self.raiz / "state").mkdir(parents=True)
        (self.raiz / "state" / "state.sqlite").write_bytes(b"")
        self.projeto = self.raiz / "projects" / "p"
        self.copia = self.projeto / "copia"
        self.copia.mkdir(parents=True)
        self.programa = self.copia / "app.sh"
        self.programa.write_text("echo ok\n", encoding="utf-8")
        self.manifesto = manifesto_de(self.copia, self.base / "manifesto.json")
        self.dados = self.projeto / "dados"
        self.dados.mkdir()
        self.entradas = []
        for nome in ("caso-1.json", "caso-2.json", "caso-3.json"):
            (self.dados / nome).write_text("{}", encoding="utf-8")
            self.entradas.append(self.dados / nome)

    def plano(self, entradas=None, gravavel=None, sem_isolamento=None) -> dict:
        return self.ex.montar_plano(
            "gravar", [str(self.programa), "{entrada}"], copia=self.copia, manifesto=self.manifesto, cwd=None,
            entradas=[str(e) for e in (self.entradas if entradas is None else entradas)],
            gravavel=gravavel or ("ensaio", self.projeto / "ensaio"), limites=self.ex.limites(30), variaveis=[],
            sem_isolamento=sem_isolamento, bwrap=None if sem_isolamento else BWRAP)

    def test_fb01_folha_lista_entradas_e_pasta_gravavel_e_a_frase_nova(self):
        folha = carregar("folha_do_plano")
        plano = self.plano()
        self.assertEqual(plano["projeto_da_copia"], str(self.projeto))
        texto = folha.para_a_folha(plano, "f" * 64)
        self.assertIn(f"3 entradas em {self.dados} (caso-1.json, caso-2.json, caso-3.json)", texto)
        self.assertIn(f"a pasta gravável {self.projeto / 'ensaio'}", texto)
        self.assertIn("além da cópia, das entradas e da pasta gravável que você indicou", texto)
        self.assertNotIn("ATENÇÃO", texto, "tudo fica no projeto da cópia: nada a avisar")
        self.ex.conferir(plano)  # entradas no projeto da cópia: aceitas

    def test_fb01_no_isolamento_entrada_fora_da_copia_e_do_projeto_e_recusada(self):
        # A reprodução do revisor (um arquivo qualquer fora da cópia), outro projeto da mesma fundação e a pasta
        # pessoal (o arquivo nem precisa existir: a recusa vem antes de abrir qualquer coisa).
        fora = self.base / "pe" / "segredos" / "leak.txt"
        outro = self.raiz / "projects" / "outro" / "dados" / "x.json"
        for alvo in (fora, outro):
            alvo.parent.mkdir(parents=True)
            alvo.write_text("CANARIO-R177-FB01", encoding="utf-8")
        casa = Path(os.path.realpath(os.path.expanduser("~"))) / "r177-fb01-inexistente.json"
        for alvo in (fora, outro, casa):
            with self.subTest(str(alvo)):
                with self.assertRaises(self.ex.Recusa) as ctx:
                    self.ex.conferir(self.plano(entradas=[*self.entradas, alvo]))
                self.assertIn("fora da cópia e do projeto", str(ctx.exception))
                self.assertIn(str(alvo), str(ctx.exception))
        self.assertFalse(casa.exists())

    def test_fb01_no_isolamento_pasta_saida_fora_do_projeto_ou_que_contem_a_copia_e_recusada(self):
        saida_fora = self.base / "saida-fora"
        saida_fora.mkdir()
        with self.assertRaises(self.ex.Recusa) as ctx:
            self.ex.conferir(self.plano(gravavel=("pasta-saida", saida_fora)))
        self.assertIn("fora da cópia e do projeto", str(ctx.exception))
        with self.assertRaises(self.ex.Recusa) as ctx:
            self.ex.conferir(self.plano(gravavel=("pasta-saida", self.projeto)))
        self.assertIn("contém a cópia", str(ctx.exception))
        saida = self.projeto / "saida"
        saida.mkdir()
        self.ex.conferir(self.plano(gravavel=("pasta-saida", saida)))  # no projeto, ao lado da cópia: aceita

    def test_fb01_folha_avisa_o_que_fica_fora_e_o_que_fica_na_pasta_pessoal(self):
        folha = carregar("folha_do_plano")
        casa = self.base / "casa"
        (casa / "docs").mkdir(parents=True)
        pessoal = casa / "docs" / "pessoal.json"
        pessoal.write_text("{}", encoding="utf-8")
        saida = self.base / "saida"
        plano = self.plano(entradas=[*self.entradas, pessoal], gravavel=("pasta-saida", saida), sem_isolamento=MOTIVO)
        with mock.patch.object(folha, "_casa", return_value=str(casa)):
            texto = folha.para_a_folha(plano, "0" * 64)
        self.assertIn("4 entradas em", texto)
        self.assertIn(f"ATENÇÃO: fora da cópia e do projeto dela: {pessoal}, {saida}", texto)
        self.assertIn(f"ATENÇÃO: na sua pasta pessoal: {pessoal}", texto)
        # A cópia fora de um projeto da fundação também é avisada.
        avulsa = self.base / "avulsa"
        avulsa.mkdir()
        (avulsa / "app.sh").write_text("echo ok\n", encoding="utf-8")
        plano = self.ex.montar_plano("gravar", [str(avulsa / "app.sh")], copia=avulsa,
                                     manifesto=manifesto_de(avulsa, self.base / "m-avulsa.json"), cwd=None,
                                     entradas=[], gravavel=None, limites=self.ex.limites(30), variaveis=[],
                                     sem_isolamento=MOTIVO)
        self.assertIsNone(plano["projeto_da_copia"])
        self.assertIn("ATENÇÃO: a cópia não fica num projeto da fundação", folha.para_a_folha(plano, "0" * 64))


class TestRunCaseExigePlano(unittest.TestCase):
    """Nota do revisor: `run_case(plano=None)` rodava sem isolamento por padrão."""

    def test_run_case_sem_plano_e_sem_motivo_recusa_sem_executar(self):
        mod = carregar("caracterizar")
        marca = pasta(self, "r177-run-case-") / "rodou.txt"
        cmd = [sys.executable, "-c", f"import pathlib; pathlib.Path({str(marca)!r}).write_text('rodou')"]
        with self.assertRaises(mod.EXEC.Recusa) as ctx:
            mod.run_case(cmd, "", None, None, [], 30)
        self.assertIn("plano", str(ctx.exception))
        self.assertFalse(marca.exists(), "run_case sem plano executou o código")
        caso = mod.run_case(cmd, "", None, None, [], 30, sem_isolamento=MOTIVO)
        self.assertEqual(caso["codigo"], 0, caso["stderr"])
        self.assertTrue(marca.exists())


if __name__ == "__main__":
    unittest.main()
