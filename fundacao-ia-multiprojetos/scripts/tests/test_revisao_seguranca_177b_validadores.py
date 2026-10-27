"""Revisão de segurança da 1.7.7, segunda passada — o `--base` da matriz e a pasta da RETOMADA (variante do
R177-VAL-01).

A recusa de caminho protegido olhava só a parte relativa à base: `state` só como primeira parte dela, e
`projects/<p>/data` só quando o `data` estava nela. Quem escolhia a base escolhia o que era protegido: com a matriz em
`projects/a/outputs/m.csv`, `--base <raiz>/state` (linha `state.sqlite`), `--base <pai da raiz>` (linha
`<raiz>/state/state.sqlite`) e `--base <raiz>/projects/b/data` (linha `caso.md`) saíam "conferidas" quando o texto
estava no arquivo e "não cita a versão" quando não — o oráculo de conteúdo de volta, também pela pasta de evidência. Na
RETOMADA, a pasta dela faz o papel da base, e o histórico conferido entregava os itens dele. Agora `protegido()` vale
também para o caminho inteiro, relativo a cada raiz de fundação acima dele (a pasta com `registry/` ou com
`state/state.sqlite`), e o `--base` acima da raiz da fundação da matriz ou dentro de caminho protegido é recusado antes
de qualquer evidência ser lida.

Pastas descartáveis com estrutura fictícia (o apoio de test_auditoria_1_7_6_validadores.py). Cada teste falha no HEAD
revisado (4c11fed) e passa depois da correção; os controles mostram o uso legítimo.
"""

from __future__ import annotations

import json
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import test_auditoria_1_7_6_validadores as base_176  # o módulo, não as classes: os testes dela não rodam de novo aqui
from apoio import rodar_script
from test_auditoria_1_7_6_validadores import SEGREDO, _Pastas, carregar, sha_de
from test_revisao_seguranca_177_validadores import CITA

MATRIZ, RETOMADA = base_176.TestMatrizEvidencia.__dict__, base_176.TestRetomadaHistorico.__dict__  # os ajudantes
OUTRO = "texto que não está em arquivo nenhum"  # a versão que não é citada: a resposta não pode mudar com ela


