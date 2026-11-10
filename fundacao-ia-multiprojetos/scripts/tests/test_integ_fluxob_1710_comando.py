"""Segunda revisão do pacote INTEG-FLUXOB (lote 2 da 1.7.10): o comando pronto que o titular cola no terminal dele.

Antes, o B7 do perfil de terceiros e o `comando_de_registro` do `importar.py` punham caminhos e nomes do código
importado (ou escolhidos pela sessão) entre aspas duplas, sem escapar nada: no bash e no PowerShell o `$` e a crase
valem dentro delas, e no Linux o nome pode ter a própria aspa. Um nome preparado mudava o comando que o titular roda
fora de qualquer sandbox. E o B7 dava o `segredos.py conferir` só dos 5 primeiros nomes fracos, mas levava todos
ao manifesto. Agora cada caminho e nome vai entre aspas simples do shell de destino
(`codigo_do_plano.citar_no_terminal`: no sh/bash, `'\\''`; no PowerShell, as cinco aspas simples dobradas), o que não
dá para citar com segurança fica sem comando ("renomeie-o"), e o B7 é um comando só, que confere todos e só com código
0 em todos refaz o manifesto.
Prova: a leitura de cada comando pela regra de cada shell, nos dois sistemas (`shlex` e a regra das aspas simples do
PowerShell), o analisador do PowerShell no Windows e, no sistema de cada um, o B7 rodado de verdade (sh no Linux,
PowerShell no Windows) com nomes hostis que criariam arquivos se escapassem das aspas. Dados fictícios.
"""

from __future__ import annotations

import base64
import glob
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import ENV, rodar_script
from test_integ_fluxob_1710_importar import IMP, _Importacao
from test_integ_fluxob_1710_perfil import EX, SITE, TOKENIZER, _Projeto

CODIGO, PERFIL = EX.CODIGO, EX.PERFIL
NO_WINDOWS = os.name == "nt"
# A regra do PowerShell, independente do código testado: as aspas simples (ASCII e U+2018 a U+201B) e as duplas (ASCII
# e U+201C a U+201E) que o tokenizador dele reconhece (System.Management.Automation.Language.CharExtensions).
ASPAS_PS = ("'",) + tuple(chr(c) for c in (0x2018, 0x2019, 0x201A, 0x201B))
DUPLAS_PS = ('"',) + tuple(chr(c) for c in (0x201C, 0x201D, 0x201E))
POWERSHELL = shutil.which("powershell.exe") if NO_WINDOWS else None
# Nomes hostis: se algum pedaço sair das aspas, o shell cria INJ-* na pasta atual. O do sh tem aspas duplas e barra
# invertida, que o Windows não aceita em nome de arquivo (e que o PowerShell recusa); o de cada sistema vira arquivo. A
# regra única parte o nome também na barra invertida: o pedaço depois dela tem o "token" (para o nome ser fraco). Desde
# a terceira revisão, o do sh não tem aspa simples (nem a ASCII nem as tipográficas, que ele recusa: o texto fica
# literal também no PowerShell); no lugar delas, as aspas duplas tipográficas, que o sh lê como letra.
HOSTIL_PS = "token $(New-Item INJ-a) `$x '; New-Item INJ-b; ' \u2019; New-Item INJ-c; \u2019 \u2018y\u201b [z].py"
HOSTIL_SH = "x \\ \"; touch INJ-d; \" token $(touch INJ-a) `touch INJ-b` \u201c; touch INJ-c; \u201d [z].py"
PASTA_PS = "orig $(New-Item INJ-a) '; New-Item INJ-b; ' \u2019; New-Item INJ-c; \u2019"
PASTA_SH = "orig $(touch INJ-a) `touch INJ-b` \u201c; touch INJ-c; \u201d \"x\" \\ \u201e"
HOSTIL, PASTA_HOSTIL = (HOSTIL_PS, PASTA_PS) if NO_WINDOWS else (HOSTIL_SH, PASTA_SH)
VALORES_HOSTIS = ["a b", "$(id)", "`id`", "'", "it's", '"', "\\", "x\\", "!$&|;<>(){}*?[]#~%", "\u2019",
                  "\u2018x\u201b", "\u201a\u201a", "D:\\Pasta de IA\\x", "/tmp/a b/c", "ç ã ñ 日本"]
