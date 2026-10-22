"""Achados #8 e #10 da auditoria Codex Security da 1.7.6 (21/10/2026) no `atualizar_fundacao.py`, cada um com o
cenário de falha reproduzido. Pastas descartáveis; identidade de ensaio; nada no perfil nem numa fundação real.

#8: o `checar` importava o pacote da própria raiz (`python -m fundacao eventos verificar`, com a raiz como pasta
atual) e o ensaio descobria os testes na árvore viva (`unittest discover`): um módulo alterado ou um
`tests/test_*.py` plantado rodava antes de a raiz ser conferida. Agora o `checar` só lê (a cadeia de eventos é
conferida pelo kit da skill, com o banco aberto somente leitura); executável que nem o kit novo nem o registro da
instalação conhecem faz recusar antes de qualquer importação; e o ensaio roda os testes de cópias conferidas por
hash, com os módulos enumerados da lista, não da pasta.
#10: o `desfazer` aceitava em `copiados` e `substituidos` qualquer caminho dentro da raiz (o banco, a configuração de
registry/) e tratava o registro em evidence/ como plano autêntico. Agora toda categoria fica nas áreas de código do kit
e o registro só vale com a âncora que o `aplicar` grava em registry/atualizacoes.jsonl.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import ENV, SCRIPTS, SKILL, criar_ligacao_dir, rodar_script, versao_do_kit

IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"
LIVRO = Path("registry") / "atualizacoes.jsonl"
TESTE_DE_ORIGEM = '''import os
import unittest
from pathlib import Path


class TestOrigem(unittest.TestCase):
    def test_registra_de_onde_rodou(self):
        with open(os.environ["MARCADOR_ORIGEM"], "a", encoding="utf-8") as fh:
            fh.write(str(Path(__file__).resolve()) + "\\n")
'''


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def codigo_que_marca(marcador: Path) -> str:
    """Linhas que um atacante plantaria: gravam o marcador quando o módulo é importado ou executado."""
    return ("from pathlib import Path as _Marca\n"
            "_Marca(" + repr(str(marcador)) + ").write_text('rodou', encoding='utf-8')\n")


def user_version(db: Path) -> int:
    con = sqlite3.connect(db)
    try:
        return con.execute("PRAGMA user_version").fetchone()[0]
    finally:
        con.close()


class _Raiz(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="auditoria-176-atualizador-"))
        self.raiz, self.backups = self.base / "raiz", self.base / "backups"
        r = rodar_script("instalar_kit.py", "--destino", self.raiz)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = subprocess.run([sys.executable, "-B", "-m", "fundacao", "--raiz", str(self.raiz), "init", "--admin",
                            "titular-ensaio"], cwd=str(self.raiz), env=ENV, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.env = {**ENV, IDENTIDADE: "titular-ensaio"}

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def registrar_hash(self, rel: str) -> None:
        """O registro da instalação passa a ter o hash atual do arquivo, como se o kit anterior o tivesse instalado."""
        reg = self.raiz / "registry" / "kit_install.json"
        historico = json.loads(reg.read_text(encoding="utf-8"))
        historico[-1]["copiados"] = [i for i in historico[-1]["copiados"] if i["path"] != rel]
        historico[-1]["copiados"].append({"path": rel, "sha256": sha(self.raiz / rel)})
        reg.write_text(json.dumps(historico, ensure_ascii=False, indent=2), encoding="utf-8")

    def versao_antiga(self) -> None:
        """A raiz passa a declarar 1.0.0, com o hash registrado como se fosse a versão instalada."""
        init = self.raiz / "fundacao" / "__init__.py"
        atual = 'KIT_VERSION = "' + versao_do_kit(self.raiz) + '"'
        init.write_text(init.read_text(encoding="utf-8").replace(atual, 'KIT_VERSION = "1.0.0"'), encoding="utf-8")
        self.registrar_hash("fundacao/__init__.py")

    def atualizar(self, *args, script: Path | None = None, env: dict | None = None) -> tuple:
        script = script or SCRIPTS / "atualizar_fundacao.py"
        r = subprocess.run([sys.executable, "-B", str(script), *map(str, args)], env=env or self.env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        try:
            return r.returncode, json.loads(r.stdout)
        except ValueError:
            self.fail("saída não é JSON: " + r.stdout[-500:] + r.stderr[-500:])

    def foto(self) -> dict:
        return {p.relative_to(self.raiz).as_posix(): sha(p) for p in self.raiz.rglob("*")
                if p.is_file() and "state" not in p.relative_to(self.raiz).parts}


class TestChecarNaoExecutaCodigoDaRaiz(_Raiz):
    """#8: o `checar` não importa nem executa nada da raiz, nem quando o código alterado parece a versão instalada."""

    def plantar(self) -> dict:
        marcas = {nome: self.base / ("marcador-" + nome) for nome in ("init", "main")}
        init = self.raiz / "fundacao" / "__init__.py"
        init.write_text(init.read_text(encoding="utf-8") + "\n" + codigo_que_marca(marcas["init"]), encoding="utf-8")
        main = self.raiz / "fundacao" / "__main__.py"
        futuro = "from __future__ import annotations\n"
        main.write_text(main.read_text(encoding="utf-8").replace(futuro, futuro + codigo_que_marca(marcas["main"]), 1),
                        encoding="utf-8")
        return marcas

    def test_checar_nunca_importa_init_nem_main_da_raiz(self):
        marcas = self.plantar()
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 1, chk)
        self.assertEqual(sorted(a["path"] for a in chk["mudancas"]["alterados_localmente"]),
                         ["fundacao/__init__.py", "fundacao/__main__.py"])
        self.assertEqual([n for n, m in marcas.items() if m.exists()], [])        # nada da raiz rodou
        # O atacante acerta também o registro da instalação: a raiz parece "versão anterior" e pode ser aplicada,
        # mas o `checar` continua sem executar o código dela.
        for rel in ("fundacao/__init__.py", "fundacao/__main__.py"):
            self.registrar_hash(rel)
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 0, chk)
        self.assertEqual(sorted(chk["mudancas"]["atualizar"]), ["fundacao/__init__.py", "fundacao/__main__.py"])
        self.assertTrue(chk["cadeia_de_eventos"]["cadeia_integra"], chk)       # conferida sem importar a raiz
        self.assertEqual([n for n, m in marcas.items() if m.exists()], [])

    def test_checar_recusa_cadeia_de_eventos_adulterada(self):
        """A conferência da cadeia vale de fato: `eventos verificar` sai com código 0 mesmo com a cadeia quebrada,
        e o `checar` só recusava quando o comando falhava."""
        db = self.raiz / "state" / "state.sqlite"
        con = sqlite3.connect(db)
        try:
            con.execute("UPDATE event SET kind = kind || '-adulterado' WHERE seq = (SELECT MIN(seq) FROM event)")
            con.commit()
        finally:
            con.close()
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 1, chk)
        self.assertFalse(chk["cadeia_de_eventos"]["cadeia_integra"], chk)
        self.assertTrue(any("cadeia de eventos" in m for m in chk["motivos"]), chk["motivos"])


