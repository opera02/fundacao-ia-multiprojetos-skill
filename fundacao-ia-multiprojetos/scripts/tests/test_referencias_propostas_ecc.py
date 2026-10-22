"""Propostas 3 e 5 da análise do everything-claude-code (21/10/2026), parte "Agora" da 1.7.7.

3: a memória automática do Claude Code é uma por pasta de repositório (ou pela pasta onde a sessão abriu); como as
sessões da fundação abrem na raiz, ela é uma só para todos os projetos. A capacidade 04 diz o que pode entrar nela e
o AGENTS.md gerado na raiz traz a regra em uma linha.
5: o trabalho delegado volta numa passagem com arquivos tocados, caminho real e SHA-256, o que foi real e o que foi
simulado, o que não foi feito e as armadilhas novas; o coordenador confere antes de registrar (na nova execução da
E10, a RETOMADA citou um arquivo que não era o usado).
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from apoio import SKILL, rodar_script
from test_referencias_decisoes import secao


def ler(rel: str) -> str:
    return (SKILL / rel).read_text(encoding="utf-8")


def plano(texto: str) -> str:
    return " ".join(texto.split())


class TestMemoriaAutomaticaDoHost(unittest.TestCase):
    def test_paragrafo_na_capacidade_04(self):
        s = plano(secao(ler("references/capacidades/04-memoria.md"), "Memória automática do host"))
        for trecho in ("`~/.claude/projects/<pasta>/memory/`", "`MEMORY.md`", "200 linhas ou 25 KB",
                       "não é carregada nos subagentes", "`autoMemoryEnabled: false`",
                       "`CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`", "[Verificado 2026-10-21; code.claude.com/docs/en/memory]",
                       "uma só para todos os projetos da raiz",
                       "sem nome, número, fato ou trecho de projeto ou de caso", "Lição de um projeto fica no projeto",
                       "não autorização nem prova", "nunca aprovada por quem a extraiu", "não é adotada",
                       "decisão do titular", "everything-claude-code, proposta 3"):
            self.assertIn(trecho, s)

    def test_linha_no_agents_md_gerado_na_raiz(self):
        raiz = Path(tempfile.mkdtemp(prefix="memoria-automatica-"))
        try:
            p = rodar_script("instrucoes_raiz.py", "gerar", "--raiz", raiz)
            self.assertEqual(p.returncode, 0, p.stdout[-400:] + p.stderr[-400:])
            texto = (raiz / "AGENTS.md").read_text(encoding="utf-8")
            limites = plano(secao(texto, "Limites"))
            self.assertIn("A memória automática do host é uma só para todos os projetos desta raiz: não grave nela "
                          "nada de projeto ou de caso; lição de um projeto fica no projeto.", limites)
            self.assertLessEqual(len(texto.splitlines()), 80)
            conf = rodar_script("instrucoes_raiz.py", "conferir", "--raiz", raiz)
            self.assertEqual((conf.returncode, json.loads(conf.stdout)["ok"]), (0, True))
        finally:
            shutil.rmtree(raiz, ignore_errors=True)


class TestPassagemDoTrabalhoDelegado(unittest.TestCase):
    def test_modelo_tem_os_campos_e_cabe_em_30_linhas(self):
        bruto = ler("assets/templates/PASSAGEM.md")
        texto = plano(bruto.replace("\n> ", "\n"))  # a nota de abertura é uma citação de várias linhas
        for trecho in ("É relato, não prova", "SHA-256 diferente do que está no disco = não registra e devolve",
                       "modelo lido do rastro", "Caminho real (relativo à raiz autorizada)", "SHA-256 depois",
                       "pasta temporária da sessão", "Real ou simulado", '"não rodada", nunca "passou"',
                       "## O que não foi feito", "Armadilhas novas", "Perguntas abertas", "ainda abertos"):
            self.assertIn(trecho, texto)
        self.assertLessEqual(len(bruto.splitlines()), 30)

    def test_capacidade_02_cita_a_passagem_no_pacote_e_na_verificacao(self):
        texto = ler("references/capacidades/02-agentes-subagentes.md")
        impl = plano(secao(texto, "Implementação"))
        for trecho in ("**passagem** (`assets/templates/PASSAGEM.md`)", "caminho real e SHA-256",
                       "o que foi real e o que foi simulado", "o que não foi feito", "armadilhas novas",
                       "confere os arquivos e os hashes antes de registrar", "everything-claude-code, proposta 5",
                       "a RETOMADA citou outro arquivo"):
            self.assertIn(trecho, impl)
        verificacao = plano(secao(texto, "Verificação"))
        self.assertIn("| Passagem que cita arquivo ausente, da pasta temporária da sessão ou com SHA-256 diferente do "
                      "disco | o coordenador não registra e devolve ao executor |", verificacao)


if __name__ == "__main__":
    unittest.main()