PERMITIDOS = {"python", "python3", "-I", "-B", "conferir", "criar", "--raiz", "--saida", "--git", "listar", "ignorar",
              "incluir", "--pasta-segredo", "--incluir-pasta-ignorada", "--excluir", "--incluir-fraco",
              "--texto-canonico", "registrar-projeto", "--projeto", "--origem", "copiar", "--plano", "--plano-sha256"}
SEPARADORES_SH = {"&&"}
SEPARADORES_PS = {";", "if", "($LASTEXITCODE", "-eq", "0)", "{", "}"}


def _fixa(palavra: str) -> bool:
    """Palavra que o comando pronto põe sem aspas: uma das fixas ou um SHA-256."""
    return palavra in PERMITIDOS or bool(re.fullmatch(r"[0-9a-f]{64}", palavra))


def palavras_do_sh(comando: str) -> list[tuple[str, bool]]:
    """(valor, citada) de cada palavra pela regra do sh para o que o comando pronto usa: aspas simples literais e a
    barra invertida fora delas valendo o caractere seguinte; o espaço separa. Na palavra citada, nenhum caractere fica
    solto (fora das aspas e sem barra): o shell o leria."""
    palavras, partes, citada, solta, i = [], [], False, False, 0
    while i <= len(comando):
        c = comando[i] if i < len(comando) else " "
        if c == "'":
            fim = comando.index("'", i + 1)  # ValueError: aspa sem fim
            partes.append(comando[i + 1:fim])
            citada, i = True, fim + 1
        elif c == "\\":
            partes.append(comando[i + 1])
            citada, i = True, i + 2
        elif c == " ":
            if partes:
                valor = "".join(partes)
                assert not (citada and solta), f"caractere solto junto das aspas em {valor!r}: {comando!r}"
                assert citada or _fixa(valor) or valor in SEPARADORES_SH, f"fora das aspas: {valor!r} em {comando!r}"
                palavras.append((valor, citada))
            partes, citada, solta, i = [], False, False, i + 1
        else:
            partes.append(c)
            solta, i = True, i + 1
    return palavras


def cadeias_do_powershell(comando: str) -> tuple[str, list[str]]:
    """(o comando com cada cadeia entre aspas simples trocada por <c>, os valores delas), pela regra do tokenizador do
    PowerShell: qualquer uma das cinco aspas simples abre e fecha, e duas seguidas dentro valem a segunda."""
    fora, cadeias, i = [], [], 0
    while i < len(comando):
        if comando[i] not in ASPAS_PS:
            fora.append(comando[i])
            i += 1
            continue
        i, valor = i + 1, []
        while True:
            if i >= len(comando):
                raise AssertionError(f"cadeia sem fim: {comando!r}")
            if comando[i] in ASPAS_PS:
                if i + 1 < len(comando) and comando[i + 1] in ASPAS_PS:
                    valor.append(comando[i + 1])
                    i += 2
                    continue
                i += 1
                break
            valor.append(comando[i])
            i += 1
        cadeias.append("".join(valor))
        fora.append("<c>")
    return "".join(fora), cadeias


def argvs(comando: str, *, powershell: bool) -> list[list[str]]:
    """Os programas que o comando roda, cada um com os argumentos como o shell os passa. Fora das aspas só pode haver
    as palavras fixas do comando pronto e os separadores (`&&`; no PowerShell, `if ($LASTEXITCODE -eq 0) { ... }`)."""
    if powershell:
        esqueleto, cadeias = cadeias_do_powershell(comando)
        palavras, k = [], 0
        for palavra in esqueleto.replace(";", " ; ").split():
            if palavra == "<c>":
                palavras.append((cadeias[k], True))
                k += 1
            else:
                assert _fixa(palavra) or palavra in SEPARADORES_PS, f"fora das aspas: {palavra!r} em {comando!r}"
                palavras.append((palavra, False))
        separadores = SEPARADORES_PS
    else:
        palavras, separadores = palavras_do_sh(comando), SEPARADORES_SH
        assert [v for v, _c in palavras] == shlex.split(comando), comando  # a mesma leitura do shlex
    comandos, atual = [], []
    for valor, citada in palavras:
        if not citada and valor in separadores:
            if atual:
                comandos.append(atual)
            atual = []
        else:
            atual.append(valor)
    return [*comandos, *([atual] if atual else [])]


