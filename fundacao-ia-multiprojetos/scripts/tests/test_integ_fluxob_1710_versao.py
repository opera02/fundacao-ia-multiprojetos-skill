"""Integração do fluxo B na 1.7.10 (pacote INTEG-FLUXOB do lote 2), itens 5 e 6, na versão em uso
(`scripts/versao_em_uso.py`).

Item 5: o `voltar` exige a decisão assinada do titular, conferida como no `promover` — aceite, assinado, sobre o pedido
de volta (`pedir-volta`, em `outputs/`) e esse SHA-256 —, e um aceite vale para uma volta só. Independe do sandbox:
com a raiz em `/mnt/e`, ele não confina os comandos da sessão (contratos do lote 2, §0).
Item 6: a cópia do `promover` é a cópia única da skill (`copia_segura.copiar_conferindo`, contratos do lote 2, §8), com
o SHA-256 da proposta, `modo=None` e a pasta do projeto como `dentro_de`.
Revisão do pacote: o registro que não se lê recusa (falha fechada: valer como vazio liberava o reuso do aceite, e os
bytes fora do UTF-8 saíam como traceback), e o pedido sem `--para` não vale depois de uma promoção ou volta posterior a
ele (o aceite não prende qual é a anterior mais recente).
A verificação do kit é simulada, salvo no teste que roda o kit de verdade com uma decisão sem assinatura. Raiz fictícia
em pasta temporária.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from apoio import ENV, SCRIPTS, rodar_script

IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"


def carregar():
    spec = importlib.util.spec_from_file_location("_teste_integ_versao", SCRIPTS / "versao_em_uso.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


MOD = carregar()


def aceite(alvo: dict, **mudar):
    """A verificação simulada do kit: aceite assinado sobre a entrega `alvo` (proposta ou pedido), salvo `mudar`."""
    v = {"valida": True, "tipo": "aceite", "forca": "assinatura", "motivo": "decisão assinada pelo titular",
         "entrega": {"caminho": alvo["entrega"], "sha256": alvo["sha256"]}, "decisao_id": "dec-1",
         "sha256_decisao": hashlib.sha256(alvo["sha256"].encode()).hexdigest()}
    v.update(mudar)
    return lambda _raiz, _decisao: v


class _Raiz(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="integ-versao-")))
        self.addCleanup(MOD._apagar, self.base)
        self.raiz = self.base / "raiz"
        self.projeto = self.raiz / "projects" / "p"
        self.trabalho = self.projeto / "trabalho"
        for rel, conteudo in (("app.py", b"print('v1')\n"), ("lib/util.py", b"X = 1\n")):
            (self.trabalho / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.trabalho / rel).write_bytes(conteudo)
        (self.projeto / "decisoes").mkdir(parents=True)
        self.decisao = self.projeto / "decisoes" / "dec-1.json"
        self.decisao.write_text("{}", encoding="utf-8")
        self.lista = self.base / "lista.txt"
        self.lista.write_text("**/*.py\n", encoding="utf-8")
        self.em_uso = self.raiz / "em-uso" / "p"

    def promover(self, nome: str, conteudo: bytes) -> dict:
        (self.trabalho / "app.py").write_bytes(conteudo)
        proposta = MOD.propor(self.raiz, "p", self.trabalho, self.lista, self.projeto / "outputs" / "versao" / nome)
        return MOD.promover(self.raiz, "p", proposta["proposta"], proposta["sha256"], self.decisao,
                            verificar=aceite(proposta))

    def pedir(self, nome: str = "volta.json", **extra) -> dict:
        return MOD.pedir_volta(self.raiz, "p", self.projeto / "outputs" / "versao" / nome,
                               motivo="voltar a versão que funcionava", **extra)

    def atual(self) -> bytes:
        return (self.em_uso / "atual" / "app.py").read_bytes()


class TestVoltarExigeOAceite(_Raiz):
    def setUp(self):
        super().setUp()
        self.promover("v1.json", b"print('v1')\n")
        self.promover("v2.json", b"print('v2')\n")

    def test_sem_o_aceite_assinado_do_pedido_nada_e_trocado(self):
        pedido = self.pedir()
        outra = self.pedir("outra.json")
        casos = {"decisão inválida": {"valida": False, "motivo": "assinatura ausente"},
                 "não é aceite": {"tipo": "correcao"}, "sem assinatura": {"forca": "sem-assinatura"},
                 "outra entrega": {"entrega": {"caminho": outra["entrega"], "sha256": pedido["sha256"]}},
                 "outro SHA-256": {"entrega": {"caminho": pedido["entrega"], "sha256": outra["sha256"]}}}
        for nome, mudar in casos.items():
            with self.subTest(nome):
                with self.assertRaises(MOD.Recusa) as ctx:
                    MOD.voltar(self.raiz, "p", pedido["pedido"], pedido["sha256"], self.decisao,
                               verificar=aceite(pedido, **mudar))
                self.assertIn("nada foi trocado", str(ctx.exception))
        with self.assertRaises(MOD.Recusa):  # o SHA-256 informado não é o do pedido
            MOD.voltar(self.raiz, "p", pedido["pedido"], "f" * 64, self.decisao, verificar=aceite(pedido))
        self.assertEqual(self.atual(), b"print('v2')\n")
        res = MOD.voltar(self.raiz, "p", pedido["pedido"], pedido["sha256"], self.decisao, verificar=aceite(pedido))
        self.assertTrue(res["voltou"])
        self.assertEqual(self.atual(), b"print('v1')\n")
        ultima = json.loads((self.em_uso / "registro.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual((ultima["acao"], ultima["pedido_sha256"], ultima["decisao_id"]),
                         ("voltar", pedido["sha256"], "dec-1"))

    def test_um_aceite_vale_para_uma_volta_so(self):
        pedido = self.pedir()
        MOD.voltar(self.raiz, "p", pedido["pedido"], pedido["sha256"], self.decisao, verificar=aceite(pedido))
        self.promover("v3.json", b"print('v3')\n")
        with self.assertRaises(MOD.Recusa) as ctx:
            MOD.voltar(self.raiz, "p", pedido["pedido"], pedido["sha256"], self.decisao, verificar=aceite(pedido))
        self.assertIn("uma volta só", str(ctx.exception))
        self.assertEqual(self.atual(), b"print('v3')\n")

    def test_pedido_forjado_ou_fora_de_outputs_recusa(self):
        validos = {"schema_version": MOD.ESQUEMA_VOLTA, "projeto": "p", "para": None, "motivo": "x",
                   "criado_em": MOD._instante()}
        for nome, mudar in {"outro esquema": {"schema_version": "x"}, "outro projeto": {"projeto": "q"},
                            "anterior com caminho": {"para": "../fora"}, "sem motivo": {"motivo": " "},
                            "sem data": {"criado_em": None}, "data sem fuso": {"criado_em": "2026-10-31T12:00:00"},
                            "data fora do ISO": {"criado_em": "31/10/2026"}}.items():
            with self.subTest(nome):
                bruto = json.dumps({**validos, **mudar}).encode("utf-8")
                arquivo = self.projeto / "outputs" / "forjado.json"
                arquivo.write_bytes(bruto)
                entrega = {"entrega": "outputs/forjado.json", "sha256": hashlib.sha256(bruto).hexdigest()}
                with self.assertRaises(MOD.Recusa):
                    MOD.voltar(self.raiz, "p", arquivo, entrega["sha256"], self.decisao, verificar=aceite(entrega))
        fora = self.projeto / "volta.json"
        fora.write_bytes(b"{}")
        with self.assertRaises(MOD.Recusa):
            MOD.voltar(self.raiz, "p", fora, hashlib.sha256(b"{}").hexdigest(), self.decisao,
                       verificar=aceite({"entrega": "volta.json", "sha256": hashlib.sha256(b"{}").hexdigest()}))
        for para in ("../x", "a/b"):
            with self.subTest(para=para), self.assertRaises(MOD.Recusa):
                self.pedir(para=para)
        self.assertEqual(self.atual(), b"print('v2')\n")

    def test_registro_que_falha_depois_da_volta_sai_com_codigo_3(self):
        pedido = self.pedir()
        args = ["voltar", "--raiz", str(self.raiz), "--projeto", "p", "--pedido", pedido["pedido"],
                "--pedido-sha256", pedido["sha256"], "--decisao", str(self.decisao)]
        with mock.patch.object(MOD, "verificar_decisao_pelo_kit", aceite(pedido)), \
                mock.patch.object(MOD, "_registrar", side_effect=OSError("disco cheio simulado")), \
                mock.patch.object(sys, "stdout", io.StringIO()) as saida:
            codigo = MOD.main(args)
        self.assertEqual(codigo, 3)
        self.assertTrue(json.loads(saida.getvalue())["registro"].startswith("falhou:"))
        self.assertEqual(self.atual(), b"print('v1')\n")

    def test_linha_de_comando_do_pedido_e_o_voltar_antigo_recusado(self):
        saida = self.projeto / "outputs" / "versao" / "cli.json"
        r = rodar_script("versao_em_uso.py", "pedir-volta", "--raiz", self.raiz, "--projeto", "p", "--saida", saida,
                         "--motivo", "voltar pela linha de comando")
        self.assertEqual(r.returncode, 0, r.stderr)
        res = json.loads(r.stdout)
        self.assertEqual(res["sha256"], hashlib.sha256(saida.read_bytes()).hexdigest())
        self.assertTrue(any("voltar" in passo and "--pedido-sha256" in passo for passo in res["proximos_passos"]))
        self.assertEqual(rodar_script("versao_em_uso.py", "voltar", "--raiz", self.raiz, "--projeto", "p").returncode,
                         2, "voltar sem pedido e sem decisão é uso incorreto")
        self.assertEqual(self.atual(), b"print('v2')\n")


class TestRegistroEDataDoPedido(_Raiz):
    """Revisão do pacote: o registro ilegível não vale como vazio, e o pedido sem --para tem data."""

    def setUp(self):
        super().setUp()
        self.promover("v1.json", b"print('v1')\n")
        self.promover("v2.json", b"print('v2')\n")

    @staticmethod
    def instante(segundos: int) -> str:
        """Uma data depois de agora (as promoções do setUp ficam antes dela), com `segundos` a mais; dentro da folga do
        relógio (`FOLGA_DO_RELOGIO`, 5 minutos), além da qual o pedido sem --para no futuro recusa."""
        return (datetime.now(timezone.utc) + timedelta(minutes=1, seconds=segundos)).isoformat(timespec="microseconds")

    def test_registro_com_bytes_fora_do_utf8_recusa_o_voltar_e_o_conferir(self):
        pedido = self.pedir()
        with open(self.em_uso / "registro.jsonl", "ab") as f:
            f.write(b'{"acao": "voltar", "motivo": "\xff\xfe"}\n')
        with self.assertRaises(MOD.Recusa) as ctx:
            MOD.voltar(self.raiz, "p", pedido["pedido"], pedido["sha256"], self.decisao, verificar=aceite(pedido))
        self.assertIn("não se lê (UnicodeDecodeError)", str(ctx.exception))
        self.assertIn("nada foi trocado", str(ctx.exception))
        args = ["voltar", "--raiz", str(self.raiz), "--projeto", "p", "--pedido", pedido["pedido"],
                "--pedido-sha256", pedido["sha256"], "--decisao", str(self.decisao)]
        with mock.patch.object(MOD, "verificar_decisao_pelo_kit", aceite(pedido)), \
                mock.patch.object(sys, "stderr", io.StringIO()) as erro:
            self.assertEqual(MOD.main(args), 2, "recusa (código 2), não traceback (código 1)")
        self.assertIn("não se lê", json.loads(erro.getvalue())["erro"])
        r = rodar_script("versao_em_uso.py", "conferir", "--raiz", self.raiz, "--projeto", "p")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(self.atual(), b"print('v2')\n")

    def test_registro_que_e_pasta_nao_libera_o_reuso_do_aceite(self):
        registro = self.em_uso / "registro.jsonl"
        registro.unlink()
        registro.mkdir()  # existe e não se lê: antes, o reuso do aceite ficava liberado (falha aberta)
        with self.assertRaises(MOD.Recusa) as ctx:
            MOD._ja_usados_na_volta(registro)
        self.assertIn("se este aceite já foi usado", str(ctx.exception))
        self.assertEqual(MOD._ja_usados_na_volta(self.em_uso / "nao-existe.jsonl"), set(), "sem registro, nenhum")

    def test_pedido_sem_para_nao_vale_depois_de_outra_promocao(self):
        with mock.patch.object(MOD, "_instante", return_value=self.instante(0)):
            pedido = self.pedir()  # pedido para "a anterior mais recente" (a v1, hoje)
        with mock.patch.object(MOD, "_instante", return_value=self.instante(5)):
            self.promover("v3.json", b"print('v3')\n")  # depois do pedido: a mais recente passa a ser a v2
        with self.assertRaises(MOD.Recusa) as ctx:
            MOD.voltar(self.raiz, "p", pedido["pedido"], pedido["sha256"], self.decisao, verificar=aceite(pedido))
        self.assertIn("houve promoção ou volta depois do pedido", str(ctx.exception))
        self.assertEqual(self.atual(), b"print('v3')\n", "nada foi trocado")
        # Com --para, o aceite prende qual anterior volta: a promoção posterior não muda o que ele diz.
        primeira = sorted(os.listdir(self.em_uso / "anteriores"))[0]
        with mock.patch.object(MOD, "_instante", return_value=self.instante(10)):
            certo = self.pedir("certo.json", para=primeira)
        MOD.voltar(self.raiz, "p", certo["pedido"], certo["sha256"], self.decisao, verificar=aceite(certo))
        self.assertEqual(self.atual(), b"print('v1')\n")

    def test_pedido_sem_para_feito_depois_da_ultima_promocao_vale(self):
        with mock.patch.object(MOD, "_instante", return_value=self.instante(0)):
            pedido = self.pedir()
        MOD.voltar(self.raiz, "p", pedido["pedido"], pedido["sha256"], self.decisao, verificar=aceite(pedido))
        self.assertEqual(self.atual(), b"print('v1')\n")


class TestPedidoComDataNoFuturo(_Raiz):
    """Segunda revisão do pacote: quem grava o pedido de volta é a sessão; com a data no futuro, nenhuma promoção
    posterior recusaria o voltar sem --para. Além da folga do relógio (5 minutos), recusa; com --para, a data não
    escolhe nada e não recusa."""

    def setUp(self):
        super().setUp()
        self.promover("v1.json", b"print('v1')\n")
        self.promover("v2.json", b"print('v2')\n")

    def test_pedido_sem_para_com_data_no_futuro_recusa_e_nada_e_trocado(self):
        with mock.patch.object(MOD, "_instante", return_value="2099-01-01T00:00:00+00:00"):
            pedido = self.pedir()
        with self.assertRaises(MOD.Recusa) as ctx:
            MOD.voltar(self.raiz, "p", pedido["pedido"], pedido["sha256"], self.decisao, verificar=aceite(pedido))
        self.assertIn("data no futuro", str(ctx.exception))
        self.assertIn("nada foi trocado", str(ctx.exception))
        self.assertEqual(self.atual(), b"print('v2')\n")
        primeira = sorted(os.listdir(self.em_uso / "anteriores"))[0]
        with mock.patch.object(MOD, "_instante", return_value="2099-01-01T00:00:00+00:00"):
            certo = self.pedir("certo.json", para=primeira)  # com --para, a data não escolhe a anterior
        MOD.voltar(self.raiz, "p", certo["pedido"], certo["sha256"], self.decisao, verificar=aceite(certo))
        self.assertEqual(self.atual(), b"print('v1')\n")

    def test_folga_do_relogio(self):
        agora = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
        base = {"schema_version": MOD.ESQUEMA_VOLTA, "projeto": "p", "para": None, "motivo": "voltar (fictício)"}
        dentro = (agora + MOD.FOLGA_DO_RELOGIO - timedelta(seconds=1)).isoformat()
        fora = (agora + MOD.FOLGA_DO_RELOGIO + timedelta(seconds=1)).isoformat()
        self.assertEqual(MOD.FOLGA_DO_RELOGIO, timedelta(minutes=5))
        self.assertIsNone(MOD.validar_pedido({**base, "criado_em": dentro}, "p", agora=agora)[0])
        self.assertIsNone(MOD.validar_pedido({**base, "criado_em": agora.isoformat()}, "p", agora=agora)[0])
        with self.assertRaises(MOD.Recusa):
            MOD.validar_pedido({**base, "criado_em": fora}, "p", agora=agora)
        with self.assertRaises(MOD.Recusa):  # o fuso não esconde a data no futuro
            MOD.validar_pedido({**base, "criado_em": "2026-11-01T09:30:00-03:00"}, "p", agora=agora)
        self.assertEqual(MOD.validar_pedido({**base, "para": "x1", "criado_em": fora}, "p", agora=agora)[0], "x1")


class TestCopiaUnicaNoPromover(_Raiz):
    def test_promover_copia_pela_copia_unica_com_o_sha256_da_proposta(self):
        chamadas = []
        real = MOD.COPIA.copiar_conferindo

        def espiao(origem, destino, **kw):
            chamadas.append(kw)
            return real(origem, destino, **kw)

        with mock.patch.object(MOD.COPIA, "copiar_conferindo", side_effect=espiao):
            self.promover("v1.json", b"print('v1')\n")
        proposta = json.loads((self.projeto / "outputs" / "versao" / "v1.json").read_bytes())
        self.assertEqual(sorted(c["sha256_esperado"] for c in chamadas),
                         sorted(a["sha256"] for a in proposta["arquivos"]))
        self.assertTrue(all(c["modo"] is None and Path(c["dentro_de"]) == self.projeto for c in chamadas), chamadas)

    def test_arquivo_trocado_por_vinculo_fisico_depois_da_proposta_recusa(self):
        proposta = MOD.propor(self.raiz, "p", self.trabalho, self.lista, self.projeto / "outputs" / "v.json")
        fora = self.base / "fora.py"
        fora.write_bytes((self.trabalho / "lib" / "util.py").read_bytes())  # mesmo conteúdo, mesmo SHA-256
        (self.trabalho / "lib" / "util.py").unlink()
        try:
            os.link(fora, self.trabalho / "lib" / "util.py")
        except OSError as exc:
            self.skipTest(f"vínculo físico indisponível: {exc}")
        with self.assertRaises(MOD.Recusa) as ctx:
            MOD.promover(self.raiz, "p", proposta["proposta"], proposta["sha256"], self.decisao,
                         verificar=aceite(proposta))
        self.assertIn("vínculo físico", str(ctx.exception))
        self.assertFalse((self.em_uso / "atual").exists(), "nada foi trocado")


class TestKitDaRaiz(unittest.TestCase):
    """O voltar pelo kit de verdade (`python -m fundacao decisao verificar`): aceite sem assinatura não volta."""

    def test_voltar_com_aceite_sem_assinatura_recusa(self):
        base = Path(os.path.realpath(tempfile.mkdtemp(prefix="integ-versao-kit-")))
        self.addCleanup(MOD._apagar, base)
        raiz = base / "raiz"
        r = rodar_script("instalar_kit.py", "--destino", raiz)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        env = {**ENV, IDENTIDADE: "titular-ensaio"}
        for args in (("init", "--admin", "titular-ensaio"),
                     ("projeto", "criar", "--id", "p", "--nome", "P", "--finalidade", "ensaio da volta")):
            r = subprocess.run([sys.executable, "-B", "-m", "fundacao", "--raiz", str(raiz), *args], cwd=str(raiz),
                               env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        projeto = raiz / "projects" / "p"
        (projeto / "trabalho").mkdir()
        lista = base / "lista.txt"
        lista.write_text("*.py\n", encoding="utf-8")
        for n, versao in enumerate((b"print('v1')\n", b"print('v2')\n"), 1):  # duas promoções deixam uma anterior
            (projeto / "trabalho" / "app.py").write_bytes(versao)
            prop = MOD.propor(raiz, "p", projeto / "trabalho", lista, projeto / "outputs" / f"v{n}.json")
            MOD.promover(raiz, "p", prop["proposta"], prop["sha256"], projeto / "decisoes" / "x.json",
                         verificar=aceite(prop))
        pedido = MOD.pedir_volta(raiz, "p", projeto / "outputs" / "volta.json", motivo="ensaio")
        d = {"schema_version": "fundacao.decisao_assinada/1", "decisao_id": "dec-volta", "project_id": "p",
             "task_id": "tarefa-ensaio", "tipo": "aceite", "motivo": "ensaio", "assinante": "titular-ensaio",
             "namespace": "fundacao-decisao", "entrega": {"caminho": pedido["entrega"], "sha256": pedido["sha256"]},
             "preparado_em": "2026-10-31T12:00:00+0000"}
        decisao = projeto / "decisoes" / "dec-volta.json"
        decisao.parent.mkdir(parents=True, exist_ok=True)
        decisao.write_bytes((json.dumps(d, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))
        r = subprocess.run([sys.executable, "-B", str(SCRIPTS / "versao_em_uso.py"), "voltar", "--raiz", str(raiz),
                            "--projeto", "p", "--pedido", pedido["pedido"], "--pedido-sha256", pedido["sha256"],
                            "--decisao", str(decisao)], env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=300)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("assinatura ausente", r.stderr)
        self.assertEqual((raiz / "em-uso" / "p" / "atual" / "app.py").read_bytes(), b"print('v2')\n")


if __name__ == "__main__":
    unittest.main()
