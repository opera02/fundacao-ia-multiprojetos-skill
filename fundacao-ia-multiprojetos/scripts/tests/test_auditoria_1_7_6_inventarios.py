"""Auditoria Codex Security da 1.7.6, #7 — inventários do fluxo B que seguiam ligação de arquivo e não tinham teto.

Até a 1.7.6, `instrucoes_aninhadas.py` (B1) e `sinais_compatibilidade.py` (B3) percorriam a origem importada com
`rglob`, que no Windows atravessa junção, e `is_file()`/`read_bytes()` seguiam o link simbólico de arquivo: o hash, o
`name` de uma skill e as linhas com credencial do outro lado entravam no diagnóstico, antes da aprovação; arquivo,
profundidade e quantidade não tinham teto. Cada teste exige o comportamento seguro e falha na 1.7.6. O teste da
lista do B1 (test_instrucoes_aninhadas) e os cenários CEN-02 e CEN-04 são os controles do uso legítimo.

Pastas descartáveis com estrutura fictícia, com o apoio de test_auditoria_1_7_6_validadores.py (junção no Windows;
link simbólico de arquivo só onde o sistema permite, sem teste pulado).
"""

from __future__ import annotations

import hashlib
import json
import unittest
from unittest import mock

from apoio import criar_ligacao_dir, rodar_script
from test_auditoria_1_7_6_validadores import SEGREDO, Contador, _Pastas, carregar, grande, link_de_arquivo


class TestInventariosDoFluxoB(_Pastas):
    """instrucoes_aninhadas.py (B1) e sinais_compatibilidade.py (B3) não atravessam ligação e têm tetos."""

    def setUp(self):
        super().setUp()
        self.origem = self.raiz  # a origem importada fica no lugar da raiz
        self.escrever("CLAUDE.md", "instrução da origem (dado)")
        self.escrever("squad/notas.py", "x = 1\n")
        (self.fora / "CLAUDE.md").write_text(SEGREDO, encoding="utf-8")
        skill = self.fora / ".claude" / "skills" / "x" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nname: skill-de-fora\n---\n", encoding="utf-8")
        # Valores fictícios com espaço: casam o padrão dos sinais, não o da varredura de segredos do pacote.
        (self.fora / "codigo.py").write_text('api_key = "valor ficticio 1"\nrequests.get("x")\n', encoding="utf-8")

    def inventario(self) -> tuple[int, dict, str]:
        p = rodar_script("instrucoes_aninhadas.py", "listar", "--raiz", self.origem, timeout=120)
        return p.returncode, json.loads(p.stdout), p.stdout

    def sinais(self) -> tuple[dict, str]:
        p = rodar_script("sinais_compatibilidade.py", "--raiz", self.origem, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout), p.stdout

    @staticmethod
    def locais(res: dict) -> list[str]:
        return [loc for v in res["sinais"].values() for loc in v]

    def test_juncao_e_link_de_arquivo_nao_sao_seguidos(self):
        tipo = criar_ligacao_dir(self.origem / "elo", self.fora)
        ligados = ["elo"]
        if link_de_arquivo(self.origem / "AGENTS.md", self.fora / "CLAUDE.md"):
            ligados.append("AGENTS.md")
            link_de_arquivo(self.origem / "ligado.py", self.fora / "codigo.py")
            ligados.append("ligado.py")
        codigo, res, saida = self.inventario()
        caminhos = [i["caminho"] for v in res["itens"].values() for i in v]
        self.assertEqual(caminhos, ["CLAUDE.md"], f"{tipo}: o inventário atravessou a ligação")
        self.assertNotIn("skill-de-fora", saida)
        self.assertNotIn(hashlib.sha256(SEGREDO.encode()).hexdigest(), saida)
        self.assertEqual(sorted(res.get("ligacoes_nao_seguidas", [])), sorted(ligados))
        self.assertEqual(codigo, 1, "inventário com ligação não seguida precisa sair como parcial")
        s, saida = self.sinais()
        self.assertEqual([x for x in self.locais(s) if not x.startswith("squad/")], [],
                         f"{tipo}: os sinais leram o outro lado da ligação")
        self.assertEqual(sorted(s.get("ligacoes_nao_seguidas", [])), sorted(ligados))
        self.assertTrue(any("ligaç" in m for m in s["motivos"]), s["motivos"])

    def test_arquivo_grande_nao_e_lido_inteiro(self):
        teto = getattr(carregar("instrucoes_aninhadas"), "TETO_ARQUIVO", 5_000_000)
        grande(self.origem / "squad" / "AGENTS.md", teto + 1, "instrução enorme")
        codigo, res, _ = self.inventario()
        item = next(i for i in res["itens"]["instrucoes"] if i["caminho"] == "squad/AGENTS.md")
        self.assertIsNone(item["sha256"], "arquivo acima do teto foi lido inteiro")
        self.assertEqual(codigo, 1)
        teto = getattr(carregar("sinais_compatibilidade"), "TETO_ARQUIVO", 5_000_000)
        p = grande(self.origem / "squad" / "enorme.py", teto + 1, "import os\n")
        with p.open("ab") as fh:
            fh.write(b'\n' + 'senha = "valor ficticio 2"'.encode() + b'\n')
        s, _ = self.sinais()
        self.assertEqual(s["sinais"]["credencial_embutida"], [], "arquivo acima do teto foi lido inteiro")
        self.assertIn("squad/enorme.py", [x["caminho"] for x in s.get("nao_lidos", [])])

    def test_teto_de_profundidade(self):
        fundo = self.origem / "fundo"
        for _ in range(36):  # nomes curtos: o caminho fica abaixo de 260 caracteres no Windows
            fundo = fundo / "p"
        (fundo / ".claude" / "skills" / "funda").mkdir(parents=True)
        (fundo / ".claude" / "skills" / "funda" / "SKILL.md").write_text("---\nname: funda\n---\n", encoding="utf-8")
        (fundo / "x.py").write_text('token = "valor ficticio 3"\n', encoding="utf-8")
        codigo, res, _ = self.inventario()
        self.assertEqual(res["itens"]["skills"], [], "a varredura desceu sem teto de profundidade")
        self.assertEqual(codigo, 1)
        s, _ = self.sinais()
        self.assertEqual(s["sinais"]["credencial_embutida"], [])
        self.assertFalse(s.get("completo", True))

    def test_teto_de_itens_vale_durante_a_varredura(self):
        for i in range(3):
            for j in range(100):
                self.escrever(f"g{i}/a{j:03d}.txt", "x")
        for nome, chamar in (("instrucoes_aninhadas", lambda m: m.listar(self.origem.resolve())),
                             ("sinais_compatibilidade", lambda m: m.scan(self.origem.resolve()))):
            with self.subTest(script=nome):
                mod = carregar(nome)
                Contador.total = 0
                with mock.patch("os.scandir", Contador), mock.patch.object(mod, "TETO_ITENS", 50, create=True):
                    res = chamar(mod)
                self.assertLessEqual(Contador.total, 60, "a pasta foi percorrida inteira antes do teto")
                self.assertFalse(res.get("completo", True), res.get("limites_atingidos"))


if __name__ == "__main__":
    unittest.main()
