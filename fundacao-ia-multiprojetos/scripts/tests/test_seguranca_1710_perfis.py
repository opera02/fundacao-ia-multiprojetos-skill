"""Revisão de segurança da 1.7.10, rodada 4, grupo PERFIS: os perfis e os preparos do host.

- WSL-01: o perfil do Ubuntu de cada projeto nega a leitura da área root (`<área>/projetos/<o>/**`) e do lançador
  (`<bin>/abrir-fundacao-<o>`) de cada OUTRO projeto (os de projects/, os do registry/projetos-host.json e as áreas já
  gravadas), com invariante e a conferência do lançador; antes, o perfil não negava nem citava a área.
- WSL-02: o espelho `<raiz>/.claude/projetos/<p>/` não segue uma ligação posta no meio (o chmod e a gravação seguiam),
  e o ensaio com root (pastas que a conta escolhe) é recusado.
- HOOK-F9: o perfil do Windows nega a ferramenta Monitor, e toda ferramenta que roda comando fica coberta por hook ou
  negada nos dois perfis.
- HOOK-F8 (parte do perfil): o perfil do Ubuntu nega o /mnt/wslg (outro caminho da raiz no ext4) à Read, ao Grep e ao
  Glob.
- CI-F1 (código): o preparar-wsl.sh, o preparar-maquina.ps1, o preparar-projeto.ps1 e o preparo_host.py não rodam de
  dentro de `<raiz>/projects/`, e a mensagem aponta o programa da skill instalada.
- CI-F3 (código): no PowerShell, a elevação pelo powershell.exe da pasta do sistema e os cmdlets sensíveis pelo nome
  qualificado (uma função do perfil não os pega); no Ubuntu, o preparar-wsl.sh fixa o PATH, para diante de funções
  exportadas e do BASH_ENV e chama o sudo pelo caminho absoluto.

Pastas descartáveis, dados fictícios; nada de sudo, UAC, /etc ou casa real: os preparos rodam em simulação ou ensaio.
"""

from __future__ import annotations

import contextlib
import ctypes
import importlib.util
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import ENV, SCRIPTS, SKILL
from test_host_projeto_apoio import (LINUX, carregar_preparo, claude_de_ensaio, instalar, raiz_de_ensaio, sha,
                                     skill_de_ensaio, usuario_atual)
from test_host_windows import ELEVADO, SENHA_DE_ENSAIO, TEM_SSH, gerar_chave

RAIZ = "/mnt/e/Fundacao Exemplo"
POWERSHELL = shutil.which("powershell.exe") if os.name == "nt" else None
BASH = shutil.which("bash") if LINUX else None
PODE_BASH = bool(BASH) and Path("/usr/bin/python3").exists()
# As ferramentas do Claude Code que rodam comando de shell (references/fontes-verificadas.md: o sandbox cobre "Bash,
# PowerShell, Monitor"), conferidas contra a lista verificada do alertas_hooks.
COMANDO = ("Bash", "PowerShell", "Monitor")
# Os cmdlets que uma função do perfil do PowerShell pegaria no lugar do de verdade (CI-F3), com o módulo de cada um.
MODULO_DO_CMDLET = {"Start-Process": "Microsoft.PowerShell.Management", "Get-Process": "Microsoft.PowerShell.Management",
                    "Get-AuthenticodeSignature": "Microsoft.PowerShell.Security",
                    "Get-Acl": "Microsoft.PowerShell.Security", "Get-Item": "Microsoft.PowerShell.Management",
                    "Get-ChildItem": "Microsoft.PowerShell.Management", "Get-Command": "Microsoft.PowerShell.Core",
                    "ConvertFrom-Json": "Microsoft.PowerShell.Utility", "Add-Type": "Microsoft.PowerShell.Utility",
                    "Resolve-Path": "Microsoft.PowerShell.Management"}
SENSIVEIS = tuple(MODULO_DO_CMDLET)


def ps_literal(texto) -> str:
    return "'" + str(texto).replace("'", "''") + "'"


def pasta_do_sistema() -> str:
    buf = ctypes.create_unicode_buffer(520)
    ctypes.windll.kernel32.GetSystemDirectoryW(buf, 520)
    return buf.value


def linhas_de_codigo(caminho: Path) -> list[str]:
    """As linhas do script sem a ajuda (<# ... #>) e sem os comentários de linha inteira (o que roda)."""
    texto = re.sub(r"<#.*?#>", "", caminho.read_text(encoding="utf-8-sig"), flags=re.S)
    return [l for l in texto.splitlines() if not l.lstrip().startswith("#")]


