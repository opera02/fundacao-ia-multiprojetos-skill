"""Cópia cifrada, o lado do titular (1.7.11; desenho DESENHO-COPIA-CIFRADA-1.7.11, lote 4; prova N12).

Três comandos novos da ferramenta fixa do titular (`assets/host/fundacao_titular.py`): `preparar-chave-copia`, `conferir-copia` e
`decifrar-copia`, e o `-ChaveDaCopia` do `preparar-maquina.ps1`. A senha, que o titular digita na janela do gpg, entra aqui por
loopback (`extras_gpg`); a chave é de TESTE e o chaveiro, uma pasta curta temporária.
- N12: depois de cada comando (feito, falho ou recusado) não sobra `gpg-agent` vivo naquele --homedir.
- A ferramenta avisa, antes de pedir a senha, quando roda fora da cópia protegida (uma cópia alterada pediria a senha por conta
  própria); o parser aceita só as opções dos comandos; chaveiro acima de ~85 caracteres (forma do msys) e privada dentro da raiz
  recusam; o conferir-copia registra {"conferida_em", "ok"}, que o `backup situacao` lê.
- O hashes.json da cópia protegida (o plano do ajudante) leva os módulos novos do kit, que a ferramenta confere antes de importar.
- `preparar-maquina.ps1 -ChaveDaCopia`: conferência estática (o analisador do PowerShell, os parâmetros, a etapa de administrador
  antes da âncora no despacho) e PowerShell de verdade sem UAC: a simulação mostra o plano sem gravar, -SemUAC deixa pendente
  (código 3), arquivo que não é uma única chave pública recusa antes de qualquer gravação (código 2), chave diferente já
  instalada é conflito até -TrocarChaveDaCopia, a gravação (-SemDono, o que o UAC faria) segue a pasta e a ACL da âncora, não
  atravessa ligação e guarda a chave anterior; a etapa de administrador recusa sem o UAC (código 4).
Pastas descartáveis; nada em C:\\ProgramData nem no chaveiro do titular.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from apoio import ENV, KIT, SKILL
from test_host_projeto_ferramenta import FERRAMENTA, sha
from test_host_projeto_apoio import carregar_preparo
from test_host_windows import (ELEVADO, POWERSHELL, PS1, SENHA_DE_ENSAIO, _Base as _BaseWindows, fotografia,
                               gerar_chave)

sys.path.insert(0, str(KIT / "tests"))
from apoio_cifra import (LOOPBACK, arquivos_de_teste, chaveiros, conteudo_da_pasta, copia_sintetica,  # noqa: E402
                         exigir_gpg)

from fundacao.core import cifra_copia  # noqa: E402
from fundacao.core.backup_cifrado import cifrar_copia  # noqa: E402

EXTRAS = ("--batch", *LOOPBACK)
A = B = EXE = None


def setUpModule() -> None:
    global A, B, EXE
    EXE = exigir_gpg()
    A, B = chaveiros("Teste A", "Teste B")


def executar(cmd, *, timeout: int = 300, env=None) -> subprocess.CompletedProcess:
    """Roda `cmd` sem entrada (stdin fechada: nenhum filho espera senha no console) e, estourado o prazo, mata a ÁRVORE
    inteira antes de ler os canos: o `subprocess.run` mata só o processo e depois espera o fim dos canos, que um neto
    (o ssh-keygen do preparar-maquina, esperando senha) herdou e segura para sempre."""
    proc = subprocess.Popen([str(c) for c in cmd], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace", env=env)
    try:
        saida, erro = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=60)
        else:
            proc.kill()
        proc.communicate(timeout=30)
        raise
    return subprocess.CompletedProcess(proc.args, proc.returncode, saida, erro)


def carregar_ferramenta():
    spec = importlib.util.spec_from_file_location("_titular_copia_cifrada", FERRAMENTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)  # só define funções: nada roda
    return modulo


def processos_do_gpg_agent() -> list[str]:
    if os.name == "nt":
        r = subprocess.run([POWERSHELL or "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                            "Get-CimInstance Win32_Process -Filter \"Name='gpg-agent.exe'\" | ForEach-Object { $_.CommandLine }"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    else:
        r = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True, timeout=60)
    return [linha for linha in r.stdout.splitlines() if "gpg-agent" in linha]


def agentes_vivos(casa: Path) -> list[str]:
    """Os gpg-agent vivos naquele --homedir (na forma do gpg), dando ao encerramento até ~5 s para terminar."""
    alvo = cifra_copia.para_gpg(casa)
    for _ in range(25):
        vivos = [linha for linha in processos_do_gpg_agent() if alvo in linha]
        if not vivos:
            return []
        time.sleep(0.2)
    return vivos


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="tt-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.t = carregar_ferramenta()
        self.saida = io.StringIO()


class TestFerramenta(Base):
    def test_o_parser_so_aceita_as_opcoes_dos_comandos(self):
        p = self.t.construir_parser()
        a = p.parse_args(["preparar-chave-copia", "--raiz", "R", "--guardar-em", "G"])
        self.assertEqual((a.acao, a.guardar_em, a.casa, a.publica), ("preparar-chave-copia", "G", None, None))
        a = p.parse_args(["conferir-copia", "--origem", "O", "--sha256-manifesto", "a" * 64, "--casa", "C"])
        self.assertEqual((a.acao, a.origem, a.raiz, a.casa), ("conferir-copia", "O", None, "C"))
        a = p.parse_args(["decifrar-copia", "--origem", "O", "--destino", "D", "--aceitar-sem-ancora"])
        self.assertTrue(a.aceitar_sem_ancora)
        for ruim in (["preparar-chave-copia", "--raiz", "R"], ["conferir-copia"], ["decifrar-copia", "--origem", "O"],
                     ["conferir-copia", "--origem", "O", "--destino", "D"], ["conferir-copia", "--orig", "O"],
                     ["preparar-chave-copia", "--raiz", "R", "--guardar-em", "G", "--senha", "x"]):
            with self.subTest(ruim=ruim), mock.patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit):
                p.parse_args(ruim)

    def test_avisa_antes_da_senha_quando_roda_fora_da_copia_protegida(self):
        copia = self.t.conferir_copia()
        self.assertFalse(copia["protegida"])  # esta cópia da ferramenta fica na árvore da skill
        self.t._abrir_copia_cifrada(lambda texto="": self.saida.write(texto + "\n"))
        self.assertIn("AVISO", self.saida.getvalue())
        self.assertIn("pedir a sua senha por conta própria", self.saida.getvalue())
        outra = io.StringIO()
        with mock.patch.object(self.t, "conferir_copia", return_value={"protegida": True}):
            self.t._abrir_copia_cifrada(lambda texto="": outra.write(texto + "\n"))
        self.assertEqual(outra.getvalue(), "")

    def test_o_kit_carregado_e_o_desta_copia(self):
        k = self.t.kit_copia()
        self.assertTrue(Path(k.titular.__file__).resolve().is_relative_to(KIT.resolve()))

    def test_chaveiro_longo_e_privada_dentro_da_raiz_recusam_pelo_comando(self):
        raiz = self.tmp / "raiz"
        raiz.mkdir()
        casos = {"chaveiro longo": ["preparar-chave-copia", "--raiz", str(raiz), "--guardar-em", str(self.tmp / "g"),
                                    "--casa", str(self.tmp / ("c" * 120))],
                 "privada na raiz": ["preparar-chave-copia", "--raiz", str(raiz), "--guardar-em", str(raiz / "g"),
                                     "--casa", str(self.tmp / "casa")],
                 "conferir com chaveiro longo": ["conferir-copia", "--origem", str(self.tmp), "--casa", str(self.tmp / ("c" * 120))]}
        for nome, argv in casos.items():
            with self.subTest(nome), mock.patch("sys.stderr", new_callable=io.StringIO) as erro, \
                    mock.patch("subprocess.Popen", side_effect=AssertionError("chamou o gpg")):
                codigo = self.t._rodar(self.t.construir_parser().parse_args(argv))
            self.assertEqual(codigo, 2, nome)
            self.assertIn("Recusado", erro.getvalue())
        self.assertFalse((self.tmp / "casa").exists())


class TestFluxoDoTitular(Base):
    """preparar → conferir → decifrar, com a chave que o próprio comando criou; N12 depois de cada um."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.base = Path(tempfile.mkdtemp(prefix="tf-"))
        cls.addClassCleanup(shutil.rmtree, cls.base, ignore_errors=True)
        cls.t = carregar_ferramenta()
        cls.casa = cls.base / "casa"
        cls.saida_do_preparo = io.StringIO()
        cls.codigo = cls.t.preparar_chave_copia(cls.base / "raiz", cls.base / "guardar", casa=cls.casa,
                                                publica=cls.base / "pub" / "chave.asc", saida=cls.saida_do_preparo,
                                                extras_gpg=EXTRAS)
        cls.addClassCleanup(lambda: shutil.rmtree(cls.casa, ignore_errors=True))
        cls.claro = cls.base / "claro"
        copia_sintetica(cls.claro, arquivos_de_teste())
        cls.cifrada = cls.base / "cifrada"
        cls.r = cifrar_copia(cls.claro, cls.cifrada, cls.base / "pub" / "chave.asc", tamanho_parte=64 * 1024, exe=EXE)

    def test_preparar_chave_copia(self):
        texto = self.saida_do_preparo.getvalue()
        self.assertEqual(self.codigo, 0, texto)
        self.assertIn("Impressão digital da chave:", texto)
        self.assertIn("-ChaveDaCopia", texto)
        self.assertIn("seis palavras", texto)
        self.assertTrue((self.base / "pub" / "chave.asc").is_file())
        self.assertTrue((self.base / "guardar" / "chave-privada-protegida.asc").is_file())
        self.assertEqual(agentes_vivos(self.casa), [], "N12: o gpg-agent do chaveiro foi encerrado")

    def comando(self, funcao, *args, **kw):
        saida = io.StringIO()
        with mock.patch.object(self.t, "conferir_copia", return_value={"protegida": True}):
            codigo = funcao(*args, saida=saida, casa=self.casa, extras_gpg=EXTRAS, **kw)
        return codigo, saida.getvalue()

    def test_conferir_copia_registra_e_encerra_o_agente(self):
        registro = self.base / "conferencias.jsonl"
        antes = conteudo_da_pasta(self.cifrada)
        codigo, texto = self.comando(self.t.conferir_copia_cifrada, self.cifrada, sha256_manifesto=self.r["sha256_manifesto"],
                                     registro=registro)
        self.assertEqual(codigo, 0, texto)
        self.assertIn(f"conteúdo conferido: {len(arquivos_de_teste())} arquivos, banco íntegro", texto)
        self.assertIn("compare com a do seu papel", texto)
        linha = json.loads(registro.read_text(encoding="utf-8").splitlines()[-1])
        self.assertTrue(linha["ok"])
        self.assertTrue(linha["conferida_em"].endswith("Z"))
        self.assertEqual(conteudo_da_pasta(self.cifrada), antes)
        self.assertEqual(agentes_vivos(self.casa), [], "N12")

    def test_conferir_copia_que_nao_confere_diz_nao_conferiu_e_encerra_o_agente(self):
        registro = self.base / "conferencias-ruim.jsonl"
        codigo, texto = self.comando(self.t.conferir_copia_cifrada, self.cifrada, sha256_manifesto="0" * 64, registro=registro)
        self.assertEqual(codigo, 2)
        self.assertIn("NÃO CONFEREU", texto)
        self.assertFalse(json.loads(registro.read_text(encoding="utf-8"))["ok"])
        self.assertEqual(agentes_vivos(self.casa), [], "N12")

    def test_senha_errada_nao_confere_e_nao_deixa_agente(self):
        from fundacao.core.decifra_copia import encerrar_agente
        encerrar_agente(EXE, self.casa)  # senão o agente lembra da senha certa de outro teste
        saida = io.StringIO()
        with mock.patch.object(self.t, "conferir_copia", return_value={"protegida": True}):
            codigo = self.t.conferir_copia_cifrada(self.cifrada, sha256_manifesto=self.r["sha256_manifesto"], casa=self.casa,
                                                   saida=saida, registro=self.base / "c3.jsonl",
                                                   extras_gpg=("--batch", "--pinentry-mode", "loopback", "--passphrase", "errada"))
        self.assertEqual(codigo, 2, saida.getvalue())
        self.assertEqual(agentes_vivos(self.casa), [], "N12")

    def test_decifrar_copia_para_a_pasta_nova(self):
        destino = self.base / "decifrada"
        codigo, texto = self.comando(self.t.decifrar_copia_cifrada, self.cifrada, destino,
                                     sha256_manifesto=self.r["sha256_manifesto"])
        self.assertEqual(codigo, 0, texto)
        self.assertEqual(conteudo_da_pasta(destino), conteudo_da_pasta(self.claro))
        self.assertIn("sha256_manifesto_interno", texto)
        self.assertEqual(agentes_vivos(self.casa), [], "N12")

    def test_decifrar_copia_alterada_recusa_sem_pedir_a_senha(self):
        alterada = self.base / "alterada"
        shutil.copytree(self.cifrada, alterada)
        parte = sorted(alterada.glob("parte-*.gpg"))[0]
        dados = bytearray(parte.read_bytes())
        dados[len(dados) // 2] ^= 1
        parte.write_bytes(bytes(dados))
        with mock.patch("subprocess.Popen", side_effect=AssertionError("chamou o gpg")), \
                mock.patch.object(self.t, "conferir_copia", return_value={"protegida": True}):
            with self.assertRaises(self.t.Recusa) as e:
                self.t.decifrar_copia_cifrada(alterada, self.base / "nao-sai", sha256_manifesto=self.r["sha256_manifesto"],
                                              casa=self.casa, saida=io.StringIO(), extras_gpg=EXTRAS)
        self.assertIn("o gpg não foi chamado", str(e.exception))
        self.assertFalse((self.base / "nao-sai").exists())

    def raiz_com_livro(self, nome: str, *ancoras) -> Path:
        """Uma raiz de ensaio com o `state/copias.jsonl` (o que uma sessão consegue gravar) anotando as `ancoras`."""
        raiz = self.base / nome
        (raiz / "state").mkdir(parents=True)
        (raiz / "state" / "copias.jsonl").write_text("".join(json.dumps({"sha256_manifesto": a}) + "\n" for a in ancoras),
                                                     encoding="utf-8", newline="\n")
        return raiz

    def test_f7_livro_da_raiz_sozinho_nao_decifra_nem_o_certo(self):
        raiz = self.raiz_com_livro("raiz-f7a", self.r["sha256_manifesto"])
        destino = self.base / "f7a-nao-sai"
        with mock.patch("subprocess.Popen", side_effect=AssertionError("chamou o gpg")), \
                mock.patch.object(self.t, "conferir_copia", return_value={"protegida": True}):
            with self.assertRaises(self.t.Recusa) as e:
                self.t.decifrar_copia_cifrada(self.cifrada, destino, raiz=raiz, casa=self.casa, saida=io.StringIO(),
                                              extras_gpg=EXTRAS)
            argv = ["decifrar-copia", "--origem", str(self.cifrada), "--destino", str(destino), "--raiz", str(raiz)]
            with mock.patch("sys.stderr", new_callable=io.StringIO) as erro:
                codigo = self.t._rodar(self.t.construir_parser().parse_args(argv))
        for texto in (str(e.exception), erro.getvalue()):
            self.assertIn("--sha256-manifesto", texto)
            self.assertIn("--aceitar-sem-ancora", texto)
            self.assertIn("state/copias.jsonl", texto)
        self.assertEqual(codigo, 2)
        self.assertFalse(destino.exists())

    def test_f7_copia_trocada_com_livro_adulterado_nao_decifra(self):
        """Prova negativa: cópia refeita com a MESMA chave pública, âncora dela anotada no livro da raiz: sem o código do
        titular recusa; com o código da cópia verdadeira, a trocada diverge. Nada decifrado, gpg não chamado."""
        pasta = self.base / "f7b"
        copia_sintetica(pasta / "claro", {**arquivos_de_teste(), "AGENTS.md": b"forjado\n"})
        forjada = cifrar_copia(pasta / "claro", pasta / "cifrada", self.base / "pub" / "chave.asc", tamanho_parte=64 * 1024,
                               exe=EXE)
        raiz = self.raiz_com_livro("raiz-f7b", forjada["sha256_manifesto"])
        destino = self.base / "f7b-nao-sai"
        with mock.patch("subprocess.Popen", side_effect=AssertionError("chamou o gpg")), \
                mock.patch.object(self.t, "conferir_copia", return_value={"protegida": True}):
            with self.assertRaises(self.t.Recusa):
                self.t.decifrar_copia_cifrada(pasta / "cifrada", destino, raiz=raiz, casa=self.casa, saida=io.StringIO(),
                                              extras_gpg=EXTRAS)
            with self.assertRaises(self.t.Recusa) as e:
                self.t.decifrar_copia_cifrada(pasta / "cifrada", destino, raiz=raiz, sha256_manifesto=self.r["sha256_manifesto"],
                                              casa=self.casa, saida=io.StringIO(), extras_gpg=EXTRAS)
        self.assertIn("o gpg não foi chamado", str(e.exception))
        self.assertFalse(destino.exists())

    def test_f7_aceitar_sem_ancora_decifra_sem_usar_o_livro_e_o_livro_so_confere_em_segundo(self):
        raiz = self.raiz_com_livro("raiz-f7c", self.r["sha256_manifesto"])
        codigo, texto = self.comando(self.t.decifrar_copia_cifrada, self.cifrada, self.base / "f7c-aceita", raiz=raiz,
                                     aceitar_sem_ancora=True)
        resposta = json.loads(texto[texto.index("{"):])
        self.assertEqual(codigo, 0, texto)
        self.assertEqual(resposta["ancora"]["situacao"], "ausente")  # o livro certo não conferiu nada
        self.assertIn("aviso_ancora", resposta)
        sem_a_copia = self.raiz_com_livro("raiz-f7d", "0" * 64)
        codigo, texto = self.comando(self.t.decifrar_copia_cifrada, self.cifrada, self.base / "f7d-confere", raiz=sem_a_copia,
                                     sha256_manifesto=self.r["sha256_manifesto"])
        resposta = json.loads(texto[texto.index("{"):])
        self.assertEqual(codigo, 0, texto)
        self.assertEqual((resposta["ancora"]["fonte"], resposta["livro_de_copias"]), ("sha256 informado", "nao_consta"))
        self.assertIn("aviso_livro", resposta)
        self.assertEqual(agentes_vivos(self.casa), [], "N12")


class TestHashesDaCopiaProtegida(unittest.TestCase):
    def test_o_plano_leva_os_modulos_do_lado_do_titular(self):
        plano = carregar_preparo().plano_da_ferramenta(SKILL, "/usr/local/lib/fundacao-ia")
        arquivos = set(plano["hashes"]["arquivos"])
        for modulo in ("titular_copia", "decifra_copia", "backup_cifrado", "cifra_copia", "politica_cifra", "leia_me_cifrada",
                       "copia_cifrada"):
            self.assertIn(f"assets/fundacao-kit/fundacao/core/{modulo}.py", arquivos, modulo)
        self.assertIn("assets/host/fundacao_titular.py", arquivos)
        self.assertEqual(plano["hashes"]["arquivos"]["assets/host/fundacao_titular.py"], sha(FERRAMENTA))


@unittest.skipIf(ELEVADO, "o script recusa rodar elevado (código 2), por desenho: este ensaio exige a conta comum")
class ChaveDaCopiaNoPowerShell(_BaseWindows):
    def setUp(self):
        super().setUp()
        # Nenhum teste pode chegar à geração da chave do titular (o ssh-keygen esperaria a senha no console): a chave
        # fictícia, com senha, já existe, como nos outros testes do preparar-maquina.
        gerar_chave(self.chave, SENHA_DE_ENSAIO)
        self.chave_copia = self.base / "entrada" / "chave-da-copia.asc"
        self.chave_copia.parent.mkdir()
        self.chave_copia.write_bytes(A.publica.read_bytes())
        self.destino = self.base / "ProgramData" / "FundacaoIA" / "confianca" / "chave-da-copia.asc"

    def rodar(self, *args, relatorio: bool = True, python=sys.executable, copias=None):
        """Como o `_Base.rodar`, pelo `executar` (sem entrada; prazo que mata a árvore)."""
        if copias is None:
            copias = () if "-Backups" in map(str, args) else ("-SemBackups",)
        self.n += 1
        rel = self.base / f"relatorio-{self.n}.json"
        cmd = [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(self.ps1),
               "-Raiz", str(self.raiz), "-Titular", "titular", "-Chave", str(self.chave), "-Ancora", str(self.ancora),
               "-Ferramentas", str(self.ferramentas), *(["-Python", str(python)] if python else []),
               *map(str, copias), *map(str, args)]
        if relatorio:
            cmd += ["-Relatorio", str(rel)]
        p = executar(cmd, env=ENV)
        dados = json.loads(rel.read_text(encoding="utf-8")) if rel.is_file() else None
        return p, dados

    def ps(self, codigo: str, env: dict | None = None):
        """Funções do script (carregado com ponto) num PowerShell novo, pelo `executar`."""
        arq = self.base / f"trecho-{self.n}.ps1"
        self.n += 1
        prelude = "try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }"
        arq.write_text(prelude + chr(10) + f". '{PS1}'" + chr(10) + codigo + chr(10), encoding="utf-8-sig")
        p = executar([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", arq], env=env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return json.loads(p.stdout.strip().splitlines()[-1])

    def rodar_com(self, *args, arquivo=None, **kw):
        return self.rodar("-ChaveDaCopia", str(arquivo or self.chave_copia), "-AncoraChaveCopia", str(self.destino), *args, **kw)

    # ------------------------------------------------------------ estática
    def test_conferencia_estatica_do_script(self):
        texto = PS1.read_text(encoding="utf-8-sig")
        arq = self.base / "analisar.ps1"
        arq.write_text("$e = $null; $t = $null\n[void][System.Management.Automation.Language.Parser]::ParseFile("
                       f"'{PS1}', [ref]$t, [ref]$e)\n@{{ erros = @($e | ForEach-Object {{ $_.Message }}) }} | ConvertTo-Json -Compress\n",
                       encoding="utf-8-sig")
        p = executar([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", arq], env=ENV)
        self.assertEqual(json.loads(p.stdout.strip().splitlines()[-1])["erros"], [], p.stdout + p.stderr)
        for parametro in ("[string] $ChaveDaCopia", "[string] $AncoraChaveCopia", "[switch] $TrocarChaveDaCopia",
                          "[switch] $EtapaChaveCopia", "[string] $ChaveDaCopiaEsperada"):
            self.assertIn(parametro, texto)
        self.assertIn(r"'FundacaoIA\confianca\chave-da-copia.asc'", texto)
        despacho = texto[texto.rindex("if ($MyInvocation.InvocationName -ne '.')"):]
        self.assertLess(despacho.index("$EtapaChaveCopia"), despacho.index("$EtapaAncora -or $EtapaFerramenta"))
        etapa = texto[texto.index("function Invoke-EtapaChaveCopiaInterna"):texto.index("function Invoke-EtapaChaveCopia {")]
        for exigencia in ("Test-Elevado", "Get-FundacaoQueContem $PSScriptRoot", "Test-CaminhoAncora $AncoraChaveCopia",
                          "$ChaveDaCopiaEsperada", "Install-ChaveDaCopia"):
            self.assertIn(exigencia, etapa)
        instalar = texto[texto.index("function Install-ChaveDaCopia"):texto.index("function Invoke-EtapaChaveCopiaInterna")]
        for exigencia in ("Set-AclProtegida", "Set-AclArquivoHerdada", "Test-ReparsePoint", "-Trocar"):
            self.assertIn(exigencia, instalar)
        self.assertIn("'EtapaChaveCopia', 'ChaveDaCopiaEsperada'", texto, "fora do comando pronto das cópias")
        self.assertIn(" 2c. Chave pública da cópia de segurança CIFRADA", texto, "documentada no cabeçalho")

    # ------------------------------------------------------------ plano
    def test_simulacao_mostra_o_plano_e_nao_grava(self):
        antes = fotografia(self.raiz, self.chave.parent, self.base / "ProgramData")
        p, rel = self.rodar_com("-Simular", "-Projeto", "caso-real")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(fotografia(self.raiz, self.chave.parent, self.base / "ProgramData"), antes)
        item = self.item(rel, "chave-da-copia")
        self.assertEqual((item["acao"], item["exige_admin"], item["sha256"]), ("criar", True, sha(self.chave_copia)))
        self.assertEqual(item["caminho"], str(self.destino))
        self.assertIn("confirmação", item["detalhe"])
        self.assertFalse(self.destino.exists())

    def test_sem_uac_deixa_pendente_e_nao_grava(self):
        p, rel = self.rodar_com("-SemUAC", "-Projeto", "caso-real")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual(self.item(rel, "chave-da-copia")["acao"], "pendente_admin")
        self.assertTrue(any("chave pública da cópia cifrada" in x for x in rel["pendencias"]))
        self.assertFalse(self.destino.exists())

    def test_sem_a_opcao_nada_muda(self):
        p, rel = self.rodar("-Simular", "-Projeto", "caso-real")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertNotIn("chave-da-copia", [i["id"] for i in rel["itens"]])

    def test_arquivo_que_nao_e_uma_unica_chave_publica_recusa_antes_de_gravar(self):
        pasta = self.base / "ruins"
        pasta.mkdir()
        casos = {"privada": A.privada, "ausente": pasta / "nao-existe.asc"}
        (pasta / "duas.asc").write_bytes(A.publica.read_bytes() + b"\n" + B.publica.read_bytes())
        (pasta / "texto.asc").write_text("isto não é uma chave\n", encoding="utf-8")
        (pasta / "grande.asc").write_bytes(A.publica.read_bytes() + b" " * (1 << 20))
        (pasta / "vazio.asc").write_bytes(b"")
        (pasta / "com-privada.asc").write_bytes(A.publica.read_bytes() + A.privada.read_bytes())
        for nome in ("duas", "texto", "grande", "vazio", "com-privada"):
            casos[nome] = pasta / f"{nome}.asc"
        for nome, arquivo in casos.items():
            with self.subTest(nome):
                antes = fotografia(self.base / "ProgramData", self.chave.parent)
                p, rel = self.rodar_com("-Simular", arquivo=arquivo)
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIn("-ChaveDaCopia", rel["mensagem"])
                self.assertIn("nada foi alterado", rel["mensagem"])
                self.assertEqual(fotografia(self.base / "ProgramData", self.chave.parent), antes)
        p, rel = self.rodar("-ChaveDaCopia", "chave-relativa.asc", "-AncoraChaveCopia", str(self.destino), "-Simular")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("caminho completo", rel["mensagem"])
        self.assertFalse(self.ancora.exists() or self.destino.exists())

    def test_caminho_da_chave_na_raiz_do_disco_ou_no_perfil_recusa(self):
        for ruim in (str(Path(self.base.anchor) / "chave-da-copia.asc"), str(Path(os.environ["USERPROFILE"]) / "chave-da-copia.asc")):
            with self.subTest(ruim=ruim):
                p, rel = self.rodar("-ChaveDaCopia", str(self.chave_copia), "-AncoraChaveCopia", ruim, "-Simular")
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIn("chave da cópia", rel["mensagem"])

    def test_outra_chave_ja_instalada_e_conflito_ate_a_troca(self):
        self.destino.parent.mkdir(parents=True)
        self.destino.write_bytes(B.publica.read_bytes())
        p, rel = self.rodar_com("-Simular", "-Projeto", "caso-real")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        item = self.item(rel, "chave-da-copia")
        self.assertEqual(item["acao"], "conflito")
        self.assertIn("-TrocarChaveDaCopia", item["detalhe"])
        p, rel = self.rodar_com("-Simular", "-TrocarChaveDaCopia", "-Projeto", "caso-real")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.item(rel, "chave-da-copia")["acao"], "atualizar")
        self.assertEqual(self.destino.read_bytes(), B.publica.read_bytes(), "a simulação não troca nada")

    # ------------------------------------------------------------ gravação (o que o UAC faria, sem UAC)
    def instalar(self, bytes_py: bytes, destino: Path, extra: str = "", trocar: bool = False) -> dict:
        arquivo = self.base / f"chave-a-instalar-{self.n}.bin"
        arquivo.write_bytes(bytes_py)
        return self.ps(
            "$acoes = New-Object System.Collections.Generic.List[string]; $erro = $null\n"
            f"{extra}\n"
            f"try {{ Install-ChaveDaCopia ([IO.File]::ReadAllBytes('{arquivo}')) '{destino}' $acoes -SemDono{' -Trocar' if trocar else ''} }}\n"
            "catch { $erro = $_.Exception.Message }\n"
            "@{ erro = $erro; acoes = $acoes.ToArray() } | ConvertTo-Json -Compress -Depth 4")

    def test_grava_na_pasta_da_ancora_e_e_idempotente(self):
        r = self.instalar(A.publica.read_bytes(), self.destino)
        self.assertIsNone(r["erro"], r)
        self.assertEqual(self.destino.read_bytes(), A.publica.read_bytes())
        self.assertTrue(any("chave pública da cópia gravada, herdando da pasta, dono Administradores" in a for a in r["acoes"]), r["acoes"])
        r = self.instalar(A.publica.read_bytes(), self.destino)
        self.assertIsNone(r["erro"], r)
        self.assertTrue(any("já era esta" in a for a in r["acoes"]), r["acoes"])
        self.assertEqual(sorted(p.name for p in self.destino.parent.iterdir()), ["chave-da-copia.asc"])

    def test_outra_chave_so_com_a_troca_e_guarda_a_anterior(self):
        self.instalar(A.publica.read_bytes(), self.destino)
        r = self.instalar(B.publica.read_bytes(), self.destino)
        self.assertIn("-TrocarChaveDaCopia", r["erro"])
        self.assertEqual(self.destino.read_bytes(), A.publica.read_bytes())
        r = self.instalar(B.publica.read_bytes(), self.destino, trocar=True)
        self.assertIsNone(r["erro"], r)
        self.assertEqual(self.destino.read_bytes(), B.publica.read_bytes())
        anteriores = [p for p in self.destino.parent.iterdir() if ".anterior-" in p.name]
        self.assertEqual([p.read_bytes() for p in anteriores], [A.publica.read_bytes()])

    def test_pasta_trocada_por_juncao_nao_e_atravessada(self):
        from apoio import criar_ligacao_dir
        fora = self.base / "fora"
        fora.mkdir()
        destino = self.base / "ProgramData2" / "FundacaoIA" / "confianca" / "chave-da-copia.asc"
        destino.parent.parent.mkdir(parents=True)
        criar_ligacao_dir(destino.parent, fora)
        r = self.instalar(A.publica.read_bytes(), destino)
        self.assertIn("é ligação", r["erro"])
        self.assertEqual(list(fora.iterdir()), [], "a chave foi gravada através da ligação")

    def test_a_etapa_de_administrador_recusa_sem_o_uac(self):
        p = executar([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", self.ps1,
                      "-EtapaChaveCopia", "-ChaveDaCopia", self.chave_copia, "-AncoraChaveCopia", self.destino,
                      "-ChaveDaCopiaEsperada", sha(self.chave_copia)], env=ENV)
        self.assertEqual(p.returncode, 4, p.stdout + p.stderr)
        self.assertFalse(self.destino.exists())


if __name__ == "__main__":
    unittest.main()