class TestExecutavelForaDoInventario(_Raiz):
    """#8: arquivo executável que nem o kit novo nem o registro da instalação conhecem faz recusar antes de qualquer
    descoberta ou importação; `__pycache__` e arquivo de dados a mais não recusam. Mudança de critério declarada na
    1.7.7 (revisão de segurança, R177-ATU-02): o `__pycache__` continua sem recusar, mas o `checar` o lista em
    `bytecode_a_apagar` e a promoção o apaga — antes ele era ignorado e o bytecode plantado ali rodava depois."""

    def test_teste_nao_rastreado_faz_o_aplicar_parar_antes_de_importar(self):
        self.versao_antiga()
        marcador = self.base / "marcador-teste"
        (self.raiz / "tests" / "test_evil.py").write_text(codigo_que_marca(marcador), encoding="utf-8")
        antes = self.foto()
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups,
                                   "--padrao-testes", "test_evil*.py")
        self.assertEqual((code, res.get("etapa")), (1, "checar"), res)
        self.assertEqual(res["checar"]["mudancas"]["executaveis_a_mais"], ["tests/test_evil.py"])
        self.assertTrue(any("executável" in m for m in res["checar"]["motivos"]), res["checar"]["motivos"])
        self.assertFalse(marcador.exists())                                    # não foi descoberto nem importado
        self.assertFalse(self.backups.exists())                                # parou antes do backup
        self.assertEqual(self.foto(), antes)

    def test_modulo_novo_no_pacote_e_bytecode_solto_fazem_o_checar_recusar(self):
        core = self.raiz / "fundacao" / "core"
        (core / "plantado.py").write_text("VALOR = 1\n", encoding="utf-8")
        (core / "solto.pyc").write_bytes(b"\x00" * 16)                         # bytecode fora do __pycache__
        (core / "__pycache__").mkdir(exist_ok=True)
        (core / "__pycache__" / "ids.cpython-312.pyc").write_bytes(b"\x00" * 16)  # derivado: não recusa (R177-ATU-02)
        (self.raiz / "templates" / "project" / "nota-do-titular.md").write_text("dado\n", encoding="utf-8")
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 1, chk)
        self.assertEqual(chk["mudancas"]["executaveis_a_mais"],
                         ["fundacao/core/plantado.py", "fundacao/core/solto.pyc"])
        self.assertTrue(any("executável" in m for m in chk["motivos"]), chk["motivos"])
        self.assertEqual(chk["mudancas"]["bytecode_a_apagar"], ["fundacao/core/__pycache__"])  # a promoção o apaga

    def test_ligacao_dentro_da_area_de_codigo_faz_o_checar_recusar(self):
        fora = self.base / "fora"
        fora.mkdir()
        (fora / "util.py").write_text("VALOR = 1\n", encoding="utf-8")
        criar_ligacao_dir(self.raiz / "fundacao" / "extra", fora)
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 1, chk)
        self.assertIn("fundacao/extra", chk["mudancas"]["por_ligacao"])


