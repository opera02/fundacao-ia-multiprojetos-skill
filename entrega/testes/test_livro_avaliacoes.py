"""Livro-caixa e identidade das rodadas de avaliação (harness2, P1).

Método adaptado de Harness² (arXiv:2610.14224, github.com/google-research/harness2, commit 1cfe254, Apache-2.0).
Reproduz, com transcrições fictícias e sem chamar modelo, o que aconteceu nas iterações 3 e 4 do AVALIACOES.md:
a partida interrompida que não entrou na conta do teto de 1, o modelo anotado de memória (opus × sonnet), campos
ausentes que viravam 0 e o resultado de um texto da skill (commit 2b6ec26) citado depois que o texto mudou.
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
LIVRO = EVALS / "livro_avaliacoes.py"
ESPERADO = "claude-sonnet-5-5"


def rodar(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=600)


def _modulo(nome: str, caminho: Path):
    spec = importlib.util.spec_from_file_location(nome, caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def setUpModule():
    """Pasta temporária própria (base_temporaria.py; revisão de segurança da 1.7.7, terceira passada, R177C-T-01): a
    área do executor e as pastas dos testes não dependem do que há na pasta temporária da máquina."""
    unittest.addModuleCleanup(_modulo("base_temporaria", Path(__file__).with_name("base_temporaria.py")).ligar())


def transcricao(pasta: Path, nome: str, modelo: str | None = ESPERADO, resultado: dict | None = None) -> Path:
    """Rastro no formato stream-json: system/init, uma mensagem do assistente e o result."""
    eventos = []
    if modelo:
        eventos.append({"type": "system", "subtype": "init", "model": modelo, "session_id": "s1"})
    eventos.append({"type": "assistant", "message": {"model": modelo or "x", "content": [{"type": "text", "text": "ok"}]}})
    eventos.append({"type": "result", "subtype": "success", "is_error": False,
                    **({"duration_ms": 413000, "num_turns": 54, "total_cost_usd": 1.51,
                        "usage": {"input_tokens": 10, "cache_creation_input_tokens": 5,
                                  "cache_read_input_tokens": 100, "output_tokens": 7}}
                       if resultado is None else resultado)})
    arq = pasta / nome
    arq.write_text("\n".join(json.dumps(e) for e in eventos) + "\n", encoding="utf-8")
    return arq


class TestLivroAvaliacoes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory(prefix="p1-")
        cls.t = Path(cls._td.name)
        cls.skill = cls.t / "skill" / "fundacao-ia-multiprojetos"
        _modulo("iso_p1", EVALS / "isolamento.py").copiar_skill(SKILL, cls.skill)

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def abrir(self, nome: str, teto: int, *bracos: str, codigo: int = 0) -> Path:
        livro = self.t / nome
        r = rodar(LIVRO, "abrir", "--livro", livro, "--autorizacao", "Sim: nova execução da E10 (teto de 1 execução)",
                  "--data", "2026-10-21", "--teto", teto, "--modelo-esperado", ESPERADO,
                  *[x for b in (bracos or (f"with_skill={self.skill}",)) for x in ("--braco", b)])
        self.assertEqual(r.returncode, codigo, r.stdout + r.stderr)
        return livro

    def test_teto_1_partida_interrompida_conta_e_a_segunda_e_recusada_sem_gravar(self):
        livro = self.abrir("teto-1", 1)
        self.assertEqual(rodar(LIVRO, "iniciar", "--livro", livro, "--rotulo", "E10-r1", "--avaliacao", 10,
                               "--braco", "with_skill").returncode, 0)
        r = rodar(LIVRO, "fechar", "--livro", livro, "--rotulo", "E10-r1", "--estado", "interrompida")
        self.assertEqual(r.returncode, 0, r.stderr)
        antes = (livro / "livro.json").read_bytes()
        r = rodar(LIVRO, "iniciar", "--livro", livro, "--rotulo", "E10-r2", "--avaliacao", 10, "--braco", "with_skill")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("teto atingido", r.stderr)
        self.assertEqual((livro / "livro.json").read_bytes(), antes, "a recusa gravou no livro")

    def test_rotulo_repetido_e_recusado(self):
        livro = self.abrir("rotulo", 3)
        args = ("iniciar", "--livro", livro, "--rotulo", "E10-r1", "--avaliacao", 10, "--braco", "with_skill")
        self.assertEqual(rodar(LIVRO, *args).returncode, 0)
        r = rodar(LIVRO, *args)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("rótulo repetido", r.stderr)
        self.assertEqual(rodar(LIVRO, "iniciar", "--livro", livro, "--rotulo", "../fora", "--avaliacao", 10,
                               "--braco", "with_skill").returncode, 2)

    def test_modelo_da_transcricao_diferente_do_esperado_faz_o_conferir_falhar(self):
        livro = self.abrir("modelo", 2)
        for rotulo, modelo in (("E10-r1", ESPERADO), ("E10-r2", "claude-opus-5-5")):
            self.assertEqual(rodar(LIVRO, "iniciar", "--livro", livro, "--rotulo", rotulo, "--avaliacao", 10,
                                   "--braco", "with_skill").returncode, 0)
            r = rodar(LIVRO, "fechar", "--livro", livro, "--rotulo", rotulo, "--estado", "concluida",
                      "--transcricao", transcricao(self.t, f"{rotulo}.jsonl", modelo))
            self.assertEqual(r.returncode, 0, r.stderr)
        r = rodar(LIVRO, "conferir", "--livro", livro)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        relatorio = json.loads(r.stdout)
        self.assertEqual(len(relatorio["problemas"]), 1, relatorio)
        self.assertIn("claude-opus-5-5", relatorio["problemas"][0])
        self.assertIn(ESPERADO, relatorio["problemas"][0])
        self.assertRegex(relatorio["livro_sha256"], r"^[0-9a-f]{64}$")
        guardada = livro / "transcricoes" / "E10-r1.jsonl"
        self.assertEqual(guardada.read_bytes(), (self.t / "E10-r1.jsonl").read_bytes())

    def test_custo_e_turnos_ausentes_ficam_unknown_nunca_zero(self):
        livro = self.abrir("ausentes", 1)
        self.assertEqual(rodar(LIVRO, "iniciar", "--livro", livro, "--rotulo", "E11-r1", "--avaliacao", 11,
                               "--braco", "with_skill").returncode, 0)
        r = rodar(LIVRO, "fechar", "--livro", livro, "--rotulo", "E11-r1", "--estado", "concluida",
                  "--transcricao", transcricao(self.t, "ausentes.jsonl", resultado={}))
        self.assertEqual(r.returncode, 0, r.stderr)
        medidas = json.loads(r.stdout)["medidas"]
        self.assertEqual(medidas["modelo"], ESPERADO)
        self.assertEqual((medidas["turnos"], medidas["duracao_s"]), ("unknown", "unknown"))
        self.assertEqual(medidas["consumo"]["custo_usd"], "unknown")
        self.assertEqual(set(medidas["consumo"]["tokens"].values()), {"unknown"})
        self.assertNotIn(0, [medidas["turnos"], medidas["duracao_s"], medidas["consumo"]["custo_usd"]])
        self.assertEqual(rodar(LIVRO, "conferir", "--livro", livro).returncode, 0)

    def test_skill_mudada_depois_da_execucao_faz_a_validade_acusar_outro_texto(self):
        copia = self.t / "skill-validade" / "fundacao-ia-multiprojetos"
        shutil.copytree(self.skill, copia)
        livro = self.abrir("validade", 1, f"with_skill={copia}")
        self.assertEqual(rodar(LIVRO, "iniciar", "--livro", livro, "--rotulo", "E10-r1", "--avaliacao", 10,
                               "--braco", "with_skill").returncode, 0)
        self.assertEqual(rodar(LIVRO, "fechar", "--livro", livro, "--rotulo", "E10-r1", "--estado", "concluida",
                               "--transcricao", transcricao(self.t, "valida.jsonl")).returncode, 0)
        r = rodar(LIVRO, "validade", "--livro", livro, "--skill", copia)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["resultados"][0]["situacao"], "vale para o texto atual")
        skill_md = copia / "SKILL.md"
        skill_md.write_text(skill_md.read_text(encoding="utf-8") + "\nRegra nova revisada depois da execução.\n",
                            encoding="utf-8")
        r = rodar(LIVRO, "validade", "--livro", livro, "--skill", copia)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        resultado = json.loads(r.stdout)["resultados"][0]
        self.assertEqual(resultado["situacao"], "resultado de outro texto")
        self.assertEqual(resultado["arquivos_que_diferem"]["alterados"], ["SKILL.md"])
        r = rodar(LIVRO, "iniciar", "--livro", livro, "--rotulo", "E10-r2", "--avaliacao", 10, "--braco", "with_skill")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)

    def test_abrir_sobre_o_livro_de_outro_experimento_e_recusado(self):
        livro = self.abrir("outro", 1)
        self.abrir("outro", 1)  # a mesma identidade: nada muda
        antes = (livro / "livro.json").read_bytes()
        self.abrir("outro", 2, codigo=3)
        self.assertEqual((livro / "livro.json").read_bytes(), antes)

    def test_skill_do_braco_alterada_recusa_iniciar(self):
        copia = self.t / "skill-iniciar" / "fundacao-ia-multiprojetos"
        shutil.copytree(self.skill, copia)
        livro = self.abrir("iniciar", 2, f"with_skill={copia}", "without_skill=")
        (copia / "references" / "nota-nova.md").write_text("texto novo\n", encoding="utf-8")
        r = rodar(LIVRO, "iniciar", "--livro", livro, "--rotulo", "E10-r1", "--avaliacao", 10, "--braco", "with_skill")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("mudou desde o abrir", r.stderr)
        r = rodar(LIVRO, "iniciar", "--livro", livro, "--rotulo", "E10-r1", "--avaliacao", 10,
                  "--braco", "without_skill")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_preparar_com_livro_recusa_alem_do_teto_e_simular_nao_cria_nada(self):
        livro = self.abrir("preparo", 1, f"with_skill={self.skill}", "without_skill=")
        ws = self.t / "ws-preparo"
        preparar = EVALS / "preparar_avaliacoes.py"
        r = rodar(preparar, "--workspace", ws, "--so", "10", "--livro", livro, "--simular")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        plano = json.loads(r.stdout)
        self.assertEqual((plano["partidas"], plano["teto_restante"]), (2, 1))
        self.assertIn("teto", plano["recusaria"])
        r = rodar(preparar, "--workspace", ws, "--so", "10", "--livro", livro)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertFalse(ws.exists(), "a recusa criou a bancada")
        self.assertEqual([p.name for p in self.t.iterdir() if p.name.startswith("trabalho-")], [])
        r = rodar(preparar, "--workspace", ws, "--so", "8", "--livro", livro, "--simular")  # E8: só com a skill
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([p["braco"] for p in json.loads(r.stdout)["plano"]], ["with_skill"])
        self.assertFalse(ws.exists(), "a simulação criou a bancada")


if __name__ == "__main__":
    unittest.main()