def analisador_do_powershell(comando: str) -> tuple[int, list[list[str]]]:
    """(erros, comandos) que o analisador do PowerShell vê (só analisa: nada roda, como no teste E11 do kit): cada
    elemento é o valor da cadeia constante, o texto do parâmetro ou `<Tipo>` do que não é constante."""
    script = (
        "$c = $env:COMANDO_EM_ANALISE; $t = $null; $e = $null; "
        "$a = [System.Management.Automation.Language.Parser]::ParseInput($c, [ref]$t, [ref]$e); 'E ' + $e.Count; "
        "foreach ($k in $a.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true)) {"
        " $l = foreach ($x in $k.CommandElements) {"
        " if ($x -is [System.Management.Automation.Language.StringConstantExpressionAst]) {"
        " 'S:' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($x.Value)) }"
        " elseif ($x -is [System.Management.Automation.Language.CommandParameterAst] -and $null -eq $x.Argument) {"
        " 'S:' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($x.Extent.Text)) }"
        " else { 'X:' + $x.GetType().Name } }; 'C ' + ($l -join ' ') }")
    r = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-EncodedCommand",
                        base64.b64encode(script.encode("utf-16-le")).decode("ascii")], capture_output=True,
                       text=True, errors="replace", timeout=120, env={**os.environ, "COMANDO_EM_ANALISE": comando})
    linhas = r.stdout.split("\n")
    erros = int(next(linha for linha in linhas if linha.startswith("E ")).split()[1])
    comandos = [[base64.b64decode(e[2:]).decode("utf-8") if e.startswith("S:") else f"<{e[2:]}>"
                 for e in linha.split()[1:]] for linha in linhas if linha.startswith("C ")]
    return erros, comandos


def rodar_no_terminal(comando: str, pasta: Path) -> subprocess.CompletedProcess:
    """O comando como o titular o cola: no sh (Linux) ou no PowerShell (Windows), na `pasta`, com o Python dos testes
    no começo do PATH (o comando chama `python3` ou `python`)."""
    env = {**ENV, "PATH": os.path.dirname(sys.executable) + os.pathsep + ENV.get("PATH", "")}
    if NO_WINDOWS:
        script = base64.b64encode((comando + "; exit $LASTEXITCODE").encode("utf-16-le")).decode("ascii")
        args = [POWERSHELL, "-NoProfile", "-NonInteractive", "-EncodedCommand", script]
    else:
        args = ["sh", "-c", comando]
    return subprocess.run(args, cwd=str(pasta), env=env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=600)


class TestCitarNoTerminal(unittest.TestCase):
    def test_cada_valor_hostil_e_um_argumento_literal_nos_dois_shells(self):
        for valor in VALORES_HOSTIS:
            with self.subTest(valor=valor):
                if not set(valor) & set(ASPAS_PS):  # com aspa simples, o sh recusa (terceira revisão)
                    self.assertEqual(shlex.split(CODIGO.citar_no_terminal(valor, powershell=False)), [valor])
                if not (set(valor) & set(DUPLAS_PS) or (valor.endswith("\\") and " " in valor)):
                    self.assertEqual(cadeias_do_powershell(CODIGO.citar_no_terminal(valor, powershell=True)),
                                     ("<c>", [valor]))
        self.assertEqual(CODIGO.citar_no_terminal("D:\\", powershell=True), "'D:\\'")  # sem espaço: passa como está

    def test_o_que_nao_da_para_citar_com_seguranca_e_recusado(self):
        nos_dois = ["", "-x", "a\nb", "a\rb", "a\tb", "a\x00b", "a\u202eb", "a\u200bb", "a\u2028b", "a\x85b"]
        so_no_powershell = ['a"b', "a\u201cb", "a\u201db", "a\u201eb", "C:\\a b\\"]
        for valor in nos_dois + so_no_powershell:
            with self.subTest(valor=ascii(valor)), self.assertRaises(ValueError):
                CODIGO.citar_no_terminal(valor, powershell=True)
        for valor in nos_dois + [v for v in VALORES_HOSTIS if set(v) & set(ASPAS_PS)]:  # o sh, também a aspa simples
            with self.subTest(valor=ascii(valor)), self.assertRaises(ValueError):
                CODIGO.citar_no_terminal(valor, powershell=False)
        self.assertEqual(CODIGO.visivel("a\u202eb"), ascii("a\u202eb"))
        self.assertEqual(CODIGO.visivel("ação $x"), "ação $x")

    @unittest.skipUnless(POWERSHELL, "analisador do PowerShell só no Windows")
    def test_o_analisador_do_powershell_ve_um_argumento_constante(self):
        valores = [v for v in VALORES_HOSTIS if '"' not in v and not v.endswith("\\")]
        comando = "python " + " ".join(CODIGO.citar_no_terminal(v, powershell=True) for v in valores)
        self.assertEqual(analisador_do_powershell(comando), (0, [["python", *valores]]))


