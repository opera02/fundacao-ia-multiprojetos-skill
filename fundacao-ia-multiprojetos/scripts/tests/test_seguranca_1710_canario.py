"""Revisão de segurança da 1.7.10, rodada 4 (grupo CANARIO). CAN-1: o portão do canário recalcula a conclusão pelos
itens (o conjunto exato dos ids das sondas, uma constante com teste de igualdade com o ensaio; cada item de comando
com `passou`, o perfil gerado, o sandbox ligado e o temp do lançador) e recusa o relatório de seis campos escrito à
mão (CI-F2); o instalar mostra, como root e antes de gravar, o resumo dos itens e o SHA-256, que o `rodar` do ensaio
mostra ao gravar. CAN-2: o relatório real que não aprova (false ou null) revoga o aprovado da mesma versão, e o
preparar-wsl.sh segue para o preparo dos projetos, que fecha as aberturas. CAN-3: o `limpar` exige a configuração do
ensaio desta base na casa, com a marca do plano, recusa base com sinais de fundação e apaga cada hook só com o
SHA-256 do plano. Itens novos do canário: ler a área root de outro projeto (WSL-01) e gravar em `<raiz>/.claude`
(HOOK-F1). CI-F1: o ensaio não roda de uma cópia dentro de `<raiz>/projects/`. Cada caso falha no código de antes (a
contraprova roda este arquivo num worktree da base). Pastas descartáveis, dados fictícios; nada abre o Claude Code. O
que grava a área do titular e roda o preparar-wsl.sh é do Ubuntu (pulado no Windows, com o motivo)."""

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
from pathlib import Path
from unittest import mock

import test_host_wsl as hw
from apoio import SCRIPTS, SKILL
from test_ensaio_isolamento import (HOOKS, LINUX, Base, _ctx, copia_do_script, executor_bom, executor_ruim, indice,
                                    rodar_copia, transcricao)
from test_host_projeto_apoio import (carregar_preparo, claude_de_ensaio, ficha_de_ensaio, gravar_ficha_na_caixa,
                                     instalar, instalar_canario, raiz_de_ensaio, sha, skill_de_ensaio)

SHA_CLAUDE = "c" * 64
NOVOS = ("leitura_area_outro_projeto", "escrita_claude_da_raiz")
# 1.7.11 (C01, C13, M1 a M3): as sondas do ensaio do lote B em diante, de classe medida ou carga (fora do portão)
NOVOS_1711 = ("modo_sem_perguntas", "sudo_na_sessao", "rede_em_mnt", "conectores_da_conta", "subagentes",
              "agents_md_exclusao", "mencao_arroba")
TODOS_NOVOS = NOVOS + NOVOS_1711


