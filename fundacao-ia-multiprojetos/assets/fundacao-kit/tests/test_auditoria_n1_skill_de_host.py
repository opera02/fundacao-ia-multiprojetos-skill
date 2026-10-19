"""Achado extra N1 (ensaio do usuário com a skill caveman): desabilitar no registro não desliga
uma skill de host. O comando tem de AVISAR quando o arquivo do `host-skill:` ainda existe, sem
apagar nem mover nada. Skill de host fictícia, numa fundação descartável."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

from helpers import FoundationTestCase

from fundacao.core import components
from fundacao.core.contracts import FundacaoError

PASTA = "projects/reversa-lab/.claude/skills/caveman-ficticio"


class TestN1SkillDeHost(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.pasta = self.root / PASTA
        self.pasta.mkdir(parents=True)
        (self.pasta / "SKILL.md").write_text("---\nname: caveman-ficticio\ndescription: estilo fictício\n---\n",
                                             encoding="utf-8")
        (self.root / "registry" / "components" / "caveman-ficticio.json").write_text(json.dumps({
            "schema_version": "fundacao.component/1", "component_id": "caveman-ficticio",
            "version": "skills/caveman-ficticio@0000000", "kind": "skill", "enabled": True,
            "entrypoint": f"host-skill:{PASTA}/SKILL.md", "allowed_projects": ["reversa-lab"],
            "permissions": [], "timeout_seconds": 10}), encoding="utf-8")

    def cli(self, *args):
        env = {k: v for k, v in os.environ.items() if k != "FUNDACAO_PRINCIPAL"}
        env.update(FUNDACAO_PRINCIPAL="operador-lab", PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, "-B", "-m", "fundacao", "--raiz", str(self.root), *args],
                              capture_output=True, text=True, encoding="utf-8", cwd=str(self.root), env=env)

    def test_n1_desabilitar_avisa_que_a_skill_continua_no_disco(self):
        p = self.cli("componente", "desabilitar", "--id", "caveman-ficticio")
        self.assertEqual(p.returncode, 0, p.stderr)
        saida = json.loads(p.stdout)
        self.assertFalse(saida["enabled"])
        avisos = saida.get("avisos") or []
        self.assertTrue(avisos, "a saída não avisa que o host continua carregando a skill")
        self.assertEqual(avisos[0]["codigo"], "W_SKILL_DE_HOST_AINDA_NO_DISCO")
        self.assertEqual(avisos[0]["pasta"], PASTA)
        self.assertIn("AVISO", p.stderr)
        self.assertTrue((self.pasta / "SKILL.md").is_file(), "o comando apagou ou moveu a skill")
        reg = json.loads((self.root / "registry" / "components" / "caveman-ficticio.json").read_text(encoding="utf-8"))
        self.assertFalse(reg["enabled"])
        self.assertNotIn("avisos", reg, "o aviso não pode ir para o registro")

    def test_n1_sem_a_pasta_nao_ha_aviso(self):
        self.pasta.rename(self.pasta.with_name("caveman-ficticio.retirada"))  # passo 2 já feito
        saida = json.loads(self.cli("componente", "desabilitar", "--id", "caveman-ficticio").stdout)
        self.assertFalse(saida.get("avisos"))

    def test_n1_componente_de_host_nao_e_despachado_pelo_kit(self):
        with self.assertRaises(FundacaoError):
            components.dispatch(self.root, self.con, self.eng, "reversa-lab", "caveman-ficticio", {})
        executados = self.con.execute("SELECT COUNT(*) FROM dispatch WHERE outcome = 'executed'").fetchone()[0]
        self.assertEqual(executados, 0, "o kit tentou executar um componente que o host lê do disco")


if __name__ == "__main__":
    unittest.main()
