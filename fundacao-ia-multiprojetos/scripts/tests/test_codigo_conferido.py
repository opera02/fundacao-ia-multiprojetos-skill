"""Metadados de codigo n?o enumeram dados nem seguem ligacoes para procurar pacotes."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import SCRIPTS, criar_ligacao_dir


def carregar():
    spec = importlib.util.spec_from_file_location("_codigo_conferido_revisao", SCRIPTS / "codigo_conferido.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PrimeiroNivelSemDados(unittest.TestCase):
    def test_dados_nao_sao_listados_e_codigo_continua_conferido(self):
        cc = carregar()
        with tempfile.TemporaryDirectory(prefix="codigo-ficticio-") as tmp:
            root = Path(tmp)
            for nome in ("projects", "state", "registry", "evidence", "secrets"):
                (root / nome / "conteudo-protegido").mkdir(parents=True)
            (root / "avulso.py").write_text("# ficticio", encoding="utf-8")
            (root / "pacote").mkdir()
            (root / "pacote/__init__.py").write_text("# ficticio", encoding="utf-8")
            real, proibidos = os.listdir, []

            def listar(pasta):
                if Path(pasta).name in ("projects", "state", "registry", "evidence", "secrets"):
                    proibidos.append(str(pasta))
                return real(pasta)

            with mock.patch.object(os, "listdir", listar):
                arquivos, _ = cc.primeiro_nivel(root)
            self.assertEqual(proibidos, [], "dados foram enumerados antes da recusa")
            self.assertEqual(set(arquivos), {"avulso.py", "pacote/__init__.py"})

    def test_arquivo_protegido_regular_nao_importavel_e_ignorado_sem_leitura(self):
        cc = carregar()
        with tempfile.TemporaryDirectory(prefix="codigo-ficticio-") as tmp:
            root = Path(tmp)
            dados = {root / nome for nome in (".env", "auth.json", "secret.txt")}
            for arquivo in dados:
                arquivo.write_text("CONTEUDO-FICTICIO-NAO-LER", encoding="utf-8")
            abrir_original, listar_original = Path.open, os.listdir
            acessos = []

            def abrir(caminho, *args, **kwargs):
                if Path(caminho) in dados:
                    acessos.append(str(caminho))
                return abrir_original(caminho, *args, **kwargs)

            def listar(caminho):
                if Path(caminho) in dados:
                    acessos.append(str(caminho))
                return listar_original(caminho)

            with mock.patch.object(Path, "open", abrir), mock.patch.object(os, "listdir", listar):
                resultado = cc.inventario(root, {}, {})
            self.assertEqual(acessos, [], "arquivo de dados foi aberto ou enumerado")
            self.assertEqual(resultado, {"conferidos": {}, "a_mais": [], "alterados": [], "ligacoes": []})

    def test_modulo_com_nome_protegido_recusa_sem_ler_ou_enumerar(self):
        cc = carregar()
        with tempfile.TemporaryDirectory(prefix="codigo-ficticio-") as tmp:
            root = Path(tmp)
            modulo, pacote = root / "secrets.py", root / "secrets"
            modulo.write_text("CONTEUDO-FICTICIO-NAO-EXECUTAR", encoding="utf-8")
            pacote.mkdir()
            (pacote / "__init__.py").write_text("CONTEUDO-FICTICIO-NAO-EXECUTAR", encoding="utf-8")
            abrir_original, listar_original = Path.open, os.listdir
            acessos = []

            def abrir(caminho, *args, **kwargs):
                if Path(caminho) == modulo or Path(caminho).is_relative_to(pacote):
                    acessos.append(str(caminho))
                return abrir_original(caminho, *args, **kwargs)

            def listar(caminho):
                if Path(caminho) == pacote:
                    acessos.append(str(caminho))
                return listar_original(caminho)

            with mock.patch.object(Path, "open", abrir), mock.patch.object(os, "listdir", listar):
                resultado = cc.inventario(root, {}, {})
            self.assertEqual(acessos, [], "nome protegido foi lido ou enumerado")
            self.assertTrue(resultado["ligacoes"], "modulo protegido ficou invisivel para a recusa")

    def test_ligacao_no_primeiro_nivel_nao_e_enumerada(self):
        cc = carregar()
        with tempfile.TemporaryDirectory(prefix="codigo-ficticio-") as tmp:
            root, fora = Path(tmp) / "root", Path(tmp) / "fora"
            root.mkdir(); fora.mkdir()
            (fora / "__init__.py").write_text("# ficticio", encoding="utf-8")
            alias = root / "pacote"
            criar_ligacao_dir(alias, fora)
            real, abertos = os.listdir, []

            def listar(pasta):
                if Path(pasta) == alias:
                    abertos.append(str(pasta))
                return real(pasta)

            with mock.patch.object(os, "listdir", listar):
                _, ligacoes = cc.primeiro_nivel(root)
            self.assertEqual(abertos, [], "ligacao foi seguida antes da recusa")
            self.assertIn("pacote", ligacoes)


if __name__ == "__main__":
    unittest.main()
