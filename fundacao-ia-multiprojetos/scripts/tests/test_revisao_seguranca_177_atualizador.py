"""Revisão de segurança independente da 1.7.7 (simulação da liberação real), achados do atualizador, cada um com o
cenário de falha reproduzido. Pastas descartáveis; identidade de ensaio; nada no perfil nem numa fundação real.

R177-ATU-01: no ensaio, a promoção na cópia guarda a versão anterior do kit em registry/kit_backup/<carimbo>/ e a
suíte DEPOIS levava registry/ inteiro; o `FoundationTestCase` do kit copia KIT/registry para cada raiz de teste, e o
teste do backup que procura o literal da credencial fictícia o achava no fonte antigo guardado ali: regressão falsa,
`aplicar` parado na etapa `ensaio`. Os testes do atualizador usavam `test_nenhum_*`/`test_local_*` e o mesmo kit com a
versão rebaixada; aqui a raiz tem a versão anterior de um teste do kit e a suíte roda com o padrão padrão.
R177-ATU-02: o inventário e as cópias pulam `__pycache__` (o Python o refaz da fonte), mas a promoção não o limpava:
um `.pyc` de hash não conferido (`UNCHECKED_HASH`) plantado ali passava pelo `checar` e pelo `aplicar` e rodava no uso
normal, no lugar da fonte conferida. Agora a promoção apaga o `__pycache__` das áreas de código sem seguir ligação, o
`checar` mostra o que será apagado e `__pycache__` que é ligação recusa.
R177-ATU-03: o `instrucoes_raiz.py` gravava pelo temporário previsível `.AGENTS.md.tmp` (vínculo físico ali levava o
AGENTS.md gerado a um arquivo de fora) e o atualizador gravava em registry/kit_backup, evidence/atualizacoes e
registry/atualizacoes.jsonl sem conferir ligação. Agora o temporário é imprevisível e exclusivo, destino que é ligação
recusa, o `checar` recusa ligação ou vínculo físico onde a atualização grava, e cada gravação confere de novo.
Observação do revisor: o `desfazer` podia ser repetido (ou rodar depois de outra atualização) e devolvia os substituídos
sem conferir o `sha256_novo`; agora o código tem de ser o que a atualização deixou.
R177-VAL-04 (parte do atualizador): o inventário do host rodava depois da promoção e antes de gravar o registro, com
3600 s sem captura, e a falha sumia do resumo. Agora o registro e a âncora vêm antes, o inventário tem 120 s, e
travar ou falhar vira "inventário do host não conferido (<motivo>)" no resumo.
"""

from __future__ import annotations

import importlib.util
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import KIT, SCRIPTS, SKILL, criar_ligacao_dir, rodar_script
from test_auditoria_1_7_6_atualizador import LIVRO, _Raiz, codigo_que_marca, sha


def carregar(nome: str):
    """Módulo dos scripts carregado pelo caminho (como nos testes da 1.7.6)."""
    spec = importlib.util.spec_from_file_location(nome, SCRIPTS / (nome + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ID_FALSO = ("test_auditoria_1_5_0_backup.TestN24BackupNaoSegueLigacao."
            "test_24_juncao_de_projeto_para_fora_nao_entra_na_copia")


class TestEnsaioComKitRealmenteDiferente(_Raiz):
    """R177-ATU-01: a cópia dos testes leva de registry/ a configuração, não as cópias do código guardadas ali."""

    def test_teste_do_kit_alterado_e_padrao_de_testes_padrao_sem_regressao_falsa(self):
        rel = "tests/test_auditoria_1_5_0_backup.py"
        alvo = self.raiz / rel
        texto = alvo.read_text(encoding="utf-8")
        anterior = texto.replace('"""Auditoria da 1.4.5', '"""Auditoria da 1.4.5 (texto da versão anterior do kit)', 1)
        self.assertNotEqual(anterior, texto)
        alvo.write_text(anterior, encoding="utf-8", newline="\n")
        self.registrar_hash(rel)                                            # como se o kit anterior o tivesse
        self.versao_antiga()
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 0, chk)
        self.assertIn(rel, chk["mudancas"]["atualizar"])
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups)  # test*.py, o padrão
        self.assertEqual(code, 0, {k: res.get(k) for k in ("etapa", "motivo", "regressoes", "testes_sumidos")})
        reg = json.loads(Path(res["registro"]).read_text(encoding="utf-8"))
        ensaio = reg["ensaio"]
        self.assertEqual((ensaio["regressoes"], ensaio["testes_sumidos"], ensaio["pulados_novos"]), ([], [], []))
        self.assertIn(ID_FALSO, ensaio["suite_na_copia_atualizada"]["ids"])          # rodou, com o padrão padrão
        self.assertNotIn(ID_FALSO, ensaio["suite_na_copia_atualizada"]["falhas"])
        guardado = Path(reg["promocao"]["instalar_kit"]["backup_dos_substituidos"]) / rel
        self.assertEqual(guardado.read_text(encoding="utf-8"), anterior)              # a versão anterior ficou guardada
        self.assertEqual(sha(alvo), sha(KIT / rel))


