"""Avisos de terceiros (1.7.7; método adaptado de Harness², proposta P6).

`AVISOS-DE-TERCEIROS.md`, na raiz da skill ao lado do `LICENSE.txt`, vai no pacote instalável. Cada origem externa
citada no pacote (a skill sem `evals/`) ou nas notas de versão tem ali uma entrada com projeto, commit analisado,
licença, nomes no texto e o tipo de aproveitamento (ideia ou trecho); entrada do tipo trecho traz o aviso de
copyright e o texto da licença. Critério de citação, escrito no próprio arquivo: um dos "Nomes no texto" de uma
entrada ou um rótulo de origem com nome de repositório (`análise do <projeto>`, `[Decisão; <projeto>, ...]`,
`método adaptado de <projeto>`). Antes desta versão, o modelo de revisão de segurança traduzido do vibe-coding-toolkit
(MIT) ia no pacote sem o aviso de copyright do toolkit.

Revisão de segurança da 1.7.7, R177-VAL-10: a entrada do everything-claude-code não listava as propostas 1
(inventário dos plugins) e 4 (avaliações repetidas), rotuladas no código. Agora cada rótulo de proposta do pacote e
das notas — `<projeto>, [<data>, ]proposta N`, `<projeto>, P<n>` ou `proposta N da análise do <projeto>` — precisa
estar em "Propostas aproveitadas" da entrada daquele projeto.
"""

from __future__ import annotations

import re
import unittest

from apoio import SKILL

AVISOS = SKILL / "AVISOS-DE-TERCEIROS.md"
NOTAS = SKILL.parent / "entrega" / "README-ENTREGA.md"
PROJETO = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+|[a-z]+[0-9][a-z0-9]*"
ROTULOS = (re.compile(rf"\banálise d[oa] ({PROJETO})\b"),
           re.compile(rf"\[Decisão; (?:análise d[oa] )?({PROJETO}),"),
           re.compile(rf"\bmétodo adaptado de ({PROJETO})\b"))
CAMPOS = ("Projeto", "Commit analisado", "Licença", "Nomes no texto", "Aproveitamento")
TIPOS = ("ideia", "trecho")
TEXTO_MIT = "Permission is hereby granted, free of charge, to any person obtaining a copy"
NUMEROS = r"P?\d+(?:(?:,\s*|\s+e\s+)P?\d+)*"  # "4", "2 e 3", "P1, P2 e P4"
COM_HIFEN = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+"   # projeto ainda sem entrada (sem hífen, "p125" seria página do livro)


def ler_entradas(texto: str) -> tuple[dict, list]:
    """{nome: {campo: valor, "corpo": texto da seção}} e os problemas de forma de cada entrada."""
    entradas, problemas = {}, []
    for bloco in re.split(r"(?m)^## +", texto)[1:]:
        cabeca, _, corpo = bloco.partition("\n")
        nome, campos, atual = cabeca.strip(), {}, None
        for linha in corpo.splitlines():
            m = re.match(r"^- ([^:]+):\s*(.*)$", linha)
            if m:
                atual = m.group(1)
                campos[atual] = m.group(2).strip()
            elif atual and linha[:2] == "  " and linha.strip():
                campos[atual] += " " + linha.strip()
            else:
                atual = None
        faltam = [c for c in CAMPOS if not campos.get(c)]
        if faltam:
            problemas.append(f"{nome}: faltam {', '.join(faltam)}")
            continue
        nomes = [n.strip() for n in campos["Nomes no texto"].split(",") if n.strip()]
        tipo = campos["Aproveitamento"].strip(" .")
        if nome not in nomes:
            problemas.append(f"{nome}: o título precisa estar entre os nomes no texto")
        if not re.search(r"`[0-9a-f]{7,40}`", campos["Commit analisado"]):
            problemas.append(f"{nome}: commit analisado sem hash entre crases")
        if tipo not in TIPOS:
            problemas.append(f"{nome}: aproveitamento precisa ser {' ou '.join(TIPOS)}")
        elif tipo == "trecho" and not (re.search(r"(?m)^Copyright \(c\) \d{4} \S", corpo) and TEXTO_MIT in corpo):
            problemas.append(f"{nome}: trecho exige o aviso de copyright e o texto da licença no arquivo")
        entradas[nome] = {**campos, "nomes": nomes, "tipo": tipo, "corpo": corpo}
    return entradas, problemas


def origens_citadas(textos: dict, entradas: dict) -> dict:
    """{origem: arquivos que a citam}: pelos nomes das entradas ou por um rótulo de origem com nome de repositório."""
    por_nome = {n.lower(): chave for chave, e in entradas.items() for n in e["nomes"]}
    citadas: dict = {}
    for arquivo, texto in textos.items():
        for chave, e in entradas.items():
            if any(n in texto for n in e["nomes"]):
                citadas.setdefault(chave, set()).add(arquivo)
        for rx in ROTULOS:
            for m in rx.finditer(texto):
                citadas.setdefault(por_nome.get(m.group(1).lower(), m.group(1)), set()).add(arquivo)
    return citadas


