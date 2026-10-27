"""Arquivos que vão na cópia da skill do executor não repetem pistas da bancada da E11 (R179-27).

A cópia que o executor recebe exclui só evals/; modelos e testes de scripts vão junto. Exemplos tirados das partidas
de calibração e da coorte-1 (o filtro de permissão da bancada, os modos encontrados, a rota que um achado liga)
dariam ao executor a forma do erro que a avaliação mede. Este teste fica fora do pacote.
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2] / 'fundacao-ia-multiprojetos'
ARQUIVOS = ('assets/templates/AUDITORIA-SEGURANCA.md', 'assets/templates/REVISAO-SEGURANCA.md',
            'scripts/verificar_revisao_seguranca.py', 'scripts/tests/test_verificar_revisao_seguranca.py')
PISTAS = ('-perm -002', 'o+w', '0o666', 'modo 777', 'em 777', 'rota paga', 'route_policy.json gravável',
          'armadilha da bancada', 'nos 27 arquivos', 'diretório evidence/ foi listado', 'pela busca C6',
          'propriedade de `')  # o dono do arquivo na bancada; sem o nome, que é dado local


def _isolamento():
    spec = importlib.util.spec_from_file_location('isolamento', SKILL / 'evals' / 'isolamento.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SemPistasDaBancada(unittest.TestCase):
    def test_arquivos_do_pacote_nao_repetem_pistas(self):
        for rel in ARQUIVOS:
            texto = (SKILL / rel).read_text(encoding='utf-8')
            for pista in PISTAS:
                with self.subTest(arquivo=rel, pista=pista):
                    self.assertNotIn(pista, texto)

    def test_corpo_da_skill_nao_repete_pistas(self):
        """O corpo da SKILL.md vai no pedido do executor e passou a receber regras tiradas da bancada (R179-34 e
        R179-35). "rota paga" fica de fora: é a regra antiga da seção 3, item 8, e não um exemplo de partida."""
        texto = (SKILL / 'SKILL.md').read_text(encoding='utf-8')
        for pista in PISTAS:
            if pista == 'rota paga':
                continue
            with self.subTest(pista=pista):
                self.assertNotIn(pista, texto)
        self.assertIn('não habilite rota paga', texto)  # a exceção continua sendo a da regra de acessos e custos

    def test_copia_da_skill_nao_tem_nome_de_caso(self):
        """O alarme de isolamento recusa a preparação se um nome da cópia da skill contém o nome de um caso: o
        esqueleto chamado AUDITORIA-SOMENTE-LEITURA.md repetia o caso da E11 e parou toda a bancada (b1f2de0)."""
        iso = _isolamento()
        evals = json.loads((SKILL / 'evals' / 'evals.json').read_text(encoding='utf-8'))['evals']
        casos = sorted({ev['name'].casefold() for ev in evals})
        self.assertTrue(iso._nome_proibido('AUDITORIA-SOMENTE-LEITURA.md', casos))  # a regra acusa o nome antigo
        with tempfile.TemporaryDirectory() as tmp:
            iso.copiar_skill(SKILL, Path(tmp) / SKILL.name)
            percorridos = [c.relative_to(tmp).as_posix() for c, _ in iso.percorrer(Path(tmp))]
        self.assertIn(f'{SKILL.name}/assets/templates/AUDITORIA-SEGURANCA.md', percorridos)  # a cópia não veio vazia
        achados = [rel for rel in percorridos if any(iso._nome_proibido(p, casos) for p in rel.split('/'))]
        self.assertEqual(achados, [])


if __name__ == '__main__':
    unittest.main()
