"""Revisão de segurança da 1.7.7, segunda passada, na área do atualizador, cada achado com o cenário de falha
reproduzido. Pastas descartáveis; identidade de ensaio; nada no perfil nem numa fundação real.

R177B-B-05: o `instalar_kit.py` gravava o registry/kit_install.json com `write_text`, que grava através de vínculo
físico (hard link, que no Windows qualquer conta cria), e o atualizador só conferia o vínculo no `checar`, antes do
ensaio inteiro: vínculo criado durante o ensaio levava o registro da promoção ao arquivo de fora, e o `aplicar`
terminava ok. Agora o registro da instalação vai por temporário imprevisível e `os.replace`
(`gravacao_segura.publicar`), ligação no caminho dele recusa no plano, e o atualizador confere de novo, logo antes da
promoção, onde a atualização grava.
R177B-B-06: o inventário só olhava fundacao/, templates/ e tests/, mas o uso normal (`python -m fundacao` com a raiz
como pasta atual) põe a raiz no caminho de importação, à frente da biblioteca padrão: um `argparse.py` plantado na raiz
passava pelo `checar` e rodava no `status`. Agora o inventário confere também o primeiro nível da raiz (módulos,
pacotes, `.pth` e o `__pycache__`), recusa executável que nem o kit nem o registro conhecem, e a promoção apaga o
`__pycache__` dali.
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

from apoio import SCRIPTS, SKILL, criar_ligacao_dir, rodar_script, versao_do_kit
from test_auditoria_1_7_6_atualizador import _Raiz, codigo_que_marca, sha


def carregar(nome: str):
    """Módulo dos scripts carregado pelo caminho (como nos testes da primeira passada)."""
    spec = importlib.util.spec_from_file_location(nome + "_177b", SCRIPTS / (nome + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestRegistroDaInstalacaoSemSeguirVinculo(unittest.TestCase):
    """R177B-B-05: o `instalar_kit.py` não grava o registro da instalação através de vínculo físico nem de ligação."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="registro-da-instalacao-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.raiz = self.base / "raiz"
        r = rodar_script("instalar_kit.py", "--destino", self.raiz)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.reg = self.raiz / "registry" / "kit_install.json"

    def test_vinculo_fisico_no_registro_nao_leva_a_gravacao_para_fora(self):
        fora = self.base / "kit_install-de-fora.json"
        shutil.move(self.reg, fora)
        os.link(fora, self.reg)                                            # hard link: qualquer conta cria
        antes = fora.read_bytes()
        (self.raiz / "tests" / "helpers.py").unlink()                      # o kit o copia de volta e registra
        r = rodar_script("instalar_kit.py", "--destino", self.raiz)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(fora.read_bytes(), antes, "o registro da instalação foi gravado no arquivo de fora")
        self.assertEqual(os.stat(self.reg).st_nlink, 1)
        historico = json.loads(self.reg.read_text(encoding="utf-8"))
        self.assertEqual(len(historico), 2)
        self.assertEqual([c["path"] for c in historico[-1]["copiados"]], ["tests/helpers.py"])
        self.assertEqual([p.name for p in self.reg.parent.iterdir() if p.name.endswith(".tmp")], [])

    def test_ligacao_no_lugar_do_registro_nao_grava_e_avisa(self):
        """Ligação posta no lugar do registro depois do plano (corrida): nada vai para o alvo dela, e a saída diz que o
        registro não foi gravado, sem cair."""
        ik = carregar("instalar_kit")
        pasta_de_fora = self.base / "pasta-de-fora"
        pasta_de_fora.mkdir()
        self.reg.unlink()
        criar_ligacao_dir(self.reg, pasta_de_fora)
        motivo = ik.registrar(self.raiz, {"ensaio": True})
        self.assertTrue(motivo, "o registro foi gravado através da ligação")
        self.assertEqual(list(pasta_de_fora.iterdir()), [])