def propostas_citadas(textos: dict, entradas: dict) -> dict:
    """{origem: {número: arquivos}} dos rótulos de proposta — `<projeto>, [<data>, ]proposta(s) N`, `<projeto>, P<n>`
    e `proposta(s) N da análise do <projeto>`, com quebra de linha entre as palavras —, pelo nome da entrada."""
    por_nome = {n.lower(): chave for chave, e in entradas.items() for n in e["nomes"]}
    nome = "|".join([*map(re.escape, sorted(por_nome, key=len, reverse=True)), COM_HIFEN])
    com_nome = re.compile(rf"(?i:(?<![\w-])({nome})),\s+(?:\d{{2}}/\d{{2}}/\d{{4}},\s+)?"
                          rf"(?:[Pp]ropostas?\s+({NUMEROS})|(P\d+(?:(?:,\s*|\s+e\s+)P\d+)*))(?!\.\d)\b")
    da_analise = re.compile(rf"\b[Pp]ropostas?\s+({NUMEROS})\s+da\s+análise\s+d[oa]\s+(?i:({nome}))(?![\w-])")
    citadas: dict = {}
    for arquivo, texto in textos.items():
        achados = [(m.group(1), m.group(2) or m.group(3)) for m in com_nome.finditer(texto)]
        achados += [(m.group(2), m.group(1)) for m in da_analise.finditer(texto)]
        for nome_citado, numeros in achados:
            origem = por_nome.get(nome_citado.lower(), nome_citado)
            for n in re.findall(r"\d+", numeros):
                citadas.setdefault(origem, {}).setdefault(int(n), set()).add(arquivo)
    return citadas


def propostas_registradas(entrada: dict) -> set:
    """Números do campo "Propostas aproveitadas" da entrada (o texto entre parênteses é a descrição)."""
    lista = re.sub(r"\([^)]*\)", "", entrada.get("Propostas aproveitadas", ""))
    return {int(n) for n in re.findall(r"\bP?(\d+)\b", lista)}


def textos_do_pacote_e_das_notas() -> dict:
    textos = {}
    for arq in sorted(SKILL.rglob("*")):
        rel = arq.relative_to(SKILL).as_posix()
        if (not arq.is_file() or rel.startswith("evals/") or "__pycache__" in rel or arq.suffix == ".pyc"
                or arq == AVISOS):
            continue
        try:
            textos[rel] = arq.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
    if NOTAS.is_file():  # existe na árvore de desenvolvimento e na cópia pública; não no pacote instalado
        textos["entrega/README-ENTREGA.md"] = NOTAS.read_text(encoding="utf-8")
    return textos


