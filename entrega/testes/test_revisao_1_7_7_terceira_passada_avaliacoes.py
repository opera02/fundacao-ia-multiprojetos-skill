r"""Terceira passada da revisão de segurança da 1.7.7 nas avaliações: R177C-B-06 a 08 e R177C-T-01.

- R177C-B-06: o lastro da partida ficava preso à chave da execução (`11/base/run-1`) e à ordem da passada, não à
  pasta gravada no `iniciar`: com a `iteration-1` copiada como `iteration-2`, o `cegar` e o `resumo_k` aprovavam as
  duas com uma partida só; e a cópia da pasta da avaliação que ordena antes da original tomava o lastro dela no
  `resumo_k`. Agora o `iniciar` exige que o `registro` do pedido seja a pasta da execução na bancada, e a partida só
  dá lastro ao rastro dessa pasta.
- R177C-B-07: a identidade do preparo descrevia as fixtures pela política do manifesto, que ignora `.venv`, `venv`,
  `node_modules`, `__pycache__`..., e não segue ligação (fica só o nome); o preparo as copiava com `copytree`, que
  copia tudo e segue a junção. Um arquivo novo numa dessas pastas, ou o outro lado de uma junção trocado depois do
  `abrir`, entrava no ambiente com o `iniciar` e o `preparar` saindo 0. Agora a identidade cobre tudo o que a cópia
  leva, e ligação nas fixtures é recusada no cálculo da identidade e na cópia.
- R177C-B-08: `isolamento.conferir_vizinhanca` comparava os caminhos pelo texto depois do `resolve()`, que mantém o
  prefixo de dispositivo do Windows (`\\?\`): `--area \\?\<mãe do repositório>\irma` passava (sem o prefixo, era
  recusada), e também a área dentro do repositório ou na bancada; o mesmo valia para a pasta cega do `cegar.py`.
  Agora a comparação tira o prefixo e confere o lugar pela identidade no sistema de arquivos (pega também
  `\\localhost\C$\...`). No rastro do executor, o `?` do prefixo contava como curinga na raiz: todo caminho com ele,
  até o do próprio ambiente, contaminava; agora conta o lugar que o caminho designa.
- R177C-T-01 (robustez dos testes, sem mudar a regra): uma pasta `<skill>-workspace` (o skill-creator cria),
  `eval-N`, `iteration-N` ou `evals` na pasta temporária da máquina, em %LOCALAPPDATA% ou em AppData fazia 11 testes
  das avaliações falharem e 4 classes nem montarem: a área padrão e as pastas dos testes ficavam na pasta temporária
  do sistema, e a vizinhança do gabarito confere as três pastas acima delas. A regra está certa (o executor veria o
  workspace com `ls ..`); cada módulo afetado liga agora uma pasta temporária própria (base_temporaria.py).
Tudo em pastas temporárias, com uma cópia da árvore e dados fictícios; nada aqui chama modelo, `claude`, `codex` nem
rede.
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

ENTREGA = Path(__file__).resolve().parents[1]
SKILL = ENTREGA.parent / "fundacao-ia-multiprojetos"
EVALS = SKILL / "evals"
ESPERADO = "claude-sonnet-5-5"
REPO = "repositorio-ficticio"  # nome qualquer: nenhum padrão de nome do gabarito o reconhece
PREFIXO = "\\\\?\\"  # prefixo de dispositivo do Windows (caminho longo)


def rodar(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=900)


def _modulo(nome: str, caminho: Path):
    spec = importlib.util.spec_from_file_location(nome, caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def setUpModule():
    """Pasta temporária própria (base_temporaria.py; revisão de segurança da 1.7.7, terceira passada, R177C-T-01): a
    área do executor e as pastas dos testes não dependem do que há na pasta temporária da máquina."""
    unittest.addModuleCleanup(_modulo("base_temporaria", Path(__file__).with_name("base_temporaria.py")).ligar())


# Ajudantes da segunda passada (cópia da árvore, bancada da E11 e partida amarrada à run-1), lidos pelo caminho.
T2 = _modulo("t2_r177c", Path(__file__).with_name("test_revisao_1_7_7_segunda_passada_avaliacoes.py"))


def outros_nomes(alvo: Path) -> dict[str, str]:
    r"""Nomes do mesmo lugar que `alvo`: com o prefixo `\\?\` e, se o compartilhamento administrativo da unidade
    responde neste Windows, por ele (`\\localhost\C$\...`, também com `\\?\UNC\`)."""
    nomes = {"prefixo": PREFIXO + str(alvo)}
    unidade = alvo.drive.rstrip(":")
    if len(unidade) == 1 and Path(f"\\\\localhost\\{unidade}$\\").is_dir():
        rede = f"\\\\localhost\\{unidade}$" + str(alvo)[2:]
        nomes |= {"compartilhamento": rede, "prefixo de rede": PREFIXO + "UNC\\" + rede[2:]}
    return nomes


@unittest.skipUnless(os.name == "nt", "prefixo de dispositivo e compartilhamento administrativo são do Windows")
class TestR177CB08AreaPorOutroNome(unittest.TestCase):
    """Árvore copiada para `<pai>/repositorio-ficticio/` (com `entrega/`, o que faz da pasta-mãe da skill o
    repositório) e workspace longe dele: a área e a pasta cega escritas por outro nome do mesmo lugar são recusadas
    como pelo nome comum."""

    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory(prefix="r177c-08-")
        cls.t = Path(cls._td.name).resolve()
        cls.pai = cls.t / "pai"
        cls.skill = T2.copiar_arvore(cls.pai / REPO)
        (cls.pai / REPO / "entrega").mkdir()
        cls.ws = cls.t / "w" / "ws"  # o pai do workspace é zona: fica longe do repositório
        cls.iso = _modulo("iso_r177c_08", cls.skill / "evals" / "isolamento.py")

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def test_conferir_vizinhanca_recusa_a_area_por_outro_nome_como_pelo_nome_comum(self):
        bancada = self.ws / "iteration-1"  # como no primeiro preparo: a bancada ainda não existe
        casos = {"ao lado do repositório": (self.pai / "area-irma", REPO),
                 "dentro do repositório": (self.pai / REPO / "area", REPO),
                 "na bancada": (bancada / "area", "iteration-1")}
        for caso, (alvo, motivo) in casos.items():
            comum = self.iso.conferir_vizinhanca(alvo, bancada)
            self.assertTrue([p for p in comum if motivo in p], comum)  # pelo nome comum, já era recusada
            for forma, nome in outros_nomes(alvo).items():
                with self.subTest(caso=caso, forma=forma):
                    problemas = self.iso.conferir_vizinhanca(nome, bancada)
                    self.assertTrue([p for p in problemas if motivo in p], f"{nome} passou: {problemas}")
        self.assertFalse(self.ws.exists(), "a conferência criou a bancada")

    def test_preparar_recusa_area_com_prefixo_ao_lado_do_repositorio_sem_criar_nada(self):
        area, preparar = self.pai / "area-irma", self.skill / "evals" / "preparar_avaliacoes.py"
        r = rodar(preparar, "--workspace", self.ws, "--so", "1", "--area", PREFIXO + str(area), "--simular")
        self.assertEqual(r.returncode, 3, r.stdout[-800:] + r.stderr[-800:])
        self.assertIn(REPO, json.loads(r.stdout)["recusaria"] or "")
        r = rodar(preparar, "--workspace", self.ws, "--so", "1", "--area", PREFIXO + str(area))
        self.assertEqual(r.returncode, 3, r.stdout[-800:] + r.stderr[-800:])
        self.assertIn(REPO, r.stderr)
        self.assertFalse(self.ws.exists() or area.exists(), "a recusa criou a bancada ou a área")

    def test_cegar_recusa_pasta_cega_com_prefixo_ao_lado_do_repositorio(self):
        livro, evals = self.t / "livros" / "l1", self.skill / "evals"
        r = rodar(evals / "livro_avaliacoes.py", "abrir", "--livro", livro, "--autorizacao", "ensaio fictício",
                  "--data", "2026-10-22", "--teto", 1, "--modelo-esperado", ESPERADO, "--braco", "without_skill=")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        (self.ws / "iteration-9").mkdir(parents=True)
        try:
            cega = self.pai / "notas-cegas"
            antes = (livro / "livro.json").read_bytes()
            r = rodar(evals / "cegar.py", "cegar", "--iteracao", self.ws / "iteration-9", "--livro", livro,
                      "--destino", PREFIXO + str(cega))
            self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
            self.assertIn("a pasta cega", r.stderr)
            self.assertIn(REPO, r.stderr)
            self.assertFalse(cega.exists(), "a recusa criou a pasta cega")
            self.assertEqual((livro / "livro.json").read_bytes(), antes, "a recusa gravou no livro")
        finally:
            shutil.rmtree(self.ws, ignore_errors=True)


class TestR177CB08RastroComPrefixo(unittest.TestCase):
    """No rastro, o caminho com o prefixo de dispositivo conta pelo lugar que designa: a leitura de outra raiz do
    gabarito (a árvore da skill com evals/) contamina e a do próprio ambiente, não. Antes, o `?` do prefixo contava
    como curinga na raiz e todo caminho com ele contaminava; com o volume ou o GLOBALROOT depois, continua contando.
    O prefixo só existe no Windows: no Linux o texto não designa lugar, e a CI pública do Ubuntu reprovou o caso do
    próprio ambiente (1.7.8); lá roda só o caso sem prefixo."""

    def test_caminho_sem_prefixo_da_outra_raiz_contamina(self):
        self._conferir(lambda dev, execucao: ((str(dev / "SKILL.md"), "contaminada"),))

    @unittest.skipUnless(os.name == "nt", "o prefixo de dispositivo do Windows só designa lugar no Windows")
    def test_caminho_com_prefixo_conta_pelo_lugar_que_designa(self):
        self._conferir(lambda dev, execucao: (
            (PREFIXO + str(dev / "SKILL.md"), "contaminada"),
            (PREFIXO + str(execucao / "ambiente" / "RETOMADA.md"), "sem_acesso_no_rastro"),
            (PREFIXO + "GLOBALROOT\\Device\\HarddiskVolume3\\x.json", "contaminada")))

    def _conferir(self, casos):
        ve = _modulo("ve_r177c_08", EVALS / "verificar_execucoes.py")
        with tempfile.TemporaryDirectory(prefix="r177c-08-rastro-") as td:
            t = Path(td).resolve()
            it = t / "ws" / "iteration-1"
            (it / "eval-10-retomada-desatualizada" / "with_skill" / "run-1").mkdir(parents=True)
            execucao = t / "trabalho-x" / "a1b2c3d4e5"
            for sub in ("ambiente", "saidas"):
                (execucao / sub).mkdir(parents=True)
            dev = t / "repo" / "arvore-de-desenvolvimento"  # sem nome do gabarito no caminho
            (dev / "evals").mkdir(parents=True)
            rastro = t / "rastro"
            rastro.mkdir()
            for caminho, esperado in casos(dev, execucao):
                with self.subTest(caminho=caminho):
                    uso = {"type": "assistant", "message": {"content": [
                        {"type": "tool_use", "id": "u1", "name": "Read", "input": {"file_path": caminho}}]}}
                    (rastro / "trace.jsonl").write_text(json.dumps(uso) + "\n", encoding="utf-8")
                    r = ve.acesso_ao_gabarito(rastro / "trace.jsonl", it, ve.nomes_do_gabarito(it),
                                              (execucao / "ambiente", execucao / "saidas", execucao),
                                              area=execucao.parent, protegidas=(dev,))
                    self.assertEqual(r["estado"], esperado, r)


class TestR177CB06LastroDaPastaGravadaNoIniciar(unittest.TestCase):
    """Uma partida, amarrada à run-1 da E11 (segurança: só passa com pass^k) da iteration-1. Antes, a cópia da
    bancada inteira (`iteration-1` como `iteration-2`) era cegada e aprovada com a mesma partida, e a cópia da pasta
    da avaliação que ordena antes da original tomava o lastro dela no `resumo_k`."""

    def setUp(self):
        td = tempfile.TemporaryDirectory(prefix="r177c-06-")
        self.addCleanup(td.cleanup)
        self.t = Path(td.name).resolve()
        self.it = self.t / "repo" / "ws" / "iteration-1"
        self.edir = T2.bancada_e11(self.it, "base")
        self.livro = self.t / "livros" / "l1"
        r = rodar(T2.LIVRO, "abrir", "--livro", self.livro, "--autorizacao", "ensaio fictício", "--data", "2026-10-22",
                  "--teto", 2, "--modelo-esperado", ESPERADO, "--braco", "base=")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.pedido = T2.amarrar_run_1(self.edir, self.livro, "base", "E11-r1")

    def aprovar(self, *runs: Path) -> None:
        """Notas aprovadas (como se reveladas): só a execução com lastro pode contar."""
        assercoes = json.loads((self.edir / "eval_metadata.json").read_text(encoding="utf-8"))["assertions"]
        for run in runs:
            T2._gravar(run / "grading.json", {"expectations": [{"text": a, "passed": True, "evidence": "fictícia"}
                                                               for a in assercoes]})

    def cegar(self, it: Path) -> subprocess.CompletedProcess:
        separada = tempfile.TemporaryDirectory(prefix="r177c-06-cega-")
        self.addCleanup(separada.cleanup)
        return rodar(EVALS / "cegar.py", "cegar", "--iteracao", it, "--livro", self.livro, "--destino",
                     Path(separada.name) / "cega")

    def resumo(self, it: Path) -> dict:
        r = rodar(EVALS / "resumo_k.py", "--iteracao", it, "--livro", self.livro)
        self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
        return json.loads(r.stdout)["avaliacoes"]

    def test_bancada_copiada_nao_ganha_lastro_da_partida_da_original(self):
        copia = self.it.parent / "iteration-2"
        shutil.copytree(self.it, copia)  # prompts.json, isolamento.json, rastro e saídas: tudo igual
        antes = (self.livro / "livro.json").read_bytes()
        r = self.cegar(copia)
        self.assertEqual(r.returncode, 3, "a cópia da bancada foi cegada com a partida da original: " + r.stdout)
        self.assertIn("11/base/run-1: sem partida", r.stderr)
        self.assertEqual((self.livro / "livro.json").read_bytes(), antes, "a recusa gravou no livro")
        run = Path(self.edir.name) / "base" / "run-1"
        self.aprovar(self.it / run, copia / run)
        linha = self.resumo(copia)[self.edir.name]["bracos"]["base"]
        self.assertEqual((linha["execucoes"]["run-1"]["estado"], linha["veredito"]), ("nao_medida", "não medida"))
        self.assertIn("sem partida", linha["execucoes"]["run-1"]["motivo"])
        original = self.resumo(self.it)[self.edir.name]["bracos"]["base"]
        self.assertEqual((original["execucoes"]["run-1"]["estado"], original["veredito"]), ("aprovada", "passou"))
        self.assertEqual(self.cegar(self.it).returncode, 0, "a original perdeu o lastro")

    def test_copia_da_pasta_da_avaliacao_que_ordena_antes_nao_toma_o_lastro_da_original(self):
        copia = self.it / "eval-11-a"  # ordena antes de eval-11-auditoria-somente-leitura
        shutil.copytree(self.edir, copia)
        shutil.rmtree(copia / "base" / "run-1" / "outputs")  # sem saídas: o cegar não a lê, o resumo_k sim
        self.aprovar(self.edir / "base" / "run-1", copia / "base" / "run-1")
        avaliacoes = self.resumo(self.it)
        self.assertEqual(avaliacoes[self.edir.name]["bracos"]["base"]["execucoes"]["run-1"]["estado"], "aprovada",
                         avaliacoes)
        sobra = avaliacoes["eval-11-a"]["bracos"]["base"]
        self.assertEqual((sobra["execucoes"]["run-1"]["estado"], sobra["veredito"]), ("nao_medida", "não medida"))
        self.assertIn("sem partida", sobra["execucoes"]["run-1"]["motivo"])

    def test_iniciar_recusa_registro_que_nao_e_a_pasta_da_execucao_na_bancada(self):
        outra = self.it.parent / "iteration-2" / self.edir.name / "base" / "run-1"
        vizinha = self.edir / "base" / "run-2"
        fora = self.t / "fora" / self.edir.name / "base" / "run-1"
        for pasta in (outra, vizinha, fora):
            pasta.mkdir(parents=True)
        prompts = self.it / "prompts.json"
        pedidos = json.loads(prompts.read_text(encoding="utf-8"))
        chave = "11/base/run-1"
        for i, registro in enumerate((outra, vizinha, fora, None)):
            with self.subTest(registro=registro):
                T2._gravar(prompts, {chave: {**pedidos[chave], "registro": registro.as_posix() if registro else None}})
                antes = (self.livro / "livro.json").read_bytes()
                r = rodar(T2.LIVRO, "iniciar", "--livro", self.livro, "--rotulo", f"E11-x{i}", "--avaliacao", 11,
                          "--braco", "base", "--iteracao", self.it, "--execucao", self.pedido["id"])
                self.assertEqual(r.returncode, 3, "partida amarrada a outra pasta: " + r.stdout + r.stderr)
                self.assertIn("registro", r.stderr)
                self.assertEqual((self.livro / "livro.json").read_bytes(), antes, "a recusa gravou no livro")
        T2._gravar(prompts, pedidos)  # o registro do preparo: a pasta da execução na bancada
        r = rodar(T2.LIVRO, "iniciar", "--livro", self.livro, "--rotulo", "E11-r2", "--avaliacao", 11, "--braco",
                  "base", "--iteracao", self.it, "--execucao", self.pedido["id"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


def ligar_pasta(destino: Path, atalho: Path, caso: unittest.TestCase) -> None:
    """Junção (Windows) ou link simbólico de pasta em `atalho`, apontando para `destino`; pula o teste se o
    sistema não deixar criar."""
    try:
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(destino), str(atalho))
        else:
            os.symlink(destino, atalho, target_is_directory=True)
    except (OSError, ImportError, AttributeError) as exc:
        caso.skipTest(f"ligação de pasta indisponível neste ambiente: {exc}")


def desligar_pasta(atalho: Path) -> None:
    """Desfaz a ligação sem tocar no outro lado."""
    if os.name == "nt":
        os.rmdir(atalho)
    else:
        os.unlink(atalho)


class TestR177CB07FixturesInteirasNaIdentidade(unittest.TestCase):
    """Numa cópia da árvore: o preparo copia das fixtures o que a identidade descreve, e nada além. Antes, um arquivo
    novo numa pasta que o manifesto ignora (`.venv`, `venv`, `node_modules`, `__pycache__`) e o outro lado de uma
    junção já presente no `abrir` entravam no ambiente com o `iniciar` e o `preparar` saindo 0."""

    def setUp(self):
        td = tempfile.TemporaryDirectory(prefix="r177c-07-")
        self.addCleanup(td.cleanup)
        self.t = Path(td.name).resolve()
        self.evals = T2.copiar_arvore(self.t / "arvore") / "evals"
        self.fixture = self.evals / "fixtures" / "legado-squad"
        self.livro = self.t / "livro"

    def abrir(self) -> subprocess.CompletedProcess:
        return rodar(self.evals / "livro_avaliacoes.py", "abrir", "--livro", self.livro, "--autorizacao",
                     "ensaio fictício", "--data", "2026-10-22", "--teto", 2, "--modelo-esperado", ESPERADO,
                     "--braco", "without_skill=")

    def iniciar(self, rotulo: str) -> subprocess.CompletedProcess:
        return rodar(self.evals / "livro_avaliacoes.py", "iniciar", "--livro", self.livro, "--rotulo", rotulo,
                     "--avaliacao", 2, "--braco", "without_skill")

    def test_arquivo_novo_onde_o_manifesto_nao_olha_recusa_iniciar_e_preparar(self):
        self.assertEqual(self.abrir().returncode, 0)
        plantados = ("node_modules/plantado.txt", ".venv/LEIA-ISTO.md", "__pycache__/plantado.txt", "venv/x.md",
                     "pasta-vazia/")
        for i, rel in enumerate(plantados):
            with self.subTest(rel=rel):
                alvo = self.fixture / rel
                alvo.parent.mkdir(parents=True, exist_ok=True)
                if rel.endswith("/"):
                    alvo.mkdir()
                else:
                    alvo.write_text("Instrução plantada depois do abrir (fictícia).\n", encoding="utf-8")
                try:
                    antes = (self.livro / "livro.json").read_bytes()
                    r = self.iniciar(f"E2-{i}")
                    self.assertEqual(r.returncode, 3, f"{rel} entrou depois do abrir e o iniciar aceitou: {r.stderr}")
                    self.assertIn("evals/fixtures/legado-squad/" + rel.split("/")[0], r.stderr)
                    self.assertEqual((self.livro / "livro.json").read_bytes(), antes, "a recusa gravou no livro")
                    ws = self.t / f"ws-{i}"
                    p = rodar(self.evals / "preparar_avaliacoes.py", "--workspace", ws, "--so", "2", "--livro",
                              self.livro, "--simular")
                    self.assertEqual(p.returncode, 3, p.stdout[-800:] + p.stderr[-800:])
                    self.assertFalse(ws.exists(), "a recusa criou a bancada")
                finally:
                    shutil.rmtree(self.fixture / rel.split("/")[0])
        self.assertEqual(self.iniciar("E2-ok").returncode, 0, "sem nada plantado, o iniciar volta a aceitar")

    def test_juncao_nas_fixtures_recusa_abrir_e_preparar_sem_criar_nada(self):
        fora = self.t / "fora"
        fora.mkdir()
        (fora / "notas.md").write_text("versão 1 (fictícia)\n", encoding="utf-8")
        juncao = self.fixture / "ext"
        ligar_pasta(fora, juncao, self)
        ws = self.t / "ws"
        try:
            r = self.abrir()
            self.assertEqual(r.returncode, 3, "junção nas fixtures e o abrir aceitou: " + r.stdout + r.stderr)
            self.assertIn("evals/fixtures/legado-squad/ext", r.stderr)
            self.assertFalse((self.livro / "livro.json").exists(), "a recusa abriu o livro")
            p = rodar(self.evals / "preparar_avaliacoes.py", "--workspace", ws, "--so", "2")  # sem livro: a cópia
            self.assertEqual(p.returncode, 3, p.stdout[-800:] + p.stderr[-800:])
            self.assertIn("evals/fixtures/legado-squad/ext", p.stderr)
            self.assertFalse(ws.exists(), "a recusa criou a bancada")
        finally:
            desligar_pasta(juncao)
            estado = ws / "iteration-1" / "isolamento.json"
            if estado.is_file():  # antes da correção, o preparo criava a área na pasta temporária do sistema
                shutil.rmtree(json.loads(estado.read_text(encoding="utf-8"))["area"], ignore_errors=True)

    def test_copia_da_fixture_recusa_ligacao_e_leva_o_que_a_identidade_descreve(self):
        iso = _modulo("iso_r177c_07", self.evals / "isolamento.py")
        (self.fixture / ".venv").mkdir()
        (self.fixture / ".venv" / "x.md").write_text("fictício\n", encoding="utf-8")
        livro = _modulo("livro_r177c_07", self.evals / "livro_avaliacoes.py")
        identidade = livro.identidade_das_fixtures()
        destino = self.t / "copia" / "origem"
        iso.copiar_fixture(self.fixture, destino)
        copiado = {p.relative_to(destino).as_posix() + ("/" if p.is_dir() else "") for p in destino.rglob("*")}
        prefixo = "evals/fixtures/legado-squad/"
        self.assertEqual(copiado, {k[len(prefixo):] for k in identidade if k.startswith(prefixo) and k != prefixo})
        self.assertIn(".venv/x.md", copiado)
        fora = self.t / "fora"
        fora.mkdir()
        ligar_pasta(fora, self.fixture / "ext", self)
        try:
            with self.assertRaisesRegex(RuntimeError, "ligação"):
                iso.copiar_fixture(self.fixture, self.t / "copia2" / "origem")
            self.assertFalse((self.t / "copia2").exists(), "a recusa copiou alguma coisa")
        finally:
            desligar_pasta(self.fixture / "ext")


class TestR177CT01TestesIndependentesDaMaquina(unittest.TestCase):
    """Pasta temporária da máquina com `zz-workspace` (como o que o skill-creator deixa), `eval-3` em %LOCALAPPDATA% e
    `evals` em AppData. A regra continua recusando a área padrão ali; os testes que punham a área ou a pasta cega na
    pasta temporária passam mesmo assim, porque cada módulo liga a pasta própria (base_temporaria.py). Antes, 11
    testes falhavam e 4 classes nem montavam."""

    REPRESENTATIVOS = ("test_revisao_1_7_7_gabarito_e_cegas.TestR177Val06AreaForaDoRepositorio."
                       "test_area_padrao_fica_fora_do_repositorio_e_do_pai_do_workspace",
                       "test_revisao_1_7_7_segunda_passada_avaliacoes.TestR177Val08UmaPartidaUmaExecucao."
                       "test_pasta_da_avaliacao_copiada_nao_ganha_lastro_da_mesma_partida")

    def test_nomes_do_gabarito_na_pasta_temporaria_da_maquina_nao_derrubam_os_testes(self):
        with tempfile.TemporaryDirectory(prefix="t01-") as td, tempfile.TemporaryDirectory(prefix="t01-ws-") as ws:
            appdata = Path(td).resolve() / "AppData"
            temp = appdata / "Local" / "Temp"
            for suja in (temp / "zz-workspace", appdata / "Local" / "eval-3", appdata / "evals"):
                suja.mkdir(parents=True)
            ambiente = {**os.environ, **{nome: str(temp) for nome in ("TMPDIR", "TEMP", "TMP")}}
            r = subprocess.run([sys.executable, "-B", str(EVALS / "preparar_avaliacoes.py"), "--workspace",
                                str(Path(ws) / "ws"), "--so", "1", "--simular"], env=ambiente, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=900)
            self.assertEqual(r.returncode, 3, "a regra afrouxou: " + r.stdout[-800:] + r.stderr[-800:])
            recusa = json.loads(r.stdout)["recusaria"]
            for nome in ("zz-workspace", "eval-3", "evals"):
                self.assertIn(f"nomes do gabarito: {nome}", recusa)
            r = subprocess.run([sys.executable, "-B", "-m", "unittest", *self.REPRESENTATIVOS],
                               cwd=str(Path(__file__).parent), env=ambiente, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=900)
            self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-3000:])
            self.assertRegex(r.stderr, r"Ran 2 tests[\s\S]*\nOK")


if __name__ == "__main__":
    unittest.main()
