"""Revisão de segurança da 1.7.7, terceira passada, na área do atualizador, cada achado com o cenário de falha
reproduzido. Pastas descartáveis; identidade de ensaio; nada no perfil nem numa fundação real.

R177C-B-03: o inventário do primeiro nível da raiz só reconhecia como pacote a pasta com `__init__` [R177B-B-06]. Uma
pasta `mcp/` sem `__init__`, com `server/__init__.py`, passava pelo `checar` e rodava no uso normal num ambiente sem o
SDK do MCP (`python -m fundacao.mcp_servidor` com a raiz como pasta atual): sem pacote comum `mcp` no caminho de
importação, o Python monta um pacote de namespace com a pasta da raiz. Agora a pasta (ou ligação) com o nome de um
módulo de primeiro nível que o kit importa de fora da biblioteca padrão (`IMPORTADOS_DE_FORA`, que este teste confere
pela árvore sintática do kit) entra no inventário mesmo sem `__init__`, comparada sem caixa; as demais pastas do
primeiro nível sem `__init__` continuam fora dele.
R177C-B-04: o `instalar_kit.py` que saía com código 3 depois da promoção (registro da instalação não gravado ou
composição divergente) fazia o `aplicar` parar sem guardar nem ancorar o registro da promoção: a raiz ficava no kit
novo, com o `__pycache__`, e o `desfazer` recusava por falta de âncora. Agora, sem `nada_escrito` na saída do
instalador, o `aplicar` apaga o `__pycache__` e grava e ancora o registro, com a promoção marcada como interrompida,
antes de parar; com `nada_escrito`, para como antes; sem saída legível (o instalador caiu), não há plano para o
`desfazer`: o `__pycache__` sai, o registro fica sem âncora e a mensagem manda à cópia ANTES (C9). O instalador caía
justamente com o registry/kit_install.json ilegível ou trocado (JSON ou UTF-8 inválido, aninhamento que estoura a
pilha, conteúdo que não é lista): agora isso vira `registro_nao_gravado`, e o `aplicar` cai no ramo com plano e âncora.
Quarta passada (R177D-5): a saída 5 com `desfeito` e composição `nao_alterada` (o instalador desfez a promoção que
falhou) conta como `nada_escrito`: sem âncora, sem tocar a raiz, com a mensagem de que ela não foi alterada.
Comandos para colar (limite 4 do relatório): os "Para voltar" traziam só o nome do script e o caminho do registro sem
aspas; colados no PowerShell de outra pasta, o script não era achado, e o caminho com espaço (como o da raiz do
titular) se partia. Agora todo comando que o atualizador sugere vem com `python`, o caminho completo do
script e os caminhos entre aspas duplas; os testes o colam como texto no PowerShell e no bash, de outra pasta.
"""

from __future__ import annotations

import ast
import base64
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

from apoio import ENV, KIT, SCRIPTS, SKILL, criar_ligacao_dir, rodar_script, versao_do_kit
from test_auditoria_1_7_6_atualizador import IDENTIDADE, LIVRO, _Raiz, codigo_que_marca, sha

AREAS = ("fundacao", "templates", "tests")


