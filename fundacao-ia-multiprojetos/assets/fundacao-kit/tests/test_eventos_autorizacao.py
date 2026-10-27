"""A2: diagnóstico global exige audit/admin antes de ler eventos fictícios."""
from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

from tests.helpers import FoundationTestCase, sim
from fundacao import __main__ as cli
from fundacao.core import events
from fundacao.core.contracts import AccessDenied


class EventosAutorizacaoTests(FoundationTestCase):
    def setUp(self):
        super().setUp()
        for principal in ('sem-concessao', 'auditor-projeto', 'leitor-fundacao',
                          'auditor-fundacao', 'admin-fundacao'):
            self.policy.register_principal(self.admin, principal)
        for principal in ('auditor-projeto', 'leitor-fundacao', 'auditor-fundacao', 'admin-fundacao'):
            self.policy.grant(self.admin, principal, 'project:juridico-lab', 'read')
        for principal, resource, action in (
            ('auditor-projeto', 'project:juridico-lab', 'audit'),
            ('leitor-fundacao', 'foundation', 'read'),
            ('auditor-fundacao', 'foundation', 'audit'),
            ('admin-fundacao', 'foundation', 'admin'),
        ):
            self.policy.grant(self.admin, principal, resource, action)
        events.emit(self.con, 'ensaio_global', project_id='reversa-lab',
                    payload={'marcador': 'FICTICIO-OUTRO-PROJETO'})

    def tearDown(self):
        self.con.set_authorizer(None)
        super().tearDown()

    def call(self, principal, command, action=None, destination=None):
        args = SimpleNamespace(raiz=self.root, acao=action, destino=destination)
        # Só a borda de conexão/identidade é substituída; política, SQL e cadeia são reais.
        with patch.object(cli, '_con', return_value=self.con), \
             patch.object(cli, 'principal_from_env', return_value=sim(principal)):
            return command(args)

    def observe_reads(self):
        reads = []
        def authorizer(action, table, column, database, source):
            if action == sqlite3.SQLITE_READ and table == 'event':
                reads.append(column)
            return sqlite3.SQLITE_OK
        self.con.set_authorizer(authorizer)
        return reads

    def test_status_sem_auditoria_global_nao_verifica_nem_le_payload(self):
        for principal in ('sem-concessao', 'auditor-projeto', 'leitor-fundacao'):
            with self.subTest(principal=principal):
                reads = self.observe_reads()
                with patch.object(cli.events, 'verify_chain', wraps=events.verify_chain) as spy:
                    status = self.call(principal, cli.cmd_status)
                self.con.set_authorizer(None)
                self.assertEqual((spy.call_count, 'payload_json' in reads), (0, False))
                self.assertIsNone(status['eventos_cadeia_integra'])
                self.assertIsNone(status['primeiro_evento_quebrado'])
                self.assertEqual(status['eventos_diagnostico_global'], 'nao_medido_sem_permissao')
                self.assertEqual(status['projetos_autorizados'],
                                 [] if principal == 'sem-concessao' else ['juridico-lab'])
                self.assertEqual(status['tarefas_por_estado'], {})

    def test_eventos_negados_antes_verificacao_e_exportacao(self):
        for principal in ('sem-concessao', 'auditor-projeto', 'leitor-fundacao'):
            for action in ('verificar', 'exportar'):
                with self.subTest(principal=principal, acao=action):
                    reads = self.observe_reads()
                    denied = False
                    destination = self.root / 'negado.jsonl'
                    with patch.object(cli.events, 'verify_chain', wraps=events.verify_chain) as spy:
                        try:
                            self.call(principal, cli.cmd_eventos, action, destination)
                        except AccessDenied:
                            denied = True
                    self.con.set_authorizer(None)
                    self.assertEqual((spy.call_count, 'payload_json' in reads), (0, False))
                    self.assertTrue(denied, 'comando deve negar por política antes do diagnóstico')
                    # Registrar a negativa pode ler o último hash; isso não é ler o payload global.
                    self.assertIn('hash', reads)
                    row = self.con.execute('SELECT kind, subject, payload_json FROM event ORDER BY seq DESC LIMIT 1').fetchone()
                    self.assertEqual(row['kind'], 'access_denied')
                    self.assertEqual(row['subject'], principal)
                    self.assertEqual(json.loads(row['payload_json']), {
                        'action': 'audit', 'resource': 'foundation', 'source': 'teste-simulado'})
                    self.assertFalse(destination.exists())

    def test_autorizados_recebem_cadeia_integra_e_quebra_real(self):
        for principal in ('auditor-fundacao', 'admin-fundacao'):
            with self.subTest(principal=principal):
                reads = self.observe_reads()
                status = self.call(principal, cli.cmd_status)
                self.con.set_authorizer(None)
                self.assertIn('payload_json', reads)
                self.assertIs(status['eventos_cadeia_integra'], True)
                self.assertIsNone(status['primeiro_evento_quebrado'])
                self.assertEqual(self.call(principal, cli.cmd_eventos, 'verificar'), {
                    'cadeia_integra': True, 'primeiro_evento_quebrado': None})
        broken = self.con.execute("SELECT seq FROM event WHERE kind='ensaio_global'").fetchone()[0]
        self.con.execute('UPDATE event SET payload_json=? WHERE seq=?', ('{"adulterado":true}', broken))
        for principal in ('auditor-fundacao', 'admin-fundacao'):
            with self.subTest(principal=principal, quebrada=True):
                status = self.call(principal, cli.cmd_status)
                self.assertIs(status['eventos_cadeia_integra'], False)
                self.assertEqual(status['primeiro_evento_quebrado'], broken)
                self.assertEqual(self.call(principal, cli.cmd_eventos, 'verificar'), {
                    'cadeia_integra': False, 'primeiro_evento_quebrado': broken})

    def test_exportacao_autorizada_preservada(self):
        for principal in ('auditor-fundacao', 'admin-fundacao'):
            with self.subTest(principal=principal):
                events.emit(self.con, 'ensaio_exportacao', subject=principal)
                destination = self.root / (principal + '.jsonl')
                result = self.call(principal, cli.cmd_eventos, 'exportar', destination)
                records = [json.loads(line) for line in destination.read_text(encoding='utf-8').splitlines()]
                self.assertEqual(result['exportados'], len(records))
                self.assertGreater(len(records), 0)
                self.assertTrue(any(row['kind'] == 'ensaio_exportacao' for row in records))

    def test_revogacao_retira_diagnostico_imediatamente(self):
        for principal, action in (('auditor-fundacao', 'audit'), ('admin-fundacao', 'admin')):
            with self.subTest(principal=principal):
                self.assertIs(self.call(principal, cli.cmd_status)['eventos_cadeia_integra'], True)
                self.policy.revoke(self.admin, principal, 'foundation', action)
                reads = self.observe_reads()
                with patch.object(cli.events, 'verify_chain', wraps=events.verify_chain) as spy:
                    status = self.call(principal, cli.cmd_status)
                    with self.assertRaises(AccessDenied):
                        self.call(principal, cli.cmd_eventos, 'verificar')
                self.con.set_authorizer(None)
                spy.assert_not_called()
                self.assertNotIn('payload_json', reads)
                self.assertIsNone(status['eventos_cadeia_integra'])
                self.assertIsNone(status['primeiro_evento_quebrado'])
                self.assertEqual(status['eventos_diagnostico_global'], 'nao_medido_sem_permissao')
                self.assertEqual(status['projetos_autorizados'], ['juridico-lab'])
