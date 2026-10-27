"""Perfis do host gerados pelos modelos da skill (`assets/host/preparo_host.py`).

Na implantação real de 2026-10-20 o perfil do WSL levou três versões: a v1 deixou `state/` como tmpfs
vazio dentro do sandbox (a regra `Read(./state/**)` vira `denyRead`), a v2 só religou a leitura e a v3
religou leitura e escrita. Hooks e perfis foram copiados à mão. Estes testes fixam o que a v3 provou e
exigem que os perfis saiam dos modelos com os caminhos da máquina, sem marcador sobrando.

Só biblioteca padrão; pastas descartáveis; nenhum arquivo do host é lido ou alterado.
"""

from __future__ import annotations

import importlib.util
import json
import ntpath
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import ENV, SKILL

HOST = SKILL / "assets" / "host"
AJUDANTE = HOST / "preparo_host.py"


def carregar():
    sys.dont_write_bytecode = True  # sem __pycache__ em assets/host/ (o CEN-11 acusa)
    spec = importlib.util.spec_from_file_location("preparo_host", AJUDANTE)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def rodar(*args, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(AJUDANTE), *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=ENV, timeout=120, cwd=str(cwd) if cwd else None)


NEGACOES_DA_RAIZ = ["Read(./.env)", "Read(./.env.*)", "Read(./**/.env)", "Read(./**/.env.*)", "Read(./secrets/**)",
                    "Read(./**/secrets/**)", "Read(./**/*.pem)", "Read(./**/*.key)", "Read(./**/*.pfx)",
                    "Read(./**/*.p12)", "Read(./**/id_rsa*)", "Read(./**/*credentials*)", "Read(./**/*secret*)",
                    "Read(./**/*.kdbx)", "Read(./**/auth.json)", "Read(./state/**)"]


def hook(comando: str, script: str, nome: str, matcher: str, mensagem: str) -> dict:
    return {"matcher": matcher, "hooks": [{"type": "command", "command": comando, "args": ["-B", script], "timeout": 10,
                                           "onFailure": "block", "statusMessage": f"{nome}: {mensagem}"}]}


def ganchos(comando: str, pasta: str, sep: str) -> dict:
    return {"SessionStart": [{"matcher": "compact", "hooks": [{
        "type": "command", "command": comando, "args": ["-I", "-B", pasta + sep + "sinais_sessao.py"],
        "timeout": 3, "onFailure": "block", "statusMessage": "sinais_sessao: lembrando a retomada após compactação"}]}],
        "PreToolUse": [
        hook(comando, pasta + sep + "guarda_caminho.py", "guarda_caminho", "Edit|Write|MultiEdit|NotebookEdit|mcp__.*",
             "conferindo destino da escrita"),
        hook(comando, pasta + sep + "guarda_identidade.py", "guarda_identidade", "Bash|PowerShell",
             "conferindo troca de identidade")]}


class CaminhosWsl(unittest.TestCase):
    def setUp(self):
        self.m = carregar()

    def test_unidade_do_windows_vira_montagem_do_wsl(self):
        self.assertEqual(self.m.caminho_wsl(r"E:\Fundacao Exemplo"), "/mnt/e/Fundacao Exemplo")
        self.assertEqual(self.m.caminho_wsl("D:/Origem Ç/"), "/mnt/d/Origem Ç")
        self.assertEqual(self.m.caminho_wsl("C:\\"), "/mnt/c")
        self.assertEqual(self.m.caminho_wsl(r"E:\x", montagem="/windir/"), "/windir/e/x")

    def test_caminho_do_linux_fica_como_esta(self):
        self.assertEqual(self.m.caminho_wsl("/mnt/e/Fundacao Exemplo/"), "/mnt/e/Fundacao Exemplo")

    def test_relativo_e_unc_sao_recusados(self):
        for ruim in ("projeto", r"..\x", r"\servidor\pasta", ""):
            with self.subTest(ruim=ruim), self.assertRaises(ValueError):
                self.m.caminho_wsl(ruim)


