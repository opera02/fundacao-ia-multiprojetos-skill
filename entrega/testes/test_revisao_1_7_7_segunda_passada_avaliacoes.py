"""Segunda passada da revisão de segurança da 1.7.7 nas avaliações: limites do R177-VAL-06 a 09 e o R177B-A-03.

- R177-VAL-06 e 07 (limite): a pasta-mãe do repositório saía das zonas do gabarito, ao contrário do §9 do
  AVALIACOES.md, e `--area` (ou a pasta cega do `cegar.py`) ao lado do repositório era aceita. Agora o repositório
  conta como nome do gabarito ao lado, qualquer que seja o nome dele: área ou pasta cega até três pastas abaixo da
  mãe dele é recusada.
- R177-VAL-08 (limite): uma partida dava lastro a duas execuções se o `id` do prompts.json e o rastro fossem copiados
  (fraude deliberada do operador). Agora a partida só dá lastro à execução amarrada a ela no `iniciar` e, numa
  passada do `cegar` ou do `resumo_k`, a uma execução só; a outra fica "sem partida".
- R177-VAL-09 (sem impacto, correção barata): `nao_tabelas` só reconhecia a tabela virtual pelo texto "CREATE
  VIRTUAL" com um espaço; o SQLite grava esse texto normalizado, mas um esquema escrito à mão (`writable_schema`)
  com dois espaços, quebra de linha ou comentário entre as palavras carrega a mesma tabela virtual e passava.
- R177B-A-03: a identidade do preparo guardava a `.env` da fixture legado-squad só pelo nome ("excluído sem
  leitura"), mas o valor dela é o que o verificador procura na E2 e na E3 (`SEGREDOS`) e o preparo copia a fixture
  para os ambientes: trocado o valor depois do `abrir`, nada recusava, e uma execução que vazasse o valor novo saía
  "sem vazamento". Agora as fixtures entram pelo conteúdo; o valor não aparece no livro nem nas mensagens.
Tudo em pastas temporárias, com uma cópia da árvore e dados fictícios; nada aqui chama modelo, `claude`, `codex` nem
rede.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENTREGA = Path(__file__).resolve().parents[1]
SKILL = ENTREGA.parent / "fundacao-ia-multiprojetos"
EVALS = SKILL / "evals"
LIVRO = EVALS / "livro_avaliacoes.py"
ESPERADO = "claude-sonnet-5-5"
REPO = "repositorio-ficticio"  # nome qualquer: nenhum padrão de nome do gabarito o reconhece


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


def copiar_arvore(destino: Path) -> Path:
    """Cópia da árvore da skill em `destino`; devolve a pasta da skill copiada."""
    copia = destino / "fundacao-ia-multiprojetos"
    shutil.copytree(SKILL, copia, ignore=shutil.ignore_patterns("__pycache__"))
    return copia


def _gravar(caminho: Path, dados) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


def bancada_e11(it: Path, braco: str) -> Path:
    """Bancada com a E11 (segurança: só passa com pass^k) de um braço e a run-1 com uma saída fictícia (sem
    ambiente: só o que o `cegar` e o `resumo_k` leem); devolve a pasta da avaliação."""
    e11 = next(e for e in json.loads((EVALS / "evals.json").read_text(encoding="utf-8"))["evals"] if e["id"] == 11)
    edir = it / "eval-11-auditoria-somente-leitura"
    _gravar(edir / "eval_metadata.json", {"eval_id": 11, "assertions": e11["expectations"], "configs": [braco],
                                          "seguranca": True})
    (edir / braco / "run-1" / "outputs").mkdir(parents=True)
    (edir / braco / "run-1" / "outputs" / "RELATO.md").write_text("Relatório fictício\n", encoding="utf-8")
    return edir


def amarrar_run_1(edir: Path, livro: Path, braco: str, rotulo: str) -> dict:
    """Uma partida amarrada à run-1 (pedido com id neutro, isolamento.json com a skill do livro e ambiente vazio),
    fechada com o rastro dela; devolve o pedido."""
    it = edir.parent
    ident = hashlib.sha256(f"11|{braco}|1".encode()).hexdigest()[:10]
    amb = it.parent.parent / "area-ficticia" / ident / "ambiente"
    amb.mkdir(parents=True)
    pedido = {"id": ident, "avaliacao": 11, "braco": braco, "ambiente": amb.as_posix(), "skill": None,
              "skill_sha256": None, "registro": (edir / braco / "run-1").as_posix()}
    vazio = hashlib.sha256(json.dumps([]).encode()).hexdigest()  # impressão de um ambiente vazio
    _gravar(it / "prompts.json", {f"11/{braco}/run-1": pedido})
    _gravar(it / "isolamento.json", {"skills": {braco: "sem_skill"},
                                     "ambientes": {"11/run-1": {"bracos": {braco: vazio}}}})
    r = rodar(LIVRO, "iniciar", "--livro", livro, "--rotulo", rotulo, "--avaliacao", 11, "--braco", braco,
              "--iteracao", it, "--execucao", ident)
    assert r.returncode == 0, r.stdout + r.stderr
    eventos = [{"type": "system", "subtype": "init", "model": ESPERADO},
               {"type": "assistant", "message": {"model": ESPERADO, "content": [{"type": "text", "text": "ok"}]}},
               {"type": "result", "subtype": "success", "is_error": False}]
    Path(pedido["registro"], "trace.jsonl").write_text("\n".join(map(json.dumps, eventos)) + "\n", encoding="utf-8")
    r = rodar(LIVRO, "fechar", "--livro", livro, "--rotulo", rotulo, "--estado", "concluida")  # o rastro amarrado
    assert r.returncode == 0, r.stdout + r.stderr
    return pedido


class TestR177Val06RepositorioAoLado(unittest.TestCase):
    """Árvore copiada para `<pai>/repositorio-ficticio/` com `entrega/` (o que faz da pasta-mãe da skill o
    repositório) e workspace longe dele: área e pasta cega ao lado do repositório são recusadas; longe dele, o
    repositório não é acusado."""

    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory(prefix="r177b-06-")
        cls.t = Path(cls._td.name).resolve()
        cls.pai = cls.t / "pai"
        cls.skill = copiar_arvore(cls.pai / REPO)
        (cls.pai / REPO / "entrega").mkdir()
        cls.ws = cls.t / "w" / "ws"  # o pai do workspace é zona: fica longe do repositório
        cls.iso = _modulo("iso_r177b_06", cls.skill / "evals" / "isolamento.py")

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def test_conferir_vizinhanca_acusa_o_repositorio_ao_lado(self):
        bancada = self.ws / "iteration-1"
        for alvo in (self.pai / "area-irma", self.pai / "a" / "b" / "c"):  # `ls ..` ou `ls ../../..` mostra o repo
            for papel in ("a área do executor", "a pasta cega"):
                with self.subTest(alvo=alvo.relative_to(self.t).as_posix(), papel=papel):
                    problemas = self.iso.conferir_vizinhanca(alvo, bancada, papel=papel)
                    self.assertTrue([p for p in problemas if REPO in p and papel in p], problemas)
        longe = self.iso.conferir_vizinhanca(self.t / "longe" / "area", bancada)
        self.assertEqual([p for p in longe if REPO in p], [], longe)

    def test_preparar_recusa_area_ao_lado_do_repositorio_sem_criar_nada(self):
        area, preparar = self.pai / "area-irma", self.skill / "evals" / "preparar_avaliacoes.py"
        r = rodar(preparar, "--workspace", self.ws, "--so", "1", "--area", area, "--simular")
        self.assertEqual(r.returncode, 3, r.stdout[-800:] + r.stderr[-800:])
        self.assertIn(REPO, json.loads(r.stdout)["recusaria"] or "")
        r = rodar(preparar, "--workspace", self.ws, "--so", "1", "--area", area)
        self.assertEqual(r.returncode, 3, r.stdout[-800:] + r.stderr[-800:])
        self.assertIn(REPO, r.stderr)
        self.assertFalse(self.ws.exists() or area.exists(), "a recusa criou a bancada ou a área")

    def test_cegar_recusa_pasta_cega_ao_lado_do_repositorio(self):
        livro, evals = self.t / "livros" / "l1", self.skill / "evals"
        r = rodar(evals / "livro_avaliacoes.py", "abrir", "--livro", livro, "--autorizacao", "ensaio fictício",
                  "--data", "2026-10-21", "--teto", 1, "--modelo-esperado", ESPERADO, "--braco", "without_skill=")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        (self.ws / "iteration-9").mkdir(parents=True)
        try:
            cega = self.pai / "notas-cegas"
            antes = (livro / "livro.json").read_bytes()
            r = rodar(evals / "cegar.py", "cegar", "--iteracao", self.ws / "iteration-9", "--livro", livro,
                      "--destino", cega)
            self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
            self.assertIn("a pasta cega", r.stderr)
            self.assertIn(REPO, r.stderr)
            self.assertFalse(cega.exists(), "a recusa criou a pasta cega")
            self.assertEqual((livro / "livro.json").read_bytes(), antes, "a recusa gravou no livro")
        finally:
            shutil.rmtree(self.ws, ignore_errors=True)


class TestR177Val08UmaPartidaUmaExecucao(unittest.TestCase):
    """Teto 3 e uma partida só, amarrada à run-1 da E11. Antes, com o id do prompts.json e o rastro da run-1 copiados
    para outra execução, as duas tinham lastro: eram cegadas e contavam no pass^k."""

    def setUp(self):
        td = tempfile.TemporaryDirectory(prefix="r177b-08-")
        self.addCleanup(td.cleanup)
        self.t = Path(td.name).resolve()
        self.it = self.t / "repo" / "ws" / "iteration-1"
        self.edir = bancada_e11(self.it, "base")
        self.livro = self.t / "livros" / "l1"
        r = rodar(LIVRO, "abrir", "--livro", self.livro, "--autorizacao", "ensaio fictício", "--data", "2026-10-21",
                  "--teto", 3, "--modelo-esperado", ESPERADO, "--braco", "base=")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.pedido = amarrar_run_1(self.edir, self.livro, "base", "E11-r1")

    def aprovar(self, *runs: Path) -> None:
        """Notas aprovadas (como se reveladas): só a execução com lastro pode contar."""
        assercoes = json.loads((self.edir / "eval_metadata.json").read_text(encoding="utf-8"))["assertions"]
        for run in runs:
            _gravar(run / "grading.json", {"expectations": [{"text": a, "passed": True, "evidence": "fictícia"}
                                                            for a in assercoes]})

    def cegar(self) -> subprocess.CompletedProcess:
        separada = tempfile.TemporaryDirectory(prefix="r177b-08-cega-")
        self.addCleanup(separada.cleanup)
        return rodar(EVALS / "cegar.py", "cegar", "--iteracao", self.it, "--livro", self.livro, "--destino",
                     Path(separada.name) / "cega")

    def resumo(self) -> dict:
        r = rodar(EVALS / "resumo_k.py", "--iteracao", self.it, "--livro", self.livro)
        self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
        return json.loads(r.stdout)["avaliacoes"]

    def test_id_e_rastro_copiados_para_outras_execucoes_ficam_sem_partida(self):
        runs = [self.edir / "base" / f"run-{k}" for k in (1, 2, 3)]
        pedidos = json.loads((self.it / "prompts.json").read_text(encoding="utf-8"))
        for k, run in ((2, runs[1]), (3, runs[2])):  # a fraude: o mesmo id e o mesmo rastro em outra execução
            shutil.copytree(runs[0] / "outputs", run / "outputs")
            shutil.copyfile(runs[0] / "trace.jsonl", run / "trace.jsonl")
            pedidos[f"11/base/run-{k}"] = {**self.pedido, "registro": run.as_posix()}
        _gravar(self.it / "prompts.json", pedidos)
        antes = (self.livro / "livro.json").read_bytes()
        r = self.cegar()
        self.assertEqual(r.returncode, 3, "uma partida deu lastro a três execuções: " + r.stdout + r.stderr)
        for k in (2, 3):
            self.assertIn(f"11/base/run-{k}: sem partida", r.stderr)
        self.assertNotIn("11/base/run-1:", r.stderr)
        self.assertEqual((self.livro / "livro.json").read_bytes(), antes, "a recusa gravou no livro")
        self.aprovar(*runs)
        linha = self.resumo()[self.edir.name]["bracos"]["base"]
        estados = {run: e["estado"] for run, e in linha["execucoes"].items()}
        self.assertEqual(estados, {"run-1": "aprovada", "run-2": "nao_medida", "run-3": "nao_medida"}, linha)
        self.assertIn("sem partida", linha["execucoes"]["run-3"]["motivo"])
        self.assertEqual((linha["pass^k"], linha["veredito"]), ("nao_medido", "não medida"))

    def test_pasta_da_avaliacao_copiada_nao_ganha_lastro_da_mesma_partida(self):
        """A mesma chave em duas pastas (o eval_id vem do eval_metadata.json): a partida dá lastro a uma só."""
        copia = self.it / "eval-11-copia"
        shutil.copytree(self.edir, copia)
        self.aprovar(self.edir / "base" / "run-1", copia / "base" / "run-1")
        r = self.cegar()
        self.assertEqual(r.returncode, 3, "uma partida deu lastro a duas execuções: " + r.stdout + r.stderr)
        self.assertIn("sem partida", r.stderr)
        avaliacoes = self.resumo()
        self.assertEqual(avaliacoes[self.edir.name]["bracos"]["base"]["execucoes"]["run-1"]["estado"], "aprovada")
        sobra = avaliacoes["eval-11-copia"]["bracos"]["base"]
        self.assertEqual(sobra["execucoes"]["run-1"]["estado"], "nao_medida", sobra)
        self.assertIn("sem partida", sobra["execucoes"]["run-1"]["motivo"])
        self.assertEqual(sobra["veredito"], "não medida")


TABELAS_DO_KIT = ("CREATE TABLE project (project_id TEXT)",
                  "CREATE TABLE acl (subject TEXT, resource TEXT, action TEXT)",
                  "CREATE TABLE run (run_id TEXT, flow_id TEXT, state TEXT)",
                  "CREATE TABLE step (run_id TEXT, step_id TEXT, state TEXT, attempts INT, executions INT)")
VIRTUAIS_DISFARCADAS = ("CREATE  VIRTUAL TABLE event USING fts5(kind)",                # dois espaços (o achado)
                        "CREATE\n\tVIRTUAL TABLE event USING fts5(kind)",              # quebra de linha e tabulação
                        "CREATE/**/VIRTUAL TABLE event USING fts5(kind)",              # comentário de bloco
                        "create -- comentário\nvirtual table event using fts5(kind)")  # comentário de linha


def banco_com_virtual_disfarcada(caminho: Path, texto: str) -> Path:
    """Banco com as tabelas do kit e `event` virtual cujo texto no sqlite_master foi reescrito à mão
    (`writable_schema`): o SQLite carrega a mesma tabela virtual, com outro texto."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(caminho))
    try:
        for comando in (*TABELAS_DO_KIT, "CREATE VIRTUAL TABLE event USING fts5(kind)"):
            con.execute(comando)
        con.execute("PRAGMA writable_schema = ON")
        con.execute("UPDATE sqlite_master SET sql = ? WHERE name = 'event'", (texto,))
        con.commit()
    finally:
        con.close()
    return caminho


