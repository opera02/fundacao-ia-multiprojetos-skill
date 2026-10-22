"""Revisão de segurança da 1.7.7, segunda passada, área do kit — variante do R177-KIT-02: a própria cópia, por uma
ligação, passava como "fundação viva".

`_fundacao_viva` conferia só a raiz. Com `--raiz <pasta nova>` cujo `state/` é junção (no Windows; link simbólico nos
demais) para `<cópia>/state`, a ACL forjada na cópia e o manifesto recalculado, um principal que não administra a
fundação passava com `politica: "fundação viva"`: o `verificar` saía 0 e o `restaurar --aceitar-copia-sem-ancora`
liberava. Agora a raiz também não vale quando o banco (`<raiz>/state/state.sqlite`) fica dentro da cópia — pelo caminho
resolvido e pela identidade do disco, como em `dentro_da_copia`, ou por ser o próprio arquivo do banco dela (vínculo
físico) — ou quando há ligação no caminho do banco (`preparo.ligacao_no_caminho`, como no `backup criar`).

Identidades, projetos e conteúdos fictícios; nada é executado do código da cópia. Cada teste falha no HEAD revisado
(4c11fed) e passa depois da correção; o controle mostra a fundação viva real decidindo.
"""

from __future__ import annotations

import json
import os
import shutil
import unittest
from pathlib import Path

from apoio_auditoria import criar_ligacao_dir
from test_auditoria_1_7_7_ancora import MOTIVO
from test_revisao_1_7_7_kit import _Revisao

from fundacao.core import ancora_copia


class TestKit02BancoDaCopiaPorLigacao(_Revisao):
    def setUp(self):
        super().setUp()
        self.snap, _ = self.criar_copia()
        self.forjar_admin(self.snap, "operador-juridico")  # não administra a fundação viva; forja a ACL na cópia
        self.registro = self.registro_guardado_sem_livro()

    def raiz_nova(self, nome: str) -> Path:
        nova = self.pasta(nome)
        nova.mkdir()
        return nova

    def negado(self, raiz: Path) -> None:
        """O `verificar` e o `restaurar --aceitar-copia-sem-ancora` recusam quem não administra a fundação."""
        ver = self.cli_em("operador-juridico", raiz, self.root, "backup", "verificar", "--origem", str(self.snap))
        self.assertEqual(ver.returncode, 2, ver.stdout + ver.stderr)  # no 4c11fed: 0, com "fundação viva"
        self.assertIn("E_ACCESS_DENIED", ver.stderr)
        dest = self.pasta(f"dest-{raiz.name}")
        rest = self.cli_em("operador-juridico", raiz, self.root, "backup", "restaurar", "--origem", str(self.snap),
                           "--destino", str(dest), "--retiradas", str(self.registro),
                           "--aceitar-copia-sem-ancora", MOTIVO)
        self.assertEqual(rest.returncode, 2, rest.stdout + rest.stderr)
        self.assertIn("E_ACCESS_DENIED", rest.stderr)
        self.assertFalse(dest.exists(), "nada pode ser copiado para o destino")

    def test_state_ligado_ao_da_copia_nao_e_fundacao_viva(self):
        nova = self.raiz_nova("raiz-ligada")
        criar_ligacao_dir(nova / "state", self.snap / "state")
        self.negado(nova)
        viva, motivo = ancora_copia._fundacao_viva(nova, self.snap)
        self.assertIsNone(viva)
        self.assertIn("banco", motivo)

    def test_banco_que_e_o_arquivo_da_copia_nao_e_fundacao_viva(self):
        nova = self.raiz_nova("raiz-vinculo")
        (nova / "state").mkdir()
        try:
            os.link(self.snap / "state" / "state.sqlite", nova / "state" / "state.sqlite")
        except (OSError, NotImplementedError) as exc:  # sistema de arquivos sem vínculo físico (FAT, exFAT)
            self.skipTest(f"vínculo físico indisponível aqui: {exc}")
        self.negado(nova)
        self.assertIn("cópia", ancora_copia._fundacao_viva(nova, self.snap)[1])

    def test_ligacao_no_caminho_do_banco_nao_e_fundacao_viva(self):
        """Ligação para fora da cópia também não vale: o caminho do banco leva a outro lugar (pede o caminho real)."""
        outra = self.raiz_nova("outra-pasta")
        shutil.copytree(self.snap / "state", outra / "state")  # o banco forjado, fora da cópia
        nova = self.raiz_nova("raiz-ligada-fora")
        criar_ligacao_dir(nova / "state", outra / "state")
        self.negado(nova)
        self.assertIn("ligação", ancora_copia._fundacao_viva(nova, self.snap)[1])
        atalho = self.raiz_nova("atalho") / "raiz"  # a fundação viva por um atalho: vale o caminho real
        criar_ligacao_dir(atalho, self.root)  # dentro de uma pasta real: a limpeza remove a ligação sem segui-la
        self.assertIn("ligação", ancora_copia._fundacao_viva(atalho, self.snap)[1])

    def test_controle_fundacao_viva_real_continua_decidindo(self):
        """Sem ligação no caminho do banco, a fundação viva decide: o admin dela passa; a ACL forjada na cópia não."""
        ok = self.cli("operador-lab", "backup", "verificar", "--origem", str(self.snap))
        self.assertNotEqual(ok.returncode, 2, ok.stdout + ok.stderr)  # 0 ou 3 (a cópia forjada não confere)
        self.assertEqual(json.loads(ok.stdout)["autorizacao"]["politica"], "fundação viva")
        negado = self.cli("operador-juridico", "backup", "verificar", "--origem", str(self.snap))
        self.assertEqual(negado.returncode, 2, negado.stdout + negado.stderr)
        self.assertIn("E_ACCESS_DENIED", negado.stderr)


if __name__ == "__main__":
    unittest.main()
