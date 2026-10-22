"""Mudança → efeito → veredito e lições com evidência (1.7.7; método adaptado de Harness², proposta P3).

`entrega/licoes.py validar` confere os `entrega/licoes/MUDANCAS-<versão>.md`: vocabulário fechado, efeito "não
observado" só com "sem efeito observado", evidência que existe na árvore com a grafia exata (relativa, contida, sem
ligação e fora das pastas que a cópia pública não leva), nenhum caminho pessoal nem e-mail, lição apoiada só em
"confundido" sem confiança alta, no máximo três lições ou SEM_ENTRADA, LF, e o `LICOES.md` igual ao que o `indice`
gera. Árvores descartáveis com arquivos fictícios; o último caso confere a árvore real.
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
RAIZ = ENTREGA.parent
CABECALHO = ("| # | Componente | O que mudou | Motivo observado (onde) | Efeito observado (onde) | Veredito |",
             "|---|---|---|---|---|---|")


def carregar_modulo():
    spec = importlib.util.spec_from_file_location("licoes_em_teste", ENTREGA / "licoes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LICOES = carregar_modulo()


def linha(ident="M1", veredito="ajudou", efeito="o caso fictício passa (`notas/NOTA.md`)", motivo="falhou o caso"):
    return f"| {ident} | `skill/scripts/a.py` | mudou a regra | {motivo} | {efeito} | {veredito} |"


def licao(ident="L1", evidencia="M1; `notas/NOTA.md`; commit `abc1234`", confianca="média", extra=""):
    return (f"### {ident} — Título fictício\n- Gatilho: situação fictícia.\n- Lição: faça a coisa fictícia;\n"
            f"  e confira.\n- Evidência: {evidencia}\n- Confiança: {confianca}\n{extra}")


def mudancas(versao="9.9.1", linhas=None, licoes=None, cabecalho=None):
    return "\n".join([f"# Mudanças da {versao}", "",
                      cabecalho if cabecalho is not None else f"Versão: {versao} · Registro: teste.", "",
                      "## Mudanças", "", *CABECALHO, *(linhas or [linha()]), "",
                      "## Lições", "", licao() if licoes is None else licoes, ""])


class TestLicoes(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="licoes-teste-"))
        self.pasta = self.raiz / "entrega" / "licoes"
        self.pasta.mkdir(parents=True)
        for rel in ("notas/NOTA.md", "entrega/auditoria/privado.md"):
            (self.raiz / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.raiz / rel).write_text("conteúdo fictício\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.raiz, ignore_errors=True)

    def escrever(self, texto, versao="9.9.1"):
        (self.pasta / f"MUDANCAS-{versao}.md").write_text(texto, encoding="utf-8", newline="\n")

    def reescrever(self, texto, versao="9.9.1"):
        for antigo in self.pasta.glob("*.md"):
            antigo.unlink()
        self.escrever(texto, versao)

    def problemas(self):
        LICOES.indice(self.raiz)
        return LICOES.validar(self.raiz)["problemas"]

    def assertProblema(self, trecho, texto=None):
        if texto is not None:
            self.reescrever(texto)
        problemas = self.problemas()
        self.assertTrue(any(trecho in p for p in problemas), problemas)

    def assertSemProblema(self, texto):
        self.reescrever(texto)
        self.assertEqual(self.problemas(), [])

    def test_arquivo_valido_e_indice_refeito_duas_vezes_igual(self):
        self.escrever(mudancas())
        self.escrever(mudancas("9.9.10", licoes="SEM_ENTRADA"), "9.9.10")
        self.assertEqual(LICOES.indice(self.raiz)["acao"], "criar")
        antes = (self.pasta / "LICOES.md").read_bytes()
        self.assertEqual(LICOES.indice(self.raiz)["acao"], "igual")
        self.assertEqual((self.pasta / "LICOES.md").read_bytes(), antes)
        res = LICOES.validar(self.raiz)
        self.assertEqual((res["ok"], res["licoes"], res["problemas"]), (True, 1, []))
        self.assertEqual(res["arquivos"], ["MUDANCAS-9.9.1.md", "MUDANCAS-9.9.10.md"])  # ordem de versão
        texto = antes.decode("utf-8")
        for trecho in ("| situação fictícia. | faça a coisa fictícia; e confira. | média | 9.9.1, L1",
                       "(SEM_ENTRADA): 9.9.10."):
            self.assertIn(trecho, texto)
        self.assertNotIn(b"\r\n", antes)

    def test_indice_editado_a_mao_e_acusado_e_o_indice_o_refaz(self):
        self.escrever(mudancas())
        LICOES.indice(self.raiz)
        alvo = self.pasta / "LICOES.md"
        alvo.write_text(alvo.read_text(encoding="utf-8") + "| lição inventada | x | alta | 9.9.9 |\n",
                        encoding="utf-8", newline="\n")
        res = LICOES.validar(self.raiz)
        self.assertFalse(res["ok"])
        self.assertIn("diferente do que o indice gera", res["problemas"][0])
        self.assertEqual(LICOES.indice(self.raiz)["acao"], "atualizar")
        self.assertTrue(LICOES.validar(self.raiz)["ok"])

    def test_vocabulario_fechado(self):
        self.assertProblema("veredito fora do vocabulário", mudancas(linhas=[linha(veredito="melhorou")]))
        self.assertProblema("confiança fora do vocabulário", mudancas(licoes=licao(confianca="altíssima")))

    def test_efeito_nao_observado_so_com_sem_efeito_observado(self):
        self.assertProblema("só admite o veredito 'sem efeito observado'",
                            mudancas(linhas=[linha(efeito="não observado (sem nova execução)")]))
        self.assertSemProblema(mudancas(linhas=[linha(efeito="não observado", veredito="sem efeito observado")]))

    def test_evidencia_ausente_contida_e_publica(self):
        casos = {"M1; `notas/AUSENTE.md`": "não existe na árvore",
                 "M1; `notas/nota.md`": "com esta grafia",                       # maiúsculas trocadas
                 "M1; `notas/../notas/NOTA.md`": "'..'",
                 "M1; `/etc/NOTA.md`": "caminho absoluto",
                 "M1; `entrega/auditoria/privado.md`": "cópia pública não leva",
                 "M1; commit `abc1234`": "ao menos um caminho",
                 "`notas/NOTA.md`": "ao menos uma linha da tabela",
                 "M7; `notas/NOTA.md`": "cita M7, que não está na tabela"}
        for evidencia, trecho in casos.items():
            with self.subTest(evidencia=evidencia):
                self.assertProblema(trecho, mudancas(licoes=licao(evidencia=evidencia)))

    def test_evidencia_por_ligacao_recusada(self):
        real = self.raiz / "notas" / "real"
        real.mkdir()
        (real / "ARQ.md").write_text("fictício\n", encoding="utf-8")
        elo = self.raiz / "elo"
        if os.name == "nt":
            r = subprocess.run(["cmd", "/c", "mklink", "/J", str(elo), str(real)], capture_output=True, text=True,
                               errors="replace")
            if r.returncode != 0:
                raise unittest.SkipTest(f"junção indisponível: {r.stdout} {r.stderr}")
        else:
            os.symlink(real, elo, target_is_directory=True)
        self.assertProblema("passa por ligação", mudancas(licoes=licao(evidencia="M1; `elo/ARQ.md`")))

    def test_confianca_alta_so_com_confundido_e_palpite(self):
        confuso = [linha(veredito="confundido")]
        self.assertProblema("é palpite", mudancas(linhas=confuso, licoes=licao(confianca="alta")))
        self.assertSemProblema(mudancas(linhas=confuso, licoes=licao(confianca="média")))
        misto = [linha(veredito="confundido"), linha("M2")]
        self.assertSemProblema(mudancas(linhas=misto, licoes=licao(evidencia="M1, M2; `notas/NOTA.md`",
                                                                    confianca="alta")))

    def test_caminho_pessoal_e_email_recusados(self):
        casos = {"C" + ":" + "\\" + "Users" + "\\" + "fulano" + "\\" + "notas": "caminho absoluto do Windows",
                 "/" + "home/fulano/notas": "pasta de usuário",
                 "fulano" + "@" + "exemplo.com": "e-mail"}
        for valor, trecho in casos.items():
            with self.subTest(trecho=trecho):
                self.assertProblema(trecho, mudancas(linhas=[linha(motivo=f"visto em {valor}")]))

    def test_sem_entrada_limite_e_campos_das_licoes(self):
        quatro = "\n".join(licao(f"L{n}") for n in range(1, 5))
        casos = {"SEM_ENTRADA\n\n" + licao(): "não se mistura",
                 quatro: "o máximo é 3",
                 "": "escreva SEM_ENTRADA",
                 licao() + "\n" + licao(): "sem repetir",
                 licao(extra="- Opinião: fictícia\n"): "campo desconhecido",
                 licao().replace("- Confiança: média\n", ""): "faltam campos: Confiança"}
        for texto, trecho in casos.items():
            with self.subTest(trecho=trecho):
                self.assertProblema(trecho, mudancas(licoes=texto))

    def test_cabecalho_tabela_nome_e_fim_de_linha(self):
        self.assertProblema("'Versão: 9.9.1'", mudancas(cabecalho="Versão: 9.9.3"))
        self.assertProblema("precisa das colunas", mudancas().replace("| Veredito |", "| Nota |", 1))
        self.assertProblema("M1, M2", mudancas(linhas=[linha(ident="X1")]))
        self.assertProblema("componente precisa ser caminho",
                            mudancas(linhas=[linha().replace("`skill/scripts/a.py`", "skill/scripts/a.py")]))
        self.assertProblema("CRLF", mudancas().replace("\n", "\r\n"))
        self.reescrever(mudancas())
        (self.pasta / "MUDANCAS-9.9.1.md").rename(self.pasta / "MUDANCAS-final.md")
        self.assertProblema("nome fora do formato")

    def test_linha_de_comando_codigos_e_json(self):
        def rodar(*args):
            p = subprocess.run([sys.executable, "-B", str(ENTREGA / "licoes.py"), *args, "--raiz", str(self.raiz)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            return p.returncode, json.loads(p.stdout)

        self.escrever(mudancas(linhas=[linha(veredito="melhorou")]))
        code, res = rodar("indice")
        self.assertEqual((code, res["ok"]), (1, False))
        self.assertFalse((self.pasta / "LICOES.md").exists())  # fonte inválida não vira índice
        self.escrever(mudancas())
        self.assertEqual(rodar("validar")[0], 1)                 # índice ausente
        self.assertEqual(rodar("indice"), (0, {"ok": True, "acao": "criar", "arquivo": "entrega/licoes/LICOES.md",
                                               "licoes": 1}))
        self.assertEqual(rodar("validar")[0], 0)

    def test_arvore_real_valida_e_indice_em_dia(self):
        res = LICOES.validar(RAIZ)
        self.assertEqual(res["problemas"], [])
        self.assertGreaterEqual(res["licoes"], 6)


if __name__ == "__main__":
    unittest.main()
