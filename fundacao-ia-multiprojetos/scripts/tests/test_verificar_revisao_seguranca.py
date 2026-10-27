"""Conferência formal auxiliar; casos fictícios, sem gabarito de avaliação."""
import hashlib
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'verificar_revisao_seguranca.py'
TEMPLATE = SCRIPT.parent.parent / 'assets/templates/REVISAO-SEGURANCA.md'


def relatorio(confianca='alta'):
    return ('## Achados\n\n### F1 — observação estática\n- Local: core/exemplo.py:10\n'
            '- Evidência: grep -n x core/exemplo.py mostrou "10: x"\n'
            '- Cenário de falha concreto: entrada fictícia sem validação\n- Impacto: condicional\n'
            '- Confiança: ' + confianca + '\n\n## Pendências\nNão houve exploração.\n')


CAMPOS_OK = ('- Local: core/exemplo.py:10\n- Evidência: grep -n x core/exemplo.py mostrou "10: x"\n'
             '- Cenário de falha concreto: entrada fictícia sem validação\n- Impacto: condicional\n')


def achados_sem_confianca(extra='', n=1):
    """Achados completos, menos a confiança: a única falta que o teste examina."""
    return '## Achados\n' + ''.join('### F' + str(i) + '\n' + CAMPOS_OK for i in range(1, n + 1)) + extra + '\n'


def recibo(n=13):
    return json.dumps({'formato': 'fundacao.operacoes-observadas/1',
                       'operacoes': [{'id': 'comando-' + str(i)} for i in range(n)]}, ensure_ascii=False) + '\n'


def dados_com_recibo(n=13, declarado=None):
    raw = recibo(n)
    text = '## Evidências\n- Recibo SHA-256: ' + hashlib.sha256(raw.encode()).hexdigest()
    text += '\n- Operações no recibo: ' + str(n if declarado is None else declarado) + '\n\n' + relatorio()
    return {'relatorio': text, 'recibo_texto': raw}