# ------------------------------------------------------------------ WSL-01 e HOOK-F8: o perfil do Ubuntu
class AreaRootDosOutrosProjetos(unittest.TestCase):
    def setUp(self):
        self.m = carregar_preparo()
        self.kw = dict(raiz=r"E:\Fundacao Exemplo", projeto="caso-real", perfil_windows=r"C:\Users\titular-ensaio",
                       outros_projetos=["lab-b", "lab-a"])

    def perfil(self, **extra):
        return self.m.perfil_wsl(**{**self.kw, **extra})

    def test_cada_outro_projeto_tem_a_area_e_o_lancador_negados(self):
        negadas = self.perfil()["permissions"]["deny"]
        for o in ("lab-a", "lab-b"):
            self.assertIn(f"Read(//etc/fundacao-ia/projetos/{o}/**)", negadas)
            self.assertIn(f"Read(//usr/local/bin/abrir-fundacao-{o})", negadas)
        self.assertFalse([r for r in negadas if "caso-real" in r and ("/projetos/" in r or "abrir-fundacao" in r)])

    def test_registrados_e_areas_ja_gravadas_tambem_negados(self):
        negadas = self.perfil(projetos_registrados=["lab-arquivado", "caso-real"])["permissions"]["deny"]
        self.assertIn("Read(//etc/fundacao-ia/projetos/lab-arquivado/**)", negadas)
        self.assertIn("Read(//usr/local/bin/abrir-fundacao-lab-arquivado)", negadas)
        self.assertNotIn("Read(//etc/fundacao-ia/projetos/caso-real/**)", negadas)  # a própria área fica legível

    def test_area_e_pasta_do_lancador_do_ensaio(self):
        negadas = self.perfil(area_raiz="/tmp/ensaio/area", bin_dir="/tmp/ensaio/bin")["permissions"]["deny"]
        self.assertIn("Read(//tmp/ensaio/area/projetos/lab-a/**)", negadas)
        self.assertIn("Read(//tmp/ensaio/bin/abrir-fundacao-lab-a)", negadas)
        with self.assertRaises(ValueError):
            self.perfil(area_raiz="relativa/area")

    def test_invariante_acusa_o_perfil_sem_a_area_de_um_outro_projeto(self):
        perfil = self.perfil()
        perfil["permissions"]["deny"] = [r for r in perfil["permissions"]["deny"]
                                         if r != "Read(//etc/fundacao-ia/projetos/lab-a/**)"]
        for kw in ({}, {"area_raiz": "/etc/fundacao-ia", "bin_dir": "/usr/local/bin"}):
            with self.subTest(kw=kw):
                problemas = self.m.invariantes_perfil_wsl(perfil, RAIZ, "caso-real", **kw)
                self.assertTrue([p for p in problemas if "lab-a" in p and "área root" in p], problemas)
        self.assertTrue(self.m.conferir_perfil_wsl(perfil, RAIZ, "caso-real", ["lab-a", "lab-b"]))

    def test_conferir_compara_com_a_area_confiavel(self):
        perfil = self.perfil()
        self.assertEqual(self.m.conferir_perfil_wsl(perfil, RAIZ, "caso-real", ["lab-a", "lab-b"]), [])
        problemas = self.m.conferir_perfil_wsl(perfil, RAIZ, "caso-real", ["lab-a", "lab-b"],
                                               parametros={"area_raiz": "/outra/area", "bin_dir": "/usr/local/bin"})
        self.assertTrue(problemas)
        vagas = self.m.parametros_do_perfil_wsl(perfil, RAIZ)
        self.assertEqual((vagas["area_raiz"], vagas["bin_dir"], vagas["areas"]),
                         ("/etc/fundacao-ia", "/usr/local/bin", ["lab-a", "lab-b"]))


    def test_s3_o_executor_de_skills_dos_outros_projetos_tambem_e_negado_e_o_proprio_nao(self):
        negadas = self.perfil()["permissions"]["deny"]
        for o in ("lab-a", "lab-b"):
            self.assertIn(f"Read(//usr/local/bin/fundacao-skill-{o})", negadas)
        self.assertFalse([r for r in negadas if "fundacao-skill-caso-real" in r])  # o executor do próprio projeto fica
        negadas = self.perfil(projetos_registrados=["lab-arquivado"], area_raiz="/tmp/ensaio/area",
                              bin_dir="/tmp/ensaio/bin")["permissions"]["deny"]
        self.assertIn("Read(//tmp/ensaio/bin/fundacao-skill-lab-arquivado)", negadas)

    def test_s3_invariante_e_conferir_acusam_o_perfil_sem_o_executor_de_um_outro_projeto(self):
        perfil = self.perfil()
        perfil["permissions"]["deny"] = [r for r in perfil["permissions"]["deny"]
                                         if r != "Read(//usr/local/bin/fundacao-skill-lab-a)"]
        for kw in ({}, {"area_raiz": "/etc/fundacao-ia", "bin_dir": "/usr/local/bin"}):
            with self.subTest(kw=kw):
                problemas = self.m.invariantes_perfil_wsl(perfil, RAIZ, "caso-real", **kw)
                self.assertTrue([p for p in problemas if "lab-a" in p and "executor de skills" in p], problemas)
        self.assertTrue(self.m.conferir_perfil_wsl(perfil, RAIZ, "caso-real", ["lab-a", "lab-b"]))
        with self.assertRaises(self.m.EntradaInvalida):  # a leitura das vagas exige o executor de cada projeto
            self.m.parametros_do_perfil_wsl(perfil, RAIZ)
        completo = self.perfil()
        self.assertEqual(self.m.parametros_do_perfil_wsl(completo, RAIZ)["areas"], ["lab-a", "lab-b"])
        self.assertEqual(self.m.conferir_perfil_wsl(completo, RAIZ, "caso-real", ["lab-a", "lab-b"]), [])


class MntWslgNegado(unittest.TestCase):
    def setUp(self):
        self.m = carregar_preparo()
        self.kw = dict(raiz=r"E:\Fundacao Exemplo", projeto="caso-real", perfil_windows=r"C:\Users\titular-ensaio",
                       outros_projetos=["lab-a"])

    def test_o_perfil_nega_o_mnt_wslg_a_read_grep_e_glob(self):
        perfil = self.m.perfil_wsl(**self.kw)
        self.assertIn("Read(//mnt/wslg/**)", perfil["permissions"]["deny"])
        self.assertIn("/mnt/wslg", perfil["sandbox"]["filesystem"]["denyRead"])  # os comandos, como antes

    def test_invariante_acusa_o_perfil_sem_o_mnt_wslg(self):
        perfil = self.m.perfil_wsl(**self.kw)
        perfil["permissions"]["deny"].remove("Read(//mnt/wslg/**)")
        problemas = self.m.invariantes_perfil_wsl(perfil, RAIZ, "caso-real")
        self.assertTrue([p for p in problemas if "/mnt/wslg" in p], problemas)


