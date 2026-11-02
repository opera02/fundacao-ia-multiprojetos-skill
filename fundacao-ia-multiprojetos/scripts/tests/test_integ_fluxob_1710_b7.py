"""Terceira revisão do pacote INTEG-FLUXOB (lote 2 da 1.7.10): o B7 com o nome fraco que o `segredos.py` não examina,
e o arquivo comum cujo nome termina no sufixo ' (ligação)' ou ' (especial)'.

1. O B7 é uma cadeia que só refaz o manifesto com código 0 em cada `segredos.py conferir`, mas o conferir dá código 1,
sem saída, para o que ele não examina: vínculo físico, acima do teto de 5 MB e binário. Numa venv de IA, a biblioteca
compilada do tiktoken e do tokenizers tem nome fraco (`*token*`): o comando parava nela, e o perfil dessa venv nunca
ficava preso. Agora esses nomes, separados pelos metadados (lstat, sem ler o conteúdo), saem da cadeia: a recusa diz
quais são e que levá-los sem a conferência é decisão do titular, com um comando à parte. O binário de outro nome
(`token.pickle`, que pode ser segredo) continua na cadeia, que para nele (a falha continua fechada).
2. O item de `fora_do_manifesto` é texto, e o tipo sai do sufixo: um arquivo comum de nome fraco terminado em
' (ligação)' dava o mesmo texto da ligação aceita do nome-base e sumia dos soltos, e o plano dizia preso com esse
arquivo fora do manifesto e à vista da caixa. Agora, se o arquivo com o sufixo existe, ele também fica solto; levado ao
manifesto pelo B7, não volta.
Pastas temporárias e dados fictícios; os comandos rodam de verdade no terminal de cada sistema (sh no Linux,
PowerShell no Windows), salvo onde dito.
"""

from __future__ import annotations

import hashlib
import os
import unittest

from apoio import criar_ligacao_dir, rodar_script
from test_integ_fluxob_1710_comando import NO_WINDOWS, POWERSHELL, argvs, rodar_no_terminal
from test_integ_fluxob_1710_perfil import EX, SITE, TOKENIZER, _Projeto

PERFIL = EX.PERFIL
BIBLIOTECA = f"{SITE}/_tiktoken.cpython-312-x86_64-linux-gnu.so"  # nome fraco (*token*) de biblioteca compilada
PICKLE = f"{SITE}/pkg/token.pickle"  # binário de nome fraco sem sufixo de biblioteca: pode ser segredo
BINARIO = b"\x7fELF\x02\x01\x01" + bytes(57)  # cabeçalho fictício: byte nulo no começo (o conferir o vê binário)
MARCA_CADEIA, MARCA_A_PARTE = "(--incluir-fraco): ", "(--incluir-fraco, sem conferir): "
FIM = ". Depois, ponha o manifesto_sha256"
INICIO_A_PARTE = "; nome fraco que o segredos.py não examina"


def comandos_da_recusa(texto: str) -> tuple[str | None, str | None]:
    """(a cadeia do B7, o comando à parte para o que o segredos.py não examina), cada um None se a recusa não o traz."""
    corpo, a_parte, cadeia = texto.rsplit(FIM, 1)[0], None, None
    if MARCA_A_PARTE in corpo:
        corpo, a_parte = corpo.split(MARCA_A_PARTE, 1)
    if MARCA_CADEIA in corpo:
        cadeia = corpo.split(MARCA_CADEIA, 1)[1].split(INICIO_A_PARTE, 1)[0]
    return cadeia, a_parte


def levados(comando: list[str]) -> list[str]:
    return sorted(comando[i + 1] for i, a in enumerate(comando) if a == "--incluir-fraco")


class _B7(_Projeto):
    def setUp(self):
        super().setUp()
        self.pasta_do_terminal = self.base / "terminal"  # a pasta atual do shell
        self.pasta_do_terminal.mkdir()

    def caminho(self, rel: str) -> str:
        return os.path.normpath(os.path.join(str(self.tools), *rel.split("/")))

    def manifesto_novo(self, dados: dict) -> dict:
        dados["codigo"]["manifesto_sha256"] = hashlib.sha256(self.man.read_bytes()).hexdigest()
        return dados

    def conferidos(self, comando: str) -> list[str]:
        return [c[-1] for c in argvs(comando, powershell=NO_WINDOWS) if "conferir" in c]

    def rodar(self, comando: str, codigo: int = 0) -> None:
        if NO_WINDOWS and not POWERSHELL:
            self.skipTest("sem PowerShell para rodar o comando")
        r = rodar_no_terminal(comando, self.pasta_do_terminal)
        self.assertEqual(r.returncode == 0, codigo == 0, r.stdout[-2000:] + r.stderr[-2000:])
        self.assertEqual(os.listdir(self.pasta_do_terminal), [])