class PerfilWindows(unittest.TestCase):
    def test_hooks_da_raiz_com_o_python_informado(self):
        m = carregar()
        perfil = m.perfil_windows(raiz=r"E:\Fundacao Exemplo", python=r"C:\Py\python.exe")
        esperado = {
            "permissions": {"deny": NEGACOES_DA_RAIZ + ["Read(~/.claude/.credentials.json)", "Read(~/.codex/auth.json)",
                                                        "Read(~/.ssh/**)", "Edit(./.claude/**)"]},
            "claudeMdExcludes": ["**/projects/*/data/**"],  # 1.7.0: pasta de dados não vira instrução
            "env": {"FUNDACAO_MCP_PERMITIDAS": "mcp__ccd_*"},
            "hooks": ganchos(r"C:\Py\python.exe", r"E:\Fundacao Exemplo\.claude\hooks", "\\"),
            "statusLine": {"type": "command", "command": m.comando_status_windows(
                r"C:\Py\python.exe", r"E:\Fundacao Exemplo\.claude\hooks\sinais_sessao.py")},
        }
        self.assertEqual(perfil, esperado)
        self.assertNotIn("{{", m.texto_json(perfil))
        self.assertEqual(m.perfil_windows(raiz="E:/Fundacao Exemplo/", python="C:/Py/python.exe"), esperado)


class PerfilWsl(unittest.TestCase):
    """O perfil do WSL sai do modelo igual ao v3 provado no caso real, com os caminhos desta máquina."""

    def setUp(self):
        self.m = carregar()
        self.kw = dict(raiz=r"E:\Fundacao Exemplo", projeto="caso-real", perfil_windows=r"C:\Perfis\titular.PC-EXEMPLO",
                       outros_projetos=["lab-b", "lab-a", "lab-c"], backups=[r"D:\Backups-Exemplo"],
                       somente_leitura=[r"D:\Origem Ç"])

    def test_reproduz_o_perfil_v3_do_caso_real(self):
        raiz, perfil_win = "/mnt/e/Fundacao Exemplo", "/mnt/c/Perfis/titular.PC-EXEMPLO"
        esperado = {
            "permissions": {"deny": NEGACOES_DA_RAIZ + [
                "Read(~/.claude/.credentials.json)", "Read(~/.codex/auth.json)", "Read(~/.ssh/**)",
                f"Read(/{perfil_win}/.claude/.credentials.json)", f"Read(/{perfil_win}/.codex/auth.json)",
                f"Read(/{perfil_win}/.ssh/**)", "WebFetch", "WebSearch",  # 1.7.0: sem saída pela web
                "Edit(./.claude/**)", "Edit(//mnt/c/ProgramData/FundacaoIA/**)", "Edit(//mnt/d/Origem Ç/**)"]},
            "claudeMdExcludes": ["**/projects/*/data/**"],
            "env": {"FUNDACAO_MCP_PERMITIDAS": "", "DISABLE_AUTOUPDATER": "1"},
            "hooks": ganchos("/usr/bin/python3", raiz + "/.claude/hooks", "/"),
            "statusLine": {"type": "command", "command": "/usr/bin/python3 -I -B '" + raiz
                           + "/.claude/hooks/sinais_sessao.py' --status-line"},
            "sandbox": {
                "enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False,
                "filesystem": {
                    "allowWrite": ["/mnt/d/Backups-Exemplo", raiz + "/state"],
                    "denyWrite": [raiz + "/.claude", raiz + "/projects/lab-a", raiz + "/projects/lab-b",
                                  raiz + "/projects/lab-c", "/mnt/d/Origem Ç", "/mnt/c/ProgramData/FundacaoIA"],
                    "denyRead": ["~/.ssh", "~/.claude/.credentials.json", "~/.codex", perfil_win + "/.ssh",
                                 perfil_win + "/.claude/.credentials.json", perfil_win + "/.codex"],
                    "allowRead": [raiz + "/state"]},
                "network": {"allowedDomains": []}},
        }
        self.assertEqual(self.m.perfil_wsl(**self.kw), esperado)

    def test_state_legivel_e_gravavel_no_sandbox_e_negado_ao_read(self):
        perfil = self.m.perfil_wsl(**self.kw)
        fs = perfil["sandbox"]["filesystem"]
        self.assertIn("/mnt/e/Fundacao Exemplo/state", fs["allowRead"])   # v1: tmpfs vazio sem isto
        self.assertIn("/mnt/e/Fundacao Exemplo/state", fs["allowWrite"])  # v2: só leitura sem isto
        self.assertIn("Read(./state/**)", perfil["permissions"]["deny"])  # a ferramenta Read continua negada
        self.assertEqual(self.m.conferir_perfil_wsl(perfil, "/mnt/e/Fundacao Exemplo"), [])

    def test_sem_backups_nem_somente_leitura_nao_sobra_marcador(self):
        kw = {**self.kw, "backups": [], "somente_leitura": [], "outros_projetos": []}
        perfil = self.m.perfil_wsl(**kw)
        texto = self.m.texto_json(perfil)
        self.assertNotIn("{{", texto)
        self.assertEqual(perfil["sandbox"]["filesystem"]["allowWrite"], ["/mnt/e/Fundacao Exemplo/state"])
        self.assertNotIn("Edit(//mnt/d/Origem Ç/**)", perfil["permissions"]["deny"])

    def test_projeto_da_sessao_nao_pode_estar_entre_os_negados(self):
        with self.assertRaises(ValueError):
            self.m.perfil_wsl(**{**self.kw, "outros_projetos": ["caso-real", "lab-a"]})
        with self.assertRaises(ValueError):
            self.m.perfil_wsl(**{**self.kw, "projeto": "../fora"})

    def test_marcador_sem_valor_ou_com_digitos_nao_passa_em_silencio(self):
        with self.assertRaises(ValueError):
            self.m.renderizar({"a": ["{{DESCONHECIDO}}/x"]}, {"RAIZ": "/r"})
        with self.assertRaises(ValueError):
            self.m.renderizar({"a": "{{ raiz }}"}, {"RAIZ": "/r"})
        self.assertEqual(self.m.renderizar({"a": "{{SHA256}}"}, {"SHA256": "x"}), {"a": "x"})

    def test_conferencia_acusa_os_perfis_v1_e_v2(self):
        v3 = self.m.perfil_wsl(**self.kw)
        v2 = json.loads(json.dumps(v3))
        v2["sandbox"]["filesystem"]["allowWrite"].remove("/mnt/e/Fundacao Exemplo/state")
        v1 = json.loads(json.dumps(v2))
        del v1["sandbox"]["filesystem"]["allowRead"]
        self.assertTrue(any("escrita" in p for p in self.m.conferir_perfil_wsl(v2, "/mnt/e/Fundacao Exemplo")))
        self.assertTrue(any("leitura" in p for p in self.m.conferir_perfil_wsl(v1, "/mnt/e/Fundacao Exemplo")))


