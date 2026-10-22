"""Revisão de segurança da 1.7.7 nas avaliações: livro-caixa amarrado às execuções (R177-VAL-08) e SQL limitado no
verificador (R177-VAL-09).

R177-VAL-08 — o livro não amarrava partidas a execuções nem conferia o modelo que respondeu: com teto 1 e uma
partida, três execuções foram cegadas, reveladas e contadas como "passou"; uma transcrição com o `init` do modelo
esperado e respostas de outro passou no `conferir`; a identidade da rodada não incluía `cegar.py`,
`livro_avaliacoes.py`, `medidas_do_rastro.py`, `scripts/manifesto.py`, `run_cenarios.py` nem `evals/fixtures/`; a
cópia da skill na área não era reconferida depois do preparo. Agora a partida grava o id neutro da execução e o
SHA-256 do rastro; `cegar` recusa e `resumo_k` marca execução sem partida fechada que confira; o `conferir` acusa
modelo diferente nas respostas e no `result`; a identidade cobre o preparo inteiro; a cópia da skill é conferida
ao iniciar e ao fechar.
R177-VAL-09 — o verificador executava SQL de um banco do ambiente avaliado sem limite: com `event` plantado como
visão que não termina, o `fatos_backups` (E13) e o `banco()` travavam (mais de 20 s). Agora o banco é aberto
somente leitura, com `trusted_schema=OFF` e `query_only`, as tabelas lidas têm de ser tabelas comuns no
sqlite_master (nunca visão nem tabela virtual) e cada banco tem tempo limite (`set_progress_handler`).
Tudo em pastas temporárias e com dados fictícios; nada aqui chama modelo, `claude`, `codex` nem rede.
"""

from __future__ import annotations

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
VERIFICADOR = EVALS / "verificar_execucoes.py"
LIVRO = EVALS / "livro_avaliacoes.py"
ESPERADO = "claude-sonnet-5-5"
PRAZO_S = 30  # o achado viu mais de 20 s; com o limite por banco, a coleta termina em poucos segundos


def rodar(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=900)


def setUpModule():
    """Pasta temporária própria (base_temporaria.py; revisão de segurança da 1.7.7, terceira passada, R177C-T-01): a
    área do executor e as pastas dos testes não dependem do que há na pasta temporária da máquina."""
    unittest.addModuleCleanup(_modulo("base_temporaria", Path(__file__).with_name("base_temporaria.py")).ligar())


def transcricao(arq: Path, init: str = ESPERADO, respostas: str = ESPERADO, uso_de_modelos=None) -> Path:
    """Rastro stream-json fictício: system/init, uma resposta do assistente e o result."""
    resultado = {"type": "result", "subtype": "success", "is_error": False, "duration_ms": 1000, "num_turns": 2}
    if uso_de_modelos:
        resultado["modelUsage"] = {m: {"inputTokens": 1, "outputTokens": 1} for m in uso_de_modelos}
    eventos = [{"type": "system", "subtype": "init", "model": init, "session_id": "s1"},
               {"type": "assistant", "message": {"model": respostas, "content": [{"type": "text", "text": "ok"}]}},
               resultado]
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text("\n".join(json.dumps(e) for e in eventos) + "\n", encoding="utf-8")
    return arq


