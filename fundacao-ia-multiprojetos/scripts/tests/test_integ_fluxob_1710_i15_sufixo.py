"""Integração final da 1.7.10, item I15 da folha (o baixo que sobrou da quarta reconferência do pacote INTEG-FLUXOB,
`REV4-INTEG-FLUXOB.json`): no fluxo B, o item `x (ligação)` de `codigo_do_plano.fora_do_manifesto` não esconde mais um
arquivo comum chamado `x (ligação)`, e o valor da opção na forma `--opção=valor` (o `--require=`, o `--import=`, o
`--loader=` e o `--env-file=` do Node) entra nos citados, como na forma separada.

Antes: `nao_preso` lia o item só como a ligação `x` (e tirava os dois sufixos em cadeia), e o `citados` não via o valor
depois do `=`. `node --require=./token (ligação) app.js` saía PRESO com o arquivo fora do manifesto, que podia ser
trocado depois do aceite sem a conferência ver. Pelo mesmo cuidado, também: a ligação chamada `x (especial)` (o item
é `x (especial) (ligação)`), o nome fora do UTF-8 (o item é o `ascii` dele) e a conferência pela contagem dos itens
(uma ligação `x` nova tem o texto do arquivo comum `x (ligação)` que já estava fora do manifesto). Nada roda: os planos
são montados sem isolamento, com um `node` fictício fora da cópia. Dados fictícios em pastas descartáveis.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import SCRIPTS, criar_ligacao_dir, rodar_script

MOTIVO = "fixture própria e fictícia do teste do item I15 da integração"
NO_LINUX = sys.platform.startswith("linux")


def carregar(nome: str):
    spec = importlib.util.spec_from_file_location(f"_teste_integ_i15_{nome}", SCRIPTS / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


EX = carregar("execucao_isolada")
CODIGO = EX.CODIGO


class TestTextoDoItem(unittest.TestCase):
    """As regras de `nao_preso` sobre o texto do item, sem sistema de arquivos (valem em qualquer sistema)."""

    def test_o_item_da_ligacao_vale_tambem_pelo_arquivo_comum_do_mesmo_nome(self):
        fora = ["token (ligação)"]
        self.assertTrue(CODIGO.nao_preso("token (ligação)", fora), "o arquivo comum desse nome, fora do manifesto")
        self.assertTrue(CODIGO.nao_preso("token", fora), "a ligação token")
        self.assertTrue(CODIGO.nao_preso("token/x.js", fora), "o que se lê pela ligação")
        self.assertFalse(CODIGO.nao_preso("token.js", fora))
        self.assertFalse(CODIGO.nao_preso("tokens (ligação)", fora))
        especial = ["lib/x.pth (especial)"]
        self.assertTrue(CODIGO.nao_preso("lib/x.pth (especial)", especial), "o arquivo comum desse nome")
        self.assertTrue(CODIGO.nao_preso("lib/x.pth", especial), "o especial lib/x.pth")

    def test_o_nome_base_sai_com_um_sufixo_so(self):
        # A ligação chamada 'x (especial)' dá o item 'x (especial) (ligação)'; tirar os dois sufixos dava 'x', que não é
        # nem a ligação nem o arquivo do texto inteiro (e deixava de fora o que se lê pela ligação).
        fora = ["x (especial) (ligação)"]
        self.assertTrue(CODIGO.nao_preso("x (especial)", fora))
        self.assertTrue(CODIGO.nao_preso("x (especial)/m.js", fora))
        self.assertTrue(CODIGO.nao_preso("x (especial) (ligação)", fora))
        self.assertFalse(CODIGO.nao_preso("x", fora))
        self.assertTrue(CODIGO.nao_preso("y (ligação)", ["y (ligação) (especial)"]), "o especial chamado 'y (ligação)'")

    def test_pasta_e_nome_fora_do_utf8(self):
        self.assertTrue(CODIGO.nao_preso("node_modules/x/index.js", ["node_modules/"]))
        self.assertFalse(CODIGO.nao_preso("node_modules2/x.js", ["node_modules/"]))
        ilegivel = "d\udcff"  # o nome b'd\xff' como o Python o lê no Linux
        self.assertTrue(CODIGO.nao_preso(ilegivel, [ascii(ilegivel)]))
        self.assertTrue(CODIGO.nao_preso(ilegivel + "/m.py", [ascii(ilegivel)]), "o que fica dentro dele")
        self.assertFalse(CODIGO.nao_preso("d/m.py", [ascii(ilegivel)]))
        # Arquivo comum com aspas no nome não vira outro caminho: só o `ascii` de um nome fora do UTF-8 é decodificado.
        self.assertFalse(CODIGO.nao_preso("abc", ["'abc'"]))
        self.assertTrue(CODIGO.nao_preso("'abc'", ["'abc'"]))
        self.assertFalse(CODIGO.nao_preso("d\udcff", ["'d\\udcff' "]), "texto que não é o ascii de um nome")

    def test_valor_da_opcao_longa_com_igual_entra_nos_citados(self):
        with tempfile.TemporaryDirectory(prefix="integ-i15-citados-") as pasta:
            for nome in ("app.js", "lib.js", "m.mjs", "l.mjs", "config.env"):
                Path(pasta, nome).write_text("// fictício\n", encoding="utf-8")
            comando = ["node", "--require=./lib.js", "--import=./m.mjs", "--loader=./l.mjs", "--env-file=config.env",
                       "--title=meu-app", "--input={entrada}", "app.js"]
            esperados = [os.path.abspath(os.path.join(pasta, n)) for n in ("lib.js", "m.mjs", "l.mjs", "config.env",
                                                                           "app.js")]
            self.assertEqual(CODIGO.citados(comando, pasta), esperados)
            separado = ["node", "--require", "./lib.js", "app.js"]  # a forma separada continua como era
            self.assertEqual(CODIGO.citados(separado, pasta), [esperados[0], esperados[-1]])
            self.assertEqual(CODIGO.citados(["node", "-r=./lib.js", "app.js"], pasta), [esperados[-1]],
                             "o Node só lê --opção=valor na opção longa")


class _Copia(unittest.TestCase):
    """Uma cópia com app.js e app.py, o manifesto (formato 3) fora dela e um `node` fictício fora dela."""

    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="integ-i15-")))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.copia = self.base / "copia"
        self.escrever({"app.js": "console.log(1)\n", "app.py": "import token\nprint('ok')\n",
                       "lib.js": "module.exports = 1\n"})
        (self.base / "fora.js").write_text("module.exports = 2\n", encoding="utf-8")  # ../fora.js, fora da cópia
        (self.base / "fora.blob").write_bytes(b"instantaneo ficticio\n")
        (self.base / "bin").mkdir()
        self.node = self.base / "bin" / "node"  # programa de mentira, só para o plano (nada roda)
        self.node.write_bytes(b"programa ficticio\n")
        self.man = self.base / "manifesto.json"

    def escrever(self, arquivos: dict) -> None:
        for rel, texto in arquivos.items():
            p = self.copia / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(texto, encoding="utf-8", newline="\n")

    def manifesto(self) -> None:
        r = rodar_script("manifesto.py", "criar", "--raiz", self.copia, "--saida", self.man)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def fora(self) -> list[str]:
        _ref, politica, antigos = CODIGO.ler_manifesto(self.man.read_bytes())
        return CODIGO.fora_do_manifesto(str(self.copia), politica, antigos, str(self.man))

    def plano(self, comando, cwd: Path | None = None) -> dict:
        return EX.montar_plano("gravar", [str(c) for c in comando], copia=str(self.copia), manifesto=str(self.man),
                               cwd=str(cwd or self.copia), entradas=[], gravavel=None, limites=EX.limites(30),
                               variaveis=[], sem_isolamento=MOTIVO)

    def motivos(self, comando) -> list[str]:
        comando = [str(c) for c in comando]
        return CODIGO.motivos_nao_preso(comando, str(self.copia), str(self.copia), comando[0], self.fora(), [])

    def recusa(self, comando) -> str:
        with self.assertRaises(EX.Recusa) as ctx:
            self.plano(comando)
        return str(ctx.exception)


class TestArquivoComumComOSufixo(_Copia):
    def test_require_com_igual_do_arquivo_comum_x_ligacao_nao_sai_preso(self):
        # A sonda da REV4: o arquivo comum 'token (ligação)' (nome fraco: fora do manifesto) carregado pelo --require=.
        self.escrever({"token (ligação)": "module.exports = 1\n"})
        self.manifesto()
        self.assertIn("token (ligação)", self.fora())
        for comando in ([self.node, "--require=./token (ligação)", "app.js"],
                        [self.node, "--require", "./token (ligação)", "app.js"]):
            with self.subTest(comando=comando[1:]):
                self.assertIn("que o manifesto não prende", self.recusa(comando))
        # E o motivo sai pelo nao_preso, sem depender do citados:
        motivos = self.motivos([self.node, "--require=./token (ligação)", "app.js"])
        self.assertTrue(any("--require ./token (ligação)" in m and "não prende" in m for m in motivos), motivos)

    def test_ligacao_chamada_x_especial_nao_sai_presa(self):
        alvo = self.base / "de-fora"
        alvo.mkdir()
        (alvo / "m.js").write_text("module.exports = 3\n", encoding="utf-8")
        criar_ligacao_dir(self.copia / "x (especial)", alvo)
        self.manifesto()
        fora = self.fora()
        self.assertIn("x (especial) (ligação)", fora)
        self.assertTrue(CODIGO.nao_preso("x (especial)/m.js", fora))
        self.assertIn("que o manifesto não prende", self.recusa([self.node, "--require=./x (especial)/m.js", "app.js"]))
        motivos = self.motivos([self.node, "--import=./x (especial)/m.js", "app.js"])
        self.assertTrue(any("x (especial)/m.js" in m and "não prende" in m for m in motivos), motivos)

    def test_ligacao_nova_com_o_texto_de_um_arquivo_comum_que_ja_estava_para_a_execucao(self):
        # O arquivo comum 'token (ligação)' (nome fraco) já estava fora do manifesto no aceite; a ligação 'token' nova
        # (o `import token` do app.py viria dela) dá o mesmo texto: pelo conjunto, nada mudava.
        self.escrever({"token (ligação)": "X = 1\n"})
        self.manifesto()
        plano = self.plano([sys.executable, "app.py"])
        self.assertTrue(plano["codigo_executado"].startswith("preso pelo manifesto"), plano["codigo_executado"])
        EX.conferir(plano)
        alvo = self.base / "pacote-de-fora"
        alvo.mkdir()
        (alvo / "__init__.py").write_text("print('de fora')\n", encoding="utf-8")
        criar_ligacao_dir(self.copia / "token", alvo)
        with self.assertRaises(EX.Recusa) as ctx:
            EX.conferir(plano)
        self.assertIn("novo fora do manifesto: token (ligação)", str(ctx.exception))

    def test_some_o_arquivo_comum_e_fica_a_ligacao_do_mesmo_texto(self):
        alvo = self.base / "de-fora"
        alvo.mkdir()
        criar_ligacao_dir(self.copia / "token", alvo)
        self.escrever({"token (ligação)": "X = 1\n"})
        self.manifesto()
        plano = self.plano([sys.executable, "app.py"])
        self.assertEqual(plano["manifesto"]["fora_do_manifesto"].count("token (ligação)"), 2, "a ligação e o arquivo")
        EX.conferir(plano)
        os.unlink(self.copia / "token (ligação)")
        with self.assertRaises(EX.Recusa) as ctx:
            EX.conferir(plano)
        self.assertIn("sumiu de fora do manifesto: token (ligação)", str(ctx.exception))


class TestOpcaoComIgual(_Copia):
    def setUp(self):
        super().setUp()
        self.manifesto()

    def test_arquivo_preso_pela_forma_com_igual_continua_preso(self):
        for comando in ([self.node, "--require=./lib.js", "app.js"], [self.node, "--require", "./lib.js", "app.js"],
                        [self.node, "--title=meu-app", "app.js"]):
            with self.subTest(comando=comando[1:]):
                plano = self.plano(comando)
                self.assertTrue(plano["codigo_executado"].startswith("preso pelo manifesto"), plano["codigo_executado"])

    def test_arquivo_fora_da_copia_pela_forma_com_igual_recusa(self):
        for opcao in ("--require", "--import", "--loader", "--experimental-loader", "--env-file"):
            with self.subTest(opcao=opcao):
                texto = self.recusa([self.node, f"{opcao}=../fora.js", "app.js"])
                self.assertIn("fora da cópia", texto)
                self.assertIn("fora.js", texto)

    def test_outra_opcao_longa_que_le_arquivo_tambem_recusa(self):
        # O --snapshot-blob do Node não está na tabela do plano: na forma separada o arquivo já era citado (todo
        # argumento que é arquivo conta); na forma com '=', também.
        for comando in ([self.node, "--snapshot-blob=../fora.blob", "app.js"],
                        [self.node, "--snapshot-blob", "../fora.blob", "app.js"]):
            with self.subTest(comando=comando[1:]):
                self.assertIn("fora da cópia", self.recusa(comando))

    def test_marca_no_valor_continua_nao_preso_sem_recusa(self):
        plano = self.plano([self.node, "--require={entrada}", "app.js"])
        self.assertTrue(plano["codigo_executado"].startswith("NÃO PRESO"), plano["codigo_executado"])


@unittest.skipUnless(NO_LINUX, "nome fora do UTF-8 (bytes no caminho): Linux")
class TestNomeForaDoUtf8(_Copia):
    def test_pasta_de_trabalho_ou_modulo_dentro_do_nome_fora_do_utf8_nao_sai_preso(self):
        pasta = os.fsencode(str(self.copia)) + b"/d\xff"
        os.mkdir(pasta)
        with open(pasta + b"/m.py", "wb") as f:
            f.write(b"print('de dentro')\n")
        self.manifesto()
        nome = "d\udcff"
        self.assertIn(ascii(nome), self.fora())
        plano = self.plano([sys.executable, str(self.copia / "app.py")], cwd=self.copia / nome)
        self.assertTrue(plano["codigo_executado"].startswith("NÃO PRESO"), plano["codigo_executado"])
        self.assertTrue(any("pasta de trabalho" in m for m in plano["codigo_nao_preso"]), plano["codigo_nao_preso"])
        plano = self.plano([sys.executable, "-m", nome + ".m"])
        self.assertTrue(any("o módulo" in m for m in plano["codigo_nao_preso"]), plano["codigo_nao_preso"])


if __name__ == "__main__":
    unittest.main()
