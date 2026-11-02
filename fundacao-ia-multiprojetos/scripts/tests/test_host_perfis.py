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

from apoio import ENV, SKILL, criar_ligacao_dir

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
    # 1.7.10 (contratos do lote 2, §7): todos os hooks com -I -B (sem o site do usuário nem PYTHONPATH no guarda).
    return {"matcher": matcher, "hooks": [{"type": "command", "command": comando, "args": ["-I", "-B", script],
                                           "timeout": 10, "onFailure": "block", "statusMessage": f"{nome}: {mensagem}"}]}


def ganchos(comando: str, pasta: str, sep: str, wsl: bool = False) -> dict:
    """Os hooks do perfil (1.7.10, contratos do lote 2, §7): no Windows, mais o aviso da cópia semanal; no projeto do
    Ubuntu, mais a lista positiva de ferramentas (matcher `*`, a forma documentada de "todas")."""
    inicio = [{"matcher": "compact", "hooks": [{
        "type": "command", "command": comando, "args": ["-I", "-B", pasta + sep + "sinais_sessao.py"],
        "timeout": 3, "onFailure": "block", "statusMessage": "sinais_sessao: lembrando a retomada após compactação"}]}]
    if not wsl:
        inicio.append({"matcher": "startup|resume", "hooks": [{
            "type": "command", "command": comando, "args": ["-I", "-B", pasta + sep + "aviso_copia.py"], "timeout": 5,
            "statusMessage": "aviso_copia: idade da última cópia de segurança"}]})
    pre = [hook(comando, pasta + sep + "guarda_ferramentas.py", "guarda_ferramentas", "*",
                "só as ferramentas da lista do projeto")] if wsl else []
    pre += [hook(comando, pasta + sep + "guarda_caminho.py", "guarda_caminho", "Edit|Write|MultiEdit|NotebookEdit|mcp__.*",
                 "conferindo destino da escrita"),
            hook(comando, pasta + sep + "guarda_identidade.py", "guarda_identidade", "Bash|PowerShell",
                 "conferindo troca de identidade e caminho de outro projeto" + ("" if wsl else " (guarda-corpo)")),
            hook(comando, pasta + sep + "guarda_rede.py", "guarda_rede", "WebFetch|WebSearch",
                 "só os domínios da ficha do projeto" if wsl else "sessões do Windows sem web"),
            hook(comando, pasta + sep + "guarda_leitura.py", "guarda_leitura", "Read|Grep|Glob",
                 "outro projeto e state/ ficam fora" if wsl
                 else "(guarda-corpo: no Windows não há sandbox e o shell lê tudo)")]
    if not wsl:  # o rótulo do Windows vem logo depois do nome, sem os dois-pontos
        pre[-1]["hooks"][0]["statusMessage"] = pre[-1]["hooks"][0]["statusMessage"].replace("guarda_leitura: ",
                                                                                           "guarda_leitura ")
    return {"SessionStart": inicio, "PreToolUse": pre}


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


def complemento(m, modelo) -> list:
    """As negações da regra única (fortes + pastas) que o modelo ainda não traz literalmente (1.7.10)."""
    return m.complemento_de_segredos(m.ler_modelo(modelo))


class PerfilWindows(unittest.TestCase):
    def test_hooks_da_raiz_com_o_python_informado(self):
        m = carregar()
        perfil = m.perfil_windows(raiz=r"E:\Fundacao Exemplo", python=r"C:\Py\python.exe")
        esperado = {
            "permissions": {"deny": NEGACOES_DA_RAIZ[:15] + complemento(m, m.MODELO_WINDOWS) + [
                "Read(./state/**)", "Read(./projects/*/data/**)", "Read(~/.claude/.credentials.json)",
                "Read(~/.codex/auth.json)", "Read(~/.ssh/**)", "WebFetch", "WebSearch", "Edit(./.claude/**)",
                "Edit(./registry/projetos-host.json)"]},  # 1.7.10: regra única, dados e web negados no Windows
            "claudeMdExcludes": ["**/projects/*/data/**"],  # 1.7.0: pasta de dados não vira instrução
            "env": {"FUNDACAO_MCP_PERMITIDAS": "mcp__ccd_*", "FUNDACAO_RAIZ": r"E:\Fundacao Exemplo",
                    "FUNDACAO_SEM_DADOS": "1"},
            "hooks": ganchos(r"C:\Py\python.exe", r"E:\Fundacao Exemplo\.claude\hooks", "\\"),
            "statusLine": {"type": "command", "command": m.comando_status_windows(
                r"C:\Py\python.exe", r"E:\Fundacao Exemplo\.claude\hooks\sinais_sessao.py")},
        }
        self.assertEqual(perfil, esperado)
        self.assertNotIn("{{", m.texto_json(perfil))
        self.assertEqual(m.perfil_windows(raiz="E:/Fundacao Exemplo/", python="C:/Py/python.exe"), esperado)