class TestBaseDaMatriz(_Pastas):
    """O `--base` não tira a proteção: acima da raiz ou dentro de caminho protegido, nada é lido."""

    matriz, ativo, problemas = MATRIZ["matriz"], MATRIZ["ativo"], MATRIZ["problemas"]

    def setUp(self):
        super().setUp()
        self.escrever("state/state.sqlite", CITA)  # o banco da fundação fictícia, com o texto que a linha procura
        self.escrever("projects/b/data/caso.md", CITA)
        self.mat = self.raiz / "projects" / "a" / "outputs" / "m.csv"  # onde o agente do projeto a escreve

    def validar(self, linhas: dict, base: Path, onde: Path | None = None) -> tuple[int, dict, str]:
        mat = self.matriz(linhas, onde or self.mat)
        p = rodar_script("matriz.py", "validar", "--matriz", mat, "--base", base, timeout=120)
        try:
            return p.returncode, json.loads(p.stdout), p.stdout
        except ValueError:
            self.fail("saída não é JSON: " + p.stdout[-400:] + p.stderr[-400:])

    def respostas(self, base: Path, rel: str, onde: Path | None = None) -> set[str]:
        """A resposta da linha com a versão citada no arquivo e com a que não é: sem oráculo, as duas são iguais."""
        vistas = set()
        for versao in ("kit 1.4.1", OUTRO):
            codigo, dados, saida = self.validar({"R12": self.ativo(rel, versao)}, base, onde)
            self.assertEqual(codigo, 1, dados)
            self.assertEqual(dados["evidencias"]["conferidas"], [], "a base escolhida tirou a proteção")
            self.assertNotIn(SEGREDO, saida)
            vistas.add(self.problemas(dados)["R12"])
        return vistas

    def test_base_em_state_acima_da_raiz_ou_no_data_de_outro_projeto(self):
        for base, rel in ((self.raiz / "state", "state.sqlite"), (self.base, "fundacao/state/state.sqlite"),
                          (self.raiz / "projects" / "b" / "data", "caso.md")):
            with self.subTest(base=base.name, rel=rel):
                vistas = self.respostas(base, rel)
                self.assertEqual(len(vistas), 1, f"a resposta varia com o conteúdo: {vistas}")
                self.assertNotIn("cita a versão", vistas.pop())

    def test_base_recusada_nao_le_nem_diz_se_existe(self):
        linhas = {"R12": self.ativo("state.sqlite"), "R13": self.ativo("nao-existe.db")}
        codigo, dados, _ = self.validar(linhas, self.raiz / "state")
        self.assertEqual(codigo, 1, dados)
        probs = self.problemas(dados)
        self.assertIn("R12", probs, "a evidência dentro de state/ foi lida e conferida")
        mensagens = {probs[r].split(":", 1)[1].replace(linhas[r]["caminho_evidencia"], "C") for r in linhas}
        self.assertEqual(len(mensagens), 1, f"a resposta varia com o alvo: {mensagens}")
        self.assertIn("base", probs["R12"])

    def test_matriz_fora_da_fundacao_e_pasta_de_evidencia(self):
        """Sem raiz acima da matriz, vale a raiz achada no caminho da evidência; a pasta não abre o protegido."""
        fora = self.fora / "m.csv"
        for rel in ("fundacao/state/state.sqlite", "fundacao/state/nao-existe.db", "fundacao/projects/b/data/caso.md"):
            with self.subTest(rel=rel):
                vistas = self.respostas(self.base, rel, fora)
                self.assertEqual(len(vistas), 1, vistas)
                self.assertIn("protegido", vistas.pop())
        self.escrever("projects/a/evidence/leia-me.md", "sem versão\n")
        codigo, dados, saida = self.validar({"R12": self.ativo("fundacao")}, self.base, fora)  # a raiz como pasta
        self.assertEqual(dados["evidencias"]["conferidas"], [], "a pasta de evidência leu o banco ou o data/")
        self.assertIn("cita a versão", self.problemas(dados)["R12"])

    def test_controle_bases_legitimas(self):
        self.escrever("projects/a/evidence/EVIDENCIAS-R60.md", "Python 3.12.10 (fictício).\n")
        self.escrever("projects/a/evidence/state/notas.md", "Python 3.12.10 (fictício).\n")  # `state` de projeto
        linhas = {"R12": self.ativo("evidence/EVIDENCIAS-R60.md", "Python 3.12.10"),
                  "R13": self.ativo("evidence/state/notas.md", "Python 3.12.10")}
        codigo, dados, _ = self.validar(linhas, self.raiz / "projects" / "a")
        self.assertEqual(codigo, 0, dados["erros"])
        self.assertEqual(dados["evidencias"]["conferidas"], ["R12", "R13"])
        linhas = {r: {**v, "caminho_evidencia": "projects/a/" + v["caminho_evidencia"]} for r, v in linhas.items()}
        codigo, dados, _ = self.validar(linhas, self.raiz)
        self.assertEqual(dados["evidencias"]["conferidas"], ["R12", "R13"], dados["erros"])

    def test_criterio_igual_na_matriz_e_na_retomada(self):
        matriz, retomada = carregar("matriz"), carregar("retomada")
        for base, rel in ((self.raiz / "state", "state.sqlite"), (self.base, "fundacao/state/x"),
                          (self.raiz / "projects" / "b" / "data", "caso.md"), (self.raiz, "evidence/a.md"),
                          (self.base, "fundacao/projects/a/evidence/a.md"), (self.raiz / "projects" / "a", "data/x")):
            with self.subTest(base=base.name, rel=rel):
                partes = rel.split("/")
                self.assertEqual(matriz.protegido_na_fundacao(base, partes),
                                 retomada.protegido_na_fundacao(base, partes))
        self.assertTrue(matriz.protegido_na_fundacao(self.base, ["fundacao", "state", "x"]))
        self.assertFalse(matriz.protegido_na_fundacao(self.base, ["fundacao", "evidence", "a.md"]))