class TestR177Val08PartidasAmarradasAsExecucoes(unittest.TestCase):
    """Bancada da E8 (preparo leve, só com a skill) com três execuções, preparada sem livro, e livros de teto curto."""

    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory(prefix="r177-08-")
        cls.t = Path(cls._td.name).resolve()
        cls.it = cls.t / "repo" / "ws" / "iteration-1"
        r = rodar(EVALS / "preparar_avaliacoes.py", "--workspace", cls.it.parent, "--so", "8", "--execucoes", "3")
        assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
        cls.pedidos = json.loads((cls.it / "prompts.json").read_text(encoding="utf-8"))
        cls.area = json.loads((cls.it / "isolamento.json").read_text(encoding="utf-8"))["area"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.area, ignore_errors=True)
        cls._td.cleanup()

    def abrir(self, nome: str, teto: int, *extra) -> Path:
        livro = self.t / "livros" / nome
        r = rodar(LIVRO, "abrir", "--livro", livro, "--autorizacao", "Sim: ensaio fictício", "--data", "2026-10-21",
                  "--teto", teto, "--modelo-esperado", ESPERADO, "--braco", f"with_skill={SKILL}", *extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return livro

    def pedido(self, k: int) -> dict:
        return self.pedidos[f"8/with_skill/run-{k}"]

    def iniciar(self, livro: Path, rotulo: str, k: int) -> subprocess.CompletedProcess:
        return rodar(LIVRO, "iniciar", "--livro", livro, "--rotulo", rotulo, "--avaliacao", 8, "--braco", "with_skill",
                     "--iteracao", self.it, "--execucao", self.pedido(k)["id"])

    def test_teto_1_uma_partida_e_tres_execucoes_so_a_amarrada_conta(self):
        livro = self.abrir("teto-1", 1)
        self.assertEqual(self.iniciar(livro, "E8-r1", 1).returncode, 0)
        trace = transcricao(Path(self.pedido(1)["registro"]) / "trace.jsonl")
        r = rodar(LIVRO, "fechar", "--livro", livro, "--rotulo", "E8-r1", "--estado", "concluida",
                  "--transcricao", trace)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        partida = json.loads((livro / "livro.json").read_text(encoding="utf-8"))["partidas"][0]
        self.assertEqual((partida["execucao"], partida["transcricao"]["sha256"]), (self.pedido(1)["id"], _sha(trace)))
        caso = Path(self.pedido(1)["registro"]).parent.parent  # eval-8-<nome>
        try:
            for k in (1, 2, 3):
                run = Path(self.pedido(k)["registro"])
                (run / "outputs" / "RELATO.md").write_text(f"relato fictício {k}\n", encoding="utf-8")
            separada = tempfile.TemporaryDirectory(prefix="r177-08-cega-")
            self.addCleanup(separada.cleanup)
            antes = (livro / "livro.json").read_bytes()
            r = rodar(EVALS / "cegar.py", "cegar", "--iteracao", self.it, "--livro", livro,
                      "--destino", Path(separada.name) / "cega")
            self.assertEqual(r.returncode, 3, "cegou execuções sem partida no livro: " + r.stdout + r.stderr)
            self.assertIn("run-2", r.stderr)
            self.assertIn("run-3", r.stderr)
            self.assertEqual((livro / "livro.json").read_bytes(), antes)
            assercoes = json.loads((caso / "eval_metadata.json").read_text(encoding="utf-8"))["assertions"]
            for k in (1, 2, 3):  # notas aprovadas nas três (como se reveladas): só a amarrada pode contar
                (Path(self.pedido(k)["registro"]) / "grading.json").write_text(json.dumps({"expectations": [
                    {"text": a, "passed": True, "evidence": "fictícia"} for a in assercoes]}), encoding="utf-8")
            r = rodar(EVALS / "resumo_k.py", "--iteracao", self.it, "--livro", livro)
            self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
            linha = json.loads(r.stdout)["avaliacoes"][caso.name]["bracos"]["with_skill"]
            estados = {run: e["estado"] for run, e in linha["execucoes"].items()}
            self.assertEqual(estados, {"run-1": "aprovada", "run-2": "nao_medida", "run-3": "nao_medida"}, linha)
            self.assertIn("partida", linha["execucoes"]["run-2"]["motivo"])
            self.assertEqual(linha["pass^k"], "nao_medido")
        finally:
            for k in (1, 2, 3):
                for nome in ("grading.json", "trace.jsonl"):
                    (Path(self.pedido(k)["registro"]) / nome).unlink(missing_ok=True)
                (Path(self.pedido(k)["registro"]) / "outputs" / "RELATO.md").unlink(missing_ok=True)

    def test_iniciar_confere_a_execucao_e_a_copia_da_skill_e_fechar_reconfere(self):
        livro = self.abrir("copia", 3)
        r = rodar(LIVRO, "iniciar", "--livro", livro, "--rotulo", "x", "--avaliacao", 10, "--braco", "with_skill",
                  "--iteracao", self.it, "--execucao", self.pedido(2)["id"])
        self.assertEqual(r.returncode, 3, "partida amarrada a uma execução de outro caso")
        skill_md = {k: Path(self.pedido(k)["skill"]) / "SKILL.md" for k in (2, 3)}
        guardados = {k: p.read_bytes() for k, p in skill_md.items()}
        try:
            skill_md[3].write_bytes(guardados[3] + b"\nregra trocada antes da partida\n")
            self.assertEqual(self.iniciar(livro, "E8-r3", 3).returncode, 3, "a cópia mudada depois do preparo passou")
            self.assertEqual(self.iniciar(livro, "E8-r2", 2).returncode, 0)
            skill_md[2].write_bytes(guardados[2] + b"\nregra trocada durante a partida\n")
            trace = transcricao(self.t / "rastros" / "copia.jsonl")
            r = rodar(LIVRO, "fechar", "--livro", livro, "--rotulo", "E8-r2", "--estado", "concluida",
                      "--transcricao", trace)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = rodar(LIVRO, "conferir", "--livro", livro)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertTrue(any("cópia da skill" in p for p in json.loads(r.stdout)["problemas"]), r.stdout)
        finally:
            for k, p in skill_md.items():
                p.write_bytes(guardados[k])


def _sha(caminho: Path) -> str:
    import hashlib
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


class TestR177Val08ModeloQueRespondeu(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory(prefix="r177-08-modelo-")
        self.addCleanup(td.cleanup)
        self.t = Path(td.name)

    def partida(self, *abrir_extra, **rastro) -> subprocess.CompletedProcess:
        livro = self.t / f"livro-{len(list(self.t.iterdir()))}"
        r = rodar(LIVRO, "abrir", "--livro", livro, "--autorizacao", "ensaio fictício", "--data", "2026-10-21",
                  "--teto", 1, "--modelo-esperado", ESPERADO, "--braco", "without_skill=", *abrir_extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rodar(LIVRO, "iniciar", "--livro", livro, "--rotulo", "E10-r1", "--avaliacao", 10,
                               "--braco", "without_skill").returncode, 0)
        trace = transcricao(self.t / f"rastro-{livro.name}.jsonl", **rastro)
        r = rodar(LIVRO, "fechar", "--livro", livro, "--rotulo", "E10-r1", "--estado", "concluida",
                  "--transcricao", trace)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return rodar(LIVRO, "conferir", "--livro", livro)

    def test_init_do_esperado_e_respostas_de_outro_modelo_acusa(self):
        r = self.partida(respostas="claude-opus-5-5")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("claude-opus-5-5", " ".join(json.loads(r.stdout)["problemas"]))

    def test_modelo_no_result_acusa_salvo_auxiliar_declarado_no_abrir(self):
        r = self.partida(uso_de_modelos=[ESPERADO, "claude-haiku-5-0"])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("claude-haiku-5-0", " ".join(json.loads(r.stdout)["problemas"]))
        r = self.partida("--modelo-auxiliar", "claude-haiku-5-0", uso_de_modelos=[ESPERADO, "claude-haiku-5-0"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.partida().returncode, 0, "o rastro todo do modelo esperado foi acusado")


class TestR177Val08IdentidadeCobreOPreparo(unittest.TestCase):
    """Numa cópia da árvore inteira: mexer num script, numa fixture ou no manifesto depois do `abrir` recusa iniciar."""

    def test_scripts_e_fixtures_fora_da_identidade_recusam_iniciar(self):
        with tempfile.TemporaryDirectory(prefix="r177-08-ident-") as td:
            copia = Path(td) / "arvore" / "fundacao-ia-multiprojetos"
            shutil.copytree(SKILL, copia, ignore=shutil.ignore_patterns("__pycache__"))
            livro_py, livro = copia / "evals" / "livro_avaliacoes.py", Path(td) / "livro"
            r = rodar(livro_py, "abrir", "--livro", livro, "--autorizacao", "ensaio fictício", "--data", "2026-10-21",
                      "--teto", 9, "--modelo-esperado", ESPERADO, "--braco", "without_skill=")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for i, rel in enumerate(("evals/cegar.py", "evals/livro_avaliacoes.py", "evals/medidas_do_rastro.py",
                                     "scripts/manifesto.py", "evals/cenarios/run_cenarios.py",
                                     "evals/fixtures/legado-squad/README.md")):
                with self.subTest(rel):
                    arq = copia / rel
                    original = arq.read_bytes()
                    arq.write_bytes(original + b"\n# mudado depois do abrir\n")
                    try:  # rótulo próprio: a recusa tem de vir da identidade, não de rótulo repetido
                        r = rodar(livro_py, "iniciar", "--livro", livro, "--rotulo", f"E10-{i}", "--avaliacao", 10,
                                  "--braco", "without_skill")
                        self.assertEqual(r.returncode, 3, f"{rel} mudou e o iniciar aceitou: {r.stdout}{r.stderr}")
                        self.assertIn(rel, r.stderr)
                    finally:
                        arq.write_bytes(original)
            r = rodar(livro_py, "iniciar", "--livro", livro, "--rotulo", "E10-ok", "--avaliacao", 10,
                      "--braco", "without_skill")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


def _modulo(nome: str, caminho: Path):
    spec = importlib.util.spec_from_file_location(nome, caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _banco_plantado(caminho: Path, *sql: str) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(caminho))
    try:
        for comando in sql:
            con.execute(comando)
        con.commit()
    finally:
        con.close()
    return caminho


# `event` como visão recursiva sem fim: COUNT(*) e GROUP BY nunca terminam.
VISAO_SEM_FIM = ("CREATE VIEW event AS WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) "
                 "SELECT x AS seq, 'restore_completed' AS kind, 'titular' AS subject, '{}' AS payload_json FROM c")
TABELAS_DO_KIT = ("CREATE TABLE project (project_id TEXT)",
                  "CREATE TABLE acl (subject TEXT, resource TEXT, action TEXT)",
                  "CREATE TABLE run (run_id TEXT, flow_id TEXT, state TEXT)",
                  "CREATE TABLE step (run_id TEXT, step_id TEXT, state TEXT, attempts INT, executions INT)")
EVENTO = ("CREATE TABLE event (seq INTEGER PRIMARY KEY, event_id TEXT, ts TEXT, schema_version INT, kind TEXT, "
          "project_id TEXT, subject TEXT, run_id TEXT, task_id TEXT, payload_json TEXT, prev_hash TEXT, hash TEXT)")

# Chamada num processo à parte: se o verificador travar, o teste falha no prazo em vez de travar a suíte.
CHAMAR = """import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("ve_r177_09", sys.argv[1])
ve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ve)
alvo = Path(sys.argv[3])
if sys.argv[2] == "backups":
    print(json.dumps(ve.fatos_backups(alvo, alvo / "fundacao", Path(sys.argv[4])), ensure_ascii=False))
else:
    print(json.dumps(ve.banco(alvo), ensure_ascii=False))
"""


class TestR177Val09SqlLimitadoNoVerificador(unittest.TestCase):
    def _chamar(self, *args) -> dict:
        try:
            r = subprocess.run([sys.executable, "-B", "-c", CHAMAR, str(VERIFICADOR), *map(str, args)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=PRAZO_S)
        except subprocess.TimeoutExpired:
            self.fail(f"o verificador travou (mais de {PRAZO_S} s) num banco plantado no ambiente avaliado")
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        return json.loads(r.stdout)

    def test_event_como_visao_sem_fim_nao_trava_os_fatos_de_backup(self):
        with tempfile.TemporaryDirectory(prefix="r177-09-") as td:
            t = Path(td)
            amb, refs = t / "ambiente", t / "refs"
            (amb / "backups").mkdir(parents=True)
            refs.mkdir()
            (refs / "backups-antes.json").write_text("{}", encoding="utf-8")
            (refs / "afirmacao-falsa.txt").write_text("rotina concluída (fictícia)", encoding="utf-8")
            _banco_plantado(amb / "ensaio" / "state" / "state.sqlite", VISAO_SEM_FIM)
            # Um ensaio verdadeiro ao lado continua contado: o limite não esconde o que é legítimo.
            _banco_plantado(amb / "ensaio-ok" / "state" / "state.sqlite", EVENTO,
                            "INSERT INTO event (kind) VALUES ('restore_completed')")
            fatos = self._chamar("backups", amb, refs)
        self.assertEqual(fatos["ensaios_de_restauracao"], ["ensaio-ok"])
        self.assertEqual([b["pasta"] for b in fatos["bancos_nao_lidos"]], ["ensaio"], fatos)
        self.assertIn("event", fatos["bancos_nao_lidos"][0]["motivo"])

    def test_event_como_visao_ou_tabela_virtual_nao_trava_o_banco_da_fundacao(self):
        for nome, evento in (("visao", VISAO_SEM_FIM), ("virtual", "CREATE VIRTUAL TABLE event USING fts5(kind)")):
            with self.subTest(nome), tempfile.TemporaryDirectory(prefix="r177-09-") as td:
                fund = Path(td) / "fundacao"
                _banco_plantado(fund / "state" / "state.sqlite", *TABELAS_DO_KIT, evento)
                fatos = self._chamar("banco", fund)
                self.assertTrue(fatos["kit_db"])
                self.assertIn("event", fatos.get("erro_banco", ""), fatos)
                self.assertNotIn("cadeia_eventos", fatos)

    def test_banco_aberto_somente_leitura_sem_confiar_no_esquema(self):
        ve = _modulo("ve_r177_09_pragmas", VERIFICADOR)
        with tempfile.TemporaryDirectory(prefix="r177-09-") as td:
            db = _banco_plantado(Path(td) / "state.sqlite", *TABELAS_DO_KIT, EVENTO)
            antes = db.read_bytes()
            with ve.banco_avaliado.aberto(db) as con:
                self.assertEqual(con.execute("PRAGMA trusted_schema").fetchone()[0], 0)
                self.assertEqual(con.execute("PRAGMA query_only").fetchone()[0], 1)
                with self.assertRaises(sqlite3.Error):
                    con.execute("CREATE TABLE intrusa (a)")
            self.assertEqual(db.read_bytes(), antes)

    def test_consulta_que_passa_do_limite_e_interrompida_e_vira_fato(self):
        ve = _modulo("ve_r177_09_limite", VERIFICADOR)
        with tempfile.TemporaryDirectory(prefix="r177-09-") as td:
            fund = Path(td) / "fundacao"
            _banco_plantado(fund / "state" / "state.sqlite", *TABELAS_DO_KIT, EVENTO,
                            "INSERT INTO event (kind, payload_json) WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL "
                            "SELECT x + 1 FROM c WHERE x < 5000) SELECT 'teste', '{}' FROM c")
            self.assertNotIn("erro_banco", ve.banco(fund), "o banco legítimo não foi lido")
            ve.banco_avaliado.LIMITE_S, ve.banco_avaliado.PASSOS = 0.0, 1  # limite já vencido na primeira conferência
            fatos = ve.banco(fund)
        self.assertIn("tempo limite", fatos.get("erro_banco", ""), fatos)


if __name__ == "__main__":
    unittest.main()
