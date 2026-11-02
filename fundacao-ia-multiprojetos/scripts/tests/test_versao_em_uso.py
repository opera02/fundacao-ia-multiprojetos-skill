"""Versão em uso de um projeto (escopo 0.6 da 1.7.10; desenho §5.4): `scripts/versao_em_uso.py`.

A IA propõe (lista com SHA-256, sem segredo nem pasta ignorada, em outputs/ do projeto); o titular promove com o aceite
assinado sobre aquela proposta e aquele SHA-256 (conferido pelo kit da raiz; aqui, por uma verificação simulada,
salvo no teste que roda o kit de verdade com uma decisão sem assinatura); a troca guarda a anterior, tenta de novo no
WinError 5 e devolve a anterior se a nova não entra; `voltar` e `conferir` fecham o ciclo. Raiz fictícia em pasta
temporária.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import ENV, SCRIPTS, rodar_script

IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"


def carregar():
    spec = importlib.util.spec_from_file_location("_teste_versao_em_uso", SCRIPTS / "versao_em_uso.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


MOD = carregar()


def sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def transitorio() -> PermissionError:
    exc = PermissionError(13, "acesso negado (simulado pelo teste)")
    exc.winerror = 5
    return exc


class _Raiz(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="versao-em-uso-")))
        self.addCleanup(MOD._apagar, self.base)
        self.raiz = self.base / "raiz"
        self.projeto = self.raiz / "projects" / "p"
        self.trabalho = self.projeto / "trabalho"
        for rel, conteudo in (("app.py", b"print('v1')\n"), ("lib/util.py", b"X = 1\n"), ("lib/rascunho.py", b"#\n"),
                              ("dados.csv", b"a,b\n"), (".env", b"CHAVE=ficticia\n"), ("segredos/chave.txt", b"x\n"),
                              ("__pycache__/app.cpython-312.pyc", b"\0"), ("node_modules/m/i.js", b"//\n")):
            (self.trabalho / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.trabalho / rel).write_bytes(conteudo)
        (self.projeto / "decisoes").mkdir(parents=True)
        self.decisao = self.projeto / "decisoes" / "dec-aceite-1.json"
        self.decisao.write_text("{}", encoding="utf-8")
        self.lista = self.base / "lista.txt"
        self.lista.write_text("# o que vai para a versão em uso\n**/*.py\n!lib/rascunho.py\n.env\nsegredos/\n",
                              encoding="utf-8")
        self.em_uso = self.raiz / "em-uso" / "p"

    def propor(self, nome: str = "proposta.json") -> dict:
        return MOD.propor(self.raiz, "p", self.trabalho, self.lista, self.projeto / "outputs" / "versao" / nome)

    def aceite(self, proposta: dict, **mudar):
        v = {"valida": True, "tipo": "aceite", "forca": "assinatura", "motivo": "decisão assinada pelo titular",
             "entrega": {"caminho": proposta["entrega"], "sha256": proposta["sha256"]}, "decisao_id": "dec-aceite-1",
             "sha256_decisao": sha(proposta["sha256"].encode())}  # uma decisão por entrega, como no kit (KIT-F1)
        v.update(mudar)
        return lambda _raiz, _decisao: v

    def promover(self, proposta: dict, **mudar) -> dict:
        return MOD.promover(self.raiz, "p", proposta["proposta"], proposta["sha256"], self.decisao,
                            verificar=self.aceite(proposta, **mudar))

    def registro(self) -> list:
        return [json.loads(l) for l in (self.em_uso / "registro.jsonl").read_text(encoding="utf-8").splitlines()]

    def sem_sobras(self) -> None:
        self.assertEqual([n for n in os.listdir(self.em_uso) if n.startswith(".")], [], "preparo ou trava sobrou")


class TestPropor(_Raiz):
    def test_lista_com_sha256_sem_segredo_nem_pasta_ignorada(self):
        res = self.propor()
        proposta = json.loads(Path(res["proposta"]).read_bytes())
        self.assertEqual(res["sha256"], sha(Path(res["proposta"]).read_bytes()))
        self.assertEqual(res["entrega"], "outputs/versao/proposta.json")
        self.assertEqual([a["caminho"] for a in proposta["arquivos"]], ["app.py", "lib/util.py"])
        for item in proposta["arquivos"]:
            self.assertEqual(item["sha256"], sha((self.trabalho / item["caminho"]).read_bytes()))
        excluidos = {e["caminho"] for e in proposta["excluidos"]}
        self.assertEqual(excluidos, {".env", "segredos/chave.txt"})
        self.assertNotIn("ficticia", json.dumps(res))
        self.assertIn("__pycache__/", res["pastas_ignoradas"]["primeiras"])
        self.assertIsNone(res["diferenca"], "sem versão em uso, não há diferença")
        self.assertTrue(any("decisao preparar" in passo for passo in res["proximos_passos"]))

    def test_pela_linha_de_comando_e_recusas(self):
        saida = self.projeto / "outputs" / "v.json"
        r = rodar_script("versao_em_uso.py", "propor", "--raiz", self.raiz, "--projeto", "p", "--de", self.trabalho,
                         "--lista", self.lista, "--saida", saida)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["sha256"], sha(saida.read_bytes()))
        fora = self.base / "fora"
        fora.mkdir()
        vazia = self.base / "vazia.txt"
        vazia.write_text("# nada\n!x\n", encoding="utf-8")
        nada = self.base / "nada.txt"
        nada.write_text("*.inexistente\n", encoding="utf-8")
        casos = {"saída fora de outputs": ("--de", self.trabalho, "--lista", self.lista, "--saida",
                                           self.projeto / "x.json"),
                 "pasta de fora do projeto": ("--de", fora, "--lista", self.lista, "--saida", saida),
                 "lista sem inclusão": ("--de", self.trabalho, "--lista", vazia, "--saida", saida),
                 "lista que não casa": ("--de", self.trabalho, "--lista", nada, "--saida", saida)}
        for nome, args in casos.items():
            with self.subTest(nome):
                r = rodar_script("versao_em_uso.py", "propor", "--raiz", self.raiz, "--projeto", "p", *args)
                self.assertEqual(r.returncode, 2, r.stdout)

    def test_glob(self):
        casos = [("**/*.py", "a.py", True), ("**/*.py", "x/y/a.py", True), ("*.py", "x/a.py", False),
                 ("lib/", "lib/a/b.txt", True), ("lib/", "libx/a", False), ("a?.txt", "ab.txt", True),
                 ("[!a]b", "cb", True), ("[!a]b", "ab", False), ("src/**/teste_*.py", "src/teste_x.py", True)]
        for padrao, rel, casa in casos:
            with self.subTest(padrao=padrao, rel=rel):
                self.assertEqual(bool(MOD.regex_do_glob(padrao).match(rel)), casa)

    def test_lista_com_glob_invalido_recusa(self):
        ruim = self.base / "ruim.txt"
        ruim.write_text("[z-a]\n", encoding="utf-8")  # faixa de classe inválida: re.error
        with self.assertRaises(MOD.Recusa) as ctx:
            MOD.ler_lista(ruim)
        self.assertIn("glob inválido", str(ctx.exception))


class TestPromoverVoltarConferir(_Raiz):
    def test_ciclo_promover_conferir_promover_voltar(self):
        v1 = self.propor("v1.json")
        res = self.promover(v1)
        atual = self.em_uso / "atual"
        self.assertTrue(res["promovida"])
        self.assertIsNone(res["anterior"])
        self.assertEqual((atual / "app.py").read_bytes(), b"print('v1')\n")
        self.assertFalse((atual / ".env").exists())
        self.assertTrue((atual / MOD.MANIFESTO_DA_VERSAO).is_file())
        r = rodar_script("versao_em_uso.py", "conferir", "--raiz", self.raiz, "--projeto", "p")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        (self.trabalho / "app.py").write_bytes(b"print('v2')\n")
        v2 = self.propor("v2.json")
        res = self.promover(v2)
        self.assertEqual(res["diferenca"]["alterados"], ["app.py"])
        self.assertTrue((self.em_uso / "anteriores" / res["anterior"] / "app.py").is_file())
        self.assertEqual((atual / "app.py").read_bytes(), b"print('v2')\n")
        # Desde a integração da 1.7.10, o voltar exige o aceite assinado de um pedido de volta (simulado aqui).
        pedido = MOD.pedir_volta(self.raiz, "p", self.projeto / "outputs" / "versao" / "volta.json",
                                 motivo="ensaio da volta")
        res = MOD.voltar(self.raiz, "p", pedido["pedido"], pedido["sha256"], self.decisao,
                         verificar=self.aceite(pedido))
        self.assertEqual((atual / "app.py").read_bytes(), b"print('v1')\n")
        self.assertTrue((self.em_uso / "anteriores" / res["a_que_saiu"] / "app.py").is_file())
        self.assertTrue(MOD.conferir(self.raiz, "p")["ok"])
        self.assertEqual([l["acao"] for l in self.registro()], ["promover", "promover", "voltar"])
        self.assertEqual(self.registro()[0]["proposta_sha256"], v1["sha256"])
        self.sem_sobras()

    def test_conferir_acusa_alterado_ausente_a_mais_e_manifesto_trocado(self):
        self.promover(self.propor())
        atual = self.em_uso / "atual"
        (atual / "__pycache__").mkdir()
        (atual / "__pycache__" / "app.cpython-312.pyc").write_bytes(b"\0")  # KIT-F5: a mais (as tarefas rodam com -B)
        self.assertEqual(MOD.conferir(self.raiz, "p")["a_mais"], ["__pycache__/app.cpython-312.pyc"])
        MOD._apagar(atual / "__pycache__")
        self.assertTrue(MOD.conferir(self.raiz, "p")["ok"])
        mudancas = {"alterados": lambda: (atual / "app.py").write_bytes(b"print('outro')\n"),
                    "ausentes": lambda: (atual / "lib" / "util.py").unlink(),
                    "a_mais": lambda: (atual / "extra.py").write_bytes(b"#\n")}
        for campo, mudar in mudancas.items():
            with self.subTest(campo):
                mudar()
                r = rodar_script("versao_em_uso.py", "conferir", "--raiz", self.raiz, "--projeto", "p")
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertTrue(json.loads(r.stdout)[campo])
        # Manifesto refeito para bater com a pasta adulterada: o registro da promoção ainda acusa a troca.
        manifesto = atual / MOD.MANIFESTO_DA_VERSAO
        arquivos = [{"caminho": p.relative_to(atual).as_posix(), "tamanho": p.stat().st_size,
                     "sha256": sha(p.read_bytes())} for p in sorted(atual.rglob("*"))
                    if p.is_file() and "__pycache__" not in p.parts and p.name != MOD.MANIFESTO_DA_VERSAO]
        dados = json.loads(manifesto.read_bytes())
        dados["arquivos"] = arquivos
        manifesto.write_text(json.dumps(dados), encoding="utf-8")
        res = MOD.conferir(self.raiz, "p")
        self.assertEqual((res["alterados"], res["ausentes"], res["a_mais"]), ([], [], []))
        self.assertIs(res["manifesto_confere_com_o_registro"], False)
        self.assertFalse(res["ok"])

    def test_recusas_sem_trocar_nada(self):
        v1 = self.propor()
        self.promover(v1)
        antes = (self.em_uso / "atual" / "app.py").read_bytes()
        (self.trabalho / "app.py").write_bytes(b"print('v2')\n")
        v2 = self.propor("v2.json")
        casos = {"decisão inválida": {"valida": False, "motivo": "assinatura ausente"},
                 "não é aceite": {"tipo": "correcao"}, "sem assinatura": {"forca": "sem-assinatura"},
                 "outra entrega": {"entrega": {"caminho": "outputs/versao/v1.json", "sha256": v2["sha256"]}},
                 "outro SHA-256": {"entrega": {"caminho": v2["entrega"], "sha256": v1["sha256"]}}}
        for nome, mudar in casos.items():
            with self.subTest(nome), self.assertRaises(MOD.Recusa):
                self.promover(v2, **mudar)
        with self.assertRaises(MOD.Recusa):
            MOD.promover(self.raiz, "p", v2["proposta"], "f" * 64, self.decisao, verificar=self.aceite(v2))
        (self.trabalho / "app.py").write_bytes(b"print('trocado depois da proposta')\n")
        with self.assertRaises(MOD.Recusa) as ctx:
            self.promover(v2)
        self.assertIn("difere da proposta", str(ctx.exception))
        self.assertEqual((self.em_uso / "atual" / "app.py").read_bytes(), antes)
        self.assertEqual(len(self.registro()), 1)
        self.sem_sobras()

    def test_proposta_forjada_com_caminho_perigoso_e_recusada(self):
        for caminho in ("../fora.py", ".env", "segredos/chave.txt", "/abs.py", "VERSAO-EM-USO.json",
                        "node_modules/m/i.js"):
            with self.subTest(caminho):
                bruto = json.dumps({"schema_version": MOD.ESQUEMA_PROPOSTA, "projeto": "p", "origem": "trabalho",
                                    "arquivos": [{"caminho": caminho, "tamanho": 1, "sha256": "0" * 64}]}).encode()
                arquivo = self.projeto / "outputs" / "forjada.json"
                arquivo.parent.mkdir(parents=True, exist_ok=True)
                arquivo.write_bytes(bruto)
                proposta = {"proposta": arquivo, "sha256": sha(bruto), "entrega": "outputs/forjada.json"}
                with self.assertRaises(MOD.Recusa):
                    self.promover(proposta)
        self.assertFalse((self.em_uso / "atual").exists())


class TestRegistroEModo(_Raiz):
    def test_registro_que_falha_depois_da_troca_devolve_promovida_e_falhou(self):
        # A troca já aconteceu: a falha do registro não vira a recusa de código 2, mas promovida=True e registro falhou.
        v1 = self.propor("v1.json")
        with mock.patch.object(MOD, "_registrar", side_effect=OSError("disco cheio simulado")):
            res = self.promover(v1)
        self.assertTrue(res["promovida"])
        self.assertTrue(res["registro"].startswith("falhou:"), res["registro"])
        self.assertEqual((self.em_uso / "atual" / "app.py").read_bytes(), b"print('v1')\n")
        self.sem_sobras()

    def test_registro_invalido_antes_da_troca_recusa_sem_trocar(self):
        v1 = self.propor("v1.json")
        self.em_uso.mkdir(parents=True)
        (self.em_uso / "registro.jsonl").mkdir()  # registro é uma pasta: não aceita o anexar
        with self.assertRaises((MOD.Recusa, OSError)):
            self.promover(v1)
        self.assertFalse((self.em_uso / "atual").exists(), "nada foi trocado")
        self.sem_sobras()

    @unittest.skipUnless(os.name != "nt", "o bit de execução (chmod) não tem sentido no Windows")
    def test_modo_de_execucao_preservado_e_conferido(self):
        import stat
        os.chmod(self.trabalho / "app.py", 0o755)
        self.promover(self.propor("v1.json"))
        atual = self.em_uso / "atual"
        self.assertEqual(stat.S_IMODE(os.lstat(atual / "app.py").st_mode) & 0o755, 0o755)
        self.assertTrue(MOD.conferir(self.raiz, "p")["ok"])
        os.chmod(atual / "app.py", 0o644)  # tira o bit de execução
        res = MOD.conferir(self.raiz, "p")
        self.assertEqual(res["modo_diferente"], ["app.py"])
        self.assertFalse(res["ok"])


class TestNovaTentativa(_Raiz):
    def setUp(self):
        super().setUp()
        self.promover(self.propor("v1.json"))
        (self.trabalho / "app.py").write_bytes(b"print('v2')\n")
        self.v2 = self.propor("v2.json")
        self.esperas = []

    def renomear_falhando(self, vezes: int, erro=transitorio):
        real = os.rename
        estado = {"falhas": 0}

        def renomear(origem, destino):
            if Path(origem).name.startswith(".preparo-") and estado["falhas"] < vezes:
                estado["falhas"] += 1
                raise erro()
            real(origem, destino)
        return renomear

    def test_winerror_5_tenta_de_novo_e_promove(self):
        with mock.patch.object(MOD, "_renomear", self.renomear_falhando(2)), \
                mock.patch.object(MOD, "_esperar", self.esperas.append):
            res = self.promover(self.v2)
        self.assertEqual(self.esperas, [1, 2])
        self.assertEqual(res["tentativas_de_renomear"], 1 + 3)
        self.assertEqual((self.em_uso / "atual" / "app.py").read_bytes(), b"print('v2')\n")
        self.sem_sobras()

    def test_falha_persistente_devolve_a_anterior(self):
        with mock.patch.object(MOD, "_renomear", self.renomear_falhando(99)), \
                mock.patch.object(MOD, "_esperar", self.esperas.append), self.assertRaises(MOD.Recusa) as ctx:
            self.promover(self.v2)
        self.assertEqual(self.esperas, list(MOD.ESPERAS))
        self.assertIn("anterior continua em uso", str(ctx.exception))
        self.assertEqual((self.em_uso / "atual" / "app.py").read_bytes(), b"print('v1')\n")
        self.assertEqual(os.listdir(self.em_uso / "anteriores"), [])
        self.sem_sobras()

    def test_erro_que_nao_e_transitorio_nao_espera(self):
        with mock.patch.object(MOD, "_renomear", self.renomear_falhando(1, lambda: OSError(18, "outro volume"))), \
                mock.patch.object(MOD, "_esperar", self.esperas.append), self.assertRaises(MOD.Recusa):
            self.promover(self.v2)
        self.assertEqual(self.esperas, [])
        self.assertEqual((self.em_uso / "atual" / "app.py").read_bytes(), b"print('v1')\n")


class TestKitDaRaiz(unittest.TestCase):
    """A conferência da decisão pelo kit de verdade (`python -m fundacao decisao verificar`): aceite sem assinatura
    não promove. A âncora desta máquina, se houver, não muda o resultado: falta a assinatura."""

    def test_aceite_sem_assinatura_nao_promove(self):
        base = Path(os.path.realpath(tempfile.mkdtemp(prefix="versao-em-uso-kit-")))
        self.addCleanup(MOD._apagar, base)
        raiz = base / "raiz"
        r = rodar_script("instalar_kit.py", "--destino", raiz)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        env = {**ENV, IDENTIDADE: "titular-ensaio"}
        for args in (("init", "--admin", "titular-ensaio"),
                     ("projeto", "criar", "--id", "p", "--nome", "P", "--finalidade", "ensaio da versão em uso")):
            r = subprocess.run([sys.executable, "-B", "-m", "fundacao", "--raiz", str(raiz), *args], cwd=str(raiz),
                               env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        trabalho = raiz / "projects" / "p" / "trabalho"
        trabalho.mkdir()
        (trabalho / "app.py").write_bytes(b"print('ok')\n")
        lista = base / "lista.txt"
        lista.write_text("*.py\n", encoding="utf-8")
        proposta = MOD.propor(raiz, "p", trabalho, lista, raiz / "projects" / "p" / "outputs" / "versao.json")
        d = {"schema_version": "fundacao.decisao_assinada/1", "decisao_id": "dec-aceite-ensaio", "project_id": "p",
             "task_id": "tarefa-ensaio", "tipo": "aceite", "motivo": "ensaio", "assinante": "titular-ensaio",
             "namespace": "fundacao-decisao", "entrega": {"caminho": proposta["entrega"], "sha256": proposta["sha256"]},
             "preparado_em": "2026-10-31T12:00:00+0000"}
        decisao = raiz / "projects" / "p" / "decisoes" / "dec-aceite-ensaio.json"
        decisao.parent.mkdir(parents=True, exist_ok=True)
        decisao.write_bytes((json.dumps(d, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))
        r = subprocess.run([sys.executable, "-B", str(SCRIPTS / "versao_em_uso.py"), "promover", "--raiz", str(raiz),
                            "--projeto", "p", "--proposta", proposta["proposta"], "--proposta-sha256",
                            proposta["sha256"], "--decisao", str(decisao)], env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("assinatura ausente", r.stderr)
        self.assertFalse((raiz / "em-uso").exists(), "nada da versão em uso nasce antes do aceite conferido")


if __name__ == "__main__":
    unittest.main()
