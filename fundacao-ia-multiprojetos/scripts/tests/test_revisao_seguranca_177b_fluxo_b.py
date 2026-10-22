"""Revisão de segurança da 1.7.7, segunda passada, sobre o plano de execução do fluxo B (`scripts/execucao_isolada.py`,
`scripts/codigo_do_plano.py`, `scripts/folha_do_plano.py` e `scripts/caracterizar.py`): variantes que rodavam código
trocado depois do aceite com a folha dizendo "preso".

- R177B-B-01 (média): manifesto com `"politica": null` contornava o que o plano diz não prender. O lançador decidia o
  formato 1 por "política ausente"; o `manifesto.py verificar`, por "política nula", e tirava da verificação o que o
  manifesto lista em `excluidos`: com o `app.py` só em `excluidos`, o plano dizia "preso" e o `app.py` trocado rodava.
  Agora a regra é uma só (`manifesto.politica_efetiva`), política que não é dicionário do formato 2 é recusada e o
  arquivo que o comando cita tem de estar na lista de arquivos do manifesto, fora dos excluídos.
- R177B-B-02 (média): código de fora da cópia sem citar arquivo — `--cwd` na pasta gravável com `python3 -m app`,
  `--variavel PYTHONPATH=<pasta gravável>` e `python3 {entrada}` — rodava com a folha dizendo "preso". Agora o plano
  marca o código como NÃO PRESO, com os motivos, e a folha avisa e mostra a pasta de trabalho.
- R177B-B-03 (baixa): a cópia era conferida uma vez só, antes do primeiro caso: trocada durante ele, os casos seguintes
  rodavam o código trocado e o golden ficava com o hash aprovado. Agora o programa, o manifesto e a cópia são
  conferidos antes e depois de cada caso, e a divergência para a execução sem gravar o golden.

Programas e dados fictícios, em pastas descartáveis. Os planos isolados de R177B-B-02 são montados com o caminho do
bubblewrap informado (nada roda nele). Os casos de R177B-B-03 rodam no bubblewrap onde ele abre um sandbox (WSL) e,
fora dele, sem isolamento, com o motivo registrado: o mesmo teste vale no Windows e no Linux, sem teste pulado.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from apoio import ENV, SCRIPTS

MOTIVO = "revisão da 1.7.7, segunda passada: programas fictícios do próprio teste"
SEM_ISOLAMENTO = ("--sem-isolamento", MOTIVO)
BWRAP = "/usr/bin/bwrap"  # só o caminho: o plano isolado é montado e conferido, não executado


def carregar(nome: str):
    spec = importlib.util.spec_from_file_location(f"_revisao_177b_fb_{nome}", SCRIPTS / f"{nome}.py")
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


class TestB01PoliticaNula(unittest.TestCase):
    """Pela linha de comando, sem isolamento (vale em qualquer sistema): o manifesto editado à mão."""

    def setUp(self):
        self.base = pasta(self, "r177b-b01-")
        self.copia = self.base / "copia"
        (self.copia / "entradas").mkdir(parents=True)
        (self.copia / "entradas" / "um.json").write_text("{}", encoding="utf-8")
        self.app = self.copia / "app.py"
        self.app.write_text("print('benigno')\n", encoding="utf-8")
        (self.copia / "util.py").write_text("X = 1\n", encoding="utf-8")
        self.manifesto = manifesto_de(self.copia, self.base / "manifesto.json")
        self.golden = self.base / "golden.json"
        self.marca = self.base / "trocado-rodou.txt"

    def args(self) -> list:
        return ["--entradas", self.copia / "entradas" / "*.json", "--copia", self.copia, "--manifesto", self.manifesto,
                *SEM_ISOLAMENTO, "--", sys.executable, self.app, "{entrada}"]

    def editar(self, politica, so_em_excluidos=()) -> None:
        """Troca a política e passa os arquivos indicados da lista de arquivos para a de excluídos."""
        dados = json.loads(self.manifesto.read_text(encoding="utf-8"))
        dados["politica"] = politica
        dados["arquivos"] = [f for f in dados["arquivos"] if f["path"] not in so_em_excluidos]
        dados["excluidos"] += [{"path": p, "motivo": "editado à mão"} for p in so_em_excluidos]
        self.manifesto.write_text(json.dumps(dados), encoding="utf-8")

    def test_b01_politica_nula_e_o_script_so_em_excluidos_recusa_e_o_trocado_nao_roda(self):
        # A reprodução do revisor: `politica` nula e o app.py só em `excluidos`; hash aprovado; app.py trocado depois.
        self.editar(None, ["app.py"])
        p = cli("plano", *self.args())
        aprovado = json.loads(p.stdout)["sha256"] if p.returncode == 0 else "0" * 64
        self.app.write_text(f"import pathlib\npathlib.Path({str(self.marca)!r}).write_text('rodou')\n",
                            encoding="utf-8")
        g = cli("gravar", "--plano-aprovado", aprovado, "--saida", self.golden, *self.args())
        self.assertFalse(self.marca.exists(), "rodou o script trocado depois do aceite")
        self.assertEqual(g.returncode, 2, g.stdout + g.stderr)
        self.assertFalse(self.golden.exists())
        self.assertEqual(p.returncode, 2, "plano com política nula e o script só em excluidos foi aceito: "
                         + p.stdout[-600:])
        self.assertIn("que o manifesto não prende", erro(p))

    def test_b01_politica_nula_e_um_modulo_so_em_excluidos_vai_para_fora_do_manifesto(self):
        self.editar(None, ["util.py"])
        p = cli("plano", *self.args())
        self.assertEqual(p.returncode, 0, p.stderr)
        dados = json.loads(p.stdout)
        self.assertEqual(dados["plano"]["manifesto"]["fora_do_manifesto"], ["util.py"])
        self.assertIn("não vê nem prende (ligação, nome de segredo, exclusão dele ou pasta que ele ignora): util.py",
                      dados["para_a_folha"])

    def test_b01_politica_que_nao_e_dicionario_do_formato_2_e_recusada(self):
        validas = json.loads(self.manifesto.read_text(encoding="utf-8"))["politica"]
        for politica in ([], "padrao", 0, False, {}, {**validas, "pastas_ignoradas": "node_modules"}):
            with self.subTest(politica=politica):
                self.editar(politica)
                p = cli("plano", *self.args())
                self.assertEqual(p.returncode, 2, p.stdout[-400:])
                self.assertIn("política", erro(p))
                # O `verificar` usa a mesma regra: recusa (uso incorreto, código 2) em vez de cair com exceção.
                v = subprocess.run([sys.executable, "-B", str(SCRIPTS / "manifesto.py"), "verificar", "--raiz",
                                    str(self.copia), "--manifesto", str(self.manifesto)], capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", timeout=120)
                self.assertEqual(v.returncode, 2, v.stdout + v.stderr)
                self.assertIn("política", v.stderr)


class TestB02CodigoDeForaDaCopia(unittest.TestCase):
    """O que o hash e o manifesto não prendem sem que o comando cite um arquivo: pasta de trabalho, variáveis e o lugar
    de {entrada}/{ensaio} no comando."""

    def setUp(self):
        self.ex = carregar("execucao_isolada")
        self.base = pasta(self, "r177b-b02-")
        self.copia = self.base / "copia"
        (self.copia / "entradas").mkdir(parents=True)
        (self.copia / "entradas" / "um.json").write_text("{}", encoding="utf-8")
        self.app = self.copia / "app.py"
        self.app.write_text("import sys\nprint('da cópia', sys.argv[1:])\n", encoding="utf-8")
        (self.copia / "app.sh").write_text("echo ok\n", encoding="utf-8")
        (self.copia / "app.js").write_text("console.log('ok')\n", encoding="utf-8")
        self.manifesto = manifesto_de(self.copia, self.base / "manifesto.json")
        self.saida = self.base / "saida"
        self.saida.mkdir()

    def plano(self, comando, *, variaveis=(), gravavel=None) -> dict:
        """Plano sem isolamento (vale em qualquer sistema), com a cópia, o manifesto e a pasta de trabalho padrão."""
        return self.ex.montar_plano("gravar", [str(c) for c in comando], copia=self.copia, manifesto=self.manifesto,
                                    cwd=None, entradas=[str(self.copia / "entradas" / "um.json")], gravavel=gravavel,
                                    limites=self.ex.limites(30), variaveis=list(variaveis), sem_isolamento=MOTIVO)

    def test_b02_pasta_de_trabalho_na_pasta_gravavel_marca_nao_preso_e_a_folha_mostra_a_pasta(self):
        # A reprodução do revisor, sem isolamento: `--cwd <pasta-saida> -- python -m app`, com um app.py lá.
        (self.saida / "app.py").write_text("print('da pasta gravável')\n", encoding="utf-8")
        comuns = ["--entradas", self.copia / "entradas" / "*.json", "--copia", self.copia, "--manifesto",
                  self.manifesto, "--pasta-saida", self.saida, *SEM_ISOLAMENTO]
        p = cli("plano", *comuns, "--cwd", self.saida, "--", sys.executable, "-m", "app", "{entrada}")
        self.assertEqual(p.returncode, 0, p.stderr)
        dados = json.loads(p.stdout)
        plano, folha = dados["plano"], dados["para_a_folha"]
        self.assertTrue(plano["codigo_executado"].startswith("NÃO PRESO"), plano["codigo_executado"])
        self.assertIn(f"pasta de trabalho {self.saida}", folha)
        self.assertIn("ATENÇÃO: o código que o programa roda NÃO está preso", folha)
        self.assertNotIn("inclusive os módulos que o programa importa dela", folha)
        # Com a pasta de trabalho na cópia (o padrão), o código fica preso e a folha mostra a pasta também.
        p = cli("plano", *comuns, "--", sys.executable, "-m", "app", "{entrada}")
        self.assertEqual(p.returncode, 0, p.stderr)
        dados = json.loads(p.stdout)
        self.assertTrue(dados["plano"]["codigo_executado"].startswith("preso pelo manifesto"))
        self.assertIn(f"pasta de trabalho {self.copia}", dados["para_a_folha"])
        self.assertIn("inclusive os módulos que o programa importa dela", dados["para_a_folha"])

    def test_b02_no_isolamento_pasta_de_trabalho_na_pasta_saida_marca_nao_preso(self):
        # Plano isolado (caminho do bwrap informado): cópia e pasta-saida no projeto de uma fundação fictícia.
        raiz = self.base / "raiz"
        (raiz / "state").mkdir(parents=True)
        (raiz / "state" / "state.sqlite").write_bytes(b"")
        projeto = raiz / "projects" / "p"
        copia, saida = projeto / "copia", projeto / "saida"
        copia.mkdir(parents=True)
        saida.mkdir()
        programa = copia / "app.sh"
        programa.write_text("echo ok\n", encoding="utf-8")
        manifesto = manifesto_de(copia, self.base / "manifesto-bwrap.json")

        def plano(cwd) -> dict:
            return self.ex.montar_plano("gravar", [str(programa)], copia=copia, manifesto=manifesto, cwd=cwd,
                                        entradas=[], gravavel=("pasta-saida", saida), limites=self.ex.limites(30),
                                        variaveis=[], sem_isolamento=None, bwrap=BWRAP)

        isolado = plano(saida)
        self.assertEqual(isolado["isolamento"], "bwrap")
        self.assertTrue(isolado["codigo_executado"].startswith("NÃO PRESO"), isolado["codigo_executado"])
        self.ex.conferir(isolado)  # o plano continua válido: o titular decide vendo o aviso
        self.assertTrue(plano(None)["codigo_executado"].startswith("preso pelo manifesto"))

    def test_b02_variavel_que_muda_de_onde_o_codigo_e_carregado_marca_nao_preso(self):
        folha = carregar("folha_do_plano")
        for nome in ("PYTHONPATH", "PYTHONPYCACHEPREFIX", "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONHOME",
                     "NODE_OPTIONS", "NODE_PATH", "LD_PRELOAD", "LD_LIBRARY_PATH", "PERL5LIB", "PERL5OPT", "RUBYLIB",
                     "RUBYOPT", "BASH_ENV", "ENV", "CLASSPATH", "JAVA_TOOL_OPTIONS"):
            with self.subTest(nome):
                plano = self.plano([sys.executable, self.app, "{entrada}"], variaveis=[f"{nome}={self.saida}"])
                self.assertTrue(plano["codigo_executado"].startswith("NÃO PRESO"), plano["codigo_executado"])
                self.assertIn(nome, plano["codigo_executado"])
                texto = folha.para_a_folha(plano, "0" * 64)
                self.assertIn("ATENÇÃO: o código que o programa roda NÃO está preso", texto)
                self.assertIn(nome, texto)
        # Variável que não muda o carregamento do código: continua preso.
        plano = self.plano([sys.executable, self.app, "{entrada}"], variaveis=["CANARIO_B02=1"])
        self.assertTrue(plano["codigo_executado"].startswith("preso pelo manifesto"), plano["codigo_executado"])

    def test_b02_entrada_ou_ensaio_no_lugar_do_codigo_marca_nao_preso(self):
        sistema = self.base / "sistema"  # programas de mentira, só para o plano (nada roda)
        sistema.mkdir()
        for nome in ("sh", "node", "env"):
            (sistema / nome).write_bytes(b"programa ficticio\n")
        py, sh, node, env = sys.executable, sistema / "sh", sistema / "node", sistema / "env"
        nao_presos = {
            "python {entrada}": [py, "{entrada}"],
            "python -X utf8 {entrada}": [py, "-X", "utf8", "{entrada}"],
            "python -B -- {entrada}": [py, "-B", "--", "{entrada}"],
            "python -m {entrada}": [py, "-m", "{entrada}"],
            "python -c com {entrada} no código": [py, "-c", "exec(open('{entrada}').read())"],
            "python -X pycache_prefix={ensaio}": [py, "-X", "pycache_prefix={ensaio}", self.app, "{entrada}"],
            "sh {entrada}": [sh, "{entrada}"],
            "sh -e {entrada}": [sh, "-e", "{entrada}"],
            "sh -c {entrada}": [sh, "-c", "{entrada}"],
            "sh {ensaio}/x.sh": [sh, "{ensaio}/x.sh"],
            "node {entrada}": [node, "{entrada}"],
            "node --require {ensaio}/x.js app.js": [node, "--require", "{ensaio}/x.js", self.copia / "app.js"],
            "env python3 {entrada}": [env, "python3", "{entrada}"],
        }
        presos = {
            "python app.py {entrada}": [py, self.app, "{entrada}"],
            "python -B -X utf8 app.py {entrada} {ensaio}": [py, "-B", "-X", "utf8", self.app, "{entrada}", "{ensaio}"],
            "python -m app {entrada}": [py, "-m", "app", "{entrada}"],
            "python -c código {entrada}": [py, "-c", "import sys; print(sys.argv[1])", "{entrada}"],
            "sh app.sh {entrada} {ensaio}": [sh, self.copia / "app.sh", "{entrada}", "{ensaio}"],
            "sh -c 'cat \"$1\"' sh {entrada}": [sh, "-c", 'cat "$1"', "sh", "{entrada}"],
            "node app.js {entrada}": [node, self.copia / "app.js", "{entrada}"],
            "env python3 app.py {entrada}": [env, "python3", self.app, "{entrada}"],
            "programa da cópia {entrada}": [self.copia / "app.sh", "{entrada}"],
        }
        ensaio = ("ensaio", self.base / "ensaio")
        for nome, comando in nao_presos.items():
            with self.subTest(nome):
                plano = self.plano(comando, gravavel=ensaio)
                self.assertTrue(plano["codigo_executado"].startswith("NÃO PRESO"), plano["codigo_executado"])
        for nome, comando in presos.items():
            with self.subTest(nome):
                plano = self.plano(comando, gravavel=ensaio)
                self.assertTrue(plano["codigo_executado"].startswith("preso pelo manifesto"), plano["codigo_executado"])

    def test_b02_programa_que_e_a_entrada_ou_o_ensaio_e_recusado(self):
        for comando in (["{entrada}"], ["{ensaio}/prog"]):
            with self.subTest(comando), self.assertRaises(self.ex.Recusa) as ctx:
                self.plano(comando)
            self.assertIn("não pode ser {entrada} nem {ensaio}", str(ctx.exception))


# R177B-B-03: o app.py do primeiro caso avisa que começou e espera a troca feita por fora; o trocado deixa uma marca.
BENIGNO = ("import pathlib, sys, time\n"
           "caso = pathlib.Path(sys.argv[2])\n"
           "if caso.name == 'caso-000':\n"
           "    (caso / 'iniciou').write_text('1')\n"
           "    fim = time.time() + 30\n"
           "    while not (caso / 'pode-seguir').exists() and time.time() < fim:\n"
           "        time.sleep(0.05)\n"
           "print('benigno', pathlib.Path(sys.argv[1]).name)\n")
TROCADO = ("import pathlib, sys\n"
           "(pathlib.Path(sys.argv[2]) / 'trocado-rodou').write_text('1')\n"
           "print('TROCADO')\n")


class TestB03ConferidaACadaCaso(unittest.TestCase):
    """No bubblewrap onde ele abre um sandbox (WSL); fora dele, sem isolamento, com o motivo: o mesmo teste nos dois."""

    def setUp(self):
        self.ex = carregar("execucao_isolada")
        bwrap, _motivo = self.ex.sondar_bwrap()
        self.modo = [] if bwrap else list(SEM_ISOLAMENTO)
        self.base = pasta(self, "r177b-b03-")
        self.copia = self.base / "raiz" / "projects" / "p" / "copia"
        (self.copia / "entradas").mkdir(parents=True)
        for nome in ("a.json", "b.json", "c.json"):
            (self.copia / "entradas" / nome).write_text("{}", encoding="utf-8")
        self.app = self.copia / "app.py"
        self.app.write_text(BENIGNO, encoding="utf-8")
        self.manifesto = manifesto_de(self.copia, self.base / "manifesto.json")
        self.ensaio = self.base / "raiz" / "projects" / "p" / "ensaio"
        self.golden = self.base / "golden.json"

    def gravar_trocando_no_primeiro_caso(self, trocar) -> subprocess.CompletedProcess:
        """Plano e `gravar` com três casos; durante o primeiro, `trocar()` muda a cópia por fora."""
        args = ["--entradas", self.copia / "entradas" / "*.json", "--copia", self.copia, "--manifesto", self.manifesto,
                "--ensaio", self.ensaio, *self.modo, "--", sys.executable, self.app, "{entrada}", "{ensaio}"]
        p = cli("plano", *args)
        self.assertEqual(p.returncode, 0, p.stderr)
        dados = json.loads(p.stdout)
        self.assertTrue(dados["plano"]["codigo_executado"].startswith("preso pelo manifesto"))

        def no_primeiro_caso() -> None:
            caso = self.ensaio / "caso-000"
            fim = time.time() + 120
            while not (caso / "iniciou").exists() and time.time() < fim:
                time.sleep(0.05)
            trocar()
            (caso / "pode-seguir").write_text("1", encoding="utf-8")

        troca = threading.Thread(target=no_primeiro_caso, daemon=True)
        troca.start()
        g = cli("gravar", "--plano-aprovado", dados["sha256"], "--saida", self.golden, *args)
        troca.join(timeout=150)
        return g

    def conferir_que_parou(self, g: subprocess.CompletedProcess) -> None:
        rodou = sorted(p.relative_to(self.ensaio).as_posix() for p in self.ensaio.rglob("trocado-rodou"))
        self.assertEqual(rodou, [], "o código trocado rodou depois do aceite")
        self.assertEqual(g.returncode, 2, g.stdout + g.stderr)
        self.assertFalse(self.golden.exists(), "o golden foi gravado com a cópia trocada")
        self.assertIn("o golden não foi gravado", erro(g))

    def test_b03_script_trocado_durante_o_primeiro_caso_para_e_nao_grava_o_golden(self):
        # A reprodução do revisor: script trocado por fora durante o primeiro de três casos.
        g = self.gravar_trocando_no_primeiro_caso(lambda: self.app.write_text(TROCADO, encoding="utf-8"))
        self.conferir_que_parou(g)
        self.assertIn("app.py", erro(g))

    def test_b03_manifesto_refeito_sobre_o_script_trocado_tambem_para(self):
        def trocar() -> None:
            self.app.write_text(TROCADO, encoding="utf-8")
            manifesto_de(self.copia, self.manifesto)  # o arquivo do manifesto do plano, refeito sobre o trocado

        g = self.gravar_trocando_no_primeiro_caso(trocar)
        self.conferir_que_parou(g)
        self.assertIn("manifesto", erro(g))

    def test_b03_item_novo_que_o_manifesto_nao_ve_entre_os_casos_para(self):
        def plantar() -> None:  # bytecode numa pasta que o manifesto ignora: o `verificar` sozinho não o vê
            (self.copia / "__pycache__").mkdir()
            (self.copia / "__pycache__" / "util.cpython-312.pyc").write_bytes(b"bytecode ficticio")

        g = self.gravar_trocando_no_primeiro_caso(plantar)
        self.assertEqual(g.returncode, 2, g.stdout + g.stderr)
        self.assertFalse(self.golden.exists())
        self.assertIn("__pycache__", erro(g))

    def test_b03_programa_trocado_depois_do_plano_e_recusado(self):
        programa = self.base / "sistema" / "prog"
        programa.parent.mkdir()
        programa.write_bytes(b"programa ficticio v1\n")
        plano = self.ex.montar_plano("caso", [str(programa)], copia=None, manifesto=None, cwd=None, entradas=[],
                                     gravavel=None, limites=self.ex.limites(30), variaveis=[], sem_isolamento=MOTIVO)
        self.ex.conferir(plano)
        programa.write_bytes(b"programa ficticio v2\n")
        with self.assertRaises(self.ex.Recusa) as ctx:
            self.ex.conferir(plano)
        self.assertIn("programa", str(ctx.exception))

    def test_b03_pasta_gravavel_dentro_da_copia_fica_fora_da_conferencia_e_a_folha_avisa(self):
        # O uso do CEN-02 (o programa grava em saida/, dentro da própria pasta): roda os três casos e a folha avisa.
        programa = self.copia / "escreve.py"
        programa.write_text("import pathlib, sys\npathlib.Path('saida').mkdir(exist_ok=True)\n"
                            "(pathlib.Path('saida') / (pathlib.Path(sys.argv[1]).stem + '.txt')).write_text('ok')\n",
                            encoding="utf-8")
        manifesto_de(self.copia, self.manifesto)
        args = ["--entradas", self.copia / "entradas" / "*.json", "--copia", self.copia, "--manifesto", self.manifesto,
                "--pasta-saida", self.copia / "saida", *self.modo, "--", sys.executable, programa, "{entrada}"]
        p = cli("plano", *args)
        self.assertEqual(p.returncode, 0, p.stderr)
        dados = json.loads(p.stdout)
        self.assertEqual(dados["plano"]["manifesto"].get("pasta_gravavel_na_copia"), "saida")
        self.assertIn("ATENÇÃO: a pasta gravável fica dentro da cópia (saida/)", dados["para_a_folha"])
        g = cli("gravar", "--plano-aprovado", dados["sha256"], "--saida", self.golden, *args)
        self.assertEqual(g.returncode, 0, g.stdout + g.stderr)
        casos = json.loads(self.golden.read_text(encoding="utf-8"))["casos"]
        self.assertEqual([sorted(c["efeitos"]["escritos"]) for c in casos], [["a.txt"], ["b.txt"], ["c.txt"]])


if __name__ == "__main__":
    unittest.main()
