"""RETOMADA enxuta com histórico arquivado e conferido (proposta 7 da análise do vibe-coding-toolkit, 21/10/2026).

A RETOMADA real tinha 37.893 bytes, 165 linhas e 19 linhas com mais de 400 caracteres, e toda sessão nova a lê
inteira. Agora o `validar` avisa (sem bloquear) acima de 12 KB, 150 linhas ou linha com mais de 600
caracteres; o `arquivar` guarda a versão inteira em evidence/retomada/, confere byte a byte e acrescenta o
ponteiro com o SHA-256; o `validar` passa a recusar ponteiro para histórico ausente ou alterado e a conferir
que cada item de "Ações já realizadas que não devem ser repetidas" do histórico continua listado no índice
(pela parte antes do primeiro ":"). Pastas descartáveis.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from apoio import rodar_script
from test_retomada import OBRIGATORIOS, preencher

ITENS = ["- Backup pos-b4-001 no D: (rótulo não se reutiliza): verificado, 12 tarefas, 93 eventos",
         "- Pedido do B3 req_40c491ba (reenviar devolve a mesma tarefa): entrega v1 em outputs/",
         "- Liberação da 1.5.1: GitHub b96a9e6, perfil às 23:48, fundação às 23:56"]


class TestRetomadaArquivar(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="retomada-arquivar-"))
        self.arq = self.base / "RETOMADA.md"
        self.historico = self.base / "evidence" / "retomada"

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def escrever(self, extra: str = "", itens=ITENS) -> str:
        valores = dict(OBRIGATORIOS)
        valores["Ações já realizadas que não devem ser repetidas:"] = ""
        texto = preencher(valores).replace("Ações já realizadas que não devem ser repetidas: \n",
                                           "Ações já realizadas que não devem ser repetidas:\n" + "\n".join(itens) + "\n")
        self.arq.write_text(texto + extra, encoding="utf-8")
        return texto + extra

    def rodar(self, *args):
        p = rodar_script("retomada.py", *args)
        try:
            return p.returncode, json.loads(p.stdout)
        except ValueError:
            self.fail("saída não é JSON: " + p.stdout[-400:] + p.stderr[-400:])

    def test_validar_avisa_tamanho_sem_bloquear(self):
        self.escrever("Sessão antiga: " + "x" * 700 + "\n" + "linha de histórico\n" * 700)
        code, res = self.rodar("validar", "--arquivo", self.arq)
        self.assertEqual(code, 0, res)
        avisos = " ".join(res["avisos"])
        for trecho in ("KB", "linhas", "600 caracteres", "arquivar"):
            self.assertIn(trecho, avisos)

    def test_arquivar_guarda_inteiro_confere_e_aponta(self):
        original = self.escrever("Sessão antiga: muito texto de histórico.\n")
        code, res = self.rodar("arquivar", "--arquivo", self.arq, "--historico", self.historico)
        self.assertEqual(code, 0, res)
        guardado = Path(res["historico"])
        self.assertEqual(guardado.read_text(encoding="utf-8"), original)
        self.assertIn(res["sha256"], self.arq.read_text(encoding="utf-8"))
        self.assertEqual(res["itens_nao_repetir"], 3)
        code, val = self.rodar("validar", "--arquivo", self.arq)
        self.assertEqual(code, 0, val)
        self.assertEqual(val["historicos"][0]["estado"], "conferido")
        code, res2 = self.rodar("arquivar", "--arquivo", self.arq, "--historico", self.historico,
                                "--nome", guardado.name)
        self.assertEqual(code, 1, res2)                                           # não sobrescreve
        self.assertIn("já existe", res2["erro"])

    def test_validar_recusa_historico_alterado_e_item_esquecido(self):
        self.escrever()
        code, res = self.rodar("arquivar", "--arquivo", self.arq, "--historico", self.historico)
        self.assertEqual(code, 0, res)
        texto = self.arq.read_text(encoding="utf-8")
        compacto = texto.replace(ITENS[1] + "\n", "")                              # item esquecido no índice
        self.arq.write_text(compacto, encoding="utf-8")
        code, val = self.rodar("validar", "--arquivo", self.arq)
        self.assertEqual(code, 1, val)
        self.assertEqual(val["itens_do_historico_ausentes"], ["Pedido do B3 req_40c491ba (reenviar devolve a mesma tarefa)"])
        reescrito = texto.replace(ITENS[0], "- Backup pos-b4-001 no D: (rótulo não se reutiliza): ver histórico")
        self.arq.write_text(reescrito, encoding="utf-8")
        code, val = self.rodar("validar", "--arquivo", self.arq)                   # resumido, mesma chave: vale
        self.assertEqual(code, 0, val)
        guardado = Path(res["historico"])
        guardado.write_text(guardado.read_text(encoding="utf-8") + "adulterado\n", encoding="utf-8")
        code, val = self.rodar("validar", "--arquivo", self.arq)
        self.assertEqual(code, 1, val)
        self.assertEqual(val["historicos"][0]["estado"], "alterado")


if __name__ == "__main__":
    unittest.main()