VINCULO_NO_ENSAIO = '''import os
import unittest
from pathlib import Path


class TestVinculoNoEnsaio(unittest.TestCase):
    def test_troca_o_registro_da_instalacao_da_raiz_por_vinculo_fisico(self):
        reg, fora = Path(os.environ["REGISTRO_DA_RAIZ"]), Path(os.environ["REGISTRO_DE_FORA"])
        if not fora.exists():  # a primeira suíte do ensaio, depois do `checar`
            os.replace(reg, fora)
            os.link(fora, reg)
'''


class TestVinculoCriadoDuranteOEnsaio(_Raiz):
    """R177B-B-05, o cenário do achado: o vínculo físico aparece no registro da instalação durante o ensaio."""

    def test_aplicar_nao_grava_o_registro_no_arquivo_de_fora(self):
        skill = self.base / "skill"
        shutil.copytree(SKILL, skill, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "evals"))
        for base in (skill / "assets" / "fundacao-kit", self.raiz):              # teste que o kit novo também tem
            (base / "tests" / "test_local_vinculo.py").write_text(VINCULO_NO_ENSAIO, encoding="utf-8")
        self.versao_antiga()
        reg, fora = self.raiz / "registry" / "kit_install.json", self.base / "kit_install-de-fora.json"
        antes = reg.read_bytes()
        env = {**self.env, "REGISTRO_DA_RAIZ": str(reg), "REGISTRO_DE_FORA": str(fora)}
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups, "--padrao-testes",
                                   "test_local_*.py", script=skill / "scripts" / "atualizar_fundacao.py", env=env)
        self.assertTrue(fora.is_file(), "controle: o vínculo físico deveria ter sido criado durante o ensaio")
        self.assertEqual(fora.read_bytes(), antes, "o registro da promoção foi gravado no arquivo de fora")
        self.assertEqual((code, res.get("etapa")), (1, "promocao"), res)
        self.assertIn("registry/kit_install.json", res["motivo"])
        self.assertEqual(versao_do_kit(self.raiz), "1.0.0")                       # a raiz não foi promovida