class TestCopiaDosTestesSemCopiasDoCodigo(unittest.TestCase):
    """R177-ATU-01: `preparar_copia` leva registry/ sem o que o instalador e o atualizador guardam ali (cópias do
    código, preparo, históricos e inventário do host); a configuração do kit continua indo."""

    def setUp(self):
        self.cc = carregar("codigo_conferido")
        self.base = Path(tempfile.mkdtemp(prefix="copia-dos-testes-"))
        self.origem = self.base / "origem"
        for rel, conteudo in {"fundacao/__init__.py": "", "tests/test_x.py": "",
                              "registry/route_policy.json": "{}\n", "registry/components/c.json": "{}\n",
                              "registry/configuracao-decidida.json": "{}\n",
                              "registry/kit_backup/20261021T000000Z-ab12/tests/test_x.py": "ANTIGO = 1\n",
                              "registry/kit_backup/instrucoes-20261021T000000Z/AGENTS.md": "# anterior\n",
                              "registry/kit_preparo/20261021T000000Z-ab12/fundacao/__init__.py": "",
                              "registry/kit_install.json": "[]\n", "registry/atualizacoes.jsonl": "",
                              "registry/inventario-host.json": "{}\n"}.items():
            (self.origem / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.origem / rel).write_text(conteudo, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_registry_vai_sem_kit_backup_preparo_historicos_e_inventario(self):
        conferidos = {rel: sha(self.origem / rel) for rel in ("fundacao/__init__.py", "tests/test_x.py")}
        self.cc.preparar_copia(self.origem, conferidos, self.base / "copia", dados=("registry",))
        copiados = sorted(p.relative_to(self.base / "copia").as_posix() for p in (self.base / "copia").rglob("*")
                          if p.is_file())
        self.assertEqual(copiados, ["fundacao/__init__.py", "registry/components/c.json",
                                    "registry/configuracao-decidida.json", "registry/route_policy.json",
                                    "tests/test_x.py"])


class TestBytecodePlantado(_Raiz):
    """R177-ATU-02: bytecode plantado no `__pycache__` não sobrevive ao `aplicar`."""

    def plantar_pyc(self, marcador: Path) -> Path:
        """`fundacao/__pycache__/__init__.<tag>.pyc` de uma fonte que grava o marcador, com hash não conferido: o
        Python o carrega sem olhar a fonte (`-B` só impede gravar bytecode, não ler)."""
        init = self.raiz / "fundacao" / "__init__.py"
        fonte = self.base / "fonte-plantada" / "__init__.py"
        fonte.parent.mkdir()
        fonte.write_text(init.read_text(encoding="utf-8") + "\n" + codigo_que_marca(marcador), encoding="utf-8")
        pyc = Path(importlib.util.cache_from_source(str(init)))
        pyc.parent.mkdir(exist_ok=True)
        py_compile.compile(str(fonte), cfile=str(pyc), doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
        return pyc

    def uso_normal(self) -> None:
        """Um comando comum do kit na raiz, como o lançador faz depois da atualização."""
        subprocess.run([sys.executable, "-B", "-m", "fundacao", "--raiz", str(self.raiz), "status"], cwd=str(self.raiz),
                       env=self.env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)

    def test_pyc_plantado_no_pycache_e_apagado_na_promocao(self):
        marcador = self.base / "marcador-pyc"
        pyc = self.plantar_pyc(marcador)
        self.uso_normal()
        self.assertTrue(marcador.exists(), "controle: o bytecode plantado deveria rodar no uso normal")
        marcador.unlink()
        self.versao_antiga()
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 0, chk)                                       # derivado: não recusa
        self.assertFalse(marcador.exists())                                  # o checar não importa a raiz
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups,
                                   "--padrao-testes", "test_nenhum_*.py")
        self.assertEqual(code, 0, res)
        self.uso_normal()
        self.assertFalse(marcador.exists(), "o bytecode plantado rodou depois do aplicar")
        self.assertFalse(pyc.parent.exists(), "o __pycache__ plantado continuou na raiz")
        self.assertEqual(chk["mudancas"].get("bytecode_a_apagar"), ["fundacao/__pycache__"])  # o checar avisa
        reg = json.loads(Path(res["registro"]).read_text(encoding="utf-8"))
        self.assertEqual(reg["promocao"].get("bytecode_apagado"), ["fundacao/__pycache__"])

    def test_pycache_que_e_ligacao_faz_o_checar_recusar(self):
        fora = self.base / "fora"
        fora.mkdir()
        (fora / "ids.cpython-312.pyc").write_bytes(b"\x00" * 16)
        criar_ligacao_dir(self.raiz / "fundacao" / "core" / "__pycache__", fora)
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 1, chk)
        self.assertIn("fundacao/core/__pycache__", chk["mudancas"]["por_ligacao"])

    def test_apagar_bytecode_tira_so_a_ligacao_e_nao_segue(self):
        cc = carregar("codigo_conferido")
        fora = self.base / "fora"
        fora.mkdir()
        (fora / "dado-de-fora.pyc").write_bytes(b"\x00" * 16)
        (self.raiz / "tests" / "__pycache__").mkdir()
        (self.raiz / "tests" / "__pycache__" / "helpers.cpython-312.pyc").write_bytes(b"\x00" * 16)
        criar_ligacao_dir(self.raiz / "fundacao" / "core" / "__pycache__", fora)
        self.assertEqual(cc.apagar_bytecode(self.raiz), (["fundacao/core/__pycache__", "tests/__pycache__"], []))
        self.assertFalse(cc.ligacao(self.raiz / "fundacao" / "core" / "__pycache__"))
        self.assertFalse((self.raiz / "fundacao" / "core" / "__pycache__").exists())
        self.assertFalse((self.raiz / "tests" / "__pycache__").exists())
        self.assertTrue((fora / "dado-de-fora.pyc").is_file())              # o alvo da ligação ficou intacto


