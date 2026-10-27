"""Livro com assinaturas: chaves fictícias descartáveis, nunca a chave do titular."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from helpers import FoundationTestCase
from fundacao.core import ancora_copia, backup, decisoes, livro_assinado
from fundacao.core.canon import canonical_json, sha256_bytes
from fundacao.core.contracts import AccessDenied, FundacaoError, ValidationError


class TestLivroAssinado(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.manifesto = b'{"copia":"ficticia"}'
        self.sha = sha256_bytes(self.manifesto)
        self.livro = self.root / "state/copias.jsonl"
        self.entrada = {"sha256_manifesto": self.sha, "rotulo": "copia-ficticia"}
        self.livro.write_text(canonical_json(self.entrada) + "\n", encoding="utf-8")
        self.arquivo = self.root / "projects/juridico-lab/outputs/copia-assinada.json"

    def test_sem_assinatura_e_alteracao_de_entrada_nao_autenticam(self):
        with self.assertRaises(ValidationError):
            livro_assinado.ancora_do_livro(self.livro, self.manifesto)
        livro_assinado.preparar(self.livro, self.sha, "titular-ficticio", self.arquivo)
        antes = self.livro.read_bytes()
        with self.assertRaises(ValidationError):
            livro_assinado.registrar(self.livro, self.arquivo)
        self.assertEqual(self.livro.read_bytes(), antes)

    def test_assinatura_real_ficticia_adulteracao_namespace_e_idempotencia(self):
        exe = decisoes.ssh_keygen_do_sistema()
        if not exe: self.skipTest("OpenSSH do sistema ausente")
        chave = self.root / "chave-ficticia"
        subprocess.run([exe, "-q", "-t", "ed25519", "-N", "", "-f", str(chave)], check=True,
                       capture_output=True, timeout=30)
        ancora = self.root / "allowed_signers-ficticio"
        ancora.write_text("titular-ficticio " + Path(str(chave) + ".pub").read_text(), encoding="utf-8")
        livro_assinado.preparar(self.livro, self.sha, "titular-ficticio", self.arquivo)
        subprocess.run([exe, "-Y", "sign", "-f", str(chave), "-n", "fundacao-decisao", str(self.arquivo)],
                       check=True, capture_output=True, timeout=30)
        with mock.patch.object(decisoes, "ancora_padrao", return_value=ancora), \
                mock.patch.object(decisoes, "conferir_ancora", return_value={"protegida": True}):
            with self.assertRaises(ValidationError):
                livro_assinado.registrar(self.livro, self.arquivo)
        Path(str(self.arquivo) + ".sig").unlink()
        subprocess.run([exe, "-Y", "sign", "-f", str(chave), "-n", "fundacao-copia", str(self.arquivo)],
                       check=True, capture_output=True, timeout=30)
        # A barreira do SO é simulada; a assinatura e os bytes adulterados são reais.
        with mock.patch.object(decisoes, "ancora_padrao", return_value=ancora), \
                mock.patch.object(decisoes, "conferir_ancora", return_value={"protegida": True}):
            self.assertTrue(livro_assinado.registrar(self.livro, self.arquivo)["registrada"])
            antes = self.livro.read_bytes()
            self.assertTrue(livro_assinado.registrar(self.livro, self.arquivo)["ja_registrada"])
            self.assertEqual(self.livro.read_bytes(), antes)
            self.assertEqual(livro_assinado.ancora_do_livro(self.livro, self.manifesto), self.sha)
            self.livro.write_bytes(antes.replace(b'copia-ficticia', b'copia-adulterada'))
            with self.assertRaises(ValidationError):
                livro_assinado.ancora_do_livro(self.livro, self.manifesto)

    def test_preparar_nao_sobrescreve_e_livro_linkado_recusa(self):
        livro_assinado.preparar(self.livro, self.sha, "titular-ficticio", self.arquivo)
        with self.assertRaises((ValidationError, FileExistsError)):
            livro_assinado.preparar(self.livro, self.sha, "titular-ficticio", self.arquivo)
        import os
        alias = self.root / "alias-livro.jsonl"
        os.link(self.livro, alias)
        with self.assertRaises((ValidationError, OSError)):
            livro_assinado.preparar(self.livro, self.sha, "titular-ficticio", self.arquivo.with_name("outra.json"))

    def test_verificador_do_path_nao_e_aceito_nem_com_ok_true(self):
        doc = {"schema_version": livro_assinado.SCHEMA, "assinante": "titular-ficticio",
               "registrado_em": "2026-10-22T00:00:00Z", "entrada": self.entrada}
        with mock.patch.object(decisoes, "ssh_keygen_do_sistema", return_value=Path("/sistema/ssh-keygen")), \
                mock.patch.object(decisoes, "ancora_padrao", return_value=Path("/ancora-ficticia")), \
                mock.patch.object(decisoes, "conferir_ancora", return_value={"protegida": True}), \
                mock.patch.object(decisoes, "verificar_assinatura", return_value={"ok": True, "ssh_keygen_do_sistema": False}):
            with self.assertRaises(ValidationError):
                livro_assinado._verificar(doc, b"assinatura-ficticia")

    def test_cli_memoria_e_assinaturas_estao_registradas(self):
        from fundacao.__main__ import build_parser
        parser = build_parser()
        for comando in (["memoria", "licao", "consultar", "--projeto", "juridico-lab", "--gatilho", "x"],
                        ["copia-assinatura", "preparar", "--projeto", "juridico-lab", "--sha256-manifesto", self.sha],
                        ["backup", "verificar", "--origem", "copia-ficticia", "--exigir-livro-assinado"]):
            with self.subTest(comando=comando): self.assertTrue(callable(parser.parse_args(comando).func))

    def test_cli_estrita_nega_sem_admin_vivo_antes_de_ler_manifesto_ou_livro(self):
        from fundacao.__main__ import build_parser
        from fundacao.cli_backup import executar
        origem = self.root / "copia-nao-autorizada"
        args = build_parser().parse_args(["--raiz", str(self.root), "backup", "verificar", "--origem", str(origem),
                                         "--exigir-livro-assinado"])
        # Só a identidade de ensaio substitui o lançador; a ACL real da raiz fictícia deve negar primeiro.
        with mock.patch.object(ancora_copia, "principal_from_env", return_value=self.jur), \
                mock.patch.object(backup.preparo, "ler", side_effect=ValidationError("manifesto foi lido cedo")):
            with self.assertRaises(FundacaoError) as erro:
                executar(args, None)
        self.assertIsInstance(erro.exception, AccessDenied)

    def test_cli_desastre_estrito_exige_assinatura_mesmo_com_hash_informado(self):
        from fundacao.__main__ import build_parser
        from fundacao.cli_backup import executar
        origem = self.root / "copia-ficticia"
        copia = backup.create_backup(self.root, origem, "ensaio-ficticio")
        destino = self.root / "restauracao-ficticia"
        args = build_parser().parse_args([
            "--raiz", str(self.root / "raiz-perdida"), "backup", "restaurar", "--origem", str(origem),
            "--destino", str(destino), "--retiradas", str(self.root / "state/retiradas.jsonl"),
            "--sha256-manifesto", copia["sha256_manifesto"], "--exigir-livro-assinado"])
        with mock.patch.object(ancora_copia, "principal_from_env", return_value=self.admin):
            with self.assertRaises(ValidationError):
                executar(args, None)
        self.assertFalse(destino.exists())

    def test_cli_desastre_estrito_autoriza_copia_com_assinatura_ficticia_real(self):
        from fundacao.__main__ import build_parser
        from fundacao.cli_backup import executar
        exe = decisoes.ssh_keygen_do_sistema()
        if not exe: self.skipTest("OpenSSH do sistema ausente")
        origem = self.root / "copia-ficticia"
        copia = backup.create_backup(self.root, origem, "ensaio-ficticio")
        chave = self.root / "chave-ficticia"
        subprocess.run([exe, "-q", "-t", "ed25519", "-N", "", "-f", str(chave)], check=True,
                       capture_output=True, timeout=30)
        ancora = self.root / "allowed_signers-ficticio"
        ancora.write_text(self.admin.principal_id + " " + Path(str(chave) + ".pub").read_text(), encoding="utf-8")
        livro_assinado.preparar(self.livro, copia["sha256_manifesto"], self.admin.principal_id, self.arquivo)
        subprocess.run([exe, "-Y", "sign", "-f", str(chave), "-n", "fundacao-copia", str(self.arquivo)],
                       check=True, capture_output=True, timeout=30)
        destino = self.root / "restauracao-ficticia"
        args = build_parser().parse_args([
            "--raiz", str(self.root / "raiz-perdida"), "backup", "restaurar", "--origem", str(origem),
            "--destino", str(destino), "--retiradas", str(self.root / "state/retiradas.jsonl"),
            "--exigir-livro-assinado"])
        with mock.patch.object(decisoes, "ancora_padrao", return_value=ancora), \
                mock.patch.object(decisoes, "conferir_ancora", return_value={"protegida": True}), \
                mock.patch.object(ancora_copia, "principal_from_env", return_value=self.admin):
            livro_assinado.registrar(self.livro, self.arquivo)
            resultado = executar(args, None)
        self.assertTrue(resultado["released"])
        self.assertEqual(resultado["autorizacao"]["politica"], "cópia autenticada pela âncora")
        self.assertTrue((destino / "state/state.sqlite").is_file())
