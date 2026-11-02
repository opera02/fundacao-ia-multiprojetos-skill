"""1.7.10 — trava de manutenção, registro da última cópia, `backup situacao` e saída resumida do `backup criar`
(desenho 1.7.10, §5.8 e §7.1; MELHORIAS-1.7.10, §0 item 14).

- `state/manutencao.json` existe durante o `backup criar` e sai no fim, também na falha; trava de outra operação (o
  atualizador) fica.
- `registry/ultima-copia.json` (fundacao.ultima_copia/1, LF) é gravado pelo `backup criar` e ganha `verificada_em` no
  `backup verificar` com sucesso; cópia mais antiga não troca o registro.
- `backup situacao` (administração ou auditoria) diz a idade da última cópia e, passados 7 dias, avisa com o comando
  pronto da próxima.
- `backup criar` devolve o resumo; a lista de arquivos só com --detalhar.
A CLI roda em processo (`cli_backup.executar` com o parser de `cli_backup.registrar_parser`), com a identidade do
lançador simulada. Identidades, caminhos e datas fictícios.
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

from apoio_auditoria import criar_ligacao_dir
from helpers import FoundationTestCase

from fundacao import cli_backup
from fundacao.__main__ import _con, build_parser
from fundacao.core import backup, manutencao
from fundacao.core.ancora_copia import anotar_ancora
from fundacao.core.auth import ENV_PRINCIPAL
from fundacao.core.contracts import AccessDenied, ValidationError


def data_iso(dias_atras: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=dias_atras)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class TestTrava(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="fundacao-trava-"))
        self.addCleanup(shutil.rmtree, self.raiz, True)
        (self.raiz / "state").mkdir()

    def test_travar_ler_destravar(self):
        trava = manutencao.travar(self.raiz, "ensaio fictício")
        self.assertEqual(set(trava), {"motivo", "pid", "host", "desde"})
        bruto = (self.raiz / "state" / "manutencao.json").read_bytes()
        self.assertNotIn(b"\r", bruto)
        self.assertEqual(json.loads(bruto), trava)
        self.assertEqual(manutencao.ler(self.raiz), trava)
        self.assertIsNone(manutencao.travar(self.raiz, "outra operação"), "trava existente não é trocada")
        self.assertEqual(manutencao.ler(self.raiz), trava)
        self.assertFalse(manutencao.destravar(self.raiz, {**trava, "pid": -1}), "trava de outra operação ficou")
        self.assertTrue(manutencao.destravar(self.raiz, trava))
        self.assertIsNone(manutencao.ler(self.raiz))

    def test_travada_sai_no_fim_e_na_falha(self):
        with manutencao.travada(self.raiz, "bloco") as trava:
            self.assertEqual(manutencao.ler(self.raiz), trava)
        self.assertIsNone(manutencao.ler(self.raiz))
        with self.assertRaises(RuntimeError):
            with manutencao.travada(self.raiz, "bloco que falha"):
                raise RuntimeError("falha simulada")
        self.assertIsNone(manutencao.ler(self.raiz))

    def test_trava_alheia_fica(self):
        alheia = manutencao.travar(self.raiz, "atualizar_fundacao aplicar (fictício)")
        with manutencao.travada(self.raiz, "backup criar") as trava:
            self.assertIsNone(trava)
        self.assertEqual(manutencao.ler(self.raiz), alheia)

    def test_trava_ilegivel_vale_como_trava(self):
        (self.raiz / "state" / "manutencao.json").write_bytes(b"\x00 lixo")
        self.assertIn("ilegivel", manutencao.ler(self.raiz))
        self.assertIsNone(manutencao.travar(self.raiz, "backup criar"))

    def test_ligacao_no_caminho_recusa(self):
        fora = Path(tempfile.mkdtemp(prefix="fundacao-trava-fora-"))
        self.addCleanup(shutil.rmtree, fora, True)
        shutil.rmtree(self.raiz / "state")
        criar_ligacao_dir(self.raiz / "state", fora)
        with self.assertRaises(ValidationError):
            manutencao.travar(self.raiz, "backup criar")
        self.assertEqual(list(fora.iterdir()), [], "a trava foi gravada através da ligação")


class TestLivroEProximaCopia(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="fundacao-livro-"))
        self.addCleanup(shutil.rmtree, self.raiz, True)
        (self.raiz / "state").mkdir()
        (self.raiz / "registry").mkdir()

    def test_livro_com_linha_ruim_e_entrada_assinada(self):
        livro = self.raiz / "state" / "copias.jsonl"
        entrada = {"rotulo": "s1", "criado_em": data_iso(3), "destino": "D:/IA/copias/s1",
                   "sha256_manifesto": "a" * 64}
        mais_nova = {"rotulo": "s2", "criado_em": data_iso(1), "destino": "D:/IA/copias/s2",
                     "sha256_manifesto": "b" * 64}
        envelope = {"documento": {"entrada": mais_nova}, "assinatura_base64": "AAAA"}
        linhas = [json.dumps(entrada), "isto não é JSON", json.dumps(envelope), json.dumps(mais_nova)]
        livro.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        res = manutencao.copias_do_livro(self.raiz)
        self.assertEqual((res["situacao"], res["entradas"]), ("lido", 2))
        self.assertEqual(res["ultima"]["rotulo"], "s2")

    def test_situacao_pelo_livro_quando_nao_ha_registro(self):
        anotar_ancora(self.raiz / "state" / "copias.jsonl",
                      {"rotulo": "antiga", "criado_em": data_iso(10), "destino": "D:/IA/copias/antiga",
                       "sha256_manifesto": "c" * 64})
        res = manutencao.situacao(self.raiz)
        self.assertFalse(res["em_dia"])
        self.assertEqual(res["idade_dias"], 10)
        self.assertEqual(res["ultima_copia"]["rotulo"], "antiga")
        self.assertIsNone(res["ultima_copia"]["verificada_em"])

    def test_proxima_copia(self):
        agora = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
        res = cli_backup.proxima_copia(Path("/tmp/fundacao-ficticia"), str(self.raiz / "copias" / "semanal-2026-S43"),
                                       agora)
        self.assertEqual(res["rotulo"], "semanal-2026-S44")
        self.assertEqual(Path(res["destino"]), self.raiz / "copias" / "semanal-2026-S44")
        self.assertIn("backup criar --destino", res["criar"])
        self.assertIn("--rotulo semanal-2026-S44", res["criar"])
        self.assertIn("backup verificar --origem", res["verificar"])
        (self.raiz / "copias" / "semanal-2026-S44").mkdir(parents=True)
        res = cli_backup.proxima_copia(Path("/tmp/fundacao-ficticia"), str(self.raiz / "copias" / "x"), agora)
        self.assertEqual(res["rotulo"], "semanal-2026-S44-2", "o rótulo já usado na semana não se repete")
        for ruim in (None, "", "D:/IA/copias/x\nRemove-Item -Recurse C:/"):
            with self.subTest(anterior=ruim):
                res = cli_backup.proxima_copia(Path("/tmp/fundacao-ficticia"), ruim, agora)
                self.assertIn("<pasta das cópias", res["destino"])
                self.assertNotIn("\n", res["criar"])


class TestCliBackup1710(FoundationTestCase):
    def setUp(self):
        super().setUp()
        # #4: registry/ultima-copia.json é gravado a cada `backup criar`, mas não está nas exclusões do
        # FoundationTestCase — numa fundação instalada ele viria na cópia do registry e test_situacao_sem_copia falharia.
        (self.root / "registry" / "ultima-copia.json").unlink(missing_ok=True)
        self.extra = []
        self.log = self.root / "state" / "retiradas.jsonl"
        self.raiz = self.root.resolve()

    def tearDown(self):
        for p in self.extra:
            shutil.rmtree(p, ignore_errors=True)
        super().tearDown()

    def pasta(self, nome: str) -> Path:
        p = self.root.parent / f"{self.root.name}-{nome}"
        self.extra.append(p)
        return p

    @staticmethod
    def parser() -> argparse.ArgumentParser:
        p = argparse.ArgumentParser(prog="fundacao")
        p.add_argument("--raiz", type=Path, default=Path.cwd())
        sub = p.add_subparsers(dest="comando", required=True)
        cli_backup.registrar_parser(sub)
        return p

    def cli(self, quem: str, *argv: str) -> tuple[dict, str]:
        args = self.parser().parse_args(["--raiz", str(self.raiz), "backup", *argv])
        with mock.patch.dict(os.environ, {ENV_PRINCIPAL: quem}), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            return cli_backup.executar(args, _con), err.getvalue()

    def test_parser_igual_ao_da_entrada_principal_mais_as_novidades(self):
        casos = [["backup", "criar", "--destino", "/tmp/copias/x", "--rotulo", "r1"],
                 ["backup", "verificar", "--origem", "/tmp/copias/x", "--sha256-manifesto", "a" * 64,
                  "--exigir-livro-assinado"],
                 ["backup", "restaurar", "--origem", "o", "--destino", "d", "--retiradas", "r.jsonl",
                  "--aceitar-registro-nao-comprovado", "--aceitar-copia-sem-ancora", "motivo fictício"]]
        for argv in casos:
            with self.subTest(argv=argv):
                antigo = vars(build_parser().parse_args(argv))
                antigo.pop("func")
                self.assertIs(antigo.pop("detalhar"), False)  # 1.7.10: a entrada principal já usa o parser de cli_backup
                novo = vars(self.parser().parse_args(argv))
                self.assertIs(novo.pop("detalhar"), False)
                self.assertEqual(novo, antigo)
        novo = self.parser().parse_args(["backup", "situacao"])
        self.assertEqual(novo.acao, "situacao")
        self.assertTrue(self.parser().parse_args(["backup", "criar", "--detalhar"]).detalhar)

    def test_criar_devolve_resumo_e_grava_a_ultima_copia(self):
        snap = self.pasta("snap")
        res, _ = self.cli("operador-lab", "criar", "--destino", str(snap), "--rotulo", "resumo-1710")
        self.assertNotIn("files", res)
        manifesto = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(res["arquivos"], len(manifesto["files"]))
        self.assertEqual(res["bytes"], sum(f["size"] for f in manifesto["files"]))
        for chave in ("rotulo", "created_at", "db", "sha256_manifesto", "guarde_a_ancora", "avisos",
                      "ligacoes_nao_seguidas", "git_levados", "segredos_incluidos", "retiradas"):
            self.assertIn(chave, res)
        self.assertEqual(res["rotulo"], "resumo-1710")
        self.assertEqual((res["git_levados"], res["segredos_incluidos"]), (0, 0))
        arquivo = self.root / "registry" / "ultima-copia.json"
        bruto = arquivo.read_bytes()
        self.assertNotIn(b"\r", bruto, "o registro é gravado em LF")
        registro = json.loads(bruto)
        self.assertEqual(registro, {"schema_version": "fundacao.ultima_copia/1", "rotulo": "resumo-1710",
                                    "criada_em": manifesto["created_at"], "verificada_em": None,
                                    "destino": str(snap.resolve())})
        self.assertIsNone(manutencao.ler(self.root), "a trava saiu no fim")
        detalhado, _ = self.cli("operador-lab", "criar", "--destino", str(self.pasta("snap-2")), "--detalhar")
        self.assertIn("files", detalhado)

    def test_trava_existe_durante_a_copia_e_sai_tambem_na_falha(self):
        vistas = []
        real = backup.create_backup

        def olhar(*args, **kwargs):
            vistas.append(manutencao.ler(self.root))
            return real(*args, **kwargs)
        with mock.patch.object(backup, "create_backup", side_effect=olhar):
            self.cli("operador-lab", "criar", "--destino", str(self.pasta("snap")))
        self.assertEqual(vistas[0]["motivo"], "backup criar (manual)")
        self.assertEqual(vistas[0]["pid"], os.getpid())
        self.assertIsNone(manutencao.ler(self.root))
        with mock.patch.object(backup, "create_backup", side_effect=OSError(28, "disco cheio (simulado)")):
            with self.assertRaises(OSError):
                self.cli("operador-lab", "criar", "--destino", str(self.pasta("snap-falha")))
        self.assertIsNone(manutencao.ler(self.root), "a trava ficou depois da falha")

    def test_quem_nao_administra_nao_trava(self):
        with self.assertRaises(AccessDenied):
            self.cli("operador-juridico", "criar", "--destino", str(self.pasta("snap")))
        self.assertFalse((self.root / "state" / "manutencao.json").exists())

    def test_trava_do_atualizador_fica_depois_do_backup(self):
        alheia = manutencao.travar(self.root, "atualizar_fundacao aplicar (fictício)")
        self.cli("operador-lab", "criar", "--destino", str(self.pasta("snap")))
        self.assertEqual(manutencao.ler(self.root), alheia)

    def test_trava_pre_existente_avisa_em_criar_e_em_situacao(self):
        # #3: antes, uma trava já existente deixava o backup correr sem trava e sem aviso; agora avisa (não derruba).
        alheia = manutencao.travar(self.root, "atualizar_fundacao aplicar (fictício)")
        res, _ = self.cli("operador-lab", "criar", "--destino", str(self.pasta("snap")))
        self.assertTrue(any("já havia uma trava de manutenção" in a for a in res["avisos"]), res["avisos"])
        self.assertTrue(any(alheia["desde"] in a for a in res["avisos"]), "o aviso traz o desde da trava")
        self.assertEqual(manutencao.ler(self.root), alheia, "a trava alheia não foi trocada nem removida")
        sit, err = self.cli("operador-lab", "situacao")
        self.assertIn("há uma trava de manutenção", sit["aviso_trava"])
        self.assertIn(alheia["desde"], sit["aviso_trava"])
        self.assertIn("W_TRAVA_DE_MANUTENCAO", err)

    def test_verificar_anota_e_copia_antiga_nao_troca_o_registro(self):
        antiga, nova = self.pasta("antiga"), self.pasta("nova")
        self.cli("operador-lab", "criar", "--destino", str(antiga), "--rotulo", "antiga")
        self.cli("operador-lab", "criar", "--destino", str(nova), "--rotulo", "nova")
        ver, _ = self.cli("operador-lab", "verificar", "--origem", str(nova))
        self.assertTrue(ver["ok"], ver)
        self.assertIn("anotada", ver["registro_da_copia"])
        registro = manutencao.ler_ultima_copia(self.root)
        self.assertEqual(registro["rotulo"], "nova")
        self.assertIsNotNone(registro["verificada_em"])
        ver, _ = self.cli("operador-lab", "verificar", "--origem", str(antiga))
        self.assertTrue(ver["ok"], ver)
        self.assertIn("mais antiga", ver["registro_da_copia"])
        self.assertEqual(manutencao.ler_ultima_copia(self.root), registro)

    def test_situacao_em_dia_e_atrasada(self):
        snap = self.pasta("snap")
        self.cli("operador-lab", "criar", "--destino", str(snap), "--rotulo", "recente")
        res, err = self.cli("operador-lab", "situacao")
        self.assertTrue(res["em_dia"], res)
        self.assertEqual(res["idade_dias"], 0)
        self.assertNotIn("aviso", res)
        self.assertNotIn("W_COPIA_ANTIGA", err)
        self.assertEqual(res["livro"]["entradas"], 1)
        # Nove dias depois (datas fictícias no registro e no livro).
        anterior = str(self.root.parent / "copias-ficticias" / "semanal-antiga")
        manutencao.registrar_copia(self.root, rotulo="semanal-antiga", criada_em=data_iso(9.1), destino=anterior)
        (self.root / "state" / "copias.jsonl").unlink()
        res, err = self.cli("operador-lab", "situacao")
        self.assertFalse(res["em_dia"])
        self.assertEqual(res["idade_dias"], 9)
        self.assertIn("9 dias (mais de 7)", res["aviso"])
        self.assertIn("W_COPIA_ANTIGA", err)
        proxima = res["proxima_copia"]
        ano, semana, _ = datetime.now(timezone.utc).isocalendar()
        self.assertEqual(proxima["rotulo"], f"semanal-{ano}-S{semana:02d}")
        self.assertEqual(Path(proxima["destino"]).parent, Path(anterior).parent)
        self.assertIn("backup criar --destino", proxima["criar"])

    def test_situacao_sem_copia(self):
        res, err = self.cli("operador-lab", "situacao")
        self.assertIsNone(res["ultima_copia"])
        self.assertFalse(res["em_dia"])
        self.assertIn("nenhuma cópia", res["aviso"])
        self.assertIn("W_COPIA_ANTIGA", err)
        self.assertIn("<pasta das cópias", res["proxima_copia"]["destino"])

    def test_situacao_so_para_administracao_ou_auditoria(self):
        for quem in ("operador-juridico", "revisor-juridico"):  # o revisor audita o projeto, não a fundação
            with self.subTest(quem=quem), self.assertRaises(AccessDenied):
                self.cli(quem, "situacao")
        self.policy.grant(self.admin, "curador-comum", "foundation", "audit")
        res, _ = self.cli("curador-comum", "situacao")
        self.assertIn("em_dia", res)


if __name__ == "__main__":
    unittest.main()
