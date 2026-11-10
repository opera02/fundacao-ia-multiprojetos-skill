"""1.7.11 — o lado do titular da cópia cifrada no kit (desenho DESENHO-COPIA-CIFRADA-1.7.11, lote 4): `preparar_chave`,
`conferir_conteudo` (o conferir-copia mensal) e `decifrar`, com chave de TESTE e a senha por loopback (o titular a digita na
janela do gpg). Provas: o chaveiro só vale até ~85 caracteres na forma do msys; a chave nasce com a pública para a âncora e a
privada protegida pela senha (restaura num chaveiro novo só com a senha); nada é sobrescrito e a falha não deixa resto;
o conferir-copia decifra em fluxo SEM gravar arquivo, confere cada SHA-256 e o banco contra o manifesto interno, registra
{"conferida_em", "ok"} e falha (ok False, registrada) com parte alterada (sem chamar o gpg), MDC, senha errada, arquivo
trocado ou a mais e banco corrompido. Conteúdos fictícios.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio_cifra import (FRASE_DE_TESTE, LOOPBACK, arquivos_de_teste, chaveiros, cifrada_de_um_tar, conteudo_da_pasta,
                         copia_sintetica, exigir_gpg, sha, tar_da_copia)

from fundacao.core import cifra_copia, titular_copia
from fundacao.core.backup_cifrado import MANIFESTO, cifrar_copia
from fundacao.core.canon import sha256_bytes
from fundacao.core.cifra_copia import CifraRecusada, SessaoDeCifra
from fundacao.core.contracts import ValidationError
from fundacao.core.decifra_copia import encerrar_agente

A = B = EXE = None
EXTRAS = ("--batch", *LOOPBACK)
MOLDE = None


def setUpModule() -> None:
    global A, B, EXE, MOLDE
    EXE = exigir_gpg()
    A, B = chaveiros("Teste A", "Teste B")
    pasta = Path(tempfile.mkdtemp(prefix="tc-molde-"))
    unittest.addModuleCleanup(shutil.rmtree, pasta, ignore_errors=True)
    copia_sintetica(pasta / "claro", arquivos_de_teste())
    resultado = cifrar_copia(pasta / "claro", pasta / "cifrada", A.publica, tamanho_parte=64 * 1024, exe=EXE)
    MOLDE = (pasta, resultado)


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="tc-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)


class TestChaveiro(Base):
    def test_o_limite_e_o_da_forma_do_msys(self):
        limite = titular_copia.LIMITE_CASA
        base = self.tmp / "x"
        falta = limite - len(cifra_copia.para_gpg(base))
        if falta < 0:
            self.skipTest("pasta temporária longa demais para montar o caso")
        igual = Path(str(base) + "a" * falta)
        longo = Path(str(base) + "a" * (falta + 1))
        self.assertEqual(len(cifra_copia.para_gpg(igual)), limite)
        self.assertEqual(titular_copia.conferir_chaveiro(igual), igual)
        with self.assertRaises(CifraRecusada) as e:
            titular_copia.conferir_chaveiro(longo)
        self.assertEqual(e.exception.details["caracteres"], limite + 1)
        self.assertIn("mais curto", str(e.exception))

    def test_o_padrao_cabe_para_um_perfil_comum(self):
        with mock.patch.dict("os.environ", {"APPDATA": r"C:\\Users\\ficticio\\AppData\\Roaming"}):
            if titular_copia.os.name == "nt":
                self.assertLessEqual(len(cifra_copia.para_gpg(titular_copia.chaveiro_padrao())), titular_copia.LIMITE_CASA)


class TestPrepararChave(Base):
    """A chave é criada UMA vez para a classe (leva ~10 s); os testes dela só leem. Os de recusa criam o que precisam."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.base = Path(tempfile.mkdtemp(prefix="tc-chave-"))
        cls.addClassCleanup(shutil.rmtree, cls.base, ignore_errors=True)
        with mock.patch.object(titular_copia, "encerrar_agente", wraps=titular_copia.encerrar_agente) as agente:
            cls.r = titular_copia.preparar_chave(cls.base / "guardar", casa=cls.base / "casa", exe=EXE, extras_gpg=EXTRAS,
                                                 publica=cls.base / "pub" / "chave-da-copia.asc")
        cls.agente_encerrado = agente.call_count

    def preparar(self, **kw) -> dict:
        kw.setdefault("casa", self.tmp / "casa")
        kw.setdefault("publica", self.tmp / "pub" / "chave-da-copia.asc")
        kw.setdefault("extras_gpg", EXTRAS)
        return titular_copia.preparar_chave(self.tmp / "guardar", exe=EXE, **kw)

    def test_cria_a_chave_a_publica_e_a_privada_protegida(self):
        r = self.r
        self.assertEqual(self.agente_encerrado, 1, "o agente do gpg é encerrado no fim")
        self.assertTrue(r["ok"])
        self.assertRegex(r["impressao_digital"], r"^[0-9A-F]{40}$")
        self.assertNotEqual(r["impressao_digital"], r["subchave_de_cifra"])
        conf = (self.base / "casa" / "gpg-agent.conf").read_text(encoding="utf-8")
        for linha in ("default-cache-ttl 60", "max-cache-ttl 600", "s2k-count 65011712"):
            self.assertIn(linha, conf)
        publica, privada = Path(r["chave_publica"]), Path(r["chave_privada_protegida"])
        self.assertEqual(privada, self.base / "guardar" / "chave-privada-protegida.asc")
        self.assertIn("BEGIN PGP PRIVATE KEY BLOCK", privada.read_text(encoding="ascii"))
        self.assertNotIn("PRIVATE KEY", publica.read_text(encoding="ascii"))
        with SessaoDeCifra(publica, EXE) as sessao:
            self.assertEqual(sessao.destinatario["principal"], r["impressao_digital"])
            self.assertEqual(sessao.destinatario["subchaves_de_cifra"], [r["subchave_de_cifra"]])
        self.assertEqual(len(r["proximos_passos"]), 3)
        self.assertIn("-ChaveDaCopia", r["proximos_passos"][2])

    def test_a_privada_protegida_restaura_so_com_a_senha(self):
        r = self.r
        cifrado = self.tmp / "x.gpg"
        with SessaoDeCifra(r["chave_publica"], EXE) as sessao:
            with sessao.cifrador(cifrado) as c:
                c.write(b"dado ficticio")
        novo = Path(tempfile.mkdtemp(prefix="tn"))
        self.addCleanup(lambda: (encerrar_agente(EXE, novo), shutil.rmtree(novo, ignore_errors=True)))
        gpg = lambda *a: subprocess.run([EXE, "--no-options", "--batch", "--homedir", cifra_copia.para_gpg(novo), *a],  # noqa: E731
                                        capture_output=True, env=cifra_copia._ambiente())
        self.assertEqual(gpg("--pinentry-mode", "loopback", "--passphrase", FRASE_DE_TESTE, "--import",
                             cifra_copia.para_gpg(r["chave_privada_protegida"])).returncode, 0)
        encerrar_agente(EXE, novo)
        errada = gpg("--pinentry-mode", "loopback", "--passphrase", "errada", "--output", "-", "--decrypt", cifra_copia.para_gpg(cifrado))
        self.assertNotEqual(errada.returncode, 0)
        self.assertEqual(errada.stdout, b"")
        certa = gpg("--pinentry-mode", "loopback", "--passphrase", FRASE_DE_TESTE, "--output", "-", "--decrypt", cifra_copia.para_gpg(cifrado))
        self.assertEqual((certa.returncode, certa.stdout), (0, b"dado ficticio"))

    def test_nada_e_sobrescrito_e_a_segunda_chamada_recusa(self):
        r = self.r
        antes = {p: p.read_bytes() for p in (Path(r["chave_publica"]), Path(r["chave_privada_protegida"]))}
        with self.assertRaises(CifraRecusada) as e:
            titular_copia.preparar_chave(self.base / "guardar", casa=self.base / "casa", exe=EXE, extras_gpg=EXTRAS,
                                         publica=self.base / "pub" / "chave-da-copia.asc")
        self.assertIn("nada foi sobrescrito", str(e.exception))
        with self.assertRaises(CifraRecusada):  # outro chaveiro, mas a pública e a privada já existem
            titular_copia.preparar_chave(self.base / "guardar", casa=self.tmp / "outra-casa", exe=EXE, extras_gpg=EXTRAS,
                                         publica=self.base / "pub" / "chave-da-copia.asc")
        self.assertEqual({p: p.read_bytes() for p in antes}, antes)
        self.assertFalse((self.tmp / "outra-casa").exists())

    def test_pasta_da_privada_dentro_da_raiz_ou_chaveiro_longo_recusam_sem_chamar_o_gpg(self):
        raiz = self.tmp / "raiz"
        raiz.mkdir()
        with mock.patch("subprocess.run", side_effect=AssertionError("chamou o gpg")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("chamou o gpg")):
            with self.assertRaises(CifraRecusada) as e:
                titular_copia.preparar_chave(raiz / "guardar", casa=self.tmp / "casa", raiz=raiz, exe=EXE)
            self.assertIn("dentro da raiz", str(e.exception))
            with self.assertRaises(CifraRecusada):
                titular_copia.preparar_chave(self.tmp / "g", casa=self.tmp / ("c" * 120), exe=EXE)
        self.assertFalse((self.tmp / "casa").exists())

    def test_falha_do_gpg_nao_deixa_chaveiro_nem_arquivos(self):
        with self.assertRaises(CifraRecusada):
            self.preparar(extras_gpg=("--batch", "--pinentry-mode", "error"))  # sem senha: o gpg não cria
        self.assertFalse((self.tmp / "casa").exists())
        self.assertFalse((self.tmp / "pub" / "chave-da-copia.asc").exists())
        self.assertEqual(list((self.tmp / "guardar").glob("*")), [])


