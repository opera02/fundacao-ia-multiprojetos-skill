"""Revisão de segurança da 1.7.10, grupo VERSAO: a versão em uso (`scripts/versao_em_uso.py`).

KIT-F1: o `promover` aceitava de novo um aceite já usado e repunha uma versão substituída sem assinatura nova (v1
promovida, v2 promovida, a proposta e a decisão da v1 de novo: a v1 voltava para `atual/`, e o registro mostrava a
mesma decisão duas vezes). Agora um aceite vale para uma promoção só (o registro guarda a proposta e a decisão usadas,
como no `voltar`), e a proposta vale para a troca a partir da versão em uso de quando foi feita: o manifesto dela que o
`propor` leu (`manifesto_em_uso`) precisa ser o de agora, e promoção ou volta registrada depois da data da proposta
recusa. Quando a sessão não lê `em-uso/` (Ubuntu), a âncora vem da cópia que o promover grava em `outputs/` (revisão 1
da correção; o resto dela em test_versao_em_uso_ancora_1710.py), e a data no futuro além da folga do relógio recusa.
KIT-F5: o `conferir` pulava `__pycache__`, `.venv`, `venv` e `node_modules` (e `.git` e os caches de ferramenta): um
.pyc plantado em `atual/__pycache__/` rodava, mesmo com `python -B` (que só não grava), e o conferir dizia ok. Agora o
`__pycache__` e as outras pastas que o manifesto ignora contam como a mais, também na anterior do `voltar`; `.venv`,
`venv` (ambiente virtual de verdade, com `pyvenv.cfg`) e `node_modules` não são conferidas, e o conferir o diz ("não
conferido: <pasta>"), nunca num ok calado.
A verificação do kit é simulada, como nos testes do pacote. Raiz fictícia em pasta temporária.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import itertools
import json
import os
import py_compile
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from apoio import SCRIPTS, rodar_script

DEPENDENCIAS = {".venv", "venv", "node_modules"}  # as pastas que o conferir diz não conferir (KIT-F5)
PYC = f"util.{sys.implementation.cache_tag}.pyc"


def carregar():
    spec = importlib.util.spec_from_file_location("_teste_versao_revisao_1710", SCRIPTS / "versao_em_uso.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


MOD = carregar()


def sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def aceite(alvo: dict, **mudar):
    """A verificação simulada do kit: aceite assinado sobre a entrega `alvo` (proposta ou pedido); cada decisão tem o
    seu SHA-256, como no kit (o dos bytes da decisão, que levam a entrega)."""
    v = {"valida": True, "tipo": "aceite", "forca": "assinatura", "motivo": "decisão assinada pelo titular",
         "entrega": {"caminho": alvo["entrega"], "sha256": alvo["sha256"]}, "decisao_id": "dec-" + alvo["sha256"][:8],
         "sha256_decisao": sha(b"decisao ficticia de " + alvo["sha256"].encode())}
    v.update(mudar)
    return lambda _raiz, _decisao: v


class _Raiz(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="versao-revisao-")))
        self.addCleanup(MOD._apagar, self.base)
        self.raiz = self.base / "raiz"
        self.projeto = self.raiz / "projects" / "p"
        self.trabalho = self.projeto / "trabalho"
        self.trabalho.mkdir(parents=True)
        (self.trabalho / "main.py").write_bytes(b"import util\nprint('resultado:', util.QUEM)\n")
        (self.projeto / "decisoes").mkdir()
        self.decisao = self.projeto / "decisoes" / "dec.json"
        self.decisao.write_text("{}", encoding="utf-8")
        self.lista = self.base / "lista.txt"
        self.lista.write_text("**/*.py\n", encoding="utf-8")
        self.em_uso = self.raiz / "em-uso" / "p"
        self.atual = self.em_uso / "atual"

    def devolver(self, quem: str) -> None:
        """Os bytes de uma versão na pasta de trabalho (a sessão pode devolver os de uma antiga: sem eles, a cópia
        recusa)."""
        (self.trabalho / "util.py").write_bytes(f"QUEM = {quem!r}\n".encode())

    def propor(self, nome: str, quem: str) -> dict:
        self.devolver(quem)
        return MOD.propor(self.raiz, "p", self.trabalho, self.lista, self.projeto / "outputs" / "versao" / nome)

    def forjar(self, nome: str, quem: str, **mudar) -> dict:
        """Uma proposta da pasta de trabalho com campos trocados: quem grava a proposta é a sessão."""
        dados = json.loads(Path(self.propor(nome, quem)["proposta"]).read_bytes())
        dados.update(mudar)
        bruto = (json.dumps(dados, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        arquivo = self.projeto / "outputs" / "versao" / nome
        arquivo.write_bytes(bruto)
        return {"proposta": str(arquivo), "sha256": sha(bruto), "entrega": f"outputs/versao/{nome}"}

    def promover(self, proposta: dict, **mudar) -> dict:
        return MOD.promover(self.raiz, "p", proposta["proposta"], proposta["sha256"], self.decisao,
                            verificar=aceite(proposta, **mudar))

    def pedir_e_voltar(self) -> dict:
        pedido = MOD.pedir_volta(self.raiz, "p", self.projeto / "outputs" / "versao" / "volta.json",
                                 motivo="voltar a anterior (fictício)")
        return MOD.voltar(self.raiz, "p", pedido["pedido"], pedido["sha256"], self.decisao, verificar=aceite(pedido))

    def em_uso_agora(self) -> bytes:
        return (self.atual / "util.py").read_bytes()

    @staticmethod
    def escondido():
        """A sessão do Ubuntu: em-uso/ fica fora da leitura e parece ausente (a âncora vem da cópia em outputs/)."""
        return mock.patch.object(MOD, "_em_uso", lambda raiz, projeto: Path(raiz) / "em-uso-fora-da-leitura" / projeto)

    def registro(self) -> list:
        return [json.loads(l) for l in (self.em_uso / "registro.jsonl").read_text(encoding="utf-8").splitlines()]

    @staticmethod
    def relogio():
        """Cada chamada de `_instante` (proposta, pedido e linha do registro) um segundo depois da anterior, a partir de
        uma hora atrás: a ordem não depende da resolução do relógio do sistema."""
        inicio, passo = datetime.now(timezone.utc) - timedelta(hours=1), itertools.count()
        return mock.patch.object(MOD, "_instante", side_effect=lambda: (
            inicio + timedelta(seconds=next(passo))).isoformat(timespec="microseconds"))


class TestUmAceiteUmaPromocao(_Raiz):
    """KIT-F1: promover v1, promover v2, reusar o aceite da v1 -> recusa, nada trocado; e as variantes do caminho."""

    def test_reusar_o_aceite_da_v1_depois_da_v2_recusa_e_nada_e_trocado(self):
        v1 = self.propor("v1.json", "v1")
        self.promover(v1)
        v2 = self.propor("v2.json", "v2-correcao")
        self.promover(v2)
        anteriores = sorted(os.listdir(self.em_uso / "anteriores"))
        self.devolver("v1")
        with self.assertRaises(MOD.Recusa) as ctx:
            self.promover(v1)
        self.assertIn("uma promoção só", str(ctx.exception))
        self.assertIn("nada foi trocado", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v2-correcao'\n")
        self.assertEqual(sorted(os.listdir(self.em_uso / "anteriores")), anteriores)
        self.assertEqual([l["proposta_sha256"] for l in self.registro()], [v1["sha256"], v2["sha256"]])
        self.assertTrue(MOD.conferir(self.raiz, "p")["ok"])
        self.assertEqual([n for n in os.listdir(self.em_uso) if n.startswith(".")], [], "preparo ou trava sobrou")

    def test_pela_linha_de_comando_o_reuso_sai_com_codigo_2(self):
        v1 = self.propor("v1.json", "v1")
        self.promover(v1)
        self.promover(self.propor("v2.json", "v2"))
        self.devolver("v1")
        args = ["promover", "--raiz", str(self.raiz), "--projeto", "p", "--proposta", v1["proposta"],
                "--proposta-sha256", v1["sha256"], "--decisao", str(self.decisao)]
        with mock.patch.object(MOD, "verificar_decisao_pelo_kit", aceite(v1)), \
                mock.patch.object(sys, "stdout", io.StringIO()), \
                mock.patch.object(sys, "stderr", io.StringIO()) as erro:
            self.assertEqual(MOD.main(args), 2)
        self.assertIn("uma promoção só", json.loads(erro.getvalue())["erro"])
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v2'\n")

    def test_a_decisao_ja_usada_nao_faz_outra_troca(self):
        v1 = self.propor("v1.json", "v1")
        self.promover(v1)
        usada = aceite(v1)(None, None)["sha256_decisao"]
        with self.assertRaises(MOD.Recusa) as ctx:
            self.promover(self.propor("v2.json", "v2"), sha256_decisao=usada)
        self.assertIn("uma promoção só", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")

    def test_aceite_nao_usado_de_proposta_feita_antes_da_ultima_troca_recusa(self):
        # O titular assinou a v1 e não a promoveu; a v2, proposta depois, foi promovida: a v1 era a troca a partir da
        # v0, que já saiu (o aceite não usado também não vale).
        self.promover(self.propor("v0.json", "v0"))
        v1 = self.propor("v1.json", "v1")
        self.promover(self.propor("v2.json", "v2"))
        self.devolver("v1")
        with self.assertRaises(MOD.Recusa) as ctx:
            self.promover(v1)
        self.assertIn("mudou depois da proposta", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v2'\n")
        self.promover(self.propor("v1-de-novo.json", "v1"))  # proposta de novo, sobre a versão em uso de agora: vale
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")

    def test_sem_leitura_de_em_uso_vale_a_copia_da_ancora(self):
        # Na sessão do Ubuntu, em-uso/ fica fora da leitura: o propor lê a âncora da cópia que o promover grava em
        # outputs/ (revisão 1 da correção: a proposta sem âncora não vale mais com versão em uso; a data, contra o
        # registro gravado no terminal do titular, é a segunda camada).
        with self.relogio():
            self.promover(self.propor("v0.json", "v0"))
            with self.escondido():
                v1, v2 = self.propor("v1.json", "v1"), self.propor("v2.json", "v2")
            self.assertEqual(json.loads(Path(v1["proposta"]).read_bytes())["manifesto_em_uso"],
                             sha((self.atual / MOD.MANIFESTO_DA_VERSAO).read_bytes()))
            self.promover(v2)
            self.devolver("v1")
            with self.assertRaises(MOD.Recusa) as ctx:
                self.promover(v1)
            self.assertIn("mudou depois da proposta", str(ctx.exception))
            self.assertEqual(self.em_uso_agora(), b"QUEM = 'v2'\n")
            with self.escondido():
                v1 = self.propor("v1-de-novo.json", "v1")
            self.promover(v1)
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")

    def test_o_aceite_da_v2_nao_a_repoe_depois_de_uma_volta(self):
        self.promover(self.propor("v1.json", "v1"))
        v2 = self.propor("v2.json", "v2")
        self.promover(v2)
        self.pedir_e_voltar()
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")
        self.devolver("v2")
        with self.assertRaises(MOD.Recusa) as ctx:
            self.promover(v2)
        self.assertIn("nada foi trocado", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")

    def test_proposta_sem_data_ou_com_data_no_futuro_recusa(self):
        # Com a data no futuro, nenhuma troca posterior recusaria o aceite: além da folga do relógio, recusa.
        self.promover(self.propor("v1.json", "v1"))
        futuro = (datetime.now(timezone.utc) + MOD.FOLGA_DO_RELOGIO + timedelta(minutes=2)).isoformat()
        for nome, criada_em in (("futuro.json", futuro), ("sem-data.json", None),
                                ("sem-fuso.json", "2026-11-01T12:00:00")):
            with self.subTest(nome):
                with self.assertRaises(MOD.Recusa) as ctx:
                    self.promover(self.forjar(nome, "v2", criada_em=criada_em))
                self.assertIn("nada foi trocado", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")
        dentro = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
        self.promover(self.forjar("dentro.json", "v2", criada_em=dentro))  # dentro da folga do relógio: vale
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v2'\n")

    def test_registro_que_nao_se_le_recusa_o_promover(self):
        # Valer como vazio liberaria o reuso do aceite: falha fechada, como no voltar.
        self.promover(self.propor("v1.json", "v1"))
        v2 = self.propor("v2.json", "v2")
        with open(self.em_uso / "registro.jsonl", "ab") as f:
            f.write(b'{"acao": "promover", "motivo": "\xff\xfe"}\n')
        with self.assertRaises(MOD.Recusa) as ctx:
            self.promover(v2)
        self.assertIn("não se lê", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")

    def test_promocao_que_falhou_antes_da_troca_nao_gasta_o_aceite(self):
        # O uso normal continua: a nova tentativa, com o mesmo aceite, promove.
        self.promover(self.propor("v1.json", "v1"))
        v2 = self.propor("v2.json", "v2")
        real = os.rename

        def renomear(origem, destino):
            if Path(origem).name.startswith(".preparo-"):
                exc = PermissionError(13, "acesso negado (simulado pelo teste)")
                exc.winerror = 5
                raise exc
            real(origem, destino)
        with mock.patch.object(MOD, "_renomear", renomear), mock.patch.object(MOD, "_esperar", lambda _s: None), \
                self.assertRaises(MOD.Recusa):
            self.promover(v2)
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")
        self.promover(v2)
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v2'\n")


class TestConferirNaoPulaPastas(_Raiz):
    """KIT-F5: o que o conferir não confere ele diz; o resto conta."""

    def setUp(self):
        super().setUp()
        self.promover(self.propor("v1.json", "LEGITIMO"))

    def tarefa(self, *opcoes) -> str:
        """A tarefa rodada de atual/, como o envoltório a rodaria, sem o ambiente do teste (-E)."""
        r = subprocess.run([sys.executable, "-E", "-s", *opcoes, "main.py"], cwd=str(self.atual), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_pyc_plantado_roda_mesmo_com_python_B_e_o_conferir_acusa(self):
        fonte = self.base / "plantado" / "util.py"
        fonte.parent.mkdir()
        fonte.write_bytes(b"QUEM = 'INJETADO'\n")
        (self.atual / "__pycache__").mkdir()
        py_compile.compile(str(fonte), cfile=str(self.atual / "__pycache__" / PYC), doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
        self.assertEqual(self.tarefa("-B"), "resultado: INJETADO", "o -B só não grava: o .pyc plantado roda")
        fora = self.base / "pycache-fora-de-em-uso"
        self.assertEqual(self.tarefa("-B", "-X", f"pycache_prefix={fora}"), "resultado: LEGITIMO")
        res = MOD.conferir(self.raiz, "p")
        self.assertEqual(res["a_mais"], [f"__pycache__/{PYC}"])
        self.assertFalse(res["ok"])
        self.assertIn("python -B", res["dica"])
        r = rodar_script("versao_em_uso.py", "conferir", "--raiz", self.raiz, "--projeto", "p")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_outras_pastas_que_o_manifesto_ignora_contam_como_a_mais(self):
        plantados = sorted([*(f"{nome}/plantado.py" for nome in MOD.IGNORADAS - DEPENDENCIAS), "lib/__pycache__/x.pyc"])
        for rel in plantados:
            (self.atual / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.atual / rel).write_bytes(b"print('plantado')\n")
        res = MOD.conferir(self.raiz, "p")
        self.assertEqual(res["a_mais"], plantados)
        self.assertFalse(res["ok"])

    def test_dependencias_nao_conferidas_sao_ditas_nunca_num_ok_calado(self):
        for rel in (".venv/pyvenv.cfg", "node_modules/m/index.js", "sub/venv/pyvenv.cfg", "sub/venv/lib/x.py"):
            (self.atual / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.atual / rel).write_bytes(b"#\n")
        res = MOD.conferir(self.raiz, "p")
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["nao_conferido"], [".venv/", "node_modules/", "sub/venv/"])
        self.assertIn("não conferido: .venv/", res["aviso"])
        r = rodar_script("versao_em_uso.py", "conferir", "--raiz", self.raiz, "--projeto", "p")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["nao_conferido"], [".venv/", "node_modules/", "sub/venv/"])
        self.assertIn("não conferido: .venv/", json.loads(r.stderr)["aviso"])
        for nome in (".venv", "node_modules", "sub"):
            MOD._apagar(self.atual / nome)
        res = MOD.conferir(self.raiz, "p")
        self.assertEqual((res["ok"], res["nao_conferido"], "aviso" in res), (True, [], False))

    def test_voltar_confere_a_anterior_do_mesmo_jeito(self):
        self.promover(self.propor("v2.json", "v2"))
        anterior = self.em_uso / "anteriores" / sorted(os.listdir(self.em_uso / "anteriores"))[0]
        (anterior / "__pycache__").mkdir()
        (anterior / "__pycache__" / PYC).write_bytes(b"\0")
        pedido = MOD.pedir_volta(self.raiz, "p", self.projeto / "outputs" / "versao" / "volta.json",
                                 motivo="voltar a anterior (fictício)")
        with self.assertRaises(MOD.Recusa) as ctx:
            MOD.voltar(self.raiz, "p", pedido["pedido"], pedido["sha256"], self.decisao, verificar=aceite(pedido))
        self.assertIn("difere do manifesto", str(ctx.exception))
        self.assertIn("python -B", str(ctx.exception))  # a dica do conferir também na recusa (revisão 1 da correção)
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v2'\n")
        MOD._apagar(anterior / "__pycache__")
        (anterior / ".venv").mkdir()
        (anterior / ".venv" / "pyvenv.cfg").write_bytes(b"#\n")
        res = MOD.voltar(self.raiz, "p", pedido["pedido"], pedido["sha256"], self.decisao, verificar=aceite(pedido))
        self.assertEqual(res["nao_conferido"], [".venv/"])
        self.assertIn("não conferido: .venv/", res["aviso"])
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'LEGITIMO'\n")


if __name__ == "__main__":
    unittest.main()