class TestR177Val09VirtualComOutroSeparador(unittest.TestCase):
    def test_nao_tabelas_acusa_virtual_com_espacos_ou_comentario_entre_as_palavras(self):
        ba = _modulo("ba_r177b_09", EVALS / "banco_avaliado.py")
        for texto in VIRTUAIS_DISFARCADAS:
            with self.subTest(texto=texto), tempfile.TemporaryDirectory(prefix="r177b-09-") as td:
                db = banco_com_virtual_disfarcada(Path(td) / "state.sqlite", texto)
                with ba.aberto(db) as con:
                    if sqlite3.sqlite_version_info >= (3, 37, 0):  # o SQLite carregou mesmo uma tabela virtual
                        self.assertEqual([t[2] for t in con.execute("PRAGMA table_list") if t[1] == "event"],
                                         ["virtual"])
                    self.assertEqual(ba.nao_tabelas(con, ("project", "event")), ["event (tabela virtual)"])

    def test_banco_da_fundacao_com_event_virtual_disfarcada_nao_e_lido(self):
        ve = _modulo("ve_r177b_09", EVALS / "verificar_execucoes.py")
        with tempfile.TemporaryDirectory(prefix="r177b-09-") as td:
            fund = Path(td) / "fundacao"
            banco_com_virtual_disfarcada(fund / "state" / "state.sqlite", VIRTUAIS_DISFARCADAS[0])
            fatos = ve.banco(fund)
        self.assertIn("event (tabela virtual)", fatos.get("erro_banco", ""), fatos)
        self.assertNotIn("cadeia_eventos", fatos)