class TestCopiaConferida(unittest.TestCase):
    """#8: a cópia de onde o código roda leva só os arquivos conferidos, gravados dos bytes cujo hash foi conferido;
    troca ou executável novo depois da conferência recusam; os módulos de teste saem da lista, como no discover."""

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("codigo_conferido", SCRIPTS / "codigo_conferido.py")
        self.cc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cc)
        self.base = Path(tempfile.mkdtemp(prefix="copia-conferida-"))
        self.origem = self.base / "origem"
        for rel, texto in {"fundacao/__init__.py": "", "fundacao/a.py": "A = 1\n", "tests/test_x.py": "",
                           "tests/sub/__init__.py": "", "tests/sub/test_y.py": "", "tests/solta/test_z.py": "",
                           "tests/apoio.py": "", "registry/politica.json": "{}\n"}.items():
            (self.origem / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.origem / rel).write_text(texto, encoding="utf-8")
        (self.origem / "fundacao" / "__pycache__").mkdir()
        (self.origem / "fundacao" / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"\x00" * 16)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_copia_so_o_conferido_e_recusa_troca_depois_da_conferencia(self):
        cc = self.cc
        do_kit = {rel: sha(p) for rel, p in cc.percorrer(self.origem)[0].items()}
        inv = cc.inventario(self.origem, do_kit, {})
        self.assertEqual((inv["a_mais"], inv["alterados"], inv["ligacoes"]), ([], [], []))
        cc.preparar_copia(self.origem, inv["conferidos"], self.base / "copia", dados=("registry",))
        copiados = sorted(p.relative_to(self.base / "copia").as_posix() for p in (self.base / "copia").rglob("*")
                          if p.is_file())
        self.assertEqual(copiados, sorted([*inv["conferidos"], "registry/politica.json"]))   # sem __pycache__
        self.assertEqual(cc.modulos_de_teste(inv["conferidos"], "test*.py"), ["sub.test_y", "test_x"])
        (self.origem / "fundacao" / "a.py").write_text("A = 2\n", encoding="utf-8")         # troca depois
        with self.assertRaises(ValueError):
            cc.preparar_copia(self.origem, inv["conferidos"], self.base / "copia2")
        (self.origem / "fundacao" / "a.py").write_text("A = 1\n", encoding="utf-8")
        (self.origem / "tests" / "test_novo.py").write_text("", encoding="utf-8")            # executável novo
        with self.assertRaises(ValueError):
            cc.preparar_copia(self.origem, inv["conferidos"], self.base / "copia3")