class TestConferirConteudo(Base):
    """A cópia cifrada é a do molde (feita uma vez); cada teste trabalha numa cópia de arquivos dela."""

    def setUp(self) -> None:
        super().setUp()
        self.claro, self.cifrada = self.tmp / "claro", self.tmp / "cifrada"
        shutil.copytree(MOLDE[0] / "claro", self.claro)
        shutil.copytree(MOLDE[0] / "cifrada", self.cifrada)
        self.ancora, self.registro = MOLDE[1]["sha256_manifesto"], self.tmp / "conferencias.jsonl"

    def conferir(self, origem=None, **kw) -> dict:
        kw.setdefault("sha256_manifesto", self.ancora)
        kw.setdefault("extras_gpg", EXTRAS)
        kw.setdefault("encerrar", False)
        return titular_copia.conferir_conteudo(origem or self.cifrada, kw.pop("casa", A.casa), exe=EXE, registro=self.registro, **kw)

    def linhas(self) -> list[dict]:
        return [json.loads(x) for x in self.registro.read_text(encoding="utf-8").splitlines()]

    def restos(self) -> list[str]:
        return sorted(p.name for p in Path(tempfile.gettempdir()).glob("fundacao-conferencia-*"))

    def test_conteudo_conferido_sem_gravar_arquivo_nenhum(self):
        antes, restos = conteudo_da_pasta(self.cifrada), self.restos()
        r = self.conferir()
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["arquivos"], len(arquivos_de_teste()))
        self.assertEqual(r["banco"], "íntegro")
        self.assertEqual(r["impressao_digital"], A.impressao)
        self.assertEqual(conteudo_da_pasta(self.cifrada), antes, "a conferência não toca a cópia")
        self.assertEqual(self.restos(), restos, "a pasta temporária do banco saiu")
        (linha,) = self.linhas()
        self.assertTrue(linha["ok"])
        self.assertEqual(set(linha) - {"registro_nao_gravado"}, {"conferida_em", "ok", "rotulo", "partes", "impressao_digital",
                                                                 "sha256_manifesto", "arquivos", "banco"})
        self.assertNotIn("projects", self.registro.read_text(encoding="utf-8"), "o registro não leva nomes nem conteúdo")

    def test_o_registro_so_acrescenta_e_alimenta_o_situacao(self):
        from fundacao.core import politica_cifra
        self.conferir()
        self.conferir()
        self.assertEqual(len(self.linhas()), 2)
        self.assertEqual(len(politica_cifra.ler_conferencias(self.registro)), 2)

    def test_parte_alterada_nao_chama_o_gpg_e_fica_registrada(self):
        parte = sorted(self.cifrada.glob("parte-*.gpg"))[0]
        dados = bytearray(parte.read_bytes())
        dados[len(dados) // 2] ^= 1
        parte.write_bytes(bytes(dados))
        with mock.patch("subprocess.Popen", side_effect=AssertionError("chamou o gpg")), \
                mock.patch("subprocess.run", side_effect=AssertionError("chamou o gpg")):
            r = self.conferir()
        self.assertFalse(r["ok"])
        self.assertIn("o gpg não foi chamado", r["motivo"])
        self.assertEqual(r["verificacao"]["changed"], [parte.name])
        self.assertFalse(self.linhas()[0]["ok"])

    def test_bloco_alterado_com_hashes_refeitos_e_pego_pelo_mdc(self):
        parte = sorted(self.cifrada.glob("parte-*.gpg"))[1]
        dados = bytearray(parte.read_bytes())
        dados[len(dados) // 2] ^= 1
        parte.write_bytes(bytes(dados))
        m = json.loads((self.cifrada / MANIFESTO).read_text(encoding="utf-8"))
        for p in m["partes"]:
            if p["nome"] == parte.name:
                p["sha256"] = sha(bytes(dados))
        bruto = json.dumps(m, indent=2).encode("utf-8")
        (self.cifrada / MANIFESTO).write_bytes(bruto)
        r = self.conferir(sha256_manifesto=sha256_bytes(bruto))
        self.assertFalse(r["ok"])
        self.assertIn("não decifrou", r["motivo"])
        self.assertFalse(self.linhas()[0]["ok"])

    def test_senha_errada_nao_confere(self):
        encerrar_agente(EXE, A.casa)  # senão o agente lembra da senha certa dos outros testes
        r = self.conferir(extras_gpg=("--batch", "--pinentry-mode", "loopback", "--passphrase", "errada"))
        self.assertFalse(r["ok"])
        self.assertFalse(self.linhas()[0]["ok"])

    def test_chave_de_outro_par_nao_confere(self):
        r = self.conferir(casa=B.casa)
        self.assertFalse(r["ok"])

    def test_destinatario_esperado_diferente_nao_chama_o_gpg(self):
        with mock.patch("subprocess.Popen", side_effect=AssertionError("chamou o gpg")), \
                mock.patch("subprocess.run", side_effect=AssertionError("chamou o gpg")):
            r = self.conferir(destinatario_esperado=B.impressao)
        self.assertFalse(r["ok"])

    def forjar(self, claro: Path, **kw) -> dict:
        forjada = self.tmp / "forjada"
        ancora = cifrada_de_um_tar(forjada, claro, tar_da_copia(claro, **kw), A, EXE)
        return {"origem": forjada, "sha256_manifesto": ancora}

    def test_a_forjada_sem_defeito_confere_controle(self):
        self.assertTrue(self.conferir(**self.forjar(self.claro))["ok"])

    def test_arquivo_trocado_a_mais_ou_ausente_dentro_da_cifra(self):
        casos = {"trocado": dict(extras=[("files/AGENTS.md", tarfile.REGTYPE, b"outro conteudo", "")], sem=("files/AGENTS.md",)),
                 "a mais": dict(extras=[("files/extra.txt", tarfile.REGTYPE, b"a mais", "")]),
                 "ausente": dict(sem=("files/AGENTS.md",))}
        for nome, kw in casos.items():
            with self.subTest(nome):
                shutil.rmtree(self.tmp / "forjada", ignore_errors=True)
                r = self.conferir(**self.forjar(self.claro, **kw))
                self.assertFalse(r["ok"], nome)
                self.assertIn("não conferem com o manifesto interno", r["motivo"])
        self.assertTrue(all(not x["ok"] for x in self.linhas()))

    def test_banco_corrompido_com_o_hash_certo_nao_passa_no_integrity_check(self):
        banco = self.claro / "state" / "state.sqlite"
        banco.write_bytes(b"isto nao e um banco sqlite" * 400)
        manifesto = json.loads((self.claro / "manifest.json").read_text(encoding="utf-8"))
        manifesto["db_sha256"] = sha(banco.read_bytes())
        (self.claro / "manifest.json").write_text(json.dumps(manifesto, indent=2), encoding="utf-8")
        r = self.conferir(**self.forjar(self.claro))
        self.assertFalse(r["ok"], r)
        self.assertTrue("integrity_check" in r["motivo"] or "decifrado" in r["motivo"], r["motivo"])

    def test_membro_de_caminho_absoluto_ou_ligacao_dentro_da_cifra(self):
        for nome, tipo, alvo in (("/fora.txt", tarfile.REGTYPE, ""), ("files/../../fora.txt", tarfile.REGTYPE, ""),
                                 ("files/ligacao", tarfile.SYMTYPE, "/etc/passwd")):
            with self.subTest(nome):
                shutil.rmtree(self.tmp / "forjada", ignore_errors=True)
                r = self.conferir(**self.forjar(self.claro, extras=[(nome, tipo, b"" if alvo else b"x", alvo)]))
                self.assertFalse(r["ok"], nome)

    def test_chaveiro_longo_demais_recusa_antes_de_tudo(self):
        with mock.patch("subprocess.Popen", side_effect=AssertionError("chamou o gpg")):
            with self.assertRaises(CifraRecusada):
                self.conferir(casa=self.tmp / ("c" * 120))
        self.assertFalse(self.registro.exists())

    def test_o_agente_e_encerrado_por_padrao_no_fim(self):
        with mock.patch.object(titular_copia, "encerrar_agente") as agente:
            titular_copia.conferir_conteudo(self.cifrada, A.casa, sha256_manifesto=self.ancora, exe=EXE, extras_gpg=EXTRAS,
                                            registro=self.registro)
        agente.assert_called_once()


class TestDecifrar(Base):
    def test_decifra_para_a_pasta_da_copia(self):
        destino = self.tmp / "dec"
        r = titular_copia.decifrar(MOLDE[0] / "cifrada", destino, A.casa, sha256_manifesto=MOLDE[1]["sha256_manifesto"], exe=EXE,
                                   extras_gpg=EXTRAS, encerrar=False)
        self.assertTrue(r["ok"])
        self.assertEqual(conteudo_da_pasta(destino), conteudo_da_pasta(MOLDE[0] / "claro"))

    def test_chaveiro_longo_demais_recusa(self):
        with self.assertRaises(CifraRecusada):
            titular_copia.decifrar(MOLDE[0] / "cifrada", self.tmp / "dec", self.tmp / ("c" * 120), exe=EXE)
        self.assertFalse((self.tmp / "dec").exists())

    def livro(self, *ancoras, raiz: str = "raiz") -> Path:
        livro = self.tmp / raiz / "state" / "copias.jsonl"
        livro.parent.mkdir(parents=True)
        livro.write_text("".join(json.dumps({"sha256_manifesto": a}) + "\n" for a in ancoras), encoding="utf-8", newline="\n")
        return livro

    def test_f7_a_ancora_vem_do_titular_o_livro_sozinho_nao_basta(self):
        livro = self.livro(MOLDE[1]["sha256_manifesto"])  # até o livro certo: a sessão grava nele, então não ancora
        for nome, kw in {"sem nada": {}, "só o livro": {"livro": livro}, "código em branco": {"sha256_manifesto": "  ", "livro": livro}}.items():
            with self.subTest(nome), mock.patch("subprocess.Popen", side_effect=AssertionError("chamou o gpg")):
                with self.assertRaises(ValidationError) as e:
                    titular_copia.decifrar(MOLDE[0] / "cifrada", self.tmp / "dec", A.casa, exe=EXE, extras_gpg=EXTRAS, **kw)
            self.assertIn("--sha256-manifesto", str(e.exception))
            self.assertIn("--aceitar-sem-ancora", str(e.exception))
            self.assertFalse((self.tmp / "dec").exists())

    def test_f7_livro_adulterado_com_a_ancora_de_uma_copia_trocada_nao_decifra(self):
        pasta = self.tmp / "outra"
        copia_sintetica(pasta / "claro", {**arquivos_de_teste(), "AGENTS.md": b"forjado\n"})
        forjada = cifrar_copia(pasta / "claro", pasta / "cifrada", A.publica, tamanho_parte=64 * 1024, exe=EXE)
        livro = self.livro(forjada["sha256_manifesto"])
        with mock.patch("subprocess.Popen", side_effect=AssertionError("chamou o gpg")):
            with self.assertRaises(ValidationError):  # sem o código do titular
                titular_copia.decifrar(pasta / "cifrada", self.tmp / "dec", A.casa, exe=EXE, extras_gpg=EXTRAS, livro=livro)
            with self.assertRaises(ValidationError) as e:  # com o código da cópia verdadeira: a trocada diverge
                titular_copia.decifrar(pasta / "cifrada", self.tmp / "dec", A.casa, exe=EXE, extras_gpg=EXTRAS, livro=livro,
                                       sha256_manifesto=MOLDE[1]["sha256_manifesto"])
        self.assertEqual(e.exception.details["verificacao"]["ancora"]["situacao"], "divergente")
        self.assertFalse((self.tmp / "dec").exists())

    def test_aceitar_sem_ancora_e_a_escolha_dele_e_o_livro_nao_entra(self):
        livro = self.livro(MOLDE[1]["sha256_manifesto"])
        r = titular_copia.decifrar(MOLDE[0] / "cifrada", self.tmp / "dec", A.casa, exe=EXE, extras_gpg=EXTRAS, encerrar=False,
                                   livro=livro, aceitar_sem_ancora=True)
        self.assertTrue(r["ok"])
        self.assertEqual(r["ancora"]["situacao"], "ausente")  # o livro não conferiu nada
        self.assertIn("aviso_ancora", r)
        self.assertNotIn("livro_de_copias", r)

    def test_o_livro_e_a_segunda_conferencia_com_o_codigo_do_titular(self):
        casos = {"consta": self.livro(MOLDE[1]["sha256_manifesto"], raiz="r1"), "nao_consta": self.livro("0" * 64, raiz="r2")}
        for esperado, livro in casos.items():
            with self.subTest(esperado):
                destino = self.tmp / f"dec-{esperado}"
                r = titular_copia.decifrar(MOLDE[0] / "cifrada", destino, A.casa, exe=EXE, extras_gpg=EXTRAS, encerrar=False,
                                           livro=livro, sha256_manifesto=MOLDE[1]["sha256_manifesto"])
                self.assertEqual((r["ok"], r["ancora"]["fonte"], r["livro_de_copias"]), (True, "sha256 informado", esperado))
                self.assertEqual("aviso_livro" in r, esperado == "nao_consta")
        r = titular_copia.decifrar(MOLDE[0] / "cifrada", self.tmp / "dec-sem", A.casa, exe=EXE, extras_gpg=EXTRAS, encerrar=False,
                                   sha256_manifesto=MOLDE[1]["sha256_manifesto"])
        self.assertEqual(r["livro_de_copias"], "ausente")


if __name__ == "__main__":
    unittest.main()