def carregar(nome: str):
    """Módulo dos scripts carregado pelo caminho (como nos testes das passadas anteriores)."""
    spec = importlib.util.spec_from_file_location(nome + "_177c", SCRIPTS / (nome + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def importados_de_fora(pacote: Path) -> set:
    """Nomes de primeiro nível que os fontes de `pacote` importam de fora da biblioteca padrão e do próprio pacote,
    lidos pela árvore sintática, sem executar nada: `import x`, `from x import y` e `importlib.import_module("x")` ou
    `__import__("x")` com o nome constante. Importação relativa é do próprio pacote."""
    nomes = set()
    for arq in sorted(Path(pacote).rglob("*.py")):
        if "__pycache__" in arq.parts:
            continue
        for no in ast.walk(ast.parse(arq.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Import):
                nomes |= {a.name.split(".")[0] for a in no.names}
            elif isinstance(no, ast.ImportFrom) and no.level == 0 and no.module:
                nomes.add(no.module.split(".")[0])
            elif isinstance(no, ast.Call) and no.args and isinstance(no.args[0], ast.Constant) \
                    and isinstance(no.args[0].value, str) and (getattr(no.func, "attr", None) == "import_module"
                                                               or getattr(no.func, "id", None) == "__import__"):
                nomes.add(no.args[0].value.split(".")[0])
    return {n for n in nomes if n not in sys.stdlib_module_names and n != Path(pacote).name}


class TestImportadosDeForaDoKit(unittest.TestCase):
    """R177C-B-03: a lista de nomes do inventário é a que os fontes do kit importam; se o kit passar a importar outro
    pacote de fora da biblioteca padrão, este teste para até a lista acompanhar (não diverge em silêncio)."""

    def test_detector_contra_trechos(self):
        base = Path(tempfile.mkdtemp(prefix="importados-de-fora-"))
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        (base / "pacote" / "sub").mkdir(parents=True)
        (base / "pacote" / "a.py").write_text("import json, requests\nfrom mcp.server import x\nfrom . import b\n"
                                              "from .sub import c\nimport pacote.sub\n", encoding="utf-8")
        (base / "pacote" / "sub" / "c.py").write_text("import importlib\nimportlib.import_module('yaml.loader')\n"
                                                      "__import__('toml')\nimportlib.import_module(nome)\n",
                                                      encoding="utf-8")
        self.assertEqual(importados_de_fora(base / "pacote"), {"requests", "mcp", "yaml", "toml"})

    def test_constante_bate_com_os_fontes_do_kit(self):
        cc = carregar("codigo_conferido")
        self.assertEqual(importados_de_fora(KIT / "fundacao"), set(cc.IMPORTADOS_DE_FORA))
        self.assertEqual([n for n in cc.IMPORTADOS_DE_FORA if n != n.lower()], [])  # comparada sem caixa


class TestNamespaceDoMcpNaRaiz(_Raiz):
    """R177C-B-03, o cenário do achado: `mcp/server/__init__.py` plantado na raiz, sem `mcp/__init__.py`."""

    def importar_sem_sdk(self) -> None:
        """O que o servidor MCP fazia sem o SDK no caminho (`python -S`: sem site-packages), com a raiz como pasta
        atual: `import mcp.server` monta o pacote de namespace com a pasta da raiz."""
        subprocess.run([sys.executable, "-E", "-S", "-B", "-c", "import mcp.server"], cwd=str(self.raiz), env=ENV,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)

    def test_pasta_mcp_sem_init_faz_o_checar_recusar(self):
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 0, chk)                                            # controle: a raiz do instalador passa
        marcador = self.base / "marcador-mcp"
        (self.raiz / "mcp" / "server").mkdir(parents=True)
        (self.raiz / "mcp" / "server" / "__init__.py").write_text(codigo_que_marca(marcador), encoding="utf-8")
        self.importar_sem_sdk()
        if not marcador.exists():
            self.skipTest("há um pacote mcp comum fora do site neste Python: o namespace não vence aqui")
        marcador.unlink()                                                         # controle: o plantado roda
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 1, chk)
        self.assertEqual(chk["mudancas"]["executaveis_a_mais"], ["mcp/server/__init__.py"])
        self.assertTrue(any("primeiro nível da raiz" in m and "mcp" in m for m in chk["motivos"]), chk["motivos"])
        self.assertFalse(marcador.exists())                                       # o `checar` não o importou
        self.versao_antiga()
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups,
                                   "--padrao-testes", "test_nenhum_*.py")
        self.assertEqual((code, res.get("etapa")), (1, "checar"), res)
        self.assertFalse(self.backups.exists())                                   # parou antes do backup


