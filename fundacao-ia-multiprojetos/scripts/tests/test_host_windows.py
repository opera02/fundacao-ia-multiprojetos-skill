"""`assets/host/windows/preparar-maquina.ps1`: chave do titular, âncora das decisões assinadas, hooks e perfis.

Na implantação real de 2026-10-20 a âncora `allowed_signers` levou cinco voltas: `(OI)(CI)` aplicado ao arquivo o
deixou ilegível; depois do `/reset`, o dono era o próprio usuário, que tem `WRITE_DAC` implícito e trocaria as
permissões sem UAC (a sondagem antiga, só de escrita, dizia "protegida"); só com o dono Administradores (`takeown
/A`) ela ficou protegida. Hooks e perfis foram copiados à mão.

Estes testes rodam o script num PowerShell de verdade, em pastas descartáveis, com chaves de ensaio (`-N` só aqui,
no teste: o script nunca recebe nem repassa senha). O que exige administrador não é simulado como real: roda-se a
simulação (`-Simular`/`-WhatIf`), o modo `-SemUAC` (a âncora fica pendente, código 3) e as peças que não exigem
administrador (sondagem sem alterar nada, ACL sem a troca de dono, recusa da etapa elevada sem administrador).
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import ENV, SKILL

PS1 = SKILL / "assets" / "host" / "windows" / "preparar-maquina.ps1"
POWERSHELL = shutil.which("powershell.exe") if os.name == "nt" else None
SSH_KEYGEN = (str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "OpenSSH" / "ssh-keygen.exe")
              if os.name == "nt" else None)
TEM_SSH = bool(SSH_KEYGEN and Path(SSH_KEYGEN).is_file())
ELEVADO = bool(os.name == "nt" and ctypes.windll.shell32.IsUserAnAdmin())
SENHA_DE_ENSAIO = "ensaio-nao-e-credencial-123"


def gerar_chave(destino: Path, senha: str) -> str:
    """Chave descartável do teste; devolve a linha pública."""
    subprocess.run([SSH_KEYGEN, "-q", "-t", "ed25519", "-N", senha, "-C", "ensaio-decisoes", "-f", str(destino)],
                   check=True, capture_output=True, timeout=60)
    return Path(str(destino) + ".pub").read_text(encoding="ascii").strip()


def impressao(linha_publica: str) -> str:
    blob = base64.b64decode(linha_publica.split()[1])
    return "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")


def sha(caminho: Path) -> str:
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def fotografia(*pastas: Path) -> dict:
    """Arquivos e hashes sob as pastas (para provar que nada mudou)."""
    out = {}
    for pasta in pastas:
        if pasta.exists():
            for p in sorted(pasta.rglob("*")):
                out[str(p)] = sha(p) if p.is_file() else "<pasta>"
    return out


@unittest.skipUnless(POWERSHELL and TEM_SSH, "PowerShell do Windows ou OpenSSH do sistema indisponível")
class _Base(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="preparar-maquina-teste-")).resolve()  # nome longo (TEMP curto no GitHub)
        self.raiz = self.base / "Fundacao Teste"
        for pasta in ("registry", "projects/caso-real", "projects/lab-a"):
            (self.raiz / pasta).mkdir(parents=True)
        self.chave = self.base / "ssh" / "fundacao_titular"
        self.chave.parent.mkdir()
        self.ancora = self.base / "ProgramData" / "FundacaoIA" / "confianca" / "allowed_signers"
        self.n = 0

    def tearDown(self):
        subprocess.run(["icacls", str(self.base), "/reset", "/T", "/C", "/Q"], capture_output=True, timeout=120)
        shutil.rmtree(self.base, ignore_errors=True)

    def rodar(self, *args, relatorio: bool = True):
        self.n += 1
        rel = self.base / f"relatorio-{self.n}.json"
        cmd = [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(PS1),
               "-Raiz", str(self.raiz), "-Titular", "titular", "-Chave", str(self.chave), "-Ancora", str(self.ancora),
               "-Python", sys.executable, *map(str, args)]
        if relatorio:
            cmd += ["-Relatorio", str(rel)]
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV,
                           timeout=300)
        dados = json.loads(rel.read_text(encoding="utf-8")) if rel.is_file() else None
        return p, dados

    def item(self, relatorio: dict, ident: str) -> dict:
        return next(i for i in relatorio["itens"] if i["id"] == ident)

    def ps(self, codigo: str, env: dict | None = None):
        """Funções do script (carregado com ponto, sem rodar o principal) num PowerShell novo."""
        arq = self.base / f"trecho-{self.n}.ps1"
        self.n += 1
        prelude = "try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }"  # saída em UTF-8
        arq.write_text(prelude + chr(10) + f". '{PS1}'" + chr(10) + codigo + chr(10), encoding="utf-8-sig")
        p = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                            str(arq)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
                           env=env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return json.loads(p.stdout.strip().splitlines()[-1])


@unittest.skipIf(ELEVADO, "o script recusa rodar elevado (código 2), por desenho: este ensaio exige a conta comum")
class Simulacao(_Base):
    def test_simulacao_mostra_o_plano_e_nao_grava_nada(self):
        antes = fotografia(self.raiz, self.chave.parent, self.base / "ProgramData")
        p, rel = self.rodar("-Simular", "-Projeto", "caso-real")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(fotografia(self.raiz, self.chave.parent, self.base / "ProgramData"), antes)
        self.assertTrue(rel["simulacao"])
        self.assertFalse(rel["nada_a_fazer"])
        acoes = {i["id"]: i["acao"] for i in rel["itens"]}
        self.assertEqual(acoes["chave"], "criar")
        self.assertEqual(acoes["ancora"], "criar")
        for ident in ("hook:guarda_caminho.py", "hook:guarda_identidade.py", "settings.json", "settings.wsl.json",
                      "settings.local.json"):
            self.assertEqual(acoes[ident], "criar", ident)
        ancora = self.item(rel, "ancora")
        self.assertTrue(ancora["exige_admin"])
        self.assertIn("confirmação", ancora["detalhe"])  # acento certo: o .ps1 é lido como UTF-8 (BOM)
        self.assertFalse(self.item(rel, "chave")["exige_admin"])

    def test_whatif_equivale_a_simulacao(self):
        antes = fotografia(self.raiz, self.chave.parent, self.base / "ProgramData")
        p, rel = self.rodar("-WhatIf")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(rel["simulacao"])
        self.assertEqual(fotografia(self.raiz, self.chave.parent, self.base / "ProgramData"), antes)

    def test_raiz_que_nao_e_fundacao_e_recusada(self):
        outra = self.base / "qualquer"
        outra.mkdir()
        p = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                            str(PS1), "-Raiz", str(outra), "-Titular", "titular", "-Simular"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=ENV, timeout=300)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertFalse((outra / ".claude").exists())


@unittest.skipIf(ELEVADO, "o script recusa rodar elevado (código 2), por desenho: este ensaio exige a conta comum")
class SemUac(_Base):
    """Modo real sem o UAC: tudo o que não exige administrador é feito; a âncora fica pendente (código 3)."""

    def setUp(self):
        super().setUp()
        self.publica = gerar_chave(self.chave, SENHA_DE_ENSAIO)

    def test_instala_hooks_e_perfis_e_deixa_a_ancora_pendente(self):
        p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", "-Backups", str(self.base / "Backups"))
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        claude = self.raiz / ".claude"
        for nome in ("guarda_caminho.py", "guarda_identidade.py"):
            self.assertEqual(sha(claude / "hooks" / nome), sha(SKILL / "assets" / "hooks" / nome))
        win = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
        gancho = win["hooks"]["PreToolUse"][0]["hooks"][0]
        self.assertEqual(gancho["command"], sys.executable)
        self.assertEqual(gancho["args"][1], str(claude / "hooks" / "guarda_caminho.py"))
        wsl = json.loads((claude / "settings.wsl.json").read_text(encoding="utf-8"))
        fs = wsl["sandbox"]["filesystem"]
        self.assertTrue(any(c.endswith("/Fundacao Teste/state") for c in fs["allowWrite"]))
        self.assertTrue(any(c.endswith("/Fundacao Teste/projects/lab-a") for c in fs["denyWrite"]))
        self.assertTrue(any(c.endswith("/Backups") for c in fs["allowWrite"]))
        local = json.loads((claude / "settings.local.json").read_text(encoding="utf-8"))
        self.assertEqual(local["env"], {"FUNDACAO_PRINCIPAL": "titular", "FUNDACAO_PROJECT": "caso-real"})  # 1.7.0
        chave = self.item(rel, "chave")
        self.assertEqual((chave["acao"], chave["estado_da_senha"]), ("igual", "presente"))
        self.assertEqual(chave["impressao_digital"], impressao(self.publica))
        self.assertEqual(self.item(rel, "ancora")["acao"], "pendente_admin")
        self.assertFalse(self.ancora.exists())

    def test_skills_aninhadas_negadas_por_nome_nos_dois_perfis(self):
        """1.7.0 (proposta 2): -NegarSkill, com nomes separados por vírgula, vira Skill(<nome>) nas negações."""
        p, _rel = self.rodar("-SemUAC", "-Projeto", "caso-real", "-NegarSkill", "skill-da-copia,outra-skill")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        for perfil in ("settings.json", "settings.wsl.json"):
            negadas = json.loads((self.raiz / ".claude" / perfil).read_text(encoding="utf-8"))["permissions"]["deny"]
            self.assertLessEqual({"Skill(skill-da-copia)", "Skill(outra-skill)"}, set(negadas), perfil)

    def test_segunda_execucao_nao_altera_nada(self):
        self.rodar("-SemUAC", "-Projeto", "caso-real")
        antes = fotografia(self.raiz)
        p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        acoes = {i["id"]: i["acao"] for i in rel["itens"]}
        for ident in ("hook:guarda_caminho.py", "hook:guarda_identidade.py", "settings.json", "settings.wsl.json",
                      "settings.local.json"):
            self.assertEqual(acoes[ident], "igual", ident)
        depois = {k: v for k, v in fotografia(self.raiz).items() if "evidence" not in k}
        self.assertEqual(depois, {k: v for k, v in antes.items() if "evidence" not in k})
        self.assertFalse((self.raiz / ".claude" / "anteriores").exists())

    def test_hook_alterado_e_guardado_antes_de_ser_trocado(self):
        self.rodar("-SemUAC")
        destino = self.raiz / ".claude" / "hooks" / "guarda_caminho.py"
        destino.write_text("# hook alterado\n", encoding="utf-8")
        p, rel = self.rodar("-SemUAC")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual(sha(destino), sha(SKILL / "assets" / "hooks" / "guarda_caminho.py"))
        item = self.item(rel, "hook:guarda_caminho.py")
        self.assertEqual(item["acao"], "atualizar")
        self.assertEqual(Path(item["anterior"]).read_text(encoding="utf-8"), "# hook alterado\n")
        self.assertIn(str(self.raiz / ".claude" / "anteriores"), item["anterior"])

    def test_identidade_diferente_nao_e_sobrescrita(self):
        local = self.raiz / ".claude" / "settings.local.json"
        local.parent.mkdir()
        local.write_text('{"env": {"FUNDACAO_PRINCIPAL": "outra-pessoa"}}' + chr(10), encoding="utf-8")
        antes = local.read_bytes()
        p, rel = self.rodar("-SemUAC")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertEqual(self.item(rel, "settings.local.json")["acao"], "conflito")
        self.assertEqual(local.read_bytes(), antes)

    def test_settings_local_sem_identidade_ganha_so_a_identidade(self):
        local = self.raiz / ".claude" / "settings.local.json"
        local.parent.mkdir()
        local.write_text('{"sandbox": {"enabled": true}}' + chr(10), encoding="utf-8")
        p, rel = self.rodar("-SemUAC")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        dados = json.loads(local.read_text(encoding="utf-8"))
        self.assertEqual(dados, {"sandbox": {"enabled": True}, "env": {"FUNDACAO_PRINCIPAL": "titular"}})
        self.assertEqual(self.item(rel, "settings.local.json")["acao"], "atualizar")


@unittest.skipIf(ELEVADO, "o script recusa rodar elevado (código 2), por desenho: este ensaio exige a conta comum")
class ChaveSemSenha(_Base):
    def test_chave_sem_senha_e_recusada_antes_de_qualquer_escrita(self):
        gerar_chave(self.chave, "")
        p, rel = self.rodar("-SemUAC")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertEqual(self.item(rel, "chave")["estado_da_senha"], "ausente")
        self.assertFalse((self.raiz / ".claude").exists())


@unittest.skipIf(ELEVADO, "teste da recusa sem administrador: este processo está elevado")
class EtapaElevada(_Base):
    def test_etapa_da_ancora_recusa_sem_administrador(self):
        publica = gerar_chave(self.chave, SENHA_DE_ENSAIO)
        p = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                            str(PS1), "-EtapaAncora", "-Ancora", str(self.ancora), "-Titular", "titular",
                            "-ChavePublica", str(self.chave) + ".pub", "-ImpressaoEsperada", impressao(publica)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, timeout=300)
        self.assertEqual(p.returncode, 4, p.stdout + p.stderr)
        self.assertFalse(self.ancora.exists())
        self.assertFalse(self.ancora.parent.exists())


class Funcoes(_Base):
    """Peças do script carregadas com ponto (o principal não roda)."""

    def setUp(self):
        super().setUp()
        self.publica = gerar_chave(self.chave, SENHA_DE_ENSAIO)

    def test_impressao_digital_igual_a_do_ssh_keygen(self):
        r = subprocess.run([SSH_KEYGEN, "-l", "-E", "sha256", "-f", str(self.chave) + ".pub"], capture_output=True,
                           text=True, timeout=60)
        dados = self.ps(f"@{{ fp = Get-ImpressaoDigital -LinhaPublica '{self.publica}' }} | ConvertTo-Json -Compress")
        self.assertEqual(dados["fp"], r.stdout.split()[1])
        self.assertEqual(dados["fp"], impressao(self.publica))

    def test_linha_da_ancora_no_formato_da_barreira(self):
        dados = self.ps(f"@{{ l = Get-LinhaAncora -Titular 'titular' -LinhaPublica '{self.publica}' }} | "
                        "ConvertTo-Json -Compress")
        self.assertEqual(dados["l"], 'titular namespaces="fundacao-decisao" ' + self.publica)

    def test_mesclar_a_ancora_sem_perder_nem_trocar_em_silencio(self):
        outra = gerar_chave(self.base / "ssh" / "outra", SENHA_DE_ENSAIO)
        nova = 'titular namespaces="fundacao-decisao" ' + self.publica
        velha = 'titular namespaces="fundacao-decisao" ' + outra
        alheia = 'revisor namespaces="fundacao-decisao" ' + outra
        sem_comentario = 'titular namespaces="fundacao-decisao" ' + " ".join(self.publica.split()[:2])
        casos = [("igual", [sem_comentario], False, [sem_comentario]),
                 ("acrescentar", [alheia], False, [alheia, nova]),
                 ("conflito", [velha], False, [velha]),
                 ("trocar", ["# comentário", velha, alheia], True, ["# comentário", nova, alheia])]
        for acao, linhas, trocar, esperado in casos:
            with self.subTest(acao=acao):
                lista = ", ".join("'" + l.replace("'", "''") + "'" for l in linhas)
                extra = " -Trocar" if trocar else ""
                dados = self.ps(f"$r = Merge-Ancora -Linhas @({lista}) -Titular 'titular' -LinhaNova '{nova}'{extra}\n"
                                "@{ acao = $r.Acao; linhas = @($r.Linhas) } | ConvertTo-Json -Compress")
                self.assertEqual(dados["acao"], acao)
                self.assertEqual(dados["linhas"], esperado)

    def test_sondagem_acusa_arquivo_do_proprio_usuario(self):
        self.ancora.parent.mkdir(parents=True)
        self.ancora.write_text("x\n", encoding="ascii", newline="\n")
        s = self.ps(f"Get-SondagemAncora -Ancora '{self.ancora}' | ConvertTo-Json -Compress -Depth 6")
        self.assertFalse(s["protegida"])
        self.assertTrue(s["arquivo"]["direitos"]["GENERIC_WRITE"])
        acusa_dono = any("dono" in m for m in s["motivos"])
        if ELEVADO and s["arquivo"]["dono_administradores"]:
            # Processo elevado no Windows Server (CI pública da 1.7.2): o arquivo novo nasce com o grupo
            # Administradores como dono, e a sondagem acusa só pelos direitos de escrita desta conta.
            self.assertFalse(acusa_dono, s["motivos"])
        else:
            self.assertTrue(acusa_dono, s["motivos"])


    def test_chamado_de_um_powershell_7_ainda_carrega_o_get_acl(self):
        """Aberto a partir de um PowerShell 7 (como faz o GitHub Actions, ou um terminal do pwsh), o Windows PowerShell
        herda os caminhos de módulo do 7 e o Get-Acl não carrega (CI pública da 1.7.1). O script limpa esses caminhos."""
        modulo = self.base / "PowerShell" / "7" / "Modules" / "Microsoft.PowerShell.Security"
        modulo.mkdir(parents=True)
        (modulo / "Microsoft.PowerShell.Security.psd1").write_text(
            "@{ ModuleVersion = '7.0.0.0'; GUID = 'a94c8c7e-9810-47c0-b8af-65089c13a35a'; PowerShellVersion = '7.0'; "
            "CompatiblePSEditions = @('Core'); CmdletsToExport = @('Get-Acl', 'Set-Acl') }" + chr(10), encoding="utf-8")
        env = {**os.environ, "PSModulePath": str(modulo.parent) + os.pathsep + os.environ.get("PSModulePath", "")}
        dados = self.ps(f"@{{ dono = (Get-Acl -LiteralPath '{self.base}').Owner }} | ConvertTo-Json -Compress", env=env)
        self.assertTrue(dados["dono"])


@unittest.skipUnless(ELEVADO, "só num processo elevado: a recusa do script quando roda como administrador")
class Elevado(_Base):
    def test_rodar_elevado_e_recusado_sem_escrever(self):
        antes = fotografia(self.raiz)
        p, _rel = self.rodar("-SemUAC", "-Projeto", "caso-real")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("PowerShell comum", p.stdout + p.stderr)
        self.assertEqual(fotografia(self.raiz), antes)


@unittest.skipIf(ELEVADO, "as provas de ACL sem administrador não valem num processo elevado")
class AclSemTrocaDeDono(_Base):
    """Reproduz a volta do `/reset`: herança cortada e só leitura para Usuários, mas o dono ainda é o usuário."""

    def setUp(self):
        super().setUp()
        self.ancora.parent.mkdir(parents=True)
        self.ancora.write_text("x\n", encoding="ascii", newline="\n")
        base, pasta = self.ancora.parent.parent, self.ancora.parent
        self.sondagem = self.ps(
            f"Set-AclProtegida -Pasta '{base}' -SemDono; Set-AclProtegida -Pasta '{pasta}' -SemDono\n"
            f"Set-AclArquivoHerdada -Arquivo '{self.ancora}' -SemDono\n"
            f"Get-SondagemAncora -Ancora '{self.ancora}' | ConvertTo-Json -Compress -Depth 6")

    def test_escrita_fechada_mas_o_dono_ainda_troca_as_permissoes(self):
        s = self.sondagem
        self.assertFalse(s["arquivo"]["direitos"]["GENERIC_WRITE"])
        self.assertFalse(s["pasta"]["direitos"]["ADD_FILE"])
        self.assertFalse(s["pasta"]["direitos"]["DELETE_CHILD"])
        self.assertTrue(s["pasta"]["heranca_cortada"])
        self.assertTrue(s["base"]["heranca_cortada"])
        self.assertTrue(s["arquivo"]["direitos"]["WRITE_DAC"])
        self.assertFalse(s["protegida"])
        self.assertTrue(any("dono" in m for m in s["motivos"]))

    def test_arquivo_herda_da_pasta_sem_regra_de_heranca_e_continua_legivel(self):
        dados = self.ps(f"$acl = Get-Acl -LiteralPath '{self.ancora}'\n"
                        "@{ protegido = $acl.AreAccessRulesProtected; "
                        "explicitas = @($acl.Access | Where-Object { -not $_.IsInherited }).Count; "
                        "com_heranca = @($acl.Access | Where-Object { [int]$_.InheritanceFlags -ne 0 }).Count; "
                        f"texto = [IO.File]::ReadAllText('{self.ancora}') }} | ConvertTo-Json -Compress")
        self.assertEqual((dados["protegido"], dados["explicitas"], dados["com_heranca"]), (False, 0, 0))
        self.assertEqual(dados["texto"], "x\n")


class Fonte(unittest.TestCase):
    def test_script_em_utf8_com_bom(self):
        self.assertTrue(PS1.read_bytes().startswith(b"\xef\xbb\xbf"))  # o PowerShell 5.1 lê sem BOM como ANSI

    def test_script_nunca_recebe_nem_repassa_senha(self):
        texto = PS1.read_text(encoding="utf-8-sig")
        self.assertNotRegex(texto, r"(?<![\w-])-N\b")
        for proibido in ("Read-Host", "ConvertTo-SecureString", "-AsSecureString"):
            self.assertNotIn(proibido, texto)


    def test_host_sem_falso_positivo_na_varredura_de_segredos_do_pacote(self):
        """A montagem da transferência recusa o pacote com `senha|token|... = '<8 ou mais caracteres>'`; em 2026-10-21
        o campo com o estado da senha da chave no relatório, com o valor 'presente', parou a liberação da 1.6.0."""
        padrao = re.compile(r"(?i)\b(?:password|senha|passwd|secret|api[_-]?key|token)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]")
        arquivos = [a for a in (SKILL / "assets" / "host").rglob("*") if a.is_file() and a.suffix != ".pyc"]
        arquivos += sorted((SKILL / "scripts" / "tests").glob("test_host_*.py"))
        for arq in arquivos:
            with self.subTest(arquivo=arq.name):
                self.assertIsNone(padrao.search(arq.read_text(encoding="utf-8-sig")))


if __name__ == "__main__":
    unittest.main()