# ------------------------------------------------------------------ HOOK-F9: ferramentas que rodam comando
def casa(matcher, nome: str) -> bool:
    """A regra do matcher do Claude Code (scripts/alertas_hooks.py): `*` ou vazio, todas; só letras, dígitos, `_`,
    `-`, espaço, `,` e `|`, lista exata; outro caractere, expressão sem âncora."""
    if matcher in (None, "", "*"):
        return True
    if re.fullmatch(r"[A-Za-z0-9_\-, |]*", str(matcher)):
        return nome in [n.strip() for n in re.split(r"[|,]", str(matcher)) if n.strip()]
    return re.search(str(matcher), nome) is not None


def ferramentas_do_hook_de_shell() -> set:
    texto = (SKILL / "assets" / "hooks" / "guarda_identidade.py").read_text(encoding="utf-8")
    return set(re.findall(r'"([^"]+)"', re.search(r"^SHELL_TOOLS\s*=\s*\{([^}]*)\}", texto, re.M).group(1)))


def cobertura(perfil) -> dict:
    """Como cada ferramenta que roda comando fica no perfil: negada, fora da lista fechada (com o guarda_ferramentas de
    matcher que casa tudo) ou com o hook que lê o comando (guarda_identidade, que a trata como shell); None: solta."""
    negadas = set(perfil["permissions"]["deny"])
    lista = perfil.get("env", {}).get("FUNDACAO_FERRAMENTAS")
    grupos = perfil["hooks"]["PreToolUse"]

    def com_hook(hook: str, ferramenta: str) -> bool:
        return any(casa(g.get("matcher"), ferramenta) and any(str(h["args"][-1]).endswith(hook) for h in g["hooks"])
                   for g in grupos)

    saida = {}
    for ferramenta in COMANDO:
        if ferramenta in negadas:
            saida[ferramenta] = "negada"
        elif lista is not None and ferramenta not in lista.split(",") and com_hook("guarda_ferramentas.py", ferramenta):
            saida[ferramenta] = "fora da lista fechada"
        elif com_hook("guarda_identidade.py", ferramenta) and ferramenta in ferramentas_do_hook_de_shell():
            saida[ferramenta] = "hook"
        else:
            saida[ferramenta] = None
    return saida


class FerramentasDeComando(unittest.TestCase):
    def setUp(self):
        self.m = carregar_preparo()

    def test_as_ferramentas_de_comando_sao_da_lista_verificada(self):
        spec = importlib.util.spec_from_file_location("alertas_hooks_perfis_1710", SCRIPTS / "alertas_hooks.py")
        alertas = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(alertas)
        self.assertTrue(set(COMANDO) <= set(alertas.FERRAMENTAS))

    def test_o_perfil_do_windows_nega_o_monitor(self):
        perfil = self.m.perfil_windows(raiz=r"E:\Fundacao Exemplo", python=r"C:\Py\python.exe", projeto="caso-real")
        self.assertIn("Monitor", perfil["permissions"]["deny"])
        self.assertEqual(cobertura(perfil), {"Bash": "hook", "PowerShell": "hook", "Monitor": "negada"})

    def test_toda_ferramenta_de_comando_coberta_nos_dois_perfis(self):
        windows = self.m.perfil_windows(raiz=r"E:\Fundacao Exemplo", python=r"C:\Py\python.exe", projeto="caso-real")
        ubuntu = self.m.perfil_wsl(raiz=r"E:\Fundacao Exemplo", projeto="caso-real",
                                   perfil_windows=r"C:\Users\titular-ensaio", outros_projetos=["lab-a"])
        for nome, perfil in (("Windows", windows), ("Ubuntu", ubuntu)):
            with self.subTest(perfil=nome):
                soltas = [f for f, como in cobertura(perfil).items() if como is None]
                self.assertEqual(soltas, [], f"perfil do {nome}: ferramenta que roda comando sem hook nem negação")
        # O do Ubuntu tem a lista fechada (o --tools do lançador e o guarda_ferramentas com matcher "*").
        self.assertEqual(cobertura(ubuntu), {"Bash": "hook", "PowerShell": "fora da lista fechada",
                                             "Monitor": "fora da lista fechada"})


# ------------------------------------------------------------------ WSL-02 e WSL-01 no preparo do Ubuntu
class _Area(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="seguranca-perfis-1710-")).resolve()
        self.skill = skill_de_ensaio(self.base)
        self.raiz = raiz_de_ensaio(self.base, self.skill)
        (self.base / "home").mkdir()
        self.claude = claude_de_ensaio(self.base / "claude-ensaio")
        self.area = self.base / "area" / "projetos" / "caso-real"
        self.espelho = self.raiz / ".claude" / "projetos" / "caso-real"

    def tearDown(self):
        for p in sorted(self.base.rglob("*"), reverse=True):
            try:
                if not p.is_symlink():
                    os.chmod(p, 0o700 if p.is_dir() else 0o600)
            except OSError:
                pass
        shutil.rmtree(self.base, ignore_errors=True)

    def instalar(self):
        r = instalar(self.skill, self.raiz, self.base, "caso-real", self.claude)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def instalar_no_processo(self):
        """O mesmo instalar-projeto de ensaio, no processo do teste (para pôr a troca no meio); a ficha fechada vem de um
        vigente de ensaio, sem importar o kit no processo."""
        return self.instalar_no_processo_com(carregar_preparo(self.skill))

    def instalar_no_processo_com(self, m):
        return m.instalar_projeto(
            vigente=lambda raiz, projeto, area: {"valida": False, "motivo_invalida": "ensaio sem ficha"},
            ensaio=True, raiz=str(self.raiz), projeto="caso-real", titular="titular", claude=str(self.claude),
            claude_versao="2.1.302", claude_sha256=sha(self.claude), origem_hash="ensaio",
            perfil_windows="/mnt/c/User" + "s/titular-ensaio", casa=str(self.base / "home"), usuario=usuario_atual(),
            area_raiz=str(self.base / "area"), bin_dir=str(self.base / "bin"), temp_base=str(self.base / "tmp"),
            sonda_interop_cmd=str(self.base / "sem-interop" / "cmd.exe"),
            sonda_interop_binfmt=str(self.base / "sem-interop" / "binfmt"),
            gerenciadas=str(self.base / "claude-code-gerenciado"), ferramenta_base=None)


