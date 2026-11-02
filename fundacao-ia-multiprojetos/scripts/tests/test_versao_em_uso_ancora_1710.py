"""Revisão 1 da correção do grupo VERSAO (revisão de segurança da 1.7.10, rodada 4), KIT-F1: `scripts/versao_em_uso.py`.

A proposta (e o pedido de volta sem --para) valia pela data, que a sessão grava. Onde o sandbox confina (a sessão do
Ubuntu não lê em-uso/), a proposta saía sem o manifesto da versão em uso, e a data no futuro só recusava na hora: o
aceite ficava guardado e, passada a data, valia depois de outras trocas (a v1 voltava por cima da v2, e o pedido de
volta punha em uso a versão que a v2 corrigiu). Agora a proposta e o pedido levam a âncora da versão em uso (o SHA-256
do manifesto de atual/ e o da última troca do registro), lida de em-uso/ ou da cópia que o promover e o voltar gravam
em outputs/; vazia, só vale sem versão em uso, e a conferência é contra em-uso/ (cópia forjada só faz recusar). A data
só não pode estar mais de 5 minutos no futuro: atrás do registro, com a âncora certa, ela não recusa (revisão 2 da
correção: a camada da data recusava a entrega honesta feita com o relógio do Ubuntu atrás). Revisão 3 da correção: o
pedido com --para, assinado e não usado, continuava valendo depois de outras trocas e punha a versão pedida no lugar de
uma que entrou depois dele, sem assinatura nova; agora a âncora vale também para ele (TestPedidoComPara). A
verificação do kit é simulada, como nos testes do pacote, e o relógio dos cenários de 30 dias também. Raiz fictícia em
pasta temporária.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from apoio import SCRIPTS, criar_ligacao_dir

INICIO = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def carregar():
    spec = importlib.util.spec_from_file_location("_teste_versao_ancora_1710", SCRIPTS / "versao_em_uso.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


MOD = carregar()


def sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def aceite(alvo: dict):
    """A verificação simulada do kit: aceite assinado sobre a entrega `alvo`; uma decisão por entrega, como no kit."""
    v = {"valida": True, "tipo": "aceite", "forca": "assinatura", "motivo": "decisão assinada pelo titular",
         "entrega": {"caminho": alvo["entrega"], "sha256": alvo["sha256"]}, "decisao_id": "dec-" + alvo["sha256"][:8],
         "sha256_decisao": sha(b"decisao ficticia de " + alvo["sha256"].encode())}
    return lambda _raiz, _decisao: v


class Relogio:
    """O relógio de quem roda (sessão e terminal do titular), simulado em `MOD.datetime`: anda 1 ms a cada leitura (as
    datas nunca empatam), e `dia(n)` o põe no dia n a partir de INICIO."""

    def __init__(self):
        self.agora, relogio = INICIO, self

        class Simulado(datetime):
            @classmethod
            def now(cls, tz=None):
                relogio.agora += timedelta(milliseconds=1)
                return relogio.agora if tz is not None else relogio.agora.replace(tzinfo=None)
        self._troca = mock.patch.object(MOD, "datetime", Simulado)

    def __enter__(self):
        self._troca.start()
        return self

    def __exit__(self, *_exc):
        self._troca.stop()

    def dia(self, n: int) -> None:
        self.agora = INICIO + timedelta(days=n)

    def daqui(self, dias: int) -> str:
        return (self.agora + timedelta(days=dias)).isoformat(timespec="microseconds")


class _Raiz(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="versao-ancora-")))
        self.addCleanup(MOD._apagar, self.base)
        self.raiz = self.base / "raiz"
        self.projeto = self.raiz / "projects" / "p"
        self.trabalho = self.projeto / "trabalho"
        self.trabalho.mkdir(parents=True)
        (self.projeto / "decisoes").mkdir()
        self.decisao = self.projeto / "decisoes" / "dec.json"
        self.decisao.write_text("{}", encoding="utf-8")
        self.lista = self.base / "lista.txt"
        self.lista.write_text("**/*.py\n", encoding="utf-8")
        self.em_uso = self.raiz / "em-uso" / "p"
        self.atual = self.em_uso / "atual"
        self.copia = self.projeto / MOD.ESTADO_PARA_A_SESSAO

    def devolver(self, quem: str) -> None:
        """Os bytes de uma versão na pasta de trabalho (a sessão pode devolver os de uma antiga)."""
        (self.trabalho / "util.py").write_bytes(f"QUEM = {quem!r}\n".encode())

    def propor(self, nome: str, quem: str) -> dict:
        self.devolver(quem)
        return MOD.propor(self.raiz, "p", self.trabalho, self.lista, self.projeto / "outputs" / "versao" / nome)

    @staticmethod
    def reescrever(entrega: dict, chave: str, **mudar) -> dict:
        """A entrega com campos trocados: quem grava a proposta e o pedido é a sessão."""
        dados = json.loads(Path(entrega[chave]).read_bytes())
        dados.update(mudar)
        bruto = (json.dumps(dados, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        Path(entrega[chave]).write_bytes(bruto)
        return {**entrega, "sha256": sha(bruto)}

    def forjar(self, nome: str, quem: str, **mudar) -> dict:
        return self.reescrever(self.propor(nome, quem), "proposta", **mudar)

    def promover(self, proposta: dict) -> dict:
        return MOD.promover(self.raiz, "p", proposta["proposta"], proposta["sha256"], self.decisao,
                            verificar=aceite(proposta))

    def pedir(self, nome: str = "volta.json", **extra) -> dict:
        return MOD.pedir_volta(self.raiz, "p", self.projeto / "outputs" / "versao" / nome,
                               motivo="voltar a anterior (fictício)", **extra)

    def voltar(self, pedido: dict) -> dict:
        return MOD.voltar(self.raiz, "p", pedido["pedido"], pedido["sha256"], self.decisao, verificar=aceite(pedido))

    def em_uso_agora(self) -> bytes:
        return (self.atual / "util.py").read_bytes()

    def manifesto(self) -> str:
        return sha((self.atual / MOD.MANIFESTO_DA_VERSAO).read_bytes())

    @staticmethod
    def ancora(entrega: dict) -> dict:
        dados = json.loads(Path(entrega.get("proposta") or entrega["pedido"]).read_bytes())
        return {k: dados.get(k) for k in MOD.ANCORA}

    @staticmethod
    def escondido():
        """A sessão do Ubuntu: em-uso/ fica fora da leitura e parece ausente."""
        return mock.patch.object(MOD, "_em_uso", lambda raiz, projeto: Path(raiz) / "em-uso-fora-da-leitura" / projeto)


class TestPropostaComDataNoFuturo(_Raiz):
    """O titular assina no dia 0 a proposta da v1 com a data do dia 30 (que ele não vê); o promover recusa na hora, e a
    sessão diz "proponha de novo"; no dia 1 a v2 (a correção) entra; no dia 30 o aceite guardado não pode valer."""

    def test_sem_ancora_nao_vale_no_dia_30_depois_da_v2(self):
        with Relogio() as relogio:
            self.promover(self.propor("v0.json", "v0"))
            v1 = self.forjar("v1.json", "v1", criada_em=relogio.daqui(30), manifesto_em_uso=None, ultima_troca=None)
            with self.assertRaises(MOD.Recusa) as ctx:
                self.promover(v1)
            self.assertIn("data no futuro", str(ctx.exception))
            relogio.dia(1)
            self.promover(self.propor("v2.json", "v2-correcao"))
            relogio.dia(30)
            self.devolver("v1")
            with self.assertRaises(MOD.Recusa) as ctx:
                self.promover(v1)
        self.assertIn("não diz qual versão estava em uso", str(ctx.exception))
        self.assertIn("nada foi trocado", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v2-correcao'\n")
        self.assertEqual(len((self.em_uso / "registro.jsonl").read_text(encoding="utf-8").splitlines()), 2)

    def test_com_ancora_honesta_ou_forjada_nao_vale_depois_da_v2(self):
        with Relogio() as relogio:
            self.promover(self.propor("v0.json", "v0"))
            honesta = self.forjar("v1.json", "v1", criada_em=relogio.daqui(30))
            forjada = self.forjar("v1-forjada.json", "v1", criada_em=relogio.daqui(30), manifesto_em_uso="0" * 64,
                                  ultima_troca="1" * 64)
            relogio.dia(1)
            self.promover(self.propor("v2.json", "v2-correcao"))
            relogio.dia(30)
            self.devolver("v1")
            for proposta in (honesta, forjada):
                with self.assertRaises(MOD.Recusa) as ctx:
                    self.promover(proposta)
                self.assertIn("mudou depois da proposta", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v2-correcao'\n")

    def test_a_volta_a_v0_nao_libera_a_proposta_feita_sobre_ela(self):
        # A volta repõe a v0, com o manifesto de quando a v1 foi proposta: só a última troca do registro diz que a
        # proposta é de antes da v2 (com a data no futuro, a data não diz).
        with Relogio() as relogio:
            self.promover(self.propor("v0.json", "v0"))
            m0, v1 = self.manifesto(), self.forjar("v1.json", "v1", criada_em=relogio.daqui(30))
            relogio.dia(1)
            self.promover(self.propor("v2.json", "v2"))
            relogio.dia(2)
            self.voltar(self.pedir())
            self.assertEqual(self.manifesto(), m0)
            relogio.dia(30)
            self.devolver("v1")
            with self.assertRaises(MOD.Recusa) as ctx:
                self.promover(v1)
        self.assertIn("mudou depois da proposta", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v0'\n")


class TestAncoraDaProposta(_Raiz):
    def test_registro_que_falhou_depois_da_troca_nao_libera_a_proposta_antiga(self):
        # Só o manifesto_em_uso recusa: a promoção da v3 não entrou no registro (código 3), e nem a data nem a última
        # troca a veem (revisão 1 da correção: nenhum teste prendia o manifesto_em_uso).
        v1 = self.propor("v1.json", "v1")
        self.assertEqual(self.ancora(v1), dict.fromkeys(MOD.ANCORA), "sem versão em uso, a âncora é vazia")
        self.promover(v1)
        m1 = self.manifesto()
        v2, v3 = self.propor("v2.json", "v2"), self.propor("v3.json", "v3")
        self.assertEqual(self.ancora(v2)["manifesto_em_uso"], m1)
        with mock.patch.object(MOD, "_registrar", side_effect=OSError("disco cheio simulado")):
            self.assertTrue(self.promover(v3)["registro"].startswith("falhou:"))
        self.devolver("v2")
        with self.assertRaises(MOD.Recusa) as ctx:
            self.promover(v2)
        self.assertIn("mudou depois da proposta", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v3'\n")

    def test_ancora_fora_do_formato_recusa(self):
        self.promover(self.propor("v1.json", "v1"))
        for n, (campo, valor) in enumerate((c, v) for c in MOD.ANCORA for v in ("xyz", 5, ["0" * 64])):
            with self.subTest(campo=campo, valor=valor):
                with self.assertRaises(MOD.Recusa) as ctx:
                    self.promover(self.forjar(f"formato-{n}.json", "v2", **{campo: valor}))
                self.assertIn("fora do formato", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")


class TestPedidoSemParaComDataNoFuturo(_Raiz):
    """O titular assina o pedido "a anterior mais recente" quando ela era a v0, com a data do dia 30."""

    def setUp(self):
        super().setUp()
        self.relogio = Relogio()
        self.addCleanup(self.relogio.__exit__)
        self.relogio.__enter__()
        self.promover(self.propor("v0.json", "v0"))
        self.promover(self.propor("v1.json", "v1"))

    def test_sem_ancora_nao_vale_no_dia_30_depois_da_v2(self):
        pedido = self.reescrever(self.pedir(), "pedido", criado_em=self.relogio.daqui(30), manifesto_em_uso=None,
                                 ultima_troca=None)
        with self.assertRaises(MOD.Recusa) as ctx:
            self.voltar(pedido)
        self.assertIn("data no futuro", str(ctx.exception))
        self.relogio.dia(1)
        self.promover(self.propor("v2.json", "v2"))  # a mais recente passa a ser a v1, que a v2 corrigiu
        self.relogio.dia(30)
        with self.assertRaises(MOD.Recusa) as ctx:
            self.voltar(pedido)
        self.assertIn("não diz qual versão estava em uso", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v2'\n")

    def test_com_ancora_honesta_nao_vale_no_dia_30_depois_da_v2(self):
        pedido = self.reescrever(self.pedir(), "pedido", criado_em=self.relogio.daqui(30))
        self.relogio.dia(1)
        self.promover(self.propor("v2.json", "v2"))
        self.relogio.dia(30)
        with self.assertRaises(MOD.Recusa) as ctx:
            self.voltar(pedido)
        self.assertIn("houve promoção ou volta depois do pedido", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v2'\n")

    def test_a_volta_com_para_a_v1_nao_libera_o_pedido_antigo(self):
        # Com --para, a v1 volta (o manifesto de quando o pedido foi feito), e a anterior mais recente passa a ser a v2,
        # que o titular acabou de tirar: só a última troca do registro recusa.
        pedido = self.reescrever(self.pedir(), "pedido", criado_em=self.relogio.daqui(30))
        self.relogio.dia(1)
        self.promover(self.propor("v2.json", "v2"))
        self.relogio.dia(2)
        self.voltar(self.pedir("para-v1.json", para=sorted(os.listdir(self.em_uso / "anteriores"))[-1]))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")
        self.relogio.dia(30)
        with self.assertRaises(MOD.Recusa) as ctx:
            self.voltar(pedido)
        self.assertIn("houve promoção ou volta depois do pedido", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")


class TestCopiaDaAncoraParaASessao(_Raiz):
    def test_a_sessao_que_nao_le_em_uso_le_a_copia(self):
        res = self.promover(self.propor("v0.json", "v0"))
        self.assertEqual(res["estado_para_a_sessao"], str(self.copia))
        self.assertEqual(json.loads(self.copia.read_bytes())["manifesto_em_uso"], self.manifesto())
        with self.escondido():
            v1 = self.propor("v1.json", "v1")
        self.assertIsNone(v1["diferenca"], "a sessão do Ubuntu não vê a versão em uso")
        self.assertEqual(self.ancora(v1), MOD._estado_em_uso(self.em_uso))
        self.promover(v1)
        with self.escondido():
            pedido = self.pedir()
        self.assertEqual(self.ancora(pedido), MOD._estado_em_uso(self.em_uso))
        self.voltar(pedido)
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v0'\n")
        copia = json.loads(self.copia.read_bytes())
        self.assertEqual({k: copia[k] for k in MOD.ANCORA}, MOD._estado_em_uso(self.em_uso), "a volta também a grava")

    def test_copia_forjada_so_faz_recusar_e_a_recusa_a_regrava(self):
        self.promover(self.propor("v0.json", "v0"))
        forjada = {**json.loads(self.copia.read_bytes()), "manifesto_em_uso": "0" * 64}  # a sessão grava em outputs/
        self.copia.write_bytes(json.dumps(forjada).encode("utf-8"))
        with self.escondido():
            v1 = self.propor("v1.json", "v1")
        with self.assertRaises(MOD.Recusa) as ctx:
            self.promover(v1)
        self.assertIn("mudou depois da proposta", str(ctx.exception))
        self.assertIn(f"gravada em {MOD.ESTADO_PARA_A_SESSAO}", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v0'\n")
        with self.escondido():
            v1 = self.propor("v1-de-novo.json", "v1")
        self.promover(v1)
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")

    def test_sem_a_copia_a_proposta_sai_sem_ancora_e_a_recusa_a_grava(self):
        # Como numa versão em uso de antes desta revisão, sem a cópia: uma proposta de novo, e vale.
        self.promover(self.propor("v0.json", "v0"))
        self.copia.unlink()
        with self.escondido():
            v1 = self.propor("v1.json", "v1")
        self.assertEqual(self.ancora(v1), dict.fromkeys(MOD.ANCORA))
        with self.assertRaises(MOD.Recusa) as ctx:
            self.promover(v1)
        self.assertIn("não diz qual versão estava em uso", str(ctx.exception))
        self.assertTrue(self.copia.is_file())
        with self.escondido():
            v1 = self.propor("v1-de-novo.json", "v1")
        self.promover(v1)
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")

    def test_pasta_da_copia_que_e_ligacao_nao_e_seguida(self):
        # A sessão troca outputs/versao por uma ligação: o promover (terminal do titular) não grava por ela, e diz.
        fora = self.base / "fora"
        fora.mkdir()
        (self.projeto / "outputs").mkdir()
        criar_ligacao_dir(self.projeto / "outputs" / "versao", fora)
        self.devolver("v0")
        v0 = MOD.propor(self.raiz, "p", self.trabalho, self.lista, self.projeto / "outputs" / "v0.json")
        args = ["promover", "--raiz", str(self.raiz), "--projeto", "p", "--proposta", v0["proposta"],
                "--proposta-sha256", v0["sha256"], "--decisao", str(self.decisao)]
        with mock.patch.object(MOD, "verificar_decisao_pelo_kit", aceite(v0)), \
                mock.patch.object(sys, "stdout", io.StringIO()) as saida, \
                mock.patch.object(sys, "stderr", io.StringIO()) as erro:
            self.assertEqual(MOD.main(args), 0, "a troca aconteceu: nem recusa (2) nem registro falho (3)")
        self.assertTrue(json.loads(saida.getvalue())["estado_para_a_sessao"].startswith("falhou:"))
        self.assertIn("não foi gravada", json.loads(erro.getvalue())["aviso"])
        self.assertEqual(os.listdir(fora), [])
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v0'\n")


class TestMensagemDaData(_Raiz):
    """Sessão no Ubuntu e promover no PowerShell: o relógio de onde a entrega foi feita atrás do terminal do titular
    (30 s e 30 minutos), sem troca nenhuma depois dela. A âncora confere, e ela já prova que nenhuma troca foi
    registrada depois da entrega: a data não recusa (revisão 2 da correção: a camada da data recusava a proposta e o
    pedido honestos, e a dica de rodar no mesmo sistema não resolvia). A entrega feita antes de outra troca, com o mesmo
    relógio atrasado, continua recusada, pela âncora."""

    def atrasada(self, segundos: int) -> str:
        ultima = json.loads((self.em_uso / "registro.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        return (datetime.fromisoformat(ultima["quando"]) - timedelta(seconds=segundos)).isoformat()

    def test_proposta(self):
        self.promover(self.propor("v1.json", "v1"))
        v3 = self.forjar("v3.json", "v3", criada_em=self.atrasada(30 * 60))  # feita antes da v2, com o relógio atrás
        self.promover(self.forjar("v2.json", "v2", criada_em=self.atrasada(30)))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v2'\n")
        self.promover(self.forjar("v4.json", "v4", criada_em=self.atrasada(30 * 60)))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v4'\n")
        self.devolver("v3")
        with self.assertRaises(MOD.Recusa) as ctx:
            self.promover(v3)
        self.assertIn("mudou depois da proposta", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v4'\n")

    def test_pedido_sem_para(self):
        self.promover(self.propor("v1.json", "v1"))
        self.promover(self.propor("v2.json", "v2"))
        self.voltar(self.reescrever(self.pedir(), "pedido", criado_em=self.atrasada(30)))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")
        antigo = self.reescrever(self.pedir("antigo.json"), "pedido", criado_em=self.atrasada(30 * 60))
        self.promover(self.propor("v3.json", "v3"))  # depois do pedido: a anterior mais recente mudou
        with self.assertRaises(MOD.Recusa) as ctx:
            self.voltar(antigo)
        self.assertIn("houve promoção ou volta depois do pedido", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v3'\n")
        anteriores = self.em_uso / "anteriores"
        mais_recente = (anteriores / sorted(os.listdir(anteriores))[-1] / "util.py").read_bytes()
        self.voltar(self.reescrever(self.pedir("de-novo.json"), "pedido", criado_em=self.atrasada(30 * 60)))
        self.assertEqual(self.em_uso_agora(), mais_recente)


class TestPedidoComPara(_Raiz):
    """Revisão 3 da correção (a sonda da revisão 3, com o kit de verdade): v0 e v1 promovidas; o pedido --para a
    anterior da v0 e o pedido sem --para, assinados e não usados; v2 promovida. O sem --para recusava, e o com --para
    punha a v0 em uso por cima da v2, sem assinatura nova. Agora o pedido, com ou sem --para, vale para a volta a partir
    da versão em uso de quando foi feito (a âncora, conferida antes da trava e dentro dela)."""

    def setUp(self):
        super().setUp()
        self.promover(self.propor("v0.json", "v0"))
        self.promover(self.propor("v1.json", "v1"))
        self.a0 = sorted(os.listdir(self.em_uso / "anteriores"))[0]  # a anterior que guarda a v0

    def trocas(self) -> int:
        return len((self.em_uso / "registro.jsonl").read_bytes().splitlines())

    def test_pedido_com_para_nao_vale_depois_de_outra_promocao(self):
        com_para, sem_para = self.pedir("com-para.json", para=self.a0), self.pedir("sem-para.json")
        self.promover(self.propor("v2.json", "v2"))
        real, travas = MOD._trava, []
        for pedido in (sem_para, com_para):
            with self.subTest(pedido["entrega"]):
                with mock.patch.object(MOD, "_trava", lambda em_uso: travas.append(em_uso) or real(em_uso)), \
                        self.assertRaises(MOD.Recusa) as ctx:
                    self.voltar(pedido)
                self.assertIn("houve promoção ou volta depois do pedido", str(ctx.exception))
                self.assertIn("nada foi trocado", str(ctx.exception))
        self.assertEqual(travas, [], "recusa já na conferência de fora da trava, antes de conferir a anterior")
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v2'\n")
        self.assertEqual(self.trocas(), 3)
        self.voltar(self.pedir("com-para-de-novo.json", para=self.a0))  # feito sobre a versão em uso de agora: vale
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v0'\n")

    def test_pedido_com_para_nao_vale_depois_de_uma_volta(self):
        # Dois pedidos com --para, assinados; o titular roda um (a v1 volta): o outro punha a v0 no lugar dela.
        self.promover(self.propor("v2.json", "v2"))
        a0, a1 = sorted(os.listdir(self.em_uso / "anteriores"))
        para_v0, para_v1 = self.pedir("para-v0.json", para=a0), self.pedir("para-v1.json", para=a1)
        self.voltar(para_v1)
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")
        with self.assertRaises(MOD.Recusa) as ctx:
            self.voltar(para_v0)
        self.assertIn("houve promoção ou volta depois do pedido", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")
        self.assertEqual(self.trocas(), 4)

    def test_troca_que_entra_antes_da_trava_recusa_o_pedido_com_para(self):
        # A conferência de fora da trava passa; uma promoção entra antes da trava (outra janela do titular): a de dentro
        # da trava recusa (sem ela, a v0 entrava por cima da v2).
        pedido, v2 = self.pedir("com-para.json", para=self.a0), self.propor("v2.json", "v2")
        real, entrou = MOD._trava, []

        def trava(em_uso):
            if not entrou:
                entrou.append(em_uso)
                self.promover(v2)  # com a trava de verdade: esta função já não promove de novo
            return real(em_uso)
        with mock.patch.object(MOD, "_trava", trava), self.assertRaises(MOD.Recusa) as ctx:
            self.voltar(pedido)
        self.assertEqual(len(entrou), 1, "a promoção entrou entre a conferência de fora e a trava")
        self.assertIn("houve promoção ou volta depois do pedido", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v2'\n")
        self.assertEqual(self.trocas(), 3)

    def test_pedido_com_para_sem_ancora_recusa_e_a_recusa_grava_a_copia(self):
        # A sessão do Ubuntu sem a cópia da âncora (como numa versão em uso de antes desta revisão): o pedido sai sem
        # âncora, e o voltar o recusa e grava a cópia; o pedido de novo vale.
        self.copia.unlink()
        with self.escondido():
            pedido = self.pedir("sem-ancora.json", para=self.a0)
        self.assertEqual(self.ancora(pedido), dict.fromkeys(MOD.ANCORA))
        with self.assertRaises(MOD.Recusa) as ctx:
            self.voltar(pedido)
        self.assertIn("o pedido não diz qual versão estava em uso", str(ctx.exception))
        self.assertTrue(self.copia.is_file())
        with self.escondido():
            pedido = self.pedir("com-ancora.json", para=self.a0)
        self.voltar(pedido)
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v0'\n")


if __name__ == "__main__":
    unittest.main()
