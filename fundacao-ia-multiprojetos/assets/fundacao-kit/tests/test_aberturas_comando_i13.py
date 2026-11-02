"""Item I13 da integração da 1.7.10: os dois baixos da última reconferência do pacote ABERTURAS (REV4), em
core/aberturas_comando.py.
- Sem a cópia protegida do Ubuntu à vista, o `onde_rodar` começa pelo passo que falta e não manda colar as formas do
  Ubuntu (a janela abriria e fecharia sem mensagem; as chaves ficam na saída, para depois do preparo); "a janela espera
  um Enter no fim" só da forma cuja cópia foi vista; na sessão do Windows, que não enxerga o Ubuntu, a forma do Ubuntu
  vem com a condição do preparo do WSL.
- O Python registrado no hashes.json da cópia do Windows só vale se esta conta não o altera (a sondagem da âncora, sem
  ler o binário como allowed_signers) e se o SHA-256 dele confere: um Python numa pasta desta conta (como o por usuário,
  em AppData) fica pendente, citado no motivo.
- Toda forma chama o Python com -I -B -S (nenhum .pth de site-packages roda antes da ferramenta).
- Revisão da integração: a cópia do Ubuntu só conta à vista se ela e as pastas acima são de root, sem ligação nem
  escrita de grupo ou de outros (defeito 6); sem as duas cópias, o passo diz que as formas do Ubuntu dependem só do
  preparo do WSL (defeito 10).
Cada teste reprova o código anterior. Pastas descartáveis e dados fictícios: a cópia do Ubuntu é simulada com
FERRAMENTA_POSIX numa pasta temporária e a do Windows com FERRAMENTA_WINDOWS; nada em /usr/local nem em
C:\\ProgramData."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  (põe o kit no sys.path)

from fundacao import KIT_VERSION
from fundacao.core import aberturas, aberturas_comando, decisoes


def citadas(r: dict) -> set[str]:
    """As chaves que o onde_rodar cita (entre aspas simples)."""
    return set(re.findall(r"'([a-z_]+)'", r["onde_rodar"]))


class ComandoCase(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="aberturas-i13-"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.posix = self.base / "lib-fundacao-ia"
        self.posix.mkdir()
        if os.name == "posix":  # a cópia do Ubuntu, vazia até instalar_ubuntu()
            self.trocar(aberturas_comando, "FERRAMENTA_POSIX", str(self.posix))
        self.trocar(aberturas_comando, "FERRAMENTA_WINDOWS", str(self.base / "sem-copia-windows"))
        self.trocar(aberturas_comando, "CAIXA_EXECUTAR", 10_000)  # a pasta temporária é longa; o limite tem teste

    def trocar(self, alvo, nome: str, valor) -> None:
        troca = mock.patch.object(alvo, nome, valor)
        troca.start()
        self.addCleanup(troca.stop)

    def ambiente_wsl(self) -> None:
        """O ambiente do kit no porteiro: sem SystemRoot nem windir, com WSL_DISTRO_NAME (emenda E1)."""
        ambiente = mock.patch.dict(os.environ, {}, clear=False)
        ambiente.start()
        self.addCleanup(ambiente.stop)
        for nome in ("SystemRoot", "windir"):
            os.environ.pop(nome, None)
        os.environ["WSL_DISTRO_NAME"] = "Ubuntu"

    def instalar_ubuntu(self, de_root: bool = True) -> Path:
        """A cópia do Ubuntu na pasta temporária. A do preparo do WSL é de root, numa cadeia de pastas de root; aqui o
        dono e o modo são simulados (`_de_root`), salvo com `de_root=False` (revisão da integração, defeito 6: só o
        arquivo existir não basta; a pasta temporária é desta conta)."""
        ferramenta = self.posix.joinpath(KIT_VERSION, *aberturas_comando.REL_FERRAMENTA)
        ferramenta.parent.mkdir(parents=True)
        ferramenta.write_text("# ferramenta fictícia do ensaio\n", encoding="utf-8")
        if de_root:
            self.trocar(aberturas_comando, "_de_root", lambda st: True)
        return ferramenta

    def instalar_windows(self, python: str = r"C:\Program Files\Python312\python.exe", sha256: str = "0" * 64) -> None:
        base = self.base / "programdata"
        (base / KIT_VERSION).mkdir(parents=True, exist_ok=True)
        (base / KIT_VERSION / "hashes.json").write_text(json.dumps(
            {"schema_version": aberturas_comando.ESQUEMA_HASHES, "versao": KIT_VERSION, "arquivos": {},
             "python": {"caminho": python, "sha256": sha256}}), encoding="utf-8")
        self.trocar(aberturas_comando, "FERRAMENTA_WINDOWS", str(base))

    def windows_pronto(self):
        """A cópia do Windows protegida e o Python dela conferido (a conferência tem testes próprios abaixo)."""
        self.instalar_windows()
        self.trocar(decisoes, "conferir_ancora", mock.Mock(return_value={"protegida": True}))
        self.trocar(aberturas_comando, "conferir_python", mock.Mock(return_value=None))


class TestOndeRodarSemACopiaDoUbuntu(ComandoCase):
    @unittest.skipUnless(os.name == "posix", "o kit no Linux do WSL (o fluxo do porteiro)")
    def test_no_wsl_sem_copia_nenhuma_comeca_pelo_passo_que_falta(self):
        self.ambiente_wsl()
        r = aberturas.comando_do_titular("/mnt/d/IA/fundacao", "juridico-lab", 3)
        onde = r["onde_rodar"]
        self.assertTrue(onde.startswith("Ainda não dá para assinar por aqui: "), onde)
        self.assertIn(r["ubuntu_pendente"], onde)
        self.assertIn(r["executar_windows_pendente"], onde)
        for forma in ("executar_ubuntu", "bash"):
            self.assertIn(forma, r)  # a chave fica na saída, para depois do preparo
            self.assertNotIn(f"'{forma}'", onde)  # mas o passo não manda colá-la
        self.assertNotIn("espera um Enter", onde)
        self.assertEqual(citadas(r) - set(r), set(), onde)
        # Revisão da integração (defeito 10): as formas do Ubuntu dependem só do preparo do WSL; a do Windows, do
        # preparar-maquina.ps1. Antes: "só rodam depois de um desses passos" (o do Windows parecia bastar).
        self.assertIn("As formas do Ubuntu desta saída (executar_ubuntu e bash) só rodam depois do preparo do WSL "
                      "(sudo); a do Windows aparece depois do preparar-maquina.ps1 (UAC).", onde)
        self.assertNotIn("de um desses passos", onde)
        self.instalar_ubuntu()  # com a cópia de root (simulada) à vista, volta a mandar a caixa Executar
        r = aberturas.comando_do_titular("/mnt/d/IA/fundacao", "juridico-lab", 3)
        self.assertNotIn("ubuntu_pendente", r)
        self.assertTrue(r["onde_rodar"].startswith("FORA do Claude. "), r["onde_rodar"])
        self.assertIn("cole o texto de 'executar_ubuntu'", r["onde_rodar"])
        self.assertIn("a janela espera um Enter no fim", r["onde_rodar"])
        self.assertIn("'bash'", r["onde_rodar"])  # o último recurso

    @unittest.skipUnless(os.name == "posix", "o kit no Linux do WSL (o fluxo do porteiro)")
    def test_no_wsl_com_a_copia_do_windows_e_sem_a_do_ubuntu_so_a_forma_do_windows(self):
        self.ambiente_wsl()
        self.windows_pronto()
        r = aberturas.comando_do_titular("/mnt/d/IA/fundacao", "juridico-lab", 3)
        onde = r["onde_rodar"]
        self.assertTrue(onde.startswith("FORA do Claude: tecle Win+R"), onde)
        self.assertIn("cole o texto de 'executar_windows'", onde)
        self.assertIn("a janela espera um Enter no fim", onde)
        self.assertIn("'ubuntu_pendente'", onde)
        self.assertIn("'powershell'", onde)
        for forma in ("executar_ubuntu", "bash"):
            self.assertIn(forma, r)
            self.assertNotIn(f"'{forma}'", onde)
        self.assertEqual(citadas(r) - set(r), set(), onde)

    @unittest.skipUnless(os.name == "posix", "o kit no Linux")
    def test_linux_fora_do_wsl_sem_a_copia_nao_manda_colar_o_bash(self):
        ambiente = mock.patch.dict(os.environ, {}, clear=False)
        ambiente.start()
        self.addCleanup(ambiente.stop)
        os.environ.pop("WSL_DISTRO_NAME", None)
        self.trocar(aberturas_comando, "em_wsl", mock.Mock(return_value=False))
        r = aberturas.comando_do_titular("/srv/fundacao", "juridico-lab", 3)
        self.assertTrue(r["onde_rodar"].startswith("Ainda não dá para assinar por aqui: "), r["onde_rodar"])
        self.assertTrue(r["onde_rodar"].endswith("depois dele. O que falta: 'ubuntu_pendente'."), r["onde_rodar"])
        self.assertIn("bash", r)
        self.assertNotIn("'bash'", r["onde_rodar"])
        self.instalar_ubuntu()
        r = aberturas.comando_do_titular("/srv/fundacao", "juridico-lab", 3)
        self.assertTrue(r["onde_rodar"].startswith("FORA do Claude, num terminal novo, cole o texto de 'bash'"),
                        r["onde_rodar"])

    @unittest.skipUnless(os.name == "nt", "a sessão do Windows, que não enxerga o Ubuntu")
    def test_no_windows_a_forma_do_ubuntu_vem_com_a_condicao_do_preparo_do_wsl(self):
        if not os.environ.get("SystemRoot"):
            self.skipTest("sem SystemRoot no ambiente do Windows")
        raiz = self.base / "raiz"
        condicao = (f"só roda depois de o preparo do WSL (sudo) instalar a cópia protegida em "
                    f"{aberturas_comando.FERRAMENTA_POSIX}/{KIT_VERSION}; antes disso, a janela abre e fecha sem "
                    "mensagem")
        r = aberturas.comando_do_titular(raiz, "juridico-lab", 3)  # sem a cópia do Windows: só a forma do Ubuntu
        onde = r["onde_rodar"]
        self.assertIn("cole o texto de 'executar_ubuntu'", onde)
        self.assertIn(condicao, onde)
        self.assertNotIn("espera um Enter", onde)  # a cópia do Ubuntu não é vista daqui
        self.assertIn("A 'bash' também só roda depois do preparo do WSL (sudo).", onde)  # o último recurso também
        self.windows_pronto()
        r = aberturas.comando_do_titular(raiz, "juridico-lab", 3)
        onde = r["onde_rodar"]
        self.assertTrue(onde.startswith("FORA do Claude: tecle Win+R"), onde)
        self.assertIn("cole o texto de 'executar_windows'", onde)
        self.assertIn("a janela espera um Enter no fim", onde)  # a da cópia do Windows, conferida
        self.assertIn("use 'executar_ubuntu', que " + condicao, onde)
        self.assertEqual(citadas(r) - set(r), set(), onde)


class TestCopiaDoUbuntuDeRoot(ComandoCase):
    """Revisão da integração (defeito 6): a cópia do Ubuntu só conta à vista se o arquivo da ferramenta e cada pasta
    acima, até "/", são de root, sem ligação nem escrita de grupo ou de outros (lstat), a regra que a ferramenta exige
    ao rodar. Antes, bastava o arquivo existir: num Linux com /usr/local gravável pelo grupo, o kit indicaria uma cópia
    plantada. E (defeito 10) o passo sem as duas cópias, quando a do Windows não serve para a raiz."""

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0,
                         "dono e modo do POSIX, numa conta comum")
    def test_copia_numa_pasta_desta_conta_fica_pendente(self):
        self.ambiente_wsl()
        self.instalar_ubuntu(de_root=False)  # o arquivo existe, mas a pasta temporária é desta conta
        r = aberturas.comando_do_titular("/mnt/d/IA/fundacao", "juridico-lab", 3)
        pendente = r["ubuntu_pendente"]
        for trecho in ("não está protegida", "não é de root ou tem escrita de grupo ou de outros",
                       "refaça o passo do titular, com sudo, no preparo do WSL"):
            self.assertIn(trecho, pendente)
        onde = r["onde_rodar"]
        self.assertTrue(onde.startswith("Ainda não dá para assinar por aqui: "), onde)
        for forma in ("executar_ubuntu", "bash"):
            self.assertIn(forma, r)
            self.assertNotIn(f"'{forma}'", onde)
        self.assertNotIn("espera um Enter", onde)

    @unittest.skipUnless(os.name == "posix", "ligação simbólica do POSIX")
    def test_ligacao_no_caminho_fica_pendente(self):
        self.ambiente_wsl()
        ferramenta = self.instalar_ubuntu()  # dono e modo simulados: só a ligação decide
        self.assertNotIn("ubuntu_pendente", aberturas.comando_do_titular("/mnt/d/IA/fundacao", "juridico-lab", 3))
        real = self.base / "ferramenta-real.py"
        ferramenta.rename(real)
        ferramenta.symlink_to(real)  # o arquivo da ferramenta é ligação
        r = aberturas.comando_do_titular("/mnt/d/IA/fundacao", "juridico-lab", 3)
        self.assertIn(f"ligação no caminho: {ferramenta}", r["ubuntu_pendente"])
        ferramenta.unlink()
        real.rename(ferramenta)
        pasta = self.posix / KIT_VERSION
        outra = self.base / "versao-real"
        pasta.rename(outra)
        pasta.symlink_to(outra, target_is_directory=True)  # uma pasta acima é ligação
        r = aberturas.comando_do_titular("/mnt/d/IA/fundacao", "juridico-lab", 3)
        self.assertIn(f"ligação no caminho: {pasta}", r["ubuntu_pendente"])

    def test_regra_do_dono_e_do_modo(self):
        def st(modo: int, dono: int) -> os.stat_result:
            return os.stat_result((modo, 0, 0, 1, dono, 0, 0, 0, 0, 0))
        self.assertTrue(aberturas_comando._de_root(st(0o40755, 0)))
        self.assertTrue(aberturas_comando._de_root(st(0o100644, 0)))
        for modo, dono in ((0o40775, 0), (0o40757, 0), (0o100664, 0), (0o41777, 0), (0o40755, 1000)):
            with self.subTest(modo=oct(modo), dono=dono):
                self.assertFalse(aberturas_comando._de_root(st(modo, dono)))

    @unittest.skipUnless(os.name == "posix", "dono e modo do POSIX")
    def test_caminho_de_root_de_verdade_vale(self):
        """A regra aceita uma cadeia de root de verdade (sem simulação): o /usr/bin/env do sistema."""
        alvo = Path("/usr/bin/env")
        try:
            cadeia = [os.lstat(p) for p in (alvo, *alvo.parents)]
        except OSError:
            self.skipTest("sem /usr/bin/env neste sistema")
        if not stat.S_ISREG(cadeia[0].st_mode) or any(stat.S_ISLNK(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o022
                                                      for s in cadeia):
            self.skipTest("o /usr/bin/env deste sistema não está numa cadeia de root sem ligação")
        self.assertIsNone(aberturas_comando._pendencia_da_copia_posix(str(alvo)))
        self.assertIn("ainda não foi instalada", aberturas_comando._pendencia_da_copia_posix("/usr/bin/nao-existe-x"))

    @unittest.skipUnless(os.name == "posix", "o kit no Linux do WSL (o fluxo do porteiro)")
    def test_sem_as_duas_copias_e_a_raiz_sem_caminho_no_windows(self):
        self.ambiente_wsl()
        os.environ.pop("WSL_DISTRO_NAME", None)  # sem a variável, /home/... não tem caminho no Windows
        self.trocar(aberturas_comando, "em_wsl", mock.Mock(return_value=True))
        self.windows_pronto()
        r = aberturas.comando_do_titular("/home/ensaio/fundacao", "juridico-lab", 3)
        self.assertEqual(r["executar_windows_pendente"], "a raiz não tem caminho equivalente no Windows")
        self.assertIn("As formas do Ubuntu desta saída (executar_ubuntu e bash) só rodam depois do preparo do WSL "
                      "(sudo); a do Windows não sai para esta raiz.", r["onde_rodar"])
        self.assertEqual(citadas(r) - set(r), set(), r["onde_rodar"])


class TestPythonRegistradoNaCopiaDoWindows(ComandoCase):
    def test_sha256_registrado_confere_e_forma_do_registro(self):
        python = self.base / "python.exe"
        python.write_bytes(b"MZ python ficticio do ensaio")
        certo = hashlib.sha256(python.read_bytes()).hexdigest()
        self.trocar(aberturas_comando, "_alteravel", mock.Mock(return_value=[]))  # como se esta conta não o alterasse
        self.assertIsNone(aberturas_comando.conferir_python(python, certo))
        self.assertIn("não confere com o SHA-256", aberturas_comando.conferir_python(python, "0" * 64))
        for ruim in (None, "", "0" * 63, certo.upper(), 64):
            with self.subTest(sha256=ruim):
                self.assertIn("SHA-256 registrado", aberturas_comando.conferir_python(python, ruim))
        self.assertIn("não existe", aberturas_comando.conferir_python(self.base / "nao-existe.exe", certo))

    def test_python_numa_pasta_desta_conta_pode_ser_alterado(self):
        """A sondagem de verdade (sem mock): a pasta temporária é desta conta, como a de um Python por usuário."""
        python = self.base / "Python312" / "python.exe"
        python.parent.mkdir()
        python.write_bytes(b"MZ python ficticio do ensaio")
        motivo = aberturas_comando.conferir_python(python, hashlib.sha256(python.read_bytes()).hexdigest())
        self.assertIsNotNone(motivo)
        self.assertIn("pode ser alterado por esta conta", motivo)
        self.assertEqual(sorted(p.name for p in python.parent.iterdir()), ["python.exe"])  # a sonda não deixou nada

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0,
                         "permissões do POSIX (root grava em tudo)")
    def test_no_posix_python_somente_leitura_vale_e_ligacao_recusa(self):
        pasta = self.base / "usr-bin"
        pasta.mkdir()
        python = pasta / "python.exe"
        python.write_bytes(b"python ficticio do ensaio")
        sha = hashlib.sha256(python.read_bytes()).hexdigest()
        python.chmod(0o444)
        pasta.chmod(0o555)
        self.addCleanup(pasta.chmod, 0o755)  # antes do rmtree (as limpezas rodam da última para a primeira)
        self.assertIsNone(aberturas_comando.conferir_python(python, sha))
        self.assertIn("não confere", aberturas_comando.conferir_python(python, "f" * 64))
        atalho = self.base / "atalho.exe"
        atalho.symlink_to(python)
        self.assertIn("ligação", aberturas_comando.conferir_python(atalho, sha))

    @unittest.skipUnless(os.name == "nt", "a sondagem dos direitos desta conta no Windows")
    def test_no_windows_python_por_usuario_fica_pendente_citando_o_python(self):
        pasta = self.base / "AppData-Local-Programs-Python312"
        pasta.mkdir()
        python = pasta / "python.exe"
        python.write_bytes(b"MZ python ficticio do ensaio")
        self.instalar_windows(str(python), hashlib.sha256(python.read_bytes()).hexdigest())
        self.trocar(decisoes, "conferir_ancora", mock.Mock(return_value={"protegida": True}))  # a do hashes.json
        obtido, motivo = aberturas_comando.python_da_copia_windows()
        self.assertIsNone(obtido)
        for trecho in (str(python), "pode ser alterado por esta conta", "instalado para todos os usuários"):
            self.assertIn(trecho, motivo)
        r = aberturas.comando_do_titular(self.base / "raiz", "juridico-lab", 3)
        self.assertFalse({"executar_windows", "powershell"} & set(r))
        self.assertIn(str(python), r["executar_windows_pendente"])

    @unittest.skipUnless(os.name == "posix", "o kit no WSL: o Python do Windows visto por /mnt/c")
    def test_no_wsl_o_python_e_conferido_pelo_caminho_visto_do_wsl(self):
        python = r"C:\Ficticio-Fundacao-IA\Python312\python.exe"
        self.instalar_windows(python, "a" * 64)
        self.trocar(decisoes, "conferir_ancora", mock.Mock(return_value={"protegida": True}))
        with mock.patch.object(aberturas_comando, "conferir_python", return_value=None) as conferir:
            self.assertEqual(aberturas_comando.python_da_copia_windows(), (python, ""))
        conferir.assert_called_once_with(Path("/mnt/c/Ficticio-Fundacao-IA/Python312/python.exe"), "a" * 64)
        obtido, motivo = aberturas_comando.python_da_copia_windows()  # a conferência de verdade: o arquivo não existe
        self.assertIsNone(obtido)
        self.assertIn(python, motivo)
        self.assertIn("não existe neste computador", motivo)


class TestFormasSemSite(ComandoCase):
    def test_toda_forma_chama_o_python_com_menos_s(self):
        """-I não implica -S: sem ele, um .pth plantado em site-packages rodaria antes da ferramenta (REV4)."""
        if os.name == "posix":
            self.ambiente_wsl()
            self.instalar_ubuntu()
            raiz = "/mnt/d/IA/fundacao"
        elif not os.environ.get("SystemRoot"):
            self.skipTest("sem SystemRoot no ambiente do Windows")
        else:
            raiz = self.base / "raiz"
        self.windows_pronto()
        r = aberturas.comando_do_titular(raiz, "juridico-lab", 3)
        formas = {c: r[c] for c in ("executar_windows", "executar_ubuntu", "powershell", "bash") if c in r}
        self.assertEqual(set(formas), {"executar_windows", "executar_ubuntu", "powershell", "bash"}, r)
        for forma, comando in formas.items():
            with self.subTest(forma=forma):
                self.assertIn(f" {aberturas_comando.OPCOES_DO_PYTHON} ", comando)
                self.assertLess(comando.index(" -I -B -S "), comando.index("fundacao_titular.py"))
        self.assertEqual(aberturas_comando.OPCOES_DO_PYTHON, "-I -B -S")


if __name__ == "__main__":
    unittest.main()