def caminho_do_descritor(fd: int) -> str:
    return os.readlink(f"/proc/self/fd/{fd}")


@unittest.skipUnless(LINUX, "a área do titular e o espelho são do Ubuntu (WSL2): ligação, O_NOFOLLOW e dir_fd")
class EspelhoSemSeguirLigacao(_Area):
    def test_troca_do_arquivo_por_ligacao_no_meio_nao_muda_o_modo_da_vitima(self):
        """Contraprova (código de antes): no ramo "igual", o os.chmod por caminho seguia a ligação posta entre a
        conferência e o chmod, e a vítima (aqui, um arquivo 0600 fictício) virava 0644."""
        self.instalar()
        alvo = self.espelho / "settings.wsl.json"
        os.chmod(alvo, 0o600)  # o preparo quer devolver o 0644
        vitima = self.base / "vitima.txt"
        vitima.write_text("conteúdo fictício da vítima\n", encoding="utf-8")
        os.chmod(vitima, 0o600)
        chmod, fchmod, trocado = os.chmod, os.fchmod, []

        def trocar():
            if not trocado:
                os.rename(alvo, str(alvo) + ".original")
                os.symlink(vitima, alvo)
                trocado.append(True)

        def chmod_com_troca(caminho, modo, *a, **kw):
            if os.fspath(caminho) == str(alvo):
                trocar()
            return chmod(caminho, modo, *a, **kw)

        def fchmod_com_troca(fd, modo):
            if caminho_do_descritor(fd) == str(alvo):
                trocar()
            return fchmod(fd, modo)

        with mock.patch("os.chmod", chmod_com_troca), mock.patch("os.fchmod", fchmod_com_troca):
            self.instalar_no_processo()
        self.assertEqual(stat.S_IMODE(os.stat(vitima).st_mode), 0o600)
        self.assertEqual(vitima.read_text(encoding="utf-8"), "conteúdo fictício da vítima\n")

    def test_troca_da_pasta_por_ligacao_no_meio_nao_grava_na_pasta_alvo(self):
        """Contraprova (código de antes): trocada a pasta do espelho por uma ligação para outra pasta (a área de outro
        projeto, por exemplo) logo depois da conferência, os arquivos de nome fixo do espelho iam para lá."""
        self.instalar()
        vitima = self.base / "area-b"
        vitima.mkdir()
        nomes = ("settings.wsl.json", "porteiro.json", "mcp.json", "aberturas.json", "hashes.json")
        for nome in nomes:
            (vitima / nome).write_text("conteúdo fictício do projeto B\n", encoding="utf-8")
        abrir, trocado = os.open, []

        def abrir_com_troca(caminho, flags, modo=0o777, *, dir_fd=None):
            cheio = (os.path.join(caminho_do_descritor(dir_fd), os.fspath(caminho)) if dir_fd is not None
                     else os.path.abspath(os.fspath(caminho)))
            if not trocado and cheio == str(self.espelho / "settings.wsl.json"):
                os.rename(self.espelho, str(self.espelho) + ".original")
                os.symlink(vitima, self.espelho, target_is_directory=True)
                trocado.append(True)
            return abrir(caminho, flags, modo, dir_fd=dir_fd)

        with mock.patch("os.open", abrir_com_troca):
            self.instalar_no_processo()
        for nome in nomes:
            self.assertEqual((vitima / nome).read_text(encoding="utf-8"), "conteúdo fictício do projeto B\n", nome)

    def test_ensaio_com_root_e_recusado_antes_de_gravar(self):
        """A variante do mesmo caminho: com sudo e as pastas do ensaio (--area-raiz e --bin, que a conta escolhe), o root
        gravaria por caminho numa pasta da conta. O ensaio roda sem root."""
        m = carregar_preparo(self.skill)
        with mock.patch.object(m, "_e_root", return_value=True), self.assertRaises(m.EntradaInvalida) as erro:
            self.instalar_no_processo_com(m)
        self.assertIn("sem root", str(erro.exception))
        self.assertFalse((self.base / "area").exists())
        self.assertFalse((self.base / "bin").exists())

    def test_ligacao_no_lugar_de_um_arquivo_do_espelho_vira_aviso(self):
        self.instalar()
        vitima = self.base / "vitima.txt"
        vitima.write_text("conteúdo fictício\n", encoding="utf-8")
        (self.espelho / "mcp.json").unlink()
        (self.espelho / "mcp.json").symlink_to(vitima)
        rel = self.instalar()
        self.assertEqual(vitima.read_text(encoding="utf-8"), "conteúdo fictício\n")
        self.assertIn("aviso", [a["acao"] for a in rel["acoes"] if a["item"] == "espelho"])


