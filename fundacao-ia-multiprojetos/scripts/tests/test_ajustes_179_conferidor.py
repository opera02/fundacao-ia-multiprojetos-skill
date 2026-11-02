"""Limites do conferidor da revisão registrados na 1.7.9 (R179-26, limites 1 e 2; R179-28, limites 1 e 2), corrigidos
na 1.7.10 (pacote AJUSTES-179).

- Quadro em lista: só a coluna de afirmação da tabela era conferida, e a afirmação escrita como item de lista no quadro
  escapava da regra de alcance. Agora o item e as linhas que o continuam são conferidos; o parágrafo do modelo entre as
  linhas do quadro, não.
- Linha recuada com 4 ou mais espaços: saía como bloco de código, e a afirmação ou o hash abreviado num subitem de lista
  escapavam. Agora sai só o bloco recuado que vem depois de linha vazia e fora de lista; nos campos dos achados, a linha
  recuada continua fora (subitem não é o campo).
- Reticências coladas a uma palavra: "xa1b2c3…" e "a1b2c3…fim" não casavam com o padrão do hash abreviado. Agora as
  bordas recusam só dígito hexadecimal antes e depois.
Da revisão independente do pacote (1.7.10): a linha na margem encerra o bloco de código recuado (o caso que faltava
para o mutante sem esse reset); a continuação recuada do campo Correção fica fora com ele, salvo outro campo do achado
recuado; e a sequência só de letras a-f que continua numa palavra ("…fim", "…do") não é o fim do hash abreviado.
Cada caso que reprova aqui passava antes da correção. Relatórios fictícios; o conferidor não lê caminhos."""
import hashlib
import importlib.util
import unittest

from test_verificar_revisao_seguranca import SCRIPT, relatorio

H = hashlib.sha256(b'manifesto de exemplo').hexdigest()  # o mesmo hash fictício do teste do conferidor
ESCOPO = f'## Escopo\n- Invariância: manifesto `{H}` antes e depois.\n'