class TestInventarioDoNamespace(unittest.TestCase):
    """R177C-B-03: variantes no inventário (sem caixa, módulo solto na pasta, ligação) e as pastas comuns do primeiro
    nível sem `__init__` (como as da raiz real: ci/, ferramentas/, plugins/, prototipos/) continuam sem recusar."""

    def setUp(self):
        self.cc = carregar("codigo_conferido")
        self.base = Path(tempfile.mkdtemp(prefix="namespace-mcp-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.raiz = self.base / "raiz"
        (self.raiz / "fundacao").mkdir(parents=True)

    def plantar(self, arquivos: dict) -> None:
        for rel, texto in arquivos.items():
            (self.raiz / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.raiz / rel).write_text(texto, encoding="utf-8")

    def inventario(self) -> dict:
        return self.cc.inventario(self.raiz, {}, {})

    def test_pastas_comuns_sem_init_nao_recusam(self):
        self.plantar({"ci/gerar.py": "A = 1\n", "ferramentas/util.py": "A = 1\n", "plugins/p/x.py": "A = 1\n",
                      "prototipos/a.py": "A = 1\n", "mcpx/b.py": "A = 1\n", "mcp-notas/c.py": "A = 1\n",
                      "mcp/LEIA-ME.md": "dado\n", "mcp/__pycache__/server.cpython-312.pyc": "\x00"})
        inv = self.inventario()
        self.assertEqual((inv["a_mais"], inv["ligacoes"]), ([], []))

    def test_sem_caixa_e_modulo_solto_na_pasta(self):
        self.plantar({"MCP/server/__init__.py": "A = 1\n", "MCP/server/mcpserver/exceptions.py": "A = 1\n",
                      "MCP/util.pyc": "\x00", "MCP/server/LEIA-ME.md": "dado\n"})
        self.assertEqual(self.inventario()["a_mais"],
                         ["MCP/server/__init__.py", "MCP/server/mcpserver/exceptions.py", "MCP/util.pyc"])

    def test_ligacao_com_o_nome_ou_dentro_da_pasta_recusa(self):
        fora = self.base / "fora"
        (fora / "server").mkdir(parents=True)
        (fora / "server" / "__init__.py").write_text("A = 1\n", encoding="utf-8")
        criar_ligacao_dir(self.raiz / "mcp", fora)
        inv = self.inventario()
        self.assertEqual((inv["a_mais"], inv["ligacoes"]), ([], ["mcp"]))       # sem seguir a ligação
        self.remover(self.raiz / "mcp")
        (self.raiz / "mcp").mkdir()
        criar_ligacao_dir(self.raiz / "mcp" / "server", fora / "server")
        inv = self.inventario()
        self.assertEqual((inv["a_mais"], inv["ligacoes"]), ([], ["mcp/server"]))
        self.assertTrue((fora / "server" / "__init__.py").is_file())            # o alvo ficou intacto

    @staticmethod
    def remover(ligacao: Path) -> None:
        try:
            ligacao.unlink()
        except OSError:
            ligacao.rmdir()  # junção do Windows: sai o nome, o alvo fica


HISTORICOS_TROCADOS = {
    "JSON inválido": b"{nao e json",
    "UTF-8 inválido": b"[\"\xff\xfe\"]",
    "com BOM": "\ufeff[]".encode("utf-8"),
    "objeto": b"{}",
    "nulo": b"null",
    "texto": b"\"texto\"",
    "número": b"42",
    "aninhamento fundo": b"[" * 100000 + b"]" * 100000,
    "inteiro longo demais": b"[" + b"1" * 5000 + b"]",
}


class TestHistoricoDaInstalacaoTrocado(unittest.TestCase):
    """R177C-B-04, limite 1 do relatório: o registry/kit_install.json ilegível ou trocado não derruba quem o lê nem é
    refeito por quem grava; o `registrar` do instalador devolve o motivo (vira `registro_nao_gravado`)."""

    def setUp(self):
        self.ik, self.af, self.ra = carregar("instalar_kit"), carregar("atualizar_fundacao"), carregar(
            "registro_atualizacao")
        self.base = Path(tempfile.mkdtemp(prefix="historico-trocado-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        (self.base / "registry").mkdir()
        self.reg = self.base / "registry" / "kit_install.json"

    def test_historico_trocado_nao_e_gravado_nem_derruba_a_leitura(self):
        for nome, conteudo in HISTORICOS_TROCADOS.items():
            with self.subTest(nome):
                self.reg.write_bytes(conteudo)
                motivo = self.ik.registrar(self.base, {"ensaio": True})
                self.assertTrue(isinstance(motivo, str) and motivo, motivo)
                self.assertEqual(self.reg.read_bytes(), conteudo)               # nem refeito nem acrescido
                self.assertEqual(self.ik.instalados_antes(self.base), {})        # o plano lê como sem histórico
                self.assertEqual(self.af.hashes_instalados(self.base), {})      # o `checar`, idem
                volta = self.ra._registrar_volta(self.base, {}, [], "registro.json", "1.0.0")
                self.assertNotEqual(volta, "atualizado")                        # o `desfazer` avisa, não cai
                self.assertEqual(self.reg.read_bytes(), conteudo)

    def test_historico_valido_continua_acrescido(self):
        self.reg.write_text("[]", encoding="utf-8")
        self.assertIsNone(self.ik.registrar(self.base, {"ensaio": True}))
        self.assertEqual(json.loads(self.reg.read_text(encoding="utf-8")), [{"ensaio": True}])


class TestFonteSemCaractereInvisivel(unittest.TestCase):
    """R177D-6 (quarta passada): o BOM literal entrou num teste desta passada. Caractere de controle (fora o tab e a
    quebra de linha) ou de formatação (BOM, inversão de direção e afins) literal num fonte não aparece na revisão; nos
    `.py` da skill ele vai por escape, nunca literal. Lidos os bytes, para o retorno de carro não sumir na leitura."""

    def test_nenhum_py_da_skill_tem_caractere_invisivel_literal(self):
        achados = []
        for arq in sorted(SKILL.rglob("*.py")):
            if "__pycache__" in arq.parts:
                continue
            for n, linha in enumerate(arq.read_bytes().decode("utf-8").split("\n"), 1):
                achados += [arq.relative_to(SKILL).as_posix() + ":" + str(n) + ": U+" + format(ord(c), "04X")
                            for c in linha if c != "\t" and unicodedata.category(c) in ("Cc", "Cf")]
        self.assertEqual(achados, [])


SUBSTITUTO_REGISTRO = '''

_registrar_original = registrar


def registrar(dest, record):  # substituto do teste: na raiz, o registro da instalação não é gravado (código 3)
    if Path(dest) == Path(os.environ["RAIZ_REAL"]).resolve():
        return "simulado pelo teste: ligação no lugar do registro"
    return _registrar_original(dest, record)
'''

SUBSTITUTO_SEM_SAIDA = '''

_registrar_original = registrar


def registrar(dest, record):  # substituto do teste: na raiz, o instalador cai depois de promover, sem saída JSON
    if Path(dest) == Path(os.environ["RAIZ_REAL"]).resolve():
        raise RuntimeError("simulado pelo teste: queda depois da promoção")
    return _registrar_original(dest, record)
'''

SUBSTITUTO_HISTORICO_TROCADO = '''

_registrar_original = registrar


def registrar(dest, record):  # substituto do teste: o histórico da raiz é trocado logo antes do registro da promoção
    if Path(dest) == Path(os.environ["RAIZ_REAL"]).resolve():
        (Path(dest) / "registry" / "kit_install.json").write_text("{trocado", encoding="utf-8")
    return _registrar_original(dest, record)
'''

SUBSTITUTO_PROMOCAO_DESFEITA = '''

_promover_original = promover


def promover(dest, plano, carimbo):  # substituto do teste: na raiz, a troca do 2º arquivo falha (arquivo preso, como
    # pelo antivírus), e o próprio instalador desfaz a promoção (código 5, desfeito)
    if Path(dest) != Path(os.environ["RAIZ_REAL"]).resolve():
        return _promover_original(dest, plano, carimbo)
    trocar, trocados = os.replace, []

    def trocar_ate_prender(origem, alvo):
        trocados.append(alvo)
        if len(trocados) == 2:
            raise PermissionError(13, "arquivo em uso por outro processo (simulado pelo teste)", str(alvo))
        return trocar(origem, alvo)

    os.replace = trocar_ate_prender
    try:
        return _promover_original(dest, plano, carimbo)
    finally:
        os.replace = trocar
'''

SUBSTITUTO_NADA_ESCRITO = '''

_main_original = main


def main():  # substituto do teste: na raiz, sai com código 3 sem gravar nada
    destino = Path(sys.argv[sys.argv.index("--destino") + 1]).resolve()
    if destino == Path(os.environ["RAIZ_REAL"]).resolve():
        print(json.dumps({"composicao": "nao_alterada", "atualizacao_incompleta": True, "nada_escrito": True,
                          "acao_necessaria": "simulado pelo teste"}))
        return 3
    return _main_original()
'''


class TestPromocaoInterrompidaPeloInstalador(_Raiz):
    """R177C-B-04: o instalador sai com código 3 na promoção; o `aplicar` para com o registro ancorado se algo foi
    gravado, e o `desfazer` devolve o código anterior. Sem saída legível, a volta é a cópia ANTES (C9)."""

    def skill_com_instalador(self, substituto: str) -> Path:
        """Cópia da skill com o `instalar_kit.py` trocado pelo substituto só na raiz real (o ensaio usa o original)."""
        skill = self.base / "skill"
        shutil.copytree(SKILL, skill, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "evals"))
        ik = skill / "scripts" / "instalar_kit.py"
        texto = ik.read_text(encoding="utf-8")
        self.assertIn('\nif __name__ == "__main__":', texto)
        ik.write_text(texto.replace('\nif __name__ == "__main__":', substituto + '\n\nif __name__ == "__main__":', 1),
                      encoding="utf-8")
        return skill / "scripts" / "atualizar_fundacao.py"

    def codigo(self) -> dict:
        return {rel: h for rel, h in self.foto().items() if rel.split("/")[0] in AREAS and "__pycache__" not in rel}

    def ancorados(self) -> list:
        livro = self.raiz / LIVRO
        linhas = livro.read_text(encoding="utf-8").splitlines() if livro.is_file() else []
        return [(item.get("registro"), item.get("sha256")) for item in map(json.loads, linhas)]

    def preparar(self) -> Path:
        """Versão anterior na raiz, um arquivo do kit a copiar e bytecode plantado (não conferido)."""
        self.versao_antiga()
        (self.raiz / "tests" / "helpers.py").unlink()
        pycache = self.raiz / "fundacao" / "core" / "__pycache__"
        pycache.mkdir()
        (pycache / "ids.cpython-312.pyc").write_bytes(b"\x00" * 16)
        return pycache

    def test_saida_3_depois_da_promocao_ancora_o_registro_e_o_desfazer_volta(self):
        script = self.skill_com_instalador(SUBSTITUTO_REGISTRO)
        pycache = self.preparar()
        antes = self.codigo()
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups, "--padrao-testes",
                                   "test_nenhum_*.py", script=script, env={**self.env, "RAIZ_REAL": str(self.raiz)})
        self.assertEqual((code, res.get("etapa")), (1, "instalar_kit"), res)
        self.assertEqual((res["codigo"], res["saida"]["composicao"]), (3, "verificada"))
        self.assertIn("simulado pelo teste", res["saida"]["registro_nao_gravado"])
        self.assertNotIn("nada_escrito", res["saida"])
        self.assertEqual(versao_do_kit(self.raiz), versao_do_kit(KIT))           # a promoção aconteceu
        arq = Path(res["registro"])
        self.assertIn((arq.relative_to(self.raiz.resolve()).as_posix(), sha(arq)), self.ancorados())
        reg = json.loads(arq.read_text(encoding="utf-8"))
        self.assertIn("interrompida", reg["promocao"])
        self.assertEqual(reg["promocao"]["instalar_kit"]["composicao"], "verificada")
        self.assertEqual(reg["promocao"]["bytecode_apagado"], ["fundacao/core/__pycache__"])
        self.assertFalse(pycache.exists())                                       # como na promoção normal
        self.assertEqual(res["para_voltar"],                                     # pronto para colar (limite 4)
                         'python "' + str(script.resolve()) + '" desfazer --registro "' + res["registro"] + '"')
        code, des = self.atualizar("desfazer", "--registro", arq)
        self.assertEqual(code, 0, des)
        self.assertEqual(versao_do_kit(self.raiz), "1.0.0")
        self.assertEqual(self.codigo(), antes)                                   # o código anterior, arquivo a arquivo
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 0, chk)                                           # e a raiz volta a ser atualizável
        self.assertEqual((chk["mudancas"]["atualizar"], chk["mudancas"]["copiar"]),
                         (["fundacao/__init__.py"], ["tests/helpers.py"]))

    def test_historico_trocado_na_promocao_ancora_o_registro_e_o_desfazer_volta(self):
        """Limite 1 do relatório: com o histórico trocado antes do registro da promoção, o instalador caía sem saída e o
        `aplicar` ia para o ramo sem plano; agora sai com `registro_nao_gravado` e o registro fica ancorado."""
        script = self.skill_com_instalador(SUBSTITUTO_HISTORICO_TROCADO)
        pycache = self.preparar()
        antes = self.codigo()
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups, "--padrao-testes",
                                   "test_nenhum_*.py", script=script, env={**self.env, "RAIZ_REAL": str(self.raiz)})
        self.assertEqual((code, res.get("etapa"), res.get("codigo")), (1, "instalar_kit", 3), res)
        self.assertEqual(res["saida"]["composicao"], "verificada")
        self.assertIn("JSONDecodeError", res["saida"]["registro_nao_gravado"])
        arq = Path(res["registro"])
        self.assertIn((arq.relative_to(self.raiz.resolve()).as_posix(), sha(arq)), self.ancorados())
        self.assertFalse(pycache.exists())
        code, des = self.atualizar("desfazer", "--registro", arq)
        self.assertEqual(code, 0, des)
        self.assertEqual((versao_do_kit(self.raiz), self.codigo()), ("1.0.0", antes))
        self.assertIn("JSONDecodeError", des["registro_da_instalacao"])           # o histórico trocado fica como está
        self.assertEqual((self.raiz / "registry" / "kit_install.json").read_text(encoding="utf-8"), "{trocado")

    def test_saida_3_com_nada_escrito_para_como_antes(self):
        script = self.skill_com_instalador(SUBSTITUTO_NADA_ESCRITO)
        pycache = self.preparar()
        antes = self.codigo()
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups, "--padrao-testes",
                                   "test_nenhum_*.py", script=script, env={**self.env, "RAIZ_REAL": str(self.raiz)})
        self.assertEqual((code, res.get("etapa")), (1, "instalar_kit"), res)
        self.assertTrue(res["saida"]["nada_escrito"])
        arq = Path(res["registro"])
        self.assertNotIn(arq.relative_to(self.raiz.resolve()).as_posix(), [r for r, _h in self.ancorados()])
        self.assertNotIn("promocao", json.loads(arq.read_text(encoding="utf-8")))
        self.assertNotIn("para_voltar", res)
        self.assertEqual((versao_do_kit(self.raiz), self.codigo()), ("1.0.0", antes))  # a raiz não foi alterada
        self.assertTrue(pycache.is_dir())

    def test_saida_5_desfeita_pelo_instalador_para_sem_tocar_a_raiz(self):
        """R177D-5 (quarta passada): a troca de um arquivo falhou (preso, como pelo antivírus) e o próprio instalador
        desfez a promoção (código 5, `desfeito`, composição `nao_alterada`): o código da raiz é o de antes. O `aplicar`
        ancorava o registro e mandava ao `desfazer`, que recusava (o código já era o anterior) e mandava à cópia ANTES;
        agora para como com `nada_escrito`, sem âncora, sem `para_voltar` e sem apagar o `__pycache__`, e diz isso."""
        script = self.skill_com_instalador(SUBSTITUTO_PROMOCAO_DESFEITA)
        pycache = self.preparar()
        antes = self.codigo()
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups, "--padrao-testes",
                                   "test_nenhum_*.py", script=script, env={**self.env, "RAIZ_REAL": str(self.raiz)})
        self.assertEqual((code, res.get("etapa"), res.get("codigo")), (1, "instalar_kit", 5), res)
        self.assertEqual((res["saida"]["desfeito"], res["saida"]["composicao"]), (True, "nao_alterada"))
        self.assertIn("simulado pelo teste", " ".join(res["saida"]["erros"]))     # o arquivo preso
        self.assertEqual((versao_do_kit(self.raiz), self.codigo()), ("1.0.0", antes))  # o instalador desfez
        arq = Path(res["registro"])
        self.assertNotIn(arq.relative_to(self.raiz.resolve()).as_posix(), [r for r, _h in self.ancorados()])
        self.assertNotIn("promocao", json.loads(arq.read_text(encoding="utf-8")))
        self.assertNotIn("para_voltar", res)
        self.assertTrue(pycache.is_dir())                                         # sem tocar a raiz
        self.assertIn("NÃO foi alterado", res["motivo"])

    def test_queda_sem_saida_depois_da_promocao_manda_a_copia_antes(self):
        """Sem a saída do instalador não há plano para o `desfazer`: registro sem âncora, a mensagem manda à cópia
        ANTES (C9), e o `__pycache__` sai, porque a raiz pode ter ficado com o código novo."""
        script = self.skill_com_instalador(SUBSTITUTO_SEM_SAIDA)
        pycache = self.preparar()
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups, "--padrao-testes",
                                   "test_nenhum_*.py", script=script, env={**self.env, "RAIZ_REAL": str(self.raiz)})
        self.assertEqual((code, res.get("etapa"), res["saida"]), (1, "instalar_kit", None), res)
        self.assertIn("simulado pelo teste", res["erro"])                       # caiu depois de promover
        self.assertEqual(versao_do_kit(self.raiz), versao_do_kit(KIT))
        self.assertIn("cópia ANTES numa pasta nova (C9)", res["motivo"])
        self.assertEqual(res["bytecode_apagado"], ["fundacao/core/__pycache__"])
        self.assertFalse(pycache.exists())
        arq = Path(res["registro"])
        self.assertNotIn(arq.relative_to(self.raiz.resolve()).as_posix(), [r for r, _h in self.ancorados()])
        self.assertNotIn("para_voltar", res)