@unittest.skipUnless(LINUX, "a área do titular é do Ubuntu (WSL2): instalar-projeto só roda no Linux")
class AreaRootNoPreparo(_Area):
    def test_o_perfil_instalado_nega_as_areas_e_os_lancadores_dos_outros(self):
        registro = {"schema_version": "fundacao.projetos_host/1", "projetos": {
            "lab-arquivado": {"origens": [], "somente_leitura": [], "aninhadas_negadas": []}}}
        (self.raiz / "registry" / "projetos-host.json").write_text(json.dumps(registro), encoding="utf-8")
        (self.base / "area" / "projetos" / "lab-antigo").mkdir(parents=True)  # área de projeto que saiu de projects/
        self.instalar()
        negadas = json.loads((self.area / "settings.wsl.json").read_text(encoding="utf-8"))["permissions"]["deny"]
        area, binario = (self.base / "area").as_posix(), (self.base / "bin").as_posix()
        for o in ("lab-a", "lab-arquivado", "lab-antigo"):
            self.assertIn(f"Read(/{area}/projetos/{o}/**)", negadas)
            self.assertIn(f"Read(/{binario}/abrir-fundacao-{o})", negadas)
            self.assertIn(f"Read(/{binario}/fundacao-skill-{o})", negadas)  # 1.7.11, S3
        self.assertNotIn(f"Read(/{area}/projetos/caso-real/**)", negadas)
        m = carregar_preparo(self.skill)
        self.assertEqual(m.conferir_abertura(self.raiz, "caso-real", self.area)["problemas"], [])

    def test_area_gravada_depois_fecha_a_abertura(self):
        """Um projeto preparado depois deste (a área dele existe, a negação dele não está no perfil deste): o lançador
        não abre até o preparo deste rodar de novo."""
        self.instalar()
        (self.base / "area" / "projetos" / "lab-novo").mkdir()
        m = carregar_preparo(self.skill)
        res = m.conferir_abertura(self.raiz, "caso-real", self.area)
        self.assertFalse(res["ok"])
        self.assertTrue([p for p in res["problemas"] if "lab-novo" in p], res["problemas"])


