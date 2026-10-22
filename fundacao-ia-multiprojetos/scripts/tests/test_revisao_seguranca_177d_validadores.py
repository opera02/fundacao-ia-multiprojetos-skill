"""Revisão de segurança da 1.7.7, quarta passada — o caminho acima da raiz da fundação (R177D-1).

- R177D-1 (média, regressão do R177C-B-01): `caminho_negado` aplicava a lista de negação (`*secret*`, `*credentials*`,
  `.env*`, `~<dígito>`) a todas as partes do caminho real, também às de cima da raiz da fundação, que o host não nega
  (as regras dele são `./**/...`, relativas à raiz). Uma fundação em `...\\Users\\Secretaria\\Projeto de IA` (ou na
  conta "Secretário", ou sob `credentials-antigas`) tinha toda evidência recusada ("base das evidências recusada") e a
  RETOMADA recusada no `validar` e no `arquivar`: o critério de conclusão nunca se cumpria. Agora o caminho inteiro só
  é conferido sem raiz de fundação acima; com raiz, valem as partes relativas a ela (como na segunda passada) e, em
  qualquer lugar, só `.ssh` e `.codex`, que os perfis do host negam em `~/` — uma `registry/` plantada em `.ssh` não
  devolve o oráculo.

Pastas descartáveis com estrutura fictícia (o apoio de test_auditoria_1_7_6_validadores.py). Cada teste falha no HEAD
revisado (59b3813) e passa depois da correção; os controles mostram o uso legítimo.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import test_auditoria_1_7_6_validadores as base_176  # o módulo, não as classes: os testes dela não rodam de novo aqui
from apoio import rodar_script
from test_auditoria_1_7_6_validadores import SEGREDO, _Pastas, carregar

MATRIZ, RETOMADA = base_176.TestMatrizEvidencia.__dict__, base_176.TestRetomadaHistorico.__dict__  # os ajudantes
CONTAS = ("Secretaria", "Secretário", "credentials-antigas", "Recepcao~1")  # partes acima da raiz que casam a lista
OUTRO = "texto que não está em arquivo nenhum"  # a versão que não é citada: a resposta não pode mudar com ela


class _Fundacoes(_Pastas):
    matriz, ativo, problemas = MATRIZ["matriz"], MATRIZ["ativo"], MATRIZ["problemas"]
    ITENS, texto_retomada, historico = RETOMADA["ITENS"], RETOMADA["texto_retomada"], RETOMADA["historico"]

    def fundacao(self, *partes: str) -> Path:
        raiz = self.base.joinpath(*partes)
        (raiz / "registry").mkdir(parents=True)
        for rel, texto in (("evidence/kit/EVIDENCIAS-A5.md", "Ensaio do kit 1.4.1 (fictício).\n"),
                           ("projects/a/evidence/EVIDENCIAS-R60.md", "Python 3.12.10 (fictício).\n")):
            (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
            (raiz / rel).write_text(texto, encoding="utf-8")
        return raiz

    def json_de(self, *args, timeout: int = 120) -> tuple[int, dict, str]:
        p = rodar_script(*args, timeout=timeout)
        try:
            return p.returncode, json.loads(p.stdout), p.stdout
        except ValueError:
            self.fail("saída não é JSON: " + p.stdout[-400:] + p.stderr[-400:])


class TestFundacaoSobPastaComNomeDaLista(_Fundacoes):
    """R177D-1: o que fica acima da raiz da fundação não é negado (o host nega `./**/...`, relativo à raiz)."""

    def test_matriz_e_retomada_aceitas_numa_conta_secretaria(self):
        for conta in CONTAS:
            with self.subTest(conta=conta):
                raiz = self.fundacao("Users", conta, "Projeto de IA")
                mat = self.matriz({"R01": self.ativo("evidence/kit/EVIDENCIAS-A5.md"),
                                   "R60": self.ativo("projects/a/evidence/EVIDENCIAS-R60.md", "Python 3.12.10")},
                                  raiz / "registry" / "requisitos.csv")
                codigo, dados, _ = self.json_de("matriz.py", "validar", "--matriz", mat)
                self.assertEqual(codigo, 0, dados["erros"])  # no 59b3813: "base das evidências recusada"
                self.assertEqual(dados["evidencias"]["conferidas"], ["R01", "R60"])
                mat = self.matriz({"R60": self.ativo("evidence/EVIDENCIAS-R60.md", "Python 3.12.10")},
                                  raiz / "projects" / "a" / "registry" / "requisitos.csv")  # base padrão: o projeto
                codigo, dados, _ = self.json_de("matriz.py", "validar", "--matriz", mat)
                self.assertEqual(dados["evidencias"]["conferidas"], ["R60"], dados["erros"])
                arq = raiz / "RETOMADA.md"
                arq.write_text(self.texto_retomada([], self.ITENS), encoding="utf-8")
                codigo, res, _ = self.json_de("retomada.py", "arquivar", "--arquivo", arq, "--historico",
                                              raiz / "evidence" / "retomada", timeout=60)
                self.assertEqual(codigo, 0, res)  # no 59b3813: "a pasta da RETOMADA fica em pasta que o host nega"
                codigo, res, _ = self.json_de("retomada.py", "validar", "--arquivo", arq, timeout=60)
                self.assertEqual(codigo, 0, res)
                self.assertEqual([h["estado"] for h in res["historicos"]], ["conferido"])

    def test_controle_sem_raiz_acima_ssh_e_dentro_da_raiz_continuam_recusados(self):
        home = self.base / "home-falso"
        ssh = home / ".ssh"
        ssh.mkdir(parents=True)
        (ssh / "id_ed25519").write_text(f"conteúdo fictício: kit 1.4.1 {SEGREDO}\n", encoding="utf-8")
        (home / "secrets").mkdir()
        (home / "secrets" / "x.md").write_text(f"kit 1.4.1 {SEGREDO}\n", encoding="utf-8")
        raiz = self.fundacao("Users", "Titular", "Projeto de IA")
        (raiz / "projects" / "secretaria-juridica" / "evidence").mkdir(parents=True)
        (raiz / "projects" / "secretaria-juridica" / "evidence" / "x.md").write_text(f"kit 1.4.1 {SEGREDO}\n",
                                                                                      encoding="utf-8")
        mat = raiz / "registry" / "requisitos.csv"
        casos = [(ssh, "id_ed25519", False), (home / "secrets", "x.md", False),       # sem raiz acima: o inteiro
                 (raiz, "projects/secretaria-juridica/evidence/x.md", False),          # dentro da raiz: o relativo
                 (ssh, "id_ed25519", True)]  # `.ssh` com cara de raiz (registry/): o host nega ~/.ssh mesmo assim
        for base, rel, registry_em_ssh in casos:
            if registry_em_ssh:
                (ssh / "registry").mkdir()
            with self.subTest(base=base.name, rel=rel, registry_em_ssh=registry_em_ssh):
                vistas = set()
                for versao in ("kit 1.4.1", OUTRO):
                    codigo, dados, saida = self.json_de("matriz.py", "validar", "--matriz",
                                                        self.matriz({"R12": self.ativo(rel, versao)}, mat),
                                                        "--base", base)
                    self.assertEqual(dados["evidencias"]["conferidas"], [], "a evidência protegida foi lida")
                    self.assertNotIn(SEGREDO, saida)
                    vistas.add(self.problemas(dados)["R12"])
                self.assertEqual(len(vistas), 1, f"a resposta varia com o conteúdo: {vistas}")

    def test_fundacao_dentro_de_ssh_continua_recusada(self):
        raiz = self.fundacao("home-falso", ".ssh", "fundacao")  # o host nega ~/.ssh/** mesmo com a raiz lá dentro
        mat = self.matriz({"R01": self.ativo("evidence/kit/EVIDENCIAS-A5.md")}, raiz / "registry" / "requisitos.csv")
        codigo, dados, _ = self.json_de("matriz.py", "validar", "--matriz", mat)
        self.assertEqual(codigo, 1)
        self.assertEqual(dados["evidencias"]["conferidas"], [])
        self.assertIn("nada foi lido", self.problemas(dados)["R01"])

    def test_regra_com_e_sem_raiz(self):
        for nome in ("matriz", "retomada"):
            mod = carregar(nome)
            with self.subTest(modulo=nome):
                raiz = self.base / nome / "Users" / "Secretaria" / "Projeto de IA"
                (raiz / "registry").mkdir(parents=True)
                self.assertFalse(mod.protegido_na_fundacao(raiz, ["evidence", "a.md"]))       # acima da raiz: livre
                self.assertTrue(mod.protegido_na_fundacao(raiz, ["secrets", "a.md"]))         # relativo à raiz: negado
                self.assertTrue(mod.protegido_na_fundacao(raiz.parent, ["x", "a.md"]))        # sem raiz: o inteiro
                self.assertTrue(mod.caminho_negado(raiz / ".ssh" / "a", [raiz]))              # .ssh: em qualquer lugar
                self.assertFalse(mod.caminho_negado(raiz / "a", [raiz]))
                self.assertTrue(mod.caminho_negado(raiz / "a"))                               # sem raiz informada


if __name__ == "__main__":
    unittest.main()