class PerfilWslConferidoPeloModelo(unittest.TestCase):
    """Auditoria Codex Security da 1.7.6, #5: a conferência olhava só alguns indicadores do perfil (a rede, as
    negações de credenciais e dos outros projetos, o matcher, o comando e a falha fechada dos hooks e as chaves
    desconhecidas passavam), e o preparo do WSL fixava o hash do que passasse. Agora o perfil só passa igual ao que o
    modelo gera com os caminhos dele e os projetos da raiz."""

    RAIZ = "/mnt/e/Fundacao Exemplo"

    def setUp(self):
        self.m = carregar()
        self.perfil = self.m.perfil_wsl(raiz=r"E:\Fundacao Exemplo", projeto="caso-real",
                                        perfil_windows=r"C:\Perfis\titular.PC-EXEMPLO",
                                        outros_projetos=["lab-a", "lab-b"], backups=[r"D:\Backups-Exemplo"],
                                        somente_leitura=[r"D:\Origem Ç"], negar=["squad-peticoes"])

    def conferir(self, perfil, outros=("lab-a", "lab-b"), projeto="caso-real"):
        return self.m.conferir_perfil_wsl(perfil, self.RAIZ, projeto=projeto, outros_projetos=list(outros))

    def alterado(self, mudanca) -> dict:
        perfil = json.loads(json.dumps(self.perfil))
        mudanca(perfil)
        return perfil

    def test_perfil_gerado_pelo_modelo_passa(self):
        self.assertEqual(self.conferir(self.perfil), [])
        self.assertEqual(self.m.conferir_perfil_wsl(self.perfil, self.RAIZ), [])

    def test_enfraquecimentos_sao_acusados(self):
        def fs(p):
            return p["sandbox"]["filesystem"]

        def gancho(p, i):
            return p["hooks"]["PreToolUse"][i]["hooks"][0]

        casos = {
            "rede liberada": lambda p: p["sandbox"]["network"]["allowedDomains"].append("exemplo.invalid"),
            "credencial do Linux legível no sandbox": lambda p: fs(p)["denyRead"].remove("~/.ssh"),
            "credencial do Windows legível no sandbox":
                lambda p: fs(p)["denyRead"].remove("/mnt/c/Perfis/titular.PC-EXEMPLO/.codex"),
            "Read de credencial liberado": lambda p: p["permissions"]["deny"].remove("Read(~/.ssh/**)"),
            "outro projeto gravável": lambda p: fs(p)["denyWrite"].remove(self.RAIZ + "/projects/lab-a"),
            "pasta da âncora gravável": lambda p: fs(p)["denyWrite"].remove("/mnt/c/ProgramData/FundacaoIA"),
            "matcher trocado": lambda p: p["hooks"]["PreToolUse"][0].update(matcher="Write"),
            "falha aberta": lambda p: gancho(p, 1).update(onFailure="allow"),
            "comando do hook trocado": lambda p: gancho(p, 0).update(command="/bin/true"),
            "tempo do hook trocado": lambda p: gancho(p, 0).update(timeout=1),
            "hook a mais": lambda p: p["hooks"]["PreToolUse"].append(
                {"matcher": "Read", "hooks": [{"type": "command", "command": "/tmp/x"}]}),
            "permissão a mais": lambda p: p["permissions"].update(allow=["Bash(curl:*)"]),
            "chave desconhecida": lambda p: p.update(statusLine={"type": "command", "command": "/tmp/x"}),
            "troca de identidade liberada": lambda p: p["env"].update(FUNDACAO_PERMITIR_TROCA_IDENTIDADE="1"),
            "verdadeiro como número": lambda p: p["sandbox"].update(allowUnsandboxedCommands=0),
        }
        for nome, mudanca in casos.items():
            with self.subTest(nome):
                self.assertTrue(self.conferir(self.alterado(mudanca)))
                if nome != "outro projeto gravável":  # sem a lista de projetos da raiz, só a estrutura é conferida
                    self.assertTrue(self.m.conferir_perfil_wsl(self.alterado(mudanca), self.RAIZ))

    def test_projeto_criado_depois_do_preparo_do_windows_e_acusado(self):
        problemas = self.conferir(self.perfil, outros=("lab-a", "lab-b", "lab-novo"))
        self.assertTrue(any("lab-novo" in p for p in problemas), problemas)
        self.assertEqual(self.conferir(self.perfil, outros=("lab-a",)), [])  # negar projeto que saiu não libera nada

    def test_perfil_de_outro_projeto_e_acusado(self):
        problemas = self.conferir(self.perfil, outros=("caso-real", "lab-b"), projeto="lab-a")
        self.assertTrue(any("lab-a" in p for p in problemas), problemas)       # o da sessão está negado
        self.assertTrue(any("caso-real" in p for p in problemas), problemas)   # e o outro ficou gravável

    def test_linha_de_comando_confere_com_os_projetos_da_raiz(self):
        base = Path(tempfile.mkdtemp(prefix="perfil-wsl-conferido-teste-"))
        try:
            raiz = base / "Fundacao Exemplo"
            for nome in ("caso-real", "lab-a"):
                (raiz / "projects" / nome).mkdir(parents=True)
            perfil = base / "settings.wsl.json"
            r = rodar("perfil-wsl", "--raiz", raiz, "--projeto", "caso-real", "--perfil-windows", r"C:\Perfis\titular",
                      "--saida", perfil)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = rodar("conferir-perfil-wsl", "--perfil", perfil, "--raiz", raiz, "--projeto", "caso-real")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            (raiz / "projects" / "lab-novo").mkdir()
            r = rodar("conferir-perfil-wsl", "--perfil", perfil, "--raiz", raiz, "--projeto", "caso-real")
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("lab-novo", r.stdout)
        finally:
            shutil.rmtree(base, ignore_errors=True)