# ------------------------------------------------------------------ CI-F1: nada roda de dentro de <raiz>/projects/
class DentroDeProjects(unittest.TestCase):
    """Uma cópia da skill dentro de `<raiz fictícia>/projects/p/` (a pasta que a sessão do projeto grava)."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="seguranca-ci-f1-1710-")).resolve()
        self.ficticia = self.base / "Raiz Ficticia"
        for pasta in ("registry", "projects/p"):
            (self.ficticia / pasta).mkdir(parents=True)
        (self.ficticia / "RETOMADA.md").write_text("# RETOMADA de ensaio\n", encoding="utf-8")
        self.skill = skill_de_ensaio(self.ficticia / "projects" / "p")
        self.origem = self.base / "origem"
        self.origem.mkdir()

    def tearDown(self):
        if os.name == "nt":
            subprocess.run(["icacls", str(self.base), "/reset", "/T", "/C", "/Q"], capture_output=True, timeout=120)
        shutil.rmtree(self.base, ignore_errors=True)

    def ajudante(self, *args):
        return subprocess.run([sys.executable, "-I", "-B", str(self.skill / "assets" / "host" / "preparo_host.py"),
                               *map(str, args)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=ENV, timeout=120)

    def assertRecusaDeProjects(self, texto: str):
        self.assertIn("projects", texto)
        self.assertIn("fundacao-ia-multiprojetos", texto)
        self.assertIn(".claude", texto)  # o programa da skill instalada
        self.assertIn("nada foi alterado", texto)

    def test_registrar_projeto_da_copia_contra_a_fundacao_que_a_contem_recusa(self):
        r = self.ajudante("registrar-projeto", "--raiz", self.ficticia, "--projeto", "p", "--origem", self.origem)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertRecusaDeProjects(json.loads(r.stdout)["erro"])
        self.assertFalse((self.ficticia / "registry" / "projetos-host.json").exists())

    def test_a_mesma_copia_contra_outra_raiz_roda(self):
        outra = self.base / "Outra Raiz"
        for pasta in ("registry", "projects/p"):
            (outra / pasta).mkdir(parents=True)
        r = self.ajudante("registrar-projeto", "--raiz", outra, "--projeto", "p", "--origem", self.origem)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((outra / "registry" / "projetos-host.json").is_file())

    def test_como_root_nenhum_comando_roda_de_dentro_de_projects(self):
        m = carregar_preparo(self.skill)
        saida = io.StringIO()
        with mock.patch.object(m, "_e_root", return_value=True), contextlib.redirect_stdout(saida):
            codigo = m.main(["instalar-canario", "--relatorio", str(self.base / "relatorio.json"), "--area-raiz",
                             str(self.base / "area")])
        self.assertEqual(codigo, 2, saida.getvalue())
        self.assertRecusaDeProjects(json.loads(saida.getvalue())["erro"])

    @unittest.skipUnless(PODE_BASH, "o preparar-wsl.sh roda no Linux (bash e /usr/bin/python3)")
    def test_preparar_wsl_de_dentro_de_projects_recusa(self):
        (self.base / "home").mkdir()
        conf = self.base / "wsl.conf"
        conf.write_text("[boot]\nsystemd=true\n", encoding="utf-8")
        r = subprocess.run([BASH, str(self.skill / "assets" / "host" / "wsl" / "preparar-wsl.sh"), "--raiz",
                            str(self.ficticia), "--projeto", "p", "--titular", "titular", "--simular", "--wsl-conf",
                            str(conf), "--python", "/usr/bin/python3"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300,
                           env={"HOME": str(self.base / "home"), "PATH": "/usr/bin:/bin"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertRecusaDeProjects(r.stderr)

    def powershell(self, script: Path, *args):
        relatorio = self.base / f"relatorio-{script.stem}.json"
        p = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                            str(script), *map(str, args), "-Relatorio", str(relatorio)], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=ENV, timeout=300)
        return p, (json.loads(relatorio.read_text(encoding="utf-8")) if relatorio.is_file() else None)

    @unittest.skipUnless(POWERSHELL, "PowerShell do Windows indisponível")
    def test_preparar_maquina_de_dentro_de_projects_recusa_na_simulacao(self):
        p, rel = self.powershell(self.skill / "assets" / "host" / "windows" / "preparar-maquina.ps1", "-Raiz",
                                 self.ficticia, "-Titular", "titular", "-Simular", "-SemBackups")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertRecusaDeProjects(rel["mensagem"])
        self.assertEqual(rel["itens"], [])

    @unittest.skipUnless(POWERSHELL and TEM_SSH, "PowerShell do Windows ou OpenSSH do sistema indisponível")
    def test_preparar_maquina_real_de_dentro_de_projects_recusa_tambem_em_outra_raiz(self):
        """O modo real (-SemUAC grava hooks e perfis) não roda de projects/ de fundação nenhuma, nem contra outra raiz."""
        outra = self.base / "Outra Raiz"
        for pasta in ("registry", "projects/caso-real"):
            (outra / pasta).mkdir(parents=True)
        chave = self.base / "ssh" / "fundacao_titular"
        chave.parent.mkdir()
        gerar_chave(chave, SENHA_DE_ENSAIO)  # chave de ensaio com senha: o script nunca a gera aqui
        p, rel = self.powershell(self.skill / "assets" / "host" / "windows" / "preparar-maquina.ps1", "-Raiz", outra,
                                 "-Titular", "titular", "-SemUAC", "-SemBackups", "-Python", sys.executable, "-Chave",
                                 chave, "-Ancora",
                                 self.base / "ProgramData" / "FundacaoIA" / "confianca" / "allowed_signers",
                                 "-Ferramentas", self.base / "ProgramData" / "FundacaoIA" / "ferramentas")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertRecusaDeProjects(rel["mensagem"])
        self.assertFalse((outra / ".claude").exists())

    @unittest.skipUnless(POWERSHELL, "PowerShell do Windows indisponível")
    def test_preparar_projeto_de_dentro_de_projects_recusa_na_simulacao(self):
        p, rel = self.powershell(self.skill / "assets" / "host" / "windows" / "preparar-projeto.ps1", "-Raiz",
                                 self.ficticia, "-Titular", "titular", "-Projeto", "p", "-Simular", "-SemBackups")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertRecusaDeProjects(rel["mensagem"])


# ------------------------------------------------------------------ CI-F3: o ambiente de quem chama não escolhe
@unittest.skipUnless(PODE_BASH, "o preparar-wsl.sh roda no Linux (bash e /usr/bin/python3)")
class AmbienteDeQuemChamaNoUbuntu(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="seguranca-ci-f3-wsl-1710-")).resolve()
        self.skill = skill_de_ensaio(self.base)
        self.raiz = raiz_de_ensaio(self.base, self.skill)
        self.preparar = self.skill / "assets" / "host" / "wsl" / "preparar-wsl.sh"
        (self.base / "home").mkdir()
        self.conf = self.base / "wsl.conf"
        self.conf.write_text("[boot]\nsystemd=true\n", encoding="utf-8")
        self.marca = self.base / "marca-interceptado"

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def rodar(self, env: dict):
        return subprocess.run([BASH, str(self.preparar), "--raiz", str(self.raiz), "--projeto", "caso-real",
                               "--titular", "titular", "--simular", "--wsl-conf", str(self.conf), "--python",
                               "/usr/bin/python3", "--perfil-windows", "/mnt/c/User" + "s/titular-ensaio"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
                              env={"HOME": str(self.base / "home"), "PATH": "/usr/bin:/bin", **env})

    def test_o_path_de_quem_chama_nao_escolhe_os_programas(self):
        falsos = self.base / "falsos"
        falsos.mkdir()
        (falsos / "id").write_text(f"#!/bin/sh\n/usr/bin/touch '{self.marca}'\nexec /usr/bin/id \"$@\"\n",
                                   encoding="utf-8", newline="\n")
        (falsos / "id").chmod(0o755)
        r = self.rodar({"PATH": f"{falsos}:/usr/bin:/bin"})
        self.assertFalse(self.marca.exists(), r.stdout + r.stderr)

    def test_funcao_exportada_para_o_preparo_antes_de_tudo(self):
        r = self.rodar({"BASH_FUNC_id%%": f"() {{ /usr/bin/touch '{self.marca}'; /usr/bin/id \"$@\"; }}"})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("funções exportadas", r.stderr)
        self.assertFalse(self.marca.exists())
        self.assertNotIn("Raiz:", r.stdout)  # nada do preparo rodou

    def test_bash_env_para_o_preparo(self):
        inicial = self.base / "inicial.sh"
        inicial.write_text(": # arquivo que o bash leria antes da primeira linha\n", encoding="utf-8")
        r = self.rodar({"BASH_ENV": str(inicial)})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("BASH_ENV", r.stderr)
        self.assertNotIn("Raiz:", r.stdout)

    def test_shellopts_bashopts_e_ps4_param_o_preparo_antes_de_tudo(self):
        """1.7.11 (N2 da revisão do lote B): o bash importa SHELLOPTS, BASHOPTS e PS4 do ambiente; com xtrace, o PS4 roda
        código do usuário a cada linha do script, também depois do primeiro sudo. A guarda recusa as três. Pode nascer
        a marca do PS4 até a guarda (ainda não houve sudo); depois dela, nada: um preparo que seguisse traçaria
        centenas de linhas."""
        marca = self.base / "ps4-marca.txt"
        casos = {"SHELLOPTS": {"SHELLOPTS": "xtrace"}, "BASHOPTS": {"BASHOPTS": "extglob"},
                 "PS4": {"PS4": "+ "},
                 "SHELLOPTS com PS4 que roda comando": {"SHELLOPTS": "xtrace",
                                                        "PS4": f"$(/usr/bin/printf x >> '{marca}')"}}
        for nome, env in casos.items():
            with self.subTest(nome):
                r = self.rodar(env)
                self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("SHELLOPTS", r.stderr)
                self.assertNotIn("Raiz:", r.stdout)  # nada do preparo rodou
        self.assertLess(len(marca.read_text(encoding="ascii")) if marca.exists() else 0, 20)

    def test_o_sudo_pelo_caminho_absoluto(self):
        texto = self.preparar.read_text(encoding="utf-8")
        corpo = re.search(r"^como_root\(\) \{.*?^\}", texto, re.M | re.S).group(0)
        self.assertIn('/usr/bin/sudo "$@"', corpo)
        self.assertNotRegex(corpo, r'(?<![/\w])sudo "\$@"')
        linha = next(l for l in texto.splitlines() if '"${args[@]}"); r=$?' in l and "AJUDANTE" in l and "sudo" in l)
        self.assertIn('/usr/bin/sudo "$PY"', linha)


@unittest.skipUnless(POWERSHELL, "PowerShell do Windows indisponível")
class PerfilDoPowerShellNoWindows(unittest.TestCase):
    """Um perfil do PowerShell (que a sessão pode ter gravado) define funções com o nome dos cmdlets: o preparo usa os
    de verdade (nome qualificado) e os programas da pasta do sistema."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="seguranca-ci-f3-ps-1710-")).resolve()
        self.raiz = self.base / "Fundacao Teste"
        for pasta in ("registry", "projects/caso-real"):
            (self.raiz / pasta).mkdir(parents=True)
        self.skill = skill_de_ensaio(self.base)
        self.ps1 = self.skill / "assets" / "host" / "windows" / "preparar-maquina.ps1"
        self.marca = self.base / "interceptados.txt"

    def tearDown(self):
        subprocess.run(["icacls", str(self.base), "/reset", "/T", "/C", "/Q"], capture_output=True, timeout=120)
        shutil.rmtree(self.base, ignore_errors=True)

    def rodar_ps(self, codigo: str):
        arquivo = self.base / f"trecho-{len(list(self.base.glob('trecho-*')))}.ps1"
        arquivo.write_text("try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }\n" + codigo,
                           encoding="utf-8-sig")
        return subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                               str(arquivo)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=ENV, timeout=300)

    @unittest.skipIf(ELEVADO, "o script recusa rodar elevado (código 2), por desenho: este ensaio exige a conta comum")
    def test_simulacao_nao_chama_funcao_do_perfil_no_lugar_dos_cmdlets(self):
        """Contraprova (código de antes): as funções do "perfil" (definidas antes do script, como o $PROFILE as
        define) registram a chamada e repassam ao cmdlet; o preparo de antes as chamava (Add-Type, Resolve-Path,
        Get-Item, Get-AuthenticodeSignature, Get-Acl, ConvertFrom-Json...). A elevação (Start-Process) nunca repassa."""
        def hostil(nome: str) -> str:
            registro = f"[IO.File]::AppendAllText({ps_literal(self.marca)}, '{nome}' + [char]10)"
            if nome in ("Start-Process", "Get-Process"):
                return f"function global:{nome} {{ {registro}; throw 'interceptado: {nome}' }}"
            entrada = "$input | " if nome == "ConvertFrom-Json" else ""
            return f"function global:{nome} {{ {registro}; {entrada}{MODULO_DO_CMDLET[nome]}\\{nome} @args }}"
        hostis = "\n".join(map(hostil, SENSIVEIS))
        relatorio = self.base / "relatorio.json"
        args = " ".join(ps_literal(a) if not str(a).startswith("-") else str(a) for a in (
            "-Raiz", self.raiz, "-Titular", "titular", "-Chave", self.base / "ssh" / "fundacao_titular", "-Ancora",
            self.base / "ProgramData" / "FundacaoIA" / "confianca" / "allowed_signers", "-Ferramentas",
            self.base / "ProgramData" / "FundacaoIA" / "ferramentas", "-Python", sys.executable, "-SemBackups",
            "-Simular", "-Relatorio", relatorio))
        p = self.rodar_ps(hostis + "\n& " + ps_literal(self.ps1) + " " + args + "\nexit $LASTEXITCODE\n")
        interceptados = self.marca.read_text(encoding="utf-8").split() if self.marca.exists() else []
        self.assertEqual(interceptados, [], p.stdout + p.stderr)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_ssh_keygen_e_powershell_da_elevacao_pela_pasta_do_sistema(self):
        falso = self.base / "falso"
        (falso / "System32" / "OpenSSH").mkdir(parents=True)
        (falso / "System32" / "OpenSSH" / "ssh-keygen.exe").write_bytes(b"MZ")  # se escolhido, o perfil venceu
        p = self.rodar_ps(f". {ps_literal(self.ps1)}\n$antes = $env:SystemRoot\n$env:SystemRoot = {ps_literal(falso)}\n"
                          "$ssh = Get-SshKeygen\n$ps = Get-ProgramaDoSistema $POWERSHELL_DO_SISTEMA\n"
                          "$env:SystemRoot = $antes  # o ConvertTo-Json precisa do de verdade\n"
                          "@{ ssh = $ssh; ps = $ps } | ConvertTo-Json -Compress\n")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        dados = json.loads(p.stdout.strip().splitlines()[-1])
        sistema = pasta_do_sistema()
        self.assertEqual(dados["ssh"].casefold(), os.path.join(sistema, "OpenSSH", "ssh-keygen.exe").casefold())
        self.assertEqual(dados["ps"].casefold(),
                         os.path.join(sistema, "WindowsPowerShell", "v1.0", "powershell.exe").casefold())


