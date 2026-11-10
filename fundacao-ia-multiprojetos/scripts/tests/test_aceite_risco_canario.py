"""Aceite de risco do canário (1.7.10.1; pedido do titular de 02/11/2026; DECISAO-007 da fundação).

Com o canário reprovado (false ou null), a ficha de aberturas de um projeto só vale com o aceite de risco que o titular
assina na ferramenta fixa (`assets/host/fundacao_titular.py aceitar-risco`): montado só com código fixo a partir do
relatório real do ensaio, assinado no namespace da ficha (`fundacao-abertura`), com esquema próprio, preso ao SHA-256
do relatório instalado, ao Claude Code fixado, à forma de caminho da raiz, ao projeto e a uma vigência de até 180 dias.
O preparo do host o instala na área do titular, fixa o relatório e o aceite no hashes.json e o lançador os reconfere.

- `PecasDoAceite`: as peças puras, em qualquer sistema (os nomes iguais na ferramenta e no preparo, a mesma conta da
  forma de caminho, o esquema fechado, o portão que expõe o reprovado e o `com_canario`).
- `CerimoniaDoAceite`: a cerimônia com o `ssh-keygen` do sistema, chaves sem senha geradas na hora e a âncora de
  ensaio no lugar da desta máquina; a conferência do preparo contra o kit real (sem `ssh-keygen`, pula).
- `AceiteNoPreparo`: o preparo do Ubuntu em ensaio, sem root (só no Linux), com os substitutos do apoio.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from apoio import KIT, SKILL
from test_host_projeto_apoio import (LINUX, aceite_de_ensaio, carregar_preparo, claude_de_ensaio, ficha_de_ensaio,
                                     gravar_aceite_na_caixa, gravar_ficha_na_caixa, instalar, instalar_canario,
                                     raiz_de_ensaio, relatorio_de_canario, sha, skill_de_ensaio)

FERRAMENTA = SKILL / "assets" / "host" / "fundacao_titular.py"
HOJE = date(2026, 11, 2)
PROJETO = "caso-real"
SHA_CLAUDE = "c" * 64


def carregar_ferramenta():
    spec = importlib.util.spec_from_file_location("_fundacao_titular_aceite_teste", FERRAMENTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


TITULAR = carregar_ferramenta()
K = TITULAR.kit()
PREPARO = carregar_preparo()


def relatorio_de_seis_itens(**mudancas) -> dict:
    """O relatório reprovado do titular em 02/11/2026 como o teste da 1.7.10.1 o escrevia (ids e vereditos; valores
    fictícios): seis itens, um deles com o id "Item Estranho;rm", e sem perfil, sandbox nem temp. NÃO é o formato do
    ensaio real: o portão e a ferramenta o recusam (1.7.11, junção do lote B). Serve de base dos completos abaixo e dos
    casos de recusa."""
    itens = [{"id": i, "classe": "comando", "veredito": "nao_medido", "canario": {"apareceu": False}}
             for i in ("leitura_outro_projeto", "leitura_state", "escrita_fora_do_projeto")]
    itens += [{"id": "plugin_setting_sources_local", "classe": "comando", "veredito": "falhou"},
              {"id": "skill_agente_aninhado", "classe": "carga", "veredito": "nao_medido"},
              {"id": "Item Estranho;rm", "classe": "comando", "veredito": "falhou"}]
    base = {"schema_version": "fundacao.ensaio_isolamento/1", "data": "2026-11-02T18:49:27Z", "simulado": False,
            "forma": "drvfs:/mnt/e/Ensaio de IA", "sistema_de_arquivos": "9p",
            "claude": {"versao": "2.1.302", "sha256": SHA_CLAUDE}, "itens": itens,
            "conclusao": {"forma": "drvfs:/mnt/e/Ensaio de IA", "sistema_de_arquivos": "9p",
                          "confina_comandos": False, "motivo": "itens de comando com falha"}}
    base.update(mudancas)
    return base


def relatorio_completo(aprova: bool = False, **mudancas) -> dict:
    """O mesmo relatório no formato do ensaio desta versão (revisão de segurança da 1.7.10, CAN-1: o portão recusa o
    relatório sem as sondas, o perfil, o sandbox e o temp; a ferramenta do titular usa a mesma regra). Reprovado: as
    sondas de comando que o de 02/11/2026 não mediu ou falhou continuam assim; aprovado: todas as de comando passam."""
    itens = []
    for ident, classe in PREPARO.SONDAS_DO_CANARIO.items():
        veredito = "passou"
        if not aprova and ident in ("plugin_setting_sources_local",):
            veredito = "falhou"
        elif not aprova and ident in ("leitura_outro_projeto", "leitura_state", "escrita_fora_do_projeto"):
            veredito = "nao_medido"
        itens.append({"id": ident, "classe": classe, "veredito": veredito, "canario": {"apareceu": False}})
    base = relatorio_de_seis_itens(itens=itens, perfil={"gerado": True}, sandbox_ligado=True,
                                   temp={"do_lancador": True})
    if aprova:
        base["conclusao"] = {**base["conclusao"], "confina_comandos": True}
    base.update(mudancas)
    return base


def relatorio_anterior(aprova: bool = False, **mudancas) -> dict:
    """O completo sem as duas sondas que o ensaio da 1.7.10 e da 1.7.10.1 não tinha (`SONDAS_ADIADAS`): o relatório que
    já pode estar instalado na máquina do titular, com o aceite de risco dele (DECISAO-007)."""
    base = relatorio_completo(aprova)
    base["itens"] = [i for i in base["itens"] if i["id"] not in PREPARO.SONDAS_ADIADAS]
    base.update(mudancas)
    return base


def bytes_de(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


class PecasDoAceite(unittest.TestCase):
    def test_relatorio_onde_a_sessao_grava_e_recusado(self):
        """Revisão de segurança da 1.7.10.1, R17101-ACE-3: dentro da raiz ou, no Ubuntu, num disco do Windows
        (/mnt/...), onde o sandbox não confina os comandos; sem diferença de maiúsculas e minúsculas."""
        f = TITULAR.onde_a_sessao_grava
        raiz = "/mnt/e/Projeto Exemplo"
        for caminho in ("/mnt/e/Projeto Exemplo/projects/x/canario.json", "/mnt/e/projeto exemplo/canario.json",
                        "/mnt/c/Users/<usuario>/canario-drvfs.json", "/mnt/d/canario.json", "/MNT/c/x.json", "/mnt"):
            with self.subTest(caminho):
                self.assertTrue(f(caminho, raiz, True))
        for caminho in ("/home/titular/canario-drvfs.json", "/mntx/canario.json", "/root/canario.json"):
            with self.subTest(caminho):
                self.assertFalse(f(caminho, raiz, True))
        self.assertTrue(f("e:\\projeto exemplo\\projects\\x\\c.json", "E:\\Projeto Exemplo", False))
        self.assertTrue(f("E:/Projeto Exemplo/c.json", "E:\\Projeto Exemplo", False))
        self.assertFalse(f("E:\\Projeto Exemplo 2\\c.json", "E:\\Projeto Exemplo", False))
        self.assertFalse(f("\\\\wsl.localhost\\Ubuntu\\home\\titular\\c.json", "E:\\Projeto Exemplo", False))

    def test_nomes_iguais_na_ferramenta_e_no_preparo(self):
        for nome in ("ESQUEMA_ACEITE", "ACEITE_NOME", "PASTA_DO_ACEITE", "PRAZO_DO_ACEITE", "FS_DRVFS",
                     "ESQUEMA_CANARIO", "VERSAO_MAXIMA_ACEITE"):
            with self.subTest(nome):
                self.assertEqual(getattr(TITULAR, nome), getattr(PREPARO, nome))
        self.assertLessEqual(TITULAR.PRAZO_PROPOSTO, TITULAR.PRAZO_DO_ACEITE)
        self.assertEqual(TITULAR.ITEM_DO_CANARIO.pattern.strip("^$"), PREPARO.ITEM_DO_CANARIO.pattern.strip("^$"))
        self.assertTrue(TITULAR.RISCOS and all(r.strip() for r in TITULAR.RISCOS))

    def test_forma_do_relatorio_e_a_mesma_conta_do_preparo(self):
        casos = [("ext4", "ext4"), ("ext4", "9p"), ("drvfs:/mnt/e/Ensaio de IA", "9p"), ("drvfs:/mnt/e/../c/x", "9p"),
                 ("drvfs:/mnt/e", "9p"), ("drvfs:/mnt/E/x", "9p"), ("drvfs:/mnt/e/x", "ext4"),
                 ("drvfs:/mnt/e/x\n", "9p"), ("drvfs:/mnt/d/IA", "drvfs"), (None, "9p"), ("ext4", None)]
        for forma, fs in casos:
            with self.subTest(forma=forma, fs=fs):
                rel = {"forma": forma, "sistema_de_arquivos": fs}
                self.assertEqual(TITULAR.forma_do_relatorio(rel), PREPARO._forma_do_relatorio(rel))
        self.assertEqual(TITULAR.forma_do_relatorio({"forma": "drvfs:/mnt/e/Ensaio de IA",
                                                     "sistema_de_arquivos": "9p"}), "drvfs:/mnt/e")

    def test_resumo_do_relatorio_guarda_so_o_conferido(self):
        rel = relatorio_completo()
        rel["itens"][0]["canario"]["apareceu"] = True
        r = TITULAR.resumo_do_relatorio(rel, bytes_de(rel))
        self.assertEqual(set(r), PREPARO.CAMPOS_DO_CANARIO_ACEITO)
        self.assertEqual(r["relatorio_sha256"], hashlib.sha256(bytes_de(rel)).hexdigest())
        self.assertEqual((r["claude_versao"], r["claude_sha256"], r["forma"], r["confina_comandos"]),
                         ("2.1.302", SHA_CLAUDE, "drvfs:/mnt/e", False))
        self.assertEqual(r["falhou"], ["plugin_setting_sources_local"])
        self.assertEqual(r["nao_medido"], ["escrita_fora_do_projeto", "leitura_outro_projeto", "leitura_state"])
        self.assertEqual(r["vazou"], ["leitura_outro_projeto"])
        nulo = relatorio_completo(conclusao={**relatorio_completo()["conclusao"], "confina_comandos": None})
        self.assertIsNone(TITULAR.resumo_do_relatorio(nulo, bytes_de(nulo))["confina_comandos"])
        recusas = {"aprovado": relatorio_completo(aprova=True),
                   "simulado": relatorio_completo(simulado=True),
                   "sem a marca de real": {k: v for k, v in rel.items() if k != "simulado"},
                   "outro esquema": relatorio_completo(schema_version="fundacao.ensaio_isolamento_simulado/1"),
                   "sem o Claude Code": relatorio_completo(claude={"versao": "2.1.302"}),
                   "sem a conclusão": relatorio_completo(conclusao={"forma": rel["forma"]}),
                   "conclusão de outra forma": relatorio_completo(conclusao={**rel["conclusao"], "forma": "ext4"}),
                   "forma que o canário não prova": relatorio_completo(forma="drvfs:/mnt/e/x",
                                                                       sistema_de_arquivos="ext4"),
                   "não é objeto": ["x"],
                   # 1.7.11: a ferramenta usa a regra do portão (antes aceitava qualquer lista de itens)
                   "seis itens, um de id estranho (o formato antigo do teste)": relatorio_de_seis_itens(),
                   "sem o perfil": relatorio_completo(perfil=None),
                   "sem o temp": {k: v for k, v in relatorio_completo().items() if k != "temp"},
                   "sem a chave do sandbox": {k: v for k, v in relatorio_completo().items() if k != "sandbox_ligado"},
                   "item de fora": relatorio_completo(itens=[*relatorio_completo()["itens"],
                                                             {"id": "sonda_inventada", "classe": "comando",
                                                              "veredito": "falhou"}]),
                   "falta uma sonda que não é adiada": relatorio_completo(itens=[
                       i for i in relatorio_completo()["itens"] if i["id"] != "leitura_state"]),
                   "item repetido": relatorio_completo(itens=[*relatorio_completo()["itens"],
                                                              relatorio_completo()["itens"][0]]),
                   "anterior que se diz aprovado": relatorio_anterior(aprova=True)}
        for nome, ruim in recusas.items():
            with self.subTest(nome):
                with self.assertRaises(TITULAR.Recusa):
                    TITULAR.resumo_do_relatorio(ruim, b"{}")

    def test_resumo_do_relatorio_anterior_conta_as_sondas_que_faltam_como_nao_medidas(self):
        """1.7.11, N1: o relatório do ensaio da 1.7.10 e da 1.7.10.1 (sem as duas sondas novas) segue aceito para o
        aceite de risco, e o titular vê as duas que faltam entre os itens não medidos."""
        anterior = relatorio_anterior()
        r = TITULAR.resumo_do_relatorio(anterior, bytes_de(anterior))
        self.assertEqual(r["nao_medido"], sorted({"escrita_fora_do_projeto", "leitura_outro_projeto", "leitura_state",
                                                  *PREPARO.SONDAS_ADIADAS}))
        self.assertEqual(PREPARO.problemas_do_aceite(
            {"schema_version": PREPARO.ESQUEMA_ACEITE, "project_id": PROJETO, "versao": 1, "aceito_em": "2026-11-02",
             "vigencia_ate": "2027-01-31", "riscos": list(TITULAR.RISCOS), "canario": r}, PROJETO, HOJE), [])

    def aceite(self, **mudancas) -> dict:
        a = {"schema_version": PREPARO.ESQUEMA_ACEITE, "project_id": PROJETO, "versao": 1, "aceito_em": "2026-11-02",
             "vigencia_ate": "2027-01-31", "riscos": list(TITULAR.RISCOS),
             "canario": TITULAR.resumo_do_relatorio(relatorio_completo(), bytes_de(relatorio_completo()))}
        a.update(mudancas)
        return a

    def test_esquema_fechado_do_aceite(self):
        self.assertEqual(PREPARO.problemas_do_aceite(self.aceite(), PROJETO, HOJE), [])
        self.assertEqual(PREPARO.problemas_do_aceite(self.aceite(), PROJETO, date(2027, 1, 31)), [])  # no dia, vale
        c = self.aceite()["canario"]
        casos = {"campo a mais": self.aceite(extra=1),
                 "campo a menos": {k: v for k, v in self.aceite().items() if k != "riscos"},
                 "outro esquema": self.aceite(schema_version="fundacao.ficha_aberturas/1"),
                 "outro projeto": self.aceite(project_id="lab-a"),
                 "versão zero": self.aceite(versao=0), "versão booleana": self.aceite(versao=True),
                 "versão em texto": self.aceite(versao="2"), "versão acima do teto": self.aceite(versao=1000000),
                 "vigência acima de 180 dias": self.aceite(vigencia_ate="2027-05-02"),
                 "vigência antes do aceite": self.aceite(vigencia_ate="2026-11-01"),
                 "aceite no futuro": self.aceite(aceito_em="2026-11-03", vigencia_ate="2026-12-01"),
                 "data fora da forma": self.aceite(vigencia_ate="31/01/2027"),
                 "canário aprovado": self.aceite(canario={**c, "confina_comandos": True}),
                 "forma não normalizada": self.aceite(canario={**c, "forma": "drvfs:/mnt/e/Ensaio de IA"}),
                 "item fora da forma": self.aceite(canario={**c, "falhou": ["x;y"]}),
                 "canário com campo a mais": self.aceite(canario={**c, "extra": 1}),
                 "sem riscos": self.aceite(riscos=[]),
                 "risco vazio": self.aceite(riscos=["  "])}
        for nome, ruim in casos.items():
            with self.subTest(nome):
                self.assertTrue(PREPARO.problemas_do_aceite(ruim, PROJETO, HOJE), nome)
        self.assertTrue(any("vencido" in p for p in PREPARO.problemas_do_aceite(self.aceite(), PROJETO,
                                                                                date(2027, 2, 1))))

    def test_portao_expoe_o_reprovado_so_do_claude_fixado_e_da_forma_da_raiz(self):
        base = Path(tempfile.mkdtemp(prefix="aceite-portao-"))
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        arquivo = base / "canario" / "2.1.302.json"
        arquivo.parent.mkdir(parents=True)
        arquivo.write_bytes(bytes_de(relatorio_completo()))
        kw = dict(claude_versao="2.1.302", claude_sha256=SHA_CLAUDE, raiz_wsl="/mnt/e/Projeto Exemplo", fs_raiz="9p")
        p = PREPARO.portao_do_canario(base, **kw)
        self.assertFalse(p["aprovado"])
        self.assertEqual(p["reprovado"], {"sha256": sha(arquivo), "confina_comandos": False, "claude_versao": "2.1.302",
                                          "claude_sha256": SHA_CLAUDE, "data": "2026-11-02T18:49:27Z"})
        self.assertEqual(p["forma"], "drvfs:/mnt/e")
        for nome, outro in (("outro binário", {**kw, "claude_sha256": "d" * 64}),
                            ("outra forma da raiz", {**kw, "raiz_wsl": "/mnt/d/Outra"}),
                            ("raiz no ext4", {**kw, "raiz_wsl": "/home/titular/f", "fs_raiz": "ext4"})):
            with self.subTest(nome):
                self.assertNotIn("reprovado", PREPARO.portao_do_canario(base, **outro))
        arquivo.write_bytes(bytes_de(relatorio_completo(aprova=True)))
        p = PREPARO.portao_do_canario(base, **kw)
        self.assertTrue(p["aprovado"])
        self.assertNotIn("reprovado", p)
        # 1.7.11, N1: o relatório do ensaio anterior (sem as duas sondas novas) segue reprovado, com o mesmo SHA-256 para
        # o aceite assinado; e, se se diz aprovado, nunca aprova nem vira reprovado.
        arquivo.write_bytes(bytes_de(relatorio_anterior()))
        p = PREPARO.portao_do_canario(base, **kw)
        self.assertFalse(p["aprovado"])
        self.assertEqual(p["reprovado"]["sha256"], sha(arquivo))
        arquivo.write_bytes(bytes_de(relatorio_anterior(aprova=True)))
        p = PREPARO.portao_do_canario(base, **kw)
        self.assertFalse(p["aprovado"])
        self.assertNotIn("reprovado", p)
        self.assertIn("ensaio anterior", p["motivo"])

    def test_o_titular_e_o_portao_concordam_no_que_e_um_relatorio_real(self):
        """1.7.11, junção do lote B, item 4: a ferramenta do titular (aceitar-risco) e o preparo do host carregam a
        mesma regra (fundacao/core/canario.py do kit). Para cada relatório que não aprova, o titular monta o aceite
        exatamente quando o portão, com ele instalado, expõe o `reprovado` a que um aceite se prende; e o titular
        nunca monta aceite para o que diz aprovar."""
        regra = TITULAR.regra_do_canario()
        modulo = PREPARO.modulo_do_canario()
        self.assertEqual(regra.SONDAS_DO_CANARIO, PREPARO.SONDAS_DO_CANARIO)
        self.assertEqual(regra.SONDAS_ADIADAS, PREPARO.SONDAS_ADIADAS)
        self.assertEqual(regra.VEREDITOS_DO_CANARIO, PREPARO.VEREDITOS_DO_CANARIO)
        self.assertEqual(Path(modulo.__file__).resolve(), (KIT / "fundacao" / "core" / "canario.py").resolve())
        completo = relatorio_completo()
        todos = completo["itens"]
        sem_leitura_state = [i for i in todos if i["id"] != "leitura_state"]
        casos = {
            "completo": completo, "anterior": relatorio_anterior(),
            "incoerente (false com tudo passou)": relatorio_completo(itens=[{**i, "veredito": "passou"} for i in todos]),
            "conclusão null": relatorio_completo(conclusao={**completo["conclusao"], "confina_comandos": None}),
            "seis itens": relatorio_de_seis_itens(), "sem o perfil": relatorio_completo(perfil=None),
            "sem o sandbox": {k: v for k, v in completo.items() if k != "sandbox_ligado"},
            "falta uma sonda que não é adiada": relatorio_completo(itens=sem_leitura_state),
            "anterior sem uma sonda que não é adiada": relatorio_anterior(
                itens=[i for i in relatorio_anterior()["itens"] if i["id"] != "leitura_state"]),
            "item repetido": relatorio_completo(itens=[*todos, todos[0]]),
            "id estranho": relatorio_completo(itens=[*todos, {"id": "Item Estranho;rm", "classe": "comando",
                                                              "veredito": "falhou"}]),
            "classe trocada": relatorio_completo(itens=[{**todos[0], "classe": "informativo"}, *todos[1:]]),
            "veredito fora do ensaio": relatorio_completo(itens=[{**todos[0], "veredito": "ok"}, *todos[1:]]),
            "simulado": relatorio_completo(simulado=True),
            "outro esquema": relatorio_completo(schema_version="fundacao.ensaio_isolamento_simulado/1")}
        base = Path(tempfile.mkdtemp(prefix="aceite-concorda-"))
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        arquivo = base / "canario" / "2.1.302.json"
        arquivo.parent.mkdir(parents=True)
        kw = dict(claude_versao="2.1.302", claude_sha256=SHA_CLAUDE, raiz_wsl="/mnt/e/Projeto Exemplo", fs_raiz="9p")
        aceitos = set()
        for nome, rel in casos.items():
            with self.subTest(nome):
                bruto = bytes_de(rel)
                arquivo.write_bytes(bruto)
                portao = PREPARO.portao_do_canario(base, **kw)
                self.assertFalse(portao["aprovado"], nome)
                try:
                    TITULAR.resumo_do_relatorio(rel, bruto)
                    aceita = True
                    aceitos.add(nome)
                except TITULAR.Recusa:
                    aceita = False
                self.assertEqual(aceita, "reprovado" in portao, f"{nome}: {portao.get('motivo')}")
        self.assertEqual(aceitos, {"completo", "anterior", "incoerente (false com tudo passou)", "conclusão null"})
        # o que se diz aprovado: o titular nunca monta o aceite; o portão aprova só o completo e coerente
        com_falha = [{**i, "veredito": "falhou"} if i["classe"] == "comando" else i for i in todos]
        for nome, rel in (("completo aprovado", relatorio_completo(aprova=True)),
                          ("anterior aprovado", relatorio_anterior(aprova=True)),
                          ("incoerente aprovado", relatorio_completo(aprova=True, itens=com_falha))):
            with self.subTest(nome):
                arquivo.write_bytes(bytes_de(rel))
                with self.assertRaises(TITULAR.Recusa):
                    TITULAR.resumo_do_relatorio(rel, bytes_de(rel))
                self.assertEqual(PREPARO.portao_do_canario(base, **kw)["aprovado"], nome == "completo aprovado")

    def test_com_canario_sob_o_aceite(self):
        aberta = {**PREPARO.aberturas_fechadas(), "valida": True, "versao": 2, "rede": ["github.com"]}
        reprovado = {"aprovado": False, "motivo": "não provou", "reprovado": {"sha256": "a" * 64}}
        valido = {"valido": True, "arquivo": "x", "sha256": "b" * 64, "sig_sha256": "c" * 64,
                  "aceito_em": "2026-11-02", "vigencia_ate": "2027-01-31", "relatorio_sha256": "a" * 64}
        sob = PREPARO.com_canario(aberta, reprovado, valido)
        self.assertTrue(sob["valida"])
        self.assertEqual(sob["rede"], ["github.com"])
        self.assertEqual(sob["aceite_risco"]["relatorio_sha256"], "a" * 64)
        self.assertIn("aceite de risco", sob["motivo"])
        fechada = PREPARO.com_canario(aberta, reprovado, {"valido": False, "motivo": "aceite de outro projeto"})
        self.assertFalse(fechada["valida"])
        self.assertEqual(fechada["rede"], [])
        self.assertIn("aceite de outro projeto", fechada["motivo"])
        self.assertFalse(PREPARO.com_canario(aberta, reprovado)["valida"])
        self.assertIs(PREPARO.com_canario(aberta, {"aprovado": True}, valido), aberta)
        sem_ficha = PREPARO.aberturas_fechadas()
        self.assertIs(PREPARO.com_canario(sem_ficha, reprovado, valido), sem_ficha)  # o aceite sozinho não abre nada


class CerimoniaDoAceite(unittest.TestCase):
    """A cerimônia de verdade (ssh-keygen do sistema) e a conferência do preparo contra o kit real desta skill."""

    def setUp(self):
        try:
            self.keygen = K.decisoes.ssh_keygen()
        except FileNotFoundError as exc:
            self.skipTest(f"ssh-keygen indisponível neste ambiente: {exc}")
        self.base = Path(tempfile.mkdtemp(prefix="aceite-risco-teste-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.raiz = self.base / "raiz"
        shutil.copytree(KIT / "fundacao", self.raiz / "fundacao", ignore=shutil.ignore_patterns("__pycache__"))
        (self.raiz / "projects" / PROJETO).mkdir(parents=True)
        self.chaves = self.base / "chaves"
        self.chaves.mkdir()
        for nome in ("titular-ensaio", "intruso"):
            subprocess.run([self.keygen, "-q", "-t", "ed25519", "-N", "", "-C", nome, "-f", str(self.chaves / nome)],
                           check=True, capture_output=True)
        self.ancora = self.base / "ancora" / "allowed_signers"
        self.ancora.parent.mkdir()
        self.escrever_ancora("fundacao-decisao,fundacao-abertura")
        padrao = mock.patch.object(K.decisoes, "ANCORAS_PADRAO", (str(self.ancora),))
        padrao.start()
        self.addCleanup(padrao.stop)
        self.relatorio = self.base / "casa" / "canario-drvfs.json"
        self.relatorio.parent.mkdir()
        self.relatorio.write_bytes(bytes_de(relatorio_completo()))
        self.caixa = self.raiz / ".claude" / "projetos" / PROJETO / "risco"
        self.perguntas = []

    def escrever_ancora(self, namespaces: str) -> None:
        pub = (self.chaves / "titular-ensaio.pub").read_text(encoding="ascii").strip()
        self.ancora.write_text(f'titular-ensaio namespaces="{namespaces}" {pub}\n', encoding="ascii")

    def aceitar(self, resposta: str = PROJETO, **kw) -> tuple[int, str]:
        saida = io.StringIO()

        def confirmar(texto):
            self.perguntas.append(texto)
            return resposta
        kw.setdefault("chave", self.chaves / "titular-ensaio")
        kw.setdefault("canario", self.relatorio)
        codigo = TITULAR.aceitar_risco(self.raiz, kw.pop("projeto", PROJETO), kw.pop("canario"), confirmar=confirmar,
                                       saida=saida, hoje=HOJE, **kw)
        return codigo, saida.getvalue()

    def canario_instalado(self, **mudancas) -> dict:
        """O que o portão do preparo devolve com este relatório instalado na raiz em /mnt/e."""
        return {"aprovado": False, "forma": "drvfs:/mnt/e", "motivo": "não provou",
                "reprovado": {"sha256": sha(self.relatorio), "confina_comandos": False, "claude_versao": "2.1.302",
                              "claude_sha256": SHA_CLAUDE, "data": "2026-11-02T18:49:27Z", **mudancas}}

    def conferir(self, canario=None, projeto=PROJETO, hoje=HOJE) -> dict:
        return PREPARO.conferir_aceite_de_risco(self.caixa, projeto, canario or self.canario_instalado(), hoje=hoje)

    def nada_gravado(self) -> None:
        self.assertFalse(self.caixa.exists() and any(self.caixa.iterdir()))

    def test_assina_grava_na_caixa_e_o_preparo_confere(self):
        codigo, texto = self.aceitar()
        self.assertEqual(codigo, 0, texto)
        bruto = (self.caixa / TITULAR.ACEITE_NOME).read_bytes()
        aceite = json.loads(bruto)
        self.assertEqual(K.regras.canonico(aceite), bruto)
        self.assertEqual((aceite["schema_version"], aceite["project_id"], aceite["versao"], aceite["aceito_em"],
                          aceite["vigencia_ate"]),
                         (TITULAR.ESQUEMA_ACEITE, PROJETO, 1, "2026-11-02", (HOJE + timedelta(days=90)).isoformat()))
        self.assertEqual(aceite["canario"]["relatorio_sha256"], sha(self.relatorio))
        self.assertEqual(aceite["riscos"], list(TITULAR.RISCOS))
        for trecho in ("confina_comandos = false", "plugin_setting_sources_local", "leitura_state", sha(self.relatorio),
                       "não abre nada sozinho", "Os outros projetos continuam fechados", "/mnt/c", "Inicializar",
                       "Aceite assinado pela chave de titular-ensaio", "--canario"):
            self.assertIn(trecho, texto)
        self.assertNotIn("Item Estranho", texto)
        self.assertEqual(len(self.perguntas), 1)
        self.assertIn(f"digite o nome do projeto ({PROJETO})", self.perguntas[0])
        r = self.conferir()
        self.assertTrue(r["valido"], r)
        self.assertEqual((r["relatorio_sha256"], r["vigencia_ate"]), (sha(self.relatorio), aceite["vigencia_ate"]))
        self.assertEqual(r["sha256"], hashlib.sha256(bruto).hexdigest())

    def test_aceite_assinado_para_o_relatorio_anterior_continua_valido(self):
        """1.7.11, N1 (revisão da junção): o aceite que o titular já assinou para o relatório do ensaio da 1.7.10 e da
        1.7.10.1 (sem as duas sondas novas) segue válido depois do lote B: o relatório continua reprovado, com o mesmo
        SHA-256, e a ficha abre sob o aceite. O aceite antigo é o que a ferramenta de antes montava (sem as sondas
        ausentes entre as não medidas); o preparo não recalcula esse campo."""
        anterior = relatorio_anterior()
        self.relatorio.write_bytes(bytes_de(anterior))
        with mock.patch.object(TITULAR.regra_do_canario(), "sondas_ausentes", return_value=[]):
            codigo, texto = self.aceitar()
        self.assertEqual(codigo, 0, texto)
        area = self.base / "area"
        (area / "canario").mkdir(parents=True)
        (area / "canario" / "2.1.302.json").write_bytes(self.relatorio.read_bytes())
        portao = PREPARO.portao_do_canario(area, claude_versao="2.1.302", claude_sha256=SHA_CLAUDE,
                                           raiz_wsl="/mnt/e/Projeto Exemplo", fs_raiz="9p")
        self.assertFalse(portao["aprovado"])
        self.assertEqual(portao["reprovado"]["sha256"], sha(self.relatorio))
        r = self.conferir(canario=portao)
        self.assertTrue(r["valido"], r)
        aberta = {**PREPARO.aberturas_fechadas(), "valida": True, "versao": 2, "rede": ["github.com"]}
        sob = PREPARO.com_canario(aberta, portao, r)
        self.assertTrue(sob["valida"])
        self.assertIn("aceite_risco", sob)

    def test_versao_nova_passa_da_maior_vista(self):
        """R17101-ACE-1 e ACE-4: a versão do aceite novo passa da maior que o aceite ASSINADO da caixa de entrada mostra
        e, no Ubuntu, da área do titular (de dono root); só no Windows, que não lê a área, também da do espelho na raiz.
        O que a sessão planta sem a assinatura do titular não conta."""
        versao = lambda: json.loads((self.caixa / TITULAR.ACEITE_NOME).read_bytes())["versao"]  # noqa: E731
        self.assertEqual(self.aceitar()[0], 0)
        self.assertEqual(versao(), 1)
        self.assertEqual(self.aceitar()[0], 0)
        self.assertEqual(versao(), 2)
        plantado = json.loads((self.caixa / TITULAR.ACEITE_NOME).read_bytes())
        plantado["versao"] = 999999  # a assinatura da v2 não confere com ele
        (self.caixa / TITULAR.ACEITE_NOME).write_bytes(K.regras.canonico(plantado))
        (self.caixa / "maior-versao").write_text("999999\n", encoding="ascii")  # na caixa de entrada, nunca conta
        self.assertEqual(self.aceitar()[0], 0)
        self.assertEqual(versao(), 1)
        espelho = self.raiz / ".claude" / "projetos" / PROJETO / "hashes.json"
        espelho.write_text(json.dumps({"aceite_risco": {"versao": 7}}), encoding="utf-8")
        self.assertEqual(self.aceitar()[0], 0)
        self.assertEqual(versao(), 8 if os.name == "nt" else 2)
        espelho.write_text("[" * 200000 + "]" * 200000, encoding="utf-8")  # aninhado demais: não conta, sem traceback
        self.assertEqual(self.aceitar()[0], 0)
        if os.name == "nt":
            espelho.write_text(json.dumps({"aceite_risco": {"versao": 999999}}), encoding="utf-8")
            with self.assertRaises(TITULAR.Recusa) as ctx:
                self.aceitar()
            self.assertIn("forma do Ubuntu", str(ctx.exception))
        else:  # a área do titular (de ensaio no lugar da /etc/fundacao-ia) com a maior instalada; o espelho não conta
            espelho.write_text(json.dumps({"aceite_risco": {"versao": 999999}}), encoding="utf-8")
            area = self.base / "etc" / PROJETO / "risco"
            area.mkdir(parents=True)
            (area / "maior-versao").write_text("40\n", encoding="ascii")
            with mock.patch.object(TITULAR, "AREA_DO_ACEITE", str(self.base / "etc" / "{projeto}" / "risco")):
                self.assertEqual(self.aceitar()[0], 0)
            self.assertEqual(versao(), 41)

    def test_vigencia_pedida_e_os_limites(self):
        codigo, _ = self.aceitar(vigencia_ate="2027-04-30")
        self.assertEqual(codigo, 0)
        self.assertEqual(json.loads((self.caixa / TITULAR.ACEITE_NOME).read_bytes())["vigencia_ate"], "2027-04-30")
        shutil.rmtree(self.caixa)
        for ruim in ("2027-05-02", "2026-11-01", "amanhã", "2027-02-30"):
            with self.subTest(ruim):
                with self.assertRaises(TITULAR.Recusa):
                    self.aceitar(vigencia_ate=ruim)
                self.nada_gravado()

    def test_confirmacao_errada_nao_grava_nada(self):
        for resposta in ("", "sim", "lab-a", None):
            with self.subTest(resposta=resposta):
                codigo, texto = self.aceitar(resposta=resposta)
                self.assertEqual(codigo, 1)
                self.assertIn("nada foi assinado", texto)
                self.nada_gravado()

    def test_recusas_antes_de_pedir_a_senha(self):
        aprovado = self.base / "aprovado.json"
        aprovado.write_bytes(bytes_de(relatorio_completo(aprova=True)))
        simulado = self.base / "simulado.json"
        simulado.write_bytes(bytes_de(relatorio_completo(simulado=True)))
        repetido = self.base / "repetido.json"
        repetido.write_bytes(b'{"schema_version": "x", "schema_version": "fundacao.ensaio_isolamento/1"}')
        na_raiz = self.raiz / "projects" / PROJETO / "canario-drvfs.json"  # onde a sessão grava: nunca vale
        na_raiz.write_bytes(self.relatorio.read_bytes())
        seis_itens = self.base / "seis-itens.json"  # o formato antigo do teste: o portão nunca o aplicaria
        seis_itens.write_bytes(bytes_de(relatorio_de_seis_itens()))
        anterior_aprovado = self.base / "anterior-aprovado.json"  # incompleto que se diz aprovado
        anterior_aprovado.write_bytes(bytes_de(relatorio_anterior(aprova=True)))
        casos = {"canário aprovado": dict(canario=aprovado), "simulação": dict(canario=simulado),
                 "formato que o portão não aplica": dict(canario=seis_itens),
                 "anterior que se diz aprovado": dict(canario=anterior_aprovado),
                 "chave repetida": dict(canario=repetido), "relatório ausente": dict(canario=self.base / "nao.json"),
                 "relatório dentro da raiz": dict(canario=na_raiz),
                 "projeto sem pasta": dict(projeto="lab-a"), "projeto inválido": dict(projeto="Caso Real")}
        for nome, kw in casos.items():
            with self.subTest(nome):
                with self.assertRaises(TITULAR.Recusa):
                    self.aceitar(**kw)
                self.nada_gravado()
        self.assertEqual(self.perguntas, [])
        self.escrever_ancora("fundacao-decisao")  # a linha da 1.7.9: o namespace da ficha fora
        with self.assertRaises(TITULAR.Recusa) as ctx:
            self.aceitar()
        self.assertIn("fundacao-abertura", str(ctx.exception))
        self.nada_gravado()

    def assinar_com(self, chave: str, namespace: str, conteudo: bytes) -> bytes:
        alvo = self.base / f"assinar-{chave}-{namespace}.json"
        alvo.write_bytes(conteudo)
        subprocess.run([self.keygen, "-Y", "sign", "-f", str(self.chaves / chave), "-n", namespace, str(alvo)],
                       check=True, capture_output=True)
        return Path(str(alvo) + ".sig").read_bytes()

    def test_o_preparo_recusa_o_aceite_que_nao_e_o_assinado_para_este_relatorio(self):
        self.assertEqual(self.aceitar()[0], 0)
        arquivo, sig = self.caixa / TITULAR.ACEITE_NOME, self.caixa / (TITULAR.ACEITE_NOME + ".sig")
        bruto, assinatura = arquivo.read_bytes(), sig.read_bytes()
        casos = {
            "outro relatório": dict(canario=self.canario_instalado(sha256="e" * 64)),
            "outro Claude Code": dict(canario=self.canario_instalado(claude_sha256="d" * 64)),
            "outra forma da raiz": dict(canario={**self.canario_instalado(), "forma": "drvfs:/mnt/d"}),
            "canário aprovado ou ausente": dict(canario={"aprovado": True, "forma": "drvfs:/mnt/e"}),
            "outro projeto": dict(projeto="lab-a"),
            "vencido": dict(hoje=HOJE + timedelta(days=91)),
        }
        for nome, kw in casos.items():
            with self.subTest(nome):
                r = self.conferir(**kw)
                self.assertFalse(r["valido"], nome)
                self.assertTrue(r["motivo"])
        alterado = json.loads(bruto)
        alterado["vigencia_ate"] = "2027-04-30"
        trocas = {"aceite alterado depois de assinar": (K.regras.canonico(alterado), assinatura),
                  "assinado por outra chave": (bruto, self.assinar_com("intruso", "fundacao-abertura", bruto)),
                  "assinado no namespace das decisões": (bruto, self.assinar_com("titular-ensaio", "fundacao-decisao",
                                                                                   bruto)),
                  "fora da forma canônica": (bruto.replace(b"\n", b"\r\n"), assinatura)}
        for nome, (conteudo, s) in trocas.items():
            with self.subTest(nome):
                arquivo.write_bytes(conteudo)
                sig.write_bytes(s)
                self.assertFalse(self.conferir()["valido"], nome)
        arquivo.write_bytes(bruto)
        sig.unlink()
        self.assertFalse(self.conferir()["valido"])
        sig.write_bytes(assinatura)
        self.assertTrue(self.conferir()["valido"])

    def test_ficha_nao_serve_de_aceite_nem_o_aceite_de_ficha(self):
        self.assertEqual(self.aceitar()[0], 0)
        bruto = (self.caixa / TITULAR.ACEITE_NOME).read_bytes()
        assinatura = (self.caixa / (TITULAR.ACEITE_NOME + ".sig")).read_bytes()
        area = self.base / "ficha-area"
        area.mkdir()
        (area / "ficha-v1.json").write_bytes(bruto)
        (area / "ficha-v1.json.sig").write_bytes(assinatura)
        self.assertFalse(K.aberturas.vigente(self.raiz, PROJETO, area, hoje=HOJE)["valida"])
        ficha = {"schema_version": K.regras.SCHEMA, "ficha_id": "f1", "project_id": PROJETO, "versao": 1,
                 "motivo": "ensaio", "consequencias": "ensaio", "rede": {"dominios": ["github.com"]}}
        conteudo = K.regras.canonico(ficha)
        (self.caixa / TITULAR.ACEITE_NOME).write_bytes(conteudo)
        (self.caixa / (TITULAR.ACEITE_NOME + ".sig")).write_bytes(self.assinar_com("titular-ensaio",
                                                                                 "fundacao-abertura", conteudo))
        r = self.conferir()
        self.assertFalse(r["valido"])
        self.assertIn("esquema", r["motivo"])

    def test_linha_de_comando_tem_o_aceitar_risco(self):
        a = TITULAR.construir_parser().parse_args(["aceitar-risco", "--raiz", "R", "--projeto", PROJETO, "--canario",
                                                   "~/canario-drvfs.json", "--vigencia-ate", "2027-01-31"])
        self.assertEqual((a.acao, a.canario, a.vigencia_ate, a.chave), ("aceitar-risco", "~/canario-drvfs.json",
                                                                         "2027-01-31", None))
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            TITULAR.construir_parser().parse_args(["aceitar-risco", "--raiz", "R", "--projeto", PROJETO])


@unittest.skipUnless(LINUX, "a área do titular é do Ubuntu (WSL2): instalar-canario e instalar-projeto só no Linux")
class AceiteNoPreparo(unittest.TestCase):
    """O preparo do Ubuntu em ensaio: com o canário reprovado instalado, só o aceite assinado deste projeto e deste
    relatório deixa a ficha valer; ele fica fixado no hashes.json, e o lançador recusa abrir com o aceite vencido ou
    com outro relatório instalado."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="aceite-preparo-")).resolve()
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.skill = skill_de_ensaio(self.base)
        self.raiz = raiz_de_ensaio(self.base, self.skill)
        (self.base / "home").mkdir()
        self.claude = claude_de_ensaio(self.base / "claude-ensaio")
        self.m = carregar_preparo(self.skill)
        self.area = self.base / "area" / "projetos" / PROJETO
        self.canario = self.base / "area" / "canario" / "2.1.302.json"
        self.forma = self.m.forma_do_caminho(self.raiz.as_posix(), self.m.tipo_de_fs(self.raiz))
        if self.forma is None:
            self.skipTest("a pasta temporária fica num sistema de arquivos que o canário não prova")
        gravar_ficha_na_caixa(self.raiz, PROJETO, ficha_de_ensaio(PROJETO, 1, rede={"dominios": ["pypi.org"]},
                                                                  webfetch={"dominios": ["pypi.org"]}))
        self.hoje = date.today()

    def instalar_reprovado(self, data: str = "2026-11-02T18:49:27Z") -> str:
        aprovado = relatorio_de_canario(self.m, self.raiz, self.claude)
        ruim = relatorio_de_canario(self.m, self.raiz, self.claude, data=data, conclusao={
            "forma": aprovado["forma"], "sistema_de_arquivos": aprovado["sistema_de_arquivos"],
            "confina_comandos": False, "motivo": "plugin_setting_sources_local falhou"})
        r = instalar_canario(self.skill, self.base, ruim)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(json.loads(r.stdout)["aprovado"])
        return sha(self.canario)

    def aceitar(self, relatorio_sha256: str, projeto: str = PROJETO, caixa: str = PROJETO, **datas) -> Path:
        datas.setdefault("aceito_em", self.hoje.isoformat())
        datas.setdefault("vigencia_ate", (self.hoje + timedelta(days=30)).isoformat())
        return gravar_aceite_na_caixa(self.raiz, caixa, aceite_de_ensaio(projeto, relatorio_sha256, sha(self.claude),
                                                                         self.forma, **datas))

    def instalar(self, projeto: str = PROJETO, **kw) -> dict:
        r = instalar(self.skill, self.raiz, self.base, projeto, self.claude, **kw)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def ler(self, nome: str, area: Path | None = None) -> dict:
        return json.loads(((area or self.area) / nome).read_text(encoding="utf-8"))

    def test_sem_aceite_o_relatorio_reprovado_fecha_tudo(self):
        self.instalar_reprovado()
        rel = self.instalar()
        self.assertFalse(rel["aberturas"]["valida"])
        self.assertTrue(any("sem canário aprovado" in a for a in rel["avisos"]), rel["avisos"])
        self.assertEqual(self.ler("settings.wsl.json")["sandbox"]["network"]["allowedDomains"], [])
        self.assertIsNone(self.ler("hashes.json")["aceite_risco"])
        self.assertTrue(self.m.conferir_abertura(self.raiz, PROJETO, self.area)["ok"])

    def test_com_o_aceite_a_ficha_vale_so_neste_projeto_e_fica_fixada(self):
        relatorio = self.instalar_reprovado()
        self.aceitar(relatorio)
        previa = self.instalar(simular=True)
        self.assertTrue(previa["aberturas"]["valida"], previa)
        self.assertFalse((self.area / "risco").exists())  # a simulação não grava
        rel = self.instalar()
        self.assertTrue(rel["aberturas"]["valida"], rel)
        self.assertIn("aceite de risco", rel["aberturas"]["motivo"])
        self.assertTrue(any("canário NÃO aprovado" in a for a in rel["avisos"]), rel["avisos"])
        perfil = self.ler("settings.wsl.json")
        self.assertEqual(perfil["sandbox"]["network"]["allowedDomains"], ["pypi.org"])
        self.assertNotIn("WebFetch", perfil["permissions"]["deny"])
        hashes = self.ler("hashes.json")
        self.assertEqual(hashes["aceite_risco"]["relatorio_sha256"], relatorio)
        risco = self.area / "risco" / "aceite-risco-canario.json"
        for caminho in (self.canario, risco, Path(str(risco) + ".sig")):
            self.assertEqual(hashes["arquivos"][caminho.as_posix()], sha(caminho))
        self.assertTrue(self.m.conferir_abertura(self.raiz, PROJETO, self.area)["ok"])
        self.assertEqual(self.instalar()["aceite_risco"]["instalacao"]["acao"], "igual")
        # Outro projeto: a mesma ficha e o aceite de caso-real copiado na caixa dele não abrem nada.
        outro = self.base / "area" / "projetos" / "lab-a"
        gravar_ficha_na_caixa(self.raiz, "lab-a", ficha_de_ensaio("lab-a", 1, rede={"dominios": ["pypi.org"]}))
        self.aceitar(relatorio, projeto=PROJETO, caixa="lab-a")
        rel = self.instalar("lab-a")
        self.assertFalse(rel["aberturas"]["valida"], rel)
        self.assertEqual(self.ler("settings.wsl.json", outro)["sandbox"]["network"]["allowedDomains"], [])
        self.assertFalse((outro / "risco").exists())

    def test_aceite_de_outro_relatorio_ou_vencido_nao_vale(self):
        relatorio = self.instalar_reprovado()
        casos = {"outro relatório": dict(relatorio_sha256="e" * 64),
                 "vencido": dict(relatorio_sha256=relatorio, aceito_em=(self.hoje - timedelta(days=100)).isoformat(),
                                 vigencia_ate=(self.hoje - timedelta(days=1)).isoformat())}
        for nome, kw in casos.items():
            with self.subTest(nome):
                self.aceitar(**kw)
                rel = self.instalar()
                self.assertFalse(rel["aberturas"]["valida"], rel)
                self.assertTrue(any("não foi instalado" in a for a in rel["avisos"]), rel["avisos"])
                self.assertFalse((self.area / "risco").exists())
                self.assertEqual(self.ler("settings.wsl.json")["sandbox"]["network"]["allowedDomains"], [])

    def test_aceite_antigo_nao_volta_pela_caixa_de_entrada(self):
        """R17101-ACE-1: a área guarda a maior versão instalada (risco/maior-versao); uma cópia antiga do aceite, ou
        outro conteúdo com a mesma versão, devolvidos à caixa de entrada, não são instalados."""
        relatorio = self.instalar_reprovado()
        longo = (self.hoje + timedelta(days=90)).isoformat()
        self.aceitar(relatorio, versao=1, vigencia_ate=longo)
        antigo = {n: (self.raiz / ".claude" / "projetos" / PROJETO / "risco" / n).read_bytes()
                  for n in ("aceite-risco-canario.json", "aceite-risco-canario.json.sig")}
        self.assertTrue(self.instalar()["aberturas"]["valida"])
        self.aceitar(relatorio, versao=2)  # o titular encurta o aceite: 30 dias
        rel = self.instalar()
        self.assertEqual(rel["aceite_risco"]["aplicado"]["versao"], 2, rel)
        self.assertEqual((self.area / "risco" / "maior-versao").read_text(encoding="ascii"), "2\n")
        instalado = sha(self.area / "risco" / "aceite-risco-canario.json")
        for nome, conteudo in antigo.items():  # a sessão devolve a cópia da v1 (90 dias) à caixa de entrada
            (self.raiz / ".claude" / "projetos" / PROJETO / "risco" / nome).write_bytes(conteudo)
        rel = self.instalar()
        self.assertTrue(any("um aceite antigo não volta" in a for a in rel["avisos"]), rel["avisos"])
        self.assertEqual(sha(self.area / "risco" / "aceite-risco-canario.json"), instalado)
        self.assertEqual(rel["aceite_risco"]["aplicado"]["versao"], 2, rel)
        self.aceitar(relatorio, versao=2, vigencia_ate=longo)  # a mesma versão com outro conteúdo também não
        rel = self.instalar()
        self.assertEqual(sha(self.area / "risco" / "aceite-risco-canario.json"), instalado)
        self.assertEqual(rel["aceite_risco"]["aplicado"]["vigencia_ate"], (self.hoje + timedelta(days=30)).isoformat())

    def test_o_lancador_recusa_com_o_aceite_vencido_ou_outro_relatorio(self):
        relatorio = self.instalar_reprovado()
        self.aceitar(relatorio)
        self.assertTrue(self.instalar()["aberturas"]["valida"])
        res = self.m.conferir_abertura(self.raiz, PROJETO, self.area, hoje=self.hoje + timedelta(days=31))
        self.assertFalse(res["ok"])
        self.assertTrue(any("aceite de risco do canário venceu" in p for p in res["problemas"]), res)
        self.instalar_reprovado(data="2026-11-03T10:00:00Z")  # outro relatório reprovado, instalado depois
        res = self.m.conferir_abertura(self.raiz, PROJETO, self.area)
        self.assertFalse(res["ok"])
        self.assertTrue(any("o aceite de risco é do anterior" in p for p in res["problemas"]), res)
        rel = self.instalar()  # o preparo de novo: o aceite é do relatório anterior, e tudo fecha
        self.assertFalse(rel["aberturas"]["valida"], rel)
        self.assertEqual(self.ler("settings.wsl.json")["sandbox"]["network"]["allowedDomains"], [])
        self.assertTrue(self.m.conferir_abertura(self.raiz, PROJETO, self.area)["ok"])

    def test_gerar_e_conferir_o_perfil_usam_o_aceite_da_area(self):
        from apoio import ENV

        def rodar(*args):
            return subprocess.run([sys.executable, "-I", "-B", str(self.skill / "assets" / "host" / "preparo_host.py"),
                                   *map(str, args)], capture_output=True, text=True, encoding="utf-8", env=ENV,
                                  timeout=120)
        self.aceitar(self.instalar_reprovado())
        self.instalar()
        comum = ("--raiz", self.raiz, "--projeto", PROJETO, "--perfil-windows", "/mnt/c/Users/<usuario>",
                 "--area-raiz", self.base / "area", "--temp-base", (self.base / "tmp").as_posix())
        r = rodar("conferir-perfil-wsl", "--perfil", self.area / "settings.wsl.json", *comum)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        saida = self.base / "gerado.json"
        r = rodar("gerar-perfil-projeto", *comum, "--saida", saida)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(saida.read_text(encoding="utf-8"))["sandbox"]["network"]["allowedDomains"],
                         ["pypi.org"])


if __name__ == "__main__":
    unittest.main()
