"""Auditoria Codex Security da 1.7.6, achado #1 (alto): o fluxo B executava código importado sem fronteira de
isolamento. A "cópia isolada" do B6 só trocava a pasta de trabalho: o `caracterizar.py` rodava o programa com o
ambiente (identidade, chaves), a rede e os arquivos da conta; um descendente destacado sobrevivia ao prazo e ao fim
normal; e a saída não tinha teto.

Agora cada caso passa pelo lançador `scripts/execucao_isolada.py`, com um plano explícito preso por SHA-256
(`caracterizar.py plano`; `gravar` e `comparar` exigem `--plano-aprovado` igual ao recalculado): bubblewrap no
Linux/WSL; sem ele, recusa, salvo `--sem-isolamento "<motivo>"`, que fica no plano. Nos dois modos: ambiente mínimo,
árvore de processos encerrada no prazo, no teto de saída e no fim normal, e limites do SO. Os testes com o
bubblewrap de verdade só rodam onde ele abre um sandbox (no Windows ficam pulados). Programas e dados fictícios, em
pastas descartáveis.

Desde a revisão de segurança da 1.7.7 (R177-FB-02), `--copia` exige `--manifesto`: aqui o manifesto da cópia é feito
por `scripts/manifesto.py criar` e refeito quando o teste muda a cópia de propósito antes do plano; e `run_case` sem
plano exige o motivo explícito (`sem_isolamento=`), como o `--sem-isolamento` da linha de comando.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from apoio import ENV, SCRIPTS

SEM_ISOLAMENTO = ("--sem-isolamento", "teste da skill: programas fictícios do próprio teste")
MOTIVO = SEM_ISOLAMENTO[1]  # o mesmo motivo, para `run_case` sem plano
TETO_PADRAO = 32 * 1024 * 1024  # teto de saída padrão do plano, por fluxo (stdout e stderr)


def carregar(nome: str):
    spec = importlib.util.spec_from_file_location(f"_auditoria_176_g1_{nome}", SCRIPTS / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def cli(*args, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / "caracterizar.py"), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", env=env or ENV,
                          timeout=300)


def erro(p: subprocess.CompletedProcess) -> str:
    """A mensagem `{"erro": ...}` do stderr (ou o stderr inteiro, se não houver)."""
    for linha in reversed(p.stderr.strip().splitlines()):
        try:
            return json.loads(linha)["erro"]
        except (ValueError, KeyError, TypeError):
            continue
    return p.stderr


def pasta_temporaria(teste: unittest.TestCase, prefixo: str) -> Path:
    base = Path(tempfile.mkdtemp(prefix=prefixo))
    teste.addCleanup(shutil.rmtree, base, ignore_errors=True)
    return base


def manifesto_da_copia(copia: Path, saida: Path) -> Path:
    """`scripts/manifesto.py criar` da cópia, gravado fora dela (`--copia` exige `--manifesto` desde a 1.7.7)."""
    r = subprocess.run([sys.executable, "-B", str(SCRIPTS / "manifesto.py"), "criar", "--raiz", str(copia), "--saida",
                        str(saida)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return saida


# Neto destacado: grava "iniciou", espera e grava a marca atrasada. O filho cria o neto fora do grupo de processos
# (POSIX: sessão própria) ou destacado e tentando sair do Job Object (Windows), espera o neto começar e fica um tempo.
NETO = ("import pathlib, sys, time\n"
        "pathlib.Path(sys.argv[1]).write_text('iniciou')\n"
        "time.sleep(float(sys.argv[3]))\n"
        "pathlib.Path(sys.argv[2]).write_text('atrasado')\n")
FILHO = ("import os, pathlib, subprocess, sys, time\n"
         "iniciou, marca, espera, fica = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])\n"
         f"args = [sys.executable, '-c', {NETO!r}, iniciou, marca, espera]\n"
         "nulo = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
         "if os.name == 'nt':\n"
         "    destacado = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP\n"
         "    try:\n"
         "        subprocess.Popen(args, creationflags=destacado | 0x01000000, **nulo)  # CREATE_BREAKAWAY_FROM_JOB\n"
         "    except OSError:\n"
         "        subprocess.Popen(args, creationflags=destacado, **nulo)\n"
         "else:\n"
         "    subprocess.Popen(args, start_new_session=True, **nulo)\n"
         "fim = time.time() + 15\n"
         "while not pathlib.Path(iniciou).exists() and time.time() < fim:\n"
         "    time.sleep(0.05)\n"
         "time.sleep(fica)\n")


class TestCasoContido(unittest.TestCase):
    """Pela função de cada caso (`run_case`): o que o programa recebe e o que sobra dele."""

    def test_canario_de_ambiente_nao_chega_ao_programa(self):
        mod = carregar("caracterizar")
        programa = ("import json, os\n"
                    "print(json.dumps({'nomes': sorted(os.environ), 'casa': {k: os.environ.get(k) for k in "
                    "('HOME', 'USERPROFILE', 'TEMP', 'TMP', 'TMPDIR')}}))\n")
        canarios = {"FUNDACAO_PRINCIPAL": "canario-identidade-g1", "FUNDACAO_PROJECT": "canario-projeto-g1",
                    "ANTHROPIC_API_KEY": "canario-chave-de-api-g1", "PYTHONPATH": "canario-pythonpath-g1"}
        with mock.patch.dict(os.environ, canarios):
            caso = mod.run_case([sys.executable, "-c", programa], "", None, None, [], 60, sem_isolamento=MOTIVO)
        self.assertEqual(caso["codigo"], 0, caso["stderr"])
        dados = json.loads(caso["stdout"])
        for nome, valor in canarios.items():
            self.assertNotIn(nome, dados["nomes"], f"{nome} chegou ao programa")
            self.assertNotIn(valor, caso["stdout"])
        reais = {os.path.normcase(str(Path.home())), os.path.normcase(tempfile.gettempdir())}
        for nome, valor in dados["casa"].items():
            if valor:
                self.assertNotIn(os.path.normcase(valor), reais, f"{nome} aponta para a pasta real da conta")

    def test_descendente_destacado_nao_grava_depois_do_fim_normal(self):
        mod = carregar("caracterizar")
        base = pasta_temporaria(self, "g1-fim-normal-")
        iniciou, marca = base / "iniciou.txt", base / "marca.txt"
        caso = mod.run_case([sys.executable, "-c", FILHO, str(iniciou), str(marca), "2", "0"], "", None, None, [], 60,
                            sem_isolamento=MOTIVO)
        self.assertEqual(caso["codigo"], 0, caso["stderr"])
        time.sleep(4)
        self.assertTrue(iniciou.exists(), "o descendente nem começou: o teste não provaria nada")
        self.assertFalse(marca.exists(), "descendente destacado sobreviveu ao fim normal do caso")

    def test_descendente_destacado_nao_grava_depois_do_timeout(self):
        mod = carregar("caracterizar")
        base = pasta_temporaria(self, "g1-timeout-")
        iniciou, marca = base / "iniciou.txt", base / "marca.txt"
        caso = mod.run_case([sys.executable, "-c", FILHO, str(iniciou), str(marca), "4", "60"], "", None, None, [], 3,
                            sem_isolamento=MOTIVO)
        self.assertEqual(caso["codigo"], "timeout")
        time.sleep(4)
        self.assertTrue(iniciou.exists(), "o descendente nem começou: o teste não provaria nada")
        self.assertFalse(marca.exists(), "descendente destacado sobreviveu ao prazo do caso")

    def test_saida_acima_do_teto_e_cortada_e_a_arvore_encerrada(self):
        mod = carregar("caracterizar")
        marca = pasta_temporaria(self, "g1-teto-") / "continuou.txt"
        programa = ("import pathlib, sys, time\n"
                    "bloco = b'x' * (1 << 20)\n"
                    f"for _ in range({TETO_PADRAO >> 20} + 8):\n"
                    "    sys.stdout.buffer.write(bloco)\n"
                    "sys.stdout.flush()\n"
                    "time.sleep(2)\n"
                    "pathlib.Path(sys.argv[1]).write_text('continuou')\n")
        caso = mod.run_case([sys.executable, "-c", programa, str(marca)], "", None, None, [], 60, sem_isolamento=MOTIVO)
        self.assertEqual(caso["codigo"], "saida_acima_do_teto")
        self.assertEqual(caso["stdout_tamanho"], TETO_PADRAO)
        time.sleep(3)
        self.assertFalse(marca.exists(), "o programa seguiu rodando depois do teto de saída")

    def test_efeitos_nao_seguem_ligacao_criada_pelo_programa(self):
        # O programa importado controla o que grava na pasta gravável; o lançador, de fora, não segue o que ele
        # deixou lá (junção no Windows, link simbólico no POSIX): a ligação é efeito, o destino não é lido.
        mod = carregar("caracterizar")
        base = pasta_temporaria(self, "g1-ligacao-")
        fora = base / "fora"
        fora.mkdir()
        (fora / "segredo-ficticio.txt").write_text("CANARIO-G1-FORA", encoding="utf-8")
        ensaio = base / "ensaio"
        mod.preparar_ensaio(ensaio)
        programa = ("import os, sys\n"
                    "alvo, link = sys.argv[1], os.path.join(sys.argv[2], 'atalho')\n"
                    "if os.name == 'nt':\n"
                    "    import _winapi\n"
                    "    _winapi.CreateJunction(alvo, link)\n"
                    "else:\n"
                    "    os.symlink(alvo, link, target_is_directory=True)\n")
        caso = mod.run_case([sys.executable, "-c", programa, str(fora), "{ensaio}"], "", None, None, [], 60, ensaio, 0,
                            sem_isolamento=MOTIVO)
        self.assertEqual(caso["codigo"], 0, caso["stderr"])
        escritos = caso["efeitos"]["escritos"]
        self.assertIn("atalho", escritos, "a ligação criada pelo programa não apareceu como efeito")
        self.assertNotIn("atalho/segredo-ficticio.txt", escritos, "o lançador seguiu a ligação para fora da pasta")


class TestPlanoPresoPorHash(unittest.TestCase):
    """Pela linha de comando: o plano, o hash e as recusas antes de executar."""

    def setUp(self):
        self.base = pasta_temporaria(self, "g1-plano-")
        self.copia = self.base / "copia"
        (self.copia / "entradas").mkdir(parents=True)
        (self.copia / "entradas" / "um.json").write_text("{}", encoding="utf-8")
        self.app = self.copia / "app.py"
        self.app.write_text("import sys\nprint('caso', sys.argv[1][-7:])\n", encoding="utf-8")
        self.golden = self.base / "golden.json"
        self.manifesto = self.base / "manifesto-copia.json"
        self.selar()

    def selar(self) -> None:
        """(Re)faz o manifesto da cópia: no início e quando o teste muda a cópia de propósito, antes do plano."""
        manifesto_da_copia(self.copia, self.manifesto)

    def args(self, *extra, cmd=None) -> list:
        return ["--entradas", self.copia / "entradas" / "*.json", "--copia", self.copia, "--manifesto", self.manifesto,
                *extra, "--", *(cmd or [sys.executable, self.app, "{entrada}"])]

    def plano(self, *args, env=None) -> tuple[subprocess.CompletedProcess, dict | None]:
        p = cli("plano", *args, env=env)
        return p, (json.loads(p.stdout) if p.returncode == 0 else None)

    def test_hash_muda_com_comando_ambiente_pasta_gravavel_motivo_limite_e_copia(self):
        outra = self.base / "outra-copia"
        shutil.copytree(self.copia, outra)  # a mesma cópia em outra pasta, com o manifesto e o script dela
        manifesto_outra = manifesto_da_copia(outra, self.base / "manifesto-outra.json")
        refeito = manifesto_da_copia(self.copia, self.base / "manifesto-refeito.json")
        variantes = {
            "base": self.args(*SEM_ISOLAMENTO),
            "comando": self.args(*SEM_ISOLAMENTO, cmd=[sys.executable, self.app, "{entrada}", "--outro"]),
            "ambiente": self.args(*SEM_ISOLAMENTO, "--variavel", "CANARIO_G1=1"),
            "pasta gravável": self.args(*SEM_ISOLAMENTO, "--ensaio", self.base / "ensaio-a"),
            "outra pasta gravável": self.args(*SEM_ISOLAMENTO, "--ensaio", self.base / "ensaio-b"),
            "motivo": self.args("--sem-isolamento", "outro motivo registrado"),
            "limite": self.args(*SEM_ISOLAMENTO, "--memoria-mb", "1024"),
            "cópia": ["--entradas", self.copia / "entradas" / "*.json", "--copia", outra, "--manifesto",
                      manifesto_outra, *SEM_ISOLAMENTO, "--", sys.executable, outra / "app.py", "{entrada}"],
            "manifesto": ["--entradas", self.copia / "entradas" / "*.json", "--copia", self.copia, "--manifesto",
                          refeito, *SEM_ISOLAMENTO, "--", sys.executable, self.app, "{entrada}"],
        }
        hashes = {}
        for nome, args in variantes.items():
            p, dados = self.plano(*args)
            self.assertEqual(p.returncode, 0, f"{nome}: {p.stderr}")
            hashes[nome] = dados["sha256"]
        self.assertEqual(len(set(hashes.values())), len(hashes), hashes)
        self.assertEqual(self.plano(*variantes["base"])[1]["sha256"], hashes["base"], "o plano não é determinístico")

    def test_plano_aprovado_divergente_recusa_sem_executar(self):
        marca = self.base / "b-rodou.txt"
        outro = self.copia / "b.py"
        outro.write_text(f"import pathlib\npathlib.Path({str(marca)!r}).write_text('rodou')\n", encoding="utf-8")
        self.selar()  # b.py faz parte da cópia aprovada: a recusa abaixo é pelo comando, não pelo manifesto
        _p, aprovado = self.plano(*self.args(*SEM_ISOLAMENTO))
        p = cli("gravar", "--plano-aprovado", aprovado["sha256"], "--saida", self.golden,
                *self.args(*SEM_ISOLAMENTO, cmd=[sys.executable, outro, "{entrada}"]))
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("o plano mudou", erro(p))
        self.assertFalse(marca.exists(), "rodou um comando diferente do aprovado")
        self.assertFalse(self.golden.exists())
        ok = cli("gravar", "--plano-aprovado", aprovado["sha256"], "--saida", self.golden, *self.args(*SEM_ISOLAMENTO))
        self.assertEqual(ok.returncode, 0, ok.stderr)
        golden = json.loads(self.golden.read_text(encoding="utf-8"))
        self.assertEqual((golden["plano_sha256"], golden["isolamento"]), (aprovado["sha256"], "nenhum"))
        # O plano do gravar não serve para o comparar (outra ação, outras entradas): recusa até o plano dele.
        cmp_args = ["--golden", self.golden, "--copia", self.copia, "--manifesto", self.manifesto, *SEM_ISOLAMENTO,
                    "--", sys.executable, self.app, "{entrada}"]
        self.assertEqual(cli("comparar", "--plano-aprovado", aprovado["sha256"], *cmp_args).returncode, 2)
        _p, plano_cmp = self.plano(*cmp_args)
        cmp = cli("comparar", "--plano-aprovado", plano_cmp["sha256"], *cmp_args)
        self.assertEqual(cmp.returncode, 0, cmp.stdout + cmp.stderr)

    def test_gravar_sem_plano_aprovado_recusa(self):
        p = cli("gravar", "--saida", self.golden, *self.args(*SEM_ISOLAMENTO))
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("--plano-aprovado", erro(p))
        self.assertFalse(self.golden.exists())

    def test_sem_bubblewrap_e_sem_opcao_recusa_com_o_caminho_para_o_leigo(self):
        vazio = self.base / "sem-programas"
        vazio.mkdir()
        env = {**ENV, "PATH": str(vazio)}  # nenhum bwrap à vista, também num Linux que o tenha
        p, _ = self.plano(*self.args(), env=env)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        for termo in ("WSL", "bubblewrap", "--sem-isolamento", "toda a autoridade da sua conta"):
            self.assertIn(termo, erro(p))
        marca = self.base / "rodou.txt"
        self.app.write_text(f"import pathlib\npathlib.Path({str(marca)!r}).write_text('rodou')\n", encoding="utf-8")
        g = cli("gravar", "--plano-aprovado", "0" * 64, "--saida", self.golden, *self.args(), env=env)
        self.assertEqual(g.returncode, 2, g.stdout + g.stderr)
        self.assertFalse(marca.exists(), "o código importado rodou sem isolamento e sem o motivo")

    def test_sem_isolamento_registra_o_motivo_e_avisa_a_autoridade_total(self):
        p, dados = self.plano(*self.args("--sem-isolamento", "fixture fictícia do teste"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(dados["plano"]["isolamento"], "nenhum")
        self.assertEqual(dados["plano"]["motivo_sem_isolamento"], "fixture fictícia do teste")
        for termo in ("SEM ISOLAMENTO", "toda a autoridade da sua conta", "usa a rede", dados["sha256"]):
            self.assertIn(termo, dados["para_a_folha"])
        vazio, _ = self.plano(*self.args("--sem-isolamento", "   "))
        self.assertEqual(vazio.returncode, 2, "sem isolamento e sem motivo")

    def test_variavel_de_segredo_e_identidade_com_valor_sao_recusadas(self):
        for nome in ("ANTHROPIC_API_KEY", "GITHUB_TOKEN", "SENHA_DO_BANCO"):
            with self.subTest(nome):
                p, _ = self.plano(*self.args(*SEM_ISOLAMENTO, "--variavel", nome), env={**ENV, nome: "canario-g1"})
                self.assertEqual(p.returncode, 2, p.stdout)
                self.assertIn("segredo", erro(p))
        p, _ = self.plano(*self.args(*SEM_ISOLAMENTO, "--variavel", "FUNDACAO_PRINCIPAL=forjado"))
        self.assertEqual(p.returncode, 2, p.stdout)
        self.assertIn("lançador", erro(p))
        # A identidade do lançador passa só pelo nome (B8: a ferramenta de execução da fundação precisa dela).
        p, dados = self.plano(*self.args(*SEM_ISOLAMENTO, "--variavel", "FUNDACAO_PRINCIPAL"),
                              env={**ENV, "FUNDACAO_PRINCIPAL": "ensaio-g1"})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(dados["plano"]["ambiente"]["FUNDACAO_PRINCIPAL"], "ensaio-g1")

    def test_copia_diferente_do_manifesto_recusa_antes_de_executar(self):
        # O manifesto da cópia vem do setUp (`manifesto.py criar`), como em todos os planos com cópia desde a 1.7.7.
        _p, dados = self.plano(*self.args(*SEM_ISOLAMENTO))
        self.assertEqual(dados["plano"]["manifesto"]["sha256"], hashlib.sha256(self.manifesto.read_bytes()).hexdigest())
        marca = self.base / "adulterado-rodou.txt"
        self.app.write_text(f"import pathlib\npathlib.Path({str(marca)!r}).write_text('rodou')\n", encoding="utf-8")
        p = cli("gravar", "--plano-aprovado", dados["sha256"], "--saida", self.golden, *self.args(*SEM_ISOLAMENTO))
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("manifesto", erro(p))
        self.assertFalse(marca.exists(), "rodou código diferente do manifesto do plano")

    def test_golden_dentro_da_pasta_gravavel_e_recusado(self):
        ensaio = self.base / "ensaio"
        args = self.args(*SEM_ISOLAMENTO, "--ensaio", ensaio)
        _p, dados = self.plano(*args)
        p = cli("gravar", "--plano-aprovado", dados["sha256"], "--saida", ensaio / "golden.json", *args)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("gravável", erro(p))

    def test_lancador_morto_de_repente_nao_deixa_o_caso_rodando(self):
        iniciou, marca = self.base / "iniciou.txt", self.base / "marca.txt"
        prog = self.copia / "demora.py"
        prog.write_text(f"import pathlib, time\npathlib.Path({str(iniciou)!r}).write_text('iniciou')\n"
                        f"time.sleep(3)\npathlib.Path({str(marca)!r}).write_text('atrasado')\n", encoding="utf-8")
        self.selar()
        args = self.args(*SEM_ISOLAMENTO, cmd=[sys.executable, prog, "{entrada}"])
        _p, dados = self.plano(*args)
        lancador = subprocess.Popen([sys.executable, "-B", str(SCRIPTS / "caracterizar.py"), "gravar",
                                     "--plano-aprovado", dados["sha256"], "--saida", str(self.golden), *map(str, args)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=ENV)
        fim = time.time() + 30
        while not iniciou.exists() and time.time() < fim:
            time.sleep(0.05)
        self.assertTrue(iniciou.exists(), "o caso nem começou")
        lancador.kill()  # TerminateProcess no Windows, SIGKILL no POSIX: nenhum `finally` do lançador roda
        lancador.wait(timeout=30)
        time.sleep(4)
        self.assertFalse(marca.exists(), "o caso continuou rodando depois que o lançador morreu")

    def test_memoria_limitada_pelo_sistema(self):
        prog = self.copia / "aloca.py"
        prog.write_text("x = bytearray(1 << 30)\nprint('alocou', len(x))\n", encoding="utf-8")
        self.selar()
        args = self.args(*SEM_ISOLAMENTO, "--memoria-mb", "256", cmd=[sys.executable, prog, "{entrada}"])
        _p, dados = self.plano(*args)
        p = cli("gravar", "--plano-aprovado", dados["sha256"], "--saida", self.golden, *args)
        self.assertEqual(p.returncode, 0, p.stderr)
        caso = json.loads(self.golden.read_text(encoding="utf-8"))["casos"][0]
        self.assertNotIn("alocou", caso["stdout"])
        self.assertNotEqual(caso["codigo"], 0)
        self.assertIn("MemoryError", caso["stderr"])


class TestArgvDoBubblewrap(unittest.TestCase):
    """O que o sandbox monta, conferido sem rodar o bubblewrap (vale em qualquer sistema)."""

    def test_argv_traduz_o_plano_e_so_a_pasta_do_caso_e_gravavel(self):
        ex = carregar("execucao_isolada")
        copia, entrada = "/raiz/projects/p/copia", "/raiz/projects/p/entradas/um.json"
        caso = "/raiz/projects/p/ensaio/caso-000"
        plano = {"bwrap": "/usr/bin/bwrap", "cwd": copia,
                 "ambiente": {"PATH": ex.PATH_ISOLADO, "HOME": "/tmp", "TMPDIR": "/tmp", "LANG": "C.UTF-8"},
                 "montagens": [["ro-bind", "/usr", "/usr"], ["symlink", "usr/bin", "/bin"], ["ro-bind", "/etc", "/etc"],
                               ["proc", "/proc"], ["dev", "/dev"], ["tmpfs", "/tmp"], ["ro-bind", copia, copia]]}
        argv = ex.argv_bwrap(plano, ["/usr/bin/python3", "app.py", entrada], entrada=entrada, gravavel=caso)
        corte = argv.index("--")
        opcoes, comando = argv[:corte], argv[corte + 1:]
        self.assertEqual(argv[0], "/usr/bin/bwrap")
        self.assertEqual(comando, ["/usr/bin/python3", "app.py", entrada])
        for flag in ("--unshare-all", "--die-with-parent", "--new-session", "--clearenv"):
            self.assertIn(flag, opcoes)
        self.assertNotIn("--share-net", opcoes)
        self.assertLess(opcoes.index("--clearenv"), opcoes.index("--setenv"))
        definidas = {opcoes[i + 1]: opcoes[i + 2] for i, o in enumerate(opcoes) if o == "--setenv"}
        self.assertEqual(definidas, plano["ambiente"])
        texto = " ".join(opcoes)
        for trecho in ("--ro-bind /usr /usr", "--symlink usr/bin /bin", "--proc /proc", "--dev /dev", "--tmpfs /tmp",
                       f"--ro-bind {copia} {copia}", f"--ro-bind {entrada} {entrada}", f"--bind {caso} {caso}",
                       f"--chdir {copia}"):
            self.assertIn(trecho, texto)
        self.assertEqual(opcoes.count("--bind"), 1, "só a pasta gravável do caso pode ser montada com escrita")

    def test_montagens_do_plano_nao_expoem_casa_raiz_state_nem_outros_projetos(self):
        ex = carregar("execucao_isolada")
        raiz = pasta_temporaria(self, "g1-montagens-") / "raiz"
        copia, entrada, ensaio = raiz / "projects" / "p" / "copia", raiz / "projects" / "p" / "um.json", raiz / "ensaio"
        for d in (raiz / "state", raiz / "projects" / "outro", copia):
            d.mkdir(parents=True)
        entrada.write_text("{}", encoding="utf-8")
        programa = copia / "app.sh"
        programa.write_text("echo ok\n", encoding="utf-8")
        manifesto = manifesto_da_copia(copia, raiz.parent / "manifesto-copia.json")
        plano = ex.montar_plano("gravar", [str(programa), "{entrada}"], copia=copia, manifesto=manifesto, cwd=None,
                                entradas=[str(entrada)], gravavel=("ensaio", ensaio), limites=ex.limites(30),
                                variaveis=[], sem_isolamento=None, bwrap="/usr/bin/bwrap")
        self.assertEqual((plano["isolamento"], plano["rede"]), ("bwrap", ex.REDE_NEGADA))
        origens = {m[1] for m in plano["montagens"] if m[0] in ("ro-bind", "bind")}
        self.assertEqual(origens - {"/usr", "/etc", "/bin", "/sbin", "/lib", "/lib64", "/lib32", "/libx32"},
                         {os.path.abspath(copia)})
        self.assertFalse(any(m[0] == "bind" for m in plano["montagens"]), "montagem gravável fixa no plano")
        proibidas = {os.path.abspath(p) for p in (raiz, raiz / "state", raiz / "projects" / "outro", Path.home())}
        self.assertFalse(origens & proibidas)
        self.assertEqual(plano["ambiente"]["HOME"], "/tmp")
        self.assertFalse([k for k in plano["ambiente"] if k.startswith(("FUNDACAO_", "PYTHON"))])

    def test_montagem_recusa_raiz_projects_inteira_pasta_com_a_casa_e_ligacao(self):
        ex = carregar("execucao_isolada")
        base = Path(os.path.realpath(pasta_temporaria(self, "g1-montavel-")))
        raiz = base / "raiz"
        (raiz / "state").mkdir(parents=True)
        (raiz / "state" / "state.sqlite").write_bytes(b"")
        (raiz / "projects" / "p" / "copia").mkdir(parents=True)
        ex._montavel(str(raiz / "projects" / "p" / "copia"))  # a cópia dentro do projeto é aceita
        for proibida in (raiz, raiz / "projects"):
            with self.subTest(str(proibida)), self.assertRaises(ex.Recusa) as ctx:
                ex._montavel(str(proibida))
            self.assertIn("fundação", str(ctx.exception))
        with self.assertRaises(ex.Recusa) as ctx:
            ex._montavel(os.path.dirname(os.path.realpath(os.path.expanduser("~"))))
        self.assertIn("pasta pessoal", str(ctx.exception))
        (base / "alvo").mkdir()
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(base / "alvo"), str(base / "ligacao"))
        else:
            (base / "ligacao").symlink_to(base / "alvo", target_is_directory=True)
        with self.assertRaises(ex.Recusa) as ctx:
            ex._montavel(str(base / "ligacao"))
        self.assertIn("ligação", str(ctx.exception))

    def test_programa_fora_do_que_o_sandbox_ve_e_recusado(self):
        ex = carregar("execucao_isolada")
        base = pasta_temporaria(self, "g1-fora-")
        copia, fora = base / "copia", base / "fora"
        copia.mkdir()
        fora.mkdir()
        (fora / "prog.sh").write_text("echo fora\n", encoding="utf-8")
        manifesto = manifesto_da_copia(copia, base / "manifesto-copia.json")
        with self.assertRaises(ex.Recusa) as ctx:
            ex.montar_plano("gravar", [str(fora / "prog.sh")], copia=copia, manifesto=manifesto, cwd=None, entradas=[],
                            gravavel=None, limites=ex.limites(30), variaveis=[], sem_isolamento=None,
                            bwrap="/usr/bin/bwrap")
        self.assertIn("sandbox", str(ctx.exception))


class TestBubblewrapDeVerdade(unittest.TestCase):
    """Só onde o bubblewrap abre um sandbox (Linux/WSL com o preparo do host); no Windows, pulados."""

    def setUp(self):
        ex = carregar("execucao_isolada")
        caminho, motivo = ex.sondar_bwrap()
        if not caminho:
            self.skipTest(f"bubblewrap não abre um sandbox aqui: {motivo}")
        self.base = pasta_temporaria(self, "g1-bwrap-")
        self.raiz = self.base / "raiz"
        self.copia = self.raiz / "projects" / "p" / "copia"
        (self.copia / "entradas").mkdir(parents=True)
        (self.copia / "entradas" / "um.json").write_text("{}", encoding="utf-8")
        self.ensaio = self.raiz / "projects" / "p" / "ensaio"
        self.golden = self.base / "golden.json"

    def gravar(self, script: str, env: dict | None = None) -> dict:
        sonda = self.copia / "sonda.sh"
        sonda.write_text(script, encoding="utf-8")
        manifesto = manifesto_da_copia(self.copia, self.base / "manifesto-copia.json")
        args = ["--entradas", self.copia / "entradas" / "*.json", "--copia", self.copia, "--manifesto", manifesto,
                "--ensaio", self.ensaio, "--", "/bin/sh", sonda, "{entrada}", "{ensaio}"]
        p = cli("plano", *args, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        dados = json.loads(p.stdout)
        self.assertEqual(dados["plano"]["isolamento"], "bwrap")
        g = cli("gravar", "--plano-aprovado", dados["sha256"], "--saida", self.golden, *args, env=env)
        self.assertEqual(g.returncode, 0, g.stdout + g.stderr)
        return json.loads(self.golden.read_text(encoding="utf-8"))["casos"][0]

    def test_bwrap_canarios_rede_ambiente_e_copia_so_leitura(self):
        estado, outro = self.raiz / "state", self.raiz / "projects" / "outro"
        for pasta, texto in ((estado, "CANARIO-G1-STATE"), (outro, "CANARIO-G1-OUTRO")):
            pasta.mkdir(parents=True)
            (pasta / "canario.txt").write_text(texto, encoding="utf-8")
        script = (f'cat "{estado}/canario.txt" 2>/dev/null\n'
                  f'cat "{outro}/canario.txt" 2>/dev/null\n'
                  f'test -e "{Path.home()}" && echo CASA-REAL-VISIVEL\n'
                  "echo INTERFACES $(tail -n +3 /proc/net/dev | cut -d: -f1 | tr -d ' ')\n"
                  "env\n"
                  f'(echo x > "{self.copia}/novo.txt") 2>/dev/null && echo COPIA-GRAVAVEL\n'
                  'echo y > "$2/ok.txt" && echo ENSAIO-GRAVAVEL\n'
                  "exit 0\n")
        env = {**ENV, "FUNDACAO_PRINCIPAL": "canario-identidade-g1", "ANTHROPIC_API_KEY": "canario-chave-de-api-g1"}
        caso = self.gravar(script, env)
        saida = caso["stdout"]
        for proibido in ("CANARIO-G1-STATE", "CANARIO-G1-OUTRO", "CASA-REAL-VISIVEL", "COPIA-GRAVAVEL",
                         "canario-identidade-g1", "canario-chave-de-api-g1", "FUNDACAO_", "ANTHROPIC_"):
            self.assertNotIn(proibido, saida)
        self.assertIn("INTERFACES lo\n", saida, "rede além do lo próprio do sandbox")
        self.assertIn("HOME=/tmp", saida)
        self.assertIn("ENSAIO-GRAVAVEL", saida)
        self.assertFalse((self.copia / "novo.txt").exists())
        self.assertIn("ok.txt", caso["efeitos"]["escritos"])

    def test_bwrap_descendente_destacado_morre_com_o_sandbox(self):
        script = ('setsid sh -c \'echo iniciou > "$1/iniciou"; sleep 2; echo atrasado > "$1/marca"\' sh "$2" &\n'
                  'while [ ! -e "$2/iniciou" ]; do sleep 0.1; done\n'
                  "exit 0\n")
        caso = self.gravar(script)
        self.assertEqual(caso["codigo"], 0, caso["stderr"])
        time.sleep(3.5)
        pasta_caso = self.ensaio / "caso-000"
        self.assertTrue((pasta_caso / "iniciou").exists(), "o descendente nem começou")
        self.assertFalse((pasta_caso / "marca").exists(), "descendente sobreviveu ao fim do sandbox")


if __name__ == "__main__":
    unittest.main()