class FontesDoPrepararWsl(unittest.TestCase):
    """O texto do preparar-wsl.sh (roda nos dois sistemas; o comportamento no bash é do Ubuntu): 1.7.11, N2 da revisão do
    lote B."""

    def setUp(self):
        self.texto = (SKILL / "assets" / "host" / "wsl" / "preparar-wsl.sh").read_text(encoding="utf-8")

    def test_a_guarda_recusa_shellopts_bashopts_e_ps4(self):
        linhas = self.texto.splitlines()
        inicio = next(i for i, l in enumerate(linhas) if l.startswith("case ") and "/usr/bin/env" in l)
        padrao = linhas[inicio + 1]
        for nome in ("BASH_FUNC_", "BASH_ENV=", "SHELLOPTS=", "BASHOPTS=", "PS4="):
            self.assertIn(nome, padrao, nome)
        fim = next(i for i in range(inicio, len(linhas)) if linhas[i] == "esac")
        self.assertTrue(any("kill -s KILL" in l for l in linhas[inicio:fim]))
        self.assertLess(inicio, next(i for i, l in enumerate(linhas) if l.startswith("PATH=/usr/sbin")))

    def test_a_recusa_de_dentro_de_projects_mostra_o_comando_com_env_i(self):
        mensagem = next(l for l in self.texto.splitlines() if "Rode o da skill instalada" in l)
        self.assertIn("/usr/bin/env -i", mensagem)
        self.assertIn("/usr/bin/bash --noprofile --norc /mnt/c/", mensagem)
        self.assertNotIn(": bash /mnt/c/", mensagem)

    def test_o_sudo_do_canario_pelo_caminho_absoluto(self):
        chamadas = [l for l in self.texto.splitlines() if "$AJUDANTE" in l and "sudo" in l and not l.lstrip().startswith("#")]
        # 1.7.11 (jaula L4, e673230): o `chama_jaula` do preparo da jaula é a terceira chamada; no ensaio ela roda o
        # ajudante como o seu usuário, e no real pelo sudo de caminho absoluto, como as outras duas.
        self.assertEqual(len(chamadas), 3, chamadas)
        for linha in chamadas:
            self.assertIn('/usr/bin/sudo "$PY" -I -B "$AJUDANTE"', linha)
            self.assertNotIn('=$(sudo ', linha)


