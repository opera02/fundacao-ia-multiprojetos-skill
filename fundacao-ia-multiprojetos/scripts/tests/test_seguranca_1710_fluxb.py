"""Revisão de segurança da 1.7.10, rodada 4, grupo FLUXB: FLUXB-F2, FLUXB-F4, FLUXB-F5, CI-F6 e a parte do CI-F1 que
cabe ao `importar.py`. Cada teste reproduz o achado (falha no código de antes, 4e88910) e confere o uso normal.

- FLUXB-F2: gravações do titular em pasta que a sessão grava seguiam a ligação posta numa pasta acima. No `importar.py
  copiar`, a pasta temporária da cópia do SQLite nascia pelo caminho do destino, e a sessão que trocava uma pasta acima
  dele por ligação deixava o banco em outro projeto; a limpeza das sobras também ia pelo caminho. No `rodar` do perfil,
  a pasta de saída e o registro eram criados e abertos pelo caminho depois da conferência.
- FLUXB-F4: a varredura do plano entrava numa cópia de segurança do kit (ou numa raiz de fundação, ou no banco dela)
  dentro da origem registrada, e o `copiar` a levava inteira ao projeto, com o state.sqlite de todos os projetos.
- FLUXB-F5: os textos do perfil prometiam o que é da 1.7.11 (a ficha com execucao[], o porteiro que roda, a jaula).
- CI-F6: a sentinela abria uma caixa mais simples que a dos testes, e os testes da caixa pulavam com a CI verde.
- CI-F1: o `copiar`, passo do titular fora do sandbox, rodava de uma cópia da skill dentro de projects/.
A cópia de segurança é feita de verdade pelo kit desta skill (`fundacao.core.backup.create_backup`). Dados fictícios,
em pastas temporárias.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import test_auditoria_1_7_6_execucao_isolada as testes_da_auditoria
import test_execucao_perfil as testes_do_perfil
import test_sentinela_ci as sentinela
from apoio import ENV, KIT, SCRIPTS, criar_ligacao_dir, rodar_script
from test_importar import apagar_arvore, copiar_scripts_e_kit, rodar_copiar

NO_LINUX = sys.platform.startswith("linux")
SEM_FUNDACAO = {k: v for k, v in ENV.items() if not k.startswith("FUNDACAO_")}
CANARIO_OUTRO = "CANARIO-OUTRO-PROJETO-FICTICIO"
VARIAVEL_CI = "FUNDACAO_CI_EXIGE_BWRAP"


def carregar(nome: str):
    spec = importlib.util.spec_from_file_location(f"_seguranca_1710_fluxb_{nome}", SCRIPTS / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


IMP = carregar("importar")
EX = carregar("execucao_isolada")


class _Fundacao(unittest.TestCase):
    """Uma fundação de teste com os projetos proj-a (o do destino) e proj-b (o outro)."""

    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="seg1710-fluxb-")))
        self.addCleanup(apagar_arvore, self.base)
        self.raiz = self.base / "fundacao"
        for pasta in ("projects/proj-a", "projects/proj-b", "fundacao", "registry", "state"):
            (self.raiz / pasta).mkdir(parents=True, exist_ok=True)
        (self.raiz / "fundacao" / "__main__.py").write_text("# raiz de teste\n", encoding="utf-8")
        self.destino = self.raiz / "projects" / "proj-a" / "data" / "origem" / "parte1"
        self.plano_arq = self.base / "planos" / "plano.json"

    def registrar(self, *origens: Path) -> None:
        dados = {"schema_version": "fundacao.projetos_host/1",
                 "projetos": {"proj-a": {"origens": [str(o) for o in origens], "somente_leitura": [],
                                         "aninhadas_negadas": []}}}
        (self.raiz / "registry" / "projetos-host.json").write_text(json.dumps(dados, ensure_ascii=False),
                                                                   encoding="utf-8")

    def plano(self, origem: Path, *extra, codigo: int = 0) -> dict:
        p = rodar_script("importar.py", "plano", "--origem", origem, "--destino", self.destino, "--raiz-fundacao",
                         self.raiz, "--saida", self.plano_arq, *extra)
        self.assertEqual(p.returncode, codigo, p.stdout + p.stderr)
        if codigo:
            return {"erro": json.loads(p.stderr.strip().splitlines()[-1])["erro"]}
        dados = json.loads(p.stdout)
        dados["plano_json"] = json.loads(self.plano_arq.read_text(encoding="utf-8"))
        return dados

    def copiar_no_processo(self, sha: str) -> tuple[int, dict]:
        saida = io.StringIO()
        with mock.patch.dict(os.environ), mock.patch.object(sys, "stdout", saida), \
                mock.patch.object(sys, "stderr", io.StringIO()):
            os.environ.pop("FUNDACAO_RAIZ", None)
            codigo = IMP.main(["copiar", "--plano", str(self.plano_arq), "--plano-sha256", sha])
        return codigo, (json.loads(saida.getvalue()) if saida.getvalue().strip() else {})

    @staticmethod
    def por_caminho(itens: list) -> dict:
        return {i["caminho"]: i for i in itens}


# ------------------------------------------------------------------------------------------------ FLUXB-F2 (importar)
class TestF2CopiaDoSqliteForaDaArvoreDaSessao(_Fundacao):
    """A sessão troca `data/origem` (acima do destino) por ligação para o outro projeto durante a cópia do SQLite."""

    def setUp(self):
        super().setUp()
        self.origem = self.base / "fontes" / "app"
        (self.origem / "dados").mkdir(parents=True)
        (self.origem / "a.txt").write_text("a\n", encoding="utf-8")
        con = sqlite3.connect(self.origem / "dados" / "app.db")
        con.execute("CREATE TABLE itens (v TEXT)")
        con.execute("INSERT INTO itens VALUES ('um')")
        con.commit()
        con.close()
        self.registrar(self.origem)
        self.outro = self.raiz / "projects" / "proj-b" / "data"  # o alvo da ligação: o outro projeto
        (self.outro / "parte1").mkdir(parents=True)
        self.acima = self.raiz / "projects" / "proj-a" / "data" / "origem"

    def trocar(self) -> None:
        os.rename(self.acima, self.acima.with_name("origem-real"))
        criar_ligacao_dir(self.acima, self.outro)

    def destrocar(self) -> None:
        if os.path.lexists(self.acima) and os.path.lexists(self.acima.with_name("origem-real")):
            if os.name == "nt":
                os.rmdir(self.acima)  # a junção sai sem levar o alvo
            else:
                os.unlink(self.acima)
            os.rename(self.acima.with_name("origem-real"), self.acima)

    def no_outro_projeto(self) -> list[str]:
        return sorted(p.relative_to(self.outro).as_posix() for p in self.outro.rglob("*"))

    def test_banco_nao_fica_no_outro_projeto(self):
        dados = self.plano(self.origem)
        original, real, visto = IMP.Copia.copiar_sqlite, IMP.subprocess.run, {}

        def troca_antes(self2, item):  # a troca cai antes da pasta temporária
            self.trocar()
            return original(self2, item)

        def destroca_depois(args, **kw):  # e é desfeita logo depois do backup_sqlite.py, antes da limpeza
            if not any(str(a).endswith("backup_sqlite.py") for a in args):
                return real(args, **kw)  # o mklink /J da troca, no Windows
            visto["trocado"] = os.path.realpath(self.acima) == os.path.realpath(self.outro)
            r = real(args, **kw)
            self.destrocar()
            return r

        try:
            with mock.patch.object(IMP.Copia, "copiar_sqlite", troca_antes), \
                    mock.patch.object(IMP.subprocess, "run", side_effect=destroca_depois):
                codigo, res = self.copiar_no_processo(dados["sha256"])
        finally:
            self.destrocar()
        self.assertTrue(visto.get("trocado"), "a troca não valia durante o backup: o teste não exercitou o caminho")
        self.assertEqual(self.no_outro_projeto(), ["parte1"], "o processo do titular gravou no outro projeto")
        self.assertEqual((codigo, res.get("falhas")), (0, []), res)
        banco = self.destino / "dados" / "app.db"
        con = sqlite3.connect(banco.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            self.assertEqual(con.execute("SELECT v FROM itens").fetchall(), [("um",)])
        finally:
            con.close()
        self.assertEqual([p for p in self.destino.iterdir() if p.name.startswith(IMP.PREFIXO_TEMP)], [])

    def test_temporario_do_sqlite_e_privado_e_fora_da_raiz(self):
        dados = self.plano(self.origem)
        vistos, real = [], IMP.subprocess.run

        def espiao(args, **kw):
            if "--destino" in args:
                vistos.append(Path(args[args.index("--destino") + 1]))
            return real(args, **kw)

        with mock.patch.object(IMP.subprocess, "run", side_effect=espiao):
            codigo, res = self.copiar_no_processo(dados["sha256"])
        self.assertEqual((codigo, res["falhas"]), (0, []))
        self.assertEqual(len(vistos), 1)
        self.assertFalse(Path(os.path.realpath(vistos[0])).is_relative_to(Path(os.path.realpath(self.raiz))),
                         vistos[0])
        self.assertFalse(vistos[0].parent.exists(), "o temporário privado sobrou")

    def test_limpeza_das_sobras_nao_sai_do_destino(self):
        sobra = self.outro / "parte1" / ".importando-abcdef12"  # nomes desta ferramenta, no outro projeto
        sobra.mkdir()
        (sobra / "copia.sqlite").write_bytes(b"do outro projeto")
        (self.outro / "parte1" / ".importando-0011.tmp").write_bytes(b"do outro projeto")
        dados = self.plano(self.origem)
        original, visto = IMP.Copia.neutralizar, {}

        def neutralizar_e_trocar(self2, itens):  # a troca cai logo antes da limpeza das sobras
            resultado = original(self2, itens)
            self.trocar()
            visto["trocado"] = os.path.realpath(self.acima) == os.path.realpath(self.outro)
            return resultado

        try:
            with mock.patch.object(IMP.Copia, "neutralizar", neutralizar_e_trocar):
                self.copiar_no_processo(dados["sha256"])
        finally:
            self.destrocar()
        self.assertTrue(visto.get("trocado"), "a troca não aconteceu: o teste não exercitou a limpeza")
        self.assertTrue((sobra / "copia.sqlite").is_file(), "a limpeza apagou uma pasta do outro projeto")
        self.assertTrue((self.outro / "parte1" / ".importando-0011.tmp").is_file())

    # ------------------------------------------------------------------ 1.7.11, N3: a sobra sai sem o Python 3.11
    def test_nenhuma_chamada_do_shutil_rmtree_usa_dir_fd(self):
        """O `shutil.rmtree(dir_fd=)` só existe a partir do Python 3.11, e o SKILL.md declara 3.10+: a sobra de uma cópia
        interrompida (`.importando-*`) é apagada por descritor com `os.unlink` e `os.rmdir`."""
        arvore = ast.parse((SCRIPTS / "importar.py").read_text(encoding="utf-8"))
        chamadas = [n for n in ast.walk(arvore) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "rmtree" and any(k.arg == "dir_fd" for k in n.keywords)]
        self.assertEqual([n.lineno for n in chamadas], [], "shutil.rmtree(dir_fd=) exige o Python 3.11")
        self.assertTrue(callable(IMP.apagar_pasta_por_descritor))

    @unittest.skipUnless(NO_LINUX, "descritor de pasta (dir_fd): Linux; no Windows a limpeza é pelo caminho")
    def test_sobra_do_destino_sai_sem_o_rmtree_com_dir_fd(self):
        """Simula o Python 3.10 (o `shutil.rmtree` recusa `dir_fd`): a cópia termina sem TypeError, a sobra do destino sai
        com o que tem dentro, e uma ligação dentro dela sai como ligação, sem levar o que ela aponta."""
        self.destino.mkdir(parents=True)
        sobra = self.destino / ".importando-abcdef12"
        (sobra / "sub" / "fundo").mkdir(parents=True)
        (sobra / "copia.sqlite").write_bytes(b"sobra")
        (sobra / "sub" / "fundo" / "x.bin").write_bytes(b"sobra")
        alvo = self.outro / "parte1"
        (alvo / "intacto.txt").write_text("do outro projeto\n", encoding="utf-8")
        os.symlink(alvo, sobra / "sub" / "para-o-outro")
        dados = self.plano(self.origem)
        # uma cópia interrompida deixa a marca desta importação: o `copiar` retoma e limpa as sobras
        (self.destino / IMP.MARCA).write_text(json.dumps({"plano_sha256": dados["sha256"]}), encoding="utf-8")
        real = shutil.rmtree

        def sem_dir_fd(caminho, *args, dir_fd=None, **kw):
            if dir_fd is not None:
                raise TypeError("rmtree() got an unexpected keyword argument 'dir_fd'")
            return real(caminho, *args, **kw)

        with mock.patch.object(IMP.shutil, "rmtree", sem_dir_fd):
            codigo, res = self.copiar_no_processo(dados["sha256"])
        self.assertEqual((codigo, res.get("falhas")), (0, []), res)
        self.assertFalse(sobra.exists(), "a sobra do destino não foi apagada")
        self.assertEqual((alvo / "intacto.txt").read_text(encoding="utf-8"), "do outro projeto\n")


# ------------------------------------------------------------------------------------------------ FLUXB-F2 (rodar)
@unittest.skipUnless(NO_LINUX, "descritor de pasta (dir_fd) e O_PATH: Linux; no Windows o rodar não roda (sem caixa)")
class TestF2RegistroEPastaDeSaidaDoRodar(unittest.TestCase):
    """O `rodar` (que o titular roda no terminal) grava na pasta do projeto, que a sessão grava: a sessão troca
    `outputs/execucao` por ligação para o mesmo lugar do outro projeto no instante da gravação. A caixa é simulada
    (`_rodar`): o que se confere é onde o titular grava, não o bubblewrap."""

    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="seg1710-rodar-")))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        raiz = self.base / "raiz"
        self.p, self.outro = raiz / "projects" / "p", raiz / "projects" / "outro"
        (raiz / "state").mkdir(parents=True)
        (raiz / "state" / "state.sqlite").write_bytes(b"")
        (self.p / "codigo").mkdir(parents=True)
        (self.p / "codigo" / "a.txt").write_text("a\n", encoding="utf-8")
        programa = self.p / "codigo" / "prog.sh"
        programa.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
        os.chmod(programa, 0o755)
        self.execucao = self.p / "outputs" / "execucao"
        self.execucao.mkdir(parents=True)
        (self.outro / "outputs" / "execucao").mkdir(parents=True)
        perfil = {"schema_version": EX.ESQUEMA_PERFIL, "perfil_id": "testes", "projeto": "p",
                  "tipo": EX.COMANDOS_DO_PROJETO, "motivo": "teste fictício", "validade": "2099-12-31",
                  "modelos": [{"nome": "roda", "argv": ["./prog.sh", "{caminhos}"]}], "codigo": {"preso": False},
                  "montagens": {"trabalho": "codigo", "saida": "outputs/execucao/saida"}}
        self.arquivo = self.p / "perfis" / "perfil.json"
        self.arquivo.parent.mkdir()
        bruto = json.dumps(perfil).encode("utf-8")
        self.arquivo.write_bytes(bruto)
        self.sha = hashlib.sha256(bruto).hexdigest()
        self.trocado = False

    def trocar(self) -> None:
        if not self.trocado:
            self.trocado = True
            os.rename(self.execucao, self.execucao.with_name("execucao-real"))
            os.symlink(self.outro / "outputs" / "execucao", self.execucao)

    def destrocar(self) -> None:
        if self.trocado:
            os.unlink(self.execucao)
            os.rename(self.execucao.with_name("execucao-real"), self.execucao)

    def sem_lancador(self):
        ambiente = mock.patch.dict(os.environ)
        ambiente.start()
        self.addCleanup(ambiente.stop)
        for nome in ("FUNDACAO_PROJECT", "FUNDACAO_PROJETO_TRAVADO"):
            os.environ.pop(nome, None)

    def test_registro_nao_vai_para_o_outro_projeto(self):
        self.sem_lancador()
        original = os.open

        def abrir(caminho, *a, **k):  # a troca cai no instante de abrir o registro
            if os.fsdecode(caminho).endswith("registro.jsonl"):
                self.trocar()
            return original(caminho, *a, **k)

        caixa = {"codigo": 0, "stdout": b"ok\n", "stderr": b""}
        try:
            with mock.patch.object(EX.PERFIL, "_rodar", return_value=caixa), \
                    mock.patch.object(EX.PERFIL, "bwrap_monta_por_descritor", return_value=True), \
                    mock.patch.object(os, "open", abrir):
                res, codigo = EX.rodar_perfil(self.arquivo, self.sha, ["./prog.sh", "a.txt"], projeto="p",
                                              bwrap="/usr/bin/bwrap", hoje=date(2026, 11, 1))
        finally:
            self.destrocar()
        self.assertTrue(self.trocado, "a troca não aconteceu: o teste não exercitou a gravação")
        self.assertFalse((self.outro / "outputs" / "execucao" / "registro.jsonl").exists(),
                         "o titular anexou a linha do projeto p ao registro do outro projeto")
        linhas = (self.execucao / "registro.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(x)["perfil_id"] for x in linhas], ["testes"])
        self.assertEqual((codigo, res["registro"]), (0, str(self.execucao / "registro.jsonl")))

    def test_pasta_de_saida_nova_nao_nasce_no_outro_projeto(self):
        self.sem_lancador()
        perfil = EX.ler_perfil(self.arquivo, self.sha, hoje=date(2026, 11, 1))
        original = os.mkdir

        def criar(caminho, *a, **k):  # a troca cai no instante de criar a pasta de saída
            if os.fsdecode(caminho).endswith("saida"):
                self.trocar()
            return original(caminho, *a, **k)

        try:
            with mock.patch.object(os, "mkdir", criar):
                try:
                    EX.plano_do_perfil(perfil, ["./prog.sh", "a.txt"], bwrap="/usr/bin/bwrap")
                except (EX.Recusa, OSError):
                    pass  # a pasta conferida virou ligação: o plano recusa
        finally:
            self.destrocar()
        self.assertTrue(self.trocado)
        self.assertEqual(sorted(os.listdir(self.outro / "outputs" / "execucao")), [],
                         "o titular criou a pasta de saída no outro projeto")

    def test_fifo_no_lugar_do_registro_nao_prende_o_rodar(self):
        self.sem_lancador()
        os.mkfifo(self.execucao / "registro.jsonl")
        with mock.patch.object(EX.PERFIL, "_rodar", return_value={"codigo": 0, "stdout": b"", "stderr": b""}), \
                mock.patch.object(EX.PERFIL, "bwrap_monta_por_descritor", return_value=True):
            res, codigo = EX.rodar_perfil(self.arquivo, self.sha, ["./prog.sh", "a.txt"], projeto="p",
                                          bwrap="/usr/bin/bwrap", hoje=date(2026, 11, 1))
        self.assertEqual(codigo, 3)
        self.assertTrue(res["registro"].startswith("falhou"), res["registro"])


# ------------------------------------------------------------------------------------------------ FLUXB-F4
class TestF4CopiaDeSegurancaNaOrigem(_Fundacao):
    """O titular registrou uma origem larga (a unidade que guarda também as cópias de segurança da fundação)."""

    @classmethod
    def setUpClass(cls):
        cls.molde = Path(os.path.realpath(tempfile.mkdtemp(prefix="seg1710-copia-real-")))
        raiz = cls.molde / "raiz-copiada"
        env = {**SEM_FUNDACAO, "PYTHONPATH": str(KIT)}
        r = subprocess.run([sys.executable, "-B", "-m", "fundacao", "--raiz", str(raiz), "init", "--admin",
                            "titular-ficticio"], capture_output=True, text=True, env=env, timeout=300)
        if r.returncode != 0:
            raise AssertionError(r.stdout + r.stderr)
        (raiz / "fundacao").mkdir(exist_ok=True)  # o kit instalado na raiz: o pacote fundacao vai para files/
        (raiz / "fundacao" / "__main__.py").write_text("# kit instalado (fictício)\n", encoding="utf-8")
        (raiz / "projects" / "outro" / "data").mkdir(parents=True, exist_ok=True)
        (raiz / "projects" / "outro" / "data" / "cliente-ficticio.txt").write_text(CANARIO_OUTRO, encoding="utf-8")
        codigo = ("import sys; from pathlib import Path; from fundacao.core import backup; "
                  "backup.create_backup(Path(sys.argv[1]), Path(sys.argv[2]), 'copia-ficticia')")
        r = subprocess.run([sys.executable, "-B", "-c", codigo, str(raiz), str(cls.molde / "copia")],
                           capture_output=True, text=True, env=env, timeout=300)
        if r.returncode != 0:
            raise AssertionError(r.stdout + r.stderr)
        cls.raiz_copiada = raiz

    @classmethod
    def tearDownClass(cls):
        apagar_arvore(cls.molde)

    def setUp(self):
        super().setUp()
        self.unidade = self.base / "unidade"
        (self.unidade / "trabalho" / "app").mkdir(parents=True)
        (self.unidade / "trabalho" / "app" / "a.txt").write_text("a\n", encoding="utf-8")
        self.copia = self.unidade / "copias" / "2026-11-01"
        shutil.copytree(self.molde / "copia", self.copia)
        self.registrar(self.unidade)

    def test_a_copia_e_de_verdade(self):
        for rel in ("manifest.json", "files/fundacao/__main__.py", "files/projects/outro/data/cliente-ficticio.txt",
                    "state/state.sqlite"):
            self.assertTrue((self.copia / rel).is_file(), rel)

    def test_origem_que_e_a_copia_ou_fica_nela_recusa(self):
        for origem in (self.copia, self.copia / "state", self.copia / "files", self.copia / "files" / "projects"
                       / "outro"):
            with self.subTest(origem=origem.relative_to(self.unidade).as_posix()):
                erro = self.plano(origem, codigo=2)["erro"]
                self.assertIn("um projeto não importa de outro", erro)
                self.assertFalse(self.plano_arq.exists())
        self.assertIn("cópia de segurança do kit", self.plano(self.copia, codigo=2)["erro"])

    def test_copia_dentro_da_origem_fica_fora_com_aviso_e_nao_e_copiada(self):
        dados = self.plano(self.unidade)
        itens = self.por_caminho(dados["plano_json"]["itens"])
        self.assertEqual((itens["copias/2026-11-01"]["classe"], itens["copias/2026-11-01"]["regra"]),
                         ("fundacao", "copia-do-kit"))
        self.assertEqual([c for c in itens if c.startswith("copias/2026-11-01/")], [])
        self.assertEqual(itens["trabalho/app/a.txt"]["classe"], "comum")
        self.assertEqual(dados["resumo"]["fundacao"], 1)
        aviso = next(a for a in dados["avisos"] if "pasta(s) de fundação" in a)
        self.assertIn("copias/2026-11-01", aviso)
        p = rodar_copiar("--plano", self.plano_arq, "--plano-sha256", dados["sha256"])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        copiados = [x for x in self.destino.rglob("*") if x.is_file()]
        self.assertIn(self.destino / "trabalho" / "app" / "a.txt", copiados)
        self.assertFalse([x for x in copiados if x.name == "state.sqlite" or CANARIO_OUTRO.encode() in x.read_bytes()])
        fora = self.por_caminho(json.loads((self.destino / "MANIFESTO-IMPORTACAO.json").read_text("utf-8"))["fora"])
        self.assertEqual(fora["copias/2026-11-01"]["regra"], "copia-do-kit")

    def test_raiz_de_fundacao_e_banco_dentro_da_origem_ficam_fora(self):
        shutil.copytree(self.raiz_copiada, self.unidade / "fundacao-velha")
        (self.unidade / "so-o-banco" / "state").mkdir(parents=True)
        shutil.copy2(self.copia / "state" / "state.sqlite", self.unidade / "so-o-banco" / "state" / "state.sqlite")
        shutil.rmtree(self.copia)
        itens = self.por_caminho(self.plano(self.unidade)["plano_json"]["itens"])
        self.assertEqual(itens["fundacao-velha"]["regra"], "raiz-de-fundacao")
        self.assertEqual(itens["so-o-banco"]["regra"], "banco-da-fundacao")
        self.assertEqual([c for c in itens if c.startswith(("fundacao-velha/", "so-o-banco/"))], [])

    def test_copia_dentro_de_pasta_de_segredo_nao_entra_pelo_opaco(self):
        (self.unidade / ".segredos").mkdir()
        (self.unidade / ".segredos" / "token.txt").write_text("opaco fictício\n", encoding="utf-8")
        shutil.move(str(self.copia), str(self.unidade / ".segredos" / "copia"))
        dados = self.plano(self.unidade, "--opaco", ".segredos/*")
        itens = self.por_caminho(dados["plano_json"]["itens"])
        self.assertEqual(itens[".segredos/token.txt"]["classe"], "opaco")
        self.assertEqual([c for c in itens if c.startswith(".segredos/copia")], [])
        aviso = next(a for a in dados["avisos"] if "pasta(s) de fundação" in a)
        self.assertIn("1 sem o nome", aviso)
        self.assertNotIn(".segredos/copia", aviso)

    # ------------------------------------------------------------------ 1.7.11, N4: a cópia só de projects/ ou de um projeto
    def _projeto_copiado(self, onde: Path, nome: str = "outro") -> Path:
        """A pasta de um projeto como a cópia a deixa: INSTRUCOES.md, data/ e outputs/, sem nada do resto da fundação."""
        pasta = onde / nome
        (pasta / "data").mkdir(parents=True)
        (pasta / "outputs").mkdir()
        (pasta / "INSTRUCOES.md").write_text("# Instruções do projeto de teste\n", encoding="utf-8")
        (pasta / "data" / "cliente-ficticio.txt").write_text(CANARIO_OUTRO, encoding="utf-8")
        return pasta

    def test_copia_so_de_projects_dentro_da_origem_fica_fora_com_aviso(self):
        outro = self._projeto_copiado(self.unidade / "copias-parciais" / "projects")
        dados = self.plano(self.unidade)
        itens = self.por_caminho(dados["plano_json"]["itens"])
        rel = outro.relative_to(self.unidade).as_posix()
        self.assertEqual((itens[rel]["classe"], itens[rel]["regra"]), ("fundacao", "projeto-de-fundacao"))
        self.assertEqual([c for c in itens if c.startswith(rel + "/")], [])
        self.assertEqual(itens["trabalho/app/a.txt"]["classe"], "comum")
        aviso = next(a for a in dados["avisos"] if "pasta(s) de fundação" in a)
        self.assertIn(rel, aviso)
        p = rodar_copiar("--plano", self.plano_arq, "--plano-sha256", dados["sha256"])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse([x for x in self.destino.rglob("*") if x.is_file() and x.name == "cliente-ficticio.txt"])
        # a origem que é a pasta `projects` da cópia: o projeto de dentro é podado do mesmo jeito
        itens = self.por_caminho(self.plano(outro.parent)["plano_json"]["itens"])
        self.assertEqual(itens["outro"]["regra"], "projeto-de-fundacao")
        self.assertEqual([c for c in itens if c.startswith("outro/")], [])

    def test_origem_que_e_a_pasta_de_outro_projeto_ou_fica_nela_recusa(self):
        outro = self._projeto_copiado(self.unidade / "copias-parciais" / "projects")
        self.registrar(self.unidade)
        for origem in (outro, outro / "data"):
            with self.subTest(origem=origem.relative_to(self.unidade).as_posix()):
                erro = self.plano(origem, codigo=2)["erro"]
                self.assertIn("um projeto não importa de outro", erro)
                self.assertFalse(self.plano_arq.exists())
        self.assertIn("pasta de um projeto da fundação", self.plano(outro, codigo=2)["erro"])

    def test_a_marca_de_projeto_nao_vale_para_o_proprio_projeto_do_destino(self):
        """A importação de dentro do projeto do destino continua: ele tem INSTRUCOES.md, data/ e outputs/, e só o que
        está abaixo dele conta."""
        projeto = self.raiz / "projects" / "proj-a"
        (projeto / "outputs").mkdir()
        (projeto / "data").mkdir(exist_ok=True)
        (projeto / "INSTRUCOES.md").write_text("# Instruções do projeto de teste\n", encoding="utf-8")
        local = projeto / "trabalho-local" / "app"
        local.mkdir(parents=True)
        (local / "b.txt").write_text("b\n", encoding="utf-8")
        self.registrar(local)
        self.assertEqual(IMP.marca_de_fundacao(projeto), "projeto-de-fundacao")  # ele tem a marca...
        dados = self.plano(local)  # ...e mesmo assim a importação de dentro dele segue
        itens = self.por_caminho(dados["plano_json"]["itens"])
        self.assertEqual(itens["b.txt"]["classe"], "comum")
        # uma cópia de outro projeto DENTRO do projeto do destino continua recusada
        copiado = self._projeto_copiado(projeto / "velho", "projects-copia")
        self.registrar(copiado)
        self.assertIn("dentro do projeto", self.plano(copiado, codigo=2)["erro"])

    def test_pasta_com_so_parte_da_marca_de_projeto_nao_e_fundacao(self):
        for parte in ("INSTRUCOES.md", "data", "outputs"):
            pasta = self.unidade / f"quase-{parte.lower().replace('.', '-')}"
            outras = {"INSTRUCOES.md", "data", "outputs"} - {parte}
            pasta.mkdir()
            for nome in outras:
                if nome == "INSTRUCOES.md":
                    (pasta / nome).write_text("# x\n", encoding="utf-8")
                else:
                    (pasta / nome).mkdir()
            self.assertIsNone(IMP.marca_de_fundacao(pasta), parte)
        pasta = self.unidade / "instrucoes-como-pasta"  # INSTRUCOES.md precisa ser arquivo comum
        (pasta / "INSTRUCOES.md").mkdir(parents=True)
        (pasta / "data").mkdir()
        (pasta / "outputs").mkdir()
        self.assertIsNone(IMP.marca_de_fundacao(pasta))

    def test_copia_com_o_nome_de_git_nao_vai_para_o_zip(self):
        (self.unidade / "repo").mkdir()
        shutil.move(str(self.copia), str(self.unidade / "repo" / ".git"))
        itens = self.por_caminho(self.plano(self.unidade)["plano_json"]["itens"])
        self.assertEqual((itens["repo/.git"]["classe"], itens["repo/.git"]["regra"]), ("fundacao", "copia-do-kit"))

    def test_copia_no_projeto_do_destino_tambem_recusa(self):
        velho = self.raiz / "projects" / "proj-a" / "velho"
        shutil.copytree(self.molde / "copia", velho / "copia")
        self.registrar(velho)
        self.assertIn("dentro do projeto", self.plano(velho / "copia", codigo=2)["erro"])
        itens = self.por_caminho(self.plano(velho)["plano_json"]["itens"])
        self.assertEqual(itens["copia"]["classe"], "fundacao")

    def test_lista_de_permissao_nao_mostra_o_nome_da_pasta_podada(self):
        dados = self.plano(self.unidade, "--modo", "lista-de-permissao", "--permitir", "trabalho/*")
        aviso = next(a for a in dados["avisos"] if "pasta(s) de fundação" in a)
        self.assertIn("1 sem o nome", aviso)
        self.assertNotIn("2026-11-01", json.dumps(dados, ensure_ascii=False))

    def test_ultima_copia_do_titular(self):
        zipadas = self.unidade / "copias" / "zipadas"  # sem marca nenhuma: só o registro diz que é cópia
        zipadas.mkdir()
        (zipadas / "fundacao-2026-10.zip").write_bytes(b"PK zip ficticio")
        registro = self.raiz / "registry" / "ultima-copia.json"
        registro.write_text(json.dumps({"schema_version": "fundacao.ultima_copia/1", "rotulo": "x",
                                        "criada_em": "2026-10-31T00:00:00+00:00", "verificada_em": None,
                                        "destino": str(zipadas)}), encoding="utf-8")
        itens = self.por_caminho(self.plano(self.unidade)["plano_json"]["itens"])
        self.assertEqual((itens["copias/zipadas"]["classe"], itens["copias/zipadas"]["regra"]),
                         ("fundacao", "copia-do-titular"))
        self.assertNotIn("copias/zipadas/fundacao-2026-10.zip", itens)
        self.assertIn("última cópia de segurança do titular", self.plano(zipadas, codigo=2)["erro"])
        registro.write_bytes(b"{nada")  # ilegível: o plano segue, com o aviso, e as marcas continuam valendo
        dados = self.plano(self.unidade)
        self.assertTrue([a for a in dados["avisos"] if "ultima-copia.json não foi lido" in a], dados["avisos"])
        self.assertEqual(self.por_caminho(dados["plano_json"]["itens"])["copias/2026-11-01"]["classe"], "fundacao")


# ------------------------------------------------------------------------------------------------ CI-F1 (importar)
class TestCIF1CopiarDeDentroDeProjects(_Fundacao):
    """O `copiar` é passo do titular, fora do sandbox: de uma cópia da skill dentro da pasta projects/ de uma fundação
    (onde a sessão grava), ele recusa antes de carregar os módulos ao lado."""

    def setUp(self):
        super().setUp()
        self.origem = self.base / "fontes" / "app"
        self.origem.mkdir(parents=True)
        (self.origem / "a.txt").write_text("a\n", encoding="utf-8")
        self.registrar(self.origem)
        self.sha = self.plano(self.origem)["sha256"]
        self.outra = self.base / "outra-fundacao"  # a fundação de outra pasta, com a skill copiada num projeto
        (self.outra / "registry").mkdir(parents=True)
        self.skill = self.outra / "projects" / "q" / "skill"
        self.scripts = copiar_scripts_e_kit(self.skill)
        self.carregou = self.base / "carregou-o-modulo-ao-lado.txt"
        with open(self.scripts / "regras_de_segredo.py", "a", encoding="utf-8", newline="\n") as fh:  # a sessão o troca
            fh.write(f"\nimport pathlib as _pl\n_pl.Path({str(self.carregou)!r}).write_text('sim', encoding='utf-8')\n")

    def copiar(self, scripts: Path) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-I", "-B", str(scripts / "importar.py"), "copiar", "--plano",
                               str(self.plano_arq), "--plano-sha256", self.sha], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=ENV, timeout=180)

    def test_de_dentro_de_projects_recusa_sem_carregar_nada(self):
        p = self.copiar(self.scripts)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("fica dentro da pasta projects/", p.stderr)
        self.assertIn("skill instalada", p.stderr)
        self.assertFalse(self.carregou.exists(), "o módulo ao lado rodou antes da recusa")
        self.assertFalse(self.destino.exists(), "copiou")

    def test_por_ligacao_de_fora_tambem_recusa(self):
        atalho = self.base / "atalho"
        criar_ligacao_dir(atalho, self.skill)
        p = self.copiar(atalho / "scripts")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("fica dentro da pasta projects/", p.stderr)
        self.assertFalse(self.carregou.exists())

    def test_pasta_projects_sem_registry_nao_e_fundacao(self):
        solta = self.base / "solta" / "projects" / "q" / "skill"
        scripts = copiar_scripts_e_kit(solta)
        self.assertIsNone(IMP.raiz_de_projects_acima(scripts / "importar.py"))
        self.assertEqual(IMP.raiz_de_projects_acima(self.scripts / "importar.py"), self.outra)
        p = self.copiar(scripts)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue((self.destino / "a.txt").is_file())


# ------------------------------------------------------------------------------------------------ FLUXB-F5
class TestF5TextosDoPerfilSemPromessaDa1711(unittest.TestCase):
    """Enquanto a seção `execucao` da ficha for reservada (preenchida, a ficha recusa com "1.7.11"), os textos do perfil
    não citam `execucao[]`, e toda frase deles que fala da ficha, de assinatura, da jaula, do porteiro que roda ou das
    operações executar e rodar diz que é da 1.7.11 (a I24 trocou a folha e a recusa do SHA-256; aqui, o resto)."""

    PALAVRAS = ("ficha", "assinad", "jaula", "porteiro da sessão", "operação executar", "operação rodar")
    ARQUIVOS = ("perfil_execucao.py", "execucao_isolada.py")

    @staticmethod
    def reservadas() -> tuple:
        spec = importlib.util.spec_from_file_location("_seguranca_1710_aberturas_regras",
                                                      KIT / "fundacao" / "core" / "aberturas_regras.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo.RESERVADAS

    @staticmethod
    def textos(arquivo: Path):
        """Cada texto do arquivo (docstrings, mensagens e ajudas), com o f-string inteiro, '{}' no lugar dos valores."""
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        partes = {id(v) for n in ast.walk(arvore) if isinstance(n, ast.JoinedStr) for v in n.values}
        for no in ast.walk(arvore):
            if isinstance(no, ast.JoinedStr):
                yield "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in no.values)
            elif isinstance(no, ast.Constant) and isinstance(no.value, str) and id(no) not in partes:
                yield no.value

    def test_nao_citam_execucao_da_ficha_enquanto_reservada(self):
        if "execucao" not in self.reservadas():
            return  # na 1.7.11 a seção vale, e os textos podem citá-la
        for nome in self.ARQUIVOS:
            with self.subTest(nome):
                self.assertNotIn("execucao[]", (SCRIPTS / nome).read_text(encoding="utf-8"))

    def test_toda_frase_sobre_o_que_e_da_1711_diz_1711(self):
        if "execucao" not in self.reservadas():
            return
        for nome in self.ARQUIVOS:
            for texto in self.textos(SCRIPTS / nome):
                for frase in " ".join(texto.split()).split(". "):
                    if any(p in frase.lower() for p in self.PALAVRAS):
                        with self.subTest(arquivo=nome, frase=frase[:120]):
                            self.assertIn("1.7.11", frase)

    def test_sem_caixa_manda_ao_terminal_do_titular(self):
        with mock.patch.object(EX.PERFIL, "sondar_bwrap", return_value=(None, "simulado")):
            with self.assertRaises(EX.Recusa) as ctx:
                EX.plano_do_perfil({}, ["./prog.sh"])  # a recusa vem antes de ler o perfil
        texto = str(ctx.exception)
        for termo in ("o titular roda o mesmo comando no terminal dele", "1.7.11", "simulado"):
            self.assertIn(termo, texto)
        self.assertNotIn("quem roda é o porteiro", texto)


# ------------------------------------------------------------------------------------------------ CI-F6
def _sem_caixa(ex):
    """O módulo da caixa com a sondagem recusada (o gatilho do achado: a caixa simples abre, a dos testes não)."""
    if hasattr(ex, "sondar_bwrap"):
        ex.sondar_bwrap = lambda: (None, "simulado: a caixa dos testes não abre aqui")
    if hasattr(ex, "PERFIL"):
        ex.PERFIL.sondar_bwrap = ex.sondar_bwrap
        ex.PERFIL.bwrap_monta_por_descritor = lambda caminho: False
    return ex


class TestCIF6CaixaPuladaNaoPassaVerde(unittest.TestCase):
    """Com FUNDACAO_CI_EXIGE_BWRAP=1 e a sondagem da caixa recusada, a sentinela e os testes da caixa falham (nenhum
    pula); sem a variável (fora da CI), os testes da caixa pulam como antes."""

    def rodar(self, classe, *, exige: bool) -> unittest.TestResult:
        resultado = unittest.TestResult()
        carregar_sentinela = sentinela.__dict__.get("carregar_execucao_isolada", lambda: carregar("execucao_isolada"))
        carregar_auditoria = testes_da_auditoria.carregar
        with mock.patch.dict(os.environ), \
                mock.patch.object(sentinela, "carregar_execucao_isolada", lambda: _sem_caixa(carregar_sentinela()),
                                  create=True), \
                mock.patch.object(testes_da_auditoria, "carregar", lambda nome: _sem_caixa(carregar_auditoria(nome))),\
                mock.patch.object(testes_do_perfil.EX, "sondar_bwrap",
                                  return_value=(None, "simulado: a caixa dos testes não abre aqui")):
            if exige:
                os.environ[VARIAVEL_CI] = "1"
            else:
                os.environ.pop(VARIAVEL_CI, None)
            unittest.TestLoader().loadTestsFromTestCase(classe).run(resultado)
        return resultado

    def test_na_ci_nenhum_teste_da_caixa_pula(self):
        for classe in (sentinela.TestSentinelaDaCaixa, testes_do_perfil.TestCaixaDeVerdade,
                       testes_da_auditoria.TestBubblewrapDeVerdade):
            with self.subTest(classe.__name__):
                resultado = self.rodar(classe, exige=True)
                self.assertGreater(resultado.testsRun, 0)
                self.assertEqual(resultado.skipped, [], "um teste da caixa pulou com a CI exigindo a caixa")
                self.assertFalse(resultado.wasSuccessful(), "a CI ficaria verde sem a caixa dos testes")

    def test_fora_da_ci_os_testes_da_caixa_pulam_como_antes(self):
        for classe in (sentinela.TestSentinelaDaCaixa, testes_do_perfil.TestCaixaDeVerdade,
                       testes_da_auditoria.TestBubblewrapDeVerdade):
            with self.subTest(classe.__name__):
                resultado = self.rodar(classe, exige=False)
                self.assertTrue(resultado.wasSuccessful(), resultado.failures + resultado.errors)
                self.assertEqual(len(resultado.skipped), resultado.testsRun)

    def test_o_passo_do_bubblewrap_da_ci_roda_a_sentinela(self):
        validar = SCRIPTS.parents[1] / ".github" / "workflows" / "validar.yml"
        if not validar.is_file():  # no pacote .skill o workflow não vai
            return
        texto = validar.read_text(encoding="utf-8")
        passo = texto.split("- name: bubblewrap e socat (Ubuntu)", 1)[1].split("- name:", 1)[0]
        self.assertIn("-p test_sentinela_ci.py", passo)  # a mesma sondagem dos testes, e não só a caixa simples
        self.assertIn("FUNDACAO_CI_EXIGE_BWRAP: ${{ matrix.os == 'ubuntu-latest' && '1' || '' }}", texto)


if __name__ == "__main__":
    unittest.main()