ORIGINAL = "CONTEUDO-ORIGINAL-DE-FORA-DA-RAIZ\n"


class TestInstrucoesSemGravarPorLigacao(unittest.TestCase):
    """R177-ATU-03: o `instrucoes_raiz.py gerar` não grava por nome previsível nem através de ligação."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="instrucoes-ligacao-"))
        self.raiz, self.fora = self.base / "raiz", self.base / "fora.txt"
        self.raiz.mkdir()
        self.fora.write_text(ORIGINAL, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def gerar(self, *args) -> tuple:
        r = rodar_script("instrucoes_raiz.py", "gerar", "--raiz", self.raiz, *args)
        try:
            return r.returncode, json.loads(r.stdout)
        except ValueError:
            return r.returncode, {"saida_nao_json": (r.stdout + r.stderr)[-400:]}

    def test_vinculo_fisico_no_temporario_previsivel_nao_leva_a_gravacao_para_fora(self):
        os.link(self.fora, self.raiz / ".AGENTS.md.tmp")                   # hard link: qualquer conta cria
        code, res = self.gerar()
        self.assertEqual(code, 0, res)
        self.assertEqual(self.fora.read_text(encoding="utf-8"), ORIGINAL)  # o arquivo de fora não mudou
        self.assertIn("<!-- fundacao: início", (self.raiz / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual(os.stat(self.raiz / "AGENTS.md").st_nlink, 1)
        self.assertEqual([p.name for p in self.raiz.iterdir() if p.name.endswith(".tmp")], [".AGENTS.md.tmp"])

    def test_destino_que_e_ligacao_e_recusado_sem_gravar(self):
        pasta_de_fora = self.base / "pasta-de-fora"
        pasta_de_fora.mkdir()
        criar_ligacao_dir(self.raiz / "AGENTS.md", pasta_de_fora)
        for args in ((), ("--simular",)):
            with self.subTest(args=args):
                code, res = self.gerar(*args)
                self.assertEqual((code, res.get("ok")), (1, False), res)
                self.assertIn("ligação", res.get("erro", ""))
        self.assertEqual(list(pasta_de_fora.iterdir()), [])
        self.assertEqual(sorted(p.name for p in self.raiz.iterdir()), ["AGENTS.md"])  # nem CLAUDE.md, nem temporário
        r = rodar_script("instrucoes_raiz.py", "conferir", "--raiz", self.raiz)
        self.assertEqual(r.returncode, 1)
        self.assertTrue(any("ligação" in p for p in json.loads(r.stdout)["problemas"]), r.stdout)


class TestAtualizadorSemGravarPorLigacao(_Raiz):
    """R177-ATU-03: o atualizador não grava a cópia das instruções, o registro nem a âncora através de ligação ou
    vínculo físico. O cenário é o do kit igual com instruções de versão anterior: grava os três."""

    def setUp(self):
        super().setUp()
        r = rodar_script("instrucoes_raiz.py", "gerar", "--raiz", self.raiz)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        agents = self.raiz / "AGENTS.md"
        texto = agents.read_text(encoding="utf-8")
        antigo = re.sub(r"(Gerado pela skill `fundacao-ia-multiprojetos` )\S+\.", r"\g<1>1.0.0.", texto, count=1)
        self.assertNotEqual(antigo, texto)
        agents.write_text(antigo, encoding="utf-8", newline="\n")
        self.antes_agents = agents.read_bytes()

    def aplicar_recusado(self, trecho: str) -> dict:
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups,
                                   "--padrao-testes", "test_nenhum_*.py")
        self.assertEqual((code, res.get("etapa")), (1, "checar"), res)
        self.assertTrue(any(trecho in m and "grava" in m for m in res["checar"]["motivos"]), res["checar"]["motivos"])
        self.assertEqual((self.raiz / "AGENTS.md").read_bytes(), self.antes_agents)  # nada regenerado
        return res

    def test_juncao_em_kit_backup_recusa_e_nada_vai_para_fora(self):
        fora = self.base / "kit-backup-de-fora"
        fora.mkdir()
        criar_ligacao_dir(self.raiz / "registry" / "kit_backup", fora)
        self.aplicar_recusado("registry/kit_backup")
        self.assertEqual(list(fora.iterdir()), [])

    def test_juncao_em_evidence_atualizacoes_recusa_e_nada_vai_para_fora(self):
        fora = self.base / "evidencias-de-fora"
        fora.mkdir()
        (self.raiz / "evidence").mkdir(exist_ok=True)
        criar_ligacao_dir(self.raiz / "evidence" / "atualizacoes", fora)
        self.aplicar_recusado("evidence/atualizacoes")
        self.assertEqual(list(fora.iterdir()), [])

    def test_vinculo_fisico_no_livro_das_ancoras_recusa_e_o_arquivo_de_fora_fica(self):
        fora = self.base / "livro-de-fora.jsonl"
        fora.write_text(ORIGINAL, encoding="utf-8")
        os.link(fora, self.raiz / LIVRO)
        self.aplicar_recusado("registry/atualizacoes.jsonl")
        self.assertEqual(fora.read_text(encoding="utf-8"), ORIGINAL)

    def test_gravacao_confere_de_novo_a_ligacao_no_momento_de_gravar(self):
        """Ligação criada depois do `checar` (corrida): o registro e a âncora recusam na hora de gravar (a gravação
        do registro mora em registro_atualizacao.py desde a 1.7.7; antes, `atualizar_fundacao._gravar`)."""
        ra = carregar("registro_atualizacao")
        fora = self.base / "evidencias-de-fora"
        fora.mkdir()
        (self.raiz / "evidence").mkdir(exist_ok=True)
        criar_ligacao_dir(self.raiz / "evidence" / "atualizacoes", fora)
        with self.assertRaises(ra.Parada) as ctx:
            ra.gravar(self.raiz, "registro-de-ensaio.json", {"ensaio": True}, ancorar=True)
        self.assertEqual(ctx.exception.etapa, "registro")
        self.assertEqual(list(fora.iterdir()), [])
        self.assertFalse((self.raiz / LIVRO).exists())


class TestGravacaoSegura(unittest.TestCase):
    """R177-ATU-03: as primitivas de `gravacao_segura.py` (o padrão do `publicacao.py` do kit, sem importá-lo)."""

    def setUp(self):
        self.gs = carregar("gravacao_segura")
        self.base = Path(tempfile.mkdtemp(prefix="gravacao-segura-"))
        self.fora = self.base / "fora.txt"
        self.fora.write_text(ORIGINAL, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_anexar_e_criar_recusam_vinculo_fisico_e_publicar_troca_o_nome(self):
        livro = self.base / "livro.jsonl"
        os.link(self.fora, livro)
        with self.assertRaises(self.gs.GravacaoRecusada):
            self.gs.anexar(livro, b"linha\n")
        with self.assertRaises(FileExistsError):
            self.gs.criar(livro, b"novo\n")
        self.gs.publicar(livro, b"publicado\n")                            # troca o nome; não grava por ele
        self.assertEqual((livro.read_bytes(), self.fora.read_text(encoding="utf-8")), (b"publicado\n", ORIGINAL))
        self.gs.anexar(livro, b"mais\n")                                   # agora é arquivo simples
        self.assertEqual(livro.read_bytes(), b"publicado\nmais\n")
        self.assertEqual([p.name for p in self.base.iterdir() if p.suffix == ".tmp"], [])

    def test_publicar_recusa_destino_ligacao_e_pasta_sem_ligacao_recusa(self):
        alvo = self.base / "alvo"
        alvo.mkdir()
        raiz = self.base / "raiz"
        raiz.mkdir()
        criar_ligacao_dir(raiz / "AGENTS.md", alvo)
        with self.assertRaises(self.gs.GravacaoRecusada):
            self.gs.publicar(raiz / "AGENTS.md", b"x")
        criar_ligacao_dir(raiz / "evidence", alvo)
        with self.assertRaises(self.gs.GravacaoRecusada):
            self.gs.pasta_sem_ligacao(raiz, "evidence/atualizacoes")
        self.assertEqual(list(alvo.iterdir()), [])
        self.assertEqual(self.gs.desviados(raiz, ["AGENTS.md", "evidence/atualizacoes", "registry/x.json"]),
                         ["AGENTS.md", "evidence/atualizacoes"])


class TestDesfazerConfereOCodigoAtual(_Raiz):
    """Observação do revisor: o `desfazer` só devolve se o código ainda é o que a atualização deixou (`sha256_novo`)."""

    def aplicar(self) -> dict:
        self.versao_antiga()
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups,
                                   "--padrao-testes", "test_nenhum_*.py")
        self.assertEqual(code, 0, res)
        return res

    def test_desfazer_repetido_e_recusado_sem_alterar_nada(self):
        res = self.aplicar()
        code, des = self.atualizar("desfazer", "--registro", res["registro"])
        self.assertEqual(code, 0, des)
        antes = self.foto()
        code, des2 = self.atualizar("desfazer", "--registro", res["registro"])
        self.assertEqual((code, des2.get("etapa")), (1, "desfazer"), des2)
        self.assertIn("mudou depois", des2["motivo"])
        self.assertEqual(self.foto(), antes)                                # nem registro novo

    def test_desfazer_depois_de_outra_mudanca_nao_devolve_por_cima(self):
        res = self.aplicar()
        init = self.raiz / "fundacao" / "__init__.py"
        posterior = init.read_text(encoding="utf-8") + "# versão posterior (outra atualização)\n"
        init.write_text(posterior, encoding="utf-8")
        code, des = self.atualizar("desfazer", "--registro", res["registro"])
        self.assertEqual((code, des.get("etapa")), (1, "desfazer"), des)
        self.assertEqual(init.read_text(encoding="utf-8"), posterior)

    def test_desfazer_recusa_vinculo_fisico_no_registro_da_instalacao(self):
        res = self.aplicar()
        reg = self.raiz / "registry" / "kit_install.json"
        fora = self.base / "kit_install-de-fora.json"
        shutil.move(reg, fora)
        os.link(fora, reg)
        conteudo = fora.read_bytes()
        code, des = self.atualizar("desfazer", "--registro", res["registro"])
        self.assertEqual((code, des.get("etapa")), (1, "desfazer"), des)
        self.assertEqual(fora.read_bytes(), conteudo)
        init = (self.raiz / "fundacao" / "__init__.py").read_text(encoding="utf-8")
        self.assertNotIn('KIT_VERSION = "1.0.0"', init)                     # nada foi devolvido


STUB_INVENTARIO = '''import json, sys, time
from pathlib import Path
args = sys.argv[1:]
livro = Path(args[args.index("--raiz") + 1]) / "registry" / "atualizacoes.jsonl"
linhas = livro.read_text(encoding="utf-8").splitlines() if livro.exists() else []
Path({marca!r}).write_text(json.dumps(linhas), encoding="utf-8")
time.sleep(20)
'''


class TestInventarioDoHostDepoisDoRegistro(_Raiz):
    """R177-VAL-04 (parte do atualizador): o inventário do host não perde a atualização já promovida."""

    def test_inventario_que_trava_vem_depois_do_registro_e_aparece_no_resumo(self):
        skill = self.base / "skill"
        shutil.copytree(SKILL, skill, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "evals"))
        marca = self.base / "o-que-o-inventario-viu.json"
        (skill / "scripts" / "inventariar_host.py").write_text(STUB_INVENTARIO.format(marca=str(marca)),
                                                              encoding="utf-8")
        script = skill / "scripts" / "atualizar_fundacao.py"
        texto = script.read_text(encoding="utf-8")  # o tempo limite da cópia cai para 2 s: o teste não espera 120 s
        script.write_text(re.sub(r"(?m)^TEMPO_INVENTARIO = \d+", "TEMPO_INVENTARIO = 2", texto), encoding="utf-8")
        (self.raiz / "registry" / "inventario-host.json").write_text("{}\n", encoding="utf-8")
        self.versao_antiga()
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups,
                                   "--padrao-testes", "test_nenhum_*.py", script=script)
        self.assertEqual(code, 0, res)
        rel = Path(res["registro"]).resolve().relative_to(self.raiz.resolve()).as_posix()
        vistas = [json.loads(linha)["registro"] for linha in json.loads(marca.read_text(encoding="utf-8"))]
        self.assertIn(rel, vistas, "o inventário rodou antes de o registro ser gravado e ancorado")
        self.assertTrue(any("inventário do host não conferido" in linha.lower() for linha in res["resumo"]),
                        res["resumo"])
        code, des = self.atualizar("desfazer", "--registro", res["registro"], script=script)
        self.assertEqual(code, 0, des)                                       # o registro vale para voltar

    def test_inventario_com_tempo_esgotado_ou_saida_estranha_nao_lanca(self):
        af = carregar("atualizar_fundacao")
        (self.raiz / "registry" / "inventario-host.json").write_text("{}\n", encoding="utf-8")
        esgotado = subprocess.TimeoutExpired(cmd="inventariar_host.py", timeout=1)
        with mock.patch.object(af, "rodar", side_effect=esgotado):
            res = af._inventario_host(self.raiz)
        self.assertEqual(res["conferido"], False)
        self.assertIn("tempo", res["motivo"])
        with mock.patch.object(af, "rodar", return_value=(0, {"diferencas": ["não é dicionário"]}, "")):
            res = af._inventario_host(self.raiz)
        self.assertEqual(res["conferido"], False)


if __name__ == "__main__":
    unittest.main()