def shells_do_titular() -> dict:
    """Onde o titular cola o comando, os que houver aqui: o PowerShell (o do Windows ou o pwsh) e o bash (no Windows,
    o do Git: o bash.exe do System32 é o do WSL, que não vê os caminhos do Windows)."""
    achados = {}
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell:
        achados["PowerShell"] = powershell
    bash = shutil.which("bash")
    if os.name == "nt":
        if bash and Path(bash).resolve().is_relative_to(Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve()):
            bash = None
        git = shutil.which("git")
        if not bash and git:
            bash = next((str(p / "bin" / "bash.exe") for p in Path(git).resolve().parents
                         if (p / "bin" / "bash.exe").is_file()), None)
    if bash:
        achados["bash"] = bash
    return achados


SONDA = """import json, sys
from pathlib import Path
Path(sys.argv[0]).with_name("argv-recebido.json").write_text(json.dumps(sys.argv, ensure_ascii=False),
                                                              encoding="utf-8")
"""


class _Colar:
    """O comando sugerido colado como texto no shell, de uma pasta que não é a do script: no PowerShell pelo
    `-EncodedCommand` e no bash pela entrada, sem nenhuma citação a mais no meio do caminho."""

    def ambiente_do_shell(self) -> dict:
        """O `python` que o shell acha primeiro é este interpretador (o comando sugerido começa por `python`)."""
        pasta = Path(sys.executable).parent
        if not (pasta / ("python.exe" if os.name == "nt" else "python")).is_file():
            pasta = self.base / "python no caminho"
            pasta.mkdir(exist_ok=True)
            if not (pasta / "python").exists():
                (pasta / "python").symlink_to(sys.executable)
        return {**getattr(self, "env", ENV), "PATH": str(pasta) + os.pathsep + os.environ.get("PATH", "")}

    def colar(self, shell: str, texto: str) -> subprocess.CompletedProcess:
        outra = self.base / "outra pasta de trabalho"
        outra.mkdir(exist_ok=True)
        programa = shells_do_titular()[shell]
        if shell == "PowerShell":
            codigo = base64.b64encode(texto.encode("utf-16-le")).decode("ascii")
            cmd, entrada = [programa, "-NoProfile", "-NonInteractive", "-EncodedCommand", codigo], None
        else:
            cmd, entrada = [programa], (texto + "\n").encode("utf-8")
        return subprocess.run(cmd, input=entrada, cwd=str(outra), env=self.ambiente_do_shell(), capture_output=True,
                              timeout=600)

    def conferir_colado(self, texto: str, script: Path, argumentos: list) -> None:
        """Em cada shell, o comando colado chega ao script (a sonda no lugar dele) com cada caminho inteiro."""
        shells = shells_do_titular()
        if not shells:
            self.skipTest("nem PowerShell nem bash neste ambiente")
        real, recebido = script.read_bytes(), script.with_name("argv-recebido.json")
        try:
            script.write_text(SONDA, encoding="utf-8")
            for shell in shells:
                with self.subTest(shell):
                    recebido.unlink(missing_ok=True)
                    r = self.colar(shell, texto)
                    self.assertTrue(recebido.is_file(), shell + ": o script não foi achado ou não rodou: "
                                    + (r.stdout + r.stderr).decode("utf-8", "replace")[-600:])
                    self.assertEqual(json.loads(recebido.read_text(encoding="utf-8")), [str(script), *argumentos])
        finally:
            script.write_bytes(real)
            recebido.unlink(missing_ok=True)


