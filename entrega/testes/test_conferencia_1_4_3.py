"""Conferência independente da 1.4.3 — CF-01 a CF-04 (`auditoria/CONFERENCIA-1.4.3.md`, seção 7).

CF-01 (P2): o `guarda_identidade.py` da 1.4.3 deixava passar formas comuns de atribuição explícita de
`FUNDACAO_PRINCIPAL` no PowerShell — caminho `env:` entre aspas, `-Path:`/`-Path=`, `Env:\\`, `Remove-Item` entre
aspas, `+=` — que a 1.4.2 negava; a leitura (`echo`, `Get-ChildItem`, `-eq`) tem de continuar liberada.
CF-02 (P3): `remover --confirmar` mantinha, com código 1, uma ligação pendurada (alvo que não existe mais) com o
nome desta skill; só a ligação é removida e relatada.
CF-03 (P3): `SKILL.md` em UTF-8 com BOM era recusado com a mensagem "declara name None"; o BOM é aceito e, sem
`name` legível, a mensagem diz isso.
CF-04 (P3): com a marca de troca ilegível, a cópia preparada ficava órfã em `~/.agents/skills-preparo/`; as pastas
`<nome>-*` que sobram são removidas e relatadas em `passos`.

Perfis DESCARTÁVEIS (USERPROFILE e HOME temporários, conferidos antes). O hook é o da árvore ao lado de `entrega/`
(`../fundacao-ia-multiprojetos/assets/hooks/guarda_identidade.py`). Falham no instalador e no hook da 1.4.3 (menos o
controle de leitura do CF-01, que passa nas duas versões) e passam na 1.4.4.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from test_auditoria_1_4_1 import _Base, skill_md
from test_auditoria_final_1_4_2 import QUEDA_ENTRE_AS_RENOMEACOES, _Preparo

ENTREGA = Path(__file__).resolve().parents[1]
HOOK = ENTREGA.parent / "fundacao-ia-multiprojetos" / "assets" / "hooks" / "guarda_identidade.py"

# As cinco formas do CF-01, as duas do padrão sugerido na conferência (`-Path=` e `Env:\\`) e a sintaxe documentada
# do `New-Item` para o drive `env:` (acrescentada na 1.4.4).
ATRIBUICOES_CF01 = [
    'Set-Item -Path "env:FUNDACAO_PRINCIPAL" -Value "titular"',
    "Set-Item 'env:FUNDACAO_PRINCIPAL' 'titular'",
    "Set-Item -Path:env:FUNDACAO_PRINCIPAL -Value titular",
    'Remove-Item "env:FUNDACAO_PRINCIPAL"',
    "$env:FUNDACAO_PRINCIPAL += 'x'",
    "Set-Item -Path=env:FUNDACAO_PRINCIPAL -Value titular",
    "Set-Item Env:\\FUNDACAO_PRINCIPAL titular",
    "New-Item -Path env: -Name FUNDACAO_PRINCIPAL -Value titular",
]
# Leitura e comparação: nunca são troca de identidade (AF-07); passam na 1.4.3 e na 1.4.4.
LEITURAS = [
    ("PowerShell", "echo $env:FUNDACAO_PRINCIPAL"),
    ("PowerShell", "Get-ChildItem env:FUNDACAO_PRINCIPAL"),
    ("PowerShell", "if ($env:FUNDACAO_PRINCIPAL -eq 'titular') { 'ok' }"),
    ("PowerShell", "$quem = $env:FUNDACAO_PRINCIPAL"),
    ("Bash", 'echo "$FUNDACAO_PRINCIPAL"'),
    ("Bash", '[[ "$FUNDACAO_PRINCIPAL" == titular ]] && echo sim'),
]


def decisao(comando: str, ferramenta: str = "PowerShell") -> str:
    """Decisão do hook para um evento PreToolUse sintético: `deny`, `sem_decisao` ou o erro."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("FUNDACAO_")}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    evento = json.dumps({"tool_name": ferramenta, "tool_input": {"command": comando}})
    p = subprocess.run([sys.executable, "-B", str(HOOK)], input=evento, capture_output=True, text=True,
                       encoding="utf-8", env=env, timeout=60)
    if p.returncode != 0:
        return f"codigo={p.returncode}: {p.stderr[-200:]}"
    if not p.stdout.strip():
        return "sem_decisao"
    return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"]