class FontesDosScriptsDoWindows(unittest.TestCase):
    """O texto dos dois scripts (roda nos dois sistemas): cmdlets sensíveis pelo nome qualificado e a elevação pelo
    powershell.exe da pasta do sistema, sem o perfil (CI-F3)."""

    def test_elevacao_qualificada_com_o_powershell_do_sistema_e_sem_perfil(self):
        for script in ("preparar-maquina.ps1", "preparar-projeto.ps1"):
            linhas = linhas_de_codigo(SKILL / "assets" / "host" / "windows" / script)
            for nome in SENSIVEIS:
                with self.subTest(script=script, cmdlet=nome):
                    soltas = [l.strip() for l in linhas
                              if re.search(r"(?<![\w\\-])" + re.escape(nome) + r"\b", l) and "'" + nome not in l]
                    self.assertEqual(soltas, [], f"{nome} sem o nome qualificado em {script}")
            self.assertFalse([l for l in linhas if "$env:SystemRoot" in l and "Join-Path" in l], script)
        linhas = linhas_de_codigo(SKILL / "assets" / "host" / "windows" / "preparar-maquina.ps1")
        # 1.7.11 (cópia cifrada lote 4, 90c8685): a etapa da chave da cópia é a terceira elevação, com o seu relançamento
        # ($argumentosC). O padrão do relançamento pega qualquer nome $argumentos*, para nenhum escapar da conferência.
        elevacoes = [l for l in linhas if "Start-Process" in l]
        self.assertEqual(len(elevacoes), 3)
        for linha in elevacoes:
            self.assertIn("Microsoft.PowerShell.Management\\Start-Process -FilePath (Get-ProgramaDoSistema "
                          "$POWERSHELL_DO_SISTEMA)", linha)
        relancamentos = [l for l in linhas if re.search(r"\$argumentos\w* = @\(", l)]
        self.assertEqual(len(relancamentos), 3)
        for linha in relancamentos:
            self.assertIn("@('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath", linha)

    def test_o_passo_do_ubuntu_mostrado_roda_o_bash_sem_o_ambiente_do_terminal(self):
        texto = (SKILL / "assets" / "host" / "windows" / "preparar-projeto.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("$rel.proximo_passo = '/usr/bin/env -i HOME=\"$HOME\" PATH=/usr/bin:/bin /usr/bin/bash --noprofile "
                      "--norc \"' +", texto)


if __name__ == "__main__":
    unittest.main()
