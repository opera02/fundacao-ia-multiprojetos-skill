"""Auditoria técnica sobre a 1.4.1 (A12–A16) — `manifesto.py`, `backup_sqlite.py` e `caracterizar.py`.

Cada teste exige o comportamento seguro; na 1.4.5 (base a8e74c4) eles falham por asserção, salvo os
marcados como compatibilidade. Dados fictícios em pastas descartáveis. Ligação de diretório: junção no
Windows (`mklink /J`, sem administrador); link simbólico de ARQUIVO no Windows exige privilégio — sem
ele, o teste é pulado e o achado fica conferido pela junção e pela leitura do código.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import SCRIPTS, criar_ligacao_dir, rodar_script

EXTERNO = "CONTEUDO-EXTERNO-FICTICIO-A12"


def carregar(nome: str):
    spec = importlib.util.spec_from_file_location(f"_auditoria_150_{nome}", SCRIPTS / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def chamar_main(modulo, *args) -> tuple[int, str]:
    saida = io.StringIO()
    with mock.patch.object(sys, "argv", [str(modulo.__file__), *map(str, args)]), contextlib.redirect_stdout(saida):
        codigo = modulo.main()
    return codigo, saida.getvalue()


class _Pastas(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="auditoria-150-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)  # não atravessa junção (3.8+)
        self.raiz = self.base / "projeto"
        self.raiz.mkdir()
        (self.raiz / "a.txt").write_text("conteúdo de dentro", encoding="utf-8")

    def criar_manifesto(self, saida: Path) -> dict:
        p = rodar_script("manifesto.py", "criar", "--raiz", self.raiz, "--saida", saida)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(saida.read_text(encoding="utf-8"))

    def verificar_manifesto(self, manifesto: Path) -> tuple[int, str]:
        p = rodar_script("manifesto.py", "verificar", "--raiz", self.raiz, "--manifesto", manifesto)
        return p.returncode, p.stdout


class TestA12ManifestoNaoSegueLigacao(_Pastas):
    def setUp(self):
        super().setUp()
        self.fora = self.base / "fora"
        self.fora.mkdir()
        (self.fora / "externo.txt").write_text(EXTERNO, encoding="utf-8")
        self.man = self.base / "manifesto.json"

    def test_a12_juncao_para_fora_da_raiz_nao_e_lida_nem_listada(self):
        tipo = criar_ligacao_dir(self.raiz / "atalho", self.fora)
        m = self.criar_manifesto(self.man)
        self.assertEqual([f["path"] for f in m["arquivos"]], ["a.txt"], f"{tipo}: o manifesto leu fora da raiz")
        texto = json.dumps(m, ensure_ascii=False)
        self.assertNotIn("externo.txt", texto, "o manifesto listou o conteúdo da pasta ligada")
        self.assertNotIn(hashlib.sha256(EXTERNO.encode()).hexdigest(), texto)
        self.assertEqual([e["path"] for e in m["excluidos"]], ["atalho"])
        self.assertIn("ligação", m["excluidos"][0]["motivo"])

    def test_a12_link_de_arquivo_para_fora_da_raiz_nao_e_lido(self):
        try:
            (self.raiz / "inocente.txt").symlink_to(self.fora / "externo.txt")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"link simbólico de arquivo indisponível neste ambiente: {exc}")
        m = self.criar_manifesto(self.man)
        self.assertEqual([f["path"] for f in m["arquivos"]], ["a.txt"])
        self.assertEqual([e["path"] for e in m["excluidos"]], ["inocente.txt"])

    def test_a12_verificacao_nao_le_pela_juncao_criada_depois(self):
        self.criar_manifesto(self.man)
        criar_ligacao_dir(self.raiz / "atalho", self.fora)
        codigo, saida = self.verificar_manifesto(self.man)
        self.assertNotIn("externo.txt", saida, "a verificação atravessou a junção")
        self.assertEqual(codigo, 0, saida)


class TestA13ManifestoDentroDaRaiz(_Pastas):
    def test_a13_saida_dentro_da_raiz_nao_entra_no_proprio_conjunto(self):
        man = self.raiz / "evidencias" / "manifesto.json"
        m = self.criar_manifesto(man)
        self.assertEqual([f["path"] for f in m["arquivos"]], ["a.txt"])
        self.assertEqual(m["politica"]["exclusoes_literais"], ["evidencias/manifesto.json"])
        codigo, saida = self.verificar_manifesto(man)
        self.assertEqual(codigo, 0, saida)
        # Recriar no mesmo caminho não inclui o manifesto anterior.
        self.assertEqual([f["path"] for f in self.criar_manifesto(man)["arquivos"]], ["a.txt"])

    def test_a13_nome_com_colchetes_e_excluido_literalmente(self):
        (self.raiz / "manifest1.json").write_text("{}", encoding="utf-8")
        man = self.raiz / "manifest[1].json"  # como padrão glob, casaria com manifest1.json
        m = self.criar_manifesto(man)
        self.assertEqual([f["path"] for f in m["arquivos"]], ["a.txt", "manifest1.json"])
        codigo, saida = self.verificar_manifesto(man)
        self.assertEqual(codigo, 0, saida)
        (self.raiz / "manifest1.json").write_text('{"mudou": 1}', encoding="utf-8")
        codigo, saida = self.verificar_manifesto(man)
        self.assertEqual(codigo, 1, saida)
        self.assertEqual(json.loads(saida)["alterados"], ["manifest1.json"])

    def test_a13_compatibilidade_saida_fora_da_raiz_mantem_a_politica_anterior(self):
        """Compatibilidade (passa antes e depois): sem saída dentro da raiz, a política não ganha campo,
        e o `comparar` com manifestos anteriores não acusa política diferente."""
        m = self.criar_manifesto(self.base / "manifesto.json")
        self.assertNotIn("exclusoes_literais", m["politica"])


class TestA14BackupSqliteMesmoSnapshot(_Pastas):
    def test_a14_escritor_concorrente_depois_da_copia_nao_invalida_o_snapshot(self):
        mod = carregar("backup_sqlite")
        origem, destino = self.base / "origem.sqlite", self.base / "ref" / "copia.sqlite"
        con = sqlite3.connect(origem)
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("CREATE TABLE itens (v TEXT)")
        con.execute("INSERT INTO itens VALUES ('antes')")
        con.commit()
        con.close()
        conectar = sqlite3.connect
        escritas = []

        class OrigemComEscritorDepoisDaCopia(sqlite3.Connection):
            def backup(self, alvo, **kw):
                super().backup(alvo, **kw)
                escritor = conectar(origem)  # segunda conexão; em WAL grava com a leitura aberta
                try:
                    escritor.execute("INSERT INTO itens VALUES ('depois')")
                    escritor.commit()
                    escritas.append("depois")
                finally:
                    escritor.close()

        def conectar_instrumentado(caminho, *a, **kw):
            if str(caminho).startswith("file:") and "origem.sqlite?mode=ro" in str(caminho):
                kw["factory"] = OrigemComEscritorDepoisDaCopia
            return conectar(caminho, *a, **kw)

        with mock.patch.object(mod.sqlite3, "connect", side_effect=conectar_instrumentado):
            codigo, saida = chamar_main(mod, "--origem", origem, "--destino", destino)
        self.assertEqual(escritas, ["depois"], "o escritor concorrente não gravou")
        self.assertEqual(codigo, 0, saida)
        dados = json.loads(saida)
        self.assertTrue(dados["ok"])
        self.assertEqual((dados["origem"]["tabelas"], dados["copia"]["tabelas"]), ({"itens": 1}, {"itens": 1}))
        with contextlib.closing(conectar(origem)) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM itens").fetchone()[0], 2)
        with contextlib.closing(conectar(destino)) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM itens").fetchone()[0], 1)


class TestA15ContagemDeTabelas(_Pastas):
    def banco(self, *comandos: str) -> Path:
        caminho = self.base / "banco.sqlite"
        con = sqlite3.connect(caminho)
        for comando in comandos:
            con.execute(comando)
        con.commit()
        con.close()
        return caminho

    def test_a15_nome_com_aspas_e_contado_como_inteiro(self):
        mod = carregar("backup_sqlite")
        db = self.banco('CREATE TABLE "a""b" (v)', 'INSERT INTO "a""b" VALUES (1)')
        self.assertEqual(mod.summary(db)["tabelas"], {'a"b': 1})
        codigo, saida = chamar_main(mod, "--origem", db, "--destino", self.base / "copia.sqlite")
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(json.loads(saida)["copia"]["tabelas"], {'a"b': 1})

    def test_a15_tabela_com_nome_sqlite_sem_sublinhado_e_contada(self):
        """No LIKE, `_` é curinga: o filtro das tabelas internas deixava `sqlite1` sem contagem."""
        mod = carregar("backup_sqlite")
        db = self.banco("CREATE TABLE sqlite1 (v)", "INSERT INTO sqlite1 VALUES (1)")
        self.assertEqual(mod.summary(db)["tabelas"], {"sqlite1": 1})

    def test_a15_tabela_virtual_sem_modulo_fica_declarada_a_parte(self):
        """O módulo da tabela virtual (ex.: vec0) pode não existir neste Python: ela não é contada, fica
        em `tabelas_nao_contadas` (nunca como texto no lugar da contagem) e a cópia segue."""
        mod = carregar("backup_sqlite")
        db = self.banco("CREATE TABLE t (v)", "INSERT INTO t VALUES (1)", "PRAGMA writable_schema = ON",
                        "INSERT INTO sqlite_master (type, name, tbl_name, rootpage, sql) VALUES "
                        "('table', 'vt', 'vt', 0, 'CREATE VIRTUAL TABLE vt USING modulo_ficticio(a)')")
        codigo, saida = chamar_main(mod, "--origem", db, "--destino", self.base / "copia.sqlite")
        self.assertEqual(codigo, 0, saida)
        dados = json.loads(saida)
        for lado in ("origem", "copia"):
            self.assertEqual(dados[lado]["tabelas"], {"t": 1}, f"{lado}: erro de contagem virou dado")
            self.assertIn("modulo_ficticio", dados[lado]["tabelas_nao_contadas"]["vt"])

    def test_a15_outro_erro_de_contagem_interrompe(self):
        mod = carregar("backup_sqlite")
        db = self.banco("CREATE TABLE t (v)")
        conectar = sqlite3.connect

        class FalhaNaContagem:
            def __init__(self, con):
                self._con = con

            def execute(self, sql, *a):
                if sql.startswith("SELECT COUNT(*) FROM") and "sqlite_master" not in sql:
                    raise sqlite3.OperationalError("falha fictícia de leitura")
                return self._con.execute(sql, *a)

            def close(self):
                self._con.close()

        with mock.patch.object(mod.sqlite3, "connect", side_effect=lambda *a, **k: FalhaNaContagem(conectar(*a, **k))):
            with self.assertRaises(sqlite3.OperationalError):
                mod.summary(db)


class TestA16TimeoutGuardaSaidaParcial(unittest.TestCase):
    PROGRAMA = ("import sys, time; print('{m}', flush=True); print('erro-{m}', file=sys.stderr, flush=True); "
                "time.sleep(60)")

    def test_a16_saidas_parciais_diferentes_nao_comparam_iguais(self):
        mod = carregar("caracterizar")
        casos = [mod.run_case([sys.executable, "-I", "-c", self.PROGRAMA.format(m=m)], "", None, None, [], 3)
                 for m in ("ANTIGO", "NOVO")]
        self.assertEqual([c["codigo"] for c in casos], ["timeout", "timeout"])
        self.assertIn("ANTIGO", casos[0]["stdout"], "a saída parcial foi descartada no timeout")
        self.assertIn("erro-NOVO", casos[1]["stderr"])
        self.assertIn("stdout", mod.comparar_caso(casos[0], casos[1]))

    def test_a16_compatibilidade_golden_anterior_com_timeout_nao_acusa_diferenca_falsa(self):
        """Golden gravado antes da correção guardou stdout vazio e stderr TIMEOUT: nos casos com timeout,
        a comparação fica em código e efeitos, com aviso para gravar de novo."""
        base = Path(tempfile.mkdtemp(prefix="auditoria-150-golden-"))
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        entrada = base / "um.json"
        entrada.write_text("{}", encoding="utf-8")

        def sha(texto: str) -> str:
            return hashlib.sha256(texto.encode("utf-8")).hexdigest()

        caso = {"entrada": str(entrada), "codigo": "timeout", "stdout_sha256": sha(""), "stdout_tamanho": 0,
                "stdout": "", "stderr_sha256": sha("TIMEOUT"), "stderr_tamanho": 7, "stderr": "TIMEOUT",
                "efeitos": {"escritos": {}, "removidos": []}, "preexistentes": 0, "arquivos": {}}
        golden = base / "golden.json"
        golden.write_text(json.dumps({"schema_version": "fundacao.golden/2", "comando": [], "ignorar": [],
                                      "casos": [caso]}), encoding="utf-8")
        p = rodar_script("caracterizar.py", "comparar", "--golden", golden, "--timeout", "3", "--",
                         sys.executable, "-I", "-c", self.PROGRAMA.format(m="QUALQUER"))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("timeout", json.loads(p.stdout)["aviso"])


if __name__ == "__main__":
    unittest.main()
