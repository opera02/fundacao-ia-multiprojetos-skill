"""Regressões documentais de E7/E9/E13 (e, na 1.7.10, das sondas do sandbox); não medem obediência de um modelo."""
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

    def test_glob_sem_pasta_e_poda_pelo_nome_das_pastas(self):
        # 1.7.10: o Glob com padrão sem pasta casa em qualquer profundidade (desce em `projects/`), e a poda só vale pelo
        # nome das duas pastas (revisão de segurança final da 1.7.9, F1). Os comandos completos ficam nos modelos da
        # auditoria e da revisão (test_verificar_revisao_seguranca.py).
        retomada = item(secao(self.texto, '1. Antes de qualquer ação'), 2)
        for regra in (
            'sem poda de `projects/` e `state/` pelo nome das duas (`find` com `-name` e `-prune`, `grep` com '
            '`--exclude-dir`; no PowerShell, `-Exclude` não poda)',
            'O Glob com padrão sem pasta (`*`, `*.md`) desce em todas as subpastas: para ver a raiz, use `ls <raiz>`.',
        ):
            self.assertIn(regra, retomada)

    def test_regra_2_diz_que_o_isolamento_em_mnt_e_logico(self):
        # 1.7.10: nas sondas de 31/10/2026, com a raiz em `/mnt/e`, o sandbox não confinou os comandos; nenhuma frase
        # promete ali barreira do sistema operacional antes do canário do projeto.
        regra2 = ' '.join(self.texto.split('2. **Autorização fora do modelo.**', 1)[1].split('\n3. ', 1)[0].split())
        self.assertIn('No Ubuntu com a raiz em `/mnt/<x>`, o isolamento é lógico até o canário do projeto passar: nas '
                      'sondas de 31/10/2026, em `/mnt/e`, o sandbox não confinou comandos.', regra2)

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