def carregar():
    spec = importlib.util.spec_from_file_location('verificar_revisao_ajustes_179', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def com_impacto(extra: str) -> str:
    """O relatório mínimo válido com `extra` logo depois do campo de impacto do achado."""
    return relatorio().replace('- Impacto: condicional', '- Impacto: condicional\n' + extra)


def com_secao(texto: str) -> str:
    """O relatório mínimo válido com `texto` antes das pendências (seção fora do modelo: conferida linha a linha)."""
    return relatorio().replace('## Pendências', texto + '\n## Pendências')


def quadro(corpo: str) -> str:
    return '## Quadro de afirmações\n\n' + corpo + '\n\n' + relatorio()


class Base(unittest.TestCase):
    def setUp(self):
        self.m = carregar()

    def validar(self, texto: str) -> dict:
        return self.m.validar({'relatorio': texto})

    def assertPassa(self, texto: str) -> None:
        out = self.validar(texto)
        self.assertTrue(out['preenchimento_ok'], out['erros'])

    def assertAlcance(self, texto: str, palavra: str) -> None:
        out = self.validar(texto)
        self.assertFalse(out['preenchimento_ok'], texto)
        self.assertTrue(any('cobertura' in e and f'("{palavra}")' in e for e in out['erros']), out['erros'])

    def assertHash(self, texto: str) -> None:
        out = self.validar(texto)
        self.assertFalse(out['preenchimento_ok'], texto)
        self.assertTrue(any('hash abreviado' in e for e in out['erros']), out['erros'])


class TestQuadroEmLista(Base):
    def test_item_de_lista_no_quadro_precisa_de_cobertura(self):
        for item, palavra in (('- A1: nenhum arquivo .py abre conexões (C1; fundacao; observado)', 'nenhum'),
                              ('* A1 — todos os arquivos de cache estão abertos', 'todos'),
                              ('1. A1: só o titular grava o registro', 'só'),
                              ('+ **A1**: qualquer conta pode editar a política', 'qualquer')):
            with self.subTest(item=item):
                self.assertAlcance(quadro(item), palavra)
        self.assertPassa(quadro('- A1: conexão não localizada nas fontes listadas pelo grep sem corte'))

    def test_linha_que_continua_o_item_tambem(self):
        for corpo in ('- A1: o código abre o caminho recebido\n  e nenhum arquivo valida a entrada',  # recuada
                      '- A1: o código abre o caminho recebido\ne nenhum arquivo valida a entrada',  # colada ao item
                      '- A1: o código abre o caminho recebido\n\n  e nenhum arquivo valida a entrada'):  # depois de vazia
            with self.subTest(corpo=corpo):
                self.assertAlcance(quadro(corpo), 'nenhum')

    def test_subitem_recuado_no_quadro(self):
        self.assertAlcance(quadro('- A1: o código abre o caminho\n    - nenhum arquivo valida a entrada'), 'nenhum')

    def test_paragrafo_do_modelo_entre_as_linhas_do_quadro_nao_e_afirmacao(self):
        # Os dois modelos explicam o quadro em parágrafos com "só" e "todos": continuam fora da regra, antes e depois da
        # tabela e depois de uma lista separada por linha vazia.
        corpo = ('No quadro, só as afirmações que um achado usam; todos com fonte.\n\n'
                 '| ID | Afirmação | Fonte |\n| --- | --- | --- |\n| A1 | core/x.py:10 abre o caminho | C1 |\n\n'
                 '- A2: core/x.py:12 grava o resultado\n\nRedija os achados só a partir deste quadro.')
        self.assertPassa(quadro(corpo))

    def test_instrucao_do_modelo_isenta_so_a_si(self):
        # A regra do modelo completo que fica entre os itens do quadro passa; a mesma palavra numa afirmação, não, nem
        # outra palavra de alcance na mesma linha da regra.
        regra = ('- Ocorrência após uma ação não prova sua causa. Registre a sequência observada; atribua o mecanismo '
                 'somente com\n  reprodução ou evidência que o vincule.')
        self.assertPassa(quadro(regra))
        self.assertAlcance(quadro('- A1: o registro é gravado somente com a chave do titular'), 'somente')
        self.assertAlcance(quadro(regra.replace('; atribua', '; todos os casos; atribua')), 'todos')

    def test_tabela_continua_conferida_so_na_coluna_da_afirmacao(self):
        tabela = ('| ID | Afirmação | Fonte |\n| --- | --- | --- |\n'
                  '| A1 | core/x.py:10 abre o caminho | C1: só a linha 10 |')
        self.assertPassa(quadro(tabela))
        self.assertAlcance(quadro(tabela.replace('core/x.py:10 abre o caminho', 'nenhum arquivo valida')), 'nenhum')


class TestSubitemRecuado(Base):
    def test_subitem_com_quatro_espacos_ou_tab_passa_pela_regra_de_alcance(self):
        for recuo in ('    ', '\t', ' \t', '      '):
            with self.subTest(recuo=repr(recuo)):
                self.assertAlcance(com_impacto(recuo + '- nenhum arquivo valida a entrada'), 'nenhum')  # no achado
                self.assertAlcance(com_secao('## Notas\n- Leitura de core/\n' + recuo + '- todos os arquivos estão '
                                             'abertos'), 'todos')  # em seção fora do modelo

    def test_titulo_recuado_num_subitem_nao_desliga_a_regra(self):
        # Um "## Escopo" recuado dentro de uma lista não é título: a linha seguinte continua conferida.
        self.assertAlcance(com_secao('## Notas\n- Leitura de core/\n    ## Escopo\nnenhum arquivo valida a entrada'),
                           'nenhum')

    def test_subitem_recuado_nas_pendencias_segue_o_campo_de_cima(self):
        out = self.validar(relatorio().replace('## Pendências\n', '## Pendências\n- Não verificado, com o motivo:\n'
                                               '    - só a pasta docs/ foi percorrida\n'))
        self.assertTrue(any('pendência descreve o que foi feito' in e for e in out['erros']), out['erros'])
        self.assertPassa(relatorio().replace('## Pendências\n', '## Pendências\n- Endurecimento sugerido:\n'
                                             '    - aceitar apenas caminhos da raiz\n'))

    def test_continuacao_recuada_de_paragrafo_e_conferida(self):
        # Sem linha vazia antes, a linha recuada continua o parágrafo: não é bloco de código.
        self.assertAlcance(com_secao('## Notas\nTexto corrido do relatório\n    e nenhum arquivo usa rede'), 'nenhum')

    def test_depois_de_linha_vazia_dentro_de_lista_continua_conferida(self):
        self.assertAlcance(com_secao('## Notas\n- Nota: leitura de core/\n\n    nenhum arquivo valida a entrada'),
                           'nenhum')

    def test_bloco_de_codigo_recuado_depois_de_linha_vazia_e_fora_de_lista_sai(self):
        codigo = '## Notas\nSaída do exemplo:\n\n    nenhum arquivo usa rede\n\n    abc123def4…9f0e\n'
        self.assertPassa(com_secao(codigo))
        # O bloco continua nas linhas recuadas seguidas, sem linha vazia entre elas.
        self.assertPassa(com_secao('## Notas\nSaída:\n\n    $ grep -c x core/a.py\n    todos os arquivos: 0\n'))
        # A primeira linha não vazia com menos recuo encerra o bloco: volta a ser conferida, e a linha recuada colada a
        # ela continua o parágrafo, não o bloco (revisão do pacote: sem zerar o bloco na linha da margem, ela sumia).
        self.assertAlcance(com_secao(codigo + 'Todos os arquivos estão abertos.'), 'todos')
        self.assertAlcance(com_secao(codigo + 'Texto na margem\n    e nenhum arquivo usa rede'), 'nenhum')
        # Uma lista antes, encerrada por parágrafo na margem depois de linha vazia, não faz do bloco um subitem.
        self.assertPassa(com_secao('## Notas\n- Nota: x\n\nSaída do exemplo:\n\n    nenhum arquivo usa rede\n'))

    def test_campo_do_achado_em_subitem_recuado_continua_fora(self):
        # Nos campos, a linha recuada continua fora: o subitem não preenche o campo do achado.
        texto = relatorio().replace('- Local: core/exemplo.py:10\n', '').replace(
            '- Evidência: grep -n x core/exemplo.py mostrou "10: x"\n',
            '- Evidência: grep -n x core/exemplo.py mostrou "10: x"\n    - Local: core/exemplo.py:10\n')
        out = self.validar(texto)
        self.assertFalse(out['preenchimento_ok'])
        self.assertTrue(any('preencha local' in e for e in out['erros']), out['erros'])

    def test_hash_abreviado_em_subitem_recuado_e_conferido(self):
        sub = f'    - manifesto `{H[:10]}…` conferido antes e depois'
        self.assertHash(com_impacto(sub))
        self.assertPassa(ESCOPO + com_impacto(sub))
        # No bloco de código recuado (depois de linha vazia e fora de lista), a abreviação continua fora.
        self.assertPassa(com_secao(f'## Notas\nSaída:\n\n    {H[:10]}…'))


CORRECAO = '- Correção estreita proposta e próxima validação: trocar X por Y'


class TestCorrecaoRecuada(Base):
    """Revisão do pacote (1.7.10): a linha recuada que continua o campo Correção é recomendação, como o campo. Com 4 ou
    mais espaços ela passou a chegar à regra de alcance (subitem) e virava falso positivo; com 2, já virava antes."""

    def test_continuacao_recuada_da_correcao_fica_fora(self):
        for recuo in (' ', '  ', '    ', '\t', '      '):  # reconferência: um espaço também continua o campo
            with self.subTest(recuo=repr(recuo)):
                self.assertPassa(com_impacto(CORRECAO + '\n' + recuo + 'e aceitar apenas caminhos da raiz'))
                self.assertPassa(com_impacto(CORRECAO + '\n' + recuo + '- aceitar só caminhos da raiz\n' + recuo +
                                             '- recusar todos os outros'))
        # Depois de linha vazia, dentro da lista, a linha recuada continua o campo; o subitem com rótulo que não é campo
        # do achado ("Opção A") também.
        self.assertPassa(com_impacto(CORRECAO + '\n\n    e aceitar apenas caminhos da raiz'))
        self.assertPassa(com_impacto(CORRECAO + '\n    - Opção A: aceitar apenas caminhos da raiz'))

    def test_outro_campo_do_achado_recuado_debaixo_da_correcao_continua_conferido(self):
        for recuo in ('  ', '    ', '\t'):
            with self.subTest(recuo=repr(recuo)):
                self.assertAlcance(com_impacto(CORRECAO + '\n' + recuo + '- Impacto: nenhum arquivo valida a entrada'),
                                   'nenhum')
                self.assertAlcance(com_impacto(CORRECAO + '\n' + recuo + '- Contraevidência considerada: todos os '
                                                                      'testes passam'), 'todos')

    def test_a_margem_e_o_titulo_encerram_a_correcao(self):
        self.assertAlcance(com_impacto(CORRECAO + '\nTodos os casos foram reproduzidos.'), 'todos')
        self.assertAlcance(com_impacto(CORRECAO + '\n- Situação da observação: nenhum teste a reproduz'), 'nenhum')
        # Reconferência: o título de achado recuado logo depois da Correção não herda o rótulo dela.
        for recuo in (' ', '   ', '    '):
            with self.subTest(recuo=repr(recuo)):
                self.assertAlcance(com_impacto(CORRECAO + '\n' + recuo + '### F2 — nenhum arquivo valida a entrada'),
                                   'nenhum')
        # "## Achados (continuação)" é seção de achados e não conta como segunda "## Achados": a linha recuada logo
        # depois do título não herda a Correção, último campo do achado de cima.
        texto = relatorio().replace('\n\n## Pendências', '\n' + CORRECAO + '\n## Achados (continuação)\n'
                                    '    e nenhum arquivo valida a entrada\n\n## Pendências')
        self.assertTrue(texto.index(CORRECAO) < texto.index('## Achados (continuação)'))
        self.assertAlcance(texto, 'nenhum')
        self.assertPassa(texto.replace('## Achados (continuação)\n', ''))  # sem o título, a linha continua a Correção

    def test_continuacao_de_outro_campo_continua_conferida(self):
        for recuo in ('  ', '    '):
            with self.subTest(recuo=repr(recuo)):
                self.assertAlcance(com_impacto(recuo + 'e nenhum arquivo valida a entrada'), 'nenhum')


class TestReticenciasColadas(Base):
    def test_colada_a_palavra_antes(self):
        nota = f'- Nota: commit{H[:10]}… conferido'
        self.assertHash(com_impacto(nota))
        self.assertPassa(ESCOPO + com_impacto(nota))

    def test_colada_a_palavra_depois(self):
        # "a1b2c3…fim": a sequência só de letras a-f que continua numa palavra ("f" de "fim", "d" de "do") é a palavra,
        # não o fim: confere-se só o começo. Revisão do pacote (1.7.10): antes, o "f" virava o fim, e a abreviação
        # certa, com o hash inteiro no relatório, não conferia (falso positivo).
        for nota in (f'- Nota: `{H[:10]}…fim` do trecho', f'- Nota: o manifesto {H[:10]}…do lote',
                     f'- Nota: o manifesto {H[:10]}…fé do lote', f'- Nota: o manifesto {H[:10]}…café do lote'):
            with self.subTest(nota=nota):
                self.assertHash(com_impacto(nota))
                self.assertPassa(ESCOPO + com_impacto(nota))
        # Começo errado continua recusado, com ou sem a palavra colada.
        errado = ('0' if H[0] != '0' else '1') + H[1:10]
        self.assertHash(ESCOPO + com_impacto(f'- Nota: `{errado}…fim` do trecho'))

    def test_fim_com_algarismo_colado_a_letra_continua_conferido(self):
        # A sequência com algarismo continua sendo o fim mesmo colada a uma letra: "…cca5x" confere "cca5", e um fim
        # errado ("…d4e5x") é recusado. Fim só de letras a-f seguido de espaço também é fim.
        self.assertNotEqual(H[-4:], 'd4e5')
        self.assertRegex(H[-4:], '[0-9]')
        self.assertPassa(ESCOPO + com_impacto(f'- Nota: `{H[:10]}…{H[-4:]}x` conferido'))
        self.assertHash(ESCOPO + com_impacto('- Nota: `' + H[:10] + '…d4e5x` conferido'))
        inteiro = H[:-4] + 'beef'
        nota = f'- Nota: `{inteiro[:10]}…beef` conferido'
        self.assertPassa(f'## Escopo\n- Invariância: manifesto `{inteiro}` antes e depois.\n' + com_impacto(nota))
        self.assertHash(ESCOPO + com_impacto(nota))

    def test_digito_hexadecimal_colado_continua_parte_do_comeco(self):
        # Controle das bordas: dígito hexadecimal antes não é borda; entra no começo, que deixa de conferir.
        d = '0' if H[0] != '0' else '1'
        self.assertHash(ESCOPO + com_impacto(f'- Nota: `{d}{H[:10]}…`'))
        self.assertPassa(ESCOPO + com_impacto(f'- Nota: `{H[:10]}…`'))

    def test_palavra_e_data_continuam_fora_mesmo_coladas(self):
        for nota in ('- Nota: decade... de testes', '- Nota: lote 20261025... arquivado', '- Nota: xdecade… de testes',
                     '- Nota: lote x20261025…fim'):
            with self.subTest(nota=nota):
                self.assertPassa(com_impacto(nota))


if __name__ == '__main__':
    unittest.main()