class IdentidadeDaSessaoDeDadosReais(unittest.TestCase):
    """Auditoria Codex Security da 1.7.6, #5: a sessão de dados reais carrega o settings.local.json
    (--setting-sources local), e o preparo só conferia que ele existia: um hook, uma permissão, um plugin, uma
    variável como FUNDACAO_PERMITIR_TROCA_IDENTIDADE ou outra identidade passavam. Agora ele só serve com a identidade
    do titular (e o projeto da sessão), e o preparo do Windows com -Projeto grava só isso."""

    OK = {"env": {"FUNDACAO_PRINCIPAL": "titular", "FUNDACAO_PROJECT": "caso-real"}}

    def setUp(self):
        self.m = carregar()

    def test_so_a_identidade_do_titular_passa(self):
        self.assertEqual(self.m.conferir_identidade(self.OK, "titular", "caso-real"), [])
        self.assertEqual(self.m.conferir_identidade({"env": {"FUNDACAO_PRINCIPAL": "titular"}}, "titular", "caso-real"),
                         [])
        casos = {
            "outra identidade": {"env": {"FUNDACAO_PRINCIPAL": "outra-pessoa"}},
            "outro projeto": {"env": {"FUNDACAO_PRINCIPAL": "titular", "FUNDACAO_PROJECT": "lab-a"}},
            "troca de identidade liberada": {"env": {"FUNDACAO_PRINCIPAL": "titular",
                                                     "FUNDACAO_PERMITIR_TROCA_IDENTIDADE": "1"}},
            "hook": {**self.OK, "hooks": {"PreToolUse": []}},
            "permissão": {**self.OK, "permissions": {"allow": ["Bash(curl:*)"]}},
            "plugin": {**self.OK, "enabledPlugins": {"exemplo@exemplo": True}},
            "sandbox": {**self.OK, "sandbox": {"network": {"allowedDomains": ["exemplo.invalid"]}}},
            "sem identidade": {"env": {}},
            "env que não é objeto": {"env": ["FUNDACAO_PRINCIPAL"]},
            "não é objeto": ["env"],
        }
        for nome, dados in casos.items():
            with self.subTest(nome):
                self.assertTrue(self.m.conferir_identidade(dados, "titular", "caso-real"))

    def test_estrito_deixa_so_a_identidade_e_mantem_o_conflito(self):
        atual = {"permissions": {"allow": ["Bash(curl:*)"]}, "env": {"OUTRA": "1", "FUNDACAO_PRINCIPAL": "titular"}}
        self.assertEqual(self.m.identidade("titular", atual, "caso-real", estrito=True), self.OK)
        with self.assertRaises(self.m.Conflito):
            self.m.identidade("titular", {"env": {"FUNDACAO_PRINCIPAL": "outra-pessoa"}}, "caso-real", estrito=True)

    def test_linha_de_comando_confere_sem_mostrar_valores(self):
        base = Path(tempfile.mkdtemp(prefix="identidade-conferida-teste-"))
        try:
            local = base / "settings.local.json"
            local.write_text(json.dumps(self.OK), encoding="utf-8")
            r = rodar("conferir-identidade", "--arquivo", local, "--titular", "titular", "--projeto", "caso-real")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            local.write_text(json.dumps({"env": {**self.OK["env"], "OUTRA_CHAVE": "valor-que-nao-aparece"}}),
                             encoding="utf-8")
            r = rodar("conferir-identidade", "--arquivo", local, "--titular", "titular", "--projeto", "caso-real")
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("OUTRA_CHAVE", r.stdout)
            self.assertNotIn("valor-que-nao-aparece", r.stdout)
            r = rodar("identidade", "--titular", "titular", "--projeto", "caso-real", "--atual", local, "--estrito")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(json.loads(r.stdout), self.OK)
        finally:
            shutil.rmtree(base, ignore_errors=True)