class TestNomeFracoQueOSegredosNaoExamina(_B7):
    def test_biblioteca_compilada_sai_da_cadeia_e_o_comando_dos_outros_passa(self):
        (self.tools / BIBLIOTECA).write_bytes(BINARIO)
        r = rodar_script("segredos.py", "conferir", self.tools / BIBLIOTECA)  # ele não a examina: código 1
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('"binario"', r.stdout)
        dados = self.terceiros()  # sem o B7: o tokenizer.py também fica fora
        texto = self.recusa_do_plano(dados)
        self.assertIn(f"{BIBLIOTECA} (biblioteca compilada, binária)", texto)
        self.assertIn("decisão sua", texto)
        cadeia, a_parte = comandos_da_recusa(texto)
        self.assertEqual(self.conferidos(cadeia), [self.caminho(TOKENIZER)], "a biblioteca sai da cadeia")
        self.assertEqual(levados(argvs(cadeia, powershell=NO_WINDOWS)[-1]), [TOKENIZER])
        self.assertEqual(self.conferidos(a_parte), [self.caminho(TOKENIZER)], "o à parte confere os outros")
        self.assertEqual(levados(argvs(a_parte, powershell=NO_WINDOWS)[-1]), sorted([TOKENIZER, BIBLIOTECA]))
        self.rodar(cadeia)  # o comando dos outros nomes passa (antes, parava no código 1 da biblioteca)
        dados = self.manifesto_novo(dados)
        texto = self.recusa_do_plano(dados)  # sem a decisão, a biblioteca continua fora: recusa só por ela
        cadeia, a_parte = comandos_da_recusa(texto)
        self.assertIsNone(cadeia, "sem nome para conferir, não há cadeia")
        self.assertEqual(len(argvs(a_parte, powershell=NO_WINDOWS)), 1, "o comando à parte é só o manifesto.py criar")
        self.assertEqual(self.conferidos(a_parte), [])
        self.assertEqual(levados(argvs(a_parte, powershell=NO_WINDOWS)[-1]), sorted([TOKENIZER, BIBLIOTECA]))
        self.rodar(a_parte)  # a decisão do titular
        self.assertEqual(self.plano(self.manifesto_novo(dados), self.argv())["codigo_executado"],
                         EX.PRESO_PELO_PERFIL)

    def test_binario_de_outro_nome_continua_na_cadeia_que_para_nele(self):
        (self.tools / PICKLE).write_bytes(b"\x80\x04\x95" + bytes(29))  # pickle fictício: binário
        self.assertIsNone(PERFIL.nao_examinado(self.caminho(PICKLE)), "pelos metadados, nada o separa")
        dados = self.terceiros(*self.b7())
        texto = self.recusa_do_plano(dados)
        cadeia, a_parte = comandos_da_recusa(texto)
        self.assertIsNone(a_parte, "sem comando à parte: a falha continua fechada para o que pode ser segredo")
        self.assertEqual(self.conferidos(cadeia), [self.caminho(PICKLE)])
        antes = self.man.read_bytes()
        self.rodar(cadeia, codigo=1)
        self.assertEqual(self.man.read_bytes(), antes, "o conferir para no binário e o manifesto não é refeito")

    def test_separados_so_pelos_metadados_como_o_conferir_os_pula(self):
        pkg = self.tools / SITE / "pkg"
        externo = self.base / "fora-do-codigo.py"
        externo.write_text("X = 1\n", encoding="utf-8")
        vinculo = pkg / "password_util.py"
        try:
            os.link(externo, vinculo)
        except OSError as exc:
            self.skipTest(f"vínculo físico indisponível aqui: {exc}")
        grande = pkg / "token_vocab.json"
        with open(grande, "wb") as f:
            f.truncate(PERFIL.SEGREDOS.TETO_BYTES + 1)  # sem gravar os bytes: só o tamanho conta
        casos = {vinculo: ("vínculo físico", "vinculo-fisico"), grande: ("acima do teto", "acima-do-teto")}
        for nome in ("x.pyd", "x.dll", "x.dylib", "x.abi3.so", "X.DLL"):
            (pkg / nome).write_bytes(BINARIO)
            casos[pkg / nome] = ("biblioteca compilada", "binario")
        for caminho, (motivo, veredito) in casos.items():
            with self.subTest(caminho=caminho.name):
                self.assertIn(motivo, PERFIL.nao_examinado(str(caminho)))
                r = rodar_script("segredos.py", "conferir", caminho)  # a mesma conclusão do conferir, que o pula
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn(f'"{veredito}"', r.stdout)
        self.assertIsNone(PERFIL.nao_examinado(self.caminho(TOKENIZER)), "texto comum: o conferir o examina")
        self.assertIsNone(PERFIL.nao_examinado(str(pkg / "nao-existe.so")), "erro no lstat: fica na cadeia")
        texto = self.recusa_do_plano(self.terceiros(*self.b7()))
        cadeia, a_parte = comandos_da_recusa(texto)
        self.assertIsNone(cadeia)
        self.assertIn(f"{SITE}/pkg/password_util.py (vínculo físico", texto)
        self.assertIn(f"{SITE}/pkg/token_vocab.json (acima do teto", texto)
        self.assertEqual(levados(argvs(a_parte, powershell=NO_WINDOWS)[-1]),
                         sorted([TOKENIZER, f"{SITE}/pkg/password_util.py", f"{SITE}/pkg/token_vocab.json"]))


