"""Auditoria externa da 1.3.4 — registros de avaliação (F19).

Confere o que é verificável sem nova rodada de modelos: comparação PAREADA publicada, telemetria
não medida marcada como tal, mapa de ordem do acionamento entregue (a pontuação se reproduz) e
rubrica do E7 que mede acesso, não só ausência do marcador. Não repete avaliações com subagentes.
"""

from __future__ import annotations

import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENTREGA = Path(__file__).resolve().parents[1]
AVALIACOES = ENTREGA / "avaliacoes"
SKILL = ENTREGA.parent / "fundacao-ia-multiprojetos"
REANALISE = AVALIACOES / "reanalise-pareada-iteracao-1.json"


class TestF19Avaliacoes(unittest.TestCase):
    def test_f19_mapa_de_ordem_entregue_reproduz_a_pontuacao_do_acionamento(self):
        origem = AVALIACOES / "acionamento"
        self.assertTrue((origem / "ordem.json").is_file(), "ordem.json não acompanha a entrega")
        with tempfile.TemporaryDirectory(prefix="acionamento-teste-") as t:
            copia = Path(t) / "acionamento"
            shutil.copytree(origem, copia)
            p = subprocess.run([sys.executable, "-B", str(SKILL / "evals" / "acionamento" / "montar_simulacao.py"),
                                "pontuar", "--respostas", str(copia / "respostas.json"), "--saida", str(copia)],
                               capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            res = json.loads((copia / "resultado.json").read_text(encoding="utf-8"))
        gravado = json.loads((origem / "resultado.json").read_text(encoding="utf-8"))
        self.assertEqual((res["acertos"], res["total"]), (gravado["acertos"], gravado["total"]))
        self.assertIn("simulação", res["tipo"])

    def test_f19_comparacao_pareada_publicada_confere_com_o_benchmark(self):
        self.assertTrue(REANALISE.is_file(), "reanálise pareada não publicada")
        bench = json.loads((AVALIACOES / "subagentes-iteracao-1" / "benchmark.json").read_text(encoding="utf-8"))
        pares = {}
        for r in bench["runs"]:
            pares.setdefault(r["eval_id"], {})[r["configuration"]] = r["result"]
        completos = [p for p in pares.values() if set(p) == {"with_skill", "without_skill"}]
        publicado = json.loads(REANALISE.read_text(encoding="utf-8"))
        for metrica in ("time_seconds", "tokens"):
            delta = statistics.mean(p["with_skill"][metrica] - p["without_skill"][metrica] for p in completos)
            self.assertAlmostEqual(publicado["pareado"][metrica]["delta_medio"], delta, places=2)
        self.assertEqual(publicado["pareado"]["pares"], len(completos))
        texto = (AVALIACOES / "AVALIACOES.md").read_text(encoding="utf-8")
        self.assertIn("pareada", texto, "AVALIACOES.md não publica a comparação pareada")

    def test_f19_telemetria_nao_medida_nao_aparece_como_zero(self):
        publicado = json.loads(REANALISE.read_text(encoding="utf-8")) if REANALISE.is_file() else {}
        self.assertEqual(publicado.get("telemetria", {}).get("tool_calls"), "nao_medido")
        self.assertEqual(publicado.get("telemetria", {}).get("errors"), "nao_medido")

    def test_f19_acesso_vem_do_trace_e_sem_trace_fica_nao_medido(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("ve_teste", SKILL / "evals" / "verificar_execucoes.py")
        ve = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ve)
        funcao = getattr(ve, "acessos_no_trace", None)
        self.assertIsNotNone(funcao, "os fatos da avaliação não examinam o trace de ferramentas")
        linhas = [{"type": "assistant", "message": {"content": [
                      {"type": "tool_use", "name": "Bash",
                       "input": {"command": "cat projects/juridico-lab/data/aurora-notas.md"}}]}},
                  {"type": "assistant", "message": {"content": [
                      {"type": "tool_use", "name": "Bash",
                       "input": {"command": "python -m fundacao --raiz . status"}}]}}]
        with tempfile.TemporaryDirectory(prefix="trace-teste-") as t:
            trace = Path(t) / "trace.jsonl"
            trace.write_text("\n".join(json.dumps(x) for x in linhas), encoding="utf-8")
            r = funcao(trace)
            self.assertEqual(funcao(Path(t) / "sem-trace.jsonl"), "nao_medido")
        self.assertEqual(len(r["diretos"]), 1)

    def test_f19_rubrica_do_e7_mede_acesso_antes_da_resposta(self):
        evals = json.loads((SKILL / "evals" / "evals.json").read_text(encoding="utf-8"))
        lista = evals["evals"] if isinstance(evals, dict) else evals
        e7 = next(e for e in lista if e["id"] == 7)
        self.assertTrue(any("trace" in x.lower() or "transcri" in x.lower() for x in e7["expectations"]),
                        "a rubrica do E7 mede só a ausência do marcador na resposta")


if __name__ == "__main__":
    unittest.main()