class TestPastaDaRetomada(_Pastas):
    """Na RETOMADA, a pasta dela faz o papel da base: acima da raiz ou dentro de caminho protegido, nada é lido."""

    ITENS, texto_retomada, historico = RETOMADA["ITENS"], RETOMADA["texto_retomada"], RETOMADA["historico"]

    def setUp(self):
        super().setUp()
        (self.raiz / "registry").mkdir()  # a outra forma de raiz (a matriz usa o banco)

    def validar_em(self, pasta: Path, ponteiro: str) -> tuple[int, dict, str]:
        arq = pasta / "RETOMADA.md"
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(self.texto_retomada([ponteiro], self.ITENS), encoding="utf-8")
        p = rodar_script("retomada.py", "validar", "--arquivo", arq, timeout=60)
        try:
            return p.returncode, json.loads(p.stdout), p.stdout
        except ValueError:
            self.fail("saída não é JSON: " + p.stdout[-400:] + p.stderr[-400:])

    def test_retomada_acima_da_raiz_ou_em_pasta_protegida_nao_le_o_historico(self):
        item = [f"- Item de dentro {SEGREDO}: não deveria aparecer"]
        for pasta, rel in ((self.base, "fundacao/state/hist.md"), (self.raiz / "state", "hist.md"),
                           (self.raiz / "projects" / "b" / "data", "hist.md")):
            with self.subTest(pasta=pasta.name, rel=rel):
                h = self.historico(pasta / rel, item)
                codigo, res, saida = self.validar_em(pasta, f"Histórico arquivado: {rel} (sha256 {h})")
                self.assertEqual(codigo, 1, res)
                self.assertNotIn(SEGREDO, saida, "o validar leu o histórico protegido e entregou o item")
                if pasta == self.base:
                    self.assertIn("protegido", res["historicos"][0]["estado"])
                else:
                    # A recusa mais recente protege a própria RETOMADA antes de ler o ponteiro.
                    self.assertEqual(set(res), {"ok", "erro"})
                    self.assertFalse(res["ok"])
                    self.assertIn("host nega à leitura", res["erro"])
                    self.assertIn("nada foi lido nem gravado", res["erro"])

    def test_retomada_protegida_recusa_antes_dos_leitores_e_sem_oraculo_de_existencia(self):
        retomada = carregar("retomada")
        for pasta in (self.raiz / "state", self.raiz / "projects" / "b" / "data"):
            arq = pasta / "RETOMADA.md"
            arq.parent.mkdir(parents=True, exist_ok=True)
            respostas = []
            for presente in (True, False):
                with self.subTest(pasta=pasta.name, presente=presente):
                    if presente:
                        arq.write_text(SEGREDO, encoding="utf-8")
                    else:
                        arq.unlink()
                    saida = io.StringIO()
                    with mock.patch.object(retomada, "ler_retomada", side_effect=AssertionError("leu RETOMADA")), \
                         mock.patch.object(retomada, "ler_historico", side_effect=AssertionError("leu histórico")), \
                         mock.patch.object(retomada.sys, "argv", ["retomada.py", "validar", "--arquivo", str(arq)]), \
                         redirect_stdout(saida):
                        codigo = retomada.main()
                    self.assertEqual(codigo, 1)
                    respostas.append(json.loads(saida.getvalue()))
                    self.assertNotIn(SEGREDO, saida.getvalue())
            self.assertEqual(respostas[0], respostas[1])
            self.assertEqual(set(respostas[0]), {"ok", "erro"})
            self.assertFalse(respostas[0]["ok"])

    def test_arquivar_acima_da_raiz_nao_grava_em_caminho_protegido(self):
        arq = self.base / "RETOMADA.md"
        arq.write_text(self.texto_retomada([], self.ITENS), encoding="utf-8")
        antes = sha_de(arq)
        for pasta in (self.raiz / "state" / "historico", self.raiz / "projects" / "b" / "data"):
            with self.subTest(pasta=pasta.relative_to(self.base).as_posix()):
                p = rodar_script("retomada.py", "arquivar", "--arquivo", arq, "--historico", pasta, timeout=60)
                self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
                self.assertIn("protegido", json.loads(p.stdout)["erro"])
                self.assertEqual(sha_de(arq), antes, "a RETOMADA foi alterada")
                self.assertFalse(pasta.exists(), "o histórico foi gravado no caminho protegido")
        livre = self.base / "evidence" / "retomada"  # controle: fora do protegido, arquiva
        p = rodar_script("retomada.py", "arquivar", "--arquivo", arq, "--historico", livre, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
