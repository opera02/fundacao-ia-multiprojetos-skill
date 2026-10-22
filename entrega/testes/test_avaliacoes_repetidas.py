"""Avaliações repetidas: todas as execuções contam e segurança só passa com pass^k (everything-claude-code,
proposta 4).

Até a 1.7.6, o verificador lia só `run-1` (uma segunda execução era ignorada sem aviso) e as avaliações rodavam
uma vez cada. Aqui nada roda modelo: a E1 é preparada com k = 2 e os fatos das duas execuções aparecem; numa
iteração fictícia, `run-1` aprovado e `run-2` reprovado dão pass@2 = sim e pass^2 = não — a avaliação de segurança
(E7) não passa e a de capacidade (E12) passa; execução sem nota ou com nota inválida é "não medida", nunca
"passou"; execução contaminada (acesso ao gabarito no rastro) não pode ser aprovada.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENTREGA = Path(__file__).resolve().parents[1]
SKILL = ENTREGA.parent / "fundacao-ia-multiprojetos"
EVALS = SKILL / "evals"


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


def _evals() -> dict:
    return {e["id"]: e for e in json.loads((EVALS / "evals.json").read_text(encoding="utf-8"))["evals"]}


class TestTodasAsExecucoesContam(unittest.TestCase):
    def test_seguranca_marcada_em_e7_e9_e11(self):
        self.assertEqual(sorted(i for i, e in _evals().items() if e.get("seguranca")), [7, 9, 11])

    def test_verificador_percorre_todas_as_execucoes(self):
        with tempfile.TemporaryDirectory(prefix="k-") as td:
            ws = Path(td) / "ws"
            r = rodar(EVALS / "preparar_avaliacoes.py", "--workspace", ws, "--so", "1", "--execucoes", "2")
            self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-1500:])
            it = ws / "iteration-1"
            area = json.loads((it / "isolamento.json").read_text(encoding="utf-8"))["area"]
            self.addCleanup(shutil.rmtree, area, True)  # área na pasta temporária do sistema (R177-VAL-06)
            pedidos = json.loads((it / "prompts.json").read_text(encoding="utf-8"))
            self.assertEqual(len({p["ambiente"] for p in pedidos.values()}), 4, "cada execução com ambiente próprio")
            r = rodar(EVALS / "verificar_execucoes.py", "--iteracao", it, "--so", "1")
            self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
            fatos = json.loads((it / "_referencias" / "fatos.json").read_text(encoding="utf-8"))
            resumo = json.loads((it / "_referencias" / "resumo-k.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(fatos), [f"eval-1-nova-fundacao/{b}/run-{k}" for b in ("with_skill", "without_skill")
                                         for k in (1, 2)])
        bracos = resumo["avaliacoes"]["eval-1-nova-fundacao"]["bracos"]
        self.assertEqual({b: (x["k"], x["pass@k"], x["veredito"]) for b, x in bracos.items()},
                         {"with_skill": (2, "nao_medido", "não medida"), "without_skill": (2, "nao_medido", "não medida")},
                         "execução sem nota virou resultado")


class TestPassAtKEPassHatK(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="k-ficticia-")
        self.it = Path(self._td.name) / "iteration-1"

    def tearDown(self):
        self._td.cleanup()

    def avaliacao(self, eid: int, notas: dict[str, list | None], fatos: dict | None = None) -> dict:
        """Iteração fictícia: uma pasta por execução, com a nota (`grading.json`) dada; None = sem nota."""
        ev = _evals()[eid]
        edir = self.it / f"eval-{eid}-{ev['name']}"
        edir.mkdir(parents=True)
        (edir / "eval_metadata.json").write_text(json.dumps({
            "eval_id": eid, "eval_name": ev["name"], "assertions": ev["expectations"],
            "seguranca": bool(ev.get("seguranca"))}, ensure_ascii=False), encoding="utf-8")
        for run, passed in notas.items():
            pasta = edir / "with_skill" / run
            (pasta / "outputs").mkdir(parents=True)
            if passed is not None:
                (pasta / "grading.json").write_text(json.dumps({"expectations": [
                    {"text": t, "passed": p, "evidence": "fictícia"} for t, p in zip(ev["expectations"], passed)]},
                    ensure_ascii=False), encoding="utf-8")
        (self.it / "_referencias").mkdir(exist_ok=True)
        (self.it / "_referencias" / "fatos.json").write_text(json.dumps(fatos or {}), encoding="utf-8")
        r = rodar(EVALS / "resumo_k.py", "--iteracao", self.it)
        self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
        resumo = json.loads((self.it / "_referencias" / "resumo-k.json").read_text(encoding="utf-8"))
        shutil.rmtree(edir)
        return resumo["avaliacoes"][edir.name]["bracos"]["with_skill"]

    def test_run_1_aprovado_e_run_2_reprovado(self):
        n7 = len(_evals()[7]["expectations"])
        seguranca = self.avaliacao(7, {"run-1": [True] * n7, "run-2": [True] * (n7 - 1) + [False]})
        self.assertEqual({k: v["estado"] for k, v in seguranca["execucoes"].items()},
                         {"run-1": "aprovada", "run-2": "reprovada"})
        self.assertEqual((seguranca["k"], seguranca["pass@k"], seguranca["pass^k"]), (2, "sim", "nao"))
        self.assertEqual(seguranca["veredito"], "não passou", "segurança passou sem pass^k")
        n12 = len(_evals()[12]["expectations"])
        capacidade = self.avaliacao(12, {"run-1": [True] * n12, "run-2": [False] + [True] * (n12 - 1)})
        self.assertEqual((capacidade["pass@k"], capacidade["pass^k"], capacidade["veredito"]), ("sim", "nao", "passou"))

    def test_nao_rodado_nunca_vira_passou(self):
        n = len(_evals()[9]["expectations"])
        r = self.avaliacao(9, {"run-1": [True] * n, "run-2": None, "run-10": ["nao_medido"] + [True] * (n - 1)})
        self.assertEqual(list(r["execucoes"]), ["run-1", "run-2", "run-10"], "execuções fora de ordem")
        self.assertEqual([v["estado"] for v in r["execucoes"].values()], ["aprovada", "nao_medida", "nao_medida"])
        self.assertEqual((r["pass^k"], r["veredito"]), ("nao_medido", "não medida"))
        sozinha = self.avaliacao(11, {"run-1": [True] * len(_evals()[11]["expectations"])})
        self.assertEqual((sozinha["veredito"], sozinha["aviso"]),
                         ("passou", "k = 1: teste de fumaça, sem medida de variabilidade"))

    def test_nota_invalida_e_execucao_contaminada_nao_aprovam(self):
        n = len(_evals()[7]["expectations"])
        invalida = self.avaliacao(7, {"run-1": [1] * n})  # 1 não é true
        self.assertEqual(invalida["execucoes"]["run-1"]["estado"], "nao_medida")
        curta = self.avaliacao(7, {"run-1": [True] * (n - 1)})
        self.assertEqual(curta["execucoes"]["run-1"]["estado"], "nao_medida")
        contaminada = self.avaliacao(7, {"run-1": [True] * n}, fatos={
            "eval-7-acesso-entre-projetos/with_skill/run-1": {"acesso_ao_gabarito": {"estado": "contaminada"}}})
        self.assertEqual(contaminada["execucoes"]["run-1"]["estado"], "contaminada")
        self.assertEqual((contaminada["pass@k"], contaminada["pass^k"], contaminada["veredito"]),
                         ("nao", "nao", "não passou"))


if __name__ == "__main__":
    unittest.main()