class TestCF01GuardaIdentidade(unittest.TestCase):
    def setUp(self):
        self.assertTrue(HOOK.is_file(), f"a árvore da skill precisa estar ao lado de entrega/: {HOOK} não existe")

    def test_cf01_formas_de_atribuicao_explicita_no_powershell_sao_negadas(self):
        for comando in ATRIBUICOES_CF01:
            with self.subTest(comando):
                self.assertEqual(decisao(comando), "deny")

    def test_cf01_controle_leitura_da_variavel_segue_livre(self):
        """Controle: passa na 1.4.3 e na 1.4.4."""
        for ferramenta, comando in LEITURAS:
            with self.subTest(comando):
                self.assertEqual(decisao(comando, ferramenta), "sem_decisao")


class TestCF02LigacaoPendurada(_Base):
    def ligar_para(self, alvo: Path) -> None:
        self.link.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            r = subprocess.run(["cmd", "/c", "mklink", "/J", str(self.link), str(alvo)], capture_output=True,
                               text=True, errors="replace")
            if r.returncode != 0:
                self.skipTest(f"junção indisponível: {r.stdout.strip()} {r.stderr.strip()}")
        else:
            self.link.symlink_to(alvo, target_is_directory=True)

    def test_cf02_ligacao_pendurada_com_este_nome_e_removida_e_relatada(self):
        sumido = self.base / "alvo-sumido"
        sumido.mkdir()
        self.ligar_para(sumido)
        sumido.rmdir()
        self.assertTrue(os.path.lexists(self.link) and not self.link.exists(), "a ligação pendurada não se reproduziu")
        p, saida = self.rodar("remover", "--confirmar")
        self.assertFalse(os.path.lexists(self.link), "a ligação pendurada ficou em ~/.claude/skills")
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])
        self.assertTrue((saida or {}).get("removido"), saida)
        ligacoes = [i for i in (saida or {}).get("removidos", []) if i.get("tipo") == "ligação"]
        self.assertTrue(ligacoes and "pendurada" in ligacoes[0].get("motivo", ""), saida)


class TestCF03CabecalhoDoSkillMd(_Base):
    def test_cf03_skill_md_em_utf8_com_bom_e_instalado(self):
        origem = self.nova_origem("bom", "com-bom")
        (origem / "SKILL.md").write_bytes(b"\xef\xbb\xbf" + skill_md("com-bom").encode("utf-8"))
        p, saida = self.rodar("instalar", "--origem", origem)
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])
        self.assertEqual(self.descricao_instalada(), "com-bom")
        self.assertTrue((self.link / "SKILL.md").exists())

    def test_cf03_sem_name_legivel_a_recusa_diz_isso_e_nao_None(self):
        origem = self.nova_origem("sem-name", "sem-name")
        (origem / "SKILL.md").write_text("---\ndescription: sem name\n---\n", encoding="utf-8")
        p, saida = self.rodar("instalar", "--origem", origem)
        self.assertNotEqual(p.returncode, 0, "instalou uma origem cujo cabeçalho não declara name")
        self.assertFalse(self.copia.exists())
        erro = (saida or {}).get("erro", "")
        self.assertIn("name", erro, saida)
        self.assertIn("legível", erro, saida)
        self.assertNotIn("None", erro, saida)


class TestCF04MarcaIlegivel(_Preparo):
    def test_cf04_marca_ilegivel_nao_deixa_copia_preparada_orfa(self):
        v1, v2 = self.nova_origem("v1", "versao-1"), self.nova_origem("v2", "versao-2")
        self.instalar(v1)
        self.rodar("atualizar", "--origem", v2, preludio=QUEDA_ENTRE_AS_RENOMEACOES)
        self.assertFalse(self.copia.exists(), "a queda entre as renomeações não se reproduziu")
        marca = self.preparo / "troca-em-andamento.json"
        self.assertTrue(marca.is_file(), "a marca de troca não ficou na área de preparo")
        marca.write_text("{nao-json", encoding="utf-8")
        orfas = [s for s in self.sobras() if s != marca.name]
        self.assertEqual(len(orfas), 1, orfas)
        p, saida = self.rodar("atualizar", "--origem", v2)
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])
        self.assertEqual(self.descricao_instalada(), "versao-2")
        self.assertTrue((self.link / "SKILL.md").exists(), "a ligação ficou pendurada")
        self.assertEqual(self.sobras(), [], "a cópia preparada ficou órfã em skills-preparo depois da marca ilegível")
        passos = " ".join((saida or {}).get("passos", []))
        self.assertIn("ilegível", passos, saida)
        self.assertIn(orfas[0], passos, saida)


if __name__ == "__main__":
    unittest.main()
