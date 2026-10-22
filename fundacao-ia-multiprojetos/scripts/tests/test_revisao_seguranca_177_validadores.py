"""Revisão de segurança da 1.7.7 — resíduos nos validadores e nos inventários de caminho (R177-VAL-01 e -02).

- VAL-01: a base padrão da matriz oficial é a raiz da fundação, e o `validar` conferia se a evidência citava a versão
  ou batia com `sha256_evidencia`: linhas apontando para `.env`, `state/state.sqlite` e `projects/b/data/caso.md`
  saíam "conferidas" quando o texto estava no arquivo e recusadas quando não — oráculo de conteúdo e de hash fora das
  regras de leitura do host. O ponteiro de histórico da RETOMADA era oráculo de existência e de tamanho. Agora caminho
  protegido é recusado antes de tocar o disco, com a mesma resposta exista ou não o alvo: primeira parte `state`, nome
  de segredo da lista de negação dos perfis do host (`permissions.deny` e `denyRead`) e `projects/<projeto>/data/`,
  com o nome comparado como o Windows compara (sem caixa, sem ponto ou espaço no fim; nome curto 8.3 recusado).
  Arquivo protegido dentro de uma pasta de evidência não é lido; o `arquivar` não grava histórico em caminho
  protegido.
- VAL-02: nenhum validador conferia o número de nomes do arquivo: um vínculo físico (hard link) dentro da base para um
  arquivo de fora (no NTFS, `os.link` não exige privilégio) era lido como se fosse da base, e o B1 dava `completo:
  true`. Agora arquivo com `st_nlink > 1` (no lstat e, depois de abrir, no fstat) não é lido: problema na matriz e na
  RETOMADA, inventário parcial no B1 e no B3.

Pastas descartáveis com estrutura fictícia (apoio de test_auditoria_1_7_6_validadores.py). Cada teste falha na revisão
f1bdc88 e passa depois da correção; os controles mostram o formato real da matriz e da RETOMADA.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import unittest
from pathlib import Path
from unittest import mock

import test_auditoria_1_7_6_validadores as base_176  # o módulo, não as classes: os testes dela não rodam de novo aqui
from apoio import SKILL, rodar_script
from test_auditoria_1_7_6_validadores import SEGREDO, _Pastas, carregar, sha_de

MATRIZ, RETOMADA = base_176.TestMatrizEvidencia.__dict__, base_176.TestRetomadaHistorico.__dict__  # os ajudantes

CITA = f"kit 1.4.1 {SEGREDO}\n"  # cita a versão avaliada das linhas: sem a recusa, a linha sairia conferida
PROTEGIDOS = (".env", "state/state.sqlite", "projects/b/data/caso.md", "secrets/chave.txt", "evidence/servidor.pem",
              "evidence/.env.local", "evidence/auth.json", "evidence/id_rsa", "evidence/minhas-credentials.txt",
              "evidence/x-secret-y.md", "evidence/cofre.kdbx", "evidence/a.key", "evidence/b.pfx", "evidence/c.p12",
              ".ssh/config", ".codex/config.toml")
VARIANTES = ("STATE/state.sqlite", "state./state.sqlite", "state /state.sqlite", ".ENV", "Projects/b/DATA/caso.md",
             "projects/b/data./caso.md", "STATE~1/state.sqlite", "evidence/ENV~1")
# Formas dos caminhos de evidência da matriz real (só os nomes; conferidas na leitura permitida do requisitos.csv).
FORMAS_REAIS = ("evidence/kit/EVIDENCIAS-A5.md", "evidence/isolamento/EVIDENCIAS-A6-A7.md",
                "evidence/orquestracao/EVIDENCIAS-R05.md", "evidence/agentes/EVIDENCIAS-A10.md",
                "evidence/provedores/EVIDENCIAS-R12-R17.md",
                "evidence/provedores/EVIDENCIAS-R13-DIVERGENCIA-2026-10-21.md",
                "evidence/rag/EVIDENCIAS-R25-R23-R37-R40.md", "evidence/cag/EVIDENCIAS-CAG.md",
                "evidence/host/EVIDENCIAS-HOOKS.md", "evidence/plugins/EVIDENCIAS-R35-R36.md",
                "evidence/consumo/EVIDENCIAS-R38.md", "docs/RELATORIO-FINAL.md", "evidence/referencia/EVIDENCIAS-A4.md",
                "evidence/conversa/EVIDENCIAS-R49.md", "evidence/caso-real/EVIDENCIAS-R51.md",
                "evidence/componentes/EVIDENCIAS-R54.md", "evidence/privacidade/EVIDENCIAS-R55.md",
                "evidence/ci/EVIDENCIAS-R58-R59.md", "projects/juridico-lab/evidence/EVIDENCIAS-R60.md",
                "evidence/retomada/RETOMADA-20261021T100757Z.md", "evidence/orquestracao")


@contextlib.contextmanager
def sem_disco():
    """Contexto em que tocar o disco (lstat ou open) é falha do teste: a recusa vem antes."""
    with mock.patch("os.lstat", side_effect=AssertionError("tocou o disco")), \
            mock.patch("os.open", side_effect=AssertionError("tocou o disco")):
        yield


def amostras_da_negacao() -> list[str]:
    """Um caminho de exemplo para cada regra de leitura negada nos perfis do host (`Read(...)` e `denyRead`)."""
    amostras = []
    for perfil in (SKILL / "assets" / "host" / "windows" / "settings.json",
                   SKILL / "assets" / "host" / "wsl" / "settings.wsl.json"):
        dados = json.loads(perfil.read_text(encoding="utf-8"))
        regras = [r[5:-1] for r in dados["permissions"]["deny"] if r.startswith("Read(")]
        regras += dados.get("sandbox", {}).get("filesystem", {}).get("denyRead", [])
        for regra in regras:
            for prefixo in ("./", "~/", "/"):
                regra = regra.removeprefix(prefixo)
            if regra.startswith("{{"):
                regra = regra.split("}}/", 1)[1]
            regra = regra.replace("**/", "a/").removesuffix("/**").replace("*", "x")
            amostras += [regra, regra + "/dentro.md"]
    return sorted(set(amostras))


class TestMatrizCaminhoProtegido(_Pastas):
    """R177-VAL-01 na matriz: evidência em caminho protegido não é lida, e a resposta não diz se ela existe."""

    matriz, validar, ativo, problemas = MATRIZ["matriz"], MATRIZ["validar"], MATRIZ["ativo"], MATRIZ["problemas"]

    def test_protegido_nao_e_conferido_nem_revela_existencia(self):
        for rel in PROTEGIDOS:
            self.escrever(rel, CITA)
        linhas = {f"R{12 + i}": self.ativo(rel) for i, rel in enumerate(PROTEGIDOS + VARIANTES)}
        sem_alvo = ("state/nao-existe.sqlite", "projects/b/data/nao-existe.md", ".env.nao-existe")
        linhas.update({f"R{40 + i}": self.ativo(rel) for i, rel in enumerate(sem_alvo)})
        linhas["R45"] = self.ativo(".env", sha256_evidencia=sha_de(self.raiz / ".env"))  # o hash confere
        codigo, dados, saida = self.validar(self.matriz(linhas))
        self.assertEqual(codigo, 1)
        self.assertEqual(dados["evidencias"]["conferidas"], [], "caminho protegido foi lido e conferido")
        probs = self.problemas(dados)
        for rid, linha in linhas.items():
            with self.subTest(caminho=linha["caminho_evidencia"]):
                self.assertIn("protegido", probs.get(rid, ""), probs.get(rid))
        mensagens = {probs[rid].split(":", 1)[1].replace(linhas[rid]["caminho_evidencia"], "C") for rid in linhas}
        self.assertEqual(len(mensagens), 1, f"a resposta varia com o alvo: {mensagens}")
        self.assertNotIn(SEGREDO, saida)

    def test_recusa_vem_antes_de_tocar_o_disco(self):
        mod = carregar("matriz")
        with sem_disco():
            for rel in PROTEGIDOS[:4] + VARIANTES[-2:]:
                with self.subTest(caminho=rel):
                    achados = mod.examinar_evidencia(self.raiz, rel, "kit 1.4.1", "")
                    self.assertEqual(len(achados), 1)
                    self.assertIn("protegido", achados[0])

    def test_pasta_de_evidencia_nao_le_o_protegido_de_dentro(self):
        self.escrever("evidence/pasta/.env", CITA)
        self.escrever("evidence/pasta/leia-me.md", "sem versão\n")
        self.escrever("evidence/outra/secrets/chave.md", CITA)
        self.escrever("evidence/outra/leia-me.md", "sem versão\n")
        self.escrever("projects/b/data/caso.md", CITA)
        self.escrever("projects/b/evidence/leia-me.md", "sem versão\n")
        mat = self.matriz({"R12": self.ativo("evidence/pasta"), "R13": self.ativo("evidence/outra"),
                           "R14": self.ativo("projects")})
        codigo, dados, saida = self.validar(mat)
        self.assertEqual(codigo, 1)
        self.assertEqual(dados["evidencias"]["conferidas"], [], "a pasta leu o arquivo protegido")
        for rid in ("R12", "R13", "R14"):
            self.assertIn("cita a versão", self.problemas(dados).get(rid, ""))

    def test_negacoes_do_perfil_do_host_estao_cobertas(self):
        mod = carregar("matriz")
        amostras = amostras_da_negacao()
        self.assertGreaterEqual(len(amostras), 30)
        for rel in amostras:
            with self.subTest(caminho=rel):
                self.assertTrue(mod.protegido(self.raiz, rel.split("/")), rel)

    def test_controle_formas_reais_continuam_aceitas(self):
        mod = carregar("matriz")
        for rel in FORMAS_REAIS:
            with self.subTest(caminho=rel):
                self.assertFalse(mod.protegido(self.raiz, rel.split("/")))
        projeto = self.raiz / "projects" / "a"
        self.assertTrue(mod.protegido(projeto, ["data", "caso.md"]))         # base num projeto: o data/ dele
        self.assertFalse(mod.protegido(projeto, ["evidence", "EVIDENCIAS-R60.md"]))

    def test_matriz_e_retomada_usam_o_mesmo_criterio(self):
        matriz, retomada = carregar("matriz"), carregar("retomada")
        self.assertEqual(matriz.NOMES_PROTEGIDOS, retomada.NOMES_PROTEGIDOS)
        for rel in amostras_da_negacao() + list(PROTEGIDOS + VARIANTES + FORMAS_REAIS):
            for base in (self.raiz, self.raiz / "projects" / "a"):
                self.assertEqual(matriz.protegido(base, rel.split("/")), retomada.protegido(base, rel.split("/")),
                                 rel)


class TestRetomadaCaminhoProtegido(_Pastas):
    """R177-VAL-01 na RETOMADA: o ponteiro de histórico para caminho protegido não é lido nem revela existência."""

    ITENS, texto_retomada, historico = RETOMADA["ITENS"], RETOMADA["texto_retomada"], RETOMADA["historico"]
    validar = RETOMADA["validar"]

    def test_ponteiro_protegido_nao_e_lido(self):
        ponteiros = []
        for rel in (".env", "state/hist.md", "projects/b/data/hist.md", "evidence/retomada/.env.antigo"):
            h = self.historico(self.raiz / rel, [f"- Item de dentro {SEGREDO}: não deveria aparecer"])
            ponteiros.append(f"Histórico arquivado: {rel} (sha256 {h})")
        ponteiros.append(f"Histórico arquivado: state/nao-existe.md (sha256 {'0' * 64})")
        codigo, res, saida = self.validar(ponteiros)
        self.assertEqual(codigo, 1, res)
        self.assertNotIn(SEGREDO, saida, "o validar leu o histórico protegido")
        estados = [x["estado"] for x in res["historicos"]]
        self.assertEqual(len(set(estados)), 1, f"a resposta varia com o alvo: {estados}")
        self.assertIn("protegido", estados[0])
        mod = carregar("retomada")
        with sem_disco():
            self.assertIn("protegido", mod.ler_historico(self.raiz, "state/hist.md", "0" * 64)[0])

    def test_arquivar_nao_grava_em_caminho_protegido(self):
        arq = self.raiz / "RETOMADA.md"
        arq.write_text(self.texto_retomada([], self.ITENS), encoding="utf-8")
        antes = sha_de(arq)
        for pasta in (self.raiz / "state" / "historico", self.raiz / "projects" / "b" / "data"):
            with self.subTest(pasta=pasta.relative_to(self.raiz).as_posix()):
                p = rodar_script("retomada.py", "arquivar", "--arquivo", arq, "--historico", pasta, timeout=60)
                self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
                self.assertIn("protegido", json.loads(p.stdout)["erro"])
                self.assertEqual(sha_de(arq), antes, "a RETOMADA foi alterada")
                self.assertFalse(pasta.exists(), "o histórico foi gravado no caminho protegido")


class TestVinculoFisico(_Pastas):
    """R177-VAL-02: arquivo com vínculo físico (hard link) não é lido — o conteúdo pode ser de um arquivo de fora."""

    matriz, validar, ativo, problemas = MATRIZ["matriz"], MATRIZ["validar"], MATRIZ["ativo"], MATRIZ["problemas"]
    ITENS, texto_retomada, historico = RETOMADA["ITENS"], RETOMADA["texto_retomada"], RETOMADA["historico"]

    def vincular(self, rel: str, alvo: Path) -> Path:
        p = self.raiz / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(alvo, p)
        except (OSError, NotImplementedError) as exc:  # sistema de arquivos sem vínculo físico (FAT, exFAT)
            raise unittest.SkipTest(f"vínculo físico indisponível aqui: {exc}") from None
        return p

    def test_matriz_nao_le_vinculo_fisico(self):
        segredo = self.fora / "segredo.md"  # cita a versão: "kit 1.4.1 ..."
        self.vincular("evidence/R12.md", segredo)
        self.vincular("evidence/pasta/elo.md", segredo)
        self.escrever("evidence/pasta/leia-me.md", "sem versão\n")
        mat = self.matriz({"R12": self.ativo("evidence/R12.md"),
                           "R13": self.ativo("evidence/R12.md", sha256_evidencia=sha_de(segredo)),
                           "R14": self.ativo("evidence/pasta")})
        codigo, dados, saida = self.validar(mat)
        self.assertEqual(codigo, 1)
        self.assertEqual(dados["evidencias"]["conferidas"], [], "o vínculo físico foi lido como evidência da base")
        probs = self.problemas(dados)
        for rid in ("R12", "R13"):
            self.assertIn("vínculo físico", probs.get(rid, ""), probs)
        self.assertIn("cita a versão", probs.get("R14", ""))
        self.assertNotIn(SEGREDO, saida)

    def test_retomada_nao_le_vinculo_fisico(self):
        hist = self.fora / "hist.md"
        h = self.historico(hist, [f"- Item de fora {SEGREDO}: não deveria aparecer"])
        self.vincular("evidence/retomada/elo.md", hist)
        codigo, res, saida = RETOMADA["validar"](self, [f"Histórico arquivado: evidence/retomada/elo.md (sha256 {h})"])
        self.assertEqual(codigo, 1, res)
        self.assertNotIn(SEGREDO, saida, "o validar leu o histórico pelo vínculo físico")
        self.assertIn("vínculo físico", res["historicos"][0]["estado"])

    def test_inventarios_do_fluxo_b_ficam_parciais(self):
        (self.fora / "CLAUDE.md").write_text(SEGREDO, encoding="utf-8")
        # Valores fictícios com espaço: casam o padrão dos sinais, não o da varredura de segredos do pacote.
        (self.fora / "codigo.py").write_text('api_key = "valor ficticio 1"\nrequests.get("x")\n', encoding="utf-8")
        self.escrever("CLAUDE.md", "instrução da origem (dado)")
        self.vincular("AGENTS.md", self.fora / "CLAUDE.md")
        self.vincular("ligado.py", self.fora / "codigo.py")
        p = rodar_script("instrucoes_aninhadas.py", "listar", "--raiz", self.raiz, timeout=120)
        res = json.loads(p.stdout)
        self.assertEqual(p.returncode, 1, "inventário com vínculo físico precisa sair como parcial")
        self.assertFalse(res["completo"])
        self.assertIsNone(next(i for i in res["itens"]["instrucoes"] if i["caminho"] == "AGENTS.md")["sha256"])
        self.assertNotIn(hashlib.sha256(SEGREDO.encode()).hexdigest(), p.stdout)
        self.assertTrue(any(n["caminho"] == "AGENTS.md" and "vínculo físico" in n["motivo"] for n in res["nao_lidos"]))
        p = rodar_script("sinais_compatibilidade.py", "--raiz", self.raiz, timeout=120)
        s = json.loads(p.stdout)
        self.assertEqual([loc for v in s["sinais"].values() for loc in v if loc.startswith("ligado.py")], [],
                         "os sinais leram o arquivo de fora pelo vínculo físico")
        self.assertTrue(any(n["caminho"] == "ligado.py" and "vínculo físico" in n["motivo"] for n in s["nao_lidos"]))
        self.assertFalse(s["completo"])
        self.assertNotEqual(s["classe_sugerida"], "integração direta")


if __name__ == "__main__":
    unittest.main()