class TestModuloPlantadoNaRaiz(_Raiz):
    """R177B-B-06: executável no primeiro nível da raiz faz o `checar` recusar; o `__pycache__` dali sai na promoção."""

    def uso_normal(self) -> None:
        """Um comando comum do kit na raiz, como o lançador faz: a raiz é a pasta atual."""
        subprocess.run([sys.executable, "-B", "-m", "fundacao", "--raiz", str(self.raiz), "status"], cwd=str(self.raiz),
                       env=self.env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)

    def test_argparse_plantado_na_raiz_faz_o_checar_e_o_aplicar_recusarem(self):
        marcador = self.base / "marcador-argparse"
        (self.raiz / "argparse.py").write_text(codigo_que_marca(marcador), encoding="utf-8")
        self.uso_normal()
        self.assertTrue(marcador.exists(), "controle: o módulo plantado na raiz deveria rodar no uso normal")
        marcador.unlink()
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 1, chk)
        self.assertEqual(chk["mudancas"]["executaveis_a_mais"], ["argparse.py"])
        self.assertTrue(any("primeiro nível da raiz" in m for m in chk["motivos"]), chk["motivos"])
        self.versao_antiga()
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups,
                                   "--padrao-testes", "test_nenhum_*.py")
        self.assertEqual((code, res.get("etapa")), (1, "checar"), res)
        self.assertFalse(self.backups.exists())                                   # parou antes do backup
        self.assertFalse(marcador.exists())                                       # nada importou o módulo plantado

    def test_pacote_bytecode_pth_e_pyw_no_primeiro_nivel_recusam_e_dado_nao(self):
        (self.raiz / "json").mkdir()
        (self.raiz / "json" / "__init__.py").write_text("VALOR = 1\n", encoding="utf-8")   # pacote: sombra o json
        (self.raiz / "solto.pyc").write_bytes(b"\x00" * 16)
        (self.raiz / "caminhos.pth").write_text("import os\n", encoding="utf-8")
        (self.raiz / "janela.pyw").write_text("VALOR = 1\n", encoding="utf-8")
        (self.raiz / "RETOMADA.md").write_text("# notas do titular\n", encoding="utf-8")   # dados: não recusam
        (self.raiz / "dados").mkdir()
        (self.raiz / "dados" / "rascunho.py").write_text("VALOR = 1\n", encoding="utf-8")  # pasta sem __init__
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 1, chk)
        self.assertEqual(chk["mudancas"]["executaveis_a_mais"],
                         ["caminhos.pth", "janela.pyw", "json/__init__.py", "solto.pyc"])

    def test_pycache_do_primeiro_nivel_nao_recusa_e_e_apagado_na_promocao(self):
        (self.raiz / "__pycache__").mkdir()
        (self.raiz / "__pycache__" / "argparse.cpython-312.pyc").write_bytes(b"\x00" * 16)
        self.versao_antiga()
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 0, chk)                                            # derivado: não recusa
        self.assertEqual(chk["mudancas"]["bytecode_a_apagar"], ["__pycache__"])
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups,
                                   "--padrao-testes", "test_nenhum_*.py")
        self.assertEqual(code, 0, res)
        self.assertFalse((self.raiz / "__pycache__").exists())
        reg = json.loads(Path(res["registro"]).read_text(encoding="utf-8"))
        self.assertEqual(reg["promocao"]["bytecode_apagado"], ["__pycache__"])

    def test_pycache_do_primeiro_nivel_que_e_ligacao_recusa_e_sai_sem_seguir(self):
        fora = self.base / "fora"
        fora.mkdir()
        (fora / "argparse.cpython-312.pyc").write_bytes(b"\x00" * 16)
        criar_ligacao_dir(self.raiz / "__pycache__", fora)
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 1, chk)
        self.assertIn("__pycache__", chk["mudancas"]["por_ligacao"])
        cc = carregar("codigo_conferido")
        self.assertEqual(cc.apagar_bytecode(self.raiz), (["__pycache__"], []))
        self.assertFalse(cc.ligacao(self.raiz / "__pycache__"))
        self.assertTrue((fora / "argparse.cpython-312.pyc").is_file())           # o alvo ficou intacto


class TestInventarioDoPrimeiroNivel(unittest.TestCase):
    """R177B-B-06: executável do primeiro nível só passa com o hash do kit novo ou do registro, e nunca vai para as
    cópias de onde o código e os testes rodam (elas levam só as áreas de código)."""

    def setUp(self):
        self.cc = carregar("codigo_conferido")
        self.base = Path(tempfile.mkdtemp(prefix="primeiro-nivel-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        for rel, texto in {"fundacao/__init__.py": "", "conftest.py": "A = 1\n", "extra.py": "B = 1\n"}.items():
            (self.base / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.base / rel).write_text(texto, encoding="utf-8")

    def test_conhecido_pelo_kit_ou_pelo_registro_passa_e_mudado_recusa(self):
        do_kit = {rel: sha(self.base / rel) for rel in ("fundacao/__init__.py", "conftest.py")}
        registrados = {"extra.py": sha(self.base / "extra.py")}
        inv = self.cc.inventario(self.base, do_kit, registrados)
        self.assertEqual((inv["a_mais"], inv["ligacoes"]), ([], []))
        self.assertEqual(sorted(inv["conferidos"]), ["fundacao/__init__.py"])     # a raiz não entra nas cópias
        (self.base / "extra.py").write_text("B = 2\n", encoding="utf-8")
        self.assertEqual(self.cc.inventario(self.base, do_kit, registrados)["a_mais"], ["extra.py"])
        so_o_pacote = {"fundacao/__init__.py": do_kit["fundacao/__init__.py"]}
        self.assertEqual(self.cc.inventario(self.base, so_o_pacote, {})["a_mais"], ["conftest.py", "extra.py"])


if __name__ == "__main__":
    unittest.main()