class TestAvisosDeTerceiros(unittest.TestCase):
    def setUp(self):
        self.texto = AVISOS.read_text(encoding="utf-8")
        self.entradas, self.problemas = ler_entradas(self.texto)

    def test_arquivo_na_raiz_do_pacote_ao_lado_da_licenca_em_lf(self):
        self.assertTrue((SKILL / "LICENSE.txt").is_file())
        self.assertNotIn(b"\r\n", AVISOS.read_bytes())
        self.assertIn("scripts/tests/test_avisos_de_terceiros.py", self.texto)  # o critério aponta este teste

    def test_entradas_completas(self):
        self.assertEqual(self.problemas, [])
        self.assertEqual(sorted(self.entradas), ["everything-claude-code", "harness2", "vibe-coding-toolkit"])

    def test_cada_origem_citada_tem_entrada_e_cada_entrada_e_citada(self):
        citadas = origens_citadas(textos_do_pacote_e_das_notas(), self.entradas)
        self.assertEqual({o: sorted(a)[:3] for o, a in citadas.items() if o not in self.entradas}, {})
        self.assertEqual(sorted(set(self.entradas) - set(citadas)), [])

    def test_trecho_do_toolkit_traz_aviso_e_licenca_mit(self):
        toolkit = self.entradas["vibe-coding-toolkit"]
        self.assertEqual((toolkit["tipo"], toolkit["Licença"].split()[0]), ("trecho", "MIT"))
        self.assertIn("`790a895`", toolkit["Commit analisado"])
        self.assertIn("Copyright (c) 2026 Matheus Gomes", toolkit["corpo"])
        self.assertIn("The above copyright notice and this permission notice shall be included", toolkit["corpo"])
        self.assertIn("`assets/templates/REVISAO-SEGURANCA.md`", toolkit["Trechos, traduzidos e adaptados"])

    def test_harness2_e_everything_claude_code_so_como_ideia(self):
        harness, ecc = self.entradas["harness2"], self.entradas["everything-claude-code"]
        self.assertEqual((harness["tipo"], ecc["tipo"]), ("ideia", "ideia"))
        self.assertIn("`1cfe254`", harness["Commit analisado"])
        self.assertTrue(harness["Licença"].startswith("Apache-2.0"))
        self.assertIn("método adaptado de Harness² (arXiv:2610.14224, github.com/google-research/harness2, commit "
                      "1cfe254, Apache-2.0)", harness["Atribuição"])
        self.assertIn("`432485b`", ecc["Commit analisado"])
        self.assertIn("não confirmada", ecc["Licença"])
        self.assertIn("Harness²", harness["nomes"])

    def test_origem_nova_sem_entrada_e_acusada(self):
        textos = {"a.md": "[Decisão; " + "análise do " + "projeto-novo" + ", 2026]",
                  "b.md": "Regra " + "método adaptado de " + "outro9" + " (artigo).",
                  "c.md": "análise " + "de 21/10/2026; análise do dossiê; [Decisão; 1.7.0, avaliação]"}
        citadas = origens_citadas(textos, self.entradas)
        self.assertEqual(sorted(o for o in citadas if o not in self.entradas), ["outro9", "projeto-novo"])
        self.assertEqual(citadas["projeto-novo"], {"a.md"})

    def test_cada_proposta_rotulada_esta_na_entrada(self):
        citadas = propostas_citadas(textos_do_pacote_e_das_notas(), self.entradas)
        faltam = {f"{origem}, proposta {n}": sorted(arquivos)[:3] for origem, numeros in citadas.items()
                  for n, arquivos in numeros.items()
                  if origem not in self.entradas or n not in propostas_registradas(self.entradas[origem])}
        self.assertEqual(faltam, {})
        self.assertEqual(sorted(citadas), ["everything-claude-code", "harness2", "vibe-coding-toolkit"])
        self.assertEqual(propostas_registradas(self.entradas["everything-claude-code"]), {1, 3, 4, 5})

    def test_proposta_rotulada_sem_registro_e_acusada(self):
        # Rótulos partidos com "+": este arquivo também é do pacote e não pode citar proposta que não existe.
        textos = {"a.md": "[Decisão; everything-claude-code, " + "proposta 9]",
                  "b.md": "(análise do vibe-coding-toolkit, 21/10/2026,\n  " + "propostas 16 e 17)",
                  "c.md": "[Decisão; harness2, " + "P7, P8 e P9]",
                  "d.md": "método adaptado de Harness², " + "proposta P10",
                  "e.md": "(proposta 18 da " + "análise do\nvibe-coding-toolkit)",
                  "f.md": "[Decisão; " + "outro-novo, " + "P2]",
                  "g.md": "(análise do vibe-coding-toolkit, " + "21/10/2026); proposta 3.0; [Livro p125, " + "P03]"}
        citadas = propostas_citadas(textos, self.entradas)
        self.assertEqual({o: sorted(ns) for o, ns in citadas.items()},
                         {"everything-claude-code": [9], "vibe-coding-toolkit": [16, 17, 18],
                          "harness2": [7, 8, 9, 10], "outro-novo": [2]})
        registradas = {o: propostas_registradas(e) for o, e in self.entradas.items()}
        self.assertTrue(all(n not in registradas[o] for o, ns in citadas.items() if o in registradas for n in ns))
        self.assertEqual(propostas_registradas({"Propostas aproveitadas": "1 (inventário, R54 e E10), P3 e 4"}),
                         {1, 3, 4})

    def test_nome_registrado_e_rotulo_contam_para_a_mesma_entrada(self):
        textos = {"x.md": "ver Harness² e o repositório", "y.md": "[Decisão; " + "harness2, P3]"}
        self.assertEqual(origens_citadas(textos, self.entradas), {"harness2": {"x.md", "y.md"}})

    def test_entrada_incompleta_ou_trecho_sem_licenca_e_acusada(self):
        base = ("## exemplo-a\n\n- Projeto: github.com/fulano/exemplo-a\n- Commit analisado: `abcdef1`\n"
                "- Licença: MIT\n- Nomes no texto: exemplo-a\n- Aproveitamento: {tipo}\n")
        casos = {base.format(tipo="trecho"): "trecho exige o aviso de copyright",
                 base.format(tipo="parcial"): "aproveitamento precisa ser",
                 base.format(tipo="ideia").replace("`abcdef1`", "abcdef1"): "commit analisado sem hash",
                 base.format(tipo="ideia").replace("- Licença: MIT\n", ""): "faltam Licença",
                 base.format(tipo="ideia").replace("Nomes no texto: exemplo-a", "Nomes no texto: outro"):
                     "o título precisa estar entre os nomes"}
        for texto, trecho in casos.items():
            with self.subTest(trecho=trecho):
                _, problemas = ler_entradas(texto)
                self.assertTrue(any(trecho in p for p in problemas), problemas)
        com_licenca = base.format(tipo="trecho") + "\n```text\nCopyright (c) 2026 Fulano\n\n" + TEXTO_MIT + "\n```\n"
        self.assertEqual(ler_entradas(com_licenca)[1], [])


if __name__ == "__main__":
    unittest.main()
