"""Windows na 1.7.10 (DESENHO §4; contratos do lote 2, §5 e §6; folha do HOST, item 7).

`preparar-maquina.ps1`: o projeto das sessões do Windows vai ao env do `.claude/settings.json`; trocar o projeto já
gravado exige `-TrocarProjeto`, e o plano inteiro é calculado antes da chave, do UAC e de qualquer gravação (sem a
opção, conflito e nada gravado); `-SomenteLeitura` e `-Backups` são separados só na vírgula seguida de unidade e
conferidos antes de gravar; o perfil único do Ubuntu da 1.7.9 é aposentado; a linha do titular na âncora ganha os
namespaces `fundacao-abertura` e `fundacao-copia` (mesma chave, pelo UAC; I22); rodado sozinho, o perfil nega a edição
das origens registradas de todos os projetos (I21), e sem `-Backups` nem `-SemBackups` ele recusa no plano, com o comando
pronto (revisão da terceira rodada da integração, defeito 1). `preparar-projeto.ps1`: lê `registry/projetos-host.json`,
roda o preparar-maquina com as cópias de `-Backups` (sem elas, só com `-SemBackups` explícito, repassado; sem os dois,
ou só com espaços em `-Backups`, recusa antes de gravar, com o comando pronto: I21 e defeito 2), recusa com o Ubuntu
ligado e, com `-AssinarFicha`, chama a ferramenta fixa do titular; a pasta registrada que sumiu (de outro projeto:
aviso e Edit negado mesmo assim; do próprio: para) e o caminho só do Ubuntu (aviso). Revisão seguinte da terceira
rodada: a raiz de um disco vale como está e a pasta que contém a raiz é recusada (defeito 1); a cópia registrada em
`registry/ultima-copia.json` recusa o `-SemBackups` e põe a pasta no comando pronto, e `-BackupsAusente` nega as cópias
num disco desligado (defeito 2); a negação dada só na linha de comando vira pendência (defeito 3). PowerShell de
verdade, pastas descartáveis e chaves de ensaio (como o `test_host_windows`).
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from apoio import ENV, SKILL
from test_host_windows import POWERSHELL, SENHA_DE_ENSAIO, ELEVADO, _Base, fotografia, gerar_chave

PROJETO_PS1 = SKILL / "assets" / "host" / "windows" / "preparar-projeto.ps1"
SEM_PASTA = "'<pasta das cópias de segurança, em outro disco>'"  # o texto do comando pronto sem pasta conhecida


def outra_unidade(evitar: Path) -> str | None:
    """A raiz de um disco fixo desta máquina que não é o da pasta de ensaio ("E:\\"): -Backups nela não contém a raiz
    de ensaio e nada é gravado nela (o perfil só nega). Só disco fixo, sem rede nem removível; sem outro, None."""
    if os.name != "nt":
        return None
    letra = evitar.drive[:1].upper()
    for c in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        raiz = c + ":\\"
        if c != letra and ctypes.windll.kernel32.GetDriveTypeW(raiz) == 3 and os.path.isdir(raiz):
            return raiz
    return None


def registrar_copia(raiz: Path, destino) -> None:
    """registry/ultima-copia.json de ensaio, na forma que o backup criar do kit grava (fundacao.ultima_copia/1)."""
    dados = {"schema_version": "fundacao.ultima_copia/1", "rotulo": "semanal-2026-S44",
             "criada_em": "2026-10-30T10:00:00Z", "verificada_em": None, "destino": str(destino)}
    (raiz / "registry" / "ultima-copia.json").write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n",
                                                         encoding="utf-8", newline="\n")


@unittest.skipIf(ELEVADO, "o script recusa rodar elevado (código 2), por desenho: este ensaio exige a conta comum")
class TrocaDeProjeto(_Base):
    def setUp(self):
        super().setUp()
        gerar_chave(self.chave, SENHA_DE_ENSAIO)

    def test_troca_sem_a_opcao_e_recusada_antes_da_chave_e_sem_gravar(self):
        p, _rel = self.rodar("-SemUAC", "-Projeto", "caso-real")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        antes = {k: v for k, v in fotografia(self.raiz).items() if "evidence" not in k}
        p, rel = self.rodar("-SemUAC", "-Projeto", "lab-a")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        item = self.item(rel, "projeto")
        self.assertEqual((item["acao"], item["projeto_anterior"]), ("conflito", "caso-real"))
        self.assertIn("-TrocarProjeto", item["detalhe"])
        self.assertNotIn("chave", [i["id"] for i in rel["itens"]])  # o plano vem antes da chave e do UAC
        self.assertEqual({k: v for k, v in fotografia(self.raiz).items() if "evidence" not in k}, antes)

    def test_troca_com_a_opcao_simulada_e_real(self):
        self.rodar("-SemUAC", "-Projeto", "caso-real")
        antes = {k: v for k, v in fotografia(self.raiz).items() if "evidence" not in k}
        p, rel = self.rodar("-Simular", "-Projeto", "lab-a", "-TrocarProjeto")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.item(rel, "projeto")["acao"], "trocar")
        self.assertEqual({k: v for k, v in fotografia(self.raiz).items() if "evidence" not in k}, antes)
        p, rel = self.rodar("-SemUAC", "-Projeto", "lab-a", "-TrocarProjeto")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        win = json.loads((self.raiz / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(win["env"]["FUNDACAO_PROJECT"], "lab-a")
        self.assertIn("Read(./projects/caso-real/**)", win["permissions"]["deny"])
        anterior = Path(self.item(rel, "settings.json")["anterior"])
        self.assertEqual(json.loads(anterior.read_text(encoding="utf-8"))["env"]["FUNDACAO_PROJECT"], "caso-real")

    def test_projeto_da_1_7_9_no_settings_local_vai_ao_settings_json(self):
        claude = self.raiz / ".claude"
        claude.mkdir()
        (claude / "settings.local.json").write_text(json.dumps({"env": {"FUNDACAO_" + "PRINCIPAL": "titular",
                                                                        "FUNDACAO_PROJECT": "caso-real"}}),
                                                    encoding="utf-8")
        p, rel = self.rodar("-SemUAC", "-Projeto", "lab-a")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)  # o 1.7.9 já tinha outro projeto: troca explícita
        self.assertEqual(self.item(rel, "projeto")["acao"], "conflito")
        p, _rel = self.rodar("-SemUAC")  # sem -Projeto: mantém o que já estava gravado
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        win = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(win["env"]["FUNDACAO_PROJECT"], "caso-real")
        local = json.loads((claude / "settings.local.json").read_text(encoding="utf-8"))
        self.assertNotIn("FUNDACAO_PROJECT", local["env"])


@unittest.skipIf(ELEVADO, "o script recusa rodar elevado (código 2), por desenho: este ensaio exige a conta comum")
class PastasInformadas(_Base):
    def setUp(self):
        super().setUp()
        gerar_chave(self.chave, SENHA_DE_ENSAIO)
        self.a = self.base / "Origem A, com vírgula"
        self.b = self.base / "Origem B"
        self.a.mkdir()
        self.b.mkdir()

    def test_duas_pastas_juntas_pelo_file_sao_separadas_na_virgula_da_unidade(self):
        p, _rel = self.rodar("-SemUAC", "-Projeto", "caso-real", "-SomenteLeitura", f"{self.a},{self.b}")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        negadas = json.loads((self.raiz / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]
        for pasta in (self.a, self.b):
            self.assertTrue(any(r.startswith("Edit(//") and r.endswith("/" + pasta.name + "/**)") for r in negadas),
                            pasta.name)

    def test_pasta_inexistente_ou_dentro_da_raiz_recusa_sem_gravar(self):
        for valor, trecho in ((str(self.base / "nao-existe"), "inexistente"),
                              (str(self.raiz / "projects" / "lab-a"), "dentro da raiz"), ("relativa\\x", "absoluto")):
            for opcao in ("-SomenteLeitura", "-Backups"):
                with self.subTest(valor=valor, opcao=opcao):
                    p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", opcao, valor)
                    self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                    self.assertIn(trecho, rel["mensagem"])
                    self.assertFalse((self.raiz / ".claude").exists())

    def test_pasta_registrada_ausente_segue_negada_e_a_forma_e_conferida(self):
        """-SomenteLeituraAusente (o preparar-projeto.ps1 passa as pastas registradas que sumiram; reconferência do
        lote 2): a existência não é exigida, e a pasta sai com o Edit negado; a forma (unidade local, fora da raiz)
        segue conferida, e fora dela nada é gravado."""
        sumida = self.base / "Origem Sumida"
        p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", "-SomenteLeituraAusente", str(sumida))
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        negadas = json.loads((self.raiz / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]
        self.assertTrue(any(r.startswith("Edit(//") and r.endswith("/Origem Sumida/**)") for r in negadas), negadas)
        self.assertEqual(rel["somente_leitura_ausente"], [str(sumida)])
        antes = {k: v for k, v in fotografia(self.raiz).items() if "evidence" not in k}
        for valor, trecho in ((str(self.raiz / "projects" / "lab-a"), "dentro da raiz"), ("relativa\\x", "absoluto")):
            with self.subTest(valor=valor):
                p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", "-SomenteLeituraAusente", valor)
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIn(trecho, rel["mensagem"])
                self.assertEqual({k: v for k, v in fotografia(self.raiz).items() if "evidence" not in k}, antes)


@unittest.skipIf(ELEVADO, "o script recusa rodar elevado (código 2), por desenho: este ensaio exige a conta comum")
class CopiasNoPreparoDaMaquina(_Base):
    """Revisão da terceira rodada da integração, defeito 1: o portão da I21 (b) também no preparar-maquina.ps1. Ele
    refaz inteiro o .claude/settings.json e, rodado sozinho sem -Backups (o passo que a folha manda rodar por último, e
    que a I22 pede de novo a toda instalação da 1.7.10, pelo UAC da âncora), apagava em silêncio o Read e o Edit
    negados das cópias de segurança, que têm os dados de todos os projetos. Agora, sem -Backups e sem um -SemBackups
    explícito, recusa com código 2 no plano (antes da chave, do UAC e de qualquer gravação, também na simulação), com o
    motivo e o comando pronto; os dois juntos também. Defeito 2: decide pela lista conferida (-Backups só com espaços
    não é cópia). Contraprova: o script de antes saía com 3 e gravava o perfil sem as duas regras."""

    def setUp(self):
        super().setUp()
        gerar_chave(self.chave, SENHA_DE_ENSAIO)
        self.copias = self.base / "Copias IA"
        self.copias.mkdir()

    def negadas(self) -> list:
        return json.loads((self.raiz / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]

    def das_copias(self) -> list:
        return sorted(r for r in self.negadas() if r.endswith("/" + self.copias.name + "/**)"))

    def test_sem_backups_nem_sem_backups_recusa_no_plano_com_o_comando_pronto(self):
        p, _rel = self.rodar("-SemUAC", "-Projeto", "caso-real", "-Backups", str(self.copias))
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        regras = self.das_copias()
        self.assertEqual([r[:7] for r in regras], ["Edit(//", "Read(//"])
        antes = fotografia(self.raiz, self.base / "ProgramData", self.chave.parent)
        for modo in ("-SemUAC", "-Simular", "-WhatIf"):
            with self.subTest(modo=modo):
                p, rel = self.rodar(modo, "-Projeto", "caso-real", copias=())
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertEqual(fotografia(self.raiz, self.base / "ProgramData", self.chave.parent), antes)
                self.assertEqual(rel["itens"], [])  # o plano para antes da chave, do UAC e dos arquivos
                for trecho in ("-Backups", "-SemBackups", "Read e o Edit negados das cópias", "Nada foi alterado"):
                    self.assertIn(trecho, rel["mensagem"])
                comando = rel["comando_pronto"]
                self.assertTrue(comando.casefold().startswith(
                    f"powershell -ExecutionPolicy Bypass -File '{self.ps1}'".casefold()), comando)
                for trecho in (f"-Raiz '{self.raiz}'", "-Titular 'titular'", "-Projeto 'caso-real'", f" {modo}",
                               f"-Python '{sys.executable}'",
                               "-Backups '<pasta das cópias de segurança, em outro disco>'"):
                    self.assertIn(trecho, comando)
                self.assertNotIn("-SemBackups", comando)
                self.assertIn(f"-Raiz '{self.raiz}'", p.stdout)  # o comando pronto também sai na tela do titular
        self.assertEqual(self.das_copias(), regras)  # o perfil segue com as duas regras

    def test_o_comando_pronto_roda_com_a_pasta_no_lugar_do_texto(self):
        """Colado no PowerShell comum com a pasta das cópias no lugar do texto entre < >, o comando pronto roda e grava
        a negação das cópias (aqui sem o perfil do PowerShell de quem roda os testes)."""
        p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", copias=())
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        marca = "'<pasta das cópias de segurança, em outro disco>'"
        self.assertEqual(rel["comando_pronto"].count(marca), 1)
        pronto = rel["comando_pronto"].replace(marca, "'" + str(self.copias).replace("'", "''") + "'").replace(
            "powershell -ExecutionPolicy Bypass", "powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass", 1)
        r = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", pronto + "; exit $LASTEXITCODE"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, timeout=300)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual([x[:7] for x in self.das_copias()], ["Edit(//", "Read(//"])

    def test_juntos_ou_so_espacos_recusam_e_espacos_com_sem_backups_nao_sao_copia(self):
        antes = fotografia(self.raiz, self.base / "ProgramData")
        casos = ((("-Backups", " "), "falta -Backups"), (("-Backups", "   "), "falta -Backups"),
                 (("-Backups", str(self.copias), "-SemBackups"), "juntos"))
        for copias, trecho in casos:
            with self.subTest(copias=copias):
                p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", copias=copias)
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIn(trecho, rel["mensagem"])
                self.assertEqual(bool(rel["comando_pronto"]), trecho == "falta -Backups")
                self.assertEqual(fotografia(self.raiz, self.base / "ProgramData"), antes)
        # Só espaços com -SemBackups: a lista vazia nunca conta como cópia, e vale o -SemBackups.
        p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", copias=("-Backups", " ", "-SemBackups"))
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual((rel["backups"], rel["sem_backups"]), ([], True))
        self.assertFalse([r for r in self.negadas() if r.startswith("Read(//")])

    def test_sem_backups_explicito_grava_sem_as_copias_com_pendencia(self):
        p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", copias=("-SemBackups",))
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual((rel["backups"], rel["sem_backups"], rel["comando_pronto"]), ([], True, None))
        self.assertTrue(any("-SemBackups" in x and "-Backups" in x for x in rel["pendencias"]), rel["pendencias"])
        self.assertFalse([r for r in self.negadas() if r.startswith("Read(//")])
        p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", "-Backups", str(self.copias))
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual((rel["backups"], rel["sem_backups"]), ([str(self.copias)], False))
        self.assertFalse([x for x in rel["pendencias"] if "-SemBackups" in x], rel["pendencias"])


@unittest.skipIf(ELEVADO, "o script recusa rodar elevado (código 2), por desenho: este ensaio exige a conta comum")
class RaizDeDiscoNasPastas(_Base):
    """Revisão seguinte da terceira rodada da integração, defeito 1: o Get-PastasConferidas tirava a barra final também
    da raiz de um disco ("E:\\" virava "E:"), e o ajudante recusava "E:" (código 1, "pasta do Windows com unidade
    esperada"): quem guarda as cópias num disco só delas não tinha a negação delas por script nenhum. Agora a raiz do
    disco fica com a barra, e a comparação com a raiz da fundação é pelo texto sem a barra. A lacuna vizinha: a pasta que
    CONTÉM a raiz (a de cima, o disco da raiz) passava e negaria às sessões a própria fundação; agora é recusada, com o
    motivo, nas três listas. Contraprova: o script de antes devolvia "E:" e aceitava a pasta de cima."""

    def setUp(self):
        super().setUp()
        gerar_chave(self.chave, SENHA_DE_ENSAIO)

    def test_raiz_de_disco_fica_com_a_barra_e_a_pasta_que_contem_a_raiz_e_recusada(self):
        """Get-PastasConferidas por ponto, com a raiz da fundação numa unidade fictícia (Z:)."""
        def aspas(texto) -> str:
            return "'" + str(texto).replace("'", "''") + "'"

        dados = self.ps("\n".join([
            "$Raiz = 'Z:\\fundacao'",
            "$d = $env:SystemDrive + '\\'",
            "$a = Get-PastasConferidas -Valores @($d) -Rotulo '-Backups'",
            "$b = Get-PastasConferidas -Valores @($env:SystemDrive + '/') -Rotulo '-BackupsAusente' -AceitarAusente",
            f"$Raiz = {aspas(self.raiz)}",
            f"$c = Get-PastasConferidas -Valores @({aspas(self.base)}) -Rotulo '-Backups'",
            f"$e = Get-PastasConferidas -Valores @({aspas(self.raiz.anchor)}) -Rotulo '-SomenteLeitura'",
            f"$f = Get-PastasConferidas -Valores @({aspas(self.base)}) -Rotulo '-BackupsAusente' -AceitarAusente",
            f"$g = Get-PastasConferidas -Valores @({aspas(str(self.base) + chr(92))}) -Rotulo '-SomenteLeituraAusente' "
            "-AceitarAusente",
            f"$h = Get-PastasConferidas -Valores @({aspas(self.base / 'Fundacao Teste B')}) -Rotulo '-Backups' -AceitarAusente",
            "@{ disco = @($a.Lista); erro = $a.Erro; barra = @($b.Lista); acima = $c.Erro; disco_da_raiz = $e.Erro",
            "   ausente_acima = $f.Erro; acima_com_barra = $g.Erro; vizinha = @($h.Lista) } | ConvertTo-Json -Compress"]))
        unidade = os.environ.get("SystemDrive", "C:") + "\\"
        self.assertEqual((dados["disco"], dados["erro"], dados["barra"]), ([unidade], None, [unidade]))
        for chave, rotulo in (("acima", "-Backups"), ("disco_da_raiz", "-SomenteLeitura"),
                              ("ausente_acima", "-BackupsAusente"), ("acima_com_barra", "-SomenteLeituraAusente")):
            with self.subTest(chave):
                self.assertTrue(dados[chave] and dados[chave].startswith(rotulo + ": a pasta contém a raiz"), dados[chave])
        # A vizinha que só começa com o mesmo nome ("Fundacao Teste B") não contém a raiz: passa.
        self.assertEqual(dados["vizinha"], [str(self.base / "Fundacao Teste B")])

    def test_pasta_que_contem_a_raiz_recusa_sem_gravar(self):
        antes = fotografia(self.raiz, self.base / "ProgramData", self.chave.parent)
        for opcao, valor in (("-Backups", str(self.base)), ("-SomenteLeitura", str(self.base)),
                             ("-BackupsAusente", str(self.base)), ("-Backups", self.raiz.anchor)):
            with self.subTest(opcao=opcao, valor=valor):
                p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", opcao, valor,
                                    copias=() if opcao.startswith("-Backups") else ("-SemBackups",))
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIn("contém a raiz", rel["mensagem"])
                self.assertEqual(fotografia(self.raiz, self.base / "ProgramData", self.chave.parent), antes)

    def test_disco_so_das_copias_vai_ao_perfil(self):
        unidade = outra_unidade(self.base)
        if not unidade:
            self.skipTest("esta máquina não tem outro disco fixo além do da pasta de ensaio")
        p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", "-Backups", unidade)
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual(rel["backups"], [unidade])
        negadas = json.loads((self.raiz / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]
        letra = unidade[0].lower()
        for regra in (f"Read(//{letra}/**)", f"Edit(//{letra}/**)"):
            self.assertIn(regra, negadas)


@unittest.skipIf(ELEVADO, "o script recusa rodar elevado (código 2), por desenho: este ensaio exige a conta comum")
class CopiaRegistrada(_Base):
    """Revisão seguinte da terceira rodada da integração, defeito 2: o -SemBackups ("ainda não há cópias") era aceito às
    cegas, e -Backups exigia a pasta existente, sem equivalente do -SomenteLeituraAusente: com o disco das cópias
    desligado, a única saída era o -SemBackups, e o perfil saía sem o Read e o Edit negados delas. Agora o plano lê
    registry/ultima-copia.json pelo ajudante (como o aviso_copia.py: sem seguir ligação, até 64 KiB): com destino
    registrado, o -SemBackups é recusado (código 2, nada gravado) e o comando pronto traz a pasta de cima do destino no
    lugar do texto entre < > (-Backups se ela existe, -BackupsAusente se não). O registro só recusa e sugere, nunca
    aceita: forjado, a pasta que não passa nas regras de -Backups não é sugerida, e o registro ilegível só deixa a
    pendência. -BackupsAusente nega a leitura e a edição da pasta que não existe agora (só a forma é conferida).
    Contraprova: o script de antes saía com 3 e gravava o perfil sem a negação das cópias registradas."""

    def setUp(self):
        super().setUp()
        gerar_chave(self.chave, SENHA_DE_ENSAIO)
        self.copias = self.base / "Copias IA"
        self.copias.mkdir()

    def negadas(self) -> list:
        return json.loads((self.raiz / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]

    def test_sem_backups_recusado_e_o_comando_pronto_traz_a_pasta_e_roda(self):
        destino = self.copias / "semanal-2026-S44"
        registrar_copia(self.raiz, destino)
        antes = fotografia(self.raiz, self.base / "ProgramData", self.chave.parent)
        for modo in ("-SemUAC", "-Simular"):
            with self.subTest(modo=modo):
                p, rel = self.rodar(modo, "-Projeto", "caso-real", copias=("-SemBackups",))
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertEqual(fotografia(self.raiz, self.base / "ProgramData", self.chave.parent), antes)
                self.assertEqual(rel["itens"], [])  # no plano, antes da chave, do UAC e dos arquivos
                for trecho in ("-SemBackups recusado", str(destino), "registry\\ultima-copia.json", "Nada foi alterado"):
                    self.assertIn(trecho, rel["mensagem"])
                self.assertEqual((rel["ultima_copia"]["registro"], rel["pasta_sugerida"]), ("lido", str(self.copias)))
                comando = rel["comando_pronto"]
                self.assertIn("-Backups '" + str(self.copias).replace("'", "''") + "'", comando)
                self.assertNotIn(SEM_PASTA, comando)
                self.assertNotIn("-SemBackups", comando)
                self.assertIn("registry\\ultima-copia.json: confira", p.stdout)  # a tela diz de onde veio a pasta
        p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", copias=())  # sem nenhum dos dois: a mesma pasta
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("falta -Backups", rel["mensagem"])
        self.assertIn(str(destino), rel["mensagem"])
        pronto = rel["comando_pronto"].replace("powershell -ExecutionPolicy Bypass",
                                               "powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass", 1)
        r = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", pronto + "; exit $LASTEXITCODE"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, timeout=300)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)  # colado como está, sem trocar nada
        das_copias = sorted(x[:7] for x in self.negadas() if x.endswith("/" + self.copias.name + "/**)"))
        self.assertEqual(das_copias, ["Edit(//", "Read(//"])

    def test_disco_das_copias_desligado_vai_com_backups_ausente(self):
        desligada = self.base / "Copias Desligadas"  # não existe: o disco das cópias está desligado
        registrar_copia(self.raiz, desligada / "semanal-2026-S44")
        p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", copias=("-SemBackups",))
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("-BackupsAusente '" + str(desligada) + "'", rel["comando_pronto"])
        antes = fotografia(self.raiz, self.base / "ProgramData")
        p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", copias=("-Backups", str(desligada)))
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        for trecho in ("inexistente", "-BackupsAusente"):  # a recusa da pasta inexistente aponta a saída
            self.assertIn(trecho, rel["mensagem"])
        self.assertEqual(fotografia(self.raiz, self.base / "ProgramData"), antes)
        p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", copias=("-BackupsAusente", str(desligada)))
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual((rel["backups"], rel["backups_ausentes"], rel["sem_backups"]), ([], [str(desligada)], False))
        das_copias = sorted(x[:7] for x in self.negadas() if x.endswith("/" + desligada.name + "/**)"))
        self.assertEqual(das_copias, ["Edit(//", "Read(//"])
        self.assertFalse([x for x in rel["pendencias"] if "-SemBackups" in x or "fica fora" in x], rel["pendencias"])
        antes = fotografia(self.raiz, self.base / "ProgramData")
        for valor, trecho in ((str(self.raiz / "projects" / "lab-a"), "dentro da raiz"), ("relativa\\x", "absoluto"),
                              (str(desligada) + "," + str(self.copias), "juntos")):
            with self.subTest(valor=valor):  # a forma segue conferida; com -SemBackups, juntos
                extra = ("-SemBackups",) if trecho == "juntos" else ()
                p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", copias=("-BackupsAusente", valor, *extra))
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIn(trecho, rel["mensagem"])
                self.assertEqual(fotografia(self.raiz, self.base / "ProgramData"), antes)

    def test_registro_forjado_so_recusa_e_nunca_vira_argumento(self):
        """Uma sessão grava registry/: com o destino dentro da raiz ou na pasta que contém a raiz, o -SemBackups é
        recusado, mas a pasta não é sugerida (fica o texto entre < >); com aspas no destino (que quebrariam o argumento
        do comando pronto), o ajudante recusa o registro, o -SemBackups vale e a pendência diz por quê."""
        for destino in (self.raiz / "projects" / "caso-real" / "semanal", self.base / "semanal"):
            with self.subTest(destino=str(destino)):
                registrar_copia(self.raiz, destino)
                p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", copias=("-SemBackups",))
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIn("-SemBackups recusado", rel["mensagem"])
                self.assertIn(SEM_PASTA, rel["comando_pronto"])
                self.assertIsNone(rel["pasta_sugerida"])
        registrar_copia(self.raiz, "E:\\Copias\" -Python \"C:\\Outro\\python.exe")
        p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", copias=("-SemBackups",))
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual((rel["ultima_copia"]["registro"], rel["comando_pronto"]), ("recusado", None))
        pendencias = [x for x in rel["pendencias"] if "ultima-copia.json" in x]
        self.assertEqual(len(pendencias), 1, rel["pendencias"])
        self.assertIn("recusado", pendencias[0])
        self.assertNotIn("Outro", pendencias[0])  # o motivo não traz o conteúdo do arquivo

    def test_copia_registrada_fora_das_pastas_dadas_vira_pendencia(self):
        destino = self.copias / "semanal-2026-S44"
        registrar_copia(self.raiz, destino)
        outra = self.base / "Outras Copias"
        outra.mkdir()
        p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", copias=("-Backups", str(outra)))
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertTrue(any(str(destino) in x and "fica fora" in x for x in rel["pendencias"]), rel["pendencias"])
        p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real", copias=("-Backups", f"{outra},{self.copias}"))
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertFalse([x for x in rel["pendencias"] if "fica fora" in x], rel["pendencias"])


@unittest.skipIf(ELEVADO, "o script recusa rodar elevado (código 2), por desenho: este ensaio exige a conta comum")
class PerfilUnicoAposentado(_Base):
    def test_settings_wsl_da_1_7_9_vai_para_anteriores(self):
        gerar_chave(self.chave, SENHA_DE_ENSAIO)
        claude = self.raiz / ".claude"
        claude.mkdir()
        (claude / "settings.wsl.json").write_text('{"perfil": "1.7.9"}\n', encoding="utf-8")
        p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        item = self.item(rel, "settings.wsl.json")
        self.assertEqual(item["acao"], "aposentar")
        self.assertFalse((claude / "settings.wsl.json").exists())
        self.assertEqual(Path(item["anterior"]).read_text(encoding="utf-8"), '{"perfil": "1.7.9"}\n')


class AncoraComNamespaceDaFicha(_Base):
    def test_mesma_chave_sem_fundacao_abertura_e_trocada_sem_conflito(self):
        publica = gerar_chave(self.chave, SENHA_DE_ENSAIO)
        outra = gerar_chave(self.base / "ssh" / "outra", SENHA_DE_ENSAIO)
        antiga = 'titular namespaces="fundacao-decisao" ' + publica
        nova = 'titular namespaces="fundacao-decisao,fundacao-abertura" ' + publica
        alheia = 'revisor namespaces="fundacao-decisao" ' + outra
        casos = [("namespaces", ["# comentário", antiga, alheia], ["# comentário", nova, alheia]),
                 ("igual", [nova], [nova]),
                 ("igual", ["titular " + publica], ["titular " + publica]),  # sem namespaces=: vale para todos
                 ("conflito", ['titular namespaces="fundacao-decisao" ' + outra],
                  ['titular namespaces="fundacao-decisao" ' + outra])]
        for acao, linhas, esperado in casos:
            with self.subTest(acao=acao, linhas=len(linhas)):
                lista = ", ".join("'" + l.replace("'", "''") + "'" for l in linhas)
                dados = self.ps(f"$r = Merge-Ancora -Linhas @({lista}) -Titular 'titular' -LinhaNova '{nova}'\n"
                                "@{ acao = $r.Acao; linhas = @($r.Linhas) } | ConvertTo-Json -Compress")
                self.assertEqual(dados["acao"], acao)
                self.assertEqual(dados["linhas"], esperado)

    def test_linha_sem_fundacao_copia_e_trocada_pela_nova_e_a_com_os_tres_fica(self):
        """Folha da integração, I22: o livro de cópias assinado (core/livro_assinado.py) confere em fundacao-copia
        contra a mesma âncora. A linha nova é a do próprio script (Get-LinhaAncora, com o $NAMESPACES); a da mesma chave
        sem um dos três (a da 1.7.9 e a da 1.7.10 de antes) é trocada por ela, com a mesma chave e sem conflito (a ação
        'namespaces', que pede o UAC como as outras); a que já tem os três (ou mais) fica igual. Contraprova: com o
        $NAMESPACES de antes, a linha da 1.7.10 dava 'igual' e a nova não tinha fundacao-copia."""
        publica = gerar_chave(self.chave, SENHA_DE_ENSAIO)
        outra = gerar_chave(self.base / "ssh" / "outra", SENHA_DE_ENSAIO)
        nova = 'titular namespaces="fundacao-decisao,fundacao-abertura,fundacao-copia" ' + publica
        da_179 = 'titular namespaces="fundacao-decisao" ' + publica
        da_1710 = 'titular namespaces="fundacao-decisao,fundacao-abertura" ' + publica
        com_mais = 'titular namespaces="fundacao-copia,fundacao-abertura,fundacao-decisao,outro" ' + publica
        alheia = 'revisor namespaces="fundacao-decisao" ' + outra
        casos = [("namespaces", ["# comentário", da_179, alheia], ["# comentário", nova, alheia]),
                 ("namespaces", [alheia, da_1710], [alheia, nova]),
                 ("igual", [nova], [nova]),
                 ("igual", [com_mais], [com_mais]),
                 ("conflito", ['titular namespaces="fundacao-decisao,fundacao-abertura" ' + outra],
                  ['titular namespaces="fundacao-decisao,fundacao-abertura" ' + outra])]
        for acao, linhas, esperado in casos:
            with self.subTest(acao=acao, linhas=len(linhas)):
                lista = ", ".join("'" + l.replace("'", "''") + "'" for l in linhas)
                dados = self.ps(f"$n = Get-LinhaAncora -Titular 'titular' -LinhaPublica '{publica}'\n"
                                f"$r = Merge-Ancora -Linhas @({lista}) -Titular 'titular' -LinhaNova $n\n"
                                "@{ nova = $n; acao = $r.Acao; linhas = @($r.Linhas) } | ConvertTo-Json -Compress")
                self.assertEqual(dados["nova"], nova)
                self.assertEqual(dados["acao"], acao)
                self.assertEqual(dados["linhas"], esperado)


@unittest.skipIf(ELEVADO, "o script recusa rodar elevado (código 2), por desenho: este ensaio exige a conta comum")
class AncoraSemFundacaoCopia(_Base):
    def test_linha_da_1_7_10_pede_o_uac_e_sem_ele_a_ancora_nao_muda(self):
        """I22, no preparo de verdade: a âncora com a linha da 1.7.10 de antes (sem fundacao-copia) não confere; a
        simulação mostra a troca (o detalhe diz o que falta), e o -SemUAC a deixa pendente, sem tocar no arquivo: a
        troca é feita só pela etapa de administrador, no mesmo UAC da âncora. Contraprova: com o $NAMESPACES de antes,
        a linha da 1.7.10 conferia (conteudo_confere verdadeiro) e o detalhe não falava em fundacao-copia."""
        publica = gerar_chave(self.chave, SENHA_DE_ENSAIO)
        self.ancora.parent.mkdir(parents=True)
        self.ancora.write_bytes(('titular namespaces="fundacao-decisao,fundacao-abertura" ' + publica + "\r\n").encode())
        antes = self.ancora.read_bytes()
        p, rel = self.rodar("-Simular", "-Projeto", "caso-real")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        item = self.item(rel, "ancora")
        self.assertEqual((item["acao"], item["conteudo_confere"]), ("atualizar", False))
        self.assertIn("fundacao-copia", item["detalhe"])
        p, rel = self.rodar("-SemUAC", "-Projeto", "caso-real")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual(self.item(rel, "ancora")["acao"], "pendente_admin")
        self.assertEqual(self.ancora.read_bytes(), antes)


@unittest.skipIf(ELEVADO, "o script recusa rodar elevado (código 2), por desenho: este ensaio exige a conta comum")
class PrepararProjeto(_Base):
    def setUp(self):
        super().setUp()
        gerar_chave(self.chave, SENHA_DE_ENSAIO)
        self.ps1_projeto = self.ps1.parent / "preparar-projeto.ps1"
        self.origem = self.base / "Origem Registrada"
        self.origem.mkdir()
        r = subprocess.run([sys.executable, "-I", "-B", str(SKILL / "assets" / "host" / "preparo_host.py"),
                            "registrar-projeto", "--raiz", str(self.raiz), "--projeto", "caso-real", "--origem",
                            str(self.origem), "--negar-skill", "squad-aninhada"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=ENV, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def projeto(self, *args, projeto: str = "caso-real", copias=("-SemBackups",)):
        """`copias`: -Backups <pastas> ou -SemBackups (I21: sem nenhum dos dois, o script recusa antes de gravar). Os
        testes de antes da I21 rodam com -SemBackups explícito, o comportamento que eles tinham (nunca -Backups)."""
        self.n += 1
        rel = self.base / f"projeto-{self.n}.json"
        cmd = [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(self.ps1_projeto),
               "-Raiz", str(self.raiz), "-Titular", "titular", "-Projeto", projeto, "-Chave", str(self.chave),
               "-Ancora", str(self.ancora), "-Ferramentas", str(self.ferramentas), "-Python", sys.executable,
               "-Distribuicao", "Ensaio-Sem-Distro",
               "-Relatorio", str(rel), *map(str, copias), *map(str, args)]
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV,
                           timeout=300)
        return p, (json.loads(rel.read_text(encoding="utf-8")) if rel.is_file() else None)

    def test_simulacao_le_o_registro_e_nao_grava_nada(self):
        antes = fotografia(self.raiz)
        p, rel = self.projeto("-Simular")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(fotografia(self.raiz), antes)
        self.assertEqual(rel["somente_leitura"], [str(self.origem)])
        self.assertEqual(rel["preparar_maquina"]["codigo"], 0)
        self.assertFalse(rel["ubuntu"]["ligado"])
        for trecho in ("preparar-wsl.sh", "--projeto caso-real", "--titular titular", "--perfil-windows"):
            self.assertIn(trecho, rel["proximo_passo"])

    def test_grava_o_perfil_com_a_origem_e_a_negacao_do_registro_sem_backups(self):
        p, rel = self.projeto("-SemUAC")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        win = json.loads((self.raiz / ".claude" / "settings.json").read_text(encoding="utf-8"))
        # revisão do lote 2: o -Projeto daqui é o da sessão do Ubuntu; o das sessões do Windows só com -ProjetoWindows
        self.assertNotIn("FUNDACAO_PROJECT", win["env"])
        self.assertIn("Skill(squad-aninhada)", win["permissions"]["deny"])
        self.assertTrue(any(r.startswith("Edit(//") and r.endswith("/Origem Registrada/**)")
                            for r in win["permissions"]["deny"]))
        self.assertFalse([r for r in win["permissions"]["deny"] if r.startswith("Read(//")])  # nada de -Backups
        maquina = json.loads(Path(rel["preparar_maquina"]["relatorio"]).read_text(encoding="utf-8"))
        self.assertEqual(maquina["codigo"], 3)

    def test_sem_backups_nem_sem_backups_recusa_antes_de_gravar_com_o_comando_pronto(self):
        """Folha da integração, I21 (b): o .claude/settings.json é refeito inteiro por cada script, e o
        preparar-projeto.ps1 nunca repassava -Backups: o perfil que ele gravava perdia o Read e o Edit negados das
        cópias, que têm os dados de todos os projetos. Sem -Backups e sem -SemBackups, recusa com código 2 antes de
        gravar qualquer coisa, também na simulação, com o motivo e o comando pronto com -Backups (os mesmos parâmetros
        dados). Contraprova: o script de antes saía com 0 na simulação e gravava o perfil sem as cópias (código 3)."""
        antes = fotografia(self.raiz, self.base / "ProgramData")
        for modo in ("-Simular", "-SemUAC"):
            with self.subTest(modo=modo):
                p, rel = self.projeto(modo, "-ProjetoWindows", "caso-real", copias=())
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertEqual(fotografia(self.raiz, self.base / "ProgramData"), antes)
                self.assertIsNone(rel["preparar_maquina"])  # o preparar-maquina.ps1 nem rodou
                for trecho in ("-Backups", "-SemBackups", "Read e o Edit negados das cópias", "Nada foi alterado"):
                    self.assertIn(trecho, rel["mensagem"])
                comando = rel["comando_pronto"]
                self.assertTrue(comando.casefold().startswith(
                    f"powershell -ExecutionPolicy Bypass -File '{self.ps1_projeto}'".casefold()), comando)
                for trecho in (f"-Raiz '{self.raiz}'", "-Titular 'titular'", "-Projeto 'caso-real'",
                               "-ProjetoWindows 'caso-real'", f" {modo}", f"-Python '{sys.executable}'",
                               "-Backups '<pasta das cópias de segurança, em outro disco>'"):
                    self.assertIn(trecho, comando)
                self.assertNotIn("-SemBackups", comando)
                self.assertIn(f"-Raiz '{self.raiz}'", p.stdout)  # o comando pronto também sai na tela do titular

    def test_backups_conferidos_e_repassados_ao_preparar_maquina(self):
        """I21 (b): -Backups passa pela mesma função do preparar-maquina.ps1 (vírgula seguida de unidade, pasta
        existente, disco local, fora da raiz) e é repassado a ele: o perfil gravado nega a leitura e a edição das
        cópias. A simulação mostra as pastas e não grava nada."""
        a, b = self.base / "Copias A, com vírgula", self.base / "Copias B"
        a.mkdir()
        b.mkdir()
        antes = fotografia(self.raiz)
        p, rel = self.projeto("-Simular", copias=("-Backups", f"{a},{b}"))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(rel["backups"], [str(a), str(b)])
        self.assertEqual(fotografia(self.raiz), antes)
        p, rel = self.projeto("-SemUAC", copias=("-Backups", f"{a},{b}"))
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual((rel["backups"], rel["sem_backups"]), ([str(a), str(b)], False))
        self.assertFalse(any("-SemBackups" in aviso for aviso in rel["avisos"]), rel["avisos"])
        negadas = json.loads((self.raiz / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]
        for pasta in (a, b):
            for regra in ("Read(//", "Edit(//"):
                self.assertTrue(any(r.startswith(regra) and r.endswith("/" + pasta.name + "/**)") for r in negadas),
                                (regra, pasta.name, negadas))

    def test_backups_fora_da_regra_ou_junto_com_sem_backups_recusa_sem_gravar(self):
        antes = fotografia(self.raiz, self.base / "ProgramData")
        casos = ((("-Backups", str(self.base / "nao-existe")), "inexistente"),
                 (("-Backups", str(self.raiz / "projects" / "lab-a")), "dentro da raiz"),
                 (("-Backups", "relativa\\x"), "absoluto"),
                 (("-Backups", str(self.origem), "-SemBackups"), "juntos"))
        for copias, trecho in casos:
            with self.subTest(trecho=trecho):
                p, rel = self.projeto("-SemUAC", copias=copias)
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIn(trecho, rel["mensagem"])
                self.assertIsNone(rel["preparar_maquina"])
                self.assertEqual(fotografia(self.raiz, self.base / "ProgramData"), antes)

    def test_preparar_maquina_sozinho_depois_do_projeto_com_backups_nao_apaga_as_copias(self):
        """Revisão da terceira rodada da integração, defeito 1, a sequência da sonda: o preparar-projeto.ps1 com
        -Backups grava o Read e o Edit negados das cópias; o preparar-maquina.ps1 rodado depois, sozinho, sem -Backups
        nem -SemBackups, recusa no plano (código 2), não grava nada e mostra o comando pronto com -Backups.
        Contraprova: o script de antes saía com 3 (settings.json 'atualizar', sem detalhe) e as duas regras sumiam."""
        copias = self.base / "Copias IA"
        copias.mkdir()
        p, _rel = self.projeto("-SemUAC", copias=("-Backups", str(copias)))
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        perfil = self.raiz / ".claude" / "settings.json"

        def das_copias() -> list:
            negadas = json.loads(perfil.read_text(encoding="utf-8"))["permissions"]["deny"]
            return sorted(r for r in negadas if r.endswith("/" + copias.name + "/**)"))

        regras = das_copias()
        self.assertEqual([r[:7] for r in regras], ["Edit(//", "Read(//"])
        antes = fotografia(self.raiz, self.base / "ProgramData")
        p, rel = self.rodar("-SemUAC", copias=())  # o preparar-maquina.ps1 sozinho, como a folha manda rodar
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertEqual(fotografia(self.raiz, self.base / "ProgramData"), antes)
        self.assertIn("-Backups '<pasta das cópias de segurança, em outro disco>'", rel["comando_pronto"])
        self.assertEqual(das_copias(), regras)

    def test_backups_so_de_espacos_nao_contam_como_copias(self):
        """Revisão da terceira rodada da integração, defeito 2: o portão olhava o valor cru de -Backups, e ' ' contava
        como "tem cópias"; a conferência devolvia a lista vazia e o perfil saía sem a negação delas (código 3, sem o
        aviso do -SemBackups). Agora decide pela lista conferida: só espaços (também a lista ' ',' ', que só passa pela
        linha de comando do PowerShell) é a falta de -Backups: código 2, o comando pronto e nada gravado. Com
        -SemBackups, vale o -SemBackups, com o aviso."""
        antes = fotografia(self.raiz, self.base / "ProgramData")
        for valor in (" ", "   "):
            with self.subTest(valor=repr(valor)):
                p, rel = self.projeto("-SemUAC", copias=("-Backups", valor))
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIsNone(rel["preparar_maquina"])
                self.assertIn("falta -Backups", rel["mensagem"])
                self.assertTrue(rel["comando_pronto"])
                self.assertEqual(fotografia(self.raiz, self.base / "ProgramData"), antes)

        def aspas(texto) -> str:
            return "'" + str(texto).replace("'", "''") + "'"

        rel_arq = self.base / "projeto-lista-de-espacos.json"
        comando = (f"& {aspas(self.ps1_projeto)} -Raiz {aspas(self.raiz)} -Titular titular -Projeto caso-real "
                   f"-Chave {aspas(self.chave)} -Ancora {aspas(self.ancora)} -Ferramentas {aspas(self.ferramentas)} "
                   f"-Python {aspas(sys.executable)} -Distribuicao Ensaio-Sem-Distro -Relatorio {aspas(rel_arq)} "
                   "-SemUAC -Backups ' ',' '; exit $LASTEXITCODE")
        p = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
                            comando], capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV,
                           timeout=300)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        rel = json.loads(rel_arq.read_text(encoding="utf-8"))
        self.assertIsNone(rel["preparar_maquina"])
        self.assertIn("falta -Backups", rel["mensagem"])
        self.assertEqual(fotografia(self.raiz, self.base / "ProgramData"), antes)
        p, rel = self.projeto("-SemUAC", copias=("-Backups", " ", "-SemBackups"))
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual((rel["backups"], rel["sem_backups"]), ([], True))
        self.assertTrue(any("-SemBackups" in a for a in rel["avisos"]), rel["avisos"])
        win = json.loads((self.raiz / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertFalse([r for r in win["permissions"]["deny"] if r.startswith("Read(//")])

    def test_sem_backups_explicito_segue_com_aviso_e_sem_a_negacao_das_copias(self):
        p, rel = self.projeto("-SemUAC")  # copias: -SemBackups (o padrão do auxiliar)
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual((rel["backups"], rel["sem_backups"]), ([], True))
        self.assertTrue(any("-SemBackups" in a and "por último" in a for a in rel["avisos"]), rel["avisos"])
        win = json.loads((self.raiz / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertFalse([r for r in win["permissions"]["deny"] if r.startswith("Read(//")])

    def test_preparar_maquina_sozinho_nega_a_edicao_das_origens_registradas(self):
        """Folha da integração, I21 (a): o perfil do Windows é um só e é refeito inteiro; o preparar-maquina.ps1 rodado
        sozinho, sem -SomenteLeitura, deixava gravável a origem registrada. O ajudante (perfil-windows) soma ao Edit
        negado as origens e as pastas só de leitura de TODOS os projetos de registry/projetos-host.json (a do Ubuntu em
        /mnt/<x> vira a pasta do Windows); o caminho só do Ubuntu fica de fora. Contraprova: o ajudante de antes
        gerava o perfil sem o Edit negado das duas pastas."""
        leitura = self.base / "Leitura Lab"
        leitura.mkdir()
        vista_do_wsl = "/mnt/" + leitura.drive[0].lower() + leitura.as_posix()[2:]
        registro = self.raiz / "registry" / "projetos-host.json"
        dados = json.loads(registro.read_text(encoding="utf-8"))
        dados["projetos"]["lab-a"] = {"origens": ["/home/ensaio/origem-lab"], "somente_leitura": [vista_do_wsl],
                                      "aninhadas_negadas": []}
        registro.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        p, _rel = self.rodar("-SemUAC", "-Projeto", "caso-real")  # o preparar-maquina.ps1, sem -SomenteLeitura
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        negadas = json.loads((self.raiz / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]
        edicao = [r for r in negadas if r.startswith("Edit(//")]
        for pasta in (self.origem, leitura):
            self.assertTrue(any(r.endswith("/" + pasta.name + "/**)") for r in edicao), (pasta.name, edicao))
        self.assertFalse([r for r in negadas if "origem-lab" in r])
        self.assertFalse([r for r in negadas if r.startswith("Read(//")])  # só a edição: a origem segue legível

    def test_disco_so_das_copias_e_repassado_com_a_barra(self):
        """Revisão seguinte da terceira rodada da integração, defeito 1: o preparar-projeto.ps1 tirava a barra de "E:\\",
        e o preparar-maquina.ps1, ao conferir de novo a lista repassada, recusava "E:" (código 2, com o texto enganoso
        "caminho absoluto num disco local esperado"). Agora a raiz do disco vai como está, e o perfil nega a leitura e a
        edição do disco inteiro. A pasta que contém a raiz é recusada antes de rodar o preparar-maquina.ps1."""
        antes = fotografia(self.raiz, self.base / "ProgramData")
        for copias in (("-Backups", str(self.base)), ("-BackupsAusente", str(self.base)), ("-Backups", self.raiz.anchor)):
            with self.subTest(copias=copias):
                p, rel = self.projeto("-SemUAC", copias=copias)
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIn("contém a raiz", rel["mensagem"])
                self.assertIsNone(rel["preparar_maquina"])
                self.assertEqual(fotografia(self.raiz, self.base / "ProgramData"), antes)
        unidade = outra_unidade(self.base)
        if not unidade:
            self.skipTest("esta máquina não tem outro disco fixo além do da pasta de ensaio")
        p, rel = self.projeto("-SemUAC", copias=("-Backups", unidade))
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual(rel["backups"], [unidade])
        maquina = json.loads(Path(rel["preparar_maquina"]["relatorio"]).read_text(encoding="utf-8"))
        self.assertEqual(maquina["backups"], [unidade])
        negadas = json.loads((self.raiz / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]
        letra = unidade[0].lower()
        for regra in (f"Read(//{letra}/**)", f"Edit(//{letra}/**)"):
            self.assertIn(regra, negadas)

    def test_copia_registrada_recusa_o_sem_backups_e_o_backups_ausente_e_repassado(self):
        """Revisão seguinte da terceira rodada da integração, defeito 2, no preparo do projeto: com a cópia registrada
        em registry/ultima-copia.json, o -SemBackups é recusado antes de rodar o preparar-maquina.ps1 (código 2, nada
        gravado), com o comando pronto deste script e a pasta das cópias; -BackupsAusente (o disco das cópias
        desligado) é conferido pela forma e repassado, e o perfil nega a leitura e a edição da pasta."""
        copias = self.base / "Copias IA"
        copias.mkdir()
        registrar_copia(self.raiz, copias / "semanal-2026-S44")
        antes = fotografia(self.raiz, self.base / "ProgramData")
        p, rel = self.projeto("-SemUAC")  # copias: -SemBackups (o padrão do auxiliar)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIsNone(rel["preparar_maquina"])
        self.assertEqual(fotografia(self.raiz, self.base / "ProgramData"), antes)
        self.assertIn("-SemBackups recusado", rel["mensagem"])
        comando = rel["comando_pronto"]
        self.assertTrue(comando.casefold().startswith(
            f"powershell -ExecutionPolicy Bypass -File '{self.ps1_projeto}'".casefold()), comando)
        self.assertIn(f"-Backups '{copias}'", comando)
        self.assertNotIn("-SemBackups", comando)
        self.assertEqual(rel["pasta_sugerida"], str(copias))
        desligada = self.base / "Copias Desligadas"
        p, rel = self.projeto("-SemUAC", copias=("-BackupsAusente", str(desligada)))
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual((rel["backups"], rel["backups_ausentes"]), ([], [str(desligada)]))
        maquina = json.loads(Path(rel["preparar_maquina"]["relatorio"]).read_text(encoding="utf-8"))
        self.assertEqual(maquina["backups_ausentes"], [str(desligada)])
        negadas = json.loads((self.raiz / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]
        self.assertEqual(sorted(x[:7] for x in negadas if x.endswith("/" + desligada.name + "/**)")),
                         ["Edit(//", "Read(//"])
        # A cópia registrada fica fora da pasta dada: aviso, com a pasta dela.
        self.assertTrue(any("fica fora" in a and str(copias) in a for a in rel["avisos"]), rel["avisos"])
        p, rel = self.projeto("-SemUAC", copias=("-Backups", str(desligada)))  # a pasta inexistente aponta a saída
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("-BackupsAusente", rel["mensagem"])

    def test_negacao_so_da_linha_de_comando_vira_pendencia(self):
        """Revisão seguinte da terceira rodada da integração, defeito 3: uma negação dada só na linha de comando do
        preparar-maquina.ps1 (-SomenteLeitura de pasta fora do registro, -NegarSkill de nome que nenhum projeto
        registrou) sumia em silêncio no próximo preparar-projeto.ps1, que refaz o perfil só com o registro. Agora vira
        pendência, no relatório e na tela, com o que fazer; o que o registro cobre (a origem, uma subpasta dela, a skill
        registrada) não. A última parte mostra que a pendência diz a verdade: o preparo do projeto tira as duas."""
        sub = self.origem / "sub"
        sub.mkdir()
        p, rel = self.rodar("-SemUAC", "-SomenteLeitura", f"{self.origem},{sub}", "-NegarSkill", "squad-aninhada")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual(rel["negacoes_fora_do_registro"], {"somente_leitura": [], "negar_skill": []})
        self.assertFalse([x for x in rel["pendencias"] if "linha de comando" in x], rel["pendencias"])
        solta = self.base / "Leitura Solta"
        solta.mkdir()
        p, rel = self.rodar("-SemUAC", "-SomenteLeitura", str(solta), "-NegarSkill", "squad-aninhada,squad-solta")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual(rel["negacoes_fora_do_registro"], {"somente_leitura": [str(solta)], "negar_skill": ["squad-solta"]})
        pendencias = [x for x in rel["pendencias"] if "linha de comando" in x]
        self.assertEqual(len(pendencias), 1, rel["pendencias"])
        for trecho in (str(solta), "-NegarSkill squad-solta", "preparar-projeto.ps1", "registrar-projeto", "por último"):
            self.assertIn(trecho, pendencias[0])
        self.assertNotIn("squad-aninhada", pendencias[0])
        self.assertIn("Pendente: estas nega", p.stdout)  # também na tela do titular
        negadas = json.loads((self.raiz / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]
        self.assertIn("Skill(squad-solta)", negadas)
        self.assertTrue(any(r.endswith("/Leitura Solta/**)") for r in negadas))
        p, _rel = self.projeto("-SemUAC")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        negadas = json.loads((self.raiz / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]
        self.assertNotIn("Skill(squad-solta)", negadas)
        self.assertFalse([r for r in negadas if r.endswith("/Leitura Solta/**)")])
        self.assertIn("Skill(squad-aninhada)", negadas)  # a registrada fica

    def test_assinar_ficha_chama_a_ferramenta_fixa_do_titular(self):
        registro = self.base / "titular-chamadas.jsonl"  # o substituto de ensaio grava aqui os argumentos
        p, rel = self.projeto("-SemUAC", "-AssinarFicha", "-Versao", "2")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        chamadas = [json.loads(l) for l in registro.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(chamadas, [["assinar-ficha", "--raiz", str(self.raiz), "--projeto", "caso-real",
                                     "--versao", "2"]])
        p, rel = self.projeto("-Simular", "-AssinarFicha")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("fundacao_titular.py assinar-ficha", rel["assinatura"]["comando"])
        self.assertEqual(len(registro.read_text(encoding="utf-8").splitlines()), 1)  # simulação não assina

    def test_assinar_ficha_passa_menos_s_e_diz_qual_copia_assina(self):
        """Revisão da integração (defeito 8): o -AssinarFicha chama o Python com -I -B -S (sem o -S, um .pth de
        site-packages do Python por usuário rodaria antes da ferramenta; -I não implica -S) e, sem a cópia protegida do
        Windows instalada e conferida (aqui: -SemUAC, e o Python desta máquina é por usuário), chama a da skill, com o
        motivo nos avisos e no relatório. O substituto de ensaio grava as opções com que o Python rodou."""
        registro = self.base / "titular-opcoes.jsonl"
        (self.ps1.parents[3] / "assets" / "host" / "fundacao_titular.py").write_text(
            "import json, sys\n"
            f"with open({str(registro)!r}, 'a', encoding='utf-8') as f:\n"
            "    f.write(json.dumps({'argv': sys.argv[1:], 'isolado': sys.flags.isolated, 'sem_site': sys.flags.no_site,"
            " 'sem_bytecode': sys.flags.dont_write_bytecode, 'site': 'site' in sys.modules}) + '\\n')\n",
            encoding="utf-8", newline="\n")
        p, rel = self.projeto("-SemUAC", "-AssinarFicha", "-Versao", "2")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        chamadas = [json.loads(l) for l in registro.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(chamadas), 1, chamadas)
        self.assertEqual(chamadas[0]["argv"], ["assinar-ficha", "--raiz", str(self.raiz), "--projeto", "caso-real",
                                               "--versao", "2"])
        self.assertEqual({k: chamadas[0][k] for k in ("isolado", "sem_site", "sem_bytecode", "site")},
                         {"isolado": 1, "sem_site": 1, "sem_bytecode": 1, "site": False})
        self.assertIn(" -I -B -S ", rel["assinatura"]["comando"])
        self.assertEqual(rel["assinatura"]["copia"], "skill")
        self.assertTrue(rel["assinatura"]["motivo"])
        self.assertTrue(any("fora da cópia protegida" in a for a in rel["avisos"]), rel["avisos"])

    def test_a_copia_protegida_so_vale_igual_protegida_e_com_o_python_de_todos(self):
        """Get-FerramentaDaFicha, carregado com ponto (revisão da integração, defeito 8): a ferramenta da cópia
        protegida do Windows só com o item do Get-ItemFerramenta igual ao plano, protegido e com o Python instalado
        para todos os usuários; em qualquer outro caso, a da skill, com o motivo."""
        protegida = str(self.base / "ProgramData-ficticio" / "FundacaoIA" / "ferramentas" / "1.7.10")
        arq, saida = self.base / "trecho-ferramenta.ps1", self.base / "ferramenta-da-ficha.json"
        arq.write_text("\n".join([
            f". '{self.ps1_projeto}'",
            "function ItemDeEnsaio($acao, $protegida, $todos, $detalhe) { [pscustomobject]@{ acao = $acao; "
            f"protegida = $protegida; python_todos = $todos; caminho = '{protegida}'; detalhe = $detalhe }} }}",
            "$casos = [ordered]@{",
            "  igual = (Get-FerramentaDaFicha (ItemDeEnsaio 'igual' $true $true $null))",
            "  sem_protecao = (Get-FerramentaDaFicha (ItemDeEnsaio 'igual' $false $true $null))",
            "  por_usuario = (Get-FerramentaDaFicha (ItemDeEnsaio 'pendente' $false $false 'Python por usuário (ensaio)'))",
            "  criar = (Get-FerramentaDaFicha (ItemDeEnsaio 'criar' $false $true $null))",
            "  atualizar = (Get-FerramentaDaFicha (ItemDeEnsaio 'atualizar' $true $true $null))",
            "  nada = (Get-FerramentaDaFicha $null) }",
            f"[IO.File]::WriteAllText('{saida}', (ConvertTo-Json -InputObject $casos -Compress -Depth 3), "
            "(New-Object System.Text.UTF8Encoding($false)))"]) + "\n", encoding="utf-8-sig")
        p = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                            str(arq)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        r = json.loads(saida.read_text(encoding="utf-8"))  # em arquivo UTF-8: a saída do console não é UTF-8
        self.assertEqual(r["igual"], {"caminho": protegida + "\\assets\\host\\fundacao_titular.py", "copia": "protegida",
                                      "motivo": None})
        da_skill = str(self.ps1_projeto.parents[2] / "host" / "fundacao_titular.py")
        for caso in ("sem_protecao", "por_usuario", "criar", "atualizar", "nada"):
            with self.subTest(caso):
                self.assertEqual((r[caso]["copia"], r[caso]["caminho"]), ("skill", da_skill))
                self.assertTrue(r[caso]["motivo"])
        self.assertEqual(r["por_usuario"]["motivo"], "Python por usuário (ensaio)")
        self.assertIn("ainda não foi instalada", r["criar"]["motivo"])
        self.assertIn("difere desta skill", r["atualizar"]["motivo"])

    def registrar(self, projeto: str, origem: Path) -> None:
        r = subprocess.run([sys.executable, "-I", "-B", str(SKILL / "assets" / "host" / "preparo_host.py"),
                            "registrar-projeto", "--raiz", str(self.raiz), "--projeto", projeto, "--origem",
                            str(origem)], capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV,
                           timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_sessoes_do_windows_em_outro_projeto_ficam_e_as_origens_somam(self):
        """Revisão do lote 2, o caso real: as sessões do Windows são do coordenador (aqui, caso-real) e outro projeto
        é preparado para o Ubuntu. Antes, o preparo parava em conflito (código 1), nada era preparado e a mensagem
        mandava usar o próprio preparar-projeto.ps1; e as origens dos outros projetos perdiam o Edit negado."""
        outra = self.base / "Origem Lab"
        outra.mkdir()
        self.registrar("lab-a", outra)
        p, _rel = self.rodar("-SemUAC", "-Projeto", "caso-real")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        registro = self.base / "titular-chamadas.jsonl"  # o substituto de ensaio grava aqui os argumentos
        p, rel = self.projeto("-SemUAC", "-AssinarFicha", projeto="lab-a")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        win = json.loads((self.raiz / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(win["env"]["FUNDACAO_PROJECT"], "caso-real")  # o coordenador não muda
        edicao = [r for r in win["permissions"]["deny"] if r.startswith("Edit(//")]
        for pasta in (self.origem, outra):  # as origens dos dois projetos ficam só de leitura
            self.assertTrue(any(r.endswith("/" + pasta.name + "/**)") for r in edicao), (pasta.name, edicao))
        self.assertEqual(sorted(rel["somente_leitura"]), sorted([str(self.origem), str(outra)]))
        maquina = json.loads(Path(rel["preparar_maquina"]["relatorio"]).read_text(encoding="utf-8"))
        self.assertEqual(self.item(maquina, "projeto")["acao"], "igual")
        chamadas = [json.loads(l) for l in registro.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(chamadas, [["assinar-ficha", "--raiz", str(self.raiz), "--projeto", "lab-a"]])

    def test_pasta_registrada_que_sumiu_avisa_com_o_projeto_e_segue_negada(self):
        """Reconferência do lote 2: uma pasta registrada que não existe mais (disco desligado, pasta movida) parava o
        preparo de qualquer projeto (código 2, "veja o relatório"), sem dizer de quem era. Agora a de outro projeto
        vira aviso com o projeto e a pasta, segue com o Edit negado (quando o disco voltar, já está protegida) e o
        preparo continua; a do próprio projeto para o preparo dele, com o projeto e a pasta na mensagem, sem gravar."""
        sumida = self.base / "Origem Lab Sumida"
        sumida.mkdir()
        self.registrar("lab-a", sumida)
        sumida.rmdir()
        p, rel = self.projeto("-SemUAC")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertTrue(any("lab-a" in a and str(sumida) in a for a in rel["avisos"]), rel["avisos"])
        self.assertIn("lab-a", p.stdout)  # o aviso também sai na tela do titular
        self.assertEqual(rel["somente_leitura"], [str(self.origem)])
        self.assertEqual(rel["somente_leitura_ausente"], [str(sumida)])
        win = json.loads((self.raiz / ".claude" / "settings.json").read_text(encoding="utf-8"))
        edicao = [r for r in win["permissions"]["deny"] if r.startswith("Edit(//")]
        for pasta in (self.origem, sumida):  # a sumida segue negada para escrita
            self.assertTrue(any(r.endswith("/" + pasta.name + "/**)") for r in edicao), (pasta.name, edicao))
        maquina = json.loads(Path(rel["preparar_maquina"]["relatorio"]).read_text(encoding="utf-8"))
        self.assertEqual(maquina["somente_leitura_ausente"], [str(sumida)])
        antes = {k: v for k, v in fotografia(self.raiz).items() if "evidence" not in k}
        p, rel = self.projeto("-SemUAC", projeto="lab-a")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        for trecho in ("lab-a", str(sumida), "Nada foi alterado"):
            self.assertIn(trecho, rel["mensagem"])
        self.assertEqual({k: v for k, v in fotografia(self.raiz).items() if "evidence" not in k}, antes)

    def test_caminho_so_do_ubuntu_no_registro_vira_aviso(self):
        """Uma origem registrada pelo lado do Ubuntu (fora de /mnt/<x>) não cabe no perfil do Windows: antes parava o
        preparo de todos (código 2, "caminho absoluto num disco local esperado"); agora é aviso com o projeto e o
        caminho, e o resto segue."""
        registro = self.raiz / "registry" / "projetos-host.json"
        dados = json.loads(registro.read_text(encoding="utf-8"))
        dados["projetos"]["lab-a"] = {"origens": ["/home/ensaio/origem-lab"], "somente_leitura": [],
                                      "aninhadas_negadas": []}
        registro.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        p, rel = self.projeto("-SemUAC")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertTrue(any("lab-a" in a and "/home/ensaio/origem-lab" in a for a in rel["avisos"]), rel["avisos"])
        self.assertEqual(rel["somente_leitura"], [str(self.origem)])
        self.assertEqual(rel["somente_leitura_ausente"], [])

    def test_projeto_windows_so_troca_de_proposito(self):
        p, _rel = self.rodar("-SemUAC", "-Projeto", "caso-real")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        p, rel = self.projeto("-SemUAC", "-TrocarProjeto", projeto="lab-a")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)  # -TrocarProjeto sem dizer para qual
        self.assertIn("-ProjetoWindows", rel["mensagem"])
        p, rel = self.projeto("-SemUAC", "-ProjetoWindows", "lab-a", projeto="lab-a")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)  # troca sem -TrocarProjeto: conflito, nada gravado
        detalhe = self.item(json.loads(Path(rel["preparar_maquina"]["relatorio"]).read_text(encoding="utf-8")),
                            "projeto")["detalhe"]
        self.assertIn("-TrocarProjeto", detalhe)
        self.assertIn("sem -ProjetoWindows", detalhe)  # a saída aponta o caminho sem troca, não um laço
        p, _rel = self.projeto("-SemUAC", "-ProjetoWindows", "lab-a", "-TrocarProjeto", projeto="lab-a")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        win = json.loads((self.raiz / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(win["env"]["FUNDACAO_PROJECT"], "lab-a")

    def test_projeto_fora_da_forma_do_kit_e_recusado(self):
        for valor in ("caso_real", "caso.real", "a--b"):
            with self.subTest(valor):
                p, rel = self.projeto("-Simular", projeto=valor)
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIn("projeto inválido", rel["mensagem"])

    def test_projeto_inexistente_e_recusado(self):
        p, rel = self.projeto("-Simular", projeto="nao-existe")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("nao-existe", rel["mensagem"])

    def test_ubuntu_ligado_e_reconhecido_na_saida_do_wsl(self):
        arq = self.base / "trecho-projeto.ps1"
        arq.write_text(f". '{self.ps1_projeto}'\n"
                       "@{ ligado = (Test-NaLista @(\"U`0b`0u`0n`0t`0u\", 'docker-desktop') 'ubuntu'); "
                       "desligado = (Test-NaLista @('docker-desktop') 'Ubuntu') } | ConvertTo-Json -Compress\n",
                       encoding="utf-8-sig")
        p = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                            str(arq)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(json.loads(p.stdout.strip().splitlines()[-1]), {"ligado": True, "desligado": False})


class FonteDoPreparoDoProjeto(unittest.TestCase):
    def test_utf8_com_bom_sem_senha_e_com_backups_repassados(self):
        """Até a I21 o script nunca repassava -Backups (aqui se conferia a ausência de `$Backups`); a folha da integração
        (I21 b) inverteu a regra: ele aceita -Backups, confere e repassa ao preparar-maquina.ps1, ou exige -SemBackups."""
        bruto = PROJETO_PS1.read_bytes()
        self.assertTrue(bruto.startswith(b"\xef\xbb\xbf"))  # o PowerShell 5.1 lê sem BOM como ANSI
        self.assertNotIn(b"\r", bruto)
        texto = bruto.decode("utf-8-sig")
        for proibido in ("Read-Host", "ConvertTo-SecureString", "-AsSecureString"):
            self.assertNotIn(proibido, texto)
        self.assertIn("fundacao_titular.py", texto)
        bloco = texto[texto.index("param("):texto.index("Set-StrictMode")]
        for parametro in ("[string[]] $Backups", "[switch] $SemBackups"):
            self.assertIn(parametro, bloco)
        self.assertIn("$parametros.Backups = ", texto)
        self.assertNotIn("nunca -Backups", texto)

    def test_sem_backups_aceito_pelo_preparar_maquina_e_repassado(self):
        """Revisão da terceira rodada da integração, defeito 1: o preparar-maquina.ps1 aceita -SemBackups (o portão da
        I21 b vale nele também), e o preparar-projeto.ps1 o repassa; sem o repasse, o preparo do projeto com -SemBackups
        pararia no portão do preparar-maquina.ps1."""
        maquina = (PROJETO_PS1.parent / "preparar-maquina.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("[switch] $SemBackups", maquina[maquina.index("param("):maquina.index("Set-StrictMode")])
        self.assertIn("if ($SemBackups) { $parametros.SemBackups = $true }", PROJETO_PS1.read_text(encoding="utf-8-sig"))

    def test_backups_ausente_nos_dois_e_o_portao_e_um_so(self):
        """Revisão seguinte da terceira rodada da integração, defeito 2: -BackupsAusente nos dois scripts, repassado pelo
        do projeto; o portão das cópias é uma função só (Get-PortaoDasCopias, do preparar-maquina.ps1), que o do projeto
        usa pelo carregamento num escopo próprio: as duas recusas não se separam."""
        maquina = (PROJETO_PS1.parent / "preparar-maquina.ps1").read_text(encoding="utf-8-sig")
        projeto = PROJETO_PS1.read_text(encoding="utf-8-sig")
        for texto in (maquina, projeto):
            self.assertIn("[string[]] $BackupsAusente", texto[texto.index("param("):texto.index("Set-StrictMode")])
        self.assertIn("$parametros.BackupsAusente = ", projeto)
        self.assertEqual(maquina.count("function Get-PortaoDasCopias"), 1)
        self.assertNotIn("function Get-PortaoDasCopias", projeto)
        self.assertIn("Get-PortaoDasCopias", projeto)


if __name__ == "__main__":
    unittest.main()
