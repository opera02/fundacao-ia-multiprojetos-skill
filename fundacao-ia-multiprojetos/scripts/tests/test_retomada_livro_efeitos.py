"""Livro de efeitos ancorado por hash (1.7.10, seção 2 do escopo: o validar da RETOMADA).

O validar exigia no índice uma linha por item de "Ações já realizadas" de cada histórico arquivado: a RETOMADA da raiz
chegou a 174 linhas e 25 KB, e o aviso de tamanho ficou permanente. Agora `arquivar --consolidar-efeitos` grava o livro
EFEITOS-REALIZADOS-<data>.md (arquivo novo) com as chaves de todos os efeitos — do índice, dos históricos e do livro
anterior — e o ponteiro "Efeitos arquivados: <caminho> (sha256 <hash>)"; o validar aceita o item no índice OU no livro
conferido, com as mesmas proteções do histórico. Pastas descartáveis com dados fictícios."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from apoio import SCRIPTS, rodar_script
from test_retomada import OBRIGATORIOS, preencher

ITENS = ["- Backup pos-ficticio-001 no D: (rótulo não se reutiliza): verificado, 12 tarefas",
         "- Pedido req_ficticio_01 (reenviar devolve a mesma tarefa): entrega v1 em outputs/",
         "- Liberação da 9.9.8: GitHub abc1234, perfil às 23:48",
         "- Cópia de referência do projeto-ficticio: manifesto conferido"]


class TestLivroDeEfeitos(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="retomada-livro-"))
        self.arq = self.base / "RETOMADA.md"
        self.historico = self.base / "evidence" / "retomada"

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def escrever(self, itens, minimos: str = "") -> None:
        valores = dict(OBRIGATORIOS)
        valores["Ações já realizadas que não devem ser repetidas:"] = ""
        efeitos = ("\n" + "\n".join(itens)) if itens else " ver o livro de efeitos"  # sem item: o campo diz onde
        texto = preencher(valores).replace("Ações já realizadas que não devem ser repetidas: \n",
                                           "Ações já realizadas que não devem ser repetidas:" + efeitos + "\n")
        if minimos:
            texto = texto.replace("1. evidence/ambiente/inventario-2026-10-20.json",
                                  "1. evidence/ambiente/inventario-2026-10-20.json\n2. " + minimos)
        self.arq.write_text(texto, encoding="utf-8")

    def manter_ponteiros(self, itens, minimos: str = "") -> None:
        """Reescreve o índice só com `itens`, mantendo os ponteiros que o arquivar pôs."""
        ponteiros = [l for l in self.arq.read_text(encoding="utf-8").splitlines()
                     if l.startswith(("Histórico arquivado:", "Efeitos arquivados:"))]
        self.escrever(itens, minimos)
        self.arq.write_text("\n".join(ponteiros) + "\n" + self.arq.read_text(encoding="utf-8"), encoding="utf-8")

    def rodar(self, *args):
        p = rodar_script("retomada.py", *args)
        try:
            return p.returncode, json.loads(p.stdout)
        except ValueError:
            self.fail("saída não é JSON: " + p.stdout[-400:] + p.stderr[-400:])

    def validar(self):
        return self.rodar("validar", "--arquivo", self.arq)

    def arquivar(self, *extra):
        return self.rodar("arquivar", "--arquivo", self.arq, "--historico", self.historico, *extra)

    def test_item_no_livro_conferido_dispensa_a_linha_no_indice(self):
        self.escrever(ITENS)
        code, res = self.arquivar()
        self.assertEqual(code, 0, res)
        self.manter_ponteiros(ITENS[3:])
        code, val = self.validar()
        self.assertEqual(code, 1, val)  # sem o livro, os itens do histórico continuam exigidos no índice
        self.assertEqual(len(val["itens_do_historico_ausentes"]), 3)
        code, res = self.arquivar("--nome", "RETOMADA-2.md", "--consolidar-efeitos")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["chaves_no_livro"], 4)
        livro = Path(res["livro"])
        self.assertTrue(livro.name.startswith("EFEITOS-REALIZADOS-"))
        self.assertIn("Efeitos arquivados: evidence/retomada/" + livro.name, self.arq.read_text(encoding="utf-8"))
        code, val = self.validar()
        self.assertEqual(code, 0, val)
        self.assertEqual([(e["estado"], e["itens"]) for e in val["efeitos_arquivados"]], [("conferido", 4)])
        self.assertIn("Arquivos mínimos para leitura", " ".join(val["avisos"]))  # o livro ainda não foi citado
        self.manter_ponteiros([], minimos="evidence/retomada/" + livro.name)
        code, val = self.validar()
        self.assertEqual(code, 0, val)
        self.assertNotIn("Arquivos mínimos para leitura", " ".join(val["avisos"]))

    def test_item_fora_do_indice_e_do_livro_reprova_e_livro_alterado_reprova(self):
        self.escrever(ITENS[:2])
        self.assertEqual(self.arquivar("--consolidar-efeitos")[0], 0)
        self.manter_ponteiros(ITENS[:2] + ITENS[2:3])  # um item novo, só no índice
        self.assertEqual(self.arquivar("--nome", "RETOMADA-2.md")[0], 0)  # histórico sem consolidar
        self.manter_ponteiros([])  # o item novo saiu do índice e não está no livro
        code, val = self.validar()
        self.assertEqual(code, 1, val)
        self.assertEqual(val["itens_do_historico_ausentes"], ["Liberação da 9.9.8"])
        livro = next(self.historico.glob("EFEITOS-REALIZADOS-*.md"))
        self.manter_ponteiros(ITENS[2:3])
        self.assertEqual(self.validar()[0], 0)
        livro.write_text(livro.read_text(encoding="utf-8") + "- Efeito inventado\n", encoding="utf-8")
        code, val = self.validar()
        self.assertEqual(code, 1, val)
        self.assertEqual(val["efeitos_arquivados"][0]["estado"], "alterado")

    def test_consolidar_duas_vezes_preserva_as_chaves_e_deixa_um_ponteiro(self):
        self.escrever(ITENS[:3])
        code, res = self.arquivar("--consolidar-efeitos")
        self.assertEqual(code, 0, res)
        self.manter_ponteiros(ITENS[3:])  # o índice enxuto: os três primeiros só no livro
        code, res = self.arquivar("--nome", "RETOMADA-2.md", "--consolidar-efeitos")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["chaves_no_livro"], 4)
        texto = self.arq.read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"^Efeitos arquivados:", texto, re.M)), 1)
        self.assertEqual(len(re.findall(r"^Histórico arquivado:", texto, re.M)), 2)
        self.assertEqual(len(list(self.historico.glob("EFEITOS-REALIZADOS-*.md"))), 2)  # o anterior não é apagado
        self.manter_ponteiros([])
        code, val = self.validar()
        self.assertEqual(code, 0, val)

    def test_livro_em_caminho_protegido_ou_fora_da_pasta_nao_e_lido(self):
        self.escrever(ITENS[:1])
        for caminho, estado in (("state/EFEITOS-REALIZADOS-x.md", "caminho protegido"),
                                ("../EFEITOS-REALIZADOS-x.md", "fora da pasta")):
            with self.subTest(caminho=caminho):
                self.arq.write_text("Efeitos arquivados: " + caminho + " (sha256 " + "a" * 64 + ")\n"
                                    + self.arq.read_text(encoding="utf-8"), encoding="utf-8")
                code, val = self.validar()
                self.assertEqual(code, 1, val)
                self.assertIn(estado, val["efeitos_arquivados"][0]["estado"])
                self.escrever(ITENS[:1])

    def test_livro_com_vinculo_fisico_nao_e_lido(self):
        self.escrever(ITENS[:2])
        code, res = self.arquivar("--consolidar-efeitos")
        self.assertEqual(code, 0, res)
        livro = Path(res["livro"])
        fora = self.base.parent / (self.base.name + "-fora.md")  # mesmo conteúdo, fora da pasta da RETOMADA
        fora.write_bytes(livro.read_bytes())
        self.addCleanup(fora.unlink, missing_ok=True)
        livro.unlink()
        try:
            os.link(fora, livro)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"vínculo físico indisponível aqui: {exc}")
        code, val = self.validar()
        self.assertEqual(code, 1, val)
        self.assertIn("vínculo físico", val["efeitos_arquivados"][0]["estado"])

    def test_consolidar_com_ponteiro_que_nao_confere_nao_altera_nada(self):
        self.escrever(ITENS)
        self.arq.write_text("Histórico arquivado: evidence/retomada/sumiu.md (sha256 " + "b" * 64 + ")\n"
                            + self.arq.read_text(encoding="utf-8"), encoding="utf-8")
        antes = self.arq.read_bytes()
        code, res = self.arquivar("--consolidar-efeitos")
        self.assertEqual(code, 1, res)
        self.assertIn("não confere", res["erro"])
        self.assertEqual(self.arq.read_bytes(), antes)
        self.assertFalse(self.historico.exists())

    def test_limites_dos_avisos_de_tamanho_nao_mudaram(self):
        spec = importlib.util.spec_from_file_location("_retomada_limites", SCRIPTS / "retomada.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual((mod.LIMITE_BYTES, mod.LIMITE_LINHAS, mod.LIMITE_LINHA), (12_000, 150, 600))


if __name__ == "__main__":
    unittest.main()