class TestComandoDoB7(_Projeto):
    def setUp(self):
        super().setUp()
        self.pasta_do_terminal = self.base / "terminal"  # a pasta atual do shell: os INJ-* cairiam aqui
        self.pasta_do_terminal.mkdir()

    def comando_da_recusa(self, dados: dict) -> str:
        texto = self.recusa_do_plano(dados)
        self.assertIn("(--incluir-fraco): ", texto)
        return texto.split("(--incluir-fraco): ", 1)[1].rsplit(". Depois, ponha o manifesto_sha256", 1)[0]

    def manifesto_novo(self, dados: dict) -> dict:
        dados["codigo"]["manifesto_sha256"] = hashlib.sha256(self.man.read_bytes()).hexdigest()
        return dados

    def caminho(self, rel: str) -> str:
        return os.path.normpath(os.path.join(str(self.tools), *rel.split("/")))

    def test_nome_hostil_vai_literal_ao_programa_e_o_b7_destrava(self):
        rel = f"{SITE}/pkg/{HOSTIL}"
        (self.tools / rel).write_text("X = 1\n", encoding="utf-8")
        dados = self.terceiros(*self.b7())
        comando = self.comando_da_recusa(dados)
        politica = CODIGO.ler_manifesto(self.man.read_bytes())[1]
        for powershell, nome in ((False, HOSTIL_SH), (True, HOSTIL_PS)):  # a leitura de cada shell, nos dois sistemas
            with self.subTest(powershell=powershell):
                outro = f"{SITE}/pkg/{nome}"  # só o texto: o comando não lê o arquivo
                lidos = argvs(PERFIL.comando_do_b7(str(self.tools), str(self.man), politica, [outro],
                                                   powershell=powershell), powershell=powershell)
                self.assertEqual(lidos[0], ["python" if powershell else "python3", "-I", "-B",
                                            str(Path(PERFIL.__file__).resolve().parent / "segredos.py"), "conferir",
                                            self.caminho(outro)])
                criar = lidos[-1]
                self.assertEqual((criar[criar.index("--raiz") + 1], criar[criar.index("--saida") + 1]),
                                 (str(self.tools), str(self.man)))
                fracos = [criar[i + 1] for i, a in enumerate(criar) if a == "--incluir-fraco"]
                self.assertEqual(sorted(fracos), sorted([TOKENIZER, glob.escape(outro)]))
        self.assertEqual(argvs(comando, powershell=NO_WINDOWS)[0][-1], self.caminho(rel))
        if POWERSHELL:
            erros, comandos = analisador_do_powershell(comando)
            self.assertEqual(erros, 0)
            self.assertFalse([e for c in comandos for e in c if e.startswith("<")], comandos)
            self.assertEqual(comandos, argvs(comando, powershell=True))
        if NO_WINDOWS and not POWERSHELL:
            self.skipTest("sem PowerShell para rodar o comando")
        r = rodar_no_terminal(comando, self.pasta_do_terminal)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
        self.assertEqual(os.listdir(self.pasta_do_terminal), [], "nada do nome saiu das aspas")
        manifesto = json.loads(self.man.read_text(encoding="utf-8"))
        self.assertIn(rel, {f["path"] for f in manifesto["arquivos"]}, "o nome chegou literal ao manifesto.py")
        plano = self.plano(self.manifesto_novo(dados), self.argv())
        self.assertEqual(plano["codigo_executado"], EX.PRESO_PELO_PERFIL)

    def test_o_b7_confere_todos_os_nomes_fracos_e_sem_codigo_0_nao_leva_nenhum(self):
        nomes = [f"{SITE}/pkg/token_{i}.py" for i in range(8)]  # mais de 5: antes, só 5 eram conferidos
        for rel in nomes:
            (self.tools / rel).write_text("X = 1\n", encoding="utf-8")
        indicio = self.tools / nomes[4]
        indicio.write_text("api_" + "key = '" + "Ab1" * 6 + "'\n", encoding="utf-8")  # montado: não casa a varredura
        dados = self.terceiros(*self.b7())
        comando = self.comando_da_recusa(dados)
        lidos = argvs(comando, powershell=NO_WINDOWS)
        conferidos = [c[-1] for c in lidos if "conferir" in c]
        self.assertEqual(sorted(conferidos), sorted(self.caminho(r) for r in nomes))
        self.assertEqual(len([a for a in lidos[-1] if a == "--incluir-fraco"]), len(nomes) + 1)
        if NO_WINDOWS and not POWERSHELL:
            self.skipTest("sem PowerShell para rodar o comando")
        antes = self.man.read_bytes()
        r = rodar_no_terminal(comando, self.pasta_do_terminal)
        self.assertNotEqual(r.returncode, 0, "o indício para o comando")
        self.assertEqual(self.man.read_bytes(), antes, "sem código 0 em todos, o manifesto não é refeito")
        indicio.write_text("X = 1\n", encoding="utf-8")
        r = rodar_no_terminal(comando, self.pasta_do_terminal)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
        self.assertEqual(self.plano(self.manifesto_novo(dados), self.argv())["codigo_executado"],
                         EX.PRESO_PELO_PERFIL)

    def test_nome_que_nao_da_para_citar_recusa_sem_comando(self):
        invisivel = f"{SITE}/pkg/token\u202eyp.txt"  # U+202E inverteria o que o titular lê
        (self.tools / invisivel).write_text("X = 1\n", encoding="utf-8")
        texto = self.recusa_do_plano(self.terceiros(*self.b7()))
        self.assertIn("renomeie-o", texto)
        self.assertNotIn("\u202e", texto, "o nome sai como ascii")
        self.assertIn(ascii("token\u202eyp.txt")[1:-1], texto)
        self.assertNotIn("criar --raiz", texto, "sem comando pronto")


