"""Fronteira de arquivos do coletor: somente dados fictícios locais."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

EVALS = Path(__file__).resolve().parents[2] / 'fundacao-ia-multiprojetos/evals'

def modulo(nome):
    spec = importlib.util.spec_from_file_location('r179_' + nome, EVALS / (nome + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

class Fronteira(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='r179-leitura-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.amb = self.root / 'amb'; self.amb.mkdir()
        self.ve = modulo('verificar_execucoes')

    def db(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path)
        try:
            con.execute('CREATE TABLE event(kind TEXT)')
            con.execute("INSERT INTO event VALUES('restore_completed')")
            con.commit()
        finally: con.close()
        return path

    def test_db_hardlink_recusado_antes_de_sqlite(self):
        external = self.db(self.root / 'externo.sqlite')
        target = self.amb / 'state/state.sqlite'; target.parent.mkdir()
        os.link(external, target)
        with patch.object(self.ve.banco_avaliado.sqlite3, 'connect', side_effect=AssertionError('conexao externa')):
            result = self.ve.banco(self.amb)
        self.assertIn('erro_banco', result)
        self.assertNotIn('cadeia_eventos', result)

    def test_auxiliares_hardlink_recusados_antes_de_sqlite(self):
        target = self.db(self.amb / 'state/state.sqlite')
        external = self.root / 'externo'; external.write_bytes(b'NAO_LER')
        for suffix in ('-wal', '-shm', '-journal'):
            sidecar = Path(str(target) + suffix); os.link(external, sidecar)
            try:
                with patch.object(self.ve.banco_avaliado.sqlite3, 'connect', side_effect=AssertionError('conexao externa')):
                    result = self.ve.banco(self.amb)
                self.assertIn('erro_banco', result)
            finally: sidecar.unlink()

    def test_ancestral_symlink_recusado(self):
        external = self.root / 'externo'; self.db(external / 'state.sqlite')
        try: (self.amb / 'state').symlink_to(external, target_is_directory=True)
        except OSError as exc: self.skipTest(str(exc))
        with patch.object(self.ve.banco_avaliado.sqlite3, 'connect', side_effect=AssertionError('conexao externa')):
            self.assertIn('erro_banco', self.ve.banco(self.amb))

    def test_manifesto_e_files_hardlinks_nao_conferem(self):
        backup = self.amb / 'backup'; (backup / 'files').mkdir(parents=True)
        external = self.root / 'manifesto'; external.write_text('{"files":[]}')
        os.link(external, backup / 'manifest.json')
        self.assertFalse(self.ve._copia_confere(backup))
        (backup / 'manifest.json').unlink()
        import hashlib
        payload = self.root / 'payload'; payload.write_bytes(b'privado')
        os.link(payload, backup / 'files/a')
        (backup / 'manifest.json').write_text(json.dumps({'files':[{'path':'a','sha256':hashlib.sha256(b'privado').hexdigest()}]}))
        self.assertFalse(self.ve._copia_confere(backup))

    def test_files_symlink_nao_confere(self):
        backup = self.amb / 'backup'; backup.mkdir()
        external = self.root / 'files'; external.mkdir(); (external / 'a').write_bytes(b'privado')
        try: (backup / 'files').symlink_to(external, target_is_directory=True)
        except OSError as exc: self.skipTest(str(exc))
        import hashlib
        (backup / 'manifest.json').write_text(json.dumps({'files':[{'path':'a','sha256':hashlib.sha256(b'privado').hexdigest()}]}))
        self.assertFalse(self.ve._copia_confere(backup))

    def test_wal_legitimo_lido_apenas_na_copia(self):
        target = self.amb / 'state.sqlite'
        original = sqlite3.connect(target)
        self.addCleanup(original.close)
        original.execute('PRAGMA journal_mode=WAL'); original.execute('PRAGMA wal_autocheckpoint=0')
        original.execute('CREATE TABLE exemplo(v TEXT)'); original.commit()
        original.execute("INSERT INTO exemplo VALUES('confirmado-no-wal')"); original.commit()
        before = {p.name:p.read_bytes() for p in self.amb.iterdir()}
        real_connect = sqlite3.connect
        def connect(database, **kwargs):
            self.assertNotIn(str(target).replace('\\','/'), database)
            return real_connect(database, **kwargs)
        with patch.object(self.ve.banco_avaliado.sqlite3, 'connect', side_effect=connect):
            with self.ve.banco_avaliado.aberto(target, raiz=self.amb) as con:
                self.assertEqual(con.execute('SELECT v FROM exemplo').fetchall(), [('confirmado-no-wal',)])
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.amb.iterdir()})

    def test_snapshot_recusa_integralmente_sem_leitor_confiavel(self):
        out = self.root / 'out'; out.mkdir()
        outside = self.root / 'fora'; outside.write_bytes(b'PRIVADO')
        os.link(outside, out / 'RELATO.md')
        with patch.object(self.ve, 'run', side_effect=AssertionError('leitor iniciado antes da guarda')):
            result = self.ve.fatos_run(3,'candidato',self.root/'run',self.root/'refs',self.amb,out)
        self.assertIn('ambiente_nao_lido', result)
        self.assertNotIn('origem_inalterada', result)
        self.assertNotIn('vazamentos_saidas', result)

    def test_snapshot_limitado_e_recusa_caminho_ascendente(self):
        la = modulo('leitura_avaliada')
        (self.amb / 'a').write_bytes(b'12345')
        with self.assertRaises(ValueError): la.ler(self.amb, self.amb/'../fora')
        with self.assertRaises(ValueError): la.ler(self.amb, self.amb/'a', limite=4)

    def test_contador_global_inclui_pastas_ainda_na_pilha(self):
        la = modulo('leitura_avaliada')
        for name in ('a','b','c'): (self.amb/name).mkdir()
        for name in ('x','y'): (self.amb/'c'/name).write_bytes(b'1')
        real_iterdir = Path.iterdir
        def ordered(path): return iter(sorted(real_iterdir(path),key=lambda p:p.name))
        with patch.object(la,'MAX_ENTRADAS',4), patch.object(Path,'iterdir',ordered):
            with self.assertRaises(ValueError): la.capturar(self.amb)

    def test_coleta_main_nao_copia_hardlink_antes_de_fatos_run(self):
        it = self.root/'bancada/iteration-1'; run = it/'eval-3-exemplo/candidato/run-1'
        run.mkdir(parents=True)
        out = self.root/'saidas'; out.mkdir()
        outside = self.root/'externo'; outside.write_text('NAO_LER')
        os.link(outside,out/'resposta.md')
        (it/'prompts.json').write_text(json.dumps({'3/candidato/run-1':{'id':'ficticio','ambiente':str(self.amb),'outputs':str(out)}}))
        with patch.object(sys,'argv',['verificar','--iteracao',str(it)]), \
             patch.object(self.ve.iso,'copiar_arquivos',side_effect=AssertionError('copia externa')), \
             patch.object(self.ve,'fatos_run',side_effect=AssertionError('leitura depois da recusa')), \
             patch.object(self.ve,'acesso_ao_gabarito',return_value={'estado':'nao_medido'}):
            self.assertEqual(self.ve.main(),0)
        facts = json.loads((it/'_referencias/fatos.json').read_text())
        self.assertIn('ambiente_nao_lido',facts['eval-3-exemplo/candidato/run-1'])

    def test_snapshot_preserva_raiz_do_rastro_e_remapeia_apenas_caminhos(self):
        out = self.root/'out'; out.mkdir()
        literal = []
        def coletar(eid,cfg,run,refs,a,o,*,raiz_rastro):
            self.assertEqual(raiz_rastro,self.amb)
            literal.append(str(a/'NAO_REESCREVER'))
            return {'retomadas':[{'arquivo':(a/'RETOMADA.md').as_posix()},{'arquivo':str(o/'RETOMADA.md')}],
                    'texto_literal':literal[-1]}
        with patch.object(self.ve,'_fatos_run',side_effect=coletar):
            result=self.ve.fatos_run(7,'candidato',self.root/'run',self.root/'refs',self.amb,out)
        self.assertEqual([r['arquivo'] for r in result['retomadas']],[(self.amb/'RETOMADA.md').as_posix(),(out/'RETOMADA.md').as_posix()])
        self.assertEqual(result['texto_literal'],literal[0])

    def test_saida_parcial_preserva_irmao_sem_afirmar_ausencia_global(self):
        it=self.root/'bancada/iteration-1';run=it/'eval-3-exemplo/candidato/run-1';run.mkdir(parents=True)
        out=self.root/'saidas';out.mkdir();(out/'RELATO.md').write_text('entrega legitima')
        outside=self.root/'fora';outside.mkdir();(outside/'privado').write_text('NAO_LER')
        link=out/'RELATO-OMITIDO'
        try:
            if os.name=='nt':
                import _winapi
                _winapi.CreateJunction(str(outside),str(link))
            else: link.symlink_to(outside,target_is_directory=True)
        except (OSError,ImportError,AttributeError) as exc:self.skipTest(str(exc))
        try:
            (it/'prompts.json').write_text(json.dumps({'3/candidato/run-1':{'id':'ficticio','ambiente':str(self.amb),'outputs':str(out)}}))
            with patch.object(sys,'argv',['verificar','--iteracao',str(it)]), \
                 patch.object(self.ve,'fatos_run',return_value={'relato':True,'vazamentos_saidas':{}}), \
                 patch.object(self.ve,'acesso_ao_gabarito',return_value={'estado':'nao_medido'}):
                self.assertEqual(self.ve.main(),0)
            fact=json.loads((it/'_referencias/fatos.json').read_text())['eval-3-exemplo/candidato/run-1']
            self.assertTrue((run/'outputs/RELATO.md').is_file())
            self.assertFalse((run/'outputs/RELATO-OMITIDO').exists())
            self.assertEqual(fact['saidas_nao_recolhidas'],['RELATO-OMITIDO'])
            self.assertNotIn('vazamentos_saidas',fact)
            self.assertIn('parcial',fact['cobertura_saidas'])
            (out/'RELATO.md').unlink()
            omitted_name='relato.md' if os.name=='nt' else 'RELATO.md'
            if os.name=='nt':
                os.rmdir(link);_winapi.CreateJunction(str(outside),str(out/omitted_name))
            else:
                link.unlink();(out/omitted_name).symlink_to(outside,target_is_directory=True)
            link=out/omitted_name
            with patch.object(sys,'argv',['verificar','--iteracao',str(it)]), \
                 patch.object(self.ve,'fatos_run',return_value={'relato':False,'relato_bytes':0}), \
                 patch.object(self.ve,'acesso_ao_gabarito',return_value={'estado':'nao_medido'}):
                self.assertEqual(self.ve.main(),0)
            fact=json.loads((it/'_referencias/fatos.json').read_text())['eval-3-exemplo/candidato/run-1']
            self.assertEqual(fact['relato'],'nao_medido')
            self.assertEqual(fact['relato_bytes'],'nao_medido')
        finally:
            if os.name=='nt':os.rmdir(link)
            else:link.unlink()

if __name__ == '__main__': unittest.main()
