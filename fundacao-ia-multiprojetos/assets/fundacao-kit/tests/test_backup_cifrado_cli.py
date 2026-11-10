"""1.7.11 — `backup` com a cópia cifrada na CLI (desenho DESENHO-COPIA-CIFRADA-1.7.11, lote 3; prova N9).

Fundação de laboratório, chave de TESTE e a CLI em processo (`cli_backup.executar`), com a identidade do lançador simulada. A chave
da cópia "instalada" é um arquivo de teste (politica_cifra.CHAVES_PADRAO); a sondagem de proteção da âncora é a de verdade
(arquivo gravável por esta conta = não protegida) ou, nos testes do caminho feliz, trocada por "protegida". Provas: `criar` cifra
com a chave protegida e deixa só texto cifrado; chave instalada e não protegida (ou em registry/) recusa sem gravar cópia nenhuma;
`--sem-cifra` grava em claro com o motivo no livro e no registro e avisa W_COPIA_EM_CLARO; `cifrar` converte uma cópia antiga
conferida pela âncora; `verificar` reconhece a cifrada, sem senha, e avisa a troca de chave; `restaurar` com origem cifrada recusa
com o comando do decifrar-copia; `situacao` avisa W_COPIA_EM_CLARO e W_CONTEUDO_NAO_CONFERIDO. Conteúdos fictícios.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from apoio_cifra import Chaveiro, chaveiros, exigir_gpg
from helpers import FoundationTestCase

from fundacao import cli_backup
from fundacao.__main__ import _con
from fundacao.core import backup, backup_cifrado, copia_cifrada, manutencao, politica_cifra
from fundacao.core.auth import ENV_PRINCIPAL
from fundacao.core.contracts import AccessDenied, ValidationError

A = B = EXE = None
PROTEGIDA = {"protegida": True, "motivo": "âncora protegida (simulada)"}


def setUpModule() -> None:
    global A, B, EXE
    EXE = exigir_gpg()
    A, B = chaveiros("Teste A", "Teste B")  # divididas entre os módulos


def data_iso(dias_atras: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=dias_atras)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class Base(FoundationTestCase):
    def setUp(self):
        super().setUp()
        (self.root / "registry" / "ultima-copia.json").unlink(missing_ok=True)
        self.base = Path(tempfile.mkdtemp(prefix="cl-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.raiz = self.root.resolve()
        self.local = self.base / "local"
        self.chave_arquivo = self.base / "confianca" / "chave-da-copia.asc"
        dados = mock.patch.object(politica_cifra, "pasta_de_dados", return_value=self.base / "dados")
        dados.start()
        self.addCleanup(dados.stop)

    def instalar(self, chave: Chaveiro = None, onde: Path = None, protegida: bool = True) -> Path:
        """Instala a chave pública de teste como a da cópia; `protegida`: a sondagem da âncora diz que sim."""
        caminho = onde or self.chave_arquivo
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes((chave or A).publica.read_bytes())
        p = mock.patch.object(politica_cifra, "CHAVES_PADRAO", (str(caminho),))
        p.start()
        self.addCleanup(p.stop)
        if protegida:
            p = mock.patch.object(politica_cifra, "protegida", return_value=PROTEGIDA)
            p.start()
            self.addCleanup(p.stop)
        return caminho

    @staticmethod
    def parser() -> argparse.ArgumentParser:
        p = argparse.ArgumentParser(prog="fundacao")
        p.add_argument("--raiz", type=Path, default=Path.cwd())
        sub = p.add_subparsers(dest="comando", required=True)
        cli_backup.registrar_parser(sub)
        return p

    def cli(self, quem: str, *argv: str) -> tuple[dict, str]:
        args = self.parser().parse_args(["--raiz", str(self.raiz), "backup", *argv])
        with mock.patch.dict(os.environ, {ENV_PRINCIPAL: quem}), mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            return cli_backup.executar(args, _con), err.getvalue()

    def criar(self, nome: str = "cifrada", *extra: str) -> tuple[dict, str, Path]:
        destino = self.base / nome
        res, err = self.cli("operador-lab", "criar", "--destino", str(destino), "--rotulo", nome,
                            "--preparo-local", str(self.local), *extra)
        return res, err, destino

    def registro(self) -> dict:
        return json.loads((self.root / "registry" / "ultima-copia.json").read_text(encoding="utf-8"))

    def livro(self) -> list[dict]:
        return [json.loads(x) for x in (self.root / "state" / "copias.jsonl").read_text(encoding="utf-8").splitlines()]


class TestCriar(Base):
    def test_parser_tem_as_opcoes_novas(self):
        args = self.parser().parse_args(["backup", "cifrar", "--origem", "o", "--destino", "d", "--sem-cifra", "m",
                                         "--preparo-local", "p"])
        self.assertEqual((args.acao, args.sem_cifra, args.preparo_local), ("cifrar", "m", Path("p")))
        self.assertIsNone(self.parser().parse_args(["backup", "criar"]).sem_cifra)

    def test_com_a_chave_protegida_a_copia_sai_cifrada(self):
        self.instalar()
        res, err, destino = self.criar()
        self.assertTrue(res["cifrada"])
        self.assertNotEqual(res["sha256_manifesto"], res["sha256_manifesto_interno"])
        self.assertEqual(res["destinatario"]["principal"], A.impressao)
        self.assertTrue(res["preparo_local_apagado"])
        self.assertIn("exige a senha", res["conteudo"])
        self.assertNotIn("W_COPIA_EM_CLARO", err)
        self.assertFalse((destino / "manifest.json").exists(), "cópia em claro no destino")
        self.assertTrue((destino / "manifesto-cifrado.json").is_file())
        self.assertFalse(self.local.exists())
        self.assertIsNone(manutencao.ler(self.root), "a trava saiu")
        for chave in ("rotulo", "created_at", "arquivos", "bytes", "db", "retiradas", "guarde_a_ancora", "avisos", "partes"):
            self.assertIn(chave, res)
        self.assertEqual(self.registro(), {"schema_version": "fundacao.ultima_copia/1", "rotulo": "cifrada",
                                           "criada_em": res["created_at"], "verificada_em": None,
                                           "destino": str(destino.resolve()), "cifrada": True})
        self.assertTrue(backup_cifrado.verificar_cifrada(destino, sha256_manifesto=res["sha256_manifesto"])["ok"])

    def test_sem_chave_instalada_e_a_copia_de_hoje(self):
        res, err, destino = self.criar("claro")
        self.assertNotIn("cifrada", res)
        self.assertTrue((destino / "manifest.json").is_file())
        self.assertNotIn("W_COPIA_EM_CLARO", err)
        self.assertNotIn("cifrada", self.registro())
        self.assertTrue(any("--preparo-local só vale" in a for a in res["avisos"]))

    def test_n9_chave_instalada_mas_nao_protegida_recusa_sem_gravar_nada(self):
        with mock.patch.object(backup, "create_backup") as copiar, mock.patch.object(copia_cifrada, "criar_cifrada") as cifrar:
            for onde in (self.chave_arquivo, self.root / "registry" / "chave-da-copia.asc"):
                with self.subTest(onde=str(onde)):
                    self.instalar(onde=onde, protegida=False)  # a sondagem real: esta conta consegue alterar o arquivo
                    with self.assertRaises(ValidationError) as e:
                        self.criar("recusada")
                    self.assertIn("não está protegida", str(e.exception))
                    self.assertIn("nem em claro", str(e.exception))
        copiar.assert_not_called()
        cifrar.assert_not_called()
        self.assertFalse((self.base / "recusada").exists())
        self.assertFalse(self.local.exists())
        self.assertIsNone(manutencao.ler(self.root))
        self.assertFalse((self.root / "registry" / "ultima-copia.json").exists())

    def test_sem_cifra_grava_em_claro_com_o_motivo(self):
        self.instalar(protegida=False)
        res, err, destino = self.criar("em-claro", "--sem-cifra", "disco de ensaio fictício")
        self.assertTrue((destino / "manifest.json").is_file())
        self.assertNotIn("cifrada", res)
        self.assertIn("W_COPIA_EM_CLARO", err)
        self.assertIn("disco de ensaio fictício", err)
        self.assertEqual(self.registro()["sem_cifra"], "disco de ensaio fictício")
        self.assertNotIn("cifrada", self.registro())
        livro = [x for x in self.livro() if x.get("sem_cifra")]
        self.assertEqual([x["sha256_manifesto"] for x in livro], [res["sha256_manifesto"]])
        with self.assertRaises(ValidationError):
            self.criar("sem-motivo", "--sem-cifra", "   ")

    def test_quem_nao_administra_nao_cria_nem_cifra(self):
        self.instalar()
        for acao in (("criar", "--destino", str(self.base / "x")), ("cifrar", "--origem", "o", "--destino", str(self.base / "y"))):
            with self.subTest(acao=acao[0]), self.assertRaises(AccessDenied):
                self.cli("operador-juridico", *acao)
        self.assertFalse((self.base / "x").exists())


class TestCifrar(Base):
    def test_converte_uma_copia_antiga_conferida_pela_ancora(self):
        claro, _, antiga = self.criar("antiga")
        self.assertNotIn("cifrada", claro)
        self.instalar()
        res, _ = self.cli("operador-lab", "cifrar", "--origem", str(antiga), "--destino", str(self.base / "convertida"),
                          "--sha256-manifesto", claro["sha256_manifesto"])
        self.assertTrue(res["cifrada"])
        self.assertEqual(res["sha256_manifesto_interno"], claro["sha256_manifesto"], "a âncora do conteúdo é a da cópia antiga")
        self.assertEqual(res["ancora_do_conteudo"], claro["sha256_manifesto"])
        entrada = [x for x in self.livro() if x.get("cifrada")][0]
        criada = json.loads((antiga / "manifest.json").read_text(encoding="utf-8"))["created_at"]
        self.assertEqual(entrada["criado_em"], criada, "converter não faz a cópia antiga parecer nova")
        self.assertTrue(backup_cifrado.verificar_cifrada(self.base / "convertida", sha256_manifesto=res["sha256_manifesto"])["ok"])

    def test_pelo_livro_sem_informar_a_ancora(self):
        _, _, antiga = self.criar("antiga")
        self.instalar()
        res, _ = self.cli("operador-lab", "cifrar", "--origem", str(antiga), "--destino", str(self.base / "convertida"))
        self.assertTrue(res["cifrada"])

    def test_copia_alterada_ou_sem_chave_nao_cifra(self):
        claro, _, antiga = self.criar("antiga")
        with self.assertRaises(ValidationError) as e:
            self.cli("operador-lab", "cifrar", "--origem", str(antiga), "--destino", str(self.base / "c1"))
        self.assertIn("não está instalada", str(e.exception))
        self.instalar()
        alvo = next(p for p in (antiga / "files").rglob("*") if p.is_file() and p.stat().st_size > 5)
        alvo.write_bytes(bytes(b ^ 1 for b in alvo.read_bytes()))
        with self.assertRaises(ValidationError) as e:
            self.cli("operador-lab", "cifrar", "--origem", str(antiga), "--destino", str(self.base / "c2"),
                     "--sha256-manifesto", claro["sha256_manifesto"])
        self.assertIn("nada foi cifrado", str(e.exception))
        with self.assertRaises(ValidationError):
            self.cli("operador-lab", "cifrar", "--origem", str(antiga), "--destino", str(self.base / "c3"),
                     "--sha256-manifesto", "0" * 64)
        self.assertEqual([p.name for p in self.base.iterdir() if p.name in ("c1", "c2", "c3")], [])


class TestVerificarERestaurar(Base):
    """Uma cópia cifrada feita pelo `backup criar` UMA vez para a classe (molde, com o livro e o registro que ele deixou);
    cada teste ganha uma fundação de laboratório nova com cópias de arquivos do molde."""

    @classmethod
    def setUpClass(cls) -> None:
        lab = Base("run")  # só para usar a montagem da fundação de laboratório e o `criar` da CLI
        lab.setUp()
        try:
            lab.instalar()
            cls.res, _, destino = lab.criar()
            cls.molde = Path(tempfile.mkdtemp(prefix="cl-molde-"))
            cls.addClassCleanup(shutil.rmtree, cls.molde, ignore_errors=True)
            shutil.copytree(destino, cls.molde / "cifrada")
            shutil.copyfile(lab.root / "state" / "copias.jsonl", cls.molde / "copias.jsonl")
            shutil.copyfile(lab.root / "registry" / "ultima-copia.json", cls.molde / "ultima-copia.json")
        finally:
            lab.doCleanups()
            lab.tearDown()

    def setUp(self):
        super().setUp()
        self.instalar()
        self.destino = self.base / "cifrada"
        shutil.copytree(self.molde / "cifrada", self.destino)
        shutil.copyfile(self.molde / "copias.jsonl", self.root / "state" / "copias.jsonl")
        shutil.copyfile(self.molde / "ultima-copia.json", self.root / "registry" / "ultima-copia.json")
        self.ancora = self.res["sha256_manifesto"]

    def test_verificar_reconhece_a_cifrada_sem_senha(self):
        res, _ = self.cli("operador-lab", "verificar", "--origem", str(self.destino), "--sha256-manifesto", self.ancora)
        self.assertTrue(res["ok"], res)
        self.assertEqual((res["cifrada"], res["conteudo_conferido"]), (True, False))
        self.assertEqual(res["ancora"]["situacao"], "conferida")
        self.assertEqual(res["autorizacao"]["politica"], "fundação viva")
        self.assertEqual(res["destinatario_da_ancora"], A.impressao)
        self.assertNotIn("aviso_destinatario", res)
        self.assertIn("anotada", res["registro_da_copia"])
        registro = self.registro()
        self.assertTrue(registro["cifrada"])
        self.assertIsNotNone(registro["verificada_em"])
        self.assertEqual(registro["destino"], str(self.destino.resolve()))

    def test_verificar_pelo_livro(self):
        res, _ = self.cli("operador-lab", "verificar", "--origem", str(self.destino))
        self.assertTrue(res["ok"])
        self.assertEqual(res["ancora"]["fonte"], "livro de cópias")

    def test_parte_alterada_nao_confere_e_nao_anota(self):
        parte = sorted(self.destino.glob("parte-*.gpg"))[0]
        dados = bytearray(parte.read_bytes())
        dados[len(dados) // 2] ^= 1
        parte.write_bytes(bytes(dados))
        antes = self.registro()
        res, _ = self.cli("operador-lab", "verificar", "--origem", str(self.destino), "--sha256-manifesto", self.ancora)
        self.assertFalse(res["ok"])
        self.assertEqual(res["changed"], [parte.name])
        self.assertNotIn("registro_da_copia", res)
        self.assertEqual(self.registro(), antes)

    def test_troca_de_chave_e_aviso_nao_erro(self):
        self.instalar(chave=B)
        res, _ = self.cli("operador-lab", "verificar", "--origem", str(self.destino), "--sha256-manifesto", self.ancora)
        self.assertTrue(res["ok"], "as cópias antigas continuam conferíveis")
        self.assertEqual(res["destinatario_da_ancora"], B.impressao)
        self.assertIn("outra chave", res["aviso_destinatario"])

    def test_sem_fundacao_viva_ninguem_e_autorizado_pela_cifrada(self):
        vazia = Path(tempfile.mkdtemp(prefix="cl-vazia-"))
        self.addCleanup(shutil.rmtree, vazia, ignore_errors=True)
        with self.assertRaises(AccessDenied) as e:
            backup_cifrado.autorizar_cifrada(vazia, self.destino)
        self.assertIn("decifrar-copia", str(e.exception))

    def test_quem_nao_administra_nao_verifica(self):
        with self.assertRaises(AccessDenied):
            self.cli("operador-juridico", "verificar", "--origem", str(self.destino), "--sha256-manifesto", self.ancora)

    def test_restaurar_com_origem_cifrada_recusa_com_o_comando_do_decifrar(self):
        with self.assertRaises(ValidationError) as e:
            self.cli("operador-lab", "restaurar", "--origem", str(self.destino), "--destino", str(self.base / "restaurada"),
                     "--retiradas", str(self.root / "state" / "retiradas.jsonl"), "--sha256-manifesto", self.ancora)
        self.assertIn("CIFRADA", str(e.exception))
        decifrar = e.exception.details["decifrar"]
        self.assertIn("decifrar-copia", decifrar)
        self.assertIn(str(self.destino), decifrar)
        self.assertIn("fundacao_titular.py", decifrar)
        self.assertIn("--sha256-manifesto", e.exception.details["depois"])
        self.assertFalse((self.base / "restaurada").exists())

    def test_cifrada_nao_confunde_a_copia_comum(self):
        self.assertTrue(backup_cifrado.e_cifrada(self.destino))
        _, _, comum = self.criar("comum", "--sem-cifra", "ensaio")
        self.assertFalse(backup_cifrado.e_cifrada(comum))


class TestSituacao(Base):
    def test_copia_em_claro_com_a_chave_instalada_avisa(self):
        _, _, _ = self.criar("claro-antes")
        res, err = self.cli("operador-lab", "situacao")
        self.assertNotIn("W_COPIA_EM_CLARO", err, "sem chave instalada e sem --sem-cifra a cópia em claro é a de hoje")
        self.instalar()
        res, err = self.cli("operador-lab", "situacao")
        self.assertIn("W_COPIA_EM_CLARO", err)
        self.assertEqual([a["code"] for a in res["avisos_da_cifra"]], ["W_COPIA_EM_CLARO"])

    def test_sem_cifra_registrado_avisa_mesmo_sem_a_chave(self):
        self.instalar(protegida=False)
        self.criar("em-claro", "--sem-cifra", "motivo de ensaio")
        with mock.patch.object(politica_cifra, "CHAVES_PADRAO", ()):
            res, err = self.cli("operador-lab", "situacao")
        self.assertIn("W_COPIA_EM_CLARO", err)
        self.assertIn("motivo de ensaio", err)
        self.assertEqual(res["ultima_copia"]["sem_cifra"], "motivo de ensaio")

    def test_cifrada_em_dia_nao_avisa(self):
        self.instalar()
        self.criar()
        res, err = self.cli("operador-lab", "situacao")
        self.assertTrue(res["ultima_copia"]["cifrada"])
        self.assertEqual(res["avisos_da_cifra"], [])
        self.assertNotIn("W_COPIA_EM_CLARO", err)
        self.assertNotIn("W_CONTEUDO_NAO_CONFERIDO", err)

    def test_conteudo_nao_conferido_passados_35_dias(self):
        agora = datetime.now(timezone.utc)

        def situacao(criada_dias_atras, primeira_dias_atras, conferencias):
            res = {"ultima_copia": {"cifrada": True, "criada_em": data_iso(criada_dias_atras), "destino": "D:/IA/copias/s1"},
                   "livro": {"primeira_cifrada": data_iso(primeira_dias_atras)}}
            return [a["code"] for a in politica_cifra.avisos(res, chave_instalada=True, conferencias=conferencias, agora=agora)]

        boa = lambda dias: {"conferida_em": data_iso(dias), "ok": True}  # noqa: E731
        self.assertEqual(situacao(1, 20, []), [], "adoção recente: ainda dentro dos 35 dias")
        self.assertEqual(situacao(1, 36, []), ["W_CONTEUDO_NAO_CONFERIDO"])
        self.assertEqual(situacao(1, 90, [boa(10)]), [], "conferida há 10 dias")
        self.assertEqual(situacao(1, 90, [boa(40)]), ["W_CONTEUDO_NAO_CONFERIDO"])
        self.assertEqual(situacao(1, 90, [{"conferida_em": data_iso(2), "ok": False}]), ["W_CONTEUDO_NAO_CONFERIDO"],
                         "conferência que falhou não conta")
        comando = politica_cifra.avisos({"ultima_copia": {"cifrada": True, "criada_em": data_iso(1), "destino": "D:/c/s1"},
                                         "livro": {"primeira_cifrada": data_iso(60)}}, chave_instalada=True,
                                        conferencias=[], agora=agora)[0]["message"]
        self.assertIn("conferir-copia", comando)
        self.assertIn("D:/c/s1", comando)

    def test_o_registro_das_conferencias_e_lido_com_linhas_ruins(self):
        arquivo = self.base / "conferencias-copia.jsonl"
        arquivo.write_text("\n".join([json.dumps({"conferida_em": data_iso(1), "ok": True}), "isto não é JSON",
                                      json.dumps({"conferida_em": "ontem"}), json.dumps([1, 2])]) + "\n", encoding="utf-8")
        self.assertEqual(len(politica_cifra.ler_conferencias(arquivo)), 1)
        self.assertEqual(politica_cifra.ler_conferencias(self.base / "nao-existe.jsonl"), [])

    def test_o_livro_conta_a_primeira_cifrada(self):
        self.instalar()
        self.criar()
        livro = manutencao.copias_do_livro(self.root)
        self.assertIn("primeira_cifrada", livro)
        self.assertTrue(livro["ultima"]["cifrada"])


class TestPreparoLocalPadrao(unittest.TestCase):
    def test_o_padrao_fica_na_pasta_de_dados_do_perfil(self):
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\ficticio\AppData\Local", "XDG_DATA_HOME": "/home/f/.local/share"}):
            padrao = copia_cifrada.preparo_local_padrao("semanal-2026-S45")
        self.assertEqual(padrao.parts[-3:], ("FundacaoIA", "preparo-copias", "semanal-2026-S45"))


if __name__ == "__main__":
    unittest.main()
