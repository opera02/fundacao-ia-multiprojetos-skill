"""Segunda revisão do pacote INTEG-FLUXOB (lote 2 da 1.7.10): arquivo especial (FIFO, socket ou dispositivo) no código
preso.

O manifesto só lê arquivo comum: o FIFO, o socket e o dispositivo ficavam fora dele e fora de
`codigo_do_plano.fora_do_manifesto` (os três varredores só tratavam arquivo, pasta e ligação). O plano dizia PRESO
("o resto que ele não prende recusa a execução") e a conferência de antes e de depois não via nada, mas por um FIFO
`x.pth` no site-packages um processo de fora entrega ao `site` do Python o que quiser a cada início, e por um socket a
caixa fala com quem está fora. Agora ele vai para o que o manifesto não prende como `<caminho> (especial)`: no perfil de
terceiros recusa (no plano, no conferir-perfil e antes e depois da execução); no fluxo B, deixa o código NÃO PRESO, e
um novo depois do plano para a execução. Os casos com FIFO e socket de verdade só no Linux (o Windows não os cria numa
pasta); o resto vale em qualquer sistema. Nada roda (o caminho do bubblewrap vai injetado no plano). Dados fictícios.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import SCRIPTS, rodar_script
from test_integ_fluxob_1710_perfil import EX, SITE, _Projeto

CODIGO = EX.CODIGO
PERFIL = EX.PERFIL
NO_LINUX = sys.platform.startswith("linux") and hasattr(os, "mkfifo")
MOTIVO = "fixture própria e fictícia do teste do arquivo especial"


def _carregar(nome: str):
    spec = importlib.util.spec_from_file_location(f"_teste_integ_especial_{nome}", SCRIPTS / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


FOLHA = _carregar("folha_do_plano")  # o texto do fluxo B que o titular lê antes do aceite


def criar_socket(caminho: Path) -> None:
    """Um socket de domínio Unix no caminho (o arquivo fica depois de fechado)."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.bind(str(caminho))
    finally:
        s.close()


class TestEspecialSemSistemaDeArquivos(unittest.TestCase):
    """As regras sobre o item `(especial)`, em qualquer sistema."""

    def test_o_item_especial_e_solto_e_nao_preso(self):
        self.assertEqual(PERFIL._do_fora("lib/x.pth (especial)"), ("especial", "lib/x.pth"))
        self.assertEqual(PERFIL._do_fora("lib/y (ligação)"), ("ligacao", "lib/y"))
        self.assertEqual(PERFIL._classe_do_solto("especial", "lib/x.pth", {}), "especial")
        self.assertIn("FIFO, socket ou dispositivo", PERFIL.PASSOS_DOS_SOLTOS["especial"])
        self.assertTrue(CODIGO.nao_preso("lib/x.pth", ["lib/x.pth (especial)"]))
        self.assertFalse(CODIGO.nao_preso("lib/x.py", ["lib/x.pth (especial)"]))
        raiz = os.path.abspath("raiz-ficticia")
        mascarado = [["arquivo", os.path.join(raiz, "lib", "chave.pem")]]  # nem a máscara o tira dos soltos
        soltos = PERFIL.soltos_do_codigo(raiz, {"arquivos": []}, ["lib/chave.pem (especial)"], mascarado, [])
        self.assertEqual(soltos, [("especial", "lib/chave.pem")])

    def test_no_fluxo_b_o_especial_deixa_o_codigo_nao_preso(self):
        copia = os.path.abspath("copia-ficticia")  # só texto: nada é lido
        motivos = CODIGO.motivos_nao_preso(["python3", "app.py"], copia, copia, "python3", ["x.pth (especial)"], [])
        self.assertTrue(any("arquivo especial" in m and "x.pth" in m for m in motivos), motivos)
        self.assertEqual(CODIGO.motivos_nao_preso(["python3", "app.py"], copia, copia, "python3",
                                                  ["x.pth (ligação)"], []), [])

    def test_textos_da_ligacao_aceita_citam_a_pasta_do_codigo_preso(self):
        # Terceiro baixo da revisão: a ligação aceita também aponta para uma pasta do código preso (lib64 -> lib).
        for texto in (EX.PRESO_PELO_PERFIL, PERFIL.SOLTO_NA_FOLHA, PERFIL.__doc__, PERFIL.PASSOS_DOS_SOLTOS["ligacao"]):
            self.assertIn("para uma pasta do código preso", " ".join(texto.split()))
        self.assertIn("arquivo especial", EX.PRESO_PELO_PERFIL)