def carregar_ensaio():
    """O ensaio desta árvore, pelo caminho (carregar não cria nada)."""
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("ensaio_seguranca_1710", SCRIPTS / "ensaio_isolamento_wsl.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def carregar_titular():
    """A ferramenta fixa do titular desta árvore, pelo caminho (aceitar-risco usa a mesma regra do portão)."""
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("titular_seguranca_1711",
                                                  SKILL / "assets" / "host" / "fundacao_titular.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def itens_do_ensaio(ensaio, trocas: dict | None = None) -> list:
    """Os itens que o ensaio desta árvore produz (os ids e as classes das SONDAS dele): comando e carga com `passou`,
    o informativo `nao_medido`; `trocas` muda o veredito de um id."""
    trocas = trocas or {}
    return [{"id": s["id"], "classe": s["classe"], "motivo": "ensaio",
             "veredito": trocas.get(s["id"], "nao_medido" if s["classe"] == "informativo" else "passou")}
            for s in ensaio.SONDAS]


def relatorio_real(ensaio, *, forma="ext4", fs="ext4", sha_claude=SHA_CLAUDE, trocas=None, confina=True,
                   **mudancas) -> dict:
    """Um relatório completo como o do ensaio real (o que o `rodar` grava), aprovado por padrão."""
    rel = {"schema_version": "fundacao.ensaio_isolamento/1", "data": "2026-11-01T12:00:00Z", "simulado": False,
           "forma": forma, "base": "/home/ensaio/canario", "projeto": "ensaio-a", "sistema_de_arquivos": fs,
           "claude": {"binario": "/home/ensaio/claude", "versao": "2.1.302", "sha256": sha_claude},
           "sandbox_ligado": True, "seccomp_presente": None, "perfil": {"gerado": True, "veredito": "passou"},
           "temp": {"base": "/tmp", "do_lancador": True}, "itens": itens_do_ensaio(ensaio, trocas),
           "conclusao": {"forma": forma, "sistema_de_arquivos": fs, "confina_comandos": confina, "motivo": "ensaio"}}
    rel.update(mudancas)
    return rel


def relatorio_anterior(ensaio, *, confina=False, trocas=None, **mudancas) -> dict:
    """O relatório do ensaio da 1.7.10 e da 1.7.10.1: o completo sem as sondas que o ensaio não tinha (as `NOVOS` e as
    `NOVOS_1711`). Por padrão reprovado (conclusão false), como o que o titular instalou em 02/11/2026."""
    rel = relatorio_real(ensaio, confina=confina, trocas=trocas, **mudancas)
    rel["itens"] = [i for i in rel["itens"] if i["id"] not in TODOS_NOVOS]
    return rel


def relatorio_do_lote_b(ensaio, *, confina=True, trocas=None, **mudancas) -> dict:
    """O relatório de um ensaio do lote B (a árvore antes da 1.7.11 completa): tem as duas sondas de `NOVOS`, mas não as
    de `NOVOS_1711`. Pode se dizer aprovado e nunca aprova."""
    rel = relatorio_real(ensaio, confina=confina, trocas=trocas, **mudancas)
    rel["itens"] = [i for i in rel["itens"] if i["id"] not in NOVOS_1711]
    return rel


def seis_campos(forma="ext4", fs="ext4") -> dict:
    """O relatório de seis campos escrito à mão do achado (CI-F2, o A do CAN-1): sem nenhum item medido."""
    return {"schema_version": "fundacao.ensaio_isolamento/1", "simulado": False, "forma": forma,
            "sistema_de_arquivos": fs, "claude": {"versao": "2.1.302", "sha256": SHA_CLAUDE},
            "conclusao": {"confina_comandos": True}}


def so_o_booleano_trocado(ensaio) -> dict:
    """O B do CAN-1: drvfs, todos os itens de comando com `falhou`, o perfil não gerado, o sandbox desligado e o temp
    fora do lançador, e só o booleano da conclusão trocado para true."""
    trocas = {s["id"]: "falhou" for s in ensaio.SONDAS if s["classe"] == "comando"}
    return relatorio_real(ensaio, forma="drvfs:/mnt/e/Ensaio", fs="9p", trocas=trocas, sandbox_ligado=False,
                          perfil={"gerado": False, "veredito": "nao_medido"}, temp={"base": "/x", "do_lancador": False})


def fotografia(pasta: Path) -> dict:
    """Cada nome abaixo de `pasta` com o SHA-256 (ou `<pasta>`), sem seguir ligação."""
    saida = {}
    for p in sorted(Path(pasta).rglob("*")):
        rel = p.relative_to(pasta).as_posix()
        saida[rel] = "<pasta>" if p.is_dir() and not p.is_symlink() else hashlib.sha256(p.read_bytes()).hexdigest()
    return saida


class PortaoRecalculaPelosItens(unittest.TestCase):
    """CAN-1 e CI-F2, nas peças puras (em qualquer sistema)."""

    def setUp(self):
        self.m = carregar_preparo()
        self.ensaio = carregar_ensaio()

    def conferir(self, rel, forma="ext4"):
        return self.m.conferir_relatorio_do_canario(rel, claude_versao="2.1.302", claude_sha256=SHA_CLAUDE,
                                                    forma=forma)

    def test_a_constante_dos_ids_e_a_do_ensaio(self):
        """Teste de igualdade entre as duas pontas: os ids e a classe de cada sonda."""
        self.assertEqual(self.m.SONDAS_DO_CANARIO, {s["id"]: s["classe"] for s in self.ensaio.SONDAS})
        for novo in NOVOS:
            self.assertEqual(self.m.SONDAS_DO_CANARIO[novo], "comando")
        for novo, classe in zip(NOVOS_1711, ("medida", "medida", "medida", "medida", "medida", "carga", "carga")):
            self.assertEqual(self.m.SONDAS_DO_CANARIO[novo], classe, novo)

    def test_o_relatorio_completo_aprova(self):
        self.assertIsNone(self.conferir(relatorio_real(self.ensaio)))
        self.assertIsNone(self.conferir(relatorio_real(self.ensaio, forma="drvfs:/mnt/e/x", fs="9p"),
                                        forma="drvfs:/mnt/e"))

    def test_o_de_seis_campos_escrito_a_mao_e_recusado(self):
        self.assertTrue(self.conferir(seis_campos()))
        com_a_conclusao_inteira = seis_campos()  # nem com a forma e o sistema de arquivos também na conclusão
        com_a_conclusao_inteira["conclusao"].update(forma="ext4", sistema_de_arquivos="ext4")
        motivo = self.conferir(com_a_conclusao_inteira)
        self.assertTrue(motivo)
        self.assertIn("itens", motivo)

    def test_so_o_booleano_trocado_nao_aprova(self):
        motivo = self.conferir(so_o_booleano_trocado(self.ensaio), forma="drvfs:/mnt/e")
        self.assertTrue(motivo)
        self.assertIn("recalculada pelos itens", motivo)

    def test_cada_condicao_recalculada_recusa(self):
        def com(**kw):
            return relatorio_real(self.ensaio, **kw)

        sem_um = com()
        sem_um["itens"] = [i for i in sem_um["itens"] if i["id"] != "leitura_state"]  # não é das adiadas
        repetido = com()
        repetido["itens"].append(dict(repetido["itens"][0]))
        a_mais = com()
        a_mais["itens"].append({"id": "sonda_inventada", "classe": "comando", "veredito": "passou"})
        rotulado = com()
        rotulado["itens"][0]["classe"] = "informativo"  # um item de comando não escapa pelo rótulo
        casos = {
            "um item de comando falhou": com(trocas={"escrita_claude_da_raiz": "falhou"}),
            "um item de comando não medido": com(trocas={"leitura_area_outro_projeto": "nao_medido"}),
            "veredito fora do ensaio": com(trocas={"rede_fora_da_lista": "ok"}),
            "falta um item": sem_um, "item repetido": repetido, "item a mais": a_mais,
            "item de comando rotulado informativo": rotulado,
            "perfil não gerado": com(perfil={"gerado": False}),
            "sem o perfil": com(perfil=None),
            "sandbox não ligado": com(sandbox_ligado=None),
            "temp fora do lançador": com(temp={"do_lancador": False}),
            "conclusão de outro sistema de arquivos": com(conclusao={"forma": "ext4", "sistema_de_arquivos": "9p",
                                                                     "confina_comandos": True}),
            "itens que não são lista": com(itens={"leitura_state": "passou"}),
        }
        for nome, rel in casos.items():
            with self.subTest(nome):
                self.assertTrue(self.conferir(rel), nome)

    def test_o_portao_recusa_o_relatorio_de_seis_campos_na_area(self):
        base = Path(tempfile.mkdtemp(prefix="canario-seis-1710-"))
        try:
            area = base / "area"
            (area / "canario").mkdir(parents=True)
            (area / "canario" / "2.1.302.json").write_text(json.dumps(seis_campos()), encoding="utf-8")
            portao = self.m.portao_do_canario(area, claude_versao="2.1.302", claude_sha256=SHA_CLAUDE,
                                              raiz_wsl="/home/titular/fundacao", fs_raiz="ext4")
            self.assertFalse(portao["aprovado"], portao)
            (area / "canario" / "2.1.302.json").write_text(json.dumps(relatorio_real(self.ensaio)), encoding="utf-8")
            self.assertTrue(self.m.portao_do_canario(area, claude_versao="2.1.302", claude_sha256=SHA_CLAUDE,
                                                     raiz_wsl="/home/titular/fundacao", fs_raiz="ext4")["aprovado"])
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_classificar_o_que_o_instalar_faz(self):
        """CAN-1 e CAN-2 sem gravar: o real que aprova vai como aprovação; o real com false ou null, como revogação;
        o que não é relatório real (seis campos, simulação) é recusado. O resumo traz o SHA-256 e cada item."""
        classificar = self.m.classificar_relatorio_do_canario
        aprovado = json.dumps(relatorio_real(self.ensaio)).encode("utf-8")
        cl = classificar(aprovado)
        self.assertTrue(cl["aprovado"])
        self.assertIsNone(cl["motivo"])
        self.assertEqual(cl["sha256"], hashlib.sha256(aprovado).hexdigest())
        texto = "\n".join(cl["resumo"])
        self.assertIn(cl["sha256"], texto)
        for s in self.ensaio.SONDAS:
            self.assertIn(s["id"], texto)
        self.assertIn("vai como aprovação", texto)
        for confina, trocas in ((False, {"escrita_fora_do_projeto": "falhou"}),
                                (None, {"rede_fora_da_lista": "nao_medido"})):
            with self.subTest(confina=confina):
                cl = classificar(json.dumps(relatorio_real(self.ensaio, trocas=trocas, confina=confina)).encode())
                self.assertFalse(cl["aprovado"])
                self.assertTrue(cl["motivo"])
                self.assertIn("vai como revogação", "\n".join(cl["resumo"]))
        # 1.7.11 (item 2 da revisão da junção): o que diz true mas que o recálculo pelos itens não confirma é incoerente
        # e é recusado, em vez de instalado como revogação que o preparar-wsl.sh descreveria como "false ou null".
        for nome, rel in (("seis campos", seis_campos()), ("simulação", relatorio_real(self.ensaio, simulado=True)),
                          ("só o booleano trocado", so_o_booleano_trocado(self.ensaio)),
                          ("true com um item de comando falhando",
                           relatorio_real(self.ensaio, trocas={"escrita_fora_do_projeto": "falhou"})),
                          ("true sem o sandbox", relatorio_real(self.ensaio, sandbox_ligado=False)),
                          ("true sem o perfil gerado", relatorio_real(self.ensaio, perfil={"gerado": False})),
                          ("true com o temp fora do lançador", relatorio_real(self.ensaio, temp={"do_lancador": False}))):
            with self.subTest(nome):
                with self.assertRaises(self.m.EntradaInvalida):
                    classificar(json.dumps(rel).encode("utf-8"))


    # ------------------------------------------------------------------ 1.7.11, N1: sonda que falta só baixa a confiança
    def test_as_sondas_adiadas_sao_as_que_o_ensaio_anterior_nao_tinha(self):
        """(d) `SONDAS_ADIADAS` está contido em `SONDAS_DO_CANARIO` e é exatamente o que o ensaio da 1.7.10 e da 1.7.10.1
        não tinha (as duas de comando de `NOVOS`) mais o que a 1.7.11 acrescentou (`NOVOS_1711`: medidas e cargas, que
        o portão não conta)."""
        self.assertEqual(self.m.SONDAS_ADIADAS, frozenset(TODOS_NOVOS))
        kit = self.m.modulo_do_canario()  # as duas partes da lista ficam só no kit (o preparo expõe a soma)
        self.assertEqual(kit.SONDAS_DA_1710, frozenset(NOVOS))
        self.assertEqual(kit.SONDAS_DA_1711, frozenset(NOVOS_1711))
        self.assertTrue(self.m.SONDAS_ADIADAS <= set(self.m.SONDAS_DO_CANARIO))
        for ident in NOVOS:
            self.assertEqual(self.m.SONDAS_DO_CANARIO[ident], "comando")
        for ident in NOVOS_1711:
            self.assertIn(self.m.SONDAS_DO_CANARIO[ident], ("medida", "carga"))
        self.assertEqual(len(self.m.SONDAS_DO_CANARIO) - len(self.m.SONDAS_ADIADAS), 10)
        anterior = relatorio_anterior(self.ensaio)
        self.assertEqual(len(anterior["itens"]), 10)
        self.assertEqual(self.m.sondas_ausentes(anterior), sorted(TODOS_NOVOS))
        self.assertEqual(self.m.sondas_ausentes(relatorio_do_lote_b(self.ensaio)), sorted(NOVOS_1711))
        self.assertEqual(self.m.sondas_ausentes(relatorio_real(self.ensaio)), [])

    def test_sem_o_kit_o_acesso_dinamico_levanta_attributeerror(self):
        """O `__getattr__` do módulo traduz a falta do kit em AttributeError (`hasattr` dá False)."""
        falta = mock.patch.object(self.m, "modulo_do_canario", side_effect=self.m.EntradaInvalida("sem kit"))
        with falta:
            self.assertFalse(hasattr(self.m, "SONDAS_DO_CANARIO"))
            with self.assertRaises(AttributeError):
                self.m.VEREDITOS_DO_CANARIO
        self.assertTrue(hasattr(self.m, "SONDAS_DO_CANARIO"))

    def test_sonda_nova_so_baixa_a_confianca(self):
        """1.7.11: toda sonda nova entra pela regra de transição. O relatório do lote B (sem as `NOVOS_1711`) segue um
        relatório real, mas nunca aprova, e o aceite de risco dele conta as que faltam como não medidas; já o completo
        aprova mesmo com uma medida ou uma carga `falhou` ou `nao_medido` (a classe delas não entra no portão)."""
        lote_b = relatorio_do_lote_b(self.ensaio)
        self.assertIsNone(self.m.estrutura_do_relatorio_do_canario(lote_b))
        self.assertIn("ensaio anterior", self.conferir(lote_b))
        reprovado = relatorio_do_lote_b(self.ensaio, confina=False, trocas={"escrita_fora_do_projeto": "falhou"})
        self.assertIsNone(self.m.estrutura_do_relatorio_do_canario(reprovado))
        cl = self.m.classificar_relatorio_do_canario(json.dumps(reprovado).encode("utf-8"))
        self.assertIs(cl["aprovado"], False)
        for ausente in NOVOS_1711:
            self.assertIn(f"{ausente} ({self.m.SONDAS_DO_CANARIO[ausente]}): ausente (ensaio anterior; conta como "
                          "não medido)", chr(10).join(cl["resumo"]))
        trocas = {"sudo_na_sessao": "falhou", "conectores_da_conta": "nao_medido", "subagentes": "falhou",
                  "agents_md_exclusao": "falhou", "modo_sem_perguntas": "nao_medido"}
        self.assertIsNone(self.conferir(relatorio_real(self.ensaio, trocas=trocas)))

    def test_o_relatorio_anterior_reprovado_continua_reprovado_e_nunca_aprova(self):
        """(a) o anterior (completo menos as 2 adiadas, conclusão false) tem a estrutura aceita, o portão dá `reprovado`
        com o SHA-256 do arquivo, e o `classificar` dá aprovado False, com as duas sondas como ausentes no resumo. (b) o
        anterior que diz true, com todas as de comando `passou`, é recusado no `classificar` e, instalado, o portão dá
        aprovado False e sem `reprovado` (nenhum aceite se prende a ele)."""
        reprovado = relatorio_anterior(self.ensaio, trocas={"escrita_fora_do_projeto": "falhou"})
        self.assertIsNone(self.m.estrutura_do_relatorio_do_canario(reprovado))
        bruto = json.dumps(reprovado).encode("utf-8")
        cl = self.m.classificar_relatorio_do_canario(bruto)
        self.assertIs(cl["aprovado"], False)
        texto = "\n".join(cl["resumo"])
        for ausente in TODOS_NOVOS:
            self.assertIn(f"{ausente} ({self.m.SONDAS_DO_CANARIO[ausente]}): ausente (ensaio anterior; conta como não "
                          "medido)", texto)
        aprovado_falso = relatorio_anterior(self.ensaio, confina=True)
        self.assertIsNone(self.m.estrutura_do_relatorio_do_canario(aprovado_falso))
        motivo = self.conferir(aprovado_falso)
        self.assertIn("ensaio anterior", motivo)
        for ausente in TODOS_NOVOS:
            self.assertIn(ausente, motivo)
        with self.assertRaises(self.m.EntradaInvalida) as ctx:
            self.m.classificar_relatorio_do_canario(json.dumps(aprovado_falso).encode("utf-8"))
        self.assertIn("ensaio anterior", str(ctx.exception))
        base = Path(tempfile.mkdtemp(prefix="canario-anterior-1711-"))
        try:
            area = base / "area"
            (area / "canario").mkdir(parents=True)
            arquivo = area / "canario" / "2.1.302.json"
            kw = dict(claude_versao="2.1.302", claude_sha256=SHA_CLAUDE, raiz_wsl="/home/titular/fundacao",
                      fs_raiz="ext4")
            arquivo.write_bytes(bruto)
            portao = self.m.portao_do_canario(area, **kw)
            self.assertFalse(portao["aprovado"], portao)
            self.assertEqual(portao["reprovado"]["sha256"], hashlib.sha256(bruto).hexdigest())
            self.assertIs(portao["reprovado"]["confina_comandos"], False)
            nulo = json.dumps(relatorio_anterior(self.ensaio, confina=None)).encode("utf-8")
            arquivo.write_bytes(nulo)
            self.assertEqual(self.m.portao_do_canario(area, **kw)["reprovado"]["sha256"],
                             hashlib.sha256(nulo).hexdigest())
            arquivo.write_bytes(json.dumps(aprovado_falso).encode("utf-8"))  # só chegaria assim por mão alheia
            portao = self.m.portao_do_canario(area, **kw)
            self.assertFalse(portao["aprovado"], portao)
            self.assertNotIn("reprovado", portao)
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_faltar_uma_sonda_que_nao_e_adiada_recusa(self):
        """(c) só as `SONDAS_ADIADAS` podem faltar: nem no completo nem no anterior falta outra, e id de fora não entra."""
        completo = relatorio_real(self.ensaio)
        anterior = relatorio_anterior(self.ensaio)
        casos = {}
        for ident in self.m.SONDAS_DO_CANARIO:
            if ident in self.m.SONDAS_ADIADAS:
                continue
            casos[f"completo sem {ident}"] = {**completo, "itens": [i for i in completo["itens"] if i["id"] != ident]}
            casos[f"anterior sem {ident}"] = {**anterior, "itens": [i for i in anterior["itens"] if i["id"] != ident]}
        casos["anterior com id de fora"] = {**anterior, "itens": [*anterior["itens"], {
            "id": "sonda_inventada", "classe": "comando", "veredito": "passou"}]}
        casos["anterior com item repetido"] = {**anterior, "itens": [*anterior["itens"], dict(anterior["itens"][0])]}
        for nome, rel in casos.items():
            with self.subTest(nome):
                self.assertTrue(self.m.estrutura_do_relatorio_do_canario(rel), nome)
                with self.assertRaises(self.m.EntradaInvalida):
                    self.m.classificar_relatorio_do_canario(json.dumps(rel).encode("utf-8"))
        # uma só das duas adiadas que falte também é de um ensaio anterior (conta como ausente) e nunca aprova
        so_uma = {**completo, "itens": [i for i in completo["itens"] if i["id"] != NOVOS[0]]}
        self.assertIsNone(self.m.estrutura_do_relatorio_do_canario(so_uma))
        self.assertEqual(self.m.sondas_ausentes(so_uma), [NOVOS[0]])
        self.assertIn("ensaio anterior", self.conferir(so_uma))

    def test_a_ferramenta_do_titular_usa_a_mesma_regra_da_estrutura(self):
        """Item 3 da revisão da junção, a forma recomendada: a ferramenta carrega o `canario.py` do kit, o mesmo módulo
        do preparo; o resultado de `estrutura` é o mesmo nos dois para os relatórios deste arquivo."""
        titular = carregar_titular()
        regra = titular.regra_do_canario()
        rels = [relatorio_real(self.ensaio), relatorio_anterior(self.ensaio), seis_campos(),
                so_o_booleano_trocado(self.ensaio), relatorio_real(self.ensaio, simulado=True),
                relatorio_real(self.ensaio, perfil=None)]
        for rel in rels:
            self.assertEqual(regra.estrutura(rel), self.m.estrutura_do_relatorio_do_canario(rel))
        self.assertEqual(regra.SONDAS_DO_CANARIO, {s["id"]: s["classe"] for s in self.ensaio.SONDAS})


class RelatorioDoEnsaioContinuaAceito(Base):
    """O relatório que o ensaio desta árvore grava (executor de teste que confina) passa no portão; o que vaza não; e o
    `rodar` mostra o SHA-256 do que gravou (CAN-1)."""

    def setUp(self):
        super().setUp()
        self.m = carregar_preparo()

    def rodar(self, executor_de):
        plano = self.mod.preparar(self.base)
        return self.mod.rodar(self.base, executor=executor_de(plano["nonce"]), claude_versao="2.1.302",
                              claude_sha256=SHA_CLAUDE, perfil_info={"gerado": True, "veredito": "passou"},
                              sandbox_ligado=True, linux=True, contexto=_ctx())

    def test_o_que_confina_e_aceito_e_o_que_vaza_revoga(self):
        rel = self.rodar(executor_bom)
        self.assertIs(rel["conclusao"]["confina_comandos"], True)
        self.assertIsNone(self.m.conferir_relatorio_do_canario(rel, claude_versao="2.1.302", claude_sha256=SHA_CLAUDE,
                                                               forma="ext4"))
        self.assertTrue(self.m.classificar_relatorio_do_canario(json.dumps(rel).encode("utf-8"))["aprovado"])
        self.mod.limpar(self.base)
        rel = self.rodar(executor_ruim)
        self.assertIs(rel["conclusao"]["confina_comandos"], False)
        cl = self.m.classificar_relatorio_do_canario(json.dumps(rel).encode("utf-8"))  # real: não é recusado
        self.assertFalse(cl["aprovado"])

    def test_o_rodar_mostra_o_sha256_do_relatorio_gravado(self):
        destino = self.tmp / "relatorio.json"
        erro = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(erro):
            self.mod._saida({"schema_version": "fundacao.ensaio_isolamento/1", "itens": []}, str(destino))
        self.assertIn(hashlib.sha256(destino.read_bytes()).hexdigest(), erro.getvalue())


@unittest.skipUnless(LINUX, "a área do titular é do Ubuntu (WSL2): instalar-canario e instalar-projeto só no Linux")
class RevogacaoNaAreaDoTitular(unittest.TestCase):
    """CAN-2: um canário reprovado depois de um aprovado da mesma versão revoga (antes, o aprovado ficava)."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="canario-revoga-1710-")).resolve()
        self.skill = skill_de_ensaio(self.base)
        self.raiz = raiz_de_ensaio(self.base, self.skill)
        (self.base / "home").mkdir()
        self.claude = claude_de_ensaio(self.base / "claude-ensaio")
        self.m = carregar_preparo(self.skill)
        self.ensaio = carregar_ensaio()
        self.area = self.base / "area" / "projetos" / "caso-real"
        self.canario = self.base / "area" / "canario" / "2.1.302.json"
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 1, rede={"dominios": ["pypi.org"]},
                                                                      webfetch={"dominios": ["pypi.org"]}))

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def rel(self, **kw) -> dict:
        fs = self.m.tipo_de_fs(self.raiz)
        forma = self.m.forma_do_caminho(self.raiz.as_posix(), fs)
        if forma is None:
            raise unittest.SkipTest(f"a pasta temporária fica num sistema de arquivos ({fs}) que o canário não prova")
        forma = "ext4" if forma == "ext4" else forma + "/ensaio-canario"
        return relatorio_real(self.ensaio, forma=forma, fs=fs, sha_claude=sha(self.claude), **kw)

    def instalar(self):
        r = instalar(self.skill, self.raiz, self.base, "caso-real", self.claude)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def perfil(self) -> dict:
        return json.loads((self.area / "settings.wsl.json").read_text(encoding="utf-8"))

    def aberto(self) -> bool:
        perfil = self.perfil()
        return perfil["sandbox"]["network"]["allowedDomains"] == ["pypi.org"] and \
            "WebFetch" not in perfil["permissions"]["deny"]

    def test_aprovado_e_depois_reprovado_revoga_e_o_preparo_fecha(self):
        for confina, trocas in ((False, {"escrita_fora_do_projeto": "falhou"}),
                                (None, {"rede_fora_da_lista": "nao_medido"})):
            with self.subTest(confina=confina):
                r = instalar_canario(self.skill, self.base, self.rel())
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn(json.loads(r.stdout)["acao"], ("criar", "atualizar"))
                self.assertTrue(self.instalar()["canario"]["aprovado"])
                self.assertTrue(self.aberto())
                reprovado = self.rel(trocas=trocas, confina=confina)
                r = instalar_canario(self.skill, self.base, reprovado)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # antes: recusado (2) e o aprovado ficava
                saida = json.loads(r.stdout)
                self.assertIs(saida["aprovado"], False)
                self.assertEqual(saida["acao"], "atualizar")
                self.assertEqual(sha(self.canario), sha(self.base / "relatorio-canario.json"))
                self.assertIn("vai como revogação", r.stderr)
                portao = self.m.portao_do_canario(self.base / "area", claude_versao="2.1.302",
                                                  claude_sha256=sha(self.claude), raiz_wsl=self.raiz.as_posix())
                self.assertFalse(portao["aprovado"], portao)
                abertura = self.m.conferir_abertura(self.raiz, "caso-real", self.area)
                self.assertFalse(abertura["ok"])  # o lançador recusa até o preparo seguinte
                self.assertTrue(any("canário" in p for p in abertura["problemas"]), abertura)
                rel = self.instalar()
                self.assertFalse(rel["canario"]["aprovado"])
                self.assertFalse(self.aberto())
                self.assertEqual(self.perfil()["sandbox"]["network"]["allowedDomains"], [])
                self.assertFalse(json.loads((self.area / "aberturas.json").read_text(encoding="utf-8"))["valida"])
                self.assertTrue(self.m.conferir_abertura(self.raiz, "caso-real", self.area)["ok"])

    def rel_anterior(self, **kw) -> dict:
        """O relatório da 1.7.10 e da 1.7.10.1 desta raiz: o completo sem as sondas novas."""
        rel = self.rel(**kw)
        rel["itens"] = [i for i in rel["itens"] if i["id"] not in TODOS_NOVOS]
        return rel

    def test_o_anterior_aprovado_ja_instalado_fecha_no_preparo_seguinte(self):
        """1.7.11, N1: o relatório da 1.7.10.1 que dizia aprovado e já está na área do titular (instalado antes do lote B)
        deixa de aprovar: sonda que falta só baixa a confiança. O lançador recusa abrir até o preparo seguinte, que
        fecha as aberturas; o portão não o trata como reprovado (nenhum aceite se prende a ele)."""
        r = instalar_canario(self.skill, self.base, self.rel())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.instalar()["canario"]["aprovado"])
        self.assertTrue(self.aberto())
        self.canario.write_text(json.dumps(self.rel_anterior()), encoding="utf-8")  # como a 1.7.10.1 o instalou
        portao = self.m.portao_do_canario(self.base / "area", claude_versao="2.1.302", claude_sha256=sha(self.claude),
                                          raiz_wsl=self.raiz.as_posix())
        self.assertFalse(portao["aprovado"], portao)
        self.assertNotIn("reprovado", portao)
        self.assertIn("ensaio anterior", portao["motivo"])
        abertura = self.m.conferir_abertura(self.raiz, "caso-real", self.area)
        self.assertFalse(abertura["ok"])  # o lançador recusa até o preparo seguinte
        self.assertTrue(any("canário" in p for p in abertura["problemas"]), abertura)
        rel = self.instalar()
        self.assertFalse(rel["canario"]["aprovado"])
        self.assertFalse(self.aberto())
        self.assertEqual(self.perfil()["sandbox"]["network"]["allowedDomains"], [])
        self.assertTrue(self.m.conferir_abertura(self.raiz, "caso-real", self.area)["ok"])

    def test_o_anterior_reprovado_ja_instalado_continua_reprovado(self):
        """1.7.11, N1: o reprovado da 1.7.10.1 (sem as duas sondas novas) segue reprovado no portão, com o SHA-256 do
        arquivo, para o aceite de risco assinado para ele."""
        reprovado = self.rel_anterior(confina=False, trocas={"escrita_fora_do_projeto": "falhou"})
        r = instalar_canario(self.skill, self.base, reprovado)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # reprovado de ensaio anterior: instalado como revogação
        self.assertIs(json.loads(r.stdout)["aprovado"], False)
        portao = self.m.portao_do_canario(self.base / "area", claude_versao="2.1.302", claude_sha256=sha(self.claude),
                                          raiz_wsl=self.raiz.as_posix())
        self.assertFalse(portao["aprovado"], portao)
        self.assertEqual(portao["reprovado"]["sha256"], sha(self.canario))

    def test_o_incoerente_e_o_anterior_aprovado_sao_recusados_e_o_aprovado_fica(self):
        """1.7.11 (item 2 da revisão da junção): o que diz true sem os itens confirmarem não é instalado como revogação."""
        r = instalar_canario(self.skill, self.base, self.rel())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        antes = sha(self.canario)
        incoerente = self.rel(trocas={"escrita_fora_do_projeto": "falhou"})  # confina true com um item de comando falhando
        for nome, rel in (("incoerente", incoerente), ("anterior que se diz aprovado", self.rel_anterior())):
            with self.subTest(nome):
                r = instalar_canario(self.skill, self.base, rel)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("recusado", r.stdout)
                self.assertEqual(sha(self.canario), antes)

    def test_o_resumo_sai_no_stderr_antes_de_gravar_com_o_sha256(self):
        r = instalar_canario(self.skill, self.base, self.rel())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(sha(self.canario), r.stderr)
        for s in self.ensaio.SONDAS:
            self.assertIn(s["id"], r.stderr)
        self.assertIn("vai como aprovação", r.stderr)
        json.loads(r.stdout)  # o stdout continua só com o JSON que o preparar-wsl.sh lê

    def test_o_de_seis_campos_e_recusado_e_o_aprovado_fica(self):
        r = instalar_canario(self.skill, self.base, self.rel())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        antes = sha(self.canario)
        r = instalar_canario(self.skill, self.base, seis_campos())
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("recusado", r.stdout)
        self.assertEqual(sha(self.canario), antes)


@unittest.skipUnless(hw.PODE, "1.7.10: o preparar-wsl.sh grava a área do titular no Linux (bash e /usr/bin/python3)")
class RevogacaoPeloPreparoDoUbuntu(unittest.TestCase):
    """CAN-2 pelo preparar-wsl.sh: com o relatório real que não aprova, a linha [revogar] canario e o preparo dos
    projetos segue e fecha o perfil (antes: [erro] canario, código 1, sem os projetos, e o aprovado ficava). O resumo
    dos itens (CAN-1) passa pelo stderr do script."""

    setUp = hw.PrepararWslNoBash.setUp
    tearDown = hw.PrepararWslNoBash.tearDown
    preparar_wsl = hw.PrepararWslNoBash.preparar_wsl

    def test_aprovado_e_depois_reprovado_pelo_preparar_wsl(self):
        gravar_ficha_na_caixa(self.raiz, "caso-real", ficha_de_ensaio("caso-real", 1, rede={"dominios": ["pypi.org"]},
                                                                      webfetch={"dominios": ["pypi.org"]}))
        m, ensaio = carregar_preparo(self.skill), carregar_ensaio()
        fs = m.tipo_de_fs(self.raiz)
        forma = m.forma_do_caminho(self.raiz.as_posix(), fs)
        if forma is None:
            self.skipTest(f"a pasta temporária fica num sistema de arquivos ({fs}) que o canário não prova")
        forma = "ext4" if forma == "ext4" else forma + "/ensaio-canario"
        arquivo = self.base / "relatorio-canario.json"
        perfil = self.base / "area" / "projetos" / "caso-real" / "settings.wsl.json"
        arquivo.write_text(json.dumps(relatorio_real(ensaio, forma=forma, fs=fs, sha_claude=sha(self.binario))),
                           encoding="utf-8")
        r = self.preparar_wsl("--claude-sha256", sha(self.binario), "--canario", arquivo, wsl=True, pacotes=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("[criar] canario:", r.stdout)
        self.assertEqual(json.loads(perfil.read_text(encoding="utf-8"))["sandbox"]["network"]["allowedDomains"],
                         ["pypi.org"])
        reprovado = relatorio_real(ensaio, forma=forma, fs=fs, sha_claude=sha(self.binario), confina=False,
                                   trocas={"leitura_area_outro_projeto": "falhou"})
        arquivo.write_text(json.dumps(reprovado), encoding="utf-8")
        r = self.preparar_wsl("--claude-sha256", sha(self.binario), "--canario", arquivo, wsl=True, pacotes=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # antes: [erro] canario, código 1, sem os projetos
        self.assertIn("[revogar] canario:", r.stdout)
        self.assertTrue([l for l in r.stdout.splitlines() if "projeto caso-real" in l], r.stdout)
        self.assertEqual(sha(self.base / "area" / "canario" / "2.1.302.json"), sha(arquivo))
        self.assertEqual(json.loads(perfil.read_text(encoding="utf-8"))["sandbox"]["network"]["allowedDomains"], [])
        self.assertIn(sha(arquivo), r.stderr)  # o resumo dos itens, que o root mostra antes de gravar (CAN-1)
        self.assertIn("vai como revogação", r.stderr)


class LimparSoABaseDoEnsaio(Base):
    """CAN-3 (em qualquer sistema): o plano.json tem marcador constante, e qualquer um o planta."""

    def plantar_plano(self, pasta: Path, **extra) -> None:
        (pasta / "plano.json").write_text(json.dumps({"schema_version": self.mod.ESQUEMA_PLANO,
                                                      "marcador": self.mod.MARCADOR, **extra}), encoding="utf-8")

    def hooks_de_verdade(self, pasta: Path) -> dict:
        hooks = pasta / ".claude" / "hooks"
        hooks.mkdir(parents=True)
        for nome in HOOKS:
            (hooks / nome).write_text(f"# hook de verdade: {nome}\n", encoding="utf-8")
        return {nome: hashlib.sha256((hooks / nome).read_bytes()).hexdigest() for nome in HOOKS}

    def plantar_config(self, pasta: Path) -> dict:
        """A configuração do ensaio desta pasta plantada na casa, com a marca do plano: a prova passa."""
        cfg = self.mod.config_do_ensaio(pasta)
        cfg.mkdir(parents=True)
        (cfg / ".ensaio-isolamento").write_text("0123456789abcdef\n", encoding="utf-8")
        st = os.lstat(cfg)
        return {"caminho": cfg.as_posix(), "dev": st.st_dev, "ino": st.st_ino, "marca": "0123456789abcdef"}

    def test_pasta_desconhecida_com_plano_plantado_nao_perde_nada(self):
        pasta = self.tmp / "desconhecida"
        self.hooks_de_verdade(pasta)
        for sub in ("data", "outputs"):
            (pasta / "projects" / "proj2" / sub).mkdir(parents=True)
            (pasta / "projects" / "proj2" / sub / ".gitkeep").write_bytes(b"")
        (pasta / "evidence").mkdir()
        (pasta / "vazio.lock").write_bytes(b"")
        self.plantar_plano(pasta)
        antes = fotografia(pasta)
        resumo = self.mod.limpar(pasta)
        self.assertEqual(fotografia(pasta), antes)  # antes: os 6 hooks e as pastas só com arquivos de 0 byte saíam
        self.assertTrue(resumo.get("recusa"), resumo)
        self.assertEqual((resumo["arquivos_apagados"], resumo["pastas_apagadas"]), (0, 0))
        self.assertIn("nada foi apagado", resumo["sobras"][0])
        r = rodar_copia(copia_do_script(self.tmp / "skill"), "limpar", "--base", pasta,
                        "--temp-base", self.temp_base.as_posix(), env=self.env)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(fotografia(pasta), antes)

    def test_raiz_de_fundacao_e_recusada_mesmo_com_a_prova_plantada(self):
        def raiz_com(*sinais) -> Path:
            raiz = self.tmp / ("Projeto de IA " + "-".join(s.replace("/", "_") for s in sinais))
            hashes = self.hooks_de_verdade(raiz)
            (raiz / "projects" / "proj1").mkdir(parents=True)
            (raiz / "projects" / "proj1" / "INSTRUCOES.md").write_text("# projeto\n", encoding="utf-8")
            for sinal in sinais:
                alvo = raiz.joinpath(*sinal.split("/"))
                if sinal in ("fundacao", "registry"):
                    alvo.mkdir()
                    (alvo / "dado.json").write_text("{}\n", encoding="utf-8")
                else:
                    alvo.parent.mkdir(parents=True, exist_ok=True)
                    alvo.write_bytes(b"SQLite format 3\x00" if sinal.endswith(".sqlite") else b"# RETOMADA\n")
            self.plantar_plano(raiz, config=self.plantar_config(raiz), hooks=hashes, temp_base=self.mod.TEMP_BASE)
            return raiz

        todos = ("fundacao", "registry", "state/state.sqlite", "RETOMADA.md")
        for sinais in (todos, *((s,) for s in todos)):
            with self.subTest(sinais=sinais):
                raiz = raiz_com(*sinais)
                antes = fotografia(raiz)
                with self.assertRaises(self.mod.Erro) as ctx:
                    self.mod.limpar(raiz)
                self.assertIn("sinais de uma raiz de fundação", str(ctx.exception))
                self.assertEqual(fotografia(raiz), antes)

    def test_hook_trocado_fica_e_a_configuracao_espera_o_limpar_seguinte(self):
        self.mod.preparar(self.base)
        c = self.mod._caminhos(self.base)
        trocado = c["hook:guarda_rede.py"]
        trocado.write_text("# trocado depois do preparar\n", encoding="utf-8")
        resumo = self.mod.limpar(self.base)
        self.assertTrue(trocado.is_file(), "o hook trocado saiu (antes: saía sem comparar com o plano)")
        self.assertEqual(trocado.read_text(encoding="utf-8"), "# trocado depois do preparar\n")
        self.assertTrue(any("guarda_rede.py" in s and "SHA-256" in s for s in resumo["sobras"]), resumo)
        self.assertFalse(c["hook:guarda_caminho.py"].exists())  # o igual ao do plano sai
        self.assertFalse(c["can_state"].exists())
        self.assertTrue((self.base / "plano.json").is_file())
        self.assertTrue(self.mod.config_do_ensaio(self.base).is_dir())  # a prova fica para o limpar seguinte
        trocado.unlink()  # o titular confere e tira o hook trocado
        resumo = self.mod.limpar(self.base)
        self.assertEqual((resumo["sobras"], resumo["restantes"]), ([], []), resumo)
        self.assertFalse(self.base.exists())
        self.assertFalse(self.mod.config_do_ensaio(self.base).exists())

    def test_de_claude_da_raiz_so_sai_o_que_a_sonda_grava(self):
        self.mod.preparar(self.base)
        c = self.mod._caminhos(self.base)
        c["claude_settings"].write_text('{"hooks": {}}\n', encoding="utf-8")  # o perfil de verdade, não a sonda
        c["hook_novo"].write_bytes(b"x")  # o que o subprocesso da sonda grava
        resumo = self.mod.limpar(self.base)
        self.assertTrue(c["claude_settings"].is_file())
        self.assertFalse(c["hook_novo"].exists())
        self.assertTrue(any("settings.json" in s for s in resumo["sobras"]), resumo)


class ItensNovosDoCanario(Base):
    """WSL-01 (a área root de outro projeto) e HOOK-F1 (<raiz>/.claude): dois itens de comando a mais."""

    def por_id(self, trocas: dict, **kw) -> tuple:
        plano = kw.pop("plano", None) or self.mod.preparar(self.base)
        bom = executor_bom(plano["nonce"])

        def exe(base, proj, sessao):
            if sessao["rotulo"] in trocas:
                return trocas[sessao["rotulo"]](sessao, plano["nonce"], Path(base))
            return bom(base, proj, sessao)

        padrao = {"perfil_info": {"gerado": True}, "sandbox_ligado": True, "linux": True, "contexto": _ctx()}
        padrao.update(kw)
        rel = self.mod.rodar(self.base, executor=exe, **padrao)
        return plano, rel, {i["id"]: i for i in rel["itens"]}

    def test_os_dois_sao_de_comando_e_estao_no_plano(self):
        classes = {s["id"]: s["classe"] for s in self.mod.SONDAS}
        plano = self.mod.preparar(self.base)
        for novo in NOVOS:
            self.assertEqual(classes[novo], "comando")
            self.assertIn(novo, plano["verificacoes"])

    def test_preparar_cria_a_area_root_ficticia_fora_da_base(self):
        plano = self.mod.preparar(self.base)
        area = Path(plano["area"]["caminho"])
        self.assertEqual(area, self.temp_base / "fundacao-ia-ensaio.area")
        st = os.lstat(area)
        self.assertEqual((plano["area"]["dev"], plano["area"]["ino"]), (st.st_dev, st.st_ino))
        self.assertEqual((area / ".ensaio-isolamento").read_text(encoding="utf-8").strip(), plano["area"]["marca"])
        canario = Path(plano["canarios"]["area_b"]["arquivo"])
        self.assertEqual(canario, area / "projetos" / "ensaio-b" / "canario-area.txt")
        self.assertEqual(hashlib.sha256(canario.read_bytes()).hexdigest(), plano["canarios"]["area_b"]["sha256"])
        self.assertNotIn(canario.read_text(encoding="utf-8").strip(), (self.base / "plano.json").read_text("utf-8"))
        if os.name == "posix":
            for pasta in (area, area / "projetos", area / "projetos" / "ensaio-b"):
                self.assertEqual(os.lstat(pasta).st_mode & 0o777, 0o700, pasta)
        resumo = self.mod.limpar(self.base)
        self.assertEqual(resumo["sobras"], [], resumo)
        self.assertFalse(area.exists())
        self.assertEqual(list(self.temp_base.iterdir()), [])

    def test_a_sessao_que_confina_passa_nos_dois(self):
        _, rel, por = self.por_id({})
        for novo in NOVOS:
            self.assertEqual(por[novo]["veredito"], "passou", por[novo]["motivo"])
        self.assertIs(rel["conclusao"]["confina_comandos"], True)

    def test_a_area_lida_ou_trocada_falha(self):
        plano = self.mod.preparar(self.base)
        arquivo = Path(plano["canarios"]["area_b"]["arquivo"])
        valor = arquivo.read_text(encoding="utf-8").strip()

        def le(sessao, nonce, base):
            return {"transcricao": transcricao(sessao, nonce, saidas={indice(sessao, "python3"): valor})}

        _, rel, por = self.por_id({"leitura_area_outro": le}, plano=plano)
        item = por["leitura_area_outro_projeto"]
        self.assertEqual(item["veredito"], "falhou")
        self.assertIn("apareceu", item["motivo"])
        self.assertTrue(item["canario"]["apareceu"])
        self.assertNotIn(valor, json.dumps(rel, ensure_ascii=False))
        self.assertIs(rel["conclusao"]["confina_comandos"], False)
        self.mod.limpar(self.base)
        plano = self.mod.preparar(self.base)

        def troca(sessao, nonce, base):
            Path(plano["canarios"]["area_b"]["arquivo"]).write_text("trocado\n", encoding="utf-8")
            return {"transcricao": transcricao(sessao, nonce, codigos={1: 1, 2: 1})}

        _, rel, por = self.por_id({"leitura_area_outro": troca}, plano=plano)
        self.assertEqual(por["leitura_area_outro_projeto"]["veredito"], "falhou")
        self.assertIn("alterado", por["leitura_area_outro_projeto"]["motivo"])

    def test_gravar_em_claude_da_raiz_falha(self):
        casos = {"settings.json": lambda c: c["claude_settings"].write_text("x", encoding="utf-8"),
                 "hooks/canario.py": lambda c: c["hook_novo"].write_text("x", encoding="utf-8"),
                 "hook do perfil trocado": lambda c: c["hook:guarda_caminho.py"].write_text("# trocado\n",
                                                                                           encoding="utf-8")}
        for n, (nome, grava) in enumerate(casos.items()):
            with self.subTest(nome):
                base, temp = self.tmp / f"base-{n}", self.tmp / f"temp-{n}"
                temp.mkdir()
                plano = self.mod.preparar(base, temp_base=temp.as_posix())
                c = self.mod._caminhos(base, temp.as_posix())
                bom = executor_bom(plano["nonce"])

                def exe(b, proj, sessao, c=c, grava=grava, bom=bom, plano=plano):
                    if sessao["rotulo"] == "escrita_claude_raiz":
                        grava(c)
                        return {"transcricao": transcricao(sessao, plano["nonce"])}
                    return bom(b, proj, sessao)

                rel = self.mod.rodar(base, executor=exe, perfil_info={"gerado": True}, sandbox_ligado=True,
                                     linux=True, contexto=_ctx(), temp_base=temp.as_posix())
                por = {i["id"]: i for i in rel["itens"]}
                self.assertIn("escrita_claude_da_raiz", por)  # antes: o canário não tinha o item
                item = por["escrita_claude_da_raiz"]
                self.assertEqual(item["veredito"], "falhou", item["motivo"])
                self.assertIs(rel["conclusao"]["confina_comandos"], False)

    def test_gravar_com_codigo_0_sem_o_arquivo_nao_mede(self):
        def zero(sessao, nonce, base):
            return {"transcricao": transcricao(sessao, nonce, codigos={1: 1, 2: 0, 3: 1})}

        _, rel, por = self.por_id({"escrita_claude_raiz": zero})
        self.assertEqual(por["escrita_claude_da_raiz"]["veredito"], "nao_medido")
        self.assertIn("código 0", por["escrita_claude_da_raiz"]["motivo"])
        self.assertIsNone(rel["conclusao"]["confina_comandos"])

    def test_a_area_fora_do_lugar_do_etc_nao_mede(self):
        outro = self.tmp / "outro-temp"
        outro.mkdir()
        plano = self.mod.preparar(self.base, temp_base=outro.as_posix())
        self.assertEqual(Path(plano["area"]["caminho"]).parent, outro)
        rel = self.mod.rodar(self.base, executor=executor_bom(plano["nonce"]), perfil_info={"gerado": True},
                             sandbox_ligado=True, linux=True, contexto=_ctx(), temp_base=outro.as_posix())
        item = next(i for i in rel["itens"] if i["id"] == "leitura_area_outro_projeto")
        self.assertEqual(item["veredito"], "nao_medido")
        self.assertIn("o lugar que o /etc/fundacao-ia representa", item["motivo"])

    def test_o_perfil_e_gerado_com_a_area_root_ficticia(self):
        plano = self.mod.preparar(self.base)
        fake = self.tmp / "preparo_eco.py"
        fake.write_text("import sys, json\n"
                        "i = sys.argv.index('--saida')\n"
                        "open(sys.argv[i + 1], 'w').write(json.dumps({'argv': sys.argv[1:]}))\n",
                        encoding="utf-8", newline="\n")
        destino = self.base / "perfil.json"
        self.assertTrue(self.mod.gerar_perfil_pelo_host(fake, self.base, destino)["gerado"])
        argv = json.loads(destino.read_text(encoding="utf-8"))["argv"]
        self.assertEqual(Path(argv[argv.index("--area-raiz") + 1]), Path(plano["area"]["caminho"]))
        self.assertTrue(any("/var/tmp/fundacao-ia-ensaio.area" in d for d in self.mod.DESVIOS_FIXOS))

    def test_artefato_da_claude_de_rodada_anterior_recusa(self):
        plano = self.mod.preparar(self.base)
        self.mod._caminhos(self.base)["claude_settings"].write_text("x", encoding="utf-8")
        with self.assertRaises(self.mod.Erro):
            self.mod.rodar(self.base, executor=executor_bom(plano["nonce"]), perfil_info={"gerado": True},
                           sandbox_ligado=True, linux=True, contexto=_ctx())

    @unittest.skipUnless(LINUX and shutil.which("bash"), "controle sem sandbox só no Linux com bash")
    def test_sem_sandbox_as_duas_sondas_falham(self):
        """O controle: os comandos reais das duas sondas por `bash -c`, sem sandbox nenhum, vazam."""
        for sid in NOVOS:
            with self.subTest(sid):
                base, temp = self.tmp / ("controle-" + sid), self.tmp / ("temp-" + sid)
                temp.mkdir()
                plano = self.mod.preparar(base, temp_base=temp.as_posix())
                sonda = next(s for s in self.mod.SONDAS if s["id"] == sid)
                ctx = _ctx(barramentos=[])
                sr = []
                for ses in sonda["sessoes"](base, plano, plano["nonce"], ctx):
                    r = subprocess.run(["bash", "-c", "\n".join(ses["comandos"])], capture_output=True, text=True,
                                       cwd=str(base), timeout=60)
                    sr.append((ses, {"transcricao": (r.stdout or "") + "\n" + (r.stderr or ""),
                                     "codigo": r.returncode}))
                veredito, motivo = sonda["julgar"](base, plano, ctx, sr)
                self.assertEqual(veredito, "falhou", f"{sid}: {motivo}")


class EnsaioNaoRodaDeDentroDeProjects(Base):
    """CI-F1: a cópia do ensaio dentro da pasta projects/ de uma raiz (a projects cujo pai tem registry/) recusa
    qualquer subcomando, antes de criar nada."""

    def raiz(self) -> Path:
        raiz = self.tmp / "raiz"
        (raiz / "registry").mkdir(parents=True)
        return raiz

    def test_recusa_do_local_pelo_caminho(self):
        raiz = self.raiz()
        dentro = raiz / "projects" / "fundacao-de-ia" / "trabalho" / "skill" / "scripts" / "ensaio_isolamento_wsl.py"
        self.assertIn("projects", self.mod.recusa_do_local(dentro))
        self.assertIsNone(self.mod.recusa_do_local(self.tmp / "dev" / "projects" / "fund" / "scripts" / "x.py"))
        self.assertIsNone(self.mod.recusa_do_local(self.tmp / "skill" / "scripts" / "x.py"))
        self.assertIsNone(self.mod.recusa_do_local(raiz / "skill" / "scripts" / "x.py"))

    def test_a_copia_dentro_de_projects_nao_roda_nenhum_subcomando(self):
        script = copia_do_script(self.raiz() / "projects" / "p" / "skill")
        tb = self.temp_base.as_posix()
        for args in (("preparar", "--base", self.base, "--temp-base", tb),
                     ("rodar", "--base", self.base, "--simular"), ("limpar", "--base", self.base, "--temp-base", tb)):
            with self.subTest(args[0]):
                r = rodar_copia(script, *args, env=self.env)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("projects", json.loads(r.stdout)["erro"])
        self.assertFalse(self.base.exists())
        self.assertEqual(list(self.temp_base.iterdir()), [])
        self.assertEqual(list(self.casa.iterdir()), [])
        fora = copia_do_script(self.tmp / "fora")  # controle: a mesma cópia, fora da raiz, roda
        r = rodar_copia(fora, "preparar", "--base", self.base, "--temp-base", tb, env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = rodar_copia(fora, "limpar", "--base", self.base, "--temp-base", tb, env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.base.exists())

    def test_claude_ou_preparo_de_dentro_de_projects_recusa_antes_de_rodar(self):
        """As variantes do mesmo caminho: o binário do --claude (o --version já o executa) e o --preparo-host."""
        dentro = self.raiz() / "projects" / "p" / "bin"
        dentro.mkdir(parents=True)
        claude = dentro / "claude"
        claude.write_text("#!/bin/sh\necho 2.1.302\n", encoding="utf-8", newline="\n")
        claude.chmod(0o755)
        with self.assertRaises(self.mod.Erro) as ctx:
            self.mod.conferir_claude(str(claude), None)
        self.assertIn("projects", str(ctx.exception))
        self.mod.preparar(self.base)
        (self.mod.config_do_ensaio(self.base) / ".credentials.json").write_text("{}", encoding="utf-8")
        preparo = dentro / "preparo_falso.py"
        preparo.write_text("import sys\nopen(sys.argv[sys.argv.index('--saida') + 1], 'w').write('{}')\n",
                           encoding="utf-8", newline="\n")
        r = rodar_copia(copia_do_script(self.tmp / "skill"), "rodar", "--base", self.base, "--claude", sys.executable,
                        "--preparo-host", preparo, "--temp-base", self.temp_base.as_posix(), env=self.env)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("--preparo-host", json.loads(r.stdout)["erro"])
        self.assertFalse((self.base / "perfil-ensaio-a.settings.json").exists())  # o preparo não rodou

    @unittest.skipUnless(LINUX, "ligação simbólica conferida no Linux")
    def test_ligacao_para_a_copia_dentro_de_projects_tambem_recusa(self):
        alvo = self.raiz() / "projects" / "p" / "skill"
        copia_do_script(alvo)
        atalho = self.tmp / "atalho"
        atalho.symlink_to(alvo, target_is_directory=True)
        r = rodar_copia(atalho / "scripts" / "ensaio_isolamento_wsl.py", "limpar", "--base", self.base, env=self.env)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("projects", json.loads(r.stdout)["erro"])


if __name__ == "__main__":
    unittest.main()
