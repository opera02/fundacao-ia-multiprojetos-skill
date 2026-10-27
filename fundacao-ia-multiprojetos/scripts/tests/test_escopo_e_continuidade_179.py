"""Regressões documentais de E7/E9/E13; não medem obediência de um modelo."""
import unittest

from apoio import SKILL
from test_referencias_decisoes import secao
from test_regra_retomada_desatualizada import item


class EscopoEContinuidade(unittest.TestCase):
    def setUp(self):
        self.texto = (SKILL / 'SKILL.md').read_text(encoding='utf-8')

    def test_ancestral_e_filtros_nao_delimitam_autorizacao(self):
        retomada = item(secao(self.texto, '1. Antes de qualquer ação'), 2)
        for regra in (
            'Não busque em ancestrais que incluam projetos alheios',
            '`head`, `maxdepth` e filtros de saída não delimitam autorização',
            'infraestrutura conhecida', 'pasta do projeto confirmada pelo serviço',
        ):
            self.assertIn(regra, retomada)

    def test_decisao_aplicavel_dispensa_pergunta_repetida(self):
        autonomia = ' '.join(secao(self.texto, '4. Autonomia, decisão e bloqueio').split())
        self.assertIn('Autorização aplicável já dada dispensa nova pergunta', autonomia)
        self.assertIn('Bloqueio na exclusão não suspende cópia e restauração já autorizadas', autonomia)
        self.assertIn('confira identidade, fonte e destino antes', autonomia)
        self.assertIn('ampliar escopo, usar dados reais', autonomia)

    def test_identidade_do_lancador_tem_prioridade_sem_remover_excecao_ficticia(self):
        kit = ' '.join(secao(self.texto, '7. Kit de referência').split())
        lab = kit[kit.index('**Laboratório (dados fictícios):**'):kit.index('**Dados reais:**')]
        self.assertIn('Se o lançador já fornece identidade válida, use-a sem trocá-la', lab)
        for regra in ('registrou no `init`', 'confirmada pelo serviço',
                      'não declarada nesta conversa', 'não invente', 'não pare só por isso'):
            self.assertIn(regra, lab)
        real = kit[kit.index('**Dados reais:**'):]
        self.assertIn('Não atribua `FUNDACAO_PRINCIPAL`', real)


if __name__ == '__main__':
    unittest.main()