class TestR177bA03EnvDaFixtureNaIdentidade(unittest.TestCase):
    """Numa cópia da árvore: a `.env` da fixture trocada depois do `abrir` recusa o `iniciar` e o `preparar --livro`.
    O teste nunca lê o valor de antes: só escreve um novo, fictício, na cópia."""

    def test_valor_da_env_da_fixture_mudado_depois_do_abrir_recusa_sem_mostrar_o_valor(self):
        rel, novo = "evals/fixtures/legado-squad/.env", "valor-ficticio-trocado-depois-do-abrir"
        with tempfile.TemporaryDirectory(prefix="r177b-a03-") as td:
            t = Path(td).resolve()
            evals, livro = copiar_arvore(t / "arvore") / "evals", t / "livro"
            r = rodar(evals / "livro_avaliacoes.py", "abrir", "--livro", livro, "--autorizacao", "ensaio fictício",
                      "--data", "2026-10-21", "--teto", 2, "--modelo-esperado", ESPERADO, "--braco", "without_skill=")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            (evals.parent / rel).write_text(f"CHAVE_FICTICIA={novo}\n", encoding="utf-8")
            iniciar = rodar(evals / "livro_avaliacoes.py", "iniciar", "--livro", livro, "--rotulo", "E2-r1",
                            "--avaliacao", 2, "--braco", "without_skill")
            self.assertEqual(iniciar.returncode, 3,
                             "a .env mudou e o iniciar aceitou: " + iniciar.stdout + iniciar.stderr)
            self.assertIn(rel, iniciar.stderr)
            preparar = rodar(evals / "preparar_avaliacoes.py", "--workspace", t / "ws", "--so", "2", "--livro", livro,
                             "--simular")
            self.assertEqual(preparar.returncode, 3, preparar.stdout[-800:] + preparar.stderr[-800:])
            self.assertIn(rel, preparar.stderr)
            self.assertFalse((t / "ws").exists(), "a recusa criou a bancada")
            texto = (livro / "livro.json").read_text(encoding="utf-8")
            self.assertRegex(json.loads(texto)["identidade"]["scripts"][rel], r"^[0-9a-f]{64}$")
            vistos = texto + "".join(x.stdout + x.stderr for x in (r, iniciar, preparar))
            segredos = _modulo("ve_r177b_a03", EVALS / "verificar_execucoes.py").SEGREDOS
            for valor in (novo, *segredos[2], *segredos[3]):  # o valor procurado na E2 e na E3 e o novo
                self.assertNotIn(valor, vistos, "o valor da .env apareceu no livro ou numa mensagem")


if __name__ == "__main__":
    unittest.main()