@unittest.skipUnless(NO_LINUX, "FIFO e socket numa pasta: Linux")
class TestEspecialNoPerfil(_Projeto):
    def test_fifo_na_venv_antes_do_plano_recusa_no_plano_e_no_conferir_perfil(self):
        dados = self.terceiros(*self.b7())
        os.mkfifo(self.tools / SITE / "x.pth")  # o `site` do Python leria o que um processo de fora escrevesse nele
        texto = self.recusa_do_plano(dados)
        for trecho in ("arquivo especial (FIFO, socket ou dispositivo)", f"{SITE}/x.pth", "nada foi executado"):
            self.assertIn(trecho, texto)
        arquivo, _sha = self.gravar(dados, "perfil-fifo.json")
        with self.assertRaises(EX.Recusa) as ctx:
            EX.conferir_perfil(arquivo)
        self.assertIn("arquivo especial", str(ctx.exception))
        os.unlink(self.tools / SITE / "x.pth")
        self.assertEqual(self.plano(dados, self.argv())["codigo_executado"], EX.PRESO_PELO_PERFIL)

    def test_socket_no_codigo_preso_recusa(self):
        dados = self.terceiros(*self.b7())
        criar_socket(self.tools / "s.sock")
        self.assertIn("arquivo especial", self.recusa_do_plano(dados))

    def test_fifo_que_aparece_depois_do_plano_para_antes_e_depois_da_execucao(self):
        plano = self.plano(self.terceiros(*self.b7()), self.argv())
        EX.conferir_plano_do_perfil(plano, antes=True)
        os.mkfifo(self.tools / SITE / "pkg" / "y.pth")
        for antes in (True, False):
            with self.subTest(antes=antes), self.assertRaises(EX.Recusa) as ctx:
                EX.conferir_plano_do_perfil(plano, antes=antes)
            self.assertIn(f"novo fora do manifesto: {SITE}/pkg/y.pth (especial)", str(ctx.exception))


@unittest.skipUnless(NO_LINUX, "FIFO e socket numa pasta: Linux")
class TestEspecialNoFluxoB(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="integ-especial-")))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.copia = self.base / "copia"
        for rel, texto in {"app.py": "print('ok')\n", "entradas/um.json": "{}\n"}.items():
            (self.copia / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.copia / rel).write_text(texto, encoding="utf-8")
        self.man = self.base / "manifesto.json"

    def manifesto(self, *extra) -> None:
        r = rodar_script("manifesto.py", "criar", "--raiz", self.copia, "--saida", self.man, *extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def fora(self) -> list[str]:
        _ref, politica, antigos = CODIGO.ler_manifesto(self.man.read_bytes())
        return CODIGO.fora_do_manifesto(str(self.copia), politica, antigos, str(self.man))

    def plano(self) -> dict:
        return EX.montar_plano("gravar", [sys.executable, str(self.copia / "app.py"), "{entrada}"],
                               copia=str(self.copia), manifesto=str(self.man), cwd=None,
                               entradas=[str(self.copia / "entradas" / "um.json")], gravavel=None,
                               limites=EX.limites(30), variaveis=[], sem_isolamento=MOTIVO)

    def test_fifo_na_copia_deixa_o_codigo_nao_preso_e_vai_para_a_folha(self):
        os.mkfifo(self.copia / "x.pth")
        criar_socket(self.copia / "s.sock")
        self.manifesto()
        self.assertLessEqual({"x.pth (especial)", "s.sock (especial)"}, set(self.fora()))
        plano = self.plano()
        self.assertTrue(plano["codigo_executado"].startswith("NÃO PRESO"), plano["codigo_executado"])
        self.assertTrue(any("arquivo especial" in m for m in plano["codigo_nao_preso"]), plano["codigo_nao_preso"])
        folha = FOLHA.codigo(plano)
        self.assertIn("NÃO está preso", folha)
        self.assertIn("x.pth (especial)", folha)

    def test_fifo_novo_depois_do_plano_para_a_execucao(self):
        self.manifesto()
        plano = self.plano()
        EX.conferir(plano)
        os.mkfifo(self.copia / "x.pth")
        with self.assertRaises(EX.Recusa) as ctx:
            EX.conferir(plano)
        self.assertIn("novo fora do manifesto: x.pth (especial)", str(ctx.exception))

    def test_formato_2_e_o_git_do_modo_incluir_tambem_listam_o_especial(self):
        os.mkfifo(self.copia / "f2.pth")
        manifesto = CODIGO.MANIFESTO
        self.man.write_text(json.dumps(manifesto.build(self.copia, manifesto.politica_padrao())), encoding="utf-8")
        self.assertIn("f2.pth (especial)", self.fora())
        for rel in (".git/objects/ab", ".git/refs/heads"):
            (self.copia / rel).mkdir(parents=True)
        (self.copia / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        self.manifesto("--git", "incluir")
        os.mkfifo(self.copia / ".git" / "objects" / "ab" / "cano")
        os.mkfifo(self.copia / ".git" / "cano")
        fora = self.fora()
        for item in (".git/objects/ab/cano (especial)", ".git/cano (especial)", "f2.pth (especial)"):
            self.assertIn(item, fora)


if __name__ == "__main__":
    unittest.main()
