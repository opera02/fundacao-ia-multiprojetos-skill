"""ARVORE-SKILL.md conferido (1.7.10, seção 2 do escopo): na 1.7.9 ele ficou com 290 de 301 arquivos e três sem
descrição, e nada o conferia. `gerar_arvore.py --conferir` não grava e sai com código 1 se o ARVORE difere do que o
gerador escreveria ou tem "(sem descrição)"; este teste roda na CI pública do commit publicado, que só recebe commits
de liberação (o ARVORE é regenerado antes de liberar). Árvores fictícias em pastas temporárias para a regra; a árvore
real só é lida."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENTREGA = Path(__file__).resolve().parents[1]
GERADOR = ENTREGA / "gerar_arvore.py"


def carregar():
    spec = importlib.util.spec_from_file_location("gerar_arvore_1710", GERADOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestConferirArvore(unittest.TestCase):
    def setUp(self):
        self.mod = carregar()
        tmp = tempfile.TemporaryDirectory(prefix="arvore-1710-")
        self.addCleanup(tmp.cleanup)
        self.skill = Path(tmp.name) / "fundacao-ia-multiprojetos"
        for rel in ("SKILL.md", "LICENSE.txt", "references/livro/glossario.md", "scripts/tests/test_a.py"):
            (self.skill / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.skill / rel).write_text("fictício\n", encoding="utf-8")
        self.saida = Path(tmp.name) / "ARVORE-SKILL.md"

    def test_igual_ao_gerado_passa_e_nada_e_gravado(self):
        texto, sem, n = self.mod.montar(self.skill)
        self.assertEqual((sem, n), ([], 4))
        self.saida.write_bytes(texto.replace("\n", "\r\n").encode("utf-8"))  # quebra de linha do Windows não conta
        antes = self.saida.read_bytes()
        res = self.mod.conferir(self.skill, self.saida)
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.saida.read_bytes(), antes)

    def test_desatualizado_ou_sem_descricao_reprova(self):
        texto, _sem, _n = self.mod.montar(self.skill)
        self.saida.write_text(texto, encoding="utf-8", newline="\n")
        (self.skill / "references" / "nova-referencia.md").write_text("fictícia\n", encoding="utf-8")
        res = self.mod.conferir(self.skill, self.saida)
        self.assertFalse(res["ok"])
        self.assertFalse(res["igual_ao_gerado"])
        self.assertEqual(res["sem_descricao"], ["references/nova-referencia.md"])
        self.assertFalse(self.mod.conferir(self.skill, self.saida.with_name("AUSENTE.md"))["ok"])

    def test_arvore_da_skill_confere_com_o_gerador(self):
        """A árvore real: todo arquivo descrito e o ARVORE-SKILL.md regenerado (na integração e antes de liberar)."""
        p = subprocess.run([sys.executable, "-B", str(GERADOR), "--conferir"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        res = json.loads(p.stdout)
        self.assertEqual(res["sem_descricao"], [], "descreva em FINALIDADE (entrega/gerar_arvore.py)")
        self.assertEqual(p.returncode, 0, "rode python entrega/gerar_arvore.py e faça o commit: " + json.dumps(res))


if __name__ == "__main__":
    unittest.main()