# registry/projetos-host.json de ensaio (pastas fictícias; o registro só guarda a forma, não confere a existência aqui).
REGISTRO_DE_ENSAIO = {"schema_version": "fundacao.projetos_host/1", "projetos": {
    "lab-a": {"origens": ["/mnt/e/Origem Lab", "/home/ensaio/so-do-ubuntu"], "somente_leitura": ["D:\\Leitura Lab"],
              "aninhadas_negadas": []},
    "caso-real": {"origens": ["D:\\Origem Caso"], "somente_leitura": [], "aninhadas_negadas": ["squad-aninhada"]}}}


class PerfilWindowsComRegistro(unittest.TestCase):
    """Folha da integração, I21 (a): o perfil do Windows é um só e é refeito inteiro a cada preparo. O perfil-windows
    soma ao Edit negado as origens e as pastas só de leitura de TODOS os projetos do registry/projetos-host.json (lido
    pelo ler_projetos_host), além das de --somente-leitura: o preparar-maquina.ps1 rodado sozinho não deixa uma origem
    gravável. `/mnt/<x>/...` vira a pasta do Windows; o caminho só do Ubuntu fica de fora; a leitura não é negada."""

    def test_edicao_negada_das_pastas_de_todos_os_projetos(self):
        m = carregar()
        perfil = m.perfil_windows(raiz=r"E:\Fundacao Exemplo", python=r"C:\Py\python.exe", registro=REGISTRO_DE_ENSAIO,
                                  somente_leitura=[r"F:\Outra", r"D:\Origem Caso"], backups=[r"G:\Copias"])
        negadas = perfil["permissions"]["deny"]
        self.assertEqual([r for r in negadas if r.startswith("Edit(//")],
                         ["Edit(//f/Outra/**)", "Edit(//d/Origem Caso/**)", "Edit(//e/Origem Lab/**)",
                          "Edit(//d/Leitura Lab/**)", "Edit(//g/Copias/**)"])  # sem repetir a que veio dos dois lados
        self.assertFalse([r for r in negadas if "so-do-ubuntu" in r])
        self.assertEqual([r for r in negadas if r.startswith("Read(//")], ["Read(//g/Copias/**)"])  # só as cópias
        vazio = {"schema_version": "fundacao.projetos_host/1", "projetos": {}}
        self.assertEqual(m.perfil_windows(raiz=r"E:\Fundacao Exemplo", python=r"C:\Py\python.exe", registro=vazio),
                         m.perfil_windows(raiz=r"E:\Fundacao Exemplo", python=r"C:\Py\python.exe"))

    def test_linha_de_comando_nega_a_edicao_da_origem_registrada_sem_somente_leitura(self):
        """Contraprova: o perfil-windows de antes lia o registro só pelas skills negadas e saía sem o Edit negado."""
        base = Path(tempfile.mkdtemp(prefix="host-perfil-windows-registro-"))
        try:
            raiz = base / "Fundacao Exemplo"
            for nome in ("caso-real", "lab-a"):
                (raiz / "projects" / nome).mkdir(parents=True)
            (raiz / "registry").mkdir()
            (raiz / "registry" / "projetos-host.json").write_text(json.dumps(REGISTRO_DE_ENSAIO, ensure_ascii=False),
                                                                  encoding="utf-8", newline="\n")
            r = rodar("perfil-windows", "--raiz", raiz, "--python", sys.executable, "--projeto", "caso-real")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            negadas = json.loads(r.stdout)["permissions"]["deny"]
            for regra in ("Edit(//d/Origem Caso/**)", "Edit(//e/Origem Lab/**)", "Edit(//d/Leitura Lab/**)",
                          "Skill(squad-aninhada)"):
                self.assertIn(regra, negadas)
            self.assertFalse([regra for regra in negadas if "so-do-ubuntu" in regra])
            (raiz / "registry" / "projetos-host.json").write_text('{"schema_version": "outro"}', encoding="utf-8")
            r = rodar("perfil-windows", "--raiz", raiz, "--python", sys.executable)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)  # registro fora do esquema: nada sai
            self.assertIn("fundacao.projetos_host/1", r.stdout)
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_raiz_de_um_disco_nas_copias_vale_o_disco_inteiro(self):
        """Revisão seguinte da terceira rodada da integração, defeito 1: o disco só das cópias ("C:\\") chega ao ajudante
        com a barra (o Get-PastasConferidas dos scripts do Windows a tirava, e "C:" era recusado como "pasta do Windows
        com unidade esperada") e sai como o disco inteiro, na leitura e na edição; "C:" sem a barra segue recusado.
        Também pela linha de comando, como o preparar-maquina.ps1 chama."""
        m = carregar()
        perfil = m.perfil_windows(raiz=r"E:\Fundacao Exemplo", python=r"C:\Py\python.exe", backups=["C:\\"],
                                  somente_leitura=["F:/"])
        negadas = perfil["permissions"]["deny"]
        for regra in ("Read(//c/**)", "Edit(//c/**)", "Edit(//f/**)"):
            self.assertIn(regra, negadas)
        self.assertNotIn("Read(//f/**)", negadas)  # só leitura: a leitura segue
        with self.assertRaises(ValueError):
            m.perfil_windows(raiz=r"E:\Fundacao Exemplo", python=r"C:\Py\python.exe", backups=["C:"])
        r = rodar("perfil-windows", "--raiz", r"E:\Fundacao Exemplo", "--python", r"C:\Py\python.exe", "--backups", "C:\\")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        negadas = json.loads(r.stdout)["permissions"]["deny"]
        self.assertIn("Read(//c/**)", negadas)
        self.assertIn("Edit(//c/**)", negadas)

    def test_pasta_que_contem_a_raiz_nao_vai_ao_perfil(self):
        """A lacuna vizinha do defeito 1 (revisão seguinte da terceira rodada da integração): a pasta que é a raiz ou a
        contém negaria às sessões a própria fundação. Os scripts do Windows e o registrar-projeto já a recusam; o
        registro antigo ou feito à mão chega ao ajudante pelo preparar-maquina.ps1 rodado sozinho, e ele recusa, com a
        pasta e o que fazer, sem gerar o perfil. A pasta vizinha que só começa com o mesmo nome segue."""
        m = carregar()
        raiz = r"E:\Fundacao Exemplo"
        casos = {"registro": dict(registro={"schema_version": "fundacao.projetos_host/1", "projetos": {"lab-a": {
                     "origens": ["/mnt/e"], "somente_leitura": [], "aninhadas_negadas": []}}}),
                 "backups": dict(backups=["E:\\"]),
                 "somente leitura": dict(somente_leitura=["e:/fundacao exemplo/"])}
        for nome, kw in casos.items():
            with self.subTest(nome), self.assertRaises(ValueError) as erro:
                m.perfil_windows(raiz=raiz, python=r"C:\Py\python.exe", **kw)
            self.assertIn("contém a raiz", str(erro.exception))
        perfil = m.perfil_windows(raiz=raiz, python=r"C:\Py\python.exe", backups=[r"E:\Fundacao Exemplo B"])
        self.assertIn("Edit(//e/Fundacao Exemplo B/**)", perfil["permissions"]["deny"])

    def test_registro_por_ligacao_nao_e_lido(self):
        """O registro é lido pelo ler_projetos_host, sem seguir ligação: registry/ como junção (ou link) recusa."""
        base = Path(tempfile.mkdtemp(prefix="host-perfil-windows-ligacao-"))
        try:
            raiz = base / "Fundacao Exemplo"
            (raiz / "projects" / "caso-real").mkdir(parents=True)
            fora = base / "registro-fora"
            fora.mkdir()
            (fora / "projetos-host.json").write_text(json.dumps(REGISTRO_DE_ENSAIO, ensure_ascii=False),
                                                     encoding="utf-8", newline="\n")
            criar_ligacao_dir(raiz / "registry", fora)
            r = rodar("perfil-windows", "--raiz", raiz, "--python", sys.executable)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("ligação", r.stdout)
        finally:
            shutil.rmtree(base, ignore_errors=True)


