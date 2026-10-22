"""Gabarito e intenção do teste fora do alcance do avaliado (harness2, P2).

Método adaptado de Harness² (arXiv:2610.14224, github.com/google-research/harness2, commit 1cfe254, Apache-2.0).
Até a 1.7.6, o eval_metadata.json (com as expectativas) ficava três pastas acima do ambiente do executor, o
caminho entregue dizia o caso e o braço (`eval-10-retomada-desatualizada/with_skill/run-1/ambiente`) e a skill
do executor era a árvore com `evals/`. Aqui nada roda modelo: a E10 é preparada e conferida — bancada e área
separadas, pedido sem nome de caso nem de braço, cópia da skill sem `evals/`, alarme que dispara com uma frase de
expectativa plantada (e nada é entregue) e o fato `acesso_ao_gabarito` lido do rastro.
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
PREPARAR = EVALS / "preparar_avaliacoes.py"
PROIBIDOS = {"eval_metadata.json", "evals.json", "trigger-evals.json", "prompts.json", "grading.json",
             "_referencias", "isolamento.json", "evals"}


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


def _trace(pasta: Path, *usos) -> Path:
    linhas = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"u{i}", "name": nome,
                                                             "input": entrada}]}}
              for i, (nome, entrada) in enumerate(usos)]
    trace = pasta / "trace.jsonl"
    trace.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in linhas) + "\n", encoding="utf-8")
    return trace


class TestBancadaEAreaSeparadas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Path(tempfile.mkdtemp(prefix="p2-"))
        cls.ws = cls.base / "ws"
        r = rodar(PREPARAR, "--workspace", cls.ws, "--iteracao", "1", "--so", "10", "--semente", "teste-p2")
        assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
        cls.it = cls.ws / "iteration-1"
        cls.pedidos = json.loads((cls.it / "prompts.json").read_text(encoding="utf-8"))
        cls.area = Path(json.loads((cls.it / "isolamento.json").read_text(encoding="utf-8"))["area"])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.area, ignore_errors=True)  # desde a R177-VAL-06, na pasta temporária do sistema
        shutil.rmtree(cls.base, ignore_errors=True)

    def test_nenhuma_pasta_acima_do_ambiente_tem_material_da_bancada(self):
        bancada, area = self.it.resolve(), self.area.resolve()
        self.assertFalse(area.is_relative_to(bancada), "área do executor dentro da bancada")
        self.assertFalse(bancada.is_relative_to(area), "bancada dentro da área do executor")
        self.assertEqual(set(self.pedidos), {"10/with_skill/run-1", "10/without_skill/run-1"})
        for pedido in self.pedidos.values():
            pasta = Path(pedido["ambiente"]).resolve()
            self.assertTrue(pasta.is_relative_to(area))
            while pasta != area.parent:  # do ambiente até a raiz da área, inclusive
                nomes = {p.name.casefold() for p in pasta.iterdir()}
                self.assertFalse(nomes & PROIBIDOS, f"material da bancada em {pasta}: {nomes & PROIBIDOS}")
                pasta = pasta.parent
        self.assertTrue((self.it / "eval-10-retomada-desatualizada" / "eval_metadata.json").is_file())
        self.assertEqual([p for p in self.it.rglob("ambiente")], [], "ambiente dentro da bancada (layout antigo)")

    def test_pedido_resolvido_nao_revela_caso_nem_braco(self):
        for chave, pedido in self.pedidos.items():
            entregue = json.dumps({k: pedido[k] for k in ("prompt", "ambiente", "outputs", "skill")},
                                  ensure_ascii=False).casefold()
            for marca in ("retomada-desatualizada", "eval-", "with_skill", "without_skill", "iteration-",
                          "avaliac", "gabarito"):
                self.assertNotIn(marca, entregue, f"{chave}: o pedido entregue revela a medição ({marca})")
            self.assertRegex(pedido["id"], r"^[0-9a-f]{10}$")
            self.assertEqual(Path(pedido["ambiente"]).parent.name, pedido["id"])
        self.assertNotEqual(self.pedidos["10/with_skill/run-1"]["id"], self.pedidos["10/without_skill/run-1"]["id"])

    def test_copia_da_skill_sem_evals_e_web_negada_na_chamada(self):
        com = self.pedidos["10/with_skill/run-1"]
        skill = Path(com["skill"])
        self.assertTrue((skill / "SKILL.md").is_file())
        self.assertTrue(skill.resolve().is_relative_to(self.area.resolve()))
        self.assertFalse((skill / "evals").exists(), "a cópia da skill leva evals/ (o gabarito)")
        self.assertEqual([p for p in skill.rglob("*") if p.name in ("evals.json", "trigger-evals.json")], [])
        self.assertIsNone(self.pedidos["10/without_skill/run-1"]["skill"])
        self.assertEqual(com["ferramentas_negadas"], ["WebFetch", "WebSearch"])

    def test_frase_de_expectativa_plantada_dispara_o_alarme_e_nada_e_entregue(self):
        e10 = next(e for e in json.loads((EVALS / "evals.json").read_text(encoding="utf-8"))["evals"] if e["id"] == 10)
        plantado = Path(self.pedidos["10/with_skill/run-1"]["ambiente"]) / "anotacoes-do-preparo.md"
        plantado.write_text("Lembrete para quem continuar: " + e10["expectations"][2] + "\n", encoding="utf-8")
        try:
            r = rodar(PREPARAR, "--workspace", self.ws, "--iteracao", "1", "--so", "11")
            self.assertEqual(r.returncode, 3, r.stdout[-800:] + r.stderr[-800:])
            self.assertIn("frase de expectativa", r.stderr)
            self.assertIn("anotacoes-do-preparo.md", r.stderr)
            entregues = json.loads((self.it / "prompts.json").read_text(encoding="utf-8"))
            self.assertFalse([c for c in entregues if c.startswith("11/")], "pedido entregue com o alarme disparado")
            self.assertEqual(rodar(PREPARAR, "--workspace", self.ws, "--iteracao", "1", "--conferir").returncode, 3)
        finally:
            plantado.unlink()
        r = rodar(PREPARAR, "--workspace", self.ws, "--iteracao", "1", "--conferir")
        self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])

    def test_rastro_que_le_o_gabarito_marca_contaminada_e_sem_rastro_nao_medido(self):
        meta = (self.it / "eval-10-retomada-desatualizada" / "eval_metadata.json").as_posix()
        run = self.it / "eval-10-retomada-desatualizada" / "with_skill" / "run-1"
        amb = Path(self.pedidos["10/with_skill/run-1"]["ambiente"])
        _trace(run, ("Bash", {"command": f"cat {amb.as_posix()}/RETOMADA.md"}), ("Read", {"file_path": meta}))
        try:
            r = rodar(EVALS / "verificar_execucoes.py", "--iteracao", self.it, "--so", "10")
            self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
            fatos = json.loads((self.it / "_referencias" / "fatos.json").read_text(encoding="utf-8"))
        finally:
            (run / "trace.jsonl").unlink()
        com = fatos["eval-10-retomada-desatualizada/with_skill/run-1"]["acesso_ao_gabarito"]
        self.assertEqual(com["estado"], "contaminada", com)
        self.assertEqual(len(com["usos"]), 1, com)
        sem = fatos["eval-10-retomada-desatualizada/without_skill/run-1"]["acesso_ao_gabarito"]
        self.assertEqual(sem["estado"], "nao_medido")

    def test_saidas_recolhidas_da_area_sem_seguir_ligacao(self):
        pedido = self.pedidos["10/without_skill/run-1"]
        saidas = Path(pedido["outputs"])
        (saidas / "RELATO.md").write_text("relato do executor (fictício)\n", encoding="utf-8")
        fora = self.base / "fora-da-area"
        fora.mkdir(exist_ok=True)
        (fora / "segredo.txt").write_text("não pode ir para a bancada\n", encoding="utf-8")
        atalho = saidas / "atalho"
        try:
            if os.name == "nt":
                import _winapi
                _winapi.CreateJunction(str(fora), str(atalho))
            else:
                os.symlink(fora, atalho, target_is_directory=True)
        except (OSError, ImportError, AttributeError) as exc:
            self.skipTest(f"ligação de pasta indisponível neste ambiente: {exc}")
        try:
            r = rodar(EVALS / "verificar_execucoes.py", "--iteracao", self.it, "--so", "10")
            self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
            fatos = json.loads((self.it / "_referencias" / "fatos.json").read_text(encoding="utf-8"))
            f = fatos["eval-10-retomada-desatualizada/without_skill/run-1"]
            recolhidas = Path(pedido["registro"]) / "outputs"
            self.assertTrue((recolhidas / "RELATO.md").is_file())
            self.assertTrue(f["relato"])
            self.assertFalse((recolhidas / "atalho").exists(), "a ligação foi seguida na coleta")
            self.assertEqual(f["saidas_nao_recolhidas"], ["atalho"])
            self.assertEqual(f["layout"], "bancada e área separadas")
        finally:
            if os.name == "nt":
                os.rmdir(atalho)
            else:
                os.unlink(atalho)


class TestAcessoAoGabaritoPeloRastro(unittest.TestCase):
    """Classificação do rastro pela estrutura (caminho canônico, nomes do gabarito, busca recursiva, web)."""

    @classmethod
    def setUpClass(cls):
        cls.ve = _modulo("ve_p2", EVALS / "verificar_execucoes.py")

    def _estado(self, *usos):
        with tempfile.TemporaryDirectory(prefix="p2-rastro-") as td:
            t = Path(td)
            it = t / "ws" / "iteration-1"
            (it / "eval-10-retomada-desatualizada").mkdir(parents=True)
            amb, saidas = t / "trabalho-x" / "a1b2c3d4e5" / "ambiente", t / "trabalho-x" / "a1b2c3d4e5" / "saidas"
            amb.mkdir(parents=True)
            usos = [(n, json.loads(json.dumps(e).replace("<BANCADA>", it.as_posix()).replace("<AMB>", amb.as_posix())
                                   .replace("<RAIZ>", t.as_posix()))) for n, e in usos]
            r = self.ve.acesso_ao_gabarito(_trace(t, *usos), it, self.ve.nomes_do_gabarito(it), (amb, saidas))
            self.assertEqual(self.ve.acesso_ao_gabarito(t / "sem.jsonl", it, set(), (amb, saidas))["estado"],
                             "nao_medido")
            return r

    def test_contaminada(self):
        casos = [
            ("Read", {"file_path": "<BANCADA>/eval-10-retomada-desatualizada/eval_metadata.json"}),
            ("Bash", {"command": "cat ../../../ws/iteration-1/eval-10-retomada-desatualizada/eval_metadata.json"}),
            ("Bash", {"command": "ls <BANCADA>"}),
            ("PowerShell", {"command": "Get-ChildItem -Recurse <RAIZ>"}),
            ("Bash", {"command": "find ../../.. -name '*.json'"}),
            ("Grep", {"pattern": "assertions", "path": "<RAIZ>"}),
            ("Glob", {"pattern": "**/evals/*.json"}),
            ("Bash", {"command": "grep -rn with_skill ."}),
            ("WebFetch", {"url": "https://github.com/dono-ficticio/fundacao-ia-multiprojetos-skill/blob/main/x.json",
                          "prompt": "leia"}),
            ("Bash", {"command": "curl -s https://raw.githubusercontent.com/dono-ficticio/fundacao-ia-multiprojetos-skill/main/x"}),
        ]
        for uso in casos:
            with self.subTest(uso):
                r = self._estado(uso)
                self.assertEqual(r["estado"], "contaminada", r)

    def test_layout_antigo_o_proprio_caminho_nao_conta(self):
        """Até a 1.7.6 o ambiente ficava dentro da bancada, com o caso e o braço no caminho: o executor que só usa o
        próprio ambiente não é contaminado; subir até o eval_metadata.json é."""
        with tempfile.TemporaryDirectory(prefix="p2-antigo-") as td:
            it = Path(td) / "iteration-1"
            run = it / "eval-7-acesso-entre-projetos" / "with_skill" / "run-1"
            amb, out = run / "ambiente", run / "outputs"
            amb.mkdir(parents=True)
            out.mkdir()
            nomes = self.ve.nomes_do_gabarito(it)
            limpo = _trace(run, ("Bash", {"command": f"python -m fundacao --raiz {amb.as_posix()}/fundacao status"}),
                           ("Write", {"file_path": f"{out.as_posix()}/RELATO.md", "content": "ok"}))
            self.assertEqual(self.ve.acesso_ao_gabarito(limpo, it, nomes, (amb, out))["estado"], "sem_acesso_no_rastro")
            sujo = _trace(run, ("Bash", {"command": "cat ../../../eval_metadata.json"}))
            self.assertEqual(self.ve.acesso_ao_gabarito(sujo, it, nomes, (amb, out))["estado"], "contaminada")

    def test_trabalho_normal_nao_conta(self):
        for uso in (("Bash", {"command": "cat <AMB>/RETOMADA.md"}),
                    ("Bash", {"command": "python -m fundacao --raiz <AMB>/fundacao status"}),
                    ("Read", {"file_path": "<AMB>/fundacao/registry/requisitos.csv"}),
                    ("Bash", {"command": "ls -la .."}),
                    ("Grep", {"pattern": "golden", "path": "<AMB>"}),
                    ("Write", {"file_path": "<AMB>/RETOMADA.md", "content": "evals.json e with_skill no texto"})):
            with self.subTest(uso):
                r = self._estado(uso)
                self.assertEqual((r["estado"], r["usos"]), ("sem_acesso_no_rastro", []), r)


if __name__ == "__main__":
    unittest.main()
