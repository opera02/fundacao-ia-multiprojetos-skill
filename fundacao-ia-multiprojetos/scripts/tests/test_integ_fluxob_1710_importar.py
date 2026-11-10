"""Integração do fluxo B na 1.7.10 (pacote INTEG-FLUXOB do lote 2), itens 6 e 7, no `scripts/importar.py`.

Item 7 (contratos do lote 2, §6): o `plano` (e o `copiar`, que o recalcula) só aceita a `--origem` registrada para o
projeto do destino em `registry/projetos-host.json` (`fundacao.projetos_host/1`), lido com teto e sem seguir ligação;
sem o registro, ou sem a origem nele, recusa com o comando pronto do `preparo_host.py registrar-projeto`.
Item 6 (§8): a origem é aberta pela abertura conferida da cópia única (`copia_segura.abrir_comum`, dentro da origem); o
destino continua gravado pelo `Gravador`. Pastas descartáveis, conteúdo fictício.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import SCRIPTS, criar_ligacao_dir, rodar_script
from test_importar import rodar_copiar  # o copiar recusa rodar de dentro de projects/ (CI-F1)

CANARIO = "CANARIO-DE-FORA-DA-ORIGEM-FICTICIO"


def carregar():
    spec = importlib.util.spec_from_file_location("_teste_integ_importar", SCRIPTS / "importar.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


IMP = carregar()


def apagar_arvore(caminho: Path) -> None:
    def tirar_so_leitura(func, alvo, _exc):
        try:
            os.chmod(alvo, stat.S_IWRITE | stat.S_IREAD)
            func(alvo)
        except OSError:
            pass
    shutil.rmtree(caminho, onexc=tirar_so_leitura)


class _Importacao(unittest.TestCase):
    def setUp(self):
        # O importador roda neste processo: a raiz da fundação viva do ambiente (FUNDACAO_RAIZ, que o perfil do Windows
        # da 1.7.10 põe nas sessões da raiz) não vale aqui, como o apoio já faz para os subprocessos (1.7.10.1).
        ambiente = mock.patch.dict(os.environ)
        ambiente.start()
        self.addCleanup(ambiente.stop)
        os.environ.pop("FUNDACAO_RAIZ", None)
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="integ-importar-")))
        self.addCleanup(apagar_arvore, self.base)
        self.origem = self.base / "fontes" / "app"
        for rel, texto in {"a.txt": "a\n", "caso/dois.txt": "dois\n", "caso/um.txt": "um\n",
                           "sub/b.txt": "b\n"}.items():
            (self.origem / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.origem / rel).write_text(texto, encoding="utf-8")
        self.raiz = self.base / "fundacao"
        (self.raiz / "projects" / "proj-a").mkdir(parents=True)
        (self.raiz / "fundacao").mkdir()
        (self.raiz / "fundacao" / "__main__.py").write_text("# raiz de teste\n", encoding="utf-8")
        (self.raiz / "registry").mkdir()
        (self.raiz / "state").mkdir()
        self.registro = self.raiz / "registry" / "projetos-host.json"
        self.registrar({"proj-a": [self.origem]})
        self.destino = self.raiz / "projects" / "proj-a" / "data" / "origem" / "parte1"
        self.plano_arq = self.base / "planos" / "plano.json"

    def registrar(self, projetos: dict, **extra) -> None:
        dados = {"schema_version": "fundacao.projetos_host/1",
                 "projetos": {p: {"origens": [str(o) for o in origens], "somente_leitura": [], "aninhadas_negadas": []}
                              for p, origens in projetos.items()}, **extra}
        if os.path.lexists(self.registro):
            self.registro.unlink()
        self.registro.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")

    def plano(self, origem: Path | None = None, codigo: int = 0) -> dict:
        p = rodar_script("importar.py", "plano", "--origem", origem or self.origem, "--destino", self.destino,
                         "--raiz-fundacao", self.raiz, "--saida", self.plano_arq)
        self.assertEqual(p.returncode, codigo, p.stdout + p.stderr)
        return json.loads(p.stdout) if codigo == 0 else {"erro": json.loads(p.stderr.strip().splitlines()[-1])["erro"]}


class TestOrigemRegistrada(_Importacao):
    def test_sem_registro_recusa_com_o_comando_pronto(self):
        self.registro.unlink()
        erro = self.plano(codigo=2)["erro"]
        for trecho in ("não está registrada", "não existe", "registrar-projeto", "--projeto 'proj-a'",
                       f"--origem '{self.origem}'", "preparo_host.py"):
            self.assertIn(trecho, erro)
        self.assertFalse(self.plano_arq.exists())

    def test_projeto_sem_a_origem_recusa(self):
        outra = self.base / "fontes" / "outra"
        outra.mkdir()
        self.registrar({"proj-a": [outra]})
        self.assertIn("não lista esta origem para o projeto proj-a", self.plano(codigo=2)["erro"])
        self.registrar({"proj-b": [self.origem]})
        self.assertIn("não tem o projeto proj-a", self.plano(codigo=2)["erro"])

    def test_pasta_dentro_da_origem_registrada_vale_e_a_de_fora_nao(self):
        self.registrar({"proj-a": [self.base / "fontes"]})
        self.assertEqual(len(self.plano()["sha256"]), 64)
        self.registrar({"proj-a": [self.origem / "sub"]})
        self.plano(codigo=2)  # a origem fica ACIMA da registrada: não vale
        self.plano(origem=self.origem / "sub")

    def test_registro_fora_do_formato_acima_do_teto_ou_com_vinculo_recusa(self):
        casos = {"não é JSON": b"{nada", "outro esquema": json.dumps({"schema_version": "x", "projetos": {}}).encode(),
                 "projetos não é objeto": json.dumps({"schema_version": "fundacao.projetos_host/1",
                                                      "projetos": []}).encode(),
                 "acima do teto": b" " * (IMP.TETO_REGISTRO + 1)}
        for nome, bruto in casos.items():
            with self.subTest(nome):
                self.registro.write_bytes(bruto)
                self.plano(codigo=2)
        self.registrar({"proj-a": [self.origem]})
        try:
            os.link(self.registro, self.base / "outro-nome.json")
        except OSError as exc:
            self.skipTest(f"vínculo físico indisponível: {exc}")
        self.assertIn("sem seguir ligação", self.plano(codigo=2)["erro"])

    def test_registro_que_e_ligacao_recusa(self):
        verdadeiro = self.base / "registro-de-fora.json"
        verdadeiro.write_text(json.dumps({"schema_version": "fundacao.projetos_host/1",
                                          "projetos": {"proj-a": {"origens": [str(self.origem)]}}}), encoding="utf-8")
        self.registro.unlink()
        try:
            self.registro.symlink_to(verdadeiro)
        except OSError as exc:
            self.skipTest(f"link simbólico de arquivo indisponível: {exc}")
        self.assertIn("sem seguir ligação", self.plano(codigo=2)["erro"])

    def test_copiar_reconfere_o_registro(self):
        dados = self.plano()
        self.registrar({"proj-a": []})
        p = rodar_copiar("--plano", self.plano_arq, "--plano-sha256", dados["sha256"])  # de fora de projects/ (CI-F1)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("não está registrada", p.stderr)
        self.assertFalse(self.destino.exists())

    def test_caminho_do_registro_entre_windows_e_wsl(self):
        if os.name == "nt":
            casos = {"/mnt/d/IA/fonte": "D:\\IA\\fonte", "D:\\IA\\fonte": "D:\\IA\\fonte", "D:/IA/fonte": "D:/IA/fonte",
                     "relativo\\x": None, "/tmp/x": None}
        else:
            casos = {"D:\\IA\\fonte": "/mnt/d/IA/fonte", "D:/IA/fonte": "/mnt/d/IA/fonte",
                     "/mnt/d/IA/fonte": "/mnt/d/IA/fonte", "relativo/x": None}
        casos.update({"": None, 7: None})
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(IMP.caminho_local(texto), esperado)


def _sem_caixa(pasta: Path) -> bool:
    """A pasta fica num sistema de arquivos que não distingue maiúsculas (o /mnt/<x> do WSL, no NTFS)."""
    outra = pasta.parent / pasta.name.swapcase()
    return outra != pasta and outra.is_dir() and os.path.samefile(outra, pasta)


class TestOrigemPelaIdentidade(unittest.TestCase):
    """Revisão do pacote: no Ubuntu a comparação de texto distingue maiúsculas, mas o /mnt/<x> (NTFS) não; o registro
    feito no Windows com outra caixa valia no Windows e recusava no WSL. A identidade da pasta (dispositivo e inode)
    resolve, sem aceitar pasta de fora."""

    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="integ-importar-id-")))
        self.addCleanup(apagar_arvore, self.base)
        (self.base / "registry").mkdir()

    def registrar(self, *origens: str) -> None:
        dados = {"schema_version": "fundacao.projetos_host/1",
                 "projetos": {"proj-a": {"origens": list(origens), "somente_leitura": [], "aninhadas_negadas": []}}}
        (self.base / "registry" / "projetos-host.json").write_text(json.dumps(dados, ensure_ascii=False),
                                                                   encoding="utf-8")

    def test_identidade_vale_para_a_pasta_e_para_o_que_fica_dentro(self):
        origem, outra = self.base / "fonte", self.base / "outra"
        (origem / "sub").mkdir(parents=True)
        outra.mkdir()
        apelido = self.base / "apelido"
        criar_ligacao_dir(apelido, origem)  # outro caminho para a mesma pasta
        self.assertTrue(IMP.dentro_pela_identidade(str(origem), str(apelido)))
        self.assertTrue(IMP.dentro_pela_identidade(str(origem / "sub"), str(apelido)))
        self.assertFalse(IMP.dentro_pela_identidade(str(outra), str(apelido)))
        self.assertFalse(IMP.dentro_pela_identidade(str(origem), str(origem / "sub")), "acima da registrada: não")
        self.assertFalse(IMP.dentro_pela_identidade(str(origem), str(self.base / "nao-existe")))

    @unittest.skipUnless(sys.platform.startswith("linux") and _sem_caixa(SCRIPTS),
                         "só no Linux com a skill num /mnt/<x> que não distingue maiúsculas (o WSL no NTFS)")
    def test_registro_com_outra_caixa_no_mnt_vale_no_wsl(self):
        # A pasta registrada é a dos scripts da skill (só lida aqui: stat), com outra caixa; o registro fica no /tmp.
        outra_caixa = str(SCRIPTS.parent / SCRIPTS.name.swapcase())
        self.registrar(outra_caixa)
        IMP.conferir_origem_registrada(self.base, "proj-a", SCRIPTS)
        IMP.conferir_origem_registrada(self.base, "proj-a", SCRIPTS / "tests")  # dentro dela
        partes = SCRIPTS.parts
        if len(partes) > 3 and partes[1] == "mnt" and len(partes[2]) == 1:  # o texto digitado no Windows, em minúsculas
            self.registrar(f"{partes[2].upper()}:\\" + "\\".join(partes[3:]).lower())
            IMP.conferir_origem_registrada(self.base, "proj-a", SCRIPTS)
        self.registrar(str(SCRIPTS.parent / "REFERENCES"))  # outra pasta que existe, com outra caixa: recusa
        with self.assertRaises(IMP.Recusa):
            IMP.conferir_origem_registrada(self.base, "proj-a", SCRIPTS)
        self.registrar(str(SCRIPTS / "TESTS"))  # a origem fica acima da registrada: recusa
        with self.assertRaises(IMP.Recusa):
            IMP.conferir_origem_registrada(self.base, "proj-a", SCRIPTS)


class TestAberturaConferidaDaOrigem(_Importacao):
    def copiar(self, sha: str) -> tuple[int, dict]:
        saida = io.StringIO()
        with mock.patch.object(sys, "stdout", saida), mock.patch.object(sys, "stderr", io.StringIO()):
            codigo = IMP.main(["copiar", "--plano", str(self.plano_arq), "--plano-sha256", sha])
        return codigo, (json.loads(saida.getvalue()) if saida.getvalue().strip() else {})

    def test_a_origem_e_aberta_pela_copia_unica(self):
        dados = self.plano()
        chamadas = []
        real = IMP.COPIA.abrir_comum

        def espiao(caminho, dentro_de=None):
            chamadas.append((Path(caminho), Path(dentro_de)))
            return real(caminho, dentro_de)

        with mock.patch.object(IMP.COPIA, "abrir_comum", side_effect=espiao):
            codigo, res = self.copiar(dados["sha256"])
        self.assertEqual((codigo, res["falhas"]), (0, []))
        lidos = {c.relative_to(self.origem).as_posix() for c, base in chamadas if base == self.origem}
        self.assertLessEqual({"a.txt", "caso/dois.txt", "caso/um.txt", "sub/b.txt"}, lidos)

    def test_pasta_da_origem_trocada_por_ligacao_durante_a_copia_fica_nas_falhas(self):
        fora = self.base / "fora"
        fora.mkdir()
        (fora / "um.txt").write_text(CANARIO, encoding="utf-8")
        dados = self.plano()
        original = IMP.Copia.copiar_arquivo

        def troca_no_meio(self2, item, **extra):
            original(self2, item, **extra)
            if item["caminho"] == "caso/dois.txt":  # a pasta da origem vira ligação para fora entre dois arquivos
                apagar_arvore(self2.origem / "caso")
                criar_ligacao_dir(self2.origem / "caso", fora)

        with mock.patch.object(IMP.Copia, "copiar_arquivo", troca_no_meio):
            codigo, res = self.copiar(dados["sha256"])
        self.assertEqual(codigo, 1)
        falha = next(f for f in res["falhas"] if f["caminho"] == "caso/um.txt")
        self.assertNotIn("ilegível", falha["motivo"], "a recusa da abertura conferida vem com o motivo")
        copiados = "".join(p.read_text(encoding="utf-8") for p in self.destino.rglob("*.txt"))
        self.assertNotIn(CANARIO, copiados)

    def test_copia_do_sqlite_trocada_na_pasta_temporaria_fica_nas_falhas(self):
        # A pasta temporária da API de backup fica no destino, onde a sessão grava: um vínculo físico posto no lugar
        # de copia.sqlite (para um arquivo de fora) não pode ir para a cópia.
        con = sqlite3.connect(self.origem / "dados.db")
        con.execute("CREATE TABLE t (v TEXT)")
        con.execute("INSERT INTO t VALUES ('x')")
        con.commit()
        con.close()
        fora = self.base / "de-fora.bin"
        fora.write_bytes(CANARIO.encode("utf-8"))
        dados = self.plano()
        real = IMP.subprocess.run

        def trocar(args, **kw):
            r = real(args, **kw)
            saida = Path(args[args.index("--destino") + 1])
            saida.unlink()
            try:
                os.link(fora, saida)
            except OSError as exc:
                raise unittest.SkipTest(f"vínculo físico indisponível: {exc}") from None
            return r

        with mock.patch.object(IMP.subprocess, "run", side_effect=trocar):
            codigo, res = self.copiar(dados["sha256"])
        self.assertEqual(codigo, 1)
        self.assertIn("dados.db", {f["caminho"] for f in res["falhas"]})
        self.assertNotIn(CANARIO.encode("utf-8"),
                         b"".join(p.read_bytes() for p in self.destino.rglob("*") if p.is_file()))


if __name__ == "__main__":
    unittest.main()