class PerfilWsl(unittest.TestCase):
    """O perfil do PROJETO no Ubuntu (1.7.10) sai do modelo com os caminhos desta máquina: plano A mais as negações
    nominais do plano B, `state/` fora do sandbox (só o porteiro abre o banco) e tudo fechado sem ficha assinada."""

    def setUp(self):
        self.m = carregar()
        self.kw = dict(raiz=r"E:\Fundacao Exemplo", projeto="caso-real", perfil_windows=r"C:\Perfis\titular.PC-EXEMPLO",
                       outros_projetos=["lab-b", "lab-a", "lab-c"], somente_leitura=[r"D:\Origem Ç"])

    def test_reproduz_o_perfil_v3_do_caso_real(self):
        """O v3 da 1.7.9 (state/ legível e gravável no sandbox) deixou de valer: o perfil do projeto da 1.7.10."""
        raiz, perfil_win = "/mnt/e/Fundacao Exemplo", "/mnt/c/Perfis/titular.PC-EXEMPLO"
        proj = raiz + "/projects/caso-real"
        outros = ("lab-a", "lab-b", "lab-c")
        nominais = [r for o in outros for r in (f"Read(/{raiz}/projects/{o}/**)", f"Read(/{raiz}/.claude/projetos/{o}/**)")]
        nominais += ["Read(//mnt/d/**)", f"Read(/{perfil_win}/**)"] + [f"Read(~/{r})" for r in (
            ".claude/projects/**", ".claude/history.jsonl", ".claude/file-history/**", ".claude/paste-cache/**",
            ".claude/session-env/**", ".claude/sessions/**", ".claude/shell-snapshots/**", ".claude/todos/**",
            ".claude/plans/**", ".claude/backups/**", ".codex/**", ".fundacao/**", ".local/share/fundacao-ia/**")]
        esperado = {
            "permissions": {"blockReadsOutsideWorkingDirectories": True, "deny": NEGACOES_DA_RAIZ[:15] + complemento(
                self.m, self.m.MODELO_WSL) + [
                f"Read(/{raiz}/state/**)", "Read(~/.claude/.credentials.json)", "Read(~/.codex/auth.json)",
                "Read(~/.ssh/**)", f"Read(/{perfil_win}/.claude/.credentials.json)",
                f"Read(/{perfil_win}/.codex/auth.json)", f"Read(/{perfil_win}/.ssh/**)", *nominais,
                "WebFetch", "WebSearch",  # 1.7.0: sem saída pela web (sem ficha)
                f"Edit(/{raiz}/.claude/**)", f"Edit(/{raiz}/registry/**)", f"Edit(/{proj}/.claude/**)",
                f"Edit(/{proj}/.porteiro/respostas/**)", f"Edit(/{proj}/CLAUDE.local.md)",
                "Edit(//mnt/c/ProgramData/FundacaoIA/**)", "Edit(//mnt/d/Origem Ç/**)"], "allow": []},
            "claudeMdExcludes": ["**/projects/*/data/**"],
            "syncClaudeAiSkills": False, "syncClaudeAiPlugins": False, "disableClaudeAiConnectors": True,
            "env": {"FUNDACAO_" + "PRINCIPAL": "sessao-caso-real", "FUNDACAO_PROJECT": "caso-real",
                    "FUNDACAO_RAIZ": raiz, "FUNDACAO_PORTEIRO": proj + "/.porteiro",
                    "FUNDACAO_FERRAMENTAS": "Bash,Read,Edit,Write,Glob,Grep,Skill,Task,TodoWrite",
                    "FUNDACAO_MCP_PERMITIDAS": "", "FUNDACAO_DOMINIOS_WEB": "", "DISABLE_AUTOUPDATER": "1",
                    "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "1", "PYTHONPATH": raiz, "XDG_CACHE_HOME": proj + "/.cache",
                    "npm_config_cache": proj + "/.cache/npm", "PIP_CACHE_DIR": proj + "/.cache/pip",
                    "UV_CACHE_DIR": proj + "/.cache/uv", "CLAUDE_CODE_DISABLE_WEB_FETCH": "1"},
            "hooks": ganchos("/usr/bin/python3", raiz + "/.claude/hooks", "/", wsl=True),
            "statusLine": {"type": "command", "command": "/usr/bin/python3 -I -B '" + raiz
                           + "/.claude/hooks/sinais_sessao.py' --status-line"},
            "sandbox": {
                "enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False,
                "filesystem": {
                    "allowWrite": [],
                    "denyWrite": [raiz + "/.claude", raiz + "/registry", proj + "/.claude", proj + "/.porteiro/respostas",
                                  proj + "/CLAUDE.local.md", raiz + "/projects/lab-a", raiz + "/projects/lab-b",
                                  raiz + "/projects/lab-c", "/mnt/d/Origem Ç", "/mnt/c/ProgramData/FundacaoIA"],
                    "denyRead": ["~/.ssh", "~/.claude/.credentials.json", "~/.codex", perfil_win + "/.ssh",
                                 perfil_win + "/.claude/.credentials.json", perfil_win + "/.codex", "/tmp", "/run",
                                 "/var/run", "/mnt/wsl", "/mnt/wslg"],
                    "allowRead": [raiz + "/fundacao", "/mnt/c/ProgramData/FundacaoIA", "/mnt/d/Origem Ç",
                                  "/tmp/fundacao-ia-caso-real"]},
                "network": {"allowedDomains": [], "strictAllowlist": True}},
        }
        self.assertEqual(self.m.perfil_wsl(**self.kw), esperado)

    def test_state_fora_do_sandbox_e_negado_ao_read(self):
        """1.7.10: o contrário da v3 da 1.7.9. `state/` existe, fica negado (Read absoluto, que vira denyRead) e sem
        allowRead nem allowWrite: a armadilha do tmpfs da v1 não volta, e só o porteiro, fora do sandbox, abre o banco."""
        perfil = self.m.perfil_wsl(**self.kw)
        fs = perfil["sandbox"]["filesystem"]
        self.assertNotIn("/mnt/e/Fundacao Exemplo/state", fs["allowRead"])
        self.assertNotIn("/mnt/e/Fundacao Exemplo/state", fs["allowWrite"])
        self.assertIn("Read(//mnt/e/Fundacao Exemplo/state/**)", perfil["permissions"]["deny"])
        self.assertEqual(self.m.conferir_perfil_wsl(perfil, "/mnt/e/Fundacao Exemplo"), [])

    def test_sem_backups_nem_somente_leitura_nao_sobra_marcador(self):
        kw = {**self.kw, "backups": [], "somente_leitura": [], "outros_projetos": []}
        perfil = self.m.perfil_wsl(**kw)
        texto = self.m.texto_json(perfil)
        self.assertNotIn("{{", texto)
        self.assertEqual(perfil["sandbox"]["filesystem"]["allowWrite"], [])  # 1.7.10: escrita só no projeto
        self.assertNotIn("Edit(//mnt/d/Origem Ç/**)", perfil["permissions"]["deny"])
        with self.assertRaises(ValueError):  # 1.7.10: cópias de segurança não ficam graváveis pela sessão
            self.m.perfil_wsl(**{**kw, "backups": [r"D:\Backups-Exemplo"]})

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
        """As formas antigas de `state/` no sandbox (v3 da 1.7.9: legível e gravável; v2: só legível) são acusadas;
        na 1.7.10, state/ fica fora do sandbox."""
        atual = self.m.perfil_wsl(**self.kw)
        v2 = json.loads(json.dumps(atual))
        v2["sandbox"]["filesystem"]["allowRead"].append("/mnt/e/Fundacao Exemplo/state")
        v3 = json.loads(json.dumps(v2))
        v3["sandbox"]["filesystem"]["allowWrite"].append("/mnt/e/Fundacao Exemplo/state")
        self.assertTrue(any("allowRead" in p for p in self.m.conferir_perfil_wsl(v2, "/mnt/e/Fundacao Exemplo")))
        self.assertTrue(any("allowWrite" in p for p in self.m.conferir_perfil_wsl(v3, "/mnt/e/Fundacao Exemplo")))


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
                                        outros_projetos=["lab-a", "lab-b"], somente_leitura=[r"D:\Origem Ç"],
                                        negar=["squad-peticoes"])  # 1.7.10: sem backups no perfil do projeto

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
            area = ("--area-raiz", base / "area-inexistente")  # 1.7.10: nunca a área do titular desta máquina
            r = rodar("perfil-wsl", "--raiz", raiz, "--projeto", "caso-real", "--perfil-windows", r"C:\Perfis\titular",
                      *area, "--saida", perfil)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = rodar("conferir-perfil-wsl", "--perfil", perfil, "--raiz", raiz, "--projeto", "caso-real", *area)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            (raiz / "projects" / "lab-novo").mkdir()
            r = rodar("conferir-perfil-wsl", "--perfil", perfil, "--raiz", raiz, "--projeto", "caso-real", *area)
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
                      r"C:\Perfis\titular.PC-EXEMPLO", "--area-raiz", self.base / "area-inexistente", "--saida",
                      destino)  # 1.7.10: sem --backups (recusado) e sem ler a área do titular desta máquina
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