class Conferidor(unittest.TestCase):
    def module(self):
        self.assertTrue(SCRIPT.exists(), 'conferidor ainda ausente')
        spec = importlib.util.spec_from_file_location('verificar_revisao', SCRIPT)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        return mod

    def test_valid_confidence_levels_do_not_approve_merit(self):
        m = self.module()
        for value in ['alta', 'média', 'media', 'baixa']:
            with self.subTest(value=value):
                out = m.validar({'relatorio': relatorio(value)})
                self.assertTrue(out['preenchimento_ok'], out)
                self.assertIs(out['merito_verificado'], False)

    def assertSoConfianca(self, out, n=1):
        self.assertFalse(out['preenchimento_ok'])
        self.assertEqual(len(out['erros']), n, out['erros'])
        self.assertTrue(all('confiança' in e for e in out['erros']), out['erros'])

    def test_missing_confidence_is_reported_for_each_finding(self):
        m = self.module()
        self.assertSoConfianca(m.validar({'relatorio': achados_sem_confianca(n=3)}), 3)

    def test_confidence_outside_finding_is_not_inherited(self):
        m = self.module()
        self.assertSoConfianca(m.validar({'relatorio': '- Confiança: alta\n' + achados_sem_confianca()}))

    def test_code_and_quoted_examples_do_not_fill_confidence(self):
        m = self.module()
        for body in ['```text\n- Confiança: alta\n```', '> - Confiança: alta', '<!--\n- Confiança: alta\n-->']:
            with self.subTest(body=body):
                self.assertSoConfianca(m.validar({'relatorio': achados_sem_confianca(body)}))

    def test_unknown_or_conflicting_confidence_is_rejected(self):
        m = self.module()
        for text in [relatorio('certeza absoluta'), relatorio('alta\n- Confiança: baixa')]:
            self.assertFalse(m.validar({'relatorio': text})['preenchimento_ok'])

    def test_explicit_no_findings_does_not_invent_one(self):
        m = self.module()
        out = m.validar({'relatorio': '## Achados\nNenhum achado comprovado no escopo.\n'})
        self.assertTrue(out['preenchimento_ok'], out)
        self.assertEqual(out['achados_conferidos'], 0)
        self.assertFalse(out['merito_verificado'])

    def test_absent_or_empty_findings_section_rejected(self):
        m = self.module()
        for text in ['texto sem estrutura', '## Achados\n\n## Pendências\n', '```\n## Achados\nNenhum achado comprovado no escopo.\n```']:
            self.assertFalse(m.validar({'relatorio': text})['preenchimento_ok'])

    def test_literal_receipt_count_and_hash(self):
        m = self.module(); out = m.validar(dados_com_recibo())
        self.assertTrue(out['preenchimento_ok'], out)
        self.assertEqual(out['recibo_observado']['operacoes'], 13)
        self.assertEqual(out['recibo_observado']['sha256'], hashlib.sha256(recibo().encode()).hexdigest())

    def test_copy_with_thirteen_cannot_be_declared_twelve(self):
        m = self.module(); out = m.validar(dados_com_recibo(declarado=12))
        self.assertFalse(out['preenchimento_ok'])
        self.assertTrue(any('quantidade' in e for e in out['erros']))

    def test_hash_mismatch_is_rejected(self):
        m = self.module(); d = dados_com_recibo()
        d['relatorio'] = d['relatorio'].replace(hashlib.sha256(d['recibo_texto'].encode()).hexdigest(), '0'*64)
        self.assertFalse(m.validar(d)['preenchimento_ok'])

    def test_duplicate_receipt_declarations_are_rejected(self):
        m = self.module()
        for label in ['- Recibo SHA-256:', '- Operações no recibo:']:
            d = dados_com_recibo()
            line = next(x for x in d['relatorio'].splitlines() if x.startswith(label))
            d['relatorio'] += '\n' + line + '\n'
            self.assertFalse(m.validar(d)['preenchimento_ok'])

    def test_blank_duplicate_receipt_declarations_are_rejected(self):
        m = self.module()
        for line in ['- Recibo SHA-256: ', '- Operações no recibo: ']:
            d = dados_com_recibo(); d['relatorio'] += '\n' + line + '\n'
            self.assertFalse(m.validar(d)['preenchimento_ok'])

    def test_no_findings_must_be_an_explicit_whole_line(self):
        m = self.module()
        for text in ['> Nenhum achado comprovado no escopo.', 'Não é verdade que nenhum achado comprovado no escopo.']:
            self.assertFalse(m.validar({'relatorio': '## Achados\n' + text})['preenchimento_ok'])

    def test_indented_examples_do_not_fill_confidence(self):
        m = self.module()
        for indent in ['    ', '\t', ' \t', '  \t', '   \t']:
            with self.subTest(indent=repr(indent)):
                self.assertSoConfianca(m.validar({'relatorio': achados_sem_confianca(indent + '- Confiança: alta')}))

    def test_confidence_value_cannot_be_borrowed_from_next_line(self):
        m = self.module()
        self.assertSoConfianca(m.validar({'relatorio': achados_sem_confianca('- Confiança:\nalta')}))

    def test_literal_unicode_and_crlf_are_not_normalized_for_hash(self):
        m = self.module(); raw = recibo().replace('"formato"', '"limite":"ação", "formato"').replace('\n', '\r\n')
        text = '- Recibo SHA-256: ' + hashlib.sha256(raw.encode()).hexdigest() + '\n- Operações no recibo: 13\n' + relatorio()
        out = m.validar({'relatorio': text, 'recibo_texto': raw})
        self.assertTrue(out['preenchimento_ok'], out)
        self.assertNotEqual(out['recibo_observado']['sha256'], hashlib.sha256(raw.replace('\r\n','\n').encode()).hexdigest())

    def test_numeric_overflow_in_receipt_is_rejected(self):
        m = self.module(); raw = recibo().replace('"formato"', '"numero":1e999, "formato"')
        text = '- Recibo SHA-256: ' + hashlib.sha256(raw.encode()).hexdigest() + '\n- Operações no recibo: 13\n' + relatorio()
        self.assertFalse(m.validar({'relatorio': text, 'recibo_texto': raw})['preenchimento_ok'])

    def test_receipt_fields_required_when_literal_supplied(self):
        m = self.module()
        self.assertFalse(m.validar({'relatorio': relatorio(), 'recibo_texto': recibo()})['preenchimento_ok'])

    def test_receipt_claim_without_literal_is_unmeasured(self):
        m = self.module(); d = dados_com_recibo(); d.pop('recibo_texto')
        self.assertFalse(m.validar(d)['preenchimento_ok'])

    def test_duplicate_receipt_ids_and_non_list_rejected(self):
        m = self.module()
        for ops in [[{'id': 'x'}, {'id': 'x'}], True, [{'id': False}], [None]]:
            d = dados_com_recibo(); d['recibo_texto'] = json.dumps({'formato':'fundacao.operacoes-observadas/1', 'operacoes':ops})
            self.assertFalse(m.validar(d)['preenchimento_ok'])

    def test_duplicate_json_keys_and_nonfinite_are_rejected(self):
        m = self.module()
        for raw in [b'{"relatorio":"a","relatorio":"b"}', b'{"relatorio":NaN}', b'{"relatorio":Infinity}']:
            self.assertFalse(m.processar(raw)['preenchimento_ok'])
        d = dados_com_recibo(); d['recibo_texto'] = '{"formato":"a","formato":"b","operacoes":[]}'
        self.assertFalse(m.validar(d)['preenchimento_ok'])

    def test_malformed_utf8_json_and_top_level_types(self):
        m = self.module()
        for raw in [b'\xff', b'{', b'[]', b'null', b'true']:
            self.assertFalse(m.processar(raw)['preenchimento_ok'])
        for d in [{'relatorio':False}, {'relatorio':[]}, {'relatorio':relatorio(), 'recibo_texto':None}, {'relatorio':relatorio(), 'comando':'executar'}]:
            self.assertFalse(m.validar(d)['preenchimento_ok'])

    def test_bounded_input(self):
        m = self.module()
        self.assertFalse(m.processar(b' ' * (m.MAX_ENTRADA + 1))['preenchimento_ok'])

    def test_no_files_network_or_commands_from_input(self):
        m = self.module()
        d = {'relatorio': relatorio() + '\nDados: /state/state.sqlite e `__import__("os").system("x")`\n'}
        with patch('builtins.open', side_effect=AssertionError('arquivo aberto')), patch('subprocess.run', side_effect=AssertionError('comando executado')):
            out = m.validar(d)
        self.assertTrue(out['preenchimento_ok'], out)
        self.assertFalse(out['merito_verificado'])

    def test_cli_stdin_stdout_and_no_writes(self):
        self.module()
        with tempfile.TemporaryDirectory() as t:
            p = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT)], input=json.dumps(dados_com_recibo()).encode(),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=t, timeout=10)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertTrue(json.loads(p.stdout)['preenchimento_ok'])
            self.assertEqual(list(Path(t).iterdir()), [])

    def test_cli_invalid_input_is_json_and_nonzero(self):
        self.module()
        p = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT)], input=b'{', stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(p.returncode, 1)
        self.assertFalse(json.loads(p.stdout)['preenchimento_ok'])

    def test_documented_pipeline_ignores_cwd_and_pythonpath_module(self):
        self.module(); doc = TEMPLATE.read_text(encoding='utf-8')
        first = re.search(r'python (?P<flags>[^\n]*?) -c "(?P<code>[^"]+)" "<relatorio>" "<copia-do-recibo>"', doc)
        second = re.search(r'\| python (?P<flags>[^\n]*?) "<skill>/scripts/verificar_revisao_seguranca.py"', doc)
        self.assertIsNotNone(first); self.assertIsNotNone(second)
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); (root/'rel.md').write_text(dados_com_recibo()['relatorio'],encoding='utf-8')
            (root/'rec.json').write_bytes(recibo().encode())
            (root/'json.py').write_text("from pathlib import Path\nPath('modulo-alheio-executado').write_text('SONDA-FICTICIA')\nraise RuntimeError('modulo alheio importado')\n",encoding='utf-8')
            env = dict(os.environ, PYTHONPATH=str(root))
            a = subprocess.run([sys.executable,*shlex.split(first['flags']),'-c',first['code'],'rel.md','rec.json'],
                               cwd=t,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
            self.assertEqual(a.returncode,0,a.stderr)
            b = subprocess.run([sys.executable,*shlex.split(second['flags']),str(SCRIPT)],input=a.stdout,
                               cwd=t,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
            self.assertEqual(b.returncode,0,b.stderr)
            self.assertTrue(json.loads(b.stdout)['preenchimento_ok'])
            self.assertFalse((root/'modulo-alheio-executado').exists())

    def test_finding_requires_local_evidence_scenario_and_impact(self):
        m = self.module()
        for campo, nome in [('- Local:', 'local'), ('- Evidência:', 'evidência'), ('- Cenário', 'cenário'), ('- Impacto:', 'impacto')]:
            with self.subTest(campo=campo):
                texto = '\n'.join(l for l in relatorio().splitlines() if not l.startswith(campo))
                out = m.validar({'relatorio': texto})
                self.assertFalse(out['preenchimento_ok'])
                self.assertTrue(any(nome in e for e in out['erros']), out['erros'])
        vazio = relatorio().replace('- Impacto: condicional', '- Impacto:')
        self.assertFalse(m.validar({'relatorio': vazio})['preenchimento_ok'])

    def test_local_needs_line_record_or_metadata(self):
        m = self.module()
        self.assertFalse(m.validar({'relatorio': relatorio().replace('core/exemplo.py:10', 'core/exemplo.py')})['preenchimento_ok'])
        for local in ['config/exemplo.json (metadado: dono)', 'evento 12 do registro', 'core/a.py, linhas 3-9']:
            with self.subTest(local=local):
                out = m.validar({'relatorio': relatorio().replace('core/exemplo.py:10', local)})
                self.assertTrue(out['preenchimento_ok'], out)

    def test_scope_claim_in_finding_needs_declared_coverage(self):
        m = self.module()
        for frase in ['o código não valida entradas em nenhum ponto', 'todos os arquivos de cache estão abertos',
                      'só há ocorrências em cli.py', 'qualquer conta pode editar', 'não há uso de rede', 'a fundação está segura']:
            with self.subTest(frase=frase):
                texto = relatorio().replace('- Impacto: condicional', '- Impacto: ' + frase)
                out = m.validar({'relatorio': texto})
                self.assertFalse(out['preenchimento_ok'])
                self.assertTrue(any('cobertura' in e for e in out['erros']), out['erros'])
        for frase in ['eval não localizado nas fontes core/ e adapters/ (grep sem corte)',
                      'condicional: qualquer conta com acesso à pasta, não conferido',
                      'nos 12 arquivos listados o atributo aparece em todos']:
            with self.subTest(frase=frase):
                texto = relatorio().replace('- Impacto: condicional', '- Impacto: ' + frase)
                self.assertTrue(m.validar({'relatorio': texto})['preenchimento_ok'])

    def test_scope_claim_in_claims_table_needs_coverage_header_is_ignored(self):
        m = self.module()
        quadro = ('## Quadro de afirmações\n| ID | Afirmação | Fonte | Escopo | Estado | Condições |\n'
                  '| --- | --- | --- | --- | --- | --- |\n'
                  '| A1 | nenhum arquivo .py abre conexões | find | fundacao | observado | sem pendência |\n\n')
        out = m.validar({'relatorio': quadro + relatorio()})
        self.assertFalse(out['preenchimento_ok'])
        ok = quadro.replace('nenhum arquivo .py abre conexões', 'conexão não localizada nas fontes listadas pelo grep sem corte')
        self.assertTrue(m.validar({'relatorio': ok + relatorio()})['preenchimento_ok'])

    def test_positive_summary_section_is_rejected(self):
        m = self.module()
        for titulo in ['## O que está bem', '## Pontos fortes', '## Sem achado comprovado nestas áreas (no que li)']:
            with self.subTest(titulo=titulo):
                out = m.validar({'relatorio': relatorio() + '\n' + titulo + '\n- rotas desligadas\n'})
                self.assertFalse(out['preenchimento_ok'])
                self.assertTrue(any('positiva' in e for e in out['erros']), out['erros'])

    def test_exempt_phrases_are_not_scope_claims(self):
        m = self.module()
        texto = relatorio().replace('- Impacto: condicional', '- Impacto: condicional; revisão somente leitura')
        self.assertTrue(m.validar({'relatorio': texto})['preenchimento_ok'])
        proposta = relatorio().replace('- Impacto: condicional',
                                       '- Impacto: condicional\n- Correção estreita proposta: validar a chave antes de qualquer uso real')
        self.assertTrue(m.validar({'relatorio': proposta})['preenchimento_ok'])
        self.assertTrue(m.validar({'relatorio': '## Achados\nNenhum achado comprovado no escopo.\n'})['preenchimento_ok'])

    def test_report_filled_from_the_template_passes(self):
        m = self.module(); doc = TEMPLATE.read_text(encoding='utf-8')
        trocas = [
            ('| A1 | <frase limitada ao que foi conferido> | <arquivo:linha, comando/resultado ou registro> | '
             '<arquivos, identidades e janela cobertos> | <estado> | <condições ou nenhuma> |',
             '| A1 | core/x.py:10 abre o caminho recebido sem conferir | sed -n 10p core/x.py: "open(caminho)" | '
             'core/x.py:10 | observado | nenhuma |'),
            ('| <operação e alvo reais> | <fonte recuperável no rastro: o comando copiado> | <resultado literal ou resumo fiel> '
             '| <total contado (wc -l) e exibidas; cortada se o total passa das exibidas ou se o comando tem limite '
             'próprio e o total chega a ele> | <conclusão limitada a esse resultado> |',
             '| leitura de core/x.py:10 | sed -n 10p core/x.py | open(caminho) | 1; exibidas: todas | a linha 10 abre o '
             'caminho recebido |'),
            ('### <ID> — <título>', '### S1 — core/x.py:10 abre caminho sem conferência'),
            ('- Severidade (crítica · alta · média · baixa) e por quê:',
             '- Severidade (crítica · alta · média · baixa) e por quê: média, condicional à origem do caminho'),
            ('- Confiança: <alta | média | baixa>', '- Confiança: média'),
            ('- Situação da observação: confirmada | a validar', '- Situação da observação: confirmada'),
            ('- Alcance e impacto: demonstrados | condicionais; pré-requisitos conferidos e os que faltam:',
             '- Alcance e impacto: condicional: depende de quem fornece o caminho, não conferido'),
            ('- Origem: introduzido nesta versão | regressão | preexistente | indeterminado', '- Origem: indeterminado'),
            ('- Local: arquivo:linha e revisão (ou camada não commitada)', '- Local: core/x.py:10 (revisão atual)'),
            ('- Evidência: IDs do quadro de afirmações, comando e trecho literal redigido, e caminho da entrada à '
             'operação sensível (observado ou condicional):',
             '- Evidência: A1; sed -n 10p core/x.py mostrou "open(caminho)"'),
            ('- Quem consegue disparar e com que pré-requisitos (identidade, permissão, arquivo):',
             '- Quem consegue disparar e com que pré-requisitos (identidade, permissão, arquivo): não medido'),
            ('- Cenário de falha concreto (a entrada ou o estado que faz quebrar) e impacto:',
             '- Cenário de falha concreto (a entrada ou o estado que faz quebrar) e impacto: um nome com dois pontos sai '
             'da pasta esperada (condicional)'),
            ('- Contraevidência considerada; reprodução ou teste, ou a prova que falta:',
             '- Contraevidência considerada; reprodução ou teste, ou a prova que falta: não medido'),
            ('- Recibo SHA-256: <hash dos bytes da cópia entregue>\n- Operações no recibo: <quantidade na cópia entregue>\n', ''),
        ]
        for velho, novo in trocas:
            self.assertEqual(doc.count(velho), 1, velho)
            doc = doc.replace(velho, novo)
        out = m.validar({'relatorio': doc})
        self.assertTrue(out['preenchimento_ok'], out['erros'])
        self.assertEqual(out['achados_conferidos'], 1)

    def test_lean_read_only_audit_skeleton_filled_passes(self):
        m = self.module()
        enxuto = TEMPLATE.with_name('AUDITORIA-SEGURANCA.md')
        doc = enxuto.read_text(encoding='utf-8')
        for trecho in ('Divergências de método', '## Comandos executados', '## Resposta final', 'Cenário de falha concreto',
                       '- Confiança:', 'não estabelece que a fundação é segura', 'REVISAO-SEGURANCA.md',
                       'verificar_revisao_seguranca.py', 'não declare a auditoria aprovada', 'Situação da observação',
                       'Hipóteses não comprovadas', 'Invariância', 'Escopo efetivamente examinado', 'AVISOS-DE-TERCEIROS.md',
                       'wc -l < "$TMPDIR/aud/C1.txt"', 'não renumere', 'Linhas na saída (`wc -l`) e exibidas',
                       "grep -F -- '<pedaço do trecho>'", 'não conte a olho', 'apague-a depois da conferência',
                       'mkdir -p "$TMPDIR/aud"', '{ <comando>; } > "$TMPDIR/aud/C1.txt" 2>&1',
                       '& { <comando> } *>&1 | Out-File', 'Select-String -SimpleMatch', "grep -n 'C[0-9]'",
                       'Não ponha limite dentro das', 'só as afirmações que um achado ou a invariância usam',
                       'Nos achados, não entra fato que o quadro não tenha', 'Saída agrupada', 'a pendência não o descreve',
                       'copiado da saída de `cat`', 'sem acréscimo', 'o relatório não aponta para ela',
                       'Leitura feita com a ferramenta Read também entra na tabela',
                       'não mude o diretório do shell (`cd`, `pushd`, `Set-Location`)',
                       '`.claude/.cc-writes` no diretório atual do shell', '`( cd <pasta> && <comando> )`'):
            self.assertIn(trecho, doc)
        trocas = [
            ('| C1 | <comando como foi emitido> | <não; ou sim, com ou sem poda> | <número copiado do wc -l; exibidas: '
             'todas, ou as primeiras 80> | <linhas copiadas do arquivo do comando> |',
             '| C1 | grep -n chave config/exemplo.json | não | 1; exibidas: todas | config/exemplo.json:3: chave = livre |'),
            ('| A1 | <frase limitada ao que o comando mostrou> | <C3: trecho> | <arquivos ou caminhos percorridos> | <estado> | <condições ou nenhuma> |',
             '| A1 | config/exemplo.json:3 aceita a chave sem lista de valores | C1: config/exemplo.json:3 | config/exemplo.json | observado | nenhuma |'),
            ('- Situação da observação: confirmada | a validar', '- Situação da observação: confirmada'),
            ('### F1 — <título: a observação, não a exploração>', '### F1 — config/exemplo.json aceita chave livre'),
            ('- Local: arquivo:linha (para modo de arquivo, o arquivo e "metadado")', '- Local: config/exemplo.json:3'),
            ('- Evidência: Nº do comando, trecho literal redigido e IDs do quadro', '- Evidência: C1, A1: "config/exemplo.json:3: chave = livre"'),
            ('- Cenário de falha concreto (condicional se depender de pré-requisito não conferido):',
             '- Cenário de falha concreto (condicional se depender de pré-requisito não conferido): um valor inesperado muda o comportamento (condicional)'),
            ('- Impacto (demonstrado | condicional, com os pré-requisitos que faltam):',
             '- Impacto (demonstrado | condicional, com os pré-requisitos que faltam): condicional a quem edita o arquivo'),
            ('- Severidade (crítica · alta · média · baixa) e por quê:', '- Severidade (crítica · alta · média · baixa) e por quê: média'),
            ('- Confiança: <alta | média | baixa>', '- Confiança: média'),
        ]
        for velho, novo in trocas:
            self.assertEqual(doc.count(velho), 1, velho)
            doc = doc.replace(velho, novo)
        out = m.validar({'relatorio': doc})
        self.assertTrue(out['preenchimento_ok'], out['erros'])
        self.assertEqual(out['achados_conferidos'], 1)
        fluxo = (SCRIPT.parent.parent / 'references' / 'fluxo-c-operar.md').read_text(encoding='utf-8')
        self.assertIn('assets/templates/AUDITORIA-SEGURANCA.md', fluxo)
        self.assertIn('não mude o diretório do shell para dentro da árvore revisada', fluxo)
        completo = TEMPLATE.read_text(encoding='utf-8')
        self.assertIn('não mude o diretório do shell para dentro da árvore revisada', completo)
        fontes = (SCRIPT.parent.parent / 'references' / 'fontes-verificadas.md').read_text(encoding='utf-8')
        self.assertIn('a CLI cria `.claude/.cc-writes`', fontes)  # o fato que o C10 cita
        cru = enxuto.read_text(encoding='utf-8')
        for velho, novo in trocas:
            if 'Local' not in velho and 'Evidência' not in velho:
                cru = cru.replace(velho, novo)
        out = m.validar({'relatorio': cru})
        self.assertFalse(out['preenchimento_ok'])
        self.assertEqual(sum('texto do modelo' in e for e in out['erros']), 2, out['erros'])

    def test_skill_md_routes_read_only_audit_to_lean_skeleton_before_first_command(self):
        # 1.7.9: a auditoria da fundação em uso, só lendo, chega ao esqueleto antes do primeiro passo da seção 1 (que já
        # lê a RETOMADA e roda o inventário) e pelo mapa (seção 8); o arquivo apontado existe. R179-38: só nesse pedido,
        # dito "auditoria de segurança" ou "revisão de segurança" (a auditoria operacional, que lê o estado, não). Com
        # "leia primeiro" sem condição, quase todas as execuções começavam pelo esqueleto em pedidos que não eram
        # auditoria, e o escopo dele (sem banco, sem executar código) chegou a impedir que se fechasse uma etapa pendente.
        skill = (SCRIPT.parent.parent / 'SKILL.md').read_text(encoding='utf-8')
        secoes = {m['n']: m['corpo'] for m in re.finditer(r'^## (?P<n>\d+)\.[^\n]*\n(?P<corpo>.*?)(?=^## |\Z)', skill,
                                                           re.S | re.M)}
        antes_dos_passos = ' '.join(secoes['1'].split('\n1. ', 1)[0].split())
        self.assertIn('Só no pedido de auditoria de segurança ou revisão de segurança da fundação em uso, só lendo, '
                      'leia antes `assets/templates/AUDITORIA-SEGURANCA.md`; nos demais pedidos, não o leia.',
                      antes_dos_passos)
        self.assertRegex(secoes['8'], r'\| Auditoria de segurança da fundação em uso, só lendo \| '
                                      r'`assets/templates/AUDITORIA-SEGURANCA\.md` \|')
        self.assertNotIn('leia primeiro', skill.lower())  # a frase sem condição que levava qualquer pedido ao esqueleto
        self.assertEqual(skill.count('AUDITORIA-SEGURANCA.md'), 2)  # a condição da seção 1 e o mapa; nenhum outro
        self.assertTrue(TEMPLATE.with_name('AUDITORIA-SEGURANCA.md').is_file())
        # O primeiro comando pode sair junto da leitura do esqueleto: a regra do diretório do shell vem no próprio corpo,
        # antes da condição da auditoria, e vale para todos os pedidos.
        self.assertTrue(antes_dos_passos.startswith('Desde o primeiro comando, não entre na fundação com `cd`/`pushd`'))
        self.assertIn('`.claude/.cc-writes` no diretório atual', antes_dos_passos)  # a pasta nova, mesmo com `.claude/`
        # Valendo para todos, a regra não pode conflitar com os comandos que rodam na raiz: subshell, sem `cd` solto.
        self.assertIn('(cd <raiz> && python -m fundacao init --admin <id-do-titular>)', secoes['7'])
        self.assertIn('(cd <raiz> && python -B -m unittest discover -s tests)', secoes['7'])
        fluxo_a = (SCRIPT.parent.parent / 'references' / 'fluxo-a-implantar.md').read_text(encoding='utf-8')
        for nome, texto in (('SKILL.md', skill), ('fluxo-a-implantar.md', fluxo_a)):
            with self.subTest(arquivo=nome):
                self.assertIsNone(re.search(r'^cd <raiz>', texto, re.M))

    def test_poda_com_inicio_absoluto_e_as_duas_pastas(self):
        # 1.7.9 (revisão de segurança final, F1): `find <absoluto> -path ./projects -prune` não poda nada,
        # `--exclude-dir=projects` deixa `state/` e, no PowerShell, `-Exclude` não poda a recursão; os exemplos que os
        # modelos davam levavam a travessia que a própria regra proíbe. F2: `git -C` roda o monitor da árvore.
        skill = ' '.join((SCRIPT.parent.parent / 'SKILL.md').read_text(encoding='utf-8').split())
        self.assertIn('sem poda de `projects/` e `state/`', skill)
        for nome in ('REVISAO-SEGURANCA.md', 'AUDITORIA-SEGURANCA.md'):
            texto = ' '.join(TEMPLATE.with_name(nome).read_text(encoding='utf-8').split())
            with self.subTest(modelo=nome):
                # pelo nome: `-path` falha com raiz em barra invertida, barra no fim ou colchetes (segunda passada)
                self.assertIn('find <raiz> -type d \\( -name projects -o -name state \\) -prune -o -type f -print', texto)
                self.assertNotIn("-path '<raiz>/projects'", texto)
                self.assertIn('grep -r --exclude-dir=projects --exclude-dir=state', texto)
                self.assertIn('`-Exclude` não poda', texto)
                self.assertIn("Get-ChildItem -Force -LiteralPath <raiz> | Where-Object Name -notin 'projects','state' | "
                              "Get-ChildItem -Force -Recurse -File", texto)  # -Force: oculto não sai calado
                self.assertNotIn('find . -path ./projects -prune', texto)
        auditoria = ' '.join(TEMPLATE.with_name('AUDITORIA-SEGURANCA.md').read_text(encoding='utf-8').split())
        self.assertIn('Não rode `git` na árvore auditada', auditoria)
        self.assertIn('git -c core.fsmonitor=false --no-optional-locks -C <pasta>` sem programa configurado', auditoria)
        self.assertNotIn('`git --no-optional-locks -C', auditoria)

    def test_environment_inventory_only_when_request_allows_probing_host(self):
        # 1.7.9: mesmo com --somente-localizar, o inventário lê PATH e /proc; num pedido restrito a uma pasta ele não
        # roda (seção 1, item 3), e o esqueleto da auditoria põe o host fora da árvore no que fica fora do escopo.
        skill = (SCRIPT.parent.parent / 'SKILL.md').read_text(encoding='utf-8')
        item3 = ' '.join(skill.split('\n3. **Identifique o ambiente', 1)[1].split('\n4. ', 1)[0].split())
        self.assertIn('Se o pedido deixa sondar o host, rode', item3)
        self.assertIn('mas lê PATH e `/proc`', item3)
        self.assertIn('Pedido restrito a uma pasta: não rode e declare o ambiente não inventariado.', item3)
        escopo = ' '.join(TEMPLATE.with_name('AUDITORIA-SEGURANCA.md').read_text(encoding='utf-8')
                          .split('- Fora do escopo por regra:', 1)[1].split('\n- ', 1)[0].split())
        self.assertIn('o host fora da árvore (o inventário do ambiente, `inspecionar_ambiente.py`, lê PATH e `/proc`: não '
                      'rode)', escopo)
        codigo = (SCRIPT.parent / 'inspecionar_ambiente.py').read_text(encoding='utf-8')
        self.assertIn('/proc/mounts', codigo)  # o motivo do texto continua verdadeiro

    def test_lean_skeleton_documented_pipeline_without_receipt(self):
        self.module()
        doc = TEMPLATE.with_name('AUDITORIA-SEGURANCA.md').read_text(encoding='utf-8')
        first = re.search(r'python (?P<flags>[^\n]*?) -c "(?P<code>[^"]+)" "<relatorio>" \|', doc)
        second = re.search(r'\| python (?P<flags>[^\n]*?) "<skill>/scripts/verificar_revisao_seguranca.py"', doc)
        self.assertIsNotNone(first); self.assertIsNotNone(second)
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); (root/'rel.md').write_text(relatorio(), encoding='utf-8')
            (root/'json.py').write_text("raise RuntimeError('modulo alheio importado')\n", encoding='utf-8')
            env = dict(os.environ, PYTHONPATH=str(root))
            a = subprocess.run([sys.executable, *shlex.split(first['flags']), '-c', first['code'], 'rel.md'],
                               cwd=t, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            self.assertEqual(a.returncode, 0, a.stderr)
            b = subprocess.run([sys.executable, *shlex.split(second['flags']), str(SCRIPT)], input=a.stdout,
                               cwd=t, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            self.assertEqual(b.returncode, 0, b.stderr)
            self.assertTrue(json.loads(b.stdout)['preenchimento_ok'])

    def test_abbreviated_hash_must_match_a_full_hash_of_the_report(self):
        m = self.module()
        h = hashlib.sha256(b'manifesto de exemplo').hexdigest()
        outro = h[:-5] + ('0' if h[-5] != '0' else '1') + h[-4:]  # mesmo começo, fim diferente
        def com(*celulas, inteiro=True):
            linhas = ''.join(f'| C{i} | sha256sum lista.txt | não | 1; exibidas: todas | `{c}  lista.txt` |\n'
                             for i, c in enumerate(celulas, 1))
            escopo = f'## Escopo\n- Invariância: C1, manifesto `{h}` antes e depois.\n' if inteiro else ''
            return escopo + '## Comandos executados\n' + linhas + relatorio()
        for celula in (f'{h[:12]}…{h[-5:]}', f'{h[:12]}...{h[-5:]}', f'{h[:10]}…', h):
            with self.subTest(celula=celula):
                out = m.validar({'relatorio': com(celula)})
                self.assertTrue(out['preenchimento_ok'], out['erros'])
        for celula, inteiro in ((f'{outro[:12]}...{outro[-5:]}', True), (f'{h[:10]}…', False),
                                (f'{h[:12]}…{h[-5:]}', False)):
            with self.subTest(celula=celula, inteiro=inteiro):
                out = m.validar({'relatorio': com(celula, inteiro=inteiro)})
                self.assertFalse(out['preenchimento_ok'])
                self.assertTrue(any('hash abreviado' in e for e in out['erros']), out['erros'])
        # Palavra só de letras a-f, data só de algarismos, exemplo em bloco de código e intervalo do git (três pontos,
        # os dois lados com 7 ou mais dígitos) não são conferidos.
        for extra in ('- Nota: decade... de testes\n', '- Nota: lote 20261025... arquivado\n',
                      '```\nabc123def4...9f0e\n```\n', '- Nota: `git diff 82015fe...5f4e4f5`\n'):
            with self.subTest(extra=extra):
                out = m.validar({'relatorio': relatorio().replace('## Pendências', extra + '\n## Pendências')})
                self.assertTrue(out['preenchimento_ok'], out['erros'])
        # Com "…" ou quatro pontos, sem git na linha, e com hash inteiro só em comentário, a abreviação é conferida.
        for celula, inteiro in ((f'{outro[:12]}…{outro[-7:]}', True), (f'{outro[:12]}....{outro[-5:]}', True),
                                (f'{outro[:12]}...{outro[-11:]}', True)):
            with self.subTest(celula=celula):
                self.assertFalse(m.validar({'relatorio': com(celula, inteiro=inteiro)})['preenchimento_ok'])
        comentado = com(f'{h[:12]}…{h[-5:]}', inteiro=False).replace('## Comandos', f'<!-- {h} -->\n## Comandos')
        self.assertFalse(m.validar({'relatorio': comentado})['preenchimento_ok'])
        # git noutra célula da mesma linha não isenta a abreviação; na mesma célula, com `\|` escapado antes, isenta.
        linha = f'| C3 | git log -1 | não | 1; exibidas: todas | `{outro[:12]}...{outro[-11:]}` |\n'
        self.assertFalse(m.validar({'relatorio': '## Comandos executados\n' + linha + relatorio()})['preenchimento_ok'])
        linha = '| C3 | `ls \\| git diff 82015fe...5f4e4f5` | não | 1; exibidas: todas | `M x.py` |\n'
        out = m.validar({'relatorio': '## Comandos executados\n' + linha + relatorio()})
        self.assertTrue(out['preenchimento_ok'], out['erros'])

    def test_many_abbreviated_hashes_are_capped_and_bounded(self):
        m = self.module()
        texto = relatorio() + '\n' + ''.join(f'`{"0a" * 3}{i:06x}…`\n' for i in range(300))
        out = m.validar({'relatorio': texto})
        self.assertEqual(len(out['erros']), m.MAX_ERROS + 1, out['erros'][-1])
        self.assertEqual(out['erros'][-1], f'mais {300 - m.MAX_ERROS} erros: corrija estes e confira de novo')
        # Muitos hashes inteiros com o mesmo começo e abreviações diferentes: o teto de comparações para a conferência.
        inteiros = ['abc123' + hashlib.sha256(str(i).encode()).hexdigest()[6:] for i in range(3000)]
        abreviados = [f'`{x[:10]}…{x[-5:]}`' for x in reversed(inteiros)]
        out = m.validar({'relatorio': relatorio() + '\n' + '\n'.join(inteiros + abreviados) + '\n'})
        self.assertIn('hashes abreviados demais para conferir: cite os hashes inteiros', out['erros'])

    def test_command_section_is_method_not_scope_claim(self):
        m = self.module()
        comandos = '## Comandos executados\n| C2 | grep -rn x core/ | não | não | core/a.py:3: # só o titular grava |\n'
        self.assertTrue(m.validar({'relatorio': comandos + relatorio()})['preenchimento_ok'])
        self.assertFalse(m.validar({'relatorio': comandos.replace('## Comandos executados', '## Outros') + relatorio()})['preenchimento_ok'])

    def test_template_text_and_labels_do_not_satisfy_or_hide(self):
        m = self.module()
        for velho, novo in [('- Local: core/exemplo.py:10', '- Local: arquivo:linha e revisão (ou camada não commitada)'),
                            ('- Evidência: grep -n x core/exemplo.py mostrou "10: x"',
                             '- Evidência: IDs do quadro de afirmações, comando e trecho literal redigido, e caminho'),
                            ('- Local: core/exemplo.py:10', '- Local: fundacao/v2/x.py')]:
            with self.subTest(novo=novo):
                self.assertFalse(m.validar({'relatorio': relatorio().replace(velho, novo)})['preenchimento_ok'])
        for impacto in ['- Impacto (demonstrado | condicional, com os pré-requisitos que faltam): demonstrado; qualquer conta lê todos os casos',
                        '- Impacto: incondicional: qualquer conta lê todos os casos',
                        '- Cenário de falha concreto (condicional se depender de pré-requisito): nenhum teste cobre isso']:
            with self.subTest(impacto=impacto):
                out = m.validar({'relatorio': relatorio().replace('- Impacto: condicional', '- Impacto: condicional\n' + impacto)})
                self.assertTrue(any('cobertura' in e for e in out['erros']), out['erros'])

    def test_more_scope_words_and_their_coverage(self):
        m = self.module()
        for frase in ['todo arquivo .py usa eval', 'nada grava fora de state/', 'ninguém além do titular aprova',
                      'jamais usa rede', 'não existe uso de rede']:
            with self.subTest(frase=frase):
                texto = relatorio().replace('- Impacto: condicional', '- Impacto: ' + frase)
                self.assertFalse(m.validar({'relatorio': texto})['preenchimento_ok'])
        for frase in ['li apenas core/x.py:1-40', 'não é seguro presumir o alcance', 'lidos somente os três JSON',
                      'Esta revisão não estabelece que a versão é segura']:
            with self.subTest(frase=frase):
                texto = relatorio().replace('- Impacto: condicional', '- Impacto: condicional\n- Nota: ' + frase)
                self.assertTrue(m.validar({'relatorio': texto})['preenchimento_ok'], frase)

    def test_sections_outside_template_and_title_are_checked(self):
        m = self.module()
        for extra in ['## Conclusão\nA versão está segura.\n', '## Resumo\nnenhum uso de rede\n']:
            with self.subTest(extra=extra):
                out = m.validar({'relatorio': extra + relatorio()})
                self.assertTrue(any('cobertura' in e for e in out['erros']), out['erros'])
        titulo = '# Revisão: nenhuma falha, a versão está segura\n> Relatório PRIVADO, somente leitura.\n'
        self.assertFalse(m.validar({'relatorio': titulo + relatorio()})['preenchimento_ok'])
        citado = '# Revisão de segurança da fundação\n> Nada na fundação foi alterado (citação do aviso).\n'
        self.assertTrue(m.validar({'relatorio': citado + relatorio()})['preenchimento_ok'])

    def test_method_statements_in_scope_and_coverage_are_not_scope_claims(self):
        m = self.module()
        metodo = ('## Escopo\n- Camadas incluídas: commits; arquivos não rastreados: nenhum\n'
                  '- Exclusões: só metadados de projects/, por regra do pedido\n'
                  '## Cobertura e evidência\n- Comandos e testes rodados: nenhum; revisão só leitura\n'
                  '- Caminhos revisados: listei só os nomes de core/\n'
                  '| sed -n 1,40p core/x.py | sed | linhas 1-40 | não | só as linhas 1-40 de core/x.py |\n')
        out = m.validar({'relatorio': metodo + relatorio()})
        self.assertTrue(out['preenchimento_ok'], out['erros'])

    def test_reading_restriction_exempts_only_itself(self):
        m = self.module()
        for frase in ['o token é lido por qualquer conta local', 'li todos os arquivos de core/ e nenhum usa rede',
                      'os arquivos lidos mostram que nenhum projeto é exposto', 'li apenas core/x.py e nenhum arquivo usa rede']:
            with self.subTest(frase=frase):
                texto = relatorio().replace('- Impacto: condicional', '- Impacto: ' + frase)
                self.assertFalse(m.validar({'relatorio': texto})['preenchimento_ok'])
        texto = relatorio().replace('- Impacto: condicional', '- Impacto: condicional\n- Nota: li apenas core/x.py:1-40')
        self.assertTrue(m.validar({'relatorio': texto})['preenchimento_ok'])

    def test_operating_system_is_not_only_and_pending_titles_vary(self):
        m = self.module()
        so = relatorio().replace('- Impacto: condicional', '- Impacto: depende de outra conta do SO')
        self.assertTrue(m.validar({'relatorio': so})['preenchimento_ok'])
        leitura = relatorio().replace('- Impacto: condicional', '- Impacto: condicional\n- Nota: revisão só leitura')
        self.assertTrue(m.validar({'relatorio': leitura})['preenchimento_ok'])
        conferido = relatorio().replace('- Impacto: condicional', '- Impacto: nenhum teste roda isso, não conferido')
        self.assertTrue(m.validar({'relatorio': conferido})['preenchimento_ok'])
        for titulo in ['## Pendências', '## Pendências e limites', '## Pendencias']:
            with self.subTest(titulo=titulo):
                texto = relatorio().replace('## Pendências\n', titulo + '\n- nada medido; todos os testes sem rodar\n')
                self.assertTrue(m.validar({'relatorio': texto})['preenchimento_ok'])

    def test_both_spellings_count_except_unaccented_so(self):
        m = self.module()
        for frase in ['nao ha uso de rede', 'a fundacao esta segura', 'ninguem alem do titular aprova',
                      'nao existe uso de rede', 'os unicos arquivos gravaveis']:
            with self.subTest(frase=frase):
                texto = relatorio().replace('- Impacto: condicional', '- Impacto: ' + frase)
                self.assertFalse(m.validar({'relatorio': texto})['preenchimento_ok'])
        for frase in ['nenhum arquivo usa rede (nao medido)', 'qualquer conta local, nao conferido',
                      'nenhum uso de rede, nao localizado em core/']:
            with self.subTest(frase=frase):
                texto = relatorio().replace('- Impacto: condicional', '- Impacto: ' + frase)
                self.assertTrue(m.validar({'relatorio': texto})['preenchimento_ok'])

    def test_conjunction_negation_and_mandatory_phrases_in_both_spellings(self):
        m = self.module()
        for frase in ['a gravação usa os.replace e é atômica e segura contra queda', 'o caminho é curto e seguro',
                      'nao é seguro presumir o alcance', 'não e seguro presumir o alcance',
                      'Nenhuma correcao foi aplicada pela revisão', 'Nao estabelece que a versao é segura']:
            with self.subTest(frase=frase):
                texto = relatorio().replace('- Impacto: condicional', '- Impacto: condicional\n- Nota: ' + frase)
                self.assertTrue(m.validar({'relatorio': texto})['preenchimento_ok'], m.validar({'relatorio': texto})['erros'])
        self.assertFalse(m.validar({'relatorio': relatorio().replace('- Impacto: condicional', '- Impacto: a fundação é segura')})['preenchimento_ok'])

    def test_section_titles_pass_through_the_scope_rule(self):
        m = self.module()
        for titulo in ['## Conclusão: a versão está segura', '## Pendências: nenhuma falha restante']:
            with self.subTest(titulo=titulo):
                out = m.validar({'relatorio': relatorio() + '\n' + titulo + '\ntexto neutro\n'})
                self.assertTrue(any('título' in e for e in out['erros']), out['erros'])
        for titulo in ['## Observações (só leitura)', '## Escopo: todo o repositório', '## Nenhum achado comprovado no escopo']:
            with self.subTest(titulo=titulo):
                out = m.validar({'relatorio': relatorio() + '\n' + titulo + '\ntexto neutro\n'})
                self.assertFalse(any('título' in e for e in out['erros']), out['erros'])
        doc = TEMPLATE.read_text(encoding='utf-8')
        titulos = [l for l in doc.splitlines() if l.startswith('## ')]
        self.assertGreaterEqual(len(titulos), 7)
        out = m.validar({'relatorio': '\n'.join(titulos) + '\n' + relatorio()})
        self.assertFalse(any('título' in e for e in out['erros']), out['erros'])

    def test_title_scope_description_is_not_a_claim(self):
        m = self.module()
        for titulo in ['# Revisão de segurança de toda a fundação — 1.7.9', '# Revisão — todo o repositório — 1.7.8..1.7.9']:
            with self.subTest(titulo=titulo):
                self.assertTrue(m.validar({'relatorio': titulo + '\n' + relatorio()})['preenchimento_ok'])
        self.assertFalse(m.validar({'relatorio': '# Revisão: toda a fundação está segura\n' + relatorio()})['preenchimento_ok'])

    def test_field_lines_are_parsed_in_linear_time(self):
        m = self.module()
        import time
        inicio = time.monotonic()
        m.validar({'relatorio': relatorio() + '## Resumo\n- ' + ' ' * 200000 + 'x\n'})
        m.validar({'relatorio': relatorio().replace('- Impacto: condicional', '- Impacto: condicional\n- ' + ' ' * 200000 + 'x')})
        self.assertLess(time.monotonic() - inicio, 2.0)

    def test_pending_items_say_what_was_not_verified(self):
        """Pendência com "só", "somente", "apenas" ou "único" descreve o que foi feito: recusada mesmo com cobertura e
        com "li apenas". Frases fixas, o que não foi verificado, o endurecimento sugerido e a hipótese rotulada, com
        as linhas recuadas que os continuam, continuam aceitos."""
        m = self.module()
        for frase in ['- só a pasta docs/ foi percorrida', '- os demais arquivos passaram somente pela busca B2',
                      '- li apenas core/x.py', '- o único arquivo fora do manifesto é x (não medido)',
                      '- Não verificado: apenas o banco ficou de fora',
                      '- Não verificado, com o motivo:\n  - só a pasta docs/ foi percorrida',
                      '- Endurecimento sugerido: rever x\nsó a pasta docs/ foi percorrida']:
            with self.subTest(frase=frase):
                out = m.validar({'relatorio': relatorio().replace('## Pendências\n', '## Pendências\n' + frase + '\n')})
                self.assertFalse(out['preenchimento_ok'])
                self.assertTrue(any('pendência descreve o que foi feito' in e for e in out['erros']), out['erros'])
        for frase in ['- conteúdo de state/ não verificado (regra de escopo)', '- auditoria somente leitura',
                      '- Nenhuma correção foi aplicada.', '- Esta auditoria não estabelece que a fundação é segura.',
                      '- nada medido sobre rede; todos os testes ficaram sem rodar',
                      '- Endurecimento sugerido (separado dos achados): aceitar apenas caminhos da raiz',
                      '- Endurecimento sugerido:\n  - aceitar apenas caminhos da raiz',
                      '- Hipóteses não comprovadas e a evidência que falta: só o titular grava x (não comprovado)']:
            with self.subTest(frase=frase):
                out = m.validar({'relatorio': relatorio().replace('## Pendências\n', '## Pendências\n' + frase + '\n')})
                self.assertTrue(out['preenchimento_ok'], out['erros'])

    def test_rules_conference_preamble_and_pending_quantifiers_pass(self):
        m = self.module()
        doc = TEMPLATE.read_text(encoding='utf-8')
        regras = doc[doc.index('## Regras de escrita'):doc.index('## Escopo')]
        texto = ('# Revisão\n> Nada foi alterado e somente leitura.\n' + regras + relatorio()
                 + '\n## Pendências e limites\n- nada medido sobre rede; todos os testes ficaram sem rodar\n')
        self.assertTrue(m.validar({'relatorio': texto})['preenchimento_ok'], m.validar({'relatorio': texto})['erros'])

    def test_linear_title_and_bounded_errors(self):
        m = self.module()
        import time
        inicio = time.monotonic()
        m.validar({'relatorio': '## x' + ' ' * 200000 + 'y\n' + relatorio()})
        self.assertLess(time.monotonic() - inicio, 2.0)
        out = m.validar({'relatorio': relatorio().replace('- Impacto: condicional', '- Impacto: condicional' + '\nsó x' * 300)})
        self.assertLessEqual(len(out['erros']), m.MAX_ERROS + 1)
        self.assertIn('mais', out['erros'][-1])


if __name__ == '__main__': unittest.main()