class Identidade(unittest.TestCase):
    def test_settings_local_entrega_a_identidade_do_titular(self):
        m = carregar()
        self.assertEqual(m.identidade("titular"), {"env": {"FUNDACAO_PRINCIPAL": "titular"}})
        for ruim in ("", "Titular Silva", "a" * 70, "../x"):
            with self.subTest(ruim=ruim), self.assertRaises(ValueError):
                m.identidade(ruim)


class IdentidadeMesclada(unittest.TestCase):
    """O `settings.local.json` existente só ganha a identidade; outra identidade já gravada é conflito."""

    def test_acrescenta_so_a_identidade(self):
        m = carregar()
        atual = {"sandbox": {"enabled": True}, "env": {"OUTRA": "1"}}
        self.assertEqual(m.identidade("titular", atual),
                         {"sandbox": {"enabled": True}, "env": {"OUTRA": "1", "FUNDACAO_PRINCIPAL": "titular"}})
        self.assertEqual(atual, {"sandbox": {"enabled": True}, "env": {"OUTRA": "1"}})  # não altera a entrada

    def test_mesma_identidade_fica_igual_e_outra_e_conflito(self):
        m = carregar()
        atual = {"env": {"FUNDACAO_PRINCIPAL": "titular"}}
        self.assertEqual(m.identidade("titular", atual), atual)
        with self.assertRaises(m.Conflito):
            m.identidade("titular", {"env": {"FUNDACAO_PRINCIPAL": "outra-pessoa"}})

    def test_linha_de_comando_mescla_e_acusa_conflito(self):
        base = Path(tempfile.mkdtemp(prefix="identidade-teste-"))
        try:
            atual = base / "settings.local.json"
            atual.write_text('{"sandbox": {"enabled": true}}', encoding="utf-8")
            r = rodar("identidade", "--titular", "titular", "--atual", atual)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(json.loads(r.stdout)["env"], {"FUNDACAO_PRINCIPAL": "titular"})
            atual.write_text('{"env": {"FUNDACAO_PRINCIPAL": "outra-pessoa"}}', encoding="utf-8")
            r = rodar("identidade", "--titular", "titular", "--atual", atual)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("outra-pessoa", r.stdout)
        finally:
            shutil.rmtree(base, ignore_errors=True)


