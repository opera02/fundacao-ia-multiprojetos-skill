"""CLI `conhecimento`: pedir o conteúdo de um projeto pelo serviço, mesmo esperando recusa (1.7.9).

A leitura autorizada existia só no servidor MCP (listar_documentos e buscar) e na API Python. Sem comando na CLI, o
agente que olha a ajuda não achava como pedir o conteúdo, e nenhuma negativa ficava na trilha."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

from helpers import CANARIOS, FoundationTestCase

from fundacao.core.knowledge import KnowledgeService

APROVADO = {c: {"resultado": "aprovado", "evidencia": f"conferido contra a página ({c})"}
            for c in ("origem", "fidelidade", "vigencia", "acesso", "finalidade")}
LONGO = ("Aurora " + "procedimentoexemplificativo " * 5) * 40  # trechos de 80 palavras com mais de 500 caracteres


class TestCliConhecimento(FoundationTestCase):
    def _cli(self, principal: str, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "FUNDACAO_PRINCIPAL"}
        env.update(PYTHONDONTWRITEBYTECODE="1", FUNDACAO_PRINCIPAL=principal)
        return subprocess.run([sys.executable, "-m", "fundacao", "--raiz", str(self.root), *args],
                              capture_output=True, text=True, encoding="utf-8", cwd=str(self.root), env=env)

    def _negativas(self, principal: str) -> int:
        return self.con.execute("SELECT COUNT(*) FROM event WHERE kind='access_denied' AND subject=?",
                                (principal,)).fetchone()[0]

    def setUp(self):
        super().setUp()
        self.write_data("juridico-lab", "catalog.json", json.dumps({"doc-aurora-01": "notas.md"}))
        self.write_data("juridico-lab", "notas.md", CANARIOS["juridico-lab"])

    def _publicar(self):
        kj, kr = KnowledgeService(self.root, self.con, self.jur), KnowledgeService(self.root, self.con, self.revisor)
        self.write_data("juridico-lab", "fontes/guia.md", LONGO + CANARIOS["juridico-lab"])
        kj.register_source("juridico-lab", "juridico-lab/GUIA-AURORA", 1, "fontes/guia.md")
        h = kj.prepare("juridico-lab/GUIA-AURORA", 1, [LONGO + CANARIOS["juridico-lab"]])
        kj.index("juridico-lab/GUIA-AURORA", 1)
        kr.curate("juridico-lab/GUIA-AURORA", 1, APROVADO, h, review_due="2026-11-18", purpose="laboratório")
        self.con.commit()

    def _negado(self, p):
        self.assertEqual(p.returncode, 2, p.stdout)
        erro = json.loads(p.stderr)["error"]
        self.assertEqual((erro["code"], erro["action"]), ("E_ACCESS_DENIED", "read"))
        self.assertEqual(p.stdout, "")
        self.assertNotIn(CANARIOS["juridico-lab"], p.stderr)
        self.assertNotIn("doc-aurora-01", p.stderr)

    def test_listar_do_proprio_projeto(self):
        p = self._cli("operador-juridico", "conhecimento", "listar", "--projeto", "juridico-lab")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout), {"projeto": "juridico-lab", "documentos": ["doc-aurora-01"]})

    def test_outro_projeto_e_negado_com_evento_e_sem_conteudo(self):
        self._publicar()  # a busca negada teria trecho aprovado a devolver
        for args in (("listar",), ("buscar", "--consulta", "Aurora"), ("buscar",)):  # buscar sem consulta também
            with self.subTest(args=args):
                antes = self._negativas("operador-engenharia")
                self._negado(self._cli("operador-engenharia", "conhecimento", *args, "--projeto", "juridico-lab"))
                self.assertEqual(self._negativas("operador-engenharia"), antes + 1)

    def test_autoriza_antes_de_ler_o_catalogo(self):
        # Catálogo ilegível: quem não pode ler recebe a negativa (com evento), não o erro do arquivo.
        self.write_data("juridico-lab", "catalog.json", "[{\"id\": 1}, {\"id\": 2}]")
        antes = self._negativas("operador-engenharia")
        self._negado(self._cli("operador-engenharia", "conhecimento", "listar", "--projeto", "juridico-lab"))
        self.assertEqual(self._negativas("operador-engenharia"), antes + 1)
        p = self._cli("operador-juridico", "conhecimento", "listar", "--projeto", "juridico-lab")
        self.assertEqual(p.returncode, 2, p.stdout)  # catálogo malformado: erro do contrato, sem traceback
        self.assertEqual(json.loads(p.stderr)["error"]["code"], "E_VALIDATION")

    def test_buscar_devolve_trecho_aprovado_com_citacao_e_corte(self):
        self._publicar()
        p = self._cli("operador-juridico", "conhecimento", "buscar", "--projeto", "juridico-lab", "--consulta",
                      "Aurora")
        self.assertEqual(p.returncode, 0, p.stderr)
        r = json.loads(p.stdout)
        self.assertEqual(r["projeto"], "juridico-lab")
        self.assertTrue(r["trechos"])
        for t in r["trechos"]:
            self.assertEqual(set(t), {"citacao", "trecho"})
            self.assertTrue(t["citacao"].startswith("juridico-lab/GUIA-AURORA"))
            self.assertEqual(len(t["trecho"]), 500)  # o trecho tem mais de 500 caracteres: sai cortado, como no MCP
        p = self._cli("operador-engenharia", "conhecimento", "buscar", "--projeto", "reversa-lab")
        self.assertEqual(p.returncode, 0, p.stderr)  # sem termos e sem índice: vazio
        self.assertEqual(json.loads(p.stdout), {"projeto": "reversa-lab", "trechos": []})

    def test_projeto_inexistente_responde_como_negado(self):
        antes = self._negativas("operador-engenharia")
        p = self._cli("operador-engenharia", "conhecimento", "listar", "--projeto", "projeto-fic-inexistente")
        self.assertEqual(p.returncode, 2, p.stdout)
        self.assertEqual(json.loads(p.stderr)["error"]["code"], "E_ACCESS_DENIED")
        self.assertEqual(self._negativas("operador-engenharia"), antes + 1)

    def test_identidade_ausente_ou_nao_registrada_nao_le(self):
        env = {k: v for k, v in os.environ.items() if k != "FUNDACAO_PRINCIPAL"}
        p = subprocess.run([sys.executable, "-m", "fundacao", "--raiz", str(self.root), "conhecimento", "listar",
                            "--projeto", "juridico-lab"], capture_output=True, text=True, encoding="utf-8",
                           cwd=str(self.root), env=env)
        self.assertEqual(p.returncode, 2, p.stdout)
        self.assertNotIn("doc-aurora-01", p.stdout + p.stderr)
        p = self._cli("identidade-fic-desconhecida", "conhecimento", "listar", "--projeto", "juridico-lab")
        self.assertEqual(p.returncode, 2, p.stdout)
        self.assertNotIn("doc-aurora-01", p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
