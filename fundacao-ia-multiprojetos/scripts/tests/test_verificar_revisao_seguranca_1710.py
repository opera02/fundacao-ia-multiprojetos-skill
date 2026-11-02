"""F4 da revisão de segurança da 1.7.9 (corrigido na 1.7.10): o conferidor da revisão acumulava erros de alcance sem
teto e só cortava a lista no fim. Agora a lista para em MAX_ERROS + 1 mensagens durante a conferência, em todas as
regras, e o resto só é contado ("mais N erros"). Relatórios fictícios de 10 mil linhas; não lê caminhos."""
import importlib.util
import unittest

from test_verificar_revisao_seguranca import SCRIPT, achados_sem_confianca, relatorio


def carregar():
    spec = importlib.util.spec_from_file_location('verificar_revisao_1710', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestTetoDosErros(unittest.TestCase):
    def setUp(self):
        self.m = carregar()

    def test_dez_mil_linhas_de_alcance_param_de_acumular(self):
        texto = relatorio() + '\n## Outra seção\n' + 'nenhum arquivo foi alterado nesta linha\n' * 10_000
        acumulados = self.m._alcance(self.m._com_acento(texto))
        self.assertEqual(len(acumulados), self.m.MAX_ERROS + 1)  # a lista não passou do teto durante a conferência
        self.assertEqual(acumulados.ocultos, 10_000 - (self.m.MAX_ERROS + 1))
        out = self.m.validar({'relatorio': texto})
        self.assertFalse(out['preenchimento_ok'])
        self.assertEqual(len(out['erros']), self.m.MAX_ERROS + 1)
        self.assertEqual(out['erros'][-1], f'mais {10_000 - self.m.MAX_ERROS} erros: corrija estes e confira de novo')

    def test_dez_mil_achados_sem_confianca_tambem(self):
        out = self.m.validar({'relatorio': achados_sem_confianca(n=10_000)})
        self.assertEqual(len(out['erros']), self.m.MAX_ERROS + 1)
        self.assertEqual(out['erros'][-1], f'mais {10_000 - self.m.MAX_ERROS} erros: corrija estes e confira de novo')

    def test_lista_com_teto_conta_tudo_o_que_recebe(self):
        erros = self.m._Erros()
        erros += ['e'] * 30
        erros.extend(['f'] * 30)
        erros.append('g')
        self.assertEqual((len(erros), erros.ocultos), (self.m.MAX_ERROS + 1, 61 - (self.m.MAX_ERROS + 1)))
        self.assertEqual(self.m._resultado(erros)['erros'][-1],
                         f'mais {61 - self.m.MAX_ERROS} erros: corrija estes e confira de novo')
        self.assertTrue(self.m.validar({'relatorio': relatorio()})['preenchimento_ok'])  # controle


if __name__ == '__main__':
    unittest.main()