class LinhaDeComando(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="host-perfis-teste-"))
        self.raiz = self.base / "Fundacao Exemplo"
        for nome in ("caso-real", "lab-a", "lab-b", ".oculta"):
            (self.raiz / "projects" / nome).mkdir(parents=True)
        (self.raiz / "projects" / "lab-a" / "sub").mkdir()
        (self.raiz / "projects" / "nao-e-pasta.txt").write_text("x", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_projetos_da_raiz_lista_so_o_primeiro_nivel(self):
        self.assertEqual(carregar().projetos_da_raiz(self.raiz), ["caso-real", "lab-a", "lab-b"])

    def test_perfil_wsl_grava_json_deterministico(self):
        saidas = []
        for n in (1, 2):
            destino = self.base / f"perfil-{n}.json"
            r = rodar("perfil-wsl", "--raiz", self.raiz, "--projeto", "caso-real", "--perfil-windows",
                      r"C:\Perfis\titular.PC-EXEMPLO", "--backups", r"D:\Backups-Exemplo", "--saida", destino)
            self.assertEqual(r.returncode, 0, r.stderr)
            saidas.append(destino.read_bytes())
        self.assertEqual(saidas[0], saidas[1])
        self.assertTrue(saidas[0].endswith(b"\n"))
        perfil = json.loads(saidas[0].decode("utf-8"))
        negados = perfil["sandbox"]["filesystem"]["denyWrite"]
        raiz = carregar().caminho_wsl(str(self.raiz))
        self.assertIn(raiz + "/projects/lab-a", negados)
        self.assertIn(raiz + "/projects/lab-b", negados)
        self.assertNotIn(raiz + "/projects/caso-real", negados)

    def test_perfil_wsl_recusa_projeto_ausente_sem_gravar(self):
        destino = self.base / "perfil.json"
        r = rodar("perfil-wsl", "--raiz", self.raiz, "--projeto", "nao-existe", "--perfil-windows", r"C:\Perfis\x",
                  "--saida", destino)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("nao-existe", r.stdout + r.stderr)  # recusa do ajudante, não do Python sem o arquivo
        self.assertFalse(destino.exists())

    def test_perfil_windows_e_identidade_pela_linha_de_comando(self):
        r = rodar("perfil-windows", "--raiz", self.raiz, "--python", sys.executable)
        self.assertEqual(r.returncode, 0, r.stderr)
        perfil = json.loads(r.stdout)
        # O perfil é das sessões do Windows: o caminho sai com as barras do Windows (num Linux, \usr\bin...).
        self.assertEqual(perfil["hooks"]["PreToolUse"][0]["hooks"][0]["command"], ntpath.normpath(sys.executable))
        r = rodar("identidade", "--titular", "titular")
        self.assertEqual(json.loads(r.stdout)["env"], {"FUNDACAO_PRINCIPAL": "titular"})


BLOCO = "[interop]\nenabled=false\nappendWindowsPath=false\n"


class WslConf(unittest.TestCase):
    """`/etc/wsl.conf` com um único bloco [interop] desligado; no caso real o bloco foi repetido três vezes."""

    def setUp(self):
        self.ajustar = carregar().ajustar_wsl_conf

    def secoes(self, texto: str) -> list[str]:
        return [linha.strip().lower() for linha in texto.splitlines() if linha.strip().startswith("[")]

    def test_arquivo_vazio_ganha_o_bloco(self):
        texto, mudou = self.ajustar("")
        self.assertTrue(mudou)
        self.assertEqual(texto, BLOCO)

    def test_tres_blocos_repetidos_viram_um(self):
        texto, mudou = self.ajustar("[boot]\nsystemd=true\n\n" + ("\n" + BLOCO) * 3)
        self.assertTrue(mudou)
        self.assertEqual(self.secoes(texto), ["[boot]", "[interop]"])
        self.assertEqual(texto.lower().count("enabled=false"), 1)
        self.assertIn("systemd=true", texto)

    def test_liga_desligado_e_preserva_o_resto(self):
        original = "# meu comentário\n[user]\ndefault=titular\n\n[interop]\n# nota\nEnabled = true\n"
        texto, mudou = self.ajustar(original)
        self.assertTrue(mudou)
        self.assertIn("# meu comentário", texto)
        self.assertIn("# nota", texto)
        self.assertIn("default=titular", texto)
        self.assertNotIn("true", texto.split("[interop]", 1)[1].lower())
        self.assertEqual(self.secoes(texto), ["[user]", "[interop]"])

    def test_ja_correto_nao_muda(self):
        texto, mudou = self.ajustar("[boot]\nsystemd=true\n\n" + BLOCO)
        self.assertFalse(mudou)
        segundo, mudou2 = self.ajustar(texto)
        self.assertEqual((segundo, mudou2), (texto, False))

    def test_linha_de_comando_so_le_o_arquivo(self):
        base = Path(tempfile.mkdtemp(prefix="wsl-conf-teste-"))
        try:
            arq = base / "wsl.conf"
            arq.write_text(BLOCO * 2, encoding="utf-8")
            antes = arq.read_bytes()
            r = rodar("wsl-conf", "--arquivo", arq)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(json.loads(r.stdout)["mudou"])
            self.assertEqual(arq.read_bytes(), antes)
        finally:
            shutil.rmtree(base, ignore_errors=True)


H1, H2, H3, H4, H5 = "1" * 64, "2" * 64, "3" * 64, "4" * 64, "5" * 64


def raiz_preparada(base: Path) -> Path:
    """Raiz como o preparo do Windows a deixa: hooks da skill, perfil do WSL do modelo e só a identidade."""
    m = carregar()
    raiz = base / "raiz"
    (raiz / "projects" / "caso-real").mkdir(parents=True)
    (raiz / ".claude" / "hooks").mkdir(parents=True)
    for nome in ("guarda_caminho.py", "guarda_identidade.py", "sinais_sessao.py"):
        shutil.copyfile(SKILL / "assets" / "hooks" / nome, raiz / ".claude" / "hooks" / nome)
    perfil = m.perfil_wsl(raiz=m.caminho_wsl(str(raiz)), projeto="caso-real", perfil_windows="/mnt/c/Perfis/titular",
                          outros_projetos=[])
    (raiz / ".claude" / "settings.wsl.json").write_text(m.texto_json(perfil), encoding="utf-8", newline="\n")
    (raiz / ".claude" / "settings.local.json").write_text(m.texto_json(m.identidade("titular", projeto="caso-real")),
                                                          encoding="utf-8", newline="\n")
    return raiz


class Lancador(unittest.TestCase):
    """O lançador da sessão de dados reais sai do modelo com os hashes fixados e aspas seguras para o bash."""

    def valores(self, **extra) -> dict:
        return {"RAIZ": "/mnt/e/Raiz de Ensaio ç", "PROJETO": "caso-real",
                "CLAUDE_BIN": "/home/titular/.local/share/fundacao-ia/claude/2.1.302/claude",
                "CLAUDE_VERSAO": "2.1.302", "CLAUDE_SHA256": H1, "CLAUDE_ORIGEM_HASH": "manifesto assinado",
                "PERFIL_SHA256": H2, "HOOK_CAMINHO_SHA256": H3, "HOOK_IDENTIDADE_SHA256": H4,
                "HOOK_SINAIS_SHA256": "6" * 64,
                "TITULAR": "titular", "LOCAL_SHA256": H5,
                "SKILL_MD": "/mnt/c/Perfis/titular/.claude/skills/fundacao-ia-multiprojetos/SKILL.md", **extra}

    def lancar(self, raiz: Path, saida: Path, titular: str = "titular") -> subprocess.CompletedProcess:
        return rodar("lancador", "--raiz", raiz, "--projeto", "caso-real", "--titular", titular, "--claude",
                     "/opt/claude/claude", "--claude-versao", "2.1.302", "--claude-sha256", H1, "--origem-hash",
                     "informado", "--skill-md", "/opt/skill/SKILL.md", "--saida", saida)

    def test_sem_marcadores_e_com_os_valores_fixados(self):
        texto = carregar().lancador(self.valores())
        self.assertNotIn("{{", texto)
        for valor in (H1, H2, H3, H4, "2.1.302", "caso-real", "'/mnt/e/Raiz de Ensaio ç'"):
            self.assertIn(valor, texto)
        self.assertTrue(texto.startswith("#!/usr/bin/env bash\n"))
        self.assertNotIn("\r", texto)

    def test_aspas_simples_no_caminho_nao_quebram_o_script(self):
        texto = carregar().lancador(self.valores(RAIZ="/mnt/e/D'Ávila"))
        self.assertIn("'/mnt/e/D'" + chr(92) + "''Ávila'", texto)  # aspas simples escapadas para o bash

    def test_valores_invalidos_sao_recusados(self):
        m = carregar()
        for chave, ruim in (("CLAUDE_SHA256", "abc"), ("PERFIL_SHA256", "Z" * 64), ("PROJETO", "../x"),
                            ("RAIZ", "relativo/x"), ("CLAUDE_BIN", "claude"), ("TITULAR", "Titular Silva"),
                            ("LOCAL_SHA256", "abc")):
            with self.subTest(chave=chave), self.assertRaises(ValueError):
                m.lancador(self.valores(**{chave: ruim}))
        with self.assertRaises(ValueError):
            m.lancador({k: v for k, v in self.valores().items() if k != "PERFIL_SHA256"})

    def test_linha_de_comando_fixa_perfil_e_hooks_da_raiz(self):
        base = Path(tempfile.mkdtemp(prefix="lancador-teste-"))
        try:
            raiz = raiz_preparada(base)  # 1.7.7: o lançador só fixa perfil, hooks e identidade que conferem
            ganchos_dir = raiz / ".claude" / "hooks"
            saida = base / "abrir-fundacao.sh"
            r = self.lancar(raiz, saida)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            texto = saida.read_text(encoding="utf-8")
            import hashlib
            for arq in (raiz / ".claude" / "settings.wsl.json", ganchos_dir / "guarda_caminho.py",
                        ganchos_dir / "guarda_identidade.py", ganchos_dir / "sinais_sessao.py"):
                self.assertIn(hashlib.sha256(arq.read_bytes()).hexdigest(), texto)
            (ganchos_dir / "guarda_identidade.py").unlink()
            r = self.lancar(raiz, base / "outro.sh")
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("guarda_identidade", r.stdout + r.stderr)
            self.assertFalse((base / "outro.sh").exists())
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_linha_de_comando_so_fixa_o_que_confere(self):
        """Auditoria Codex Security da 1.7.6, #5: o lançador fixava o hash de qualquer perfil que passasse na
        conferência parcial e nem olhava o settings.local.json. Agora confere perfil (igual ao do modelo), hooks
        (iguais aos da skill) e identidade (só a do titular informado) nos mesmos bytes cujo hash fixa."""
        import hashlib
        base = Path(tempfile.mkdtemp(prefix="lancador-conferido-teste-"))
        try:
            raiz = raiz_preparada(base)
            local = raiz / ".claude" / "settings.local.json"
            r = self.lancar(raiz, base / "certo.sh")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            texto = (base / "certo.sh").read_text(encoding="utf-8")
            self.assertIn(hashlib.sha256(local.read_bytes()).hexdigest(), texto)
            self.assertIn("TITULAR='titular'", texto)

            def perfil_com_rede():
                arq = raiz / ".claude" / "settings.wsl.json"
                dados = json.loads(arq.read_text(encoding="utf-8"))
                dados["sandbox"]["network"]["allowedDomains"] = ["exemplo.invalid"]
                arq.write_text(json.dumps(dados), encoding="utf-8")

            def local_com_hook():
                local.write_text(json.dumps({**json.loads(local.read_text(encoding="utf-8")),
                                             "hooks": {"PreToolUse": []}}), encoding="utf-8")

            def hook_alterado():
                with open(raiz / ".claude" / "hooks" / "guarda_identidade.py", "a", encoding="utf-8") as f:
                    f.write("# alterado\n")

            casos = {"perfil": (perfil_com_rede, "titular"), "settings.local.json": (local_com_hook, "titular"),
                     "guarda_identidade": (hook_alterado, "titular"), "outra-pessoa": (lambda: None, "outra-pessoa"),
                     "lab-novo": (lambda: (raiz / "projects" / "lab-novo").mkdir(), "titular")}
            for n, (trecho, (mudanca, titular)) in enumerate(casos.items()):
                with self.subTest(trecho):
                    shutil.rmtree(raiz)
                    raiz_preparada(base)
                    mudanca()
                    saida = base / f"recusado-{n}.sh"
                    r = self.lancar(raiz, saida, titular=titular)
                    self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                    self.assertIn(trecho, r.stdout)
                    self.assertFalse(saida.exists())
        finally:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