class TestComandoDoImportar(_Importacao):
    def raiz_sem_registro(self, nome: str) -> Path:
        """Outra raiz de fundação fictícia, `<base>/<nome>`, com o projeto proj-a e sem o registro de origens; o plano
        passa a usá-la (a raiz de `_Importacao` já tem o registro)."""
        raiz = self.base / nome
        for pasta in ("projects/proj-a", "fundacao", "registry", "state"):
            (raiz / pasta).mkdir(parents=True)
        (raiz / "fundacao" / "__main__.py").write_text("# raiz de teste\n", encoding="utf-8")
        self.raiz, self.registro = raiz, raiz / "registry" / "projetos-host.json"
        self.destino = raiz / "projects" / "proj-a" / "data" / "origem" / "parte1"
        return raiz

    def test_comando_de_registro_roda_no_terminal_e_o_plano_passa(self):
        # Integração final da 1.7.10, item I23: o `preparo_host.py registrar-projeto` exige --raiz, e o comando pronto
        # da recusa não a trazia; colado no terminal, saía com código 2 (uso incorreto) sem registrar nada. Raiz e
        # origem temporárias, de nomes hostis, a origem fora da raiz; o Python do sistema e o preparo desta skill.
        if NO_WINDOWS and not POWERSHELL:
            self.skipTest("sem PowerShell para rodar o comando")
        raiz = self.raiz_sem_registro(f"raiz {PASTA_HOSTIL}")
        origem = self.base / "fontes" / PASTA_HOSTIL
        origem.mkdir()
        (origem / "a.txt").write_text("a\n", encoding="utf-8")
        comando = self.plano(origem=origem, codigo=2)["erro"].split("No terminal do titular: ", 1)[1]
        self.assertEqual(argvs(comando, powershell=NO_WINDOWS),
                         [["python" if NO_WINDOWS else "python3", str(IMP.PREPARO_HOST), "registrar-projeto", "--raiz",
                           str(raiz), "--projeto", "proj-a", "--origem", str(origem)]])
        terminal = self.base / "terminal"  # a pasta atual do shell: os INJ-* cairiam aqui
        terminal.mkdir()
        antes = comando.replace(f" --raiz {CODIGO.citar_no_terminal(raiz)}", "", 1)  # o comando de antes do I23
        self.assertNotEqual(antes, comando)
        r = rodar_no_terminal(antes, terminal)
        self.assertEqual(r.returncode, 2, r.stdout[-2000:] + r.stderr[-2000:])
        self.assertIn("--raiz", r.stdout + r.stderr)
        self.assertFalse(os.path.lexists(self.registro), "sem --raiz, nada é registrado")
        r = rodar_no_terminal(comando, terminal)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
        self.assertEqual(os.listdir(terminal), [], "nada do nome saiu das aspas")
        self.assertEqual(json.loads(self.registro.read_text(encoding="utf-8"))["projetos"],
                         {"proj-a": {"origens": [str(origem)], "somente_leitura": [], "aninhadas_negadas": [],
                                    "agentes_negados": []}})
        self.assertEqual(len(self.plano(origem=origem)["sha256"]), 64, "com a origem registrada, o plano passa")

    def test_raiz_que_nao_da_para_citar_fica_sem_comando(self):
        # I23: a raiz vai ao comando pela citação única; antes ela nem entrava, e o comando saía "pronto" (e errado).
        raiz = self.raiz_sem_registro("raiz\u202ex")  # U+202E inverteria o que o titular lê
        erro = self.plano(codigo=2)["erro"]
        self.assertIn("Não há comando pronto", erro)
        self.assertIn(ascii(str(raiz)), erro, "a recusa diz qual valor não dá para citar")
        self.assertIn("(a origem ou a raiz)", erro)
        self.assertNotIn("registrar-projeto", erro)
        self.assertNotIn("\u202e", erro)

    def test_comando_de_registro_cita_a_origem_hostil(self):
        origem = self.base / "fontes" / PASTA_HOSTIL
        origem.mkdir()
        (origem / "a.txt").write_text("a\n", encoding="utf-8")
        erro = self.plano(origem=origem, codigo=2)["erro"]
        comando = erro.split("No terminal do titular: ", 1)[1]
        esperado = ["python" if NO_WINDOWS else "python3", str(IMP.PREPARO_HOST), "registrar-projeto", "--raiz",
                    str(self.raiz), "--projeto", "proj-a", "--origem", str(origem)]
        self.assertEqual(argvs(comando, powershell=NO_WINDOWS), [esperado])
        if POWERSHELL:
            self.assertEqual(analisador_do_powershell(comando), (0, [esperado]))

    def test_origem_que_nao_da_para_citar_fica_sem_comando(self):
        origem = self.base / "fontes" / "orig\u202ex"
        origem.mkdir()
        (origem / "a.txt").write_text("a\n", encoding="utf-8")
        erro = self.plano(origem=origem, codigo=2)["erro"]
        self.assertIn("Não há comando pronto", erro)
        self.assertNotIn("registrar-projeto", erro)  # o comando começa por --raiz desde o I23
        self.assertNotIn("\u202e", erro)

    def test_proximo_passo_do_plano_cita_o_caminho_do_plano(self):
        self.plano_arq = self.base / "planos" / (PASTA_HOSTIL + ".json")
        dados = self.plano()
        esperado = ["python" if NO_WINDOWS else "python3", "-I", "-B", str(Path(IMP.__file__).resolve()), "copiar",
                    "--plano", str(self.plano_arq), "--plano-sha256", dados["sha256"]]
        self.assertEqual(argvs(dados["proximo_passo"], powershell=NO_WINDOWS), [esperado])
        self.plano_arq = self.base / "planos" / "plano\u202e.json"
        self.assertIn("noutro caminho", self.plano(codigo=2)["erro"])
        self.assertFalse(self.plano_arq.exists())


if __name__ == "__main__":
    unittest.main()