def depois_de(resumo: list, prefixo: str) -> str:
    """O comando da única linha do resumo que começa por `prefixo`."""
    linhas = [linha for linha in resumo if linha.startswith(prefixo)]
    assert len(linhas) == 1, resumo
    return linhas[0][len(prefixo):]


class TestCitacaoDosCaminhos(_Colar, unittest.TestCase):
    """Limite 4: o caminho vai entre aspas duplas só quando nenhum dos dois shells o interpreta lá dentro, e o
    formato do `comando` chega inteiro ao script nos dois, com os caracteres que um nome de pasta costuma ter."""

    def setUp(self):
        self.af = carregar("atualizar_fundacao")
        self.base = Path(tempfile.mkdtemp(prefix="citacao-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)

    def test_citar_recusa_o_que_o_shell_interpretaria_entre_aspas(self):
        for ruim in ('a"b', "a\u201cb", "a\u201db", "a\u201eb", "a$b", "a`b", "a!b", "a\nb", "a\rb", "a\tb",
                     "\\\\servidor\\pasta", "C:\\pasta\\"):
            with self.subTest(repr(ruim)), self.assertRaises(ValueError):
                self.af.citar(ruim)
        aviso = self.af.comando(Path("x.py"), "desfazer", "--registro", Path("a$b"))
        self.assertTrue(aviso.startswith("(comando não montado"), aviso)

    def test_comando_chega_inteiro_com_espaco_acento_e_pontuacao(self):
        pasta = self.base / "Área de trabalho (cópia) d'Ávila & cia; 100% #1 [x] {y} @z, a=b+c ~ ^"
        pasta.mkdir()
        sonda, alvo = pasta / "sonda.py", pasta / "registro com espaço.json"
        sonda.write_text("", encoding="utf-8")
        texto = self.af.comando(sonda, "desfazer", "--registro", alvo)
        self.assertEqual(texto, 'python "' + str(sonda.resolve()) + '" desfazer --registro "' + str(alvo) + '"')
        self.conferir_colado(texto, sonda.resolve(), ["desfazer", "--registro", str(alvo)])

    def test_os_demais_comandos_trazem_o_script_inteiro_e_os_caminhos_entre_aspas(self):
        af, raiz = self.af, self.base.resolve() / "raiz da fundação"
        q = lambda caminho: '"' + str(caminho) + '"'  # noqa: E731
        [host] = af._resumo_host(raiz, {"conferido": False, "motivo": "ensaio"})
        self.assertTrue(host.endswith(" ".join(["python", q(af.INVENTARIAR_HOST), "verificar", "--inventario",
                                                q(raiz / af.INVENTARIO_HOST), "--raiz", q(raiz)])), host)
        [mudou] = af._resumo_host(raiz, {"conferido": True, "sem_mudancas": False, "mudancas": {"skills": 1}})
        self.assertTrue(mudou.endswith(" ".join(["python", q(af.INVENTARIAR_HOST), "gravar", "--saida",
                                                 q(raiz / af.INVENTARIO_HOST), "--raiz", q(raiz), "--substituir"])),
                        mudou)
        [conflito] = af._resumo_instrucoes(raiz, {"conflito": "escrito à mão"})
        self.assertTrue(conflito.endswith(" ".join(["python", q(af.INSTRUCOES_RAIZ), "gerar", "--raiz", q(raiz),
                                                    "--adotar"])), conflito)
        [erro] = af._resumo_instrucoes(raiz, {"erro": "ensaio"})
        self.assertTrue(erro.endswith(" ".join(["python", q(af.INSTRUCOES_RAIZ), "gerar", "--raiz", q(raiz)])), erro)


class TestComandoProntoParaColar(_Colar, _Raiz):
    """Limite 4, o cenário: raiz e skill em pastas com espaço e acento; o "Para voltar" do resumo, colado como texto
    de outra pasta, chega ao script com os caminhos inteiros e volta a raiz."""

    def setUp(self):  # como o do `_Raiz`, com espaço e acento em todo o caminho
        self.base = Path(tempfile.mkdtemp(prefix="comando pronto-"))
        self.raiz, self.backups = self.base / "raiz da fundação", self.base / "cópias de segurança"
        r = rodar_script("instalar_kit.py", "--destino", self.raiz)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = subprocess.run([sys.executable, "-B", "-m", "fundacao", "--raiz", str(self.raiz), "init", "--admin",
                            "titular-ensaio"], cwd=str(self.raiz), env=ENV, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.env = {**ENV, IDENTIDADE: "titular-ensaio"}
        skill = self.base / "skill com espaço"
        shutil.copytree(SKILL, skill, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "evals"))
        self.script = (skill / "scripts" / "atualizar_fundacao.py").resolve()

    def aplicar(self) -> dict:
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups, "--padrao-testes",
                                   "test_nenhum_*.py", script=self.script)
        self.assertEqual(code, 0, res)
        return res

    def voltar(self, texto: str) -> None:
        """O comando de verdade (o script real de volta no lugar), colado no primeiro shell."""
        shell = next(iter(shells_do_titular()))
        r = self.colar(shell, texto)
        self.assertEqual(r.returncode, 0, shell + ": " + (r.stdout + r.stderr).decode("utf-8", "replace")[-800:])

    def test_para_voltar_o_codigo_colado_de_outra_pasta(self):
        self.versao_antiga()
        antes = {rel: h for rel, h in self.foto().items() if rel.split("/")[0] in AREAS}
        res = self.aplicar()
        texto = depois_de(res["resumo"], "Para voltar o código: ")
        self.conferir_colado(texto, self.script, ["desfazer", "--registro", res["registro"]])
        self.assertEqual(texto, 'python "' + str(self.script) + '" desfazer --registro "' + res["registro"] + '"')
        self.voltar(texto)
        self.assertEqual(versao_do_kit(self.raiz), "1.0.0")
        self.assertEqual({rel: h for rel, h in self.foto().items() if rel.split("/")[0] in AREAS}, antes)

    def test_para_voltar_as_instrucoes_colado_de_outra_pasta(self):
        res = self.aplicar()                                                      # kit igual: só as instruções
        self.assertTrue(res.get("so_instrucoes"), res)
        self.assertTrue((self.raiz / "AGENTS.md").is_file())
        texto = depois_de(res["resumo"], "Para voltar as instruções: ")
        self.conferir_colado(texto, self.script, ["desfazer", "--registro", res["registro"]])
        self.assertEqual(texto, 'python "' + str(self.script) + '" desfazer --registro "' + res["registro"] + '"')
        self.voltar(texto)
        self.assertEqual([n for n in ("AGENTS.md", "CLAUDE.md") if (self.raiz / n).exists()], [])


if __name__ == "__main__":
    unittest.main()
