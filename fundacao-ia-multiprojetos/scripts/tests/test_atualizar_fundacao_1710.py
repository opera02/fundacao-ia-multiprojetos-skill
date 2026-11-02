"""atualizar_fundacao.py na fundação viva com dados reais (1.7.10, item 0.15 e seção 2 do escopo).

- O ensaio nasce numa pasta nova dentro de --pasta-ensaio (padrão: a de --backups), não na temporária do C:; dentro da
  raiz, recusa.
- A limpeza do ensaio e do código conferido é contada (sem ignore_errors silencioso); a marca somente leitura sai só
  dentro da pasta criada pelo atualizador; a ligação sai como ligação, sem tocar o destino.
- A cópia ANTES que falha na promoção (código 2 com E_ARQUIVO/E_PROMOCAO ou WinError 5) conta a sobra, confere o
  destino ausente e tenta de novo UMA vez, com rótulo novo; as duas tentativas vão para o registro.
- WSL em execução antes de começar e antes da restauração do ensaio recusa (a raiz de ensaio na pasta temporária só
  registra); a trava state/manutencao.json existe durante o aplicar e sai no fim, também na falha.
- A estimativa de tempo pelo número de arquivos (medido em 31/10/2026) e o prazo configurável.
- Revisão de segurança da 1.7.10 (KITCOPIA, correções da revisão 1): --backups dentro da raiz e a política de backup que
  o kit novo recusaria param no `checar`, antes de qualquer cópia.
Fundações fictícias em pastas descartáveis; nenhum dado real."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import ENV, SCRIPTS, criar_ligacao_dir, rodar_script, versao_do_kit

IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"
CANARIO = "CONTEUDO-FICTICIO-FORA-DA-PASTA"


def carregar():
    spec = importlib.util.spec_from_file_location("_atualizar_1710", SCRIPTS / "atualizar_fundacao.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestLimpezaContada(unittest.TestCase):
    def setUp(self):
        self.mod = carregar()
        self.base = Path(tempfile.mkdtemp(prefix="limpeza-1710-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.pasta = self.base / "ensaio-atualizacao-ficticio"
        (self.pasta / "raiz" / "projects" / "p" / "data").mkdir(parents=True)
        for rel in ("raiz/AGENTS.md", "raiz/projects/p/data/doc.md", "raiz/projects/p/data/so-leitura.md"):
            (self.pasta / rel).write_bytes("dado fictício\n".encode("utf-8"))
        os.chmod(self.pasta / "raiz/projects/p/data/so-leitura.md", stat.S_IREAD)  # somente leitura
        if os.name == "nt":
            os.chmod(self.pasta / "raiz/projects/p", stat.S_IREAD)  # no Windows, a marca também em pasta
        self.fora = self.base / "fora"
        self.fora.mkdir()
        (self.fora / "canario.txt").write_text(CANARIO, encoding="utf-8")

    def test_apaga_tudo_tira_a_marca_e_nao_segue_ligacao(self):
        criar_ligacao_dir(self.pasta / "raiz" / "atalho", self.fora)
        res = self.mod.limpar(self.pasta)
        self.assertTrue(res["limpa"], res)
        self.assertEqual(res["sobra"], {"arquivos": 0, "pastas": 0, "ligacoes": 0, "bytes": 0})
        self.assertEqual(res["erros"], [])
        self.assertGreaterEqual(res["apagados"], 8)
        self.assertFalse(self.pasta.exists())
        self.assertEqual((self.fora / "canario.txt").read_text(encoding="utf-8"), CANARIO)  # o destino da ligação fica

    def test_falha_conta_a_sobra_e_o_erro_sem_esconder(self):
        preso = str(self.pasta / "raiz" / "projects" / "p" / "data" / "doc.md")
        original = os.unlink

        def unlink(caminho, *a, **k):
            if os.path.normcase(str(caminho)) == os.path.normcase(preso):
                raise PermissionError(13, "arquivo preso (ensaio)")
            return original(caminho, *a, **k)

        with mock.patch.object(self.mod.os, "unlink", unlink):
            res = self.mod.limpar(self.pasta)
        self.assertFalse(res["limpa"])
        self.assertEqual(res["sobra"]["arquivos"], 1)
        self.assertEqual(res["sobra"]["bytes"], len("dado fictício\n".encode("utf-8")))
        self.assertTrue(res["erros"], res["erros"])  # o erro fica registrado (a sobra não é escondida)
        self.assertFalse(any("doc.md" in e for e in res["erros"]), res["erros"])  # nome do caso não vai às saídas
        self.assertTrue(any("raiz/projects/p" in e for e in res["erros"]), res["erros"])  # a área, sim
        self.assertNotIn("dado fictício", json.dumps(res, ensure_ascii=False))
        self.assertTrue(self.mod._resumo_limpeza({"ensaio": res})[0].startswith("Atenção: sobrou parte da cópia de "
                                                                                 "ensaio"))

    def test_pasta_ausente_e_limpa(self):
        self.assertTrue(self.mod.limpar(self.base / "nao-existe")["limpa"])


class TestNovaTentativaDaCopiaAntes(unittest.TestCase):
    ERRO = json.dumps({"error": {"code": "E_ARQUIVO", "message": "[WinError 5] Acesso negado: preparo -> destino",
                                 "tipo": "PermissionError"}})

    def setUp(self):
        self.mod = carregar()
        self.base = Path(tempfile.mkdtemp(prefix="tentativa-1710-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.backups = self.base / "backups"
        self.backups.mkdir()
        self.destino = self.backups / "antes-kit-9.9.9-20261031T000000Z"
        sobra = self.backups / ("." + self.destino.name + ".preparo-1a2b3c4d")
        (sobra / "files" / "projects").mkdir(parents=True)
        (sobra / "files" / "projects" / "x.md").write_text("dado fictício da sobra\n", encoding="utf-8")

    def copia(self, respostas: list):
        chamadas = []

        def fundacao(codigo, raiz, *args, prazo=None):
            chamadas.append((args[1], args[args.index("--destino") + 1] if "--destino" in args else args[3], prazo))
            return respostas.pop(0)

        return chamadas, mock.patch.object(self.mod, "fundacao", fundacao)

    def test_falha_na_promocao_tenta_de_novo_uma_vez_com_rotulo_novo(self):
        chamadas, p = self.copia([(2, None, self.ERRO), (0, {"sha256_manifesto": "a" * 64, "files": [1, 2]}, ""),
                                  (0, {"ok": True}, "")])
        with p:
            res = self.mod._backup(Path("codigo"), self.base, self.destino, self.destino.name, 777, tentar_de_novo=True)
        self.assertEqual(res["rotulo"], self.destino.name + "-tentativa-2")
        self.assertEqual([c[0] for c in chamadas], ["criar", "criar", "verificar"])
        self.assertTrue(all(c[2] == 777 for c in chamadas))
        primeira, segunda = res["tentativas"]
        self.assertEqual((primeira["codigo"], segunda["codigo"]), (2, 0))
        self.assertEqual(primeira["sobra_do_preparo"]["arquivos"], 1)
        self.assertEqual(primeira["sobra_do_preparo"]["pastas_de_preparo"], ["." + self.destino.name + ".preparo-1a2b3c4d"])
        self.assertTrue(any(self.backups.glob(".*.preparo-*")), "a sobra tem dados: só o titular apaga")

    def test_conta_os_arquivos_nos_dois_formatos_do_backup_criar(self):
        # Integração 1.7.10: o kit 1.7.9 (cópia ANTES) devolve a lista `files`; o 1.7.10 devolve só o resumo, com
        # `arquivos` (número). Antes desta junção, o resumo do 1.7.10 contava 0 arquivos.
        for saida, esperado in (({"sha256_manifesto": "a" * 64, "files": [1, 2, 3]}, 3),
                                ({"sha256_manifesto": "a" * 64, "arquivos": 5}, 5)):
            with self.subTest(esperado=esperado):
                _, p = self.copia([(0, saida, ""), (0, {"ok": True}, "")])
                with p:
                    res = self.mod._backup(Path("codigo"), self.base, self.destino, self.destino.name, 777)
                self.assertEqual(res["arquivos"], esperado)

    def test_outra_falha_destino_existente_ou_segunda_falha_param(self):
        erro_comum = json.dumps({"error": {"code": "E_VALIDATION", "message": "outra coisa"}})
        for respostas, tentativas in (([(2, None, erro_comum)], 1), ([(2, None, self.ERRO), (2, None, self.ERRO)], 2)):
            with self.subTest(tentativas=tentativas):
                _chamadas, p = self.copia(list(respostas))
                with p, self.assertRaises(self.mod.Parada) as ctx:
                    self.mod._backup(Path("codigo"), self.base, self.destino, self.destino.name, tentar_de_novo=True)
                self.assertEqual(len(ctx.exception.detalhes["tentativas"]), tentativas)
        self.destino.mkdir()
        _chamadas, p = self.copia([(2, None, self.ERRO)])
        with p, self.assertRaises(self.mod.Parada) as ctx:
            self.mod._backup(Path("codigo"), self.base, self.destino, self.destino.name, tentar_de_novo=True)
        self.assertIn("destino existe", ctx.exception.motivo)

    def test_copia_depois_nao_tenta_de_novo(self):
        _chamadas, p = self.copia([(2, None, self.ERRO)])
        with p, self.assertRaises(self.mod.Parada) as ctx:
            self.mod._backup(Path("codigo"), self.base, self.destino, self.destino.name)
        self.assertEqual(len(ctx.exception.detalhes["tentativas"]), 1)

    def test_reconhece_a_falha_de_promocao(self):
        f = self.mod.falha_de_promocao
        self.assertTrue(f(2, self.ERRO))
        self.assertTrue(f(2, json.dumps({"error": {"code": "E_PROMOCAO", "message": "x"}})))
        self.assertTrue(f(2, "Traceback ... [WinError 5] Acesso negado"))
        self.assertFalse(f(1, self.ERRO))
        self.assertFalse(f(2, json.dumps({"error": {"code": "E_VALIDATION", "message": "x"}})))
        # `error` como texto ou lista não pode lançar AttributeError; o WinError no texto continua valendo.
        self.assertFalse(f(2, json.dumps({"error": "texto solto"})))
        self.assertFalse(f(2, json.dumps({"error": ["lista"]})))
        self.assertTrue(f(2, json.dumps({"error": "x [WinError 5] y"})))


class TestEstimativa(unittest.TestCase):
    def test_conta_o_que_a_copia_leva_e_escala_pela_medida(self):
        mod = carregar()
        with tempfile.TemporaryDirectory() as t:
            raiz = Path(t)
            for rel in ("fundacao/a.py", "projects/p/data/b.md", "projects/p/.env", "docs/c.md", "RETOMADA.md",
                        "projects/p/node_modules/x.js", "projects/p/.git/HEAD", "fundacao/__pycache__/a.pyc",
                        "modelos/peso.bin", "state/state.sqlite"):
                (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
                (raiz / rel).write_text("x", encoding="utf-8")
            self.assertEqual(mod.contar_arquivos(raiz), 4)  # a.py, b.md, c.md e RETOMADA.md
            (raiz / "registry").mkdir()
            (raiz / "registry" / "backup_policy.json").write_text(json.dumps({"incluir": ["modelos"]}), encoding="utf-8")
            self.assertEqual(mod.contar_arquivos(raiz), 4)  # a.py, b.md, a política e o peso (docs saiu da lista)
            # Entradas inseguras da política são puladas, como no kit (sem absoluto, unidade, .., state/, .git).
            (raiz / "registry" / "backup_policy.json").write_text(
                json.dumps({"incluir": ["modelos", "../fora", "state/x", ".git/y", "/abs"]}), encoding="utf-8")
            self.assertEqual(mod._incluidos(raiz), ["modelos"])
            self.assertEqual(mod.contar_arquivos(raiz), 4)
        with mock.patch.object(mod, "contar_arquivos", return_value=130_000):
            est = mod.estimar(Path("."))
        self.assertEqual(est["segundos"], {"copia_antes": 1770, "restauracao_do_ensaio": 1620, "copia_depois": 1770})
        self.assertEqual(est["minutos"], 86)
        self.assertIn("31/10/2026", est["base"])


class TestWslEmUso(unittest.TestCase):
    """MÉDIO 3: dentro do Ubuntu, o wsl.exe do Windows aparece pela interop e listaria a própria distribuição,
    derrubando a sessão no `aplicar`. Fora do Windows, `wsl_em_uso` devolve [] sem consultar o wsl.exe."""

    def setUp(self):
        self.mod = carregar()

    def test_no_ubuntu_nao_consulta_o_wsl(self):
        def nao_chamar(*a, **k):
            raise AssertionError("não pode consultar o wsl.exe no Ubuntu")
        with mock.patch.object(self.mod.subprocess, "run", nao_chamar), \
                mock.patch.object(self.mod.shutil, "which", lambda _n: "/mnt/c/Windows/System32/wsl.exe"):
            self.assertEqual(self.mod.wsl_em_uso(nome_sistema="posix"), [])

    def test_no_windows_sem_wsl_exe_devolve_vazio(self):
        with mock.patch.object(self.mod.shutil, "which", lambda _n: None):
            self.assertEqual(self.mod.wsl_em_uso(nome_sistema="nt"), [])

    def test_no_windows_lista_as_distros_menos_docker(self):
        class R:
            stdout = "Ubuntu\ndocker-desktop\n".encode("utf-16-le")
        with mock.patch.object(self.mod.shutil, "which", lambda _n: "C:/w/wsl.exe"), \
                mock.patch.object(self.mod.subprocess, "run", lambda *a, **k: R()):
            self.assertEqual(self.mod.wsl_em_uso(nome_sistema="nt"), ["Ubuntu"])


class Fundacao(unittest.TestCase):
    """Fundação fictícia instalada pelo kit da skill, como em test_atualizar_fundacao.py."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="atualizar-1710-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.raiz, self.backups = self.tmp / "raiz", self.tmp / "backups"
        r = rodar_script("instalar_kit.py", "--destino", self.raiz)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = subprocess.run([sys.executable, "-B", "-m", "fundacao", "--raiz", str(self.raiz), "init", "--admin",
                            "titular-ensaio"], cwd=str(self.raiz), env=ENV, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.mod = carregar()
        self.trava = self.raiz / "state" / "manutencao.json"

    def versao_antiga(self) -> None:
        init = self.raiz / "fundacao" / "__init__.py"
        atual = 'KIT_VERSION = "' + versao_do_kit(self.raiz) + '"'
        init.write_text(init.read_text(encoding="utf-8").replace(atual, 'KIT_VERSION = "1.0.0"'), encoding="utf-8")
        reg = self.raiz / "registry" / "kit_install.json"
        historico = json.loads(reg.read_text(encoding="utf-8"))
        for item in historico[-1]["copiados"]:
            if item["path"] == "fundacao/__init__.py":
                item["sha256"] = __import__("hashlib").sha256(init.read_bytes()).hexdigest()
        reg.write_text(json.dumps(historico, ensure_ascii=False, indent=2), encoding="utf-8")


class TestWslETrava(Fundacao):
    def aplicar(self, **kw):
        with mock.patch.dict(os.environ, {IDENTIDADE: "titular-ensaio"}):
            return self.mod.aplicar(self.raiz, self.backups, "test_nenhum_*.py", **kw)

    def test_wsl_em_execucao_recusa_antes_de_tudo(self):
        with mock.patch.object(self.mod, "wsl_em_uso", lambda: ["Ubuntu"]), \
                mock.patch.object(self.mod, "em_pasta_temporaria", lambda _r: False), \
                mock.patch.object(self.mod, "_inspecionar", side_effect=AssertionError("o checar não pode rodar")):
            with self.assertRaises(self.mod.Parada) as ctx:
                self.aplicar()
        self.assertEqual(ctx.exception.etapa, "checar")
        self.assertIn("WSL em execução (Ubuntu)", ctx.exception.motivo)
        self.assertFalse(self.trava.exists())
        self.assertFalse(self.backups.exists())

    def test_raiz_de_ensaio_na_pasta_temporaria_so_registra(self):
        self.assertTrue(self.mod.em_pasta_temporaria(self.raiz))
        with mock.patch.object(self.mod, "wsl_em_uso", lambda: ["Ubuntu"]):
            self.assertEqual(self.mod.sem_wsl("checar", self.raiz)["so_registrado"],
                             "raiz de ensaio na pasta temporária")

    def test_trava_durante_o_aplicar_e_fora_no_fim_tambem_na_falha(self):
        vistas = []

        def so_instrucoes(raiz, pre, carimbo):
            vistas.append(json.loads(self.trava.read_text(encoding="utf-8")))
            return {"ok": True, "nada_a_fazer": True, "resumo": []}

        with mock.patch.object(self.mod, "_so_instrucoes", so_instrucoes):
            res = self.aplicar()
        self.assertEqual(set(vistas[0]), {"motivo", "pid", "host", "desde"})
        self.assertEqual(vistas[0]["pid"], os.getpid())
        self.assertEqual(res["trava"], {"removida": True})
        self.assertFalse(self.trava.exists())

        def falha(raiz, pre, carimbo):
            raise self.mod.Parada("ensaio", "falha de ensaio")

        with mock.patch.object(self.mod, "_so_instrucoes", falha), self.assertRaises(self.mod.Parada) as ctx:
            self.aplicar()
        self.assertEqual(ctx.exception.detalhes["trava"], {"removida": True})
        self.assertFalse(self.trava.exists())

    def test_trava_existente_recusa_sem_alterar(self):
        self.trava.write_text(json.dumps({"motivo": "outra", "pid": 1, "host": "x", "desde": "y"}), encoding="utf-8")
        antes = self.trava.read_bytes()
        with self.assertRaises(self.mod.Parada) as ctx:
            self.aplicar()
        self.assertEqual(ctx.exception.etapa, "trava")
        self.assertEqual(self.trava.read_bytes(), antes)

    def test_pasta_de_ensaio_dentro_da_raiz_recusa(self):
        with self.assertRaises(self.mod.Parada) as ctx:
            self.aplicar(pasta_ensaio=self.raiz / "evidence")
        self.assertIn("dentro da raiz", ctx.exception.motivo)
        self.assertFalse(self.trava.exists())

    def test_wsl_antes_da_restauracao_do_ensaio(self):
        tmp = self.tmp / "ensaio"
        tmp.mkdir()
        antes = {"pasta": str(self.backups / "x"), "sha256_manifesto": "a" * 64, "ancora_pelo_kit": True}
        with mock.patch.object(self.mod, "wsl_em_uso", lambda: ["Ubuntu"]), \
                mock.patch.object(self.mod, "em_pasta_temporaria", lambda _r: False), \
                mock.patch.object(self.mod, "fundacao", side_effect=AssertionError("a restauração não pode rodar")):
            with self.assertRaises(self.mod.Parada) as ctx:
                self.mod._ensaio_na_copia(self.raiz, Path("codigo"), antes, "test_*.py", {}, tmp)
        self.assertEqual(ctx.exception.etapa, "ensaio")


class TestAplicarDeVerdade(Fundacao):
    def test_ensaio_na_pasta_das_copias_com_limpeza_contada_e_sem_trava(self):
        self.versao_antiga()
        r = subprocess.run([sys.executable, "-B", str(SCRIPTS / "atualizar_fundacao.py"), "aplicar", "--raiz",
                            str(self.raiz), "--backups", str(self.backups), "--padrao-testes", "test_nenhum_*.py",
                            "--prazo", "900"], env={**ENV, IDENTIDADE: "titular-ensaio"}, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=900)
        self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
        res = json.loads(r.stdout)
        self.assertIn("Estimativa: cerca de", r.stderr)
        reg = json.loads(Path(res["registro"]).read_text(encoding="utf-8"))
        ensaio = Path(reg["limpeza"]["pasta_do_ensaio"])
        self.assertEqual(ensaio.parent, self.backups.resolve())  # no disco das cópias, não na temporária
        self.assertTrue(ensaio.name.startswith("ensaio-atualizacao-"))
        self.assertTrue(reg["limpeza"]["ensaio"]["limpa"], reg["limpeza"])
        self.assertTrue(reg["limpeza"]["codigo"]["limpa"], reg["limpeza"])
        self.assertEqual(list(self.backups.glob("ensaio-atualizacao-*")), [])
        self.assertGreater(reg["estimativa"]["arquivos"], 0)
        self.assertEqual(reg["prazo_por_etapa"], 900)
        self.assertLessEqual({"motivo", "pid", "host", "desde"}, set(reg["trava"]))
        self.assertEqual(res["trava"], {"removida": True})
        self.assertFalse(self.trava.exists())
        self.assertIn("em_uso", reg["wsl"])
        # A política da raiz passa a levar as áreas da 1.7.10, antes da cópia DEPOIS.
        self.assertTrue(reg["politica_de_backup"]["mudou"], reg["politica_de_backup"])
        politica = json.loads((self.raiz / "registry" / "backup_policy.json").read_text(encoding="utf-8"))
        self.assertLessEqual({"em-uso", ".claude/projetos"}, set(politica["incluir"]))
        self.assertTrue(any("passa a levar também" in linha for linha in res["resumo"]), res["resumo"])


class TestPoliticaDeBackup(unittest.TestCase):
    """A política de backup da raiz ganha `em-uso/` e `.claude/projetos/` no `aplicar` (1.7.10; crítica do desenho
    §5.1): só acrescenta, preserva o resto, é idempotente e não grava por ligação nem sobre política estragada."""

    def setUp(self):
        self.mod = carregar()
        self.raiz = Path(tempfile.mkdtemp(prefix="politica-1710-"))
        self.addCleanup(shutil.rmtree, self.raiz, ignore_errors=True)
        (self.raiz / "registry").mkdir()
        self.arq = self.raiz / "registry" / "backup_policy.json"

    def test_acrescenta_preservando_o_resto_e_e_idempotente(self):
        original = {"schema_version": "fundacao.backup_policy/1", "origem": "lista do titular",
                    "incluir": ["docs", ".claude/hooks"]}
        self.arq.write_text(json.dumps(original), encoding="utf-8")
        res = self.mod.politica_de_backup(self.raiz)
        self.assertEqual((res["mudou"], res["criada"], res["acrescentados"]),
                         (True, False, ["em-uso", ".claude/projetos"]))
        dados = json.loads(self.arq.read_text(encoding="utf-8"))
        self.assertEqual(dados, {**original, "incluir": ["docs", ".claude/hooks", "em-uso", ".claude/projetos"]})
        self.assertEqual(self.mod.politica_de_backup(self.raiz), {"mudou": False})
        self.assertEqual(self.mod._resumo_politica({"mudou": False}), [])

    def test_sem_politica_nasce_com_a_lista_padrao_mais_as_areas_novas(self):
        self.arq.unlink(missing_ok=True)
        res = self.mod.politica_de_backup(self.raiz)
        self.assertTrue(res["criada"])
        dados = json.loads(self.arq.read_text(encoding="utf-8"))
        self.assertEqual(dados["incluir"], [*self.mod.REGISTROS_NA_COPIA, "em-uso", ".claude/projetos"])
        self.assertIn("criado", self.mod._resumo_politica(res)[0])

    def test_politica_estragada_fica_como_esta_com_aviso(self):
        for conteudo in ("{nao e json", json.dumps({"incluir": "docs"}), json.dumps(["docs"])):
            with self.subTest(conteudo=conteudo):
                self.arq.write_text(conteudo, encoding="utf-8")
                res = self.mod.politica_de_backup(self.raiz)
                self.assertFalse(res["mudou"])
                self.assertEqual(self.arq.read_text(encoding="utf-8"), conteudo)
                self.assertIn("acrescente à mão", self.mod._resumo_politica(res)[0])

    def test_registry_ligado_para_fora_recusa_sem_gravar_la(self):
        fora = self.raiz.parent / (self.raiz.name + "-fora")
        fora.mkdir()
        self.addCleanup(shutil.rmtree, fora, ignore_errors=True)
        (fora / "backup_policy.json").write_text(json.dumps({"incluir": ["docs"]}), encoding="utf-8")
        shutil.rmtree(self.raiz / "registry")
        criar_ligacao_dir(self.raiz / "registry", fora)
        res = self.mod.politica_de_backup(self.raiz)
        self.assertFalse(res["mudou"])
        self.assertIn("ligação", res["erro"])
        self.assertEqual(json.loads((fora / "backup_policy.json").read_text(encoding="utf-8")), {"incluir": ["docs"]})

    def test_fora_da_copia_igual_ao_do_kit_e_o_cache_fica_fora(self):
        import ast
        arvore = ast.parse((SCRIPTS.parent / "assets" / "fundacao-kit" / "fundacao" / "core" / "backup.py")
                           .read_text(encoding="utf-8"))
        kit = next(ast.literal_eval(no.value) for no in arvore.body if isinstance(no, ast.Assign)
                   and any(getattr(t, "id", None) == "EXCLUDE_PARTS" for t in no.targets))
        self.assertEqual(self.mod.FORA_DA_COPIA, kit)
        for rel in ("projects/p/data/a.md", "projects/p/.cache/npm/x.tgz", "projects/p/.cache/pip/y.whl"):
            (self.raiz / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.raiz / rel).write_text("x", encoding="utf-8")
        self.arq.write_text(json.dumps({"incluir": []}), encoding="utf-8")
        self.assertEqual(self.mod.contar_arquivos(self.raiz), 2)  # a.md e a política; o cache de ferramenta, não


class TestCopiasEPoliticaAntesDeQualquerCopia(Fundacao):
    """Revisão de segurança da 1.7.10 (KITCOPIA, correções da revisão 1): --backups dentro da raiz recusa no `checar`,
    com ou sem --pasta-ensaio (KIT-F7: a cópia ANTES, feita pelo kit da raiz, nascia dentro dela, e a DEPOIS só era
    recusada depois da promoção), e a política de backup que o kit novo recusaria aparece no `checar` (KIT-F2: antes, só
    a cópia DEPOIS a recusava, com a raiz já promovida), sem cópia nem trava."""

    def aplicar(self, backups: Path, **kw):
        with mock.patch.dict(os.environ, {IDENTIDADE: "titular-ensaio"}), \
                mock.patch.object(self.mod, "_backup", side_effect=AssertionError("nenhuma cópia pode ser feita")):
            return self.mod.aplicar(self.raiz, backups, "test_nenhum_*.py", **kw)

    def test_backups_dentro_da_raiz_recusa_mesmo_com_o_ensaio_fora(self):
        self.versao_antiga()
        dentro = [self.raiz / "copias", self.raiz / "projects" / "p" / "outputs" / "copias"]
        if os.name == "nt":  # o NTFS não distingue caixa
            dentro.append(Path(str(self.raiz).upper()) / "copias-maiusculas")
        for backups in dentro:
            with self.subTest(backups=backups):
                with self.assertRaises(self.mod.Parada) as ctx:
                    self.aplicar(backups, pasta_ensaio=self.tmp / "ensaio-fora")
                self.assertEqual(ctx.exception.etapa, "checar")
                self.assertIn("--backups", ctx.exception.motivo)
                self.assertFalse(backups.exists())
                self.assertFalse(self.trava.exists())
        self.assertFalse((self.tmp / "ensaio-fora").exists())

    def test_politica_que_o_kit_novo_recusaria_aparece_no_checar(self):
        arq = self.raiz / "registry" / "backup_policy.json"
        (self.raiz / "state" / "sub").mkdir()
        criar_ligacao_dir(self.raiz / "atalho", self.raiz / "state")

        def checar():
            with mock.patch.object(self.mod, "cadeia_de_eventos", lambda _r: (True, {})), \
                    mock.patch.object(self.mod, "_plano_instrucoes", lambda _r: {}), \
                    mock.patch.object(self.mod, "rota_sigilosa", lambda _r: {"conferida": True}):
                return self.mod.checar(self.raiz)

        for ruim in ("state ", "STATE", ".GIT", "atalho/sub"):
            with self.subTest(entrada=ruim):
                arq.write_text(json.dumps({"incluir": ["docs", ruim]}), encoding="utf-8")
                res = checar()
                self.assertFalse(res["pode_aplicar"])
                self.assertTrue(any("backup_policy.json" in m and repr(ruim) in m for m in res["motivos"]),
                                res["motivos"])
        for estragada in ("{nao e json", json.dumps({"incluir": "docs"})):
            with self.subTest(estragada=estragada):
                arq.write_text(estragada, encoding="utf-8")
                self.assertTrue(any("backup_policy.json" in m for m in checar()["motivos"]))
        arq.write_text(json.dumps({"incluir": ["docs", "em-uso", ".claude/projetos"]}), encoding="utf-8")
        self.assertFalse(any("backup_policy.json" in m for m in checar()["motivos"]))
        arq.unlink()  # sem a política, o padrão do kit e as áreas da 1.7.10: nada a recusar
        self.assertFalse(any("backup_policy.json" in m for m in checar()["motivos"]))


if __name__ == "__main__":
    unittest.main()
