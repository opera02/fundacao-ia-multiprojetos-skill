"""Cópia protegida da ferramenta do titular (1.7.10; folha da integração, I11; core/aberturas_comando do kit).

O kit mostra a assinatura da ficha pela cópia protegida em `/usr/local/lib/fundacao-ia/<v>/` (Ubuntu, root) e em
`C:\\ProgramData\\FundacaoIA\\ferramentas\\<v>\\` (Windows, ACL de administrador), com o `hashes.json` do esquema
`fundacao.ferramenta_titular/1` que a ferramenta confere antes de importar o kit. Aqui: o preparo do Ubuntu
(`instalar-projeto`) grava a do Ubuntu sem seguir ligação, pela cópia conferida, e ela passa no `conferir_copia` da
ferramenta real (no ensaio sem root, a base em pasta temporária e a conferência de dono root trocada); o
`preparar-maquina.ps1` só registra um Python instalado para todos os usuários (o desta máquina é por usuário: a forma
do Windows fica pendente, com o motivo, sem UAC), e a cópia do Windows sai do plano do ajudante (a mesma conta da do
Ubuntu), sem atravessar junção, conferida por esta conta. Pastas descartáveis; nada em /usr/local nem em C:\\ProgramData.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from apoio import ENV, KIT, SKILL, versao_do_kit
from test_host_projeto_apoio import LINUX, carregar_preparo
from test_host_projeto_area import _Base as _BaseArea, fotografia
from test_host_windows import ELEVADO, PS1, POWERSHELL, _Base as _BaseWindows

if str(KIT) not in sys.path:  # o kit da skill, como a ferramenta do titular o carrega
    sys.path.insert(0, str(KIT))
from fundacao.core import aberturas, aberturas_comando  # noqa: E402

FERRAMENTA = SKILL / "assets" / "host" / "fundacao_titular.py"


def sha(caminho) -> str:
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def ferramenta_real(base: Path):
    """A ferramenta do titular da skill (a real, não o substituto da cópia de ensaio), com a base da cópia protegida na
    pasta de ensaio: o conferir_copia dela é a prova de que a cópia gravada é a que ela aceita."""
    spec = importlib.util.spec_from_file_location("_titular_da_copia_de_ensaio", FERRAMENTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)  # só define funções: nada roda
    modulo.COPIA_PROTEGIDA = {"nt": str(base), "posix": str(base)}
    return modulo


def arquivos_do_kit(skill: Path) -> dict:
    kit = skill / "assets" / "fundacao-kit" / "fundacao"
    saida = {}
    for atual, pastas, arquivos in os.walk(kit):
        pastas[:] = [p for p in pastas if p not in ("__pycache__", ".pytest_cache", ".git")]
        for nome in arquivos:
            if not nome.endswith((".pyc", ".sqlite")):
                caminho = Path(atual) / nome
                saida["assets/fundacao-kit/fundacao/" + caminho.relative_to(kit).as_posix()] = sha(caminho)
    return saida


class ConstantesIguais(unittest.TestCase):
    """Os caminhos, o esquema e a forma do Python são os do kit e da ferramenta (uma definição em cada ponta, presas)."""

    def test_iguais_ao_kit_a_ferramenta_e_o_powershell(self):
        m = carregar_preparo()
        self.assertEqual(m.FERRAMENTA_BASE, aberturas.FERRAMENTA_POSIX)
        self.assertEqual(m.ESQUEMA_FERRAMENTA, aberturas.ESQUEMA_HASHES)
        self.assertEqual(m.REL_FERRAMENTA, "/".join(aberturas.REL_FERRAMENTA))
        self.assertEqual((m.PYTHON_WINDOWS.pattern, m.PYTHON_WINDOWS.flags),
                         (aberturas_comando._PYTHON_WINDOWS.pattern, aberturas_comando._PYTHON_WINDOWS.flags))
        titular = ferramenta_real(Path("/x"))
        self.assertEqual(titular.ESQUEMA_HASHES, m.ESQUEMA_FERRAMENTA)
        self.assertEqual(m.versao_do_kit(SKILL), versao_do_kit(KIT))
        texto = PS1.read_text(encoding="utf-8-sig")
        self.assertIn("$Ferramentas = (Join-Path $env:ProgramData 'FundacaoIA\\ferramentas')", texto)
        self.assertTrue(aberturas.FERRAMENTA_WINDOWS.endswith(r"\ProgramData\FundacaoIA\ferramentas"))
        self.assertIn(f"$ESQUEMA_FERRAMENTA = '{aberturas.ESQUEMA_HASHES}'", texto)
        self.assertIn(f"$REL_FERRAMENTA = '{m.REL_FERRAMENTA}'", texto)

    def test_plano_da_ferramenta_e_exatamente_a_arvore_que_a_ferramenta_confere(self):
        m = carregar_preparo()
        plano = m.plano_da_ferramenta(SKILL, "/usr/local/lib/fundacao-ia")
        esperado = {m.REL_FERRAMENTA: sha(FERRAMENTA), **arquivos_do_kit(SKILL)}
        self.assertEqual(plano["hashes"], {"schema_version": "fundacao.ferramenta_titular/1",
                                           "versao": versao_do_kit(KIT), "arquivos": esperado})
        self.assertEqual(plano["sha256"], hashlib.sha256(plano["hashes_bytes"]).hexdigest())
        self.assertEqual(json.loads(plano["hashes_bytes"].decode("utf-8")), plano["hashes"])
        self.assertEqual(Path(plano["destino"]).as_posix(), "/usr/local/lib/fundacao-ia/" + versao_do_kit(KIT))
        self.assertFalse([r for r in plano["manifesto"] if "__pycache__" in r or r.endswith(".pyc")])


class PlanoParaOWindows(unittest.TestCase):
    """`preparo_host.py plano-ferramenta [--python PY]`: o que o preparar-maquina.ps1 grava na cópia do Windows."""

    def rodar(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-I", "-B", str(SKILL / "assets" / "host" / "preparo_host.py"),
                               "plano-ferramenta", *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=ENV, timeout=120)

    def test_sem_python_o_plano_e_o_mesmo_da_copia_do_ubuntu(self):
        r = self.rodar()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        dados = json.loads(r.stdout)
        texto = dados["hashes_json"].encode("utf-8")
        self.assertEqual(dados["sha256"], hashlib.sha256(texto).hexdigest())
        plano = carregar_preparo().plano_da_ferramenta(SKILL, None)
        self.assertEqual(texto, plano["hashes_bytes"])
        self.assertEqual(dados["arquivos"], plano["hashes"]["arquivos"])
        self.assertNotIn("python", json.loads(texto))

    @unittest.skipUnless(os.name == "nt", "o Python fixado da cópia do Windows é um python.exe")
    def test_com_o_python_fixado_e_o_sha256_dele(self):
        python = os.path.realpath(sys.executable)
        r = self.rodar("--python", python)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        hashes = json.loads(json.loads(r.stdout)["hashes_json"])
        self.assertEqual(hashes["python"], {"caminho": python, "sha256": sha(python)})
        for ruim in ("python.exe", r"C:\Pasta;Outra\python.exe", r"C:\Python312\pythonw.exe"):
            with self.subTest(ruim=ruim):
                self.assertEqual(self.rodar("--python", ruim).returncode, 2)


@unittest.skipUnless(LINUX, "a cópia protegida do Ubuntu é gravada pelo instalar-projeto, só no Linux")
class CopiaDoUbuntu(_BaseArea):
    def setUp(self):
        super().setUp()
        self.ferramentas = self.base / "ferramentas"
        self.versao = versao_do_kit(self.skill / "assets" / "fundacao-kit")
        self.destino = self.ferramentas / self.versao

    def instalar_com(self, *extra, **kw):
        return self.instalar("--ferramenta-base", str(self.ferramentas), *extra, **kw)

    def acao(self, rel: dict) -> str:
        return next(a["acao"] for a in rel["acoes"] if a["item"] == "ferramenta-titular")

    def conferir_pela_ferramenta(self) -> dict:
        titular = ferramenta_real(self.ferramentas)
        with mock.patch.object(titular, "_problemas_de_dono_posix", return_value=[]):  # ensaio sem root
            return titular.conferir_copia(self.destino / "assets" / "host")

    def test_grava_a_copia_que_a_ferramenta_confere_e_e_idempotente(self):
        rel = self.instalar_com()
        self.assertEqual(self.acao(rel), "criar")
        self.assertEqual(rel["ferramenta_titular"]["caminho"], self.destino.as_posix())
        hashes = json.loads((self.destino / "hashes.json").read_text(encoding="utf-8"))
        esperado = {"assets/host/fundacao_titular.py": sha(self.skill / "assets" / "host" / "fundacao_titular.py"),
                    **arquivos_do_kit(self.skill)}
        self.assertEqual(hashes, {"schema_version": "fundacao.ferramenta_titular/1", "versao": self.versao,
                                  "arquivos": esperado})  # no Ubuntu, sem a chave python (o /usr/bin/python3)
        for rel_arquivo, valor in esperado.items():
            self.assertEqual(sha(self.destino.joinpath(*rel_arquivo.split("/"))), valor, rel_arquivo)
        self.assertEqual(os.listdir(self.destino / "assets" / "fundacao-kit"), ["fundacao"])
        for atual, pastas, arquivos in os.walk(self.ferramentas):
            self.assertEqual(stat.S_IMODE(os.lstat(atual).st_mode), 0o755, atual)
            for nome in arquivos:
                self.assertEqual(stat.S_IMODE(os.lstat(Path(atual) / nome).st_mode), 0o644, nome)
        self.assertEqual(self.conferir_pela_ferramenta(), {"protegida": True, "versao": self.versao,
                                                          "raiz": str(self.destino)})
        antes = fotografia(self.ferramentas)
        rel = self.instalar_com()
        self.assertEqual(self.acao(rel), "igual")
        self.assertEqual(fotografia(self.ferramentas), antes)
        self.assertEqual(sorted(os.listdir(self.ferramentas)), [self.versao])  # sem .novo-* nem .antigo-*

    def test_copia_alterada_volta_ao_plano_sem_seguir_ligacao(self):
        self.instalar_com()
        alvo = self.destino / "assets" / "fundacao-kit" / "fundacao" / "core" / "aberturas_regras.py"
        fora = self.base / "fora-da-copia.txt"
        fora.write_text("não pode mudar\n", encoding="utf-8")
        mudancas = {"arquivo trocado": lambda: alvo.write_bytes(alvo.read_bytes() + b"\n# alterado\n"),
                    "arquivo a mais": lambda: (alvo.parent / "extra.py").write_text("X = 1\n", encoding="utf-8"),
                    "ligação dentro": lambda: (alvo.parent / "ligado.py").symlink_to(fora),
                    "modo gravável": lambda: os.chmod(alvo, 0o666)}
        for nome, mudar in mudancas.items():
            with self.subTest(nome):
                mudar()
                rel = self.instalar_com()
                self.assertEqual(self.acao(rel), "atualizar", nome)
                self.assertEqual(self.conferir_pela_ferramenta()["protegida"], True)
                self.assertFalse((alvo.parent / "extra.py").exists() or (alvo.parent / "ligado.py").is_symlink())
                self.assertEqual(sorted(os.listdir(self.ferramentas)), [self.versao])
        self.assertEqual(fora.read_text(encoding="utf-8"), "não pode mudar\n")

    def test_simulacao_mostra_o_plano_sem_gravar(self):
        rel = self.instalar_com(simular=True)
        self.assertEqual(rel["ferramenta_titular"]["estado"], "criar")
        self.assertFalse(self.ferramentas.exists())

    def test_ensaio_sem_a_opcao_nao_grava_a_copia(self):
        rel = self.instalar()
        self.assertFalse([a for a in rel["acoes"] if a["item"] == "ferramenta-titular"])
        self.assertIsNone(rel["ferramenta_titular"]["caminho"])
        self.assertIn("--ferramenta-base", rel["ferramenta_titular"]["motivo"])
        self.assertFalse(self.ferramentas.exists())

    def test_ligacao_no_kit_da_skill_recusa_o_plano(self):
        ligacao = self.skill / "assets" / "fundacao-kit" / "fundacao" / "core" / "ligado.py"
        ligacao.symlink_to(self.base / "home")
        with self.assertRaises(self.m.EntradaInvalida):
            self.m.plano_da_ferramenta(self.skill, str(self.ferramentas))
        r = subprocess.run([sys.executable, "-I", "-B", str(self.skill / "assets" / "host" / "preparo_host.py"),
                            "instalar-projeto", "--raiz", str(self.raiz), "--projeto", "caso-real", "--titular",
                            "titular", "--claude", str(self.claude), "--claude-versao", "2.1.302", "--claude-sha256",
                            sha(self.claude), "--origem-hash", "ensaio", "--perfil-windows", "/mnt/c/Users/<usuario>",
                            "--casa", str(self.base / "home"), "--usuario", "ensaio", "--area-raiz",
                            str(self.base / "area"), "--bin", str(self.base / "bin"), "--ferramenta-base",
                            str(self.ferramentas)], capture_output=True, text=True, env=ENV, timeout=120)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertFalse(self.ferramentas.exists())


class OpcaoSoNoEnsaio(unittest.TestCase):
    def test_ferramenta_base_sem_area_de_ensaio_e_recusada(self):
        r = subprocess.run([sys.executable, "-I", "-B", str(SKILL / "assets" / "host" / "preparo_host.py"),
                            "instalar-projeto", "--raiz", "/x", "--projeto", "caso-real", "--titular", "titular",
                            "--claude", "/x/claude", "--claude-versao", "2.1.302", "--claude-sha256", "0" * 64,
                            "--origem-hash", "ensaio", "--perfil-windows", "/mnt/c/Users/<usuario>", "--casa", "/x",
                            "--usuario", "ensaio", "--ferramenta-base", "/tmp/ferramentas-ensaio"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, timeout=120)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("só para ensaio", r.stdout)


@unittest.skipIf(ELEVADO, "o script recusa rodar elevado (código 2), por desenho: este ensaio exige a conta comum")
class CopiaDoWindows(_BaseWindows):
    """PowerShell de verdade. O que exige administrador não roda aqui: a gravação (Install-CopiaFerramenta) é provada
    com -SemDono numa pasta de ensaio, como a ACL da âncora; a etapa elevada só recusa sem o UAC."""

    def ps_ensaio(self, codigo: str) -> dict:
        """Funções do script da cópia de ensaio da skill (o $SKILL dele é a cópia), carregado com ponto."""
        arq = self.base / f"trecho-ferramenta-{self.n}.ps1"
        self.n += 1
        prelude = "try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }"
        arq.write_text(prelude + chr(10) + f". '{self.ps1}'" + chr(10) + codigo + chr(10), encoding="utf-8-sig")
        p = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(arq)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, env=ENV)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return json.loads(p.stdout.strip().splitlines()[-1])

    def instalar_copia(self, base: Path, mexer: str = "") -> dict:
        """O plano do ajudante (com o Python que roda os testes registrado) e a gravação sem UAC, -SemDono."""
        py = os.path.realpath(sys.executable)
        return self.ps_ensaio(
            f"$r = Invoke-Ajudante '{py}' @('plano-ferramenta', '--python', '{py}')\n"
            "$plano = $r.Saida | ConvertFrom-Json\n"
            "$bytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes([string]$plano.hashes_json)\n"
            f"{mexer}\n"
            "$acoes = New-Object System.Collections.Generic.List[string]\n"
            f"$erro = $null; $destino = $null\n"
            f"try {{ $destino = Install-CopiaFerramenta $bytes '{base}' $acoes -SemDono }}\n"
            "catch { $erro = $_.Exception.Message }\n"
            "$estado = $null\n"
            "if ($destino) { $estado = Get-EstadoFerramenta $bytes $plano.arquivos $destino }\n"
            "@{ destino = $destino; erro = $erro; acoes = $acoes.ToArray(); igual = $(if ($estado) { $estado.igual }); "
            "protegida = $(if ($estado) { $estado.protegida }); versao = [string]$plano.versao } | "
            "ConvertTo-Json -Compress -Depth 5")

    def test_python_por_usuario_fica_pendente_sem_uac_e_sem_gravar(self):
        from test_host_windows import SENHA_DE_ENSAIO, gerar_chave
        gerar_chave(self.chave, SENHA_DE_ENSAIO)
        todos = self.ps(f"(Get-SondagemPython '{os.path.realpath(sys.executable)}') | ConvertTo-Json -Compress")["todos"]
        p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        item = self.item(rel, "ferramenta-titular")
        if todos:  # Python para todos os usuários (não é o desta máquina): espera o UAC, como a âncora
            self.assertEqual(item["acao"], "pendente_admin")
            self.assertTrue(any("cópia protegida" in x for x in rel["pendencias"]), rel["pendencias"])
        else:
            self.assertEqual(item["acao"], "pendente")
            self.assertFalse(item["python_todos"])
            for trecho in ("só para este usuário", "executar_ubuntu", "todos os usuários"):
                self.assertIn(trecho, item["detalhe"])
            self.assertTrue(any("forma do Windows" in x for x in rel["pendencias"]), rel["pendencias"])
        self.assertFalse(self.ferramentas.exists())
        p, rel = self.rodar("-Simular", "-Projeto", "caso-real")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.item(rel, "ferramenta-titular")["acao"], "criar" if todos else "pendente")
        self.assertFalse(self.ferramentas.exists())

    def test_sondagem_do_python_desta_conta(self):
        dados = self.ps(f"(Get-SondagemPython '{os.path.realpath(sys.executable)}') | ConvertTo-Json -Compress")
        if dados["todos"]:
            self.skipTest("o Python destes testes é instalado para todos os usuários")
        self.assertTrue(any("esta conta tem" in m for m in dados["motivos"]), dados)
        sistema = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "notepad.exe"
        if sistema.is_file():  # pasta do sistema: esta conta não altera nada ali
            self.assertTrue(self.ps(f"(Get-SondagemPython '{sistema}') | ConvertTo-Json -Compress")["todos"])

    def test_grava_pelo_plano_do_ajudante_e_a_ferramenta_aceita(self):
        base = self.base / "ProgramData" / "FundacaoIA" / "ferramentas"
        dados = self.instalar_copia(base)
        self.assertIsNone(dados["erro"], dados)
        destino = Path(dados["destino"])
        self.assertEqual(destino, base / dados["versao"])
        self.assertTrue(dados["igual"])
        self.assertFalse(dados["protegida"])  # sem UAC, o dono é esta conta (WRITE_DAC): só o administrador protege
        hashes = json.loads((destino / "hashes.json").read_text(encoding="utf-8"))
        self.assertEqual(hashes["python"]["caminho"], os.path.realpath(sys.executable))
        titular = ferramenta_real(base)
        with mock.patch.object(titular, "_direitos_concedidos_windows", return_value=[]):
            self.assertEqual(titular.conferir_copia(destino / "assets" / "host"),
                             {"protegida": True, "versao": dados["versao"], "raiz": str(destino)})
        self.assertEqual(sorted(p.name for p in base.iterdir()), [dados["versao"]])

    def test_arquivo_trocado_depois_do_plano_nao_instala_nada(self):
        base = self.base / "ProgramData" / "FundacaoIA" / "ferramentas"
        alvo = self.ps1.parents[2] / "fundacao-kit" / "fundacao" / "core" / "aberturas_regras.py"
        dados = self.instalar_copia(base, mexer=f"Add-Content -LiteralPath '{alvo}' -Value '# trocado depois do plano'")
        self.assertIn("mudou depois do plano", dados["erro"])
        self.assertIsNone(dados["destino"])
        self.assertEqual([p.name for p in base.iterdir()] if base.exists() else [], [])  # nem a pasta nova sobra

    def test_copia_anterior_com_juncao_sai_sem_atravessar(self):
        """Uma pasta da versão pré-criada por uma sessão (antes da ACL), com junção para fora: a troca a tira sem
        entrar na junção (o Remove-Item -Recurse do PowerShell 5.1 entraria)."""
        from apoio import criar_ligacao_dir
        base = self.base / "ProgramData" / "FundacaoIA" / "ferramentas"
        versao = versao_do_kit(self.ps1.parents[2] / "fundacao-kit")
        precioso = self.base / "Documentos do titular"
        precioso.mkdir()
        (precioso / "importante.txt").write_text("não pode sumir\n", encoding="utf-8")
        plantada = base / versao
        plantada.mkdir(parents=True)
        criar_ligacao_dir(plantada / "juncao", precioso)
        dados = self.instalar_copia(base)
        self.assertIsNone(dados["erro"], dados)
        self.assertTrue(dados["igual"])
        self.assertEqual((precioso / "importante.txt").read_text(encoding="utf-8"), "não pode sumir\n")
        self.assertFalse((Path(dados["destino"]) / "juncao").exists())

    def test_plano_fora_da_forma_e_recusado_sem_gravar(self):
        base = self.base / "ProgramData" / "FundacaoIA" / "ferramentas"
        trocas = {"caminho com ..": "$plano.hashes_json -replace 'assets/fundacao-kit/fundacao/__init__.py', "
                                    "'assets/fundacao-kit/fundacao/../../fora.py'",
                  "outro esquema": "$plano.hashes_json -replace 'fundacao.ferramenta_titular/1', 'outro/1'",
                  "python trocado": "$plano.hashes_json -replace '\"sha256\": \"[0-9a-f]{64}\"\\s*}', "
                                    "'\"sha256\": \"" + "0" * 64 + "\" }'"}
        for nome, troca in trocas.items():
            with self.subTest(nome):
                dados = self.instalar_copia(base, mexer="$bytes = (New-Object System.Text.UTF8Encoding($false))."
                                                        f"GetBytes([string]({troca}))")
                self.assertTrue(dados["erro"], (nome, dados))
                self.assertIsNone(dados["destino"])
                self.assertFalse(base.exists() and [p for p in base.iterdir()], nome)

    def test_etapa_da_ferramenta_recusa_sem_administrador(self):
        plano = self.base / "plano.json"
        plano.write_text("{}", encoding="utf-8")
        p = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                            str(self.ps1), "-EtapaFerramenta", "-Ferramentas", str(self.ferramentas),
                            "-PlanoFerramenta", str(plano), "-FerramentaEsperada", sha(plano)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, timeout=300)
        self.assertEqual(p.returncode, 4, p.stdout + p.stderr)
        self.assertFalse(self.ferramentas.exists())


if __name__ == "__main__":
    unittest.main()