class TestArquivoComOSufixoNoNome(_B7):
    def b7_da_recusa(self, dados: dict, item: str) -> str:
        texto = self.recusa_do_plano(dados)
        cadeia, _a_parte = comandos_da_recusa(texto)
        self.assertEqual(self.conferidos(cadeia), [self.caminho(item)], texto)
        return cadeia

    def test_arquivo_com_o_sufixo_da_ligacao_aceita_fica_solto(self):
        criar_ligacao_dir(self.tools / SITE / "token", self.tools / SITE / "tokenizers")  # aceita: pasta do código
        dados = self.terceiros(*self.b7())
        plano = self.plano(dados, self.argv())
        self.assertIn(f"{SITE}/token (ligação)", plano["manifesto"]["fora_do_manifesto"])
        self.assertEqual(plano["codigo_executado"], EX.PRESO_PELO_PERFIL)
        item = f"{SITE}/token (ligação)"
        (self.tools / item).write_text("X = 1\n", encoding="utf-8")  # o mesmo texto da ligação aceita
        arquivo, _sha = self.gravar(dados, "perfil-sufixo.json")
        with self.assertRaises(EX.Recusa) as ctx:  # no conferir-perfil também (no Windows, sem conferir a ligação)
            EX.conferir_perfil(arquivo)
        self.assertIn(item, str(ctx.exception))
        self.rodar(self.b7_da_recusa(dados, item))
        plano = self.plano(self.manifesto_novo(dados), self.argv())  # levado pelo B7, não volta aos soltos
        self.assertEqual(plano["codigo_executado"], EX.PRESO_PELO_PERFIL)
        self.assertEqual(plano["manifesto"]["fora_do_manifesto"].count(item), 1, "só o da ligação")

    def test_arquivo_com_o_sufixo_do_especial_fica_solto_como_arquivo(self):
        item = f"{SITE}/pkg/token (especial)"
        (self.tools / item).write_text("X = 1\n", encoding="utf-8")  # nenhum especial de nome-base
        dados = self.terceiros(*self.b7())
        texto = self.recusa_do_plano(dados)
        self.assertNotIn("arquivo especial (FIFO", texto, "não há especial: o texto é só o do arquivo")
        self.rodar(self.b7_da_recusa(dados, item))
        self.assertEqual(self.plano(self.manifesto_novo(dados), self.argv())["codigo_executado"],
                         EX.PRESO_PELO_PERFIL)

    def test_regras_do_item_com_o_sufixo(self):
        raiz = self.tools
        (raiz / "a (ligação)").write_text("X = 1\n", encoding="utf-8")
        (raiz / "d (ligação)").mkdir()  # a pasta desse nome não dá o texto 'd (ligação)'
        (raiz / "chave.pem (especial)").write_text("x\n", encoding="utf-8")  # nome forte: a caixa o vê vazio
        mascarado = [["arquivo", str(raiz / "chave.pem (especial)")]]
        preso = {"arquivos": [{"path": "p (ligação)", "sha256": "0" * 64}]}  # preso: o texto não vem dele, e a
        (raiz / "p (ligação)").write_text("X = 1\n", encoding="utf-8")  # ligação 'p', que não existe mais, recusa
        casos = {"a (ligação)": [("arquivo", "a (ligação)")], "d (ligação)": [("ligacao", "d")],
                 "chave.pem (especial)": [], "p (ligação)": [("ligacao", "p")]}
        for item, esperado in casos.items():
            with self.subTest(item=item):
                soltos = PERFIL.soltos_do_codigo(str(raiz), preso, [item], mascarado, [])
                self.assertEqual(soltos, esperado)
        dois = PERFIL.soltos_do_codigo(str(raiz), {"arquivos": []}, ["a (ligação)", "a (ligação)"], [], [])
        self.assertEqual(dois, [("arquivo", "a (ligação)")], "a ligação e o arquivo do mesmo texto: um solto só")


if __name__ == "__main__":
    unittest.main()