def raiz_preparada(base: Path):
    """Raiz como o preparo do Windows a deixa (hooks e kit iguais aos da skill de ensaio) e o Claude Code falso.
    1.7.10: o lançador sai do `instalar-projeto`, na área do titular, e não mais do perfil único da raiz."""
    from test_host_projeto_apoio import claude_de_ensaio, raiz_de_ensaio, skill_de_ensaio
    skill = skill_de_ensaio(base)
    return skill, raiz_de_ensaio(base, skill, outros=()), claude_de_ensaio(base / "claude-ensaio")


class Lancador(unittest.TestCase):
    """O lançador da sessão do projeto sai do modelo com os hashes fixados e aspas seguras para o bash."""

    def valores(self, **extra) -> dict:
        return {"RAIZ": "/mnt/e/Raiz de Ensaio ç", "PROJETO": "caso-real", "USUARIO": "titular",
                "AREA": "/etc/fundacao-ia/projetos/caso-real", "SKILL": "/etc/fundacao-ia/skill/1.7.10-abc",
                "CLAUDE_BIN": "/etc/fundacao-ia/claude/2.1.302/claude", "CLAUDE_VERSAO": "2.1.302", "CLAUDE_SHA256": H1,
                "CLAUDE_ORIGEM_HASH": "manifesto assinado", "FERRAMENTAS": "Bash,Read", "PLUGINS": "",
                "PREPARO_SHA256": H2, "PORTEIRO_SHA256": H3, "TEMP_PROJETO": "/tmp/fundacao-ia-caso-real",
                "SONDA_INTEROP_CMD": "/mnt/c/Windows/System32/cmd.exe",
                "SONDA_INTEROP_BINFMT": "/proc/sys/fs/binfmt_misc", **extra}

    def lancar(self, skill: Path, raiz: Path, base: Path, claude: Path) -> subprocess.CompletedProcess:
        from test_host_projeto_apoio import instalar
        return instalar(skill, raiz, base, "caso-real", claude)

    def test_sem_marcadores_e_com_os_valores_fixados(self):
        texto = carregar().lancador(self.valores())
        self.assertNotIn("{{", texto)
        for valor in (H1, H2, H3, "2.1.302", "caso-real", "'/mnt/e/Raiz de Ensaio ç'"):
            self.assertIn(valor, texto)
        self.assertTrue(texto.startswith("#!/usr/bin/env bash\n"))
        self.assertNotIn("\r", texto)

    def test_aspas_simples_no_caminho_nao_quebram_o_script(self):
        texto = carregar().lancador(self.valores(RAIZ="/mnt/e/D'Ávila"))
        self.assertIn("'/mnt/e/D'" + chr(92) + "''Ávila'", texto)  # aspas simples escapadas para o bash

    def test_valores_invalidos_sao_recusados(self):
        m = carregar()
        for chave, ruim in (("CLAUDE_SHA256", "abc"), ("PREPARO_SHA256", "Z" * 64), ("PROJETO", "../x"),
                            ("RAIZ", "relativo/x"), ("CLAUDE_BIN", "claude"), ("USUARIO", "Titular Silva"),
                            ("PORTEIRO_SHA256", "abc")):
            with self.subTest(chave=chave), self.assertRaises(ValueError):
                m.lancador(self.valores(**{chave: ruim}))
        with self.assertRaises(ValueError):
            m.lancador({k: v for k, v in self.valores().items() if k != "PREPARO_SHA256"})

    @unittest.skipUnless(sys.platform.startswith("linux"), "1.7.10: o lançador sai do instalar-projeto, no Ubuntu")
    def test_linha_de_comando_fixa_perfil_e_hooks_da_raiz(self):
        import hashlib
        base = Path(tempfile.mkdtemp(prefix="lancador-teste-")).resolve()
        try:
            skill, raiz, claude = raiz_preparada(base)  # 1.7.7: o lançador só fixa perfil e hooks que conferem
            ganchos_dir = raiz / ".claude" / "hooks"
            r = self.lancar(skill, raiz, base, claude)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            area = base / "area" / "projetos" / "caso-real"
            hashes = json.loads((area / "hashes.json").read_text(encoding="utf-8"))["arquivos"]
            for arq in (area / "settings.wsl.json", ganchos_dir / "guarda_caminho.py",
                        ganchos_dir / "guarda_identidade.py", ganchos_dir / "sinais_sessao.py"):
                self.assertEqual(hashes[arq.as_posix()], hashlib.sha256(arq.read_bytes()).hexdigest())
            self.assertIn(hashlib.sha256(claude.read_bytes()).hexdigest(),
                          (base / "bin" / "abrir-fundacao-caso-real").read_text(encoding="utf-8"))
            shutil.rmtree(base / "area")
            shutil.rmtree(base / "bin")
            (ganchos_dir / "guarda_identidade.py").unlink()
            r = self.lancar(skill, raiz, base, claude)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("guarda_identidade", r.stdout + r.stderr)
            self.assertFalse((base / "bin").exists())
        finally:
            shutil.rmtree(base, ignore_errors=True)

    @unittest.skipUnless(sys.platform.startswith("linux"), "1.7.10: o lançador sai do instalar-projeto, no Ubuntu")
    def test_linha_de_comando_so_fixa_o_que_confere(self):
        """Auditoria Codex Security da 1.7.6, #5: o lançador fixava o hash de qualquer perfil que passasse na
        conferência parcial. Na 1.7.10 o perfil é gerado na área do titular, e o preparo só fixa hooks iguais aos da
        skill, o kit da raiz igual ao da skill e o Claude Code com o SHA-256 informado; senão, nada é gravado."""
        from test_host_projeto_apoio import instalar, sha as sha_de
        base = Path(tempfile.mkdtemp(prefix="lancador-conferido-teste-")).resolve()
        try:
            def hook_alterado(raiz, _claude):
                with open(raiz / ".claude" / "hooks" / "guarda_identidade.py", "a", encoding="utf-8") as f:
                    f.write("# alterado\n")

            def kit_alterado(raiz, _claude):
                with open(raiz / "fundacao" / "__init__.py", "a", encoding="utf-8") as f:
                    f.write("# alterado\n")

            def claude_trocado(_raiz, claude):
                with open(claude, "a", encoding="utf-8") as f:
                    f.write("# outro binário\n")

            casos = {"guarda_identidade": hook_alterado, "kit da raiz": kit_alterado, "não confere": claude_trocado}
            for n, (trecho, mudanca) in enumerate(casos.items()):
                with self.subTest(trecho):
                    pasta = base / f"caso-{n}"
                    pasta.mkdir()
                    skill, raiz, claude = raiz_preparada(pasta)
                    esperado = sha_de(claude)
                    mudanca(raiz, claude)
                    r = instalar(skill, raiz, pasta, "caso-real", claude, "--claude-sha256", esperado)
                    self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                    self.assertIn(trecho, r.stdout)
                    self.assertFalse((pasta / "bin").exists())
        finally:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