class TestEnsaioEmCopiaConferida(_Raiz):
    """#8: os testes do ensaio rodam de cópias conferidas por hash (antes e depois), nunca da árvore viva da raiz."""

    def test_ensaio_roda_os_testes_de_copia_conferida(self):
        skill = self.base / "skill"
        shutil.copytree(SKILL, skill, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "evals"))
        for base in (skill / "assets" / "fundacao-kit", self.raiz):                 # teste que o kit novo também tem
            (base / "tests" / "test_local_origem.py").write_text(TESTE_DE_ORIGEM, encoding="utf-8")
        self.versao_antiga()
        marcador = self.base / "origens.txt"
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups, "--padrao-testes",
                                   "test_local_*.py", script=skill / "scripts" / "atualizar_fundacao.py",
                                   env={**self.env, "MARCADOR_ORIGEM": str(marcador)})
        self.assertEqual(code, 0, res)
        origens = [Path(linha) for linha in marcador.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(origens), 2, origens)                                # antes e depois da atualização
        raiz = self.raiz.resolve()
        self.assertEqual([o for o in origens if o.is_relative_to(raiz)], [])      # nenhum rodou da árvore viva
        self.assertEqual([o for o in origens if o.exists()], [])                  # as cópias foram apagadas


class TestDesfazerSoComPlanoAutentico(_Raiz):
    """#10: o `desfazer` só mexe nas áreas de código do kit e só aceita registro com a âncora gravada pelo `aplicar`."""

    def ancorar(self, arq: Path) -> None:
        """O atacante também acrescenta a âncora do registro forjado: a restrição das categorias vale sozinha."""
        livro = self.raiz / LIVRO
        with open(livro, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"registro": arq.relative_to(self.raiz).as_posix(), "sha256": sha(arq)}) + "\n")

    def test_desfazer_recusa_copiados_e_substituidos_fora_das_areas_de_codigo(self):
        db = self.raiz / "state" / "state.sqlite"
        politica = self.raiz / "registry" / "route_policy.json"
        guarda = self.raiz / "registry" / "kit_backup" / "forjado"
        (guarda / "registry").mkdir(parents=True)
        falsa = guarda / "registry" / "route_policy.json"
        falsa.write_text('{"task_routes": {}}\n', encoding="utf-8")
        reg = {"raiz": str(self.raiz), "user_version_antes": user_version(db),
               "promocao": {"instalar_kit": {
                   "backup_dos_substituidos": str(guarda), "orfaos_retirados": [],
                   "copiados": [{"path": "state/state.sqlite", "sha256": sha(db)}],
                   "substituidos": [{"path": "registry/route_policy.json", "sha256_anterior": sha(falsa),
                                     "sha256_novo": sha(politica)}]}}}
        arq = self.raiz / "evidence" / "atualizacoes" / "atualizacao-kit-9.9.9-forjado.json"
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(json.dumps(reg), encoding="utf-8")
        self.ancorar(arq)
        antes = (sha(db), sha(politica))
        code, res = self.atualizar("desfazer", "--registro", arq)
        self.assertEqual((code, res.get("etapa")), (1, "desfazer"), res)
        self.assertIn("áreas de código", res["motivo"])
        self.assertTrue(db.is_file())
        self.assertEqual((sha(db), sha(politica)), antes)

    def test_registro_alterado_depois_de_gravado_nao_vale(self):
        self.versao_antiga()
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups,
                                   "--padrao-testes", "test_nenhum_*.py")
        self.assertEqual(code, 0, res)
        arq = Path(res["registro"])
        linhas = [json.loads(linha) for linha in (self.raiz / LIVRO).read_text(encoding="utf-8").splitlines()]
        self.assertIn({"registro": arq.relative_to(self.raiz.resolve()).as_posix(), "sha256": sha(arq)},
                      [{k: item.get(k) for k in ("registro", "sha256")} for item in linhas])
        reg = json.loads(arq.read_text(encoding="utf-8"))
        alvo = self.raiz / "tests" / "helpers.py"
        reg["promocao"]["instalar_kit"]["copiados"].append({"path": "tests/helpers.py", "sha256": sha(alvo)})
        arq.write_text(json.dumps(reg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        versao = versao_do_kit(self.raiz)
        code, des = self.atualizar("desfazer", "--registro", arq)
        self.assertEqual((code, des.get("etapa")), (1, "desfazer"), des)
        self.assertIn("âncora", des["motivo"])
        self.assertTrue(alvo.is_file())
        self.assertEqual(versao_do_kit(self.raiz), versao)                         # nada foi devolvido


if __name__ == "__main__":
    unittest.main()
