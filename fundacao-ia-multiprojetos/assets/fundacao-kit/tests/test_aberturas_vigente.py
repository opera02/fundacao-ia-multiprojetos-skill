"""A ficha de aberturas em vigor (1.7.10, contratos do lote 2, §5): `aberturas.vigente(raiz, projeto, area)` lê só a
área, confere a assinatura no namespace `fundacao-abertura` contra a âncora e escolhe a MAIOR versão; se ela não vale
(assinatura, tetos, projeto, vencida...), tudo fechado, sem voltar à anterior (crítica do desenho).

Chaves e âncora de ENSAIO, sem senha, geradas na hora numa pasta temporária; a âncora padrão desta máquina é trocada
pela de ensaio (nunca lida). Sem `ssh-keygen` no sistema, o teste é pulado com o motivo."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from apoio_decisoes import keygen
from test_aberturas_regras import HOJE, ficha

from fundacao.core import aberturas, decisoes
from fundacao.core import aberturas_regras as regras

CAMPOS_DO_CONTRATO = {"projeto", "valida", "versao", "arquivo", "sha256", "sig_sha256", "ficha", "motivo_invalida",
                      "area"}


class Assinador:
    """Duas chaves de ensaio (`titular-ensaio` e `intruso`) e a âncora com a do titular. `namespaces`: o da linha
    (None = sem a opção, todos os namespaces; a âncora da 1.7.9 traz só fundacao-decisao)."""

    def __init__(self, base: Path, namespaces: str | None = "fundacao-decisao,fundacao-abertura"):
        self.pasta = Path(base) / "chaves"
        self.pasta.mkdir(parents=True)
        for nome in ("titular-ensaio", "intruso"):
            subprocess.run([keygen(), "-q", "-t", "ed25519", "-N", "", "-C", nome, "-f", str(self.pasta / nome)],
                           check=True, capture_output=True)
        self.ancora = Path(base) / "ancora" / "allowed_signers"
        self.ancora.parent.mkdir(parents=True)
        self.escrever_ancora(namespaces)

    def escrever_ancora(self, namespaces: str | None) -> None:
        pub = (self.pasta / "titular-ensaio.pub").read_text(encoding="ascii").strip()
        opcao = f'namespaces="{namespaces}" ' if namespaces is not None else ""
        self.ancora.write_text(f"titular-ensaio {opcao}{pub}\n", encoding="ascii")

    def chave(self, nome: str = "titular-ensaio") -> Path:
        return self.pasta / nome

    def assinar(self, arquivo: Path, chave: str = "titular-ensaio", namespace: str = regras.NAMESPACE) -> Path:
        sig = Path(str(arquivo) + ".sig")
        sig.unlink(missing_ok=True)
        subprocess.run([keygen(), "-Y", "sign", "-f", str(self.chave(chave)), "-n", namespace, str(arquivo)],
                       check=True, capture_output=True)
        return sig

    def gravar(self, area: Path, f: dict, *, bruto: bytes | None = None, assinar: bool = True, **kw) -> Path:
        """A ficha `f` em `area/ficha-v<versao>.json`, nos bytes canônicos (ou em `bruto`), assinada."""
        area.mkdir(parents=True, exist_ok=True)
        alvo = area / f"ficha-v{f['versao']}.json"
        alvo.write_bytes(regras.canonico(f) if bruto is None else bruto)
        if assinar:
            self.assinar(alvo, **kw)
        return alvo


class VigenteCase(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="aberturas-vigente-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.assinador = Assinador(self.base)
        padrao = mock.patch.object(decisoes, "ANCORAS_PADRAO", (str(self.assinador.ancora),))
        padrao.start()
        self.addCleanup(padrao.stop)
        self.raiz = self.base / "raiz"
        self.area = self.base / "area-do-titular" / "juridico-lab" / "ficha"

    def vigente(self, area=None, projeto="juridico-lab", hoje=HOJE) -> dict:
        r = aberturas.vigente(self.raiz, projeto, self.area if area is None else area, hoje=hoje)
        self.assertEqual(set(r), CAMPOS_DO_CONTRATO)
        return r

    def fechada(self, trecho: str, **kw) -> dict:
        r = self.vigente(**kw)
        self.assertFalse(r["valida"], r)
        self.assertIsNone(r["ficha"])
        self.assertIn(trecho.casefold(), r["motivo_invalida"].casefold())
        return r


class TestVigente(VigenteCase):
    def test_sem_area_ou_sem_ficha_tudo_fechado(self):
        self.fechada("nenhuma ficha")
        self.area.mkdir(parents=True)
        (self.area / "maior-versao").write_text("3\n", encoding="ascii")  # outros arquivos da área não contam
        (self.area / "ficha-v02.json").write_text("{}", encoding="ascii")  # nome fora da forma: não é ficha
        r = self.fechada("nenhuma ficha")
        self.assertEqual(r["area"], str(self.area))

    def test_ficha_assinada_vale(self):
        f = ficha(rede={"dominios": ["registry.npmjs.org"]}, vigencia_ate="2026-12-31")
        alvo = self.assinador.gravar(self.area, f)
        r = self.vigente()
        self.assertTrue(r["valida"], r)
        self.assertEqual((r["versao"], r["ficha"], r["motivo_invalida"]), (1, f, None))
        self.assertEqual(r["arquivo"], str(alvo))
        self.assertEqual(r["sha256"], hashlib.sha256(alvo.read_bytes()).hexdigest())
        self.assertEqual(r["sig_sha256"], hashlib.sha256(Path(str(alvo) + ".sig").read_bytes()).hexdigest())

    def test_maior_versao_vale_qualquer_que_seja_a_ordem_de_gravacao(self):
        self.assinador.gravar(self.area, ficha(versao=2, rede={"dominios": ["pypi.org"]}))
        self.assinador.gravar(self.area, ficha(versao=1, rede={"dominios": ["registry.npmjs.org"]}))  # menor, depois
        r = self.vigente()
        self.assertEqual((r["valida"], r["versao"], r["ficha"]["rede"]), (True, 2, {"dominios": ["pypi.org"]}))

    def test_maior_versao_invalida_fecha_tudo_sem_voltar_a_anterior(self):
        self.assinador.gravar(self.area, ficha(versao=1, rede={"dominios": ["registry.npmjs.org"]}))
        self.assinador.gravar(self.area, ficha(versao=2), chave="intruso")
        r = self.fechada("não está na âncora")
        self.assertEqual(r["versao"], 2)
        self.assertIn("sem voltar à versão anterior", r["motivo_invalida"])

    def test_sem_assinatura(self):
        self.assinador.gravar(self.area, ficha(), assinar=False)
        self.fechada("sem assinatura")

    def test_namespace_errado(self):
        self.assinador.gravar(self.area, ficha(), namespace=decisoes.NAMESPACE)
        self.fechada("outro namespace")

    def test_ancora_da_1_7_9_restrita_a_fundacao_decisao_manda_atualizar(self):
        self.assinador.escrever_ancora("fundacao-decisao")
        self.assinador.gravar(self.area, ficha())
        self.fechada("atualize a âncora")

    def test_ancora_sem_restricao_de_namespace_e_com_padrao(self):
        self.assinador.gravar(self.area, ficha())
        for namespaces in (None, "fundacao-*"):
            with self.subTest(namespaces=namespaces):
                self.assinador.escrever_ancora(namespaces)
                self.assertTrue(self.vigente()["valida"])
        self.assinador.escrever_ancora("fundacao-*,!fundacao-abertura")
        self.fechada("atualize a âncora")

    def test_vencida_fecha_tudo_e_no_dia_ainda_vale(self):
        self.assinador.gravar(self.area, ficha(versao=1, rede={"dominios": ["registry.npmjs.org"]}))
        self.assinador.gravar(self.area, ficha(versao=2, vigencia_ate="2026-10-30"))
        r = self.fechada("vencida")
        self.assertEqual(r["versao"], 2)  # a v1, sem vigência, não volta a valer
        self.assertTrue(self.vigente(hoje=date(2026, 10, 30))["valida"])

    def test_conteudo_trocado_depois_de_assinar(self):
        alvo = self.assinador.gravar(self.area, ficha())
        alvo.write_bytes(regras.canonico(ficha(rede={"dominios": ["registry.npmjs.org"]})))
        self.fechada("não confere")

    def test_fora_da_forma_canonica_mesmo_assinada(self):
        f = ficha()
        self.assinador.gravar(self.area, f, bruto=(regras.canonico(f).decode("utf-8").replace("\n", "\r\n")
                                                   .encode("utf-8")))
        self.fechada("forma canônica")

    def test_ficha_de_outro_projeto_versao_trocada_e_reservada(self):
        self.assinador.gravar(self.area, ficha(project_id="reversa-lab"))
        self.fechada("outro projeto")
        shutil.rmtree(self.area)
        self.area.mkdir(parents=True)
        (self.area / "ficha-v4.json").write_bytes(regras.canonico(ficha(versao=3)))
        self.assinador.assinar(self.area / "ficha-v4.json")
        self.fechada("difere da do nome")
        shutil.rmtree(self.area)
        self.assinador.gravar(self.area, ficha(mcp=[{"nome": "playwright"}]))
        self.fechada("1.7.11")

    def test_ancora_ausente_e_ssh_keygen_do_sistema_ausente(self):
        self.assinador.gravar(self.area, ficha())
        with mock.patch.object(decisoes, "ANCORAS_PADRAO", (str(self.base / "nao-existe"),)):
            self.fechada("âncora ausente")
        with mock.patch.object(decisoes, "ssh_keygen_do_sistema", return_value=None):
            self.fechada("OpenSSH do sistema ausente")

    def test_projeto_invalido_nao_le_nada(self):
        for projeto in ("../reversa-lab", "Juridico", "", None):
            with self.subTest(projeto=projeto):
                r = aberturas.vigente(self.raiz, projeto, self.area, hoje=HOJE)
                self.assertFalse(r["valida"])
                self.assertIn("projeto inválido", r["motivo_invalida"])

    def test_namespace_permitido(self):
        casos = {None: True, (): False, ("fundacao-decisao",): False, ("fundacao-decisao", "fundacao-abertura"): True,
                 ("fundacao-*",): True, ("fundacao-*", "!fundacao-abertura"): False, ("*",): True}
        for padroes, esperado in casos.items():
            with self.subTest(padroes=padroes):
                self.assertEqual(aberturas.namespace_permitido(list(padroes) if padroes is not None else None,
                                                               regras.NAMESPACE), esperado)

    def test_conferir_assinatura_devolve_o_assinante(self):
        bruto = regras.canonico(ficha())
        alvo = self.base / "f.json"
        alvo.write_bytes(bruto)
        sig = self.assinador.assinar(alvo).read_bytes()
        r = aberturas.conferir_assinatura(bruto, sig)
        self.assertEqual((r["ok"], r["assinante"]), (True, "titular-ensaio"))
        self.assertFalse(aberturas.conferir_assinatura(bruto + b" ", sig)["ok"])
        self.assertIn("ilegível", aberturas.conferir_assinatura(bruto, b"lixo")["motivo"])


class TestVigenteSemLigacao(VigenteCase):
    def test_area_que_e_ligacao_fecha_tudo(self):
        real = self.base / "area-real"
        self.assinador.gravar(real, ficha())
        self.area.parent.mkdir(parents=True)
        if os.name == "nt":
            r = subprocess.run(["cmd", "/c", "mklink", "/J", str(self.area), str(real)], capture_output=True, text=True)
            if r.returncode != 0:
                self.skipTest(f"junção indisponível: {r.stdout} {r.stderr}")
        else:
            self.area.symlink_to(real, target_is_directory=True)
        self.fechada("ligação")
        self.assertTrue(aberturas.vigente(self.raiz, "juridico-lab", real, hoje=HOJE)["valida"])

    def test_ficha_com_vinculo_fisico_fecha_tudo(self):
        real = self.assinador.gravar(self.base / "outra", ficha())
        self.area.mkdir(parents=True)
        try:
            os.link(real, self.area / "ficha-v1.json")
            os.link(Path(str(real) + ".sig"), self.area / "ficha-v1.json.sig")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"vínculo físico indisponível: {exc}")
        self.fechada("recusado")

    @unittest.skipUnless(os.name == "posix", "link simbólico de arquivo exige privilégio no Windows")
    def test_ficha_que_e_link_simbolico_fecha_tudo(self):
        real = self.assinador.gravar(self.base / "outra", ficha())
        self.area.mkdir(parents=True)
        (self.area / "ficha-v1.json").symlink_to(real)
        (self.area / "ficha-v1.json.sig").symlink_to(Path(str(real) + ".sig"))
        self.fechada("recusado")

    @unittest.skipUnless(os.name == "posix", "FIFO só fora do Windows")
    def test_fifo_no_lugar_da_ficha_nao_trava(self):
        self.area.mkdir(parents=True)
        os.mkfifo(self.area / "ficha-v1.json")
        self.fechada("recusado")


if __name__ == "__main__":
    unittest.main()
